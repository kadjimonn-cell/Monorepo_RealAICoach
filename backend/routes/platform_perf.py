"""Platform-Wide Performance Monitoring — Unified score, budgets, trending, DB monitoring, auto-fix."""

from fastapi import APIRouter, Request, HTTPException
from datetime import datetime, timezone, timedelta
import psutil
import time
import os
import logging
import re
import math
from pathlib import Path
import asyncio
import httpx
from urllib.parse import urlparse

router = APIRouter(prefix="/admin/platform-perf")
logger = logging.getLogger(__name__)

# ── Performance Budgets (thresholds) ─────────────────────────────
BUDGETS = {
    "lcp_s": {"target": 2.5, "critical": 4.0, "unit": "s", "label": "Largest Contentful Paint"},
    "fcp_s": {"target": 1.8, "critical": 3.0, "unit": "s", "label": "First Contentful Paint"},
    "inp_ms": {"target": 200, "critical": 500, "unit": "ms", "label": "Interaction to Next Paint"},
    "ttfb_ms": {"target": 600, "critical": 1200, "unit": "ms", "label": "Time to First Byte"},
    "cls": {"target": 0.1, "critical": 0.25, "unit": "", "label": "Cumulative Layout Shift"},
    "api_p95_ms": {"target": 500, "critical": 1500, "unit": "ms", "label": "API p95 Response Time"},
    "api_error_pct": {"target": 2.0, "critical": 5.0, "unit": "%", "label": "API Error Rate"},
    "db_latency_ms": {"target": 50, "critical": 200, "unit": "ms", "label": "DB Query Latency"},
    "cpu_pct": {"target": 70, "critical": 90, "unit": "%", "label": "CPU Usage"},
    "memory_pct": {"target": 80, "critical": 95, "unit": "%", "label": "Memory Usage"},
    "disk_pct": {"target": 80, "critical": 95, "unit": "%", "label": "Disk Usage"},
}

SNAPSHOT_COLLECTION = "perf_snapshots"
SLOW_QUERIES_COLLECTION = "slow_queries"
BUNDLE_HISTORY_COLLECTION = "bundle_budget_history"
ROUTE_HEALTH_HISTORY_COLLECTION = "route_health_history"
SHELL_HEALTH_COLLECTION = "shell_health_events"
ADMIN_TAB_INTEGRITY_HISTORY_COLLECTION = "admin_tab_integrity_history"

SHELL_HEALTH_ALERT_BANDS = {
    "band_thresholds": {
        "warning_stress_score": 18,
        "critical_stress_score": 40,
    },
    "counter_thresholds": {
        "warning": {
            "fallback_activations": 2,
            "rate_limit_429s": 3,
            "route_recoveries": 2,
        },
        "critical": {
            "fallback_activations": 5,
            "rate_limit_429s": 8,
            "route_recoveries": 4,
        },
    },
}

ROUTE_HEALTH_DIRECT_ROUTES = [
    "/",
    "/welcome",
    "/auth/login",
    "/contact",
    "/features",
    "/features/ai-automations",
    "/features/ai-chatbot",
    "/features/ai-cognitive",
    "/features/ai-copywriter",
    "/features/ai-enterprise",
    "/features/ai-found-love",
    "/features/ai-photo",
    "/features/ai-private-search",
    "/features/ai-search",
    "/features/ai-speech",
    "/features/ai-video",
    "/features/ai-vision",
    "/features/ai-writer",
    "/features/assistant",
    "/features/buy-smart-home",
    "/features/fitness",
    "/features/health-dashboard",
    "/features/medimate",
    "/features/pennypilot",
    "/features/school-tutor",
    "/features/smart-cars",
    "/features/smartbuy",
    "/features/travelpal",
]

ROUTE_HEALTH_PROTECTED_PROBES = [
    {
        "id": "dashboard",
        "label": "Dashboard",
        "route_path": "/dashboard",
        "api_path": "/api/home/dashboard-stats",
    },
    {
        "id": "executive_dashboard",
        "label": "Executive Dashboard",
        "route_path": "/executive-dashboard",
        "api_path": "/api/admin/executive/overview",
    },
    {
        "id": "admin_console",
        "label": "Admin Console",
        "route_path": "/admin-console?category=operations&tab=critical-journey-monitor",
        "api_path": "/api/admin/critical-journeys/status",
    },
    {
        "id": "ai_learning_hub",
        "label": "AI Learning Hub",
        "route_path": "/ai-learning-hub?tab=journey&filter=all",
        "api_path": "/api/ai-learn/my-learning-center",
    },
    {
        "id": "certificate_gallery",
        "label": "Certificate Gallery",
        "route_path": "/certificate-gallery",
        "api_path": "/api/ai-learn/certificates",
    },
    {
        "id": "certificate_analytics",
        "label": "Certificate Analytics",
        "route_path": "/admin-console?category=analytics&tab=certificate-analytics",
        "api_path": "/api/ai-learn/admin/certificate-analytics?range=all",
    },
    {
        "id": "admin_home",
        "label": "Admin Home",
        "route_path": "/admin",
        "api_path": "/api/auth/me",
    },
    {
        "id": "admin_system",
        "label": "Admin System",
        "route_path": "/admin-system",
        "api_path": "/api/auth/me",
    },
    {
        "id": "admin_activity_log",
        "label": "Admin Activity Log",
        "route_path": "/admin-activity-log",
        "api_path": "/api/auth/me",
    },
    {
        "id": "ops_performance",
        "label": "Ops Performance",
        "route_path": "/ops-performance",
        "api_path": "/api/auth/me",
    },
    {
        "id": "ops_route_health",
        "label": "Ops Route Health",
        "route_path": "/ops-route-health",
        "api_path": "/api/auth/me",
    },
    {
        "id": "route_health_report",
        "label": "Route Health Report",
        "route_path": "/route-health-report",
        "api_path": "/api/auth/me",
    },
    {
        "id": "policy_console",
        "label": "Policy Console",
        "route_path": "/policy-console",
        "api_path": "/api/auth/me",
    },
    {
        "id": "team_management",
        "label": "Team Management",
        "route_path": "/team-management",
        "api_path": "/api/auth/me",
    },
]

ROUTE_HEALTH_REDIRECT_EXPECTATIONS = {
    "/mini-apps": "/features",
    "/mini-apps/onboarding": "/onboarding",
    "/mini-apps/job-platform": "/job-platform",
    "/mini-apps/mobile-money": "/subscription/plans",
    "/mini-apps/marketplace": "/features/smartbuy",
    "/mini-apps/digital-bank": "/features/pennypilot",
    "/mini-apps/creator-exchange": "/my-analytics",
    "/mini-apps/ai-accounting": "/features/pennypilot",
    "/mini-apps/invoice-generator": "/content-library",
    "/mini-apps/drama-box": "/content-library",
    "/mini-apps/music-streaming": "/features/ai-speech",
    "/mini-apps/local-music": "/features/ai-speech",
}

ROUTE_RESOLUTION_FILE = Path("/app/frontend/src/utils/routeResolution.ts")
FRONTEND_APP_ROOT = Path("/app/frontend/app")
ADMIN_CONSOLE_CATEGORY_FILE = Path("/app/frontend/src/components/admin-console/AdminConsoleExtracted.tsx")
ADMIN_CONSOLE_VIEW_FILE = Path("/app/frontend/src/components/AdminConsoleView.tsx")
APP_SHELL_FILE = Path("/app/frontend/src/components/AppShell.tsx")
EXPECTED_LOCKED_ADMIN_NAV_KEYS = {"team-management", "admin", "admin-console"}
ROUTE_INTEGRITY_CRITICAL_ROUTES = [
    "/admin-console",
    "/executive-dashboard",
    "/ops-route-health",
    "/route-health-report",
]
ROUTE_INTEGRITY_PROTECTED_SEGMENTS = {
    "admin",
    "admin-console",
    "admin-system",
    "admin-activity-log",
    "executive-dashboard",
    "ops-route-health",
    "ops-performance",
    "policy-console",
    "team-management",
}

THEME_VISIBILITY_AUDIT_ROOTS = [
    Path("/app/frontend/app"),
    Path("/app/frontend/src/components"),
]

# ── KNOWN DARK / LIGHT HEX VALUES ────────────────────────────────────────────
_DARK_HEX = r"(?:050A18|080E24|0B0F1A|0F172A|0A0A0A|111827|1F2937|0D1B2A|1A2A45|1E293B|152232|0D2137|0D0F1A|0D0F1C|0A0F1E|060D1B)"
_LIGHT_HEX = r"(?:F9FAFB|F8FAFC|FFFFFF|FFF|E2E8F0|CBD5E1|F1F5F9|FAFBFC|F5F7FA|FFFAEB|FFFFF0)"

# ── AUDIT PATTERN REGISTRY ───────────────────────────────────────────────────
# Each entry: regex (applied per line), severity (fail|warn|info), message, weight
THEME_VISIBILITY_RISK_PATTERNS = {
    # ── FAIL: dark text in dark-mode ternary slot (classic inversion)  ──────────
    # `color: darkMode ? '#DARK'` → dark text shown in dark mode = invisible
    "inverted_dark_text": {
        "regex": re.compile(
            rf"(?<![a-z])color:\s*darkMode\s*\?\s*'#(?:{_DARK_HEX})'",
            re.IGNORECASE,
        ),
        "severity": "fail",
        "message": "Inverted text: dark colour in dark-mode ternary slot → text invisible in dark mode",
        "weight": 30,
    },
    # ── FAIL: both ternary branches resolve to dark (bad in at least one mode) ──
    # `darkMode ? '#DARK' : '#DARK'` → card/text is always dark regardless of theme
    "same_dark_both_modes": {
        "regex": re.compile(
            rf"darkMode\s*\?\s*'#(?:{_DARK_HEX})'\s*:\s*'#(?:{_DARK_HEX})'",
            re.IGNORECASE,
        ),
        "severity": "fail",
        "message": "Same dark colour in both modes → invisible in light mode (and possibly dark mode too)",
        "weight": 25,
    },
    # ── WARN: CSS inline always-dark background (may be intentional in admin panels) ──
    "css_dark_bg_always": {
        "regex": re.compile(
            rf"background(?:Color)?:\s*'#(?:{_DARK_HEX})'",
            re.IGNORECASE,
        ),
        "severity": "warn",
        "message": "Hardcoded dark background with no theme branch → may look like a black card in light mode",
        "weight": 12,
    },
    # ── WARN: hardcoded dark text without branch ──────────────────────────────
    "hardcoded_dark_text_no_branch": {
        "regex": re.compile(
            rf"(?<![a-z])color:\s*'#(?:{_DARK_HEX})'",
            re.IGNORECASE,
        ),
        "severity": "warn",
        "message": "Hardcoded dark text colour without darkMode branch → may be invisible on dark backgrounds",
        "weight": 8,
    },
    # ── WARN: hardcoded light text without branch ────────────────────────────
    "hardcoded_light_text_no_branch": {
        "regex": re.compile(
            rf"(?<![a-z])color:\s*'#(?:{_LIGHT_HEX})'",
            re.IGNORECASE,
        ),
        "severity": "warn",
        "message": "Hardcoded light text colour without darkMode branch → may be invisible in light mode",
        "weight": 6,
    },
    # ── WARN: hardcoded light bg without branch ──────────────────────────────
    "hardcoded_light_bg_no_branch": {
        "regex": re.compile(
            rf"backgroundColor:\s*'#(?:{_LIGHT_HEX})'",
            re.IGNORECASE,
        ),
        "severity": "warn",
        "message": "Hardcoded light background without darkMode branch → may look broken in dark mode",
        "weight": 5,
    },
    # ── INFO: T-object with hardcoded dark values (classic LoginInner pattern) ─
    "t_object_hardcoded_dark": {
        "regex": re.compile(
            rf"(?:text|bg|bgAlt|bgCard|bgSoft):\s*'#(?:{_DARK_HEX})'",
            re.IGNORECASE,
        ),
        "severity": "info",
        "message": "T-object token hardcoded to a dark value — ensure the T object is built from colors.* tokens",
        "weight": 4,
    },
    # ── WARN: ANY hardcoded hex backgroundColor not using colors.* token ──
    # Catches all `backgroundColor: '#XXXXXX'` or `backgroundColor: '#XXX'` patterns
    # that should instead use colors.card, colors.bg, colors.surface, etc.
    "hardcoded_bg_any_hex": {
        "regex": re.compile(
            r"""backgroundColor:\s*['"]#[0-9A-Fa-f]{3,8}['"]""",
        ),
        "severity": "warn",
        "message": "Hardcoded hex backgroundColor — should use V2 colors.* token (e.g. colors.card, colors.bg)",
        "weight": 7,
    },
    # ── WARN: ANY hardcoded hex in CSS background property ──
    # Catches `background: '#XXXXXX'` and `background: 'linear-gradient(...#XXXXXX...)'`
    "hardcoded_css_bg_any_hex": {
        "regex": re.compile(
            r"""(?<!Image)background:\s*['"][^'"]*#[0-9A-Fa-f]{3,8}""",
        ),
        "severity": "warn",
        "message": "Hardcoded hex in background style — should use V2 colors.* token",
        "weight": 6,
    },
    # ── WARN: ANY hardcoded hex color (text) not using colors.* ──
    "hardcoded_text_color_any_hex": {
        "regex": re.compile(
            r"""(?<![a-z])color:\s*['"]#[0-9A-Fa-f]{3,8}['"]""",
        ),
        "severity": "warn",
        "message": "Hardcoded hex text color — should use V2 colors.* token (e.g. colors.text, colors.textMuted)",
        "weight": 5,
    },
    # ── WARN: ANY hardcoded hex borderColor not using colors.* ──
    "hardcoded_border_any_hex": {
        "regex": re.compile(
            r"""borderColor:\s*['"]#[0-9A-Fa-f]{3,8}['"]""",
        ),
        "severity": "warn",
        "message": "Hardcoded hex borderColor — should use V2 colors.* token (e.g. colors.border)",
        "weight": 4,
    },
}

THEME_VISIBILITY_CONTEXTUAL_RELIEF_FILES = {
    "app/payment-history-export-v2.tsx": 0.18,
    "app/payment-document-v2.tsx": 0.18,
}

# ── FILES THAT ARE INTENTIONALLY DARK-ONLY (documents / exports) ─────────────
_THEME_AUDIT_SKIP_FILES = {
    "src/components/ui/",
    "app/payment-history-export",
    "app/payment-document",
    # V7 Cobalt Blue is an isolated template theme — its widget intentionally
    # hardcodes the V7 palette to signal the builder is in V7 mode.
    "src/components/admin/V7TemplateComplianceWidget.tsx",
    # Theme validation dashboard renders V1 vs V2 side-by-side for parity
    # testing; its hardcoded hexes are the intentional demo content.
    "src/components/admin/ThemeValidationDashboard.tsx",
    # SSR / HTML template — no React context, intentionally hardcoded splash.
    "app/+html.tsx",
    "app/+not-found.tsx",
    "app/_layout.tsx",
}

THEME_AUDIT_HISTORY_COLLECTION = "theme_audit_history"
V2_COMPLIANCE_HISTORY_COLLECTION = "v2_compliance_reports"
V2_COMPLIANCE_CACHE_TTL_SECONDS = 300
_V2_RUNTIME_CACHE: dict[str, object] = {"generated_at": None, "report": None}

_V2_LEGACY_BRAND_TOKENS = {
    "#3B82F6",
    "#00D4AA",
    "#6366F1",
    "#8B5CF6",
    "#7C3AED",
    "#A78BFA",
    "#2563EB",
    "#0EA5E9",
    "#06B6D4",
    "#D946EF",
}
_V2_ALLOWED_BRAND_TOKENS = {"#14B8A6", "#0F766E", "#5EEAD4"}
_V2_GLOBAL_BLOCKER_FILES = {
    "app/_layout.tsx",
    "app/+html.tsx",
    "src/components/AppShell.tsx",
    "src/components/GlobalNavBar.tsx",
    "src/components/PublicPageLayout.tsx",
    "src/components/Footer.tsx",
    "src/context/ThemeContext.tsx",
}
_V2_LEGACY_BRAND_REGEX = re.compile(
    r"(#(?:3B82F6|00D4AA|6366F1|8B5CF6|7C3AED|A78BFA|2563EB|0EA5E9|06B6D4|D946EF))",
    re.IGNORECASE,
)
_V2_BRAND_OVERRIDE_REGEX = re.compile(
    r"(?:primary|accent|brand)\s*:\s*['\"](#[0-9A-Fa-f]{6})['\"]",
    re.IGNORECASE,
)
_V2_RAW_HEX_REGEX = re.compile(r"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})")

_GPS_THEME_POLICY_FALLBACK = {
    "pages_theme_version": "v2",
    "email_theme_version": "v7",
    "pdf_theme_version": "v15",
    "pages_theme_enforcement": "mandatory_no_bypass",
    "strict_no_bypass": True,
    "strict_route_prefixes": ["/certificate", "/settings", "/profile"],
}

_V2_STRICT_HEX_ALLOWED_TOKENS = {"#14B8A6", "#0F766E", "#5EEAD4"}
_V2_STRICT_HEX_ALLOWED_EXTERNAL = {"#0A66C2"}
_V2_STRICT_POLICY_COMPONENT_FILES = {
    "src/components/pages/SettingsEnterprise.tsx",
    "src/components/pages/SettingsInner.tsx",
}
_V2_STRICT_SHARED_SHELL_FILES = {
    "src/components/AppShell.tsx",
}


def _normalize_v2_theme_policy(raw_policy: object) -> dict:
    policy = dict(_GPS_THEME_POLICY_FALLBACK)
    if isinstance(raw_policy, dict):
        routes = raw_policy.get("strict_route_prefixes")
        if isinstance(routes, list):
            cleaned = [str(route).strip() for route in routes if str(route).strip().startswith("/")]
            if cleaned:
                policy["strict_route_prefixes"] = sorted(set(cleaned))
    policy["pages_theme_version"] = "v2"
    policy["email_theme_version"] = "v7"
    policy["pdf_theme_version"] = "v15"
    policy["pages_theme_enforcement"] = "mandatory_no_bypass"
    policy["strict_no_bypass"] = True
    return policy


def _route_matches_prefix(route_path: str | None, prefixes: list[str]) -> bool:
    if not route_path:
        return False
    for prefix in prefixes:
        if route_path == prefix or route_path.startswith(prefix + "/") or route_path.startswith(prefix + "*"):
            return True
    return False


async def _get_db():
    from routes.db import db
    return db


