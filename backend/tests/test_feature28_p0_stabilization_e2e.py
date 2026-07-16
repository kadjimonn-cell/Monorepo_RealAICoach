"""
Feature 28 P0 Stabilization E2E Tests
Tests the Audio Studio source_health contract and full flow:
- GET /api/audio-studio/v2/bootstrap includes deterministic source_health object
- Full flow: login -> bootstrap -> play -> daily-drop-inbox -> mark-listened
- Auth consistency: cookie-based auth (no localStorage bearer token)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")

# Test credentials from /app/memory/test_credentials.md
FREE_USER_EMAIL = "p1.free.1779113329@example.com"
FREE_USER_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def free_user_session():
    """Create authenticated session for free user"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    
    # Login
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": FREE_USER_EMAIL, "password": FREE_USER_PASSWORD},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert data.get("user_id"), "No user_id in login response"
    assert data.get("subscription_plan") == "free", f"Expected free plan, got {data.get('subscription_plan')}"
    
    return session


class TestFeature28SourceHealthContract:
    """Test source_health API contract in bootstrap response"""
    
    def test_bootstrap_returns_source_health_object(self, free_user_session):
        """Verify bootstrap includes source_health with required fields"""
        response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200, f"Bootstrap failed: {response.text}"
        
        data = response.json()
        assert "source_health" in data, "source_health missing from bootstrap response"
        
        source_health = data["source_health"]
        assert source_health is not None, "source_health is None"
        
        # Verify required fields
        required_fields = [
            "status",
            "reason_code",
            "checked_at",
            "total_items",
            "playable_items",
        ]
        for field in required_fields:
            assert field in source_health, f"source_health missing field: {field}"
    
    def test_source_health_status_is_deterministic(self, free_user_session):
        """Verify source_health.status is one of allowed values"""
        response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200
        
        data = response.json()
        source_health = data.get("source_health", {})
        status = source_health.get("status")
        
        allowed_statuses = ["HEALTHY", "DEGRADED", "UNAVAILABLE", "UNKNOWN"]
        assert status in allowed_statuses, f"Invalid status: {status}, expected one of {allowed_statuses}"
    
    def test_source_health_reason_code_format(self, free_user_session):
        """Verify source_health.reason_code follows expected format"""
        response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200
        
        data = response.json()
        source_health = data.get("source_health", {})
        reason_code = source_health.get("reason_code", "")
        
        # Reason code should start with AUDIO_STUDIO_SOURCE_HEALTH_
        assert reason_code.startswith("AUDIO_STUDIO_SOURCE_HEALTH_"), \
            f"Invalid reason_code format: {reason_code}"
    
    def test_source_health_metrics_are_numeric(self, free_user_session):
        """Verify source_health metrics are numeric values"""
        response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200
        
        data = response.json()
        source_health = data.get("source_health", {})
        
        # Verify numeric fields
        numeric_fields = [
            "total_items",
            "playable_items",
            "degraded_items",
            "unavailable_items",
            "secure_https_ratio",
            "insecure_http_items",
            "fallback_items",
        ]
        for field in numeric_fields:
            if field in source_health:
                value = source_health[field]
                assert isinstance(value, (int, float)), \
                    f"source_health.{field} should be numeric, got {type(value)}"
    
    def test_source_health_contract_metadata(self, free_user_session):
        """Verify source_health includes contract metadata"""
        response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200
        
        data = response.json()
        source_health = data.get("source_health", {})
        contract = source_health.get("contract", {})
        
        # Verify contract metadata
        assert "allowed_statuses" in contract, "contract.allowed_statuses missing"
        assert "deterministic" in contract, "contract.deterministic missing"
        assert contract.get("deterministic") is True, "contract.deterministic should be True"
        
        allowed = contract.get("allowed_statuses", [])
        assert "HEALTHY" in allowed
        assert "DEGRADED" in allowed
        assert "UNAVAILABLE" in allowed
        assert "UNKNOWN" in allowed


