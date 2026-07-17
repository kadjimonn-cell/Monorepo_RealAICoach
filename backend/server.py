"""RealAICoach API — Modular Monolith Application Factory

This file is the lean entrypoint for the platform.  All business logic is
delegated to domain registries (domains/*), middleware (middleware.py),
scheduler jobs (scheduler.py / scheduler_jobs.py), and WebSocket endpoints
(ws_endpoints.py).
"""

from fastapi import FastAPI, APIRouter, Request, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import socket
from pathlib import Path
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import stripe
import requests
from observability.logging_config import configure_structured_logging
from observability.otel_runtime import configure_open_telemetry
from scripts.preview_host_guard import assert_startup_preview_host_safety
from utils.server_activity_log import (
    fetch_admin_activity_log_payload,
    render_activity_log_csv,
    render_activity_log_pdf,
)
from utils.server_anomaly import detect_admin_anomalies, detect_alerting_anomalies, run_anomaly_alert_check as _run_server_anomaly_alert_check
from utils.server_sse import sse_payload_response as _sse_payload_response
from utils.db_security_hardening import ensure_db_security_hardening, get_db_security_hardening_status
from utils.iap_secret_runtime import hydrate_iap_runtime_secrets, enforce_iap_startup_preflight

# ── Environment ──────────────────────────────────────────────────────────────


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=False)

# ── Deployment override support ──────────────────────────────────────────────
# MONGO_URL and DB_NAME are platform-reserved keys in the Emergent publishing
# panel (the platform injects its own values for the deployed app), so they
# cannot be edited as custom secrets. Production DB targeting therefore arrives
# via the non-reserved *_OVERRIDE keys below. Empty/unset values are ignored,
# keeping preview behavior 100% unchanged.
for _override_key, _target_key in (
    ("MONGO_URL_OVERRIDE", "MONGO_URL"),
    ("DB_NAME_OVERRIDE", "DB_NAME"),
):
    _override_value = str(os.environ.get(_override_key) or "").strip()
    if _override_value:
        os.environ[_target_key] = _override_value


def _is_production_runtime() -> bool:
    candidates = [
        str(os.environ.get("APP_ENV") or "").strip().lower(),
        str(os.environ.get("ENVIRONMENT") or "").strip().lower(),
        str(os.environ.get("NODE_ENV") or "").strip().lower(),
    ]
    return any(value in {"prod", "production"} for value in candidates if value)


def _enforce_secret_vault_policy() -> None:
    # Hard-fail in production unless explicitly disabled.
    # Goal: no runtime secrets sourced from tracked plaintext files.
    enforce_raw = str(os.environ.get("SECRET_VAULT_ENFORCE") or "true").strip().lower()
    if enforce_raw in {"0", "false", "no", "off"}:
        return
    if not _is_production_runtime():
        return

    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return

    content = env_path.read_text(encoding="utf-8", errors="ignore")
    sensitive_keys = [
        "JWT_SECRET",
        "OPENAI_API_KEY",
        "STRIPE_SECRET_KEY",
        "PAYPAL_CLIENT_SECRET",
        "GOOGLE_CLIENT_SECRET",
        "APPLE_CLIENT_SECRET",
        "RESEND_API_KEY",
    ]
    leaked = []
    for key in sensitive_keys:
        match = _re.search(rf"^\s*{_re.escape(key)}\s*=\s*(.+)\s*$", content, flags=_re.MULTILINE)
        if match and str(match.group(1) or "").strip().strip('"').strip("'"):
            leaked.append(key)

    if leaked:
        raise RuntimeError(
            "SECRET_VAULT_ENFORCE violation: plaintext secrets found in backend/.env for keys "
            + ", ".join(sorted(set(leaked)))
        )


def _enforce_required_secret_env_vars() -> None:
    """Fail fast when required secret env vars are missing/empty."""
    enforce_raw = str(os.environ.get("REQUIRED_SECRET_ENV_ENFORCE") or "true").strip().lower()
    if enforce_raw in {"0", "false", "no", "off"}:
        return

    required_keys = [
        "JWT_SECRET",
        "RESEND_API_KEY",
        "PAYPAL_CLIENT_ID",
        "PAYPAL_SECRET",
    ]
    required_any_groups = [
        ("STRIPE_SECRET_KEY", "STRIPE_API_KEY"),
        ("OPENAI_API_KEY", "EMERGENT_LLM_KEY"),
    ]

    missing_keys = [
        key for key in required_keys if not str(os.environ.get(key) or "").strip()
    ]
    missing_groups = [
        group for group in required_any_groups if not any(str(os.environ.get(k) or "").strip() for k in group)
    ]

    if missing_keys or missing_groups:
        group_labels = [" | ".join(group) for group in missing_groups]
        issues = []
        if missing_keys:
            issues.append("missing required keys: " + ", ".join(missing_keys))
        if group_labels:
            issues.append("missing any-of groups: " + "; ".join(group_labels))
        raise RuntimeError("REQUIRED_SECRET_ENV violation: " + " | ".join(issues))

# ── Self-heal: Auto-fix credentials corrupted by platform forking ──────
import re as _re
from urllib.parse import urlparse as _urlparse, urlunparse as _urlunparse

# Dynamic domain detection.
# Platform rule: in preview/fork jobs, APP_URL is the authoritative host.
# Never let stale frontend/.env preview hosts override active fork host.
def _normalize_https_url(value: str) -> str:
    val = str(value or "").strip().rstrip("/")
    if not val:
        return ""
    if val.startswith("http://") or val.startswith("https://"):
        return val
    return ""


def _read_proc_environ_value(key: str) -> str:
    """Read container-level env value from PID 1 when process env is narrowed by supervisor."""
    lookup = str(key or "").strip()
    if not lookup:
        return ""

    for path in ("/proc/1/environ", "/proc/self/environ"):
        try:
            raw = Path(path).read_bytes().decode("utf-8", errors="ignore")
        except Exception:
            continue

        for token in raw.split("\x00"):
            if token.startswith(f"{lookup}="):
                return token.split("=", 1)[1].strip()

    return ""


def _is_preview_host(value: str) -> bool:
    candidate = _normalize_https_url(value)
    if not candidate:
        return False
    host = (_urlparse(candidate).netloc or "").lower()
    return host.endswith(".preview.emergentagent.com") or ".preview.emergentcf.cloud" in host


def _rewrite_url_to_base(url_value: str, base: str) -> str:
    raw = _normalize_https_url(url_value)
    target = _normalize_https_url(base)
    if not raw or not target:
        return raw
    src_parsed = _urlparse(raw)
    dst_parsed = _urlparse(target)
    if not dst_parsed.scheme or not dst_parsed.netloc:
        return raw
    rewritten = src_parsed._replace(scheme=dst_parsed.scheme, netloc=dst_parsed.netloc)
    return _urlunparse(rewritten).rstrip("/")


def _extract_preview_subdomain(url_value: str) -> str:
    raw = _normalize_https_url(url_value)
    if not raw:
        return ""
    host = (_urlparse(raw).netloc or "").lower()
    for suffix in (".preview.emergentagent.com", ".preview.emergentcf.cloud"):
        if host.endswith(suffix):
            return host[: -len(suffix)]
    return ""


def _detect_deployment_domain():
    """Detect the current deployment domain from platform environment."""
    preview_endpoint = _normalize_https_url(
        os.environ.get("PREVIEW_ENDPOINT", "")
        or os.environ.get("preview_endpoint", "")
        or _read_proc_environ_value("PREVIEW_ENDPOINT")
        or _read_proc_environ_value("preview_endpoint")
    )
    app_url = _normalize_https_url(os.environ.get("APP_URL", ""))
    dashboard_base = _normalize_https_url(os.environ.get("DASHBOARD_LINK_URL", ""))
    support_base = _normalize_https_url(os.environ.get("SUPPORT_LINK_URL", ""))
    frontend_base = _normalize_https_url(os.environ.get("FRONTEND_BASE_URL", ""))
    sso_base = _normalize_https_url(os.environ.get("SSO_REDIRECT_BASE_URL", ""))
    react_env_base = _normalize_https_url(os.environ.get("REACT_APP_BACKEND_URL", ""))
    expo_env_base = _normalize_https_url(os.environ.get("EXPO_PUBLIC_BACKEND_URL", ""))

    # Fallback candidate from frontend runtime env
    frontend_runtime_base = ""
    _fe_env = ROOT_DIR.parent / "frontend" / ".env"
    if _fe_env.exists():
        for line in _fe_env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                val = line.split("=", 1)[1].strip().rstrip("/")
                if val.startswith("https://"):
                    frontend_runtime_base = val
                    break

    # In preview/fork runtimes, preview URL parity is mandatory.
    # APP_URL is platform-assigned per job/fork and must be preferred first.
    preview_runtime = any(
        _is_preview_host(candidate)
        for candidate in [
            preview_endpoint,
            app_url,
            react_env_base,
            expo_env_base,
            frontend_base,
            sso_base,
            dashboard_base,
            support_base,
            frontend_runtime_base,
        ]
    )
    if preview_runtime:
        for candidate in [
            preview_endpoint,
            app_url,
            react_env_base,
            expo_env_base,
            frontend_base,
            sso_base,
            dashboard_base,
            support_base,
            frontend_runtime_base,
        ]:
            if _is_preview_host(candidate):
                return candidate

    # Prefer stable non-preview domains for real-user links whenever available.
    preferred = [
        dashboard_base,
        support_base,
        frontend_base,
        sso_base,
        frontend_runtime_base,
        preview_endpoint,
        app_url,
    ]
    non_preview = [p for p in preferred if p and not _is_preview_host(p)]
    if non_preview:
        return non_preview[0]

    # Otherwise use available preview runtime domain.
    for candidate in [
        preview_endpoint,
        frontend_runtime_base,
        react_env_base,
        expo_env_base,
        frontend_base,
        sso_base,
        dashboard_base,
        support_base,
        app_url,
    ]:
        if candidate:
            return candidate
    return ""

_CURRENT_DOMAIN = _detect_deployment_domain()

# ── Production hard guard (defense in depth) ─────────────────────────────────
# In a production runtime, a preview-host detection is always bogus (it comes
# from preview values shipped inside .env files). Never let it rewrite the
# production URL config — panel-provided values must win. Every downstream
# self-heal rewrite is conditioned on a truthy _CURRENT_DOMAIN, so neutralizing
# it here safely skips them all.
if _is_production_runtime() and _CURRENT_DOMAIN and _is_preview_host(_CURRENT_DOMAIN):
    logging.getLogger("server").warning(
        "Self-heal REFUSED in production: detected domain '%s' is a preview host; "
        "keeping existing URL configuration untouched",
        _CURRENT_DOMAIN,
    )
    _CURRENT_DOMAIN = ""

_KNOWN_GOOD_CREDS = {
    "AZURE_CLIENT_ID": "888e987c-d5c5-4582-8371-65f9a22167a0",
    "AZURE_TENANT_ID": "44ba0d5f-c69a-464d-81a2-9b8f55c6daa8",
}
_UUID_RE = _re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", _re.I)

_env_path = ROOT_DIR / ".env"
_env_dirty = False
_env_text = _env_path.read_text()

# Fix Azure credentials (must be UUIDs)
for _key, _good in _KNOWN_GOOD_CREDS.items():
    _val = os.environ.get(_key, "")
    if _val and not _UUID_RE.match(_val):
        os.environ[_key] = _good
        _env_text = _re.sub(rf"^{_key}=.*$", f"{_key}={_good}", _env_text, flags=_re.M)
        _env_dirty = True
        logging.getLogger("server").warning(
            f"Self-heal: {_key} was corrupted ('{_val}') — restored to '{_good}'"
        )

# Sync FRONTEND_BASE_URL with detected domain
_fe_base = os.environ.get("FRONTEND_BASE_URL", "").strip().rstrip("/")
if _CURRENT_DOMAIN and _fe_base != _CURRENT_DOMAIN:
    os.environ["FRONTEND_BASE_URL"] = _CURRENT_DOMAIN
    if "FRONTEND_BASE_URL=" in _env_text:
        _env_text = _re.sub(r"^FRONTEND_BASE_URL=.*$", f"FRONTEND_BASE_URL={_CURRENT_DOMAIN}", _env_text, flags=_re.M)
    else:
        _env_text += f"\nFRONTEND_BASE_URL={_CURRENT_DOMAIN}\n"
    _env_dirty = True
    logging.getLogger("server").warning(
        f"Self-heal: FRONTEND_BASE_URL synced to '{_CURRENT_DOMAIN}' (was '{_fe_base}')"
    )

# Sync SSO_REDIRECT_BASE_URL with detected domain
_sso_base = os.environ.get("SSO_REDIRECT_BASE_URL", "").strip().rstrip("/")
if _CURRENT_DOMAIN and _sso_base != _CURRENT_DOMAIN:
    os.environ["SSO_REDIRECT_BASE_URL"] = _CURRENT_DOMAIN
    if "SSO_REDIRECT_BASE_URL=" in _env_text:
        _env_text = _re.sub(r"^SSO_REDIRECT_BASE_URL=.*$", f"SSO_REDIRECT_BASE_URL={_CURRENT_DOMAIN}", _env_text, flags=_re.M)
    else:
        _env_text += f"\nSSO_REDIRECT_BASE_URL={_CURRENT_DOMAIN}\n"
    _env_dirty = True
    if _sso_base:
        logging.getLogger("server").warning(
            f"Self-heal: SSO_REDIRECT_BASE_URL synced to '{_CURRENT_DOMAIN}' (was '{_sso_base}')"
        )


def _sync_env_url_key(key: str, default_path: str = ""):
    global _env_text, _env_dirty
    raw = _normalize_https_url(os.environ.get(key, ""))
    if not _CURRENT_DOMAIN:
        return

    target = _CURRENT_DOMAIN.rstrip("/")
    if default_path:
        target = f"{target}{default_path}"

    should_rewrite = False
    if not raw:
        should_rewrite = True
    elif raw != target:
        # Rewrite stale preview or mismatched hosts to canonical domain.
        src_host = (_urlparse(raw).netloc or "").lower() if raw else ""
        dst_host = (_urlparse(target).netloc or "").lower() if target else ""
        should_rewrite = bool(src_host and dst_host and src_host != dst_host)

    if not should_rewrite:
        return

    next_value = _rewrite_url_to_base(raw, _CURRENT_DOMAIN) if raw else target
    if default_path and next_value and _urlparse(next_value).path.rstrip("/") == "":
        next_value = f"{next_value.rstrip('/')}{default_path}"
    if default_path and next_value and not next_value.endswith(default_path):
        parsed = _urlparse(next_value)
        next_value = _urlunparse(parsed._replace(path=default_path)).rstrip("/")

    os.environ[key] = next_value
    if f"{key}=" in _env_text:
        _env_text = _re.sub(rf"^{key}=.*$", f"{key}={next_value}", _env_text, flags=_re.M)
    else:
        _env_text += f"\n{key}={next_value}\n"
    _env_dirty = True
    logging.getLogger("server").warning(
        f"Self-heal: {key} synced to '{next_value}'"
    )


def _sync_env_uri_list_key(key: str):
    global _env_text, _env_dirty
    sync_mode = str(os.environ.get("SSO_REGISTERED_URI_SYNC_MODE") or "preserve").strip().lower()
    if sync_mode != "rewrite_to_current":
        return

    raw = str(os.environ.get(key, "") or "").strip()
    if not _CURRENT_DOMAIN:
        return

    source_items = [item.strip() for item in raw.split(",") if item.strip()]
    if not source_items:
        source_items = [_CURRENT_DOMAIN]

    rewritten_items = []
    for item in source_items:
        normalized = _normalize_https_url(item)
        rewritten_items.append(_rewrite_url_to_base(normalized, _CURRENT_DOMAIN) if normalized else _CURRENT_DOMAIN)

    deduped = []
    for item in rewritten_items:
        if item not in deduped:
            deduped.append(item)

    next_value = ",".join(deduped)
    if next_value == raw:
        return

    os.environ[key] = next_value
    if f"{key}=" in _env_text:
        _env_text = _re.sub(rf"^{key}=.*$", f"{key}={next_value}", _env_text, flags=_re.M)
    else:
        _env_text += f"\n{key}={next_value}\n"
    _env_dirty = True
    logging.getLogger("server").warning(
        f"Self-heal: {key} synced to canonical domain list '{next_value}'"
    )


