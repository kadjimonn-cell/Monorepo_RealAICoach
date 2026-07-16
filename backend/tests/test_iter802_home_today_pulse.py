"""Iteration 802 regression: /api/home/today-pulse.

Contract:
  * Cookie-session authenticated GET returns 200 with keys:
    streak_days (>=1), sessions_today (>=0), total_sessions (>=0),
    badges_earned (int), badges_total (==8), checklist_percent (0..100), timestamp.
  * Calling twice within the same UTC day does NOT increment streak_days.
  * Unauthenticated GET returns 401.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required")

EMAIL = "p1.free.1779113329@example.com"
PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def authed_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"auth/login failed with {r.status_code}: {r.text[:200]}")
    token = None
    try:
        data = r.json()
        token = (
            data.get("access_token")
            or data.get("token")
            or (data.get("data") or {}).get("access_token")
        )
    except Exception:
        pass
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


class TestTodayPulseAuth:
    def test_today_pulse_unauthenticated_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/home/today-pulse", timeout=30)
        assert r.status_code == 401, f"expected 401, got {r.status_code} body={r.text[:200]}"

    def test_today_pulse_authenticated_returns_200_with_all_fields(self, authed_session):
        r = authed_session.get(f"{BASE_URL}/api/home/today-pulse", timeout=30)
        assert r.status_code == 200, f"unexpected status={r.status_code} body={r.text[:300]}"
        data = r.json()
        required = {"streak_days", "sessions_today", "total_sessions",
                    "badges_earned", "badges_total", "checklist_percent", "timestamp"}
        missing = required - set(data.keys())
        assert not missing, f"missing keys {missing}: {data}"
        assert data["badges_total"] == 8, f"badges_total must be 8, got {data['badges_total']}"
        assert isinstance(data["streak_days"], int) and data["streak_days"] >= 1, (
            f"streak_days must be int >=1 after login, got {data['streak_days']}"
        )
        assert isinstance(data["sessions_today"], int) and data["sessions_today"] >= 0
        assert isinstance(data["total_sessions"], int) and data["total_sessions"] >= 0
        assert isinstance(data["badges_earned"], int) and 0 <= data["badges_earned"] <= 6
        assert isinstance(data["checklist_percent"], int) and 0 <= data["checklist_percent"] <= 100

    def test_today_pulse_streak_stable_within_same_day(self, authed_session):
        """Calling twice the same UTC day must NOT increment streak_days."""
        r1 = authed_session.get(f"{BASE_URL}/api/home/today-pulse", timeout=30)
        assert r1.status_code == 200
        streak1 = r1.json()["streak_days"]
        r2 = authed_session.get(f"{BASE_URL}/api/home/today-pulse", timeout=30)
        assert r2.status_code == 200
        streak2 = r2.json()["streak_days"]
        assert streak1 == streak2, (
            f"streak changed within same UTC day: {streak1} -> {streak2}"
        )
