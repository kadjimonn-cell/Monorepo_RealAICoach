"""
Payment Non-Success Notification Parity Test Suite

Tests that all 5 payment providers (Stripe, PayPal, FedaPay, Apple IAP, Google IAP)
have proper non-success/failure/cancelled/pending/unknown notification behavior.

This verifies the Checkpoint C implementation for payment provider audit/fix.
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestBackendHealth:
    """Verify backend is accessible before running payment tests."""

    def test_backend_health(self):
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Backend health check passed")


class TestStripeNonSuccessNotifications:
    """Verify Stripe non-success path has notification behavior."""

    def test_stripe_routes_file_has_failed_notification_handling(self):
        """Stripe webhook should handle PAYMENT FAILED / EXPIRED states with notifications."""
        stripe_routes_path = "/app/backend/routes/payments_stripe_routes.py"
        with open(stripe_routes_path, "r") as f:
            content = f.read()

        # Check for failed/expired payment handling
        assert "PAYMENT FAILED" in content or "payment_status" in content, "Stripe routes should handle payment status"
        assert "payment_failed" in content.lower() or "failed" in content.lower(), "Stripe should handle failed payments"
        assert "notification" in content.lower(), "Stripe should have notification handling"
        assert "create_notification" in content, "Stripe should create in-app notifications for failures"
        print("✓ Stripe routes have failed payment notification handling")

    def test_stripe_webhook_handles_failed_expired_states(self):
        """Stripe webhook should handle failed and expired checkout sessions."""
        stripe_routes_path = "/app/backend/routes/payments_stripe_routes.py"
        with open(stripe_routes_path, "r") as f:
            content = f.read()

        # Check for specific failure handling
        assert "payment_status" in content, "Stripe should track payment_status"
        assert "expired" in content.lower(), "Stripe should handle expired sessions"
        print("✓ Stripe webhook handles failed/expired states")


class TestPayPalNonSuccessNotifications:
    """Verify PayPal non-success path has notification behavior."""

    def test_paypal_routes_has_failure_webhook_events(self):
        """PayPal webhook should handle BILLING.SUBSCRIPTION.PAYMENT.FAILED and related events."""
        paypal_routes_path = "/app/backend/routes/payments_paypal_routes.py"
        with open(paypal_routes_path, "r") as f:
            content = f.read()

        # Check for failure webhook events
        assert "BILLING.SUBSCRIPTION.PAYMENT.FAILED" in content, "PayPal should handle subscription payment failed"
        assert "BILLING.SUBSCRIPTION.CANCELLED" in content, "PayPal should handle subscription cancelled"
        assert "PAYMENT.SALE.REVERSED" in content, "PayPal should handle payment reversed"
        assert "PAYMENT.SALE.REFUNDED" in content, "PayPal should handle payment refunded"
        print("✓ PayPal routes handle failure/cancelled/refund webhook events")

    def test_paypal_failure_creates_user_notification(self):
        """PayPal failure events should create in-app notifications for users."""
        paypal_routes_path = "/app/backend/routes/payments_paypal_routes.py"
        with open(paypal_routes_path, "r") as f:
            content = f.read()

        # Check for notification insertion on failure
        assert "db.notifications.insert_one" in content, "PayPal should insert notifications"
        assert "payment_failed" in content, "PayPal should use payment_failed notification type"
        assert "subscription_cancelled" in content, "PayPal should use subscription_cancelled notification type"
        print("✓ PayPal failure events create user notifications")

    def test_paypal_capture_denied_refunded_handling(self):
        """PayPal should handle PAYMENT.CAPTURE.DENIED and PAYMENT.CAPTURE.REFUNDED."""
        paypal_routes_path = "/app/backend/routes/payments_paypal_routes.py"
        with open(paypal_routes_path, "r") as f:
            content = f.read()

        assert "PAYMENT.CAPTURE.DENIED" in content, "PayPal should handle capture denied"
        assert "PAYMENT.CAPTURE.REFUNDED" in content, "PayPal should handle capture refunded"
        print("✓ PayPal handles capture denied/refunded events")


class TestFedaPayNonSuccessNotifications:
    """Verify FedaPay non-success path has notification behavior."""

    def test_fedapay_routes_has_failure_handling(self):
        """FedaPay webhook should handle failed/cancelled/unknown outcomes."""
        fedapay_routes_path = "/app/backend/routes/payments_fedapay_routes.py"
        with open(fedapay_routes_path, "r") as f:
            content = f.read()

        # Check for failure handling
        assert "failed" in content.lower(), "FedaPay should handle failed payments"
        assert "cancelled" in content.lower() or "canceled" in content.lower(), "FedaPay should handle cancelled payments"
        assert "declined" in content.lower(), "FedaPay should handle declined payments"
        print("✓ FedaPay routes handle failed/cancelled/declined states")

    def test_fedapay_failure_creates_notification(self):
        """FedaPay failure should create in-app notification for users."""
        fedapay_routes_path = "/app/backend/routes/payments_fedapay_routes.py"
        with open(fedapay_routes_path, "r") as f:
            content = f.read()

        # Check for notification on failure
        assert "create_notification" in content, "FedaPay should create notifications"
        assert "payment_failed" in content, "FedaPay should use payment_failed notification type"
        print("✓ FedaPay failure creates user notifications")


class TestAppleIAPNonSuccessNotifications:
    """Verify Apple IAP non-success path has notification behavior."""

    def test_apple_iap_has_failure_notification_function(self):
        """Apple IAP should have a failure notification function."""
        iap_routes_path = "/app/backend/routes/iap.py"
        with open(iap_routes_path, "r") as f:
            content = f.read()

        # Check for failure notification function
        assert "_send_iap_failure_notification" in content, "Apple IAP should have failure notification function"
        assert "payment_failed" in content, "Apple IAP should use payment_failed notification type"
        print("✓ Apple IAP has failure notification function")

    def test_apple_iap_handles_expired_revoked_states(self):
        """Apple IAP should handle expired and revoked subscription states."""
        iap_routes_path = "/app/backend/routes/iap.py"
        with open(iap_routes_path, "r") as f:
            content = f.read()

        assert "expired" in content.lower(), "Apple IAP should handle expired subscriptions"
        assert "revoked" in content.lower(), "Apple IAP should handle revoked subscriptions"
        print("✓ Apple IAP handles expired/revoked states")


class TestGoogleIAPNonSuccessNotifications:
    """Verify Google IAP non-success path has notification behavior (shared with Apple IAP)."""

    def test_google_iap_uses_shared_failure_notification(self):
        """Google IAP should use the shared IAP failure notification function."""
        iap_routes_path = "/app/backend/routes/iap.py"
        with open(iap_routes_path, "r") as f:
            content = f.read()

        # Google IAP uses the same iap.py routes
        assert "_send_iap_failure_notification" in content, "Google IAP should use shared failure notification"
        assert "platform" in content, "IAP routes should track platform (apple/google)"
        print("✓ Google IAP uses shared failure notification function")


class TestFrontendNonSuccessToastSystem:
    """Verify frontend toast system supports non-success payment notifications."""

    def test_realtime_toast_has_payment_failed_type(self):
        """RealtimeToast should have payment_failed type configuration."""
        toast_path = "/app/frontend/src/components/RealtimeToast.tsx"
        with open(toast_path, "r") as f:
            content = f.read()

        assert "payment_failed" in content, "Toast should have payment_failed type"
        assert "subscription_cancelled" in content, "Toast should have subscription_cancelled type"
        assert "warning" in content, "Toast should have warning type"
        assert "error" in content, "Toast should have error type"
        print("✓ RealtimeToast has payment_failed/subscription_cancelled/warning/error types")

    def test_plans_page_emits_nonsuccess_toast(self):
        """Plans page should emit toast for non-success return status."""
        plans_path = "/app/frontend/app/subscription/plans.tsx"
        with open(plans_path, "r") as f:
            content = f.read()

        assert "notificationEvents.emit('toast'" in content, "Plans should emit toast events"
        assert "payment_failed" in content, "Plans should use payment_failed toast type"
        assert "warning" in content, "Plans should use warning toast type"
        assert "returnStatusBanner" in content, "Plans should have return status banner"
        print("✓ Plans page emits non-success toast notifications")

    def test_mobile_subscriptions_emits_inactive_store_toast(self):
        """MobileSubscriptionsViewV2 should emit toast for inactive store status."""
        mobile_subs_path = "/app/frontend/src/components/MobileSubscriptionsViewV2.tsx"
        with open(mobile_subs_path, "r") as f:
            content = f.read()

        assert "hasObservedInactiveStoreStatus" in content, "Mobile subs should track inactive store status"
        assert "notificationEvents.emit('toast'" in content, "Mobile subs should emit toast events"
        assert "payment_failed" in content, "Mobile subs should use payment_failed toast type"
        assert "expired" in content.lower(), "Mobile subs should handle expired status"
        assert "cancelled" in content.lower() or "canceled" in content.lower(), "Mobile subs should handle cancelled status"
        print("✓ MobileSubscriptionsViewV2 emits inactive store toast notifications")


class TestContractTestCoverage:
    """Verify contract test has non-success notification coverage."""

    def test_contract_test_has_nonsuccess_assertions(self):
        """Contract test should have assertions for non-success notification behavior."""
        contract_test_path = "/app/frontend/src/__tests__/homeDashboardAuthLock.contract.test.ts"
        with open(contract_test_path, "r") as f:
            content = f.read()

        assert "keeps non-success payment notifications visible across providers" in content, "Contract test should have non-success test"
        assert "notificationEvents.emit('toast'" in content, "Contract test should verify toast emission"
        assert "payment_failed" in content, "Contract test should verify payment_failed type"
        assert "hasObservedInactiveStoreStatus" in content, "Contract test should verify IAP inactive status"
        assert "BILLING.SUBSCRIPTION.PAYMENT.FAILED" in content, "Contract test should verify PayPal webhook events"
        print("✓ Contract test has non-success notification coverage assertions")


class TestProviderByProviderSummary:
    """Generate provider-by-provider summary of non-success notification behavior."""

    def test_generate_provider_summary(self):
        """Generate summary of what users see after unsuccessful payment for each provider."""
        summary = {
            "stripe": {
                "backend_handling": False,
                "frontend_handling": False,
                "notification_types": [],
                "user_sees": []
            },
            "paypal": {
                "backend_handling": False,
                "frontend_handling": False,
                "notification_types": [],
                "user_sees": []
            },
            "fedapay": {
                "backend_handling": False,
                "frontend_handling": False,
                "notification_types": [],
                "user_sees": []
            },
            "apple_iap": {
                "backend_handling": False,
                "frontend_handling": False,
                "notification_types": [],
                "user_sees": []
            },
            "google_iap": {
                "backend_handling": False,
                "frontend_handling": False,
                "notification_types": [],
                "user_sees": []
            }
        }

        # Check Stripe
        with open("/app/backend/routes/payments_stripe_routes.py", "r") as f:
            stripe_content = f.read()
        if "create_notification" in stripe_content and "payment_failed" in stripe_content.lower():
            summary["stripe"]["backend_handling"] = True
            summary["stripe"]["notification_types"].append("in-app notification")
            summary["stripe"]["user_sees"].append("In-app notification for failed/expired checkout")

        # Check PayPal
        with open("/app/backend/routes/payments_paypal_routes.py", "r") as f:
            paypal_content = f.read()
        if "db.notifications.insert_one" in paypal_content:
            summary["paypal"]["backend_handling"] = True
            summary["paypal"]["notification_types"].extend(["payment_failed", "subscription_cancelled"])
            summary["paypal"]["user_sees"].extend([
                "In-app notification for payment failed",
                "In-app notification for subscription cancelled",
                "In-app notification for payment reversed/refunded"
            ])

        # Check FedaPay
        with open("/app/backend/routes/payments_fedapay_routes.py", "r") as f:
            fedapay_content = f.read()
        if "create_notification" in fedapay_content and "payment_failed" in fedapay_content:
            summary["fedapay"]["backend_handling"] = True
            summary["fedapay"]["notification_types"].append("payment_failed")
            summary["fedapay"]["user_sees"].append("In-app notification for failed/cancelled/declined payment")

        # Check Apple/Google IAP
        with open("/app/backend/routes/iap.py", "r") as f:
            iap_content = f.read()
        if "_send_iap_failure_notification" in iap_content:
            summary["apple_iap"]["backend_handling"] = True
            summary["apple_iap"]["notification_types"].append("payment_failed")
            summary["apple_iap"]["user_sees"].append("In-app notification for failed/expired/refunded IAP")
            summary["google_iap"]["backend_handling"] = True
            summary["google_iap"]["notification_types"].append("payment_failed")
            summary["google_iap"]["user_sees"].append("In-app notification for failed/expired/refunded IAP")

        # Check frontend handling
        with open("/app/frontend/app/subscription/plans.tsx", "r") as f:
            plans_content = f.read()
        if "notificationEvents.emit('toast'" in plans_content and "returnStatusBanner" in plans_content:
            for provider in ["stripe", "paypal", "fedapay"]:
                summary[provider]["frontend_handling"] = True
                summary[provider]["user_sees"].append("Toast notification on plans page for non-success return")

        with open("/app/frontend/src/components/MobileSubscriptionsViewV2.tsx", "r") as f:
            mobile_content = f.read()
        if "hasObservedInactiveStoreStatus" in mobile_content and "notificationEvents.emit('toast'" in mobile_content:
            summary["apple_iap"]["frontend_handling"] = True
            summary["apple_iap"]["user_sees"].append("Toast notification for inactive store status")
            summary["google_iap"]["frontend_handling"] = True
            summary["google_iap"]["user_sees"].append("Toast notification for inactive store status")

        # Print summary
        print("\n" + "=" * 80)
        print("PROVIDER-BY-PROVIDER NON-SUCCESS NOTIFICATION SUMMARY")
        print("=" * 80)

        all_providers_have_notifications = True
        for provider, data in summary.items():
            print(f"\n{provider.upper()}:")
            print(f"  Backend handling: {'✓' if data['backend_handling'] else '✗'}")
            print(f"  Frontend handling: {'✓' if data['frontend_handling'] else '✗'}")
            print(f"  Notification types: {', '.join(data['notification_types']) if data['notification_types'] else 'None'}")
            print("  What users see:")
            for item in data['user_sees']:
                print(f"    - {item}")
            if not data['backend_handling'] and not data['frontend_handling']:
                all_providers_have_notifications = False
                print("  ⚠️  WARNING: No notification behavior found!")

        print("\n" + "=" * 80)
        if all_providers_have_notifications:
            print("✓ ALL 5 PROVIDERS HAVE NON-SUCCESS NOTIFICATION BEHAVIOR")
        else:
            print("✗ SOME PROVIDERS MISSING NON-SUCCESS NOTIFICATION BEHAVIOR")
        print("=" * 80)

        assert all_providers_have_notifications, "All providers should have non-success notification behavior"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
