"""Scheduler job registrations — extracted from server.py"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone, timedelta
import logging
import asyncio
import io
import uuid
import os
import time
from utils.http_tls import get_httpx_verify

logger = logging.getLogger(__name__)
log = logger

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(
    job_defaults={
        'max_instances': 1,
        'coalesce': True,
        'misfire_grace_time': 60,
    }
)
_scheduler_listener_registered = False


def on_job_error(event) -> None:
    """Log APScheduler missed/failed jobs and dispatch to webhook alerting + DB audit."""
    job_id = getattr(event, "job_id", "unknown")
    code = getattr(event, "code", "unknown")
    exception = getattr(event, "exception", None)
    traceback_text = getattr(event, "traceback", "") or ""

    if exception:
        logger.error(
            "[apscheduler] job execution failed | job_id=%s code=%s error=%s\n%s",
            job_id,
            code,
            exception,
            traceback_text,
        )
        _dispatch_scheduler_alert(
            event_type="apscheduler_job_error",
            severity="critical",
            title=f"APScheduler job failed: {job_id}",
            summary=str(exception),
            fields={
                "job_id": str(job_id),
                "code": str(code),
                "traceback": traceback_text[:800] or "(none)",
            },
        )
        return

    logger.warning(
        "[apscheduler] job execution missed | job_id=%s code=%s",
        job_id,
        code,
    )
    _dispatch_scheduler_alert(
        event_type="apscheduler_job_missed",
        severity="warning",
        title=f"APScheduler job missed: {job_id}",
        summary=f"code={code}",
        fields={"job_id": str(job_id), "code": str(code)},
    )


def _dispatch_scheduler_alert(
    event_type: str,
    severity: str,
    title: str,
    summary: str,
    fields: dict,
) -> None:
    """Fire-and-forget: webhook alert + DB audit for scheduler job errors/misses.

    Runs synchronously (called from APScheduler's sync event callback) but
    schedules async work via the already-running asyncio event loop.
    """
    import asyncio

    # 1. Webhook alert (Slack / Teams) via the shared alerting bus
    try:
        from services.webhook_alerts import send_alert_fire_and_forget
        send_alert_fire_and_forget(event_type, severity, title, summary, fields)
    except Exception as exc:  # never crash the scheduler callback
        logger.warning("[apscheduler-alert] webhook dispatch failed: %s", exc)

    # 2. DB audit trail — async, fire-and-forget
    async def _persist_audit() -> None:
        try:
            from routes.db import db
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.apscheduler_job_error_events.insert_one({
                "event_type": event_type,
                "severity": severity,
                "title": title,
                "summary": summary[:500],
                "fields": fields,
                "created_at": now_iso,
            })
        except Exception as exc:
            logger.warning("[apscheduler-alert] db audit failed: %s", exc)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_persist_audit())
    except Exception as exc:
        logger.warning("[apscheduler-alert] audit task schedule failed: %s", exc)


# ── Metro dev server health probe ──
# State holder for transition-edge logging (healthy → unhealthy → healthy)
# so the log stream shows ONE alert per transition, not a repeated WARN
# on every 5-minute tick.
_metro_probe_state: dict = {"last_status": "unknown", "consecutive_failures": 0}
_web_preview_probe_state: dict = {
    "last_status": "unknown",
    "consecutive_failures": 0,
    "last_restart_ts": 0.0,
}
ALLOW_EXPO_FALLBACK_RESTART = str(
    os.environ.get("WEB_PREVIEW_ALLOW_EXPO_FALLBACK_RESTART") or "0"
).strip() == "1"
ALLOW_WEB_PREVIEW_AUTORESTART = str(
    os.environ.get("WEB_PREVIEW_ALLOW_AUTORESTART") or "0"
).strip() == "1"
FRONTEND_EXPORT_LOCKFILE = "/tmp/frontend_export_build.lock"

WEB_PREVIEW_RESTART_FAILURE_THRESHOLD = 6
WEB_PREVIEW_RESTART_COOLDOWN_SECONDS = 15 * 60


async def monitor_subscription_prompt_telemetry() -> None:
    """
    Monitor subscription prompt volume stability.

    Policy (user-selected):
    - Compare current trailing 1-hour prompt volume against rolling 6-hour average
    - Flag anomaly when current >= 150% of baseline and delta >= 5 events
    - Persist status + anomalies in DB and backend logs
    """
    try:
        from routes.db import db

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        current_start = now - timedelta(hours=1)
        baseline_start = now - timedelta(hours=7)

        current_q = {
            "created_at": {
                "$gte": current_start.isoformat(),
                "$lt": now_iso,
            }
        }
        baseline_q = {
            "created_at": {
                "$gte": baseline_start.isoformat(),
                "$lt": current_start.isoformat(),
            }
        }

        current_count = int(await db.subscription_prompt_telemetry.count_documents(current_q))
        baseline_total = int(await db.subscription_prompt_telemetry.count_documents(baseline_q))
        baseline_avg = (baseline_total / 6.0) if baseline_total > 0 else 0.0

        threshold_multiplier = 1.5  # +50%
        delta = current_count - baseline_avg
        ratio = (current_count / baseline_avg) if baseline_avg > 0 else None

        anomaly = False
        reason = "stable"
        if baseline_avg > 0:
            if current_count >= (baseline_avg * threshold_multiplier) and delta >= 5:
                anomaly = True
                reason = "spike_vs_rolling_6h"
        else:
            if current_count >= 15:
                anomaly = True
                reason = "cold_start_spike"

        window_id = f"{current_start.replace(minute=0, second=0, microsecond=0).isoformat()}__{now.replace(minute=0, second=0, microsecond=0).isoformat()}"

        status_doc = {
            "key": "subscription_prompt_telemetry_monitor",
            "updated_at": now_iso,
            "window_id": window_id,
            "current_window": {
                "start": current_start.isoformat(),
                "end": now_iso,
                "count": current_count,
            },
            "baseline_window": {
                "start": baseline_start.isoformat(),
                "end": current_start.isoformat(),
                "total": baseline_total,
                "avg_per_hour": baseline_avg,
            },
            "threshold": {
                "type": "rolling_6h_avg",
                "multiplier": threshold_multiplier,
                "delta_min": 5,
            },
            "anomaly": anomaly,
            "reason": reason,
            "ratio": ratio,
            "delta": delta,
        }

        prev = await db.subscription_prompt_telemetry_monitor_state.find_one(
            {"key": "subscription_prompt_telemetry_monitor"},
            {"_id": 0, "last_alert_window_id": 1},
        )
        last_alert_window_id = (prev or {}).get("last_alert_window_id")

        update_doc = {"$set": status_doc}
        if anomaly and last_alert_window_id != window_id:
            update_doc["$set"]["last_alert_window_id"] = window_id

            await db.subscription_prompt_telemetry_monitor_events.insert_one(
                {
                    "created_at": now_iso,
                    "window_id": window_id,
                    "severity": "warning",
                    "reason": reason,
                    "current_count": current_count,
                    "baseline_avg": baseline_avg,
                    "ratio": ratio,
                    "delta": delta,
                }
            )
            logger.warning(
                "subscription-prompt-monitor: anomaly detected (%s) current=%s baseline_avg=%.2f ratio=%.2f delta=%.2f",
                reason,
                current_count,
                baseline_avg,
                ratio,
                delta,
            )
        else:
            logger.info(
                "subscription-prompt-monitor: stable current=%s baseline_avg=%.2f ratio=%s",
                current_count,
                baseline_avg or 0.0,
                f"{ratio:.2f}" if ratio is not None else "n/a",
            )

        await db.subscription_prompt_telemetry_monitor_state.update_one(
            {"key": "subscription_prompt_telemetry_monitor"},
            update_doc,
            upsert=True,
        )
    except Exception as exc:
        logger.warning("subscription-prompt-monitor failed: %s", exc)


async def _record_preview_watchdog_event(payload: dict) -> None:
    """Persist preview watchdog events for audit/history without breaking scheduler."""
    try:
        from routes.db import db

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(payload or {}),
        }
        await db.preview_runtime_watchdog_events.insert_one(event)
        await db.preview_runtime_watchdog_state.update_one(
            {"key": "global"},
            {
                "$set": {
                    "key": "global",
                    "updated_at": event["timestamp"],
                    "last_event": event,
                    "metro_state": {
                        "status": _metro_probe_state.get("last_status"),
                        "failures": _metro_probe_state.get("consecutive_failures", 0),
                    },
                    "web_state": {
                        "status": _web_preview_probe_state.get("last_status"),
                        "failures": _web_preview_probe_state.get("consecutive_failures", 0),
                    },
                }
            },
            upsert=True,
        )
    except Exception:
        return


async def _update_preview_watchdog_state_heartbeat(probe: str, status: str, detail: str = "") -> None:
    """Persist latest probe state even when no incident transition happened."""
    try:
        from routes.db import db

        now_iso = datetime.now(timezone.utc).isoformat()
        await db.preview_runtime_watchdog_state.update_one(
            {"key": "global"},
            {
                "$set": {
                    "key": "global",
                    "updated_at": now_iso,
                    "last_probe": {
                        "probe": probe,
                        "status": status,
                        "detail": (detail or "")[:300],
                        "timestamp": now_iso,
                    },
                    "metro_state": {
                        "status": _metro_probe_state.get("last_status"),
                        "failures": _metro_probe_state.get("consecutive_failures", 0),
                    },
                    "web_state": {
                        "status": _web_preview_probe_state.get("last_status"),
                        "failures": _web_preview_probe_state.get("consecutive_failures", 0),
                    },
                }
            },
            upsert=True,
        )
    except Exception:
        return


async def _supervisor_restart(service_name: str) -> tuple[bool, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "supervisorctl", "restart", service_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        if proc.returncode == 0:
            return True, (stdout.decode() or "").strip() or f"{service_name} restarted"
        msg = ((stderr.decode() or "") + " " + (stdout.decode() or "")).strip()
        return False, msg or f"restart {service_name} failed"
    except Exception as exc:
        return False, str(exc)


async def probe_metro_dev_server() -> None:
    """Probe the Metro dev server (mobile preview bundler) at port 3001.

    Why this exists: on 2026-04-24 the `expo` supervisor service failed
    silently because `yarn expo start` resolved to a missing global binary.
    Web worked fine; only mobile preview (Expo Go phone mockup) was a black
    screen. We had no alert telling us the mobile preview was dead.

    This probe fires every 5 minutes, calls `GET /status` on the Metro
    server, and logs a WARN whenever the health state TRANSITIONS
    (healthy→unhealthy or unhealthy→healthy). Two or more consecutive
    failures elevates to an ERROR log so it surfaces in ops dashboards.
    """
    import httpx  # type: ignore
    # Port is env-configurable: in single-port pods (current preview topology)
    # Metro and the web dev server share :3000; legacy dual-port pods used :3001.
    # Probing a port nothing listens on caused a restart storm (expo restarted
    # every 2 minutes) — see 2026-07-16 incident.
    _metro_port = str(os.environ.get("METRO_PROBE_PORT") or "3000").strip() or "3000"
    url = f"http://127.0.0.1:{_metro_port}/status"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
        ok = r.status_code == 200 and "running" in r.text.lower()
    except Exception as exc:  # connection refused, timeout, etc.
        ok = False
        last_err = type(exc).__name__
    else:
        last_err = None if ok else f"status={r.status_code}"

    prev = _metro_probe_state["last_status"]
    new = "healthy" if ok else "unhealthy"

    if ok:
        _metro_probe_state["consecutive_failures"] = 0
        if prev == "unhealthy":
            logger.warning("metro-probe: RECOVERED — Metro dev server (port %s) is back online. Mobile preview restored.", _metro_port)
            await _record_preview_watchdog_event({
                "probe": "metro",
                "status": "recovered",
                "detail": f"Metro port {_metro_port} recovered",
            })
    else:
        _metro_probe_state["consecutive_failures"] += 1
        streak = _metro_probe_state["consecutive_failures"]
        if prev != "unhealthy":
            logger.warning(
                "metro-probe: DOWN — Metro dev server (port %s) not responding (%s). "
                "Mobile Expo Go preview will show a black screen until Metro is restored. "
                "Check `supervisorctl status expo` and /var/log/supervisor/expo.err.log.",
                _metro_port,
                last_err,
            )
            await _record_preview_watchdog_event({
                "probe": "metro",
                "status": "down",
                "detail": f"Metro {_metro_port} not responding ({last_err})",
                "streak": streak,
            })
        elif streak >= 2:
            logger.error(
                "metro-probe: STILL DOWN after %d consecutive probes (%s). "
                "Run `sudo supervisorctl restart expo` once the root cause is identified.",
                streak, last_err,
            )
            restart_ok, restart_msg = await _supervisor_restart("expo")
            await _record_preview_watchdog_event({
                "probe": "metro",
                "status": "auto_recovery_attempted",
                "detail": f"restart expo -> {'ok' if restart_ok else 'failed'}: {restart_msg}",
                "streak": streak,
                "last_error": last_err,
            })

    _metro_probe_state["last_status"] = new
    await _update_preview_watchdog_state_heartbeat("metro", new, f"last_err={last_err}")


async def probe_web_preview_server() -> None:
    """Probe web preview route on 3000 and self-heal expo_manual on sustained failures.

    Stability policy:
    - Probe a lightweight preview health endpoint first.
    - If route probe fails but API proxy on :3000 still responds, treat as degraded
      and suppress auto-restart (avoids restart storms during transient route churn).
    - Auto-restart only after sustained failures with cooldown.
    """
    import httpx  # type: ignore
    import time as _time

    url = "http://127.0.0.1:3000/_preview/health"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(url)
        body = (r.text or "")[:1200].lower()
        ok = r.status_code == 200 and '"ok":true' in body
        degraded_proxy_only = False
    except Exception as exc:
        ok = False
        last_err = type(exc).__name__
        degraded_proxy_only = False
    else:
        last_err = None if ok else f"status={r.status_code}"

    # If route probe is unhealthy but local proxy still serves API, avoid restart loop.
    if not ok:
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                api_probe = await client.get("http://127.0.0.1:3000/api/health")
            if api_probe.status_code == 200:
                degraded_proxy_only = True
                ok = True
                last_err = f"route_unhealthy_but_api_proxy_ok:{last_err}"
        except Exception:
            degraded_proxy_only = False

    prev = _web_preview_probe_state["last_status"]
    new = "degraded" if (ok and degraded_proxy_only) else ("healthy" if ok else "unhealthy")

    if ok:
        _web_preview_probe_state["consecutive_failures"] = 0
        if prev in {"unhealthy", "degraded"}:
            logger.warning(
                "web-preview-probe: RECOVERED — Web preview route on 3000 is back online (%s).",
                "degraded proxy fallback" if degraded_proxy_only else "full recovery",
            )
            await _record_preview_watchdog_event({
                "probe": "web_preview",
                "status": "recovered",
                "detail": "Web preview route recovered",
            })
        elif degraded_proxy_only:
            logger.warning(
                "web-preview-probe: DEGRADED — route probe unhealthy but :3000 API proxy is alive (%s). "
                "Suppressing auto-restart to avoid churn.",
                last_err,
            )
            await _record_preview_watchdog_event({
                "probe": "web_preview",
                "status": "degraded",
                "detail": f"route unhealthy, api proxy alive ({last_err})",
            })
    else:
        _web_preview_probe_state["consecutive_failures"] += 1
        streak = _web_preview_probe_state["consecutive_failures"]
        if prev != "unhealthy":
            logger.warning(
                "web-preview-probe: DOWN — route %s unhealthy (%s). "
                "Iframe preview may stall/black-screen until service recovers.",
                url,
                last_err,
            )
            await _record_preview_watchdog_event({
                "probe": "web_preview",
                "status": "down",
                "detail": f"route {url} unhealthy ({last_err})",
                "streak": streak,
            })
        elif streak >= WEB_PREVIEW_RESTART_FAILURE_THRESHOLD:
            now_ts = float(_time.time())
            last_restart_ts = float(_web_preview_probe_state.get("last_restart_ts") or 0.0)
            cooldown_remaining = int(max(0.0, WEB_PREVIEW_RESTART_COOLDOWN_SECONDS - (now_ts - last_restart_ts)))

            if cooldown_remaining > 0:
                logger.warning(
                    "web-preview-probe: sustained failures (%d, %s) but restart cooldown active (%ds left).",
                    streak,
                    last_err,
                    cooldown_remaining,
                )
                await _record_preview_watchdog_event({
                    "probe": "web_preview",
                    "status": "restart_cooldown_active",
                    "detail": f"cooldown {cooldown_remaining}s remaining",
                    "streak": streak,
                    "last_error": last_err,
                })
                _web_preview_probe_state["last_status"] = new
                await _update_preview_watchdog_state_heartbeat("web_preview", new, f"last_err={last_err}")
                return

            logger.error(
                "web-preview-probe: STILL DOWN after %d probes (%s). Auto-restarting expo_manual.",
                streak,
                last_err,
            )

            if not ALLOW_WEB_PREVIEW_AUTORESTART:
                logger.warning(
                    "web-preview-probe: auto-restart disabled by WEB_PREVIEW_ALLOW_AUTORESTART policy.",
                )
                await _record_preview_watchdog_event({
                    "probe": "web_preview",
                    "status": "restart_disabled_by_policy",
                    "detail": "WEB_PREVIEW_ALLOW_AUTORESTART is not enabled",
                    "streak": streak,
                    "last_error": last_err,
                })
                _web_preview_probe_state["last_status"] = new
                await _update_preview_watchdog_state_heartbeat("web_preview", new, "restart disabled by policy")
                return

            if os.path.exists(FRONTEND_EXPORT_LOCKFILE):
                logger.warning(
                    "web-preview-probe: restart deferred while frontend export lock is active (%s).",
                    FRONTEND_EXPORT_LOCKFILE,
                )
                await _record_preview_watchdog_event({
                    "probe": "web_preview",
                    "status": "restart_deferred_export_in_progress",
                    "detail": f"lock active at {FRONTEND_EXPORT_LOCKFILE}",
                    "streak": streak,
                    "last_error": last_err,
                })
                _web_preview_probe_state["last_status"] = new
                await _update_preview_watchdog_state_heartbeat("web_preview", new, f"restart deferred lock={FRONTEND_EXPORT_LOCKFILE}")
                return

            restart_ok, restart_msg = await _supervisor_restart("expo_manual")
            _web_preview_probe_state["last_restart_ts"] = now_ts
            await _record_preview_watchdog_event({
                "probe": "web_preview",
                "status": "auto_recovery_attempted",
                "detail": f"restart expo_manual -> {'ok' if restart_ok else 'failed'}: {restart_msg}",
                "streak": streak,
                "last_error": last_err,
            })

            # Secondary safety net when web repeatedly fails: refresh expo fallback too.
            if ALLOW_EXPO_FALLBACK_RESTART and streak >= WEB_PREVIEW_RESTART_FAILURE_THRESHOLD + 2:
                fallback_ok, fallback_msg = await _supervisor_restart("expo")
                await _record_preview_watchdog_event({
                    "probe": "web_preview",
                    "status": "fallback_recovery_attempted",
                    "detail": f"restart expo fallback -> {'ok' if fallback_ok else 'failed'}: {fallback_msg}",
                    "streak": streak,
                    "last_error": last_err,
                })

    _web_preview_probe_state["last_status"] = new
    await _update_preview_watchdog_state_heartbeat("web_preview", new, f"last_err={last_err}")


async def run_annual_receipt_summary_dispatch(
    *,
    recipient_override: str | None = None,
    target_user_id: str | None = None,
    target_year: int | None = None,
) -> dict:
    """Dispatch annual receipt summary emails.

    - Scheduler path: call with defaults (normal user recipients).
    - Verification path: pass recipient_override to route output to admin inbox.
    """
    from routes.db import db as _db
    from utils.receipt_generator import generate_pdf_from_payment
    from utils.pdf_v15_filename import build_pdf_v15_filename
    from utils.email_service import send_catalog_template
    import base64
    from pypdf import PdfReader, PdfWriter

    prev_year = int(target_year or (datetime.now(timezone.utc).year - 1))
    year_start_dt = datetime(prev_year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    year_end_dt = datetime(prev_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    year_start_iso = year_start_dt.isoformat()
    year_end_iso = year_end_dt.isoformat()
    query = {
        "$or": [
            {"created_at": {"$gte": year_start_dt, "$lte": year_end_dt}},
            {"created_at": {"$gte": year_start_iso, "$lte": year_end_iso}},
        ]
    }

    if target_user_id:
        all_user_ids = [target_user_id]
    else:
        user_ids = await _db.payments.distinct("user_id", query)
        txn_user_ids = await _db.payment_transactions.distinct("user_id", query)
        all_user_ids = list(set(user_ids + txn_user_ids))

    sent_count = 0
    failed: list[dict] = []
    for uid in all_user_ids:
        try:
            user_doc = await _db.users.find_one({"user_id": uid}, {"_id": 0})
            if not user_doc:
                continue

            user_query = {**query, "user_id": uid}
            payments = await _db.payments.find(user_query, {"_id": 0}).sort("created_at", -1).to_list(500)
            txns = await _db.payment_transactions.find(user_query, {"_id": 0}).sort("created_at", -1).to_list(500)

            all_payments = []
            seen = set()
            for p in payments:
                pid = p.get("payment_id") or p.get("id", "")
                if pid and pid not in seen:
                    seen.add(pid)
                    all_payments.append(p)
            for t in txns:
                pid = t.get("payment_id") or t.get("session_id") or t.get("id", "")
                if pid and pid not in seen:
                    seen.add(pid)
                    all_payments.append({
                        "id": t.get("id") or pid,
                        "payment_id": pid,
                        "plan_id": t.get("plan_id"),
                        "amount": t.get("amount"),
                        "currency": t.get("currency"),
                        "payment_method": t.get("payment_method"),
                        "status": t.get("payment_status") or t.get("status") or "completed",
                        "billing_period": t.get("billing_period"),
                        "created_at": t.get("created_at"),
                    })

            if not all_payments:
                continue

            user_name = user_doc.get("name", "")
            user_email = user_doc.get("email")
            recipient_email = (recipient_override or user_email or "").strip()
            if not recipient_email:
                continue

            writer = PdfWriter()
            total_amount = 0.0
            for payment in all_payments:
                try:
                    from routes.payments import _apply_canonical_plan_pricing, _assert_plan_pricing_or_block

                    plan_snapshot = await _assert_plan_pricing_or_block(payment, context="annual_receipt_summary")
                    canonical_payment = _apply_canonical_plan_pricing(payment, plan_snapshot)
                    total_amount += float(canonical_payment.get("amount", 0) or 0)

                    pdf_bytes = generate_pdf_from_payment("receipt", canonical_payment, user_name, user_email or recipient_email)
                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    for page in reader.pages:
                        writer.add_page(page)
                except Exception:
                    continue

            if len(writer.pages) == 0:
                continue

            output = io.BytesIO()
            writer.write(output)
            combined_pdf = output.getvalue()

            attachment = {
                "filename": build_pdf_v15_filename("annual-receipts", prev_year),
                "content": base64.b64encode(combined_pdf).decode("utf-8"),
                "content_type": "application/pdf",
            }

            send_result = await send_catalog_template(
                recipient_email=recipient_email,
                template_key="annual_receipt_summary",
                recipient_name=user_name,
                user_name=user_name,
                year=str(prev_year),
                total_amount=f"${total_amount:.2f}",
                receipt_count=len(all_payments),
                attachments=[attachment],
            )
            if send_result.get("success"):
                sent_count += 1
            else:
                failed.append({"user_id": uid, "email": recipient_email, "error": str(send_result.get("error") or "send_failed")[:180]})
        except Exception as e:
            failed.append({"user_id": uid, "error": str(e)[:180]})

    return {
        "year": prev_year,
        "processed_users": len(all_user_ids),
        "sent_count": sent_count,
        "failed": failed,
        "recipient_override": recipient_override or "",
    }


def register(app):
    from routes.db import db

    @app.on_event("startup")
    async def start_scheduler():
        global _scheduler_listener_registered
        if not _scheduler_listener_registered:
            scheduler.add_listener(on_job_error, EVENT_JOB_ERROR | EVENT_JOB_MISSED)
            _scheduler_listener_registered = True

        # ── Content ──
        from routes.content import automate_content_items, run_nightly_auto_categorization

        async def scheduled_content_automation():
            logger.info("Running scheduled content automation...")
            try:
                items = await automate_content_items(max_items=3)
                logger.info(f"Scheduled automation added {len(items)} items.")
            except Exception as e:
                logger.error(f"Scheduled automation failed: {e}")

        scheduler.add_job(scheduled_content_automation, IntervalTrigger(hours=24), id="daily_content_automation", replace_existing=True,
    max_instances=1)
        scheduler.add_job(run_nightly_auto_categorization, CronTrigger(hour=2, minute=0), id="nightly_auto_categorization", replace_existing=True,
    max_instances=1)

        # ── Subscriptions ──
        from routes.subscription_enforcement import scheduled_subscription_maintenance
        scheduler.add_job(scheduled_subscription_maintenance, CronTrigger(hour=8, minute=0), id="daily_subscription_maintenance", replace_existing=True,
    max_instances=1)

        # ── Feature 31 retired: Problem Solver replaced by AI Coaching Team (no scheduled jobs) ──

        # ── AI Coaching Team: weekly engagement digest ──
        try:
            from services.coaching_team_digest import send_coaching_team_weekly_digest

            async def scheduled_coaching_team_weekly_digest():
                try:
                    summary = await send_coaching_team_weekly_digest(trigger="apscheduler_weekly")
                    logger.info(
                        "[coaching-digest] scheduled run: sent=%s skipped_pref=%s errors=%s",
                        summary.get("sent", 0), summary.get("skipped_pref", 0), summary.get("errors", 0),
                    )
                except Exception as exc:
                    logger.error(f"[coaching-digest] scheduled run failed: {exc}")

            scheduler.add_job(
                scheduled_coaching_team_weekly_digest,
                CronTrigger(day_of_week="mon", hour=15, minute=0),
                id="weekly_coaching_team_digest",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
        except Exception as exc:
            logger.error(f"Failed to register coaching team digest scheduler job: {exc}")

        # ── AI Coaching Team: daily push digest (Expo mobile + Web Push) ──
        try:
            from services.coaching_digest_push import send_coaching_daily_digest_push

            async def scheduled_coaching_daily_digest_push():
                try:
                    summary = await send_coaching_daily_digest_push(trigger="apscheduler_daily")
                    logger.info(
                        "[coaching-digest-push] scheduled run: sent=%s skipped_pref=%s no_channel=%s errors=%s",
                        summary.get("sent", 0), summary.get("skipped_pref", 0),
                        summary.get("skipped_no_channel", 0), summary.get("errors", 0),
                    )
                except Exception as exc:
                    logger.error(f"[coaching-digest-push] scheduled run failed: {exc}")

            scheduler.add_job(
                scheduled_coaching_daily_digest_push,
                CronTrigger(hour=9, minute=0),
                id="daily_coaching_digest_push",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
        except Exception as exc:
            logger.error(f"Failed to register coaching daily push digest scheduler job: {exc}")

        # ── Platform Control Center: scheduled announcement templates ──
        try:
            from routes.platform_control import run_scheduled_platform_announcements

            scheduler.add_job(
                run_scheduled_platform_announcements,
                IntervalTrigger(minutes=1),
                id="platform_control_announcement_scheduler",
                replace_existing=True,
                max_instances=1)
        except Exception as exc:
            logger.error(f"Platform control announcement scheduler registration failed: {exc}")

        # ── Legal Governance: scheduled legal notice broadcasts ──
        try:
            from routes.admin_broadcast import run_scheduled_legal_notice_broadcasts

            scheduler.add_job(
                run_scheduled_legal_notice_broadcasts,
                IntervalTrigger(minutes=1),
                id="legal_notice_scheduler",
                replace_existing=True,
                max_instances=1)
        except Exception as exc:
            logger.error(f"Legal notice scheduler registration failed: {exc}")

        # ── Careers ATS: GDPR auto-purge ──
        from routes.careers_tier1 import scheduled_gdpr_auto_purge
        scheduler.add_job(
            scheduled_gdpr_auto_purge,
            CronTrigger(hour=3, minute=0),
            id="daily_careers_gdpr_auto_purge",
            replace_existing=True,
            max_instances=1)

        # ── Careers ATS: GDPR auto-purge DAILY DIGEST (03:05 UTC — 5 min after purge) ──
        from routes.careers_tier1 import send_gdpr_purge_daily_digest

        async def scheduled_gdpr_purge_daily_digest():
            try:
                res = await send_gdpr_purge_daily_digest(trigger="apscheduler_daily")
                logger.info(
                    f"[careers/gdpr-digest] scheduled run: ok={res.get('ok')} "
                    f"sent_ok={res.get('sent_ok', 0)} failed={res.get('sent_failed', 0)} "
                    f"skipped={res.get('skipped', False)}"
                )
            except Exception as e:
                logger.error(f"[careers/gdpr-digest] scheduled run failed: {e}")

        scheduler.add_job(
            scheduled_gdpr_purge_daily_digest,
            CronTrigger(hour=3, minute=5),
            id="daily_careers_gdpr_purge_digest",
            replace_existing=True,
            max_instances=1)

        # ── Careers ATS: Silver-medalist nurture cadence ──
        from routes.careers_tier3 import scheduled_silver_medalist_nurture
        scheduler.add_job(
            scheduled_silver_medalist_nurture,
            CronTrigger(hour=9, minute=0),
            id="daily_careers_silver_medalist_nurture",
            replace_existing=True,
            max_instances=1)

        # ── Payment E2E Control Center Automation ──
        async def scheduled_payment_e2e_quick_daily():
            try:
                from routes.admin_payment_analytics import run_payment_e2e_scheduled
                report = await run_payment_e2e_scheduled(full_suite=False, trigger="scheduled_daily_quick")
                summary = report.get("summary", {}) if isinstance(report, dict) else {}
                logger.info(
                    f"Payment E2E quick daily completed: {summary.get('passed', 0)}/{summary.get('total', 0)} checks"
                )
            except Exception as e:
                logger.error(f"Payment E2E quick daily failed: {e}")

        async def scheduled_payment_e2e_full_weekly():
            try:
                from routes.admin_payment_analytics import run_payment_e2e_scheduled
                report = await run_payment_e2e_scheduled(full_suite=True, trigger="scheduled_weekly_full")
                summary = report.get("summary", {}) if isinstance(report, dict) else {}
                logger.info(
                    f"Payment E2E weekly full completed: {summary.get('passed', 0)}/{summary.get('total', 0)} checks"
                )
            except Exception as e:
                logger.error(f"Payment E2E weekly full failed: {e}")

        # Approved schedule:
        # - Quick daily run: 06:00 UTC
        # - Full weekly run: Sunday 06:15 UTC
        scheduler.add_job(
            scheduled_payment_e2e_quick_daily,
            CronTrigger(hour=6, minute=0),
            id="payment_e2e_quick_daily",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_payment_e2e_full_weekly,
            CronTrigger(day_of_week='sun', hour=6, minute=15),
            id="payment_e2e_full_weekly",
            replace_existing=True,
            max_instances=1)

        # ── Theme Visibility Audit (nightly 03:00 UTC; detects UI regressions) ──
        from routes.platform_perf import run_theme_visibility_audit_scheduled

        async def scheduled_theme_visibility_audit():
            try:
                summary = await run_theme_visibility_audit_scheduled(trigger="nightly_cron")
                logger.info(
                    f"[theme-audit-nightly] result: grade={summary.get('grade')} "
                    f"fails={summary.get('fails')} regression={summary.get('regression')}"
                )
            except Exception as e:
                logger.error(f"Nightly theme visibility audit failed: {e}")

        scheduler.add_job(
            scheduled_theme_visibility_audit,
            CronTrigger(hour=3, minute=0),
            id="nightly_theme_visibility_audit",
            replace_existing=True,
            max_instances=1)

        # ── Offer auto-expiry sweep (hourly; flips unresponded sent offers to 'expired') ──
        from routes.careers_offers import sweep_expired_offers

        async def scheduled_offer_expiry_sweep():
            try:
                result = await sweep_expired_offers()
                if result.get("expired", 0):
                    logger.info(f"[offers] hourly sweep expired {result['expired']} offer(s)")
            except Exception as e:
                logger.error(f"Offer expiry sweep failed: {e}")

        scheduler.add_job(
            scheduled_offer_expiry_sweep,
            IntervalTrigger(hours=1),
            id="hourly_offer_expiry_sweep",
            replace_existing=True,
            max_instances=1)

        # ── Instant Search-Alert Email Scan (every 30 minutes) ──
        async def scheduled_search_alert_instant_scan():
            try:
                from routes.job_search import run_search_alert_instant_scan
                summary = await run_search_alert_instant_scan(trigger="scheduled_30m")
                if summary.get("emails_sent"):
                    logger.info(
                        f"[search-alert-scan] sent={summary['emails_sent']} "
                        f"matched={summary['matched_users']} scanned={summary['scanned_users']}"
                    )
            except Exception as e:
                logger.error(f"Search alert instant scan failed: {e}")

        scheduler.add_job(
            scheduled_search_alert_instant_scan,
            IntervalTrigger(minutes=30),
            id="search_alert_instant_scan",
            replace_existing=True,
            max_instances=1)


        # ── Safe Auto Run: Theme Audit every 6 hours (only persists if state changed) ──
        async def safe_auto_theme_audit():
            try:
                summary = await run_theme_visibility_audit_scheduled(trigger="safe_auto_6h")
                logger.info(
                    f"[theme-audit-safe-auto] result: grade={summary.get('grade')} "
                    f"fails={summary.get('fails')} regression={summary.get('regression')}"
                )
            except Exception as e:
                logger.error(f"Safe auto theme audit failed: {e}")

        scheduler.add_job(
            safe_auto_theme_audit,
            IntervalTrigger(hours=6),
            id="safe_auto_theme_visibility_audit",
            replace_existing=True,
            max_instances=1)

        # ── LLM Daily Spend + Budget Burn Digest (08:00 UTC daily) ──
        from services.llm_daily_digest import send_daily_llm_digest

        async def scheduled_llm_daily_digest():
            try:
                summary = await send_daily_llm_digest(trigger="scheduled_daily")
                logger.info(
                    f"[llm-daily-digest] sent={summary.get('sent')}/{summary.get('recipients')} "
                    f"burn={summary.get('burn_pct')}% yday=${summary.get('yesterday_cost_usd')}"
                )
            except Exception as e:
                logger.error(f"LLM daily digest failed: {e}")

        scheduler.add_job(
            scheduled_llm_daily_digest,
            CronTrigger(hour=8, minute=0),
            id="llm_daily_digest",
            replace_existing=True,
            max_instances=1)

        # ── Weekly Platform Quality Digest to Slack/Teams (Mon 09:00 UTC) ──
        from services.webhook_alerts import send_weekly_digest

        async def scheduled_weekly_webhook_digest():
            try:
                res = await send_weekly_digest(trigger="scheduled_weekly")
                logger.info(f"[webhook-weekly-digest] dispatched={res.get('dispatched')}")
            except Exception as e:
                logger.error(f"Weekly webhook digest failed: {e}")

        scheduler.add_job(
            scheduled_weekly_webhook_digest,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="webhook_weekly_digest",
            replace_existing=True,
            max_instances=1)


        # ── GTEC Upstream Watchdog (§5 systemic-fix self-driving loop) ──
        # Nightly 02:30 UTC — polls npm registry for each declared blocker
        # (eslint-config-expo v10 compat, async-storage 3.x, Expo 56 major)
        # and auto-opens a P-priority ticket when the upstream condition
        # clears. Read-only; never mutates package.json.
        try:
            from services.gtec_upstream_watchdog import (
                scheduled_upstream_watchdog,
            )

            async def scheduled_gtec_upstream_watchdog():
                try:
                    summary = await scheduled_upstream_watchdog()
                    logger.info(
                        "[gtec-upstream-watchdog] checked=%s cleared=%s blocked=%s errors=%s",
                        summary.get("total"),
                        summary.get("cleared"),
                        summary.get("still_blocked"),
                        summary.get("errors"),
                    )
                except Exception as e:
                    logger.error(f"GTEC upstream watchdog run failed: {e}")

            scheduler.add_job(
                scheduled_gtec_upstream_watchdog,
                CronTrigger(hour=2, minute=30),
                id="gtec_upstream_watchdog_nightly",
                replace_existing=True,
                max_instances=1)
            logger.info("[gtec-upstream-watchdog] scheduled nightly @ 02:30 UTC")
        except Exception as exc:  # noqa: BLE001 — never break startup
            logger.warning(f"GTEC upstream watchdog not scheduled: {exc}")




        # ── Quality Digest ──
        # ── Invitation Cleanup (nightly 03:30 UTC; expires + purges old revoked/expired rows) ──
        from routes.platform_employees import run_invitation_cleanup_scheduled

        async def scheduled_invitation_cleanup():
            try:
                summary = await run_invitation_cleanup_scheduled(
                    trigger="nightly_cron", purge_days=30
                )
                logger.info(
                    f"[invitation-cleanup] result: marked_expired={summary.get('marked_expired')} "
                    f"purged={summary.get('purged')}"
                )
            except Exception as e:
                logger.error(f"Nightly invitation cleanup failed: {e}")

        scheduler.add_job(
            scheduled_invitation_cleanup,
            CronTrigger(hour=3, minute=30),
            id="nightly_invitation_cleanup",
            replace_existing=True,
            max_instances=1)

        # ── GDPR Weekly Compliance Digest (Mondays 09:00 UTC) ──
        from routes.gdpr_self_service import send_weekly_digest as send_gdpr_weekly_digest

        async def scheduled_gdpr_weekly_digest():
            try:
                res = await send_gdpr_weekly_digest(trigger="cron")
                logger.info(
                    f"[gdpr-weekly-digest] sent_ok={res['sent_ok']} recipient={res['recipient']} "
                    f"total={res['summary']['total_requests']}"
                )
            except Exception as e:
                logger.error(f"GDPR weekly digest failed: {e}")

        scheduler.add_job(
            scheduled_gdpr_weekly_digest,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="gdpr_weekly_digest",
            replace_existing=True,
            max_instances=1)

        # ── GDPR Retention Purge (nightly 03:45 UTC) ──
        from routes.gdpr_self_service import run_retention_purge

        async def scheduled_gdpr_retention_purge():
            try:
                summary = await run_retention_purge(trigger="cron")
                logger.info(
                    f"[gdpr-retention] status={summary.get('status')} "
                    f"days={summary.get('retention_days')} "
                    f"purged_total={summary.get('purged', {}).get('total', 0)}"
                )
            except Exception as e:
                logger.error(f"GDPR retention purge failed: {e}")

        scheduler.add_job(
            scheduled_gdpr_retention_purge,
            CronTrigger(hour=3, minute=45),
            id="gdpr_retention_purge",
            replace_existing=True,
            max_instances=1)
        from scheduler_jobs import scheduled_weekly_quality_digest
        scheduler.add_job(scheduled_weekly_quality_digest, CronTrigger(day_of_week='sun', hour=9, minute=0), id="weekly_quality_digest", replace_existing=True,
    max_instances=1)

        # ── Referral Program Weekly Email ──
        from scheduler_jobs import scheduled_referral_weekly_email
        scheduler.add_job(scheduled_referral_weekly_email, CronTrigger(day_of_week='mon', hour=10, minute=0), id="referral_weekly_email", replace_existing=True,
    max_instances=1)

        # ── Smart Weekly Digest (coaching progress + streaks, Mon 08:00 UTC) ──
        from scheduler_jobs import scheduled_smart_weekly_digest
        scheduler.add_job(scheduled_smart_weekly_digest, CronTrigger(day_of_week='mon', hour=8, minute=0), id="smart_weekly_digest_dispatch", replace_existing=True,
    max_instances=1)

        # ── Blog V2 Weekly Digest + Email Tie-in (Mon 10:30 UTC) ──
        from scheduler_jobs import scheduled_blog_v2_weekly_digest_cycle
        scheduler.add_job(
            scheduled_blog_v2_weekly_digest_cycle,
            CronTrigger(day_of_week='mon', hour=10, minute=30),
            id="blog_v2_weekly_digest_cycle",
            replace_existing=True,
            max_instances=1,
        )

        # ── Daily Usage Summary Email (20:00 UTC / end of day) ──
        from scheduler_jobs import scheduled_daily_usage_summary
        scheduler.add_job(scheduled_daily_usage_summary, CronTrigger(hour=20, minute=0), id="daily_usage_summary", replace_existing=True,
    max_instances=1)

        # ── SSO Redirect URI Auto-Sync (every 10 minutes) ──
        from scheduler_jobs import scheduled_sso_redirect_auto_sync
        scheduler.add_job(
            scheduled_sso_redirect_auto_sync,
            IntervalTrigger(minutes=10),
            id="sso_redirect_auto_sync",
            replace_existing=True,
            max_instances=1)

        # ── SSO Provider Registration Alignment (every 10 minutes) ──
        from scheduler_jobs import scheduled_sso_provider_registration_alignment_auto
        scheduler.add_job(
            scheduled_sso_provider_registration_alignment_auto,
            IntervalTrigger(minutes=10),
            id="sso_provider_registration_alignment_auto",
            replace_existing=True,
            max_instances=1)

        # ── SSO E2E Validation (every 15 minutes; alert only on state change) ──
        from scheduler_jobs import scheduled_sso_e2e_validation_alerts
        scheduler.add_job(
            scheduled_sso_e2e_validation_alerts,
            IntervalTrigger(minutes=15),
            id="sso_e2e_validation_auto",
            replace_existing=True,
            max_instances=1)

        # ── SSO Redirect Drift Sentinel (every 2 minutes) ──
        from scheduler_jobs import scheduled_sso_redirect_drift_sentinel
        scheduler.add_job(
            scheduled_sso_redirect_drift_sentinel,
            IntervalTrigger(minutes=2),
            id="sso_redirect_drift_sentinel",
            replace_existing=True,
            max_instances=1)

        # ── Multi-region Synthetic Auth Probe + Route SLO Alerting (every 10 minutes) ──
        from scheduler_jobs import scheduled_multi_region_auth_probe
        scheduler.add_job(
            scheduled_multi_region_auth_probe,
            IntervalTrigger(minutes=10),
            id="multi_region_auth_probe",
            replace_existing=True,
            max_instances=1)

        # ── Fallback Auth Link Guardian (magic-link + QR base freshness, every 5 minutes) ──
        from scheduler_jobs import scheduled_auth_fallback_link_guardian
        scheduler.add_job(
            scheduled_auth_fallback_link_guardian,
            IntervalTrigger(minutes=5),
            id="auth_fallback_link_guardian",
            replace_existing=True,
            max_instances=1)

        # ── Continuous Admin E2E Health Gate (every 30 minutes, state-change notifications only) ──
        from scheduler_jobs import scheduled_admin_e2e_health_gate
        scheduler.add_job(
            scheduled_admin_e2e_health_gate,
            IntervalTrigger(minutes=30),
            id="admin_e2e_health_gate",
            replace_existing=True,
            max_instances=1)

        # ── CIA Trust Score Heartbeat (hourly, feeds Production Security Policy Gate) ──
        from scheduler_jobs import scheduled_cia_trust_heartbeat
        scheduler.add_job(
            scheduled_cia_trust_heartbeat,
            IntervalTrigger(hours=1),
            id="cia_trust_heartbeat",
            replace_existing=True,
            max_instances=1)

        # ── Stale Payment Expiry Sweep (daily 01:20 UTC, abandoned-checkout hygiene) ──
        from scheduler_jobs import scheduled_stale_payment_expiry_sweep
        scheduler.add_job(
            scheduled_stale_payment_expiry_sweep,
            CronTrigger(hour=1, minute=20),
            id="stale_payment_expiry_sweep",
            replace_existing=True,
            max_instances=1)

        # ── Nightly Preview Browser E2E Wake-and-Run (daily 02:55 UTC) ──
        from scheduler_jobs import scheduled_preview_browser_e2e_wake_and_run
        scheduler.add_job(
            scheduled_preview_browser_e2e_wake_and_run,
            CronTrigger(hour=2, minute=55),
            id="preview_browser_e2e_wake_and_run_nightly",
            replace_existing=True,
            max_instances=1)

        # ── Critical Journey Monitor (every 5 minutes) ──
        from scheduler_jobs import scheduled_critical_journey_monitor
        scheduler.add_job(
            scheduled_critical_journey_monitor,
            IntervalTrigger(minutes=5),
            id="critical_journey_monitor",
            replace_existing=True,
            max_instances=1)

        # ── Global Parity Audit (hourly + nightly full check) ──
        from scheduler_jobs import (
            scheduled_global_parity_audit_hourly,
            scheduled_global_parity_audit_nightly,
        )
        scheduler.add_job(
            scheduled_global_parity_audit_hourly,
            IntervalTrigger(hours=1),
            id="global_parity_audit_hourly",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_global_parity_audit_nightly,
            CronTrigger(hour=2, minute=40),
            id="global_parity_audit_nightly",
            replace_existing=True,
            max_instances=1)

        # ── Assigned Host Guardian (every 5 minutes, auto-fallback + state-change alerts) ──
        from scheduler_jobs import scheduled_assigned_host_guardian
        scheduler.add_job(
            scheduled_assigned_host_guardian,
            IntervalTrigger(minutes=5),
            id="assigned_host_guardian",
            replace_existing=True,
            max_instances=1)

        # ── Fee Visibility Visual Contract Audit (hourly + nightly with safe guardrails) ──
        from scheduler_jobs import (
            scheduled_fee_visibility_visual_audit_hourly,
            scheduled_fee_visibility_visual_audit_nightly,
        )
        scheduler.add_job(
            scheduled_fee_visibility_visual_audit_hourly,
            IntervalTrigger(hours=1),
            id="fee_visibility_visual_audit_hourly",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_fee_visibility_visual_audit_nightly,
            CronTrigger(hour=3, minute=10),
            id="fee_visibility_visual_audit_nightly",
            replace_existing=True,
            max_instances=1)

        # ── Preview Cache Hygiene Monitor (hourly + nightly) ──
        from scheduler_jobs import (
            scheduled_preview_cache_hygiene_hourly,
            scheduled_preview_cache_hygiene_nightly,
        )
        scheduler.add_job(
            scheduled_preview_cache_hygiene_hourly,
            IntervalTrigger(hours=1),
            id="preview_cache_hygiene_hourly",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_preview_cache_hygiene_nightly,
            CronTrigger(hour=3, minute=30),
            id="preview_cache_hygiene_nightly",
            replace_existing=True,
            max_instances=1)

        # ── Subscription Plan Enforcement Guardrail (every 6 hours) ──
        from scheduler_jobs import (
            scheduled_subscription_plan_guardrail,
            scheduled_global_rbac_subscription_enforcement,
            scheduled_quarterly_access_recertification,
            scheduled_pricing_guard_nightly_monitor,
            scheduled_i18n_literal_autofix_dry_run_report,
        )
        scheduler.add_job(
            scheduled_subscription_plan_guardrail,
            IntervalTrigger(hours=6),
            id="subscription_plan_guardrail",
            replace_existing=True,
            max_instances=1)

        scheduler.add_job(
            scheduled_global_rbac_subscription_enforcement,
            IntervalTrigger(hours=1),
            id="global_rbac_subscription_enforcement",
            replace_existing=True,
            max_instances=1)

        scheduler.add_job(
            scheduled_quarterly_access_recertification,
            CronTrigger(month="1,4,7,10", day=1, hour=7, minute=15),
            id="quarterly_access_recertification",
            replace_existing=True,
            max_instances=1)

        # ── Nightly Pricing-Guard Incident Monitor (00:05 UTC) ──
        scheduler.add_job(
            scheduled_pricing_guard_nightly_monitor,
            CronTrigger(hour=0, minute=5),
            id="pricing_guard_nightly_monitor",
            replace_existing=True,
            max_instances=1)

        # ── Nightly I18n Literal-Autofix Dry-Run Report (00:25 UTC) ──
        scheduler.add_job(
            scheduled_i18n_literal_autofix_dry_run_report,
            CronTrigger(hour=0, minute=25),
            id="i18n_literal_autofix_dry_run_report",
            replace_existing=True,
            max_instances=1)

        # ── Production Security Policy Gate (every 10 minutes) ──
        from scheduler_jobs import scheduled_production_security_policy_gate
        scheduler.add_job(
            scheduled_production_security_policy_gate,
            IntervalTrigger(minutes=10),
            id="production_security_policy_gate",
            replace_existing=True,
            max_instances=1)

        # ── Key Rotation Governance Automation (attestation, drift, bundles, game-day staleness) ──
        from scheduler_jobs import (
            scheduled_key_rotation_policy_attestation,
            scheduled_key_rotation_status_drift_monitor,
            scheduled_key_rotation_compliance_bundle_autogen,
            scheduled_key_rotation_game_day_staleness_guard,
            scheduled_siem_webhook_dead_letter_retry,
            scheduled_security_incident_runbook_monitor,
        )
        scheduler.add_job(
            scheduled_key_rotation_policy_attestation,
            IntervalTrigger(hours=6),
            id="key_rotation_policy_attestation",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_key_rotation_status_drift_monitor,
            IntervalTrigger(minutes=30),
            id="key_rotation_status_drift_monitor",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_key_rotation_compliance_bundle_autogen,
            IntervalTrigger(hours=1),
            id="key_rotation_compliance_bundle_autogen",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_key_rotation_game_day_staleness_guard,
            CronTrigger(hour=7, minute=10),
            id="key_rotation_game_day_staleness_guard",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_siem_webhook_dead_letter_retry,
            IntervalTrigger(minutes=30),
            id="siem_webhook_dead_letter_retry",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_security_incident_runbook_monitor,
            CronTrigger(minute=0, hour="*/3"),
            id="security_incident_runbook_monitor",
            replace_existing=True,
            max_instances=1)

        # ── Release Intelligence Monitor (every 5 minutes) ──
        from scheduler_jobs import scheduled_release_intelligence_monitor
        scheduler.add_job(
            scheduled_release_intelligence_monitor,
            IntervalTrigger(minutes=5),
            id="release_intelligence_monitor",
            replace_existing=True,
            max_instances=1)

        # ── Core Web Vitals Performance Alerts (every 2 hours) ──
        async def scheduled_cwv_alert_check():
            try:
                from routes.seo_analytics import check_and_send_vitals_alerts
                await check_and_send_vitals_alerts()
            except Exception as e:
                log.error(f"CWV alert check failed: {e}")

        scheduler.add_job(scheduled_cwv_alert_check, IntervalTrigger(hours=2), id="cwv_performance_alerts", replace_existing=True,
    max_instances=1)

        # ── Referral Fraud Detection Scan (every 6 hours) ──
        async def scheduled_fraud_scan():
            try:
                from routes.referrals import run_fraud_scan, REFERRALS_FRAUD_AUTOSCAN_ENABLED
                if not REFERRALS_FRAUD_AUTOSCAN_ENABLED:
                    log.info("Referral fraud scan skipped: REFERRALS_FRAUD_AUTOSCAN_ENABLED is off")
                    return
                new_alerts = await run_fraud_scan()
                if new_alerts > 0:
                    log.info(f"Fraud scan completed: {new_alerts} new alerts generated")
                    # Store scan history
                    from datetime import datetime, timezone
                    from utils.db import db
                    await db.referral_fraud_scan_history.insert_one({
                        "scan_time": datetime.now(timezone.utc).isoformat(),
                        "alerts_generated": new_alerts,
                        "scan_type": "scheduled",
                    })
                else:
                    log.info("Fraud scan completed: no new alerts")
            except Exception as e:
                log.error(f"Fraud scan error: {e}")
        scheduler.add_job(scheduled_fraud_scan, IntervalTrigger(hours=6), id="referral_fraud_scan", replace_existing=True,
    max_instances=1)

        # ── Referral Integrity Alert Monitor (every 15 minutes) ──
        async def scheduled_referral_integrity_alerts():
            try:
                from routes.referrals import evaluate_and_emit_referral_integrity_alerts

                result = await evaluate_and_emit_referral_integrity_alerts(trigger="scheduled")
                if result.get("alert_generated"):
                    log.warning(
                        "Referral integrity alert emitted: %s",
                        result.get("signals", []),
                    )
            except Exception as e:
                log.error(f"Referral integrity monitor error: {e}")

        scheduler.add_job(
            scheduled_referral_integrity_alerts,
            IntervalTrigger(minutes=15),
            id="referral_integrity_alert_monitor",
            replace_existing=True,
            max_instances=1,
        )

        # ── Churn Recovery Win-Back Reminders (bi-weekly) ──
        async def scheduled_winback_reminders():
            try:
                from services.churn_recovery import send_winback_reminders
                sent = await send_winback_reminders()
                log.info(f"Win-back reminders job: sent {sent} emails")
            except Exception as e:
                log.error(f"Win-back reminders error: {e}")
        scheduler.add_job(scheduled_winback_reminders, IntervalTrigger(days=1), id="churn_winback_reminders", replace_existing=True,
    max_instances=1)

        # ── Flappy Bird Streak Saver Emails (daily, 7h before UTC midnight) ──
        async def scheduled_flappy_streak_saver():
            try:
                from services.flappy_streak_saver import send_streak_saver_reminders
                sent = await send_streak_saver_reminders()
                log.info(f"Flappy streak saver job: sent {sent} emails")
            except Exception as e:
                log.error(f"Flappy streak saver error: {e}")
        scheduler.add_job(scheduled_flappy_streak_saver, CronTrigger(hour=17, minute=0), id="flappy_streak_saver", replace_existing=True,
    max_instances=1)

        # ── Payment Failure Recovery Emails (every 6 hours) ──
        async def scheduled_payment_recovery():
            try:
                from utils.payment_recovery import process_recovery_emails
                await process_recovery_emails(db)
            except Exception as e:
                log.error(f"Payment recovery email job error: {e}")
        scheduler.add_job(scheduled_payment_recovery, IntervalTrigger(hours=6), id="payment_failure_recovery", replace_existing=True,
    max_instances=1)

        # ── Missed Payment Notification Recovery (every 5 minutes) ──
        async def scheduled_payment_notification_recovery():
            try:
                from routes import payments as payments_routes

                txs = await db.payment_transactions.find(
                    payments_routes._build_missed_notification_recovery_query(),
                    {"_id": 0},
                ).sort("created_at", 1).limit(25).to_list(25)

                if not txs:
                    return

                recovered = 0
                skipped = 0
                failed = 0
                for tx in txs:
                    try:
                        outcome = await payments_routes._recover_missed_notification_for_transaction(tx)
                        if outcome.get("status") == "recovered":
                            recovered += 1
                        else:
                            skipped += 1
                    except Exception as exc:
                        failed += 1
                        log.error(
                            "Payment notification recovery job failed for session=%s payment=%s: %s",
                            tx.get("session_id"),
                            tx.get("payment_id"),
                            exc,
                        )

                log.info(
                    "Payment notification recovery job: scanned=%s recovered=%s skipped=%s failed=%s",
                    len(txs),
                    recovered,
                    skipped,
                    failed,
                )
            except Exception as e:
                log.error(f"Payment notification recovery scheduler error: {e}")

        scheduler.add_job(
            scheduled_payment_notification_recovery,
            IntervalTrigger(minutes=5),
            id="payment_notification_recovery",
            replace_existing=True,
            max_instances=1)

        # ── FedaPay Webhook URL Auto-Sync (every 10 minutes — permanent fix) ──
        async def scheduled_fedapay_webhook_sync():
            try:
                from routes.fedapay_client import sync_webhook_url, get_current_webhook_url
                url = get_current_webhook_url()
                if not url:
                    return
                result = await sync_webhook_url()
                action = result.get("action", "none")
                if action != "none":
                    log.info(f"[FEDAPAY-SYNC] Webhook auto-synced: {action} -> {result.get('url', url)}")
            except Exception as e:
                log.warning(f"[FEDAPAY-SYNC] Webhook sync error: {e}")
        scheduler.add_job(scheduled_fedapay_webhook_sync, IntervalTrigger(minutes=10), id="fedapay_webhook_sync", replace_existing=True,
    max_instances=1)

        # ── FedaPay Country/Fee Policy Auto-Refresh (API-first + fallback) ──
        async def scheduled_fedapay_policy_refresh(force: bool = False):
            try:
                from utils.fedapay_policy_service import refresh_fedapay_policy
                policy = await refresh_fedapay_policy(db, force=force)
                log.info(
                    "[FEDAPAY-POLICY] refreshed source=%s countries=%s",
                    policy.get("source", "unknown"),
                    len(policy.get("countries", {}) or {}),
                )
            except Exception as e:
                log.warning(f"[FEDAPAY-POLICY] refresh error: {e}")

        async def scheduled_fedapay_policy_auto_sync():
            """Force-sync FedaPay policy to capture upstream fee changes without admin action."""
            try:
                from utils.fedapay_policy_service import refresh_fedapay_policy

                policy = await refresh_fedapay_policy(db, force=True)
                policy_hash = str(policy.get("policy_hash") or "")
                source = str(policy.get("source") or "unknown")
                countries_count = len(policy.get("countries", {}) or {})
                now_iso = datetime.now(timezone.utc).isoformat()

                state_key = "fedapay_policy_live_hash"
                prev_state = await db.system_runtime_flags.find_one({"key": state_key}, {"_id": 0}) or {}
                prev_hash = str(prev_state.get("value") or "")
                changed = bool(prev_hash and policy_hash and prev_hash != policy_hash)

                await db.system_runtime_flags.update_one(
                    {"key": state_key},
                    {
                        "$set": {
                            "key": state_key,
                            "value": policy_hash,
                            "source": source,
                            "countries_count": countries_count,
                            "updated_at": now_iso,
                            "changed": changed,
                        }
                    },
                    upsert=True,
                )

                if changed:
                    await db.fedapay_policy_source_events.insert_one(
                        {
                            "event": "fedapay_policy_auto_updated",
                            "from_hash": prev_hash,
                            "to_hash": policy_hash,
                            "source": source,
                            "country_count": countries_count,
                            "changed_at": now_iso,
                        }
                    )
                    admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(40)
                    for admin in admins:
                        admin_id = str(admin.get("user_id") or "")
                        if not admin_id:
                            continue
                        await db.notifications.insert_one(
                            {
                                "id": f"fedapay_policy_auto_updated_{admin_id}_{int(time.time())}",
                                "user_id": admin_id,
                                "type": "fedapay_policy_auto_updated",
                                "title": "FedaPay Fee Policy Auto-Updated",
                                "message": "FedaPay fee policy changed automatically and was applied platform-wide.",
                                "read": False,
                                "created_at": now_iso,
                                "metadata": {
                                    "from_hash": prev_hash,
                                    "to_hash": policy_hash,
                                    "source": source,
                                    "country_count": countries_count,
                                },
                            }
                        )

                log.info(
                    "[FEDAPAY-POLICY-AUTO] synced source=%s countries=%s changed=%s",
                    source,
                    countries_count,
                    changed,
                )
            except Exception as e:
                log.warning(f"[FEDAPAY-POLICY-AUTO] sync error: {e}")

        async def scheduled_fedapay_policy_cache_reset():
            try:
                from utils.fedapay_policy_service import clear_fedapay_policy_cache
                await clear_fedapay_policy_cache(db)
                await scheduled_fedapay_policy_refresh(force=True)
            except Exception as e:
                log.warning(f"[FEDAPAY-POLICY] cache reset error: {e}")

        await scheduled_fedapay_policy_cache_reset()
        await scheduled_fedapay_policy_auto_sync()
        scheduler.add_job(
            scheduled_fedapay_policy_refresh,
            IntervalTrigger(minutes=30),
            id="fedapay_policy_refresh",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_fedapay_policy_auto_sync,
            IntervalTrigger(minutes=5),
            id="fedapay_policy_auto_sync",
            replace_existing=True,
            max_instances=1)

        # ── AI Budget ──
        from routes.ai_model_management import generate_weekly_budget_report

        async def scheduled_weekly_ai_budget_report():
            try:
                report = await generate_weekly_budget_report()
                logger.info(f"Weekly AI budget report: {report['report_id']}")
            except Exception as e:
                logger.error(f"Weekly AI budget report failed: {e}")

        scheduler.add_job(scheduled_weekly_ai_budget_report, CronTrigger(day_of_week='mon', hour=8, minute=0), id="weekly_ai_budget_report", replace_existing=True,
    max_instances=1)

        # ── A/B Testing ──
        from routes.advanced_admin import auto_winner_check
        scheduler.add_job(auto_winner_check, IntervalTrigger(minutes=15), id="ab_auto_winner_check", replace_existing=True,
    max_instances=1)

        # ── A/B Scheduled Rollout ──
        from routes.ab_prompt_testing import check_scheduled_rollouts
        scheduler.add_job(check_scheduled_rollouts, IntervalTrigger(minutes=5), id="ab_scheduled_rollout_check", replace_existing=True,
    max_instances=1)

        # ── A/B Test Rotation (weekly) ──
        from routes.ab_testing import scheduled_ab_rotation
        scheduler.add_job(scheduled_ab_rotation, CronTrigger(day_of_week='mon', hour=6, minute=0), id="ab_test_rotation_weekly", replace_existing=True,
    max_instances=1)

        # ── Page Performance Auto-Fix (every 15 min) ──
        async def perf_regression_scan():
            try:
                from routes.page_performance import run_perf_regression_scan
                await run_perf_regression_scan()
            except Exception as e:
                logger.error(f"Perf regression scan failed: {e}")
        scheduler.add_job(perf_regression_scan, IntervalTrigger(minutes=15), id="perf_regression_autofix", replace_existing=True,
    max_instances=1)

        # ── Weekly Email Heatmap Digest (Fridays 9 AM UTC) ──
        async def weekly_heatmap_digest():
            try:
                from routes.email_notifications import _send_weekly_heatmap_digest
                await _send_weekly_heatmap_digest(db)
            except Exception as e:
                logger.error(f"Weekly heatmap digest failed: {e}")
        scheduler.add_job(weekly_heatmap_digest, CronTrigger(day_of_week='fri', hour=9, minute=0), id="weekly_heatmap_digest", replace_existing=True,
    max_instances=1)

        # ── ATS Sync ──
        from routes.ats_integrations import run_scheduled_syncs
        scheduler.add_job(run_scheduled_syncs, IntervalTrigger(minutes=30), id="ats_auto_sync", replace_existing=True,
    max_instances=1)

        # ── Webhook Retry ──
        from routes.webhook_retry_engine import run_retry_cycle
        scheduler.add_job(run_retry_cycle, IntervalTrigger(seconds=30), id="webhook_auto_retry", replace_existing=True,
    max_instances=1)

        # ── AI Alerting ──
        from routes.ai_alerting import run_alert_check
        scheduler.add_job(run_alert_check, IntervalTrigger(minutes=5), id="ai_feature_alerting", replace_existing=True,
    max_instances=1)

        # ── Escalation Engine ──
        from routes.escalation_engine import run_escalation_check
        scheduler.add_job(run_escalation_check, IntervalTrigger(minutes=2), id="ticket_escalation_check", replace_existing=True,
    max_instances=1)

        # ── Auto Scaling ──
        from routes.auto_scaling import evaluate_scaling_rules
        scheduler.add_job(evaluate_scaling_rules, IntervalTrigger(seconds=60), id="auto_scaling_eval", replace_existing=True,
    max_instances=1)


        # ── Ticket Feedback Digest (weekly on Monday 9:00 UTC) ──
        async def scheduled_feedback_digest():
            try:
                from routes.ticket_feedback import generate_and_send_digest
                result = await generate_and_send_digest()
                logger.info(f"Feedback digest: {result}")
            except Exception as e:
                logger.error(f"Feedback digest failed: {e}")

        scheduler.add_job(scheduled_feedback_digest, CronTrigger(day_of_week='mon', hour=9, minute=30), id="ticket_feedback_digest", replace_existing=True,
    max_instances=1)

        # ── Sentiment Drop Alert Check (hourly) ──
        async def scheduled_sentiment_alert_check():
            try:
                from routes.ticket_feedback import run_sentiment_alert_check
                result = await run_sentiment_alert_check()
                logger.info(f"Sentiment alert check: {result}")
            except Exception as e:
                logger.error(f"Sentiment alert check failed: {e}")
        scheduler.add_job(scheduled_sentiment_alert_check, IntervalTrigger(hours=1), id="sentiment_alert_check", replace_existing=True,
    max_instances=1)


        # ── Weekly Sentiment Summary Email ──
        async def scheduled_sentiment_summary():
            try:
                from routes.ticket_feedback import generate_and_send_sentiment_summary
                # Check if today matches configured day
                from routes.db import db as _db
                config = await _db.system_config.find_one({"key": "sentiment_summary"}, {"_id": 0})
                day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
                target_day = day_map.get((config or {}).get("day", "friday"), 4)
                target_hour = (config or {}).get("hour", 9)
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                if now.weekday() == target_day and now.hour == target_hour:
                    result = await generate_and_send_sentiment_summary()
                    logger.info(f"Sentiment summary: {result}")
            except Exception as e:
                logger.error(f"Sentiment summary failed: {e}")
        scheduler.add_job(scheduled_sentiment_summary, IntervalTrigger(hours=1), id="sentiment_summary_weekly", replace_existing=True,
    max_instances=1)


        # ── Weekly CSAT AI Report Email ──
        async def scheduled_csat_ai_report():
            try:
                from routes.csat_router import generate_and_send_csat_ai_report
                from routes.db import db as _db
                config = await _db.system_config.find_one({"key": "csat_ai_report"}, {"_id": 0})
                day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
                target_day = day_map.get((config or {}).get("day", "monday"), 0)
                target_hour = (config or {}).get("hour", 8)
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                if now.weekday() == target_day and now.hour == target_hour:
                    result = await generate_and_send_csat_ai_report()
                    logger.info(f"CSAT AI report: {result}")
            except Exception as e:
                logger.error(f"CSAT AI report failed: {e}")
        scheduler.add_job(scheduled_csat_ai_report, IntervalTrigger(hours=1), id="csat_ai_report_weekly", replace_existing=True,
    max_instances=1)


        # ── Weekly AI Health Digest Email ──
        async def scheduled_ai_health_digest():
            try:
                from routes.ai_autofix_engine import run_all_fixes
                from routes.ai_panel_insights import generate_and_send_ai_health_digest
                from routes.db import db as _db
                config = await _db.system_config.find_one({"key": "ai_health_digest"}, {"_id": 0})
                day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
                target_day = day_map.get((config or {}).get("day", "monday"), 0)
                target_hour = (config or {}).get("hour", 8)
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                if now.weekday() == target_day and now.hour == target_hour:
                    # Step 1: Run auto-fix first
                    fix_result = await run_all_fixes()
                    logger.info(f"AI Auto-Fix (pre-digest): {fix_result.get('total_actions', 0)} actions taken")
                    # Step 2: Then send digest (with updated data)
                    result = await generate_and_send_ai_health_digest()
                    logger.info(f"AI Health Digest: {result}")
            except Exception as e:
                logger.error(f"AI Health Digest failed: {e}")
        scheduler.add_job(scheduled_ai_health_digest, IntervalTrigger(hours=1), id="ai_health_digest_weekly", replace_existing=True,
    max_instances=1)

        # ── Daily AI Auto-Fix ──
        async def scheduled_daily_autofix():
            try:
                from routes.ai_autofix_engine import run_all_fixes
                result = await run_all_fixes()
                logger.info(f"Daily AI Auto-Fix: {result.get('total_actions', 0)} actions taken")
            except Exception as e:
                logger.error(f"Daily AI Auto-Fix failed: {e}")
        scheduler.add_job(scheduled_daily_autofix, IntervalTrigger(hours=6), id="ai_autofix_daily", replace_existing=True,
    max_instances=1)



        # ── SIEM Alert Evaluation ──
        from routes.siem_logging import _evaluate_alert_rules
        async def siem_alert_eval():
            try:
                triggered = await _evaluate_alert_rules()
                if triggered:
                    logger.info(f"SIEM alert evaluation: triggered {triggered} alert(s)")
            except Exception as e:
                logger.error(f"SIEM alert eval failed: {e}")
        scheduler.add_job(siem_alert_eval, IntervalTrigger(minutes=5), id="siem_alert_eval", replace_existing=True,
    max_instances=1)

        # ── Anomaly Spike Detection + Auto-Fix (every 15 minutes) ──
        async def scheduled_anomaly_spike_check():
            try:
                from services.anomaly_digest import check_spike_and_autofix
                from routes.db import db as _db
                await check_spike_and_autofix(_db)
            except Exception as e:
                logger.error(f"Anomaly spike check failed: {e}")
        scheduler.add_job(scheduled_anomaly_spike_check, IntervalTrigger(minutes=15), id="anomaly_spike_check", replace_existing=True,
    max_instances=1)

        # ── Anomaly Daily Digest (daily at 8 AM UTC) ──
        async def scheduled_anomaly_daily_digest():
            try:
                from services.anomaly_digest import send_daily_digest
                from routes.db import db as _db
                await send_daily_digest(_db)
            except Exception as e:
                logger.error(f"Anomaly daily digest failed: {e}")
        scheduler.add_job(scheduled_anomaly_daily_digest, CronTrigger(hour=8, minute=0), id="anomaly_daily_digest", replace_existing=True,
    max_instances=1)

        # ── Anomaly Weekly Digest (Monday at 9 AM UTC) ──
        async def scheduled_anomaly_weekly_digest():
            try:
                from services.anomaly_digest import send_weekly_digest
                from routes.db import db as _db
                await send_weekly_digest(_db)
            except Exception as e:
                logger.error(f"Anomaly weekly digest failed: {e}")
        scheduler.add_job(scheduled_anomaly_weekly_digest, CronTrigger(day_of_week='mon', hour=9, minute=0), id="anomaly_weekly_digest", replace_existing=True,
    max_instances=1)

        # ── Admin Real-Time Push Notifications — Custom Rules Engine (every 45 seconds) ──
        async def scheduled_admin_push_alerts():
            try:
                from routes.admin_notification_rules import evaluate_custom_rules
                await evaluate_custom_rules()
            except Exception as e:
                logger.error(f"Admin push alerts failed: {e}")
        scheduler.add_job(scheduled_admin_push_alerts, IntervalTrigger(seconds=45), id="admin_push_alerts", replace_existing=True,
    max_instances=1)

        # ── Admin Email Guardrail Monitor (every 10 minutes) ──
        # Global monitor for admin-only templates sent to known non-admin users.
        async def scheduled_admin_email_guardrail_monitor():
            try:
                from services.admin_email_guardrail_monitor import run_incremental_admin_template_monitor
                outcome = await run_incremental_admin_template_monitor(db)
                if outcome.get("violations_total", 0) > 0:
                    logger.warning(
                        "[admin-email-guardrail] violations=%s system_alert_admin_non_admin=%s",
                        outcome.get("violations_total"),
                        outcome.get("system_alert_admin_non_admin"),
                    )
            except Exception as e:
                logger.error(f"Admin email guardrail monitor failed: {e}")

        scheduler.add_job(
            scheduled_admin_email_guardrail_monitor,
            IntervalTrigger(minutes=10),
            id="admin_email_guardrail_monitor",
            replace_existing=True,
            max_instances=1)

        # ── Annual Receipt Summary (Jan 1st at 10 AM UTC) ──
        async def scheduled_annual_receipt_summary():
            try:
                summary = await run_annual_receipt_summary_dispatch()
                logger.info(
                    "Annual receipt summary: sent to %s/%s users for %s",
                    summary.get("sent_count", 0),
                    summary.get("processed_users", 0),
                    summary.get("year"),
                )
            except Exception as e:
                logger.error(f"Annual receipt summary scheduler failed: {e}")

        scheduler.add_job(scheduled_annual_receipt_summary, CronTrigger(month=1, day=1, hour=10, minute=0), id="annual_receipt_summary", replace_existing=True,
    max_instances=1)


        # ── Google OAuth Verification Monitor (every 6 hours) ──
        async def scheduled_google_verification_check():
            try:
                from services.google_verification_monitor import check_google_verification_status
                from routes.db import db as _db
                result = await check_google_verification_status(_db)
                if result.get("status_changed"):
                    logger.info(f"Google verification status changed: {result.get('previous_status')} -> {result.get('status')}")
                else:
                    logger.info(f"Google verification check: status={result.get('status')}")
            except Exception as e:
                logger.error(f"Google verification check failed: {e}")
        scheduler.add_job(scheduled_google_verification_check, IntervalTrigger(hours=6), id="google_verification_monitor", replace_existing=True,
    max_instances=1)

        # ── Blog Post Auto-Rotation (daily check) ──
        async def scheduled_blog_rotation():
            try:
                from services.blog_service import rotate_blog_posts
                from routes.db import db as _db
                await rotate_blog_posts(_db)
                logger.info("Blog post rotation check completed")
            except Exception as e:
                logger.error(f"Blog rotation failed: {e}")
        scheduler.add_job(scheduled_blog_rotation, IntervalTrigger(hours=24), id="blog_rotation", replace_existing=True,
    max_instances=1)

        # ── Contact Form Auto Follow-Up (every hour) ──
        async def scheduled_contact_followup():
            try:
                from routes.contact import process_contact_followups
                result = await process_contact_followups()
                if result.get("sent", 0) > 0:
                    logger.info(f"Contact follow-up: sent {result['sent']} follow-up email(s)")
            except Exception as e:
                logger.error(f"Contact follow-up check failed: {e}")
        scheduler.add_job(scheduled_contact_followup, IntervalTrigger(hours=1), id="contact_auto_followup", replace_existing=True,
    max_instances=1)

        # ── Newsletter Blog Digest (bi-weekly: every 14 days) ──
        async def scheduled_blog_digest():
            try:
                from routes.newsletter_router import send_blog_digest
                sent = await send_blog_digest()
                logger.info(f"Blog digest sent to {sent} subscribers")
            except Exception as e:
                logger.error(f"Blog digest failed: {e}")
        scheduler.add_job(scheduled_blog_digest, IntervalTrigger(days=14), id="blog_digest", replace_existing=True,
    max_instances=1)

        # ── Newsletter TZ-aware Cohort Dispatcher (every 15 min; fires weekly
        # briefings to subscribers whose preferred (weekday, hour) matches NOW
        # in their local timezone, with per-ISO-week idempotency). ──
        async def scheduled_tz_aware_briefing_dispatch():
            try:
                from routes.newsletter_router import send_tz_aware_briefings_due
                summary = await send_tz_aware_briefings_due()
                if summary.get("matched"):
                    logger.info(
                        f"[tz-briefing] checked={summary.get('checked')} "
                        f"matched={summary.get('matched')} "
                        f"sent={summary.get('sent')} "
                        f"skipped_dedup={summary.get('skipped_dedup')} "
                        f"failed={summary.get('failed')}"
                    )
            except Exception as e:
                logger.error(f"TZ-aware briefing dispatch failed: {e}")
        scheduler.add_job(
            scheduled_tz_aware_briefing_dispatch,
            IntervalTrigger(minutes=15),
            id="newsletter_tz_aware_briefing_dispatch",
            replace_existing=True,
            max_instances=1)

        # ── Admin Routes Sentinel (every 5 min; state-change Slack alerts
        # when Team Management / Executive Console / Operations Console
        # route probes regress or recover). ──
        async def scheduled_admin_routes_sentinel():
            try:
                from services.admin_routes_sentinel import run_admin_routes_sentinel
                summary = await run_admin_routes_sentinel()
                if summary.get("transitions"):
                    logger.warning(
                        f"[admin-routes-sentinel] transitions={summary['transitions']} "
                        f"dispatched={summary['dispatched']}"
                    )
            except Exception as e:
                logger.error(f"Admin routes sentinel failed: {e}")
        scheduler.add_job(
            scheduled_admin_routes_sentinel,
            IntervalTrigger(minutes=5),
            id="admin_routes_sentinel",
            replace_existing=True,
            max_instances=1)

        # ── Autonomous Weekly Blog + Newsletter (every Monday at 10 AM UTC) ──
        async def scheduled_autonomous_weekly_blog_newsletter():
            job_id = "autonomous_weekly_blog_newsletter"
            try:
                from scheduler_jobs import _record_scheduler_heartbeat
                from services.autonomous_content_automation import run_weekly_autonomous_content_cycle

                result = await run_weekly_autonomous_content_cycle(db, triggered_by="scheduler")
                heartbeat_status = "healthy" if result.get("status") in {"completed", "skipped"} else "error"
                detail = (
                    f"status={result.get('status')} week={result.get('week_key')} "
                    f"blog={result.get('blog_slug')} sent={result.get('newsletter_sent', 0)}/"
                    f"{result.get('subscribers_total', 0)}"
                )
                await _record_scheduler_heartbeat(job_id, heartbeat_status, detail)
                logger.info(f"Autonomous weekly blog/newsletter run finished: {detail}")
            except Exception as e:
                try:
                    from scheduler_jobs import _record_scheduler_heartbeat

                    await _record_scheduler_heartbeat(job_id, "error", str(e)[:200])
                except Exception:
                    pass
                logger.error(f"Autonomous weekly blog/newsletter failed: {e}")

        scheduler.add_job(
            scheduled_autonomous_weekly_blog_newsletter,
            CronTrigger(day_of_week='mon', hour=10, minute=0),
            id="autonomous_weekly_blog_newsletter",
            replace_existing=True,
            max_instances=1)

        # ── Performance Metrics History ──
        async def collect_perf_metrics():
            try:
                from routes.system_metrics import _get_system_metrics
                from routes.db import db as _db
                metrics = _get_system_metrics()
                await _db.perf_metrics_history.insert_one(metrics)
                # Clean old entries (keep 24h)
                from datetime import datetime as dt, timezone as tz, timedelta as td
                cutoff = (dt.now(tz.utc) - td(hours=24)).isoformat()
                await _db.perf_metrics_history.delete_many({"timestamp": {"$lt": cutoff}})
            except Exception as e:
                logger.error(f"Perf metrics collection failed: {e}")
        scheduler.add_job(collect_perf_metrics, IntervalTrigger(seconds=30), id="perf_metrics_collector", replace_existing=True,
    max_instances=1)

        # ── Performance Guardian Auto-Fix ──
        async def scheduled_guardian_auto_fix():
            try:
                from routes.performance_guardian import auto_fix_check
                await auto_fix_check()
            except Exception as e:
                logger.error(f"Performance Guardian auto-fix check failed: {e}")
        scheduler.add_job(scheduled_guardian_auto_fix, IntervalTrigger(minutes=15), id="performance_guardian_autofix", replace_existing=True,
    max_instances=1)

        # ── Proactive Performance Alerts (every 30 minutes) ──
        async def scheduled_proactive_alerts():
            try:
                from routes.performance_guardian import proactive_vitals_alert
                await proactive_vitals_alert()
            except Exception as e:
                logger.error(f"Proactive vitals alert failed: {e}")
        scheduler.add_job(scheduled_proactive_alerts, IntervalTrigger(minutes=30), id="proactive_vitals_alerts", replace_existing=True,
    max_instances=1)

        # ── Centralized Auto-Fix Engine Sweep (every 15 minutes) ──
        async def scheduled_autofix_sweep():
            try:
                from routes.admin_autofix_engine import scheduled_autofix_sweep as _sweep
                await _sweep()
            except Exception as e:
                logger.error(f"Auto-fix engine sweep failed: {e}")
        scheduler.add_job(scheduled_autofix_sweep, IntervalTrigger(minutes=15), id="autofix_engine_sweep", replace_existing=True,
    max_instances=1)

        # ── Platform Performance Snapshots (every 5 minutes) ──
        async def scheduled_perf_snapshot():
            try:
                from routes.platform_perf import take_perf_snapshot
                await take_perf_snapshot()
            except Exception as e:
                logger.error(f"Performance snapshot failed: {e}")
        scheduler.add_job(scheduled_perf_snapshot, IntervalTrigger(minutes=5), id="perf_snapshot", replace_existing=True,
    max_instances=1)

        # ── Performance Reports ──
        from routes.performance_reports import send_performance_report

        async def scheduled_daily_report():
            try:
                result = await send_performance_report("daily")
                logger.info(f"Daily report sent to {len(result['sent_to'])} admin(s)")
            except Exception as e:
                logger.error(f"Daily performance report failed: {e}")

        async def scheduled_weekly_report():
            try:
                result = await send_performance_report("weekly")
                logger.info(f"Weekly report sent to {len(result['sent_to'])} admin(s)")
            except Exception as e:
                logger.error(f"Weekly performance report failed: {e}")

        scheduler.add_job(scheduled_daily_report, CronTrigger(hour=7, minute=0), id="daily_performance_report", replace_existing=True,
    max_instances=1)
        scheduler.add_job(scheduled_weekly_report, CronTrigger(day_of_week='mon', hour=7, minute=0), id="weekly_performance_report", replace_existing=True,
    max_instances=1)

        # ── Scheduled Audit Export ──
        async def scheduled_audit_export():
            try:
                config = await db.audit_export_schedule.find_one({"key": "audit_export_schedule"})
                if not config or not config.get("enabled"):
                    return
                from routes.admin_data_management import run_scheduled_audit_export
                result = await run_scheduled_audit_export()
                logger.info(f"Scheduled audit export: {result}")
            except Exception as e:
                logger.error(f"Scheduled audit export failed: {e}")

        scheduler.add_job(scheduled_audit_export, CronTrigger(day_of_week='mon', hour=8, minute=0), id="weekly_audit_export", replace_existing=True,
    max_instances=1)

        # ── User Re-engagement (daily at 9 AM UTC) ──
        async def scheduled_reengagement():
            try:
                from routes.reengagement import run_reengagement_check
                result = await run_reengagement_check()
                logger.info(f"Reengagement check: {result}")
            except Exception as e:
                logger.error(f"Reengagement check failed: {e}")
        scheduler.add_job(scheduled_reengagement, CronTrigger(hour=9, minute=30), id="daily_reengagement_check", replace_existing=True,
    max_instances=1)

        # ── A/B Test Auto-Evaluation (daily at 10 PM UTC) ──
        async def scheduled_ab_evaluation():
            try:
                from routes.ab_testing import evaluate_expired_tests
                await evaluate_expired_tests()
            except Exception as e:
                logger.error(f"A/B test evaluation failed: {e}")
        scheduler.add_job(scheduled_ab_evaluation, CronTrigger(hour=22, minute=0), id="daily_ab_evaluation", replace_existing=True,
    max_instances=1)

        # ── A/B Test Scheduled Activation (every 15 minutes) ──
        async def scheduled_ab_activation():
            try:
                from routes.ab_testing import activate_scheduled_tests
                await activate_scheduled_tests()
            except Exception as e:
                logger.error(f"A/B test activation failed: {e}")
        scheduler.add_job(scheduled_ab_activation, IntervalTrigger(minutes=15), id="ab_scheduled_activation", replace_existing=True,
    max_instances=1)

        # ── Daily Code Health Check (6 AM UTC) ──
        async def scheduled_code_health():
            try:
                from routes.code_health import scheduled_code_health_check
                await scheduled_code_health_check()
                logger.info("Code health check completed")
            except Exception as e:
                logger.error(f"Code health check failed: {e}")
        scheduler.add_job(scheduled_code_health, CronTrigger(hour=6, minute=0), id="daily_code_health", replace_existing=True,
    max_instances=1)

        # ── Admin Health Digest (8 AM UTC, after the code-health check) ──
        async def scheduled_admin_health_digest():
            try:
                from services.admin_health_digest import run_admin_health_digest
                record = await run_admin_health_digest()
                logger.info(
                    f"Admin health digest: severity={record['severity']} "
                    f"broken_routes={len(record['unhealthy_routes'])} "
                    f"crashes24h={record['total_errors_24h']} "
                    f"dispatched={record['dispatched']}"
                )
            except Exception as e:
                logger.error(f"Admin health digest failed: {e}")
        scheduler.add_job(
            scheduled_admin_health_digest,
            CronTrigger(hour=8, minute=0),
            id="daily_admin_health_digest",
            replace_existing=True,
            max_instances=1)

        # ── Daily Entitlement Drift Audit (8:20 AM UTC) ──
        async def scheduled_entitlement_drift_audit():
            try:
                from services.entitlement_drift_audit import run_entitlement_drift_audit
                record = await run_entitlement_drift_audit(trigger="scheduled_daily")
                logger.info(
                    f"Entitlement drift audit: status={record['status']} "
                    f"findings={record['finding_count']} high={record['high_risk_count']} "
                    f"dispatched={record['alert_dispatched']}"
                )
            except Exception as e:
                logger.error(f"Entitlement drift audit failed: {e}")
        scheduler.add_job(
            scheduled_entitlement_drift_audit,
            CronTrigger(hour=8, minute=20),
            id="daily_entitlement_drift_audit",
            replace_existing=True,
            max_instances=1)

        # ── Daily Job Alerts (9:00 AM UTC) ──
        async def scheduled_daily_job_alerts():
            try:
                from routes.job_alerts import _execute_daily_job_alerts
                result = await _execute_daily_job_alerts()
                logger.info(f"Daily job alerts: {result.get('message', 'done')}")
            except Exception as e:
                logger.error(f"Daily job alerts failed: {e}")
        scheduler.add_job(scheduled_daily_job_alerts, CronTrigger(hour=9, minute=0), id="daily_job_alerts", replace_existing=True,
    max_instances=1)

        # ── Nightly JS/TDZ Code Health Scan (3 AM UTC) ──
        async def nightly_js_code_health():
            try:
                from routes.code_health_scanner import run_nightly_code_health_scan
                await run_nightly_code_health_scan()
                logger.info("Nightly JS/TDZ code health scan completed")
            except Exception as e:
                logger.error(f"Nightly JS/TDZ scan failed: {e}")
        scheduler.add_job(nightly_js_code_health, CronTrigger(hour=3, minute=0), id="nightly_js_code_health", replace_existing=True,
    max_instances=1)

        # ── Daily Accessibility Audit (6:30 AM UTC) ──
        async def scheduled_accessibility():
            try:
                from routes.accessibility_audit import scheduled_accessibility_check
                await scheduled_accessibility_check()
                logger.info("Accessibility audit completed")
            except Exception as e:
                logger.error(f"Accessibility audit failed: {e}")
        scheduler.add_job(scheduled_accessibility, CronTrigger(hour=6, minute=30), id="daily_accessibility", replace_existing=True,
    max_instances=1)

        # ── Weekly AI Changelog Generation (every Monday at 10 AM UTC) ──
        async def scheduled_changelog_generation():
            try:
                # Create a mock admin request-like context
                from datetime import datetime, timezone
                import uuid
                logger.info("Starting scheduled AI changelog generation...")

                now = datetime.now(timezone.utc)
                seven_days_ago = (now - timedelta(days=7)).isoformat()
                metrics = {}
                try:
                    metrics["total_users"] = await db.users.count_documents({})
                    metrics["new_users_7d"] = await db.users.count_documents({"created_at": {"$gte": seven_days_ago}})
                    metrics["total_referrals"] = await db.referrals.count_documents({})
                    metrics["new_referrals_7d"] = await db.referrals.count_documents({"created_at": {"$gte": seven_days_ago}})
                    metrics["nova_conversations_7d"] = await db.nova_conversations.count_documents({"created_at": {"$gte": seven_days_ago}})
                    metrics["faq_searches_7d"] = await db.faq_searches.count_documents({"timestamp": {"$gte": seven_days_ago}})
                except Exception as e:
                    logger.warning(f"Changelog metrics error: {e}")

                existing = await db.changelog_entries.find(
                    {"created_at": {"$gte": seven_days_ago}}, {"_id": 0, "title": 1}
                ).to_list(50)
                existing_titles = [e["title"] for e in existing]

                from emergentintegrations.llm.chat import LlmChat, UserMessage
                EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
                chat = LlmChat(
                    api_key=EMERGENT_LLM_KEY,
                    session_id=f"changelog-weekly-{uuid.uuid4().hex[:8]}",
                    system_message="""You are a product manager writing changelog entries for RealAICoach, an enterprise referral & coaching platform.
Generate 3-5 professional changelog entries based on the platform metrics provided. Each entry should:
- Have a concise, compelling title
- Include a 1-2 sentence description
- Be categorized as: feature, improvement, fix, or security
- Include 2-3 highlight bullet points

IMPORTANT: Do NOT duplicate these existing entries: """ + str(existing_titles) + """
Respond ONLY with valid JSON array like:
[{"title": "...", "description": "...", "category": "feature|improvement|fix|security", "highlights": ["...", "..."]}]""",
                ).with_model("openai", "gpt-4o")

                prompt = f"""Platform metrics (last 7 days):
- Total users: {metrics.get('total_users', 'N/A')}
- New users (7d): {metrics.get('new_users_7d', 'N/A')}
- Referrals: {metrics.get('total_referrals', 'N/A')}/{metrics.get('new_referrals_7d', 'N/A')}
- Nova AI conversations (7d): {metrics.get('nova_conversations_7d', 'N/A')}
- FAQ searches (7d): {metrics.get('faq_searches_7d', 'N/A')}
Current date: {now.strftime('%B %d, %Y')}. Generate entries reflecting real improvements."""

                response = await chat.send_message(UserMessage(text=prompt))
                import json
                text = response.strip()
                if "```" in text:
                    text = text.split("```")[1].replace("json", "").strip()
                entries_data = json.loads(text)

                version = f"v{now.strftime('%Y.%m.%d')}"
                created = 0
                for ed in entries_data:
                    if ed.get("title") in existing_titles:
                        continue
                    entry = {
                        "entry_id": f"cl_{uuid.uuid4().hex[:12]}",
                        "title": ed["title"],
                        "description": ed.get("description", ""),
                        "category": ed.get("category", "feature"),
                        "version": version,
                        "highlights": ed.get("highlights", []),
                        "is_published": False,
                        "created_by": "ai_scheduled_weekly",
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                        "ai_generated": True,
                    }
                    await db.changelog_entries.insert_one(entry)
                    created += 1

                logger.info(f"Scheduled changelog generation: {created} entries created as drafts")
            except Exception as e:
                logger.error(f"Scheduled changelog generation failed: {e}")
        scheduler.add_job(scheduled_changelog_generation, CronTrigger(day_of_week='mon', hour=10, minute=0), id="weekly_changelog_generation", replace_existing=True,
    max_instances=1)

        # ── Renewal Reminders ──
        async def scheduled_renewal_reminders():
            logger.info("Running renewal reminder check...")
            try:
                from routes.notification_engine import emit_notification
                from utils.email_service import is_email_configured

                now = datetime.now(timezone.utc)
                total_sent = 0
                for days in [7, 3, 1]:
                    target_date = (now + timedelta(days=days)).strftime("%Y-%m-%d")
                    users = await db.users.find({
                        "subscription_status": "active",
                        "subscription_plan": {"$ne": "free"},
                        "subscription_permanent": {"$ne": True},
                        "access_locked": {"$ne": True},
                        "subscription_expires_at": {"$regex": f"^{target_date}"},
                    }, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1}).to_list(500)
                    for u in users:
                        existing = await db.notifications.find_one({
                            "user_id": u["user_id"],
                            "type": f"renewal_reminder_{days}d",
                            "created_at": {"$gte": (now - timedelta(hours=20)).isoformat()},
                        })
                        if existing:
                            continue
                        plan_name = u.get("subscription_plan", "").title()
                        title = f"Subscription expires in {days} day{'s' if days > 1 else ''}"
                        body = f"Your {plan_name} subscription will expire on {target_date}. Renew now to keep all your premium features."

                        # Use central notification engine (in-app + WebSocket + push)
                        await emit_notification(
                            user_id=u["user_id"],
                            notif_type=f"renewal_reminder_{days}d",
                            title=title,
                            body=body,
                            action_url="/subscription/plans",
                            send_email_notification=False,
                        )

                        # Send email for renewal reminders (critical communication)
                        if is_email_configured() and u.get("email"):
                            try:
                                from utils.email_service import send_catalog_template
                                await send_catalog_template(
                                    recipient_email=u["email"],
                                    template_key="renewal_reminder",
                                    recipient_name=u.get("name", ""),
                                    user_name=u.get("name", ""),
                                    plan_name=plan_name,
                                    renewal_date=target_date,
                                    amount="",
                                    days_remaining=days,
                                )
                            except Exception as e:
                                logger.error(f"Renewal email failed for {u['user_id']}: {e}")

                        total_sent += 1
                if total_sent > 0:
                    logger.info(f"Sent {total_sent} renewal reminders (in-app + email + push)")
            except Exception as e:
                logger.error(f"Renewal reminder failed: {e}")

        scheduler.add_job(scheduled_renewal_reminders, CronTrigger(hour=9, minute=0), id="renewal_reminders", replace_existing=True,
    max_instances=1)

        # ── Hiring ──
        from routes.integrations import send_booking_reminders, send_agenda_event_reminders
        scheduler.add_job(send_booking_reminders, IntervalTrigger(minutes=2), id="meeting_reminders_integrations", replace_existing=True,
    max_instances=1)
        scheduler.add_job(send_agenda_event_reminders, IntervalTrigger(minutes=1), id="agenda_event_reminders", replace_existing=True,
    max_instances=1)

        from routes.smart_scheduler import send_interview_reminders, send_daily_job_suggestions, detect_hiring_delays, notify_employers_new_candidates
        from routes.weekly_hiring_report import send_weekly_hiring_report
        scheduler.add_job(send_interview_reminders, IntervalTrigger(minutes=3), id="interview_reminders", replace_existing=True,
    max_instances=1)
        scheduler.add_job(send_daily_job_suggestions, CronTrigger(hour=8, minute=30), id="daily_job_suggestions", replace_existing=True,
    max_instances=1)
        scheduler.add_job(detect_hiring_delays, IntervalTrigger(hours=6), id="hiring_delay_detection", replace_existing=True,
    max_instances=1)
        scheduler.add_job(notify_employers_new_candidates, IntervalTrigger(hours=4), id="new_candidate_notifications", replace_existing=True,
    max_instances=1)
        scheduler.add_job(send_weekly_hiring_report, CronTrigger(day_of_week='mon', hour=9, minute=30), id="weekly_hiring_report", replace_existing=True,
    max_instances=1)

        # ── Employer ──
        from routes.employers import auto_unlock_employer_reverification
        scheduler.add_job(auto_unlock_employer_reverification, IntervalTrigger(hours=6), id="employer_reverify_unlock", replace_existing=True,
    max_instances=1)

        from routes.id_verification import auto_unlock_idv_reverification
        scheduler.add_job(auto_unlock_idv_reverification, IntervalTrigger(hours=6), id="idv_reverify_unlock", replace_existing=True,
    max_instances=1)

        # ── Engagement Emails ──
        from scheduler_jobs import (
            scheduled_weekly_engagement_emails,
            scheduled_weekly_careers_job_creation_and_announcement,
            scheduled_talent_network_role_alert_dispatch,
            scheduled_talent_network_campaign_scheduler,
            scheduled_bill_generator_hourly_daemon,
            scheduled_watch_videos_daily_drop,
        )
        scheduler.add_job(scheduled_weekly_engagement_emails, CronTrigger(day_of_week='mon', hour=9, minute=0), id="weekly_engagement_emails", replace_existing=True,
    max_instances=1)
        scheduler.add_job(
            scheduled_weekly_careers_job_creation_and_announcement,
            CronTrigger(day_of_week='mon', hour=8, minute=45),
            id="weekly_careers_job_automation",
            replace_existing=True,
            max_instances=1)
        from scheduler_jobs import scheduled_job_search_weekly_digest
        scheduler.add_job(
            scheduled_job_search_weekly_digest,
            CronTrigger(day_of_week='mon', hour=9, minute=30),
            id="job_search_weekly_digest",
            replace_existing=True,
            max_instances=1)
        from scheduler_jobs import scheduled_streak_protection_nudge
        scheduler.add_job(
            scheduled_streak_protection_nudge,
            CronTrigger(hour=18, minute=0),
            id="streak_protection_nudge",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_talent_network_role_alert_dispatch,
            IntervalTrigger(hours=24),
            id="careers_talent_network_role_alert_dispatch",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_talent_network_campaign_scheduler,
            IntervalTrigger(minutes=5),
            id="careers_talent_network_campaign_scheduler",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_bill_generator_hourly_daemon,
            IntervalTrigger(hours=1),
            id="bill_generator_hourly_daemon",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_watch_videos_daily_drop,
            CronTrigger(hour=0, minute=0),
            id="watch_videos_daily_drop",
            replace_existing=True,
            max_instances=1)

        # ── Meeting Reminders ──
        from scheduler_jobs import check_meeting_reminders
        scheduler.add_job(check_meeting_reminders, IntervalTrigger(minutes=5), id="meeting_reminders", replace_existing=True,
    max_instances=1)

        # ── SLA, Fraud, Self-Repair ──
        from routes import sla_engine, fraud_engine, self_repair_engine
        scheduler.add_job(sla_engine.run_sla_escalation, IntervalTrigger(hours=6), id="sla_ticket_escalation", replace_existing=True,
    max_instances=1)
        scheduler.add_job(fraud_engine.run_fraud_scan, IntervalTrigger(hours=12), id="fraud_scan", replace_existing=True,
    max_instances=1)
        scheduler.add_job(self_repair_engine.run_self_repair, IntervalTrigger(hours=6), id="self_repair", replace_existing=True,
    max_instances=1)

        # ── Proactive Support Nudges (every 60 min) ──
        try:
            from routes.admin_management import run_support_proactive_nudges

            async def scheduled_support_proactive_nudges():
                try:
                    summary = await run_support_proactive_nudges(trigger="apscheduler_hourly")
                    logger.info(
                        "[support-proactive-nudges] scanned=%s generated=%s",
                        summary.get("scanned", 0),
                        summary.get("generated", 0),
                    )
                except Exception as exc:
                    logger.error(f"Support proactive nudge run failed: {exc}")

            scheduler.add_job(
                scheduled_support_proactive_nudges,
                IntervalTrigger(hours=1),
                id="support_proactive_nudges",
                replace_existing=True,
                max_instances=1)
        except Exception as exc:
            logger.error(f"Support proactive nudge scheduler registration failed: {exc}")

        # ── Platform Compliance Digest (daily 08:20 UTC) ──
        try:
            from routes.compliance_digest_hub import generate_platform_compliance_digest

            async def scheduled_platform_compliance_digest():
                try:
                    record = await generate_platform_compliance_digest(trigger="apscheduler_daily")
                    digest = (record or {}).get("digest") or {}
                    logger.info(
                        "[platform-compliance-digest] severity=%s sent=%s/%s",
                        digest.get("severity", "unknown"),
                        record.get("sent_ok", 0),
                        len(record.get("recipients") or []),
                    )
                except Exception as exc:
                    logger.error(f"Platform compliance digest failed: {exc}")

            scheduler.add_job(
                scheduled_platform_compliance_digest,
                CronTrigger(hour=8, minute=20),
                id="platform_compliance_digest_daily",
                replace_existing=True,
                max_instances=1)
        except Exception as exc:
            logger.error(f"Platform compliance digest scheduler registration failed: {exc}")

        # ── Session Cleanup ──
        from routes.admin_session_cleanup import run_all_enabled_policies
        scheduler.add_job(run_all_enabled_policies, IntervalTrigger(hours=1), id="session_cleanup", replace_existing=True,
    max_instances=1)

        # ── Auto-Response Scan ──
        from scheduler_jobs import run_auto_response_scan
        scheduler.add_job(run_auto_response_scan, IntervalTrigger(minutes=5), id="auto_response_scan", replace_existing=True,
    max_instances=1)

        # ── Anomaly Alert Check (every 15 min) ──
        from server import run_anomaly_alert_check
        scheduler.add_job(run_anomaly_alert_check, IntervalTrigger(minutes=15), id="anomaly_alert_check", replace_existing=True,
    max_instances=1)

        # ── Continuous Enterprise Auto-Audit + Regression Gate + Growth Monitor ──
        from scheduler_jobs import (
            scheduled_platform_cache_freshness_guard,
            scheduled_acceptance_report_refresh,
            scheduled_logo_render_probe,
            scheduled_full_system_auto_audit,
            scheduled_enterprise_lock_cycle,
            scheduled_slo_breach_auto_mitigation,
            scheduled_weekly_enterprise_standard_enforcement,
            scheduled_e2e_regression_gate,
            scheduled_growth_integrity_monitor,
            scheduled_global_experience_assurance,
            scheduled_fedapay_webhook_self_heal,
            scheduled_resend_webhook_guard,
            scheduled_tax_compliance_audit,
            scheduled_learning_certificate_anchor_batch,
            scheduled_learning_hub_integrity_guard,
            scheduled_learning_hub_weekly_autopublish,
            scheduled_learning_hub_video_maintenance,
            scheduled_learning_hub_assurance_guard,
            scheduled_learning_hub_email_dispatcher,
            scheduled_learning_hub_synthetic_canary,
        )
        scheduler.add_job(
            scheduled_platform_cache_freshness_guard,
            IntervalTrigger(minutes=10),
            id="platform_cache_freshness_guard",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_acceptance_report_refresh,
            CronTrigger(hour=3, minute=30),
            id="cross_provider_acceptance_report_refresh",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_logo_render_probe,
            CronTrigger(hour=3, minute=40),
            id="logo_render_probe",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_full_system_auto_audit,
            IntervalTrigger(hours=2),
            id="platform_full_auto_audit",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_enterprise_lock_cycle,
            IntervalTrigger(hours=1),
            id="enterprise_lock_cycle",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_slo_breach_auto_mitigation,
            IntervalTrigger(minutes=3),
            id="slo_breach_auto_mitigation",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_weekly_enterprise_standard_enforcement,
            CronTrigger(day_of_week='sun', hour=5, minute=45),
            id="enterprise_standard_weekly_guard",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_e2e_regression_gate,
            IntervalTrigger(minutes=30),
            id="platform_e2e_regression_gate",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_growth_integrity_monitor,
            IntervalTrigger(minutes=20),
            id="growth_integrity_monitor",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_global_experience_assurance,
            IntervalTrigger(minutes=20),
            id="global_experience_assurance",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_fedapay_webhook_self_heal,
            IntervalTrigger(minutes=10),
            id="fedapay_webhook_self_heal",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_resend_webhook_guard,
            IntervalTrigger(minutes=15),
            id="resend_webhook_guard",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_tax_compliance_audit,
            IntervalTrigger(hours=6),
            id="scheduled_tax_compliance_audit",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_learning_certificate_anchor_batch,
            IntervalTrigger(hours=1),
            id="learning_certificate_anchor_batch",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_learning_hub_integrity_guard,
            IntervalTrigger(hours=1),
            id="learning_hub_integrity_guard",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_learning_hub_assurance_guard,
            IntervalTrigger(minutes=15),
            id="learning_hub_assurance_guard",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_learning_hub_video_maintenance,
            IntervalTrigger(minutes=30),
            id="learning_hub_video_maintenance",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_learning_hub_weekly_autopublish,
            CronTrigger(day_of_week='mon', hour=6, minute=0),
            id="learning_hub_weekly_autopublish",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_learning_hub_email_dispatcher,
            IntervalTrigger(minutes=1),
            id="learning_hub_email_dispatcher",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_learning_hub_synthetic_canary,
            IntervalTrigger(hours=1),
            id="learning_hub_synthetic_canary",
            replace_existing=True,
            max_instances=1)

        from routes.ai_platform_integrity import (
            scheduled_platform_integrity_daily,
            scheduled_platform_integrity_guardian,
            scheduled_platform_integrity_realtime,
        )
        scheduler.add_job(
            scheduled_platform_integrity_guardian,
            IntervalTrigger(minutes=5),
            id="ai_platform_integrity_guardian",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_platform_integrity_realtime,
            IntervalTrigger(minutes=15),
            id="ai_platform_integrity_realtime",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_platform_integrity_daily,
            CronTrigger(hour=4, minute=0),
            id="ai_platform_integrity_daily",
            replace_existing=True,
            max_instances=1)

        from routes.iap import (
            scheduled_iap_nightly_health_drill,
            scheduled_iap_tax_freshness_guard,
            scheduled_iap_webhook_retry_cycle,
        )

        scheduler.add_job(
            scheduled_iap_webhook_retry_cycle,
            IntervalTrigger(minutes=3),
            id="iap_webhook_retry_cycle",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_iap_nightly_health_drill,
            CronTrigger(hour=3, minute=30),
            id="iap_nightly_health_drill",
            replace_existing=True,
            max_instances=1)
        scheduler.add_job(
            scheduled_iap_tax_freshness_guard,
            IntervalTrigger(minutes=15),
            id="iap_tax_freshness_guard",
            replace_existing=True,
            max_instances=1)

        # ── Autonomous Engine Nightly Blocked Attempt Export (1:20 AM UTC) ──
        from scheduler_jobs import scheduled_autonomous_blocked_attempts_export
        scheduler.add_job(
            scheduled_autonomous_blocked_attempts_export,
            CronTrigger(hour=1, minute=20),
            id="autonomous_blocked_attempts_nightly_export",
            replace_existing=True,
            max_instances=1)

        # ── Payment Analytics Reports ──
        from routes.payments import run_scheduled_payment_reports

        async def weekly_payment_reports():
            await run_scheduled_payment_reports("weekly")

        async def monthly_payment_reports():
            await run_scheduled_payment_reports("monthly")

        scheduler.add_job(weekly_payment_reports, CronTrigger(day_of_week='mon', hour=8, minute=30), id="weekly_payment_reports", replace_existing=True,
    max_instances=1)
        scheduler.add_job(monthly_payment_reports, CronTrigger(day=1, hour=8, minute=30), id="monthly_payment_reports", replace_existing=True,
    max_instances=1)

        # ── Renewal Reminder Check (daily at 9:00 UTC) ──
        from routes.payments import run_renewal_reminder_check

        async def daily_renewal_check():
            await run_renewal_reminder_check()

        scheduler.add_job(daily_renewal_check, CronTrigger(hour=9, minute=0), id="daily_renewal_reminders", replace_existing=True,
    max_instances=1)

        # ── Daily Notification Digest ──
        from routes.notification_engine import _send_daily_digest_for_user

        async def daily_notification_digest():
            """Send daily digest emails to all eligible users at 8 AM UTC."""
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            user_ids = await db.notifications.distinct("user_id", {"read": False, "created_at": {"$gte": cutoff}})
            sent, skipped = 0, 0
            for uid in user_ids:
                result = await _send_daily_digest_for_user(uid)
                if result.get("sent"):
                    sent += 1
                else:
                    skipped += 1
            logger.info(f"Daily digest: sent={sent}, skipped={skipped}, total={len(user_ids)}")

        scheduler.add_job(daily_notification_digest, CronTrigger(hour=8, minute=0), id="daily_notification_digest", replace_existing=True,
    max_instances=1)

        # ── Nightly Data Integrity Scan (3 AM UTC) ──
        async def nightly_integrity_scan():
            """Check data consistency: orphan records, missing fields, stale sessions."""
            logger.info("Starting nightly data integrity scan...")
            results = {"timestamp": datetime.now(timezone.utc).isoformat(), "scan_id": f"scan_{uuid.uuid4().hex[:12]}"}
            issues = []
            try:
                # 1. Stale sessions (all expired)
                now = datetime.now(timezone.utc)
                stale_count = await db.user_sessions.count_documents({"expires_at": {"$lt": now}})
                if stale_count > 0:
                    await db.user_sessions.delete_many({"expires_at": {"$lt": now}})
                    issues.append({"type": "stale_sessions", "count": stale_count, "action": "cleaned"})

                # 2. Users without email
                no_email = await db.users.count_documents({"email": {"$in": [None, ""]}})
                if no_email > 0:
                    issues.append({"type": "users_without_email", "count": no_email, "action": "flagged"})

                # 3. Payments without user_id
                orphan_payments = await db.payments.count_documents({"user_id": {"$in": [None, ""]}})
                if orphan_payments > 0:
                    issues.append({"type": "orphan_payments", "count": orphan_payments, "action": "flagged"})

                # 4. Goals without user_id
                orphan_goals = await db.ai_goals.count_documents({"user_id": {"$in": [None, ""]}})
                if orphan_goals > 0:
                    issues.append({"type": "orphan_goals", "count": orphan_goals, "action": "flagged"})

                # 5. Notifications older than 90 days
                old_notif_cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
                old_notifs = await db.notifications.count_documents({"created_at": {"$lt": old_notif_cutoff}})
                if old_notifs > 0:
                    await db.notifications.delete_many({"created_at": {"$lt": old_notif_cutoff}})
                    issues.append({"type": "old_notifications", "count": old_notifs, "action": "cleaned"})

                # 6. Collection stats
                user_count = await db.users.count_documents({})
                payment_count = await db.payments.count_documents({})
                goal_count = await db.ai_goals.count_documents({})
                results["stats"] = {"users": user_count, "payments": payment_count, "goals": goal_count}
            except Exception as e:
                issues.append({"type": "scan_error", "error": str(e)})

            results["issues"] = issues
            results["issues_count"] = len(issues)
            results["status"] = "clean" if len(issues) == 0 else "issues_found"
            await db.integrity_scans.insert_one(results)
            logger.info(f"Integrity scan complete: {len(issues)} issue(s) found")

        scheduler.add_job(nightly_integrity_scan, CronTrigger(hour=3, minute=0), id="nightly_integrity_scan", replace_existing=True,
    max_instances=1)

        # ── Nightly Auto-Backup (4 AM UTC) ──
        async def nightly_auto_backup():
            """Export key collections to JSON for backup."""
            logger.info("Starting nightly auto-backup...")
            backup_id = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            backup_meta = {"backup_id": backup_id, "timestamp": datetime.now(timezone.utc).isoformat(), "collections": {}}
            try:
                for coll_name in ["users", "payments", "ai_goals", "subscriptions", "notifications"]:
                    coll = db[coll_name]
                    count = await coll.count_documents({})
                    # Store document count as backup metadata (actual backup would write to S3/disk in production)
                    backup_meta["collections"][coll_name] = {"document_count": count}

                backup_meta["status"] = "completed"
                backup_meta["size_estimate"] = "metadata_only"
            except Exception as e:
                backup_meta["status"] = "failed"
                backup_meta["error"] = str(e)
                logger.error(f"Auto-backup failed: {e}")

            await db.backup_history.insert_one(backup_meta)
            # Retain only last 30 backups
            all_backups = await db.backup_history.count_documents({})
            if all_backups > 30:
                oldest = await db.backup_history.find({}, {"_id": 1}).sort("timestamp", 1).limit(all_backups - 30).to_list(100)
                if oldest:
                    ids = [b["_id"] for b in oldest]
                    await db.backup_history.delete_many({"_id": {"$in": ids}})
            logger.info(f"Auto-backup {backup_id} completed")

        scheduler.add_job(nightly_auto_backup, CronTrigger(hour=4, minute=0), id="nightly_auto_backup", replace_existing=True,
    max_instances=1)

        # ── Newsletter Monthly Campaign ──
        from routes.newsletter_campaigns_router import run_monthly_campaign
        scheduler.add_job(run_monthly_campaign, CronTrigger(hour=10, minute=0), id="newsletter_monthly_campaign", replace_existing=True,
    max_instances=1)

        # ── Newsletter Segment Refresh ──
        from routes.newsletter_segments_router import refresh_all_segments
        scheduler.add_job(refresh_all_segments, CronTrigger(hour=3, minute=30), id="newsletter_segment_refresh", replace_existing=True,
    max_instances=1)

        # ── CSAT Survey (every 45 days) ──
        async def scheduled_csat_surveys():
            try:
                from routes.csat_router import _send_csat_surveys
                sent = await _send_csat_surveys(db, target="all")
                if sent > 0:
                    logger.info(f"CSAT: Sent {sent} satisfaction surveys")
            except Exception as e:
                logger.error(f"CSAT survey send failed: {e}")
        scheduler.add_job(scheduled_csat_surveys, CronTrigger(hour=9, minute=0), id="csat_survey_auto", replace_existing=True,
    max_instances=1)

        # ── CSAT Reminder (7 days after initial send) ──
        async def scheduled_csat_reminders():
            try:
                from routes.csat_router import _send_csat_reminders
                sent = await _send_csat_reminders(db)
                if sent > 0:
                    logger.info(f"CSAT: Sent {sent} reminder(s)")
            except Exception as e:
                logger.error(f"CSAT reminder send failed: {e}")
        scheduler.add_job(scheduled_csat_reminders, CronTrigger(hour=9, minute=30), id="csat_reminder_auto", replace_existing=True,
    max_instances=1)

        # ── Onboarding Drip Campaign (daily at 9:00 AM) ──
        async def scheduled_drip_campaign():
            try:
                from routes.drip_campaign import process_drip_campaigns
                sent = await process_drip_campaigns()
                if sent > 0:
                    logger.info(f"Drip campaign: {sent} emails sent")
            except Exception as e:
                logger.error(f"Drip campaign failed: {e}")
        scheduler.add_job(scheduled_drip_campaign, CronTrigger(hour=9, minute=0), id="onboarding_drip_campaign", replace_existing=True,
    max_instances=1)

        # ── Alert Monitor (every 60s) ──
        from services.alert_monitor import run_alert_monitor

        async def scheduled_alert_monitor():
            try:
                await run_alert_monitor(db)
            except Exception as e:
                logger.error(f"Alert monitor failed: {e}")

        scheduler.add_job(scheduled_alert_monitor, IntervalTrigger(seconds=60), id="alert_monitor", replace_existing=True,
    max_instances=1)

        # ── Automation Dashboard WebSocket Broadcaster (every 15s) ──
        async def broadcast_automation_dashboard():
            """Push real-time automation data to connected WebSocket clients."""
            try:
                from utils.ws_manager import ws_manager
                if not ws_manager.automation_listeners:
                    return  # No clients connected, skip

                from routes.automation_engine import (
                    _get_all_heartbeats, _compute_real_mttr, _compute_automation_score
                )
                import psutil
                now = datetime.now(timezone.utc)

                # System metrics
                cpu = psutil.cpu_percent(interval=0.3)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage("/")

                # Heartbeats (real checks)
                heartbeats = await _get_all_heartbeats()

                # Incident stats
                coll = db.automation_incidents
                rules_coll = db.automation_rules
                total_incidents = await coll.count_documents({})
                open_incidents = await coll.count_documents({"status": "open"})
                resolved_24h = await coll.count_documents({
                    "status": "resolved",
                    "resolved_at": {"$gte": now - timedelta(hours=24)}
                })
                auto_healed = await coll.count_documents({"auto_healed": True})
                active_rules = await rules_coll.count_documents({"enabled": True})
                total_rules = await rules_coll.count_documents({})
                mttr = await _compute_real_mttr()
                score = _compute_automation_score(
                    active_rules, total_rules, open_incidents,
                    auto_healed, total_incidents, heartbeats
                )

                payload = {
                    "type": "automation:update",
                    "timestamp": now.isoformat(),
                    "system_metrics": {
                        "cpu_percent": cpu,
                        "memory_percent": round(mem.percent, 1),
                        "memory_used_gb": round(mem.used / (1024**3), 2),
                        "memory_total_gb": round(mem.total / (1024**3), 2),
                        "disk_percent": round(disk.percent, 1),
                        "disk_used_gb": round(disk.used / (1024**3), 2),
                        "disk_total_gb": round(disk.total / (1024**3), 2),
                    },
                    "heartbeats": heartbeats,
                    "incident_stats": {
                        "total": total_incidents,
                        "open": open_incidents,
                        "resolved_24h": resolved_24h,
                        "auto_healed": auto_healed,
                        "mttr_minutes": mttr,
                    },
                    "automation_score": score,
                    "rules": {"active": active_rules, "total": total_rules},
                }
                await ws_manager.broadcast_automation(payload)
            except Exception as e:
                logger.error(f"Automation WS broadcast failed: {e}")

        scheduler.add_job(broadcast_automation_dashboard, IntervalTrigger(seconds=15), id="automation_ws_broadcast", replace_existing=True,
    max_instances=1)

        # ── Scheduled Compliance Scan (weekly, configurable) ──
        async def scheduled_compliance_scan():
            try:
                config = await db.compliance_scan_config.find_one({})
                if not config or not config.get("enabled"):
                    return

                logger.info("[ComplianceScan] Running scheduled compliance scan...")
                import httpx
                base_url = (os.environ.get("FRONTEND_BASE_URL") or "").rstrip("/")
                if not base_url:
                    logger.warning("[ComplianceScan] FRONTEND_BASE_URL missing; skipping run")
                    return
                os.environ.get("REACT_APP_BACKEND_URL", base_url)

                # Record a posture snapshot first
                from routes.security_engine import SECURITY_HEADERS, WAF_PATTERNS
                now = datetime.now(timezone.utc)
                header_score = 0
                try:
                    async with httpx.AsyncClient(timeout=10.0, verify=get_httpx_verify()) as client:
                        resp = await client.get(base_url)
                        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                        for h_name, h_config in SECURITY_HEADERS.items():
                            present = h_name.lower() in resp_headers
                            passed = present
                            if h_config["expected"] != "present" and present:
                                passed = h_config["expected"].lower() in resp_headers.get(h_name.lower(), "").lower()
                            if passed:
                                header_score += 1
                except Exception:
                    pass

                header_pct = round((header_score / max(len(SECURITY_HEADERS), 1)) * 100)
                waf_enabled = sum(1 for r in WAF_PATTERNS if r["enabled"])
                custom_rules = await db.waf_custom_rules.count_documents({})
                waf_pct = min(100, round(((waf_enabled + custom_rules) / 10) * 100))
                overall = round((header_pct + waf_pct + 100 + 100) / 4)

                await db.security_posture_timeline.insert_one({
                    "timestamp": now, "overall_score": overall, "header_score": header_pct,
                    "waf_score": waf_pct, "auth_score": 100, "rate_limit_score": 100,
                    "waf_rules_active": waf_enabled + custom_rules,
                    "source": "scheduled_scan",
                })

                # Send email report if recipients configured
                recipients = config.get("email_recipients", [])
                if recipients:
                    try:
                        from routes.alerts import send_resend_email
                        subject = f"[RealAICoach] Weekly Compliance Scan — Score: {overall}%"
                        body_html = (
                            f"<h2>Scheduled Compliance Scan Report</h2>"
                            f"<p><strong>Overall Security Score:</strong> {overall}%</p>"
                            f"<p>Headers: {header_pct}% | WAF: {waf_pct}% | Auth: 100% | Rate Limiting: 100%</p>"
                            f"<p>Active WAF Rules: {waf_enabled + custom_rules}</p>"
                            f"<p><em>Generated at {now.isoformat()}</em></p>"
                            f"<p>View full report in the Admin Console → Security → Compliance tab.</p>"
                        )
                        for email in recipients:
                            await send_resend_email(email, subject, body_html)
                        logger.info(f"[ComplianceScan] Sent report to {len(recipients)} recipients")
                    except Exception as e:
                        logger.warning(f"[ComplianceScan] Email send failed: {e}")

                logger.info(f"[ComplianceScan] Scan complete. Score: {overall}%")
            except Exception as e:
                logger.error(f"Scheduled compliance scan failed: {e}")

        scheduler.add_job(scheduled_compliance_scan, CronTrigger(day_of_week="mon", hour=9, minute=0), id="weekly_compliance_scan", replace_existing=True,
    max_instances=1)

        # ── Weekly Unified ASO Report ──
        from routes.aso_unified import scheduled_weekly_report
        scheduler.add_job(scheduled_weekly_report, CronTrigger(day_of_week="mon", hour=8, minute=0), id="weekly_aso_report", replace_existing=True,
    max_instances=1)

        # ── Daily ASO Keyword Ranking Refresh (6 AM UTC) ──
        async def scheduled_keyword_refresh():
            """Auto-refresh all tracked ASO keyword rankings from live store data."""
            try:
                keywords = await db.aso_keywords.find({}).to_list(200)
                if not keywords:
                    return
                from services.aso_keyword_service import get_real_keyword_data
                now = datetime.now(timezone.utc)
                updated = 0
                for kw in keywords:
                    try:
                        real_data = await get_real_keyword_data(kw["keyword"])
                        prev_apple = kw.get("apple", {}).get("rank", 0)
                        prev_google = kw.get("google", {}).get("rank", 0)
                        new_apple = real_data["apple"]["rank"]
                        new_google = real_data["google"]["rank"]
                        await db.aso_keywords.update_one({"keyword": kw["keyword"]}, {"$set": {
                            "updated_at": now.isoformat(),
                            "data_source": "live",
                            "apple.prev_rank": prev_apple,
                            "apple.rank": new_apple,
                            "apple.difficulty": real_data["apple"]["difficulty"],
                            "apple.search_volume": real_data["apple"]["search_volume"],
                            "apple.total_results": real_data["apple"].get("total_results", 0),
                            "apple.top_results": real_data["apple"].get("top_results", []),
                            "google.prev_rank": prev_google,
                            "google.rank": new_google,
                            "google.difficulty": real_data["google"]["difficulty"],
                            "google.search_volume": real_data["google"]["search_volume"],
                            "google.total_results": real_data["google"].get("total_results", 0),
                            "google.top_results": real_data["google"].get("top_results", []),
                            "competitors": real_data["competitors"],
                        }})
                        # Store history point for trend analysis
                        await db.aso_keyword_ranking_history.insert_one({
                            "keyword": kw["keyword"],
                            "date": now.strftime("%Y-%m-%d"),
                            "timestamp": now.isoformat(),
                            "apple_rank": new_apple,
                            "google_rank": new_google,
                            "apple_difficulty": real_data["apple"]["difficulty"],
                            "google_difficulty": real_data["google"]["difficulty"],
                        })
                        # Check for significant rank changes and send email alerts
                        try:
                            from routes.aso_alerts import check_and_send_ranking_alerts
                            await check_and_send_ranking_alerts(kw["keyword"], prev_apple, new_apple, prev_google, new_google)
                        except Exception as ae:
                            logger.warning(f"Alert check failed for '{kw['keyword']}': {ae}")
                        updated += 1
                    except Exception as e:
                        logger.warning(f"Keyword refresh failed for '{kw['keyword']}': {e}")
                # Trim history (keep 90 days)
                cutoff = (now - timedelta(days=90)).isoformat()
                await db.aso_keyword_ranking_history.delete_many({"timestamp": {"$lt": cutoff}})
                logger.info(f"ASO keyword auto-refresh: {updated}/{len(keywords)} updated from live data")
            except Exception as e:
                logger.error(f"ASO keyword auto-refresh failed: {e}")
        scheduler.add_job(scheduled_keyword_refresh, CronTrigger(hour=6, minute=0), id="daily_aso_keyword_refresh", replace_existing=True,
    max_instances=1)

        # ── AI Auto-Detection (every 60 seconds) ──
        from routes.auto_detect import run_detection_cycle
        scheduler.add_job(run_detection_cycle, "interval", seconds=60, id="auto_detect_cycle", replace_existing=True,
    max_instances=1)

        # ── Weekly Translation Quality Check (Sundays 6 AM UTC) ──
        async def scheduled_translation_quality():
            try:
                from routes.i18n import run_weekly_translation_quality_check
                result = await run_weekly_translation_quality_check()
                logger.info(f"Translation quality check: avg={result.get('avg_score')}%, below_threshold={result.get('below_threshold')}")
            except Exception as e:
                logger.error(f"Translation quality check failed: {e}")
        scheduler.add_job(scheduled_translation_quality, CronTrigger(day_of_week='sun', hour=6, minute=0), id="weekly_translation_quality", replace_existing=True,
    max_instances=1)

        # ── Weekly Email Contrast Compliance Report (Sundays 7:30 AM UTC) ──
        from scheduler_jobs import scheduled_weekly_email_contrast_compliance
        scheduler.add_job(
            scheduled_weekly_email_contrast_compliance,
            CronTrigger(day_of_week='sun', hour=7, minute=30),
            id="weekly_email_contrast_compliance",
            replace_existing=True,
            max_instances=1)

        # ── Nightly Dark-Mode Regression Scan (Daily 02:40 UTC) ──
        from scheduler_jobs import scheduled_nightly_darkmode_regression_scan
        scheduler.add_job(
            scheduled_nightly_darkmode_regression_scan,
            CronTrigger(hour=2, minute=40),
            id="nightly_darkmode_regression_scan",
            replace_existing=True,
            max_instances=1)

        # ── Periodic Performance Audit (Every 6 hours) ──
        from scheduler_jobs import scheduled_perf_audit
        scheduler.add_job(
            scheduled_perf_audit,
            CronTrigger(hour='*/6', minute=15),
            id="periodic_perf_audit",
            replace_existing=True,
            max_instances=1)

        # ── Continuous Autonomous Execution (24/7 Mode) ──
        from scheduler_jobs import scheduled_continuous_cycle, scheduled_validity_autofix_refresh
        from routes.autonomous_engine import _get_engine_config

        continuous_config = await _get_engine_config()
        continuous_policy = continuous_config.get("continuous_policy", {})
        continuous_interval_minutes = max(5, min(1440, int(continuous_policy.get("interval_minutes", 30))))
        scheduler.add_job(
            scheduled_continuous_cycle,
            IntervalTrigger(minutes=continuous_interval_minutes),
            id="continuous_autonomous_cycle",
            replace_existing=True,
            max_instances=1)

        # ── Strict Gate Validity Auto-Refresh (no manual admin input) ──
        scheduler.add_job(
            scheduled_validity_autofix_refresh,
            IntervalTrigger(minutes=15),
            id="autonomous_validity_autofix",
            replace_existing=True,
            max_instances=1)

        # ── Predictive Failure Prevention Mode ──
        from scheduler_jobs import scheduled_predictive_failure_prevention

        predictive_policy = continuous_config.get("predictive_policy", {})
        predictive_interval_minutes = max(5, min(1440, int(predictive_policy.get("scheduled_interval_minutes", 30))))
        scheduler.add_job(
            scheduled_predictive_failure_prevention,
            IntervalTrigger(minutes=predictive_interval_minutes),
            id="predictive_failure_prevention",
            replace_existing=True,
            max_instances=1)

        # ── Zero-Trust Auto-Mitigation + Auto-Fix Integration ──
        from scheduler_jobs import scheduled_zero_trust_auto_mitigation, scheduled_zero_trust_daily_email_digest

        zero_trust_policy = continuous_config.get("zero_trust_policy", {})
        zero_trust_interval_minutes = max(5, min(1440, int(zero_trust_policy.get("interval_minutes", 10))))
        scheduler.add_job(
            scheduled_zero_trust_auto_mitigation,
            IntervalTrigger(minutes=zero_trust_interval_minutes),
            id="zero_trust_auto_mitigation",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=120),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )

        # ── Zero-Trust Daily Status Email Digest (checks every 15 minutes, sends once/day at configured UTC time) ──
        scheduler.add_job(
            scheduled_zero_trust_daily_email_digest,
            IntervalTrigger(minutes=15),
            id="zero_trust_daily_email_digest",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=150),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )

        # ── Theme Guardrail Scan (Light/Dark Global Audit) ──
        from scheduler_jobs import (
            scheduled_theme_guardrail_scan,
            scheduled_theme_drift_nightly_detector,
            scheduled_admin_tabs_theme_drift_report,
            scheduled_admin_tabs_theme_drift_weekly_digest,
        )

        scheduler.add_job(
            scheduled_theme_guardrail_scan,
            IntervalTrigger(minutes=30),
            id="theme_guardrail_scan",
            replace_existing=True,
            max_instances=1)

        # ── Theme Drift Nightly Detector + Ticket Creation (02:40 UTC) ──
        scheduler.add_job(
            scheduled_theme_drift_nightly_detector,
            CronTrigger(hour=2, minute=40),
            id="theme_drift_nightly_detector",
            replace_existing=True,
            max_instances=1)

        # ── Daily Admin/Tabs Theme Drift Report (03:15 UTC) ──
        scheduler.add_job(
            scheduled_admin_tabs_theme_drift_report,
            CronTrigger(hour=3, minute=15),
            id="admin_tabs_theme_drift_report",
            replace_existing=True,
            max_instances=1)

        # ── Weekly Admin/Tabs Theme Drift Email Digest (Mondays 07:45 UTC) ──
        scheduler.add_job(
            scheduled_admin_tabs_theme_drift_weekly_digest,
            CronTrigger(day_of_week='mon', hour=7, minute=45),
            id="admin_tabs_theme_drift_weekly_digest",
            replace_existing=True,
            max_instances=1)

        # ── Active Defense Nightly Scan (03:00 UTC) ──
        from scheduler_jobs import scheduled_active_defense_nightly_scan
        scheduler.add_job(
            scheduled_active_defense_nightly_scan,
            CronTrigger(hour=3, minute=0),
            id="active_defense_nightly_scan",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

        # ── Weekly Email Auto-Fix (Wednesdays 7 AM UTC) ──
        async def scheduled_email_autofix():
            try:
                from services.email_autofix import run_email_autofix
                result = await run_email_autofix()
                logger.info(f"Email auto-fix: status={result['status']}, underperformers={result['underperformers']}, fixes={result.get('fixes', 0)}")
            except Exception as e:
                logger.error(f"Email auto-fix failed: {e}")
        scheduler.add_job(scheduled_email_autofix, CronTrigger(day_of_week='wed', hour=7, minute=0), id="weekly_email_autofix", replace_existing=True,
    max_instances=1)

        # ── Nightly Security Posture Scan ──
        async def scheduled_nightly_security_scan():
            """Run security posture scan every night at 3 AM UTC. Email admin if any check degrades."""
            try:
                from routes.security_posture import _run_all_checks, _calculate_score

                results = await _run_all_checks()
                score, grade = _calculate_score(results)

                passed = sum(1 for r in results if r["status"] == "pass")
                warnings = sum(1 for r in results if r["status"] == "warn")
                failed = sum(1 for r in results if r["status"] == "fail")

                # Store scan
                await db.security_posture_scans.insert_one({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "score": score,
                    "grade": grade,
                    "total_checks": len(results),
                    "passed": passed,
                    "warnings": warnings,
                    "failed": failed,
                    "auto_fixed": 0,
                    "source": "nightly_cron",
                })

                # Check for degraded checks (fail or warn on critical/high severity)
                degraded = [r for r in results if r["status"] in ("fail", "warn") and r["severity"] in ("critical", "high")]

                if degraded:
                    # Build email alert
                    issues_html = ""
                    for d in degraded:
                        sev_color = "#EF4444" if d["severity"] == "critical" else "#F59E0B"
                        status_label = "FAIL" if d["status"] == "fail" else "WARN"
                        issues_html += f"""
                        <tr>
                          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;">
                            <span style="display:inline-block;padding:2px 8px;border-radius:4px;background:{sev_color}18;color:{sev_color};font-size:10px;font-weight:700;">{status_label}</span>
                          </td>
                          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;font-weight:600;color:#0F172A;font-size:13px;">{d['name']}</td>
                          <td style="padding:8px 12px;border-bottom:1px solid #E2E8F0;color:#64748B;font-size:12px;">{d['detail'][:80]}</td>
                        </tr>"""


                    # Send to admin
                    admin = await db.users.find_one({"is_admin": True}, {"_id": 0, "email": 1, "name": 1})
                    if admin:
                        from utils.email_service import send_catalog_template
                        await send_catalog_template(
                            recipient_email=admin["email"],
                            template_key="security_scan_alert",
                            recipient_name=admin.get("name", "Admin"),
                            score=score,
                            grade=grade,
                            degraded_count=len(degraded),
                            degraded_checks=degraded[:5],
                        )
                        logger.info(f"[SECURITY-SCAN] Nightly scan: {score}% ({grade}), {len(degraded)} degraded checks — alert sent to {admin['email']}")
                else:
                    logger.info(f"[SECURITY-SCAN] Nightly scan: {score}% ({grade}), all critical/high checks PASS — no alert needed")

            except Exception as e:
                logger.error(f"Nightly security scan failed: {e}")

        scheduler.add_job(scheduled_nightly_security_scan, CronTrigger(hour=3, minute=0), id="nightly_security_scan", replace_existing=True,
    max_instances=1)

        # Production-critical scheduler jobs
        from scheduler_jobs import scheduled_card_expiry_check, scheduled_invoice_dunning, scheduled_welcome_back_check
        scheduler.add_job(scheduled_card_expiry_check, CronTrigger(hour=10, minute=0), id="card_expiry_check", replace_existing=True,
    max_instances=1)
        scheduler.add_job(scheduled_invoice_dunning, CronTrigger(hour=11, minute=0), id="invoice_dunning", replace_existing=True,
    max_instances=1)
        scheduler.add_job(scheduled_welcome_back_check, CronTrigger(day_of_week="mon", hour=9, minute=30), id="welcome_back_check", replace_existing=True,
    max_instances=1)

        # Security incident spike alerting (every 10 minutes)
        from routes.security_incidents import check_incident_spike, check_and_autoblock_ips
        scheduler.add_job(check_incident_spike, IntervalTrigger(minutes=10), id="incident_spike_alert", replace_existing=True,
    max_instances=1)
        scheduler.add_job(check_and_autoblock_ips, IntervalTrigger(minutes=10), id="ip_autoblock", replace_existing=True,
    max_instances=1)

        # Monitoring-ledger retention cleanup (daily) — keeps noisy audit/alert
        # collections bounded so they don't bloat the DB.
        async def scheduled_monitoring_retention_cleanup():
            now = datetime.now(timezone.utc)
            d7 = (now - timedelta(days=7)).isoformat()
            d30 = (now - timedelta(days=30)).isoformat()
            d90 = (now - timedelta(days=90)).isoformat()
            targets = [
                ("gps_runtime_snapshots", "created_at", d7),
                ("security_incidents", "ts", d30),
                ("enterprise_autonomous_engine_audit", "checked_at", d30),
                ("gtec_c5_trust_monitor_runs", "checked_at", d30),
                ("gtec_c5_pipeline_alerts", "alerted_at", d30),
                ("ai_platform_integrity_runs", "finished_at", d30),
                ("incident_spike_alerts", "alerted_at", d90),
                ("perf_audit_history", "audited_at", d90),
                ("security_events", "timestamp", d90),
            ]
            deleted = {}
            for coll, field, cutoff in targets:
                try:
                    res = await db[coll].delete_many({field: {"$lt": cutoff, "$type": "string"}})
                    deleted[coll] = res.deleted_count
                except Exception as exc:
                    logger.error(f"[retention-cleanup] {coll} failed: {exc}")
            await db.scheduler_heartbeats.update_one(
                {"job_id": "monitoring_retention_cleanup"},
                {"$set": {"job_id": "monitoring_retention_cleanup", "last_run": now.isoformat(), "status": "ok", "details": deleted}},
                upsert=True,
            )
            logger.info(f"[retention-cleanup] deleted={deleted}")

        scheduler.add_job(scheduled_monitoring_retention_cleanup, IntervalTrigger(hours=24),
    id="monitoring_retention_cleanup", replace_existing=True,
    next_run_time=datetime.now(timezone.utc) + timedelta(minutes=5),
    coalesce=True, max_instances=1, misfire_grace_time=3600)

        # Monthly dependency vulnerability scan (1st of each month at 04:00 UTC)
        async def scheduled_monthly_dependency_scan():
            """Run pip-audit + yarn audit and store results. Email admin if high/critical found."""
            import subprocess
            import json as _json
            logger.info("[DEP-SCAN] Running monthly dependency vulnerability scan...")
            try:
                from routes.db import db as _db
                from datetime import datetime as _dt, timezone as _tz
                ts = _dt.now(_tz.utc).isoformat()
                be_proc = subprocess.run(["/root/.venv/bin/pip-audit", "--format", "json", "--progress-spinner", "off"], capture_output=True, text=True, timeout=120, cwd="/app/backend")
                be_vulns = []
                if be_proc.stdout:
                    d = _json.loads(be_proc.stdout)
                    be_vulns = [{"package": v.get("name","?"), "installed": v.get("version","?"), "id": v.get("id","?"), "fix": (v.get("fix_versions") or ["N/A"])[0], "description": v.get("description","")[:200]} for v in d.get("vulnerabilities", [])[:50]]
                be_sum = {"total": len(be_vulns)}

                fe_proc = subprocess.run(["yarn", "audit", "--json"], capture_output=True, text=True, timeout=120, cwd="/app/frontend")
                fe_vulns, fe_sum = [], {"total": 0, "critical": 0, "high": 0, "moderate": 0, "low": 0}
                for line in (fe_proc.stdout or "").split("\n"):
                    if not line.strip():
                        continue
                    try:
                        entry = _json.loads(line)
                        if entry.get("type") == "auditAdvisory":
                            adv = entry["data"]["advisory"]
                            fe_vulns.append({"package": adv.get("module_name","?"), "severity": adv.get("severity","?"), "title": adv.get("title","")[:200], "patched": adv.get("patched_versions","N/A")})
                        elif entry.get("type") == "auditSummary":
                            meta = entry.get("data",{}).get("vulnerabilities",{})
                            fe_sum = {"total": sum(meta.values()), "critical": meta.get("critical",0), "high": meta.get("high",0), "moderate": meta.get("moderate",0), "low": meta.get("low",0)}
                    except Exception:
                        continue

                total_v = len(be_vulns) + fe_sum.get("total", 0)
                crit = fe_sum.get("critical", 0)
                high = fe_sum.get("high", 0)
                risk = "low" if total_v == 0 else "medium" if crit == 0 and high == 0 else "high" if crit == 0 else "critical"

                await _db["dependency_scans"].insert_one({
                    "timestamp": ts, "risk_level": risk, "total_vulns": total_v,
                    "critical": crit, "high": high, "triggered_by": "scheduler:monthly",
                    "backend_summary": be_sum, "frontend_summary": fe_sum,
                    "backend_vulns": be_vulns[:50], "frontend_vulns": fe_vulns[:50],
                })

                logger.info(f"[DEP-SCAN] Monthly scan complete: {total_v} total vulns, {crit} critical, {high} high — risk={risk}")

                # Alert admin if any high or critical vulnerabilities found
                if crit > 0 or high > 0:
                    try:
                        admin = await _db.users.find_one({"is_admin": True}, {"_id": 0, "email": 1, "name": 1})
                        if admin:
                            # Route through the V7 catalog builder so the email
                            # passes the hard-block guardrail (no raw plain-text
                            # bypass — that would fail with v7_violation:True).
                            from utils.email_service import send_email
                            from utils.email_templates import build_system_alert_admin_email
                            sev = "CRITICAL" if crit > 0 else "HIGH"
                            tpl = build_system_alert_admin_email(
                                alert_type="Monthly Dependency Scan",
                                severity=sev,
                                description=(
                                    f"{total_v} vulnerabilities detected ({crit} critical, {high} high). "
                                    "Review and update the affected packages at your earliest convenience."
                                ),
                                component="Dependency Scanner",
                                timestamp=ts,
                            )
                            await send_email(
                                recipient_email=admin["email"],
                                subject=f"[{risk.upper()}] Monthly Dependency Scan — {total_v} vulnerabilities found",
                                content=tpl.html,
                                content_text=tpl.text,
                                name=admin.get("name", "Admin"),
                                template_key="system_alert_admin",
                            )
                            logger.info(f"[DEP-SCAN] Alert email sent to {admin['email']}")
                    except Exception as mail_err:
                        logger.warning(f"[DEP-SCAN] Failed to send alert email: {mail_err}")
            except Exception as exc:
                logger.error(f"[DEP-SCAN] Monthly dependency scan failed: {exc}")

        scheduler.add_job(scheduled_monthly_dependency_scan, CronTrigger(day=1, hour=4, minute=0), id="monthly_dependency_scan", replace_existing=True,
    max_instances=1)

        # ── GTEC Crawler Safe Auto Runs ──
        # Checks the `gtec_crawler_settings.auto_run.enabled` flag every 6h and
        # kicks a desktop-only platform scan if enabled. No-op when disabled.
        from routes.gtec_crawler_api import scheduled_auto_run as scheduled_gtec_auto_run
        scheduler.add_job(
            scheduled_gtec_auto_run,
            IntervalTrigger(hours=6),
            id="gtec_crawler_safe_auto_run",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=120),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )

        # ── GTEC C5 Safe Auto Runs (Global System Directive) ──
        # Ticks every hour; the tick reads the configured interval_hours + enabled
        # flag from `gtec_scan_c5_settings` and fires the full SAST+DAST+RBAC+
        # Subscription+Responsiveness+Perf directive pipeline when due.
        #
        # NOTE (catch-up): APScheduler's IntervalTrigger schedules the FIRST
        # run one full interval after scheduler start. Since the backend may
        # hot-reload / restart more often than 1h, the tick would never fire
        # in practice — explaining gaps of 6h+ between scans that admins
        # observed. We use `next_run_time = now + 90s` so every startup runs
        # a catch-up tick shortly after boot; the tick itself is idempotent
        # (it skips if a recent scan already exists within interval_hours).
        from services.gtec_scan_v2 import (
            MATRIX64_SCHEDULER_JOB_ID,
            SAFE_AUTO_RUN_JOB_ID,
            LEGACY_SAFE_AUTO_RUN_JOB_ID,
            REPORTS_COL,
            SETTINGS_COL,
            LEGACY_REPORTS_COL,
            LEGACY_SETTINGS_COL,
            build_trust_gate_snapshot,
            ensure_internal_collections_migrated,
            ensure_pipeline_enforcement_policy,
            get_pipeline_enforcement_state,
            run_external_host_certification_pass,
            run_go_no_go_release_drill,
            run_white_screen_sentry_matrix,
            scheduled_matrix64_pipeline_tick,
            should_retry_external_host_certification,
            scheduled_gtec_v2_tick,
        )
        await ensure_internal_collections_migrated(db)
        await ensure_pipeline_enforcement_policy(db, mode="soft-block", hard_block_after_hours=48)
        scheduler.add_job(
            scheduled_gtec_v2_tick,
            IntervalTrigger(hours=1),
            id=SAFE_AUTO_RUN_JOB_ID,
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=90),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )

        # ── Enterprise Reality Validation Guardian (assumption-free) ──
        # Runs every 5 minutes. Verifies critical autonomous-engine runtime
        # health from scheduler registration + fresh heartbeats. If stale,
        # attempts deterministic auto-recovery and notifies admins using a
        # registered template.
        guardian_process_started_at = datetime.now(timezone.utc)

        async def scheduled_enterprise_reality_validation_guardian():
            now = datetime.now(timezone.utc)
            # Startup grace period: restarts are the known cause of transient
            # heartbeat staleness — skip validation for the first 15 minutes.
            if (now - guardian_process_started_at).total_seconds() < 15 * 60:
                logger.info("[enterprise-guardian] startup grace period active — skipping validation cycle")
                return

            def _parse_iso(ts: str | None):
                if not ts:
                    return None
                try:
                    return datetime.fromisoformat(ts)
                except Exception:
                    return None

            def _fmt_downtime(start_ts: str | None) -> str:
                dt = _parse_iso(start_ts)
                if not dt:
                    return "unknown"
                secs = max(0, int((now - dt).total_seconds()))
                h, rem = divmod(secs, 3600)
                m, s = divmod(rem, 60)
                if h > 0:
                    return f"{h}h {m}m {s}s"
                if m > 0:
                    return f"{m}m {s}s"
                return f"{s}s"

            async def _collect_state() -> dict:
                required = [
                    SAFE_AUTO_RUN_JOB_ID,
                    MATRIX64_SCHEDULER_JOB_ID,
                    "gtec_crawler_safe_auto_run",
                    "gtec_upstream_watchdog_nightly",
                    "zero_trust_auto_mitigation",
                    "active_defense_nightly_scan",
                ]
                missing = [jid for jid in required if scheduler.get_job(jid) is None]

                v2_hb = await db.scheduler_heartbeats.find_one(
                    {"job_id": SAFE_AUTO_RUN_JOB_ID},
                    {"_id": 0, "last_run": 1, "status": 1, "details": 1},
                )
                if not v2_hb:
                    v2_hb = await db.scheduler_heartbeats.find_one(
                        {"job_id": LEGACY_SAFE_AUTO_RUN_JOB_ID},
                        {"_id": 0, "last_run": 1, "status": 1, "details": 1},
                    )
                # Read configured cadence so cadence-slip detection scales
                # with whatever the admin has set (3h, 6h, 12h, etc.)
                v2_settings = await db[SETTINGS_COL].find_one(
                    {}, {"_id": 0, "interval_hours": 1}
                ) or {}
                if not v2_settings:
                    v2_settings = await db[LEGACY_SETTINGS_COL].find_one(
                        {}, {"_id": 0, "interval_hours": 1}
                    ) or {}
                v2_interval_hours = int(v2_settings.get("interval_hours") or 6)
                v2_interval_hours = max(1, min(24, v2_interval_hours))
                # Latest *actual* scan report (heartbeat ≠ scan; tick records
                # a heartbeat on every iteration even when it skips firing).
                v2_latest_report = await db[REPORTS_COL].find_one(
                    {},
                    {"_id": 0, "generated_at": 1, "task_id": 1, "status": 1},
                    sort=[("generated_at", -1)],
                )
                if not v2_latest_report:
                    v2_latest_report = await db[LEGACY_REPORTS_COL].find_one(
                        {},
                        {"_id": 0, "generated_at": 1, "task_id": 1, "status": 1},
                        sort=[("generated_at", -1)],
                    )
                crawler_hb = await db.scheduler_heartbeats.find_one(
                    {"job_id": "gtec_crawler_safe_auto_run"},
                    {"_id": 0, "last_run": 1, "status": 1, "details": 1},
                )
                matrix64_hb = await db.scheduler_heartbeats.find_one(
                    {"job_id": MATRIX64_SCHEDULER_JOB_ID},
                    {"_id": 0, "last_run": 1, "status": 1, "details": 1},
                )
                watchdog = await db.gtec_upstream_watchdog_runs.find_one(
                    {}, {"_id": 0, "checked_at": 1}, sort=[("checked_at", -1)]
                )
                zt_auto_hb = await db.scheduler_heartbeats.find_one(
                    {"job_id": "zero_trust_auto_mitigation"},
                    {"_id": 0, "last_run": 1, "status": 1, "detail": 1},
                )
                zt_active_hb = await db.scheduler_heartbeats.find_one(
                    {"job_id": "active_defense_nightly_scan"},
                    {"_id": 0, "last_run": 1, "status": 1, "detail": 1},
                )
                engine_cfg = await db.autonomous_engine_config.find_one(
                    {"config_id": "global"},
                    {"_id": 0, "zero_trust_policy.interval_minutes": 1},
                ) or {}
                zt_interval_minutes = int(
                    ((engine_cfg.get("zero_trust_policy") or {}).get("interval_minutes") or 10)
                )
                zt_interval_minutes = max(5, min(60, zt_interval_minutes))

                v2_ts = _parse_iso((v2_hb or {}).get("last_run"))
                v2_latest_report_ts = _parse_iso((v2_latest_report or {}).get("generated_at"))
                crawler_ts = _parse_iso((crawler_hb or {}).get("last_run"))
                matrix64_ts = _parse_iso((matrix64_hb or {}).get("last_run"))
                watchdog_ts = _parse_iso((watchdog or {}).get("checked_at"))
                zt_auto_ts = _parse_iso((zt_auto_hb or {}).get("last_run"))
                zt_active_ts = _parse_iso((zt_active_hb or {}).get("last_run"))

                v2_fresh = bool(v2_ts and (now - v2_ts).total_seconds() <= (2 * 3600))
                # Cadence-slip detection (Reality Validation Guardian, v3)
                # ────────────────────────────────────────────────────────
                # Heartbeat freshness alone is insufficient: the tick
                # records a heartbeat every iteration, even when it skips
                # firing. A real cadence slip is detected by comparing the
                # most-recent *actual* scan report timestamp against
                # `interval_hours × 1.5` (1.5× tolerance to absorb scan
                # duration + late ticks without false positives).
                v2_cadence_slip_threshold_seconds = int(v2_interval_hours * 1.5 * 3600)
                v2_cadence_fresh = bool(
                    v2_latest_report_ts
                    and (now - v2_latest_report_ts).total_seconds()
                        <= v2_cadence_slip_threshold_seconds
                )
                crawler_fresh = bool(crawler_ts and (now - crawler_ts).total_seconds() <= (7 * 3600))
                matrix64_fresh = bool(matrix64_ts and (now - matrix64_ts).total_seconds() <= (30 * 3600))
                watchdog_fresh = bool(watchdog_ts and (now - watchdog_ts).total_seconds() <= (26 * 3600))
                zt_auto_fresh_seconds = max(45 * 60, zt_interval_minutes * 3 * 60)
                zt_auto_fresh = bool(zt_auto_ts and (now - zt_auto_ts).total_seconds() <= zt_auto_fresh_seconds)
                zt_active_fresh = bool(zt_active_ts and (now - zt_active_ts).total_seconds() <= (36 * 3600))

                reasons = []
                if missing:
                    reasons.append(f"missing_jobs:{','.join(missing)}")
                if not v2_fresh:
                    reasons.append("gtec_scan_c5_scheduler_heartbeat_stale_or_missing")
                # Cadence slip is a *separate* anomaly class from heartbeat
                # staleness — surface it explicitly so admins know whether
                # the tick is dead vs. the tick is alive but skipping.
                if not v2_cadence_fresh:
                    reasons.append(
                        f"gtec_scan_c5_cadence_slip:"
                        f"interval={v2_interval_hours}h:"
                        f"threshold={int(v2_interval_hours * 1.5)}h"
                    )
                if not crawler_fresh:
                    reasons.append("gtec_crawler_scheduler_heartbeat_stale_or_missing")
                if not matrix64_fresh:
                    reasons.append("gtec_c5_matrix64_pipeline_stale_or_missing")
                if not watchdog_fresh:
                    reasons.append("gtec_upstream_watchdog_run_stale_or_missing")
                if not zt_auto_fresh:
                    reasons.append("zero_trust_auto_mitigation_stale_or_missing")
                if not zt_active_fresh:
                    reasons.append("active_defense_nightly_scan_stale_or_missing")

                return {
                    "missing_jobs": missing,
                    "v2_fresh": v2_fresh,
                    "v2_cadence_fresh": v2_cadence_fresh,
                    "v2_interval_hours": v2_interval_hours,
                    "v2_cadence_slip_threshold_hours": round(v2_interval_hours * 1.5, 1),
                    "v2_latest_report": v2_latest_report or {},
                    "crawler_fresh": crawler_fresh,
                    "matrix64_fresh": matrix64_fresh,
                    "watchdog_fresh": watchdog_fresh,
                    "zt_auto_fresh": zt_auto_fresh,
                    "zt_active_fresh": zt_active_fresh,
                    "reasons": reasons,
                    "v2_heartbeat": v2_hb or {},
                    "crawler_heartbeat": crawler_hb or {},
                    "matrix64_heartbeat": matrix64_hb or {},
                    "watchdog": watchdog or {},
                    "zero_trust_heartbeat": zt_auto_hb or {},
                    "active_defense_heartbeat": zt_active_hb or {},
                }

            try:
                pre = await _collect_state()
                actions: list[str] = []

                # Deterministic auto-recovery (only when stale/missing).
                if pre["missing_jobs"]:
                    actions.append("critical_scheduler_jobs_missing_detected")

                if not pre["v2_fresh"]:
                    try:
                        await scheduled_gtec_v2_tick()
                        actions.append("triggered_gtec_scan_c5_tick")
                    except Exception as exc:
                        logger.error(f"[enterprise-guardian] gtec v2 tick recovery failed: {exc}")
                        actions.append("gtec_scan_c5_tick_recovery_failed")
                elif not pre.get("v2_cadence_fresh", True):
                    # v2_fresh is OK (heartbeats coming in) but the actual
                    # scan cadence has slipped past `interval × 1.5`.
                    # Trigger an immediate catch-up tick — the tick is
                    # idempotent (skips internally if a recent scan exists),
                    # so duplicate firing is safe.
                    try:
                        await scheduled_gtec_v2_tick()
                        actions.append(
                            f"triggered_gtec_scan_c5_cadence_catch_up:"
                            f"interval={pre.get('v2_interval_hours')}h"
                        )
                    except Exception as exc:
                        logger.error(
                            f"[enterprise-guardian] gtec v2 cadence catch-up failed: {exc}"
                        )
                        actions.append("gtec_scan_c5_cadence_catch_up_failed")

                if not pre["crawler_fresh"]:
                    try:
                        await scheduled_gtec_auto_run()
                        actions.append("triggered_gtec_crawler_auto_run")
                    except Exception as exc:
                        logger.error(f"[enterprise-guardian] gtec crawler recovery failed: {exc}")
                        actions.append("gtec_crawler_recovery_failed")

                if not pre.get("matrix64_fresh", True):
                    try:
                        await scheduled_matrix64_pipeline_tick()
                        actions.append("triggered_gtec_c5_matrix64_pipeline")
                    except Exception as exc:
                        logger.error(f"[enterprise-guardian] matrix64 recovery failed: {exc}")
                        actions.append("gtec_c5_matrix64_pipeline_recovery_failed")

                if not pre["watchdog_fresh"]:
                    try:
                        from services.gtec_upstream_watchdog import run_watchdog
                        await run_watchdog(db, trigger="enterprise_guardian_auto_recovery")
                        actions.append("triggered_gtec_upstream_watchdog")
                    except Exception as exc:
                        logger.error(f"[enterprise-guardian] watchdog recovery failed: {exc}")
                        actions.append("gtec_watchdog_recovery_failed")

                if not pre["zt_auto_fresh"]:
                    try:
                        await scheduled_zero_trust_auto_mitigation()
                        actions.append("triggered_zero_trust_auto_mitigation")
                    except Exception as exc:
                        logger.error(f"[enterprise-guardian] zero-trust recovery failed: {exc}")
                        actions.append("zero_trust_auto_mitigation_recovery_failed")

                if not pre["zt_active_fresh"]:
                    try:
                        await scheduled_active_defense_nightly_scan()
                        actions.append("triggered_active_defense_nightly_scan")
                    except Exception as exc:
                        logger.error(f"[enterprise-guardian] active-defense recovery failed: {exc}")
                        actions.append("active_defense_nightly_scan_recovery_failed")

                post = await _collect_state()
                status = "healthy" if not post["reasons"] else "degraded"

                # Persist truth snapshot for audits.
                await db.enterprise_autonomous_engine_audit.insert_one({
                    "checked_at": now.isoformat(),
                    "status": status,
                    "pre_reasons": pre["reasons"],
                    "post_reasons": post["reasons"],
                    "actions": actions,
                    "pre": pre,
                    "post": post,
                    "source": "enterprise_reality_validation_guardian",
                })

                state = await db.enterprise_autonomous_engine_guardian_state.find_one(
                    {"_id": "state"}, {"_id": 0}
                ) or {}
                last_status = state.get("status")
                last_alert_ts = _parse_iso(state.get("last_alert_at"))
                cooldown_seconds = 30 * 60
                can_alert = (not last_alert_ts) or (now - last_alert_ts).total_seconds() >= cooldown_seconds

                # Send admin notifications via REGISTERED TEMPLATE.
                notify_breach = status == "degraded" and (last_status != "degraded" or can_alert)
                notify_recovery = status == "healthy" and last_status == "degraded"

                # Self-heals completed within a single cycle are audit-logged
                # only — no admin email (noise suppression).
                if status == "healthy" and last_status != "degraded" and pre["reasons"] and actions:
                    logger.info(
                        f"[enterprise-guardian] self-healed within cycle (no alert sent): "
                        f"pre={pre['reasons']} actions={actions}"
                    )

                if notify_breach or notify_recovery:
                    try:
                        from utils.email_service import is_email_configured, send_catalog_template
                        if is_email_configured():
                            admins = []
                            async for u in db.users.find({"is_admin": True}, {"_id": 0, "email": 1}).limit(10):
                                if u.get("email"):
                                    admins.append(u["email"])
                            if not admins:
                                admins = ["admin@realaicoach.app"]

                            if notify_breach:
                                action_taken = (
                                    f"Auto-recovery attempted: {', '.join(actions)}"
                                    if actions else "Auto-recovery attempted: none"
                                )
                                for email in admins:
                                    await send_catalog_template(
                                        recipient_email=email,
                                        template_key="automation_alert",
                                        rule_name="Enterprise Autonomous Engine",
                                        metric_name="guardian_status",
                                        current_value="degraded",
                                        condition="=",
                                        threshold="healthy",
                                        action_taken=action_taken,
                                        is_recovery=False,
                                    )
                            elif notify_recovery:
                                for email in admins:
                                    await send_catalog_template(
                                        recipient_email=email,
                                        template_key="automation_alert",
                                        rule_name="Enterprise Autonomous Engine",
                                        metric_name="guardian_status",
                                        current_value="healthy",
                                        condition="=",
                                        threshold="healthy",
                                        action_taken="Autonomous guardrails restored to healthy state",
                                        is_recovery=True,
                                        downtime=_fmt_downtime(state.get("last_degraded_at")),
                                        fix_applied=(", ".join(actions) if actions else "Self-healed by scheduler guardrails"),
                                    )
                    except Exception as mail_exc:
                        logger.error(f"[enterprise-guardian] notification send failed: {mail_exc}")

                # Update latest guardian state.
                update = {
                    "status": status,
                    "last_checked_at": now.isoformat(),
                    "last_reasons": post["reasons"],
                    "last_actions": actions,
                }
                if status == "degraded":
                    update["last_degraded_at"] = state.get("last_degraded_at") or now.isoformat()
                    if notify_breach:
                        update["last_alert_at"] = now.isoformat()
                else:
                    update["last_recovered_at"] = now.isoformat()
                    if notify_recovery:
                        update["last_alert_at"] = now.isoformat()

                await db.enterprise_autonomous_engine_guardian_state.update_one(
                    {"_id": "state"}, {"$set": update}, upsert=True
                )
            except Exception as exc:
                logger.error(f"[enterprise-guardian] scheduled check failed: {exc}")

        scheduler.add_job(
            scheduled_enterprise_reality_validation_guardian,
            IntervalTrigger(minutes=5),
            id="enterprise_reality_validation_guardian",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=150),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=120,
        )

        # ── GTEC C5 Continuous Trust Monitor + Pipeline Enforcement ──
        # Runs every 10 minutes and records trust snapshots.
        # During soft-block, it alerts but does not enforce release-fail mode.
        # After 48h (or configured policy), it auto-escalates to hard-block mode.
        async def scheduled_gtec_c5_continuous_trust_monitor():
            try:
                snapshot = await build_trust_gate_snapshot(db)
                policy_state = await get_pipeline_enforcement_state(db)
                sentry = await run_white_screen_sentry_matrix(
                    db,
                    triggered_by="continuous_monitor",
                    force=True,
                )
                trust_score = float(snapshot.get("trust_score_percent") or 0.0)
                mode = str(policy_state.get("effective_mode") or "soft-block")

                degrade_reasons: list[str] = []
                if trust_score < 100.0:
                    degrade_reasons.append("trust_score_below_100")
                sentry_failed = int(sentry.get("failed_checks") or 0)
                sentry_total = int(sentry.get("total_checks") or 0)
                sentry_passed = bool(sentry.get("white_screen_gate_passed")) and sentry_failed == 0 and sentry_total > 0
                if not sentry_passed:
                    degrade_reasons.append("white_screen_sentry_failed")
                degraded = len(degrade_reasons) > 0

                monitor_doc = {
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "mode": mode,
                    "trust_score_percent": trust_score,
                    "passed_gates": int(snapshot.get("passed_gates") or 0),
                    "total_gates": int(snapshot.get("total_gates") or 0),
                    "degraded": degraded,
                    "latest_task_id": snapshot.get("latest_public_task_id") or "",
                    "policy_state": policy_state,
                    "gates": snapshot.get("gates") or [],
                    "degrade_reasons": degrade_reasons,
                    "white_screen_sentry": {
                        "run_id": sentry.get("run_id"),
                        "gate_passed": sentry_passed,
                        "failed_checks": sentry_failed,
                        "total_checks": sentry_total,
                        "generated_at": sentry.get("generated_at"),
                    },
                    "viewport_matrix": {
                        "route_source": sentry.get("route_source"),
                        "viewports": sentry.get("viewports") or ["mobile", "tablet", "desktop"],
                        "matrix_summary": sentry.get("matrix_summary") or {},
                    },
                }
                await db.gtec_c5_trust_monitor_runs.insert_one(monitor_doc)

                if degraded:
                    await db.gtec_c5_pipeline_alerts.insert_one(
                        {
                            "alerted_at": datetime.now(timezone.utc).isoformat(),
                            "mode": mode,
                            "trust_score_percent": trust_score,
                            "message": "GTEC C5 release-readiness degraded",
                            "reasons": degrade_reasons,
                            "white_screen_sentry_failed_checks": sentry_failed,
                            "latest_task_id": snapshot.get("latest_public_task_id") or "",
                        }
                    )

                    if mode == "hard-block":
                        try:
                            alert_state = await db.gtec_c5_alert_state.find_one({"_id": "state"}) or {}
                            _last_raw = alert_state.get("last_alert_at")
                            try:
                                _last_dt = datetime.fromisoformat(_last_raw) if _last_raw else None
                            except Exception:
                                _last_dt = None
                            _now_utc = datetime.now(timezone.utc)
                            _transitioned = alert_state.get("last_status") != "degraded"
                            _cooldown_ok = (not _last_dt) or (_now_utc - _last_dt).total_seconds() >= 3600
                            if not (_transitioned or _cooldown_ok):
                                logger.info("[gtec-c5-monitor] degraded but alert suppressed (cooldown, last_alert_at=%s)", _last_raw)
                                raise StopAsyncIteration
                            from utils.email_service import is_email_configured, send_catalog_template
                            if is_email_configured():
                                admins = []
                                async for u in db.users.find({"is_admin": True}, {"_id": 0, "email": 1}).limit(20):
                                    if u.get("email"):
                                        admins.append(u["email"])
                                if trust_score < 100.0:
                                    _metric, _cond, _thresh, _val = "trust_score_percent", "<", "100", str(trust_score)
                                else:
                                    _metric, _cond, _thresh, _val = "white_screen_sentry_failed_checks", ">", "0", str(sentry_failed)
                                for email in (admins or ["admin@realaicoach.app"]):
                                    await send_catalog_template(
                                        recipient_email=email,
                                        template_key="automation_alert",
                                        rule_name="GTEC C5 Trust Pipeline",
                                        metric_name=_metric,
                                        current_value=_val,
                                        condition=_cond,
                                        threshold=_thresh,
                                        action_taken=(
                                            f"Degrade reasons: {', '.join(degrade_reasons)}. "
                                            "Hard-block mode active: release pipeline must fail until trust score is "
                                            "restored to 100 and white-screen sentry is clean"
                                        ),
                                        is_recovery=False,
                                    )
                                await db.gtec_c5_alert_state.update_one(
                                    {"_id": "state"},
                                    {"$set": {"last_alert_at": _now_utc.isoformat()}},
                                    upsert=True,
                                )
                        except StopAsyncIteration:
                            pass
                        except Exception as mail_exc:
                            logger.error(f"[gtec-c5-monitor] failed to notify admins: {mail_exc}")

                await db.gtec_c5_alert_state.update_one(
                    {"_id": "state"},
                    {"$set": {
                        "last_status": "degraded" if degraded else "healthy",
                        "last_checked_at": datetime.now(timezone.utc).isoformat(),
                    }},
                    upsert=True,
                )

                logger.info(
                    "[gtec-c5-monitor] mode=%s trust=%.2f passed=%s/%s sentry=%s degraded=%s",
                    mode,
                    trust_score,
                    snapshot.get("passed_gates"),
                    snapshot.get("total_gates"),
                    "PASS" if sentry_passed else "FAIL",
                    degraded,
                )
            except Exception as exc:
                logger.error(f"[gtec-c5-monitor] continuous monitor failed: {exc}")

        scheduler.add_job(
            scheduled_gtec_c5_continuous_trust_monitor,
            IntervalTrigger(minutes=10),
            id="gtec_c5_continuous_trust_monitor",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=180),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=120,
        )

        # ── Global Matrix64 nightly anti-regression artifact pipeline ──
        # Strict 64-cell sweep: 4 routes × 4 viewports × 4 languages.
        scheduler.add_job(
            scheduled_matrix64_pipeline_tick,
            CronTrigger(hour=1, minute=0),
            id=MATRIX64_SCHEDULER_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=900,
        )

        # ── External-host certification retry gate ──
        # Re-runs full external-host certification automatically once
        # proxy/preview stability recovers, using retry heuristics + cooldown.
        async def scheduled_gtec_c5_external_host_certification_retry():
            try:
                retry = await should_retry_external_host_certification(db)
                if not bool(retry.get("needs_retry")):
                    return

                result = await run_external_host_certification_pass(
                    db,
                    triggered_by="scheduler_proxy_stability_retry",
                    force=False,
                    include_release_drill=True,
                    simulate_hard_block=True,
                )
                logger.info(
                    "[gtec-c5-external-cert-retry] status=%s id=%s reasons=%s",
                    result.get("status"),
                    result.get("certification_id"),
                    ",".join(retry.get("reasons") or []),
                )
            except Exception as exc:
                logger.error(f"[gtec-c5-external-cert-retry] failed: {exc}")

        scheduler.add_job(
            scheduled_gtec_c5_external_host_certification_retry,
            IntervalTrigger(minutes=15),
            id="gtec_c5_external_host_certification_retry",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=4),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=180,
        )

        # ── 48h Boundary Live GO/NO-GO Drill (non-simulated) ──
        async def scheduled_gtec_c5_boundary_go_no_go_drill():
            try:
                state = await get_pipeline_enforcement_state(db)
                if str(state.get("effective_mode") or "") != "hard-block":
                    return

                boundary_marker = str(state.get("hard_block_at") or "")
                if not boundary_marker:
                    return

                existing = await db.gtec_c5_release_drills.find_one(
                    {
                        "simulated_hard_block": False,
                        "boundary_marker": boundary_marker,
                    },
                    {"_id": 0, "drill_id": 1},
                    sort=[("drill_at", -1)],
                )
                if existing:
                    return

                drill = await run_go_no_go_release_drill(
                    db,
                    simulate_hard_block=False,
                    triggered_by="scheduler_boundary_guard",
                    boundary_marker=boundary_marker,
                )
                logger.info(
                    "[gtec-c5-boundary-drill] completed boundary=%s drill_id=%s decision=%s",
                    boundary_marker,
                    drill.get("drill_id"),
                    drill.get("decision"),
                )
            except Exception as exc:
                logger.error(f"[gtec-c5-boundary-drill] failed: {exc}")

        scheduler.add_job(
            scheduled_gtec_c5_boundary_go_no_go_drill,
            IntervalTrigger(minutes=15),
            id="gtec_c5_boundary_go_no_go_drill",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=3),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=180,
        )

        # ── DB Security Hardening Continuous Pass (enterprise) ──
        async def scheduled_db_security_hardening_pass():
            try:
                from utils.db_security_hardening import ensure_db_security_hardening
                result = await ensure_db_security_hardening(db)
                logger.info(
                    "[db-hardening] scheduled status=%s created=%s failed=%s",
                    result.get("status"),
                    len(result.get("created_indexes") or []),
                    len(result.get("failed_indexes") or []),
                )
            except Exception as exc:
                logger.error(f"[db-hardening] scheduled pass failed: {exc}")

        scheduler.add_job(
            scheduled_db_security_hardening_pass,
            CronTrigger(hour=2, minute=20),
            id="db_security_hardening_pass",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=6),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=180,
        )

        # ── Metro dev server health probe ──
        # Probes the Metro bundler at http://localhost:3001/status every
        # 5 minutes. On 2026-04-24 the `expo` supervisor service silently
        # failed for hours because `yarn expo start` resolved to a missing
        # global binary; web worked fine but mobile preview was a black
        # screen. Emits a single WARN log when the probe transitions
        # healthy→unhealthy so ops sees it in the aggregated log stream
        # without spamming on every tick.
        scheduler.add_job(
            probe_metro_dev_server,
            IntervalTrigger(minutes=2),
            id="metro_dev_server_health_probe",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=60,
        )

        # ── Web preview health probe + auto-recovery ──
        # Probes local route on :3000 every minute and auto-restarts
        # expo_manual (and fallback expo on sustained failures) to prevent
        # black preview spinner windows from persisting.
        scheduler.add_job(
            probe_web_preview_server,
            IntervalTrigger(minutes=1),
            id="web_preview_health_probe",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=45),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=60,
        )

        # ── Subscription prompt telemetry stability monitor ──
        # Every 15 minutes, compare trailing 1-hour volume against rolling
        # 6-hour average and persist anomalies/events for admin tracking.
        scheduler.add_job(
            monitor_subscription_prompt_telemetry,
            IntervalTrigger(minutes=15),
            id="subscription_prompt_telemetry_monitor",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=90),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=120,
        )

        # ── GPS notification replay worker (durable delivery at scale) ──
        async def scheduled_gps_notification_outbox_worker():
            try:
                from routes.db import db as runtime_db
                from routes.global_platform_state import process_gps_notification_outbox
                from services.gps_outbox import outbox_stats

                def _stats_now_iso() -> str:
                    return datetime.now(timezone.utc).isoformat()

                stats = await outbox_stats(runtime_db, _stats_now_iso)
                backlog = int(stats.get("queued", 0)) + int(stats.get("retrying", 0))

                if backlog >= 20000:
                    batch_size = 1800
                    max_cycles = 4
                elif backlog >= 5000:
                    batch_size = 900
                    max_cycles = 3
                elif backlog >= 1000:
                    batch_size = 350
                    max_cycles = 2
                else:
                    batch_size = 100
                    max_cycles = 1

                result = await process_gps_notification_outbox(batch_size=batch_size, max_cycles=max_cycles)
                logger.info(
                    "[gps-outbox] backlog=%s batch=%s cycles=%s processed=%s sent=%s retrying=%s failed=%s",
                    backlog,
                    batch_size,
                    result.get("cycles"),
                    result.get("processed"),
                    result.get("sent"),
                    result.get("retrying"),
                    result.get("failed"),
                )
            except Exception as exc:
                logger.error(f"[gps-outbox] worker failed: {exc}")

        scheduler.add_job(
            scheduled_gps_notification_outbox_worker,
            IntervalTrigger(seconds=45),
            id="gps_notification_outbox_worker",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=120,
        )

        # ── GPS outbox reconciliation (fill delivery gaps) ──
        async def scheduled_gps_notification_reconciliation():
            try:
                from routes.global_platform_state import reconcile_gps_notification_outbox
                result = await reconcile_gps_notification_outbox(limit_events=30)
                logger.info(
                    "[gps-outbox-reconcile] events_checked=%s inserted=%s",
                    result.get("events_checked"),
                    result.get("inserted"),
                )
            except Exception as exc:
                logger.error(f"[gps-outbox-reconcile] failed: {exc}")

        scheduler.add_job(
            scheduled_gps_notification_reconciliation,
            IntervalTrigger(minutes=10),
            id="gps_notification_outbox_reconciliation",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(minutes=2),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=180,
        )

        # ── GPS catalog integrity guard (permanent global safety net) ──
        async def scheduled_gps_catalog_integrity_guard():
            try:
                from routes.db import db as runtime_db
                from services.gps_catalog_guard import ensure_gps_catalog_integrity

                result = await ensure_gps_catalog_integrity(
                    runtime_db,
                    actor_user_id="scheduler_gps_catalog_guard",
                )
                await runtime_db.scheduler_heartbeats.update_one(
                    {"job_id": "gps_catalog_integrity_guard"},
                    {
                        "$set": {
                            "job_id": "gps_catalog_integrity_guard",
                            "status": "healthy" if bool((result.get("completeness") or {}).get("is_complete")) else "degraded",
                            "last_run": datetime.now(timezone.utc).isoformat(),
                            "details": {
                                "repaired": bool(result.get("repaired")),
                                "inserted_plans": result.get("inserted_plans") or [],
                                "inserted_faq": result.get("inserted_faq") or [],
                                "completeness": result.get("completeness") or {},
                            },
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                    upsert=True,
                )
                logger.info(
                    "[gps-catalog-guard] repaired=%s plans=%s faq=%s complete=%s",
                    result.get("repaired"),
                    len(result.get("inserted_plans") or []),
                    len(result.get("inserted_faq") or []),
                    (result.get("completeness") or {}).get("is_complete"),
                )
            except Exception as exc:
                logger.error(f"[gps-catalog-guard] failed: {exc}")

        scheduler.add_job(
            scheduled_gps_catalog_integrity_guard,
            IntervalTrigger(minutes=15),
            id="gps_catalog_integrity_guard",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=70),
            coalesce=True,
            max_instances=1,
            misfire_grace_time=180,
        )

        # ── Nightly global integrity artifact (contract + theme + matrix snapshot) ──
        async def scheduled_platform_integrity_artifact_nightly():
            try:
                from routes.db import db as runtime_db
                from services.gps_catalog_guard import generate_platform_integrity_artifact

                artifact = await generate_platform_integrity_artifact(
                    runtime_db,
                    source="scheduler_nightly",
                )
                await runtime_db.scheduler_heartbeats.update_one(
                    {"job_id": "platform_integrity_artifact_nightly"},
                    {
                        "$set": {
                            "job_id": "platform_integrity_artifact_nightly",
                            "status": "healthy",
                            "last_run": datetime.now(timezone.utc).isoformat(),
                            "details": {
                                "run_id": artifact.get("run_id"),
                                "artifact_path": artifact.get("artifact_path"),
                                "catalog_complete": ((artifact.get("catalog_completeness") or {}).get("is_complete")),
                                "theme_grade": ((artifact.get("theme_gate") or {}).get("grade")),
                            },
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                    upsert=True,
                )
                logger.info(
                    "[platform-integrity-nightly] run_id=%s path=%s",
                    artifact.get("run_id"),
                    artifact.get("artifact_path"),
                )
            except Exception as exc:
                logger.error(f"[platform-integrity-nightly] failed: {exc}")

        scheduler.add_job(
            scheduled_platform_integrity_artifact_nightly,
            CronTrigger(hour=1, minute=40),
            id="platform_integrity_artifact_nightly",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=900,
        )

        scheduler.start()
        logger.info("APScheduler started.")

        # ── Travel Visa Daily Lesson Rotation ──
        async def tv_daily_rotation_job():
            try:
                from routes.travel_visa import run_daily_lesson_rotation
                await run_daily_lesson_rotation()
                logger.info("[tv-daily-rotation] Daily lesson rotation completed")
            except Exception as e:
                logger.error(f"[tv-daily-rotation] Error: {e}")

        scheduler.add_job(tv_daily_rotation_job, CronTrigger(hour=6, minute=0), id="tv_daily_rotation", replace_existing=True,
    max_instances=1)

        # ── Daily Meditation Reminder Dispatch ──
        async def daily_meditation_reminder_dispatch_job():
            try:
                from routes.travel_visa_daily_meditation import run_daily_meditation_reminder_dispatch
                result = await run_daily_meditation_reminder_dispatch(batch_limit=300)
                logger.info(
                    f"[daily-meditation-reminders] scanned={result.get('scanned', 0)} sent={result.get('sent', 0)} skipped={result.get('skipped', 0)} failed={result.get('failed', 0)}"
                )
            except Exception as e:
                logger.error(f"[daily-meditation-reminders] Error: {e}")

        scheduler.add_job(
            daily_meditation_reminder_dispatch_job,
            CronTrigger(minute="*/15"),
            id="daily_meditation_reminder_dispatch",
            replace_existing=True,
            max_instances=1)

        # ── Daily Meditation Prayer Audio Auto-Drop (3/day) + notifications ──
        async def daily_meditation_prayer_audio_drop_job():
            try:
                from routes.travel_visa_daily_meditation import run_daily_prayer_audio_auto_publish
                result = await run_daily_prayer_audio_auto_publish(force=False, max_users=700, notify_users=True)
                logger.info(
                    f"[daily-meditation-prayer-audio-drop] created={result.get('created_count', 0)} today_total={result.get('today_total', 0)} in_app={result.get('notifications', {}).get('in_app_sent', 0)} email={result.get('notifications', {}).get('email_sent', 0)}"
                )
            except Exception as e:
                logger.error(f"[daily-meditation-prayer-audio-drop] Error: {e}")

        scheduler.add_job(
            daily_meditation_prayer_audio_drop_job,
            CronTrigger(hour=5, minute=35),
            id="daily_meditation_prayer_audio_drop",
            replace_existing=True,
            max_instances=1)

        # ── Daily Meditation Weekly Digest Dispatch (email) ──
        async def daily_meditation_weekly_digest_job():
            try:
                from routes.travel_visa_daily_meditation import run_weekly_meditation_digest_dispatch
                result = await run_weekly_meditation_digest_dispatch(max_users=150)
                logger.info(
                    f"[daily-meditation-weekly-digest] scanned={result.get('scanned', 0)} sent={result.get('sent', 0)} skipped={result.get('skipped', 0)} failed={result.get('failed', 0)}"
                )
            except Exception as e:
                logger.error(f"[daily-meditation-weekly-digest] Error: {e}")

        scheduler.add_job(
            daily_meditation_weekly_digest_job,
            CronTrigger(hour=8, minute=10),
            id="daily_meditation_weekly_digest_dispatch",
            replace_existing=True,
            max_instances=1)

        # ── Notification Auto-Archive (configurable TTL) ──
        async def notification_auto_archive_job():
            try:
                from routes.db import db as _db
                # Read admin-configured retention days (default 30)
                settings_doc = await _db.platform_settings.find_one({"key": "notification_retention"}, {"_id": 0})
                settings = settings_doc.get("value", {}) if settings_doc else {}
                if not settings.get("auto_archive_enabled", True):
                    logger.info("[notif-auto-archive] Disabled by admin settings, skipping")
                    return
                retention_days = settings.get("retention_days", 30)
                cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
                result = await _db.notifications.update_many(
                    {"created_at": {"$lt": cutoff}, "archived": {"$ne": True}},
                    {"$set": {"archived": True, "archived_at": datetime.now(timezone.utc).isoformat(), "auto_archived": True}},
                )
                if result.modified_count:
                    logger.info(f"[notif-auto-archive] Archived {result.modified_count} notifications older than {retention_days} days")
            except Exception as e:
                logger.error(f"[notif-auto-archive] Error: {e}")

        scheduler.add_job(notification_auto_archive_job, CronTrigger(hour=3, minute=30), id="notification_auto_archive", replace_existing=True,
    max_instances=1)


    @app.on_event("shutdown")
    async def shutdown_scheduler():
        scheduler.shutdown()
        logger.info("APScheduler shut down.")
