"""Iter917 — Mono cross-platform restructure regression.

Verifies backend is healthy after /app/frontend -> /app/frontend move and new web shell
was added at /app/frontend, and preview_host_guard still passes at boot.
"""
import os
import subprocess
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASS = "NewAdminPass2026!"
FREE_EMAIL = "p1.free.1779113329@example.com"
FREE_PASS = "P1Free#2026!Aa"


# ------------------------ Structure & files -----------------------------------
class TestStructure:
    def test_frontend_has_react_scripts_not_expo(self):
        pkg = Path("/app/frontend/package.json").read_text()
        assert "react-scripts" in pkg
        assert '"expo"' not in pkg

    def test_mobile_has_expo(self):
        pkg = Path("/app/frontend/package.json").read_text()
        assert '"expo"' in pkg

    def test_mobile_eas_and_app_json_present(self):
        assert Path("/app/frontend/eas.json").exists()
        assert Path("/app/frontend/app.json").exists()

    def test_web_shell_files_present(self):
        for p in [
            "/app/frontend/server.js",
            "/app/frontend/scripts/build.js",
            "/app/frontend/scripts/sync-rnw.js",
        ]:
            assert Path(p).exists(), f"missing {p}"

    def test_frontend_env_has_expo_tunnel_subdomain(self):
        env = Path("/app/frontend/.env").read_text()
        assert "EXPO_TUNNEL_SUBDOMAIN=coach-web-preview
        assert "REACT_APP_BACKEND_URL=" in env


# ------------------------ Backend health / auth -------------------------------
class TestBackendHealth:
    def test_health_200(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"

    def test_admin_login_cookie_auth(self):
        s = requests.Session()
        r = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        # /auth/me works with session cookie
        me = s.get(
            f"{BASE_URL}/api/auth/me",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert me.status_code == 200, me.text[:200]
        body = me.json()
        assert body.get("email") == ADMIN_EMAIL

    def test_free_user_login_and_me(self):
        s = requests.Session()
        r = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": FREE_EMAIL, "password": FREE_PASS},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code == 200, r.text[:200]
        me = s.get(
            f"{BASE_URL}/api/auth/me",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert me.status_code == 200, me.text[:200]
        assert me.json().get("email") == FREE_EMAIL


# ------------------------ Backend startup clean -------------------------------
class TestBackendStartupLogs:
    """Ensure current backend boot has NO /app/frontend path errors.

    Historical failures BEFORE the fresh restart are expected in the log (they
    are what motivated the fix). We only assert that the most recent boot
    (identified by the last "Application startup complete." marker) is clean.
    """

    LOG = "/var/log/supervisor/backend.err.log"

    def test_current_boot_has_no_frontend_path_errors(self):
        raw = Path(self.LOG).read_text(errors="replace")
        # locate last "Application startup complete" — everything after is
        # the currently-running process' runtime log.
        idx = raw.rfind("Application startup complete.")
        assert idx != -1, "no startup completion marker found"
        tail = raw[idx:]
        # These strings would indicate the guard rejected /app/frontend/.env
        # or the bulk-path fix left a dangling reference.
        bad = [
            "/app/frontend/.env: missing env file",
            "/app/frontend/.env: missing EXPO_TUNNEL_SUBDOMAIN",
            "Preview startup host guard failed",
        ]
        offenders = [b for b in bad if b in tail]
        assert not offenders, f"post-boot errors detected: {offenders}"

    def test_current_boot_no_filenotfound_for_frontend_paths(self):
        raw = Path(self.LOG).read_text(errors="replace")
        idx = raw.rfind("Application startup complete.")
        tail = raw[idx:] if idx != -1 else raw
        # FileNotFoundError referencing /app/frontend/ (stale path from bulk rename)
        import re

        matches = re.findall(
            r"FileNotFoundError.*?/app/frontend/[A-Za-z0-9_./-]+", tail
        )
        assert not matches, f"stale /app/frontend/ path errors: {matches[:5]}"


# ------------------------ Web shell smoke (port 3555) -------------------------
@pytest.fixture(scope="module")
def web_shell():
    """Boot the new web shell on port 3555, yield base url, then kill it."""
    env = os.environ.copy()
    env["PORT"] = "3555"
    proc = subprocess.Popen(
        ["node", "server.js"],
        cwd="/app/frontend",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # wait until listening
    import time

    for _ in range(30):
        try:
            requests.get("http://localhost:3555/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    yield "http://localhost:3555"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


class TestWebShell:
    def test_healthz(self, web_shell):
        r = requests.get(f"{web_shell}/healthz", timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert "build" in body.get("dist_dir", "") or "rnw_dist" in body.get(
            "dist_dir", ""
        )

    def test_root_serves_html(self, web_shell):
        r = requests.get(f"{web_shell}/", timeout=5)
        assert r.status_code == 200
        assert len(r.content) > 1000

    def test_welcome_serves_html(self, web_shell):
        r = requests.get(f"{web_shell}/welcome", timeout=5)
        assert r.status_code == 200
        assert len(r.content) > 1000


# ------------------------ Build script ----------------------------------------
class TestBuildScript:
    def test_build_script_runs_and_produces_client_and_server(self, tmp_path):
        # run in place — script writes to /app/frontend/build
        r = subprocess.run(
            ["node", "scripts/build.js"],
            cwd="/app/frontend",
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"build failed: {r.stderr[-400:]}"
        assert Path("/app/frontend/build/client").is_dir()
        assert Path("/app/frontend/build/server").is_dir()
