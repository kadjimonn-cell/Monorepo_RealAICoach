"""Per-endpoint API rate limiting middleware.

Tracks request counts per IP+endpoint combination using an in-process sliding
window. Returns 429 Too Many Requests when limits are exceeded.

The backend runs as a single uvicorn worker, so an in-memory window is exact.

Default limits (requests/window):
- Auth endpoints: 20/min
- AI features: 30/min
- Admin endpoints: 60/min
- General API: 100/min
"""

import time
import os
import asyncio
import hmac
from collections import deque
from typing import Dict, Tuple, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

# Per-endpoint rate limits: (max_requests, window_seconds)
# Increased login limit to 30/min for better UX during testing/demos
ENDPOINT_LIMITS: Dict[str, Tuple[int, int]] = {
    "/api/auth/login": (30, 60),
    "/api/auth/me": (240, 60),
    "/api/auth/renew-session": (120, 60),
    "/api/auth/register": (10, 60),
    "/api/auth/otp/verify": (15, 60),
    "/api/auth/password/reset": (5, 300),
    "/api/auth/2fa/enable": (5, 60),
    "/api/auth/2fa/disable": (5, 60),
    "/api/auth/biometric/set-pin": (5, 60),
    "/api/auth/biometric/webauthn-register-options": (5, 60),
}

PREFIX_LIMITS: Dict[str, Tuple[int, int]] = {
    "/api/auth/": (60, 60),  # Increased from 30 to 60 for better UX
    "/api/ai/": (100, 60),   # Increased from 50 to 100
    "/api/admin/": (300, 60), # Increased from 150 to 300
    "/api/subscriptions/": (300, 60),  # Admin console/banner flows can burst during render
    "/api/messaging/": (100, 60),  # Increased from 60 to 100
    "/api/messages/": (100, 60),   # Increased from 60 to 100
    "/api/features/": (500, 60),  # Very high limit for feature flags
    "/api/config/": (500, 60),    # Very high limit for config endpoints
    "/api/system/": (600, 60),    # Live metrics can burst from multiple mounted shells
    "/api/home/": (200, 60),      # Home dashboard endpoints
    "/api/payments/": (2000, 60),  # Very high limit for payment endpoints (currencies polled frequently by frontend)
    "/api/changelog": (200, 60),  # Changelog endpoint
    "/api/contact": (100, 60),    # Contact endpoint
    "/api/i18n/": (500, 60),      # i18n endpoints polled frequently
    "/api/notifications/": (200, 60),  # Notification endpoints
    "/api/live-activity/": (200, 60),  # Live activity endpoints
}

DEFAULT_LIMIT = (300, 60)  # Increased from 200 to 300 for better UX
ADMIN_AUTH_LIMIT = (600, 60)  # Increased from 400 to 600 for admin users
ADMIN_TOKEN_CACHE_TTL_SECONDS = 5
ADMIN_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_ADMIN_TOKEN_CACHE_PREFIX = "api_rate_limiter:admin"
_E2E_TOKEN_CACHE_PREFIX = "api_rate_limiter:e2e"
E2E_BYPASS_HEADER = "x-e2e-test-bypass"
E2E_BYPASS_TOKEN_ENV_KEY = "E2E_RATE_LIMIT_BYPASS_TOKEN"
E2E_BYPASS_FALLBACK_VALUES = frozenset({"1", "true", "yes", "playwright", "playwright-e2e", "e2e"})
E2E_TEST_EMAIL_ALLOWLIST = frozenset(
    {
        "admin@realaicoach.app",
        "f22.premium.20260613@example.com",
        "f22.basic.20260613@example.com",
        "p1.free.1779113329@example.com",
        "curation.1779076352@example.com",
        "nova.v2.1779074133@example.com",
    }
)

# In-process TTL cache backing the admin/e2e token lookups.
_bool_cache: Dict[str, Tuple[bool, float]] = {}
_BOOL_CACHE_MAX_KEYS = 20000


async def _cache_get_bool(prefix: str, token: str) -> Optional[bool]:
    entry = _bool_cache.get(f"{prefix}:{token}")
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at <= time.time():
        _bool_cache.pop(f"{prefix}:{token}", None)
        return None
    return value


async def _cache_set_bool(prefix: str, token: str, value: bool, ttl_seconds: int) -> None:
    if len(_bool_cache) > _BOOL_CACHE_MAX_KEYS:
        now = time.time()
        for key in [k for k, (_, exp) in _bool_cache.items() if exp <= now]:
            _bool_cache.pop(key, None)
    _bool_cache[f"{prefix}:{token}"] = (bool(value), time.time() + ttl_seconds)


async def _cache_delete(prefix: str, token: str) -> None:
    _bool_cache.pop(f"{prefix}:{token}", None)


