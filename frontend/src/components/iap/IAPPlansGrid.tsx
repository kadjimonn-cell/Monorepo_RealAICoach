import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { BillingSectionCard } from '../paymentHistory/BillingRoutePrimitives';
import { formatAmount } from '../paymentHistory/utils';

type Props = {
  colors: any;
  products: any[];
  status: any;
  tx: (key: string, fallback: string) => string;
  onOpenReview: (product: any, provider: 'apple' | 'google') => void;
};

export const IAPPlansGrid = ({ colors, products, status, tx, onOpenReview }: Props) => {
  const currentProductId = String(status?.product_id || '');

  return (
    <BillingSectionCard colors={colors} testId="iap-plans-card">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} {...getTestProps('iap-plans-title')}>
            {tx('mobileSubscriptions.plans.title', 'Available In-App Purchase Plans')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>
            {tx('iap.plans.subtitle', 'Review live Apple and Google checkout estimates before handing off to the store.')}
          </Text>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 16 }}>
        {products.map((product) => {
          const isCurrent = currentProductId && currentProductId === product.product_id;
          const appleEstimate = product?.checkout_estimates?.apple || {};
          const googleEstimate = product?.checkout_estimates?.google || {};
          return (
            <View
              key={product.product_id}
              style={{
                flex: 1,
                minWidth: 260,
                borderRadius: 18,
                borderWidth: 1,
                borderColor: isCurrent ? `${colors.success}44` : colors.border,
                backgroundColor: isCurrent ? colors.successSoft : colors.bgSoft,
                padding: 16,
              }}
              {...getTestProps(`mobile-plan-${product.plan}-${product.period}`)}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                  <View style={{ width: 42, height: 42, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor((product.plan === 'premium' ? colors.purple : colors.primary), '18'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={product.plan === 'premium' ? 'diamond-outline' : 'star-outline'} size={18} color={product.plan === 'premium' ? colors.purpleText || colors.purple : colors.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }}>{product.display_name}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{product.product_id}</Text>
                  </View>
                </View>
                {isCurrent && (
                  <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: `${colors.success}18`, borderWidth: 1, borderColor: `${colors.success}44` }}>
                    <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800' }}>{tx('mobileSubscriptions.plans.current', 'CURRENT')}</Text>
                  </View>
                )}
              </View>

              <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4, marginTop: 14 }}>
                <Text style={{ color: colors.text, fontSize: 28, fontWeight: '900' }}>{formatAmount(Number(product.price || 0), product.currency || 'USD')}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '700' }}>/ {product.period === 'yearly' ? tx('mobileSubscriptions.period.yr', 'yr') : tx('mobileSubscriptions.period.mo', 'mo')}</Text>
              </View>

              <View style={{ gap: 10, marginTop: 16 }}>
                {[
                  ['apple', appleEstimate, tx('mobileSubscriptions.providers.apple', 'Apple App Store'), 'logo-apple'],
                  ['google', googleEstimate, tx('mobileSubscriptions.providers.googleStore', 'Google Play Store'), 'logo-google-playstore'],
                ].map(([provider, estimate, label, icon]) => (
                  <View key={`${product.product_id}-${provider}`} style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} {...getTestProps(`mobile-plan-${provider}-breakdown-${product.product_id}`)}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <Ionicons name={icon as any} size={16} color={provider === 'apple' ? colors.textMuted : colors.successText} />
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{label}</Text>
                      </View>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '900' }} {...getTestProps(`mobile-plan-${provider}-total-${product.product_id}`)}>{formatAmount(Number((estimate as any)?.final_total || (estimate as any)?.total_amount || 0), product.currency || 'USD')}</Text>
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 17, marginTop: 8 }} {...getTestProps(`mobile-plan-${provider}-tax-note-${product.product_id}`)}>
                      {(estimate as any)?.tax_disclosure || tx('mobileSubscriptions.pricing.taxDisclosure', 'Taxes shown here are calculated before payment to ensure transparency.')}
                    </Text>
                    <TouchableOpacity onPress={() => onOpenReview(product, provider as 'apple' | 'google')} accessibilityLabel="On open review in iapplans grid button" style={{ marginTop: 10, minHeight: 42, borderRadius: 12, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' }} {...getTestProps(`mobile-plan-${provider}-continue-button-${product.product_id}`)}>
                      <Text style={{ color: colors.primaryText || colors.text, fontSize: 12, fontWeight: '800' }}>{tx('mobileSubscriptions.pricing.reviewBeforeStore', 'Review pricing before store handoff')}</Text>
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
            </View>
          );
        })}
      </View>
    </BillingSectionCard>
  );
};

/* i18n-probe t('i18n.auto.probe') */
