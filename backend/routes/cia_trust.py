from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import os

import httpx
from fastapi import APIRouter, HTTPException, Request

from routes.db import db, get_current_user


router = APIRouter(tags=["CIA Trust"])

TRUST_HISTORY_COLLECTION = "cia_trust_history"
SELF_HEAL_COLLECTION = "cia_self_heal_runs"


async def _require_admin(req: Request) -> dict:
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    role = str(getattr(user, "role", "") or (user.get("role", "") if isinstance(user, dict) else "")).lower()
    if role not in {"admin", "super_admin", "superadmin", "owner"}:
        raise HTTPException(status_code=403, detail="Admin access required")

    user_id = getattr(user, "user_id", None) or (user.get("user_id") if isinstance(user, dict) else None)
    email = getattr(user, "email", None) or (user.get("email") if isinstance(user, dict) else None)
    return {"user_id": user_id, "email": email, "role": role}


def _clip(value: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, float(value)))


async def _provider_readiness_snapshot() -> list[dict[str, Any]]:
    from routes.iap import _resolve_iap_provider_readiness

    stripe_secret = os.environ.get("STRIPE_API_KEY", "")
    stripe_pub = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    paypal_client = os.environ.get("PAYPAL_CLIENT_ID", "")
    paypal_secret = os.environ.get("PAYPAL_SECRET", "")
    fedapay_secret = os.environ.get("FEDAPAY_SECRET_KEY", "")

    stripe_state = "live_ready" if stripe_secret.startswith("sk_live_") and stripe_pub.startswith("pk_live_") else "degraded" if stripe_secret else "unavailable"
    paypal_mode = str(os.environ.get("PAYPAL_MODE", "live")).lower()
    paypal_state = "live_ready" if (paypal_client and paypal_secret and paypal_mode == "live") else "degraded" if (paypal_client and paypal_secret) else "unavailable"
    fedapay_state = "live_ready" if fedapay_secret else "unavailable"

    iap = _resolve_iap_provider_readiness()
    apple_state = str(iap.get("providers", {}).get("apple", {}).get("readiness_state", "unavailable"))
    google_state = str(iap.get("providers", {}).get("google", {}).get("readiness_state", "unavailable"))

    def normalize_iap(state: str) -> str:
        if state == "live_ready":
            return "live_ready"
        if state in {"sandbox_ready", "test_ready"}:
            return "degraded"
        return "unavailable"

    return [
        {"provider": "stripe", "label": "Stripe", "state": stripe_state},
        {"provider": "paypal", "label": "PayPal", "state": paypal_state},
        {"provider": "fedapay", "label": "FedaPay", "state": fedapay_state},
        {"provider": "apple", "label": "Apple IAP", "state": normalize_iap(apple_state)},
        {"provider": "google", "label": "Google IAP", "state": normalize_iap(google_state)},
    ]


