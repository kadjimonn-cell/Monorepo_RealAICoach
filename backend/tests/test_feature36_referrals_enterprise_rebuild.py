"""
Feature 36 Referrals Enterprise Rebuild Tests
Validates P0/P1/P3 hardening contracts for production reliability.
"""

import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
BASIC_EMAIL = "f22.basic.20260613@example.com"
BASIC_PASSWORD = "F22Basic#2026Aa"


def _session(email: str, password: str) -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    res = sess.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert res.status_code == 200, f"login failed: {res.status_code} {res.text}"
    return sess


def test_referral_admin_fraud_alerts_is_read_only_and_has_scan_metadata():
    admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
    res = admin.get(f"{BASE_URL}/api/referrals/admin/fraud-alerts?page=1&page_size=5", timeout=30)
    assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
    data = res.json()
    assert "last_scan" in data
    assert "last_scan_type" in data
    assert "last_scan_new_alerts" in data
    assert data.get("new_alerts_found") == 0


def test_referral_ops_health_endpoint_available_for_admin():
    admin = _session(ADMIN_EMAIL, ADMIN_PASSWORD)
    res = admin.get(f"{BASE_URL}/api/referrals/admin/ops-health", timeout=30)
    assert res.status_code == 200, f"Expected 200 got {res.status_code}: {res.text}"
    data = res.json()
    assert "flags" in data
    assert "idempotency" in data
    assert "fraud" in data
    assert "funnel" in data


def test_auto_apply_renewal_is_idempotent_with_header_key():
    basic = _session(BASIC_EMAIL, BASIC_PASSWORD)
    idem_key = "feature36-renewal-idem"
    headers = {"X-Idempotency-Key": idem_key, "X-Requested-With": "XMLHttpRequest"}
    res1 = basic.post(f"{BASE_URL}/api/referrals/auto-apply-renewal", headers=headers, timeout=30)
    assert res1.status_code in (200, 400), f"Unexpected: {res1.status_code} {res1.text}"

    res2 = basic.post(f"{BASE_URL}/api/referrals/auto-apply-renewal", headers=headers, timeout=30)
    assert res2.status_code == 200, f"Expected idempotent replay 200, got {res2.status_code}: {res2.text}"
    data2 = res2.json()
    assert data2.get("idempotent_replay") is True or data2.get("already_processed") is True
