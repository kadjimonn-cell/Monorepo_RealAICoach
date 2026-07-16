"""Single source of truth for publicly accessible API endpoints.

This module is intentionally consumed by both middleware-level auth gating
and access-control policy logic to avoid whitelist drift.
"""

from __future__ import annotations

import re


PUBLIC_API_PREFIXES: tuple[str, ...] = (
    # Infrastructure
    "/api/health", "/api/system/health",
    # Multi-platform client bootstrap handshake (no PII, no secrets)
    "/api/client/bootstrap",
    "/api/system/instance-marker",
    "/api/hiring/v2/health",
    # Platform control public state/countdown
    "/api/platform-control/public/",
    # Config & feature flags (read-only, no sensitive data)
    "/api/config/global", "/api/config/boot-policy", "/api/config/boot-policy/telemetry", "/api/config/v2-compliance/runtime", "/api/features/registry",
    # Global Platform State (public read models)
    "/api/gps/state", "/api/gps/summary", "/api/gps/events", "/api/gps/consistency/check", "/api/gps/health",
    "/api/gps/faq/telemetry/",
    "/api/system/vanity-metrics", "/api/system/live-metrics",
    # Static assets
    "/api/static/", "/api/robots.txt", "/api/sitemap.xml",
    # Auth flows (login, register, password reset, OTP, SSO)
    "/api/auth/login", "/api/auth/register",
    "/api/auth/password/reset", "/api/auth/verify",
    "/api/auth/otp/", "/api/auth/2fa/verify",
    "/api/auth/magic-link/", "/api/auth/qr/",
    "/api/auth/google/", "/api/auth/microsoft/", "/api/auth/apple/",
    "/api/auth/sso-config", "/api/auth/lookup",
    "/api/auth/action-otp/verify",
    # Passkey/biometric login flow (pre-login, user not yet authenticated)
    "/api/auth/biometric/has-passkey",
    "/api/auth/biometric/webauthn-auth-options",
    "/api/auth/biometric/webauthn-auth-complete",
    "/api/auth/biometric/verify-pin",
    "/api/auth/me", "/api/auth/renew-session",
    "/api/auth/session-bootstrap-telemetry",
    "/api/auth/track-route",
    "/api/oauth/",
    # Public content pages
    "/api/tos/current", "/api/contact/submit",
    "/api/newsletter/subscribe", "/api/newsletter/unsubscribe",
    "/api/newsletter/preferences/cadence",
    "/api/newsletter/admin/dispatch-due-now",
    "/api/careers/", "/api/blog/",
    "/api/jobs/public", "/api/jobs/search",
    # i18n auto-translate and locale support
    "/api/i18n/auto-translate",
    "/api/i18n/language-guidance",
    "/api/i18n/supported-languages",
    "/api/i18n/fallback-hit",
    "/api/i18n/locales",
    "/api/i18n/languages",
    # Welcome-page social-proof (no PII, just counts)
    "/api/public/",
    # GDPR self-service (email-verified flow, no session)
    "/api/gdpr/request", "/api/gdpr/verify", "/api/gdpr/execute", "/api/gdpr/download",
    # Certificate verification (public by design)
    "/api/ai-learn/certificates/verify/",
    "/api/travel-visa/certificate/verify/",
    # FPS match card — public read-only share surface (no PII, mirrors certificate verifier)
    "/api/games-station/match-card/",
    "/api/ai-learn/course-cover/",
    # Webhooks (validated by their own signature checks)
    "/api/webhook/", "/api/resend-webhooks/", "/api/webhooks/",
    "/api/payments/fedapay/webhook", "/api/payments/apple/webhook",
    "/api/iap/apple/", "/api/iap/google/",
    # Email tracking pixels & click redirects
    "/api/r/", "/api/ab-testing/track/", "/api/track/",
    "/api/email-notifications/track/",
    # Payments public
    "/api/payments/currencies",
    "/api/fedapay/callback",
    "/api/subscriptions/plans",  # canonical user/public plans read endpoint
    # Telemetry & vitals (rate-limited separately)
    "/api/vitals/", "/api/platform-shell-health/",
    # Admin telemetry endpoints used by non-admin user flows
    "/api/admin/session-replay/record",
    "/api/admin/session-replay/end",
    "/api/admin/live-activity/log-event",
    "/api/admin/autonomous-engine/feedback/collect",
    "/api/admin/autonomous-engine/certificate/verify/",
    "/api/admin/uiem/log",
    "/api/admin/v7-templates/log",
    # Platform employee invitation accept flow (public by design)
    "/api/admin/employees/invitations/verify",
    "/api/admin/employees/invitations/accept",
    "/api/admin/employees/invitations/decline",
    # Prompt experiments (A/B test variant assignment)
    "/api/prompt-experiment/",
    # Public visitor conversion telemetry for Welcome/About CTA surfaces
    "/api/subscription-conversion/",
    # Status page (public)
    "/api/status/",
    # Changelog (public)
    "/api/changelog/",
    # Pricing/FAQ (public content)
    "/api/pricing", "/api/faq", "/api/support/faq", "/api/support/faq/smart-search",
    # Public support email intake + AI drafting for /contact page
    "/api/support/email",
    "/api/support/email/insights",
    "/api/support/email/assist",
    "/api/support/email/submit",
    "/api/support/nova/health",
    # Share links (public by design)
    "/api/share/",
    # CSAT public submission
    "/api/csat/submit",
    # GTEC-hardening: public-facing telemetry & read-only data relays
    "/api/auth-compliance/route-block",
    "/api/data/crypto",
    "/api/data/weather",
    "/api/data/finance",
    # Public media
    "/api/media/",
    "/api/health-guide/",
    "/api/fitness-planner/",
    "/api/real-estate/",
    # Learning Coach guest-safe APIs (owner namespace isolated via auth:/guest: prefixes)
    "/api/learning-coach/",
    # School Tutor guest-safe APIs (owner namespace isolated via auth:/guest: prefixes)
    "/api/school/",
    # Mental Wellness guest-safe APIs (owner namespace isolated via auth:/guest: prefixes)
    "/api/wellness/",
    "/api/health-wellness/",
    # AI Services guest-safe APIs (all use auth-based owner resolution)
    "/api/ai-chat",
    "/api/healthhalo/",
    "/api/finwise/",
    "/api/smartbuy/",
    "/api/homemate/",
    "/api/autogenie/",
    "/api/disasterguard/",
    "/api/assetpilot/",
    "/api/timesaver/",
    "/api/travelpal/",
    "/api/globecoach/",
    # Workflow Builder guest-safe APIs (owner namespace isolated via fallback_user_id)
    "/api/workflows/",
    "/api/workflows",  # Base path for POST /api/workflows
    # Business Ops Copilot guest-safe APIs (route-level auth via fallback_user_id)
    "/api/ai-enterprise/",
    # Guest-safe feature studio APIs — each router enforces route-level auth
    # (session cookie or fallback_user_id) and returns 401 without credentials.
    "/api/ai-photo-studio/",
    "/api/ai-speech-studio/",
    "/api/bill-generator/",
    "/api/decision-coach/",
    "/api/mobility-assistant/",
    "/api/money-strategy-hub/",
    "/api/personal-assistant/",
    "/api/relationship-coach/",
    "/api/research-navigator/",
    "/api/smart-shopping-advisor/",
    "/api/travel-planner-pro/",
    "/api/video-studio/",
    "/api/writing-studio/",
)


PUBLIC_API_EXACT: frozenset[str] = frozenset(
    {
        "/api/health",
        "/api/hiring/v2/health",
        "/api/system/instance-marker",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/sso-config",
        "/api/auth/lookup",
        "/api/auth/logout-banner-telemetry",
        "/api/tos/current",
        "/api/payments/config",
        "/api/payments/currencies",
        "/api/payments/paypal/webhook",
        "/api/fedapay/callback",
        "/api/iap/products",
        "/api/errors/client",
        "/api/features/gallery-data",
        "/api/geo/detect",
        "/api/gtec/directive/state",
        "/api/sports/v2/secure-stream",
        "/api/subscriptions/plans",
    }
)


def is_public_api_path(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path in PUBLIC_API_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES)


def build_public_regex_patterns() -> list[str]:
    """Build regex patterns for access-control engine from canonical contract."""
    patterns: list[str] = [rf"^{re.escape(p)}$" for p in sorted(PUBLIC_API_EXACT)]
    patterns.extend([rf"^{re.escape(prefix)}" for prefix in PUBLIC_API_PREFIXES])
    # De-duplicate while preserving order
    dedup: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        if pattern in seen:
            continue
        seen.add(pattern)
        dedup.append(pattern)
    return dedup
