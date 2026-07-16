"""Web Push Notification Service — VAPID-based push notifications.

Endpoints:
- GET  /api/push/vapid-public-key — Returns the public VAPID key for client subscription
- POST /api/push/subscribe — Store a push subscription
- POST /api/push/unsubscribe — Remove a push subscription
- POST /api/admin/push/send — Send push notification to specific users or all subscribers
- GET  /api/admin/push/subscribers — List all push subscribers
"""

import os
import logging
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Push Notifications"])

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
# Handle PEM keys stored in .env with literal \n instead of real newlines
_raw_private = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PRIVATE_KEY = _raw_private.replace("\\n", "\n") if "\\n" in _raw_private else _raw_private
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@realaicoach.app")


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict  # {auth: str, p256dh: str}
    user_id: Optional[str] = None


class PushMessage(BaseModel):
    title: str
    body: str
    url: Optional[str] = "/"
    icon: Optional[str] = None
    tag: Optional[str] = None
    user_ids: Optional[list] = None  # None = send to all


@router.get("/push/vapid-public-key")
async def get_vapid_public_key():
    """Return the public VAPID key for client-side subscription"""
    return {"public_key": VAPID_PUBLIC_KEY}


@router.post("/push/subscribe")
async def subscribe(request: Request, body: PushSubscription):
    """Store a push subscription"""
    from routes.db import db
    now = datetime.now(timezone.utc)

    doc = {
        "endpoint": body.endpoint,
        "keys": body.keys,
        "user_id": body.user_id,
        "subscribed_at": now,
        "last_push": None,
        "push_count": 0,
        "active": True,
    }
    await db.push_subscriptions.update_one(
        {"endpoint": body.endpoint},
        {"$set": doc},
        upsert=True
    )
    return {"status": "subscribed", "endpoint": body.endpoint[:50] + "..."}


@router.post("/push/unsubscribe")
async def unsubscribe(request: Request, body: PushSubscription):
    """Remove a push subscription"""
    from routes.db import db
    result = await db.push_subscriptions.delete_one({"endpoint": body.endpoint})
    return {"status": "unsubscribed", "deleted": result.deleted_count}


@router.post("/admin/push/send")
async def send_push_notification(request: Request, body: PushMessage):
    """Send push notification to subscribers"""
    from routes.db import db

    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
        return {"status": "error", "message": "VAPID keys not configured"}

    # Find target subscriptions
    query = {"active": True}
    if body.user_ids:
        query["user_id"] = {"$in": body.user_ids}

    subscriptions = []
    async for sub in db.push_subscriptions.find(query, {"_id": 0}):
        subscriptions.append(sub)

    if not subscriptions:
        return {"status": "no_subscribers", "sent": 0}

    payload = json.dumps({
        "title": body.title,
        "body": body.body,
        "url": body.url or "/",
        "icon": body.icon or "/api/static/images/favicon-64.png",
        "tag": body.tag,
    })

    sent = 0
    failed = 0
    errors = []

    try:
        from pywebpush import webpush, WebPushException

        vapid_claims = {"sub": VAPID_SUBJECT}

        for sub in subscriptions:
            try:
                subscription_info = {
                    "endpoint": sub["endpoint"],
                    "keys": sub["keys"],
                }
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,
                    timeout=10,
                )
                sent += 1
                await db.push_subscriptions.update_one(
                    {"endpoint": sub["endpoint"]},
                    {"$set": {"last_push": datetime.now(timezone.utc)}, "$inc": {"push_count": 1}}
                )
            except WebPushException as e:
                resp_code = getattr(e, 'response', None)
                status_code = resp_code.status_code if resp_code else 0
                if status_code in (404, 410):
                    await db.push_subscriptions.update_one(
                        {"endpoint": sub["endpoint"]},
                        {"$set": {"active": False}}
                    )
                failed += 1
                errors.append(str(e)[:100])
            except Exception as e:
                failed += 1
                errors.append(str(e)[:100])

    except ImportError:
        return {"status": "error", "message": "pywebpush library not installed. Run: pip install pywebpush"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}

    # Log push event
    await db.push_log.insert_one({
        "title": body.title,
        "body": body.body,
        "sent": sent,
        "failed": failed,
        "total_targets": len(subscriptions),
        "created_at": datetime.now(timezone.utc),
    })

    return {
        "status": "sent",
        "sent": sent,
        "failed": failed,
        "total_targets": len(subscriptions),
        "errors": errors[:5],
    }


@router.get("/admin/push/subscribers")
async def list_subscribers(request: Request):
    """List push subscribers"""
    from routes.db import db
    subs = []
    async for sub in db.push_subscriptions.find({"active": True}, {"_id": 0}).limit(100):
        if hasattr(sub.get("subscribed_at"), "isoformat"):
            sub["subscribed_at"] = sub["subscribed_at"].isoformat()
        if hasattr(sub.get("last_push"), "isoformat"):
            sub["last_push"] = sub["last_push"].isoformat()
        subs.append(sub)
    return {"subscribers": subs, "total": len(subs)}


def register(api_router, app):
    api_router.include_router(router)
