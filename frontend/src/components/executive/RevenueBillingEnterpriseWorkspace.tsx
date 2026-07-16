import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  RefreshControl, useWindowDimensions, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';

/* ─── helpers ─── */
const tx_ = (t: (k: string) => string, key: string, fallback: string) => {
  const v = t(key);
  return v === key ? fallback : v;
};
const fmt = (n: number | null | undefined, decimals = 2): string => {
  if (n == null || isNaN(Number(n))) return '--';
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
};
const fmtInt = (n: number | null | undefined): string => {
  if (n == null || isNaN(Number(n))) return '--';
  return Math.round(Number(n)).toLocaleString();
};
const fmtPct = (n: number | null | undefined): string => {
  if (n == null || isNaN(Number(n))) return '--';
  return `${Number(n).toFixed(1)}%`;
};
const fmtUsd = (n: number | null | undefined): string => {
  if (n == null || isNaN(Number(n))) return '--';
  return `$${fmt(n)}`;
};
const safeArr = (v: any): any[] => (Array.isArray(v) ? v : []);

/* ─── types ─── */
interface SubAnalytics {
  kpis?: any;
  distribution?: any;
  platform?: any;
  billing?: any;
  plan_catalog?: any[];
  trends?: any[];
  funnel?: any[];
}
interface PaymentOverview {
  active_subscribers?: number;
  total_revenue?: number;
  payment_count?: number;
  mrr?: number;
  arr?: number;
  arpu?: number;
  churn_rate?: number;
  stripe?: any;
  paypal?: any;
  revenue_by_currency?: any;
  revenue_by_country?: any;
  revenue_trend?: any[];
  new_subscribers?: number;
  canceled_subscribers?: number;
}
interface FinancialIntel {
  revenue_timeline?: any[];
  subscription_growth?: any;
  revenue_breakdown?: any;
  payment_methods?: any;
  summary?: any;
}
interface TrustFunnel {
  providers?: any[];
  totals?: any;
}
interface LlmOverview {
  kpi?: any;
  budget?: any;
  trend_14d?: any[];
  by_model?: any[];
  by_feature?: any[];
}
interface IapStats {
  active_apple_subscribers?: number;
  active_google_subscribers?: number;
  total_transactions?: number;
  estimated_mrr?: number;
  platform_breakdown?: any[];
  recent_transactions?: any[];
}

/* ─── KPI Card ─── */
const KpiCard = ({ label, value, sub, accent, colors, testId, icon }: {
  label: string; value: string; sub?: string; accent?: string;
  colors: any; testId: string; icon?: string;
}) => (
  <View
    style={{
      flex: 1, minWidth: 140, backgroundColor: colors.cardBg, borderRadius: 14,
      padding: 14, borderWidth: 1, borderColor: colors.border, gap: 4,
    }}
    data-testid={testId} testID={testId}
  >
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      {icon && <Ionicons name={icon as any} size={14} color={accent || colors.primary} />}
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{label}</Text>
    </View>
    <Text style={{ color: accent || colors.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.5 }}>{value}</Text>
    {sub ? <Text style={{ color: colors.textMuted, fontSize: 10 }}>{sub}</Text> : null}
  </View>
);

/* ─── Section Header ─── */
const SH = ({ title, icon, colors, testId }: { title: string; icon: string; colors: any; testId: string }) => (
  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }} data-testid={testId} testID={testId}>
    <Ionicons name={icon as any} size={16} color={colors.primary} />
    <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }}>{title}</Text>
  </View>
);

/* ─── Mini Bar Chart (CSS-only) ─── */
const MiniBar = ({ data, maxVal, color, colors }: { data: number[]; maxVal: number; color: string; colors: any }) => {
  const safe = data.length > 0 ? data : [0];
  const mx = maxVal > 0 ? maxVal : 1;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 48 }}>
      {safe.slice(-14).map((v, i) => (
        <View
          key={i}
          style={{
            flex: 1, minWidth: 4, maxWidth: 16,
            height: Math.max(2, (v / mx) * 48),
            backgroundColor: v > 0 ? color : `${colors.textMuted}22`,
            borderRadius: 3,
          }}
        />
      ))}
    </View>
  );
};

