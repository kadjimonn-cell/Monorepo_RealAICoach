"""Suggested AI Specialists strip — user-facing recommendation endpoints.

GET  /api/access-control/feature-specialists/{feature_key}       (sanitized, user auth)
POST /api/access-control/feature-specialists/{feature_key}/click (conversion event)
"""

import os
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")

from utils.access_control_engine import CANONICAL_FEATURE_METERS  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

FREE_USER = {"email": "p1.free.1779113329@example.com", "password": "P1Free#2026!Aa"}

FEATURE_KEYS = [m["feature_key"] for m in CANONICAL_FEATURE_METERS]
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


def test_requires_auth():
    r = requests.get(f"{BASE_URL}/api/access-control/feature-specialists/money-strategy-hub", timeout=30)
    assert r.status_code in (401, 403)


def test_unknown_feature_404(free_user):
    r = free_user.get(f"{BASE_URL}/api/access-control/feature-specialists/not-a-feature", timeout=30)
    assert r.status_code == 404


def test_specialists_sanitized_and_relevant(free_user):
    r = free_user.get(f"{BASE_URL}/api/access-control/feature-specialists/money-strategy-hub", timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert data["feature_key"] == "money-strategy-hub"
    assert data["plan"] in ("free", "basic", "premium")
    assert data["cta_route"] == "/ai-coaching-team"
    specialists = data["specialists"]
    assert 1 <= len(specialists) <= 4
    for sp in specialists:
        assert set(sp.keys()) <= PUBLIC_FIELDS, f"leaked fields: {set(sp.keys()) - PUBLIC_FIELDS}"
        assert not (set(sp.keys()) & FORBIDDEN_FIELDS)
        assert sp["name"] and sp["agent_key"]


def test_every_canonical_feature_returns_specialists(free_user):
    for fk in FEATURE_KEYS:
        r = free_user.get(f"{BASE_URL}/api/access-control/feature-specialists/{fk}", timeout=60)
        assert r.status_code == 200, f"{fk}: {r.status_code}"
        assert len(r.json()["specialists"]) >= 1, f"{fk} returned no specialists"


def test_click_event_logged(free_user):
    r = free_user.post(
        f"{BASE_URL}/api/access-control/feature-specialists/money-strategy-hub/click",
        json={"agent_key": "financial_advisor"}, timeout=30)
    assert r.status_code == 200
    assert r.json()["logged"] is True


def test_click_unknown_feature_404(free_user):
    r = free_user.post(
        f"{BASE_URL}/api/access-control/feature-specialists/not-a-feature/click",
        json={"agent_key": "financial_advisor"}, timeout=30)
    assert r.status_code == 404


def test_click_requires_auth():
    r = requests.post(
        f"{BASE_URL}/api/access-control/feature-specialists/money-strategy-hub/click",
        json={"agent_key": "financial_advisor"},
        headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}, timeout=30)
    assert r.status_code in (401, 403)
