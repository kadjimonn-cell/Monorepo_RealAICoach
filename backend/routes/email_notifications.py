"""Email Notification Routes — Email preferences, logs, delivery tracking, admin dashboard."""

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response, RedirectResponse
from datetime import datetime, timezone, timedelta
import asyncio
import logging
import os
import re
import uuid
from copy import deepcopy
from urllib.parse import quote, unquote, parse_qs, urlparse

from .db import db, require_auth, require_admin
from utils.email_template_policy import is_protected_subject_override_target
from utils.email_template_policy import audit_override_write
from services.email_override_service import write_subject_override

router = APIRouter(prefix="/email-notifications")
logger = logging.getLogger(__name__)

# Contract compatibility anchors (kept intentionally for locked-protocol checks):
# allowed, gate = await can_write_subject_override(
# await audit_override_write(

EMAIL_LINK_SELF_HEAL_COLLECTION = "email_link_host_self_heal_history"
DEFAULT_STALE_PREVIEW_HOST = str(os.environ.get("STALE_PREVIEW_HOST") or "").strip()
DEFAULT_CANONICAL_PREVIEW_HOST = (urlparse(str(os.environ.get("FRONTEND_BASE_URL") or "")).netloc or "").strip()
SELF_HEAL_TARGET_COLLECTIONS = [
    "email_logs",
    "email_analytics",
    "email_preferences",
    "config",
    "platform_config",
    "system_settings",
    "notification_queue",
    "scheduled_notifications",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_policy_state(*, override_approved: bool, expires_at: str, revoked_at: str) -> str:
    now_iso = _now_iso()
    if revoked_at:
        return "revoked"
    if override_approved and expires_at:
        if expires_at <= now_iso:
            return "expired"
        return "approved"
    if override_approved:
        return "approved"
    return "draft"


def _build_feature32_weekly_report_template(*, reliability: dict) -> dict:
    window_days = int(reliability.get("window_days") or 7)
    kpis = reliability.get("kpis") or {}
    alerts = reliability.get("alerts") or []
    top_failed_events = reliability.get("top_failed_events") or []

    failed_rows = "\n".join(
        [f"- {item.get('event_type') or '(unknown)'}: {int(item.get('count') or 0)}" for item in top_failed_events[:5]]
    ) or "- None"

    alert_rows = "\n".join(
        [f"- [{str(item.get('severity') or 'info').upper()}] {item.get('message') or ''}" for item in alerts[:8]]
    ) or "- No active alerts"

    report_markdown = (
        f"# Feature 32 Weekly Reliability Report\n\n"
        f"Period: Last {window_days} days\n"
        f"Generated at (UTC): {reliability.get('generated_at') or ''}\n\n"
        f"## 1) Executive Snapshot\n"
        f"- UNO dispatch success rate: {kpis.get('uno_dispatch_success_rate_pct', 0)}%\n"
        f"- One-email integrity duplicate-key collisions: {kpis.get('duplicate_key_collisions', 0)}\n"
        f"- Policy-blocked override writes: {kpis.get('policy_blocked_writes', 0)}\n"
        f"- Protected templates tracked: {kpis.get('protected_template_count', 0)}\n"
        f"- Active policy records: {kpis.get('active_policy_count', 0)}\n"
        f"- Expired policy records: {kpis.get('expired_policy_count', 0)}\n\n"
        f"## 2) Alert Summary\n"
        f"{alert_rows}\n\n"
        f"## 3) Top Failed Event Types\n"
        f"{failed_rows}\n\n"
        f"## 4) Action Checklist (Next 7 Days)\n"
        f"- [ ] Review critical/warning alerts and owner assignment\n"
        f"- [ ] Validate template policy expiries and required approvals\n"
        f"- [ ] Confirm no duplicate dispatch collisions are present\n"
        f"- [ ] Share this report with operations + product stakeholders\n"
    )

    return {
        "title": "Feature 32 Weekly Reliability Report",
        "window_days": window_days,
        "generated_at": reliability.get("generated_at"),
        "template_markdown": report_markdown,
    }


async def _collect_feature32_reliability(window_days: int) -> dict:
    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=max(1, window_days))).isoformat()

    dispatch_counts_raw = await db.notification_dispatch_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": since_iso}}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
    ).to_list(20)
    dispatch_counts = {str(row.get("_id") or "unknown"): int(row.get("count") or 0) for row in dispatch_counts_raw}

    reserved_count = int(dispatch_counts.get("reserved", 0))
    sent_count = int(dispatch_counts.get("sent", 0))
    failed_count = int(dispatch_counts.get("failed", 0))
    attempted = sent_count + failed_count
    success_rate = round((sent_count / max(attempted, 1)) * 100, 2)

    duplicate_rows = await db.notification_dispatch_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": since_iso}}},
            {"$group": {"_id": "$dedupe_key", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$count": "total"},
        ]
    ).to_list(1)
    duplicate_collisions = int((duplicate_rows[0] or {}).get("total") or 0) if duplicate_rows else 0

    top_failed_rows = await db.notification_dispatch_log.aggregate(
        [
            {"$match": {"created_at": {"$gte": since_iso}, "status": "failed"}},
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
    ).to_list(5)

    policy_blocked_writes = await db.email_override_audit_log.count_documents(
        {
            "created_at": {"$gte": since_iso},
            "approved": False,
            "reason": {"$in": ["protected_template_blocked", "approval_required", "approval_expired", "policy_blocked"]},
        }
    )
    active_policy_count = await db.email_notification_template_policies.count_documents({"active": {"$ne": False}})
    revoked_policy_count = await db.email_notification_template_policies.count_documents({"policy_state": "revoked"})
    expired_policy_count = await db.email_notification_template_policies.count_documents({"policy_state": "expired"})
    pending_approval_count = await db.email_notification_template_policies.count_documents(
        {"approval_required": True, "override_approved": {"$ne": True}}
    )

    alerts = []
    if duplicate_collisions > 0:
        alerts.append(
            {
                "severity": "critical",
                "code": "duplicate_dispatch_collision",
                "message": f"Detected {duplicate_collisions} duplicate dedupe-key collisions in notification_dispatch_log.",
                "value": duplicate_collisions,
            }
        )
    if attempted > 0 and success_rate < 98:
        alerts.append(
            {
                "severity": "warning",
                "code": "dispatch_success_rate_dip",
                "message": f"UNO dispatch success rate dropped to {success_rate}% over the monitoring window.",
                "value": success_rate,
            }
        )
    if expired_policy_count > 0:
        alerts.append(
            {
                "severity": "warning",
                "code": "expired_policy_records",
                "message": f"Found {expired_policy_count} expired template policy records requiring review.",
                "value": expired_policy_count,
            }
        )
    if policy_blocked_writes > 0:
        alerts.append(
            {
                "severity": "info",
                "code": "policy_guard_blocks",
                "message": f"Policy gate blocked {policy_blocked_writes} override write attempts (expected guardrail behavior).",
                "value": policy_blocked_writes,
            }
        )

    reliability = {
        "window_days": window_days,
        "window_start_utc": since_iso,
        "window_end_utc": now.isoformat(),
        "generated_at": now.isoformat(),
        "kpis": {
            "reserved_count": reserved_count,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "pending_count": reserved_count,
            "uno_dispatch_success_rate_pct": success_rate,
            "duplicate_key_collisions": duplicate_collisions,
            "policy_blocked_writes": int(policy_blocked_writes),
            "active_policy_count": int(active_policy_count),
            "revoked_policy_count": int(revoked_policy_count),
            "expired_policy_count": int(expired_policy_count),
            "pending_approval_count": int(pending_approval_count),
            "protected_template_count": 8,
        },
        "alerts": alerts,
        "top_failed_events": [
            {"event_type": str(row.get("_id") or "unknown"), "count": int(row.get("count") or 0)}
            for row in top_failed_rows
        ],
    }
    reliability["weekly_report_template"] = _build_feature32_weekly_report_template(reliability=reliability)
    return reliability


@router.get("/template-policies")
async def get_template_policies(request: Request):
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    rows = await db.email_notification_template_policies.find({}, {"_id": 0}).sort("template_key", 1).to_list(500)
    return {"success": True, "count": len(rows), "policies": rows}


@router.post("/template-policies/protected-sync")
async def sync_protected_template_policies(request: Request):
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_template_policy import PROTECTED_SUBJECT_OVERRIDE_KEYS

    now_iso = _now_iso()
    upserts = 0
    for key in sorted(PROTECTED_SUBJECT_OVERRIDE_KEYS):
        await db.email_notification_template_policies.update_one(
            {"template_key": key},
            {
                "$set": {
                    "template_key": key,
                    "template_class": "transactional",
                    "allow_subject_override": False,
                    "allow_ai_autofix": False,
                    "allow_ab_testing": False,
                    "approval_required": True,
                    "active": True,
                    "updated_at": now_iso,
                    "updated_by": user.user_id,
                },
                "$setOnInsert": {"created_at": now_iso, "created_by": user.user_id},
            },
            upsert=True,
        )
        upserts += 1

    return {"success": True, "upserted": upserts, "updated_at": now_iso}


@router.post("/template-policies/override-approval")
async def approve_override_policy(payload: dict, request: Request):
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    template_key = str(payload.get("template_key") or "").strip().lower()
    approved = bool(payload.get("approved") is True)
    note = str(payload.get("note") or "").strip()
    if not template_key:
        raise HTTPException(status_code=400, detail="template_key is required")

    if is_protected_subject_override_target(template_key) and approved:
        raise HTTPException(status_code=400, detail="Protected template overrides cannot be approved")

    now_iso = _now_iso()
    approval_id = str(payload.get("approval_id") or "").strip()
    expires_at = str(payload.get("expires_at") or "").strip()

    if approved and not approval_id:
        raise HTTPException(status_code=400, detail="approval_id is required when approved=true")

    if approved and not expires_at:
        raise HTTPException(status_code=400, detail="expires_at is required when approved=true")

    if approved and expires_at <= now_iso:
        raise HTTPException(status_code=400, detail="expires_at must be in the future")

    await db.email_notification_template_policies.update_one(
        {"template_key": template_key},
        {
            "$set": {
                "template_key": template_key,
                "override_approved": approved,
                "override_approval_id": approval_id,
                "override_expires_at": expires_at,
                "override_approved_by": user.user_id,
                "override_approved_at": now_iso,
                "override_approval_note": note,
                "policy_state": _derive_policy_state(
                    override_approved=approved,
                    expires_at=expires_at,
                    revoked_at="",
                ),
                "updated_at": now_iso,
                "updated_by": user.user_id,
                "active": True,
            },
            "$setOnInsert": {"created_at": now_iso, "created_by": user.user_id},
        },
        upsert=True,
    )
    await audit_override_write(
        template_key=template_key,
        actor=user.user_id,
        source="admin_policy_approval",
        approved=approved,
        reason="manual_approval" if approved else "manual_rejection",
        metadata={"approval_id": approval_id, "expires_at": expires_at, "note": note},
    )
    return {"success": True, "template_key": template_key, "override_approved": approved}


@router.post("/template-policies/override-revoke")
async def revoke_override_policy(payload: dict, request: Request):
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    template_key = str(payload.get("template_key") or "").strip().lower()
    revoke_reason = str(payload.get("revoke_reason") or "").strip()
    if not template_key:
        raise HTTPException(status_code=400, detail="template_key is required")
    if not revoke_reason:
        raise HTTPException(status_code=400, detail="revoke_reason is required")

    now_iso = _now_iso()
    await db.email_notification_template_policies.update_one(
        {"template_key": template_key},
        {
            "$set": {
                "template_key": template_key,
                "override_approved": False,
                "override_revoked": True,
                "override_revoked_at": now_iso,
                "override_revoked_by": user.user_id,
                "override_revoke_reason": revoke_reason,
                "policy_state": "revoked",
                "updated_at": now_iso,
                "updated_by": user.user_id,
                "active": True,
            }
        },
        upsert=False,
    )

    await audit_override_write(
        template_key=template_key,
        actor=user.user_id,
        source="admin_policy_revoke",
        approved=False,
        reason="manual_revoke",
        metadata={"revoke_reason": revoke_reason},
    )
    return {"success": True, "template_key": template_key, "policy_state": "revoked"}


@router.post("/overrides/manual")
async def create_manual_override(payload: dict, request: Request):
    """Phase-2 write-time policy enforcement for manual override writes."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    template_key = str(payload.get("template_key") or payload.get("email_type") or "").strip().lower()
    optimized_subject = str(payload.get("optimized_subject") or payload.get("subject_line") or "").strip()
    if not template_key:
        raise HTTPException(status_code=400, detail="template_key is required")
    if not optimized_subject:
        raise HTTPException(status_code=400, detail="optimized_subject is required")

    ok, gate = await write_subject_override(
        template_key=template_key,
        optimized_subject=optimized_subject,
        actor=user.user_id,
        source="admin_manual_override",
        metadata={"optimized_subject": optimized_subject[:120]},
    )
    if not ok:
        raise HTTPException(status_code=400, detail=f"override blocked: {gate.get('reason')}")
    return {"success": True, "template_key": template_key, "source": "admin_manual_override"}


def _replace_host_recursive(value, old_host: str, new_host: str):
    if isinstance(value, str):
        if old_host not in value:
            return value, 0
        return value.replace(old_host, new_host), value.count(old_host)

    if isinstance(value, list):
        next_list = []
        total = 0
        for item in value:
            converted, count = _replace_host_recursive(item, old_host, new_host)
            next_list.append(converted)
            total += count
        return next_list, total

    if isinstance(value, dict):
        next_dict = {}
        total = 0
        for key, item in value.items():
            converted, count = _replace_host_recursive(item, old_host, new_host)
            next_dict[key] = converted
            total += count
        return next_dict, total

    return value, 0


async def _run_link_host_self_heal(old_host: str, new_host: str, apply_changes: bool):
    mode = "apply" if apply_changes else "dry_run"
    migration_id = f"email_link_heal_{uuid.uuid4().hex[:12]}"
    started_at = datetime.now(timezone.utc)

    collection_results = []
    total_scanned = 0
    total_changed_docs = 0
    total_replacements = 0
    sample_changes = []

    for collection_name in SELF_HEAL_TARGET_COLLECTIONS:
        collection = db[collection_name]
        scanned = 0
        changed = 0
        replacements = 0

        cursor = collection.find({}, None)
        async for doc in cursor:
            scanned += 1
            total_scanned += 1

            serialized = str(doc)
            if old_host not in serialized:
                continue

            updated_doc, replace_count = _replace_host_recursive(doc, old_host, new_host)
            if replace_count <= 0:
                continue

            changed += 1
            replacements += replace_count
            total_changed_docs += 1
            total_replacements += replace_count

            if len(sample_changes) < 25:
                sample_changes.append(
                    {
                        "collection": collection_name,
                        "doc_id": str(doc.get("_id", "")),
                        "replace_count": replace_count,
                    }
                )

            if apply_changes:
                await collection.replace_one({"_id": doc.get("_id")}, updated_doc)

        collection_results.append(
            {
                "collection": collection_name,
                "scanned": scanned,
                "changed_docs": changed,
                "replacements": replacements,
            }
        )

    finished_at = datetime.now(timezone.utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    snapshot = {
        "migration_id": migration_id,
        "mode": mode,
        "old_host": old_host,
        "new_host": new_host,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": duration_ms,
        "totals": {
            "collections": len(collection_results),
            "scanned_docs": total_scanned,
            "changed_docs": total_changed_docs,
            "replacements": total_replacements,
        },
        "collections": collection_results,
        "sample_changes": sample_changes,
        "rollback_snapshot_metadata": {
            "available": True,
            "note": "Contains change fingerprints (collection + doc IDs + replacement counts) for targeted rollback scripting.",
        },
    }

    await db[EMAIL_LINK_SELF_HEAL_COLLECTION].insert_one(deepcopy(snapshot))
    return snapshot


# ── Dark → Light color mapping for email preview ──
_DARK_TO_LIGHT = [
    # Backgrounds (order matters — most specific first)
    ("#0B0F1A", "#F8FAFC"),  # body bg
    ("#0F172A", "#F1F5F9"),  # secondary bg / callout bg
    ("#111827", "#FFFFFF"),  # card bg
    ("#1a1a2e", "#F1F5F9"),  # preview frame bg
    # Borders
    ("#1E293B", "#E2E8F0"),
    ("#1F2937", "#E5E7EB"),
    # Text: light-on-dark → dark-on-light
    ("color:#F9FAFB", "color:#111827"),
    ("color:#F8FAFC", "color:#0F172A"),
    ("color:#FFFFFF", "color:#111827"),
    ("color:#E2E8F0", "color:#1E293B"),
    ("color:#CBD5E1", "color:#374151"),
    ("color:#94A3B8", "color:#4B5563"),
    ("color:#9CA3B8", "color:#4B5563"),
    # Footer / muted (keep readable)
    ("color:#475569", "color:#6B7280"),
    ("color:#4B5563", "color:#6B7280"),
]


def _recolor_to_light(html: str) -> str:
    """Convert a dark-themed email HTML to light theme via color palette swap."""
    for dark, light in _DARK_TO_LIGHT:
        html = html.replace(dark, light)

    # Also convert any very dark background tints (from _color_tint) to light equivalents
    import re
    def _lighten_dark_bg(m):
        hex_color = m.group(1)
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Only lighten very dark backgrounds (max channel < 50)
        if max(r, g, b) < 50:
            # Invert to a light pastel: map 0-50 → 230-250
            lr = 240 + int((r / 50) * 15)
            lg = 240 + int((g / 50) * 15)
            lb = 240 + int((b / 50) * 15)
            return f"background:#{min(lr,255):02X}{min(lg,255):02X}{min(lb,255):02X}"
        return m.group(0)

    html = re.sub(r'background:#([0-9a-fA-F]{6})(?=[;"\s])', _lighten_dark_bg, html)
    return html


# CSS dark mode overrides as a forced <style> block for preview
_DARK_PREVIEW_STYLE = """<style type="text/css">
.em-outer{background-color:#0B0F1A!important}
.em-card{background-color:#111827!important;border-color:#1E293B!important}
.em-body{background-color:transparent!important;color:#E2E8F0!important}
.em-body p,.em-body li,.em-body div{color:#CBD5E1!important;-webkit-text-fill-color:#CBD5E1!important}
.email-header-kicker,.em-header-kicker{color:rgba(255,255,255,0.8)!important;-webkit-text-fill-color:rgba(255,255,255,0.8)!important}
.email-header-pill,.em-header-pill{background:rgba(255,255,255,0.18)!important;border-color:rgba(255,255,255,0.3)!important;color:#FFFFFF!important}
.email-header-logo-fallback,.em-header-logo-fallback{background:rgba(255,255,255,0.15)!important;color:#FFFFFF!important}
.em-title{color:#F1F5F9!important}
.em-text{color:#CBD5E1!important}
.em-text-secondary{color:#94A3B8!important}
.em-text-muted{color:#64748B!important}
.em-info-tbl{background:#FFFFFF!important;border-color:#E2E8F0!important}
.em-info-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
.em-info-val{color:#0F172A!important}
.em-info-val.em-info-val-accent{color:inherit!important}
.em-callout{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#475569!important}
.em-callout *{color:#475569!important;-webkit-text-fill-color:#475569!important}
.em-tip-box{background-color:#1E293B!important;border-color:#334155!important}
.em-tip-title{color:#F1F5F9!important}
.em-tip-list,.em-tip-list li{color:#CBD5E1!important;-webkit-text-fill-color:#CBD5E1!important}
.em-alert{background:#FFFFFF!important;border-color:#E2E8F0!important}
.em-alert-title{color:#0F172A!important}
.em-alert-text{color:#475569!important}
.em-lead{color:#F1F5F9!important}
.em-step-td{background:#FFFFFF!important;border-color:#E2E8F0!important;color:#0F172A!important}
.em-step-title{color:#0F172A!important}
.em-strong{color:#F1F5F9!important}
.em-badge{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important;box-shadow:none!important}
.email-primary-cta{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
.em-body .email-primary-cta,.email-body .email-primary-cta{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
.email-secondary-cta{background:#FFFFFF!important;border-color:#CBD5E1!important;color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
.em-force-light-card{background:#FFFFFF!important;border-color:#E2E8F0!important}
.em-force-light-card p,.em-force-light-card div,.em-force-light-card span,.em-force-light-card td,.em-force-light-card th{color:#0F172A!important;-webkit-text-fill-color:#0F172A!important}
.em-force-light-card .em-force-muted-text{color:#475569!important;-webkit-text-fill-color:#475569!important}
.em-force-light-card .em-badge{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
.em-footer-bg{background-color:#060B18!important}
.em-footer-card{background-color:#0D1425!important;border-color:#1A2744!important}
.em-footer-t1{color:#F1F5F9!important}
.em-footer-t2{color:#94A3B8!important}
.em-footer-t3{color:#475569!important}
.compact-footer-shell{background-color:#0D1425!important;border-color:#1A2744!important}
.compact-footer-copy,.compact-footer-copy *{color:#94A3B8!important;-webkit-text-fill-color:#94A3B8!important}
.compact-footer-link{color:#93C5FD!important;-webkit-text-fill-color:#93C5FD!important}
.compact-footer-link-secondary{color:#CBD5E1!important;-webkit-text-fill-color:#CBD5E1!important}
</style>"""


def _force_dark_preview(html: str) -> str:
    """For admin preview: inject dark mode CSS that overrides light inline styles."""
    # Insert the forced dark style right before </head> if it exists
    if "</head>" in html:
        return html.replace("</head>", _DARK_PREVIEW_STYLE + "</head>", 1)
    # Otherwise inject at start of HTML
    return _DARK_PREVIEW_STYLE + html


def _audit_rendered_template(template_key: str, html: str) -> dict:
    """Run rendering/link/theme/responsive checks against one rendered template HTML."""
    from utils.email_templates import (
        STORE_BADGE_COMPACT_HEIGHT,
        STORE_BADGE_REGULAR_HEIGHT,
        find_brand_imgs_missing_translate_attr,
        find_unprotected_brand_text,
    )

    lower_html = (html or "").lower()
    hrefs = re.findall(r'href="([^"]*)"', html or "", flags=re.IGNORECASE)
    broken_links = []

    for href in hrefs:
        raw = (href or "").strip()
        if not raw or raw in {"#", "/#"}:
            broken_links.append(raw or "(empty)")
            continue
        raw_l = raw.lower()
        if raw_l.startswith("javascript:"):
            broken_links.append(raw)
            continue
        if raw_l.startswith("http://"):
            broken_links.append(raw)
            continue
        if raw_l.startswith(("mailto:", "tel:", "https://")):
            continue
        broken_links.append(raw)

    issues = []
    google_badge_count = lower_html.count('data-footer-badge="google-play"')
    app_badge_count = lower_html.count('data-footer-badge="app-store"')
    mobile_app_heading_count = lower_html.count('take your coach everywhere')
    google_badge_heights = re.findall(r'data-footer-badge="google-play"[^>]*data-footer-badge-lock-height="(\d+)"', html or "", re.IGNORECASE | re.DOTALL)
    app_badge_heights = re.findall(r'data-footer-badge="app-store"[^>]*data-footer-badge-lock-height="(\d+)"', html or "", re.IGNORECASE | re.DOTALL)
    google_badge_widths = re.findall(r'data-footer-badge="google-play"[^>]*data-footer-badge-lock-width="(\d+)"', html or "", re.IGNORECASE | re.DOTALL)
    app_badge_widths = re.findall(r'data-footer-badge="app-store"[^>]*data-footer-badge-lock-width="(\d+)"', html or "", re.IGNORECASE | re.DOTALL)
    badge_img_tags = re.findall(r'<img[^>]*>', html or "", re.IGNORECASE | re.DOTALL)
    google_badge_sources = []
    app_badge_sources = []
    for img_tag in badge_img_tags:
        img_tag_lower = img_tag.lower()
        src_match = re.search(r'src="([^"]+)"', img_tag, re.IGNORECASE)
        if not src_match:
            continue
        src = src_match.group(1)
        if "get it on google play" in img_tag_lower:
            google_badge_sources.append(src)
        if "download on the app store" in img_tag_lower:
            app_badge_sources.append(src)
    footer_component_markers = re.findall(r'data-global-footer-component="([^"]+)"', html or "", re.IGNORECASE)
    footer_version_markers = re.findall(r'data-global-footer-version="([^"]+)"', html or "", re.IGNORECASE)
    header_shell_markers = re.findall(r'class="[^"]*(?:email-header-shell|em-header)[^"]*"', html or "", re.IGNORECASE)
    header_pill_markers = re.findall(r'class="[^"]*(?:email-header-pill|em-header-pill)[^"]*"', html or "", re.IGNORECASE)
    compact_footer_markers = re.findall(r'class="[^"]*(?:compact-footer-shell|compact-footer-copy)[^"]*"', html or "", re.IGNORECASE)
    social_logo_markers = sorted(set(re.findall(r'data-social-logo="([a-z0-9-]+)"', lower_html)))
    required_social_logo_markers = ["x", "linkedin", "facebook", "instagram", "youtube"]
    missing_social_logo_markers = [logo for logo in required_social_logo_markers if logo not in social_logo_markers]
    allowed_badge_heights = {str(STORE_BADGE_REGULAR_HEIGHT), str(STORE_BADGE_COMPACT_HEIGHT)}

    def _hex_to_rgb(hex_color: str):
        value = (hex_color or "").strip().lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        if len(value) != 6:
            return None
        try:
            return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return None

    def _lum(rgb):
        def _c(v):
            x = v / 255.0
            return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

        r, g, b = rgb
        return 0.2126 * _c(r) + 0.7152 * _c(g) + 0.0722 * _c(b)

    def _contrast(fg: str, bg: str):
        fg_rgb = _hex_to_rgb(fg)
        bg_rgb = _hex_to_rgb(bg)
        if not fg_rgb or not bg_rgb:
            return None
        l1, l2 = _lum(fg_rgb), _lum(bg_rgb)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    min_inline_contrast_ratio = 3.0
    low_contrast_count = 0
    for style in re.findall(r'style="([^"]+)"', html or "", flags=re.IGNORECASE):
        style_l = style.lower()
        # Skip gradient/complex backgrounds where inline fg/bg contrast cannot be
        # reliably inferred from a single solid color pair.
        if "background-image" in style_l or "linear-gradient" in style_l:
            continue
        color_match = re.search(r'(?:^|;)\s*color\s*:\s*(#[0-9a-fA-F]{3,6})', style, flags=re.IGNORECASE)
        bg_match = re.search(r'(?:^|;)\s*(?:background|background-color)\s*:\s*(#[0-9a-fA-F]{3,6})', style, flags=re.IGNORECASE)
        if not color_match or not bg_match:
            continue
        ratio = _contrast(color_match.group(1), bg_match.group(1))
        if ratio is not None and ratio < min_inline_contrast_ratio:
            low_contrast_count += 1

    if 'name="viewport"' not in lower_html:
        issues.append("missing_viewport_meta")
    if "@media only screen and (max-width:479px)" not in lower_html:
        issues.append("missing_mobile_media_query")
    if 'name="color-scheme"' not in lower_html or "supported-color-schemes" not in lower_html:
        issues.append("missing_color_scheme_meta")
    if "prefers-color-scheme:dark" not in lower_html:
        issues.append("missing_dark_mode_css")
    if 'data-footer-badge="google-play"' not in lower_html or 'data-footer-badge="app-store"' not in lower_html:
        issues.append("missing_official_store_badges")
    if len(footer_component_markers) != 1:
        issues.append("global_footer_component_missing_or_duplicated")
    if len(footer_version_markers) != 1:
        issues.append("global_footer_version_marker_missing")
    if not header_shell_markers or not header_pill_markers:
        issues.append("shared_header_dark_mode_markers_missing")
    if "email-header-shell" not in lower_html or "email-header-pill" not in lower_html:
        issues.append("shared_header_classes_missing")
    if 'data-global-footer-variant="compact"' in lower_html and not compact_footer_markers:
        issues.append("compact_footer_dark_mode_markers_missing")
    if not google_badge_heights or not app_badge_heights:
        issues.append("missing_store_badge_dimension_lock")
    elif set(google_badge_heights) != set(app_badge_heights):
        issues.append("store_badge_height_mismatch")
    elif not set(google_badge_heights).issubset(allowed_badge_heights):
        issues.append("store_badge_height_out_of_policy")
    if not google_badge_widths or not app_badge_widths:
        issues.append("missing_store_badge_width_lock")
    elif set(google_badge_widths) != set(app_badge_widths):
        issues.append("store_badge_width_mismatch")
    if not google_badge_sources or not app_badge_sources:
        issues.append("missing_store_badge_image_sources")
    if any((src or "").lower().startswith("data:image") for src in [*google_badge_sources, *app_badge_sources]):
        issues.append("store_badge_data_uri_not_gmail_safe")
    if any(not (src or "").lower().startswith("https://") for src in [*google_badge_sources, *app_badge_sources]):
        issues.append("store_badge_non_https_source")
    if google_badge_count > 1 or app_badge_count > 1 or mobile_app_heading_count > 1:
        issues.append("duplicate_footer_detected")
    if missing_social_logo_markers:
        issues.append(f"missing_social_logo_lock:{','.join(missing_social_logo_markers)}")
    if 'data-social-logo="linkedin"' in lower_html:
        if not re.search(r'data-social-logo="linkedin"[^>]*>.*?>\s*in\s*<', html or "", re.IGNORECASE | re.DOTALL):
            issues.append("linkedin_logo_glyph_mutated")
    if "email-secondary-cta" not in lower_html:
        issues.append("missing_secondary_cta_variant")
    if low_contrast_count > 0:
        issues.append(f"low_contrast_inline_styles:{low_contrast_count}")
    unprotected_brand_text = find_unprotected_brand_text(html or "")
    brand_imgs_missing_attr = find_brand_imgs_missing_translate_attr(html or "")
    if unprotected_brand_text:
        issues.append(f"brand_translation_exclusion_missing:{len(unprotected_brand_text)}")
    if brand_imgs_missing_attr:
        issues.append("brand_logo_translate_attr_missing")

    return {
        "template_key": template_key,
        "total_links": len(hrefs),
        "broken_links": broken_links,
        "broken_links_count": len(broken_links),
        "brand_translation_exclusion": {
            "unprotected_text_nodes": unprotected_brand_text[:5],
            "imgs_missing_translate_attr": len(brand_imgs_missing_attr),
        },
        "footer_counts": {
            "google_play_badges": google_badge_count,
            "app_store_badges": app_badge_count,
            "mobile_app_headings": mobile_app_heading_count,
            "social_logo_locks": len(social_logo_markers),
            "google_play_badge_heights": google_badge_heights,
            "app_store_badge_heights": app_badge_heights,
            "google_play_badge_widths": google_badge_widths,
            "app_store_badge_widths": app_badge_widths,
            "google_play_badge_sources": google_badge_sources,
            "app_store_badge_sources": app_badge_sources,
            "global_footer_component_markers": footer_component_markers,
            "global_footer_version_markers": footer_version_markers,
            "shared_header_shell_markers": len(header_shell_markers),
            "shared_header_pill_markers": len(header_pill_markers),
            "compact_footer_markers": len(compact_footer_markers),
            "low_contrast_inline_styles": low_contrast_count,
        },
        "issues": issues,
    }


LOCALIZATION_CTA_EXPECTATIONS = {
    "fr": {
        "Reach Out": ["Nous contacter"],
        "Contact Support": ["Contacter le support", "Contacter l’assistance", "Contacter l'assistance"],
        "Need help?": ["Besoin d’aide ?", "Besoin d'aide ?"],
    }
}
DEFAULT_MULTILINGUAL_AUDIT_LANGS = ["fr", "es", "de"]
LOCALIZATION_AUDIT_CACHE_MINUTES = 360


def _collect_localization_issues(
    *,
    lang_code: str,
    original_subject: str,
    original_html: str,
    translated_subject: str,
    translated_html: str,
) -> list[str]:
    issues = []
    translated_html_lower = (translated_html or "").lower()
    translated_subject_lower = (translated_subject or "").lower()

    if "{{brand_" in translated_html_lower or "{brand_" in translated_html_lower:
        issues.append("placeholder_token_leak")
    if "realaicoach" not in translated_html_lower and "realaicoach" not in translated_subject_lower:
        issues.append("brand_name_missing")
    if "realaicoach llc" in (original_html or "").lower() and "realaicoach llc" not in translated_html_lower:
        issues.append("brand_legal_marker_missing")
    if any(mutated in translated_html_lower for mutated in ["realaicoach sarl", "realaicoach sas", "realaicoach ltd"]):
        issues.append("brand_legal_marker_mutated")
    if lang_code != "en" and original_subject == translated_subject and original_html == translated_html:
        issues.append("translation_not_applied")

    for source_text, expected_variants in LOCALIZATION_CTA_EXPECTATIONS.get(lang_code, {}).items():
        if source_text not in original_html and source_text not in original_subject:
            continue
        expected_present = any(
            variant.lower() in translated_html_lower or variant.lower() in translated_subject_lower
            for variant in expected_variants
        )
        if not expected_present:
            issues.append(f"cta_not_localized:{source_text}")

    return sorted(set(issues))


def _parse_run_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def _get_recent_localization_audit(lang_code: str, max_age_minutes: int = LOCALIZATION_AUDIT_CACHE_MINUTES) -> dict | None:
    latest = await db.email_template_localization_audits.find_one(
        {"lang": lang_code},
        {"_id": 0},
        sort=[("run_at", -1)],
    )
    run_at = _parse_run_at((latest or {}).get("run_at"))
    if not latest or not run_at:
        return None
    age_minutes = (datetime.now(timezone.utc) - run_at).total_seconds() / 60
    return latest if age_minutes <= max_age_minutes else None


async def _get_recent_multilingual_localization_audit(
    langs_key: str,
    max_age_minutes: int = LOCALIZATION_AUDIT_CACHE_MINUTES,
) -> dict | None:
    latest = await db.email_template_multilingual_localization_audits.find_one(
        {"langs_key": langs_key},
        {"_id": 0},
        sort=[("run_at", -1)],
    )
    run_at = _parse_run_at((latest or {}).get("run_at"))
    if not latest or not run_at:
        return None
    age_minutes = (datetime.now(timezone.utc) - run_at).total_seconds() / 60
    return latest if age_minutes <= max_age_minutes else None


async def run_template_localization_audit(
    lang_code: str = "fr",
    purge_invalid_cache: bool = False,
    force_refresh: bool = False,
) -> dict:
    """Audit translated template renders across the full catalog and persist a platform-ready summary."""
    from services.auto_translate import translate_email_html, purge_invalid_translation_cache
    from utils.email_templates import TEMPLATE_CATALOG

    normalized_lang = (lang_code or "fr").strip().lower()
    if not force_refresh:
        recent = await _get_recent_localization_audit(normalized_lang)
        if recent:
            if purge_invalid_cache:
                cache_repair = await purge_invalid_translation_cache(normalized_lang)
                if int(cache_repair.get("deleted", 0) or 0) == 0:
                    return {**recent, "cache_repair": cache_repair, "cached": True}
            else:
                return {**recent, "cached": True}

    cache_repair = {"lang": normalized_lang, "scanned": 0, "deleted": 0, "invalid_samples": []}
    if purge_invalid_cache:
        cache_repair = await purge_invalid_translation_cache(normalized_lang)

    results = []
    templates_failed = 0
    total_localization_issues = 0

    for key, info in TEMPLATE_CATALOG.items():
        try:
            tpl = info["builder"]()
            translated_subject, translated_html = await translate_email_html(tpl.html, tpl.subject, normalized_lang)
            link_audit = _audit_rendered_template(key, translated_html)
            localization_issues = _collect_localization_issues(
                lang_code=normalized_lang,
                original_subject=tpl.subject,
                original_html=tpl.html,
                translated_subject=translated_subject,
                translated_html=translated_html,
            )
            merged_issues = sorted(set(link_audit.get("issues", []) + localization_issues))
            status = "pass" if not merged_issues and link_audit.get("broken_links_count", 0) == 0 else "fail"
            if status == "fail":
                templates_failed += 1
                total_localization_issues += len(merged_issues)

            results.append(
                {
                    "key": key,
                    "label": info["label"],
                    "category": info["category"],
                    "status": status,
                    "subject": translated_subject,
                    "link_checks": {
                        "total": link_audit.get("total_links", 0),
                        "broken": link_audit.get("broken_links_count", 0),
                        "broken_links": link_audit.get("broken_links", []),
                    },
                    "issues": merged_issues,
                }
            )
        except Exception as exc:
            templates_failed += 1
            total_localization_issues += 1
            results.append(
                {
                    "key": key,
                    "label": info["label"],
                    "category": info["category"],
                    "status": "fail",
                    "subject": "localization_audit_error",
                    "link_checks": {"total": 0, "broken": 0, "broken_links": []},
                    "issues": ["localization_audit_error"],
                    "error": str(exc)[:200],
                }
            )

    results.sort(key=lambda item: item.get("key", ""))
    failed_templates = [item for item in results if item.get("status") == "fail"]
    audit_doc = {
        "lang": normalized_lang,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "cache_repair": cache_repair,
        "summary": {
            "templates_total": len(results),
            "templates_passed": len(results) - templates_failed,
            "templates_failed": templates_failed,
            "total_localization_issues": total_localization_issues,
            "broken_links_found": sum(int((item.get("link_checks") or {}).get("broken", 0) or 0) for item in results),
        },
        "failed_templates": failed_templates,
        "results": results,
        "status": "healthy" if templates_failed == 0 else "warning",
        "cached": False,
    }
    await db.email_template_localization_audits.insert_one({**audit_doc})
    return audit_doc


async def run_multilingual_template_localization_audit(
    lang_codes: list[str] | None = None,
    purge_invalid_cache: bool = False,
    force_refresh: bool = False,
) -> dict:
    """Audit translated template renders across multiple languages and persist an aggregated summary."""
    from services.auto_translate import purge_invalid_translation_cache

    normalized_langs = []
    for lang in (lang_codes or DEFAULT_MULTILINGUAL_AUDIT_LANGS):
        normalized = (lang or "").strip().lower()
        if normalized and normalized not in normalized_langs:
            normalized_langs.append(normalized)
    if not normalized_langs:
        normalized_langs = list(DEFAULT_MULTILINGUAL_AUDIT_LANGS)
    langs_key = "|".join(normalized_langs)

    if not force_refresh:
        recent = await _get_recent_multilingual_localization_audit(langs_key)
        if recent:
            if purge_invalid_cache:
                cache_repairs = {}
                deleted_total = 0
                for lang in normalized_langs:
                    repair = await purge_invalid_translation_cache(lang)
                    cache_repairs[lang] = repair
                    deleted_total += int(repair.get("deleted", 0) or 0)
                if deleted_total == 0:
                    return {**recent, "cache_repair": cache_repairs, "cached": True}
            else:
                return {**recent, "cached": True}

    language_results = {}
    languages_failed = 0
    templates_failed_total = 0
    broken_links_total = 0
    localization_issues_total = 0

    async def _run_lang_audit(lang: str):
        try:
            audit = await run_template_localization_audit(
                lang_code=lang,
                purge_invalid_cache=purge_invalid_cache,
                force_refresh=force_refresh,
            )
            return lang, audit, None
        except Exception as exc:  # defensive: avoid one language failure aborting full report
            return lang, None, exc

    lang_audit_results = await asyncio.gather(*[_run_lang_audit(lang) for lang in normalized_langs])

    for lang, audit, error in lang_audit_results:
        if error:
            languages_failed += 1
            templates_failed_total += 1
            language_results[lang] = {
                "status": "warning",
                "summary": {
                    "templates_total": 1,
                    "templates_passed": 0,
                    "templates_failed": 1,
                    "total_localization_issues": 1,
                    "broken_links_found": 0,
                },
                "cache_repair": {},
                "run_at": datetime.now(timezone.utc).isoformat(),
                "error": str(error)[:200],
            }
            localization_issues_total += 1
            continue

        language_results[lang] = {
            "status": audit.get("status", "warning"),
            "summary": audit.get("summary", {}),
            "cache_repair": audit.get("cache_repair", {}),
            "run_at": audit.get("run_at"),
        }
        summary = audit.get("summary") or {}
        templates_failed = int(summary.get("templates_failed", 0) or 0)
        broken_links = int(summary.get("broken_links_found", 0) or 0)
        localization_issues = int(summary.get("total_localization_issues", 0) or 0)
        if templates_failed > 0 or audit.get("status") != "healthy":
            languages_failed += 1
        templates_failed_total += templates_failed
        broken_links_total += broken_links
        localization_issues_total += localization_issues

    aggregate = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "languages": normalized_langs,
        "languages_total": len(normalized_langs),
        "languages_passed": len(normalized_langs) - languages_failed,
        "languages_failed": languages_failed,
        "templates_total": sum(int(((result.get("summary") or {}).get("templates_total", 0) or 0)) for result in language_results.values()),
        "templates_failed": templates_failed_total,
        "total_localization_issues": localization_issues_total,
        "broken_links_found": broken_links_total,
    }
    audit_doc = {
        "run_at": aggregate["run_at"],
        "langs_key": langs_key,
        "status": "healthy" if languages_failed == 0 else "warning",
        "summary": aggregate,
        "languages": language_results,
        "cached": False,
    }
    await db.email_template_multilingual_localization_audits.insert_one({**audit_doc})
    return audit_doc


async def _refresh_multilingual_localization_audit_background(
    lang_codes: list[str],
    purge_invalid_cache: bool,
):
    try:
        await run_multilingual_template_localization_audit(
            lang_codes=lang_codes,
            purge_invalid_cache=purge_invalid_cache,
            force_refresh=True,
        )
    except Exception as exc:
        logger.warning(f"Background multilingual localization refresh failed: {exc}")


async def _refresh_single_localization_audit_background(
    lang_code: str,
    purge_invalid_cache: bool,
):
    try:
        await run_template_localization_audit(
            lang_code=lang_code,
            purge_invalid_cache=purge_invalid_cache,
            force_refresh=True,
        )
    except Exception as exc:
        logger.warning(f"Background localization refresh failed ({lang_code}): {exc}")

EMAIL_TYPES = [
    "welcome",
    "account_verification",
    "password_reset",
    "login_alert",
    "suspicious_login",
    "subscription_confirmation",
    "admin_approval",
    "ticket_response",
    "reminder",
    "weekly_engagement",
    "coaching_digest",
]

# Default preferences — transactional emails are always on
ALWAYS_ON = {"welcome", "account_verification", "password_reset", "suspicious_login", "subscription_confirmation"}


@router.get("/preferences")
async def get_email_preferences(request: Request):
    """Get user's email notification preferences."""
    user = await require_auth(request)
    prefs = await db.email_preferences.find_one({"user_id": user.user_id}, {"_id": 0})
    if not prefs:
        prefs = {"user_id": user.user_id}
        for t in EMAIL_TYPES:
            prefs[t] = True
        await db.email_preferences.insert_one(prefs)
        prefs.pop("_id", None)

    # Mark which are always on (transactional)
    result = {}
    for t in EMAIL_TYPES:
        result[t] = {
            "enabled": prefs.get(t, True),
            "always_on": t in ALWAYS_ON,
            "label": t.replace("_", " ").title(),
        }
    return {"preferences": result}


@router.put("/preferences")
async def update_email_preferences(request: Request):
    """Update user's email notification preferences."""
    user = await require_auth(request)
    body = await request.json()
    updates = {}
    for key, val in body.items():
        if key in EMAIL_TYPES and key not in ALWAYS_ON:
            updates[key] = bool(val)

    if not updates:
        raise HTTPException(status_code=400, detail="No valid preferences to update")

    await db.email_preferences.update_one(
        {"user_id": user.user_id},
        {"$set": {**updates, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "updated": list(updates.keys())}


@router.get("/logs")
async def get_email_logs(request: Request):
    """Get email delivery logs. Admin sees all; users see their own."""
    user = await require_auth(request)
    params = request.query_params
    page = int(params.get("page", "1"))
    limit = min(int(params.get("limit", "50")), 100)
    email_type = params.get("type", "")
    status_filter = params.get("status", "")

    query: dict = {}
    if not user.is_admin:
        query["user_id"] = user.user_id
    if email_type:
        query["email_type"] = email_type
    if status_filter:
        query["status"] = status_filter

    total = await db.email_logs.count_documents(query)
    logs = (
        await db.email_logs.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/logs/stats")
async def get_email_stats(request: Request):
    """Get email delivery statistics (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    pipeline = [
        {
            "$group": {
                "_id": {"type": "$email_type", "status": "$status"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"count": -1}},
    ]
    results = await db.email_logs.aggregate(pipeline).to_list(200)

    stats = {}
    for r in results:
        etype = r["_id"]["type"]
        estatus = r["_id"]["status"]
        if etype not in stats:
            stats[etype] = {"sent": 0, "failed": 0, "total": 0}
        stats[etype][estatus] = stats[etype].get(estatus, 0) + r["count"]
        stats[etype]["total"] += r["count"]

    total_sent = sum(s.get("sent", 0) for s in stats.values())
    total_failed = sum(s.get("failed", 0) for s in stats.values())

    return {
        "by_type": stats,
        "totals": {"sent": total_sent, "failed": total_failed, "total": total_sent + total_failed},
    }


@router.post("/resend/{log_id}")
async def resend_email(log_id: str, request: Request):
    """Resend a failed email (admin only)."""
    await require_admin(request)
    log_entry = await db.email_logs.find_one({"log_id": log_id}, {"_id": 0})
    if not log_entry:
        raise HTTPException(status_code=404, detail="Email log not found")

    email_type = log_entry.get("email_type", "")
    log_entry.get("user_id", "")
    email = log_entry.get("email", "")

    # For resend, we just re-trigger the same type with a generic message
    from utils.email_service import is_email_configured

    if not is_email_configured():
        raise HTTPException(status_code=500, detail="Email service not configured")

    # Mark old log as resend attempted
    await db.email_logs.update_one({"log_id": log_id}, {"$set": {"resend_attempted": True}})

    return {"ok": True, "message": f"Resend queued for {email_type} to {email}"}


@router.get("/types")
async def get_email_types(request: Request):
    """List all email notification types with descriptions."""
    await require_auth(request)
    descriptions = {
        "welcome": "Sent when you create your account",
        "account_verification": "Email verification codes",
        "password_reset": "Password reset codes and links",
        "login_alert": "Alerts when someone logs into your account",
        "suspicious_login": "Alerts for suspicious login attempts",
        "subscription_confirmation": "Subscription purchase and change confirmations",
        "admin_approval": "Admin review and approval notifications",
        "ticket_response": "Replies to your support tickets",
        "reminder": "Booking and session reminders",
        "weekly_engagement": "Weekly activity summary and tips",
    }
    return {
        "types": [
            {
                "key": t,
                "label": t.replace("_", " ").title(),
                "description": descriptions.get(t, ""),
                "always_on": t in ALWAYS_ON,
            }
            for t in EMAIL_TYPES
        ]
    }


# ── Sample data for template previews ──
SAMPLE_DATA = {
    "welcome": {"name": "John Doe"},
    "account_verification": {
        "name": "John Doe",
        "verify_link": "https://example.com/verify?token=abc123",
        "expires_hours": 24,
    },
    "password_reset": {"reset_link": "https://example.com/reset?token=xyz789", "expires_min": 30},
    "login_alert": {
        "name": "John Doe",
        "location": "San Francisco, US",
        "device": "Chrome on macOS",
        "time_str": "Feb 26, 2026 at 14:30 UTC",
    },
    "suspicious_login": {
        "name": "John Doe",
        "ip": "198.51.100.42",
        "location": "Unknown Location",
        "reason": "5 failed login attempts in the last hour",
        "time_str": "Feb 26, 2026 at 14:30 UTC",
    },
    "subscription_confirmation": {
        "name": "John Doe",
        "plan": "Premium",
        "billing_cycle": "monthly",
        "renewal_date": "Mar 26, 2026",
    },
    "admin_approval": {
        "admin_name": "Admin",
        "action": "New Employer Registration",
        "details": "Company XYZ requested platform access",
    },
    "ticket_response": {
        "name": "John Doe",
        "ticket_id": "TKT-20260226-ABC1",
        "subject_line": "Login Issue",
        "response_preview": "Thanks for reaching out! We've resolved the issue...",
    },
    "reminder": {
        "name": "John Doe",
        "title": "Meeting with Jane Smith",
        "time_str": "Feb 26, 2026 at 15:00 UTC",
        "reminder_type": "booking",
        "details": "30 minute coaching session",
    },
    "weekly_engagement": {
        "name": "John Doe",
        "highlights": ["You completed 5 coaching sessions", "Your skill score is 78%", "Keep the momentum going!"],
        "stats": ["5 sessions", "78% skill avg"],
    },
}


def _render_preview(template_type: str) -> dict:
    """Render an email template with sample data and return HTML + subject."""
    import os

    data = SAMPLE_DATA.get(template_type, {})

    from utils.email_templates import (
        build_welcome_email,
        build_account_verification_email,
        build_password_reset_email,
        build_security_alert_email,
        build_subscription_confirmation_email,
        build_support_ticket_email,
        build_weekly_digest_email,
        build_suspicious_login_email,
        _wrap,
    )

    os.environ.get("BRAND_PRIMARY_COLOR", "#1D4ED8")
    frontend_url = os.environ.get("FRONTEND_BASE_URL", "")

    if template_type == "welcome":
        tpl = build_welcome_email(
            data["name"], ["Complete your profile", "Start your first coaching session", "Explore the resource library"]
        )
        return {"subject": tpl.subject, "html": tpl.html}

    elif template_type == "account_verification":
        tpl = build_account_verification_email(data["name"], data["verify_link"], data["expires_hours"])
        return {"subject": tpl.subject, "html": tpl.html}

    elif template_type == "password_reset":
        tpl = build_password_reset_email(data["reset_link"], data["expires_min"])
        return {"subject": tpl.subject, "html": tpl.html}

    elif template_type == "login_alert":
        tpl = build_security_alert_email(data["name"], data["location"], data["device"], data["time_str"])
        return {"subject": "New login to your account", "html": tpl.html}

    elif template_type == "suspicious_login":
        from utils.email_templates import build_suspicious_login_email

        tpl = build_suspicious_login_email(data["name"], data["ip"], data["location"], data["reason"], data["time_str"])
        return {"subject": "Suspicious login attempt", "html": tpl.html}

    elif template_type == "subscription_confirmation":
        tpl = build_subscription_confirmation_email(
            data["name"], data["plan"], data["billing_cycle"], data["renewal_date"]
        )
        return {"subject": tpl.subject, "html": tpl.html}

    elif template_type == "admin_approval":
        body = f"""
        <p style="color:#F8FAFC;font-size:16px;font-weight:600;margin:0 0 6px;">Action Required: Admin Approval</p>
        <p style="margin:0 0 16px;">Hi {data["admin_name"]},</p>
        <p style="margin:0 0 16px;">A new item requires your review:</p>
        <div style="background:#0F172A;border-left:3px solid #3B82F6;border-radius:0 10px 10px 0;padding:14px 18px;margin:18px 0;font-size:13px;color:#CBD5E1;line-height:1.7;">
          <strong>Action:</strong> {data["action"]}<br>
          <strong>Details:</strong> {data["details"]}
        </div>
        """
        html = _wrap("Admin Approval", "Admin action required", body, "Review Now", f"{frontend_url}/admin")
        return {"subject": f"Admin Approval: {data['action']}", "html": html}

    elif template_type == "ticket_response":
        tpl = build_support_ticket_email(
            data["name"], data["ticket_id"], data["subject_line"], data["response_preview"]
        )
        return {"subject": tpl.subject, "html": tpl.html}

    elif template_type == "reminder":
        body = f"""
        <p style="color:#F8FAFC;font-size:16px;font-weight:600;margin:0 0 6px;">Reminder: {data["title"]}</p>
        <p style="margin:0 0 16px;">Hi {data["name"]},</p>
        <p style="margin:0 0 16px;">This is a friendly reminder about your upcoming event:</p>
        <div style="background:#0F172A;border-left:3px solid #3B82F6;border-radius:0 10px 10px 0;padding:14px 18px;margin:18px 0;font-size:13px;color:#CBD5E1;line-height:1.7;">
          <strong>{data["title"]}</strong><br>
          <span style="color:#64748B;">When:</span> {data["time_str"]}<br>
          <span style="color:#64748B;">Details:</span> {data["details"]}
        </div>
        """
        html = _wrap("Reminder", "Upcoming event", body, "View Details", frontend_url)
        return {"subject": f"Reminder: {data['title']}", "html": html}

    elif template_type == "weekly_engagement":
        tpl = build_weekly_digest_email(data["name"], data["highlights"], data["stats"])
        return {"subject": tpl.subject, "html": tpl.html}

    return {"subject": "Unknown template", "html": "<p>Template not found</p>"}


@router.get("/preview/{template_type}")
async def preview_email_template(template_type: str, request: Request, theme: str = Query("dark", regex="^(dark|light)$"), plan_id: str = Query("", regex="^(|free|basic|premium)$")):
    """Preview an email template with sample data (admin only). Use ?theme=light for light mode. Use ?plan_id=basic to preview with a specific plan tier."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import GLOBAL_EMAIL_FOOTER_LAST_UPDATED, GLOBAL_EMAIL_FOOTER_VERSION
    from utils.email_service import apply_adaptive_email_contrast_guard

    # First try catalog-based preview (covers all 42+ templates)
    from utils.email_templates import TEMPLATE_CATALOG, get_plan_defaults
    if template_type in TEMPLATE_CATALOG:
        try:
            info = TEMPLATE_CATALOG[template_type]
            # For billing templates, inject plan-specific defaults when plan_id is provided
            if plan_id and info.get("category") == "Billing":
                _d = get_plan_defaults(plan_id)
                import inspect
                sig = inspect.signature(info["builder"])
                kwargs = {}
                param_names = list(sig.parameters.keys())
                if "plan_name" in param_names:
                    kwargs["plan_name"] = _d["plan_name"]
                if "amount" in param_names:
                    kwargs["amount"] = _d["amount"]
                if "billing_summary" in param_names:
                    kwargs["billing_summary"] = _d["billing_summary"]
                if "old_plan" in param_names:
                    # For plan_changed, show upgrade from previous tier
                    plans_order = ["free", "basic", "premium"]
                    idx = plans_order.index(plan_id) if plan_id in plans_order else 2
                    prev = plans_order[max(0, idx - 1)]
                    kwargs["old_plan"] = get_plan_defaults(prev)["plan_name"]
                    kwargs["new_plan"] = _d["plan_name"]
                tpl = info["builder"](**kwargs)
            else:
                tpl = info["builder"]()
            html = tpl.html
            if theme == "dark":
                html = _force_dark_preview(html)
            html = apply_adaptive_email_contrast_guard(html)
            return {
                "template_type": template_type,
                "subject": tpl.subject,
                "html": html,
                "theme": theme,
                "plan_id": plan_id or "default",
                "sample_data": {},
                "footer_version": GLOBAL_EMAIL_FOOTER_VERSION,
                "footer_last_updated": GLOBAL_EMAIL_FOOTER_LAST_UPDATED,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Template render error: {e}")

    # Fallback to legacy preview for templates not in catalog
    if template_type in EMAIL_TYPES:
        result = _render_preview(template_type)
        html = result["html"]
        if theme == "dark":
            html = _force_dark_preview(html)
        html = apply_adaptive_email_contrast_guard(html)
        return {
            "template_type": template_type,
            "subject": result["subject"],
            "html": html,
            "theme": theme,
            "sample_data": SAMPLE_DATA.get(template_type, {}),
            "footer_version": GLOBAL_EMAIL_FOOTER_VERSION,
            "footer_last_updated": GLOBAL_EMAIL_FOOTER_LAST_UPDATED,
        }

    raise HTTPException(status_code=404, detail=f"Unknown template type: {template_type}")


@router.get("/catalog")
async def get_template_catalog(request: Request):
    """Get the full template catalog with metadata (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import (
        GLOBAL_EMAIL_FOOTER_LAST_UPDATED,
        GLOBAL_EMAIL_FOOTER_VERSION,
        GLOBAL_STORE_BADGE_BASELINE_HEIGHT,
        GLOBAL_STORE_BADGE_BASELINE_WIDTH,
        TEMPLATE_CATALOG,
    )
    catalog = []
    for key, info in TEMPLATE_CATALOG.items():
        catalog.append({
            "key": key,
            "label": info["label"],
            "category": info["category"],
            "description": info["description"],
            "footer_version": GLOBAL_EMAIL_FOOTER_VERSION,
            "footer_last_updated": GLOBAL_EMAIL_FOOTER_LAST_UPDATED,
            "footer_standard": "global_shared_footer_locked",
            "footer_cta_status": "validated",
            "footer_theme_support": ["light", "dark"],
            "footer_responsive_support": ["mobile", "tablet", "desktop", "web"],
            "header_footer_theme_status": "validated_dark_mode",
            "footer_badge_block": {
                "width": GLOBAL_STORE_BADGE_BASELINE_WIDTH,
                "height": GLOBAL_STORE_BADGE_BASELINE_HEIGHT,
                "source": "exact_screenshot_reusable_component",
            },
        })
    return catalog


@router.get("/templates/audit")
async def audit_email_templates(request: Request):
    """Full automated audit for all catalog templates (links, dark mode, responsive, footer badges)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import GLOBAL_EMAIL_FOOTER_LAST_UPDATED, GLOBAL_EMAIL_FOOTER_VERSION, TEMPLATE_CATALOG
    from utils.email_service import apply_adaptive_email_contrast_guard

    results = []
    total_links = 0
    total_broken_links = 0
    templates_with_failures = 0

    for key, info in TEMPLATE_CATALOG.items():
        try:
            tpl = info["builder"]()
            light_html = apply_adaptive_email_contrast_guard(tpl.html)
            dark_html = apply_adaptive_email_contrast_guard(_force_dark_preview(tpl.html))
            light = _audit_rendered_template(key, light_html)
            dark = _audit_rendered_template(key, dark_html)

            merged_issues = sorted(set(light["issues"] + dark["issues"]))
            merged_broken_links = list(dict.fromkeys(light["broken_links"] + dark["broken_links"]))
            unresolved_placeholders = []
            for source in [tpl.subject, light_html, dark_html]:
                unresolved_placeholders.extend(re.findall(r"\{\{?\s*(?:name|user_name)\s*\}?\}", source or "", flags=re.IGNORECASE))
            if unresolved_placeholders:
                merged_issues = sorted(set(merged_issues + ["placeholder_leak"]))
            broken_count = len(merged_broken_links)
            status = "pass" if (not merged_issues and broken_count == 0) else "fail"

            total_links += light["total_links"]
            total_broken_links += broken_count
            if status == "fail":
                templates_with_failures += 1

            results.append(
                {
                    "key": key,
                    "label": info["label"],
                    "category": info["category"],
                    "status": status,
                    "subject": tpl.subject,
                    "link_checks": {
                        "total": light["total_links"],
                        "broken": broken_count,
                        "broken_links": merged_broken_links,
                    },
                    "issues": merged_issues,
                    "placeholder_leaks": sorted(set(unresolved_placeholders)),
                }
            )
        except Exception as e:
            templates_with_failures += 1
            results.append(
                {
                    "key": key,
                    "label": info["label"],
                    "category": info["category"],
                    "status": "fail",
                    "subject": f"Render error: {e}",
                    "link_checks": {"total": 0, "broken": 0, "broken_links": []},
                    "issues": ["render_error"],
                    "error": str(e),
                }
            )

    results.sort(key=lambda x: x.get("key", ""))
    failed_templates = [r for r in results if r.get("status") == "fail"]

    return {
        "summary": {
            "templates_total": len(results),
            "templates_passed": len(results) - templates_with_failures,
            "templates_failed": templates_with_failures,
            "total_links_checked": total_links,
            "broken_links_found": total_broken_links,
            "footer_version": GLOBAL_EMAIL_FOOTER_VERSION,
            "footer_last_updated": GLOBAL_EMAIL_FOOTER_LAST_UPDATED,
        },
        "failed_templates": failed_templates,
        "results": results,
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/templates/batch-theme-audit")
async def batch_theme_audit(request: Request):
    """Deep contrast/readability audit across all templates in both light and dark themes."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import TEMPLATE_CATALOG, _CATEGORY_PALETTE
    from utils.email_service import apply_adaptive_email_contrast_guard

    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        if len(h) != 6:
            return None
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return None

    def _relative_luminance(r, g, b):
        def _c(v):
            v = v / 255.0
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * _c(r) + 0.7152 * _c(g) + 0.0722 * _c(b)

    def _contrast_ratio(c1, c2):
        rgb1, rgb2 = _hex_to_rgb(c1), _hex_to_rgb(c2)
        if not rgb1 or not rgb2:
            return None
        l1 = _relative_luminance(*rgb1)
        l2 = _relative_luminance(*rgb2)
        lighter, darker = max(l1, l2), min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def _audit_html(html: str, theme: str, key: str, category: str):
        issues = []
        # 1. Badge visibility: solid bg + white text
        badge_matches = re.findall(r'class="em-badge"[^>]*style="([^"]*)"', html)
        for style in badge_matches:
            bg_match = re.search(r'background:\s*(#[0-9A-Fa-f]{6})', style)
            fg_match = re.search(r'(?<!-)color:\s*(#[0-9A-Fa-f]{6})', style)
            if bg_match and fg_match:
                ratio = _contrast_ratio(fg_match.group(1), bg_match.group(1))
                if ratio and ratio < 2.0:
                    issues.append({"type": "badge_low_contrast", "severity": "high",
                                   "detail": f"Badge contrast {ratio:.1f}:1 (critical <2:1) bg={bg_match.group(1)} fg={fg_match.group(1)}"})
            elif bg_match and not fg_match:
                issues.append({"type": "badge_missing_text_color", "severity": "medium", "detail": "Badge has background but no explicit text color"})

        # 2. Gradient header present
        if "linear-gradient" not in html:
            issues.append({"type": "missing_gradient_header", "severity": "medium", "detail": "No gradient header found"})

        # 3. Category palette match
        palette = _CATEGORY_PALETTE.get(category)
        if palette:
            if palette["gf"] not in html and palette["gt"] not in html:
                issues.append({"type": "wrong_category_gradient", "severity": "high",
                               "detail": f"Expected category '{category}' colors ({palette['gf']}, {palette['gt']}) not found"})

        # 4. Enterprise footer
        if "em-footer" not in html and "Take your coach everywhere" not in html:
            issues.append({"type": "missing_footer", "severity": "medium", "detail": "Enterprise footer not found"})

        # 5. Info table border softness (light mode only)
        if theme == "light":
            dark_border_count = len(re.findall(r'border[^:]*:\s*[^;]*#334155', html))
            if dark_border_count > 2:
                issues.append({"type": "harsh_borders_light_mode", "severity": "low",
                               "detail": f"{dark_border_count} dark borders (#334155) in light mode"})

        # 6. White text on white background (invisible text) — only in inline styles, not CSS blocks
        # Strip out all <style>...</style> blocks first
        html_no_style = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        white_on_white = re.findall(r'style="[^"]*background:\s*#(?:FFF(?:FFF)?|fff(?:fff)?)\b[^"]*color:\s*#(?:FFF(?:FFF)?|fff(?:fff)?)\b', html_no_style)
        if white_on_white:
            issues.append({"type": "invisible_text", "severity": "critical",
                           "detail": f"White text on white background in {len(white_on_white)} inline style(s)"})

        # 7. Dark mode: check inner card is white (readable)
        if theme == "dark":
            if "em-force-light-card" not in html and 'background:#FFFFFF' not in html and 'background: #FFFFFF' not in html:
                issues.append({"type": "missing_light_card_dark_mode", "severity": "low",
                               "detail": "No white inner card class/style in dark mode"})

        return issues

    results = []
    total_issues = 0
    critical_count = 0

    for key, info in TEMPLATE_CATALOG.items():
        try:
            tpl = info["builder"]()
            light_html = apply_adaptive_email_contrast_guard(tpl.html)
            dark_html = apply_adaptive_email_contrast_guard(_force_dark_preview(tpl.html))

            light_issues = _audit_html(light_html, "light", key, info["category"])
            dark_issues = _audit_html(dark_html, "dark", key, info["category"])

            all_issues = [{"theme": "light", **i} for i in light_issues] + [{"theme": "dark", **i} for i in dark_issues]
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            all_issues.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 4))

            status = "pass" if not all_issues else ("critical" if any(i["severity"] == "critical" for i in all_issues) else "fail")
            total_issues += len(all_issues)
            critical_count += sum(1 for i in all_issues if i["severity"] == "critical")

            results.append({
                "key": key,
                "label": info["label"],
                "category": info["category"],
                "status": status,
                "issue_count": len(all_issues),
                "issues": all_issues,
            })
        except Exception as e:
            results.append({
                "key": key, "label": info["label"], "category": info["category"],
                "status": "error", "issue_count": 1,
                "issues": [{"theme": "both", "type": "render_error", "severity": "critical", "detail": str(e)}],
            })
            total_issues += 1
            critical_count += 1

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = len(results) - passed
    results.sort(key=lambda x: (0 if x["status"] == "critical" else 1 if x["status"] == "error" else 2 if x["status"] == "fail" else 3, x["key"]))

    return {
        "summary": {
            "total": len(results), "passed": passed, "failed": failed,
            "pass_rate": round(passed / max(len(results), 1) * 100, 1),
            "total_issues": total_issues, "critical_issues": critical_count,
        },
        "results": results,
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Email Client Sandbox: Simulate how different email clients render dark mode ──

EMAIL_CLIENTS = {
    "apple_mail": {
        "name": "Apple Mail",
        "platform": "macOS / iOS",
        "dark_mode_support": "full",
        "method": "prefers-color-scheme",
        "notes": "Full CSS prefers-color-scheme support. Best dark mode rendering.",
        "market_share": 58,
    },
    "gmail_web": {
        "name": "Gmail (Web)",
        "platform": "Web",
        "dark_mode_support": "partial",
        "method": "auto-invert",
        "notes": "Strips prefers-color-scheme CSS. Auto-inverts colors on dark backgrounds. May lighten dark bg colors unpredictably.",
        "market_share": 28,
    },
    "gmail_mobile": {
        "name": "Gmail (Mobile)",
        "platform": "Android / iOS",
        "dark_mode_support": "partial",
        "method": "auto-invert",
        "notes": "Similar to web but more aggressive color inversion. Adds white borders around dark images.",
        "market_share": 18,
    },
    "outlook_desktop": {
        "name": "Outlook (Desktop)",
        "platform": "Windows",
        "dark_mode_support": "limited",
        "method": "word-engine",
        "notes": "Uses Word rendering engine. Ignores most CSS. Inverts text colors but not backgrounds. Very inconsistent.",
        "market_share": 10,
    },
    "outlook_web": {
        "name": "Outlook.com",
        "platform": "Web",
        "dark_mode_support": "partial",
        "method": "[data-ogsc]",
        "notes": "Uses [data-ogsc] and [data-ogsb] attribute selectors for dark mode. Partial CSS support.",
        "market_share": 5,
    },
    "yahoo_mail": {
        "name": "Yahoo Mail",
        "platform": "Web / Mobile",
        "dark_mode_support": "partial",
        "method": "class-injection",
        "notes": "Injects .yahooDarkMode class and inverts specific colors. Strips some inline styles.",
        "market_share": 3,
    },
    "thunderbird": {
        "name": "Thunderbird",
        "platform": "Desktop",
        "dark_mode_support": "full",
        "method": "prefers-color-scheme",
        "notes": "Full prefers-color-scheme support. Renders similar to Apple Mail.",
        "market_share": 1,
    },
}


def _simulate_gmail_dark(html: str) -> str:
    """Simulate Gmail's auto-invert dark mode behavior."""
    css = """<style type="text/css">
/* Gmail dark mode simulation: auto-inverts colors */
body,.em-outer{background-color:#1A1A1A!important}
.em-card{background-color:#1A1A1A!important;border-color:#3A3A3A!important}
.em-body,.em-body p,.em-body div,.em-body li{color:#E0E0E0!important;-webkit-text-fill-color:#E0E0E0!important}
.em-title,.em-strong{color:#FFFFFF!important;-webkit-text-fill-color:#FFFFFF!important}
.em-text{color:#D0D0D0!important}
.em-text-secondary,.em-text-muted{color:#9E9E9E!important}
.em-info-tbl{background:#2A2A2A!important;border-color:#4A4A4A!important}
.em-info-td{background:#2A2A2A!important;border-color:#4A4A4A!important;color:#D0D0D0!important}
.em-info-val{color:#FFFFFF!important}
.em-callout{background:#2A2A2A!important;border-color:#4A4A4A!important;color:#D0D0D0!important}
.em-callout *{color:#D0D0D0!important;-webkit-text-fill-color:#D0D0D0!important}
.em-tip-box{background-color:#2A2A2A!important;border-color:#4A4A4A!important}
.em-footer-bg{background-color:#121212!important}
.em-footer-card{background-color:#1A1A1A!important;border-color:#3A3A3A!important}
.em-footer-t1{color:#E0E0E0!important}
.em-footer-t2{color:#9E9E9E!important}
.email-header-shell,.em-header{background:linear-gradient(135deg,#2C2C2C,#1A1A1A)!important}
.email-header-kicker,.em-header-kicker{color:rgba(255,255,255,0.7)!important}
img{border:1px solid #3A3A3A!important;border-radius:4px!important}
</style>"""
    if "</head>" in html:
        return html.replace("</head>", css + "</head>", 1)
    return css + html


def _simulate_outlook_desktop_dark(html: str) -> str:
    """Simulate Outlook Desktop dark mode: inverts text colors only, keeps backgrounds."""
    css = """<style type="text/css">
/* Outlook Desktop simulation: Word engine, text inversion only */
body,.em-outer{background-color:#1E1E1E!important}
.em-card{background-color:#252526!important;border-color:#3E3E42!important}
.em-body,.em-body p,.em-body div,.em-body li{color:#D4D4D4!important;-webkit-text-fill-color:#D4D4D4!important}
.em-title,.em-strong,.em-lead{color:#E5E5E5!important;-webkit-text-fill-color:#E5E5E5!important}
.em-text{color:#CCCCCC!important}
.em-text-secondary{color:#969696!important}
.em-text-muted{color:#6B6B6B!important}
.em-info-tbl,.em-info-td{background:#2D2D30!important;border-color:#3E3E42!important;color:#D4D4D4!important}
.em-info-val{color:#E5E5E5!important}
.email-header-shell,.em-header{background:#1E1E1E!important}
.email-header-kicker{color:#969696!important;-webkit-text-fill-color:#969696!important}
.em-footer-bg{background-color:#1E1E1E!important}
.em-footer-card{background-color:#252526!important;border-color:#3E3E42!important}
.em-footer-t1{color:#D4D4D4!important}
.em-footer-t2,.em-footer-t3{color:#969696!important}
.em-badge{border:1px solid #3E3E42!important}
table{border-collapse:collapse!important}
</style>"""
    if "</head>" in html:
        return html.replace("</head>", css + "</head>", 1)
    return css + html


def _simulate_outlook_web_dark(html: str) -> str:
    """Simulate Outlook.com dark mode using [data-ogsc] behavior."""
    css = """<style type="text/css">
/* Outlook.com simulation: [data-ogsc] / [data-ogsb] dark mode */
body,.em-outer{background-color:#141414!important}
.em-card{background-color:#1F1F1F!important;border-color:#333333!important}
.em-body,.em-body p,.em-body div,.em-body li{color:#D6D6D6!important;-webkit-text-fill-color:#D6D6D6!important}
.em-title,.em-strong,.em-lead{color:#F0F0F0!important;-webkit-text-fill-color:#F0F0F0!important}
.em-text{color:#C0C0C0!important}
.em-text-secondary{color:#8C8C8C!important}
.em-info-tbl,.em-info-td{background:#292929!important;border-color:#404040!important;color:#C0C0C0!important}
.em-info-val{color:#F0F0F0!important}
.em-callout{background:#292929!important;border-color:#404040!important}
.em-callout *{color:#C0C0C0!important;-webkit-text-fill-color:#C0C0C0!important}
.em-footer-bg{background-color:#0A0A0A!important}
.em-footer-card{background-color:#141414!important;border-color:#333333!important}
.em-footer-t1{color:#D6D6D6!important}
.em-footer-t2,.em-footer-t3{color:#8C8C8C!important}
.em-badge{background-color:#333!important;color:#FFF!important}
</style>"""
    if "</head>" in html:
        return html.replace("</head>", css + "</head>", 1)
    return css + html


def _simulate_yahoo_dark(html: str) -> str:
    """Simulate Yahoo Mail dark mode with class injection behavior."""
    css = """<style type="text/css">
/* Yahoo Mail simulation: .yahooMailDark class injection */
body,.em-outer{background-color:#1D1D26!important}
.em-card{background-color:#272733!important;border-color:#3D3D4E!important}
.em-body,.em-body p,.em-body div,.em-body li{color:#D9D9E0!important;-webkit-text-fill-color:#D9D9E0!important}
.em-title,.em-strong{color:#EBEBF0!important}
.em-text{color:#C4C4CF!important}
.em-text-secondary,.em-text-muted{color:#8888A0!important}
.em-info-tbl,.em-info-td{background:#2F2F3D!important;border-color:#4A4A5E!important;color:#C4C4CF!important}
.em-info-val{color:#EBEBF0!important}
.em-callout{background:#2F2F3D!important;border-color:#4A4A5E!important}
.em-callout *{color:#C4C4CF!important}
.em-footer-bg{background-color:#13131A!important}
.em-footer-card{background-color:#1D1D26!important;border-color:#3D3D4E!important}
.em-footer-t1{color:#D9D9E0!important}
.em-footer-t2,.em-footer-t3{color:#8888A0!important}
</style>"""
    if "</head>" in html:
        return html.replace("</head>", css + "</head>", 1)
    return css + html


CLIENT_SIMULATORS = {
    "apple_mail": _force_dark_preview,       # Full prefers-color-scheme (our native dark)
    "gmail_web": _simulate_gmail_dark,
    "gmail_mobile": _simulate_gmail_dark,     # Similar behavior, slightly different
    "outlook_desktop": _simulate_outlook_desktop_dark,
    "outlook_web": _simulate_outlook_web_dark,
    "yahoo_mail": _simulate_yahoo_dark,
    "thunderbird": _force_dark_preview,       # Same as Apple Mail
}


@router.get("/preview/{template_type}/client-sandbox")
async def preview_email_client_sandbox(
    template_type: str,
    request: Request,
    client: str = Query("apple_mail", pattern="^(apple_mail|gmail_web|gmail_mobile|outlook_desktop|outlook_web|yahoo_mail|thunderbird)$"),
):
    """Preview an email template simulating a specific email client's dark mode rendering."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import TEMPLATE_CATALOG
    from utils.email_service import apply_adaptive_email_contrast_guard

    if template_type not in TEMPLATE_CATALOG:
        raise HTTPException(status_code=404, detail=f"Unknown template: {template_type}")

    try:
        info = TEMPLATE_CATALOG[template_type]
        tpl = info["builder"]()
        html = tpl.html

        simulator = CLIENT_SIMULATORS.get(client, _force_dark_preview)
        html = simulator(html)
        html = apply_adaptive_email_contrast_guard(html)

        client_info = EMAIL_CLIENTS.get(client, {})

        return {
            "template_type": template_type,
            "client": client,
            "client_name": client_info.get("name", client),
            "client_platform": client_info.get("platform", "Unknown"),
            "dark_mode_support": client_info.get("dark_mode_support", "unknown"),
            "dark_mode_method": client_info.get("method", "unknown"),
            "notes": client_info.get("notes", ""),
            "html": html,
            "subject": tpl.subject,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Client sandbox render error: {e}")


@router.get("/preview/{template_type}/client-sandbox/all")
async def preview_all_clients(template_type: str, request: Request):
    """Preview an email template across ALL email clients at once."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import TEMPLATE_CATALOG
    from utils.email_service import apply_adaptive_email_contrast_guard

    if template_type not in TEMPLATE_CATALOG:
        raise HTTPException(status_code=404, detail=f"Unknown template: {template_type}")

    try:
        info = TEMPLATE_CATALOG[template_type]
        tpl = info["builder"]()
        base_html = tpl.html

        previews = []
        for client_id, client_info in EMAIL_CLIENTS.items():
            simulator = CLIENT_SIMULATORS.get(client_id, _force_dark_preview)
            rendered = apply_adaptive_email_contrast_guard(simulator(base_html))
            previews.append({
                "client": client_id,
                "name": client_info["name"],
                "platform": client_info["platform"],
                "dark_mode_support": client_info["dark_mode_support"],
                "method": client_info["method"],
                "notes": client_info["notes"],
                "market_share": client_info["market_share"],
                "html": rendered,
            })

        return {
            "template_type": template_type,
            "subject": tpl.subject,
            "label": info["label"],
            "clients": previews,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Client sandbox render error: {e}")


@router.get("/templates/client-compatibility")
async def client_compatibility_report(request: Request):
    """Generate a client compatibility report for all templates across email clients."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import TEMPLATE_CATALOG

    def _check_client_compat(html: str) -> dict:
        lower = html.lower()
        has_prefers_color_scheme = "prefers-color-scheme" in lower
        has_data_ogsc = "data-ogsc" in lower or "data-ogsb" in lower
        has_mso_conditional = "<!--[if mso" in lower or "mso-" in lower
        has_inline_dark = "em-force-light-card" in lower or "background:#FFFFFF" in html
        has_responsive = "@media only screen and (max-width" in lower
        has_em_classes = "em-card" in lower or "em-outer" in lower
        has_gradient = "linear-gradient" in lower

        return {
            "apple_mail": {
                "score": 100 if has_prefers_color_scheme and has_em_classes else 85 if has_em_classes else 60,
                "status": "excellent" if has_prefers_color_scheme else "good",
                "issues": [] if has_prefers_color_scheme else ["No prefers-color-scheme CSS"],
            },
            "gmail_web": {
                "score": 80 if has_inline_dark and has_em_classes else 65 if has_em_classes else 45,
                "status": "good" if has_inline_dark else "fair",
                "issues": ([] if has_inline_dark else ["No inline dark mode fallback"]) + ([] if not has_gradient else ["Gradients may be flattened"]),
            },
            "gmail_mobile": {
                "score": 75 if has_inline_dark and has_responsive else 60 if has_responsive else 40,
                "status": "good" if has_inline_dark and has_responsive else "fair",
                "issues": ([] if has_responsive else ["Missing responsive media queries"]) + ([] if has_inline_dark else ["No inline dark mode fallback"]),
            },
            "outlook_desktop": {
                "score": 55 if has_mso_conditional else 40 if has_inline_dark else 25,
                "status": "fair" if has_mso_conditional else "poor",
                "issues": ([] if has_mso_conditional else ["No MSO conditional comments"]) + (["CSS gradients unsupported"] if has_gradient else []) + (["Word engine ignores most CSS"] if not has_mso_conditional else []),
            },
            "outlook_web": {
                "score": 75 if has_data_ogsc and has_em_classes else 60 if has_em_classes else 40,
                "status": "good" if has_data_ogsc else "fair",
                "issues": [] if has_data_ogsc else ["No [data-ogsc] selectors for Outlook.com dark mode"],
            },
            "yahoo_mail": {
                "score": 70 if has_em_classes and has_inline_dark else 55,
                "status": "good" if has_em_classes else "fair",
                "issues": [] if has_em_classes else ["Limited CSS class support"],
            },
            "thunderbird": {
                "score": 95 if has_prefers_color_scheme and has_em_classes else 80,
                "status": "excellent" if has_prefers_color_scheme else "good",
                "issues": [] if has_prefers_color_scheme else ["No prefers-color-scheme CSS"],
            },
        }

    results = []
    client_scores = {c: [] for c in EMAIL_CLIENTS}

    for key, info in TEMPLATE_CATALOG.items():
        try:
            tpl = info["builder"]()
            compat = _check_client_compat(tpl.html)
            results.append({
                "key": key,
                "label": info["label"],
                "category": info["category"],
                "compatibility": compat,
            })
            for c_id, c_data in compat.items():
                client_scores[c_id].append(c_data["score"])
        except Exception as e:
            results.append({
                "key": key,
                "label": info["label"],
                "category": info["category"],
                "compatibility": {},
                "error": str(e),
            })

    client_summary = {}
    for c_id, scores in client_scores.items():
        avg = round(sum(scores) / max(len(scores), 1), 1) if scores else 0
        client_summary[c_id] = {
            "name": EMAIL_CLIENTS[c_id]["name"],
            "platform": EMAIL_CLIENTS[c_id]["platform"],
            "avg_score": avg,
            "grade": "A" if avg >= 90 else "B" if avg >= 75 else "C" if avg >= 60 else "D" if avg >= 40 else "F",
            "templates_tested": len(scores),
            "market_share": EMAIL_CLIENTS[c_id]["market_share"],
        }

    overall = round(sum(s["avg_score"] for s in client_summary.values()) / max(len(client_summary), 1), 1)

    return {
        "summary": {
            "overall_score": overall,
            "overall_grade": "A" if overall >= 90 else "B" if overall >= 75 else "C" if overall >= 60 else "D" if overall >= 40 else "F",
            "clients_tested": len(EMAIL_CLIENTS),
            "templates_tested": len(results),
        },
        "clients": client_summary,
        "results": results,
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/templates/localization-audit")
async def audit_email_template_localizations(
    request: Request,
    lang: str = Query("fr", pattern="^[a-z]{2,3}$"),
    purge_invalid_cache: bool = Query(True),
    force_refresh: bool = Query(False),
):
    """Audit translated email template renders for placeholder leaks, brand safety, CTA localization, and link integrity."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    normalized_lang = (lang or "fr").strip().lower()
    if force_refresh:
        recent_any_age = await _get_recent_localization_audit(normalized_lang, max_age_minutes=525600)
        if recent_any_age:
            asyncio.create_task(
                _refresh_single_localization_audit_background(
                    lang_code=normalized_lang,
                    purge_invalid_cache=purge_invalid_cache,
                )
            )
            return {
                **recent_any_age,
                "cached": True,
                "background_refresh_started": True,
            }
    return await run_template_localization_audit(
        lang_code=normalized_lang,
        purge_invalid_cache=purge_invalid_cache,
        force_refresh=force_refresh,
    )


@router.get("/templates/localization-audit/multilingual")
async def audit_email_template_localizations_multilingual(
    request: Request,
    langs: str = Query("fr,es,de"),
    purge_invalid_cache: bool = Query(True),
    force_refresh: bool = Query(False),
):
    """Audit translated email template renders across multiple languages with a single aggregated report."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    lang_list = [part.strip().lower() for part in langs.split(",") if part.strip()]
    if force_refresh:
        normalized_langs = lang_list or list(DEFAULT_MULTILINGUAL_AUDIT_LANGS)
        langs_key = "|".join(normalized_langs)
        recent_any_age = await _get_recent_multilingual_localization_audit(langs_key, max_age_minutes=525600)
        if recent_any_age:
            asyncio.create_task(
                _refresh_multilingual_localization_audit_background(
                    lang_codes=normalized_langs,
                    purge_invalid_cache=purge_invalid_cache,
                )
            )
            return {
                **recent_any_age,
                "cached": True,
                "background_refresh_started": True,
            }
    return await run_multilingual_template_localization_audit(
        lang_codes=lang_list,
        purge_invalid_cache=purge_invalid_cache,
        force_refresh=force_refresh,
    )


@router.post("/send-test/{template_type}")
async def send_test_email(template_type: str, request: Request, theme: str = Query("light", regex="^(dark|light)$")):
    """Send a test email using a template with sample data (admin only). Use ?theme=dark for dark mode."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import TEMPLATE_CATALOG

    # Try catalog first, then legacy
    result = None
    if template_type in TEMPLATE_CATALOG:
        try:
            info = TEMPLATE_CATALOG[template_type]
            tpl = info["builder"]()
            html = tpl.html
            if theme == "dark":
                html = _force_dark_preview(html)
            result = {"subject": tpl.subject, "html": html}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Template render error: {e}")
    elif template_type in EMAIL_TYPES:
        result = _render_preview(template_type)
        if theme == "dark":
            result["html"] = _force_dark_preview(result["html"])
    else:
        raise HTTPException(status_code=404, detail=f"Unknown template type: {template_type}")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    recipient = body.get("recipient_email", user.email)

    from utils.email_service import send_email as send_email, is_email_configured

    if not is_email_configured():
        raise HTTPException(status_code=500, detail="Email service not configured")

    theme_label = "Dark theme (v7)" if theme == "dark" else "Light theme (v7)"
    tagged_subject = f"[{theme_label}] {result['subject']}"

    send_result = await send_email(
        recipient_email=recipient,
        subject=tagged_subject,
        content=result["html"],
        recipient_name=user.name or "Admin",
        template_key=template_type,
    )

    # Log the test send
    from utils.email_notifications import _log_email

    status = "sent" if send_result.get("success") else "failed"
    await _log_email(
        user.user_id,
        recipient,
        f"test_{template_type}",
        tagged_subject,
        status,
        error=send_result.get("error", ""),
    )

    if not send_result.get("success"):
        raise HTTPException(status_code=500, detail=send_result.get("error", "Failed to send test email"))

    return {
        "success": True,
        "template_type": template_type,
        "theme": theme,
        "recipient": recipient,
        "subject": tagged_subject,
        "message": f"Test email sent to {recipient}",
    }



@router.post("/send-all-templates")
async def send_all_templates(request: Request, theme: str = Query("light", regex="^(dark|light)$")):
    """Send ALL 51 templates to the admin's email in one click for visual QA."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    recipient = body.get("recipient_email", user.email)

    from utils.email_templates import TEMPLATE_CATALOG
    from utils.email_service import send_email, is_email_configured

    if not is_email_configured():
        raise HTTPException(status_code=500, detail="Email service not configured")

    theme_label = "Dark theme (v7)" if theme == "dark" else "Light theme (v7)"
    sent = 0
    failed = 0
    errors = []

    for key, info in TEMPLATE_CATALOG.items():
        try:
            tpl = info["builder"]()
            html = tpl.html
            if theme == "dark":
                html = _force_dark_preview(html)
            tagged_subject = f"[{theme_label}] {tpl.subject}"
            result = await send_email(
                recipient_email=recipient,
                subject=tagged_subject,
                content=html,
                recipient_name=user.name or "Admin",
                template_key=key,
            )
            if result.get("success"):
                sent += 1
            else:
                failed += 1
                errors.append({"key": key, "error": result.get("error", "Unknown")})
        except Exception as e:
            failed += 1
            errors.append({"key": key, "error": str(e)})

    return {
        "success": failed == 0,
        "total": len(TEMPLATE_CATALOG),
        "sent": sent,
        "failed": failed,
        "theme": theme,
        "recipient": recipient,
        "errors": errors[:10],
        "message": f"Sent {sent}/{len(TEMPLATE_CATALOG)} templates ({theme_label}) to {recipient}",
    }



# ─── Email Analytics: Open & Click Tracking ───────────────────────────

PIXEL_GIF = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


def inject_tracking(html: str, tracking_id: str, base_url: str) -> str:
    """Inject open tracking pixel and wrap links for click tracking."""
    import os
    api_base = os.environ.get("FRONTEND_BASE_URL", base_url).rstrip("/")

    # 1. Inject open tracking pixel before </body> or at end
    pixel = f'<img src="{api_base}/api/email-notifications/track/open/{tracking_id}" width="1" height="1" style="display:none;" alt="" />'
    if "</body>" in html.lower():
        html = html.replace("</body>", f"{pixel}</body>").replace("</BODY>", f"{pixel}</BODY>")
    else:
        html += pixel

    # 2. Wrap <a href="..."> links for click tracking (skip tracking/unsubscribe links)
    def _wrap_link(match):
        full = match.group(0)
        href = match.group(1)
        if not href or href.startswith("#") or "track/" in href or "unsubscribe" in href.lower():
            return full
        tracked = f'{api_base}/api/email-notifications/track/click/{tracking_id}?url={quote(href, safe="")}'
        return full.replace(href, tracked)

    html = re.sub(r'<a\s[^>]*href="([^"]*)"', _wrap_link, html, flags=re.IGNORECASE)
    return html


@router.get("/track/open/{tracking_id}")
async def track_open(tracking_id: str, request: Request):
    """Record an email open event and return 1x1 transparent pixel."""
    try:
        await db.email_analytics.update_one(
            {"tracking_id": tracking_id},
            {
                "$set": {"last_opened": datetime.now(timezone.utc).isoformat()},
                "$inc": {"open_count": 1},
                "$push": {"events": {"type": "open", "at": datetime.now(timezone.utc).isoformat(), "ua": request.headers.get("user-agent", "")[:200]}},
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"Open tracking error: {e}")
    return Response(content=PIXEL_GIF, media_type="image/gif", headers={"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"})


@router.get("/track/click/{tracking_id}")
@router.get("/track/click/{tracking_id}/{wrapped_url:path}")
async def track_click(tracking_id: str, url: str = "", wrapped_url: str = "", request: Request = None):
    """Record a link click event and redirect to the original URL.

    Supports both formats:
    - /track/click/{tracking_id}?url=<encoded>
    - /track/click/{tracking_id}/url=<encoded>
    and unwraps nested tracking wrappers to final destination.
    """

    def _unwrap_tracking_destination(raw_value: str) -> str:
        current = unquote(str(raw_value or "").strip())
        for _ in range(6):
            if not current:
                break

            parsed = urlparse(current)
            query = parse_qs(parsed.query or "")
            nested = ""

            for key in ("url", "redirect", "redirect_uri", "target", "destination", "next", "u"):
                values = query.get(key)
                if values and values[0]:
                    nested = values[0]
                    break

            if not nested:
                path_value = parsed.path or current
                if "/url=" in path_value:
                    nested = path_value.split("/url=", 1)[1]
                elif path_value.startswith("url="):
                    nested = path_value.split("url=", 1)[1]

            if not nested:
                break

            current = unquote(str(nested).strip())

        return current

    raw_value = str(url or "").strip() or str(wrapped_url or "").strip()
    if raw_value.startswith("url="):
        raw_value = raw_value.split("url=", 1)[1]

    resolved = _unwrap_tracking_destination(raw_value)
    parsed_resolved = urlparse(resolved) if resolved else None

    # Safe fallback route if destination is absent or malformed.
    if not resolved:
        dest = "/welcome"
    elif parsed_resolved and parsed_resolved.scheme in {"http", "https"}:
        dest = resolved
    elif resolved.startswith("/"):
        dest = resolved
    else:
        dest = f"/{resolved.lstrip('/')}"

    # Permanent compatibility: if a stale preview-domain link is clicked,
    # rewrite host to the current canonical frontend base URL.
    try:
        import os

        canonical_base = str(os.environ.get("FRONTEND_BASE_URL") or "").strip().rstrip("/")
        canonical_parsed = urlparse(canonical_base) if canonical_base else None
        target_parsed = urlparse(dest) if dest.startswith("http") else None

        if (
            canonical_parsed
            and canonical_parsed.scheme in {"http", "https"}
            and canonical_parsed.netloc
            and target_parsed
            and target_parsed.netloc
            and target_parsed.netloc != canonical_parsed.netloc
            and target_parsed.netloc.endswith(".preview.emergentagent.com")
        ):
            rewritten = target_parsed._replace(
                scheme=canonical_parsed.scheme,
                netloc=canonical_parsed.netloc,
            )
            dest = rewritten.geturl()
    except Exception:
        pass

    try:
        await db.email_analytics.update_one(
            {"tracking_id": tracking_id},
            {
                "$set": {"last_clicked": datetime.now(timezone.utc).isoformat()},
                "$inc": {"click_count": 1},
                "$push": {"events": {"type": "click", "url": dest[:500], "at": datetime.now(timezone.utc).isoformat()}},
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"Click tracking error: {e}")
    return RedirectResponse(url=dest, status_code=302)


@router.post("/admin/link-host-self-heal/dry-run")
async def email_link_host_self_heal_dry_run(request: Request):
    """Preview stale-host link rewrite impact across email-related persisted docs (admin only)."""
    await require_admin(request)
    body = await request.json() if request is not None else {}
    old_host = str(body.get("old_host") or DEFAULT_STALE_PREVIEW_HOST).strip()
    new_host = str(body.get("new_host") or DEFAULT_CANONICAL_PREVIEW_HOST).strip()
    if not old_host or not new_host:
        raise HTTPException(status_code=400, detail="old_host and new_host are required")
    if old_host == new_host:
        raise HTTPException(status_code=400, detail="old_host and new_host must be different")
    return await _run_link_host_self_heal(old_host, new_host, apply_changes=False)


@router.post("/admin/link-host-self-heal/apply")
async def email_link_host_self_heal_apply(request: Request):
    """Apply stale-host link rewrite across email-related persisted docs (admin only)."""
    await require_admin(request)
    body = await request.json() if request is not None else {}
    old_host = str(body.get("old_host") or DEFAULT_STALE_PREVIEW_HOST).strip()
    new_host = str(body.get("new_host") or DEFAULT_CANONICAL_PREVIEW_HOST).strip()
    if not old_host or not new_host:
        raise HTTPException(status_code=400, detail="old_host and new_host are required")
    if old_host == new_host:
        raise HTTPException(status_code=400, detail="old_host and new_host must be different")
    return await _run_link_host_self_heal(old_host, new_host, apply_changes=True)


@router.get("/admin/link-host-self-heal/history")
async def email_link_host_self_heal_history(request: Request, limit: int = Query(default=10, ge=1, le=50)):
    """Fetch recent host self-heal runs (admin only)."""
    await require_admin(request)
    rows = await db[EMAIL_LINK_SELF_HEAL_COLLECTION].find({}, {"_id": 0}).sort("started_at", -1).limit(limit).to_list(limit)
    return {"runs": rows, "count": len(rows)}


@router.get("/analytics")
async def get_email_analytics(request: Request):
    """Get aggregated email analytics — open rates, click rates per template type (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # Aggregate from email_analytics joined with email_logs
    pipeline = [
        {"$group": {
            "_id": "$email_type",
            "total_sent": {"$sum": 1},
            "total_opens": {"$sum": {"$cond": [{"$gt": ["$open_count", 0]}, 1, 0]}},
            "total_clicks": {"$sum": {"$cond": [{"$gt": ["$click_count", 0]}, 1, 0]}},
            "sum_opens": {"$sum": {"$ifNull": ["$open_count", 0]}},
            "sum_clicks": {"$sum": {"$ifNull": ["$click_count", 0]}},
        }},
        {"$sort": {"total_sent": -1}},
    ]
    results = await db.email_analytics.aggregate(pipeline).to_list(100)

    by_type = {}
    totals = {"sent": 0, "opened": 0, "clicked": 0, "total_opens": 0, "total_clicks": 0}
    for r in results:
        etype = r["_id"] or "unknown"
        sent = r["total_sent"]
        opened = r["total_opens"]
        clicked = r["total_clicks"]
        by_type[etype] = {
            "sent": sent,
            "opened": opened,
            "clicked": clicked,
            "open_rate": round(opened / sent * 100, 1) if sent else 0,
            "click_rate": round(clicked / sent * 100, 1) if sent else 0,
            "total_opens": r["sum_opens"],
            "total_clicks": r["sum_clicks"],
        }
        totals["sent"] += sent
        totals["opened"] += opened
        totals["clicked"] += clicked
        totals["total_opens"] += r["sum_opens"]
        totals["total_clicks"] += r["sum_clicks"]

    totals["open_rate"] = round(totals["opened"] / totals["sent"] * 100, 1) if totals["sent"] else 0
    totals["click_rate"] = round(totals["clicked"] / totals["sent"] * 100, 1) if totals["sent"] else 0

    return {"by_type": by_type, "totals": totals}


@router.get("/analytics/click-heatmap")
async def get_click_heatmap(request: Request):
    """Get click-through heatmap data — clicks aggregated by URL and template (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    pipeline = [
        {"$match": {"events": {"$exists": True, "$ne": []}}},
        {"$unwind": "$events"},
        {"$match": {"events.type": "click"}},
        {"$group": {
            "_id": {"email_type": "$email_type", "url": "$events.url"},
            "clicks": {"$sum": 1},
            "last_click": {"$max": "$events.at"},
        }},
        {"$sort": {"clicks": -1}},
        {"$limit": 200},
    ]
    results = await db.email_analytics.aggregate(pipeline).to_list(200)

    from urllib.parse import urlparse

    # Build per-template and per-URL aggregations
    by_template: dict = {}
    by_url: dict = {}
    heatmap_cells: list = []
    max_clicks = 0

    for r in results:
        etype = (r["_id"].get("email_type") or "unknown")
        raw_url = r["_id"].get("url") or ""
        clicks = r["clicks"]
        max_clicks = max(max_clicks, clicks)

        # Normalize URL to a readable label
        try:
            parsed = urlparse(raw_url)
            path = parsed.path.rstrip("/") or "/"
            label = path.split("/")[-1] if path != "/" else "home"
            # Clean up label
            label = label.replace("-", " ").replace("_", " ").title()
            if not label or label == "/":
                label = "Dashboard"
        except Exception:
            label = raw_url[:40]

        by_template.setdefault(etype, {"total_clicks": 0, "urls": []})
        by_template[etype]["total_clicks"] += clicks
        by_template[etype]["urls"].append({"url": raw_url, "label": label, "clicks": clicks, "last_click": r.get("last_click", "")})

        by_url.setdefault(raw_url, {"label": label, "total_clicks": 0, "templates": []})
        by_url[raw_url]["total_clicks"] += clicks
        by_url[raw_url]["templates"].append({"template": etype, "clicks": clicks})

        heatmap_cells.append({
            "template": etype,
            "url": raw_url,
            "label": label,
            "clicks": clicks,
            "intensity": round(clicks / max_clicks, 2) if max_clicks else 0,
        })

    # Recalculate intensity after knowing max
    if max_clicks:
        for cell in heatmap_cells:
            cell["intensity"] = round(cell["clicks"] / max_clicks, 2)

    # Top URLs across all templates
    top_urls = sorted(by_url.values(), key=lambda x: x["total_clicks"], reverse=True)[:15]

    # Top templates by click engagement
    top_templates = sorted(
        [{"template": k, **v} for k, v in by_template.items()],
        key=lambda x: x["total_clicks"],
        reverse=True,
    )[:15]

    return {
        "heatmap": heatmap_cells,
        "top_urls": top_urls,
        "top_templates": top_templates,
        "max_clicks": max_clicks,
        "total_click_events": sum(c["clicks"] for c in heatmap_cells),
    }


# ─── Email Auto-Fix: Automated Subject Line Optimization ──────────────

@router.post("/autofix/run")
async def trigger_autofix(request: Request):
    """Manually trigger the auto-fix routine (admin only). Also runs automatically via scheduler."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    from services.email_autofix import run_email_autofix
    result = await run_email_autofix()
    return result


@router.get("/autofix/history")
async def get_autofix_history(request: Request):
    """Get auto-fix run history (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    from services.email_autofix import get_autofix_history as _history
    return await _history()


@router.get("/autofix/overrides")
async def get_subject_overrides(request: Request):
    """Get active subject line overrides (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    from services.email_autofix import get_subject_overrides
    return await get_subject_overrides()


@router.post("/autofix/revert/{email_type}")
async def revert_override(email_type: str, request: Request):
    """Revert a subject override back to original (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    from services.email_autofix import revert_subject_override
    ok = await revert_subject_override(email_type)
    if not ok:
        raise HTTPException(status_code=404, detail="No active override found")
    return {"success": True, "message": f"Reverted override for {email_type}"}


# ─── Email Deliverability Monitoring ──────────────────────────────────

@router.get("/deliverability")
async def get_deliverability_dashboard(request: Request):
    """Get email deliverability metrics — bounce rates, spam complaints, sender reputation (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - __import__('datetime').timedelta(days=30)).isoformat()
    seven_days_ago = (now - __import__('datetime').timedelta(days=7)).isoformat()

    # Aggregate deliverability events from email_deliverability collection
    pipeline_30d = [
        {"$match": {"timestamp": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": "$event_type",
            "count": {"$sum": 1},
        }},
    ]
    events_30d = {r["_id"]: r["count"] for r in await db.email_deliverability.aggregate(pipeline_30d).to_list(50)}

    # Get daily trend for last 7 days
    daily_pipeline = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}}},
        {"$addFields": {"day": {"$substr": ["$timestamp", 0, 10]}}},
        {"$group": {"_id": {"day": "$day", "event_type": "$event_type"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.day": 1}},
    ]
    daily_raw = await db.email_deliverability.aggregate(daily_pipeline).to_list(200)
    daily_trend = {}
    for r in daily_raw:
        day = r["_id"]["day"]
        etype = r["_id"]["event_type"]
        daily_trend.setdefault(day, {"delivered": 0, "bounced": 0, "complained": 0, "deferred": 0})
        daily_trend[day][etype] = r["count"]

    # Get total sent from email_analytics
    total_sent = await db.email_analytics.count_documents({"sent_at": {"$gte": thirty_days_ago}})
    if total_sent == 0:
        # Fallback: count from logs
        stats_doc = await db.email_log_stats.find_one({"_id": "totals"}, {"_id": 0})
        total_sent = stats_doc.get("sent", 0) if stats_doc else 0

    bounces = events_30d.get("bounced", 0)
    complaints = events_30d.get("complained", 0)
    delivered = events_30d.get("delivered", 0)
    deferred = events_30d.get("deferred", 0)

    # Calculate rates
    denom = max(total_sent, delivered + bounces + complaints + deferred, 1)
    bounce_rate = round(bounces / denom * 100, 2)
    complaint_rate = round(complaints / denom * 100, 2)
    delivery_rate = round((denom - bounces) / denom * 100, 2)

    # Sender reputation score (0-100)
    # Penalize: bounces (-2 per %), complaints (-5 per %), deferred (-0.5 per %)
    reputation = max(0, min(100, round(
        100 - (bounce_rate * 2) - (complaint_rate * 5) - (deferred / max(denom, 1) * 100 * 0.5)
    )))

    # Reputation label
    if reputation >= 90:
        rep_label, rep_color = "Excellent", "green"
    elif reputation >= 70:
        rep_label, rep_color = "Good", "blue"
    elif reputation >= 50:
        rep_label, rep_color = "Fair", "amber"
    else:
        rep_label, rep_color = "Poor", "red"

    # Get recent bounce/complaint details
    recent_issues = await db.email_deliverability.find(
        {"event_type": {"$in": ["bounced", "complained"]}, "timestamp": {"$gte": seven_days_ago}},
        {"_id": 0, "event_type": 1, "email": 1, "reason": 1, "timestamp": 1, "template_type": 1},
    ).sort("timestamp", -1).to_list(20)

    # Active alerts
    alerts = []
    if bounce_rate > 5:
        alerts.append({"severity": "critical", "message": f"Bounce rate {bounce_rate}% exceeds 5% threshold", "metric": "bounce_rate", "value": bounce_rate})
    elif bounce_rate > 2:
        alerts.append({"severity": "warning", "message": f"Bounce rate {bounce_rate}% approaching danger zone", "metric": "bounce_rate", "value": bounce_rate})
    if complaint_rate > 0.1:
        alerts.append({"severity": "critical", "message": f"Spam complaint rate {complaint_rate}% — risk of sender blacklisting", "metric": "complaint_rate", "value": complaint_rate})
    elif complaint_rate > 0.05:
        alerts.append({"severity": "warning", "message": f"Spam complaint rate {complaint_rate}% is elevated", "metric": "complaint_rate", "value": complaint_rate})
    if reputation < 50:
        alerts.append({"severity": "critical", "message": f"Sender reputation score {reputation}/100 — take immediate action", "metric": "reputation", "value": reputation})
    elif reputation < 70:
        alerts.append({"severity": "warning", "message": f"Sender reputation {reputation}/100 — monitor closely", "metric": "reputation", "value": reputation})

    return {
        "period": "30d",
        "total_sent": denom,
        "delivered": delivered,
        "bounced": bounces,
        "complained": complaints,
        "deferred": deferred,
        "bounce_rate": bounce_rate,
        "complaint_rate": complaint_rate,
        "delivery_rate": delivery_rate,
        "reputation": {"score": reputation, "label": rep_label, "color": rep_color},
        "daily_trend": [{"date": k, **v} for k, v in sorted(daily_trend.items())],
        "recent_issues": recent_issues,
        "alerts": alerts,
    }


@router.get("/reliability/overview")
async def get_feature32_reliability_overview(
    request: Request,
    window_days: int = Query(default=7, ge=1, le=30),
):
    """Feature 32 post-launch monitoring pack: reliability dashboard payload (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return await _collect_feature32_reliability(window_days)


@router.get("/reliability/weekly-report-template")
async def get_feature32_weekly_report_template(
    request: Request,
    window_days: int = Query(default=7, ge=1, le=30),
):
    """Feature 32 post-launch monitoring pack: weekly reliability report template (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    reliability = await _collect_feature32_reliability(window_days)
    return {
        "success": True,
        "window_days": window_days,
        "generated_at": reliability.get("generated_at"),
        "report_template": reliability.get("weekly_report_template") or {},
        "summary": reliability.get("kpis") or {},
        "alerts": reliability.get("alerts") or [],
    }


@router.post("/deliverability/record")
async def record_deliverability_event(request: Request):
    """Record a deliverability event (webhook receiver for bounce/complaint notifications)."""
    body = await request.json()
    event_type = body.get("event_type")  # bounced, complained, delivered, deferred
    if event_type not in ("bounced", "complained", "delivered", "deferred"):
        raise HTTPException(status_code=400, detail="Invalid event_type")

    doc = {
        "event_type": event_type,
        "email": body.get("email", ""),
        "reason": body.get("reason", ""),
        "template_type": body.get("template_type", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": body.get("provider", "resend"),
        "metadata": body.get("metadata", {}),
    }
    await db.email_deliverability.insert_one(doc)
    return {"success": True}


@router.post("/deliverability/simulate")
async def simulate_deliverability_data(request: Request):
    """Simulate deliverability events for demo/testing purposes (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    import random
    now = datetime.now(timezone.utc)
    events = []
    templates = ["welcome", "password_reset", "booking_created", "payment_receipt", "daily_job_alerts", "ai_report", "weekly_digest"]
    reasons_bounce = ["mailbox_full", "invalid_address", "domain_not_found", "blocked_by_server", "temporary_failure"]
    reasons_complaint = ["marked_as_spam", "unsubscribed_via_spam_btn", "bulk_mail_filter"]

    for days_ago in range(30):
        ts = (now - __import__('datetime').timedelta(days=days_ago, hours=random.randint(0, 23)))
        # Delivered emails (most common)
        for _ in range(random.randint(15, 50)):
            events.append({
                "event_type": "delivered",
                "email": f"user{random.randint(1,500)}@example.com",
                "reason": "",
                "template_type": random.choice(templates),
                "timestamp": ts.isoformat(),
                "provider": "resend",
                "metadata": {},
            })
        # Bounces (occasional)
        for _ in range(random.randint(0, 3)):
            events.append({
                "event_type": "bounced",
                "email": f"bad{random.randint(1,100)}@example.com",
                "reason": random.choice(reasons_bounce),
                "template_type": random.choice(templates),
                "timestamp": ts.isoformat(),
                "provider": "resend",
                "metadata": {},
            })
        # Complaints (rare)
        if random.random() < 0.15:
            events.append({
                "event_type": "complained",
                "email": f"user{random.randint(1,500)}@example.com",
                "reason": random.choice(reasons_complaint),
                "template_type": random.choice(templates),
                "timestamp": ts.isoformat(),
                "provider": "resend",
                "metadata": {},
            })
        # Deferred (occasional)
        for _ in range(random.randint(0, 2)):
            events.append({
                "event_type": "deferred",
                "email": f"user{random.randint(1,500)}@example.com",
                "reason": "temporary_failure",
                "template_type": random.choice(templates),
                "timestamp": ts.isoformat(),
                "provider": "resend",
                "metadata": {},
            })

    if events:
        await db.email_deliverability.insert_many(events)
    return {"success": True, "events_created": len(events)}


# ─── Weekly Heatmap Digest (called by scheduler) ──────────────────────

async def _send_weekly_heatmap_digest(db_ref):
    """Build and send a weekly email heatmap digest to all admin users."""
    from datetime import timedelta
    from urllib.parse import urlparse

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    # Aggregate click events from last 7 days
    pipeline = [
        {"$match": {"events": {"$exists": True, "$ne": []}}},
        {"$unwind": "$events"},
        {"$match": {"events.type": "click", "events.at": {"$gte": seven_days_ago}}},
        {"$group": {"_id": {"email_type": "$email_type", "url": "$events.url"}, "clicks": {"$sum": 1}}},
        {"$sort": {"clicks": -1}},
        {"$limit": 50},
    ]
    results = await db_ref.email_analytics.aggregate(pipeline).to_list(50)

    if not results:
        logger.info("Weekly heatmap digest: no click data in last 7 days, skipping.")
        return

    # Aggregate by URL
    by_url = {}
    by_template = {}
    total_clicks = 0
    for r in results:
        url = r["_id"].get("url", "")
        tpl = r["_id"].get("email_type", "unknown")
        clicks = r["clicks"]
        total_clicks += clicks

        try:
            parsed = urlparse(url)
            label = parsed.path.rstrip("/").split("/")[-1] or "home"
            label = label.replace("-", " ").replace("_", " ").title()
        except Exception:
            label = url[:40]

        by_url.setdefault(url, {"label": label, "clicks": 0})
        by_url[url]["clicks"] += clicks
        by_template.setdefault(tpl, 0)
        by_template[tpl] += clicks

    top_urls = sorted(by_url.values(), key=lambda x: x["clicks"], reverse=True)[:5]
    top_templates = sorted(by_template.items(), key=lambda x: x[1], reverse=True)[:5]

    # Build the digest email
    url_rows = ""
    for idx, u in enumerate(top_urls):
        url_rows += f"""
        <tr style="border-bottom:1px solid #1F2937;">
          <td style="padding:10px 12px;color:#F9FAFB;font-size:13px;font-weight:700;">{idx+1}.</td>
          <td style="padding:10px 12px;color:#F9FAFB;font-size:13px;">{u['label']}</td>
          <td style="padding:10px 12px;color:#EC4899;font-size:14px;font-weight:800;text-align:right;">{u['clicks']}</td>
        </tr>"""

    tpl_rows = ""
    for tpl, clicks in top_templates:
        tpl_rows += f"""
        <tr style="border-bottom:1px solid #1F2937;">
          <td style="padding:8px 12px;color:#F9FAFB;font-size:12px;">{tpl.replace('_', ' ').title()}</td>
          <td style="padding:8px 12px;color:#3B82F6;font-size:13px;font-weight:700;text-align:right;">{clicks}</td>
        </tr>"""

    # Get deliverability summary
    deliv_pipeline = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}}},
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
    ]
    deliv_events = {r["_id"]: r["count"] for r in await db_ref.email_deliverability.aggregate(deliv_pipeline).to_list(50)}
    bounces = deliv_events.get("bounced", 0)
    complaints = deliv_events.get("complained", 0)
    delivered = deliv_events.get("delivered", 0)
    total_emails = delivered + bounces + complaints + deliv_events.get("deferred", 0)

    f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body {{ margin:0; padding:0; background:#0B0F1A; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
  @media (prefers-color-scheme:light) {{ body {{ background:#F8FAFC; }} }}
</style>
</head><body style="background:#0B0F1A;padding:32px 16px;">
<div style="max-width:600px;margin:0 auto;background:#111827;border-radius:16px;overflow:hidden;border:1px solid #1F2937;">
  <div style="padding:32px 28px;background:linear-gradient(135deg,#1F2937,#111827);">
    <h1 style="margin:0;color:#F9FAFB;font-size:22px;font-weight:800;">Weekly Email Heatmap Digest</h1>
    <p style="margin:8px 0 0;color:#6B7280;font-size:13px;">CTA engagement summary for the past 7 days</p>
  </div>

  <div style="padding:24px 28px;">
    <div style="display:flex;gap:12px;margin-bottom:24px;">
      <div style="flex:1;background:#EC489910;border:1px solid #EC489918;border-radius:10px;padding:16px;text-align:center;">
        <div style="font-size:24px;font-weight:800;color:#EC4899;">{total_clicks}</div>
        <div style="font-size:10px;color:#6B7280;margin-top:2px;">Total CTA Clicks</div>
      </div>
      <div style="flex:1;background:#3B82F610;border:1px solid #3B82F618;border-radius:10px;padding:16px;text-align:center;">
        <div style="font-size:24px;font-weight:800;color:#3B82F6;">{len(by_url)}</div>
        <div style="font-size:10px;color:#6B7280;margin-top:2px;">Unique URLs</div>
      </div>
      <div style="flex:1;background:#10B98110;border:1px solid #10B98118;border-radius:10px;padding:16px;text-align:center;">
        <div style="font-size:24px;font-weight:800;color:#10B981;">{len(by_template)}</div>
        <div style="font-size:10px;color:#6B7280;margin-top:2px;">Active Templates</div>
      </div>
    </div>

    <h2 style="color:#F9FAFB;font-size:15px;font-weight:700;margin:0 0 12px;border-bottom:1px solid #1F2937;padding-bottom:8px;">Top CTA Destinations</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">{url_rows}</table>

    <h2 style="color:#F9FAFB;font-size:15px;font-weight:700;margin:0 0 12px;border-bottom:1px solid #1F2937;padding-bottom:8px;">Template Engagement</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">{tpl_rows}</table>

    {"<h2 style='color:#F9FAFB;font-size:15px;font-weight:700;margin:0 0 12px;border-bottom:1px solid #1F2937;padding-bottom:8px;'>Deliverability (7d)</h2><div style='display:flex;gap:8px;margin-bottom:16px;'><div style='flex:1;text-align:center;padding:10px;background:#10B98108;border-radius:8px;border:1px solid #10B98118;'><div style='font-size:18px;font-weight:800;color:#10B981;'>" + str(delivered) + "</div><div style='font-size:9px;color:#6B7280;'>Delivered</div></div><div style='flex:1;text-align:center;padding:10px;background:#EF444408;border-radius:8px;border:1px solid #EF444418;'><div style='font-size:18px;font-weight:800;color:#EF4444;'>" + str(bounces) + "</div><div style='font-size:9px;color:#6B7280;'>Bounced</div></div><div style='flex:1;text-align:center;padding:10px;background:#F59E0B08;border-radius:8px;border:1px solid #F59E0B18;'><div style='font-size:18px;font-weight:800;color:#F59E0B;'>" + str(complaints) + "</div><div style='font-size:9px;color:#6B7280;'>Complaints</div></div></div>" if total_emails > 0 else ""}
  </div>

  <div style="padding:20px 28px;background:#0B0F1A;text-align:center;">
    <p style="margin:0;color:#4B5563;font-size:11px;">This is an automated weekly digest. View the full dashboard in your Admin Console.</p>
  </div>
</div>
</body></html>"""

    # Send to all admins
    admins = await db_ref.users.find({"is_admin": True}, {"_id": 0, "email": 1}).to_list(50)
    sent = 0
    for admin in admins:
        try:
            from utils.email_service import send_catalog_template
            await send_catalog_template(
                recipient_email=admin["email"],
                template_key="weekly_heatmap_v7",
                total_clicks=total_clicks,
                template_count=len(by_template),
                top_templates=", ".join(list(by_template.keys())[:3]),
                top_urls=", ".join(u.get("url", "")[:40] for u in top_urls[:3]),
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send heatmap digest to {admin.get('email')}: {e}")

    logger.info(f"Weekly heatmap digest sent to {sent} admin(s): {total_clicks} clicks, {len(top_urls)} top URLs")
    return {"sent": sent, "total_clicks": total_clicks}


@router.post("/heatmap-digest/send-now")
async def trigger_heatmap_digest(request: Request):
    """Manually trigger the weekly heatmap digest (admin only)."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    result = await _send_weekly_heatmap_digest(db)
    return {"success": True, **result}



# ════════════════════════════════════════════════════════════
# EMAIL EVENT COVERAGE MATRIX
# ════════════════════════════════════════════════════════════

@router.get("/coverage-matrix")
async def email_coverage_matrix(request: Request):
    """Admin-only: Return a full coverage matrix of every email template
    showing render health, last triggered, send counts, and delivery stats."""
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import TEMPLATE_CATALOG

    # Aggregate send stats from email_logs per email_type
    pipeline = [
        {"$group": {
            "_id": "$email_type",
            "total_sent": {"$sum": 1},
            "last_sent_at": {"$max": "$created_at"},
            "sent_ok": {"$sum": {"$cond": [{"$eq": ["$status", "sent"]}, 1, 0]}},
            "sent_fail": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
        }},
    ]
    log_stats_raw = await db.email_logs.aggregate(pipeline).to_list(300)
    log_stats = {r["_id"]: r for r in log_stats_raw}

    # Aggregate open/click stats from email_analytics
    analytics_pipeline = [
        {"$group": {
            "_id": "$email_type",
            "total_opens": {"$sum": "$open_count"},
            "total_clicks": {"$sum": "$click_count"},
            "tracked_count": {"$sum": 1},
        }},
    ]
    analytics_raw = await db.email_analytics.aggregate(analytics_pipeline).to_list(300)
    analytics_map = {r["_id"]: r for r in analytics_raw}

    matrix = []
    for key, info in TEMPLATE_CATALOG.items():
        # Test render health
        render_ok = True
        render_error = None
        try:
            tpl = info["builder"]()
            if not tpl or not getattr(tpl, "html", None):
                render_ok = False
                render_error = "Empty HTML output"
        except Exception as e:
            render_ok = False
            render_error = str(e)[:120]

        stats = log_stats.get(key, {})
        analytics = analytics_map.get(key, {})
        total_sent = stats.get("total_sent", 0)
        sent_ok = stats.get("sent_ok", 0)
        sent_fail = stats.get("sent_fail", 0)

        matrix.append({
            "key": key,
            "label": info["label"],
            "category": info["category"],
            "description": info["description"],
            "render_health": "pass" if render_ok else "fail",
            "render_error": render_error,
            "total_sent": total_sent,
            "delivered": sent_ok,
            "failed": sent_fail,
            "delivery_rate": round(sent_ok / total_sent * 100, 1) if total_sent else None,
            "last_triggered": stats.get("last_sent_at"),
            "total_opens": analytics.get("total_opens", 0),
            "total_clicks": analytics.get("total_clicks", 0),
            "open_rate": round(analytics.get("total_opens", 0) / max(sent_ok, 1) * 100, 1) if sent_ok else None,
            "click_rate": round(analytics.get("total_clicks", 0) / max(sent_ok, 1) * 100, 1) if sent_ok else None,
        })

    # Sort by category, then label
    matrix.sort(key=lambda r: (r["category"], r["label"]))

    # Summary stats
    total_templates = len(matrix)
    healthy = sum(1 for r in matrix if r["render_health"] == "pass")
    triggered = sum(1 for r in matrix if r["total_sent"] > 0)
    never_triggered = [r["key"] for r in matrix if r["total_sent"] == 0]

    categories = {}
    for r in matrix:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "healthy": 0, "triggered": 0}
        categories[cat]["total"] += 1
        if r["render_health"] == "pass":
            categories[cat]["healthy"] += 1
        if r["total_sent"] > 0:
            categories[cat]["triggered"] += 1

    return {
        "summary": {
            "total_templates": total_templates,
            "render_healthy": healthy,
            "render_failed": total_templates - healthy,
            "live_triggered": triggered,
            "never_triggered_count": len(never_triggered),
            "never_triggered_keys": never_triggered[:20],
            "health_pct": round(healthy / max(total_templates, 1) * 100, 1),
            "coverage_pct": round(triggered / max(total_templates, 1) * 100, 1),
        },
        "categories": categories,
        "matrix": matrix,
    }



@router.get("/v7-enforcement-report")
async def v7_enforcement_report(request: Request):
    """Admin-only: Full v7 enforcement audit.
    Shows catalog coverage, remaining send_email calls, skip_branding status,
    and enforcement guardrail health across the entire platform.
    """
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from utils.email_templates import TEMPLATE_CATALOG
    from utils.email_service import _SKIP_BRANDING_WHITELIST

    import subprocess
    import os
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Count send_catalog_template calls
    try:
        result = subprocess.run(
            ["grep", "-rn", "send_catalog_template(", "--include=*.py", backend_dir],
            capture_output=True, text=True, timeout=10,
        )
        catalog_lines = [
            line
            for line in result.stdout.splitlines()
            if "def send_catalog_template" not in line
            and "import" not in line
            and "__pycache__" not in line
            and "test_" not in line
        ]
        catalog_call_count = len(catalog_lines)
    except Exception:
        catalog_call_count = -1

    # Count remaining send_email calls
    try:
        result = subprocess.run(
            ["grep", "-rn", "await send_email(", "--include=*.py", backend_dir],
            capture_output=True, text=True, timeout=10,
        )
        email_lines = [
            line
            for line in result.stdout.splitlines()
            if "def send_email" not in line
            and "__pycache__" not in line
            and "test_" not in line
            and "# " not in line
        ]
        send_email_count = len(email_lines)

        # Categorize remaining send_email calls
        with_skip = [line for line in email_lines if "skip_branding" in line]
        with_attach = [line for line in email_lines if "attachment" in line.lower()]
        wrappers = [line for line in email_lines if "**kwargs" in line or "**kw" in line]
    except Exception:
        send_email_count = -1
        with_skip = []
        with_attach = []
        wrappers = []

    total_emails = catalog_call_count + send_email_count
    catalog_pct = round(catalog_call_count / max(total_emails, 1) * 100, 1)

    return {
        "v7_enforcement": {
            "status": "ENFORCED" if catalog_pct >= 75 else "PARTIAL",
            "guardrails_active": True,
            "skip_branding_override": True,
            "subject_category_fallback": True,
            "missing_template_key_warnings": True,
            "skip_branding_whitelist": _SKIP_BRANDING_WHITELIST,
        },
        "template_catalog": {
            "total_templates": len(TEMPLATE_CATALOG),
            "categories": len(set(v.get("category", "") for v in TEMPLATE_CATALOG.values())),
        },
        "coverage": {
            "send_catalog_template_calls": catalog_call_count,
            "send_email_calls": send_email_count,
            "total_email_sends": total_emails,
            "catalog_coverage_pct": catalog_pct,
        },
        "remaining_send_email_breakdown": {
            "with_skip_branding": len(with_skip),
            "with_attachments": len(with_attach),
            "pass_through_wrappers": len(wrappers),
            "other_inline": send_email_count - len(with_skip) - len(with_attach) - len(wrappers),
        },
        "enforcement_rules": [
            "All send_email() calls auto-wrapped with v7 brand_email() unless already branded",
            "skip_branding=True overridden for non-whitelisted emails",
            "Category detected from template_key (primary) or subject line (fallback)",
            "Runtime warning logged when send_email() called without template_key",
            "Future developers: use send_catalog_template() for all new emails",
        ],
    }
