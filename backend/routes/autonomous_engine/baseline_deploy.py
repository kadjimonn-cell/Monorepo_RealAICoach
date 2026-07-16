"""Baseline management, certificates, completion audit, coverage, deployment, canary."""
import asyncio
import copy
import base64
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel

from routes.autonomous_engine._shared import (
    router, _db, _require_admin, _get_engine_config, _save_engine_config,
    GATE_NAMES, MANDATORY_GATES,
    DEFAULT_COVERAGE_POLICY, DEFAULT_DEPLOYMENT_POLICY,
)

from services.autonomous.common import (
    compute_certificate_hash as _compute_certificate_hash,
    compute_certificate_qr_hash as _compute_certificate_qr_hash,
    parse_iso_datetime as _parse_iso_datetime,
    resolve_external_base_url as _resolve_external_base_url,
)
from services.autonomous.audit_reports import (
    build_certificate_history_query,
    build_completion_audit_query,
)
from routes.autonomous_engine.core_pipeline import (
    _get_baseline_state, _save_baseline_state, _run_deployment_gate,
    evaluate_completion_gate_and_audit, CompletionGateRequest,
)
from utils.pdf_v15_filename import build_pdf_v15_filename


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")
    return themed

class BaselineLockRequest(BaseModel):
    note: Optional[str] = None


@router.get("/baseline/status")
async def get_pass_baseline_status(request: Request):
    """Get immutable PASS baseline protection status."""
    await _require_admin(request)
    return await _get_baseline_state()


@router.post("/baseline/lock")
async def lock_pass_baseline(request: Request, body: Optional[BaselineLockRequest] = None):
    """Lock current latest PASS run as immutable production baseline."""
    user = await _require_admin(request)
    db = await _db()
    latest_pass = await db.autonomous_engine_runs.find_one({"status": "PASS"}, {"_id": 0}, sort=[("timestamp", -1)])
    if not latest_pass:
        raise HTTPException(status_code=409, detail="Cannot lock baseline: no PASS run found")

    config = await _get_engine_config()
    baseline = await _get_baseline_state()
    baseline.update(
        {
            "locked": True,
            "locked_at": datetime.now(timezone.utc).isoformat(),
            "locked_by": str(getattr(user, "email", "admin")),
            "baseline_run_id": latest_pass.get("run_id"),
            "baseline_final_output": latest_pass.get("final_output", {}),
            "baseline_config": copy.deepcopy(config),
            "note": str((body or BaselineLockRequest()).note or "pass_baseline_locked"),
        }
    )
    await _save_baseline_state(baseline)
    return baseline


