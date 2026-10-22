# TG Bot - Meta Ads
User uploaded zip; unzipped into /app (backend FastAPI webhook bot + React landing). Configured .env with bot token, Neon Postgres DATABASE_URL, ADMIN_IDS=7188243734. Webhook set to preview URL. Meta Pixel/CAPI tokens left empty.

## 2026-06 Custom Time Stats
- Added "🕒 Custom Time" button in Stats (m:stats) and Statistics (adm:stats). Flow: pick date (last 7 days buttons or type DD-MM-YYYY) -> Full Day or Custom Time (e.g. 5AM-6AM). Future dates/times rejected. Bangladesh time. Code: backend/customtime.py
- Backlog: welcome message + Start button on join request (5-min window) so broadcasts reach requesters
- Added ✏️ Custom Date button (ct:cd) in Custom Time date picker to type any date
- Stats (m:stats) now shows আজ / ৭ দিন / ৩০ দিন / মোট per metric in spaced tree layout + update time
- Join requests/joins only counted & notified when made via bot's CURRENT invite link (settings.invite_link); other links ignored (bot.is_bot_link, extras.on_chat_member)
- Frontend brand name single source: frontend/src/brand.json (used in content.js + index.html via REACT_APP_BRAND_NAME set in craco.config.js)
- backend-vps obfuscated .c regenerated (Cython 3.3.0) for bot, extras, admin_panel + new customtime after each backend change
- /download now includes all .md docs (README, vps-run, vps-obfuscated-run, domain-to-vps, vercel-setup, PRD.md) except test_credentials.md; always builds live (updated code); moved vps docs from tgbot/ to /app root, removed tgbot extraction dir
- Wlc Start Msg: "Set Record / Media" (recmedia.py). Record Video (video_note/video) + Extra Media (text/media) as separate /start messages, each optional & removable; Set Order reorders enabled blocks (rec/xtra/main). Stored in db.msgs _id start_rec/start_xtra/start_seq. send_start() sends ordered sequence.
