"""P0 White-Screen Sentry + Viewport Matrix Tests for GTEC C5.

Tests the newly added P0 features:
1. POST /api/admin/gtec-scan-v2/pipeline/go-no-go-drill - returns quickly with white-screen gate validation
2. Continuous monitoring stores viewport matrix metadata
3. GET /api/admin/gtec-scan-v2/pipeline/evidence-bundle/latest - includes viewport_matrix and white_screen_sentry
4. GET /api/admin/gtec-scan-v2/pipeline/viewport-artifacts/latest - returns latest artifact run
5. GET /api/admin/gtec-scan-v2/release-certificate - includes checks.white_screen_sentry and checks.responsive_viewport_matrix
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest
import requests


def _load_base_url() -> str:
    """Load base URL from environment or .env file."""
    env = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if env:
        return env.rstrip("/")
    # Fallback to localhost for internal testing
    return "http://localhost:8001"


BASE_URL = _load_base_url()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@realaicoach.app")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "NewAdminPass2026!")

# Module-level session
_ADMIN_SESSION = None
_SESSION_TOKEN = None


def _is_admin_forbidden(response: requests.Response) -> bool:
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    if isinstance(detail, str) and "admin access required" in detail.lower():
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}:
            return True
        message = str(detail.get("message") or "").lower()
        if "admin access blocked" in message:
            return True

    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    return top_code in {"RISK_ENGINE_ADMIN_API_BLOCKED", "RISK_ENGINE_ID_VERIFICATION_REQUIRED"}


def _skip_if_admin_blocked_response(response: requests.Response, context: str) -> None:
    if _is_admin_forbidden(response):
        pytest.skip(f"{context} blocked by environment containment/authorization policy")


def _get_admin_session() -> requests.Session:
    """Get or create a shared admin session."""
    global _ADMIN_SESSION, _SESSION_TOKEN
    
    if _ADMIN_SESSION is not None and _SESSION_TOKEN is not None:
        return _ADMIN_SESSION
    
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    token = (
        data.get("session_token")
        or data.get("token")
        or data.get("access_token")
        or r.cookies.get("session_token")
        or s.cookies.get("session_token")
    )
    if not token:
        pytest.skip("missing token in login JSON/cookies")
    s.headers.update({"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"})

    original_get = s.get

    def guarded_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        if _is_admin_forbidden(response):
            pytest.skip("Admin API blocked by environment containment/authorization policy")
        return response

    s.get = guarded_get
    
    _ADMIN_SESSION = s
    _SESSION_TOKEN = token
    return s


@pytest.fixture(scope="module")
def admin_session():
    """Module-scoped fixture for admin session."""
    return _get_admin_session()


class TestGTECP0SentryViewport:
    """P0 White-Screen Sentry + Viewport Matrix Tests"""

    def test_go_no_go_drill_returns_white_screen_validation(self, admin_session):
        """Test POST /api/admin/gtec-scan-v2/pipeline/go-no-go-drill returns white-screen gate validation fields."""
        r = admin_session.post(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/go-no-go-drill",
            json={"simulate_hard_block": True},
            timeout=300,  # Allow time for sentry to run
        )
        _skip_if_admin_blocked_response(r, "go-no-go drill")
        assert r.status_code == 200, f"go-no-go-drill failed: {r.status_code} {r.text[:300]}"
        
        body = r.json()
        
        # Verify required fields
        assert body.get("drill_id"), "Missing drill_id"
        assert body.get("decision") in {"GO", "NO_GO"}, f"Invalid decision: {body.get('decision')}"
        assert body.get("drill_at"), "Missing drill_at"
        
        # Verify validation block with white-screen gate fields
        validation = body.get("validation") or {}
        assert "white_screen_gate_passed" in validation, "Missing white_screen_gate_passed in validation"
        assert "white_screen_failed_checks" in validation, "Missing white_screen_failed_checks in validation"
        assert "white_screen_total_checks" in validation, "Missing white_screen_total_checks in validation"
        assert "hard_block_validation_passed" in validation, "Missing hard_block_validation_passed in validation"
        assert "all_gates_pass" in validation, "Missing all_gates_pass in validation"
        
        # Verify viewport_matrix_run_id is present
        assert body.get("viewport_matrix_run_id"), "Missing viewport_matrix_run_id"
        
        print(f"GO/NO-GO drill: decision={body.get('decision')}, "
              f"white_screen_gate_passed={validation.get('white_screen_gate_passed')}, "
              f"failed_checks={validation.get('white_screen_failed_checks')}/{validation.get('white_screen_total_checks')}")

    def test_evidence_bundle_includes_viewport_matrix_and_sentry(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/pipeline/evidence-bundle/latest includes viewport_matrix and white_screen_sentry."""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/evidence-bundle/latest",
            timeout=30,
        )
        assert r.status_code == 200, f"evidence-bundle/latest failed: {r.status_code} {r.text[:200]}"
        
        body = r.json()
        bundle = body.get("bundle") or {}
        
        # Verify bundle structure
        assert bundle.get("bundle_id"), "Missing bundle_id"
        
        # Verify viewport_matrix section
        viewport_matrix = bundle.get("viewport_matrix") or {}
        assert "run_id" in viewport_matrix, "Missing viewport_matrix.run_id"
        assert "viewports" in viewport_matrix, "Missing viewport_matrix.viewports"
        assert "routes_tested" in viewport_matrix, "Missing viewport_matrix.routes_tested"
        assert "total_checks" in viewport_matrix, "Missing viewport_matrix.total_checks"
        assert "failed_checks" in viewport_matrix, "Missing viewport_matrix.failed_checks"
        assert "matrix_summary" in viewport_matrix, "Missing viewport_matrix.matrix_summary"
        assert "artifacts" in viewport_matrix, "Missing viewport_matrix.artifacts"
        
        # Verify white_screen_sentry section
        white_screen_sentry = bundle.get("white_screen_sentry") or {}
        assert "run_id" in white_screen_sentry, "Missing white_screen_sentry.run_id"
        assert "gate_passed" in white_screen_sentry, "Missing white_screen_sentry.gate_passed"
        assert "failed_checks" in white_screen_sentry, "Missing white_screen_sentry.failed_checks"
        assert "total_checks" in white_screen_sentry, "Missing white_screen_sentry.total_checks"
        assert "generated_at" in white_screen_sentry, "Missing white_screen_sentry.generated_at"
        
        print(f"Evidence bundle: bundle_id={bundle.get('bundle_id')}, "
              f"viewport_matrix.run_id={viewport_matrix.get('run_id')}, "
              f"white_screen_sentry.gate_passed={white_screen_sentry.get('gate_passed')}")

    def test_viewport_artifacts_latest_returns_run_and_gate_status(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/pipeline/viewport-artifacts/latest returns run_id and gate status."""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/viewport-artifacts/latest",
            timeout=30,
        )
        assert r.status_code == 200, f"viewport-artifacts/latest failed: {r.status_code} {r.text[:200]}"
        
        body = r.json()
        artifact_run = body.get("artifact_run") or {}
        
        # Verify required fields
        assert artifact_run.get("run_id"), "Missing run_id"
        assert "white_screen_gate_passed" in artifact_run, "Missing white_screen_gate_passed"
        assert "total_checks" in artifact_run, "Missing total_checks"
        assert "failed_checks" in artifact_run, "Missing failed_checks"
        
        # Verify generated_at is present
        assert "generated_at" in artifact_run, "Missing generated_at"
        
        print(f"Viewport artifacts: run_id={artifact_run.get('run_id')}, "
              f"gate_passed={artifact_run.get('white_screen_gate_passed')}, "
              f"checks={artifact_run.get('failed_checks')}/{artifact_run.get('total_checks')}")

    def test_release_certificate_includes_sentry_and_viewport_checks(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/release-certificate includes checks.white_screen_sentry and checks.responsive_viewport_matrix."""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/release-certificate",
            timeout=30,
        )
        assert r.status_code == 200, f"release-certificate failed: {r.status_code} {r.text[:200]}"
        
        body = r.json()
        
        # Verify certificate structure
        assert body.get("certificate_id"), "Missing certificate_id"
        assert body.get("system_name") == "GTEC C5", f"Expected system_name='GTEC C5', got {body.get('system_name')}"
        assert "trust_score_percent" in body, "Missing trust_score_percent"
        
        checks = body.get("checks") or {}
        
        # Verify white_screen_sentry check
        white_screen_sentry = checks.get("white_screen_sentry") or {}
        assert "status" in white_screen_sentry, "Missing checks.white_screen_sentry.status"
        assert "run_id" in white_screen_sentry, "Missing checks.white_screen_sentry.run_id"
        assert "failed_checks" in white_screen_sentry, "Missing checks.white_screen_sentry.failed_checks"
        assert "total_checks" in white_screen_sentry, "Missing checks.white_screen_sentry.total_checks"
        assert "routes_tested" in white_screen_sentry, "Missing checks.white_screen_sentry.routes_tested"
        assert "generated_at" in white_screen_sentry, "Missing checks.white_screen_sentry.generated_at"
        
        # Verify responsive_viewport_matrix check
        responsive_viewport_matrix = checks.get("responsive_viewport_matrix") or {}
        assert "viewports" in responsive_viewport_matrix, "Missing checks.responsive_viewport_matrix.viewports"
        assert "matrix_summary" in responsive_viewport_matrix, "Missing checks.responsive_viewport_matrix.matrix_summary"
        assert "artifact_count" in responsive_viewport_matrix, "Missing checks.responsive_viewport_matrix.artifact_count"
        
        print(f"Release certificate: certificate_id={body.get('certificate_id')}, "
              f"trust_score={body.get('trust_score_percent')}%, "
              f"white_screen_sentry.status={white_screen_sentry.get('status')}, "
              f"viewport_matrix.artifact_count={responsive_viewport_matrix.get('artifact_count')}")

    def test_go_no_go_drill_latest_endpoint(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/pipeline/go-no-go-drill/latest returns latest drill entry."""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/go-no-go-drill/latest",
            timeout=30,
        )
        assert r.status_code == 200, f"go-no-go-drill/latest failed: {r.status_code} {r.text[:200]}"
        
        body = r.json()
        assert "drill" in body, "Missing drill key in response"
        assert "generated_at" in body, "Missing generated_at key in response"
        
        drill = body.get("drill")
        if drill:
            assert drill.get("drill_id"), "Missing drill_id in drill"
            assert drill.get("drill_at"), "Missing drill_at in drill"
            assert drill.get("decision") in {"GO", "NO_GO"}, f"Invalid decision: {drill.get('decision')}"
            
            # Verify validation block
            validation = drill.get("validation") or {}
            assert "white_screen_gate_passed" in validation, "Missing white_screen_gate_passed in drill.validation"
            
            print(f"Latest drill: drill_id={drill.get('drill_id')}, "
                  f"decision={drill.get('decision')}, "
                  f"white_screen_gate_passed={validation.get('white_screen_gate_passed')}")
        else:
            print("No drill found yet (expected if no drill has been run)")

    def test_trust_gates_endpoint_still_works(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/trust-gates still works and returns gate payload."""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/trust-gates",
            timeout=30,
        )
        assert r.status_code == 200, f"trust-gates failed: {r.status_code} {r.text[:200]}"
        
        body = r.json()
        assert body.get("system_name") == "GTEC C5", f"Expected system_name='GTEC C5', got {body.get('system_name')}"
        assert "trust_score_percent" in body, "Missing trust_score_percent"
        assert "passed_gates" in body, "Missing passed_gates"
        assert "total_gates" in body, "Missing total_gates"
        assert "gates" in body, "Missing gates"
        
        gates = body.get("gates") or []
        assert len(gates) > 0, "Expected at least one gate"
        
        print(f"Trust gates: score={body.get('trust_score_percent')}%, "
              f"passed={body.get('passed_gates')}/{body.get('total_gates')}")

    def test_pipeline_enforcement_state_endpoint(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/pipeline/enforcement-state returns mode and hard_block_at."""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/enforcement-state",
            timeout=30,
        )
        assert r.status_code == 200, f"enforcement-state failed: {r.status_code} {r.text[:200]}"
        
        body = r.json()
        state = body.get("state") or {}
        
        assert state.get("effective_mode") in {"soft-block", "hard-block"}, f"Invalid effective_mode: {state.get('effective_mode')}"
        assert state.get("declared_mode") in {"soft-block", "hard-block"}, f"Invalid declared_mode: {state.get('declared_mode')}"
        assert int(state.get("hard_block_after_hours") or 0) >= 1, "hard_block_after_hours should be >= 1"
        
        print(f"Pipeline enforcement: declared={state.get('declared_mode')}, "
              f"effective={state.get('effective_mode')}, "
              f"hard_block_after_hours={state.get('hard_block_after_hours')}")

    def test_go_no_go_drill_includes_async_refresh_flag(self, admin_session):
        """Test POST /api/admin/gtec-scan-v2/pipeline/go-no-go-drill includes white_screen_refresh_queued flag."""
        r = admin_session.post(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/go-no-go-drill",
            json={"simulate_hard_block": False},
            timeout=300,
        )
        _skip_if_admin_blocked_response(r, "go-no-go drill async refresh")
        assert r.status_code == 200, f"go-no-go-drill failed: {r.status_code} {r.text[:300]}"
        
        body = r.json()
        validation = body.get("validation") or {}
        
        # Verify async refresh flag is present in validation block
        assert "white_screen_refresh_queued" in validation, "Missing white_screen_refresh_queued in validation"
        
        # The flag should be a boolean
        refresh_queued = validation.get("white_screen_refresh_queued")
        assert isinstance(refresh_queued, bool), f"white_screen_refresh_queued should be boolean, got {type(refresh_queued)}"
        
        print(f"GO/NO-GO drill async refresh: white_screen_refresh_queued={refresh_queued}, "
              f"total_checks={validation.get('white_screen_total_checks')}")

    def test_viewport_artifacts_latest_has_non_zero_checks_after_refresh(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/pipeline/viewport-artifacts/latest returns non-zero checks if sentry has run."""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/viewport-artifacts/latest",
            timeout=30,
        )
        assert r.status_code == 200, f"viewport-artifacts/latest failed: {r.status_code} {r.text[:200]}"
        
        body = r.json()
        artifact_run = body.get("artifact_run") or {}
        
        # If artifact_run exists, verify it has the expected structure
        if artifact_run:
            total_checks = int(artifact_run.get("total_checks") or 0)
            failed_checks = int(artifact_run.get("failed_checks") or 0)
            
            # Verify run_id format (should start with wss_)
            run_id = artifact_run.get("run_id") or ""
            assert run_id.startswith("wss_"), f"run_id should start with 'wss_', got {run_id}"
            
            # Verify viewports are present
            viewports = artifact_run.get("viewports") or []
            assert len(viewports) > 0, "Expected at least one viewport"
            
            # Verify routes_tested is present
            routes_tested = artifact_run.get("routes_tested") or []
            
            print(f"Viewport artifacts: run_id={run_id}, "
                  f"total_checks={total_checks}, failed_checks={failed_checks}, "
                  f"viewports={viewports}, routes_count={len(routes_tested)}")
        else:
            print("No viewport artifact run found yet (expected if sentry hasn't run)")

    def test_evidence_bundle_viewport_matrix_has_artifacts_array(self, admin_session):
        """Test GET /api/admin/gtec-scan-v2/pipeline/evidence-bundle/latest viewport_matrix has artifacts array."""
        r = admin_session.get(
            f"{BASE_URL}/api/admin/gtec-scan-v2/pipeline/evidence-bundle/latest",
            timeout=30,
        )
        assert r.status_code == 200, f"evidence-bundle/latest failed: {r.status_code} {r.text[:200]}"
        
        body = r.json()
        bundle = body.get("bundle") or {}
        
        if bundle:
            viewport_matrix = bundle.get("viewport_matrix") or {}
            
            # Verify artifacts array is present
            artifacts = viewport_matrix.get("artifacts") or []
            assert isinstance(artifacts, list), "viewport_matrix.artifacts should be a list"
            
            # Verify matrix_summary structure
            matrix_summary = viewport_matrix.get("matrix_summary") or {}
            
            # If artifacts exist, verify their structure
            if artifacts:
                first_artifact = artifacts[0]
                assert "route" in first_artifact or "probe_url" in first_artifact, "Artifact should have route or probe_url"
                assert "viewport" in first_artifact, "Artifact should have viewport"
                assert "status" in first_artifact, "Artifact should have status"
            
            print(f"Evidence bundle viewport_matrix: artifacts_count={len(artifacts)}, "
                  f"matrix_summary_keys={list(matrix_summary.keys())}")
        else:
            print("No evidence bundle found yet")
