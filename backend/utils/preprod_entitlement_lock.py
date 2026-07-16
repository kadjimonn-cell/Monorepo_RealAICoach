"""Pre-Production Entitlement Lock.

While active, every non-admin user resolves to the `free` plan regardless of
stored subscription state, and paid-plan checkout/upgrade paths are blocked.
Flip off at production launch via POST /api/platform-control/entitlement-lock.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

LOCK_DOC_ID = "preprod_entitlement_lock"

_CACHE: dict = {"active": None}


def _env_default() -> bool:
    raw = str(os.environ.get("PREPROD_ENTITLEMENT_LOCK", "true")).strip().lower()
    return raw not in {"0", "false", "off", "no"}


def is_preprod_lock_active() -> bool:
    cached = _CACHE["active"]
    if cached is None:
        return _env_default()
    return bool(cached)


async def load_preprod_lock_state() -> bool:
    from routes.db import db

    doc = await db.platform_entitlement_lock.find_one({"lock_id": LOCK_DOC_ID}, {"_id": 0})
    if doc is not None and "active" in doc:
        _CACHE["active"] = bool(doc["active"])
    else:
        _CACHE["active"] = _env_default()
    return _CACHE["active"]


async def set_preprod_lock_state(active: bool, actor_email: str) -> dict:
    from routes.db import db

    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {"active": bool(active), "updated_at": now_iso, "updated_by": str(actor_email or "")}
    await db.platform_entitlement_lock.update_one(
        {"lock_id": LOCK_DOC_ID}, {"$set": payload}, upsert=True
    )
    _CACHE["active"] = bool(active)
    await db.subscription_audit_log.insert_one(
        {
            "event_type": "preprod_entitlement_lock_toggled",
            "active": bool(active),
            "actor_email": str(actor_email or ""),
            "created_at": now_iso,
        }
    )
    return payload


def get_preprod_lock_snapshot() -> dict:
    return {"active": is_preprod_lock_active(), "env_default": _env_default()}
