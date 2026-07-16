import React, { useEffect, useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';

function makeC(AC: any) { return {
  ...AC,
  bg: AC.bg,
  card: AC.card,
  card2: AC.cardSoft,
  border: AC.border,
  text: AC.text,
  muted: AC.textDim,
  sec: AC.textSec,
  green: AC.success,
  red: AC.error,
  blue: AC.primary,
  yellow: AC.warning,
  purple: AC.purple,
  cyan: AC.info,
  orange: AC.orange,
  orangeText: AC.orangeText,
  indigo: AC.indigo,
  lime: AC.successText,
  teal: AC.teal,
  pink: AC.errorText,
  accent: AC.info,
}; }

// Theme-aware palette bound to --app-* CSS vars so module-scope helpers
// (KPICard, HEALTH_MAP, STATUS_MAP) render correctly without needing
// component-tree access. State colors (green/red/yellow/orange) stay
// semantic.
const C = {
  indigoText: 'var(--app-primary)',
  purpleText: 'var(--app-info)',
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  card2: 'var(--app-surface)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  muted: 'var(--app-text-muted)' as any,
  sec: 'var(--app-text-sec)' as any,
  green: 'var(--app-success)' as any,
  red: 'var(--app-error)' as any,
  blue: 'var(--app-primary)' as any,
  yellow: 'var(--app-warning)' as any,
  purple: 'var(--app-primary)' as any,
  cyan: 'var(--app-info)' as any,
  orange: 'var(--app-warning)' as any,
  orangeText: 'var(--app-warning)' as any,
  indigo: 'var(--app-primary)' as any,
  lime: 'var(--app-success)' as any,
  teal: 'var(--app-primary)' as any,
  pink: 'var(--app-error)' as any,
  accent: 'var(--app-info)' as any,
};

const HEALTH_MAP: Record<string, { color: string; icon: string }> = {
  healthy:  { color: C.green,  icon: 'shield-checkmark' },
  degraded: { color: C.yellow, icon: 'warning' },
  critical: { color: C.red,    icon: 'alert-circle' },
  idle:     { color: C.muted,  icon: 'moon' },
};

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  sent:         { color: C.green,  label: 'Delivered' },
  failed:       { color: C.red,    label: 'Failed' },
  rate_limited: { color: C.orangeText, label: 'Rate Limited' },
};

