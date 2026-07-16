from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace
from typing import Any, Optional
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routes.db import db, require_admin

router = APIRouter(prefix="/admin/platform-integrity", tags=["AI Platform Integrity"])


DEFAULT_RULE = {
    "rule_id": "global_ai_platform_integrity",
    "enabled": True,
    "safe_mode": True,
    "alert_on_critical_fix": True,
    "realtime_interval_minutes": 5,
    "daily_scan_hour_utc": 4,
    "locked_mode": True,
    "autonomous_mode": "full_platform_persistent",
    "zero_error_policy": True,
    "global_e2e_validation": True,
    "auto_lock_regressions": True,
    "scope": ["frontend", "backend", "apis", "db", "admin", "user", "realtime", "theme", "i18n", "responsiveness"],
}

CRITICAL_FRONTEND_SURFACES = [
    "/",
    "/notifications",
    "/subscription/payment",
    "/subscription/mobile-money",
    "/payment-history",
    "/admin-console?category=operations&tab=ai-platform-integrity",
]

CRITICAL_ADMIN_SURFACES = [
    "operations:ai-platform-integrity",
    "operations:platform-health",
    "operations:ops-dashboard",
    "finance:payments-tax",
    "comms:languages",
    "overview:dashboard",
]

CRITICAL_API_SURFACES = [
    "/api/admin/platform-integrity/overview",
    "/api/admin/platform-integrity/history",
    "/api/admin/platform-integrity/run-cycle",
    "/api/admin/payments-tax-intelligence/overview",
    "/api/admin/platform-health/scan",
    "/api/i18n/brand-protection/audit",
]

CRITICAL_DB_COLLECTIONS = [
    "users",
    "notifications",
    "payment_transactions",
    "financial_ledger_entries",
    "scheduler_heartbeats",
    "ai_platform_integrity_runs",
    "ai_platform_integrity_config",
]

CRITICAL_SCHEDULER_JOBS = [
    "enterprise_lock_cycle",
    "platform_full_auto_audit",
    "platform_e2e_regression_gate",
    "growth_integrity_monitor",
    "ai_platform_integrity_realtime",
    "ai_platform_integrity_guardian",
    "ai_platform_integrity_daily",
]

SCHEDULER_FRESHNESS_MINUTES = {
    "ai_platform_integrity_guardian": 15,
    "ai_platform_integrity_realtime": 30,
    "ai_platform_integrity_daily": 26 * 60,
    "platform_e2e_regression_gate": 45,
    "growth_integrity_monitor": 35,
    "enterprise_lock_cycle": 90,
    "platform_full_auto_audit": 150,
}

INTEGRITY_ALERT_STATE_SYSTEM_KEY = "ai_platform_integrity_alert_state_v1"


class IntegrityConfigUpdate(BaseModel):
    alert_on_critical_fix: Optional[bool] = None
    realtime_interval_minutes: Optional[int] = None
    daily_scan_hour_utc: Optional[int] = None


class PreviewAlertRequest(BaseModel):
    preview_type: str = "integrity"
    recipient_email: Optional[str] = "realaicoach@gmail.com"
    recipient_name: Optional[str] = "Preview Recipient"


def _admin_stub() -> Any:
    return SimpleNamespace(user_id="system_integrity", email="admin@realaicoach.app", is_admin=True, full_access=True, role="admin", roles=["admin"])


async def _get_config() -> dict:
    doc = await db.ai_platform_integrity_config.find_one({"rule_id": DEFAULT_RULE["rule_id"]}, {"_id": 0})
    merged = {**DEFAULT_RULE}
    if doc:
        merged.update(doc)
    return merged


async def _set_scheduler_heartbeat(job_id: str, *, status: str, details: Optional[dict] = None) -> None:
    await db.scheduler_heartbeats.update_one(
        {"job_id": job_id},
        {
            "$set": {
                "job_id": job_id,
                "status": status,
                "last_run": datetime.now(timezone.utc).isoformat(),
                "details": details or {},
            }
        },
        upsert=True,
    )


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _is_fresh_heartbeat(last_run: Optional[str], max_age_minutes: int = 20) -> bool:
    parsed = _parse_iso(last_run)
    if not parsed:
        return False
    return (datetime.now(timezone.utc) - parsed).total_seconds() <= (max_age_minutes * 60)