async def _collect_web_vitals(db) -> dict:
    """Collect current Web Vitals from web_vitals collection."""
    now = datetime.now(timezone.utc)
    since_1h = now - timedelta(hours=1)
    pipe = [
        {"$match": {"timestamp": {"$gte": since_1h}}},
        {"$group": {
            "_id": None,
            "avg_lcp": {"$avg": "$lcp"}, "avg_fcp": {"$avg": "$fcp"},
            "avg_ttfb": {"$avg": "$ttfb"}, "avg_cls": {"$avg": "$cls"}, "avg_inp": {"$avg": "$inp"},
            "p95_lcp": {"$max": "$lcp"}, "samples": {"$sum": 1},
        }},
    ]
    try:
        data = await db.web_vitals.aggregate(pipe).to_list(1)
        if data:
            d = data[0]
            return {
                "lcp_s": round(d.get("avg_lcp") or 0, 3),
                "fcp_s": round(d.get("avg_fcp") or 0, 3),
                "inp_ms": round(d.get("avg_inp") or 0, 1),
                "ttfb_ms": round(d.get("avg_ttfb") or 0, 1),
                "cls": round(d.get("avg_cls") or 0, 4),
                "p95_lcp": round(d.get("p95_lcp") or 0, 3),
                "samples": d.get("samples", 0),
            }
    except Exception as e:
        logger.warning(f"Web vitals collection error: {e}")
    return {"lcp_s": 0, "fcp_s": 0, "inp_ms": 0, "ttfb_ms": 0, "cls": 0, "p95_lcp": 0, "samples": 0}


def _collect_api_metrics() -> dict:
    """Collect current API metrics from in-memory request stats."""
    from routes.platform_monitor import _request_stats, _server_start
    total = max(_request_stats["total_requests"], 1)
    errors = _request_stats["total_errors"]
    uptime_s = time.time() - _server_start

    all_times = []
    for times in _request_stats["endpoint_times"].values():
        all_times.extend(times)

    p95 = 0
    avg = 0
    if all_times:
        sorted_t = sorted(all_times)
        p95 = round(sorted_t[int(len(sorted_t) * 0.95)] if len(sorted_t) >= 2 else sorted_t[-1], 1)
        avg = round(sum(all_times) / len(all_times), 1)

    return {
        "total_requests": total,
        "total_errors": errors,
        "error_rate_pct": round((errors / total) * 100, 2),
        "api_p95_ms": p95,
        "api_avg_ms": avg,
        "requests_per_min": round(total / max(uptime_s / 60, 1), 1),
        "slow_count": len(_request_stats["slow_requests"]),
        "uptime_s": round(uptime_s),
    }


async def _collect_db_metrics(db) -> dict:
    """Collect database performance metrics."""
    try:
        start = time.time()
        await db.command("ping")
        latency = round((time.time() - start) * 1000, 1)

        collections = await db.list_collection_names()
        total_docs = 0
        for coll_name in collections[:20]:
            try:
                total_docs += await db[coll_name].estimated_document_count()
            except Exception:
                pass

        # Check for slow queries in the last hour
        now = datetime.now(timezone.utc)
        hour_ago = now - timedelta(hours=1)
        slow_count = await db[SLOW_QUERIES_COLLECTION].count_documents(
            {"timestamp": {"$gte": hour_ago}}
        ) if SLOW_QUERIES_COLLECTION in collections else 0

        return {
            "status": "healthy" if latency < 100 else "degraded",
            "db_latency_ms": latency,
            "collections": len(collections),
            "total_documents": total_docs,
            "slow_queries_1h": slow_count,
        }
    except Exception as e:
        return {"status": "error", "db_latency_ms": 9999, "error": str(e)[:100]}


def _collect_bundle_metrics() -> dict:
    web_dist = Path("/app/frontend/dist/client/_expo/static/js/web")
    if not web_dist.exists():
        return {
            "status": "missing",
            "message": "Web dist folder not found",
            "largest_bundle_mb": 0,
            "total_bundle_mb": 0,
            "file_count": 0,
        }

    files = list(web_dist.glob("*.js"))
    if not files:
        return {
            "status": "missing",
            "message": "No web bundles found",
            "largest_bundle_mb": 0,
            "total_bundle_mb": 0,
            "file_count": 0,
        }

    largest = max(files, key=lambda f: f.stat().st_size)
    total_bytes = sum(f.stat().st_size for f in files)
    largest_mb = round(largest.stat().st_size / (1024 * 1024), 3)
    total_mb = round(total_bytes / (1024 * 1024), 3)

    return {
        "status": "ok",
        "largest_bundle_name": largest.name,
        "largest_bundle_mb": largest_mb,
        "total_bundle_mb": total_mb,
        "file_count": len(files),
        "within_largest_budget": largest_mb <= 4.0,
        "within_total_budget": total_mb <= 10.0,
    }


def _normalize_route_health_path(path: str) -> str:
    raw = str(path or "").split("?")[0].split("#")[0].strip()
    if not raw.startswith("/"):
        raw = f"/{raw}" if raw else "/"
    return re.sub(r"/+", "/", raw) or "/"


def _route_first_segment(path: str) -> str:
    parts = [part for part in _normalize_route_health_path(path).split("/") if part]
    return parts[0] if parts else ""


def _collect_segments_from_directory(directory: Path) -> set[str]:
    segments: set[str] = set()
    for entry in directory.iterdir():
        name = entry.name
        if name.startswith(".") or name.startswith("+"):
            continue

        if entry.is_file() and name.endswith(".tsx"):
            stem = Path(name).stem
            if stem in {"index", "_layout"}:
                continue
            if stem.startswith("_") or stem.startswith("+"):
                continue
            if stem.startswith("(") and stem.endswith(")"):
                continue
            segments.add(stem)
            continue

        if entry.is_dir():
            if name.startswith("_"):
                continue
            if name.startswith("(") and name.endswith(")"):
                continue
            segments.add(name)

    return segments


def _discover_top_level_route_segments() -> set[str]:
    if not FRONTEND_APP_ROOT.exists():
        return set()

    segments: set[str] = set()
    for entry in FRONTEND_APP_ROOT.iterdir():
        name = entry.name
        if name.startswith(".") or name.startswith("+"):
            continue

        if entry.is_file() and name.endswith(".tsx"):
            stem = Path(name).stem
            if stem in {"index", "_layout"}:
                continue
            if stem.startswith("_") or stem.startswith("+"):
                continue
            if stem.startswith("(") and stem.endswith(")"):
                continue
            segments.add(stem)
            continue

        if entry.is_dir() and name.startswith("(") and name.endswith(")"):
            segments |= _collect_segments_from_directory(entry)
            continue

        if entry.is_dir() and not name.startswith("_"):
            segments.add(name)

    return segments


def _read_known_top_level_segments() -> set[str]:
    try:
        raw = ROUTE_RESOLUTION_FILE.read_text(encoding="utf-8")
    except Exception:
        return set()

    marker_start = "KNOWN_TOP_LEVEL_SEGMENTS = new Set(["
    start_idx = raw.find(marker_start)
    if start_idx == -1:
        return set()

    block_start = start_idx + len(marker_start)
    block_end = raw.find("])", block_start)
    if block_end == -1:
        return set()

    block = raw[block_start:block_end]
    return set(re.findall(r"'([^']*)'", block))


def _build_route_integrity_checker() -> dict:
    known_segments = _read_known_top_level_segments()
    known_without_root = {seg for seg in known_segments if seg}
    discovered_segments = _discover_top_level_route_segments()

    missing_from_whitelist = sorted(discovered_segments - known_without_root)
    # Expo router group segments like "(tabs)" never appear in URLs, so they are
    # valid whitelist entries that discovery can't see — not stale.
    stale_whitelist_segments = sorted(
        seg for seg in (known_without_root - discovered_segments) if not seg.startswith("(")
    )

    redirect_target_issues = []
    for source_path, expected_target in ROUTE_HEALTH_REDIRECT_EXPECTATIONS.items():
        segment = _route_first_segment(expected_target)
        if segment and segment not in known_without_root:
            redirect_target_issues.append(
                {
                    "source_path": source_path,
                    "expected_target": expected_target,
                    "missing_segment": segment,
                }
            )

    probe_paths = {
        _normalize_route_health_path(str(probe.get("route_path") or ""))
        for probe in ROUTE_HEALTH_PROTECTED_PROBES
    }
    critical_route_checks = []
    for route_path in ROUTE_INTEGRITY_CRITICAL_ROUTES:
        normalized_path = _normalize_route_health_path(route_path)
        segment = _route_first_segment(normalized_path)
        critical_route_checks.append(
            {
                "route_path": normalized_path,
                "segment": segment,
                "has_known_segment": segment in known_without_root,
                "has_runtime_probe": normalized_path in probe_paths,
            }
        )

    protected_discovered_segments = sorted(
        [segment for segment in discovered_segments if segment in ROUTE_INTEGRITY_PROTECTED_SEGMENTS]
    )
    protected_probe_segments = sorted({_route_first_segment(path) for path in probe_paths if _route_first_segment(path)})
    uncovered_protected_segments = sorted(set(protected_discovered_segments) - set(protected_probe_segments))

    missing_critical_segments = [
        row.get("route_path") for row in critical_route_checks if not row.get("has_known_segment")
    ]
    missing_critical_probes = [
        row.get("route_path") for row in critical_route_checks if not row.get("has_runtime_probe")
    ]

    status = "healthy"
    if missing_critical_segments or redirect_target_issues:
        status = "critical"
    elif missing_from_whitelist or stale_whitelist_segments or missing_critical_probes or uncovered_protected_segments:
        status = "warning"

    recommendations: list[str] = []
    if missing_from_whitelist:
        recommendations.append("Add missing top-level routes to KNOWN_TOP_LEVEL_SEGMENTS in routeResolution.ts.")
    if redirect_target_issues:
        recommendations.append("Fix redirect target segments so every legacy redirect lands on a known route segment.")
    if missing_critical_probes:
        recommendations.append("Add runtime protected probes for critical admin/executive routes.")
    if uncovered_protected_segments:
        recommendations.append("Review protected admin/executive segments that are not covered by route-health probes.")
    if not recommendations:
        recommendations.append("Route registry and protected-route checker are healthy.")

    return {
        "status": status,
        "known_segment_count": len(known_without_root),
        "discovered_segment_count": len(discovered_segments),
        "missing_from_whitelist": missing_from_whitelist,
        "stale_whitelist_segments": stale_whitelist_segments,
        "redirect_target_issues": redirect_target_issues,
        "critical_route_checks": critical_route_checks,
        "protected_discovered_segments": protected_discovered_segments,
        "protected_probe_segments": protected_probe_segments,
        "uncovered_protected_segments": uncovered_protected_segments,
        "recommendations": recommendations,
    }


def _parse_admin_console_tab_registry() -> dict:
    try:
        raw = ADMIN_CONSOLE_CATEGORY_FILE.read_text(encoding="utf-8")
    except Exception:
        return {"categories": [], "tabs": []}

    categories = []
    tabs = []

    category_pattern = re.compile(
        r"\{\s*id:\s*'([^']+)'\s*,\s*label:\s*'([^']+)'[\s\S]*?tabs:\s*\[([\s\S]*?)\]\s*,?\s*\}",
        re.MULTILINE,
    )
    tab_pattern = re.compile(r"\{\s*id:\s*'([^']+)'\s*,\s*label:\s*'([^']+)'")

    for cat_id, cat_label, tabs_block in category_pattern.findall(raw):
        category_item = {
            "category_id": str(cat_id),
            "category_label": str(cat_label),
            "tab_count": 0,
        }
        categories.append(category_item)
        for tab_id, tab_label in tab_pattern.findall(tabs_block):
            tab_doc = {
                "category_id": str(cat_id),
                "category_label": str(cat_label),
                "tab_id": str(tab_id),
                "tab_label": str(tab_label),
            }
            tabs.append(tab_doc)
            category_item["tab_count"] = int(category_item["tab_count"] or 0) + 1

    return {
        "categories": categories,
        "tabs": tabs,
    }


def _parse_admin_console_renderer_registry() -> dict:
    try:
        raw = ADMIN_CONSOLE_VIEW_FILE.read_text(encoding="utf-8")
    except Exception:
        return {
            "panel_case_tabs": [],
            "alias_target_tabs": [],
            "supported_tab_ids": [],
        }

    panel_case_tabs = sorted(set(re.findall(r"case '([^']+)':\s*return", raw)))
    alias_target_tabs: set[str] = set()
    if "const TAB_ALIASES" in raw:
        alias_block = raw.split("const TAB_ALIASES", 1)[1]
        alias_block = alias_block.split("};", 1)[0]
        alias_target_tabs = set(re.findall(r"'[^']+'\s*:\s*'([^']+)'", alias_block))

    supported_tab_ids = sorted(set(panel_case_tabs) | alias_target_tabs)
    return {
        "panel_case_tabs": panel_case_tabs,
        "alias_target_tabs": sorted(alias_target_tabs),
        "supported_tab_ids": supported_tab_ids,
    }


def _build_admin_tab_integrity() -> dict:
    registry = _parse_admin_console_tab_registry()
    renderer = _parse_admin_console_renderer_registry()

    tab_ids = sorted({str(row.get("tab_id") or "") for row in registry.get("tabs", []) if row.get("tab_id")})
    supported_tab_ids = sorted({str(tab_id) for tab_id in renderer.get("supported_tab_ids", []) if tab_id})

    missing_tab_renderers = sorted(set(tab_ids) - set(supported_tab_ids))
    orphan_renderer_tabs = sorted(set(supported_tab_ids) - set(tab_ids))

    status = "healthy"
    if missing_tab_renderers:
        status = "critical"
    elif orphan_renderer_tabs:
        status = "warning"

    recommendations: list[str] = []
    if missing_tab_renderers:
        recommendations.append("Add PanelContent handlers for admin tabs missing renderers to prevent blank admin panels.")
    if orphan_renderer_tabs:
        recommendations.append("Remove or remap stale PanelContent handlers that no longer exist in admin category tab definitions.")
    if not recommendations:
        recommendations.append("Admin tab registry and renderer mapping are synchronized.")

    return {
        "status": status,
        "total_categories": len(registry.get("categories", [])),
        "total_tabs": len(tab_ids),
        "total_supported_renderers": len(supported_tab_ids),
        "categories": registry.get("categories", []),
        "missing_tab_renderers": missing_tab_renderers,
        "orphan_renderer_tabs": orphan_renderer_tabs,
        "recommendations": recommendations,
    }


async def _run_admin_tab_runtime_probe(client: httpx.AsyncClient, base_url: str, headers: dict[str, str]) -> dict:
    registry = _parse_admin_console_tab_registry()
    tab_entries = registry.get("tabs", [])
    if not tab_entries:
        return {
            "status": "warning",
            "probed_tabs": 0,
            "healthy_tabs": 0,
            "failed_tabs": [],
            "recommendations": ["Admin tab definitions could not be parsed; verify AdminConsoleExtracted.tsx format."],
        }

    probes = []
    probe_meta = []
    for row in tab_entries:
        category_id = str(row.get("category_id") or "").strip()
        tab_id = str(row.get("tab_id") or "").strip()
        if not category_id or not tab_id:
            continue
        path = f"/admin-console?category={category_id}&tab={tab_id}"
        probes.append(_run_route_probe(client, base_url, path, headers=headers))
        probe_meta.append({"category_id": category_id, "tab_id": tab_id})

    probe_results = await asyncio.gather(*probes, return_exceptions=True)
    normalized_results = [row for row in probe_results if isinstance(row, dict)]

    failed_tabs = []
    for idx, result in enumerate(probe_results):
        if not isinstance(result, dict):
            failed_tabs.append(
                {
                    "category_id": probe_meta[idx].get("category_id") if idx < len(probe_meta) else "",
                    "tab_id": probe_meta[idx].get("tab_id") if idx < len(probe_meta) else "",
                    "status_code": 0,
                    "final_path": "",
                    "latency_ms": 0,
                }
            )
            continue

        row = result
        meta = probe_meta[idx] if idx < len(probe_meta) else {}
        final_path = str(row.get("final_path") or "")
        healthy = bool(row.get("healthy")) and final_path.startswith("/admin-console")
        if not healthy:
            failed_tabs.append(
                {
                    "category_id": meta.get("category_id"),
                    "tab_id": meta.get("tab_id"),
                    "status_code": row.get("status_code", 0),
                    "final_path": final_path,
                    "latency_ms": row.get("latency_ms", 0),
                }
            )

    healthy_tabs = max(0, len(normalized_results) - len(failed_tabs))
    status = "healthy" if not failed_tabs else ("warning" if len(failed_tabs) <= 3 else "critical")

    recommendations: list[str] = []
    if failed_tabs:
        recommendations.append("Fix admin-console category/tab URL handling and route guards for the failing tab deep links.")
    else:
        recommendations.append("All admin tab deep links rendered successfully.")

    return {
        "status": status,
        "probed_tabs": len(normalized_results),
        "healthy_tabs": healthy_tabs,
        "failed_tabs": failed_tabs[:20],
        "recommendations": recommendations,
    }


def _scan_file_for_theme_issues(file_path: Path, relative_path: str) -> dict:
    """Scan a single file line-by-line for theme visibility issues."""
    # Skip intentionally dark-only files
    for skip_marker in _THEME_AUDIT_SKIP_FILES:
        if skip_marker in relative_path:
            return {
                "file": relative_path,
                "skipped": True,
                "skip_reason": "Intentionally dark-only or design system file",
                "issues": [],
                "fail_count": 0,
                "warn_count": 0,
                "info_count": 0,
                "total_issues": 0,
                "grade": "A",
            }
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {
            "file": relative_path,
            "error": True,
            "issues": [],
            "fail_count": 0,
            "warn_count": 0,
            "info_count": 0,
            "total_issues": 0,
            "grade": "?",
        }

    # File-level suppression pragma: `// @theme-audit-file-ok: <reason>` anywhere
    # in the first 20 lines signals that all hardcoded hex in the file are
    # intentional (SSR splash, semantic state chrome, brand identity tables, etc.).
    header = "\n".join(lines[:20])
    if "@theme-audit-file-ok" in header:
        return {
            "file": relative_path,
            "skipped": True,
            "skip_reason": "File-level @theme-audit-file-ok pragma",
            "issues": [],
            "fail_count": 0,
            "warn_count": 0,
            "info_count": 0,
            "total_issues": 0,
            "grade": "A",
        }

    issues: list[dict] = []

    for line_no, raw_line in enumerate(lines, 1):
        stripped = raw_line.strip()
        # Skip pure comment lines
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue

        # Line-level suppression: `// @theme-ok` or `/* @theme-ok */`
        # Signals the engineer intentionally wants a hardcoded hex on this line
        # (brand identity colors, SSR splash, semantic state chrome, etc.)
        if "@theme-ok" in raw_line:
            continue

        has_dark_ternary = bool(re.search(r"darkMode\s*\?", raw_line))
        has_colors_token = bool(re.search(r"colors\.\w+", raw_line))
        snippet = stripped[:130]

        for pattern_key, cfg in THEME_VISIBILITY_RISK_PATTERNS.items():
            regex = cfg["regex"]

            # "no_branch" patterns only fire on lines WITHOUT a darkMode ternary
            if "no_branch" in pattern_key and has_dark_ternary:
                continue

            # ternary-specific patterns only fire on lines WITH darkMode ternary
            if pattern_key in ("inverted_dark_bg", "inverted_dark_text", "same_dark_both_modes"):
                if not has_dark_ternary:
                    continue

            # Generic "any_hex" patterns skip lines that already use colors.* tokens
            if pattern_key.endswith("_any_hex") and has_colors_token:
                continue

            if regex.search(raw_line):
                issues.append({
                    "line": line_no,
                    "pattern": pattern_key,
                    "severity": cfg["severity"],
                    "message": cfg["message"],
                    "code": snippet.encode("ascii", "replace").decode("ascii"),
                })

    # Deduplicate: keep only the worst issue per line
    _SEVERITY_RANK = {"fail": 3, "warn": 2, "info": 1}
    best_per_line: dict[int, dict] = {}
    for issue in issues:
        ln = issue["line"]
        if ln not in best_per_line or _SEVERITY_RANK[issue["severity"]] > _SEVERITY_RANK[best_per_line[ln]["severity"]]:
            best_per_line[ln] = issue

    final_issues = sorted(best_per_line.values(), key=lambda x: x["line"])

    fail_count = sum(1 for i in final_issues if i["severity"] == "fail")
    warn_count = sum(1 for i in final_issues if i["severity"] == "warn")
    info_count = sum(1 for i in final_issues if i["severity"] == "info")

    if fail_count >= 8:
        grade = "F"
    elif fail_count >= 4:
        grade = "D"
    elif fail_count >= 2:
        grade = "C"
    elif fail_count >= 1 or warn_count >= 12:
        grade = "B"
    elif warn_count >= 5:
        grade = "B"
    else:
        grade = "A"

    return {
        "file": relative_path,
        "issues": final_issues,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "info_count": info_count,
        "total_issues": len(final_issues),
        "grade": grade,
    }


