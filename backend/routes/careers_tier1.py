"""
Careers ATS — Tier 1 + GDPR enhancements.

Features shipped in this module:
  T1-A. AI Resume Scorecard          — Claude ranks applicant vs. role spec
  T1-B. Bulk actions                  — multi-row status / tag / soft-delete
  T1-C. Tags CRUD                     — tag taxonomy + per-application tagging
  G.    GDPR retention engine         — policy + preview + purge + audit trail
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

from routes.db import db, require_admin
from routes.careers_enhancements import _resolve_role_rubric, _now_iso

logger = logging.getLogger(__name__)
router = APIRouter()

APPS_COL = "careers_applications"
GDPR_AUDIT_COL = "careers_gdpr_audit"
GDPR_POLICY_COL = "careers_gdpr_policy"
GDPR_POLICY_KEY = "default"



# Human-friendly status labels used in the applicant-facing status-change email.
_STATUS_LABEL: dict[str, str] = {
    "received": "Application Received",
    "screening": "Under Review",
    "interview": "Interview Stage",
    "offer": "Offer Extended",
    "hired": "Welcome Aboard",
    "rejected": "Decision",
    "withdrawn": "Withdrawn",
    "on_hold": "On Hold",
}


async def _broadcast_status_change(application_ids: list[str], new_status: str) -> None:
    """Send applicant-facing status-update emails after a bulk set_status flip.

    Fire-and-forget. Never raises — failures are logged and skipped so bulk
    actions always succeed even if the transactional email provider hiccups.
    """
    try:
        from utils.email_service import is_email_configured, send_catalog_template
    except Exception as _e:  # pragma: no cover
        logger.warning(f"[careers/bulk] email service unavailable: {_e}")
        return

    if not is_email_configured():
        logger.info("[careers/bulk] email not configured; skipping status-change broadcast")
        return

    label = _STATUS_LABEL.get(new_status, new_status.replace("_", " ").title())
    # Skip loud notifications for terminal statuses the applicant already owns
    # (withdrawn) or purely internal states we don't want to tell them about.
    if new_status in {"withdrawn", "on_hold"}:
        return

    async for doc in db[APPS_COL].find(
        {"application_id": {"$in": application_ids}, "merged_into": {"$exists": False}},
        {
            "_id": 0,
            "application_id": 1,
            "name": 1,
            "email": 1,
            "role_title": 1,
        },
    ):
        email = (doc.get("email") or "").strip()
        if not email:
            continue
        try:
            await send_catalog_template(
                recipient_email=email,
                template_key="career_status_update",
                applicant_name=doc.get("name") or "there",
                position=doc.get("role_title") or "your application",
                application_id=doc["application_id"],
                status=new_status,
                status_label=label,
                headers={"X-Application-ID": doc["application_id"]},
            )
            logger.info(
                f"[careers/bulk] status-update email sent for "
                f"{doc['application_id']} → {new_status}"
            )
        except Exception as _e:  # pragma: no cover
            logger.warning(
                f"[careers/bulk] status-update email failed for "
                f"{doc['application_id']}: {_e}"
            )



# ─────────────────────────────────────────────────────────────────────────────
# T1-A. AI Resume Scorecard
# ─────────────────────────────────────────────────────────────────────────────


class ResumeScoreBody(BaseModel):
    resume_text: Optional[str] = Field(None, max_length=60000)
    role_spec: Optional[str] = Field(None, max_length=8000)
    persist: bool = True


def _extract_resume_text(app_doc: dict[str, Any]) -> str:
    """Best-effort pull of resume-like text from an application doc."""
    parts: list[str] = []
    for k in ("cover_letter", "resume_text", "summary", "bio", "skills", "experience", "linkedin_url"):
        v = app_doc.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(f"[{k}]\n{v.strip()}")
        elif isinstance(v, list):
            parts.append(f"[{k}]\n" + "\n".join(map(str, v)))
    docs = app_doc.get("documents") or []
    for d in docs[:3]:
        if isinstance(d, dict):
            txt = d.get("extracted_text") or d.get("content") or ""
            if isinstance(txt, str) and txt.strip():
                parts.append(f"[{d.get('filename', 'document')}]\n{txt.strip()[:8000]}")
    return "\n\n".join(parts)[:20000]


@router.post("/careers/applications/{app_id}/resume-score")
async def admin_resume_score(request: Request, app_id: str, body: ResumeScoreBody):
    """Generate an AI resume score (0-100) + skills gap analysis for an applicant."""
    await require_admin(request)
    app_doc = await db[APPS_COL].find_one({"application_id": app_id})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")

    resume_text = (body.resume_text or _extract_resume_text(app_doc)).strip()
    if len(resume_text) < 40:
        raise HTTPException(
            status_code=400,
            detail="Not enough resume text on file (need ≥40 chars). Pass `resume_text` in the request body or add documents to the application.",
        )

    role_title = app_doc.get("role_title") or "Open role"
    role_spec = (body.role_spec or app_doc.get("role_description") or app_doc.get("role_spec") or "").strip()
    rubric = _resolve_role_rubric(role_title)
    criteria_ids = [c["id"] for c in rubric["criteria"]]

    system = (
        "You are a senior technical recruiter scoring a candidate's resume against a role. "
        "Your response MUST be strict JSON with this exact schema: "
        '{"score": <0-100>, "fit_score": <0-100>, "cultural_fit_pct": <0-100>, '
        '"skills_matched": [<skill>], "skills_missing": [<skill>], '
        '"rubric_scores": {<criterion_id>: <1-5>}, '
        '"top_strengths": [<short phrase>], "top_gaps": [<short phrase>], '
        '"one_liner_summary": "<1 sentence verdict>"} '
        "Use ONLY the rubric criterion ids listed below. Be rigorous — reserve 90+ for exceptional fits."
    )
    prompt = (
        f"ROLE: {role_title}\n"
        f"ROLE SPEC / REQUIREMENTS: {role_spec or '(not provided — infer from role title)'}\n"
        f"RUBRIC CRITERIA (score each 1-5): {', '.join(criteria_ids)}\n\n"
        f"RESUME / APPLICATION TEXT:\n{resume_text}\n\n"
        f"Produce the JSON score."
    )

    try:
        from utils.llm_helper import generate_verified_json
        result = await generate_verified_json(
            prompt=prompt,
            system_message=system,
            session_id=f"resume-score-{app_id[-8:]}",
            model="gpt-4o",
            feature="careers_resume_score",
        )
    except Exception as e:
        logger.warning(f"[careers/resume-score] LLM failed for {app_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Resume scoring service unavailable: {str(e)[:100]}")

    def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
        try:
            return max(lo, min(hi, int(v)))
        except Exception:
            return default

    score = _clamp_int((result or {}).get("score"), 0, 100, 50)
    fit = _clamp_int((result or {}).get("fit_score"), 0, 100, score)
    cultural = _clamp_int((result or {}).get("cultural_fit_pct"), 0, 100, 50)
    rubric_scores_raw = (result or {}).get("rubric_scores") or {}
    rubric_scores = {cid: _clamp_int(rubric_scores_raw.get(cid, 3), 1, 5, 3) for cid in criteria_ids}

    payload = {
        "score": score,
        "fit_score": fit,
        "cultural_fit_pct": cultural,
        "rubric_key": rubric["role_key"],
        "rubric_scores": rubric_scores,
        "skills_matched": list(map(str, (result or {}).get("skills_matched") or []))[:20],
        "skills_missing": list(map(str, (result or {}).get("skills_missing") or []))[:20],
        "top_strengths": list(map(str, (result or {}).get("top_strengths") or []))[:5],
        "top_gaps": list(map(str, (result or {}).get("top_gaps") or []))[:5],
        "one_liner_summary": str((result or {}).get("one_liner_summary") or "")[:400],
        "resume_length": len(resume_text),
        "model": "gpt-4o",
        "generated_at": _now_iso(),
    }
    if body.persist:
        await db[APPS_COL].update_one(
            {"application_id": app_id},
            {"$set": {"resume_score": payload}},
        )
    return {"ok": True, "resume_score": payload, "persisted": body.persist}


# ─────────────────────────────────────────────────────────────────────────────
# T1-B. Bulk actions
# ─────────────────────────────────────────────────────────────────────────────

BULK_ACTIONS = {
    "set_status": "Change status",
    "add_tag": "Add tag",
    "remove_tag": "Remove tag",
    "soft_delete_gdpr": "GDPR soft-delete",
}

ALLOWED_STATUSES = {
    "received", "screening", "interview", "offer", "hired",
    "rejected", "withdrawn", "on_hold",
}


class BulkActionBody(BaseModel):
    application_ids: list[str] = Field(..., min_length=1, max_length=200)
    action: str = Field(..., pattern="^(set_status|add_tag|remove_tag|soft_delete_gdpr)$")
    new_status: Optional[str] = None
    tag: Optional[str] = Field(None, max_length=40)
    gdpr_reason: Optional[str] = Field("bulk_admin_action", max_length=120)


@router.post("/careers/applications/bulk-action")
async def admin_bulk_action(request: Request, body: BulkActionBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or getattr(admin, "user_id", None) or "admin"
    now = _now_iso()
    updated = 0
    failures: list[dict[str, Any]] = []

    if body.action == "set_status":
        if not body.new_status or body.new_status not in ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail=f"invalid status; must be one of {sorted(ALLOWED_STATUSES)}")
        res = await db[APPS_COL].update_many(
            {"application_id": {"$in": body.application_ids}, "merged_into": {"$exists": False}},
            {"$set": {"status": body.new_status, "status_updated_at": now, "status_updated_by": actor}},
        )
        updated = res.modified_count
        # Fire-and-forget applicant notifications deep-linking to the public
        # tracker page. Runs AFTER the DB update so the applicant's live
        # status is already flipped by the time the email hits their inbox.
        try:
            import asyncio as _asyncio
            _asyncio.create_task(_broadcast_status_change(body.application_ids, body.new_status))
        except Exception as _e:  # pragma: no cover — never block bulk action
            logger.warning(f"[careers/bulk] status-change broadcast skipped: {_e}")

    elif body.action == "add_tag":
        if not body.tag:
            raise HTTPException(status_code=400, detail="tag required")
        tag_slug = body.tag.strip().lower().replace(" ", "-")[:40]
        res = await db[APPS_COL].update_many(
            {"application_id": {"$in": body.application_ids}, "merged_into": {"$exists": False}},
            {"$addToSet": {"tags": tag_slug}, "$set": {"status_updated_at": now}},
        )
        updated = res.modified_count

    elif body.action == "remove_tag":
        if not body.tag:
            raise HTTPException(status_code=400, detail="tag required")
        tag_slug = body.tag.strip().lower().replace(" ", "-")[:40]
        res = await db[APPS_COL].update_many(
            {"application_id": {"$in": body.application_ids}, "merged_into": {"$exists": False}},
            {"$pull": {"tags": tag_slug}, "$set": {"status_updated_at": now}},
        )
        updated = res.modified_count

    elif body.action == "soft_delete_gdpr":
        # Mark as gdpr_purged — preserves application_id for the audit trail but
        # clears PII fields. Full delete only via the retention engine.
        redactions = {
            "name": "[GDPR-REDACTED]",
            "email": "",
            "phone": "",
            "cover_letter": "",
            "resume_text": "",
            "documents": [],
            "admin_notes": f"GDPR soft-deleted {now} by {actor}; reason: {body.gdpr_reason}",
            "status": "rejected",
            "status_updated_at": now,
            "gdpr_soft_deleted_at": now,
            "gdpr_soft_deleted_by": actor,
            "gdpr_reason": body.gdpr_reason or "bulk_admin_action",
        }
        res = await db[APPS_COL].update_many(
            {"application_id": {"$in": body.application_ids}, "merged_into": {"$exists": False}, "gdpr_soft_deleted_at": {"$exists": False}},
            {"$set": redactions},
        )
        updated = res.modified_count
        # Write audit rows
        if updated:
            await db[GDPR_AUDIT_COL].insert_many([
                {
                    "audit_id": f"gdpr_{uuid.uuid4().hex[:12]}",
                    "application_id": aid,
                    "kind": "soft_delete",
                    "actor": actor,
                    "reason": body.gdpr_reason or "bulk_admin_action",
                    "created_at": now,
                } for aid in body.application_ids
            ])

    return {
        "ok": True,
        "action": body.action,
        "requested": len(body.application_ids),
        "updated": updated,
        "failures": failures,
        "generated_at": now,
    }


@router.get("/careers/applications/bulk-action/options")
async def admin_bulk_action_options(request: Request):
    await require_admin(request)
    # Tag usage frequency for autocomplete
    tag_counts: list[dict[str, Any]] = []
    async for d in db[APPS_COL].aggregate([
        {"$match": {"tags": {"$type": "array"}}},
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 40},
    ]):
        tag_counts.append({"tag": d.get("_id"), "count": int(d.get("n") or 0)})
    return {
        "actions": BULK_ACTIONS,
        "statuses": sorted(ALLOWED_STATUSES),
        "tags": tag_counts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# G. GDPR retention engine
# ─────────────────────────────────────────────────────────────────────────────


class GDPRPolicyBody(BaseModel):
    rejected_retention_days: int = Field(180, ge=7, le=3650)
    withdrawn_retention_days: int = Field(180, ge=7, le=3650)
    audit_enabled: bool = True
    auto_purge_enabled: bool = False


async def _read_policy() -> dict[str, Any]:
    doc = await db[GDPR_POLICY_COL].find_one({"key": GDPR_POLICY_KEY}, {"_id": 0})
    if not doc:
        return {
            "key": GDPR_POLICY_KEY,
            "rejected_retention_days": 180,
            "withdrawn_retention_days": 180,
            "audit_enabled": True,
            "auto_purge_enabled": False,
            "updated_at": None,
            "updated_by": None,
        }
    return doc


@router.get("/careers/gdpr/retention-policy")
async def admin_get_retention_policy(request: Request):
    await require_admin(request)
    return {"policy": await _read_policy()}


@router.post("/careers/gdpr/retention-policy")
async def admin_set_retention_policy(request: Request, body: GDPRPolicyBody):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or getattr(admin, "user_id", None) or "admin"
    now = _now_iso()
    payload = {
        "key": GDPR_POLICY_KEY,
        "rejected_retention_days": body.rejected_retention_days,
        "withdrawn_retention_days": body.withdrawn_retention_days,
        "audit_enabled": body.audit_enabled,
        "auto_purge_enabled": body.auto_purge_enabled,
        "updated_at": now,
        "updated_by": actor,
    }
    await db[GDPR_POLICY_COL].update_one(
        {"key": GDPR_POLICY_KEY},
        {"$set": payload},
        upsert=True,
    )
    if body.audit_enabled:
        await db[GDPR_AUDIT_COL].insert_one({
            "audit_id": f"gdpr_{uuid.uuid4().hex[:12]}",
            "application_id": None,
            "kind": "policy_update",
            "actor": actor,
            "payload": payload,
            "created_at": now,
        })
    return {"ok": True, "policy": payload}


def _purge_candidate_query(policy: dict[str, Any]) -> dict[str, Any]:
    rej_cut = (datetime.now(timezone.utc) - timedelta(days=int(policy.get("rejected_retention_days", 180)))).isoformat()
    with_cut = (datetime.now(timezone.utc) - timedelta(days=int(policy.get("withdrawn_retention_days", 180)))).isoformat()
    return {
        "$and": [
            {"gdpr_purged_at": {"$exists": False}},
            {"$or": [
                {"status": "rejected", "status_updated_at": {"$lte": rej_cut}},
                {"status": "withdrawn", "status_updated_at": {"$lte": with_cut}},
            ]},
        ],
    }


@router.get("/careers/gdpr/purge-preview")
async def admin_gdpr_purge_preview(request: Request):
    await require_admin(request)
    policy = await _read_policy()
    q = _purge_candidate_query(policy)
    total = await db[APPS_COL].count_documents(q)
    items: list[dict[str, Any]] = []
    async for d in db[APPS_COL].find(q, {"_id": 0, "application_id": 1, "name": 1, "email": 1, "status": 1, "status_updated_at": 1, "role_title": 1}).sort("status_updated_at", 1).limit(50):
        items.append({
            "application_id": d.get("application_id"),
            "name": d.get("name") or "",
            "email": d.get("email") or "",
            "status": d.get("status") or "",
            "last_activity_at": d.get("status_updated_at") or "",
            "position": d.get("role_title") or "",
        })
    return {"policy": policy, "total_eligible": total, "preview": items, "generated_at": _now_iso()}


@router.post("/careers/gdpr/purge")
async def admin_gdpr_purge(request: Request, dry_run: bool = Query(False)):
    admin = await require_admin(request)
    actor = getattr(admin, "email", None) or getattr(admin, "user_id", None) or "admin"
    policy = await _read_policy()
    q = _purge_candidate_query(policy)
    now = _now_iso()

    purged_ids: list[str] = []
    async for d in db[APPS_COL].find(q, {"_id": 0, "application_id": 1}):
        if d.get("application_id"):
            purged_ids.append(d["application_id"])

    if dry_run:
        return {"ok": True, "dry_run": True, "would_purge": len(purged_ids), "ids": purged_ids[:100]}

    if purged_ids:
        await db[APPS_COL].update_many(
            {"application_id": {"$in": purged_ids}},
            {"$set": {
                "name": "[GDPR-PURGED]",
                "email": "",
                "phone": "",
                "cover_letter": "",
                "resume_text": "",
                "documents": [],
                "admin_notes": f"GDPR-purged by retention policy on {now}; actor={actor}",
                "gdpr_purged_at": now,
                "gdpr_purged_by": actor,
                "gdpr_reason": "retention_policy",
            }},
        )
        if policy.get("audit_enabled", True):
            await db[GDPR_AUDIT_COL].insert_many([
                {
                    "audit_id": f"gdpr_{uuid.uuid4().hex[:12]}",
                    "application_id": aid,
                    "kind": "retention_purge",
                    "actor": actor,
                    "policy_snapshot": policy,
                    "created_at": now,
                } for aid in purged_ids
            ])
    return {"ok": True, "purged": len(purged_ids), "ids": purged_ids[:100], "generated_at": now}


@router.get("/careers/gdpr/audit")
async def admin_gdpr_audit(request: Request, limit: int = Query(100, ge=1, le=500), application_id: Optional[str] = None):
    await require_admin(request)
    q: dict[str, Any] = {}
    if application_id:
        q["application_id"] = application_id
    items: list[dict[str, Any]] = []
    async for d in db[GDPR_AUDIT_COL].find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
        items.append(d)
    return {"items": items, "count": len(items)}


# ─────────────────────────────────────────────────────────────────────────────
# Auto-purge scheduler job — runs daily at 03:00 UTC via APScheduler
# ─────────────────────────────────────────────────────────────────────────────


async def scheduled_gdpr_auto_purge() -> dict[str, Any]:
    """APScheduler entrypoint. Reads the current policy and, if
    `auto_purge_enabled`, runs the retention purge with actor='scheduler'.
    Writes an audit row for every purged id and a summary stamp on the policy.
    Never raises — returns a dict for callers (e.g. manual run endpoint)."""
    try:
        policy = await _read_policy()
    except Exception as e:
        logger.warning(f"[careers/gdpr] auto-purge: could not read policy: {e}")
        return {"ok": False, "reason": "policy_read_failed", "detail": str(e)[:120]}

    if not policy.get("auto_purge_enabled"):
        return {"ok": True, "skipped": True, "reason": "auto_purge_disabled"}

    q = _purge_candidate_query(policy)
    now = _now_iso()
    purged_ids: list[str] = []
    try:
        async for d in db[APPS_COL].find(q, {"_id": 0, "application_id": 1}):
            if d.get("application_id"):
                purged_ids.append(d["application_id"])
    except Exception as e:
        logger.warning(f"[careers/gdpr] auto-purge: candidate scan failed: {e}")
        return {"ok": False, "reason": "scan_failed", "detail": str(e)[:120]}

    purged = 0
    if purged_ids:
        try:
            await db[APPS_COL].update_many(
                {"application_id": {"$in": purged_ids}},
                {"$set": {
                    "name": "[GDPR-PURGED]",
                    "email": "",
                    "phone": "",
                    "cover_letter": "",
                    "resume_text": "",
                    "documents": [],
                    "admin_notes": f"GDPR-auto-purged by scheduler on {now}",
                    "gdpr_purged_at": now,
                    "gdpr_purged_by": "scheduler",
                    "gdpr_reason": "scheduled_retention_policy",
                }},
            )
            purged = len(purged_ids)
            if policy.get("audit_enabled", True):
                await db[GDPR_AUDIT_COL].insert_many([
                    {
                        "audit_id": f"gdpr_{uuid.uuid4().hex[:12]}",
                        "application_id": aid,
                        "kind": "retention_purge",
                        "actor": "scheduler",
                        "policy_snapshot": policy,
                        "trigger": "apscheduler_daily",
                        "created_at": now,
                    } for aid in purged_ids
                ])
        except Exception as e:
            logger.warning(f"[careers/gdpr] auto-purge: redact failed: {e}")
            return {"ok": False, "reason": "redact_failed", "detail": str(e)[:120]}

    # Track last-run on the policy for operator visibility
    await db[GDPR_POLICY_COL].update_one(
        {"key": GDPR_POLICY_KEY},
        {"$set": {
            "last_auto_purge_at": now,
            "last_auto_purge_count": purged,
            "last_auto_purge_trigger": "apscheduler_daily",
        }},
        upsert=True,
    )
    logger.info(f"[careers/gdpr] auto-purge scheduler: purged={purged} at={now}")
    return {"ok": True, "purged": purged, "ids": purged_ids[:50], "trigger": "apscheduler_daily", "ran_at": now}


@router.post("/careers/gdpr/auto-purge/run-now")
async def admin_trigger_auto_purge(request: Request):
    """Admin-triggered synchronous run of the scheduler entrypoint — useful
    for testing the exact cron path without waiting for 03:00 UTC."""
    await require_admin(request)
    result = await scheduled_gdpr_auto_purge()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# GDPR daily digest email — runs at 03:05 UTC (5 min after the auto-purge)
# ─────────────────────────────────────────────────────────────────────────────


async def _gather_gdpr_daily_digest_payload(lookback_hours: int = 26) -> dict[str, Any]:
    """Aggregate the past ~24h of GDPR auto-purge activity into a payload
    suitable for the `careers_gdpr_purge_daily_digest` email template.

    Pulls from:
      - careers_gdpr_policy.default.last_auto_purge_* stamps (current policy state)
      - careers_gdpr_audit rows with trigger='apscheduler_daily' in the window
      - candidate age (created_at) on the purged applications for oldest/newest
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=lookback_hours)).isoformat()
    run_date_label = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    policy = await _read_policy()
    retention_days = int(policy.get("retention_days") or 0)
    auto_purge_enabled = bool(policy.get("auto_purge_enabled"))
    last_at = str(policy.get("last_auto_purge_at") or "")
    last_count = int(policy.get("last_auto_purge_count") or 0)
    last_trigger = str(policy.get("last_auto_purge_trigger") or "apscheduler_daily")

    # Pull audit rows from the window
    q = {
        "kind": "retention_purge",
        "actor": "scheduler",
        "trigger": "apscheduler_daily",
        "created_at": {"$gte": cutoff},
    }
    audit_rows: list[dict[str, Any]] = []
    try:
        async for d in db[GDPR_AUDIT_COL].find(q, {"_id": 0, "application_id": 1, "created_at": 1}).limit(5000):
            audit_rows.append(d)
    except Exception as e:
        logger.warning(f"[careers/gdpr] digest: audit scan failed: {e}")

    purged_count = len(audit_rows) or last_count

    # For oldest/newest "age" we peek at the purged apps' original created_at.
    oldest_days = 0
    newest_days = 0
    if audit_rows:
        try:
            app_ids = [r.get("application_id") for r in audit_rows if r.get("application_id")]
            if app_ids:
                ages: list[int] = []
                async for a in db[APPS_COL].find(
                    {"application_id": {"$in": app_ids}},
                    {"_id": 0, "created_at": 1},
                ).limit(5000):
                    created = a.get("created_at")
                    if isinstance(created, str) and created:
                        try:
                            ca = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            ages.append(max(int((now - ca).days), 0))
                        except Exception:
                            continue
                if ages:
                    oldest_days = max(ages)
                    newest_days = min(ages)
        except Exception as e:
            logger.warning(f"[careers/gdpr] digest: age lookup failed: {e}")

    return {
        "run_date_label": run_date_label,
        "purged_count": purged_count,
        "retention_days": retention_days,
        "oldest_purged_days": oldest_days,
        "newest_purged_days": newest_days,
        "audit_rows_written": len(audit_rows),
        "run_trigger": last_trigger,
        "ran_at": last_at,
        "auto_purge_enabled": auto_purge_enabled,
        "policy_actor": "scheduler",
    }


