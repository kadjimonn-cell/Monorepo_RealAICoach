"""Progressive risk engine helpers (0-100 risk scoring + enforcement metadata)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
import uuid

from fastapi import Request

from utils.email_service import is_email_configured, send_catalog_template


RISK_ENGINE_STATUS = "ACTIVE"

LOW_MAX = 30
MEDIUM_MAX = 60
HIGH_MAX = 80


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _extract_ip(request: Optional[Request]) -> str:
    if not request:
        return "unknown"
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _risk_level_from_score(score: int) -> str:
    if score <= LOW_MAX:
        return "low"
    if score <= MEDIUM_MAX:
        return "medium"
    if score <= HIGH_MAX:
        return "high"
    return "critical"


def _score_midpoint_for_level(level: str) -> int:
    band = (level or "low").lower()
    if band == "low":
        return 20
    if band == "medium":
        return 48
    if band == "high":
        return 71
    return 90


def _downgrade_level(level: str) -> str:
    band = (level or "low").lower()
    if band == "critical":
        return "high"
    if band == "high":
        return "medium"
    if band == "medium":
        return "low"
    return "low"


def _trigger_for_level(level: str) -> str:
    mapping = {
        "low": "NO_FRICTION",
        "medium": "STEP_UP_MFA",
        "high": "ADMIN_API_BLOCK_AND_MFA",
        "critical": "SESSION_LOCK_AND_ID_VERIFICATION",
    }
    return mapping.get((level or "low").lower(), "NO_FRICTION")


def _session_protection_for_level(level: str) -> str:
    mapping = {
        "low": "STANDARD_MONITORING",
        "medium": "MFA_CHALLENGE",
        "high": "PRIVILEGED_API_CONTAINMENT",
        "critical": "SESSION_LOCKDOWN",
    }
    return mapping.get((level or "low").lower(), "STANDARD_MONITORING")


def format_risk_engine_output(
    *,
    risk_score: int,
    risk_level: str,
    trigger: str,
    false_positive_rate_pct: float,
    session_protection: str,
    confidence_pct: float,
) -> str:
    return "\n".join(
        [
            f"RISK_ENGINE_STATUS: {RISK_ENGINE_STATUS}",
            f"RISK_SCORE: {int(risk_score)}",
            f"RISK_LEVEL: {str(risk_level).upper()}",
            f"TRIGGER: {trigger}",
            f"FALSE_POSITIVE_RATE: {round(float(false_positive_rate_pct), 2)}%",
            f"SESSION_PROTECTION: {session_protection}",
            f"CONFIDENCE: {round(float(confidence_pct), 1)}%",
        ]
    )


async def _estimate_false_positive_rate(db, confidence: float) -> float:
    reviewed_total = await db.risk_engine_feedback.count_documents({"reviewed": True})
    if reviewed_total > 0:
        false_positive_total = await db.risk_engine_feedback.count_documents({
            "reviewed": True,
            "outcome": "false_positive",
        })
        return round((false_positive_total / max(reviewed_total, 1)) * 100.0, 2)

    return round(_clamp((1.0 - confidence) * 30.0, 1.0, 35.0), 2)


def _risk_restrictions(level: str) -> Dict[str, bool]:
    band = (level or "low").lower()
    return {
        "requires_mfa": band in {"medium", "high"},
        "block_admin_privileged_api": band in {"high", "critical"},
        "require_id_verification": band == "critical",
        "lock_session": band == "critical",
    }


async def evaluate_progressive_risk(
    *,
    db,
    user_id: str,
    user_email: str,
    request: Optional[Request],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ctx = context or {}
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    since_1h = (now - timedelta(hours=1)).isoformat()
    since_24h = (now - timedelta(hours=24)).isoformat()
    since_7d = (now - timedelta(days=7)).isoformat()

    ip_address = _extract_ip(request)

    login_failed_1h = await db.security_events.count_documents(
        {
            "user_id": user_id,
            "event_type": "login_failed",
            "timestamp": {"$gte": since_1h},
        }
    )
    login_failed_24h = await db.security_events.count_documents(
        {
            "user_id": user_id,
            "event_type": "login_failed",
            "timestamp": {"$gte": since_24h},
        }
    )
    otp_failed_24h = await db.security_events.count_documents(
        {
            "user_id": user_id,
            "event_type": {"$in": ["otp_failed", "2fa_failed"]},
            "timestamp": {"$gte": since_24h},
        }
    )
    login_rate_limit_24h = await db.security_events.count_documents(
        {
            "$or": [{"user_id": user_id}, {"ip_address": ip_address}],
            "event_type": {"$in": ["login_rate_limit", "login_email_rate_limit", "admin_rate_limit"]},
            "timestamp": {"$gte": since_24h},
        }
    )

    known_device = bool(ctx.get("known_device", False))
    trusted_device = bool(ctx.get("trusted_device", False))
    country_changed = bool(ctx.get("country_changed", False))

    active_sessions = await db.user_sessions.count_documents(
        {"user_id": user_id, "expires_at": {"$gte": now}}
    )
    recent_sessions = await db.user_sessions.find(
        {
            "user_id": user_id,
            "issued_at": {"$gte": now - timedelta(hours=24)},
        },
        {"_id": 0, "ip_address": 1},
    ).to_list(100)
    distinct_ips_24h = len({str(item.get("ip_address") or "") for item in recent_sessions if item.get("ip_address")})

    high_events_24h = await db.security_events.count_documents(
        {
            "user_id": user_id,
            "risk_level": "high",
            "timestamp": {"$gte": since_24h},
        }
    )
    critical_events_24h = await db.security_events.count_documents(
        {
            "user_id": user_id,
            "risk_level": "critical",
            "timestamp": {"$gte": since_24h},
        }
    )
    admin_denied_24h = await db.security_events.count_documents(
        {
            "user_id": user_id,
            "event_type": {"$in": ["admin_access_denied", "role_denied", "blocked_user", "blocked_ip"]},
            "timestamp": {"$gte": since_24h},
        }
    )

    api_abuse_events_1h = await db.security_events.count_documents(
        {
            "$or": [{"user_id": user_id}, {"ip_address": ip_address}],
            "event_type": {
                "$in": [
                    "admin_rate_limit",
                    "login_rate_limit",
                    "login_email_rate_limit",
                    "jwt_invalid",
                    "invalid_session",
                    "blocked_ip",
                ]
            },
            "timestamp": {"$gte": since_1h},
        }
    )

    auth_score = min(
        100,
        (login_failed_1h * 18)
        + (max(0, login_failed_24h - 2) * 7)
        + (otp_failed_24h * 12)
        + (login_rate_limit_24h * 16),
    )

    device_score = 0
    if not known_device:
        device_score += 34
    if not trusted_device:
        device_score += 14
    if country_changed:
        device_score += 18
    if active_sessions > 3:
        device_score += min((active_sessions - 3) * 8, 24)
    if distinct_ips_24h > 2:
        device_score += min((distinct_ips_24h - 2) * 9, 24)
    device_score = min(device_score, 100)

    behavioral_score = min(100, (critical_events_24h * 26) + (high_events_24h * 12) + (admin_denied_24h * 10))
    api_abuse_score = min(100, (api_abuse_events_1h * 18) + (login_rate_limit_24h * 8))

    weighted_score = (
        auth_score * 0.30
        + device_score * 0.25
        + behavioral_score * 0.25
        + api_abuse_score * 0.20
    )
    risk_score = int(round(_clamp(weighted_score, 0, 100)))

    evidence_points = (
        login_failed_1h
        + login_failed_24h
        + otp_failed_24h
        + login_rate_limit_24h
        + high_events_24h
        + critical_events_24h
        + api_abuse_events_1h
        + (0 if known_device else 2)
        + (1 if country_changed else 0)
    )
    confidence = _clamp(0.58 + (evidence_points * 0.035), 0.58, 0.98)

    false_positive_rate_pct = await _estimate_false_positive_rate(db, confidence)

    risk_level = _risk_level_from_score(risk_score)
    false_positive_guard_applied = False
    if risk_level in {"high", "critical"} and confidence < 0.72:
        risk_level = _downgrade_level(risk_level)
        risk_score = _score_midpoint_for_level(risk_level)
        false_positive_guard_applied = True

    trigger = _trigger_for_level(risk_level)
    session_protection = _session_protection_for_level(risk_level)
    confidence_pct = round(confidence * 100.0, 1)
    output_block = format_risk_engine_output(
        risk_score=risk_score,
        risk_level=risk_level,
        trigger=trigger,
        false_positive_rate_pct=false_positive_rate_pct,
        session_protection=session_protection,
        confidence_pct=confidence_pct,
    )

    return {
        "assessment_id": f"risk_{uuid.uuid4().hex[:12]}",
        "risk_engine_status": RISK_ENGINE_STATUS,
        "user_id": user_id,
        "user_email": user_email,
        "assessed_at": now_iso,
        "source": str(ctx.get("source") or "runtime"),
        "stage": str(ctx.get("stage") or "runtime"),
        "ip_address": ip_address,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "trigger": trigger,
        "session_protection": session_protection,
        "confidence": round(confidence, 3),
        "confidence_pct": confidence_pct,
        "false_positive_rate_pct": false_positive_rate_pct,
        "false_positive_guard_applied": false_positive_guard_applied,
        "signals": {
            "authentication": {
                "score": int(round(auth_score)),
                "failed_logins_1h": int(login_failed_1h),
                "failed_logins_24h": int(login_failed_24h),
                "otp_failures_24h": int(otp_failed_24h),
                "rate_limits_24h": int(login_rate_limit_24h),
            },
            "device_session": {
                "score": int(round(device_score)),
                "known_device": known_device,
                "trusted_device": trusted_device,
                "country_changed": country_changed,
                "active_sessions": int(active_sessions),
                "distinct_ips_24h": int(distinct_ips_24h),
            },
            "behavioral": {
                "score": int(round(behavioral_score)),
                "high_events_24h": int(high_events_24h),
                "critical_events_24h": int(critical_events_24h),
                "admin_denied_24h": int(admin_denied_24h),
            },
            "api_abuse": {
                "score": int(round(api_abuse_score)),
                "api_abuse_events_1h": int(api_abuse_events_1h),
                "rate_limit_events_24h": int(login_rate_limit_24h),
            },
        },
        "rolling_windows": {
            "hour": since_1h,
            "day": since_24h,
            "week": since_7d,
        },
        "restrictions": _risk_restrictions(risk_level),
        "output_block": output_block,
    }


def _should_send_admin_alert(previous_profile: Optional[dict], assessment: Dict[str, Any]) -> bool:
    level = str(assessment.get("risk_level") or "low").lower()
    score = int(assessment.get("risk_score") or 0)
    if level in {"high", "critical"}:
        return True

    if not previous_profile:
        return level in {"medium", "high", "critical"}

    prev_level = str(previous_profile.get("risk_level") or "low").lower()
    prev_score = int(previous_profile.get("risk_score") or 0)
    return prev_level != level and abs(prev_score - score) >= 15 and level in {"medium", "high", "critical"}


async def _send_admin_risk_email(db, assessment: Dict[str, Any], source: str) -> int:
    if not is_email_configured():
        return 0

    admins = await db.users.find(
        {"$or": [{"is_admin": True}, {"role": "admin"}]},
        {"_id": 0, "email": 1, "name": 1},
    ).to_list(200)

    sent = 0
    seen = set()
    for admin in admins:
        email = str(admin.get("email") or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        result = await send_catalog_template(
            recipient_email=email,
            template_key="risk_engine_status_v7",
            recipient_name=admin.get("name") or "Admin",
            user_id=assessment.get("user_id", ""),
            user_email=assessment.get("user_email", ""),
            risk_score=int(assessment.get("risk_score") or 0),
            risk_level=str(assessment.get("risk_level") or "low").upper(),
            trigger=str(assessment.get("trigger") or "NO_FRICTION"),
            false_positive_rate=f"{assessment.get('false_positive_rate_pct', 0)}%",
            session_protection=str(assessment.get("session_protection") or "STANDARD_MONITORING"),
            confidence=f"{assessment.get('confidence_pct', 0)}%",
            output_block=str(assessment.get("output_block") or ""),
            source=source,
            scored_at=str(assessment.get("assessed_at") or ""),
        )
        if result.get("success"):
            sent += 1
    return sent


async def persist_risk_assessment(
    *,
    db,
    assessment: Dict[str, Any],
    source: str,
    notify_admins: bool = True,
) -> Dict[str, Any]:
    user_id = str(assessment.get("user_id") or "")
    if not user_id:
        return {"saved": False, "alert_sent": 0, "previous_profile": None}

    previous = await db.progressive_risk_profiles.find_one({"user_id": user_id}, {"_id": 0})

    assessment_doc = {
        **assessment,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.progressive_risk_assessments.insert_one(assessment_doc)

    profile_doc = {
        "user_id": user_id,
        "user_email": assessment.get("user_email"),
        "risk_engine_status": assessment.get("risk_engine_status", RISK_ENGINE_STATUS),
        "risk_score": int(assessment.get("risk_score") or 0),
        "risk_level": assessment.get("risk_level", "low"),
        "trigger": assessment.get("trigger", "NO_FRICTION"),
        "false_positive_rate_pct": float(assessment.get("false_positive_rate_pct") or 0.0),
        "session_protection": assessment.get("session_protection", "STANDARD_MONITORING"),
        "confidence": float(assessment.get("confidence") or 0.0),
        "confidence_pct": float(assessment.get("confidence_pct") or 0.0),
        "restrictions": assessment.get("restrictions") or {},
        "output_block": assessment.get("output_block") or "",
        "signals": assessment.get("signals") or {},
        "last_assessment_id": assessment.get("assessment_id"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.progressive_risk_profiles.update_one({"user_id": user_id}, {"$set": profile_doc}, upsert=True)

    alerts_sent = 0
    if notify_admins and _should_send_admin_alert(previous, assessment):
        alerts_sent = await _send_admin_risk_email(db, assessment, source)

    return {
        "saved": True,
        "previous_profile": previous,
        "alert_sent": alerts_sent,
    }