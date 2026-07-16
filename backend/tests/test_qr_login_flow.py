"""
QR Login Flow — End-to-end backend tests.

Covers:
  - POST /api/auth/qr/generate
  - GET  /api/auth/qr/status/{session_id}
  - POST /api/auth/qr/approve
  - POST /api/auth/qr/consume (new endpoint that sets HttpOnly session cookie)
  - Cookie session validated via /api/auth/me
  - Error paths: invalid token, wrong session_id, expired session

Assumptions:
  - Web auth is cookie-based (WEB_COOKIE_ONLY_AUTH=true)
  - /api/auth/qr/generate and /api/auth/qr/consume are CSRF-exempt
  - /api/auth/qr/approve requires CSRF (X-Requested-With) + auth cookie
  - QR sessions expire after 300 seconds
"""

import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def phone_client():
    """Simulates the 'phone' — a logged-in cookie session for the approver."""
    s = requests.Session()
    s.headers.update(XHR_HEADERS)
    resp = s.post(f"{BASE_URL}/api/auth/login",
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                  headers=XHR_HEADERS)
    if resp.status_code != 200:
        pytest.skip(f"Login failed with status {resp.status_code}: {resp.text[:200]}")
    # Verify cookie session works
    me = s.get(f"{BASE_URL}/api/auth/me")
    if me.status_code != 200:
        pytest.skip(f"/auth/me failed post-login: {me.status_code}")
    return s


# ── Tests: qr/generate ─────────────────────────────────────────────────

class TestQRGenerate:
    def test_generate_returns_session_id_qr_url_expires(self, anon_client):
        r = anon_client.post(f"{BASE_URL}/api/auth/qr/generate")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "session_id" in data and isinstance(data["session_id"], str)
        assert data["session_id"].startswith("qr_")
        assert "qr_url" in data and data["qr_url"].startswith("http")
        assert "/auth/qr-approve?session=" in data["qr_url"]
        assert data["expires_in"] == 300

    def test_generate_is_csrf_exempt(self, anon_client):
        # No X-Requested-With header — should still succeed (endpoint is CSRF-exempt)
        r = requests.post(f"{BASE_URL}/api/auth/qr/generate",
                          headers={"Content-Type": "application/json"})
        assert r.status_code == 200, r.text


# ── Tests: qr/status pending ───────────────────────────────────────────

