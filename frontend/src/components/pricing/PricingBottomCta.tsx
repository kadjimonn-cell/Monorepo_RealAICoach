import React from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Text, TouchableOpacity, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { withAlpha } from '../../utils/colorAlpha';

interface PricingBottomCtaProps {
  colors: any;
  darkMode: boolean;
  isDesktop: boolean;
  isMobile: boolean;
  onCompare: () => void;
  onStart: () => void;
  onTalkSales: () => void;
}

export const PricingBottomCta = ({ colors, darkMode, isDesktop, isMobile, onCompare, onStart, onTalkSales }: PricingBottomCtaProps) => {
  const { tx } = useTranslation();
  return (
    <View
      style={{
        borderRadius: isMobile ? 24 : 28,
        borderWidth: 1,
        borderColor: darkMode ? withAlpha(colors.primary, '38') : withAlpha(colors.primary, '20'),
        backgroundColor: darkMode ? colors.surfaceElevated : colors.cardMuted,
        padding: isMobile ? 16 : 26,
        gap: isMobile ? 16 : 18,
      }}
      data-testid="pricing-bottom-cta-card"
      testID="pricing-bottom-cta-card"
    >
      <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 16, justifyContent: 'space-between' }}>
        <View style={{ flex: 1, gap: 8 }}>
          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.2 }} data-testid="pricing-bottom-cta-label" testID="pricing-bottom-cta-label">
            {tx('pricing.bottom.label', 'Ready when the plan is clear')}
          </Text>
          <Text style={{ color: colors.text, fontSize: isMobile ? 22 : 34, fontWeight: '900', letterSpacing: -0.9, lineHeight: isMobile ? 28 : 40 }} data-testid="pricing-bottom-cta-title" testID="pricing-bottom-cta-title">
            {tx('pricing.bottom.title', 'Start small, scale cleanly, and keep the pricing conversation simple.')}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: isMobile ? 21 : 22, maxWidth: 720 }} data-testid="pricing-bottom-cta-copy" testID="pricing-bottom-cta-copy">
            {tx('pricing.bottom.copy', 'Use Free to prove momentum, shift into Basic for consistent operating cadence, or move directly to Premium when support depth and usage intensity matter immediately.')}
          </Text>
        </View>

        <View style={{ gap: 10, minWidth: isDesktop ? 280 : undefined }} data-testid="pricing-bottom-cta-proof" testID="pricing-bottom-cta-proof">
          {[
            tx('pricing.bottom.proof.1', 'Aligned to current entitlement routes'),
            tx('pricing.bottom.proof.2', 'Monthly and annual visibility before conversion'),
            tx('pricing.bottom.proof.3', 'Clear support progression from community to priority'),
          ].map((item, index) => (
            <View key={item} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`pricing-bottom-proof-${index}`} testID={`pricing-bottom-proof-${index}`}>
              <Ionicons name="checkmark-circle" size={16} color={colors.primary} />
              <Text style={{ color: colors.textSec, fontSize: 12, flex: 1, lineHeight: 18 }}>{item}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
        <TouchableOpacity
          onPress={onStart}
          style={{ borderRadius: 12, backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, alignItems: 'center' }}
          data-testid="pricing-bottom-start-trial"
          testID="pricing-bottom-start-trial"
        >
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('pricing.bottom.cta.start', 'Start Free')}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={onCompare}
          style={{ borderRadius: 12, borderWidth: 1, borderColor: darkMode ? colors.borderStrong : colors.borderBright, backgroundColor: darkMode ? colors.surfaceHover : colors.card, paddingHorizontal: 18, paddingVertical: 12, alignItems: 'center' }}
          data-testid="pricing-bottom-compare-plans"
          testID="pricing-bottom-compare-plans"
        >
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('pricing.bottom.cta.compare', 'Compare in app')}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={onTalkSales}
          style={{ borderRadius: 12, borderWidth: 1, borderColor: darkMode ? colors.borderStrong : colors.borderBright, backgroundColor: darkMode ? colors.surfaceHover : colors.card, paddingHorizontal: 18, paddingVertical: 12, alignItems: 'center' }}
          data-testid="pricing-bottom-talk-sales"
          testID="pricing-bottom-talk-sales"
        >
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('pricing.bottom.cta.sales', 'Talk to sales')}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};