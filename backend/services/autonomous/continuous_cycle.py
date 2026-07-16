import asyncio
import hashlib
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

import aiohttp


DEFAULT_CONTINUOUS_POLICY = {
    "interval_minutes": 30,
    "health_check_endpoints": [
        "/api/health",
        "/api/auth/sso-config",
        "/api/features/registry",
        "/api/system/vanity-metrics",
    ],
    "latency_samples_per_endpoint": 3,
    "latency_spike_threshold_ms": 1500,
    "error_rate_threshold_pct": 5.0,
    "run_tests_check": True,
    "auto_heal_enabled": True,
    "alert_on_anomaly": True,
    "forever_loop_enabled": True,
    "forever_loop_deploy_release_monitor": True,
    "forever_loop_learn_to_memory": True,
    "max_history": 500,
}


FOREVER_LOOP_STEPS = [
    "Monitor",
    "Detect",
    "Fix",
    "Test",
    "Validate",
    "Optimize",
    "Deploy",
    "Learn",
    "Repeat",
]


async def _learn_from_cycle(db, *, cycle_id: str, status: str, anomalies: list, phases: dict, enabled: bool) -> dict:
    if not enabled:
        return {"stored": False, "reason": "learning_disabled"}

    now_iso = datetime.now(timezone.utc).isoformat()
    memory_type = "failure" if anomalies and status == "FAIL" else ("fix" if status == "HEALED" else "optimization")
    signature = f"forever_loop::{memory_type}::{len(anomalies)}"
    solution = (
        "Reuse drift + feedback + release monitor triage before promoting deployment."
        if anomalies
        else "Reuse stable forever-loop execution profile and maintain current thresholds."
    )
    memory_id = f"mem_{hashlib.sha1(f'{signature}|{solution}'.encode('utf-8')).hexdigest()[:16]}"

    await db.system_knowledge_memory.update_one(
        {"memory_id": memory_id},
        {
            "$set": {
                "memory_id": memory_id,
                "memory_type": memory_type,
                "signature": signature,
                "problem_summary": f"Forever loop cycle {cycle_id} ended with {status} and {len(anomalies)} anomalies",
                "solution_summary": solution,
                "source": "forever_loop",
                "tags": ["forever_loop", "continuous", status.lower()],
                "tokens": ["forever", "loop", "continuous", status.lower()],
                "confidence_score": 0.68 if status != "FAIL" else 0.72,
                "active": True,
                "updated_at": now_iso,
                "evidence": {
                    "cycle_id": cycle_id,
                    "status": status,
                    "anomaly_count": len(anomalies),
                    "phase_keys": list((phases or {}).keys()),
                },
            },
            "$setOnInsert": {
                "created_at": now_iso,
                "reuse_count": 0,
            },
        },
        upsert=True,
    )

    return {"stored": True, "memory_id": memory_id, "memory_type": memory_type}


