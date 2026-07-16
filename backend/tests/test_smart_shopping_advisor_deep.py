"""Deep E2E Backend Tests for Feature 10: Smart Shopping Advisor

Test coverage:
    - Bootstrap (tier limits, usage counters)
- Wishlist Management (CRUD + items)
- Price Tracking Engine (alerts, history)
- AI Product Advisor (comparison, recommendations, reviews)
- Shopping Budget Tracker (CRUD, purchases, analytics)
- Deal & Coupon Finder (search, validation)
- Carbon Footprint Calculator (calculation, reports)
- Tier Limits Enforcement
- Guest vs Authenticated Flows
"""

import requests
import json
import sys
import os
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
TEST_EMAIL = "admin@realaicoach.app"
TEST_PASSWORD = "NewAdminPass2026!"


class TestSmartShoppingAdvisor:
    """Comprehensive backend test suite for Smart Shopping Advisor."""
    
    def __init__(self):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.user_id = None
        
        # Test data storage
        self.wishlist_id = None
        self.item_id = None
        self.alert_id = None
        self.budget_id = None
        self.purchase_id = None
        
        self.passed = 0
        self.failed = 0
        self.test_results = []

    def setup(self):
        """Authenticate and get session token."""
        print("\n" + "="*80)
        print("FEATURE 10: SMART SHOPPING ADVISOR - DEEP BACKEND E2E TESTS")
        print("="*80)
        
        print("\n[SETUP] Authenticating...")
        response = self.session.post(
            f"{self.base_url}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        if response.status_code != 200:
            print(f"❌ Login failed: {response.status_code}")
            print(f"Response: {response.text}")
            sys.exit(1)
        
        data = response.json()
        self.user_id = data.get("user_id")
        
        print(f"✅ Authenticated as: {TEST_EMAIL}")
        print(f"✅ User ID: {self.user_id}")
        print("✅ Session established")

    def log_test(self, name: str, passed: bool, message: str = ""):
        """Log test result."""
        if passed:
            self.passed += 1
            print(f"  ✅ {name}")
        else:
            self.failed += 1
            print(f"  ❌ {name}")
            if message:
                print(f"     Error: {message}")
        
        self.test_results.append({
            "test": name,
            "passed": passed,
            "message": message
        })

    def test_bootstrap(self):
        """Test 1: Bootstrap - Get tier limits and usage."""
        print("\n[TEST 1] Bootstrap API")
        
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/bootstrap")
        
        if response.status_code == 200:
            data = response.json()
            has_owner = "owner_id" in data
            has_tier = "tier" in data
            has_limits = "limits" in data
            has_usage = "usage" in data
            has_features = "features_available" in data

            self.log_test(
                "Bootstrap returns owner_id, tier, limits, usage, features",
                has_owner and has_tier and has_limits and has_usage and has_features,
                f"Missing fields: owner={has_owner}, tier={has_tier}, limits={has_limits}, usage={has_usage}, features={has_features}"
            )
        else:
            self.log_test("Bootstrap API", False, f"Status {response.status_code}: {response.text[:200]}")

    def test_wishlist_crud(self):
        """Test 2-4: Wishlist CRUD operations."""
        print("\n[TEST 2-4] Wishlist Management")
        
        # Test 2: Create wishlist
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/wishlists",
            json={
                "name": "Holiday Shopping 2026",
                "description": "Gifts for family",
                "items": [
                    {
                        "product_name": "Laptop",
                        "target_price": 1000.0,
                        "current_price": 1200.0,
                        "priority": "high"
                    }
                ]
            },
            headers={"Origin": self.base_url}
        )
        
        if response.status_code == 200:
            data = response.json()
            self.wishlist_id = data.get("wishlist_id")
            self.log_test("Create wishlist", self.wishlist_id is not None)
        else:
            self.log_test("Create wishlist", False, f"Status {response.status_code}")
        
        # Test 3: List wishlists
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/wishlists"
        )
        
        if response.status_code == 200:
            data = response.json()
            wishlists = data.get("wishlists", [])
            self.log_test("List wishlists", len(wishlists) > 0)
            
            # Store item_id for later tests
            if wishlists and wishlists[0].get("items"):
                self.item_id = wishlists[0]["items"][0]["item_id"]
        else:
            self.log_test("List wishlists", False, f"Status {response.status_code}")
        
        # Test 4: Get specific wishlist
        if self.wishlist_id:
            response = self.session.get(
                f"/api/smart-shopping-advisor/wishlists/{self.wishlist_id}"
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Get wishlist by ID", data.get("id") == self.wishlist_id)
            else:
                self.log_test("Get wishlist by ID", False, f"Status {response.status_code}")

    def test_wishlist_items(self):
        """Test 5-7: Wishlist item management."""
        print("\n[TEST 5-7] Wishlist Item Management")
        
        if not self.wishlist_id:
            print("  ⏭️  Skipping (no wishlist created)")
        return
        
                # Test 5: Add item to wishlist
        response = self.session.post(
            f"/api/smart-shopping-advisor/wishlists/{self.wishlist_id}/items",
            json={
                "product_name": "Wireless Headphones",
                "target_price": 150.0,
                "current_price": 180.0,
                "priority": "medium"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            new_item_id = data.get("item_id")
            self.log_test("Add item to wishlist", new_item_id is not None)
            if new_item_id:
                self.item_id = new_item_id
        else:
            self.log_test("Add item to wishlist", False, f"Status {response.status_code}")
        
        # Test 6: Update wishlist item
        if self.item_id:
            response = self.session.put(
                f"/api/smart-shopping-advisor/wishlists/{self.wishlist_id}/items/{self.item_id}",
                json={"current_price": 170.0, "notes": "Price dropped!"}
            )
            
            self.log_test("Update wishlist item", response.status_code == 200, 
                         f"Status {response.status_code}" if response.status_code != 200 else "")
        
        # Test 7: Delete wishlist item (we'll delete the first one, keep the second)
        if self.item_id:
            response = self.session.delete(
                f"/api/smart-shopping-advisor/wishlists/{self.wishlist_id}/items/{self.item_id}"
            )
            
            self.log_test("Delete wishlist item", response.status_code == 200,
                         f"Status {response.status_code}" if response.status_code != 200 else "")

    def test_price_alerts(self):
        """Test 8-10: Price alert system."""
        print("\n[TEST 8-10] Price Alert System")
        
        if not self.wishlist_id:
            print("  ⏭️  Skipping (no wishlist created)")
        return
        
                # Test 8: Create price alert
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/price-alerts",
            json={
                "wishlist_id": self.wishlist_id,
                "item_id": "test-item-123",
                "product_name": "Smart Watch",
                "target_price": 200.0,
                "current_price": 250.0,
                "alert_threshold_pct": 15.0
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.alert_id = data.get("alert_id")
            self.log_test("Create price alert", self.alert_id is not None)
        else:
            self.log_test("Create price alert", False, f"Status {response.status_code}")
        
        # Test 9: List price alerts
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/price-alerts"
        )
        
        if response.status_code == 200:
            data = response.json()
            alerts = data.get("alerts", [])
            self.log_test("List price alerts", len(alerts) > 0)
        else:
            self.log_test("List price alerts", False, f"Status {response.status_code}")
        
        # Test 10: Update price alert
        if self.alert_id:
            response = self.session.put(
                f"/api/smart-shopping-advisor/price-alerts/{self.alert_id}",
                json={"target_price": 190.0}
            )
            
            self.log_test("Update price alert", response.status_code == 200,
                         f"Status {response.status_code}" if response.status_code != 200 else "")

    def test_price_history(self):
        """Test 11-12: Price history tracking."""
        print("\n[TEST 11-12] Price History Tracking")
        
                # Test 11: Log price history
        test_item_id = "history-test-item-001"
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/price-history",
            json={
                "item_id": test_item_id,
                "product_name": "Gaming Console",
                "price": 499.99,
                "currency": "USD",
                "source": "user"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("Log price history", data.get("log_id") is not None)
        else:
            self.log_test("Log price history", False, f"Status {response.status_code}")
        
        # Test 12: Get price history
        response = self.session.get(
            f"/api/smart-shopping-advisor/price-history/{test_item_id}",
            params={"days": 30}
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("Get price history", "history" in data)
        else:
            self.log_test("Get price history", False, f"Status {response.status_code}")

    def test_ai_product_advisor(self):
        """Test 13-15: AI product advisor features."""
        print("\n[TEST 13-15] AI Product Advisor")
        
                # Test 13: Product comparison
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/product-compare",
            json={
                "products": [
                    {"name": "Laptop A", "price": 1000, "ram": "16GB", "cpu": "i7"},
                    {"name": "Laptop B", "price": 1200, "ram": "32GB", "cpu": "i9"}
                ],
                "comparison_criteria": ["price", "performance", "value"]
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("AI product comparison", "comparison" in data)
        else:
            self.log_test("AI product comparison", False, f"Status {response.status_code}")
        
        # Test 14: AI recommendation
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/ai-recommendation",
            json={
                "query": "Best laptop under $1000 for programming",
                "budget": 1000.0,
                "preferences": {"use_case": "software development"}
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("AI recommendation", "recommendation" in data)
        else:
            self.log_test("AI recommendation", False, f"Status {response.status_code}")
        
        # Test 15: Review analysis
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/review-analysis",
            json={
                "product_name": "XYZ Wireless Mouse",
                "reviews": [
                    "Great mouse, comfortable grip!",
                    "Battery life is excellent",
                    "A bit expensive but worth it"
                ]
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("AI review analysis", "analysis" in data)
        else:
            self.log_test("AI review analysis", False, f"Status {response.status_code}")

    def test_shopping_budgets(self):
        """Test 16-19: Shopping budget management."""
        print("\n[TEST 16-19] Shopping Budget Tracker")
        
                # Test 16: Create budget
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/budgets",
            json={
                "name": "Electronics Budget",
                "category": "electronics",
                "monthly_limit": 1000.0,
                "currency": "USD",
                "alert_threshold_pct": 80.0
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.budget_id = data.get("budget_id")
            self.log_test("Create shopping budget", self.budget_id is not None)
        else:
            self.log_test("Create shopping budget", False, f"Status {response.status_code}")
        
        # Test 17: List budgets
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/budgets"
        )
        
        if response.status_code == 200:
            data = response.json()
            budgets = data.get("budgets", [])
            self.log_test("List shopping budgets", len(budgets) > 0)
        else:
            self.log_test("List shopping budgets", False, f"Status {response.status_code}")
        
        # Test 18: Update budget
        if self.budget_id:
            response = self.session.put(
                f"/api/smart-shopping-advisor/budgets/{self.budget_id}",
                json={"monthly_limit": 1200.0}
            )
            
            self.log_test("Update shopping budget", response.status_code == 200,
                         f"Status {response.status_code}" if response.status_code != 200 else "")
        
        # Test 19: Log purchase
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/purchases",
            json={
                "budget_id": self.budget_id,
                "product_name": "Wireless Keyboard",
                "amount": 79.99,
                "currency": "USD",
                "merchant": "Amazon",
                "category": "electronics",
                "notes": "Mechanical keyboard"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.purchase_id = data.get("purchase_id")
            self.log_test("Log purchase", self.purchase_id is not None)
        else:
            self.log_test("Log purchase", False, f"Status {response.status_code}")

    def test_purchase_analytics(self):
        """Test 20-21: Purchase history and analytics."""
        print("\n[TEST 20-21] Purchase Analytics")
        
                # Test 20: Get purchase history
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/purchases",
            params={"limit": 50}
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("Get purchase history", "purchases" in data)
        else:
            self.log_test("Get purchase history", False, f"Status {response.status_code}")
        
        # Test 21: Get budget analytics
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/budget-analytics"
        )
        
        if response.status_code == 200:
            data = response.json()
            has_required = all(k in data for k in ["total_budget", "total_spent", "total_remaining", "budgets"])
            self.log_test("Get budget analytics", has_required)
        else:
            self.log_test("Get budget analytics", False, f"Status {response.status_code}")

    def test_deal_finder(self):
        """Test 22-24: Deal and coupon finder."""
        print("\n[TEST 22-24] Deal & Coupon Finder")
        
                # Test 22: Get deals
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/deals",
            params={"category": "electronics", "limit": 10}
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("Get deals", "deals" in data)
        else:
            self.log_test("Get deals", False, f"Status {response.status_code}")
        
        # Test 23: AI deal search
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/deals/search",
            json={
                "query": "laptop deals under $1000",
                "category": "electronics",
                "max_price": 1000.0
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("AI deal search", "deals" in data)
        else:
            self.log_test("AI deal search", False, f"Status {response.status_code}")
        
        # Test 24: Validate coupon
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/coupons/validate",
            json={
                "coupon_code": "SAVE20",
                "merchant": "Amazon"
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            self.log_test("Validate coupon", "validation" in data)
        else:
            self.log_test("Validate coupon", False, f"Status {response.status_code}")

    def test_carbon_footprint(self):
        """Test 25-26: Carbon footprint calculator."""
        print("\n[TEST 25-26] Carbon Footprint Calculator")
        
                # Test 25: Calculate carbon footprint
        response = self.session.post(f"{self.base_url}/api/smart-shopping-advisor/carbon-footprint",
            json={
                "product_name": "Laptop",
                "category": "electronics",
                "quantity": 1
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            has_carbon = "carbon_kg" in data
            self.log_test("Calculate carbon footprint", has_carbon)
        else:
            self.log_test("Calculate carbon footprint", False, f"Status {response.status_code}")
        
        # Test 26: Get carbon report
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/carbon-report"
        )
        
        if response.status_code == 200:
            data = response.json()
            has_report = all(k in data for k in ["month", "total_carbon_kg", "total_purchases"])
            self.log_test("Get carbon report", has_report)
        else:
            self.log_test("Get carbon report", False, f"Status {response.status_code}")

    def test_guest_flow(self):
        """Test 27: Guest user flow with fallback_user_id."""
        print("\n[TEST 27] Guest User Flow")
        
                # Test without authentication
        response = self.session.get(f"{self.base_url}/api/smart-shopping-advisor/bootstrap",
            params={"fallback_user_id": "guest-test-123"}
        )
        
        if response.status_code == 200:
            data = response.json()
            is_guest = data.get("user_id") == "guest-test-123"
            self.log_test("Guest user bootstrap", is_guest)
        else:
            self.log_test("Guest user bootstrap", False, f"Status {response.status_code}")

    def test_cleanup(self):
        """Test 28: Cleanup - Delete test data."""
        print("\n[TEST 28] Cleanup Test Data")
        
        cleanup_success = True
        
        # Delete price alert
        if self.alert_id:
            response = self.session.delete(
                f"/api/smart-shopping-advisor/price-alerts/{self.alert_id}"
            )
            if response.status_code != 200:
                cleanup_success = False
        
        # Delete budget (archive)
        if self.budget_id:
            response = self.session.delete(
                f"/api/smart-shopping-advisor/budgets/{self.budget_id}"
            )
            if response.status_code != 200:
                cleanup_success = False
        
        # Delete wishlist
        if self.wishlist_id:
            response = self.session.delete(
                f"/api/smart-shopping-advisor/wishlists/{self.wishlist_id}"
            )
            if response.status_code != 200:
                cleanup_success = False
        
        self.log_test("Cleanup test data", cleanup_success)

    async def run_all_tests(self):
        """Run complete test suite."""
        await self.setup()
        
        self.test_bootstrap()
        self.test_wishlist_crud()
        self.test_wishlist_items()
        self.test_price_alerts()
        self.test_price_history()
        self.test_ai_product_advisor()
        self.test_shopping_budgets()
        self.test_purchase_analytics()
        self.test_deal_finder()
        self.test_carbon_footprint()
        self.test_guest_flow()
        self.test_cleanup()
        
        self.print_summary()

    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"📊 Total:  {self.passed + self.failed}")
        print(f"📈 Success Rate: {(self.passed / (self.passed + self.failed) * 100):.1f}%")
        print("="*80)
        
        if self.failed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["passed"]:
                    print(f"  - {result['test']}: {result['message']}")
        
        print("\n" + "="*80)
        if self.failed == 0:
            print("✅ ALL TESTS PASSED - Feature 10 Backend is Production Ready!")
        else:
            print(f"⚠️  {self.failed} test(s) failed - Review and fix issues")
        print("="*80 + "\n")


def main():
    """Main test runner."""
    tester = TestSmartShoppingAdvisor()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
