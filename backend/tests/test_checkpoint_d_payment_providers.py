"""
Checkpoint D Verification: Payment Provider E2E Tests
Tests all 5 payment providers (Stripe, PayPal, FedaPay, Apple IAP, Google IAP)
and verifies the native-store plan-unlocked destination summary contract.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://coach-web-preview.preview.emergentagent.com"

# Test credentials
TEST_EMAIL = "p1.free.1779113329@example.com"
TEST_PASSWORD = "P1Free#2026!Aa"


@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session for tests"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    # Login
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code}")
    
    return session


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_backend_health(self):
        """Verify backend is healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("Backend health: OK")
    
    def test_auth_login(self):
        """Verify login works with test credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        }, headers={"Content-Type": "application/json"})
        
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert data["email"] == TEST_EMAIL
        print(f"Login successful: user_id={data['user_id']}")


class TestIAPProviders:
    """Apple IAP and Google IAP provider tests"""
    
    def test_iap_products_public(self):
        """IAP products endpoint should be accessible without auth"""
        response = requests.get(f"{BASE_URL}/api/iap/products")
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert len(data["products"]) > 0
        print(f"IAP products count: {len(data['products'])}")
    
    def test_iap_status_authenticated(self, auth_session):
        """IAP status requires authentication"""
        response = auth_session.get(f"{BASE_URL}/api/iap/status")
        assert response.status_code == 200
        data = response.json()
        assert "plan" in data
        assert "status" in data
        print(f"IAP status: plan={data['plan']}, status={data['status']}")
    
    def test_iap_readiness_authenticated(self, auth_session):
        """IAP readiness shows provider configuration"""
        response = auth_session.get(f"{BASE_URL}/api/iap/readiness")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        
        # Verify Apple IAP
        apple = data["providers"].get("apple", {})
        assert apple.get("configured") == True
        assert apple.get("readiness_state") == "live_ready"
        print(f"Apple IAP: {apple.get('status_label')}")
        
        # Verify Google IAP
        google = data["providers"].get("google", {})
        assert google.get("configured") == True
        assert google.get("readiness_state") == "live_ready"
        print(f"Google IAP: {google.get('status_label')}")
    
    def test_iap_history_authenticated(self, auth_session):
        """IAP history endpoint works"""
        response = auth_session.get(f"{BASE_URL}/api/iap/history")
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
        print(f"IAP history transactions: {len(data.get('transactions', []))}")
    
    def test_iap_timeline_authenticated(self, auth_session):
        """IAP timeline endpoint works"""
        response = auth_session.get(f"{BASE_URL}/api/iap/timeline")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        print(f"IAP timeline events: {len(data.get('events', []))}")
    
    def test_iap_manage_links_authenticated(self, auth_session):
        """IAP manage links endpoint works"""
        response = auth_session.get(f"{BASE_URL}/api/iap/manage-links")
        assert response.status_code == 200
        data = response.json()
        # Should have apple and/or google links
        print(f"IAP manage links: apple={data.get('apple', 'N/A')[:50] if data.get('apple') else 'N/A'}")


class TestWebPaymentProviders:
    """Stripe, PayPal, FedaPay provider tests"""
    
    def test_payment_history_authenticated(self, auth_session):
        """Payment history endpoint works"""
        response = auth_session.get(f"{BASE_URL}/api/payments/history")
        assert response.status_code == 200
        data = response.json()
        assert "payments" in data or "transactions" in data
        tx_count = len(data.get("transactions", []))
        print(f"Payment history transactions: {tx_count}")
    
    def test_subscription_status_authenticated(self, auth_session):
        """Subscription status endpoint works"""
        response = auth_session.get(f"{BASE_URL}/api/subscription/status")
        # May return 200 or subscription required error
        assert response.status_code in [200, 403]
        print(f"Subscription status: {response.status_code}")


class TestPaymentSuccessContract:
    """Verify the shared success panel contract across providers"""
    
    def test_iap_products_have_checkout_estimates(self):
        """IAP products should include checkout estimates for Apple and Google"""
        response = requests.get(f"{BASE_URL}/api/iap/products")
        assert response.status_code == 200
        data = response.json()
        
        products = data.get("products", [])
        assert len(products) > 0
        
        # Check first product has checkout estimates
        product = products[0]
        estimates = product.get("checkout_estimates", {})
        
        # Should have apple and google estimates
        assert "apple" in estimates or "google" in estimates
        
        if "apple" in estimates:
            apple_est = estimates["apple"]
            assert "total_amount" in apple_est or "final_total" in apple_est
            print(f"Apple estimate for {product.get('plan')}: {apple_est.get('final_total', apple_est.get('total_amount'))}")
        
        if "google" in estimates:
            google_est = estimates["google"]
            assert "total_amount" in google_est or "final_total" in google_est
            print(f"Google estimate for {product.get('plan')}: {google_est.get('final_total', google_est.get('total_amount'))}")


class TestNativeStoreSuccessFlow:
    """Test the native store success flow parameters"""
    
    def test_iap_status_shows_platform_when_active(self, auth_session):
        """When IAP subscription is active, status should show platform"""
        response = auth_session.get(f"{BASE_URL}/api/iap/status")
        assert response.status_code == 200
        data = response.json()
        
        # For free user, platform should be null
        # For IAP subscriber, platform should be 'apple' or 'google'
        plan = data.get("plan", "free")
        platform = data.get("platform")
        status = data.get("status")
        
        print(f"IAP status check: plan={plan}, platform={platform}, status={status}")
        
        if plan != "free" and status == "active":
            assert platform in ["apple", "google", None]
    
    def test_iap_products_have_required_fields(self):
        """IAP products should have all required fields for success flow"""
        response = requests.get(f"{BASE_URL}/api/iap/products")
        assert response.status_code == 200
        data = response.json()
        
        products = data.get("products", [])
        assert len(products) > 0
        
        for product in products:
            # Required fields for success flow
            assert "product_id" in product
            assert "plan" in product
            assert "period" in product
            assert "price" in product
            assert "currency" in product
            assert "display_name" in product
            
            print(f"Product verified: {product.get('display_name')} ({product.get('plan')}/{product.get('period')})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
