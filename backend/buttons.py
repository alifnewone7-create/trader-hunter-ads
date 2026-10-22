from db import db
from extras import answer, set_state
from settings_store import get_settings
from telegram_api import BOT_INFO
from rich import (LAYOUTS, MAX_BUTTONS, STYLES, btn, build_rows, button_label, make_button, move_item,
                  normalize_url, panel, parse_button_name, send_rich)

KINDS = {"start": "Start Msg"}
DEFAULT_MSGS = {
    "start": ("<b>স্বাগতম!</b>\n\nনিচের বাটনে চাপ দিয়ে আমাদের টেলিগ্রাম চ্যানেলে <b>জয়েন রিকুয়েস্ট</b> পাঠান। "
              "রিকুয়েস্ট অনুমোদন হলেই আপনি চ্যানেলে যুক্ত হয়ে যাবেন।"),
}
PREMIUM_HINT = ("A ✨ Premium emoji anywhere in the name (start, middle or end) becomes the premium button icon on the "
                "<b>left</b> (Telegram shows premium icons only on the left).")


JOIN_TEXT = "Join Our Channel"


def is_join(b):
    return bool(b.get("join"))


async def get_msg(kind):
    doc = await db.msgs.find_one({"_id": kind}) or {}
    bs = doc.get("buttons", [])
    if kind == "start":
        if not any(is_join(b) for b in bs):
            bs.append({"join": True, "text": JOIN_TEXT, "icon": None, "alt": None, "style": "success"})
        link = (await get_settings())["invite_link"]
        for b in bs:
            if is_join(b):
                b["url"] = link or f"https://t.me/{BOT_INFO['username']}"
                b["linked"] = bool(link)
    return {"text": doc.get("text", DEFAULT_MSGS[kind]), "media": doc.get("media"),
            "buttons": bs, "layout": doc.get("layout", 1)}


async def load(target, uid):
    if target == "bc":
        return ((await db.admins.find_one({"user_id": uid})) or {}).get("bc")
    return await get_msg(target)


async def save(target, uid, cfg):
    if target == "bc":
        await db.admins.update_one({"user_id": uid}, {"$set": {"bc": cfg}})
    else:
        await db.msgs.update_one({"_id": target}, {"$set": cfg}, upsert=True)


def title(target):
    return "Broadcast" if target == "bc" else KINDS[target]


def list_view(target, cfg):
    bs, layout = cfg["buttons"], cfg.get("layout") or 1
    labels = [btn(f"{i}. {button_label(b)}", f"b:e:{target}:{i - 1}", "primary") for i, b in enumerate(bs, 1)]
    rows = [labels[i:i + layout] for i in range(0, len(labels), layout)]
    if bs:
        arrow = "↕️" if layout == 1 else "↔️"
        rows.append([btn(f"{arrow} Layout: {LAYOUTS[layout]} (tap to change)", f"b:l:{target}", "primary")])
    rows.append([btn("➕ Add Button", f"b:a:{target}", "success")])
    if target == "bc":
        head = f"🔘 <b>Broadcast Buttons</b> ({len(bs)}/{MAX_BUTTONS})\n\n"
        text = head + (f"📐 Layout: <b>{LAYOUTS[layout]}</b>\n\nTap a button to edit or delete it, change the layout, add a "
                       "new one, or tap ✅ Done." if bs else "Add buttons under the broadcast message, or skip to send it "
                       "without buttons.")
        rows += [[btn("✅ Done" if bs else "⏭ Skip", "bc:done", "primary")], [btn("❌ Cancel", "adm:cancel", "danger")]]
    else:
        text = (f"🔘 <b>{KINDS[target]} – Buttons</b> ({len(bs)}/{MAX_BUTTONS})\n\n📐 Layout: <b>{LAYOUTS[layout]}</b>\n\n"
                "Tap a button to edit or delete it, change the layout, or add a new one."
                + ("\n\n🔒 <b>Join Our Channel</b> is a default button – it always uses the channel join-request link "
                   "and can't be removed." if target == "start" else ""))
        rows.append([btn("⬅️ Back", f"cfg:{target}", "danger")])
    return text, rows


