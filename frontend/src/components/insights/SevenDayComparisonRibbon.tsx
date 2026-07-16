import React from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type ComparisonMetric = {
  id: string;
  label: string;
  current: number;
  previous: number;
  suffix?: string;
  precision?: number;
};

type SevenDayComparisonRibbonProps = {
  title: string;
  subtitle: string;
  metrics: ComparisonMetric[];
  colors: any;
  testIdPrefix: string;
  refreshing?: boolean;
  onRefresh?: () => void;
};

const formatMetric = (value: number, precision: number = 0) => {
  if (!Number.isFinite(value)) return '0';
  return value.toFixed(precision);
};

export const SevenDayComparisonRibbon = ({
  title,
  subtitle,
  metrics,
  colors,
  testIdPrefix,
  refreshing = false,
  onRefresh,
}: SevenDayComparisonRibbonProps) => {
  if (!metrics || metrics.length === 0) return null;

  const textMuted = colors.textMuted || colors.muted || colors.textSec || colors.text;
  const bgSoft = colors.bgSoft || colors.surface || colors.card;
  const successTone = colors.successText || colors.success || colors.primary;
  const errorTone = colors.errorText || colors.error || textMuted;

  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        padding: 12,
        gap: 10,
      }}
      data-testid={`${testIdPrefix}-ribbon`}
      testID={`${testIdPrefix}-ribbon`}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View>
          <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text }} data-testid={`${testIdPrefix}-title`} testID={`${testIdPrefix}-title`}>{title}</Text>
          <Text style={{ fontSize: 11, color: textMuted }} data-testid={`${testIdPrefix}-subtitle`} testID={`${testIdPrefix}-subtitle`}>{subtitle}</Text>
        </View>
        {!!onRefresh && (
          <TouchableOpacity
            onPress={onRefresh}
            style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: bgSoft, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 5 }}
            data-testid={`${testIdPrefix}-refresh-button`}
            testID={`${testIdPrefix}-refresh-button`}
          >
            {refreshing ? <ActivityIndicator size="small" color={textMuted} /> : <Ionicons name="refresh-outline" size={13} color={textMuted} />}
            <Text style={{ fontSize: 10, color: textMuted, fontWeight: '700' }}>Refresh</Text>
          </TouchableOpacity>
        )}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid={`${testIdPrefix}-metrics`} testID={`${testIdPrefix}-metrics`}>
        {metrics.map((metric) => {
          const delta = metric.current - metric.previous;
          const direction = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
          const tone = direction === 'up' ? successTone : direction === 'down' ? errorTone : textMuted;
          const icon = direction === 'up' ? 'trending-up' : direction === 'down' ? 'trending-down' : 'remove';
          const precision = metric.precision ?? 0;

          return (
            <View
              key={metric.id}
              style={{
                minWidth: 170,
                flexGrow: 1,
                borderRadius: 11,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: bgSoft,
                padding: 10,
                gap: 5,
              }}
              data-testid={`${testIdPrefix}-metric-${metric.id}`}
              testID={`${testIdPrefix}-metric-${metric.id}`}
            >
              <Text style={{ fontSize: 10, color: textMuted }}>{metric.label}</Text>
              <Text style={{ fontSize: 15, fontWeight: '900', color: colors.text }}>
                {formatMetric(metric.current, precision)}{metric.suffix || ''}
              </Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <Ionicons name={icon as any} size={12} color={tone} />
                <Text style={{ fontSize: 10, fontWeight: '700', color: tone }}>
                  {delta >= 0 ? '+' : ''}{formatMetric(delta, precision)}{metric.suffix || ''} vs prior 7d
                </Text>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
