import React, { useEffect, useState } from 'react';
import { Modal, Pressable, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { formatAmount } from '../paymentHistory/utils';

type CheckoutSelection = {
  product: any;
  provider: 'apple' | 'google';
  estimate: any;
  manageUrl: string;
  readiness?: any;
};

type Props = {
  visible: boolean;
  selection: CheckoutSelection | null;
  colors: any;
  tx: (key: string, fallback: string) => string;
  onClose: () => void;
  onContinue: (selection: CheckoutSelection) => void;
};

const MetricRow = ({ label, value, colors, testId }: { label: string; value: string; colors: any; testId: string }) => (
  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 8 }} {...getTestProps(testId)}>
    <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '700', flex: 1 }}>{label}</Text>
    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', flex: 1, textAlign: 'right' }}>{value}</Text>
  </View>
);

export const IAPCheckoutReviewModal = ({ visible, selection, colors, tx, onClose, onContinue }: Props) => {
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (visible) setConfirmed(false);
  }, [visible]);

  if (!selection) return null;

  const readinessState = String(selection.readiness?.status_label || tx('iap.checkout.readinessUnknown', 'Unavailable'));
  const providerLabel = selection.provider === 'apple'
    ? tx('mobileSubscriptions.providers.apple', 'Apple App Store')
    : tx('mobileSubscriptions.providers.googleStore', 'Google Play Store');
  const estimate = selection.estimate || {};
  const jurisdiction = estimate?.jurisdiction || {};
  const jurisdictionLabel = [jurisdiction.country, jurisdiction.state, jurisdiction.postal_code].filter(Boolean).join(' · ') || tx('mobileSubscriptions.defaults.na', 'N/A');

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: 'rgba(15,23,42,0.58)', justifyContent: 'center', alignItems: 'center', padding: 20 }} onPress={onClose} {...getTestProps('iap-checkout-review-overlay')} accessibilityLabel="Close">
        <Pressable accessibilityLabel="Iap checkout review modal button"
          onPress={(event) => event.stopPropagation?.()}
          style={{ width: '100%', maxWidth: 960, borderRadius: 24, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, padding: 20 }}
          {...getTestProps('iap-checkout-review-modal')}
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.9 }}>{tx('iap.checkout.eyebrow', 'Store checkout review')}</Text>
              <Text style={{ color: colors.text, fontSize: 24, fontWeight: '900', marginTop: 10 }} {...getTestProps('iap-checkout-review-title')}>
                {selection.product?.display_name || tx('iap.checkout.planFallback', 'Plan')}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 8 }} {...getTestProps('iap-checkout-review-subtitle')}>
                {tx('iap.checkout.subtitle', 'Review the exact platform data before continuing to the store. No pricing is fabricated on this page.')}
              </Text>
            </View>
            <TouchableOpacity onPress={onClose} style={{ width: 34, height: 34, borderRadius: 999, backgroundColor: colors.bgSoft, alignItems: 'center', justifyContent: 'center' }} {...getTestProps('iap-checkout-review-close-button')} accessibilityLabel="providerLabel">
              <Ionicons name="close" size={18} color={colors.textMuted} />
            </TouchableOpacity>
          </View>

          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: 16 }}>
            <View style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33') }} {...getTestProps('iap-checkout-review-provider-pill')}>
              <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{providerLabel}</Text>
            </View>
            <View style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }} {...getTestProps('iap-checkout-review-readiness-pill')}>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>{readinessState}</Text>
            </View>
          </View>

          <View style={{ marginTop: 18, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 16 }} {...getTestProps('iap-checkout-review-breakdown-card')}>
            <MetricRow label={tx('mobileSubscriptions.pricing.basePlanPrice', 'Base Plan Price')} value={formatAmount(Number(estimate?.base_plan_price || estimate?.subtotal || 0), selection.product?.currency || 'USD')} colors={colors} testId="iap-checkout-review-base-price" />
            <MetricRow label={tx('mobileSubscriptions.pricing.platformFee', 'Platform Fee (IAP Commission)')} value={`${formatAmount(Number(estimate?.platform_fee || estimate?.processing_fee || 0), selection.product?.currency || 'USD')} · ${Number(estimate?.platform_fee_rate_pct || 0).toFixed(2)}%`} colors={colors} testId="iap-checkout-review-platform-fee" />
            <MetricRow label={tx('mobileSubscriptions.pricing.applicableTaxes', 'Applicable Taxes')} value={`${formatAmount(Number(estimate?.tax_fee || 0), selection.product?.currency || 'USD')} · ${Number(estimate?.tax_rate_pct || 0).toFixed(2)}%`} colors={colors} testId="iap-checkout-review-tax-fee" />
            <MetricRow label={tx('mobileSubscriptions.pricing.jurisdiction', 'Jurisdiction')} value={jurisdictionLabel} colors={colors} testId="iap-checkout-review-jurisdiction" />
            <MetricRow label={tx('mobileSubscriptions.pricing.finalTotal', 'Final Total')} value={formatAmount(Number(estimate?.final_total || estimate?.total_amount || 0), selection.product?.currency || 'USD')} colors={colors} testId="iap-checkout-review-final-total" />
          </View>

          {!!estimate?.tax_disclosure && (
            <View style={{ marginTop: 14, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} {...getTestProps('iap-checkout-review-disclosure')}>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('iap.checkout.disclosureTitle', 'Tax disclosure')}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>{estimate.tax_disclosure}</Text>
            </View>
          )}

          {Array.isArray(estimate?.tax_breakdown) && estimate.tax_breakdown.length > 0 && (
            <View style={{ marginTop: 14, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} {...getTestProps('iap-checkout-review-tax-breakdown')}>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('iap.checkout.taxBreakdownTitle', 'Tax breakdown')}</Text>
              <View style={{ gap: 6, marginTop: 10 }}>
                {estimate.tax_breakdown.map((row: any, index: number) => (
                  <Text key={`${selection.product?.product_id}-${selection.provider}-${index}`} style={{ color: colors.textMuted, fontSize: 11, lineHeight: 16 }} {...getTestProps(`iap-checkout-review-tax-line-${index}`)}>
                    • {row?.tax_name || row?.tax_type || tx('mobileSubscriptions.pricing.tax', 'Tax')}: {formatAmount(Number(row?.tax_amount || 0), selection.product?.currency || 'USD')} ({Number((row?.tax_rate || 0) * 100).toFixed(2)}%)
                  </Text>
                ))}
              </View>
            </View>
          )}

          <TouchableOpacity onPress={() => setConfirmed((current) => !current)} accessibilityLabel="Iap checkout review confirm toggle button" style={{ marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 8 }} {...getTestProps('iap-checkout-review-confirm-toggle')}>
            <Ionicons name={confirmed ? 'checkbox' : 'square-outline'} size={18} color={confirmed ? colors.success : colors.textMuted} />
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', flex: 1 }}>
              {estimate?.confirmation_copy || tx('iap.checkout.confirmationCopy', 'I confirm the Base Plan Price, Platform Fee (IAP Commission), Taxes, and Final Total before purchase.')}
            </Text>
          </TouchableOpacity>

          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
            <TouchableOpacity onPress={onClose} style={{ flex: 1, minHeight: 44, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14 }} {...getTestProps('iap-checkout-review-cancel-button')} accessibilityLabel="Close">
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('iap.checkout.cancel', 'Cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="Iap checkout review continue button"
              onPress={() => onContinue(selection)}
              disabled={!confirmed}
              style={{ flex: 1.3, minHeight: 44, borderRadius: 12, backgroundColor: confirmed ? colors.primary : colors.bgSoft, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14, opacity: confirmed ? 1 : 0.6 }}
              {...getTestProps('iap-checkout-review-continue-button')}
            >
              <Text style={{ color: confirmed ? (colors.primaryText || colors.text) : colors.textMuted, fontSize: 12, fontWeight: '800' }}>{tx('mobileSubscriptions.pricing.continueToStore', 'Continue to store')}</Text>
            </TouchableOpacity>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
};

/* i18n-probe t('i18n.auto.probe') */
