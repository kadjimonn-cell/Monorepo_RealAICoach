"""Feature 34 reliability/release-gate routes (locked protocol)."""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routes.db import db, require_admin
from routes.integrations import _require_calendar_user, _assert_user_scope, calendar_observability as legacy_calendar_observability
from utils.access_control_engine import compute_effective_plan


router = APIRouter()


class ReleaseGateProfileUpdateRequest(BaseModel):
    profile: str


_RELIABILITY_PROFILES: Dict[str, Dict[str, float]] = {
    "strict": {
        "max_conflicts_30d": 4,
        "min_reminder_success_rate": 0.985,
        "max_error_rate_7d": 0.010,
        "min_booking_conversion_7d": 0.12,
    },
    "standard": {
        "max_conflicts_30d": 9,
        "min_reminder_success_rate": 0.95,
        "max_error_rate_7d": 0.03,
        "min_booking_conversion_7d": 0.08,
    },
    "lenient": {
        "max_conflicts_30d": 16,
        "min_reminder_success_rate": 0.90,
        "max_error_rate_7d": 0.06,
        "min_booking_conversion_7d": 0.04,
    },
}


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


async def _compute_user_reliability_snapshot(user_id: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    recent_events = (
        await db.calendar_events.find(
            {"user_id": user_id, "start": {"$gte": month_ago}},
            {"_id": 0, "start": 1, "end": 1, "updated_at": 1},
        )
        .sort("start", 1)
        .to_list(600)
    )

    conflict_count_30d = 0
    ranges = []
    for ev in recent_events:
        try:
            start_dt = datetime.fromisoformat(str(ev.get("start", "")).replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(str(ev.get("end", "")).replace("Z", "+00:00"))
            if end_dt <= start_dt:
                continue
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            ranges.append((start_dt, end_dt))
        except Exception:
            continue

    ranges.sort(key=lambda item: item[0])
    for idx in range(1, len(ranges)):
        if ranges[idx][0] < ranges[idx - 1][1]:
            conflict_count_30d += 1

    bookings_7d = await db.calendar_bookings.count_documents({"user_id": user_id, "created_at": {"$gte": week_ago}})
    booking_pages = await db.booking_pages.count_documents({"user_id": user_id, "active": True})

    funnel_views_7d = await db.calendar_booking_funnel_events.count_documents(
        {"user_id": user_id, "stage": "view", "created_at": {"$gte": week_ago}}
    )
    funnel_booked_7d = await db.calendar_booking_funnel_events.count_documents(
        {"user_id": user_id, "stage": "booked", "created_at": {"$gte": week_ago}}
    )

    reminder_logs_7d = (
        await db.email_logs.find(
            {
                "user_id": user_id,
                "sent_at": {"$gte": week_ago},
                "email_type": {"$regex": r"^booking_reminder_"},
            },
            {"_id": 0, "status": 1},
        ).to_list(1000)
    )
    reminder_sent = sum(1 for row in reminder_logs_7d if str(row.get("status") or "").lower() == "sent")
    reminder_total = len(reminder_logs_7d)
    reminder_success_rate = _safe_ratio(reminder_sent, reminder_total)

    incident_7d = await db.notifications.count_documents(
        {
            "user_id": user_id,
            "created_at": {"$gte": week_ago},
            "type": {"$in": ["booking_cancelled", "booking_cancelled_by_host"]},
        }
    )

    sync_rows_7d = await db.calendar_sync_telemetry.find(
        {"user_id": user_id, "created_at": {"$gte": week_ago}},
        {"_id": 0, "status": 1, "latency_ms": 1},
    ).to_list(500)
    sync_total = len(sync_rows_7d)
    sync_errors = sum(1 for row in sync_rows_7d if str(row.get("status") or "") != "success")
    sync_error_rate_7d = _safe_ratio(sync_errors, sync_total)
    sorted_latencies = sorted(
        [int(row.get("latency_ms") or 0) for row in sync_rows_7d if int(row.get("latency_ms") or 0) >= 0]
    )
    sync_latency_p95_ms = 0
    if sorted_latencies:
        idx = min(len(sorted_latencies) - 1, int(round(0.95 * (len(sorted_latencies) - 1))))
        sync_latency_p95_ms = int(sorted_latencies[idx])

    operation_volume_7d = max(1, bookings_7d + len(recent_events) + sync_total)
    error_rate_7d = _safe_ratio(incident_7d + sync_errors, operation_volume_7d)

    conversion_window = int(funnel_booked_7d)
    conversion_denominator = max(1, int(funnel_views_7d))
    if conversion_denominator <= 1 and conversion_window <= 1:
        conversion_denominator = max(1, booking_pages)
        conversion_window = int(bookings_7d)
    booking_conversion_7d = _safe_ratio(conversion_window, conversion_denominator)

    recent_events_14d = (
        await db.calendar_events.find(
            {"user_id": user_id, "start": {"$gte": (now - timedelta(days=14)).isoformat()}},
            {"_id": 0, "start": 1, "end": 1},
        )
        .sort("start", 1)
        .to_list(700)
    )
    current_conflicts_7d = 0
    previous_conflicts_7d = 0
    current_cut = now - timedelta(days=7)
    previous_cut = now - timedelta(days=14)
    recent_ranges = []
    for row in recent_events_14d:
        try:
            s = datetime.fromisoformat(str(row.get("start", "")).replace("Z", "+00:00"))
            e = datetime.fromisoformat(str(row.get("end", "")).replace("Z", "+00:00"))
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if e.tzinfo is None:
                e = e.replace(tzinfo=timezone.utc)
            if e <= s:
                continue
            recent_ranges.append((s, e))
        except Exception:
            continue
    recent_ranges.sort(key=lambda item: item[0])
    for idx in range(1, len(recent_ranges)):
        if recent_ranges[idx][0] < recent_ranges[idx - 1][1]:
            start_dt = recent_ranges[idx][0]
            if start_dt >= current_cut:
                current_conflicts_7d += 1
            elif previous_cut <= start_dt < current_cut:
                previous_conflicts_7d += 1

    sync_mode = "local"
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "google_calendar": 1,
            "subscription_plan": 1,
            "subscription_status": 1,
            "subscription_end_date": 1,
            "pending_subscription_transition": 1,
            "payment_verified": 1,
            "is_admin": 1,
        },
    )
    if user_doc and (user_doc.get("google_calendar") or {}).get("access_token"):
        sync_mode = "google_two_way"

    effective_plan = compute_effective_plan(user_doc or {})
    return {
        "user_id": user_id,
        "plan_scope": effective_plan,
        "sync_mode": sync_mode,
        "window": {"days_7": True, "days_30": True},
        "metrics": {
            "conflict_events_30d": int(conflict_count_30d),
            "conflicts_current_7d": int(current_conflicts_7d),
            "conflicts_previous_7d": int(previous_conflicts_7d),
            "bookings_7d": int(bookings_7d),
            "booking_pages_active": int(booking_pages),
            "booking_views_7d": int(funnel_views_7d),
            "bookings_confirmed_7d": int(funnel_booked_7d),
            "reminder_success_rate_7d": round(reminder_success_rate, 4),
            "error_rate_7d": round(error_rate_7d, 4),
            "booking_conversion_7d": round(booking_conversion_7d, 4),
            "sync_total_7d": int(sync_total),
            "sync_error_rate_7d": round(sync_error_rate_7d, 4),
            "sync_latency_p95_ms": int(sync_latency_p95_ms),
        },
    }


