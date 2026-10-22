import asyncio
import hmac
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from bot import handle_update  # noqa: E402
from db import close_db, ensure_indexes  # noqa: E402
from telegram_api import init_bot  # noqa: E402
from extras import seed_admins, spawn, sync_unrequested  # noqa: E402
from tracking import router as tracking_router  # noqa: E402
from download import router as download_router  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI()
api_router = APIRouter(prefix="/api")
WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]
_tasks = set()


@api_router.get("/")
async def root():
    return {"message": "ok"}


@api_router.post("/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
    if not hmac.compare_digest(x_telegram_bot_api_secret_token or "", WEBHOOK_SECRET):
        raise HTTPException(401, "invalid secret")
    update = await request.json()
    task = asyncio.create_task(_process(update))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"ok": True}


async def _process(update):
    try:
        await handle_update(update)
    except Exception:
        logger.exception("update handling failed")


api_router.include_router(tracking_router)
if os.environ.get("ENABLE_DOWNLOAD") != "false":
    api_router.include_router(download_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    await init_bot()
    await seed_admins()
    spawn(sync_unrequested())


@app.on_event("shutdown")
async def shutdown_db_client():
    await close_db()
