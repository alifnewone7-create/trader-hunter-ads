import asyncio
import logging
import os
from datetime import timedelta

from bot import esc, now
from db import db
from rich import btn, panel, send_rich, tg
from settings_store import get_settings, update_settings

log = logging.getLogger("extras")
ADMIN_IDS = {int(x) for x in os.environ["ADMIN_IDS"].replace(" ", "").split(",") if x}
NOTIFY_ICON = '<tg-emoji emoji-id="5886412370347036129">🔔</tg-emoji>'
COUNT_ICON = '<tg-emoji emoji-id="5447279224488490651">👥</tg-emoji>'
PERMISSION = "Invite Users via Link (needed to approve join requests)"
MEMBER_STATUSES = {"creator", "administrator", "member"}
HOME = [btn("⬅️ Back", "m:home", "danger")]
_tasks = set()


def spawn(coro):
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def ensure_admin(uid):
    if uid in ADMIN_IDS:
        await db.admins.update_one({"user_id": uid}, {"$setOnInsert": {"chat_id": uid, "name": str(uid),
                                   "logged_in_at": now(), "awaiting": None}}, upsert=True)


async def seed_admins():
    await db.admins.delete_many({"user_id": {"$nin": list(ADMIN_IDS)}})
    for uid in ADMIN_IDS:
        await ensure_admin(uid)
    await tg("deleteMyCommands")
    for uid in ADMIN_IDS:
        await tg("deleteMyCommands", scope={"type": "chat", "chat_id": uid})


async def set_state(uid, awaiting, **ctx):
    await db.admins.update_one({"user_id": uid}, {"$set": {"awaiting": awaiting, "ctx": ctx}})


async def upsert_user(user, started=False):
    t = now()
    fields = {"first_name": user.get("first_name"), "username": user.get("username"), "last_active": t}
    if started:
        fields.update(started=True, is_blocked=False)
    r = await db.users.update_one({"user_id": user["id"]}, {"$set": fields, "$setOnInsert": {
        "joined_at": t, **({} if started else {"started": False, "is_blocked": False})}}, upsert=True)
    return r.upserted_id is not None


async def notify_new_user(user, source):
    if not (await get_settings())["notify"]:
        return
    uname = f"@{esc(user['username'])}" if user.get("username") else "—"
    count = await db.users.count_documents({})
    text = (f"{NOTIFY_ICON} <b>New User ( {source} )</b>\n\n<b>Name : {esc(user.get('first_name'))}</b>\n"
            f"<b>Username : {uname}</b>\n<b>User Id : {user['id']}</b>\n\n{COUNT_ICON} <b>User Count : {count}</b>")
    for a in await db.admins.find({}, {"chat_id": 1}).to_list(50):
        await send_rich(a["chat_id"], text)


async def has_requested(uid):
    return bool(await db.join_requests.count_documents({"telegram_user_id": uid})
                or await db.members.count_documents({"user_id": uid}))


async def mark_unrequested(user):
    uid = user["id"]
    if await has_requested(uid):
        return
    t = now()
    await db.unrequested.update_one({"user_id": uid}, {"$set": {
        "first_name": user.get("first_name"), "username": user.get("username"), "last_start_at": t},
        "$setOnInsert": {"started_at": t}}, upsert=True)
    if await has_requested(uid):
        await clear_unrequested(uid)


async def clear_unrequested(uid):
    await db.unrequested.delete_many({"user_id": uid})


async def sync_unrequested():
    started = set(await db.users.distinct("user_id", {"started": True}))
    requested = set(await db.join_requests.distinct("telegram_user_id"))
    requested |= set(await db.members.distinct("user_id"))
    current = set(await db.unrequested.distinct("user_id"))
    if current & requested:
        await db.unrequested.delete_many({"user_id": {"$in": list(current & requested)}})
    missing = list(started - requested - current)
    users = {u["user_id"]: u for u in await db.users.find({"started": True}).to_list(None)} if missing else {}
    for uid in missing:
        u = users.get(uid, {})
        await db.unrequested.update_one({"user_id": uid}, {"$set": {
            "first_name": u.get("first_name"), "username": u.get("username"), "last_start_at": u.get("last_active")},
            "$setOnInsert": {"started_at": u.get("joined_at") or now()}}, upsert=True)
    log.info("unrequested synced: %s", await db.unrequested.count_documents({}))


async def on_chat_member(upd):
    chat, s = upd.get("chat", {}), await get_settings()
    if chat.get("id") != s["channel_id"]:
        return
    old, new = upd.get("old_chat_member", {}), upd.get("new_chat_member", {})
    user = new.get("user") or {}
    if user.get("is_bot"):
        return
    was = old.get("status") in MEMBER_STATUSES or old.get("is_member")
    is_ = new.get("status") in MEMBER_STATUSES or (new.get("status") == "restricted" and new.get("is_member"))
    if was == is_:
        return
    from bot import is_bot_link
    key = {"user_id": user["id"], "chat_id": chat["id"]}
    if is_:
        known = await db.join_requests.count_documents({"chat_id": chat["id"], "telegram_user_id": user["id"]})
        if not known and not is_bot_link(upd, s):
            return
    elif not await db.members.count_documents(key):
        return
    await upsert_user(user)
    await db.members.update_one({"user_id": user["id"], "chat_id": chat["id"]},
                                {"$set": {"status": "joined" if is_ else "left", "updated_at": now()}}, upsert=True)
    await clear_unrequested(user["id"])
    if is_:
        await db.join_requests.update_many({"chat_id": chat["id"], "telegram_user_id": user["id"], "status": "pending"},
                                           {"$set": {"status": "approved", "decided_at": now()}})


