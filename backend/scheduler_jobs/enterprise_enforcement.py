# ruff: noqa
"""scheduler_jobs.enterprise_enforcement — Enterprise policy enforcement jobs.

**Phase 2 batch #16.**

Jobs: enterprise lock cycle, SLO breach auto-mitigation, weekly enterprise
standard enforcement, global RBAC subscription enforcement, quarterly
access recertification.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from utils.pagination import iter_find_paginated
from scheduler_jobs.observability import _record_scheduler_heartbeat
from scheduler_jobs.admin_context import _get_scheduler_admin_context  # noqa: F401

logger = logging.getLogger("scheduler_jobs.enterprise_enforcement")


async def scheduled_enterprise_lock_cycle():
    """Runs enterprise audit pipeline (detect→repair→validate→lock) and persists permanent enforcement."""
    job_id = "enterprise_lock_cycle"
    try:
        from routes.db import db
        from routes.platform_health import run_enterprise_auto_audit

        admin_ctx = await _get_scheduler_admin_context()
        result = await run_enterprise_auto_audit(user=admin_ctx)
        final_state = result.get("final_state", {}) if isinstance(result, dict) else {}
        score = int(final_state.get("score", 0) or 0)
        issues = int(final_state.get("issues", 0) or 0)
        stable = bool(final_state.get("stable", False))

        await db.enterprise_lock_cycle_history.insert_one(
            {
                "run_at": datetime.now(timezone.utc).isoformat(),
                "score": score,
                "issues": issues,
                "stable": stable,
                "run_id": result.get("run_id") if isinstance(result, dict) else None,
                "rollback_checkpoint": result.get("rollback_checkpoint") if isinstance(result, dict) else None,
            }
        )

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if stable else "warning",
            f"score={score} issues={issues} stable={stable}",
        )
        logger.info("Enterprise lock cycle completed: score=%s issues=%s stable=%s", score, issues, stable)
    except Exception as e:
        logger.error(f"scheduled_enterprise_lock_cycle failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_slo_breach_auto_mitigation():
    """Evaluate p95 latency SLO and auto-apply targeted mitigation recipes when breached."""
    job_id = "slo_breach_auto_mitigation"
    try:
        from routes.platform_health import run_slo_auto_mitigation_cycle

        result = await run_slo_auto_mitigation_cycle(triggered_by="scheduler")
        status = str(result.get("status") or "unknown")
        perf = result.get("current_performance") or {}
        policy = result.get("policy") or {}
        actions = result.get("actions") or []

        if status in {"healthy", "disabled", "insufficient_data"}:
            heartbeat_status = "healthy"
        elif status in {"breach_detected", "mitigated"}:
            heartbeat_status = "warning"
        else:
            heartbeat_status = "error"

        await _record_scheduler_heartbeat(
            job_id,
            heartbeat_status,
            f"status={status} p95={perf.get('global_p95_ms')} threshold={policy.get('p95_latency_threshold_ms')} actions={len(actions)}",
        )
    except Exception as e:
        logger.error(f"scheduled_slo_breach_auto_mitigation failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_weekly_enterprise_standard_enforcement():
    """Weekly enterprise-standard enforce-now equivalent with score-drop alerting (<95)."""
    job_id = "enterprise_standard_weekly_guard"
    try:
        from routes.db import db
        from routes.platform_health import enforce_enterprise_standard_now
        from routes.admin_push_notifications import emit_realtime_alert
        from utils.email_service import send_catalog_template

        admin_ctx = await _get_scheduler_admin_context()
        now_iso = datetime.now(timezone.utc).isoformat()
        launch = await enforce_enterprise_standard_now(user=admin_ctx)
        run_id = str(launch.get("run_id") or "")

        final_doc = None
        for _ in range(72):
            final_doc = await db.enterprise_standard_enforcement_history.find_one(
                {"run_id": run_id},
                {"_id": 0},
            )
            phase = str((final_doc or {}).get("phase") or "")
            status = str((final_doc or {}).get("status") or "")
            if phase in {"completed", "failed"} or status in {"healthy", "warning", "critical", "error"}:
                break
            await asyncio.sleep(5)

        final_state = (final_doc or {}).get("final_state") if isinstance(final_doc, dict) else {}
        final_score = int((final_state or {}).get("score") or 0)
        final_issues = int((final_state or {}).get("issues") or 0)
        enforcement_status = str((final_doc or {}).get("status") or "timeout")
        phase = str((final_doc or {}).get("phase") or "running")
        pass_gate = enforcement_status == "healthy" and final_score >= 95 and final_issues == 0

        run_record = {
            "run_at": now_iso,
            "run_id": run_id,
            "status": enforcement_status,
            "phase": phase,
            "score": final_score,
            "issues": final_issues,
            "pass_gate": pass_gate,
            "trigger": "scheduled_weekly",
            "final_doc": final_doc or {},
        }
        await db.enterprise_standard_weekly_guard_history.insert_one(run_record)

        flag_key = "enterprise_standard_weekly_guard_state"
        previous_state_doc = await db.system_runtime_flags.find_one({"key": flag_key}, {"_id": 0}) or {}
        previous_gate = str(previous_state_doc.get("state") or "")
        current_gate = "pass" if pass_gate else "fail"
        changed = bool(previous_gate) and previous_gate != current_gate
        await db.system_runtime_flags.update_one(
            {"key": flag_key},
            {
                "$set": {
                    "key": flag_key,
                    "state": current_gate,
                    "previous_state": previous_gate or None,
                    "changed": changed,
                    "last_run_at": now_iso,
                    "score": final_score,
                    "issues": final_issues,
                    "status": enforcement_status,
                    "run_id": run_id,
                }
            },
            upsert=True,
        )

        if final_score < 95 or not pass_gate:
            severity = "critical" if final_score < 90 or enforcement_status in {"critical", "error", "timeout"} else "warning"
            title = "Weekly Enterprise Enforcement Alert"
            message = (
                f"Enterprise-standard weekly enforcement scored {final_score}/100 with {final_issues} issue(s). "
                f"Status: {enforcement_status.upper()} (run {run_id})."
            )

            await emit_realtime_alert(
                alert_type="enterprise_standard_weekly_guard",
                severity=severity,
                title=title,
                message=message,
            )

            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(100)
            seen_emails = set()
            for adm in admins:
                uid = str(adm.get("user_id") or "")
                email = str(adm.get("email") or "").strip().lower()
                name = str(adm.get("name") or "Admin")
                if uid:
                    await db.notifications.insert_one(
                        {
                            "id": f"enterprise_weekly_guard_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                            "user_id": uid,
                            "type": "enterprise_standard_weekly_guard",
                            "title": title,
                            "message": message,
                            "read": False,
                            "created_at": now_iso,
                            "metadata": {
                                "run_id": run_id,
                                "score": final_score,
                                "issues": final_issues,
                                "status": enforcement_status,
                            },
                        }
                    )
                if email:
                    seen_emails.add(email)
                    await send_catalog_template(
                        recipient_email=email,
                        template_key="admin_detailed_system_alert",
                        recipient_name=name,
                        title="Weekly Enterprise Enforcement Alert",
                        intro=f"Score: {final_score}/100 | Issues: {final_issues} | Status: {enforcement_status.upper()}",
                        rows=[("Score", f"{final_score}/100"), ("Issues", str(final_issues)), ("Status", enforcement_status.upper()), ("Run ID", run_id)],
                        accent="#F59E0B" if enforcement_status == "warning" else "#EF4444" if enforcement_status == "critical" else "#10B981",
                        status_label=enforcement_status.upper(),
                        footer_note="Weekly Enterprise Enforcement Alert",
                    )

            fallback_email = str(os.environ.get("ADMIN_EMAIL") or "").strip().lower()
            if fallback_email and fallback_email not in seen_emails:
                await send_catalog_template(
                    recipient_email=fallback_email,
                    template_key="admin_detailed_system_alert",
                    recipient_name="Admin",
                    title="Weekly Enterprise Enforcement Alert",
                    intro=f"Score: {final_score}/100 | Issues: {final_issues} | Status: {enforcement_status.upper()}",
                    rows=[("Score", f"{final_score}/100"), ("Issues", str(final_issues)), ("Status", enforcement_status.upper()), ("Run ID", run_id)],
                    accent="#F59E0B" if enforcement_status == "warning" else "#EF4444" if enforcement_status == "critical" else "#10B981",
                    status_label=enforcement_status.upper(),
                    footer_note="Weekly Enterprise Enforcement Alert",
                )

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if pass_gate else "warning",
            f"run_id={run_id} score={final_score} issues={final_issues} status={enforcement_status}",
        )
    except Exception as e:
        logger.error(f"scheduled_weekly_enterprise_standard_enforcement failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_global_rbac_subscription_enforcement():
    """Hourly global guard: revoke non-admin bypass flags and downgrade unverified paid users."""
    job_id = "global_rbac_subscription_enforcement"
    try:
        from utils.access_governance import apply_global_rbac_subscription_enforcement

        result = await apply_global_rbac_subscription_enforcement(
            trigger="scheduled_hourly_guard",
            actor_user_id="scheduler",
            actor_email="scheduler@system",
            baseline_reset_non_admin_paid=False,
        )
        await _record_scheduler_heartbeat(
            job_id,
            "healthy",
            f"run={result.get('run_id')} revoked={result.get('revoked_non_admin_privileged_flags')} downgraded_unverified={result.get('downgraded_non_admin_unverified_paid')}",
        )
    except Exception as e:
        logger.error(f"scheduled_global_rbac_subscription_enforcement failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_quarterly_access_recertification():
    """Quarterly campaign: require admin recertification for platform employee entitlements."""
    job_id = "quarterly_access_recertification"
    try:
        from routes.db import db

        now = datetime.now(timezone.utc)
        quarter = ((now.month - 1) // 3) + 1
        campaign_id = f"recert_{now.year}_q{quarter}"

        existing = await db.access_recertification_campaigns.find_one({"campaign_id": campaign_id}, {"_id": 0, "campaign_id": 1})
        if existing:
            await _record_scheduler_heartbeat(job_id, "healthy", f"campaign_exists={campaign_id}")
            return

        employees = []
        async for employee_row in iter_find_paginated(
            db.users,
            {
                "is_admin": {"$ne": True},
                "platform_role": {"$exists": True, "$nin": [None, ""]},
            },
            {
                "_id": 0,
                "user_id": 1,
                "email": 1,
                "platform_role": 1,
                "employee_permissions": 1,
                "feature_access": 1,
            },
            max_docs=20000,
        ):
            employees.append(employee_row)

        now_iso = now.isoformat()
        due_at = (now + timedelta(days=14)).isoformat()
        if employees:
            docs = []
            for emp in employees:
                docs.append(
                    {
                        "task_id": f"rectask_{uuid.uuid4().hex[:12]}",
                        "campaign_id": campaign_id,
                        "user_id": str(emp.get("user_id") or ""),
                        "email": str(emp.get("email") or ""),
                        "platform_role": str(emp.get("platform_role") or ""),
                        "employee_permissions": emp.get("employee_permissions") or [],
                        "feature_access": emp.get("feature_access") or [],
                        "status": "pending_admin_recertification",
                        "created_at": now_iso,
                        "due_at": due_at,
                    }
                )
            await db.access_recertification_tasks.insert_many(docs)

        await db.access_recertification_campaigns.insert_one(
            {
                "campaign_id": campaign_id,
                "quarter": quarter,
                "year": now.year,
                "status": "open",
                "target_count": len(employees),
                "created_at": now_iso,
                "due_at": due_at,
            }
        )

        await db.notifications.insert_one(
            {
                "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
                "type": "access_recertification",
                "title": "Quarterly access recertification campaign opened",
                "message": f"Campaign {campaign_id} opened for {len(employees)} platform employee accounts.",
                "created_at": now_iso,
            }
        )
        await _record_scheduler_heartbeat(job_id, "healthy", f"campaign={campaign_id} targets={len(employees)}")
    except Exception as e:
        logger.error(f"scheduled_quarterly_access_recertification failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


__all__ = [
    "scheduled_enterprise_lock_cycle",
    "scheduled_slo_breach_auto_mitigation",
    "scheduled_weekly_enterprise_standard_enforcement",
    "scheduled_global_rbac_subscription_enforcement",
    "scheduled_quarterly_access_recertification",
]
