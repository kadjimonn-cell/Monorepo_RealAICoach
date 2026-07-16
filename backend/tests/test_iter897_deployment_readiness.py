"""Iteration 897 - Deployment / Production readiness verification.

Verifies:
1. GET /api/health returns 200 and backend has no lingering index creation errors.
2. Admin login succeeds and is_admin=true.
3. Free user login (regression).
4. Rate limiting on repeated wrong-password logins (throwaway email) eventually returns 429.
5. MongoDB TTL indexes: integration_webhook_replay_guard.expires_at_1 (TTL=0) and
   service_heartbeats.checked_at_1 (TTL=259200) exist.
"""
import os
import time
import asyncio
import pytest
import requests
from pathlib import Path

# Load backend .env (BASE_URL fallback via frontend/.env preserved)
def _load_env_file(p):
    if not Path(p).exists():
        return {}
    out = {}
    for line in Path(p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out

_FRONT_ENV = _load_env_file('/app/frontend/.env')
_BACK_ENV = _load_env_file('/app/backend/.env')

BASE_URL = (os.environ.get('REACT_APP_BACKEND_URL') or _FRONT_ENV.get('REACT_APP_BACKEND_URL')).rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL') or _BACK_ENV.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME') or _BACK_ENV.get('DB_NAME')

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"


# ---------- Section 1: health ----------
def test_health_ok():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "healthy"
    assert "service" in body


# ---------- Section 2: admin login ----------
def test_admin_login_success():
    payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    r = requests.post(f"{BASE_URL}/api/auth/login", json=payload, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    # token may live in different keys - handle both flat and nested user shape
    user = data.get("user") or data
    is_admin = user.get("is_admin") if isinstance(user, dict) else None
    if is_admin is None and isinstance(data, dict):
        is_admin = data.get("is_admin")
    assert is_admin is True, f"admin login OK but is_admin not true: {data}"


# ---------- Section 3: free user login ----------
def test_free_user_login_success():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_EMAIL, "password": FREE_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"free login failed: {r.status_code} {r.text[:400]}"


# ---------- Section 4: rate limit via throwaway wrong-password email ----------
def test_rate_limit_wrong_password_returns_429():
    # Use throwaway/non-existent email to avoid locking real accounts
    throwaway = f"iter897rl{int(time.time())}@example.com"
    saw_429 = False
    statuses = []
    # 40 rapid attempts should hit sliding-window redis limiter (login limits are strict)
    for i in range(40):
        try:
            r = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": throwaway, "password": "wrong-pw-iter897"},
                timeout=10,
            )
        except requests.RequestException:
            continue
        statuses.append(r.status_code)
        if r.status_code == 429:
            saw_429 = True
            break
    assert saw_429, f"Did not observe 429 across 40 attempts. Statuses: {statuses[:20]}..."


# ---------- Section 5: TTL indexes ----------
@pytest.mark.asyncio
async def test_ttl_indexes_present():
    from motor.motor_asyncio import AsyncIOMotorClient  # local import to avoid module-load fail
    assert MONGO_URL and DB_NAME, "MONGO_URL / DB_NAME must be loaded"
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        db = client[DB_NAME]

        # integration_webhook_replay_guard.expires_at_1 TTL=0
        idxs_replay = await db.integration_webhook_replay_guard.index_information()
        assert "expires_at_1" in idxs_replay, f"expires_at_1 missing on integration_webhook_replay_guard: {list(idxs_replay.keys())}"
        assert idxs_replay["expires_at_1"].get("expireAfterSeconds") == 0, idxs_replay["expires_at_1"]

        # service_heartbeats.checked_at_1 TTL=259200
        idxs_hb = await db.service_heartbeats.index_information()
        assert "checked_at_1" in idxs_hb, f"checked_at_1 missing on service_heartbeats: {list(idxs_hb.keys())}"
        assert idxs_hb["checked_at_1"].get("expireAfterSeconds") == 259200, idxs_hb["checked_at_1"]
    finally:
        client.close()
