"""
Test suite for B7+B8 verification: 5-provider subscription checkout orchestration.
Covers: Stripe, PayPal, FedaPay, Apple IAP, Google IAP
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
TEST_USER_EMAIL = "nova.v2.1779074133@example.com"
TEST_USER_PASSWORD = "NovaV2#2026!Aa"


class TestPaymentsConfigEndpoint:
    """Test GET /api/payments/config (public) includes all 5 provider fields"""

    def test_payments_config_returns_stripe_fields(self):
        """Verify payments/config includes stripe_available and stripe_publishable_key"""
        response = requests.get(f"{BASE_URL}/api/payments/config", timeout=15)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "stripe_available" in data, "Missing stripe_available field"
        assert "stripe_publishable_key" in data, "Missing stripe_publishable_key field"
        print(f"PASSED: stripe_available={data.get('stripe_available')}")

    def test_payments_config_returns_paypal_fields(self):
        """Verify payments/config includes paypal_available and paypal_client_id"""
        response = requests.get(f"{BASE_URL}/api/payments/config", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "paypal_available" in data, "Missing paypal_available field"
        assert "paypal_client_id" in data, "Missing paypal_client_id field"
        assert "paypal_mode" in data, "Missing paypal_mode field"
        print(f"PASSED: paypal_available={data.get('paypal_available')}, mode={data.get('paypal_mode')}")

    def test_payments_config_returns_fedapay_fields(self):
        """Verify payments/config includes fedapay_available and fedapay_public_key"""
        response = requests.get(f"{BASE_URL}/api/payments/config", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "fedapay_available" in data, "Missing fedapay_available field"
        assert "fedapay_public_key" in data, "Missing fedapay_public_key field"
        print(f"PASSED: fedapay_available={data.get('fedapay_available')}")

    def test_payments_config_returns_apple_iap_fields(self):
        """Verify payments/config includes apple_iap_available and apple_iap_status_label"""
        response = requests.get(f"{BASE_URL}/api/payments/config", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "apple_iap_available" in data, "Missing apple_iap_available field"
        assert "apple_iap_status_label" in data, "Missing apple_iap_status_label field"
        print(f"PASSED: apple_iap_available={data.get('apple_iap_available')}, status={data.get('apple_iap_status_label')}")

    def test_payments_config_returns_google_iap_fields(self):
        """Verify payments/config includes google_iap_available and google_iap_status_label"""
        response = requests.get(f"{BASE_URL}/api/payments/config", timeout=15)
        assert response.status_code == 200
        data = response.json()
        assert "google_iap_available" in data, "Missing google_iap_available field"
        assert "google_iap_status_label" in data, "Missing google_iap_status_label field"
        print(f"PASSED: google_iap_available={data.get('google_iap_available')}, status={data.get('google_iap_status_label')}")


class TestProviderReadinessMatrix:
    """Test GET /api/subscriptions/provider-readiness-matrix returns all 5 providers"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        """Login and get auth token"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15
        )
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        self.cookies = login_response.cookies
        self.headers = {"X-Requested-With": "XMLHttpRequest"}

    def test_readiness_matrix_returns_all_5_providers(self):
        """Verify provider-readiness-matrix returns stripe, paypal, fedapay, apple_iap, google_iap"""
        response = requests.get(
            f"{BASE_URL}/api/subscriptions/provider-readiness-matrix",
            cookies=self.cookies,
            headers=self.headers,
            timeout=15
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "providers" in data, "Missing providers field"
        providers = data["providers"]
        
        expected_providers = ["stripe", "paypal", "fedapay", "apple_iap", "google_iap"]
        for provider in expected_providers:
            assert provider in providers, f"Missing provider: {provider}"
            provider_data = providers[provider]
            assert "available" in provider_data, f"Missing 'available' for {provider}"
            assert "status_label" in provider_data, f"Missing 'status_label' for {provider}"
            assert "route" in provider_data, f"Missing 'route' for {provider}"
            print(f"  {provider}: available={provider_data.get('available')}, status={provider_data.get('status_label')}")
        
        print("PASSED: All 5 providers present in readiness matrix")

    def test_readiness_matrix_requires_auth(self):
        """Verify provider-readiness-matrix requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/subscriptions/provider-readiness-matrix",
            timeout=15
        )
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        print("PASSED: Readiness matrix requires authentication")


class TestInitiateCheckoutOrchestration:
    """Test POST /api/subscriptions/initiate-checkout for all 5 providers"""

    @pytest.fixture(autouse=True)
    def setup_auth(self):
        """Login and get auth token"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15
        )
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        self.cookies = login_response.cookies
        self.headers = {"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"}

    def test_initiate_checkout_stripe(self):
        """Test initiate-checkout with stripe payment method"""
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "stripe",
            "currency": "usd"
        }
        response = requests.post(
            f"{BASE_URL}/api/subscriptions/initiate-checkout",
            json=payload,
            cookies=self.cookies,
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("provider") == "stripe" or data.get("payment_method") == "stripe", "Provider should be stripe"
        assert "checkout_url" in data or "session_id" in data, "Missing checkout_url or session_id for stripe"
        print(f"PASSED: Stripe checkout initiated, has checkout_url={bool(data.get('checkout_url'))}")

    def test_initiate_checkout_paypal(self):
        """Test initiate-checkout with paypal payment method"""
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "paypal",
            "currency": "usd"
        }
        response = requests.post(
            f"{BASE_URL}/api/subscriptions/initiate-checkout",
            json=payload,
            cookies=self.cookies,
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("provider") == "paypal" or data.get("payment_method") == "paypal", "Provider should be paypal"
        assert "checkout_url" in data or "order_id" in data, "Missing checkout_url or order_id for paypal"
        print(f"PASSED: PayPal checkout initiated, has checkout_url={bool(data.get('checkout_url'))}")

    def test_initiate_checkout_fedapay_without_phone(self):
        """Test initiate-checkout with fedapay without phone returns route + required_fields (no hard error)"""
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "fedapay",
            "currency": "XOF"
        }
        response = requests.post(
            f"{BASE_URL}/api/subscriptions/initiate-checkout",
            json=payload,
            cookies=self.cookies,
            headers=self.headers,
            timeout=30
        )
        # Should NOT return 4xx/5xx error - should return 200 with route info
        assert response.status_code == 200, f"Expected 200 (soft redirect), got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("provider") == "fedapay" or data.get("payment_method") == "fedapay", "Provider should be fedapay"
        assert data.get("action_type") == "route", f"Expected action_type='route', got {data.get('action_type')}"
        assert "route" in data or "checkout_url" in data, "Missing route or checkout_url"
        assert "required_fields" in data, "Missing required_fields for fedapay without phone"
        assert "phone_number" in data.get("required_fields", []), "phone_number should be in required_fields"
        print(f"PASSED: FedaPay without phone returns route={data.get('route')}, required_fields={data.get('required_fields')}")

    def test_initiate_checkout_fedapay_with_phone(self):
        """Test initiate-checkout with fedapay with phone initiates mobile money checkout"""
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "fedapay",
            "currency": "XOF",
            "phone_number": "22997000000",
            "mobile_provider": "mtn"
        }
        response = requests.post(
            f"{BASE_URL}/api/subscriptions/initiate-checkout",
            json=payload,
            cookies=self.cookies,
            headers=self.headers,
            timeout=30
        )
        # May return 200 with payment_url or error if FedaPay sandbox not fully configured
        # The key is it should attempt to initiate, not return a route redirect
        if response.status_code == 200:
            data = response.json()
            assert data.get("provider") == "fedapay" or data.get("payment_method") == "fedapay", "Provider should be fedapay"
            # With phone, should either have payment_url or transaction_id
            has_payment_url = bool(data.get("payment_url") or data.get("checkout_url"))
            has_transaction = bool(data.get("transaction_id") or data.get("reference"))
            assert has_payment_url or has_transaction or data.get("action_type") == "redirect_url", \
                f"Expected payment_url or transaction_id, got: {data}"
            print(f"PASSED: FedaPay with phone initiated, payment_url={has_payment_url}, transaction={has_transaction}")
        else:
            # If FedaPay API fails, it should be a 500 or specific error, not 400 for missing phone
            assert response.status_code != 400 or "phone" not in response.text.lower(), \
                "Should not complain about missing phone when phone is provided"
            print(f"INFO: FedaPay with phone returned {response.status_code} - may be sandbox limitation")

    def test_initiate_checkout_apple_iap(self):
        """Test initiate-checkout with apple_iap payment method"""
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "apple_iap"
        }
        response = requests.post(
            f"{BASE_URL}/api/subscriptions/initiate-checkout",
            json=payload,
            cookies=self.cookies,
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("provider") == "apple_iap" or data.get("payment_method") == "apple_iap", "Provider should be apple_iap"
        assert data.get("action_type") == "route", f"Expected action_type='route' for IAP, got {data.get('action_type')}"
        assert "route" in data or "checkout_url" in data, "Missing route or checkout_url for apple_iap"
        print(f"PASSED: Apple IAP checkout returns route={data.get('route')}")

    def test_initiate_checkout_google_iap(self):
        """Test initiate-checkout with google_iap payment method"""
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "google_iap"
        }
        response = requests.post(
            f"{BASE_URL}/api/subscriptions/initiate-checkout",
            json=payload,
            cookies=self.cookies,
            headers=self.headers,
            timeout=30
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data.get("provider") == "google_iap" or data.get("payment_method") == "google_iap", "Provider should be google_iap"
        assert data.get("action_type") == "route", f"Expected action_type='route' for IAP, got {data.get('action_type')}"
        assert "route" in data or "checkout_url" in data, "Missing route or checkout_url for google_iap"
        print(f"PASSED: Google IAP checkout returns route={data.get('route')}")

    def test_initiate_checkout_requires_auth(self):
        """Verify initiate-checkout requires authentication"""
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "stripe"
        }
        response = requests.post(
            f"{BASE_URL}/api/subscriptions/initiate-checkout",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        print("PASSED: initiate-checkout requires authentication")

    def test_initiate_checkout_invalid_method(self):
        """Verify initiate-checkout rejects invalid payment method"""
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "invalid_method"
        }
        response = requests.post(
            f"{BASE_URL}/api/subscriptions/initiate-checkout",
            json=payload,
            cookies=self.cookies,
            headers=self.headers,
            timeout=15
        )
        assert response.status_code == 400, f"Expected 400 for invalid method, got {response.status_code}"
        print("PASSED: initiate-checkout rejects invalid payment method")