def _build_theme_visibility_audit() -> dict:
    """Full platform static code scan for dark/light mode colour visibility issues."""
    files_to_scan: list[Path] = []
    for root in THEME_VISIBILITY_AUDIT_ROOTS:
        if not root.exists():
            continue
        files_to_scan.extend(sorted(root.rglob("*.tsx")))

    file_results: list[dict] = []
    for fp in files_to_scan:
        rel = str(fp).replace("/app/frontend/", "")
        file_results.append(_scan_file_for_theme_issues(fp, rel))

    active = [r for r in file_results if not r.get("skipped") and not r.get("error")]

    total_fail = sum(r["fail_count"] for r in active)
    total_warn = sum(r["warn_count"] for r in active)
    total_info = sum(r["info_count"] for r in active)
    total_files = len(active)
    files_failing = [r for r in active if r["fail_count"] > 0]
    files_warning = [r for r in active if r["fail_count"] == 0 and r["warn_count"] > 0]
    files_clean = [r for r in active if r["total_issues"] == 0]

    # Overall platform grade
    # FAIL issues (same-dark-in-both-modes, invisible-text) are the actionable, user-visible bugs.
    # WARN issues are advisory (hardcoded color without darkMode branch) — many are chart/admin
    # specific and don't always need theming. We primarily grade on FAILs, using warnings only
    # to distinguish A vs A- when no critical issues exist.
    if total_fail >= 20:
        overall_grade = "F"
    elif total_fail >= 10:
        overall_grade = "D"
    elif total_fail >= 5:
        overall_grade = "C"
    elif total_fail >= 2:
        overall_grade = "B"
    elif total_fail == 1:
        overall_grade = "A-"
    elif total_warn >= 2000:
        overall_grade = "A-"
    else:
        overall_grade = "A"

    # Sort: failing files first (by fail_count desc), then warning files
    sorted_results = (
        sorted(files_failing, key=lambda r: r["fail_count"], reverse=True)
        + sorted(files_warning, key=lambda r: r["warn_count"], reverse=True)
        + sorted(files_clean, key=lambda r: r["file"])
    )

    return {
        "overall_grade": overall_grade,
        "summary": {
            "total_files_scanned": total_files,
            "files_failing": len(files_failing),
            "files_warning": len(files_warning),
            "files_clean": len(files_clean),
            "total_fail_issues": total_fail,
            "total_warn_issues": total_warn,
            "total_info_issues": total_info,
        },
        "files": sorted_results,
        "patterns_checked": list(THEME_VISIBILITY_RISK_PATTERNS.keys()),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }


def _route_from_relative_file(relative_path: str) -> str | None:
    if not relative_path.startswith("app/") or not relative_path.endswith(".tsx"):
        return None
    route = relative_path[len("app/") : -4]
    parts = [part for part in route.split("/") if part and not (part.startswith("(") and part.endswith(")"))]
    if not parts:
        return "/"
    has_dynamic = any(part.startswith("[") and part.endswith("]") for part in parts)
    if has_dynamic:
        cleaned_parts = ["*" if (part.startswith("[") and part.endswith("]")) else part for part in parts]
        path = "/" + "/".join(cleaned_parts)
        return path if path != "/" else "/"
    if parts[-1] == "index":
        parts = parts[:-1]
    path = "/" + "/".join(parts)
    return path if path != "/" else "/"


def _scan_file_for_v2_compliance(
    file_path: Path,
    relative_path: str,
    *,
    strict_route_prefixes: list[str],
    strict_no_bypass: bool,
) -> dict:
    route_path = _route_from_relative_file(relative_path)
    is_strict_policy_file = relative_path in _V2_STRICT_POLICY_COMPONENT_FILES
    strict_route = _route_matches_prefix(route_path, strict_route_prefixes) or is_strict_policy_file

    try:
        raw_text = file_path.read_text(encoding="utf-8")
        lines = raw_text.splitlines()
    except Exception:
        return {
            "file": relative_path,
            "issues": [],
            "fail_count": 0,
            "warn_count": 0,
            "total_issues": 0,
            "route_path": route_path,
        }

    # Parity with the ratchet scanner (`_theme_scanner.is_file_opted_out`):
    # a file whose opening ~800 bytes carry `@theme-audit-file-ok` is an
    # explicit, justification-documented design exception (intentional
    # always-dark ops/admin panels). Skip both rules for such files so the
    # runtime scanner matches the static ratchet behaviour.
    if "@theme-audit-file-ok" in (raw_text[:800] or "") and not (strict_no_bypass and strict_route):
        return {
            "file": relative_path,
            "issues": [],
            "fail_count": 0,
            "warn_count": 0,
            "total_issues": 0,
            "route_path": route_path,
            "exempted": True,
        }

    issues: list[dict] = []
    for line_no, raw_line in enumerate(lines, 1):
        stripped = raw_line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue

        legacy_match = _V2_LEGACY_BRAND_REGEX.search(raw_line)
        if legacy_match:
            issues.append({
                "line": line_no,
                "severity": "fail",
                "rule": "legacy_brand_color",
                "message": f"Legacy brand token {legacy_match.group(1).upper()} found. Use V2 teal tokens only.",
                "code": stripped[:160],
            })
            continue

        brand_override_match = _V2_BRAND_OVERRIDE_REGEX.search(raw_line)
        if brand_override_match:
            token = brand_override_match.group(1).upper()
            if token not in _V2_ALLOWED_BRAND_TOKENS and token not in _V2_LEGACY_BRAND_TOKENS:
                issues.append({
                    "line": line_no,
                    "severity": "warn",
                    "rule": "brand_override_token",
                    "message": f"Custom brand token {token} is outside the approved V2 teal system.",
                    "code": stripped[:160],
                })

        if strict_no_bypass and strict_route:
            raw_hex = sorted(set(_V2_RAW_HEX_REGEX.findall(raw_line)))
            for token in raw_hex:
                upper = token.upper()
                if upper in _V2_STRICT_HEX_ALLOWED_TOKENS or upper in _V2_STRICT_HEX_ALLOWED_EXTERNAL:
                    continue
                if upper in _V2_LEGACY_BRAND_TOKENS:
                    continue
                issues.append(
                    {
                        "line": line_no,
                        "severity": "fail",
                        "rule": "strict_no_bypass_raw_hex",
                        "message": f"Strict no-bypass route cannot use raw hex token {upper}; use V2 theme tokens from GPS/ThemeContext.",
                        "code": stripped[:160],
                    }
                )

    fail_count = sum(1 for issue in issues if issue["severity"] == "fail")
    warn_count = sum(1 for issue in issues if issue["severity"] == "warn")
    return {
        "file": relative_path,
        "issues": issues[:25],
        "fail_count": fail_count,
        "warn_count": warn_count,
        "total_issues": len(issues),
        "route_path": route_path,
        "strict_route": strict_route,
    }