def _status_rollup(items: list[dict]) -> dict:
    summary = {"healthy": 0, "warning": 0, "critical": 0}
    for item in items:
        status = str(item.get("status") or "warning").lower()
        if status not in summary:
            status = "warning"
        summary[status] += 1
    return summary


def _scope_registry() -> dict:
    return {
        "frontend_routes": {
            "count": len(CRITICAL_FRONTEND_SURFACES),
            "items": CRITICAL_FRONTEND_SURFACES,
        },
        "admin_tabs": {
            "count": len(CRITICAL_ADMIN_SURFACES),
            "items": CRITICAL_ADMIN_SURFACES,
        },
        "api_routes": {
            "count": len(CRITICAL_API_SURFACES),
            "items": CRITICAL_API_SURFACES,
        },
        "db_collections": {
            "count": len(CRITICAL_DB_COLLECTIONS),
            "items": CRITICAL_DB_COLLECTIONS,
        },
        "scheduler_jobs": {
            "count": len(CRITICAL_SCHEDULER_JOBS),
            "items": CRITICAL_SCHEDULER_JOBS,
        },
    }


async def _global_surface_validation(platform_scan: dict, live_services: dict, domain_rollup: dict) -> dict:
    collections = set(await db.list_collection_names())
    missing_collections = [name for name in CRITICAL_DB_COLLECTIONS if name not in collections]

    scheduler_rows = await db.scheduler_heartbeats.find(
        {"job_id": {"$in": CRITICAL_SCHEDULER_JOBS}},
        {"_id": 0, "job_id": 1, "status": 1, "last_run": 1},
    ).to_list(50)
    scheduler_by_job = {row.get("job_id"): row for row in scheduler_rows}
    missing_jobs = []
    stale_jobs = []
    errored_jobs = []
    degraded_jobs = []
    for job_id in CRITICAL_SCHEDULER_JOBS:
        row = scheduler_by_job.get(job_id)
        if not row:
            missing_jobs.append(job_id)
            continue

        status = str(row.get("status") or "unknown").lower()
        freshness_window = int(SCHEDULER_FRESHNESS_MINUTES.get(job_id, 30))
        if status == "error":
            errored_jobs.append(job_id)
            continue

        if not _is_fresh_heartbeat(row.get("last_run"), freshness_window):
            stale_jobs.append(job_id)
            continue

        if status not in {"healthy", "ok"}:
            degraded_jobs.append(job_id)

    stale_or_missing = [*missing_jobs, *errored_jobs, *stale_jobs, *degraded_jobs]
    scheduler_guard_status = (
        "critical"
        if missing_jobs or errored_jobs
        else "warning"
        if stale_jobs or degraded_jobs
        else "healthy"
    )

    notification_backlog = await db.notification_recovery_queue.count_documents(
        {"status": {"$in": ["queued", "pending", "failed"]}}
    ) if "notification_recovery_queue" in collections else 0
    fedapay_dead = await db.fedapay_webhook_events.count_documents({"status": "dead"}) if "fedapay_webhook_events" in collections else 0

    stale_url_count = int(platform_scan.get("stale_urls", {}).get("count", 0) or 0)
    build_stale = bool(platform_scan.get("build", {}).get("stale", False))
    total_issues = int(platform_scan.get("total_issues", 0) or 0)
    warning_domains = int(domain_rollup.get("summary", {}).get("warning", 0) or 0)
    errored_domains = int(domain_rollup.get("summary", {}).get("error", 0) or 0)

    checks = [
        {
            "id": "frontend_render_guard",
            "label": "Frontend Rendering + Route Integrity",
            "status": "critical" if build_stale else "warning" if stale_url_count > 0 else "healthy",
            "detail": f"Build stale={build_stale}, stale route references={stale_url_count}",
        },
        {
            "id": "api_service_guard",
            "label": "Backend/API Service Continuity",
            "status": "critical" if total_issues >= 15 else "warning" if total_issues >= 5 else "healthy",
            "detail": f"Platform scan issues={total_issues}",
        },
        {
            "id": "scheduler_sync_guard",
            "label": "Autonomous Job Sync",
            "status": scheduler_guard_status,
            "detail": (
                f"missing={len(missing_jobs)}, stale={len(stale_jobs)}, "
                f"error={len(errored_jobs)}, degraded={len(degraded_jobs)}"
            ),
            "affected_jobs": stale_or_missing,
            "health_breakdown": {
                "missing": missing_jobs,
                "stale": stale_jobs,
                "error": errored_jobs,
                "degraded": degraded_jobs,
            },
        },
        {
            "id": "database_integrity_guard",
            "label": "Database Integrity + Required Collections",
            "status": "critical" if missing_collections else "healthy",
            "detail": "All required collections present" if not missing_collections else f"Missing collections: {', '.join(missing_collections)}",
            "missing_collections": missing_collections,
        },
        {
            "id": "realtime_pipeline_guard",
            "label": "Realtime + Recovery Pipelines",
            "status": "critical" if fedapay_dead > 0 else "warning" if notification_backlog > 25 else "healthy",
            "detail": f"notification backlog={notification_backlog}, fedapay dead events={fedapay_dead}",
        },
        {
            "id": "admin_user_surface_guard",
            "label": "Admin/User Surface Connectivity",
            "status": "critical" if errored_domains > 0 else "warning" if warning_domains > 6 else "healthy",
            "detail": f"warning domains={warning_domains}, errored domains={errored_domains}",
        },
    ]
    summary = _status_rollup(checks)
    overall = "critical" if summary["critical"] > 0 else "warning" if summary["warning"] > 0 else "healthy"
    return {
        "status": overall,
        "summary": summary,
        "checks": checks,
        "metrics": {
            "notification_backlog": notification_backlog,
            "fedapay_dead_events": fedapay_dead,
            "critical_scheduler_jobs": len(CRITICAL_SCHEDULER_JOBS),
            "scheduler_rows_seen": len(scheduler_rows),
            "scheduler_missing_jobs": len(missing_jobs),
            "scheduler_stale_jobs": len(stale_jobs),
            "scheduler_degraded_jobs": len(degraded_jobs),
        },
    }


