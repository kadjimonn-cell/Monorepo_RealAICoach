from __future__ import annotations

from typing import Iterable
from datetime import datetime, timezone

from routes.db import db


# Enterprise guardrail: transactional reminder-family templates are protected
# from subject experiments and automated override mutations.
PROTECTED_SUBJECT_OVERRIDE_PREFIXES: tuple[str, ...] = (
    "reminder",
    "meeting_reminder",
    "booking_reminder",
    "agenda_reminder",
)

PROTECTED_SUBJECT_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "meeting_reminder",
        "meeting_reminder_calendar",
        "booking_created",
        "booking_confirmed_host",
        "booking_confirmed_guest",
        "booking_cancelled",
        "booking_rescheduled",
        "agenda_reminder",
    }
)


def _normalized(value: str | None) -> str:
    return str(value or "").strip().lower()


def is_protected_subject_override_target(key_or_type: str | None) -> bool:
    value = _normalized(key_or_type)
    if not value:
        return False
    if value in PROTECTED_SUBJECT_OVERRIDE_KEYS:
        return True
    return any(value.startswith(prefix) for prefix in PROTECTED_SUBJECT_OVERRIDE_PREFIXES)


def any_protected_targets(values: Iterable[str]) -> bool:
    return any(is_protected_subject_override_target(v) for v in values)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def can_write_subject_override(*, template_key: str, actor: str, source: str) -> tuple[bool, dict]:
    """Central gate for all subject override writes (AB/autofix/admin).

    Enforces protected-template deny + policy approval/expiry for non-protected
    template overrides.
    """
    key = _normalized(template_key)
    actor_id = _normalized(actor)
    source_id = _normalized(source)
    now_iso = _now_iso()

    if not key:
        return False, {"reason": "template_key_required"}

    if is_protected_subject_override_target(key):
        return False, {"reason": "protected_template_blocked", "template_key": key}

    policy = await db.email_notification_template_policies.find_one({"template_key": key}, {"_id": 0}) or {}

    approval_required = bool(policy.get("approval_required") is True)
    override_approved = bool(policy.get("override_approved") is True)
    expires_at = str(policy.get("override_expires_at") or "").strip()

    if approval_required and not override_approved:
        return False, {"reason": "approval_required", "template_key": key}

    if expires_at and expires_at < now_iso:
        return False, {"reason": "approval_expired", "template_key": key, "override_expires_at": expires_at}

    return True, {
        "template_key": key,
        "actor": actor_id,
        "source": source_id,
        "policy": policy,
        "checked_at": now_iso,
    }


async def audit_override_write(*, template_key: str, actor: str, source: str, approved: bool, reason: str, metadata: dict | None = None) -> None:
    await db.email_override_audit_log.insert_one(
        {
            "audit_id": f"override_audit_{_now_iso()}_{template_key}",
            "template_key": _normalized(template_key),
            "actor": _normalized(actor),
            "source": _normalized(source),
            "approved": bool(approved),
            "reason": str(reason or "").strip().lower(),
            "metadata": metadata or {},
            "created_at": _now_iso(),
        }
    )
