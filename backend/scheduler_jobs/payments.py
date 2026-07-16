"""
scheduler_jobs.payments — Payments / billing automation scheduled jobs.

**Phase 2 incremental domain split — sixth batch.**

Owns the recurring billing-side automation: bill-generator hourly daemon,
FedaPay webhook self-healing (sync + retry + dead-letter replay with
adaptive alerting), and the daily invoice-dunning email campaign.

Jobs in this module
===================
- ``scheduled_bill_generator_hourly_daemon`` — hourly guardrailed run for
  the Bill Generator due recurring schedules.
- ``scheduled_fedapay_webhook_self_heal`` — maintains FedaPay webhook
  endpoint URL + drains retry/dead queues + adaptive admin alerting with
  a 30-minute cooldown and 6-hour stale-signature override.
- ``scheduled_invoice_dunning`` — daily 3/7/14-day past-due dunning email
  campaign with per-month idempotency (one notification per user / tier /
  expiry-month).

External callers (`scheduler.py`) continue to import via the facade.
"""

import logging
import os
import requests
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from utils.pagination import iter_find_paginated

from scheduler_jobs.observability import _record_scheduler_heartbeat
from scheduler_jobs.utils import _resolve_frontend_base_url


logger = logging.getLogger("scheduler_jobs.payments")


def _resend_expected_webhook_endpoint() -> str:
    base_url = _resolve_frontend_base_url()
    if not base_url:
        base_url = str(os.environ.get("FRONTEND_BASE_URL") or "").strip().rstrip("/")
    return f"{base_url}/api/webhooks/resend" if base_url else ""


