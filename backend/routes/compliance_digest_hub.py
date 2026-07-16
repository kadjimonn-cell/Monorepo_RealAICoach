"""Compliance Digest Hub.

Inbox-style admin feed that aggregates every compliance / governance digest
email dispatched by the platform's schedulers into a single reviewable place.

Senders instrument themselves by calling `log_digest_entry(...)` immediately
after dispatch. Admins review entries via the frontend panel, which calls:

    GET    /api/compliance-digests/feed
    GET    /api/compliance-digests/unreviewed-count
    POST   /api/compliance-digests/{entry_id}/review
    POST   /api/compliance-digests/{entry_id}/unreview
    GET    /api/compliance-digests/kinds
    POST   /api/compliance-digests/recipients        (GDPR digest recipient list)
    GET    /api/compliance-digests/recipients

Collection: `compliance_digest_feed`  — indexed on `entry_id` (unique) +
`kind` + `created_at` (desc).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, EmailStr

from routes.db import db, require_admin
from routes.careers_common import COMPLIANCE_DIGEST_FEED_COL
from utils.pdf_v15_filename import build_pdf_v15_filename

logger = logging.getLogger(__name__)
router = APIRouter()

FEED_COL = COMPLIANCE_DIGEST_FEED_COL
RECIPIENT_SETTINGS_KEY = "careers_gdpr_digest_recipients"

# Known digest kinds — used by the frontend filter pills + validation.
KNOWN_DIGEST_KINDS: tuple[str, ...] = (
    "careers_gdpr_purge_daily",
    "gdpr_retention_weekly",
    "platform_quality_weekly",
    "webhook_alerts_weekly",
    "llm_daily",
    "platform_compliance_daily",
    "gtec_c5_run_receipt",
)

KIND_LABELS: dict[str, str] = {
    "careers_gdpr_purge_daily": "GDPR Auto-Purge · Daily",
    "gdpr_retention_weekly": "GDPR Retention · Weekly",
    "platform_quality_weekly": "Platform Quality · Weekly",
    "webhook_alerts_weekly": "Webhook Alerts · Weekly",
    "llm_daily": "LLM Spend · Daily",
    "platform_compliance_daily": "Platform Compliance · Daily",
    "gtec_c5_run_receipt": "GTEC C5 · Run Receipt",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_public_gtec_task_id(task_id: object) -> str:
    raw = str(task_id or "").strip()
    if not raw:
        return ""
    if raw.startswith("gtec_v2_"):
        return f"gtec_c5_{raw.split('gtec_v2_', 1)[1]}"
    return raw


def _hydrate_gtec_receipt_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Normalize GTEC C5 receipt payload shape for locked-protocol consumers.

    Guarantees a deterministic PDF filename (with gtec-c5 naming) even for
    older receipt records created before canonical filename enforcement.
    """
    out = dict(payload or {})
    changed = False

    public_task_id = _to_public_gtec_task_id(out.get("task_id") or out.get("internal_task_id") or "")
    if public_task_id and out.get("task_id") != public_task_id:
        out["task_id"] = public_task_id
        changed = True

    pdf_attachment = dict(out.get("pdf_attachment") or {})
    existing_name = str(pdf_attachment.get("filename") or "").strip()
    normalized_name = existing_name.replace("gtec-v2", "gtec-c5").replace("gtec_v2", "gtec_c5")
    if normalized_name != existing_name:
        pdf_attachment["filename"] = normalized_name
        changed = True

    if not str(pdf_attachment.get("filename") or "").strip():
        seeded_task = public_task_id or "gtec_c5"
        pdf_attachment["filename"] = build_pdf_v15_filename("compliance", seeded_task)
        changed = True

    if changed:
        out["pdf_attachment"] = pdf_attachment
    return out, changed