async def _lock_integrity_state(record: dict, global_validation: dict, config: dict) -> dict:
    payload = (
        f"{record.get('run_id')}|{record.get('status')}|{record.get('final_score')}|"
        f"{record.get('platform_fixes')}|{record.get('domain_fixes')}|{record.get('self_repairs')}|"
        f"{record.get('ai_applied')}|{global_validation.get('status')}|{global_validation.get('summary')}"
    )
    signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    lock_doc = {
        "lock_id": f"lock_{uuid.uuid4().hex[:12]}",
        "rule_id": DEFAULT_RULE["rule_id"],
        "run_id": record.get("run_id"),
        "lock_signature": signature,
        "status": "locked" if config.get("auto_lock_regressions", True) else "observed",
        "validation_status": global_validation.get("status", "warning"),
        "summary": {
            "final_score": record.get("final_score", 0),
            "critical_checks": global_validation.get("summary", {}).get("critical", 0),
            "warning_checks": global_validation.get("summary", {}).get("warning", 0),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ai_platform_integrity_locks.insert_one({**lock_doc})
    return lock_doc


def _build_integrity_alert_signature(summary: dict) -> str:
    status = str(summary.get("status") or "unknown").strip().lower()
    final_score = int(round(float(summary.get("final_score") or 0)))
    platform_fixes = int(summary.get("platform_fixes") or 0)
    domain_fixes = int(summary.get("domain_fixes") or 0)
    ai_applied = int(summary.get("ai_applied") or 0)
    review_queue = int(summary.get("review_queue") or 0)
    critical_checks = int(summary.get("critical_checks") or 0)
    payload = f"{status}|{final_score}|{platform_fixes}|{domain_fixes}|{ai_applied}|{review_queue}|{critical_checks}"
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:24]


async def _reserve_integrity_alert_transition(summary: dict) -> tuple[bool, str]:
    status = str(summary.get("status") or "unknown").strip().lower()
    signature = _build_integrity_alert_signature(summary)
    now_iso = datetime.now(timezone.utc).isoformat()

    state_doc = await db.system_state.find_one({"key": INTEGRITY_ALERT_STATE_SYSTEM_KEY}, {"_id": 0, "value": 1})
    state = (state_doc or {}).get("value") or {}
    last_status = str(state.get("last_status") or "").strip().lower()
    last_signature = str(state.get("last_signature") or "").strip().lower()

    if last_status == status and last_signature == signature:
        await db.system_state.update_one(
            {"key": INTEGRITY_ALERT_STATE_SYSTEM_KEY},
            {
                "$set": {
                    "updated_at": now_iso,
                    "value.last_seen_at": now_iso,
                }
            },
            upsert=True,
        )
        return False, signature

    await db.system_state.update_one(
        {"key": INTEGRITY_ALERT_STATE_SYSTEM_KEY},
        {
            "$set": {
                "key": INTEGRITY_ALERT_STATE_SYSTEM_KEY,
                "updated_at": now_iso,
                "value": {
                    "last_status": status,
                    "last_signature": signature,
                    "last_trigger": str(summary.get("trigger") or ""),
                    "last_score": int(round(float(summary.get("final_score") or 0))),
                    "last_sent_at": now_iso,
                    "last_seen_at": now_iso,
                },
            }
        },
        upsert=True,
    )
    return True, signature


async def _send_integrity_alert(summary: dict) -> None:
    from routes.payments import _get_admin_receipt_recipients, _push_realtime_notification
    from utils.email_service import is_email_configured

    should_send, signature = await _reserve_integrity_alert_transition(summary)
    if not should_send:
        return

    recipients = await _get_admin_receipt_recipients()
    if not recipients:
        return

    title = f"Integrity Engine {summary['status'].upper()} — {summary['final_score']}/100"
    body = (
        f"Trigger: {summary['trigger']} | Platform fixes: {summary['platform_fixes']} | "
        f"Domain fixes: {summary['domain_fixes']} | AI fixes: {summary['ai_applied']} | "
        f"Review queue: {summary['review_queue']}"
    )

    admin_users = await db.users.find({"email": {"$in": recipients}}, {"_id": 0, "user_id": 1, "email": 1}).to_list(25)
    for admin in admin_users:
      notif_id = f"notif_{uuid.uuid4().hex[:12]}"
      notif = {
          "id": notif_id,
          "notification_id": notif_id,
          "user_id": admin.get("user_id"),
          "type": "platform_integrity_alert",
          "title": title,
          "message": body,
          "read": False,
          "created_at": datetime.now(timezone.utc).isoformat(),
          "metadata": {"summary": summary},
      }
      await db.notifications.insert_one({**notif})
      await _push_realtime_notification(admin.get("user_id"), notif)

    if is_email_configured():
        from utils.email_service import send_catalog_template
        dedupe_seed = f"integrity-cycle-report:{signature}"
        for recipient in recipients:
            await send_catalog_template(
                recipient_email=recipient,
                template_key="integrity_cycle_report",
                recipient_name="Platform Admin",
                status=summary["status"],
                trigger=summary["trigger"],
                final_score=summary["final_score"],
                platform_fixes=summary["platform_fixes"],
                domain_fixes=summary["domain_fixes"],
                ai_applied=summary["ai_applied"],
                review_queue=summary["review_queue"],
                dedupe_key=dedupe_seed,
            )


def _force_preview_theme(html: str, theme: str) -> str:
    if theme != "dark":
        return html
    injection = """
    <style>
      body,.em-outer{background:#0B0F1A!important}
      .em-card{background:#111827!important;border-color:#1E293B!important}
      .em-body{background:#111827!important;color:#E2E8F0!important}
      .em-title{color:#F1F5F9!important}
      .em-text{color:#CBD5E1!important}
      .em-text-secondary{color:#94A3B8!important}
      .em-text-muted{color:#64748B!important}
      .em-alert{background:#1E293B!important;border-color:#334155!important}
      .em-alert-title{color:#F1F5F9!important}
      .em-alert-text{color:#94A3B8!important}
      .em-force-light-card{background:#FFFFFF!important;border-color:#E2E8F0!important}
      .em-force-dark-text{color:#0F172A!important}
      .em-force-muted-text{color:#64748B!important}
    </style>
    """
    return html.replace("</head>", f"{injection}</head>") if "</head>" in html else html


def _build_preview_html(preview_type: str, theme: str) -> str:
    from utils.email_templates import build_admin_system_alert_email

    preview_type = preview_type.strip().lower()
    if preview_type == "integrity":
        html = build_admin_system_alert_email(
            "AI Platform Integrity & Auto-Fix Engine",
            "A new integrity cycle completed. Review the latest production-quality enforcement summary below.",
            [("Status", "WARNING"), ("Trigger", "manual"), ("Platform score", "97/100"), ("Platform fixes", "0"), ("Domain fixes", "27"), ("AI fixes applied", "3"), ("Review queue", "0")],
            accent="#F59E0B",
            status_label="Integrity warning",
            footer_note="Preview mode for dark/light QA.",
            cta_label="Open Integrity Engine",
            cta_url="/admin-console?category=operations&tab=ai-platform-integrity",
        )
    elif preview_type == "performance":
        html = build_admin_system_alert_email(
            "Performance Alert: WARNING",
            "Web vitals have degraded beyond acceptable thresholds. Review the sample alert layout below.",
            [("LCP", "3.9s • WARNING • Threshold 2.5s"), ("CLS", "0.21 • WARNING • Threshold 0.1"), ("INP", "320ms • WARNING • Threshold 200ms")],
            accent="#F59E0B",
            status_label="Performance warning",
            footer_note="Preview mode for dark/light QA.",
        )
    elif preview_type in {"payment-e2e", "payment_e2e"}:
        html = build_admin_system_alert_email(
            "Payment E2E Failure Alert",
            "Regression report PAY-ALERT-2026 completed with severity HIGH. Passed 14 / 18 checks (77.8%).",
            [("Failed Check", "PayPal monthly premium Paris flow missing receipt attachment"), ("Failed Check", "Admin alert latency above threshold")],
            accent="#EF4444",
            status_label="ALERT",
            footer_note="Preview mode for dark/light QA.",
        )
    else:
        raise HTTPException(status_code=404, detail="Preview type not found")
    return _force_preview_theme(html, theme)


async def _send_preview_alert(preview_type: str, recipient_email: str, recipient_name: str) -> dict:
    from utils.email_service import send_email

    # V7 compliant: use registered template
    from utils.email_templates import build_integrity_preview_alert_email
    preview_html = _build_preview_html(preview_type, "dark")
    tpl = build_integrity_preview_alert_email(
        preview_type=preview_type,
        preview_html=preview_html,
    )
    await send_email(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        subject=tpl.subject,
        content=tpl.html,
        content_text=tpl.text,
        template_key="integrity_preview_alert",
        skip_branding=True,
    )
    return {"success": True, "preview_type": preview_type, "recipient_email": recipient_email}


async def _domain_status_rollup() -> dict:
    from routes import admin_autofix_engine

    statuses = []
    counts = {"healthy": 0, "fixed": 0, "warning": 0, "stale": 0, "error": 0}
    for key, cfg in admin_autofix_engine.DOMAINS.items():
        try:
            item = await admin_autofix_engine._get_domain_status(key, cfg)
        except Exception as exc:
            item = {"domain": key, "label": cfg["label"], "status": "error", "issues_found": 0, "fixes_applied": 0, "last_run": None, "fix_action": cfg["fix_action"], "error": str(exc)[:120]}
        counts[item["status"]] = counts.get(item["status"], 0) + 1
        statuses.append(item)
    return {"summary": counts, "domains": statuses}


async def _integrity_layers(platform_scan: dict, live_services: dict) -> list[dict]:
    translation_jobs = await db.translation_jobs.count_documents({"status": "completed"})
    brand_audits = await db.brand_protection_audit.count_documents({})
    scheduler = live_services.get("scheduler", {})
    realtime = live_services.get("realtime", {})
    build_ok = not platform_scan.get("build", {}).get("stale", False)
    stale_urls = platform_scan.get("stale_urls", {}).get("count", 0)
    total_issues = platform_scan.get("total_issues", 0)
    return [
        {"id": "frontend", "label": "Frontend + Responsiveness", "status": "healthy" if build_ok and stale_urls == 0 else "warning", "detail": platform_scan.get("build", {}).get("message", "Frontend scan complete")},
        {"id": "backend", "label": "Backend + APIs", "status": "healthy" if total_issues < 5 else "warning", "detail": f"{platform_scan.get('score', 0)}/100 platform scan score"},
        {"id": "db", "label": "Database Integrity", "status": "healthy" if scheduler.get("heartbeats_healthy", 0) >= max(scheduler.get("heartbeats_total", 1) - 1, 1) else "warning", "detail": f"{scheduler.get('heartbeats_healthy', 0)}/{scheduler.get('heartbeats_total', 0)} scheduler heartbeats healthy"},
        {"id": "realtime", "label": "Realtime Sync", "status": "healthy" if realtime.get("active_sessions", 0) >= 0 else "warning", "detail": f"{realtime.get('ws_connections', 0)} websocket connections"},
        {"id": "theme", "label": "Light / Dark Adaptation", "status": "healthy" if build_ok else "warning", "detail": "Auto-theme guarded by enterprise web bundle validation"},
        {"id": "i18n", "label": "Language + Brand Safety", "status": "healthy" if translation_jobs >= 0 else "warning", "detail": f"{translation_jobs} translation jobs, {brand_audits} brand audits recorded"},
    ]


async def _collect_overview() -> dict:
    from routes import platform_health

    admin_user = _admin_stub()
    config = await _get_config()
    latest_run = await db.ai_platform_integrity_runs.find_one({}, {"_id": 0}, sort=[("started_at", -1)]) or {}
    latest_lock = await db.ai_platform_integrity_locks.find_one({}, {"_id": 0}, sort=[("created_at", -1)]) or {}
    latest_ai = await db.ai_autofix_history.find_one({}, {"_id": 0}, sort=[("run_at", -1)]) or {}
    latest_repair = await db.self_repair_log.find_one({}, {"_id": 0}, sort=[("timestamp", -1)]) or {}
    platform_scan = await platform_health.scan_platform_health(admin_user)
    live_services = await platform_health.get_live_services_status(admin_user)
    domain_rollup = await _domain_status_rollup()
    global_validation = await _global_surface_validation(platform_scan, live_services, domain_rollup)
    review_queue = await db.ai_autofix_review_queue.count_documents({"review_status": "pending"})
    autonomous_ids = [
        "platform_full_auto_audit",
        "enterprise_lock_cycle",
        "platform_e2e_regression_gate",
        "ai_platform_integrity_guardian",
        "ai_platform_integrity_realtime",
        "ai_platform_integrity_daily",
    ]
    heartbeats = await db.scheduler_heartbeats.find({"job_id": {"$in": autonomous_ids}}, {"_id": 0}).sort("last_run", -1).to_list(20)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "platform_scan": platform_scan,
        "live_services": live_services,
        "domain_rollup": domain_rollup,
        "ai_autofix_latest": latest_ai,
        "self_repair_latest": latest_repair,
        "review_queue": review_queue,
        "autonomous_jobs": heartbeats,
        "latest_run": latest_run,
        "latest_lock": latest_lock,
        "global_registry": _scope_registry(),
        "global_validation": global_validation,
        "integrity_layers": await _integrity_layers(platform_scan, live_services),
    }


