"""Subscription Enforcement Middleware — PLATFORM-WIDE ACCESS CONTROL.

Access tiers:
  Free    → Limited (dashboard, profile, 3 AI conversations/day, basic features)
  Basic   → Near-unlimited (most features, 10 conversations/day)
  Premium → Full unlimited (everything including advanced exports, analytics, enterprise)

This middleware intercepts ALL /api/ requests and enforces subscription level
based on the route path. One central config — no per-route wiring needed.
"""

import os
import re
import logging
import uuid
import jwt
from datetime import datetime, timezone, timedelta
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from fastapi import Request
from shared.pricing_policy import get_plan_amount

from routes.db import db, log_authorization_audit
from utils.access_control_engine import (
    evaluate_api_access,
    reconcile_due_transition,
    is_admin_flag,
    compute_effective_plan,
    resolve_feature_meter,
    get_feature_daily_action_limit,
    SUBSCRIPTION_ACCESS_POLICY_VERSION,
)

logger = logging.getLogger("subscription_enforcement")
JWT_SECRET = os.environ.get("JWT_SECRET", "")

# ────────────────────────────────────────────────────────────────
# ROUTE ACCESS CONFIGURATION
# ────────────────────────────────────────────────────────────────

# PUBLIC — No authentication required (webhooks, auth, health, public pages)
PUBLIC_PATTERNS = [
    r"^/api/auth/login",
    r"^/api/auth/register",
    r"^/api/auth/verify",
    r"^/api/auth/forgot",
    r"^/api/auth/reset",
    r"^/api/auth/google",
    r"^/api/auth/sso",
    r"^/api/auth/refresh",
    r"^/api/webhook/",
    r"^/api/payments/fedapay/webhook",
    r"^/api/paypal/webhook",
    r"^/api/iap/(apple|google)/webhook",
    r"^/api/resend-webhook",
    r"^/api/health",
    r"^/api/config",
    r"^/api/i18n/",
    r"^/api/contact",
    r"^/api/share/",
    r"^/api/support/faq",
    r"^/api/support/articles",
    r"^/api/changelog",
    r"^/api/features/registry",
    r"^/api/iap/products",
    r"^/api/payments/available",
    r"^/api/payments/currencies",
    r"^/api/payments/config",
    r"^/api/subscriptions/plans",
    r"^/api/subscriptions/renewal-banner",
    r"^/api/geo/",
    r"^/api/public/",
    r"^/api/vitals/page-perf",
    r"^/api/vitals/page-optimizations",
    r"^/api/live-activity/",
    r"^/api/system/vanity-metrics",
    r"^/api/system/live-metrics",
    r"^/api/vitals/report",
    r"^/api/platform-shell-health/ingest",
    r"^/api/platform-shell-health/realtime-ingest",
    r"^/api/status/public",
    r"^/api/platform-control/public/",
    r"^/api/jobs/alerts/unsubscribe",
    r"^/api/ai-learn/certificates/verify/",
]

