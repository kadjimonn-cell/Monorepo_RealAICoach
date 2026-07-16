"""Feature 37 - Flappy Bird Game backend tests.

Validates:
- /api/flappy-bird/bootstrap requires auth (401 unauth), returns fields for authed
- /api/flappy-bird/score persists a run, returns is_new_best, validation for score range
- /api/flappy-bird/leaderboard returns ranked list
- Registry regression: /api/features/registry contains flappy-bird at feature_number=37
- FPS Game regression: /api/games-station/bootstrap still works (authed)
"""

import os
import re

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    # Login (may require OTP bypass for admin; try direct login first)
    resp = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} {resp.text[:200]}")
    # Attach CSRF header for subsequent state-changing requests
    csrf = s.cookies.get("csrf_token")
    if csrf:
        s.headers.update({"X-CSRF-Token": csrf})
    return s


class TestFlappyBirdAuthGuard:
    """Unauthenticated access must be rejected."""

    def test_bootstrap_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"

    def test_leaderboard_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/flappy-bird/leaderboard", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_score_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 1, "duration_ms": 100},
            timeout=15,
        )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


class TestFlappyBirdBootstrap:
    """Authenticated bootstrap returns required shape."""

    def test_bootstrap_shape(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        data = r.json()
        assert data.get("feature_id") == "flappy-bird"
        assert "personal_best" in data and isinstance(data["personal_best"], int)
        assert "games_played" in data and isinstance(data["games_played"], int)
        assert "leaderboard" in data and isinstance(data["leaderboard"], list)
        assert data.get("max_score") == 9999


class TestFlappyBirdScoreValidation:
    """POST /score validation - negative and >9999 must reject with 422."""

    def test_score_negative_rejected(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": -1, "duration_ms": 100},
            timeout=15,
        )
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text[:200]}"

    def test_score_too_high_rejected(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 10000, "duration_ms": 100},
            timeout=15,
        )
        assert r.status_code == 422, f"expected 422, got {r.status_code}"


class TestFlappyBirdScoreSubmit:
    """Happy-path submission increments games_played and updates personal_best when higher."""

    def test_submit_and_persist(self, admin_session):
        # Get baseline
        r0 = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r0.status_code == 200
        baseline = r0.json()
        prev_best = int(baseline["personal_best"])
        prev_games = int(baseline["games_played"])

        # Submit a small (likely not new-best) score
        r1 = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": 1, "duration_ms": 500},
            timeout=15,
        )
        assert r1.status_code == 200, f"{r1.status_code}: {r1.text[:300]}"
        d1 = r1.json()
        assert d1.get("accepted") is True
        assert d1.get("score") == 1
        assert "is_new_best" in d1
        assert d1.get("games_played") == prev_games + 1
        # personal_best should be >= previous
        assert int(d1["personal_best"]) >= prev_best

        # Submit a possible new best (high value but valid). Cap at 9999 (schema max).
        # If prev_best is already 9999 we cannot exceed it — assert non-regressing behavior.
        new_high = min(max(prev_best + 1, 50), 9999)
        r2 = admin_session.post(
            f"{BASE_URL}/api/flappy-bird/score",
            json={"score": new_high, "duration_ms": 1200},
            timeout=15,
        )
        assert r2.status_code == 200
        d2 = r2.json()
        if prev_best < 9999:
            assert d2["is_new_best"] is True
            assert int(d2["personal_best"]) >= new_high
        else:
            # Already at ceiling — best cannot increase; is_new_best must be False
            assert d2["is_new_best"] is False
            assert int(d2["personal_best"]) == 9999
        assert d2["games_played"] == prev_games + 2

        # GET bootstrap to verify persistence
        r3 = admin_session.get(f"{BASE_URL}/api/flappy-bird/bootstrap", timeout=15)
        assert r3.status_code == 200
        d3 = r3.json()
        assert int(d3["personal_best"]) >= new_high
        assert int(d3["games_played"]) == prev_games + 2


class TestFlappyBirdLeaderboard:
    """Leaderboard returns ranked entries."""

    def test_leaderboard_ranked(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/flappy-bird/leaderboard", timeout=15)
        assert r.status_code == 200
        data = r.json()
        lb = data.get("leaderboard")
        assert isinstance(lb, list)
        if len(lb) >= 2:
            # ranks ascending, best_score descending
            for i, entry in enumerate(lb):
                assert entry["rank"] == i + 1
                assert isinstance(entry["best_score"], int)
            for i in range(len(lb) - 1):
                assert lb[i]["best_score"] >= lb[i + 1]["best_score"]


class TestFeatureRegistryRegression:
    """Registry must include flappy-bird at feature_number=37 and preserve prior features."""

    def test_registry_includes_flappy_bird(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        data = r.json()
        # Registry format may be { features: [...] } or a list
        features = data.get("features") if isinstance(data, dict) else data
        assert isinstance(features, list), f"features shape: {type(features)}"
        by_id = {f.get("feature_id") or f.get("id") or f.get("slug"): f for f in features}
        fb = by_id.get("flappy-bird")
        assert fb is not None, "flappy-bird missing from feature registry"
        # feature_number = 37
        num = fb.get("feature_number") or fb.get("number")
        assert num == 37, f"expected feature_number 37, got {num}"
        route = fb.get("route") or fb.get("path")
        assert route == "/features/flappy-bird", f"route mismatch: {route}"
        category = fb.get("category")
        assert category == "entertainment"

    def test_registry_preserves_36_prior_features(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert r.status_code == 200
        data = r.json()
        features = data.get("features") if isinstance(data, dict) else data
        numbers = sorted({f.get("feature_number") or f.get("number") for f in features if (f.get("feature_number") or f.get("number"))})
        # 1..37 must all be present
        assert 37 in numbers
        for n in range(1, 37):
            assert n in numbers, f"feature_number {n} missing (regression!)"


class TestFPSGameRegression:
    """FPS Game endpoints must still function (adjacent Feature 22 regression)."""

    def test_games_station_bootstrap(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/games-station/bootstrap", timeout=15)
        # Bootstrap must not 5xx; 200 preferred. 404 would indicate regression.
        assert r.status_code in (200, 401, 403), f"regression suspected: {r.status_code}: {r.text[:200]}"
