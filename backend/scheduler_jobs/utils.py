"""
scheduler_jobs.utils — Pure utility helpers for scheduled jobs.

**Phase 2 incremental domain split — first batch.**

These helpers are pure (no DB access, no external I/O dependencies on
module-level state) and used across the weekly-careers job pipeline.
They are now the canonical home; `scheduler_jobs/_legacy.py` re-imports
them so all existing call sites keep working unchanged.

Pattern for future extractions
==============================
1. Identify a cluster of pure / nearly-pure helpers in `_legacy.py`.
2. Move them here (or into a new domain module like `scheduler_jobs/email.py`).
3. In `_legacy.py`, replace the original `def` block with a single-line
   `from scheduler_jobs.utils import _name  # noqa: F401`.
4. The `__init__.py` facade auto-mirrors any new attribute, so external
   call sites (`from scheduler_jobs import _name`) keep working.
5. Run `python -m pytest backend/tests/` to confirm zero regressions.
"""

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _slugify_weekly_careers(value: str) -> str:
    """Convert a freeform title into a stable URL-safe slug.

    Used as the building block for weekly-careers job slugs. Returns
    the literal string ``weekly-careers-opening`` when the input is
    empty or contains only non-alphanumeric characters.
    """
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return normalized or "weekly-careers-opening"


def _resolve_frontend_base_url() -> str:
    """Return the public frontend base URL for outbound notifications.

    Probes ``FRONTEND_BASE_URL``, ``REACT_APP_BACKEND_URL``, then
    ``EXPO_PUBLIC_BACKEND_URL`` and returns the first value that looks
    like an http(s) URL. Returns an empty string when nothing usable
    is configured (callers must guard against this and skip the link).
    """
    candidates = [
        str(os.environ.get("FRONTEND_BASE_URL") or "").strip(),
        str(os.environ.get("REACT_APP_BACKEND_URL") or "").strip(),
        str(os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "").strip(),
    ]
    for candidate in candidates:
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate.rstrip("/")
    return ""


def _is_active_user_record(user: Dict[str, Any]) -> bool:
    """Return True when a user record qualifies for engagement campaigns.

    Excludes accounts that are explicitly locked (``access_locked``)
    or in a non-paying subscription state. Used by the weekly-careers
    job and engagement email pipelines.
    """
    if not user:
        return False
    if user.get("access_locked") is True:
        return False
    status = str(user.get("subscription_status") or "").strip().lower()
    return status in {"active", "trial"}


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    """Best-effort ISO-8601 → timezone-aware datetime parser.

    Accepts ``Z`` suffix and naive ISO strings (assumed UTC).
    Returns ``None`` for empty / unparseable input. Used by the
    global-parity safe-precheck cooldown logic and the
    fee-visibility visual audit safe-config rollback flow.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


__all__ = [
    "_slugify_weekly_careers",
    "_resolve_frontend_base_url",
    "_is_active_user_record",
    "_parse_iso_datetime",
]
