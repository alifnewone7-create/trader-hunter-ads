import re
from datetime import datetime, timedelta

from bot import BD, esc, fmt, name_of, now, send, show
from db import db
from meta_capi import verify_token
from settings_store import get_settings, update_settings
from telegram_api import BOT_ID, tg

STATUS = {"sent": "✅ Subscribe গেছে", "failed": "⚠️ পাঠাতে ব্যর্থ", "unmatched": "➖ Unmatched (ad ডেটা নেই)",
          "none": "— এখনো রিকুয়েস্ট দেয়নি", "sending": "⏳ পাঠানো হচ্ছে"}
BACK = [{"text": "⬅️ Back", "callback_data": "m:home", "style": "danger"}]


async def on_admin_login(m, user, text):
    from extras import ADMIN_IDS
    chat_id, uid = m["chat"]["id"], user["id"]
    if uid in ADMIN_IDS:
        await db.admins.update_one({"user_id": uid}, {"$set": {"chat_id": chat_id, "name": name_of(user), "awaiting": None}})
        await show_menu(chat_id)


async def show_menu(chat_id, message_id=None):
    s = await get_settings()
    pending = await db.join_requests.count_documents({"status": "pending"})
    ch = esc(s["channel_title"]) if s["channel_id"] else "❌ সেট করা নেই"
    tok = "✅" if s["capi_token"] else "❌ নেই"
    mode = f"🧪 Test ({esc(s['test_event_code'])})" if s["test_event_code"] else "🟢 Live"
    text = (f"<b>অ্যাডমিন প্যানেল</b>\n\nচ্যানেল: {ch}\nPixel: <code>{esc(s['pixel_id']) or '—'}</code>\n"
            f"Access Token: {tok}\nইভেন্ট মোড: {mode}\nPending রিকুয়েস্ট: {pending}")
    kb = [[{"text": "📊 Stats", "callback_data": "m:stats", "style": "primary"},
           {"text": "📈 Statistics", "callback_data": "adm:stats", "style": "success"}],
          [{"text": "👋 Wlc Setting", "callback_data": "adm:wlc", "style": "success"},
           {"text": "📢 Broadcast", "callback_data": "adm:bc", "style": "primary"}],
          [{"text": "⚙️ Settings", "callback_data": "m:settings", "style": "danger"}]]
    await show(chat_id, text, kb, message_id)


async def count_range(start):
    t = {"$gte": start} if start else {"$exists": True, "$ne": None}
    return [
        await db.pageviews.count_documents({"created_at": t}),
        await db.start_tokens.count_documents({"created_at": t}),
        await db.leads.count_documents({"started_at": t}),
        await db.join_requests.count_documents({"created_at": t}),
        await db.leads.count_documents({"subscribe_status": "sent", "subscribe_at": t}),
        await db.leads.count_documents({"subscribe_status": "failed", "subscribe_at": t}),
        await db.leads.count_documents({"subscribe_status": "unmatched", "subscribe_at": t}),
        await db.unrequested.count_documents({"started_at": t}),
    ]


async def show_stats(chat_id, message_id):
    local_now = now().astimezone(BD)
    today = datetime(local_now.year, local_now.month, local_now.day, tzinfo=BD)
    rows = [await count_range(today), await count_range(today - timedelta(days=6)),
            await count_range(today - timedelta(days=29)), await count_range(None)]
    labels = ["🌐 পেজ ভিজিট", "👆 বাটন ক্লিক", "🤖 বট Start", "📨 জয়েন রিকুয়েস্ট",
              "✅ Subscribe গেছে", "⚠️ Failed", "➖ Unmatched", "📝 Unrequested"]
    lines = [f"<b>{lb}</b>\n├ আজ : <b>{rows[0][i]}</b>\n├ ৭ দিন : <b>{rows[1][i]}</b>\n"
             f"├ ৩০ দিন : <b>{rows[2][i]}</b>\n└ মোট : <b>{rows[3][i]}</b>" for i, lb in enumerate(labels)]
    updated = local_now.strftime("%d %b %Y, %I:%M %p")
    text = ("<b>📊 পরিসংখ্যান</b>\n<i>বাংলাদেশ সময় অনুযায়ী</i>\n\n" + "\n\n".join(lines) +
            f"\n\n🕒 আপডেট : <code>{updated}</code>")
    await show(chat_id, text, [[{"text": "🔄 Refresh", "callback_data": "m:stats", "style": "primary"},
                                {"text": "🕒 Custom Time", "callback_data": "ct:open", "style": "success"}], BACK], message_id)