async def _emit_resend_webhook_alert(
    *,
    db,
    now_iso: str,
    severity: str,
    title: str,
    message: str,
    metadata: Dict[str, Any],
) -> None:
    """Fanout admin notification + persist alert state for Resend webhook drift."""
    flag_key = "resend_webhook_guard_alert"
    state = await db.system_runtime_flags.find_one({"key": flag_key}, {"_id": 0}) or {}
    prev_sig = str(state.get("last_alert_signature") or "")
    sig = str(metadata.get("alert_signature") or "")
    if sig and sig == prev_sig:
        return

    admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(50)
    ts = int(datetime.now(timezone.utc).timestamp())
    for adm in admins:
        uid = str(adm.get("user_id") or "")
        if not uid:
            continue
        await db.notifications.insert_one(
            {
                "id": f"resend_webhook_guard_alert_{uid}_{ts}",
                "user_id": uid,
                "type": "resend_webhook_guard_alert",
                "title": title,
                "message": message,
                "read": False,
                "created_at": now_iso,
                "metadata": {
                    "severity": severity,
                    **metadata,
                },
            }
        )

    await db.system_runtime_flags.update_one(
        {"key": flag_key},
        {
            "$set": {
                "key": flag_key,
                "last_alert_signature": sig,
                "last_alert_at": now_iso,
                "severity": severity,
                "title": title,
                "metadata": metadata,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )


async def scheduled_resend_webhook_guard() -> Dict[str, Any]:
    """Detect/repair Resend webhook drift and disabled state, then alert admins."""
    job_id = "resend_webhook_guard"
    try:
        from routes.db import db

        resend_key = str(os.environ.get("RESEND_API_KEY") or "").strip()
        expected_endpoint = _resend_expected_webhook_endpoint()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        if not resend_key:
            await _record_scheduler_heartbeat(job_id, "skipped", "RESEND_API_KEY missing")
            return {"status": "skipped", "reason": "resend_api_key_missing"}

        if not expected_endpoint:
            await _record_scheduler_heartbeat(job_id, "skipped", "Expected endpoint missing")
            return {"status": "skipped", "reason": "expected_endpoint_missing"}

        webhook_events = [
            "email.sent",
            "email.delivered",
            "email.delivery_delayed",
            "email.bounced",
            "email.complained",
            "email.opened",
            "email.clicked",
        ]
        headers = {
            "Authorization": f"Bearer {resend_key}",
            "Content-Type": "application/json",
        }

        list_resp = requests.get("https://api.resend.com/webhooks", headers={"Authorization": f"Bearer {resend_key}"}, timeout=20)
        if list_resp.status_code != 200:
            detail = f"list_failed_status={list_resp.status_code}"
            await _record_scheduler_heartbeat(job_id, "warning", detail)
            await db.resend_webhook_guard_events.insert_one(
                {
                    "created_at": now_iso,
                    "status": "warning",
                    "phase": "list",
                    "detail": detail,
                    "expected_endpoint": expected_endpoint,
                }
            )
            return {"status": "warning", "detail": detail}

        data = list_resp.json() or {}
        webhooks = data.get("data", []) if isinstance(data, dict) else []

        endpoint_normalized = expected_endpoint.rstrip("/")
        matched = None
        for wh in webhooks:
            endpoint = str(wh.get("endpoint") or "").strip().rstrip("/")
            if endpoint == endpoint_normalized:
                matched = wh
                break

        action = "none"
        repaired = False
        target = matched

        if target is None:
            stale = sorted(
                [
                    wh
                    for wh in webhooks
                    if str(wh.get("endpoint") or "").strip().endswith("/api/webhooks/resend")
                ],
                key=lambda w: str(w.get("created_at") or ""),
            )
            if stale:
                target = stale[-1]
                wid = str(target.get("id") or "").strip()
                if wid:
                    patch_payload = {
                        "endpoint": expected_endpoint,
                        "events": webhook_events,
                        "status": "enabled",
                    }
                    patch_resp = requests.patch(
                        f"https://api.resend.com/webhooks/{wid}",
                        headers=headers,
                        json=patch_payload,
                        timeout=20,
                    )
                    if patch_resp.status_code in (200, 201):
                        action = "autosync_patch_stale"
                        repaired = True
                    else:
                        action = f"autosync_patch_stale_failed_{patch_resp.status_code}"
            else:
                create_payload = {
                    "endpoint": expected_endpoint,
                    "events": webhook_events,
                    "status": "enabled",
                }
                create_resp = requests.post(
                    "https://api.resend.com/webhooks",
                    headers=headers,
                    json=create_payload,
                    timeout=20,
                )
                if create_resp.status_code in (200, 201):
                    action = "autocreate"
                    repaired = True
                else:
                    action = f"autocreate_failed_{create_resp.status_code}"

        if target is not None and action == "none":
            wid = str(target.get("id") or "").strip()
            endpoint = str(target.get("endpoint") or "").strip().rstrip("/")
            current_events = sorted([str(e) for e in (target.get("events") or [])])
            expected_events = sorted(webhook_events)
            status_value = str(target.get("status") or "").strip().lower()
            disabled = status_value == "disabled"
            drifted = endpoint != endpoint_normalized or current_events != expected_events
            if wid and (disabled or drifted):
                patch_payload = {
                    "endpoint": expected_endpoint,
                    "events": webhook_events,
                    "status": "enabled",
                }
                patch_resp = requests.patch(
                    f"https://api.resend.com/webhooks/{wid}",
                    headers=headers,
                    json=patch_payload,
                    timeout=20,
                )
                if patch_resp.status_code in (200, 201):
                    action = "autopatch_disabled_or_drift"
                    repaired = True
                else:
                    action = f"autopatch_failed_{patch_resp.status_code}"

        list_after = requests.get("https://api.resend.com/webhooks", headers={"Authorization": f"Bearer {resend_key}"}, timeout=20)
        aligned = False
        active_count = 0
        if list_after.status_code == 200:
            post_data = list_after.json() or {}
            post_webhooks = post_data.get("data", []) if isinstance(post_data, dict) else []
            for wh in post_webhooks:
                endpoint = str(wh.get("endpoint") or "").strip().rstrip("/")
                status_value = str(wh.get("status") or "").strip().lower()
                events = sorted([str(e) for e in (wh.get("events") or [])])
                if endpoint == endpoint_normalized:
                    active_count += 1
                    if status_value != "disabled" and events == sorted(webhook_events):
                        aligned = True

        severity = "healthy" if aligned else ("warning" if repaired else "critical")
        alert_signature = f"{expected_endpoint}|aligned={aligned}|action={action}|active={active_count}"

        event_doc = {
            "created_at": now_iso,
            "job_id": job_id,
            "status": severity,
            "action": action,
            "aligned": aligned,
            "repaired": repaired,
            "expected_endpoint": expected_endpoint,
            "active_matching_webhooks": active_count,
            "alert_signature": alert_signature,
        }
        await db.resend_webhook_guard_events.insert_one(event_doc)
        await db.system_runtime_flags.update_one(
            {"key": "resend_webhook_guard_state"},
            {
                "$set": {
                    "key": "resend_webhook_guard_state",
                    "updated_at": now_iso,
                    "severity": severity,
                    "aligned": aligned,
                    "action": action,
                    "expected_endpoint": expected_endpoint,
                    "active_matching_webhooks": active_count,
                    "last_event": event_doc,
                }
            },
            upsert=True,
        )

        if severity in {"warning", "critical"}:
            await _emit_resend_webhook_alert(
                db=db,
                now_iso=now_iso,
                severity=severity,
                title="Resend Webhook Drift Guard Alert",
                message=(
                    f"Resend webhook guard detected {severity} condition. "
                    f"aligned={aligned}, action={action}, active_matches={active_count}."
                ),
                metadata={
                    "expected_endpoint": expected_endpoint,
                    "aligned": aligned,
                    "action": action,
                    "active_matching_webhooks": active_count,
                    "alert_signature": alert_signature,
                },
            )

        await _record_scheduler_heartbeat(
            job_id,
            severity,
            f"aligned={aligned} action={action} active={active_count}",
        )
        return {
            "status": severity,
            "aligned": aligned,
            "action": action,
            "active_matching_webhooks": active_count,
            "expected_endpoint": expected_endpoint,
        }
    except Exception as exc:
        logger.error("scheduled_resend_webhook_guard failed: %s", exc)
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:220])
        return {"status": "error", "error": str(exc)[:220]}


