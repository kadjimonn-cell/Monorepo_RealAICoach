"""Reality validation, monitoring, anomaly detection, feedback loop."""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import Query, Request
from pydantic import BaseModel

from routes.autonomous_engine._shared import (
    router, _db, _require_admin, _get_engine_config, _save_engine_config,
    _send_monitoring_alert_email, DEFAULT_FEEDBACK_LOOP_POLICY,
)

from services.autonomous.monitoring import (
    compute_live_metrics as _compute_live_metrics,
    detect_anomalies as _detect_anomalies,
)
from services.autonomous.feedback import feedback_issue_score as _feedback_issue_score
from routes.autonomous_engine.core_pipeline import (
    _get_reality_validation_policy, _save_reality_validation_policy,
    _run_reality_validation_evaluation, _lookup_system_memory,
    run_full_pipeline,
)
from services.autonomous.common import parse_iso_datetime as _parse_iso_datetime
from routes.autonomous_engine.memory_predictive import (
    FEATURE_STEPS,
    _create_feature_build_record,
    _run_feature_build_automation,
)

@router.get("/reality-validation/policy")
async def get_reality_validation_policy(request: Request):
    await _require_admin(request)
    return {"policy": await _get_reality_validation_policy()}


@router.post("/reality-validation/policy")
async def update_reality_validation_policy(request: Request, body: "RealityValidationPolicyUpdate"):
    admin = await _require_admin(request)
    policy = await _get_reality_validation_policy()
    payload = body.dict(exclude_none=True)
    for key, value in payload.items():
        if key in {"default_window_hours", "max_window_hours", "auto_refresh_seconds"}:
            policy[key] = int(value)
        elif key in {"required_for_every_task", "required_for_every_release", "enabled"}:
            policy[key] = bool(value)
        elif key == "required_confidence":
            policy[key] = str(value).upper().strip()

    if policy.get("required_confidence") not in {"HIGH", "MEDIUM", "LOW"}:
        policy["required_confidence"] = "HIGH"

    saved = await _save_reality_validation_policy(policy, updated_by=getattr(admin, "email", "admin"))
    return {"updated": True, "policy": saved}


@router.post("/reality-validation/run")
async def run_reality_validation(request: Request, hours: int = Query(default=24, ge=1, le=168)):
    await _require_admin(request)
    result = await _run_reality_validation_evaluation(request, window_hours=hours)
    return result


@router.get("/reality-validation/history")
async def get_reality_validation_history(request: Request, hours: int = Query(default=24, ge=1, le=168), limit: int = Query(default=20, ge=1, le=200)):
    await _require_admin(request)
    db = await _db()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await db.reality_validation_runs.find(
        {
            "$or": [
                {"created_at": {"$gte": since}},
                {"evaluated_at": {"$gte": since.isoformat()}},
            ]
        },
        {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"runs": rows, "returned": len(rows), "hours": hours}


@router.get("/reality-validation/dashboard")
async def get_reality_validation_dashboard(
    request: Request,
    hours: int = Query(default=24, ge=1, le=168),
    force_run: bool = Query(default=False),
):
    await _require_admin(request)
    db = await _db()
    policy = await _get_reality_validation_policy()
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(seconds=max(10, int(policy.get("auto_refresh_seconds", 30)) * 2))

    latest = await db.reality_validation_runs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    latest_created_raw = (latest or {}).get("created_at") if latest else None
    if isinstance(latest_created_raw, datetime):
        latest_created = latest_created_raw
        # Ensure timezone-aware for comparison
        if latest_created.tzinfo is None:
            latest_created = latest_created.replace(tzinfo=timezone.utc)
    else:
        latest_created = _parse_iso_datetime(latest_created_raw)

    should_run = bool(force_run) or not latest or not latest_created or latest_created < stale_cutoff
    if should_run and policy.get("enabled", True):
        latest = await _run_reality_validation_evaluation(request, window_hours=hours)

    history = await db.reality_validation_runs.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)

    reality_status = str((latest or {}).get("reality_status") or "FAIL").upper()
    confidence = str((latest or {}).get("confidence") or "LOW").upper()
    missing_evidence = (latest or {}).get("missing_evidence") or []

    return {
        "reality_status": reality_status,
        "confidence": confidence,
        "required_confidence": policy.get("required_confidence", "HIGH"),
        "policy": policy,
        "latest": latest,
        "recent_history": history,
        "evidence_complete": bool((latest or {}).get("evidence_complete", False)),
        "missing_evidence": missing_evidence,
        "no_fake_status_enforced": True,
        "pass_rule": {
            "all_categories_pass": bool((latest or {}).get("summary", {}).get("categories_pass", False)),
            "mandatory_scenarios_executed_and_passed": bool((latest or {}).get("mandatory_scenarios_pass", False)),
            "confidence_high_required": confidence == str(policy.get("required_confidence", "HIGH")).upper(),
            "evidence_mandatory": len(missing_evidence) == 0,
        },
    }


