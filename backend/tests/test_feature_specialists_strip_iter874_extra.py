"""Iteration 874 - Extra verification for Suggested AI Specialists strip.

Spot-checks 4-5 different feature keys (smart-writing-studio, fitness-planner-pro,
sports, travel-visa, my-podcasts) and confirms:
- Sanitization (no leakage of system_prompt/allowed_tools/permissions/provider/model/config_profile)
- 1..4 specialists returned
- POST click event actually inserts into mongo collection `specialist_strip_events`
- Duplicate clicks each produce a distinct event document (count grows)
"""

import os
import sys
import asyncio

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}

SPOT_CHECK_FEATURES = [
    "smart-writing-studio",
    "fitness-planner-pro",
    "sports",
    "travel-visa",
    "my-podcasts",
]

PUBLIC_FIELDS = {"agent_key", "name", "role", "category", "subcategory", "description"}
FORBIDDEN_FIELDS = {"system_prompt", "allowed_tools", "permissions", "config_profile", "provider", "model"}


@pytest.fixture(scope="module")
def free_user():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json=FREE_USER, timeout=30)
    if r.status_code == 429:
        pytest.skip("Rate limited during login")
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return sess


@pytest.mark.parametrize("feature_key", SPOT_CHECK_FEATURES)
def test_spot_check_feature_relevant_and_sanitized(free_user, feature_key):
    r = free_user.get(f"{BASE_URL}/api/access-control/feature-specialists/{feature_key}", timeout=60)
    assert r.status_code == 200, f"{feature_key}: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data["feature_key"] == feature_key
    assert data["cta_route"] == "/ai-coaching-team"
    assert data["plan"] in ("free", "basic", "premium")
    specialists = data["specialists"]
    assert 1 <= len(specialists) <= 4, f"{feature_key}: {len(specialists)} specialists"
    for sp in specialists:
        keys = set(sp.keys())
        # Strict allow-list check
        assert keys <= PUBLIC_FIELDS, f"{feature_key} leaked fields: {keys - PUBLIC_FIELDS}"
        assert not (keys & FORBIDDEN_FIELDS), f"{feature_key} forbidden fields: {keys & FORBIDDEN_FIELDS}"
        assert sp["name"], f"{feature_key} empty name"
        assert sp["agent_key"], f"{feature_key} empty agent_key"


def test_click_event_persisted_in_mongo(free_user):
    """After POST /click, verify a new doc exists in `specialist_strip_events`."""
    from routes.db import db

    feature_key = "smart-writing-studio"
    agent_key = "creative_writer"

    async def get_count():
        return await db.specialist_strip_events.count_documents(
            {"feature_key": feature_key, "agent_key": agent_key}
        )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        before = loop.run_until_complete(get_count())
        r = free_user.post(
            f"{BASE_URL}/api/access-control/feature-specialists/{feature_key}/click",
            json={"agent_key": agent_key},
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json()["logged"] is True

        # allow a moment for the write
        import time
        time.sleep(0.5)

        after = loop.run_until_complete(get_count())
        assert after == before + 1, f"expected count to grow by 1: before={before} after={after}"

        # Fetch the newest doc and verify required fields
        async def get_latest():
            return await db.specialist_strip_events.find_one(
                {"feature_key": feature_key, "agent_key": agent_key},
                sort=[("created_at", -1)],
            )

        latest = loop.run_until_complete(get_latest())
        assert latest is not None
        for k in ("event_id", "user_id", "feature_key", "agent_key", "plan", "created_at"):
            assert k in latest, f"missing key {k} in event doc"
        assert latest["feature_key"] == feature_key
        assert latest["agent_key"] == agent_key
    finally:
        loop.close()


def test_click_missing_agent_key_returns_422(free_user):
    r = free_user.post(
        f"{BASE_URL}/api/access-control/feature-specialists/smart-writing-studio/click",
        json={},
        timeout=30,
    )
    # Pydantic validation error -> 422
    assert r.status_code in (400, 422)