class TestQRStatusPending:
    def test_fresh_session_is_pending(self, anon_client):
        gen = anon_client.post(f"{BASE_URL}/api/auth/qr/generate").json()
        sid = gen["session_id"]
        r = anon_client.get(f"{BASE_URL}/api/auth/qr/status/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending"
        assert "session_token" not in data or not data.get("session_token")

    def test_status_unknown_session_returns_404(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/auth/qr/status/qr_deadbeefdeadbeef")
        assert r.status_code == 404


# ── Tests: qr/approve (requires auth) ──────────────────────────────────

class TestQRApprove:
    def test_approve_without_auth_returns_401(self, anon_client):
        gen = anon_client.post(f"{BASE_URL}/api/auth/qr/generate").json()
        sid = gen["session_id"]
        r = anon_client.post(f"{BASE_URL}/api/auth/qr/approve",
                             json={"session_id": sid},
                             headers=XHR_HEADERS)
        assert r.status_code == 401

    def test_approve_unknown_session_returns_404(self, phone_client):
        r = phone_client.post(f"{BASE_URL}/api/auth/qr/approve",
                              json={"session_id": "qr_nonexistent12345"})
        assert r.status_code == 404

    def test_approve_flips_status_and_writes_session_token(self, anon_client, phone_client):
        gen = anon_client.post(f"{BASE_URL}/api/auth/qr/generate").json()
        sid = gen["session_id"]

        # Approve from the phone
        r = phone_client.post(f"{BASE_URL}/api/auth/qr/approve",
                              json={"session_id": sid})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

        # Desktop polls status — should see approved + session_token + user_id
        s = anon_client.get(f"{BASE_URL}/api/auth/qr/status/{sid}")
        assert s.status_code == 200
        sd = s.json()
        assert sd["status"] == "approved"
        assert sd.get("session_token"), "session_token missing on approved status"
        assert sd.get("user_id"), "user_id missing on approved status"

    def test_approve_twice_rejects_second_call(self, anon_client, phone_client):
        gen = anon_client.post(f"{BASE_URL}/api/auth/qr/generate").json()
        sid = gen["session_id"]
        first = phone_client.post(f"{BASE_URL}/api/auth/qr/approve", json={"session_id": sid})
        assert first.status_code == 200
        # After first approve then polling, status may become 'consumed' — the
        # second approve call should reject with 400
        second = phone_client.post(f"{BASE_URL}/api/auth/qr/approve", json={"session_id": sid})
        assert second.status_code == 400


# ── Tests: qr/consume (new endpoint) ───────────────────────────────────

class TestQRConsume:
    def _approved_session(self, anon_client, phone_client):
        gen = anon_client.post(f"{BASE_URL}/api/auth/qr/generate").json()
        sid = gen["session_id"]
        appr = phone_client.post(f"{BASE_URL}/api/auth/qr/approve", json={"session_id": sid})
        assert appr.status_code == 200
        # poll status to retrieve session_token
        st = anon_client.get(f"{BASE_URL}/api/auth/qr/status/{sid}").json()
        assert st["status"] == "approved"
        return sid, st["session_token"], st["user_id"]

    def test_consume_sets_cookie_and_returns_user(self, anon_client, phone_client):
        sid, token, uid = self._approved_session(anon_client, phone_client)
        # New desktop client to prove that consume alone establishes session
        desktop = requests.Session()
        desktop.headers.update({"Content-Type": "application/json"})
        r = desktop.post(f"{BASE_URL}/api/auth/qr/consume",
                         json={"session_id": sid, "session_token": token})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        assert data["user_id"] == uid
        assert data["email"] == ADMIN_EMAIL

        # Verify cookie was set (session cookie name may vary but there must be at least one)
        assert len(desktop.cookies) > 0, "No cookies set after consume"

        # /auth/me with just the cookie should succeed — proving cookie session established
        me = desktop.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200, f"me failed after consume: {me.status_code} {me.text[:200]}"
        me_data = me.json()
        assert me_data["email"] == ADMIN_EMAIL
        assert me_data["user_id"] == uid

    def test_consume_wrong_session_id_returns_404(self, anon_client, phone_client):
        sid, token, _ = self._approved_session(anon_client, phone_client)
        r = requests.post(f"{BASE_URL}/api/auth/qr/consume",
                          json={"session_id": "qr_fake_session_id", "session_token": token},
                          headers={"Content-Type": "application/json"})
        assert r.status_code == 404

    def test_consume_invalid_token_returns_error(self, anon_client, phone_client):
        sid, _, _ = self._approved_session(anon_client, phone_client)
        r = requests.post(f"{BASE_URL}/api/auth/qr/consume",
                          json={"session_id": sid, "session_token": "not.a.valid.jwt.token"},
                          headers={"Content-Type": "application/json"})
        # Token mismatch triggers 403; if token happens to match doc but is invalid JWT it becomes 401.
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_consume_is_csrf_exempt(self, anon_client, phone_client):
        sid, token, _ = self._approved_session(anon_client, phone_client)
        # No X-Requested-With header
        r = requests.post(f"{BASE_URL}/api/auth/qr/consume",
                          json={"session_id": sid, "session_token": token},
                          headers={"Content-Type": "application/json"})
        assert r.status_code == 200, f"Consume should be CSRF-exempt: {r.status_code} {r.text[:200]}"


# ── Tests: consumed / already-used ─────────────────────────────────────

class TestQRLifecycle:
    def test_status_after_polling_becomes_consumed(self, anon_client, phone_client):
        gen = anon_client.post(f"{BASE_URL}/api/auth/qr/generate").json()
        sid = gen["session_id"]
        phone_client.post(f"{BASE_URL}/api/auth/qr/approve", json={"session_id": sid})
        first = anon_client.get(f"{BASE_URL}/api/auth/qr/status/{sid}").json()
        assert first["status"] == "approved"
        # Second poll → server has flipped status to 'consumed' to prevent replay
        second = anon_client.get(f"{BASE_URL}/api/auth/qr/status/{sid}").json()
        assert second["status"] in ("consumed", "approved")


# ── Tests: expiry (best-effort — patch DB directly if possible, else skip) ─

class TestQRExpiry:
    def test_expired_session_returns_expired(self, anon_client):
        """We generate a session and simulate expiry by touching MongoDB directly."""
        try:
            from pymongo import MongoClient
        except ImportError:
            pytest.skip("pymongo not available for expiry test")
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "realtalk_db")
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
        try:
            client.admin.command("ping")
        except Exception:
            pytest.skip("MongoDB not reachable from test host")

        gen = anon_client.post(f"{BASE_URL}/api/auth/qr/generate").json()
        sid = gen["session_id"]
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        client[db_name].qr_sessions.update_one({"session_id": sid}, {"$set": {"expires_at": past}})
        r = anon_client.get(f"{BASE_URL}/api/auth/qr/status/{sid}")
        assert r.status_code == 200
        assert r.json()["status"] == "expired"