async def _get_active_release_gate_profile() -> str:
    doc = await db.platform_runtime_config.find_one(
        {"key": "feature34_release_gate_profile"},
        {"_id": 0, "value": 1},
    )
    value = str((doc or {}).get("value") or "").strip().lower()
    return value if value in _RELIABILITY_PROFILES else "standard"


async def _set_active_release_gate_profile(profile: str, actor_user_id: str) -> str:
    normalized = str(profile or "").strip().lower()
    if normalized not in _RELIABILITY_PROFILES:
        raise HTTPException(status_code=400, detail="Invalid profile. Use strict, standard, or lenient")
    await db.platform_runtime_config.update_one(
        {"key": "feature34_release_gate_profile"},
        {
            "$set": {
                "value": normalized,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": actor_user_id,
            }
        },
        upsert=True,
    )
    return normalized


def _evaluate_release_gate(profile: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    normalized = str(profile or "standard").strip().lower()
    thresholds = _RELIABILITY_PROFILES.get(normalized)
    if thresholds is None:
        raise HTTPException(status_code=400, detail="Invalid profile. Use strict, standard, or lenient")

    metrics = snapshot.get("metrics", {})
    checks = {
        "conflicts_ok": float(metrics.get("conflict_events_30d", 0)) <= float(thresholds["max_conflicts_30d"]),
        "reminders_ok": float(metrics.get("reminder_success_rate_7d", 0.0)) >= float(thresholds["min_reminder_success_rate"]),
        "error_rate_ok": float(metrics.get("error_rate_7d", 0.0)) <= float(thresholds["max_error_rate_7d"]),
        "conversion_ok": float(metrics.get("booking_conversion_7d", 0.0)) >= float(thresholds["min_booking_conversion_7d"]),
    }
    pass_gate = all(checks.values())
    failed_reasons = [name for name, ok in checks.items() if not ok]
    return {
        "profile": normalized,
        "thresholds": thresholds,
        "checks": checks,
        "pass": pass_gate,
        "decision": "go" if pass_gate else "no-go",
        "failed_reasons": failed_reasons,
    }


@router.get("/calendar/reliability/{user_id}")
async def calendar_reliability_snapshot(user_id: str, request: Request):
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)
    return await _compute_user_reliability_snapshot(user_id)