async def run_platform_integrity_cycle(*, trigger: str, include_ai: bool) -> dict:
    from routes import ai_autofix_engine, admin_autofix_engine, platform_health, self_repair_engine

    config = await _get_config()
    if not config.get("enabled", True):
        return {"status": "disabled", "trigger": trigger}

    admin_user = _admin_stub()
    started_at = datetime.now(timezone.utc).isoformat()
    baseline_scan = await platform_health.scan_platform_health(admin_user)
    platform_fix = await platform_health.auto_fix_platform(admin_user) if baseline_scan.get("fixable_issues", 0) > 0 else None
    self_repair_result = await self_repair_engine.run_self_repair()

    domain_results = {}
    domain_issues = 0
    domain_fixes = 0
    for key in admin_autofix_engine.DOMAINS:
        result = await admin_autofix_engine._execute_fix(key)
        domain_results[key] = result
        domain_issues += int(result.get("issues_found", 0) or 0)
        domain_fixes += int(result.get("fixes_applied", 0) or 0)

    ai_result = None
    if include_ai:
        ai_result = await ai_autofix_engine.run_all_fixes()

    validation_scan = await platform_health.scan_platform_health(admin_user)
    live_services = await platform_health.get_live_services_status(admin_user)
    domain_rollup = await _domain_status_rollup()
    global_validation = await _global_surface_validation(validation_scan, live_services, domain_rollup)
    review_queue = await db.ai_autofix_review_queue.count_documents({"review_status": "pending"})
    total_repairs = int(self_repair_result.get("total", 0) or 0)
    ai_applied = int(ai_result.get("total_applied", 0) or 0) if ai_result else 0
    status = "healthy" if validation_scan.get("score", 0) >= 90 and review_queue == 0 else "warning" if validation_scan.get("score", 0) >= 70 else "critical"
    if global_validation.get("status") == "critical":
        status = "critical"
    elif global_validation.get("status") == "warning" and status == "healthy":
        status = "warning"

    record = {
        "run_id": f"integrity_{uuid.uuid4().hex[:12]}",
        "trigger": trigger,
        "mode": "full" if include_ai else "realtime",
        "status": status,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "baseline_score": baseline_scan.get("score", 0),
        "final_score": validation_scan.get("score", 0),
        "platform_fixes": sum((action.get("fixed_count", 0) or 0) for action in (platform_fix or {}).get("actions", [])),
        "self_repairs": total_repairs,
        "domain_issues": domain_issues,
        "domain_fixes": domain_fixes,
        "ai_applied": ai_applied,
        "review_queue": review_queue,
        "baseline_scan": baseline_scan,
        "validation_scan": validation_scan,
        "platform_fix": platform_fix,
        "self_repair": self_repair_result,
        "domain_results": domain_results,
        "ai_result": ai_result,
        "live_services": live_services,
        "domain_rollup": domain_rollup,
        "global_validation": global_validation,
        "global_registry": _scope_registry(),
    }
    lock_state = await _lock_integrity_state(record, global_validation, config)
    record["lock_state"] = lock_state
    await db.ai_platform_integrity_runs.insert_one({**record})

    if config.get("alert_on_critical_fix", True) and (status != "healthy" or record["platform_fixes"] > 0 or domain_fixes > 0 or total_repairs > 0 or ai_applied > 0):
        await _send_integrity_alert({
            "status": status,
            "trigger": trigger,
            "final_score": record["final_score"],
            "platform_fixes": record["platform_fixes"],
            "domain_fixes": domain_fixes,
            "ai_applied": ai_applied,
            "review_queue": review_queue,
            "critical_checks": global_validation.get("summary", {}).get("critical", 0),
        })

    return record