async def show_recent(chat_id, message_id):
    leads = await db.leads.find({}, {"_id": 0}).sort("updated_at", -1).limit(10).to_list(10)
    if not leads:
        text = "<b>🕑 Recent</b>\n\nএখনো কেউ আসেনি।"
    else:
        items = []
        for i, ld in enumerate(leads, 1):
            src = "Ad link" if ld.get("visitor_id") else "সরাসরি"
            err = f"\n   কারণ: {esc(ld.get('subscribe_error'))}" if ld.get("subscribe_status") == "failed" else ""
            items.append(f"{i}. <b>{esc(name_of(ld))}</b> · {src}\n   Start: {fmt(ld.get('last_start_at'))}"
                         f" · Request: {fmt(ld.get('join_requested_at'))}\n   "
                         f"{STATUS.get(ld.get('subscribe_status'), '—')}{err}")
        text = "<b>🕑 শেষ ১০ জন</b>\n\n" + "\n\n".join(items)
    await show(chat_id, text, [[{"text": "🔄 Refresh", "callback_data": "m:recent", "style": "primary"}], BACK], message_id)


async def show_pending(chat_id, message_id):
    reqs = await db.join_requests.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    total = await db.join_requests.count_documents({"status": "pending"})
    kb = []
    if not reqs:
        text = "<b>⏳ Pending requests</b>\n\nকোনো pending রিকুয়েস্ট নেই।"
    else:
        text = f"<b>⏳ Pending requests</b> (মোট {total}, শেষ ১০টি)\n\n" + "\n".join(
            f"{i}. {esc(r['name'])} · {fmt(r.get('created_at'))}" for i, r in enumerate(reqs, 1))
        for i, r in enumerate(reqs, 1):
            key = f"{r['chat_id']}:{r['telegram_user_id']}"
            kb.append([{"text": f"✅ {i}. Approve", "callback_data": f"jr:a:{key}:p", "style": "success"},
                       {"text": f"❌ {i}. Decline", "callback_data": f"jr:d:{key}:p", "style": "danger"}])
    kb += [[{"text": "🔄 Refresh", "callback_data": "m:pending", "style": "primary"}], BACK]
    await show(chat_id, text, kb, message_id)


async def decide(chat_id: int, user_id: int, approve: bool):
    method = "approveChatJoinRequest" if approve else "declineChatJoinRequest"
    r = await tg(method, chat_id=chat_id, user_id=user_id)
    gone = "HIDE_REQUESTER_MISSING" in r.get("description", "") or "USER_ALREADY_PARTICIPANT" in r.get("description", "")
    if r.get("ok") or gone:
        await db.join_requests.update_many({"chat_id": chat_id, "telegram_user_id": user_id, "status": "pending"},
                                           {"$set": {"status": "approved" if approve else "declined",
                                                     "decided_at": now()}})
        return True, "আগেই হ্যান্ডেল করা হয়েছে" if gone else ("Approve হয়েছে" if approve else "Decline হয়েছে")
    return False, r.get("description", "ব্যর্থ")