# ═══════════════════════════════════════════════════════════
# REAL-TIME PRODUCTION MONITORING
# ═══════════════════════════════════════════════════════════

DEFAULT_MONITOR_POLICY = {
    "window_seconds": 300,
    "latency_baseline_ms": 500,
    "latency_spike_factor": 3.0,
    "error_rate_threshold_pct": 5.0,
    "ui_crash_threshold_per_min": 10,
    "flow_dropoff_threshold_pct": 50.0,
    "auto_heal_on_anomaly": True,
    "alert_admin_on_anomaly": True,
    "max_anomaly_history": 200,
}

# In-memory rolling window for fast real-time access
_monitor_window: Dict[str, list] = {
    "api_latency": [],
    "api_errors": [],
    "ui_crashes": [],
    "user_flows": [],
}
_monitor_anomalies: list = []
_monitor_last_heal_at: Optional[str] = None


class MonitorIngestPayload(BaseModel):
    data_points: List[Dict[str, Any]]


@router.post("/monitor/ingest")
async def ingest_monitor_data(request: Request, body: MonitorIngestPayload):
    """Ingest telemetry data points: latency, errors, UI crashes, user flows."""
    await _require_admin(request)
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("monitor_policy", DEFAULT_MONITOR_POLICY)
    global _monitor_last_heal_at

    now_ts = datetime.now(timezone.utc).timestamp()
    ingested = {"api_latency": 0, "api_errors": 0, "ui_crashes": 0, "user_flows": 0}

    for dp in body.data_points:
        dp_type = dp.get("type", "")
        entry = {"ts": now_ts, **dp}

        if dp_type == "api_latency":
            _monitor_window["api_latency"].append(entry)
            ingested["api_latency"] += 1
        elif dp_type == "api_error":
            _monitor_window["api_errors"].append(entry)
            ingested["api_errors"] += 1
        elif dp_type == "ui_crash":
            _monitor_window["ui_crashes"].append(entry)
            ingested["ui_crashes"] += 1
        elif dp_type == "user_flow":
            _monitor_window["user_flows"].append(entry)
            ingested["user_flows"] += 1

    # Compute metrics and detect anomalies
    metrics = _compute_live_metrics(policy, _monitor_window)
    anomalies = _detect_anomalies(metrics, policy)

    triggered_heal = False
    if anomalies:
        for a in anomalies:
            _monitor_anomalies.append(a)
        # Trim anomaly history
        max_history = policy.get("max_anomaly_history", 200)
        while len(_monitor_anomalies) > max_history:
            _monitor_anomalies.pop(0)

        # Persist anomalies to DB
        await db.monitor_anomalies.insert_many([{**a} for a in anomalies])

        # Auto-heal trigger
        if policy.get("auto_heal_on_anomaly", True):
            _monitor_last_heal_at = datetime.now(timezone.utc).isoformat()
            triggered_heal = True
            try:
                heal_config = await _get_engine_config()
                asyncio.create_task(run_full_pipeline(heal_config, triggered_by="auto_heal_anomaly"))
            except Exception:
                pass

        # Admin alert
        if policy.get("alert_admin_on_anomaly", True):
            try:
                ", ".join(a["type"] for a in anomalies)

                # V7 compliant: use registered template
                from utils.email_templates import build_production_anomaly_alert_email
                tpl = build_production_anomaly_alert_email(
                    anomaly_count=len(anomalies),
                    anomalies=anomalies,
                    auto_heal_triggered=triggered_heal,
                )
                await _send_monitoring_alert_email(
                    recipient_email="admin@realaicoach.app",
                    subject=tpl.subject,
                    content=tpl.html,
                    template_key="production_anomaly_alert",
                    skip_branding=True,
                )
            except Exception:
                pass

    return {
        "ingested": ingested,
        "total_ingested": sum(ingested.values()),
        "anomalies_detected": len(anomalies),
        "anomalies": anomalies,
        "triggered_heal": triggered_heal,
    }


