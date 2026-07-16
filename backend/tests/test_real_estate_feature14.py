"""
Feature 14: Property Decision Advisor (Real Estate) API Tests
Tests for /api/real-estate/ endpoints with guest flow using fallback_user_id
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}

# Test fallback user ID (must start with user_ and be at least 20 chars)
VALID_FALLBACK_USER_ID = "user_testfeature14abc12345"
INVALID_FALLBACK_USER_ID = "invalid_short"


class TestRealEstatePublicContract:
    """Verify /api/real-estate/ is in public API contract"""
    
    def test_search_endpoint_accessible_without_auth(self):
        """Search endpoint should be accessible for guest users with fallback_user_id"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/search",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "location": "Miami, FL"
            }
        )
        # Should not return 401 for valid fallback_user_id
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "properties" in data
        assert "owner_id" in data
        assert data["owner_id"].startswith("guest:")
    
    def test_valuation_endpoint_accessible_without_auth(self):
        """Valuation endpoint should be accessible for guest users with fallback_user_id"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/ai-valuation",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "address": "123 Main St, Miami, FL"
            }
        )
        # Should not return 401 for valid fallback_user_id
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "valuation_report" in data
        assert "owner_id" in data
        assert data["owner_id"].startswith("guest:")


class TestRealEstateGuestFlow:
    """Test guest flow with fallback_user_id"""
    
    def test_search_requires_auth_or_fallback(self):
        """Search should return 401 when no auth and no fallback_user_id"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/search",
            headers=HEADERS,
            json={"location": "Miami, FL"}
        )
        assert response.status_code == 401
        
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error_code"] == "real_estate_auth_required"
    
    def test_valuation_requires_auth_or_fallback(self):
        """Valuation should return 401 when no auth and no fallback_user_id"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/ai-valuation",
            headers=HEADERS,
            json={"address": "123 Main St, Miami, FL"}
        )
        assert response.status_code == 401
        
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error_code"] == "real_estate_auth_required"
    
    def test_search_with_valid_fallback_user_id(self):
        """Search should work with valid fallback_user_id"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/search",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "location": "New York, NY"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "properties" in data
        assert isinstance(data["properties"], list)
        assert "tier" in data
        assert data["tier"] == "free"  # Guest users get free tier
        assert "daily_limit" in data
    
    def test_valuation_with_valid_fallback_user_id(self):
        """Valuation should work with valid fallback_user_id"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/ai-valuation",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "address": "456 Ocean Drive, Miami, FL"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "valuation_report" in data
        assert isinstance(data["valuation_report"], str)
        assert len(data["valuation_report"]) > 100  # Should have substantial content
        assert "remaining_today" in data


class TestRealEstateSearchEndpoint:
    """Test /api/real-estate/search endpoint"""
    
    def test_search_returns_properties(self):
        """Search should return list of properties"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/search",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "location": "Los Angeles, CA"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "properties" in data
        assert isinstance(data["properties"], list)
        
        if len(data["properties"]) > 0:
            prop = data["properties"][0]
            # Verify property structure
            assert "id" in prop
            assert "address" in prop
            assert "city" in prop
            assert "price" in prop
            assert "beds" in prop
            assert "baths" in prop
            assert "sqft" in prop
    
    def test_search_with_filters(self):
        """Search should accept filter parameters"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/search",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "location": "Miami, FL",
                "min_price": 500000,
                "max_price": 1000000,
                "beds": 3
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "properties" in data
    
    def test_search_returns_tier_info(self):
        """Search should return tier and limit information"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/search",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "location": "Miami, FL"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "tier" in data
        assert "daily_limit" in data
        assert "used_today" in data
        assert "remaining_today" in data


class TestRealEstateValuationEndpoint:
    """Test /api/real-estate/ai-valuation endpoint"""
    
    def test_valuation_returns_report(self):
        """Valuation should return AI-generated report"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/ai-valuation",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "address": "789 Beach Blvd, Miami, FL"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "valuation_report" in data
        assert isinstance(data["valuation_report"], str)
        assert "address" in data
        assert data["address"] == "789 Beach Blvd, Miami, FL"
    
    def test_valuation_returns_tier_info(self):
        """Valuation should return tier and limit information"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/ai-valuation",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "address": "100 Main St, Miami, FL"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "tier" in data
        assert "daily_limit" in data
        assert "remaining_today" in data


class TestRealEstateMortgageCalculator:
    """Test /api/real-estate/mortgage-calculator endpoint (no auth required)"""
    
    def test_mortgage_calculation(self):
        """Mortgage calculator should work without authentication"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/mortgage-calculator",
            headers=HEADERS,
            json={
                "price": 500000,
                "down_payment": 100000,
                "rate": 6.5,
                "term_years": 30
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "monthly_payment" in data
        assert "total_paid" in data
        assert "total_interest" in data
        assert "principal" in data
        assert data["principal"] == 400000  # price - down_payment
    
    def test_mortgage_calculation_zero_rate(self):
        """Mortgage calculator should handle zero interest rate"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/mortgage-calculator",
            headers=HEADERS,
            json={
                "price": 300000,
                "down_payment": 60000,
                "rate": 0,
                "term_years": 15
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "monthly_payment" in data
        # With 0% rate, monthly payment = principal / (term_years * 12)
        expected_monthly = 240000 / (15 * 12)
        assert abs(data["monthly_payment"] - expected_monthly) < 1


class TestRealEstateTourScheduling:
    """Test /api/real-estate/schedule-tour endpoint"""
    
    def test_tour_scheduling_free_tier_blocked(self):
        """Tour scheduling should be blocked for free tier users"""
        response = requests.post(
            f"{BASE_URL}/api/real-estate/schedule-tour",
            headers=HEADERS,
            json={
                "fallback_user_id": VALID_FALLBACK_USER_ID,
                "property_address": "123 Main St, Miami, FL",
                "preferred_date": "2026-02-15"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert not data["success"]
        assert "Premium required" in data["message"]
        assert data["tier"] == "free"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
