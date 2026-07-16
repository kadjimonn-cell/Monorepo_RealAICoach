"""
scheduler_jobs.sso_auth_health — SSO + multi-region auth health scheduled jobs.

**Phase 2 incremental domain split — batch #9.**

Owns the recurring auth-surface health monitoring: SSO redirect
sync/drift sentinels, provider-registration alignment, E2E validation
alerts, multi-region auth probes, fallback-link guardian, and the
admin E2E health gate.

Jobs in this module
===================
- ``scheduled_sso_redirect_auto_sync``
- ``scheduled_sso_provider_registration_alignment_auto``
- ``scheduled_sso_e2e_validation_alerts``
- ``scheduled_sso_redirect_drift_sentinel``
- ``scheduled_multi_region_auth_probe``
- ``scheduled_auth_fallback_link_guardian``
- ``scheduled_admin_e2e_health_gate``

All function bodies are byte-identical to the originals in `_legacy.py`
— this is a pure relocation, not a rewrite. The facade re-export
guarantees `from scheduler_jobs import scheduled_X` keeps working for
all existing call sites in `scheduler.py`.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone


from scheduler_jobs.observability import _record_scheduler_heartbeat


logger = logging.getLogger("scheduler_jobs.sso_auth_health")


async def scheduled_sso_redirect_auto_sync():
    """Persist SSO redirect base periodically so forked environments inherit callback base automatically."""
    try:
        from routes.db import db

        def _norm_base(raw: str) -> str:
            val = str(raw or "").strip().rstrip("/")
            if not val:
                return ""
            if not (val.startswith("https://") or val.startswith("http://")):
                val = f"https://{val}"
            return val.rstrip("/")

        def _parse_csv_bases(raw: str) -> list[str]:
            out: list[str] = []
            seen: set[str] = set()
            for item in str(raw or "").split(","):
                base = _norm_base(item)
                if not base or base in seen:
                    continue
                seen.add(base)
                out.append(base)
            return out

        def _is_preview_host(base: str) -> bool:
            host = ""
            try:
                host = base.split("//", 1)[1].split("/", 1)[0].lower().strip()
            except Exception:
                host = ""
            return host.endswith("preview.emergentagent.com")

        def _env_bool_local(key: str, default: bool = False) -> bool:
            raw = str(os.environ.get(key, "") or "").strip().lower()
            if not raw:
                return default
            return raw in {"1", "true", "yes", "on", "enabled"}

        base = (
            os.environ.get("SSO_CANONICAL_REDIRECT_BASE")
            or os.environ.get("SSO_REDIRECT_BASE_URL")
            or os.environ.get("FRONTEND_BASE_URL")
            or ""
        ).strip().rstrip("/")
        if not base:
            logger.warning("SSO redirect auto-sync skipped: no canonical SSO redirect base configured")
            return

        existing = await db.system_runtime_flags.find_one({"key": "sso_redirect_base"}, {"_id": 0}) or {}
        existing_base = str(existing.get("base") or "").strip().rstrip("/")
        existing_source = str(existing.get("source") or "")

        target_base = base
        source = "scheduler_auto_sync"

        # Preserve runtime-derived callback bases to avoid thrashing after fork/domain transitions.
        if existing_base and existing_base != base and existing_source in {"request_auto_sync", "fork_auto_sync"}:
            target_base = existing_base
            source = "scheduler_runtime_base_preserved"

        now_iso = datetime.now(timezone.utc).isoformat()
        await db.system_runtime_flags.update_one(
            {"key": "sso_redirect_base"},
            {
                "$set": {
                    "key": "sso_redirect_base",
                    "base": target_base,
                    "updated_at": now_iso,
                    "source": source,
                }
            },
            upsert=True,
        )
        await db.system_runtime_flags.update_one(
            {"key": "sso_redirect_auto_sync_meta"},
            {
                "$set": {
                    "key": "sso_redirect_auto_sync_meta",
                    "last_synced_at": now_iso,
                    "active_base": target_base,
                    "configured_base": base,
                    "source": source,
                }
            },
            upsert=True,
        )

        # Apple auto-sync: in preview environments prefer current preview base when registered;
        # otherwise use provider-verified base, then stable non-preview fallback.
        apple_verified_bases = _parse_csv_bases(os.environ.get("APPLE_SSO_PROVIDER_VERIFIED_REDIRECT_BASES") or "")
        apple_registered_bases = _parse_csv_bases(os.environ.get("APPLE_SSO_REGISTERED_REDIRECT_URIS") or "")
        apple_candidates: list[str] = []
        apple_source = "scheduler_apple_provider_verified_auto_sync"

        if (
            _env_bool_local("APPLE_SSO_AUTO_SYNC_USE_DYNAMIC_PREVIEW", False)
            and target_base
            and _is_preview_host(target_base)
            and target_base in apple_registered_bases
        ):
            apple_candidates.append(target_base)
            apple_source = "scheduler_apple_preview_registered_auto_sync"

        apple_candidates.extend(apple_verified_bases)
        if not apple_candidates:
            non_preview = [base for base in apple_registered_bases if not _is_preview_host(base)]
            apple_candidates = non_preview or apple_registered_bases
            if apple_candidates:
                apple_source = "scheduler_apple_registered_fallback_auto_sync"

        # De-duplicate while preserving priority order.
        deduped_apple_candidates: list[str] = []
        seen_apple: set[str] = set()
        for base in apple_candidates:
            if not base or base in seen_apple:
                continue
            seen_apple.add(base)
            deduped_apple_candidates.append(base)

        if deduped_apple_candidates:
            apple_target = deduped_apple_candidates[0]
            await db.system_runtime_flags.update_one(
                {"key": "sso_redirect_override_apple"},
                {
                    "$set": {
                        "key": "sso_redirect_override_apple",
                        "base": apple_target,
                        "updated_at": now_iso,
                        "source": apple_source,
                        "candidates": deduped_apple_candidates,
                    }
                },
                upsert=True,
            )
            logger.info(
                "SSO redirect auto-sync: apple provider override persisted -> %s (candidates=%s)",
                apple_target,
                ",".join(deduped_apple_candidates),
            )

        logger.info(f"SSO redirect auto-sync: active base persisted -> {target_base} (configured={base})")
    except Exception as e:
        logger.error(f"SSO redirect auto-sync failed: {e}")


async def scheduled_sso_provider_registration_alignment_auto():
    """Attempt provider registration alignment automatically (Microsoft via Graph, Apple guidance-only)."""
    job_id = "sso_provider_registration_alignment_auto"
    try:
        from routes.auth import _run_sso_provider_registration_alignment

        result = await _run_sso_provider_registration_alignment(
            request=None,
            updated_by="scheduler",
            trigger="scheduler_auto",
        )
        ms = result.get("microsoft") if isinstance(result, dict) else {}
        aligned = bool(isinstance(ms, dict) and ms.get("aligned"))
        status = "healthy" if aligned else "warning"
        detail = (
            f"ok={bool(result.get('ok')) if isinstance(result, dict) else False} "
            f"ms_aligned={aligned}"
        )
        await _record_scheduler_heartbeat(job_id, status, detail)
    except Exception as e:
        logger.error(f"SSO provider registration auto-alignment failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_sso_e2e_validation_alerts():
    """Run SSO E2E validation every 15 min and alert only on pass/fail state transitions."""
    job_id = "sso_e2e_validation_auto"
    try:
        from routes.db import db
        from routes.auth import run_sso_e2e_validation_internal

        result = await run_sso_e2e_validation_internal(None)
        passed = bool(result.get("passed"))
        state = "pass" if passed else "fail"
        now_iso = datetime.now(timezone.utc).isoformat()

        key = "sso_e2e_validation_state"
        prev = await db.system_runtime_flags.find_one({"key": key}, {"_id": 0}) or {}
        prev_state = str(prev.get("state") or "")
        changed = bool(prev_state) and prev_state != state

        first_failed_at = str(prev.get("first_failed_at") or "")
        incident_ticket_id = str(prev.get("incident_ticket_id") or "")
        incident_open = bool(prev.get("incident_open"))
        fail_duration_minutes = 0

        if state == "fail":
            if prev_state != "fail" or not first_failed_at:
                first_failed_at = now_iso

            try:
                started = datetime.fromisoformat(first_failed_at.replace("Z", "+00:00"))
                fail_duration_minutes = max(0, int((datetime.now(timezone.utc) - started).total_seconds() // 60))
            except Exception:
                fail_duration_minutes = 0

            if fail_duration_minutes >= 30 and not incident_open:
                submission_id = f"sso_inc_{uuid.uuid4().hex[:12]}"
                ticket_number = f"INC-SSO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
                await db.support_submissions.insert_one(
                    {
                        "submission_id": submission_id,
                        "ticket_number": ticket_number,
                        "user_id": "system",
                        "user_email": "system@realaicoach.local",
                        "user_name": "Safe Auto Validation Engine",
                        "subject": "SSO E2E persistent failure (>30m)",
                        "message": "Microsoft/Apple SSO E2E validation has remained in FAIL state for over 30 minutes. Auto incident opened.",
                        "category": "security",
                        "priority": "high",
                        "status": "open",
                        "assigned_to": "operations",
                        "attachments": [],
                        "reply_logs": [],
                        "auto_generated": True,
                        "source": "sso_e2e_validation_auto",
                        "history": [
                            {
                                "action": "auto_created",
                                "note": "Created due to persistent SSO E2E failure >30m",
                                "by": "system",
                                "by_name": "Safe Auto Validation Engine",
                                "at": now_iso,
                            }
                        ],
                        "metadata": {
                            "first_failed_at": first_failed_at,
                            "fail_duration_minutes": fail_duration_minutes,
                            "active_base": result.get("active_base"),
                        },
                        "resolved_at": None,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    }
                )
                incident_open = True
                incident_ticket_id = submission_id

                try:
                    from routes.admin_push_notifications import emit_realtime_alert

                    await emit_realtime_alert(
                        alert_type="sso_e2e_incident_created",
                        severity="critical",
                        title="SSO Incident Auto-Created",
                        message=f"SSO validation stayed FAIL >30m. Incident {ticket_number} was created automatically.",
                    )
                except Exception:
                    pass

                admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(100)
                for adm in admins:
                    uid = str(adm.get("user_id") or "")
                    if not uid:
                        continue
                    await db.notifications.insert_one(
                        {
                            "id": f"sso_e2e_incident_created_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                            "user_id": uid,
                            "type": "sso_e2e_incident_created",
                            "title": "SSO Incident Auto-Created",
                            "message": f"Persistent SSO FAIL >30m. Incident {ticket_number} has been opened automatically.",
                            "read": False,
                            "created_at": now_iso,
                            "metadata": {
                                "incident_ticket_id": submission_id,
                                "ticket_number": ticket_number,
                                "fail_duration_minutes": fail_duration_minutes,
                            },
                        }
                    )

        if state == "pass":
            fail_duration_minutes = 0
            first_failed_at = ""
            if incident_open and incident_ticket_id:
                await db.support_submissions.update_one(
                    {"submission_id": incident_ticket_id, "status": {"$in": ["open", "pending"]}},
                    {
                        "$set": {
                            "status": "resolved",
                            "resolved_at": now_iso,
                            "updated_at": now_iso,
                        },
                        "$push": {
                            "history": {
                                "action": "auto_resolved",
                                "note": "Resolved automatically after SSO E2E validation recovered",
                                "by": "system",
                                "by_name": "Safe Auto Validation Engine",
                                "at": now_iso,
                            }
                        },
                    },
                )
                incident_open = False

        failed_checks = [c.get("name") for c in (result.get("checks") or []) if not c.get("passed")]

        await db.system_runtime_flags.update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "state": state,
                    "previous_state": prev_state or None,
                    "changed": changed,
                    "last_run_at": now_iso,
                    "first_failed_at": first_failed_at or None,
                    "fail_duration_minutes": fail_duration_minutes,
                    "incident_ticket_id": incident_ticket_id or None,
                    "incident_open": incident_open,
                    "active_base": result.get("active_base"),
                    "failed_checks": failed_checks,
                    "validation": {
                        "severity": result.get("severity"),
                        "callbacks": result.get("callbacks"),
                    },
                }
            },
            upsert=True,
        )

        if changed:
            from routes.admin_push_notifications import emit_realtime_alert

            severity = "warning" if state == "fail" else "info"
            title = "SSO E2E state changed"
            if state == "fail":
                message = f"Microsoft/Apple SSO validation changed PASS → FAIL. Failed checks: {', '.join(failed_checks) if failed_checks else 'unknown'}."
            else:
                message = "Microsoft/Apple SSO validation recovered FAIL → PASS."

            await emit_realtime_alert(
                alert_type="sso_e2e_state_change",
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
                        "id": f"sso_e2e_state_change_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": uid,
                        "type": "sso_e2e_state_change",
                        "title": title,
                        "message": message,
                        "read": False,
                        "created_at": now_iso,
                        "metadata": {
                            "state": state,
                            "previous_state": prev_state,
                            "failed_checks": failed_checks,
                            "active_base": result.get("active_base"),
                            "incident_ticket_id": incident_ticket_id or None,
                            "fail_duration_minutes": fail_duration_minutes,
                        },
                    }
                )

        await _record_scheduler_heartbeat(
            job_id,
            "healthy" if passed else "warning",
            f"state={state} changed={changed} failed_checks={','.join(failed_checks) if failed_checks else 'none'}",
        )

    except Exception as e:
        logger.error(f"SSO E2E scheduled validation failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_sso_redirect_drift_sentinel():
    """Detect callback-host drift and emit immediate admin alerts on state transitions."""
    job_id = "sso_redirect_drift_sentinel"
    try:
        from routes.db import db
        from routes.auth import _build_sso_redirect_drift_snapshot
        from routes.admin_push_notifications import emit_realtime_alert

        snapshot = await _build_sso_redirect_drift_snapshot(None)
        state = "drift" if snapshot.get("drift_detected") else "healthy"
        now_iso = datetime.now(timezone.utc).isoformat()

        key = "sso_redirect_drift_sentinel_state"
        prev = await db.system_runtime_flags.find_one({"key": key}, {"_id": 0}) or {}
        prev_state = str(prev.get("state") or "")
        changed = bool(prev_state) and prev_state != state

        await db.system_runtime_flags.update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "state": state,
                    "previous_state": prev_state or None,
                    "changed": changed,
                    "last_run_at": now_iso,
                    "last_changed_at": now_iso if changed else prev.get("last_changed_at"),
                    "snapshot": snapshot,
                }
            },
            upsert=True,
        )

        should_alert = state == "drift" and (changed or not prev_state)
        if should_alert:
            providers = snapshot.get("drift_providers") or []
            message = (
                "SSO Redirect Drift Sentinel detected callback divergence "
                f"for providers: {', '.join(providers) if providers else 'unknown'}."
            )
            await emit_realtime_alert(
                alert_type="sso_redirect_drift_sentinel",
                severity="critical",
                title="SSO Redirect Drift Detected",
                message=message,
            )

            admins = await db.users.find({"is_admin": True}, {"_id": 0, "user_id": 1}).to_list(100)
            for adm in admins:
                uid = str(adm.get("user_id") or "")
                if not uid:
                    continue
                await db.notifications.insert_one(
                    {
                        "id": f"sso_redirect_drift_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": uid,
                        "type": "sso_redirect_drift_sentinel",
                        "title": "SSO Redirect Drift Detected",
                        "message": message,
                        "read": False,
                        "created_at": now_iso,
                        "metadata": {
                            "state": state,
                            "providers": providers,
                            "active_base": snapshot.get("active_base"),
                        },
                    }
                )

        await _record_scheduler_heartbeat(
            job_id,
            "warning" if state == "drift" else "healthy",
            f"state={state} providers={','.join(snapshot.get('drift_providers') or []) or 'none'}",
        )
    except Exception as e:
        logger.error(f"SSO Redirect Drift Sentinel failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_multi_region_auth_probe():
    """Synthetic auth probes across configured regions + route-level SLO alerting."""
    job_id = "multi_region_auth_probe"
    try:
        import httpx
        from routes.db import db
        from routes.admin_push_notifications import emit_realtime_alert

        base_url = (os.environ.get("FRONTEND_BASE_URL") or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("FRONTEND_BASE_URL missing")

        regions_raw = str(os.environ.get("AUTH_PROBE_REGIONS") or "us-east,eu-west,ap-south").strip()
        regions = [r.strip() for r in regions_raw.split(",") if r.strip()]
        if not regions:
            regions = ["us-east", "eu-west", "ap-south"]

        route_thresholds = {
            "health": float(os.environ.get("AUTH_SLO_HEALTH_P95_MS") or 800),
            "microsoft_init": float(os.environ.get("AUTH_SLO_MICROSOFT_INIT_P95_MS") or 1500),
            "apple_init": float(os.environ.get("AUTH_SLO_APPLE_INIT_P95_MS") or 1500),
            "sso_config": float(os.environ.get("AUTH_SLO_SSO_CONFIG_P95_MS") or 1200),
        }

        targets = [
            ("health", "/api/health"),
            ("microsoft_init", "/api/auth/microsoft/init"),
            ("apple_init", "/api/auth/apple/init"),
            ("sso_config", "/api/auth/sso-config"),
        ]

        measurements = []
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            for region in regions:
                for route_name, path in targets:
                    started = datetime.now(timezone.utc)
                    t0 = started.timestamp()
                    resp = await client.get(
                        f"{base_url}{path}",
                        headers={"X-Synthetic-Region": region, "X-Auth-Probe": "1"},
                    )
                    latency_ms = (datetime.now(timezone.utc).timestamp() - t0) * 1000.0
                    measurements.append(
                        {
                            "region": region,
                            "route": route_name,
                            "path": path,
                            "status_code": resp.status_code,
                            "latency_ms": round(latency_ms, 2),
                            "ok": resp.status_code < 400,
                            "timestamp": started.isoformat(),
                        }
                    )

        route_summary = {}
        slo_violations = []
        for route_name, _ in targets:
            rows = [m for m in measurements if m["route"] == route_name]
            if not rows:
                continue
            latencies = sorted(float(r["latency_ms"]) for r in rows)
            idx = max(0, min(len(latencies) - 1, int(round(0.95 * len(latencies) + 0.5)) - 1))
            p95 = latencies[idx]
            availability = round((sum(1 for r in rows if r["ok"]) / max(1, len(rows))) * 100, 2)
            threshold = float(route_thresholds.get(route_name, 1500))
            route_summary[route_name] = {
                "p95_ms": round(p95, 2),
                "availability_pct": availability,
                "threshold_ms": threshold,
            }
            if p95 > threshold or availability < 99.0:
                slo_violations.append(
                    {
                        "route": route_name,
                        "p95_ms": round(p95, 2),
                        "threshold_ms": threshold,
                        "availability_pct": availability,
                    }
                )

        key = "multi_region_auth_probe_state"
        prev = await db.system_runtime_flags.find_one({"key": key}, {"_id": 0}) or {}
        prev_streaks = dict(prev.get("route_failure_streaks") or {})

        route_failure_streaks = {}
        for route_name, _ in targets:
            route_failed = any(v.get("route") == route_name for v in slo_violations)
            route_failure_streaks[route_name] = int(prev_streaks.get(route_name, 0)) + 1 if route_failed else 0

        persistent_violations = [
            v for v in slo_violations if int(route_failure_streaks.get(v.get("route"), 0)) >= 2
        ]

        status = "fail" if persistent_violations else "pass"
        now_iso = datetime.now(timezone.utc).isoformat()

        run_doc = {
            "ran_at": now_iso,
            "base_url": base_url,
            "regions": regions,
            "status": status,
            "route_summary": route_summary,
            "slo_violations": slo_violations,
            "persistent_slo_violations": persistent_violations,
            "route_failure_streaks": route_failure_streaks,
            "measurements": measurements,
        }
        await db.multi_region_auth_probe_runs.insert_one(run_doc)

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
                    "base_url": base_url,
                    "regions": regions,
                    "route_summary": route_summary,
                    "slo_violations": slo_violations,
                    "persistent_slo_violations": persistent_violations,
                    "route_failure_streaks": route_failure_streaks,
                }
            },
            upsert=True,
        )

        if changed:
            severity = "critical" if status == "fail" else "info"
            title = "Multi-region Auth Probe SLO"
            message = (
                "Route-level auth SLO changed PASS → FAIL. "
                + (", ".join(f"{v['route']} p95={v['p95_ms']}ms" for v in persistent_violations[:4]) or "Unknown violations")
                if status == "fail"
                else "Route-level auth SLO recovered FAIL → PASS."
            )
            await emit_realtime_alert(
                alert_type="multi_region_auth_probe_slo_state_change",
                severity=severity,
                title=title,
                message=message,
            )

        await _record_scheduler_heartbeat(
            job_id,
            "warning" if status == "fail" else "healthy",
            f"state={status} persistent_violations={len(persistent_violations)} regions={len(regions)}",
        )
    except Exception as e:
        logger.error(f"Multi-region auth probe failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_auth_fallback_link_guardian():
    """Monitor magic-link and QR link base freshness to prevent stale-login-link drift."""
    job_id = "auth_fallback_link_guardian"
    try:
        from routes.db import db
        from routes.auth import _resolve_auth_fallback_base
        from routes.admin_push_notifications import emit_realtime_alert

        active_base = await _resolve_auth_fallback_base(None)
        now = datetime.now(timezone.utc)
        since_iso = (now - timedelta(hours=48)).isoformat()

        stale_magic = await db.magic_links.count_documents({
            "created_at": {"$gte": since_iso},
            "auth_base": {"$exists": True, "$ne": active_base},
        })
        stale_qr = await db.qr_sessions.count_documents({
            "created_at": {"$gte": since_iso},
            "auth_base": {"$exists": True, "$ne": active_base},
        })

        status = "healthy" if active_base and (stale_magic + stale_qr) == 0 else "warning"
        now_iso = now.isoformat()

        key = "auth_fallback_link_guardian_state"
        prev = await db.system_runtime_flags.find_one({"key": key}, {"_id": 0}) or {}
        prev_status = str(prev.get("status") or "")
        changed = bool(prev_status) and prev_status != status

        payload = {
            "key": key,
            "status": status,
            "active_base": active_base,
            "stale_magic_count_48h": stale_magic,
            "stale_qr_count_48h": stale_qr,
            "updated_at": now_iso,
            "changed": changed,
            "previous_status": prev_status or None,
        }
        await db.system_runtime_flags.update_one({"key": key}, {"$set": payload}, upsert=True)

        if changed and status != "healthy":
            await emit_realtime_alert(
                alert_type="auth_fallback_link_guardian",
                severity="warning",
                title="Fallback Login Link Drift Risk",
                message=(
                    f"Detected stale fallback links (magic={stale_magic}, qr={stale_qr}) "
                    f"vs active base {active_base}."
                ),
            )

        await _record_scheduler_heartbeat(
            job_id,
            status,
            f"active_base={active_base} stale_magic={stale_magic} stale_qr={stale_qr}",
        )
    except Exception as e:
        logger.error(f"Auth fallback link guardian failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


async def scheduled_admin_e2e_health_gate():
    """Nightly admin E2E health gate with state-change notifications only."""
    job_id = "admin_e2e_health_gate"
    try:
        import httpx
        from routes.db import db
        from routes.admin_push_notifications import emit_realtime_alert

        base_url = (os.environ.get("FRONTEND_BASE_URL") or "http://localhost:3000").strip().rstrip("/")
        admin_email = os.environ.get("TEST_ADMIN_EMAIL", "")
        admin_password = os.environ.get("TEST_ADMIN_PASSWORD", "")

        checks = []

        async with httpx.AsyncClient(
            timeout=45.0, follow_redirects=True,
            headers={"X-Requested-With": "XMLHttpRequest"},
        ) as client:
            login = await client.post(
                f"{base_url}/api/auth/login",
                json={"email": admin_email, "password": admin_password},
            )
            login_ok = login.status_code == 200
            checks.append({"name": "admin_login", "ok": login_ok, "status_code": login.status_code})

            # Platform auth is cookie-session based (no bearer token in the login
            # response); the client cookie jar carries the session from here on.
            headers = {}
            endpoint_checks = [
                ("admin_overview", "/api/admin/overview"),
                ("cia_trust", "/api/admin/cia-trust/overview"),
                ("sso_validate", "/api/auth/admin/sso-validate-e2e", "POST"),
                ("gateway_config", "/api/subscriptions/gateway-config"),
                ("iap_matrix", "/api/iap/readiness-matrix"),
                ("live_notifications", "/api/admin/notifications/live"),
                ("route_health", "/api/admin/platform-perf/route-health"),
                ("route_integrity_checker", "/api/admin/platform-perf/route-integrity-checker"),
                ("admin_tab_integrity", "/api/admin/platform-perf/admin-tab-integrity"),
                ("theme_visibility_audit", "/api/admin/platform-perf/theme-visibility-audit"),
                ("navigation_lock_audit", "/api/admin/platform-perf/navigation-lock-audit"),
            ]

            for item in endpoint_checks:
                if len(item) == 3 and item[2] == "POST":
                    name, path, _ = item
                    resp = await client.post(f"{base_url}{path}", headers=headers, json={})
                else:
                    name, path = item[0], item[1]
                    resp = await client.get(f"{base_url}{path}", headers=headers)
                checks.append({"name": name, "ok": resp.status_code < 400, "status_code": resp.status_code})

                if name == "route_integrity_checker" and resp.status_code < 400:
                    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    checker_ok = str(payload.get("status") or "").lower() == "healthy"
                    checks.append({"name": "route_integrity_checker_healthy", "ok": checker_ok, "status_code": resp.status_code})

                if name == "admin_tab_integrity" and resp.status_code < 400:
                    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    status_ok = str(payload.get("status") or "").lower() == "healthy"
                    missing = payload.get("missing_tab_renderers") if isinstance(payload.get("missing_tab_renderers"), list) else []
                    checks.append({"name": "admin_tab_integrity_healthy", "ok": status_ok and len(missing) == 0, "status_code": resp.status_code})

                if name == "theme_visibility_audit" and resp.status_code < 400:
                    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    status_value = str(payload.get("status") or "").lower()
                    severity = payload.get("severity_summary") if isinstance(payload.get("severity_summary"), dict) else {}
                    critical_count = int(severity.get("critical") or 0)
                    legacy_ok = status_value in {"healthy", "warning"} and critical_count == 0
                    # Current schema: grade-based (overall_grade + summary.total_fail_issues)
                    summary_block = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
                    grade_ok = (
                        str(payload.get("overall_grade") or "").upper() in {"A", "B"}
                        and int(summary_block.get("total_fail_issues") or 0) == 0
                    )
                    checks.append({"name": "theme_visibility_audit_healthy", "ok": legacy_ok or grade_ok, "status_code": resp.status_code})

                if name == "navigation_lock_audit" and resp.status_code < 400:
                    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    status_ok = str(payload.get("status") or "").lower() == "healthy"
                    checks.append({"name": "navigation_lock_audit_healthy", "ok": status_ok, "status_code": resp.status_code})

                if name == "route_health" and resp.status_code < 400:
                    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
                    route_integrity_ok = str(summary.get("route_integrity_checker_status") or "").lower() == "healthy"
                    protected_integrity_ok = float(summary.get("protected_integrity_pct") or 0) >= 95
                    checks.append({"name": "route_health_integrity_gate", "ok": route_integrity_ok and protected_integrity_ok, "status_code": resp.status_code})

        passed = all(c.get("ok") for c in checks)
        status = "pass" if passed else "fail"
        failed_checks = [c.get("name") for c in checks if not c.get("ok")]
        now_iso = datetime.now(timezone.utc).isoformat()

        await db.admin_e2e_health_gate_runs.insert_one(
            {
                "ran_at": now_iso,
                "status": status,
                "checks": checks,
                "failed_checks": failed_checks,
                "base_url": base_url,
            }
        )

        key = "admin_e2e_health_gate_state"
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
                    "base_url": base_url,
                }
            },
            upsert=True,
        )

        if changed:
            severity = "critical" if status == "fail" else "info"
            title = "Nightly Admin E2E Health Gate"
            message = (
                f"Admin E2E health gate changed PASS → FAIL. Failed checks: {', '.join(failed_checks) if failed_checks else 'unknown'}."
                if status == "fail"
                else "Admin E2E health gate recovered FAIL → PASS."
            )

            await emit_realtime_alert(
                alert_type="admin_e2e_health_gate_state_change",
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
                        "id": f"admin_e2e_health_gate_{uid}_{int(datetime.now(timezone.utc).timestamp())}",
                        "user_id": uid,
                        "type": "admin_e2e_health_gate_state_change",
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
        logger.error(f"Nightly admin E2E health gate failed: {e}")
        await _record_scheduler_heartbeat(job_id, "error", str(e))


__all__ = [
    "scheduled_sso_redirect_auto_sync",
    "scheduled_sso_provider_registration_alignment_auto",
    "scheduled_sso_e2e_validation_alerts",
    "scheduled_sso_redirect_drift_sentinel",
    "scheduled_multi_region_auth_probe",
    "scheduled_auth_fallback_link_guardian",
    "scheduled_admin_e2e_health_gate",
]


async def scheduled_cia_trust_heartbeat():
    """Hourly: persist the computed CIA trust score so the Production Security
    Policy Gate (cia_trust_score check) has a fresh heartbeat to evaluate."""
    job_id = "cia_trust_heartbeat"
    try:
        from routes.db import db
        from routes.cia_trust import _compute_cia_overview

        overview = await _compute_cia_overview()
        now_iso = datetime.now(timezone.utc).isoformat()
        trust_score = overview.get("trust_score")
        cia = overview.get("cia") or {}
        engine = overview.get("ai_security_engine") or {}
        await db.cia_trust_heartbeat.insert_one({
            "captured_at": now_iso,
            "trust_score": trust_score,
            "threat_level": engine.get("threat_level"),
            "confidentiality": (cia.get("confidentiality") or {}).get("score"),
            "integrity": (cia.get("integrity") or {}).get("score"),
            "availability": (cia.get("availability") or {}).get("score"),
            "source": "scheduler",
        })
        await db.cia_trust_history.insert_one({
            "captured_at": now_iso,
            "trust_score": trust_score,
        })
        await _record_scheduler_heartbeat(job_id, "ok", f"trust_score={trust_score}")
        return {"status": "ok", "trust_score": trust_score, "captured_at": now_iso}
    except Exception as e:
        await _record_scheduler_heartbeat(job_id, "error", str(e))
        return {"status": "error", "error": str(e)}
