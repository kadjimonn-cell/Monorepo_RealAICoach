"""
Backend regression for GET /api/auth/me KYC fields.
Verifies that /api/auth/me returns kyc_verified and kyc_tier keys:
- Free (not verified) user: kyc_verified=False, kyc_tier=None
- Verified premium user: kyc_verified=True, kyc_tier='verified'
"""
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://coach-web-preview.preview.emergentagent.com",
).rstrip("/")

FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

VERIFIED_EMAIL = "watchvideos.premium.4dc6ab84@example.com"
VERIFIED_PASSWORD = "WatchVideos#2026Aa"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE_EMAIL, FREE_PASSWORD)


@pytest.fixture(scope="module")
def verified_session():
    return _login(VERIFIED_EMAIL, VERIFIED_PASSWORD)


class TestAuthMeKycFields:
    def test_me_unauthenticated_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code in (401, 403), f"Expected auth required, got {r.status_code}"

    def test_me_free_user_kyc_fields_present(self, free_session):
        r = free_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # Support both flat and nested user structures
        user = d.get("user", d)
        assert "kyc_verified" in user, f"kyc_verified missing in /api/auth/me response. keys={list(user.keys())}"
        assert "kyc_tier" in user, f"kyc_tier missing in /api/auth/me response. keys={list(user.keys())}"
        assert user["kyc_verified"] is False, f"free user kyc_verified should be False, got {user['kyc_verified']}"
        assert user["kyc_tier"] in (None, "", "none", "null"), f"free user kyc_tier should be null-ish, got {user['kyc_tier']!r}"

    def test_me_verified_premium_user_kyc_fields(self, verified_session):
        r = verified_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        user = d.get("user", d)
        assert "kyc_verified" in user and "kyc_tier" in user, (
            f"KYC fields missing on verified user. keys={list(user.keys())}"
        )
        assert user["kyc_verified"] is True, f"verified user kyc_verified should be True, got {user['kyc_verified']}"
        assert user["kyc_tier"] == "verified", f"verified user kyc_tier should be 'verified', got {user['kyc_tier']!r}"
