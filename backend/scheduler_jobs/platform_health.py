"""
scheduler_jobs.platform_health — Platform-wide health, integrity, and autonomous-cycle jobs.

**Phase 2 incremental domain split — batch #23.**

Owns the continuous platform-health pipeline: cache freshness,
growth-integrity monitor, global UX assurance, the 24/7 autonomous
cycle, validity autofix refresh, and predictive failure prevention.

Jobs in this module
===================
- ``scheduled_platform_cache_freshness_guard`` — continuous
  frontend/backend cache freshness guard with auto-fix + runtime
  state, disk-pressure cleanup, and notification-on-warning.
- ``scheduled_growth_integrity_monitor`` — continuous anomaly /
  payment integrity monitor.
- ``scheduled_global_experience_assurance`` — continuous platform-wide
  UX/API/link/cache assurance with auto-remediation.
- ``scheduled_continuous_cycle`` — 24/7 continuous autonomous cycle.
- ``scheduled_validity_autofix_refresh`` — auto-fix run keeping strict
  hard-gate validity fresh.
- ``scheduled_predictive_failure_prevention`` — predicts likely
  failures ahead of impact and preemptively mitigates.

Internal helpers
================
- ``_trim_validity_autofix_history`` — keep validity-autofix-runs
  collection bounded.
"""

import logging
import os
import shlex
import shutil
import subprocess
import uuid
from datetime import datetime, timezone

from scheduler_jobs.admin_context import _get_scheduler_admin_context
from scheduler_jobs.observability import _record_scheduler_heartbeat


logger = logging.getLogger("scheduler_jobs.platform_health")

FRONTEND_EXPORT_LOCKFILE = "/tmp/frontend_export_build.lock"
FRONTEND_EXPORT_NODE_OPTIONS = str(
    os.environ.get("FRONTEND_EXPORT_NODE_OPTIONS") or "--max-old-space-size=3072"
).strip()


