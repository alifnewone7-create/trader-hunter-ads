import re
from datetime import datetime, timedelta

from bot import BD, now
from db import db
from extras import answer, set_state
from rich import btn, panel, send_rich

BACK = [btn("⬅️ Back", "ct:open", "danger")]
HOME = [btn("🏠 Menu", "m:home", "danger")]
CANCEL = [[btn("❌ Cancel", "ct:open", "danger")]]
TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.I)


def bd_today():
    n = now().astimezone(BD)
    return datetime(n.year, n.month, n.day, tzinfo=BD)


def ex_date():
    return (bd_today() - timedelta(days=1)).strftime("%d-%m-%Y")


def key_of(d):
    return d.strftime("%Y%m%d")


def day_of(key):
    return datetime.strptime(key, "%Y%m%d").replace(tzinfo=BD)


def parse_date(text):
    m = re.fullmatch(r"\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\s*", text or "")
    if not m:
        return None
    try:
        return datetime(int(m[3]), int(m[2]), int(m[1]), tzinfo=BD)
    except ValueError:
        return None


def parse_clock(text):
    m = TIME_RE.match(text or "")
    if not m:
        return None
    h, mi, ap = int(m[1]), int(m[2] or 0), (m[3] or "").lower()
    if ap:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ap == "pm" else 0)
    if h > 23 or mi > 59:
        return None
    return h, mi


