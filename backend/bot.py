import asyncio
import html
import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from db import DuplicateKeyError, ReturnDocument

from db import db
from meta_capi import build_user_data, send_event
from settings_store import get_settings
from telegram_api import tg

log = logging.getLogger("bot")
_seen_updates = OrderedDict()
_bg = set()


def _persist_done(t):
    _bg.discard(t)
    if not t.cancelled() and t.exception():
        log.warning("saving processed update failed: %s", t.exception())
BD = timezone(timedelta(hours=6))


def now():
    return datetime.now(timezone.utc)


def esc(s):
    return html.escape(str(s if s is not None else ""))


def fmt(dt):
    return dt.astimezone(BD).strftime("%d %b, %I:%M %p") if dt else "—"


def name_of(u: dict) -> str:
    full = " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x) or "User"
    return f"{full} (@{u['username']})" if u.get("username") else full


async def send(chat_id, text, kb=None):
    return await tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                    reply_markup={"inline_keyboard": kb} if kb else None, disable_web_page_preview=True)


async def show(chat_id, text, kb, message_id=None):
    if message_id:
        r = await tg("editMessageText", chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML",
                     reply_markup={"inline_keyboard": kb}, disable_web_page_preview=True)
        if r.get("ok") or "not modified" in r.get("description", ""):
            return
    await send(chat_id, text, kb)


async def send_join_link(chat_id, user=None):
    from wlc import send_start
    await send_start(chat_id, user or {})


async def on_start(m: dict, user: dict, text: str):
    parts = text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else None
    t = now()
    visitor_id = None
    if token:
        tok = await db.start_tokens.find_one_and_update(
            {"token": token, "used": False, "expires_at": {"$gt": t}},
            {"$set": {"used": True, "used_by": user["id"], "used_at": t}},
        )
        visitor_id = tok["visitor_id"] if tok else None
    await send_join_link(m["chat"]["id"], user)
    uid = user["id"]
    fields = {"username": user.get("username"), "first_name": user.get("first_name"),
              "last_name": user.get("last_name"), "last_start_at": t, "updated_at": t}
    lead = await db.leads.find_one({"telegram_user_id": uid}, {"subscribe_status": 1})
    if visitor_id and (not lead or lead.get("subscribe_status") != "sent"):
        fields.update(visitor_id=visitor_id, matched_at=t)
    await db.leads.update_one(
        {"telegram_user_id": uid},
        {"$set": fields, "$setOnInsert": {"started_at": t, "subscribe_status": "none"}},
        upsert=True,
    )
    from extras import mark_unrequested, notify_new_user, upsert_user
    if await upsert_user(user, started=True):
        await notify_new_user(user, "Start")
    await mark_unrequested(user)


async def fire_subscribe(uid: int, chat_id: int, req_date: int, channel_title: str) -> dict:
    lead = await db.leads.find_one_and_update(
        {"telegram_user_id": uid, "visitor_id": {"$ne": None}, "subscribe_status": {"$nin": ["sent", "sending"]}},
        {"$set": {"subscribe_status": "sending"}},
        return_document=ReturnDocument.AFTER,
    )
    if not lead:
        current = await db.leads.find_one({"telegram_user_id": uid}) or {}
        if current.get("subscribe_status") in ("sent", "sending"):
            return {"status": "sent", "note": "আগেই পাঠানো হয়েছে"}
        await db.leads.update_one({"telegram_user_id": uid},
                                  {"$set": {"subscribe_status": "unmatched", "subscribe_at": now()}})
        return {"status": "unmatched"}
    visitor = await db.visitors.find_one({"visitor_id": lead["visitor_id"]}) or {"visitor_id": lead["visitor_id"]}
    res = await send_event("Subscribe", f"sub_{chat_id}_{uid}", build_user_data(visitor),
                           source_url=visitor.get("landing_url"), event_time=req_date,
                           custom_data={"content_name": channel_title or "Telegram channel"})
    status = "sent" if res["ok"] else "failed"
    await db.leads.update_one({"telegram_user_id": uid}, {"$set": {
        "subscribe_status": status, "subscribe_at": now(), "subscribe_error": res.get("error"),
        "subscribe_test": res.get("test"), "fbtrace_id": res.get("fbtrace_id")}})
    return {"status": status, "error": res.get("error"), "test": res.get("test")}


async def first_request(chat_id, uid, t):
    try:
        await db.jr_notified.insert_one({"_id": f"{chat_id}:{uid}", "created_at": t})
    except DuplicateKeyError:
        return False
    return not await db.join_requests.count_documents({"chat_id": chat_id, "telegram_user_id": uid})


_jr_locks = {}


def is_bot_link(upd, s):
    used = ((upd.get("invite_link") or {}).get("invite_link") or "").strip().rstrip("/")
    return bool(used and s.get("invite_link") and used == s["invite_link"].strip().rstrip("/"))


async def on_join_request(jr: dict):
    key = (jr["chat"]["id"], jr["from"]["id"])
    lock = _jr_locks.setdefault(key, asyncio.Lock())
    try:
        async with lock:
            await _on_join_request(jr)
    finally:
        if not lock.locked() and not getattr(lock, "_waiters", None):
            _jr_locks.pop(key, None)


