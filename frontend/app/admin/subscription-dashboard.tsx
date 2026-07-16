import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput, StyleSheet, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import api from '../../src/services/api';
import { useAutoRefresh } from '../../src/hooks/useAutoRefresh';
import { ExecutiveDashboardSkeleton } from '../../src/components/SkeletonLoaders';
import Svg, { Rect, Text as SvgText, Line, Circle } from 'react-native-svg';
import GeoHeatmap from '../../src/components/admin/GeoHeatmap';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { Redirect } from 'expo-router';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';

import { useAdminTheme } from '../../src/hooks/useAdminTheme';
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
  stripe: 'var(--app-primary)', paypal: 'var(--app-primary)', accent: _V.purple,
};
const LIGHT = {
  bg: _V.bg, card: _V.card, cardAlt: _V.cardMuted, border: _V.border,
  text: _V.text, textSec: _V.textSec, textMuted: _V.textMuted,
  primary: _V.primary, success: _V.success, warning: _V.warning, error: _V.error,
  stripe: 'var(--app-primary)', paypal: 'var(--app-primary)', accent: _V.purple,
};

const KpiCard = ({ label, value, icon, color, sub }: any) => (
  <View style={[s.kpi, { borderLeftColor: color }]} data-testid={`kpi-${label.toLowerCase().replace(/\s/g,'-')}`} testID={`kpi-${label.toLowerCase().replace(/\s/g,'-')}`}>
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

const BarChart = ({ data, height = 180, color = DARK.primary, label = 'Revenue' }: any) => {
  const { width } = useWindowDimensions();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  if (!data?.length) return <Text style={{ color: DARK.textMuted, textAlign: 'center', padding: 20 }}>{tx('admin.subscriptionDashboard.states.noData', 'No data')}</Text>;
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
        <SvgText x={15} y={height} fill={DARK.textMuted} fontSize="9" textAnchor="middle">0</SvgText>
      </Svg>
    </View>
  );
};

const DonutChart = ({ data, size = 120 }: any) => {
  const total = data.reduce((a: number, d: any) => a + d.value, 0) || 1;
  const r = size / 2 - 10;
  let startAngle = 0;
  return (
    <View style={{ alignItems: 'center' }}>
      <Svg width={size} height={size}>
        {data.map((d: any, i: number) => {
          const angle = (d.value / total) * 360;
          const endAngle = startAngle + angle;
          const largeArc = angle > 180 ? 1 : 0;
          const sx = size / 2 + r * Math.cos((startAngle * Math.PI) / 180);
          const sy = size / 2 + r * Math.sin((startAngle * Math.PI) / 180);
          const ex = size / 2 + r * Math.cos((endAngle * Math.PI) / 180);
          const ey = size / 2 + r * Math.sin((endAngle * Math.PI) / 180);
          const _path = `M ${size / 2} ${size / 2} L ${sx} ${sy} A ${r} ${r} 0 ${largeArc} 1 ${ex} ${ey} Z`;
          startAngle = endAngle;
          return <Rect key={i} x={0} y={0} width={0} height={0} fill="transparent" />;
        })}
        {(() => { let cum = 0; return data.map((d: any, i: number) => {
          const pct = d.value / total;
          const sa = cum * 2 * Math.PI - Math.PI / 2;
          cum += pct;
          const ea = cum * 2 * Math.PI - Math.PI / 2;
          const _la = pct > 0.5 ? 1 : 0;
          const ir = r * 0.55;
          return <React.Fragment key={i}>
            {pct > 0 && <Rect x={0} y={0} width={0} height={0} fill="transparent" />}
            <Circle cx={size / 2 + (r + ir) / 2 * Math.cos((sa + ea) / 2)} cy={size / 2 + (r + ir) / 2 * Math.sin((sa + ea) / 2)} r={pct * 40 + 4} fill={d.color} opacity={0.9} />
          </React.Fragment>;
        }); })()}
        <Circle cx={size / 2} cy={size / 2} r={r * 0.45} fill={DARK.card} />
        <SvgText x={size / 2} y={size / 2 + 4} fill={DARK.text} fontSize="14" fontWeight="bold" textAnchor="middle">{total.toLocaleString()}</SvgText>
      </Svg>
      <View style={{ flexDirection: 'row', gap: 16, marginTop: 8 }}>
        {data.map((d: any, i: number) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: d.color }} />
            <Text style={{ color: DARK.textSec, fontSize: 11 }}>{d.label}: ${d.value.toLocaleString()}</Text>
          </View>
        ))}
      </View>
    </View>
  );
};

const ReliabilityTrendSparkline = ({ points, color = DARK.success }: { points: { date: string; score: number }[]; color?: string }) => {
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const w = 420;
  const h = 90;
  if (!points?.length) {
    return <Text style={{ color: DARK.textMuted, fontSize: 12 }}>{tx('admin.subscriptionDashboard.reliability.noHistory', 'No reliability history available yet.')}</Text>;
  }
  const max = 100;
  const step = points.length > 1 ? (w - 30) / (points.length - 1) : 0;
  const coords = points.map((p, i) => {
    const x = 20 + i * step;
    const y = h - (Math.max(0, Math.min(100, p.score)) / max) * (h - 20);
    return { x, y, point: p };
  });
  return (
    <Svg width={w} height={h + 22}>
      <Line x1="20" y1={h} x2={w} y2={h} stroke={DARK.border} strokeWidth="1" />
      {coords.map((c, i) => {
        const n = coords[i + 1];
        return n ? <Line key={`seg-${i}`} x1={c.x} y1={c.y} x2={n.x} y2={n.y} stroke={color} strokeWidth="2" /> : null;
      })}
      {coords.map((c, i) => (
        <React.Fragment key={`pt-${i}`}>
          <Circle cx={c.x} cy={c.y} r="2.8" fill={color} />
          {(i === 0 || i === coords.length - 1 || i % 2 === 0) && (
            <SvgText x={c.x} y={h + 12} fill={DARK.textMuted} fontSize="9" textAnchor="middle">{c.point.date.slice(5)}</SvgText>
          )}
        </React.Fragment>
      ))}
    </Svg>
  );
};

