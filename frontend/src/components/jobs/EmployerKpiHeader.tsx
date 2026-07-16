import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

type KpiPayload = {
  kpis?: {
    time_to_hire_days?: number;
    stage_conversion_pct?: number;
    offer_acceptance_pct?: number;
    active_bottlenecks?: number;
  };
  counts?: {
    total_applications?: number;
    progressed_applications?: number;
    offers_sent?: number;
    offers_accepted?: number;
  };
  window_days?: number;
};

type EmployerKpiHeaderProps = {
  onDrilldown?: (filterKey: 'time-to-hire' | 'stage-conversion' | 'offer-acceptance' | 'active-bottlenecks') => void;
};

export function EmployerKpiHeader({ onDrilldown }: EmployerKpiHeaderProps) {
  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [payload, setPayload] = useState<KpiPayload | null>(null);

  const cardBg = colors.card;
  const border = colors.border;
  const tileBg = colors.bgSoft || colors.cardMuted || colors.bg;
  const text = colors.text;
  const muted = colors.textMuted;

  const load = useCallback(async (silent = false) => {
    setError('');
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const res = await api.get('/jobs/employer/kpi-header', { params: { window_days: 30 } });
      setPayload(res.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load hiring KPIs.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => {
      void load(true);
    }, 45000);
    return () => clearInterval(timer);
  }, [load]);

  if (loading) {
    return (
      <View style={{ backgroundColor: cardBg, borderWidth: 1, borderColor: border, borderRadius: 14, padding: 14, marginBottom: 16 }} data-testid="employer-kpi-header-loading" testID="employer-kpi-header-loading">
        <ActivityIndicator color={colors.primary} />
        <Text style={{ color: muted, fontSize: 11, marginTop: 8 }}>Loading Hiring Command KPIs...</Text>
      </View>
    );
  }

  const kpis = payload?.kpis || {};
  const counts = payload?.counts || {};
  const cards = [
    {
      id: 'time-to-hire',
      label: 'Avg Time-to-Hire',
      value: `${Number(kpis.time_to_hire_days || 0).toFixed(1)}d`,
      hint: `${Number(counts.total_applications || 0)} applications in 30d`,
      color: colors.infoText,
    },
    {
      id: 'stage-conversion',
      label: 'Stage Conversion',
      value: `${Number(kpis.stage_conversion_pct || 0).toFixed(1)}%`,
      hint: `${Number(counts.progressed_applications || 0)} progressed`,
      color: colors.primary,
    },
    {
      id: 'offer-acceptance',
      label: 'Offer Acceptance',
      value: `${Number(kpis.offer_acceptance_pct || 0).toFixed(1)}%`,
      hint: `${Number(counts.offers_accepted || 0)}/${Number(counts.offers_sent || 0)} accepted`,
      color: colors.successText,
    },
    {
      id: 'active-bottlenecks',
      label: 'Active Bottlenecks',
      value: `${Number(kpis.active_bottlenecks || 0)}`,
      hint: 'Candidates currently beyond SLA',
      color: Number(kpis.active_bottlenecks || 0) > 0 ? colors.warningText : colors.muted,
    },
  ];

  return (
    <View style={{ backgroundColor: cardBg, borderWidth: 1, borderColor: border, borderRadius: 14, padding: 14, marginBottom: 16 }} data-testid="employer-kpi-header" testID="employer-kpi-header">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <View>
          <Text style={{ color: text, fontSize: 17, fontWeight: '800' }} data-testid="employer-kpi-header-title" testID="employer-kpi-header-title">Hiring Command KPI Header</Text>
          <Text style={{ color: muted, fontSize: 10, marginTop: 2 }}>
            Unified hiring performance snapshot (last 30 days)
          </Text>
        </View>
        <Pressable
          onPress={() => void load(true)}
          disabled={refreshing}
          style={{ borderWidth: 1, borderColor: border, borderRadius: 8, backgroundColor: tileBg, paddingHorizontal: 10, paddingVertical: 7 }}
          data-testid="employer-kpi-header-refresh-button"
          testID="employer-kpi-header-refresh-button"
        >
          <Text style={{ color: text, fontSize: 10, fontWeight: '800' }}>{refreshing ? 'Refreshing...' : 'Refresh KPIs'}</Text>
        </Pressable>
      </View>

      {error ? (
        <View style={{ borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, borderRadius: 8, padding: 8, marginBottom: 10 }} data-testid="employer-kpi-header-error" testID="employer-kpi-header-error">
          <Text style={{ color: colors.errorText, fontSize: 10, fontWeight: '700' }}>{error}</Text>
        </View>
      ) : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="employer-kpi-header-cards-row" testID="employer-kpi-header-cards-row">
        {cards.map((card) => (
          <Pressable
            key={card.id}
            onPress={() => onDrilldown?.(card.id as 'time-to-hire' | 'stage-conversion' | 'offer-acceptance' | 'active-bottlenecks')}
            style={{ flex: 1, minWidth: 170, borderWidth: 1, borderColor: border, borderRadius: 10, backgroundColor: tileBg, padding: 10 }}
            data-testid={`employer-kpi-card-${card.id}`}
            testID={`employer-kpi-card-${card.id}`}
          >
            <Text style={{ color: muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{card.label}</Text>
            <Text style={{ color: card.color, fontSize: 22, fontWeight: '900', marginTop: 4 }} data-testid={`employer-kpi-card-value-${card.id}`} testID={`employer-kpi-card-value-${card.id}`}>
              {card.value}
            </Text>
            <Text style={{ color: muted, fontSize: 10, marginTop: 4 }}>{card.hint}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
