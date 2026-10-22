import os

from db import db


async def get_settings() -> dict:
    doc = await db.settings.find_one({"_id": "main"}) or {}
    return {
        "pixel_id": doc.get("pixel_id") or os.environ.get("META_PIXEL_ID", ""),
        "capi_token": doc.get("capi_token") or os.environ.get("META_ACCESS_TOKEN", ""),
        "test_event_code": doc["test_event_code"] if "test_event_code" in doc else os.environ.get("META_TEST_EVENT_CODE", ""),
        "channel_id": doc.get("channel_id"),
        "channel_title": doc.get("channel_title"),
        "invite_link": doc.get("invite_link"),
        "notify": doc.get("notify", False),
        "auto_approve": doc.get("auto_approve", False),
        "member_count": doc.get("member_count", 0),
    }


async def update_settings(**values):
    await db.settings.update_one({"_id": "main"}, {"$set": values}, upsert=True)
