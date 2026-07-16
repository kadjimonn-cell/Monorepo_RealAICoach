"""
GDPR Self-Service — Data Export & Delete
----------------------------------------

Public, email-verified flow for end users (contact-form visitors, support-ticket
submitters, feedback givers) to exercise their GDPR/CCPA rights:

    1. POST /api/gdpr/request   {email, action}       → sends a signed, 15-min link
    2. POST /api/gdpr/verify    {token}               → returns counts & request meta
    3. POST /api/gdpr/execute   {token, confirm:true} → exports JSON or deletes rows

Security
    • HMAC-SHA256 signed, JWT-encoded token (`JWT_SECRET`). 15-min TTL.
    • Scope lookup uses `email_hash` (already deterministically hashed at insert).
    • Rate-limit: max 3 active requests per email per 24h.
    • Audit log row written on every `execute`.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field

from routes.db import db, JWT_SECRET
from utils.field_encryption import hash_lookup, decrypt_doc
from utils.email_service import send_catalog_template

logger = logging.getLogger("gdpr")
router = APIRouter(prefix="/gdpr", tags=["GDPR"])

# ── Collections & decrypt fields ─────────────────────────────────────────
_GDPR_COLLECTIONS = {
    "contact_submissions": ("name", "email", "message", "ip"),
    "support_tickets": ("name", "email", "message"),
    "feedback": ("email", "message"),
}

TOKEN_TTL_MIN = 15
MAX_REQUESTS_PER_DAY = 3
ACTIONS = ("export", "delete")


# ── Models ───────────────────────────────────────────────────────────────
class GDPRRequestIn(BaseModel):
    email: EmailStr
    action: Literal["export", "delete"]


class GDPRTokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=4096)


class GDPRExecuteIn(BaseModel):
    token: str = Field(min_length=10, max_length=4096)
    confirm: bool = False


# ── Token helpers ────────────────────────────────────────────────────────
def _issue_token(email: str, action: str, request_id: str) -> str:
    payload = {
        "kind": "gdpr_self_service",
        "email_hash": hash_lookup(email),
        "action": action,
        "request_id": request_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MIN),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=400, detail="Invalid or expired link") from e
    if payload.get("kind") != "gdpr_self_service":
        raise HTTPException(status_code=400, detail="Invalid link kind")
    if payload.get("action") not in ACTIONS:
        raise HTTPException(status_code=400, detail="Invalid action")
    return payload


def _frontend_base() -> str:
    base = (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("PUBLIC_APP_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
        or ""
    ).rstrip("/")
    return base


async def _count_records(email_hash: str) -> dict:
    counts = {}
    for coll in _GDPR_COLLECTIONS:
        counts[coll] = await db[coll].count_documents({"email_hash": email_hash})
    counts["total"] = sum(counts.values())
    return counts


# ── Endpoints ────────────────────────────────────────────────────────────
@router.post("/request")
async def gdpr_request(payload: GDPRRequestIn, request: Request):
    """
    Start a self-service data request. Always returns 200 (enumeration-resistant):
    even if no records exist or an abuse check fails, the response is identical.
    """
    email = payload.email.strip().lower()
    email_hash = hash_lookup(email)
    action = payload.action
    now = datetime.now(timezone.utc)

    # Abuse guard — enumeration-resistant, just ignore but return success
    cutoff = now - timedelta(hours=24)
    recent = await db.gdpr_requests.count_documents({
        "email_hash": email_hash,
        "created_at": {"$gte": cutoff.isoformat()},
    })
    if recent >= MAX_REQUESTS_PER_DAY:
        logger.warning("gdpr: rate limit %s hits for %s", recent, email_hash[:10])
        return {"status": "queued"}

    counts = await _count_records(email_hash)

    request_id = f"gdpr_{now.strftime('%Y%m%d%H%M%S')}_{email_hash[:10]}_{secrets.token_hex(3)}"
    token = _issue_token(email, action, request_id)
    doc = {
        "request_id": request_id,
        "email_hash": email_hash,
        "action": action,
        "status": "pending_verification",
        "record_counts_at_request": counts,
        "created_at": now.isoformat(),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:500],
    }
    await db.gdpr_requests.insert_one(doc)

    # Build verify link
    base = _frontend_base()
    verify_link = f"{base}/privacy-verify?token={token}" if base else f"/privacy-verify?token={token}"
    # For EXPORT — also build a 1-click direct-download link (skips the confirmation page)
    api_base = os.environ.get("PUBLIC_API_URL") or base
    download_link = f"{api_base}/api/gdpr/download?token={token}"

    # Dispatch via v7 catalog template (enforces branded shell, proper HTML, plain-text fallback)
    try:
        if action == "export":
            await send_catalog_template(
                recipient_email=email,
                template_key="gdpr_export_ready",
                download_link=download_link,
                review_link=verify_link,
                request_id=request_id,
                expiry_minutes=TOKEN_TTL_MIN,
            )
        else:
            await send_catalog_template(
                recipient_email=email,
                template_key="gdpr_delete_verify",
                verify_link=verify_link,
                request_id=request_id,
                expiry_minutes=TOKEN_TTL_MIN,
            )
    except Exception as exc:
        logger.error("gdpr: email dispatch failed for %s: %s", email_hash[:10], exc)

    return {"status": "queued"}


@router.post("/verify")
async def gdpr_verify(payload: GDPRTokenIn):
    """Validate a token and return record-count summary (no data yet)."""
    data = _decode_token(payload.token)
    doc = await db.gdpr_requests.find_one({"request_id": data["request_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Request not found")
    if doc.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Request already completed")
    counts = await _count_records(data["email_hash"])
    return {
        "request_id": data["request_id"],
        "action": data["action"],
        "record_counts": counts,
        "expires_at_utc": datetime.fromtimestamp(data["exp"], tz=timezone.utc).isoformat(),
    }


@router.post("/execute")
async def gdpr_execute(payload: GDPRExecuteIn, request: Request):
    """
    Execute the requested action.
      • export → returns JSON blob of decrypted data
      • delete → hard-deletes matching rows and returns counts
    """
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation flag is required")
    data = _decode_token(payload.token)
    email_hash = data["email_hash"]
    action = data["action"]
    request_id = data["request_id"]

    doc = await db.gdpr_requests.find_one({"request_id": request_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Request not found")
    if doc.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Request already completed")

    now = datetime.now(timezone.utc)
    audit_entry_common = {
        "request_id": request_id,
        "email_hash": email_hash,
        "action": action,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:500],
        "timestamp": now.isoformat(),
    }

    if action == "export":
        export = {}
        for coll, enc_fields in _GDPR_COLLECTIONS.items():
            rows = await db[coll].find({"email_hash": email_hash}, {"_id": 0}).to_list(1000)
            for r in rows:
                decrypt_doc(r, enc_fields)
            export[coll] = rows

        await db.gdpr_requests.update_one(
            {"request_id": request_id},
            {"$set": {"status": "completed", "completed_at": now.isoformat(),
                      "record_counts_at_execute": {k: len(v) for k, v in export.items()}}},
        )
        await db.gdpr_audit_log.insert_one({
            **audit_entry_common,
            "result": "exported",
            "counts": {k: len(v) for k, v in export.items()},
        })
        return {
            "request_id": request_id,
            "action": "export",
            "generated_at_utc": now.isoformat(),
            "data": export,
        }

    # action == "delete"
    deleted = {}
    for coll in _GDPR_COLLECTIONS:
        res = await db[coll].delete_many({"email_hash": email_hash})
        deleted[coll] = res.deleted_count

    await db.gdpr_requests.update_one(
        {"request_id": request_id},
        {"$set": {"status": "completed", "completed_at": now.isoformat(),
                  "deleted_counts": deleted}},
    )
    await db.gdpr_audit_log.insert_one({
        **audit_entry_common,
        "result": "deleted",
        "counts": deleted,
    })
    return {
        "request_id": request_id,
        "action": "delete",
        "completed_at_utc": now.isoformat(),
        "deleted": deleted,
    }


@router.get("/download")
async def gdpr_download(token: str, request: Request):
    """
    1-click export download — the verify email's "Download My Data" button
    hits this endpoint directly with the signed token. Executes the export,
    marks the request completed, writes the audit log, and streams the JSON
    as an attachment. Mobile-webview friendly (single-tap download).
    Export-only (delete still requires explicit UI confirmation).
    """
    data = _decode_token(token)
    if data.get("action") != "export":
        raise HTTPException(status_code=400, detail="Direct download supports export only")

    email_hash = data["email_hash"]
    request_id = data["request_id"]
    doc = await db.gdpr_requests.find_one({"request_id": request_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Request not found")
    if doc.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Export already completed — request a new link")

    # Collect + decrypt
    export: dict = {}
    for coll, enc_fields in _GDPR_COLLECTIONS.items():
        rows = await db[coll].find({"email_hash": email_hash}, {"_id": 0}).to_list(1000)
        for r in rows:
            decrypt_doc(r, enc_fields)
        export[coll] = rows

    now = datetime.now(timezone.utc)
    payload = {
        "request_id": request_id,
        "action": "export",
        "generated_at_utc": now.isoformat(),
        "data": export,
    }

    await db.gdpr_requests.update_one(
        {"request_id": request_id},
        {"$set": {
            "status": "completed",
            "completed_at": now.isoformat(),
            "record_counts_at_execute": {k: len(v) for k, v in export.items()},
            "delivery_mode": "direct_download",
        }},
    )
    await db.gdpr_audit_log.insert_one({
        "request_id": request_id,
        "email_hash": email_hash,
        "action": "export",
        "result": "exported",
        "counts": {k: len(v) for k, v in export.items()},
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:500],
        "timestamp": now.isoformat(),
        "delivery_mode": "direct_download",
    })

    filename = f"realaicoach_data_{request_id}.json"
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


# ─────────────────────────────────────────────────────────────────────────
# Admin — compliance officer dashboard
# ─────────────────────────────────────────────────────────────────────────
from routes.db import require_admin  # noqa: E402


@router.get("/admin/requests")
async def admin_list_requests(
    request: Request,
    status: str = "all",
    action: str = "all",
    limit: int = 50,
    skip: int = 0,
):
    """List GDPR self-service requests for audit. Admin-only."""
    await require_admin(request)

    query: dict = {}
    if status and status != "all":
        query["status"] = status
    if action and action != "all" and action in ACTIONS:
        query["action"] = action

    cursor = db.gdpr_requests.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    rows = await cursor.to_list(limit)
    total = await db.gdpr_requests.count_documents(query)

    # Summary buckets
    counts = {
        "total": await db.gdpr_requests.count_documents({}),
        "pending_verification": await db.gdpr_requests.count_documents({"status": "pending_verification"}),
        "completed": await db.gdpr_requests.count_documents({"status": "completed"}),
        "exports_completed": await db.gdpr_requests.count_documents({"status": "completed", "action": "export"}),
        "deletes_completed": await db.gdpr_requests.count_documents({"status": "completed", "action": "delete"}),
        "last_24h": await db.gdpr_requests.count_documents({
            "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()},
        }),
    }
    return {"requests": rows, "total": total, "counts": counts}


@router.get("/admin/audit-log")
async def admin_audit_log(request: Request, limit: int = 100):
    """Tail of gdpr_audit_log — permanent execution trail. Admin-only."""
    await require_admin(request)
    rows = await db.gdpr_audit_log.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    total = await db.gdpr_audit_log.count_documents({})
    return {"entries": rows, "total": total}


# ─────────────────────────────────────────────────────────────────────────
# Weekly compliance digest — used by scheduler + admin "send now" endpoint
# ─────────────────────────────────────────────────────────────────────────
async def build_weekly_digest(window_days: int = 7) -> dict:
    """Aggregate GDPR self-service activity for the last `window_days`."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=window_days)
    since_iso = since.isoformat()

    requests_in_window = await db.gdpr_requests.find(
        {"created_at": {"$gte": since_iso}}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)

    audit_in_window = await db.gdpr_audit_log.find(
        {"timestamp": {"$gte": since_iso}}, {"_id": 0}
    ).sort("timestamp", -1).to_list(500)

    total_requests = len(requests_in_window)
    export_requests = sum(1 for r in requests_in_window if r.get("action") == "export")
    delete_requests = sum(1 for r in requests_in_window if r.get("action") == "delete")
    completed = sum(1 for r in requests_in_window if r.get("status") == "completed")
    pending = sum(1 for r in requests_in_window if r.get("status") == "pending_verification")

    deleted_records = 0
    exported_records = 0
    for a in audit_in_window:
        counts = a.get("counts") or {}
        tot = sum(v for k, v in counts.items() if k != "total" and isinstance(v, int))
        if a.get("result") == "deleted":
            deleted_records += tot
        elif a.get("result") == "exported":
            exported_records += tot

    # Expired-pending = requests created >15min ago still in pending_verification
    stale_pending = [
        r for r in requests_in_window
        if r.get("status") == "pending_verification"
        and r.get("created_at", "") < (now - timedelta(minutes=16)).isoformat()
    ]

    return {
        "window_days": window_days,
        "window_start_utc": since_iso,
        "window_end_utc": now.isoformat(),
        "total_requests": total_requests,
        "export_requests": export_requests,
        "delete_requests": delete_requests,
        "completed": completed,
        "pending": pending,
        "unverified_abandoned": len(stale_pending),
        "exported_records": exported_records,
        "deleted_records": deleted_records,
        "recent_audit_entries": audit_in_window[:10],
    }


