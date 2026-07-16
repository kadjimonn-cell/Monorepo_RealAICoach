"""Multi-platform client bootstrap handshake.

Single public endpoint future Android/iOS/web clients call on launch to
discover the API version, auth capabilities, feature/config endpoints and
platform support policy. No PII, no secrets.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from services.client_version_policy import get_client_version_policy

router = APIRouter(prefix="/client", tags=["Client Bootstrap"])

NATIVE_PLATFORM_VALUES = ("mobile", "native", "android", "ios", "expo")


def _platform_entry(policy: dict, key: str, status: str) -> dict:
    entry = policy.get(key) or {}
    return {
        "min_supported_version": entry.get("min_supported_version", "1.0.0"),
        "latest_version": entry.get("latest_version", "1.0.0"),
        "update_url": entry.get("update_url", ""),
        "enforced": bool(entry.get("enforced", True)),
        "status": status,
    }


@router.get("/bootstrap")
async def client_bootstrap(request: Request):
    client_platform = str(request.headers.get("X-Client-Platform") or "web").strip().lower()
    policy = await get_client_version_policy()
    return {
        "api_version": "v1",
        "service": "RealAICoach API",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "client_platform": client_platform if client_platform in NATIVE_PLATFORM_VALUES else "web",
        "base_paths": {"versioned": "/api/v1", "legacy": "/api"},
        "platforms": {
            "web": {"min_supported_version": "1.0.0", "status": "active"},
            "android": _platform_entry(policy, "android", "planned"),
            "ios": _platform_entry(policy, "ios", "planned"),
            "expo": _platform_entry(policy, "expo", "planned"),
        },
        "version_enforcement": {
            "platform_header": "X-Client-Platform",
            "version_header": "X-App-Version",
            "blocked_status": 426,
            "blocked_code": "CLIENT_UPDATE_REQUIRED",
            "exempt_paths": ["/api/health", "/api/client/bootstrap"],
        },
        "auth": {
            "channels": ["cookie", "bearer"],
            "native_token_header": "X-Client-Platform",
            "native_token_values": list(NATIVE_PLATFORM_VALUES),
            "csrf_header": "X-Requested-With",
            "login_endpoint": "/api/v1/auth/login",
            "register_endpoint": "/api/v1/auth/register",
            "refresh_endpoint": "/api/v1/auth/token/refresh",
            "session_endpoint": "/api/v1/auth/me",
            "refresh_tokens_supported": True,
            "mfa_supported": True,
            "oauth_providers": ["google", "microsoft", "apple"],
            "passkeys_supported": True,
        },
        "capabilities": {
            "features_registry": "/api/v1/features/registry",
            "global_config": "/api/v1/config/global",
            "platform_state": "/api/v1/gps/state",
            "subscriptions_plans": "/api/v1/payments/subscriptions/plans",
            "subscriptions_status": "/api/v1/payments/subscriptions/status",
            "notifications": "/api/v1/notifications",
            "health": "/api/v1/health",
        },
        "i18n": {
            "auto_translate": True,
            "languages_endpoint": "/api/v1/i18n/languages",
            "locales_endpoint": "/api/v1/i18n/locales",
        },
        "theming": {
            "app_theme_contract": "v2-light-dark",
            "email_theme_contract": "v7-light-dark",
        },
        "compression": "gzip",
        "rate_limiting": True,
        "docs": {
            "openapi_url": "/api/v1/openapi.json",
            "swagger_url": "/api/v1/docs",
            "access": "admin",
        },
        "environment": str(os.environ.get("APP_ENV") or "preview"),
    }
