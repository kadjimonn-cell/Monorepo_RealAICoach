import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import api from '../../src/services/api';
import { useAutoRefresh } from '../../src/hooks/useAutoRefresh';
import { ExecutiveDashboardSkeleton } from '../../src/components/SkeletonLoaders';
import Svg, { Rect, Text as SvgText, Line, Circle } from 'react-native-svg';
import GeoHeatmap from '../../src/components/admin/GeoHeatmap';
import { HeartbeatPulse } from '../../src/components/common/HeartbeatPulse';

import { useAdminTheme } from '../../src/hooks/useAdminTheme';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
const _V = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  cardMuted: 'var(--app-card-muted)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  success: 'var(--app-success)' as any,
  warning: 'var(--app-warning)' as any,
  error: 'var(--app-error)' as any,
  purple: 'var(--app-info)' as any,
};
const DARK = {
  bg: _V.bg, card: _V.card, cardAlt: _V.cardMuted, border: _V.border,
  text: _V.text, textSec: _V.textSec, textMuted: _V.textMuted,
  primary: _V.primary, success: _V.success, warning: _V.warning, error: _V.error,
  momo: 'var(--app-primary)', fedapay: 'var(--app-primary)', accent: _V.purple,
};
const LIGHT = {
  bg: _V.bg, card: _V.card, cardAlt: _V.cardMuted, border: _V.border,
  text: _V.text, textSec: _V.textSec, textMuted: _V.textMuted,
  primary: _V.primary, success: _V.success, warning: _V.warning, error: _V.error,
  momo: 'var(--app-primary)', fedapay: 'var(--app-primary)', accent: _V.purple,
};