@router.get("/monitor/live")
async def get_live_metrics(request: Request):
    """Get current real-time production metrics snapshot."""
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("monitor_policy", DEFAULT_MONITOR_POLICY)

    metrics = _compute_live_metrics(policy, _monitor_window)
    anomalies = _detect_anomalies(metrics, policy)

    return {
        "metrics": metrics,
        "active_anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "last_heal_triggered_at": _monitor_last_heal_at,
        "policy": policy,
        "status": "ANOMALY" if anomalies else "HEALTHY",
    }


@router.get("/monitor/anomalies")
async def get_anomaly_history(request: Request, limit: int = Query(default=50, ge=1, le=500)):
    """Get recent anomaly history from in-memory buffer and DB."""
    await _require_admin(request)
    db = await _db()

    db_anomalies = await db.monitor_anomalies.find(
        {}, {"_id": 0}
    ).sort("detected_at", -1).limit(limit).to_list(limit)

    return {
        "anomalies": db_anomalies,
        "total_in_memory": len(_monitor_anomalies),
        "total_returned": len(db_anomalies),
    }


class MonitorPolicyUpdate(BaseModel):
    window_seconds: Optional[int] = None
    latency_baseline_ms: Optional[float] = None
    latency_spike_factor: Optional[float] = None
    error_rate_threshold_pct: Optional[float] = None
    ui_crash_threshold_per_min: Optional[int] = None
    flow_dropoff_threshold_pct: Optional[float] = None
    auto_heal_on_anomaly: Optional[bool] = None
    alert_admin_on_anomaly: Optional[bool] = None


@router.post("/monitor/policy")
async def update_monitor_policy(request: Request, body: MonitorPolicyUpdate):
    """Update real-time monitoring policy thresholds."""
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("monitor_policy", {**DEFAULT_MONITOR_POLICY})

    if body.window_seconds is not None:
        policy["window_seconds"] = max(30, min(3600, body.window_seconds))
    if body.latency_baseline_ms is not None:
        policy["latency_baseline_ms"] = max(10, body.latency_baseline_ms)
    if body.latency_spike_factor is not None:
        policy["latency_spike_factor"] = max(1.1, body.latency_spike_factor)
    if body.error_rate_threshold_pct is not None:
        policy["error_rate_threshold_pct"] = max(0.1, min(100, body.error_rate_threshold_pct))
    if body.ui_crash_threshold_per_min is not None:
        policy["ui_crash_threshold_per_min"] = max(1, body.ui_crash_threshold_per_min)
    if body.flow_dropoff_threshold_pct is not None:
        policy["flow_dropoff_threshold_pct"] = max(1, min(100, body.flow_dropoff_threshold_pct))
    if body.auto_heal_on_anomaly is not None:
        policy["auto_heal_on_anomaly"] = body.auto_heal_on_anomaly
    if body.alert_admin_on_anomaly is not None:
        policy["alert_admin_on_anomaly"] = body.alert_admin_on_anomaly

    config["monitor_policy"] = policy
    await _save_engine_config(config)

    return {"updated": True, "monitor_policy": policy}


