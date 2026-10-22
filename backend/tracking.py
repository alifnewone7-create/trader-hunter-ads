import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, Field
from db import DuplicateKeyError

from db import db
from meta_capi import build_user_data, send_event
from settings_store import get_settings
from telegram_api import BOT_INFO

router = APIRouter()
TOKEN_TTL = int(os.environ["START_TOKEN_TTL_MINUTES"])
FB_RE = re.compile(r"^fb\.\d\.\d+\..+$")
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


class TrackIn(BaseModel):
    visitor_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    url: Optional[str] = Field(None, max_length=2000)
    fbp: Optional[str] = Field(None, max_length=200)
    fbc: Optional[str] = Field(None, max_length=600)


class PageViewIn(TrackIn):
    event_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    referrer: Optional[str] = Field(None, max_length=2000)


def client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def upsert_visitor(body: TrackIn, request: Request) -> dict:
    now = datetime.now(timezone.utc)
    fields = {"ip": client_ip(request), "user_agent": request.headers.get("user-agent", "")[:500], "last_seen": now}
    if body.fbp and FB_RE.match(body.fbp):
        fields["fbp"] = body.fbp
    fbc = body.fbc if body.fbc and FB_RE.match(body.fbc) else None
    if body.url:
        fields["landing_url"] = body.url
        qs = parse_qs(urlparse(body.url).query)
        fbclid = (qs.get("fbclid") or [None])[0]
        if fbclid and not fbc:
            fbc = f"fb.1.{int(time.time() * 1000)}.{fbclid}"
        utm = {k: qs[k][0][:200] for k in UTM_KEYS if qs.get(k)}
        if utm:
            fields["utm"] = utm
    if fbc:
        fields["fbc"] = fbc
    return await db.visitors.find_one_and_update(
        {"visitor_id": body.visitor_id},
        {"$set": fields, "$setOnInsert": {"created_at": now}},
        upsert=True,
        return_document=True,
    )


async def send_server_pageview(event_id: str, visitor: dict):
    res = await send_event("PageView", event_id, build_user_data(visitor), source_url=visitor.get("landing_url"))
    await db.pageviews.update_one(
        {"event_id": event_id},
        {"$set": {"capi_status": "sent" if res["ok"] else "failed", "capi_error": res.get("error")}},
    )


@router.get("/public/config")
async def public_config():
    s = await get_settings()
    return {"pixel_id": s["pixel_id"] or None, "bot_username": BOT_INFO["username"]}


@router.post("/track/pageview")
async def track_pageview(body: PageViewIn, request: Request, tasks: BackgroundTasks):
    visitor = await upsert_visitor(body, request)
    try:
        await db.pageviews.insert_one({
            "event_id": body.event_id,
            "visitor_id": body.visitor_id,
            "referrer": body.referrer,
            "created_at": datetime.now(timezone.utc),
            "capi_status": "pending",
        })
    except DuplicateKeyError:
        return {"ok": True, "duplicate": True}
    tasks.add_task(send_server_pageview, body.event_id, visitor)
    return {"ok": True}


class StartLinkIn(TrackIn):
    token: Optional[str] = Field(None, min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/track/start-link")
async def start_link(body: StartLinkIn, request: Request):
    await upsert_visitor(body, request)
    now = datetime.now(timezone.utc)
    token = body.token or secrets.token_urlsafe(12)
    try:
        await db.start_tokens.insert_one({
            "token": token,
            "visitor_id": body.visitor_id,
            "created_at": now,
            "expires_at": now + timedelta(minutes=TOKEN_TTL),
            "used": False,
        })
    except DuplicateKeyError:
        pass
    return {"deep_link": f"https://t.me/{BOT_INFO['username']}?start={token}"}
