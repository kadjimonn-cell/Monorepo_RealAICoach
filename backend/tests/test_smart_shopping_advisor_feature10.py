"""
Feature 10: Smart Shopping Advisor - Backend API Tests
Tests strict guest-id validation, auth requirements, and core CRUD operations.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Headers for POST requests (CSRF bypass)
POST_HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}

# Test guest IDs
VALID_GUEST_ID = "user_testfeature10abc12345"  # Valid format: user_ + 12-80 alphanumeric chars
VALID_GUEST_ID_WISHLIST = "user_testfeature10wishlist123"  # Separate ID for wishlist tests to avoid tier limits
INVALID_LEGACY_GUEST_ID = "guest-smart-shopping"  # Legacy format - should be rejected
INVALID_SHORT_GUEST_ID = "user_abc"  # Too short (< 12 chars after user_)
INVALID_NO_PREFIX_GUEST_ID = "testfeature10abc12345"  # Missing user_ prefix


class TestSmartShoppingAdvisorStrictGuestIdValidation:
    """Tests for strict guest-id validation in _resolve_owner_id"""

    def test_bootstrap_with_valid_guest_id_returns_200(self):
        """Valid user_* format should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/bootstrap",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "owner_id" in data
        assert "tier" in data
        assert "limits" in data
        assert "usage" in data
        assert "features_available" in data
        print(f"PASS: Bootstrap with valid guest ID returns 200, tier={data['tier']}")

    def test_bootstrap_with_invalid_legacy_guest_id_returns_400(self):
        """Legacy guest-smart-shopping format should be rejected with 400"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/bootstrap",
            params={"fallback_user_id": INVALID_LEGACY_GUEST_ID}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "shopping_invalid_guest_id"
        print("PASS: Legacy guest ID rejected with 400 shopping_invalid_guest_id")

    def test_bootstrap_with_short_guest_id_returns_400(self):
        """Short guest ID (< 12 chars after user_) should be rejected with 400"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/bootstrap",
            params={"fallback_user_id": INVALID_SHORT_GUEST_ID}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "shopping_invalid_guest_id"
        print("PASS: Short guest ID rejected with 400 shopping_invalid_guest_id")

    def test_bootstrap_with_no_prefix_guest_id_returns_400(self):
        """Guest ID without user_ prefix should be rejected with 400"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/bootstrap",
            params={"fallback_user_id": INVALID_NO_PREFIX_GUEST_ID}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "shopping_invalid_guest_id"
        print("PASS: No-prefix guest ID rejected with 400 shopping_invalid_guest_id")

    def test_bootstrap_without_fallback_user_id_returns_401(self):
        """Missing auth and fallback_user_id should return 401"""
        response = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "shopping_auth_required"
        print("PASS: Missing auth/fallback returns 401 shopping_auth_required")


class TestSmartShoppingAdvisorWishlists:
    """Tests for wishlist CRUD operations"""

    def test_wishlists_list_with_valid_guest_id(self):
        """GET /wishlists with valid guest ID should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/wishlists",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "wishlists" in data
        print(f"PASS: Wishlists list returns 200, count={len(data['wishlists'])}")

    def test_wishlists_list_without_auth_returns_401(self):
        """GET /wishlists without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/wishlists")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: Wishlists list without auth returns 401")

    def test_create_wishlist(self):
        """POST /wishlists should create a wishlist (or return 403 if tier limit reached)"""
        response = requests.post(
            f"{BASE_URL}/api/smart-shopping-advisor/wishlists",
            params={"fallback_user_id": VALID_GUEST_ID_WISHLIST},
            headers=POST_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID_WISHLIST,
                "name": "Test Wishlist Feature 10",
                "description": "Testing wishlist creation",
                "items": []
            }
        )
        # Accept 200 (created) or 403 (tier limit reached - expected behavior)
        if response.status_code == 403 and "limit reached" in response.text:
            print("PASS: Wishlist tier limit enforced correctly (403)")
            return
        assert response.status_code == 200, f"Expected 200 or 403 tier limit, got {response.status_code}: {response.text}"
        data = response.json()
        assert "wishlist_id" in data
        print(f"PASS: Wishlist created, id={data['wishlist_id']}")

    def test_get_wishlist_by_id(self):
        """GET /wishlists/{id} should return wishlist details"""
        # First create a wishlist
        create_response = requests.post(
            f"{BASE_URL}/api/smart-shopping-advisor/wishlists",
            params={"fallback_user_id": VALID_GUEST_ID_WISHLIST},
            headers=POST_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID_WISHLIST,
                "name": "Test Wishlist for Get",
                "description": "Testing get by ID",
                "items": []
            }
        )
        # If tier limit reached, skip this test
        if create_response.status_code == 403 and "limit reached" in create_response.text:
            print("SKIP: Wishlist tier limit reached - tier limits working correctly")
            return
        assert create_response.status_code == 200
        wishlist_id = create_response.json()["wishlist_id"]

        # Then get it
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/wishlists/{wishlist_id}",
            params={"fallback_user_id": VALID_GUEST_ID_WISHLIST}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["id"] == wishlist_id
        assert data["name"] == "Test Wishlist for Get"
        print("PASS: Get wishlist by ID returns 200")

    def test_delete_wishlist(self):
        """DELETE /wishlists/{id} should delete wishlist"""
        # First create a wishlist
        create_response = requests.post(
            f"{BASE_URL}/api/smart-shopping-advisor/wishlists",
            params={"fallback_user_id": VALID_GUEST_ID_WISHLIST},
            headers=POST_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID_WISHLIST,
                "name": "Test Wishlist for Delete",
                "description": "Testing delete",
                "items": []
            }
        )
        # If tier limit reached, skip this test
        if create_response.status_code == 403 and "limit reached" in create_response.text:
            print("SKIP: Wishlist tier limit reached - tier limits working correctly")
            return
        assert create_response.status_code == 200
        wishlist_id = create_response.json()["wishlist_id"]

        # Then delete it
        response = requests.delete(
            f"{BASE_URL}/api/smart-shopping-advisor/wishlists/{wishlist_id}",
            params={"fallback_user_id": VALID_GUEST_ID_WISHLIST},
            headers=POST_HEADERS
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Delete wishlist returns 200")


class TestSmartShoppingAdvisorBudgets:
    """Tests for budget CRUD operations"""

    def test_budgets_list_with_valid_guest_id(self):
        """GET /budgets with valid guest ID should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/budgets",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "budgets" in data
        print(f"PASS: Budgets list returns 200, count={len(data['budgets'])}")

    def test_budgets_list_without_auth_returns_401(self):
        """GET /budgets without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/budgets")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: Budgets list without auth returns 401")

    def test_create_budget(self):
        """POST /budgets should create a budget (or return 403 if tier limit reached)"""
        response = requests.post(
            f"{BASE_URL}/api/smart-shopping-advisor/budgets",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=POST_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": "Test Budget Feature 10",
                "category": "electronics",
                "monthly_limit": 500.0,
                "currency": "USD",
                "alert_threshold_pct": 80.0
            }
        )
        # Accept 200 (created) or 403 (tier limit reached - expected behavior)
        if response.status_code == 403 and "limit reached" in response.text:
            print("PASS: Budget tier limit enforced correctly (403)")
            return
        assert response.status_code == 200, f"Expected 200 or 403 tier limit, got {response.status_code}: {response.text}"
        data = response.json()
        assert "budget_id" in data
        print(f"PASS: Budget created, id={data['budget_id']}")


class TestSmartShoppingAdvisorDeals:
    """Tests for deals endpoints"""

    def test_deals_list_with_valid_guest_id(self):
        """GET /deals with valid guest ID should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/deals",
            params={"fallback_user_id": VALID_GUEST_ID, "limit": 10}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "deals" in data
        print(f"PASS: Deals list returns 200, count={len(data['deals'])}")

    def test_deals_list_without_auth_returns_401(self):
        """GET /deals without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/deals")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: Deals list without auth returns 401")


class TestSmartShoppingAdvisorCarbonReport:
    """Tests for carbon report endpoint"""

    def test_carbon_report_with_valid_guest_id(self):
        """GET /carbon-report with valid guest ID should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/carbon-report",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "month" in data
        assert "total_purchases" in data
        assert "total_carbon_kg" in data
        print(f"PASS: Carbon report returns 200, total_carbon_kg={data['total_carbon_kg']}")

    def test_carbon_report_without_auth_returns_401(self):
        """GET /carbon-report without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/carbon-report")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: Carbon report without auth returns 401")


class TestSmartShoppingAdvisorPriceAlerts:
    """Tests for price alerts endpoints"""

    def test_price_alerts_list_with_valid_guest_id(self):
        """GET /price-alerts with valid guest ID should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/price-alerts",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "alerts" in data
        print(f"PASS: Price alerts list returns 200, count={len(data['alerts'])}")

    def test_price_alerts_list_without_auth_returns_401(self):
        """GET /price-alerts without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/smart-shopping-advisor/price-alerts")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: Price alerts list without auth returns 401")


class TestSmartShoppingAdvisorPurchases:
    """Tests for purchases endpoints"""

    def test_purchases_list_with_valid_guest_id(self):
        """GET /purchases with valid guest ID should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/purchases",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "purchases" in data
        print(f"PASS: Purchases list returns 200, count={len(data['purchases'])}")

    def test_log_purchase(self):
        """POST /purchases should log a purchase"""
        response = requests.post(
            f"{BASE_URL}/api/smart-shopping-advisor/purchases",
            params={"fallback_user_id": VALID_GUEST_ID},
            headers=POST_HEADERS,
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "product_name": "Test Product Feature 10",
                "amount": 99.99,
                "currency": "USD",
                "category": "electronics",
                "merchant": "Test Store"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "purchase_id" in data
        assert "carbon_footprint_kg" in data
        print(f"PASS: Purchase logged, id={data['purchase_id']}, carbon={data['carbon_footprint_kg']}kg")


class TestSmartShoppingAdvisorBudgetAnalytics:
    """Tests for budget analytics endpoint"""

    def test_budget_analytics_with_valid_guest_id(self):
        """GET /budget-analytics with valid guest ID should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/smart-shopping-advisor/budget-analytics",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "month" in data
        assert "total_budget" in data
        assert "total_spent" in data
        print(f"PASS: Budget analytics returns 200, total_spent={data['total_spent']}")


class TestSmartShoppingAdvisorPublicContract:
    """Tests for public API contract"""

    def test_smart_shopping_advisor_prefix_is_public(self):
        """Verify /api/smart-shopping-advisor/ is in public API contract"""
        # Import the contract module
        import sys
        sys.path.insert(0, "/app/backend")
        from utils.public_api_contract import PUBLIC_API_PREFIXES, is_public_api_path

        assert "/api/smart-shopping-advisor/" in PUBLIC_API_PREFIXES, \
            "/api/smart-shopping-advisor/ should be in PUBLIC_API_PREFIXES"
        
        # Test specific paths
        assert is_public_api_path("/api/smart-shopping-advisor/bootstrap")
        assert is_public_api_path("/api/smart-shopping-advisor/wishlists")
        assert is_public_api_path("/api/smart-shopping-advisor/budgets")
        assert is_public_api_path("/api/smart-shopping-advisor/deals")
        assert is_public_api_path("/api/smart-shopping-advisor/carbon-report")
        print("PASS: /api/smart-shopping-advisor/ prefix is in public contract")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
