"""Middleware definitions — extracted from server.py"""
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.exceptions import RequestValidationError
from routes.db import get_current_user
from routes.db import db as _mw_db
from utils.access_control_engine import required_employee_permission, build_employee_permissions
from utils.public_api_contract import PUBLIC_API_EXACT, PUBLIC_API_PREFIXES
import os
import logging
import time
import asyncio
import re
import secrets
from datetime import timedelta as _timedelta
from routes.platform_monitor import record_request
from observability.request_context import (
    extract_request_observability_context,
    bind_request_context,
    reset_request_context,
)

try:
    from opentelemetry import trace as otel_trace
except Exception:  # pragma: no cover
    otel_trace = None

logger = logging.getLogger(__name__)

E2E_BYPASS_HEADER = "x-e2e-test-bypass"

FAST_CACHE_API_PREFIXES = (
    "/api/health",
    "/api/system/health",
    "/api/system/instance-marker",
    "/api/config/global",
    "/api/config/boot-policy",
    "/api/config/boot-policy/telemetry",
    "/api/config/v2-compliance/runtime",
    "/api/features/registry",
    "/api/system/vanity-metrics",
    "/api/system/live-metrics",
    "/api/public/signups-recent",
    "/api/public/coaching-tip-of-the-day",
    "/api/robots.txt",
    "/api/sitemap.xml",
    "/health",
    "/system/health",
    "/system/instance-marker",
    "/config/global",
    "/features/registry",
    "/system/vanity-metrics",
    "/system/live-metrics",
    "/robots.txt",
    "/sitemap.xml",
)

TRACKING_EXEMPT_PREFIXES = (
    "/api/platform-shell-health/ingest",
    "/api/platform-shell-health/realtime-ingest",
    "/platform-shell-health/ingest",
    "/platform-shell-health/realtime-ingest",
)