async def run_continuous_cycle_core(
    *,
    db,
    config: dict,
    triggered_by: str,
    run_tests_gate: Callable[[], Awaitable[dict]],
    run_drift_detection: Callable[..., Awaitable[dict]],
    run_feedback_loop_analysis: Callable[..., Awaitable[dict]],
    get_engine_config: Callable[[], Awaitable[dict]],
    run_full_pipeline: Callable[..., Awaitable[dict]],
    run_release_intelligence_monitor: Optional[Callable[..., Awaitable[dict]]] = None,
    auto_log_failure: Optional[Callable[..., Awaitable[dict]]] = None,
) -> dict:
    policy = config.get("continuous_policy", DEFAULT_CONTINUOUS_POLICY)
    now_iso = datetime.now(timezone.utc).isoformat()
    cycle_id = f"cycle_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    anomalies = []
    healed = False
    phases: Dict[str, Any] = {}

    base_url = "http://localhost:8001"
    endpoints = policy.get("health_check_endpoints", DEFAULT_CONTINUOUS_POLICY["health_check_endpoints"])
    samples_per = int(policy.get("latency_samples_per_endpoint", 3))
    spike_threshold = float(policy.get("latency_spike_threshold_ms", 1500))
    err_threshold = float(policy.get("error_rate_threshold_pct", 5.0))

    api_results = {}
    total_reqs = 0
    total_errors = 0
    all_latencies = []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sess:
            for ep in endpoints:
                lats = []
                ep_errors = 0
                for _ in range(samples_per):
                    t0 = asyncio.get_event_loop().time()
                    try:
                        async with sess.get(f"{base_url}{ep}") as resp:
                            await resp.read()
                            elapsed = round((asyncio.get_event_loop().time() - t0) * 1000, 1)
                            lats.append(elapsed)
                            total_reqs += 1
                            if resp.status >= 500:
                                ep_errors += 1
                                total_errors += 1
                    except Exception:
                        total_reqs += 1
                        total_errors += 1
                        ep_errors += 1
                all_latencies.extend(lats)
                avg = round(sum(lats) / len(lats), 1) if lats else 0
                api_results[ep] = {"avg_ms": avg, "samples": len(lats), "errors": ep_errors}
                if avg > spike_threshold:
                    anomalies.append({"type": "latency_spike", "endpoint": ep, "avg_ms": avg, "threshold": spike_threshold})
    except Exception as exc:
        phases["health_error"] = str(exc)[:200]

    overall_avg = round(sum(all_latencies) / len(all_latencies), 1) if all_latencies else 0
    error_rate = round((total_errors / max(total_reqs, 1)) * 100, 1)
    if error_rate > err_threshold:
        anomalies.append({"type": "error_rate_spike", "rate_pct": error_rate, "threshold": err_threshold})

    phases["health_check"] = {
        "status": "PASS" if not any(a["type"] in ("latency_spike", "error_rate_spike") for a in anomalies) else "FAIL",
        "overall_avg_ms": overall_avg,
        "error_rate_pct": error_rate,
        "endpoints": api_results,
    }

    tests_result = None
    if policy.get("run_tests_check", True):
        try:
            tests_result = await run_tests_gate()
            tests_passed = tests_result.get("status") == "PASS"
            phases["test_drift"] = {
                "status": "PASS" if tests_passed else "FAIL",
                "tests_status": tests_result.get("status"),
                "issues": tests_result.get("issues", [])[:3],
            }
            if not tests_passed:
                anomalies.append({"type": "test_drift", "detail": "; ".join(tests_result.get("issues", [])[:2])})
        except Exception as exc:
            phases["test_drift"] = {"status": "ERROR", "error": str(exc)[:200]}
    else:
        phases["test_drift"] = {"status": "SKIP"}

    try:
        baseline_audits = await db.perf_audit_history.find(
            {"api_overall_avg_ms": {"$exists": True, "$gt": 0}},
            {"_id": 0, "api_overall_avg_ms": 1, "bundle_size_mb": 1},
        ).sort("audited_at", -1).limit(5).to_list(5)

        perf_degraded = False
        if baseline_audits and overall_avg > 0:
            hist_avg = sum(a["api_overall_avg_ms"] for a in baseline_audits) / len(baseline_audits)
            if hist_avg > 0 and overall_avg > hist_avg * 2:
                perf_degraded = True
                anomalies.append(
                    {
                        "type": "perf_degradation",
                        "current_ms": overall_avg,
                        "historical_ms": round(hist_avg, 1),
                        "factor": round(overall_avg / hist_avg, 2),
                    }
                )

        phases["perf_budget"] = {
            "status": "FAIL" if perf_degraded else "PASS",
            "current_avg_ms": overall_avg,
            "historical_avg_ms": round(sum(a["api_overall_avg_ms"] for a in baseline_audits) / len(baseline_audits), 1)
            if baseline_audits
            else None,
        }
    except Exception as exc:
        phases["perf_budget"] = {"status": "ERROR", "error": str(exc)[:200]}

    drift_result = await run_drift_detection(
        triggered_by=f"continuous:{triggered_by}",
        current_perf_snapshot={
            "api_overall_avg_ms": overall_avg,
            "status": "ALERT" if any(a.get("type") in ("latency_spike", "error_rate_spike", "perf_degradation") for a in anomalies) else "HEALTHY",
            "api_metrics": api_results,
        },
        current_tests_result=tests_result,
        auto_optimize=True,
    )
    phases["drift_detection"] = {
        "status": drift_result.get("status"),
        "detected": drift_result.get("detected", False),
        "signal_count": len(drift_result.get("signals", [])),
        "auto_optimized": drift_result.get("auto_optimized", False),
        "restored": drift_result.get("restored", False),
        "event_id": drift_result.get("event_id"),
    }
    if drift_result.get("detected"):
        for signal in drift_result.get("signals", []):
            anomalies.append(
                {
                    "type": signal.get("type", "drift_detected"),
                    "source": signal.get("source"),
                    "detail": str(signal)[:220],
                }
            )

    feedback_result = await run_feedback_loop_analysis(triggered_by=f"continuous:{triggered_by}")
    phases["feedback_loop"] = {
        "status": feedback_result.get("status"),
        "event_count": feedback_result.get("event_count", 0),
        "friction_count": len(feedback_result.get("friction_detected", [])),
        "generated_tasks": len(feedback_result.get("generated_tasks", [])),
        "run_id": feedback_result.get("run_id"),
    }

    if drift_result.get("auto_optimized"):
        healed = bool(drift_result.get("restored", False))
        phases["auto_heal"] = {
            "triggered": True,
            "source": "drift_detection",
            "anomalies_count": len(anomalies),
            "retest_status": ((drift_result.get("revalidation") or {}).get("tests") or {}).get("status", "UNKNOWN"),
            "restored": bool(drift_result.get("restored", False)),
            "pipeline_status": ((drift_result.get("optimization") or {}).get("pipeline_status")),
        }
    elif anomalies and policy.get("auto_heal_enabled", True):
        try:
            heal_config = await get_engine_config()
            await run_full_pipeline(heal_config, triggered_by="continuous_auto_heal")
            healed = True
            retest = await run_tests_gate()
            phases["auto_heal"] = {
                "triggered": True,
                "anomalies_count": len(anomalies),
                "retest_status": retest.get("status", "UNKNOWN"),
                "restored": retest.get("status") == "PASS",
            }

            if auto_log_failure is not None:
                for anomaly in anomalies:
                    asyncio.ensure_future(
                        auto_log_failure(
                            failure_type="continuous_cycle_anomaly",
                            component=anomaly.get("endpoint", anomaly.get("type", "unknown")),
                            error_signature=str(anomaly)[:200],
                            root_cause=anomaly.get("detail", anomaly.get("type", "")),
                            context={"cycle_id": cycle_id},
                        )
                    )
        except Exception as exc:
            phases["auto_heal"] = {"triggered": True, "error": str(exc)[:200], "restored": False}
    else:
        phases["auto_heal"] = {"triggered": False}

    if anomalies and policy.get("alert_on_anomaly", True):
        try:

            anom_lines = "".join(
                f"<p style='margin:3px 0;color:#334155;font-size:12px'>- <strong>{a.get('type')}</strong>: {str({k: v for k, v in a.items() if k != 'type'})[:80]}</p>"
                for a in anomalies[:5]
            )
            (
                "<div class='em-force-light-card' style='font-family:Inter,sans-serif;padding:16px;background:#FFFFFF;border:1px solid #FECACA;border-radius:10px'>"
                f"<h3 class='em-force-dark-text' style='margin:0 0 8px;color:#B91C1C'>24/7 Cycle Anomaly — {cycle_id}</h3>"
                f"<p class='em-force-muted-text' style='margin:0 0 6px;color:#475569;font-size:13px'>{len(anomalies)} anomaly(s) detected</p>"
                f"{anom_lines}"
                f"<p style='margin:8px 0 0;color:{'#059669' if healed else '#DC2626'};font-size:12px;font-weight:700'>Auto-heal: {'Triggered + Re-tested' if healed else 'Not triggered'}</p>"
                "</div>"
            )
            admin_email = os.environ.get("ADMIN_EMAILS", "").split(",")[0].strip()
            if not admin_email:
                pass
            else:
                from utils.email_service import send_catalog_template
                await send_catalog_template(
                    recipient_email=admin_email,
                    template_key="system_alert_admin",
                    alert_type="24/7 Anomaly Detection",
                    severity="HIGH",
                    description=f"{len(anomalies)} anomaly(s) detected at {now_iso[:16]}",
                    component="Autonomous Continuous Cycle",
                )
        except Exception:
            pass

    overall_status = "PASS" if not anomalies else ("HEALED" if healed and phases.get("auto_heal", {}).get("restored") else "FAIL")

    deploy_result = {"status": "SKIP", "reason": "release_monitor_not_requested"}
    if policy.get("forever_loop_deploy_release_monitor", True) and run_release_intelligence_monitor is not None:
        try:
            monitor_res = await run_release_intelligence_monitor(trigger="continuous_forever_loop")
            deploy_result = {
                "status": "PASS",
                "evaluated": monitor_res.get("evaluated", 0),
                "stable": monitor_res.get("stable", 0),
                "rolled_back": monitor_res.get("rolled_back", 0),
                "run_at": monitor_res.get("run_at"),
            }
        except Exception as exc:
            deploy_result = {"status": "FAIL", "error": str(exc)[:180]}

    learn_result = await _learn_from_cycle(
        db,
        cycle_id=cycle_id,
        status=overall_status,
        anomalies=anomalies,
        phases=phases,
        enabled=bool(policy.get("forever_loop_learn_to_memory", True)),
    )

    monitor_status = "PASS" if phases.get("health_check", {}).get("status") == "PASS" else "FAIL"
    detect_status = "DETECTED" if anomalies else "PASS"
    fix_status = "SKIP" if not anomalies else ("PASS" if phases.get("auto_heal", {}).get("restored") else "FAIL")
    test_status = phases.get("test_drift", {}).get("status", "UNKNOWN")
    validate_status = "PASS" if overall_status in {"PASS", "HEALED"} else "FAIL"
    optimize_status = "PASS" if phases.get("drift_detection", {}).get("status") in {"PASS", "RESTORED"} else (
        "FAIL" if phases.get("drift_detection", {}).get("detected") else "PASS"
    )
    deploy_status = deploy_result.get("status", "SKIP")
    learn_status = "PASS" if learn_result.get("stored") else "SKIP"
    repeat_status = "PASS"
    next_run_at = (datetime.now(timezone.utc) + timedelta(minutes=int(policy.get("interval_minutes", 30)))).isoformat()

    forever_loop = {
        "enabled": bool(policy.get("forever_loop_enabled", True)),
        "steps": FOREVER_LOOP_STEPS,
        "stages": [
            {"name": "Monitor", "status": monitor_status},
            {"name": "Detect", "status": detect_status, "anomalies": len(anomalies)},
            {"name": "Fix", "status": fix_status},
            {"name": "Test", "status": test_status},
            {"name": "Validate", "status": validate_status},
            {"name": "Optimize", "status": optimize_status},
            {"name": "Deploy", "status": deploy_status, "details": deploy_result},
            {"name": "Learn", "status": learn_status, "details": learn_result},
            {"name": "Repeat", "status": repeat_status, "next_run_at": next_run_at},
        ],
        "next_run_at": next_run_at,
    }

    cycle = {
        "cycle_id": cycle_id,
        "executed_at": now_iso,
        "triggered_by": triggered_by,
        "status": overall_status,
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "healed": healed,
        "phases": phases,
        "overall_avg_ms": overall_avg,
        "error_rate_pct": error_rate,
        "forever_loop": forever_loop,
    }
    await db.continuous_cycle_history.insert_one({**cycle})

    max_hist = policy.get("max_history", 500)
    count = await db.continuous_cycle_history.count_documents({})
    if count > max_hist:
        over = count - max_hist
        oldest = await db.continuous_cycle_history.find({}, {"_id": 1}).sort("executed_at", 1).limit(over).to_list(over)
        if oldest:
            await db.continuous_cycle_history.delete_many({"_id": {"$in": [o["_id"] for o in oldest]}})

    return cycle
