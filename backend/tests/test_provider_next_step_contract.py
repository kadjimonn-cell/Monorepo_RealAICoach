"""
Provider-specific 'what unlocks next' helper line contract verification.
Tests the P0 refinement: provider-specific next-step line under each unlocked-destination summary.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestBackendHealth:
    """Basic backend health verification"""
    
    def test_backend_health(self):
        """Verify backend is running"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        print("Backend health check passed")


class TestProviderNextStepSourceContract:
    """Verify provider-next-step implementation in source code"""
    
    def test_subscription_unlocked_destination_summary_has_provider_next_step_mapping(self):
        """Verify SubscriptionUnlockedDestinationSummary has provider-specific next-step config"""
        file_path = '/app/frontend/src/components/payment/SubscriptionUnlockedDestinationSummary.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify getProviderNextStepConfig function exists
        assert 'function getProviderNextStepConfig' in content, "Missing getProviderNextStepConfig function"
        
        # Verify all 5 provider cases
        assert "case 'stripe':" in content, "Missing stripe case in provider next-step config"
        assert "case 'paypal':" in content, "Missing paypal case in provider next-step config"
        assert "case 'fedapay':" in content, "Missing fedapay case in provider next-step config"
        assert "case 'apple_iap':" in content, "Missing apple_iap case in provider next-step config"
        assert "case 'google_iap':" in content, "Missing google_iap case in provider next-step config"
        
        # Verify i18n keys for each provider
        assert 'payment.success.providerNextStep.stripe' in content, "Missing stripe i18n key"
        assert 'payment.success.providerNextStep.paypal' in content, "Missing paypal i18n key"
        assert 'payment.success.providerNextStep.fedapay' in content, "Missing fedapay i18n key"
        assert 'payment.success.providerNextStep.apple_iap' in content, "Missing apple_iap i18n key"
        assert 'payment.success.providerNextStep.google_iap' in content, "Missing google_iap i18n key"
        assert 'payment.success.providerNextStep.default' in content, "Missing default i18n key"
        
        print("SubscriptionUnlockedDestinationSummary has all provider-next-step mappings")
    
    def test_subscription_unlocked_destination_summary_has_next_step_testids(self):
        """Verify next-step data-testid attributes are present"""
        file_path = '/app/frontend/src/components/payment/SubscriptionUnlockedDestinationSummary.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify next-step-label and next-step testids
        assert '${testIdPrefix}-next-step-label' in content, "Missing next-step-label testid"
        assert '${testIdPrefix}-next-step' in content, "Missing next-step testid"
        
        # Verify the label text
        assert "tx('payment.success.providerNextStep.label', 'What unlocks next')" in content, "Missing 'What unlocks next' label"
        
        print("SubscriptionUnlockedDestinationSummary has next-step testids")
    
    def test_subscription_unlocked_destination_summary_has_provider_props(self):
        """Verify providerKey and providerLabel props are defined"""
        file_path = '/app/frontend/src/components/payment/SubscriptionUnlockedDestinationSummary.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify props type definition
        assert "providerKey?:" in content, "Missing providerKey prop"
        assert "providerLabel?:" in content, "Missing providerLabel prop"
        
        # Verify normalizeProviderKey function
        assert 'function normalizeProviderKey' in content, "Missing normalizeProviderKey function"
        
        print("SubscriptionUnlockedDestinationSummary has provider props")


class TestPaymentWebUnlockedProviderWiring:
    """Verify payment.tsx passes providerKey/providerLabel to summary"""
    
    def test_payment_tsx_passes_provider_context(self):
        """Verify payment.tsx passes providerKey and providerLabel"""
        file_path = '/app/frontend/app/subscription/payment.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify providerKey is passed
        assert 'providerKey={selectedGatewaySlug}' in content, "Missing providerKey={selectedGatewaySlug}"
        
        # Verify providerLabel is passed
        assert 'providerLabel={selectedGatewayLabel}' in content, "Missing providerLabel={selectedGatewayLabel}"
        
        # Verify testIdPrefix
        assert 'testIdPrefix="payment-web-unlocked"' in content, "Missing payment-web-unlocked testIdPrefix"
        
        print("payment.tsx passes provider context correctly")


