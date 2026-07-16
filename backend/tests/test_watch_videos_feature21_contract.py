"""Feature 21 (Watch Videos) contract and stability tests.

Focused on permanent contract guarantees to prevent drift:
- Auth required on protected endpoints
- Stable health endpoint
- Bootstrap/catalog/watch/feedback/preferences/watchlist flows
- Recommendation reasons endpoint availability
"""

import os
import time
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _auth_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text[:200]}"
    return s


def test_watch_videos_auth_required_on_core_endpoints():
    endpoints = [
        "/api/videos/health",
        "/api/videos/bootstrap",
        "/api/videos/catalog",
        "/api/videos/preferences",
        "/api/videos/watchlist",
        "/api/videos/recommendations/reasons",
    ]
    for ep in endpoints:
        r = requests.get(f"{BASE_URL}{ep}", timeout=20)
        assert r.status_code == 401, f"Expected 401 for {ep}, got {r.status_code}"


def test_watch_videos_health_bootstrap_catalog_contracts():
    s = _auth_session()

    health = s.get(f"{BASE_URL}/api/videos/health", timeout=30)
    assert health.status_code == 200, health.text[:200]
    h = health.json()
    assert h.get("status") == "healthy"
    assert h.get("feature_id") == "watch-videos"

    boot = s.get(f"{BASE_URL}/api/videos/bootstrap", timeout=45)
    assert boot.status_code == 200, boot.text[:200]
    b = boot.json()
    for key in ["plan", "scope_label", "quota", "categories", "catalog", "recommended_for_you"]:
        assert key in b, f"Missing bootstrap key: {key}"

    catalog = s.get(f"{BASE_URL}/api/videos/catalog", params={"sort_by": "latest", "limit": 12}, timeout=45)
    assert catalog.status_code == 200, catalog.text[:200]
    c = catalog.json()
    assert "items" in c and isinstance(c["items"], list)


def test_watch_videos_recommendation_reasons_endpoint_contract():
    s = _auth_session()
    resp = s.get(f"{BASE_URL}/api/videos/recommendations/reasons", params={"limit": 10}, timeout=45)
    assert resp.status_code == 200, resp.text[:200]
    data = resp.json()
    assert data.get("success") is True
    assert data.get("feature_id") == "watch-videos"
    assert "items" in data and isinstance(data["items"], list)
    if data["items"]:
        first = data["items"][0]
        assert "video_id" in first
        assert "reasons" in first and isinstance(first["reasons"], list)


def test_watch_videos_watch_feedback_preferences_watchlist_flow():
    s = _auth_session()

    catalog = s.get(f"{BASE_URL}/api/videos/catalog", params={"sort_by": "latest", "limit": 15}, timeout=45)
    assert catalog.status_code == 200
    items = catalog.json().get("items", [])
    assert items, "Catalog empty"
    video = items[0]
    video_id = str(video.get("video_id") or "")
    assert video_id

    watch = s.post(
        f"{BASE_URL}/api/videos/watch",
        json={
            "video_id": video_id,
            "progress_seconds": 15,
            "duration_seconds": int(video.get("duration_seconds") or 180),
            "completed": False,
            "source": "contract_test",
        },
        timeout=45,
    )
    assert watch.status_code == 200, watch.text[:200]
    w = watch.json()
    assert w.get("success") is True
    assert "quota" in w and "history" in w

    feedback = s.post(f"{BASE_URL}/api/videos/feedback", json={"video_id": video_id, "feedback": "like"}, timeout=30)
    assert feedback.status_code == 200, feedback.text[:200]
    f = feedback.json()
    assert f.get("success") is True

    pref_read = s.get(f"{BASE_URL}/api/videos/preferences", timeout=30)
    assert pref_read.status_code == 200
    pref_write = s.post(
        f"{BASE_URL}/api/videos/preferences",
        json={"show_recommendation_reasons": True, "autoplay_next_enabled": True},
        timeout=30,
    )
    assert pref_write.status_code == 200

    wl_toggle = s.post(f"{BASE_URL}/api/videos/watchlist/toggle", json={"video_id": video_id, "action": "toggle"}, timeout=30)
    assert wl_toggle.status_code == 200, wl_toggle.text[:200]
    wl = s.get(f"{BASE_URL}/api/videos/watchlist", timeout=30)
    assert wl.status_code == 200
    wl_data = wl.json()
    assert "watchlist" in wl_data and isinstance(wl_data["watchlist"], list)


def test_watch_videos_json_serializable_no_500():
    s = _auth_session()
    endpoints = [
        "/api/videos/health",
        "/api/videos/bootstrap",
        "/api/videos/catalog?sort_by=latest&limit=8",
        "/api/videos/preferences",
        "/api/videos/watchlist",
        "/api/videos/recommendations/reasons?limit=8",
    ]
    for ep in endpoints:
        r = s.get(f"{BASE_URL}{ep}", timeout=45)
        assert r.status_code < 500, f"{ep} returned {r.status_code}"
        _ = r.json()
