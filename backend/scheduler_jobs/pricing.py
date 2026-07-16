"""scheduler_jobs.pricing — Pricing & subscription-plan guardrail jobs.

**Phase 2 batch #17.**

Jobs: subscription_plan_guardrail (continuous), pricing_guard_nightly_monitor.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from scheduler_jobs.observability import _record_scheduler_heartbeat

logger = logging.getLogger("scheduler_jobs.pricing")


async def scheduled_subscription_plan_guardrail():
    """Recurring subscription-plan enforcement guardrail (Free/Basic/Premium drift detection)."""
    job_id = "subscription_plan_guardrail"
    try:
        import httpx
        from routes.db import db
        from routes.admin_push_notifications import emit_realtime_alert

        base_url = (os.environ.get("FRONTEND_BASE_URL") or "http://localhost:3000").strip().rstrip("/")
        checks = []

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            plans = await client.get(f"{base_url}/api/subscriptions/plans")
            checks.append({"name": "plans_endpoint", "ok": plans.status_code == 200, "status_code": plans.status_code})

            has_expected_tiers = False
            if plans.status_code == 200:
                try:
                    payload = plans.json()
                    entries = payload.get("plans") if isinstance(payload, dict) else payload
                    tiers = {str((p or {}).get("id") or (p or {}).get("plan") or (p or {}).get("slug") or "").lower() for p in (entries or [])}
                    has_expected_tiers = {"free", "basic", "premium"}.issubset(tiers)
                except Exception:
                    has_expected_tiers = False
            checks.append({"name": "plan_tiers_present", "ok": has_expected_tiers, "status_code": 200 if has_expected_tiers else 500})

            premium_probe = await client.get(f"{base_url}/api/admin/enterprise/features")
            checks.append({"name": "premium_endpoint_protected", "ok": premium_probe.status_code in [401, 403], "status_code": premium_probe.status_code})

        passed = all(c.get("ok") for c in checks)
        status = "pass" if passed else "fail"
        failed_checks = [c.get("name") for c in checks if not c.get("ok")]
        now_iso = datetime.now(timezone.utc).isoformat()

        await db.subscription_plan_guardrail_runs.insert_one(
            {
                "ran_at": now_iso,
                "status": status,
                "checks": checks,
                "failed_checks": failed_checks,
                "base_url": base_url,
            }
        )

        key = "subscription_plan_guardrail_state"
        prev = await db.system_runtime_flags.find_one({"key": key}, {"_id": 0}) or {}
        prev_state = str(prev.get("state") or "")
        changed = bool(prev_state) and prev_state != status

        await db.system_runtime_flags.update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "state": status,
                    "previous_state": prev_state or None,
                    "changed": changed,
                    "last_run_at": now_iso,
                    "failed_checks": failed_checks,
                }
            },
            upsert=True,
        )

        if changed:
            severity = "critical" if status == "fail" else "info"
            title = "Subscription Plan Guardrail State Changed"
            message = (
                f"Subscription guardrail changed PASS → FAIL. Failed checks: {', '.join(failed_checks) if failed_checks else 'unknown'}."
                if status == "fail"
                else "Subscription guardrail recovered FAIL → PASS."
            )

            await emit_realtime_alert(
                alert_type="subscription_plan_guardrail_state_change",
                severity=severity,
                title=title,
                message=message,
            )

            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(100)
            for adm in admins:
                uid = str(adm.get("user_id") or "")
                if not uid:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"subscription_guardrail_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": uid,
                        "type": "subscription_plan_guardrail_state_change",
                        "title": title,
                        "message": message,
                        "read": False,
                        "created_at": now_iso,
                        "metadata": {
                            "state": status,
                            "previous_state": prev_state,
                            "failed_checks": failed_checks,
                        },
                    }
                )

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if passed else "warning",
            f"state={status} changed={changed} failed={','.join(failed_checks) if failed_checks else 'none'}",
        )

    except Exception as e:
        logger.error(f"Subscription plan guardrail failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_pricing_guard_nightly_monitor():
    """Nightly pricing-guard incident monitor (00:05 UTC) with admin dashboard alerts."""
    job_id = "pricing_guard_nightly_monitor"
    try:
        from routes.db import db
        from routes.admin_push_notifications import emit_realtime_alert

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        window_start = now - timedelta(hours=24)
        window_start_iso = window_start.isoformat()
        monitor_day = now.strftime("%Y-%m-%d")

        base_query = {
            "created_at": {
                "$gte": window_start_iso,
                "$lt": now_iso,
            }
        }
        projection = {
            "_id": 0,
            "created_at": 1,
            "route": 1,
            "context": 1,
            "event_type": 1,
            "reason": 1,
            "param_price": 1,
            "canonical_price": 1,
            "actual_amount": 1,
            "expected_amount": 1,
            "plan_id": 1,
            "billing_period": 1,
        }

        incidents = await db.pricing_mismatch_alert_events.find(
            base_query,
            projection,
        ).sort("created_at", -1).limit(300).to_list(300)
        incident_count = int(await db.pricing_mismatch_alert_events.count_documents(base_query))
        open_count = int(
            await db.pricing_mismatch_alert_events.count_documents(
                {
                    **base_query,
                    "status": {"$ne": "acknowledged"},
                }
            )
        )

        context_counts: dict[str, int] = {}
        for item in incidents:
            ctx = str(
                item.get("route")
                or item.get("context")
                or item.get("event_type")
                or item.get("reason")
                or "unknown"
            ).strip()
            context_counts[ctx] = context_counts.get(ctx, 0) + 1

        top_contexts = sorted(context_counts.items(), key=lambda entry: entry[1], reverse=True)[:3]
        top_contexts_summary = ", ".join([f"{name} ({count})" for name, count in top_contexts]) if top_contexts else "n/a"

        sample = incidents[0] if incidents else {}
        sample_param = sample.get("param_price")
        if sample_param is None:
            sample_param = sample.get("actual_amount")

        sample_canonical = sample.get("canonical_price")
        if sample_canonical is None:
            sample_canonical = sample.get("expected_amount")

        severity = "critical" if incident_count >= 10 else "warning" if incident_count > 0 else "info"

        await db.pricing_guard_nightly_monitor_runs.insert_one(
            {
                "job_id": job_id,
                "created_at": now_iso,
                "window_start": window_start_iso,
                "window_end": now_iso,
                "incident_count": incident_count,
                "open_count": open_count,
                "severity": severity,
                "top_contexts": [
                    {"context": name, "count": count}
                    for name, count in top_contexts
                ],
                "sample": {
                    "context": str(sample.get("route") or sample.get("context") or sample.get("event_type") or ""),
                    "plan_id": str(sample.get("plan_id") or ""),
                    "billing_period": str(sample.get("billing_period") or ""),
                    "param_price": sample_param,
                    "canonical_price": sample_canonical,
                },
            }
        )

        state_key = "pricing_guard_nightly_monitor_state"
        previous_state = await db.system_runtime_flags.find_one({"key": state_key}, {"_id": 0}) or {}
        last_alert_day = str(previous_state.get("last_alert_day_utc") or "")
        should_alert = incident_count > 0 and last_alert_day != monitor_day
        alerted = False

        if should_alert:
            title = "Pricing Guard Incidents Detected"
            message = (
                f"{incident_count} pricing-guard incident(s) detected in the last 24 hours "
                f"(open: {open_count}). Top contexts: {top_contexts_summary}."
            )

            await emit_realtime_alert(
                alert_type="pricing_guard_nightly_incident_alert",
                severity=severity,
                title=title,
                message=message,
            )

            admins = await db.users.find(
                {"is_admin": True},
                {"_id": 0, "user_id": 1},
            ).to_list(100)
            for admin in admins:
                uid = str(admin.get("user_id") or "")
                if not uid:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"pricing_guard_nightly_{uid}_{int(now.timestamp())}",
                        "user_id": uid,
                        "type": "pricing_guard_nightly_incident_alert",
                        "title": title,
                        "message": message,
                        "read": False,
                        "created_at": now_iso,
                        "metadata": {
                            "job_id": job_id,
                            "window_start": window_start_iso,
                            "window_end": now_iso,
                            "incident_count": incident_count,
                            "open_count": open_count,
                            "top_contexts": [
                                {"context": name, "count": count}
                                for name, count in top_contexts
                            ],
                            "sample_param_price": sample_param,
                            "sample_canonical_price": sample_canonical,
                        },
                    }
                )

            alerted = True

        await db.system_runtime_flags.update_one(
            {"key": state_key},
            {
                "$set": {
                    "key": state_key,
                    "last_run_at": now_iso,
                    "window_start": window_start_iso,
                    "window_end": now_iso,
                    "incident_count": incident_count,
                    "open_count": open_count,
                    "severity": severity,
                    "top_contexts": [
                        {"context": name, "count": count}
                        for name, count in top_contexts
                    ],
                    "last_alert_day_utc": monitor_day if alerted else (last_alert_day or None),
                    "alerted": alerted,
                }
            },
            upsert=True,
        )

        await _record_scheduler_heartbeat(
            job_id,
            "warning" if incident_count > 0 else "healthy",
            f"incidents={incident_count} open={open_count} alerted={alerted} top={top_contexts_summary[:120]}",
        )
    except Exception as e:
        logger.error(f"Pricing guard nightly monitor failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e)[:180])


__all__ = [
    "scheduled_subscription_plan_guardrail",
    "scheduled_pricing_guard_nightly_monitor",
]