# ═══════════════════════════════════════════════════════════
# INTELLIGENT FEEDBACK LOOP (REAL USERS)
# ═══════════════════════════════════════════════════════════

class FeedbackEventPayload(BaseModel):
    event_type: str
    route: Optional[str] = "/"
    session_id: Optional[str] = None
    target: Optional[str] = None
    duration_ms: Optional[float] = None
    interaction_count: Optional[int] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}


class FeedbackPolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    analyze_window_hours: Optional[int] = None
    min_route_views_for_detection: Optional[int] = None
    min_route_exits_for_dropoff: Optional[int] = None
    dropoff_threshold_pct: Optional[float] = None
    slow_interaction_threshold_ms: Optional[int] = None
    slow_interaction_count_threshold: Optional[int] = None
    error_count_threshold: Optional[int] = None
    interaction_bounce_ms: Optional[int] = None
    auto_create_tasks: Optional[bool] = None
    auto_run_pipeline_on_high_severity: Optional[bool] = None
    high_severity_score_threshold: Optional[int] = None
    max_event_history: Optional[int] = None
    max_task_history: Optional[int] = None


class RealityValidationPolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    default_window_hours: Optional[int] = None
    max_window_hours: Optional[int] = None
    auto_refresh_seconds: Optional[int] = None
    required_confidence: Optional[str] = None
    required_for_every_task: Optional[bool] = None
    required_for_every_release: Optional[bool] = None


async def _trim_feedback_collection(collection_name: str, max_items: int, sort_field: str):
    db = await _db()
    collection = getattr(db, collection_name)
    count = await collection.count_documents({})
    if count <= max_items:
        return
    overflow = count - max_items
    oldest = await collection.find({}, {"_id": 1}).sort(sort_field, 1).limit(overflow).to_list(overflow)
    if oldest:
        await collection.delete_many({"_id": {"$in": [item["_id"] for item in oldest]}})


async def _build_feedback_loop_summary(config: Optional[dict] = None) -> dict:
    db = await _db()
    cfg = config or await _get_engine_config()
    policy = cfg.get("feedback_loop_policy", {**DEFAULT_FEEDBACK_LOOP_POLICY})
    latest_run = await db.feedback_loop_runs.find_one({}, {"_id": 0}, sort=[("analyzed_at", -1)])
    open_tasks = await db.feedback_loop_tasks.count_documents({"status": {"$in": ["generated", "pipeline_running", "blocked", "deployable"]}})
    total_events = await db.feedback_loop_events.count_documents({})
    total_tasks = await db.feedback_loop_tasks.count_documents({})
    return {
        "enabled": bool(policy.get("enabled", True)),
        "policy": policy,
        "latest_run": latest_run,
        "stats": {
            "total_events": total_events,
            "total_tasks": total_tasks,
            "open_tasks": open_tasks,
        },
    }


async def _execute_feedback_task_pipeline(task_id: str, feature_id: str):
    db = await _db()
    try:
        pipeline_result = await _run_feature_build_automation(feature_id, max_steps=len(FEATURE_STEPS))
        final_feature = pipeline_result.get("final_feature") or {}
        status = "deployable" if final_feature.get("status") == "completed" else final_feature.get("status", "pipeline_running")
        await db.feedback_loop_tasks.update_one(
            {"task_id": task_id},
            {"$set": {
                "pipeline_result": pipeline_result.get("latest_result"),
                "status": status,
                "pipeline_finished_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    except Exception as exc:
        await db.feedback_loop_tasks.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": "pipeline_error",
                "pipeline_result": {"status": "FAIL", "error": str(exc)[:240]},
                "pipeline_finished_at": datetime.now(timezone.utc).isoformat(),
            }},
        )