@router.get("/calendar/observability/{user_id}")
async def calendar_observability_compat_route(user_id: str, request: Request):
    base_payload = await legacy_calendar_observability(user_id, request)
    reliability = await _compute_user_reliability_snapshot(user_id)
    base_payload["reliability"] = reliability
    return base_payload


@router.get("/calendar/release-gate/{user_id}")
async def calendar_release_gate(user_id: str, request: Request, profile: Optional[str] = None):
    user = await _require_calendar_user(request)
    _assert_user_scope(user.user_id, user_id)
    selected_profile = str(profile or "").strip().lower() or await _get_active_release_gate_profile()
    snapshot = await _compute_user_reliability_snapshot(user_id)
    gate = _evaluate_release_gate(selected_profile, snapshot)
    return {
        "feature": "book-meeting",
        "user_id": user_id,
        "profile": gate["profile"],
        "snapshot": snapshot,
        "gate": gate,
    }


@router.get("/admin/calendar/release-gate/profile")
async def get_admin_release_gate_profile(request: Request):
    admin_user = await require_admin(request)
    active = await _get_active_release_gate_profile()
    return {
        "success": True,
        "feature": "book-meeting",
        "active_profile": active,
        "profiles": _RELIABILITY_PROFILES,
        "updated_by": getattr(admin_user, "user_id", ""),
    }


@router.put("/admin/calendar/release-gate/profile")
async def set_admin_release_gate_profile(request: Request, body: ReleaseGateProfileUpdateRequest):
    admin_user = await require_admin(request)
    active = await _set_active_release_gate_profile(body.profile, getattr(admin_user, "user_id", "system"))
    return {
        "success": True,
        "feature": "book-meeting",
        "active_profile": active,
        "profiles": _RELIABILITY_PROFILES,
    }


