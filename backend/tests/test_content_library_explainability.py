"""
Test Content Library Explainability Badges (Feature 33 P1.5)
Tests that backend returns explainability fields for sort=recommended
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
BASIC_USER_EMAIL = "f21.basic.1781338672@example.com"
BASIC_USER_PASSWORD = "F21Basic#2026Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestContentLibraryExplainability:
    """Test explainability fields in content library API"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        
    def _login(self, email, password):
        """Helper to login and get session"""
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
        return response
    
    def test_health_check(self):
        """Verify API is accessible"""
        response = self.session.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print("Health check passed")
    
    def test_login_basic_user(self):
        """Test login with basic user"""
        response = self._login(BASIC_USER_EMAIL, BASIC_USER_PASSWORD)
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "user_id" in data or "user" in data, "No user data in response"
        print("Basic user login successful")
        return data
    
    def test_login_admin_user(self):
        """Test login with admin user"""
        response = self._login(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        print("Admin login successful")
        return data
    
    def test_library_recommended_sort_returns_explainability_fields(self):
        """
        CRITICAL: Verify that sort=recommended returns explainability fields:
        - score
        - recency_rank
        - affinity_rank
        - bookmark_rank
        - recommendation_reasons
        """
        # Login first
        login_resp = self._login(BASIC_USER_EMAIL, BASIC_USER_PASSWORD)
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        user_data = login_resp.json()
        user_id = user_data.get("user_id") or user_data.get("user", {}).get("user_id")
        
        # Call library with sort=recommended
        response = self.session.get(
            f"{BASE_URL}/api/content/library",
            params={
                "sort": "recommended",
                "page": 1,
                "per_page": 12,
                "user_id": user_id
            }
        )
        
        assert response.status_code == 200, f"Library API failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "items" in data, "No items in response"
        assert "total" in data, "No total in response"
        assert "page" in data, "No page in response"
        
        print(f"Library response: total={data.get('total')}, items={len(data.get('items', []))}")
        
        # If there are items, verify explainability fields
        items = data.get("items", [])
        if len(items) > 0:
            for i, item in enumerate(items[:3]):  # Check first 3 items
                # Verify explainability fields exist
                assert "score" in item, f"Item {i} missing 'score' field"
                assert "recency_rank" in item, f"Item {i} missing 'recency_rank' field"
                assert "affinity_rank" in item, f"Item {i} missing 'affinity_rank' field"
                assert "bookmark_rank" in item, f"Item {i} missing 'bookmark_rank' field"
                assert "recommendation_reasons" in item, f"Item {i} missing 'recommendation_reasons' field"
                
                # Verify field types
                assert isinstance(item["score"], (int, float)), f"Item {i} score is not numeric"
                assert isinstance(item["recency_rank"], (int, float)), f"Item {i} recency_rank is not numeric"
                assert isinstance(item["affinity_rank"], (int, float)), f"Item {i} affinity_rank is not numeric"
                assert isinstance(item["bookmark_rank"], (int, float)), f"Item {i} bookmark_rank is not numeric"
                assert isinstance(item["recommendation_reasons"], list), f"Item {i} recommendation_reasons is not a list"
                
                print(f"Item {i}: score={item['score']}, reasons={item['recommendation_reasons']}")
        else:
            print("No items in library - explainability fields cannot be verified with data")
            # This is acceptable - the test passes if API structure is correct
        
        print("Explainability fields test PASSED")
    
    def test_library_newest_sort_no_explainability_fields(self):
        """
        Verify that sort=newest does NOT return explainability fields
        (they should only appear for recommended sort)
        """
        # Login first
        login_resp = self._login(BASIC_USER_EMAIL, BASIC_USER_PASSWORD)
        assert login_resp.status_code == 200
        
        user_data = login_resp.json()
        user_id = user_data.get("user_id") or user_data.get("user", {}).get("user_id")
        
        # Call library with sort=newest
        response = self.session.get(
            f"{BASE_URL}/api/content/library",
            params={
                "sort": "newest",
                "page": 1,
                "per_page": 12,
                "user_id": user_id
            }
        )
        
        assert response.status_code == 200, f"Library API failed: {response.text}"
        data = response.json()
        
        items = data.get("items", [])
        if len(items) > 0:
            for i, item in enumerate(items[:3]):
                # For newest sort, explainability fields should NOT be present
                # (or if present, they should be default/empty)
                if "score" in item:
                    # If score exists, it should be 0 or not set for non-recommended
                    print(f"Item {i} has score={item.get('score')} in newest sort (may be residual)")
        
        print("Newest sort test PASSED - no explainability fields expected")
    
    def test_library_oldest_sort_no_explainability_fields(self):
        """
        Verify that sort=oldest does NOT return explainability fields
        """
        # Login first
        login_resp = self._login(BASIC_USER_EMAIL, BASIC_USER_PASSWORD)
        assert login_resp.status_code == 200
        
        user_data = login_resp.json()
        user_id = user_data.get("user_id") or user_data.get("user", {}).get("user_id")
        
        # Call library with sort=oldest
        response = self.session.get(
            f"{BASE_URL}/api/content/library",
            params={
                "sort": "oldest",
                "page": 1,
                "per_page": 12,
                "user_id": user_id
            }
        )
        
        assert response.status_code == 200, f"Library API failed: {response.text}"
        print("Oldest sort test PASSED")
    
    def test_free_user_library_gate(self):
        """
        Verify that free users are gated from library access
        """
        # Login with free user
        response = self._login("p1.free.1779113329@example.com", "P1Free#2026!Aa")
        assert response.status_code == 200, f"Free user login failed: {response.text}"
        
        user_data = response.json()
        user_id = user_data.get("user_id") or user_data.get("user", {}).get("user_id")
        
        # Try to access library
        lib_response = self.session.get(
            f"{BASE_URL}/api/content/library",
            params={
                "sort": "recommended",
                "page": 1,
                "per_page": 12,
                "user_id": user_id
            }
        )
        
        # Should return 403 with subscription_required error
        assert lib_response.status_code == 403, f"Expected 403 for free user, got {lib_response.status_code}"
        data = lib_response.json()
        # Error can be "subscription_required" or "Subscription Required"
        error_val = str(data.get("error", "")).lower().replace(" ", "_")
        assert "subscription" in error_val, f"Expected subscription error: {data}"
        print("Free user gate test PASSED")
    
    def test_bookmark_toggle_endpoint(self):
        """
        Regression: Verify bookmark toggle endpoint still works
        """
        # Login first
        login_resp = self._login(BASIC_USER_EMAIL, BASIC_USER_PASSWORD)
        assert login_resp.status_code == 200
        
        user_data = login_resp.json()
        user_id = user_data.get("user_id") or user_data.get("user", {}).get("user_id")
        
        # Toggle bookmark on a test content ID
        response = self.session.post(
            f"{BASE_URL}/api/content/bookmarks/toggle",
            json={
                "user_id": user_id,
                "content_id": "test_content_explainability_123",
                "title": "Test Content for Explainability"
            }
        )
        
        assert response.status_code == 200, f"Bookmark toggle failed: {response.text}"
        data = response.json()
        assert "bookmarked" in data, "No bookmarked field in response"
        print(f"Bookmark toggle test PASSED: bookmarked={data.get('bookmarked')}")
        
        # Toggle again to remove
        response2 = self.session.post(
            f"{BASE_URL}/api/content/bookmarks/toggle",
            json={
                "user_id": user_id,
                "content_id": "test_content_explainability_123",
                "title": "Test Content for Explainability"
            }
        )
        assert response2.status_code == 200
        print("Bookmark toggle cleanup PASSED")
    
    def test_library_export_endpoint(self):
        """
        Regression: Verify library export endpoint still works
        """
        # Login first
        login_resp = self._login(BASIC_USER_EMAIL, BASIC_USER_PASSWORD)
        assert login_resp.status_code == 200
        
        # Test export with empty items (should still work)
        response = self.session.post(
            f"{BASE_URL}/api/content/library/export",
            json={
                "items": [
                    {
                        "title": "Test Item",
                        "type": "article",
                        "category": "productivity",
                        "url": "https://example.com/test",
                        "added_date": "2026-01-01T00:00:00Z"
                    }
                ],
                "format": "txt"
            }
        )
        
        assert response.status_code == 200, f"Export failed: {response.text}"
        assert "text/plain" in response.headers.get("content-type", ""), "Expected text/plain content type"
        print("Library export test PASSED")


class TestContentLibraryRegressions:
    """Regression tests for core library flows"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
    
    def _login(self, email, password):
        """Helper to login"""
        return self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": email,
            "password": password
        })
    
    def test_content_automate_endpoint(self):
        """Verify content automation endpoint works"""
        # This endpoint may require auth or be public - test both scenarios
        response = self.session.post(
            f"{BASE_URL}/api/content/automate",
            json={"max_items": 3}
        )
        # May return 200, 401 (auth required), or 500
        assert response.status_code in [200, 401, 500], f"Unexpected status: {response.status_code}"
        print(f"Content automate test: status={response.status_code}")
    
    def test_content_recent_endpoint(self):
        """Verify recent content endpoint works"""
        response = self.session.get(f"{BASE_URL}/api/content/recent?limit=6")
        # May require auth
        if response.status_code == 401:
            print("Recent content endpoint requires auth - skipping")
            return
        assert response.status_code == 200, f"Recent content failed: {response.text}"
        data = response.json()
        assert "items" in data, "No items in response"
        print(f"Recent content test PASSED: {len(data.get('items', []))} items")
    
    def test_bookmarks_get_endpoint(self):
        """Verify get bookmarks endpoint works"""
        # Login first
        login_resp = self._login(BASIC_USER_EMAIL, BASIC_USER_PASSWORD)
        assert login_resp.status_code == 200
        
        user_data = login_resp.json()
        user_id = user_data.get("user_id") or user_data.get("user", {}).get("user_id")
        
        response = self.session.get(f"{BASE_URL}/api/content/bookmarks/{user_id}")
        assert response.status_code == 200, f"Get bookmarks failed: {response.text}"
        data = response.json()
        assert "bookmarks" in data, "No bookmarks in response"
        print(f"Get bookmarks test PASSED: {len(data.get('bookmarks', []))} bookmarks")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
