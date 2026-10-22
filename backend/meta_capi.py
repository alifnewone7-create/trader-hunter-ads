import hashlib
import logging
import os
import time

import httpx

from settings_store import get_settings

log = logging.getLogger("meta")
GRAPH = f"https://graph.facebook.com/{os.environ['META_API_VERSION']}"
_client = httpx.AsyncClient(timeout=20)


def sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def build_user_data(visitor: dict) -> dict:
    ud = {}
    if visitor.get("ip"):
        ud["client_ip_address"] = visitor["ip"]
    if visitor.get("user_agent"):
        ud["client_user_agent"] = visitor["user_agent"]
    if visitor.get("fbc"):
        ud["fbc"] = visitor["fbc"]
    if visitor.get("fbp"):
        ud["fbp"] = visitor["fbp"]
    if visitor.get("visitor_id"):
        ud["external_id"] = [sha256(visitor["visitor_id"])]
    return ud


async def send_event(event_name, event_id, user_data, source_url=None, event_time=None, custom_data=None) -> dict:
    s = await get_settings()
    if not s["pixel_id"] or not s["capi_token"]:
        return {"ok": False, "error": "Pixel ID বা Access Token সেট করা নেই"}
    event = {
        "event_name": event_name,
        "event_time": int(event_time or time.time()),
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
    }
    if source_url:
        event["event_source_url"] = source_url
    if custom_data:
        event["custom_data"] = custom_data
    payload = {"data": [event]}
    if s["test_event_code"]:
        payload["test_event_code"] = s["test_event_code"]
    try:
        r = await _client.post(f"{GRAPH}/{s['pixel_id']}/events", params={"access_token": s["capi_token"]}, json=payload)
        body = r.json()
    except Exception as e:
        log.warning("CAPI %s failed: %s", event_name, e)
        return {"ok": False, "error": str(e)[:300]}
    if r.status_code == 200 and body.get("events_received"):
        return {"ok": True, "fbtrace_id": body.get("fbtrace_id"), "test": bool(s["test_event_code"])}
    err = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else str(body)
    log.warning("CAPI %s rejected: %s", event_name, err)
    return {"ok": False, "error": str(err)[:300]}


async def verify_token(pixel_id: str, token: str):
    try:
        r = await _client.get(f"{GRAPH}/{pixel_id}", params={"fields": "id,name", "access_token": token})
        body = r.json()
    except Exception as e:
        return False, str(e)[:200]
    if "error" in body:
        return False, body["error"].get("message", "unknown error")
    return True, body.get("name") or body.get("id")
