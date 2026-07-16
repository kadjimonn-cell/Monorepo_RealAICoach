import React from 'react';
import { Ionicons } from '@expo/vector-icons';
import { Text, TouchableOpacity, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { withAlpha } from '../../utils/colorAlpha';
import { DisplayTier, TierId } from './pricingModels';

interface PricingPlansSectionProps {
  activeTier: TierId;
  annualSavingsPct: number;
  colors: any;
  darkMode: boolean;
  isDesktop: boolean;
  isMobile: boolean;
  isYearly: boolean;
  onRegister: () => void;
  onSelectTier: (tierId: TierId) => void;
  setIsYearly: (value: boolean) => void;
  tiers: DisplayTier[];
}

export const PricingPlansSection = ({
  activeTier,
  annualSavingsPct,
  colors,
  darkMode,
  isDesktop,
  isMobile,
  isYearly,
  onRegister,
  onSelectTier,
  setIsYearly,
  tiers,
}: PricingPlansSectionProps) => {
  const { tx } = useTranslation();
  return (
    <View style={{ gap: 18 }} data-testid="pricing-plans-section" testID="pricing-plans-section">
      <View style={{ alignItems: 'center', gap: 10 }}>
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.2 }} data-testid="pricing-plans-label" testID="pricing-plans-label">
          {tx('pricing.plans.label', 'Choose your operating cadence')}
        </Text>
        <Text style={{ color: colors.text, fontSize: isMobile ? 27 : 34, fontWeight: '900', letterSpacing: -0.7, textAlign: 'center' }} data-testid="pricing-plans-title" testID="pricing-plans-title">
          {tx('pricing.plans.title', 'Three tiers. One clear upgrade path.')}
        </Text>
        <Text style={{ color: colors.textSec, fontSize: 14, lineHeight: 22, textAlign: 'center', maxWidth: 780 }} data-testid="pricing-plans-subtitle" testID="pricing-plans-subtitle">
          {tx('pricing.plans.subtitle', 'Compare what changes across launch, operating, and accelerated usage — then preview the plan that fits the current stage of work.')}
        </Text>

        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 4,
            borderRadius: 999,
            borderWidth: 1,
            borderColor: colors.border,
            backgroundColor: colors.card,
            padding: 4,
          }}
          data-testid="pricing-billing-toggle"
          testID="pricing-billing-toggle"
        >
          <TouchableOpacity
            onPress={() => setIsYearly(false)}
            style={{
              borderRadius: 999,
              paddingHorizontal: 18,
              paddingVertical: 10,
              backgroundColor: !isYearly ? colors.bg : 'transparent',
            }}
            data-testid="pricing-toggle-monthly"
            testID="pricing-toggle-monthly"
          >
            <Text style={{ color: !isYearly ? colors.text : colors.textMuted, fontSize: 12, fontWeight: '800' }}>{tx('pricing.plans.toggle.monthly', 'Monthly')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setIsYearly(true)}
            style={{
              borderRadius: 999,
              paddingHorizontal: 18,
              paddingVertical: 10,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 8,
              backgroundColor: isYearly ? colors.bg : 'transparent',
            }}
            data-testid="pricing-toggle-yearly"
            testID="pricing-toggle-yearly"
          >
            <Text style={{ color: isYearly ? colors.text : colors.textMuted, fontSize: 12, fontWeight: '800' }}>{tx('pricing.plans.toggle.annual', 'Annual')}</Text>
            <View style={{ borderRadius: 999, backgroundColor: withAlpha(colors.primary, '18'), paddingHorizontal: 8, paddingVertical: 4 }} data-testid="pricing-toggle-savings-badge" testID="pricing-toggle-savings-badge">
              <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{tx('pricing.plans.toggle.save', 'Save')} {Math.max(annualSavingsPct, 19)}%</Text>
            </View>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14, justifyContent: 'center' }} data-testid="pricing-plan-grid" testID="pricing-plan-grid">
        {tiers.map((tier, index) => {
          const selected = tier.id === activeTier;
          const price = isYearly ? tier.yearly : tier.monthly;
          const monthlyEquivalent = tier.yearly > 0 ? Math.round(tier.yearly / 12) : tier.monthly;

          return (
            <TouchableOpacity
              key={tier.id}
              onPress={() => onSelectTier(tier.id)}
              style={{
                width: isMobile ? '100%' as any : isDesktop ? '32.2%' as any : '48.4%' as any,
                borderRadius: 24,
                borderWidth: selected ? 2 : tier.featured ? 1.5 : 1,
                borderColor: selected ? colors.primary : tier.featured ? withAlpha(colors.primary, darkMode ? '54' : '36') : withAlpha(colors.text, '10'),
                backgroundColor: selected ? withAlpha(colors.primary, darkMode ? '18' : '0C') : colors.card,
                padding: isMobile ? 16 : 20,
                gap: 12,
                shadowColor: colors.text,
                shadowOpacity: selected ? 0.12 : 0.05,
                shadowRadius: selected ? 26 : 16,
                shadowOffset: { width: 0, height: selected ? 12 : 8 },
                elevation: selected ? 8 : 3,
              }}
              data-testid={`pricing-tier-${tier.id}`}
              testID={`pricing-tier-${tier.id}`}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                <View style={{ gap: 6 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }} data-testid={`pricing-tier-value-label-${tier.id}`} testID={`pricing-tier-value-label-${tier.id}`}>
                    {tier.valueLabel}
                  </Text>
                  <Text style={{ color: colors.text, fontSize: 26, fontWeight: '900' }} data-testid={`pricing-tier-name-${tier.id}`} testID={`pricing-tier-name-${tier.id}`}>
                    {tier.name}
                  </Text>
                </View>

                <View style={{ alignItems: 'flex-end', gap: 8 }}>
                  {tier.badge ? (
                    <View style={{ borderRadius: 999, backgroundColor: selected ? withAlpha(colors.primary, darkMode ? '22' : '16') : withAlpha(colors.text, '0A'), paddingHorizontal: 10, paddingVertical: 5 }} data-testid={`pricing-tier-badge-${tier.id}`} testID={`pricing-tier-badge-${tier.id}`}>
                      <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{tier.badge}</Text>
                    </View>
                  ) : null}
                  {selected ? (
                    <View style={{ borderRadius: 999, borderWidth: 1, borderColor: withAlpha(colors.primary, '44'), backgroundColor: withAlpha(colors.primary, '10'), paddingHorizontal: 9, paddingVertical: 4 }} data-testid={`pricing-tier-selected-chip-${tier.id}`} testID={`pricing-tier-selected-chip-${tier.id}`}>
                      <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{tx('pricing.plans.previewing', 'Previewing')}</Text>
                    </View>
                  ) : null}
                </View>
              </View>

              <View style={{ gap: 2 }}>
                <Text style={{ color: colors.text, fontSize: 36, fontWeight: '900', letterSpacing: -1 }} data-testid={`pricing-tier-price-${tier.id}`} testID={`pricing-tier-price-${tier.id}`}>
                  ${price}
                  <Text style={{ color: colors.textMuted, fontSize: 13, fontWeight: '700' }}> {isYearly ? '/year' : '/month'}</Text>
                </Text>
                <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid={`pricing-tier-price-note-${tier.id}`} testID={`pricing-tier-price-note-${tier.id}`}>
                  {price === 0 ? tx('pricing.plans.card.freeNote', 'No upfront commitment required.') : isYearly ? `${tx('pricing.plans.card.equivalentTo', 'Equivalent to')} $${monthlyEquivalent}${tx('pricing.plans.card.perMonthBilledAnnually', '/month billed annually.')}` : tx('pricing.plans.card.switchAnnual', 'Switch to annual when budget predictability matters.')}
                </Text>
              </View>

              <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 21 }} data-testid={`pricing-tier-subtitle-${tier.id}`} testID={`pricing-tier-subtitle-${tier.id}`}>
                {tier.subtitle}
              </Text>

              <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 14, gap: 8 }} data-testid={`pricing-tier-fit-card-${tier.id}`} testID={`pricing-tier-fit-card-${tier.id}`}>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid={`pricing-tier-audience-${tier.id}`} testID={`pricing-tier-audience-${tier.id}`}>
                  {tier.audience}
                </Text>
                <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 19 }} data-testid={`pricing-tier-rollout-${tier.id}`} testID={`pricing-tier-rollout-${tier.id}`}>
                  {tier.rollout}
                </Text>
              </View>

              <View style={{ gap: 8 }}>
                {tier.unlocks.map((item, unlockIndex) => (
                  <View key={`${tier.id}-${item}-${unlockIndex}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`pricing-tier-feature-${tier.id}-${unlockIndex}`} testID={`pricing-tier-feature-${tier.id}-${unlockIndex}`}>
                    <Ionicons name="checkmark-circle" size={16} color={selected ? colors.text : colors.primary} />
                    <Text style={{ color: colors.textSec, fontSize: 12, flex: 1 }}>{item}</Text>
                  </View>
                ))}
              </View>

              <View style={{ borderTopWidth: 1, borderTopColor: withAlpha(colors.text, '10'), paddingTop: 12, gap: 8 }}>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('pricing.plans.card.support', 'Support')}</Text>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid={`pricing-tier-support-${tier.id}`} testID={`pricing-tier-support-${tier.id}`}>
                  {tier.support}
                </Text>
              </View>

              <TouchableOpacity
                onPress={onRegister}
                style={{
                  borderRadius: 12,
                  paddingVertical: 12,
                  alignItems: 'center',
                  backgroundColor: selected ? colors.primary : (darkMode ? colors.surfaceHover : colors.bg),
                  borderWidth: 1,
                  borderColor: selected ? colors.primary : colors.borderStrong,
                }}
                data-testid={`pricing-tier-cta-${tier.id}`}
                testID={`pricing-tier-cta-${tier.id}`}
              >
                <Text style={{ color: selected ? colors.primaryText : colors.text, fontSize: 12, fontWeight: '800' }}>{tier.cta}</Text>
              </TouchableOpacity>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
};