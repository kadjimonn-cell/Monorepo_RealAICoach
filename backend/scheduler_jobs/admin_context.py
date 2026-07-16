"""
scheduler_jobs.admin_context — Scheduler admin authentication context.

**Phase 2 incremental domain split — batch #20 (final consolidation).**

Provides the canonical scheduler-admin user context and JWT minter used
by background jobs that must hit internal admin-only endpoints
(`/api/admin/platform-health/...`, audit replay, etc.).

Pulled out of the former `scheduler_jobs/_legacy.py` so multiple
extracted job modules (`weekly_careers`, `enterprise_enforcement`,
`audit_gates`, `platform_health`, `hosting`, `global_parity`,
`visual_audits`, `preview_cache`) can import directly without
re-entering the legacy facade.

Public API
==========
- ``_SchedulerAdminContext`` — minimal duck-typed user object exposing
  ``user_id``, ``email``, and ``is_admin`` (always True).
- ``_get_scheduler_admin_context()`` — async; looks up the first
  ``is_admin: True`` user in Mongo and returns a populated context.
  Falls back to ``("scheduler_admin", ADMIN_EMAILS[0] or "system@localhost")``
  when no admin user exists.
- ``_mint_scheduler_admin_token(minutes: int = 30)`` — async; mints a
  short-lived JWT for the scheduler admin and persists the session in
  ``db.user_sessions``. Returns an empty string when no admin user is
  available (callers must skip on empty).
"""

import os
from datetime import datetime, timedelta, timezone


class _SchedulerAdminContext:
    """Minimal admin user context used by scheduled jobs."""

    def __init__(self, user_id: str, email: str):
        self.user_id = user_id
        self.email = email
        self.is_admin = True


async def _get_scheduler_admin_context() -> _SchedulerAdminContext:
    from routes.db import db

    admin = await db.users.find_one(
        {"is_admin": True},
        {"_id": 0, "user_id": 1, "email": 1},
    )
    if admin and admin.get("user_id") and admin.get("email"):
        return _SchedulerAdminContext(admin["user_id"], admin["email"])
    return _SchedulerAdminContext(
        "scheduler_admin",
        os.environ.get("ADMIN_EMAILS", "").split(",")[0].strip() or "system@localhost",
    )


async def _mint_scheduler_admin_token(minutes: int = 30) -> str:
    from routes.db import db, create_jwt_token

    admin = await db.users.find_one(
        {"is_admin": True},
        {"_id": 0, "user_id": 1, "email": 1, "token_version": 1},
    )
    if not admin or not admin.get("user_id") or not admin.get("email"):
        return ""

    token_version = int(admin.get("token_version", 0) or 0)
    token = create_jwt_token(admin["user_id"], admin["email"], token_version, minutes)
    now = datetime.now(timezone.utc)
    await db.user_sessions.update_one(
        {"session_token": token},
        {
            "$set": {
                "session_token": token,
                "user_id": admin["user_id"],
                "email": admin["email"],
                "issued_at": now,
                "expires_at": now + timedelta(minutes=minutes),
                "created_at": now.isoformat(),
            }
        },
        upsert=True,
    )
    return token


__all__ = [
    "_SchedulerAdminContext",
    "_get_scheduler_admin_context",
    "_mint_scheduler_admin_token",
]
