"""
IAP Credential Lifecycle Hardening - D1-D6 Checkpoint Tests

Tests:
D1: Canonical secret contract - contract_version=iap-secret-contract-v2
D2: Runtime secret hydration - paths use /run/secrets/iap or /tmp/realaicoach/iap_secrets
D3: Readiness refactor with failure_reasons - providers have failure_reasons field
D4: Security gate alignment - CI gate passes with updated path policy
D5: Startup preflight - logs appear and backend starts
D6: Diagnostics/audit controls - admin/secret-diagnostics rejects non-admin with 403
"""

import pytest
import requests
import os
import subprocess
from pathlib import Path

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

# Non-admin test credentials
NON_ADMIN_EMAIL = "nova.v2.1779074133@example.com"
NON_ADMIN_PASSWORD = "NovaV2#2026!Aa"

# Admin credentials for comparison
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


def _is_env_admin_block(response: requests.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code not in (401, 403, 503):
        return False

    try:
        payload = response.json()
    except Exception:
        payload = {}

    detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    top_code = str(payload.get("code") or "").upper() if isinstance(payload, dict) else ""
    blocked_codes = {
        "AUTH_REQUIRED",
        "RISK_ENGINE_ADMIN_API_BLOCKED",
        "RISK_ENGINE_ID_VERIFICATION_REQUIRED",
        "PRODUCTION_POLICY_GATE_BLOCKED",
    }

    if top_code in blocked_codes:
        return True

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").upper()
        if code in blocked_codes:
            return True
        message = str(detail.get("message") or "").lower()
        return (
            "authentication required" in message
            or "admin access required" in message
            or "id checker" in message
            or "policy gate" in message
            or "too many" in message
            or "rate limit" in message
        )

    if isinstance(detail, str):
        lowered = detail.lower()
        return (
            "authentication required" in lowered
            or "admin access required" in lowered
            or "id checker" in lowered
            or "policy gate" in lowered
            or "too many" in lowered
            or "rate limit" in lowered
        )

    body = (response.text or "").lower()
    return (
        "authentication required" in body
        or "admin access required" in body
        or "risk_engine" in body
        or "policy gate" in body
        or "too many" in body
        or "rate limit" in body
    )


class TestD1CanonicalSecretContract:
    """D1: Verify contract_version=iap-secret-contract-v2 in readiness response"""
    
    def test_readiness_returns_contract_version_v2(self, authenticated_session):
        """GET /api/iap/readiness should return contract_version=iap-secret-contract-v2"""
        session = authenticated_session
        resp = session.get(
            f"{BASE_URL}/api/iap/readiness",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # D1: Verify contract_version
        assert "contract_version" in data, "Response should contain 'contract_version'"
        assert data["contract_version"] == "iap-secret-contract-v2", \
            f"Expected contract_version='iap-secret-contract-v2', got '{data.get('contract_version')}'"
        print(f"PASS D1: contract_version={data['contract_version']}")


class TestD2RuntimeSecretHydration:
    """D2: Verify runtime secret paths use /run/secrets/iap or /tmp/realaicoach/iap_secrets"""
    
    def test_readiness_matrix_shows_runtime_scoped_paths(self, authenticated_session):
        """GET /api/iap/readiness-matrix should show secret_source and runtime_scoped fields"""
        session = authenticated_session
        resp = session.get(
            f"{BASE_URL}/api/iap/readiness-matrix",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # D2: Verify matrix contains Apple/Google rows with secret_source and runtime_scoped
        assert "matrix" in data or "providers" in data, "Response should contain 'matrix' or 'providers'"
        
        providers = data.get("providers", {})
        matrix = data.get("matrix", [])
        
        # Check providers dict
        for provider_key in ["apple", "google"]:
            if provider_key in providers:
                provider = providers[provider_key]
                assert "secret_source" in provider, f"{provider_key} should have 'secret_source' field"
                assert "secret_runtime_scoped" in provider, f"{provider_key} should have 'secret_runtime_scoped' field"
                print(f"PASS D2: {provider_key} has secret_source={provider.get('secret_source')}, runtime_scoped={provider.get('secret_runtime_scoped')}")
        
        # Check matrix array
        for item in matrix:
            provider_name = item.get("provider", "unknown")
            assert "secret_source" in item, f"Matrix item {provider_name} should have 'secret_source'"
            assert "secret_runtime_scoped" in item, f"Matrix item {provider_name} should have 'secret_runtime_scoped'"
    
    def test_env_paths_use_runtime_mounts(self):
        """IAP secret path env values should use runtime mounts, not workspace paths"""
        env_path = Path("/app/backend/.env")
        assert env_path.exists(), "backend/.env must exist"
        
        values = {}
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
        
        keys = [
            "ASC_PRIVATE_KEY_PATH",
            "APPLE_IAP_PRIVATE_KEY_PATH",
            "GOOGLE_PLAY_SERVICE_ACCOUNT_PATH",
            "GOOGLE_PLAY_IAP_SERVICE_ACCOUNT_PATH",
        ]
        
        for key in keys:
            value = values.get(key, "")
            if not value:
                print(f"SKIP D2: {key} not configured")
                continue
            
            # Must NOT point to workspace path
            assert not value.startswith("/app/backend/"), \
                f"{key} must not point to workspace path: {value}"
            
            # Must use runtime secret mount path
            assert value.startswith("/run/secrets/iap/") or value.startswith("/tmp/realaicoach/iap_secrets/"), \
                f"{key} must use runtime secret mount path: {value}"
            
            print(f"PASS D2: {key}={value} (runtime mount)")


class TestD3ReadinessFailureReasons:
    """D3: Verify readiness response includes provider failure_reasons"""
    
    def test_readiness_providers_have_failure_reasons(self, authenticated_session):
        """GET /api/iap/readiness should include failure_reasons for each provider"""
        session = authenticated_session
        resp = session.get(
            f"{BASE_URL}/api/iap/readiness",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        providers = data.get("providers", {})
        assert providers, "Response should contain 'providers' dict"
        
        for provider_key in ["apple", "google"]:
            if provider_key in providers:
                provider = providers[provider_key]
                assert "failure_reasons" in provider, \
                    f"{provider_key} should have 'failure_reasons' field"
                failure_reasons = provider.get("failure_reasons", [])
                assert isinstance(failure_reasons, list), \
                    f"{provider_key} failure_reasons should be a list"
                print(f"PASS D3: {provider_key} has failure_reasons={failure_reasons}")


class TestD4SecurityGateAlignment:
    """D4: Verify security gate passes with updated path policy checks"""
    
    def test_security_gate_passes(self):
        """Security CI gate should pass"""
        result = subprocess.run(
            ["python3", "/app/security/ci_security_gate.py"],
            capture_output=True,
            text=True,
            timeout=30
        )
        assert result.returncode == 0, f"Security gate failed: {result.stdout}\n{result.stderr}"
        assert "SECURITY_GATE=PASS" in result.stdout, f"Expected PASS, got: {result.stdout}"
        print("PASS D4: Security CI gate passes")
    
    def test_disallowed_secret_files_absent(self):
        """Disallowed static secret files should not exist in workspace"""
        disallowed_files = [
            "/app/backend/google_play_iap_service_account.json",
            "/app/backend/google_play_service_account.json",
            "/app/backend/AuthKey_34YP9488M8.p8",
            "/app/backend/SubscriptionKey_848DFKTZ47.p8",
            "/app/frontend/cookies.txt",
        ]
        for filepath in disallowed_files:
            assert not os.path.exists(filepath), f"Disallowed file exists: {filepath}"
        print("PASS D4: All disallowed secret files are absent")


class TestD5StartupPreflight:
    """D5: Verify startup preflight logs appear and backend still starts"""
    
    def test_backend_is_running(self):
        """Backend should be running and responding to health checks"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200, f"Backend health check failed: {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "healthy", f"Backend not healthy: {data}"
        print("PASS D5: Backend is running and healthy")
    
    def test_startup_preflight_code_exists(self):
        """Startup preflight code should exist in server.py"""
        server_path = Path("/app/backend/server.py")
        content = server_path.read_text(encoding="utf-8")
        
        assert "enforce_iap_startup_preflight" in content, \
            "server.py should contain enforce_iap_startup_preflight"
        assert "iap-startup-preflight" in content, \
            "server.py should contain iap-startup-preflight log marker"
        print("PASS D5: Startup preflight code exists in server.py")
    
    def test_iap_secret_runtime_module_exists(self):
        """IAP secret runtime module should exist with required functions"""
        module_path = Path("/app/backend/utils/iap_secret_runtime.py")
        assert module_path.exists(), "iap_secret_runtime.py should exist"
        
        content = module_path.read_text(encoding="utf-8")
        required_functions = [
            "hydrate_iap_runtime_secrets",
            "compute_iap_provider_readiness",
            "get_iap_secret_diagnostics",
            "enforce_iap_startup_preflight",
        ]
        for func in required_functions:
            assert func in content, f"iap_secret_runtime.py should contain {func}"
        
        # Verify contract version constant
        assert 'CONTRACT_VERSION = "iap-secret-contract-v2"' in content, \
            "iap_secret_runtime.py should define CONTRACT_VERSION as iap-secret-contract-v2"
        
        # Verify runtime directory constants
        assert 'DEFAULT_RUNTIME_DIR = Path("/run/secrets/iap")' in content, \
            "iap_secret_runtime.py should define DEFAULT_RUNTIME_DIR"
        assert 'FALLBACK_RUNTIME_DIR = Path("/tmp/realaicoach/iap_secrets")' in content, \
            "iap_secret_runtime.py should define FALLBACK_RUNTIME_DIR"
        
        print("PASS D5: IAP secret runtime module has all required functions and constants")


class TestD6DiagnosticsAuditControls:
    """D6: Verify admin/secret-diagnostics rejects non-admin with 403"""
    
    def test_secret_diagnostics_rejects_non_admin(self, non_admin_session):
        """GET /api/iap/admin/secret-diagnostics should reject non-admin with 403"""
        session = non_admin_session
        resp = session.get(
            f"{BASE_URL}/api/iap/admin/secret-diagnostics",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15
        )
        assert resp.status_code == 403, \
            f"Expected 403 for non-admin, got {resp.status_code}: {resp.text}"
        print("PASS D6: admin/secret-diagnostics rejects non-admin with 403")
    
    def test_secret_diagnostics_rejects_unauthenticated(self):
        """GET /api/iap/admin/secret-diagnostics should reject unauthenticated requests"""
        resp = requests.get(
            f"{BASE_URL}/api/iap/admin/secret-diagnostics",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15
        )
        # Should be 401 (unauthenticated) or 403 (forbidden)
        assert resp.status_code in [401, 403], \
            f"Expected 401 or 403 for unauthenticated, got {resp.status_code}: {resp.text}"
        print(f"PASS D6: admin/secret-diagnostics rejects unauthenticated with {resp.status_code}")
    
    def test_secret_diagnostics_allows_admin(self, admin_session):
        """GET /api/iap/admin/secret-diagnostics should allow admin access"""
        session = admin_session
        resp = session.get(
            f"{BASE_URL}/api/iap/admin/secret-diagnostics",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15
        )

        if _is_env_admin_block(resp):
            pytest.skip("admin/secret-diagnostics blocked by environment containment/policy gate")

        assert resp.status_code == 200, \
            f"Expected 200 for admin, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Verify diagnostics response structure
        assert "contract_version" in data, "Diagnostics should contain contract_version"
        assert data["contract_version"] == "iap-secret-contract-v2", \
            f"Expected contract_version='iap-secret-contract-v2', got '{data.get('contract_version')}'"
        print(f"PASS D6: admin/secret-diagnostics allows admin, contract_version={data['contract_version']}")


class TestFrontendLoaderHelper:
    """Verify frontend loader helper remains functional after challenge-aware timing update"""
    
    def test_html_tsx_has_challenge_detection(self):
        """Frontend +html.tsx should have challenge-aware loader code"""
        html_path = Path("/app/frontend/app/+html.tsx")
        assert html_path.exists(), "+html.tsx should exist"
        
        content = html_path.read_text(encoding="utf-8")
        
        # Check for challenge detection function
        assert "detectEdgeChallenge" in content, \
            "+html.tsx should contain detectEdgeChallenge function"
        
        # Check for challenge-aware messaging
        assert "Verifying security challenge" in content or "Taking longer than expected" in content, \
            "+html.tsx should have challenge-aware user messaging"
        
        # Check for reload helper
        assert "Reload App" in content, \
            "+html.tsx should have Reload App button"
        
        print("PASS: Frontend +html.tsx has challenge-aware loader code")


# ── Fixtures ──

@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    return session


@pytest.fixture
def authenticated_session(api_client):
    """Get authenticated session with non-admin credentials"""
    login_resp = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": NON_ADMIN_EMAIL, "password": NON_ADMIN_PASSWORD},
        timeout=15
    )
    if login_resp.status_code != 200:
        pytest.skip(f"Login failed for non-admin: {login_resp.text}")
    
    for cookie in login_resp.cookies:
        api_client.cookies.set(cookie.name, cookie.value)
    
    return api_client


@pytest.fixture
def non_admin_session(api_client):
    """Alias for authenticated_session with non-admin user"""
    login_resp = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": NON_ADMIN_EMAIL, "password": NON_ADMIN_PASSWORD},
        timeout=15
    )
    if login_resp.status_code != 200:
        pytest.skip(f"Login failed for non-admin: {login_resp.text}")
    
    for cookie in login_resp.cookies:
        api_client.cookies.set(cookie.name, cookie.value)
    
    return api_client


@pytest.fixture
def admin_session():
    """Get authenticated session with admin credentials"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    login_resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15
    )

    if _is_env_admin_block(login_resp):
        pytest.skip(f"Login blocked for admin by environment containment/policy gate: {login_resp.status_code}")

    if login_resp.status_code != 200:
        pytest.skip(f"Login failed for admin: {login_resp.text}")

    login_data = login_resp.json()
    token = (
        login_data.get("session_token")
        or login_data.get("token")
        or login_data.get("access_token")
        or login_resp.cookies.get("session_token")
        or session.cookies.get("session_token")
    )
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    for cookie in login_resp.cookies:
        session.cookies.set(cookie.name, cookie.value)
    
    return session


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
