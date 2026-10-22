from buttons import KINDS, get_msg, is_join
from db import db
from extras import HOME, answer, set_state
from rich import LAYOUTS, MEDIA_TYPES, btn, count_tg_emoji, deliver, extract_media, html_of, panel, render, send_rich
from settings_store import get_settings, update_settings

DESC = {"start": "Sent when a user sends /start to the bot."}
VARS_HELP = "<code>{first_name}</code>  <code>{username}</code>"


async def show_wlc(chat_id, mid=None):
    on = (await get_settings())["notify"]
    text = ("👋 <b>Wlc Setting</b>\n\nChoose which message you want to customize 👇\n\n"
            f"🔔 Notification: <b>{'ON' if on else 'OFF'}</b>\n<i>ON: admins get both the <b>New User</b> and the "
            "<b>নতুন জয়েন রিকুয়েস্ট</b> notification. OFF: both are turned off.</i>")
    rows = [[btn("🚀 Start Msg", "cfg:start", "primary")],
            [btn("🔔 Notification: ON", "wlc:notify", "success") if on else btn("🔕 Notification: OFF", "wlc:notify", "danger")],
            HOME]
    await panel(chat_id, text, rows, mid)


def summary(kind, cfg):
    media = MEDIA_TYPES[cfg["media"]["type"]] if cfg.get("media") else "None"
    extra = "\n🔒 Default button: <b>Join Our Channel</b> (channel join-request link)" if kind == "start" else ""
    return (f"⚙️ <b>{KINDS[kind]}</b>\n<i>{DESC[kind]}</i>\n\n📝 Text: <b>{'Set' if cfg.get('text') else 'None'}</b>\n"
            f"🖼 Media: <b>{media}</b>\n🔘 Buttons: <b>{len(cfg['buttons'])}</b>  📐 Layout: "
            f"<b>{LAYOUTS[cfg.get('layout') or 1]}</b>\n✨ Premium emoji: <b>{count_tg_emoji(cfg.get('text'))}</b>{extra}")


def kind_rows(kind):
    rows = [[btn("📝 Set Text", f"txt:{kind}", "primary"), btn("🖼 Set Media", f"med:{kind}", "primary")],
            [btn("🔘 Set Button", f"b:list:{kind}", "success")]]
    if kind == "start":
        rows.append([btn("📹 Set Record / Media", "rm:menu", "success")])
    return rows + [[btn("👁 Preview", f"prv:{kind}", "primary")], [btn("⬅️ Back", "adm:wlc", "danger")]]


async def show_kind(chat_id, kind, mid=None):
    await panel(chat_id, summary(kind, await get_msg(kind)), kind_rows(kind), mid)


async def send_kind(chat_id, kind, user):
    cfg = await get_msg(kind)
    cfg["buttons"] = [b for b in cfg["buttons"] if not is_join(b) or b.get("linked")]
    if not (cfg["text"] or cfg["media"] or cfg["buttons"]):
        return None
    return await deliver(chat_id, cfg, user)


async def send_start(chat_id, user):
    from recmedia import send_blocks
    return await send_blocks(chat_id, user, lambda: send_kind(chat_id, "start", user))


async def on_wlc_cb(cq, data, chat_id, mid):
    uid = cq["from"]["id"]
    head, _, kind = data.partition(":")
    if data == "adm:wlc":
        await set_state(uid, None)
        await answer(cq)
        return await show_wlc(chat_id, mid)
    if data == "wlc:notify":
        on = not (await get_settings())["notify"]
        await update_settings(notify=on)
        await answer(cq, "🔔 Notification ON" if on else "🔕 Notification OFF")
        return await show_wlc(chat_id, mid)
    if kind not in KINDS:
        return await answer(cq)
    cfg = await get_msg(kind)
    back = [[btn("⬅️ Back", f"cfg:{kind}", "danger")]]
    if head == "cfg":
        await set_state(uid, None)
        await answer(cq)
        return await show_kind(chat_id, kind, mid)
    if head == "txt":
        await set_state(uid, "wlc_text", kind=kind)
        await answer(cq)
        return await panel(chat_id, f"📝 <b>{KINDS[kind]} – Set Text</b>\n\nCurrent text:\n━━━━━━━━━━━━\n"
                           f"{render(cfg['text'], cq['from']) or '—'}\n━━━━━━━━━━━━\n\nSend the new text. All Telegram "
                           f"formatting and ✨ Premium emoji are supported.\nVariables: {VARS_HELP}", back, mid)
    if head == "med":
        await set_state(uid, "wlc_media", kind=kind)
        await answer(cq)
        media = MEDIA_TYPES[cfg["media"]["type"]] if cfg.get("media") else "None"
        rows = ([[btn("🗑 Remove Media", f"medr:{kind}", "danger")]] if cfg.get("media") else []) + back
        return await panel(chat_id, f"🖼 <b>{KINDS[kind]} – Set Media</b>\n\nCurrent media: <b>{media}</b>\n\nSend a photo, "
                           "video, audio, GIF, voice or document.\nThe message text is shown as the media caption. If you "
                           "send the media with a caption, that caption becomes the new text.", rows, mid)
    if head == "medr":
        await db.msgs.update_one({"_id": kind}, {"$set": {"media": None}}, upsert=True)
        await set_state(uid, None)
        await answer(cq, "🗑 Media removed")
        return await show_kind(chat_id, kind, mid)
    if head == "prv":
        r = await (send_start(chat_id, cq["from"]) if kind == "start" else send_kind(chat_id, kind, cq["from"]))
        return await answer(cq, "👁 Preview sent" if r else "⚠️ Message is empty — nothing will be sent")


async def on_wlc_input(m, admin):
    chat_id, uid = m["chat"]["id"], admin["user_id"]
    kind = (admin.get("ctx") or {}).get("kind")
    if kind not in KINDS:
        return await set_state(uid, None)
    if admin["awaiting"] == "wlc_text":
        if m.get("text") is None:
            return await send_rich(chat_id, "⚠️ Please send text. To set media use 🖼 Set Media.")
        await db.msgs.update_one({"_id": kind}, {"$set": {"text": html_of(m)}}, upsert=True)
        await send_rich(chat_id, "✅ Text saved!")
    else:
        media = extract_media(m)
        if not media:
            return await send_rich(chat_id, "⚠️ Please send a photo, video, audio, GIF, voice or document.")
        upd = {"media": media}
        if m.get("caption"):
            upd["text"] = html_of(m)
        await db.msgs.update_one({"_id": kind}, {"$set": upd}, upsert=True)
        await send_rich(chat_id, f"✅ {MEDIA_TYPES[media['type']]} saved!")
    await set_state(uid, None)
    await panel(chat_id, summary(kind, await get_msg(kind)), kind_rows(kind))