async def _on_join_request(jr: dict):
    from admin_panel import notify_join_request
    from extras import approve_one, clear_unrequested, notify_new_user, upsert_user
    s = await get_settings()
    chat_id = jr["chat"]["id"]
    if s["channel_id"] and chat_id != s["channel_id"]:
        return
    if not is_bot_link(jr, s):
        return
    user = jr["from"]
    uid = user["id"]
    t = now()
    first = await first_request(chat_id, uid, t)
    await db.join_requests.update_one(
        {"chat_id": chat_id, "telegram_user_id": uid, "status": "pending"},
        {"$set": {"name": name_of(user), "request_date": jr.get("date")}, "$setOnInsert": {"created_at": t}},
        upsert=True,
    )
    await clear_unrequested(uid)
    await db.leads.update_one(
        {"telegram_user_id": uid},
        {"$set": {"username": user.get("username"), "first_name": user.get("first_name"),
                  "last_name": user.get("last_name"), "join_requested_at": t, "updated_at": t},
         "$setOnInsert": {"subscribe_status": "none"}},
        upsert=True,
    )
    if await upsert_user(user):
        await notify_new_user(user, "Join Request")
    result = await fire_subscribe(uid, chat_id, jr.get("date") or int(t.timestamp()), s["channel_title"])
    auto = await approve_one(chat_id, uid) if s["auto_approve"] else None
    if first:
        await notify_join_request(chat_id, user, result, auto)


async def on_message(m: dict):
    from admin_panel import on_admin_input, on_admin_login, show_menu
    from extras import ADMIN_IDS, PICKER_CANCEL, REMOVE_KB, ensure_admin, on_chat_shared, show_channel
    from rich import send_rich
    if m.get("chat", {}).get("type") != "private":
        return
    user = m.get("from") or {}
    chat_id = m["chat"]["id"]
    text = (m.get("text") or "").strip()
    if text.startswith("/start"):
        from cooldown import blocked
        if blocked(chat_id, user.get("id")):
            return
        return await on_start(m, user, text)
    await ensure_admin(user.get("id"))
    if text.startswith("/admin"):
        return await on_admin_login(m, user, text)
    admin = await db.admins.find_one({"user_id": user.get("id")}) if user.get("id") in ADMIN_IDS else None
    if not admin:
        return await send_join_link(chat_id, user)
    if m.get("chat_shared"):
        return await on_chat_shared(m)
    if text == PICKER_CANCEL:
        await send_rich(chat_id, "❌ Cancelled.", reply_markup=REMOVE_KB)
        return await show_channel(chat_id)
    if text in ("/menu", "/cancel"):
        await db.admins.update_one({"user_id": user["id"]}, {"$set": {"awaiting": None, "bc": None}})
        if text == "/cancel":
            await send(chat_id, "❌ Cancelled.")
        return await show_menu(chat_id)
    if admin.get("awaiting") in NEW_STATES:
        return await NEW_STATES[admin["awaiting"]](m, admin)
    if admin.get("awaiting"):
        return await on_admin_input(m, admin, text)
    await show_menu(chat_id)


async def _new_state(m, admin):
    from broadcast import on_bc_message
    from buttons import on_button_input
    from wlc import on_wlc_input
    kind = admin["awaiting"]
    from customtime import on_ct_input
    from recmedia import on_rm_input
    fn = (on_bc_message if kind == "bc_wait" else on_wlc_input if kind.startswith("wlc_")
          else on_ct_input if kind.startswith("ct_")
          else on_rm_input if kind.startswith(("rec_", "xtra_")) else on_button_input)
    return await fn(m, admin)


NEW_STATES = {k: _new_state for k in ("bc_wait", "wlc_text", "wlc_media", "btn_name", "btn_url", "btn_rename", "btn_relink",
                                      "ct_date", "ct_time", "rec_wait", "xtra_text", "xtra_media")}


async def handle_update(u: dict):
    if "update_id" in u:
        if not _seen_updates:
            for d in await db.processed_updates.find({}, {"_id": 1}).sort("created_at", -1).limit(5000).to_list(5000):
                _seen_updates[d["_id"]] = True
        if u["update_id"] in _seen_updates:
            return
        _seen_updates[u["update_id"]] = True
        if len(_seen_updates) > 5000:
            _seen_updates.popitem(last=False)
        persist = asyncio.create_task(db.processed_updates.insert_one({"_id": u["update_id"], "created_at": now()}))
        _bg.add(persist)
        persist.add_done_callback(_persist_done)
    from admin_panel import on_callback, on_my_chat_member
    from extras import on_chat_member
    if "message" in u:
        await on_message(u["message"])
    elif "callback_query" in u:
        await on_callback(u["callback_query"])
    elif "chat_join_request" in u:
        await on_join_request(u["chat_join_request"])
    elif "my_chat_member" in u:
        await on_my_chat_member(u["my_chat_member"])
    elif "chat_member" in u:
        await on_chat_member(u["chat_member"])