async def log_digest_entry(
    *,
    kind: str,
    subject: str,
    summary: str,
    recipients: list[str],
    sent_ok: int,
    sent_failed: int,
    payload: Optional[dict[str, Any]] = None,
    trigger: str = "scheduler",
) -> Optional[str]:
    """Persist a digest-dispatch event into the hub feed. Fail-safe: returns
    None + logs on error. Senders must NEVER let a digest logging failure
    break the outbound email flow."""
    try:
        entry_id = f"dgst_{uuid.uuid4().hex[:12]}"
        normalized_payload = dict(payload or {})
        if kind == "gtec_c5_run_receipt":
            normalized_payload, _ = _hydrate_gtec_receipt_payload(normalized_payload)

        doc = {
            "entry_id": entry_id,
            "kind": kind,
            "kind_label": KIND_LABELS.get(kind, kind.replace("_", " ").title()),
            "subject": subject or "(no subject)",
            "summary": (summary or "")[:600],
            "recipients": [str(r) for r in (recipients or []) if r],
            "recipient_count": len(recipients or []),
            "sent_ok": int(sent_ok or 0),
            "sent_failed": int(sent_failed or 0),
            "payload": normalized_payload,
            "trigger": trigger,
            "created_at": _now_iso(),
            "reviewed_at": None,
            "reviewed_by": None,
            "review_notes": "",
        }
        await db[FEED_COL].insert_one(doc)
        return entry_id
    except Exception as e:
        logger.warning(f"[compliance-digest-hub] log_digest_entry failed: {e}")
        return None


async def _resolve_active_recipients() -> dict[str, Any]:
    """Resolve digest recipients from DB override > env > admin fallback."""
    doc = await db.settings.find_one({"key": RECIPIENT_SETTINGS_KEY}, {"_id": 0})
    configured: list[str] = []
    if doc and isinstance(doc.get("value"), list):
        configured = [str(x) for x in doc["value"] if x and "@" in str(x)]
    env_csv = os.environ.get("CAREERS_GDPR_DIGEST_RECIPIENTS", "")
    env_single = os.environ.get("GDPR_DIGEST_RECIPIENT", "")
    fallback_admins: list[str] = []
    async for u in db.users.find({"is_admin": True}, {"_id": 0, "email": 1}).limit(50):
        e = str(u.get("email") or "").strip()
        if e and "@" in e:
            fallback_admins.append(e)
    active_source = "admin_fallback"
    active = fallback_admins
    if configured:
        active_source = "db_override"
        active = configured
    elif env_csv.strip():
        active_source = "env_csv"
        active = [e.strip() for e in env_csv.split(",") if "@" in e]
    elif env_single.strip():
        active_source = "env_single"
        active = [env_single.strip()]

    return {
        "configured": configured,
        "env_csv": env_csv,
        "env_single": env_single,
        "admin_fallback": fallback_admins,
        "active": active,
        "active_source": active_source,
    }