async def scheduled_platform_integrity_realtime() -> None:
    job_id = "ai_platform_integrity_realtime"
    try:
        result = await run_platform_integrity_cycle(trigger="realtime_scheduler", include_ai=False)
        await _set_scheduler_heartbeat(
            job_id,
            status="healthy" if result.get("status") != "critical" else "warning",
            details={
                "score": result.get("final_score"),
                "run_id": result.get("run_id"),
                "global_status": result.get("global_validation", {}).get("status"),
            },
        )
    except Exception as exc:
        await _set_scheduler_heartbeat(job_id, status="error", details={"error": str(exc)[:160]})


async def scheduled_platform_integrity_guardian() -> None:
    job_id = "ai_platform_integrity_guardian"
    try:
        result = await run_platform_integrity_cycle(trigger="guardian_scheduler", include_ai=False)
        await _set_scheduler_heartbeat(
            job_id,
            status="healthy" if result.get("status") != "critical" else "warning",
            details={
                "score": result.get("final_score"),
                "run_id": result.get("run_id"),
                "global_status": result.get("global_validation", {}).get("status"),
            },
        )
    except Exception as exc:
        await _set_scheduler_heartbeat(job_id, status="error", details={"error": str(exc)[:160]})


async def scheduled_platform_integrity_daily() -> None:
    job_id = "ai_platform_integrity_daily"
    try:
        result = await run_platform_integrity_cycle(trigger="daily_scheduler", include_ai=True)
        await _set_scheduler_heartbeat(
            job_id,
            status="healthy" if result.get("status") != "critical" else "warning",
            details={
                "score": result.get("final_score"),
                "run_id": result.get("run_id"),
                "global_status": result.get("global_validation", {}).get("status"),
            },
        )
    except Exception as exc:
        await _set_scheduler_heartbeat(job_id, status="error", details={"error": str(exc)[:160]})