async def _generate_feedback_task(issue: dict, policy: dict, triggered_by: str, allow_pipeline_auto_run: bool = True) -> dict:
    db = await _db()
    signature = f"{issue['issue_type']}::{issue.get('route', 'global')}"
    memory_lookup = await _lookup_system_memory(
        task_type="feedback_task_generation",
        signature=signature,
        context={"issue": issue, "triggered_by": triggered_by},
        categories=["failure", "fix", "test_pattern", "optimization"],
    )
    best_memory = (memory_lookup.get("matches") or [None])[0]
    existing = await db.feedback_loop_tasks.find_one(
        {"signature": signature, "status": {"$in": ["generated", "pipeline_running", "blocked", "deployable"]}},
        {"_id": 0},
        sort=[("generated_at", -1)],
    )
    if existing:
        return {"created": False, "task": existing}

    task_id = f"feedback_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    title = issue.get("title") or f"Feedback loop: improve {issue.get('route', 'user flow')}"
    description = issue.get("description") or "Auto-generated from real-user friction detection"
    if best_memory and best_memory.get("solution_summary"):
        description = f"{description} | Memory-reused solution: {best_memory.get('solution_summary')}"
    feature = await _create_feature_build_record(
        name=title,
        description=description,
        owner="feedback_loop",
        test_files=[],
        extra_fields={
            "source": "feedback_loop",
            "source_signature": signature,
            "feedback_task_id": task_id,
            "feedback_issue": issue,
            "memory_lookup": memory_lookup,
        },
    )

    task = {
        "task_id": task_id,
        "signature": signature,
        "issue_type": issue.get("issue_type"),
        "route": issue.get("route"),
        "severity": issue.get("severity"),
        "score": issue.get("score"),
        "title": title,
        "description": description,
        "evidence": issue.get("evidence", {}),
        "feature_id": feature.get("feature_id"),
        "status": "generated",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "triggered_by": triggered_by,
        "memory_lookup": memory_lookup,
        "pipeline_auto_run": False,
        "pipeline_result": None,
    }
    await db.feedback_loop_tasks.insert_one({**task})

    if allow_pipeline_auto_run and policy.get("auto_run_pipeline_on_high_severity", True) and int(issue.get("score", 0)) >= int(policy.get("high_severity_score_threshold", 80)):
        task["pipeline_auto_run"] = True
        task["status"] = "pipeline_running"
        await db.feedback_loop_tasks.update_one(
            {"task_id": task_id},
            {"$set": {
                "pipeline_auto_run": True,
                "status": task["status"],
            }},
        )
        asyncio.create_task(_execute_feedback_task_pipeline(task_id, feature.get("feature_id")))

    await _trim_feedback_collection("feedback_loop_tasks", int(policy.get("max_task_history", 250)), "generated_at")
    return {"created": True, "task": task}