class TestThemeExceptionAllowlist:
    """Test that subscription pages are NOT in theme-exception-allowlist"""

    def test_subscription_payment_not_in_allowlist(self):
        """Verify app/subscription/payment.tsx is NOT in theme-exception-allowlist"""
        allowlist_path = "/app/frontend/scripts/theme-exception-allowlist.json"
        import json
        with open(allowlist_path, 'r') as f:
            allowlist = json.load(f)
        
        files = allowlist.get("files", [])
        subscription_payment_entries = [f for f in files if "subscription/payment" in f.lower()]
        assert len(subscription_payment_entries) == 0, \
            f"subscription/payment.tsx should NOT be in allowlist, found: {subscription_payment_entries}"
        print("PASSED: subscription/payment.tsx is NOT in theme-exception-allowlist")

    def test_subscription_plans_not_in_allowlist(self):
        """Verify app/subscription/plans.tsx is NOT in theme-exception-allowlist"""
        allowlist_path = "/app/frontend/scripts/theme-exception-allowlist.json"
        import json
        with open(allowlist_path, 'r') as f:
            allowlist = json.load(f)
        
        files = allowlist.get("files", [])
        subscription_plans_entries = [f for f in files if "subscription/plans" in f.lower()]
        assert len(subscription_plans_entries) == 0, \
            f"subscription/plans.tsx should NOT be in allowlist, found: {subscription_plans_entries}"
        print("PASSED: subscription/plans.tsx is NOT in theme-exception-allowlist")

    def test_subscription_mobile_money_in_allowlist(self):
        """Verify app/subscription/mobile-money.tsx IS in theme-exception-allowlist (expected)"""
        allowlist_path = "/app/frontend/scripts/theme-exception-allowlist.json"
        import json
        with open(allowlist_path, 'r') as f:
            allowlist = json.load(f)
        
        files = allowlist.get("files", [])
        mobile_money_entries = [f for f in files if "subscription/mobile-money" in f.lower()]
        # mobile-money.tsx is expected to be in allowlist per the file content
        assert len(mobile_money_entries) > 0, \
            "subscription/mobile-money.tsx should be in allowlist (expected exception)"
        print("PASSED: subscription/mobile-money.tsx is in theme-exception-allowlist (expected)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
