from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from routes.db import db


async def reserve_dispatch_once(*, dedupe_key: str, event_type: str, channel: str, recipient: str, payload: Dict[str, Any]) -> bool:
    """Immutable one-time reservation for notification/email dispatch.

    Uses unique `dedupe_key` in `notification_dispatch_log` as the canonical
    global-send ledger.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    payload_hash = hashlib.sha256(str(payload).encode("utf-8", errors="ignore")).hexdigest()[:24]
    try:
        await db.notification_dispatch_log.insert_one(
            {
                "dispatch_id": f"ndis_{uuid.uuid4().hex[:12]}",
                "dedupe_key": str(dedupe_key).strip().lower(),
                "event_type": str(event_type or "").strip().lower(),
                "channel": str(channel or "").strip().lower(),
                "recipient": str(recipient or "").strip().lower(),
                "payload_hash": payload_hash,
                "status": "reserved",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        )
        return True
    except Exception:
        return False


async def mark_dispatch_status(*, dedupe_key: str, status: str, extra: Dict[str, Any] | None = None) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    doc: Dict[str, Any] = {"status": str(status or "").strip().lower(), "updated_at": now_iso}
    if extra:
        doc.update(extra)
    await db.notification_dispatch_log.update_one(
        {"dedupe_key": str(dedupe_key).strip().lower()},
        {"$set": doc},
    )
