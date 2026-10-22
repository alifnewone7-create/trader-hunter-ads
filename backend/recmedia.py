from db import db
from extras import answer, set_state
from rich import MEDIA_TYPES, btn, deliver, html_of, panel, render
from telegram_api import tg

REC_ID = "start_rec"
XTRA_ID = "start_xtra"
SEQ_ID = "start_seq"
BLOCKS = {"rec": "📹 Record Video", "xtra": "🖼 Extra Media", "main": "🚀 Start Msg"}
DEFAULT_ORDER = ["rec", "xtra", "main"]
RM_BACK = [[btn("⬅️ Back", "rm:menu", "danger")]]


async def get_rec():
    return (await db.msgs.find_one({"_id": REC_ID}) or {}).get("media")


async def get_xtra():
    doc = await db.msgs.find_one({"_id": XTRA_ID}) or {}
    return {"text": doc.get("text"), "media": doc.get("media")}


def xtra_on(x):
    return bool(x["text"] or x["media"])


async def enabled_map():
    return {"main": True, "rec": bool(await get_rec()), "xtra": xtra_on(await get_xtra())}


async def get_order():
    doc = await db.msgs.find_one({"_id": SEQ_ID}) or {}
    order = [b for b in (doc.get("order") or []) if b in BLOCKS]
    return order + [b for b in DEFAULT_ORDER if b not in order]


# ---------- sending ----------

async def send_rec(chat_id, rec):
    if rec["type"] == "video_note":
        return await tg("sendVideoNote", chat_id=chat_id, video_note=rec["file_id"])
    return await tg("sendVideo", chat_id=chat_id, video=rec["file_id"])


async def send_xtra(chat_id, x, user):
    return await deliver(chat_id, {"text": x["text"], "media": x["media"], "buttons": [], "layout": 1}, user)


async def send_blocks(chat_id, user, send_main):
    order, en = await get_order(), await enabled_map()
    rec, xtra = await get_rec(), await get_xtra()
    sent = None
    for b in order:
        if not en[b]:
            continue
        if b == "main":
            sent = await send_main() or sent
        elif b == "rec":
            sent = await send_rec(chat_id, rec) or sent
        elif b == "xtra":
            sent = await send_xtra(chat_id, xtra, user) or sent
    return sent


# ---------- menu ----------

async def show_menu(chat_id, mid=None):
    rec, xtra = await get_rec(), await get_xtra()
    rstat = "✅ Set" if rec else "None"
    xstat = "✅ Set" if xtra_on(xtra) else "None"
    text = ("📹 <b>Record / Media</b>\n\n<i>Extra messages shown together with the start message when a user sends "
            "/start. Both are optional — remove them and they won't be sent. You can set the order below.</i>\n\n"
            f"📹 Record Video: <b>{rstat}</b>\n🖼 Extra Media: <b>{xstat}</b>")
    rows = [[btn("📹 Set Record Video", "rec:open", "primary")],
            [btn("🖼 Media", "xtra:open", "primary")],
            [btn("↕️ Set Order", "ord:open", "success")],
            [btn("⬅️ Back", "cfg:start", "danger")]]
    await panel(chat_id, text, rows, mid)


# ---------- record video ----------

async def show_rec(chat_id, mid=None):
    rec = await get_rec()
    cur = f"✅ {'Video Note' if rec['type'] == 'video_note' else 'Video'} set" if rec else "None"
    text = ("📹 <b>Set Record Video</b>\n\n<i>Record a video note (round video) right here in Telegram, or send a normal "
            "video. It is shown as its own message after /start.</i>\n\n"
            f"Current: <b>{cur}</b>\n\n👉 Record/send the video now.")
    rows = ([[btn("👁 Preview", "rec:prv", "primary"), btn("🗑 Remove", "rec:rm", "danger")]] if rec else []) + RM_BACK
    await panel(chat_id, text, rows, mid)


async def show_xtra(chat_id, mid=None):
    x = await get_xtra()
    media = MEDIA_TYPES[x["media"]["type"]] if x["media"] else "None"
    text = ("🖼 <b>Extra Media</b>\n\n<i>Like the start message — you can set media, text, or both. Shown as its own "
            "message after /start.</i>\n\n"
            f"📝 Text: <b>{'Set' if x['text'] else 'None'}</b>\n🖼 Media: <b>{media}</b>")
    rows = [[btn("📝 Set Text", "xtra:txt", "primary"), btn("🖼 Set Media", "xtra:med", "primary")]]
    clear = ([btn("🗑 Text", "xtra:rmtxt", "danger")] if x["text"] else []) + \
            ([btn("🗑 Media", "xtra:rmmed", "danger")] if x["media"] else [])
    if clear:
        rows.append(clear)
    rows += [[btn("👁 Preview", "xtra:prv", "primary")], [btn("⬅️ Back", "rm:menu", "danger")]]
    await panel(chat_id, text, rows, mid)


async def show_order(chat_id, mid=None):
    order, en = await get_order(), await enabled_map()
    seq = [b for b in order if en[b]]
    lines = "\n".join(f"{i + 1}. {BLOCKS[b]}" for i, b in enumerate(seq))
    text = ("↕️ <b>Set Order</b>\n\n<i>The messages sent after /start, in order from top to bottom.</i>\n\n" + lines +
            "\n\nUse ⬆️ / ⬇️ to change the order.")
    rows = []
    for i, b in enumerate(seq):
        row = [btn(BLOCKS[b], "ord:nop", None)]
        row.append(btn("⬆️", f"ord:u:{b}", "primary") if i > 0 else btn("·", "ord:nop", None))
        row.append(btn("⬇️", f"ord:d:{b}", "primary") if i < len(seq) - 1 else btn("·", "ord:nop", None))
        rows.append(row)
    rows.append([btn("⬅️ Back", "rm:menu", "danger")])
    await panel(chat_id, text, rows, mid)


