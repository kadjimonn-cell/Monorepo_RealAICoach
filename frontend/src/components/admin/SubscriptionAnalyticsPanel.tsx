import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAiInsight, AIInsightPanel, PriorityItem, FindingItem, QuickWinItem } from './AIInsightHelpers';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

// ── Recharts (web only) ──
 
let PieChart: any, Pie: any, Cell: any, Tooltip: any, ResponsiveContainer: any;
if (Platform.OS === 'web') {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const rc = require('recharts');
  PieChart = rc.PieChart; Pie = rc.Pie; Cell = rc.Cell;
  Tooltip = rc.Tooltip; ResponsiveContainer = rc.ResponsiveContainer;
}

const tx = (_key: string, fallback: string) => fallback;

function FunnelBar({ stage, count, pct, color, idx }: { stage: string; count: number; pct: number; color: string; idx: number }) {
  const T = useExecTheme();
  const widths = [100, 80, 60, 50];
  return (
    <View style={{ alignItems: 'center', flex: 1 }} data-testid={`funnel-stage-${idx}`} testID={`funnel-stage-${idx}`}>
      <View style={{ width: `${widths[idx] || 70}%`, height: 48, backgroundColor: (globalThis as any).__alphaColor(color, '20'), borderRadius: 8, justifyContent: 'center', alignItems: 'center', marginBottom: 6 }}>
        <Text style={{ color, fontSize: 16, fontWeight: '800' }}>{count}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{stage}</Text>
      <Text style={{ color: T.textMuted, fontSize: 10 }}>{pct}%</Text>
      {idx < 3 && <Ionicons name="chevron-forward" size={14} color={T.textMuted} style={{ position: 'absolute', right: -6, top: 18 }} />}
    </View>
  );
}

