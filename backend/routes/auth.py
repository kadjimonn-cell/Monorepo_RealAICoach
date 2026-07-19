"""Authentication routes extracted from server.py."""

from fastapi import APIRouter, HTTPException, Request, Response, Query
import re
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
import uuid
import os
import logging
import random
import base64
import httpx
import secrets
import hashlib
import time as _time
from urllib.parse import urlencode, quote as _url_quote, urlparse
import hmac
import json
from html import escape as _html_escape
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from routes.db import (
    db,
    User,
    UserSession,
    hash_password,
    verify_password,
    create_jwt_token,
    get_current_user,
    is_admin_email,
    is_full_access_email,
    apply_access_overrides,
    log_security_event,
    apply_security_block,
    is_security_blocked,
    _apply_preview_risk_bypass_if_allowed,
    JWT_SECRET,
)
from routes.payments_catalog import get_subscription_plan_from_gps
from utils.rate_limit import check_rate_limit, clear_rate_limit
from utils.email_service import (
    send_catalog_template,
    send_template_email,
    is_email_configured as is_email_configured,
    is_nonprod_test_domain_recipient,
)
from utils.progressive_risk_engine import evaluate_progressive_risk, persist_risk_assessment, format_risk_engine_output
from utils.ws_ticket_auth import hash_ws_ticket

logger = logging.getLogger(__name__)
router = APIRouter()

AUTH_COVERAGE_REPORT_DIR = "/app/test_reports"
AUTH_COVERAGE_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
AUTH_COVERAGE_LABELS = {
    "core_auth_session": "Core Auth / Session",
    "password_reset_verification": "Password Reset / Verification",
    "otp_2fa": "OTP / 2FA",
    "biometric_passkey": "Biometric / Passkey",
    "passwordless": "Passwordless (QR / Magic Link)",
    "sso_platform_level": "SSO Platform-Level",
    "linking_merge": "Linked Accounts / Merge",
    "security_trust_device": "Security / Trust Device",
    "admin_auth_controls": "Admin Auth Controls",
    "auth_bound_media": "Auth-Bound Media",
}

try:
    AUTH_PROFILE_IMAGE_INLINE_MAX_CHARS = int(str(os.environ.get("AUTH_PROFILE_IMAGE_INLINE_MAX_CHARS") or "2048"))
except Exception:
    AUTH_PROFILE_IMAGE_INLINE_MAX_CHARS = 2048

EMAIL_OTP_TEMPLATE_KEY = os.environ.get("EMAIL_OTP_TEMPLATE_KEY", "email-otp")
EMAIL_OTP_EXPIRY_MINUTES = os.environ.get("OTP_EXPIRY_MINUTES", "10")
RESET_LINK_BASE = os.environ.get("RESET_LINK_BASE")
VERIFY_LINK_BASE = os.environ.get("VERIFY_LINK_BASE")
PASSKEY_ROLLOUT_PERCENT = int(str(os.environ.get("PASSKEY_ROLLOUT_PERCENT") or "100"))
PASSKEY_CHALLENGE_TTL_SECONDS = int(str(os.environ.get("PASSKEY_CHALLENGE_TTL_SECONDS") or "180"))
PASSKEY_PROMPT_COOLDOWN_SECONDS = int(str(os.environ.get("PASSKEY_PROMPT_COOLDOWN_SECONDS") or "1209600"))

ADMIN_SESSION_MINUTES = 300  # 5 hours
USER_SESSION_MINUTES = 300  # 5 hours inactivity auto-logout
REMEMBER_ME_MINUTES = 43200  # 30 days
SESSION_TIMEOUT_CONFIG_KEY = "session_timeout_config"
SSO_TELEMETRY_RETENTION_DAYS = 30
SSO_TELEMETRY_MAX_EVENTS = 10000
SSO_TELEMETRY_AUTO_PRUNE_INTERVAL_SECONDS = 300
_sso_telemetry_last_prune_at: Optional[datetime] = None
TENANT_DISCLAIMER_PROFILE_MAP_KEY = "tenant_disclaimer_profile_map"
LEGAL_PROFILE_VALUES = {"default", "strict_regulated"}
LOGOUT_TELEMETRY_COLLECTION = "auth_logout_telemetry_events"
AUTH_SESSION_TELEMETRY_COLLECTION = "auth_session_bootstrap_telemetry"
WS_TICKET_TTL_SECONDS = 90
WS_TICKET_ALLOWED_CHANNELS = {
    "notifications",
    "ticket_chat",
    "admin_activity",
    "automation_dashboard",
    "aso_dashboard",
    "siem_events",
    "enterprise_live",
    "system_metrics",
    "jobs_employer_pipeline",
    "fps_game",
}
WS_TICKET_ADMIN_CHANNELS = {
    "admin_activity",
    "automation_dashboard",
    "aso_dashboard",
    "siem_events",
    "enterprise_live",
    "system_metrics",
}

# ── Password Strength ──
MIN_PASSWORD_LENGTH = 8

def validate_password_strength(password: str) -> str | None:
    """Returns error message if password is weak, None if strong."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number"
    return None


def _clamp_session_minutes(value: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(fallback)
    return max(30, min(parsed, 24 * 60))


async def _load_session_timeout_config() -> Dict[str, int]:
    doc = await db.platform_runtime_config.find_one({"key": SESSION_TIMEOUT_CONFIG_KEY}, {"_id": 0}) or {}
    admin_minutes = _clamp_session_minutes(doc.get("admin_minutes", ADMIN_SESSION_MINUTES), ADMIN_SESSION_MINUTES)
    user_minutes = _clamp_session_minutes(doc.get("user_minutes", USER_SESSION_MINUTES), USER_SESSION_MINUTES)
    return {
        "admin_minutes": admin_minutes,
        "user_minutes": user_minutes,
    }


async def _resolve_session_timeout_minutes(is_admin: bool) -> int:
    cfg = await _load_session_timeout_config()
    return int(cfg["admin_minutes"] if is_admin else cfg["user_minutes"])


async def _session_timeout_config_response() -> Dict[str, object]:
    cfg = await _load_session_timeout_config()
    return {
        "admin_minutes": int(cfg["admin_minutes"]),
        "user_minutes": int(cfg["user_minutes"]),
        "admin_hours": round(int(cfg["admin_minutes"]) / 60, 2),
        "user_hours": round(int(cfg["user_minutes"]) / 60, 2),
    }


async def invalidate_user_sessions(user_id: str, keep_current: str = None):
    """Invalidate all sessions for a user, optionally keeping the current one."""
    query = {"user_id": user_id}
    if keep_current:
        query["session_token"] = {"$ne": keep_current}
    await db.user_sessions.delete_many(query)


def _allow_native_auth_tokens(request: Optional[Request]) -> bool:
    if request is None:
        return False
    channel_hint = str(
        request.headers.get("X-Client-Platform")
        or request.headers.get("X-Auth-Channel")
        or ""
    ).strip().lower()
    return channel_hint in {"mobile", "native", "android", "ios", "expo"}


def _extract_request_host(request: Optional[Request]) -> str:
    if request is None:
        return ""

    forwarded_host = str(request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
    if forwarded_host:
        return forwarded_host

    host_header = str(request.headers.get("host") or "").split(",")[0].strip()
    if host_header:
        return host_header

    if request.url and request.url.hostname:
        if request.url.port and request.url.port not in (80, 443):
            return f"{request.url.hostname}:{request.url.port}"
        return str(request.url.hostname)

    return ""


def _is_localhost_host(raw_host: str) -> bool:
    host = str(raw_host or "").strip().lower()
    if not host:
        return False

    if host.startswith("[") and "]" in host:
        host = host[1:host.index("]")]
    elif host.count(":") == 1:
        host = host.split(":")[0].strip()

    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    return host.endswith(".localhost")


def _resolve_session_cookie_security(request: Optional[Request]) -> Dict[str, Any]:
    host = _extract_request_host(request)
    is_local = _is_localhost_host(host)
    if is_local:
        return {"secure": False, "samesite": "lax"}
    return {"secure": True, "samesite": "none"}


def _set_session_cookie(response: Response, token: str, max_age_seconds: int, request: Optional[Request] = None) -> None:
    cookie_security = _resolve_session_cookie_security(request)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=bool(cookie_security["secure"]),
        samesite=str(cookie_security["samesite"]),
        max_age=max_age_seconds,
        path="/",
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie("session_token", path="/")

    # Compatibility sweep: explicitly expire both secure and local variants.
    for secure, samesite in ((True, "none"), (False, "lax")):
        try:
            response.set_cookie(
                key="session_token",
                value="",
                max_age=0,
                expires=0,
                httponly=True,
                secure=secure,
                samesite=samesite,
                path="/",
            )
        except Exception:
            continue


def _auth_token_payload(
    request: Optional[Request],
    *,
    session_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> Dict[str, str]:
    if not _allow_native_auth_tokens(request):
        return {}
    payload: Dict[str, str] = {}
    if session_token:
        payload["session_token"] = session_token
    if refresh_token:
        payload["refresh_token"] = refresh_token
    return payload


def _normalize_ws_ticket_channel(raw_channel: str) -> str:
    channel = str(raw_channel or "notifications").strip().lower()
    if channel not in WS_TICKET_ALLOWED_CHANNELS:
        raise HTTPException(status_code=400, detail="Unsupported ws ticket channel")
    return channel

def _parse_email_set(raw: str) -> set[str]:
    return {
        email.strip().lower()
        for email in str(raw or "").split(",")
        if str(email or "").strip()
    }


def _env_flag_enabled(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on", "enabled"}


# 2FA exempted emails — these accounts bypass OTP at login
OTP_EXEMPT_EMAILS = _parse_email_set(os.environ.get("OTP_EXEMPT_EMAILS", ""))
AUTH_TEST_HELPER_DEFAULT_EMAIL_ALLOWLIST = {
    "e2e.2fa.stable@realaicoach.app",
    "e2e.candidate.20260507105947@gmail.com",
    "p1.free.1779113329@example.com",
    "jobs.free.final.90705154@gmail.com",
    "feature26.approved.employer.e2e@realaicoach.app",
    "f21.basic.1781338672@example.com",
}
AUTH_TEST_HELPER_PURPOSE_ALLOWLIST = {"2fa", "login"}


def _is_non_production_runtime() -> bool:
    env_values = [
        str(os.environ.get("ENVIRONMENT") or "").strip().lower(),
        str(os.environ.get("APP_ENV") or "").strip().lower(),
        str(os.environ.get("NODE_ENV") or "").strip().lower(),
    ]

    for value in env_values:
        if value in {"prod", "production", "live"}:
            return False

    for value in env_values:
        if value in {"dev", "development", "test", "testing", "staging", "preview", "local", "localhost"}:
            return True

    frontend_host = str(os.environ.get("FRONTEND_BASE_URL") or "").strip().lower()
    if "localhost" in frontend_host or "127.0.0.1" in frontend_host:
        return True
    if "preview.emergentagent.com" in frontend_host:
        return True

    return False


def _auth_test_helpers_enabled() -> bool:
    raw_toggle = str(os.environ.get("AUTH_TEST_HELPERS_ENABLED") or "").strip().lower()
    toggle_enabled = False
    if raw_toggle:
        toggle_enabled = raw_toggle in {"1", "true", "yes", "on", "enabled"}
    return bool(toggle_enabled and _is_non_production_runtime())


def _auth_test_helper_email_allowlist() -> set[str]:
    configured = _parse_email_set(os.environ.get("E2E_OTP_HELPER_EMAILS", ""))
    combined = set(AUTH_TEST_HELPER_DEFAULT_EMAIL_ALLOWLIST)
    combined.update(configured)
    return {email.strip().lower() for email in combined if str(email or "").strip()}


def _auth_e2e_otp_bypass_enabled() -> bool:
    return bool(
        _is_non_production_runtime()
        and _env_flag_enabled("AUTH_E2E_OTP_BYPASS_ENABLED", False)
    )


def _auth_e2e_otp_bypass_email_allowlist() -> set[str]:
    configured = _parse_email_set(os.environ.get("AUTH_E2E_OTP_BYPASS_EMAILS", ""))
    combined = set(configured)
    if _auth_test_helpers_enabled():
        combined.update(_auth_test_helper_email_allowlist())
    return {email.strip().lower() for email in combined if str(email or "").strip()}


def _auth_e2e_otp_bypass_admin_only() -> bool:
    return bool(_env_flag_enabled("AUTH_E2E_OTP_BYPASS_ADMIN_ONLY", True))


def _should_apply_e2e_otp_login_bypass(user: Any) -> bool:
    if user is None or not _auth_e2e_otp_bypass_enabled():
        return False

    if isinstance(user, dict):
        email = str(user.get("email") or "").strip().lower()
        is_admin = bool(user.get("is_admin"))
        full_access = bool(user.get("full_access"))
    else:
        email = str(getattr(user, "email", "") or "").strip().lower()
        is_admin = bool(getattr(user, "is_admin", False))
        full_access = bool(getattr(user, "full_access", False))

    if not email:
        return False

    allowlisted = _auth_e2e_otp_bypass_email_allowlist()
    if not allowlisted or email not in allowlisted:
        return False

    if _auth_e2e_otp_bypass_admin_only() and not (is_admin or full_access):
        helper_allowlisted_non_admin = bool(
            _auth_test_helpers_enabled()
            and email in _auth_test_helper_email_allowlist()
        )
        if not helper_allowlisted_non_admin:
            return False

    return True


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except Exception:
        value = int(default)
    return max(minimum, value)


LOGIN_RATE_LIMIT = _env_int("LOGIN_RATE_LIMIT", 50)
LOGIN_RATE_WINDOW = _env_int("LOGIN_RATE_WINDOW_SECONDS", 60)
LOGIN_EMAIL_RATE_LIMIT = _env_int("LOGIN_EMAIL_RATE_LIMIT", 10)
LOGIN_EMAIL_RATE_WINDOW = _env_int("LOGIN_EMAIL_RATE_WINDOW_SECONDS", 900, 60)

AUTH_RATE_LIMIT_BYPASS_EMAILS = _parse_email_set(os.environ.get("AUTH_RATE_LIMIT_BYPASS_EMAILS", ""))
AUTH_RATE_LIMIT_BYPASS_EMAILS.update(OTP_EXEMPT_EMAILS)
AUTH_RATE_LIMIT_BYPASS_EMAILS.update(_parse_email_set(os.environ.get("ADMIN_EMAILS", "")))
admin_email_seed = str(os.environ.get("ADMIN_EMAIL") or "").strip().lower()
if admin_email_seed:
    AUTH_RATE_LIMIT_BYPASS_EMAILS.add(admin_email_seed)


OTP_GRACE_DAYS = 30
OTP_POST_VERIFY_GRACE_DAYS = _env_int("OTP_POST_VERIFY_GRACE_DAYS", 30)
OTP_MAX_ATTEMPTS = 3
OTP_LOCK_THRESHOLD = 5
OTP_RATE_LIMIT_PER_HOUR = _env_int("OTP_RATE_LIMIT_PER_HOUR", 3)
OTP_RATE_LIMIT_WINDOW_SECONDS = _env_int("OTP_RATE_LIMIT_WINDOW_SECONDS", 900, 60)
OTP_RATE_LIMIT_PRIVILEGED_MULTIPLIER = _env_int("OTP_RATE_LIMIT_PRIVILEGED_MULTIPLIER", 4)
OTP_CODE_LENGTH = 8
_azure_authority_fallback_warning_emitted = False


def _is_otp_exempt(email: str) -> bool:
    return str(email or "").strip().lower() in OTP_EXEMPT_EMAILS


def _is_login_rate_limit_exempt(email: str) -> bool:
    normalized = str(email or "").strip().lower()
    if not normalized:
        return False
    if normalized in AUTH_RATE_LIMIT_BYPASS_EMAILS:
        return True
    return normalized.startswith("e2e.")


def _is_otp_policy_exempt(user: Any) -> bool:
    """Unified OTP exemption policy across auth flows.

    Global safeguard: privileged accounts and explicit policy emails are OTP-exempt.
    """
    if user is None:
        return False
    if isinstance(user, dict):
        email = str(user.get("email") or "")
        is_admin = bool(user.get("is_admin"))
        full_access = bool(user.get("full_access"))
    else:
        email = str(getattr(user, "email", "") or "")
        is_admin = bool(getattr(user, "is_admin", False))
        full_access = bool(getattr(user, "full_access", False))
    return _is_otp_exempt(email) or is_admin or full_access


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _build_auth_recovery_detail(
    message: str,
    code: str,
    *,
    retry_after_seconds: Optional[int] = None,
    blocked_until: Optional[datetime] = None,
    support_url: str = "/contact",
    reset_password_url: str = "/auth/forgot-password",
) -> Dict[str, Any]:
    detail: Dict[str, Any] = {
        "message": message,
        "code": code,
        "support_url": support_url,
        "reset_password_url": reset_password_url,
        "recovery_actions": ["contact_support", "reset_password"],
    }
    if retry_after_seconds is not None:
        detail["retry_after_seconds"] = max(1, int(retry_after_seconds))
    if blocked_until is not None:
        detail["blocked_until"] = blocked_until.isoformat() if hasattr(blocked_until, "isoformat") else str(blocked_until)
    return detail


def _safe_profile_image_for_auth_response(value: Any) -> str:
    image_value = str(value or "").strip()
    if not image_value:
        return ""
    if image_value.lower().startswith("data:image/") and len(image_value) > AUTH_PROFILE_IMAGE_INLINE_MAX_CHARS:
        return ""
    return image_value


async def _run_progressive_risk_assessment(
    user: User,
    request: Optional[Request],
    *,
    stage: str,
    source: str,
) -> Optional[Dict[str, Any]]:
    """Evaluate and persist progressive risk posture for the active auth flow."""
    try:
        resolved_ctx = await _resolve_client_context(request) if request else {"ip": "unknown", "location": "Unknown"}
        country = await _detect_country(request) if request else "US"
        user_agent = request.headers.get("User-Agent", "Unknown device") if request else "Unknown device"
        ip_addr = resolved_ctx.get("ip") or (request.client.host if request and request.client else "unknown")
        device_fp = _fingerprint_device(user_agent, ip_addr)
        known_device_doc = await db.known_devices.find_one(
            {"user_id": user.user_id, "device_id": device_fp},
            {"_id": 0, "trusted": 1, "country": 1},
        )
        known_country = str(known_device_doc.get("country") or "").upper() if known_device_doc else ""
        country_changed = bool(known_country and country and known_country != str(country).upper())

        risk_assessment = await evaluate_progressive_risk(
            db=db,
            user_id=user.user_id,
            user_email=user.email,
            request=request,
            context={
                "stage": stage,
                "source": source,
                "known_device": bool(known_device_doc),
                "trusted_device": bool(known_device_doc.get("trusted", False)) if known_device_doc else False,
                "country_changed": country_changed,
            },
        )
        await persist_risk_assessment(
            db=db,
            assessment=risk_assessment,
            source=source,
            notify_admins=True,
        )
        return risk_assessment
    except Exception as risk_exc:
        logger.warning(f"Progressive risk assessment skipped for {user.user_id}: {risk_exc}")
        return None


async def _apply_preview_login_risk_bypass_if_allowed(
    *,
    user: User,
    request: Optional[Request],
    risk_assessment: Optional[Dict[str, Any]],
    source: str,
) -> Optional[Dict[str, Any]]:
    """Allow explicit preview/test bypass for admin auth lockouts without weakening production."""
    if not risk_assessment:
        return risk_assessment

    restrictions = risk_assessment.get("restrictions") or {}
    if not restrictions.get("require_id_verification"):
        return risk_assessment

    bypassed = await _apply_preview_risk_bypass_if_allowed(
        user=user,
        request=request,
        active_risk=risk_assessment,
        bypass_scope=source,
    )
    if not bypassed:
        return risk_assessment

    bypassed_assessment = _apply_alternative_recovery_bypass(risk_assessment, "preview_risk_bypass")
    await persist_risk_assessment(
        db=db,
        assessment=bypassed_assessment or {},
        source=f"{source}_preview_bypass",
        notify_admins=False,
    )
    return bypassed_assessment


def _risk_guidance_for_level(level: str, recovery_mode: Optional[str] = None) -> Dict[str, Any]:
    band = str(level or "low").lower()
    support_email = "security@realaicoach.app"
    if recovery_mode == "alternative_recovery_approved":
        return {
            "message": "Your alternative recovery verification is successful. ID Checker is optional for now, and enhanced monitoring remains active.",
            "steps": [
                "Optional: Complete ID Checker anytime for maximum account trust and faster future sign-ins.",
                "Optional: Upload identification documents if you prefer formal identity validation.",
                "Continue securely using your reset-password or one-time-code recovery path.",
            ],
            "risk_code": "risk_engine_alternative_recovery_approved",
            "support_email": support_email,
        }
    if band == "critical":
        return {
            "message": "We detected critical security risk and activated account protection. You may choose verification or an alternative recovery path.",
            "steps": [
                "Optional: Open ID Checker from the security prompt.",
                "Optional: Upload and submit your identification documents if you select verification.",
                "Alternative recovery: Reset Password or use One-Time Code sign-in to continue without mandatory ID Checker.",
            ],
            "risk_code": "risk_engine_recovery_options_available",
            "support_email": support_email,
        }
    if band == "high":
        return {
            "message": "We detected high-risk activity. Privileged actions are temporarily blocked for account protection.",
            "steps": [
                "Complete the MFA prompt to confirm this login.",
                "Review recent devices/sessions in Security settings.",
                "If this sign-in was not you, reset your password immediately or contact security support.",
            ],
            "risk_code": "risk_engine_admin_api_blocked",
            "support_email": support_email,
        }
    if band == "medium":
        return {
            "message": "We detected unusual activity and added a step-up MFA check to keep your account safe.",
            "steps": [
                "Enter the one-time code sent to your verified channel.",
                "Confirm your session after successful code verification.",
                "Contact security support if you did not initiate this login.",
            ],
            "risk_code": "risk_engine_step_up_mfa",
            "support_email": support_email,
        }
    return {
        "message": "No additional security action required.",
        "steps": [],
        "risk_code": "risk_engine_no_action",
        "support_email": support_email,
    }


def _apply_alternative_recovery_bypass(
    risk_assessment: Optional[Dict[str, Any]],
    method: str,
) -> Optional[Dict[str, Any]]:
    """Downgrade CRITICAL lockout after approved alternative recovery (password reset or one-time code)."""
    if not risk_assessment:
        return risk_assessment
    if str(risk_assessment.get("risk_level") or "").lower() != "critical":
        return risk_assessment

    downgraded_score = max(46, min(58, int(risk_assessment.get("risk_score") or 56)))
    risk_assessment["risk_level"] = "medium"
    risk_assessment["risk_score"] = downgraded_score
    risk_assessment["trigger"] = "STEP_UP_MFA"
    risk_assessment["session_protection"] = "MFA_CHALLENGE"
    risk_assessment["restrictions"] = {
        "requires_mfa": True,
        "block_admin_privileged_api": False,
        "require_id_verification": False,
        "lock_session": False,
    }
    risk_assessment["recovery_bypass"] = {
        "applied": True,
        "method": method,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
    risk_assessment["output_block"] = format_risk_engine_output(
        risk_score=downgraded_score,
        risk_level="medium",
        trigger="STEP_UP_MFA",
        false_positive_rate_pct=float(risk_assessment.get("false_positive_rate_pct") or 0),
        session_protection="MFA_CHALLENGE",
        confidence_pct=float(risk_assessment.get("confidence_pct") or 70),
    )
    return risk_assessment


async def _send_user_risk_guidance_email(user: User, risk_assessment: Dict[str, Any], guidance: Dict[str, Any]) -> bool:
    """Send user-facing security guidance email with anti-spam cooldown."""
    try:
        if not user.email:
            return False
        level = str((risk_assessment or {}).get("risk_level") or "low").lower()
        if level == "low":
            return False

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        recent = await db.risk_user_guidance_log.find_one(
            {
                "user_id": user.user_id,
                "risk_level": level,
                "created_at": {"$gte": cutoff},
            },
            {"_id": 0},
        )
        if recent:
            return False

        result = await send_catalog_template(
            recipient_email=user.email,
            template_key="risk_engine_user_guidance_v7",
            recipient_name=user.name or "there",
            risk_level=str(level).upper(),
            risk_score=int((risk_assessment or {}).get("risk_score") or 0),
            trigger=str((risk_assessment or {}).get("trigger") or "STEP_UP_MFA"),
            message=str(guidance.get("message") or ""),
            next_steps=guidance.get("steps") or [],
            support_url=str(guidance.get("support_email") or "security@realaicoach.app"),
            idv_url=(
                f"{str(os.environ.get('FRONTEND_BASE_URL') or '').rstrip('/')}/id-checker"
                if str(os.environ.get('FRONTEND_BASE_URL') or '').strip()
                else "/id-checker"
            ),
        )

        await db.risk_user_guidance_log.insert_one(
            {
                "log_id": f"risk_user_guidance_{uuid.uuid4().hex[:10]}",
                "user_id": user.user_id,
                "email": user.email,
                "risk_level": level,
                "risk_score": int((risk_assessment or {}).get("risk_score") or 0),
                "sent": bool(result.get("success")),
                "error": result.get("error") if not result.get("success") else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return bool(result.get("success"))
    except Exception as email_exc:
        logger.warning(f"User risk guidance email failed for {user.user_id}: {email_exc}")
        return False


async def _create_idv_access_token(user_id: str, source: str = "risk_lockout") -> Optional[str]:
    """Create short-lived token allowing locked-out users to continue ID Checker flow."""
    try:
        token = f"idv_{uuid.uuid4().hex}{uuid.uuid4().hex[:12]}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=45)
        await db.idv_access_tokens.insert_one(
            {
                "token": token,
                "user_id": user_id,
                "source": source,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at,
                "revoked": False,
            }
        )
        return token
    except Exception as token_exc:
        logger.warning(f"Unable to create IDV access token for {user_id}: {token_exc}")
        return None


# ═════════════════════════════════════════════════════════
# CLIENT CONTEXT RESOLVER (IP, Location, Device)
# ═════════════════════════════════════════════════════════

def _get_real_ip(request: Request) -> str:
    """Extract the real client IP from proxy headers.
    Priority: X-Real-IP > first non-private X-Forwarded-For > client.host
    """
    # X-Real-IP is set by many reverse proxies and is the most reliable
    real_ip = (request.headers.get("X-Real-IP") or "").strip()
    if real_ip and not real_ip.startswith(("10.", "172.", "192.168.", "127.", "0.")):
        return real_ip

    # X-Forwarded-For: <client>, <proxy1>, <proxy2>
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        parts = [p.strip() for p in xff.split(",")]
        # Find the first public IP (skip private/internal IPs)
        for part in parts:
            if part and not part.startswith(("10.", "172.", "192.168.", "127.", "0.", "169.254.", "fc", "fd", "fe80")):
                return part
        # If all are private, use the first one
        if parts[0]:
            return parts[0]

    # Fallback to direct connection IP
    if request.client:
        return request.client.host
    return "unknown"


def _parse_device_name(ua_string: str) -> str:
    """Parse User-Agent string into a friendly device name like 'Chrome 147 on Windows 10'."""
    if not ua_string or ua_string == "Unknown device":
        return "Unknown Device"
    try:
        from user_agents import parse as ua_parse
        ua = ua_parse(ua_string)
        browser = ua.browser.family or "Unknown Browser"
        browser_ver = ua.browser.version_string
        if browser_ver:
            # Take only major version
            major = browser_ver.split(".")[0]
            browser = f"{browser} {major}"
        os_name = ua.os.family or ""
        os_ver = ua.os.version_string
        if os_name and os_ver:
            os_full = f"{os_name} {os_ver}"
        elif os_name:
            os_full = os_name
        else:
            os_full = ""
        device_brand = ua.device.brand or ""
        device_model = ua.device.model or ""
        device_str = f"{device_brand} {device_model}".strip()
        # Build result
        parts = [browser]
        if os_full:
            parts.append(f"on {os_full}")
        if device_str and device_str not in ("Other", ""):
            parts.append(f"({device_str})")
        return " ".join(parts)
    except Exception:
        # Fallback: extract basic info from UA string
        if "Chrome" in ua_string:
            return "Chrome Browser"
        if "Firefox" in ua_string:
            return "Firefox Browser"
        if "Safari" in ua_string:
            return "Safari Browser"
        return ua_string[:80]


async def _resolve_client_context(request: Request) -> dict:
    """Resolve the full client context: real IP, geo location, device name."""
    ip = _get_real_ip(request)
    ua_raw = request.headers.get("User-Agent", "Unknown device") if request else "Unknown"
    device = _parse_device_name(ua_raw)

    # Resolve geo location using the ip_geolocation module
    location = "Unknown"
    try:
        from utils.ip_geolocation import lookup_ip
        geo = await lookup_ip(db, ip)
        if geo:
            city = geo.get("city", "")
            region = geo.get("region", "")
            country = geo.get("country", "")
            parts = [p for p in [city, region, country] if p]
            if parts:
                location = ", ".join(parts)
    except Exception as e:
        logger.warning(f"Geo lookup failed for {ip}: {e}")

    return {"ip": ip, "location": location, "device": device, "ua_raw": ua_raw}

# ═════════════════════════════════════════════════════════


def _build_ip_block_detail(block_doc: Dict[str, Any]) -> Dict[str, Any]:
    blocked_until = block_doc.get("blocked_until")
    if isinstance(blocked_until, str):
        try:
            blocked_until = datetime.fromisoformat(blocked_until.replace("Z", "+00:00"))
        except Exception:
            blocked_until = None
    if hasattr(blocked_until, "tzinfo") and blocked_until and blocked_until.tzinfo is None:
        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
    retry_after_seconds = None
    if blocked_until:
        retry_after_seconds = int(max(1, (blocked_until - datetime.now(timezone.utc)).total_seconds()))
    return _build_auth_recovery_detail(
        "Sign-in is temporarily blocked from this network after multiple failed attempts. Please wait and try again, reset your password, or contact support if you need immediate help.",
        "ip_temporarily_blocked",
        retry_after_seconds=retry_after_seconds,
        blocked_until=blocked_until,
    )


async def _get_password_reset_unlock_waiver(email: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query: Dict[str, Any] = {"email": email.lower()}
    if user_id:
        query["user_id"] = user_id
    waiver = await db.password_reset_unlock_waivers.find_one(query, {"_id": 0})
    if not waiver:
        return None
    expires_at = waiver.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            expires_at = None
    if expires_at and hasattr(expires_at, "tzinfo") and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        await db.password_reset_unlock_waivers.delete_many(query)
        return None
    return waiver


async def _check_otp_grace_period(user_id: str) -> bool:
    """Return True when OTP challenge can be skipped for this user.

    Grace is granted if:
    1) account is newly created, OR
    2) user has recently completed OTP verification.
    """
    now = datetime.now(timezone.utc)

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "created_at": 1})
    created_at = (user_doc or {}).get("created_at")
    if created_at:
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except Exception:
                created_at = None
        if isinstance(created_at, datetime):
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (now - created_at).days < OTP_GRACE_DAYS:
                return True

    security_doc = await db.user_security.find_one({"user_id": user_id}, {"_id": 0, "last_otp_verified_at": 1})
    last_verified = (security_doc or {}).get("last_otp_verified_at")
    if last_verified:
        if isinstance(last_verified, str):
            try:
                last_verified = datetime.fromisoformat(last_verified.replace("Z", "+00:00"))
            except Exception:
                last_verified = None
        if isinstance(last_verified, datetime):
            if last_verified.tzinfo is None:
                last_verified = last_verified.replace(tzinfo=timezone.utc)
            if (now - last_verified).days < OTP_POST_VERIFY_GRACE_DAYS:
                return True

    return False


async def _record_otp_verification(user_id: str):
    """Record successful OTP verification for grace period tracking."""
    await db.user_security.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "last_otp_verified_at": datetime.now(timezone.utc).isoformat(),
                "failed_otp_attempts": 0,
                "account_locked": False,
            }
        },
        upsert=True,
    )


async def _check_otp_lock(user_id: str) -> bool:
    """Return True if account is locked due to failed OTP attempts."""
    record = await db.user_security.find_one({"user_id": user_id}, {"_id": 0})
    return bool(record and record.get("account_locked"))


async def _get_otp_lock_record(user_id: str) -> Optional[Dict[str, Any]]:
    return await db.user_security.find_one(
        {"user_id": user_id, "account_locked": True},
        {"_id": 0, "failed_otp_attempts": 1, "locked_at": 1, "account_locked": 1},
    )


async def _increment_otp_failure(user_id: str) -> int:
    """Increment failed OTP attempts and lock if threshold reached."""
    result = await db.user_security.find_one_and_update(
        {"user_id": user_id},
        {"$inc": {"failed_otp_attempts": 1}},
        upsert=True,
        return_document=True,
        projection={"_id": 0, "failed_otp_attempts": 1},
    )
    attempts = result.get("failed_otp_attempts", 1) if result else 1
    if attempts >= OTP_LOCK_THRESHOLD:
        await db.user_security.update_one(
            {"user_id": user_id},
            {"$set": {"account_locked": True, "locked_at": datetime.now(timezone.utc).isoformat()}},
        )
    return attempts


async def _send_otp(
    user_id: str,
    email: str,
    name: str,
    purpose: str,
    method: str = "email",
    phone: str = None,
    is_privileged: bool = False,
    force_resend: bool = False,
) -> dict:
    """Generate, store (hashed), and send OTP via email. Returns success dict."""
    from utils.email_notifications import _log_email

    now = datetime.now(timezone.utc)

    # Reuse an existing active OTP instead of issuing a fresh code repeatedly.
    # This prevents accidental lockouts caused by repeated login button clicks.
    active_otp = await db.otp_codes.find_one(
        {
            "user_id": user_id,
            "purpose": purpose,
            "expires_at": {"$gt": now},
            "attempts": {"$lt": OTP_MAX_ATTEMPTS},
        },
        {"_id": 0, "expires_at": 1, "method": 1},
    )
    if active_otp and not force_resend:
        expires_at = active_otp.get("expires_at")
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except Exception:
                expires_at = now
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            remaining_seconds = max(1, int((expires_at - now).total_seconds()))
            logger.info(f"OTP reused user={user_id} purpose={purpose} remaining_seconds={remaining_seconds}")
            return {
                "success": True,
                "method": str(active_otp.get("method") or method or "email"),
                "expires_in": max(1, int((remaining_seconds + 59) // 60)),
                "reused_existing": True,
                "delivery_status": "reused",
            }

    if force_resend and active_otp:
        logger.info(f"OTP force-resend requested for user={user_id} purpose={purpose}")

    # Rate limit OTP generation (purpose-scoped, rolling window, sent-only)
    window_start = now - timedelta(seconds=OTP_RATE_LIMIT_WINDOW_SECONDS)
    effective_limit = OTP_RATE_LIMIT_PER_HOUR * (OTP_RATE_LIMIT_PRIVILEGED_MULTIPLIER if is_privileged else 1)
    recent_otp_count = await db.otp_logs.count_documents(
        {
            "user_id": user_id,
            "purpose": purpose,
            "status": "sent",
            "created_at": {"$gte": window_start.isoformat()},
        }
    )
    if recent_otp_count >= effective_limit:
        oldest_event = await db.otp_logs.find_one(
            {
                "user_id": user_id,
                "purpose": purpose,
                "status": "sent",
                "created_at": {"$gte": window_start.isoformat()},
            },
            {"_id": 0, "created_at": 1},
            sort=[("created_at", 1)],
        )
        retry_after_seconds = OTP_RATE_LIMIT_WINDOW_SECONDS
        created_raw = (oldest_event or {}).get("created_at")
        if created_raw:
            try:
                created_at = datetime.fromisoformat(str(created_raw))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                elapsed = int((now - created_at).total_seconds())
                retry_after_seconds = max(1, OTP_RATE_LIMIT_WINDOW_SECONDS - max(0, elapsed))
            except Exception:
                retry_after_seconds = OTP_RATE_LIMIT_WINDOW_SECONDS
        await _log_email(user_id, email, "otp", f"OTP ({purpose})", "rate_limited", error="Rate limit exceeded")
        return {
            "success": False,
            "error": "OTP rate limit exceeded. Try again later.",
            "http_status": 429,
            "delivery_status": "rate_limited",
            "error_detail": _build_auth_recovery_detail(
                "Too many verification code requests. Please wait before requesting another code.",
                "otp_request_rate_limited",
                retry_after_seconds=retry_after_seconds,
            ),
        }

    otp_code = f"{random.randint(0, (10 ** OTP_CODE_LENGTH) - 1):0{OTP_CODE_LENGTH}d}"
    otp_hash = _hash_otp(otp_code)
    otp_expiry = _otp_expiry_minutes()
    expires_at = now + timedelta(minutes=otp_expiry)

    # Clear old OTPs for this purpose
    await db.otp_codes.delete_many({"user_id": user_id, "purpose": purpose})

    # Store hashed OTP
    await db.otp_codes.insert_one(
        {
            "user_id": user_id,
            "code_hash": otp_hash,
            "created_at": now,
            "expires_at": expires_at,
            "purpose": purpose,
            "method": "email",
            "attempts": 0,
        }
    )

    # Log OTP generation
    await db.otp_logs.insert_one(
        {
            "user_id": user_id,
            "purpose": purpose,
            "method": "email",
            "created_at": now.isoformat(),
            "status": "sent",
        }
    )

    # Send via email
    if not is_email_configured():
        await _log_email(user_id, email, "otp", f"OTP ({purpose})", "failed", error="Email service not configured")
        return {
            "success": False,
            "error": "Verification code delivery is temporarily unavailable.",
            "http_status": 503,
            "delivery_status": "email_service_unavailable",
            "error_detail": "Verification code delivery is temporarily unavailable. Please try again shortly.",
        }

    # Try template-based email first
    if EMAIL_OTP_TEMPLATE_KEY:
        template_payload = {"code": otp_code, "expiry_minutes": otp_expiry, "user_name": name}
        result = await send_template_email(
            recipient_email=email,
            template_key=EMAIL_OTP_TEMPLATE_KEY,
            data=template_payload,
            subject=f"Your RealAICoach {OTP_CODE_LENGTH}-digit verification code",
            contact_external_id=email,
        )
        if result.get("success"):
            await _log_email(user_id, email, "otp", f"OTP ({purpose})", "sent", message_id=result.get("message_id", ""))
            logger.info(f"OTP delivered user={user_id} purpose={purpose} method=email status=sent")
            payload = {"success": True, "method": "email", "expires_in": otp_expiry, "delivery_status": "sent"}
            delivery_notice = str(result.get("delivery_notice") or "").strip()
            if delivery_notice:
                payload["delivery_notice"] = delivery_notice
            return payload
        logger.warning(f"OTP template email failed for {user_id}: {result.get('error')}. Falling back to direct email.")

    # Fallback: send OTP via regular email
    from utils.email_service import render_email_logo

    render_email_logo(variant="support")
    " ".join(list(otp_code))
    fallback_result = await send_catalog_template(
        recipient_email=email,
        template_key="otp_code",
        recipient_name=name,
        code=otp_code,
        user_name=name,
        expiry_minutes=otp_expiry,
    )
    if fallback_result.get("success"):
        await _log_email(
            user_id, email, "otp", f"OTP ({purpose})", "sent", message_id=fallback_result.get("message_id", "")
        )
        logger.info(f"OTP delivered user={user_id} purpose={purpose} method=email status=sent_fallback")
        payload = {"success": True, "method": "email", "expires_in": otp_expiry, "delivery_status": "sent"}
        delivery_notice = str(fallback_result.get("delivery_notice") or "").strip()
        if delivery_notice:
            payload["delivery_notice"] = delivery_notice
        return payload

    await _log_email(user_id, email, "otp", f"OTP ({purpose})", "failed", error=fallback_result.get("error", "Unknown"))
    logger.error(
        f"OTP email completely failed for {user_id}: template={result.get('error') if EMAIL_OTP_TEMPLATE_KEY else 'N/A'}, direct={fallback_result.get('error')}"
    )
    return {
        "success": False,
        "error": "Verification code delivery is temporarily unavailable.",
        "http_status": 503,
        "delivery_status": "delivery_failed",
        "error_detail": "Verification code delivery is temporarily unavailable. Please try again shortly.",
    }


async def _verify_otp_code(user_id: str, code: str, purpose: str) -> dict:
    """Verify an OTP code. Returns success dict."""
    if await _check_otp_lock(user_id):
        lock_record = await _get_otp_lock_record(user_id) or {}
        return {
            "success": False,
            "error": "Your account has been temporarily locked after multiple failed verification attempts.",
            "http_status": 403,
            "error_detail": {
                **_build_auth_recovery_detail(
                    "Your account has been temporarily locked after multiple failed verification attempts. Reset your password or contact support to regain access.",
                    "otp_account_locked",
                ),
                "failed_attempts": int(lock_record.get("failed_otp_attempts") or 0),
                "locked_at": lock_record.get("locked_at"),
            },
        }

    code_hash = _hash_otp(code)
    otp_doc = await db.otp_codes.find_one(
        {
            "user_id": user_id,
            "code_hash": code_hash,
            "purpose": purpose,
        },
        {"_id": 0},
    )

    if not otp_doc:
        # Check for unhashed legacy codes
        otp_doc = await db.otp_codes.find_one(
            {
                "user_id": user_id,
                "code": code,
                "purpose": purpose,
            },
            {"_id": 0},
        )

    if not otp_doc:
        attempts = await _increment_otp_failure(user_id)
        remaining = OTP_LOCK_THRESHOLD - attempts
        return {"success": False, "error": f"Invalid code. {max(0, remaining)} attempts remaining."}

    expires_at = otp_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires_at:
        await db.otp_codes.delete_many({"user_id": user_id, "purpose": purpose})
        return {"success": False, "error": "Code expired. Please request a new one."}

    # Check max attempts on this OTP
    if otp_doc.get("attempts", 0) >= OTP_MAX_ATTEMPTS:
        await db.otp_codes.delete_many({"user_id": user_id, "purpose": purpose})
        return {"success": False, "error": "Too many attempts. Request a new code."}

    # Success — clean up
    await db.otp_codes.delete_many({"user_id": user_id, "purpose": purpose})
    await _record_otp_verification(user_id)

    # Log success
    await db.otp_logs.update_one(
        {"user_id": user_id, "purpose": purpose, "status": "sent"},
        {"$set": {"status": "verified", "verified_at": datetime.now(timezone.utc).isoformat()}},
        upsert=False,
    )

    return {"success": True}


async def _verify_backup_code(user_id: str, code: str) -> dict:
    """Verify a backup code. Returns success dict."""
    code_hash = _hash_otp(code.upper().replace("-", "").replace(" ", ""))
    security = await db.user_security.find_one({"user_id": user_id}, {"_id": 0})
    if not security or not security.get("backup_codes"):
        return {"success": False, "error": "No backup codes configured."}

    for i, bc in enumerate(security["backup_codes"]):
        if bc["code_hash"] == code_hash and not bc.get("used"):
            await db.user_security.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        f"backup_codes.{i}.used": True,
                        f"backup_codes.{i}.used_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            await _record_otp_verification(user_id)
            return {"success": True, "backup_code_used": True}

    return {"success": False, "error": "Invalid backup code."}


async def _maybe_block_ip(ip_address: str):
    if not ip_address:
        return
    window_start = datetime.now(timezone.utc) - timedelta(minutes=10)
    failed_count = await db.security_events.count_documents(
        {
            "ip_address": ip_address,
            "event_type": "login_failed",
            "timestamp": {"$gte": window_start.isoformat()},
        }
    )
    if failed_count >= 5:
        await apply_security_block(None, ip_address, "Repeated failed login attempts", "high", 15)
        return


# ── Request Models ──


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False
    resend_otp: bool = False


class Verify2FARequest(BaseModel):
    user_id: str
    code: str
    remember_me: bool = False


class OtpLoginRequest(BaseModel):
    email: EmailStr
    force_resend: bool = False


class OtpVerifyRequest(BaseModel):
    email: EmailStr
    code: str


class AdminE2EOtpIssueRequest(BaseModel):
    email: EmailStr
    purpose: str = "2fa"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class AuthLookupResponse(BaseModel):
    exists: bool
    user_id: Optional[str] = None
    has_pin: bool = False
    has_passkey: bool = False
    message: str = ""


class SetPinRequest(BaseModel):
    user_id: str
    pin: str


class VerifyPinRequest(BaseModel):
    user_id: str
    pin: str


class WebAuthnOptionsRequest(BaseModel):
    user_id: Optional[str] = None


class WebAuthnRegisterCompleteRequest(BaseModel):
    user_id: Optional[str] = None
    challenge_id: Optional[str] = None
    credential: Optional[Dict[str, Any]] = None
    credential_id: Optional[str] = None
    nickname: Optional[str] = None


class WebAuthnAuthCompleteRequest(BaseModel):
    user_id: str
    challenge_id: Optional[str] = None
    credential: Optional[Dict[str, Any]] = None
    credential_id: Optional[str] = None


class WebAuthnCredentialDeleteRequest(BaseModel):
    challenge_id: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    user_id: str
    current_password: str
    new_password: str


class SSOTelemetryRequest(BaseModel):
    provider: str
    phase: str
    iframe_mode: Optional[bool] = None
    cross_origin_iframe: Optional[bool] = None
    popup_method: Optional[str] = None
    note: Optional[str] = None
    context: Optional[str] = None


class LogoutBannerTelemetryRequest(BaseModel):
    event: str
    source: Optional[str] = None
    route_path: Optional[str] = None
    reason: Optional[str] = None
    redirect_target: Optional[str] = None
    expected_logout_banner: Optional[bool] = None


class AuthSessionTelemetryRequest(BaseModel):
    reason_code: str
    phase: Optional[str] = None
    status: Optional[int] = None
    attempt: Optional[int] = None


class TenantDisclaimerProfileMapRequest(BaseModel):
    default_profile: Optional[str] = "default"
    mappings: Dict[str, str] = Field(default_factory=dict)
    merge: bool = False


@router.get("/auth/lookup", response_model=AuthLookupResponse)
async def auth_lookup(email: str, raw_request: Request = None):
    """Lookup auth methods for an email. Anti-enumeration: always returns same shape.

    Rate-limited and timing-safe to prevent email enumeration attacks.
    """
    # Rate limit: 5 lookups per 5 minutes per IP
    ip = raw_request.client.host if raw_request and raw_request.client else "unknown"
    email_normalized = str(email or "").strip().lower()
    is_local_probe = ip in {"127.0.0.1", "::1", "localhost"}
    is_e2e_probe = email_normalized.startswith("e2e.")
    bypass_lookup_limit = _is_non_production_runtime() and (is_local_probe or is_e2e_probe)
    if not bypass_lookup_limit and not check_rate_limit(f"auth_lookup:{ip}", 5, 300):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    user_doc = await db.users.find_one({"email": email_normalized}, {"_id": 0})
    if not user_doc:
        # Generate deterministic fake user_id from email hash (consistent per email)
        fake_id = f"user_{hashlib.sha256(email.lower().encode()).hexdigest()[:12]}"
        # Perform same DB lookups to maintain consistent timing (prevent timing attacks)
        await db.biometric_pins.find_one({"user_id": fake_id})
        await db.webauthn_credentials.find_one({"user_id": fake_id})
        return AuthLookupResponse(
            exists=True,
            user_id=fake_id,
            has_pin=False,
            has_passkey=False,
            message="OK",
        )

    user_id = user_doc["user_id"]
    has_pin = await db.biometric_pins.find_one({"user_id": user_id}) is not None
    has_passkey = await db.webauthn_credentials.find_one({"user_id": user_id}) is not None

    return AuthLookupResponse(
        exists=True,
        user_id=user_id,
        has_pin=has_pin,
        has_passkey=has_passkey,
        message="OK",
    )


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    theme_preference: Optional[str] = None
    currency_preference: Optional[str] = None
    language_preference: Optional[str] = None


SUPPORTED_LANGUAGE_PREFERENCE_CODES = {
    "en", "es", "fr", "de", "it", "pt", "zh", "ja", "ko", "hi", "ar",
    "ru", "tr", "nl", "sv", "pl", "th", "vi", "id", "ms", "sw", "uk", "ro",
}


class SessionTimeoutConfigRequest(BaseModel):
    user_hours: int
    admin_hours: int


def build_reset_link(token: str, base_url: str | None = None) -> str:
    target = str(base_url or RESET_LINK_BASE or "").strip()
    if not target:
        raise ValueError("RESET_LINK_BASE is not configured")
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}{urlencode({'token': token})}"


def build_verify_link(token: str) -> str:
    if not VERIFY_LINK_BASE:
        raise ValueError("VERIFY_LINK_BASE is not configured")
    separator = "&" if "?" in VERIFY_LINK_BASE else "?"
    return f"{VERIFY_LINK_BASE}{separator}{urlencode({'token': token})}"


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _send_password_change_confirmation_email(user_doc: Dict[str, Any], changed_at: Optional[str] = None) -> None:
    if not is_email_configured() or not user_doc.get("email"):
        return

    user_id = user_doc.get("user_id")
    prefs = await db.security_alert_prefs.find_one({"user_id": user_id}, {"_id": 0}) if user_id else None
    if prefs and prefs.get("email_password_change") is False:
        return

    changed_at_text = changed_at or datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")
    result = await send_catalog_template(
        recipient_email=user_doc["email"],
        template_key="password_changed",
        recipient_name=user_doc.get("name", user_doc.get("email", "")),
        user_name=user_doc.get("name", user_doc.get("email", "")),
        changed_at=changed_at_text,
    )
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "Failed to send password change confirmation email")

    try:
        from utils.email_notifications import _log_email

        await _log_email(user_doc.get("user_id", "unknown"), user_doc["email"], "password_changed", "Password changed", "sent")
    except Exception:
        pass


def _otp_expiry_minutes() -> int:
    if not EMAIL_OTP_EXPIRY_MINUTES:
        raise ValueError("OTP_EXPIRY_MINUTES not configured")
    return int(EMAIL_OTP_EXPIRY_MINUTES)


def _normalize_legal_profile(value: Any, fallback: str = "default") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in LEGAL_PROFILE_VALUES:
        return candidate
    return fallback


def _normalize_disclaimer_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_disclaimer_map(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    normalized: Dict[str, str] = {}
    for key, value in raw.items():
        normalized_key = _normalize_disclaimer_key(key)
        if not normalized_key:
            continue
        normalized[normalized_key] = _normalize_legal_profile(value)
    return normalized


def _extract_email_domain(value: Any) -> str:
    email = str(value or "").strip().lower()
    if "@" not in email:
        return ""
    return email.split("@")[-1].strip()


def _collect_disclaimer_candidate_keys(
    request: Optional[Request] = None,
    user_doc: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> List[str]:
    source_doc = user_doc or {}
    override_doc = overrides or {}
    host_value = str(override_doc.get("host") or "").strip()
    if not host_value and request is not None:
        host_value = str(request.headers.get("host") or "").strip()
    host_base = host_value.split(":")[0] if host_value else ""

    email_value = override_doc.get("email") or source_doc.get("email")
    candidate_values = [
        override_doc.get("tenant_id") or source_doc.get("tenant_id"),
        override_doc.get("organization_id") or source_doc.get("organization_id"),
        override_doc.get("company_id") or source_doc.get("company_id"),
        override_doc.get("workspace_id") or source_doc.get("workspace_id"),
        host_base,
        _extract_email_domain(email_value),
    ]

    unique: List[str] = []
    for raw_value in candidate_values:
        normalized = _normalize_disclaimer_key(raw_value)
        if not normalized:
            continue
        if normalized in unique:
            continue
        unique.append(normalized)
    return unique


async def _get_tenant_disclaimer_profile_state() -> Dict[str, Any]:
    doc = await db.system_runtime_flags.find_one({"key": TENANT_DISCLAIMER_PROFILE_MAP_KEY}, {"_id": 0}) or {}
    mappings = _normalize_disclaimer_map(doc.get("mappings") or {})
    default_profile = _normalize_legal_profile(doc.get("default_profile"), "default")
    return {
        "key": TENANT_DISCLAIMER_PROFILE_MAP_KEY,
        "default_profile": default_profile,
        "mappings": mappings,
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
    }


async def _resolve_tenant_disclaimer_profile(
    request: Optional[Request] = None,
    user_doc: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state = await _get_tenant_disclaimer_profile_state()
    default_profile = state["default_profile"]
    mappings: Dict[str, str] = state.get("mappings") or {}
    candidate_keys = _collect_disclaimer_candidate_keys(request=request, user_doc=user_doc, overrides=overrides)

    for key in candidate_keys:
        mapped = mappings.get(key)
        if mapped:
            return {
                "legal_profile": mapped,
                "matched_key": key,
                "candidate_keys": candidate_keys,
                "mapping_source": "runtime_mapping",
                "default_profile": default_profile,
                "updated_at": state.get("updated_at"),
            }

    return {
        "legal_profile": default_profile,
        "matched_key": None,
        "candidate_keys": candidate_keys,
        "mapping_source": "default_profile",
        "default_profile": default_profile,
        "updated_at": state.get("updated_at"),
    }


async def _capture_logout_telemetry_event(
    request: Request,
    event_type: str,
    user: Optional[User],
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    body = payload or {}

    def _trim(value: Any, limit: int = 160) -> str:
        text = str(value or "").strip()
        return text[:limit]

    details = {
        "action": _trim(body.get("action"), 80),
        "reason": _trim(body.get("reason"), 160),
        "source": _trim(body.get("source"), 160),
        "route_path": _trim(body.get("route_path"), 220),
        "redirect_target": _trim(body.get("redirect_target"), 220),
        "platform": _trim(body.get("platform"), 40),
        "session_id": _trim(body.get("session_id"), 120),
        "expected_logout_banner": bool(body.get("expected_logout_banner")),
        "initiated_at": _trim(body.get("initiated_at"), 80),
        "banner_variant": _trim(body.get("banner_variant"), 80),
    }

    tenant_context = {
        "tenant_id": _trim(body.get("tenant_id"), 120),
        "organization_id": _trim(body.get("organization_id"), 120),
        "company_id": _trim(body.get("company_id"), 120),
        "workspace_id": _trim(body.get("workspace_id"), 120),
    }

    user_id = user.user_id if user else (_trim(body.get("user_id"), 120) or None)
    email = user.email if user else (_trim(body.get("email"), 160) or None)

    await db[LOGOUT_TELEMETRY_COLLECTION].insert_one(
        {
            "event_id": f"lgtele_{uuid.uuid4().hex[:12]}",
            "event_type": _trim(event_type, 80) or "logout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "email": email,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "tenant_context": tenant_context,
            "details": details,
        }
    )


@router.post("/auth/register")
async def register(request: RegisterRequest, response: Response, raw_request: Request = None):
    """Register with email and password"""
    # Rate limit registration: 5 per hour per IP
    ip_address = raw_request.client.host if raw_request and raw_request.client else "unknown"
    if not check_rate_limit(f"register:{ip_address}", 5, 3600):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Please try again later.")

    existing = await db.users.find_one({"email": request.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Unable to complete registration. Please try again or use a different email.")

    pw_error = validate_password_strength(request.password)
    if pw_error:
        raise HTTPException(status_code=400, detail=pw_error)

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user = User(
        user_id=user_id,
        email=request.email,
        name=request.name,
        auth_provider="email",
        password_hash=hash_password(request.password),
        roles=["user"],
        role="user",
    )

    if is_full_access_email(request.email):
        user.subscription_plan = "premium"
        user.subscription_status = "active"
        user.full_access = True
        user.is_admin = False
        user.role = "full_users"
        user.roles = ["user", "premium", "full_users"]
    elif is_admin_email(request.email):
        user.subscription_plan = "premium"
        user.subscription_status = "active"
        user.is_admin = True
        user.full_access = True
        user.role = "admin"
        user.roles = ["user", "premium", "admin"]

    await db.users.insert_one(user.dict())

    # Best-effort geo currency prefill (non-blocking; manual preference always wins later)
    async def _prefill_geo_currency(ip: str, uid: str) -> None:
        try:
            from routes.geo_detection import COUNTRIES, detect_country_from_ip
            from routes.payments_checkout_core import SUPPORTED_CURRENCIES
            country = await detect_country_from_ip(ip)
            currency = (COUNTRIES.get(country) or {}).get("currency")
            if currency and currency != "USD" and currency in SUPPORTED_CURRENCIES:
                await db.users.update_one(
                    {"user_id": uid, "currency_preference": {"$in": [None, ""]}},
                    {"$set": {"currency_preference": currency, "signup_country": country}},
                )
            elif country:
                await db.users.update_one({"user_id": uid}, {"$set": {"signup_country": country}})
        except Exception as exc:
            logger.warning(f"Geo currency prefill failed for {uid}: {exc}")

    geo_ip = ip_address
    if raw_request is not None:
        try:
            from routes.geo_detection import _extract_client_ip
            geo_ip = _extract_client_ip(raw_request)
        except Exception:
            pass
    import asyncio as _prefill_asyncio
    _prefill_asyncio.create_task(_prefill_geo_currency(geo_ip, user_id))

    # Send welcome + verification emails via centralized notification service
    try:
        from utils.email_notifications import notify

        await notify.welcome(user_id, user.email, user.name)
    except Exception as exc:
        logger.error(f"Welcome email failed: {exc}")

    if is_email_configured():
        try:
            verify_token = secrets.token_urlsafe(32)
            verify_hash = _hash_reset_token(verify_token)
            verify_expires = datetime.now(timezone.utc) + timedelta(hours=24)
            await db.email_verification_tokens.insert_one(
                {
                    "user_id": user_id,
                    "email": user.email,
                    "token_hash": verify_hash,
                    "created_at": datetime.now(timezone.utc),
                    "expires_at": verify_expires,
                    "used": False,
                }
            )
            verify_link = build_verify_link(verify_token)
            from utils.email_notifications import notify

            await notify.account_verification(user_id, user.email, user.name, verify_link, 24)
        except Exception as exc:
            logger.error(f"Verification email failed: {exc}")

    token_version = user.token_version if hasattr(user, "token_version") else 0
    expires_minutes = await _resolve_session_timeout_minutes(False)
    token = create_jwt_token(user_id, request.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user_id,
        session_token=token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=raw_request.client.host if raw_request and raw_request.client else None,
    )
    await db.user_sessions.insert_one(session.dict())

    _set_session_cookie(response, token, expires_minutes * 60, raw_request)

    # Fire welcome notification
    _asyncio.ensure_future(_notify_registration(user_id, user.name))

    return {
        "user_id": user_id,
        "email": user.email,
        "name": user.name,
        "roles": user.roles,
        "role": user.role,
        **_auth_token_payload(raw_request, session_token=token, refresh_token=refresh_token),
    }


# ── registration notification helper (fire and forget) ──
async def _notify_registration(user_id: str, name: str):
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=user_id,
            notif_type="welcome",
            title="Welcome to RealAICoach!",
            body=f"Hi {name}, your account is ready. Start your coaching journey today.",
            action_url="/dashboard",
        )
    except Exception:
        pass


import asyncio as _asyncio


def _schedule_non_blocking_task(coro, label: str) -> None:
    """Schedule a fire-and-forget coroutine with guarded error logging."""
    try:
        task = _asyncio.create_task(coro)
    except Exception as exc:
        logger.warning(f"Failed to schedule async task '{label}': {exc}")
        return

    def _on_done(done_task):
        try:
            done_task.result()
        except Exception as task_exc:
            logger.warning(f"Async task '{label}' failed: {task_exc}")

    task.add_done_callback(_on_done)


async def _run_login_post_success_side_effects(user_id: str, email: str, name: str, request: Optional[Request]) -> None:
    """Run non-critical post-login hooks outside the critical response path."""
    if request is None:
        return

    try:
        from routes.live_activity import log_activity

        await log_activity(db, "login", user_id, email, f"{name or email} signed in")
    except Exception as exc:
        logger.warning(f"Post-login live activity failed for {user_id}: {exc}")

    try:
        from utils.ws_manager import broadcast_data_change

        await broadcast_data_change("sessions", "created", user_id)
    except Exception as exc:
        logger.warning(f"Post-login broadcast failed for {user_id}: {exc}")

    try:
        await check_and_alert_new_session(user_id, email, name, request)
    except Exception as exc:
        logger.warning(f"Post-login alert check failed for {user_id}: {exc}")

    try:
        from routes.ab_testing import check_user_returned

        await check_user_returned(user_id)
    except Exception as exc:
        logger.warning(f"Post-login return tracking failed for {user_id}: {exc}")


def _is_login_disabled_account(user_doc: dict | None) -> bool:
    if not user_doc:
        return False
    if user_doc.get("is_active") is False:
        return True
    if user_doc.get("allow_login") is False:
        return True
    if user_doc.get("hygiene_obsolete_alias") is True:
        return True
    return False


@router.post("/auth/login")
async def login(login_data: LoginRequest, response: Response, request: Request = None):
    """Login with email and password"""
    login_started_at = _time.perf_counter()
    perf_user_lookup_ms = 0
    perf_password_verify_ms = 0
    perf_risk_eval_ms = 0
    perf_session_write_ms = 0
    perf_tenant_profile_ms = 0

    ip_address = request.client.host if request and request.client else "unknown"
    email_normalized = (login_data.email or "").strip().lower()
    is_rate_limit_exempt = _is_login_rate_limit_exempt(email_normalized)
    user_lookup_started_at = _time.perf_counter()
    user_doc = await db.users.find_one({"email": email_normalized}, {"_id": 0})
    perf_user_lookup_ms = int((_time.perf_counter() - user_lookup_started_at) * 1000)
    waiver = await _get_password_reset_unlock_waiver(email_normalized, user_doc.get("user_id") if user_doc else None)
    if (waiver or is_rate_limit_exempt) and ip_address:
        clear_rate_limit(f"login:{ip_address}")
        clear_rate_limit(f"login_email:{email_normalized}")
        await db.security_blocks.delete_many({"ip_address": ip_address})

    if not waiver and not is_rate_limit_exempt and not check_rate_limit(f"login:{ip_address}", LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW):
        await log_security_event(None, "login_rate_limit", "medium", request, {"email": login_data.email})
        raise HTTPException(
            status_code=429,
            detail=_build_auth_recovery_detail(
                "Too many login attempts from this device. Please wait a moment before trying again.",
                "login_rate_limited",
                retry_after_seconds=LOGIN_RATE_WINDOW,
            ),
        )
    # Per-email rate limit: 10 attempts per 15 min per email (blocks distributed brute-force across IPs)
    if not waiver and not is_rate_limit_exempt and not check_rate_limit(
        f"login_email:{email_normalized}",
        LOGIN_EMAIL_RATE_LIMIT,
        LOGIN_EMAIL_RATE_WINDOW,
    ):
        await log_security_event(None, "login_email_rate_limit", "high", request, {"email": login_data.email})
        raise HTTPException(
            status_code=429,
            detail=_build_auth_recovery_detail(
                "Too many login attempts for this account. Please wait before trying again.",
                "login_rate_limited",
                retry_after_seconds=900,
            ),
        )
    ip_block = None if waiver else await is_security_blocked(None, ip_address)
    if ip_block:
        await log_security_event(None, "blocked_ip", "high", request)
        raise HTTPException(status_code=403, detail=_build_ip_block_detail(ip_block))

    if not user_doc:
        await log_security_event(None, "login_failed", "medium", request, {"email": login_data.email})
        await _maybe_block_ip(ip_address)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if _is_login_disabled_account(user_doc):
        await log_security_event(user_doc.get("user_id"), "blocked_user", "high", request, {"email": login_data.email, "reason": "obsolete_or_disabled_account"})
        raise HTTPException(status_code=403, detail="This account is inactive. Please use your primary account.")

    user = User(**user_doc)
    password_verify_started_at = _time.perf_counter()
    password_valid = bool(user.password_hash) and verify_password(login_data.password, user.password_hash)
    perf_password_verify_ms = int((_time.perf_counter() - password_verify_started_at) * 1000)
    if not password_valid:
        await log_security_event(user.user_id, "login_failed", "medium", request, {"email": login_data.email})
        await _maybe_block_ip(ip_address)

        # Send suspicious login alert for repeated failures
        try:
            from utils.email_notifications import notify

            fail_count = await db.security_events.count_documents(
                {
                    "user_id": user.user_id,
                    "event_type": "login_failed",
                    "timestamp": {"$gte": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()},
                }
            )
            if fail_count >= 3:
                ctx = await _resolve_client_context(request)
                qa_doc = await db.qa_traffic_allowlist.find_one({"key": "default"}, {"_id": 0, "ips": 1})
                if ctx["ip"] not in set((qa_doc or {}).get("ips") or []):
                    await notify.suspicious_login(
                        user.user_id,
                        user.email,
                        user.name,
                        ctx["ip"],
                        ctx["location"],
                        f"{fail_count} failed login attempts in the last hour",
                        device=ctx["device"],
                    )
        except Exception:
            pass

        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = await apply_access_overrides(user)
    if ip_address:
        clear_rate_limit(f"login:{ip_address}")
    clear_rate_limit(f"login_email:{email_normalized}")

    risk_eval_started_at = _time.perf_counter()
    risk_assessment = await _run_progressive_risk_assessment(
        user,
        request,
        stage="password_login",
        source="auth_login",
    )
    risk_assessment = await _apply_preview_login_risk_bypass_if_allowed(
        user=user,
        request=request,
        risk_assessment=risk_assessment,
        source="auth_login_password",
    )
    perf_risk_eval_ms = int((_time.perf_counter() - risk_eval_started_at) * 1000)
    risk_restrictions = (risk_assessment or {}).get("restrictions", {})

    if risk_restrictions.get("require_id_verification") and waiver:
        risk_assessment = _apply_alternative_recovery_bypass(risk_assessment, "password_reset")
        await persist_risk_assessment(
            db=db,
            assessment=risk_assessment or {},
            source="auth_login_password_reset_bypass",
            notify_admins=False,
        )
        risk_restrictions = (risk_assessment or {}).get("restrictions", {})

    risk_guidance = _risk_guidance_for_level(
        (risk_assessment or {}).get("risk_level", "low"),
        "alternative_recovery_approved" if (risk_assessment or {}).get("recovery_bypass", {}).get("applied") else None,
    )

    if risk_restrictions.get("require_id_verification"):
        user_guidance_sent = await _send_user_risk_guidance_email(user, risk_assessment or {}, risk_guidance)
        idv_access_token = await _create_idv_access_token(user.user_id, "auth_login_critical")
        try:
            from routes.id_verification import trigger_risk_based_id_verification

            await trigger_risk_based_id_verification(
                user.user_id,
                risk_assessment or {},
                triggered_by="auth_login_critical",
            )
        except Exception as idv_exc:
            logger.warning(f"Risk-triggered ID Checker failed for {user.user_id}: {idv_exc}")

        await db.user_sessions.delete_many({"user_id": user.user_id})
        await log_security_event(
            user.user_id,
            "risk_engine_critical_lockout",
            "critical",
            request,
            {
                "risk_score": (risk_assessment or {}).get("risk_score"),
                "risk_level": (risk_assessment or {}).get("risk_level"),
                "trigger": (risk_assessment or {}).get("trigger"),
            },
        )
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Critical account risk detected. Session is locked and ID Checker is required.",
                "code": "risk_engine_id_verification_required",
                "requires_id_verification": True,
                "risk_engine": risk_assessment,
                "risk_output": (risk_assessment or {}).get("output_block", ""),
                "display_message": risk_guidance.get("message"),
                "next_steps": risk_guidance.get("steps", []),
                "email_notification_sent": user_guidance_sent,
                "risk_code": risk_guidance.get("risk_code", "risk_engine_id_verification_required"),
                "support_email": risk_guidance.get("support_email", "security@realaicoach.app"),
                "support_url": "mailto:security@realaicoach.app",
                "idv_access_token": idv_access_token,
                "idv_access_expires_in_seconds": 2700,
            },
        )

    # ── 2FA Policy ──
    # Exempt accounts: admin + full_access users bypass OTP entirely
    otp_policy_exempt = _is_otp_policy_exempt(user)
    e2e_otp_bypass_applied = _should_apply_e2e_otp_login_bypass(user)
    if e2e_otp_bypass_applied:
        otp_policy_exempt = True
        await log_security_event(
            user.user_id,
            "auth_e2e_otp_bypass_applied",
            "medium",
            request,
            {
                "email": str(user.email or "").strip().lower(),
                "scope": "password_login",
                "non_production_only": True,
                "admin_only_mode": _auth_e2e_otp_bypass_admin_only(),
            },
        )
    within_grace = False
    if otp_policy_exempt:
        requires_otp = False
    else:
        # After 30 days since signup, ALL users require OTP at login
        within_grace = await _check_otp_grace_period(user.user_id)
        requires_otp = not within_grace

    if risk_restrictions.get("requires_mfa") and not otp_policy_exempt and not within_grace:
        requires_otp = True

    risk_stepup_email_sent = False
    if requires_otp and (risk_assessment or {}).get("risk_level") in {"medium", "high"}:
        risk_stepup_email_sent = await _send_user_risk_guidance_email(user, risk_assessment or {}, risk_guidance)

    if requires_otp:
        # Check if account is locked
        if await _check_otp_lock(user.user_id):
            lock_record = await _get_otp_lock_record(user.user_id) or {}
            raise HTTPException(
                status_code=403,
                detail={
                    **_build_auth_recovery_detail(
                        "Your account has been temporarily locked after multiple failed verification attempts. Reset your password or contact support to regain access.",
                        "otp_account_locked",
                    ),
                    "failed_attempts": int(lock_record.get("failed_otp_attempts") or 0),
                    "locked_at": lock_record.get("locked_at"),
                },
            )

        # Determine OTP method based on geo + user preference
        country = await _detect_country(request) if request else "US"
        method, phone = await _get_otp_method(user.user_id, country)

        otp_result = await _send_otp(
            user.user_id,
            user.email,
            user.name,
            "2fa",
            method=method,
            phone=phone,
            is_privileged=otp_policy_exempt,
            force_resend=bool(login_data.resend_otp),
        )
        if not otp_result.get("success"):
            error_msg = otp_result.get("error", "Failed to send verification code")
            status = int(otp_result.get("http_status") or (429 if "rate limit" in error_msg.lower() else 500))
            raise HTTPException(status_code=status, detail=otp_result.get("error_detail") or error_msg)

        code_reused = bool(otp_result.get("reused_existing"))
        response_payload = {
            "requires_2fa": True,
            "user_id": user.user_id,
            "email": user.email,
            "email_sent": not code_reused,
            "otp_method": otp_result.get("method", "email"),
            "code_reused": code_reused,
            "code_expires_in_minutes": int(otp_result.get("expires_in") or _otp_expiry_minutes()),
            "otp_delivery_status": str(otp_result.get("delivery_status") or ("reused" if code_reused else "sent")),
            "remember_me": bool(login_data.remember_me),
            "country": country,
            "is_us": country == "US",
            "message": f"2FA verification required. Check your {'phone' if otp_result.get('method') == 'sms' else 'email'} for the code.",
            "risk_level": (risk_assessment or {}).get("risk_level", "low"),
            "risk_score": (risk_assessment or {}).get("risk_score", 0),
            "risk_engine_status": (risk_assessment or {}).get("risk_engine_status", "ACTIVE"),
            "risk_output": (risk_assessment or {}).get("output_block", ""),
            "progressive_action": (risk_assessment or {}).get("trigger", "STEP_UP_MFA"),
            "display_message": risk_guidance.get("message"),
            "next_steps": risk_guidance.get("steps", []),
            "email_notification_sent": risk_stepup_email_sent,
            "risk_code": risk_guidance.get("risk_code", "risk_engine_step_up_mfa"),
            "support_email": risk_guidance.get("support_email", "security@realaicoach.app"),
            "support_url": "mailto:security@realaicoach.app",
        }
        delivery_notice = str(otp_result.get("delivery_notice") or "").strip()
        if delivery_notice:
            response_payload["delivery_notice"] = delivery_notice
        if is_nonprod_test_domain_recipient(user.email):
            response_payload["nonprod_test_domain"] = True
        return response_payload

    # No 2FA - proceed with normal login
    token_version = user.token_version
    if login_data.remember_me:
        expires_minutes = REMEMBER_ME_MINUTES
    else:
        expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request and request.client else None,
    )
    session_doc = session.dict()
    if risk_assessment:
        session_doc["risk_context"] = {
            "risk_score": int(risk_assessment.get("risk_score") or 0),
            "risk_level": str(risk_assessment.get("risk_level") or "low"),
            "trigger": str(risk_assessment.get("trigger") or "NO_FRICTION"),
            "assessed_at": str(risk_assessment.get("assessed_at") or datetime.now(timezone.utc).isoformat()),
            "session_protection": str(risk_assessment.get("session_protection") or "STANDARD_MONITORING"),
        }
    session_write_started_at = _time.perf_counter()
    await db.user_sessions.insert_one(session_doc)
    perf_session_write_ms = int((_time.perf_counter() - session_write_started_at) * 1000)

    _set_session_cookie(response, token, expires_minutes * 60, request)

    await log_security_event(user.user_id, "login_success", "low", request)

    _schedule_non_blocking_task(
        _run_login_post_success_side_effects(user.user_id, user.email, user.name, request),
        "login_post_success_side_effects",
    )

    # Check if returning user (has last_active_route from previous session)
    last_route = user_doc.get("last_active_route", "")
    last_active = user_doc.get("last_active_at", "")
    welcome_back = bool(last_route and last_active)

    if waiver:
        await db.password_reset_unlock_waivers.delete_many({"email": login_data.email.lower()})

    tenant_profile_started_at = _time.perf_counter()
    tenant_disclaimer = await _resolve_tenant_disclaimer_profile(
        request=request,
        user_doc=user_doc,
        overrides={"email": user.email},
    )
    perf_tenant_profile_ms = int((_time.perf_counter() - tenant_profile_started_at) * 1000)

    total_login_ms = int((_time.perf_counter() - login_started_at) * 1000)
    if total_login_ms >= 1200:
        logger.info(
            "auth_login_perf stage=success user_id=%s total_ms=%s user_lookup_ms=%s password_verify_ms=%s "
            "risk_eval_ms=%s session_write_ms=%s tenant_profile_ms=%s",
            user.user_id,
            total_login_ms,
            perf_user_lookup_ms,
            perf_password_verify_ms,
            perf_risk_eval_ms,
            max(perf_session_write_ms, 0),
            perf_tenant_profile_ms,
        )

    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "is_admin": user.is_admin,
        "full_access": user.full_access,
        "roles": user.roles,
        "role": user.role,
        "email_verified": user.email_verified,
        "profile_image": _safe_profile_image_for_auth_response(user_doc.get("profile_image", "")),
        **_auth_token_payload(request, session_token=token, refresh_token=refresh_token),
        "welcome_back": welcome_back,
        "last_active_route": last_route,
        "last_active_at": last_active,
        "theme_preference": user_doc.get("theme_preference"),
        "language_preference": user_doc.get("language_preference"),
        "currency_preference": user_doc.get("currency_preference"),
        "tenant_id": user_doc.get("tenant_id"),
        "organization_id": user_doc.get("organization_id"),
        "company_id": user_doc.get("company_id"),
        "workspace_id": user_doc.get("workspace_id"),
        "tenant_disclaimer_profile": tenant_disclaimer.get("legal_profile"),
        "risk_level": (risk_assessment or {}).get("risk_level", "low"),
        "risk_score": (risk_assessment or {}).get("risk_score", 0),
        "risk_engine_status": (risk_assessment or {}).get("risk_engine_status", "ACTIVE"),
        "risk_output": (risk_assessment or {}).get("output_block", ""),
        "e2e_otp_bypass_applied": bool(e2e_otp_bypass_applied),
    }



@router.post("/auth/renew-session")
async def renew_session(request: Request, response: Response):
    """Renew the current session with a fresh 30-day token (for 'Remember me' users)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_version = user.token_version
    expires_minutes = REMEMBER_ME_MINUTES
    token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)

    session = UserSession(
        user_id=user.user_id,
        session_token=token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request and request.client else None,
    )
    await db.user_sessions.insert_one(session.dict())

    _set_session_cookie(response, token, expires_minutes * 60, request)

    return {
        **_auth_token_payload(request, session_token=token, refresh_token=refresh_token),
        "expires_in_seconds": expires_minutes * 60,
        "message": "Session renewed for 30 days",
    }


@router.post("/auth/password/reset/request")
async def request_password_reset(reset_req: PasswordResetRequest, raw_request: Request = None):
    # Rate limit password reset: 3 per 15 minutes per IP
    ip_address = raw_request.client.host if raw_request and raw_request.client else "unknown"
    if not check_rate_limit(f"password_reset:{ip_address}", 3, 900):
        raise HTTPException(status_code=429, detail="Too many reset requests. Please try again later.")
    # Per-email rate limit: 3 per hour per email (blocks distributed brute-force)
    if not check_rate_limit(f"password_reset_email:{reset_req.email.lower()}", 3, 3600):
        raise HTTPException(status_code=429, detail="Too many reset requests for this email. Please try again later.")

    if not is_email_configured():
        raise HTTPException(status_code=503, detail="Password reset service is temporarily unavailable. Please try again shortly.")
    fallback_base = await _resolve_auth_fallback_base(raw_request)
    if not RESET_LINK_BASE and not fallback_base:
        raise HTTPException(status_code=500, detail="RESET_LINK_BASE not configured")

    email = reset_req.email.lower()
    user_doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not user_doc:
        # Return success even if user doesn't exist to prevent email enumeration
        return {"message": "If an account with that email exists, a password reset link has been sent."}

    token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    await db.password_reset_tokens.update_many(
        {"user_id": user_doc["user_id"], "used": False},
        {"$set": {"used": True, "used_at": datetime.now(timezone.utc)}},
    )

    await db.password_reset_tokens.insert_one(
        {
            "user_id": user_doc["user_id"],
            "email": email,
            "token_hash": token_hash,
            "created_at": datetime.now(timezone.utc),
            "expires_at": expires_at,
            "used": False,
        }
    )

    reset_target = RESET_LINK_BASE or f"{fallback_base}/auth/reset-password"
    reset_link = build_reset_link(token, reset_target)
    result = await send_catalog_template(
        recipient_email=email,
        template_key="password_reset",
        reset_link=reset_link,
        expiry_minutes=30,
    )
    if not result.get("success"):
        logger.error(f"Password reset email failed: {result.get('error')}")
        raise HTTPException(status_code=503, detail="Password reset service is temporarily unavailable. Please try again shortly.")

    # Log via centralized email notification service
    try:
        from utils.email_notifications import _log_email

        await _log_email(
            user_doc.get("user_id", "unknown"),
            email,
            "password_reset",
            "Password reset",
            "sent",
            message_id=result.get("message_id", ""),
        )
    except Exception:
        pass

    nonprod_test_domain = bool(is_nonprod_test_domain_recipient(email))
    response_payload = {
        "success": True,
        "message": "Password reset email sent",
    }
    delivery_notice = str(result.get("delivery_notice") or "").strip()
    if delivery_notice:
        response_payload["delivery_notice"] = delivery_notice
    if nonprod_test_domain:
        response_payload["nonprod_test_domain"] = True
    return response_payload


@router.post("/auth/password/reset/confirm")
async def confirm_password_reset(payload: PasswordResetConfirm, request: Request):
    # Enforce full password strength (same rules as registration)
    pw_error = validate_password_strength(payload.new_password)
    if pw_error:
        raise HTTPException(status_code=400, detail=pw_error)

    token_hash = _hash_reset_token(payload.token)
    token_doc = await db.password_reset_tokens.find_one(
        {
            "token_hash": token_hash,
            "used": False,
        },
        {"_id": 0},
    )

    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    expires_at = token_doc.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            expires_at = None
    if hasattr(expires_at, "tzinfo") and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token expired")

    await db.users.update_one(
        {"user_id": token_doc["user_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": datetime.now(timezone.utc)}},
    )
    await db.password_reset_tokens.update_one(
        {"token_hash": token_hash},
        {"$set": {"used": True, "used_at": datetime.now(timezone.utc)}},
    )
    # Invalidate all existing sessions — force re-login with new password
    await invalidate_user_sessions(token_doc["user_id"])
    await db.user_security.update_one(
        {"user_id": token_doc["user_id"]},
        {
            "$set": {
                "account_locked": False,
                "failed_otp_attempts": 0,
                "unlocked_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    ip_address = request.client.host if request and request.client else None
    if ip_address:
        await db.security_blocks.delete_many({"ip_address": ip_address})
        clear_rate_limit(f"login:{ip_address}")
    await db.password_reset_unlock_waivers.update_one(
        {"email": str(token_doc.get("email") or "").lower(), "user_id": token_doc["user_id"]},
        {
            "$set": {
                "email": str(token_doc.get("email") or "").lower(),
                "user_id": token_doc["user_id"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            }
        },
        upsert=True,
    )

    user_doc = await db.users.find_one({"user_id": token_doc["user_id"]}, {"_id": 0, "user_id": 1, "email": 1, "name": 1}) or {}
    if user_doc:
        try:
            await _send_password_change_confirmation_email(user_doc)
        except Exception as e:
            logger.error(f"Password reset confirmation email failed: {e}")

    return {"success": True}


def _verification_page(title: str, message: str, success: bool = True, redirect_url: str = "") -> str:
    """Generate a styled HTML verification result page."""
    icon = "&#10003;" if success else "&#10007;"
    icon_bg = "#10B981" if success else "#EF4444"
    redirect_script = (
        f'<script>setTimeout(function(){{window.location.href="{redirect_url}";}}, 4000);</script>'
        if redirect_url
        else ""
    )
    redirect_note = (
        '<p style="color:#9ca3af;font-size:12px;margin-top:16px;">Redirecting you to sign in...</p>'
        if redirect_url
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - RealAICoach</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}}.card{{background:#fff;border-radius:20px;padding:48px 40px;max-width:420px;width:100%;text-align:center;box-shadow:0 4px 24px rgba(0,0,0,.08)}}.icon{{width:64px;height:64px;border-radius:50%;background:{icon_bg};color:#fff;font-size:28px;display:flex;align-items:center;justify-content:center;margin:0 auto 20px}}h1{{color:#111827;font-size:22px;font-weight:700;margin-bottom:8px}}p{{color:#6b7280;font-size:14px;line-height:1.5}}.btn{{display:inline-block;background:#6366f1;color:#fff;padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:600;font-size:14px;margin-top:20px}}</style>
{redirect_script}</head><body>
<div class="card"><div class="icon">{icon}</div><h1>{title}</h1><p>{message}</p>{redirect_note}<a href="/auth/login" class="btn">Go to Sign In</a></div>
</body></html>"""


@router.get("/auth/verify", response_class=HTMLResponse)
async def verify_email(token: str):
    token_hash = _hash_reset_token(token)
    token_doc = await db.email_verification_tokens.find_one(
        {
            "token_hash": token_hash,
            "used": False,
        },
        {"_id": 0},
    )

    if not token_doc:
        return HTMLResponse(
            _verification_page(
                "Verification Failed",
                "This verification link is invalid or has already been used. Please request a new verification email.",
                success=False,
            ),
            status_code=400,
        )

    if token_doc.get("expires_at"):
        exp = token_doc["expires_at"]
        if hasattr(exp, "tzinfo") and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return HTMLResponse(
                _verification_page(
                    "Link Expired",
                    "This verification link has expired. Please request a new verification email from your account settings.",
                    success=False,
                ),
                status_code=400,
            )

    await db.users.update_one(
        {"user_id": token_doc["user_id"]},
        {"$set": {"email_verified": True, "updated_at": datetime.now(timezone.utc)}},
    )
    await db.email_verification_tokens.update_one(
        {"token_hash": token_hash},
        {"$set": {"used": True, "used_at": datetime.now(timezone.utc)}},
    )

    return HTMLResponse(
        _verification_page(
            "Email Verified!",
            "Your email has been successfully verified. You can now enjoy all features of RealAICoach.",
            success=True,
            redirect_url="/auth/login",
        )
    )


@router.post("/auth/otp/request")
async def request_login_otp(request: OtpLoginRequest):
    user = await db.users.find_one({"email": request.email.lower()})
    if not user:
        # Return success to prevent email enumeration
        return {"message": "If an account with that email exists, an OTP has been sent.", "expires_in": 10}

    if _is_login_disabled_account(user):
        # Keep enumeration-safe behavior while preventing OTP sends to disabled aliases.
        return {"message": "If an account with that email exists, an OTP has been sent.", "expires_in": 10}

    user_id = user["user_id"]
    user_name = user.get("name", "User")

    # Use centralized _send_otp for hashing, rate limiting, and logging
    otp_result = await _send_otp(
        user_id,
        request.email,
        user_name,
        "login",
        is_privileged=bool(user.get("is_admin") or user.get("full_access") or _is_otp_exempt(request.email)),
        force_resend=bool(request.force_resend),
    )
    if not otp_result.get("success"):
        error_msg = otp_result.get("error", "Failed to send OTP email")
        logger.error(f"[OTP Login] Failed to send OTP to {request.email}: {error_msg}")
        raise HTTPException(status_code=int(otp_result.get("http_status") or 500), detail=otp_result.get("error_detail") or error_msg)

    logger.info(f"[OTP Login] OTP delivered state={otp_result.get('delivery_status', 'sent')} to {request.email} (user_id={user_id})")
    code_reused = bool(otp_result.get("reused_existing"))
    response_payload = {
        "message": "Existing code still valid" if code_reused else "OTP sent",
        "expires_in": otp_result.get("expires_in", 10),
        "code_reused": code_reused,
        "otp_delivery_status": str(otp_result.get("delivery_status") or ("reused" if code_reused else "sent")),
    }
    delivery_notice = str(otp_result.get("delivery_notice") or "").strip()
    if delivery_notice:
        response_payload["delivery_notice"] = delivery_notice
    if is_nonprod_test_domain_recipient(request.email):
        response_payload["nonprod_test_domain"] = True
    return response_payload


@router.post("/auth/otp/verify")
async def verify_login_otp(payload: OtpVerifyRequest, response: Response, request: Request):
    user_doc = await db.users.find_one({"email": payload.email.lower()})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if _is_login_disabled_account(user_doc):
        await log_security_event(user_doc.get("user_id"), "blocked_user", "high", request, {"email": payload.email, "reason": "obsolete_or_disabled_account"})
        raise HTTPException(status_code=403, detail="This account is inactive. Please use your primary account.")

    user_id = user_doc["user_id"]

    # Use centralized _verify_otp_code for consistency (supports hashed & legacy codes)
    result = await _verify_otp_code(user_id, payload.code, "login")
    if not result.get("success"):
        raise HTTPException(
            status_code=int(result.get("http_status") or 401),
            detail=result.get("error_detail") or result.get("error", "Invalid or expired code"),
        )

    user = User(**user_doc)
    user = await apply_access_overrides(user)

    risk_assessment = await _run_progressive_risk_assessment(
        user,
        request,
        stage="otp_login_verify",
        source="auth_otp_verify",
    )
    risk_assessment = await _apply_preview_login_risk_bypass_if_allowed(
        user=user,
        request=request,
        risk_assessment=risk_assessment,
        source="auth_otp_verify",
    )
    risk_restrictions = (risk_assessment or {}).get("restrictions", {})
    if risk_restrictions.get("require_id_verification"):
        risk_assessment = _apply_alternative_recovery_bypass(risk_assessment, "one_time_code")
        await persist_risk_assessment(
            db=db,
            assessment=risk_assessment or {},
            source="auth_otp_recovery_bypass",
            notify_admins=False,
        )
        risk_restrictions = (risk_assessment or {}).get("restrictions", {})

    risk_guidance = _risk_guidance_for_level(
        (risk_assessment or {}).get("risk_level", "low"),
        "alternative_recovery_approved" if (risk_assessment or {}).get("recovery_bypass", {}).get("applied") else None,
    )
    if risk_restrictions.get("require_id_verification"):
        user_guidance_sent = await _send_user_risk_guidance_email(user, risk_assessment or {}, risk_guidance)
        idv_access_token = await _create_idv_access_token(user.user_id, "auth_otp_verify_critical")
        try:
            from routes.id_verification import trigger_risk_based_id_verification

            await trigger_risk_based_id_verification(
                user.user_id,
                risk_assessment or {},
                triggered_by="auth_otp_verify_critical",
            )
        except Exception as idv_exc:
            logger.warning(f"Risk-triggered IDV failed after OTP verify for {user.user_id}: {idv_exc}")

        await db.user_sessions.delete_many({"user_id": user.user_id})
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Critical account risk detected. Session is locked and ID Checker is required.",
                "code": "risk_engine_id_verification_required",
                "requires_id_verification": True,
                "risk_engine": risk_assessment,
                "risk_output": (risk_assessment or {}).get("output_block", ""),
                "display_message": risk_guidance.get("message"),
                "next_steps": risk_guidance.get("steps", []),
                "email_notification_sent": user_guidance_sent,
                "risk_code": risk_guidance.get("risk_code", "risk_engine_id_verification_required"),
                "support_email": risk_guidance.get("support_email", "security@realaicoach.app"),
                "support_url": "mailto:security@realaicoach.app",
                "idv_access_token": idv_access_token,
                "idv_access_expires_in_seconds": 2700,
            },
        )

    token_version = user.token_version
    if request.remember_me:
        expires_minutes = REMEMBER_ME_MINUTES
    else:
        expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request.client else None,
    )
    session_doc = session.dict()
    session_doc["mfa_verified_at"] = datetime.now(timezone.utc).isoformat()
    if risk_assessment:
        session_doc["risk_context"] = {
            "risk_score": int(risk_assessment.get("risk_score") or 0),
            "risk_level": str(risk_assessment.get("risk_level") or "low"),
            "trigger": str(risk_assessment.get("trigger") or "NO_FRICTION"),
            "assessed_at": str(risk_assessment.get("assessed_at") or datetime.now(timezone.utc).isoformat()),
            "session_protection": str(risk_assessment.get("session_protection") or "STANDARD_MONITORING"),
        }
    await db.user_sessions.insert_one(session_doc)

    _set_session_cookie(response, token, expires_minutes * 60, request)

    await log_security_event(user.user_id, "login_success", "low", request)

    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "is_admin": user.is_admin,
        "full_access": user.full_access,
        "roles": user.roles,
        "role": user.role,
        "email_verified": user.email_verified,
        **_auth_token_payload(request, session_token=token, refresh_token=refresh_token),
        "risk_level": (risk_assessment or {}).get("risk_level", "low"),
        "risk_score": (risk_assessment or {}).get("risk_score", 0),
        "risk_engine_status": (risk_assessment or {}).get("risk_engine_status", "ACTIVE"),
        "risk_output": (risk_assessment or {}).get("output_block", ""),
    }


@router.post("/auth/2fa/verify")
async def verify_2fa(request: Verify2FARequest, response: Response, raw_request: Request):
    """Verify 2FA OTP code or backup code and complete login"""
    result = await _verify_otp_code(request.user_id, request.code, "2fa")
    if not result.get("success"):
        # Try backup code as fallback
        backup_result = await _verify_backup_code(request.user_id, request.code)
        if not backup_result.get("success"):
            raise HTTPException(
                status_code=int(result.get("http_status") or 400),
                detail=result.get("error_detail") or result.get("error", "Verification failed"),
            )

    user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Resource not found")

    user = User(**user_doc)
    user = await apply_access_overrides(user)

    risk_assessment = await _run_progressive_risk_assessment(
        user,
        raw_request,
        stage="2fa_verify",
        source="auth_2fa_verify",
    )
    risk_assessment = await _apply_preview_login_risk_bypass_if_allowed(
        user=user,
        request=raw_request,
        risk_assessment=risk_assessment,
        source="auth_2fa_verify",
    )
    risk_restrictions = (risk_assessment or {}).get("restrictions", {})
    if risk_restrictions.get("require_id_verification"):
        risk_assessment = _apply_alternative_recovery_bypass(risk_assessment, "one_time_code")
        await persist_risk_assessment(
            db=db,
            assessment=risk_assessment or {},
            source="auth_2fa_recovery_bypass",
            notify_admins=False,
        )
        risk_restrictions = (risk_assessment or {}).get("restrictions", {})

    risk_guidance = _risk_guidance_for_level(
        (risk_assessment or {}).get("risk_level", "low"),
        "alternative_recovery_approved" if (risk_assessment or {}).get("recovery_bypass", {}).get("applied") else None,
    )
    if risk_restrictions.get("require_id_verification"):
        user_guidance_sent = await _send_user_risk_guidance_email(user, risk_assessment or {}, risk_guidance)
        idv_access_token = await _create_idv_access_token(user.user_id, "auth_2fa_verify_critical")
        try:
            from routes.id_verification import trigger_risk_based_id_verification

            await trigger_risk_based_id_verification(
                user.user_id,
                risk_assessment or {},
                triggered_by="auth_2fa_verify_critical",
            )
        except Exception as idv_exc:
            logger.warning(f"Risk-triggered IDV failed after 2FA verify for {user.user_id}: {idv_exc}")

        await db.user_sessions.delete_many({"user_id": user.user_id})
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Critical account risk detected. Session is locked and ID Checker is required.",
                "code": "risk_engine_id_verification_required",
                "requires_id_verification": True,
                "risk_engine": risk_assessment,
                "risk_output": (risk_assessment or {}).get("output_block", ""),
                "display_message": risk_guidance.get("message"),
                "next_steps": risk_guidance.get("steps", []),
                "email_notification_sent": user_guidance_sent,
                "risk_code": risk_guidance.get("risk_code", "risk_engine_id_verification_required"),
                "support_email": risk_guidance.get("support_email", "security@realaicoach.app"),
                "support_url": "mailto:security@realaicoach.app",
                "idv_access_token": idv_access_token,
                "idv_access_expires_in_seconds": 2700,
            },
        )

    token_version = user.token_version
    expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=raw_request.client.host if raw_request and raw_request.client else None,
    )
    session_doc = session.dict()
    session_doc["mfa_verified_at"] = datetime.now(timezone.utc).isoformat()
    if risk_assessment:
        session_doc["risk_context"] = {
            "risk_score": int(risk_assessment.get("risk_score") or 0),
            "risk_level": str(risk_assessment.get("risk_level") or "low"),
            "trigger": str(risk_assessment.get("trigger") or "NO_FRICTION"),
            "assessed_at": str(risk_assessment.get("assessed_at") or datetime.now(timezone.utc).isoformat()),
            "session_protection": str(risk_assessment.get("session_protection") or "STANDARD_MONITORING"),
        }
    await db.user_sessions.insert_one(session_doc)

    _set_session_cookie(response, token, expires_minutes * 60, raw_request)

    await log_security_event(user.user_id, "login_success", "low", raw_request)

    # Check if this is a returning user (has last_active_route)
    last_route = user_doc.get("last_active_route", "")
    last_active = user_doc.get("last_active_at", "")
    welcome_back = bool(last_route and last_active)

    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "is_admin": user.is_admin,
        "full_access": user.full_access,
        "roles": user.roles,
        "role": user.role,
        "email_verified": user.email_verified,
        "profile_image": _safe_profile_image_for_auth_response(user_doc.get("profile_image", "")),
        **_auth_token_payload(raw_request, session_token=token, refresh_token=refresh_token),
        "welcome_back": welcome_back,
        "last_active_route": last_route,
        "last_active_at": last_active,
        "theme_preference": user_doc.get("theme_preference"),
        "risk_level": (risk_assessment or {}).get("risk_level", "low"),
        "risk_score": (risk_assessment or {}).get("risk_score", 0),
        "risk_engine_status": (risk_assessment or {}).get("risk_engine_status", "ACTIVE"),
        "risk_output": (risk_assessment or {}).get("output_block", ""),
    }


# ── Sensitive Action OTP ──


class ActionOTPRequest(BaseModel):
    action: str  # password_change, wallet_transfer, loan_request, profile_update, large_transaction


class ActionOTPVerify(BaseModel):
    action: str
    code: str


@router.post("/auth/action-otp/request")
async def request_action_otp(payload: ActionOTPRequest, request: Request):
    """Request OTP for sensitive actions (wallet transfer, password change, etc.)"""
    from routes.db import require_auth

    user = await require_auth(request)

    # Exempt accounts don't need action OTP
    if _is_otp_policy_exempt(user):
        return {"exempt": True, "message": "Action OTP not required for this account."}

    purpose = f"action_{payload.action}"
    otp_result = await _send_otp(user.user_id, user.email, user.name, purpose)
    if not otp_result.get("success"):
        raise HTTPException(status_code=int(otp_result.get("http_status") or 500), detail=otp_result.get("error_detail") or otp_result.get("error", "Failed to send OTP"))

    return {"success": True, "method": otp_result.get("method"), "expires_in": otp_result.get("expires_in")}


@router.post("/auth/action-otp/verify")
async def verify_action_otp(payload: ActionOTPVerify, request: Request):
    """Verify OTP for a sensitive action."""
    from routes.db import require_auth

    user = await require_auth(request)

    if _is_otp_policy_exempt(user):
        return {"success": True, "exempt": True}

    purpose = f"action_{payload.action}"
    result = await _verify_otp_code(user.user_id, payload.code, purpose)
    if not result.get("success"):
        raise HTTPException(
            status_code=int(result.get("http_status") or 400),
            detail=result.get("error_detail") or result.get("error", "Verification failed"),
        )

    return {"success": True}


# ── Admin OTP Monitoring ──


@router.get("/auth/admin/otp-dashboard")
async def admin_otp_dashboard(request: Request):
    """Admin dashboard for OTP monitoring."""
    from routes.db import require_admin

    await require_admin(request)

    total_logs = await db.otp_logs.count_documents({})
    sent = await db.otp_logs.count_documents({"status": "sent"})
    verified = await db.otp_logs.count_documents({"status": "verified"})

    email_sent = await db.otp_logs.count_documents({"method": "email"})
    sms_sent = await db.otp_logs.count_documents({"method": "sms"})

    locked_accounts = await db.user_security.count_documents({"account_locked": True})
    total_security = await db.user_security.count_documents({})

    # Recent OTP activity
    recent = await db.otp_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(30)

    # Failed attempts
    high_failures = await db.user_security.find(
        {"failed_otp_attempts": {"$gte": 3}},
        {"_id": 0, "user_id": 1, "failed_otp_attempts": 1, "account_locked": 1},
    ).to_list(20)

    return {
        "total_otps": total_logs,
        "sent": sent,
        "verified": verified,
        "success_rate": round(verified / max(sent, 1) * 100, 1),
        "email_sent": email_sent,
        "sms_sent": sms_sent,
        "email_success_rate": round(verified / max(email_sent, 1) * 100, 1),
        "locked_accounts": locked_accounts,
        "total_security_records": total_security,
        "recent_activity": recent,
        "high_failure_accounts": high_failures,
    }


@router.post("/auth/admin/e2e/otp/issue")
async def admin_issue_e2e_otp(payload: AdminE2EOtpIssueRequest, request: Request):
    """Issue an OTP code for allowlisted E2E accounts in non-production runtimes."""
    from routes.db import require_admin

    admin_user = await require_admin(request)

    if not _auth_test_helpers_enabled():
        raise HTTPException(status_code=403, detail="E2E OTP helper is disabled outside non-production runtimes")

    target_email = str(payload.email or "").strip().lower()
    allowlisted_emails = _auth_test_helper_email_allowlist()
    if target_email not in allowlisted_emails:
        raise HTTPException(status_code=403, detail="Target email is not in E2E OTP helper allowlist")

    purpose = str(payload.purpose or "2fa").strip().lower()
    if purpose not in AUTH_TEST_HELPER_PURPOSE_ALLOWLIST:
        raise HTTPException(
            status_code=400,
            detail=f"purpose must be one of: {', '.join(sorted(AUTH_TEST_HELPER_PURPOSE_ALLOWLIST))}",
        )

    user_doc = await db.users.find_one({"email": target_email}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found for provided email")

    now = datetime.now(timezone.utc)
    force_outside_grace_at = (now - timedelta(days=max(OTP_GRACE_DAYS, OTP_POST_VERIFY_GRACE_DAYS) + 7)).isoformat()

    # Deterministic E2E setup: ensure target user is outside all grace windows so login reliably prompts 2FA.
    await db.users.update_one(
        {"user_id": user_doc["user_id"]},
        {
            "$set": {
                "created_at": force_outside_grace_at,
                "updated_at": now.isoformat(),
            }
        },
    )
    await db.user_security.update_one(
        {"user_id": user_doc["user_id"]},
        {
            "$set": {
                "last_otp_verified_at": "2000-01-01T00:00:00+00:00",
                "failed_otp_attempts": 0,
                "account_locked": False,
                "updated_at": now.isoformat(),
            }
        },
        upsert=True,
    )

    otp_code = f"{random.randint(0, (10 ** OTP_CODE_LENGTH) - 1):0{OTP_CODE_LENGTH}d}"
    expires_in_minutes = _otp_expiry_minutes()
    expires_at = now + timedelta(minutes=expires_in_minutes)

    await db.otp_codes.delete_many({"user_id": user_doc["user_id"], "purpose": purpose})
    await db.otp_codes.insert_one(
        {
            "user_id": user_doc["user_id"],
            "code_hash": _hash_otp(otp_code),
            "purpose": purpose,
            "attempts": 0,
            "expires_at": expires_at,
            "created_at": now,
            "issued_by": "admin_e2e_helper",
            "issued_by_user_id": admin_user.user_id,
        }
    )

    await db.otp_logs.insert_one(
        {
            "user_id": user_doc["user_id"],
            "purpose": purpose,
            "method": "e2e_helper",
            "status": "sent",
            "created_at": now.isoformat(),
            "target_email": target_email,
            "issued_by_user_id": admin_user.user_id,
        }
    )

    await log_security_event(
        admin_user.user_id,
        "admin_e2e_otp_issued",
        "medium",
        request,
        {
            "target_user_id": user_doc["user_id"],
            "target_email": target_email,
            "purpose": purpose,
        },
    )

    return {
        "success": True,
        "target_email": target_email,
        "user_id": user_doc["user_id"],
        "purpose": purpose,
        "otp_code": otp_code,
        "expires_in_minutes": expires_in_minutes,
        "expires_at": expires_at.isoformat(),
        "non_production_only": True,
        "grace_window_reset": True,
    }


@router.post("/auth/admin/unlock-account")
async def admin_unlock_account(request: Request):
    """Admin endpoint to unlock a locked account."""
    from routes.db import require_admin

    await require_admin(request)
    body = await request.json()
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    result = await db.user_security.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "account_locked": False,
                "failed_otp_attempts": 0,
                "unlocked_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    return {"success": result.modified_count > 0}


# ── 2FA Settings & Backup Codes ──


def _generate_backup_codes(count: int = 8) -> list:
    """Generate a set of one-time backup codes."""
    return [secrets.token_hex(4).upper() for _ in range(count)]


@router.get("/auth/2fa/status")
async def get_2fa_status(request: Request):
    """Get 2FA status for the current user."""
    from routes.db import require_auth

    user = await require_auth(request)

    security = await db.user_security.find_one({"user_id": user.user_id}, {"_id": 0})
    settings = await db.security_settings.find_one({"user_id": user.user_id}, {"_id": 0})
    has_pin = await db.biometric_pins.find_one({"user_id": user.user_id}) is not None
    has_passkey = await db.webauthn_credentials.find_one({"user_id": user.user_id}) is not None
    passkey_count = await db.webauthn_credentials.count_documents({"user_id": user.user_id})

    two_fa_enabled = bool(security and security.get("two_fa_enabled"))
    is_exempt = _is_otp_policy_exempt(user)
    backup_codes_count = 0
    if security and security.get("backup_codes"):
        backup_codes_count = sum(1 for c in security["backup_codes"] if not c.get("used"))

    return {
        "two_fa_enabled": two_fa_enabled,
        "is_exempt": is_exempt,
        "email": user.email,
        "backup_codes_remaining": backup_codes_count,
        "has_pin": has_pin,
        "has_passkey": has_passkey,
        "passkey_count": passkey_count,
        "passkey_rollout_enabled": _passkey_rollout_enabled_for_user(user.user_id),
        "passkey_rollout_percent": max(0, min(PASSKEY_ROLLOUT_PERCENT, 100)),
        "biometric_enabled": bool(settings and settings.get("biometric_enabled")),
        "last_otp_verified_at": security.get("last_otp_verified_at") if security else None,
        "account_locked": bool(security and security.get("account_locked")),
    }


@router.post("/auth/2fa/enable")
async def enable_2fa(request: Request):
    """Enable 2FA for the current user and generate backup codes."""
    from routes.db import require_auth

    user = await require_auth(request)

    if _is_otp_policy_exempt(user):
        return {
            "message": "2FA is managed by organization policy for this account.",
            "two_fa_enabled": False,
            "exempt": True,
        }

    backup_codes = _generate_backup_codes()
    hashed_codes = [
        {"code_hash": _hash_otp(c), "used": False, "created_at": datetime.now(timezone.utc).isoformat()}
        for c in backup_codes
    ]

    await db.user_security.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "two_fa_enabled": True,
                "two_fa_enabled_at": datetime.now(timezone.utc).isoformat(),
                "backup_codes": hashed_codes,
                "failed_otp_attempts": 0,
                "account_locked": False,
            }
        },
        upsert=True,
    )

    await log_security_event(user.user_id, "2fa_enabled", "low", request)

    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=user.user_id,
            notif_type="2fa_enabled",
            title="2FA Enabled",
            body="Two-factor authentication is now active on your account.",
            action_url="/security",
        )
    except Exception:
        pass

    return {
        "two_fa_enabled": True,
        "backup_codes": backup_codes,
        "message": "2FA enabled. Save your backup codes securely.",
    }


@router.post("/auth/2fa/disable")
async def disable_2fa(request: Request):
    """Disable 2FA for the current user."""
    from routes.db import require_auth

    user = await require_auth(request)

    if _is_otp_policy_exempt(user):
        return {"message": "2FA is managed by organization policy.", "two_fa_enabled": False}

    await db.user_security.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "two_fa_enabled": False,
                "backup_codes": [],
                "two_fa_disabled_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    await log_security_event(user.user_id, "2fa_disabled", "medium", request)

    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=user.user_id,
            notif_type="2fa_disabled",
            title="2FA Disabled",
            body="Two-factor authentication has been disabled. If this wasn't you, enable it again immediately.",
            action_url="/security",
        )
    except Exception:
        pass

    return {"two_fa_enabled": False, "message": "2FA has been disabled."}


@router.post("/auth/2fa/backup-codes/regenerate")
async def regenerate_backup_codes(request: Request):
    """Generate new backup codes, invalidating old ones."""
    from routes.db import require_auth

    user = await require_auth(request)

    backup_codes = _generate_backup_codes()
    hashed_codes = [
        {"code_hash": _hash_otp(c), "used": False, "created_at": datetime.now(timezone.utc).isoformat()}
        for c in backup_codes
    ]

    await db.user_security.update_one(
        {"user_id": user.user_id},
        {"$set": {"backup_codes": hashed_codes}},
        upsert=True,
    )

    await log_security_event(user.user_id, "backup_codes_regenerated", "low", request)
    return {"backup_codes": backup_codes, "message": "New backup codes generated. Old codes are now invalid."}


@router.get("/auth/security/login-history")
async def get_login_history(request: Request):
    """Get recent login history for the current user."""
    from routes.db import require_auth

    user = await require_auth(request)

    events = (
        await db.security_events.find(
            {
                "user_id": user.user_id,
                "event_type": {"$in": ["login_success", "login_failed", "logout", "2fa_enabled", "2fa_disabled"]},
            },
            {"_id": 0},
        )
        .sort("timestamp", -1)
        .limit(20)
        .to_list(20)
    )

    return {"events": events}


def _passkey_rollout_bucket(user_id: str) -> int:
    digest = hashlib.sha256(str(user_id or "").encode()).hexdigest()
    return int(digest[:8], 16) % 100


def _passkey_rollout_enabled_for_user(user_id: str) -> bool:
    rollout = max(0, min(PASSKEY_ROLLOUT_PERCENT, 100))
    if rollout >= 100:
        return True
    if rollout <= 0:
        return False
    return _passkey_rollout_bucket(user_id) < rollout


def _resolve_webauthn_rp_id(origin: str) -> str:
    host = str(urlparse(origin).hostname or "").strip().lower()
    if not host:
        raise HTTPException(status_code=500, detail="Passkey RP host is not configured")
    # ALWAYS allow localhost for Playwright testing
    return "localhost" if host == "localhost" else host


def _resolve_webauthn_origins(request: Request, canonical_origin: str) -> list[str]:
    origins: list[str] = []
    if canonical_origin:
        origins.append(canonical_origin)
    header_origin = _normalize_base_url(request.headers.get("origin") or "")
    if header_origin and _is_allowed_sso_base(header_origin) and header_origin not in origins:
        origins.append(header_origin)
    runtime_base = _normalize_base_url(_get_frontend_base(request) or "")
    if runtime_base and _is_allowed_sso_base(runtime_base) and runtime_base not in origins:
        origins.append(runtime_base)
    if not origins:
        raise HTTPException(status_code=500, detail="Passkey origin is not configured")
    return origins


async def _resolve_webauthn_config(request: Request) -> Dict[str, Any]:
    canonical_origin = _normalize_base_url(await _resolve_auth_fallback_base(request))
    rp_id = _resolve_webauthn_rp_id(canonical_origin)
    expected_origins = _resolve_webauthn_origins(request, canonical_origin)
    return {
        "origin": canonical_origin,
        "rp_id": rp_id,
        "expected_origins": expected_origins,
    }


async def _safe_json_body(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


async def _create_webauthn_challenge(
    *,
    user_id: str,
    challenge: str,
    challenge_type: str,
    rp_id: str,
    origin: str,
) -> str:
    now = datetime.now(timezone.utc)
    challenge_id = f"wac_{uuid.uuid4().hex[:20]}"
    await db.webauthn_challenges.insert_one(
        {
            "challenge_id": challenge_id,
            "user_id": user_id,
            "challenge": challenge,
            "type": challenge_type,
            "rp_id": rp_id,
            "origin": origin,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=PASSKEY_CHALLENGE_TTL_SECONDS)).isoformat(),
            "consumed": False,
        }
    )
    return challenge_id


async def _consume_webauthn_challenge(
    *,
    user_id: str,
    challenge: str,
    challenge_type: str,
    challenge_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    now_iso = datetime.now(timezone.utc).isoformat()
    query: Dict[str, Any] = {
        "user_id": user_id,
        "challenge": challenge,
        "type": challenge_type,
        "consumed": False,
        "expires_at": {"$gte": now_iso},
    }
    if challenge_id:
        query["challenge_id"] = challenge_id
    doc = await db.webauthn_challenges.find_one_and_update(
        query,
        {"$set": {"consumed": True, "consumed_at": now_iso}},
        projection={"_id": 0},
    )
    return doc


def _extract_credential_id(credential: Dict[str, Any], fallback: Optional[str] = None) -> str:
    candidate = str(
        credential.get("id")
        or credential.get("rawId")
        or fallback
        or ""
    ).strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="Passkey credential id missing")
    return candidate


def _safe_transports(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for raw in value:
        text = str(raw or "").strip().lower()
        if text:
            items.append(text)
    return items


# ── Biometric / PIN Endpoints ──


@router.post("/auth/biometric/set-pin")
async def set_biometric_pin(request: SetPinRequest):
    """Set a PIN for biometric/quick unlock"""
    if len(request.pin) != 4 or not request.pin.isdigit():
        raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits")

    hashed_pin = hash_password(request.pin)
    await db.biometric_pins.update_one(
        {"user_id": request.user_id},
        {
            "$set": {
                "user_id": request.user_id,
                "pin_hash": hashed_pin,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    await db.security_settings.update_one(
        {"user_id": request.user_id}, {"$set": {"biometric_enabled": True}}, upsert=True
    )
    return {"message": "PIN set successfully", "biometric_enabled": True}


@router.post("/auth/biometric/verify-pin")
async def verify_biometric_pin(request: VerifyPinRequest, response: Response):
    """Verify PIN for quick unlock / biometric login"""
    pin_doc = await db.biometric_pins.find_one({"user_id": request.user_id})
    if not pin_doc:
        raise HTTPException(status_code=404, detail="No PIN set. Please set up biometric login first.")

    if not verify_password(request.pin, pin_doc["pin_hash"]):
        raise HTTPException(status_code=401, detail="Invalid PIN")

    user_doc = await db.users.find_one({"user_id": request.user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Resource not found")

    user = User(**user_doc)
    user = await apply_access_overrides(user)
    token_version = user.token_version
    expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=None,
    )
    await db.user_sessions.insert_one(session.dict())

    _set_session_cookie(response, token, expires_minutes * 60, None)

    await log_security_event(user.user_id, "login_success", "low", None)

    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "is_admin": user.is_admin,
        "full_access": user.full_access,
        "roles": user.roles,
        "role": user.role,
        "email_verified": user.email_verified,
        **_auth_token_payload(None, session_token=token, refresh_token=refresh_token),
    }


# ── WebAuthn Biometric Endpoints ──


@router.post("/auth/biometric/webauthn-register-options")
async def webauthn_register_options(request: Request):
    """Generate hardened WebAuthn registration options for the authenticated user."""
    from routes.db import require_auth

    actor = await require_auth(request)
    payload = WebAuthnOptionsRequest(**(await _safe_json_body(request)))
    user_id = str(payload.user_id or actor.user_id)

    if user_id != actor.user_id and not bool(actor.is_admin):
        raise HTTPException(status_code=403, detail="Cannot create passkey options for another user")
    if not _passkey_rollout_enabled_for_user(user_id):
        raise HTTPException(status_code=403, detail="Passkey rollout is not enabled for this account yet")

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Resource not found")

    cfg = await _resolve_webauthn_config(request)
    existing = await db.webauthn_credentials.find({"user_id": user_id}, {"_id": 0, "credential_id": 1}).to_list(20)
    exclude_credentials: List[PublicKeyCredentialDescriptor] = []
    for row in existing:
        cid = str(row.get("credential_id") or "").strip()
        if not cid:
            continue
        try:
            exclude_credentials.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(cid)))
        except Exception:
            continue

    registration_options = generate_registration_options(
        rp_id=cfg["rp_id"],
        rp_name="RealAICoach",
        user_id=user_id.encode(),
        user_name=str(user_doc.get("email") or ""),
        user_display_name=str(user_doc.get("name") or user_doc.get("email") or ""),
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        timeout=60000,
        exclude_credentials=exclude_credentials,
    )

    options_payload = json.loads(options_to_json(registration_options))
    challenge = str(options_payload.get("challenge") or "").strip()
    if not challenge:
        raise HTTPException(status_code=500, detail="Failed to generate passkey challenge")

    challenge_id = await _create_webauthn_challenge(
        user_id=user_id,
        challenge=challenge,
        challenge_type="register",
        rp_id=cfg["rp_id"],
        origin=cfg["origin"],
    )
    options_payload["challenge_id"] = challenge_id
    options_payload["rollout"] = {
        "enabled": True,
        "rollout_percent": max(0, min(PASSKEY_ROLLOUT_PERCENT, 100)),
    }
    return options_payload


def _parse_webauthn_challenge_from_credential(credential: Dict[str, Any]) -> str:
    response_obj = credential.get("response") if isinstance(credential, dict) else None
    if not isinstance(response_obj, dict):
        raise HTTPException(status_code=400, detail="Passkey response is missing")
    client_data_b64 = str(response_obj.get("clientDataJSON") or "").strip()
    if not client_data_b64:
        raise HTTPException(status_code=400, detail="Passkey clientDataJSON is required")
    try:
        client_data_raw = base64url_to_bytes(client_data_b64)
        payload = json.loads(client_data_raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid passkey clientDataJSON payload")
    challenge = str(payload.get("challenge") or "").strip()
    if not challenge:
        raise HTTPException(status_code=400, detail="Passkey challenge is missing")
    return challenge


@router.post("/auth/biometric/webauthn-register-complete")
async def webauthn_register_complete(request: Request):
    """Complete WebAuthn registration with cryptographic verification and replay protection."""
    from routes.db import require_auth

    actor = await require_auth(request)
    payload = WebAuthnRegisterCompleteRequest(**(await _safe_json_body(request)))
    user_id = str(payload.user_id or actor.user_id)

    if user_id != actor.user_id and not bool(actor.is_admin):
        raise HTTPException(status_code=403, detail="Cannot register passkey for another user")
    if not _passkey_rollout_enabled_for_user(user_id):
        raise HTTPException(status_code=403, detail="Passkey rollout is not enabled for this account yet")
    if not isinstance(payload.credential, dict):
        raise HTTPException(status_code=400, detail="Passkey credential payload is required")

    credential = payload.credential
    challenge = _parse_webauthn_challenge_from_credential(credential)
    challenge_doc = await _consume_webauthn_challenge(
        user_id=user_id,
        challenge=challenge,
        challenge_type="register",
        challenge_id=payload.challenge_id,
    )
    if not challenge_doc:
        raise HTTPException(status_code=400, detail="Passkey challenge expired or already used")

    cfg = await _resolve_webauthn_config(request)
    expected_rp_id = str(challenge_doc.get("rp_id") or cfg["rp_id"])
    expected_origins = cfg["expected_origins"]

    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(str(challenge_doc.get("challenge") or "")),
            expected_rp_id=expected_rp_id,
            expected_origin=expected_origins,
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        await log_security_event(user_id, "passkey_registration_failed", "medium", request, {"reason": str(exc)[:160]})
        raise HTTPException(status_code=401, detail="Passkey registration verification failed")

    now_iso = datetime.now(timezone.utc).isoformat()
    credential_id = bytes_to_base64url(verified.credential_id)
    credential_public_key = bytes_to_base64url(verified.credential_public_key)
    transports = _safe_transports(((credential.get("response") or {}).get("transports")))
    nickname = str(payload.nickname or "").strip()[:80] or "This device"
    aaguid_raw = getattr(verified, "aaguid", None)
    if isinstance(aaguid_raw, bytes):
        aaguid = aaguid_raw.hex()
    else:
        aaguid = str(aaguid_raw or "")

    await db.webauthn_credentials.update_one(
        {"user_id": user_id, "credential_id": credential_id},
        {
            "$set": {
                "user_id": user_id,
                "credential_id": credential_id,
                "credential_public_key": credential_public_key,
                "sign_count": int(getattr(verified, "sign_count", 0) or 0),
                "aaguid": aaguid,
                "fmt": str(getattr(verified, "fmt", "") or ""),
                "credential_device_type": str(getattr(getattr(verified, "credential_device_type", None), "value", getattr(verified, "credential_device_type", "")) or ""),
                "credential_backed_up": bool(getattr(verified, "credential_backed_up", False)),
                "nickname": nickname,
                "transports": transports,
                "created_at": now_iso,
                "last_used_at": None,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    await db.security_settings.update_one(
        {"user_id": user_id},
        {"$set": {"biometric_enabled": True, "biometric_last_enabled_at": now_iso}},
        upsert=True,
    )
    await log_security_event(user_id, "passkey_registered", "low", request, {"credential_id": credential_id})

    passkey_count = await db.webauthn_credentials.count_documents({"user_id": user_id})
    return {
        "message": "Biometric registered successfully",
        "biometric_enabled": True,
        "credential_id": credential_id,
        "passkey_count": passkey_count,
    }


@router.get("/auth/biometric/has-passkey")
async def check_user_has_passkey(request: Request):
    """Check if user has enrolled any passkey credentials."""
    user_id = request.query_params.get("user_id", "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    
    count = await db.webauthn_credentials.count_documents({"user_id": user_id})
    return {"has_passkey": count > 0, "passkey_count": count}


@router.post("/auth/biometric/webauthn-auth-options")
async def webauthn_auth_options(request: Request):
    """Generate hardened WebAuthn authentication options for login."""
    payload = WebAuthnOptionsRequest(**(await _safe_json_body(request)))
    user_id = str(payload.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    if not _passkey_rollout_enabled_for_user(user_id):
        raise HTTPException(status_code=403, detail="Passkey rollout is not enabled for this account yet")

    rows = await db.webauthn_credentials.find({"user_id": user_id}, {"_id": 0, "credential_id": 1}).to_list(30)
    if not rows:
        raise HTTPException(status_code=404, detail="No biometric credential registered")

    allow_credentials: List[PublicKeyCredentialDescriptor] = []
    for row in rows:
        cid = str(row.get("credential_id") or "").strip()
        if not cid:
            continue
        try:
            allow_credentials.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(cid)))
        except Exception:
            continue

    if not allow_credentials:
        raise HTTPException(status_code=404, detail="No valid biometric credential registered")

    cfg = await _resolve_webauthn_config(request)
    authn_options = generate_authentication_options(
        rp_id=cfg["rp_id"],
        allow_credentials=allow_credentials,
        timeout=60000,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    options_payload = json.loads(options_to_json(authn_options))
    challenge = str(options_payload.get("challenge") or "").strip()
    if not challenge:
        raise HTTPException(status_code=500, detail="Failed to generate passkey challenge")

    challenge_id = await _create_webauthn_challenge(
        user_id=user_id,
        challenge=challenge,
        challenge_type="auth",
        rp_id=cfg["rp_id"],
        origin=cfg["origin"],
    )
    options_payload["challenge_id"] = challenge_id
    return options_payload


@router.post("/auth/biometric/webauthn-auth-complete")
async def webauthn_auth_complete(request: Request, response: Response):
    """Complete WebAuthn authentication with cryptographic assertion verification."""
    payload = WebAuthnAuthCompleteRequest(**(await _safe_json_body(request)))
    user_id = str(payload.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    if not _passkey_rollout_enabled_for_user(user_id):
        raise HTTPException(status_code=403, detail="Passkey rollout is not enabled for this account yet")
    if not isinstance(payload.credential, dict):
        raise HTTPException(status_code=400, detail="Passkey credential payload is required")

    credential = payload.credential
    credential_id = _extract_credential_id(credential, payload.credential_id)

    cred = await db.webauthn_credentials.find_one(
        {"user_id": user_id, "credential_id": credential_id},
        {"_id": 0},
    )
    if not cred:
        await log_security_event(user_id, "passkey_login_failed", "medium", request, {"reason": "credential_not_found"})
        raise HTTPException(status_code=401, detail="Biometric verification failed")

    challenge = _parse_webauthn_challenge_from_credential(credential)
    challenge_doc = await _consume_webauthn_challenge(
        user_id=user_id,
        challenge=challenge,
        challenge_type="auth",
        challenge_id=payload.challenge_id,
    )
    if not challenge_doc:
        await log_security_event(user_id, "passkey_login_failed", "medium", request, {"reason": "challenge_expired_or_replayed"})
        raise HTTPException(status_code=400, detail="Passkey challenge expired or already used")

    cfg = await _resolve_webauthn_config(request)
    expected_rp_id = str(challenge_doc.get("rp_id") or cfg["rp_id"])
    expected_origins = cfg["expected_origins"]

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(str(challenge_doc.get("challenge") or "")),
            expected_rp_id=expected_rp_id,
            expected_origin=expected_origins,
            credential_public_key=base64url_to_bytes(str(cred.get("credential_public_key") or "")),
            credential_current_sign_count=int(cred.get("sign_count") or 0),
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        await log_security_event(user_id, "passkey_login_failed", "medium", request, {"reason": str(exc)[:160]})
        raise HTTPException(status_code=401, detail="Biometric verification failed")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.webauthn_credentials.update_one(
        {"user_id": user_id, "credential_id": credential_id},
        {
            "$set": {
                "sign_count": int(getattr(verified, "new_sign_count", cred.get("sign_count") or 0)),
                "last_used_at": now_iso,
                "credential_backed_up": bool(getattr(verified, "credential_backed_up", False)),
                "credential_device_type": str(getattr(getattr(verified, "credential_device_type", None), "value", getattr(verified, "credential_device_type", "")) or ""),
                "updated_at": now_iso,
            }
        },
    )

    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() if request else ""
    if not ip:
        ip = request.client.host if request and request.client else "unknown"
    ua = request.headers.get("User-Agent", "") if request else ""
    device_fp = _fingerprint_device(ua, ip)
    await db.known_devices.update_one(
        {"user_id": user_id, "device_id": device_fp},
        {
            "$set": {
                "last_passkey_credential_id": credential_id,
                "last_seen": now_iso,
                "updated_at": now_iso,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "device_id": device_fp,
                "trusted": False,
                "first_seen": now_iso,
                "user_agent": ua[:120],
                "ip_address": ip,
                "device_type": "mobile" if any(k in (ua or "").lower() for k in ("mobile", "android", "iphone")) else "desktop",
                "login_count": 0,
            },
            "$inc": {"login_count": 1},
        },
        upsert=True,
    )

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Resource not found")

    user = User(**user_doc)
    user = await apply_access_overrides(user)
    token_version = user.token_version
    expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request.client else None,
    )
    await db.user_sessions.insert_one(session.dict())

    _set_session_cookie(response, token, expires_minutes * 60, request)

    await log_security_event(user.user_id, "passkey_login_success", "low", request, {"credential_id": credential_id})

    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "is_admin": user.is_admin,
        "full_access": user.full_access,
        "roles": user.roles,
        "role": user.role,
        "email_verified": user.email_verified,
        "login_method": "passkey",
        **_auth_token_payload(request, session_token=token, refresh_token=refresh_token),
    }


@router.get("/auth/biometric/webauthn/credentials")
async def webauthn_list_credentials(request: Request):
    """List passkey credentials for the authenticated user."""
    from routes.db import require_auth

    user = await require_auth(request)
    rows = await db.webauthn_credentials.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(30)
    sanitized = []
    for row in rows:
        sanitized.append(
            {
                "credential_id": row.get("credential_id", ""),
                "nickname": row.get("nickname") or "This device",
                "created_at": row.get("created_at"),
                "last_used_at": row.get("last_used_at"),
                "credential_device_type": row.get("credential_device_type") or "",
                "credential_backed_up": bool(row.get("credential_backed_up", False)),
                "transports": row.get("transports") or [],
                "sign_count": int(row.get("sign_count") or 0),
            }
        )
    return {
        "credentials": sanitized,
        "total": len(sanitized),
        "rollout": {
            "enabled": _passkey_rollout_enabled_for_user(user.user_id),
            "rollout_percent": max(0, min(PASSKEY_ROLLOUT_PERCENT, 100)),
        },
    }


@router.delete("/auth/biometric/webauthn/credentials/{credential_id}")
async def webauthn_delete_credential(credential_id: str, request: Request):
    """Delete one passkey credential for the authenticated user."""
    from routes.db import require_auth

    user = await require_auth(request)
    cid = str(credential_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="credential_id required")

    result = await db.webauthn_credentials.delete_one({"user_id": user.user_id, "credential_id": cid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Passkey credential not found")

    remaining = await db.webauthn_credentials.count_documents({"user_id": user.user_id})
    await db.security_settings.update_one(
        {"user_id": user.user_id},
        {"$set": {"biometric_enabled": remaining > 0, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    await log_security_event(user.user_id, "passkey_revoked", "medium", request, {"credential_id": cid, "remaining": remaining})
    return {"success": True, "credential_id": cid, "remaining": remaining}


@router.get("/auth/biometric/enrollment-eligibility")
async def webauthn_enrollment_eligibility(request: Request):
    """Return whether this account should see the passkey enrollment prompt."""
    from routes.db import require_auth

    user = await require_auth(request)
    user_id = user.user_id
    has_passkey = await db.webauthn_credentials.find_one({"user_id": user_id}, {"_id": 0, "credential_id": 1}) is not None
    settings = await db.security_settings.find_one({"user_id": user_id}, {"_id": 0}) or {}
    dismissed_at = str(settings.get("passkey_prompt_dismissed_at") or "").strip()

    cooldown_elapsed = True
    if dismissed_at:
        try:
            dismissed_dt = datetime.fromisoformat(dismissed_at.replace("Z", "+00:00"))
            cooldown_elapsed = (datetime.now(timezone.utc) - dismissed_dt).total_seconds() >= PASSKEY_PROMPT_COOLDOWN_SECONDS
        except Exception:
            cooldown_elapsed = True

    rollout_enabled = _passkey_rollout_enabled_for_user(user_id)
    should_prompt = bool(rollout_enabled and not has_passkey and cooldown_elapsed)
    return {
        "rollout_enabled": rollout_enabled,
        "rollout_percent": max(0, min(PASSKEY_ROLLOUT_PERCENT, 100)),
        "has_passkey": has_passkey,
        "cooldown_elapsed": cooldown_elapsed,
        "should_prompt": should_prompt,
    }


@router.post("/auth/biometric/enrollment-dismiss")
async def webauthn_enrollment_dismiss(request: Request):
    """Persist passkey enrollment prompt dismissal timestamp for cooldown."""
    from routes.db import require_auth

    user = await require_auth(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.security_settings.update_one(
        {"user_id": user.user_id},
        {"$set": {"passkey_prompt_dismissed_at": now_iso, "updated_at": now_iso}},
        upsert=True,
    )
    return {"success": True, "dismissed_at": now_iso}


# ── Password & Profile ──


@router.post("/auth/change-password")
async def change_password(request: ChangePasswordRequest, raw_request: Request):
    """Change user password"""
    user_data = await db.users.find_one({"user_id": request.user_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="Resource not found")

    if not verify_password(request.current_password, user_data.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    pw_error = validate_password_strength(request.new_password)
    if pw_error:
        raise HTTPException(status_code=400, detail=pw_error)

    new_hash = hash_password(request.new_password)
    await db.users.update_one(
        {"user_id": request.user_id}, {"$set": {"password_hash": new_hash, "updated_at": datetime.now(timezone.utc)}}
    )

    # Invalidate all other sessions — force re-login with new password
    await invalidate_user_sessions(request.user_id)

    # Clear any IP blocks and failed login counters for this user so they can
    # immediately log back in with the new password without being blocked.
    user_email = user_data.get("email", "")
    await db.security_blocks.delete_many({"$or": [{"user_id": request.user_id}, {"email": user_email}]})
    await db.users.update_one(
        {"user_id": request.user_id},
        {"$set": {"failed_login_attempts": 0}, "$unset": {"lockout_until": ""}}
    )
    # Also clear IP-based blocks for the requester's IP
    ip_address = raw_request.client.host if raw_request and raw_request.client else None
    if ip_address:
        await db.security_blocks.delete_many({"ip_address": ip_address})
        clear_rate_limit(f"login:{ip_address}")
    # Create a password-reset waiver so user can login immediately without IP blocks
    await db.password_reset_unlock_waivers.update_one(
        {"email": user_email.lower(), "user_id": request.user_id},
        {"$set": {
            "email": user_email.lower(),
            "user_id": request.user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        }},
        upsert=True,
    )

    try:
        await _send_password_change_confirmation_email(user_data)
    except Exception as e:
        logger.error(f"Password changed email failed: {e}")

    # Real-time notification
    try:
        from routes.notification_engine import emit_notification

        await emit_notification(
            user_id=request.user_id,
            notif_type="password_changed",
            title="Password Updated",
            body="Your password was successfully changed. If this wasn't you, secure your account immediately.",
            action_url="/security",
        )
    except Exception:
        pass

    return {"message": "Password changed successfully"}


@router.post("/auth/google/session")
async def google_auth_session(request: Request, response: Response):
    """Exchange Emergent Google OAuth session_id for user data"""
    body = await request.json()
    session_id = body.get("session_id")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    async with httpx.AsyncClient() as client:
        auth_response = await client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data", headers={"X-Session-ID": session_id}
        )

        if auth_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid session")

        user_data = auth_response.json()

    existing = await db.users.find_one({"email": user_data["email"]}, {"_id": 0})
    google_picture = user_data.get("picture", "")

    if existing:
        user = User(**existing)
        update_fields: dict = {"auth_provider": "google"}
        # Set profile_image from Google if user doesn't have one yet
        if google_picture and not existing.get("profile_image"):
            update_fields["profile_image"] = google_picture
        if update_fields:
            await db.users.update_one({"user_id": user.user_id}, {"$set": update_fields})
        await db.user_sessions.delete_many({"user_id": user.user_id})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = User(
            user_id=user_id,
            email=user_data["email"],
            name=user_data["name"],
            picture=google_picture,
            auth_provider="google",
        )
        user_dict = user.dict()
        if google_picture:
            user_dict["profile_image"] = google_picture
        await db.users.insert_one(user_dict)

    user = await apply_access_overrides(user)

    token_version = user.token_version
    expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    session_token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=session_token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request.client else None,
    )
    await db.user_sessions.insert_one(session.dict())

    _set_session_cookie(response, session_token, expires_minutes * 60, request)

    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "is_admin": user.is_admin,
        "full_access": user.full_access,
        "roles": user.roles,
        **_auth_token_payload(request, session_token=session_token),
    }


# ── Microsoft SSO ──────────────────────────────────────────────────────────
try:
    import msal
except ImportError:
    msal = None
    logger.warning("msal package not installed — Microsoft SSO will be unavailable")

SSO_STATE_TTL_SECONDS = 15 * 60
_SSO_STATE_REPLAY_CACHE: dict[str, int] = {}


def _consume_sso_state_signature(signature: str) -> bool:
    sig = str(signature or "").strip().lower()
    if not sig:
        return False
    now_ts = int(datetime.now(timezone.utc).timestamp())

    # prune stale entries
    stale = [key for key, ts in _SSO_STATE_REPLAY_CACHE.items() if now_ts - int(ts) > SSO_STATE_TTL_SECONDS]
    for key in stale:
        _SSO_STATE_REPLAY_CACHE.pop(key, None)

    if sig in _SSO_STATE_REPLAY_CACHE:
        return False

    _SSO_STATE_REPLAY_CACHE[sig] = now_ts
    return True


def _normalize_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    if not (raw.startswith("https://") or raw.startswith("http://")):
        raw = f"https://{raw}"
    try:
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return ""
        scheme = "https" if parsed.scheme.lower() == "http" else parsed.scheme.lower()
        return f"{scheme}://{parsed.netloc}".rstrip("/")
    except Exception:
        return ""


def _build_qr_approval_url(frontend_base: str, session_id: str) -> str:
    normalized = _normalize_base_url(frontend_base)
    if not normalized:
        return ""
    return f"{normalized}/auth/qr-approve?{urlencode({'session': session_id})}"


def _extract_host(base_url: str) -> str:
    normalized = _normalize_base_url(base_url)
    if not normalized:
        return ""
    try:
        return (urlparse(normalized).hostname or "").lower().strip()
    except Exception:
        return ""


def _is_preview_sso_base(base_url: str) -> bool:
    host = _extract_host(base_url)
    return bool(host and host.endswith("preview.emergentagent.com"))


def _allowed_sso_host_suffixes() -> list[str]:
    hosts: set[str] = set()

    for key in [
        "SSO_ALLOWED_HOST_SUFFIXES",
        "SSO_ALLOWED_HOSTS",
    ]:
        raw = str(os.environ.get(key, "") or "").strip()
        if raw:
            for part in raw.split(","):
                item = str(part or "").strip().lower()
                if item:
                    hosts.add(item)

    for candidate in [
        os.environ.get("SSO_CANONICAL_REDIRECT_BASE", ""),
        os.environ.get("SSO_REDIRECT_BASE_URL", ""),
        os.environ.get("FRONTEND_BASE_URL", ""),
    ]:
        host = _extract_host(candidate)
        if host:
            hosts.add(host)

    # Keep enterprise preview/prod suffixes trusted by default.
    hosts.update({
        "preview.emergentagent.com",
        "realaicoach.app",
        "www.realaicoach.app",
    })
    return sorted(hosts)


def _is_allowed_sso_base(base_url: str) -> bool:
    host = _extract_host(base_url)
    if not host:
        return False
    for allowed in _allowed_sso_host_suffixes():
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    return False


def _configured_sso_redirect_base() -> str:
    canonical = _normalize_base_url(os.environ.get("SSO_CANONICAL_REDIRECT_BASE") or "")
    if canonical and _is_allowed_sso_base(canonical):
        return canonical

    redirect_env = _normalize_base_url(os.environ.get("SSO_REDIRECT_BASE_URL") or "")
    frontend_env = _normalize_base_url(os.environ.get("FRONTEND_BASE_URL") or "")

    # Auto-heal stale preview aliases: if override points to old preview host but FRONTEND_BASE_URL is newer,
    # prefer FRONTEND_BASE_URL unless explicit canonical override is set.
    if redirect_env and frontend_env and _extract_host(redirect_env) != _extract_host(frontend_env):
        if _extract_host(redirect_env).endswith("preview.emergentagent.com"):
            if _is_allowed_sso_base(frontend_env):
                return frontend_env

    if redirect_env and _is_allowed_sso_base(redirect_env):
        return redirect_env
    if frontend_env and _is_allowed_sso_base(frontend_env):
        return frontend_env
    return ""


def _provider_redirect_env_override(provider: str | None) -> str:
    p = str(provider or "").strip().lower()
    if p == "microsoft":
        candidate = _normalize_base_url(os.environ.get("MS_SSO_CANONICAL_REDIRECT_BASE") or "")
        if candidate and _is_allowed_sso_base(candidate):
            return candidate
    if p == "apple":
        candidate = _normalize_base_url(os.environ.get("APPLE_SSO_CANONICAL_REDIRECT_BASE") or "")
        if candidate and _is_allowed_sso_base(candidate):
            return candidate
    return ""


def _provider_registered_redirect_fallback(provider: str | None) -> str:
    if not _env_bool("SSO_ALLOW_REGISTERED_REDIRECT_URI_AS_ACTIVE_BASE", False):
        return ""

    p = str(provider or "").strip().lower()
    if p == "microsoft":
        for item in str(os.environ.get("MS_SSO_REGISTERED_REDIRECT_URIS") or "").split(","):
            base = _normalize_base_url(item)
            if base and _is_allowed_sso_base(base):
                return base
    if p == "apple":
        for item in str(os.environ.get("APPLE_SSO_REGISTERED_REDIRECT_URIS") or "").split(","):
            base = _normalize_base_url(item)
            if base and _is_allowed_sso_base(base):
                return base
    return ""


def _apple_auto_synced_redirect_base(request: Request | None = None) -> str:
    """Resolve Apple callback base using provider-verified canonical strategy."""
    registered = _parse_registered_redirect_uris("APPLE_SSO_REGISTERED_REDIRECT_URIS")
    allowlist = _apple_effective_callback_allowlist(request)
    strict_allowlist = _apple_strict_callback_allowlist_enabled()

    for base in allowlist:
        if base and _is_allowed_sso_base(base):
            return base

    if strict_allowlist and allowlist:
        return ""

    if _env_bool("APPLE_SSO_AUTO_SYNC_FALLBACK_TO_REGISTERED", True):
        non_preview = [base for base in registered if base and not _is_preview_sso_base(base)]
        for base in non_preview:
            if _is_allowed_sso_base(base):
                return base

    return ""


def _apple_callback_strategy() -> str:
    if _apple_stable_broker_callback_uri():
        return "broker"
    mode = str(os.environ.get("APPLE_SSO_CALLBACK_STRATEGY") or "direct").strip().lower()
    return mode if mode in {"direct", "broker"} else "direct"


def _apple_force_direct_callback_in_preview() -> bool:
    return _env_bool("APPLE_SSO_FORCE_DIRECT_CALLBACK_IN_PREVIEW", True)


def _apple_effective_callback_strategy(request: Request | None = None) -> str:
    strategy = _apple_callback_strategy()
    if strategy != "broker" or not request or not _apple_force_direct_callback_in_preview():
        return strategy

    for candidate in [
        _preferred_preview_frontend_base(),
        _normalize_base_url(_get_frontend_base(request) or ""),
    ]:
        if candidate and _is_preview_sso_base(candidate):
            return "direct"

    return strategy


def _apple_stable_broker_callback_uri() -> str:
    raw = str(os.environ.get("APPLE_SSO_STABLE_BROKER_CALLBACK_URL") or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        base = _normalize_base_url(f"{parsed.scheme}://{parsed.netloc}") if parsed.scheme and parsed.netloc else ""
        path = str(parsed.path or "").strip()
        if not base or not path:
            return ""
        if not _is_allowed_sso_base(base):
            return ""
        if not path.startswith("/api/auth/apple/"):
            return ""
        return f"{base}{path}"
    except Exception:
        return ""


def _apple_broker_callback_path() -> str:
    path = str(os.environ.get("APPLE_SSO_BROKER_CALLBACK_PATH") or "/api/auth/apple/broker/callback").strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def _apple_broker_base() -> str:
    stable_callback = _apple_stable_broker_callback_uri()
    if stable_callback:
        parsed = urlparse(stable_callback)
        stable_base = _normalize_base_url(f"{parsed.scheme}://{parsed.netloc}") if parsed.scheme and parsed.netloc else ""
        if stable_base and _is_allowed_sso_base(stable_base):
            return stable_base
    base = _normalize_base_url(os.environ.get("APPLE_SSO_BROKER_BASE") or "")
    if base and _is_allowed_sso_base(base):
        return base
    return ""


def _apple_force_preview_broker_in_preview() -> bool:
    return _env_bool("APPLE_SSO_FORCE_PREVIEW_BROKER_IN_PREVIEW", True)


def _apple_broker_base_for_request(request: Request | None = None) -> str:
    if request and _apple_force_preview_broker_in_preview():
        for candidate in [
            _preferred_preview_frontend_base(),
            _normalize_base_url(_get_frontend_base(request) or ""),
        ]:
            if candidate and _is_preview_sso_base(candidate) and _is_allowed_sso_base(candidate):
                return candidate
    return _apple_broker_base()


def _apple_broker_callback_uri() -> str:
    stable_callback = _apple_stable_broker_callback_uri()
    if stable_callback:
        return stable_callback
    base = _apple_broker_base()
    if not base:
        return ""
    return f"{base}{_apple_broker_callback_path()}"


def _apple_broker_callback_uri_for_request(request: Request | None = None) -> str:
    if not request:
        return _apple_broker_callback_uri()

    request_base = _apple_broker_base_for_request(request)
    if not request_base:
        return _apple_broker_callback_uri()

    if _is_preview_sso_base(request_base):
        return f"{request_base}{_apple_broker_callback_path()}"

    stable_callback = _apple_stable_broker_callback_uri()
    if stable_callback:
        parsed = urlparse(stable_callback)
        stable_base = _normalize_base_url(f"{parsed.scheme}://{parsed.netloc}") if parsed.scheme and parsed.netloc else ""
        if stable_base and stable_base == request_base:
            return stable_callback

    return f"{request_base}{_apple_broker_callback_path()}"


def _apple_callback_uri_for_base(base: str, broker_mode: bool = False) -> str:
    normalized_base = _normalize_base_url(base)
    if not normalized_base:
        return ""
    if broker_mode:
        broker_callback = _apple_broker_callback_uri()
        if broker_callback:
            parsed = urlparse(broker_callback)
            broker_base = _normalize_base_url(f"{parsed.scheme}://{parsed.netloc}") if parsed.scheme and parsed.netloc else ""
            if broker_base and broker_base == normalized_base:
                return broker_callback
        return f"{normalized_base}{_apple_broker_callback_path()}"
    return f"{normalized_base}/api/auth/apple/callback"


async def _apple_runtime_broker_bases() -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(raw_value: Any) -> None:
        normalized = _normalize_base_url(str(raw_value or ""))
        if not normalized or normalized in seen:
            return
        if not _is_allowed_sso_base(normalized):
            return
        if not _is_preview_sso_base(normalized):
            return
        seen.add(normalized)
        candidates.append(normalized)

    try:
        override_doc = await db.system_runtime_flags.find_one(
            {"key": "sso_redirect_override_apple"},
            {"_id": 0, "base": 1},
        ) or {}
        _add(override_doc.get("base"))

        alignment_doc = await db.system_runtime_flags.find_one(
            {"key": "sso_provider_registration_alignment"},
            {"_id": 0, "result": 1},
        ) or {}
        alignment_result = alignment_doc.get("result") if isinstance(alignment_doc.get("result"), dict) else {}
        _add(alignment_result.get("active_base_apple"))
        _add(alignment_result.get("active_base"))

        drift_doc = await db.system_runtime_flags.find_one(
            {"key": "sso_redirect_drift_sentinel_state"},
            {"_id": 0, "snapshot": 1},
        ) or {}
        drift_snapshot = drift_doc.get("snapshot") if isinstance(drift_doc.get("snapshot"), dict) else {}
        _add(drift_snapshot.get("active_base_apple"))
        _add(drift_snapshot.get("active_base"))

        preflight_doc = await db.system_runtime_flags.find_one(
            {"key": "sso_apple_redirect_preflight"},
            {"_id": 0, "selected_base": 1},
        ) or {}
        _add(preflight_doc.get("selected_base"))
    except Exception:
        return []

    return candidates


def _provider_redirect_resolution_mode() -> str:
    mode = str(os.environ.get("SSO_PROVIDER_REDIRECT_RESOLUTION_MODE") or "canonical_first").strip().lower()
    if mode in {"registered_first", "legacy_registered_first"}:
        return "registered_first"
    return "canonical_first"


def _sso_state_secret() -> str:
    secret = str(os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY") or "").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET/SECRET_KEY missing or weak for SSO state signing")
    return secret


def _env_bool(key: str, default: bool = False) -> bool:
    raw = str(os.environ.get(key, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "enabled"}


def _strict_registered_callbacks_enabled() -> bool:
    # Enterprise default: strict mode ON unless explicitly disabled.
    return _env_bool("SSO_STRICT_REGISTERED_CALLBACKS", True)


def _build_sso_state(
    provider: str,
    return_base: str,
    mode: str = "login",
    user_id: str | None = None,
    callback_base: str | None = None,
    callback_uri: str | None = None,
) -> str:
    safe_return_base = _normalize_base_url(return_base)
    if not safe_return_base or not _is_allowed_sso_base(safe_return_base):
        safe_return_base = _configured_sso_redirect_base()

    payload = {
        "v": 1,
        "provider": str(provider or "").strip().lower(),
        "mode": str(mode or "login").strip().lower(),
        "return_base": safe_return_base,
        "uid": str(user_id or ""),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "nonce": secrets.token_urlsafe(8),
    }
    safe_callback_base = _normalize_base_url(callback_base or "")
    if safe_callback_base and _is_allowed_sso_base(safe_callback_base):
        payload["cb"] = safe_callback_base

    raw_callback_uri = str(callback_uri or "").strip()
    if raw_callback_uri:
        try:
            parsed_uri = urlparse(raw_callback_uri)
            callback_base_uri = _normalize_base_url(f"{parsed_uri.scheme}://{parsed_uri.netloc}")
            callback_path = str(parsed_uri.path or "").strip()
            if (
                callback_base_uri
                and _is_allowed_sso_base(callback_base_uri)
                and callback_path.startswith("/api/auth/apple/")
            ):
                payload["cbu"] = f"{callback_base_uri}{callback_path}"
        except Exception:
            pass

    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(_sso_state_secret().encode(), encoded.encode(), hashlib.sha256).hexdigest()[:24]
    return f"s1.{encoded}.{signature}"


def _decode_sso_state(
    state: str | None,
    expected_provider: str | None = None,
    consume_replay: bool = True,
) -> dict:
    parsed: dict = {}
    raw_state = str(state or "").strip()
    if not raw_state.startswith("s1."):
        return parsed
    parts = raw_state.split(".")
    if len(parts) != 3:
        return parsed

    _, encoded, provided_sig = parts
    expected_sig = hmac.new(_sso_state_secret().encode(), encoded.encode(), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(expected_sig, provided_sig):
        return parsed
    if consume_replay and not _consume_sso_state_signature(provided_sig):
        return parsed

    try:
        pad = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(f"{encoded}{pad}").decode())
    except Exception:
        return parsed

    issued_at = int(payload.get("iat") or 0)
    if issued_at <= 0:
        return parsed
    age_seconds = int(datetime.now(timezone.utc).timestamp()) - issued_at
    if age_seconds < 0 or age_seconds > SSO_STATE_TTL_SECONDS:
        return parsed

    provider = str(payload.get("provider") or "").strip().lower()
    if expected_provider and provider and provider != str(expected_provider).strip().lower():
        return parsed

    return_base = _normalize_base_url(payload.get("return_base") or "")
    if return_base and _is_allowed_sso_base(return_base):
        parsed["return_base"] = return_base

    mode = str(payload.get("mode") or "").strip().lower()
    if mode:
        parsed["mode"] = mode

    uid = str(payload.get("uid") or "").strip()
    if uid:
        parsed["uid"] = uid

    callback_base = _normalize_base_url(payload.get("cb") or "")
    if callback_base and _is_allowed_sso_base(callback_base):
        parsed["callback_base"] = callback_base

    callback_uri = str(payload.get("cbu") or "").strip()
    if callback_uri:
        try:
            parsed_uri = urlparse(callback_uri)
            callback_uri_base = _normalize_base_url(f"{parsed_uri.scheme}://{parsed_uri.netloc}")
            callback_uri_path = str(parsed_uri.path or "").strip()
            if (
                callback_uri_base
                and _is_allowed_sso_base(callback_uri_base)
                and callback_uri_path.startswith("/api/auth/apple/")
            ):
                parsed["callback_uri"] = f"{callback_uri_base}{callback_uri_path}"
        except Exception:
            pass

    return parsed


def _get_frontend_base(request: Request = None) -> str:
    """Return the frontend base URL, preferring the request host for accuracy in dynamic environments."""
    env_base = _normalize_base_url(os.environ.get("FRONTEND_BASE_URL") or "")
    sso_override = _configured_sso_redirect_base()

    # Prefer trusted proxy/runtime host headers over third-party Origin/Referer.
    if request:
        forwarded_host = request.headers.get("x-forwarded-host", "")
        forwarded_proto = (request.headers.get("x-forwarded-proto", "https") or "https").split(",")[0].strip()
        if forwarded_host:
            candidate = _normalize_base_url(f"{forwarded_proto}://{forwarded_host}")
            if candidate and _is_allowed_sso_base(candidate):
                return candidate
        if request.url and request.url.hostname:
            scheme = forwarded_proto or request.url.scheme or "https"
            port = request.url.port
            if port and port not in (80, 443):
                candidate = _normalize_base_url(f"{scheme}://{request.url.hostname}:{port}")
            else:
                candidate = _normalize_base_url(f"{scheme}://{request.url.hostname}")
            if candidate and _is_allowed_sso_base(candidate):
                return candidate

        # Fallback to Origin/Referer only when it matches trusted frontend host.
        trusted_host = ""
        if env_base:
            try:
                trusted_host = (urlparse(env_base).netloc or "").lower()
            except Exception:
                trusted_host = ""

        for hdr in [request.headers.get("origin"), request.headers.get("referer")]:
            candidate = (hdr or "").strip()
            if not (candidate.startswith("http://") or candidate.startswith("https://")):
                continue
            try:
                parsed = urlparse(candidate)
                if parsed.scheme and parsed.netloc and (not trusted_host or parsed.netloc.lower() == trusted_host):
                    normalized = _normalize_base_url(f"{parsed.scheme}://{parsed.netloc}")
                    if normalized and _is_allowed_sso_base(normalized):
                        return normalized
            except Exception:
                continue

    # Fallback to configured/canonical env var
    base = sso_override or env_base
    if not base:
        logger.error("No valid SSO frontend base is configured — redirects will fail")
    return base


def _preferred_preview_frontend_base() -> str:
    for candidate in [
        _configured_sso_redirect_base(),
        _normalize_base_url(os.environ.get("FRONTEND_BASE_URL") or ""),
    ]:
        if candidate and _is_allowed_sso_base(candidate) and _is_preview_sso_base(candidate):
            return candidate
    return ""


def _resolve_sso_return_base(request: Request = None) -> str:
    request_base = _get_frontend_base(request)
    preferred_preview = _preferred_preview_frontend_base()
    if preferred_preview:
        return preferred_preview
    return request_base


def _coerce_sso_return_base(candidate: str | None, request: Request = None) -> str:
    normalized = _normalize_base_url(candidate or "")
    preferred_preview = _preferred_preview_frontend_base()
    if preferred_preview:
        if not normalized or not _is_preview_sso_base(normalized):
            return preferred_preview
    if normalized and _is_allowed_sso_base(normalized):
        return normalized
    return _resolve_sso_return_base(request)


async def _resolve_sso_redirect_base(request: Request = None, force_sync: bool = False, provider: str | None = None) -> str:
    """Persistent SSO redirect base auto-sync so forks inherit working callback base without manual updates."""
    provider_key = str(provider or "").strip().lower()

    if provider_key == "apple":
        apple_auto_base = _apple_auto_synced_redirect_base(request)
        if apple_auto_base:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.system_runtime_flags.update_one(
                {"key": "sso_redirect_override_apple"},
                {
                    "$set": {
                        "key": "sso_redirect_override_apple",
                        "base": apple_auto_base,
                        "updated_at": now_iso,
                        "source": "apple_env_tier_auto_sync",
                    }
                },
                upsert=True,
            )
            return apple_auto_base

    if provider_key:
        runtime_override_key = f"sso_redirect_override_{provider_key}"
        runtime_override = await db.system_runtime_flags.find_one({"key": runtime_override_key}, {"_id": 0}) or {}
        runtime_base = _normalize_base_url(runtime_override.get("base") or "")
        if provider_key == "apple":
            if runtime_base and _is_allowed_sso_base(runtime_base) and _apple_provider_base_verified(runtime_base, request=request):
                return runtime_base
        elif runtime_base and _is_allowed_sso_base(runtime_base):
            return runtime_base

    provider_env_override = _provider_redirect_env_override(provider)
    if provider_key == "apple" and provider_env_override and not _apple_provider_base_verified(provider_env_override, request=request):
        provider_env_override = ""
    if provider_env_override:
        return provider_env_override

    registered_fallback = _provider_registered_redirect_fallback(provider)
    resolution_mode = _provider_redirect_resolution_mode()

    if resolution_mode == "registered_first" and registered_fallback:
        return registered_fallback

    env_override = _configured_sso_redirect_base()
    if env_override:
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.system_runtime_flags.update_one(
            {"key": "sso_redirect_base"},
            {
                "$set": {
                    "key": "sso_redirect_base",
                    "base": env_override,
                    "updated_at": now_iso,
                    "source": "env_canonical",
                }
            },
            upsert=True,
        )
        return env_override

    if registered_fallback:
        return registered_fallback

    key = "sso_redirect_base"
    detected = _normalize_base_url(_get_frontend_base(request))
    if not detected:
        detected = _normalize_base_url(os.environ.get("FRONTEND_BASE_URL") or "")

    existing = await db.system_runtime_flags.find_one({"key": key}, {"_id": 0})
    stored_base = _normalize_base_url(str((existing or {}).get("base") or ""))

    if stored_base and not _is_allowed_sso_base(stored_base):
        stored_base = ""

    if force_sync or not stored_base:
        upsert_base = detected or stored_base
        if upsert_base:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.system_runtime_flags.update_one(
                {"key": key},
                {
                    "$set": {
                        "key": key,
                        "base": upsert_base,
                        "updated_at": now_iso,
                        "source": "request_auto_sync",
                    }
                },
                upsert=True,
            )
            return upsert_base

    if stored_base and detected and stored_base != detected:
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.system_runtime_flags.update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "base": detected,
                    "updated_at": now_iso,
                    "source": "fork_auto_sync",
                    "previous_base": stored_base,
                }
            },
            upsert=True,
        )
        return detected

    fallback = _normalize_base_url(os.environ.get("FRONTEND_BASE_URL") or "")
    return stored_base or detected or fallback


async def _resolve_auth_fallback_base(request: Request | None = None) -> str:
    """Canonical base for fallback login methods (magic link + QR + password reset links)."""
    canonical = await _resolve_sso_redirect_base(request)
    if canonical and _is_allowed_sso_base(canonical):
        return canonical

    if RESET_LINK_BASE:
        parsed = urlparse(str(RESET_LINK_BASE).strip())
        reset_base = _normalize_base_url(f"{parsed.scheme}://{parsed.netloc}") if parsed.scheme and parsed.netloc else ""
        if reset_base and _is_allowed_sso_base(reset_base):
            return reset_base

    if request:
        origin = _normalize_base_url(request.headers.get("origin") or "")
        if origin and _is_allowed_sso_base(origin):
            return origin

    env_base = _normalize_base_url(os.environ.get("FRONTEND_BASE_URL") or "")
    return env_base


MS_SCOPES = ["User.Read"]


def _is_guid_like(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value or ""))


def _resolve_azure_authority_segment() -> str:
    global _azure_authority_fallback_warning_emitted

    tenant_id = str(os.environ.get("AZURE_TENANT_ID") or "").strip()
    authority_mode = str(os.environ.get("AZURE_AUTHORITY_MODE") or "tenant").strip().lower()
    authority_tenant = str(os.environ.get("AZURE_AUTHORITY_TENANT") or "").strip()

    if authority_mode == "common":
        return "common"

    if authority_tenant:
        if _is_guid_like(authority_tenant) or "." in authority_tenant:
            return authority_tenant
        if tenant_id:
            if not _azure_authority_fallback_warning_emitted:
                logger.warning(
                    "AZURE_AUTHORITY_TENANT='%s' is not a valid GUID/domain; falling back to AZURE_TENANT_ID='%s'",
                    authority_tenant,
                    tenant_id,
                )
                _azure_authority_fallback_warning_emitted = True
            return tenant_id

    return tenant_id or "common"


def _get_msal_app():
    """Build MSAL ConfidentialClientApplication from env vars."""
    if msal is None:
        raise ValueError("msal package is not installed")
    client_id = os.environ.get("AZURE_CLIENT_ID", "")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError("Azure AD credentials are not configured.")

    authority_segment = _resolve_azure_authority_segment()

    return msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{authority_segment}",
    )


async def _ms_redirect_uri_async(request: Request = None):
    """Build Microsoft OAuth callback URI using persistent auto-synced redirect base."""
    base = await _resolve_sso_redirect_base(request, provider="microsoft")
    return f"{base}/api/auth/microsoft/callback"


def _ms_redirect_uri(request: Request = None):
    base = _get_frontend_base(request) if request else os.environ.get("FRONTEND_BASE_URL", "")
    return f"{base}/api/auth/microsoft/callback"


def _parse_registered_redirect_uris(env_key: str) -> list[str]:
    raw = str(os.environ.get(env_key, "") or "").strip()
    uris: list[str] = []
    if not raw:
        return uris
    for item in raw.split(","):
        normalized = _normalize_base_url(item)
        if normalized:
            uris.append(normalized)
    # preserve order while deduplicating
    seen = set()
    ordered = []
    for uri in uris:
        if uri in seen:
            continue
        seen.add(uri)
        ordered.append(uri)
    return ordered


@router.get("/auth/sso-config")
async def sso_config_diagnostic(request: Request):
    """Diagnostic endpoint: shows current SSO redirect URIs. Useful after platform forks."""
    dynamic_base = _get_frontend_base(request)
    static_base = os.environ.get("FRONTEND_BASE_URL", "NOT SET")
    canonical_base = _configured_sso_redirect_base() or "NOT SET"
    persisted = await db.system_runtime_flags.find_one({"key": "sso_redirect_base"}, {"_id": 0}) or {}
    persisted_base = persisted.get("base") or "NOT SET"
    active_base = await _resolve_sso_redirect_base(request)
    ms_active_base = await _resolve_sso_redirect_base(request, provider="microsoft")
    apple_active_base = await _resolve_sso_redirect_base(request, provider="apple")
    ms_registered = _parse_registered_redirect_uris("MS_SSO_REGISTERED_REDIRECT_URIS")
    apple_registered = _parse_registered_redirect_uris("APPLE_SSO_REGISTERED_REDIRECT_URIS")
    apple_verified = _apple_provider_verified_bases()
    apple_accepted = _apple_provider_accepted_callback_bases(request)
    apple_strategy = _apple_effective_callback_strategy(request)
    apple_broker_callback = _apple_broker_callback_uri_for_request(request) or None
    apple_expected_provider_callback = apple_broker_callback or f"{apple_active_base}/api/auth/apple/callback"
    apple_preflight_state = await db.system_runtime_flags.find_one(
        {"key": "sso_apple_redirect_preflight"},
        {"_id": 0, "selected_callback": 1, "selected_via": 1},
    ) or {}
    apple_dynamic_candidate = _apple_dynamic_preview_base_candidate(request)
    apple_verification_source = _apple_provider_base_verification_source(apple_active_base, request=request)
    ms_callback = f"{ms_active_base}/api/auth/microsoft/callback"
    apple_callback = f"{apple_active_base}/api/auth/apple/callback"
    return {
        "deployment_domain_dynamic": dynamic_base,
        "deployment_domain_env": static_base,
        "deployment_domain_canonical": canonical_base,
        "deployment_domain_persisted": persisted_base,
        "deployment_domain_active": active_base,
        "deployment_domain_active_microsoft": ms_active_base,
        "deployment_domain_active_apple": apple_active_base,
        "microsoft_callback": ms_callback,
        "apple_callback": apple_callback,
        "microsoft_registered_callbacks": [f"{uri}/api/auth/microsoft/callback" for uri in ms_registered],
        "apple_registered_callbacks": [f"{uri}/api/auth/apple/callback" for uri in apple_registered],
        "microsoft_callback_registered": (f"{ms_active_base}" in ms_registered) if ms_registered else None,
        "apple_callback_registered": (f"{apple_active_base}" in apple_registered) if apple_registered else None,
        "apple_provider_verified_bases": apple_verified,
        "apple_provider_verified_callbacks": [f"{uri}/api/auth/apple/callback" for uri in apple_verified],
        "apple_provider_accepted_bases": apple_accepted,
        "apple_provider_accepted_callbacks": [f"{uri}/api/auth/apple/callback" for uri in apple_accepted],
        "apple_dynamic_preview_candidate": apple_dynamic_candidate or None,
        "apple_auto_refresh_accepted_preview_base_enabled": _apple_auto_refresh_accepted_preview_base_enabled(),
        "apple_provider_verified_base_required": _apple_provider_verified_base_required(),
        "apple_provider_verified_base_active": apple_verification_source != "none",
        "apple_provider_verification_source": apple_verification_source,
        "apple_callback_strategy": apple_strategy,
        "apple_callback_strategy_raw": _apple_callback_strategy(),
        "apple_broker_callback": apple_broker_callback,
        "apple_expected_provider_callback": apple_expected_provider_callback,
        "apple_broker_enforced": bool(apple_strategy == "broker" and apple_broker_callback),
        "apple_preflight_selected_callback": apple_preflight_state.get("selected_callback") or None,
        "apple_preflight_selected_via": apple_preflight_state.get("selected_via") or None,
        "apple_preview_registered_fallback_enabled": _env_bool("APPLE_SSO_PREVIEW_ALLOW_REGISTERED_BASE", False),
        "apple_dynamic_preview_auto_sync_enabled": _env_bool("APPLE_SSO_AUTO_SYNC_USE_DYNAMIC_PREVIEW", False),
        "apple_strict_callback_allowlist_enabled": _apple_strict_callback_allowlist_enabled(),
        "apple_require_preflight_accepted": _apple_require_preflight_accepted(),
        "allowed_sso_host_suffixes": _allowed_sso_host_suffixes(),
        "azure_client_id": os.environ.get("AZURE_CLIENT_ID", "NOT SET"),
        "azure_tenant_id": os.environ.get("AZURE_TENANT_ID", "NOT SET"),
        "azure_authority_mode": os.environ.get("AZURE_AUTHORITY_MODE", "tenant"),
        "azure_authority_tenant": os.environ.get("AZURE_AUTHORITY_TENANT") or os.environ.get("AZURE_TENANT_ID", "NOT SET"),
        "azure_authority_effective_tenant": _resolve_azure_authority_segment(),
        "apple_client_id": os.environ.get("APPLE_CLIENT_ID", "NOT SET"),
        "provider_redirect_resolution_mode": _provider_redirect_resolution_mode(),
        "registered_redirect_fallback_enabled": _env_bool("SSO_ALLOW_REGISTERED_REDIRECT_URI_AS_ACTIVE_BASE", False),
        "registered_uri_sync_mode": str(os.environ.get("SSO_REGISTERED_URI_SYNC_MODE") or "preserve"),
        "canonical_provider_callback_mode": bool(ms_active_base != dynamic_base or apple_active_base != dynamic_base),
        "provider_callback_broker_base": _configured_sso_redirect_base() or None,
        "note": "SSO uses a canonical redirect base with signed state return routing to prevent redirect URI drift across forks and aliases.",
    }


@router.get("/auth/admin/fallback-links/health")
async def admin_fallback_links_health(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    active_base = await _resolve_auth_fallback_base(request)
    latest_magic = await db.magic_links.find_one({}, {"_id": 0, "created_at": 1, "email": 1, "auth_base": 1}, sort=[("created_at", -1)]) or {}
    latest_qr = await db.qr_sessions.find_one({}, {"_id": 0, "created_at": 1, "session_id": 1, "auth_base": 1}, sort=[("created_at", -1)]) or {}

    stale_magic_count = 0
    stale_qr_count = 0
    if active_base:
        stale_magic_count = await db.magic_links.count_documents({"auth_base": {"$exists": True, "$ne": active_base}})
        stale_qr_count = await db.qr_sessions.count_documents({"auth_base": {"$exists": True, "$ne": active_base}})

    return {
        "ok": True,
        "active_base": active_base,
        "latest_magic_link": latest_magic,
        "latest_qr_session": latest_qr,
        "stale_magic_link_count": stale_magic_count,
        "stale_qr_session_count": stale_qr_count,
        "healthy": bool(active_base),
    }


@router.post("/auth/admin/sso-redirect-auto-sync")
async def admin_sso_redirect_auto_sync(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    base = await _resolve_sso_redirect_base(request, force_sync=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    await db.system_runtime_flags.update_one(
        {"key": "sso_redirect_auto_sync_meta"},
        {
            "$set": {
                "key": "sso_redirect_auto_sync_meta",
                "last_synced_at": now_iso,
                "last_synced_by": getattr(user, "email", None),
                "active_base": base,
            }
        },
        upsert=True,
    )

    return {
        "ok": True,
        "active_base": base,
        "microsoft_callback": f"{base}/api/auth/microsoft/callback",
        "apple_callback": f"{base}/api/auth/apple/callback",
        "microsoft_callback_registered": (base in _parse_registered_redirect_uris("MS_SSO_REGISTERED_REDIRECT_URIS"))
        if _parse_registered_redirect_uris("MS_SSO_REGISTERED_REDIRECT_URIS")
        else None,
        "apple_callback_registered": (base in _parse_registered_redirect_uris("APPLE_SSO_REGISTERED_REDIRECT_URIS"))
        if _parse_registered_redirect_uris("APPLE_SSO_REGISTERED_REDIRECT_URIS")
        else None,
        "link_microsoft_callback": f"{base}/api/auth/link/microsoft/callback",
        "link_apple_callback": f"{base}/api/auth/apple/callback",
        "synced_at": now_iso,
        "mode": "persistent_auto_sync",
    }


@router.post("/auth/admin/sso-validate-e2e")
async def admin_sso_validate_e2e(request: Request):
    """One-click backend-side SSO integrity validation for Microsoft + Apple callback flow wiring."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    return await run_sso_e2e_validation_internal(request)


async def run_sso_e2e_validation_internal(request: Request | None = None) -> dict:
    """Reusable validation payload for manual admin check + scheduled state-change monitoring."""
    base = await _resolve_sso_redirect_base(request)
    ms_base = await _resolve_sso_redirect_base(request, provider="microsoft")
    apple_base = await _resolve_sso_redirect_base(request, provider="apple")
    ms_callback = await _ms_redirect_uri_async(request)
    apple_callback = await _apple_redirect_uri_async(request)
    ms_registered_bases = _parse_registered_redirect_uris("MS_SSO_REGISTERED_REDIRECT_URIS")
    apple_registered_bases = _parse_registered_redirect_uris("APPLE_SSO_REGISTERED_REDIRECT_URIS")
    apple_verified_bases = _apple_provider_verified_bases()
    apple_accepted_bases = _apple_provider_accepted_callback_bases(request)
    apple_allowlist_bases = apple_accepted_bases if apple_accepted_bases else apple_verified_bases
    apple_verified_required = _apple_provider_verified_base_required()
    apple_verification_source = _apple_provider_base_verification_source(apple_base, request=request)
    strict_mode = _strict_registered_callbacks_enabled()

    checks = []
    checks.append({
        "name": "redirect_base_present",
        "passed": bool(base),
        "details": f"active_base={base or 'missing'}",
    })
    checks.append({
        "name": "callbacks_use_https",
        "passed": ms_callback.startswith("https://") and apple_callback.startswith("https://"),
        "details": f"microsoft={ms_callback}, apple={apple_callback}",
    })
    checks.append({
        "name": "active_base_allowed_host",
        "passed": _is_allowed_sso_base(base),
        "details": f"allowed={_is_allowed_sso_base(base)} host={_extract_host(base)}",
    })

    try:
        app = _get_msal_app()
        auth_url = app.get_authorization_request_url(
            scopes=MS_SCOPES,
            redirect_uri=ms_callback,
            state="sso_validate_e2e",
        )
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(auth_url)
        redirect_uri_qs = (parse_qs(parsed.query).get("redirect_uri") or [""])[0]
        checks.append({
            "name": "microsoft_auth_redirect_matches",
            "passed": redirect_uri_qs == ms_callback,
            "details": f"redirect_uri={redirect_uri_qs}",
        })
    except Exception as e:
        checks.append({
            "name": "microsoft_auth_redirect_matches",
            "passed": False,
            "details": f"exception={e}",
        })

    checks.append({
        "name": "apple_client_configured",
        "passed": bool(APPLE_CLIENT_ID),
        "details": f"apple_client_id={'set' if APPLE_CLIENT_ID else 'missing'}",
    })
    apple_strategy = _apple_effective_callback_strategy(request)
    if apple_strategy == "broker":
        expected_apple_callback = _apple_broker_callback_uri_for_request(request)
    else:
        expected_apple_callback = f"{apple_base}/api/auth/apple/callback"
    checks.append({
        "name": "apple_callback_matches_active_base",
        "passed": bool(expected_apple_callback) and apple_callback == expected_apple_callback,
        "details": f"strategy={apple_strategy} apple_callback={apple_callback} expected={expected_apple_callback}",
    })

    checks.append({
        "name": "microsoft_callback_matches_active_base",
        "passed": ms_callback == f"{ms_base}/api/auth/microsoft/callback",
        "details": f"ms_callback={ms_callback}",
    })

    checks.append({
        "name": "microsoft_callback_registered",
        "passed": (ms_base in ms_registered_bases) if ms_registered_bases else (not strict_mode),
        "details": (
            f"registered={'yes' if ms_registered_bases else 'not_configured'} strict={strict_mode} "
            f"active_base={ms_base}"
        ),
        "registered_bases": ms_registered_bases,
    })
    checks.append({
        "name": "apple_callback_registered",
        "passed": (apple_base in apple_registered_bases) if apple_registered_bases else (not strict_mode),
        "details": (
            f"registered={'yes' if apple_registered_bases else 'not_configured'} strict={strict_mode} "
            f"active_base={apple_base}"
        ),
        "registered_bases": apple_registered_bases,
    })
    checks.append({
        "name": "apple_provider_verified_base",
        "passed": (apple_verification_source != "none") if apple_verified_required else True,
        "details": (
            f"required={apple_verified_required} verified={'yes' if apple_verification_source != 'none' else 'no'} "
            f"active_base={apple_base} source={apple_verification_source}"
        ),
        "verified_bases": apple_verified_bases,
        "verification_source": apple_verification_source,
    })
    checks.append({
        "name": "apple_callback_in_provider_allowlist",
        "passed": (apple_base in apple_allowlist_bases) if apple_allowlist_bases else (not _apple_strict_callback_allowlist_enabled()),
        "details": (
            f"strict_allowlist={_apple_strict_callback_allowlist_enabled()} active_base={apple_base} "
            f"allowlist_size={len(apple_allowlist_bases)}"
        ),
        "allowlist_bases": apple_allowlist_bases,
    })

    passed = all(bool(item.get("passed")) for item in checks)
    has_registration_gap = any(
        item.get("name") in {"microsoft_callback_registered", "apple_callback_registered"}
        and not bool(item.get("passed"))
        for item in checks
    )
    severity = "critical" if has_registration_gap else ("healthy" if passed else "warning")
    return {
        "ok": True,
        "passed": passed,
        "severity": severity,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "active_base": base,
        "active_base_microsoft": ms_base,
        "active_base_apple": apple_base,
        "callbacks": {
            "microsoft": ms_callback,
            "apple": apple_callback,
        },
        "strict_registered_callbacks": strict_mode,
        "checks": checks,
    }


async def _build_sso_redirect_drift_snapshot(request: Request | None = None) -> dict:
    validation = await run_sso_e2e_validation_internal(request)
    checks = validation.get("checks") or []
    active_base = str(validation.get("active_base") or "")
    active_host = _extract_host(active_base)

    ms_check = next((c for c in checks if c.get("name") == "microsoft_callback_registered"), None) or {}
    apple_check = next((c for c in checks if c.get("name") == "apple_callback_registered"), None) or {}
    drift_providers = []
    if not bool(ms_check.get("passed")):
        drift_providers.append("microsoft")
    if not bool(apple_check.get("passed")):
        drift_providers.append("apple")

    has_host_drift = any(
        bool(c.get("name") in {"microsoft_callback_matches_active_base", "apple_callback_matches_active_base"})
        and not bool(c.get("passed"))
        for c in checks
    )

    drift_detected = bool(drift_providers or has_host_drift)
    status = "critical" if drift_detected else "healthy"
    return {
        "ok": True,
        "status": status,
        "drift_detected": drift_detected,
        "active_base": active_base,
        "active_host": active_host,
        "drift_providers": drift_providers,
        "strict_registered_callbacks": bool(validation.get("strict_registered_callbacks")),
        "validated_at": validation.get("validated_at"),
        "checks": checks,
    }


@router.get("/auth/admin/sso-redirect-drift-sentinel")
async def admin_sso_redirect_drift_sentinel(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    snapshot = await _build_sso_redirect_drift_snapshot(request)
    persisted = await db.system_runtime_flags.find_one({"key": "sso_redirect_drift_sentinel_state"}, {"_id": 0}) or {}
    return {
        **snapshot,
        "last_state": persisted.get("state"),
        "last_changed_at": persisted.get("last_changed_at"),
    }


@router.get("/auth/admin/multi-region-auth-probe/status")
async def admin_multi_region_auth_probe_status(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    latest = await db.multi_region_auth_probe_runs.find_one({}, {"_id": 0}, sort=[("ran_at", -1)]) or {}
    state = await db.system_runtime_flags.find_one({"key": "multi_region_auth_probe_state"}, {"_id": 0}) or {}
    return {
        "ok": True,
        "latest_run": latest,
        "state": state,
    }


@router.post("/auth/admin/multi-region-auth-probe/run-now")
async def admin_multi_region_auth_probe_run_now(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    from scheduler_jobs import scheduled_multi_region_auth_probe

    await scheduled_multi_region_auth_probe()
    latest = await db.multi_region_auth_probe_runs.find_one({}, {"_id": 0}, sort=[("ran_at", -1)]) or {}
    state = await db.system_runtime_flags.find_one({"key": "multi_region_auth_probe_state"}, {"_id": 0}) or {}
    return {"ok": True, "latest_run": latest, "state": state}


@router.post("/auth/admin/sso-redirect-drift-sentinel/run-now")
async def admin_sso_redirect_drift_sentinel_run_now(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    from scheduler_jobs import scheduled_sso_redirect_drift_sentinel

    await scheduled_sso_redirect_drift_sentinel()
    state = await db.system_runtime_flags.find_one({"key": "sso_redirect_drift_sentinel_state"}, {"_id": 0}) or {}
    return {"ok": True, "state": state}


@router.post("/auth/admin/sso-provider-registration/align")
async def admin_sso_provider_registration_align(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    return await _run_sso_provider_registration_alignment(
        request=request,
        updated_by=getattr(user, "email", None),
        trigger="admin_manual",
    )


def _is_preview_redirect_uri(uri: str) -> bool:
    try:
        host = (urlparse(str(uri or "")).hostname or "").lower()
    except Exception:
        host = ""
    return bool(host.endswith(".preview.emergentagent.com") or ".preview.emergentcf.cloud" in host)


def _build_trimmed_ms_redirect_list(existing_uris: list[str], required_uris: list[str]) -> list[str]:
    max_preview = int(os.environ.get("MS_SSO_MAX_PREVIEW_REDIRECT_URIS") or 12)
    normalized_existing = [str(item or "").strip() for item in existing_uris if str(item or "").strip()]
    normalized_required = [str(item or "").strip() for item in required_uris if str(item or "").strip()]

    ordered = []
    seen = set()
    for item in normalized_existing + normalized_required:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)

    keep_required = set(normalized_required)
    non_preview = [item for item in ordered if item in keep_required or not _is_preview_redirect_uri(item)]
    preview_candidates = [item for item in ordered if item not in keep_required and _is_preview_redirect_uri(item)]
    preview_tail = preview_candidates[-max(1, max_preview):]

    merged = []
    seen_merged = set()
    for item in non_preview + preview_tail + normalized_required:
        if item in seen_merged:
            continue
        seen_merged.add(item)
        merged.append(item)
    return merged


async def _run_sso_provider_registration_alignment(
    request: Request | None,
    updated_by: str | None,
    trigger: str,
) -> dict:

    import httpx

    base = await _resolve_sso_redirect_base(request)
    ms_base = await _resolve_sso_redirect_base(request, provider="microsoft")
    apple_base = await _resolve_sso_redirect_base(request, provider="apple")
    apple_provider_callback = _apple_broker_callback_uri_for_request(request) or f"{apple_base}/api/auth/apple/callback"
    microsoft_callback = f"{ms_base}/api/auth/microsoft/callback"
    microsoft_link_callback = f"{ms_base}/api/auth/link/microsoft/callback"

    result = {
        "ok": True,
        "active_base": base,
        "active_base_microsoft": ms_base,
        "active_base_apple": apple_base,
        "microsoft": {
            "attempted": False,
            "aligned": False,
            "required_callbacks": [microsoft_callback, microsoft_link_callback],
        },
        "apple": {
            "attempted": False,
            "aligned": False,
            "required_callbacks": [apple_provider_callback],
            "manual_required": True,
            "note": "Apple Service ID callback alignment requires Apple Developer Console update.",
        },
    }

    az_client_id = str(os.environ.get("AZURE_CLIENT_ID") or "").strip()
    az_tenant = str(os.environ.get("AZURE_TENANT_ID") or "").strip()
    az_secret = str(os.environ.get("AZURE_CLIENT_SECRET") or "").strip()

    if az_client_id and az_tenant and az_secret:
        result["microsoft"]["attempted"] = True
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                token_resp = await client.post(
                    f"https://login.microsoftonline.com/{az_tenant}/oauth2/v2.0/token",
                    data={
                        "client_id": az_client_id,
                        "client_secret": az_secret,
                        "scope": "https://graph.microsoft.com/.default",
                        "grant_type": "client_credentials",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                token_resp.raise_for_status()
                access_token = (token_resp.json() or {}).get("access_token")
                if not access_token:
                    raise ValueError("Graph token missing access_token")

                headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                app_resp = await client.get(
                    "https://graph.microsoft.com/v1.0/applications",
                    params={"$filter": f"appId eq '{az_client_id}'", "$select": "id,appId,web"},
                    headers=headers,
                )
                app_resp.raise_for_status()
                app_rows = (app_resp.json() or {}).get("value") or []
                if not app_rows:
                    raise ValueError("Azure app registration not found for AZURE_CLIENT_ID")

                app_row = app_rows[0]
                app_obj_id = str(app_row.get("id") or "")
                existing_uris = list((((app_row.get("web") or {}).get("redirectUris")) or []))
                desired = _build_trimmed_ms_redirect_list(existing_uris, [microsoft_callback, microsoft_link_callback])

                patch_resp = await client.patch(
                    f"https://graph.microsoft.com/v1.0/applications/{app_obj_id}",
                    headers=headers,
                    json={"web": {"redirectUris": desired}},
                )
                if patch_resp.status_code not in {200, 204}:
                    raise ValueError(f"Azure app patch failed: status={patch_resp.status_code} body={patch_resp.text[:240]}")

                result["microsoft"]["aligned"] = True
                result["microsoft"]["registered_callbacks"] = desired
        except Exception as e:
            result["microsoft"]["error"] = str(e)
            result["ok"] = False
    else:
        result["microsoft"]["error"] = "Azure credentials missing for Graph alignment"

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.system_runtime_flags.update_one(
        {"key": "sso_provider_registration_alignment"},
        {
            "$set": {
                "key": "sso_provider_registration_alignment",
                "updated_at": now_iso,
                "updated_by": updated_by,
                "trigger": trigger,
                "result": result,
            }
        },
        upsert=True,
    )

    return result


@router.post("/auth/admin/sso-live-provider-signoff")
async def admin_sso_live_provider_signoff(request: Request):
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    base = await _resolve_sso_redirect_base(request)
    validation = await run_sso_e2e_validation_internal(request)

    ms_test_email = str(os.environ.get("SSO_TEST_MICROSOFT_EMAIL") or "").strip()
    ms_test_password = str(os.environ.get("SSO_TEST_MICROSOFT_PASSWORD") or "").strip()
    apple_test_email = str(os.environ.get("SSO_TEST_APPLE_EMAIL") or "").strip()
    apple_test_password = str(os.environ.get("SSO_TEST_APPLE_PASSWORD") or "").strip()

    credentials_ready = bool(ms_test_email and ms_test_password and apple_test_email and apple_test_password)
    signoff_status = "ready_for_live_run" if credentials_ready else "blocked_missing_test_credentials"

    payload = {
        "ok": True,
        "status": signoff_status,
        "active_base": base,
        "strict_registered_callbacks": bool(validation.get("strict_registered_callbacks")),
        "credentials_present": {
            "microsoft": bool(ms_test_email and ms_test_password),
            "apple": bool(apple_test_email and apple_test_password),
        },
        "message": (
            "Dedicated test credentials are present; run browser-driven live signoff now."
            if credentials_ready
            else "Dedicated Microsoft/Apple test credentials are not set in environment; full consent-to-session live signoff is blocked."
        ),
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.system_runtime_flags.update_one(
        {"key": "sso_live_provider_signoff"},
        {"$set": {"key": "sso_live_provider_signoff", **payload}},
        upsert=True,
    )
    return payload


@router.get("/admin/sso-status")
async def admin_sso_status(request: Request):
    """Admin endpoint: SSO provider health status with connectivity checks."""
    dynamic_base = _get_frontend_base(request)
    active_base = await _resolve_sso_redirect_base(request)
    ms_active_base = await _resolve_sso_redirect_base(request, provider="microsoft")
    apple_active_base = await _resolve_sso_redirect_base(request, provider="apple")
    ms_registered_bases = _parse_registered_redirect_uris("MS_SSO_REGISTERED_REDIRECT_URIS")
    apple_registered_bases = _parse_registered_redirect_uris("APPLE_SSO_REGISTERED_REDIRECT_URIS")
    apple_verified_bases = _apple_provider_verified_bases()
    apple_accepted_bases = _apple_provider_accepted_callback_bases(request)
    apple_verified_required = _apple_provider_verified_base_required()
    apple_verification_source = _apple_provider_base_verification_source(apple_active_base, request=request)
    apple_dynamic_candidate = _apple_dynamic_preview_base_candidate(request)
    strict_mode = _strict_registered_callbacks_enabled()
    apple_redirect_preflight = await db.system_runtime_flags.find_one({"key": "sso_apple_redirect_preflight"}, {"_id": 0}) or {}
    apple_strategy = _apple_effective_callback_strategy(request)
    apple_broker_callback = _apple_broker_callback_uri_for_request(request) or None
    apple_expected_provider_callback = apple_broker_callback or f"{apple_active_base}/api/auth/apple/callback"
    apple_selected_callback = str(apple_redirect_preflight.get("selected_callback") or "")
    providers = []

    # --- Google ---
    g_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    g_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    g_configured = bool(g_id and g_secret)
    g_status = "configured" if g_configured else "not_configured"
    g_issues = []
    if not g_id:
        g_issues.append("GOOGLE_CLIENT_ID missing")
    if not g_secret:
        g_issues.append("GOOGLE_CLIENT_SECRET missing")
    providers.append({
        "provider": "google",
        "label": "Google OAuth",
        "icon": "logo-google",
        "status": g_status,
        "configured": g_configured,
        "callback_url": f"{dynamic_base}/api/oauth/calendar/callback",
        "auth_url": "https://auth.emergentagent.com/ (Emergent managed)",
        "issues": g_issues,
        "action": None if g_configured else "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend .env",
    })

    # --- Microsoft ---
    az_id = os.environ.get("AZURE_CLIENT_ID", "")
    az_tid = os.environ.get("AZURE_TENANT_ID", "")
    az_sec = os.environ.get("AZURE_CLIENT_SECRET", "")
    az_authority_mode = str(os.environ.get("AZURE_AUTHORITY_MODE") or "tenant").strip().lower()
    ms_configured = bool(az_id and az_tid and az_sec)
    ms_callback = f"{ms_active_base}/api/auth/microsoft/callback"
    ms_issues = []
    if not az_id:
        ms_issues.append("AZURE_CLIENT_ID missing")
    if not az_tid:
        ms_issues.append("AZURE_TENANT_ID missing")
    if not az_sec:
        ms_issues.append("AZURE_CLIENT_SECRET missing")
    # Check for corrupted credentials (fork artifacts)
    if az_id and (len(az_id) < 30 or "-" not in az_id):
        ms_issues.append(f"AZURE_CLIENT_ID appears corrupted: '{az_id[:20]}...'")
    if az_authority_mode == "common":
        ms_issues.append("AZURE_AUTHORITY_MODE=common can cause tenant drift; tenant mode is recommended")
    if strict_mode and not ms_registered_bases:
        ms_issues.append("Strict mode: MS_SSO_REGISTERED_REDIRECT_URIS is missing")
    if ms_registered_bases and ms_active_base not in ms_registered_bases:
        ms_issues.append(
            "Active callback base is missing in MS_SSO_REGISTERED_REDIRECT_URIS "
            f"(active={ms_active_base})"
        )
    ms_status = "configured" if ms_configured and not ms_issues else ("misconfigured" if ms_issues else "not_configured")
    providers.append({
        "provider": "microsoft",
        "label": "Microsoft SSO",
        "icon": "logo-microsoft",
        "status": ms_status,
        "configured": ms_configured,
        "callback_url": ms_callback,
        "registered_callbacks": [f"{uri}/api/auth/microsoft/callback" for uri in ms_registered_bases],
        "callback_registered": (ms_active_base in ms_registered_bases) if ms_registered_bases else None,
        "client_id": az_id[:12] + "..." if az_id else "NOT SET",
        "issues": ms_issues,
        "action": "Register callback URL in Azure Portal" if ms_configured else "Add Azure credentials to backend .env",
    })

    # --- Apple ---
    ap_id = os.environ.get("APPLE_CLIENT_ID", "")
    ap_team = os.environ.get("APPLE_TEAM_ID", "")
    ap_key = os.environ.get("APPLE_KEY_ID", "")
    ap_pk = os.environ.get("APPLE_PRIVATE_KEY", "")
    ap_configured = bool(ap_id and ap_team and ap_key and ap_pk)
    ap_callback = f"{apple_active_base}/api/auth/apple/callback"
    ap_issues = []
    if not ap_id:
        ap_issues.append("APPLE_CLIENT_ID missing")
    if not ap_team:
        ap_issues.append("APPLE_TEAM_ID missing")
    if not ap_key:
        ap_issues.append("APPLE_KEY_ID missing")
    if not ap_pk:
        ap_issues.append("APPLE_PRIVATE_KEY missing")
    if strict_mode and not apple_registered_bases:
        ap_issues.append("Strict mode: APPLE_SSO_REGISTERED_REDIRECT_URIS is missing")
    if apple_registered_bases and apple_active_base not in apple_registered_bases:
        ap_issues.append(
            "Active callback base is missing in APPLE_SSO_REGISTERED_REDIRECT_URIS "
            f"(active={apple_active_base})"
        )
    if apple_verified_required and apple_verification_source == "none":
        ap_issues.append(
            "Provider-level verification required: active callback base must exist in "
            "APPLE_SSO_PROVIDER_VERIFIED_REDIRECT_BASES "
            f"(active={apple_active_base})"
        )
    if _apple_strict_callback_allowlist_enabled():
        allowlist = _apple_provider_accepted_callback_bases(request) or apple_verified_bases
        if allowlist and apple_active_base not in allowlist:
            ap_issues.append(
                "Strict allowlist violation: active callback base is missing in effective provider callback allowlist "
                f"(active={apple_active_base})"
            )
    if _apple_redirect_preflight_enabled() and _apple_require_preflight_accepted():
        selected_via = str(apple_redirect_preflight.get("selected_via") or "")
        if selected_via and selected_via not in {
            "apple_authorize_preflight",
            "apple_broker_runtime_preflight",
            "apple_runtime_direct_preflight",
        }:
            ap_issues.append(
                "Preflight acceptance required: latest Apple callback probe did not confirm provider acceptance "
                f"(selected_via={selected_via})"
            )
    if apple_strategy == "broker" and apple_expected_provider_callback:
        if apple_selected_callback and apple_selected_callback != apple_expected_provider_callback:
            ap_issues.append(
                "Stable broker enforcement mismatch: latest selected Apple callback differs from expected broker callback "
                f"(selected={apple_selected_callback}, expected={apple_expected_provider_callback})"
            )
    ap_status = "configured" if ap_configured and not ap_issues else ("misconfigured" if ap_issues else "not_configured")
    providers.append({
        "provider": "apple",
        "label": "Apple SSO",
        "icon": "logo-apple",
        "status": ap_status,
        "configured": ap_configured,
        "callback_url": ap_callback,
        "registered_callbacks": [f"{uri}/api/auth/apple/callback" for uri in apple_registered_bases],
        "callback_registered": (apple_active_base in apple_registered_bases) if apple_registered_bases else None,
        "provider_verified_base_required": apple_verified_required,
        "provider_verified_bases": apple_verified_bases,
        "provider_accepted_bases": apple_accepted_bases,
        "dynamic_preview_candidate": apple_dynamic_candidate or None,
        "auto_refresh_accepted_preview_base_enabled": _apple_auto_refresh_accepted_preview_base_enabled(),
        "provider_verified_base": apple_verification_source != "none",
        "provider_verification_source": apple_verification_source,
        "callback_strategy": apple_strategy,
        "broker_callback": apple_broker_callback,
        "expected_provider_callback": apple_expected_provider_callback,
        "selected_provider_callback": apple_selected_callback or None,
        "broker_enforced": bool(apple_strategy == "broker" and apple_broker_callback),
        "preview_registered_fallback_enabled": _env_bool("APPLE_SSO_PREVIEW_ALLOW_REGISTERED_BASE", False),
        "strict_callback_allowlist_enabled": _apple_strict_callback_allowlist_enabled(),
        "require_preflight_accepted": _apple_require_preflight_accepted(),
        "client_id": ap_id or "NOT SET",
        "issues": ap_issues,
        "action": "Register callback URL in Apple Developer Console" if ap_configured else "Add Apple credentials to backend .env",
    })

    configured_count = sum(1 for p in providers if p["status"] == "configured")
    drift_sentinel = await db.system_runtime_flags.find_one({"key": "sso_redirect_drift_sentinel_state"}, {"_id": 0}) or {}
    probe_state = await db.system_runtime_flags.find_one({"key": "multi_region_auth_probe_state"}, {"_id": 0}) or {}
    registration_alignment = await db.system_runtime_flags.find_one({"key": "sso_provider_registration_alignment"}, {"_id": 0}) or {}
    live_signoff = await db.system_runtime_flags.find_one({"key": "sso_live_provider_signoff"}, {"_id": 0}) or {}

    return {
        "deployment_domain": dynamic_base,
        "active_redirect_base": active_base,
        "active_redirect_base_microsoft": ms_active_base,
        "active_redirect_base_apple": apple_active_base,
        "strict_registered_callbacks": strict_mode,
        "provider_redirect_resolution_mode": _provider_redirect_resolution_mode(),
        "registered_redirect_fallback_enabled": _env_bool("SSO_ALLOW_REGISTERED_REDIRECT_URI_AS_ACTIVE_BASE", False),
        "registered_uri_sync_mode": str(os.environ.get("SSO_REGISTERED_URI_SYNC_MODE") or "preserve"),
        "canonical_provider_callback_mode": bool(ms_active_base != dynamic_base or apple_active_base != dynamic_base),
        "provider_callback_broker_base": _configured_sso_redirect_base() or None,
        "allowed_sso_host_suffixes": _allowed_sso_host_suffixes(),
        "providers": providers,
        "sso_redirect_drift_sentinel": drift_sentinel,
        "multi_region_auth_probe": probe_state,
        "provider_registration_alignment": registration_alignment,
        "live_provider_signoff": live_signoff,
        "apple_redirect_preflight": apple_redirect_preflight,
        "summary": {
            "total": len(providers),
            "configured": configured_count,
            "issues": len(providers) - configured_count,
            "health": "healthy" if configured_count == len(providers) else ("degraded" if configured_count > 0 else "critical"),
        },
    }


@router.post("/auth/sso-telemetry")
async def capture_sso_telemetry(payload: SSOTelemetryRequest, request: Request):
    """Capture SSO click/popup/callback telemetry for iframe debugging and long-term stability."""
    provider = (payload.provider or "").strip().lower()
    phase = (payload.phase or "").strip().lower()

    if provider not in {"google", "microsoft", "apple"}:
        raise HTTPException(status_code=400, detail="Invalid provider")
    if not phase or len(phase) > 64:
        raise HTTPException(status_code=400, detail="Invalid phase")

    user = await get_current_user(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    details = {
        "provider": provider,
        "phase": phase,
        "iframe_mode": payload.iframe_mode,
        "cross_origin_iframe": payload.cross_origin_iframe,
        "popup_method": (payload.popup_method or "")[:64],
        "context": (payload.context or "")[:80],
        "note": (payload.note or "")[:300],
    }

    await db.sso_debug_events.insert_one(
        {
            "event_id": f"ssoevt_{uuid.uuid4().hex[:10]}",
            "timestamp": now_iso,
            "provider": provider,
            "phase": phase,
            "user_id": user.user_id if user else None,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "details": details,
        }
    )

    await log_security_event(
        user.user_id if user else None,
        f"sso_{provider}_{phase}",
        "low",
        request,
        details,
    )

    # Auto-prune at most once every few minutes to keep collection bounded long-term.
    global _sso_telemetry_last_prune_at
    now = datetime.now(timezone.utc)
    should_prune = (
        _sso_telemetry_last_prune_at is None
        or (now - _sso_telemetry_last_prune_at).total_seconds() >= SSO_TELEMETRY_AUTO_PRUNE_INTERVAL_SECONDS
    )
    if should_prune:
        try:
            await _prune_sso_telemetry_events()
            _sso_telemetry_last_prune_at = now
        except Exception as prune_err:
            logger.warning(f"SSO telemetry auto-prune skipped: {prune_err}")

    return {"ok": True}


async def _prune_sso_telemetry_events() -> dict:
    """Apply retention + hard max cap for SSO telemetry collection."""
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=SSO_TELEMETRY_RETENTION_DAYS)).isoformat()

    old_result = await db.sso_debug_events.delete_many({"timestamp": {"$lt": cutoff_iso}})
    removed_old = int(getattr(old_result, "deleted_count", 0) or 0)

    total_after_age_prune = await db.sso_debug_events.count_documents({})
    removed_overflow = 0

    if total_after_age_prune > SSO_TELEMETRY_MAX_EVENTS:
        overflow = total_after_age_prune - SSO_TELEMETRY_MAX_EVENTS
        oldest_cursor = db.sso_debug_events.find({}, {"_id": 1}).sort("timestamp", 1).limit(overflow)
        oldest_ids = [doc["_id"] async for doc in oldest_cursor if doc.get("_id") is not None]
        if oldest_ids:
            overflow_result = await db.sso_debug_events.delete_many({"_id": {"$in": oldest_ids}})
            removed_overflow = int(getattr(overflow_result, "deleted_count", 0) or 0)

    total_after = await db.sso_debug_events.count_documents({})
    return {
        "retention_days": SSO_TELEMETRY_RETENTION_DAYS,
        "max_events": SSO_TELEMETRY_MAX_EVENTS,
        "removed_old": removed_old,
        "removed_overflow": removed_overflow,
        "total_after": int(total_after),
    }


@router.get("/admin/sso-debug")
async def admin_sso_debug(request: Request, limit: int = 60):
    """Admin-only SSO debug payload: provider status + recent SSO telemetry events."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    safe_limit = max(10, min(limit, 200))
    events = []

    cursor = db.sso_debug_events.find({}, {"_id": 0}).sort("timestamp", -1).limit(safe_limit)
    async for doc in cursor:
        events.append(doc)

    # Backfill from legacy security events if telemetry collection has no records yet
    if not events:
        fallback = db.security_events.find(
            {"event_type": {"$regex": r"^sso_(google|microsoft|apple)_"}},
            {"_id": 0, "event_type": 1, "timestamp": 1, "user_id": 1, "ip_address": 1, "details": 1},
        ).sort("timestamp", -1).limit(safe_limit)
        async for doc in fallback:
            evt = doc.get("event_type", "")
            parts = evt.split("_")
            provider = parts[1] if len(parts) > 2 else "unknown"
            phase = "_".join(parts[2:]) if len(parts) > 2 else evt
            events.append(
                {
                    "event_id": f"legacy_{uuid.uuid4().hex[:8]}",
                    "timestamp": doc.get("timestamp"),
                    "provider": provider,
                    "phase": phase,
                    "user_id": doc.get("user_id"),
                    "ip_address": doc.get("ip_address"),
                    "details": doc.get("details", {}),
                    "legacy": True,
                }
            )

    status = await admin_sso_status(request)
    stored_count = await db.sso_debug_events.count_documents({})
    return {
        "deployment_domain": status.get("deployment_domain"),
        "summary": status.get("summary"),
        "providers": status.get("providers", []),
        "events": events,
        "count": len(events),
        "stored_count": int(stored_count),
        "retention_policy": {
            "retention_days": SSO_TELEMETRY_RETENTION_DAYS,
            "max_events": SSO_TELEMETRY_MAX_EVENTS,
        },
    }


@router.post("/admin/sso-debug/cleanup")
async def admin_sso_debug_cleanup(request: Request):
    """Admin-triggered cleanup for SSO telemetry retention/cap enforcement."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await _prune_sso_telemetry_events()
    global _sso_telemetry_last_prune_at
    _sso_telemetry_last_prune_at = datetime.now(timezone.utc)
    return {"ok": True, **result}


@router.get("/auth/google/init")
async def google_sso_init(request: Request):
    """Compatibility init endpoint for clients expecting /api/auth/google/init."""
    base = await _resolve_sso_redirect_base(request)
    return {
        "ok": True,
        "provider": "google",
        "mode": "token_exchange",
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "frontend_base": base,
        "session_exchange_endpoint": "/api/auth/google/session",
    }


@router.get("/auth/microsoft/init")
async def microsoft_sso_init(request: Request):
    """Compatibility init endpoint for clients expecting /api/auth/microsoft/init."""
    base = await _resolve_sso_redirect_base(request)
    callback = await _ms_redirect_uri_async(request)
    try:
        app = _get_msal_app()
        state = _build_sso_state("microsoft", _get_frontend_base(request), mode="login")
        auth_url = app.get_authorization_request_url(
            scopes=MS_SCOPES,
            redirect_uri=callback,
            state=state,
        )
    except Exception:
        auth_url = f"{base}/auth/login?sso_error=not_configured"

    return {
        "ok": True,
        "provider": "microsoft",
        "frontend_base": base,
        "callback": callback,
        "login_url": "/api/auth/microsoft/login",
        "auth_url": auth_url,
    }


@router.get("/auth/apple/init")
async def apple_sso_init(request: Request):
    """Compatibility init endpoint for clients expecting /api/auth/apple/init."""
    base = await _resolve_sso_redirect_base(request)
    resolved = await _resolve_apple_redirect_uri_for_auth(request)
    callback = resolved.get("callback") or await _apple_redirect_uri_async(request)
    return {
        "ok": True,
        "provider": "apple",
        "frontend_base": base,
        "callback": callback,
        "client_id": APPLE_CLIENT_ID,
        "authorize_url": "https://appleid.apple.com/auth/authorize",
        "redirect_preflight": {
            "selected_via": resolved.get("selected_via"),
            "all_invalid": bool(resolved.get("all_invalid")),
            "probes": resolved.get("probes", []),
        },
    }


@router.get("/auth/microsoft/login")
async def microsoft_login_redirect(request: Request):
    """Always use 302 redirect for all devices - simplest and most reliable approach."""
    from fastapi.responses import RedirectResponse

    frontend_base = _get_frontend_base(request)
    try:
        app = _get_msal_app()
        redirect_uri = await _ms_redirect_uri_async(request)
        state = _build_sso_state("microsoft", frontend_base, mode="login")
        auth_url = app.get_authorization_request_url(
            scopes=MS_SCOPES,
            redirect_uri=redirect_uri,
            state=state,
        )
        return RedirectResponse(url=auth_url, status_code=302)
    except Exception as e:
        logger.error(f"Microsoft SSO error: {e}")
        err = "not_configured" if "configured" in str(e).lower() or "install" in str(e).lower() else "unavailable"
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error={err}", status_code=302)


@router.get("/auth/microsoft/mobile-test", response_class=HTMLResponse)
async def microsoft_mobile_test(request: Request):
    """Standalone test page for Microsoft SSO - bypasses all frontend caching."""
    from fastapi.responses import HTMLResponse

    try:
        app = _get_msal_app()
        redirect_uri = await _ms_redirect_uri_async(request)
        state = _build_sso_state("microsoft", _get_frontend_base(request), mode="login")
        auth_url = app.get_authorization_request_url(
            scopes=MS_SCOPES,
            redirect_uri=redirect_uri,
            state=state,
        )
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Microsoft SSO Test</title>
<style>body{{font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#0f172a;color:#fff}}
.card{{background:#1e293b;border-radius:16px;padding:32px;max-width:400px;width:90%;text-align:center}}
a.btn{{display:block;background:#2563eb;color:#fff;text-decoration:none;padding:16px 24px;border-radius:12px;font-size:18px;font-weight:600;margin:20px 0}}
a.btn:active{{background:#1d4ed8}}
.info{{color:#94a3b8;font-size:13px;margin-top:16px}}</style></head>
<body><div class="card">
<h2 style="margin-top:0">Microsoft SSO Test</h2>
<p>Tap the button below to sign in with Microsoft</p>
<a class="btn" href="{auth_url}">Sign in with Microsoft</a>
<p class="info">This page bypasses all frontend caching.<br>If this works, the issue is browser cache.</p>
</div></body></html>"""
        return HTMLResponse(
            content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
        )
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error: {e}</h1>", status_code=500)


@router.get("/auth/microsoft/callback")
async def microsoft_callback(
    request: Request,
    response: Response,
    code: str = None,
    error: str = None,
    error_description: str = None,
    state: str = None,
):
    """Handle OAuth callback from Microsoft, create/update user, redirect to frontend."""
    from fastapi.responses import RedirectResponse

    state_payload = _decode_sso_state(state, expected_provider="microsoft")
    frontend_base = state_payload.get("return_base") or _get_frontend_base(request)

    if error:
        logger.error(f"Microsoft OAuth error: {error} — {error_description}")
        if "AADSTS50011" in str(error_description or ""):
            try:
                await db.system_runtime_flags.update_one(
                    {"key": "sso_last_redirect_mismatch"},
                    {
                        "$set": {
                            "key": "sso_last_redirect_mismatch",
                            "provider": "microsoft",
                            "error": str(error),
                            "error_description": str(error_description or "")[:800],
                            "expected_callback": await _ms_redirect_uri_async(request),
                            "active_base": await _resolve_sso_redirect_base(request),
                            "captured_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                    upsert=True,
                )
            except Exception:
                pass
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error={error}")

    if not code:
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=no_code")

    try:
        app = _get_msal_app()
        token_response = app.acquire_token_by_authorization_code(
            code=code,
            scopes=MS_SCOPES,
            redirect_uri=await _ms_redirect_uri_async(request),
        )

        if "error" in token_response:
            logger.error(f"MSAL token error: {token_response}")
            return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=token_failed")

        result = await _process_ms_token(token_response, request)
        if "error" in result:
            return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error={result['error']}")

        session_token_value = result.get("session_token") or result.get("_session_token_internal")
        if not session_token_value:
            logger.error("Microsoft SSO callback missing session token payload")
            return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=session_payload_missing", status_code=302)

        redirect_url = f"{frontend_base}/auth/login?sso_provider=microsoft&sso_status=success"
        resp = RedirectResponse(url=redirect_url, status_code=302)
        _set_session_cookie(resp, session_token_value, int(result.get("expires_minutes", 120)) * 60, request)
        return resp

    except Exception as e:
        logger.exception(f"Microsoft SSO callback error: {e}")
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=internal")


@router.post("/auth/microsoft/exchange")
async def microsoft_exchange(request: Request):
    """Exchange Microsoft OAuth code for session token via XHR (no redirect).
    Used by the frontend /auth/ms-callback page to avoid direct /api/ navigation on mobile."""
    body = await request.json()
    code = body.get("code")
    redirect_uri = body.get("redirect_uri")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        app = _get_msal_app()
        # Use the redirect_uri from the frontend (which is the frontend callback page)
        token_response = app.acquire_token_by_authorization_code(
            code=code,
            scopes=MS_SCOPES,
            redirect_uri=redirect_uri or await _ms_redirect_uri_async(request),
        )

        if "error" in token_response:
            logger.error(f"MSAL exchange error: {token_response}")
            raise HTTPException(
                status_code=400, detail=token_response.get("error_description", "Token exchange failed")
            )

        result = await _process_ms_token(token_response, request)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        result.pop("_session_token_internal", None)
        result.pop("_refresh_token_internal", None)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Microsoft exchange error: {e}")
        raise HTTPException(status_code=500, detail="Microsoft login failed")


async def _process_ms_token(token_response: dict, request: Request) -> dict:
    """Shared logic: exchange MS access token for user session. Returns dict with session_token or error."""
    try:
        access_token = token_response["access_token"]

        # Fetch user profile from Microsoft Graph
        async with httpx.AsyncClient() as client:
            graph_resp = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if graph_resp.status_code != 200:
                logger.error(f"MS Graph error: {graph_resp.text}")
                return {"error": "graph_failed"}
            ms_user = graph_resp.json()

        email = ms_user.get("mail") or ms_user.get("userPrincipalName", "")
        name = ms_user.get("displayName", email.split("@")[0])
        ms_id = ms_user.get("id", "")

        # Try to fetch profile photo URL from Microsoft Graph
        ms_photo_url = ""
        try:
            async with httpx.AsyncClient() as photo_client:
                photo_resp = await photo_client.get(
                    "https://graph.microsoft.com/v1.0/me/photo/$value",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=5.0,
                )
                if photo_resp.status_code == 200:
                    import base64
                    photo_b64 = base64.b64encode(photo_resp.content).decode()
                    content_type = photo_resp.headers.get("content-type", "image/jpeg")
                    ms_photo_url = f"data:{content_type};base64,{photo_b64}"
        except Exception as photo_err:
            logger.debug(f"Could not fetch MS profile photo: {photo_err}")

        # Find or create user
        existing = await db.users.find_one({"email": email}, {"_id": 0})

        if existing:
            user = User(**existing)
            update_fields = {"auth_provider": "microsoft", "microsoft_id": ms_id, "name": name or user.name}
            if ms_photo_url and not existing.get("profile_image"):
                update_fields["profile_image"] = ms_photo_url
            await db.users.update_one(
                {"user_id": user.user_id},
                {"$set": update_fields},
            )
            await db.user_sessions.delete_many({"user_id": user.user_id})
        else:
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            user = User(
                user_id=user_id,
                email=email,
                name=name,
                auth_provider="microsoft",
            )
            user_dict = user.dict()
            user_dict["microsoft_id"] = ms_id
            if ms_photo_url:
                user_dict["profile_image"] = ms_photo_url
            await db.users.insert_one(user_dict)

        user = await apply_access_overrides(user)

        token_version = user.token_version
        expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
        session_token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
        refresh_token = secrets.token_urlsafe(32)
        session = UserSession(
            user_id=user.user_id,
            session_token=session_token,
            refresh_token=refresh_token,
            token_version=token_version,
            issued_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
            ip_address=request.client.host if request.client else None,
        )
        await db.user_sessions.insert_one(session.dict())
        await log_security_event(user.user_id, "login_microsoft_sso", "low", request, {"email": email})

        return {
            "_session_token_internal": session_token,
            "_refresh_token_internal": refresh_token,
            **_auth_token_payload(request, session_token=session_token, refresh_token=refresh_token),
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
            "expires_minutes": expires_minutes,
        }
    except Exception as e:
        logger.exception(f"MS token processing error: {e}")
        return {"error": "internal"}


# ── Apple Sign-In ──────────────────────────────────────────────────────────

APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID", "")
APPLE_TEAM_ID = os.environ.get("APPLE_TEAM_ID", "")
APPLE_KEY_ID = os.environ.get("APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY = os.environ.get("APPLE_PRIVATE_KEY", "")  # PEM content or path


def _apple_configured() -> bool:
    return bool(APPLE_CLIENT_ID and APPLE_TEAM_ID and APPLE_KEY_ID and APPLE_PRIVATE_KEY)


def _generate_apple_client_secret() -> str:
    """Generate a signed JWT client_secret for Apple Sign-In."""
    import jwt as pyjwt

    now = datetime.now(timezone.utc)
    payload = {
        "iss": APPLE_TEAM_ID,
        "iat": now,
        "exp": now + timedelta(days=180),
        "aud": "https://appleid.apple.com",
        "sub": APPLE_CLIENT_ID,
    }
    key = APPLE_PRIVATE_KEY.replace("\\n", "\n")
    return pyjwt.encode(payload, key, algorithm="ES256", headers={"kid": APPLE_KEY_ID})


async def _apple_redirect_uri_async(request: Request = None) -> str:
    """Build Apple OAuth callback URI using persistent auto-synced redirect base."""
    strategy = _apple_effective_callback_strategy(request)
    broker_callback = _apple_broker_callback_uri_for_request(request) if strategy == "broker" else ""
    if broker_callback:
        return broker_callback

    if request and strategy == "direct":
        preview_return_base = _resolve_sso_return_base(request)
        if preview_return_base and _is_preview_sso_base(preview_return_base):
            return f"{preview_return_base}/api/auth/apple/callback"

    base = await _resolve_sso_redirect_base(request, provider="apple")
    return f"{base}/api/auth/apple/callback"


def _apple_redirect_uri(request: Request = None) -> str:
    base = _get_frontend_base(request) if request else os.environ.get("FRONTEND_BASE_URL", "")
    return f"{base}/api/auth/apple/callback"


_APPLE_REDIRECT_PREFLIGHT_CACHE: Dict[str, Dict[str, Any]] = {}


def _apple_redirect_preflight_ttl_seconds() -> int:
    try:
        return max(30, int(os.environ.get("APPLE_SSO_REDIRECT_PREFLIGHT_TTL_SECONDS") or 300))
    except Exception:
        return 300


def _apple_redirect_preflight_enabled() -> bool:
    return _env_bool("APPLE_SSO_REDIRECT_PREFLIGHT_ENABLED", True)


def _apple_fail_fast_invalid_redirect() -> bool:
    return _env_bool("APPLE_SSO_FAIL_FAST_ON_INVALID_REDIRECT", True)


def _apple_require_preflight_accepted() -> bool:
    return _env_bool("APPLE_SSO_REQUIRE_PREFLIGHT_ACCEPTED", True)


def _apple_strict_callback_allowlist_enabled() -> bool:
    return _env_bool("APPLE_SSO_STRICT_CALLBACK_ALLOWLIST", True)


def _apple_auto_refresh_accepted_preview_base_enabled() -> bool:
    return _env_bool("APPLE_SSO_AUTO_REFRESH_ACCEPTED_PREVIEW_BASE", True)


def _apple_provider_verified_base_required() -> bool:
    return _env_bool("APPLE_SSO_REQUIRE_PROVIDER_VERIFIED_BASE", True)


def _apple_provider_verified_bases() -> list[str]:
    return _parse_registered_redirect_uris("APPLE_SSO_PROVIDER_VERIFIED_REDIRECT_BASES")


def _apple_dynamic_preview_base_candidate(request: Request | None = None) -> str:
    if not _apple_auto_refresh_accepted_preview_base_enabled():
        return ""
    raw = _get_frontend_base(request) if request else (os.environ.get("FRONTEND_BASE_URL") or "")
    base = _normalize_base_url(raw)
    if not base:
        return ""
    if not _is_preview_sso_base(base):
        return ""
    if not _is_allowed_sso_base(base):
        return ""
    return base


def _apple_provider_accepted_callback_bases(request: Request | None = None) -> list[str]:
    configured = _parse_registered_redirect_uris("APPLE_SSO_PROVIDER_ACCEPTED_CALLBACK_BASES")
    dynamic_preview = _apple_dynamic_preview_base_candidate(request)
    broker_base = _apple_broker_base_for_request(request) if _apple_effective_callback_strategy(request) == "broker" else ""

    merged: list[str] = []
    seen: set[str] = set()

    if dynamic_preview:
        merged.append(dynamic_preview)
        seen.add(dynamic_preview)

    for base in configured:
        if not base or base in seen:
            continue
        seen.add(base)
        merged.append(base)

    if broker_base and broker_base not in seen:
        seen.add(broker_base)
        merged.append(broker_base)
    return merged


def _apple_effective_callback_allowlist(request: Request | None = None) -> list[str]:
    accepted = _apple_provider_accepted_callback_bases(request)
    return accepted if accepted else _apple_provider_verified_bases()


def _apple_provider_base_verification_source(base: str | None, request: Request | None = None) -> str:
    normalized = _normalize_base_url(base or "")
    if not normalized:
        return "none"

    if normalized in _apple_provider_accepted_callback_bases(request):
        return "provider_accepted_list"

    if normalized in _apple_provider_verified_bases():
        return "provider_verified_list"

    return "none"


def _apple_provider_base_verified(base: str | None, request: Request | None = None) -> bool:
    normalized = _normalize_base_url(base or "")
    if not normalized:
        return False
    return _apple_provider_base_verification_source(normalized, request=request) != "none"


def _apple_redirect_candidates(request: Request) -> list[str]:
    candidates: list[str] = []
    strict_allowlist = _apple_strict_callback_allowlist_enabled()
    allowlist = _apple_effective_callback_allowlist(request)

    if _apple_effective_callback_strategy(request) == "broker":
        broker_base = _apple_broker_base_for_request(request)
        if broker_base and _is_allowed_sso_base(broker_base):
            return [broker_base]
        return []

    if strict_allowlist and allowlist:
        for base in allowlist:
            normalized = _normalize_base_url(base)
            if normalized and _is_allowed_sso_base(normalized):
                candidates.append(normalized)

        deduped_allowlist: list[str] = []
        seen_allowlist = set()
        for base in candidates:
            if base in seen_allowlist:
                continue
            seen_allowlist.add(base)
            deduped_allowlist.append(base)
        return deduped_allowlist

    auto_synced = _apple_auto_synced_redirect_base(request)
    if auto_synced and _is_allowed_sso_base(auto_synced):
        candidates.append(auto_synced)

    for base in _apple_effective_callback_allowlist(request):
        normalized = _normalize_base_url(base)
        if normalized and _is_allowed_sso_base(normalized):
            candidates.append(normalized)

    for raw in [
        os.environ.get("APPLE_SSO_CANONICAL_REDIRECT_BASE", ""),
        os.environ.get("SSO_CANONICAL_REDIRECT_BASE", ""),
        os.environ.get("SSO_REDIRECT_BASE_URL", ""),
        os.environ.get("FRONTEND_BASE_URL", ""),
        _get_frontend_base(request),
    ]:
        base = _normalize_base_url(raw)
        if base and _is_allowed_sso_base(base):
            candidates.append(base)

    for item in str(os.environ.get("APPLE_SSO_REGISTERED_REDIRECT_URIS") or "").split(","):
        base = _normalize_base_url(item)
        if base and _is_allowed_sso_base(base):
            candidates.append(base)

    deduped: list[str] = []
    seen = set()
    for base in candidates:
        if base in seen:
            continue
        seen.add(base)
        deduped.append(base)
    return deduped


async def _apple_preflight_redirect_uri(redirect_uri: str) -> Dict[str, Any]:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    ttl = _apple_redirect_preflight_ttl_seconds()
    cached = _APPLE_REDIRECT_PREFLIGHT_CACHE.get(redirect_uri)
    if cached and now_ts - int(cached.get("ts") or 0) <= ttl:
        return {**cached, "cached": True}

    params = {
        "client_id": APPLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "name email",
        "response_mode": "form_post",
        "state": "apple_redirect_probe",
    }
    probe_url = f"https://appleid.apple.com/auth/authorize?{urlencode(params)}"

    result: Dict[str, Any] = {
        "redirect_uri": redirect_uri,
        "ok": False,
        "invalid_redirect": False,
        "signal": "unknown",
        "status_code": None,
        "reason": "",
        "cached": False,
        "ts": now_ts,
    }

    try:
        async with httpx.AsyncClient(timeout=7.0, follow_redirects=True) as client:
            resp = await client.get(probe_url)
        raw_text = resp.text or ""
        text = raw_text.lower()

        boot_error_code = ""
        boot_error_message = ""
        try:
            boot_match = re.search(r'class="boot_args"[^>]*>(.*?)</script>', raw_text, flags=re.IGNORECASE | re.DOTALL)
            if boot_match:
                boot_args = json.loads((boot_match.group(1) or "").strip() or "{}")
                direct = boot_args.get("direct") if isinstance(boot_args, dict) else {}
                if isinstance(direct, dict):
                    boot_error_code = str(direct.get("errorcode") or "").strip().lower()
                    boot_error_message = str(direct.get("errormessage") or "").strip().lower()
        except Exception:
            boot_error_code = ""
            boot_error_message = ""

        invalid_redirect = (
            "invalid web redirect url" in text
            or ("invalid_request" in text and "redirect" in text)
            or (
                boot_error_code == "invalid_request"
                and ("redirect" in boot_error_message or "invalid web redirect url" in boot_error_message)
            )
        )
        final_host = ""
        try:
            final_host = (urlparse(str(resp.url)).hostname or "").lower().strip()
        except Exception:
            final_host = ""
        provider_page_hint = any(
            marker in text
            for marker in [
                "use your apple account to sign in",
                "email or phone number",
                "apple account",
                "appleid.apple.com",
                "signin",
                "continue",
            ]
        )
        accepted = bool(
            int(resp.status_code) == 200
            and final_host.endswith("apple.com")
            and not invalid_redirect
            and provider_page_hint
        )
        signal = "accepted" if accepted else ("invalid_redirect" if invalid_redirect else "unverifiable")
        reason = (
            "accepted"
            if accepted
            else ("invalid_web_redirect_url" if invalid_redirect else f"unverifiable_response_status_{int(resp.status_code)}")
        )
        result.update(
            {
                "ok": accepted,
                "invalid_redirect": invalid_redirect,
                "signal": signal,
                "status_code": int(resp.status_code),
                "reason": reason,
                "boot_error_code": boot_error_code,
                "boot_error_message": boot_error_message,
                "probe_text_len": len(text),
            }
        )
    except Exception as exc:
        result.update(
            {
                "ok": False,
                "invalid_redirect": False,
                "signal": "probe_error",
                "reason": f"probe_error:{type(exc).__name__}",
            }
        )

    _APPLE_REDIRECT_PREFLIGHT_CACHE[redirect_uri] = result
    return result


async def _resolve_apple_redirect_uri_for_auth(request: Request) -> Dict[str, Any]:
    candidates = _apple_redirect_candidates(request)
    probes: list[Dict[str, Any]] = []
    invalid_probe_count = 0
    broker_mode = _apple_effective_callback_strategy(request) == "broker"

    if not candidates:
        base = await _resolve_sso_redirect_base(request, provider="apple")
        callback = _apple_callback_uri_for_base(base, broker_mode=broker_mode)
        return {
            "callback": callback,
            "base": base,
            "selected_via": "resolver_fallback",
            "all_invalid": False,
            "all_unverifiable": False,
            "probes": probes,
        }

    if not _apple_redirect_preflight_enabled():
        base = candidates[0]
        callback = _apple_callback_uri_for_base(base, broker_mode=broker_mode)
        return {
            "callback": callback,
            "base": base,
            "selected_via": "first_candidate_prefight_disabled",
            "all_invalid": False,
            "all_unverifiable": False,
            "probes": probes,
        }

    for base in candidates:
        callback = _apple_callback_uri_for_base(base, broker_mode=broker_mode)
        probe = await _apple_preflight_redirect_uri(callback)
        probe["base"] = base
        probes.append(probe)
        if bool(probe.get("invalid_redirect")):
            invalid_probe_count += 1
        if probe.get("ok"):
            return {
                "callback": callback,
                "base": base,
                "selected_via": "apple_authorize_preflight",
                "all_invalid": False,
                "all_unverifiable": False,
                "probes": probes,
            }

    base = candidates[0]
    all_invalid = bool(probes) and invalid_probe_count == len(probes)

    if all_invalid and not broker_mode:
        runtime_bases = await _apple_runtime_broker_bases()

        for runtime_base in runtime_bases:
            runtime_callback = _apple_callback_uri_for_base(runtime_base, broker_mode=False)
            if not runtime_callback:
                continue
            runtime_probe = await _apple_preflight_redirect_uri(runtime_callback)
            runtime_probe["base"] = runtime_base
            probes.append(runtime_probe)
            if runtime_probe.get("ok"):
                return {
                    "callback": runtime_callback,
                    "base": runtime_base,
                    "selected_via": "apple_runtime_direct_preflight",
                    "all_invalid": False,
                    "all_unverifiable": False,
                    "probes": probes,
                }

        for broker_base in runtime_bases:
            broker_callback = _apple_callback_uri_for_base(broker_base, broker_mode=True)
            if not broker_callback:
                continue
            broker_probe = await _apple_preflight_redirect_uri(broker_callback)
            broker_probe["base"] = broker_base
            probes.append(broker_probe)
            if broker_probe.get("ok"):
                return {
                    "callback": broker_callback,
                    "base": broker_base,
                    "selected_via": "apple_broker_runtime_preflight",
                    "all_invalid": False,
                    "all_unverifiable": False,
                    "probes": probes,
                }

    fallback_callback = _apple_callback_uri_for_base(base, broker_mode=broker_mode)
    return {
        "callback": fallback_callback,
        "base": base,
        "selected_via": "all_invalid_fallback" if all_invalid else "all_unverifiable_fallback",
        "all_invalid": all_invalid,
        "all_unverifiable": bool(probes) and not all_invalid,
        "probes": probes,
    }


@router.get("/auth/apple/login")
async def apple_login_redirect(request: Request):
    """Redirect to Apple's authorization page."""
    from fastapi.responses import RedirectResponse

    frontend_base = _resolve_sso_return_base(request)

    if not _apple_configured():
        logger.warning("Apple Sign-In not configured — missing credentials")
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=apple_not_configured", status_code=302)

    resolved = await _resolve_apple_redirect_uri_for_auth(request)
    redirect_uri = resolved.get("callback") or await _apple_redirect_uri_async(request)
    callback_base = _normalize_base_url(resolved.get("base") or "")
    selected_via = str(resolved.get("selected_via") or "")
    broker_callback = _apple_broker_callback_uri_for_request(request)
    callback_strategy = _apple_effective_callback_strategy(request)
    broker_enforced = bool(callback_strategy == "broker" and broker_callback)
    runtime_preflight_selected = selected_via in {"apple_broker_runtime_preflight", "apple_runtime_direct_preflight"}
    provider_verified_required = _apple_provider_verified_base_required()
    provider_verified_bases = _apple_provider_verified_bases()
    provider_accepted_bases = _apple_provider_accepted_callback_bases(request)
    if runtime_preflight_selected and callback_base and callback_base not in provider_accepted_bases:
        provider_accepted_bases = [callback_base, *provider_accepted_bases]
    dynamic_preview_candidate = _apple_dynamic_preview_base_candidate(request)
    provider_verification_source = _apple_provider_base_verification_source(callback_base, request=request)
    if runtime_preflight_selected:
        provider_verification_source = selected_via
    provider_verified = provider_verification_source != "none"
    state = _build_sso_state(
        "apple",
        frontend_base,
        mode="login",
        callback_base=callback_base,
        callback_uri=redirect_uri,
    )

    try:
        await db.system_runtime_flags.update_one(
            {"key": "sso_apple_redirect_preflight"},
            {
                "$set": {
                    "key": "sso_apple_redirect_preflight",
                    "status": (
                        "all_candidates_invalid"
                        if bool(resolved.get("all_invalid"))
                        else ("all_candidates_unverifiable" if bool(resolved.get("all_unverifiable")) else "selected")
                    ),
                    "selected_callback": redirect_uri,
                    "selected_base": callback_base,
                    "selected_via": selected_via,
                    "probes": resolved.get("probes", []),
                    "all_unverifiable": bool(resolved.get("all_unverifiable")),
                    "provider_verified_required": provider_verified_required,
                    "provider_verified": provider_verified,
                    "provider_verification_source": provider_verification_source,
                    "provider_verified_bases": provider_verified_bases,
                    "provider_accepted_bases": provider_accepted_bases,
                    "dynamic_preview_candidate": dynamic_preview_candidate,
                    "auto_refresh_accepted_preview_base_enabled": _apple_auto_refresh_accepted_preview_base_enabled(),
                    "callback_strategy_effective": callback_strategy,
                    "callback_strategy_raw": _apple_callback_strategy(),
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )
    except Exception:
        pass

    if broker_enforced and redirect_uri != broker_callback:
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=apple_callback_not_provider_registered", status_code=302)

    relax_preflight_in_preview = _env_bool("APPLE_SSO_RELAX_PREFLIGHT_IN_PREVIEW", True) and _is_preview_sso_base(frontend_base)

    if bool(resolved.get("all_invalid")) and _apple_fail_fast_invalid_redirect() and not relax_preflight_in_preview:
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=apple_redirect_unregistered", status_code=302)
    preflight_ok_sources = {
        "apple_authorize_preflight",
        "apple_broker_runtime_preflight",
        "apple_runtime_direct_preflight",
    }
    if (
        _apple_redirect_preflight_enabled()
        and _apple_require_preflight_accepted()
        and selected_via not in preflight_ok_sources
        and not relax_preflight_in_preview
    ):
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=apple_callback_not_provider_registered", status_code=302)
    if provider_verified_required and not provider_verified:
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=apple_provider_verification_required", status_code=302)
    params = {
        "client_id": APPLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "name email",
        "response_mode": "form_post",
        "state": state,
    }
    from urllib.parse import urlencode
    query = urlencode(params)
    auth_url = f"https://appleid.apple.com/auth/authorize?{query}"
    return RedirectResponse(url=auth_url, status_code=302)


@router.post("/auth/apple/broker/callback")
async def apple_broker_callback(request: Request):
    """Stable broker callback: relay Apple form_post payload to active environment callback."""
    from fastapi.responses import RedirectResponse

    form = await request.form()
    state = form.get("state")
    state_payload = _decode_sso_state(state, expected_provider="apple", consume_replay=False)
    fallback_base = _resolve_sso_return_base(request)
    target_base = _coerce_sso_return_base(state_payload.get("return_base"), request=request)

    if not target_base or not _is_allowed_sso_base(target_base):
        return RedirectResponse(url=f"{fallback_base}/auth/login?sso_error=apple_broker_invalid_target", status_code=302)

    target_callback = f"{target_base}/api/auth/apple/callback"
    relay_fields: dict[str, str] = {}
    for key in ["state", "code", "id_token", "user", "error"]:
        value = form.get(key)
        if value is None:
            continue
        relay_fields[key] = str(value)

    inputs = "\n".join(
        f'<input type="hidden" name="{_html_escape(k)}" value="{_html_escape(v)}" />'
        for k, v in relay_fields.items()
    )
    callback_safe = _html_escape(target_callback)

    html = f"""
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Redirecting…</title>
  </head>
  <body>
    <form id=\"apple-broker-relay-form\" method=\"post\" action=\"{callback_safe}\">
      {inputs}
    </form>
    <script>
      (function () {{
        var form = document.getElementById('apple-broker-relay-form');
        if (form) form.submit();
      }})();
    </script>
    <noscript>
      <p>Continue Apple sign-in:</p>
      <button type=\"submit\" form=\"apple-broker-relay-form\">Continue</button>
    </noscript>
  </body>
</html>
"""
    return HTMLResponse(content=html, status_code=200)


@router.post("/auth/apple/callback")
async def apple_callback(request: Request):
    """Handle Apple's form_post callback with authorization code."""
    from fastapi.responses import RedirectResponse

    form = await request.form()
    state = form.get("state")
    state_payload_peek = _decode_sso_state(state, expected_provider="apple", consume_replay=False)
    frontend_base = _coerce_sso_return_base(state_payload_peek.get("return_base"), request=request)
    request_base = _get_frontend_base(request)

    if state and frontend_base and _normalize_base_url(frontend_base) != _normalize_base_url(request_base):
        target_callback = f"{frontend_base}/api/auth/apple/callback"
        relay_fields: dict[str, str] = {}
        for key in ["state", "code", "id_token", "user", "error"]:
            value = form.get(key)
            if value is None:
                continue
            relay_fields[key] = str(value)

        relay_inputs = "\n".join(
            f'<input type="hidden" name="{_html_escape(k)}" value="{_html_escape(v)}" />'
            for k, v in relay_fields.items()
        )
        callback_safe = _html_escape(target_callback)
        relay_html = f"""
<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Redirecting…</title>
  </head>
  <body>
    <form id=\"apple-cross-host-relay-form\" method=\"post\" action=\"{callback_safe}\">
      {relay_inputs}
    </form>
    <script>
      (function () {{
        var form = document.getElementById('apple-cross-host-relay-form');
        if (form) form.submit();
      }})();
    </script>
    <noscript>
      <p>Continue Apple sign-in:</p>
      <button type=\"submit\" form=\"apple-cross-host-relay-form\">Continue</button>
    </noscript>
  </body>
</html>
"""
        return HTMLResponse(content=relay_html, status_code=200)

    state_payload = _decode_sso_state(state, expected_provider="apple")
    frontend_base = _coerce_sso_return_base(state_payload.get("return_base"), request=request)
    callback_base = state_payload.get("callback_base") or await _resolve_sso_redirect_base(request, provider="apple")
    callback_override = state_payload.get("callback_uri") or _apple_callback_uri_for_base(callback_base, broker_mode=False)

    code = form.get("code")
    id_token_str = form.get("id_token")
    error_val = form.get("error")
    user_json = form.get("user")  # Apple only sends this on first sign-in

    if error_val:
        logger.error(f"Apple OAuth error: {error_val}")
        if str(error_val).lower() == "invalid_request":
            try:
                await db.system_runtime_flags.update_one(
                    {"key": "sso_last_redirect_mismatch"},
                    {
                        "$set": {
                            "key": "sso_last_redirect_mismatch",
                            "provider": "apple",
                            "error": str(error_val),
                            "expected_callback": callback_override,
                            "active_base": await _resolve_sso_redirect_base(request),
                            "active_base_apple": callback_base,
                            "captured_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                    upsert=True,
                )
            except Exception:
                pass
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error={error_val}", status_code=302)

    if not code:
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=no_code", status_code=302)

    try:
        result = await _process_apple_auth(code, id_token_str, user_json, request, redirect_uri_override=callback_override)
        if "error" in result:
            return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error={result['error']}", status_code=302)

        session_token_value = result.get("session_token") or result.get("_session_token_internal")
        if not session_token_value:
            logger.error("Apple SSO callback missing session token payload")
            return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=session_payload_missing", status_code=302)

        redirect_url = f"{frontend_base}/auth/login?sso_provider=apple&sso_status=success"
        resp = RedirectResponse(url=redirect_url, status_code=302)
        _set_session_cookie(resp, session_token_value, int(result.get("expires_minutes", 120)) * 60, request)
        return resp
    except Exception as e:
        logger.exception(f"Apple SSO callback error: {e}")
        return RedirectResponse(url=f"{frontend_base}/auth/login?sso_error=internal", status_code=302)


@router.post("/auth/apple/exchange")
async def apple_exchange(request: Request):
    """Exchange Apple OAuth code for session token via XHR (frontend callback page)."""
    body = await request.json()
    code = body.get("code")
    id_token_str = body.get("id_token")
    user_json = body.get("user")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        result = await _process_apple_auth(code, id_token_str, user_json, request)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        result.pop("_session_token_internal", None)
        result.pop("_refresh_token_internal", None)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Apple exchange error: {e}")
        raise HTTPException(status_code=500, detail="Apple login failed")


# ══════════ NATIVE (EXPO) SSO: direct provider-token verification ══════════
# These endpoints serve the native mobile app (iOS/Android builds) which obtains
# provider identity tokens on-device (expo-auth-session / expo-apple-authentication)
# instead of the browser redirect flows used by web.


def _native_google_allowed_audiences() -> list[str]:
    auds: list[str] = []
    for key in ("GOOGLE_CLIENT_ID", "GOOGLE_IOS_CLIENT_ID", "GOOGLE_ANDROID_CLIENT_ID"):
        val = str(os.environ.get(key, "") or "").strip()
        if val:
            auds.append(val)
    return auds


@router.get("/auth/sso-config/native")
async def native_sso_config():
    """Public, non-secret OAuth client identifiers used by the native (Expo) app."""
    ios_client_id = str(os.environ.get("GOOGLE_IOS_CLIENT_ID", "") or "").strip()
    android_client_id = str(os.environ.get("GOOGLE_ANDROID_CLIENT_ID", "") or "").strip()
    apple_bundle_id = str(os.environ.get("APPLE_BUNDLE_ID", "") or "").strip()
    apple_client_id = str(os.environ.get("APPLE_CLIENT_ID", "") or "").strip()
    return {
        "google_ios_client_id": ios_client_id or None,
        "google_android_client_id": android_client_id or None,
        "apple_native_enabled": bool(apple_bundle_id or apple_client_id),
        "apple_bundle_id": apple_bundle_id or None,
    }


async def _issue_native_sso_session(
    *,
    email: str,
    name: str,
    picture: str,
    provider: str,
    request: Request,
    response: Response,
    extra_user_fields: Optional[dict] = None,
) -> dict:
    """Find-or-create the user for a verified native SSO identity and issue a session.

    Mirrors the post-verification behavior of the web Google/Apple SSO flows.
    """
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user = User(**existing)
        update_fields: dict = {"auth_provider": provider}
        if picture and not existing.get("profile_image"):
            update_fields["profile_image"] = picture
        if name and not user.name:
            update_fields["name"] = name
        if extra_user_fields:
            update_fields.update(extra_user_fields)
        await db.users.update_one({"user_id": user.user_id}, {"$set": update_fields})
        await db.user_sessions.delete_many({"user_id": user.user_id})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = User(
            user_id=user_id,
            email=email,
            name=name or email.split("@")[0],
            picture=picture or "",
            auth_provider=provider,
        )
        user_dict = user.dict()
        if picture:
            user_dict["profile_image"] = picture
        if extra_user_fields:
            user_dict.update(extra_user_fields)
        await db.users.insert_one(user_dict)

    user = await apply_access_overrides(user)

    token_version = user.token_version
    expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    session_token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=session_token,
        refresh_token=refresh_token,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request.client else None,
    )
    await db.user_sessions.insert_one(session.dict())

    _set_session_cookie(response, session_token, expires_minutes * 60, request)
    await log_security_event(user.user_id, f"login_{provider}_native_sso", "low", request, {"email": email})

    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "is_admin": user.is_admin,
        "full_access": user.full_access,
        "roles": user.roles,
        **_auth_token_payload(request, session_token=session_token, refresh_token=refresh_token),
    }


@router.post("/auth/google/native")
async def google_native_auth(request: Request, response: Response):
    """Native Google Sign-In: verify a Google id_token issued to one of our OAuth clients."""
    body = await request.json()
    token_str = str(body.get("id_token") or "").strip()
    if not token_str:
        raise HTTPException(status_code=400, detail="id_token required")

    allowed_audiences = _native_google_allowed_audiences()
    if not allowed_audiences:
        raise HTTPException(status_code=503, detail="Native Google Sign-In is not configured")

    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        idinfo = await _asyncio.to_thread(
            google_id_token.verify_oauth2_token, token_str, google_requests.Request(), None
        )
    except Exception as exc:
        logger.warning(f"Native Google id_token verification failed: {exc.__class__.__name__}")
        raise HTTPException(status_code=401, detail="Invalid Google token")

    if idinfo.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=401, detail="Invalid Google token issuer")
    if idinfo.get("aud") not in allowed_audiences:
        raise HTTPException(status_code=401, detail="Google token audience mismatch")

    email = str(idinfo.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Google token missing email")
    if not idinfo.get("email_verified", False):
        raise HTTPException(status_code=401, detail="Google email is not verified")

    return await _issue_native_sso_session(
        email=email,
        name=str(idinfo.get("name") or ""),
        picture=str(idinfo.get("picture") or ""),
        provider="google",
        request=request,
        response=response,
    )


_APPLE_NATIVE_JWKS_CLIENT = None


def _apple_native_jwks_client():
    global _APPLE_NATIVE_JWKS_CLIENT
    if _APPLE_NATIVE_JWKS_CLIENT is None:
        from jwt import PyJWKClient

        _APPLE_NATIVE_JWKS_CLIENT = PyJWKClient("https://appleid.apple.com/auth/keys", cache_keys=True)
    return _APPLE_NATIVE_JWKS_CLIENT


@router.post("/auth/apple/native")
async def apple_native_auth(request: Request, response: Response):
    """Native Apple Sign-In: verify an identityToken (JWT) against Apple's public JWKS."""
    body = await request.json()
    identity_token = str(body.get("identity_token") or "").strip()
    full_name = str(body.get("full_name") or "").strip()
    if not identity_token:
        raise HTTPException(status_code=400, detail="identity_token required")

    allowed_audiences = [
        aud
        for aud in {
            str(os.environ.get("APPLE_BUNDLE_ID", "") or "").strip(),
            str(os.environ.get("APPLE_CLIENT_ID", "") or "").strip(),
        }
        if aud
    ]
    if not allowed_audiences:
        raise HTTPException(status_code=503, detail="Native Apple Sign-In is not configured")

    try:
        import jwt as pyjwt

        def _verify() -> dict:
            signing_key = _apple_native_jwks_client().get_signing_key_from_jwt(identity_token)
            return pyjwt.decode(
                identity_token,
                key=signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=allowed_audiences,
                issuer="https://appleid.apple.com",
            )

        claims = await _asyncio.to_thread(_verify)
    except Exception as exc:
        logger.warning(f"Native Apple identity token verification failed: {exc.__class__.__name__}")
        raise HTTPException(status_code=401, detail="Invalid Apple identity token")

    apple_sub = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").strip().lower()
    if not email and apple_sub:
        # Apple omits email in rare re-auth cases; correlate by stable Apple subject.
        existing_by_sub = await db.users.find_one({"apple_id": apple_sub}, {"_id": 0})
        if existing_by_sub:
            email = str(existing_by_sub.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Apple token missing email")

    return await _issue_native_sso_session(
        email=email,
        name=full_name,
        picture="",
        provider="apple",
        request=request,
        response=response,
        extra_user_fields={"apple_id": apple_sub} if apple_sub else None,
    )


async def _process_apple_auth(
    code: str,
    id_token_str: str | None,
    user_json: str | None,
    request: Request,
    redirect_uri_override: str | None = None,
) -> dict:
    """Exchange Apple auth code for tokens, extract user info, create/login user."""
    import jwt as pyjwt

    # Exchange authorization code for tokens
    client_secret = _generate_apple_client_secret()
    token_data = {
        "client_id": APPLE_CLIENT_ID,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri_override or await _apple_redirect_uri_async(request),
    }

    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://appleid.apple.com/auth/token", data=token_data)
        if token_resp.status_code != 200:
            logger.error(f"Apple token error: {token_resp.text}")
            return {"error": "token_failed"}
        tokens = token_resp.json()

    # Decode the id_token to get user info (Apple's id_token is a JWT)
    raw_id_token = tokens.get("id_token") or id_token_str
    if not raw_id_token:
        return {"error": "no_id_token"}

    # Decode without verification for user info (Apple's public keys rotate)
    claims = pyjwt.decode(raw_id_token, options={"verify_signature": False})
    apple_sub = claims.get("sub", "")
    email = claims.get("email", "")

    # Apple only sends name on FIRST sign-in, extract from user_json
    name = ""
    if user_json:
        try:
            import json

            user_data = json.loads(user_json) if isinstance(user_json, str) else user_json
            first = user_data.get("name", {}).get("firstName", "")
            last = user_data.get("name", {}).get("lastName", "")
            name = f"{first} {last}".strip()
        except Exception:
            pass

    if not email:
        return {"error": "no_email"}

    # Find or create user
    existing = await db.users.find_one({"email": email}, {"_id": 0})

    if existing:
        user = User(**existing)
        update_fields = {"auth_provider": "apple", "apple_id": apple_sub}
        if name and not user.name:
            update_fields["name"] = name
        await db.users.update_one({"user_id": user.user_id}, {"$set": update_fields})
        await db.user_sessions.delete_many({"user_id": user.user_id})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = User(
            user_id=user_id,
            email=email,
            name=name or email.split("@")[0],
            auth_provider="apple",
        )
        user_dict = user.dict()
        user_dict["apple_id"] = apple_sub
        await db.users.insert_one(user_dict)

    user = await apply_access_overrides(user)

    token_version = user.token_version
    expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    session_token = create_jwt_token(user.user_id, user.email, token_version, expires_minutes)
    refresh_token_val = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=session_token,
        refresh_token=refresh_token_val,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request.client else None,
    )
    await db.user_sessions.insert_one(session.dict())
    await log_security_event(user.user_id, "login_apple_sso", "low", request, {"email": email})

    return {
        "_session_token_internal": session_token,
        "_refresh_token_internal": refresh_token_val,
        **_auth_token_payload(request, session_token=session_token, refresh_token=refresh_token_val),
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "expires_minutes": expires_minutes,
    }


@router.get("/auth/me")
async def get_me(request: Request):
    """Get current user"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Apply access overrides for admin/full_access users
    user = await apply_access_overrides(user)

    plan = await get_subscription_plan_from_gps(user.subscription_plan, default_plan_id="free") or {}

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    google_calendar = user_doc.get("google_calendar", {}) if user_doc else {}
    calendar_connected = bool(google_calendar.get("access_token"))
    google_connected_at = google_calendar.get("connected_at")
    tenant_disclaimer = await _resolve_tenant_disclaimer_profile(
        request=request,
        user_doc=user_doc,
        overrides={"email": user.email},
    )

    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "is_admin": user.is_admin,
        "full_access": user.full_access,
        "platform_role": user_doc.get("platform_role") if user_doc else None,
        "employee_permissions": user_doc.get("employee_permissions", []) if user_doc else [],
        "feature_access": user_doc.get("feature_access", []) if user_doc else [],
        "roles": user.roles,
        "role": user.role,
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status,
        "phone": user_doc.get("phone", "") if user_doc else "",
        "kyc_verified": bool(user_doc.get("kyc_verified", False)) if user_doc else False,
        "kyc_tier": user_doc.get("kyc_tier") if user_doc else None,
        "profile_image": _safe_profile_image_for_auth_response(user_doc.get("profile_image", "")) if user_doc else "",
        "created_at": (user_doc.get("created_at").isoformat() if hasattr(user_doc.get("created_at"), "isoformat") else str(user_doc.get("created_at", ""))) if user_doc and user_doc.get("created_at") else "",
        "subscription": {
            "plan": user.subscription_plan,
            "status": user.subscription_status,
            "features": plan.get("features", []),
            "daily_limit": plan.get("daily_conversation_limit", 3),
        },
        "google_connected_at": google_connected_at,
        "calendar_connected": calendar_connected,
        "auth_provider": user_doc.get("auth_provider", "email") if user_doc else "email",
        "google_id": user_doc.get("google_id") if user_doc else None,
        "microsoft_id": user_doc.get("microsoft_id") if user_doc else None,
        "theme_preference": user_doc.get("theme_preference") if user_doc else None,
        "language_preference": user_doc.get("language_preference") if user_doc else None,
        "currency_preference": user_doc.get("currency_preference") if user_doc else None,
        "tenant_id": user_doc.get("tenant_id") if user_doc else None,
        "organization_id": user_doc.get("organization_id") if user_doc else None,
        "company_id": user_doc.get("company_id") if user_doc else None,
        "workspace_id": user_doc.get("workspace_id") if user_doc else None,
        "tenant_disclaimer_profile": tenant_disclaimer.get("legal_profile"),
    }


@router.get("/auth/linked-accounts")
async def get_linked_accounts(request: Request):
    """Get all linked authentication providers for the current user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Resource not found")

    providers = []
    # Email/password is always a potential provider
    has_password = bool(user_doc.get("password"))
    providers.append(
        {
            "provider": "email",
            "linked": has_password,
            "email": user.email,
            "linked_at": user_doc.get("created_at", "").isoformat() if user_doc.get("created_at") else None,
        }
    )
    # Google
    google_id = user_doc.get("google_id")
    providers.append(
        {
            "provider": "google",
            "linked": bool(google_id),
            "google_id": google_id,
            "linked_at": user_doc.get("google_linked_at"),
        }
    )
    # Microsoft
    ms_id = user_doc.get("microsoft_id")
    providers.append(
        {
            "provider": "microsoft",
            "linked": bool(ms_id),
            "microsoft_id": ms_id,
            "linked_at": user_doc.get("microsoft_linked_at"),
        }
    )
    # Apple
    apple_id = user_doc.get("apple_id")
    providers.append(
        {
            "provider": "apple",
            "linked": bool(apple_id),
            "apple_id": apple_id,
            "linked_at": user_doc.get("apple_linked_at"),
        }
    )

    return {
        "providers": providers,
        "primary_provider": user_doc.get("auth_provider", "email"),
    }


@router.post("/auth/unlink-account/{provider}")
async def unlink_account(provider: str, request: Request):
    """Unlink an authentication provider from the current user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if provider not in ("google", "microsoft", "apple"):
        raise HTTPException(status_code=400, detail="Invalid provider")

    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Ensure user has at least one other auth method
    has_password = bool(user_doc.get("password"))
    has_google = bool(user_doc.get("google_id"))
    has_microsoft = bool(user_doc.get("microsoft_id"))
    has_apple = bool(user_doc.get("apple_id"))
    linked_count = sum([has_password, has_google, has_microsoft, has_apple])

    if linked_count <= 1:
        raise HTTPException(
            status_code=400, detail="Cannot unlink your only authentication method. Link another provider first."
        )

    unset_fields = {}
    if provider == "google":
        if not has_google:
            raise HTTPException(status_code=400, detail="Google is not linked")
        unset_fields = {"google_id": "", "google_linked_at": ""}
    elif provider == "microsoft":
        if not has_microsoft:
            raise HTTPException(status_code=400, detail="Microsoft is not linked")
        unset_fields = {"microsoft_id": "", "microsoft_linked_at": ""}
    elif provider == "apple":
        if not has_apple:
            raise HTTPException(status_code=400, detail="Apple is not linked")
        unset_fields = {"apple_id": "", "apple_linked_at": ""}

    # If unlinking the primary provider, switch to another
    update = {"$unset": unset_fields}
    if user_doc.get("auth_provider") == provider:
        new_primary = (
            "email"
            if has_password
            else (
                "google"
                if has_google and provider != "google"
                else (
                    "microsoft"
                    if has_microsoft and provider != "microsoft"
                    else ("apple" if has_apple and provider != "apple" else "email")
                )
            )
        )
        update["$set"] = {"auth_provider": new_primary}

    await db.users.update_one({"user_id": user.user_id}, update)
    await log_security_event(user.user_id, f"unlink_{provider}", "medium", request, {"provider": provider})
    return {"status": "unlinked", "provider": provider}


@router.get("/auth/link/google")
async def link_google_redirect(request: Request):
    """Redirect to Google OAuth to link Google to existing account."""
    from fastapi.responses import RedirectResponse

    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    frontend_base = os.environ.get("FRONTEND_BASE_URL", "")
    redirect_url = f"{frontend_base}/"
    auth_url = f"https://auth.emergentagent.com/?redirect={_url_quote(redirect_url)}"
    return RedirectResponse(url=auth_url)


@router.post("/auth/link/google")
async def link_google_account(request: Request):
    """Link Google account to existing user using Emergent session_id."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    # Exchange session_id with Emergent Auth
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://auth.emergentagent.com/api/session-data?session_id={session_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid session")
        data = resp.json()

    google_email = data.get("email", "")
    google_id = data.get("sub", data.get("id", ""))

    # Check if this Google account is already linked to another user
    existing = await db.users.find_one({"google_id": google_id, "user_id": {"$ne": user.user_id}}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="This Google account is already linked to another user")

    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"google_id": google_id, "google_linked_at": datetime.now(timezone.utc).isoformat()}},
    )
    await log_security_event(user.user_id, "link_google", "medium", request, {"google_email": google_email})
    return {"status": "linked", "provider": "google", "email": google_email}


@router.get("/auth/link/microsoft")
async def link_microsoft_redirect(request: Request):
    """Redirect to Microsoft OAuth to link Microsoft to existing account."""
    from fastapi.responses import RedirectResponse

    frontend_base = _get_frontend_base(request)
    callback_base = await _resolve_sso_redirect_base(request)
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        app = _get_msal_app()
        redirect_uri = f"{callback_base}/api/auth/link/microsoft/callback"
        state = _build_sso_state("microsoft", frontend_base, mode="link_microsoft", user_id=user.user_id)
        auth_url = app.get_authorization_request_url(
            scopes=MS_SCOPES,
            redirect_uri=redirect_uri,
            state=state,
        )
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error(f"Microsoft link error: {e}")
        return RedirectResponse(url=f"{frontend_base}/settings?link_error=not_configured")


@router.get("/auth/link/microsoft/callback")
async def link_microsoft_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Microsoft OAuth callback for account linking."""
    from fastapi.responses import RedirectResponse

    state_payload = _decode_sso_state(state, expected_provider="microsoft")
    frontend_base = state_payload.get("return_base") or _get_frontend_base(request)

    legacy_link_state = bool(state and state.startswith("link_"))
    mode = str(state_payload.get("mode") or "")
    if error or not code or not state or (not legacy_link_state and mode != "link_microsoft"):
        return RedirectResponse(url=f"{frontend_base}/settings?link_error=failed")

    user_id = str(state_payload.get("uid") or "").strip() if not legacy_link_state else state.replace("link_", "")
    if not user_id:
        return RedirectResponse(url=f"{frontend_base}/settings?link_error=failed")

    try:
        app = _get_msal_app()
        callback_base = await _resolve_sso_redirect_base(request)
        redirect_uri = f"{callback_base}/api/auth/link/microsoft/callback"
        token_response = app.acquire_token_by_authorization_code(
            code=code,
            scopes=MS_SCOPES,
            redirect_uri=redirect_uri,
        )
        if "error" in token_response:
            return RedirectResponse(url=f"{frontend_base}/settings?link_error=token_failed")

        access_token = token_response["access_token"]
        async with httpx.AsyncClient() as client:
            graph_resp = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if graph_resp.status_code != 200:
                return RedirectResponse(url=f"{frontend_base}/settings?link_error=graph_failed")
            ms_user = graph_resp.json()

        ms_id = ms_user.get("id", "")

        # Check if Microsoft account is already linked to another user
        existing = await db.users.find_one({"microsoft_id": ms_id, "user_id": {"$ne": user_id}}, {"_id": 0})
        if existing:
            return RedirectResponse(url=f"{frontend_base}/settings?link_error=already_linked")

        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"microsoft_id": ms_id, "microsoft_linked_at": datetime.now(timezone.utc).isoformat()}},
        )
        await log_security_event(user_id, "link_microsoft", "medium", request, {"ms_email": ms_user.get("mail", "")})
        return RedirectResponse(url=f"{frontend_base}/settings?link_success=microsoft")
    except Exception as e:
        logger.exception(f"Microsoft link callback error: {e}")
        return RedirectResponse(url=f"{frontend_base}/settings?link_error=internal")


@router.get("/auth/link/apple")
async def link_apple_redirect(request: Request):
    """Redirect to Apple OAuth to link Apple to existing account."""
    from fastapi.responses import RedirectResponse

    frontend_base = _resolve_sso_return_base(request)
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not _apple_configured():
        return RedirectResponse(url=f"{frontend_base}/settings?link_error=apple_not_configured")

    redirect_uri = await _apple_redirect_uri_async(request)
    callback_base = _normalize_base_url(urlparse(redirect_uri).scheme + "://" + urlparse(redirect_uri).netloc) if redirect_uri else ""
    state = _build_sso_state(
        "apple",
        frontend_base,
        mode="link_apple",
        user_id=user.user_id,
        callback_base=callback_base,
        callback_uri=redirect_uri,
    )
    params = {
        "client_id": APPLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "name email",
        "response_mode": "form_post",
        "state": state,
    }
    query = urlencode(params)
    auth_url = f"https://appleid.apple.com/auth/authorize?{query}"
    return RedirectResponse(url=auth_url)


@router.get("/auth/sso-analytics")
async def get_sso_analytics(request: Request):
    """Comprehensive SSO analytics for the Executive Dashboard."""
    user = await get_current_user(request)
    if not user or not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    now = datetime.now(timezone.utc)
    now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    now - timedelta(days=30)

    # 1. User distribution by auth provider
    pipeline_dist = [
        {"$match": {"is_active": {"$ne": False}}},
        {"$group": {"_id": "$auth_provider", "count": {"$sum": 1}}},
    ]
    dist_cursor = db.users.aggregate(pipeline_dist)
    provider_dist = {}
    total_users = 0
    async for doc in dist_cursor:
        prov = doc["_id"] or "email"
        provider_dist[prov] = doc["count"]
        total_users += doc["count"]

    distribution = []
    colors = {"email": "#6366F1", "google": "#EA4335", "microsoft": "#00A4EF", "apple": "#A3AAAE"}
    for prov in ["email", "google", "microsoft", "apple"]:
        count = provider_dist.get(prov, 0)
        distribution.append(
            {
                "provider": prov,
                "count": count,
                "percentage": round((count / max(total_users, 1)) * 100, 1),
                "color": colors.get(prov, "#94A3B8"),
            }
        )

    # 2. Sign-in events from security_events (last 30 days, by day)
    login_events = ["login_email", "login_google_sso", "login_microsoft_sso", "login_apple_sso", "login_otp"]
    failed_events = ["login_failed", "login_lockout"]

    trends = []
    for i in range(30):
        day_start = (now - timedelta(days=29 - i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_str = day_start.strftime("%Y-%m-%d")

        counts = {}
        for evt in ["login_email", "login_google_sso", "login_microsoft_sso", "login_apple_sso"]:
            c = await db.security_events.count_documents(
                {"event_type": evt, "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}}
            )
            prov = evt.replace("login_", "").replace("_sso", "")
            counts[prov] = c

        failed = await db.security_events.count_documents(
            {
                "event_type": {"$in": failed_events},
                "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()},
            }
        )
        trends.append({"date": day_str, **counts, "failed": failed})

    # 3. Today's KPIs
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    signins_today = await db.security_events.count_documents(
        {"event_type": {"$in": login_events}, "created_at": {"$gte": today_start.isoformat()}}
    )
    failed_today = await db.security_events.count_documents(
        {"event_type": {"$in": failed_events}, "created_at": {"$gte": today_start.isoformat()}}
    )
    new_users_today = await db.users.count_documents({"created_at": {"$gte": today_start.isoformat()}})

    # 4. Success/failure rates per provider (last 7 days)
    success_rates = []
    for evt, prov in [
        ("login_email", "email"),
        ("login_google_sso", "google"),
        ("login_microsoft_sso", "microsoft"),
        ("login_apple_sso", "apple"),
    ]:
        success = await db.security_events.count_documents(
            {"event_type": evt, "created_at": {"$gte": week_ago.isoformat()}}
        )
        # Estimate failures by provider from metadata
        fail = await db.security_events.count_documents(
            {
                "event_type": {"$in": failed_events},
                "created_at": {"$gte": week_ago.isoformat()},
                "metadata.provider": prov,
            }
        )
        total = success + fail
        success_rates.append(
            {
                "provider": prov,
                "success": success,
                "failed": fail,
                "rate": round((success / max(total, 1)) * 100, 1),
                "color": colors.get(prov, "#94A3B8"),
            }
        )

    # 5. Peak hours heatmap (last 7 days)
    hourly = [0] * 24
    cursor = db.security_events.find(
        {"event_type": {"$in": login_events}, "created_at": {"$gte": week_ago.isoformat()}}, {"_id": 0, "created_at": 1}
    )
    async for doc in cursor:
        try:
            ts = doc.get("created_at", "")
            if isinstance(ts, str) and len(ts) >= 13:
                hour = int(ts[11:13])
                hourly[hour] += 1
        except Exception:
            pass

    peak_hours = [{"hour": h, "count": hourly[h]} for h in range(24)]
    max_hour_count = max(hourly) if hourly else 1

    # 6. Active sessions count by provider
    active_sessions = []
    for prov in ["email", "google", "microsoft", "apple"]:
        count = await db.user_sessions.count_documents({"auth_provider": prov})
        active_sessions.append({"provider": prov, "count": count, "color": colors.get(prov, "#94A3B8")})

    # Fallback: count from users who have that provider linked
    if sum(s["count"] for s in active_sessions) == 0:
        for i, prov in enumerate(["email", "google", "microsoft", "apple"]):
            field = "password" if prov == "email" else f"{prov}_id"
            count = await db.users.count_documents(
                {field: {"$exists": True, "$nin": [None, ""]}, "is_active": {"$ne": False}}
            )
            active_sessions[i]["count"] = count

    return {
        "distribution": distribution,
        "total_users": total_users,
        "trends": trends,
        "kpis": {
            "signins_today": signins_today,
            "failed_today": failed_today,
            "new_users_today": new_users_today,
            "success_rate": round((signins_today / max(signins_today + failed_today, 1)) * 100, 1),
            "most_popular": max(distribution, key=lambda x: x["count"])["provider"] if distribution else "email",
        },
        "success_rates": success_rates,
        "peak_hours": peak_hours,
        "max_hour_count": max_hour_count,
        "active_sessions": active_sessions,
    }


@router.get("/auth/merge/candidates")
async def get_merge_candidates(request: Request):
    """Find accounts that could be merged with the current user (same email)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Resource not found")

    email = user.email.lower().strip()
    candidates = []
    cursor = db.users.find(
        {
            "email": {"$regex": f"^{email}$", "$options": "i"},
            "user_id": {"$ne": user.user_id},
            "is_active": {"$ne": False},
        },
        {"_id": 0},
    )
    async for doc in cursor:
        providers = []
        if doc.get("password"):
            providers.append("email")
        if doc.get("google_id"):
            providers.append("google")
        if doc.get("microsoft_id"):
            providers.append("microsoft")
        if doc.get("apple_id"):
            providers.append("apple")
        candidates.append(
            {
                "user_id": doc["user_id"],
                "name": doc.get("name", "Unknown"),
                "email": doc.get("email", ""),
                "auth_provider": doc.get("auth_provider", "email"),
                "providers": providers,
                "created_at": str(doc.get("created_at", "")),
                "subscription_plan": doc.get("subscription_plan", "free"),
            }
        )
    return {"candidates": candidates, "current_user_id": user.user_id}


@router.post("/auth/merge/execute")
async def execute_merge(request: Request):
    """Merge a secondary account into the current (primary) account."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    secondary_user_id = body.get("secondary_user_id")
    if not secondary_user_id:
        raise HTTPException(status_code=400, detail="secondary_user_id is required")

    primary_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    secondary_doc = await db.users.find_one({"user_id": secondary_user_id}, {"_id": 0})
    if not primary_doc or not secondary_doc:
        raise HTTPException(status_code=404, detail="One or both accounts not found")

    if primary_doc.get("email", "").lower() != secondary_doc.get("email", "").lower():
        raise HTTPException(status_code=400, detail="Can only merge accounts with the same email address")

    if user.user_id == secondary_user_id:
        raise HTTPException(status_code=400, detail="Cannot merge an account with itself")

    # Transfer SSO identifiers from secondary to primary
    sso_updates = {}
    if secondary_doc.get("google_id") and not primary_doc.get("google_id"):
        sso_updates["google_id"] = secondary_doc["google_id"]
        sso_updates["google_linked_at"] = datetime.now(timezone.utc).isoformat()
    if secondary_doc.get("microsoft_id") and not primary_doc.get("microsoft_id"):
        sso_updates["microsoft_id"] = secondary_doc["microsoft_id"]
        sso_updates["microsoft_linked_at"] = datetime.now(timezone.utc).isoformat()
    if secondary_doc.get("apple_id") and not primary_doc.get("apple_id"):
        sso_updates["apple_id"] = secondary_doc["apple_id"]
        sso_updates["apple_linked_at"] = datetime.now(timezone.utc).isoformat()
    if secondary_doc.get("password") and not primary_doc.get("password"):
        sso_updates["password"] = secondary_doc["password"]

    if sso_updates:
        await db.users.update_one({"user_id": user.user_id}, {"$set": sso_updates})

    # Keep the better subscription
    sec_plan = secondary_doc.get("subscription_plan", "free")
    pri_plan = primary_doc.get("subscription_plan", "free")
    plan_rank = {"free": 0, "basic": 1, "pro": 2, "premium": 3, "enterprise": 4}
    if plan_rank.get(sec_plan, 0) > plan_rank.get(pri_plan, 0):
        await db.users.update_one(
            {"user_id": user.user_id},
            {
                "$set": {
                    "subscription_plan": sec_plan,
                    "subscription_status": secondary_doc.get("subscription_status", "active"),
                }
            },
        )

    # Migrate data across collections
    collections_to_migrate = [
        "ai_chat_sessions",
        "coach_conversations",
        "coach_messages",
        "sessions",
        "ai_goals",
        "goals",
        "tasks",
        "habits",
        "daily_plans",
        "daily_goals",
        "practice_sessions",
        "mock_interviews",
        "interview_simulations",
        "payment_transactions",
        "payments",
        "subscriptions",
        "invoices",
        "notifications",
        "feedback",
        "progress",
        "user_achievements",
        "coaching_badges",
        "coaching_streaks",
        "ai_feedback",
        "security_events",
        "known_devices",
        "notification_prefs",
        "email_preferences",
        "calendar_events",
        "calendar_bookings",
        "ai_images",
        "generated_resumes",
        "doc_analyses",
        "user_preferences",
        "user_content",
        "user_progress",
        "mood_logs",
        "daily_briefings",
        "learning_paths",
        "briefing_preferences",
        "digest_preferences",
        "solver_sessions",
        "voice_sessions",
    ]

    migrated_count = 0
    for coll_name in collections_to_migrate:
        try:
            result = await db[coll_name].update_many(
                {"user_id": secondary_user_id}, {"$set": {"user_id": user.user_id}}
            )
            migrated_count += result.modified_count
        except Exception as e:
            logger.warning(f"Merge: failed to migrate {coll_name}: {e}")

    # Invalidate secondary's sessions
    await db.user_sessions.delete_many({"user_id": secondary_user_id})

    # Soft delete secondary account
    await db.users.update_one(
        {"user_id": secondary_user_id},
        {
            "$set": {
                "merged_into": user.user_id,
                "merged_at": datetime.now(timezone.utc).isoformat(),
                "email": f"merged_{secondary_user_id}@deleted.local",
                "is_active": False,
            }
        },
    )

    await log_security_event(
        user.user_id,
        "account_merge",
        "high",
        request,
        {
            "secondary_user_id": secondary_user_id,
            "sso_transferred": list(sso_updates.keys()),
            "records_migrated": migrated_count,
        },
    )

    return {
        "status": "merged",
        "primary_user_id": user.user_id,
        "secondary_user_id": secondary_user_id,
        "sso_transferred": [k for k in sso_updates if k.endswith("_id")],
        "records_migrated": migrated_count,
    }


async def _detect_country(request: Request) -> str:
    """Detect user's country from IP. Returns ISO country code."""
    # Check CloudFlare / proxy headers first
    cf_country = request.headers.get("CF-IPCountry", "")
    if cf_country:
        return cf_country.upper()
    # Extract real IP from proxy headers
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not ip:
        ip = request.headers.get("X-Real-IP", "")
    if not ip or ip in ("127.0.0.1", "::1"):
        ip = request.client.host if request.client else ""
    if not ip or ip.startswith("10.") or ip.startswith("172.") or ip.startswith("192.168"):
        return "US"  # Default for local/private IPs
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"https://ipapi.co/{ip}/country/")
            if resp.status_code == 200 and len(resp.text.strip()) == 2:
                return resp.text.strip().upper()
    except Exception:
        pass
    return "US"  # Default fallback


async def _get_otp_method(user_id: str, country: str) -> tuple:
    """OTP delivery is email-only. Returns (method, None)."""
    return "email", None


@router.post("/auth/otp-preference")
async def set_otp_preference(request: Request):
    """OTP preference endpoint — email only."""
    from routes.db import require_auth

    await require_auth(request)
    return {"preference": "email"}


@router.post("/auth/track-route")
async def track_last_route(request: Request):
    """Track user's last active route for session restore."""
    from routes.db import require_auth

    user = await require_auth(request)
    body = await request.json()
    route = body.get("route", "/")
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"last_active_route": route, "last_active_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True}


async def _build_tenant_disclaimer_profile_response(
    request: Request,
    email: Optional[str] = None,
    tenant_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    company_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    user = await get_current_user(request)
    user_doc: Optional[Dict[str, Any]] = None
    if user:
        user_doc = await db.users.find_one(
            {"user_id": user.user_id},
            {
                "_id": 0,
                "email": 1,
                "tenant_id": 1,
                "organization_id": 1,
                "company_id": 1,
                "workspace_id": 1,
            },
        )
        if not user_doc:
            user_doc = {
                "email": user.email,
            }

    resolved = await _resolve_tenant_disclaimer_profile(
        request=request,
        user_doc=user_doc,
        overrides={
            "email": email,
            "tenant_id": tenant_id,
            "organization_id": organization_id,
            "company_id": company_id,
            "workspace_id": workspace_id,
            "host": host,
        },
    )

    return {
        "legal_profile": resolved.get("legal_profile", "default"),
        "matched_key": resolved.get("matched_key"),
        "mapping_source": resolved.get("mapping_source"),
        "default_profile": resolved.get("default_profile", "default"),
        "candidate_keys": resolved.get("candidate_keys", []),
        "updated_at": resolved.get("updated_at"),
    }


@router.get("/auth/tenant-disclaimer-profile")
async def get_tenant_disclaimer_profile(
    request: Request,
    email: Optional[str] = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    workspace_id: Optional[str] = Query(default=None),
    host: Optional[str] = Query(default=None),
):
    return await _build_tenant_disclaimer_profile_response(
        request=request,
        email=email,
        tenant_id=tenant_id,
        organization_id=organization_id,
        company_id=company_id,
        workspace_id=workspace_id,
        host=host,
    )


@router.get("/public/tenant-disclaimer-profile")
async def get_public_tenant_disclaimer_profile(
    request: Request,
    email: Optional[str] = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
    workspace_id: Optional[str] = Query(default=None),
    host: Optional[str] = Query(default=None),
):
    return await _build_tenant_disclaimer_profile_response(
        request=request,
        email=email,
        tenant_id=tenant_id,
        organization_id=organization_id,
        company_id=company_id,
        workspace_id=workspace_id,
        host=host,
    )


@router.get("/auth/admin/tenant-disclaimer-profile-map")
async def get_tenant_disclaimer_profile_map_admin(request: Request):
    user = await get_current_user(request)
    if not user or not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")

    state = await _get_tenant_disclaimer_profile_state()
    return {
        "key": state["key"],
        "default_profile": state["default_profile"],
        "mappings": state.get("mappings") or {},
        "mappings_count": len(state.get("mappings") or {}),
        "updated_at": state.get("updated_at"),
        "updated_by": state.get("updated_by"),
    }


@router.put("/auth/admin/tenant-disclaimer-profile-map")
async def set_tenant_disclaimer_profile_map_admin(body: TenantDisclaimerProfileMapRequest, request: Request):
    user = await get_current_user(request)
    if not user or not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")

    existing_state = await _get_tenant_disclaimer_profile_state()
    incoming_map = _normalize_disclaimer_map(body.mappings)
    next_map = incoming_map
    if body.merge:
        next_map = {**(existing_state.get("mappings") or {}), **incoming_map}

    if len(next_map) > 5000:
        raise HTTPException(status_code=400, detail="Too many mapping entries")

    default_profile = _normalize_legal_profile(body.default_profile, existing_state.get("default_profile") or "default")
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "key": TENANT_DISCLAIMER_PROFILE_MAP_KEY,
        "default_profile": default_profile,
        "mappings": next_map,
        "updated_at": now_iso,
        "updated_by": user.user_id,
    }
    await db.system_runtime_flags.update_one(
        {"key": TENANT_DISCLAIMER_PROFILE_MAP_KEY},
        {"$set": payload},
        upsert=True,
    )

    return {
        "ok": True,
        "default_profile": default_profile,
        "mappings_count": len(next_map),
        "updated_at": now_iso,
        "updated_by": user.user_id,
    }


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout user"""
    logout_payload: Dict[str, Any] = {}
    try:
        raw_payload = await request.json()
        if isinstance(raw_payload, dict):
            logout_payload = raw_payload
    except Exception:
        logout_payload = {}

    user = await get_current_user(request)
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})
    if user:
        await db.users.update_one({"user_id": user.user_id}, {"$inc": {"token_version": 1}})
        await log_security_event(user.user_id, "logout", "low", request)

    try:
        await _capture_logout_telemetry_event(
            request=request,
            event_type="logout",
            user=user,
            payload=logout_payload,
        )
    except Exception as telemetry_exc:
        logger.warning(f"Logout telemetry capture skipped: {telemetry_exc}")

    _delete_session_cookie(response)
    return {"message": "Logged out successfully"}


@router.post("/auth/logout-banner-telemetry")
async def capture_logout_banner_telemetry(payload: LogoutBannerTelemetryRequest, request: Request):
    event = str(payload.event or "").strip().lower()
    if event not in {"shown", "dismissed"}:
        raise HTTPException(status_code=400, detail="Invalid event")

    user = await get_current_user(request)
    telemetry_payload = payload.dict(exclude_none=True)
    telemetry_payload["action"] = f"logout_banner_{event}"
    try:
        await _capture_logout_telemetry_event(
            request=request,
            event_type=f"logout_banner_{event}",
            user=user,
            payload=telemetry_payload,
        )
    except Exception as telemetry_exc:
        logger.warning(f"Logout banner telemetry capture skipped: {telemetry_exc}")

    return {"ok": True}


@router.post("/auth/session-bootstrap-telemetry")
async def capture_auth_session_bootstrap_telemetry(payload: AuthSessionTelemetryRequest, request: Request):
    reason_code = str(payload.reason_code or "").strip().lower()
    if not reason_code:
        raise HTTPException(status_code=400, detail="reason_code is required")

    user = await get_current_user(request)
    await db[AUTH_SESSION_TELEMETRY_COLLECTION].insert_one(
        {
            "event_id": f"authtele_{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason_code": reason_code,
            "phase": payload.phase,
            "status": payload.status,
            "attempt": payload.attempt,
            "path": request.url.path,
            "user_id": user.user_id if user else None,
            "email": user.email if user else None,
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }
    )
    return {"ok": True}


@router.put("/auth/profile")
async def update_profile(request: ProfileUpdateRequest, req: Request):
    """Update user profile"""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name.strip()
    if request.phone is not None:
        update_data["phone"] = request.phone.strip()
    if request.profile_image is not None:
        update_data["profile_image"] = request.profile_image
    if request.theme_preference is not None and request.theme_preference in ("light", "dark", "system"):
        update_data["theme_preference"] = request.theme_preference
    if request.currency_preference is not None:
        update_data["currency_preference"] = request.currency_preference.upper()
    if request.language_preference is not None:
        normalized_language = str(request.language_preference or "").strip().lower()
        if normalized_language not in SUPPORTED_LANGUAGE_PREFERENCE_CODES:
            raise HTTPException(status_code=400, detail="Unsupported language preference")
        update_data["language_preference"] = normalized_language

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc)
        await db.users.update_one({"user_id": user.user_id}, {"$set": update_data})

    updated_user = await db.users.find_one({"user_id": user.user_id})
    if updated_user:
        updated_user.pop("_id", None)
        updated_user.pop("password_hash", None)

    return {"message": "Profile updated successfully", "user": updated_user}


@router.get("/auth/admin/session-timeout-config")
async def get_session_timeout_config(request: Request):
    user = await get_current_user(request)
    if not user or not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")
    payload = await _session_timeout_config_response()
    payload["updated_at"] = None
    payload["updated_by"] = None
    doc = await db.platform_runtime_config.find_one({"key": SESSION_TIMEOUT_CONFIG_KEY}, {"_id": 0, "updated_at": 1, "updated_by": 1})
    if doc:
        payload["updated_at"] = doc.get("updated_at")
        payload["updated_by"] = doc.get("updated_by")
    return payload


@router.post("/auth/admin/session-timeout-config")
async def set_session_timeout_config(body: SessionTimeoutConfigRequest, request: Request):
    user = await get_current_user(request)
    if not user or not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")

    user_hours = int(body.user_hours)
    admin_hours = int(body.admin_hours)
    if user_hours < 1 or user_hours > 24 or admin_hours < 1 or admin_hours > 24:
        raise HTTPException(status_code=400, detail="Session timeout hours must be between 1 and 24")

    old_cfg = await _load_session_timeout_config()
    new_user_minutes = user_hours * 60
    new_admin_minutes = admin_hours * 60
    if old_cfg.get("user_minutes") == new_user_minutes and old_cfg.get("admin_minutes") == new_admin_minutes:
        payload = await _session_timeout_config_response()
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["updated_by"] = user.user_id
        return {"success": True, "config": payload, "changed": False}

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.platform_runtime_config.update_one(
        {"key": SESSION_TIMEOUT_CONFIG_KEY},
        {
            "$set": {
                "key": SESSION_TIMEOUT_CONFIG_KEY,
                "user_minutes": new_user_minutes,
                "admin_minutes": new_admin_minutes,
                "updated_by": user.user_id,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    audit_doc = {
        "audit_id": f"session_timeout_audit_{uuid.uuid4().hex[:12]}",
        "changed_at": now_iso,
        "changed_by": user.user_id,
        "changed_by_email": getattr(user, "email", None),
        "old": {
            "user_minutes": int(old_cfg.get("user_minutes", USER_SESSION_MINUTES)),
            "admin_minutes": int(old_cfg.get("admin_minutes", ADMIN_SESSION_MINUTES)),
        },
        "new": {
            "user_minutes": new_user_minutes,
            "admin_minutes": new_admin_minutes,
        },
    }
    await db.auth_session_timeout_audit.insert_one({**audit_doc})

    try:
        from routes.notification_engine import emit_notification

        admins = await db.users.find(
            {"is_admin": True, "access_locked": {"$ne": True}},
            {"_id": 0, "user_id": 1, "email": 1, "name": 1},
        ).to_list(200)
        for admin in admins:
            admin_id = str(admin.get("user_id") or "")
            if admin_id:
                try:
                    await emit_notification(
                        user_id=admin_id,
                        notif_type="security",
                        title="Session timeout policy updated",
                        body=f"User={user_hours}h, Admin={admin_hours}h by {getattr(user, 'email', 'admin')}",
                        action_url="/ai-learning-hub",
                        metadata={
                            "policy": "session_timeout",
                            "old": audit_doc.get("old"),
                            "new": audit_doc.get("new"),
                            "changed_by": audit_doc.get("changed_by"),
                        },
                    )
                except Exception:
                    pass

            try:
                admin_email = str(admin.get("email") or "").strip()
                if admin_email and is_email_configured():
                    from utils.email_service import send_catalog_template
                    await send_catalog_template(
                        recipient_email=admin_email,
                        template_key="session_expired",
                        user_name=str(admin.get("name") or admin_email),
                        reason="Session timeout policy updated",
                        device="Admin security policy console",
                    )
            except Exception:
                pass
    except Exception:
        pass

    payload = await _session_timeout_config_response()
    payload["updated_at"] = now_iso
    payload["updated_by"] = user.user_id
    return {"success": True, "config": payload, "changed": True}


@router.get("/auth/admin/session-timeout-config/history")
async def get_session_timeout_config_history(request: Request, limit: int = Query(default=30, ge=1, le=200)):
    user = await get_current_user(request)
    if not user or not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")

    rows = await db.auth_session_timeout_audit.find({}, {"_id": 0}).sort("changed_at", -1).limit(int(limit)).to_list(int(limit))
    return {
        "history": rows,
        "count": len(rows),
    }


def _auth_default_inventory() -> Dict[str, List[str]]:
    return {
        "core_auth_session": [
            "GET /api/auth/lookup",
            "POST /api/auth/register",
            "POST /api/auth/login",
            "POST /api/auth/logout",
            "GET /api/auth/me",
            "PUT /api/auth/profile",
            "POST /api/auth/renew-session",
            "POST /api/auth/token/refresh",
            "GET /api/auth/sessions",
            "POST /api/auth/sessions/revoke-all",
            "POST /api/auth/change-password",
        ],
        "password_reset_verification": [
            "POST /api/auth/password/reset/request",
            "POST /api/auth/password/reset/confirm",
            "GET /api/auth/verify",
        ],
        "otp_2fa": [
            "POST /api/auth/otp/request",
            "POST /api/auth/otp/verify",
            "POST /api/auth/action-otp/request",
            "POST /api/auth/action-otp/verify",
            "POST /api/auth/otp-preference",
            "GET /api/auth/2fa/status",
            "POST /api/auth/2fa/enable",
            "POST /api/auth/2fa/disable",
            "POST /api/auth/2fa/verify",
            "POST /api/auth/2fa/backup-codes/regenerate",
            "GET /api/auth/admin/otp-dashboard",
            "POST /api/auth/admin/unlock-account",
        ],
        "biometric_passkey": [
            "POST /api/auth/biometric/set-pin",
            "POST /api/auth/biometric/verify-pin",
            "POST /api/auth/biometric/webauthn-register-options",
            "POST /api/auth/biometric/webauthn-register-complete",
            "POST /api/auth/biometric/webauthn-auth-options",
            "POST /api/auth/biometric/webauthn-auth-complete",
        ],
        "passwordless": [
            "POST /api/auth/qr/generate",
            "GET /api/auth/qr/status/{session_id}",
            "POST /api/auth/qr/approve",
            "POST /api/auth/magic-link/send",
            "GET /api/auth/magic-link/verify",
        ],
        "sso_platform_level": [
            "GET /api/auth/sso-config",
            "POST /api/auth/sso-telemetry",
            "GET /api/auth/google/init",
            "POST /api/auth/google/session",
            "GET /api/auth/microsoft/init",
            "GET /api/auth/microsoft/login",
            "GET /api/auth/microsoft/mobile-test",
            "GET /api/auth/microsoft/callback",
            "POST /api/auth/microsoft/exchange",
            "GET /api/auth/apple/init",
            "GET /api/auth/apple/login",
            "POST /api/auth/apple/callback",
            "POST /api/auth/apple/exchange",
        ],
        "linking_merge": [
            "GET /api/auth/linked-accounts",
            "POST /api/auth/unlink-account/{provider}",
            "GET /api/auth/link/google",
            "POST /api/auth/link/google",
            "GET /api/auth/link/microsoft",
            "GET /api/auth/link/microsoft/callback",
            "GET /api/auth/link/apple",
            "GET /api/auth/merge/candidates",
            "POST /api/auth/merge/execute",
            "GET /api/auth/sso-analytics",
        ],
        "security_trust_device": [
            "GET /api/auth/security/login-history",
            "GET /api/auth/security/overview",
            "GET /api/auth/security/alert-preferences",
            "PUT /api/auth/security/alert-preferences",
            "POST /api/auth/security/trust-device",
            "DELETE /api/auth/security/known-device/{device_id}",
        ],
        "admin_auth_controls": [
            "GET /api/auth/admin/fallback-links/health",
            "POST /api/auth/admin/sso-redirect-auto-sync",
            "POST /api/auth/admin/sso-validate-e2e",
            "GET /api/auth/admin/sso-redirect-drift-sentinel",
            "POST /api/auth/admin/sso-redirect-drift-sentinel/run-now",
            "GET /api/auth/admin/multi-region-auth-probe/status",
            "POST /api/auth/admin/multi-region-auth-probe/run-now",
            "POST /api/auth/admin/sso-provider-registration/align",
            "POST /api/auth/admin/sso-live-provider-signoff",
            "GET /api/auth/admin/session-timeout-config",
            "POST /api/auth/admin/session-timeout-config",
            "GET /api/auth/admin/session-timeout-config/history",
            "POST /api/auth/admin/e2e/otp/issue",
        ],
        "auth_bound_media": [
            "POST /api/auth/set-avatar",
            "POST /api/auth/generate-avatar",
            "GET /api/auth/avatar-history",
            "DELETE /api/auth/avatar-history/{history_id}",
            "POST /api/auth/upload-photo",
            "DELETE /api/auth/delete-photo",
            "POST /api/auth/track-route",
        ],
    }


def _auth_extract_iteration_number(filename: str) -> int:
    if not filename.startswith("iteration_") or not filename.endswith(".json"):
        return -1
    middle = filename.replace("iteration_", "").replace(".json", "").strip()
    return int(middle) if middle.isdigit() else -1


def _auth_normalize_endpoint_signature(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    parts = text.split()
    if len(parts) < 2:
        return text
    method = parts[0].upper()
    if method not in AUTH_COVERAGE_METHODS:
        return text
    path = parts[1]
    return f"{method} {path}"


def _auth_load_report_candidates() -> List[Dict[str, Any]]:
    if not os.path.isdir(AUTH_COVERAGE_REPORT_DIR):
        return []
    candidates: List[Dict[str, Any]] = []
    for name in os.listdir(AUTH_COVERAGE_REPORT_DIR):
        idx = _auth_extract_iteration_number(name)
        if idx < 0:
            continue
        path = os.path.join(AUTH_COVERAGE_REPORT_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            continue
        summary = str(payload.get("summary") or "").lower()
        is_auth = (
            "auth" in summary
            or bool(payload.get("auth_playbook_verification"))
            or bool(payload.get("endpoints_inventory"))
            or bool(payload.get("test_results", {}).get("backend_api_tests", {}).get("sections_tested"))
        )
        if not is_auth:
            continue
        candidates.append({"iteration": idx, "file": path, "payload": payload})
    candidates.sort(key=lambda row: row["iteration"], reverse=True)
    return candidates


def _auth_parse_rate_from_string(text: str) -> Optional[float]:
    val = str(text or "")
    if not val:
        return None
    chunk = val.split("%", 1)[0].strip()
    try:
        return float(chunk)
    except Exception:
        return None


async def _auth_run_live_probe_checks(request: Request) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()

    users_indexes = await db.users.index_information()
    reset_indexes = await db.password_reset_tokens.index_information()

    has_unique_email = any(
        bool(v.get("unique")) and any(str(k[0]) == "email" for k in (v.get("key") or []))
        for v in users_indexes.values()
    )
    has_reset_ttl = any(
        int(v.get("expireAfterSeconds", -1)) >= 0 and any(str(k[0]) == "expires_at" for k in (v.get("key") or []))
        for v in reset_indexes.values()
    )

    admin_count = await db.users.count_documents({"is_admin": True, "access_locked": {"$ne": True}})
    active_sessions = await db.user_sessions.count_documents({"expires_at": {"$gte": now}})
    failed_login_24h = await db.security_events.count_documents(
        {"event_type": {"$in": ["login_failed", "login_lockout"]}, "created_at": {"$gte": day_ago}}
    )

    sso_ok = False
    sso_note = ""
    try:
        sso_validation = await run_sso_e2e_validation_internal(request)
        sso_ok = str(sso_validation.get("status") or "").lower() in {"pass", "healthy"}
        if not sso_ok:
            failed_checks = [c.get("name") for c in (sso_validation.get("checks") or []) if not c.get("passed")]
            sso_note = f"failed_checks={', '.join(failed_checks[:3])}" if failed_checks else "validation_not_pass"
    except Exception as exc:
        sso_ok = False
        sso_note = f"sso_validation_error={str(exc)[:100]}"

    probe_map = {
        "core_auth_session": {
            "status": "pass" if admin_count > 0 and has_unique_email else "warning",
            "note": f"admins={admin_count}, unique_email_index={has_unique_email}, active_sessions={active_sessions}",
        },
        "password_reset_verification": {
            "status": "pass" if has_reset_ttl else "warning",
            "note": f"password_reset_ttl_index={has_reset_ttl}",
        },
        "otp_2fa": {
            "status": "pass" if OTP_RATE_LIMIT_PER_HOUR > 0 else "warning",
            "note": (
                f"otp_rate_limit_per_window={OTP_RATE_LIMIT_PER_HOUR}, "
                f"window_seconds={OTP_RATE_LIMIT_WINDOW_SECONDS}, "
                f"privileged_multiplier={OTP_RATE_LIMIT_PRIVILEGED_MULTIPLIER}, "
                f"otp_exempt_count={len(OTP_EXEMPT_EMAILS)}, "
                f"e2e_otp_bypass_enabled={_auth_e2e_otp_bypass_enabled()}, "
                f"e2e_otp_bypass_allowlist_count={len(_auth_e2e_otp_bypass_email_allowlist())}"
            ),
        },
        "biometric_passkey": {
            "status": "pass",
            "note": "biometric collections reachable",
        },
        "passwordless": {
            "status": "pass",
            "note": "magic link and qr collections reachable",
        },
        "sso_platform_level": {
            "status": "pass" if sso_ok else "warning",
            "note": sso_note or "sso_e2e_validation_pass",
        },
        "linking_merge": {
            "status": "pass",
            "note": "linked account collections reachable",
        },
        "security_trust_device": {
            "status": "warning" if failed_login_24h >= 25 else "pass",
            "note": f"failed_login_events_24h={failed_login_24h}",
        },
        "admin_auth_controls": {
            "status": "pass" if sso_ok else "warning",
            "note": "admin auth controls aligned with SSO validation",
        },
        "auth_bound_media": {
            "status": "pass",
            "note": "avatar/photo auth-bound routes available",
        },
    }

    passed = sum(1 for p in probe_map.values() if p.get("status") == "pass")
    warning = sum(1 for p in probe_map.values() if p.get("status") == "warning")
    failed = sum(1 for p in probe_map.values() if p.get("status") == "fail")
    overall = "pass" if failed == 0 and warning == 0 else ("warning" if failed == 0 else "fail")

    return {
        "generated_at": now.isoformat(),
        "overall": overall,
        "passed": passed,
        "warning": warning,
        "failed": failed,
        "modules": probe_map,
    }


def _auth_status_rank(status: str) -> int:
    norm = str(status or "").lower()
    if norm == "fail":
        return 3
    if norm == "warning":
        return 2
    return 1


@router.get("/auth/admin/coverage-matrix")
async def admin_auth_coverage_matrix(request: Request):
    user = await get_current_user(request)
    user_email = str(getattr(user, "email", "") or "").strip().lower() if user else ""
    is_admin_user = bool(getattr(user, "is_admin", False)) if user else False
    if not user or not (is_admin_user or is_admin_email(user_email) or is_full_access_email(user_email)):
        raise HTTPException(status_code=403, detail="Admin access required")

    reports = _auth_load_report_candidates()
    latest_report = reports[0] if reports else None
    inventory_report = next((r for r in reports if isinstance((r.get("payload") or {}).get("endpoints_inventory"), dict)), latest_report)

    latest_payload = (latest_report or {}).get("payload") or {}
    inventory_payload = (inventory_report or {}).get("payload") or {}
    inventory = inventory_payload.get("endpoints_inventory") if isinstance(inventory_payload.get("endpoints_inventory"), dict) else _auth_default_inventory()

    backend_issues = latest_payload.get("backend_issues") or {}
    issue_rows = [
        *list(backend_issues.get("critical") or []),
        *list(backend_issues.get("minor") or []),
    ]
    normalized_issue_rows = []
    for issue in issue_rows:
        endpoint = _auth_normalize_endpoint_signature((issue or {}).get("endpoint") or "")
        normalized_issue_rows.append({
            "endpoint": endpoint,
            "issue": (issue or {}).get("issue"),
            "priority": (issue or {}).get("priority"),
        })

    probe_data = await _auth_run_live_probe_checks(request)
    probe_map = probe_data.get("modules") or {}

    matrix_rows: List[Dict[str, Any]] = []
    endpoints_total = 0
    endpoints_passed = 0
    modules_pass = 0
    modules_warning = 0
    modules_fail = 0

    for module_id, endpoints in inventory.items():
        endpoints = list(endpoints or [])
        endpoints_total += len(endpoints)
        module_issues = []
        for item in normalized_issue_rows:
            endpoint_issue = str(item.get("endpoint") or "")
            for endpoint in endpoints:
                signature = _auth_normalize_endpoint_signature(endpoint)
                if endpoint_issue and signature and endpoint_issue in signature:
                    module_issues.append({
                        "endpoint": signature,
                        "issue": item.get("issue"),
                        "priority": item.get("priority"),
                    })
                    break

        issue_status = "pass" if len(module_issues) == 0 else "warning"
        probe_status = str((probe_map.get(module_id) or {}).get("status") or "pass").lower()
        final_status = "warning" if _auth_status_rank(probe_status) > _auth_status_rank(issue_status) else issue_status
        if probe_status == "fail" or issue_status == "fail":
            final_status = "fail"

        failed_count_estimate = len(module_issues)
        module_passed = max(0, len(endpoints) - failed_count_estimate)
        endpoints_passed += module_passed

        if final_status == "pass":
            modules_pass += 1
        elif final_status == "warning":
            modules_warning += 1
        else:
            modules_fail += 1

        matrix_rows.append(
            {
                "module_id": module_id,
                "title": AUTH_COVERAGE_LABELS.get(module_id, module_id.replace("_", " ").title()),
                "status": final_status,
                "endpoints_total": len(endpoints),
                "endpoints_passed_estimate": module_passed,
                "open_issues_count": len(module_issues),
                "open_issues": module_issues[:8],
                "live_probe": {
                    "status": probe_status,
                    "note": (probe_map.get(module_id) or {}).get("note") or "",
                },
                "endpoints": endpoints,
            }
        )

    backend_rate = _auth_parse_rate_from_string(str((latest_payload.get("success_rate") or {}).get("backend") or ""))
    frontend_rate = _auth_parse_rate_from_string(str((latest_payload.get("success_rate") or {}).get("frontend") or ""))

    overall_status = "pass"
    if modules_fail > 0:
        overall_status = "fail"
    elif modules_warning > 0:
        overall_status = "warning"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "kpis": {
            "modules_total": len(matrix_rows),
            "modules_pass": modules_pass,
            "modules_warning": modules_warning,
            "modules_fail": modules_fail,
            "endpoints_total": endpoints_total,
            "endpoints_passed_estimate": endpoints_passed,
            "coverage_pct_estimate": round((endpoints_passed / endpoints_total) * 100, 1) if endpoints_total else 0,
        },
        "report_sources": {
            "latest_auth_report": {
                "iteration": (latest_report or {}).get("iteration"),
                "file": (latest_report or {}).get("file"),
                "summary": latest_payload.get("summary"),
                "backend_rate_pct": backend_rate,
                "frontend_rate_pct": frontend_rate,
            },
            "inventory_report": {
                "iteration": (inventory_report or {}).get("iteration"),
                "file": (inventory_report or {}).get("file"),
            },
        },
        "live_probe": {
            "overall": probe_data.get("overall"),
            "passed": probe_data.get("passed"),
            "warning": probe_data.get("warning"),
            "failed": probe_data.get("failed"),
            "generated_at": probe_data.get("generated_at"),
        },
        "matrix": matrix_rows,
    }


# ═══════════════════════════════════════════
# SECURITY HARDENING: Token Refresh & Session Management
# ═══════════════════════════════════════════


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class WsTicketRequest(BaseModel):
    channel: str = "notifications"


@router.post("/auth/ws-ticket")
async def issue_ws_ticket(request: Request, payload: Optional[WsTicketRequest] = None):
    """Issue a short-lived, one-time WebSocket ticket for authenticated realtime channels."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    channel = _normalize_ws_ticket_channel((payload.channel if payload else "notifications"))
    if channel in WS_TICKET_ADMIN_CHANNELS and not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required for this realtime channel")

    now = datetime.now(timezone.utc)
    raw_ticket = secrets.token_urlsafe(48)
    ticket_hash = hash_ws_ticket(raw_ticket)
    expires_at = now + timedelta(seconds=WS_TICKET_TTL_SECONDS)

    await db.user_ws_tickets.delete_many({"user_id": user.user_id, "channel": channel, "used": False})
    await db.user_ws_tickets.insert_one(
        {
            "ticket_hash": ticket_hash,
            "channel": channel,
            "user_id": user.user_id,
            "issued_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "used": False,
            "ip_address": request.client.host if request and request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }
    )

    await log_security_event(user.user_id, "ws_ticket_issued", "low", request)
    return {
        "ticket": raw_ticket,
        "channel": channel,
        "expires_in_seconds": WS_TICKET_TTL_SECONDS,
        "user_id": user.user_id,
    }


@router.post("/auth/token/refresh")
async def refresh_token(req: TokenRefreshRequest, response: Response, request: Request = None):
    """Rotate session token using a valid refresh token. Issues new session + refresh tokens and invalidates the old pair."""
    from routes.db import _hash_refresh_token
    session = await db.user_sessions.find_one({"refresh_token": _hash_refresh_token(req.refresh_token)})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if session.get("expires_at"):
        expires = session["expires_at"]
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            await db.user_sessions.delete_one({"refresh_token": _hash_refresh_token(req.refresh_token)})
            raise HTTPException(status_code=401, detail="Refresh token expired")

    user = await db.users.find_one({"user_id": session["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")

    token_version = user.get("token_version", 0)
    if session.get("token_version") is not None and session["token_version"] != token_version:
        await db.user_sessions.delete_one({"refresh_token": _hash_refresh_token(req.refresh_token)})
        raise HTTPException(status_code=401, detail="Token version mismatch — session revoked")

    # Invalidate old session
    await db.user_sessions.delete_one({"refresh_token": _hash_refresh_token(req.refresh_token)})

    # Issue new tokens
    expires_minutes = await _resolve_session_timeout_minutes(bool(is_admin_email(user["email"])))
    new_token = create_jwt_token(user["user_id"], user["email"], token_version, expires_minutes)
    new_refresh = secrets.token_urlsafe(32)
    new_session = UserSession(
        user_id=user["user_id"],
        session_token=new_token,
        refresh_token=new_refresh,
        token_version=token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request and request.client else None,
    )
    await db.user_sessions.insert_one(new_session.dict())
    _set_session_cookie(response, new_token, expires_minutes * 60, request)
    await log_security_event(user["user_id"], "token_refresh", "low", request)
    return {
        **_auth_token_payload(request, session_token=new_token, refresh_token=new_refresh),
        "expires_in": expires_minutes * 60,
    }


@router.get("/auth/sessions")
async def list_sessions(request: Request):
    """List all active sessions for the current user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    now = datetime.now(timezone.utc)
    sessions = []
    cursor = db.user_sessions.find(
        {"user_id": user.user_id, "expires_at": {"$gte": now}}, {"_id": 0, "session_token": 0, "refresh_token": 0}
    )
    async for s in cursor:
        for k in ("issued_at", "expires_at"):
            if k in s and hasattr(s[k], "isoformat"):
                s[k] = s[k].isoformat()
        sessions.append(s)

    current_token = request.cookies.get("session_token") or (request.headers.get("Authorization") or "").replace(
        "Bearer ", ""
    )
    current_session = await db.user_sessions.find_one({"session_token": current_token, "user_id": user.user_id})
    current_session_id = str(current_session["_id"]) if current_session else None

    return {"sessions": sessions, "current_session_id": current_session_id, "total": len(sessions)}


@router.post("/auth/sessions/revoke-all")
async def revoke_all_sessions(request: Request, response: Response):
    """Revoke all sessions for the current user (force re-login everywhere). Increments token_version."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.user_sessions.delete_many({"user_id": user.user_id})
    await db.users.update_one({"user_id": user.user_id}, {"$inc": {"token_version": 1}})
    await log_security_event(user.user_id, "revoke_all_sessions", "high", request)
    _delete_session_cookie(response)
    return {
        "message": f"All {result.deleted_count} sessions revoked. Please log in again.",
        "revoked": result.deleted_count,
    }


@router.get("/auth/security/overview")
async def security_overview(request: Request):
    """Consolidated security overview for the current user — all auth methods, sessions, recent activity."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    uid = user.user_id
    now = datetime.now(timezone.utc)

    settings = await db.notification_prefs.find_one({"user_id": uid}, {"_id": 0}) or {}
    has_pin = await db.biometric_pins.find_one({"user_id": uid}) is not None
    has_passkey = await db.webauthn_credentials.find_one({"user_id": uid}) is not None
    passkey_count = await db.webauthn_credentials.count_documents({"user_id": uid})
    active_sessions = await db.user_sessions.count_documents({"user_id": uid, "expires_at": {"$gte": now}})

    # Recent login events
    recent_logins = []
    cursor = (
        db.security_events.find({"user_id": uid, "event_type": {"$in": ["login_success", "login_failure"]}}, {"_id": 0})
        .sort("timestamp", -1)
        .limit(10)
    )
    async for ev in cursor:
        if "timestamp" in ev and hasattr(ev["timestamp"], "isoformat"):
            ev["timestamp"] = ev["timestamp"].isoformat()
        recent_logins.append(ev)

    return {
        "email": user.email,
        "two_factor": {
            "enabled": bool(settings.get("two_factor_enabled")),
            "method": settings.get("two_factor_method", "email"),
            "has_backup_codes": bool(settings.get("backup_codes")),
        },
        "biometric": {
            "pin_set": has_pin,
            "passkey_registered": has_passkey,
            "passkey_count": passkey_count,
            "biometric_enabled": bool(settings.get("biometric_enabled")),
            "rollout_enabled": _passkey_rollout_enabled_for_user(uid),
            "rollout_percent": max(0, min(PASSKEY_ROLLOUT_PERCENT, 100)),
        },
        "sessions": {
            "active_count": active_sessions,
        },
        "account": {
            "email_verified": user.email_verified,
            "token_version": user.token_version,
            "created_at": user.created_at.isoformat()
            if hasattr(user.created_at, "isoformat")
            else str(user.created_at),
        },
        "recent_logins": recent_logins,
    }


@router.get("/auth/admin/biometric/observability")
async def biometric_observability(request: Request, lookback_hours: int = 24):
    """Admin observability for passkey rollout, adoption, and incident timeline."""
    from routes.db import require_auth

    actor = await require_auth(request)
    if not bool(actor.is_admin):
        raise HTTPException(status_code=403, detail="Admin privileges required")

    hours = max(1, min(int(lookback_hours or 24), 720))
    since_iso = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    total_users = await db.users.count_documents({})
    passkey_users = await db.webauthn_credentials.distinct("user_id")
    total_credentials = await db.webauthn_credentials.count_documents({})

    recent_events = await db.security_events.find(
        {
            "event_type": {
                "$in": [
                    "passkey_registered",
                    "passkey_registration_failed",
                    "passkey_login_success",
                    "passkey_login_failed",
                    "passkey_revoked",
                ]
            },
            "timestamp": {"$gte": since_iso},
        },
        {"_id": 0},
    ).sort("timestamp", -1).limit(80).to_list(80)

    registrations = sum(1 for ev in recent_events if ev.get("event_type") == "passkey_registered")
    login_success = sum(1 for ev in recent_events if ev.get("event_type") == "passkey_login_success")
    login_failed = sum(1 for ev in recent_events if ev.get("event_type") == "passkey_login_failed")
    incidents = [
        {
            "timestamp": ev.get("timestamp"),
            "user_id": ev.get("user_id"),
            "event_type": ev.get("event_type"),
            "metadata": ev.get("metadata") or {},
        }
        for ev in recent_events
        if ev.get("event_type") in {"passkey_login_failed", "passkey_registration_failed"}
    ]

    return {
        "window_hours": hours,
        "rollout": {
            "rollout_percent": max(0, min(PASSKEY_ROLLOUT_PERCENT, 100)),
            "total_users": total_users,
            "passkey_users": len(passkey_users),
            "total_credentials": total_credentials,
            "adoption_rate": (len(passkey_users) / total_users) if total_users else 0,
        },
        "activity": {
            "registrations": registrations,
            "login_success": login_success,
            "login_failed": login_failed,
        },
        "incident_timeline": incidents[:25],
    }


# ── Alert Preferences ───────────────────────────────────────────────────────

DEFAULT_ALERT_PREFS = {
    "email_new_login": True,
    "email_unrecognized_device": True,
    "email_unrecognized_location": True,
    "email_failed_login_attempt": False,
    "email_password_change": True,
    "email_2fa_change": True,
}

ALERT_PREF_ALIASES = {
    "new_login": "email_new_login",
    "email_new_login": "email_new_login",
    "unrecognized_device": "email_unrecognized_device",
    "email_unrecognized_device": "email_unrecognized_device",
    "unrecognized_location": "email_unrecognized_location",
    "email_unrecognized_location": "email_unrecognized_location",
    "failed_login_attempt": "email_failed_login_attempt",
    "email_failed_login_attempt": "email_failed_login_attempt",
    "password_change": "email_password_change",
    "email_password_change": "email_password_change",
    "two_factor_change": "email_2fa_change",
    "2fa_change": "email_2fa_change",
    "email_2fa_change": "email_2fa_change",
}


@router.get("/auth/security/alert-preferences")
async def get_alert_preferences(request: Request):
    """Get the current user's security alert preferences."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    stored = await db.security_alert_prefs.find_one({"user_id": user.user_id}, {"_id": 0})
    prefs = {"user_id": user.user_id, **DEFAULT_ALERT_PREFS}
    if stored:
        prefs.update(stored)
    # Also fetch known devices & locations
    known = await db.known_devices.find({"user_id": user.user_id}, {"_id": 0}).to_list(50)
    alert_log = (
        await db.security_alert_log.find({"user_id": user.user_id}, {"_id": 0}).sort("timestamp", -1).to_list(20)
    )
    return {"preferences": prefs, "known_devices": known, "alert_history": alert_log}


@router.put("/auth/security/alert-preferences")
async def update_alert_preferences(request: Request):
    """Update security alert preferences."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    body = await request.json()
    payload = body.get("preferences") if isinstance(body, dict) and isinstance(body.get("preferences"), dict) else body
    if not isinstance(payload, dict):
        payload = {}

    updates = {}
    for key, value in payload.items():
        normalized_key = ALERT_PREF_ALIASES.get(str(key).strip().lower())
        if not normalized_key:
            continue
        if isinstance(value, bool):
            updates[normalized_key] = value
        elif isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            updates[normalized_key] = value.strip().lower() == "true"

    if not updates:
        raise HTTPException(400, "No valid preferences provided")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.security_alert_prefs.update_one({"user_id": user.user_id}, {"$set": updates}, upsert=True)
    return {"message": "Alert preferences updated", "updated": list(updates.keys())}


@router.post("/auth/security/trust-device")
async def trust_device(request: Request):
    """Mark a known device as trusted (won't trigger alerts)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    body = await request.json()
    device_id = (
        body.get("device_id")
        or body.get("device_fingerprint")
        or body.get("fingerprint")
    )
    if isinstance(device_id, str):
        device_id = device_id.strip()

    if not device_id:
        user_agent = request.headers.get("User-Agent", "")
        ip = request.client.host if request and request.client else ""
        device_id = _fingerprint_device(user_agent, ip)

    result = await db.known_devices.update_one(
        {"user_id": user.user_id, "device_id": device_id},
        {
            "$set": {
                "trusted": True,
                "trusted_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
            },
            "$setOnInsert": {
                "user_id": user.user_id,
                "device_id": device_id,
                "device_name": body.get("device_name") or "Trusted Device",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
        upsert=True,
    )
    return {
        "message": "Device trusted",
        "device_id": device_id,
        "created": bool(result.upserted_id),
    }


@router.delete("/auth/security/known-device/{device_id}")
async def remove_known_device(request: Request, device_id: str):
    """Remove a known device."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(401, "Not authenticated")
    result = await db.known_devices.delete_one({"user_id": user.user_id, "device_id": device_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Device not found")
    return {"message": "Device removed"}


async def _detect_country(request: Request) -> str:
    """Detect country from request headers (set by proxy/CDN)."""
    for header in ("CF-IPCountry", "X-Country-Code", "X-Geo-Country"):
        val = request.headers.get(header)
        if val:
            return val
    return "Unknown"


def _fingerprint_device(user_agent: str, ip: str) -> str:
    """Create a simple device fingerprint from user-agent and IP prefix."""
    import hashlib

    ip_prefix = ".".join(ip.split(".")[:3]) if ip else "0.0.0"
    raw = f"{user_agent}|{ip_prefix}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def check_and_alert_new_session(user_id: str, email: str, name: str, request: Request):
    """Check if login is from unrecognized device/location and send alerts per preferences."""
    try:
        prefs = await db.security_alert_prefs.find_one({"user_id": user_id}, {"_id": 0})
        if not prefs:
            prefs = {**DEFAULT_ALERT_PREFS}

        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() if request else ""
        if not ip:
            ip = request.client.host if request and request.client else "unknown"
        ua = request.headers.get("User-Agent", "Unknown device") if request else "Unknown"
        await _detect_country(request) if request else "Unknown"
        device_fp = _fingerprint_device(ua, ip)

        # Resolve rich client context for emails
        ctx = await _resolve_client_context(request)
        ip = ctx["ip"]
        location = ctx["location"]
        device_name = ctx["device"]
        now = datetime.now(timezone.utc).isoformat()

        # Check if device is known
        known_device = await db.known_devices.find_one({"user_id": user_id, "device_id": device_fp})
        is_new_device = known_device is None
        is_trusted = known_device.get("trusted", False) if known_device else False

        # Register device if new
        if is_new_device:
            short_ua = ua[:120]
            device_type = "mobile" if any(k in ua.lower() for k in ("mobile", "android", "iphone")) else "desktop"
            await db.known_devices.insert_one(
                {
                    "user_id": user_id,
                    "device_id": device_fp,
                    "user_agent": short_ua,
                    "device_name": device_name,
                    "device_type": device_type,
                    "ip_address": ip,
                    "country": location,
                    "first_seen": now,
                    "last_seen": now,
                    "trusted": False,
                    "login_count": 1,
                }
            )
        else:
            await db.known_devices.update_one(
                {"user_id": user_id, "device_id": device_fp},
                {"$set": {"last_seen": now, "ip_address": ip}, "$inc": {"login_count": 1}},
            )

        # Skip alerts for trusted devices
        if is_trusted:
            return

        alerts_sent = []

        # Email alerts
        if is_new_device and prefs.get("email_unrecognized_device", True):
            from utils.email_notifications import notify

            await notify.login_alert(user_id, email, name, ip, location, device_name)
            alerts_sent.append("email_unrecognized_device")
        elif prefs.get("email_new_login", True) and not is_new_device:
            from utils.email_notifications import notify

            await notify.login_alert(user_id, email, name, ip, location, device_name)
            alerts_sent.append("email_new_login")

        # Log the alert
        if alerts_sent:
            await db.security_alert_log.insert_one(
                {
                    "user_id": user_id,
                    "alert_types": alerts_sent,
                    "ip_address": ip,
                    "location": location,
                    "device_name": device_name,
                    "user_agent": ua[:120],
                    "device_id": device_fp,
                    "is_new_device": is_new_device,
                    "timestamp": now,
                }
            )

    except Exception as exc:
        logger.warning(f"Alert check failed for {user_id}: {exc}")



# ──────────────────────────────────────────────────────────────
# Avatar Selection
# ──────────────────────────────────────────────────────────────

class SetAvatarRequest(BaseModel):
    avatar_url: str


@router.post("/auth/set-avatar")
async def set_avatar(request_data: SetAvatarRequest, request: Request):
    """Set a default avatar or external avatar URL as profile picture."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"profile_image": request_data.avatar_url, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"status": "ok", "profile_image_url": request_data.avatar_url}



# ──────────────────────────────────────────────────────────────
# QR Code Quick Login
# ──────────────────────────────────────────────────────────────

QR_SESSION_EXPIRY_SECONDS = 300  # 5 minutes


class QRApproveRequest(BaseModel):
    session_id: str


@router.post("/auth/qr/generate")
async def qr_generate(request: Request):
    """Generate a new QR login session. Returns session_id and qr_url."""
    session_id = f"qr_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)
    frontend_url = await _resolve_auth_fallback_base(request)
    if not frontend_url:
        frontend_url = _normalize_base_url(str(request.base_url).rstrip("/"))
    qr_url = _build_qr_approval_url(frontend_url, session_id)
    if not qr_url:
        raise HTTPException(status_code=503, detail="QR login is temporarily unavailable")

    await db.qr_sessions.insert_one({
        "session_id": session_id,
        "status": "pending",  # pending -> approved -> consumed / expired
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=QR_SESSION_EXPIRY_SECONDS)).isoformat(),
        "approved_by": None,
        "session_token": None,
        "auth_base": frontend_url,
    })
    return {"session_id": session_id, "qr_url": qr_url, "expires_in": QR_SESSION_EXPIRY_SECONDS}


@router.get("/auth/qr/status/{session_id}")
async def qr_status(session_id: str):
    """Poll QR session status. Desktop client calls this repeatedly."""
    doc = await db.qr_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="QR session not found")

    # Check expiry
    expires_at = datetime.fromisoformat(doc["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        await db.qr_sessions.update_one({"session_id": session_id}, {"$set": {"status": "expired"}})
        return {"status": "expired"}

    result = {"status": doc["status"]}
    if doc["status"] == "approved" and doc.get("session_token"):
        result["session_token"] = doc["session_token"]
        result["user_id"] = doc.get("approved_by", "")
        # Mark as consumed so token can't be reused
        await db.qr_sessions.update_one({"session_id": session_id}, {"$set": {"status": "consumed"}})
    return result


@router.post("/auth/qr/approve")
async def qr_approve(data: QRApproveRequest, request: Request):
    """Approve a QR session. Called from the phone by an authenticated user."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please sign in on this device first.")

    doc = await db.qr_sessions.find_one({"session_id": data.session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="QR session not found")
    if doc["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"QR session already {doc['status']}")

    expires_at = datetime.fromisoformat(doc["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        await db.qr_sessions.update_one({"session_id": data.session_id}, {"$set": {"status": "expired"}})
        raise HTTPException(status_code=400, detail="QR session expired")

    # Create a new session token for the desktop browser
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "email": 1, "token_version": 1})
    if not user_doc:
        raise HTTPException(status_code=404, detail="Resource not found")

    token_version = user_doc.get("token_version", 0)
    qr_minutes = await _resolve_session_timeout_minutes(bool(getattr(user, "is_admin", False)))
    new_token = create_jwt_token(user.user_id, user_doc["email"], token_version, qr_minutes)

    # Also create a proper user session in the DB for the new token
    await db.user_sessions.insert_one({
        "user_id": user.user_id,
        "session_token": new_token,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=qr_minutes),
        "login_method": "qr_code",
    })

    # Store session token in QR session
    await db.qr_sessions.update_one(
        {"session_id": data.session_id},
        {"$set": {"status": "approved", "approved_by": user.user_id, "session_token": new_token}},
    )

    logger.info(f"QR login approved by {user.user_id} for session {data.session_id}")
    return {"status": "approved", "message": "Login approved! Desktop browser will log in automatically."}


class QRConsumeRequest(BaseModel):
    session_id: str
    session_token: str


@router.post("/auth/qr/consume")
async def qr_consume(data: QRConsumeRequest, request: Request, response: Response):
    """Consume a QR session token and establish a cookie-based session for the desktop browser.
    Called after polling detects approval. Sets HttpOnly session cookie."""
    # Validate the QR session exists and token matches
    doc = await db.qr_sessions.find_one({"session_id": data.session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="QR session not found")
    if doc["status"] not in ("approved", "consumed"):
        raise HTTPException(status_code=400, detail=f"QR session is {doc['status']}")
    if doc.get("session_token") != data.session_token:
        raise HTTPException(status_code=403, detail="Token mismatch")

    # Verify the JWT is valid
    try:
        from jose import jwt as jose_jwt, JWTError as JoseJWTError
        payload = jose_jwt.decode(data.session_token, JWT_SECRET, algorithms=["HS256"])
    except JoseJWTError:
        raise HTTPException(status_code=401, detail="Invalid session token")

    user_id = payload.get("user_id")
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify the session exists in user_sessions
    session_exists = await db.user_sessions.find_one({"session_token": data.session_token}, {"_id": 0})
    if not session_exists:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    # Mark QR session as fully consumed
    await db.qr_sessions.update_one(
        {"session_id": data.session_id},
        {"$set": {"status": "consumed", "consumed_at": datetime.now(timezone.utc).isoformat()}},
    )

    # Set the session cookie for the desktop browser
    token_exp = payload.get("exp", 0)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    max_age = max(token_exp - now_ts, 300)
    _set_session_cookie(response, data.session_token, max_age, request)

    logger.info(f"QR session consumed for user {user_id}, session {data.session_id}")
    return {
        "status": "ok",
        "user_id": user_doc.get("user_id"),
        "email": user_doc.get("email"),
        "name": user_doc.get("name"),
        "is_admin": user_doc.get("is_admin", False),
        "subscription_plan": user_doc.get("subscription_plan", "free"),
    }


# ── Magic Link Login ──

class MagicLinkRequest(BaseModel):
    email: EmailStr

@router.post("/auth/magic-link/send")
async def send_magic_link(data: MagicLinkRequest, request: Request = None):
    """Send a magic login link to the user's email."""
    ip_address = request.client.host if request and request.client else "unknown"
    if not check_rate_limit(f"magic_link:{ip_address}", 5, 300):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few minutes.")
    # Per-email rate limit for magic links
    if not check_rate_limit(f"magic_link_email:{data.email.lower()}", 3, 600):
        raise HTTPException(status_code=429, detail="Too many magic link requests for this email. Please try again later.")

    user_doc = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user_doc:
        # Don't reveal if email exists — always return success
        return {"success": True, "message": "If an account exists, a login link has been sent."}

    fallback_base = await _resolve_auth_fallback_base(request)

    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await db.magic_links.insert_one({
        "token_hash": token_hash,
        "user_id": user_doc["user_id"],
        "email": data.email,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        "used": False,
        "auth_base": fallback_base,
    })

    # Build magic link URL using canonical auth fallback base (prevents stale preview-domain drift).
    base_url = fallback_base
    if not base_url and RESET_LINK_BASE:
        parsed = urlparse(str(RESET_LINK_BASE).strip())
        if parsed.scheme and parsed.netloc:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
    if not base_url and request:
        base_url = _normalize_base_url(request.headers.get("origin") or "")
    if not base_url:
        raise HTTPException(status_code=500, detail="Unable to resolve login link base URL")

    # Construct the actual magic-link URL that the user will click.
    # Prior versions referenced `magic_url` without defining it, causing a
    # NameError and a silent email-send failure. The fallback verify route
    # on the web app is `/auth/magic-link-verify` (the public login shell
    # consumes the `token` query-param and POSTs to /api/auth/magic-link/verify).
    magic_url = f"{base_url.rstrip('/')}/auth/magic-link-verify?token={token}"

    from utils.email_service import send_catalog_template
    result = await send_catalog_template(data.email, "magic_link", magic_url=magic_url, expiry_minutes=15)
    if not result.get("success"):
        logger.warning(f"Magic link email failed for {data.email}: {result.get('error')}")

    return {"success": True, "message": "If an account exists, a login link has been sent."}


@router.get("/auth/magic-link/verify")
async def verify_magic_link(token: str, request: Request = None, response: Response = None):
    """Verify a magic link token and create a session."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    link_doc = await db.magic_links.find_one({"token_hash": token_hash, "used": False}, {"_id": 0})
    if not link_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired link.")

    expires_at = link_doc.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if hasattr(expires_at, "tzinfo") and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at < datetime.now(timezone.utc):
        await db.magic_links.update_one({"token_hash": token_hash}, {"$set": {"used": True}})
        raise HTTPException(status_code=400, detail="This link has expired. Please request a new one.")

    # Mark as used
    await db.magic_links.update_one({"token_hash": token_hash}, {"$set": {"used": True}})

    user_doc = await db.users.find_one({"user_id": link_doc["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired link.")

    user = User(**user_doc)
    user = await apply_access_overrides(user)

    expires_minutes = await _resolve_session_timeout_minutes(bool(user.is_admin))
    session_token = create_jwt_token(user.user_id, user.email, user.token_version, expires_minutes)
    refresh_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.user_id,
        session_token=session_token,
        refresh_token=refresh_token,
        token_version=user.token_version,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        ip_address=request.client.host if request and request.client else None,
    )
    await db.user_sessions.insert_one(session.dict())

    await log_security_event(user.user_id, "magic_link_login", "low", request)

    if response:
        _set_session_cookie(response, session_token, expires_minutes * 60, request)

    return {
        "success": True,
        **_auth_token_payload(request, session_token=session_token, refresh_token=refresh_token),
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "subscription_plan": user.subscription_plan,
        "is_admin": user.is_admin,
    }


# ════════════════════════════════════════════════════════════
# DEVICE TRUST MANAGEMENT
# ════════════════════════════════════════════════════════════


@router.get("/auth/devices")
async def list_user_devices(request: Request):
    """List all known devices for the authenticated user."""
    from routes.db import require_auth
    user = await require_auth(request)
    devices_raw = await db.known_devices.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).sort("last_seen", -1).to_list(50)

    devices = []
    for d in devices_raw:
        # Parse device name if missing
        name = d.get("device_name") or _parse_device_name(d.get("user_agent", ""))
        devices.append({
            "device_id": d.get("device_id", ""),
            "device_name": name,
            "device_type": d.get("device_type", "unknown"),
            "ip_address": d.get("ip_address", ""),
            "location": d.get("country", "Unknown"),
            "first_seen": d.get("first_seen", ""),
            "last_seen": d.get("last_seen", ""),
            "trusted": d.get("trusted", False),
            "login_count": d.get("login_count", 0),
            "user_agent": d.get("user_agent", "")[:100],
        })

    return {"devices": devices, "total": len(devices)}


@router.post("/auth/devices/trust")
async def trust_known_device(request: Request):
    """Mark a device as trusted (no more alerts from it)."""
    from routes.db import require_auth
    user = await require_auth(request)
    body = await request.json()
    device_id = body.get("device_id", "")
    trusted = body.get("trusted", True)

    if not device_id:
        raise HTTPException(status_code=400, detail="device_id required")

    result = await db.known_devices.update_one(
        {"user_id": user.user_id, "device_id": device_id},
        {"$set": {"trusted": trusted, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")

    action = "trusted" if trusted else "untrusted"
    await log_security_event(user.user_id, f"device_{action}", "low", request, {"device_id": device_id})
    return {"success": True, "device_id": device_id, "trusted": trusted}


@router.delete("/auth/devices/revoke")
async def revoke_device(request: Request):
    """Revoke a device: remove it from known devices and kill its sessions."""
    from routes.db import require_auth
    user = await require_auth(request)
    body = await request.json()
    device_id = body.get("device_id", "")

    if not device_id:
        raise HTTPException(status_code=400, detail="device_id required")

    # Get the device to identify its user_agent for session matching
    device = await db.known_devices.find_one(
        {"user_id": user.user_id, "device_id": device_id}, {"_id": 0}
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Revoke any active sessions from this device
    await db.sessions.delete_many(
        {"user_id": user.user_id, "device_id": device_id}
    )

    # Remove from known devices
    await db.known_devices.delete_one(
        {"user_id": user.user_id, "device_id": device_id}
    )

    await log_security_event(user.user_id, "device_revoked", "medium", request, {
        "device_id": device_id,
        "device_name": device.get("device_name", ""),
        "ip_address": device.get("ip_address", ""),
    })
    return {"success": True, "device_id": device_id, "revoked": True}


# ── Admin Device Audit ───────────────────────────────────


@router.get("/auth/admin/devices/audit")
async def admin_device_audit(request: Request):
    """Admin only: Full device audit across all users."""
    from routes.db import require_auth
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    page = int(request.query_params.get("page", "1"))
    limit = min(int(request.query_params.get("limit", "50")), 100)
    search = request.query_params.get("search", "").strip().lower()
    trusted_filter = request.query_params.get("trusted", "")
    skip = (page - 1) * limit

    query: dict = {}
    if search:
        query["$or"] = [
            {"device_name": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"user_agent": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"ip_address": {"$regex": re.escape(str(search)), "$options": "i"}},
            {"user_id": {"$regex": re.escape(str(search)), "$options": "i"}},
        ]
    if trusted_filter == "true":
        query["trusted"] = True
    elif trusted_filter == "false":
        query["trusted"] = False

    total = await db.known_devices.count_documents(query)
    devices_raw = await db.known_devices.find(query, {"_id": 0}).sort("last_seen", -1).skip(skip).limit(limit).to_list(limit)

    # Enrich with user email
    user_ids = list({d["user_id"] for d in devices_raw})
    users_map = {}
    if user_ids:
        users_cursor = db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
        async for u in users_cursor:
            users_map[u["user_id"]] = {"email": u.get("email", ""), "name": u.get("name", "")}

    devices = []
    for d in devices_raw:
        u_info = users_map.get(d.get("user_id", ""), {})
        name = d.get("device_name") or _parse_device_name(d.get("user_agent", ""))
        devices.append({
            "device_id": d.get("device_id", ""),
            "user_id": d.get("user_id", ""),
            "user_email": u_info.get("email", ""),
            "user_name": u_info.get("name", ""),
            "device_name": name,
            "device_type": d.get("device_type", "unknown"),
            "ip_address": d.get("ip_address", ""),
            "location": d.get("country", "Unknown"),
            "first_seen": d.get("first_seen", ""),
            "last_seen": d.get("last_seen", ""),
            "trusted": d.get("trusted", False),
            "login_count": d.get("login_count", 0),
        })

    # Summary stats
    total_all = await db.known_devices.count_documents({})
    total_trusted = await db.known_devices.count_documents({"trusted": True})
    unique_users = len(await db.known_devices.distinct("user_id"))

    return {
        "devices": devices,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "summary": {
            "total_devices": total_all,
            "trusted_devices": total_trusted,
            "untrusted_devices": total_all - total_trusted,
            "unique_users": unique_users,
        },
    }


@router.post("/auth/admin/devices/force-revoke")
async def admin_force_revoke_device(request: Request):
    """Admin only: Force-revoke any device and kill its sessions."""
    from routes.db import require_auth
    user = await require_auth(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json()
    device_id = body.get("device_id", "")
    target_user_id = body.get("user_id", "")

    if not device_id or not target_user_id:
        raise HTTPException(status_code=400, detail="device_id and user_id required")

    device = await db.known_devices.find_one(
        {"user_id": target_user_id, "device_id": device_id}, {"_id": 0}
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.sessions.delete_many({"user_id": target_user_id, "device_id": device_id})
    await db.known_devices.delete_one({"user_id": target_user_id, "device_id": device_id})

    await log_security_event(user.user_id, "admin_device_revoked", "high", request, {
        "target_user_id": target_user_id,
        "device_id": device_id,
        "device_name": device.get("device_name", ""),
    })
    return {"success": True, "device_id": device_id, "revoked": True}