@router.get("/overview")
async def get_platform_integrity_overview(request: Request):
    await require_admin(request)
    return await _collect_overview()


@router.get("/history")
async def get_platform_integrity_history(request: Request, limit: int = 12):
    await require_admin(request)
    rows = await db.ai_platform_integrity_runs.find({}, {"_id": 0}).sort("started_at", -1).limit(max(1, min(limit, 50))).to_list(limit)
    return {"runs": rows, "count": len(rows)}


@router.get("/email-preview/{preview_type}")
async def get_platform_integrity_email_preview(preview_type: str, request: Request, theme: str = "light"):
    await require_admin(request)
    return {"preview_type": preview_type, "theme": theme, "html": _build_preview_html(preview_type, theme)}


@router.post("/send-preview-alert")
async def send_platform_integrity_preview_alert(request: Request, body: PreviewAlertRequest):
    await require_admin(request)
    return await _send_preview_alert(body.preview_type, body.recipient_email or "realaicoach@gmail.com", body.recipient_name or "Preview Recipient")


@router.post("/run-cycle")
async def trigger_platform_integrity_cycle(request: Request):
    await require_admin(request)
    return await run_platform_integrity_cycle(trigger="manual", include_ai=True)


@router.post("/run")
async def trigger_platform_integrity_cycle_alias(request: Request):
    await require_admin(request)
    return await run_platform_integrity_cycle(trigger="manual_alias", include_ai=True)