class TestFeature28FullFlow:
    """Test full flow: login -> bootstrap -> play -> daily-drop-inbox -> mark-listened"""
    
    def test_full_flow_for_free_tier(self, free_user_session):
        """Test complete flow works for free tier user"""
        # Step 1: Bootstrap
        bootstrap_response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert bootstrap_response.status_code == 200, f"Bootstrap failed: {bootstrap_response.text}"
        
        bootstrap_data = bootstrap_response.json()
        assert bootstrap_data.get("feature_id") == "watch-videos-audio-studio"
        assert "source_health" in bootstrap_data
        assert "catalog" in bootstrap_data
        
        catalog = bootstrap_data.get("catalog", [])
        assert len(catalog) > 0, "Catalog is empty"
        
        # Step 2: Play first item (may fail if quota exceeded)
        first_item = catalog[0]
        item_id = first_item.get("item_id")
        assert item_id, "First item has no item_id"
        
        play_response = free_user_session.post(
            f"{BASE_URL}/api/audio-studio/v2/play",
            json={
                "item_id": item_id,
                "listen_seconds": 30,
                "completed": False,
                "source": "test_flow",
            },
        )
        # Accept 200 (success) or 429 (quota exceeded for free tier)
        assert play_response.status_code in [200, 429], f"Play failed: {play_response.text}"
        
        if play_response.status_code == 200:
            play_data = play_response.json()
            assert play_data.get("item", {}).get("item_id") == item_id
        
        # Step 3: Get daily drop inbox
        inbox_response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/daily-drop-inbox",
        )
        assert inbox_response.status_code == 200, f"Inbox failed: {inbox_response.text}"
        
        inbox_data = inbox_response.json()
        assert "items" in inbox_data
        assert "total" in inbox_data
        assert "unread" in inbox_data
        
        # Step 4: Mark first inbox item as listened (if available)
        inbox_items = inbox_data.get("items", [])
        if inbox_items:
            inbox_item_id = inbox_items[0].get("item_id")
            mark_response = free_user_session.post(
                f"{BASE_URL}/api/audio-studio/v2/daily-drop-inbox/mark-listened",
                json={"item_id": inbox_item_id},
            )
            assert mark_response.status_code == 200, f"Mark listened failed: {mark_response.text}"
            
            mark_data = mark_response.json()
            assert mark_data.get("item_id") == inbox_item_id
    
    def test_bootstrap_quota_for_free_tier(self, free_user_session):
        """Verify quota information in bootstrap for free tier"""
        response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200
        
        data = response.json()
        quota = data.get("quota", {})
        
        assert quota.get("plan") == "free", f"Expected free plan, got {quota.get('plan')}"
        assert "daily_play_limit" in quota
        assert "daily_play_used" in quota
        assert "daily_play_remaining" in quota
        assert "scope_label" in quota


class TestFeature28AuthConsistency:
    """Test auth consistency - cookie-based auth only"""
    
    def test_bootstrap_requires_auth(self):
        """Verify bootstrap requires authentication"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        
        response = session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        # Should return 401 or redirect to login
        assert response.status_code in [401, 403], \
            f"Expected 401/403 for unauthenticated request, got {response.status_code}"
    
    def test_cookie_auth_works_without_bearer_token(self, free_user_session):
        """Verify cookie-based auth works without Authorization header"""
        # Ensure no Authorization header is set
        if "Authorization" in free_user_session.headers:
            del free_user_session.headers["Authorization"]
        
        response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200, \
            f"Cookie auth should work without bearer token: {response.text}"
        
        data = response.json()
        assert data.get("feature_id") == "watch-videos-audio-studio"


class TestFeature28NoRegression:
    """Test no regression in existing API endpoints"""
    
    def test_podcasts_bootstrap_still_works(self, free_user_session):
        """Verify podcasts bootstrap endpoint still works"""
        response = free_user_session.get(
            f"{BASE_URL}/api/podcasts/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200, f"Podcasts bootstrap failed: {response.text}"
        
        data = response.json()
        assert data.get("feature_id") == "watch-videos-my-podcasts"
        assert "catalog" in data
        assert "quota" in data
    
    def test_sports_bootstrap_still_works(self, free_user_session):
        """Verify sports v2 bootstrap endpoint still works"""
        response = free_user_session.get(
            f"{BASE_URL}/api/sports/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert response.status_code == 200, f"Sports bootstrap failed: {response.text}"
        
        data = response.json()
        assert data.get("feature_id") == "watch-videos-sports"
        assert "catalog" in data
        assert "quota" in data
    
    def test_audio_studio_play_endpoint_works(self, free_user_session):
        """Verify audio studio play endpoint works or returns quota exceeded"""
        # First get an item from bootstrap
        bootstrap_response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/bootstrap",
            params={"tz": "UTC"},
        )
        assert bootstrap_response.status_code == 200
        
        catalog = bootstrap_response.json().get("catalog", [])
        if not catalog:
            pytest.skip("No catalog items available")
        
        item_id = catalog[0].get("item_id")
        
        # Test play endpoint
        response = free_user_session.post(
            f"{BASE_URL}/api/audio-studio/v2/play",
            json={
                "item_id": item_id,
                "listen_seconds": 10,
                "completed": False,
                "source": "regression_test",
            },
        )
        # Accept 200 (success) or 429 (quota exceeded for free tier)
        assert response.status_code in [200, 429], f"Play endpoint failed: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "item" in data
            assert data["item"].get("item_id") == item_id
        else:
            # Quota exceeded is valid for free tier
            data = response.json()
            assert "detail" in data
            assert "daily play cap" in data["detail"].lower() or "quota" in data["detail"].lower()
    
    def test_daily_drop_inbox_endpoint_works(self, free_user_session):
        """Verify daily drop inbox endpoint works"""
        response = free_user_session.get(
            f"{BASE_URL}/api/audio-studio/v2/daily-drop-inbox",
        )
        assert response.status_code == 200, f"Daily drop inbox failed: {response.text}"
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "unread" in data
        assert data.get("surface") == "audio_studio"