@router.get("/baseline/release-readiness-certificate/pdf")
async def download_release_readiness_certificate(request: Request):
    """Generate protected release readiness certificate (PDF) only when baseline is locked and latest run is PASS."""
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    user = await _require_admin(request)
    db = await _db()

    baseline = await _get_baseline_state()
    if not baseline.get("locked"):
        raise HTTPException(status_code=409, detail="Certificate unavailable: PASS baseline is not locked")

    latest_run = await db.autonomous_engine_runs.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
    if not latest_run:
        raise HTTPException(status_code=409, detail="Certificate unavailable: no pipeline runs found")
    if latest_run.get("status") != "PASS":
        raise HTTPException(status_code=409, detail="Certificate unavailable: latest run is not PASS")

    final_output = latest_run.get("final_output") or {}
    if str(final_output.get("STATUS", "")).upper() != "PASS":
        raise HTTPException(status_code=409, detail="Certificate unavailable: latest output STATUS is not PASS")

    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    issued_at = datetime.now(timezone.utc).isoformat()
    certificate_id = f"aecert_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    certificate_payload = {
        "certificate_id": certificate_id,
        "issued_at": issued_at,
        "baseline_run_id": baseline.get("baseline_run_id"),
        "latest_run_id": latest_run.get("run_id"),
        "latest_run_status": latest_run.get("status"),
        "final_output": final_output,
        "locked_by": baseline.get("locked_by"),
    }
    certificate_hash = _compute_certificate_hash(certificate_payload)
    verification_qr_hash = _compute_certificate_qr_hash(certificate_id, certificate_hash)
    base_url = _resolve_external_base_url() or ""
    verification_path = f"/api/admin/autonomous-engine/certificate/verify/{certificate_id}?hash={verification_qr_hash}"
    verification_url = f"{base_url}{verification_path}" if base_url else verification_path

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    pdf.setTitle("RealAICoach Release Readiness Certificate")
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(56, height - 72, "Release Readiness Certificate")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(56, height - 96, "Protected by Immutable PASS Baseline Policy")

    y = height - 136
    lines = [
        f"Certificate ID: {certificate_id}",
        f"Issued At (UTC): {issued_at}",
        f"Baseline Locked: {baseline.get('locked')}",
        f"Baseline Run ID: {baseline.get('baseline_run_id')}",
        f"Baseline Locked By: {baseline.get('locked_by')}",
        f"Latest Run ID: {latest_run.get('run_id')}",
        f"Latest Run Status: {latest_run.get('status')}",
        f"STATUS: {final_output.get('STATUS')}",
        f"TESTS: {final_output.get('TESTS')}",
        f"VALIDATION: {final_output.get('VALIDATION')}",
        f"PERFORMANCE: {final_output.get('PERFORMANCE')}",
        f"E2E: {final_output.get('E2E')}",
        f"VISUAL: {final_output.get('VISUAL')}",
        f"Certificate Hash (SHA-256): {certificate_hash}",
        f"QR Hash (Verification): {verification_qr_hash}",
        f"Verify URL: {verification_url}",
    ]
    for line in lines:
        pdf.drawString(56, y, line)
        y -= 18

    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(56, 60, "This certificate is valid only while baseline remains locked and latest run remains PASS.")

    pdf.showPage()
    pdf.save()
    buf.seek(0)
    filename = build_pdf_v15_filename("release-readiness-certificate", datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'))
    composed_pdf = compose_pdf_v15_helper_layout(
        buf.read(),
        title="Release Readiness Certificate",
        subtitle="Autonomous engine baseline governance",
        right_primary=f"Certificate: {certificate_id}",
        right_secondary=f"Run: {latest_run.get('run_id')}",
        badge_text="BASELINE READINESS CERTIFICATION",
        badge_status="PASS" if str(final_output.get("STATUS", "")).upper() == "PASS" else "WARNING",
        footer_text="RealAICoach Autonomous Engine • Enterprise profile",
        summary_title="Certificate Summary",
        summary_rows=[
            ("Baseline Locked", str(baseline.get("locked"))),
            ("Latest Status", str(latest_run.get("status"))),
            ("Hash", certificate_hash[:16]),
        ],
        callout_title="Verification URL",
        callout_subtitle="Tamper-evident validation",
        callout_detail=verification_url,
        callout_status="PASS" if str(final_output.get("STATUS", "")).upper() == "PASS" else "WARNING",
    )
    pdf_bytes = _enforce_pdf_v15_enterprise(composed_pdf, f"release_readiness_certificate_{certificate_id}")

    await db.autonomous_engine_certificates.insert_one(
        {
            "certificate_id": certificate_id,
            "issued_at": issued_at,
            "issued_by": str(getattr(user, "email", "admin")),
            "baseline_run_id": baseline.get("baseline_run_id"),
            "latest_run_id": latest_run.get("run_id"),
            "latest_run_status": latest_run.get("status"),
            "final_output": final_output,
            "certificate_hash": certificate_hash,
            "verification_qr_hash": verification_qr_hash,
            "verification_url": verification_url,
            "pdf_base64": base64.b64encode(pdf_bytes).decode("utf-8"),
            "created_at": datetime.now(timezone.utc),
        }
    )

    baseline["last_certificate"] = {
        "certificate_id": certificate_id,
        "issued_at": issued_at,
        "certificate_hash": certificate_hash,
        "verification_qr_hash": verification_qr_hash,
    }
    await _save_baseline_state(baseline)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/baseline/certificate-history")
async def get_certificate_history(
    request: Request,
    limit: int = Query(30, ge=1, le=200),
    range: str = Query("all"),
    start_at: Optional[str] = Query(None),
    end_at: Optional[str] = Query(None),
    issuer: Optional[str] = Query(None),
    run_id: Optional[str] = Query(None),
):
    """Get issuance history of release readiness certificates."""
    await _require_admin(request)
    db = await _db()
    try:
        normalized_range, query = build_certificate_history_query(
            range_value=range,
            start_at=start_at,
            end_at=end_at,
            issuer=issuer,
            run_id=run_id,
            parse_iso_datetime=_parse_iso_datetime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cursor = db.autonomous_engine_certificates.find(
        query,
        {
            "_id": 0,
            "pdf_base64": 0,
            "created_at": 0,
        },
    ).sort("issued_at", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {
        "items": items,
        "total": await db.autonomous_engine_certificates.count_documents(query),
        "filters": {
            "range": normalized_range,
            "start_at": start_at,
            "end_at": end_at,
            "issuer": issuer,
            "run_id": run_id,
        },
    }


@router.get("/baseline/certificate/download/{certificate_id}")
async def download_certificate_by_id(request: Request, certificate_id: str):
    """Download a previously issued certificate by certificate_id."""
    await _require_admin(request)
    db = await _db()
    doc = await db.autonomous_engine_certificates.find_one({"certificate_id": certificate_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Certificate not found")
    pdf_b64 = doc.get("pdf_base64")
    if not pdf_b64:
        raise HTTPException(status_code=404, detail="Certificate file missing")
    pdf_bytes = base64.b64decode(pdf_b64)
    filename = build_pdf_v15_filename("release-readiness-certificate", certificate_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/certificate/verify/{certificate_id}")
async def verify_certificate_by_hash(certificate_id: str, hash: Optional[str] = Query(None)):
    """Public verification endpoint for third-party audit validation."""
    db = await _db()
    doc = await db.autonomous_engine_certificates.find_one({"certificate_id": certificate_id}, {"_id": 0, "pdf_base64": 0, "created_at": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Certificate not found")

    expected_qr_hash = _compute_certificate_qr_hash(certificate_id, str(doc.get("certificate_hash") or ""))
    provided_hash = str(hash or "").strip()
    is_valid = bool(provided_hash) and provided_hash == expected_qr_hash

    return {
        "certificate_id": certificate_id,
        "valid": is_valid,
        "provided_hash": provided_hash or None,
        "expected_hash": expected_qr_hash,
        "verification_url": doc.get("verification_url"),
        "certificate": {
            "issued_at": doc.get("issued_at"),
            "issued_by": doc.get("issued_by"),
            "baseline_run_id": doc.get("baseline_run_id"),
            "latest_run_id": doc.get("latest_run_id"),
            "latest_run_status": doc.get("latest_run_status"),
            "final_output": doc.get("final_output"),
            "certificate_hash": doc.get("certificate_hash"),
        },
    }


@router.get("/completion-audit")
async def get_completion_audit(
    request: Request,
    limit: int = Query(200, ge=1, le=5000),
    blocked_only: bool = Query(False),
    range: str = Query("all"),
    start_at: Optional[str] = Query(None),
    end_at: Optional[str] = Query(None),
):
    """Audit trail for completion attempts blocked/allowed by strict gate."""
    await _require_admin(request)
    db = await _db()
    try:
        normalized_range, query = build_completion_audit_query(
            blocked_only=blocked_only,
            range_value=range,
            start_at=start_at,
            end_at=end_at,
            parse_iso_datetime=_parse_iso_datetime,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cursor = db.autonomous_engine_completion_audit.find(query, {"_id": 0, "timestamp": 0}).sort("timestamp", -1).limit(limit)
    entries = await cursor.to_list(length=limit)
    total = await db.autonomous_engine_completion_audit.count_documents(query)
    blocked_count = await db.autonomous_engine_completion_audit.count_documents({**query, "blocked": True})
    allowed_count = await db.autonomous_engine_completion_audit.count_documents({**query, "blocked": False})

    return {
        "range": normalized_range,
        "start_at": start_at,
        "end_at": end_at,
        "entries": entries,
        "total": total,
        "blocked_count": blocked_count,
        "allowed_count": allowed_count,
    }


@router.post("/enforce-completion")
async def enforce_completion_gate(request: Request, body: Optional[CompletionGateRequest] = None):
    """Hard-block completion if strict mode is enabled and no recent PASS pipeline exists."""
    user = await _require_admin(request)
    payload = body or CompletionGateRequest()
    evaluated = await evaluate_completion_gate_and_audit(
        user=user,
        source_endpoint="/api/admin/autonomous-engine/enforce-completion",
        workflow_type=payload.workflow_type,
        workflow_id=payload.workflow_id,
        close_reason=payload.close_reason,
        context=payload.context,
    )
    gate_lock = evaluated["gate_lock"]
    audit_entry = evaluated["audit_entry"]

    if evaluated["blocked"]:
        raise HTTPException(
            status_code=423,
            detail={
                "message": "Completion is blocked by Autonomous Engine strict hard-gate. Run pipeline until STATUS=PASS.",
                "completion_blocked": True,
                "gate_lock": gate_lock,
                "audit_entry": audit_entry,
            },
        )

    return {
        "completion_allowed": True,
        "message": "Autonomous Engine gate is OPEN. Latest PASS is within enforcement window.",
        "gate_lock": gate_lock,
        "audit_entry": audit_entry,
    }


@router.post("/completion-audit/export-nightly-now")
async def trigger_nightly_blocked_attempt_export_now(request: Request):
    """Manual admin trigger for nightly blocked-attempt export email job."""
    await _require_admin(request)
    from scheduler_jobs import scheduled_autonomous_blocked_attempts_export

    await scheduled_autonomous_blocked_attempts_export()

    db = await _db()
    latest = await db.autonomous_engine_nightly_exports.find_one({}, {"_id": 0}, sort=[("run_at", -1)])
    return {
        "triggered": True,
        "message": "Nightly blocked-attempt export executed.",
        "latest_export": latest,
    }


@router.get("/coverage/status")
async def get_coverage_status(request: Request):
    """Get current test coverage vs policy thresholds."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("coverage_policy", DEFAULT_COVERAGE_POLICY)

    latest = await db.coverage_gate_history.find_one(
        {}, {"_id": 0}, sort=[("run_at", -1)]
    )
    history = await db.coverage_gate_history.find(
        {}, {"_id": 0}
    ).sort("run_at", -1).limit(10).to_list(10)

    return {
        "policy": policy,
        "latest_run": latest,
        "history": history,
        "gate_name": "coverage",
        "mandatory": "coverage" in MANDATORY_GATES,
    }


class CoveragePolicyUpdate(BaseModel):
    global_minimum_pct: Optional[float] = None
    critical_minimum_pct: Optional[float] = None
    critical_modules: Optional[List[str]] = None
    fail_on_drop: Optional[bool] = None
    fail_on_missing_tests: Optional[bool] = None


@router.post("/coverage/policy")
async def update_coverage_policy(request: Request, body: CoveragePolicyUpdate):
    """Update coverage enforcement policy thresholds."""
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("coverage_policy", {**DEFAULT_COVERAGE_POLICY})

    if body.global_minimum_pct is not None:
        policy["global_minimum_pct"] = max(0, min(100, body.global_minimum_pct))
    if body.critical_minimum_pct is not None:
        policy["critical_minimum_pct"] = max(0, min(100, body.critical_minimum_pct))
    if body.critical_modules is not None:
        policy["critical_modules"] = body.critical_modules
    if body.fail_on_drop is not None:
        policy["fail_on_drop"] = body.fail_on_drop
    if body.fail_on_missing_tests is not None:
        policy["fail_on_missing_tests"] = body.fail_on_missing_tests

    config["coverage_policy"] = policy
    await _save_engine_config(config)

    return {"updated": True, "coverage_policy": policy}


# ═══════════════════════════════════════════════════════════
# PRE-DEPLOYMENT GATE ENDPOINTS
# ═══════════════════════════════════════════════════════════

@router.get("/deployment/status")
async def get_deployment_status(request: Request):
    """Get latest deployment gate results and policy."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = {**DEFAULT_DEPLOYMENT_POLICY, **(config.get("deployment_policy") or {})}

    latest = await db.deployment_gate_history.find_one(
        {}, {"_id": 0}, sort=[("run_at", -1)]
    )
    history = await db.deployment_gate_history.find(
        {}, {"_id": 0}
    ).sort("run_at", -1).limit(10).to_list(10)

    return {
        "policy": policy,
        "latest_run": latest,
        "history": history,
        "gate_name": "deployment",
        "in_gate_names": "deployment" in GATE_NAMES,
    }


@router.post("/deployment/run")
async def run_deployment_gate_standalone(request: Request):
    """Execute the full pre-deployment gate (load sim + stress test + degradation check)."""
    await _require_admin(request)
    result = await _run_deployment_gate()
    return result


class DeploymentPolicyUpdate(BaseModel):
    load_concurrent_users: Optional[int] = None
    load_duration_seconds: Optional[int] = None
    stress_burst_size: Optional[int] = None
    max_avg_response_ms: Optional[float] = None
    max_error_rate_pct: Optional[float] = None
    max_degradation_factor: Optional[float] = None
    target_endpoints: Optional[List[str]] = None
    require_full_pipeline_pass: Optional[bool] = None


@router.post("/deployment/policy")
async def update_deployment_policy(request: Request, body: DeploymentPolicyUpdate):
    """Update pre-deployment gate policy thresholds."""
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("deployment_policy", {**DEFAULT_DEPLOYMENT_POLICY})

    if body.load_concurrent_users is not None:
        policy["load_concurrent_users"] = max(1, min(200, body.load_concurrent_users))
    if body.load_duration_seconds is not None:
        policy["load_duration_seconds"] = max(1, min(120, body.load_duration_seconds))
    if body.stress_burst_size is not None:
        policy["stress_burst_size"] = max(1, min(500, body.stress_burst_size))
    if body.max_avg_response_ms is not None:
        policy["max_avg_response_ms"] = max(100, body.max_avg_response_ms)
    if body.max_error_rate_pct is not None:
        policy["max_error_rate_pct"] = max(0, min(100, body.max_error_rate_pct))
    if body.max_degradation_factor is not None:
        policy["max_degradation_factor"] = max(1.0, body.max_degradation_factor)
    if body.target_endpoints is not None:
        policy["target_endpoints"] = body.target_endpoints
    if body.require_full_pipeline_pass is not None:
        policy["require_full_pipeline_pass"] = body.require_full_pipeline_pass

    config["deployment_policy"] = policy
    await _save_engine_config(config)

    return {"updated": True, "deployment_policy": policy}


# ═══════════════════════════════════════════════════════════
# CANARY + SAFE ROLLOUT
# ═══════════════════════════════════════════════════════════

CANARY_STAGES = ["staging", "canary_10", "canary_25", "canary_50", "full"]
DEFAULT_CANARY_POLICY = {
    "stages": {
        "staging": {"traffic_pct": 0, "max_error_rate_pct": 1, "max_avg_latency_ms": 3000, "observe_seconds": 10},
        "canary_10": {"traffic_pct": 10, "max_error_rate_pct": 2, "max_avg_latency_ms": 4000, "observe_seconds": 15},
        "canary_25": {"traffic_pct": 25, "max_error_rate_pct": 3, "max_avg_latency_ms": 4500, "observe_seconds": 15},
        "canary_50": {"traffic_pct": 50, "max_error_rate_pct": 4, "max_avg_latency_ms": 5000, "observe_seconds": 15},
        "full": {"traffic_pct": 100, "max_error_rate_pct": 5, "max_avg_latency_ms": 5000, "observe_seconds": 0},
    },
    "auto_promote": True,
    "auto_rollback": True,
    "monitor_endpoints": [
        "/api/health",
        "/api/auth/sso-config",
        "/api/features/registry",
        "/api/system/vanity-metrics",
    ],
    "health_check_interval_seconds": 3,
    "health_check_count_per_stage": 3,
}


async def _canary_health_probe(base_url: str, endpoints: list, concurrent: int) -> dict:
    """Run a health probe against target endpoints, return latency/error metrics."""
    import aiohttp
    results = {"total": 0, "successes": 0, "failures": 0, "latencies_ms": []}

    async def _probe(session, url, acc):
        t0 = asyncio.get_event_loop().time()
        try:
            async with session.get(url) as resp:
                await resp.read()
                elapsed = (asyncio.get_event_loop().time() - t0) * 1000
                acc["total"] += 1
                acc["latencies_ms"].append(round(elapsed, 1))
                if resp.status < 500:
                    acc["successes"] += 1
                else:
                    acc["failures"] += 1
        except Exception:
            acc["total"] += 1
            acc["failures"] += 1

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
            tasks = []
            for i in range(concurrent):
                ep = endpoints[i % len(endpoints)]
                tasks.append(_probe(sess, f"{base_url}{ep}", results))
            await asyncio.gather(*tasks)
    except Exception:
        pass

    lats = results["latencies_ms"]
    return {
        "total": results["total"],
        "successes": results["successes"],
        "failures": results["failures"],
        "avg_latency_ms": round(sum(lats) / len(lats), 1) if lats else 0,
        "p95_latency_ms": round(sorted(lats)[int(len(lats) * 0.95)], 1) if lats else 0,
        "error_rate_pct": round((results["failures"] / max(results["total"], 1)) * 100, 1),
    }


async def _run_canary_stage(stage_name: str, stage_config: dict, base_url: str,
                            endpoints: list, check_interval: int, check_count: int) -> dict:
    """Execute monitoring for a single canary stage. Returns stage result with metrics."""
    observe_sec = stage_config.get("observe_seconds", 60)
    max_err = stage_config.get("max_error_rate_pct", 5)
    max_lat = stage_config.get("max_avg_latency_ms", 5000)
    traffic_pct = stage_config.get("traffic_pct", 0)

    probes = []
    stable = True
    breach_reason = None

    actual_checks = max(1, check_count) if observe_sec > 0 else 1
    interval = max(1, check_interval) if observe_sec > 0 else 0

    for i in range(actual_checks):
        concurrent = max(2, int(traffic_pct / 5)) if traffic_pct > 0 else 4
        probe = await _canary_health_probe(base_url, endpoints, concurrent)
        probes.append(probe)

        if probe["error_rate_pct"] > max_err:
            stable = False
            breach_reason = f"error_rate {probe['error_rate_pct']}% > {max_err}%"
            break
        if probe["avg_latency_ms"] > max_lat:
            stable = False
            breach_reason = f"avg_latency {probe['avg_latency_ms']}ms > {max_lat}ms"
            break

        if i < actual_checks - 1 and interval > 0:
            await asyncio.sleep(interval)

    return {
        "stage": stage_name,
        "traffic_pct": traffic_pct,
        "stable": stable,
        "breach_reason": breach_reason,
        "probes": probes,
        "probe_count": len(probes),
        "final_avg_latency_ms": probes[-1]["avg_latency_ms"] if probes else 0,
        "final_error_rate_pct": probes[-1]["error_rate_pct"] if probes else 0,
    }


@router.get("/canary/status")
async def get_canary_status(request: Request):
    """Get current canary rollout state and policy."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("canary_policy", DEFAULT_CANARY_POLICY)

    active = await db.canary_rollouts.find_one(
        {"status": {"$in": ["in_progress", "monitoring"]}},
        {"_id": 0},
        sort=[("started_at", -1)],
    )
    latest_completed = await db.canary_rollouts.find_one(
        {"status": {"$in": ["completed", "rolled_back", "failed"]}},
        {"_id": 0},
        sort=[("completed_at", -1)],
    )
    history = await db.canary_rollouts.find(
        {}, {"_id": 0}
    ).sort("started_at", -1).limit(10).to_list(10)

    return {
        "policy": policy,
        "stages": CANARY_STAGES,
        "active_rollout": active,
        "latest_completed": latest_completed,
        "history": history,
    }


@router.post("/canary/start")
async def start_canary_rollout(request: Request):
    """Initiate a new canary deployment — runs through all stages with monitoring."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("canary_policy", DEFAULT_CANARY_POLICY)
    stages_config = policy.get("stages", DEFAULT_CANARY_POLICY["stages"])
    auto_promote = policy.get("auto_promote", True)
    auto_rollback = policy.get("auto_rollback", True)
    endpoints = policy.get("monitor_endpoints", DEFAULT_CANARY_POLICY["monitor_endpoints"])
    check_interval = policy.get("health_check_interval_seconds", 5)
    check_count = policy.get("health_check_count_per_stage", 6)

    base_url = "http://localhost:8001"

    rollout_id = f"canary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    rollout = {
        "rollout_id": rollout_id,
        "status": "in_progress",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "current_stage": CANARY_STAGES[0],
        "stages_completed": [],
        "stages_results": {},
        "auto_promote": auto_promote,
        "auto_rollback": auto_rollback,
        "rollback_reason": None,
        "final_verdict": None,
    }
    await db.canary_rollouts.insert_one({**rollout})

    rolled_back = False
    for stage_name in CANARY_STAGES:
        sc = stages_config.get(stage_name, {"traffic_pct": 0, "max_error_rate_pct": 5,
                                             "max_avg_latency_ms": 5000, "observe_seconds": 30})

        stage_result = await _run_canary_stage(
            stage_name, sc, base_url, endpoints, check_interval, check_count
        )
        rollout["stages_results"][stage_name] = stage_result
        rollout["current_stage"] = stage_name

        if not stage_result["stable"]:
            if auto_rollback:
                rollout["status"] = "rolled_back"
                rollout["rollback_reason"] = f"Stage '{stage_name}' unstable: {stage_result['breach_reason']}"
                rollout["completed_at"] = datetime.now(timezone.utc).isoformat()
                rollout["final_verdict"] = "ROLLBACK"
                rolled_back = True
                await db.canary_rollouts.update_one(
                    {"rollout_id": rollout_id},
                    {"$set": {k: v for k, v in rollout.items() if k != "_id"}},
                )
                break
            else:
                rollout["status"] = "failed"
                rollout["rollback_reason"] = f"Stage '{stage_name}' unstable: {stage_result['breach_reason']}"
                rollout["completed_at"] = datetime.now(timezone.utc).isoformat()
                rollout["final_verdict"] = "FAIL"
                rolled_back = True
                await db.canary_rollouts.update_one(
                    {"rollout_id": rollout_id},
                    {"$set": {k: v for k, v in rollout.items() if k != "_id"}},
                )
                break

        rollout["stages_completed"].append(stage_name)

        if not auto_promote and stage_name != "full":
            rollout["status"] = "monitoring"
            rollout["current_stage"] = stage_name
            await db.canary_rollouts.update_one(
                {"rollout_id": rollout_id},
                {"$set": {k: v for k, v in rollout.items() if k != "_id"}},
            )
            return {k: v for k, v in rollout.items() if k != "_id"}

    if not rolled_back:
        rollout["status"] = "completed"
        rollout["completed_at"] = datetime.now(timezone.utc).isoformat()
        rollout["final_verdict"] = "DEPLOYED"
        await db.canary_rollouts.update_one(
            {"rollout_id": rollout_id},
            {"$set": {k: v for k, v in rollout.items() if k != "_id"}},
        )

    return {k: v for k, v in rollout.items() if k != "_id"}


@router.post("/canary/promote")
async def promote_canary(request: Request):
    """Manually promote current canary stage to the next stage."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("canary_policy", DEFAULT_CANARY_POLICY)
    stages_config = policy.get("stages", DEFAULT_CANARY_POLICY["stages"])
    endpoints = policy.get("monitor_endpoints", DEFAULT_CANARY_POLICY["monitor_endpoints"])
    check_interval = policy.get("health_check_interval_seconds", 5)
    check_count = policy.get("health_check_count_per_stage", 6)
    base_url = "http://localhost:8001"

    active = await db.canary_rollouts.find_one(
        {"status": {"$in": ["in_progress", "monitoring"]}},
        sort=[("started_at", -1)],
    )
    if not active:
        raise HTTPException(status_code=404, detail="No active canary rollout to promote")

    current = active.get("current_stage", "staging")
    if current not in CANARY_STAGES:
        raise HTTPException(status_code=400, detail=f"Unknown current stage: {current}")

    idx = CANARY_STAGES.index(current)
    if idx >= len(CANARY_STAGES) - 1:
        raise HTTPException(status_code=400, detail="Already at full rollout, nothing to promote")

    next_stage = CANARY_STAGES[idx + 1]
    sc = stages_config.get(next_stage, {"traffic_pct": 100, "max_error_rate_pct": 5,
                                         "max_avg_latency_ms": 5000, "observe_seconds": 30})

    stage_result = await _run_canary_stage(
        next_stage, sc, base_url, endpoints, check_interval, check_count
    )

    rollout_id = active["rollout_id"]
    stages_completed = active.get("stages_completed", [])
    stages_results = active.get("stages_results", {})
    stages_results[next_stage] = stage_result

    if not stage_result["stable"]:
        await db.canary_rollouts.update_one(
            {"rollout_id": rollout_id},
            {"$set": {
                "status": "rolled_back",
                "current_stage": next_stage,
                "stages_results": stages_results,
                "rollback_reason": f"Promote to '{next_stage}' failed: {stage_result['breach_reason']}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "final_verdict": "ROLLBACK",
            }},
        )
        return {
            "rollout_id": rollout_id, "action": "promote", "promoted_to": next_stage,
            "result": "ROLLBACK", "reason": stage_result["breach_reason"],
            "stage_result": stage_result,
        }

    stages_completed.append(next_stage)
    is_final = next_stage == "full"
    update = {
        "current_stage": next_stage,
        "stages_completed": stages_completed,
        "stages_results": stages_results,
    }
    if is_final:
        update["status"] = "completed"
        update["completed_at"] = datetime.now(timezone.utc).isoformat()
        update["final_verdict"] = "DEPLOYED"
    else:
        update["status"] = "monitoring"

    await db.canary_rollouts.update_one({"rollout_id": rollout_id}, {"$set": update})

    return {
        "rollout_id": rollout_id, "action": "promote", "promoted_to": next_stage,
        "result": "DEPLOYED" if is_final else "PROMOTED",
        "stage_result": stage_result,
    }


@router.post("/canary/rollback")
async def rollback_canary(request: Request):
    """Manually rollback current canary deployment immediately."""
    await _require_admin(request)
    db = await _db()

    active = await db.canary_rollouts.find_one(
        {"status": {"$in": ["in_progress", "monitoring"]}},
        sort=[("started_at", -1)],
    )
    if not active:
        raise HTTPException(status_code=404, detail="No active canary rollout to rollback")

    rollout_id = active["rollout_id"]
    await db.canary_rollouts.update_one(
        {"rollout_id": rollout_id},
        {"$set": {
            "status": "rolled_back",
            "rollback_reason": "Manual rollback by admin",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "final_verdict": "ROLLBACK",
        }},
    )

    return {
        "rollout_id": rollout_id,
        "action": "rollback",
        "result": "ROLLED_BACK",
        "previous_stage": active.get("current_stage"),
    }


class CanaryPolicyUpdate(BaseModel):
    auto_promote: Optional[bool] = None
    auto_rollback: Optional[bool] = None
    monitor_endpoints: Optional[List[str]] = None
    health_check_interval_seconds: Optional[int] = None
    health_check_count_per_stage: Optional[int] = None
    stages: Optional[Dict[str, Any]] = None


@router.post("/canary/policy")
async def update_canary_policy(request: Request, body: CanaryPolicyUpdate):
    """Update canary rollout policy."""
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("canary_policy", {**DEFAULT_CANARY_POLICY})

    if body.auto_promote is not None:
        policy["auto_promote"] = body.auto_promote
    if body.auto_rollback is not None:
        policy["auto_rollback"] = body.auto_rollback
    if body.monitor_endpoints is not None:
        policy["monitor_endpoints"] = body.monitor_endpoints
    if body.health_check_interval_seconds is not None:
        policy["health_check_interval_seconds"] = max(1, min(60, body.health_check_interval_seconds))
    if body.health_check_count_per_stage is not None:
        policy["health_check_count_per_stage"] = max(1, min(30, body.health_check_count_per_stage))
    if body.stages is not None:
        policy["stages"] = body.stages

    config["canary_policy"] = policy
    await _save_engine_config(config)

    return {"updated": True, "canary_policy": policy}


# ═══════════════════════════════════════════════════════════
# REALITY VALIDATION DASHBOARD ENFORCEMENT
# ═══════════════════════════════════════════════════════════


