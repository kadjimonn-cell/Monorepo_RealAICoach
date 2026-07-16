import React from 'react';
import { Text, View } from 'react-native';

import { buildSubscriptionReturnToastPayload } from '../../utils/subscriptionReturnToast';
import { getTestProps } from '../../utils/testProps';

type SubscriptionUnlockedDestinationSummaryProps = {
  colors: {
    success: string;
    successText: string;
    text: string;
    textMuted: string;
    bgSoft: string;
  };
  planName?: string | null;
  providerKey?: 'stripe' | 'paypal' | 'fedapay' | 'apple_iap' | 'google_iap' | 'apple' | 'google' | 'unknown';
  providerLabel?: string | null;
  returnTarget: string;
  testIdPrefix: string;
  tx: (key: string, fallback: string) => string;
};

function normalizeProviderKey(providerKey?: string | null) {
  if (providerKey === 'apple') return 'apple_iap';
  if (providerKey === 'google') return 'google_iap';
  if (providerKey === 'stripe' || providerKey === 'paypal' || providerKey === 'fedapay' || providerKey === 'apple_iap' || providerKey === 'google_iap') {
    return providerKey;
  }
  return 'unknown';
}

function getProviderNextStepConfig(providerKey?: string | null, providerLabel?: string | null) {
  const normalized = normalizeProviderKey(providerKey);

  switch (normalized) {
    case 'stripe':
      return {
        key: 'payment.success.providerNextStep.stripe',
        fallback: 'Stripe has confirmed your payment — your upgraded tools are ready in {destination}.',
      };
    case 'paypal':
      return {
        key: 'payment.success.providerNextStep.paypal',
        fallback: 'PayPal approval is complete — jump back into {destination} and keep going.',
      };
    case 'fedapay':
      return {
        key: 'payment.success.providerNextStep.fedapay',
        fallback: 'FedaPay has confirmed your payment — your upgraded destination in {destination} is ready.',
      };
    case 'apple_iap':
      return {
        key: 'payment.success.providerNextStep.apple_iap',
        fallback: 'App Store access is synced — open {destination} to start using {plan}.',
      };
    case 'google_iap':
      return {
        key: 'payment.success.providerNextStep.google_iap',
        fallback: 'Google Play access is synced — open {destination} to start using {plan}.',
      };
    default:
      return {
        key: 'payment.success.providerNextStep.default',
        fallback: '{provider} has finished unlocking your access — continue in {destination}.',
      };
  }
}

export function SubscriptionUnlockedDestinationSummary({
  colors,
  planName,
  providerKey,
  providerLabel,
  returnTarget,
  testIdPrefix,
  tx,
}: SubscriptionUnlockedDestinationSummaryProps) {
  const payload = buildSubscriptionReturnToastPayload(returnTarget, planName);
  const localizedDestination = payload.destinationLabelKey
    ? tx(payload.destinationLabelKey, payload.destinationLabelFallback || payload.destinationLabel)
    : payload.destinationLabel;
  const localizedTitle = (payload.toastTitleKey
    ? tx(payload.toastTitleKey, payload.toastTitleFallback || String(planName || '').trim() || 'Upgrade complete')
    : payload.toastTitleFallback || String(planName || '').trim() || 'Upgrade complete')
    .replace('{plan}', String(planName || '').trim() || 'Your plan');
  const localizedAccessNote = (payload.toastMessageKey
    ? tx(payload.toastMessageKey, payload.toastMessageFallback || '')
    : payload.toastMessageFallback || '')
    .replace('{plan}', String(planName || '').trim() || 'your plan')
    .replace('{destination}', localizedDestination);
  const displayPlan = String(planName || '').trim() || tx('payment.success.defaultUnlockedAccess', 'Premium access');
  const resolvedProviderLabel = String(providerLabel || '').trim() || tx('payment.success.defaultProviderLabel', 'Payment provider');
  const providerNextStepConfig = getProviderNextStepConfig(providerKey, resolvedProviderLabel);
  const localizedProviderNextStep = tx(providerNextStepConfig.key, providerNextStepConfig.fallback)
    .replace('{plan}', displayPlan)
    .replace('{destination}', localizedDestination)
    .replace('{provider}', resolvedProviderLabel);

  return (
    <View
      style={{
        borderRadius: 16,
        borderWidth: 1,
        borderColor: `${colors.success}33`,
        backgroundColor: colors.bgSoft,
        padding: 16,
        gap: 12,
      }}
      {...getTestProps(`${testIdPrefix}-summary`)}
    >
      <Text
        style={{ color: colors.successText, fontSize: 11, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase' }}
        {...getTestProps(`${testIdPrefix}-summary-eyebrow`)}
      >
        {tx('iap.success.destinationSummaryEyebrow', 'Plan unlocked')}
      </Text>
      <Text
        style={{ color: colors.text, fontSize: 18, fontWeight: '800', lineHeight: 24 }}
        {...getTestProps(`${testIdPrefix}-summary-title`)}
      >
        {localizedTitle}
      </Text>
      <View style={{ gap: 10 }}>
        <View
          style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}
          {...getTestProps(`${testIdPrefix}-plan-row`)}
        >
          <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '700' }}>
            {tx('iap.success.destinationSummaryPlanLabel', 'Unlocked access')}
          </Text>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
            {displayPlan}
          </Text>
        </View>
        <View
          style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}
          {...getTestProps(`${testIdPrefix}-destination-row`)}
        >
          <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '700' }}>
            {tx('iap.success.destinationSummaryReturnLabel', 'Returning to')}
          </Text>
          <Text
            style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}
            {...getTestProps(`${testIdPrefix}-destination`)}
          >
            {localizedDestination}
          </Text>
        </View>
      </View>
      <Text
        style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18 }}
        {...getTestProps(`${testIdPrefix}-summary-note`)}
      >
        {localizedAccessNote}
      </Text>
      <View style={{ gap: 4 }}>
        <Text
          style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 0.8, textTransform: 'uppercase' }}
          {...getTestProps(`${testIdPrefix}-next-step-label`)}
        >
          {tx('payment.success.providerNextStep.label', 'What unlocks next')}
        </Text>
        <Text
          style={{ color: colors.text, fontSize: 12, lineHeight: 18 }}
          {...getTestProps(`${testIdPrefix}-next-step`)}
        >
          {localizedProviderNextStep}
        </Text>
      </View>
    </View>
  );
}