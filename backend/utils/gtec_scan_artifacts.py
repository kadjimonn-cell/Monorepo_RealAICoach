from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlsplit


def row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("url") or ""),
        str(row.get("viewport") or ""),
        str(row.get("final_url") or ""),
    )


def is_edge_challenge_row(row: dict[str, Any]) -> bool:
    if row.get("edge_challenge"):
        return True
    final = str(row.get("final_url") or "")
    if "__cf_chl_rt_tk" in final:
        return True
    blob = " ".join((row.get("console_errors") or []) + (row.get("page_errors") or [])).lower()
    return ("cloudflare" in blob) or ("just a moment" in blob)


def is_runtime_403_artifact(row: dict[str, Any]) -> bool:
    apis = row.get("failed_apis") or []
    if not apis:
        return False
    if (row.get("status_code") or 0) >= 400:
        return False
    if row.get("white_screen"):
        return False

    statuses = {int(a.get("status") or 0) for a in apis}
    urls = [str(a.get("url") or "") for a in apis]
    only_runtime = all("/api/config/v2-compliance/runtime" in u for u in urls)
    return statuses == {403} and only_runtime


def is_runtime_429_artifact(row: dict[str, Any]) -> bool:
    apis = row.get("failed_apis") or []
    if not apis:
        return False
    if (row.get("status_code") or 0) >= 400:
        return False
    if row.get("white_screen") or row.get("page_errors"):
        return False

    statuses = {int(a.get("status") or 0) for a in apis}
    urls = [str(a.get("url") or "").lower() for a in apis]
    if statuses != {429}:
        return False
    allowed = (
        "/api/config/v2-compliance/runtime",
        "/api/static/fonts/ionicons.ttf",
    )
    return all(any(token in u for token in allowed) for u in urls)


def is_public_api_auth_rate_limit_artifact(row: dict[str, Any]) -> bool:
    apis = row.get("failed_apis") or []
    if not apis:
        return False
    if (row.get("status_code") or 0) >= 400:
        return False
    if row.get("white_screen") or row.get("page_errors"):
        return False

    allowed_prefixes = (
        "/api/auth/me",
        "/api/geo/detect",
        "/api/config/v2-compliance/runtime",
        "/api/platform-control/public/state",
        "/api/features/registry",
        "/api/config/global",
        "/api/config/boot-policy",
        "/api/errors/client",
        "/api/static/fonts/ionicons.ttf",
        "/api/auth/session-bootstrap-telemetry",
        "/api/vitals/page-optimizations",
        "/api/payments/currencies",
        "/api/subscriptions/plans",
    )

    statuses: set[int] = set()
    for api in apis:
        status = int(api.get("status") or 0)
        statuses.add(status)
        if status not in {401, 429}:
            return False
        url = str(api.get("url") or "")
        try:
            parsed = urlsplit(url)
            path = str(parsed.path or "").lower()
        except Exception:
            path = str(url or "").lower()
        if not any(path.startswith(prefix) for prefix in allowed_prefixes):
            return False

    for err in (row.get("console_errors") or []):
        text = str(err or "").lower()
        if ("401" not in text) and ("429" not in text):
            return False
        if (
            "failed to load resource" not in text
            and "request failed with status" not in text
            and "failed to fetch" not in text
            and "failed to load remote config" not in text
        ):
            return False

    return bool(statuses)


def is_rate_limit_only_artifact(row: dict[str, Any]) -> bool:
    apis = row.get("failed_apis") or []
    if not apis:
        return False
    if (row.get("status_code") or 0) >= 400:
        return False
    if row.get("white_screen") or row.get("page_errors"):
        return False

    statuses = {int(a.get("status") or 0) for a in apis}
    if statuses != {429}:
        return False

    for err in (row.get("console_errors") or []):
        text = str(err or "").lower()
        allowed_noise = (
            "failed to load resource" in text
            or "request failed with status" in text
            or "failed to fetch" in text
            or "failed to load remote config" in text
            or ("refused to execute script" in text and "mime type ('text/html')" in text)
        )
        if not allowed_noise:
            return False
        if ("refused to execute script" not in text) and ("429" not in text):
            return False

    return True


def is_console_403_only_artifact(row: dict[str, Any]) -> bool:
    errors = row.get("console_errors") or []
    if not errors:
        return False
    if (row.get("status_code") or 0) >= 400:
        return False
    if row.get("white_screen") or row.get("page_errors") or row.get("failed_apis"):
        return False
    normalized = [str(e).lower() for e in errors]
    return all(("failed to load resource" in e and "403" in e) for e in normalized)


def is_console_429_only_artifact(row: dict[str, Any]) -> bool:
    errors = row.get("console_errors") or []
    if not errors:
        return False
    if (row.get("status_code") or 0) >= 400:
        return False
    if row.get("white_screen") or row.get("page_errors"):
        return False
    apis = row.get("failed_apis") or []
    if apis:
        statuses = {int(a.get("status") or 0) for a in apis}
        urls = [str(a.get("url") or "").lower() for a in apis]
        if statuses != {429}:
            return False
        allowed = (
            "/api/config/v2-compliance/runtime",
            "/api/static/fonts/ionicons.ttf",
        )
        if not all(any(token in u for token in allowed) for u in urls):
            return False
    normalized = [str(e).lower() for e in errors]
    return all(("failed to load resource" in e and "429" in e) for e in normalized)


def resolve_external_frontend_base_url(
    base_url: Optional[str],
    *,
    gtec_frontend_url: str,
    frontend_base_url: str,
    react_app_backend_url: str,
    frontend_env_url: str,
    backend_env_frontend: str,
    fallback_base_url: str,
) -> str:
    raw = str(base_url or "").strip()
    if raw:
        return raw.rstrip("/")

    direct = str(gtec_frontend_url or "").strip()
    if direct:
        return direct.rstrip("/")

    direct_frontend_base = str(frontend_base_url or "").strip()
    if direct_frontend_base:
        return direct_frontend_base.rstrip("/")

    backend_url = str(react_app_backend_url or "").strip().rstrip("/")
    if backend_url:
        if backend_url.endswith("/api"):
            return backend_url[:-4].rstrip("/")
        return backend_url

    if frontend_env_url:
        normalized = str(frontend_env_url).rstrip("/")
        if normalized.endswith("/api"):
            normalized = normalized[:-4].rstrip("/")
        if normalized:
            return normalized

    if backend_env_frontend:
        return str(backend_env_frontend).rstrip("/")

    return str(fallback_base_url or "").rstrip("/")
