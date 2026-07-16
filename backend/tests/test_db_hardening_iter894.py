"""Verification tests for iteration 894: db-hardening fix + regression checks.

Covers:
- Health endpoint
- Direct invocation of ensure_db_security_hardening (idempotency, no immutable _id)
- Backend log inspection post-restart
- platform_security_state doc shape
- Admin + Free user login regression (cookie session + /auth/me)
- Rate limiting on /api/auth/register (10/60s)
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load backend env explicitly (MONGO_URL, DB_NAME)
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend .env
    load_dotenv("/app/frontend/.env")
    BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PW = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PW = "P1Free#2026!Aa"


# ---------- health ----------
def test_health_endpoint():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") in ("healthy", "ok"), data


# ---------- db-hardening direct invocation ----------
@pytest.mark.asyncio
async def test_db_hardening_idempotent_no_immutable_id():
    # Import inside test so env is loaded first
    import sys
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient
    from utils.db_security_hardening import ensure_db_security_hardening

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        first = await ensure_db_security_hardening(db)
        second = await ensure_db_security_hardening(db)
    finally:
        client.close()

    for run_name, res in (("first", first), ("second", second)):
        assert res["status"] == "healthy", f"{run_name}: {res}"
        assert res["failed_indexes"] == [], f"{run_name}: {res['failed_indexes']}"
        assert "_id" not in res, f"{run_name}: leaked _id in response"
        assert res["posture"]["field_encryption_key_present"] is True
        assert res["posture"]["field_lookup_hmac_key_present"] is True
        assert res["posture"]["jwt_secret_present"] is True


# ---------- platform_security_state doc ----------
@pytest.mark.asyncio
async def test_platform_security_state_upsert():
    import sys
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        doc = await db.platform_security_state.find_one({"_id": "db_hardening"})
    finally:
        client.close()

    assert doc is not None, "platform_security_state doc missing"
    assert doc["_id"] == "db_hardening"
    assert "status" in doc
    assert "updated_at" in doc
    assert doc["status"] == "healthy", doc


# ---------- backend log inspection after restart ----------
def test_backend_log_no_hardening_errors_after_restart():
    log_path = Path("/var/log/supervisor/backend.err.log")
    assert log_path.exists(), "backend.err.log missing"
    text = log_path.read_text(errors="replace")

    # Look at only the last 500 lines (post-restart tail)
    tail_lines = text.splitlines()[-500:]
    tail = "\n".join(tail_lines)

    bad_scheduled = re.findall(r"\[db-hardening\] scheduled pass failed", tail)
    bad_index = re.findall(r"db-hardening index create failed", tail)
    immutable = re.findall(r"immutable field _id", tail)
    assert not bad_scheduled, f"scheduled pass failures found: {len(bad_scheduled)}"
    assert not bad_index, f"index create failed warnings found: {len(bad_index)}"
    assert not immutable, f"immutable _id errors found: {len(immutable)}"


# ---------- admin + free login regression ----------
def _login_and_me(email, password):
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:400]}"
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert me.status_code == 200, f"/auth/me failed {me.status_code} {me.text[:400]}"
    data = me.json()
    assert (data.get("email") or "").lower() == email.lower(), data
    return data


def test_admin_login_and_me():
    data = _login_and_me(ADMIN_EMAIL, ADMIN_PW)
    # Admin should have some admin marker
    role = str(data.get("role") or data.get("plan") or "").lower()
    assert "admin" in role or data.get("is_admin") or data.get("admin"), f"admin marker missing: {data}"


def test_free_user_login_and_me():
    data = _login_and_me(FREE_EMAIL, FREE_PW)
    plan = str(data.get("plan") or data.get("role") or "").lower()
    # Free user should be free plan (not necessarily strict)
    assert plan, f"plan missing: {data}"


# ---------- rate limiting on /api/auth/register ----------
def test_register_rate_limit_429():
    # Use unique disposable emails to avoid conflict; 10/60s expected
    got_429 = False
    last_status = None
    for i in range(14):
        payload = {
            "email": f"rl_test_{uuid.uuid4().hex[:10]}@example.com",
            "password": "TempPassword123!",
            "name": "RL Test",
        }
        r = requests.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=15)
        last_status = r.status_code
        if r.status_code == 429:
            got_429 = True
            break
        # small pause to avoid connection reset (still within 60s window)
        time.sleep(0.15)
    assert got_429, f"Did not receive 429 after 14 attempts, last_status={last_status}"