# FREE_ALLOWED — Any authenticated user regardless of plan
FREE_PATTERNS = [
    r"^/api/auth/",
    r"^/api/access-control/",
    r"^/api/notifications",
    r"^/api/weekly-digest/",
    r"^/api/ai-access/status",
    r"^/api/ai-access/tier-comparison",
    r"^/api/payments/",
    r"^/api/paypal/",
    r"^/api/fedapay/",
    r"^/api/subscriptions/",
    r"^/api/subscriptions/lifecycle/",
    r"^/api/iap/",
    r"^/api/home/",
    r"^/api/home-dashboard",
    r"^/api/onboarding",
    r"^/api/feature-access",
    r"^/api/features",
    r"^/api/gamification",
    r"^/api/conversations/",
    r"^/api/scenarios",
    r"^/api/ai-solver",
    r"^/api/ai-problem-solver",
    r"^/api/ai-coaching-team",
    r"^/api/ai-chat",
    r"^/api/cars/",
    r"^/api/real-estate/",
    r"^/api/ai-image($|/)",
    r"^/api/push",
    r"^/api/dashboard",
    r"^/api/photo/upload",
    r"^/api/mfa/",
    r"^/api/support/",
    r"^/api/referrals/",
    r"^/api/id-verification/",
    r"^/api/id-checker/",
    r"^/api/email-notifications/preferences",
    r"^/api/accessibility",
    r"^/api/system/vanity-metrics",
    r"^/api/email-notifications/track/",
    r"^/api/prompt-experiment/",
    r"^/api/ai-learn/",
    r"^/api/tos/",
    r"^/api/subscription-prompt/telemetry",
    r"^/api/bill-generator/",
    r"^/api/word-forge/",
    r"^/api/videos/",
    r"^/api/audio-studio/v2/bootstrap",
    r"^/api/audio-studio/v2/play",
    r"^/api/audio-studio/v2/follow-artist",
    r"^/api/audio-studio/v2/unfollow-artist",
    r"^/api/audio-studio/v2/daily-drop-inbox",
    r"^/api/audio-studio/v2/daily-drop-inbox/mark-listened",
    r"^/api/podcasts/v2/bootstrap",
    r"^/api/podcasts/v2/play",
    r"^/api/podcasts/v2/daily-drop-inbox",
    r"^/api/podcasts/v2/daily-drop-inbox/mark-listened",
    r"^/api/podcasts/v2/continue-listening",
    r"^/api/podcasts/v2/season-arc",
    r"^/api/podcasts/v2/source-health",
    r"^/api/sports/v2/bootstrap",
    r"^/api/sports/v2/play",
    r"^/api/sports/v2/secure-stream",
    r"^/api/sports/v2/daily-drop-inbox",
    r"^/api/sports/v2/daily-drop-inbox/mark-listened",
    r"^/api/sports/v2/follow-league",
    r"^/api/sports/v2/unfollow-league",
    r"^/api/sports/v2/reminder-settings",
    r"^/api/sports/v2/live-now",
    r"^/api/sports/v2/continue-watching",
    r"^/api/sports/v2/matchday-streak",
    r"^/api/sports/v2/prediction-challenges",
    r"^/api/sports/v2/prediction-challenges/submit",
    r"^/api/ai-photo-studio/",
    r"^/api/jobs/",
    r"^/api/employers/",
    r"^/api/employers/(apply|upload-document|my-application|my-permissions|permissions|messages/|documents/|resubmit-info|reverify-status|reverify)(/|$)",
]

# PREMIUM_ONLY — Requires Premium plan
PREMIUM_PATTERNS = [
    r"^/api/admin/enterprise",
    r"^/api/admin/automation",
    r"^/api/team-management",
    r"^/api/team-analytics",
    r"^/api/admin/ai-insights",
    r"^/api/admin/ai-remediation",
    r"^/api/admin/anomaly-detection",
    r"^/api/admin/auto-detect",
    r"^/api/admin/auto-fix-engine",
    r"^/api/admin/cdn",
    r"^/api/collab-docs",
    r"^/api/whiteboard",
    r"^/api/workspace",
    r"^/api/reports/",
    r"^/api/content-studio",
    r"^/api/ai-engine/",
    r"^/api/predictive",
    r"^/api/realtime-intelligence",
    r"^/api/siem/",
    r"^/api/phone/call/start",
    r"^/api/phone/chat",
    r"^/api/coaching/tone-analysis",
    r"^/api/ai-document-analyzer/",
    r"^/api/predictive-timeline/",
]

# ADMIN routes — require admin role (checked separately)
ADMIN_PREFIX = "/api/admin/"

# Everything else → BASIC_REQUIRED (default)

# ────────────────────────────────────────────────────────────────
# PLAN HIERARCHY
# ────────────────────────────────────────────────────────────────
PLAN_LEVEL = {"free": 0, "basic": 1, "premium": 2}

# Emails that bypass all subscription checks (system/admin accounts)
EXEMPT_EMAILS = set(
    email.strip().lower()
    for email in os.environ.get("ADMIN_EMAILS", "").split(",")
    if email.strip()
)


def _match_any(path: str, patterns: list[str]) -> bool:
    return any(re.match(p, path) for p in patterns)


def _get_required_level(path: str) -> int:
    """Determine the minimum subscription level required for a path.
    Returns: 0=public/free, 1=basic, 2=premium
    """
    if _match_any(path, PUBLIC_PATTERNS):
        return -1  # No auth needed
    if _match_any(path, FREE_PATTERNS):
        return 0   # Any authenticated user
    if _match_any(path, PREMIUM_PATTERNS):
        return 2   # Premium only
    return 1        # Default: Basic required


class SubscriptionEnforcementMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces subscription access control on all /api/ routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        normalized_path = str(path or "").strip().lower()

        # Only enforce on /api/ routes
        if not path.startswith("/api/"):
            return await call_next(request)

        # Skip enforcement for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Fast-path: skip enforcement for high-frequency safe endpoints
        _sub_skip = (
            "/api/health", "/api/system/health", "/api/config/global",
            "/api/features/registry", "/api/features/gallery", "/api/vitals/report",
            "/api/static/", "/api/system/vanity-metrics", "/api/system/live-metrics",
            "/api/prompt-experiment/", "/api/auth/login", "/api/auth/register",
            "/api/auth/me", "/api/auth/verify-otp", "/api/auth/forgot-password",
            "/api/changelog/", "/api/i18n/", "/api/platform-shell-health/",
            "/api/admin/session-replay/record", "/api/admin/live-activity/log-event",
            "/api/admin/autonomous-engine/feedback/collect",
            "/api/onboarding", "/api/notifications/",
            "/api/home/", "/api/leaderboard", "/api/gamification/",
            "/api/progress/", "/api/achievement", "/api/referrals/",
            "/api/profile", "/api/auth/devices", "/api/auth/security/",
            "/api/auth/change-password", "/api/auth/2fa/",
            "/api/contact/", "/api/feedback/",
        )
        if any(path.startswith(p) for p in _sub_skip):
            return await call_next(request)

        public_decision = evaluate_api_access(path, request.method, None)
        if public_decision.get("reason") == "public":
            return await call_next(request)

        # Extract user token with the same deterministic precedence as get_current_user:
        # Authorization Bearer token wins over cookies so reused automated sessions cannot leak roles.
        session_token = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ", 1)[1]
        if not session_token:
            session_token = request.cookies.get("session_token")
        if not session_token:
            _token_qp_allowed_prefixes = (
                "/api/ws/",
                "/api/id-verification/",
                "/api/id-checker/",
                "/api/mock-interview/",
            )
            if any(path.startswith(prefix) for prefix in _token_qp_allowed_prefixes):
                session_token = request.query_params.get("token")
        if not session_token:
            # No token at all — let the route handler deal with 401
            return await call_next(request)

        # Decode JWT and look up session (matching get_current_user logic)
        try:
            jwt.decode(session_token, JWT_SECRET, algorithms=["HS256"])
        except Exception:
            return await call_next(request)

        session = await db.user_sessions.find_one(
            {"session_token": session_token},
            {"_id": 0, "user_id": 1},
        )
        if not session:
            return await call_next(request)

        user_doc = await db.users.find_one(
            {"user_id": session["user_id"]},
            {
                "_id": 0, "user_id": 1, "email": 1, "is_admin": 1,
                "subscription_plan": 1, "subscription_status": 1,
                "subscription_end_date": 1, "subscription_permanent": 1,
                "payment_verified": 1, "full_access": 1,
                "premium_access": 1, "platform_role": 1,
                "employee_permissions": 1,
                "pending_subscription_transition": 1,
            },
        )
        if not user_doc:
            return await call_next(request)

        # Global locked protocol hard guard:
        # /api/admin/*analytics* and /api/admin/*insights* are strict admin-only.
        if normalized_path.startswith("/api/admin/") and (
            "analytics" in normalized_path or "insights" in normalized_path
        ) and not is_admin_flag(user_doc.get("is_admin")):
            await log_authorization_audit(
                actor_user_id=user_doc.get("user_id"),
                actor_email=user_doc.get("email"),
                action="api_access_check",
                outcome="denied",
                request=request,
                metadata={
                    "reason": "admin_required",
                    "scope": "global_admin_analytics_insights_lock",
                },
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Admin Access Required",
                    "message": "This route requires administrator access.",
                    "required_permission": None,
                },
            )

        user_doc, _ = await reconcile_due_transition(db, user_doc)

        email = (user_doc.get("email") or "").lower()

        # ── Bypass for exempt/system accounts ──
        if email in EXEMPT_EMAILS:
            return await call_next(request)

        decision = evaluate_api_access(path, request.method, user_doc)
        if decision.get("allowed"):
            meter_block = await self._enforce_feature_daily_meter(request, path, user_doc)
            if meter_block is not None:
                return meter_block
            if path.startswith(ADMIN_PREFIX) and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                await log_authorization_audit(
                    actor_user_id=user_doc.get("user_id"),
                    actor_email=user_doc.get("email"),
                    action="admin_surface_access",
                    outcome="allowed",
                    request=request,
                    metadata={
                        "reason": decision.get("reason"),
                        "required_permission": decision.get("required_permission"),
                    },
                )
            return await call_next(request)

        await log_authorization_audit(
            actor_user_id=user_doc.get("user_id"),
            actor_email=user_doc.get("email"),
            action="api_access_check",
            outcome="denied",
            request=request,
            metadata={
                "reason": decision.get("reason"),
                "required_plan": decision.get("required_plan"),
                "required_permission": decision.get("required_permission"),
                "current_plan": decision.get("current_plan"),
            },
        )

        if decision.get("reason") in {"admin_or_employee_permission_required", "admin_required"}:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Admin Access Required",
                    "message": "This route requires administrator access.",
                    "required_permission": decision.get("required_permission"),
                },
            )

        if decision.get("reason") == "subscription_required":
            required_plan = decision.get("required_plan", "basic")
            from utils.preprod_entitlement_lock import is_preprod_lock_active

            message = f"This feature requires a {required_plan.capitalize()} plan or higher. Upgrade now to unlock access."
            content = {
                "error": "Subscription Required",
                "message": message,
                "current_plan": decision.get("current_plan", "free"),
                "required_plan": required_plan,
                "upgrade_url": "/subscription/plans",
            }
            if is_preprod_lock_active():
                content["message"] = "Subscriptions are disabled until production launch."
                content["detail"] = "Subscriptions are disabled until production launch."
            return JSONResponse(status_code=403, content=content)

        return JSONResponse(
            status_code=403,
            content={
                "error": "Access Denied",
                "message": "Your role or subscription does not allow this action.",
            },
        )

    async def _enforce_feature_daily_meter(self, request: Request, path: str, user_doc: dict):
        """AI-driven entitlement meter: Free/Basic daily action quotas per canonical feature.

        Reads (GET/HEAD) are always open so users can explore every feature.
        Returns a 429 JSONResponse when the daily quota is exhausted, else None.
        """
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        if is_admin_flag(user_doc.get("is_admin")):
            return None
        meter = resolve_feature_meter(path)
        if not meter or meter.get("self_enforced"):
            return None
        plan = compute_effective_plan(user_doc)
        limit = get_feature_daily_action_limit(meter, plan)
        if limit < 0:
            return None

        feature_key = meter["feature_key"]
        user_id = user_doc.get("user_id")
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        used = await db.feature_usage_meter.count_documents(
            {"user_id": user_id, "feature_key": feature_key, "day": day}
        )
        if used >= limit:
            await log_authorization_audit(
                actor_user_id=user_id,
                actor_email=user_doc.get("email"),
                action="feature_daily_meter",
                outcome="limited",
                request=request,
                metadata={
                    "feature_key": feature_key,
                    "plan": plan,
                    "used": used,
                    "limit": limit,
                    "policy_version": SUBSCRIPTION_ACCESS_POLICY_VERSION,
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Daily Feature Limit Reached",
                    "error_code": "feature_daily_limit_reached",
                    "message": (
                        f"You've used your {limit} free daily actions for this feature. "
                        "Upgrade to Basic for almost unlimited access or Premium for full unlimited access."
                        if plan == "free"
                        else f"Daily action limit reached ({limit}). Upgrade to Premium for full unlimited access."
                    ),
                    "feature_key": feature_key,
                    "used": used,
                    "limit": limit,
                    "current_plan": plan,
                    "required_plan": "basic" if plan == "free" else "premium",
                    "upgrade_url": "/subscription/plans",
                    "policy_version": SUBSCRIPTION_ACCESS_POLICY_VERSION,
                },
            )

        await db.feature_usage_meter.insert_one(
            {
                "usage_id": f"fum_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "feature_key": feature_key,
                "plan": plan,
                "method": request.method,
                "path": path,
                "day": day,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return None

# ────────────────────────────────────────────────────────────────
# LEGACY FUNCTIONS (kept for backward compatibility)
# ────────────────────────────────────────────────────────────────
from routes.db import get_current_user, User
from fastapi import HTTPException


async def validate_subscription(request: Request, required_plan: str = "basic") -> User:
    """Validate subscription — now a lightweight wrapper since middleware handles enforcement."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_basic_subscription(request: Request) -> User:
    return await validate_subscription(request, "basic")


async def require_premium_subscription(request: Request) -> User:
    return await validate_subscription(request, "premium")


async def _downgrade_user(user_id: str):
    """Downgrade user to free plan."""
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1, "subscription_end_date": 1},
    ) or {}
    previous_plan = str(user_doc.get("subscription_plan") or "premium").capitalize()
    expired_on_raw = user_doc.get("subscription_end_date")
    if hasattr(expired_on_raw, "strftime"):
        expired_on = expired_on_raw.strftime("%B %d, %Y")
    else:
        expired_on = str(expired_on_raw or datetime.now(timezone.utc).date())[:10]

    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "subscription_plan": "free",
                "subscription_status": "expired",
                "payment_verified": False,
                "updated_at": datetime.now(timezone.utc),
                "reminder_7d_sent": None,
                "reminder_3d_sent": None,
                "reminder_1d_sent": None,
            }
        },
    )
    logger.info(f"User {user_id} auto-downgraded to free (subscription expired)")

    await dispatch_subscription_expiry_notification(
        user_id,
        source_provider="system",
        reason="expired",
        plan_name_override=previous_plan,
        expired_on_override=expired_on,
    )

    await db.subscription_audit_log.insert_one(
        {
            "user_id": user_id,
            "action": "auto_downgrade",
            "reason": "subscription_expired",
            "timestamp": datetime.now(timezone.utc),
        }
    )


async def dispatch_subscription_expiry_notification(
    user_id: str,
    *,
    source_provider: str = "system",
    reason: str = "expired",
    plan_name_override: str | None = None,
    expired_on_override: str | None = None,
    transaction_filter: dict | None = None,
) -> dict:
    """Create unified post-expiry notification behavior across all providers.

    Idempotency window: one expiry notification per user/provider/reason/day.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "user_id": 1,
            "email": 1,
            "name": 1,
            "subscription_plan": 1,
            "subscription_end_date": 1,
        },
    ) or {}

    plan_name = str(plan_name_override or user_doc.get("subscription_plan") or "premium").capitalize()
    expired_on_raw = expired_on_override or user_doc.get("subscription_end_date")
    if hasattr(expired_on_raw, "strftime"):
        expired_on = expired_on_raw.strftime("%B %d, %Y")
    else:
        expired_on = str(expired_on_raw or now.date())[:10]

    dedupe_key = f"subscription_expired::{user_id}::{str(source_provider).lower()}::{str(reason).lower()}::{now.strftime('%Y-%m-%d')}"
    existing = await db.notifications.find_one(
        {
            "user_id": user_id,
            "type": "subscription_expired",
            "data.dedupe_key": dedupe_key,
        },
        {"_id": 0, "id": 1},
    )
    if existing:
        if transaction_filter:
            await db.payment_transactions.update_one(
                transaction_filter,
                {
                    "$set": {
                        "notification_sent": True,
                        "notification_sent_at": now_iso,
                        "expiry_notification_sent": True,
                        "expiry_notification_sent_at": now_iso,
                        "expiry_notification_reason": str(reason),
                        "expiry_notification_provider": str(source_provider),
                    }
                },
            )
        return {"status": "duplicate_suppressed", "dedupe_key": dedupe_key, "notification_id": existing.get("id")}

    await db.notifications.insert_one(
        {
            "id": f"notif_expired_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "type": "subscription_expired",
            "title": "Subscription Expired",
            "message": "Your subscription has expired. Renew now to restore full access.",
            "icon": "alert-circle",
            "read": False,
            "action_url": "/subscription/plans",
            "created_at": now_iso,
            "data": {
                "dedupe_key": dedupe_key,
                "provider": str(source_provider),
                "reason": str(reason),
                "plan_name": plan_name,
                "expired_on": expired_on,
            },
        }
    )

    try:
        from utils.email_service import is_email_configured, send_catalog_template
        from utils.email_notifications import _log_email

        if is_email_configured() and user_doc.get("email"):
            result = await send_catalog_template(
                recipient_email=user_doc["email"],
                template_key="subscription_expired",
                recipient_name=user_doc.get("name") or user_doc.get("email") or "there",
                user_name=user_doc.get("name") or user_doc.get("email") or "there",
                plan_name=plan_name,
                expired_on=expired_on,
            )
            subject = "Subscription Expired"
            if result.get("success"):
                await _log_email(user_id, user_doc["email"], "subscription_expired", subject, "sent", message_id=result.get("message_id", ""))
            else:
                await _log_email(user_id, user_doc["email"], "subscription_expired", subject, "failed", error=result.get("error", "unknown"))
    except Exception as exc:
        logger.error(f"Subscription expired email trigger error for {user_id}: {exc}")

    await db.subscription_audit_log.insert_one(
        {
            "user_id": user_id,
            "action": "subscription_expiry_notification_sent",
            "reason": str(reason),
            "provider": str(source_provider),
            "timestamp": now,
        }
    )

    if transaction_filter:
        await db.payment_transactions.update_one(
            transaction_filter,
            {
                "$set": {
                    "notification_sent": True,
                    "notification_sent_at": now_iso,
                    "expiry_notification_sent": True,
                    "expiry_notification_sent_at": now_iso,
                    "expiry_notification_reason": str(reason),
                    "expiry_notification_provider": str(source_provider),
                }
            },
        )

    return {"status": "sent", "dedupe_key": dedupe_key}


