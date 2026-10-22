import logging
import os

import httpx

log = logging.getLogger("telegram")
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
BOT_ID = int(TOKEN.split(":")[0])
BASE = f"https://api.telegram.org/bot{TOKEN}"
BOT_INFO = {"username": None}
_client = httpx.AsyncClient(timeout=20)


async def tg(method: str, **payload) -> dict:
    payload = {k: v for k, v in payload.items() if v is not None}
    try:
        r = await _client.post(f"{BASE}/{method}", json=payload)
        data = r.json()
    except Exception as e:
        log.warning("Telegram %s failed: %s", method, e)
        return {"ok": False, "description": str(e)}
    if not data.get("ok"):
        log.warning("Telegram %s error: %s", method, data.get("description"))
    return data


async def init_bot():
    me = await tg("getMe")
    if me.get("ok"):
        BOT_INFO["username"] = me["result"]["username"]
    if os.environ.get("DISABLE_WEBHOOK_SETUP") == "true":
        return log.info("setWebhook skipped (DISABLE_WEBHOOK_SETUP=true)")
    url = f"{os.environ['PUBLIC_BASE_URL'].rstrip('/')}/api/telegram/webhook"
    res = await tg(
        "setWebhook",
        url=url,
        secret_token=os.environ["TELEGRAM_WEBHOOK_SECRET"],
        allowed_updates=["message", "callback_query", "chat_join_request", "my_chat_member", "chat_member"],
    )
    log.info("setWebhook %s -> %s", url, res.get("ok"))