function TrendChart({ trends }: { trends: any[] }) {
  const s = useExecStyles();
  const T = useExecTheme();
  if (!trends?.length) return null;
  const maxMRR = Math.max(...trends.map(t => t.mrr), 1);
  return (
    <View data-testid="mrr-trend-chart" testID="mrr-trend-chart">
      <Text style={[s.chartTitle, { marginBottom: 12 }]}>{tx('admin.subscriptionAnalyticsPanel.auto.text.001', 'MRR Trend (6 Months)')}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: 140, paddingBottom: 20 }}>
        {trends.map((t, i) => {
          const h = Math.max((t.mrr / maxMRR) * 100, 4);
          return (
            <View key={i} style={{ flex: 1, alignItems: 'center' }} data-testid={`trend-bar-${i}`} testID={`trend-bar-${i}`}>
              <Text style={{ color: T.successText, fontSize: 9, fontWeight: '700', marginBottom: 4 }}>${t.mrr.toFixed(0)}</Text>
              <View style={{ width: '70%', height: h, backgroundColor: T.primary, borderRadius: 4, minHeight: 4 }} />
              <Text style={{ color: T.textMuted, fontSize: 8, marginTop: 4 }}>{t.month.slice(0, 3)}</Text>
              <View style={{ flexDirection: 'row', gap: 2, marginTop: 2 }}>
                <Text style={{ color: T.successText, fontSize: 7 }}>+{t.new_subs}</Text>
                {t.churned > 0 && <Text style={{ color: T.error, fontSize: 7 }}>-{t.churned}</Text>}
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
}

function PlatformRevenuePie({ platform }: { platform: any }) {
  const colors = useAdminTheme();
  const T = useExecTheme();
  if (Platform.OS !== 'web' || !PieChart) return null;
  const data = [
    { name: 'App Store', value: platform?.apple?.mrr || 0, color: T.textMuted },
    { name: 'Google Play', value: platform?.google?.mrr || 0, color: 'var(--app-success)' }, // @theme-ok brand identifier
    { name: 'Stripe (Web)', value: platform?.stripe?.mrr || 0, color: colors.primary },
  ].filter(d => d.value > 0);
  if (data.length === 0) return <Text style={{ color: T.textMuted, fontSize: 11, textAlign: 'center', padding: 20 }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.002', 'No revenue data yet')}</Text>;
  return (
    <View style={{ height: 180, width: '100%' }} data-testid="platform-revenue-pie" testID="platform-revenue-pie">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={45} outerRadius={70} paddingAngle={3} dataKey="value" label={({ name, value }: any) => `${name}: $${value.toFixed(2)}`} labelLine={false}>
            {data.map((entry: any, i: number) => <Cell key={i} fill={entry.color} />)}
          </Pie>
          <Tooltip formatter={(value: number) => `$${value.toFixed(2)}`} contentStyle={{ backgroundColor: T.card, border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 11 }} />
        </PieChart>
      </ResponsiveContainer>
    </View>
  );
}

export default function SubscriptionAnalyticsPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const colors = useAdminTheme();
  const T = useExecTheme();
  const [period, setPeriod] = useState('30d');
  const { data, loading } = useLiveQuery(`/admin/subscription-analytics?period=${period}`, { entity: 'subscriptions', pollInterval: 60000 });

  if (loading && !data) {
    return (
      <View style={{ paddingVertical: 40, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 12 }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.003', 'Loading subscription analytics...')}</Text>
      </View>
    );
  }

  const kpis = data?.kpis || {};
  const dist = data?.distribution || {};
  const platform = data?.platform || {};
  const billing = data?.billing || {};
  const planCatalog = Array.isArray(data?.plan_catalog) ? data.plan_catalog : [];
  const funnel = data?.funnel || [];
  const trends = data?.trends || [];
  const totalDist = (dist.free || 0) + (dist.basic || 0) + (dist.premium || 0);
  const funnelColors = [T.primary, T.warning, T.success, T.cyan];
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _totalPlatformSubs = (platform.apple?.subs || 0) + (platform.google?.subs || 0) + (platform.stripe?.subs || 0);

  const formatPrice = (value: any, suffix = '') => {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount < 0) {
      return `Unavailable${suffix}`;
    }
    return `$${amount.toFixed(2)}${suffix}`;
  };

  const activePlans = planCatalog.length > 0
    ? planCatalog
    : [
      { plan_id: 'free', name: 'Free', monthly_price: 0, yearly_price: 0, yearly_discount_pct: 0 },
      { plan_id: 'basic', name: 'Basic', monthly_price: null, yearly_price: null, yearly_discount_pct: null },
      { plan_id: 'premium', name: 'Premium', monthly_price: null, yearly_price: null, yearly_discount_pct: null },
    ];

  const savingsHighlights = activePlans
    .filter((p: any) => Number(p?.monthly_price) > 0 && Number(p?.yearly_price) > 0)
    .map((p: any) => {
      const monthly = Number(p.monthly_price);
      const yearly = Number(p.yearly_price);
      const discount = monthly > 0 ? Math.max(0, 100 - ((yearly / (monthly * 12)) * 100)) : 0;
      return `${p.name || p.plan_id}: ${discount.toFixed(1)}% off yearly`;
    });

  return (
    <View data-testid="subscription-analytics-panel" testID="subscription-analytics-panel">
      {/* Header */}
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="card" size={18} color={T.primary} />
            <Text style={s.chartTitle}>{tx('admin.subscriptionAnalyticsPanel.auto.text.004', 'Subscription Analytics')}</Text>
          </View>
          <View style={s.periodTabs}>
            {['7d', '30d', '90d'].map(p => (
              <TouchableOpacity key={p} style={[s.periodTab, period === p && s.periodTabActive]} onPress={() => setPeriod(p)} data-testid={`sub-period-${p}`} testID={`sub-period-${p}`}>
                <Text style={[s.periodLabel, period === p && s.periodLabelActive]}>{p}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* KPI Cards */}
        <View style={s.metricsRow}>
          {[
            { label: 'MRR', value: `$${kpis.mrr?.toFixed(2) || '0'}`, color: T.successText, icon: 'trending-up' },
            { label: 'ARR', value: `$${kpis.arr?.toFixed(2) || '0'}`, color: T.primary, icon: 'bar-chart' },
            { label: 'Churn Rate', value: `${kpis.churn_rate || 0}%`, color: kpis.churn_rate > 5 ? T.error : T.success, icon: 'trending-down' },
            { label: 'LTV', value: `$${kpis.ltv?.toFixed(2) || '0'}`, color: T.cyan, icon: 'diamond' },
            { label: 'ARPU', value: `$${kpis.arpu?.toFixed(2) || '0'}`, color: T.purpleText, icon: 'person' },
            { label: 'Active Subs', value: `${kpis.active_subs || 0}`, color: T.successText, icon: 'checkmark-circle' },
          ].map((m, i) => (
            <View key={i} style={s.metricBox} data-testid={`sub-kpi-${i}`} testID={`sub-kpi-${i}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Ionicons name={m.icon as any} size={14} color={m.color} />
                <Text style={s.metricLabel}>{m.label}</Text>
              </View>
              <Text style={s.metricValue}>{m.value}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Period Stats */}
      <View style={s.panel}>
        <Text style={[s.chartTitle, { marginBottom: 12 }]}>Period Highlights ({period})</Text>
        <View style={{ flexDirection: 'row', gap: 12 }}>
          <View style={{ flex: 1, backgroundColor: T.successSoft, borderRadius: 10, padding: 14, alignItems: 'center' }}>
            <Text style={{ color: T.successText, fontSize: 22, fontWeight: '800' }}>{kpis.new_subs || 0}</Text>
            <Text style={{ color: T.successText, fontSize: 10, fontWeight: '600', marginTop: 2 }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.005', 'New Subscribers')}</Text>
          </View>
          <View style={{ flex: 1, backgroundColor: T.errorSoft, borderRadius: 10, padding: 14, alignItems: 'center' }}>
            <Text style={{ color: T.error, fontSize: 22, fontWeight: '800' }}>{kpis.churned || 0}</Text>
            <Text style={{ color: T.error, fontSize: 10, fontWeight: '600', marginTop: 2 }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.006', 'Churned')}</Text>
          </View>
          <View style={{ flex: 1, backgroundColor: T.primarySoft, borderRadius: 10, padding: 14, alignItems: 'center' }}>
            <Text style={{ color: T.primary, fontSize: 22, fontWeight: '800' }}>{kpis.conversion_rate || 0}%</Text>
            <Text style={{ color: T.primary, fontSize: 10, fontWeight: '600', marginTop: 2 }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.007', 'Conversion Rate')}</Text>
          </View>
        </View>
      </View>

      {/* Revenue by Platform + Billing Period */}
      <View style={{ flexDirection: 'row', gap: 12 }}>
        {/* Platform Revenue Breakdown */}
        <View style={[s.panel, { flex: 1 }]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="layers" size={16} color={T.primary} />
            <Text style={s.chartTitle}>{tx('admin.subscriptionAnalyticsPanel.auto.text.008', 'Revenue by Platform')}</Text>
          </View>
          <PlatformRevenuePie platform={platform} />
          <View style={{ gap: 8, marginTop: 12 }}>
            {[
              { name: 'App Store (iOS)', icon: 'logo-apple', color: T.textMuted, subs: platform.apple?.subs || 0, mrr: platform.apple?.mrr || 0, txns: platform.apple?.txns || 0 },
              { name: 'Google Play', icon: 'logo-google', color: 'var(--app-success)', subs: platform.google?.subs || 0, mrr: platform.google?.mrr || 0, txns: platform.google?.txns || 0 }, // @theme-ok brand identifier
              { name: 'Stripe (Web)', icon: 'card', color: colors.indigoText, subs: platform.stripe?.subs || 0, mrr: platform.stripe?.mrr || 0 },
            ].map((p, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', padding: 10, backgroundColor: T.bg, borderRadius: 10, borderWidth: 1, borderColor: T.border }} data-testid={`platform-row-${i}`} testID={`platform-row-${i}`}>
                <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(p.color, '15'), alignItems: 'center', justifyContent: 'center', marginRight: 10 }}>
                  <Ionicons name={p.icon as any} size={16} color={p.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{p.name}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{p.subs} subscribers{p.txns !== undefined ? ` | ${p.txns} txns this period` : ''}</Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ color: p.color, fontSize: 15, fontWeight: '800' }}>${p.mrr.toFixed(2)}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.009', 'MRR')}</Text>
                </View>
              </View>
            ))}
          </View>
        </View>

        {/* Billing Period Breakdown */}
        <View style={[s.panel, { flex: 1 }]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="calendar" size={16} color={T.primary} />
            <Text style={s.chartTitle}>{tx('admin.subscriptionAnalyticsPanel.auto.text.010', 'Billing Period')}</Text>
          </View>
          <View style={{ gap: 12 }}>
            {/* Monthly vs Yearly visual */}
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <View style={{ flex: 1, padding: 16, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(T.primary, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '25'), alignItems: 'center' }} data-testid="billing-monthly" testID="billing-monthly">
                <Ionicons name="calendar-outline" size={22} color={T.primary} />
                <Text style={{ color: T.text, fontSize: 24, fontWeight: '800', marginTop: 6 }}>{billing.monthly || 0}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.011', 'Monthly')}</Text>
                <View style={{ marginTop: 6, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(T.primary, '20') }}>
                  <Text style={{ color: T.primary, fontSize: 10, fontWeight: '700' }}>{billing.monthly_pct || 0}%</Text>
                </View>
              </View>
              <View style={{ flex: 1, padding: 16, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(T.success, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '25'), alignItems: 'center' }} data-testid="billing-yearly" testID="billing-yearly">
                <Ionicons name="calendar" size={22} color={T.successText} />
                <Text style={{ color: T.text, fontSize: 24, fontWeight: '800', marginTop: 6 }}>{billing.yearly || 0}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.012', 'Yearly')}</Text>
                <View style={{ marginTop: 6, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(T.success, '20') }}>
                  <Text style={{ color: T.successText, fontSize: 10, fontWeight: '700' }}>{billing.yearly_pct || 0}%</Text>
                </View>
              </View>
            </View>
            {/* Live yearly savings note */}
            <View style={{ padding: 10, backgroundColor: T.bg, borderRadius: 8, borderWidth: 1, borderColor: T.border }} data-testid="subscription-live-savings-note" testID="subscription-live-savings-note">
              <Text style={{ color: T.textMuted, fontSize: 10, textAlign: 'center' }}>
                {savingsHighlights.length > 0
                  ? `${tx('admin.subscriptionAnalyticsPanel.auto.text.013c', 'Live yearly discounts')}: ${savingsHighlights.join(' • ')}`
                  : tx('admin.subscriptionAnalyticsPanel.auto.text.013b', 'Live yearly discount data is not available yet')}
              </Text>
            </View>
            {/* Plan prices reference */}
            <View style={{ gap: 6 }}>
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.014', 'Active Plans')}</Text>
              {activePlans.map((p: any, i: number) => {
                const color = i === 0 ? T.textMuted : i === 1 ? T.primary : T.purpleText;
                return (
                <View key={p.plan_id || i} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: i < activePlans.length - 1 ? 1 : 0, borderBottomColor: (globalThis as any).__alphaColor(T.border, '50') }} data-testid={`active-plan-row-${p.plan_id || i}`} testID={`active-plan-row-${p.plan_id || i}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />
                    <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }}>{p.name || p.plan_id || `Plan ${i + 1}`}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 12 }}>
                    <Text style={{ color: T.textSec, fontSize: 10 }}>{formatPrice(p.monthly_price, '/mo')}</Text>
                    <Text style={{ color: T.successText, fontSize: 10, fontWeight: '600' }}>{formatPrice(p.yearly_price, '/yr')}</Text>
                  </View>
                </View>
                );
              })}
            </View>
          </View>
        </View>
      </View>

      {/* Plan Distribution */}
      <View style={s.panel}>
        <Text style={[s.chartTitle, { marginBottom: 12 }]}>{tx('admin.subscriptionAnalyticsPanel.auto.text.015', 'Plan Distribution')}</Text>
        <View style={{ gap: 8 }}>
          {[
            { plan: 'Free', count: dist.free || 0, color: T.textMuted },
            { plan: 'Basic', count: dist.basic || 0, color: T.primary },
            { plan: 'Premium', count: dist.premium || 0, color: T.purpleText },
          ].map((p, i) => {
            const pct = totalDist > 0 ? Math.round((p.count / totalDist) * 100) : 0;
            return (
              <View key={i} data-testid={`plan-dist-${i}`} testID={`plan-dist-${i}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: p.color }} />
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{p.plan}</Text>
                  </View>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{p.count} users ({pct}%)</Text>
                </View>
                <View style={{ height: 8, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
                  <View style={{ width: `${pct}%`, height: '100%', backgroundColor: p.color, borderRadius: 4 }} />
                </View>
              </View>
            );
          })}
        </View>
      </View>

      {/* MRR Trend */}
      <View style={s.panel}>
        <TrendChart trends={trends} />
      </View>

      {/* Conversion Funnel */}
      <View style={s.panel}>
        <Text style={[s.chartTitle, { marginBottom: 12 }]}>Conversion Funnel ({period})</Text>
        <View style={{ flexDirection: 'row', gap: 4 }}>
          {funnel.map((f: any, i: number) => (
            <FunnelBar key={i} stage={f.stage} count={f.count} pct={f.pct} color={funnelColors[i]} idx={i} />
          ))}
        </View>
      </View>

      {/* AI Churn Predictor */}
      <ChurnAISection />
    </View>
  );
}

function ChurnAISection() {
  const colors = useAdminTheme();
  const ai = useAiInsight('churn_predictor', 'churn-predictor');
  const [show, setShow] = useState(false);

  return (
    <View style={{ marginTop: 16 }}>
      <TouchableOpacity onPress={() => setShow(!show)} style={{ backgroundColor: `${colors.accent}20`, borderWidth: 1, borderColor: `${colors.accent}40`, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="churn-ai-toggle" testID="churn-ai-toggle">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
          <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '700' }}>{tx('admin.subscriptionAnalyticsPanel.auto.text.016', 'AI Churn Predictor')}</Text>
        </View>
        <Ionicons name={show ? 'chevron-up' : 'chevron-down'} size={16} color={'var(--app-primary)'} />
      </TouchableOpacity>
      {show && (
        <View style={{ marginTop: 12 }}>
          <AIInsightPanel
            config={{
              cacheKey: 'churn_predictor', postEndpoint: 'churn-predictor',
              title: 'AI Churn Predictor', subtitle: 'subscription churn',
              scoreKey: 'churn_risk_score', scoreLabel: 'Churn Risk Score',
              summaryKey: 'executive_summary',
              sections: [
                { key: 'risk_segments', title: 'Risk Segments', icon: 'people', renderItem: (item, idx, total) => <FindingItem key={idx} item={{...item, finding: item.segment, severity: item.churn_probability?.includes?.('7') || item.churn_probability?.includes?.('8') || item.churn_probability?.includes?.('9') ? 'high' : 'medium', recommendation: item.primary_reason}} idx={idx} total={total} /> },
                { key: 'retention_strategies', title: 'Retention Strategies', icon: 'heart', renderItem: (item, idx, total) => <PriorityItem key={idx} item={item} idx={idx} total={total} /> },
                { key: 'early_warning_signals', title: 'Early Warning Signals', icon: 'warning', renderItem: (item, idx, total) => <QuickWinItem key={idx} item={{action: item.signal, expected_impact: `${item.threshold} | ${item.action}`}} idx={idx} total={total} /> },
              ],
            }}
            data={ai.data}
            loading={ai.loading}
            onRun={ai.run}
          />
        </View>
      )}
    </View>
  );
}