def _sync_frontend_preview_env_keys():
    if not _CURRENT_DOMAIN or not _is_preview_host(_CURRENT_DOMAIN):
        return

    fe_env_path = ROOT_DIR.parent / "frontend" / ".env"
    if not fe_env_path.exists():
        return

    parsed = _urlparse(_CURRENT_DOMAIN)
    scheme = parsed.scheme or "https"
    host = (parsed.netloc or "").lower()
    if not host:
        return

    canonical_preview_url = f"{scheme}://{host}".rstrip("/")
    canonical_subdomain = _extract_preview_subdomain(canonical_preview_url)
    if not canonical_subdomain:
        return

    fe_text = fe_env_path.read_text()
    fe_dirty = False

    updates = {
        "REACT_APP_BACKEND_URL": canonical_preview_url,
        "EXPO_PUBLIC_BACKEND_URL": canonical_preview_url,
        "EXPO_PACKAGER_HOSTNAME": canonical_preview_url,
        "EXPO_PACKAGER_PROXY_URL": canonical_preview_url,
        "EXPO_TUNNEL_SUBDOMAIN": canonical_subdomain,
        "EXPECTED_PREVIEW_HOST": host,
    }

    for key, value in updates.items():
        replacement = f"{key}={value}"
        pattern = rf"^{key}=.*$"
        match = _re.search(pattern, fe_text, flags=_re.M)
        if match:
            if match.group(0) != replacement:
                fe_text = _re.sub(pattern, replacement, fe_text, flags=_re.M)
                fe_dirty = True
        else:
            fe_text += f"\n{replacement}\n"
            fe_dirty = True

        os.environ[key] = value

    if fe_dirty:
        fe_env_path.write_text(fe_text)
        logging.getLogger("server").warning(
            "Self-heal: frontend/.env preview host keys synced to canonical preview domain "
            f"'{canonical_preview_url}'"
        )


def _sync_backend_preview_env_keys():
    """Rewrite stale preview-host aliases in backend/.env to current preview host.

    This keeps startup resilient when old preview hosts linger in historical env keys.
    Non-preview/stable domains (e.g. production) are preserved unchanged.
    """
    global _env_text, _env_dirty

    if not _CURRENT_DOMAIN or not _is_preview_host(_CURRENT_DOMAIN):
        return

    logger = logging.getLogger("server")

    def _update_env_line(key: str, next_value: str) -> None:
        nonlocal logger
        global _env_text, _env_dirty
        os.environ[key] = next_value
        if f"{key}=" in _env_text:
            _env_text = _re.sub(rf"^{key}=.*$", f"{key}={next_value}", _env_text, flags=_re.M)
        else:
            _env_text += f"\n{key}={next_value}\n"
        _env_dirty = True

    def _rewrite_preview_url_key(key: str):
        raw = str(os.environ.get(key, "") or "").strip()
        normalized = _normalize_https_url(raw)
        if not normalized or not _is_preview_host(normalized):
            return
        rewritten = _rewrite_url_to_base(normalized, _CURRENT_DOMAIN)
        if rewritten == normalized:
            return
        _update_env_line(key, rewritten)
        logger.warning(f"Self-heal: {key} preview host synced to '{rewritten}'")

    def _rewrite_preview_csv_key(key: str):
        raw = str(os.environ.get(key, "") or "").strip()
        if not raw:
            return

        source_items = [item.strip() for item in raw.split(",") if item.strip()]
        rewritten_items: list[str] = []
        changed = False

        for item in source_items:
            normalized = _normalize_https_url(item)
            if normalized and _is_preview_host(normalized):
                next_item = _rewrite_url_to_base(normalized, _CURRENT_DOMAIN)
                rewritten_items.append(next_item)
                if next_item != item:
                    changed = True
            else:
                rewritten_items.append(item)

        if not changed:
            return

        deduped: list[str] = []
        for item in rewritten_items:
            if item not in deduped:
                deduped.append(item)

        next_value = ",".join(deduped)
        _update_env_line(key, next_value)
        logger.warning(f"Self-heal: {key} preview hosts synced to '{next_value}'")

    for key in [
        "SSO_CANONICAL_REDIRECT_BASE",
        "MS_SSO_CANONICAL_REDIRECT_BASE",
        "APPLE_SSO_CANONICAL_REDIRECT_BASE",
    ]:
        _rewrite_preview_url_key(key)

    for key in [
        "MS_SSO_REGISTERED_REDIRECT_URIS",
        "APPLE_SSO_REGISTERED_REDIRECT_URIS",
        "APPLE_SSO_PROVIDER_ACCEPTED_CALLBACK_BASES",
        "APPLE_SSO_PROVIDER_VERIFIED_REDIRECT_BASES",
    ]:
        _rewrite_preview_csv_key(key)


# Sync high-impact public URLs so real users never receive stale preview hosts.
_sync_env_url_key("RESET_LINK_BASE", "/auth/reset-password")
_sync_env_url_key("VERIFY_LINK_BASE", "/api/auth/verify")
_sync_env_url_key("GOOGLE_OAUTH_REDIRECT_URI", "/api/oauth/calendar/callback")
_sync_env_uri_list_key("MS_SSO_REGISTERED_REDIRECT_URIS")
_sync_env_uri_list_key("APPLE_SSO_REGISTERED_REDIRECT_URIS")
_sync_backend_preview_env_keys()
_sync_frontend_preview_env_keys()

if _env_dirty:
    _env_path.write_text(_env_text)

# Startup guard: fail fast if any stale preview host remains in env files.
assert_startup_preview_host_safety()

# Log SSO redirect URIs at startup for easy provider registration
_logger = logging.getLogger("server")
_logger.info("=== SSO Configuration ===")
_logger.info(f"Deployment domain: {_CURRENT_DOMAIN}")
_logger.info(f"Microsoft callback: {_CURRENT_DOMAIN}/api/auth/microsoft/callback")
_logger.info(f"Apple callback:     {_CURRENT_DOMAIN}/api/auth/apple/callback")
_logger.info("=========================")

_BOOT_INSTANCE_ID = f"{socket.gethostname()}:{uuid4().hex[:10]}"
_BOOTED_AT = datetime.now(timezone.utc).isoformat()

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

configure_structured_logging(service_name=str(os.environ.get("OBSERVABILITY_SERVICE_NAME") or "realaicoach-backend"))
logger = logging.getLogger(__name__)

# ── Application ──────────────────────────────────────────────────────────────

app = FastAPI(title="RealAICoach API")

FEATURE26_LEGACY_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FEATURE26_LEGACY_WRITE_PREFIXES = (
    "/jobs",
    "/employers",
    "/jobs-portal/jobs",
    "/jobs-portal/employers",
    "/api/jobs",
    "/api/employers",
    "/api/jobs-portal/jobs",
    "/api/jobs-portal/employers",
)
FEATURE26_LEGACY_READ_METHODS = {"GET", "HEAD"}

FEATURE26_LEGACY_READ_EXACT_PATHS = {
    "/api/jobs/my-posted",
    "/api/jobs/search",
    "/api/jobs/recommendations",
    "/api/jobs/my-applications",
    "/api/jobs/saved",
    "/api/jobs/profile",
    "/api/jobs/resume/score",
    "/api/jobs/analytics",
    "/api/jobs/portal-summary",
    "/api/jobs/employer/pipeline-board",
    "/api/jobs/employer/offers",
    "/api/jobs/employer/sla-alerts",
    "/api/jobs/employer/sla-auto-triggers",
    "/api/jobs/employer/kpi-header",
    "/api/jobs/employer/hiring-forecast",
    "/api/jobs/employer/talent-rediscovery",
    "/api/jobs/alerts",
    "/api/jobs/alerts/preferences",
    "/api/employers/my-application",
    "/api/employers/my-permissions",
    "/api/employers/admin/stats",
    "/api/employers/admin/applications",
    "/api/employers/admin/command-center",
    "/api/employers/reverify-status",
    "/api/jobs-portal/jobs/my-posted",
    "/api/jobs-portal/jobs/search",
    "/api/jobs-portal/jobs/recommendations",
    "/api/jobs-portal/jobs/my-applications",
    "/api/jobs-portal/jobs/saved",
    "/api/jobs-portal/jobs/profile",
    "/api/jobs-portal/jobs/resume/score",
    "/api/jobs-portal/jobs/analytics",
    "/api/jobs-portal/jobs/portal-summary",
    "/api/jobs-portal/jobs/employer/pipeline-board",
    "/api/jobs-portal/jobs/employer/offers",
    "/api/jobs-portal/jobs/employer/sla-alerts",
    "/api/jobs-portal/jobs/employer/sla-auto-triggers",
    "/api/jobs-portal/jobs/employer/kpi-header",
    "/api/jobs-portal/jobs/employer/hiring-forecast",
    "/api/jobs-portal/jobs/employer/talent-rediscovery",
    "/api/jobs-portal/jobs/alerts",
    "/api/jobs-portal/jobs/alerts/preferences",
    "/api/jobs-portal/employers/my-application",
    "/api/jobs-portal/employers/my-permissions",
    "/api/jobs-portal/employers/admin/stats",
    "/api/jobs-portal/employers/admin/applications",
    "/api/jobs-portal/employers/admin/command-center",
    "/api/jobs-portal/employers/reverify-status",
}

FEATURE26_LEGACY_READ_PREFIX_PATHS = (
    "/api/jobs/detail/",
    "/api/jobs/applicants/",
    "/api/jobs/employer/pipeline-board/",
    "/api/jobs/employer/copilot/",
    "/api/jobs/employer/scorecards/",
    "/api/jobs/employer/auto-scheduler/",
    "/api/jobs/employer/communication-sequences/",
    "/api/employers/documents/",
    "/api/employers/admin/application/",
    "/api/employers/admin/communications/",
    "/api/employers/messages/",
    "/api/jobs-portal/jobs/detail/",
    "/api/jobs-portal/jobs/applicants/",
    "/api/jobs-portal/jobs/employer/pipeline-board/",
    "/api/jobs-portal/jobs/employer/copilot/",
    "/api/jobs-portal/jobs/employer/scorecards/",
    "/api/jobs-portal/jobs/employer/auto-scheduler/",
    "/api/jobs-portal/jobs/employer/communication-sequences/",
    "/api/jobs-portal/employers/documents/",
    "/api/jobs-portal/employers/admin/application/",
    "/api/jobs-portal/employers/admin/communications/",
    "/api/jobs-portal/employers/messages/",
)


def _feature26_v2_replacement_hint(path: str) -> str:
    lowered = str(path or "").strip().lower()
    if "/jobs/apply" in lowered:
        return "/api/hiring/v2/candidate/apply"
    if "/jobs/save" in lowered:
        return "/api/hiring/v2/candidate/save/{job_id}"
    if "/jobs/profile/update" in lowered:
        return "/api/hiring/v2/candidate/profile/update"
    if "/jobs/resume/upload" in lowered:
        return "/api/hiring/v2/candidate/resume/upload"
    if "/jobs/employer/offers/build" in lowered:
        return "/api/hiring/v2/employer/offers/build"
    if "/jobs/employer/offers/" in lowered:
        return "/api/hiring/v2/employer/offers/{offer_id}/*"
    if "/jobs/employer/pipeline-board/bulk-action" in lowered:
        return "/api/hiring/v2/employer/pipeline/bulk-action"
    if "/jobs/employer/copilot/" in lowered:
        return "/api/hiring/v2/employer/pipeline/{application_id}/copilot-execute"
    return "/api/hiring/v2/*"


def _is_feature26_legacy_read_path(path: str) -> bool:
    normalized = (str(path or "").rstrip("/") or "/")
    if normalized in FEATURE26_LEGACY_READ_EXACT_PATHS:
        return True
    return any(normalized.startswith(prefix) for prefix in FEATURE26_LEGACY_READ_PREFIX_PATHS)


def _feature26_v2_read_replacement_hint(path: str) -> str:
    lowered = str(path or "").strip().lower()
    if "/jobs/my-posted" in lowered:
        return "/api/hiring/v2/employer/jobs"
    if "/jobs/search" in lowered:
        return "/api/hiring/v2/candidate/jobs/search"
    if "/jobs/detail/" in lowered:
        return "/api/hiring/v2/candidate/jobs/detail/{job_id}"
    if "/jobs/recommendations" in lowered:
        return "/api/hiring/v2/candidate/recommendations"
    if "/jobs/my-applications" in lowered:
        return "/api/hiring/v2/candidate/applications"
    if "/jobs/saved" in lowered:
        return "/api/hiring/v2/candidate/saved-jobs"
    if "/jobs/profile" in lowered:
        return "/api/hiring/v2/candidate/profile"
    if "/jobs/resume/score" in lowered:
        return "/api/hiring/v2/candidate/resume-score"
    if "/jobs/analytics" in lowered:
        return "/api/hiring/v2/candidate/analytics"
    if "/jobs/portal-summary" in lowered:
        return "/api/hiring/v2/dashboard/summary"
    if "/jobs/applicants/" in lowered:
        return "/api/hiring/v2/employer/applicants/{job_id}"
    if "/jobs/employer/pipeline-board/" in lowered and "/timeline" in lowered:
        return "/api/hiring/v2/employer/pipeline-board/{application_id}/timeline"
    if "/jobs/employer/pipeline-board/" in lowered and "/audit-export.csv" in lowered:
        return "/api/hiring/v2/employer/pipeline-board/{application_id}/audit-export.csv"
    if "/jobs/employer/pipeline-board/" in lowered and "/audit-export.pdf" in lowered:
        return "/api/hiring/v2/employer/pipeline-board/{application_id}/audit-export.pdf"
    if "/jobs/employer/pipeline-board/" in lowered and "/audit-download-history" in lowered:
        return "/api/hiring/v2/employer/pipeline-board/{application_id}/audit-download-history"
    if "/jobs/employer/pipeline-board" in lowered:
        return "/api/hiring/v2/employer/pipeline-board"
    if "/jobs/employer/offers" in lowered:
        return "/api/hiring/v2/employer/offers"
    if "/jobs/employer/sla-alerts" in lowered:
        return "/api/hiring/v2/employer/sla-alerts"
    if "/jobs/employer/sla-auto-triggers" in lowered:
        return "/api/hiring/v2/employer/sla-auto-triggers"
    if "/jobs/employer/kpi-header" in lowered:
        return "/api/hiring/v2/employer/kpi-header"
    if "/jobs/employer/copilot/" in lowered:
        return "/api/hiring/v2/employer/copilot/{application_id}/suggestions"
    if "/jobs/employer/scorecards/" in lowered:
        return "/api/hiring/v2/employer/scorecards/{application_id}"
    if "/jobs/employer/auto-scheduler/" in lowered:
        return "/api/hiring/v2/employer/auto-scheduler/{application_id}/suggest"
    if "/jobs/employer/communication-sequences/" in lowered:
        return "/api/hiring/v2/employer/communication-sequences/{application_id}"
    if "/jobs/employer/hiring-forecast" in lowered:
        return "/api/hiring/v2/employer/hiring-forecast"
    if "/jobs/employer/talent-rediscovery" in lowered:
        return "/api/hiring/v2/employer/talent-rediscovery"
    if lowered.endswith("/jobs/alerts"):
        return "/api/hiring/v2/candidate/alerts"
    if lowered.endswith("/jobs/alerts/preferences"):
        return "/api/hiring/v2/candidate/alerts/preferences"
    if "/employers/my-application" in lowered:
        return "/api/hiring/v2/employer/application/current"
    if "/employers/my-permissions" in lowered:
        return "/api/hiring/v2/employer/application/permissions"
    if "/employers/reverify-status" in lowered:
        return "/api/hiring/v2/employer/application/reverify-status"
    if "/employers/messages/" in lowered:
        return "/api/hiring/v2/employer/application/messages/{employer_id}"
    if "/employers/documents/" in lowered:
        return "/api/hiring/v2/employer/application/documents/{employer_id}/{doc_id}/download"
    if "/employers/admin/stats" in lowered:
        return "/api/hiring/v2/admin/employers/stats"
    if "/employers/admin/applications" in lowered:
        return "/api/hiring/v2/admin/employers/applications"
    if "/employers/admin/application/" in lowered:
        return "/api/hiring/v2/admin/employers/application/{employer_id}"
    if "/employers/admin/command-center" in lowered:
        return "/api/hiring/v2/admin/employers/command-center"
    if "/employers/admin/communications/" in lowered:
        return "/api/hiring/v2/admin/employers/communications/{employer_id}"
    return "/api/hiring/v2/*"


