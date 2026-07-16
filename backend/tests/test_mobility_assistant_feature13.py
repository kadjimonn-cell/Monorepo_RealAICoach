"""
Feature 13: Mobility Assistant (smart-cars) Backend API Tests
Tests strict guest-id validation, bootstrap, search, trade-in, finance, trip, insurance endpoints
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test guest fallback ID - must match ^user_[a-zA-Z0-9_-]{12,80}$
VALID_GUEST_ID = "user_testfeature13abc12345"
INVALID_SHORT_GUEST_ID = "user_abc"  # Too short (< 12 chars after prefix)
INVALID_FORMAT_GUEST_ID = "guest_12345678901234"  # Wrong prefix

# Headers to bypass CSRF for testing
TEST_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


class TestMobilityAssistantGuestValidation:
    """Test strict guest-id validation for mobility-assistant endpoints"""
    
    def test_bootstrap_valid_fallback_returns_200(self):
        """Valid user_* fallback should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/bootstrap",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "owner_id" in data
        assert "tier" in data
        assert "limits" in data
        assert "usage" in data
        print(f"PASS: Bootstrap with valid fallback returns 200, tier={data['tier']}")
    
    def test_bootstrap_invalid_short_returns_400(self):
        """Invalid short guest ID should return 400 invalid_guest_id"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/bootstrap",
            params={"fallback_user_id": INVALID_SHORT_GUEST_ID}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id", f"Expected invalid_guest_id error: {data}"
        print("PASS: Bootstrap with short guest ID returns 400 invalid_guest_id")
    
    def test_bootstrap_invalid_format_returns_400(self):
        """Invalid format guest ID (wrong prefix) should return 400 invalid_guest_id"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/bootstrap",
            params={"fallback_user_id": INVALID_FORMAT_GUEST_ID}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_guest_id", f"Expected invalid_guest_id error: {data}"
        print("PASS: Bootstrap with wrong prefix returns 400 invalid_guest_id")
    
    def test_bootstrap_missing_auth_returns_401(self):
        """Missing auth and fallback should return 401 auth_required"""
        response = requests.get(f"{BASE_URL}/api/mobility-assistant/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error") == "auth_required", f"Expected auth_required error: {data}"
        print("PASS: Bootstrap without auth/fallback returns 401 auth_required")


class TestMobilityAssistantBootstrap:
    """Test bootstrap endpoint returns correct structure"""
    
    def test_bootstrap_returns_tier_and_limits(self):
        """Bootstrap should return tier, limits, and usage"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/bootstrap",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "tier" in data
        assert data["tier"] in ["free", "basic", "premium"]
        
        assert "limits" in data
        limits = data["limits"]
        assert "searches_per_month" in limits
        assert "ai_calls_per_month" in limits
        assert "saved_vehicles" in limits
        assert "service_records" in limits
        
        assert "usage" in data
        usage = data["usage"]
        assert "searches_this_month" in usage
        assert "ai_calls_this_month" in usage
        assert "saved_vehicles" in usage
        assert "service_records" in usage
        
        print(f"PASS: Bootstrap returns complete structure with tier={data['tier']}")


class TestMobilityAssistantSearch:
    """Test vehicle search endpoint"""
    
    def test_search_vehicles_returns_listings(self):
        """Search should return listings array"""
        response = requests.post(
            f"{BASE_URL}/api/mobility-assistant/search",
            json={
                "make": "Toyota",
                "model": "Camry",
                "fallback_user_id": VALID_GUEST_ID
            },
            headers=TEST_HEADERS
        )
        # May return 200 or 403 if limit reached
        assert response.status_code in [200, 403], f"Expected 200 or 403, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "listings" in data
            assert "count" in data
            assert isinstance(data["listings"], list)
            print(f"PASS: Search returns {data['count']} listings")
        else:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") == "tier_limit_reached"
            else:
                assert "tier_limit_reached" in str(detail) or "limit" in str(detail).lower()
            print("PASS: Search returns 403 tier_limit_reached (expected for free tier)")
    
    def test_search_history_returns_array(self):
        """Search history should return history array"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/search/history",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)
        print(f"PASS: Search history returns {len(data['history'])} records")


