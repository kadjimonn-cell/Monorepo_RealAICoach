import React from 'react';
import { Text, TextInput, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { withAlpha } from '../../utils/colorAlpha';
import { DisplayTier, getDecisionPrinciples } from './pricingModels';

interface PricingRoiSectionProps {
  activeTierConfig: DisplayTier;
  colors: any;
  isDesktop: boolean;
  isMobile: boolean;
  roi: {
    currentAnnual: number;
    projectedAnnual: number;
    savings: number;
    savingsPct: number;
  };
  roiLabel: string;
  setTeamSize: (value: string) => void;
  setToolSpend: (value: string) => void;
  teamSize: string;
  toolSpend: string;
}

export const PricingRoiSection = ({
  activeTierConfig,
  colors,
  isDesktop,
  isMobile,
  roi,
  roiLabel,
  setTeamSize,
  setToolSpend,
  teamSize,
  toolSpend,
}: PricingRoiSectionProps) => {
  const { tx } = useTranslation();
  const decisionPrinciples = getDecisionPrinciples(tx);
  const savingsValue = Math.abs(Math.round(roi.savings)).toLocaleString();

  return (
    <View
      style={{
        borderRadius: 28,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: withAlpha(colors.text, '03'),
        padding: isMobile ? 18 : 24,
        gap: 18,
      }}
      data-testid="pricing-roi-section"
      testID="pricing-roi-section"
    >
      <View style={{ gap: 8 }}>
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }} data-testid="pricing-roi-label" testID="pricing-roi-label">
          {tx('pricing.roi.label', 'Commercial confidence')}
        </Text>
        <Text style={{ color: colors.text, fontSize: isMobile ? 26 : 32, fontWeight: '900', letterSpacing: -0.8 }} data-testid="pricing-roi-title" testID="pricing-roi-title">
          {tx('pricing.roi.title', 'Estimate the budget story before you ask teams to change plans.')}
        </Text>
      </View>

      <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 18 }}>
        <View style={{ flex: 1, gap: 12 }} data-testid="pricing-roi-principles" testID="pricing-roi-principles">
          {decisionPrinciples.map((card, index) => (
            <View
              key={card.title}
              style={{
                borderRadius: 20,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.card,
                padding: 16,
                gap: 6,
              }}
              data-testid={`pricing-roi-principle-${index}`}
              testID={`pricing-roi-principle-${index}`}
            >
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{card.title}</Text>
              <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 20 }}>{card.body}</Text>
            </View>
          ))}
        </View>

        <View
          style={{
            flex: 1,
            borderRadius: 24,
            borderWidth: 1,
            borderColor: withAlpha(colors.primary, '28'),
            backgroundColor: colors.card,
            padding: isMobile ? 16 : 22,
            gap: 14,
          }}
          data-testid="pricing-roi-estimator"
          testID="pricing-roi-estimator"
        >
          <View style={{ gap: 4 }}>
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '900' }} data-testid="pricing-roi-estimator-title" testID="pricing-roi-estimator-title">
              {tx('pricing.roi.estimatorTitle', 'ROI estimator for')} {activeTierConfig.name}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 20 }} data-testid="pricing-roi-estimator-copy" testID="pricing-roi-estimator-copy">
              {tx('pricing.roi.estimatorCopy', 'Compare today’s annual tool spend with the projected cost of standardizing this tier for your team.')}
            </Text>
          </View>

          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
            <TextInput
              value={teamSize}
              onChangeText={setTeamSize}
              keyboardType="numeric"
              placeholder={tx('pricing.roi.teamSizePlaceholder', 'Team size')}
              placeholderTextColor={colors.textMuted}
              style={{
                flex: 1,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.bg,
                paddingHorizontal: 12,
                paddingVertical: 11,
                color: colors.text,
              }}
              data-testid="pricing-roi-team-size"
              testID="pricing-roi-team-size"
            />
            <TextInput
              value={toolSpend}
              onChangeText={setToolSpend}
              keyboardType="numeric"
              placeholder={tx('pricing.roi.toolSpendPlaceholder', 'Current monthly spend')}
              placeholderTextColor={colors.textMuted}
              style={{
                flex: 1,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.bg,
                paddingHorizontal: 12,
                paddingVertical: 11,
                color: colors.text,
              }}
              data-testid="pricing-roi-tool-spend"
              testID="pricing-roi-tool-spend"
            />
          </View>

          <View style={{ borderRadius: 22, backgroundColor: withAlpha(colors.primary, '0D'), padding: 18, gap: 8 }} data-testid="pricing-roi-output" testID="pricing-roi-output">
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('pricing.roi.outputLabel', 'Estimated savings signal')}</Text>
            <Text style={{ color: roi.savings >= 0 ? colors.text : colors.warning, fontSize: isMobile ? 32 : 40, fontWeight: '900', letterSpacing: -1 }} data-testid="pricing-roi-savings-value" testID="pricing-roi-savings-value">
              {roi.savings >= 0 ? `$${savingsValue}` : `+${Math.abs(roi.savingsPct)}%`}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 21 }} data-testid="pricing-roi-label-copy" testID="pricing-roi-label-copy">
              {roiLabel}
            </Text>
          </View>

          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
            <View style={{ flex: 1, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 4 }} data-testid="pricing-roi-current-card" testID="pricing-roi-current-card">
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('pricing.roi.currentAnnual', 'Current annual spend')}</Text>
              <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>${Math.round(roi.currentAnnual).toLocaleString()}</Text>
            </View>
            <View style={{ flex: 1, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 4 }} data-testid="pricing-roi-projected-card" testID="pricing-roi-projected-card">
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('pricing.roi.projectedWith', 'Projected with')} {activeTierConfig.name}</Text>
              <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>${Math.round(roi.projectedAnnual).toLocaleString()}</Text>
            </View>
          </View>
        </View>
      </View>
    </View>
  );
};