def _is_payment_exempt(email: str) -> bool:
    return email.lower() in EXEMPT_EMAILS


async def check_and_expire_subscriptions():
    """Batch check for expired subscriptions. Run periodically."""
    now = datetime.now(timezone.utc)
    expired_cursor = db.users.find(
        {
            "subscription_plan": {"$in": ["basic", "premium"]},
            "subscription_end_date": {"$lt": now},
            "subscription_status": {"$ne": "expired"},
        },
        {"_id": 0, "user_id": 1, "email": 1},
    )

    count = 0
    async for user in expired_cursor:
        if not _is_payment_exempt(user.get("email", "")):
            await _downgrade_user(user["user_id"])
            count += 1

    if count > 0:
        logger.info(f"Subscription expiry check: {count} users downgraded")
    return count


async def send_expiry_reminders_multi_touch():
    """Send multi-touch reminder sequence: 7-day, 3-day, 1-day before expiry."""
    from utils.email_service import is_email_configured

    if not is_email_configured():
        return 0

    now = datetime.now(timezone.utc)
    from services.notification_dispatch import reserve_dispatch_once, mark_dispatch_status
    plan_prices = {
        "basic": f"${get_plan_amount('basic', 'monthly'):.2f}/mo",
        "premium": f"${get_plan_amount('premium', 'monthly'):.2f}/mo",
    }
    total_sent = 0
    touch_points = [(7, "reminder_7d_sent"), (3, "reminder_3d_sent"), (1, "reminder_1d_sent")]

    for days, flag in touch_points:
        window_start = now
        window_end = now + timedelta(days=days)
        cursor = db.users.find(
            {
                "subscription_plan": {"$in": ["basic", "premium"]},
                "subscription_status": "active",
                "subscription_end_date": {"$gte": window_start, "$lte": window_end},
                flag: {"$ne": True},
            },
            {"_id": 0, "user_id": 1, "email": 1, "name": 1, "subscription_plan": 1, "subscription_end_date": 1},
        )
        async for user_doc in cursor:
            if _is_payment_exempt(user_doc.get("email", "")):
                continue
            email = user_doc.get("email", "")
            name = user_doc.get("name", "User")
            plan = user_doc.get("subscription_plan", "basic")
            end_date = user_doc.get("subscription_end_date")
            if not email or not end_date:
                continue
            dedupe_key = ""
            renewal_date = end_date.strftime("%B %d, %Y") if hasattr(end_date, "strftime") else str(end_date)[:10]
            amount = plan_prices.get(plan, f"${get_plan_amount('basic', 'monthly'):.2f}/mo")
            try:
                from utils.email_service import send_catalog_template
                email_normalized = str(email).strip().lower()
                dedupe_key = f"renewal_reminder:{str(user_doc.get('user_id') or '')}:{days}:{email_normalized}:{renewal_date}"
                reserved = await reserve_dispatch_once(
                    dedupe_key=dedupe_key,
                    event_type="renewal_reminder",
                    channel="email",
                    recipient=email_normalized,
                    payload={"days": days, "plan": plan, "renewal_date": renewal_date},
                )
                if not reserved:
                    continue

                result = await send_catalog_template(
                    email,
                    "renewal_reminder",
                    name,
                    user_name=name,
                    plan_name=plan.capitalize(),
                    renewal_date=renewal_date,
                    amount=amount,
                    dedupe_key=dedupe_key,
                )
                if result.get("success"):
                    await mark_dispatch_status(
                        dedupe_key=dedupe_key,
                        status="sent",
                        extra={"sent_at": now.isoformat(), "flow": "subscription_renewal_multi_touch"},
                    )
                    await db.users.update_one(
                        {"user_id": user_doc["user_id"]},
                        {"$set": {flag: True, f"{flag}_date": now, "expiry_reminder_sent": True}},
                    )
                    total_sent += 1

                    urgency_titles = {7: "Subscription Renewing Soon", 3: "Subscription Expiring!", 1: "Last Day!"}
                    await db.notifications.insert_one({
                        "id": f"notif_sub_{days}d_{user_doc['user_id'][:8]}_{now.strftime('%Y%m%d')}",
                        "user_id": user_doc["user_id"],
                        "type": f"subscription_expiry_{days}d",
                        "title": urgency_titles.get(days, "Subscription Reminder"),
                        "message": f"Your {plan.capitalize()} plan expires in {days} day{'s' if days != 1 else ''}. Renew now to keep access.",
                        "read": False,
                        "action_url": "/subscription/plans",
                        "created_at": now.isoformat(),
                    })
                else:
                    await mark_dispatch_status(
                        dedupe_key=dedupe_key,
                        status="failed",
                        extra={"error": str(result.get("error") or "send_failed")[:300]},
                    )
            except Exception as e:
                try:
                    await mark_dispatch_status(
                        dedupe_key=dedupe_key,
                        status="failed",
                        extra={"error": str(e)[:300]},
                    )
                except Exception:
                    pass
                logger.warning(f"Expiry reminder error for {email}: {e}")

    if total_sent > 0:
        logger.info(f"Multi-touch reminders: {total_sent} emails sent")
    return total_sent


