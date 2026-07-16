import React from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useTranslation } from '../../hooks/useTranslation';
import { withAlpha } from '../../utils/colorAlpha';
import { DisplayTier } from './pricingModels';

interface PricingMatrixSectionProps {
  colors: any;
  matrixRows: {
    label: string;
    values: { free: string; basic: string; premium: string };
  }[];
  tiers: DisplayTier[];
}

export const PricingMatrixSection = ({ colors, matrixRows, tiers }: PricingMatrixSectionProps) => {
  const { tx } = useTranslation();
  return (
    <View
      style={{
        borderRadius: 28,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        padding: 20,
        gap: 16,
      }}
      data-testid="pricing-feature-matrix"
      testID="pricing-feature-matrix"
    >
      <View style={{ gap: 6 }}>
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 }} data-testid="pricing-matrix-label" testID="pricing-matrix-label">
          {tx('pricing.matrix.label', 'Decision matrix')}
        </Text>
        <Text style={{ color: colors.text, fontSize: 28, fontWeight: '900', letterSpacing: -0.7 }} data-testid="pricing-matrix-title" testID="pricing-matrix-title">
          {tx('pricing.matrix.title', 'Compare the commercial shape of each tier.')}
        </Text>
        <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 21, maxWidth: 780 }} data-testid="pricing-matrix-subtitle" testID="pricing-matrix-subtitle">
          {tx('pricing.matrix.subtitle', 'The matrix keeps the conversation focused on capacity, support, rollout posture, and the kind of team each plan is best suited for.')}
        </Text>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} data-testid="pricing-feature-matrix-scroll" testID="pricing-feature-matrix-scroll">
        <View style={{ minWidth: 860, gap: 0 }}>
          <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: withAlpha(colors.text, '10'), paddingBottom: 10 }}>
            <Text style={{ flex: 1.5, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 }}>{tx('pricing.matrix.capability', 'Capability')}</Text>
            {tiers.map((tier) => (
              <Text key={tier.id} style={{ flex: 1, color: colors.text, fontSize: 12, fontWeight: '800', textAlign: 'center' }} data-testid={`pricing-matrix-header-${tier.id}`} testID={`pricing-matrix-header-${tier.id}`}>
                {tier.name}
              </Text>
            ))}
          </View>

          {matrixRows.map((row, index) => (
            <View
              key={`${row.label}-${index}`}
              style={{
                flexDirection: 'row',
                borderBottomWidth: index === matrixRows.length - 1 ? 0 : 1,
                borderBottomColor: withAlpha(colors.text, '0C'),
                paddingVertical: 14,
                backgroundColor: index % 2 === 0 ? 'transparent' : withAlpha(colors.text, '03'),
              }}
              data-testid={`pricing-matrix-row-${index}`}
              testID={`pricing-matrix-row-${index}`}
            >
              <Text style={{ flex: 1.5, color: colors.text, fontSize: 12, fontWeight: '800', paddingRight: 12 }}>{row.label}</Text>
              <Text style={{ flex: 1, color: colors.textSec, fontSize: 11, textAlign: 'center', lineHeight: 18 }}>{row.values.free}</Text>
              <Text style={{ flex: 1, color: colors.textSec, fontSize: 11, textAlign: 'center', lineHeight: 18 }}>{row.values.basic}</Text>
              <Text style={{ flex: 1, color: colors.textSec, fontSize: 11, textAlign: 'center', lineHeight: 18 }}>{row.values.premium}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </View>
  );
};