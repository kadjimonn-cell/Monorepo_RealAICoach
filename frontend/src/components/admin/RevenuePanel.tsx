import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const _C = getC(true);

const tx = (_key: string, fallback: string) => fallback;

export default function RevenuePanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const [period, setPeriod] = useState('30d');
  const { data: metrics, loading: mLoading } = useLiveQuery(`/revenue/metrics?period=${period}`, { entity: 'revenue', pollInterval: 60000 });
  const { data: trendsData, loading: tLoading } = useLiveQuery('/revenue/trends?months=6', { entity: 'revenue', pollInterval: 60000 });
  const loading = mLoading || tLoading;
  const trends = trendsData?.trends || [];

  if (loading) return <ActivityIndicator style={{ padding: 30 }} color={C.blue} />;
  if (!metrics) return <Text style={{ color: C.muted, padding: 20 }}>{tx('admin.revenuePanel.auto.text.001', 'Unable to load metrics')}</Text>;

  const metricCards = [
    { label: 'MRR', value: `$${metrics.mrr}`, icon: 'cash', color: C.green, sub: `ARR: $${metrics.arr}` },
    { label: 'Active Subs', value: metrics.active_subscribers, icon: 'people', color: C.blue, sub: `Total: ${metrics.total_subscribers}` },
    { label: 'Churn Rate', value: `${metrics.churn_rate}%`, icon: 'trending-down', color: metrics.churn_rate > 5 ? C.red : C.green, sub: `${metrics.churned} churned` },
    { label: 'ARPU', value: `$${metrics.arpu}`, icon: 'person', color: C.purpleText, sub: `LTV: $${metrics.ltv}` },
    { label: 'New Subs', value: metrics.new_subscribers, icon: 'add-circle', color: C.green, sub: `Growth: ${metrics.growth_rate}%` },
    { label: 'Canceled', value: metrics.canceled_subscribers, icon: 'close-circle', color: C.red, sub: `of ${metrics.total_subscribers} total` },
  ];

  const maxMrr = Math.max(...trends.map(t => t.mrr), 1);

  return (
    <View data-testid="revenue-panel" testID="revenue-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.revenuePanel.auto.text.002', 'Revenue Analytics')}</Text>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {['7d', '30d', '90d'].map(p => (
            <TouchableOpacity key={p} onPress={() => setPeriod(p)} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: period === p ? (globalThis as any).__alphaColor(C.blue, '20') : 'transparent' }} data-testid={`period-${p}`} testID={`period-${p}`}>
              <Text style={{ color: period === p ? C.blue : C.muted, fontSize: 11, fontWeight: '600' }}>{p}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Metric Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }}>
        {metricCards.map(m => (
          <View key={m.label} style={{ flex: 1, minWidth: 140, backgroundColor: (globalThis as any).__alphaColor(m.color, '08'), borderRadius: 14, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(m.color, '20') }} data-testid={`metric-${m.label.toLowerCase().replace(' ', '-')}`} testID={`metric-${m.label.toLowerCase().replace(' ', '-')}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Ionicons name={m.icon as any} size={14} color={m.color} />
              <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>{m.label}</Text>
            </View>
            <Text style={{ color: m.color, fontSize: 24, fontWeight: '900' }}>{m.value}</Text>
            <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{m.sub}</Text>
          </View>
        ))}
      </View>

      {/* MRR Trend Chart (Bar) */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 20 }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 14 }}>{tx('admin.revenuePanel.auto.text.003', 'MRR Trend')}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8, height: 100 }}>
          {trends.map(t => {
            const h = Math.max(4, (t.mrr / maxMrr) * 90);
            return (
              <View key={t.month} style={{ flex: 1, alignItems: 'center' }}>
                <Text style={{ color: C.muted, fontSize: 8, marginBottom: 4 }}>${t.mrr}</Text>
                <View style={{ height: h, backgroundColor: C.blue, borderRadius: 4, width: '80%' }} />
                <Text style={{ color: C.muted, fontSize: 8, marginTop: 4 }}>{t.label.split(' ')[0]}</Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Growth Trend */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 20 }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 12 }}>{tx('admin.revenuePanel.auto.text.004', 'Subscriber Growth')}</Text>
        <View style={{ gap: 8 }}>
          {trends.map(t => (
            <View key={t.month} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Text style={{ color: C.muted, fontSize: 11, width: 50 }}>{t.label.split(' ')[0]}</Text>
              <View style={{ flexDirection: 'row', gap: 8, flex: 1 }}>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.green, '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 }}>
                  <Text style={{ color: C.green, fontSize: 10, fontWeight: '600' }}>+{t.new_subscribers}</Text>
                </View>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.red, '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 }}>
                  <Text style={{ color: C.red, fontSize: 10, fontWeight: '600' }}>-{t.churned}</Text>
                </View>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor((t.net_growth >= 0 ? C.green : C.red), '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 }}>
                  <Text style={{ color: t.net_growth >= 0 ? C.green : C.red, fontSize: 10, fontWeight: '600' }}>Net: {t.net_growth >= 0 ? '+' : ''}{t.net_growth}</Text>
                </View>
              </View>
              <Text style={{ color: C.text, fontSize: 11, fontWeight: '600' }}>{t.active}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Plan Breakdown */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 12 }}>{tx('admin.revenuePanel.auto.text.005', 'Plan Breakdown')}</Text>
        {Object.entries(metrics.plan_breakdown || {}).map(([plan, data]: [string, any]) => (
          <View key={plan} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: plan === 'enterprise' ? C.purple : plan === 'pro' ? C.blue : C.muted }} />
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '600', textTransform: 'capitalize' }}>{plan}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <Text style={{ color: C.muted, fontSize: 11 }}>{data.count} users</Text>
              <Text style={{ color: C.green, fontSize: 11, fontWeight: '600' }}>${data.revenue}/mo</Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}