class TestPaymentRedirectUnlockedProviderWiring:
    """Verify success.tsx passes providerKey/providerLabel to summary"""
    
    def test_success_tsx_passes_provider_context(self):
        """Verify success.tsx passes providerKey and providerLabel"""
        file_path = '/app/frontend/app/subscription/success.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify providerKey is passed
        assert 'providerKey={provider}' in content, "Missing providerKey={provider}"
        
        # Verify providerLabel is passed
        assert 'providerLabel={providerLabel}' in content, "Missing providerLabel={providerLabel}"
        
        # Verify testIdPrefix
        assert 'testIdPrefix="payment-redirect-unlocked"' in content, "Missing payment-redirect-unlocked testIdPrefix"
        
        print("success.tsx passes provider context correctly")


class TestPaymentResultUnlockedProviderWiring:
    """Verify payment-result.tsx passes providerKey/providerLabel to summary"""
    
    def test_payment_result_tsx_passes_provider_context(self):
        """Verify payment-result.tsx passes providerKey and providerLabel"""
        file_path = '/app/frontend/app/subscription/payment-result.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify providerKey is passed (fedapay context)
        assert "providerKey={String(gateway || 'fedapay').toLowerCase() === 'fedapay' ? 'fedapay' : 'unknown'}" in content, "Missing fedapay providerKey"
        
        # Verify providerLabel is passed
        assert "providerLabel={String(gateway || 'FedaPay')}" in content, "Missing providerLabel"
        
        # Verify testIdPrefix
        assert 'testIdPrefix="payment-result-unlocked"' in content, "Missing payment-result-unlocked testIdPrefix"
        
        print("payment-result.tsx passes provider context correctly")


class TestMobileMoneyUnlockedProviderWiring:
    """Verify mobile-money.tsx passes providerKey/providerLabel to summary"""
    
    def test_mobile_money_tsx_passes_provider_context(self):
        """Verify mobile-money.tsx passes providerKey and providerLabel"""
        file_path = '/app/frontend/app/subscription/mobile-money.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify providerKey is passed
        assert 'providerKey="fedapay"' in content, "Missing providerKey='fedapay'"
        
        # Verify providerLabel is passed
        assert "providerLabel={selectedGateway?.label || 'FedaPay'}" in content, "Missing providerLabel"
        
        # Verify testIdPrefix
        assert 'testIdPrefix="mobile-money-unlocked"' in content, "Missing mobile-money-unlocked testIdPrefix"
        
        print("mobile-money.tsx passes provider context correctly")


class TestIAPNativeUnlockedProviderWiring:
    """Verify MobileSubscriptionsViewV2.tsx passes providerKey/providerLabel to summary"""
    
    def test_mobile_subscriptions_view_passes_provider_context(self):
        """Verify MobileSubscriptionsViewV2.tsx passes providerKey and providerLabel"""
        file_path = '/app/frontend/src/components/MobileSubscriptionsViewV2.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify providerKey is passed
        assert "providerKey={routeProvider || 'unknown'}" in content, "Missing providerKey={routeProvider || 'unknown'}"
        
        # Verify providerLabel is passed
        assert 'providerLabel={routeProviderLabel}' in content, "Missing providerLabel={routeProviderLabel}"
        
        # Verify testIdPrefix
        assert 'testIdPrefix="iap-native-unlocked"' in content, "Missing iap-native-unlocked testIdPrefix"
        
        print("MobileSubscriptionsViewV2.tsx passes provider context correctly")