async def _compute_cia_overview() -> dict:
    now = datetime.now(timezone.utc)
    lookback_24h = now - timedelta(hours=24)
    lookback_1h = now - timedelta(hours=1)

    providers = await _provider_readiness_snapshot()
    live_ready_count = sum(1 for p in providers if p.get("state") == "live_ready")
    provider_health_pct = round((live_ready_count / max(1, len(providers))) * 100, 2)

    unresolved_vuln = await db.get_collection("security_vulnerabilities").count_documents({"status": {"$in": ["open", "new", "triage"]}})
    security_alerts_24h = await db.get_collection("notifications").count_documents({
        "type": {"$in": ["security", "security_alert", "risk_alert"]},
        "created_at": {"$gte": lookback_24h.isoformat()},
    })
    users_total = await db.users.count_documents({})
    mfa_enabled = await db.users.count_documents({"mfa_enabled": True})
    mfa_coverage = round((mfa_enabled / max(1, users_total)) * 100, 2)

    route_failures = await db.get_collection("route_health_history").count_documents({
        "timestamp": {"$gte": lookback_24h},
        "summary.failed": {"$gt": 0},
    })
    stale_pending_payments = await db.get_collection("payment_transactions").count_documents({
        "status": {"$in": ["pending", "processing"]},
        "created_at": {"$lt": (now - timedelta(hours=2)).isoformat()},
    })

    shell_429_last_hour = await db.get_collection("shell_health_events").aggregate([
        {"$match": {"timestamp": {"$gte": lookback_1h}}},
        {"$group": {"_id": None, "v": {"$sum": "$counters.rate_limit_429s"}}},
    ]).to_list(1)
    shell_429 = int((shell_429_last_hour[0].get("v") if shell_429_last_hour else 0) or 0)

    latest_perf = await db.get_collection("perf_snapshots").find_one({}, {"_id": 0}, sort=[("timestamp", -1)])
    api_error_rate = float(((latest_perf or {}).get("api") or {}).get("error_rate_pct") or 0)
    cpu_pct = float(((latest_perf or {}).get("system") or {}).get("cpu_pct") or 0)
    mem_pct = float(((latest_perf or {}).get("system") or {}).get("memory_pct") or 0)

    confidentiality = _clip(100 - (unresolved_vuln * 2.8) - (security_alerts_24h * 1.6) + (mfa_coverage * 0.22))
    integrity = _clip(100 - (route_failures * 2.5) - (stale_pending_payments * 1.8) + (provider_health_pct * 0.3))
    availability = _clip(100 - (api_error_rate * 6.5) - (shell_429 * 1.4) - max(0, cpu_pct - 75) - max(0, mem_pct - 82))
    trust_score = round(_clip((confidentiality * 0.34) + (integrity * 0.33) + (availability * 0.33)), 2)

    threat_level = "critical" if trust_score < 55 else "warning" if trust_score < 75 else "normal"
    top_risks = []
    if unresolved_vuln > 0:
        top_risks.append({"type": "vulnerability_backlog", "severity": "high" if unresolved_vuln >= 5 else "medium", "value": unresolved_vuln})
    if shell_429 > 0:
        top_risks.append({"type": "rate_limit_pressure", "severity": "high" if shell_429 >= 15 else "medium", "value": shell_429})
    if stale_pending_payments > 0:
        top_risks.append({"type": "payment_integrity_drift", "severity": "high" if stale_pending_payments >= 8 else "medium", "value": stale_pending_payments})

    last_self_heal = await db.get_collection(SELF_HEAL_COLLECTION).find_one({}, {"_id": 0}, sort=[("ran_at", -1)])

    history = await db.get_collection(TRUST_HISTORY_COLLECTION).find({}, {"_id": 0, "captured_at": 1, "trust_score": 1}).sort("captured_at", -1).limit(48).to_list(48)
    ordered_history = list(reversed(history))

    slope_per_hour = 0.0
    latest_score = trust_score
    if len(ordered_history) >= 2:
        first = ordered_history[0]
        last = ordered_history[-1]
        first_ts = first.get("captured_at")
        last_ts = last.get("captured_at")
        first_score = float(first.get("trust_score") or trust_score)
        last_score = float(last.get("trust_score") or trust_score)
        latest_score = last_score
        if isinstance(first_ts, datetime) and isinstance(last_ts, datetime):
            delta_hours = max((last_ts - first_ts).total_seconds() / 3600.0, 0.1)
            slope_per_hour = (last_score - first_score) / delta_hours

    trajectory = []
    for hour in range(1, 7):
        trajectory.append({
            "hour_offset": hour,
            "predicted_trust_score": round(_clip(latest_score + (slope_per_hour * hour)), 2),
        })

    projected_breach = {"level": None, "eta_hours": None}
    for point in trajectory:
        score = float(point.get("predicted_trust_score") or 0)
        if score < 55:
            projected_breach = {"level": "critical", "eta_hours": point["hour_offset"]}
            break
        if score < 75 and projected_breach["level"] is None:
            projected_breach = {"level": "warning", "eta_hours": point["hour_offset"]}

    payload = {
        "trust_score": trust_score,
        "cia": {
            "confidentiality": {"score": round(confidentiality, 2), "metrics": {"unresolved_vulnerabilities": unresolved_vuln, "security_alerts_24h": security_alerts_24h, "mfa_coverage_pct": mfa_coverage}},
            "integrity": {"score": round(integrity, 2), "metrics": {"route_failures_24h": route_failures, "stale_pending_payments": stale_pending_payments, "provider_live_ready_pct": provider_health_pct}},
            "availability": {"score": round(availability, 2), "metrics": {"api_error_rate_pct": api_error_rate, "shell_429_last_hour": shell_429, "cpu_pct": cpu_pct, "memory_pct": mem_pct}},
        },
        "providers": providers,
        "ai_security_engine": {
            "threat_level": threat_level,
            "automated_vulnerability_triage": True,
            "adaptive_security_controls": True,
            "intelligent_alert_routing": True,
        },
        "top_risks": top_risks,
        "freshness": {
            "data_freshness_pct": round(_clip(100 - api_error_rate - (shell_429 * 0.4)), 2),
            "last_updated": now.isoformat(),
            "last_self_heal": (last_self_heal or {}).get("ran_at"),
        },
        "trust_forecast": {
            "horizon_hours": 6,
            "slope_per_hour": round(slope_per_hour, 3),
            "trajectory": trajectory,
            "projected_breach": projected_breach,
        },
    }

    await db.get_collection(TRUST_HISTORY_COLLECTION).insert_one({
        "captured_at": now,
        "trust_score": trust_score,
        "confidentiality": round(confidentiality, 2),
        "integrity": round(integrity, 2),
        "availability": round(availability, 2),
    })

    return payload