async def _resolve_gdpr_digest_recipients() -> list[str]:
    """Admin recipient list for the GDPR daily digest.
    Priority order:
      1. settings.careers_gdpr_digest_recipients.value (list of emails)
      2. env var CAREERS_GDPR_DIGEST_RECIPIENTS (comma-separated)
      3. env var GDPR_DIGEST_RECIPIENT (single email — reuses gdpr_self_service default)
      4. All `users` with is_admin=True
    """
    import os
    # 1. DB override
    try:
        doc = await db.settings.find_one(
            {"key": "careers_gdpr_digest_recipients"}, {"_id": 0}
        )
        if doc and isinstance(doc.get("value"), list) and doc["value"]:
            return [str(x).strip() for x in doc["value"] if x and "@" in str(x)]
    except Exception:
        pass
    # 2. env csv
    env_csv = os.environ.get("CAREERS_GDPR_DIGEST_RECIPIENTS", "")
    if env_csv.strip():
        lst = [e.strip() for e in env_csv.split(",") if "@" in e]
        if lst:
            return lst
    # 3. single env
    one = os.environ.get("GDPR_DIGEST_RECIPIENT", "").strip()
    if one and "@" in one:
        return [one]
    # 4. all admins
    admins: list[str] = []
    try:
        async for u in db.users.find(
            {"is_admin": True},
            {"_id": 0, "email": 1},
        ).limit(50):
            e = str(u.get("email") or "").strip()
            if e and "@" in e:
                admins.append(e)
    except Exception:
        pass
    return admins


