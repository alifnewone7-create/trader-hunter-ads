import html
import re
from collections import defaultdict

from telegram_api import tg

TG_EMOJI = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', re.DOTALL)
TAGS = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"^(https?|tg)://\S+$")
VARS = {k: re.compile(r"\{((?:<[^>]+>)*)" + k + r"((?:<[^>]+>)*)\}") for k in ("first_name", "username")}
CAPTION_LIMIT = 1024
MAX_BUTTONS = 20
MEDIA_TYPES = {"photo": "Photo", "video": "Video", "audio": "Audio", "animation": "GIF",
               "document": "Document", "voice": "Voice"}
STYLES = {"none": "⚪ Default", "primary": "🔵 Blue", "success": "🟢 Green", "danger": "🔴 Red"}
LAYOUTS = {1: "1 per line", 2: "2 per line"}
SIMPLE = {"bold": "b", "italic": "i", "underline": "u", "strikethrough": "s", "spoiler": "tg-spoiler", "code": "code"}


def _tags(e):
    t = e["type"]
    if t in SIMPLE:
        return f"<{SIMPLE[t]}>", f"</{SIMPLE[t]}>"
    if t == "pre":
        lang = e.get("language")
        return (f'<pre><code class="language-{html.escape(lang)}">', "</code></pre>") if lang else ("<pre>", "</pre>")
    if t == "text_link":
        return f'<a href="{html.escape(e["url"])}">', "</a>"
    if t == "text_mention":
        return f'<a href="tg://user?id={e["user"]["id"]}">', "</a>"
    if t == "custom_emoji":
        return f'<tg-emoji emoji-id="{e["custom_emoji_id"]}">', "</tg-emoji>"
    if t == "blockquote":
        return "<blockquote>", "</blockquote>"
    if t == "expandable_blockquote":
        return "<blockquote expandable>", "</blockquote>"
    return None


def to_html(text, entities):
    if not text:
        return ""
    b = text.encode("utf-16-le")
    n = len(b) // 2
    opens, closes = defaultdict(list), defaultdict(list)
    for e in sorted(entities or [], key=lambda e: (e["offset"], -e["length"])):
        tg_ = _tags(e)
        if not tg_:
            continue
        opens[e["offset"]].append(tg_[0])
        closes[e["offset"] + e["length"]].insert(0, tg_[1])
    points = sorted({0, n, *opens, *closes})
    out = []
    for i, p in enumerate(points):
        out += closes.get(p, []) + opens.get(p, [])
        if i + 1 < len(points):
            out.append(html.escape(b[p * 2:points[i + 1] * 2].decode("utf-16-le"), quote=False))
    return "".join(out)


def html_of(m):
    if m.get("text") is not None:
        return to_html(m["text"], m.get("entities"))
    return to_html(m.get("caption") or "", m.get("caption_entities"))


def count_custom_emoji(m):
    return sum(1 for e in (m.get("entities") or []) + (m.get("caption_entities") or []) if e["type"] == "custom_emoji")


def count_tg_emoji(h):
    return len(TG_EMOJI.findall(h or ""))


def strip_tg_emoji(h):
    return TG_EMOJI.sub(r"\1", h or "")


def plain_len(h):
    return len(html.unescape(TAGS.sub("", h or "")))


def render(template, user):
    first = html.escape(user.get("first_name") or "")
    uname = html.escape(f"@{user['username']}" if user.get("username") else first)
    out = VARS["first_name"].sub(lambda m: m.group(1) + first + m.group(2), template or "")
    return VARS["username"].sub(lambda m: m.group(1) + uname + m.group(2), out)


def normalize_url(raw):
    s = (raw or "").strip()
    if re.match(r"^t\.me/\S+$", s, re.I):
        s = "https://" + s
    if URL_RE.match(s) and len(s) > len(s.split("://")[0]) + 4:
        return s
    return None


def extract_media(m):
    if m.get("photo"):
        return {"type": "photo", "file_id": m["photo"][-1]["file_id"]}
    for t in ("animation", "video", "audio", "voice", "document"):
        if m.get(t):
            return {"type": t, "file_id": m[t]["file_id"]}
    return None