const KpiCard = ({ label, value, icon, color, sub }: any) => (
  <View style={[s.kpi, { borderLeftColor: color }]} data-testid={`mm-kpi-${label.toLowerCase().replace(/\s/g,'-')}`} testID={`mm-kpi-${label.toLowerCase().replace(/\s/g,'-')}`}>
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
      <View style={[s.kpiIcon, { backgroundColor: (globalThis as any).__alphaColor(color, '18') }]}>
        <Ionicons name={icon} size={18} color={color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={s.kpiLabel}>{label}</Text>
        <Text style={[s.kpiValue, { color }]}>{value}</Text>
        {sub && <Text style={s.kpiSub}>{sub}</Text>}
      </View>
    </View>
  </View>
);

const BarChart = ({ data, height = 180, color = DARK.success }: any) => {
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  if (!data?.length) return <Text style={{ color: DARK.textMuted, textAlign: 'center', padding: 20 }}>{t("admin.subscriptionDashboard.states.noData")}</Text>;
  const cw = Math.min(width - 80, 700);
  const max = Math.max(...data.map((d: any) => d.revenue), 1);
  const barW = Math.max(4, (cw - 40) / data.length - 2);
  return (
    <View style={{ alignItems: 'center' }}>
      <Svg width={cw} height={height + 30}>
        <Line x1="30" y1="0" x2="30" y2={height} stroke={DARK.border} strokeWidth="1" />
        <Line x1="30" y1={height} x2={cw} y2={height} stroke={DARK.border} strokeWidth="1" />
        {data.map((d: any, i: number) => {
          const h = (d.revenue / max) * (height - 20);
          const x = 35 + i * ((cw - 40) / data.length);
          return (
            <React.Fragment key={i}>
              <Rect x={x} y={height - h} width={barW} height={h} rx={2} fill={color} opacity={0.85} />
              {i % Math.ceil(data.length / 6) === 0 && (
                <SvgText x={x + barW / 2} y={height + 14} fill={DARK.textMuted} fontSize="9" textAnchor="middle">{d.date?.slice(5)}</SvgText>
              )}
            </React.Fragment>
          );
        })}
        <SvgText x={15} y={12} fill={DARK.textMuted} fontSize="9" textAnchor="middle">${max.toFixed(0)}</SvgText>
      </Svg>
    </View>
  );
};

const PeriodSelector = ({ period, setPeriod }: any) => (
  <View style={{ flexDirection: 'row', gap: 6 }} data-testid="mm-period-selector" testID="mm-period-selector">
    {['7d', '30d', '90d', '1y'].map(p => (
      <TouchableOpacity key={p} onPress={() => setPeriod(p)}
        style={[s.periodBtn, period === p && s.periodActive]} data-testid={`mm-period-${p}`} testID={`mm-period-${p}`}>
        <Text style={[s.periodText, period === p && s.periodActiveText]}>{p}</Text>
      </TouchableOpacity>
    ))}
  </View>
);

const SuccessRateGauge = ({ rate }: { rate: number }) => {
  const { t } = useTranslation();
  const size = 120;
  const r = 45;
  const circumference = 2 * Math.PI * r;
  const filled = (rate / 100) * circumference;
  const color = rate > 80 ? DARK.success : rate > 50 ? DARK.warning : DARK.error;
  return (
    <View style={{ alignItems: 'center' }}>
      <Svg width={size} height={size}>
        <Circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={DARK.border} strokeWidth="8" />
        <Circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={`${filled} ${circumference}`} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        <SvgText x={size / 2} y={size / 2 - 4} fill={DARK.text} fontSize="20" fontWeight="bold" textAnchor="middle">{rate}%</SvgText>
        <SvgText x={size / 2} y={size / 2 + 14} fill={DARK.textMuted} fontSize="10" textAnchor="middle">{t("autofix.watchSweep1.success")}</SvgText>
      </Svg>
    </View>
  );
};

export default function MobileMoneyDashboard() {
  const { t } = useTranslation();
  t('i18n.route.admin.mobile-money-dashboard.probe');
  const _AC = useAdminTheme();
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  const [txns, setTxns] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState('30d');
  const [dashboardStatusCheckedAt, setDashboardStatusCheckedAt] = useState(Date.now());
  const [dashboardStatusHeartbeatSec, setDashboardStatusHeartbeatSec] = useState(0);
  const [txnPage, setTxnPage] = useState(1);
  const [txnTotal, setTxnTotal] = useState(0);
  const [txnPages, setTxnPages] = useState(1);
  const [tab, setTab] = useState<'overview' | 'transactions'>('overview');
  const [filterProvider, setFilterProvider] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [fedapayTimeline, setFedapayTimeline] = useState<any[]>([]);
  const [fedapaySourceEvents, setFedapaySourceEvents] = useState<any[]>([]);
  const [recoverableError, setRecoverableError] = useState('');
  const [isDark, setIsDark] = useState(true);
  const {darkMode: globalDark, _colors} = useTheme();
  useEffect(() => { setIsDark(globalDark); }, [globalDark]);
  const T = isDark ? DARK : LIGHT;
  const { width } = useWindowDimensions();
  const isWide = width > 768;
  const isCompact = width < 900;
  const transactionTableMinWidth = isWide ? 780 : Math.max(560, width - 28);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [overview, txnList] = await Promise.all([
        api.get(`/admin/payment-analytics/mobile-money/overview?period=${period}`),
        api.get(`/admin/payment-analytics/mobile-money/transactions?page=${txnPage}&provider=${filterProvider}&status=${filterStatus}`),
      ]);
      if (overview.data) setData(overview.data);
      if (txnList.data) {
        setTxns(txnList.data.transactions || []);
        setTxnTotal(txnList.data.total || 0);
        setTxnPages(txnList.data.pages || 1);
      }
      try {
        const timeline = await api.get('/admin/payment-analytics/fedapay-policy/timeline?page=1&limit=20');
        if (timeline?.data) {
          setFedapayTimeline(timeline.data.history || []);
          setFedapaySourceEvents(timeline.data.source_events || []);
        }
      } catch (error) { handleAppRecoverableError({ scope: 'admin/mobile-money-dashboard.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      setRecoverableError('');
    } catch (e) {
      handleAppRecoverableError({
        scope: 'admin.mobile-money.load-data',
        error: e,
        message: 'Could not load mobile money analytics right now.',
        setError: setRecoverableError,
        onRetry: () => { void loadData(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    setLoading(false);
    setDashboardStatusCheckedAt(Date.now());
  }, [period, txnPage, filterProvider, filterStatus]);

  useEffect(() => {
    if (!user?.is_admin) {
      setLoading(false);
      return;
    }
    loadData();
  }, [loadData, user?.is_admin]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      setDashboardStatusHeartbeatSec(Math.max(0, Math.floor((Date.now() - dashboardStatusCheckedAt) / 1000)));
    }, 1000);
    return () => clearInterval(intervalId);
  }, [dashboardStatusCheckedAt]);

  // 30-second auto-refresh for real-time data
  useAutoRefresh(loadData, { intervalMs: 30000 });

  const handleExport = async () => {
    try {
      const res = await api.get(`/admin/payment-analytics/mobile-money/export?period=${period}`);
      if (res.data?.csv_data) {
        const blob = new Blob([res.data.csv_data], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `mobile_money_${period}.csv`; a.click();
      }
    } catch (e) {
      handleAppRecoverableError({
        scope: 'admin.mobile-money.export',
        error: e,
        message: 'Could not export mobile money report.',
        setError: setRecoverableError,
        onRetry: () => { void handleExport(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  };

  if (loading && !data) return (
    <ExecutiveDashboardSkeleton />
  );

  const fmt = (n: number) => n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n.toFixed(2)}`;

  return (
    <ScrollView
      style={[s.container, { backgroundColor: T.bg }]}
      contentContainerStyle={{ width: '100%', maxWidth: 1440, alignSelf: 'center' }}
      data-testid="mobile-money-dashboard"
      testID="mobile-money-dashboard"
    >
      {recoverableError ? (
        <View
          style={{ marginHorizontal: 20, marginTop: 12, marginBottom: 10, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: T.negative + '35', backgroundColor: T.card, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
          data-testid="mobile-money-recoverable-error-banner"
          testID="mobile-money-recoverable-error-banner"
        >
          <Text style={{ color: T.negative, fontSize: 12, fontWeight: '700', flex: 1 }} data-testid="mobile-money-recoverable-error-text" testID="mobile-money-recoverable-error-text">{recoverableError}</Text>
          <TouchableOpacity
            onPress={() => { void loadData(); }}
            style={{ backgroundColor: T.negative, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}
            data-testid="mobile-money-recoverable-error-retry"
            testID="mobile-money-recoverable-error-retry"
          >
            <Text style={{ color: T.primaryText, fontSize: 11, fontWeight: '800' }}>{t('common.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      ) : null}
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.title}>{t("autofix.watchSweep1.mobile.money.analytics")}</Text>
          <Text style={s.subtitle}>{t("autofix.watchSweep1.mobile.money.revenue.dashboard")}</Text>
          <HeartbeatPulse
            tick={dashboardStatusHeartbeatSec}
            warningAfterSeconds={60}
            criticalAfterSeconds={120}
            dataTestId="mm-dashboard-heartbeat"
            testID="mm-dashboard-heartbeat"
            style={{ marginTop: 4 }}
          >
            <Text style={[s.subtitle, { fontSize: 11 }]}>{dashboardStatusHeartbeatSec >= 120 ? 'Critical stale' : dashboardStatusHeartbeatSec >= 60 ? 'Stale' : 'Last checked'} {dashboardStatusHeartbeatSec}{t("autofix.watchSweep1.s.ago")}</Text>
          </HeartbeatPulse>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap', justifyContent: isCompact ? 'flex-start' : 'flex-end' }}>
          <PeriodSelector period={period} setPeriod={setPeriod} />
          <TouchableOpacity onPress={handleExport} style={[s.exportBtn, { backgroundColor: T.cardAlt, borderColor: T.border }]} data-testid="mm-export-btn" testID="mm-export-btn">
            <Ionicons name="download-outline" size={16} color={T.text} />
            <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{t("admin.gdpr.action.export")}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setIsDark(!isDark)} style={[s.exportBtn, { backgroundColor: T.cardAlt, borderColor: T.border }]} data-testid="mm-theme-toggle" testID="mm-theme-toggle">
            <Ionicons name={isDark ? 'sunny-outline' : 'moon-outline'} size={16} color={T.text} />
          </TouchableOpacity>
        </View>
      </View>

      {/* KPI Row */}
      <View style={[s.grid, isWide && { flexDirection: 'row' }]}>
        <KpiCard label="Total Revenue" value={fmt(data?.total_revenue ?? 0)} icon="cash" color={T.successText} sub={`${data?.payment_count ?? 0} payments`} />
        <KpiCard label="Active Subs" value={data?.active_subscribers ?? 0} icon="people" color={T.accent} sub={`${data?.new_subscribers ?? 0} new`} />
        <KpiCard label="Success Rate" value={`${data?.success_rate ?? 0}%`} icon="checkmark-circle" color={T.successText} sub={`${data?.failed_payments ?? 0} failed`} />
        <KpiCard label="Growth" value={`${data?.growth_rate > 0 ? '+' : ''}${data?.growth_rate ?? 0}%`} icon="trending-up" color={data?.growth_rate >= 0 ? T.success : T.error} sub="vs previous period" />
      </View>

      {/* Tab Switcher */}
      <View style={{ flexDirection: 'row', gap: 0, marginTop: 20 }}>
        {(['overview', 'transactions'] as const).map(t => (
          <TouchableOpacity key={t} onPress={() => setTab(t)}
            style={[s.tab, tab === t && s.tabActive]} data-testid={`mm-tab-${t}`} testID={`mm-tab-${t}`}>
            <Text style={[s.tabText, tab === t && s.tabActiveText]}>
              {t === 'overview' ? 'Analytics Overview' : 'Transaction Log'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'overview' && (
        <>
          {/* Revenue Trend */}
          <View style={s.panel}>
            <Text style={s.panelTitle}>{t("autofix.watchSweep1.daily.revenue.trend")}</Text>
            <BarChart data={data?.revenue_trend} color={T.momo} />
          </View>

          {/* Gateway Distribution + Success Rate */}
          <View style={[s.row, isWide && { flexDirection: 'row' }]}>
            <View style={[s.panel, { flex: 1 }]}>
              <Text style={s.panelTitle}>{t("autofix.watchSweep1.gateway.distribution")}</Text>
              <View style={{ gap: 16, padding: 8 }}>
                {/* Mobile Money */}
                <View style={{ gap: 6 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <View style={[s.gwDot, { backgroundColor: T.momo }]} />
                      <Text style={{ color: T.text, fontWeight: '700', fontSize: 14 }}>{t("autofix.watchSweep1.mobile.money")}</Text>
                    </View>
                    <Text style={{ color: T.successText, fontFamily: 'monospace', fontSize: 14 }}>${(data?.momo?.revenue ?? 0).toLocaleString()}</Text>
                  </View>
                  <View style={s.barBg}>
                    <View style={[s.barFill, { width: `${Math.min(100, ((data?.momo?.revenue ?? 0) / Math.max(data?.total_revenue ?? 1, 1)) * 100)}%`, backgroundColor: T.momo }]} />
                  </View>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>{data?.momo?.count ?? 0}{t("autofix.watchSweep1.transactions")}</Text>
                </View>

                {/* FedaPay */}
                <View style={{ gap: 6 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <View style={[s.gwDot, { backgroundColor: T.fedapay }]} />
                      <Text style={{ color: T.text, fontWeight: '700', fontSize: 14 }}>{t("mobileMoney.methods.mobileMoney")}</Text>
                    </View>
                    <Text style={{ color: T.successText, fontFamily: 'monospace', fontSize: 14 }}>${(data?.fedapay?.revenue ?? 0).toLocaleString()}</Text>
                  </View>
                  <View style={s.barBg}>
                    <View style={[s.barFill, { width: `${Math.min(100, ((data?.fedapay?.revenue ?? 0) / Math.max(data?.total_revenue ?? 1, 1)) * 100)}%`, backgroundColor: T.fedapay }]} />
                  </View>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>{data?.fedapay?.count ?? 0}{t("autofix.watchSweep1.transactions")}</Text>
                </View>
              </View>
            </View>

            <View style={[s.panel, { flex: 1, alignItems: 'center', justifyContent: 'center' }]}>
              <Text style={[s.panelTitle, { alignSelf: 'flex-start' }]}>{t("autofix.watchSweep1.transaction.health")}</Text>
              <SuccessRateGauge rate={data?.success_rate ?? 0} />
              <View style={{ flexDirection: 'row', gap: 20, marginTop: 16 }}>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ color: T.successText, fontSize: 20, fontWeight: '800', fontFamily: 'monospace' }}>{data?.success_payments ?? 0}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{t("autofix.watchSweep1.successful")}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ color: T.warningText, fontSize: 20, fontWeight: '800', fontFamily: 'monospace' }}>{data?.pending_payments ?? 0}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{t("admin.csat.automation.pending")}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ color: T.error, fontSize: 20, fontWeight: '800', fontFamily: 'monospace' }}>{data?.failed_payments ?? 0}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{t("otpDashboard.hourly.columns.failed")}</Text>
                </View>
              </View>
            </View>
          </View>

          {/* Geographic Revenue Heatmap */}
          <View style={{ marginTop: 16 }}>
            <GeoHeatmap
              revenueByCountry={data?.revenue_by_country ?? {}}
              accentColor={T.momo}
              title="Mobile Money Revenue by Region"
            />
          </View>

          {/* Revenue by Country */}
          {Object.keys(data?.revenue_by_country ?? {}).length > 0 && (
            <View style={s.panel}>
              <Text style={s.panelTitle}>{t("autofix.watchSweep1.revenue.by.country")}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {Object.entries(data.revenue_by_country).map(([country, info]: any) => (
                  <View key={country} style={s.countryBadge}>
                    <Text style={{ color: T.text, fontWeight: '700', fontSize: 14 }}>{country || 'N/A'}</Text>
                    <Text style={{ color: T.successText, fontSize: 12, fontFamily: 'monospace' }}>${info.revenue.toLocaleString()}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{info.count}{t("autofix.watchSweep1.txns")}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          <View style={s.panel} data-testid="fedapay-policy-timeline-panel" testID="fedapay-policy-timeline-panel">
            <Text style={s.panelTitle}>{t("autofix.watchSweep1.fedapay.fee.policy.timeline.audit")}</Text>
            {fedapayTimeline.length === 0 ? (
              <Text style={{ color: T.textMuted, fontSize: 12 }}>{t("autofix.watchSweep1.no.timeline.entries.yet")}</Text>
            ) : (
              <View style={{ gap: 8 }}>
                {fedapayTimeline.slice(0, 10).map((item, idx) => (
                  <View key={item.history_id || idx} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10 }} data-testid={`fedapay-policy-timeline-item-${idx}`} testID={`fedapay-policy-timeline-item-${idx}`}>
                    <Text style={{ color: T.text, fontWeight: '700', fontSize: 12 }}>
                      {item.source || 'unknown'} • {item.version || 'n/a'}
                    </Text>
                    <Text style={{ color: T.textSec, fontSize: 11, marginTop: 2 }}>
                      {item.created_at ? new Date(item.created_at).toLocaleString() : 'n/a'}
                    </Text>
                    <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{t("autofix.watchSweep1.countries")}{item?.change_summary?.country_added ?? 0}{t("autofix.watchSweep1.countries.2")}{item?.change_summary?.country_removed ?? 0}{t("autofix.watchSweep1.fee.updates")}{item?.change_summary?.fee_updates ?? 0}
                    </Text>
                  </View>
                ))}
              </View>
            )}

            <Text style={[s.panelTitle, { marginTop: 14, fontSize: 14 }]}>{t("autofix.watchSweep1.policy.source.switch.events")}</Text>
            {fedapaySourceEvents.length === 0 ? (
              <Text style={{ color: T.textMuted, fontSize: 12 }}>{t("autofix.watchSweep1.no.source.switch.events.recorded")}</Text>
            ) : (
              <View style={{ gap: 6 }}>
                {fedapaySourceEvents.slice(0, 8).map((evt, idx) => (
                  <Text key={`${evt.changed_at}-${idx}`} style={{ color: T.textSec, fontSize: 11 }} data-testid={`fedapay-source-event-${idx}`} testID={`fedapay-source-event-${idx}`}>
                    {evt.changed_at ? new Date(evt.changed_at).toLocaleString() : 'n/a'}: {evt.from_source} → {evt.to_source}
                  </Text>
                ))}
              </View>
            )}
          </View>
        </>
      )}

      {tab === 'transactions' && (
        <View style={s.panel}>
          {/* Filters */}
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
            {['', 'momo', 'fedapay'].map(p => (
              <TouchableOpacity key={p} onPress={() => { setFilterProvider(p); setTxnPage(1); }}
                style={[s.filterBtn, filterProvider === p && s.filterActive]} data-testid={`filter-provider-${p || 'all'}`} testID={`filter-provider-${p || 'all'}`}>
                <Text style={[s.filterText, filterProvider === p && s.filterActiveText]}>
                  {p ? p.charAt(0).toUpperCase() + p.slice(1) : 'All Providers'}
                </Text>
              </TouchableOpacity>
            ))}
            <View style={{ width: 1, backgroundColor: T.border, marginHorizontal: 4 }} />
            {['', 'success', 'pending', 'failed'].map(st => (
              <TouchableOpacity key={st} onPress={() => { setFilterStatus(st); setTxnPage(1); }}
                style={[s.filterBtn, filterStatus === st && s.filterActive]} data-testid={`filter-status-${st || 'all'}`} testID={`filter-status-${st || 'all'}`}>
                <Text style={[s.filterText, filterStatus === st && s.filterActiveText]}>
                  {st ? st.charAt(0).toUpperCase() + st.slice(1) : 'All Status'}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={{ color: T.textSec, fontSize: 12, marginBottom: 12 }}>{txnTotal}{t("autofix.watchSweep1.transactions")}</Text>

          {/* Transaction Table */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} data-testid="mm-transactions-table-scroll" testID="mm-transactions-table-scroll">
            <View style={{ minWidth: transactionTableMinWidth, width: '100%' }}>
              <View style={s.tableHeader}>
                <Text style={[s.th, { flex: 1.5 }]}>ID</Text>
                <Text style={[s.th, { flex: 1 }]}>{t("autofix.watchSweep1.provider")}</Text>
                <Text style={[s.th, { flex: 1 }]}>{t("autofix.watchSweep1.amount")}</Text>
                <Text style={[s.th, { flex: 1 }]}>{t("admin.gdpr.filters.status")}</Text>
                <Text style={[s.th, { flex: 1.5 }]}>{t("autofix.watchSweep1.date")}</Text>
              </View>
              {txns.map((tx, i) => (
                <View key={i} style={[s.tableRow, i % 2 === 0 && { backgroundColor: T.cardAlt }]} data-testid={`mm-txn-row-${i}`} testID={`mm-txn-row-${i}`}>
                  <Text style={[s.td, { flex: 1.5, color: T.text, fontFamily: 'monospace' }]}>{(tx.payment_id || tx.transaction_id || 'N/A').slice(0, 12)}</Text>
                  <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <View style={[s.gwDotSm, { backgroundColor: tx.provider === 'fedapay' ? T.fedapay : T.momo }]} />
                    <Text style={s.td}>{tx.provider || 'N/A'}</Text>
                  </View>
                  <Text style={[s.td, { flex: 1, color: T.successText, fontFamily: 'monospace' }]}>${(tx.amount ?? 0).toFixed(2)}</Text>
                  <View style={{ flex: 1 }}>
                    <View style={[s.badge, {
                      backgroundColor: tx.status === 'success' ? (globalThis as any).__alphaColor(T.success, '20') : tx.status === 'pending' ? T.warning + '20' : T.error + '20'
                    }]}> 
                      <Text style={{
                        color: tx.status === 'success' ? T.success : tx.status === 'pending' ? T.warning : T.error,
                        fontSize: 10, fontWeight: '700'
                      }}>{(tx.status || 'N/A').toUpperCase()}</Text>
                    </View>
                  </View>
                  <Text style={[s.td, { flex: 1.5 }]}>{tx.created_at ? new Date(tx.created_at).toLocaleDateString() : 'N/A'}</Text>
                </View>
              ))}
            </View>
          </ScrollView>
          {txns.length === 0 && <Text style={{ color: T.textMuted, textAlign: 'center', padding: 40 }}>{t("autofix.watchSweep1.no.transactions.found")}</Text>}

          {/* Pagination */}
          {txnPages > 1 && (
            <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 8, marginTop: 16 }}>
              <TouchableOpacity onPress={() => setTxnPage(Math.max(1, txnPage - 1))} style={s.pageBtn}>
                <Ionicons name="chevron-back" size={16} color={T.text} />
              </TouchableOpacity>
              <Text style={{ color: T.text, alignSelf: 'center' }}>{txnPage} / {txnPages}</Text>
              <TouchableOpacity onPress={() => setTxnPage(Math.min(txnPages, txnPage + 1))} style={s.pageBtn}>
                <Ionicons name="chevron-forward" size={16} color={T.text} />
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: DARK.bg, padding: 20 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12, marginBottom: 20 },
  title: { color: DARK.text, fontSize: 24, fontWeight: '800', letterSpacing: -0.5 },
  subtitle: { color: DARK.textSec, fontSize: 13, marginTop: 2 },
  grid: { gap: 12, flexWrap: 'wrap' },
  kpi: { backgroundColor: DARK.card, borderRadius: 12, padding: 16, borderLeftWidth: 3, flex: 1, minWidth: 160 },
  kpiIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  kpiLabel: { color: DARK.textSec, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 },
  kpiValue: { fontSize: 22, fontWeight: '800', fontFamily: 'monospace', marginTop: 2 },
  kpiSub: { color: DARK.textMuted, fontSize: 10, marginTop: 2 },
  tab: { paddingVertical: 10, paddingHorizontal: 20, borderBottomWidth: 2, borderBottomColor: 'transparent' },
  tabActive: { borderBottomColor: DARK.momo },
  tabText: { color: DARK.textMuted, fontSize: 13, fontWeight: '600' },
  tabActiveText: { color: DARK.text },
  panel: { backgroundColor: DARK.card, borderRadius: 14, padding: 20, marginTop: 16, borderWidth: 1, borderColor: DARK.border },
  panelTitle: { color: DARK.text, fontSize: 16, fontWeight: '700', marginBottom: 16 },
  row: { gap: 16 },
  gwDot: { width: 12, height: 12, borderRadius: 6 },
  gwDotSm: { width: 8, height: 8, borderRadius: 4 },
  barBg: { height: 6, backgroundColor: DARK.cardAlt, borderRadius: 3 },
  barFill: { height: 6, borderRadius: 3 },
  countryBadge: { backgroundColor: DARK.cardAlt, borderRadius: 10, padding: 12, alignItems: 'center', minWidth: 80, borderWidth: 1, borderColor: DARK.border },
  filterBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: DARK.cardAlt, borderWidth: 1, borderColor: DARK.border },
  filterActive: { backgroundColor: (globalThis as any).__alphaColor(DARK.momo, '20'), borderColor: DARK.momo },
  filterText: { color: DARK.textMuted, fontSize: 11, fontWeight: '600' },
  filterActiveText: { color: DARK.momo },
  tableHeader: { flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: DARK.border },
  th: { color: DARK.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  tableRow: { flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(DARK.border, '40'), alignItems: 'center' },
  td: { color: DARK.textSec, fontSize: 12 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: 'flex-start' },
  pageBtn: { backgroundColor: DARK.cardAlt, padding: 8, borderRadius: 8 },
  periodBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: DARK.cardAlt, borderWidth: 1, borderColor: DARK.border },
  periodActive: { backgroundColor: (globalThis as any).__alphaColor(DARK.momo, '20'), borderColor: DARK.momo },
  periodText: { color: DARK.textMuted, fontSize: 11, fontWeight: '600' },
  periodActiveText: { color: DARK.momo },
  exportBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: DARK.cardAlt, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: DARK.border },
});