def parse_range(text, day):
    parts = re.split(r"\s*(?:-|–|to)\s*", (text or "").strip(), maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return None
    a, b = parse_clock(parts[0]), parse_clock(parts[1])
    if not a or not b:
        return None
    start = day + timedelta(hours=a[0], minutes=a[1])
    end = day + timedelta(hours=b[0], minutes=b[1])
    if b == (0, 0):
        end = day + timedelta(days=1)
    return start, end


async def range_counts(start, end):
    t = {"$gte": start, "$lt": end}
    rows = [
        ("🌐 Page Visits", db.pageviews.count_documents({"created_at": t})),
        ("👆 Button Clicks", db.start_tokens.count_documents({"created_at": t})),
        ("🤖 Bot Start", db.leads.count_documents({"started_at": t})),
        ("👥 New Users", db.users.count_documents({"joined_at": t})),
        ("📨 Join Requests", db.join_requests.count_documents({"created_at": t})),
        ("✅ Approved", db.join_requests.count_documents({"status": "approved", "decided_at": t})),
        ("🟢 Joined", db.members.count_documents({"status": "joined", "updated_at": t})),
        ("🚪 Leaved", db.members.count_documents({"status": "left", "updated_at": t})),
        ("📝 Unrequested", db.unrequested.count_documents({"started_at": t})),
        ("🎯 Subscribe Sent", db.leads.count_documents({"subscribe_status": "sent", "subscribe_at": t})),
        ("⚠️ Subscribe Failed", db.leads.count_documents({"subscribe_status": "failed", "subscribe_at": t})),
        ("➖ Unmatched", db.leads.count_documents({"subscribe_status": "unmatched", "subscribe_at": t})),
    ]
    return [(label, await c) for label, c in rows]


def fmt_t(dt):
    return dt.astimezone(BD).strftime("%I:%M %p").lstrip("0")


async def show_result(chat_id, start, end, mid=None, full=False):
    rows = await range_counts(start, end)
    span = "Full Day" if full and end - start == timedelta(days=1) else f"{fmt_t(start)} → {fmt_t(end)}"
    head = f"📅 <b>{start.astimezone(BD).strftime('%d %b %Y')}</b>\n🕒 <b>{span}</b>"
    body = "\n".join(f"{label}: <b>{n}</b>" for label, n in rows)
    text = f"📊 <b>Custom Time Report</b> (Bangladesh time)\n\n{head}\n\n{body}"
    await panel(chat_id, text, [[btn("🔁 New Check", "ct:open", "primary")], HOME], mid)


async def show_dates(chat_id, mid=None):
    today = bd_today()
    days = [today - timedelta(days=i) for i in range(7)]
    cells = [btn("📅 Today" if i == 0 else "📅 Yesterday" if i == 1 else d.strftime("%d %b"), f"ct:d:{key_of(d)}",
                 "success" if i == 0 else "primary") for i, d in enumerate(days)]
    rows = [cells[:2], cells[2:4], cells[4:6], cells[6:] + [btn("✏️ Custom Date", "ct:cd", "success")], HOME]
    text = ("🕒 <b>Custom Time Stats</b>\n\nকোন তারিখের data দেখতে চান? নিচ থেকে বেছে নিন, অথবা "
            "<b>✏️ Custom Date</b> চাপ দিয়ে যেকোনো তারিখ দিন।\n\n<i>সময় বাংলাদেশ টাইম অনুযায়ী।</i>")
    await panel(chat_id, text, rows, mid)


async def show_mode(chat_id, day, mid=None):
    k = key_of(day)
    text = (f"📅 <b>{day.strftime('%d %b %Y')}</b>\n\nপুরো দিনের data দেখবেন, নাকি নির্দিষ্ট সময়ের?")
    await panel(chat_id, text, [[btn("📆 Full Day", f"ct:f:{k}", "success"),
                                 btn("🕒 Custom Time", f"ct:t:{k}", "primary")], BACK], mid)


def check_day(day):
    return day <= bd_today()


async def on_ct_cb(cq, data, chat_id, mid):
    uid = cq["from"]["id"]
    parts = data.split(":")
    if data == "ct:open":
        await set_state(uid, "ct_date")
        await answer(cq)
        return await show_dates(chat_id, mid)
    if data == "ct:cd":
        await set_state(uid, "ct_date")
        await answer(cq)
        return await panel(chat_id, "✏️ <b>Custom Date</b>\n\nযে তারিখের data দেখতে চান সেটা লিখে পাঠান।\n\n"
                           f"ফরম্যাট: <code>DD-MM-YYYY</code>\nউদাহরণ: <code>{ex_date()}</code>\n\n"
                           "<i>ভবিষ্যতের তারিখ দেওয়া যাবে না।</i>", CANCEL, mid)
    try:
        day = day_of(parts[2])
    except (IndexError, ValueError):
        return await answer(cq)
    if not check_day(day):
        return await answer(cq, "⚠️ ভবিষ্যতের তারিখ দেওয়া যাবে না।", True)
    await answer(cq)
    if parts[1] == "d":
        await set_state(uid, None)
        return await show_mode(chat_id, day, mid)
    if parts[1] == "f":
        await set_state(uid, None)
        return await show_result(chat_id, day, min(day + timedelta(days=1), now()), mid, True)
    await set_state(uid, "ct_time", day=parts[2])
    await panel(chat_id, f"📅 <b>{day.strftime('%d %b %Y')}</b>\n\nকোন সময় থেকে কোন সময় পর্যন্ত দেখতে চান লিখে পাঠান।\n\n"
                "উদাহরণ:\n<code>5AM-6AM</code>\n<code>5:30 PM - 8 PM</code>\n<code>14:00-16:30</code>\n\n"
                "<i>বর্তমান সময়ের পরের সময় দেওয়া যাবে না।</i>", CANCEL, mid)


async def on_ct_input(m, admin):
    chat_id, uid = m["chat"]["id"], admin["user_id"]
    text = (m.get("text") or "").strip()
    if admin["awaiting"] == "ct_date":
        day = parse_date(text)
        if not day:
            return await send_rich(chat_id, f"⚠️ সঠিক তারিখ দিন, যেমন <code>{ex_date()}</code>।", CANCEL)
        if not check_day(day):
            return await send_rich(chat_id, "⚠️ ভবিষ্যতের তারিখ দেওয়া যাবে না।", CANCEL)
        await set_state(uid, None)
        return await show_mode(chat_id, day)
    day = day_of((admin.get("ctx") or {}).get("day") or key_of(bd_today()))
    rng = parse_range(text, day)
    if not rng:
        return await send_rich(chat_id, "⚠️ সময় বুঝতে পারিনি। এভাবে লিখুন: <code>5AM-6AM</code>", CANCEL)
    start, end = rng
    if start >= end:
        return await send_rich(chat_id, "⚠️ শুরুর সময় শেষের সময়ের আগে হতে হবে।", CANCEL)
    if end > now():
        return await send_rich(chat_id, f"⚠️ বর্তমান সময়ের (<b>{fmt_t(now())}</b>) পরের সময় দেওয়া যাবে না।", CANCEL)
    await set_state(uid, None)
    await show_result(chat_id, start, end)