def parse_button_name(m):
    text = m.get("text") or ""
    b = text.encode("utf-16-le")
    icon = alt = None
    cuts = []
    for e in m.get("entities") or []:
        if e["type"] == "custom_emoji":
            piece = b[e["offset"] * 2:(e["offset"] + e["length"]) * 2].decode("utf-16-le")
            if icon is None:
                icon, alt = e["custom_emoji_id"], piece
            cuts.append((e["offset"], e["length"]))
    for off, ln in sorted(cuts, reverse=True):
        b = b[:off * 2] + b[(off + ln) * 2:]
    name = re.sub(r"\s+", " ", b.decode("utf-16-le")).strip()
    return name[:64], icon, alt


def move_item(items, i, step):
    j = i + step
    if not (0 <= i < len(items) and 0 <= j < len(items)):
        return None
    items[i], items[j] = items[j], items[i]
    return j


def button_label(b):
    return f"{b['alt']} {b['text']}" if b.get("alt") else b["text"]


def make_button(b, icons=True):
    btn = {"text": b["text"], "url": b["url"]}
    if b.get("style"):
        btn["style"] = b["style"]
    if icons and b.get("icon"):
        btn["icon_custom_emoji_id"] = b["icon"]
    elif b.get("icon") and b.get("alt"):
        btn["text"] = button_label(b)
    return btn


def build_rows(buttons, icons=True, per_row=1):
    btns = [make_button(b, icons) for b in buttons or []]
    return [btns[i:i + per_row] for i in range(0, len(btns), per_row)]


def btn(text, data, style=None):
    b = {"text": text, "callback_data": data}
    if style:
        b["style"] = style
    return b


def _strip_kb(kb):
    if not kb or "inline_keyboard" not in kb:
        return kb
    rows = [[{k: v for k, v in b.items() if k != "icon_custom_emoji_id"} for b in r] for r in kb["inline_keyboard"]]
    return {"inline_keyboard": rows}


def _has_premium(text, kb):
    return bool(TG_EMOJI.search(text or "")) or "icon_custom_emoji_id" in str(kb or "")


async def call_rich(method, text_field, text, kb=None, **payload):
    r = await tg(method, **{text_field: text}, reply_markup=kb, parse_mode="HTML", **payload)
    if not r.get("ok") and _has_premium(text, kb) and "not modified" not in r.get("description", ""):
        r = await tg(method, **{text_field: strip_tg_emoji(text)}, reply_markup=_strip_kb(kb), parse_mode="HTML", **payload)
    return r


async def send_rich(chat_id, text, rows=None, **extra):
    kb = {"inline_keyboard": rows} if rows else extra.pop("reply_markup", None)
    return await call_rich("sendMessage", "text", text, kb, chat_id=chat_id,
                           link_preview_options={"is_disabled": True}, **extra)


async def panel(chat_id, text, rows, mid=None):
    if mid:
        r = await call_rich("editMessageText", "text", text, {"inline_keyboard": rows}, chat_id=chat_id,
                            message_id=mid, link_preview_options={"is_disabled": True})
        if r.get("ok") or "not modified" in r.get("description", ""):
            return r
    return await send_rich(chat_id, text, rows)


async def deliver(chat_id, cfg, user, extra_rows=None):
    text = render(cfg.get("text") or "", user)
    rows = build_rows(cfg.get("buttons"), True, cfg.get("layout") or 1) + (extra_rows or [])
    kb = {"inline_keyboard": rows} if rows else None
    media = cfg.get("media")
    if not media:
        return await call_rich("sendMessage", "text", text, kb, chat_id=chat_id, link_preview_options={"is_disabled": True})
    method, field = f"send{media['type'].capitalize()}", media["type"]
    if text and plain_len(text) <= CAPTION_LIMIT:
        return await call_rich(method, "caption", text, kb, chat_id=chat_id, **{field: media["file_id"]})
    r = await call_rich(method, "caption", None, None if text else kb, chat_id=chat_id, **{field: media["file_id"]})
    if text:
        r = await call_rich("sendMessage", "text", text, kb, chat_id=chat_id, link_preview_options={"is_disabled": True})
    return r