def button_view(target, i, b, total):
    name = "Broadcast Button" if target == "bc" else f"{KINDS[target]} – Button"
    link = (b["url"] if b.get("linked") else "❌ No channel added") + " (🔒 auto channel join-request link)" \
        if is_join(b) else b["url"]
    text = (f"🔘 <b>{name} #{i + 1}</b>{' 🔒 Default' if is_join(b) else ''}\n\nName: <b>{button_label(b)}</b>\nLink: {link}\n"
            f"Color: <b>{STYLES[b.get('style') or 'none']}</b>\nPremium icon: <b>{'Yes' if b.get('icon') else 'No'}</b>"
            "\n\n👆 This is how the button looks.")
    ref = f"{target}:{i}"
    if is_join(b):
        rows = [[make_button(b)], [btn("✏️ Edit Name", f"b:n:{ref}", "primary"), btn("🎨 Edit Color", f"b:c:{ref}", "success")]]
    else:
        rows = [[make_button(b)],
                [btn("✏️ Edit Name", f"b:n:{ref}", "primary"), btn("🔗 Edit Link", f"b:u:{ref}", "primary")],
                [btn("🎨 Edit Color", f"b:c:{ref}", "success"), btn("🗑 Delete", f"b:d:{ref}", "danger")]]
    move = ([btn("⬆️ Move Up", f"b:mu:{ref}", "primary")] if i > 0 else []) + \
           ([btn("⬇️ Move Down", f"b:md:{ref}", "primary")] if i < total - 1 else [])
    if move:
        rows.append(move)
    rows.append([btn("⬅️ Back", f"b:list:{target}", "danger")])
    return text, rows


def color_rows(target, i, mode):
    styles = list(STYLES)
    cells = [btn(STYLES[s], f"b:s:{target}:{i}:{s}:{mode}", None if s == "none" else s) for s in styles]
    return [cells[:2], cells[2:], [btn("⬅️ Back", f"b:e:{target}:{i}", "danger")]]


async def show_list(chat_id, target, cfg, mid=None):
    await panel(chat_id, *list_view(target, cfg), mid)


async def show_button(chat_id, target, cfg, i, mid=None):
    await panel(chat_id, *button_view(target, i, cfg["buttons"][i], len(cfg["buttons"])), mid)


async def on_button_cb(cq, data, chat_id, mid):
    uid = cq["from"]["id"]
    parts = data.split(":")
    act, target = parts[1], parts[2]
    cfg = await load(target, uid)
    if cfg is None:
        return await answer(cq, "⚠️ Broadcast session expired. Start again.", True)
    bs = cfg["buttons"]
    i = int(parts[3]) if len(parts) > 3 else None
    if i is not None and not 0 <= i < len(bs):
        return await answer(cq, "⚠️ Button not found", True)
    if act in ("u", "d") and is_join(bs[i]):
        return await answer(cq, "🔒 Default Join button: link can't be changed and it can't be removed", True)
    back_list = [[btn("⬅️ Back", f"b:list:{target}", "danger")]]
    back_btn = [[btn("⬅️ Back", f"b:e:{target}:{i}", "danger")]]
    if act == "list":
        await set_state(uid, None)
        await answer(cq)
        return await show_list(chat_id, target, cfg, mid)
    if act == "a":
        if len(bs) >= MAX_BUTTONS:
            return await answer(cq, f"⚠️ Max {MAX_BUTTONS} buttons", True)
        await set_state(uid, "btn_name", target=target)
        await answer(cq)
        head = "Broadcast Button" if target == "bc" else "New Button"
        return await panel(chat_id, f"➕ <b>{head} – Step 1/3</b>\n\nSend the button name.\n{PREMIUM_HINT}", back_list, mid)
    if act == "l":
        cfg["layout"] = 2 if (cfg.get("layout") or 1) == 1 else 1
        await save(target, uid, cfg)
        await answer(cq, f"📐 Layout: {LAYOUTS[cfg['layout']]}")
        return await show_list(chat_id, target, cfg, mid)
    if act == "e":
        await set_state(uid, None)
        await answer(cq)
        return await show_button(chat_id, target, cfg, i, mid)
    if act == "n":
        await set_state(uid, "btn_rename", target=target, i=i)
        await answer(cq)
        return await panel(chat_id, "✏️ Send the new button name. A ✨ Premium emoji anywhere in the name becomes the "
                           "button icon on the left.", back_btn, mid)
    if act == "u":
        await set_state(uid, "btn_relink", target=target, i=i)
        await answer(cq)
        return await panel(chat_id, "🔗 Send the new button link (https://... or t.me/...).", back_btn, mid)
    if act == "c":
        await answer(cq)
        return await panel(chat_id, "🎨 <b>Choose the button color</b>", color_rows(target, i, "e"), mid)
    if act == "s":
        style, mode = parts[4], parts[5]
        bs[i]["style"] = None if style == "none" else style
        await save(target, uid, cfg)
        await answer(cq, f"Color: {STYLES[style]}")
        if mode == "n" and target == "bc":
            return await show_list(chat_id, target, cfg, mid)
        return await show_button(chat_id, target, cfg, i, mid)
    if act == "d":
        bs.pop(i)
        await save(target, uid, cfg)
        await answer(cq, "🗑 Button deleted")
        return await show_list(chat_id, target, cfg, mid)
    if act in ("mu", "md"):
        j = move_item(bs, i, -1 if act == "mu" else 1)
        if j is None:
            return await answer(cq, "⚠️ Can't move", True)
        await save(target, uid, cfg)
        await answer(cq, f"✅ Moved to #{j + 1}")
        return await show_button(chat_id, target, cfg, j, mid)


