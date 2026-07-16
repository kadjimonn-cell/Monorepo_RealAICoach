"""Global monitor for admin-template recipient guardrails.

Detects and records any admin-only template email sent to known non-admin users.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging
import re
from collections import Counter
from typing import Any

from utils.email_service import (
    _ADMIN_ROLE_VALUES,
    get_admin_only_template_keys_effective,
    is_email_configured,
    send_catalog_template,
)

logger = logging.getLogger("admin_email_guardrail_monitor")

SCAN_COLLECTION = "admin_email_guardrail_scans"
STATE_COLLECTION = "admin_email_guardrail_monitor_state"
STATE_DOC_ID = "global_admin_template_recipient_guardrail"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _is_admin_user_doc(user_doc: dict[str, Any] | None) -> bool:
    if not user_doc:
        return False
    role = str(user_doc.get("role") or "").strip().lower()
    return bool(user_doc.get("is_admin")) or role in _ADMIN_ROLE_VALUES


async def _resolve_user_by_email(db: Any, email: str) -> dict[str, Any] | None:
    if not email:
        return None
    return await db.users.find_one(
        {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
        {"_id": 0, "email": 1, "is_admin": 1, "role": 1, "user_id": 1},
    )


async def _scan_admin_template_rows(
    db: Any,
    *,
    start_iso: str,
    end_iso: str,
    limit: int,
) -> dict[str, Any]:
    admin_templates = sorted(get_admin_only_template_keys_effective())

    rows = await db.email_sends.find(
        {
            "template_key": {"$in": admin_templates},
            "sent_at": {"$gte": start_iso, "$lt": end_iso},
        },
        {"_id": 0, "template_key": 1, "recipient": 1, "subject": 1, "sent_at": 1},
    ).sort("sent_at", -1).limit(max(1, min(limit, 100000))).to_list(max(1, min(limit, 100000)))

    recipients = sorted({_normalize_email(r.get("recipient")) for r in rows if r.get("recipient")})
    user_cache: dict[str, dict[str, Any] | None] = {}
    for email in recipients:
        user_cache[email] = await _resolve_user_by_email(db, email)

    violating_rows: list[dict[str, Any]] = []
    unknown_recipient_rows: list[dict[str, Any]] = []
    template_counter = Counter()
    non_admin_template_counter = Counter()

    for row in rows:
        template = str(row.get("template_key") or "").strip().lower()
        recipient = _normalize_email(row.get("recipient"))
        if not recipient:
            continue
        template_counter[template] += 1

        user_doc = user_cache.get(recipient)
        if not user_doc:
            unknown_recipient_rows.append(
                {
                    "sent_at": row.get("sent_at"),
                    "recipient": recipient,
                    "template_key": template,
                    "subject": row.get("subject"),
                    "reason": "recipient_not_found_in_users",
                }
            )
            continue

        if not _is_admin_user_doc(user_doc):
            non_admin_template_counter[template] += 1
            violating_rows.append(
                {
                    "sent_at": row.get("sent_at"),
                    "recipient": recipient,
                    "template_key": template,
                    "subject": row.get("subject"),
                    "user_id": user_doc.get("user_id"),
                    "role": user_doc.get("role"),
                    "is_admin": bool(user_doc.get("is_admin")),
                }
            )

    system_alert_non_admin = [
        v for v in violating_rows if str(v.get("template_key") or "").strip().lower() == "system_alert_admin"
    ]

    return {
        "admin_templates": admin_templates,
        "rows_scanned": len(rows),
        "distinct_recipients": len(recipients),
        "violations_total": len(violating_rows),
        "system_alert_admin_non_admin": len(system_alert_non_admin),
        "violating_rows": violating_rows,
        "system_alert_non_admin_rows": system_alert_non_admin,
        "unknown_recipient_rows": unknown_recipient_rows,
        "template_counts": dict(template_counter),
        "non_admin_template_counts": dict(non_admin_template_counter),
    }


async def deep_scan_admin_template_misroutes(
    db: Any,
    *,
    days: int = 30,
    limit: int = 50000,
) -> dict[str, Any]:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=max(1, min(days, 365)))

    scan = await _scan_admin_template_rows(
        db,
        start_iso=start_dt.isoformat(),
        end_iso=end_dt.isoformat(),
        limit=limit,
    )

    result = {
        "scan_type": "deep_scan",
        "scan_id": f"admin_guardrail_scan_{int(end_dt.timestamp())}",
        "window": {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "days": max(1, min(days, 365)),
        },
        **scan,
        "created_at": _utcnow_iso(),
    }

    await db[SCAN_COLLECTION].insert_one({**result})
    return result


async def run_incremental_admin_template_monitor(
    db: Any,
    *,
    fallback_lookback_minutes: int = 20,
    limit: int = 10000,
) -> dict[str, Any]:
    now_dt = datetime.now(timezone.utc)
    state = await db[STATE_COLLECTION].find_one({"_id": STATE_DOC_ID}, {"_id": 0}) or {}
    last_checked = _parse_iso(state.get("last_checked_at"))
    if not last_checked:
        last_checked = now_dt - timedelta(minutes=max(5, min(fallback_lookback_minutes, 720)))

    scan = await _scan_admin_template_rows(
        db,
        start_iso=last_checked.isoformat(),
        end_iso=now_dt.isoformat(),
        limit=limit,
    )

    result = {
        "scan_type": "incremental_monitor",
        "scan_id": f"admin_guardrail_monitor_{int(now_dt.timestamp())}",
        "window": {
            "start": last_checked.isoformat(),
            "end": now_dt.isoformat(),
        },
        **scan,
        "created_at": _utcnow_iso(),
    }

    await db[SCAN_COLLECTION].insert_one({**result})
    await db[STATE_COLLECTION].update_one(
        {"_id": STATE_DOC_ID},
        {
            "$set": {
                "last_checked_at": now_dt.isoformat(),
                "last_scan_id": result["scan_id"],
                "last_violations_total": result["violations_total"],
                "last_system_alert_admin_non_admin": result["system_alert_admin_non_admin"],
                "updated_at": _utcnow_iso(),
            }
        },
        upsert=True,
    )

    if result["violations_total"] > 0 and is_email_configured():
        try:
            admins = await db.users.find(
                {"is_admin": True, "email": {"$exists": True, "$ne": ""}},
                {"_id": 0, "email": 1},
            ).to_list(25)
            alert_desc = (
                f"Detected {result['violations_total']} admin-template recipient violations in the last monitor window. "
                f"system_alert_admin_non_admin={result['system_alert_admin_non_admin']}"
            )
            for admin in admins:
                email = _normalize_email(admin.get("email"))
                if not email:
                    continue
                await send_catalog_template(
                    recipient_email=email,
                    template_key="system_alert_admin",
                    alert_type="Admin Template Recipient Guardrail Violation",
                    severity="CRITICAL",
                    description=alert_desc,
                    component="email_guardrail_monitor",
                )
        except Exception as exc:
            logger.warning(f"admin email guardrail monitor alert send failed: {exc}")

    return result
