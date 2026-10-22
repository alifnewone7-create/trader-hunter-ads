import asyncio
import time
from collections import defaultdict, deque

from telegram_api import tg

LIMIT, WINDOW, COOLDOWN = 3, 60, 30
BN = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
_hits = defaultdict(deque)
_until = {}
_running = {}


def _text(left):
    return (f"⏳ <b>অনেক বেশি চেষ্টা করেছেন!</b>\n\n১ মিনিটে ৩ বারের বেশি /start দেওয়া যাবে না।\n"
            f"অনুগ্রহ করে <b>{str(left).translate(BN)} সেকেন্ড</b> অপেক্ষা করুন।")


async def _countdown(chat_id, uid):
    try:
        r = await tg("sendMessage", chat_id=chat_id, text=_text(COOLDOWN), parse_mode="HTML")
        mid = (r.get("result") or {}).get("message_id")
        while mid:
            left = int(_until.get(uid, 0) - time.monotonic() + 0.999)
            if left <= 0:
                break
            await asyncio.sleep(1)
            left = max(0, int(_until.get(uid, 0) - time.monotonic() + 0.999))
            if left:
                e = await tg("editMessageText", chat_id=chat_id, message_id=mid, text=_text(left), parse_mode="HTML")
                if e.get("error_code") == 429:
                    await asyncio.sleep((e.get("parameters") or {}).get("retry_after", 1))
        if not mid:
            await asyncio.sleep(max(0, _until.get(uid, 0) - time.monotonic()))
        else:
            await tg("editMessageText", chat_id=chat_id, message_id=mid, parse_mode="HTML",
                     text="✅ <b>অপেক্ষা শেষ!</b>\n\nএখন আবার /start দিতে পারবেন।")
    finally:
        _running.pop(uid, None)


def blocked(chat_id, uid):
    now = time.monotonic()
    if _until.get(uid, 0) > now:
        _start(chat_id, uid)
        return True
    _until.pop(uid, None)
    hits = _hits[uid]
    while hits and now - hits[0] > WINDOW:
        hits.popleft()
    hits.append(now)
    if len(hits) <= LIMIT:
        return False
    _hits.pop(uid, None)
    _until[uid] = now + COOLDOWN
    _start(chat_id, uid)
    return True


def _start(chat_id, uid):
    if uid not in _running:
        _running[uid] = asyncio.create_task(_countdown(chat_id, uid))