async def on_button_input(m, admin):
    chat_id, uid, kind = m["chat"]["id"], admin["user_id"], admin["awaiting"]
    ctx = admin.get("ctx") or {}
    target = ctx.get("target")
    cfg = await load(target, uid)
    if cfg is None:
        await set_state(uid, None)
        return await send_rich(chat_id, "⚠️ Broadcast session expired. Start again.")
    if kind in ("btn_name", "btn_rename"):
        name, icon, alt = parse_button_name(m)
        if not name:
            return await send_rich(chat_id, "⚠️ Please send the button name as text.")
        if kind == "btn_rename":
            i = ctx["i"]
            if i >= len(cfg["buttons"]):
                return await set_state(uid, None)
            cfg["buttons"][i].update(text=name, icon=icon, alt=alt)
            await save(target, uid, cfg)
            await set_state(uid, None)
            return await show_button(chat_id, target, cfg, i)
        await set_state(uid, "btn_url", target=target, name=name, icon=icon, alt=alt)
        head = "Broadcast Button" if target == "bc" else "New Button"
        return await send_rich(chat_id, f"🔗 <b>{head} – Step 2/3</b>\n\nSend the button link (https://... or t.me/...).",
                               [[btn("⬅️ Back", f"b:list:{target}", "danger")]])
    url = normalize_url(m.get("text"))
    if not url:
        return await send_rich(chat_id, "⚠️ Invalid link. Example: <code>https://t.me/yourchannel</code>")
    if kind == "btn_relink":
        i = ctx["i"]
        if i >= len(cfg["buttons"]):
            return await set_state(uid, None)
        if is_join(cfg["buttons"][i]):
            await set_state(uid, None)
            return await send_rich(chat_id, "🔒 Default Join button link can't be changed.")
        cfg["buttons"][i]["url"] = url
        await save(target, uid, cfg)
        await set_state(uid, None)
        return await show_button(chat_id, target, cfg, i)
    if len(cfg["buttons"]) >= MAX_BUTTONS:
        await set_state(uid, None)
        return await send_rich(chat_id, f"⚠️ Max {MAX_BUTTONS} buttons")
    cfg["buttons"].append({"text": ctx["name"], "icon": ctx.get("icon"), "alt": ctx.get("alt"), "url": url, "style": None})
    await save(target, uid, cfg)
    await set_state(uid, None)
    i = len(cfg["buttons"]) - 1
    head = "Broadcast Button" if target == "bc" else "New Button"
    await send_rich(chat_id, f"🎨 <b>{head} – Step 3/3</b>\n\nChoose the button color:", color_rows(target, i, "n"))


def preview_rows(cfg):
    return build_rows(cfg["buttons"], True, cfg.get("layout") or 1)