async def run_feedback_loop_analysis(triggered_by: str = "manual") -> dict:
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("feedback_loop_policy", {**DEFAULT_FEEDBACK_LOOP_POLICY})
    analyzed_at = datetime.now(timezone.utc).isoformat()
    run_id = f"feedback_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    if not policy.get("enabled", True):
        return {
            "mode": "INTELLIGENT_FEEDBACK_LOOP",
            "run_id": run_id,
            "analyzed_at": analyzed_at,
            "triggered_by": triggered_by,
            "status": "DISABLED",
            "friction_detected": [],
            "generated_tasks": [],
        }

    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=int(policy.get("analyze_window_hours", 24)))
    events = await db.feedback_loop_events.find(
        {"recorded_at": {"$gte": cutoff_dt.isoformat()}},
        {"_id": 0},
    ).sort("recorded_at", -1).to_list(5000)

    route_stats: Dict[str, dict] = {}
    target_stats: Dict[str, int] = {}
    for event in events:
        route = str(event.get("route") or "/")
        bucket = route_stats.setdefault(route, {
            "views": 0,
            "exits": 0,
            "dropoffs": 0,
            "interactions": 0,
            "slow_interactions": 0,
            "slowest_ms": 0,
            "errors": 0,
        })
        event_type = str(event.get("event_type") or "")
        if event_type == "page_view":
            bucket["views"] += 1
        elif event_type == "route_exit":
            bucket["exits"] += 1
            duration_ms = float(event.get("duration_ms") or 0)
            interaction_count = int(event.get("interaction_count") or 0)
            if interaction_count <= 0 or (duration_ms > 0 and duration_ms < int(policy.get("interaction_bounce_ms", 20000))):
                bucket["dropoffs"] += 1
        elif event_type == "interaction":
            bucket["interactions"] += 1
            duration_ms = float(event.get("duration_ms") or 0)
            if duration_ms >= float(policy.get("slow_interaction_threshold_ms", 1200)):
                bucket["slow_interactions"] += 1
                bucket["slowest_ms"] = max(bucket["slowest_ms"], duration_ms)
            target = str(event.get("target") or "").strip()
            if target:
                target_stats[target] = target_stats.get(target, 0) + 1
        elif event_type == "error":
            bucket["errors"] += 1

    friction_detected = []
    for route, stats in route_stats.items():
        exits = max(stats["exits"], 1)
        dropoff_pct = round((stats["dropoffs"] / exits) * 100, 1) if stats["exits"] else 0.0
        if stats["views"] >= int(policy.get("min_route_views_for_detection", 8)) and stats["exits"] >= int(policy.get("min_route_exits_for_dropoff", 5)) and dropoff_pct >= float(policy.get("dropoff_threshold_pct", 55.0)):
            score = _feedback_issue_score("route_dropoff", dropoff_pct, float(policy.get("dropoff_threshold_pct", 55.0)))
            friction_detected.append({
                "issue_type": "route_dropoff",
                "route": route,
                "score": score,
                "severity": "high" if score >= 80 else "medium",
                "title": f"Reduce drop-off on {route}",
                "description": f"Real users are dropping off on {route}. Improve clarity, speed, or flow completion.",
                "evidence": {"views": stats["views"], "exits": stats["exits"], "dropoff_pct": dropoff_pct},
            })
        if stats["slow_interactions"] >= int(policy.get("slow_interaction_count_threshold", 5)):
            score = _feedback_issue_score("slow_interaction", stats["slow_interactions"], float(policy.get("slow_interaction_count_threshold", 5)))
            friction_detected.append({
                "issue_type": "slow_interaction",
                "route": route,
                "score": score,
                "severity": "high" if score >= 80 else "medium",
                "title": f"Speed up interactions on {route}",
                "description": f"Users are experiencing slow interactions on {route}. Investigate UI responsiveness and network latency.",
                "evidence": {"slow_interactions": stats["slow_interactions"], "slowest_ms": stats["slowest_ms"]},
            })
        if stats["errors"] >= int(policy.get("error_count_threshold", 4)):
            score = _feedback_issue_score("runtime_errors", stats["errors"], float(policy.get("error_count_threshold", 4)))
            friction_detected.append({
                "issue_type": "runtime_errors",
                "route": route,
                "score": score,
                "severity": "high" if score >= 80 else "medium",
                "title": f"Fix real-user errors on {route}",
                "description": f"Users are hitting repeated runtime errors on {route}. Prioritize stabilization.",
                "evidence": {"errors": stats["errors"]},
            })

    friction_detected = sorted(friction_detected, key=lambda item: item.get("score", 0), reverse=True)
    generated_tasks = []
    if policy.get("auto_create_tasks", True):
        for index, issue in enumerate(friction_detected[:5]):
            generated_tasks.append(await _generate_feedback_task(issue, policy, triggered_by, allow_pipeline_auto_run=index == 0))

    run_doc = {
        "run_id": run_id,
        "mode": "INTELLIGENT_FEEDBACK_LOOP",
        "analyzed_at": analyzed_at,
        "triggered_by": triggered_by,
        "status": "FRICTION_DETECTED" if friction_detected else "STABLE",
        "behavior_summary": {
            "top_routes": sorted(
                [{"route": route, "views": stats["views"], "interactions": stats["interactions"]} for route, stats in route_stats.items()],
                key=lambda item: item["views"],
                reverse=True,
            )[:5],
            "top_targets": sorted(
                [{"target": target, "count": count} for target, count in target_stats.items()],
                key=lambda item: item["count"],
                reverse=True,
            )[:5],
        },
        "friction_detected": friction_detected,
        "generated_tasks": [{"created": t.get("created"), "task_id": (t.get("task") or {}).get("task_id"), "feature_id": (t.get("task") or {}).get("feature_id"), "status": (t.get("task") or {}).get("status")} for t in generated_tasks],
        "event_count": len(events),
    }
    await db.feedback_loop_runs.insert_one({**run_doc})
    await _trim_feedback_collection("feedback_loop_runs", 200, "analyzed_at")
    return run_doc