@app.middleware("http")
async def feature26_hard_retire_legacy_v1_writes(request: Request, call_next):
    method = str(request.method or "").upper()
    path = str(request.url.path or "")
    if method in FEATURE26_LEGACY_WRITE_METHODS and any(path.startswith(prefix) for prefix in FEATURE26_LEGACY_WRITE_PREFIXES):
        route_family = "employers" if ("/employers" in path or "/jobs-portal/employers" in path) else "jobs"
        return JSONResponse(
            status_code=410,
            content={
                "detail": {
                    "message": f"Legacy /api/{route_family} write endpoint is permanently retired. Use v2 routes.",
                    "feature_number": 26,
                    "feature_id": "jobs-portal",
                    "route_family": route_family,
                    "retirement_mode": "hard_retired",
                    "retirement_phase": "hard_retired_cleanup",
                    "replacement_hint": _feature26_v2_replacement_hint(path),
                }
            },
        )
    return await call_next(request)


@app.middleware("http")
async def feature26_hard_retire_legacy_v1_reads(request: Request, call_next):
    method = str(request.method or "").upper()
    path = str(request.url.path or "")
    if method in FEATURE26_LEGACY_READ_METHODS and _is_feature26_legacy_read_path(path):
        route_family = "employers" if ("/employers" in path or "/jobs-portal/employers" in path) else "jobs"
        return JSONResponse(
            status_code=410,
            content={
                "detail": {
                    "message": f"Legacy /api/{route_family} read endpoint is permanently retired. Use v2 routes.",
                    "feature_number": 26,
                    "feature_id": "jobs-portal",
                    "route_family": route_family,
                    "retirement_mode": "hard_retired",
                    "retirement_phase": "hard_retired_read_cleanup",
                    "replacement_hint": _feature26_v2_read_replacement_hint(path),
                    "legacy_retirement_enabled": True,
                }
            },
        )
    return await call_next(request)

configure_open_telemetry(
    app,
    service_name=str(os.environ.get("OBSERVABILITY_SERVICE_NAME") or "realaicoach-backend"),
)

# ── GTEC Global System Directive (fail-fast on boot + response headers) ─────
from middleware_gtec_directive import (
    enforce_directive_on_boot,
    GtecDirectiveMiddleware,
    public_router as gtec_directive_public_router,
)
enforce_directive_on_boot()  # RuntimeError if directive file missing/truncated
app.add_middleware(GtecDirectiveMiddleware)
# Global PDF v15 policy middleware retired 2026-07 per platform owner directive:
# PDFs are served exactly as generated — no global overlay/stamping.

# ── Middleware ────────────────────────────────────────────────────────────────

from middleware import register as register_middleware

register_middleware(app)

# API v1 versioning shim (outermost): /api/v1/* → /api/* with X-API-Version header.
from middleware_api_versioning import APIVersionRewriteMiddleware
app.add_middleware(APIVersionRewriteMiddleware)

# ── API Router ───────────────────────────────────────────────────────────────

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "RealAICoach API - Social Skills Coach"}


@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "RealAICoach API"}


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def root_health_check():
    """Root-level health endpoint for platform/Kubernetes probes (they hit GET /health,
    not /api/health). Unauthenticated, same payload as /api/health."""
    return {"status": "healthy", "service": "RealAICoach API"}


@api_router.get("/system/instance-marker")
async def system_instance_marker():
    """Deterministic runtime marker to validate external-vs-local routing parity."""
    return {
        "instance_id": _BOOT_INSTANCE_ID,
        "booted_at": _BOOTED_AT,
        "hostname": socket.gethostname(),
        "current_domain": _CURRENT_DOMAIN,
        "app_url": str(os.environ.get("APP_URL") or "").strip(),
        "frontend_base_url": str(os.environ.get("FRONTEND_BASE_URL") or "").strip(),
    }


@api_router.get("/system/health")
async def system_health():
    """Comprehensive health check — DB connectivity, memory, uptime, services."""
    import psutil
    import time

    checks = {}
    overall = "healthy"

    # DB connectivity
    try:
        await db.command("ping")
        checks["database"] = {"status": "up", "type": "MongoDB"}
    except Exception as e:
        checks["database"] = {"status": "down", "error": str(e)}
        overall = "degraded"

    # Memory
    mem = psutil.virtual_memory()
    checks["memory"] = {
        "total_mb": round(mem.total / 1048576),
        "used_mb": round(mem.used / 1048576),
        "percent": mem.percent,
        "status": "ok" if mem.percent < 90 else "warning",
    }

    # CPU
    checks["cpu"] = {"percent": psutil.cpu_percent(interval=0.1), "status": "ok"}

    # Uptime
    boot = psutil.boot_time()
    uptime_sec = time.time() - boot
    checks["uptime"] = {
        "seconds": int(uptime_sec),
        "human": f"{int(uptime_sec // 3600)}h {int((uptime_sec % 3600) // 60)}m",
    }

    # WebSocket connections
    from utils.ws_manager import ws_manager

    checks["websockets"] = {
        "authenticated_users": len(ws_manager.connections),
        "total_connections": ws_manager.active_count,
        "public_listeners": len(ws_manager.public_stream),
    }

    # Collections count
    try:
        colls = await db.list_collection_names()
        checks["collections"] = len(colls)
    except Exception:
        checks["collections"] = "unknown"

    return {"status": overall, "service": "RealAICoach API", "checks": checks}


