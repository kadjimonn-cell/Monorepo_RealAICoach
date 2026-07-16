import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

const fmt = (n: number) => n >= 1000 ? `$${(n / 1000).toFixed(1)}K` : `$${n.toFixed(0)}`;
const fmtN = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(1)}K` : `${n}`;

export default function UnifiedRevenuePanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const colors = useAdminTheme();
  const T = useExecTheme();
  const { width } = useWindowDimensions();
  const d = width >= 1024;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('30d');

  const load = useCallback(async () => {
    try {
      const res = await api.get(`/revenue/unified?period=${period}`);
      setData(res.data);
    } catch (e) { console.error('Unified revenue error:', e); }
    finally { setLoading(false); }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  const c = data?.combined || {};
  const stripe = data?.stripe || {};
  const iap = data?.iap || {};
  const trends = data?.trends || [];

  const totalMRR = c.total_mrr || 0;
  const stripePct = totalMRR > 0 ? Math.round((stripe.mrr / totalMRR) * 100) : 0;
  const iapPct = 100 - stripePct;

  const maxTrend = Math.max(...trends.map((t: any) => t.total_mrr || 0), 1);

  return (
    <View style={s.panel} data-testid="unified-revenue-panel" testID="unified-revenue-panel">
      {/* Header */}
      <View style={[s.panelHeader, { marginBottom: 16 }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: T.successSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="wallet" size={18} color={T.successText} />
          </View>
          <View>
            <Text style={s.panelTitle}>{tx('admin.unifiedRevenuePanel.auto.text.001', 'Unified Revenue')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.unifiedRevenuePanel.auto.text.002', 'Stripe (Web) + In-App Purchases (Mobile)')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {['7d', '30d', '90d'].map(p => (
            <TouchableOpacity key={p} onPress={() => { setPeriod(p); setLoading(true); }}
              style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: period === p ? (globalThis as any).__alphaColor(T.primary, '20') : 'transparent', borderWidth: 1, borderColor: period === p ? (globalThis as any).__alphaColor(T.primary, '40') : T.border }}
              data-testid={`unified-period-${p}`} testID={`unified-period-${p}`}>
              <Text style={{ color: period === p ? T.primary : T.textMuted, fontSize: 11, fontWeight: '600' }}>{p}</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity onPress={() => { setLoading(true); load(); }} style={s.refreshBtn} data-testid="unified-revenue-refresh" testID="unified-revenue-refresh">
            <Ionicons name="refresh" size={16} color={T.textSec} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Combined KPIs */}
      <View style={{ flexDirection: d ? 'row' : 'column', gap: 10, marginBottom: 16 }}>
        {[
          { label: 'Total MRR', value: fmt(c.total_mrr || 0), icon: 'trending-up', color: T.successText },
          { label: 'Total ARR', value: fmt(c.total_arr || 0), icon: 'cash', color: T.primary },
          { label: 'Active Subscribers', value: fmtN(c.total_active_subscribers || 0), icon: 'people', color: T.purpleText },
          { label: 'ARPU', value: `$${(c.arpu || 0).toFixed(2)}`, icon: 'person', color: T.cyan },
          { label: 'LTV', value: fmt(c.ltv || 0), icon: 'diamond', color: T.pink },
          { label: 'Churn Rate', value: `${c.churn_rate || 0}%`, icon: 'trending-down', color: c.churn_rate > 5 ? T.error : T.warning },
        ].map((kpi, i) => (
          <View key={i} style={{ flex: d ? 1 : undefined, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: kpi.color }}
            data-testid={`unified-kpi-${kpi.label.toLowerCase().replace(/\s/g, '-')}`} testID={`unified-kpi-${kpi.label.toLowerCase().replace(/\s/g, '-')}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(kpi.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={kpi.icon as any} size={14} color={kpi.color} />
              </View>
              <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '600', flex: 1 }}>{kpi.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.5 }}>{kpi.value}</Text>
          </View>
        ))}
      </View>

      {/* Revenue Split: Stripe vs IAP */}
      <View style={{ flexDirection: d ? 'row' : 'column', gap: 12, marginBottom: 16 }}>
        {/* Stripe Card */}
        <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="unified-stripe-card" testID="unified-stripe-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: `${colors.indigo}20`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="card" size={16} color={colors.indigoText} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.unifiedRevenuePanel.auto.text.003', 'Stripe (Web)')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{stripePct}% of total revenue</Text>
            </View>
            <Text style={{ color: colors.indigoText, fontSize: 18, fontWeight: '800' }}>{fmt(stripe.mrr || 0)}</Text>
          </View>
          <View style={{ height: 4, borderRadius: 2, backgroundColor: T.border, marginBottom: 10 }}>
            <View style={{ height: 4, borderRadius: 2, backgroundColor: colors.indigo, width: `${stripePct}%` }} />
          </View>
          <View style={{ flexDirection: 'row', gap: 16 }}>
            <View><Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.unifiedRevenuePanel.auto.text.004', 'Active')}</Text><Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{stripe.active_subscribers || 0}</Text></View>
            <View><Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.unifiedRevenuePanel.auto.text.005', 'New')}</Text><Text style={{ color: T.successText, fontSize: 13, fontWeight: '700' }}>+{stripe.new_subscribers || 0}</Text></View>
            <View><Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.unifiedRevenuePanel.auto.text.006', 'Churned')}</Text><Text style={{ color: T.error, fontSize: 13, fontWeight: '700' }}>{stripe.churned || 0}</Text></View>
          </View>
          {stripe.plan_breakdown && (
            <View style={{ marginTop: 10, flexDirection: 'row', gap: 8 }}>
              {Object.entries(stripe.plan_breakdown).map(([plan, count]: any) => (
                <View key={plan} style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: T.border }}>
                  <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600' }}>{plan}: {count}</Text>
                </View>
              ))}
            </View>
          )}
        </View>

        {/* IAP Card */}
        <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="unified-iap-card" testID="unified-iap-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: T.successSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="phone-portrait" size={16} color={T.successText} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.unifiedRevenuePanel.auto.text.007', 'In-App Purchases (Mobile)')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{iapPct}% of total revenue</Text>
            </View>
            <Text style={{ color: T.successText, fontSize: 18, fontWeight: '800' }}>{fmt(iap.mrr || 0)}</Text>
          </View>
          <View style={{ height: 4, borderRadius: 2, backgroundColor: T.border, marginBottom: 10 }}>
            <View style={{ height: 4, borderRadius: 2, backgroundColor: T.success, width: `${iapPct}%` }} />
          </View>
          <View style={{ flexDirection: 'row', gap: 16 }}>
            <View>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.unifiedRevenuePanel.auto.text.008', 'Apple')}</Text>
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{iap.apple_active || 0}</Text>
            </View>
            <View>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.unifiedRevenuePanel.auto.text.009', 'Google')}</Text>
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{iap.google_active || 0}</Text>
            </View>
            <View>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.unifiedRevenuePanel.auto.text.010', 'Total Txns')}</Text>
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{iap.total_transactions || 0}</Text>
            </View>
            <View>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.unifiedRevenuePanel.auto.text.011', 'New')}</Text>
              <Text style={{ color: T.successText, fontSize: 13, fontWeight: '700' }}>+{iap.new_transactions || 0}</Text>
            </View>
          </View>
        </View>
      </View>

      {/* Monthly MRR Trend (Stacked Bar) */}
      {trends.length > 0 && (
        <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="unified-trends-chart" testID="unified-trends-chart">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 4 }}>{tx('admin.unifiedRevenuePanel.auto.text.012', 'Monthly MRR Trend')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 16 }}>{tx('admin.unifiedRevenuePanel.auto.text.013', 'Stacked: Stripe (purple) + IAP (green)')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: d ? 12 : 6, height: 140 }}>
            {trends.map((t: any, i: number) => {
              const stripeH = maxTrend > 0 ? (t.stripe_mrr / maxTrend) * 120 : 0;
              const iapH = maxTrend > 0 ? (t.iap_mrr / maxTrend) * 120 : 0;
              return (
                <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                  <Text style={{ color: T.textMuted, fontSize: 9, marginBottom: 4 }}>{fmt(t.total_mrr)}</Text>
                  <View style={{ width: '80%', maxWidth: 48 }}>
                    {iapH > 0 && <View style={{ height: Math.max(2, iapH), backgroundColor: T.success, borderTopLeftRadius: 4, borderTopRightRadius: 4 }} />}
                    {stripeH > 0 && <View style={{ height: Math.max(2, stripeH), backgroundColor: colors.indigo, borderBottomLeftRadius: iapH > 0 ? 0 : 4, borderBottomRightRadius: iapH > 0 ? 0 : 4, borderTopLeftRadius: iapH > 0 ? 0 : 4, borderTopRightRadius: iapH > 0 ? 0 : 4 }} />}
                  </View>
                  <Text style={{ color: T.textMuted, fontSize: 9, marginTop: 4 }}>{t.label?.slice(0, 3)}</Text>
                </View>
              );
            })}
          </View>
          <View style={{ flexDirection: 'row', gap: 16, marginTop: 12, justifyContent: 'center' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: colors.indigo }} />
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.unifiedRevenuePanel.auto.text.014', 'Stripe (Web)')}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: T.success }} />
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.unifiedRevenuePanel.auto.text.015', 'IAP (Mobile)')}</Text>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