class _MemorySlidingWindow:
    """In-process sliding window rate limiter."""

    _MAX_KEYS = 50000

    def __init__(self) -> None:
        self._windows: Dict[str, deque] = {}
        self._lock = asyncio.Lock()
        self._last_prune_ms = 0

    async def allow(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        now_ms = int(time.time() * 1000)
        window_ms = int(window * 1000)
        cutoff = now_ms - window_ms

        async with self._lock:
            if now_ms - self._last_prune_ms > 60000 and len(self._windows) > self._MAX_KEYS:
                stale = [k for k, dq in self._windows.items() if not dq or dq[-1] <= cutoff]
                for k in stale:
                    self._windows.pop(k, None)
                self._last_prune_ms = now_ms

            dq = self._windows.get(key)
            if dq is None:
                dq = deque()
                self._windows[key] = dq

            while dq and dq[0] <= cutoff:
                dq.popleft()

            count = len(dq)
            if count >= limit:
                retry_ms = max(1, dq[0] + window_ms - now_ms) if dq else window_ms
                retry_after = max(1, int((retry_ms + 999) / 1000))
                return False, 0, retry_after

            dq.append(now_ms)
            return True, max(0, limit - count - 1), 0


class SlidingWindowCounter:
    """In-memory sliding window rate limiter."""

    def __init__(self) -> None:
        self._window = _MemorySlidingWindow()

    async def allow(self, key: str, limit: int, window: int) -> Tuple[bool, int, int]:
        return await self._window.allow(key, limit, window)


_counter = SlidingWindowCounter()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _extract_session_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            return token

    cookie_token = str(request.cookies.get("session_token") or "").strip()
    if cookie_token:
        return cookie_token

    return ""


def _has_valid_e2e_bypass_header(request: Request) -> bool:
    header_value = str(request.headers.get(E2E_BYPASS_HEADER) or "").strip()
    if not header_value:
        return False

    configured_token = str(os.environ.get(E2E_BYPASS_TOKEN_ENV_KEY) or "").strip()
    if configured_token:
        return hmac.compare_digest(header_value, configured_token)

    return header_value.lower() in E2E_BYPASS_FALLBACK_VALUES


def _get_limit(path: str) -> Tuple[int, int]:
    if path in ENDPOINT_LIMITS:
        return ENDPOINT_LIMITS[path]
    for prefix, limit in PREFIX_LIMITS.items():
        if path.startswith(prefix):
            return limit
    return DEFAULT_LIMIT


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
    return "localhost" in frontend_host or "127.0.0.1" in frontend_host or "preview.emergentagent.com" in frontend_host


async def _is_authenticated_admin(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return False

    token = auth.split(" ", 1)[1].strip()
    if not token:
        return False

    path = request.url.path
    method = request.method.upper()
    bypass_cache = path.startswith("/api/admin/") and method in ADMIN_MUTATION_METHODS

    if bypass_cache:
        await _cache_delete(_ADMIN_TOKEN_CACHE_PREFIX, token)

    if not bypass_cache:
        cached = await _cache_get_bool(_ADMIN_TOKEN_CACHE_PREFIX, token)
        if cached is not None:
            return cached

    try:
        from routes.db import db

        session = await db.sessions.find_one({"session_token": token, "is_active": True}, {"_id": 0, "user_id": 1})
        if not session:
            if not bypass_cache:
                await _cache_set_bool(_ADMIN_TOKEN_CACHE_PREFIX, token, False, ADMIN_TOKEN_CACHE_TTL_SECONDS)
            return False

        user = await db.users.find_one({"user_id": session.get("user_id")}, {"_id": 0, "is_admin": 1, "role": 1})
        is_admin = bool((user or {}).get("is_admin")) or str((user or {}).get("role", "")).lower() in {"admin", "owner", "super_admin", "superadmin"}
        if not bypass_cache:
            await _cache_set_bool(_ADMIN_TOKEN_CACHE_PREFIX, token, is_admin, ADMIN_TOKEN_CACHE_TTL_SECONDS)
        return is_admin
    except Exception:
        return False


async def _is_authenticated_e2e_user(request: Request) -> bool:
    token = _extract_session_token(request)
    if not token:
        return False

    cached = await _cache_get_bool(_E2E_TOKEN_CACHE_PREFIX, token)
    if cached is not None:
        return cached

    try:
        from routes.db import db

        session = await db.sessions.find_one({"session_token": token, "is_active": True}, {"_id": 0, "user_id": 1})
        if not session:
            await _cache_set_bool(_E2E_TOKEN_CACHE_PREFIX, token, False, 60)
            return False

        user = await db.users.find_one({"user_id": session.get("user_id")}, {"_id": 0, "email": 1})
        email = str((user or {}).get("email") or "").strip().lower()
        is_e2e = (
            email.startswith("e2e.")
            or email in E2E_TEST_EMAIL_ALLOWLIST
            or email.startswith("f22.")
            or email.startswith("p1.free.")
            or email.startswith("nova.v2.")
            or email.startswith("curation.")
        )
        await _cache_set_bool(_E2E_TOKEN_CACHE_PREFIX, token, is_e2e, 60)
        return is_e2e
    except Exception:
        return False


async def is_e2e_rate_limit_exempt_request(request: Request) -> bool:
    if not _is_non_production_runtime():
        return False

    if _has_valid_e2e_bypass_header(request):
        return True

    return await _is_authenticated_e2e_user(request)


class APIRateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces per-endpoint rate limits."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip non-API and health/config routes
        if not path.startswith("/api/") or path in ("/api/health", "/api/config/global"):
            return await call_next(request)

        # Skip WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        client_ip = _get_client_ip(request)
        limit, window = _get_limit(path)

        if await is_e2e_rate_limit_exempt_request(request):
            return await call_next(request)

        if path.startswith("/api/admin/"):
            if await _is_authenticated_admin(request):
                limit = max(limit, ADMIN_AUTH_LIMIT[0])
                window = max(window, ADMIN_AUTH_LIMIT[1])

        key = f"{client_ip}:{path}"

        allowed, remaining, retry_after = await _counter.allow(key, limit, window)

        if not allowed:
            logger.warning(f"Rate limit exceeded: {client_ip} -> {path} ({limit}/{window}s)")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later.", "retry_after": retry_after},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
