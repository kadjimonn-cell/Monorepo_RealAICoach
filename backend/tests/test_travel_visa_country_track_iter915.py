"""Backend tests for Travel Visa Country Track endpoint (iter915).

Feature: GET /api/travel-visa/countries/{code}/track
- Free user: 6 tracks, 5 locked / 1 unlocked (Tourist tier=free)
- Admin: 6 tracks, 0 locked (all lessons visible)
- Invalid country: 404
- Unauthenticated: 401
- Telemetry: doc inserted into tv_country_track_views
"""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASSWORD = "P1Free#2026!Aa"

CSRF_HEADER = {"X-Requested-With": "XMLHttpRequest"}


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", **CSRF_HEADER})
    r = s.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"Auth failed for {email}: {r.status_code} {r.text[:120]}")
    return s


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE_EMAIL, FREE_PASSWORD)


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


# ---------- Free user ----------
class TestCountryTrackFree:
    def test_us_track_free(self, free_session):
        r = free_session.get(f"{API}/travel-visa/countries/US/track", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # plan
        assert data["plan"] == "free", f"Expected free plan (pre-prod lock), got {data.get('plan')}"
        # tracks: expect 6 & sort order free->basic->premium
        tracks = data.get("tracks", [])
        assert len(tracks) == 6, f"Expected 6 tracks, got {len(tracks)}"
        tier_order = ["free", "basic", "premium"]
        tier_indices = [tier_order.index(t.get("tier", "free")) for t in tracks]
        assert tier_indices == sorted(tier_indices), f"Tracks not sorted by tier: {[t.get('tier') for t in tracks]}"
        # locked count
        locked = [t for t in tracks if t.get("locked")]
        unlocked = [t for t in tracks if not t.get("locked")]
        assert data.get("locked_tracks") == 5, f"locked_tracks={data.get('locked_tracks')}"
        assert len(locked) == 5
        assert len(unlocked) == 1
        # Tourist (free) unlocked with sample lessons
        assert unlocked[0]["tier"] == "free"
        assert isinstance(unlocked[0].get("lessons"), list)
        assert len(unlocked[0]["lessons"]) > 0, "Free tier track should have sample lessons"
        # Locked tracks should have empty lessons list
        for t in locked:
            assert t.get("lessons") == [], f"Locked track {t.get('category_id')} lessons not empty"
        # visa_types + embassies_count keys present
        assert "visa_types" in data
        assert isinstance(data["visa_types"], list)
        assert "embassies_count" in data
        assert isinstance(data["embassies_count"], int)

    def test_invalid_country_404(self, free_session):
        r = free_session.get(f"{API}/travel-visa/countries/XX/track", timeout=15)
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:120]}"

    def test_unauthenticated_401(self):
        r = requests.get(f"{API}/travel-visa/countries/US/track", timeout=15)
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"


# ---------- Admin ----------
class TestCountryTrackAdmin:
    def test_us_track_admin(self, admin_session):
        r = admin_session.get(f"{API}/travel-visa/countries/US/track", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["plan"] == "premium", f"Admin plan should be premium, got {data.get('plan')}"
        tracks = data.get("tracks", [])
        assert len(tracks) == 6
        assert data.get("locked_tracks") == 0
        # All tracks should have lessons list (may be empty if no lessons seeded but not locked)
        for t in tracks:
            assert t.get("locked") is False
            assert isinstance(t.get("lessons"), list)
        # At least some tracks should have lessons content
        lesson_totals = sum(len(t.get("lessons") or []) for t in tracks)
        assert lesson_totals > 0, "Expected at least some lessons across admin tracks"


# ---------- Telemetry ----------
class TestTelemetry:
    def test_telemetry_insert_on_call(self, free_session):
        """After a track call, expect a doc in tv_country_track_views collection.

        We verify indirectly by calling twice and checking the DB via a mongo helper.
        """
        # Call endpoint
        r = free_session.get(f"{API}/travel-visa/countries/CA/track", timeout=30)
        assert r.status_code == 200
        # Access DB directly using backend env
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            import asyncio
            mongo_url = os.environ.get("MONGO_URL")
            db_name = os.environ.get("DB_NAME")
            if not mongo_url or not db_name:
                pytest.skip("MONGO_URL/DB_NAME not available in test env")

            async def _check():
                client = AsyncIOMotorClient(mongo_url)
                db = client[db_name]
                cnt = await db.tv_country_track_views.count_documents({"country_code": "CA"})
                client.close()
                return cnt

            cnt = asyncio.run(_check())
            assert cnt >= 1, "Expected at least one telemetry doc for country_code=CA"
        except ImportError:
            pytest.skip("motor not available in test env")