async def show_settings(chat_id, message_id=None):
    s = await get_settings()
    tok = f"✅ সেট আছে (…{esc(s['capi_token'][-4:])})" if s["capi_token"] else "❌ সেট করা নেই"
    ch = f"{esc(s['channel_title'])} (<code>{s['channel_id']}</code>)" if s["channel_id"] else "❌ সেট করা নেই"
    text = (f"<b>⚙️ Settings</b>\n\nচ্যানেল: {ch}\nJoin-request link: {esc(s['invite_link']) or '—'}\n"
            f"Pixel ID: <code>{esc(s['pixel_id']) or '—'}</code>\nAccess Token: {tok}\n"
            f"Test Event Code: {esc(s['test_event_code']) or 'নেই (Live মোড)'}\n"
            f"Auto Approve: <b>{'✅ ON' if s['auto_approve'] else '❌ OFF'}</b>")
    auto = ({"text": "✅ Auto Approve: ON", "callback_data": "s:auto", "style": "success"} if s["auto_approve"]
            else {"text": "❌ Auto Approve: OFF", "callback_data": "s:auto", "style": "danger"})
    kb = [[{"text": "📡 Channel", "callback_data": "adm:channels", "style": "primary"}], [auto],
          [{"text": "🎯 Pixel ID", "callback_data": "s:pixel", "style": "success"},
           {"text": "🔑 Access Token", "callback_data": "s:token", "style": "success"}],
          [{"text": "🧪 Set Test Code", "callback_data": "s:test", "style": "primary"},
           {"text": "🗑 Clear Test Code", "callback_data": "s:testclear", "style": "danger"}],
          BACK]
    await show(chat_id, text, kb, message_id)


PROMPTS = {
    "channel": ("চ্যানেলের <b>@username</b> বা <b>ID</b> (যেমন -1001234567890) পাঠান, অথবা চ্যানেলের যেকোনো পোস্ট এখানে "
                "<b>forward</b> করুন।\n\nআগে বটকে চ্যানেলে Admin বানান, <b>Invite users via link</b> পারমিশন সহ।"),
    "pixel": "Meta Pixel / Dataset ID পাঠান (শুধু সংখ্যা)।",
    "token": "Conversions API Access Token পাঠান। (নিরাপত্তার জন্য মেসেজটি সাথে সাথে মুছে দেওয়া হবে)",
    "test": "Meta Events Manager → Test Events থেকে Test Event Code পাঠান (যেমন TEST12345)।",
}


async def set_channel(ref):
    r = await tg("getChat", chat_id=ref)
    if not r.get("ok"):
        return False, "চ্যানেল পাওয়া যায়নি। বটকে আগে চ্যানেলে Admin বানান, তারপর আবার চেষ্টা করুন।"
    chat = r["result"]
    if chat.get("type") not in ("channel", "supergroup"):
        return False, "এটি কোনো চ্যানেল নয়।"
    mem = await tg("getChatMember", chat_id=chat["id"], user_id=BOT_ID)
    res = mem.get("result", {})
    if res.get("status") != "administrator" or not res.get("can_invite_users"):
        return False, "বট এই চ্যানেলের Admin নয় বা <b>Invite users via link</b> পারমিশন নেই।"
    link = await tg("createChatInviteLink", chat_id=chat["id"], name="Meta Ads", creates_join_request=True)
    if not link.get("ok"):
        return False, f"Invite link বানানো যায়নি: {esc(link.get('description'))}"
    await update_settings(channel_id=chat["id"], channel_title=chat.get("title"),
                          invite_link=link["result"]["invite_link"])
    return True, f"✅ চ্যানেল সেট হয়েছে: <b>{esc(chat.get('title'))}</b>"


def channel_ref(m, text):
    fo = m.get("forward_origin") or {}
    if fo.get("type") == "channel":
        return fo["chat"]["id"]
    if m.get("forward_from_chat"):
        return m["forward_from_chat"]["id"]
    t = re.sub(r"^(https?://)?t\.me/", "@", text.strip())
    return int(t) if re.fullmatch(r"-?\d+", t) else (t if t.startswith("@") else f"@{t}")


