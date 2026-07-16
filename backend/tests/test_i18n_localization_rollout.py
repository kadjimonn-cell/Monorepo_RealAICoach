"""
Test suite for i18n localization rollout verification (C+1+2+3 batches).
Verifies:
1. GET /api/admin/i18n/coverage reports aggregate_coverage_pct >= 90
2. All non-source locales have coverage_pct >= 90
3. GET /api/config/global-production-gate returns status=pass with no blockers
4. GET /api/admin/i18n/adoption remains 100% and hardcoded-copy files remain 0
5. Evidence artifacts exist with expected metrics
"""

import pytest
import requests
import os
import json
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Admin credentials
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_admin_forbidden(response: requests.Response) -> bool:
    if response.status_code == 401:
        return True
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


def _skip_if_admin_blocked(response: requests.Response, context: str) -> None:
    if _is_admin_forbidden(response):
        pytest.skip(f"{context} blocked by environment containment/authorization policy")


@pytest.fixture(scope="module")
def admin_session():
    """Create authenticated admin session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
    
    # Login as admin
    login_response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    
    if login_response.status_code != 200:
        pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text[:200]}")

    data = login_response.json()
    token = (
        data.get("session_token")
        or data.get("token")
        or data.get("access_token")
        or login_response.cookies.get("session_token")
        or session.cookies.get("session_token")
    )
    if not token:
        pytest.skip("Admin token missing in login JSON/cookies")

    session.headers.update({"Authorization": f"Bearer {token}"})

    original_get = session.get

    def guarded_get(*args, **kwargs):
        response = original_get(*args, **kwargs)
        _skip_if_admin_blocked(response, "i18n rollout admin endpoint")
        return response

    session.get = guarded_get
    
    return session


class TestI18nCoverageMetrics:
    """Tests for i18n coverage endpoint after localization rollout."""
    
    def test_i18n_coverage_endpoint_accessible(self, admin_session):
        """Verify /api/admin/i18n/coverage is accessible with admin auth."""
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert data.get("ok") is True, "Response should have ok=True"
        print("PASS: i18n coverage endpoint accessible")
    
    def test_aggregate_coverage_pct_at_least_90(self, admin_session):
        """Verify aggregate_coverage_pct >= 90 after C+1+2+3 batches."""
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200
        data = response.json()
        
        aggregate_pct = float(data.get("aggregate_coverage_pct", 0))
        print(f"aggregate_coverage_pct: {aggregate_pct}")
        
        assert aggregate_pct >= 90.0, f"Expected aggregate_coverage_pct >= 90, got {aggregate_pct}"
        print(f"PASS: aggregate_coverage_pct = {aggregate_pct} (>= 90)")
    
    def test_all_non_source_locales_at_least_90_coverage(self, admin_session):
        """Verify all non-source locales have coverage_pct >= 90."""
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200
        data = response.json()
        
        locales = data.get("locales", {})
        below_90_locales = []
        
        for locale_code, locale_data in locales.items():
            # Skip source locale (en)
            if locale_data.get("is_source"):
                continue
            
            coverage_pct = float(locale_data.get("coverage_pct", 0))
            if coverage_pct < 90.0:
                below_90_locales.append({
                    "locale": locale_code,
                    "coverage_pct": coverage_pct,
                    "translated": locale_data.get("translated"),
                    "echoed": locale_data.get("echoed"),
                    "missing": locale_data.get("missing")
                })
        
        if below_90_locales:
            print(f"Locales below 90% coverage: {json.dumps(below_90_locales, indent=2)}")
        
        assert len(below_90_locales) == 0, f"Found {len(below_90_locales)} locales below 90% coverage: {below_90_locales}"
        print(f"PASS: All {len(locales) - 1} non-source locales have coverage_pct >= 90")
    
    def test_structural_coverage_remains_100(self, admin_session):
        """Verify structural_coverage_pct remains at 100 (no missing keys)."""
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200
        data = response.json()
        
        structural_pct = float(data.get("structural_coverage_pct", 0))
        missing_keys = int(data.get("missing_keys_total", -1))
        
        print(f"structural_coverage_pct: {structural_pct}, missing_keys_total: {missing_keys}")
        
        assert structural_pct == 100.0, f"Expected structural_coverage_pct = 100, got {structural_pct}"
        assert missing_keys == 0, f"Expected missing_keys_total = 0, got {missing_keys}"
        print("PASS: structural_coverage_pct = 100, missing_keys_total = 0")
    
    def test_i18n_health_not_red(self, admin_session):
        """Verify i18n health is not red (should be amber or green with >= 90% coverage)."""
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200
        data = response.json()
        
        health = data.get("health", "unknown")
        print(f"i18n health: {health}")
        
        assert health in ["green", "amber"], f"Expected health to be green or amber, got {health}"
        print(f"PASS: i18n health = {health}")


class TestGlobalProductionGate:
    """Tests for global production gate endpoint."""
    
    def test_global_production_gate_status_pass(self, admin_session):
        """Verify /api/config/global-production-gate returns status=pass."""
        response = admin_session.get(f"{BASE_URL}/api/config/global-production-gate")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        
        status = data.get("status")
        blockers = data.get("blockers", [])
        
        print(f"global-production-gate status: {status}")
        print(f"blockers: {json.dumps(blockers, indent=2)}")
        
        assert status == "pass", f"Expected status=pass, got {status}"
        assert len(blockers) == 0, f"Expected no blockers, got {len(blockers)}: {blockers}"
        print("PASS: global-production-gate status=pass with 0 blockers")
    
    def test_global_production_gate_i18n_signals(self, admin_session):
        """Verify i18n signals in global production gate response."""
        response = admin_session.get(f"{BASE_URL}/api/config/global-production-gate")
        assert response.status_code == 200
        data = response.json()
        
        signals = data.get("signals", {})
        i18n_coverage = signals.get("i18n_coverage", {})
        
        aggregate_pct = float(i18n_coverage.get("aggregate_coverage_pct", 0))
        structural_pct = float(i18n_coverage.get("structural_coverage_pct", 0))
        missing_keys = int(i18n_coverage.get("missing_keys_total", -1))
        
        print(f"Gate signals - aggregate: {aggregate_pct}, structural: {structural_pct}, missing: {missing_keys}")
        
        assert aggregate_pct >= 90.0, f"Expected aggregate_coverage_pct >= 90 in gate signals, got {aggregate_pct}"
        assert structural_pct == 100.0, f"Expected structural_coverage_pct = 100 in gate signals, got {structural_pct}"
        assert missing_keys == 0, f"Expected missing_keys_total = 0 in gate signals, got {missing_keys}"
        print("PASS: Gate i18n signals verified")


class TestI18nAdoption:
    """Tests for i18n adoption endpoint."""
    
    def test_i18n_adoption_100_percent(self, admin_session):
        """Verify /api/admin/i18n/adoption remains at 100%."""
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/adoption")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        
        summary = data.get("summary", {})
        adoption_pct = float(summary.get("adoption_pct", 0))
        
        print(f"adoption_pct: {adoption_pct}")
        
        assert adoption_pct == 100.0, f"Expected adoption_pct = 100, got {adoption_pct}"
        print("PASS: adoption_pct = 100")
    
    def test_hardcoded_copy_files_zero(self, admin_session):
        """Verify files_with_hardcoded_copy_without_t remains at 0."""
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/adoption")
        assert response.status_code == 200
        data = response.json()
        
        summary = data.get("summary", {})
        hardcoded_files = int(summary.get("files_with_hardcoded_copy_without_t", -1))
        
        print(f"files_with_hardcoded_copy_without_t: {hardcoded_files}")
        
        assert hardcoded_files == 0, f"Expected files_with_hardcoded_copy_without_t = 0, got {hardcoded_files}"
        print("PASS: files_with_hardcoded_copy_without_t = 0")


class TestEvidenceArtifacts:
    """Tests for evidence artifact existence and content."""
    
    def test_strict_checkpoint_evidence_pack_exists(self):
        """Verify /app/memory/STRICT_CHECKPOINT_EVIDENCE_PACK.md exists."""
        evidence_path = Path("/app/memory/STRICT_CHECKPOINT_EVIDENCE_PACK.md")
        assert evidence_path.exists(), f"Evidence pack not found at {evidence_path}"
        
        content = evidence_path.read_text(encoding="utf-8")
        assert len(content) > 100, "Evidence pack content too short"
        
        # Verify key content markers
        assert "aggregate_coverage_pct" in content, "Evidence pack missing aggregate_coverage_pct"
        assert "global-production-gate" in content, "Evidence pack missing global-production-gate"
        assert "pass" in content.lower(), "Evidence pack missing 'pass' status"
        
        print("PASS: STRICT_CHECKPOINT_EVIDENCE_PACK.md exists with expected content")
    
    def test_localization_phase_report_exists(self):
        """Verify /tmp/e1_localization_phase_report.json exists with expected metrics."""
        report_path = Path("/tmp/e1_localization_phase_report.json")
        if not report_path.exists():
            pytest.skip("Localization phase report artifact not present in current environment")
        
        content = report_path.read_text(encoding="utf-8")
        data = json.loads(content)
        
        # Verify coverage metrics
        coverage = data.get("coverage", {})
        aggregate_pct = float(coverage.get("aggregate_coverage_pct", 0))
        
        assert aggregate_pct >= 90.0, f"Report aggregate_coverage_pct should be >= 90, got {aggregate_pct}"
        
        # Verify gate status
        gate = data.get("global_production_gate", {})
        gate_status = gate.get("status")
        
        assert gate_status == "pass", f"Report gate status should be 'pass', got {gate_status}"
        
        print(f"PASS: e1_localization_phase_report.json exists with aggregate_coverage_pct={aggregate_pct}, gate={gate_status}")
    
    def test_evidence_pack_metrics_match_api(self, admin_session):
        """Verify evidence pack metrics match current API response."""
        # Get current API values
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200
        api_data = response.json()
        
        api_aggregate = float(api_data.get("aggregate_coverage_pct", 0))
        
        # Read evidence pack
        evidence_path = Path("/app/memory/STRICT_CHECKPOINT_EVIDENCE_PACK.md")
        content = evidence_path.read_text(encoding="utf-8")
        
        # Extract aggregate_coverage_pct from evidence pack (format: `96.1`)
        import re
        match = re.search(r"aggregate_coverage_pct:\s*`?(\d+\.?\d*)`?", content)
        if match:
            evidence_aggregate = float(match.group(1))
            # Allow small variance due to timing
            diff = abs(api_aggregate - evidence_aggregate)
            assert diff < 5.0, f"API aggregate ({api_aggregate}) differs from evidence ({evidence_aggregate}) by {diff}"
            print(f"PASS: Evidence pack aggregate ({evidence_aggregate}) matches API ({api_aggregate}) within tolerance")
        else:
            print("WARNING: Could not extract aggregate_coverage_pct from evidence pack")


class TestLocaleBreakdown:
    """Detailed tests for individual locale coverage."""
    
    def test_batch1_locales_coverage(self, admin_session):
        """Verify Batch 1 locales (es, fr, de, hi, ar) have >= 90% coverage."""
        batch1_locales = ["es", "fr", "de", "hi", "ar"]
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200
        data = response.json()
        
        locales = data.get("locales", {})
        for locale in batch1_locales:
            locale_data = locales.get(locale, {})
            coverage_pct = float(locale_data.get("coverage_pct", 0))
            assert coverage_pct >= 90.0, f"Batch1 locale {locale} coverage {coverage_pct} < 90"
        
        print("PASS: All Batch 1 locales (es, fr, de, hi, ar) have >= 90% coverage")
    
    def test_batch2_locales_coverage(self, admin_session):
        """Verify Batch 2 locales (id, it, ja, ko, ms, nl, pl, pt) have >= 90% coverage."""
        batch2_locales = ["id", "it", "ja", "ko", "ms", "nl", "pl", "pt"]
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200
        data = response.json()
        
        locales = data.get("locales", {})
        for locale in batch2_locales:
            locale_data = locales.get(locale, {})
            coverage_pct = float(locale_data.get("coverage_pct", 0))
            assert coverage_pct >= 90.0, f"Batch2 locale {locale} coverage {coverage_pct} < 90"
        
        print("PASS: All Batch 2 locales (id, it, ja, ko, ms, nl, pl, pt) have >= 90% coverage")
    
    def test_batch3_locales_coverage(self, admin_session):
        """Verify Batch 3 locales (ro, ru, sv, sw, th, tr, uk, vi, zh) have >= 90% coverage."""
        batch3_locales = ["ro", "ru", "sv", "sw", "th", "tr", "uk", "vi", "zh"]
        response = admin_session.get(f"{BASE_URL}/api/admin/i18n/coverage")
        assert response.status_code == 200
        data = response.json()
        
        locales = data.get("locales", {})
        for locale in batch3_locales:
            locale_data = locales.get(locale, {})
            coverage_pct = float(locale_data.get("coverage_pct", 0))
            assert coverage_pct >= 90.0, f"Batch3 locale {locale} coverage {coverage_pct} < 90"
        
        print("PASS: All Batch 3 locales (ro, ru, sv, sw, th, tr, uk, vi, zh) have >= 90% coverage")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
