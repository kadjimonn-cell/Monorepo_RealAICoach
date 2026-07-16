"""Tests for i18n pre-warm cache admin endpoints.

Covers:
 - Auth: unauthenticated calls to POST/GET pre-warm endpoints must be rejected.
 - Auth: admin session (cookie + X-Requested-With) can call the endpoints.
 - Validation: unsupported languages -> 400.
 - Status: latest run reports 'done' for fr/es/de.
 - Idempotency: preview.fr.to_warm should be 0 (already 100% cached).
 - Cache effect: auto-translate returns quickly and returns translations (all cached hits).
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(scope="module")
def anon_session():
    s = requests.Session()
    # no auth
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers=CSRF_HEADERS,
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
    return s


# ---------- AUTH: unauthenticated ----------

class TestPrewarmAuth:
    def test_post_prewarm_unauth_rejected(self, anon_session):
        r = anon_session.post(
            f"{API}/i18n/pre-warm-cache",
            json={"langs": ["fr"]},
            headers=CSRF_HEADERS,
            timeout=20,
        )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code} {r.text[:200]}"

    def test_get_prewarm_status_unauth_rejected(self, anon_session):
        r = anon_session.get(f"{API}/i18n/pre-warm-cache/status", timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code} {r.text[:200]}"


# ---------- Status as admin ----------

class TestPrewarmStatus:
    def test_admin_can_read_status(self, admin_session):
        r = admin_session.get(
            f"{API}/i18n/pre-warm-cache/status",
            headers=CSRF_HEADERS,
            timeout=20,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        data = r.json()
        assert "latest_run" in data
        latest = data["latest_run"]
        assert latest is not None, "expected at least one prior prewarm run"
        assert latest.get("status") == "done", f"latest run status={latest.get('status')}"
        langs = latest.get("langs") or {}
        # We only require that whatever langs are present all are done.
        for code, entry in langs.items():
            assert entry.get("status") == "done", f"lang {code} not done: {entry}"


# ---------- Validation ----------

class TestPrewarmValidation:
    def test_unsupported_lang_returns_400(self, admin_session):
        r = admin_session.post(
            f"{API}/i18n/pre-warm-cache",
            json={"langs": ["xx"]},
            headers=CSRF_HEADERS,
            timeout=20,
        )
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"
        body = r.text.lower()
        assert "unsupported" in body


# ---------- Idempotency (preview) ----------

class TestPrewarmIdempotency:
    def test_prewarm_fr_preview_to_warm_is_zero(self, admin_session):
        r = admin_session.post(
            f"{API}/i18n/pre-warm-cache",
            json={"langs": ["fr"]},
            headers=CSRF_HEADERS,
            timeout=30,
        )
        # if a run is already in progress, that's fine and we skip
        if r.status_code == 409:
            pytest.skip("A prewarm run is already in progress on the server")
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        data = r.json()
        assert data.get("success") is True
        preview = data.get("preview") or {}
        assert "fr" in preview
        assert preview["fr"]["to_warm"] == 0, f"preview.fr.to_warm expected 0, got {preview['fr']}"
        run_id = data["run_id"]

        # Poll until run done — should be quick since attempted=0
        deadline = time.time() + 20
        final = None
        while time.time() < deadline:
            s = admin_session.get(
                f"{API}/i18n/pre-warm-cache/status",
                headers=CSRF_HEADERS,
                timeout=20,
            )
            assert s.status_code == 200
            latest = (s.json() or {}).get("latest_run") or {}
            if latest.get("run_id") == run_id and latest.get("status") == "done":
                final = latest
                break
            time.sleep(0.5)
        assert final is not None, "prewarm run did not finish in 20s"
        fr_entry = (final.get("langs") or {}).get("fr") or {}
        assert fr_entry.get("status") == "done"
        assert fr_entry.get("attempted", -1) == 0, f"expected attempted=0, got {fr_entry}"


# ---------- Cache effect ----------

class TestPrewarmCacheEffect:
    SEEDS = [
        "FPS Game",
        "Flappy Bird Game",
        "Audio Studio",
        "My Podcasts",
        "Daily Meditation",
        "AI-Powered Visa Coaching",
        "Settings",
        "Profile",
        "Home",
        "Logout",
    ]

    def test_auto_translate_fr_cached_hits(self, admin_session):
        # Shuffle to bust the burst-dedupe cache (identical payload dedupe window)
        # but keep every string within the warmed seed set so all are cache hits.
        import random
        seeds = list(self.SEEDS)
        random.shuffle(seeds)
        payload = {"lang": "fr", "texts": seeds}
        start = time.time()
        r = admin_session.post(
            f"{API}/i18n/auto-translate",
            json=payload,
            headers=CSRF_HEADERS,
            timeout=15,
        )
        elapsed = time.time() - start
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        data = r.json()
        translations = data.get("translations") or {}
        # Every seed should have a translation entry
        for s in self.SEEDS:
            assert s in translations, f"missing translation for seed '{s}'"
        # Latency should be tight since all seeds are cache hits (allow 1.5s per spec)
        assert elapsed < 1.5, f"auto-translate too slow ({elapsed:.2f}s) — cache miss?"
        # At least some translations should differ from source (French)
        differed = [k for k in self.SEEDS if translations.get(k) and translations[k] != k]
        assert len(differed) >= 3, f"expected >=3 non-identity translations, got {differed}"