@router.post("/feedback/collect")
async def collect_feedback_signal(body: FeedbackEventPayload):
    """Collect real-user telemetry signals across all current frontend routes."""
    db = await _db()
    config = await _get_engine_config()
    policy = config.get("feedback_loop_policy", {**DEFAULT_FEEDBACK_LOOP_POLICY})
    if not policy.get("enabled", True):
        return {"accepted": False, "reason": "feedback_loop_disabled"}

    recorded_at = datetime.now(timezone.utc).isoformat()
    event = {
        "event_type": str(body.event_type or "").strip().lower(),
        "route": str(body.route or "/").strip() or "/",
        "session_id": str(body.session_id or "anonymous").strip() or "anonymous",
        "target": str(body.target or "").strip()[:160],
        "duration_ms": round(float(body.duration_ms or 0), 1) if body.duration_ms is not None else None,
        "interaction_count": int(body.interaction_count or 0) if body.interaction_count is not None else 0,
        "error_message": str(body.error_message or "").strip()[:300],
        "metadata": body.metadata or {},
        "recorded_at": recorded_at,
    }
    await db.feedback_loop_events.insert_one({**event})
    await _trim_feedback_collection("feedback_loop_events", int(policy.get("max_event_history", 10000)), "recorded_at")

    now_ts = datetime.now(timezone.utc).timestamp()
    if event["event_type"] == "error":
        _monitor_window["ui_crashes"].append({"ts": now_ts, "type": "ui_crash", "route": event["route"], "error": event.get("error_message")})
    elif event["event_type"] == "route_exit":
        _monitor_window["user_flows"].append({
            "ts": now_ts,
            "type": "user_flow",
            "route": event["route"],
            "completed": bool(event.get("interaction_count", 0) > 0 and (event.get("duration_ms") or 0) >= int(policy.get("interaction_bounce_ms", 20000))),
        })

    return {"accepted": True, "recorded_at": recorded_at, "event_type": event["event_type"]}


@router.get("/feedback/status")
async def get_feedback_loop_status(request: Request):
    await _require_admin(request)
    config = await _get_engine_config()
    return {"mode": "INTELLIGENT_FEEDBACK_LOOP", **(await _build_feedback_loop_summary(config))}


@router.post("/feedback/analyze")
async def analyze_feedback_now(request: Request):
    await _require_admin(request)
    return await run_feedback_loop_analysis(triggered_by="admin_manual")


@router.get("/feedback/tasks")
async def list_feedback_tasks(request: Request, limit: int = Query(default=30, ge=1, le=200)):
    await _require_admin(request)
    db = await _db()
    tasks = await db.feedback_loop_tasks.find({}, {"_id": 0}).sort("generated_at", -1).limit(limit).to_list(limit)
    return {"tasks": tasks, "returned": len(tasks)}


@router.post("/feedback/policy")
async def update_feedback_policy(request: Request, body: FeedbackPolicyUpdate):
    await _require_admin(request)
    config = await _get_engine_config()
    policy = config.get("feedback_loop_policy", {**DEFAULT_FEEDBACK_LOOP_POLICY})
    for field in body.model_dump(exclude_none=True):
        policy[field] = getattr(body, field)
    config["feedback_loop_policy"] = policy
    await _save_engine_config(config)
    return {"updated": True, "feedback_loop_policy": (await _get_engine_config()).get("feedback_loop_policy")}


