"""Feature 32 policy lifecycle scheduler jobs (Checkpoint C2)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from routes.db import db

logger = logging.getLogger("scheduler_jobs.feature32_policy")


async def scheduled_feature32_override_policy_expiry_sweeper():
    """Expire approved override policies whose expiry timestamp has elapsed."""
    now_iso = datetime.now(timezone.utc).isoformat()
    query = {
        "override_approved": True,
        "override_expires_at": {"$ne": "", "$lte": now_iso},
        "policy_state": {"$ne": "revoked"},
    }
    update = {
        "$set": {
            "override_approved": False,
            "policy_state": "expired",
            "override_expired_at": now_iso,
            "updated_at": now_iso,
            "updated_by": "scheduler_feature32_policy_expiry_sweeper",
            "active": True,
        }
    }
    result = await db.email_notification_template_policies.update_many(query, update)
    if result.modified_count:
        logger.info("feature32 policy expiry sweeper expired=%s", result.modified_count)
