import asyncio
import logging

from buttons import preview_rows, show_list
from db import db
from extras import HOME, answer, audience_ids, set_state, spawn
from rich import LAYOUTS, btn, count_custom_emoji, panel, send_rich, tg

log = logging.getLogger("broadcast")
AUDIENCES = {"joined": "🟢 Joined Users", "pending": "⏳ Pending Users", "leaved": "🚪 Leaved Users",
             "unrequested": "📝 Unrequested Users", "all": "👥 All Users"}
AUD_STYLE = {"joined": "success", "pending": "primary", "leaved": "danger", "unrequested": "primary", "all": "success"}
CANCEL = [[btn("❌ Cancel", "adm:cancel", "danger")]]


async def show_broadcast(chat_id, mid=None):
    counts = {k: len(await audience_ids(k)) for k in AUDIENCES}
    text = "📢 <b>Broadcast</b>\n\n" + "\n".join(f"{v}: <b>{counts[k]}</b>" for k, v in AUDIENCES.items()) + \
           "\n\nSelect which users should receive the message 👇"
    cells = [btn(f"{v} ({counts[k]})", f"bc:{k}", AUD_STYLE[k]) for k, v in AUDIENCES.items()]
    await panel(chat_id, text, [cells[:2], cells[2:4], cells[4:], HOME], mid)


def report(title, total, res):
    return (f"{title}\n\n👥 Target: <b>{total}</b>\n✅ Sent: <b>{res['sent']}</b>\n🚫 Blocked: <b>{res['blocked']}</b>\n"
            f"❌ Failed: <b>{res['failed']}</b>")


async def copy(uid, from_chat, msg_id, kb, retries=3):
    for _ in range(retries):
        r = await tg("copyMessage", chat_id=uid, from_chat_id=from_chat, message_id=msg_id, reply_markup=kb)
        if r.get("ok"):
            return "sent"
        if r.get("error_code") == 429:
            await asyncio.sleep((r.get("parameters") or {}).get("retry_after", 3) + 1)
            continue
        if r.get("error_code") == 403:
            await db.users.update_one({"user_id": uid}, {"$set": {"is_blocked": True}})
            return "blocked"
        if kb and "icon_custom_emoji_id" in str(kb):
            kb = {"inline_keyboard": [[{k: v for k, v in b.items() if k != "icon_custom_emoji_id"} for b in row]
                                      for row in kb["inline_keyboard"]]}
            continue
        return "failed"
    return "failed"


async def run_broadcast(admin_chat, bc):
    ids = sorted(await audience_ids(bc["audience"]))
    name = AUDIENCES[bc["audience"]].split(" ", 1)[1]
    rows = preview_rows(bc)
    kb = {"inline_keyboard": rows} if rows else None
    res = {"sent": 0, "blocked": 0, "failed": 0}
    status = await send_rich(admin_chat, report(f"📢 <b>Broadcast running</b> ({name})", len(ids), res))
    smid = (status.get("result") or {}).get("message_id")
    for i, uid in enumerate(ids, 1):
        res[await copy(uid, bc["from_chat"], bc["msg_id"], kb)] += 1
        await asyncio.sleep(0.04)
        if i % 25 == 0 and smid:
            await panel(admin_chat, report(f"📢 <b>Broadcast running</b> ({name})", len(ids), res), [], smid)
    log.info("Broadcast %s done: %s", bc["audience"], res)
    await panel(admin_chat, report(f"✅ <b>Broadcast finished</b> ({name})", len(ids), res), [], smid)


async def on_bc_cb(cq, data, chat_id, mid):
    uid = cq["from"]["id"]
    key = data.split(":", 1)[1]
    if data == "adm:bc":
        await set_state(uid, None)
        await answer(cq)
        return await show_broadcast(chat_id, mid)
    if key in AUDIENCES:
        total = len(await audience_ids(key))
        await db.admins.update_one({"user_id": uid}, {"$set": {"bc": None}})
        await set_state(uid, "bc_wait", audience=key)
        await answer(cq)
        return await panel(chat_id, f"📢 <b>Broadcast → {AUDIENCES[key]}</b> ({total})\n\nSend the message you want to "
                           "broadcast (text / photo / video / file / sticker). Formatting and ✨ Premium (custom) emoji "
                           "are kept as they are.", CANCEL, mid)
    bc = ((await db.admins.find_one({"user_id": uid})) or {}).get("bc")
    if not bc:
        return await answer(cq, "⚠️ Broadcast session expired. Start again.", True)
    if key == "done":
        await answer(cq)
        rows = preview_rows(bc)
        await tg("copyMessage", chat_id=chat_id, from_chat_id=bc["from_chat"], message_id=bc["msg_id"],
                 reply_markup={"inline_keyboard": rows} if rows else None)
        total = len(await audience_ids(bc["audience"]))
        return await send_rich(chat_id, f"👆 Preview above. This message will be sent to <b>{total}</b> "
                               f"{AUDIENCES[bc['audience']]}.\n🔘 Buttons: <b>{len(bc['buttons'])}</b>  📐 Layout: "
                               f"<b>{LAYOUTS[bc.get('layout') or 1]}</b>\n✨ Premium emoji: <b>{bc.get('emoji', 0)}</b>"
                               "\n\nConfirm?", [[btn("🚀 Send Now", "bc:go", "success"),
                                                 btn("❌ Cancel", "adm:cancel", "danger")]])
    if key == "go":
        await db.admins.update_one({"user_id": uid}, {"$set": {"bc": None}})
        await answer(cq)
        await panel(chat_id, "🚀 Broadcast started...", [], mid)
        spawn(run_broadcast(chat_id, bc))


async def on_bc_message(m, admin):
    uid = admin["user_id"]
    bc = {"audience": (admin.get("ctx") or {}).get("audience", "all"), "from_chat": m["chat"]["id"],
          "msg_id": m["message_id"], "buttons": [], "layout": 1, "emoji": count_custom_emoji(m)}
    await db.admins.update_one({"user_id": uid}, {"$set": {"bc": bc}})
    await set_state(uid, None)
    await show_list(m["chat"]["id"], "bc", bc)