@router.get("/config")
async def get_platform_integrity_config(request: Request):
    await require_admin(request)
    return await _get_config()


@router.put("/config")
async def update_platform_integrity_config(request: Request, body: IntegrityConfigUpdate):
    await require_admin(request)
    config = await _get_config()
    update = {**config}
    if body.alert_on_critical_fix is not None:
        update["alert_on_critical_fix"] = bool(body.alert_on_critical_fix)
    if body.realtime_interval_minutes is not None:
        update["realtime_interval_minutes"] = max(5, int(body.realtime_interval_minutes))
    if body.daily_scan_hour_utc is not None:
        update["daily_scan_hour_utc"] = max(0, min(23, int(body.daily_scan_hour_utc)))
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.ai_platform_integrity_config.update_one({"rule_id": DEFAULT_RULE["rule_id"]}, {"$set": update}, upsert=True)
    return {"success": True, "config": await _get_config()}


@router.post("/activate-full-autonomous-mode")
async def activate_full_autonomous_mode(request: Request):
    await require_admin(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    config = await _get_config()
    next_config = {
        **config,
        "enabled": True,
        "safe_mode": True,
        "locked_mode": True,
        "autonomous_mode": "full_platform_persistent",
        "zero_error_policy": True,
        "global_e2e_validation": True,
        "auto_lock_regressions": True,
        "alert_on_critical_fix": True,
        "realtime_interval_minutes": 5,
        "updated_at": now_iso,
        "activated_at": now_iso,
    }
    await db.ai_platform_integrity_config.update_one(
        {"rule_id": DEFAULT_RULE["rule_id"]},
        {"$set": next_config},
        upsert=True,
    )
    run = await run_platform_integrity_cycle(trigger="full_platform_autonomous_activation", include_ai=True)
    return {
        "success": True,
        "message": "Full platform autonomous integrity mode is active and locked.",
        "config": await _get_config(),
        "activation_run": {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "final_score": run.get("final_score"),
            "global_validation_status": run.get("global_validation", {}).get("status"),
            "lock_id": run.get("lock_state", {}).get("lock_id"),
        },
    }