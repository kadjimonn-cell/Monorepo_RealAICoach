"""Feature 36 integrity alerts + trends + policy recommendation contracts."""

import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _admin_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"admin login failed: {login.status_code} {login.text}"
    return session


def test_integrity_alerts_list_contract():
    admin = _admin_session()
    res = admin.get(f"{BASE_URL}/api/referrals/admin/integrity-alerts?status=open&page=1&page_size=10", timeout=30)
    assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
    body = res.json()
    assert "alerts" in body
    assert "total_count" in body
    assert "page" in body


def test_integrity_trends_windows_contract():
    admin = _admin_session()
    res = admin.get(f"{BASE_URL}/api/referrals/admin/integrity-trends?days=90", timeout=30)
    assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
    body = res.json()
    assert "points" in body
    assert "windows" in body
    assert "7" in body["windows"]
    assert "30" in body["windows"]
    assert "90" in body["windows"]


def test_policy_recommendation_and_apply_contracts():
    admin = _admin_session()
    recommendation = admin.get(f"{BASE_URL}/api/referrals/admin/fraud-policy/recommendation", timeout=30)
    assert recommendation.status_code == 200, f"Expected 200 got {recommendation.status_code}: {recommendation.text}"
    rec_body = recommendation.json()
    assert "recommendation" in rec_body
    assert "recommended_profile" in rec_body["recommendation"]

    apply = admin.post(f"{BASE_URL}/api/referrals/admin/fraud-policy/apply-recommendation", json={}, timeout=30)
    assert apply.status_code == 200, f"Expected 200 got {apply.status_code}: {apply.text}"
    apply_body = apply.json()
    assert apply_body.get("success") is True
    assert apply_body.get("applied_profile") in {"balanced", "strict"}


def test_integrity_evaluate_contract():
    admin = _admin_session()
    res = admin.post(f"{BASE_URL}/api/referrals/admin/integrity-alerts/evaluate", json={}, timeout=30)
    assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
    body = res.json()
    assert body.get("success") is True
    assert "metrics" in body
    assert "recommendation" in body