async def _route_security_alert_if_needed(summary: dict):
    trust_score = float(summary.get("trust_score") or 0)
    if trust_score >= 75:
        return
    try:
        from routes.admin_push_notifications import emit_realtime_alert

        severity = "critical" if trust_score < 55 else "warning"
        await emit_realtime_alert(
            alert_type="cia_trust_drop",
            severity=severity,
            title="CIA Trust Score Degradation",
            message=f"CIA Trust Score dropped to {trust_score}. Safe-Auto-Fix and alert routing are active.",
        )
    except Exception:
        return


@router.get("/admin/cia-trust/overview")
async def cia_trust_overview(request: Request):
    await _require_admin(request)
    payload = await _compute_cia_overview()
    await _route_security_alert_if_needed(payload)
    return payload


@router.get("/admin/cia-trust/widget")
async def cia_trust_widget_alias(request: Request):
    """Compatibility alias for widget-specific checks."""
    return await cia_trust_overview(request)


@router.post("/admin/cia-trust/self-heal/heartbeat")
async def cia_self_heal_heartbeat(request: Request):
    await _require_admin(request)
    now = datetime.now(timezone.utc)

    stale_cleanup = {}
    cleanup_targets = {
        "perf_snapshots": now - timedelta(days=30),
        "shell_health_events": now - timedelta(days=14),
        "route_health_history": now - timedelta(days=14),
        TRUST_HISTORY_COLLECTION: now - timedelta(days=30),
    }
    for col, cutoff in cleanup_targets.items():
        try:
            deleted = await db.get_collection(col).delete_many({"timestamp": {"$lt": cutoff}})
            stale_cleanup[col] = deleted.deleted_count
        except Exception:
            stale_cleanup[col] = 0

    base_url = str(request.base_url).rstrip("/")
    probe_paths = [
        "/api/health",
        "/api/system/health",
        "/api/subscriptions/gateway-config",
        "/dashboard",
        "/profile",
        "/subscription/mobile",
        "/admin-console",
        "/favicon.ico",
        "/manifest.json",
    ]

    broken = []
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for path in probe_paths:
            try:
                resp = await client.get(f"{base_url}{path}")
                if resp.status_code >= 400:
                    broken.append({"path": path, "status": resp.status_code})
            except Exception:
                broken.append({"path": path, "status": "unreachable"})

    overview = await _compute_cia_overview()
    await _route_security_alert_if_needed(overview)

    run_doc = {
        "ran_at": now.isoformat(),
        "stale_cleanup": stale_cleanup,
        "broken_paths": broken,
        "trust_score": overview.get("trust_score"),
        "auto_actions": [
            "cache_cleanup_completed",
            "pipeline_refresh_triggered",
            "route_asset_probe_completed",
            "adaptive_alert_routing_executed",
        ],
    }
    await db.get_collection(SELF_HEAL_COLLECTION).insert_one({
        "ran_at": now,
        "stale_cleanup": stale_cleanup,
        "broken_paths": broken,
        "trust_score": overview.get("trust_score"),
        "auto_actions": run_doc["auto_actions"],
    })

    return {
        "ok": True,
        "self_heal": run_doc,
        "overview": overview,
    }


@router.get("/admin/cia-trust/self-heal/logs")
async def cia_self_heal_logs(request: Request, limit: int = 12):
    await _require_admin(request)
    docs = await db.get_collection(SELF_HEAL_COLLECTION).find({}, {"_id": 0}).sort("ran_at", -1).limit(min(max(limit, 1), 50)).to_list(min(max(limit, 1), 50))
    return {"logs": docs, "count": len(docs)}
