"""Iteration 796 - Verify FIX 3 backend: GET /api/gps/state seeds quick_questions defaults."""
import os
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://coach-web-preview.preview.emergentagent.com').rstrip('/')

EXPECTED_DEFAULTS = [
    "What can you help me with?",
    "How does AI coaching work?",
    "How do I upgrade or manage my plan?",
]


def _login_free_user():
    s = requests.Session()
    resp = s.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": "p1.free.1779113329@example.com",
            "password": "P1Free#2026!Aa",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    return s, resp


def test_login_free_user_ok():
    _, resp = _login_free_user()
    assert resp.status_code == 200, f"login failed: {resp.status_code} {resp.text[:400]}"


def test_gps_state_quick_questions_populated_authenticated():
    """FIX 3: /api/gps/state returns messaging.quick_questions with 3 default seeded entries."""
    s, login = _login_free_user()
    assert login.status_code == 200, f"login failed: {login.status_code}"

    r = s.get(f"{BASE_URL}/api/gps/state", timeout=30)
    assert r.status_code == 200, f"gps/state failed: {r.status_code} {r.text[:400]}"
    body = r.json()
    messaging = body.get("messaging") or {}
    qq = messaging.get("quick_questions")
    assert isinstance(qq, list) and len(qq) >= 1, f"quick_questions empty or invalid: {qq!r}"
    # If self-repair seeded defaults, verify exact defaults
    print(f"quick_questions received (n={len(qq)}): {qq}")
    # Should contain all 3 defaults when self-repaired (empty case)
    for expected in EXPECTED_DEFAULTS:
        assert expected in qq, f"missing expected default: {expected!r} in {qq!r}"


def test_gps_state_quick_questions_unauthenticated():
    """Public GET /api/gps/state should also return seeded quick_questions if endpoint is public."""
    r = requests.get(f"{BASE_URL}/api/gps/state", timeout=30)
    if r.status_code != 200:
        # not public → skip
        print(f"unauth /api/gps/state returned {r.status_code}, skipping public check")
        return
    body = r.json()
    messaging = body.get("messaging") or {}
    qq = messaging.get("quick_questions")
    assert isinstance(qq, list) and len(qq) >= 1, f"unauth quick_questions empty: {qq!r}"
    for expected in EXPECTED_DEFAULTS:
        assert expected in qq, f"missing expected default (unauth): {expected!r}"