async def retry_failed_payments():
    """Check for failed payment transactions and mark for retry."""
    now = datetime.now(timezone.utc)
    failed_cursor = db.payment_transactions.find(
        {
            "payment_status": {"$in": ["failed", "expired", "cancelled"]},
            "retry_count": {"$lt": 3},
            "created_at": {"$gte": (now - timedelta(days=3)).isoformat()},
        },
        {"_id": 0},
    )
    retried = 0
    async for tx in failed_cursor:
        retry_count = tx.get("retry_count", 0) + 1
        await db.payment_transactions.update_one(
            {"session_id": tx["session_id"]},
            {"$set": {"retry_count": retry_count, "last_retry_at": now.isoformat(), "payment_status": "retry_pending"}},
        )
        await db.notifications.insert_one({
            "id": f"notif_{now.strftime('%Y%m%d%H%M%S')}_{tx.get('user_id', '')[:8]}",
            "user_id": tx.get("user_id", ""),
            "type": "payment_retry",
            "title": "Payment Retry",
            "message": f"Retrying your payment for the {tx.get('plan_id', 'Basic')} plan (attempt {retry_count}/3).",
            "read": False,
            "created_at": now.isoformat(),
        })
        retried += 1
    if retried > 0:
        logger.info(f"Payment retry: {retried} transactions queued for retry")
    return retried


async def scheduled_subscription_maintenance():
    """Combined scheduled job: expire + multi-touch reminders + payment retry."""
    expired = await check_and_expire_subscriptions()
    reminded = await send_expiry_reminders_multi_touch()
    retried = await retry_failed_payments()
    logger.info(f"Subscription maintenance: {expired} expired, {reminded} reminded, {retried} retried")