/* ─── Horizontal Funnel ─── */
const FunnelRow = ({ stages, colors }: { stages: { label: string; value: number; pct: number }[]; colors: any }) => {
  const safePct = (p: number) => (isNaN(p) || p <= 0 ? 0 : Math.min(p, 100));
  return (
    <View style={{ gap: 6 }}>
      {stages.map((s, i) => (
        <View key={i} style={{ gap: 2 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{s.label}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{fmtInt(s.value)} ({fmtPct(s.pct)})</Text>
          </View>
          <View style={{ height: 8, backgroundColor: `${colors.primary}15`, borderRadius: 4, overflow: 'hidden' }}>
            <View style={{ height: 8, width: `${safePct(s.pct)}%` as any, backgroundColor: colors.primary, borderRadius: 4 }} />
          </View>
        </View>
      ))}
    </View>
  );
};

/* ─── Provider Pill ─── */
const ProviderPill = ({ name, subs, mrr, txns, color, colors, testId }: {
  name: string; subs?: number; mrr?: number; txns?: number; color: string; colors: any; testId: string;
}) => (
  <View
    style={{
      flex: 1, minWidth: 140, backgroundColor: `${color}0A`, borderRadius: 12,
      padding: 12, borderWidth: 1, borderColor: `${color}25`, gap: 6,
    }}
    data-testid={testId} testID={testId}
  >
    <Text style={{ color, fontSize: 12, fontWeight: '800', textTransform: 'uppercase' }}>{name}</Text>
    {mrr != null && <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>{fmtUsd(mrr)}</Text>}
    <View style={{ flexDirection: 'row', gap: 10 }}>
      {subs != null && <Text style={{ color: colors.textMuted, fontSize: 10 }}>{fmtInt(subs)} subs</Text>}
      {txns != null && <Text style={{ color: colors.textMuted, fontSize: 10 }}>{fmtInt(txns)} txns</Text>}
    </View>
  </View>
);

/* ─── Transaction Row ─── */
const TxnRow = ({ txn, colors, idx }: { txn: any; colors: any; idx: number }) => {
  const amt = txn?.total_amount ?? txn?.amount ?? 0;
  const method = txn?.payment_method || txn?.provider || '--';
  const plan = txn?.plan_id || txn?.plan || '--';
  const status = txn?.status || '--';
  const date = txn?.created_at ? new Date(txn.created_at).toLocaleDateString() : '--';
  const statusColor = status === 'completed' || status === 'active' ? colors.successText : status === 'failed' ? colors.error : colors.textMuted;
  return (
    <View
      style={{
        flexDirection: 'row', alignItems: 'center', paddingVertical: 8,
        paddingHorizontal: 10, borderBottomWidth: 1, borderColor: colors.border,
        backgroundColor: idx % 2 === 0 ? 'transparent' : `${colors.textMuted}06`,
      }}
      data-testid={`txn-row-${idx}`} testID={`txn-row-${idx}`}
    >
      <Text style={{ flex: 2, color: colors.text, fontSize: 11, fontWeight: '600' }}>{date}</Text>
      <Text style={{ flex: 2, color: colors.text, fontSize: 11 }}>{method}</Text>
      <Text style={{ flex: 1.5, color: colors.text, fontSize: 11 }}>{plan}</Text>
      <Text style={{ flex: 1.5, color: colors.text, fontSize: 11, fontWeight: '700' }}>{fmtUsd(amt)}</Text>
      <View style={{ flex: 1 }}>
        <Text style={{ color: statusColor, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{status}</Text>
      </View>
    </View>
  );
};

/* ─── Main Component ─── */
export default function RevenueBillingEnterpriseWorkspace() {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const tx = useCallback((key: string, fb: string) => tx_(t, key, fb), [t]);

  const isMobile = width < 600;
  const isTablet = width >= 600 && width < 1024;

  /* ─── state ─── */
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<'7d' | '30d' | '90d'>('30d');
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const [subAnalytics, setSubAnalytics] = useState<SubAnalytics | null>(null);
  const [paymentOverview, setPaymentOverview] = useState<PaymentOverview | null>(null);
  const [financialIntel, setFinancialIntel] = useState<FinancialIntel | null>(null);
  const [trustFunnel, setTrustFunnel] = useState<TrustFunnel | null>(null);
  const [llmOverview, setLlmOverview] = useState<LlmOverview | null>(null);
  const [iapStats, setIapStats] = useState<IapStats | null>(null);
  const [recentTxns, setRecentTxns] = useState<any[]>([]);
  const [mobileMoneyOverview, setMobileMoneyOverview] = useState<any>(null);
  const [planCatalog, setPlanCatalog] = useState<any[]>([]);

  const autoRefreshRef = useRef<any>(null);

  /* ─── data loader ─── */
  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const [subRes, payRes, finRes, trustRes, llmRes, iapRes, txnRes, mmRes, planRes] = await Promise.allSettled([
        api.get(`/admin/subscription-analytics/overview?period=${period}`),
        api.get(`/admin/payment-analytics/subscriptions/overview?period=${period}`),
        api.get(`/admin/executive/financial-intelligence?period=${period}`),
        api.get('/admin/subscriptions/trust-funnel-analytics'),
        api.get('/admin/llm-billing/overview'),
        api.get('/iap/admin/stats'),
        api.get(`/admin/payment-analytics/recent-transactions?limit=15&period=${period}`),
        api.get(`/admin/payment-analytics/mobile-money/overview?period=${period}`),
        api.get('/subscriptions/plans'),
      ]);
      if (subRes.status === 'fulfilled') setSubAnalytics(subRes.value?.data || null);
      if (payRes.status === 'fulfilled') setPaymentOverview(payRes.value?.data || null);
      if (finRes.status === 'fulfilled') setFinancialIntel(finRes.value?.data || null);
      if (trustRes.status === 'fulfilled') setTrustFunnel(trustRes.value?.data || null);
      if (llmRes.status === 'fulfilled') setLlmOverview(llmRes.value?.data || null);
      if (iapRes.status === 'fulfilled') setIapStats(iapRes.value?.data || null);
      if (txnRes.status === 'fulfilled') setRecentTxns(safeArr(txnRes.value?.data?.transactions));
      if (mmRes.status === 'fulfilled') setMobileMoneyOverview(mmRes.value?.data || null);
      if (planRes.status === 'fulfilled') setPlanCatalog(safeArr(planRes.value?.data?.plans));
      setLastRefresh(new Date());
    } catch (e: any) {
      setError(e?.message || 'Failed to load revenue data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [period]);

  useEffect(() => { loadData(); }, [loadData]);

  /* auto-refresh 60s */
  useEffect(() => {
    autoRefreshRef.current = setInterval(() => loadData(true), 60000);
    return () => { if (autoRefreshRef.current) clearInterval(autoRefreshRef.current); };
  }, [loadData]);

  /* ─── derived ─── */
  const kpis = subAnalytics?.kpis || {};
  const dist = subAnalytics?.distribution || {};
  const plat = subAnalytics?.platform || {};
  const billing = subAnalytics?.billing || {};
  const trends = safeArr(subAnalytics?.trends);
  const funnel = safeArr(subAnalytics?.funnel);
  const revTimeline = safeArr(financialIntel?.revenue_timeline);
  const llmKpi = llmOverview?.kpi || {};
  const llmBudget = llmOverview?.budget || {};
  const llmTrend = safeArr(llmOverview?.trend_14d);
  const llmModels = safeArr(llmOverview?.by_model);
  const llmFeatures = safeArr(llmOverview?.by_feature);
  const trustProviders = safeArr(trustFunnel?.providers);
  const trustTotals = trustFunnel?.totals || {};
  const mmov = mobileMoneyOverview || {};

  const periodLabel = period === '7d' ? '7 Days' : period === '30d' ? '30 Days' : '90 Days';

  /* ─── styles ─── */
  const card = {
    backgroundColor: colors.cardBg, borderRadius: 16, padding: isMobile ? 14 : 18,
    borderWidth: 1, borderColor: colors.border, gap: 12,
  };
  const wrap = { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: isMobile ? 8 : 12 };

  /* ─── skeleton ─── */
  if (loading && !subAnalytics) {
    return (
      <View style={{ padding: 32, alignItems: 'center', gap: 16 }} data-testid="rev-billing-loading" testID="rev-billing-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, fontSize: 13 }}>{tx('revBilling.loading', 'Loading Revenue & Billing...')}</Text>
      </View>
    );
  }

  if (error && !subAnalytics) {
    return (
      <View style={{ padding: 32, alignItems: 'center', gap: 12 }} data-testid="rev-billing-error" testID="rev-billing-error">
        <Ionicons name="alert-circle" size={32} color={colors.error} />
        <Text style={{ color: colors.error, fontSize: 13, textAlign: 'center' }}>{error}</Text>
        <TouchableOpacity onPress={() => loadData()} style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.primary }} data-testid="rev-billing-retry-btn" testID="rev-billing-retry-btn">
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }} data-testid="rev-billing-workspace" testID="rev-billing-workspace">
      {/* ─── COMMAND HEADER ─── */}
      <View style={{ paddingHorizontal: isMobile ? 12 : 20, paddingTop: 16, paddingBottom: 12, gap: 10 }} data-testid="rev-billing-header" testID="rev-billing-header">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <View style={{ gap: 2 }}>
            <Text style={{ color: colors.text, fontSize: isMobile ? 18 : 22, fontWeight: '900', letterSpacing: -0.5 }}>
              {tx('revBilling.title', 'Revenue & Billing')}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>
              {tx('revBilling.subtitle', 'Executive Financial Intelligence Center')}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {lastRefresh && (
              <Text style={{ color: colors.textMuted, fontSize: 9 }} data-testid="rev-billing-last-updated" testID="rev-billing-last-updated">
                {lastRefresh.toLocaleTimeString()}
              </Text>
            )}
            <TouchableOpacity
              onPress={() => { setRefreshing(true); loadData(); }}
              style={{ padding: 6, borderRadius: 8, backgroundColor: `${colors.primary}12` }}
              data-testid="rev-billing-refresh-btn" testID="rev-billing-refresh-btn"
            >
              {refreshing ? <ActivityIndicator size="small" color={colors.primary} /> : <Ionicons name="refresh" size={16} color={colors.primary} />}
            </TouchableOpacity>
          </View>
        </View>
        {/* Period Pills */}
        <View style={{ flexDirection: 'row', gap: 6 }} data-testid="rev-billing-period-pills" testID="rev-billing-period-pills">
          {(['7d', '30d', '90d'] as const).map((p) => (
            <TouchableOpacity accessibilityLabel="Set period in revenue billing enterprise workspace button"
              key={p}
              onPress={() => setPeriod(p)}
              style={{
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
                backgroundColor: period === p ? colors.primary : `${colors.textMuted}12`,
              }}
              data-testid={`rev-billing-period-${p}`} testID={`rev-billing-period-${p}`}
            >
              <Text style={{ color: period === p ? 'var(--app-primary-text)' : colors.textMuted, fontSize: 11, fontWeight: '700' }}>
                {p === '7d' ? '7D' : p === '30d' ? '30D' : '90D'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: isMobile ? 12 : 20, paddingBottom: 40, gap: isMobile ? 16 : 20 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadData(); }} tintColor={colors.primary} />}
      >
        {/* ─── 1. REVENUE KPI STRIP ─── */}
        <View data-testid="rev-kpi-section" testID="rev-kpi-section">
          <SH title={tx('revBilling.kpiTitle', `Key Metrics \u00b7 ${periodLabel}`)} icon="stats-chart" colors={colors} testId="rev-kpi-header" />
          <View style={wrap}>
            <KpiCard label="MRR" value={fmtUsd(kpis.mrr)} icon="trending-up" accent={colors.successText} colors={colors} testId="kpi-mrr" />
            <KpiCard label="ARR" value={fmtUsd(kpis.arr)} icon="cash" accent={colors.primary} colors={colors} testId="kpi-arr" />
            <KpiCard label="Active Subs" value={fmtInt(kpis.active_subs)} icon="people" colors={colors} testId="kpi-active-subs" />
            <KpiCard label="New Subs" value={fmtInt(kpis.new_subs)} sub={`${periodLabel}`} icon="add-circle" accent={colors.accent} colors={colors} testId="kpi-new-subs" />
          </View>
          <View style={{ ...wrap, marginTop: isMobile ? 8 : 12 }}>
            <KpiCard label="ARPU" value={fmtUsd(kpis.arpu)} icon="person" colors={colors} testId="kpi-arpu" />
            <KpiCard label="LTV" value={fmtUsd(kpis.ltv)} icon="diamond" accent={colors.successText} colors={colors} testId="kpi-ltv" />
            <KpiCard label="Churn Rate" value={fmtPct(kpis.churn_rate)} icon="arrow-down-circle" accent={kpis.churn_rate > 5 ? colors.error : colors.successText} colors={colors} testId="kpi-churn" />
            <KpiCard label="Conversion" value={fmtPct(kpis.conversion_rate)} sub={`of ${fmtInt(kpis.total_users)} users`} icon="funnel" accent={colors.primary} colors={colors} testId="kpi-conversion" />
            <KpiCard
              label="Online Users (Live)"
              value={fmtInt(kpis.online_users_live)}
              sub="active sessions now"
              icon="pulse"
              accent={colors.accent}
              colors={colors}
              testId="kpi-online-users-live"
            />
          </View>
        </View>

        {/* ─── 2. REVENUE TREND ─── */}
        {revTimeline.length > 0 && (
          <View style={card} data-testid="rev-trend-section" testID="rev-trend-section">
            <SH title={tx('revBilling.revTrend', 'Revenue Trend')} icon="bar-chart" colors={colors} testId="rev-trend-header" />
            <MiniBar
              data={revTimeline.map((d) => d?.revenue ?? 0)}
              maxVal={Math.max(...revTimeline.map((d) => d?.revenue ?? 0), 1)}
              color={colors.primary}
              colors={colors}
            />
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: colors.textMuted, fontSize: 9 }}>{revTimeline[0]?.date || ''}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 9 }}>{revTimeline[revTimeline.length - 1]?.date || ''}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
              {(() => {
                const total = revTimeline.reduce((s, d) => s + (d?.revenue ?? 0), 0);
                const avg = revTimeline.length > 0 ? total / revTimeline.length : 0;
                const peak = Math.max(...revTimeline.map((d) => d?.revenue ?? 0));
                return (
                  <>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>Total: <Text style={{ color: colors.text, fontWeight: '700' }}>{fmtUsd(total)}</Text></Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>Avg/Day: <Text style={{ color: colors.text, fontWeight: '700' }}>{fmtUsd(avg)}</Text></Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>Peak: <Text style={{ color: colors.text, fontWeight: '700' }}>{fmtUsd(peak)}</Text></Text>
                  </>
                );
              })()}
            </View>
          </View>
        )}

        {/* ─── 3. PROVIDER BREAKDOWN ─── */}
        <View style={card} data-testid="rev-providers-section" testID="rev-providers-section">
          <SH title={tx('revBilling.providers', 'Payment Provider Breakdown')} icon="card" colors={colors} testId="rev-providers-header" />
          <View style={wrap}>
            <ProviderPill name="Stripe" subs={plat.stripe?.subs} mrr={plat.stripe?.mrr} color="var(--app-primary)" colors={colors} testId="provider-stripe" />
            <ProviderPill name="Apple IAP" subs={plat.apple?.subs} mrr={plat.apple?.mrr} txns={plat.apple?.txns} color="var(--app-primary)" colors={colors} testId="provider-apple" />
            <ProviderPill name="Google Play" subs={plat.google?.subs} mrr={plat.google?.mrr} txns={plat.google?.txns} color="var(--app-success)" colors={colors} testId="provider-google" />
            <ProviderPill
              name="FedaPay"
              subs={mmov.active_subscribers}
              mrr={mmov.total_revenue}
              txns={mmov.total_payments}
              color="var(--app-warning)"
              colors={colors}
              testId="provider-fedapay"
            />
            {paymentOverview?.paypal && (paymentOverview.paypal.count > 0 || paymentOverview.paypal.revenue > 0) && (
              <ProviderPill name="PayPal" mrr={paymentOverview.paypal.revenue} txns={paymentOverview.paypal.count} color="var(--app-primary)" colors={colors} testId="provider-paypal" />
            )}
          </View>
          {plat.iap_txns_period != null && (
            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }}>
              IAP transactions this period: <Text style={{ fontWeight: '700', color: colors.text }}>{fmtInt(plat.iap_txns_period)}</Text>
            </Text>
          )}
        </View>

        {/* ─── 4. SUBSCRIPTION DISTRIBUTION + BILLING ─── */}
        <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: isMobile ? 16 : 20 }}>
          {/* Distribution */}
          <View style={{ ...card, flex: 1 }} data-testid="rev-distribution-section" testID="rev-distribution-section">
            <SH title={tx('revBilling.planDist', 'Plan Distribution')} icon="pie-chart" colors={colors} testId="rev-distribution-header" />
            {Object.keys(dist).length > 0 ? (
              <View style={{ gap: 8 }}>
                {Object.entries(dist).map(([plan, count]) => {
                  const total = Object.values(dist).reduce((s: number, v: any) => s + Number(v || 0), 0);
                  const pct = total > 0 ? (Number(count) / total) * 100 : 0;
                  const planColor = plan === 'premium' ? colors.primary : plan === 'basic' ? colors.accent : colors.textMuted;
                  return (
                    <View key={plan} style={{ gap: 2 }} data-testid={`dist-plan-${plan}`} testID={`dist-plan-${plan}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{plan}</Text>
                        <Text style={{ color: colors.textMuted, fontSize: 11 }}>{fmtInt(count as number)} ({fmtPct(pct)})</Text>
                      </View>
                      <View style={{ height: 6, backgroundColor: `${planColor}15`, borderRadius: 3, overflow: 'hidden' }}>
                        <View style={{ height: 6, width: `${pct}%` as any, backgroundColor: planColor, borderRadius: 3 }} />
                      </View>
                    </View>
                  );
                })}
              </View>
            ) : (
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('revBilling.noDistData', 'No distribution data available')}</Text>
            )}
          </View>

          {/* Billing Cycle */}
          <View style={{ ...card, flex: 1 }} data-testid="rev-billing-cycle-section" testID="rev-billing-cycle-section">
            <SH title={tx('revBilling.billingCycle', 'Billing Cycle')} icon="calendar" colors={colors} testId="rev-billing-cycle-header" />
            <View style={{ gap: 8 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>Monthly</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>{fmtInt(billing.monthly)} ({fmtPct(billing.monthly_pct)})</Text>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>Yearly</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>{fmtInt(billing.yearly)} ({fmtPct(billing.yearly_pct)})</Text>
              </View>
            </View>
            {/* Trust Funnel */}
            {trustProviders.length > 0 && (
              <View style={{ marginTop: 8, gap: 6 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('revBilling.trustFunnel', 'Checkout Trust Funnel')}</Text>
                {trustProviders.filter(p => p.provider !== 'all').map((p, i) => (
                  <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }} data-testid={`trust-funnel-${p.provider}`} testID={`trust-funnel-${p.provider}`}>
                    <Text style={{ color: colors.text, fontSize: 11, textTransform: 'capitalize' }}>{p.provider}</Text>
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>Opens: {fmtInt(p.open_count)}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>Clicks: {fmtInt(p.conversion_click_count)}</Text>
                      <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>{fmtPct(p.conversion_rate_pct)}</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}
          </View>
        </View>

        {/* ─── 5. MRR GROWTH TREND ─── */}
        {trends.length > 0 && (
          <View style={card} data-testid="rev-mrr-trend-section" testID="rev-mrr-trend-section">
            <SH title={tx('revBilling.mrrTrend', 'MRR Growth Trend')} icon="trending-up" colors={colors} testId="rev-mrr-trend-header" />
            <MiniBar
              data={trends.map((t) => t?.mrr ?? 0)}
              maxVal={Math.max(...trends.map((t) => t?.mrr ?? 0), 1)}
              color={colors.successText}
              colors={colors}
            />
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: colors.textMuted, fontSize: 9 }}>{trends[0]?.month || ''}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 9 }}>{trends[trends.length - 1]?.month || ''}</Text>
            </View>
            {/* Monthly details */}
            <View style={{ gap: 4, marginTop: 4 }}>
              {trends.map((tr, i) => (
                <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 }}>
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '600' }}>{tr.month}</Text>
                  <View style={{ flexDirection: 'row', gap: 10 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>MRR: {fmtUsd(tr.mrr)}</Text>
                    <Text style={{ color: colors.successText, fontSize: 10 }}>+{fmtInt(tr.new_subs)} new</Text>
                    {tr.churned > 0 && <Text style={{ color: colors.error, fontSize: 10 }}>-{fmtInt(tr.churned)} churn</Text>}
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* ─── 6. SUBSCRIPTION FUNNEL ─── */}
        {funnel.length > 0 && (
          <View style={card} data-testid="rev-funnel-section" testID="rev-funnel-section">
            <SH title={tx('revBilling.subFunnel', 'Subscription Funnel')} icon="funnel" colors={colors} testId="rev-funnel-header" />
            <FunnelRow
              stages={funnel.map((f) => ({ label: f.stage, value: f.count, pct: Math.min(f.pct, 100) }))}
              colors={colors}
            />
          </View>
        )}

        {/* ─── 7. LLM COST INTELLIGENCE ─── */}
        {llmOverview && (
          <View style={card} data-testid="rev-llm-section" testID="rev-llm-section">
            <SH title={tx('revBilling.llmCost', 'LLM Cost Intelligence')} icon="flash" colors={colors} testId="rev-llm-header" />
            <View style={wrap}>
              <KpiCard label="Today" value={fmtUsd(llmKpi.today?.cost)} sub={`${fmtInt(llmKpi.today?.calls)} calls`} icon="today" colors={colors} testId="llm-kpi-today" />
              <KpiCard label="MTD" value={fmtUsd(llmKpi.mtd?.cost)} sub={`${fmtInt(llmKpi.mtd?.calls)} calls`} icon="calendar" colors={colors} testId="llm-kpi-mtd" />
              <KpiCard label="Last 30D" value={fmtUsd(llmKpi.last_30d?.cost)} sub={`${fmtInt(llmKpi.last_30d?.calls)} calls`} icon="time" colors={colors} testId="llm-kpi-30d" />
              <KpiCard
                label="Budget"
                value={fmtUsd(llmBudget.mtd_cost_usd)}
                sub={`of ${fmtUsd(llmBudget.monthly_budget_usd)} (${fmtPct(llmBudget.burn_pct)})`}
                icon="wallet"
                accent={llmBudget.over_budget ? colors.error : colors.successText}
                colors={colors}
                testId="llm-kpi-budget"
              />
            </View>
            {/* 14-day trend */}
            {llmTrend.length > 0 && (
              <View style={{ marginTop: 8 }}>
                <Text style={{ color: colors.textMuted, fontSize: 10, marginBottom: 4 }}>14-Day Cost Trend</Text>
                <MiniBar data={llmTrend.map((d) => d?.cost ?? 0)} maxVal={Math.max(...llmTrend.map((d) => d?.cost ?? 0), 0.01)} color="var(--app-warning)" colors={colors} />
              </View>
            )}
            {/* By model */}
            {llmModels.length > 0 && (
              <View style={{ marginTop: 8, gap: 4 }}>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>Cost by Model</Text>
                {llmModels.slice(0, 5).map((m, i) => (
                  <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 2 }} data-testid={`llm-model-${i}`} testID={`llm-model-${i}`}>
                    <Text style={{ color: colors.text, fontSize: 11 }}>{m.model}</Text>
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{fmtUsd(m.cost)}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{fmtInt(m.calls)} calls</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}
            {/* By feature */}
            {llmFeatures.length > 0 && (
              <View style={{ marginTop: 8, gap: 4 }}>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>Cost by Feature</Text>
                {llmFeatures.slice(0, 5).map((f, i) => (
                  <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 2 }} data-testid={`llm-feature-${i}`} testID={`llm-feature-${i}`}>
                    <Text style={{ color: colors.text, fontSize: 11 }}>{f.feature}</Text>
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{fmtUsd(f.cost)}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* ─── 8. IAP INTELLIGENCE ─── */}
        {iapStats && (
          <View style={card} data-testid="rev-iap-section" testID="rev-iap-section">
            <SH title={tx('revBilling.iap', 'In-App Purchase Intelligence')} icon="phone-portrait" colors={colors} testId="rev-iap-header" />
            <View style={wrap}>
              <KpiCard label="Apple Subs" value={fmtInt(iapStats.active_apple_subscribers)} icon="logo-apple" colors={colors} testId="iap-apple-subs" />
              <KpiCard label="Google Subs" value={fmtInt(iapStats.active_google_subscribers)} icon="logo-google-playstore" colors={colors} testId="iap-google-subs" />
              <KpiCard label="Total Txns" value={fmtInt(iapStats.total_transactions)} icon="receipt" colors={colors} testId="iap-total-txns" />
              <KpiCard label="Est. MRR" value={fmtUsd(iapStats.estimated_mrr)} icon="trending-up" accent={colors.successText} colors={colors} testId="iap-est-mrr" />
            </View>
            {safeArr(iapStats.platform_breakdown).length > 0 && (
              <View style={{ marginTop: 4, gap: 4 }}>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>Platform Breakdown</Text>
                {safeArr(iapStats.platform_breakdown).map((pb, i) => (
                  <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 2 }}>
                    <Text style={{ color: colors.text, fontSize: 11, textTransform: 'capitalize' }}>{pb.platform} - {pb.plan}</Text>
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{fmtInt(pb.count)} subs</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* ─── 9. REVENUE BY CURRENCY ─── */}
        {paymentOverview?.revenue_by_currency && Object.keys(paymentOverview.revenue_by_currency).length > 0 && (
          <View style={card} data-testid="rev-currency-section" testID="rev-currency-section">
            <SH title={tx('revBilling.byCurrency', 'Revenue by Currency')} icon="globe" colors={colors} testId="rev-currency-header" />
            <View style={{ gap: 4 }}>
              {Object.entries(paymentOverview.revenue_by_currency).map(([cur, data]: [string, any], i) => (
                <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' }}>{cur}</Text>
                  <View style={{ flexDirection: 'row', gap: 10 }}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{fmtUsd(data?.revenue)}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11 }}>{fmtInt(data?.count)} txns</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* ─── 10. PLAN CATALOG ─── */}
        {planCatalog.length > 0 && (
          <View style={card} data-testid="rev-plans-section" testID="rev-plans-section">
            <SH title={tx('revBilling.planCatalog', 'Plan Catalog')} icon="pricetags" colors={colors} testId="rev-plans-header" />
            <View style={wrap}>
              {planCatalog.map((plan, i) => {
                const planColor = plan.plan_id === 'premium' ? colors.primary : plan.plan_id === 'basic' ? colors.accent : colors.textMuted;
                return (
                  <View
                    key={i}
                    style={{
                      flex: 1, minWidth: 160, backgroundColor: `${planColor}08`, borderRadius: 12,
                      padding: 12, borderWidth: 1, borderColor: `${planColor}20`, gap: 6,
                    }}
                    data-testid={`plan-card-${plan.plan_id}`} testID={`plan-card-${plan.plan_id}`}
                  >
                    <Text style={{ color: planColor, fontSize: 13, fontWeight: '900', textTransform: 'uppercase' }}>{plan.name}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4 }}>
                      <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }}>${fmt(plan.monthly_price)}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>/mo</Text>
                    </View>
                    {plan.yearly_price > 0 && (
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                        Yearly: ${fmt(plan.yearly_price)} ({fmtPct(plan.yearly_discount_pct)} off)
                      </Text>
                    )}
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{plan.description}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        )}

        {/* ─── 11. RECENT TRANSACTIONS TABLE ─── */}
        <View style={card} data-testid="rev-txns-section" testID="rev-txns-section">
          <SH title={tx('revBilling.recentTxns', 'Recent Transactions')} icon="list" colors={colors} testId="rev-txns-header" />
          {recentTxns.length > 0 ? (
            <View>
              {/* Header */}
              <View style={{ flexDirection: 'row', paddingVertical: 6, paddingHorizontal: 10, borderBottomWidth: 2, borderColor: colors.border }}>
                <Text style={{ flex: 2, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Date</Text>
                <Text style={{ flex: 2, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Method</Text>
                <Text style={{ flex: 1.5, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Plan</Text>
                <Text style={{ flex: 1.5, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Amount</Text>
                <Text style={{ flex: 1, color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>Status</Text>
              </View>
              {recentTxns.slice(0, 10).map((txn, i) => (
                <TxnRow key={i} txn={txn} colors={colors} idx={i} />
              ))}
              {recentTxns.length > 10 && (
                <Text style={{ color: colors.textMuted, fontSize: 10, textAlign: 'center', marginTop: 6 }}>
                  Showing 10 of {recentTxns.length} transactions
                </Text>
              )}
            </View>
          ) : (
            <Text style={{ color: colors.textMuted, fontSize: 11, textAlign: 'center', paddingVertical: 16 }} data-testid="rev-txns-empty" testID="rev-txns-empty">
              {tx('revBilling.noTxns', 'No recent transactions in this period')}
            </Text>
          )}
        </View>

        {/* ─── 12. PAYMENT OVERVIEW REVENUE TREND ─── */}
        {safeArr(paymentOverview?.revenue_trend).filter(d => d?.revenue > 0).length > 0 && (
          <View style={card} data-testid="rev-daily-trend-section" testID="rev-daily-trend-section">
            <SH title={tx('revBilling.dailyRevTrend', 'Daily Revenue Trend (Payments)')} icon="analytics" colors={colors} testId="rev-daily-trend-header" />
            <MiniBar
              data={safeArr(paymentOverview?.revenue_trend).map((d) => d?.revenue ?? 0)}
              maxVal={Math.max(...safeArr(paymentOverview?.revenue_trend).map((d) => d?.revenue ?? 0), 1)}
              color={colors.accent}
              colors={colors}
            />
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: colors.textMuted, fontSize: 9 }}>{safeArr(paymentOverview?.revenue_trend)[0]?.date || ''}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 9 }}>{safeArr(paymentOverview?.revenue_trend).slice(-1)[0]?.date || ''}</Text>
            </View>
          </View>
        )}

      </ScrollView>
    </View>
  );
}
