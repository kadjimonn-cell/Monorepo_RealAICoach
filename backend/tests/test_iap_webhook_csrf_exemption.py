"""
IAP Webhook CSRF Exemption Verification Tests

Verifies that /api/iap/apple/webhook and /api/iap/google/webhook are properly
exempted from CSRF protection (X-Requested-With header requirement).

This test was created to verify the fix for the minor issues identified in
iteration_640.json where these endpoints were not in CSRF_EXEMPT_PREFIXES.
"""

import os
import pytest
import requests
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def api_client_no_csrf():
    """Requests session WITHOUT X-Requested-With header (simulates real webhook calls)"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json"
        # Intentionally NO X-Requested-With header
    })
    return session


@pytest.fixture(scope="module")
def api_client_with_csrf():
    """Requests session WITH X-Requested-With header (for comparison)"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    return session


class TestIAPWebhookCSRFExemption:
    """Test that IAP webhook endpoints are properly CSRF-exempt"""

    def test_apple_iap_webhook_without_csrf_header(self, api_client_no_csrf):
        """
        Apple IAP webhook should work WITHOUT X-Requested-With header.
        
        This verifies the fix: /api/iap/apple/webhook is now in CSRF_EXEMPT_PREFIXES.
        Before the fix, this would return 403 CSRF_BLOCKED.
        """
        response = api_client_no_csrf.post(f"{BASE_URL}/api/iap/apple/webhook", json={
            "signedPayload": "test_payload"
        })
        
        # Should NOT return 403 CSRF_BLOCKED
        assert response.status_code != 403 or "CSRF" not in response.text, \
            f"Apple IAP webhook should be CSRF-exempt, got {response.status_code}: {response.text[:200]}"
        
        # Should return 200 (acknowledged) for any payload
        assert response.status_code == 200, \
            f"Apple IAP webhook should acknowledge request, got {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        assert "received" in data or "status" in data, \
            f"Apple IAP webhook should return acknowledgment, got {data}"
        print(f"✓ Apple IAP webhook CSRF exemption verified: {response.status_code}")

    def test_google_iap_webhook_without_csrf_header(self, api_client_no_csrf):
        """
        Google IAP webhook should work WITHOUT X-Requested-With header.
        
        This verifies the fix: /api/iap/google/webhook is now in CSRF_EXEMPT_PREFIXES.
        Before the fix, this would return 403 CSRF_BLOCKED.
        """
        response = api_client_no_csrf.post(f"{BASE_URL}/api/iap/google/webhook", json={
            "message": {
                "data": "test_data"
            }
        })
        
        # Should NOT return 403 CSRF_BLOCKED
        assert response.status_code != 403 or "CSRF" not in response.text, \
            f"Google IAP webhook should be CSRF-exempt, got {response.status_code}: {response.text[:200]}"
        
        # Should return 200 (acknowledged) for any payload
        assert response.status_code == 200, \
            f"Google IAP webhook should acknowledge request, got {response.status_code}: {response.text[:200]}"
        
        data = response.json()
        assert "received" in data or "status" in data, \
            f"Google IAP webhook should return acknowledgment, got {data}"
        print(f"✓ Google IAP webhook CSRF exemption verified: {response.status_code}")

    def test_apple_iap_webhook_with_csrf_header_still_works(self, api_client_with_csrf):
        """Apple IAP webhook should also work WITH X-Requested-With header"""
        response = api_client_with_csrf.post(f"{BASE_URL}/api/iap/apple/webhook", json={
            "signedPayload": "test_payload"
        })
        
        assert response.status_code == 200, \
            f"Apple IAP webhook should work with CSRF header too, got {response.status_code}"
        print(f"✓ Apple IAP webhook works with CSRF header: {response.status_code}")

    def test_google_iap_webhook_with_csrf_header_still_works(self, api_client_with_csrf):
        """Google IAP webhook should also work WITH X-Requested-With header"""
        response = api_client_with_csrf.post(f"{BASE_URL}/api/iap/google/webhook", json={
            "message": {
                "data": "test_data"
            }
        })
        
        assert response.status_code == 200, \
            f"Google IAP webhook should work with CSRF header too, got {response.status_code}"
        print(f"✓ Google IAP webhook works with CSRF header: {response.status_code}")


class TestOtherWebhooksCSRFExemption:
    """Verify other payment webhooks remain CSRF-exempt (regression check)"""

    def test_stripe_webhook_csrf_exempt(self, api_client_no_csrf):
        """Stripe webhook should be CSRF-exempt"""
        response = api_client_no_csrf.post(f"{BASE_URL}/api/webhook/stripe", json={})
        # Should return 400 (invalid signature) not 403 (CSRF blocked)
        assert response.status_code != 403 or "CSRF" not in response.text, \
            f"Stripe webhook should be CSRF-exempt, got {response.status_code}"
        print(f"✓ Stripe webhook CSRF exemption verified: {response.status_code}")

    def test_paypal_webhook_csrf_exempt(self, api_client_no_csrf):
        """PayPal webhook should be CSRF-exempt"""
        response = api_client_no_csrf.post(f"{BASE_URL}/api/webhook/paypal", json={})
        # Should return 200 (acknowledged) not 403 (CSRF blocked)
        assert response.status_code == 200, \
            f"PayPal webhook should be CSRF-exempt, got {response.status_code}"
        print(f"✓ PayPal webhook CSRF exemption verified: {response.status_code}")

    def test_fedapay_webhook_csrf_exempt(self, api_client_no_csrf):
        """FedaPay webhook should be CSRF-exempt"""
        response = api_client_no_csrf.post(f"{BASE_URL}/api/payments/fedapay/webhook", json={})
        # Should return 200 (acknowledged) not 403 (CSRF blocked)
        assert response.status_code == 200, \
            f"FedaPay webhook should be CSRF-exempt, got {response.status_code}"
        print(f"✓ FedaPay webhook CSRF exemption verified: {response.status_code}")


class TestUnifiedExpiryNotificationRegression:
    """Regression tests to ensure unified expiry notification still works"""

    def test_health_endpoint(self, api_client_no_csrf):
        """Health endpoint should be accessible"""
        response = api_client_no_csrf.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        print(f"✓ Health endpoint accessible: {response.status_code}")

    def test_iap_products_endpoint(self, api_client_no_csrf):
        """IAP products endpoint should be accessible (public)"""
        response = api_client_no_csrf.get(f"{BASE_URL}/api/iap/products")
        assert response.status_code == 200, f"IAP products endpoint failed: {response.status_code}"
        data = response.json()
        assert "products" in data, f"IAP products should return products list: {data}"
        print(f"✓ IAP products endpoint accessible: {response.status_code}")

    def test_subscription_plans_endpoint(self, api_client_no_csrf):
        """Subscription plans endpoint should be accessible (public)"""
        response = api_client_no_csrf.get(f"{BASE_URL}/api/subscriptions/plans")
        assert response.status_code == 200, f"Subscription plans endpoint failed: {response.status_code}"
        print(f"✓ Subscription plans endpoint accessible: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