@router.get("/admin/calendar/release-gate/evaluate")
async def admin_release_gate_evaluate(request: Request, sample_size: int = 40):
    await require_admin(request)
    active_profile = await _get_active_release_gate_profile()
    dashboard = await admin_calendar_reliability_dashboard(
        request=request,
        profile=active_profile,
        sample_size=sample_size,
    )
    summary = dashboard.get("summary", {})
    go_rate = float(summary.get("go_rate") or 0.0)
    decision = "go" if go_rate >= 0.8 else "no-go"
    return {
        "feature": "book-meeting",
        "profile": active_profile,
        "decision": decision,
        "go_rate": go_rate,
        "summary": summary,
    }


@router.get("/admin/calendar/release-gate/safe-rollout-simulator")
async def admin_release_gate_safe_rollout_simulator(request: Request, sample_size: int = 40):
    await require_admin(request)
    normalized_size = max(5, min(int(sample_size), 80))
    active_profile = await _get_active_release_gate_profile()

    profile_rows = []
    for profile in ["strict", "standard", "lenient"]:
        dashboard = await admin_calendar_reliability_dashboard(
            request=request,
            profile=profile,
            sample_size=normalized_size,
        )
        summary = dashboard.get("summary", {})
        profile_rows.append(
            {
                "profile": profile,
                "users_evaluated": int(summary.get("users_evaluated") or 0),
                "go_count": int(summary.get("go_count") or 0),
                "no_go_count": int(summary.get("no_go_count") or 0),
                "go_rate": float(summary.get("go_rate") or 0.0),
            }
        )

    baseline = next((row for row in profile_rows if row.get("profile") == active_profile), None)
    baseline_go_count = int((baseline or {}).get("go_count") or 0)
    baseline_go_rate = float((baseline or {}).get("go_rate") or 0.0)
    for row in profile_rows:
        row["delta_go_count_vs_active"] = int(row.get("go_count") or 0) - baseline_go_count
        row["delta_go_rate_vs_active"] = round(float(row.get("go_rate") or 0.0) - baseline_go_rate, 4)

    recommended = max(profile_rows, key=lambda row: (float(row.get("go_rate") or 0.0), int(row.get("go_count") or 0))) if profile_rows else None

    return {
        "feature": "book-meeting",
        "active_profile": active_profile,
        "sample_size": normalized_size,
        "simulation": profile_rows,
        "recommendation": {
            "profile": (recommended or {}).get("profile") if recommended else active_profile,
            "reason": "Highest projected GO rate under sampled reliability checks.",
        },
    }


@router.get("/admin/calendar/reliability")
async def admin_calendar_reliability_dashboard(request: Request, profile: Optional[str] = None, sample_size: int = 40):
    await require_admin(request)
    active_profile = str(profile or "").strip().lower() or await _get_active_release_gate_profile()
    normalized_size = max(5, min(int(sample_size), 80))
    users = await db.users.find({}, {"_id": 0, "user_id": 1}).limit(normalized_size).to_list(normalized_size)

    rows = []
    for user in users:
        uid = str(user.get("user_id") or "").strip()
        if not uid:
            continue
        snapshot = await _compute_user_reliability_snapshot(uid)
        gate = _evaluate_release_gate(active_profile, snapshot)
        rows.append(
            {
                "user_id": uid,
                "plan_scope": snapshot.get("plan_scope"),
                "decision": gate.get("decision"),
                "failed_reasons": gate.get("failed_reasons", []),
                "metrics": snapshot.get("metrics", {}),
            }
        )

    go_count = sum(1 for row in rows if row.get("decision") == "go")
    no_go_count = sum(1 for row in rows if row.get("decision") == "no-go")

    return {
        "feature": "book-meeting",
        "profile": active_profile,
        "summary": {
            "users_evaluated": len(rows),
            "go_count": go_count,
            "no_go_count": no_go_count,
            "go_rate": round(_safe_ratio(go_count, max(1, len(rows))), 4),
        },
        "rows": rows,
    }
