"""Verification tests for iteration 865 fixes.

Tests cover:
- OTP bypass for allowlisted accounts (no requires_2fa)
- Seeded free tv.free.test account
- Free user access to ai-access status/tier-comparison
- Rate limit on certificate engagement endpoint
- Basic-required endpoints still enforce for free users
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")


def _login(email, password, native=False):
    headers = {"Content-Type": "application/json"}
    if native:
        headers["X-Client-Platform"] = "native"
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers=headers,
        timeout=30,
    )
    return r


# --- OTP bypass allowlist ---
class TestOtpBypassAllowlist:
    def test_feature21_test_login_no_2fa(self):
        r = _login("feature21.test.1781234530@example.com", "Feature21Test#2026Aa", native=True)
        assert r.status_code == 200, f"expected 200 got {r.status_code} body={r.text[:300]}"
        data = r.json()
        assert not data.get("requires_2fa"), f"unexpected 2fa challenge: {data}"

    def test_watchvideos_premium_login_no_2fa(self):
        r = _login("watchvideos.premium.4dc6ab84@example.com", "WatchVideos#2026Aa", native=True)
        assert r.status_code == 200, f"expected 200 got {r.status_code} body={r.text[:300]}"
        data = r.json()
        assert not data.get("requires_2fa"), f"unexpected 2fa challenge: {data}"

    def test_tv_free_seeded_login(self):
        r = _login("tv.free.test@realaicoach.app", "TvFree#2026!Aa", native=True)
        assert r.status_code == 200, f"expected 200 got {r.status_code} body={r.text[:300]}"


# --- Free user ai-access ---
class TestFreeUserAiAccess:
    @pytest.fixture(scope="class")
    def free_token(self):
        r = _login("p1.free.1779113329@example.com", "P1Free#2026!Aa", native=True)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        tok = d.get("session_token") or d.get("access_token") or d.get("token")
        assert tok, f"no token in {d.keys()}"
        return tok

    def test_ai_access_status_free_200(self, free_token):
        r = requests.get(
            f"{BASE_URL}/api/ai-access/status",
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=20,
        )
        assert r.status_code == 200, f"expected 200 got {r.status_code} body={r.text[:300]}"

    def test_ai_access_tier_comparison_free_200(self, free_token):
        r = requests.get(
            f"{BASE_URL}/api/ai-access/tier-comparison",
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=20,
        )
        assert r.status_code == 200, f"expected 200 got {r.status_code} body={r.text[:300]}"

    def test_ai_access_status_unauth_401(self):
        r = requests.get(f"{BASE_URL}/api/ai-access/status", timeout=20)
        assert r.status_code in (401, 403), f"unexpected {r.status_code}"

    def test_bill_generator_still_gated_for_free(self, free_token):
        r = requests.get(
            f"{BASE_URL}/api/bill-generator/bootstrap",
            headers={"Authorization": f"Bearer {free_token}"},
            timeout=20,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"


# --- Rate limit on certificate engagement (run last; consumes window) ---
class TestCertificateEngagementRateLimit:
    def test_rate_limit_burst_30_then_429(self):
        url = f"{BASE_URL}/api/ai-learn/certificates/verify/cert_b5e8b467bf1446/engagement"
        headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        body = {"event_type": "verifier_view", "source": "certificate:verifier"}
        results = []
        for i in range(35):
            r = requests.post(url, json=body, headers=headers, timeout=10)
            results.append(r.status_code)
        n_200 = sum(1 for s in results if s == 200)
        n_429 = sum(1 for s in results if s == 429)
        assert n_200 == 30, f"expected 30 successes, got {n_200}. results={results}"
        assert n_429 == 5, f"expected 5 rate-limited, got {n_429}. results={results}"
