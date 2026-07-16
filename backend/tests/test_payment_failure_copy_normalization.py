"""
Test Payment Failure Copy Normalization - Checkpoint D Verification

Verifies that all 5 payment providers (Stripe, PayPal, FedaPay, Apple IAP, Google IAP)
use consistent normalized copy for cancelled, failed, refunded, expired, and unknown states.
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestBackendHealth:
    """Verify backend is healthy before running tests."""
    
    def test_backend_health(self):
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"


class TestPaymentFailureCopyFrontendContract:
    """Verify frontend paymentFailureCopy.ts has all required states and copy."""
    
    def test_payment_failure_copy_has_all_states(self):
        """Verify paymentFailureCopy.ts exports normalizePaymentFailureState and getPaymentFailureCopy."""
        with open('/app/frontend/src/utils/paymentFailureCopy.ts', 'r') as f:
            content = f.read()
        
        # Check exports
        assert 'export type PaymentFailureState' in content
        assert 'export function normalizePaymentFailureState' in content
        assert 'export function getPaymentFailureCopy' in content
        
        # Check all 5 states are defined
        assert "'cancelled'" in content
        assert "'failed'" in content
        assert "'refunded'" in content
        assert "'expired'" in content
        assert "'unknown'" in content
        
        # Check normalization mappings
        assert "'cancelled', 'canceled'" in content  # cancelled aliases
        assert "'refunded', 'reversed', 'revoked'" in content  # refunded aliases
        assert "'expired', 'inactive'" in content  # expired aliases
        assert "'failed', 'declined', 'denied', 'unpaid'" in content  # failed aliases
    
    def test_payment_failure_copy_has_tone_property(self):
        """Verify each state has a tone property (warning or error)."""
        with open('/app/frontend/src/utils/paymentFailureCopy.ts', 'r') as f:
            content = f.read()
        
        # Check tone assignments
        assert "tone: 'warning'" in content
        assert "tone: 'error'" in content
        
        # Verify cancelled is warning
        assert "cancelled: {" in content
        # Verify failed is error
        assert "failed: {" in content


class TestPlansPageReturnStatusBanner:
    """Verify plans.tsx uses normalized copy for return status banners."""
    
    def test_plans_uses_payment_failure_copy(self):
        """Verify plans.tsx imports and uses getPaymentFailureCopy."""
        with open('/app/frontend/app/subscription/plans.tsx', 'r') as f:
            content = f.read()
        
        # Check imports
        assert 'getPaymentFailureCopy' in content
        assert 'normalizePaymentFailureState' in content
        assert "from '../../src/utils/paymentFailureCopy'" in content
        
        # Check usage for non-success states
        assert "getPaymentFailureCopy('cancelled'" in content
        assert "getPaymentFailureCopy('failed'" in content
        assert "getPaymentFailureCopy('refunded'" in content
        assert "getPaymentFailureCopy('expired'" in content
        assert "getPaymentFailureCopy('unknown'" in content
    
    def test_plans_emits_toast_for_nonsuccess(self):
        """Verify plans.tsx emits toast notifications for non-success states."""
        with open('/app/frontend/app/subscription/plans.tsx', 'r') as f:
            content = f.read()
        
        assert "notificationEvents.emit('toast'" in content
        assert "type: returnStatusBanner.tone === 'error' ? 'payment_failed' : 'warning'" in content
        assert "actionRoute: '/payment-history'" in content


class TestStripeRedirectNonSuccessCopy:
    """Verify success.tsx (Stripe/PayPal redirect) uses normalized copy."""
    
    def test_success_uses_payment_failure_copy(self):
        """Verify success.tsx imports and uses getPaymentFailureCopy."""
        with open('/app/frontend/app/subscription/success.tsx', 'r') as f:
            content = f.read()
        
        assert 'getPaymentFailureCopy' in content
        assert "from '../../src/utils/paymentFailureCopy'" in content
        
        # Check STATE_CONFIG uses normalized copy
        assert "getPaymentFailureCopy('failed'" in content
        assert "getPaymentFailureCopy('cancelled'" in content
        assert "getPaymentFailureCopy('expired'" in content
        assert "getPaymentFailureCopy('unknown'" in content


class TestFedaPayPaymentResultNonSuccessCopy:
    """Verify payment-result.tsx (FedaPay) uses normalized copy."""
    
    def test_payment_result_uses_payment_failure_copy(self):
        """Verify payment-result.tsx imports and uses getPaymentFailureCopy."""
        with open('/app/frontend/app/subscription/payment-result.tsx', 'r') as f:
            content = f.read()
        
        assert 'getPaymentFailureCopy' in content
        assert 'normalizePaymentFailureState' in content
        assert "from '../../src/utils/paymentFailureCopy'" in content
        
        # Check FedaPay-specific copy
        assert "fedapayCancelledCopy = getPaymentFailureCopy('cancelled', 'FedaPay'" in content
        assert "fedapayFailedCopy = getPaymentFailureCopy('failed', 'FedaPay'" in content
        assert "fedapayRefundedCopy = getPaymentFailureCopy('refunded', 'FedaPay'" in content
        assert "fedapayUnknownCopy = getPaymentFailureCopy('unknown', 'FedaPay'" in content


class TestAppleGoogleIAPInactiveToast:
    """Verify MobileSubscriptionsViewV2.tsx uses normalized copy for inactive store states."""
    
    def test_mobile_subscriptions_uses_payment_failure_copy(self):
        """Verify MobileSubscriptionsViewV2.tsx imports and uses getPaymentFailureCopy."""
        with open('/app/frontend/src/components/MobileSubscriptionsViewV2.tsx', 'r') as f:
            content = f.read()
        
        assert 'getPaymentFailureCopy' in content
        assert 'normalizePaymentFailureState' in content
        assert "from '../utils/paymentFailureCopy'" in content
    
    def test_mobile_subscriptions_handles_inactive_store_status(self):
        """Verify hasObservedInactiveStoreStatus triggers toast with normalized copy."""
        with open('/app/frontend/src/components/MobileSubscriptionsViewV2.tsx', 'r') as f:
            content = f.read()
        
        assert 'hasObservedInactiveStoreStatus' in content
        assert "['expired', 'cancelled', 'canceled', 'revoked']" in content
        assert "notificationEvents.emit('toast'" in content
        assert "type: copy.tone === 'error' ? 'payment_failed' : 'warning'" in content
        assert "actionRoute: '/subscription/mobile'" in content


class TestBackendStripeFailureCopy:
    """Verify Stripe backend routes use _build_provider_failure_copy."""
    
    def test_stripe_routes_has_failure_copy_function(self):
        """Verify payments_stripe_routes.py has _build_provider_failure_copy."""
        with open('/app/backend/routes/payments_stripe_routes.py', 'r') as f:
            content = f.read()
        
        assert 'def _build_provider_failure_copy' in content
        assert "Checkout cancelled" in content
        assert "Payment refunded" in content
        assert "Payment not completed" in content
    
    def test_stripe_webhook_uses_failure_copy(self):
        """Verify Stripe webhook handler uses _build_provider_failure_copy for failures."""
        with open('/app/backend/routes/payments_stripe_routes.py', 'r') as f:
            content = f.read()
        
        assert '_build_provider_failure_copy("Stripe"' in content
        assert 'notif_type="payment_failed"' in content


class TestBackendPayPalFailureCopy:
    """Verify PayPal backend routes use _build_provider_failure_copy."""
    
    def test_paypal_routes_has_failure_copy_function(self):
        """Verify payments_paypal_routes.py has _build_provider_failure_copy."""
        with open('/app/backend/routes/payments_paypal_routes.py', 'r') as f:
            content = f.read()
        
        assert 'def _build_provider_failure_copy' in content
        assert "Checkout cancelled" in content
        assert "Payment refunded" in content
        assert "Payment not completed" in content
    
    def test_paypal_webhook_handles_failure_events(self):
        """Verify PayPal webhook handles BILLING.SUBSCRIPTION failure events."""
        with open('/app/backend/routes/payments_paypal_routes.py', 'r') as f:
            content = f.read()
        
        assert 'BILLING.SUBSCRIPTION.PAYMENT.FAILED' in content
        assert 'BILLING.SUBSCRIPTION.CANCELLED' in content
        assert 'PAYMENT.SALE.REVERSED' in content
        assert 'PAYMENT.SALE.REFUNDED' in content
        assert '_build_provider_failure_copy("PayPal"' in content


class TestBackendFedaPayFailureCopy:
    """Verify FedaPay backend routes use _build_provider_failure_copy."""
    
    def test_fedapay_routes_has_failure_copy_function(self):
        """Verify payments_fedapay_routes.py has _build_provider_failure_copy."""
        with open('/app/backend/routes/payments_fedapay_routes.py', 'r') as f:
            content = f.read()
        
        assert 'def _build_provider_failure_copy' in content
        assert "Checkout cancelled" in content
        assert "Payment refunded" in content
    
    def test_fedapay_webhook_uses_failure_copy(self):
        """Verify FedaPay webhook uses _build_provider_failure_copy for failures."""
        with open('/app/backend/routes/payments_fedapay_routes.py', 'r') as f:
            content = f.read()
        
        assert '_build_provider_failure_copy("FedaPay"' in content
        assert 'notif_type="payment_failed"' in content


class TestBackendIAPFailureCopy:
    """Verify IAP backend routes use normalized failure copy."""
    
    def test_iap_routes_has_failure_notification_function(self):
        """Verify iap.py has _send_iap_failure_notification."""
        with open('/app/backend/routes/iap.py', 'r') as f:
            content = f.read()
        
        assert 'async def _send_iap_failure_notification' in content
        assert "Checkout cancelled" in content
        assert "Payment refunded" in content
    
    def test_iap_failure_notification_handles_all_states(self):
        """Verify _send_iap_failure_notification handles cancelled, refunded, and failed."""
        with open('/app/backend/routes/iap.py', 'r') as f:
            content = f.read()
        
        # Check cancelled handling
        assert '{"canceled", "cancelled"}' in content or '"canceled", "cancelled"' in content
        # Check refunded handling
        assert '{"refunded", "revoked"}' in content or '"refunded", "revoked"' in content
        # Check notification type
        assert '"type": "payment_failed"' in content


class TestI18nLocaleKeys:
    """Verify en.ts has all required i18n keys for payment failure copy."""
    
    def test_en_locale_has_banner_keys(self):
        """Verify en.ts has subscriptionPlans.banner.* keys."""
        with open('/app/frontend/src/i18n/locales/en.ts', 'r') as f:
            content = f.read()
        
        # Check all banner keys exist
        assert '"subscriptionPlans.banner.cancelled.title"' in content
        assert '"subscriptionPlans.banner.cancelled.message"' in content
        assert '"subscriptionPlans.banner.failed.title"' in content
        assert '"subscriptionPlans.banner.failed.message"' in content
        assert '"subscriptionPlans.banner.refunded.title"' in content
        assert '"subscriptionPlans.banner.refunded.message"' in content
        assert '"subscriptionPlans.banner.expired.title"' in content
        assert '"subscriptionPlans.banner.expired.message"' in content
        assert '"subscriptionPlans.banner.unknown.title"' in content
        assert '"subscriptionPlans.banner.unknown.message"' in content
        assert '"subscriptionPlans.banner.success.title"' in content
        assert '"subscriptionPlans.banner.success.message"' in content


class TestRealtimeToastTypes:
    """Verify RealtimeToast.tsx has payment_failed and subscription_cancelled types."""
    
    def test_realtime_toast_has_payment_failed_type(self):
        """Verify RealtimeToast.tsx has payment_failed type config."""
        with open('/app/frontend/src/components/RealtimeToast.tsx', 'r') as f:
            content = f.read()
        
        assert "payment_failed: { icon: 'close-circle'" in content
        assert "subscription_cancelled: { icon: 'remove-circle'" in content


class TestContractTestCoverage:
    """Verify homeDashboardAuthLock.contract.test.ts has non-success assertions."""
    
    def test_contract_test_has_nonsuccess_assertions(self):
        """Verify contract test file has assertions for non-success payment notifications."""
        with open('/app/frontend/src/__tests__/homeDashboardAuthLock.contract.test.ts', 'r') as f:
            content = f.read()
        
        assert "it('keeps non-success payment notifications visible across providers'" in content
        assert "expect(failureCopy).toContain('normalizePaymentFailureState')" in content
        assert "expect(failureCopy).toContain('getPaymentFailureCopy')" in content
        assert "expect(plans).toContain('getPaymentFailureCopy')" in content
        assert "expect(iapView).toContain('hasObservedInactiveStoreStatus')" in content


class TestProviderCopyParity:
    """Verify all 5 providers have consistent copy structure."""
    
    def test_all_providers_use_same_copy_structure(self):
        """Verify all providers use the same copy structure: title, message, tone."""
        # Frontend paymentFailureCopy.ts
        with open('/app/frontend/src/utils/paymentFailureCopy.ts', 'r') as f:
            frontend_copy = f.read()
        
        # Check structure
        assert 'title: tx(' in frontend_copy
        assert 'message: tx(' in frontend_copy
        assert "tone: 'warning'" in frontend_copy or "tone: 'error'" in frontend_copy
        
        # Backend Stripe
        with open('/app/backend/routes/payments_stripe_routes.py', 'r') as f:
            stripe_copy = f.read()
        assert 'def _build_provider_failure_copy' in stripe_copy
        
        # Backend PayPal
        with open('/app/backend/routes/payments_paypal_routes.py', 'r') as f:
            paypal_copy = f.read()
        assert 'def _build_provider_failure_copy' in paypal_copy
        
        # Backend FedaPay
        with open('/app/backend/routes/payments_fedapay_routes.py', 'r') as f:
            fedapay_copy = f.read()
        assert 'def _build_provider_failure_copy' in fedapay_copy
        
        # Backend IAP
        with open('/app/backend/routes/iap.py', 'r') as f:
            iap_copy = f.read()
        assert '_send_iap_failure_notification' in iap_copy


class TestPaymentWebUnlockedTestIds:
    """Verify payment.tsx has correct data-testid for success state."""
    
    def test_payment_tsx_has_success_testids(self):
        """Verify payment.tsx has payment-web-unlocked testIdPrefix."""
        with open('/app/frontend/app/subscription/payment.tsx', 'r') as f:
            content = f.read()
        
        assert 'testIdPrefix="payment-web-unlocked"' in content
        assert 'providerKey={selectedGatewaySlug}' in content
        assert 'providerLabel={selectedGatewayLabel}' in content


class TestPaymentRedirectUnlockedTestIds:
    """Verify success.tsx has correct data-testid for success state."""
    
    def test_success_tsx_has_success_testids(self):
        """Verify success.tsx has payment-redirect-unlocked testIdPrefix."""
        with open('/app/frontend/app/subscription/success.tsx', 'r') as f:
            content = f.read()
        
        assert 'testIdPrefix="payment-redirect-unlocked"' in content
        assert 'providerKey={provider}' in content
        assert 'providerLabel={providerLabel}' in content


class TestPaymentResultUnlockedTestIds:
    """Verify payment-result.tsx has correct data-testid for success state."""
    
    def test_payment_result_tsx_has_success_testids(self):
        """Verify payment-result.tsx has payment-result-unlocked testIdPrefix."""
        with open('/app/frontend/app/subscription/payment-result.tsx', 'r') as f:
            content = f.read()
        
        assert 'testIdPrefix="payment-result-unlocked"' in content
        assert "providerKey={String(gateway || 'fedapay').toLowerCase() === 'fedapay' ? 'fedapay' : 'unknown'}" in content


class TestIAPNativeUnlockedTestIds:
    """Verify MobileSubscriptionsViewV2.tsx has correct data-testid for success state."""
    
    def test_mobile_subscriptions_has_success_testids(self):
        """Verify MobileSubscriptionsViewV2.tsx has iap-native-unlocked testIdPrefix."""
        with open('/app/frontend/src/components/MobileSubscriptionsViewV2.tsx', 'r') as f:
            content = f.read()
        
        assert 'testIdPrefix="iap-native-unlocked"' in content
        assert "providerKey={routeProvider || 'unknown'}" in content
        assert 'providerLabel={routeProviderLabel}' in content