async def on_admin_input(m, admin, text):
    chat_id, kind = m["chat"]["id"], admin["awaiting"]
    done = True
    if kind == "channel":
        done, msg = await set_channel(channel_ref(m, text))
    elif kind == "pixel":
        done = bool(re.fullmatch(r"\d{10,20}", text))
        msg = "✅ Pixel ID সেভ হয়েছে।" if done else "সঠিক Pixel ID দিন (১০-২০ ডিজিট)।"
        if done:
            await update_settings(pixel_id=text)
    elif kind == "token":
        await tg("deleteMessage", chat_id=chat_id, message_id=m["message_id"])
        done = len(text) > 40 and " " not in text
        msg = "এটি সঠিক Access Token মনে হচ্ছে না।"
        if done:
            await update_settings(capi_token=text)
            ok, info = await verify_token((await get_settings())["pixel_id"], text)
            msg = f"✅ Token সেভ ও যাচাই হয়েছে ({esc(info)})" if ok else f"⚠️ Token সেভ হয়েছে, কিন্তু যাচাই ব্যর্থ: {esc(info)}"
    else:
        done = bool(re.fullmatch(r"[A-Za-z0-9_-]{3,40}", text))
        msg = "✅ Test Event Code সেভ হয়েছে। এখন ইভেন্টগুলো Test Events এ দেখা যাবে।" if done else "সঠিক কোড দিন।"
        if done:
            await update_settings(test_event_code=text)
    if not done:
        return await send(chat_id, msg + "\n\nআবার চেষ্টা করুন অথবা /cancel লিখুন।")
    await db.admins.update_one({"user_id": admin["user_id"]}, {"$set": {"awaiting": None}})
    await send(chat_id, msg)
    await show_settings(chat_id)


async def on_callback(cq):
    data, uid = cq.get("data", ""), cq["from"]["id"]
    msg = cq.get("message") or {}
    chat_id, mid = msg.get("chat", {}).get("id"), msg.get("message_id")
    from extras import ADMIN_IDS, ensure_admin
    if uid not in ADMIN_IDS:
        return await tg("answerCallbackQuery", callback_query_id=cq["id"])
    await ensure_admin(uid)
    if data.startswith("jr:"):
        _, act, ch, user_id, src = data.split(":")
        ok, info = await decide(int(ch), int(user_id), act == "a")
        await tg("answerCallbackQuery", callback_query_id=cq["id"], text=info, show_alert=not ok)
        if src == "p":
            return await show_pending(chat_id, mid)
        return await tg("editMessageText", chat_id=chat_id, message_id=mid, parse_mode="HTML",
                        text=f"{msg.get('text', '')}\n\n➡️ {info}")
    if await route_new(cq, data, chat_id, mid):
        return
    await tg("answerCallbackQuery", callback_query_id=cq["id"])
    if data == "m:home":
        await db.admins.update_one({"user_id": uid}, {"$set": {"awaiting": None}})
        return await show_menu(chat_id, mid)
    views = {"m:stats": show_stats, "m:recent": show_recent, "m:pending": show_pending, "m:settings": show_settings}
    if data in views:
        return await views[data](chat_id, mid)
    if data.startswith("s:use:"):
        ok, info = await set_channel(int(data.split(":")[2]))
        await send(chat_id, info)
        return await show_settings(chat_id)
    if data == "s:auto":
        await update_settings(auto_approve=not (await get_settings())["auto_approve"])
        return await show_settings(chat_id, mid)
    if data == "s:testclear":
        await update_settings(test_event_code="")
        return await show_settings(chat_id, mid)
    kind = data.split(":")[1] if data.startswith("s:") else None
    if kind in PROMPTS:
        await db.admins.update_one({"user_id": uid}, {"$set": {"awaiting": kind}})
        await show(chat_id, PROMPTS[kind], [[{"text": "❌ Cancel", "callback_data": "m:settings", "style": "danger"}]], mid)


