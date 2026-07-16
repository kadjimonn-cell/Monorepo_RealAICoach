"""Regression tests for strict subscription endpoint scope separation.

Policy:
- User/public paths must consume /api/subscriptions/plans.
- /api/admin/subscriptions/plans remains admin-console scope only.
"""

from __future__ import annotations

from pathlib import Path
import os
import re

import pytest
import requests


ROOT = Path("/app")
FRONTEND_ROOT = ROOT / "frontend"


def _iter_frontend_source_files():
    for path in FRONTEND_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"node_modules", ".git", "dist", ".expo"} for part in path.parts):
            continue
        if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        yield path


def test_no_user_path_calls_admin_subscription_plans_endpoint():
    """No frontend API call should target /api/admin/subscriptions/plans."""
    call_pattern = re.compile(
        r"(?:api\.(?:get|post|put|patch|delete)|useLiveQuery)\s*\(\s*[`\"'](?:/api)?/admin/subscriptions/plans",
        re.IGNORECASE,
    )

    offenders: list[str] = []
    for path in _iter_frontend_source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if call_pattern.search(text):
            offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, (
        "User-path dependency on admin plans endpoint detected. "
        f"Offending files: {offenders}"
    )


def test_admin_endpoint_explicitly_marked_admin_only_headers_present():
    """Admin endpoint must advertise admin-only scope in code."""
    file_path = ROOT / "backend" / "routes" / "admin_console.py"
    text = file_path.read_text(encoding="utf-8", errors="ignore")

    assert 'X-Endpoint-Scope"] = "admin-only"' in text
    assert 'X-Replacement-Endpoint"] = "/api/subscriptions/plans"' in text
    assert 'X-User-Path-Policy"] = "forbidden"' in text


def test_public_subscription_plans_endpoint_advertises_public_scope_header():
    """User-path endpoint should be publicly consumable and explicitly labeled."""
    base_url = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    if not base_url:
        pytest.skip("REACT_APP_BACKEND_URL not set")

    response = requests.get(f"{base_url}/api/subscriptions/plans", timeout=30)
    assert response.status_code == 200
    assert response.headers.get("X-Endpoint-Scope") == "public-user"