class TestMobilityAssistantTradeIn:
    """Test trade-in valuation endpoint"""
    
    def test_tradein_valuation(self):
        """Trade-in should return valuation"""
        response = requests.post(
            f"{BASE_URL}/api/mobility-assistant/trade-in",
            json={
                "make": "Honda",
                "model": "Accord",
                "year": 2020,
                "mileage": 45000,
                "condition": "Good",
                "fallback_user_id": VALID_GUEST_ID
            },
            headers=TEST_HEADERS
        )
        # May return 200 or 403 if AI limit reached
        assert response.status_code in [200, 403], f"Expected 200 or 403, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "valuation_id" in data
            assert "valuation" in data
            print(f"PASS: Trade-in returns valuation_id={data['valuation_id']}")
        else:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") == "tier_limit_reached"
            else:
                assert "tier_limit_reached" in str(detail) or "limit" in str(detail).lower()
            print("PASS: Trade-in returns 403 tier_limit_reached (expected for free tier)")


class TestMobilityAssistantFinance:
    """Test finance calculator endpoint"""
    
    def test_finance_calculation(self):
        """Finance should return payment breakdown"""
        response = requests.post(
            f"{BASE_URL}/api/mobility-assistant/finance",
            json={
                "vehicle_price": 35000,
                "down_payment": 5000,
                "loan_term_months": 60,
                "credit_score_range": "good",
                "fallback_user_id": VALID_GUEST_ID
            },
            headers=TEST_HEADERS
        )
        # May return 200 or 403 if AI limit reached
        assert response.status_code in [200, 403], f"Expected 200 or 403, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "monthly_payment" in data
            assert "total_paid" in data
            assert "total_interest" in data
            assert "apr_percent" in data
            print(f"PASS: Finance returns monthly_payment=${data['monthly_payment']}")
        else:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") == "tier_limit_reached"
            else:
                assert "tier_limit_reached" in str(detail) or "limit" in str(detail).lower()
            print("PASS: Finance returns 403 tier_limit_reached (expected for free tier)")


class TestMobilityAssistantSavedVehicles:
    """Test saved vehicles CRUD"""
    
    def test_list_saved_vehicles(self):
        """List saved vehicles should return array"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/saved-vehicles",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "vehicles" in data
        assert "count" in data
        assert isinstance(data["vehicles"], list)
        print(f"PASS: Saved vehicles returns {data['count']} vehicles")


class TestMobilityAssistantTrip:
    """Test trip planner endpoint"""
    
    def test_trip_planner(self):
        """Trip planner should return trip plan"""
        response = requests.post(
            f"{BASE_URL}/api/mobility-assistant/trip-planner",
            json={
                "origin": "Los Angeles, CA",
                "destination": "San Francisco, CA",
                "make": "Toyota",
                "model": "Camry",
                "year": 2022,
                "fuel_type": "gasoline",
                "fallback_user_id": VALID_GUEST_ID
            },
            headers=TEST_HEADERS
        )
        # May return 200 or 403 if AI limit reached
        assert response.status_code in [200, 403], f"Expected 200 or 403, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "origin" in data
            assert "destination" in data
            assert "trip_plan" in data
            print(f"PASS: Trip planner returns plan for {data['origin']} to {data['destination']}")
        else:
            data = response.json()
            detail = data.get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") == "tier_limit_reached"
            else:
                assert "tier_limit_reached" in str(detail) or "limit" in str(detail).lower()
            print("PASS: Trip planner returns 403 tier_limit_reached (expected for free tier)")


class TestMobilityAssistantServiceHistory:
    """Test service history endpoints"""
    
    def test_list_service_history(self):
        """List service history should return array"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/service-history",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "records" in data
        assert "count" in data
        assert isinstance(data["records"], list)
        print(f"PASS: Service history returns {data['count']} records")


class TestMobilityAssistantAnalytics:
    """Test analytics endpoint"""
    
    def test_analytics_returns_counts(self):
        """Analytics should return usage counts"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/analytics",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "total_searches" in data
        assert "total_trade_in_requests" in data
        assert "total_ai_calls" in data
        assert "saved_vehicles" in data
        assert "service_records" in data
        print("PASS: Analytics returns complete usage data")


class TestMobilityAssistantSessions:
    """Test sessions endpoint"""
    
    def test_sessions_returns_array(self):
        """Sessions should return usage log array"""
        response = requests.get(
            f"{BASE_URL}/api/mobility-assistant/sessions",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "sessions" in data
        assert "count" in data
        assert isinstance(data["sessions"], list)
        print(f"PASS: Sessions returns {data['count']} session records")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
