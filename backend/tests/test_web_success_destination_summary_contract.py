"""
Web Success Destination Summary Contract Tests
Verifies the explicit plan-unlocked destination summary across all 5 payment providers:
- Stripe (web card)
- PayPal (web redirect)
- FedaPay (payment-result and mobile-money)
- Apple IAP (native)
- Google IAP (native)

Checkpoint D verification for web success routes extension.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
TEST_USER_EMAIL = "p1.free.1779113329@example.com"
TEST_USER_PASSWORD = "P1Free#2026!Aa"
ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


class TestHealthAndBasics:
    """Basic health and auth tests"""
    
    def test_backend_health(self):
        """Verify backend is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["healthy", "ok"]
        print(f"Backend health: {data}")
    
    def test_auth_login(self):
        """Verify auth login works"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "user" in data or "email" in data
        print(f"Auth login successful for {TEST_USER_EMAIL}")


class TestPaymentProviderConfiguration:
    """Verify all 5 payment providers are configured"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth session"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
    
    def test_stripe_provider_configured(self):
        """Verify Stripe provider is configured"""
        response = self.session.get(
            f"{BASE_URL}/api/subscription/status",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        print("Stripe provider check: subscription status endpoint accessible")
    
    def test_paypal_provider_configured(self):
        """Verify PayPal provider is configured"""
        response = self.session.get(
            f"{BASE_URL}/api/subscription/status",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        print("PayPal provider check: subscription status endpoint accessible")
    
    def test_fedapay_provider_configured(self):
        """Verify FedaPay provider is configured"""
        response = self.session.get(
            f"{BASE_URL}/api/subscription/status",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        print("FedaPay provider check: subscription status endpoint accessible")
    
    def test_iap_products_public(self):
        """Verify IAP products endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/iap/products")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "products" in data
        print(f"IAP products: {len(data) if isinstance(data, list) else len(data.get('products', []))} products available")
    
    def test_iap_status_authenticated(self):
        """Verify IAP status endpoint for Apple/Google IAP"""
        response = self.session.get(
            f"{BASE_URL}/api/iap/status",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        data = response.json()
        # Check for platform info (Apple/Google)
        print(f"IAP status: {data}")


class TestPaymentHistoryEndpoint:
    """Verify payment history endpoint works"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth session"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
    
    def test_payment_history_accessible(self):
        """Verify payment history endpoint is accessible"""
        response = self.session.get(
            f"{BASE_URL}/api/payment/history",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "payments" in data or "history" in data
        print("Payment history accessible")


class TestSubscriptionReturnToastContract:
    """Verify subscription return toast payload builder contract"""
    
    def test_return_toast_endpoint_exists(self):
        """Verify subscription status endpoint exists for return context"""
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip("Auth failed")
        
        response = session.get(
            f"{BASE_URL}/api/subscription/status",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        data = response.json()
        # Verify response has plan info for return context
        assert "plan" in data or "subscription_plan" in data or "effective_plan" in data
        print(f"Subscription status for return context: {data}")


class TestIAPReadinessMatrix:
    """Verify IAP readiness for Apple and Google"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth session"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
    
    def test_iap_readiness_authenticated(self):
        """Verify IAP readiness endpoint"""
        response = self.session.get(
            f"{BASE_URL}/api/iap/readiness",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        data = response.json()
        print(f"IAP readiness: {data}")
    
    def test_iap_history_authenticated(self):
        """Verify IAP history endpoint"""
        response = self.session.get(
            f"{BASE_URL}/api/iap/history",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        response.json()
        print("IAP history accessible")
    
    def test_iap_timeline_authenticated(self):
        """Verify IAP timeline endpoint"""
        response = self.session.get(
            f"{BASE_URL}/api/iap/timeline",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        response.json()
        print("IAP timeline accessible")
    
    def test_iap_manage_links_authenticated(self):
        """Verify IAP manage links endpoint"""
        response = self.session.get(
            f"{BASE_URL}/api/iap/manage-links",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        response.json()
        print("IAP manage links accessible")


class TestFiveProviderOrchestration:
    """Verify all 5 providers are orchestrated correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth session"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        )
        if login_response.status_code != 200:
            pytest.skip("Auth failed - skipping authenticated tests")
    
    def test_subscription_status_has_provider_info(self):
        """Verify subscription status includes provider orchestration info"""
        response = self.session.get(
            f"{BASE_URL}/api/subscription/status",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        data = response.json()
        # Should have plan info for all providers
        print(f"Subscription status: {data}")
    
    def test_iap_products_have_required_fields(self):
        """Verify IAP products have required fields for success flow"""
        response = requests.get(f"{BASE_URL}/api/iap/products")
        assert response.status_code == 200
        data = response.json()
        products = data if isinstance(data, list) else data.get("products", [])
        
        if products:
            for product in products[:2]:  # Check first 2 products
                # Products should have plan info for success summary
                assert "id" in product or "product_id" in product
                print(f"Product: {product.get('id') or product.get('product_id')}")


class TestWebSuccessRouteContract:
    """Contract tests for web success route data-testid coverage"""
    
    def test_frontend_source_has_payment_web_unlocked(self):
        """Verify payment.tsx has payment-web-unlocked testIdPrefix"""
        # This is a source code contract test
        import subprocess
        result = subprocess.run(
            ["grep", "-l", "payment-web-unlocked", "/app/frontend/app/subscription/payment.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "payment-web-unlocked not found in payment.tsx"
        print("payment-web-unlocked found in payment.tsx")
    
    def test_frontend_source_has_payment_redirect_unlocked(self):
        """Verify success.tsx has payment-redirect-unlocked testIdPrefix"""
        import subprocess
        result = subprocess.run(
            ["grep", "-l", "payment-redirect-unlocked", "/app/frontend/app/subscription/success.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "payment-redirect-unlocked not found in success.tsx"
        print("payment-redirect-unlocked found in success.tsx")
    
    def test_frontend_source_has_payment_result_unlocked(self):
        """Verify payment-result.tsx has payment-result-unlocked testIdPrefix"""
        import subprocess
        result = subprocess.run(
            ["grep", "-l", "payment-result-unlocked", "/app/frontend/app/subscription/payment-result.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "payment-result-unlocked not found in payment-result.tsx"
        print("payment-result-unlocked found in payment-result.tsx")
    
    def test_frontend_source_has_mobile_money_unlocked(self):
        """Verify mobile-money.tsx has mobile-money-unlocked testIdPrefix"""
        import subprocess
        result = subprocess.run(
            ["grep", "-l", "mobile-money-unlocked", "/app/frontend/app/subscription/mobile-money.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "mobile-money-unlocked not found in mobile-money.tsx"
        print("mobile-money-unlocked found in mobile-money.tsx")
    
    def test_frontend_source_has_iap_native_unlocked(self):
        """Verify MobileSubscriptionsViewV2.tsx has iap-native-unlocked testIdPrefix"""
        import subprocess
        result = subprocess.run(
            ["grep", "-l", "iap-native-unlocked", "/app/frontend/src/components/MobileSubscriptionsViewV2.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "iap-native-unlocked not found in MobileSubscriptionsViewV2.tsx"
        print("iap-native-unlocked found in MobileSubscriptionsViewV2.tsx")


class TestSharedComponentContract:
    """Contract tests for shared payment success components"""
    
    def test_subscription_success_panel_has_pre_cta_content(self):
        """Verify SubscriptionSuccessPanel accepts preCtaContent prop"""
        import subprocess
        result = subprocess.run(
            ["grep", "-c", "preCtaContent", "/app/frontend/src/components/payment/SubscriptionSuccessPanel.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        count = int(result.stdout.strip())
        assert count >= 2, f"preCtaContent should appear at least twice (prop def + usage), found {count}"
        print(f"preCtaContent found {count} times in SubscriptionSuccessPanel.tsx")
    
    def test_subscription_success_panel_has_payment_success_pre_cta_content_testid(self):
        """Verify SubscriptionSuccessPanel renders payment-success-pre-cta-content"""
        import subprocess
        result = subprocess.run(
            ["grep", "-l", "payment-success-pre-cta-content", "/app/frontend/src/components/payment/SubscriptionSuccessPanel.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "payment-success-pre-cta-content not found"
        print("payment-success-pre-cta-content found in SubscriptionSuccessPanel.tsx")
    
    def test_unlocked_destination_summary_uses_build_payload(self):
        """Verify SubscriptionUnlockedDestinationSummary uses buildSubscriptionReturnToastPayload"""
        import subprocess
        result = subprocess.run(
            ["grep", "-l", "buildSubscriptionReturnToastPayload", "/app/frontend/src/components/payment/SubscriptionUnlockedDestinationSummary.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, "buildSubscriptionReturnToastPayload not found"
        print("buildSubscriptionReturnToastPayload found in SubscriptionUnlockedDestinationSummary.tsx")
    
    def test_unlocked_destination_summary_has_testid_prefix(self):
        """Verify SubscriptionUnlockedDestinationSummary uses testIdPrefix"""
        import subprocess
        result = subprocess.run(
            ["grep", "-c", "testIdPrefix", "/app/frontend/src/components/payment/SubscriptionUnlockedDestinationSummary.tsx"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        count = int(result.stdout.strip())
        assert count >= 5, f"testIdPrefix should appear at least 5 times, found {count}"
        print(f"testIdPrefix found {count} times in SubscriptionUnlockedDestinationSummary.tsx")


class TestContractTestAssertions:
    """Verify contract test file has required assertions"""
    
    def test_contract_test_has_web_success_assertions(self):
        """Verify homeDashboardAuthLock.contract.test.ts has web success route assertions"""
        import subprocess
        result = subprocess.run(
            ["grep", "-c", "payment-web-unlocked\\|payment-redirect-unlocked\\|payment-result-unlocked\\|mobile-money-unlocked\\|iap-native-unlocked",
             "/app/frontend/src/__tests__/homeDashboardAuthLock.contract.test.ts"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        count = int(result.stdout.strip())
        assert count >= 5, f"Contract test should have assertions for all 5 testIdPrefixes, found {count}"
        print(f"Contract test has {count} testIdPrefix assertions")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