async def audience_ids(audience):
    s = await get_settings()
    pending = set(await db.join_requests.distinct("telegram_user_id", {"status": "pending", "chat_id": s["channel_id"]}))
    if audience == "pending":
        return pending
    if audience == "joined":
        return set(await db.members.distinct("user_id", {"status": "joined", "chat_id": s["channel_id"]}))
    if audience == "unrequested":
        return set(await db.unrequested.distinct("user_id"))
    if audience == "leaved":
        return set(await db.members.distinct("user_id", {"status": "left", "chat_id": s["channel_id"]})) - pending
    ids = set(await db.users.distinct("user_id")) | set(await db.members.distinct("user_id"))
    ids |= set(await db.join_requests.distinct("telegram_user_id")) | set(await db.leads.distinct("telegram_user_id"))
    return {i for i in ids if i}


async def stats_text():
    s, t = await get_settings(), now()
    rng = lambda d: db.users.count_documents({"joined_at": {"$gte": t - timedelta(days=d)}})  # noqa: E731
    members = s.get("member_count", 0)
    if s["channel_id"]:
        r = await tg("getChatMemberCount", chat_id=s["channel_id"])
        if r.get("ok"):
            members = r["result"]
            await update_settings(member_count=members)
    c = {
        "24h": await rng(1), "7d": await rng(7), "30d": await rng(30), "all": await db.users.count_documents({}),
        "approved": await db.join_requests.count_documents({"status": "approved"}),
        "pending": len(await audience_ids("pending")), "joined": len(await audience_ids("joined")),
        "leaved": len(await audience_ids("leaved")), "unrequested": await db.unrequested.count_documents({}),
        "started": await db.users.count_documents({"started": True}),
        "blocked": await db.users.count_documents({"is_blocked": True}),
    }
    return (f"📊 <b>Statistics</b> (realtime)\n\n👥 <b>New Users</b>\n├ 24h: <b>{c['24h']}</b>\n├ 7d: <b>{c['7d']}</b>\n"
            f"├ 30d: <b>{c['30d']}</b>\n└ All Time: <b>{c['all']}</b>\n\n✅ Approved: <b>{c['approved']}</b>  "
            f"⏳ Pending: <b>{c['pending']}</b>\n🟢 Joined: <b>{c['joined']}</b>  🚪 Leaved: <b>{c['leaved']}</b>\n"
            f"📝 Unrequested: <b>{c['unrequested']}</b>\n"
            f"👥 Channel Members: <b>{members}</b>\n🤖 Bot started: <b>{c['started']}</b>  🚫 Blocked: <b>{c['blocked']}</b>"
            f"\n\n🕒 Updated: <code>{t.strftime('%Y-%m-%d %H:%M:%S')} UTC</code>")


STATS_KB = [[btn("✅ Approve All", "adm:apall", "success")],
            [btn("🔄 Refresh", "adm:stats", "primary"), btn("🕒 Custom Time", "ct:open", "success")], HOME]


async def answer(cq, text=None, alert=False):
    await tg("answerCallbackQuery", callback_query_id=cq["id"], text=text, show_alert=alert or None)


async def approve_one(chat_id, uid, retries=3):
    for _ in range(retries):
        r = await tg("approveChatJoinRequest", chat_id=chat_id, user_id=uid)
        d = r.get("description", "")
        if r.get("ok") or "USER_ALREADY_PARTICIPANT" in d:
            status = "approved"
        elif "HIDE_REQUESTER_MISSING" in d or "not found" in d.lower():
            status = "gone"
        elif r.get("error_code") == 429:
            await asyncio.sleep((r.get("parameters") or {}).get("retry_after", 3) + 1)
            continue
        else:
            status = "failed"
        if status != "failed":
            await db.join_requests.update_many({"chat_id": chat_id, "telegram_user_id": uid, "status": "pending"}, {
                "$set": {"status": "approved" if status == "approved" else "declined", "decided_at": now()}})
        return status
    return "failed"


def approve_report(title, total, res):
    return (f"{title}\n\n⏳ Pending: <b>{total}</b>\n✅ Approved: <b>{res['approved']}</b>\n"
            f"🚫 Request not found (declined / cancelled): <b>{res['gone']}</b>\n❌ Failed: <b>{res['failed']}</b>")


