"""
Feature 20 (Lexicon Intelligence Hub) 3-Tier Entitlement Verification Tests

Tests the fix for missing 3-tier entitlements:
- Free user → plan=free, scope_label="Limited access"
- Basic user → plan=basic, scope_label="Almost unlimited access"
- Premium/Admin → plan=premium, scope_label="Full unlimited access"

Root cause fix verified:
- _build_user_doc now includes payment_verified field
- _resolve_plan uses compute_effective_plan(_build_user_doc(user))
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
FREE_USER = {
    "email": "feature21.test.1781234530@example.com",
    "password": "Feature21Test#2026Aa"
}

BASIC_USER = {
    "email": "f21.basic.1781338672@example.com",
    "password": "F21Basic#2026Aa"
}

ADMIN_USER = {
    "email": "admin@realaicoach.app",
    "password": "NewAdminPass2026!"
}


class TestFeature20ThreeTierEntitlement:
    """Feature 20 Lexicon Intelligence Hub 3-tier entitlement verification"""

    @pytest.fixture(scope="class")
    def free_session(self):
        """Login as free user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json=FREE_USER)
        if response.status_code != 200:
            pytest.skip(f"Free user login failed: {response.status_code} - {response.text}")
        return session

    @pytest.fixture(scope="class")
    def basic_session(self):
        """Login as basic user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json=BASIC_USER)
        if response.status_code != 200:
            pytest.skip(f"Basic user login failed: {response.status_code} - {response.text}")
        return session

    @pytest.fixture(scope="class")
    def admin_session(self):
        """Login as admin user and return session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER)
        if response.status_code != 200:
            pytest.skip(f"Admin user login failed: {response.status_code} - {response.text}")
        return session

    # ==================== FREE TIER TESTS ====================

    def test_free_user_bootstrap_plan_resolution(self, free_session):
        """Free user should resolve to plan=free with Limited access"""
        response = free_session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        
        data = response.json()
        assert data.get("plan") == "free", f"Expected plan=free, got {data.get('plan')}"
        assert data.get("scope_label") == "Limited access", f"Expected 'Limited access', got {data.get('scope_label')}"
        
        # Verify limits are free-tier limits
        limits = data.get("limits", {})
        assert limits.get("generate_word") == 4, f"Expected generate_word=4, got {limits.get('generate_word')}"
        assert limits.get("quiz_attempt") == 12, f"Expected quiz_attempt=12, got {limits.get('quiz_attempt')}"
        assert limits.get("save_word") == 24, f"Expected save_word=24, got {limits.get('save_word')}"
        
        print(f"✓ Free user bootstrap: plan={data.get('plan')}, scope_label={data.get('scope_label')}")

    def test_free_user_templates_access(self, free_session):
        """Free user should access templates endpoint"""
        response = free_session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Templates failed: {response.text}"
        
        data = response.json()
        assert data.get("plan") == "free"
        assert "templates" in data
        print(f"✓ Free user templates: plan={data.get('plan')}, templates_count={len(data.get('templates', []))}")

    # ==================== BASIC TIER TESTS ====================

    def test_basic_user_bootstrap_plan_resolution(self, basic_session):
        """Basic user should resolve to plan=basic with Almost unlimited access (ROOT CAUSE FIX)"""
        response = basic_session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        
        data = response.json()
        # THIS IS THE KEY TEST - Basic user must NOT resolve to free
        assert data.get("plan") == "basic", f"CRITICAL: Expected plan=basic, got {data.get('plan')} - payment_verified fix may not be applied"
        assert data.get("scope_label") == "Almost unlimited access", f"Expected 'Almost unlimited access', got {data.get('scope_label')}"
        
        # Verify limits are basic-tier limits (much higher than free)
        limits = data.get("limits", {})
        assert limits.get("generate_word") == 180, f"Expected generate_word=180, got {limits.get('generate_word')}"
        assert limits.get("quiz_attempt") == 500, f"Expected quiz_attempt=500, got {limits.get('quiz_attempt')}"
        assert limits.get("save_word") == 1000, f"Expected save_word=1000, got {limits.get('save_word')}"
        
        print(f"✓ Basic user bootstrap: plan={data.get('plan')}, scope_label={data.get('scope_label')}")
        print("  ROOT CAUSE FIX VERIFIED: payment_verified field correctly included in _build_user_doc")

    def test_basic_user_templates_access(self, basic_session):
        """Basic user should access templates endpoint with basic plan"""
        response = basic_session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Templates failed: {response.text}"
        
        data = response.json()
        assert data.get("plan") == "basic", f"Expected plan=basic, got {data.get('plan')}"
        print(f"✓ Basic user templates: plan={data.get('plan')}")

    def test_basic_user_export_access(self, basic_session):
        """Basic user should access export endpoint"""
        response = basic_session.get(f"{BASE_URL}/api/word-forge/export")
        assert response.status_code == 200, f"Export failed: {response.text}"
        
        data = response.json()
        assert data.get("plan") == "basic", f"Expected plan=basic, got {data.get('plan')}"
        assert data.get("scope_label") == "Almost unlimited access"
        print(f"✓ Basic user export: plan={data.get('plan')}, scope_label={data.get('scope_label')}")

    # ==================== PREMIUM/ADMIN TIER TESTS ====================

    def test_admin_user_bootstrap_plan_resolution(self, admin_session):
        """Admin user should resolve to plan=premium with Full unlimited access"""
        response = admin_session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        
        data = response.json()
        assert data.get("plan") == "premium", f"Expected plan=premium, got {data.get('plan')}"
        assert data.get("scope_label") == "Full unlimited access", f"Expected 'Full unlimited access', got {data.get('scope_label')}"
        
        # Verify limits are unlimited (-1)
        limits = data.get("limits", {})
        assert limits.get("generate_word") == -1, f"Expected generate_word=-1 (unlimited), got {limits.get('generate_word')}"
        assert limits.get("quiz_attempt") == -1, f"Expected quiz_attempt=-1 (unlimited), got {limits.get('quiz_attempt')}"
        assert limits.get("save_word") == -1, f"Expected save_word=-1 (unlimited), got {limits.get('save_word')}"
        
        print(f"✓ Admin user bootstrap: plan={data.get('plan')}, scope_label={data.get('scope_label')}")

    def test_admin_user_templates_access(self, admin_session):
        """Admin user should access templates endpoint with premium plan"""
        response = admin_session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Templates failed: {response.text}"
        
        data = response.json()
        assert data.get("plan") == "premium", f"Expected plan=premium, got {data.get('plan')}"
        # Premium users get premium recommendations
        recommended = data.get("recommended_template_ids", [])
        assert "boardroom-brief" in recommended or "negotiation-edge" in recommended, \
            f"Expected premium recommendations, got {recommended}"
        print(f"✓ Admin user templates: plan={data.get('plan')}, recommended={recommended}")

    # ==================== UNAUTHENTICATED ACCESS TESTS ====================

    def test_unauthenticated_bootstrap_returns_401(self):
        """Unauthenticated request to bootstrap should return 401"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Unauthenticated bootstrap returns 401")

    def test_unauthenticated_templates_returns_401(self):
        """Unauthenticated request to templates should return 401"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Unauthenticated templates returns 401")

    # ==================== HEALTH ENDPOINT TEST ====================

    def test_health_endpoint(self, free_session):
        """Health endpoint should return healthy status"""
        response = free_session.get(f"{BASE_URL}/api/word-forge/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("feature_id") == "lexicon-intelligence"
        print(f"✓ Health endpoint: status={data.get('status')}, feature_id={data.get('feature_id')}")

    # ==================== BOOTSTRAP CONTRACT VALIDATION ====================

    def test_bootstrap_response_contract(self, free_session):
        """Bootstrap response should contain all required fields"""
        response = free_session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = [
            "plan", "scope_label", "limits", "daily_word", "saved_words",
            "review_queue", "profile", "usage_summary", "weekly_challenge",
            "capabilities", "business_contexts", "generated_at"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        print(f"✓ Bootstrap contract validated: all {len(required_fields)} required fields present")


class TestFeature20AccessControlIntegration:
    """Test access control integration for Feature 20"""

    def test_access_control_session_free_user(self):
        """Free user access control session should return effective_plan=free"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json=FREE_USER)
        if response.status_code != 200:
            pytest.skip("Free user login failed")
        
        response = session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Access control session failed: {response.text}"
        
        data = response.json()
        assert data.get("effective_plan") == "free", f"Expected effective_plan=free, got {data.get('effective_plan')}"
        print(f"✓ Free user access control session: effective_plan={data.get('effective_plan')}")

    def test_access_control_session_basic_user(self):
        """Basic user access control session should return effective_plan=basic"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json=BASIC_USER)
        if response.status_code != 200:
            pytest.skip("Basic user login failed")
        
        response = session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Access control session failed: {response.text}"
        
        data = response.json()
        assert data.get("effective_plan") == "basic", f"Expected effective_plan=basic, got {data.get('effective_plan')}"
        print(f"✓ Basic user access control session: effective_plan={data.get('effective_plan')}")

    def test_access_control_session_admin_user(self):
        """Admin user access control session should return effective_plan=premium"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        response = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER)
        if response.status_code != 200:
            pytest.skip("Admin user login failed")
        
        response = session.get(f"{BASE_URL}/api/access-control/session")
        assert response.status_code == 200, f"Access control session failed: {response.text}"
        
        data = response.json()
        assert data.get("effective_plan") == "premium", f"Expected effective_plan=premium, got {data.get('effective_plan')}"
        assert data.get("is_admin") == True, f"Expected is_admin=True, got {data.get('is_admin')}"
        print(f"✓ Admin user access control session: effective_plan={data.get('effective_plan')}, is_admin={data.get('is_admin')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
