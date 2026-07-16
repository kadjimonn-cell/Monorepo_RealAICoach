"""Parity checks for canonical public API contract wiring."""

from __future__ import annotations

from pathlib import Path
import os
import sys

import pytest
import requests

if "/app/backend" not in sys.path:
    sys.path.insert(0, "/app/backend")

from utils.public_api_contract import (
    PUBLIC_API_EXACT,
    PUBLIC_API_PREFIXES,
    build_public_regex_patterns,
)
from utils.access_control_engine import PUBLIC_PATTERNS


def test_subscriptions_plans_is_marked_public_in_contract():
    assert "/api/subscriptions/plans" in PUBLIC_API_EXACT or any(
        "/api/subscriptions/plans".startswith(prefix) for prefix in PUBLIC_API_PREFIXES
    )


def test_access_control_public_patterns_use_contract_source():
    expected = build_public_regex_patterns()
    assert PUBLIC_PATTERNS == expected


def test_middleware_uses_contract_source_symbols():
    text = Path("/app/backend/middleware.py").read_text(encoding="utf-8", errors="ignore")
    assert "AUTH_PUBLIC_PREFIXES = tuple(PUBLIC_API_PREFIXES)" in text
    assert "AUTH_PUBLIC_EXACT = set(PUBLIC_API_EXACT)" in text


def test_public_subscriptions_endpoint_is_public_runtime():
    base_url = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    if not base_url:
        pytest.skip("REACT_APP_BACKEND_URL not set")

    response = requests.get(f"{base_url}/api/subscriptions/plans", timeout=30)
    assert response.status_code == 200