const PeriodSelector = ({ period, setPeriod }: any) => (
  <View style={{ flexDirection: 'row', gap: 6 }} data-testid="period-selector" testID="period-selector">
    {['7d', '30d', '90d', '1y'].map(p => (
      <TouchableOpacity key={p} onPress={() => setPeriod(p)}
        style={[s.periodBtn, period === p && s.periodActive]} data-testid={`period-${p}`} testID={`period-${p}`}>
        <Text style={[s.periodText, period === p && s.periodActiveText]}>{p}</Text>
      </TouchableOpacity>
    ))}
  </View>
);

export default function SubscriptionDashboard() {
  const _AC = useAdminTheme();
  const { t } = useTranslation();
  t('i18n.route.admin.subscription-dashboard.probe');
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { user } = useAuth();

  const [data, setData] = useState<any>(null);
  const [subs, setSubs] = useState<any[]>([]);
  const [integrity, setIntegrity] = useState<any>(null);
  const [integrityLoading, setIntegrityLoading] = useState(false);
  const [integrityMessage, setIntegrityMessage] = useState('');
  const [paymentE2E, setPaymentE2E] = useState<any>(null);
  const [paymentE2ELoading, setPaymentE2ELoading] = useState(false);
  const [paymentE2EMessage, setPaymentE2EMessage] = useState('');
  const [integrityHistory, setIntegrityHistory] = useState<any[]>([]);
  const [prayerAudioFunnel, setPrayerAudioFunnel] = useState<any>(null);
  const [prayerAudioFunnelLoading, setPrayerAudioFunnelLoading] = useState(false);
  const [prayerAudioFunnelMessage, setPrayerAudioFunnelMessage] = useState('');
  const [prayerAudioCategoryAttribution, setPrayerAudioCategoryAttribution] = useState<any>(null);
  const [prayerAudioCategoryAttributionLoading, setPrayerAudioCategoryAttributionLoading] = useState(false);
  const [prayerAudioCategoryAttributionMessage, setPrayerAudioCategoryAttributionMessage] = useState('');
  const [recoverableError, setRecoverableError] = useState('');
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('30d');
  const [search, setSearch] = useState('');
  const [subPage, setSubPage] = useState(1);
  const [subTotal, setSubTotal] = useState(0);
  const [subPages, setSubPages] = useState(1);
  const [tab, setTab] = useState<'overview' | 'subscribers'>('overview');
  const [isDark, setIsDark] = useState(true);
  const {darkMode: globalDark, _colors} = useTheme();
  useEffect(() => { setIsDark(globalDark); }, [globalDark]);
  const T = isDark ? DARK : LIGHT;
  const { width } = useWindowDimensions();
  const isWide = width > 768;

  if (!hasAdminConsoleVisibility(user as any)) {
    return <Redirect href="/dashboard" />;
  }

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [overview, subList, integrityLatest, paymentE2ELatest, integrityHistoryResp, prayerAudioFunnelResp, prayerAudioCategoryAttributionResp] = await Promise.all([
        api.get(`/admin/payment-analytics/subscriptions/overview?period=${period}`),
        api.get(`/admin/payment-analytics/subscriptions/subscribers?page=${subPage}&search=${encodeURIComponent(search)}`),
        api.get('/admin/payment-analytics/subscriptions/integrity-report/latest').catch(() => ({ data: null })),
        api.get('/admin/payment-analytics/subscriptions/payment-e2e/latest').catch(() => ({ data: null })),
        api.get('/admin/payment-analytics/subscriptions/integrity-report/history?limit=14').catch(() => ({ data: { reports: [] } })),
        api.get('/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary?days=14&conversion_window_days=14').catch(() => ({ data: null })),
        api.get('/travel-visa/daily-meditation/admin/prayer-audio/upgrade-attribution/categories?days=30&conversion_window_days=14&top=12').catch(() => ({ data: null })),
      ]);
      if (overview.data) setData(overview.data);
      if (subList.data) {
        setSubs(subList.data.subscribers || []);
        setSubTotal(subList.data.total || 0);
        setSubPages(subList.data.pages || 1);
      }
      if (integrityLatest?.data) setIntegrity(integrityLatest.data);
      if (paymentE2ELatest?.data) setPaymentE2E(paymentE2ELatest.data);
      setIntegrityHistory(integrityHistoryResp?.data?.reports || []);
      if (prayerAudioFunnelResp?.data) setPrayerAudioFunnel(prayerAudioFunnelResp.data);
      if (prayerAudioCategoryAttributionResp?.data) setPrayerAudioCategoryAttribution(prayerAudioCategoryAttributionResp.data);
      setRecoverableError('');
    } catch (e) {
      handleAppRecoverableError({
        scope: 'admin.subscription.load-data',
        error: e,
        message: tx('admin.subscriptionDashboard.errors.loadFailed', 'Could not load subscription dashboard data.'),
        setError: setRecoverableError,
        onRetry: () => { void loadData(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    setLoading(false);
  }, [period, subPage, search]);

  useEffect(() => { loadData(); }, [loadData]);

  // 30-second auto-refresh for real-time data
  useAutoRefresh(loadData, { intervalMs: 30000 });

  const runIntegrityCheck = async () => {
    setIntegrityLoading(true);
    setIntegrityMessage('');
    try {
      const res = await api.post('/admin/payment-analytics/subscriptions/integrity-check?auto_fix=true');
      setIntegrity(res.data || null);
      const fixed = res.data?.stats?.autofix_applied ?? 0;
      const severity = (res.data?.severity || 'unknown').toUpperCase();
      setIntegrityMessage(
        tx('admin.subscriptionDashboard.messages.integrityComplete', 'Integrity check complete · severity {severity} · auto-fixes {fixed}')
          .replace('{severity}', severity)
          .replace('{fixed}', String(fixed))
      );
    } catch (e: any) {
      setIntegrityMessage(e?.response?.data?.detail || tx('admin.subscriptionDashboard.errors.integrityFailed', 'Failed to run integrity check'));
    } finally {
      setIntegrityLoading(false);
    }
  };

  const runPaymentE2E = async (fullSuite: boolean) => {
    setPaymentE2ELoading(true);
    setPaymentE2EMessage('');
    try {
      const res = await api.post(`/admin/payment-analytics/subscriptions/payment-e2e/run?full_suite=${fullSuite ? 'true' : 'false'}`);
      setPaymentE2E(res.data || null);
      const summary = res.data?.summary || {};
      setPaymentE2EMessage(
        tx('admin.subscriptionDashboard.messages.paymentE2EComplete', 'Payment E2E complete · {passed}/{total} checks passed ({rate}%)')
          .replace('{passed}', String(summary.passed ?? 0))
          .replace('{total}', String(summary.total ?? 0))
          .replace('{rate}', String(summary.pass_rate ?? 0))
      );
    } catch (e: any) {
      setPaymentE2EMessage(e?.response?.data?.detail || tx('admin.subscriptionDashboard.errors.paymentE2EFailed', 'Failed to run payment E2E control checks'));
    } finally {
      setPaymentE2ELoading(false);
    }
  };

  const downloadPaymentE2E = async (format: 'json' | 'csv') => {
    try {
      const res = await api.get(`/admin/payment-analytics/subscriptions/payment-e2e/export?format=${format}`);
      let content = '';
      if (format === 'json') {
        content = JSON.stringify(res.data || {}, null, 2);
      } else {
        content = typeof res.data === 'string' ? res.data : '';
      }
      if (typeof document !== 'undefined') {
        const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = format === 'json' ? 'payment_e2e_latest.json' : 'payment_e2e_latest.csv';
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      setPaymentE2EMessage(
        e?.response?.data?.detail || tx('admin.subscriptionDashboard.errors.exportFormatFailed', 'Failed to export {format} report').replace('{format}', format.toUpperCase())
      );
    }
  };

  const reliabilityPoints = (integrityHistory || [])
    .slice()
    .reverse()
    .slice(-7)
    .map((r: any) => {
      const severity = String(r?.severity || 'unknown').toLowerCase();
      const drift = Number(r?.stats?.entitlement_drift_count || 0);
      const expired = Number(r?.stats?.expired_but_active_count || 0);
      const pending = Number(r?.stats?.stale_pending_count || 0);
      let base = severity === 'low' ? 95 : severity === 'medium' ? 82 : severity === 'high' ? 65 : 75;
      base -= Math.min(25, drift * 2 + expired * 2 + pending);
      return {
        date: String(r?.generated_at || '').slice(0, 10),
        score: Math.max(0, Math.min(100, Math.round(base))),
      };
    });

  const handleExport = async () => {
    try {
      const res = await api.get(`/admin/payment-analytics/subscriptions/export?period=${period}`);
      if (res.data?.csv_data) {
        const blob = new Blob([res.data.csv_data], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `subscriptions_${period}.csv`; a.click();
      }
    } catch (e) {
      handleAppRecoverableError({
        scope: 'admin.subscription.export',
        error: e,
        message: tx('admin.subscriptionDashboard.errors.exportFailed', 'Failed to export subscription report.'),
        setError: setRecoverableError,
        onRetry: () => { void handleExport(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  };

  const refreshPrayerAudioFunnel = async () => {
    setPrayerAudioFunnelLoading(true);
    setPrayerAudioFunnelMessage('');
    try {
      const res = await api.get('/travel-visa/daily-meditation/admin/prayer-audio/funnel-summary?days=14&conversion_window_days=14');
      setPrayerAudioFunnel(res.data || null);
      setPrayerAudioFunnelMessage(tx('admin.subscriptionDashboard.prayerAudio.funnelRefreshed', 'Prayer audio funnel refreshed successfully.'));
    } catch (e: any) {
      setPrayerAudioFunnelMessage(e?.response?.data?.detail || tx('admin.subscriptionDashboard.prayerAudio.funnelFailed', 'Failed to refresh prayer audio funnel.'));
    } finally {
      setPrayerAudioFunnelLoading(false);
    }
  };

  const exportPrayerAudioFunnel = async (format: 'csv' | 'json') => {
    try {
      const res = await api.get(`/travel-visa/daily-meditation/admin/prayer-audio/funnel-export?days=14&conversion_window_days=14&format=${format}`);
      const content = format === 'json' ? JSON.stringify(res.data || {}, null, 2) : (typeof res.data === 'string' ? res.data : '');
      if (typeof document !== 'undefined') {
        const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = format === 'json' ? 'prayer_audio_funnel.json' : 'prayer_audio_funnel.csv';
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      setPrayerAudioFunnelMessage(e?.response?.data?.detail || tx('admin.subscriptionDashboard.prayerAudio.funnelExportFailed', 'Failed to export prayer audio funnel report.'));
    }
  };

  const refreshPrayerAudioCategoryAttribution = async () => {
    setPrayerAudioCategoryAttributionLoading(true);
    setPrayerAudioCategoryAttributionMessage('');
    try {
      const res = await api.get('/travel-visa/daily-meditation/admin/prayer-audio/upgrade-attribution/categories?days=30&conversion_window_days=14&top=12');
      setPrayerAudioCategoryAttribution(res.data || null);
      setPrayerAudioCategoryAttributionMessage(tx('admin.subscriptionDashboard.prayerAudio.categoryAttributionRefreshed', 'Category attribution refreshed successfully.'));
    } catch (e: any) {
      setPrayerAudioCategoryAttributionMessage(e?.response?.data?.detail || tx('admin.subscriptionDashboard.prayerAudio.categoryAttributionFailed', 'Failed to refresh category attribution.'));
    } finally {
      setPrayerAudioCategoryAttributionLoading(false);
    }
  };

  const exportPrayerAudioCategoryAttribution = async (format: 'csv' | 'json') => {
    try {
      const res = await api.get(`/travel-visa/daily-meditation/admin/prayer-audio/upgrade-attribution/export?days=30&conversion_window_days=14&top=20&format=${format}`);
      const content = format === 'json' ? JSON.stringify(res.data || {}, null, 2) : (typeof res.data === 'string' ? res.data : '');
      if (typeof document !== 'undefined') {
        const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = format === 'json' ? 'prayer_audio_upgrade_attribution.json' : 'prayer_audio_upgrade_attribution.csv';
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      setPrayerAudioCategoryAttributionMessage(e?.response?.data?.detail || tx('admin.subscriptionDashboard.prayerAudio.categoryAttributionExportFailed', 'Failed to export category attribution report.'));
    }
  };

  if (loading && !data) return (
    <ExecutiveDashboardSkeleton />
  );

  const fmt = (n: number) => n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n.toFixed(2)}`;

  return (
    <ScrollView style={[s.container, { backgroundColor: T.bg }]} data-testid="subscription-dashboard" testID="subscription-dashboard">
      {recoverableError ? (
        <View
          style={{ marginHorizontal: 20, marginTop: 12, marginBottom: 8, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: T.error + '35', backgroundColor: T.card, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
          data-testid="subscription-dashboard-recoverable-error-banner"
          testID="subscription-dashboard-recoverable-error-banner"
        >
          <Text style={{ color: T.error, fontSize: 12, fontWeight: '700', flex: 1 }} data-testid="subscription-dashboard-recoverable-error-text" testID="subscription-dashboard-recoverable-error-text">{recoverableError}</Text>
          <TouchableOpacity
            onPress={() => { void loadData(); }}
            style={{ backgroundColor: T.error, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}
            data-testid="subscription-dashboard-recoverable-error-retry"
            testID="subscription-dashboard-recoverable-error-retry"
          >
            <Text style={{ color: T.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      ) : null}
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.title}>{tx('admin.subscriptionDashboard.header.title', 'Subscription Analytics')}</Text>
          <Text style={s.subtitle}>{tx('admin.subscriptionDashboard.header.subtitle', 'Stripe + PayPal Revenue Dashboard')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <PeriodSelector period={period} setPeriod={setPeriod} />
          <TouchableOpacity onPress={handleExport} style={[s.exportBtn, { backgroundColor: T.cardAlt, borderColor: T.border }]} data-testid="export-btn" testID="export-btn">
            <Ionicons name="download-outline" size={16} color={T.text} />
            <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{tx('admin.subscriptionDashboard.actions.export', 'Export')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setIsDark(!isDark)} style={[s.exportBtn, { backgroundColor: T.cardAlt, borderColor: T.border }]} data-testid="theme-toggle" testID="theme-toggle">
            <Ionicons name={isDark ? 'sunny-outline' : 'moon-outline'} size={16} color={T.text} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Payment E2E Control Center */}
      <View style={[s.panel, { marginTop: 14 }]} data-testid="subscription-payment-e2e-panel" testID="subscription-payment-e2e-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <View>
            <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.paymentE2E.title', 'Payment E2E Control Center')}</Text>
            <Text style={{ color: T.textSec, fontSize: 12 }} data-testid="subscription-payment-e2e-generated-at" testID="subscription-payment-e2e-generated-at">
              {tx('admin.subscriptionDashboard.common.lastRun', 'Last run')}: {paymentE2E?.generated_at ? new Date(paymentE2E.generated_at).toLocaleString() : tx('admin.subscriptionDashboard.common.noReportYet', 'No report yet')}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={() => runPaymentE2E(false)}
              disabled={paymentE2ELoading}
              style={[s.exportBtn, { opacity: paymentE2ELoading ? 0.6 : 1 }]}
              data-testid="subscription-payment-e2e-run-button" testID="subscription-payment-e2e-run-button"
            >
              <Ionicons name="flash-outline" size={16} color={T.primary} />
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.paymentE2E.actions.runChecks', 'Run Checks')}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => runPaymentE2E(true)}
              disabled={paymentE2ELoading}
              style={[s.exportBtn, { opacity: paymentE2ELoading ? 0.6 : 1 }]}
              data-testid="subscription-payment-e2e-full-suite-button" testID="subscription-payment-e2e-full-suite-button"
            >
              {paymentE2ELoading ? <ActivityIndicator size="small" color={T.warningText} /> : <Ionicons name="build-outline" size={16} color={T.warningText} />}
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{paymentE2ELoading ? tx('admin.subscriptionDashboard.common.running', 'Running...') : tx('admin.subscriptionDashboard.paymentE2E.actions.runFullSuite', 'Run Full E2E Suite')}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => downloadPaymentE2E('json')}
              style={s.exportBtn}
              data-testid="subscription-payment-e2e-export-json-button" testID="subscription-payment-e2e-export-json-button"
            >
              <Ionicons name="document-text-outline" size={16} color={T.primary} />
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.paymentE2E.actions.exportJson', 'Export JSON')}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => downloadPaymentE2E('csv')}
              style={s.exportBtn}
              data-testid="subscription-payment-e2e-export-csv-button" testID="subscription-payment-e2e-export-csv-button"
            >
              <Ionicons name="grid-outline" size={16} color={T.primary} />
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.paymentE2E.actions.exportCsv', 'Export CSV')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ marginTop: 12, flexDirection: isWide ? 'row' : 'column', gap: 10, flexWrap: 'wrap' }}>
          <View style={s.integrityPill} data-testid="subscription-payment-e2e-severity" testID="subscription-payment-e2e-severity">
            <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.common.severity', 'Severity')}</Text>
            <Text style={[s.integrityValue, {
              color: paymentE2E?.severity === 'high' ? T.error : paymentE2E?.severity === 'degraded' ? T.warning : T.success,
            }]}>{(paymentE2E?.severity || 'unknown').toUpperCase()}</Text>
          </View>
          <View style={s.integrityPill} data-testid="subscription-payment-e2e-pass-rate" testID="subscription-payment-e2e-pass-rate">
            <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.paymentE2E.passRate', 'Pass Rate')}</Text>
            <Text style={s.integrityValue}>{paymentE2E?.summary?.pass_rate ?? 0}%</Text>
          </View>
          <View style={s.integrityPill} data-testid="subscription-payment-e2e-checks-count" testID="subscription-payment-e2e-checks-count">
            <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.paymentE2E.checks', 'Checks')}</Text>
            <Text style={s.integrityValue}>{paymentE2E?.summary?.passed ?? 0}/{paymentE2E?.summary?.total ?? 0}</Text>
          </View>
          <View style={s.integrityPill} data-testid="subscription-payment-e2e-email-log-count" testID="subscription-payment-e2e-email-log-count">
            <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.paymentE2E.recentEmailLogs', 'Recent Email Logs')}</Text>
            <Text style={s.integrityValue}>{(paymentE2E?.email_delivery_logs || []).length}</Text>
          </View>
        </View>

        {!!paymentE2EMessage && (
          <Text style={{ marginTop: 10, color: T.textSec, fontSize: 12 }} data-testid="subscription-payment-e2e-message" testID="subscription-payment-e2e-message">
            {paymentE2EMessage}
          </Text>
        )}
      </View>

      {/* KPI Row */}
      <View style={[s.panel, { marginTop: 14 }]} data-testid="subscription-reliability-trend-panel" testID="subscription-reliability-trend-panel">
        <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.reliability.title', 'Weekly Reliability Trend')}</Text>
        <Text style={{ color: T.textSec, fontSize: 12, marginTop: 4 }} data-testid="subscription-reliability-trend-subtitle" testID="subscription-reliability-trend-subtitle">
          {tx('admin.subscriptionDashboard.reliability.subtitle', 'Rolling 7-report reliability score from nightly integrity checks.')}
        </Text>
        <View style={{ marginTop: 10 }} data-testid="subscription-reliability-trend-chart" testID="subscription-reliability-trend-chart">
          <ReliabilityTrendSparkline points={reliabilityPoints} color={T.successText} />
        </View>
      </View>

      {/* KPI Row */}
      <View style={[s.grid, isWide && { flexDirection: 'row' }]}>
        <KpiCard label={tx('admin.subscriptionDashboard.kpi.mrr', 'MRR')} value={fmt(data?.mrr ?? 0)} icon="trending-up" color={T.successText} sub={tx('admin.subscriptionDashboard.kpi.mrrSub', 'Monthly Recurring Revenue')} />
        <KpiCard label={tx('admin.subscriptionDashboard.kpi.arr', 'ARR')} value={fmt(data?.arr ?? 0)} icon="stats-chart" color={T.primary} sub={tx('admin.subscriptionDashboard.kpi.arrSub', 'Annual Recurring Revenue')} />
        <KpiCard label={tx('admin.subscriptionDashboard.kpi.activeSubs', 'Active Subs')} value={data?.active_subscribers ?? 0} icon="people" color={T.accent} sub={tx('admin.subscriptionDashboard.kpi.newThisPeriod', '{count} new this period').replace('{count}', String(data?.new_subscribers ?? 0))} />
        <KpiCard label={tx('admin.subscriptionDashboard.kpi.churnRate', 'Churn Rate')} value={`${data?.churn_rate ?? 0}%`} icon="arrow-down" color={T.error} sub={tx('admin.subscriptionDashboard.kpi.canceledCount', '{count} canceled').replace('{count}', String(data?.canceled_subscribers ?? 0))} />
        <KpiCard label={tx('admin.subscriptionDashboard.kpi.arpu', 'ARPU')} value={fmt(data?.arpu ?? 0)} icon="person" color={T.warningText} sub={tx('admin.subscriptionDashboard.kpi.arpuSub', 'Avg Revenue Per User')} />
        <KpiCard label={tx('admin.subscriptionDashboard.kpi.totalRevenue', 'Total Revenue')} value={fmt(data?.total_revenue ?? 0)} icon="cash" color={T.successText} sub={tx('admin.subscriptionDashboard.kpi.paymentsCount', '{count} payments').replace('{count}', String(data?.payment_count ?? 0))} />
      </View>

      {/* Integrity Health */}
      <View style={[s.panel, { marginTop: 14 }]} data-testid="subscription-integrity-panel" testID="subscription-integrity-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <View>
            <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.integrity.title', 'Nightly Integrity Health')}</Text>
            <Text style={{ color: T.textSec, fontSize: 12 }} data-testid="subscription-integrity-generated-at" testID="subscription-integrity-generated-at">
              {tx('admin.subscriptionDashboard.common.lastRun', 'Last run')}: {integrity?.generated_at ? new Date(integrity.generated_at).toLocaleString() : tx('admin.subscriptionDashboard.common.noReportYet', 'No report yet')}
            </Text>
          </View>
          <TouchableOpacity
            onPress={runIntegrityCheck}
            disabled={integrityLoading}
            style={[s.exportBtn, { opacity: integrityLoading ? 0.6 : 1 }]}
            data-testid="subscription-integrity-run-button" testID="subscription-integrity-run-button"
          >
            {integrityLoading ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="shield-checkmark-outline" size={16} color={T.primary} />}
            <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{integrityLoading ? tx('admin.subscriptionDashboard.common.running', 'Running...') : tx('admin.subscriptionDashboard.integrity.actions.runCheck', 'Run Integrity Check')}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ marginTop: 12, flexDirection: isWide ? 'row' : 'column', gap: 10, flexWrap: 'wrap' }}>
          <View style={s.integrityPill} data-testid="subscription-integrity-severity" testID="subscription-integrity-severity">
            <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.common.severity', 'Severity')}</Text>
            <Text style={[s.integrityValue, {
              color: integrity?.severity === 'high' ? T.error : integrity?.severity === 'medium' ? T.warning : T.success,
            }]}>{(integrity?.severity || 'unknown').toUpperCase()}</Text>
          </View>
          <View style={s.integrityPill} data-testid="subscription-integrity-drift-count" testID="subscription-integrity-drift-count">
            <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.integrity.entitlementDrift', 'Entitlement Drift')}</Text>
            <Text style={s.integrityValue}>{integrity?.stats?.entitlement_drift_count ?? 0}</Text>
          </View>
          <View style={s.integrityPill} data-testid="subscription-integrity-expired-active-count" testID="subscription-integrity-expired-active-count">
            <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.integrity.expiredButActive', 'Expired but Active')}</Text>
            <Text style={s.integrityValue}>{integrity?.stats?.expired_but_active_count ?? 0}</Text>
          </View>
          <View style={s.integrityPill} data-testid="subscription-integrity-autofix-count" testID="subscription-integrity-autofix-count">
            <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.integrity.autoFixes', 'Auto Fixes')}</Text>
            <Text style={s.integrityValue}>{integrity?.stats?.autofix_applied ?? 0}</Text>
          </View>
        </View>

        {!!integrityMessage && (
          <Text style={{ marginTop: 10, color: T.textSec, fontSize: 12 }} data-testid="subscription-integrity-message" testID="subscription-integrity-message">
            {integrityMessage}
          </Text>
        )}
      </View>

      {/* Tab Switcher */}
      <View style={{ flexDirection: 'row', gap: 0, marginTop: 20 }}>
        {(['overview', 'subscribers'] as const).map(t => (
          <TouchableOpacity key={t} onPress={() => setTab(t)}
            style={[s.tab, tab === t && s.tabActive]} data-testid={`tab-${t}`} testID={`tab-${t}`}>
            <Text style={[s.tabText, tab === t && s.tabActiveText]}>{t === 'overview' ? tx('admin.subscriptionDashboard.tabs.analyticsOverview', 'Analytics Overview') : tx('admin.subscriptionDashboard.tabs.manageSubscribers', 'Manage Subscribers')}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'overview' && (
        <>
          <View style={s.panel} data-testid="prayer-audio-funnel-panel" testID="prayer-audio-funnel-panel">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <View>
                <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.prayerAudio.title', 'Prayer Audio Completion Funnel')}</Text>
                <Text style={{ color: T.textSec, fontSize: 12 }} data-testid="prayer-audio-funnel-subtitle" testID="prayer-audio-funnel-subtitle">
                  {tx('admin.subscriptionDashboard.prayerAudio.subtitle', 'Last-touch cohort analytics for Free→Basic conversion optimization (14-day window).')}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <TouchableOpacity
                  onPress={refreshPrayerAudioFunnel}
                  disabled={prayerAudioFunnelLoading}
                  style={[s.exportBtn, { opacity: prayerAudioFunnelLoading ? 0.6 : 1 }]}
                  data-testid="prayer-audio-funnel-refresh-button"
                  testID="prayer-audio-funnel-refresh-button"
                >
                  {prayerAudioFunnelLoading ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="refresh-outline" size={16} color={T.primary} />}
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.prayerAudio.refresh', 'Refresh')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => exportPrayerAudioFunnel('csv')}
                  style={s.exportBtn}
                  data-testid="prayer-audio-funnel-export-csv-button"
                  testID="prayer-audio-funnel-export-csv-button"
                >
                  <Ionicons name="download-outline" size={16} color={T.primary} />
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.prayerAudio.exportCsv', 'Export CSV')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => exportPrayerAudioFunnel('json')}
                  style={s.exportBtn}
                  data-testid="prayer-audio-funnel-export-json-button"
                  testID="prayer-audio-funnel-export-json-button"
                >
                  <Ionicons name="document-text-outline" size={16} color={T.primary} />
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.prayerAudio.exportJson', 'Export JSON')}</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={{ marginTop: 12, flexDirection: isWide ? 'row' : 'column', gap: 10, flexWrap: 'wrap' }}>
              <View style={s.integrityPill} data-testid="prayer-audio-funnel-opened" testID="prayer-audio-funnel-opened">
                <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.prayerAudio.stepOpened', 'Drop Opened')}</Text>
                <Text style={s.integrityValue}>{prayerAudioFunnel?.totals?.drop_opened ?? 0}</Text>
              </View>
              <View style={s.integrityPill} data-testid="prayer-audio-funnel-played" testID="prayer-audio-funnel-played">
                <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.prayerAudio.stepPlayed', 'Played')}</Text>
                <Text style={s.integrityValue}>{prayerAudioFunnel?.totals?.played ?? 0}</Text>
              </View>
              <View style={s.integrityPill} data-testid="prayer-audio-funnel-completed" testID="prayer-audio-funnel-completed">
                <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.prayerAudio.stepCompleted', 'Completed')}</Text>
                <Text style={s.integrityValue}>{prayerAudioFunnel?.totals?.completed ?? 0}</Text>
              </View>
              <View style={s.integrityPill} data-testid="prayer-audio-funnel-upgraded" testID="prayer-audio-funnel-upgraded">
                <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.prayerAudio.stepUpgraded', 'Upgraded')}</Text>
                <Text style={s.integrityValue}>{prayerAudioFunnel?.totals?.upgraded ?? 0}</Text>
              </View>
            </View>

            <View style={{ marginTop: 12 }} data-testid="prayer-audio-funnel-cohort-grid" testID="prayer-audio-funnel-cohort-grid">
              {["free", "basic", "premium"].map((planKey) => {
                const c = prayerAudioFunnel?.cohorts?.[planKey] || {};
                return (
                  <View key={planKey} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10, backgroundColor: T.cardAlt, marginBottom: 8 }}>
                    <Text style={{ color: T.text, fontWeight: '800', fontSize: 12, marginBottom: 6, textTransform: 'uppercase' }}>{planKey}</Text>
                    <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.subscriptionDashboard.prayerAudio.playRate', 'Play rate')}: {c.play_rate_pct ?? 0}%</Text>
                    <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.subscriptionDashboard.prayerAudio.completeRate', 'Completion rate')}: {c.completion_rate_pct ?? 0}%</Text>
                    <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.subscriptionDashboard.prayerAudio.upgradeRate', 'Upgrade rate')}: {c.upgrade_rate_pct ?? 0}%</Text>
                  </View>
                );
              })}
            </View>

            {!!prayerAudioFunnelMessage && (
              <Text style={{ marginTop: 8, color: T.textSec, fontSize: 12 }} data-testid="prayer-audio-funnel-message" testID="prayer-audio-funnel-message">
                {prayerAudioFunnelMessage}
              </Text>
            )}
          </View>

          <View style={s.panel} data-testid="prayer-audio-category-attribution-panel" testID="prayer-audio-category-attribution-panel">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <View>
                <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.prayerAudio.categoryAttributionTitle', 'Prayer Audio Upgrade Attribution by Category')}</Text>
                <Text style={{ color: T.textSec, fontSize: 12 }} data-testid="prayer-audio-category-attribution-subtitle" testID="prayer-audio-category-attribution-subtitle">
                  {tx('admin.subscriptionDashboard.prayerAudio.categoryAttributionSubtitle', 'Last-touch category slices for plan upgrades (30-day lookback).')}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <TouchableOpacity
                  onPress={refreshPrayerAudioCategoryAttribution}
                  disabled={prayerAudioCategoryAttributionLoading}
                  style={[s.exportBtn, { opacity: prayerAudioCategoryAttributionLoading ? 0.6 : 1 }]}
                  data-testid="prayer-audio-category-attribution-refresh-button"
                  testID="prayer-audio-category-attribution-refresh-button"
                >
                  {prayerAudioCategoryAttributionLoading ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="refresh-outline" size={16} color={T.primary} />}
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.prayerAudio.refresh', 'Refresh')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => exportPrayerAudioCategoryAttribution('csv')}
                  style={s.exportBtn}
                  data-testid="prayer-audio-category-attribution-export-csv-button"
                  testID="prayer-audio-category-attribution-export-csv-button"
                >
                  <Ionicons name="download-outline" size={16} color={T.primary} />
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.prayerAudio.exportCsv', 'Export CSV')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => exportPrayerAudioCategoryAttribution('json')}
                  style={s.exportBtn}
                  data-testid="prayer-audio-category-attribution-export-json-button"
                  testID="prayer-audio-category-attribution-export-json-button"
                >
                  <Ionicons name="document-text-outline" size={16} color={T.primary} />
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.subscriptionDashboard.prayerAudio.exportJson', 'Export JSON')}</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={{ marginTop: 12, flexDirection: isWide ? 'row' : 'column', gap: 10, flexWrap: 'wrap' }}>
              <View style={s.integrityPill} data-testid="prayer-audio-category-attribution-categories-count" testID="prayer-audio-category-attribution-categories-count">
                <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.prayerAudio.categories', 'Categories')}</Text>
                <Text style={s.integrityValue}>{prayerAudioCategoryAttribution?.totals?.categories_considered ?? 0}</Text>
              </View>
              <View style={s.integrityPill} data-testid="prayer-audio-category-attribution-touch-users" testID="prayer-audio-category-attribution-touch-users">
                <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.prayerAudio.touchUsers', 'Touch Users')}</Text>
                <Text style={s.integrityValue}>{prayerAudioCategoryAttribution?.totals?.distinct_touch_users ?? 0}</Text>
              </View>
              <View style={s.integrityPill} data-testid="prayer-audio-category-attribution-upgraded-users" testID="prayer-audio-category-attribution-upgraded-users">
                <Text style={s.integrityLabel}>{tx('admin.subscriptionDashboard.prayerAudio.upgradedUsers', 'Upgraded Users')}</Text>
                <Text style={s.integrityValue}>{prayerAudioCategoryAttribution?.totals?.distinct_upgraded_users ?? 0}</Text>
              </View>
            </View>

            <View style={{ marginTop: 12 }} data-testid="prayer-audio-category-attribution-grid" testID="prayer-audio-category-attribution-grid">
              {(prayerAudioCategoryAttribution?.category_slices || []).slice(0, 10).map((row: any) => (
                <View
                  key={String(row?.category || 'unknown')}
                  style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10, backgroundColor: T.cardAlt, marginBottom: 8 }}
                  data-testid={`prayer-audio-category-attribution-row-${String(row?.category || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                  testID={`prayer-audio-category-attribution-row-${String(row?.category || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
                >
                  <Text style={{ color: T.text, fontWeight: '800', fontSize: 12, marginBottom: 4 }}>{row?.category || 'Unknown Category'}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.subscriptionDashboard.prayerAudio.touchUsers', 'Touch Users')}: {row?.touch_users ?? 0}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.subscriptionDashboard.prayerAudio.upgradedUsers', 'Upgraded Users')}: {row?.upgraded_users ?? 0}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.subscriptionDashboard.prayerAudio.upgradeRate', 'Upgrade rate')}: {row?.upgrade_rate_pct ?? 0}%</Text>
                </View>
              ))}
            </View>

            {!!prayerAudioCategoryAttributionMessage && (
              <Text style={{ marginTop: 8, color: T.textSec, fontSize: 12 }} data-testid="prayer-audio-category-attribution-message" testID="prayer-audio-category-attribution-message">
                {prayerAudioCategoryAttributionMessage}
              </Text>
            )}
          </View>

          {/* Revenue Trend */}
          <View style={s.panel}>
            <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.revenueTrend.title', 'Revenue Trend')}</Text>
            <BarChart data={data?.revenue_trend} color={T.successText} />
          </View>

          {/* Provider Breakdown */}
          <View style={[s.row, isWide && { flexDirection: 'row' }]}>
            <View style={[s.panel, { flex: 1 }]}>
              <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.paymentSplit.title', 'Payment Method Split')}</Text>
              <DonutChart data={[
                { label: 'Stripe', value: data?.stripe?.revenue ?? 0, color: T.stripe },
                { label: 'PayPal', value: data?.paypal?.revenue ?? 0, color: T.paypal },
              ]} />
            </View>
            <View style={[s.panel, { flex: 1 }]}>
              <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.transactions.title', 'Transaction Count')}</Text>
              <View style={{ gap: 12, padding: 12 }}>
                <View style={s.providerRow}>
                  <View style={[s.providerDot, { backgroundColor: T.stripe }]} />
                  <Text style={s.providerLabel}>Stripe</Text>
                  <Text style={s.providerValue}>{tx('admin.subscriptionDashboard.transactions.txnCount', '{count} txns').replace('{count}', String(data?.stripe?.count ?? 0))}</Text>
                  <Text style={[s.providerValue, { color: T.successText }]}>${(data?.stripe?.revenue ?? 0).toLocaleString()}</Text>
                </View>
                <View style={s.providerRow}>
                  <View style={[s.providerDot, { backgroundColor: T.paypal }]} />
                  <Text style={s.providerLabel}>PayPal</Text>
                  <Text style={s.providerValue}>{tx('admin.subscriptionDashboard.transactions.txnCount', '{count} txns').replace('{count}', String(data?.paypal?.count ?? 0))}</Text>
                  <Text style={[s.providerValue, { color: T.successText }]}>${(data?.paypal?.revenue ?? 0).toLocaleString()}</Text>
                </View>
              </View>
            </View>
          </View>

          {/* Geographic Revenue Heatmap */}
          <View style={{ marginTop: 16 }}>
            <GeoHeatmap
              revenueByCountry={data?.revenue_by_country ?? {}}
              accentColor={T.primary}
              title={tx('admin.subscriptionDashboard.geo.title', 'Subscription Revenue by Region')}
            />
          </View>

          {/* Revenue by Currency */}
          {Object.keys(data?.revenue_by_currency ?? {}).length > 0 && (
            <View style={s.panel}>
              <Text style={s.panelTitle}>{tx('admin.subscriptionDashboard.currency.title', 'Revenue by Currency')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, padding: 8 }}>
                {Object.entries(data.revenue_by_currency).map(([cur, info]: any) => (
                  <View key={cur} style={s.currBadge}>
                    <Text style={{ color: T.text, fontWeight: '700', fontSize: 13 }}>{cur}</Text>
                    <Text style={{ color: T.successText, fontSize: 12 }}>${info.revenue.toLocaleString()}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.subscriptionDashboard.transactions.txnCount', '{count} txns').replace('{count}', String(info.count))}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}
        </>
      )}

      {tab === 'subscribers' && (
        <View style={s.panel}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <View style={[s.searchBox, { flex: 1 }]}>
              <Ionicons name="search" size={16} color={T.textMuted} />
              <TextInput
                style={s.searchInput}
                placeholder={tx('admin.subscriptionDashboard.subscribers.searchPlaceholder', 'Search subscribers...')}
                placeholderTextColor={T.textMuted}
                value={search}
                onChangeText={setSearch}
                data-testid="search-subscribers" testID="search-subscribers"
              />
            </View>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.subscriptionDashboard.subscribers.totalWithCount', '{count} total').replace('{count}', String(subTotal))}</Text>
          </View>

          {/* Subscribers Table */}
          <View style={s.tableHeader}>
            <Text style={[s.th, { flex: 2 }]}>{tx('admin.subscriptionDashboard.subscribers.table.user', 'User')}</Text>
            <Text style={[s.th, { flex: 1.5 }]}>{tx('admin.subscriptionDashboard.subscribers.table.plan', 'Plan')}</Text>
            <Text style={[s.th, { flex: 1 }]}>{tx('admin.subscriptionDashboard.subscribers.table.status', 'Status')}</Text>
            <Text style={[s.th, { flex: 1.5 }]}>{tx('admin.subscriptionDashboard.subscribers.table.created', 'Created')}</Text>
          </View>
          {subs.map((sub, i) => (
            <View key={i} style={[s.tableRow, i % 2 === 0 && { backgroundColor: T.cardAlt }]} data-testid={`subscriber-row-${i}`} testID={`subscriber-row-${i}`}>
              <Text style={[s.td, { flex: 2, color: T.text }]}>{sub.email || sub.user_id}</Text>
              <Text style={[s.td, { flex: 1.5 }]}>{sub.plan_name || sub.plan_id || tx('admin.subscriptionDashboard.common.na', 'N/A')}</Text>
              <View style={{ flex: 1 }}>
                <View style={[s.badge, { backgroundColor: sub.status === 'active' ? (globalThis as any).__alphaColor(T.success, '20') : T.error + '20' }]}>
                  <Text style={{ color: sub.status === 'active' ? T.success : T.error, fontSize: 10, fontWeight: '700' }}>
                    {(sub.status || tx('admin.subscriptionDashboard.common.na', 'N/A')).toUpperCase()}
                  </Text>
                </View>
              </View>
              <Text style={[s.td, { flex: 1.5 }]}>{sub.created_at ? new Date(sub.created_at).toLocaleDateString() : tx('admin.subscriptionDashboard.common.na', 'N/A')}</Text>
            </View>
          ))}
          {subs.length === 0 && <Text style={{ color: T.textMuted, textAlign: 'center', padding: 40 }}>{tx('admin.subscriptionDashboard.subscribers.noSubscribersFound', 'No subscribers found')}</Text>}

          {/* Pagination */}
          {subPages > 1 && (
            <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 8, marginTop: 16 }}>
              <TouchableOpacity onPress={() => setSubPage(Math.max(1, subPage - 1))} style={s.pageBtn}>
                <Ionicons name="chevron-back" size={16} color={T.text} />
              </TouchableOpacity>
              <Text style={{ color: T.text, alignSelf: 'center' }}>{subPage} / {subPages}</Text>
              <TouchableOpacity onPress={() => setSubPage(Math.min(subPages, subPage + 1))} style={s.pageBtn}>
                <Ionicons name="chevron-forward" size={16} color={T.text} />
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}
    </ScrollView>
  );
}