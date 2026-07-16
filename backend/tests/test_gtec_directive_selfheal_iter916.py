"""Iter916 — Verify GTEC directive self-heal from packaged canonical copy.

Bug fix under test: production containers do not ship /app/memory. The boot
enforcer must self-heal /app/memory/GTEC_DIRECTIVE.md from the packaged copy
at /app/backend/assets/gtec_directive_canonical.md rather than raising, only
raising if BOTH copies are unavailable.

Reference: /app/backend/middleware_gtec_directive.py
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import requests

# Ensure backend/ is importable
BACKEND_DIR = "/app/backend"
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

DIRECTIVE_PATH = Path("/app/memory/GTEC_DIRECTIVE.md")
PACKAGED_PATH = Path("/app/backend/assets/gtec_directive_canonical.md")


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture
def preserve_directive():
    """Snapshot the current directive file to a temp path, restore in teardown."""
    original_bytes = DIRECTIVE_PATH.read_bytes() if DIRECTIVE_PATH.exists() else None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".md")
    tmp.close()
    if original_bytes is not None:
        Path(tmp.name).write_bytes(original_bytes)
    yield Path(tmp.name)
    # Restore original file exactly
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


# ── BACKEND UNIT tests ──────────────────────────────────────────────────────
class TestPackagedCanonicalCopy:
    """Packaged canonical asset sanity."""

    def test_packaged_copy_exists_and_is_large(self):
        assert PACKAGED_PATH.exists(), f"Missing packaged copy: {PACKAGED_PATH}"
        content = PACKAGED_PATH.read_text(encoding="utf-8")
        assert len(content) > 200, f"Packaged copy too small: {len(content)} chars"

    def test_packaged_copy_matches_memory_directive(self):
        assert DIRECTIVE_PATH.exists(), "Memory directive missing before test"
        assert PACKAGED_PATH.read_text(encoding="utf-8") == DIRECTIVE_PATH.read_text(encoding="utf-8"), \
            "Packaged canonical copy diverged from /app/memory/GTEC_DIRECTIVE.md"


class TestSelfHealMissingFile:
    """Directive file missing → must self-heal from packaged copy."""

    def test_missing_directive_selfheals_without_raise(self, preserve_directive, fresh_module):
        # Remove the memory directive to simulate production container state
        if DIRECTIVE_PATH.exists():
            DIRECTIVE_PATH.unlink()
        assert not DIRECTIVE_PATH.exists()

        # Should NOT raise
        state = fresh_module.enforce_directive_on_boot()

        assert state["loaded"] is True, f"Expected loaded=True, got {state}"
        assert state["byte_size"] > 200, f"Expected byte_size>200, got {state['byte_size']}"
        assert DIRECTIVE_PATH.exists(), "Directive file was not restored on disk"
        # Confirm file content is same as packaged
        assert DIRECTIVE_PATH.read_text(encoding="utf-8") == PACKAGED_PATH.read_text(encoding="utf-8")


class TestSelfHealTruncatedFile:
    """Directive file truncated (<200 chars) → must self-heal from packaged copy."""

    def test_truncated_directive_selfheals(self, preserve_directive, fresh_module):
        DIRECTIVE_PATH.write_text("short", encoding="utf-8")
        assert DIRECTIVE_PATH.exists()
        assert len(DIRECTIVE_PATH.read_text(encoding="utf-8")) < 200

        state = fresh_module.enforce_directive_on_boot()

        assert state["loaded"] is True
        assert state["byte_size"] > 200
        # Verify content was restored (not the truncated version)
        assert DIRECTIVE_PATH.read_text(encoding="utf-8") == PACKAGED_PATH.read_text(encoding="utf-8")


class TestSelfHealBothUnavailable:
    """All three sources missing → MUST raise RuntimeError.

    NOTE (iter919): the hardening added a NEW embedded Python fallback via
    _read_packaged_directive() → gtec_directive_embedded.DIRECTIVE_TEXT. To
    reach the raise now we must also block the embedded import.
    """

    def test_both_missing_raises(self, preserve_directive, fresh_module, monkeypatch):
        # Remove memory copy
        if DIRECTIVE_PATH.exists():
            DIRECTIVE_PATH.unlink()
        # Point packaged path to a nonexistent location
        monkeypatch.setattr(
            fresh_module,
            "PACKAGED_DIRECTIVE_FILE",
            Path("/nonexistent/gtec_directive_canonical.md"),
        )

        # Block the embedded Python fallback too (iter919 hardening).
        monkeypatch.delitem(sys.modules, "gtec_directive_embedded", raising=False)

        class _BlockingFinder:
            def find_spec(self, name, path, target=None):
                if name == "gtec_directive_embedded":
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


# ── BACKEND LIVE tests ──────────────────────────────────────────────────────
class TestBackendLiveHealth:
    """Live service regression: backend up + directive state endpoint responds."""

    def test_health_endpoint_200(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

    def test_gtec_directive_state_public(self):
        r = requests.get(f"{BASE_URL}/api/gtec/directive/state", timeout=15)
        assert r.status_code == 200, f"Expected 200 on directive state, got {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert body.get("loaded") is True, f"loaded should be True, got: {body}"
        assert body.get("always_active") is True, f"always_active should be True, got: {body}"
        assert body.get("non_disableable") is True
        assert body.get("byte_size", 0) > 200, f"byte_size>200 required, got: {body.get('byte_size')}"
        assert body.get("version"), "version hash should be present"

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
        assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text[:200]}"
        # verify session cookie set + /me returns admin
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert me.status_code == 200, f"/auth/me failed after login: {me.status_code} {me.text[:200]}"
        me_body = me.json()
        assert (me_body.get("email") or me_body.get("user", {}).get("email")) == "admin@realaicoach.app"
        # Response should carry GTEC directive headers
        assert me.headers.get("X-GTEC-Directive-Status") == "ALWAYS-ACTIVE", \
            f"Missing/incorrect X-GTEC-Directive-Status header: {dict(me.headers)}"
        assert me.headers.get("X-GTEC-Directive-Version"), "Missing X-GTEC-Directive-Version header"
