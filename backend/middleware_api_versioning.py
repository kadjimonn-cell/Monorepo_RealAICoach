"""API v1 versioning shim + native client version enforcement.

1. Transparently maps `/api/v1/<path>` requests onto the existing `/api/<path>`
   handlers so mobile and future clients get a stable, versioned contract while
   all legacy unversioned web routes keep working unchanged.
2. Enforces the client version policy: native requests (X-Client-Platform)
   carrying an X-App-Version below the platform minimum receive
   426 Upgrade Required. Web requests are never affected; discovery endpoints
   (/api/health, /api/client/bootstrap) stay exempt so outdated clients can
   learn the required version.

Registered as the OUTERMOST middleware so every downstream security layer
(auth gate, CSRF, WAF, rate limits, IDOR) sees the canonical `/api/*` path.
"""

from __future__ import annotations

import json

V1_PREFIX = "/api/v1"
API_VERSION_HEADER = (b"x-api-version", b"1")
NATIVE_PLATFORM_VALUES = {"mobile", "native", "android", "ios", "expo"}
VERSION_EXEMPT_PATHS = ("/api/health", "/api/client/bootstrap")


def _scope_header(scope, name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key == name:
            return value.decode("latin-1").strip()
    return ""


class APIVersionRewriteMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        versioned = path == V1_PREFIX or path.startswith(V1_PREFIX + "/")
        if versioned:
            rest = path[len(V1_PREFIX):] or "/"
            path = "/api" + rest
            scope = dict(scope)
            scope["path"] = path
            scope["raw_path"] = path.encode("utf-8")

        if scope["type"] == "websocket":
            return await self.app(scope, receive, send)

        if path.startswith("/api/") and not path.startswith(VERSION_EXEMPT_PATHS):
            platform_hint = _scope_header(scope, b"x-client-platform").lower()
            app_version = _scope_header(scope, b"x-app-version")
            if platform_hint in NATIVE_PLATFORM_VALUES and app_version:
                try:
                    from services.client_version_policy import evaluate_version_block
                    block = await evaluate_version_block(platform_hint, app_version)
                except Exception:
                    block = None  # fail-open
                if block:
                    return await self._send_upgrade_required(send, block, versioned)

        if not versioned:
            return await self.app(scope, receive, send)

        async def send_with_version_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append(API_VERSION_HEADER)
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, receive, send_with_version_header)

    @staticmethod
    async def _send_upgrade_required(send, block: dict, versioned: bool):
        body = json.dumps(block).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("latin-1")),
        ]
        if versioned:
            headers.append(API_VERSION_HEADER)
        await send({"type": "http.response.start", "status": 426, "headers": headers})
        await send({"type": "http.response.body", "body": body})