class TestI18nProviderNextStepKeys:
    """Verify i18n keys for provider-next-step are present"""
    
    def test_en_locale_has_provider_next_step_keys(self):
        """Verify en.ts has all provider-next-step translation keys"""
        file_path = '/app/frontend/src/i18n/locales/en.ts'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify label key
        assert '"payment.success.providerNextStep.label": "What unlocks next"' in content, "Missing label key"
        
        # Verify stripe key
        assert '"payment.success.providerNextStep.stripe":' in content, "Missing stripe key"
        assert 'Stripe has confirmed your payment' in content, "Missing stripe message"
        
        # Verify paypal key
        assert '"payment.success.providerNextStep.paypal":' in content, "Missing paypal key"
        assert 'PayPal approval is complete' in content, "Missing paypal message"
        
        # Verify fedapay key
        assert '"payment.success.providerNextStep.fedapay":' in content, "Missing fedapay key"
        assert 'FedaPay has confirmed your payment' in content, "Missing fedapay message"
        
        # Verify apple_iap key
        assert '"payment.success.providerNextStep.apple_iap":' in content, "Missing apple_iap key"
        assert 'App Store access is synced' in content, "Missing apple_iap message"
        
        # Verify google_iap key
        assert '"payment.success.providerNextStep.google_iap":' in content, "Missing google_iap key"
        assert 'Google Play access is synced' in content, "Missing google_iap message"
        
        # Verify default key
        assert '"payment.success.providerNextStep.default":' in content, "Missing default key"
        
        print("en.ts has all provider-next-step translation keys")


class TestContractTestAssertions:
    """Verify contract test has provider-next-step assertions"""
    
    def test_contract_test_has_provider_next_step_assertions(self):
        """Verify homeDashboardAuthLock.contract.test.ts has provider-next-step assertions"""
        file_path = '/app/frontend/src/__tests__/homeDashboardAuthLock.contract.test.ts'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Verify next-step assertions
        assert "tx('payment.success.providerNextStep.label', 'What unlocks next')" in content, "Missing label assertion"
        assert 'next-step' in content, "Missing next-step testid assertion"
        
        # Verify i18n assertions
        assert '"payment.success.providerNextStep.label": "What unlocks next"' in content, "Missing i18n label assertion"
        assert '"payment.success.providerNextStep.stripe":' in content, "Missing stripe i18n assertion"
        assert '"payment.success.providerNextStep.google_iap":' in content, "Missing google_iap i18n assertion"
        
        print("Contract test has provider-next-step assertions")


class TestUnifiedPaymentSuccessContractIntact:
    """Verify unified payment success contract remains intact"""
    
    def test_subscription_success_panel_has_pre_cta_content(self):
        """Verify SubscriptionSuccessPanel still accepts preCtaContent"""
        file_path = '/app/frontend/src/components/payment/SubscriptionSuccessPanel.tsx'
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert 'preCtaContent?: React.ReactNode' in content, "Missing preCtaContent prop"
        assert 'payment-success-pre-cta-content' in content, "Missing pre-cta-content testid"
        
        print("SubscriptionSuccessPanel preCtaContent contract intact")
    
    def test_all_five_providers_use_subscription_unlocked_destination_summary(self):
        """Verify all 5 providers use SubscriptionUnlockedDestinationSummary"""
        files_to_check = [
            ('/app/frontend/app/subscription/payment.tsx', 'SubscriptionUnlockedDestinationSummary'),
            ('/app/frontend/app/subscription/success.tsx', 'SubscriptionUnlockedDestinationSummary'),
            ('/app/frontend/app/subscription/payment-result.tsx', 'SubscriptionUnlockedDestinationSummary'),
            ('/app/frontend/app/subscription/mobile-money.tsx', 'SubscriptionUnlockedDestinationSummary'),
            ('/app/frontend/src/components/MobileSubscriptionsViewV2.tsx', 'SubscriptionUnlockedDestinationSummary'),
        ]
        
        for file_path, expected_import in files_to_check:
            with open(file_path, 'r') as f:
                content = f.read()
            assert expected_import in content, f"Missing {expected_import} in {file_path}"
        
        print("All 5 providers use SubscriptionUnlockedDestinationSummary")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