async def build_platform_compliance_digest(window_hours: int = 24) -> dict[str, Any]:
    """Aggregate compliance posture across support, GDPR, security and FAQ coverage."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)
    since_iso = since.isoformat()

    open_tickets = await db.support_submissions.count_documents({"status": {"$nin": ["resolved", "closed"]}})
    escalated_open = await db.support_submissions.count_documents({"status": "escalated"})
    high_priority_open = await db.support_submissions.count_documents(
        {"status": {"$nin": ["resolved", "closed"]}, "priority": {"$in": ["high", "urgent", "critical"]}}
    )
    auto_escalated_24h = await db.support_submissions.count_documents({"auto_escalated": True, "updated_at": {"$gte": since_iso}})

    open_nudges = await db.support_proactive_nudges.count_documents({"status": "open"})
    nudges_24h = await db.support_proactive_nudges.count_documents({"created_at": {"$gte": since_iso}})

    gdpr_pending = await db.gdpr_requests.count_documents({"status": "pending_verification"})
    gdpr_completed_24h = await db.gdpr_requests.count_documents({"status": "completed", "updated_at": {"$gte": since_iso}})

    security_high_critical_24h = await db.security_events.count_documents(
        {"timestamp": {"$gte": since_iso}, "severity": {"$in": ["high", "critical"]}}
    )
    digest_unreviewed = await db[FEED_COL].count_documents({"reviewed_at": None})

    faq_active_total = await db.faq_content.count_documents({"active": {"$ne": False}})
    faq_langs_raw = await db.faq_content.distinct("lang", {"active": {"$ne": False}})
    faq_langs = sorted({str(v).strip().lower()[:2] for v in faq_langs_raw if str(v).strip()})
    required_faq_langs = ["en", "fr", "es", "de", "it", "pt"]
    faq_missing_langs = [lang_code for lang_code in required_faq_langs if lang_code not in faq_langs]

    severity = "low"
    if security_high_critical_24h >= 8 or escalated_open >= 20 or open_nudges >= 30:
        severity = "critical"
    elif security_high_critical_24h >= 4 or escalated_open >= 10 or open_nudges >= 15:
        severity = "high"
    elif security_high_critical_24h >= 1 or escalated_open >= 5 or open_nudges >= 5:
        severity = "medium"

    return {
        "window_hours": window_hours,
        "window_start": since_iso,
        "window_end": now.isoformat(),
        "severity": severity,
        "metrics": {
            "support_open_tickets": open_tickets,
            "support_escalated_open": escalated_open,
            "support_high_priority_open": high_priority_open,
            "support_auto_escalated_24h": auto_escalated_24h,
            "support_open_nudges": open_nudges,
            "support_nudges_24h": nudges_24h,
            "gdpr_pending_requests": gdpr_pending,
            "gdpr_completed_24h": gdpr_completed_24h,
            "security_high_critical_24h": security_high_critical_24h,
            "compliance_digest_unreviewed": digest_unreviewed,
            "faq_active_total": faq_active_total,
            "faq_languages_present": faq_langs,
            "faq_languages_missing": faq_missing_langs,
        },
    }


async def generate_platform_compliance_digest(trigger: str = "manual_admin") -> dict[str, Any]:
    """Generate + optionally email + log a platform-wide compliance digest."""
    digest = await build_platform_compliance_digest(window_hours=24)
    recipients_info = await _resolve_active_recipients()
    recipients = recipients_info.get("active") or []

    sent_ok = 0
    sent_failed = 0
    errors: list[str] = []

    try:
        from utils.email_service import is_email_configured, send_catalog_template

        if is_email_configured() and recipients:
            missing_langs = ", ".join(digest["metrics"].get("faq_languages_missing") or []) or "none"
            for email in recipients:
                try:
                    result = await send_catalog_template(
                        recipient_email=email,
                        template_key="platform_compliance_daily_digest",
                        severity=str(digest.get("severity") or "low"),
                        support_open_nudges=int(digest["metrics"].get("support_open_nudges") or 0),
                        support_escalated_open=int(digest["metrics"].get("support_escalated_open") or 0),
                        security_high_critical_24h=int(digest["metrics"].get("security_high_critical_24h") or 0),
                        faq_languages_missing=missing_langs,
                        dashboard_link=f"{os.environ.get('FRONTEND_BASE_URL', '').rstrip('/')}/admin-console?tab=compliance-digest" if os.environ.get("FRONTEND_BASE_URL") else "",
                    )
                    if result.get("success"):
                        sent_ok += 1
                    else:
                        sent_failed += 1
                        errors.append(f"{email}: {result.get('error', 'send_failed')}")
                except Exception as exc:
                    sent_failed += 1
                    errors.append(f"{email}: {str(exc)[:120]}")
    except Exception as exc:
        errors.append(f"email_service_unavailable: {str(exc)[:120]}")

    summary = (
        f"severity={digest['severity']} · nudges_open={digest['metrics']['support_open_nudges']} · "
        f"escalated_open={digest['metrics']['support_escalated_open']} · "
        f"security_high_critical_24h={digest['metrics']['security_high_critical_24h']}"
    )
    entry_id = await log_digest_entry(
        kind="platform_compliance_daily",
        subject=f"Platform Compliance Daily · {digest['severity'].upper()}",
        summary=summary,
        recipients=recipients,
        sent_ok=sent_ok,
        sent_failed=sent_failed,
        payload=digest,
        trigger=trigger,
    )

    record = {
        "digest_id": f"pcd_{uuid.uuid4().hex[:12]}",
        "trigger": trigger,
        "entry_id": entry_id,
        "recipients": recipients,
        "recipient_source": recipients_info.get("active_source"),
        "sent_ok": sent_ok,
        "sent_failed": sent_failed,
        "errors": errors[:10],
        "digest": digest,
        "created_at": _now_iso(),
    }
    await db.platform_compliance_digests.insert_one({**record})
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Admin feed endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/compliance-digests/feed")
async def admin_feed(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    kind: Optional[str] = Query(None),
    reviewed: Optional[str] = Query(None, pattern="^(all|reviewed|unreviewed)$"),
):
    """Inbox-style feed of recent digest dispatches, newest first."""
    await require_admin(request)
    q: dict[str, Any] = {}
    if kind:
        q["kind"] = kind
    if reviewed == "reviewed":
        q["reviewed_at"] = {"$ne": None}
    elif reviewed == "unreviewed":
        q["reviewed_at"] = None
    items: list[dict[str, Any]] = []
    async for d in db[FEED_COL].find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
        if str(d.get("kind") or "") == "gtec_c5_run_receipt":
            payload_hydrated, changed = _hydrate_gtec_receipt_payload(d.get("payload") or {})
            if changed:
                d["payload"] = payload_hydrated
                await db[FEED_COL].update_one(
                    {"entry_id": d.get("entry_id")},
                    {"$set": {"payload": payload_hydrated}},
                    upsert=False,
                )
        items.append(d)
    unreviewed_count = await db[FEED_COL].count_documents({"reviewed_at": None})
    total = await db[FEED_COL].count_documents({})
    return {
        "items": items,
        "count": len(items),
        "unreviewed_count": unreviewed_count,
        "total": total,
    }


@router.get("/compliance-digests/unreviewed-count")
async def admin_unreviewed_count(request: Request):
    """Small poll-friendly endpoint for the sidebar badge."""
    await require_admin(request)
    n = await db[FEED_COL].count_documents({"reviewed_at": None})
    return {"unreviewed_count": n}


@router.get("/compliance-digests/kinds")
async def admin_kinds(request: Request):
    """Known kinds + live per-kind counts (drives the filter pills)."""
    await require_admin(request)
    out: list[dict[str, Any]] = []
    for k in KNOWN_DIGEST_KINDS:
        total = await db[FEED_COL].count_documents({"kind": k})
        unreviewed = await db[FEED_COL].count_documents({"kind": k, "reviewed_at": None})
        out.append({
            "kind": k,
            "label": KIND_LABELS.get(k, k),
            "total": total,
            "unreviewed": unreviewed,
        })
    return {"kinds": out}


class ReviewBody(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)


@router.post("/compliance-digests/{entry_id}/review")
async def admin_mark_reviewed(request: Request, entry_id: str, body: ReviewBody):
    """Mark a digest entry reviewed (idempotent — second call is a no-op)."""
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    entry = await db[FEED_COL].find_one({"entry_id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    now = _now_iso()
    if entry.get("reviewed_at"):
        return {"ok": True, "already_reviewed": True, "reviewed_at": entry["reviewed_at"],
                "reviewed_by": entry.get("reviewed_by")}
    updates = {
        "reviewed_at": now,
        "reviewed_by": actor,
        "review_notes": (body.notes or "")[:2000],
    }
    await db[FEED_COL].update_one({"entry_id": entry_id}, {"$set": updates})
    return {"ok": True, "reviewed_at": now, "reviewed_by": actor}


@router.post("/compliance-digests/{entry_id}/unreview")
async def admin_unreview(request: Request, entry_id: str):
    """Undo a mark-reviewed action (audit trail is preserved in a history sub-array)."""
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or "admin"
    entry = await db[FEED_COL].find_one({"entry_id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    prev_reviewed_at = entry.get("reviewed_at")
    prev_reviewed_by = entry.get("reviewed_by")
    if not prev_reviewed_at:
        return {"ok": True, "already_unreviewed": True}
    history = list(entry.get("review_history") or [])
    history.append({
        "reviewed_at": prev_reviewed_at,
        "reviewed_by": prev_reviewed_by,
        "notes": entry.get("review_notes") or "",
        "unreviewed_at": _now_iso(),
        "unreviewed_by": actor,
    })
    await db[FEED_COL].update_one(
        {"entry_id": entry_id},
        {"$set": {
            "reviewed_at": None,
            "reviewed_by": None,
            "review_notes": "",
            "review_history": history,
        }},
    )
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Digest recipient config — lets ops edit without a redeploy
# ─────────────────────────────────────────────────────────────────────────────


class RecipientsBody(BaseModel):
    emails: list[EmailStr] = Field(default_factory=list)


@router.get("/compliance-digests/recipients")
async def admin_get_recipients(request: Request):
    """Current configured recipient list (priority:
    settings.careers_gdpr_digest_recipients > env > all-admins fallback)."""
    await require_admin(request)
    return await _resolve_active_recipients()


@router.put("/compliance-digests/recipients")
async def admin_set_recipients(request: Request, body: RecipientsBody):
    """Persist the recipient list — takes effect immediately for the next
    scheduled dispatch (no redeploy needed)."""
    await require_admin(request)
    emails = [str(e) for e in body.emails]
    await db.settings.update_one(
        {"key": RECIPIENT_SETTINGS_KEY},
        {"$set": {
            "key": RECIPIENT_SETTINGS_KEY,
            "value": emails,
            "updated_at": _now_iso(),
        }},
        upsert=True,
    )
    return {"ok": True, "count": len(emails), "emails": emails}


@router.get("/admin/compliance-digest")
async def admin_platform_compliance_digest(request: Request, limit: int = Query(14, ge=1, le=60)):
    """Latest platform compliance digest + history."""
    await require_admin(request)
    history = (
        await db.platform_compliance_digests.find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    latest = history[0] if history else None
    if not latest:
        digest = await build_platform_compliance_digest(window_hours=24)
        latest = {
            "digest_id": "preview",
            "trigger": "preview",
            "entry_id": None,
            "recipients": [],
            "recipient_source": "none",
            "sent_ok": 0,
            "sent_failed": 0,
            "errors": [],
            "digest": digest,
            "created_at": _now_iso(),
        }
    return {"latest": latest, "history": history, "count": len(history)}


@router.post("/admin/compliance-digest/run-now")
async def admin_platform_compliance_digest_run_now(request: Request):
    """Admin-triggered immediate platform compliance digest generation."""
    await require_admin(request)
    record = await generate_platform_compliance_digest(trigger="manual_admin")
    return {"ok": True, "record": record}


# ─────────────────────────────────────────────────────────────────────────
# CSV export — downloadable audit trail for compliance officers.
# Honors the same `kind` + `reviewed` filters as the feed so the
# downloaded file matches exactly what's visible in the UI.
# ─────────────────────────────────────────────────────────────────────────


@router.get("/compliance-digests/export.csv")
async def admin_export_csv(
    request: Request,
    kind: Optional[str] = Query(None),
    reviewed: Optional[str] = Query(None, pattern="^(all|reviewed|unreviewed)$"),
    limit: int = Query(5000, ge=1, le=50000),
):
    """Stream a CSV of digest entries for download.

    Columns are picked for a compliance reviewer's workflow — subject,
    kind, created_at, recipient count, sent ok/failed, reviewed status,
    reviewer, and summary. Heavy `payload` blobs are intentionally
    excluded so the export stays portable in Excel/Sheets."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    await require_admin(request)
    q: dict[str, Any] = {}
    if kind:
        q["kind"] = kind
    if reviewed == "reviewed":
        q["reviewed_at"] = {"$ne": None}
    elif reviewed == "unreviewed":
        q["reviewed_at"] = None

    async def _rows():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "created_at", "kind", "kind_label", "subject",
            "recipient_count", "sent_ok", "sent_failed",
            "trigger", "reviewed_at", "reviewed_by", "review_notes",
            "summary",
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        async for d in db[FEED_COL].find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
            writer.writerow([
                d.get("created_at") or "",
                d.get("kind") or "",
                KIND_LABELS.get(d.get("kind") or "", d.get("kind") or ""),
                d.get("subject") or "",
                int(d.get("recipient_count") or 0),
                int(d.get("sent_ok") or 0),
                int(d.get("sent_failed") or 0),
                d.get("trigger") or "",
                d.get("reviewed_at") or "",
                d.get("reviewed_by") or "",
                (d.get("review_notes") or "").replace("\n", " ").strip(),
                (d.get("summary") or "").replace("\n", " ").strip(),
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    fname = f"compliance-digests-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        _rows(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Cache-Control": "no-store",
        },
    )


__all__ = ["router", "log_digest_entry", "KNOWN_DIGEST_KINDS", "KIND_LABELS"]