def _render_digest_html(digest: dict, brand: str = "RealAICoach") -> str:
    """DEPRECATED: kept for backward-compat. Use build_gdpr_weekly_digest_email (v7) via catalog."""
    (
        f'<tr><td style="padding:10px;background:#FEF3C7;color:#92400E;border-radius:6px;">'
        f'<strong>{digest["unverified_abandoned"]}</strong> request(s) expired without email-link verification in this window.</td></tr>'
        if digest["unverified_abandoned"] else ""
    )
    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:620px;margin:0 auto;color:#111;">
      <h2 style="color:#4F46E5;margin:0 0 6px;">GDPR Weekly Compliance Digest</h2>
      <p style="color:#6B7280;margin:0 0 22px;font-size:13px;">Window: last {digest['window_days']} days · {brand}</p>
    </div>
    """


async def send_weekly_digest(trigger: str = "cron") -> dict:
    """Compute + send this week's GDPR digest email via v7 catalog template."""
    digest = await build_weekly_digest()
    recipient = os.environ.get("GDPR_DIGEST_RECIPIENT", "compliance@realaicoach.app")
    dashboard_link = f"{_frontend_base()}/admin/gdpr-requests" if _frontend_base() else "/admin/gdpr-requests"
    try:
        await send_catalog_template(
            recipient_email=recipient,
            template_key="gdpr_weekly_digest",
            window_days=digest["window_days"],
            total_requests=digest["total_requests"],
            export_requests=digest["export_requests"],
            delete_requests=digest["delete_requests"],
            completed=digest["completed"],
            pending=digest["pending"],
            unverified_abandoned=digest["unverified_abandoned"],
            exported_records=digest["exported_records"],
            deleted_records=digest["deleted_records"],
            dashboard_link=dashboard_link,
        )
        sent_ok = True
    except Exception as exc:
        logger.error("gdpr weekly digest email failed: %s", exc)
        sent_ok = False

    await db.gdpr_digest_history.insert_one({
        "sent_at_utc": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient,
        "trigger": trigger,
        "sent_ok": sent_ok,
        "digest": digest,
    })

    # Log into the Compliance Digest Hub inbox (fail-safe).
    try:
        from routes.compliance_digest_hub import log_digest_entry
        summary = (
            f"Window {digest['window_days']}d · "
            f"{digest['total_requests']} request(s) "
            f"(export={digest['export_requests']}, delete={digest['delete_requests']}) · "
            f"completed={digest['completed']} · pending={digest['pending']}"
        )
        await log_digest_entry(
            kind="gdpr_retention_weekly",
            subject=f"GDPR Weekly Digest · {digest['total_requests']} request(s)",
            summary=summary,
            recipients=[recipient] if recipient else [],
            sent_ok=1 if sent_ok else 0,
            sent_failed=0 if sent_ok else 1,
            payload=digest,
            trigger=trigger,
        )
    except Exception as _e:
        logger.warning("gdpr weekly digest hub-log failed: %s", _e)

    return {"sent_ok": sent_ok, "recipient": recipient, "summary": digest}