async def send_gdpr_purge_daily_digest(trigger: str = "apscheduler_daily") -> dict[str, Any]:
    """Send the daily GDPR auto-purge digest to all configured admins.

    Never raises into the caller (scheduler). Returns a result dict the cron
    can log. Silently skips if there are no recipients or email transport
    is not configured.
    """
    try:
        payload = await _gather_gdpr_daily_digest_payload()
    except Exception as e:
        logger.error(f"[careers/gdpr-digest] payload build failed: {e}")
        return {"ok": False, "reason": "payload_failed", "detail": str(e)[:200]}

    try:
        recipients = await _resolve_gdpr_digest_recipients()
    except Exception as e:
        logger.error(f"[careers/gdpr-digest] recipient resolution failed: {e}")
        return {"ok": False, "reason": "recipients_failed", "detail": str(e)[:200]}

    if not recipients:
        logger.info("[careers/gdpr-digest] no recipients configured — skipping")
        return {"ok": True, "skipped": True, "reason": "no_recipients", "payload": payload}

    try:
        from utils.email_service import is_email_configured, send_catalog_template
    except Exception as e:
        logger.error(f"[careers/gdpr-digest] email_service import failed: {e}")
        return {"ok": False, "reason": "email_import_failed", "detail": str(e)[:200]}

    if not is_email_configured():
        logger.info("[careers/gdpr-digest] email not configured — logging digest only")
        return {"ok": True, "skipped": True, "reason": "email_not_configured", "payload": payload}

    sent_ok = 0
    sent_failed = 0
    errors: list[str] = []
    for email in recipients:
        try:
            res = await send_catalog_template(
                recipient_email=email,
                template_key="careers_gdpr_purge_daily_digest",
                recipient_name="",
                **payload,
            )
            if res.get("success"):
                sent_ok += 1
            else:
                sent_failed += 1
                errors.append(f"{email}: {res.get('error', 'unknown')[:80]}")
        except Exception as e:
            sent_failed += 1
            errors.append(f"{email}: {str(e)[:80]}")

    logger.info(
        f"[careers/gdpr-digest] dispatched trigger={trigger} "
        f"sent_ok={sent_ok} failed={sent_failed} of {len(recipients)} "
        f"purged={payload['purged_count']} retention_days={payload['retention_days']}"
    )

    # Log into the Compliance Digest Hub feed (fail-safe — never break the
    # scheduler on logging errors).
    try:
        from routes.compliance_digest_hub import log_digest_entry
        summary = (
            f"Retention {payload['retention_days']}d · "
            f"{payload['purged_count']} record(s) purged · "
            f"{payload['audit_rows_written']} audit row(s) · "
            f"status={'ran' if payload['purged_count'] else 'no-op'}"
        )
        subject_line = (
            f"GDPR auto-purge: {payload['purged_count']} candidate(s) purged "
            f"({payload['run_date_label']})"
            if payload['purged_count'] else
            f"GDPR auto-purge clean: 0 purged ({payload['run_date_label']})"
        )
        await log_digest_entry(
            kind="careers_gdpr_purge_daily",
            subject=subject_line,
            summary=summary,
            recipients=recipients,
            sent_ok=sent_ok,
            sent_failed=sent_failed,
            payload=payload,
            trigger=trigger,
        )
    except Exception as _e:
        logger.warning(f"[careers/gdpr-digest] hub-log failed: {_e}")

    return {
        "ok": True,
        "sent_ok": sent_ok,
        "sent_failed": sent_failed,
        "recipients": recipients,
        "payload": payload,
        "errors": errors[:10],
        "trigger": trigger,
    }


@router.post("/careers/gdpr/digest/run-now")
async def admin_trigger_gdpr_digest(request: Request):
    """Admin-triggered synchronous run of the GDPR daily digest — for testing
    the exact cron path without waiting for 03:05 UTC."""
    await require_admin(request)
    return await send_gdpr_purge_daily_digest(trigger="manual_admin")

