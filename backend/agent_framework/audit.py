"""Centralized audit logging for all agent framework operations."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


async def log_audit(
    action: str,
    actor_id: Optional[str] = None,
    entity_type: str = "",
    entity_id: str = "",
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    from routes.db import db

    await db.af_audit_log.insert_one({
        "audit_id": str(uuid.uuid4()),
        "action": action,
        "actor_id": actor_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "detail": detail or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