async def scheduled_platform_cache_freshness_guard():
    """Continuous frontend/backend cache freshness guard with auto-fix + runtime state."""
    job_id = "platform_cache_freshness_guard"
    try:
        from routes.db import db
        from routes import platform_health as platform_health_routes

        now_iso = datetime.now(timezone.utc).isoformat()
        min_free_mb = int(os.environ.get("PLATFORM_DISK_PRESSURE_MIN_FREE_MB", "250") or 250)

        def _clear_dir_contents(target: str) -> bool:
            if not os.path.isdir(target):
                return False
            cleared_any = False
            for entry in os.listdir(target):
                full = os.path.join(target, entry)
                try:
                    if os.path.isdir(full):
                        shutil.rmtree(full, ignore_errors=True)
                    else:
                        os.remove(full)
                    cleared_any = True
                except Exception:
                    continue
            return cleared_any

        usage_before = shutil.disk_usage("/app")
        disk_free_mb = round(float(usage_before.free) / (1024 * 1024), 2)
        disk_pressure = bool(usage_before.free < (min_free_mb * 1024 * 1024))
        auto_cleaned_paths: list[str] = []

        if disk_pressure:
            for cleanup_target in [
                "/app/frontend/.metro-cache",
                "/app/frontend/test-results",
                "/app/frontend/playwright-report",
                "/app/.screenshots",
                "/app/frontend/.screenshots",
                "/app/tmp",
            ]:
                if _clear_dir_contents(cleanup_target):
                    auto_cleaned_paths.append(cleanup_target)

            usage_after = shutil.disk_usage("/app")
            disk_free_mb = round(float(usage_after.free) / (1024 * 1024), 2)
            disk_pressure = bool(usage_after.free < (min_free_mb * 1024 * 1024))

        stale_urls = platform_health_routes._scan_files_for_patterns(
            [platform_health_routes.FRONTEND_SRC, platform_health_routes.FRONTEND_APP],
            platform_health_routes.STALE_URL_PATTERNS,
            [".tsx", ".ts", ".js", ".jsx"],
        )
        cache_health = platform_health_routes._check_cache_health()
        stale_caches = [c for c in cache_health if c.get("stale")]
        build_info = platform_health_routes._check_build_staleness()

        rebuilt_frontend = False
        rebuild_feature_enabled = str(
            os.environ.get("PLATFORM_CACHE_GUARD_ENABLE_REBUILD") or "0"
        ).strip() == "1"
        if bool(build_info.get("stale")) and bool(build_info.get("source_newer_than_build")):
            build_meta = await db.system_runtime_flags.find_one(
                {"key": "frontend_build_auto_refresh_meta"},
                {"_id": 0},
            ) or {}
            last_run_at = str((build_meta.get("value") or {}).get("last_run_at") or "")
            should_rebuild = True
            if last_run_at:
                try:
                    last_dt = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    should_rebuild = (datetime.now(timezone.utc) - last_dt).total_seconds() >= 3600
                except Exception:
                    should_rebuild = True

            if should_rebuild and rebuild_feature_enabled:
                try:
                    export_cmd = (
                        "cd /app/frontend && "
                        f"CI=1 EXPO_NO_INTERACTIVE=1 NODE_OPTIONS={shlex.quote(FRONTEND_EXPORT_NODE_OPTIONS)} "
                        "node node_modules/expo/bin/cli export --platform web"
                    )
                    lock_cmd = f"flock -n {shlex.quote(FRONTEND_EXPORT_LOCKFILE)} -c {shlex.quote(export_cmd)}"
                    build_proc = subprocess.run(
                        ["bash", "-lc", lock_cmd],
                        capture_output=True,
                        text=True,
                        timeout=420,
                    )
                    rebuilt_frontend = build_proc.returncode == 0
                    lock_busy = (
                        build_proc.returncode != 0
                        and "failed to get lock" in str(build_proc.stderr or "").lower()
                    )
                    await db.system_runtime_flags.update_one(
                        {"key": "frontend_build_auto_refresh_meta"},
                        {
                            "$set": {
                                "key": "frontend_build_auto_refresh_meta",
                                "value": {
                                    "last_run_at": now_iso,
                                    "success": rebuilt_frontend,
                                    "lock_busy": lock_busy,
                                    "stdout_tail": (build_proc.stdout or "")[-800:],
                                    "stderr_tail": (build_proc.stderr or "")[-800:],
                                },
                                "updated_at": now_iso,
                            }
                        },
                        upsert=True,
                    )
                    if rebuilt_frontend:
                        build_info = platform_health_routes._check_build_staleness()
                except Exception as build_exc:
                    await db.system_runtime_flags.update_one(
                        {"key": "frontend_build_auto_refresh_meta"},
                        {
                            "$set": {
                                "key": "frontend_build_auto_refresh_meta",
                                "value": {
                                    "last_run_at": now_iso,
                                    "success": False,
                                    "error": str(build_exc),
                                },
                                "updated_at": now_iso,
                            }
                        },
                        upsert=True,
                    )
            elif should_rebuild and not rebuild_feature_enabled:
                await db.system_runtime_flags.update_one(
                    {"key": "frontend_build_auto_refresh_meta"},
                    {
                        "$set": {
                            "key": "frontend_build_auto_refresh_meta",
                            "value": {
                                "last_run_at": now_iso,
                                "success": False,
                                "disabled": True,
                                "reason": "PLATFORM_CACHE_GUARD_ENABLE_REBUILD is not enabled",
                            },
                            "updated_at": now_iso,
                        }
                    },
                    upsert=True,
                )

        url_fix = {"fixed_count": 0, "fixed": [], "failed": []}
        if stale_urls:
            url_fix = platform_health_routes._auto_fix_stale_urls(stale_urls)

        cleared_caches = []
        if stale_caches:
            cleared_caches = platform_health_routes._auto_fix_caches(stale_caches)

        previous_state = await db.system_runtime_flags.find_one(
            {"key": "platform_cache_freshness_state"},
            {"_id": 0},
        ) or {}
        previous_status = str((previous_state.get("value") or {}).get("status") or "unknown")

        active_issue_count = len(stale_urls) + len(stale_caches) + (1 if build_info.get("stale") else 0) + (1 if disk_pressure else 0)
        status = "healthy" if active_issue_count == 0 else "warning"

        state_value = {
            "status": status,
            "active_issue_count": active_issue_count,
            "stale_urls": len(stale_urls),
            "stale_caches": len(stale_caches),
            "build_stale": bool(build_info.get("stale")),
            "frontend_rebuilt": rebuilt_frontend,
            "auto_fixed_urls": int(url_fix.get("fixed_count", 0) or 0),
            "auto_cleared_caches": len(cleared_caches),
            "disk_free_mb": disk_free_mb,
            "disk_pressure": disk_pressure,
            "disk_pressure_min_free_mb": min_free_mb,
            "disk_auto_cleaned_paths": auto_cleaned_paths,
            "last_run_at": now_iso,
        }

        await db.system_runtime_flags.update_one(
            {"key": "platform_cache_freshness_state"},
            {
                "$set": {
                    "key": "platform_cache_freshness_state",
                    "value": state_value,
                    "updated_at": now_iso,
                }
            },
            upsert=True,
        )

        await db.platform_cache_freshness_history.insert_one(
            {
                "run_at": now_iso,
                "status": status,
                "stale_urls": len(stale_urls),
                "stale_caches": len(stale_caches),
                "build_stale": bool(build_info.get("stale")),
                "disk_free_mb": disk_free_mb,
                "disk_pressure": disk_pressure,
                "auto_fix": {
                    "fixed_url_files": int(url_fix.get("fixed_count", 0) or 0),
                    "cleared_caches": len(cleared_caches),
                    "disk_cleaned_paths": auto_cleaned_paths,
                },
            }
        )

        if previous_status != status and status == "warning":
            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(40)
            for admin in admins:
                admin_id = str(admin.get("user_id") or "")
                if not admin_id:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"platform_cache_freshness_warning_{admin_id}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": admin_id,
                        "type": "platform_cache_freshness_warning",
                        "title": "Platform Cache Freshness Warning",
                        "message": f"Detected {active_issue_count} freshness issue(s). Auto-fix executed.",
                        "read": False,
                        "created_at": now_iso,
                        "metadata": state_value,
                    }
                )

        await _record_scheduler_heartbeat(
            job_id,
            status,
            f"issues={active_issue_count} stale_urls={len(stale_urls)} stale_caches={len(stale_caches)} fixed_urls={int(url_fix.get('fixed_count', 0) or 0)} cleared={len(cleared_caches)} disk_pressure={disk_pressure} disk_free_mb={disk_free_mb}",
        )
    except Exception as e:
        logger.error(f"scheduled_platform_cache_freshness_guard failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_growth_integrity_monitor():
    """Continuous anomaly/payment integrity monitor for growth-scale stability."""
    job_id = "growth_integrity_monitor"
    try:
        from routes.db import db
        from routes.platform_employees import _build_employee_ai_insights

        insights = await _build_employee_ai_insights(window_hours=24)
        high_risk_alerts = [a for a in (insights.get("security_alerts") or []) if str(a.get("severity")) == "high"]

        payment_latest = await db.payment_e2e_reports.find_one({}, {"_id": 0}, sort=[("generated_at", -1)]) or {}
        payment_severity = str(payment_latest.get("severity") or "unknown")
        payment_pass_rate = float((payment_latest.get("summary") or {}).get("pass_rate") or 0)

        status = "healthy"
        if high_risk_alerts or payment_severity in {"high", "degraded"} or payment_pass_rate < 90:
            status = "warning"

        monitor_doc = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "high_risk_alerts": len(high_risk_alerts),
            "payment_severity": payment_severity,
            "payment_pass_rate": payment_pass_rate,
        }
        await db.growth_integrity_monitor_history.insert_one(monitor_doc)

        if status != "healthy":
            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(100)
            for adm in admins:
                uid = str(adm.get("user_id") or "")
                if not uid:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"growth_monitor_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": uid,
                        "type": "growth_integrity_monitor",
                        "title": "Growth Integrity Monitor Alert",
                        "message": f"Anomaly/payment monitor warning: risk_alerts={len(high_risk_alerts)}, payment={payment_severity}, pass_rate={payment_pass_rate}%.",
                        "read": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "metadata": monitor_doc,
                    }
                )
        logger.info("Growth integrity monitor completed: status=%s", status)
        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if status == "healthy" else "warning",
            f"payment_severity={payment_severity} pass_rate={payment_pass_rate}",
        )
    except Exception as e:
        logger.error(f"scheduled_growth_integrity_monitor failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_global_experience_assurance():
    """Continuous platform-wide UX/API/link/cache assurance with auto-remediation."""
    job_id = "global_experience_assurance"
    try:
        from routes.db import db
        from routes.platform_health import scan_platform_health, auto_fix_platform
        from routes.ai_learning_hub import run_learning_hub_assurance_cycle
        from routes.fedapay_client import sync_webhook_url
        from routes.payments import run_fedapay_webhook_retry_cycle, run_fedapay_webhook_dead_replay_cycle

        admin_ctx = await _get_scheduler_admin_context()
        scan = await scan_platform_health(admin_ctx)
        total_issues = int(scan.get("total_issues", 0) or 0)

        fix_result = None
        if total_issues > 0:
            fix_result = await auto_fix_platform(admin_ctx)

        localization_audit = await db.email_template_multilingual_localization_audits.find_one(
            {},
            {"_id": 0, "run_at": 1, "summary": 1, "status": 1},
            sort=[("run_at", -1)],
        ) or {}
        localization_failed = int(((localization_audit.get("summary") or {}).get("languages_failed", 0) or 0))

        learning_assurance = await run_learning_hub_assurance_cycle(triggered_by="scheduler:global-assurance")
        fedapay_sync = await sync_webhook_url()
        fedapay_retry = await run_fedapay_webhook_retry_cycle(limit=30)
        fedapay_dead = await run_fedapay_webhook_dead_replay_cycle(limit=10)

        status = "healthy"
        if total_issues > 0 or str(learning_assurance.get("status")) != "healthy" or localization_failed > 0:
            status = "warning"
        if str(fedapay_sync.get("status")) not in {"ok", "skipped"}:
            status = "critical"

        snapshot = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "platform_health": {
                "score": scan.get("score"),
                "grade": scan.get("grade"),
                "total_issues": total_issues,
            },
            "auto_fix": fix_result,
            "email_localization": localization_audit,
            "learning_hub_assurance": {
                "status": learning_assurance.get("status"),
                "video_broken_links": (learning_assurance.get("videos") or {}).get("broken_links"),
                "api_failed": (learning_assurance.get("api_validation") or {}).get("failed"),
            },
            "fedapay": {
                "sync": fedapay_sync,
                "retry": fedapay_retry,
                "dead_replay": fedapay_dead,
            },
        }
        await db.global_experience_assurance_history.insert_one(snapshot)

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if status == "healthy" else "warning" if status == "warning" else "error",
            f"scan_issues={total_issues} lh_status={learning_assurance.get('status')} fedapay_sync={fedapay_sync.get('status')}",
        )
    except Exception as e:
        logger.error(f"scheduled_global_experience_assurance failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_continuous_cycle():
    """24/7 continuous autonomous cycle — health check, latency, tests, perf, auto-heal."""
    job_id = "continuous_autonomous_cycle"
    try:
        from routes.autonomous_engine import run_continuous_cycle, _get_engine_config

        config = await _get_engine_config()
        cs_mode = config.get("continuous_mode", {})
        if not cs_mode.get("enabled", False):
            await _record_scheduler_heartbeat(job_id, "skipped", "24/7 mode disabled")
            return

        cycle = await run_continuous_cycle(triggered_by="scheduler_24_7")
        status = cycle.get("status", "UNKNOWN")
        forever_loop = cycle.get("forever_loop") or {}
        deploy_stage = next((s for s in (forever_loop.get("stages") or []) if s.get("name") == "Deploy"), {})
        learn_stage = next((s for s in (forever_loop.get("stages") or []) if s.get("name") == "Learn"), {})
        await _record_scheduler_heartbeat(
            job_id, "healthy" if status in ("PASS", "HEALED") else "warning",
            (
                f"status={status} anomalies={cycle.get('anomaly_count',0)} healed={cycle.get('healed',False)} avg={cycle.get('overall_avg_ms',0)}ms "
                f"deploy={deploy_stage.get('status','SKIP')} learn={learn_stage.get('status','SKIP')}"
            ),
        )
        logger.info(
            "Continuous cycle: status=%s anomalies=%s healed=%s avg_ms=%s",
            status, cycle.get("anomaly_count", 0), cycle.get("healed", False), cycle.get("overall_avg_ms", 0),
        )
    except Exception as exc:
        logger.error(f"scheduled_continuous_cycle failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def _trim_validity_autofix_history(max_rows: int = 300):
    try:
        from routes.db import db

        total = await db.autonomous_validity_autofix_runs.count_documents({})
        if total <= max_rows:
            return
        overflow = total - max_rows
        oldest = await db.autonomous_validity_autofix_runs.find({}, {"_id": 1}).sort("timestamp", 1).limit(overflow).to_list(overflow)
        if oldest:
            await db.autonomous_validity_autofix_runs.delete_many({"_id": {"$in": [row["_id"] for row in oldest]}})
    except Exception:
        return


async def scheduled_validity_autofix_refresh():
    """Auto-fix run to keep strict hard-gate validity fresh without admin input."""
    job_id = "autonomous_validity_autofix"
    try:
        from routes.db import db
        from routes.autonomous_engine import _get_engine_config, _build_gate_lock_state, run_full_pipeline
        from routes.ai_autofix_engine import run_all_fixes

        config = await _get_engine_config()
        if not bool(config.get("enabled", True)):
            await _record_scheduler_heartbeat(job_id, "skipped", "engine_disabled")
            return

        gate_lock = await _build_gate_lock_state(config)
        if bool(gate_lock.get("gate_open")):
            await _record_scheduler_heartbeat(job_id, "healthy", "gate_open_no_action")
            return

        policy = config.get("validity_autofix_policy") or {}
        cooldown_minutes = max(10, min(240, int(policy.get("cooldown_minutes", 45))))
        now = datetime.now(timezone.utc)
        last_attempt = await db.autonomous_validity_autofix_runs.find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
        if last_attempt and last_attempt.get("attempted_at"):
            try:
                prev = datetime.fromisoformat(str(last_attempt.get("attempted_at")).replace("Z", "+00:00"))
                mins_since = int((now - prev).total_seconds() // 60)
                if mins_since < cooldown_minutes:
                    await _record_scheduler_heartbeat(
                        job_id,
                        "skipped",
                        f"cooldown_active mins_since={mins_since} cooldown={cooldown_minutes}",
                    )
                    return
            except Exception:
                pass

        auto_fix_summary = {"total_proposed": 0, "total_applied": 0, "total_flagged": 0, "status": "not_run"}
        try:
            auto_fix_result = await run_all_fixes()
            auto_fix_summary = {
                "status": "ok",
                "total_proposed": int(auto_fix_result.get("total_proposed", 0)),
                "total_applied": int(auto_fix_result.get("total_applied", 0)),
                "total_flagged": int(auto_fix_result.get("total_flagged", 0)),
                "confidence_threshold": auto_fix_result.get("confidence_threshold"),
            }
        except Exception as exc:
            auto_fix_summary = {
                "status": "error",
                "error": str(exc)[:180],
                "total_proposed": 0,
                "total_applied": 0,
                "total_flagged": 0,
            }

        pipeline_result = await run_full_pipeline(config, triggered_by="scheduler_validity_autofix")
        post_gate = await _build_gate_lock_state(config)
        pipeline_status = str(pipeline_result.get("status") or "UNKNOWN").upper()
        if pipeline_status == "PASS" and bool(post_gate.get("gate_open")):
            status = "refreshed_pass"
        elif pipeline_status == "PASS":
            status = "pass_but_gate_closed"
        else:
            status = "pipeline_failed"

        run_doc = {
            "run_id": f"vaf_{uuid.uuid4().hex[:10]}",
            "attempted_at": now.isoformat(),
            "timestamp": now,
            "triggered_by": "scheduler",
            "status": status,
            "cooldown_minutes": cooldown_minutes,
            "pre_gate_lock": gate_lock,
            "post_gate_lock": post_gate,
            "auto_fix": auto_fix_summary,
            "pipeline": {
                "run_id": pipeline_result.get("run_id"),
                "status": pipeline_result.get("status"),
                "final_output": pipeline_result.get("final_output", {}),
            },
        }
        await db.autonomous_validity_autofix_runs.insert_one({**run_doc})
        await _trim_validity_autofix_history(max_rows=max(100, min(3000, int(policy.get("max_history", 500)))))

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if status == "refreshed_pass" else "warning",
            (
                f"status={status} pre_gate_open={bool(gate_lock.get('gate_open'))} "
                f"post_gate_open={bool(post_gate.get('gate_open'))} "
                f"pipeline={pipeline_status} autofix_applied={auto_fix_summary.get('total_applied', 0)}"
            ),
        )
    except Exception as exc:
        logger.error(f"scheduled_validity_autofix_refresh failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


async def scheduled_predictive_failure_prevention():
    """Predict likely failures ahead of impact, then preemptively fix + validate."""
    job_id = "predictive_failure_prevention"
    try:
        from routes.autonomous_engine import run_predictive_failure_prevention, _get_engine_config

        config = await _get_engine_config()
        policy = config.get("predictive_policy", {})
        if not bool(policy.get("enabled", True)):
            await _record_scheduler_heartbeat(job_id, "skipped", "predictive mode disabled")
            return
        if not bool(policy.get("scheduler_enabled", True)):
            await _record_scheduler_heartbeat(job_id, "skipped", "predictive scheduler disabled")
            return

        result = await run_predictive_failure_prevention(triggered_by="scheduler")
        status = str(result.get("status") or "UNKNOWN")
        confidence = 0
        if result.get("high_risk_predictions"):
            confidence = max(int(item.get("confidence", 0)) for item in result.get("high_risk_predictions", []))
        heartbeat_status = "healthy" if status in {"PREEMPTED_AND_VALIDATED", "LOW_RISK_MONITORING", "NO_PATTERN_DETECTED"} else "warning"
        await _record_scheduler_heartbeat(
            job_id,
            heartbeat_status,
            (
                f"status={status} predictions={result.get('prediction_count', 0)} "
                f"high_risk={result.get('high_risk_count', 0)} actions={len((result.get('preemptive') or {}).get('actions', []))} "
                f"max_conf={confidence}"
            ),
        )
        logger.info(
            "Predictive prevention: status=%s predictions=%s high_risk=%s actions=%s",
            status,
            result.get("prediction_count", 0),
            result.get("high_risk_count", 0),
            len((result.get("preemptive") or {}).get("actions", [])),
        )
    except Exception as exc:
        logger.error(f"scheduled_predictive_failure_prevention failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


__all__ = [
    "scheduled_platform_cache_freshness_guard",
    "scheduled_growth_integrity_monitor",
    "scheduled_global_experience_assurance",
    "scheduled_continuous_cycle",
    "scheduled_validity_autofix_refresh",
    "scheduled_predictive_failure_prevention",
    "_trim_validity_autofix_history",
]