/* ── KPI Card ── */
function KPICard({ icon, label, value, sub, color, trend }: {
  icon: string; label: string; value: string | number; sub?: string; color: string; trend?: string;
}) {
  return (
    <View data-testid={`kpi-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`kpi-${label.toLowerCase().replace(/\s/g, '-')}`}
      style={{ flex: 1, minWidth: 150, backgroundColor: C.card, borderRadius: 16, padding: 18, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '20') }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(color, '15'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={18} color={color} />
        </View>
        {trend && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2, backgroundColor: (globalThis as any).__alphaColor((trend.startsWith('+') ? C.green : trend.startsWith('-') ? C.red : C.muted), '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 }}>
            <Ionicons name={trend.startsWith('+') ? 'trending-up' : trend.startsWith('-') ? 'trending-down' : 'remove'} size={10} color={trend.startsWith('+') ? C.green : trend.startsWith('-') ? C.red : C.muted} />
            <Text style={{ fontSize: 10, fontWeight: '700', color: trend.startsWith('+') ? C.green : trend.startsWith('-') ? C.red : C.muted }}>{trend}</Text>
          </View>
        )}
      </View>
      <Text style={{ fontSize: 28, fontWeight: '800', color, letterSpacing: -0.5 }}>{value}</Text>
      <Text style={{ fontSize: 11, fontWeight: '600', color: C.text, marginTop: 4 }}>{label}</Text>
      {sub && <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{sub}</Text>}
    </View>
  );
}

/* ── Health Status Badge ── */
function HealthBadge({ health }: { health: string }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const h = HEALTH_MAP[health] || HEALTH_MAP.idle;
  const labels: Record<string, string> = {
    healthy: tx('otpDashboard.health.healthy', 'Healthy'),
    degraded: tx('otpDashboard.health.degraded', 'Degraded'),
    critical: tx('otpDashboard.health.critical', 'Critical'),
    idle: tx('otpDashboard.health.idle', 'Idle'),
  };
  return (
    <View data-testid="otp-health-badge" testID="otp-health-badge" style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: (globalThis as any).__alphaColor(h.color, '12'), paddingHorizontal: 14, paddingVertical: 8, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(h.color, '25') }}>
      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: h.color }} />
      <Ionicons name={h.icon as any} size={16} color={h.color} />
      <Text style={{ fontSize: 12, fontWeight: '700', color: h.color }}>{labels[health] || labels.idle}</Text>
    </View>
  );
}

/* ── Bar Chart (Trend) ── */
function TrendChart({ data, height = 120 }: { data: any[]; height?: number }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  if (!data?.length) return <Text style={{ color: C.muted, fontSize: 12, textAlign: 'center', padding: 20 }}>{tx('otpDashboard.trend.noData', 'No trend data yet')}</Text>;
  const maxVal = Math.max(...data.map(d => Math.max(d.generated, d.sent + d.failed)), 1);
  return (
    <View data-testid="otp-trend-chart" testID="otp-trend-chart">
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height, paddingTop: 8 }}>
        {data.map((d, i) => {
          const genH = (d.generated / maxVal) * (height - 20);
          const sentH = (d.sent / maxVal) * (height - 20);
          const failH = (d.failed / maxVal) * (height - 20);
          return (
            <View key={i} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
              {d.generated > 0 && <Text style={{ fontSize: 7, color: C.muted, marginBottom: 2 }}>{d.generated}</Text>}
              <View style={{ width: '70%', gap: 1 }}>
                <View style={{ height: Math.max(genH, d.generated > 0 ? 3 : 0), backgroundColor: C.blue, borderRadius: 2 }} />
                <View style={{ height: Math.max(sentH, d.sent > 0 ? 3 : 0), backgroundColor: C.green, borderRadius: 2 }} />
                {failH > 0 && <View style={{ height: Math.max(failH, 3), backgroundColor: C.red, borderRadius: 2 }} />}
              </View>
            </View>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', gap: 2, marginTop: 6 }}>
        {data.map((d, i) => (
          <View key={i} style={{ flex: 1, alignItems: 'center' }}>
            <Text style={{ fontSize: 7, color: C.muted }}>{d.date?.slice(5)}</Text>
          </View>
        ))}
      </View>
      <View style={{ flexDirection: 'row', gap: 16, marginTop: 10, justifyContent: 'center' }}>
        {[
          { c: C.blue, l: tx('otpDashboard.legend.generated', 'Generated') },
          { c: C.green, l: tx('otpDashboard.legend.delivered', 'Delivered') },
          { c: C.red, l: tx('otpDashboard.legend.failed', 'Failed') },
        ].map(x => (
          <View key={x.l} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: x.c }} />
            <Text style={{ fontSize: 9, color: C.muted }}>{x.l}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ── Hourly Heatmap ── */
function HourlyHeatmap({ data }: { data: any[] }) {
  const colors = useAdminTheme();
  if (!data?.length) return null;
  const maxVal = Math.max(...data.map(d => d.sent + d.failed), 1);
  return (
    <View data-testid="otp-hourly-heatmap" testID="otp-hourly-heatmap">
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 3 }}>
        {data.map((d, i) => {
          const total = d.sent + d.failed;
          const intensity = total / maxVal;
          const bgColor = total === 0 ? C.border : d.failed > 0 ? C.red : intensity > 0.7 ? C.green : intensity > 0.3 ? C.blue : C.cyan;
          const opacity = total === 0 ? 0.3 : 0.3 + intensity * 0.7;
          return (
            <View key={i} style={{ width: 28, height: 28, borderRadius: 6, backgroundColor: bgColor, opacity, alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ fontSize: 7, fontWeight: '700', color: colors.primaryText }}>{d.hour?.slice(0, 2)}</Text>
              {total > 0 && <Text style={{ fontSize: 6, color: colors.primaryText, opacity: 0.8 }}>{total}</Text>}
            </View>
          );
        })}
      </View>
    </View>
  );
}

/* ── Time Window Card ── */
function TimeWindowCard({ label, data, color }: { label: string; data: any; color: string }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  return (
    <View style={{ flex: 1, minWidth: 130, backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}>
      <Text style={{ fontSize: 11, fontWeight: '600', color: C.muted, marginBottom: 10 }}>{label}</Text>
      <Text style={{ fontSize: 24, fontWeight: '800', color, letterSpacing: -0.5 }}>{data?.rate ?? 0}%</Text>
      <View style={{ height: 4, backgroundColor: C.border, borderRadius: 2, marginTop: 8, overflow: 'hidden' }}>
        <View style={{ width: `${data?.rate ?? 0}%`, height: '100%', backgroundColor: color, borderRadius: 2 }} />
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
        <Text style={{ fontSize: 10, color: C.green }}>{tx('otpDashboard.window.sentWithCount', '{count} sent').replace('{count}', String(data?.sent ?? 0))}</Text>
        <Text style={{ fontSize: 10, color: C.red }}>{tx('otpDashboard.window.failWithCount', '{count} fail').replace('{count}', String(data?.failed ?? 0))}</Text>
      </View>
    </View>
  );
}

/* ── Purpose Badge ── */
function PurposeBadge({ purpose, count, maxCount }: { purpose: string; count: number; maxCount: number }) {
  const colors: Record<string, string> = { '2fa': C.blue, login: C.purple, password_reset: C.orange, verify: C.accent };
  const color = colors[purpose] || C.indigo;
  const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
  return (
    <View style={{ marginBottom: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />
          <Text style={{ fontSize: 11, fontWeight: '600', color: C.text, textTransform: 'capitalize' }}>{purpose.replace(/_/g, ' ')}</Text>
        </View>
        <Text style={{ fontSize: 11, fontWeight: '700', color }}>{count}</Text>
      </View>
      <View style={{ height: 5, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
        <View style={{ width: `${pct}%`, height: '100%', backgroundColor: color, borderRadius: 3 }} />
      </View>
    </View>
  );
}

/* ── Status Pill ── */
function StatusPill({ status }: { status: string }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const statusLabels: Record<string, string> = {
    sent: tx('otpDashboard.status.delivered', 'Delivered'),
    failed: tx('otpDashboard.status.failed', 'Failed'),
    rate_limited: tx('otpDashboard.status.rateLimited', 'Rate Limited'),
  };
  const s = STATUS_MAP[status] || { color: C.muted, label: status };
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(s.color, '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 }}>
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: s.color }} />
      <Text style={{ fontSize: 10, fontWeight: '600', color: s.color }}>{statusLabels[status] || s.label}</Text>
    </View>
  );
}

/* ══════════════════ MAIN PANEL ══════════════════ */
export default function OTPDeliveryDashboardPanel({ colors }: { colors?: any }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isWide = width > 900;

  const [tab, setTab] = useState<'overview' | 'logs' | 'hourly' | 'webhook'>('overview');
  const [logs, setLogs] = useState<any[]>([]);
  const [logMeta, setLogMeta] = useState<any>({ total: 0, page: 1, pages: 1 });
  const [logPage, setLogPage] = useState(1);
  const [logFilter, setLogFilter] = useState('');
  const [logStatus, setLogStatus] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const { data: stats, loading } = useLiveQuery('/otp-analytics/stats?days=30', { entity: 'otp', pollInterval: 30000 });
  const { data: health } = useLiveQuery('/otp-analytics/health', { entity: 'otp', pollInterval: 30000 });
  const { data: trendsData } = useLiveQuery('/otp-analytics/trends?days=14', { entity: 'otp', pollInterval: 60000 });
  const { data: hourlyData } = useLiveQuery('/otp-analytics/hourly', { entity: 'otp', pollInterval: 60000 });
  const { data: webhookStats } = useLiveQuery('/webhooks/resend/stats?days=30', { entity: 'otp', pollInterval: 60000 });
  const { data: whEventsData } = useLiveQuery('/webhooks/resend/events?limit=50', { entity: 'otp', pollInterval: 30000 });

  const trends = trendsData?.trends || [];
  const hourly = hourlyData?.hours || [];
  const webhookEvents = whEventsData?.events || [];

  const loadLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams({ page: String(logPage), limit: '20' });
      if (logFilter) params.set('email', logFilter);
      if (logStatus) params.set('status', logStatus);
      const r = await api.get(`/otp-analytics/logs?${params}`);
      setLogs(r.data?.logs || []);
      setLogMeta({ total: r.data?.total || 0, page: r.data?.page || 1, pages: r.data?.pages || 1 });
    } catch (e) { console.error('OTP logs error:', e); }
  }, [logPage, logFilter, logStatus]);

  useEffect(() => { if (tab === 'logs') loadLogs(); }, [tab, loadLogs]);

  const handleRefresh = async () => {
    setRefreshing(true);
    if (tab === 'logs') await loadLogs();
    setRefreshing(false);
  };

  if (loading) return <ActivityIndicator color={C.cyan} style={{ padding: 60 }} />;

  const TABS = [
    { id: 'overview', label: tx('otpDashboard.tabs.overview', 'Overview'), icon: 'pulse' },
    { id: 'webhook', label: tx('otpDashboard.tabs.deliveryEvents', 'Delivery Events'), icon: 'checkmark-done-circle' },
    { id: 'logs', label: tx('otpDashboard.tabs.sendLogs', 'Send Logs'), icon: 'list' },
    { id: 'hourly', label: tx('otpDashboard.tabs.hourlyView', 'Hourly View'), icon: 'time' },
  ] as const;

  return (
    <View data-testid="otp-delivery-dashboard" testID="otp-delivery-dashboard">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.cyan, '15'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="mail-unread" size={22} color={C.cyan} />
          </View>
          <View>
            <Text style={{ fontSize: 20, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>{tx('otpDashboard.header.title', 'OTP Delivery Monitor')}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{tx('otpDashboard.header.subtitle', 'Real-time email OTP delivery tracking & analytics')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <HealthBadge health={health?.health || 'idle'} />
          <TouchableOpacity data-testid="otp-refresh-btn" testID="otp-refresh-btn" onPress={handleRefresh}
            style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: C.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border }}>
            {refreshing ? <ActivityIndicator size="small" color={C.cyan} /> : <Ionicons name="refresh" size={16} color={C.muted} />}
          </TouchableOpacity>
        </View>
      </View>

      {/* Tab Bar */}
      <View style={{ flexDirection: 'row', gap: 4, marginBottom: 20, backgroundColor: C.card, borderRadius: 12, padding: 4 }}>
        {TABS.map(t => (
          <TouchableOpacity key={t.id} data-testid={`otp-tab-${t.id}`} testID={`otp-tab-${t.id}`}
            onPress={() => setTab(t.id)}
            style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 10, backgroundColor: tab === t.id ? (globalThis as any).__alphaColor(C.cyan, '15') : 'transparent' }}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? C.cyan : C.muted} />
            <Text style={{ fontSize: 12, fontWeight: tab === t.id ? '700' : '500', color: tab === t.id ? C.cyan : C.muted }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ── OVERVIEW TAB ── */}
      {tab === 'overview' && (
        <View style={{ gap: 20 }}>
          {/* KPI Row */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            <KPICard icon="paper-plane" label={tx('otpDashboard.kpi.totalGenerated', 'Total Generated')} value={stats?.total_generated ?? 0} sub={tx('otpDashboard.kpi.lastDaysWithCount', 'Last {days} days').replace('{days}', String(stats?.window_days ?? 30))} color={C.blue} />
            <KPICard icon="checkmark-circle" label={tx('otpDashboard.kpi.delivered', 'Delivered')} value={stats?.total_sent ?? 0} sub={tx('otpDashboard.kpi.successfulSends', 'Successful sends')} color={C.green} />
            <KPICard icon="close-circle" label={tx('otpDashboard.kpi.failed', 'Failed')} value={stats?.total_failed ?? 0} sub={tx('otpDashboard.kpi.sendFailures', 'Send failures')} color={C.red} />
            <KPICard icon="speedometer" label={tx('otpDashboard.kpi.deliveryRate', 'Delivery Rate')} value={`${stats?.delivery_rate ?? 0}%`} sub={tx('otpDashboard.kpi.successPercentage', 'Success percentage')} color={stats?.delivery_rate >= 95 ? C.green : stats?.delivery_rate >= 80 ? C.yellow : C.red} />
          </View>

          {/* Second KPI Row */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            <KPICard icon="people" label={tx('otpDashboard.kpi.uniqueRecipients', 'Unique Recipients')} value={stats?.unique_recipients ?? 0} color={C.purpleText} />
            <KPICard icon="hand-left" label={tx('otpDashboard.kpi.rateLimited', 'Rate Limited')} value={stats?.total_rate_limited ?? 0} sub={tx('otpDashboard.kpi.throttledRequests', 'Throttled requests')} color={C.orangeText} />
          </View>

          {/* Health Windows */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Ionicons name="fitness" size={16} color={C.cyan} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.sections.systemHealthWindows', 'System Health Windows')}</Text>
            </View>
            <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12 }}>
              <TimeWindowCard label={tx('otpDashboard.windows.last1Hour', 'Last 1 Hour')} data={health?.windows?.['1h']} color={C.cyan} />
              <TimeWindowCard label={tx('otpDashboard.windows.last6Hours', 'Last 6 Hours')} data={health?.windows?.['6h']} color={C.blue} />
              <TimeWindowCard label={tx('otpDashboard.windows.last24Hours', 'Last 24 Hours')} data={health?.windows?.['24h']} color={C.indigoText} />
            </View>
            {health?.last_failure && (
              <View style={{ marginTop: 14, padding: 12, backgroundColor: (globalThis as any).__alphaColor(C.red, '08'), borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '15') }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <Ionicons name="warning" size={12} color={C.red} />
                  <Text style={{ fontSize: 11, fontWeight: '700', color: C.red }}>{tx('otpDashboard.lastFailure.title', 'Last Failure')}</Text>
                </View>
                <Text style={{ fontSize: 10, color: C.muted }}>{health.last_failure.email} — {health.last_failure.error}</Text>
                <Text style={{ fontSize: 9, color: C.sec, marginTop: 2 }}>{health.last_failure.created_at}</Text>
              </View>
            )}
          </View>

          {/* Trend Chart */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Ionicons name="trending-up" size={16} color={C.blue} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.sections.deliveryTrend14d', '14-Day Delivery Trend')}</Text>
            </View>
            <TrendChart data={trends} />
          </View>

          {/* Purpose Breakdown */}
          <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12 }}>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <Ionicons name="pie-chart" size={16} color={C.purpleText} />
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.sections.purposeBreakdown', 'OTP Purpose Breakdown')}</Text>
              </View>
              {stats?.purpose_breakdown && Object.keys(stats.purpose_breakdown).length > 0 ? (
                Object.entries(stats.purpose_breakdown).map(([purpose, count]) => (
                  <PurposeBadge key={purpose} purpose={purpose} count={count as number} maxCount={stats.total_generated} />
                ))
              ) : (
                <Text style={{ fontSize: 12, color: C.muted, textAlign: 'center', padding: 16 }}>{tx('otpDashboard.common.noData', 'No data available')}</Text>
              )}
            </View>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <Ionicons name="stats-chart" size={16} color={C.accent} />
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.sections.deliveryPipeline', 'Delivery Pipeline')}</Text>
              </View>
              {[
                { label: tx('otpDashboard.pipeline.generated', 'Generated'), value: stats?.total_generated ?? 0, color: C.blue, icon: 'paper-plane' },
                { label: tx('otpDashboard.pipeline.sentSuccessfully', 'Sent Successfully'), value: stats?.total_sent ?? 0, color: C.green, icon: 'checkmark-done' },
                { label: tx('otpDashboard.pipeline.failed', 'Failed'), value: stats?.total_failed ?? 0, color: C.red, icon: 'close' },
                { label: tx('otpDashboard.pipeline.rateLimited', 'Rate Limited'), value: stats?.total_rate_limited ?? 0, color: C.orangeText, icon: 'hand-left' },
              ].map((item, idx) => (
                <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: idx < 3 ? 1 : 0, borderBottomColor: C.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(item.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={item.icon as any} size={14} color={item.color} />
                    </View>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }}>{item.label}</Text>
                  </View>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: item.color }}>{item.value}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      )}

      {/* ── LOGS TAB ── */}
      {tab === 'logs' && (
        <View style={{ gap: 16 }}>
          {/* Filters */}
          <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 10 }}>
            <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: C.card, borderRadius: 10, paddingHorizontal: 12, borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="search" size={14} color={C.muted} />
              <TextInput
                data-testid="otp-log-search" testID="otp-log-search"
                value={logFilter}
                onChangeText={(v) => { setLogFilter(v); setLogPage(1); }}
                placeholder={tx('otpDashboard.logs.searchPlaceholder', 'Search by email...')}
                placeholderTextColor={C.muted}
                style={{ flex: 1, paddingVertical: 10, paddingHorizontal: 8, fontSize: 12, color: C.text }}
              />
            </View>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              {['', 'sent', 'failed', 'rate_limited'].map(s => (
                <TouchableOpacity key={s} data-testid={`otp-filter-${s || 'all'}`} testID={`otp-filter-${s || 'all'}`}
                  onPress={() => { setLogStatus(s); setLogPage(1); }}
                  style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: logStatus === s ? (globalThis as any).__alphaColor(C.cyan, '15') : C.card, borderWidth: 1, borderColor: logStatus === s ? (globalThis as any).__alphaColor(C.cyan, '30') : C.border }}>
                  <Text style={{ fontSize: 11, fontWeight: '600', color: logStatus === s ? C.cyan : C.muted }}>
                    {s ? (STATUS_MAP[s]?.label || s) : tx('otpDashboard.filters.all', 'All')}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Log count */}
          <Text style={{ fontSize: 11, color: C.muted }}>{tx('otpDashboard.logs.recordsPageWithValues', '{records} records — Page {page} of {pages}').replace('{records}', String(logMeta.total)).replace('{page}', String(logMeta.page)).replace('{pages}', String(logMeta.pages))}</Text>

          {/* Log Table */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor: C.border }}>
            {/* Header */}
            <View style={{ flexDirection: 'row', paddingHorizontal: 14, paddingVertical: 10, backgroundColor: C.card2, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ flex: 2, fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('otpDashboard.logs.columns.recipient', 'Recipient')}</Text>
              <Text style={{ flex: 2, fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('otpDashboard.logs.columns.subject', 'Subject')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('otpDashboard.logs.columns.status', 'Status')}</Text>
              <Text style={{ flex: 2, fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('otpDashboard.logs.columns.time', 'Time')}</Text>
            </View>
            {logs.length === 0 ? (
              <View style={{ padding: 30, alignItems: 'center' }}>
                <Ionicons name="file-tray-outline" size={28} color={C.muted} />
                <Text style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>{tx('otpDashboard.logs.empty', 'No OTP delivery logs found')}</Text>
              </View>
            ) : (
              logs.map((log, i) => (
                <View key={log.log_id || i} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 11, borderBottomWidth: i < logs.length - 1 ? 1 : 0, borderBottomColor: (globalThis as any).__alphaColor(C.border, '60') }}>
                  <View style={{ flex: 2 }}>
                    <Text style={{ fontSize: 11, fontWeight: '600', color: C.text }} numberOfLines={1}>{log.email}</Text>
                  </View>
                  <View style={{ flex: 2 }}>
                    <Text style={{ fontSize: 10, color: C.sec }} numberOfLines={1}>{log.subject}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <StatusPill status={log.status} />
                  </View>
                  <View style={{ flex: 2 }}>
                    <Text style={{ fontSize: 10, color: C.muted }}>{log.created_at ? new Date(log.created_at).toLocaleString() : '-'}</Text>
                    {log.error ? <Text style={{ fontSize: 9, color: C.red, marginTop: 1 }} numberOfLines={1}>{log.error}</Text> : null}
                  </View>
                </View>
              ))
            )}
          </View>

          {/* Pagination */}
          {logMeta.pages > 1 && (
            <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 8, marginTop: 4 }}>
              <TouchableOpacity data-testid="otp-log-prev" testID="otp-log-prev" onPress={() => setLogPage(p => Math.max(1, p - 1))} disabled={logPage <= 1}
                style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(logPage <= 1 ? C.border : C.cyan, '15') }}>
                <Text style={{ fontSize: 11, fontWeight: '600', color: logPage <= 1 ? C.muted : C.cyan }}>{tx('otpDashboard.pagination.previous', 'Previous')}</Text>
              </TouchableOpacity>
              <View style={{ paddingHorizontal: 14, paddingVertical: 8 }}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{logMeta.page} / {logMeta.pages}</Text>
              </View>
              <TouchableOpacity data-testid="otp-log-next" testID="otp-log-next" onPress={() => setLogPage(p => Math.min(logMeta.pages, p + 1))} disabled={logPage >= logMeta.pages}
                style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(logPage >= logMeta.pages ? C.border : C.cyan, '15') }}>
                <Text style={{ fontSize: 11, fontWeight: '600', color: logPage >= logMeta.pages ? C.muted : C.cyan }}>{tx('otpDashboard.pagination.next', 'Next')}</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}

      {/* ── HOURLY TAB ── */}
      {tab === 'hourly' && (
        <View style={{ gap: 16 }}>
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Ionicons name="time" size={16} color={C.cyan} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.sections.hourlyHeatmap', '24-Hour OTP Volume Heatmap')}</Text>
            </View>
            <HourlyHeatmap data={hourly} />
            <View style={{ flexDirection: 'row', gap: 16, marginTop: 12, justifyContent: 'center' }}>
              {[{ c: C.green, l: tx('otpDashboard.hourly.sent', 'Sent') }, { c: C.red, l: tx('otpDashboard.hourly.failed', 'Failed') }, { c: C.border, l: tx('otpDashboard.hourly.noActivity', 'No Activity') }].map(x => (
                <View key={x.l} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: x.c }} />
                  <Text style={{ fontSize: 10, color: C.muted }}>{x.l}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Hourly table */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', paddingHorizontal: 14, paddingVertical: 10, backgroundColor: C.card2, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase' }}>{tx('otpDashboard.hourly.columns.hour', 'Hour')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', textAlign: 'center' }}>{tx('otpDashboard.hourly.columns.sent', 'Sent')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', textAlign: 'center' }}>{tx('otpDashboard.hourly.columns.failed', 'Failed')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', textAlign: 'center' }}>{tx('otpDashboard.hourly.columns.total', 'Total')}</Text>
            </View>
            {hourly.filter(h => h.sent > 0 || h.failed > 0).length === 0 ? (
              <View style={{ padding: 24, alignItems: 'center' }}>
                <Text style={{ fontSize: 12, color: C.muted }}>{tx('otpDashboard.hourly.empty', 'No hourly activity in the last 24h')}</Text>
              </View>
            ) : (
              hourly.filter(h => h.sent > 0 || h.failed > 0).map((h, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '40') }}>
                  <Text style={{ flex: 1, fontSize: 12, fontWeight: '600', color: C.text }}>{h.hour}</Text>
                  <Text style={{ flex: 1, fontSize: 12, fontWeight: '700', color: C.green, textAlign: 'center' }}>{h.sent}</Text>
                  <Text style={{ flex: 1, fontSize: 12, fontWeight: '700', color: h.failed > 0 ? C.red : C.muted, textAlign: 'center' }}>{h.failed}</Text>
                  <Text style={{ flex: 1, fontSize: 12, fontWeight: '700', color: C.text, textAlign: 'center' }}>{h.sent + h.failed}</Text>
                </View>
              ))
            )}
          </View>
        </View>
      )}

      {/* ── WEBHOOK / DELIVERY EVENTS TAB ── */}
      {tab === 'webhook' && (
        <View data-testid="otp-webhook-tab" testID="otp-webhook-tab" style={{ gap: 16 }}>
          {/* Webhook KPIs */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            <KPICard icon="checkmark-done-circle" label={tx('otpDashboard.webhook.confirmedDelivered', 'Confirmed Delivered')} value={webhookStats?.delivered ?? 0} color={C.green} sub={tx('otpDashboard.webhook.resendConfirmed', 'Resend webhook confirmed')} />
            <KPICard icon="arrow-undo-circle" label={tx('otpDashboard.webhook.bounced', 'Bounced')} value={webhookStats?.bounced ?? 0} color={C.red} sub={tx('otpDashboard.webhook.undeliverable', 'Undeliverable')} />
            <KPICard icon="eye" label={tx('otpDashboard.webhook.opened', 'Opened')} value={webhookStats?.opened ?? 0} color={C.purpleText} sub={tx('otpDashboard.webhook.recipientOpened', 'Recipient opened email')} />
            <KPICard icon="megaphone" label={tx('otpDashboard.webhook.complaints', 'Complaints')} value={webhookStats?.complained ?? 0} color={C.orangeText} sub={tx('otpDashboard.webhook.markedSpam', 'Marked as spam')} />
          </View>

          {/* Rates Row */}
          <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12 }}>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Ionicons name="analytics" size={16} color={C.green} />
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.webhook.deliveryConfirmationRate', 'Delivery Confirmation Rate')}</Text>
              </View>
              <Text style={{ fontSize: 36, fontWeight: '800', color: C.green, letterSpacing: -1 }}>{webhookStats?.delivery_rate ?? 0}%</Text>
              <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3, marginTop: 10, overflow: 'hidden' }}>
                <View style={{ width: `${webhookStats?.delivery_rate ?? 0}%`, height: '100%', backgroundColor: C.green, borderRadius: 3 }} />
              </View>
              <Text style={{ fontSize: 10, color: C.muted, marginTop: 6 }}>{tx('otpDashboard.webhook.eventsConfirmedWithValues', '{delivered} of {total} events confirmed').replace('{delivered}', String(webhookStats?.delivered ?? 0)).replace('{total}', String(webhookStats?.total_events ?? 0))}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Ionicons name="eye" size={16} color={C.purpleText} />
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.webhook.openRate', 'Open Rate')}</Text>
              </View>
              <Text style={{ fontSize: 36, fontWeight: '800', color: C.purpleText, letterSpacing: -1 }}>{webhookStats?.open_rate ?? 0}%</Text>
              <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3, marginTop: 10, overflow: 'hidden' }}>
                <View style={{ width: `${webhookStats?.open_rate ?? 0}%`, height: '100%', backgroundColor: C.purple, borderRadius: 3 }} />
              </View>
              <Text style={{ fontSize: 10, color: C.muted, marginTop: 6 }}>{tx('otpDashboard.webhook.openedDeliveredWithValues', '{opened} opened of {delivered} delivered').replace('{opened}', String(webhookStats?.opened ?? 0)).replace('{delivered}', String(webhookStats?.delivered ?? 0))}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Ionicons name="alert-circle" size={16} color={C.red} />
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.webhook.bounceRate', 'Bounce Rate')}</Text>
              </View>
              <Text style={{ fontSize: 36, fontWeight: '800', color: (webhookStats?.bounce_rate ?? 0) > 5 ? C.red : C.green, letterSpacing: -1 }}>{webhookStats?.bounce_rate ?? 0}%</Text>
              <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3, marginTop: 10, overflow: 'hidden' }}>
                <View style={{ width: `${webhookStats?.bounce_rate ?? 0}%`, height: '100%', backgroundColor: C.red, borderRadius: 3 }} />
              </View>
              <Text style={{ fontSize: 10, color: C.muted, marginTop: 6 }}>{tx('otpDashboard.webhook.bouncedEventsWithValues', '{bounced} bounced of {total} events').replace('{bounced}', String(webhookStats?.bounced ?? 0)).replace('{total}', String(webhookStats?.total_events ?? 0))}</Text>
            </View>
          </View>

          {/* Event Timeline */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Ionicons name="git-branch" size={16} color={C.cyan} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('otpDashboard.webhook.deliveryEventTimeline', 'Delivery Event Timeline')}</Text>
              <View style={{ marginLeft: 'auto', backgroundColor: (globalThis as any).__alphaColor(C.cyan, '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 }}>
                <Text style={{ fontSize: 10, fontWeight: '700', color: C.cyan }}>{tx('otpDashboard.webhook.eventsWithCount', '{count} events').replace('{count}', String(webhookEvents.length))}</Text>
              </View>
            </View>
            {webhookEvents.length === 0 ? (
              <View style={{ padding: 30, alignItems: 'center' }}>
                <Ionicons name="cloud-offline" size={28} color={C.muted} />
                <Text style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>{tx('otpDashboard.webhook.noEventsYet', 'No webhook events received yet')}</Text>
                <Text style={{ fontSize: 10, color: C.sec, marginTop: 4, textAlign: 'center' }}>{tx('otpDashboard.webhook.configureResendUrl', 'Configure your Resend webhook URL to start receiving delivery events')}</Text>
              </View>
            ) : (
              webhookEvents.map((evt: any, i: number) => {
                const evtColor = evt.internal_status === 'delivered' ? C.green : evt.internal_status === 'bounced' ? C.red : evt.internal_status === 'opened' ? C.purple : evt.internal_status === 'complained' ? C.orange : evt.internal_status === 'clicked' ? C.accent : C.blue;
                const evtIcon = evt.internal_status === 'delivered' ? 'checkmark-circle' : evt.internal_status === 'bounced' ? 'arrow-undo-circle' : evt.internal_status === 'opened' ? 'eye' : evt.internal_status === 'complained' ? 'megaphone' : evt.internal_status === 'clicked' ? 'hand-left' : 'paper-plane';
                return (
                  <View key={evt.email_id + '-' + i} style={{ flexDirection: 'row', gap: 12 }}>
                    <View style={{ alignItems: 'center', width: 28 }}>
                      <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(evtColor, '15'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={evtIcon as any} size={14} color={evtColor} />
                      </View>
                      {i < webhookEvents.length - 1 && <View style={{ width: 2, flex: 1, backgroundColor: C.border, minHeight: 16 }} />}
                    </View>
                    <View style={{ flex: 1, paddingBottom: 14 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <Text style={{ fontSize: 11, fontWeight: '700', color: evtColor, textTransform: 'capitalize' }}>{evt.internal_status}</Text>
                        <Text style={{ fontSize: 9, color: C.muted }}>{evt.event_type}</Text>
                      </View>
                      <Text style={{ fontSize: 11, color: C.text }}>{evt.recipient}</Text>
                      {evt.subject ? <Text style={{ fontSize: 10, color: C.sec, marginTop: 1 }} numberOfLines={1}>{evt.subject}</Text> : null}
                      <Text style={{ fontSize: 9, color: C.muted, marginTop: 3 }}>{evt.created_at ? new Date(evt.created_at).toLocaleString() : '-'}</Text>
                    </View>
                  </View>
                );
              })
            )}
          </View>
        </View>
      )}

    </View>
  );
}