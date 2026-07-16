"""
Feature 20: Lexicon Intelligence Hub - Completion Status Tests
Tests for /api/word-forge/* endpoints

Test credentials:
- Admin: admin@realaicoach.app / NewAdminPass2026!
- Free: feature21.test.1781234530@example.com / Feature21Test#2026Aa
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestFeature20Health:
    """Health endpoint tests - may require auth due to middleware"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as admin for health check (middleware may require auth)"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@realaicoach.app",
                "password": "NewAdminPass2026!"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code}")
    
    def test_health_endpoint_returns_200(self):
        """A: Health endpoint should return 200 with feature info"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("feature") == "Lexicon Intelligence Hub"
        assert data.get("feature_id") == "lexicon-intelligence"
        print("PASS: Health endpoint returns healthy status")


class TestFeature20UnauthenticatedAccess:
    """Tests for unauthenticated access - should return 401"""
    
    def test_bootstrap_requires_auth(self):
        """B: Bootstrap endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Bootstrap returns 401 for unauthenticated request")
    
    def test_templates_requires_auth(self):
        """B: Templates endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Templates returns 401 for unauthenticated request")
    
    def test_recommendations_requires_auth(self):
        """B: Recommendations endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/word-forge/recommendations")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Recommendations returns 401 for unauthenticated request")
    
    def test_export_requires_auth(self):
        """B: Export endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/word-forge/export")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Export returns 401 for unauthenticated request")
    
    def test_analytics_requires_auth(self):
        """B: Analytics endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/word-forge/analytics")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Analytics returns 401 for unauthenticated request")


class TestFeature20FreeUserAccess:
    """Tests for free user access"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as free user and get session"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "feature21.test.1781234530@example.com",
                "password": "Feature21Test#2026Aa"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip(f"Free user login failed: {login_response.status_code} - {login_response.text}")
        print("Free user login successful")
    
    def test_bootstrap_returns_free_plan(self):
        """C: Bootstrap returns free plan for free user"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("plan") == "free", f"Expected plan=free, got {data.get('plan')}"
        assert data.get("scope_label") == "Limited access"
        assert "daily_word" in data
        assert "limits" in data
        assert "capabilities" in data
        print("PASS: Bootstrap returns free plan with scope_label='Limited access'")
    
    def test_templates_accessible_for_free_user(self):
        """C: Templates endpoint accessible for free user"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "templates" in data
        assert data.get("plan") == "free"
        print(f"PASS: Templates accessible for free user, found {len(data.get('templates', []))} templates")
    
    def test_recommendations_accessible_for_free_user(self):
        """C: Recommendations endpoint accessible for free user"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/recommendations")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "recommendations" in data
        print("PASS: Recommendations accessible for free user")
    
    def test_export_accessible_for_free_user(self):
        """C: Export endpoint accessible for free user"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("plan") == "free"
        assert "profile" in data
        assert "usage_summary" in data
        print("PASS: Export accessible for free user")
    
    def test_analytics_accessible_for_free_user(self):
        """C: Analytics endpoint accessible for free user"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/analytics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("plan") == "free"
        assert "profile" in data
        assert "usage_summary" in data
        print("PASS: Analytics accessible for free user")


class TestFeature20AdminAccess:
    """Tests for admin/premium user access"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as admin user and get session"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@realaicoach.app",
                "password": "NewAdminPass2026!"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code} - {login_response.text}")
        print("Admin login successful")
    
    def test_bootstrap_returns_premium_plan_for_admin(self):
        """D: Bootstrap returns premium plan for admin"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("plan") == "premium", f"Expected plan=premium, got {data.get('plan')}"
        assert data.get("scope_label") == "Full unlimited access"
        assert "daily_word" in data
        assert "limits" in data
        # Premium should have -1 (unlimited) for limits
        limits = data.get("limits", {})
        assert limits.get("generate_word") == -1, f"Expected unlimited generate_word, got {limits.get('generate_word')}"
        print("PASS: Bootstrap returns premium plan with unlimited access for admin")
    
    def test_templates_returns_premium_recommendations_for_admin(self):
        """D: Templates returns premium recommendations for admin"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("plan") == "premium"
        # Premium should get boardroom-brief and negotiation-edge recommendations
        recommended = data.get("recommended_template_ids", [])
        assert "boardroom-brief" in recommended or "negotiation-edge" in recommended
        print("PASS: Templates returns premium recommendations for admin")
    
    def test_export_returns_premium_data_for_admin(self):
        """D: Export returns premium data for admin"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("plan") == "premium"
        assert data.get("scope_label") == "Full unlimited access"
        print("PASS: Export returns premium data for admin")


class TestFeature20EndpointContract:
    """Tests for endpoint contract presence and basic structure"""
    
    @pytest.fixture(autouse=True)
    def setup_session(self):
        """Login as admin for contract tests"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "admin@realaicoach.app",
                "password": "NewAdminPass2026!"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip(f"Admin login failed: {login_response.status_code}")
    
    def test_bootstrap_contract(self):
        """Contract: Bootstrap returns expected structure"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/bootstrap")
        assert response.status_code == 200
        data = response.json()
        # Required fields
        required_fields = ["plan", "scope_label", "limits", "daily_word", "saved_words", 
                          "review_queue", "profile", "usage_summary", "weekly_challenge",
                          "capabilities", "business_contexts", "generated_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print("PASS: Bootstrap contract verified with all required fields")
    
    def test_templates_contract(self):
        """Contract: Templates returns expected structure"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "plan" in data
        assert "recommended_template_ids" in data
        # Verify template structure
        if data.get("templates"):
            template = data["templates"][0]
            assert "template_id" in template
            assert "title" in template
            assert "description" in template
        print("PASS: Templates contract verified")
    
    def test_recommendations_contract(self):
        """Contract: Recommendations returns expected structure"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert "feature_id" in data
        assert data.get("feature_id") == "lexicon-intelligence"
        print("PASS: Recommendations contract verified")
    
    def test_export_contract(self):
        """Contract: Export returns expected structure"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/export")
        assert response.status_code == 200
        data = response.json()
        required_fields = ["feature_id", "plan", "scope_label", "profile", 
                          "usage_summary", "saved_words", "recent_words", "summary"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print("PASS: Export contract verified")
    
    def test_analytics_contract(self):
        """Contract: Analytics returns expected structure"""
        response = self.session.get(f"{BASE_URL}/api/word-forge/analytics")
        assert response.status_code == 200
        data = response.json()
        required_fields = ["plan", "scope_label", "profile", "usage_summary", 
                          "saved_words", "tracked_actions", "generated_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print("PASS: Analytics contract verified")


class TestFeature20FeatureRegistry:
    """Tests for Feature 20 presence in feature registry"""
    
    def test_feature_20_in_registry(self):
        """Feature 20 should be present in feature registry"""
        response = requests.get(f"{BASE_URL}/api/features/registry")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        features = data.get("features", [])
        
        # Find lexicon-intelligence feature
        lexicon_feature = None
        for feature in features:
            if feature.get("feature_id") == "lexicon-intelligence":
                lexicon_feature = feature
                break
        
        assert lexicon_feature is not None, "Feature 20 (lexicon-intelligence) not found in registry"
        assert lexicon_feature.get("title") == "Lexicon Intelligence Hub"
        assert lexicon_feature.get("route") == "/features/lexicon-intelligence"
        assert lexicon_feature.get("enabled") == True
        assert lexicon_feature.get("feature_number") == 20
        print("PASS: Feature 20 found in registry with correct metadata")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
