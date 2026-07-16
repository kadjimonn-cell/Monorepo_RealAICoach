import React from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Text, TouchableOpacity, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { withAlpha } from '../../utils/colorAlpha';
import { LANGUAGE_OPTIONS } from '../../i18n/languageOptions';
import { DisplayTier, getCommercialLanes, getHeroProofPoints } from './pricingModels';

interface PricingHeroSectionProps {
  activeTierConfig: DisplayTier;
  annualSavingsPct: number;
  colors: any;
  darkMode: boolean;
  isDesktop: boolean;
  isMobile: boolean;
  maxAnnualSavingsPct: number;
  onStartFree: () => void;
  onTalkSales: () => void;
}

export const PricingHeroSection = ({
  activeTierConfig,
  annualSavingsPct,
  colors,
  darkMode,
  isDesktop,
  isMobile,
  maxAnnualSavingsPct,
  onStartFree,
  onTalkSales,
}: PricingHeroSectionProps) => {
  const { tx } = useTranslation();
  const activeMonthlyEquivalent = activeTierConfig.yearly > 0 ? Math.round(activeTierConfig.yearly / 12) : activeTierConfig.monthly;
  const heroProofPoints = getHeroProofPoints(tx);
  const commercialLanes = getCommercialLanes(tx);
  const savingsLabel = annualSavingsPct > 0 ? `${annualSavingsPct}% ${tx('pricing.hero.summary.on', 'on')} ${activeTierConfig.name}` : maxAnnualSavingsPct > 0 ? `${tx('pricing.hero.summary.upTo', 'Up to')} ${maxAnnualSavingsPct}% ${tx('pricing.hero.summary.annually', 'annually')}` : tx('pricing.hero.summary.flexibleBilling', 'Flexible billing');

  return (
    <View
      style={{
        borderRadius: 28,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        padding: isMobile ? 18 : 28,
        gap: 20,
      }}
      data-testid="pricing-hero"
      testID="pricing-hero"
    >
      <View
        style={{
          flexDirection: isDesktop ? 'row' : 'column',
          gap: 18,
        }}
      >
        <View style={{ flex: isDesktop ? 1.2 : undefined, gap: 14 }}>
          <Text
            style={{ color: colors.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase' }}
            data-testid="pricing-hero-badge"
            testID="pricing-hero-badge"
          >
            {tx('pricing.hero.badge', 'Enterprise pricing • structured for clear approvals')}
          </Text>
          <Text
            style={{
              color: colors.text,
              fontSize: isMobile ? 34 : isDesktop ? 54 : 46,
              lineHeight: isMobile ? 40 : isDesktop ? 60 : 52,
              fontWeight: '900',
              letterSpacing: -1.2,
              maxWidth: 760,
            }}
            data-testid="pricing-hero-title"
            testID="pricing-hero-title"
          >
            {tx('pricing.hero.title', 'Pricing that makes the value story obvious before the buying conversation starts.')}
          </Text>
          <Text
            style={{ color: colors.textSec, fontSize: 15, lineHeight: 24, maxWidth: 760 }}
            data-testid="pricing-hero-subtitle"
            testID="pricing-hero-subtitle"
          >
            {tx('pricing.hero.subtitle', 'Free launches quickly, Basic creates operating rhythm, and Premium supports the deepest usage with stronger coverage. The structure stays aligned to the platform’s current entitlement model.')}
          </Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="pricing-hero-proof-row" testID="pricing-hero-proof-row">
            {heroProofPoints.map((item, index) => (
              <View
                key={item}
                style={{
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: colors.border,
                  backgroundColor: colors.bg,
                  paddingHorizontal: 12,
                  paddingVertical: 7,
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                }}
                data-testid={`pricing-hero-proof-pill-${index}`}
                testID={`pricing-hero-proof-pill-${index}`}
              >
                <Ionicons name="checkmark-circle" size={14} color={colors.primary} />
                <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
              </View>
            ))}
            <View
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: withAlpha(colors.primary, 0.35),
                backgroundColor: withAlpha(colors.primary, darkMode ? 0.14 : 0.08),
                paddingHorizontal: 12,
                paddingVertical: 7,
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
              }}
              data-testid="pricing-hero-languages-badge"
              testID="pricing-hero-languages-badge"
            >
              <Ionicons name="globe-outline" size={14} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>
                {tx('pricing.hero.languagesBadge', 'Available in {count} languages').replace('{count}', String(LANGUAGE_OPTIONS.length))}
              </Text>
            </View>
          </View>

          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
            <TouchableOpacity
              onPress={onStartFree}
              style={{
                borderRadius: 12,
                backgroundColor: colors.primary,
                paddingHorizontal: 18,
                paddingVertical: 12,
                alignItems: 'center',
                justifyContent: 'center',
              }}
              data-testid="pricing-hero-start-trial"
              testID="pricing-hero-start-trial"
            >
              <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('pricing.hero.cta.start', 'Start on Free')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={onTalkSales}
              style={{
                borderRadius: 12,
                borderWidth: 1,
                borderColor: darkMode ? colors.borderStrong : colors.border,
                backgroundColor: darkMode ? colors.surfaceHover : colors.bg,
                paddingHorizontal: 18,
                paddingVertical: 12,
                alignItems: 'center',
                justifyContent: 'center',
              }}
              data-testid="pricing-hero-talk-sales"
              testID="pricing-hero-talk-sales"
            >
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('pricing.hero.cta.sales', 'Talk to sales')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View
          style={{
            flex: 0.9,
            borderRadius: 24,
            borderWidth: 1,
            borderColor: withAlpha(colors.primary, '2A'),
            backgroundColor: withAlpha(colors.primary, '0D'),
            padding: isMobile ? 16 : 20,
            gap: 14,
          }}
          data-testid="pricing-hero-summary-card"
          testID="pricing-hero-summary-card"
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="pricing-hero-summary-title" testID="pricing-hero-summary-title">
              {tx('pricing.hero.summary.title', 'Current preview:')} {activeTierConfig.name}
            </Text>
            <View
              style={{
                borderRadius: 999,
                backgroundColor: withAlpha(colors.text, '10'),
                paddingHorizontal: 10,
                paddingVertical: 5,
              }}
              data-testid="pricing-hero-summary-badge"
              testID="pricing-hero-summary-badge"
            >
              <Text style={{ color: colors.text, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{activeTierConfig.valueLabel}</Text>
            </View>
          </View>

          <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 21 }} data-testid="pricing-hero-summary-copy" testID="pricing-hero-summary-copy">
            {activeTierConfig.emphasis}
          </Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            {[
              { label: tx('pricing.hero.summary.metric.monthlyEquivalent', 'Monthly equivalent'), value: activeTierConfig.monthly === 0 ? tx('pricing.hero.summary.metric.free', 'Free') : `$${activeMonthlyEquivalent}` },
              { label: tx('pricing.hero.summary.metric.annualSignal', 'Annual savings signal'), value: savingsLabel },
              { label: tx('pricing.hero.summary.metric.supportRoute', 'Support route'), value: activeTierConfig.support },
            ].map((metric, index) => (
              <View
                key={metric.label}
                style={{
                  minWidth: isDesktop ? 140 : 120,
                  flex: 1,
                  borderRadius: 18,
                  borderWidth: 1,
                  borderColor: colors.border,
                  backgroundColor: colors.card,
                  padding: 14,
                  gap: 5,
                }}
                data-testid={`pricing-hero-metric-${index}`}
                testID={`pricing-hero-metric-${index}`}
              >
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }}>{metric.label}</Text>
                <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>{metric.value}</Text>
              </View>
            ))}
          </View>

          <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 6 }} data-testid="pricing-hero-fit-card" testID="pricing-hero-fit-card">
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('pricing.hero.fit.label', 'Commercial fit')}</Text>
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="pricing-hero-fit-title" testID="pricing-hero-fit-title">
              {activeTierConfig.audience}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 20 }} data-testid="pricing-hero-fit-copy" testID="pricing-hero-fit-copy">
              {activeTierConfig.rollout}
            </Text>
          </View>
        </View>
      </View>

      <View style={{ gap: 10 }} data-testid="pricing-commercial-lanes" testID="pricing-commercial-lanes">
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('pricing.hero.lanes.label', 'Built for buyer clarity')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {commercialLanes.map((lane, index) => (
            <View
              key={lane.title}
              style={{
                flexBasis: isDesktop ? '24%' as any : isMobile ? '100%' as any : '48%' as any,
                flexGrow: 1,
                borderRadius: 18,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.bg,
                padding: 14,
                gap: 6,
              }}
              data-testid={`pricing-commercial-lane-${index}`}
              testID={`pricing-commercial-lane-${index}`}
            >
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{lane.title}</Text>
              <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 19 }}>{lane.body}</Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
};