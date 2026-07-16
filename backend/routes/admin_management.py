"""Admin User & Ticket Management — Freeze, reset password, role management, ticket escalation."""

import os
import uuid
from fastapi import APIRouter, HTTPException, Request, Response
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
import secrets
import logging
import csv
import io

from .db import (
    db,
    require_admin,
    hash_password,
    ADMIN_EMAILS,
    ADMIN_OVERRIDE_EMAILS,
    FULL_ACCESS_EMAILS,
)
from utils.ws_manager import push_admin_alert
from utils.email_service import is_email_configured

# Canonical admin dependency alias for backward compatibility
_require_admin = require_admin

router = APIRouter(prefix="/admin/manage")
logger = logging.getLogger(__name__)


def _normalize_email(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _build_trusted_email_allowlist(extra_allowlist: list[str]) -> list[str]:
    trusted: set[str] = set()
    for source in (ADMIN_EMAILS, ADMIN_OVERRIDE_EMAILS, FULL_ACCESS_EMAILS):
        for email in source or []:
            normalized = _normalize_email(email)
            if normalized and "@" in normalized:
                trusted.add(normalized)

    env_allowlist = os.environ.get("TRUSTED_EMAIL_VERIFIED_ALLOWLIST", "")
    for raw in str(env_allowlist).split(","):
        normalized = _normalize_email(raw)
        if normalized and "@" in normalized:
            trusted.add(normalized)

    for value in extra_allowlist or []:
        normalized = _normalize_email(value)
        if normalized and "@" in normalized:
            trusted.add(normalized)

    return sorted(trusted)


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _ci_contains(value: str) -> dict:
    return {"$regex": re.escape(str(value or "").strip()), "$options": "i"}


async def _collect_email_delivery_ledger(
    *,
    user_query: str,
    event_query: str,
    idempotency_query: str,
    limit: int,
    anomaly_mode: bool = False,
    anomaly_window_hours: int = 24,
    anomaly_volume_threshold: int = 5,
):
    safe_limit = max(1, min(int(limit or 100), 500))
    user_q = str(user_query or "").strip().lower()
    event_q = str(event_query or "").strip().lower()
    idemp_q = str(idempotency_query or "").strip().lower()
    parsed_window_hours = 24 if anomaly_window_hours is None else int(anomaly_window_hours)
    parsed_volume_threshold = 5 if anomaly_volume_threshold is None else int(anomaly_volume_threshold)
    safe_window_hours = max(1, min(parsed_window_hours, 168))
    safe_volume_threshold = max(2, min(parsed_volume_threshold, 100))

    idem_filter: dict = {}
    if user_q:
        idem_filter["$or"] = [{"canonical_recipient": _ci_contains(user_q)}, {"recipient": _ci_contains(user_q)}]
    if event_q:
        idem_filter["template_key"] = _ci_contains(event_q)
    if idemp_q:
        idem_filter["idempotency_key"] = _ci_contains(idemp_q)

    idempotency_rows = (
        await db.email_delivery_idempotency.find(
            idem_filter,
            {
                "_id": 0,
                "idempotency_key": 1,
                "recipient": 1,
                "canonical_recipient": 1,
                "template_key": 1,
                "dedupe_seed": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .limit(safe_limit)
        .to_list(safe_limit)
    )

    ledger_entries = []
    seen_send_ids = set()

    for row in idempotency_rows:
        created_at = row.get("created_at")
        if isinstance(created_at, datetime):
            created_iso = created_at.astimezone(timezone.utc).isoformat()
            send_upper_iso = (created_at.astimezone(timezone.utc) + timedelta(hours=12)).isoformat()
        else:
            created_iso = str(created_at or "")
            parsed = _parse_iso_dt(created_iso)
            send_upper_iso = (parsed + timedelta(hours=12)).isoformat() if parsed else "9999-12-31T23:59:59+00:00"

        send_row = await db.email_sends.find_one(
            {
                "recipient": row.get("recipient"),
                "template_key": row.get("template_key"),
                "sent_at": {"$gte": created_iso, "$lte": send_upper_iso},
            },
            {"_id": 0, "email_id": 1, "subject": 1, "sent_at": 1},
            sort=[("sent_at", 1)],
        )

        if send_row and send_row.get("email_id"):
            seen_send_ids.add(str(send_row.get("email_id")))

        ledger_entries.append(
            {
                "timestamp": created_iso,
                "recipient": row.get("recipient"),
                "template_key": row.get("template_key"),
                "idempotency_key": row.get("idempotency_key"),
                "dedupe_seed": row.get("dedupe_seed"),
                "status": "sent" if send_row else "reserved_no_send",
                "email_id": (send_row or {}).get("email_id"),
                "subject": (send_row or {}).get("subject"),
                "sent_at": (send_row or {}).get("sent_at"),
                "source": "idempotency",
            }
        )

    send_filter: dict = {}
    if user_q:
        send_filter["recipient"] = _ci_contains(user_q)
    if event_q:
        send_filter["template_key"] = _ci_contains(event_q)

    send_rows = (
        await db.email_sends.find(
            send_filter,
            {
                "_id": 0,
                "email_id": 1,
                "recipient": 1,
                "template_key": 1,
                "subject": 1,
                "sent_at": 1,
            },
        )
        .sort("sent_at", -1)
        .limit(safe_limit)
        .to_list(safe_limit)
    )

    for row in send_rows:
        email_id = str(row.get("email_id") or "")
        if email_id and email_id in seen_send_ids:
            continue
        ledger_entries.append(
            {
                "timestamp": row.get("sent_at"),
                "recipient": row.get("recipient"),
                "template_key": row.get("template_key"),
                "idempotency_key": None,
                "dedupe_seed": None,
                "status": "sent_untracked",
                "email_id": row.get("email_id"),
                "subject": row.get("subject"),
                "sent_at": row.get("sent_at"),
                "source": "send_log",
            }
        )

    ledger_entries = sorted(
        ledger_entries,
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )[:safe_limit]

    duplicate_idempotency_rows: list[dict[str, Any]] = []
    high_volume_rows: list[dict[str, Any]] = []

    if anomaly_mode:
        duplicate_pipeline = [
            {"$match": {**idem_filter, "idempotency_key": {"$exists": True, "$nin": [None, ""]}}},
            {
                "$group": {
                    "_id": "$idempotency_key",
                    "count": {"$sum": 1},
                    "latest_created_at": {"$max": "$created_at"},
                    "recipient": {"$first": "$recipient"},
                    "template_key": {"$first": "$template_key"},
                }
            },
            {"$match": {"count": {"$gt": 1}}},
            {"$sort": {"count": -1, "latest_created_at": -1}},
            {"$limit": 100},
        ]
        duplicate_idempotency_docs = await db.email_delivery_idempotency.aggregate(duplicate_pipeline).to_list(100)
        for row in duplicate_idempotency_docs:
            latest = row.get("latest_created_at")
            if isinstance(latest, datetime):
                latest_iso = latest.astimezone(timezone.utc).isoformat()
            else:
                latest_iso = str(latest or "")
            duplicate_idempotency_rows.append(
                {
                    "idempotency_key": row.get("_id"),
                    "count": int(row.get("count") or 0),
                    "latest_created_at": latest_iso,
                    "recipient": row.get("recipient"),
                    "template_key": row.get("template_key"),
                }
            )

        since_dt = datetime.now(timezone.utc) - timedelta(hours=safe_window_hours)
        send_anomaly_filter: dict[str, Any] = {"sent_at": {"$gte": since_dt.isoformat()}}
        if user_q:
            send_anomaly_filter["recipient"] = _ci_contains(user_q)
        if event_q:
            send_anomaly_filter["template_key"] = _ci_contains(event_q)

        high_volume_pipeline = [
            {"$match": send_anomaly_filter},
            {
                "$group": {
                    "_id": {
                        "recipient": "$recipient",
                        "template_key": "$template_key",
                    },
                    "send_count": {"$sum": 1},
                    "latest_sent_at": {"$max": "$sent_at"},
                }
            },
            {"$match": {"send_count": {"$gte": safe_volume_threshold}}},
            {"$sort": {"send_count": -1, "latest_sent_at": -1}},
            {"$limit": 150},
        ]
        high_volume_docs = await db.email_sends.aggregate(high_volume_pipeline).to_list(150)
        for row in high_volume_docs:
            key = row.get("_id") or {}
            high_volume_rows.append(
                {
                    "recipient": key.get("recipient"),
                    "template_key": key.get("template_key"),
                    "send_count": int(row.get("send_count") or 0),
                    "window_hours": safe_window_hours,
                    "latest_sent_at": row.get("latest_sent_at"),
                }
            )

    duplicate_key_index = {
        str(item.get("idempotency_key") or "").strip().lower()
        for item in duplicate_idempotency_rows
        if str(item.get("idempotency_key") or "").strip()
    }
    high_volume_pair_index = {
        f"{str(item.get('recipient') or '').strip().lower()}::{str(item.get('template_key') or '').strip().lower()}"
        for item in high_volume_rows
    }

    flagged_rows = 0
    for row in ledger_entries:
        flags: list[str] = []
        idem_val = str(row.get("idempotency_key") or "").strip().lower()
        if idem_val and idem_val in duplicate_key_index:
            flags.append("duplicate_idempotency_key")

        pair_val = f"{str(row.get('recipient') or '').strip().lower()}::{str(row.get('template_key') or '').strip().lower()}"
        if pair_val in high_volume_pair_index:
            flags.append("high_volume_recipient_template")

        row["anomaly_flags"] = flags
        row["anomaly_level"] = "warning" if flags else "normal"
        if flags:
            flagged_rows += 1

    return {
        "entries": ledger_entries,
        "idempotency_matches": len(idempotency_rows),
        "send_matches": len(send_rows),
        "limit": safe_limit,
        "filters": {
            "user": user_q or None,
            "event": event_q or None,
            "idempotency_key": idemp_q or None,
        },
        "anomaly_mode": bool(anomaly_mode),
        "anomaly_window_hours": safe_window_hours,
        "anomaly_volume_threshold": safe_volume_threshold,
        "anomalies": {
            "duplicate_idempotency_keys": duplicate_idempotency_rows,
            "high_volume_recipient_templates": high_volume_rows,
            "total_flagged_rows": flagged_rows,
        },
    }


def _ticket_hours_open(ticket: dict) -> float:
    created_at = _parse_iso_dt(ticket.get("created_at"))
    if not created_at:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 3600)


def _compute_ticket_risk_heat(ticket: dict) -> dict:
    """Compute a deterministic ticket-risk heat value for UI badges + nudges."""
    priority = str(ticket.get("priority") or "medium").lower()
    status = str(ticket.get("status") or "open").lower()
    escalation_level = int(ticket.get("escalation_level") or 0)
    auto_escalated = bool(ticket.get("auto_escalated"))
    assigned_to = str(ticket.get("assigned_to") or "").strip()
    hours_open = _ticket_hours_open(ticket)
    sentiment = ((ticket.get("ai_classification") or {}).get("sentiment") or {})
    frustration = int(sentiment.get("frustration_level") or 0)
    mood = str(sentiment.get("mood") or "").lower()

    score = 0
    reasons: list[str] = []

    score += {
        "low": 6,
        "medium": 16,
        "high": 34,
        "urgent": 52,
        "critical": 62,
    }.get(priority, 16)

    score += {
        "open": 8,
        "pending": 12,
        "in_progress": 14,
        "escalated": 24,
        "reopened": 18,
    }.get(status, 0)

    if auto_escalated:
        score += 16
        reasons.append("auto_escalated")
    if escalation_level > 0:
        score += min(20, escalation_level * 6)
        reasons.append(f"escalation_level_{escalation_level}")

    # Aging pressure
    if hours_open >= 6:
        score += min(18, int(hours_open // 6) * 2)
        reasons.append("aging_ticket")

    # SLA pressure by priority band
    sla_target = 24
    if priority in {"high"}:
        sla_target = 12
    if priority in {"urgent", "critical"}:
        sla_target = 4

    if status not in {"resolved", "closed"}:
        if hours_open > sla_target:
            score += 22
            reasons.append("sla_breached")
        elif hours_open >= (0.75 * sla_target):
            score += 10
            reasons.append("sla_at_risk")

    if not assigned_to and status not in {"resolved", "closed"}:
        score += 8
        reasons.append("unassigned")

    if frustration > 0:
        score += min(20, frustration * 2)
        if frustration >= 7:
            reasons.append("high_customer_frustration")
    if mood in {"angry", "desperate"}:
        score += 8
        reasons.append(f"mood_{mood}")

    score = max(0, min(100, int(round(score))))
    level = "low"
    if score >= 85:
        level = "critical"
    elif score >= 60:
        level = "high"
    elif score >= 35:
        level = "medium"

    return {
        "score": score,
        "level": level,
        "label": level.upper(),
        "reasons": reasons[:5],
        "hours_open": round(hours_open, 1),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_ticket_nudges(ticket: dict, risk_heat: dict) -> list[dict]:
    """Build nudge payloads for a single ticket based on deterministic rules."""
    status = str(ticket.get("status") or "open").lower()
    if status in {"resolved", "closed"}:
        return []

    nudges: list[dict] = []
    level = risk_heat.get("level", "low")
    score = int(risk_heat.get("score") or 0)
    hours_open = float(risk_heat.get("hours_open") or 0)
    reasons = set(risk_heat.get("reasons") or [])
    ticket_number = ticket.get("ticket_number") or ticket.get("submission_id")

    if level in {"high", "critical"}:
        nudges.append(
            {
                "nudge_type": "risk_watch",
                "priority": "high" if level == "critical" else "medium",
                "title": "Ticket risk heat elevated",
                "message": f"{ticket_number} is now {level.upper()} risk ({score}/100).",
            }
        )

    if "sla_breached" in reasons:
        nudges.append(
            {
                "nudge_type": "sla_breach",
                "priority": "high",
                "title": "SLA breached",
                "message": f"{ticket_number} breached SLA and needs immediate owner action.",
            }
        )

    if (not str(ticket.get("assigned_to") or "").strip()) and hours_open >= 8:
        nudges.append(
            {
                "nudge_type": "assignment_needed",
                "priority": "medium",
                "title": "Unassigned aging ticket",
                "message": f"{ticket_number} is unassigned for {int(hours_open)}h. Route to an agent.",
            }
        )

    if "high_customer_frustration" in reasons:
        nudges.append(
            {
                "nudge_type": "sentiment_risk",
                "priority": "medium",
                "title": "Customer sentiment risk",
                "message": f"{ticket_number} shows high frustration sentiment. Prioritize empathetic response.",
            }
        )

    return nudges


async def run_support_proactive_nudges(trigger: str = "manual") -> dict:
    """Generate deterministic support nudges for at-risk tickets."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    bucket = f"{now.strftime('%Y%m%d')}-h{now.hour // 6}"

    scanned = 0
    generated = 0
    by_type: dict[str, int] = {}

    cursor = db.support_submissions.find(
        {"status": {"$nin": ["resolved", "closed"]}},
        {
            "_id": 0,
            "submission_id": 1,
            "ticket_number": 1,
            "subject": 1,
            "status": 1,
            "priority": 1,
            "assigned_to": 1,
            "created_at": 1,
            "auto_escalated": 1,
            "escalation_level": 1,
            "ai_classification": 1,
            "user_id": 1,
            "user_name": 1,
            "user_email": 1,
        },
    ).sort("created_at", -1).limit(1000)

    async for ticket in cursor:
        scanned += 1
        risk_heat = _compute_ticket_risk_heat(ticket)
        nudges = _build_ticket_nudges(ticket, risk_heat)
        for n in nudges:
            nudge_id = f"nudge_{uuid.uuid4().hex[:12]}"
            dedupe_key = f"{ticket.get('submission_id')}::{n['nudge_type']}::{bucket}"
            doc = {
                "nudge_id": nudge_id,
                "dedupe_key": dedupe_key,
                "ticket_id": ticket.get("submission_id"),
                "ticket_number": ticket.get("ticket_number") or ticket.get("submission_id"),
                "ticket_subject": ticket.get("subject") or "Ticket",
                "ticket_status": ticket.get("status") or "open",
                "ticket_priority": ticket.get("priority") or "medium",
                "assigned_to": ticket.get("assigned_to"),
                "user_id": ticket.get("user_id"),
                "user_name": ticket.get("user_name"),
                "user_email": ticket.get("user_email"),
                "nudge_type": n["nudge_type"],
                "priority": n["priority"],
                "title": n["title"],
                "message": n["message"],
                "risk_level": risk_heat.get("level"),
                "risk_score": int(risk_heat.get("score") or 0),
                "status": "open",
                "ack_note": "",
                "acknowledged_at": None,
                "acknowledged_by": None,
                "created_at": now_iso,
                "updated_at": now_iso,
                "trigger": trigger,
            }
            result = await db.support_proactive_nudges.update_one(
                {"dedupe_key": dedupe_key},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if result.upserted_id:
                generated += 1
                by_type[n["nudge_type"]] = by_type.get(n["nudge_type"], 0) + 1

    summary = {
        "ok": True,
        "trigger": trigger,
        "scanned": scanned,
        "generated": generated,
        "by_type": by_type,
        "generated_at": now_iso,
    }
    await db.support_proactive_nudge_runs.insert_one({**summary})

    if generated > 0:
        try:
            await push_admin_alert(
                "support_proactive_nudges",
                "Proactive support nudges generated",
                f"Generated {generated} support nudge(s) across {len(by_type)} type(s).",
                severity="warning",
                extra={"generated": generated, "by_type": by_type, "trigger": trigger},
            )
        except Exception:
            pass

    return summary


# ── User Management ──


@router.get("/users")
async def list_users(request: Request, page: int = 1, limit: int = 25, search: str = "", status: str = "all"):
    """List all users with filtering."""
    await _require_admin(request)
    query = {}
    if search:
        query["$or"] = [
            {"email": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"name": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"user_id": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]
    if status == "frozen":
        query["access_locked"] = True
    elif status == "active":
        query["access_locked"] = {"$ne": True}

    total = await db.users.count_documents(query)
    users = (
        await db.users.find(query, {"_id": 0, "password_hash": 0, "pin_hash": 0, "otp_hash": 0})
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )

    return {"users": users, "total": total, "page": page, "limit": limit, "pages": max(1, (total + limit - 1) // limit)}


@router.post("/users/{user_id}/freeze")
async def freeze_user(user_id: str, request: Request):
    """Freeze a user account."""
    admin = await _require_admin(request)
    body = await request.json()
    reason = body.get("reason", "Account frozen by admin")

    result = await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "access_locked": True,
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "frozen_reason": reason,
                "frozen_by": admin.user_id,
            }
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    # Invalidate all sessions
    await db.user_sessions.delete_many({"user_id": user_id})

    # Log
    await db.security_events.insert_one(
        {
            "user_id": user_id,
            "event_type": "account_frozen",
            "severity": "high",
            "details": {"reason": reason, "admin": admin.user_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    await push_admin_alert(
        "account_frozen",
        "Account Frozen",
        f"{target.get('email', user_id)} frozen: {reason}",
        severity="critical",
        extra={"user_id": user_id, "reason": reason},
    )

    return {"ok": True, "message": f"User {user_id} frozen"}


@router.post("/users/{user_id}/unfreeze")
async def unfreeze_user(user_id: str, request: Request):
    """Unfreeze a user account."""
    admin = await _require_admin(request)

    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"access_locked": False}, "$unset": {"frozen_at": "", "frozen_reason": "", "frozen_by": ""}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    await db.security_events.insert_one(
        {
            "user_id": user_id,
            "event_type": "account_unfrozen",
            "severity": "medium",
            "details": {"admin": admin.user_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    await push_admin_alert(
        "account_unfrozen",
        "Account Unfrozen",
        f"{target.get('email', user_id)} was unfrozen by {admin.email}",
        severity="info",
        extra={"user_id": user_id},
    )

    return {"ok": True, "message": f"User {user_id} unfrozen"}


@router.post("/users/email-verified/backfill")
async def trusted_email_verified_backfill(request: Request):
    """Backfill email_verified for trusted legacy accounts (admin-only).

    Body:
    {
      "mode": "dry_run" | "apply",
      "include_admins": true,
      "include_full_access": true,
      "extra_allowlist_emails": ["ops@example.com"],
      "limit": 2000
    }
    """
    admin = await _require_admin(request)
    body = await request.json()

    mode = str(body.get("mode") or "dry_run").strip().lower()
    if mode not in {"dry_run", "apply"}:
        raise HTTPException(status_code=400, detail="mode must be one of: dry_run, apply")

    include_admins = bool(body.get("include_admins", True))
    include_full_access = bool(body.get("include_full_access", True))
    extra_allowlist = body.get("extra_allowlist_emails") or []
    if not isinstance(extra_allowlist, list):
        raise HTTPException(status_code=400, detail="extra_allowlist_emails must be a list")

    try:
        limit = int(body.get("limit", 2000))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"limit must be integer: {exc}")
    limit = max(1, min(limit, 20000))

    trusted_email_allowlist = _build_trusted_email_allowlist(extra_allowlist)

    trusted_selector: list[dict] = []
    if include_admins:
        trusted_selector.append({"is_admin": True})
    if include_full_access:
        trusted_selector.append({"full_access": True})
    if trusted_email_allowlist:
        trusted_selector.append({"email": {"$in": trusted_email_allowlist}})

    if not trusted_selector:
        raise HTTPException(status_code=400, detail="No trusted selectors enabled for backfill")

    query = {
        "$and": [
            {"email": {"$exists": True, "$ne": ""}},
            {"email_verified": {"$ne": True}},
            {"$or": trusted_selector},
        ]
    }

    candidate_count = await db.users.count_documents(query)
    candidates = (
        await db.users.find(
            query,
            {
                "_id": 0,
                "user_id": 1,
                "email": 1,
                "name": 1,
                "is_admin": 1,
                "full_access": 1,
                "email_verified": 1,
                "created_at": 1,
                "last_login_at": 1,
            },
        )
        .sort("created_at", 1)
        .limit(limit)
        .to_list(limit)
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    run_id = f"email_verify_backfill_{uuid.uuid4().hex[:10]}"

    run_doc = {
        "run_id": run_id,
        "mode": mode,
        "triggered_by": admin.user_id,
        "triggered_by_email": admin.email,
        "triggered_at": now_iso,
        "candidate_count": candidate_count,
        "sample_size": len(candidates),
        "include_admins": include_admins,
        "include_full_access": include_full_access,
        "trusted_email_allowlist_size": len(trusted_email_allowlist),
        "trusted_email_allowlist_preview": trusted_email_allowlist[:50],
    }

    if mode == "dry_run":
        await db.email_verified_backfill_runs.insert_one({**run_doc, "status": "dry_run_complete"})
        return {
            "ok": True,
            "mode": mode,
            "run_id": run_id,
            "candidate_count": candidate_count,
            "sample_count": len(candidates),
            "candidates": candidates,
            "message": "Dry run complete. No user documents were modified.",
        }

    update_result = await db.users.update_many(
        query,
        {
            "$set": {
                "email_verified": True,
                "email_verified_at": now_iso,
                "email_verified_source": "trusted_legacy_backfill",
                "updated_at": now_iso,
            }
        },
    )

    applied_count = int(update_result.modified_count or 0)
    await db.email_verified_backfill_runs.insert_one(
        {
            **run_doc,
            "status": "apply_complete",
            "matched_count": int(update_result.matched_count or 0),
            "applied_count": applied_count,
        }
    )
    await db.security_events.insert_one(
        {
            "event_id": f"sec_{uuid.uuid4().hex[:10]}",
            "user_id": admin.user_id,
            "ip_address": request.client.host if request.client else None,
            "event_type": "email_verified_backfill_apply",
            "risk_level": "medium",
            "timestamp": now_iso,
            "details": {
                "run_id": run_id,
                "applied_count": applied_count,
                "candidate_count": candidate_count,
                "include_admins": include_admins,
                "include_full_access": include_full_access,
            },
        }
    )

    return {
        "ok": True,
        "mode": mode,
        "run_id": run_id,
        "candidate_count": candidate_count,
        "applied_count": applied_count,
        "message": "Trusted legacy email_verified backfill applied.",
    }


@router.get("/users/email-verified/backfill/runs")
async def trusted_email_verified_backfill_runs(request: Request, limit: int = 25, mode: str = ""):
    """List trusted email_verified backfill run history (admin-only)."""
    await _require_admin(request)
    safe_limit = max(1, min(int(limit or 25), 500))
    mode_filter = str(mode or "").strip().lower()

    query: dict = {}
    if mode_filter in {"dry_run", "apply"}:
        query["mode"] = mode_filter

    total = await db.email_verified_backfill_runs.count_documents(query)
    runs = (
        await db.email_verified_backfill_runs.find(
            query,
            {
                "_id": 0,
                "run_id": 1,
                "mode": 1,
                "status": 1,
                "triggered_by": 1,
                "triggered_by_email": 1,
                "triggered_at": 1,
                "candidate_count": 1,
                "sample_size": 1,
                "matched_count": 1,
                "applied_count": 1,
                "include_admins": 1,
                "include_full_access": 1,
                "trusted_email_allowlist_size": 1,
                "trusted_email_allowlist_preview": 1,
            },
        )
        .sort("triggered_at", -1)
        .limit(safe_limit)
        .to_list(safe_limit)
    )

    return {
        "ok": True,
        "total": total,
        "limit": safe_limit,
        "mode_filter": mode_filter or None,
        "runs": runs,
    }


@router.get("/users/email-verified/backfill/runs.csv")
async def trusted_email_verified_backfill_runs_csv(request: Request, limit: int = 200, mode: str = ""):
    """Export trusted email_verified backfill run history CSV (admin-only)."""
    await _require_admin(request)
    safe_limit = max(1, min(int(limit or 200), 2000))
    mode_filter = str(mode or "").strip().lower()

    query: dict = {}
    if mode_filter in {"dry_run", "apply"}:
        query["mode"] = mode_filter

    rows = (
        await db.email_verified_backfill_runs.find(
            query,
            {
                "_id": 0,
                "run_id": 1,
                "mode": 1,
                "status": 1,
                "triggered_by": 1,
                "triggered_by_email": 1,
                "triggered_at": 1,
                "candidate_count": 1,
                "sample_size": 1,
                "matched_count": 1,
                "applied_count": 1,
                "include_admins": 1,
                "include_full_access": 1,
                "trusted_email_allowlist_size": 1,
                "trusted_email_allowlist_preview": 1,
            },
        )
        .sort("triggered_at", -1)
        .limit(safe_limit)
        .to_list(safe_limit)
    )

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "run_id",
            "mode",
            "status",
            "triggered_by",
            "triggered_by_email",
            "triggered_at",
            "candidate_count",
            "sample_size",
            "matched_count",
            "applied_count",
            "include_admins",
            "include_full_access",
            "trusted_email_allowlist_size",
            "trusted_email_allowlist_preview",
        ]
    )

    for row in rows:
        writer.writerow(
            [
                row.get("run_id", ""),
                row.get("mode", ""),
                row.get("status", ""),
                row.get("triggered_by", ""),
                row.get("triggered_by_email", ""),
                row.get("triggered_at", ""),
                int(row.get("candidate_count") or 0),
                int(row.get("sample_size") or 0),
                int(row.get("matched_count") or 0),
                int(row.get("applied_count") or 0),
                bool(row.get("include_admins")),
                bool(row.get("include_full_access")),
                int(row.get("trusted_email_allowlist_size") or 0),
                "|".join([str(x) for x in (row.get("trusted_email_allowlist_preview") or [])]),
            ]
        )

    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    headers = {
        "Content-Disposition": f'attachment; filename="email_verified_backfill_runs_{now_stamp}.csv"'
    }
    return Response(content=out.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/email-delivery-ledger")
async def email_delivery_ledger(
    request: Request,
    user: str = "",
    event: str = "",
    idempotency_key: str = "",
    limit: int = 100,
    anomaly_mode: bool = False,
    anomaly_window_hours: int = 24,
    anomaly_volume_threshold: int = 5,
):
    """Admin-only email delivery ledger for one-click audit and support triage."""
    await _require_admin(request)
    payload = await _collect_email_delivery_ledger(
        user_query=user,
        event_query=event,
        idempotency_query=idempotency_key,
        limit=limit,
        anomaly_mode=anomaly_mode,
        anomaly_window_hours=anomaly_window_hours,
        anomaly_volume_threshold=anomaly_volume_threshold,
    )
    return {
        "ok": True,
        **payload,
    }


@router.get("/email-delivery-ledger.csv")
async def email_delivery_ledger_csv(
    request: Request,
    user: str = "",
    event: str = "",
    idempotency_key: str = "",
    limit: int = 500,
    anomaly_mode: bool = False,
    anomaly_window_hours: int = 24,
    anomaly_volume_threshold: int = 5,
):
    """Export email delivery ledger rows as CSV (admin-only)."""
    await _require_admin(request)
    payload = await _collect_email_delivery_ledger(
        user_query=user,
        event_query=event,
        idempotency_query=idempotency_key,
        limit=limit,
        anomaly_mode=anomaly_mode,
        anomaly_window_hours=anomaly_window_hours,
        anomaly_volume_threshold=anomaly_volume_threshold,
    )

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "timestamp",
            "recipient",
            "template_key",
            "idempotency_key",
            "dedupe_seed",
            "status",
            "email_id",
            "subject",
            "sent_at",
            "source",
            "anomaly_level",
            "anomaly_flags",
        ]
    )

    for row in payload.get("entries", []):
        writer.writerow(
            [
                row.get("timestamp", ""),
                row.get("recipient", ""),
                row.get("template_key", ""),
                row.get("idempotency_key", ""),
                row.get("dedupe_seed", ""),
                row.get("status", ""),
                row.get("email_id", ""),
                row.get("subject", ""),
                row.get("sent_at", ""),
                row.get("source", ""),
                row.get("anomaly_level", "normal"),
                "|".join([str(flag) for flag in (row.get("anomaly_flags") or [])]),
            ]
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    headers = {"Content-Disposition": f'attachment; filename="email_delivery_ledger_{stamp}.csv"'}
    return Response(content=out.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@router.post("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: str, request: Request):
    """Admin force-reset a user's password. Returns temporary password."""
    admin = await _require_admin(request)

    temp_password = secrets.token_urlsafe(10)
    password_hash = hash_password(temp_password)

    result = await db.users.update_one(
        {"user_id": user_id}, {"$set": {"password_hash": password_hash, "must_change_password": True}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    # Invalidate sessions
    await db.user_sessions.delete_many({"user_id": user_id})

    await db.security_events.insert_one(
        {
            "user_id": user_id,
            "event_type": "admin_password_reset",
            "severity": "high",
            "details": {"admin": admin.user_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    if target and target.get("email") and is_email_configured():
        try:
            changed_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=target["email"],
                template_key="password_changed",
                user_name=target.get("email"),
                changed_at=changed_at,
            )
        except Exception as exc:
            logger.error(f"Admin password reset notification email failed: {exc}")

    await push_admin_alert(
        "password_reset",
        "Password Reset",
        f"Password reset for {target.get('email', user_id)} by {admin.email}",
        severity="warning",
        extra={"user_id": user_id},
    )

    return {"ok": True, "temp_password": temp_password, "message": "Password reset. User must change on next login."}


@router.post("/users/{user_id}/role")
async def update_user_role(user_id: str, request: Request):
    """Update user role and permissions."""
    admin = await _require_admin(request)
    body = await request.json()
    role = body.get("role", "")
    is_admin = body.get("is_admin", False)
    full_access = body.get("full_access", False)

    if role not in ("admin", "user", "moderator", "employer", "support"):
        raise HTTPException(status_code=400, detail="Invalid role")

    if full_access and not is_admin:
        raise HTTPException(status_code=400, detail="full_access is restricted to admin accounts only")

    update = {"role": role, "is_admin": is_admin, "full_access": bool(is_admin and full_access)}
    result = await db.users.update_one({"user_id": user_id}, {"$set": update})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found or no changes")

    await db.security_events.insert_one(
        {
            "user_id": user_id,
            "event_type": "role_changed",
            "severity": "high",
            "details": {"role": role, "is_admin": is_admin, "admin": admin.user_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
    await push_admin_alert(
        "role_changed",
        "Role Changed",
        f"{target.get('email', user_id)} role changed to {role} by {admin.email}",
        severity="warning",
        extra={"user_id": user_id, "role": role, "is_admin": is_admin},
    )

    # Notify the user about the admin action on their account
    if target and target.get("email"):
        try:
            from utils.email_service import send_catalog_template, is_email_configured
            if is_email_configured():
                await send_catalog_template(
                    recipient_email=target["email"],
                    template_key="admin_account_action",
                    user_name=target.get("name", target.get("email", "")),
                    action="role change",
                    action_details=f"Your account role has been updated to: {role}.",
                    performed_by="Platform Admin",
                )
        except Exception:
            pass

    return {"ok": True, "message": f"User role updated to {role}"}


@router.get("/users/{user_id}/login-logs")
async def get_user_login_logs(user_id: str, request: Request):
    """Get login history for a specific user."""
    await _require_admin(request)
    events = (
        await db.security_events.find(
            {
                "user_id": user_id,
                "event_type": {
                    "$in": [
                        "login_success",
                        "login_failed",
                        "account_frozen",
                        "account_unfrozen",
                        "admin_password_reset",
                        "role_changed",
                    ]
                },
            },
            {"_id": 0},
        )
        .sort("timestamp", -1)
        .limit(50)
        .to_list(50)
    )
    return {"events": events}


# ── Ticket Management ──


@router.get("/tickets")
async def list_tickets(request: Request, status: str = "all", priority: str = "all", page: int = 1, limit: int = 25):
    """List all support tickets with filtering."""
    await _require_admin(request)
    query = {}
    if status != "all":
        query["status"] = status
    if priority != "all":
        query["priority"] = priority

    total = await db.support_submissions.count_documents(query)
    tickets = (
        await db.support_submissions.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )

    # Enrich with user info
    for t in tickets:
        uid = t.get("user_id", "")
        if uid:
            u = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "email": 1})
            if u:
                t["user_name"] = u.get("name", "")
                t["user_email"] = u.get("email", "")
        t["risk_heat"] = _compute_ticket_risk_heat(t)

    return {"tickets": tickets, "total": total, "page": page, "limit": limit}


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, request: Request):
    """Get a single ticket with full history."""
    await _require_admin(request)
    ticket = await db.support_submissions.find_one({"submission_id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    uid = ticket.get("user_id", "")
    if uid:
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "email": 1})
        if u:
            ticket["user_name"] = u.get("name", "")
            ticket["user_email"] = u.get("email", "")

    ticket["risk_heat"] = _compute_ticket_risk_heat(ticket)

    return ticket


@router.post("/tickets/{ticket_id}/update")
async def update_ticket(ticket_id: str, request: Request):
    """Update ticket: status, priority, assign staff, add note."""
    admin = await _require_admin(request)
    body = await request.json()

    update: dict = {"updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": admin.user_id}
    push: dict = {}

    if "status" in body:
        s = body["status"]
        if s not in ("open", "pending", "in_progress", "escalated", "resolved", "closed", "reopened"):
            raise HTTPException(status_code=400, detail="Invalid status")
        update["status"] = s
        if s == "resolved":
            update["resolved_at"] = datetime.now(timezone.utc).isoformat()

    if "priority" in body:
        p = body["priority"]
        if p not in ("low", "medium", "high", "urgent"):
            raise HTTPException(status_code=400, detail="Invalid priority")
        update["priority"] = p

    if "assigned_to" in body:
        update["assigned_to"] = body["assigned_to"]

    if "note" in body:
        push["history"] = {
            "action": body.get("action", "note"),
            "note": body["note"],
            "by": admin.user_id,
            "by_name": admin.name,
            "at": datetime.now(timezone.utc).isoformat(),
        }

    ops: dict = {"$set": update}
    if push:
        ops["$push"] = push

    result = await db.support_submissions.update_one({"submission_id": ticket_id}, ops)
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Notify user of status change
    ticket = await db.support_submissions.find_one(
        {"submission_id": ticket_id}, {"_id": 0, "user_id": 1, "ticket_number": 1}
    )
    if ticket and ticket.get("user_id"):
        tnum = ticket.get("ticket_number", ticket_id[:8])
        try:
            from routes.notification_engine import emit_notification

            await emit_notification(
                user_id=ticket["user_id"],
                notif_type="ticket_status_update",
                title=f"Ticket {tnum} Updated",
                body=f"Status changed to: {update.get('status', 'updated')}",
                action_url="/my-tickets",
                metadata={"ticket_number": tnum, "submission_id": ticket_id},
            )
        except Exception:
            await db.notifications.insert_one(
                {
                    "notification_id": f"notif_{secrets.token_hex(6)}",
                    "user_id": ticket["user_id"],
                    "title": f"Ticket {tnum} Updated",
                    "body": f"Status: {update.get('status', 'updated')}",
                    "type": "ticket_status_update",
                    "read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    # Auto-trigger feedback survey when ticket is resolved/closed
    if body.get("status") in ("resolved", "closed") and ticket and ticket.get("user_id"):
        try:
            from routes.ticket_feedback import trigger_feedback_survey
            import asyncio
            asyncio.ensure_future(trigger_feedback_survey(
                ticket_id, ticket["user_id"], ticket.get("ticket_number", ticket_id[:8])
            ))
        except Exception:
            pass

    return {"ok": True, "message": "Ticket updated"}


@router.post("/tickets/{ticket_id}/reply")
async def reply_ticket(ticket_id: str, request: Request):
    """Admin reply to a ticket."""
    admin = await _require_admin(request)
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message required")

    update = {
        "$set": {"status": "in_progress", "updated_at": datetime.now(timezone.utc).isoformat()},
        "$push": {
            "reply_logs": {
                "from": admin.email,
                "from_name": admin.name,
                "message": message,
                "role": "admin",
                "at": datetime.now(timezone.utc).isoformat(),
            },
            "history": {
                "action": "admin_reply",
                "note": message[:100],
                "by": admin.user_id,
                "by_name": admin.name,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        },
    }

    result = await db.support_submissions.update_one({"submission_id": ticket_id}, update)
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Notify user
    ticket = await db.support_submissions.find_one(
        {"submission_id": ticket_id}, {"_id": 0, "user_id": 1, "user_email": 1, "ticket_number": 1}
    )
    if ticket:
        uid = ticket.get("user_id", "")
        tnum = ticket.get("ticket_number", ticket_id[:8])
        if uid:
            try:
                from routes.notification_engine import emit_notification

                await emit_notification(
                    user_id=uid,
                    notif_type="ticket_admin_reply",
                    title=f"Reply on ticket {tnum}",
                    body=message[:100],
                    action_url="/my-tickets",
                    metadata={"ticket_number": tnum, "submission_id": ticket_id},
                )
            except Exception:
                await db.notifications.insert_one(
                    {
                        "notification_id": f"notif_{secrets.token_hex(6)}",
                        "user_id": uid,
                        "title": f"Reply on ticket {tnum}",
                        "body": message[:100],
                        "type": "ticket_admin_reply",
                        "read": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

        # Send email notification with Reply CTA
        try:
            from utils.email_service import send_email as send_email_fn
            from utils.email_service import render_email_logo

            user_doc = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1, "name": 1})
            if user_doc:
                user_email = user_doc["email"]
                user_name = user_doc.get("name", "User")
                frontend_url = os.environ.get("FRONTEND_BASE_URL", "")
                reply_link = f"{frontend_url}/my-tickets" if frontend_url else ""
                subject_line = ticket.get("subject", "Support Request")
                logo_html = render_email_logo(variant="support")

                reply_cta = ""
                if reply_link:
                    reply_cta = f"""
                    <div style="text-align:center;margin-top:24px;">
                      <a href="{reply_link}" style="display:inline-block;padding:12px 32px;background:#3B82F6;color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;">Reply to this message</a>
                    </div>
                    <p style="text-align:center;color:#94A3B8;font-size:11px;margin-top:10px;">Click above to view and reply to your ticket</p>"""

                html = f"""
                <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:520px;margin:0 auto;padding:32px 16px;background:#0B0F1A;">
                  <div style="border-radius:20px;overflow:hidden;border:1px solid #1E293B;">
                    <div style="background:linear-gradient(135deg,#0ea5e9,#6366f1);padding:36px 28px 28px;">
                      {logo_html}
                      <div style="color:rgba(255,255,255,0.7);font-size:12px;margin-bottom:14px;">RealAICoach &middot; Support</div>
                      <h2 style="color:#FFFFFF;font-size:20px;font-weight:800;margin:0 0 6px;">Support Reply</h2>
                      <p style="color:rgba(255,255,255,0.82);font-size:13px;margin:0;">Ticket #{tnum} — {subject_line[:60]}</p>
                    </div>
                    <div style="background:#111827;padding:24px 28px;">
                      <div style="background:#0F172A;border-left:3px solid #3B82F6;border-radius:0 10px 10px 0;padding:16px;margin-bottom:20px;">
                        <div style="white-space:pre-line;color:#CBD5E1;font-size:14px;line-height:1.7;">{message[:500]}</div>
                      </div>
                      {reply_cta}
                    </div>
                  </div>
                  <p style="text-align:center;color:#475569;font-size:11px;margin-top:16px;">RealAICoach Support</p>
                </div>"""
                await send_email_fn(
                    recipient_email=user_email,
                    subject=f"Re: {subject_line} [{tnum}]",
                    content=html,
                    recipient_name=user_name,
                )
        except Exception as exc:
            logger.error(f"Email notification for ticket reply failed: {exc}")

    return {"ok": True, "message": "Reply sent"}


# ── Ticket Stats ──


@router.get("/tickets/stats/overview")
async def ticket_stats(request: Request):
    """Get ticket statistics."""
    await _require_admin(request)
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    results = await db.support_submissions.aggregate(pipeline).to_list(20)
    by_status = {r["_id"]: r["count"] for r in results if r["_id"]}

    priority_pipeline = [{"$group": {"_id": "$priority", "count": {"$sum": 1}}}]
    priority_results = await db.support_submissions.aggregate(priority_pipeline).to_list(20)
    by_priority = {r["_id"]: r["count"] for r in priority_results if r["_id"]}

    total = await db.support_submissions.count_documents({})

    risk_heat = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    active_cursor = db.support_submissions.find(
        {"status": {"$nin": ["resolved", "closed"]}},
        {
            "_id": 0,
            "status": 1,
            "priority": 1,
            "created_at": 1,
            "assigned_to": 1,
            "auto_escalated": 1,
            "escalation_level": 1,
            "ai_classification": 1,
        },
    ).limit(1000)
    async for t in active_cursor:
        lvl = _compute_ticket_risk_heat(t).get("level", "low")
        if lvl in risk_heat:
            risk_heat[lvl] += 1

    return {
        "total": total,
        "by_status": by_status,
        "by_priority": by_priority,
        "open": by_status.get("open", 0) + by_status.get("reopened", 0),
        "pending": by_status.get("pending", 0) + by_status.get("in_progress", 0),
        "resolved": by_status.get("resolved", 0) + by_status.get("closed", 0),
        "escalated": by_status.get("escalated", 0),
        "risk_heat": risk_heat,
        "risk_high_or_critical": int(risk_heat.get("high", 0)) + int(risk_heat.get("critical", 0)),
    }


@router.get("/proactive-nudges")
async def list_ticket_proactive_nudges(
    request: Request,
    status: str = "open",
    limit: int = 50,
    ticket_id: str = "",
):
    """List support proactive nudges for admin triage."""
    await _require_admin(request)

    q: dict = {}
    if status != "all":
        q["status"] = status
    if ticket_id:
        q["ticket_id"] = ticket_id

    items = (
        await db.support_proactive_nudges.find(q, {"_id": 0})
        .sort("created_at", -1)
        .limit(max(1, min(limit, 200)))
        .to_list(max(1, min(limit, 200)))
    )
    total = await db.support_proactive_nudges.count_documents(q)
    open_count = await db.support_proactive_nudges.count_documents({"status": "open"})
    ack_count = await db.support_proactive_nudges.count_documents({"status": "acknowledged"})

    return {
        "items": items,
        "total": total,
        "open": open_count,
        "acknowledged": ack_count,
    }


@router.post("/proactive-nudges/run-now")
async def run_ticket_proactive_nudges_now(request: Request):
    """Admin action: run proactive nudge generator immediately."""
    await _require_admin(request)
    return await run_support_proactive_nudges(trigger="manual_admin")


@router.post("/proactive-nudges/{nudge_id}/ack")
async def acknowledge_ticket_proactive_nudge(nudge_id: str, request: Request):
    """Mark a proactive nudge as acknowledged."""
    admin = await _require_admin(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    ack_note = str((body or {}).get("note") or "").strip()[:400]
    now_iso = datetime.now(timezone.utc).isoformat()

    result = await db.support_proactive_nudges.update_one(
        {"nudge_id": nudge_id},
        {
            "$set": {
                "status": "acknowledged",
                "acknowledged_at": now_iso,
                "acknowledged_by": admin.email,
                "ack_note": ack_note,
                "updated_at": now_iso,
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Nudge not found")
    return {"ok": True, "nudge_id": nudge_id, "acknowledged_at": now_iso, "acknowledged_by": admin.email}


# ── AI Reply Suggestion ──


@router.post("/tickets/{ticket_id}/ai-suggest")
async def ai_suggest_reply(ticket_id: str, request: Request):
    """Generate AI-powered reply suggestion for a support ticket."""
    admin = await _require_admin(request)
    body = await request.json()
    tone = body.get("tone", "professional")

    ticket = await db.support_submissions.find_one({"submission_id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Build context from ticket
    subject = ticket.get("subject", ticket.get("type", "Support Request"))
    message = ticket.get("message", ticket.get("content", ticket.get("feedback", "")))
    user_name = ticket.get("user_name", ticket.get("user_email", "User"))
    status = ticket.get("status", "open")
    priority = ticket.get("priority", "medium")
    reply_logs = ticket.get("reply_logs", [])

    conversation_history = ""
    for r in reply_logs[-5:]:
        role_label = "Admin" if r.get("role") == "admin" else "User"
        conversation_history += f"\n{role_label} ({r.get('from_name', 'Unknown')}): {r.get('message', '')}"

    prompt = f"""You are a professional customer support agent for RealAICoach, an AI coaching platform.
Generate a helpful, {tone} reply for the following support ticket.

Ticket Subject: {subject}
User: {user_name}
Status: {status}
Priority: {priority}
User's Message: {message}
{f"Previous conversation:{conversation_history}" if conversation_history else ""}

Requirements:
- Be empathetic and solution-oriented
- Address the user's concern directly
- Provide actionable next steps if applicable
- Keep the response concise but thorough (2-4 paragraphs max)
- Use the user's name when appropriate
- Tone: {tone}

Reply:"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"support-{uuid.uuid4().hex[:8]}",
            system_message="You are a professional customer support agent for RealAICoach, an AI coaching platform. Generate helpful, solution-oriented replies.",
        ).with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))
        suggestion = response.strip()

        # Log AI suggestion
        await db.support_submissions.update_one(
            {"submission_id": ticket_id},
            {
                "$push": {
                    "ai_suggestions": {
                        "suggestion": suggestion,
                        "tone": tone,
                        "generated_by": admin.user_id,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    }
                }
            },
        )

        return {"suggestion": suggestion, "tone": tone}
    except Exception as exc:
        logger.error(f"AI suggestion failed for ticket {ticket_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"AI suggestion failed: {str(exc)}")


# ── Internal Notes ──


@router.post("/tickets/{ticket_id}/internal-note")
async def add_internal_note(ticket_id: str, request: Request):
    """Add an internal note to a ticket (only visible to admins)."""
    admin = await _require_admin(request)
    body = await request.json()
    note = body.get("note", "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Note content required")

    note_entry = {
        "note_id": f"note_{secrets.token_hex(6)}",
        "note": note,
        "by": admin.user_id,
        "by_name": admin.name,
        "by_email": admin.email,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db.support_submissions.update_one(
        {"submission_id": ticket_id},
        {"$push": {"internal_notes": note_entry}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return {"ok": True, "note": note_entry}


@router.delete("/tickets/{ticket_id}/internal-note/{note_id}")
async def delete_internal_note(ticket_id: str, note_id: str, request: Request):
    """Delete an internal note from a ticket."""
    await _require_admin(request)
    result = await db.support_submissions.update_one(
        {"submission_id": ticket_id}, {"$pull": {"internal_notes": {"note_id": note_id}}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


# ── Canned Responses ──


@router.get("/canned-responses")
async def list_canned_responses(request: Request):
    """List all canned responses for quick ticket replies."""
    await _require_admin(request)
    responses = await db.canned_responses.find({}, {"_id": 0}).sort("usage_count", -1).to_list(100)
    return {"responses": responses}


@router.post("/canned-responses")
async def create_canned_response(request: Request):
    """Create a new canned response."""
    admin = await _require_admin(request)
    body = await request.json()
    title = body.get("title", "").strip()
    content = body.get("content", "").strip()
    category = body.get("category", "general")

    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and content required")

    response_doc = {
        "response_id": f"cr_{secrets.token_hex(6)}",
        "title": title,
        "content": content,
        "category": category,
        "created_by": admin.user_id,
        "created_by_name": admin.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "usage_count": 0,
    }
    await db.canned_responses.insert_one(response_doc)
    del response_doc["_id"]
    return {"ok": True, "response": response_doc}


@router.delete("/canned-responses/{response_id}")
async def delete_canned_response(response_id: str, request: Request):
    """Delete a canned response."""
    await _require_admin(request)
    result = await db.canned_responses.delete_one({"response_id": response_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Response not found")
    return {"ok": True}


@router.post("/canned-responses/{response_id}/use")
async def use_canned_response(response_id: str, request: Request):
    """Increment usage count when a canned response is used."""
    await _require_admin(request)
    await db.canned_responses.update_one(
        {"response_id": response_id},
        {"$inc": {"usage_count": 1}, "$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


# ── User Context for Ticket ──


@router.get("/tickets/{ticket_id}/user-context")
async def get_ticket_user_context(ticket_id: str, request: Request):
    """Get user context for a support ticket (previous tickets, account info)."""
    await _require_admin(request)

    ticket = await db.support_submissions.find_one({"submission_id": ticket_id}, {"_id": 0, "user_id": 1})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    uid = ticket.get("user_id", "")
    if not uid:
        return {"user": None, "previous_tickets": [], "stats": {}}

    user = await db.users.find_one(
        {"user_id": uid},
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "name": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "full_access": 1,
            "roles": 1,
            "created_at": 1,
            "email_verified": 1,
        },
    )

    # Previous tickets
    prev_tickets = (
        await db.support_submissions.find(
            {"user_id": uid},
            {
                "_id": 0,
                "submission_id": 1,
                "subject": 1,
                "type": 1,
                "status": 1,
                "priority": 1,
                "created_at": 1,
                "ticket_number": 1,
            },
        )
        .sort("created_at", -1)
        .limit(10)
        .to_list(10)
    )

    # Stats
    total_tickets = await db.support_submissions.count_documents({"user_id": uid})
    resolved = await db.support_submissions.count_documents({"user_id": uid, "status": {"$in": ["resolved", "closed"]}})

    return {
        "user": user,
        "previous_tickets": prev_tickets,
        "stats": {
            "total_tickets": total_tickets,
            "resolved": resolved,
            "open": total_tickets - resolved,
        },
    }


# ── System Health ──


@router.get("/system/health")
async def system_health(request: Request):
    """Get system health metrics."""
    await _require_admin(request)
    import time

    # DB ping
    start = time.time()
    await db.command("ping")
    db_latency = round((time.time() - start) * 1000, 1)

    # Collection stats
    collections = await db.list_collection_names()
    col_stats = {}
    for c in collections[:20]:
        try:
            count = await db[c].estimated_document_count()
            col_stats[c] = count
        except Exception:
            pass

    # Recent errors
    recent_errors = (
        await db.security_events.find(
            {
                "severity": {"$in": ["high", "critical"]},
                "timestamp": {
                    "$gte": (datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=24)).isoformat()
                },
            },
            {"_id": 0},
        )
        .sort("timestamp", -1)
        .limit(20)
        .to_list(20)
    )

    # Active sessions
    active_sessions = await db.user_sessions.count_documents({"expires_at": {"$gte": datetime.now(timezone.utc)}})

    # User stats
    total_users = await db.users.count_documents({})
    active_users_24h = await db.security_events.distinct(
        "user_id",
        {
            "event_type": "login_success",
            "timestamp": {
                "$gte": (datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=24)).isoformat()
            },
        },
    )

    return {
        "status": "healthy",
        "db_latency_ms": db_latency,
        "collections": col_stats,
        "total_collections": len(collections),
        "active_sessions": active_sessions,
        "total_users": total_users,
        "active_users_24h": len(active_users_24h),
        "recent_errors": recent_errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Security Overview ──


@router.get("/security/overview")
async def security_overview(request: Request):
    """Get security monitoring overview."""
    await _require_admin(request)
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    # Failed logins 24h
    failed_24h = await db.security_events.count_documents(
        {"event_type": "login_failed", "timestamp": {"$gte": day_ago}}
    )

    # Successful logins 24h
    success_24h = await db.security_events.count_documents(
        {"event_type": "login_success", "timestamp": {"$gte": day_ago}}
    )

    # Frozen accounts
    frozen = await db.users.count_documents({"access_locked": True})

    # Suspicious events 7d
    suspicious_7d = await db.security_events.count_documents(
        {
            "event_type": {
                "$in": ["suspicious_login", "blocked_ip", "blocked_user", "admin_rate_limit", "jwt_invalid"]
            },
            "timestamp": {"$gte": week_ago},
        }
    )

    # Recent audit log
    audit = (
        await db.security_events.find({"timestamp": {"$gte": day_ago}}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(50)
        .to_list(50)
    )

    # Daily event counts for chart (7 days)
    daily_counts = []
    for i in range(7):
        day_start = (now - timedelta(days=i + 1)).isoformat()
        day_end = (now - timedelta(days=i)).isoformat()
        count = await db.security_events.count_documents({"timestamp": {"$gte": day_start, "$lt": day_end}})
        daily_counts.append({"day": (now - timedelta(days=i)).strftime("%a"), "count": count})
    daily_counts.reverse()

    return {
        "failed_logins_24h": failed_24h,
        "successful_logins_24h": success_24h,
        "frozen_accounts": frozen,
        "suspicious_events_7d": suspicious_7d,
        "recent_audit": audit,
        "daily_events": daily_counts,
    }


# ── AI Resolution Analytics ──


@router.get("/ai-resolution/analytics")
async def ai_resolution_analytics(request: Request):
    """Get comprehensive AI resolution analytics for the Smart Resolution Dashboard."""
    await _require_admin(request)

    pipeline_total = [
        {
            "$facet": {
                "by_status": [{"$group": {"_id": "$status", "count": {"$sum": 1}}}],
                "by_priority": [{"$group": {"_id": "$priority", "count": {"$sum": 1}}}],
                "by_topic": [{"$group": {"_id": "$ai_classification.topic", "count": {"$sum": 1}}}],
                "ai_classified": [{"$match": {"ai_classification.classified_by": "ai"}}, {"$count": "count"}],
                "auto_escalated": [{"$match": {"auto_escalated": True}}, {"$count": "count"}],
                "total": [{"$count": "count"}],
                "with_ai_suggestions": [
                    {"$match": {"ai_suggestions": {"$exists": True, "$ne": []}}},
                    {"$count": "count"},
                ],
                "resolved_tickets": [
                    {"$match": {"status": {"$in": ["resolved", "closed"]}}},
                    {
                        "$group": {
                            "_id": None,
                            "count": {"$sum": 1},
                            "avg_replies": {"$avg": {"$size": {"$ifNull": ["$reply_logs", []]}}},
                        }
                    },
                ],
                "sentiment_dist": [
                    {"$match": {"ai_classification.sentiment.mood": {"$exists": True}}},
                    {
                        "$group": {
                            "_id": "$ai_classification.sentiment.mood",
                            "count": {"$sum": 1},
                            "avg_frustration": {"$avg": "$ai_classification.sentiment.frustration_level"},
                        }
                    },
                ],
                "confidence_buckets": [
                    {"$match": {"ai_classification.confidence": {"$exists": True}}},
                    {
                        "$bucket": {
                            "groupBy": "$ai_classification.confidence",
                            "boundaries": [0, 0.5, 0.7, 0.85, 1.01],
                            "default": "other",
                            "output": {"count": {"$sum": 1}},
                        }
                    },
                ],
                "top_tags": [
                    {"$unwind": {"path": "$ai_tags", "preserveNullAndEmptyArrays": False}},
                    {"$group": {"_id": "$ai_tags", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 15},
                ],
                "daily_volume": [
                    {"$match": {"created_at": {"$exists": True}}},
                    {
                        "$addFields": {
                            "date_str": {"$dateToString": {"format": "%Y-%m-%d", "date": {"$toDate": "$created_at"}}}
                        }
                    },
                    {
                        "$group": {
                            "_id": "$date_str",
                            "count": {"$sum": 1},
                            "escalated": {"$sum": {"$cond": ["$auto_escalated", 1, 0]}},
                        }
                    },
                    {"$sort": {"_id": -1}},
                    {"$limit": 14},
                ],
                "resolution_by_topic": [
                    {
                        "$match": {
                            "status": {"$in": ["resolved", "closed"]},
                            "ai_classification.topic": {"$exists": True},
                        }
                    },
                    {
                        "$group": {
                            "_id": "$ai_classification.topic",
                            "count": {"$sum": 1},
                            "avg_replies": {"$avg": {"$size": {"$ifNull": ["$reply_logs", []]}}},
                        }
                    },
                ],
                "priority_dist": [{"$group": {"_id": "$priority", "count": {"$sum": 1}}}],
                "sla_data": [
                    {"$match": {"status": {"$in": ["resolved", "closed"]}}},
                    {
                        "$addFields": {
                            "created_date": {"$toDate": "$created_at"},
                            "updated_date": {"$toDate": "$updated_at"},
                        }
                    },
                    {
                        "$addFields": {
                            "resolution_hours": {
                                "$divide": [{"$subtract": ["$updated_date", "$created_date"]}, 3600000]
                            }
                        }
                    },
                    {
                        "$group": {
                            "_id": "$priority",
                            "avg_hours": {"$avg": "$resolution_hours"},
                            "count": {"$sum": 1},
                            "within_sla": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$lte": [
                                                "$resolution_hours",
                                                {
                                                    "$switch": {
                                                        "branches": [
                                                            {"case": {"$eq": ["$priority", "urgent"]}, "then": 4},
                                                            {"case": {"$eq": ["$priority", "critical"]}, "then": 4},
                                                            {"case": {"$eq": ["$priority", "high"]}, "then": 12},
                                                        ],
                                                        "default": 24,
                                                    }
                                                },
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                ],
            }
        }
    ]

    try:
        result = await db.support_submissions.aggregate(pipeline_total).to_list(1)
        data = result[0] if result else {}
    except Exception as e:
        logger.error(f"AI resolution analytics aggregation error: {e}")
        data = {}

    total = data.get("total", [{}])[0].get("count", 0)
    ai_count = data.get("ai_classified", [{}])[0].get("count", 0)
    escalated = data.get("auto_escalated", [{}])[0].get("count", 0)
    with_suggestions = data.get("with_ai_suggestions", [{}])[0].get("count", 0)
    resolved_data = data.get("resolved_tickets", [{}])[0] if data.get("resolved_tickets") else {}
    resolved_count = resolved_data.get("count", 0)

    return {
        "overview": {
            "total_tickets": total,
            "ai_classified": ai_count,
            "ai_classification_rate": round(ai_count / total * 100, 1) if total > 0 else 0,
            "auto_escalated": escalated,
            "escalation_rate": round(escalated / total * 100, 1) if total > 0 else 0,
            "resolved": resolved_count,
            "resolution_rate": round(resolved_count / total * 100, 1) if total > 0 else 0,
            "with_ai_suggestions": with_suggestions,
            "avg_replies_to_resolve": round(resolved_data.get("avg_replies", 0), 1),
        },
        "by_status": {s["_id"]: s["count"] for s in data.get("by_status", []) if s["_id"]},
        "by_priority": {p["_id"]: p["count"] for p in data.get("by_priority", []) if p["_id"]},
        "by_topic": {t["_id"]: t["count"] for t in data.get("by_topic", []) if t["_id"]},
        "sentiment": {
            s["_id"]: {"count": s["count"], "avg_frustration": round(s["avg_frustration"], 1)}
            for s in data.get("sentiment_dist", [])
            if s["_id"]
        },
        "confidence_buckets": [{"min": b["_id"], "count": b["count"]} for b in data.get("confidence_buckets", [])],
        "top_tags": [{"tag": t["_id"], "count": t["count"]} for t in data.get("top_tags", [])],
        "daily_volume": sorted(
            [
                {"date": d["_id"], "count": d["count"], "escalated": d["escalated"]}
                for d in data.get("daily_volume", [])
            ],
            key=lambda x: x["date"],
        ),
        "resolution_by_topic": {
            t["_id"]: {"count": t["count"], "avg_replies": round(t["avg_replies"], 1)}
            for t in data.get("resolution_by_topic", [])
            if t["_id"]
        },
        "sla_compliance": [
            {
                "priority": s["_id"],
                "avg_hours": round(s["avg_hours"], 1),
                "count": s["count"],
                "within_sla": s["within_sla"],
                "compliance_pct": round(s["within_sla"] / s["count"] * 100, 1) if s["count"] > 0 else 0,
            }
            for s in data.get("sla_data", [])
            if s["_id"]
        ],
    }


# ══════════════════════════════════════════════════════════════
# ── AI-Powered Automated Ticket Assignment ──
# ══════════════════════════════════════════════════════════════

VALID_TOPICS = ["billing", "technical", "account", "feature_request", "bug_report", "general"]


@router.get("/support-agents")
async def list_support_agents(request: Request):
    """List all support agents with their current workload."""
    await _require_admin(request)
    agents = await db.support_agents.find({}, {"_id": 0}).sort("name", 1).to_list(100)

    # Enrich with live workload
    for agent in agents:
        open_count = await db.support_submissions.count_documents(
            {"assigned_to": agent.get("email", ""), "status": {"$nin": ["resolved", "closed"]}}
        )
        agent["current_load"] = open_count

    return {"agents": agents}


@router.post("/support-agents")
async def create_support_agent(request: Request):
    """Create a new support agent."""
    admin = await _require_admin(request)
    body = await request.json()
    name = body.get("name", "").strip()
    email = body.get("email", "").strip()
    topics = body.get("topics", [])
    max_concurrent = body.get("max_concurrent", 10)

    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and email required")

    existing = await db.support_agents.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Agent with this email already exists")

    valid_topics = [t for t in topics if t in VALID_TOPICS]

    agent = {
        "agent_id": f"agent_{secrets.token_hex(6)}",
        "name": name,
        "email": email,
        "topics": valid_topics,
        "max_concurrent": max_concurrent,
        "is_available": True,
        "created_by": admin.user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.support_agents.insert_one(agent)
    agent.pop("_id", None)
    return {"ok": True, "agent": agent}


@router.put("/support-agents/{agent_id}")
async def update_support_agent(agent_id: str, request: Request):
    """Update a support agent's details."""
    await _require_admin(request)
    body = await request.json()

    update: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if "name" in body:
        update["name"] = body["name"].strip()
    if "email" in body:
        update["email"] = body["email"].strip()
    if "topics" in body:
        update["topics"] = [t for t in body["topics"] if t in VALID_TOPICS]
    if "max_concurrent" in body:
        update["max_concurrent"] = max(1, min(50, int(body["max_concurrent"])))
    if "is_available" in body:
        update["is_available"] = bool(body["is_available"])

    result = await db.support_agents.update_one({"agent_id": agent_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"ok": True}


@router.delete("/support-agents/{agent_id}")
async def delete_support_agent(agent_id: str, request: Request):
    """Delete a support agent."""
    await _require_admin(request)
    result = await db.support_agents.delete_one({"agent_id": agent_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"ok": True}


@router.get("/assignment-rules")
async def get_assignment_rules(request: Request):
    """Get ticket assignment rules configuration."""
    await _require_admin(request)
    config = await db.ticket_assignment_config.find_one({"_type": "assignment_rules"}, {"_id": 0})
    if not config:
        config = {
            "_type": "assignment_rules",
            "enabled": False,
            "strategy": "round_robin",
            "rules": {},
            "fallback_agent": "",
        }
    return config


@router.post("/assignment-rules")
async def update_assignment_rules(request: Request):
    """Update ticket assignment rules."""
    await _require_admin(request)
    body = await request.json()

    config = {
        "_type": "assignment_rules",
        "enabled": bool(body.get("enabled", False)),
        "strategy": body.get("strategy", "round_robin"),
        "rules": body.get("rules", {}),
        "fallback_agent": body.get("fallback_agent", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.ticket_assignment_config.update_one(
        {"_type": "assignment_rules"},
        {"$set": config},
        upsert=True,
    )
    return {"ok": True, "config": config}


@router.get("/assignment-stats")
async def get_assignment_stats(request: Request):
    """Get ticket assignment statistics."""
    await _require_admin(request)

    agents = await db.support_agents.find({}, {"_id": 0}).to_list(100)

    agent_stats = []
    for agent in agents:
        email = agent.get("email", "")
        open_tickets = await db.support_submissions.count_documents(
            {"assigned_to": email, "status": {"$nin": ["resolved", "closed"]}}
        )
        resolved_tickets = await db.support_submissions.count_documents(
            {"assigned_to": email, "status": {"$in": ["resolved", "closed"]}}
        )
        total_assigned = await db.support_submissions.count_documents({"assigned_to": email})

        agent_stats.append(
            {
                "agent_id": agent.get("agent_id"),
                "name": agent.get("name"),
                "email": email,
                "topics": agent.get("topics", []),
                "is_available": agent.get("is_available", True),
                "max_concurrent": agent.get("max_concurrent", 10),
                "open_tickets": open_tickets,
                "resolved_tickets": resolved_tickets,
                "total_assigned": total_assigned,
                "utilization": round(open_tickets / max(1, agent.get("max_concurrent", 10)) * 100, 1),
            }
        )

    # Unassigned tickets
    unassigned = await db.support_submissions.count_documents(
        {"assigned_to": {"$in": [None, ""]}, "status": {"$nin": ["resolved", "closed"]}}
    )

    # Also count tickets assigned to default support email (not a named agent)
    agent_emails = [a.get("email", "") for a in agents]
    default_assigned = 0
    if agent_emails:
        default_assigned = await db.support_submissions.count_documents(
            {"assigned_to": {"$nin": [None, ""] + agent_emails}, "status": {"$nin": ["resolved", "closed"]}}
        )

    return {
        "agents": agent_stats,
        "unassigned_tickets": unassigned + default_assigned,
        "total_agents": len(agents),
        "available_agents": sum(1 for a in agents if a.get("is_available")),
    }


@router.post("/tickets/{ticket_id}/assign")
async def assign_ticket(ticket_id: str, request: Request):
    """Manually assign a ticket to a specific agent."""
    admin = await _require_admin(request)
    body = await request.json()
    agent_email = body.get("agent_email", "").strip()

    if not agent_email:
        raise HTTPException(status_code=400, detail="Agent email required")

    # Verify agent exists
    agent = await db.support_agents.find_one({"email": agent_email}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.support_submissions.update_one(
        {"submission_id": ticket_id},
        {
            "$set": {
                "assigned_to": agent_email,
                "assigned_agent_name": agent.get("name", ""),
                "assignment_type": "manual",
                "assigned_at": now_iso,
                "updated_at": now_iso,
            },
            "$push": {
                "history": {
                    "action": "assigned",
                    "note": f"Manually assigned to {agent.get('name', agent_email)} by {admin.name}",
                    "by": admin.user_id,
                    "by_name": admin.name,
                    "at": now_iso,
                }
            },
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return {"ok": True, "assigned_to": agent_email, "agent_name": agent.get("name", "")}


@router.post("/tickets/auto-assign")
async def trigger_auto_assign(request: Request):
    """Trigger auto-assignment for all unassigned open tickets."""
    await _require_admin(request)

    config = await db.ticket_assignment_config.find_one({"_type": "assignment_rules"}, {"_id": 0})
    if not config or not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Auto-assignment is not enabled")

    agents = await db.support_agents.find({"is_available": True}, {"_id": 0}).to_list(100)
    if not agents:
        raise HTTPException(status_code=400, detail="No available agents")

    # Get unassigned open tickets
    agent_emails = [a["email"] for a in agents]
    unassigned = (
        await db.support_submissions.find(
            {
                "status": {"$nin": ["resolved", "closed"]},
                "$or": [
                    {"assigned_to": None},
                    {"assigned_to": ""},
                    {"assigned_to": {"$nin": agent_emails}},
                ],
            },
            {"_id": 0, "submission_id": 1, "ai_classification": 1, "category": 1, "priority": 1},
        )
        .sort("created_at", 1)
        .limit(50)
        .to_list(50)
    )

    assigned_count = 0
    strategy = config.get("strategy", "round_robin")

    for ticket in unassigned:
        topic = ticket.get("ai_classification", {}).get("topic") or ticket.get("category", "general")
        best_agent = await _find_best_agent(agents, topic, strategy)
        if best_agent:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.support_submissions.update_one(
                {"submission_id": ticket["submission_id"]},
                {
                    "$set": {
                        "assigned_to": best_agent["email"],
                        "assigned_agent_name": best_agent.get("name", ""),
                        "assignment_type": "auto",
                        "assigned_at": now_iso,
                        "updated_at": now_iso,
                    },
                    "$push": {
                        "history": {
                            "action": "auto_assigned",
                            "note": f"Auto-assigned to {best_agent.get('name', best_agent['email'])} (topic: {topic}, strategy: {strategy})",
                            "by": "system",
                            "by_name": "AI Assignment Engine",
                            "at": now_iso,
                        }
                    },
                },
            )
            assigned_count += 1

    return {"ok": True, "assigned": assigned_count, "total_unassigned": len(unassigned)}


async def _find_best_agent(agents: list, topic: str, strategy: str) -> Optional[dict]:
    """Find the best agent for a ticket based on topic and strategy."""
    # Filter agents by topic specialty
    topic_agents = [a for a in agents if topic in a.get("topics", []) and a.get("is_available")]
    # Fallback to any available agent if no topic specialist found
    candidate_agents = topic_agents if topic_agents else [a for a in agents if a.get("is_available")]

    if not candidate_agents:
        return None

    # Get current workload for each candidate
    for agent in candidate_agents:
        load = await db.support_submissions.count_documents(
            {"assigned_to": agent["email"], "status": {"$nin": ["resolved", "closed"]}}
        )
        agent["_current_load"] = load

    # Filter out agents at max capacity
    candidate_agents = [a for a in candidate_agents if a["_current_load"] < a.get("max_concurrent", 10)]
    if not candidate_agents:
        return None

    if strategy == "least_loaded":
        candidate_agents.sort(key=lambda a: a["_current_load"])
        return candidate_agents[0]
    else:
        # round_robin: pick agent with lowest load (effectively the same but with topic preference)
        candidate_agents.sort(key=lambda a: (a["_current_load"], -len(a.get("topics", []))))
        return candidate_agents[0]
