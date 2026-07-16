"""Verify expanded free-limited route matrix premium surfaces.

Uses /api/access-control/check-route (server-side policy authority).
"""

import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

FREE = ("p1.free.1779113329@example.com", "P1Free#2026!Aa")
BASIC = ("f22.basic.20260613@example.com", "F22Basic#2026Aa")

PREMIUM_SURFACES = [
    "/features/content-studio",
    "/features/decision-coach",
    "/features/ai-automations",
    "/features/analytics-reports",
    "/features/ai-enterprise",
    "/mini-apps/ai-accounting",
    "/mini-apps/creator-exchange",
    "/subscription/mobile-money",
]


def _session(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    login = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert login.status_code == 200, f"login failed: {login.status_code} {login.text}"
    return s


def _check_route(s: requests.Session, path: str) -> dict:
    res = s.post(f"{BASE_URL}/api/access-control/check-route", json={"path": path}, timeout=30)
    assert res.status_code == 200, f"check-route failed {path}: {res.status_code} {res.text}"
    return res.json()


def test_free_user_blocked_from_expanded_premium_surfaces():
    s = _session(*FREE)
    for route in PREMIUM_SURFACES:
        result = _check_route(s, route)
        assert result.get("allowed") is False, f"free should be blocked: {route} -> {result}"
        assert result.get("reason") in {"subscription_required", "premium_required", "basic_required"}, (
            f"unexpected block reason for {route}: {result}"
        )


def test_basic_user_allowed_on_expanded_premium_surfaces():
    s = _session(*BASIC)
    for route in PREMIUM_SURFACES:
        result = _check_route(s, route)
        assert result.get("allowed") is True, f"basic should be allowed: {route} -> {result}"