async def route_new(cq, data, chat_id, mid):
    from broadcast import on_bc_cb
    from buttons import on_button_cb
    from extras import on_channel_cb, on_stats_cb, set_state, show_channel
    from wlc import on_wlc_cb
    uid = cq["from"]["id"]
    if data == "adm:cancel":
        await db.admins.update_one({"user_id": uid}, {"$set": {"awaiting": None, "bc": None}})
        await tg("answerCallbackQuery", callback_query_id=cq["id"], text="❌ Cancelled")
        await show_menu(chat_id, mid)
    elif data == "adm:channels":
        await set_state(uid, None)
        await tg("answerCallbackQuery", callback_query_id=cq["id"])
        await show_channel(chat_id, mid)
    elif data.startswith("ch:"):
        await on_channel_cb(cq, data, chat_id, mid)
    elif data.split(":")[0] in ("rm", "rec", "xtra", "ord"):
        from recmedia import on_rm_cb
        await on_rm_cb(cq, data, chat_id, mid)
    elif data.startswith("ct:"):
        from customtime import on_ct_cb
        await on_ct_cb(cq, data, chat_id, mid)
    elif data in ("adm:stats", "adm:apall", "adm:apgo"):
        await on_stats_cb(cq, data, chat_id, mid)
    elif data == "adm:bc" or data.startswith("bc:"):
        await on_bc_cb(cq, data, chat_id, mid)
    elif data.startswith("b:"):
        await on_button_cb(cq, data, chat_id, mid)
    elif data in ("adm:wlc", "wlc:notify") or data.split(":")[0] in ("cfg", "txt", "med", "medr", "prv"):
        await on_wlc_cb(cq, data, chat_id, mid)
    else:
        return False
    return True


AUTO_NOTE = {"approved": "✅ Auto approved", "gone": "🚫 Request not found", "failed": "⚠️ Auto approve failed"}


async def notify_join_request(chat_id, user, result, auto=None):
    if not (await get_settings())["notify"]:
        return
    note = STATUS.get(result["status"], result["status"])
    if result.get("note"):
        note += f" ({result['note']})"
    if result.get("test"):
        note += " [Test]"
    if result.get("error"):
        note += f"\nকারণ: {esc(result['error'])}"
    text = f"📨 <b>নতুন জয়েন রিকুয়েস্ট</b>\n{esc(name_of(user))}\nMeta ইভেন্ট: {note}"
    if auto:
        text += f"\n{AUTO_NOTE[auto]}"
    key = f"{chat_id}:{user['id']}"
    kb = None if auto in ("approved", "gone") else [[{"text": "✅ Approve", "callback_data": f"jr:a:{key}:n", "style": "success"},
           {"text": "❌ Decline", "callback_data": f"jr:d:{key}:n", "style": "danger"}]]
    for a in await db.admins.find({}, {"chat_id": 1}).to_list(50):
        await send(a["chat_id"], text, kb)


async def on_my_chat_member(upd):
    chat, new = upd.get("chat", {}), upd.get("new_chat_member", {})
    s = await get_settings()
    if chat.get("id") == s["channel_id"] and new.get("status") in ("left", "kicked"):
        return await update_settings(channel_id=None, channel_title=None, invite_link=None)
    if chat.get("type") != "channel" or new.get("status") != "administrator":
        return
    if s["channel_id"] == chat["id"]:
        return
    text = f"📢 বটকে <b>{esc(chat.get('title'))}</b> চ্যানেলে Admin বানানো হয়েছে। এই চ্যানেলটি ব্যবহার করবেন?"
    kb = [[{"text": "✅ এই চ্যানেল ব্যবহার করুন", "callback_data": f"s:use:{chat['id']}", "style": "success"}]]
    for a in await db.admins.find({}, {"chat_id": 1}).to_list(50):
        await send(a["chat_id"], text, kb)