@router.post("/admin/send-digest-now")
async def admin_send_digest_now(request: Request):
    """Admin-only: generate and email the weekly GDPR digest immediately."""
    await require_admin(request)
    return await send_weekly_digest(trigger="manual")


# ─────────────────────────────────────────────────────────────────────────
# Data Retention Policy
# ─────────────────────────────────────────────────────────────────────────
ALLOWED_RETENTION_DAYS = (30, 90, 180, 365)  # plus 0 = disabled (never purge)


class RetentionPolicyIn(BaseModel):
    retention_days: int  # 0 disables purging; otherwise must be in ALLOWED_RETENTION_DAYS


async def get_retention_policy() -> dict:
    """Fetch the current policy doc (or return defaults if unset)."""
    doc = await db.gdpr_settings.find_one({"_id": "retention_policy"}, {"_id": 0})
    if not doc:
        return {"retention_days": 0, "updated_at": None, "updated_by": None}
    return doc


@router.get("/admin/retention-policy")
async def admin_get_retention(request: Request):
    user = await require_admin(request)
    policy = await get_retention_policy()
    return {"policy": policy, "allowed_days": list(ALLOWED_RETENTION_DAYS), "updated_by_self": getattr(user, "email", None)}


@router.put("/admin/retention-policy")
async def admin_set_retention(payload: RetentionPolicyIn, request: Request):
    user = await require_admin(request)
    days = payload.retention_days
    if days != 0 and days not in ALLOWED_RETENTION_DAYS:
        raise HTTPException(status_code=400, detail=f"retention_days must be 0 or one of {ALLOWED_RETENTION_DAYS}")
    now = datetime.now(timezone.utc).isoformat()
    await db.gdpr_settings.update_one(
        {"_id": "retention_policy"},
        {"$set": {
            "retention_days": days,
            "updated_at": now,
            "updated_by": getattr(user, "email", "admin"),
        }},
        upsert=True,
    )
    return {"ok": True, "retention_days": days, "updated_at": now}


