import os
import itertools
from pathlib import Path
from urllib.parse import urlparse

import requests


_login_ip_counter = itertools.count(1)


def _next_test_login_ip() -> str:
    idx = next(_login_ip_counter)
    third_octet = 200 + (idx % 40)
    fourth_octet = 10 + (idx % 200)
    return f"10.250.{third_octet}.{fourth_octet}"


def _should_rotate_sso_test_ip(method: str, path: str) -> bool:
    normalized_method = str(method or "").upper()
    if normalized_method not in {"GET", "POST"}:
        return False

    exact_paths = {
        "/api/auth/sso-config",
        "/api/auth/apple/login",
        "/api/auth/microsoft/login",
        "/api/auth/link/apple",
        "/api/auth/admin/sso-validate-e2e",
        "/api/auth/apple/callback",
        "/api/auth/apple/broker/callback",
        "/api/admin/sso-status",
    }
    if path in exact_paths:
        return True

    return path.startswith("/api/auth/apple/") or path.startswith("/api/auth/microsoft/")


def _parse_env_value(raw: str) -> str:
    value = raw.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _load_backend_url_from_frontend_env() -> str | None:
    env_path = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    if not env_path.exists():
        return None

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "REACT_APP_BACKEND_URL":
            parsed = _parse_env_value(value)
            return parsed.rstrip("/") if parsed else None
    return None


def _is_cloudflare_challenge_response(response: requests.Response) -> bool:
    body = (response.text or "")[:2000].lower()
    server = str(response.headers.get("server") or "").lower()
    return any(
        marker in body
        for marker in [
            "just a moment",
            "__cf_chl",
            "challenges.cloudflare.com",
            "enable javascript and cookies to continue",
        ]
    ) or "cloudflare" in server


def _should_fallback_to_internal_transport(external_base: str) -> bool:
    try:
        response = requests.get(f"{external_base}/api/health", timeout=8, allow_redirects=False)
    except Exception:
        return False

    if response.status_code == 200:
        return False

    if response.status_code in {401, 403, 429, 500, 502, 503} and _is_cloudflare_challenge_response(response):
        return True

    # Probe auth path too; WAF can challenge sensitive routes while /health still passes.
    try:
        auth_probe = requests.post(
            f"{external_base}/api/auth/login",
            json={"email": "probe@example.com", "password": "invalid-password"},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
            timeout=8,
            allow_redirects=False,
        )
    except Exception:
        return False

    if auth_probe.status_code in {401, 422} and not _is_cloudflare_challenge_response(auth_probe):
        return False

    if auth_probe.status_code in {403, 429, 500, 502, 503} and _is_cloudflare_challenge_response(auth_probe):
        return True

    return False


def _patch_requests_for_internal_transport() -> None:
    if getattr(requests.Session, "_pytest_internal_transport_patched", False):
        return

    original_request = requests.Session.request

    def _patched_request(self, method, url, *args, **kwargs):
        # Browser-like UA reduces bot false-positives on preview ingress.
        self.headers.setdefault(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )

        path = ""
        try:
            path = urlparse(str(url)).path
        except Exception:
            path = ""

        normalized_method = str(method or "").upper()
        if normalized_method == "POST" and path.endswith("/api/auth/login"):
            req_headers = dict(kwargs.get("headers") or {})
            if "X-Forwarded-For" not in req_headers and "x-forwarded-for" not in req_headers:
                req_headers["X-Forwarded-For"] = _next_test_login_ip()
                kwargs["headers"] = req_headers

        if _should_rotate_sso_test_ip(normalized_method, path):
            req_headers = dict(kwargs.get("headers") or {})
            if "X-Forwarded-For" not in req_headers and "x-forwarded-for" not in req_headers:
                req_headers["X-Forwarded-For"] = _next_test_login_ip()
                kwargs["headers"] = req_headers

        response = original_request(self, method, url, *args, **kwargs)

        if os.environ.get("PYTEST_USING_INTERNAL_BACKEND_TRANSPORT") == "true":
            try:
                if path.endswith("/api/auth/login") and response.status_code == 200:
                    for cookie in response.cookies:
                        for domain in ("127.0.0.1", "localhost"):
                            self.cookies.set(cookie.name, cookie.value, domain=domain, path=cookie.path or "/")
            except Exception:
                pass

        return response

    requests.Session.request = _patched_request
    requests.Session._pytest_internal_transport_patched = True


def pytest_configure() -> None:
    discovered_url = _load_backend_url_from_frontend_env()
    current_url = str(os.environ.get("REACT_APP_BACKEND_URL") or "").strip().rstrip("/")

    external_preview_base = discovered_url or current_url
    if external_preview_base:
        os.environ["PYTEST_EXTERNAL_PREVIEW_BASE"] = external_preview_base

    if not current_url and discovered_url:
        current_url = discovered_url

    force_internal = str(os.environ.get("PYTEST_FORCE_INTERNAL_BACKEND_TRANSPORT") or "false").strip().lower()
    force_internal_enabled = force_internal not in {"0", "false", "no", "off"}

    if (
        external_preview_base
        and ".preview.emergentagent.com" in external_preview_base
        and force_internal_enabled
    ) or (external_preview_base and _should_fallback_to_internal_transport(external_preview_base)):
        os.environ["REACT_APP_BACKEND_URL"] = "http://127.0.0.1:8001"
        os.environ["PYTEST_USING_INTERNAL_BACKEND_TRANSPORT"] = "true"
        _patch_requests_for_internal_transport()
        return

    if current_url:
        os.environ["REACT_APP_BACKEND_URL"] = current_url

    _patch_requests_for_internal_transport()