async def run_approve_all(chat_id, mid, channel_id):
    ids = await db.join_requests.distinct("telegram_user_id", {"chat_id": channel_id, "status": "pending"})
    res = {"approved": 0, "gone": 0, "failed": 0}
    for i, uid in enumerate(ids, 1):
        res[await approve_one(channel_id, uid)] += 1
        await asyncio.sleep(0.05)
        if i % 25 == 0:
            await panel(chat_id, approve_report("🚀 <b>Approving pending requests...</b>", len(ids), res), [], mid)
    log.info("Approve all in %s done: %s", channel_id, res)
    await panel(chat_id, approve_report("✅ <b>Approve All finished</b>", len(ids), res),
                [[btn("⬅️ Back", "adm:stats", "danger")]], mid)


async def channel_text():
    s = await get_settings()
    if not s["channel_id"]:
        return ("📡 <b>Channel</b>\n\nNo channel added yet.\n\nTap <b>➕ Add Channel</b>, then pick your channel. The bot is "
                f"added as admin with only one permission: <b>{PERMISSION}</b>.\n\nOnly 1 channel can be added."), False
    return (f"📡 <b>Channel</b>\n\n• <b>{esc(s['channel_title'])}</b> (<code>{s['channel_id']}</code>)\n"
            f"🔐 Permission: <b>{PERMISSION}</b>\n🔗 Join-request link: {esc(s['invite_link']) or '—'}\n\n"
            "Only 1 channel can be added. Delete this channel to add another one."), True


async def show_channel(chat_id, mid=None):
    text, has = await channel_text()
    rows = [[btn("🗑 Delete Channel", "ch:del", "danger")]] if has else [[btn("➕ Add Channel", "ch:add", "success")]]
    await panel(chat_id, text, rows + [[btn("⬅️ Back", "m:settings", "danger")]], mid)


RIGHTS = {k: False for k in ("is_anonymous", "can_manage_chat", "can_delete_messages", "can_manage_video_chats",
                             "can_restrict_members", "can_promote_members", "can_change_info", "can_post_stories",
                             "can_edit_stories", "can_delete_stories", "can_post_messages", "can_edit_messages",
                             "can_pin_messages", "can_manage_topics")} | {"can_invite_users": True}
PICKER_CANCEL = "❌ Cancel"
PICKER = {"keyboard": [[{"text": "📡 Select Channel", "style": "success", "request_chat": {
    "request_id": 1, "chat_is_channel": True, "user_administrator_rights": RIGHTS,
    "bot_administrator_rights": RIGHTS, "request_title": True}}], [{"text": PICKER_CANCEL, "style": "danger"}]],
    "resize_keyboard": True, "one_time_keyboard": True}
REMOVE_KB = {"remove_keyboard": True}


async def on_chat_shared(m):
    from admin_panel import set_channel
    chat_id, shared = m["chat"]["id"], m["chat_shared"]
    ok, info = await set_channel(shared["chat_id"])
    if ok:
        info = f"✅ Channel added: <b>{esc((await get_settings())['channel_title'])}</b>"
    await send_rich(chat_id, info, reply_markup=REMOVE_KB)
    await show_channel(chat_id)


async def on_channel_cb(cq, data, chat_id, mid):
    s = await get_settings()
    if data == "ch:add":
        if s["channel_id"]:
            return await answer(cq, "⚠️ Only 1 channel can be added. Delete the current one first.", True)
        await answer(cq)
        return await send_rich(chat_id, "📡 <b>Add Channel</b>\n\nTap <b>📡 Select Channel</b> below and choose your "
                               f"channel.\nThe bot will be made admin with only: <b>{PERMISSION}</b>.", reply_markup=PICKER)
    if not s["channel_id"]:
        await answer(cq, "⚠️ No channel added", True)
        return await show_channel(chat_id, mid)
    if data == "ch:del":
        await answer(cq)
        return await panel(chat_id, f"🗑 <b>Delete Channel</b>\n\nRemove <b>{esc(s['channel_title'])}</b>?\nThe bot will "
                           "leave the channel and stop working there.",
                           [[btn("✅ Yes, Delete", "ch:delok", "danger"), btn("❌ No", "adm:channels", "primary")]], mid)
    await update_settings(channel_id=None, channel_title=None, invite_link=None)
    await tg("leaveChat", chat_id=s["channel_id"])
    await answer(cq, "🗑 Channel deleted")
    await show_channel(chat_id, mid)


async def on_stats_cb(cq, data, chat_id, mid):
    s = await get_settings()
    if data == "adm:stats":
        await answer(cq, "🔄 Updated")
        return await panel(chat_id, await stats_text(), STATS_KB, mid)
    if not s["channel_id"]:
        return await answer(cq, "⚠️ No channel added", True)
    total = await db.join_requests.count_documents({"chat_id": s["channel_id"], "status": "pending"})
    if not total:
        return await answer(cq, "✅ No pending requests", True)
    await answer(cq)
    if data == "adm:apall":
        return await panel(chat_id, f"✅ <b>Approve All</b>\n\nApprove all <b>{total}</b> pending join requests in "
                           f"<b>{esc(s['channel_title'])}</b>?",
                           [[btn("✅ Yes, Approve All", "adm:apgo", "success"), btn("❌ No", "adm:stats", "danger")]], mid)
    await panel(chat_id, "🚀 <b>Approving pending requests...</b>", [], mid)
    spawn(run_approve_all(chat_id, mid, s["channel_id"]))
