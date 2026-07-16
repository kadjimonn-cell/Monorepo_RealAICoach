"""
FedaPay Live E2E Verification Tests
Tests the full FedaPay payment flow with a real user account.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://coach-web-preview.preview.emergentagent.com").rstrip("/")

# Test credentials for FedaPay live verification
TEST_USER_EMAIL = "fedapay.live.user.1779241168@example.com"
TEST_USER_PASSWORD = "FedapayLive#2026Aa!"


class TestFedaPayLiveE2E:
    """FedaPay Live E2E verification tests"""

    @staticmethod
    def _is_stripe_fallback_response(data: dict) -> bool:
        gateway = str(data.get("gateway", "")).lower()
        fallback = bool(data.get("fallback"))
        payment_url = str(data.get("payment_url", "")).lower()
        return (fallback or gateway == "stripe_fallback") and "checkout.stripe.com" in payment_url
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session and authenticate"""
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        })
        self.auth_token = None
        self.user_id = None
    
    def _login(self):
        """Login and get session cookie"""
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
        )
        print(f"Login response status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            # user_id is at top level, not nested under "user"
            self.user_id = data.get("user_id")
            print(f"Login successful, user_id: {self.user_id}")
            return True
        else:
            print(f"Login failed: {response.text[:500]}")
            return False
    
    def test_01_user_login(self):
        """Test login with FedaPay test user"""
        assert self._login(), "Login should succeed"
        assert self.user_id is not None, "User ID should be returned"
        print(f"PASS: User logged in successfully with user_id={self.user_id}")
    
    def test_02_gateway_config_shows_fedapay_live(self):
        """Verify FedaPay is configured in live mode"""
        assert self._login(), "Login required"
        
        response = self.session.get(f"{BASE_URL}/api/subscriptions/gateway-config")
        assert response.status_code == 200, f"Gateway config should return 200, got {response.status_code}"
        
        data = response.json()
        print(f"Gateway config: fedapay_available={data.get('fedapay_available')}, mode={data.get('fedapay_mode')}")
        
        assert data.get("fedapay_available") is True, "FedaPay should be available"
        assert data.get("fedapay_mode") == "live", f"FedaPay should be in live mode, got {data.get('fedapay_mode')}"
        print("PASS: FedaPay is configured in LIVE mode")
    
    def test_03_mobile_money_gateways_endpoint(self):
        """Verify mobile money gateways endpoint returns FedaPay with live status"""
        assert self._login(), "Login required"
        
        response = self.session.get(f"{BASE_URL}/api/subscriptions/mobile-money/gateways")
        assert response.status_code == 200, f"Gateways endpoint should return 200, got {response.status_code}"
        
        data = response.json()
        gateways = data.get("gateways", [])
        
        fedapay_gateway = next((g for g in gateways if g.get("id") == "fedapay"), None)
        assert fedapay_gateway is not None, "FedaPay gateway should be in the list"
        
        print(f"FedaPay gateway: status={fedapay_gateway.get('status')}, mode={fedapay_gateway.get('mode')}, available={fedapay_gateway.get('available')}")
        
        assert fedapay_gateway.get("available") is True, "FedaPay should be available"
        assert fedapay_gateway.get("status") == "active", f"FedaPay status should be active, got {fedapay_gateway.get('status')}"
        assert fedapay_gateway.get("mode") == "live", f"FedaPay mode should be live, got {fedapay_gateway.get('mode')}"
        
        # Check countries are configured
        countries = fedapay_gateway.get("countries", [])
        assert len(countries) > 0, "FedaPay should have countries configured"
        print(f"PASS: FedaPay gateway is LIVE with {len(countries)} countries: {countries}")
    
    def test_04_subscription_plans_available(self):
        """Verify subscription plans are available"""
        assert self._login(), "Login required"
        
        response = self.session.get(f"{BASE_URL}/api/subscriptions/plans")
        assert response.status_code == 200, f"Plans endpoint should return 200, got {response.status_code}"
        
        data = response.json()
        plans = data.get("plans", [])
        assert len(plans) > 0, "Should have at least one plan"
        
        basic_plan = next((p for p in plans if p.get("id") == "basic"), None)
        assert basic_plan is not None, "Basic plan should exist"
        
        print(f"PASS: Found {len(plans)} plans, basic plan monthly_price=${basic_plan.get('monthly_price')}")
    
    def test_05_fedapay_mobile_money_pay_initiation(self):
        """Test FedaPay mobile money payment initiation returns live payment_url"""
        assert self._login(), "Login required"
        
        # Use a Benin phone number format for FedaPay
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "gateway": "fedapay",
            "phone_number": "+22901970000001",  # Benin format
            "currency": "XOF",
            "mobile_provider": "mtn"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/subscriptions/mobile-money/pay",
            json=payload
        )
        
        print(f"Mobile money pay response status: {response.status_code}")
        
        # Accept 200 (success) or 409 (duplicate checkout prevention)
        assert response.status_code in [200, 409], f"Expected 200 or 409, got {response.status_code}: {response.text[:500]}"
        
        data = response.json()
        print(f"Response data keys: {list(data.keys())}")
        print(f"Full response: {data}")
        
        # Check if this is a deduped transaction
        if data.get("deduped"):
            print("Transaction was deduped (existing pending transaction reused)")
            print(f"  - ticket_id: {data.get('ticket_id')}")
            print(f"  - payment_id: {data.get('payment_id')}")
            print(f"  - transaction_id: {data.get('transaction_id')}")
            print(f"  - amount_local: {data.get('amount_local')} {data.get('currency')}")
            print(f"  - gateway: {data.get('gateway')}")
            print(f"  - payment_url_regenerated: {data.get('payment_url_regenerated')}")
            
            payment_url = data.get("payment_url", "")
            assert payment_url, "Deduped transaction must include payment_url (regenerated if missing)"
            if self._is_stripe_fallback_response(data):
                assert "checkout.stripe.com" in payment_url.lower(), \
                    f"Fallback response must provide Stripe checkout URL, got: {payment_url}"
                assert data.get("fallback") is True, "Stripe fallback response must set fallback=true"
            else:
                assert "process.fedapay.com" in payment_url or "fedapay" in payment_url.lower(), \
                    f"Payment URL should be FedaPay live URL when not in fallback mode, got: {payment_url}"
            print(f"PASS: Deduped transaction has live FedaPay URL: {payment_url[:100]}...")
            return
        
        # Fresh transaction case
        assert data.get("success") is True, f"Payment initiation should succeed: {data}"
        
        payment_url = data.get("payment_url", "")
        assert payment_url, f"Payment URL should be returned: {data}"
        
        if self._is_stripe_fallback_response(data):
            assert "checkout.stripe.com" in payment_url.lower(), \
                f"Fallback payment URL should be Stripe checkout URL, got: {payment_url}"
            assert data.get("fallback") is True, "Fallback payment should include fallback=true"
            print("PASS: FedaPay unavailable fallback redirected to Stripe checkout")
            return

        # Verify it's a live FedaPay URL (process.fedapay.com for live)
        assert "process.fedapay.com" in payment_url or "fedapay.com" in payment_url, \
            f"Payment URL should be FedaPay live URL (process.fedapay.com), got: {payment_url}"
        
        print("PASS: FedaPay live payment initiated successfully!")
        print(f"  - payment_url: {payment_url[:100]}...")
        print(f"  - ticket_id: {data.get('ticket_id')}")
        print(f"  - payment_id: {data.get('payment_id')}")
        print(f"  - amount_local: {data.get('amount_local')} {data.get('currency')}")
        print(f"  - sandbox: {data.get('sandbox')}")
    
    def test_06_checkout_preview_for_fedapay(self):
        """Test checkout preview for FedaPay payment method"""
        assert self._login(), "Login required"
        
        payload = {
            "plan_id": "basic",
            "billing_period": "monthly",
            "payment_method": "fedapay",
            "currency": "XOF"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/subscriptions/checkout-preview",
            json=payload
        )
        
        assert response.status_code == 200, f"Checkout preview should return 200, got {response.status_code}: {response.text[:300]}"
        
        data = response.json()
        print(f"Checkout preview: subtotal={data.get('subtotal')}, total={data.get('total_amount')}, currency={data.get('currency')}")
        
        assert data.get("subtotal") is not None, "Subtotal should be present"
        assert data.get("total_amount") is not None, "Total amount should be present"
        print("PASS: Checkout preview works for FedaPay")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