async def move(b, step):
    order, en = await get_order(), await enabled_map()
    seq = [x for x in order if en[x]]
    if b not in seq:
        return
    i = seq.index(b)
    j = i + step
    if 0 <= j < len(seq):
        seq[i], seq[j] = seq[j], seq[i]
    new = seq + [x for x in order if not en[x]]
    await db.msgs.update_one({"_id": SEQ_ID}, {"$set": {"order": new}}, upsert=True)


# ---------- callbacks ----------

async def on_rm_cb(cq, data, chat_id, mid):
    uid = cq["from"]["id"]
    parts = data.split(":")
    head = parts[0]
    if data == "rm:menu":
        await set_state(uid, None)
        await answer(cq)
        return await show_menu(chat_id, mid)
    if head == "rec":
        if parts[1] == "open":
            await set_state(uid, "rec_wait")
            await answer(cq)
            return await show_rec(chat_id, mid)
        if parts[1] == "rm":
            await db.msgs.update_one({"_id": REC_ID}, {"$set": {"media": None}}, upsert=True)
            await set_state(uid, "rec_wait")
            await answer(cq, "🗑 Removed")
            return await show_rec(chat_id, mid)
        if parts[1] == "prv":
            rec = await get_rec()
            if rec:
                await send_rec(chat_id, rec)
            return await answer(cq, "👁 Preview sent" if rec else "⚠️ Nothing set")
    if head == "xtra":
        if parts[1] == "open":
            await set_state(uid, None)
            await answer(cq)
            return await show_xtra(chat_id, mid)
        if parts[1] == "txt":
            await set_state(uid, "xtra_text")
            await answer(cq)
            return await panel(chat_id, "📝 <b>Extra Media – Set Text</b>\n\nSend the text. All Telegram formatting and "
                               "✨ Premium emoji are supported.", [[btn("⬅️ Back", "xtra:open", "danger")]], mid)
        if parts[1] == "med":
            await set_state(uid, "xtra_media")
            await answer(cq)
            return await panel(chat_id, "🖼 <b>Extra Media – Set Media</b>\n\nSend a photo, video, audio, GIF, voice or "
                               "document. A caption becomes the text.", [[btn("⬅️ Back", "xtra:open", "danger")]], mid)
        if parts[1] == "rmtxt":
            await db.msgs.update_one({"_id": XTRA_ID}, {"$set": {"text": None}}, upsert=True)
            await answer(cq, "🗑 Text removed")
            return await show_xtra(chat_id, mid)
        if parts[1] == "rmmed":
            await db.msgs.update_one({"_id": XTRA_ID}, {"$set": {"media": None}}, upsert=True)
            await answer(cq, "🗑 Media removed")
            return await show_xtra(chat_id, mid)
        if parts[1] == "prv":
            x = await get_xtra()
            if xtra_on(x):
                await send_xtra(chat_id, x, cq["from"])
            return await answer(cq, "👁 Preview sent" if xtra_on(x) else "⚠️ Nothing set")
    if head == "ord":
        if parts[1] == "nop":
            return await answer(cq)
        if parts[1] == "open":
            await set_state(uid, None)
            await answer(cq)
            return await show_order(chat_id, mid)
        await move(parts[2], -1 if parts[1] == "u" else 1)
        await answer(cq, "✅ Moved")
        return await show_order(chat_id, mid)


async def on_rm_input(m, admin):
    from rich import extract_media, send_rich
    chat_id, uid, kind = m["chat"]["id"], admin["user_id"], admin["awaiting"]
    if kind == "rec_wait":
        vn = m.get("video_note")
        media = {"type": "video_note", "file_id": vn["file_id"]} if vn else \
            ({"type": "video", "file_id": m["video"]["file_id"]} if m.get("video") else None)
        if not media:
            return await send_rich(chat_id, "⚠️ Please record a video note or send a video.")
        await db.msgs.update_one({"_id": REC_ID}, {"$set": {"media": media}}, upsert=True)
        await set_state(uid, None)
        await send_rich(chat_id, "✅ Record video saved!")
        return await show_rec(chat_id)
    if kind == "xtra_text":
        if m.get("text") is None:
            return await send_rich(chat_id, "⚠️ Please send text. For media use 🖼 Set Media.")
        await db.msgs.update_one({"_id": XTRA_ID}, {"$set": {"text": html_of(m)}}, upsert=True)
        await send_rich(chat_id, "✅ Text saved!")
    else:
        media = extract_media(m)
        if not media:
            return await send_rich(chat_id, "⚠️ Please send a photo, video, audio, GIF, voice or document.")
        upd = {"media": media}
        if m.get("caption"):
            upd["text"] = html_of(m)
        await db.msgs.update_one({"_id": XTRA_ID}, {"$set": upd}, upsert=True)
        await send_rich(chat_id, f"✅ {MEDIA_TYPES[media['type']]} saved!")
    await set_state(uid, None)
    await show_xtra(chat_id)
