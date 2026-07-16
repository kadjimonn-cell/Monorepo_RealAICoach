"""
Test: Side Navigation ↔ Feature Gallery Parity
Verifies that side-nav feature-like entries (jobs-portal, etc.) are present in /api/features/registry
and that the gallery can display them via search.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Expected side-nav feature IDs that should appear in the feature registry
# These are from CORE_SIDENAV_FEATURE_DEFAULTS in feature_registry.py
EXPECTED_SIDENAV_FEATURES = [
    "games-station",
    "flappy-bird",
    "watch-videos",
    "audio-studio",
    "my-podcasts",
    "sports",
    "travel-visa",
    "daily-meditation",
    "ai-learning-hub",
    "ai-coaching-team",
    "ai-briefing",
    "library",
    "book-meeting",
    "integrations",
    "jobs-portal",  # Key feature to test
    "referrals",
    "id-checker",
]

# Side-nav grouped keys from AppShell.tsx (excluding ai-gallery section key itself)
SIDENAV_GROUPED_KEYS = {
    "platform": ["games-station", "flappy-bird", "watch-videos", "audio-studio", "my-podcasts", "sports", "travel-visa", "daily-meditation"],
    "ai_tools": ["ai-learning-hub", "ai-coaching-team", "ai-briefing", "library", "book-meeting", "integrations"],
    "hiring": ["jobs-portal", "referrals"],
    "verification": ["id-checker"],
}


class TestFeatureRegistryParity:
    """Tests for side-nav ↔ feature gallery parity"""

    def test_registry_endpoint_returns_200(self):
        """GET /api/features/registry should return 200"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ GET /api/features/registry returned 200")

    def test_registry_contains_features_array(self):
        """Registry response should contain features array"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "features" in data, "Response missing 'features' key"
        assert isinstance(data["features"], list), "'features' should be a list"
        assert len(data["features"]) > 0, "Features list should not be empty"
        print(f"✓ Registry contains {len(data['features'])} features")

    def test_jobs_portal_in_registry(self):
        """Jobs Portal should be present in feature registry"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        features = data.get("features", [])
        feature_ids = [f.get("feature_id") for f in features]
        
        assert "jobs-portal" in feature_ids, f"jobs-portal not found in registry. Found: {feature_ids}"
        
        # Verify jobs-portal has correct properties
        jobs_portal = next((f for f in features if f.get("feature_id") == "jobs-portal"), None)
        assert jobs_portal is not None
        assert jobs_portal.get("title") == "Job Search", f"Expected title 'Job Search', got {jobs_portal.get('title')}"
        assert jobs_portal.get("route") == "/job-search", f"Expected route '/job-search', got {jobs_portal.get('route')}"
        assert jobs_portal.get("enabled") is True, "jobs-portal should be enabled"
        print("✓ jobs-portal found in registry with correct properties")

    def test_all_sidenav_features_in_registry(self):
        """All expected side-nav features should be in registry"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        features = data.get("features", [])
        feature_ids = set(f.get("feature_id") for f in features)
        
        missing = []
        for expected_id in EXPECTED_SIDENAV_FEATURES:
            if expected_id not in feature_ids:
                missing.append(expected_id)
        
        if missing:
            print(f"✗ Missing features: {missing}")
        assert len(missing) == 0, f"Missing side-nav features in registry: {missing}"
        print(f"✓ All {len(EXPECTED_SIDENAV_FEATURES)} expected side-nav features found in registry")

    def test_sidenav_grouped_keys_parity(self):
        """Verify side-nav grouped keys (platform, ai_tools, hiring, verification) are in registry"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        features = data.get("features", [])
        feature_ids = set(f.get("feature_id") for f in features)
        
        missing_by_group = {}
        for group_name, group_keys in SIDENAV_GROUPED_KEYS.items():
            missing = [k for k in group_keys if k not in feature_ids]
            if missing:
                missing_by_group[group_name] = missing
        
        if missing_by_group:
            print(f"✗ Missing by group: {missing_by_group}")
        assert len(missing_by_group) == 0, f"Missing features by group: {missing_by_group}"
        print("✓ All side-nav grouped keys present in registry")

    def test_registry_total_count_increased(self):
        """Registry should have increased total (main agent noted 25→36)"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        total = data.get("total", 0)
        features_count = len(data.get("features", []))
        
        # Main agent noted increase from 25 to 36
        assert features_count >= 30, f"Expected at least 30 features, got {features_count}"
        print(f"✓ Registry has {features_count} features (total field: {total})")

    def test_registry_categories_derived(self):
        """Registry should derive categories from features"""
        response = requests.get(f"{BASE_URL}/api/features/registry", timeout=15)
        assert response.status_code == 200
        data = response.json()
        categories = data.get("categories", [])
        
        assert len(categories) > 0, "Categories should not be empty"
        category_ids = [c.get("id") for c in categories]
        assert "all" in category_ids, "'all' category should be present"
        print(f"✓ Registry has {len(categories)} categories: {category_ids}")


class TestRegressionRoutes:
    """Regression tests for /welcome and /login routes"""

    def test_welcome_page_loads(self):
        """GET /welcome should return 200"""
        response = requests.get(f"{BASE_URL}/welcome", timeout=15, allow_redirects=True)
        # Welcome page is frontend route, may return HTML
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ /welcome returns 200")

    def test_login_page_loads(self):
        """GET /auth/login should return 200"""
        response = requests.get(f"{BASE_URL}/auth/login", timeout=15, allow_redirects=True)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ /auth/login returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