async def run_retention_purge(trigger: str = "cron") -> dict:
    """Hard-delete rows across the 3 PII collections older than the configured retention window.
    Records the run in `gdpr_retention_log` for the admin metrics view.
    """
    policy = await get_retention_policy()
    days = int(policy.get("retention_days") or 0)
    now = datetime.now(timezone.utc)
    run_entry: dict = {
        "run_at_utc": now.isoformat(),
        "trigger": trigger,
        "retention_days": days,
        "purged": {},
        "status": "skipped" if days <= 0 else "ok",
    }

    if days <= 0:
        await db.gdpr_retention_log.insert_one(dict(run_entry))
        return run_entry

    cutoff_iso = (now - timedelta(days=days)).isoformat()
    for coll in _GDPR_COLLECTIONS:
        try:
            res = await db[coll].delete_many({"created_at": {"$lt": cutoff_iso}})
            run_entry["purged"][coll] = res.deleted_count
        except Exception as exc:
            logger.error("retention purge failed for %s: %s", coll, exc)
            run_entry["purged"][coll] = -1
            run_entry["status"] = "partial"

    run_entry["purged"]["total"] = sum(
        v for v in run_entry["purged"].values() if isinstance(v, int) and v >= 0
    )
    await db.gdpr_retention_log.insert_one(dict(run_entry))
    return run_entry


@router.post("/admin/retention/run-now")
async def admin_run_retention_now(request: Request):
    """Admin-only: trigger an immediate retention purge (same logic as the nightly cron)."""
    await require_admin(request)
    return await run_retention_purge(trigger="manual")


@router.get("/admin/retention/metrics")
async def admin_retention_metrics(request: Request, days_back: int = 30):
    """Last N days of purge-log entries + aggregate totals for the dashboard KPI."""
    await require_admin(request)
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
    logs = await db.gdpr_retention_log.find(
        {"run_at_utc": {"$gte": since}}, {"_id": 0}
    ).sort("run_at_utc", -1).to_list(200)
    total_purged = 0
    runs_completed = 0
    for e in logs:
        if e.get("status") == "ok":
            runs_completed += 1
            total_purged += e.get("purged", {}).get("total", 0)
    return {
        "window_days": days_back,
        "runs": logs,
        "runs_completed": runs_completed,
        "total_purged": total_purged,
    }
