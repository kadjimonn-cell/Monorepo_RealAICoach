"""Admin Data Management API — CRUD for dashboard seed data collections with audit logging."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
import uuid
import io
import csv
import json

from routes.db import db, require_admin
from utils.pdf_v15_filename import build_pdf_v15_filename

router = APIRouter(prefix="/admin/data", tags=["Admin Data Management"])


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise RuntimeError(f"pdf-v15-enforcement-failed:{context}:{mode}")
    return themed


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _audit(user, action: str, collection: str, target_id: str, changes: dict):
    """Record an audit log entry for every data management write operation."""
    await db.data_audit_log.insert_one(
        {
            "audit_id": f"dlog_{uuid.uuid4().hex[:12]}",
            "admin_email": user.email,
            "admin_name": user.name,
            "admin_id": user.user_id,
            "action": action,
            "collection": collection,
            "target_id": target_id,
            "changes": changes,
            "created_at": _now(),
        }
    )


# ── Audit Log Endpoint ───────────────────────────────────────


@router.get("/audit-log")
async def get_audit_log(request: Request):
    await require_admin(request)
    limit = int(request.query_params.get("limit", "50"))
    skip = int(request.query_params.get("skip", "0"))
    limit = min(limit, 200)

    total = await db.data_audit_log.count_documents({})
    logs = []
    async for doc in db.data_audit_log.find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit):
        logs.append(doc)
    return {"logs": logs, "total": total, "limit": limit, "skip": skip}


@router.get("/audit-log/export/csv")
async def export_audit_csv(request: Request):
    await require_admin(request)
    logs = []
    async for doc in db.data_audit_log.find({}, {"_id": 0}).sort("created_at", -1):
        logs.append(doc)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Timestamp", "Admin Email", "Admin Name", "Action", "Collection", "Target ID", "Changes"])
    for log_entry in logs:
        writer.writerow(
            [
                log_entry.get("created_at", ""),
                log_entry.get("admin_email", ""),
                log_entry.get("admin_name", ""),
                log_entry.get("action", ""),
                log_entry.get("collection", ""),
                log_entry.get("target_id", ""),
                json.dumps(log_entry.get("changes", {})),
            ]
        )
    buf.seek(0)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit_log_{ts}.csv"'},
    )


@router.get("/audit-log/export/pdf")
async def export_audit_pdf(request: Request):
    await require_admin(request)
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    logs = []
    async for doc in db.data_audit_log.find({}, {"_id": 0}).sort("created_at", -1):
        logs.append(doc)

    from fpdf import FPDF

    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Data Management Audit Log", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0,
        6,
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  |  Total entries: {len(logs)}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    # Table header
    col_w = [42, 55, 35, 28, 42, 35, 40]
    headers = ["Timestamp", "Admin Email", "Admin Name", "Action", "Collection", "Target ID", "Changes"]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(40, 50, 80)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True)
    pdf.ln()

    # Table rows
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(30, 30, 30)
    for idx, log_entry in enumerate(logs):
        fill = idx % 2 == 0
        if fill:
            pdf.set_fill_color(240, 242, 248)
        ts = log_entry.get("created_at", "")[:19].replace("T", " ")
        changes_str = json.dumps(log_entry.get("changes", {}))
        if len(changes_str) > 30:
            changes_str = changes_str[:27] + "..."
        vals = [
            ts,
            log_entry.get("admin_email", ""),
            log_entry.get("admin_name", ""),
            log_entry.get("action", ""),
            log_entry.get("collection", ""),
            log_entry.get("target_id", ""),
            changes_str,
        ]
        for i, v in enumerate(vals):
            pdf.cell(col_w[i], 7, str(v)[:25], border=1, fill=fill)
        pdf.ln()

    raw_pdf = pdf.output(dest="S")
    pdf_bytes = raw_pdf if isinstance(raw_pdf, (bytes, bytearray)) else str(raw_pdf).encode("latin1", errors="ignore")
    pdf_bytes = compose_pdf_v15_helper_layout(
        pdf_bytes,
        title="Data Audit Log",
        subtitle="Administrative data governance export",
        right_primary=f"Entries: {len(logs)}",
        right_secondary=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        badge_text="ADMIN DATA MANAGEMENT",
        badge_status="INFO",
        footer_text="RealAICoach Data Management • Enterprise profile",
        summary_title="Audit Summary",
        summary_rows=[
            ("Actions", str(len(logs))),
            ("Critical", str(sum(1 for log_entry in logs if str(log_entry.get('action', '')).lower() in {'delete','bulk_update','purge','revoke','reset'}))),
            ("Collections", str(len({str(log_entry.get('collection', '')) for log_entry in logs}))),
        ],
        callout_title="Governance Signal",
        callout_subtitle="Data operation transparency",
        callout_detail="This export captures administrative changes and supports weekly governance review.",
        callout_status="INFO",
    )
    buf = io.BytesIO(_enforce_pdf_v15_enterprise(pdf_bytes, "admin_audit_export_pdf"))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{build_pdf_v15_filename("audit-log", ts)}"'},
    )


# ── Platform Stats (Home Dashboard) ──────────────────────────


@router.get("/platform-stats")
async def get_platform_stats(request: Request):
    await require_admin(request)
    doc = await db.platform_stats.find_one({"key": "global"}, {"_id": 0})
    return doc or {}


@router.put("/platform-stats")
async def update_platform_stats(request: Request):
    user = await require_admin(request)
    body = await request.json()
    allowed = ["active_users", "ai_sessions_today", "performance_boost", "global_coaches", "ai_status"]
    updates = {k: body[k] for k in allowed if k in body}
    updates["updated_at"] = _now()
    await db.platform_stats.update_one({"key": "global"}, {"$set": updates}, upsert=True)
    await _audit(user, "update", "platform_stats", "global", {k: body[k] for k in allowed if k in body})
    doc = await db.platform_stats.find_one({"key": "global"}, {"_id": 0})
    return {"success": True, "data": doc}


# ── Platform Metrics (Enterprise Dashboard KPIs) ─────────────


@router.get("/platform-metrics")
async def get_platform_metrics(request: Request):
    await require_admin(request)
    doc = await db.platform_metrics.find_one({"key": "dashboard"}, {"_id": 0})
    return doc or {}


@router.put("/platform-metrics")
async def update_platform_metrics(request: Request):
    user = await require_admin(request)
    body = await request.json()
    allowed = [
        "api_requests_24h",
        "avg_response_ms",
        "error_rate_pct",
        "uptime_30d_pct",
        "user_growth_monthly",
        "mrr_cents",
        "arr_cents",
        "regions",
        "peak_hour",
        "avg_session_duration_min",
        "bounce_rate_pct",
    ]
    updates = {k: body[k] for k in allowed if k in body}
    updates["updated_at"] = _now()
    await db.platform_metrics.update_one({"key": "dashboard"}, {"$set": updates}, upsert=True)
    await _audit(user, "update", "platform_metrics", "dashboard", {k: body[k] for k in allowed if k in body})
    doc = await db.platform_metrics.find_one({"key": "dashboard"}, {"_id": 0})
    return {"success": True, "data": doc}


# ── Service Health ────────────────────────────────────────────


@router.get("/service-health")
async def get_service_health(request: Request):
    await require_admin(request)
    services = []
    async for s in db.service_health.find({}, {"_id": 0}):
        services.append(s)
    return {"services": services}


@router.post("/service-health")
async def create_service(request: Request):
    user = await require_admin(request)
    body = await request.json()
    doc = {
        "service_id": body.get("service_id", "").strip(),
        "name": body.get("name", "").strip(),
        "status": body.get("status", "healthy"),
        "uptime_pct": body.get("uptime_pct", 99.9),
        "latency_ms": body.get("latency_ms", 10),
        "updated_at": _now(),
    }
    if not doc["service_id"] or not doc["name"]:
        return {"success": False, "error": "service_id and name required"}
    await db.service_health.update_one({"service_id": doc["service_id"]}, {"$setOnInsert": doc}, upsert=True)
    await _audit(user, "create", "service_health", doc["service_id"], {"name": doc["name"], "status": doc["status"]})
    return {"success": True, "service": doc}


@router.put("/service-health/{service_id}")
async def update_service(service_id: str, request: Request):
    user = await require_admin(request)
    body = await request.json()
    allowed = ["name", "status", "uptime_pct", "latency_ms"]
    updates = {k: body[k] for k in allowed if k in body}
    updates["updated_at"] = _now()
    await db.service_health.update_one({"service_id": service_id}, {"$set": updates})
    await _audit(user, "update", "service_health", service_id, {k: body[k] for k in allowed if k in body})
    doc = await db.service_health.find_one({"service_id": service_id}, {"_id": 0})
    return {"success": True, "service": doc}


@router.delete("/service-health/{service_id}")
async def delete_service(service_id: str, request: Request):
    user = await require_admin(request)
    result = await db.service_health.delete_one({"service_id": service_id})
    if result.deleted_count > 0:
        await _audit(user, "delete", "service_health", service_id, {})
    return {"success": result.deleted_count > 0}


# ── Feature Usage Stats (Enterprise Features) ────────────────


@router.get("/feature-usage")
async def get_feature_usage(request: Request):
    await require_admin(request)
    features = []
    async for f in db.feature_usage_stats.find({}, {"_id": 0}).sort("sessions", -1):
        features.append(f)
    return {"features": features}


@router.post("/feature-usage")
async def create_feature_usage(request: Request):
    user = await require_admin(request)
    body = await request.json()
    doc = {
        "feature_id": body.get("feature_id", "").strip(),
        "name": body.get("name", "").strip(),
        "sessions": body.get("sessions", 0),
        "unique_users": body.get("unique_users", 0),
        "avg_duration": body.get("avg_duration", "0m"),
        "satisfaction": body.get("satisfaction", 0),
        "category": body.get("category", ""),
        "monthly_trend": body.get("monthly_trend", []),
        "updated_at": _now(),
    }
    if not doc["feature_id"] or not doc["name"]:
        return {"success": False, "error": "feature_id and name required"}
    await db.feature_usage_stats.update_one({"feature_id": doc["feature_id"]}, {"$setOnInsert": doc}, upsert=True)
    await _audit(user, "create", "feature_usage_stats", doc["feature_id"], {"name": doc["name"]})
    return {"success": True, "feature": doc}


@router.put("/feature-usage/{feature_id}")
async def update_feature_usage(feature_id: str, request: Request):
    user = await require_admin(request)
    body = await request.json()
    allowed = ["name", "sessions", "unique_users", "avg_duration", "satisfaction", "category", "monthly_trend"]
    updates = {k: body[k] for k in allowed if k in body}
    updates["updated_at"] = _now()
    await db.feature_usage_stats.update_one({"feature_id": feature_id}, {"$set": updates})
    await _audit(user, "update", "feature_usage_stats", feature_id, {k: body[k] for k in allowed if k in body})
    doc = await db.feature_usage_stats.find_one({"feature_id": feature_id}, {"_id": 0})
    return {"success": True, "feature": doc}


@router.delete("/feature-usage/{feature_id}")
async def delete_feature_usage(feature_id: str, request: Request):
    user = await require_admin(request)
    result = await db.feature_usage_stats.delete_one({"feature_id": feature_id})
    if result.deleted_count > 0:
        await _audit(user, "delete", "feature_usage_stats", feature_id, {})
    return {"success": result.deleted_count > 0}


# ── Error Breakdown ───────────────────────────────────────────


@router.get("/error-breakdown")
async def get_error_breakdown(request: Request):
    await require_admin(request)
    errors = []
    async for e in db.error_breakdown.find({}, {"_id": 0}):
        errors.append(e)
    return {"errors": errors}


@router.put("/error-breakdown")
async def update_error_breakdown(request: Request):
    """Bulk update error breakdown — replaces all entries."""
    user = await require_admin(request)
    body = await request.json()
    entries = body.get("errors", [])
    if not entries:
        return {"success": False, "error": "No entries provided"}

    await db.error_breakdown.delete_many({})
    now = _now()
    for e in entries:
        e["updated_at"] = now
        await db.error_breakdown.insert_one(e)

    await _audit(user, "bulk_update", "error_breakdown", "all", {"count": len(entries)})

    errors = []
    async for e in db.error_breakdown.find({}, {"_id": 0}):
        errors.append(e)
    return {"success": True, "errors": errors}


# ── Summary / All Data ────────────────────────────────────────


@router.get("/summary")
async def get_data_summary(request: Request):
    await require_admin(request)
    ps = await db.platform_stats.count_documents({})
    pm = await db.platform_metrics.count_documents({})
    sh = await db.service_health.count_documents({})
    fu = await db.feature_usage_stats.count_documents({})
    eb = await db.error_breakdown.count_documents({})
    fg = await db.feature_gallery_metrics.count_documents({})
    al = await db.data_audit_log.count_documents({})
    return {
        "collections": {
            "platform_stats": ps,
            "platform_metrics": pm,
            "service_health": sh,
            "feature_usage_stats": fu,
            "error_breakdown": eb,
            "feature_gallery_metrics": fg,
            "audit_log": al,
        },
        "generated_at": _now(),
    }


# ── Scheduled Export Config ───────────────────────────────────

DEFAULT_SCHEDULE = {
    "key": "audit_export_schedule",
    "enabled": False,
    "frequency": "weekly",  # weekly | daily
    "day_of_week": "mon",  # mon-sun (for weekly)
    "hour": 8,
    "minute": 0,
    "recipients": [],  # admin emails
    "last_run": None,
    "last_run_status": None,
    "last_run_entries": 0,
}


@router.get("/audit-log/schedule")
async def get_schedule(request: Request):
    await require_admin(request)
    doc = await db.audit_export_schedule.find_one({"key": "audit_export_schedule"}, {"_id": 0})
    if not doc:
        return DEFAULT_SCHEDULE
    return doc


@router.put("/audit-log/schedule")
async def update_schedule(request: Request):
    user = await require_admin(request)
    body = await request.json()

    allowed = ["enabled", "frequency", "day_of_week", "hour", "minute", "recipients"]
    updates = {k: body[k] for k in allowed if k in body}

    # Validate
    if "frequency" in updates and updates["frequency"] not in ("weekly", "daily"):
        return {"success": False, "error": "frequency must be 'weekly' or 'daily'"}
    if "day_of_week" in updates and updates["day_of_week"] not in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        return {"success": False, "error": "Invalid day_of_week"}
    if "hour" in updates:
        updates["hour"] = max(0, min(23, int(updates["hour"])))
    if "minute" in updates:
        updates["minute"] = max(0, min(59, int(updates["minute"])))
    if "recipients" in updates and not isinstance(updates["recipients"], list):
        return {"success": False, "error": "recipients must be an array of emails"}

    updates["updated_at"] = _now()
    await db.audit_export_schedule.update_one(
        {"key": "audit_export_schedule"},
        {"$set": updates, "$setOnInsert": {"key": "audit_export_schedule"}},
        upsert=True,
    )
    await _audit(user, "update", "audit_export_schedule", "config", updates)

    doc = await db.audit_export_schedule.find_one({"key": "audit_export_schedule"}, {"_id": 0})
    return {"success": True, "schedule": doc}


@router.post("/audit-log/trigger-export")
async def trigger_export_now(request: Request):
    """Manually trigger the scheduled audit export immediately."""
    await require_admin(request)
    result = await run_scheduled_audit_export()
    return result


async def run_scheduled_audit_export():
    """Execute the scheduled audit export: generate CSV+PDF and email to recipients."""
    from utils.email_service import is_email_configured
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout
    import base64

    config = await db.audit_export_schedule.find_one({"key": "audit_export_schedule"}, {"_id": 0})
    if not config:
        return {"success": False, "reason": "no_config"}

    recipients = config.get("recipients", [])
    if not recipients:
        await db.audit_export_schedule.update_one(
            {"key": "audit_export_schedule"},
            {"$set": {"last_run": _now(), "last_run_status": "skipped_no_recipients", "last_run_entries": 0}},
        )
        return {"success": False, "reason": "no_recipients"}

    if not is_email_configured():
        await db.audit_export_schedule.update_one(
            {"key": "audit_export_schedule"},
            {"$set": {"last_run": _now(), "last_run_status": "skipped_email_not_configured", "last_run_entries": 0}},
        )
        return {"success": False, "reason": "email_not_configured"}

    # Fetch last 7 days of audit logs
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    logs = []
    async for doc in db.data_audit_log.find({"created_at": {"$gte": cutoff}}, {"_id": 0}).sort("created_at", -1):
        logs.append(doc)

    if not logs:
        await db.audit_export_schedule.update_one(
            {"key": "audit_export_schedule"},
            {"$set": {"last_run": _now(), "last_run_status": "success_no_entries", "last_run_entries": 0}},
        )
        return {"success": True, "entries": 0, "reason": "no_entries_in_period"}

    # Generate CSV
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["Timestamp", "Admin Email", "Admin Name", "Action", "Collection", "Target ID", "Changes"])
    for log_entry in logs:
        writer.writerow(
            [
                log_entry.get("created_at", ""),
                log_entry.get("admin_email", ""),
                log_entry.get("admin_name", ""),
                log_entry.get("action", ""),
                log_entry.get("collection", ""),
                log_entry.get("target_id", ""),
                json.dumps(log_entry.get("changes", {})),
            ]
        )
    csv_bytes = csv_buf.getvalue().encode("utf-8")

    # Generate PDF
    from fpdf import FPDF

    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Weekly Audit Log Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0,
        6,
        f"Period: Last 7 days | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Entries: {len(logs)}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    col_w = [42, 55, 35, 28, 42, 35, 40]
    headers = ["Timestamp", "Admin Email", "Admin Name", "Action", "Collection", "Target ID", "Changes"]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(40, 50, 80)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(30, 30, 30)
    for idx, log_entry in enumerate(logs):
        fill = idx % 2 == 0
        if fill:
            pdf.set_fill_color(240, 242, 248)
        ts = log_entry.get("created_at", "")[:19].replace("T", " ")
        changes_str = json.dumps(log_entry.get("changes", {}))
        if len(changes_str) > 30:
            changes_str = changes_str[:27] + "..."
        vals = [
            ts,
            log_entry.get("admin_email", ""),
            log_entry.get("admin_name", ""),
            log_entry.get("action", ""),
            log_entry.get("collection", ""),
            log_entry.get("target_id", ""),
            changes_str,
        ]
        for i, v in enumerate(vals):
            pdf.cell(col_w[i], 7, str(v)[:25], border=1, fill=fill)
        pdf.ln()

    raw_pdf = pdf.output(dest="S")
    pdf_bytes = raw_pdf if isinstance(raw_pdf, (bytes, bytearray)) else str(raw_pdf).encode("latin1", errors="ignore")
    pdf_bytes = compose_pdf_v15_helper_layout(
        pdf_bytes,
        title="Weekly Audit Log",
        subtitle="Automated governance dispatch artifact",
        right_primary=f"Entries: {len(logs)}",
        right_secondary=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        badge_text="WEEKLY AUDIT GOVERNANCE",
        badge_status="INFO",
        footer_text="RealAICoach Data Governance • Enterprise profile",
        summary_title="Weekly Snapshot",
        summary_rows=[
            ("Rows", str(len(logs))),
            ("Recipients", str(len(recipients))),
            ("Window", "7 days"),
        ],
        callout_title="Dispatch Context",
        callout_subtitle="Audit accountability",
        callout_detail="Weekly export includes CSV and PDF artifacts for leadership oversight.",
        callout_status="INFO",
    )
    pdf_bytes = _enforce_pdf_v15_enterprise(pdf_bytes, "weekly_audit_log_attachment")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    period_str = f"{datetime.fromisoformat(cutoff.replace('Z', '+00:00')).strftime('%b %d, %Y')} – {datetime.now(timezone.utc).strftime('%b %d, %Y')}"
    action_counts: dict[str, int] = {}
    critical_count = 0
    critical_actions = {"delete", "bulk_update", "purge", "revoke", "reset"}
    for log in logs:
        action = str(log.get("action") or "unknown").strip().lower()
        action_counts[action] = action_counts.get(action, 0) + 1
        if action in critical_actions:
            critical_count += 1
    top_actions = sorted(action_counts.items(), key=lambda item: item[1], reverse=True)[:3]
    top_actions_str = ", ".join(
        f"{(name or 'unknown').replace('_', ' ').title()} ({count})"
        for name, count in top_actions
    ) or "No dominant actions"

    attachments = [
        {
            "filename": f"audit_log_{ts}.csv",
            "content": base64.b64encode(csv_bytes).decode("utf-8"),
            "content_type": "text/csv",
        },
        {
            "filename": build_pdf_v15_filename("audit-log", ts),
            "content": base64.b64encode(pdf_bytes).decode("utf-8"),
            "content_type": "application/pdf",
        },
    ]

    from utils.email_service import render_email_header_panel

    header_html = render_email_header_panel(
        title="Weekly Audit Log Report",
        subtitle="Scheduled audit export covering the last 7 days.",
        variant="report",
        accent="#1D4ED8",
        meta_label="Generated",
        meta_value=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="border-radius:20px;overflow:hidden;margin-bottom:18px;">{header_html}</div>
        <div class="em-force-light-card" style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;padding:16px;">
            <p class="em-force-muted-text" style="color:#475569;">Your scheduled audit export is attached. This report covers the last 7 days.</p>
            <table class="em-force-light-card" style="width:100%;border-collapse:collapse;margin:16px 0;background:#FFFFFF;">
                <tr><td class="em-force-muted-text" style="padding:8px;border-bottom:1px solid #E2E8F0;color:#64748B;">Period</td><td class="em-force-dark-text" style="padding:8px;border-bottom:1px solid #E2E8F0;font-weight:600;color:#0F172A;">Last 7 days</td></tr>
                <tr><td class="em-force-muted-text" style="padding:8px;border-bottom:1px solid #E2E8F0;color:#64748B;">Total entries</td><td class="em-force-dark-text" style="padding:8px;border-bottom:1px solid #E2E8F0;font-weight:600;color:#0F172A;">{len(logs)}</td></tr>
                <tr><td class="em-force-muted-text" style="padding:8px;border-bottom:1px solid #E2E8F0;color:#64748B;">Generated</td><td class="em-force-dark-text" style="padding:8px;border-bottom:1px solid #E2E8F0;font-weight:600;color:#0F172A;">{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</td></tr>
            </table>
            <p class="em-force-muted-text" style="color:#94A3B8;font-size:12px;">Attached: CSV and PDF reports</p>
        </div>
    </div>
    """

    sent_count = 0
    for email in recipients:
        from utils.email_service import send_catalog_template
        result = await send_catalog_template(
            recipient_email=email,
            template_key="weekly_audit_log",
            period=period_str,
            log_count=len(logs),
            critical_events=critical_count,
            top_actions=top_actions_str,
            attachments=attachments,
        )
        if result.get("success"):
            sent_count += 1

    await db.audit_export_schedule.update_one(
        {"key": "audit_export_schedule"},
        {
            "$set": {
                "last_run": _now(),
                "last_run_status": f"sent_to_{sent_count}_of_{len(recipients)}",
                "last_run_entries": len(logs),
            }
        },
    )

    return {"success": True, "entries": len(logs), "sent_to": sent_count, "total_recipients": len(recipients)}