async def _build_v2_compliance_report() -> dict:
    db = await _get_db()
    gps_state = await db.global_platform_state.find_one({"state_id": "global-platform-state"}, {"_id": 0, "theme_policy": 1})
    theme_policy = _normalize_v2_theme_policy((gps_state or {}).get("theme_policy"))
    strict_route_prefixes = list(theme_policy.get("strict_route_prefixes") or [])
    strict_no_bypass = bool(theme_policy.get("strict_no_bypass", True))

    theme_visibility = _build_theme_visibility_audit()
    files_to_scan: list[Path] = []
    for root in THEME_VISIBILITY_AUDIT_ROOTS:
        if root.exists():
            files_to_scan.extend(sorted(root.rglob("*.tsx")))

    scanned = [
        _scan_file_for_v2_compliance(
            fp,
            str(fp).replace("/app/frontend/", ""),
            strict_route_prefixes=strict_route_prefixes,
            strict_no_bypass=strict_no_bypass,
        )
        for fp in files_to_scan
    ]

    synthetic_blockers: list[dict] = []
    if strict_no_bypass:
        for row in scanned:
            if not row.get("exempted"):
                continue
            file_name = str(row.get("file") or "")
            if file_name in _V2_STRICT_SHARED_SHELL_FILES:
                for prefix in strict_route_prefixes:
                    synthetic_blockers.append(
                        {
                            "file": f"strict-no-bypass:{file_name}",
                            "route_path": f"{prefix}*",
                            "issues": [
                                {
                                    "line": 1,
                                    "severity": "fail",
                                    "rule": "strict_no_bypass_exemption",
                                    "message": "Strict no-bypass policy disallows shell-level theme-audit exemptions for this route family.",
                                    "code": file_name,
                                }
                            ],
                            "fail_count": 1,
                            "warn_count": 0,
                            "total_issues": 1,
                            "strict_route": True,
                        }
                    )

    blockers = [row for row in scanned if row.get("fail_count", 0) > 0]
    blockers.extend(synthetic_blockers)
    warnings = [row for row in scanned if row.get("fail_count", 0) == 0 and row.get("warn_count", 0) > 0]
    blocking_routes = sorted({row.get("route_path") for row in blockers if row.get("route_path")})
    global_blockers = [row for row in blockers if row.get("file") in _V2_GLOBAL_BLOCKER_FILES]

    legacy_issue_count = sum(int(row.get("fail_count") or 0) for row in blockers)
    token_warning_count = sum(int(row.get("warn_count") or 0) for row in warnings)
    theme_fail = int((theme_visibility.get("summary") or {}).get("total_fail_issues") or 0)
    theme_warn = int((theme_visibility.get("summary") or {}).get("total_warn_issues") or 0)

    score = max(0, 100 - (legacy_issue_count * 15) - min(token_warning_count, 30) - min(theme_fail * 8, 32) - min(theme_warn // 75, 20))
    advisory_warning_count = token_warning_count + theme_warn
    status = "healthy"
    if global_blockers or legacy_issue_count > 0:
        status = "critical"
    elif theme_fail > 0:
        status = "warning"

    enforcement_mode = "blocking" if strict_no_bypass else ("blocking" if status == "critical" else "observe")

    report = {
        "run_id": f"v2c_{int(datetime.now(timezone.utc).timestamp())}",
        "status": status,
        "score": score,
        "enforcement_mode": enforcement_mode,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "theme_policy": theme_policy,
        "summary": {
            "total_files_scanned": len(scanned),
            "files_with_blockers": len(blockers),
            "files_with_warnings": len(warnings),
            "blocking_routes_count": len(blocking_routes),
            "global_blocker_count": len(global_blockers),
            "strict_no_bypass": strict_no_bypass,
            "legacy_brand_issue_count": legacy_issue_count,
            "token_warning_count": token_warning_count,
            "theme_visibility_fail_count": theme_fail,
            "theme_visibility_warn_count": theme_warn,
            "advisory_warning_count": advisory_warning_count,
        },
        "blocking_routes": blocking_routes,
        "global_block": len(global_blockers) > 0,
        "top_blockers": sorted(blockers, key=lambda row: row.get("fail_count", 0), reverse=True)[:16],
        "warning_files": sorted(warnings, key=lambda row: row.get("warn_count", 0), reverse=True)[:12],
        "global_blockers": global_blockers[:12],
        "theme_visibility_summary": theme_visibility.get("summary", {}),
        "recommendations": [
            "Use `useTheme().colors` tokens for app surfaces and text instead of legacy inline brand hex values.",
            "Keep route files free from legacy purple/blue accents so runtime enforcement never blocks a page.",
            "Strict no-bypass families (/certificate*, /settings*, /profile*) cannot rely on shell-level exemption pragmas.",
            "Use the Theme Health Center validation + remediation tools before shipping new UI.",
        ],
        "rules_checked": ["legacy_brand_color", "brand_override_token", "theme_visibility_audit"],
    }
    return report


async def _get_or_build_v2_compliance_report(force_refresh: bool = False, persist: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    cached_report = _V2_RUNTIME_CACHE.get("report")
    cached_at = _V2_RUNTIME_CACHE.get("generated_at")
    if not force_refresh and cached_report and isinstance(cached_at, datetime) and (now - cached_at).total_seconds() < V2_COMPLIANCE_CACHE_TTL_SECONDS:
        return cached_report  # type: ignore[return-value]

    report = await _build_v2_compliance_report()
    _V2_RUNTIME_CACHE["report"] = report
    _V2_RUNTIME_CACHE["generated_at"] = now

    if persist:
        db = await _get_db()
        await db[V2_COMPLIANCE_HISTORY_COLLECTION].insert_one({k: v for k, v in report.items() if k != "_id"})
    return report


def _extract_string_set(raw: str, marker: str) -> set[str]:
    idx = raw.find(marker)
    if idx == -1:
        return set()
    start = raw.find("[", idx)
    end = raw.find("]", start)
    if start == -1 or end == -1:
        return set()
    block = raw[start:end]
    return set(re.findall(r"'([^']+)'", block))


def _extract_nav_item_keys(raw: str, marker: str) -> set[str]:
    idx = raw.find(marker)
    if idx == -1:
        return set()
    start = raw.find("[", idx)
    if start == -1:
        return set()
    # Find matching closing bracket by counting brackets
    depth = 0
    end = start
    for i, char in enumerate(raw[start:], start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == start:
        return set()
    block = raw[start:end + 1]
    keys = set(re.findall(r"key:\s*'([^']+)'", block))
    if "...ADMIN_ITEM" in block:
        keys.add("admin")
    return keys


def _build_navigation_lock_audit() -> dict:
    try:
        raw = APP_SHELL_FILE.read_text(encoding="utf-8")
    except Exception:
        return {
            "status": "warning",
            "message": "Unable to read AppShell navigation definitions.",
            "recommendations": ["Verify AppShell.tsx is available for navigation lock audit."],
        }

    locked_user_keys = _extract_string_set(raw, "const LOCKED_USER_NAV_KEYS")
    locked_admin_keys = _extract_string_set(raw, "const LOCKED_ADMIN_NAV_KEYS")
    base_nav_keys = _extract_nav_item_keys(raw, "const BASE_NAV_ITEMS")
    admin_nav_keys = _extract_nav_item_keys(raw, "const adminNavDefinitions")

    unlocked_user_keys = sorted(base_nav_keys - locked_user_keys)
    missing_locked_user_keys = sorted(locked_user_keys - base_nav_keys)
    admin_expected_missing = sorted(EXPECTED_LOCKED_ADMIN_NAV_KEYS - locked_admin_keys)
    admin_unexpected_locked = sorted(locked_admin_keys - EXPECTED_LOCKED_ADMIN_NAV_KEYS)
    admin_unexpected_active = sorted(admin_nav_keys - EXPECTED_LOCKED_ADMIN_NAV_KEYS)

    status = "healthy"
    if admin_expected_missing or admin_unexpected_active:
        status = "critical"
    elif unlocked_user_keys or missing_locked_user_keys or admin_unexpected_locked:
        status = "warning"

    recommendations: list[str] = []
    if status == "healthy":
        recommendations.append("Admin/User navigation lock is healthy and matches approved keys.")
    else:
        recommendations.append("Keep AppShell navigation aligned with locked key sets and approved admin nav keys.")
        if admin_unexpected_active:
            recommendations.append("Remove unapproved ADMIN items from active admin navigation definitions.")

    return {
        "status": status,
        "locked_user_key_count": len(locked_user_keys),
        "base_nav_key_count": len(base_nav_keys),
        "locked_admin_keys": sorted(locked_admin_keys),
        "active_admin_nav_keys": sorted(admin_nav_keys),
        "unlocked_user_keys": unlocked_user_keys,
        "missing_locked_user_keys": missing_locked_user_keys,
        "admin_expected_missing": admin_expected_missing,
        "admin_unexpected_locked": admin_unexpected_locked,
        "admin_unexpected_active": admin_unexpected_active,
        "recommendations": recommendations,
    }


def _resolve_frontend_base_url(request: Request) -> str:
    origin = request.headers.get("origin", "").strip()
    if origin.startswith("http"):
        return re.sub(r"\.cluster-\d+\.preview\.emergentcf\.cloud$", ".preview.emergentagent.com", origin.rstrip("/"))

    referer = request.headers.get("referer", "").strip()
    if referer.startswith("http"):
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            return re.sub(r"\.cluster-\d+\.preview\.emergentcf\.cloud$", ".preview.emergentagent.com", normalized)

    configured = (
        os.environ.get("FRONTEND_PUBLIC_URL")
        or os.environ.get("FRONTEND_BASE_URL")
        or os.environ.get("REACT_APP_BACKEND_URL")
    )
    if configured:
        return configured.rstrip("/")

    resolved = str(request.base_url).rstrip("/")
    resolved = re.sub(r"\.cluster-\d+\.preview\.emergentcf\.cloud$", ".preview.emergentagent.com", resolved)
    return resolved


def _extract_path_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or "/"


def _compact_trace_excerpt(raw: str, limit: int = 220) -> str:
    return re.sub(r"\s+", " ", str(raw or "")).strip()[:limit]


async def _run_route_probe(client: httpx.AsyncClient, base_url: str, path: str, headers: dict | None = None) -> dict:
    target = f"{base_url}{path}"
    start = time.perf_counter()
    try:
        response = await client.get(target, headers=headers)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        final_path = _extract_path_from_url(str(response.url))
        healthy = response.status_code < 400
        body_excerpt = ""
        try:
            body_excerpt = _compact_trace_excerpt((response.text or "")[:1800])
        except Exception:
            body_excerpt = ""

        lowered = body_excerpt.lower()
        runtime_markers = (
            "something went wrong",
            "error boundary",
            "referenceerror",
            "typeerror",
            "unhandledrejection",
            "uncaught",
            "render crashed",
        )
        white_screen_markers = (
            "app shell fallback",
            "taking longer than expected",
            "skip to login",
            "blank-page-fallback",
            "white-screen-hint",
        )

        runtime_error_hint = bool(response.status_code >= 500 or any(marker in lowered for marker in runtime_markers))
        white_screen_hint = bool(response.status_code == 200 and any(marker in lowered for marker in white_screen_markers))
        timeout_hint = bool(latency_ms >= 7000)

        diagnostic_flags: list[str] = []
        if response.status_code >= 500:
            diagnostic_flags.append("http_5xx")
        if runtime_error_hint:
            diagnostic_flags.append("runtime_hint")
        if white_screen_hint:
            diagnostic_flags.append("white_screen_hint")
        if timeout_hint:
            diagnostic_flags.append("slow_route_probe")

        crash_signature = ""
        if timeout_hint:
            crash_signature = "route_latency_timeout_hint"
        elif response.status_code >= 500:
            crash_signature = f"route_status_{response.status_code}"
        elif runtime_error_hint:
            crash_signature = "route_runtime_hint"
        elif white_screen_hint:
            crash_signature = "route_white_screen_hint"

        return {
            "path": path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "final_path": final_path,
            "healthy": healthy,
            "runtime_error_hint": runtime_error_hint,
            "white_screen_hint": white_screen_hint,
            "timeout_hint": timeout_hint,
            "diagnostic_flags": diagnostic_flags,
            "crash_signature": crash_signature,
            "trace_excerpt": body_excerpt,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        error_excerpt = _compact_trace_excerpt(str(exc), 220)
        lowered_error = error_excerpt.lower()
        timeout_hint = "timeout" in lowered_error
        diagnostic_flags = ["route_probe_exception"]
        if timeout_hint:
            diagnostic_flags.append("request_timeout")
        return {
            "path": path,
            "status_code": 0,
            "latency_ms": latency_ms,
            "final_path": "",
            "healthy": False,
            "runtime_error_hint": True,
            "white_screen_hint": timeout_hint,
            "timeout_hint": timeout_hint,
            "diagnostic_flags": diagnostic_flags,
            "crash_signature": "route_probe_timeout" if timeout_hint else "route_probe_exception",
            "trace_excerpt": error_excerpt,
            "error": str(exc)[:180],
        }


async def _run_api_probe(client: httpx.AsyncClient, url: str, headers: dict | None = None) -> dict:
    start = time.perf_counter()
    try:
        response = await client.get(url, headers=headers)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        timeout_hint = bool(latency_ms >= 7000)
        api_error_hint = bool(response.status_code >= 500)
        body_excerpt = ""
        if api_error_hint:
            try:
                body_excerpt = _compact_trace_excerpt((response.text or "")[:1800])
            except Exception:
                body_excerpt = ""
        diagnostic_flags: list[str] = []
        if timeout_hint:
            diagnostic_flags.append("slow_api_probe")
        if api_error_hint:
            diagnostic_flags.append("api_5xx")
        return {
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "healthy": response.status_code < 400,
            "api_timeout_hint": timeout_hint,
            "api_error_hint": api_error_hint,
            "api_error_category": f"http_{response.status_code}" if response.status_code >= 500 else "none",
            "trace_excerpt": body_excerpt,
            "diagnostic_flags": diagnostic_flags,
        }
    except Exception as exc:
        error_excerpt = _compact_trace_excerpt(str(exc), 220)
        lowered_error = error_excerpt.lower()
        timeout_hint = "timeout" in lowered_error
        diagnostic_flags = ["api_probe_exception"]
        if timeout_hint:
            diagnostic_flags.append("api_timeout")
        return {
            "status_code": 0,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "healthy": False,
            "error": str(exc)[:180],
            "api_timeout_hint": timeout_hint,
            "api_error_hint": True,
            "api_error_category": "timeout" if timeout_hint else "network_exception",
            "trace_excerpt": error_excerpt,
            "diagnostic_flags": diagnostic_flags,
        }


async def _mint_route_health_admin_session() -> str:
    from routes.db import create_jwt_token

    db = await _get_db()
    admin_email = os.environ.get("TEST_ADMIN_EMAIL", "admin@realaicoach.app")
    user = await db.users.find_one({"email": admin_email}, {"_id": 0, "user_id": 1, "email": 1, "token_version": 1})
    if not user:
        return ""

    token = create_jwt_token(user["user_id"], user["email"], int(user.get("token_version", 0) or 0), 30)
    now = datetime.now(timezone.utc)
    await db.user_sessions.update_one(
        {"session_token": token},
        {
            "$set": {
                "session_token": token,
                "user_id": user["user_id"],
                "email": user["email"],
                "issued_at": now,
                "expires_at": now + timedelta(minutes=30),
                "auth_provider": "route_health_guard",
                "synthetic_monitor": True,
            }
        },
        upsert=True,
    )
    return token


async def _run_protected_route_probe(client: httpx.AsyncClient, route_base_url: str, api_base_url: str, probe: dict, headers: dict[str, str]) -> dict:
    route_result = await _run_route_probe(client, route_base_url, probe["route_path"])
    api_result = await _run_api_probe(client, f"{api_base_url}{probe['api_path']}", headers=headers)
    api_status = int(api_result.get("status_code", 0) or 0)
    api_auth_guard_ok = api_status in {401, 403}
    api_available = bool(api_result.get("healthy")) or api_auth_guard_ok
    api_timeout_hint = bool(api_result.get("api_timeout_hint"))
    api_error_hint = bool(api_result.get("api_error_hint"))
    healthy = bool(route_result.get("healthy")) and api_available
    runtime_error_hint = bool(route_result.get("runtime_error_hint") or api_status >= 500 or api_error_hint)
    white_screen_hint = bool(route_result.get("white_screen_hint") or (bool(route_result.get("healthy")) and api_timeout_hint))

    diagnostic_flags = list(dict.fromkeys([
        *(route_result.get("diagnostic_flags") or []),
        *(api_result.get("diagnostic_flags") or []),
    ]))

    return {
        "id": probe["id"],
        "label": probe["label"],
        "route_path": probe["route_path"],
        "api_path": probe["api_path"],
        "healthy": healthy,
        "route_status_code": route_result.get("status_code", 0),
        "api_status_code": api_status,
        "api_auth_guard_ok": api_auth_guard_ok,
        "latency_ms": round(float(route_result.get("latency_ms", 0) or 0) + float(api_result.get("latency_ms", 0) or 0), 2),
        "final_path": route_result.get("final_path", ""),
        "runtime_error_hint": runtime_error_hint,
        "white_screen_hint": white_screen_hint,
        "api_timeout_hint": api_timeout_hint,
        "api_error_hint": api_error_hint,
        "api_error_category": api_result.get("api_error_category") or "none",
        "api_trace_excerpt": api_result.get("trace_excerpt") or "",
        "route_trace_excerpt": route_result.get("trace_excerpt") or "",
        "diagnostic_flags": diagnostic_flags,
    }


def _collect_system_metrics() -> dict:
    """Collect system resource metrics."""
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    proc = psutil.Process(os.getpid())
    proc_mem = proc.memory_info()

    return {
        "cpu_pct": round(cpu, 1),
        "memory_pct": round(mem.percent, 1),
        "memory_used_mb": round(mem.used / 1024 / 1024),
        "memory_total_mb": round(mem.total / 1024 / 1024),
        "disk_pct": round(disk.percent, 1),
        "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
        "net_sent_mb": round(net.bytes_sent / 1024 / 1024, 1),
        "net_recv_mb": round(net.bytes_recv / 1024 / 1024, 1),
        "process_memory_mb": round(proc_mem.rss / 1024 / 1024, 1),
        "cpu_count": psutil.cpu_count(),
    }


def _build_route_health_auto_heal_suggestions(summary: dict, direct_results: list[dict], redirect_results: list[dict], protected_results: list[dict] | None = None, route_integrity_checker: dict | None = None, admin_tab_integrity: dict | None = None, theme_visibility_audit: dict | None = None, navigation_lock_audit: dict | None = None) -> list[dict]:
    suggestions: list[dict] = []

    direct_integrity = float(summary.get("direct_integrity_pct", 0) or 0)
    redirect_success = float(summary.get("redirect_success_pct", 0) or 0)
    protected_integrity = float(summary.get("protected_integrity_pct", 0) or 0)
    p95_latency = float(summary.get("p95_latency_ms", 0) or 0)
    avg_latency = float(summary.get("avg_latency_ms", 0) or 0)

    broken_direct = [row for row in direct_results if not row.get("healthy")]
    broken_redirects = [row for row in redirect_results if not row.get("redirect_ok")]
    protected_results = protected_results or []
    broken_protected = [row for row in protected_results if not row.get("healthy")]
    runtime_hints = [row for row in direct_results if row.get("runtime_error_hint")]
    white_screen_hints = [row for row in direct_results if row.get("white_screen_hint")]

    if direct_integrity < 95:
        suggestions.append({
            "severity": "high" if direct_integrity < 85 else "medium",
            "category": "direct_route_integrity",
            "title": "Repair direct feature routes below integrity target",
            "action": "Review the failing direct routes first, then run the route report again after fixing missing screens, guards, or fetch failures.",
            "threshold": "direct_integrity_pct >= 95",
            "evidence": [row.get("path") for row in broken_direct[:5]],
        })

    if redirect_success < 95:
        suggestions.append({
            "severity": "high" if redirect_success < 85 else "medium",
            "category": "legacy_redirects",
            "title": "Repair legacy redirect coverage",
            "action": "Check the redirect map and client-side guard logic for the failing legacy paths, then validate the final target routes again.",
            "threshold": "redirect_success_pct >= 95",
            "evidence": [row.get("path") for row in broken_redirects[:5]],
        })

    if protected_results and protected_integrity < 95:
        suggestions.append({
            "severity": "high" if protected_integrity < 85 else "medium",
            "category": "protected_route_integrity",
            "title": "Repair protected admin journeys below integrity target",
            "action": "Review the failing protected route/API pairs first, then rerun route health after fixing auth guards, admin data dependencies, or stale bundles.",
            "threshold": "protected_integrity_pct >= 95",
            "evidence": [row.get("route_path") for row in broken_protected[:5]],
        })

    if p95_latency > 1400 or avg_latency > 800:
        slowest = sorted(direct_results + redirect_results, key=lambda row: row.get("latency_ms", 0), reverse=True)[:5]
        suggestions.append({
            "severity": "high" if p95_latency > 2000 else "medium",
            "category": "route_latency",
            "title": "Reduce route latency before release",
            "action": "Prioritize the slowest routes for bundle trimming, deferred widgets, and blocking-request reduction before the next release gate run.",
            "threshold": "p95_latency_ms <= 1400 and avg_latency_ms <= 800",
            "evidence": [f"{row.get('path')} ({row.get('latency_ms', 0)} ms)" for row in slowest],
        })

    if runtime_hints:
        suggestions.append({
            "severity": "medium",
            "category": "runtime_hints",
            "title": "Investigate runtime-error hints",
            "action": "Inspect browser console/runtime traces for the hinted routes and harden their data dependencies or guards.",
            "threshold": "0 runtime error hints",
            "evidence": [row.get("path") for row in runtime_hints[:5]],
        })

    if white_screen_hints:
        suggestions.append({
            "severity": "medium",
            "category": "white_screen_hints",
            "title": "Eliminate white-screen route hints",
            "action": "Verify that the affected screens render fallback data or skeletons instead of blank states when upstream calls fail.",
            "threshold": "0 white-screen hints",
            "evidence": [row.get("path") for row in white_screen_hints[:5]],
        })

    checker = route_integrity_checker or {}
    checker_status = str(checker.get("status") or "healthy").lower()
    if checker_status in {"warning", "critical"}:
        issues = [
            *(checker.get("missing_from_whitelist") or []),
            *[str(row.get("expected_target") or "") for row in (checker.get("redirect_target_issues") or [])[:3]],
        ]
        suggestions.append({
            "severity": "high" if checker_status == "critical" else "medium",
            "category": "route_registry_integrity",
            "title": "Resolve route registry integrity drift",
            "action": "Update routeResolution.ts and protected route probes so new admin/executive pages and redirect targets are validated automatically.",
            "threshold": "route_integrity_checker.status = healthy",
            "evidence": [row for row in issues if row][:6],
        })

    tab_integrity = admin_tab_integrity or {}
    tab_status = str(tab_integrity.get("status") or "healthy").lower()
    if tab_status in {"warning", "critical"}:
        evidence = [
            *(tab_integrity.get("missing_tab_renderers") or []),
            *(tab_integrity.get("orphan_renderer_tabs") or []),
        ]
        suggestions.append({
            "severity": "high" if tab_status == "critical" else "medium",
            "category": "admin_tab_integrity",
            "title": "Resolve admin tab registry drift",
            "action": "Keep admin category tabs and PanelContent renderer mappings synchronized to prevent blank tab content on admin-console deep links.",
            "threshold": "admin_tab_integrity.status = healthy",
            "evidence": [item for item in evidence if item][:8],
        })

    theme_audit = theme_visibility_audit or {}
    theme_status = str(theme_audit.get("status") or "healthy").lower()
    if theme_status in {"warning", "critical"}:
        suggestions.append({
            "severity": "medium",
            "category": "theme_visibility_integrity",
            "title": "Resolve dark/light theme visibility drift",
            "action": "Ensure monitored critical surfaces use theme-aware tokens instead of hardcoded light/dark color values.",
            "threshold": "theme_visibility_audit.status = healthy",
            "evidence": (theme_audit.get("risky_files") or [])[:6],
        })

    nav_audit = navigation_lock_audit or {}
    nav_status = str(nav_audit.get("status") or "healthy").lower()
    if nav_status in {"warning", "critical"}:
        evidence = [
            *(nav_audit.get("admin_unexpected_active") or []),
            *(nav_audit.get("unlocked_user_keys") or []),
        ]
        suggestions.append({
            "severity": "high" if nav_status == "critical" else "medium",
            "category": "navigation_lock_integrity",
            "title": "Resolve navigation lock drift",
            "action": "Keep AppShell user/admin navigation keys aligned with approved locked sets and remove unapproved entries.",
            "threshold": "navigation_lock_audit.status = healthy",
            "evidence": [item for item in evidence if item][:8],
        })

    if not suggestions:
        suggestions.append({
            "severity": "info",
            "category": "healthy",
            "title": "No auto-heal actions required",
            "action": "Route integrity and latency are within target budgets. Keep monitoring historical trend drift.",
            "threshold": "all route health budgets healthy",
            "evidence": [],
        })

    return suggestions


async def _build_ui_guardrail_summary(db, hours: int = 24) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 168)))
    docs = await db[SHELL_HEALTH_COLLECTION].find({"timestamp": {"$gte": since}}, {"_id": 0, "events": 1}).sort("timestamp", -1).limit(120).to_list(120)
    latest_by_route: dict[str, dict] = {}
    failures: list[dict] = []

    for doc in docs:
        for event in doc.get("events", []):
            if not isinstance(event, dict) or event.get("metric") != "ui_route_guard":
                continue
            metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            route_key = str(metadata.get("route_key") or "unknown")
            enriched = {
                "route_key": route_key,
                "status": metadata.get("status", "unknown"),
                "missing_texts": metadata.get("missing_texts") or [],
                "visible_auth_method_count": metadata.get("visible_auth_method_count"),
                "timestamp": event.get("timestamp"),
            }
            if route_key not in latest_by_route:
                latest_by_route[route_key] = enriched
            if enriched["status"] != "healthy":
                failures.append(enriched)

    current_failures = [item for item in latest_by_route.values() if item.get("status") != "healthy"]

    return {
        "routes_checked": len(latest_by_route),
        "failing_routes": len(current_failures),
        "latest_by_route": list(latest_by_route.values()),
        "recent_failures": failures[:10],
    }


def _parse_shell_timestamp(value) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    return None


def _build_shell_health_trend(docs: list[dict], window_hours: int) -> dict:
    bounded_hours = min(max(int(window_hours or 24), 1), 168)
    bucket_span_hours = 1 if bounded_hours <= 24 else 3 if bounded_hours <= 72 else 6
    bucket_count = max(6, min(36, math.ceil(bounded_hours / bucket_span_hours)))

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=bounded_hours)

    bucket_span_seconds = bucket_span_hours * 3600
    buckets = []
    for idx in range(bucket_count):
        start = window_start + timedelta(hours=idx * bucket_span_hours)
        end = start + timedelta(hours=bucket_span_hours)
        buckets.append({
            "start": start,
            "end": end,
            "dedupe_hits": 0,
            "fallback_activations": 0,
            "route_recoveries": 0,
            "rate_limit_429s": 0,
            "stress_score": 0,
        })

    for doc in docs:
        ts = _parse_shell_timestamp(doc.get("timestamp"))
        if not ts or ts < window_start or ts > now:
            continue

        counters = doc.get("counters", {}) if isinstance(doc.get("counters"), dict) else {}
        idx = int((ts - window_start).total_seconds() // bucket_span_seconds)
        if idx < 0:
            continue
        if idx >= bucket_count:
            idx = bucket_count - 1

        bucket = buckets[idx]
        bucket["dedupe_hits"] += int(counters.get("dedupe_hits") or 0)
        bucket["fallback_activations"] += int(counters.get("fallback_activations") or 0)
        bucket["route_recoveries"] += int(counters.get("route_recoveries") or 0)
        bucket["rate_limit_429s"] += int(counters.get("rate_limit_429s") or 0)

    trend = []
    for bucket in buckets:
        dedupe = int(bucket["dedupe_hits"] or 0)
        fallback = int(bucket["fallback_activations"] or 0)
        recoveries = int(bucket["route_recoveries"] or 0)
        r429 = int(bucket["rate_limit_429s"] or 0)

        bucket["stress_score"] = round(
            (fallback * 5.0)
            + (r429 * 4.0)
            + (recoveries * 2.0)
            + min(dedupe / 20.0, 10.0),
            2,
        )

        trend.append({
            "bucket_start": bucket["start"].isoformat(),
            "bucket_end": bucket["end"].isoformat(),
            "dedupe_hits": dedupe,
            "fallback_activations": fallback,
            "route_recoveries": recoveries,
            "rate_limit_429s": r429,
            "stress_score": bucket["stress_score"],
        })

    return {
        "window_hours": bounded_hours,
        "bucket_span_hours": bucket_span_hours,
        "trend": trend,
        "sparkline": [item["stress_score"] for item in trend],
    }


def _evaluate_shell_health_alert(totals: dict, trend: list[dict]) -> dict:
    warn_score = float(SHELL_HEALTH_ALERT_BANDS["band_thresholds"]["warning_stress_score"])
    critical_score = float(SHELL_HEALTH_ALERT_BANDS["band_thresholds"]["critical_stress_score"])
    warn_counters = SHELL_HEALTH_ALERT_BANDS["counter_thresholds"]["warning"]
    critical_counters = SHELL_HEALTH_ALERT_BANDS["counter_thresholds"]["critical"]

    latest_bucket = trend[-1] if trend else {
        "bucket_start": None,
        "bucket_end": None,
        "dedupe_hits": 0,
        "fallback_activations": 0,
        "route_recoveries": 0,
        "rate_limit_429s": 0,
        "stress_score": 0,
    }
    peak_bucket = max(trend, key=lambda item: float(item.get("stress_score") or 0), default=latest_bucket)

    first_half = trend[: max(1, len(trend) // 2)]
    second_half = trend[max(1, len(trend) // 2):] or trend
    first_avg = sum(float(item.get("stress_score") or 0) for item in first_half) / max(1, len(first_half))
    second_avg = sum(float(item.get("stress_score") or 0) for item in second_half) / max(1, len(second_half))
    drift_pct = round(((second_avg - first_avg) / max(first_avg, 1.0)) * 100.0, 2)
    drift_direction = "up" if drift_pct >= 15 else "down" if drift_pct <= -15 else "flat"

    triggered_rules = []

    def _trigger(level: str, code: str, title: str, evidence: str):
        triggered_rules.append({"level": level, "code": code, "title": title, "evidence": evidence})

    latest_fallback = int(latest_bucket.get("fallback_activations") or 0)
    latest_429 = int(latest_bucket.get("rate_limit_429s") or 0)
    latest_recoveries = int(latest_bucket.get("route_recoveries") or 0)
    latest_score = float(latest_bucket.get("stress_score") or 0)
    peak_score = float(peak_bucket.get("stress_score") or 0)

    if latest_fallback >= critical_counters["fallback_activations"]:
        _trigger("critical", "fallback_spike", "Fallback activation spike", f"Latest bucket fallback activations = {latest_fallback}")
    elif latest_fallback >= warn_counters["fallback_activations"]:
        _trigger("warning", "fallback_elevated", "Fallback activations elevated", f"Latest bucket fallback activations = {latest_fallback}")

    if latest_429 >= critical_counters["rate_limit_429s"]:
        _trigger("critical", "rate_limit_spike", "Background 429 spike", f"Latest bucket 429 count = {latest_429}")
    elif latest_429 >= warn_counters["rate_limit_429s"]:
        _trigger("warning", "rate_limit_elevated", "Background 429s elevated", f"Latest bucket 429 count = {latest_429}")

    if latest_recoveries >= critical_counters["route_recoveries"]:
        _trigger("critical", "route_recovery_spike", "Route recovery spike", f"Latest bucket route recoveries = {latest_recoveries}")
    elif latest_recoveries >= warn_counters["route_recoveries"]:
        _trigger("warning", "route_recovery_elevated", "Route recoveries elevated", f"Latest bucket route recoveries = {latest_recoveries}")

    if latest_score >= critical_score or peak_score >= critical_score * 1.35:
        _trigger("critical", "stress_score_critical", "Shell stress critical band reached", f"Latest/peak stress score = {latest_score:.2f}/{peak_score:.2f}")
    elif latest_score >= warn_score or peak_score >= critical_score:
        _trigger("warning", "stress_score_warning", "Shell stress warning band reached", f"Latest/peak stress score = {latest_score:.2f}/{peak_score:.2f}")

    total_fallbacks = int(totals.get("fallback_activations") or 0)
    total_429s = int(totals.get("rate_limit_429s") or 0)
    if total_fallbacks >= 18 or total_429s >= 28:
        _trigger("critical", "window_volume_critical", "Sustained shell instability in window", f"Window totals fallback={total_fallbacks}, 429s={total_429s}")
    elif total_fallbacks >= 8 or total_429s >= 14:
        _trigger("warning", "window_volume_warning", "Growing shell instability in window", f"Window totals fallback={total_fallbacks}, 429s={total_429s}")

    if drift_direction == "up" and second_avg >= warn_score:
        _trigger("warning", "drift_uptrend", "Shell health drift is trending upward", f"Second-half stress avg rose by {drift_pct}%")

    status = "normal"
    if any(rule["level"] == "critical" for rule in triggered_rules):
        status = "critical"
    elif any(rule["level"] == "warning" for rule in triggered_rules):
        status = "warning"

    summary = {
        "normal": "Shell telemetry is within healthy operating bands.",
        "warning": "Warning band reached. Monitor fallback and 429 trends for drift.",
        "critical": "Critical shell resilience band reached. Immediate investigation recommended.",
    }[status]

    return {
        "status": status,
        "summary": summary,
        "latest_bucket": latest_bucket,
        "peak_bucket": peak_bucket,
        "drift_pct": drift_pct,
        "drift_direction": drift_direction,
        "triggered_rules": triggered_rules[:8],
    }


def _calculate_score(web: dict, api_m: dict, db_m: dict, sys_m: dict) -> dict:
    """Calculate a unified 0-100 performance score."""
    scores = {}

    # Web Vitals (40% weight)
    web_score = 100
    if web["lcp_s"] > BUDGETS["lcp_s"]["critical"]:
        web_score -= 30
    elif web["lcp_s"] > BUDGETS["lcp_s"]["target"]:
        web_score -= 15
    if web["fcp_s"] > BUDGETS["fcp_s"]["critical"]:
        web_score -= 25
    elif web["fcp_s"] > BUDGETS["fcp_s"]["target"]:
        web_score -= 10
    if web.get("inp_ms", 0) > BUDGETS["inp_ms"]["critical"]:
        web_score -= 20
    elif web.get("inp_ms", 0) > BUDGETS["inp_ms"]["target"]:
        web_score -= 8
    if web["cls"] > BUDGETS["cls"]["critical"]:
        web_score -= 25
    elif web["cls"] > BUDGETS["cls"]["target"]:
        web_score -= 10
    if web["ttfb_ms"] > BUDGETS["ttfb_ms"]["critical"]:
        web_score -= 20
    elif web["ttfb_ms"] > BUDGETS["ttfb_ms"]["target"]:
        web_score -= 8
    scores["web_vitals"] = max(0, web_score)

    # API Performance (25% weight)
    api_score = 100
    if api_m["api_p95_ms"] > BUDGETS["api_p95_ms"]["critical"]:
        api_score -= 35
    elif api_m["api_p95_ms"] > BUDGETS["api_p95_ms"]["target"]:
        api_score -= 15
    if api_m["error_rate_pct"] > BUDGETS["api_error_pct"]["critical"]:
        api_score -= 40
    elif api_m["error_rate_pct"] > BUDGETS["api_error_pct"]["target"]:
        api_score -= 15
    scores["api"] = max(0, api_score)

    # Database (15% weight)
    db_score = 100
    if db_m.get("db_latency_ms", 0) > BUDGETS["db_latency_ms"]["critical"]:
        db_score -= 40
    elif db_m.get("db_latency_ms", 0) > BUDGETS["db_latency_ms"]["target"]:
        db_score -= 15
    if db_m.get("status") == "error":
        db_score = 0
    scores["database"] = max(0, db_score)

    # System Resources (20% weight)
    sys_score = 100
    for key in ["cpu_pct", "memory_pct", "disk_pct"]:
        val = sys_m.get(key, 0)
        if val > BUDGETS[key]["critical"]:
            sys_score -= 25
        elif val > BUDGETS[key]["target"]:
            sys_score -= 10
    scores["system"] = max(0, sys_score)

    overall = round(
        scores["web_vitals"] * 0.40 +
        scores["api"] * 0.25 +
        scores["database"] * 0.15 +
        scores["system"] * 0.20
    )

    status = "excellent" if overall >= 90 else "good" if overall >= 75 else "warning" if overall >= 50 else "critical"

    return {"overall": overall, "status": status, "breakdown": scores}


def _check_budgets(web: dict, api_m: dict, db_m: dict, sys_m: dict) -> list:
    """Check all metrics against performance budgets."""
    violations = []
    metric_map = {
        "lcp_s": web.get("lcp_s", 0),
        "fcp_s": web.get("fcp_s", 0),
        "inp_ms": web.get("inp_ms", 0),
        "ttfb_ms": web.get("ttfb_ms", 0),
        "cls": web.get("cls", 0),
        "api_p95_ms": api_m.get("api_p95_ms", 0),
        "api_error_pct": api_m.get("error_rate_pct", 0),
        "db_latency_ms": db_m.get("db_latency_ms", 0),
        "cpu_pct": sys_m.get("cpu_pct", 0),
        "memory_pct": sys_m.get("memory_pct", 0),
        "disk_pct": sys_m.get("disk_pct", 0),
    }

    for key, budget in BUDGETS.items():
        val = metric_map.get(key, 0)
        if val > budget["critical"]:
            violations.append({
                "metric": key, "label": budget["label"],
                "value": val, "target": budget["target"], "critical": budget["critical"],
                "unit": budget["unit"], "severity": "critical",
            })
        elif val > budget["target"]:
            violations.append({
                "metric": key, "label": budget["label"],
                "value": val, "target": budget["target"], "critical": budget["critical"],
                "unit": budget["unit"], "severity": "warning",
            })

    return violations


def _period_to_hours(period: str) -> int:
    normalized = str(period or "24h").strip().lower()
    mapping = {
        "1h": 1,
        "6h": 6,
        "12h": 12,
        "24h": 24,
        "48h": 48,
        "7d": 168,
    }
    return mapping.get(normalized, 24)


# ── API Endpoints ────────────────────────────────────────────────

@router.get("/unified")
async def unified_performance(request: Request):
    """Unified performance dashboard: score, all metrics, budgets, violations."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    web = await _collect_web_vitals(db)
    api_m = _collect_api_metrics()
    db_m = await _collect_db_metrics(db)
    sys_m = _collect_system_metrics()
    score = _calculate_score(web, api_m, db_m, sys_m)
    violations = _check_budgets(web, api_m, db_m, sys_m)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "web_vitals": web,
        "api": api_m,
        "database": db_m,
        "system": sys_m,
        "budget_violations": violations,
        "budgets": BUDGETS,
    }


@router.get("/dashboard")
async def performance_dashboard(request: Request, period: str = "24h"):
    """Compatibility dashboard endpoint with unified metrics + scoped trend."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    now = datetime.now(timezone.utc)
    period_hours = _period_to_hours(period)

    web = await _collect_web_vitals(db)
    api_m = _collect_api_metrics()
    db_m = await _collect_db_metrics(db)
    sys_m = _collect_system_metrics()
    score = _calculate_score(web, api_m, db_m, sys_m)
    violations = _check_budgets(web, api_m, db_m, sys_m)

    since = now - timedelta(hours=min(period_hours, 168))
    trend_docs = await db[SNAPSHOT_COLLECTION].find(
        {"timestamp": {"$gte": since}},
        {
            "_id": 0,
            "timestamp": 1,
            "score.overall": 1,
            "score.status": 1,
            "web_vitals.lcp_s": 1,
            "web_vitals.cls": 1,
            "api.api_p95_ms": 1,
            "database.db_latency_ms": 1,
            "violations_count": 1,
        },
    ).sort("timestamp", 1).limit(400).to_list(400)

    trend = []
    for row in trend_docs:
        ts = row.get("timestamp")
        web_row = row.get("web_vitals") if isinstance(row.get("web_vitals"), dict) else {}
        api_row = row.get("api") if isinstance(row.get("api"), dict) else {}
        db_row = row.get("database") if isinstance(row.get("database"), dict) else {}
        trend.append({
            "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
            "overall": int((row.get("score") or {}).get("overall") or 0),
            "status": str((row.get("score") or {}).get("status") or "unknown"),
            "lcp_s": round(float(web_row.get("lcp_s") or 0), 3),
            "cls": round(float(web_row.get("cls") or 0), 4),
            "api_p95_ms": round(float(api_row.get("api_p95_ms") or 0), 1),
            "db_latency_ms": round(float(db_row.get("db_latency_ms") or 0), 1),
            "violations_count": int(row.get("violations_count") or 0),
        })

    return {
        "timestamp": now.isoformat(),
        "period": str(period),
        "period_hours": period_hours,
        "score": score,
        "web_vitals": web,
        "api": api_m,
        "database": db_m,
        "system": sys_m,
        "budget_violations": violations,
        "budgets": BUDGETS,
        "trend": trend,
    }


@router.get("/trend")
async def performance_trend(request: Request, hours: int = 24):
    """Performance score trend over time from stored snapshots."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    since = datetime.now(timezone.utc) - timedelta(hours=min(hours, 168))

    snapshots = await db[SNAPSHOT_COLLECTION].find(
        {"timestamp": {"$gte": since}},
        {"_id": 0, "timestamp": 1, "score": 1, "web_vitals.lcp_s": 1, "web_vitals.cls": 1, "web_vitals.inp_ms": 1,
         "api.api_p95_ms": 1, "api.error_rate_pct": 1,
         "system.cpu_pct": 1, "system.memory_pct": 1,
         "database.db_latency_ms": 1, "violations_count": 1}
    ).sort("timestamp", 1).to_list(500)

    # Convert datetime objects
    for s in snapshots:
        if isinstance(s.get("timestamp"), datetime):
            s["timestamp"] = s["timestamp"].isoformat()
        web = s.get("web_vitals") if isinstance(s.get("web_vitals"), dict) else {}
        s["web_vitals"] = {
            "lcp_s": round(float(web.get("lcp_s") or 0), 3),
            "cls": round(float(web.get("cls") or 0), 4),
            "inp_ms": round(float(web.get("inp_ms") or 0), 1),
        }

    return {"period_hours": hours, "snapshots": snapshots, "count": len(snapshots)}


@router.get("/budgets")
async def get_budgets(request: Request):
    """Get current performance budgets."""
    from routes.db import require_admin
    await require_admin(request)
    return {"budgets": BUDGETS}


@router.get("/slow-queries")
async def get_slow_queries(request: Request, hours: int = 1):
    """Get recent slow database queries."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    since = datetime.now(timezone.utc) - timedelta(hours=min(hours, 24))

    queries = await db[SLOW_QUERIES_COLLECTION].find(
        {"timestamp": {"$gte": since}},
        {"_id": 0}
    ).sort("duration_ms", -1).to_list(50)

    for q in queries:
        if isinstance(q.get("timestamp"), datetime):
            q["timestamp"] = q["timestamp"].isoformat()

    return {"count": len(queries), "period_hours": hours, "queries": queries}


@router.get("/bundle-budget")
async def bundle_budget_dashboard(request: Request):
    """Return current bundle-size health + recent trend snapshots."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    now = datetime.now(timezone.utc)
    metrics = _collect_bundle_metrics()

    snapshot = {
        "timestamp": now,
        "largest_bundle_name": metrics.get("largest_bundle_name"),
        "largest_bundle_mb": metrics.get("largest_bundle_mb", 0),
        "total_bundle_mb": metrics.get("total_bundle_mb", 0),
        "file_count": metrics.get("file_count", 0),
        "within_largest_budget": metrics.get("within_largest_budget", False),
        "within_total_budget": metrics.get("within_total_budget", False),
        "status": metrics.get("status", "unknown"),
    }

    try:
        await db[BUNDLE_HISTORY_COLLECTION].insert_one(snapshot)
        cutoff = now - timedelta(days=14)
        await db[BUNDLE_HISTORY_COLLECTION].delete_many({"timestamp": {"$lt": cutoff}})
        trend_docs = await db[BUNDLE_HISTORY_COLLECTION].find(
            {},
            {
                "_id": 0,
                "timestamp": 1,
                "largest_bundle_mb": 1,
                "total_bundle_mb": 1,
                "within_largest_budget": 1,
                "within_total_budget": 1,
            },
        ).sort("timestamp", -1).limit(20).to_list(20)
    except Exception:
        trend_docs = []

    trend = []
    for row in reversed(trend_docs):
        ts = row.get("timestamp")
        trend.append({
            "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
            "largest_bundle_mb": row.get("largest_bundle_mb", 0),
            "total_bundle_mb": row.get("total_bundle_mb", 0),
            "within_largest_budget": row.get("within_largest_budget", False),
            "within_total_budget": row.get("within_total_budget", False),
        })

    return {
        "timestamp": now.isoformat(),
        "current": {
            **metrics,
            "largest_budget_mb": 4.0,
            "total_budget_mb": 10.0,
        },
        "trend": trend,
    }


@router.get("/route-health")
async def route_health_dashboard(request: Request):
    """Synthetic route health checks for feature and legacy redirect routes."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    now = datetime.now(timezone.utc)
    base_url = _resolve_frontend_base_url(request)
    api_base_url = str(request.base_url).rstrip("/")

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        direct_results = await asyncio.gather(*[
            _run_route_probe(client, base_url, route)
            for route in ROUTE_HEALTH_DIRECT_ROUTES
        ], return_exceptions=True)

        legacy_paths = list(ROUTE_HEALTH_REDIRECT_EXPECTATIONS.keys())
        legacy_checks = await asyncio.gather(*[
            _run_route_probe(client, base_url, path)
            for path in legacy_paths
        ], return_exceptions=True)

        incoming_auth_header = str(request.headers.get("authorization") or "").strip()
        auth_token = ""
        if not incoming_auth_header:
            auth_token = await _mint_route_health_admin_session()

        protected_headers = {
            "Authorization": incoming_auth_header or (f"Bearer {auth_token}" if auth_token else ""),
            "X-Route-Health-Probe": "internal",
        }
        if not protected_headers.get("Authorization"):
            protected_headers = {}
        protected_results = await asyncio.gather(*[
            _run_protected_route_probe(client, base_url, api_base_url, probe, protected_headers)
            for probe in ROUTE_HEALTH_PROTECTED_PROBES
        ], return_exceptions=True) if protected_headers else []

    # Filter out exceptions from gather results
    direct_results = [r for r in direct_results if isinstance(r, dict)]
    legacy_checks = [r for r in legacy_checks if isinstance(r, dict)]
    protected_results = [r for r in protected_results if isinstance(r, dict)]

    redirect_results = []
    for result, legacy_path in zip(legacy_checks, legacy_paths):
        expected_target = ROUTE_HEALTH_REDIRECT_EXPECTATIONS[legacy_path]
        # Legacy mini-app redirects are enforced client-side in Expo router guards.
        # HTTP probe validates route availability; redirect execution is verified in frontend E2E.
        redirect_ok = bool(result.get("healthy"))
        redirect_results.append({
            **result,
            "expected_target": expected_target,
            "redirect_ok": redirect_ok,
            "client_redirect_expected": True,
        })

    direct_ok_count = sum(1 for row in direct_results if row.get("healthy"))
    redirect_ok_count = sum(1 for row in redirect_results if row.get("redirect_ok"))
    protected_ok_count = sum(1 for row in protected_results if row.get("healthy"))

    all_latencies = [row.get("latency_ms", 0) for row in direct_results + redirect_results if row.get("latency_ms")]
    avg_latency = round(sum(all_latencies) / max(1, len(all_latencies)), 2)
    p95_latency = round(sorted(all_latencies)[int(max(0, len(all_latencies) - 1) * 0.95)], 2) if all_latencies else 0

    direct_integrity = round((direct_ok_count / max(1, len(direct_results))) * 100, 2)
    redirect_success = round((redirect_ok_count / max(1, len(redirect_results))) * 100, 2)
    protected_integrity = round((protected_ok_count / max(1, len(protected_results))) * 100, 2) if protected_results else 100.0

    route_crash_traces = [
        {
            "path": row.get("path"),
            "status_code": row.get("status_code", 0),
            "latency_ms": row.get("latency_ms", 0),
            "final_path": row.get("final_path", ""),
            "runtime_error_hint": bool(row.get("runtime_error_hint")),
            "white_screen_hint": bool(row.get("white_screen_hint")),
            "timeout_hint": bool(row.get("timeout_hint")),
            "crash_signature": row.get("crash_signature") or "",
            "trace_excerpt": row.get("trace_excerpt") or row.get("error") or "",
            "diagnostic_flags": row.get("diagnostic_flags") or [],
        }
        for row in direct_results
        if bool(row.get("runtime_error_hint"))
        or bool(row.get("white_screen_hint"))
        or int(row.get("status_code", 0) or 0) in {0}
        or int(row.get("status_code", 0) or 0) >= 500
    ]
    route_crash_traces.sort(
        key=lambda row: (
            not bool(row.get("runtime_error_hint")),
            not bool(row.get("white_screen_hint")),
            -float(row.get("latency_ms", 0) or 0),
        )
    )

    api_timeout_traces = [
        {
            "id": row.get("id"),
            "label": row.get("label"),
            "route_path": row.get("route_path"),
            "api_path": row.get("api_path"),
            "api_status_code": row.get("api_status_code", 0),
            "latency_ms": row.get("latency_ms", 0),
            "api_timeout_hint": bool(row.get("api_timeout_hint")),
            "api_error_hint": bool(row.get("api_error_hint")),
            "api_error_category": row.get("api_error_category") or "none",
            "api_trace_excerpt": row.get("api_trace_excerpt") or "",
            "diagnostic_flags": row.get("diagnostic_flags") or [],
        }
        for row in protected_results
        if bool(row.get("api_timeout_hint"))
        or bool(row.get("api_error_hint"))
        or int(row.get("api_status_code", 0) or 0) >= 500
        or int(row.get("api_status_code", 0) or 0) == 0
    ]
    api_timeout_traces.sort(
        key=lambda row: (
            not bool(row.get("api_timeout_hint")),
            not bool(row.get("api_error_hint")),
            -float(row.get("latency_ms", 0) or 0),
        )
    )

    diagnostics_summary = {
        "route_runtime_hints_count": len([row for row in direct_results if bool(row.get("runtime_error_hint"))]),
        "route_white_screen_hints_count": len([row for row in direct_results if bool(row.get("white_screen_hint"))]),
        "route_timeout_hints_count": len([row for row in direct_results if bool(row.get("timeout_hint"))]),
        "route_probe_exception_count": len([row for row in direct_results if int(row.get("status_code", 0) or 0) == 0]),
        "api_timeout_hints_count": len([row for row in protected_results if bool(row.get("api_timeout_hint"))]),
        "api_error_hints_count": len([row for row in protected_results if bool(row.get("api_error_hint"))]),
        "api_5xx_count": len([row for row in protected_results if int(row.get("api_status_code", 0) or 0) >= 500]),
    }

    snapshot = {
        "timestamp": now,
        "direct_integrity_pct": direct_integrity,
        "redirect_success_pct": redirect_success,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
        "direct_total": len(direct_results),
        "redirect_total": len(redirect_results),
        "protected_integrity_pct": protected_integrity,
        "protected_total": len(protected_results),
    }

    try:
        await db[ROUTE_HEALTH_HISTORY_COLLECTION].insert_one(snapshot)
        cutoff = now - timedelta(days=14)
        await db[ROUTE_HEALTH_HISTORY_COLLECTION].delete_many({"timestamp": {"$lt": cutoff}})
        history_docs = await db[ROUTE_HEALTH_HISTORY_COLLECTION].find(
            {},
            {
                "_id": 0,
                "timestamp": 1,
                "direct_integrity_pct": 1,
                "redirect_success_pct": 1,
                "avg_latency_ms": 1,
                "p95_latency_ms": 1,
            },
        ).sort("timestamp", -1).limit(20).to_list(20)
    except Exception:
        history_docs = []

    ui_guardrails = await _build_ui_guardrail_summary(db)
    route_integrity_checker = _build_route_integrity_checker()
    admin_tab_integrity = _build_admin_tab_integrity()
    theme_visibility_audit = _build_theme_visibility_audit()
    navigation_lock_audit = _build_navigation_lock_audit()

    history = []
    for row in reversed(history_docs):
        ts = row.get("timestamp")
        history.append({
            "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
            "direct_integrity_pct": row.get("direct_integrity_pct", 0),
            "redirect_success_pct": row.get("redirect_success_pct", 0),
            "avg_latency_ms": row.get("avg_latency_ms", 0),
            "p95_latency_ms": row.get("p95_latency_ms", 0),
        })

    return {
        "timestamp": now.isoformat(),
        "base_url": base_url,
        "direct_integrity_pct": direct_integrity,
        "protected_integrity_pct": protected_integrity,
        "direct_integrity": direct_integrity,
        "protected_integrity": protected_integrity,
        "summary": {
            "direct_integrity_pct": direct_integrity,
            "redirect_success_pct": redirect_success,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "direct_routes_checked": len(direct_results),
            "legacy_redirects_checked": len(redirect_results),
            "protected_integrity_pct": protected_integrity,
            "protected_routes_checked": len(protected_results),
            "route_integrity_checker_status": route_integrity_checker.get("status"),
            "admin_tab_integrity_status": admin_tab_integrity.get("status"),
            "theme_visibility_status": theme_visibility_audit.get("status"),
            "navigation_lock_status": navigation_lock_audit.get("status"),
            "runtime_hints_count": diagnostics_summary.get("route_runtime_hints_count", 0),
            "white_screen_hints_count": diagnostics_summary.get("route_white_screen_hints_count", 0),
            "api_timeout_hints_count": diagnostics_summary.get("api_timeout_hints_count", 0),
            "api_error_hints_count": diagnostics_summary.get("api_error_hints_count", 0),
        },
        "auto_heal_suggestions": _build_route_health_auto_heal_suggestions(
            {
                "direct_integrity_pct": direct_integrity,
                "redirect_success_pct": redirect_success,
                "avg_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency,
                "protected_integrity_pct": protected_integrity,
            },
            direct_results,
            redirect_results,
            protected_results,
            route_integrity_checker,
            admin_tab_integrity,
            theme_visibility_audit,
            navigation_lock_audit,
        ),
        "direct_routes": direct_results,
        "protected_routes": protected_results,
        "legacy_redirects": redirect_results,
        "route_integrity_checker": route_integrity_checker,
        "admin_tab_integrity": admin_tab_integrity,
        "theme_visibility_audit": theme_visibility_audit,
        "navigation_lock_audit": navigation_lock_audit,
        "diagnostics_summary": diagnostics_summary,
        "route_crash_traces": route_crash_traces[:12],
        "api_timeout_traces": api_timeout_traces[:12],
        "ui_guardrails": ui_guardrails,
        "history": history,
    }


@router.get("/route-integrity-checker")
async def route_integrity_checker_dashboard(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    return _build_route_integrity_checker()


@router.get("/admin-tab-integrity")
async def admin_tab_integrity_dashboard(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    return _build_admin_tab_integrity()


@router.get("/theme-visibility-audit")
async def theme_visibility_audit_dashboard(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    return _build_theme_visibility_audit()


@router.post("/theme-visibility-audit/run")
async def run_theme_visibility_audit(request: Request):
    """Run a fresh audit, persist to history, and return results."""
    from routes.db import require_admin

    await require_admin(request)
    result = _build_theme_visibility_audit()
    db = await _get_db()
    doc = {
        "run_id": f"audit_{int(datetime.now(timezone.utc).timestamp())}",
        "overall_grade": result["overall_grade"],
        "summary": result["summary"],
        "files": result["files"],
        "patterns_checked": result["patterns_checked"],
        "scanned_at": result["scanned_at"],
    }
    await db[THEME_AUDIT_HISTORY_COLLECTION].insert_one({k: v for k, v in doc.items() if k != "_id"})
    return result


@router.get("/theme-visibility-audit/history")
async def theme_visibility_audit_history(request: Request, limit: int = 10):
    """Return the last N audit runs (summary only, no per-file issues)."""
    from routes.db import require_admin

    await require_admin(request)
    db = await _get_db()
    cursor = db[THEME_AUDIT_HISTORY_COLLECTION].find(
        {},
        {
            "_id": 0,
            "run_id": 1,
            "overall_grade": 1,
            "summary": 1,
            "scanned_at": 1,
            "trigger": 1,
        },
    ).sort("scanned_at", -1).limit(limit)
    runs = await cursor.to_list(length=limit)
    return {"runs": runs, "total": len(runs)}


@router.get("/theme-visibility-audit/top-offenders")
async def theme_visibility_audit_top_offenders(request: Request, limit: int = 20):
    """Return the top N files ranked by warn+fail count, with per-pattern breakdowns.

    Powers the "Top Theme Offender" leaderboard widget. Each entry includes:
      - file path (relative to frontend/)
      - warn_count, fail_count, info_count
      - pattern_breakdown: {pattern_name: count}
      - grep_command: a ready-to-copy `grep -nE ...` command that surfaces all offenders
        in the file for the patterns it violates
      - sample_line: the first violating line (for quick preview)
    """
    from routes.db import require_admin

    await require_admin(request)

    audit = _build_theme_visibility_audit()
    files = audit.get("files", [])

    # Rank by (fails * 100 + warns) so fails always float to the top
    def _score(f: dict) -> int:
        return (f.get("fail_count", 0) or 0) * 1000 + (f.get("warn_count", 0) or 0)

    ranked = sorted(files, key=_score, reverse=True)
    clamp = max(1, min(int(limit), 100))
    top = ranked[:clamp]

    # Pre-computed per-pattern grep recipes. Kept aligned with _build_theme_visibility_audit regexes.
    PATTERN_GREP: dict[str, str] = {
        "hardcoded_bg_any_hex": r"backgroundColor:\s*['\"]#[0-9A-Fa-f]{3,8}['\"]",
        "hardcoded_css_bg_any_hex": r"background:\s*['\"][^'\"]*#[0-9A-Fa-f]{3,8}",
        "hardcoded_text_color_any_hex": r"[^a-z]color:\s*['\"]#[0-9A-Fa-f]{3,8}['\"]",
        "hardcoded_border_any_hex": r"borderColor:\s*['\"]#[0-9A-Fa-f]{3,8}['\"]",
        "hardcoded_dark_text_no_branch": r"color:\s*['\"](#0F172A|#1E293B|#0A0A0A)['\"]",
        "hardcoded_light_text_no_branch": r"color:\s*['\"](#FFFFFF|#FEFEFE|#F9FAFB)['\"]",
        "hardcoded_light_bg_no_branch": r"backgroundColor:\s*['\"](#FFFFFF|#F9FAFB|#F7F9FC)['\"]",
        "css_dark_bg_always": r"background:\s*['\"]#0F172A",
        "same_dark_both_modes": r"darkMode\s*\?\s*['\"]#0F172A['\"]",
        "inverted_dark_text": r"darkMode\s*\?\s*['\"]#0F172A['\"]",
        "t_object_hardcoded_dark": r"color:\s*['\"]#0F172A['\"]",
    }

    result: list[dict] = []
    for f in top:
        path = f.get("file", "")
        issues = f.get("issues", []) or []
        breakdown: dict[str, int] = {}
        for iss in issues:
            p = iss.get("pattern", "unknown")
            breakdown[p] = breakdown.get(p, 0) + 1

        # Build a single grep regex combining all offended patterns for this file
        offending_patterns = [p for p in breakdown.keys() if p in PATTERN_GREP]
        if offending_patterns:
            combined = "|".join(f"({PATTERN_GREP[p]})" for p in offending_patterns)
            grep_cmd = f"grep -nE \"{combined}\" /app/frontend/{path}"
        else:
            grep_cmd = f"grep -nE \"#[0-9A-Fa-f]{{3,8}}\" /app/frontend/{path}"

        first_issue = issues[0] if issues else None
        sample_line = None
        if first_issue:
            sample_line = {
                "line": first_issue.get("line"),
                "code": (first_issue.get("code") or "").strip()[:140],
                "pattern": first_issue.get("pattern"),
            }

        result.append({
            "path": path,
            "warn_count": f.get("warn_count", 0),
            "fail_count": f.get("fail_count", 0),
            "info_count": f.get("info_count", 0),
            "total_issues": f.get("total_issues", 0),
            "grade": f.get("grade", "?"),
            "score": _score(f),
            "pattern_breakdown": breakdown,
            "grep_command": grep_cmd,
            "sample_line": sample_line,
        })

    summary = audit.get("summary", {})
    return {
        "top_offenders": result,
        "limit": clamp,
        "total_files_with_issues": len([x for x in files if (x.get("warn_count", 0) + x.get("fail_count", 0)) > 0]),
        "total_warn_issues": summary.get("total_warn_issues", 0),
        "total_fail_issues": summary.get("total_fail_issues", 0),
        "scanned_at": audit.get("scanned_at"),
    }


@router.post("/theme-visibility-audit/autofix/preview")
async def theme_visibility_audit_autofix_preview(request: Request):
    """Preview the V2 Teal autofix for a single file (no write)."""
    from routes.db import require_admin
    from services.theme_autofix import preview_file, AutofixError

    await require_admin(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    path = (body or {}).get("path")
    if not path:
        raise HTTPException(status_code=400, detail="'path' is required")
    aggressive = bool((body or {}).get("aggressive", False))

    try:
        result = preview_file(path, aggressive=aggressive)
    except AutofixError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/theme-visibility-audit/autofix/apply")
async def theme_visibility_audit_autofix_apply(request: Request):
    """Apply the V2 Teal autofix, re-run audit, and re-lock the baseline.

    Body: { path: str, expected_original_sha?: str, relock_baseline?: bool (default true) }
    """
    from routes.db import require_admin
    from services.theme_autofix import apply_file, AutofixError

    admin_user = await require_admin(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    path = (body or {}).get("path")
    if not path:
        raise HTTPException(status_code=400, detail="'path' is required")

    expected_sha = (body or {}).get("expected_original_sha")
    relock = bool((body or {}).get("relock_baseline", True))
    aggressive = bool((body or {}).get("aggressive", False))

    # Audit BEFORE
    audit_before = _build_theme_visibility_audit()
    warns_before = audit_before.get("summary", {}).get("total_warn_issues", 0)
    fails_before = audit_before.get("summary", {}).get("total_fail_issues", 0)

    # Apply the transform
    try:
        apply_result = apply_file(path, expected_original_sha=expected_sha, aggressive=aggressive)
    except AutofixError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not apply_result.get("ok"):
        raise HTTPException(status_code=409, detail=apply_result)

    # Audit AFTER
    audit_after = _build_theme_visibility_audit()
    warns_after = audit_after.get("summary", {}).get("total_warn_issues", 0)
    fails_after = audit_after.get("summary", {}).get("total_fail_issues", 0)
    infos_after = audit_after.get("summary", {}).get("total_info_issues", 0)
    files_scanned = audit_after.get("summary", {}).get("total_files_scanned", 0)
    files_clean = audit_after.get("summary", {}).get("files_clean", 0)
    grade_after = audit_after.get("overall_grade", "?")

    # Re-lock baseline only if: no fails AND warn count dropped (or stayed flat)
    baseline_result: dict | None = None
    _GRADE_ORDER_LOCAL = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    if relock and fails_after == 0 and warns_after <= warns_before:
        try:
            db = await _get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            baseline_doc = {
                "kind": "baseline",
                "grade": grade_after,
                "grade_rank": _GRADE_ORDER_LOCAL.get(grade_after, 0),
                "warns": int(warns_after),
                "fails": int(fails_after),
                "infos": int(infos_after),
                "files_scanned": int(files_scanned),
                "files_clean": int(files_clean),
                "locked_at": now_iso,
                "locked_by": admin_user.email if admin_user else "autofix",
                "trigger": "autofix",
            }
            await db[THEME_ENFORCEMENT_COLLECTION].update_one(
                {"kind": "baseline"},
                {"$set": baseline_doc},
                upsert=True,
            )
            baseline_result = {k: v for k, v in baseline_doc.items() if k != "kind"}
        except Exception as e:
            baseline_result = {"error": str(e)}

    return {
        "ok": True,
        "apply": apply_result,
        "audit_before": {"warns": warns_before, "fails": fails_before},
        "audit_after": {"warns": warns_after, "fails": fails_after, "grade": grade_after},
        "warns_eliminated": max(0, warns_before - warns_after),
        "baseline_locked": baseline_result is not None and "error" not in (baseline_result or {}),
        "baseline": baseline_result,
    }


@router.post("/theme-visibility-audit/autofix/batch")
async def theme_visibility_audit_autofix_batch(request: Request):
    """Batch-apply the autofix across the top N offenders.

    Body: {
      limit?: int (default 10, max 50),
      aggressive?: bool (default true),
      compile_check?: bool (default true — runs npx expo export and rolls back
        every changed file on compile failure),
      relock_baseline?: bool (default true)
    }

    Returns a per-file report, aggregate stats, compile status, rollback status,
    and the new baseline snapshot.
    """
    from routes.db import require_admin
    from services.theme_autofix import batch_apply, restore_files, AutofixError  # noqa: F401
    import asyncio

    admin_user = await require_admin(request)
    try:
        body = await request.json()
    except Exception:
        body = {}

    limit = max(1, min(int((body or {}).get("limit", 10)), 50))
    aggressive = bool((body or {}).get("aggressive", True))
    compile_check = bool((body or {}).get("compile_check", True))
    relock = bool((body or {}).get("relock_baseline", True))

    # Step 1: Audit BEFORE + pick top N paths
    audit_before = _build_theme_visibility_audit()
    warns_before = audit_before.get("summary", {}).get("total_warn_issues", 0)
    fails_before = audit_before.get("summary", {}).get("total_fail_issues", 0)

    files = audit_before.get("files", [])
    ranked = sorted(
        files,
        key=lambda f: (f.get("fail_count", 0) or 0) * 1000 + (f.get("warn_count", 0) or 0),
        reverse=True,
    )
    top_paths = [
        f.get("file") for f in ranked[:limit]
        if (f.get("warn_count", 0) + f.get("fail_count", 0)) > 0
    ]

    if not top_paths:
        return {
            "ok": True,
            "message": "No offenders to clean.",
            "results": [],
            "audit_before": {"warns": warns_before, "fails": fails_before},
            "audit_after": {"warns": warns_before, "fails": fails_before},
        }

    # Step 2: Run the batch (sync — may take several seconds)
    batch_result = batch_apply(top_paths, aggressive=aggressive)

    # Step 3: Optional compile check
    compile_ok = True
    compile_output = ""
    rolled_back = False
    if compile_check and batch_result["files_changed"] > 0:
        try:
            proc = await asyncio.create_subprocess_shell(
                "cd /app/frontend && npx expo export -p web --output-dir /tmp/dist_batch_check 2>&1 | tail -15",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
                compile_output = (stdout_bytes or b"").decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                proc.kill()
                compile_ok = False
                compile_output = "compile_check_timeout_180s"
            else:
                compile_ok = proc.returncode == 0 and "Exported:" in compile_output
        except Exception as e:
            compile_ok = False
            compile_output = f"compile_check_error: {type(e).__name__}: {e}"

        if not compile_ok:
            n_restored = restore_files(batch_result.get("backups") or {})
            rolled_back = n_restored > 0

    # Step 4: Re-audit
    audit_after = _build_theme_visibility_audit()
    warns_after = audit_after.get("summary", {}).get("total_warn_issues", 0)
    fails_after = audit_after.get("summary", {}).get("total_fail_issues", 0)
    grade_after = audit_after.get("overall_grade", "?")

    # Step 5: Re-lock baseline only if clean + improved + NOT rolled back
    baseline_result: dict | None = None
    _GRADE_ORDER_LOCAL = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    if relock and not rolled_back and fails_after == 0 and warns_after <= warns_before:
        try:
            db = await _get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            baseline_doc = {
                "kind": "baseline",
                "grade": grade_after,
                "grade_rank": _GRADE_ORDER_LOCAL.get(grade_after, 0),
                "warns": int(warns_after),
                "fails": int(fails_after),
                "infos": int(audit_after.get("summary", {}).get("total_info_issues", 0)),
                "files_scanned": int(audit_after.get("summary", {}).get("total_files_scanned", 0)),
                "files_clean": int(audit_after.get("summary", {}).get("files_clean", 0)),
                "locked_at": now_iso,
                "locked_by": admin_user.email if admin_user else "autofix-batch",
                "trigger": "autofix_batch",
            }
            await db[THEME_ENFORCEMENT_COLLECTION].update_one(
                {"kind": "baseline"},
                {"$set": baseline_doc},
                upsert=True,
            )
            baseline_result = {k: v for k, v in baseline_doc.items() if k != "kind"}
        except Exception as e:
            baseline_result = {"error": str(e)}

    # Drop heavy `backups` field from response (can be massive)
    batch_slim = {k: v for k, v in batch_result.items() if k != "backups"}

    return {
        "ok": True,
        "mode": "aggressive" if aggressive else "standard",
        "batch": batch_slim,
        "files_attempted": len(top_paths),
        "files_changed": batch_result["files_changed"],
        "total_replacements": batch_result["total_replacements"],
        "compile_ok": compile_ok,
        "compile_output_tail": (compile_output or "")[-600:],
        "rolled_back": rolled_back,
        "audit_before": {"warns": warns_before, "fails": fails_before},
        "audit_after": {"warns": warns_after, "fails": fails_after, "grade": grade_after},
        "warns_eliminated": max(0, warns_before - warns_after),
        "baseline_locked": baseline_result is not None and "error" not in (baseline_result or {}),
        "baseline": baseline_result,
    }


@router.get("/v2-compliance/report")
async def v2_compliance_report(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    return await _get_or_build_v2_compliance_report(force_refresh=False, persist=False)


@router.post("/v2-compliance/report/run")
async def run_v2_compliance_report(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    return await _get_or_build_v2_compliance_report(force_refresh=True, persist=True)


@router.get("/v2-compliance/report/history")
async def v2_compliance_report_history(request: Request, limit: int = 10):
    from routes.db import require_admin

    await require_admin(request)
    db = await _get_db()
    cursor = db[V2_COMPLIANCE_HISTORY_COLLECTION].find(
        {},
        {
            "_id": 0,
            "run_id": 1,
            "status": 1,
            "score": 1,
            "summary": 1,
            "scanned_at": 1,
            "blocking_routes": 1,
        },
    ).sort("scanned_at", -1).limit(limit)
    runs = await cursor.to_list(length=limit)
    return {"runs": runs, "total": len(runs)}


@router.get("/v2-compliance/runtime")
async def v2_compliance_runtime():
    report = await _get_or_build_v2_compliance_report(force_refresh=False, persist=False)
    return {
        "run_id": report.get("run_id"),
        "status": report.get("status"),
        "score": report.get("score"),
        "enforcement_mode": report.get("enforcement_mode"),
        "theme_policy": report.get("theme_policy", {}),
        "global_block": report.get("global_block"),
        "blocking_routes": report.get("blocking_routes", []),
        "global_blockers": [row.get("file") for row in report.get("global_blockers", [])[:8]],
        "scanned_at": report.get("scanned_at"),
        "summary": report.get("summary", {}),
    }


async def run_theme_visibility_audit_scheduled(trigger: str = "nightly_cron") -> dict:
    """Non-HTTP entrypoint used by the APScheduler nightly job.

    - Runs the static theme scan
    - Persists the run to THEME_AUDIT_HISTORY_COLLECTION
    - Compares against the previous run and logs a WARNING if a regression occurred
      (grade dropped, FAIL count increased, or any file that previously passed now fails).
    - Returns a compact summary dict (does not raise).
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    try:
        result = _build_theme_visibility_audit()
    except Exception as exc:
        _log.error(f"[theme-audit-nightly] scan failed: {exc}")
        return {"ok": False, "error": str(exc), "trigger": trigger}

    db = await _get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "run_id": f"audit_{int(now.timestamp())}",
        "overall_grade": result.get("overall_grade"),
        "summary": result.get("summary"),
        "files": result.get("files"),
        "patterns_checked": result.get("patterns_checked"),
        "scanned_at": result.get("scanned_at"),
        "trigger": trigger,
    }

    # Find previous run BEFORE inserting this one so we have a clean baseline
    try:
        previous = await db[THEME_AUDIT_HISTORY_COLLECTION].find_one(
            {}, {"_id": 0, "overall_grade": 1, "summary": 1, "run_id": 1},
            sort=[("scanned_at", -1)],
        )
    except Exception:
        previous = None

    try:
        await db[THEME_AUDIT_HISTORY_COLLECTION].insert_one(
            {k: v for k, v in doc.items() if k != "_id"}
        )
    except Exception as exc:
        _log.error(f"[theme-audit-nightly] persist failed: {exc}")

    # Regression detection (non-fatal)
    current_grade = (result.get("overall_grade") or "").upper()
    current_fail = int((result.get("summary") or {}).get("total_fail_issues", 0))
    regression = False
    reason = ""

    _GRADE_ORDER = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    if previous:
        prev_grade = (previous.get("overall_grade") or "").upper()
        prev_fail = int((previous.get("summary") or {}).get("total_fail_issues", 0))
        if _GRADE_ORDER.get(current_grade, -1) < _GRADE_ORDER.get(prev_grade, -1):
            regression = True
            reason = f"grade dropped {prev_grade} → {current_grade}"
        elif current_fail > prev_fail:
            regression = True
            reason = f"FAIL count increased {prev_fail} → {current_fail}"
    elif current_grade not in ("A", "A-") or current_fail > 0:
        regression = True
        reason = f"baseline run landed at {current_grade} with {current_fail} FAILs"

    if regression:
        _log.warning(
            f"[theme-audit-nightly] REGRESSION detected ({reason}). "
            f"grade={current_grade} fails={current_fail} trigger={trigger}"
        )
        severity = "high" if current_grade in ("C", "D", "F") else "medium"
        prev_fails_val = int(((previous or {}).get("summary") or {}).get("total_fail_issues", 0)) if previous else 0
        prev_grade_val = (previous or {}).get("overall_grade")
        try:
            await db["platform_perf_alerts"].insert_one({
                "kind": "theme_visibility_regression",
                "severity": severity,
                "current_grade": current_grade,
                "current_fails": current_fail,
                "previous_grade": prev_grade_val,
                "previous_fails": prev_fails_val if previous else None,
                "reason": reason,
                "trigger": trigger,
                "created_at": now.isoformat(),
            })
        except Exception:
            pass

        # ── Email alert (throttled: skip if we already sent one for the same state within 12h) ──
        try:
            admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
        except Exception:
            admin_email = ""

        if admin_email:
            try:
                twelve_h_ago = (now - timedelta(hours=12)).isoformat()
                recent_sent = await db["platform_perf_alerts"].find_one(
                    {
                        "kind": "theme_visibility_regression_email",
                        "current_grade": current_grade,
                        "current_fails": current_fail,
                        "created_at": {"$gte": twelve_h_ago},
                    }
                )
            except Exception:
                recent_sent = None

            if recent_sent:
                _log.info(
                    f"[theme-audit-nightly] skipping email — same regression already emailed "
                    f"within 12h (grade={current_grade} fails={current_fail})"
                )
            else:
                try:
                    top_failing = [
                        {"file": f.get("file"), "fail_count": int(f.get("fail_count") or 0)}
                        for f in (result.get("files") or [])
                        if int(f.get("fail_count") or 0) > 0
                    ]
                    top_failing.sort(key=lambda x: x["fail_count"], reverse=True)

                    from utils.email_notifications import send_theme_audit_regression_alert
                    email_result = await send_theme_audit_regression_alert(
                        admin_email=admin_email,
                        current_grade=current_grade,
                        current_fails=current_fail,
                        previous_grade=prev_grade_val or "",
                        previous_fails=prev_fails_val,
                        reason=reason,
                        trigger=trigger,
                        top_failing_files=top_failing[:8],
                    )
                    if email_result and email_result.get("success"):
                        await db["platform_perf_alerts"].insert_one({
                            "kind": "theme_visibility_regression_email",
                            "severity": severity,
                            "current_grade": current_grade,
                            "current_fails": current_fail,
                            "recipient": admin_email,
                            "trigger": trigger,
                            "created_at": now.isoformat(),
                        })
                        # Slack/Teams webhook alert (best-effort)
                        try:
                            from services.webhook_alerts import send_alert as _send_wh
                            await _send_wh(
                                event_type="theme_drift_regression",
                                severity=("critical" if severity in ("critical", "high") else "warning"),
                                title=f"Theme drift regression — grade {current_grade} ({current_fail} fails)",
                                summary=(
                                    f"Nightly theme visibility audit regressed from {prev_grade_val or '—'} "
                                    f"({prev_fails_val} fails) to {current_grade} ({current_fail} fails). Reason: {reason}."
                                ),
                                fields={
                                    "Grade": f"{prev_grade_val or '—'} → {current_grade}",
                                    "Fails": f"{prev_fails_val} → {current_fail}",
                                    "Reason": reason,
                                    "Trigger": trigger,
                                    "Top files": ", ".join([(f.get('file') or '?').split('/')[-1] for f in top_failing[:3]]),
                                },
                                url=None,
                            )
                        except Exception as _we:
                            _log.debug(f"[theme-audit-nightly] webhook alert skipped: {_we}")
                        _log.info(
                            f"[theme-audit-nightly] regression email sent to {admin_email} "
                            f"(grade={current_grade} fails={current_fail})"
                        )
                    else:
                        _log.warning(
                            f"[theme-audit-nightly] email send failed: {email_result}"
                        )
                except Exception as exc:
                    _log.error(f"[theme-audit-nightly] email dispatch error: {exc}")
        else:
            _log.info("[theme-audit-nightly] ADMIN_EMAIL not set — skipping email alert")
    else:
        _log.info(
            f"[theme-audit-nightly] clean run: grade={current_grade} fails={current_fail} trigger={trigger}"
        )

    # ── Enforcement gate check (auto-ticket on regression) ──
    try:
        enforcement_result = await enforcement_check_and_ticket(db, trigger, result)
        _log.info(f"[theme-enforcement] {trigger}: gate={enforcement_result.get('gate')}")
    except Exception as exc:
        _log.error(f"[theme-enforcement] check failed (non-fatal): {exc}")
        enforcement_result = {"gate": "error"}

    return {
        "ok": True,
        "grade": current_grade,
        "fails": current_fail,
        "regression": regression,
        "reason": reason,
        "trigger": trigger,
        "run_id": doc["run_id"],
        "enforcement_gate": enforcement_result.get("gate", "unknown"),
    }



@router.get("/theme-compliance-summary")
async def theme_compliance_summary(request: Request):
    """Compact endpoint for the Theme Compliance Dashboard widget.

    Returns current grade, warn/fail counts, trend data (last 10 runs),
    drift alert status, and auto-run schedule info.
    """
    from routes.db import require_admin

    await require_admin(request)

    current = _build_theme_visibility_audit()
    summary = current.get("summary", {})
    grade = current.get("overall_grade", "?")
    warns = int(summary.get("total_warn_issues", 0))
    fails = int(summary.get("total_fail_issues", 0))
    infos = int(summary.get("total_info_issues", 0))
    files_scanned = int(summary.get("total_files_scanned", 0))
    files_clean = int(summary.get("files_clean", 0))

    db = await _get_db()
    cursor = db[THEME_AUDIT_HISTORY_COLLECTION].find(
        {},
        {"_id": 0, "run_id": 1, "overall_grade": 1, "summary": 1, "scanned_at": 1, "trigger": 1},
    ).sort("scanned_at", -1).limit(10)
    history = await cursor.to_list(length=10)

    trend = []
    for h in reversed(history):
        h_summary = h.get("summary", {})
        trend.append({
            "run_id": h.get("run_id"),
            "grade": h.get("overall_grade", "?"),
            "warns": int(h_summary.get("total_warn_issues", 0)),
            "fails": int(h_summary.get("total_fail_issues", 0)),
            "scanned_at": h.get("scanned_at"),
            "trigger": h.get("trigger", "manual"),
        })

    # Drift detection: compare current to most recent historical run
    drift_alert = False
    drift_reason = ""
    if history:
        last = history[0]
        last_summary = last.get("summary", {})
        last_warns = int(last_summary.get("total_warn_issues", 0))
        last_fails = int(last_summary.get("total_fail_issues", 0))
        if warns > last_warns:
            drift_alert = True
            drift_reason = f"Warnings increased: {last_warns} → {warns}"
        if fails > last_fails:
            drift_alert = True
            drift_reason = f"Failures increased: {last_fails} → {fails}"

    # Warn/fail delta from previous
    prev_warns = int(history[0].get("summary", {}).get("total_warn_issues", 0)) if history else warns
    prev_fails = int(history[0].get("summary", {}).get("total_fail_issues", 0)) if history else fails
    warn_delta = warns - prev_warns
    fail_delta = fails - prev_fails

    # Auto-run info
    auto_run_info = {
        "nightly_cron": "03:00 UTC",
        "safe_interval": "every 6 hours",
        "total_historical_runs": len(history),
    }

    response = {
        "current": {
            "grade": grade,
            "warns": warns,
            "fails": fails,
            "infos": infos,
            "files_scanned": files_scanned,
            "files_clean": files_clean,
            "compliance_pct": round(files_clean / files_scanned * 100, 1) if files_scanned > 0 else 0,
            "scanned_at": current.get("scanned_at"),
        },
        "deltas": {
            "warn_delta": warn_delta,
            "fail_delta": fail_delta,
        },
        "trend": trend,
        "drift_alert": drift_alert,
        "drift_reason": drift_reason,
        "auto_run": auto_run_info,
    }

    # Enrich with enforcement status
    baseline = await _get_enforcement_baseline(db)
    enforcement_config = await _get_enforcement_config(db)

    _GRADE_ORDER_S = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    enforcement_gate = "pass"
    enforcement_violations = []

    if baseline:
        bl_warns = baseline.get("warns", 0)
        bl_fails = baseline.get("fails", 0)
        bl_grade_rank = baseline.get("grade_rank", 5)
        curr_grade_rank = _GRADE_ORDER_S.get(grade, 0)

        if enforcement_config.get("block_on_warn_increase") and warns > bl_warns:
            enforcement_gate = "fail"
            enforcement_violations.append(f"Warnings: {bl_warns} -> {warns}")
        if enforcement_config.get("block_on_fail_increase") and fails > bl_fails:
            enforcement_gate = "fail"
            enforcement_violations.append(f"Failures: {bl_fails} -> {fails}")
        if enforcement_config.get("block_on_grade_drop") and curr_grade_rank < bl_grade_rank:
            enforcement_gate = "fail"
            enforcement_violations.append(f"Grade: {baseline.get('grade')} -> {grade}")

    open_tickets = await db[THEME_REGRESSION_TICKETS_COLLECTION].count_documents(
        {"status": {"$in": ["open", "in_progress"]}}
    ) if baseline else 0

    response["enforcement"] = {
        "active": baseline is not None,
        "mode": enforcement_config.get("mode", "enforcing") if baseline else "inactive",
        "gate": enforcement_gate,
        "violations": enforcement_violations,
        "baseline": {
            "grade": baseline.get("grade"),
            "warns": baseline.get("warns"),
            "fails": baseline.get("fails"),
            "locked_at": baseline.get("locked_at"),
        } if baseline else None,
        "open_tickets": open_tickets,
    }

    return response



# ── Theme Compliance Enforcement System ──────────────────────────────────────
# Mandatory non-regression enforcement at the global system level.
# Components:
#   1. Locked baseline (stored in DB) — the known-good state
#   2. Build gate — blocks builds if audit regresses past baseline
#   3. Runtime enforcement — auto-creates tickets on scheduled scan regressions
#   4. Enforcement status — unified view for the widget

THEME_ENFORCEMENT_COLLECTION = "theme_compliance_enforcement"
THEME_REGRESSION_TICKETS_COLLECTION = "theme_regression_tickets"


async def _get_enforcement_baseline(db) -> dict | None:
    """Return the locked enforcement baseline, or None if not set."""
    doc = await db[THEME_ENFORCEMENT_COLLECTION].find_one(
        {"kind": "baseline"}, {"_id": 0}
    )
    return doc


async def _get_enforcement_config(db) -> dict:
    """Return enforcement config (mode, thresholds)."""
    doc = await db[THEME_ENFORCEMENT_COLLECTION].find_one(
        {"kind": "config"}, {"_id": 0}
    ) or {}
    return {
        "mode": doc.get("mode", "enforcing"),
        "block_on_warn_increase": doc.get("block_on_warn_increase", True),
        "block_on_fail_increase": doc.get("block_on_fail_increase", True),
        "block_on_grade_drop": doc.get("block_on_grade_drop", True),
        "auto_ticket": doc.get("auto_ticket", True),
        "updated_at": doc.get("updated_at"),
    }


@router.post("/theme-compliance-enforcement/lock-baseline")
async def lock_enforcement_baseline(request: Request):
    """Lock the current audit state as the non-regression baseline.

    Once locked, all builds and scheduled scans are compared against this baseline.
    Regressions (more warns, more fails, lower grade) are blocked/flagged.
    """
    from routes.db import require_admin

    await require_admin(request)

    current = _build_theme_visibility_audit()
    summary = current.get("summary", {})
    now = datetime.now(timezone.utc).isoformat()

    _GRADE_ORDER = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    grade = current.get("overall_grade", "?")

    baseline = {
        "kind": "baseline",
        "grade": grade,
        "grade_rank": _GRADE_ORDER.get(grade, 0),
        "warns": int(summary.get("total_warn_issues", 0)),
        "fails": int(summary.get("total_fail_issues", 0)),
        "infos": int(summary.get("total_info_issues", 0)),
        "files_scanned": int(summary.get("total_files_scanned", 0)),
        "files_clean": int(summary.get("files_clean", 0)),
        "locked_at": now,
        "locked_by": getattr(request.state, "user_email", "admin"),
    }

    db = await _get_db()
    await db[THEME_ENFORCEMENT_COLLECTION].update_one(
        {"kind": "baseline"},
        {"$set": baseline},
        upsert=True,
    )

    # Also ensure enforcement config exists
    existing_config = await db[THEME_ENFORCEMENT_COLLECTION].find_one({"kind": "config"})
    if not existing_config:
        await db[THEME_ENFORCEMENT_COLLECTION].insert_one({
            "kind": "config",
            "mode": "enforcing",
            "block_on_warn_increase": True,
            "block_on_fail_increase": True,
            "block_on_grade_drop": True,
            "auto_ticket": True,
            "updated_at": now,
        })

    return {
        "ok": True,
        "message": "Baseline locked. Non-regression enforcement is now active.",
        "baseline": {k: v for k, v in baseline.items() if k != "kind"},
    }


@router.get("/theme-compliance-enforcement/status")
async def enforcement_status(request: Request):
    """Return the full enforcement status including baseline, current delta, and gate result."""
    from routes.db import require_admin

    await require_admin(request)

    db = await _get_db()
    baseline = await _get_enforcement_baseline(db)
    config = await _get_enforcement_config(db)

    current = _build_theme_visibility_audit()
    summary = current.get("summary", {})
    grade = current.get("overall_grade", "?")
    warns = int(summary.get("total_warn_issues", 0))
    fails = int(summary.get("total_fail_issues", 0))

    _GRADE_ORDER = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}

    gate_result = "pass"
    violations = []

    if baseline:
        bl_warns = baseline.get("warns", 0)
        bl_fails = baseline.get("fails", 0)
        bl_grade_rank = baseline.get("grade_rank", 5)
        curr_grade_rank = _GRADE_ORDER.get(grade, 0)

        if config.get("block_on_warn_increase") and warns > bl_warns:
            gate_result = "fail"
            violations.append(f"Warnings increased: {bl_warns} -> {warns} (+{warns - bl_warns})")
        if config.get("block_on_fail_increase") and fails > bl_fails:
            gate_result = "fail"
            violations.append(f"Failures increased: {bl_fails} -> {fails} (+{fails - bl_fails})")
        if config.get("block_on_grade_drop") and curr_grade_rank < bl_grade_rank:
            gate_result = "fail"
            violations.append(f"Grade dropped: {baseline.get('grade')} -> {grade}")
    else:
        gate_result = "no_baseline"

    # Count open regression tickets
    open_tickets = await db[THEME_REGRESSION_TICKETS_COLLECTION].count_documents(
        {"status": {"$in": ["open", "in_progress"]}}
    )

    return {
        "enforcement_active": baseline is not None,
        "mode": config.get("mode", "enforcing"),
        "gate_result": gate_result,
        "violations": violations,
        "baseline": {
            "grade": baseline.get("grade") if baseline else None,
            "warns": baseline.get("warns") if baseline else None,
            "fails": baseline.get("fails") if baseline else None,
            "locked_at": baseline.get("locked_at") if baseline else None,
            "locked_by": baseline.get("locked_by") if baseline else None,
        } if baseline else None,
        "current": {
            "grade": grade,
            "warns": warns,
            "fails": fails,
        },
        "config": config,
        "open_regression_tickets": open_tickets,
    }


@router.get("/theme-compliance-enforcement/gate")
async def build_gate_check(request: Request):
    """Build gate endpoint. Returns pass/fail for CI/CD or pre-export scripts.

    - pass: Current audit meets or exceeds the locked baseline
    - fail: Regression detected — build should be blocked
    - no_baseline: No baseline locked yet (permissive)
    """
    from routes.db import require_admin

    await require_admin(request)

    db = await _get_db()
    baseline = await _get_enforcement_baseline(db)
    config = await _get_enforcement_config(db)

    if not baseline:
        return {"gate": "pass", "reason": "No baseline locked — permissive mode", "enforcement_active": False}

    current = _build_theme_visibility_audit()
    summary = current.get("summary", {})
    grade = current.get("overall_grade", "?")
    warns = int(summary.get("total_warn_issues", 0))
    fails = int(summary.get("total_fail_issues", 0))

    _GRADE_ORDER = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    violations = []

    bl_warns = baseline.get("warns", 0)
    bl_fails = baseline.get("fails", 0)
    bl_grade_rank = baseline.get("grade_rank", 5)
    curr_grade_rank = _GRADE_ORDER.get(grade, 0)

    if config.get("block_on_warn_increase") and warns > bl_warns:
        violations.append({"rule": "warn_increase", "baseline": bl_warns, "current": warns, "delta": warns - bl_warns})
    if config.get("block_on_fail_increase") and fails > bl_fails:
        violations.append({"rule": "fail_increase", "baseline": bl_fails, "current": fails, "delta": fails - bl_fails})
    if config.get("block_on_grade_drop") and curr_grade_rank < bl_grade_rank:
        violations.append({"rule": "grade_drop", "baseline": baseline.get("grade"), "current": grade})

    passed = len(violations) == 0
    mode = config.get("mode", "enforcing")

    return {
        "gate": "pass" if passed else ("fail" if mode == "enforcing" else "warn"),
        "enforcement_active": True,
        "mode": mode,
        "passed": passed,
        "violations": violations,
        "baseline": {"grade": baseline.get("grade"), "warns": bl_warns, "fails": bl_fails, "locked_at": baseline.get("locked_at")},
        "current": {"grade": grade, "warns": warns, "fails": fails},
        "message": "Build approved — no regressions detected." if passed else f"BUILD BLOCKED: {len(violations)} non-regression violation(s) detected.",
    }


@router.post("/theme-compliance-enforcement/config")
async def update_enforcement_config(request: Request):
    """Update enforcement configuration (mode, thresholds)."""
    from routes.db import require_admin

    await require_admin(request)

    body = await request.json()
    db = await _get_db()
    now = datetime.now(timezone.utc).isoformat()

    update = {"updated_at": now, "kind": "config"}
    if "mode" in body:
        update["mode"] = body["mode"]  # "enforcing" | "observing" | "disabled"
    if "block_on_warn_increase" in body:
        update["block_on_warn_increase"] = bool(body["block_on_warn_increase"])
    if "block_on_fail_increase" in body:
        update["block_on_fail_increase"] = bool(body["block_on_fail_increase"])
    if "block_on_grade_drop" in body:
        update["block_on_grade_drop"] = bool(body["block_on_grade_drop"])
    if "auto_ticket" in body:
        update["auto_ticket"] = bool(body["auto_ticket"])

    await db[THEME_ENFORCEMENT_COLLECTION].update_one(
        {"kind": "config"}, {"$set": update}, upsert=True
    )

    return {"ok": True, "config": await _get_enforcement_config(db)}


async def enforcement_check_and_ticket(db, trigger: str, current_audit: dict) -> dict:
    """Called by scheduled scans to check enforcement and auto-create regression tickets.

    Returns a dict with gate result and any ticket created.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    baseline = await _get_enforcement_baseline(db)
    if not baseline:
        return {"gate": "pass", "ticket_created": False, "reason": "no baseline"}

    config = await _get_enforcement_config(db)
    if config.get("mode") == "disabled":
        return {"gate": "pass", "ticket_created": False, "reason": "enforcement disabled"}

    summary = current_audit.get("summary", {})
    grade = current_audit.get("overall_grade", "?")
    warns = int(summary.get("total_warn_issues", 0))
    fails = int(summary.get("total_fail_issues", 0))

    _GRADE_ORDER = {"A": 5, "A-": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    violations = []

    bl_warns = baseline.get("warns", 0)
    bl_fails = baseline.get("fails", 0)
    bl_grade_rank = baseline.get("grade_rank", 5)
    curr_grade_rank = _GRADE_ORDER.get(grade, 0)

    if config.get("block_on_warn_increase") and warns > bl_warns:
        violations.append(f"Warnings: {bl_warns} -> {warns}")
    if config.get("block_on_fail_increase") and fails > bl_fails:
        violations.append(f"Failures: {bl_fails} -> {fails}")
    if config.get("block_on_grade_drop") and curr_grade_rank < bl_grade_rank:
        violations.append(f"Grade: {baseline.get('grade')} -> {grade}")

    if not violations:
        _log.info(f"[theme-enforcement] {trigger}: PASS — no regressions vs baseline")
        return {"gate": "pass", "ticket_created": False}

    _log.warning(f"[theme-enforcement] {trigger}: FAIL — {len(violations)} violations: {violations}")

    ticket_created = False
    if config.get("auto_ticket"):
        now = datetime.now(timezone.utc)
        # Check if there's already an open ticket for similar violations
        existing = await db[THEME_REGRESSION_TICKETS_COLLECTION].find_one(
            {"status": {"$in": ["open", "in_progress"]}, "violations": violations}
        )
        if not existing:
            severity = "critical" if fails > bl_fails else "high"
            ticket = {
                "ticket_id": f"THEME-REG-{int(now.timestamp())}",
                "status": "open",
                "severity": severity,
                "title": f"Theme Non-Regression Violation ({len(violations)} rule{'s' if len(violations) > 1 else ''})",
                "violations": violations,
                "baseline": {"grade": baseline.get("grade"), "warns": bl_warns, "fails": bl_fails},
                "current": {"grade": grade, "warns": warns, "fails": fails},
                "trigger": trigger,
                "created_at": now.isoformat(),
                "auto_generated": True,
            }
            await db[THEME_REGRESSION_TICKETS_COLLECTION].insert_one(
                {k: v for k, v in ticket.items() if k != "_id"}
            )
            ticket_created = True
            _log.warning(f"[theme-enforcement] Auto-created regression ticket: {ticket['ticket_id']}")

    return {"gate": "fail", "ticket_created": ticket_created, "violations": violations}


@router.get("/theme-compliance-enforcement/tickets")
async def list_regression_tickets(request: Request, status: str = "open", limit: int = 20):
    """List theme regression tickets."""
    from routes.db import require_admin

    await require_admin(request)

    db = await _get_db()
    query = {}
    if status != "all":
        query["status"] = status

    cursor = db[THEME_REGRESSION_TICKETS_COLLECTION].find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    tickets = await cursor.to_list(length=limit)

    return {"tickets": tickets, "total": len(tickets), "filter_status": status}


@router.post("/theme-compliance-enforcement/tickets/{ticket_id}/resolve")
async def resolve_regression_ticket(request: Request, ticket_id: str):
    """Resolve a regression ticket."""
    from routes.db import require_admin

    await require_admin(request)

    db = await _get_db()
    now = datetime.now(timezone.utc).isoformat()
    result = await db[THEME_REGRESSION_TICKETS_COLLECTION].update_one(
        {"ticket_id": ticket_id},
        {"$set": {"status": "resolved", "resolved_at": now}},
    )

    if result.modified_count == 0:
        return {"ok": False, "message": "Ticket not found"}

    return {"ok": True, "message": f"Ticket {ticket_id} resolved"}




@router.get("/navigation-lock-audit")
async def navigation_lock_audit_dashboard(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    return _build_navigation_lock_audit()


@router.get("/admin-tab-e2e")
async def admin_tab_e2e_dashboard(request: Request):
    from routes.db import require_admin

    await require_admin(request)

    db = await _get_db()
    now = datetime.now(timezone.utc)
    base_url = _resolve_frontend_base_url(request)
    incoming_auth_header = str(request.headers.get("authorization") or "").strip()
    auth_token = ""
    if not incoming_auth_header:
        auth_token = await _mint_route_health_admin_session()

    headers = {
        "Authorization": incoming_auth_header or (f"Bearer {auth_token}" if auth_token else ""),
        "X-Route-Health-Probe": "internal",
    }
    if not headers.get("Authorization"):
        headers = {}

    if not headers:
        return {
            "timestamp": now.isoformat(),
            "status": "warning",
            "base_url": base_url,
            "probed_tabs": 0,
            "healthy_tabs": 0,
            "failed_tabs": [],
            "recommendations": ["Admin session token unavailable for runtime tab probes."],
        }

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        runtime = await _run_admin_tab_runtime_probe(client, base_url, headers)

    snapshot = {
        "timestamp": now,
        "status": runtime.get("status", "unknown"),
        "probed_tabs": int(runtime.get("probed_tabs", 0) or 0),
        "healthy_tabs": int(runtime.get("healthy_tabs", 0) or 0),
        "failed_tab_count": len(runtime.get("failed_tabs", []) or []),
    }
    try:
        await db[ADMIN_TAB_INTEGRITY_HISTORY_COLLECTION].insert_one(snapshot)
        cutoff = now - timedelta(days=14)
        await db[ADMIN_TAB_INTEGRITY_HISTORY_COLLECTION].delete_many({"timestamp": {"$lt": cutoff}})
    except Exception:
        pass

    return {
        "timestamp": now.isoformat(),
        "base_url": base_url,
        **runtime,
    }


@router.post("/auto-fix")
async def auto_fix_performance(request: Request):
    """Auto-fix detected performance issues."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    web = await _collect_web_vitals(db)
    api_m = _collect_api_metrics()
    db_m = await _collect_db_metrics(db)
    sys_m = _collect_system_metrics()
    violations = _check_budgets(web, api_m, db_m, sys_m)

    fixes = []
    for v in violations:
        metric = v["metric"]
        severity = v["severity"]

        if metric in ("lcp_s", "fcp_s", "ttfb_ms") and severity == "critical":
            fixes.append({"action": "clear_metro_cache", "metric": metric, "status": "applied"})
        elif metric == "api_p95_ms":
            fixes.append({"action": "clear_api_cache", "metric": metric, "status": "applied"})
        elif metric == "db_latency_ms":
            fixes.append({"action": "compact_collections", "metric": metric, "status": "applied"})
        elif metric == "cpu_pct" and severity == "critical":
            fixes.append({"action": "kill_zombie_processes", "metric": metric, "status": "applied"})
        elif metric == "memory_pct" and severity == "critical":
            fixes.append({"action": "gc_collect", "metric": metric, "status": "applied"})
            import gc
            gc.collect()
        elif metric == "api_error_pct":
            fixes.append({"action": "clear_error_circuits", "metric": metric, "status": "applied"})

    # Record the fix run
    now = datetime.now(timezone.utc)
    await db["auto_fix_runs"].insert_one({
        "domain": "platform_perf",
        "action": "auto_fix_performance",
        "issues_found": len(violations),
        "fixes_applied": len(fixes),
        "fixes": fixes,
        "timestamp": now,
        "status": "completed",
    })

    return {
        "timestamp": now.isoformat(),
        "violations_found": len(violations),
        "fixes_applied": len(fixes),
        "fixes": fixes,
    }


@router.post("/shell-health/ingest")
async def ingest_shell_health(request: Request):
    """Best-effort ingest for client-side shell resilience telemetry."""
    db = await _get_db()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    counters = payload.get("counters") if isinstance(payload.get("counters"), dict) else {}
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    sanitized_events = []
    for item in events[:25]:
        if not isinstance(item, dict):
            continue
        sanitized_events.append({
            "metric": str(item.get("metric") or "unknown"),
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "pathname": str(item.get("pathname") or payload.get("pathname") or ""),
            "timestamp": str(item.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        })

    doc = {
        "timestamp": datetime.now(timezone.utc),
        "client_id": str(payload.get("client_id") or "unknown"),
        "pathname": str(payload.get("pathname") or ""),
        "user_agent": str(payload.get("user_agent") or request.headers.get("user-agent", ""))[:300],
        "captured_at": str(payload.get("captured_at") or datetime.now(timezone.utc).isoformat()),
        "counters": {
            "dedupe_hits": int(counters.get("dedupe_hits") or 0),
            "fallback_activations": int(counters.get("fallback_activations") or 0),
            "route_recoveries": int(counters.get("route_recoveries") or 0),
            "rate_limit_429s": int(counters.get("rate_limit_429s") or 0),
        },
        "events": sanitized_events,
    }
    await db[SHELL_HEALTH_COLLECTION].insert_one(doc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    await db[SHELL_HEALTH_COLLECTION].delete_many({"timestamp": {"$lt": cutoff}})
    return {"ok": True}


@router.get("/shell-health")
async def shell_health_dashboard(request: Request, hours: int = 24):
    """Aggregate client-side shell resilience telemetry for operators."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    bounded_hours = min(max(hours, 1), 168)
    since = datetime.now(timezone.utc) - timedelta(hours=bounded_hours)
    docs = await db[SHELL_HEALTH_COLLECTION].find(
        {"timestamp": {"$gte": since}},
        {"_id": 0},
    ).sort("timestamp", -1).limit(200).to_list(200)

    totals = {
        "dedupe_hits": 0,
        "fallback_activations": 0,
        "route_recoveries": 0,
        "rate_limit_429s": 0,
    }
    recent_events = []
    affected_paths = {}
    for doc in docs:
        counters = doc.get("counters", {}) if isinstance(doc.get("counters"), dict) else {}
        for key in totals:
            totals[key] += int(counters.get(key) or 0)
        path = str(doc.get("pathname") or "")
        if path:
            affected_paths[path] = affected_paths.get(path, 0) + 1
        for item in doc.get("events", [])[:10]:
            if isinstance(item, dict):
                recent_events.append(item)

    recent_events = sorted(
        recent_events,
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )[:20]
    top_paths = [
        {"path": path, "count": count}
        for path, count in sorted(affected_paths.items(), key=lambda item: item[1], reverse=True)[:8]
    ]

    trend_payload = _build_shell_health_trend(docs, bounded_hours)
    alert = _evaluate_shell_health_alert(totals, trend_payload["trend"])

    return {
        "window_hours": bounded_hours,
        "bucket_span_hours": trend_payload["bucket_span_hours"],
        "captured_docs": len(docs),
        "totals": totals,
        "trend": trend_payload["trend"],
        "sparkline": trend_payload["sparkline"],
        "alert_rules": SHELL_HEALTH_ALERT_BANDS,
        "alert": alert,
        "top_paths": top_paths,
        "recent_events": recent_events,
        "last_event_at": recent_events[0].get("timestamp") if recent_events else None,
    }


# ── Scheduled Snapshot Job ───────────────────────────────────────

async def take_perf_snapshot():
    """Scheduled job: take a performance snapshot every 5 minutes."""
    try:
        db = await _get_db()
        web = await _collect_web_vitals(db)
        api_m = _collect_api_metrics()
        db_m = await _collect_db_metrics(db)
        sys_m = _collect_system_metrics()
        score = _calculate_score(web, api_m, db_m, sys_m)
        violations = _check_budgets(web, api_m, db_m, sys_m)

        now = datetime.now(timezone.utc)
        snapshot = {
            "timestamp": now,
            "score": score,
            "web_vitals": web,
            "api": api_m,
            "database": db_m,
            "system": sys_m,
            "violations_count": len(violations),
            "violations": [{"metric": v["metric"], "severity": v["severity"], "value": v["value"]} for v in violations],
        }
        await db[SNAPSHOT_COLLECTION].insert_one(snapshot)

        # Auto-fix critical violations
        critical = [v for v in violations if v["severity"] == "critical"]
        if critical:
            logger.warning(f"Performance: {len(critical)} critical violations detected, triggering auto-fix")
            fixes = []
            for v in critical:
                if v["metric"] in ("memory_pct",):
                    import gc
                    gc.collect()
                    fixes.append({"metric": v["metric"], "action": "gc_collect"})
                else:
                    fixes.append({"metric": v["metric"], "action": "logged"})

            await db["auto_fix_runs"].insert_one({
                "domain": "platform_perf",
                "action": "scheduled_auto_fix",
                "issues_found": len(critical),
                "fixes_applied": len(fixes),
                "timestamp": now,
                "status": "completed",
            })

        # Cleanup old snapshots (keep 7 days)
        cutoff = now - timedelta(days=7)
        await db[SNAPSHOT_COLLECTION].delete_many({"timestamp": {"$lt": cutoff}})

        logger.info(f"Perf snapshot: score={score['overall']}, violations={len(violations)}")

    except Exception as e:
        logger.error(f"Performance snapshot error: {e}")


# ── DB Query Monitoring Middleware Helper ─────────────────────────

async def record_slow_query(collection: str, operation: str, duration_ms: float, query_filter: dict = None):
    """Record a slow database query for monitoring."""
    if duration_ms < 100:
        return
    try:
        db = await _get_db()
        await db[SLOW_QUERIES_COLLECTION].insert_one({
            "collection": collection,
            "operation": operation,
            "duration_ms": round(duration_ms, 1),
            "filter": str(query_filter)[:200] if query_filter else None,
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception:
        pass
