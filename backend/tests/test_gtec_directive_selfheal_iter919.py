"""Iter919 — Two-tier GTEC directive self-heal verification.

Hardened fix under test:
- Tier 1: packaged md at /app/backend/assets/gtec_directive_canonical.md
- Tier 2 (NEW): embedded Python fallback /app/backend/gtec_directive_embedded.py
  with DIRECTIVE_TEXT constant (py modules always ship with code, even in
  stale/broken container images that omit /app/memory or /app/backend/assets).

The tests below prove the current code path cannot hit the production
"FATAL: Global System Directive missing" error because it now has TWO
independent packaged fallbacks in front of the raise.

Reference:
- /app/backend/middleware_gtec_directive.py (_read_packaged_directive helper)
- /app/backend/gtec_directive_embedded.py (DIRECTIVE_TEXT constant)
- /app/backend/assets/gtec_directive_canonical.md (packaged md copy)
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
import requests

# Ensure backend/ is importable
BACKEND_DIR = "/app/backend"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com"
).rstrip("/")

DIRECTIVE_PATH = Path("/app/memory/GTEC_DIRECTIVE.md")
PACKAGED_PATH = Path("/app/backend/assets/gtec_directive_canonical.md")
EMBEDDED_MODULE = "gtec_directive_embedded"


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture
def preserve_directive():
    """Snapshot the current directive file, restore in teardown (always)."""
    original_bytes = DIRECTIVE_PATH.read_bytes() if DIRECTIVE_PATH.exists() else None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".md")
    tmp.close()
    if original_bytes is not None:
        Path(tmp.name).write_bytes(original_bytes)
    try:
        yield Path(tmp.name)
    finally:
        # Always restore original file exactly
        try:
            if original_bytes is not None:
                DIRECTIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
                DIRECTIVE_PATH.write_bytes(original_bytes)
            else:
                if DIRECTIVE_PATH.exists():
                    DIRECTIVE_PATH.unlink()
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


@pytest.fixture
def fresh_module():
    """Freshly reload the middleware module so _STATE is reset per test."""
    if "middleware_gtec_directive" in sys.modules:
        del sys.modules["middleware_gtec_directive"]
    mod = importlib.import_module("middleware_gtec_directive")
    return mod


# ── UNIT: Three-way content sync ────────────────────────────────────────────
class TestThreeWaySync:
    """The three sources (memory, packaged md, embedded py) must be identical."""

    def test_all_three_sources_identical_content(self):
        mem = DIRECTIVE_PATH.read_text(encoding="utf-8")
        pkg = PACKAGED_PATH.read_text(encoding="utf-8")
        # Force fresh import
        if EMBEDDED_MODULE in sys.modules:
            del sys.modules[EMBEDDED_MODULE]
        from gtec_directive_embedded import DIRECTIVE_TEXT  # type: ignore

        assert len(mem) == 12588, f"memory chars={len(mem)} expected 12588"
        assert len(pkg) == 12588, f"packaged chars={len(pkg)} expected 12588"
        assert len(DIRECTIVE_TEXT) == 12588, (
            f"embedded chars={len(DIRECTIVE_TEXT)} expected 12588"
        )
        assert mem == pkg, "memory diverged from packaged md"
        assert mem == DIRECTIVE_TEXT, "memory diverged from embedded py"
        assert pkg == DIRECTIVE_TEXT, "packaged md diverged from embedded py"

    def test_embedded_module_directly_importable(self):
        if EMBEDDED_MODULE in sys.modules:
            del sys.modules[EMBEDDED_MODULE]
        mod = importlib.import_module(EMBEDDED_MODULE)
        assert hasattr(mod, "DIRECTIVE_TEXT")
        assert isinstance(mod.DIRECTIVE_TEXT, str)
        assert len(mod.DIRECTIVE_TEXT) > 200


# ── UNIT: Tier 1 self-heal (from packaged md) ───────────────────────────────
class TestTier1SelfHealFromPackagedMd:
    """Memory file missing → self-heal from packaged md (existing Tier 1)."""

    def test_missing_directive_selfheals_from_packaged_md(
        self, preserve_directive, fresh_module
    ):
        if DIRECTIVE_PATH.exists():
            DIRECTIVE_PATH.unlink()
        assert not DIRECTIVE_PATH.exists()

        state = fresh_module.enforce_directive_on_boot()

        assert state["loaded"] is True
        assert state["byte_size"] > 200
        assert DIRECTIVE_PATH.exists(), "Directive file should be restored on disk"
        assert (
            DIRECTIVE_PATH.read_text(encoding="utf-8")
            == PACKAGED_PATH.read_text(encoding="utf-8")
        )


# ── UNIT: Tier 2 self-heal (from embedded py) — THE NEW TIER ────────────────
class TestTier2SelfHealFromEmbeddedPy:
    """Memory + packaged md both missing → self-heal from embedded py DIRECTIVE_TEXT.

    This is the critical NEW test — it proves that even if a container ships
    without /app/memory AND without /app/backend/assets/, the enforce boot
    still succeeds via the embedded Python fallback that ALWAYS ships with the
    backend code.
    """

    def test_selfheals_from_embedded_when_packaged_md_missing(
        self, preserve_directive, fresh_module, monkeypatch
    ):
        # 1. Remove /app/memory copy
        if DIRECTIVE_PATH.exists():
            DIRECTIVE_PATH.unlink()
        assert not DIRECTIVE_PATH.exists()

        # 2. Point PACKAGED_DIRECTIVE_FILE to a nonexistent path (simulate
        #    missing /app/backend/assets/)
        monkeypatch.setattr(
            fresh_module,
            "PACKAGED_DIRECTIVE_FILE",
            Path("/nonexistent/gtec_directive_canonical.md"),
        )

        # 3. enforce_directive_on_boot MUST still succeed via embedded fallback
        state = fresh_module.enforce_directive_on_boot()

        assert state["loaded"] is True, f"Expected loaded=True, got {state}"
        assert state["byte_size"] > 200, (
            f"Expected byte_size>200 via embedded fallback, got {state['byte_size']}"
        )
        assert DIRECTIVE_PATH.exists(), (
            "Directive file should have been restored on disk from embedded py"
        )
        # Content matches embedded constant
        if EMBEDDED_MODULE in sys.modules:
            del sys.modules[EMBEDDED_MODULE]
        from gtec_directive_embedded import DIRECTIVE_TEXT  # type: ignore

        assert DIRECTIVE_PATH.read_text(encoding="utf-8") == DIRECTIVE_TEXT

    def test_read_packaged_directive_helper_falls_through_to_embedded(
        self, fresh_module, monkeypatch
    ):
        """Directly test the _read_packaged_directive helper falls through."""
        monkeypatch.setattr(
            fresh_module,
            "PACKAGED_DIRECTIVE_FILE",
            Path("/nonexistent/gtec_directive_canonical.md"),
        )
        text = fresh_module._read_packaged_directive()
        assert isinstance(text, str)
        assert len(text) > 200, (
            f"Helper should have returned embedded text, got len={len(text)}"
        )


# ── UNIT: Negative path — all three tiers unavailable ───────────────────────
class TestAllTiersUnavailableRaises:
    """Memory + packaged md + embedded py all unavailable → MUST raise.

    Compliance gate: the platform must refuse to boot only if literally NO
    canonical source is reachable.
    """

    def test_all_three_missing_raises_runtime_error(
        self, preserve_directive, fresh_module, monkeypatch
    ):
        # 1. Remove memory copy
        if DIRECTIVE_PATH.exists():
            DIRECTIVE_PATH.unlink()

        # 2. Point packaged md at nonexistent path
        monkeypatch.setattr(
            fresh_module,
            "PACKAGED_DIRECTIVE_FILE",
            Path("/nonexistent/gtec_directive_canonical.md"),
        )

        # 3. Block the embedded import by removing from sys.modules and shim'ing
        #    the import machinery so re-import raises ImportError.
        monkeypatch.delitem(sys.modules, EMBEDDED_MODULE, raising=False)

        class _BlockingFinder:
            def find_module(self, name, path=None):  # legacy API
                if name == EMBEDDED_MODULE:
                    return self
                return None

            def load_module(self, name):
                raise ImportError(f"blocked for test: {name}")

            # PEP 451 modern API
            def find_spec(self, name, path, target=None):
                if name == EMBEDDED_MODULE:
                    raise ImportError(f"blocked for test: {name}")
                return None

        blocker = _BlockingFinder()
        sys.meta_path.insert(0, blocker)
        try:
            with pytest.raises(RuntimeError) as exc_info:
                fresh_module.enforce_directive_on_boot()
            assert "FATAL" in str(exc_info.value)
            assert "Global System Directive" in str(exc_info.value)
        finally:
            try:
                sys.meta_path.remove(blocker)
            except ValueError:
                pass


# ── LIVE: Backend regression ────────────────────────────────────────────────
class TestBackendLive:
    """Live regression — backend up, directive loaded, admin login works."""

    def test_health_200(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200, f"health={r.status_code} body={r.text[:200]}"

    def test_directive_state_loaded(self):
        r = requests.get(f"{BASE_URL}/api/gtec/directive/state", timeout=15)
        assert r.status_code == 200, f"state={r.status_code} body={r.text[:200]}"
        body = r.json()
        assert body.get("loaded") is True
        assert body.get("always_active") is True
        assert body.get("non_disableable") is True
        assert body.get("byte_size", 0) > 200
        assert body.get("version")

    def test_admin_login_regression(self):
        s = requests.Session()
        s.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        r = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
            timeout=20,
        )
        assert r.status_code == 200, f"login={r.status_code} body={r.text[:200]}"
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert me.status_code == 200
        me_body = me.json()
        email = me_body.get("email") or me_body.get("user", {}).get("email")
        assert email == "admin@realaicoach.app"
        # GTEC headers present on admin responses
        assert me.headers.get("X-GTEC-Directive-Status") == "ALWAYS-ACTIVE"
        assert me.headers.get("X-GTEC-Directive-Version")
