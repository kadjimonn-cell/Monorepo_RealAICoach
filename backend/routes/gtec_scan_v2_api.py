"""
GTEC C5 — API surface for the Security Dashboard.

All endpoints are admin-only.

Endpoints
---------
GET    /api/admin/gtec-scan-v2/directive         — canonical directive text
GET    /api/admin/gtec-scan-v2/status/{job_id}   — live status
GET    /api/admin/gtec-scan-v2/latest            — most recent report
GET    /api/admin/gtec-scan-v2/history           — last 10 reports (summaries)
GET    /api/admin/gtec-scan-v2/memory            — learning-memory fingerprints
GET    /api/admin/gtec-scan-v2/schedule          — current auto-run schedule
GET    /api/admin/gtec-scan-v2/policy/effective  — immutable autonomous policy
GET    /api/admin/gtec-scan-v2/executions        — recent autonomous runs
GET    /api/admin/gtec-scan-v2/findings/latest   — flattened latest findings
GET    /api/admin/gtec-scan-v2/incidents         — auto-escalated incidents
GET    /api/admin/gtec-scan-v2/report-pdf/{task_id} — canonical §12/§13 PDF export
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from utils.pdf_v15_filename import build_pdf_v15_filename

from routes.db import db, require_admin
from services import gtec_scan_v2 as svc

router = APIRouter(prefix="/admin/gtec-scan-v2", tags=["GTEC C5"])


class RunBody(BaseModel):
    viewports: str = Field(
        "mobile,tablet,desktop,wide",
        # Directive §7: Mobile / Tablet / Desktop / Web scaling — all 4
        # required. Caller may override but must name valid subset.
        pattern=r"^(mobile|tablet|desktop|wide)(,(mobile|tablet|desktop|wide))*$",
    )


class ScheduleBody(BaseModel):
    enabled: Optional[bool] = None
    interval_hours: Optional[int] = Field(None, ge=1, le=24)
    viewports: Optional[str] = Field(
        None,
        pattern=r"^(mobile|tablet|desktop|wide)(,(mobile|tablet|desktop|wide))*$",
    )


class GoNoGoDrillBody(BaseModel):
    simulate_hard_block: bool = True


class ExternalCertificationRerunBody(BaseModel):
    force: bool = False
    include_release_drill: bool = True
    simulate_hard_block: bool = True


class Matrix64RunBody(BaseModel):
    force: bool = True


class ViewportArtifactItemIn(BaseModel):
    route: str
    viewport: str
    status: str
    screenshot: Optional[str] = None
    reason: Optional[str] = None


class ViewportArtifactsIn(BaseModel):
    run_id: str
    base_url: str
    routes_tested: list[str]
    total_checks: int
    failed_checks: int
    generated_at: Optional[str] = None
    artifacts: list[ViewportArtifactItemIn]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_safe(ts: Any) -> Optional[datetime]:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _flatten_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    sections = report.get("sections") or {}
    for section_name, section in sections.items():
        for finding in (section.get("findings") or []):
            items.append({
                "section": section_name,
                "label": finding.get("label"),
                "severity": finding.get("severity"),
                "detail": finding.get("detail"),
                "evidence": finding.get("evidence"),
            })
    return items


def _summarise(report: dict[str, Any]) -> dict[str, Any]:
    raw_task_id = report.get("task_id")
    public_task_id = svc.to_public_task_id(raw_task_id)
    return {
        "task_id": public_task_id,
        "internal_task_id": raw_task_id,
        "execution_hash": report.get("execution_hash"),
        "status": report.get("status"),
        "critical_vulns": report.get("critical_vulns"),
        "high_vulns": report.get("high_vulns"),
        "medium_vulns": report.get("medium_vulns"),
        "low_vulns": report.get("low_vulns"),
        "regressions": report.get("regressions"),
        "security_scan": report.get("security_scan"),
        "e2e_tests": report.get("e2e_tests"),
        "responsiveness": report.get("responsiveness"),
        "performance": report.get("performance"),
        "rbac_status": report.get("rbac_status"),
        "subscription_enforcement": report.get("subscription_enforcement"),
        "triggered_by": report.get("triggered_by"),
        "actor": report.get("actor"),
        "summary": report.get("summary"),
        "generated_at": report.get("generated_at"),
        "elapsed_ms": report.get("elapsed_ms"),
        "severity_counts": report.get("severity_counts"),
    }


def _normalise_report_for_public(report: dict[str, Any]) -> dict[str, Any]:
    out = dict(report or {})
    raw_task_id = out.get("task_id")
    public_task_id = svc.to_public_task_id(raw_task_id)
    if raw_task_id:
        out["internal_task_id"] = raw_task_id
    out["task_id"] = public_task_id

    email_dispatch = out.get("email_dispatch")
    if isinstance(email_dispatch, dict):
        pdf_meta = email_dispatch.get("pdf_attachment")
        if isinstance(pdf_meta, dict):
            filename = str(pdf_meta.get("filename") or "")
            if filename:
                pdf_meta = {
                    **pdf_meta,
                    "filename": filename.replace("gtec-v2", "gtec-c5").replace("gtec_v2", "gtec_c5"),
                }
                email_dispatch = {**email_dispatch, "pdf_attachment": pdf_meta}
                out["email_dispatch"] = email_dispatch

    return out


@router.get("/directive")
async def v2_directive(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    text = svc.read_directive_text()
    return {
        "system_name": "GTEC C5",
        "directive_text": text,
        "directive_version": svc._hash_obj(text[:4000]) if text else None,
        "always_active": True,
        "non_disableable": True,
        "loaded_from": str(svc.DIRECTIVE_FILE),
    }


@router.post("/run")
async def v2_run(request: Request, body: RunBody):
    await require_admin(request)
    raise HTTPException(
        status_code=403,
        detail=(
            "Manual scan trigger is disabled by autonomous policy. "
            "GTEC runs only through scheduled/event-driven safe auto-run."
        ),
    )


@router.get("/status/{job_id}")
async def v2_status(request: Request, job_id: str):
    await require_admin(request)
    job = svc.JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_id not found")
    return {"job": {**job}}


@router.get("/latest")
async def v2_latest(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    doc = await db[svc.REPORTS_COL].find_one(
        {}, {"_id": 0}, sort=[("generated_at", -1)],
    )
    if not doc:
        return {"report": None}

    hydrated, changed = svc.ensure_report_sections_complete(doc)
    if changed:
        await db[svc.REPORTS_COL].update_one(
            {"task_id": doc.get("task_id")},
            {"$set": {"sections": hydrated.get("sections") or {}, "steps_skipped": hydrated.get("steps_skipped") or []}},
            upsert=False,
        )
        if await svc.legacy_mirror_write_enabled(db):
            await db[svc.LEGACY_REPORTS_COL].update_one(
                {"task_id": doc.get("task_id")},
                {"$set": {"sections": hydrated.get("sections") or {}, "steps_skipped": hydrated.get("steps_skipped") or []}},
                upsert=False,
            )
    return {"report": _normalise_report_for_public(hydrated)}


@router.get("/report-pdf/{task_id}")
async def v2_report_pdf(request: Request, task_id: str):
    """Return canonical §12+§13 PDF for a completed GTEC task.

    This endpoint is the source-of-truth artifact endpoint for compliance
    verification (email attachments may be transformed by downstream gateways).
    """
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    aliases = svc.resolve_task_id_aliases(task_id)
    doc = await db[svc.REPORTS_COL].find_one({"task_id": {"$in": aliases}}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="task_id not found")

    hydrated_sections_doc, sections_changed = svc.ensure_report_sections_complete(doc)
    if sections_changed:
        doc = hydrated_sections_doc
        await db[svc.REPORTS_COL].update_one(
            {"task_id": doc.get("task_id")},
            {"$set": {"sections": doc.get("sections") or {}, "steps_skipped": doc.get("steps_skipped") or []}},
            upsert=False,
        )
        if await svc.legacy_mirror_write_enabled(db):
            await db[svc.LEGACY_REPORTS_COL].update_one(
                {"task_id": doc.get("task_id")},
                {"$set": {"sections": doc.get("sections") or {}, "steps_skipped": doc.get("steps_skipped") or []}},
                upsert=False,
            )

    # Backfill canonical C5 notification snapshot for older reports so PDF/email
    # surfaces do not diverge on UNKNOWN/0 defaults.
    if not (doc.get("c5_notification_snapshot") or {}):
        try:
            mirrored = svc.build_snapshot_from_report_email_dispatch(doc)
            has_dispatch_runtime = bool((doc.get("email_dispatch") or {}).get("c5_runtime_summary"))
            hydrated = mirrored if has_dispatch_runtime else await svc.build_c5_notification_snapshot(db, doc)
            doc["c5_notification_snapshot"] = hydrated
            await db[svc.REPORTS_COL].update_one(
                {"task_id": doc.get("task_id")},
                {"$set": {"c5_notification_snapshot": hydrated}},
                upsert=False,
            )
            if await svc.legacy_mirror_write_enabled(db):
                await db[svc.LEGACY_REPORTS_COL].update_one(
                    {"task_id": doc.get("task_id")},
                    {"$set": {"c5_notification_snapshot": hydrated}},
                    upsert=False,
                )
        except Exception:
            # keep endpoint non-breaking; renderer will still show warning state
            pass

    pdf_export = svc.build_canonical_gtec_pdf_export(doc)
    if not pdf_export or not pdf_export.get("pdf_bytes"):
        raise HTTPException(status_code=500, detail="Failed to build canonical PDF export")

    public_task_id = svc.to_public_task_id(doc.get("task_id") or task_id)
    filename = build_pdf_v15_filename("compliance", public_task_id)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-PDF-Canonical-SHA256": str(pdf_export.get("sha256") or ""),
        "X-PDF-Policy-Mode": str(pdf_export.get("policy_mode") or ""),
        "X-PDF-Source-Header": str(pdf_export.get("source_header") or ""),
        "X-PDF-Normalized-Header": str(pdf_export.get("normalized_header") or ""),
        "X-GTEC-Public-Task-ID": public_task_id,
        "X-GTEC-Internal-Task-ID": str(doc.get("task_id") or ""),
    }
    return Response(
        content=pdf_export.get("pdf_bytes") or b"",
        media_type="application/pdf",
        headers=headers,
    )


@router.get("/history")
async def v2_history(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    items: list[dict[str, Any]] = []
    async for d in db[svc.REPORTS_COL].find({}, {"_id": 0}).sort("generated_at", -1).limit(10):
        items.append(_summarise(d))
    return {"items": items, "count": len(items)}


@router.get("/memory")
async def v2_memory(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    items: list[dict[str, Any]] = []
    async for d in db[svc.MEMORY_COL].find({}, None).sort("hits", -1).limit(30):
        items.append({
            "fingerprint": str(d.get("_id")),
            "hits": int(d.get("hits") or 0),
            "last_seen_task": svc.to_public_task_id(d.get("last_seen_task") or ""),
            "internal_last_seen_task": d.get("last_seen_task"),
            "last_seen_at": d.get("last_seen_at"),
        })
    return {"items": items, "count": len(items)}


@router.get("/schedule")
async def v2_schedule_get(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    return await svc.get_schedule_settings(db)


@router.get("/migration/legacy-cleanup-window")
async def v2_legacy_cleanup_window(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    control = await svc.ensure_legacy_cleanup_window(db)
    return {
        "control": control,
        "mirror_write_enabled_now": await svc.legacy_mirror_write_enabled(db),
        "generated_at": _now_iso(),
    }


@router.get("/pipeline/enforcement-state")
async def v2_pipeline_enforcement_state(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    return {
        "state": await svc.get_pipeline_enforcement_state(db),
        "generated_at": _now_iso(),
    }


@router.get("/pipeline/go-no-go-drill/latest")
async def v2_pipeline_go_no_go_drill_latest(request: Request):
    await require_admin(request)
    doc = await db.gtec_c5_release_drills.find_one({}, {"_id": 0}, sort=[("drill_at", -1)])
    return {
        "drill": doc,
        "generated_at": _now_iso(),
    }


@router.get("/pipeline/evidence-bundle/latest")
async def v2_pipeline_evidence_bundle_latest(request: Request):
    await require_admin(request)
    bundle = await db.gtec_c5_release_evidence_bundles.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    latest_viewport = await db.gtec_c5_viewport_artifacts.find_one({}, {"_id": 0}, sort=[("stored_at", -1)])
    if bundle and latest_viewport:
        merged = {**bundle}
        merged.setdefault("viewport_matrix", {
            "run_id": latest_viewport.get("run_id"),
            "route_source": latest_viewport.get("route_source"),
            "routes_tested": latest_viewport.get("routes_tested") or [],
            "viewports": latest_viewport.get("viewports") or ["mobile", "tablet", "desktop"],
            "total_checks": int(latest_viewport.get("total_checks") or 0),
            "failed_checks": int(latest_viewport.get("failed_checks") or 0),
            "matrix_summary": latest_viewport.get("matrix_summary") or {},
            "artifacts": latest_viewport.get("artifacts") or [],
        })
        merged.setdefault("white_screen_sentry", {
            "run_id": latest_viewport.get("run_id"),
            "gate_passed": bool(latest_viewport.get("white_screen_gate_passed")) and int(latest_viewport.get("failed_checks") or 0) == 0,
            "failed_checks": int(latest_viewport.get("failed_checks") or 0),
            "total_checks": int(latest_viewport.get("total_checks") or 0),
            "generated_at": latest_viewport.get("generated_at"),
        })
        bundle = merged
    return {
        "bundle": bundle,
        "generated_at": _now_iso(),
    }


@router.post("/pipeline/viewport-artifacts")
async def v2_pipeline_viewport_artifacts(request: Request, body: ViewportArtifactsIn):
    await require_admin(request)
    gate_passed = int(body.failed_checks) == 0 and int(body.total_checks) > 0
    doc = {
        "run_id": body.run_id,
        "base_url": body.base_url,
        "routes_tested": body.routes_tested,
        "total_checks": int(body.total_checks),
        "failed_checks": int(body.failed_checks),
        "white_screen_gate_passed": gate_passed,
        "generated_at": body.generated_at or _now_iso(),
        "artifacts": [a.model_dump() for a in body.artifacts],
        "stored_at": _now_iso(),
    }
    await db.gtec_c5_viewport_artifacts.update_one(
        {"run_id": body.run_id},
        {"$set": doc},
        upsert=True,
    )
    return {
        "ok": True,
        "run_id": body.run_id,
        "stored_at": doc["stored_at"],
    }


@router.get("/pipeline/viewport-artifacts/latest")
async def v2_pipeline_viewport_artifacts_latest(request: Request):
    await require_admin(request)
    doc = await db.gtec_c5_viewport_artifacts.find_one({}, {"_id": 0}, sort=[("stored_at", -1)])
    return {
        "artifact_run": doc,
        "generated_at": _now_iso(),
    }


@router.get("/pipeline/matrix64/config")
async def v2_pipeline_matrix64_config(request: Request):
    await require_admin(request)
    cfg = await svc.get_matrix64_pipeline_config(db)
    return {
        "config": cfg,
        "generated_at": _now_iso(),
    }


@router.get("/pipeline/matrix64/latest")
async def v2_pipeline_matrix64_latest(request: Request):
    await require_admin(request)
    latest = await svc.get_latest_matrix64_pipeline_run(db)
    return {
        "run": latest,
        "generated_at": _now_iso(),
    }


@router.get("/pipeline/matrix64/history")
async def v2_pipeline_matrix64_history(request: Request, limit: int = 10):
    await require_admin(request)
    rows = await svc.list_matrix64_pipeline_runs(db, limit=limit)
    return {
        "items": rows,
        "count": len(rows),
        "generated_at": _now_iso(),
    }


@router.post("/pipeline/matrix64/run")
async def v2_pipeline_matrix64_run(request: Request, body: Matrix64RunBody):
    await require_admin(request)
    run = await svc.run_strict_matrix64_pipeline(
        db,
        triggered_by="admin_api",
        force=bool(body.force),
    )
    return {
        "run": run,
        "generated_at": _now_iso(),
    }


@router.get("/pipeline/external-host-certification/latest")
async def v2_pipeline_external_host_certification_latest(request: Request):
    await require_admin(request)
    doc = await svc.get_latest_external_host_certification(db)
    retry = await svc.should_retry_external_host_certification(db)
    return {
        "certification_run": doc,
        "retry_plan": retry,
        "generated_at": _now_iso(),
    }


@router.get("/pipeline/preflight-telemetry/trend")
async def v2_pipeline_preflight_telemetry_trend(request: Request, hours: int = 24, limit: int = 400):
    await require_admin(request)
    trend = await svc.get_preflight_telemetry_trend(db, hours=hours, limit=limit)
    return {
        "trend": trend,
        "generated_at": _now_iso(),
    }


@router.post("/pipeline/external-host-certification/rerun")
async def v2_pipeline_external_host_certification_rerun(request: Request, body: ExternalCertificationRerunBody):
    await require_admin(request)
    try:
        doc = await asyncio.wait_for(
            svc.run_external_host_certification_pass(
                db,
                triggered_by="admin_api",
                force=bool(body.force),
                include_release_drill=bool(body.include_release_drill),
                simulate_hard_block=bool(body.simulate_hard_block),
            ),
            timeout=35,
        )
    except asyncio.TimeoutError:
        doc = {
            "certification_id": f"ext_cert_busy_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "status": "busy",
            "reason": "external_host_certification_runtime_timeout",
            "triggered_by": "admin_api",
            "force": bool(body.force),
            "include_release_drill": bool(body.include_release_drill),
            "simulate_hard_block": bool(body.simulate_hard_block),
            "health": {
                "stable": False,
                "checks": [],
            },
            "started_at": _now_iso(),
            "finished_at": _now_iso(),
            "timed_out_seconds": 35,
        }
    return {
        "certification_run": doc,
        "generated_at": _now_iso(),
    }


@router.post("/pipeline/go-no-go-drill")
async def v2_pipeline_go_no_go_drill(request: Request, body: GoNoGoDrillBody):
    await require_admin(request)
    return await svc.run_go_no_go_release_drill(
        db,
        simulate_hard_block=bool(body.simulate_hard_block),
        triggered_by="admin_api",
    )


@router.post("/schedule")
async def v2_schedule_set(request: Request, body: ScheduleBody):
    await require_admin(request)
    raise HTTPException(
        status_code=403,
        detail=(
            "Schedule mutation is disabled by autonomous policy. "
            "Policy is immutable at runtime; use platform policy pipeline only."
        ),
    )



# ──────────────────────────────────────────────────────────────────────────
# Upstream Watchdog endpoints (§5 systemic-fix self-driving loop)
# ──────────────────────────────────────────────────────────────────────────
from services import gtec_upstream_watchdog as _watchdog  # noqa: E402


@router.get("/watchdog/state")
async def v2_watchdog_state(request: Request):
    await require_admin(request)
    return await _watchdog.get_state(db)


@router.post("/watchdog/run")
async def v2_watchdog_run(request: Request):
    """Manually trigger the upstream watchdog (same code path as the
    nightly APScheduler job). Returns a §12-style summary."""
    await require_admin(request)
    raise HTTPException(
        status_code=403,
        detail=(
            "Manual watchdog trigger is disabled by autonomous policy. "
            "Watchdog executes automatically by scheduler."
        ),
    )


@router.get("/policy/effective")
async def v2_policy_effective(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    policy = await svc.get_effective_policy(db)
    return {
        **policy,
        "mode": "autonomous_only",
        "manual_input_allowed": False,
        "policy_locked": True,
        "platform_data_only": True,
        "manual_endpoints_disabled": [
            "/api/admin/gtec-scan-v2/run",
            "/api/admin/gtec-scan-v2/schedule",
            "/api/admin/gtec-scan-v2/watchdog/run",
            "/api/admin/gtec-crawler/run",
            "/api/admin/gtec-crawler/auto-run",
            "/api/admin/gtec-crawler/alerts/settings",
            "/api/admin/gtec-crawler/alerts/test",
        ],
        "generated_at": _now_iso(),
    }


@router.get("/executions")
async def v2_executions(request: Request, limit: int = 20):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    safe_limit = max(1, min(int(limit), 100))
    items: list[dict[str, Any]] = []
    async for d in db[svc.EXECUTIONS_COL].find({}, {"_id": 0}).sort("generated_at", -1).limit(safe_limit):
        raw_task_id = d.get("task_id")
        if raw_task_id:
            d["internal_task_id"] = raw_task_id
            d["task_id"] = svc.to_public_task_id(raw_task_id)
        items.append(d)
    return {"items": items, "count": len(items)}


@router.get("/findings/latest")
async def v2_findings_latest(request: Request):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    report = await db[svc.REPORTS_COL].find_one({}, {"_id": 0}, sort=[("generated_at", -1)])
    if not report:
        return {"items": [], "count": 0}
    findings = _flatten_findings(report)
    return {
        "task_id": svc.to_public_task_id(report.get("task_id") or ""),
        "internal_task_id": report.get("task_id"),
        "generated_at": report.get("generated_at"),
        "items": findings,
        "count": len(findings),
    }


@router.get("/incidents")
async def v2_incidents(request: Request, status: str = "open", limit: int = 50):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)
    safe_limit = max(1, min(int(limit), 200))
    query: dict[str, Any] = {}
    if status and status != "all":
        query["status"] = status
    items: list[dict[str, Any]] = []
    async for d in db[svc.INCIDENTS_COL].find(query, {"_id": 0}).sort("updated_at", -1).limit(safe_limit):
        raw_task_id = d.get("task_id")
        if raw_task_id:
            d["internal_task_id"] = raw_task_id
            d["task_id"] = svc.to_public_task_id(raw_task_id)
        items.append(d)
    return {"items": items, "count": len(items), "status_filter": status}


@router.get("/incidents/lifecycle-timeline")
async def v2_incident_lifecycle_timeline(request: Request, limit: int = 30):
    await require_admin(request)
    await svc.ensure_internal_collections_migrated(db)

    safe_limit = max(1, min(int(limit), 100))
    items: list[dict[str, Any]] = []
    async for d in db[svc.INCIDENTS_COL].find({}, {"_id": 0}).sort("updated_at", -1).limit(safe_limit):
        raw_task_id = d.get("task_id")
        public_task_id = svc.to_public_task_id(raw_task_id or "") if raw_task_id else ""

        pending_start = _parse_iso_safe(d.get("pending_verification_started_at"))
        pending_deadline = (
            (pending_start + timedelta(hours=svc.INCIDENT_AUTOCLOSE_PENDING_HOURS)).isoformat()
            if pending_start
            else None
        )

        events: list[dict[str, Any]] = []
        if d.get("created_at"):
            events.append({"kind": "created", "at": d.get("created_at")})
        if d.get("pending_verification_started_at"):
            events.append({"kind": "pending_verification_started", "at": d.get("pending_verification_started_at")})
        if d.get("reopened_at"):
            events.append({"kind": "reopened", "at": d.get("reopened_at")})
        if d.get("closed_at"):
            events.append({"kind": "closed", "at": d.get("closed_at")})
        if d.get("last_autoclose_evaluated_task_id"):
            events.append({
                "kind": "autoclose_evaluated",
                "at": d.get("updated_at") or _now_iso(),
                "task_id": svc.to_public_task_id(d.get("last_autoclose_evaluated_task_id") or ""),
                "internal_task_id": d.get("last_autoclose_evaluated_task_id"),
            })

        item = {
            "incident_id": d.get("incident_id"),
            "incident_key": d.get("incident_key"),
            "label": d.get("label"),
            "severity": d.get("severity"),
            "status": d.get("status"),
            "containment": d.get("containment"),
            "clean_rescan_streak": int(d.get("clean_rescan_streak") or 0),
            "policy": d.get("auto_close_policy") or {
                "consecutive_clean_rescans_required": svc.INCIDENT_AUTOCLOSE_CLEAN_RESCANS,
                "pending_verification_hours": svc.INCIDENT_AUTOCLOSE_PENDING_HOURS,
            },
            "pending_verification_started_at": d.get("pending_verification_started_at"),
            "pending_verification_deadline": pending_deadline,
            "resolution_reason": d.get("resolution_reason"),
            "task_id": public_task_id,
            "internal_task_id": raw_task_id,
            "updated_at": d.get("updated_at"),
            "events": sorted(events, key=lambda e: str(e.get("at") or "")),
        }
        items.append(item)

    return {
        "items": items,
        "count": len(items),
        "generated_at": _now_iso(),
    }


@router.get("/trust-gates")
async def v2_trust_gates(request: Request):
    await require_admin(request)
    snapshot = await svc.build_trust_gate_snapshot(db)
    latest = snapshot.get("latest") or {}
    return {
        "system_name": "GTEC C5",
        "latest": _normalise_report_for_public(latest) if latest else None,
        "trust_score_percent": snapshot.get("trust_score_percent", 0),
        "passed_gates": snapshot.get("passed_gates", 0),
        "total_gates": snapshot.get("total_gates", 0),
        "gates": snapshot.get("gates", []),
        "generated_at": snapshot.get("generated_at") or _now_iso(),
    }


@router.get("/release-certificate")
async def v2_release_certificate(request: Request):
    await require_admin(request)
    cert = await svc.build_release_certificate_snapshot(db)

    await db.gtec_c5_release_certificates.update_one(
        {"certificate_id": cert["certificate_id"]},
        {"$set": cert},
        upsert=True,
    )

    return cert
