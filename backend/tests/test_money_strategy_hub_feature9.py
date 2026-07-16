"""
Feature 9 Money Strategy Hub - Backend API Tests
Tests strict guest-id validation, auth requirements, and core CRUD operations.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Valid guest ID format: user_[a-zA-Z0-9_-]{12,80}
VALID_GUEST_ID = "user_testfeature9abc12345"
INVALID_GUEST_ID_LEGACY = "guest-money-strategy-hub"  # Old legacy format - should be rejected
INVALID_GUEST_ID_SHORT = "user_abc"  # Too short
INVALID_GUEST_ID_NO_PREFIX = "testfeature9abc12345"  # Missing user_ prefix

# Headers for CSRF bypass
HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest"
}


class TestMoneyStrategyHubGuestIdValidation:
    """Tests for strict guest-id format validation (user_* format required)"""

    def test_bootstrap_with_valid_guest_id_returns_200(self):
        """Valid user_* format should return 200"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/bootstrap",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "owner_id" in data
        assert "tier" in data
        assert data["owner_id"] == f"guest:{VALID_GUEST_ID}"
        print(f"PASS: Bootstrap with valid guest ID returns 200, owner_id={data['owner_id']}")

    def test_bootstrap_with_invalid_legacy_guest_id_returns_400(self):
        """Legacy guest-money-strategy-hub format should be rejected with 400"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/bootstrap",
            params={"fallback_user_id": INVALID_GUEST_ID_LEGACY}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "money_strategy_invalid_guest_id"
        print("PASS: Legacy guest ID rejected with 400 money_strategy_invalid_guest_id")

    def test_bootstrap_with_short_guest_id_returns_400(self):
        """Short guest ID (< 12 chars after user_) should be rejected"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/bootstrap",
            params={"fallback_user_id": INVALID_GUEST_ID_SHORT}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "money_strategy_invalid_guest_id"
        print("PASS: Short guest ID rejected with 400 money_strategy_invalid_guest_id")

    def test_bootstrap_with_no_prefix_guest_id_returns_400(self):
        """Guest ID without user_ prefix should be rejected"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/bootstrap",
            params={"fallback_user_id": INVALID_GUEST_ID_NO_PREFIX}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "money_strategy_invalid_guest_id"
        print("PASS: No-prefix guest ID rejected with 400 money_strategy_invalid_guest_id")

    def test_bootstrap_without_fallback_user_id_returns_401(self):
        """Missing auth and fallback_user_id should return 401"""
        response = requests.get(f"{BASE_URL}/api/money-strategy-hub/bootstrap")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("detail", {}).get("error_code") == "money_strategy_auth_required"
        print("PASS: Missing auth/fallback returns 401 money_strategy_auth_required")


class TestMoneyStrategyHubCoreAPIs:
    """Tests for core Money Strategy Hub APIs with valid guest ID"""

    def test_profile_get_no_profile(self):
        """GET profile should return has_profile=false for new user"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/profile",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "has_profile" in data
        print(f"PASS: GET profile returns 200, has_profile={data.get('has_profile')}")

    def test_profile_create(self):
        """POST profile should create/update profile"""
        response = requests.post(
            f"{BASE_URL}/api/money-strategy-hub/profile",
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "currency": "USD",
                "monthly_income": 5000,
                "fixed_monthly_expenses": 2000,
                "savings_target_monthly": 500,
                "risk_tolerance": "moderate"
            },
            headers=HEADERS
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "profile" in data
        assert data["profile"]["currency"] == "USD"
        print("PASS: POST profile creates profile successfully")

    def test_budgets_list(self):
        """GET budgets should return list"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/budgets",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "budgets" in data
        assert "count" in data
        print(f"PASS: GET budgets returns 200, count={data.get('count')}")

    def test_budget_create(self):
        """POST budget should create budget"""
        response = requests.post(
            f"{BASE_URL}/api/money-strategy-hub/budgets",
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "name": "Test Budget Feature9",
                "category": "food",
                "monthly_limit": 500
            },
            headers=HEADERS
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "budget" in data
        assert data["budget"]["name"] == "Test Budget Feature9"
        print(f"PASS: POST budget creates budget, budget_id={data['budget'].get('budget_id')}")
        return data["budget"]["budget_id"]

    def test_expenses_list(self):
        """GET expenses should return list"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/expenses",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "expenses" in data
        assert "count" in data
        print(f"PASS: GET expenses returns 200, count={data.get('count')}")

    def test_expense_create(self):
        """POST expense should create expense"""
        response = requests.post(
            f"{BASE_URL}/api/money-strategy-hub/expenses",
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "amount": 25.50,
                "category": "food",
                "merchant": "Test Merchant Feature9"
            },
            headers=HEADERS
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "expense" in data
        assert data["expense"]["amount"] == 25.50
        print(f"PASS: POST expense creates expense, expense_id={data['expense'].get('expense_id')}")

    def test_savings_goals_list(self):
        """GET savings-goals should return list"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/savings-goals",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "goals" in data
        assert "count" in data
        print(f"PASS: GET savings-goals returns 200, count={data.get('count')}")

    def test_savings_goal_create(self):
        """POST savings-goal should create goal"""
        response = requests.post(
            f"{BASE_URL}/api/money-strategy-hub/savings-goals",
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "title": "Test Goal Feature9",
                "target_amount": 1000
            },
            headers=HEADERS
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "goal" in data
        assert data["goal"]["title"] == "Test Goal Feature9"
        print(f"PASS: POST savings-goal creates goal, goal_id={data['goal'].get('goal_id')}")

    def test_expenses_analytics(self):
        """GET expenses/analytics should return analytics"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/expenses/analytics",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "summary" in data
        assert "top_categories" in data
        print("PASS: GET expenses/analytics returns 200")

    def test_portfolio_positions_list(self):
        """GET portfolio/positions should return list"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/portfolio/positions",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "positions" in data
        assert "count" in data
        print(f"PASS: GET portfolio/positions returns 200, count={data.get('count')}")

    def test_portfolio_analytics(self):
        """GET portfolio/analytics should return analytics"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/portfolio/analytics",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "summary" in data
        assert "allocation" in data
        print("PASS: GET portfolio/analytics returns 200")

    def test_bill_reminders_list(self):
        """GET bill-reminders should return list"""
        response = requests.get(
            f"{BASE_URL}/api/money-strategy-hub/bill-reminders",
            params={"fallback_user_id": VALID_GUEST_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "bill_reminders" in data
        assert "count" in data
        print(f"PASS: GET bill-reminders returns 200, count={data.get('count')}")


class TestMoneyStrategyHubPublicContract:
    """Tests for public API contract"""

    def test_money_strategy_hub_prefix_is_public(self):
        """Verify /api/money-strategy-hub/ is in public API contract"""
        import sys
        sys.path.insert(0, "/app")
        from backend.utils.public_api_contract import PUBLIC_API_PREFIXES, is_public_api_path
        
        assert "/api/money-strategy-hub/" in PUBLIC_API_PREFIXES, \
            "/api/money-strategy-hub/ should be in PUBLIC_API_PREFIXES"
        
        # Test that paths are recognized as public
        assert is_public_api_path("/api/money-strategy-hub/bootstrap") is True
        assert is_public_api_path("/api/money-strategy-hub/profile") is True
        assert is_public_api_path("/api/money-strategy-hub/budgets") is True
        print("PASS: /api/money-strategy-hub/ is in public API contract")


class TestMoneyStrategyHubAIAdvisor:
    """Tests for AI advisor endpoint"""

    def test_ai_advisor_run(self):
        """POST ai-advisor should return advice (may take a few seconds)"""
        response = requests.post(
            f"{BASE_URL}/api/money-strategy-hub/ai-advisor",
            json={
                "fallback_user_id": VALID_GUEST_ID,
                "question": "How should I optimize my savings?",
                "planning_horizon_months": 6,
                "include_investment": True
            },
            headers=HEADERS,
            timeout=30  # AI calls may take longer
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "run" in data
        assert "advice" in data["run"]
        print("PASS: POST ai-advisor returns 200 with advice")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