# ── Bill Generator (hourly) ──────────────────────────────────────────────


async def scheduled_bill_generator_hourly_daemon() -> Dict[str, Any]:
    """Hourly guardrailed run for Bill Generator due recurring schedules."""
    job_id = "bill_generator_hourly_daemon"
    try:
        from routes.bill_generator import run_bill_generator_hourly_scheduler

        summary = await run_bill_generator_hourly_scheduler(triggered_by="apscheduler_hourly")
        detail = (
            f"status={summary.get('status')} generated={summary.get('generated', 0)} "
            f"failed={summary.get('failed', 0)}"
        )
        await _record_scheduler_heartbeat(job_id, "healthy", detail)
        return summary
    except Exception as exc:
        await _record_scheduler_heartbeat(job_id, "degraded", f"error={str(exc)[:220]}")
        return {"status": "error", "error": str(exc)[:220]}


# ── FedaPay webhook self-healing ─────────────────────────────────────────


async def scheduled_fedapay_webhook_self_heal() -> None:
    """Keep FedaPay webhook endpoint healthy + drain queued/retry webhook events.

    Adaptive alerting:
      - Severity escalates `healthy → warning → critical` based on
        dead-letter count, retry/dead density, queue depth, and sync
        success.
      - Admin notification fanout uses a 30-minute cooldown and a
        6-hour stale-signature override to avoid alert fatigue while
        still surfacing recurring incidents.
    """
    job_id = "fedapay_webhook_self_heal"
    try:
        from routes.db import db
        from routes.fedapay_client import sync_webhook_url
        from routes.payments import (
            run_fedapay_webhook_retry_cycle,
            run_fedapay_webhook_dead_replay_cycle,
        )

        sync_result = await sync_webhook_url()
        retry_result = await run_fedapay_webhook_retry_cycle(limit=30)
        dead_replay_result = await run_fedapay_webhook_dead_replay_cycle(limit=30)

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        window_30m = (now - timedelta(minutes=30)).isoformat()
        window_24h = (now - timedelta(hours=24)).isoformat()
        recent_retry_or_dead = await db.fedapay_webhook_events.count_documents(
            {
                "status": {"$in": ["retry", "dead"]},
                "updated_at": {"$gte": window_30m},
            }
        )
        dead_total = await db.fedapay_webhook_events.count_documents({"status": "dead"})
        dead_recent_30m = await db.fedapay_webhook_events.count_documents(
            {"status": "dead", "updated_at": {"$gte": window_30m}}
        )
        dead_recent_24h = await db.fedapay_webhook_events.count_documents(
            {"status": "dead", "updated_at": {"$gte": window_24h}}
        )
        queued_total = await db.fedapay_webhook_events.count_documents(
            {"status": {"$in": ["queued", "retry", "processing"]}}
        )
        sync_ok = str(sync_result.get("status") or "") == "ok"
        sync_error_recent = await db.fedapay_webhook_sync_history.count_documents(
            {
                "created_at": {"$gte": window_24h},
                "sync_result.status": {"$ne": "ok"},
            }
        )

        health_status = "healthy"
        if dead_recent_30m > 0 or recent_retry_or_dead >= 3 or queued_total >= 8 or dead_recent_24h >= 8:
            health_status = "warning"
        if not sync_ok:
            health_status = "warning"
        if (not sync_ok and sync_error_recent >= 3) or dead_recent_24h >= 12:
            health_status = "critical"

        alert_signature = (
            f"{dead_recent_30m}:{recent_retry_or_dead}:{queued_total}:{dead_recent_24h}:"
            f"{sync_result.get('status')}:{sync_error_recent}"
        )

        await db.fedapay_webhook_sync_history.insert_one(
            {
                "created_at": now_iso,
                "sync_result": sync_result,
                "retry_result": retry_result,
                "dead_replay_result": dead_replay_result,
                "health": {
                    "status": health_status,
                    "recent_retry_or_dead": recent_retry_or_dead,
                    "dead_total": dead_total,
                    "dead_recent_30m": dead_recent_30m,
                    "dead_recent_24h": dead_recent_24h,
                    "queued_total": queued_total,
                    "sync_ok": sync_ok,
                    "sync_error_recent_24h": sync_error_recent,
                    "alert_signature": alert_signature,
                },
            }
        )

        if health_status == "warning":
            flag_key = "fedapay_webhook_delivery_alert"
            alert_state = await db.system_runtime_flags.find_one({"key": flag_key}, {"_id": 0}) or {}
            last_alert_iso = str(alert_state.get("last_alert_at") or "")
            last_signature = str(alert_state.get("last_alert_signature") or "")
            should_alert = False
            if not last_alert_iso:
                should_alert = True
            else:
                cooldown_elapsed = last_alert_iso < (now - timedelta(minutes=30)).isoformat()
                stale_signature_elapsed = last_alert_iso < (now - timedelta(hours=6)).isoformat()
                signature_changed = alert_signature != last_signature
                should_alert = cooldown_elapsed and (signature_changed or stale_signature_elapsed)

            if should_alert:
                admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(50)
                for adm in admins:
                    uid = str(adm.get("user_id") or "")
                    if not uid:
                        continue
                    await db.notifications.insert_one(
                        {
                            "id": f"fdp_webhook_alert_{uid}_{int(now.timestamp())}",
                            "user_id": uid,
                            "type": "fedapay_webhook_delivery_alert",
                            "title": "FedaPay Webhook Delivery Alert",
                            "message": (
                                f"Detected delivery instability: dead(last 30m)={dead_recent_30m}, "
                                f"retry/dead(last 30m)={recent_retry_or_dead}, queued={queued_total}, "
                                f"dead(last 24h)={dead_recent_24h}."
                            ),
                            "read": False,
                            "created_at": now_iso,
                            "metadata": {
                                "dead_total": dead_total,
                                "dead_recent_30m": dead_recent_30m,
                                "dead_recent_24h": dead_recent_24h,
                                "recent_retry_or_dead": recent_retry_or_dead,
                                "queued_total": queued_total,
                                "sync_ok": sync_ok,
                                "sync_error_recent_24h": sync_error_recent,
                                "alert_signature": alert_signature,
                                "sync_result": sync_result,
                                "retry_result": retry_result,
                                "dead_replay_result": dead_replay_result,
                            },
                        }
                    )

                await db.system_runtime_flags.update_one(
                    {"key": flag_key},
                    {
                        "$set": {
                            "key": flag_key,
                            "last_alert_at": now_iso,
                            "last_alert_signature": alert_signature,
                            "dead_total": dead_total,
                            "dead_recent_30m": dead_recent_30m,
                            "dead_recent_24h": dead_recent_24h,
                            "recent_retry_or_dead": recent_retry_or_dead,
                            "queued_total": queued_total,
                            "sync_ok": sync_ok,
                            "sync_error_recent_24h": sync_error_recent,
                            "updated_at": now_iso,
                        }
                    },
                    upsert=True,
                )
        else:
            await db.system_runtime_flags.update_one(
                {"key": "fedapay_webhook_delivery_alert"},
                {
                    "$set": {
                        "key": "fedapay_webhook_delivery_alert",
                        "last_healthy_at": now_iso,
                        "dead_total": dead_total,
                        "dead_recent_30m": dead_recent_30m,
                        "dead_recent_24h": dead_recent_24h,
                        "recent_retry_or_dead": recent_retry_or_dead,
                        "queued_total": queued_total,
                        "sync_ok": sync_ok,
                        "sync_error_recent_24h": sync_error_recent,
                        "updated_at": now_iso,
                    }
                },
                upsert=True,
            )

        logger.info(
            "FedaPay webhook self-heal: sync_status=%s action=%s processed=%s dead=%s dead_30m=%s retry_or_dead_30m=%s queued=%s sync_err_24h=%s",
            sync_result.get("status"),
            sync_result.get("action"),
            retry_result.get("processed"),
            dead_total,
            dead_recent_30m,
            recent_retry_or_dead,
            queued_total,
            sync_error_recent,
        )
        await _record_scheduler_heartbeat(
            job_id,
            health_status,
            (
                f"sync={sync_result.get('status')} action={sync_result.get('action')} "
                f"dead30m={dead_recent_30m} retry30m={recent_retry_or_dead} "
                f"queued={queued_total} sync_err24h={sync_error_recent}"
            ),
        )
    except Exception as e:
        logger.error(f"scheduled_fedapay_webhook_self_heal failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


# ── Invoice dunning ──────────────────────────────────────────────────────


async def scheduled_invoice_dunning() -> None:
    """Daily dunning check for overdue subscriptions.

    Sends `invoice_past_due` emails at 3, 7, and 14 days past expiry.
    Idempotent per user / tier / expiry-month via a `dunning_notifications`
    record.
    """
    job_id = "invoice_dunning"
    try:
        from routes.db import db
        from utils.email_service import send_catalog_template, is_email_configured

        if not is_email_configured():
            await _record_scheduler_heartbeat(job_id, "skipped", "Email not configured")
            return

        now = datetime.now(timezone.utc)
        sent = 0

        async for u in iter_find_paginated(
            db.users,
            {
                "subscription_plan": {"$in": ["basic", "premium"]},
                "subscription_expires_at": {"$exists": True},
            },
            {
                "_id": 0,
                "user_id": 1,
                "email": 1,
                "name": 1,
                "subscription_plan": 1,
                "subscription_expires_at": 1,
            },
            max_docs=5000,
        ):
            expires_str = u.get("subscription_expires_at", "")
            if not expires_str:
                continue
            try:
                expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            except Exception:
                continue

            days_overdue = (now - expires).days
            if days_overdue <= 0:
                continue

            dunning_tier = None
            if 14 <= days_overdue < 15:
                dunning_tier = 14
            elif 7 <= days_overdue < 8:
                dunning_tier = 7
            elif 3 <= days_overdue < 4:
                dunning_tier = 3

            if dunning_tier and u.get("email"):
                already = await db.dunning_notifications.find_one(
                    {"user_id": u["user_id"], "tier": dunning_tier, "period": expires_str[:7]}
                )
                if already:
                    continue

                plan = (u.get("subscription_plan") or "premium").title()
                price = "$15.99" if "premium" in plan.lower() else "$5.99"

                await send_catalog_template(
                    recipient_email=u["email"],
                    template_key="invoice_past_due",
                    recipient_name=u.get("name", ""),
                    user_name=u.get("name", "there"),
                    amount=price,
                    plan_name=plan,
                    days_overdue=days_overdue,
                )
                await db.dunning_notifications.insert_one(
                    {
                        "user_id": u["user_id"],
                        "tier": dunning_tier,
                        "period": expires_str[:7],
                        "sent_at": now.isoformat(),
                    }
                )
                sent += 1

        logger.info(f"[dunning] Sent {sent} dunning emails")
        await _record_scheduler_heartbeat(job_id, "healthy", f"Sent {sent} dunning emails")
    except Exception as exc:
        logger.error(f"Invoice dunning failed: {exc}")
        await _record_scheduler_heartbeat(job_id, "error", str(exc)[:180])


__all__ = [
    "scheduled_bill_generator_hourly_daemon",
    "scheduled_fedapay_webhook_self_heal",
    "scheduled_resend_webhook_guard",
    "scheduled_invoice_dunning",
]


async def scheduled_stale_payment_expiry_sweep():
    """Daily hygiene: expire pending/processing payment_transactions older than
    24h (abandoned checkouts). Feeds CIA integrity score and payment dashboards."""
    job_id = "stale_payment_expiry_sweep"
    try:
        from datetime import datetime, timezone, timedelta
        from routes.db import db
        from scheduler_jobs.observability import _record_scheduler_heartbeat

        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=24)).isoformat()
        result = await db.payment_transactions.update_many(
            {"status": {"$in": ["pending", "processing"]}, "created_at": {"$lt": cutoff}},
            {"$set": {
                "status": "expired",
                "expired_reason": "abandoned_checkout_auto_sweep",
                "swept_at": now.isoformat(),
            }},
        )
        await _record_scheduler_heartbeat(job_id, "ok", f"expired={result.modified_count}")
        return {"status": "ok", "expired": result.modified_count}
    except Exception as e:
        from scheduler_jobs.observability import _record_scheduler_heartbeat

        await _record_scheduler_heartbeat(job_id, "error", str(e))
        return {"status": "error", "error": str(e)}
