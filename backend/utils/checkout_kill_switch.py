from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException


CHECKOUT_KILL_SWITCH_KEY = "checkout_global_kill_switch"
DEFAULT_CHECKOUT_PAUSE_MESSAGE = "Checkout is temporarily paused by admin while payment integrity checks are in progress."


async def get_checkout_kill_switch_state(db) -> Dict[str, Any]:
    doc = await db.system_runtime_flags.find_one({"key": CHECKOUT_KILL_SWITCH_KEY}, {"_id": 0}) or {}
    enabled = bool(doc.get("enabled", False))
    reason = str(doc.get("reason") or DEFAULT_CHECKOUT_PAUSE_MESSAGE)
    updated_at = doc.get("updated_at")
    updated_by = doc.get("updated_by")
    source = str(doc.get("source") or "admin_toggle")
    return {
        "key": CHECKOUT_KILL_SWITCH_KEY,
        "enabled": enabled,
        "reason": reason,
        "updated_at": updated_at,
        "updated_by": updated_by,
        "source": source,
    }


async def set_checkout_kill_switch_state(
    db,
    *,
    enabled: bool,
    reason: str,
    updated_by: str,
    source: str = "admin_toggle",
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "key": CHECKOUT_KILL_SWITCH_KEY,
        "enabled": bool(enabled),
        "reason": str(reason or DEFAULT_CHECKOUT_PAUSE_MESSAGE),
        "updated_at": now_iso,
        "updated_by": str(updated_by or "admin"),
        "source": str(source or "admin_toggle"),
    }
    await db.system_runtime_flags.update_one(
        {"key": CHECKOUT_KILL_SWITCH_KEY},
        {"$set": payload},
        upsert=True,
    )
    return payload


async def raise_if_checkout_paused(db) -> None:
    state = await get_checkout_kill_switch_state(db)
    if not state.get("enabled"):
        return

    raise HTTPException(
        status_code=503,
        detail={
            "code": "CHECKOUT_KILL_SWITCH_ENABLED",
            "message": state.get("reason") or DEFAULT_CHECKOUT_PAUSE_MESSAGE,
        },
    )
