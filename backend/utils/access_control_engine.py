"""Unified access control engine for plans, RBAC, and route authorization."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from utils.public_api_contract import build_public_regex_patterns


PLAN_LEVEL: dict[str, int] = {"free": 0, "basic": 1, "premium": 2}

SUBSCRIPTION_ACCESS_PROFILE: dict[str, str] = {
    "free": "limited",
    "basic": "almost_unlimited",
    "premium": "full_unlimited",
}

# ── PLATFORM SUBSCRIPTION ACCESS CONTROL POLICY ──
# Free    → Limited access to ALL 37 canonical features (try before upgrade)
# Basic   → Almost unlimited
# Premium → Full unlimited
# Auto-enforced via the AI-driven entitlement system (middleware metering).
SUBSCRIPTION_ACCESS_POLICY_VERSION = "2026-06.v3.free-limited-37"

# Default daily mutating-action quota per feature. Reads are always open so
# users can explore every feature before upgrading.
FEATURE_DEFAULT_DAILY_ACTIONS: dict[str, int] = {"free": 5, "basic": 200, "premium": -1}

# Canonical 37-feature meter map. `free`/`basic` override the defaults;
# `self_enforced` features keep their own tuned in-route quotas and are
# exempt from the generic middleware meter. Order matters (first match wins).
CANONICAL_FEATURE_METERS: list[dict[str, Any]] = [
    {"feature_key": "smart-writing-studio", "feature_number": 1, "prefixes": ["/api/writing-studio/"], "self_enforced": True},
    {"feature_key": "personal-ai-assistant", "feature_number": 2, "prefixes": ["/api/personal-assistant/"], "self_enforced": True},
    {"feature_key": "deep-research-navigator", "feature_number": 3, "prefixes": ["/api/research-navigator/", "/api/ai-search"], "self_enforced": True},
    {"feature_key": "workflow-builder", "feature_number": 4, "prefixes": ["/api/workflows/"], "self_enforced": True},
    {"feature_key": "decision-coach", "feature_number": 5, "prefixes": ["/api/decision-coach/"], "self_enforced": True},
    {"feature_key": "learning-coach", "feature_number": 6, "prefixes": ["/api/learning-coach/", "/api/school/"]},
    {"feature_key": "health-guide", "feature_number": 7, "prefixes": ["/api/health-guide/"]},
    {"feature_key": "fitness-planner-pro", "feature_number": 8, "prefixes": ["/api/fitness-planner/", "/api/fitness/"]},
    {"feature_key": "money-strategy-hub", "feature_number": 9, "prefixes": ["/api/money-strategy-hub/"], "self_enforced": True},
    {"feature_key": "smart-shopping-advisor", "feature_number": 10, "prefixes": ["/api/smart-shopping-advisor/"], "self_enforced": True},
    {"feature_key": "travel-planner-pro", "feature_number": 11, "prefixes": ["/api/travel-planner-pro/"], "self_enforced": True},
    {"feature_key": "relationship-coach", "feature_number": 12, "prefixes": ["/api/relationship-coach/", "/api/dating/"], "self_enforced": True},
    {"feature_key": "mobility-assistant", "feature_number": 13, "prefixes": ["/api/mobility-assistant/", "/api/cars/"], "self_enforced": True},
    {"feature_key": "property-decision-advisor", "feature_number": 14, "prefixes": ["/api/real-estate/"]},
    {"feature_key": "video-creator-studio", "feature_number": 15, "prefixes": ["/api/video-studio/"]},
    {"feature_key": "image-design-studio", "feature_number": 16, "prefixes": ["/api/ai-photo-studio/", "/api/ai-image"]},
    {"feature_key": "voice-studio", "feature_number": 17, "prefixes": ["/api/ai-speech-studio/"], "self_enforced": True},
    {"feature_key": "business-operations-copilot", "feature_number": 18, "prefixes": ["/api/ai-enterprise/"]},
    {"feature_key": "bill-generator", "feature_number": 19, "prefixes": ["/api/bill-generator/"], "self_enforced": True},
    {"feature_key": "lexicon-intelligence-hub", "feature_number": 20, "prefixes": ["/api/word-forge/"], "self_enforced": True},
    {"feature_key": "watch-videos", "feature_number": 21, "prefixes": ["/api/videos/"], "self_enforced": True},
    {"feature_key": "fps-game", "feature_number": 22, "prefixes": ["/api/games-station/"], "free": 25},
    {"feature_key": "daily-meditation", "feature_number": 25, "prefixes": ["/api/travel-visa/daily-meditation/"], "free": 10},
    {"feature_key": "travel-visa", "feature_number": 23, "prefixes": ["/api/travel-visa/"]},
    {"feature_key": "learning-hub", "feature_number": 24, "prefixes": ["/api/ai-learn/"]},
    {"feature_key": "job-portal", "feature_number": 26, "prefixes": ["/api/job-search/", "/api/jobs/", "/api/hiring/v2/"], "free": 10},
    {"feature_key": "id-checker", "feature_number": 27, "prefixes": ["/api/id-checker/", "/api/id-verification/"], "free": 10},
    {"feature_key": "audio-studio", "feature_number": 28, "prefixes": ["/api/audio-studio/v2/"], "free": 20},
    {"feature_key": "my-podcasts", "feature_number": 29, "prefixes": ["/api/podcasts/v2/"], "free": 20},
    {"feature_key": "sports", "feature_number": 30, "prefixes": ["/api/sports/v2/"], "free": 20},
    {"feature_key": "ai-coaching-team", "feature_number": 31, "prefixes": ["/api/ai-coaching-team/"], "self_enforced": True},
    {"feature_key": "daily-briefing", "feature_number": 32, "prefixes": ["/api/ai-briefing/"]},
    {"feature_key": "library", "feature_number": 33, "prefixes": ["/api/content/library", "/api/content/bookmarks", "/api/content/recent", "/api/content/user-saved"]},
    {"feature_key": "my-agenda", "feature_number": 34, "prefixes": ["/api/calendar/"], "free": 10},
    {"feature_key": "integrations", "feature_number": 35, "prefixes": ["/api/integrations/", "/api/data/crypto", "/api/data/weather", "/api/data/finance"], "free": 10},
    {"feature_key": "referral-program", "feature_number": 36, "prefixes": ["/api/referrals/"], "self_enforced": True},
    {"feature_key": "flappy-bird", "feature_number": 37, "prefixes": ["/api/flappy-bird/"], "free": 25},
]


def resolve_feature_meter(path: str) -> dict[str, Any] | None:
    for meter in CANONICAL_FEATURE_METERS:
        if any(path.startswith(prefix) for prefix in meter["prefixes"]):
            return meter
    return None


# Frontend route prefixes per canonical feature (served via canonical_feature_policy
# so the quota pill can map the current page to its feature meter).
CANONICAL_FEATURE_UI_ROUTES: dict[str, list[str]] = {
    "smart-writing-studio": ["/features/ai-writer"],
    "personal-ai-assistant": ["/features/assistant"],
    "deep-research-navigator": ["/features/ai-search"],
    "workflow-builder": ["/features/ai-automations"],
    "decision-coach": ["/features/decision-coach", "/features/ai-cognitive"],
    "learning-coach": ["/features/school-tutor"],
    "health-guide": ["/features/medimate", "/features/health-dashboard"],
    "fitness-planner-pro": ["/features/fitness"],
    "money-strategy-hub": ["/features/pennypilot"],
    "smart-shopping-advisor": ["/features/smartbuy"],
    "travel-planner-pro": ["/features/travelpal"],
    "relationship-coach": ["/features/ai-found-love"],
    "mobility-assistant": ["/features/smart-cars"],
    "property-decision-advisor": ["/features/buy-smart-home"],
    "video-creator-studio": ["/features/ai-video"],
    "image-design-studio": ["/features/ai-photo"],
    "voice-studio": ["/features/ai-speech"],
    "business-operations-copilot": ["/features/ai-enterprise"],
    "bill-generator": ["/features/bill-generator"],
    "lexicon-intelligence-hub": ["/features/lexicon-intelligence"],
    "watch-videos": ["/features/watch-videos"],
    "fps-game": ["/features/fps-game"],
    "daily-meditation": ["/features/daily-meditation"],
    "travel-visa": ["/features/travel-visa"],
    "learning-hub": ["/ai-learning-hub"],
    "job-portal": ["/job-search"],
    "id-checker": ["/id-checker", "/id-verification"],
    "audio-studio": ["/features/audio-studio"],
    "my-podcasts": ["/features/my-podcasts"],
    "sports": ["/features/sports"],
    "ai-coaching-team": ["/ai-coaching-team"],
    "daily-briefing": ["/ai-briefing"],
    "library": ["/content-library"],
    "my-agenda": ["/book-meeting"],
    "integrations": ["/integrations"],
    "referral-program": ["/referrals"],
    "flappy-bird": ["/features/flappy-bird"],
}


def get_feature_daily_action_limit(meter: dict[str, Any], plan: str) -> int:
    plan = normalize_plan(plan)
    if plan == "premium":
        return -1
    if meter.get("self_enforced"):
        return -1
    return int(meter.get(plan, FEATURE_DEFAULT_DAILY_ACTIONS[plan]))


def build_canonical_feature_policy(plan: str) -> dict[str, Any]:
    plan = normalize_plan(plan)
    policy: dict[str, Any] = {}
    for meter in CANONICAL_FEATURE_METERS:
        policy[meter["feature_key"]] = {
            "feature_number": meter["feature_number"],
            "daily_action_limit": get_feature_daily_action_limit(meter, plan),
            "self_enforced": bool(meter.get("self_enforced")),
            "read_access": "unlimited",
            "ui_routes": CANONICAL_FEATURE_UI_ROUTES.get(meter["feature_key"], []),
        }
    return policy

# Premium-only capabilities intentionally retained when Basic is "almost unlimited".
PREMIUM_EXCLUSIVE_FEATURE_KEYS: set[str] = {
    "vc_engine",
    "export_history",
    "ai_phone_call",
    "dev_advanced_debug",
    "dev_multi_env",
    "dev_team_collab",
    "dev_perf_analytics",
    "dev_advanced_export",
}


# Public endpoints — sourced from the canonical public API contract.
PUBLIC_PATTERNS: list[str] = build_public_regex_patterns()

# Authenticated endpoints allowed for free plan
FREE_PATTERNS: list[str] = [
    r"^/api/auth/",
    r"^/api/access-control/",
    r"^/api/notifications",
    r"^/api/weekly-digest/",
    r"^/api/ai-access/status",
    r"^/api/ai-access/tier-comparison",
    r"^/api/payments/",
    r"^/api/content/document",
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
    r"^/api/ai-search",
    r"^/api/school/",
    r"^/api/fitness/",
    r"^/api/dating/",
    r"^/api/weather",
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
    r"^/api/writing-studio/",
    r"^/api/personal-assistant/",
    r"^/api/research-navigator/",
    r"^/api/money-strategy-hub/",
    r"^/api/smart-shopping-advisor/",
    r"^/api/travel-planner-pro/",
    r"^/api/video-studio/",
    r"^/api/ai-photo-studio/",
    r"^/api/ai-speech-studio/",
    r"^/api/ai-enterprise/",
    r"^/api/relationship-coach/",
    r"^/api/decision-coach/",
    r"^/api/mobility-assistant/",
    r"^/api/videos/",
    r"^/api/audio-studio/v2/(?!admin/)",
    r"^/api/podcasts/v2/(?!admin/)",
    r"^/api/sports/v2/(?!admin/)",
    r"^/api/ai-briefing/",
    r"^/api/calendar/",
    r"^/api/content/library",
    r"^/api/content/bookmarks",
    r"^/api/content/recent",
    r"^/api/content/user-saved",
    r"^/api/integrations/",
    r"^/api/data/(crypto|weather|finance)",
    r"^/api/workflows/",
    r"^/api/learning-coach/",
    r"^/api/health-guide/",
    r"^/api/fitness-planner/",
    r"^/api/games-station/",
    r"^/api/flappy-bird/",
    r"^/api/travel-visa/",
    r"^/api/matchday-reminders/",
    r"^/api/jobs/",
    r"^/api/job-search/",
    r"^/api/hiring/v2/",
    r"^/api/employers/",
    r"^/api/employers/(apply|upload-document|my-application|my-permissions|permissions|messages/|documents/|resubmit-info|reverify-status|reverify)(/|$)",
]

# PLATFORM SUBSCRIPTION ACCESS CONTROL POLICY (2026-06.v3):
# No canonical feature is hard-blocked at Basic anymore. Free users get
# limited access to ALL 37 features; limits are enforced by the daily
# action meter in the enforcement middleware, not by 403 route blocks.
BASIC_PATTERNS: list[str] = []

# Premium-gated endpoints
PREMIUM_PATTERNS: list[str] = [
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


# Enterprise role model (supports predefined + custom)
PLATFORM_EMPLOYEE_ROLES: list[str] = [
    "Support",
    "BillingOps",
    "UserManager",
    "ComplianceAuditor",
    "SuperEmployee",
    "Custom",
]

PLATFORM_EMPLOYEE_PERMISSIONS: list[str] = [
    "employee.manage_users",
    "employee.manage_subscriptions",
    "employee.manage_access",
    "employee.view_audit_logs",
    "employee.manage_operations",
    "employee.view_analytics",
    "employee.manage_billing",
    "employee.handle_support",
]

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Official platform employee roles (canonical)
    "Support": ["employee.handle_support", "employee.view_audit_logs"],
    "BillingOps": ["employee.manage_subscriptions", "employee.manage_billing", "employee.view_analytics"],
    "UserManager": ["employee.manage_users", "employee.manage_access", "employee.view_audit_logs"],
    "ComplianceAuditor": ["employee.view_audit_logs", "employee.view_analytics"],
    "SuperEmployee": PLATFORM_EMPLOYEE_PERMISSIONS[:],
    "Custom": [],
    # Legacy roles used by Team Management UI — aligned so their role-specific
    # landing pages (see `platformRoleLanding.ts`) aren't blocked by UI_ROUTE_POLICIES.
    "Manager": ["employee.manage_access", "employee.manage_users", "employee.view_audit_logs", "employee.view_analytics"],
    "Support Team": ["employee.handle_support", "employee.view_audit_logs"],
    "Developer": ["employee.manage_operations", "employee.view_analytics"],
    "Engineer": ["employee.manage_operations", "employee.view_analytics"],
    "Finance Advisor": ["employee.manage_subscriptions", "employee.manage_billing", "employee.view_analytics"],
    "Designer": [],
    "QA": ["employee.view_audit_logs"],
    "Marketing": ["employee.view_analytics"],
    "Operations": ["employee.manage_operations", "employee.view_analytics"],
}


# Admin API subspaces that can be delegated to employees by permission.
EMPLOYEE_PERMISSION_PATTERNS: dict[str, list[str]] = {
    # NOTE: Order matters! More specific patterns should come before broader ones.
    # view_analytics patterns for /api/admin/employees/* analytics endpoints must be checked first
    "employee.view_analytics": [
        r"^/api/admin/employees/ai-insights",
        r"^/api/admin/employees/activity-stream",
        r"^/api/admin/subscription-analytics",
        r"^/api/admin/payment-analytics",
        r"^/api/admin/access-control/observability",
        r"^/api/admin/executive-dashboard",
        r"^/api/admin/revenue",
        r"^/api/admin/analytics",
        r"^/api/admin/executive",
    ],
    "employee.view_audit_logs": [
        r"^/api/admin/employees/audit-log",
        r"^/api/admin/access-control/audit",
        r"^/api/admin/activity-log",
    ],
    "employee.manage_users": [
        r"^/api/admin/executive/user-management",
        r"^/api/admin/users",
        r"^/api/admin/team",
    ],
    "employee.manage_access": [
        r"^/api/admin/employees$",
        r"^/api/admin/employees/",
        r"^/api/admin/employees/roles-config",
        r"^/api/admin/employees/access-requests",
        r"^/api/admin/access-control/employee-access",
        r"^/api/admin/access-control/policy-console/bootstrap",
        r"^/api/admin/access-control/policy-console/role-template/",
    ],
    "employee.manage_subscriptions": [
        r"^/api/admin/subscriptions",
        r"^/api/admin/subscription",
        r"^/api/admin/payment-analytics/subscriptions",
        r"^/api/admin/access-control/subscription-transition",
        r"^/api/admin/access-control/policy-console/pending-transitions",
        r"^/api/admin/mobile-money-dashboard",
        r"^/api/admin/subscription-dashboard",
        r"^/api/subscriptions/lifecycle/reconcile",
    ],
    "employee.manage_operations": [
        r"^/api/admin/system",
        r"^/api/admin/platform",
        r"^/api/admin/platform-health",
        r"^/api/admin/automation",
        r"^/api/admin/infra",
        r"^/api/admin/waf",
        r"^/api/admin/self-repair",
        r"^/api/admin/session-replay",
        r"^/api/admin/live-activity",
        r"^/api/admin/enterprise",
        r"^/api/admin/cdn",
        r"^/api/admin/notification-rules",
    ],
    "employee.manage_billing": [
        r"^/api/admin/payments-tax",
        r"^/api/admin/payment-analytics",
        r"^/api/admin/subscriptions",
        r"^/api/admin/payments/fedapay-policy",
    ],
    "employee.handle_support": [
        r"^/api/admin/messages",
        r"^/api/admin/support",
    ],
}


FEATURE_ACCESS: dict[str, dict[str, Any]] = {
    "platform_wallet": {"free": True, "basic": True, "premium": True},
    "platform_transfers": {"free": 3, "basic": 50, "premium": -1},
    "platform_loans": {"free": False, "basic": True, "premium": True},
    "platform_virtual_cards": {"free": 0, "basic": 1, "premium": 5},
    "platform_savings_goals": {"free": 1, "basic": 5, "premium": -1},
    "creator_studio": {"free": False, "basic": True, "premium": True},
    "creator_analytics": {"free": False, "basic": True, "premium": True},
    "ugc_studio": {"free": False, "basic": True, "premium": True},
    "live_streaming_host": {"free": False, "basic": True, "premium": True},
    "live_streaming_watch": {"free": True, "basic": True, "premium": True},
    "stock_exchange": {"free": False, "basic": True, "premium": True},
    "vc_engine": {"free": False, "basic": False, "premium": True},
    "dev_workspace_access": {"free": "limited", "basic": "unlimited", "premium": "unlimited_pro"},
    "dev_ai_requests_daily": {"free": 20, "basic": -1, "premium": -1},
    "dev_max_projects": {"free": 2, "basic": -1, "premium": -1},
    "dev_max_builds": {"free": 1, "basic": -1, "premium": -1},
    "dev_api_keys": {"free": False, "basic": True, "premium": True},
    "dev_advanced_debug": {"free": False, "basic": False, "premium": True},
    "dev_multi_env": {"free": False, "basic": False, "premium": True},
    "dev_team_collab": {"free": False, "basic": False, "premium": True},
    "dev_perf_analytics": {"free": False, "basic": False, "premium": True},
    "dev_advanced_export": {"free": False, "basic": False, "premium": True},
    "ai_conversations_daily": {"free": 3, "basic": 10, "premium": -1},
    "scenario_access": {
        "free": ["beginner"],
        "basic": ["beginner", "intermediate"],
        "premium": ["beginner", "intermediate", "advanced"],
    },
    "analytics_access": {"free": False, "basic": True, "premium": True},
    "export_history": {"free": False, "basic": False, "premium": True},
    "ai_phone_call": {"free": False, "basic": False, "premium": True},
    "content_studio_access": {"free": False, "basic": True, "premium": True},
    "coaching_team_daily_messages": {"free": 5, "basic": 50, "premium": -1},
    "coaching_team_all_coaches": {"free": False, "basic": True, "premium": True},
    "word_forge_generate_word_daily": {"free": 4, "basic": 180, "premium": -1},
    "word_forge_quiz_attempt_daily": {"free": 12, "basic": 500, "premium": -1},
    "word_forge_save_word_daily": {"free": 24, "basic": 1000, "premium": -1},
    "word_forge_review_complete_daily": {"free": 15, "basic": 700, "premium": -1},
    "word_forge_usage_coach_daily": {"free": 6, "basic": 250, "premium": -1},
    "word_forge_business_brief_daily": {"free": 5, "basic": 220, "premium": -1},
    "word_forge_weekly_challenge_submit_daily": {"free": 2, "basic": 80, "premium": -1},
    "watch_videos_daily_watch_cap": {"free": 5, "basic": 120, "premium": -1},
}


# ── UNIFIED UI ROUTE TIER CONFIG ──
# Single source of truth for frontend route gating. Served to the client via
# /api/access-control/session (`ui_tier_routes`). The frontend keeps a static
# copy only as an offline fallback.
UI_TIER_ROUTES: dict[str, list[str]] = {
    # POLICY 2026-06.v3: Free users can OPEN all 37 canonical feature routes.
    # Limits are enforced in-feature via the daily action meter, never by
    # locking the page. Non-canonical premium surfaces stay gated below.
    "free_feature_prefixes": [
        "/features/ai-writer",
        "/features/assistant",
        "/features/ai-search",
        "/features/ai-automations",
        "/features/ai-cognitive",
        "/features/decision-coach",
        "/features/school-tutor",
        "/features/medimate",
        "/features/health-dashboard",
        "/features/fitness",
        "/features/pennypilot",
        "/features/smartbuy",
        "/features/travelpal",
        "/features/ai-found-love",
        "/features/smart-cars",
        "/features/buy-smart-home",
        "/features/ai-video",
        "/features/ai-photo",
        "/features/ai-speech",
        "/features/ai-enterprise",
        "/features/bill-generator",
        "/features/lexicon-intelligence",
        "/features/watch-videos",
        "/features/fps-game",
        "/features/travel-visa",
        "/features/daily-meditation",
        "/features/audio-studio",
        "/features/my-podcasts",
        "/features/sports",
        "/features/flappy-bird",
        "/features/ai-chatbot",
    ],
    # Any /features/* route requires Basic unless in free_feature_prefixes
    "basic_ui_prefixes": ["/features"],
    # Premium-only UI surfaces
    "premium_ui_prefixes": ["/content-studio", "/workspace"],
    # No Basic-gated canonical feature routes remain under the v3 policy.
    "basic_authenticated_ui_prefixes": [],
    # Non-canonical high-value surfaces still blocked for the limited profile
    "free_limited_ui_prefixes": [
        "/content-studio",
        "/workspace",
        "/features/content-studio",
        "/features/analytics-reports",
        "/mini-apps/ai-accounting",
        "/mini-apps/creator-exchange",
        "/subscription/mobile-money",
        "/job-platform-employer",
        "/certificate-operations",
        "/admin/email-delivery-ledger",
        "/job-platform-admin",
    ],
}


UI_ROUTE_POLICIES: list[dict[str, str]] = [
    {"prefix": "/policy-console", "permission": "employee.manage_access"},
    {"prefix": "/team-management", "permission": "employee.manage_access"},
    {"prefix": "/admin-activity-log", "permission": "employee.view_audit_logs"},
    {"prefix": "/admin-system", "permission": "employee.manage_operations"},
    {"prefix": "/performance-observability", "permission": "employee.manage_operations"},
    {"prefix": "/route-health-report", "permission": "employee.manage_operations"},
    {"prefix": "/ai-feature-dashboard", "permission": "employee.view_analytics"},
    {"prefix": "/executive-dashboard", "permission": "employee.manage_operations"},
]


def _match_any(path: str, patterns: list[str]) -> bool:
    return any(re.match(pattern, path) for pattern in patterns)


def normalize_plan(plan: Any) -> str:
    candidate = str(plan or "free").strip().lower()
    if candidate not in PLAN_LEVEL:
        return "free"
    return candidate


def is_admin_flag(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return False


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt_val = value
    elif isinstance(value, str):
        raw = value.replace("Z", "+00:00")
        try:
            dt_val = datetime.fromisoformat(raw)
        except Exception:
            return None
    else:
        return None
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=timezone.utc)
    return dt_val


def build_employee_permissions(user_doc: dict[str, Any] | None) -> list[str]:
    if not user_doc:
        return []
    explicit = set(str(p) for p in (user_doc.get("employee_permissions") or []))
    role = str(user_doc.get("platform_role") or "").strip()
    defaults = set(DEFAULT_ROLE_PERMISSIONS.get(role, []))
    merged = explicit.union(defaults)
    return sorted([p for p in merged if p in PLATFORM_EMPLOYEE_PERMISSIONS])


def get_required_level(path: str) -> int:
    if _match_any(path, PUBLIC_PATTERNS):
        return -1
    if _match_any(path, BASIC_PATTERNS):
        return 1
    if _match_any(path, FREE_PATTERNS):
        return 0
    if _match_any(path, PREMIUM_PATTERNS):
        return 2
    return 1


def compute_effective_plan(user_doc: dict[str, Any] | None) -> str:
    if not user_doc:
        return "free"
    if is_admin_flag(user_doc.get("is_admin")):
        return "premium"

    from utils.preprod_entitlement_lock import is_preprod_lock_active

    if is_preprod_lock_active():
        return "free"

    plan = normalize_plan(user_doc.get("subscription_plan"))
    has_legacy_paid_flags = bool(
        user_doc.get("full_access") is True
        or user_doc.get("subscription_permanent") is True
        or user_doc.get("premium_access") is True
    )

    # Legacy profile fallback: migrate old paid flags into entitlement engine behavior.
    if plan == "free" and has_legacy_paid_flags:
        plan = "premium"

    status = str(user_doc.get("subscription_status") or "active").strip().lower()

    if status not in {"active", "trial", "cancelled", "past_due"}:
        return "free"

    if plan in {"basic", "premium"}:
        if user_doc.get("payment_verified") is not True and not has_legacy_paid_flags:
            return "free"
        end_date = parse_datetime(user_doc.get("subscription_end_date"))
        if end_date and end_date < datetime.now(timezone.utc) and not has_legacy_paid_flags:
            return "free"

    pending = user_doc.get("pending_subscription_transition") or {}
    target_plan = normalize_plan(pending.get("target_plan")) if pending else None
    effective_at = parse_datetime(pending.get("effective_at")) if pending else None
    if target_plan and effective_at and effective_at <= datetime.now(timezone.utc):
        plan = target_plan

    return normalize_plan(plan)


def required_employee_permission(path: str) -> str | None:
    for permission, patterns in EMPLOYEE_PERMISSION_PATTERNS.items():
        if _match_any(path, patterns):
            return permission
    return None


def evaluate_api_access(path: str, method: str, user_doc: dict[str, Any] | None) -> dict[str, Any]:
    required_level = get_required_level(path)
    if required_level == -1:
        return {"allowed": True, "reason": "public", "required_level": -1}

    if not user_doc:
        return {"allowed": True, "reason": "missing_user_context", "required_level": required_level}

    if is_admin_flag(user_doc.get("is_admin")):
        return {"allowed": True, "reason": "admin", "required_level": required_level}

    normalized_path = str(path or "").strip().lower()

    # Global locked protocol hard guard:
    # Any admin analytics/insights surface is STRICT admin-only,
    # never delegated to employee permissions.
    if normalized_path.startswith("/api/admin/") and (
        "analytics" in normalized_path or "insights" in normalized_path
    ):
        return {
            "allowed": False,
            "reason": "admin_required",
            "required_level": required_level,
        }

    if path.startswith("/api/admin/employees") or path.startswith("/api/team-management"):
        return {
            "allowed": False,
            "reason": "admin_required",
            "required_level": required_level,
        }

    if path.startswith("/api/audio-studio/v2/admin/") or path.startswith("/api/podcasts/v2/admin/") or path.startswith("/api/sports/v2/admin/"):
        return {
            "allowed": False,
            "reason": "admin_required",
            "required_level": required_level,
        }

    if path.startswith("/api/admin/access-control"):
        return {
            "allowed": False,
            "reason": "admin_required",
            "required_level": required_level,
        }

    # Admin surface: admin + delegated employee permissions
    if path.startswith("/api/admin/"):
        required_permission = required_employee_permission(path)
        permissions = build_employee_permissions(user_doc)
        if required_permission and required_permission in permissions:
            return {
                "allowed": True,
                "reason": "employee_permission",
                "required_permission": required_permission,
                "required_level": required_level,
            }
        return {
            "allowed": False,
            "reason": "admin_or_employee_permission_required",
            "required_permission": required_permission,
            "required_level": required_level,
        }

    effective_plan = compute_effective_plan(user_doc)
    user_level = PLAN_LEVEL.get(effective_plan, 0)
    if user_level < required_level:
        plan_names = {0: "free", 1: "basic", 2: "premium"}
        return {
            "allowed": False,
            "reason": "subscription_required",
            "required_plan": plan_names.get(required_level, "basic"),
            "current_plan": effective_plan,
            "required_level": required_level,
        }

    return {
        "allowed": True,
        "reason": "plan_ok",
        "effective_plan": effective_plan,
        "required_level": required_level,
    }


def build_feature_entitlements(effective_plan: str) -> dict[str, Any]:
    plan = normalize_plan(effective_plan)
    entitlements: dict[str, Any] = {}

    def _transform_basic_value(feature_name: str, value: Any, premium_value: Any) -> Any:
        # Keep explicit premium-exclusive controls locked.
        if feature_name in PREMIUM_EXCLUSIVE_FEATURE_KEYS:
            return value

        # Basic => almost unlimited for non-premium-exclusive capabilities.
        if isinstance(value, bool):
            return True
        if isinstance(value, (int, float)):
            if value < 0:
                return value
            return -1
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"limited", "restricted", "basic"}:
                return "unlimited"
            return value
        if isinstance(value, list):
            # Expand to premium scope when list-based access levels exist.
            return premium_value if isinstance(premium_value, list) else value
        return value

    def _transform_premium_value(value: Any) -> Any:
        # Premium => full unlimited profile.
        if isinstance(value, bool):
            return True
        if isinstance(value, (int, float)):
            if value < 0:
                return value
            return -1
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"limited", "restricted", "basic", "unlimited"}:
                return "unlimited"
            return value
        return value

    for feature_name, tier_map in FEATURE_ACCESS.items():
        current_value = tier_map.get(plan, tier_map.get("free"))
        premium_value = tier_map.get("premium")

        if plan == "basic":
            current_value = _transform_basic_value(feature_name, current_value, premium_value)
        elif plan == "premium":
            current_value = _transform_premium_value(current_value)

        entitlements[feature_name] = current_value

    entitlements["subscription_access_profile"] = SUBSCRIPTION_ACCESS_PROFILE.get(plan, "limited")
    entitlements["entitlement_engine"] = "ai_driven_entitlements_v2"
    entitlements["subscription_policy_version"] = SUBSCRIPTION_ACCESS_POLICY_VERSION
    entitlements["feature_default_daily_actions"] = dict(FEATURE_DEFAULT_DAILY_ACTIONS)
    entitlements["canonical_feature_policy"] = build_canonical_feature_policy(plan)
    return entitlements


def build_session_entitlements(user_doc: dict[str, Any]) -> dict[str, Any]:
    effective_plan = compute_effective_plan(user_doc)
    permissions = build_employee_permissions(user_doc)
    actor_type = "admin" if is_admin_flag(user_doc.get("is_admin")) else "employee" if user_doc.get("platform_role") else "user"
    access_profile = SUBSCRIPTION_ACCESS_PROFILE.get(effective_plan, "limited")
    return {
        "effective_plan": effective_plan,
        "subscription_access_profile": access_profile,
        "entitlement_engine": "ai_driven_entitlements_v2",
        "subscription_policy_version": SUBSCRIPTION_ACCESS_POLICY_VERSION,
        "actor_type": actor_type,
        "is_admin": is_admin_flag(user_doc.get("is_admin")),
        "platform_role": user_doc.get("platform_role"),
        "employee_permissions": permissions,
        "feature_entitlements": build_feature_entitlements(effective_plan),
        "ui_route_policies": UI_ROUTE_POLICIES,
        "ui_tier_routes": UI_TIER_ROUTES,
    }


async def reconcile_due_transition(db, user_doc: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    pending = user_doc.get("pending_subscription_transition") or {}
    if not pending:
        return user_doc, False
    effective_at = parse_datetime(pending.get("effective_at"))
    if not effective_at or effective_at > datetime.now(timezone.utc):
        return user_doc, False

    action = str(pending.get("action") or "downgrade").strip().lower()
    target_plan = normalize_plan(pending.get("target_plan") or "free")
    now = datetime.now(timezone.utc)

    status = "active"
    if action == "cancel" or target_plan == "free":
        status = "expired"

    set_payload: dict[str, Any] = {
        "subscription_plan": target_plan,
        "subscription_status": status,
        "updated_at": now,
    }
    if target_plan == "free":
        set_payload["subscription_end_date"] = now

    await db.users.update_one(
        {"user_id": user_doc.get("user_id")},
        {
            "$set": set_payload,
            "$unset": {"pending_subscription_transition": ""},
        },
    )
    await db.subscription_lifecycle_audit.insert_one(
        {
            "event_id": f"sla_{now.strftime('%Y%m%d%H%M%S%f')}",
            "user_id": user_doc.get("user_id"),
            "action": "applied_pending_transition",
            "target_plan": target_plan,
            "source_action": action,
            "effective_at": now.isoformat(),
            "created_at": now.isoformat(),
        }
    )

    merged = {**user_doc, **set_payload}
    merged.pop("pending_subscription_transition", None)
    return merged, True