def _is_prefixed_path(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def _is_development_runtime() -> bool:
    env_values = [
        str(os.environ.get("ENVIRONMENT") or "").strip().lower(),
        str(os.environ.get("APP_ENV") or "").strip().lower(),
        str(os.environ.get("NODE_ENV") or "").strip().lower(),
    ]
    return any(value in {"dev", "development"} for value in env_values if value)


def _build_allowed_origins() -> list[str]:
    _raw_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
    shell_origins = [
        "https://app.emergent.sh",
        "https://www.emergent.sh",
        "https://app.emergentagent.com",
        "https://www.emergentagent.com",
    ]
    if _raw_origins and _raw_origins != "*":
        explicit = [o.strip() for o in _raw_origins.split(",") if o.strip()]
        merged = explicit + shell_origins
        return list(dict.fromkeys(merged))

    _backend_url = os.environ.get("BACKEND_URL", os.environ.get("REACT_APP_BACKEND_URL", ""))
    _frontend_url = os.environ.get("FRONTEND_BASE_URL", "")
    allowed_origins = [
        "https://realaicoach.app",
        "https://www.realaicoach.app",
        "https://app.realaicoach.app",
    ]
    if _backend_url:
        allowed_origins.append(_backend_url.rstrip("/"))
    if _frontend_url:
        allowed_origins.append(_frontend_url.rstrip("/"))
    allowed_origins.extend(shell_origins)

    # Security: localhost origins removed - preview URLs provide safe development access
    # Localhost should never be allowed in production environments

    return list(dict.fromkeys(allowed_origins))


def _generate_csp_nonce() -> str:
    return secrets.token_urlsafe(16)


def _build_non_api_csp(csp_nonce: str) -> str:
    nonce = str(csp_nonce or "").strip()
    return (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' wss: https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'; "
        "upgrade-insecure-requests"
    )


def register(app: FastAPI):
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Subscription enforcement — platform-wide access control
    from routes.subscription_enforcement import SubscriptionEnforcementMiddleware
    app.add_middleware(SubscriptionEnforcementMiddleware)

    from utils.api_rate_limiter import APIRateLimitMiddleware
    app.add_middleware(APIRateLimitMiddleware)

    # ── CORS — locked to specific origins (no wildcard) ──
    ALLOWED_ORIGINS = _build_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    UPLOAD_CONTENT_LIMITS: tuple[tuple[str, int], ...] = (
        ("/api/careers/video-qa/", 50 * 1024 * 1024),
        ("/api/careers/apply/attachment", 10 * 1024 * 1024),
        ("/api/support/chat/attachment", 10 * 1024 * 1024),
        ("/api/tickets/upload-attachment", 10 * 1024 * 1024),
        ("/api/id-verification/kyc/upload-file", 15 * 1024 * 1024),
        ("/api/id-checker/kyc/upload-file", 15 * 1024 * 1024),
    )

    @app.middleware("http")
    async def upload_content_length_guard_middleware(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            path = request.url.path
            max_bytes = next((limit for prefix, limit in UPLOAD_CONTENT_LIMITS if path.startswith(prefix)), None)
            if max_bytes is not None:
                content_length_raw = str(request.headers.get("content-length") or "").strip()
                if content_length_raw:
                    try:
                        content_length = int(content_length_raw)
                    except ValueError:
                        return JSONResponse(
                            {
                                "detail": "Invalid Content-Length header",
                                "code": "UPLOAD_INVALID_CONTENT_LENGTH",
                            },
                            status_code=400,
                        )
                    if content_length > max_bytes:
                        asyncio.ensure_future(_log_security_incident(request, 413, "UPLOAD_CONTENT_TOO_LARGE"))
                        return JSONResponse(
                            {
                                "detail": f"Payload too large. Max {max_bytes // (1024 * 1024)}MB allowed.",
                                "code": "UPLOAD_CONTENT_TOO_LARGE",
                                "max_bytes": max_bytes,
                                "content_length": content_length,
                            },
                            status_code=413,
                        )
        return await _safe_call_next(request, call_next)

    @app.middleware("http")
    async def observability_context_middleware(request: Request, call_next):
        ctx = extract_request_observability_context(request)
        request.state.correlation_id = ctx.get("correlation_id")
        request.state.trace_id = ctx.get("trace_id")
        request.state.span_id = ctx.get("span_id")
        request.state.session_id = ctx.get("session_id")
        tokens = bind_request_context(ctx)
        start = time.perf_counter()

        if otel_trace:
            try:
                span = otel_trace.get_current_span()
                span_ctx = span.get_span_context() if span else None
                if span and span_ctx and span_ctx.is_valid:
                    span.set_attribute("correlation_id", str(ctx.get("correlation_id") or ""))
                    span.set_attribute("session_id", str(ctx.get("session_id") or ""))
            except Exception:
                pass

        try:
            response = await _safe_call_next(request, call_next)
            duration_ms = (time.perf_counter() - start) * 1000
            response.headers["x-correlation-id"] = str(ctx.get("correlation_id") or "")
            logger.info(
                "http_request method=%s path=%s status=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                int(getattr(response, "status_code", 0) or 0),
                duration_ms,
            )
            return response
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "http_request_failed method=%s path=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                duration_ms,
                exc_info=True,
            )
            raise
        finally:
            reset_request_context(tokens)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            field = " -> ".join(str(loc) for loc in error.get("loc", []))
            errors.append({"field": field, "message": error.get("msg", "Invalid value")})
        return JSONResponse(status_code=422, content={"detail": "Validation error", "errors": errors})

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error. Please try again later."})

    # ── NoSQL INJECTION SANITIZATION ──
    # Strips $-prefixed keys from all incoming JSON request bodies to prevent operator injection.
    # This is a defense-in-depth measure: individual routes should also validate input.
    import json as _nosql_json

    def _strip_dollar_keys(obj):
        """Recursively remove keys starting with $ from dicts."""
        if isinstance(obj, dict):
            return {k: _strip_dollar_keys(v) for k, v in obj.items() if not k.startswith("$")}
        if isinstance(obj, list):
            return [_strip_dollar_keys(item) for item in obj]
        return obj

    NOSQL_EXEMPT_PATHS = frozenset({
        "/api/webhook/stripe",
        "/api/webhook/paypal",
        "/api/payments/paypal/webhook",
        "/api/payments/fedapay/webhook",
    })

    @app.middleware("http")
    async def nosql_sanitization_middleware(request: Request, call_next):
        """Reject requests with MongoDB operator keys ($gt, $regex, etc.) in JSON bodies."""
        if request.method in ("POST", "PUT", "PATCH") and request.url.path not in NOSQL_EXEMPT_PATHS:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    raw_body = await request.body()
                    if raw_body:
                        parsed = _nosql_json.loads(raw_body)
                        sanitized = _strip_dollar_keys(parsed)
                        if parsed != sanitized:
                            ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?")
                            logger.warning(f"NoSQL injection attempt REJECTED: {request.method} {request.url.path} from {ip}")
                            asyncio.ensure_future(_log_security_incident(request, 400, "NOSQL_INJECTION_BLOCKED"))
                            return JSONResponse(
                                {"detail": "Invalid request: illegal operators in body", "code": "NOSQL_INJECTION_BLOCKED"},
                                status_code=400,
                            )
                except (ValueError, UnicodeDecodeError):
                    pass
        return await _safe_call_next(request, call_next)

    # ── SQLi PATTERN GUARD (defense-in-depth) ──
    # Platform uses MongoDB, but this guard blocks common SQL injection probes
    # that often indicate reconnaissance or credential stuffing attacks.
    SQLI_PATTERNS = [
        re.compile(r"(?i)\bunion\s+select\b"),
        re.compile(r"(?i)\binformation_schema\b"),
        re.compile(r"(?i)\bbenchmark\s*\("),
        re.compile(r"(?i)\bsleep\s*\("),
        re.compile(r"(?i)(?:'|\")\s*or\s*1\s*=\s*1"),
        re.compile(r"(?i)\bdrop\s+table\b"),
    ]

    SQLI_EXEMPT_PREFIXES = (
        "/api/webhook/",
        "/api/webhooks/",
    )

    def _looks_like_sqli(value: str) -> bool:
        if not value:
            return False
        sample = value[:3000]
        return any(p.search(sample) for p in SQLI_PATTERNS)

    @app.middleware("http")
    async def sqli_probe_guard_middleware(request: Request, call_next):
        path = request.url.path
        if any(path.startswith(prefix) for prefix in SQLI_EXEMPT_PREFIXES):
            return await _safe_call_next(request, call_next)

        for key, val in request.query_params.items():
            if _looks_like_sqli(str(val)):
                logger.warning("SQLi probe blocked: %s %s param=%s", request.method, path, key)
                asyncio.ensure_future(_log_security_incident(request, 400, "SQLI_PROBE_BLOCKED"))
                return JSONResponse(
                    {"detail": "Invalid request pattern", "code": "SQLI_PROBE_BLOCKED"},
                    status_code=400,
                )

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type or "application/x-www-form-urlencoded" in content_type:
                try:
                    raw = await request.body()
                    if raw and _looks_like_sqli(raw.decode("utf-8", errors="ignore")):
                        logger.warning("SQLi probe blocked in body: %s %s", request.method, path)
                        asyncio.ensure_future(_log_security_incident(request, 400, "SQLI_PROBE_BLOCKED"))
                        return JSONResponse(
                            {"detail": "Invalid request pattern", "code": "SQLI_PROBE_BLOCKED"},
                            status_code=400,
                        )
                except Exception:
                    pass

        return await _safe_call_next(request, call_next)

    # ── CSRF PROTECTION ──
    # Requires X-Requested-With header for state-changing requests.
    # Browsers won't attach custom headers in cross-origin simple requests,
    # so this blocks CSRF attacks from malicious sites.
    CSRF_EXEMPT_PREFIXES = (
        "/api/webhook/",       # Payment/service webhooks
        "/api/webhooks/",      # Resend + other service webhooks
        "/api/payments/paypal/webhook",
        "/api/payments/fedapay/webhook",
        "/api/iap/apple/webhook",
        "/api/iap/google/webhook",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/password/reset/",
        "/api/auth/verify",
        "/api/auth/lookup",
        "/api/auth/sso-config",
        "/api/auth/google/",
        "/api/auth/microsoft/",
        "/api/auth/apple/",
        "/api/auth/action-otp/verify",
        "/api/auth/qr/generate",
        "/api/auth/qr/consume",
        "/api/auth/biometric/webauthn-auth-options",
        "/api/auth/biometric/webauthn-auth-complete",
        "/api/auth/biometric/verify-pin",
        "/auth/login",
        "/auth/register",
        "/auth/password/reset/",
        "/auth/verify",
        "/auth/lookup",
        "/auth/sso-config",
        "/auth/google/",
        "/auth/microsoft/",
        "/auth/apple/",
        "/auth/action-otp/verify",
        "/api/oauth/",         # OAuth callbacks
        "/api/health",         # Health checks
        "/api/cron/",          # Internal cron triggers
        "/api/vitals/",        # Frontend vitals/performance reporting
        "/api/seo/web-vitals", # Public web-vitals telemetry (sendBeacon cannot set custom headers)
        "/api/platform-shell-health/",  # Shell health ingestion
        "/api/admin/session-replay/",   # Session replay recording
        "/api/admin/employees/invitations/",  # Employee invitation accept flow (public)
        "/api/admin/uiem/log",  # UIEM violation logging from frontend
        "/api/admin/v7-templates/log",  # V7 template violation logging from frontend
        "/api/auth-compliance/route-block",  # GTEC: public telemetry from RouteAccessGuard
        "/api/errors/client",  # ErrorBoundary crash reporter (sendBeacon — cannot attach headers)
        "/api/careers/applications/track/",  # Public applicant tracker (withdraw etc.)
        "/api/gps/consistency/check",  # Public self-healing telemetry check from GPS hook
        "/api/config/boot-policy/telemetry",  # Pre-hydration sendBeacon telemetry (no custom headers)
        # i18n auto-translate — called by the DOM translation engine inlined
        # into the HTML (app/+html.tsx). Script is injected pre-React so it
        # cannot read the X-Requested-With header from the React app's
        # token manager. This endpoint is a pure translation lookup with no
        # authenticated side effects, so CSRF exemption is safe. Rate-
        # limiting of this endpoint is enforced at the service layer.
        "/api/i18n/auto-translate",
        "/api/i18n/fallback-hit",
        "/api/workflows",  # Workflow Builder guest-safe APIs (fallback_user_id auth)
        "/api/workflows/",
        "/api/ai-speech-studio/",  # Voice Studio guest-safe APIs (fallback_user_id auth)
        "/api/ai-enterprise/",  # Business Ops Copilot guest-safe APIs (fallback_user_id auth)
        # Feature 26 adapter/control writes rely on authenticated cookie sessions
        # and are already guarded by role/plan checks + deny-by-default auth gate.
        # Exempting from CSRF custom-header requirement preserves legacy client compatibility.
        "/api/hiring/v2/candidate/",
        "/api/hiring/v2/employer/",
    )
    CSRF_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

    @app.middleware("http")
    async def csrf_protection_middleware(request: Request, call_next):
        """Require X-Requested-With header for state-changing requests (CSRF protection)."""
        if request.method not in CSRF_METHODS:
            return await _safe_call_next(request, call_next)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in CSRF_EXEMPT_PREFIXES):
            return await _safe_call_next(request, call_next)

        # Locked-out ID verification recovery (idv_token) must pass without standard CSRF headers.
        idv_token = request.query_params.get("idv_token") or request.headers.get("X-IDV-Access-Token")
        idv_recovery_prefixes = (
            "/api/id-verification/kyc/",
            "/api/id-verification/id-verification/kyc/",
            "/api/id-verification/qr/create",
            "/api/id-verification/qr/status/",
            "/api/id-verification/id-verification/qr/create",
            "/api/id-verification/id-verification/qr/status/",
            "/api/id-verification/qr/mobile/",
            "/api/id-verification/qr/upload/",
            "/api/id-verification/qr/complete/",
            "/api/id-checker/kyc/",
            "/api/id-checker/id-verification/kyc/",
            "/api/id-checker/qr/create",
            "/api/id-checker/qr/status/",
            "/api/id-checker/id-verification/qr/create",
            "/api/id-checker/id-verification/qr/status/",
            "/api/id-checker/qr/mobile/",
            "/api/id-checker/qr/upload/",
            "/api/id-checker/qr/complete/",
            "/api/id-checker/messages",
            "/api/id-verification/messages",
        )
        if idv_token and any(path.startswith(prefix) for prefix in idv_recovery_prefixes):
            return await _safe_call_next(request, call_next)

        # Check for custom header (XMLHttpRequest, fetch, or mobile client)
        has_csrf_header = (
            request.headers.get("x-requested-with")
            or request.headers.get("authorization")
            or request.headers.get("x-csrf-token")
            or "multipart/form-data" in request.headers.get("content-type", "")  # File uploads
        )
        if not has_csrf_header:
            asyncio.ensure_future(_log_security_incident(request, 403, "CSRF_BLOCKED"))
            return JSONResponse(
                {"detail": "CSRF validation failed", "code": "CSRF_BLOCKED"},
                status_code=403,
            )

        return await _safe_call_next(request, call_next)

    # ── SECURITY INCIDENT LOGGER ──
    from datetime import datetime, timezone as _tz

    _incident_buffer: list = []
    _BUFFER_FLUSH_SIZE = 20

    async def _log_security_incident(request: Request, status_code: int, code: str):
        """Buffer security incidents and flush to MongoDB in batches."""
        ip = request.headers.get("x-forwarded-for", request.headers.get("x-real-ip", request.client.host if request.client else "unknown"))
        if "," in ip:
            ip = ip.split(",")[0].strip()
        ua = request.headers.get("user-agent", "")[:200]

        incident = {
            "ts": datetime.now(_tz.utc).isoformat(),
            "path": request.url.path[:300],
            "method": request.method,
            "status": status_code,
            "code": code,
            "ip": ip,
            "ua": ua,
        }
        _incident_buffer.append(incident)

        if len(_incident_buffer) >= _BUFFER_FLUSH_SIZE:
            await _flush_incidents()

    async def _flush_incidents():
        """Write buffered incidents to MongoDB."""
        if not _incident_buffer:
            return
        batch = _incident_buffer.copy()
        _incident_buffer.clear()
        try:
            await _mw_db.security_incidents.insert_many(batch, ordered=False)
        except Exception as e:
            logger.warning(f"Security incident flush failed: {e}")

    # Periodic flush every 30s (catches low-traffic tail)
    async def _periodic_incident_flush():
        while True:
            await asyncio.sleep(30)
            await _flush_incidents()

    @app.on_event("startup")
    async def _start_incident_flusher():
        asyncio.create_task(_periodic_incident_flush())

    # ── RESPONSE SANITIZATION (strip sensitive fields from AUTH JSON responses) ──
    SENSITIVE_FIELDS = frozenset({
        "_id", "password_hash", "pin_hash", "otp_hash", "otp_secret",
        "otp_code", "token_hash", "reset_token", "magic_link_token",
        "biometric_key", "webauthn_credential", "secret_key",
    })

    SENSITIVE_FIELD_ROUTE_ALLOWLIST = {
        ("POST", "/api/auth/admin/e2e/otp/issue"): frozenset({"otp_code"}),
    }

    def _sanitize_value(obj, allowed_sensitive_fields=None):
        """Recursively strip sensitive fields from dicts/lists."""
        allowed_fields = allowed_sensitive_fields or frozenset()
        if isinstance(obj, dict):
            return {
                k: _sanitize_value(v, allowed_fields)
                for k, v in obj.items()
                if (k not in SENSITIVE_FIELDS) or (k in allowed_fields)
            }
        if isinstance(obj, list):
            return [_sanitize_value(item, allowed_fields) for item in obj]
        return obj

    # ── IDOR PROTECTION (user_id ownership enforcement) ──
    import re as _idor_re

    _USER_ID_RE = _idor_re.compile(r"^user_[0-9a-f]{12}$")

    # Paths where accessing another user's data is intentionally allowed
    IDOR_EXEMPT_PREFIXES = (
        "/api/admin/",       # Admin routes have dedicated admin auth
        "/api/share/",       # Public shared content by design
        "/api/auth/",        # Auth flows (no user_id path params)
        "/api/oauth/",       # OAuth callbacks
    )

    @app.middleware("http")
    async def idor_ownership_enforcement_middleware(request: Request, call_next):
        """Prevent IDOR: any user_id in URL path must match the authenticated user. Admins exempt."""
        path = request.url.path
        method = request.method

        # Skip non-API, OPTIONS, and exempt paths
        if method == "OPTIONS" or not path.startswith("/api/"):
            return await _safe_call_next(request, call_next)

        if any(path.startswith(prefix) for prefix in IDOR_EXEMPT_PREFIXES):
            return await _safe_call_next(request, call_next)

        # Extract user_id-shaped segments from the URL path
        segments = path.split("/")
        path_user_ids = [seg for seg in segments if _USER_ID_RE.match(seg)]

        if not path_user_ids:
            # No user_id in path — nothing to enforce
            return await _safe_call_next(request, call_next)

        # A user_id is in the path — verify ownership
        user = await _get_cached_user(request)
        if not user:
            # Auth middleware will handle the 401 — let it through
            return await _safe_call_next(request, call_next)

        # Admins can access any user's data
        if user.is_admin:
            return await _safe_call_next(request, call_next)

        # Non-admin: path user_id MUST match authenticated user
        for path_uid in path_user_ids:
            if path_uid != user.user_id:
                asyncio.ensure_future(_log_security_incident(request, 403, "IDOR_BLOCKED"))
                return JSONResponse(
                    {"detail": "Access denied", "code": "IDOR_BLOCKED"},
                    status_code=403,
                )

        return await _safe_call_next(request, call_next)

    def _allow_native_token_response(request: Request) -> bool:
        channel_hint = str(
            request.headers.get("X-Client-Platform")
            or request.headers.get("X-Auth-Channel")
            or ""
        ).strip().lower()
        return channel_hint in {"mobile", "native", "android", "ios", "expo"}

    AUTH_TOKEN_REDACT_PATHS = {
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/renew-session",
        "/api/auth/token/refresh",
        "/api/auth/google/session",
        "/api/auth/microsoft/exchange",
        "/api/auth/apple/exchange",
    }
    MAX_AUTH_SANITIZE_BYTES = 256 * 1024

    def _is_auth_sanitization_path(path: str) -> bool:
        if path == "/api/auth":
            return True
        return path.startswith("/api/auth/")

    def _is_trusted_binary_content_type(content_type: str) -> bool:
        ctype = str(content_type or "").split(";", 1)[0].strip().lower()
        if not ctype:
            return False
        return (
            ctype == "application/octet-stream"
            or ctype.startswith("image/")
            or ctype.startswith("video/")
        )

    @app.middleware("http")
    async def response_sanitization_middleware(request: Request, call_next):
        """Strip sensitive fields (_id, password_hash, etc.) from JSON auth responses."""
        response = await _safe_call_next(request, call_next)
        path = request.url.path

        # Only sanitize auth API JSON responses (skip static, streaming, binary, OPTIONS)
        if request.method == "OPTIONS" or not _is_auth_sanitization_path(path):
            return response

        content_type = response.headers.get("content-type", "")
        if _is_trusted_binary_content_type(content_type):
            return response

        content_type_lower = content_type.lower()
        if "application/json" not in content_type_lower:
            return response

        # Skip streaming responses (SSE, live-metrics)
        if "text/event-stream" in content_type_lower or response.status_code == 204:
            return response

        content_length_raw = response.headers.get("content-length")
        if content_length_raw:
            try:
                if int(content_length_raw) > MAX_AUTH_SANITIZE_BYTES:
                    return response
            except ValueError:
                pass

        body = b""
        try:
            body_parts = []
            async for chunk in response.body_iterator:
                body_parts.append(chunk if isinstance(chunk, bytes) else chunk.encode())
            body = b"".join(body_parts)

            if not body:
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
                    media_type="application/json",
                )

            import json as _json
            data = _json.loads(body)
            allowed_sensitive_fields = SENSITIVE_FIELD_ROUTE_ALLOWLIST.get(
                (request.method.upper(), path),
                frozenset(),
            )
            sanitized = _sanitize_value(data, allowed_sensitive_fields)
            if (
                request.method.upper() == "POST"
                and path in AUTH_TOKEN_REDACT_PATHS
                and not _allow_native_token_response(request)
                and isinstance(sanitized, dict)
            ):
                sanitized.pop("session_token", None)
                sanitized.pop("refresh_token", None)
            sanitized_body = _json.dumps(sanitized, default=str).encode()

            # Build new headers without stale Content-Length
            new_headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}

            return Response(
                content=sanitized_body,
                status_code=response.status_code,
                headers=new_headers,
                media_type="application/json",
            )
        except Exception:
            # If JSON parsing fails, return original body
            return Response(
                content=body,
                status_code=response.status_code,
                headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
                media_type=content_type or "application/json",
            )

    async def _safe_call_next(request: Request, call_next):
        try:
            return await call_next(request)
        except RuntimeError as exc:
            if "No response returned" in str(exc):
                logger.warning("Client disconnected before response completed: %s %s", request.method, request.url.path)
                return Response(status_code=204)
            raise

    async def _get_cached_user(request: Request):
        if hasattr(request.state, "_cached_user_loaded"):
            return getattr(request.state, "_cached_user", None)
        user = await get_current_user(request)
        request.state._cached_user_loaded = True
        request.state._cached_user = user
        return user

    # ── GLOBAL AUTH ENFORCEMENT (deny-by-default) ──
    # Whitelist of truly public API routes that do NOT require authentication.
    # Everything else under /api/* MUST have a valid session/JWT.
    AUTH_PUBLIC_PREFIXES = tuple(PUBLIC_API_PREFIXES)
    AUTH_PUBLIC_EXACT = set(PUBLIC_API_EXACT)

    @app.middleware("http")
    async def global_auth_enforcement_middleware(request: Request, call_next):
        """Deny-by-default: all /api/* routes require authentication unless whitelisted."""
        path = request.url.path
        method = request.method

        # Skip non-API routes and OPTIONS preflight
        if method == "OPTIONS" or not path.startswith("/api/"):
            return await _safe_call_next(request, call_next)

        # Platform Operations Control Center global lock gate.
        # Blocks non-admin traffic during maintenance/emergency while allowing
        # explicit public/system exempt endpoints.
        try:
            from routes.platform_control import (
                build_lock_response_payload,
                can_staff_read_only_bypass,
                get_effective_platform_control_state,
                is_platform_lock_active,
                is_request_exempt_from_platform_lock,
            )

            if not is_request_exempt_from_platform_lock(path):
                control_state = await get_effective_platform_control_state(force_refresh=False)
                if is_platform_lock_active(control_state):
                    user = await _get_cached_user(request)
                    if user and user.is_admin:
                        return await _safe_call_next(request, call_next)
                    if can_staff_read_only_bypass(user, control_state, method):
                        return await _safe_call_next(request, call_next)

                    lock_payload = build_lock_response_payload(control_state)
                    countdown_seconds = lock_payload.get("countdown_seconds")
                    retry_after = max(30, int(countdown_seconds)) if isinstance(countdown_seconds, int) else 300
                    return JSONResponse(
                        status_code=503,
                        content=lock_payload,
                        headers={
                            "Retry-After": str(retry_after),
                            "X-Platform-Control-Mode": str(lock_payload.get("active_mode") or "MAINTENANCE"),
                        },
                    )
        except Exception as exc:
            logger.warning("Platform control gate skipped due to runtime issue: %s", exc)

        # Allow exact public matches
        if path in AUTH_PUBLIC_EXACT:
            return await _safe_call_next(request, call_next)

        # Allow prefix-based public matches
        if any(path.startswith(prefix) for prefix in AUTH_PUBLIC_PREFIXES):
            return await _safe_call_next(request, call_next)

        # Allow locked-out ID verification recovery flows when a temporary IDV token is provided.
        idv_token = request.query_params.get("idv_token") or request.headers.get("X-IDV-Access-Token")
        idv_recovery_prefixes = (
            "/api/id-verification/kyc/",
            "/api/id-verification/id-verification/kyc/",
            "/api/id-verification/qr/create",
            "/api/id-verification/qr/status/",
            "/api/id-verification/id-verification/qr/create",
            "/api/id-verification/id-verification/qr/status/",
            "/api/id-verification/qr/mobile/",
            "/api/id-verification/qr/upload/",
            "/api/id-verification/qr/complete/",
            "/api/id-checker/kyc/",
            "/api/id-checker/id-verification/kyc/",
            "/api/id-checker/qr/create",
            "/api/id-checker/qr/status/",
            "/api/id-checker/id-verification/qr/create",
            "/api/id-checker/id-verification/qr/status/",
            "/api/id-checker/qr/mobile/",
            "/api/id-checker/qr/upload/",
            "/api/id-checker/qr/complete/",
            "/api/id-checker/messages",
            "/api/id-verification/messages",
        )
        if idv_token and any(path.startswith(prefix) for prefix in idv_recovery_prefixes):
            return await _safe_call_next(request, call_next)

        # Everything else: require authentication
        user = await _get_cached_user(request)
        if not user:
            # Log security incident
            asyncio.ensure_future(_log_security_incident(request, 401, "AUTH_REQUIRED"))
            return JSONResponse(
                {"detail": "Authentication required", "code": "AUTH_REQUIRED"},
                status_code=401,
            )

        return await _safe_call_next(request, call_next)

    @app.middleware("http")
    async def performance_tracking_middleware(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await _safe_call_next(request, call_next)
            duration_ms = (time.perf_counter() - start) * 1000
            if not _is_prefixed_path(request.url.path, TRACKING_EXEMPT_PREFIXES):
                record_request(request.url.path, request.method, response.status_code, duration_ms)
            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            if not _is_prefixed_path(request.url.path, TRACKING_EXEMPT_PREFIXES):
                record_request(request.url.path, request.method, 500, duration_ms, str(e))
            raise

    @app.middleware("http")
    async def hiring_rate_limit_middleware(request: Request, call_next):
        path = request.url.path
        hiring_prefixes = ("/api/aris/", "/api/smart-scheduler/", "/api/fairness/", "/api/learning/", "/api/experience/", "/api/hiring-analytics/")
        if any(path.startswith(p) for p in hiring_prefixes) and request.method != "OPTIONS":
            user = await _get_cached_user(request)
            if user:
                from utils.rate_limit import check_rate_limit
                ip = request.client.host if request.client else "unknown"
                if not check_rate_limit(f"hiring:{user.user_id}:{ip}", 30, 60):
                    return JSONResponse({"detail": "Rate limit exceeded. Please try again shortly."}, status_code=429)
        return await _safe_call_next(request, call_next)

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        csp_nonce = _generate_csp_nonce()
        request.state.csp_nonce = csp_nonce
        response = await _safe_call_next(request, call_next)
        path = request.url.path

        # SSE streams must never be cached. Detect by Content-Type and skip
        # all Cache-Control rewriting below so the endpoint's own headers win.
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/event-stream"):
            response.headers["Cache-Control"] = "no-cache, no-transform"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response

        # Cache-Control policy
        if path.startswith("/api/static/"):
            response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        elif path in ("/manifest.json", "/sw.js"):
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        elif path in ("/api/robots.txt", "/api/sitemap.xml"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        elif path.startswith("/api/"):
            if request.method in {"GET", "HEAD"} and _is_prefixed_path(path, FAST_CACHE_API_PREFIXES):
                response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=30"
            else:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        preview_frame_safe_prefixes = (
            "/api/r/v",
            "/api/r/t",
            "/api/r/f",
            "/api/r/x",
            "/api/payments/export-pdf",
            "/api/mock-interview/",
            "/api/auth/microsoft/",
            "/api/auth/apple/",
            "/api/auth/google/",
            "/api/oauth/",
            "/api/calendar/connect",
        )
        if not any(request.url.path.startswith(prefix) for prefix in preview_frame_safe_prefixes):
            response.headers["X-Frame-Options"] = "DENY"
        elif "X-Frame-Options" in response.headers:
            del response.headers["X-Frame-Options"]
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Vary"] = "Accept-Encoding"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self), payment=(self)"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-DNS-Prefetch-Control"] = "off"
        is_pdf_response = response.headers.get("content-type", "").startswith("application/pdf")
        if is_pdf_response or any(request.url.path.startswith(prefix) for prefix in preview_frame_safe_prefixes):
            response.headers["Cross-Origin-Opener-Policy"] = "unsafe-none"
            response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        else:
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        # Content-Security-Policy - enterprise-grade (hardened)
        if not path.startswith("/api/"):
            response.headers["Content-Security-Policy"] = _build_non_api_csp(csp_nonce)
        else:
            # API responses: minimal CSP + no framing
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response

    # NOTE: Subscription enforcement is handled by SubscriptionEnforcementMiddleware
    # (registered above via app.add_middleware). No duplicate inline middleware needed.

    @app.middleware("http")
    async def waf_middleware(request: Request, call_next):
        """Web Application Firewall — with in-memory caching for blocked IPs and geo rules."""
        import re as _re
        from urllib.parse import unquote as _unquote
        import time as _time
        from datetime import datetime as _dt, timezone as _tz

        path = request.url.path
        if request.method == "OPTIONS" or path.startswith("/api/static/"):
            return await _safe_call_next(request, call_next)

        bypass_test_rate_limit = False
        if path.startswith("/api/"):
            try:
                from utils.api_rate_limiter import is_e2e_rate_limit_exempt_request

                bypass_test_rate_limit = await is_e2e_rate_limit_exempt_request(request)
            except Exception:
                bypass_test_rate_limit = False

        waf_public_exempt_prefixes = (
            "/api/health", "/api/system/health", "/api/system/instance-marker", "/api/vitals/report",
            "/api/payments/currencies", "/api/changelog/latest",
            "/api/home/dashboard-stats", "/api/home/badges", "/api/home/tour-status",
            "/api/i18n/user-preference", "/api/i18n/language-guidance",
            "/api/config/global", "/api/config/boot-policy", "/api/config/boot-policy/telemetry", "/api/config/v2-compliance/runtime", "/api/features/registry",
            "/api/system/vanity-metrics", "/api/system/live-metrics",
            "/api/auth/login", "/api/auth/register", "/api/auth/me",
            "/api/prompt-experiment/",
        )
        if any(path.startswith(prefix) for prefix in waf_public_exempt_prefixes):
            return await _safe_call_next(request, call_next)

        waf_ip_rate_exempt_prefixes = (
            "/api/admin/live-activity/log-event",
            "/api/home/dashboard-stats", "/api/home/badges",
            "/api/home/tour-status", "/api/notifications/",
            "/api/payments/receipt/", "/api/payments/invoice/",
            "/api/referrals/admin/integrity-alerts",
            "/api/referrals/admin/integrity-trends",
            "/api/referrals/admin/fraud-policy/recommendation",
            "/api/referrals/admin/fraud-policy/apply-recommendation",
        )
        skip_waf_ip_rate_limit = any(path.startswith(prefix) for prefix in waf_ip_rate_exempt_prefixes)
        if bypass_test_rate_limit:
            skip_waf_ip_rate_limit = True

        from routes.security_engine import (
            WAF_PATTERNS, db as sec_db, BOT_PATTERNS, ALLOWED_BOTS,
            _ip_request_log, IP_RATE_LIMIT_WINDOW, IP_RATE_LIMIT_MAX
        )

        client_ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "")[:300]
        now_ts = _time.time()
        now_dt = _dt.now(_tz.utc)

        # ── In-memory blocked IP cache (refresh every 30s) ──
        if not hasattr(waf_middleware, "_blocked_cache"):
            waf_middleware._blocked_cache = set()
            waf_middleware._blocked_ts = 0
        if now_ts - waf_middleware._blocked_ts > 30:
            try:
                docs = await sec_db.blocked_ips.find(
                    {"expires_at": {"$gt": now_dt}},
                    {
                        "ip": 1,
                        "_id": 0,
                        "auto": 1,
                        "reason": 1,
                        "threshold": 1,
                        "window_minutes": 1,
                    },
                ).to_list(500)

                high_risk_codes = {
                    "CSRF_BLOCKED",
                    "IDOR_BLOCKED",
                    "WAF_BLOCKED",
                    "BOT_BLOCKED",
                    "GEO_BLOCKED",
                    "RATE_LIMITED",
                    "SQLI_PROBE_BLOCKED",
                    "NOSQL_INJECTION_BLOCKED",
                    "UPLOAD_CONTENT_TOO_LARGE",
                }

                active_blocked = set()
                for d in docs:
                    ip_entry = str(d.get("ip") or "").strip()
                    if not ip_entry:
                        continue

                    # Backward-compatible protection:
                    # older auto-block records were created from benign AUTH_REQUIRED noise.
                    # Enforce only when there is still enough high-risk evidence in window.
                    if bool(d.get("auto")) and str(d.get("reason") or "") == "auto-block: incident threshold exceeded":
                        threshold = max(1, int(d.get("threshold") or 100))
                        window_minutes = max(1, int(d.get("window_minutes") or 60))
                        cutoff_iso = (now_dt - _timedelta(minutes=window_minutes)).isoformat()
                        high_risk_count = await sec_db.security_incidents.count_documents(
                            {
                                "ip": ip_entry,
                                "ts": {"$gte": cutoff_iso},
                                "$or": [
                                    {"code": {"$in": list(high_risk_codes)}},
                                    {"status": 429},
                                ],
                            }
                        )
                        if int(high_risk_count) < threshold:
                            continue

                    active_blocked.add(ip_entry)

                waf_middleware._blocked_cache = active_blocked
                waf_middleware._blocked_ts = now_ts
            except Exception:
                pass
        if client_ip in waf_middleware._blocked_cache:
            return JSONResponse({"detail": "IP blocked", "code": "IP_BLOCKED"}, status_code=403)

        # ── In-memory geo-block cache (refresh every 60s) ──
        if not hasattr(waf_middleware, "_geo_cache"):
            waf_middleware._geo_cache = set()
            waf_middleware._geo_ts = 0
        req_country = request.headers.get("cf-ipcountry", request.headers.get("x-country", "")).upper()
        if req_country:
            if now_ts - waf_middleware._geo_ts > 60:
                try:
                    docs = await sec_db.geo_block_rules.find({"enabled": True}, {"country_code": 1, "_id": 0}).to_list(300)
                    waf_middleware._geo_cache = {d["country_code"] for d in docs}
                    waf_middleware._geo_ts = now_ts
                except Exception:
                    pass
            if req_country in waf_middleware._geo_cache:
                return JSONResponse({"detail": "Access restricted in your region", "code": "GEO_BLOCKED"}, status_code=403)

        # ── Bot detection (in-memory only) ──
        if ua:
            for bp in BOT_PATTERNS:
                if _re.search(bp, ua):
                    if not any(ab.lower() in ua.lower() for ab in ALLOWED_BOTS):
                        return JSONResponse({"detail": "Bot access restricted", "code": "BOT_BLOCKED"}, status_code=403)
                    break

        # ── Per-IP rate limiting (in-memory only) ──
        if client_ip != "unknown" and not skip_waf_ip_rate_limit:
            if client_ip not in _ip_request_log:
                _ip_request_log[client_ip] = []
            _ip_request_log[client_ip] = [t for t in _ip_request_log[client_ip] if now_ts - t < IP_RATE_LIMIT_WINDOW]
            _ip_request_log[client_ip].append(now_ts)
            if len(_ip_request_log[client_ip]) > IP_RATE_LIMIT_MAX:
                return JSONResponse(
                    {"detail": "Rate limit exceeded", "code": "RATE_LIMITED", "retry_after": IP_RATE_LIMIT_WINDOW},
                    status_code=429,
                    headers={"Retry-After": str(IP_RATE_LIMIT_WINDOW)},
                )

        # ── WAF pattern matching ──
        raw_query = str(request.url.query) if request.url.query else ""
        check_str = f"{_unquote(path)} {_unquote(raw_query)}"
        for rule in WAF_PATTERNS:
            if not rule.get("enabled"):
                continue
            try:
                if _re.search(rule["pattern"], check_str):
                    logger.warning(f"[WAF] Blocked {rule['name']} from {client_ip}: {path[:80]}")
                    return JSONResponse({"detail": "Request blocked by security policy", "code": "WAF_BLOCKED"}, status_code=403)
            except Exception:
                continue
        return await _safe_call_next(request, call_next)

    @app.middleware("http")
    async def admin_only_middleware(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/admin"):
            return await _safe_call_next(request, call_next)
        # Allow authenticated telemetry/session endpoints used by non-admin user flows
        admin_bypass_prefixes = (
            "/api/admin/session-replay/record",
            "/api/admin/session-replay/end",
            "/api/admin/live-activity/log-event",
            "/api/admin/autonomous-engine/feedback/collect",
            "/api/admin/autonomous-engine/certificate/verify/",
            "/api/admin/employees/invitations/verify",
            "/api/admin/employees/invitations/accept",
            "/api/admin/employees/invitations/decline",
            "/api/admin/uiem/log",
            "/api/admin/v7-templates/log",
        )
        if any(path.startswith(prefix) for prefix in admin_bypass_prefixes):
            return await _safe_call_next(request, call_next)
        user = await _get_cached_user(request)
        if not user:
            asyncio.ensure_future(_log_security_incident(request, 403, "ADMIN_NO_AUTH"))
            return JSONResponse({"detail": "Admin access required"}, status_code=403)
        if user.is_admin:
            return await _safe_call_next(request, call_next)

        permission = required_employee_permission(path)
        granted = set(build_employee_permissions({
            "platform_role": getattr(user, "platform_role", None),
            "employee_permissions": list(getattr(user, "employee_permissions", []) or []),
        }))
        if permission and permission in granted:
            return await _safe_call_next(request, call_next)

        if permission:
            asyncio.ensure_future(_log_security_incident(request, 403, "ADMIN_PERMISSION_DENIED"))
            return JSONResponse(
                {"detail": "Admin access required", "required_permission": permission},
                status_code=403,
            )
        asyncio.ensure_future(_log_security_incident(request, 403, "ADMIN_ACCESS_DENIED"))
        return JSONResponse({"detail": "Admin access required"}, status_code=403)

    @app.middleware("http")
    async def production_security_policy_gate_middleware(request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Fast-path: skip for high-frequency safe endpoints
        _gate_skip_prefixes = (
            "/api/health", "/api/system/health", "/api/system/instance-marker", "/api/config/global", "/api/config/boot-policy", "/api/config/boot-policy/telemetry", "/api/config/v2-compliance/runtime",
            "/api/features/registry", "/api/vitals/report", "/api/static/",
            "/api/system/vanity-metrics", "/api/system/live-metrics",
            "/api/prompt-experiment/", "/api/home/dashboard-stats",
        )
        if method == "OPTIONS" or any(path.startswith(p) for p in _gate_skip_prefixes):
            return await _safe_call_next(request, call_next)

        from utils.production_security_policy_gate import (
            evaluate_policy_gate_decision,
            persist_policy_gate_audit,
            should_enforce_policy_gate,
        )

        if not should_enforce_policy_gate(path, method):
            return await _safe_call_next(request, call_next)

        user = await _get_cached_user(request)
        decision = await evaluate_policy_gate_decision(path, method, user)

        try:
            await persist_policy_gate_audit(decision)
        except Exception as exc:
            logger.warning("Policy gate audit persistence failed: %s", exc)

        if not decision.get("allowed"):
            body = {
                "detail": "Blocked by Production Security Policy Gate",
                "code": "PRODUCTION_POLICY_GATE_BLOCKED",
                "reason_code": decision.get("reason_code"),
                "message": decision.get("message"),
                "gate_scope": decision.get("scope"),
                "failed_checks": decision.get("failed_checks", []),
                "decision_id": decision.get("decision_id"),
            }

            if decision.get("reason_code") == "subscription_required":
                body.update(
                    {
                        "error": "Subscription Required",
                        "required_plan": decision.get("required_plan", "basic"),
                        "current_plan": decision.get("current_plan", "free"),
                        "upgrade_url": "/subscription/plans",
                    }
                )
                from utils.preprod_entitlement_lock import is_preprod_lock_active

                if is_preprod_lock_active():
                    body["detail"] = "Subscriptions are disabled until production launch."
                    body["message"] = "Subscriptions are disabled until production launch."
            if decision.get("reason_code") == "admin_or_employee_permission_required":
                body["required_permission"] = decision.get("required_permission")

            return JSONResponse(
                status_code=int(decision.get("status_code") or 403),
                content=body,
                headers={
                    "X-Policy-Gate": "blocked",
                    "X-Policy-Gate-Decision": str(decision.get("decision_id") or ""),
                },
            )

        response = await _safe_call_next(request, call_next)
        response.headers["X-Policy-Gate"] = "allowed"
        response.headers["X-Policy-Gate-Decision"] = str(decision.get("decision_id") or "")
        return response
