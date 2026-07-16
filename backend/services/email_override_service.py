from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from routes.db import db
from utils.email_template_policy import can_write_subject_override, audit_override_write


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def write_subject_override(*, template_key: str, optimized_subject: str, actor: str, source: str, metadata: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any]]:
    """Single strict entrypoint for subject override writes.

    Enforces policy gate + audit trail for every writer path.
    """
    key = str(template_key or "").strip().lower()
    subj = str(optimized_subject or "").strip()
    if not key:
        return False, {"reason": "template_key_required"}
    if not subj:
        return False, {"reason": "optimized_subject_required", "template_key": key}

    allowed, gate = await can_write_subject_override(template_key=key, actor=actor, source=source)
    if not allowed:
        await audit_override_write(
            template_key=key,
            actor=actor,
            source=source,
            approved=False,
            reason=str(gate.get("reason") or "policy_blocked"),
            metadata={"optimized_subject": subj[:120], "gate": gate, **(metadata or {})},
        )
        return False, gate

    now_iso = _now_iso()
    await db.email_subject_overrides.update_one(
        {"template_type": key},
        {
            "$set": {
                "template_type": key,
                "email_type": key,
                "optimized_subject": subj,
                "subject_line": subj,
                "active": True,
                "source": source,
                "applied_at": now_iso,
                "updated_by": actor,
            },
            "$setOnInsert": {"created_at": now_iso, "created_by": actor},
        },
        upsert=True,
    )
    await audit_override_write(
        template_key=key,
        actor=actor,
        source=source,
        approved=True,
        reason="policy_gate_pass",
        metadata={"optimized_subject": subj[:120], **(metadata or {})},
    )
    return True, {"template_key": key, "source": source, "applied_at": now_iso}


async def deactivate_subject_override(*, template_key: str, actor: str, source: str, metadata: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any]]:
    key = str(template_key or "").strip().lower()
    if not key:
        return False, {"reason": "template_key_required"}

    now_iso = _now_iso()
    result = await db.email_subject_overrides.update_one(
        {"$or": [{"email_type": key}, {"template_type": key}]},
        {
            "$set": {
                "active": False,
                "reverted_at": now_iso,
                "reverted_by": actor,
                "revert_source": source,
            }
        },
    )
    await audit_override_write(
        template_key=key,
        actor=actor,
        source=source,
        approved=False,
        reason="manual_revert",
        metadata={"matched": int(result.modified_count), **(metadata or {})},
    )
    return bool(result.modified_count > 0), {"template_key": key, "matched": int(result.modified_count)}