@api_router.get("/admin/system/integrity")
async def admin_integrity_scans(request: Request):
    """Get latest integrity scan results (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    scans = await db.integrity_scans.find({}, {"_id": 0}).sort("timestamp", -1).to_list(10)
    return {"scans": scans, "total": len(scans)}


@api_router.get("/admin/system/backups")
async def admin_backup_status(request: Request):
    """Get backup history (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    backups = await db.backup_history.find({}, {"_id": 0}).sort("timestamp", -1).to_list(10)
    return {"backups": backups, "total": len(backups)}


@api_router.post("/admin/system/integrity/run")
async def admin_run_integrity_scan(request: Request):
    """Manually trigger an integrity scan (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    from scheduler import scheduler

    job = scheduler.get_job("nightly_integrity_scan")
    if job:
        job.modify(next_run_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        return {"status": "triggered", "message": "Integrity scan will run momentarily"}
    return {"status": "error", "message": "Scan job not found"}


@api_router.post("/admin/system/backups/run")
async def admin_run_backup(request: Request):
    """Manually trigger a backup (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    from scheduler import scheduler

    job = scheduler.get_job("nightly_auto_backup")
    if job:
        job.modify(next_run_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        return {"status": "triggered", "message": "Backup will run momentarily"}
    return {"status": "error", "message": "Backup job not found"}


# ── Anomaly Detection Engine ──────────────────────────────────────────────
@api_router.get("/admin/activity-log/anomalies")
async def admin_anomaly_detection(request: Request):
    """Detect suspicious patterns in security events (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    return await detect_admin_anomalies(db)


async def _run_anomaly_detection():
    return await detect_alerting_anomalies(db)


async def run_anomaly_alert_check():
    await _run_server_anomaly_alert_check(db)


@api_router.get("/admin/anomaly-alerts")
async def get_anomaly_alerts(request: Request, limit: int = 50):
    """Get anomaly alert history (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    alerts = await db.anomaly_alerts.find({}, {"_id": 0}).sort("alerted_at", -1).limit(limit).to_list(limit)
    return {"alerts": alerts, "total": len(alerts)}


@api_router.get("/admin/anomaly-alerts/settings")
async def get_anomaly_alert_settings(request: Request):
    """Get anomaly alert settings (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    settings = await db.anomaly_alert_settings.find_one({"key": "settings"}, {"_id": 0})
    if not settings:
        settings = {"key": "settings", "enabled": True, "email_enabled": True, "min_severity": "high"}
    return settings


@api_router.put("/admin/anomaly-alerts/settings")
async def update_anomaly_alert_settings(request: Request):
    """Update anomaly alert settings (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    body = await request.json()
    allowed = {"enabled", "email_enabled", "min_severity"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if "min_severity" in updates and updates["min_severity"] not in ("critical", "high", "medium", "low"):
        updates["min_severity"] = "high"
    await db.anomaly_alert_settings.update_one({"key": "settings"}, {"$set": updates}, upsert=True)
    settings = await db.anomaly_alert_settings.find_one({"key": "settings"}, {"_id": 0})
    return settings


@api_router.post("/admin/anomaly-alerts/test")
async def test_anomaly_alert(request: Request):
    """Manually trigger anomaly detection and alerting (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    await run_anomaly_alert_check()
    return {"status": "ok", "message": "Anomaly alert check triggered"}


# ── Activity Log (Security Events) ──────────────────────────────────────
@api_router.get("/admin/activity-log")
async def admin_activity_log(
    request: Request,
    page: int = 1,
    per_page: int = 50,
    event_type: str = None,
    risk_level: str = None,
    user_id: str = None,
    date_from: str = None,
    date_to: str = None,
):
    """Get paginated security activity log with filters (admin only)."""
    from routes.db import require_admin

    await require_admin(request)

    return await fetch_admin_activity_log_payload(
        db,
        page=page,
        per_page=per_page,
        event_type=event_type,
        risk_level=risk_level,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )


@api_router.get("/admin/activity-log/export/csv")
async def admin_activity_log_export_csv(
    request: Request,
    event_type: str = None,
    risk_level: str = None,
    user_id: str = None,
    date_from: str = None,
    date_to: str = None,
):
    """Export security activity log as CSV (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    from starlette.responses import Response as StarletteResponse
    filename, payload = await render_activity_log_csv(
        db,
        event_type=event_type,
        risk_level=risk_level,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )
    return StarletteResponse(
        content=payload,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/admin/activity-log/export/pdf")
async def admin_activity_log_export_pdf(
    request: Request,
    event_type: str = None,
    risk_level: str = None,
    user_id: str = None,
    date_from: str = None,
    date_to: str = None,
):
    """Export security activity log as PDF (admin only)."""
    from routes.db import require_admin

    await require_admin(request)
    from starlette.responses import Response as StarletteResponse
    filename, payload = await render_activity_log_pdf(
        db,
        event_type=event_type,
        risk_level=risk_level,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )
    return StarletteResponse(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _format_period_label(value: datetime, range_key: str) -> str:
    if range_key == "12m":
        return value.strftime("%b")
    if range_key == "90d":
        return value.strftime("%b %d")
    return value.strftime("%d %b")


def _build_growth_intelligence_payload(now: datetime, source_metrics: dict, authenticated: bool) -> dict:
    performance_boost = max(12, min(99, int(source_metrics.get("performance_boost") or 0)))
    active_users = max(120, int(source_metrics.get("active_users") or 0))
    ai_sessions_today = max(40, int(source_metrics.get("ai_sessions_today") or 0))
    global_coaches = max(12, int(source_metrics.get("global_coaches") or 0))
    users_online = max(18, int(source_metrics.get("users_online") or 0))
    system_health = max(68, min(100, int(source_metrics.get("system_health") or 0)))
    baseline_growth = max(8, performance_boost - 12)
    headline_delta = max(6, min(28, performance_boost - baseline_growth + 4))

    milestone_titles = [
        "Workflow activation launched",
        "Manager coaching cadence improved",
        "Team completion lift sustained",
        "Retention-linked adoption spike",
    ]

    range_configs = {
        "30d": {"points": 6, "step_days": 5, "label": "30D", "comparison_label": "Previous 30-day baseline"},
        "90d": {"points": 7, "step_days": 14, "label": "90D", "comparison_label": "Quarterly team baseline"},
        "12m": {"points": 12, "step_days": 30, "label": "12M", "comparison_label": "Annual industry benchmark"},
    }

    ranges = {}
    for range_idx, (range_key, config) in enumerate(range_configs.items()):
        points = []
        total_points = config["points"]
        step_days = config["step_days"]
        for idx in range(total_points):
            progress = idx / max(total_points - 1, 1)
            period_start = now - timedelta(days=step_days * (total_points - idx - 1))
            wave = ((idx % 4) - 1.5) * (1.8 if range_key == "12m" else 2.6)
            late_boost = 4 if idx >= total_points - 2 else 0
            growth_score = int(max(14, min(98, round(baseline_growth + (performance_boost - baseline_growth) * (0.58 + progress * 0.46) + wave + late_boost))))
            benchmark_score = int(max(10, min(92, round(growth_score - 8 - (idx % 3) - (0 if authenticated else 2)))))
            active_value = int(round(active_users * (0.58 + progress * 0.64 + ((idx % 3) * 0.025))))
            session_value = int(round(ai_sessions_today * (0.74 + progress * 0.82 + ((idx % 4) * 0.035))))
            completion_rate = int(max(48, min(99, round(system_health * 0.68 + progress * 16 + (idx % 4)))))
            conversion_velocity = int(max(18, min(96, round(completion_rate - 14 + (idx % 3) * 2 + progress * 8))))
            milestone = None
            if idx in {max(1, total_points // 3), max(2, total_points - 2)}:
                milestone = {
                    "title": milestone_titles[(idx + range_idx) % len(milestone_titles)],
                    "impact_label": f"+{max(6, min(18, growth_score - benchmark_score))}% lift",
                }
            points.append(
                {
                    "label": _format_period_label(period_start, range_key),
                    "period_start": period_start.isoformat(),
                    "growth_score": growth_score,
                    "benchmark_score": benchmark_score,
                    "active_users": active_value,
                    "ai_sessions": session_value,
                    "completion_rate": completion_rate,
                    "conversion_velocity": conversion_velocity,
                    "milestone": milestone,
                }
            )

        strongest = max(points, key=lambda point: point["growth_score"])
        weakest = min(points, key=lambda point: point["growth_score"])
        momentum_delta = points[-1]["growth_score"] - points[0]["growth_score"]
        ranges[range_key] = {
            "label": config["label"],
            "comparison_label": config["comparison_label"],
            "points": points,
            "strongest_period_label": strongest["label"],
            "weakest_period_label": weakest["label"],
            "momentum_delta": momentum_delta,
            "forecast_teaser": f"Maintain the current completion rhythm to unlock another +{max(9, min(24, momentum_delta + 8))}% efficiency upside.",
        }

    current_range = ranges["90d"]
    return {
        "headline_metric": {
            "label": "Growth efficiency",
            "value": performance_boost,
            "unit": "%",
            "delta_vs_baseline": headline_delta,
        },
        "benchmark_value": baseline_growth,
        "confidence": {
            "score": max(72, min(99, system_health - 2)),
            "label": "Validated across live coaching workflows" if authenticated else "Modeled from live platform telemetry",
        },
        "narrative_summary": "Momentum accelerated after workflow activation and stayed above baseline across adoption, session velocity, and completion consistency.",
        "premium_teaser": "Premium unlock reveals forecast confidence, retention correlation, and team-level benchmark deltas.",
        "proof_points": [
            {"label": "Users online now", "value": users_online, "tone": "accent"},
            {"label": "Active coaching seats", "value": active_users, "tone": "indigo"},
            {"label": "AI sessions today", "value": ai_sessions_today, "tone": "warning"},
            {"label": "Coach network", "value": global_coaches, "tone": "success"},
        ],
        "ranges": ranges,
        "default_range": "90d",
        "current_momentum_label": f"+{current_range['momentum_delta']} pts vs period start",
    }


@api_router.get("/system/live-metrics")
async def live_metrics(mode: str = Query(default="standard"), request: Request = None):
    """Public-safe endpoint for real-time vanity KPIs. Sensitive fields require auth.

    Modes:
      - `standard` (default): single JSON snapshot
      - `stream`: same JSON snapshot (kept for backward-compat — name is
        legacy, it is NOT a streaming content-type)
      - `sse`: proper `text/event-stream` Server-Sent Events response.
        Emits the current snapshot as a single `data:` event then ends the
        stream. EventSource clients will auto-reconnect, effectively giving
        a tick every `retry:` ms (see `SSE_RETRY_MS` below) without holding
        a long-lived connection.
    """
    from utils.public_rate_limits import enforce_public_rate_limit
    from routes.home_dashboard import _generate_vanity_metrics
    from routes.db import get_current_user

    blocked = enforce_public_rate_limit(request, "system_live_metrics", 180, 60)
    if blocked:
        return blocked

    mode_norm = str(mode).lower()
    stream_mode = mode_norm in ("stream", "sse")
    sse_mode = mode_norm == "sse"
    vanity = _generate_vanity_metrics(stream=stream_mode)
    now = datetime.now(timezone.utc)

    # Authenticated users get full KPIs; unauthenticated get vanity-only
    user = None
    if request:
        try:
            user = await get_current_user(request)
        except Exception:
            pass

    base_response = {
        "mode": mode_norm if mode_norm in ("stream", "sse") else "standard",
        "metric_source": {
            "vanity": "synthetic_generator",
            "kpis": "vanity_public",
            "realtime_kpis": "unavailable_without_auth",
            "growth_intelligence": "modeled_public_safe",
        },
        "vanity": {
            "active_users": vanity["active_users"],
            "ai_sessions_today": vanity["ai_sessions_today"],
            "global_coaches": vanity["global_coaches"],
            "performance_boost": vanity["performance_boost"],
            "users_online": vanity["users_online"],
            "system_health": vanity["system_health"],
        },
        "timestamp": now.isoformat(),
    }

    if not user:
        # Public: vanity metrics only — no internal KPIs, no AI load, no activity
        base_response["kpis"] = {
            "active_users": vanity["active_users"],
            "users_online": vanity["users_online"],
            "ai_sessions_today": vanity["ai_sessions_today"],
            "global_coaches": vanity["global_coaches"],
            "performance_boost": vanity["performance_boost"],
            "system_health": vanity["system_health"],
        }
        base_response["ai_load"] = {}
        base_response["recent_activity"] = []
        base_response["kpis_realtime"] = {}
        base_response["growth_intelligence"] = _build_growth_intelligence_payload(now, base_response["kpis"], authenticated=False)
        if sse_mode:
            return _sse_payload_response(base_response)
        return base_response

    # Authenticated: full data
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    last_24h = (now - timedelta(hours=24)).isoformat()

    try:
        total_users = await db.users.count_documents({})
        coaches_count = await db.users.count_documents({"$or": [{"role": "coach"}, {"platform_role": "coach"}]})
        goals_completed = await db.ai_goal_events.count_documents(
            {"event_type": "milestone_completed", "created_at": {"$gte": today_start}}
        )
    except Exception:
        total_users = 0
        coaches_count = 0
        goals_completed = 0

    activity = []
    try:
        events = (
            await db.security_events.find(
                {"created_at": {"$gte": last_24h}},
                {"_id": 0, "event_type": 1, "created_at": 1},
            )
            .sort("created_at", -1)
            .limit(6)
            .to_list(6)
        )
        for e in events:
            etype = e.get("event_type", "event").replace("_", " ").title()
            activity.append({"type": etype, "time": e.get("created_at", "")})
    except Exception:
        pass

    try:
        chat_count = await db.ai_chat_sessions.count_documents({"created_at": {"$gte": last_24h}})
        goal_count = await db.ai_goals.count_documents({"created_at": {"$gte": last_24h}})
        notif_count = await db.notifications.count_documents({"created_at": {"$gte": last_24h}})
        active_sessions = await db.user_sessions.count_documents(
            {
                "created_at": {"$gte": last_24h},
                "$or": [
                    {"revoked": {"$exists": False}},
                    {"revoked": False},
                ],
            }
        )
    except Exception:
        chat_count = goal_count = notif_count = active_sessions = 0

    max_load = max(chat_count, goal_count, notif_count, 1)

    realtime_kpis = {
        "active_users": total_users,
        "users_online": active_sessions,
        "ai_sessions_today": chat_count,
        "global_coaches": coaches_count,
        "performance_boost": min(99, max(0, int((goal_count / max(chat_count, 1)) * 100))) if chat_count > 0 else 0,
        "system_health": vanity["system_health"],
        "total_users": total_users,
        "goals_completed_today": goals_completed,
    }
    base_response["kpis"] = realtime_kpis
    base_response["kpis_realtime"] = realtime_kpis
    base_response["metric_source"] = {
        **base_response["metric_source"],
        "kpis": "database_aggregates",
        "realtime_kpis": "database_aggregates",
    }
    base_response["ai_load"] = {
        "nlp_engine": min(int(chat_count / max_load * 100) + 40, 99),
        "goal_tracking": min(int(goal_count / max_load * 100) + 50, 99),
        "career_coach": min(int(chat_count / max_load * 80) + 30, 99),
        "team_sync": min(int(notif_count / max_load * 70) + 45, 99),
        "analytics": min(int((chat_count + goal_count) / max_load * 60) + 55, 99),
    }
    base_response["recent_activity"] = activity[:6]
    base_response["growth_intelligence"] = _build_growth_intelligence_payload(now, realtime_kpis, authenticated=True)
    base_response["metric_source"] = {
        **base_response["metric_source"],
        "growth_intelligence": "database_aggregates_modeled_story",
    }

    if sse_mode:
        return _sse_payload_response(base_response)
    return base_response


@api_router.get("/system/vanity-metrics")
async def vanity_metrics(mode: str = Query(default="standard"), request: Request = None):
    """Public endpoint returning cached random platform metrics (45s TTL). No auth required."""
    from routes.home_dashboard import _generate_vanity_metrics
    from utils.public_rate_limits import enforce_public_rate_limit

    blocked = enforce_public_rate_limit(request, "system_vanity_metrics", 120, 60)
    if blocked:
        return blocked

    return _generate_vanity_metrics(stream=(str(mode).lower() == "stream"))


@api_router.get("/admin/system/public-rate-limit-stats")
async def admin_public_rate_limit_stats(request: Request):
    """Admin telemetry endpoint to tune public endpoint throttling."""
    from routes.db import require_admin
    from utils.public_rate_limits import get_public_rate_limit_stats, PUBLIC_RATE_LIMIT_RULES

    await require_admin(request)
    return {
        "stats": get_public_rate_limit_stats(),
        "rules": {
            key: {"limit": value[0], "window_seconds": value[1]}
            for key, value in PUBLIC_RATE_LIMIT_RULES.items()
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/admin/security/db-hardening/status")
async def admin_db_hardening_status(request: Request):
    from routes.db import require_admin

    await require_admin(request)
    return {
        "status": await get_db_security_hardening_status(db),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/system/status")
async def system_status():
    """Enterprise system status — comprehensive health check."""
    now = datetime.now(timezone.utc)
    checks = {}
    try:
        await db.command("ping")
        user_count = await db.users.count_documents({})
        checks["database"] = {"status": "healthy", "users": user_count}
    except Exception as e:
        checks["database"] = {"status": "error", "error": str(e)}

    critical_job_ids = [
        "gtec_scan_c5_safe_auto_run",
        "gtec_c5_continuous_trust_monitor",
        "gtec_c5_boundary_go_no_go_drill",
        "db_security_hardening_pass",
        "gtec_crawler_safe_auto_run",
        "gtec_upstream_watchdog_nightly",
        "enterprise_reality_validation_guardian",
        "zero_trust_auto_mitigation",
        "active_defense_nightly_scan",
    ]
    registered_jobs: list[str] = []
    try:
        from scheduler import scheduler as platform_scheduler
        for jid in critical_job_ids:
            if platform_scheduler.get_job(jid):
                registered_jobs.append(jid)
    except Exception as e:
        checks["scheduler"] = {"status": "error", "error": str(e)}
    else:
        checks["scheduler"] = {
            "status": "healthy" if len(registered_jobs) == len(critical_job_ids) else "degraded",
            "critical_jobs_registered": len(registered_jobs),
            "critical_jobs_total": len(critical_job_ids),
            "missing_jobs": [jid for jid in critical_job_ids if jid not in registered_jobs],
        }

    def _parse_iso(ts: str | None):
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return None

    # Truthful runtime signal for the enterprise autonomous engine.
    v2_interval = 3
    v2_doc = await db.gtec_scan_c5_settings.find_one({"_id": "schedule"}, {"_id": 0})
    if not v2_doc:
        v2_doc = await db.gtec_scan_v2_settings.find_one({"_id": "schedule"}, {"_id": 0})
    if v2_doc:
        v2_interval = int(v2_doc.get("interval_hours") or 3)

    v2_latest = await db.gtec_scan_c5_reports.find_one(
        {"triggered_by": "scheduler"},
        {"_id": 0, "task_id": 1, "generated_at": 1, "status": 1},
        sort=[("generated_at", -1)],
    )
    if not v2_latest:
        v2_latest = await db.gtec_scan_v2_reports.find_one(
            {"triggered_by": "scheduler"},
            {"_id": 0, "task_id": 1, "generated_at": 1, "status": 1},
            sort=[("generated_at", -1)],
        )
    crawler_latest = await db.gtec_crawler_runs.find_one(
        {"triggered_by": "scheduler"},
        {"_id": 0, "job_id": 1, "created_at": 1, "status": 1},
        sort=[("created_at", -1)],
    )
    v2_heartbeat = await db.scheduler_heartbeats.find_one(
        {"job_id": "gtec_scan_c5_safe_auto_run"},
        {"_id": 0, "last_run": 1, "status": 1, "details": 1},
    )
    if not v2_heartbeat:
        v2_heartbeat = await db.scheduler_heartbeats.find_one(
            {"job_id": "gtec_scan_v2_safe_auto_run"},
            {"_id": 0, "last_run": 1, "status": 1, "details": 1},
        )
    crawler_heartbeat = await db.scheduler_heartbeats.find_one(
        {"job_id": "gtec_crawler_safe_auto_run"},
        {"_id": 0, "last_run": 1, "status": 1, "details": 1},
    )
    guardian_state = await db.enterprise_autonomous_engine_guardian_state.find_one(
        {"_id": "state"},
        {"_id": 0},
    )
    watchdog_latest = await db.gtec_upstream_watchdog_runs.find_one(
        {},
        {"_id": 0, "checked_at": 1, "errors": 1, "still_blocked": 1, "cleared": 1},
        sort=[("checked_at", -1)],
    )
    engine_cfg = await db.autonomous_engine_config.find_one(
        {"config_id": "global"},
        {"_id": 0, "zero_trust_policy": 1, "active_defense_nightly_policy": 1},
    )
    zt_policy = (engine_cfg or {}).get("zero_trust_policy") or {}
    zt_nightly_policy = (engine_cfg or {}).get("active_defense_nightly_policy") or {}
    zt_interval_minutes = max(5, min(60, int(zt_policy.get("interval_minutes") or 10)))

    zt_auto_hb = await db.scheduler_heartbeats.find_one(
        {"job_id": "zero_trust_auto_mitigation"},
        {"_id": 0, "last_run": 1, "status": 1, "detail": 1},
    )
    zt_nightly_hb = await db.scheduler_heartbeats.find_one(
        {"job_id": "active_defense_nightly_scan"},
        {"_id": 0, "last_run": 1, "status": 1, "detail": 1},
    )
    zt_latest_run = await db.zero_trust_mitigation_runs.find_one(
        {},
        {
            "_id": 0,
            "run_id": 1,
            "executed_at": 1,
            "status": 1,
            "triggered_by": 1,
            "signals.threat_level": 1,
            "signals.threat_score": 1,
            "actions.applied": 1,
            "actions.queued": 1,
        },
        sort=[("executed_at", -1)],
    )
    zt_latest_scan = await db.active_defense_scans.find_one(
        {},
        {
            "_id": 0,
            "scan_id": 1,
            "completed_at": 1,
            "zero_trust_status": 1,
            "threat_level": 1,
            "confidence": 1,
            "pass_count": 1,
            "total_checks": 1,
            "sections.sast.status": 1,
            "sections.sast.findings_count": 1,
        },
        sort=[("completed_at", -1)],
    )
    zt_latest_nightly = await db.active_defense_nightly_runs.find_one(
        {},
        {
            "_id": 0,
            "run_id": 1,
            "completed_at": 1,
            "zero_trust_status": 1,
            "pass_count": 1,
            "total_checks": 1,
            "email": 1,
        },
        sort=[("completed_at", -1)],
    )

    v2_heartbeat_ts = _parse_iso((v2_heartbeat or {}).get("last_run"))
    crawler_heartbeat_ts = _parse_iso((crawler_heartbeat or {}).get("last_run"))
    v2_run_ts = _parse_iso((v2_latest or {}).get("generated_at"))
    crawler_run_ts = _parse_iso((crawler_latest or {}).get("created_at"))
    watchdog_ts = _parse_iso((watchdog_latest or {}).get("checked_at"))
    guardian_ts = _parse_iso((guardian_state or {}).get("last_checked_at"))
    zt_auto_hb_ts = _parse_iso((zt_auto_hb or {}).get("last_run"))
    zt_nightly_hb_ts = _parse_iso((zt_nightly_hb or {}).get("last_run"))
    zt_latest_run_ts = _parse_iso((zt_latest_run or {}).get("executed_at"))
    zt_latest_scan_ts = _parse_iso((zt_latest_scan or {}).get("completed_at"))
    zt_latest_nightly_ts = _parse_iso((zt_latest_nightly or {}).get("completed_at"))

    # Freshness is derived from scheduler heartbeats so skipped idempotent
    # ticks still count as "active".
    v2_fresh = bool(v2_heartbeat_ts and (now - v2_heartbeat_ts).total_seconds() <= (2 * 3600))
    crawler_fresh = bool(crawler_heartbeat_ts and (now - crawler_heartbeat_ts).total_seconds() <= (7 * 3600))
    watchdog_fresh = bool(watchdog_ts and (now - watchdog_ts).total_seconds() <= (26 * 3600))
    guardian_fresh = bool(guardian_ts and (now - guardian_ts).total_seconds() <= (12 * 60))

    engine_reasons: list[str] = []
    if "gtec_scan_c5_safe_auto_run" not in registered_jobs:
        engine_reasons.append("gtec_scan_c5_safe_auto_run_not_registered")
    if "gtec_crawler_safe_auto_run" not in registered_jobs:
        engine_reasons.append("gtec_crawler_safe_auto_run_not_registered")
    if "gtec_upstream_watchdog_nightly" not in registered_jobs:
        engine_reasons.append("gtec_upstream_watchdog_nightly_not_registered")
    if not v2_fresh:
        engine_reasons.append("gtec_scan_c5_scheduler_heartbeat_stale_or_missing")
    if not crawler_fresh:
        engine_reasons.append("gtec_crawler_scheduler_heartbeat_stale_or_missing")
    if not watchdog_fresh:
        engine_reasons.append("gtec_watchdog_run_stale_or_missing")
    if not guardian_fresh:
        engine_reasons.append("enterprise_reality_validation_guardian_stale_or_missing")

    engine_active = len(engine_reasons) == 0
    checks["enterprise_autonomous_engine"] = {
        "status": "healthy" if engine_active else "degraded",
        "policy": {
            "safe_auto_runs": "always_active",
            "non_disableable": True,
        },
        "safe_auto_runs_active": bool(v2_fresh and crawler_fresh),
        "components": {
            "gtec_scan_c5": {
                "configured_interval_hours": v2_interval,
                "last_scheduler_heartbeat_at": (v2_heartbeat or {}).get("last_run"),
                "last_scheduler_heartbeat_status": (v2_heartbeat or {}).get("status"),
                "last_scheduler_heartbeat_details": (v2_heartbeat or {}).get("details") or {},
                "last_scheduler_run_at": (v2_latest or {}).get("generated_at"),
                "last_scheduler_status": (v2_latest or {}).get("status"),
                "last_scheduler_run_fresh": bool(
                    v2_run_ts and (now - v2_run_ts).total_seconds() <= (max(v2_interval + 1, 2) * 3600)
                ),
                "fresh": v2_fresh,
            },
            "gtec_crawler": {
                "configured_interval_hours": 6,
                "last_scheduler_heartbeat_at": (crawler_heartbeat or {}).get("last_run"),
                "last_scheduler_heartbeat_status": (crawler_heartbeat or {}).get("status"),
                "last_scheduler_heartbeat_details": (crawler_heartbeat or {}).get("details") or {},
                "last_scheduler_run_at": (crawler_latest or {}).get("created_at"),
                "last_scheduler_status": (crawler_latest or {}).get("status"),
                "last_scheduler_run_fresh": bool(
                    crawler_run_ts and (now - crawler_run_ts).total_seconds() <= (7 * 3600)
                ),
                "fresh": crawler_fresh,
            },
            "gtec_upstream_watchdog": {
                "last_run_at": (watchdog_latest or {}).get("checked_at"),
                "fresh": watchdog_fresh,
            },
            "enterprise_reality_validation_guardian": {
                "last_checked_at": (guardian_state or {}).get("last_checked_at"),
                "last_status": (guardian_state or {}).get("status"),
                "last_reasons": (guardian_state or {}).get("last_reasons") or [],
                "last_actions": (guardian_state or {}).get("last_actions") or [],
                "fresh": guardian_fresh,
            },
        },
        "reasons": engine_reasons,
    }

    checks["reality_validation"] = {
        "status": "healthy" if engine_active else "degraded",
        "method": "runtime-heartbeats-plus-scheduler-registry",
        "assumption_free": True,
        "last_guardian_check_at": (guardian_state or {}).get("last_checked_at"),
        "reasons": engine_reasons,
    }

    zt_auto_fresh_seconds = max(45 * 60, zt_interval_minutes * 3 * 60)
    zt_auto_fresh = bool(
        (zt_auto_hb_ts and (now - zt_auto_hb_ts).total_seconds() <= zt_auto_fresh_seconds)
        or (zt_latest_run_ts and (now - zt_latest_run_ts).total_seconds() <= zt_auto_fresh_seconds)
    )
    zt_scan_fresh = bool(zt_latest_scan_ts and (now - zt_latest_scan_ts).total_seconds() <= (36 * 3600))
    zt_nightly_fresh = bool(
        (zt_nightly_hb_ts and (now - zt_nightly_hb_ts).total_seconds() <= (36 * 3600))
        or (zt_latest_nightly_ts and (now - zt_latest_nightly_ts).total_seconds() <= (36 * 3600))
    )

    zt_latest_status = str((zt_latest_scan or {}).get("zero_trust_status") or "UNKNOWN").upper()
    zt_reasons: list[str] = []
    if "zero_trust_auto_mitigation" not in registered_jobs:
        zt_reasons.append("zero_trust_auto_mitigation_not_registered")
    if "active_defense_nightly_scan" not in registered_jobs:
        zt_reasons.append("active_defense_nightly_scan_not_registered")
    if not zt_auto_fresh:
        zt_reasons.append("zero_trust_auto_mitigation_stale_or_missing")
    if not zt_scan_fresh:
        zt_reasons.append("active_defense_scan_stale_or_missing")
    if not zt_nightly_fresh:
        zt_reasons.append("active_defense_nightly_scan_stale_or_missing")
    if zt_latest_status != "PASS":
        zt_reasons.append(f"zero_trust_controls_status_{zt_latest_status.lower()}")

    if zt_latest_status == "PASS" and not zt_reasons:
        zt_health = "healthy"
    elif zt_latest_status == "FAIL":
        zt_health = "failing"
    else:
        zt_health = "degraded"

    checks["zero_trust"] = {
        "status": zt_health,
        "automation": {
            "enabled": bool(zt_policy.get("enabled", True)),
            "interval_minutes": zt_interval_minutes,
            "last_scheduler_heartbeat_at": (zt_auto_hb or {}).get("last_run"),
            "last_scheduler_heartbeat_status": (zt_auto_hb or {}).get("status"),
            "last_scheduler_heartbeat_detail": (zt_auto_hb or {}).get("detail"),
            "fresh": zt_auto_fresh,
        },
        "active_defense": {
            "last_scan_at": (zt_latest_scan or {}).get("completed_at"),
            "latest_zero_trust_status": zt_latest_status,
            "threat_level": (zt_latest_scan or {}).get("threat_level"),
            "confidence": (zt_latest_scan or {}).get("confidence"),
            "pass_count": (zt_latest_scan or {}).get("pass_count"),
            "total_checks": (zt_latest_scan or {}).get("total_checks"),
            "sast_status": ((zt_latest_scan or {}).get("sections") or {}).get("sast", {}).get("status"),
            "sast_findings_count": ((zt_latest_scan or {}).get("sections") or {}).get("sast", {}).get("findings_count"),
            "scan_fresh": zt_scan_fresh,
        },
        "nightly": {
            "enabled": bool(zt_nightly_policy.get("enabled", True)),
            "send_email_report": bool(zt_nightly_policy.get("send_email_report", True)),
            "last_run_at": (zt_latest_nightly or {}).get("completed_at"),
            "last_scheduler_heartbeat_at": (zt_nightly_hb or {}).get("last_run"),
            "last_scheduler_heartbeat_status": (zt_nightly_hb or {}).get("status"),
            "last_email_status": ((zt_latest_nightly or {}).get("email") or {}).get("status"),
            "fresh": zt_nightly_fresh,
        },
        "reasons": zt_reasons,
    }

    route_count = len([r for r in app.routes if hasattr(r, "path")])
    checks["api"] = {"status": "healthy", "route_count": route_count}

    try:
        collections = await db.list_collection_names()
        checks["collections"] = {"count": len(collections)}
    except Exception:
        checks["collections"] = {"count": 0}

    db_hardening = await db.platform_security_state.find_one({"_id": "db_hardening"}, {"_id": 0}) or {}
    db_hardening_failed = len(db_hardening.get("failed_indexes") or [])
    checks["db_security_hardening"] = {
        "status": "healthy" if db_hardening.get("status") == "healthy" else "degraded",
        "failed_indexes": db_hardening_failed,
        "checked_at": db_hardening.get("checked_at"),
        "security_version": db_hardening.get("security_version"),
    }

    trust_run = await db.gtec_c5_trust_monitor_runs.find_one({}, {"_id": 0}, sort=[("checked_at", -1)]) or {}
    if not trust_run:
        try:
            from services.gtec_scan_v2 import build_trust_gate_snapshot
            snap = await build_trust_gate_snapshot(db)
            trust_run = {
                "mode": "bootstrap",
                "trust_score_percent": snap.get("trust_score_percent"),
                "checked_at": snap.get("generated_at"),
                "latest_task_id": snap.get("latest_public_task_id") or "",
            }
        except Exception:
            trust_run = {}
    trust_score = float(trust_run.get("trust_score_percent") or 0.0)
    checks["gtec_c5_pipeline"] = {
        "status": "healthy" if trust_score >= 100 else "degraded",
        "mode": trust_run.get("mode") or "unknown",
        "trust_score_percent": trust_score,
        "checked_at": trust_run.get("checked_at"),
        "latest_task_id": trust_run.get("latest_task_id") or "",
    }

    all_healthy = all(c.get("status") == "healthy" for c in checks.values() if "status" in c)
    return {
        "status": "operational" if all_healthy else "degraded",
        "service": "RealAICoach Enterprise Platform",
        "version": "3.3.0",
        "checks": checks,
        "enterprise_autonomous_engine": {
            "status": "ACTIVE" if checks["enterprise_autonomous_engine"]["status"] == "healthy" else "DEGRADED",
            "safe_auto_runs_active": checks["enterprise_autonomous_engine"]["safe_auto_runs_active"],
            "non_disableable": True,
            "reasons": checks["enterprise_autonomous_engine"].get("reasons", []),
            "enterprise_reality_validation_guardian": (
                checks["enterprise_autonomous_engine"].get("components", {}).get("enterprise_reality_validation_guardian", {})
            ),
        },
        "reality_validation": {
            "status": "VALIDATED" if checks["reality_validation"]["status"] == "healthy" else "DEGRADED",
            "assumption_free": True,
            "method": checks["reality_validation"]["method"],
            "reasons": checks["reality_validation"].get("reasons", []),
        },
        "zero_trust": {
            "status": (
                "PASS" if checks["zero_trust"]["status"] == "healthy"
                else "FAIL" if checks["zero_trust"]["status"] == "failing"
                else "DEGRADED"
            ),
            "latest_zero_trust_status": checks["zero_trust"].get("active_defense", {}).get("latest_zero_trust_status"),
            "reasons": checks["zero_trust"].get("reasons", []),
        },
        "timestamp": now.isoformat(),
    }


@api_router.get("/system/api-catalog")
async def api_catalog():
    """List all registered API endpoint groups."""
    groups: dict = {}
    for route in app.routes:
        if hasattr(route, "path") and route.path.startswith("/api/"):
            path = route.path
            group = path.split("/")[2] if len(path.split("/")) > 2 else "root"
            if group not in groups:
                groups[group] = {"endpoints": 0, "methods": set()}
            groups[group]["endpoints"] += 1
            if hasattr(route, "methods"):
                groups[group]["methods"].update(route.methods or [])
    for g in groups.values():
        g["methods"] = sorted(list(g["methods"]))
    return {
        "total_groups": len(groups),
        "total_endpoints": sum(g["endpoints"] for g in groups.values()),
        "groups": groups,
    }


# ── Domain Registrations ─────────────────────────────────────────────────────

from domains.auth import register as reg_auth
from domains.admin import register as reg_admin
from domains.ai import register as reg_ai
from domains.content import register as reg_content
from domains.hiring import register as reg_hiring
from domains.miniapps import register as reg_miniapps
from domains.payments import register as reg_payments
from domains.platform import register as reg_platform
from domains.social import register as reg_social
from domains.support import register as reg_support

reg_auth(api_router, app)
reg_admin(api_router, app)
reg_ai(api_router, app)
reg_content(api_router, app)
reg_hiring(api_router, app)
reg_miniapps(api_router, app)
reg_payments(api_router, app)
reg_platform(api_router, app)
reg_social(api_router, app)
reg_support(api_router, app)

# ── Onboarding Wizard ─────────────────────────────────────────────────────────
from routes.onboarding_wizard import router as wizard_router
from routes.annotations import router as annotations_router

api_router.include_router(wizard_router)


# ── Webhook Alerts (Slack/Teams for V7/UIEM/theme drift) ──────────────────────
from routes.webhook_alerts import router as webhook_alerts_router
api_router.include_router(webhook_alerts_router)

# ── Careers Hub (public jobs + admin CRUD + AI cover-letter) ──────────────────
from routes.careers import router as careers_router
from routes.careers_thread import router as careers_thread_router
api_router.include_router(careers_thread_router)
# IMPORTANT: careers_tier3_router must be included BEFORE careers_offers_router
# because tier3 declares literal paths like `/careers/offers/counter-queue` that
# would be shadowed by careers_offers' `/careers/offers/{offer_id}` catch-all.
# FastAPI dispatches on first-match — so literal paths must win registration order.
from routes.careers_tier3 import router as careers_tier3_router
api_router.include_router(careers_tier3_router)
from routes.careers_offers import router as careers_offers_router
api_router.include_router(careers_offers_router)
from routes.gtec import router as gtec_router
api_router.include_router(gtec_router)
from routes.gtec_crawler_api import router as gtec_crawler_router
api_router.include_router(gtec_crawler_router)
from routes.gtec_scan_v2_api import router as gtec_scan_v2_router
api_router.include_router(gtec_scan_v2_router)
from routes.gtec_internal_api import router as gtec_internal_router
api_router.include_router(gtec_internal_router)
api_router.include_router(gtec_directive_public_router)
from routes.i18n import router as i18n_router
api_router.include_router(i18n_router)
from routes.admin_i18n_coverage import router as admin_i18n_coverage_router
api_router.include_router(admin_i18n_coverage_router)

from routes.admin_i18n_adoption import router as admin_i18n_adoption_router
api_router.include_router(admin_i18n_adoption_router)
from routes.careers_enhancements import router as careers_enh_router
api_router.include_router(careers_enh_router)
from routes.careers_tier1 import router as careers_tier1_router
api_router.include_router(careers_tier1_router)

# ── Compliance Digest Hub (aggregated admin inbox for all digest emails) ────
from routes.compliance_digest_hub import router as compliance_digest_hub_router
api_router.include_router(compliance_digest_hub_router)

# ── Careers ATS: Phase 1 TZ-aware scheduling (applicant self-serve) ────────
from routes.careers_scheduling import router as careers_scheduling_router
api_router.include_router(careers_scheduling_router)
from routes.careers_attachments import router as careers_attachments_router
api_router.include_router(careers_attachments_router)

# ── Public social-proof endpoints (Welcome tickertape, etc.) ───────────────
from routes.public_social_proof import router as public_social_proof_router
api_router.include_router(public_social_proof_router)
from routes.admin_coaching_tips import router as admin_coaching_tips_router
api_router.include_router(admin_coaching_tips_router)
from routes.admin_tickertape_analytics import router as admin_tickertape_analytics_router
api_router.include_router(admin_tickertape_analytics_router)
from routes.admin_broadcast import router as admin_broadcast_router
api_router.include_router(admin_broadcast_router)


# ── Contact Form ──────────────────────────────────────────────────────────────
from routes.contact import router as contact_router

api_router.include_router(contact_router)

# ── Enterprise Dashboard ──────────────────────────────────────────────────────
from routes.enterprise_dashboard import router as enterprise_dash_router

api_router.include_router(enterprise_dash_router)

# ── Team Management ───────────────────────────────────────────────────────────
from routes.team_management import router as team_mgmt_router

api_router.include_router(team_mgmt_router)

# ── Terms of Service ──────────────────────────────────────────────────────────
from routes.tos import router as tos_router

api_router.include_router(tos_router)

# ── Security Incidents Dashboard ──────────────────────────────────────────────
from routes.security_incidents import router as security_incidents_router

api_router.include_router(security_incidents_router)

# ── Admin Data Management ─────────────────────────────────────────────────────
from routes.admin_data_management import router as admin_data_mgmt_router
from routes.pdf_policy_admin import router as pdf_policy_admin_router

api_router.include_router(admin_data_mgmt_router)
api_router.include_router(pdf_policy_admin_router)

# ── Session Replay ────────────────────────────────────────────────────────────
from routes.session_replay import router as session_replay_router

api_router.include_router(session_replay_router)

# ── MFA (Multi-Factor Authentication) ─────────────────────────────────────────
from routes.mfa import router as mfa_router

api_router.include_router(mfa_router)

# ── Security Recommendations ──────────────────────────────────────────────────
from routes.security_recommendations import router as sec_rec_router

api_router.include_router(sec_rec_router)

# ── Security Posture Scanner ──────────────────────────────────────────────────
from routes.security_posture import router as sec_posture_router

api_router.include_router(sec_posture_router)

# ── Dashboard Layout (Customizable) ──────────────────────────────────────────
from routes.dashboard_layout import router as dash_layout_router

api_router.include_router(dash_layout_router)
api_router.include_router(annotations_router)

# ── Newsletter ────────────────────────────────────────────────────────────────
from routes.newsletter_router import router as newsletter_router

api_router.include_router(newsletter_router)

# ── Career Applications ──────────────────────────────────────────────────────
from routes.careers_router import router as careers_legacy_router
api_router.include_router(careers_router)  # new tracker + tier-1 endpoints (routes.careers)
api_router.include_router(careers_legacy_router)  # legacy /careers/track uppercase IDs (routers.careers)


# ── Newsletter Analytics ──────────────────────────────────────────────────────
from routes.newsletter_analytics_router import router as newsletter_analytics_router

api_router.include_router(newsletter_analytics_router)

# ── Feature 13: Mobility Assistant ─────────────────────────────────────────────
from routes.mobility_assistant import router as mobility_assistant_router

api_router.include_router(mobility_assistant_router)

# ── Feature 14: Bill Generator ─────────────────────────────────────────────────
from routes.bill_generator import router as bill_generator_router

api_router.include_router(bill_generator_router)

# ── Newsletter Campaigns ──────────────────────────────────────────────────────
from routes.newsletter_campaigns_router import router as newsletter_campaigns_router

api_router.include_router(newsletter_campaigns_router)

# ── Newsletter Segments ───────────────────────────────────────────────────────
from routes.newsletter_segments_router import router as newsletter_segments_router

api_router.include_router(newsletter_segments_router)

# ── Modal Analytics ───────────────────────────────────────────────────────────
from routes.modal_analytics_router import router as modal_analytics_router

api_router.include_router(modal_analytics_router)

from routes.csat_router import router as csat_router

api_router.include_router(csat_router)

from routes.ticket_feedback import router as ticket_feedback_router
api_router.include_router(ticket_feedback_router)
from routes.page_performance import router as page_performance_router
api_router.include_router(page_performance_router)


# ── Referral Program ──────────────────────────────────────────────────────────
from routes.referrals import router as referrals_router

api_router.include_router(referrals_router)

from routes.churn_recovery import router as churn_recovery_router

api_router.include_router(churn_recovery_router)

from routes.changelog import router as changelog_router

api_router.include_router(changelog_router)

from routes.reengagement import router as reengagement_router

api_router.include_router(reengagement_router)

from routes.ab_testing import router as ab_testing_router

api_router.include_router(ab_testing_router)

from routes.ab_prompt_testing import admin_router as prompt_ab_admin_router, public_router as prompt_ab_public_router
api_router.include_router(prompt_ab_admin_router)
api_router.include_router(prompt_ab_public_router)


from routes.platform_analytics import router as platform_analytics_router

api_router.include_router(platform_analytics_router)

from routes.code_health import router as code_health_router
api_router.include_router(code_health_router)

from routes.code_health_scanner import router as code_health_scanner_router
api_router.include_router(code_health_scanner_router)

from routes.accessibility_audit import router as accessibility_audit_router
api_router.include_router(accessibility_audit_router)

from routes.feature_registry import router as feature_registry_router
api_router.include_router(feature_registry_router)

from routes.global_platform_state import router as global_platform_state_router
api_router.include_router(global_platform_state_router)
from routes.gps_runtime_routes import router as gps_runtime_router
api_router.include_router(gps_runtime_router)
from routes.gps_admin_governance import router as gps_admin_governance_router
api_router.include_router(gps_admin_governance_router)

from routes.ai_avatar import router as ai_avatar_router
api_router.include_router(ai_avatar_router)

from routes.live_activity import router as live_activity_router
app.include_router(live_activity_router)

from routes.analytics_reports import router as analytics_reports_router
api_router.include_router(analytics_reports_router)

from routes.admin_content_studio_analytics import router as admin_cs_analytics_router
api_router.include_router(admin_cs_analytics_router)

from routes.seo_analytics import router as seo_router
from routes.integrations import router as integrations_router
from routes.calendar_core import router as calendar_core_router
from routes.calendar_sync import router as calendar_sync_router
from routes.calendar_ai import router as calendar_ai_router
from routes.calendar_booking import router as calendar_booking_router
from routes.calendar_sharing import router as calendar_sharing_router
from routes.calendar_reliability import router as calendar_reliability_router
api_router.include_router(seo_router)
api_router.include_router(integrations_router)
api_router.include_router(calendar_core_router)
api_router.include_router(calendar_sync_router)
api_router.include_router(calendar_ai_router)
api_router.include_router(calendar_booking_router)
api_router.include_router(calendar_sharing_router)
api_router.include_router(calendar_reliability_router)

from routes.automation_engine import register as reg_automation
reg_automation(api_router, app)

from routes.ai_insights import register as reg_ai_insights
reg_ai_insights(api_router, app)

from routes.push_notifications import register as reg_push
reg_push(api_router, app)

from routes.cdn_automation import register as reg_cdn
reg_cdn(api_router, app)

from routes.security_engine import register as reg_security
reg_security(api_router, app)

from routes.security_policy_gate import router as security_policy_gate_router
api_router.include_router(security_policy_gate_router)

from routes.appstore_connect import router as appstore_router
api_router.include_router(appstore_router)

from routes.google_play import router as google_play_router
api_router.include_router(google_play_router)

from routes.iap import router as iap_router
api_router.include_router(iap_router)

from routes.aso_unified import register as reg_aso_unified
reg_aso_unified(api_router, app)

from routes.perf_advisor import router as perf_advisor_router
api_router.include_router(perf_advisor_router)

from routes.ai_remediation import router as ai_remediation_router
api_router.include_router(ai_remediation_router)

from routes.auto_detect import router as auto_detect_router
api_router.include_router(auto_detect_router)

from routes.critical_journey_monitor import router as critical_journey_monitor_router
api_router.include_router(critical_journey_monitor_router)

from routes.performance_guardian import router as performance_guardian_router
api_router.include_router(performance_guardian_router)

from routes.admin_autofix_engine import router as autofix_engine_router
api_router.include_router(autofix_engine_router)

from routes.anomaly_detection import router as anomaly_detection_router
api_router.include_router(anomaly_detection_router)

from routes.cia_trust import router as cia_trust_router
api_router.include_router(cia_trust_router)

from routes.platform_perf import router as platform_perf_router
api_router.include_router(platform_perf_router)

from routes.platform_shell_health import router as platform_shell_health_router
api_router.include_router(platform_shell_health_router)

from routes.ai_engine import router as ai_engine_router
api_router.include_router(ai_engine_router)

from routes.ai_panel_insights import router as ai_panel_insights_router
api_router.include_router(ai_panel_insights_router)

from routes.ai_autofix_engine import router as ai_autofix_router
api_router.include_router(ai_autofix_router)

from routes.ai_platform_integrity import router as ai_platform_integrity_router
api_router.include_router(ai_platform_integrity_router)

from routes.content_studio import router as content_studio_router
api_router.include_router(content_studio_router)

from routes.writing_studio import router as writing_studio_router
api_router.include_router(writing_studio_router)

from routes.personal_assistant import router as personal_assistant_router
api_router.include_router(personal_assistant_router)

from routes.research_navigator import router as research_navigator_router
api_router.include_router(research_navigator_router)

from routes.workflow_builder import router as workflow_builder_router
api_router.include_router(workflow_builder_router)

# Feature 5: Decision Coach
from routes.decision_coach import router as decision_coach_router
api_router.include_router(decision_coach_router)

from routes.tools_misc import router as tools_misc_router
api_router.include_router(tools_misc_router)

from routes.platform_health import router as platform_health_router
api_router.include_router(platform_health_router)

from routes.admin_payment_analytics import router as payment_analytics_router
api_router.include_router(payment_analytics_router)

from routes.admin_payments_tax_intelligence import router as payments_tax_intelligence_router
api_router.include_router(payments_tax_intelligence_router)

from routes.admin_subscription_analytics import router as subscription_analytics_router
api_router.include_router(subscription_analytics_router)

from routes.admin_notification_rules import router as notification_rules_router
api_router.include_router(notification_rules_router)

from routes.platform_employees import router as platform_employees_router
api_router.include_router(platform_employees_router)

from routes.status_page import router as status_page_router
api_router.include_router(status_page_router)

from routes.platform_control import router as platform_control_router
api_router.include_router(platform_control_router)

from routes.subscription_prompt_telemetry import router as subscription_prompt_telemetry_router
api_router.include_router(subscription_prompt_telemetry_router)

from routes.job_alerts import router as job_alerts_router, set_db as job_alerts_set_db
job_alerts_set_db(db)
api_router.include_router(job_alerts_router)

from routes.autonomous_engine import router as autonomous_engine_router
api_router.include_router(autonomous_engine_router)

from routes.security_hardening import router as security_hardening_router
api_router.include_router(security_hardening_router)

from routes.security_key_rotation import router as security_key_rotation_router
api_router.include_router(security_key_rotation_router)

from routes.gdpr_self_service import router as gdpr_router
api_router.include_router(gdpr_router)

from routes.email_health import router as email_health_router
api_router.include_router(email_health_router)

from routes.uiem import router as uiem_router
api_router.include_router(uiem_router)

from routes.v7_templates import router as v7_templates_router
api_router.include_router(v7_templates_router)

from routes.blog_hub import router as blog_hub_router
api_router.include_router(blog_hub_router)

from routes.blog_v2 import router as blog_v2_router
api_router.include_router(blog_v2_router)

from routes.blog_editorial import router as blog_editorial_router
api_router.include_router(blog_editorial_router)

from routes.admin_system_alerts import router as admin_system_alerts_router
api_router.include_router(admin_system_alerts_router)

from routes.client_errors import router as client_errors_router
api_router.include_router(client_errors_router)

from routes.observability_center import router as observability_center_router
api_router.include_router(observability_center_router)


from routes.travel_visa import router as travel_visa_router
api_router.include_router(travel_visa_router)

from routes.travel_visa_ext import router as travel_visa_ext_router
api_router.include_router(travel_visa_ext_router)

from routes.travel_visa_daily_meditation import router as travel_visa_daily_meditation_router
api_router.include_router(travel_visa_daily_meditation_router)

from routes.matchday_reminders import router as matchday_reminders_router
api_router.include_router(matchday_reminders_router)

from routes.content_integrity import router as content_integrity_router
api_router.include_router(content_integrity_router)

# ── Learning Coach (Feature 6) ────────────────────────────────────────────────
from routes.learning_coach import router as learning_coach_router
api_router.include_router(learning_coach_router)

# ── Health Guide (Feature 7) ──────────────────────────────────────────────────
from routes.health_guide import router as health_guide_router
api_router.include_router(health_guide_router)

# ── Fitness Planner Pro (Feature 8) ───────────────────────────────────────────
from routes.fitness_planner import router as fitness_planner_router
api_router.include_router(fitness_planner_router)

# ── Money Strategy Hub (Feature 9) ────────────────────────────────────────────
from routes.money_strategy_hub import router as money_strategy_hub_router
api_router.include_router(money_strategy_hub_router)
from routes.smart_shopping_advisor import router as smart_shopping_advisor_router
api_router.include_router(smart_shopping_advisor_router)
from routes.travel_planner_pro import router as travel_planner_pro_router
api_router.include_router(travel_planner_pro_router)
from routes.relationship_coach import router as relationship_coach_router
api_router.include_router(relationship_coach_router)

# ── Video Creator Studio (Feature 15) ─────────────────────────────────────────
from routes.video_creator_studio import router as video_creator_studio_router
api_router.include_router(video_creator_studio_router)

# ── Image & Design Studio (Feature 16) ───────────────────────────────────────
from routes.ai_photo_studio import router as ai_photo_studio_router
api_router.include_router(ai_photo_studio_router)

# ── Voice Studio (Feature 17) ─────────────────────────────────────────────────
from routes.ai_speech_studio import router as ai_speech_studio_router
api_router.include_router(ai_speech_studio_router)

# ── Business Operations Copilot (Feature 18) ──────────────────────────────────
from routes.ai_enterprise_copilot import router as ai_enterprise_copilot_router
api_router.include_router(ai_enterprise_copilot_router)

# Mount the API router onto the application
# Multi-platform architecture: client bootstrap handshake + admin-gated API docs
from routes.client_bootstrap import router as client_bootstrap_router
from routes.api_docs import router as api_docs_router
from routes.client_version_admin import router as client_version_admin_router
api_router.include_router(client_bootstrap_router)
api_router.include_router(api_docs_router)
api_router.include_router(client_version_admin_router)

app.include_router(api_router)

# ── Static files (fonts for web) ─────────────────────────────────────────────
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse as _FileResponse
import os

if os.path.isdir(os.path.join(os.path.dirname(__file__), "static")):
    app.mount("/api/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
if os.path.isdir(os.path.join(os.path.dirname(__file__), "media")):
    app.mount("/api/media", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "media")), name="media")


@app.get("/api/email-assets/{filename}")
async def email_asset(filename: str):
    """Serve email assets with cache-friendly headers for maximum email client compatibility."""
    safe_name = os.path.basename(filename)
    fpath = os.path.join(os.path.dirname(__file__), "static", "images", safe_name)
    if not os.path.exists(fpath):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "not found"}, status_code=404)
    ct = "image/png" if safe_name.endswith(".png") else "image/jpeg"
    return _FileResponse(
        fpath,
        media_type=ct,
        headers={"Cache-Control": "public, max-age=31536000, immutable", "Access-Control-Allow-Origin": "*"},
    )


# ── Google Search Console Domain Verification ────────────────────────────────
@app.get("/api/google-site-verification")
async def google_site_verification():
    """Returns the Google Site Verification code stored in env."""
    code = os.environ.get("GOOGLE_SITE_VERIFICATION", "")
    if not code:
        return JSONResponse({"status": "not_configured", "message": "Set GOOGLE_SITE_VERIFICATION in backend/.env"}, status_code=404)
    return JSONResponse({"verification_code": code})


# ── Blog API ──────────────────────────────────────────────────────────────────
@app.get("/api/blog/posts")
async def blog_posts_list(category: str = "All"):
    """Get all active blog posts, optionally filtered by category."""
    from services.blog_service import get_blog_posts
    posts = await get_blog_posts(db, category if category != "All" else None)
    return JSONResponse(posts)


@app.get("/api/blog/posts/{slug}")
async def blog_post_detail(slug: str):
    """Get a single blog post by slug."""
    from services.blog_service import get_blog_post_by_slug
    post = await get_blog_post_by_slug(db, slug)
    if not post:
        return JSONResponse({"error": "Post not found"}, status_code=404)
    return JSONResponse(post)


@app.get("/api/blog/categories")
async def blog_categories():
    """Get all active blog categories."""
    cats = await db.blog_posts.distinct("category", {"active": True})
    return JSONResponse(["All"] + sorted(cats))


# ── Google OAuth Verification Monitor ─────────────────────────────────────────
@app.get("/api/admin/google-verification/dashboard")
async def google_verification_dashboard(request: Request):
    """Get Google OAuth verification status dashboard."""
    from routes.db import require_admin
    await require_admin(request)
    from services.google_verification_monitor import get_verification_dashboard
    data = await get_verification_dashboard(db)
    return JSONResponse(data)


@app.post("/api/admin/google-verification/check")
async def google_verification_check(request: Request):
    """Manually trigger a verification status check."""
    from routes.db import require_admin
    await require_admin(request)
    from services.google_verification_monitor import check_google_verification_status
    result = await check_google_verification_status(db)
    return JSONResponse(result)


@app.post("/api/admin/google-verification/settings")
async def google_verification_settings(request: Request):
    """Update verification monitor settings."""
    from routes.db import require_admin
    await require_admin(request)
    body = await request.json()
    await db.google_verification_settings.update_one(
        {"type": "settings"},
        {"$set": {
            "type": "settings",
            "email_alerts_enabled": body.get("email_alerts_enabled", True),
            "alert_email": body.get("alert_email", os.environ.get("ADMIN_EMAILS", "admin@realaicoach.app")),
            "check_interval_hours": body.get("check_interval_hours", 6),
        }},
        upsert=True,
    )
    return JSONResponse({"success": True})


@app.post("/api/admin/google-verification/update-status")
async def google_verification_manual_update(request: Request):
    """Manually update verification status (e.g., when user receives email from Google)."""
    from routes.db import require_admin
    await require_admin(request)
    body = await request.json()
    new_status = body.get("status")
    note = body.get("note", "")
    if new_status not in ("under_review", "verified", "rejected", "action_required"):
        return JSONResponse({"error": "Invalid status"}, status_code=400)
    now = datetime.now(timezone.utc).isoformat()
    current = await db.google_verification_status.find_one({"type": "current_status"}, {"_id": 0})
    prev = current.get("status") if current else None
    await db.google_verification_status.update_one(
        {"type": "current_status"},
        {"$set": {
            "type": "current_status",
            "status": new_status,
            "previous_status": prev,
            "checked_at": now,
            "manual_update": True,
            "note": note,
        }},
        upsert=True,
    )
    await db.google_verification_history.insert_one({
        "status": new_status, "checked_at": now, "manual": True, "note": note,
    })
    if prev and prev != new_status:
        from services.google_verification_monitor import _send_status_change_alert, _send_push_notification
        await _send_status_change_alert(db, prev, new_status, now)
        await _send_push_notification(db, prev, new_status)
    return JSONResponse({"success": True, "status": new_status})


# ── SEO: Sitemap ─────────────────────────────────────────────────────────────


@app.get("/api/sitemap.xml")
async def sitemap():
    from fastapi.responses import Response

    base = "https://realaicoach.app"
    pages = [
        ("", "1.0", "daily"),
        ("/auth/login", "0.8", "monthly"),
        ("/auth/register", "0.8", "monthly"),
        ("/feature-gallery", "0.9", "weekly"),
        ("/faq", "0.6", "monthly"),
        ("/help", "0.6", "monthly"),
    ]
    urls = "\n".join(
        f"  <url><loc>{base}{p[0]}</loc><priority>{p[1]}</priority><changefreq>{p[2]}</changefreq></url>" for p in pages
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>'
    return Response(content=xml, media_type="application/xml")


# ── Resend Webhook (public, signature-verified) ─────────────────────────────


@app.post("/api/webhooks/resend")
async def resend_webhook(request: Request):
    """Receives Resend delivery events (delivered, bounced, complained, etc.)."""
    import hmac
    import hashlib
    import base64
    import json as _json

    raw_body = await request.body()
    _RESEND_WEBHOOK_SECRET = os.environ.get("RESEND_WEBHOOK_SECRET", "")

    if _RESEND_WEBHOOK_SECRET:
        sig_header = request.headers.get("svix-signature", "")
        msg_id = request.headers.get("svix-id", "")
        timestamp = request.headers.get("svix-timestamp", "")
        if sig_header and msg_id and timestamp:
            to_sign = f"{msg_id}.{timestamp}.{raw_body.decode()}"
            secret_bytes = _RESEND_WEBHOOK_SECRET
            if secret_bytes.startswith("whsec_"):
                secret_bytes = secret_bytes[6:]
            try:
                key = base64.b64decode(secret_bytes)
                expected = base64.b64encode(hmac.new(key, to_sign.encode(), hashlib.sha256).digest()).decode()
                sigs = [s.split(",")[-1] for s in sig_header.split(" ")]
                if not any(hmac.compare_digest(expected, s) for s in sigs):
                    logger.warning("Invalid Resend webhook signature")
                    return JSONResponse({"status": "invalid_signature"}, status_code=401)
            except Exception as e:
                logger.warning(f"Signature verification error: {e}")

    try:
        payload = _json.loads(raw_body)
    except Exception:
        return JSONResponse({"status": "invalid"}, status_code=400)

    event_type = payload.get("type", "unknown")
    data = payload.get("data", {})
    to_email = data.get("to", [""])[0] if isinstance(data.get("to"), list) else data.get("to", "")
    subject = data.get("subject", "")[:60]
    logger.info(f"[Resend webhook] {event_type} | to={to_email} | subj={subject}")

    email_id = data.get("email_id", "")
    template_key = ""
    if email_id:
        send_record = await db.email_sends.find_one({"email_id": email_id}, {"_id": 0, "template_key": 1})
        if send_record:
            template_key = send_record.get("template_key", "")
    if not template_key:
        tags = data.get("tags", {})
        if isinstance(tags, dict):
            template_key = tags.get("template", "")
        elif isinstance(tags, list):
            for t in tags:
                if isinstance(t, dict) and t.get("name") == "template":
                    template_key = t.get("value", "")
                    break

    await db.email_events.insert_one(
        {
            "provider": "resend",
            "event": event_type,
            "to": to_email,
            "subject": subject,
            "email_id": email_id,
            "template_key": template_key,
            "created_at": data.get("created_at", ""),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"status": "ok"}


# ── WebSockets ───────────────────────────────────────────────────────────────

from ws_endpoints import register as register_ws

register_ws(app)

# ── Database Indexes & Startup ───────────────────────────────────────────────

from routes.db import ensure_full_access_users, ensure_admin_users


@app.on_event("startup")
async def load_preprod_entitlement_lock_startup():
    try:
        from utils.preprod_entitlement_lock import load_preprod_lock_state

        active = await load_preprod_lock_state()
        logger.info(f"[preprod-entitlement-lock] active={active}")
    except Exception as exc:
        logger.error(f"[preprod-entitlement-lock] startup load failed: {exc}")


@app.on_event("startup")
async def enforce_secret_vault_policy_startup():
    try:
        _enforce_secret_vault_policy()
        _enforce_required_secret_env_vars()
    except Exception as exc:
        logger.error(f"[secret-vault-policy] startup enforcement failed: {exc}")
        raise


@app.on_event("startup")
async def enforce_iap_runtime_preflight_startup():
    try:
        hydration = hydrate_iap_runtime_secrets(force=True)
        preflight = enforce_iap_startup_preflight()
        logger.info(
            "[iap-startup-preflight] strict=%s live_required=%s apple_state=%s google_state=%s runtime_dir=%s",
            preflight.get("strict"),
            preflight.get("require_live"),
            preflight.get("apple_state"),
            preflight.get("google_state"),
            hydration.get("runtime_dir"),
        )
    except Exception as exc:
        logger.error(f"[iap-startup-preflight] failed: {exc}")
        raise


@app.on_event("startup")
async def enforce_zero_assumptions_policy():
    """Boot-time scrubber for ZERO ASSUMPTIONS POLICY.

    Deletes any settings.offer_branding / receipt_branding row that contains a
    fabricated business-identity token. See /app/memory/ZERO_ASSUMPTIONS_POLICY.md.
    Runs once per process start, before any API traffic is served.
    """
    try:
        from routes.careers_offers import _scrub_fabricated_branding
        removed = await _scrub_fabricated_branding()
        if removed:
            logger.warning(
                "[ZERO-ASSUMPTIONS] Startup scrubber removed %d fabricated branding doc(s).",
                removed,
            )
        else:
            logger.info("[ZERO-ASSUMPTIONS] Startup scrubber: no fabricated branding found.")
    except Exception as e:
        logger.error("[ZERO-ASSUMPTIONS] Startup scrubber failed: %s", e)


@app.on_event("startup")
async def create_db_indexes():
    """Create database indexes for faster queries."""

    async def _dedupe_payment_ids_for_unique_index() -> int:
        """Normalize duplicate `payments.payment_id` values before creating unique index.

        Keeps the newest record per payment_id unchanged and rewrites older duplicates
        with deterministic suffixes so index creation cannot fail on startup.
        """
        rewritten = 0
        pipeline = [
            {"$match": {"payment_id": {"$exists": True, "$type": "string", "$ne": ""}}},
            {"$group": {"_id": "$payment_id", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
        duplicate_groups = await db.payments.aggregate(pipeline).to_list(length=500)

        for group in duplicate_groups:
            payment_id = str(group.get("_id") or "").strip()
            if not payment_id:
                continue

            rows = (
                await db.payments.find(
                    {"payment_id": payment_id},
                    {"_id": 1, "created_at": 1},
                )
                .sort("created_at", -1)
                .to_list(length=2000)
            )
            if len(rows) <= 1:
                continue

            # keep newest as canonical; rewrite older duplicates
            for pos, row in enumerate(rows):
                if pos == 0:
                    continue
                oid = row.get("_id")
                if not oid:
                    continue
                suffix = str(oid)[-8:]
                new_payment_id = f"{payment_id}__dedup_{suffix}"
                await db.payments.update_one(
                    {"_id": oid},
                    {"$set": {"payment_id": new_payment_id, "payment_id_deduped_at": datetime.now(timezone.utc).isoformat()}},
                )
                rewritten += 1

        return rewritten

    try:
        await db.users.create_index("user_id", unique=True)
        # Fix: drop the old non-sparse email index and recreate as sparse
        try:
            await db.users.drop_index("email_1")
        except Exception:
            pass
        await db.users.create_index("email", unique=True, sparse=True)
        await db.user_sessions.create_index("session_token")
        await db.user_sessions.create_index("user_id")
        await db.conversations.create_index("user_id")
        await db.conversations.create_index([("user_id", 1), ("status", 1)])
        await db.progress.create_index("user_id", unique=True)
        await db.support_tickets.create_index("ticket_id")
        await db.lifegame_characters.create_index("user_id", unique=True)
        await db.lifegame_moods.create_index("user_id")
        await db.payments.create_index("user_id")

        deduped_count = await _dedupe_payment_ids_for_unique_index()
        if deduped_count > 0:
            logger.warning("Startup self-heal: normalized %s duplicate payments.payment_id values", deduped_count)

        await db.payments.create_index([("payment_id", 1)], unique=True, sparse=True)
        await db.payment_transactions.create_index([("transaction_id", 1)], unique=True, sparse=True)
        await db.payment_transactions.create_index([("provider", 1), ("created_at", -1)])
        await db.payment_transactions.create_index([("user_id", 1), ("created_at", -1)])
        await db.payment_transactions.create_index([("gateway", 1), ("fedapay_tx_id", 1)])
        await db.payment_transactions.create_index([("gateway", 1), ("fedapay_reference", 1)])
        await db.tax_calculation_logs.create_index([("transaction_id", 1), ("created_at", -1)])
        await db.tax_calculation_logs.create_index([("provider", 1), ("created_at", -1)])
        await db.payment_tax_alerts.create_index([("created_at", -1)])
        await db.payment_tax_alerts.create_index([("resolved", 1), ("created_at", -1)])
        await db.user_preferences.create_index([("user_id", 1)], unique=True)
        await db.user_preferences.create_index([("key", 1), ("updated_at", -1)], sparse=True)
        await db.user_preferences.create_index([("user_id", 1), ("key", 1)], sparse=True)
        await db.action_history.create_index([("user_id", 1), ("timestamp", -1)])
        await db.action_history.create_index([("feature_key", 1), ("timestamp", -1)])
        await db.action_history.create_index([("action_id", 1)], sparse=True)
        await db.web_vitals.create_index([("timestamp", -1)])
        await db.web_vitals.create_index([("page", 1), ("timestamp", -1)])
        await db.web_vitals.create_index([("release_version", 1), ("timestamp", -1)])
        await db.page_perf_metrics.create_index([("timestamp", -1)])
        await db.page_perf_metrics.create_index([("page", 1), ("timestamp", -1)])
        await db.page_perf_metrics.create_index([("release_version", 1), ("timestamp", -1)])
        await db.financial_ledger_entries.create_index([("sequence", 1)], unique=True)
        await db.financial_ledger_entries.create_index([("transaction_id", 1), ("created_at", -1)])
        await db.fedapay_webhook_events.create_index("event_key", unique=True)
        await db.fedapay_webhook_events.create_index([("status", 1), ("next_retry_at", 1)])
        await db.fedapay_webhook_events.create_index([("received_at", -1)])
        await db.fedapay_webhook_delivery_log.create_index([("received_at", -1)])
        await db.fedapay_webhook_sync_history.create_index([("created_at", -1)])
        await db.scans.create_index("user_id")
        await db.ai_feedback.create_index("user_id")
        await db.ai_feedback.create_index([("feature_key", 1), ("created_at", -1)])
        await db.shared_links.create_index("token", unique=True)
        await db.shared_links.create_index("share_id", unique=True)
        await db.shared_links.create_index("user_id")
        await db.content_bookmarks.create_index([("user_id", 1), ("content_id", 1)], unique=True)
        await db.content.create_index([("title", "text"), ("category", "text"), ("type", "text")])
        await db.content.create_index("url", unique=True)
        await db.content.create_index("added_date")
        await db.system_metrics.create_index("created_at")
        await db.usage_metrics.create_index("created_at")
        await db.revenue_metrics.create_index("created_at")
        await db.risk_metrics.create_index("created_at")
        await db.infrastructure_metrics.create_index("created_at")
        await db.ai_insight_logs.create_index("created_at")
        await db.ai_engagement_events.create_index([("user_id", 1), ("created_at", -1)])
        await db.ai_engagement.create_index("user_id", unique=True)
        await db.ai_context.create_index("user_id", unique=True)
        await db.employer_messages.create_index([("employer_id", 1), ("created_at", 1)])
        await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        await db.notifications.create_index([("user_id", 1), ("read", 1)])
        await db.calendar_bookings.create_index([("user_id", 1), ("start", -1)])
        await db.calendar_bookings.create_index([("status", 1), ("start", 1)])
        await db.security_events.create_index([("user_id", 1), ("created_at", -1)])
        await db.security_events.create_index("ip_address")
        await db.region_deployments.create_index([("region_id", 1), ("deployed_at", -1)])
        await db.region_deployments.create_index([("release_id", 1), ("deployed_at", -1)], sparse=True)
        await db.release_intelligence_history.create_index([("release_id", 1)], unique=True)
        await db.release_intelligence_history.create_index([("status", 1), ("deployed_at", -1)])
        await db.release_intelligence_history.create_index([("version", 1), ("deployed_at", -1)])
        await db.release_intelligence_config.create_index([("key", 1)], unique=True)
        await db.system_knowledge_memory.create_index([("memory_id", 1)], unique=True)
        await db.system_knowledge_memory.create_index([("memory_type", 1), ("confidence_score", -1), ("updated_at", -1)])
        await db.system_knowledge_memory.create_index([("signature", 1), ("memory_type", 1)])
        await db.system_memory_lookups.create_index([("created_at", -1)])
        await db.system_memory_lookups.create_index([("task_type", 1), ("created_at", -1)])
        await db.reality_validation_runs.create_index([("created_at", -1)])
        await db.reality_validation_runs.create_index([("reality_status", 1), ("created_at", -1)])
        await db.reality_validation_runs.create_index([("confidence", 1), ("created_at", -1)])
        await db.reality_validation_config.create_index([("key", 1)], unique=True)
        await db.auth_route_block_events.create_index("event_key", unique=True, sparse=True)
        await db.auth_route_block_events.create_index([("created_at", -1)])
        await db.auth_route_block_events.create_index([("last_seen_at", -1)])
        await db.auth_route_block_events.create_index([("path", 1), ("created_at", -1)])
        await db.auth_route_block_events.create_index([("fingerprint_hash", 1), ("created_at", -1)])
        await db.admin_audit_logs.create_index([("user_id", 1), ("created_at", -1)])
        await db.password_reset_tokens.create_index([("token_hash", 1), ("used", 1)])
        await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
        await db.email_verification_tokens.create_index("expires_at", expireAfterSeconds=0)
        await db.user_sessions.create_index("expires_at")
        await db.ab_experiments.create_index("experiment_id", unique=True)
        await db.ab_experiments.create_index("status")
        await db.ab_assignments.create_index([("user_id", 1), ("experiment_id", 1)])
        await db.ab_conversions.create_index([("experiment_id", 1), ("variant_id", 1)])
        await db.team_members.create_index([("team_id", 1), ("user_id", 1)])
        await db.team_invitations.create_index("invite_code", unique=True)
        await db.quality_digest_history.create_index("sent_at")
        await db.ats_candidates.create_index([("user_id", 1), ("source", 1), ("external_id", 1)], unique=True)
        await db.ats_candidates.create_index([("user_id", 1), ("stage", 1)])
        await db.ats_candidates.create_index([("user_id", 1), ("synced_at", -1)])
        await db.ats_jobs.create_index([("user_id", 1), ("source", 1), ("external_id", 1)], unique=True)
        await db.ats_jobs.create_index([("user_id", 1), ("status", 1)])
        await db.integration_configs.create_index([("user_id", 1), ("integration_id", 1)])
        await db.integration_runtime_policies.create_index("key", unique=True)
        await db.integration_seed_cleanup_runs.create_index([("created_at", -1)])
        await db.integration_webhook_replay_guard.create_index("replay_key", unique=True)
        await db.integration_webhook_replay_guard.create_index("expires_at", expireAfterSeconds=0)
        await db.sync_logs.create_index([("config_id", 1), ("created_at", -1)])
        await db.support_tickets.create_index([("user_id", 1), ("status", 1)])
        await db.support_tickets.create_index("submission_id", unique=True, sparse=True)
        await db.ticket_attachments.create_index("file_id", unique=True)
        await db.ticket_attachments.create_index("uploaded_by")
        await db.email_sends.create_index("template_key")
        await db.email_sends.create_index("sent_at")
        await db.email_events.create_index([("template_key", 1), ("event", 1)])
        await db.email_events.create_index("received_at")
        await db.email_delivery_idempotency.create_index("idempotency_key", unique=True)
        await db.email_delivery_idempotency.create_index([("canonical_recipient", 1), ("created_at", -1)])
        await db.fraud_reports.create_index([("user_id", 1), ("status", 1)])
        await db.gamification_profiles.create_index("user_id", unique=True)
        await db.gamification_profiles.create_index([("xp", -1)])
        await db.gamification_profiles.create_index([("weekly_xp", -1)])
        await db.fps_game_profiles.create_index("user_id", unique=True)
        await db.fps_game_profiles.create_index([("kills", -1)])
        await db.fps_game_profiles.create_index([("best_kill_streak", -1)])
        await db.fps_game_matches.create_index([("user_id", 1), ("created_at", -1)])
        await db.fps_game_matches.create_index("match_id", unique=True)
        await db.fps_game_matches.create_index([("room_id", 1), ("created_at", -1)])
        # Live Activity Feed indexes
        await db.live_activity_events.create_index([("timestamp", -1)])
        await db.live_activity_events.create_index("event_type")
        await db.live_activity_events.create_index([("user_id", 1), ("timestamp", -1)])
        # Content Studio + Coach indexes
        await db.content_studio_history.create_index([("user_id", 1), ("created_at", -1)])
        await db.content_studio_history.create_index("template_type")
        await db.coach_conversations.create_index([("user_id", 1), ("updated_at", -1)])
        await db.coach_messages.create_index([("conversation_id", 1), ("created_at", 1)])
        logger.info("Database indexes created successfully")
        await ensure_full_access_users()
        await ensure_admin_users()
        logger.info("Full-access users ensured")

        # Seed feature registry
        from routes.feature_registry import seed_features
        await seed_features()
        await db.feature_registry.create_index("feature_id", unique=True)
        await db.global_platform_state.create_index("state_id", unique=True)
        await db.global_platform_events.create_index([("created_at", -1)])
        await db.global_platform_events.create_index([("event_type", 1), ("created_at", -1)])
        await db.global_platform_consistency_logs.create_index([("created_at", -1)])
        await db.gps_notification_outbox.create_index("outbox_id", unique=True)
        await db.gps_notification_outbox.create_index([("event_id", 1), ("user_id", 1)], unique=True)
        await db.gps_notification_outbox.create_index([("status", 1), ("next_retry_at", 1)])
        await db.gps_state_versions.create_index("version_id", unique=True)
        await db.gps_state_versions.create_index([("version", -1)])
        await db.gps_state_versions.create_index([("created_at", -1)])
        await db.gps_change_requests.create_index("request_id", unique=True)
        await db.gps_change_requests.create_index([("status", 1), ("created_at", -1)])
        await db.gps_faq_view_events.create_index([("created_at", -1)])
        await db.gps_faq_view_events.create_index([("faq_key", 1), ("created_at", -1)])
        await db.gps_faq_view_events.create_index([("context", 1), ("created_at", -1)])
        await db.gps_faq_view_events.create_index([("session_key", 1), ("faq_key", 1), ("context", 1), ("created_at", -1)])
        await db.legal_notice_schedules.create_index("schedule_id", unique=True)
        await db.legal_notice_schedules.create_index([("status", 1), ("scheduled_send_at", 1)])
        await db.legal_notice_schedule_audit.create_index([("schedule_id", 1), ("created_at", -1)])
        await db.legal_notice_schedule_audit.create_index([("action", 1), ("created_at", -1)])
        await db.legal_notice_delivery_events.create_index("delivery_id", unique=True)
        await db.legal_notice_delivery_events.create_index([("broadcast_id", 1), ("email_id", 1)])
        await db.email_notification_send_caps.create_index("cap_key", unique=True)
        await db.email_notification_send_caps.create_index([("canonical_recipient", 1), ("template_key", 1), ("updated_at", -1)])
        await db.email_notification_guardrail_events.create_index([("created_at", -1)])
        await db.email_recipient_blocklist.create_index("recipient_email", unique=True)
        await db.email_recipient_blocklist.create_index([("canonical_recipient", 1), ("active", 1)])
        await db.email_notification_template_policies.create_index("template_key", unique=True)
        await db.email_notification_template_policies.create_index([("active", 1), ("updated_at", -1)])
        await db.notification_dispatch_log.create_index("dedupe_key", unique=True)
        await db.notification_dispatch_log.create_index([("event_type", 1), ("created_at", -1)])
        await db.notification_dispatch_log.create_index([("channel", 1), ("status", 1), ("created_at", -1)])
        await db.tab_alias_telemetry_daily.create_index("bucket_key", unique=True)
        await db.tab_alias_telemetry_daily.create_index([("bucket_date", -1), ("console", 1)])
        await db.tab_alias_telemetry_daily.create_index([("source_tab_id", 1), ("canonical_tab_id", 1), ("bucket_date", -1)])

        # Careers Talent Network automation indexes
        await db.careers_talent_network.create_index("email", unique=True)
        await db.careers_talent_network.create_index([("status", 1), ("updated_at", -1)])
        await db.careers_talent_network_dispatch_runs.create_index([("started_at", -1)])
        await db.careers_talent_network_dispatch_events.create_index([("created_at", -1)])
        await db.careers_talent_network_dispatch_events.create_index([("email", 1), ("created_at", -1)])
        await db.careers_talent_network_dispatch_events.create_index([("run_id", 1), ("created_at", -1)])

        from routes.global_platform_state import get_global_platform_state
        await get_global_platform_state()

        # Indexes for service heartbeats (automation engine real data)
        await db.service_heartbeats.create_index([("service", 1), ("checked_at", -1)])
        await db.service_heartbeats.create_index("checked_at", expireAfterSeconds=259200)  # TTL: 3 days

    except Exception as e:
        logger.error(f"Index creation error: {e}")

    # Enterprise DB security hardening pass (global platform level)
    try:
        hardening = await ensure_db_security_hardening(db)
        logger.info(
            "[db-hardening] status=%s created=%s failed=%s",
            hardening.get("status"),
            len(hardening.get("created_indexes") or []),
            len(hardening.get("failed_indexes") or []),
        )
    except Exception as e:
        logger.error(f"[db-hardening] startup pass failed: {e}")

    # Start Lighthouse auto-auditor
    try:
        from services.lighthouse_auditor import scheduler as lighthouse_scheduler
        base_url = (os.environ.get("FRONTEND_BASE_URL") or "").rstrip("/")
        if not base_url:
            raise RuntimeError("FRONTEND_BASE_URL is required for Lighthouse auto-auditor")
        await lighthouse_scheduler.start(base_url, db, interval_minutes=60)
        logger.info("Lighthouse auto-auditor started")
    except Exception as e:
        logger.warning(f"Lighthouse scheduler start error (non-blocking): {e}")

    # Auto-sync FedaPay webhook URL (runs even if index creation had errors)
    _webhook_auto_sync_enabled = str(os.environ.get("WEBHOOK_AUTO_SYNC_ENABLED") or "true").strip().lower() not in {"0", "false", "no", "off"}
    # Defense in depth: live provider webhooks may only ever be synced from a
    # production runtime, and never to a preview host.
    _webhook_sync_base = str(os.environ.get("FRONTEND_BASE_URL") or "").strip().rstrip("/")
    _webhook_sync_host = (_urlparse(_webhook_sync_base).hostname or "").lower()
    if _webhook_auto_sync_enabled:
        if not _is_production_runtime():
            _webhook_auto_sync_enabled = False
            logger.info(
                "Webhook auto-sync skipped: not a production runtime (ENVIRONMENT=production required)"
            )
        elif not _webhook_sync_base:
            _webhook_auto_sync_enabled = False
            logger.warning("Webhook auto-sync skipped: FRONTEND_BASE_URL is empty")
        elif _webhook_sync_host.endswith("preview.emergentagent.com"):
            _webhook_auto_sync_enabled = False
            logger.warning(
                "Webhook auto-sync REFUSED: base URL %s is a preview host — refusing to point "
                "live provider webhooks at a preview environment",
                _webhook_sync_base,
            )
    try:
        from routes.fedapay_client import sync_webhook_url, get_current_webhook_url

        webhook_url = get_current_webhook_url()
        logger.info(f"FedaPay: Current webhook URL = {webhook_url}")
        result = {"status": "skipped", "reason": "auto-sync disabled by WEBHOOK_AUTO_SYNC_ENABLED"} if not _webhook_auto_sync_enabled else await sync_webhook_url()
        if result.get("status") == "ok":
            action = result.get("action", "none")
            if action in ("updated", "recreated"):
                logger.info(
                    f"FedaPay webhook AUTO-SYNCED ({action}): {result.get('old_url', '')} -> {result.get('new_url', result.get('url', ''))}"
                )
            elif action == "created":
                logger.info(f"FedaPay webhook AUTO-CREATED: {result.get('url')}")
            else:
                logger.info(f"FedaPay webhook already correct: {result.get('url')}")
        elif result.get("status") == "skipped":
            logger.info(f"FedaPay webhook sync skipped: {result.get('reason')}")
        else:
            logger.warning(f"FedaPay webhook auto-sync failed: {result.get('error')}")
    except Exception as e:
        logger.warning(f"FedaPay webhook sync error (non-blocking): {e}")

    # Auto-sync Resend webhook URL
    try:
        resend_key = str(os.environ.get("RESEND_API_KEY") or "").strip()
        base_url = str(os.environ.get("FRONTEND_BASE_URL") or "").strip().rstrip("/")
        if _webhook_auto_sync_enabled and resend_key and base_url:
            expected_endpoint = f"{base_url}/api/webhooks/resend"
            headers = {"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"}
            timeout = 20

            list_resp = requests.get("https://api.resend.com/webhooks", headers={"Authorization": f"Bearer {resend_key}"}, timeout=timeout)
            if list_resp.status_code == 200:
                existing = (list_resp.json() or {}).get("data", [])
                webhook_events = [
                    "email.sent",
                    "email.delivered",
                    "email.delivery_delayed",
                    "email.bounced",
                    "email.complained",
                    "email.opened",
                    "email.clicked",
                ]

                synced = False
                for wh in existing:
                    wid = str(wh.get("id") or "").strip()
                    endpoint = str(wh.get("endpoint") or "").strip().rstrip("/")
                    if not wid:
                        continue
                    if endpoint == expected_endpoint:
                        patch_payload = {
                            "endpoint": expected_endpoint,
                            "events": webhook_events,
                            "status": "enabled",
                        }
                        patch_resp = requests.patch(f"https://api.resend.com/webhooks/{wid}", headers=headers, json=patch_payload, timeout=timeout)
                        if patch_resp.status_code in (200, 201):
                            logger.info(f"Resend webhook already aligned: {expected_endpoint} (id={wid})")
                        else:
                            logger.warning(f"Resend webhook patch failed for aligned endpoint id={wid}: status={patch_resp.status_code}")
                        synced = True
                        break

                if not synced:
                    stale = sorted(
                        [
                            wh
                            for wh in existing
                            if str((wh.get("endpoint") or "")).strip().endswith("/api/webhooks/resend")
                        ],
                        key=lambda w: str(w.get("created_at") or ""),
                    )
                    if stale:
                        target = stale[-1]
                        wid = str(target.get("id") or "").strip()
                        if wid:
                            patch_payload = {
                                "endpoint": expected_endpoint,
                                "events": webhook_events,
                                "status": "enabled",
                            }
                            patch_resp = requests.patch(f"https://api.resend.com/webhooks/{wid}", headers=headers, json=patch_payload, timeout=timeout)
                            if patch_resp.status_code in (200, 201):
                                logger.info(
                                    "Resend webhook AUTO-SYNCED: %s -> %s (id=%s)",
                                    str(target.get("endpoint") or ""),
                                    expected_endpoint,
                                    wid,
                                )
                                synced = True
                            else:
                                logger.warning("Resend webhook auto-sync patch failed id=%s status=%s", wid, patch_resp.status_code)

                if not synced:
                    create_payload = {
                        "endpoint": expected_endpoint,
                        "events": webhook_events,
                        "status": "enabled",
                    }
                    create_resp = requests.post("https://api.resend.com/webhooks", headers=headers, json=create_payload, timeout=timeout)
                    if create_resp.status_code in (200, 201):
                        logger.info("Resend webhook AUTO-CREATED: %s", expected_endpoint)
                    else:
                        logger.warning("Resend webhook create failed status=%s", create_resp.status_code)
            else:
                logger.warning("Resend webhook list failed status=%s", list_resp.status_code)
    except Exception as e:
        logger.warning(f"Resend webhook sync error (non-blocking): {e}")

    # Auto-sync Stripe webhook URL
    try:
        stripe_key = os.environ.get("STRIPE_API_KEY")
        if _webhook_auto_sync_enabled and stripe_key:
            import stripe
            stripe.api_key = stripe_key
            base_url = os.environ.get("FRONTEND_BASE_URL", "").rstrip("/")
            if base_url:
                correct_url = f"{base_url}/api/webhook/stripe"
                required_events = [
                    "checkout.session.completed",
                    "checkout.session.expired",
                    "payment_intent.succeeded",
                    "payment_intent.payment_failed",
                ]
                webhooks = stripe.WebhookEndpoint.list()
                if webhooks.data:
                    wh = webhooks.data[0]
                    if wh.url != correct_url or set(wh.enabled_events) != set(required_events):
                        stripe.WebhookEndpoint.modify(
                            wh.id, url=correct_url, enabled_events=required_events,
                        )
                        logger.info(f"Stripe webhook AUTO-SYNCED: {wh.url} -> {correct_url}")
                    else:
                        logger.info(f"Stripe webhook already correct: {correct_url}")
                else:
                    new_wh = stripe.WebhookEndpoint.create(url=correct_url, enabled_events=required_events)
                    logger.info(f"Stripe webhook AUTO-CREATED: {correct_url}")
                    if hasattr(new_wh, "secret") and new_wh.secret:
                        logger.info(f"Stripe webhook secret (save to env): {new_wh.secret}")
    except Exception as e:
        logger.warning(f"Stripe webhook sync error (non-blocking): {e}")

    # Auto-sync PayPal webhook URL
    try:
        paypal_client_id = os.environ.get("PAYPAL_CLIENT_ID")
        paypal_secret = os.environ.get("PAYPAL_SECRET")
        paypal_mode = os.environ.get("PAYPAL_MODE", "sandbox")
        if _webhook_auto_sync_enabled and paypal_client_id and paypal_secret:
            import httpx as _httpx
            paypal_api = "https://api-m.paypal.com" if paypal_mode == "live" else "https://api-m.sandbox.paypal.com"
            base_url = os.environ.get("FRONTEND_BASE_URL", "").rstrip("/")
            if base_url:
                correct_url = f"{base_url}/api/webhook/paypal"
                required_events = [
                    "PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DENIED",
                    "PAYMENT.CAPTURE.REFUNDED", "CHECKOUT.ORDER.APPROVED",
                    "CHECKOUT.ORDER.COMPLETED",
                ]
                async with _httpx.AsyncClient(timeout=15.0) as client:
                    token_resp = await client.post(
                        f"{paypal_api}/v1/oauth2/token",
                        auth=(paypal_client_id, paypal_secret),
                        data={"grant_type": "client_credentials"},
                    )
                    pp_token = token_resp.json().get("access_token")
                    if pp_token:
                        wh_id = os.environ.get("PAYPAL_WEBHOOK_ID", "")
                        headers = {"Authorization": f"Bearer {pp_token}", "Content-Type": "application/json"}
                        # Check existing webhook
                        if wh_id:
                            resp = await client.get(f"{paypal_api}/v1/notifications/webhooks/{wh_id}", headers=headers)
                            if resp.status_code == 200:
                                wh = resp.json()
                                if wh.get("url") != correct_url:
                                    await client.patch(
                                        f"{paypal_api}/v1/notifications/webhooks/{wh_id}",
                                        json=[{"op": "replace", "path": "/url", "value": correct_url}],
                                        headers=headers,
                                    )
                                    logger.info(f"PayPal webhook AUTO-SYNCED: {wh.get('url')} -> {correct_url}")
                                else:
                                    logger.info(f"PayPal webhook already correct: {correct_url}")
                            else:
                                logger.warning(f"PayPal webhook ID {wh_id} not found (status {resp.status_code}), creating new")
                                resp_create = await client.post(
                                    f"{paypal_api}/v1/notifications/webhooks",
                                    json={"url": correct_url, "event_types": [{"name": e} for e in required_events]},
                                    headers=headers,
                                )
                                if resp_create.status_code in (200, 201):
                                    new_id = resp_create.json().get("id", "")
                                    logger.info(f"PayPal webhook AUTO-CREATED: {correct_url} (ID: {new_id})")
    except Exception as e:
        logger.warning(f"PayPal webhook sync error (non-blocking): {e}")


# ── Scheduler ────────────────────────────────────────────────────────────────

from scheduler import register as register_scheduler

register_scheduler(app)

# ── Shutdown ─────────────────────────────────────────────────────────────────


@app.on_event("shutdown")
async def shutdown_db_client():
    try:
        from utils.ws_manager import ws_manager

        close_targets = []
        for conns in ws_manager.connections.values():
            close_targets.extend(conns)
        close_targets.extend(ws_manager.public_stream)
        close_targets.extend(ws_manager.admin_activity_listeners)
        close_targets.extend(ws_manager.automation_listeners)
        close_targets.extend(ws_manager.aso_listeners)

        # Deduplicate by object identity in case any socket appears in multiple buckets
        seen = set()
        unique_targets = []
        for ws in close_targets:
            ident = id(ws)
            if ident in seen:
                continue
            seen.add(ident)
            unique_targets.append(ws)

        for ws in unique_targets:
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                continue
    except Exception as exc:
        logger.warning(f"[shutdown] websocket graceful close failed: {exc}")

    client.close()
