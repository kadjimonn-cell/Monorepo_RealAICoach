import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, useWindowDimensions, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

function makeT(AC: any) {
  return {
    bg: AC.bg,
    card: AC.cardMuted || AC.card,
    border: AC.border,
    text: AC.text,
    textMuted: AC.textMuted,
    textDim: AC.textDim,
    accent: AC.primary,
    success: AC.success,
    warning: AC.warning,
    danger: AC.error,
    good: AC.success,
    warn: AC.warning,
    critical: AC.error,
  };
}

const tx = (_key: string, fallback: string) => fallback;

const PERIODS = [
  { id: '1h', label: '1H' }, { id: '6h', label: '6H' }, { id: '24h', label: '24H' },
  { id: '7d', label: '7D' }, { id: '30d', label: '30D' },
];

function KPICard({ label, value, unit, icon, color, subtitle, T }: any) {
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, flex: 1, minWidth: 150 }} data-testid={`page-perf-kpi-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`page-perf-kpi-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Ionicons name={icon} size={18} color={color} />
        <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '500' }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 26, fontWeight: '700', letterSpacing: -0.5 }}>
        {value}<Text style={{ fontSize: 13, color: T.textMuted, fontWeight: '400' }}>{unit}</Text>
      </Text>
      {subtitle && <Text style={{ color: T.textDim, fontSize: 11, marginTop: 4 }}>{subtitle}</Text>}
    </View>
  );
}

function StatusBadge({ status, T }: { status: string; T: any }) {
  const config: any = {
    good: { bg: 'var(--app-success-soft)', color: T.good, label: 'OK' },
    warning: { bg: 'var(--app-warning-soft)', color: T.warn, label: 'WARN' },
    critical: { bg: 'var(--app-error-soft)', color: T.critical, label: 'SLOW' },
  };
  const c = config[status] || config.good;
  return (
    <View style={{ backgroundColor: c.bg, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
      <Text style={{ color: c.color, fontSize: 10, fontWeight: '700' }}>{c.label}</Text>
    </View>
  );
}

function BarChart({ data, maxVal, color, label, T }: any) {
  const max = maxVal || Math.max(...data.map((d: any) => d.value), 1);
  return (
    <View style={{ gap: 2, flex: 1 }}>
      <Text style={{ color: T.textMuted, fontSize: 10, marginBottom: 4, fontWeight: '500' }}>{label}</Text>
      <View style={{ flexDirection: 'row', gap: 2, alignItems: 'flex-end', height: 80 }}>
        {data.slice(-30).map((d: any, i: number) => (
          <View
            key={i}
            style={{
              flex: 1, minWidth: 3, maxWidth: 16,
              height: Math.max(2, (d.value / max) * 80),
              backgroundColor: d.value > 1000 ? T.critical : d.value > 600 ? T.warn : color,
              borderRadius: 2,
              opacity: 0.85,
            }}
          />
        ))}
      </View>
    </View>
  );
}

function HeatmapRow({ page, avg_ms, p95_ms, count, violations, violation_pct, status, skeleton, T }: any) {
  const barWidth = Math.min(100, (avg_ms / 1200) * 100);
  const barColor = status === 'critical' ? T.critical : status === 'warning' ? T.warn : T.good;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: T.border }}>
      <View style={{ flex: 3, minWidth: 160 }}>
        <Text style={{ color: T.text, fontSize: 13, fontWeight: '500' }} numberOfLines={1}>{page}</Text>
        {skeleton ? <Text style={{ color: T.textDim, fontSize: 10 }}>{skeleton}</Text> : null}
      </View>
      <View style={{ flex: 2, paddingHorizontal: 8 }}>
        <View style={{ height: 8, backgroundColor: T.border, borderRadius: 4, overflow: 'hidden' }}>
          <View style={{ width: `${barWidth}%`, height: '100%', backgroundColor: barColor, borderRadius: 4 }} />
        </View>
        <Text style={{ color: barColor, fontSize: 11, fontWeight: '600', marginTop: 2 }}>{avg_ms}ms</Text>
      </View>
      <View style={{ flex: 1, alignItems: 'center' }}>
        <Text style={{ color: T.textMuted, fontSize: 12 }}>{p95_ms}ms</Text>
      </View>
      <View style={{ flex: 1, alignItems: 'center' }}>
        <Text style={{ color: T.textMuted, fontSize: 12 }}>{count}</Text>
      </View>
      <View style={{ flex: 1, alignItems: 'center' }}>
        <Text style={{ color: violations > 0 ? T.danger : T.good, fontSize: 12, fontWeight: violations > 0 ? '600' : '400' }}>
          {violations > 0 ? `${violations} (${violation_pct}%)` : '0'}
        </Text>
      </View>
      <View style={{ width: 60, alignItems: 'flex-end' }}>
        <StatusBadge status={status} T={T} />
      </View>
    </View>
  );
}

export default function PagePerformancePanel({ colors }: { colors?: any }) {
  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('24h');
  const [data, setData] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'overview' | 'pages' | 'alerts' | 'timeline' | 'autofix'>('overview');
  const [autofixLogs, setAutofixLogs] = useState<any[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, alertRes, autofixRes] = await Promise.all([
        api.get(`/admin/page-performance/dashboard?period=${period}`),
        api.get('/admin/page-performance/alerts'),
        api.get('/admin/page-performance/autofix-log'),
      ]);
      if (dashRes.data?.ok) setData(dashRes.data);
      if (alertRes.data?.ok) setAlerts(alertRes.data.alerts || []);
      if (autofixRes.data?.ok) setAutofixLogs(autofixRes.data.logs || []);
    } catch (e) {
      console.error('Page perf fetch error:', e);
    }
    setLoading(false);
  }, [period]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const tabs = [
    { id: 'overview', label: tx('admin.pagePerformance.tabs.overview', 'Overview'), icon: 'speedometer' },
    { id: 'pages', label: tx('admin.pagePerformance.tabs.pageHeatmap', 'Page Heatmap'), icon: 'grid' },
    { id: 'alerts', label: tx('admin.pagePerformance.tabs.alertsWithCount', 'Alerts{count}').replace('{count}', alerts.length > 0 ? ` (${alerts.length})` : ''), icon: 'warning' },
    { id: 'timeline', label: tx('admin.pagePerformance.tabs.timeline', 'Timeline'), icon: 'trending-up' },
    { id: 'autofix', label: tx('admin.pagePerformance.tabs.autoFixLogWithCount', 'Auto-Fix Log{count}').replace('{count}', autofixLogs.length > 0 ? ` (${autofixLogs.length})` : ''), icon: 'construct' },
  ];

  if (loading && !data) {
    return (
      <View style={{ padding: 40, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={T.accent} />
        <Text style={{ color: T.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.pagePerformance.states.loading', 'Loading performance data...')}</Text>
      </View>
    );
  }

  const kpis = data?.kpis || {};
  const pages = data?.pages || [];
  const timeline = data?.timeline || [];

  return (
    <View style={{ flex: 1 }} data-testid="page-performance-panel" testID="page-performance-panel">
      {/* Header */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', justifyContent: 'space-between', alignItems: isWide ? 'center' : 'flex-start', marginBottom: 20, gap: 12 }}>
        <View>
          <Text style={{ color: T.text, fontSize: 22, fontWeight: '700', letterSpacing: -0.3 }}>
            {tx('admin.pagePerformance.header.title', 'Page Performance Monitor')}
          </Text>
          <Text style={{ color: T.textMuted, fontSize: 13, marginTop: 2 }}>
            {tx('admin.pagePerformance.header.subtitleWithCount', 'Real-time skeleton-to-content transition tracking across {count} pages').replace('{count}', String(kpis.unique_pages || 0))}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
          {/* Period selector */}
          {PERIODS.map(p => (
            <TouchableOpacity accessibilityLabel={tx('admin.pagePerformancePanel.auto.accessibility.001', 'Set performance time period')}
              key={p.id}
              onPress={() => setPeriod(p.id)}
              style={{
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
                backgroundColor: period === p.id ? T.accent : T.card,
                borderWidth: 1, borderColor: period === p.id ? T.accent : T.border,
              }}
              data-testid={`page-perf-period-${p.id}`} testID={`page-perf-period-${p.id}`}
            >
              <Text style={{ color: period === p.id ? 'var(--app-primary-text)' : T.textMuted, fontSize: 12, fontWeight: '600' }}>{p.label}</Text>
            </TouchableOpacity>
          ))}
          {/* Refresh */}
          <TouchableOpacity onPress={fetchData} style={{ padding: 8 }} data-testid="page-perf-refresh" testID="page-perf-refresh">
            <Ionicons name="refresh" size={18} color={T.textMuted} />
          </TouchableOpacity>
        </View>
      </View>

      {/* KPI Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 20 }} data-testid="page-perf-kpis" testID="page-perf-kpis">
        <KPICard label={tx('admin.pagePerformance.kpi.avgLoad', 'Avg Load')} value={kpis.avg_ms || 0} unit="ms" icon="speedometer" color={kpis.avg_ms > 1000 ? T.danger : kpis.avg_ms > 600 ? T.warn : T.good} subtitle={tx('admin.pagePerformance.kpi.targetThreshold', 'Target: <{threshold}ms').replace('{threshold}', String(kpis.threshold_ms || 0))} T={T} />
        <KPICard label={tx('admin.pagePerformance.kpi.p95Load', 'P95 Load')} value={kpis.p95_ms || 0} unit="ms" icon="trending-up" color={kpis.p95_ms > 1000 ? T.danger : T.warn} subtitle={tx('admin.pagePerformance.kpi.p95Subtitle', '95th percentile')} T={T} />
        <KPICard label={tx('admin.pagePerformance.kpi.totalLoads', 'Total Loads')} value={kpis.total_loads || 0} unit="" icon="layers" color={T.accent} subtitle={tx('admin.pagePerformance.kpi.uniquePagesWithCount', '{count} unique pages').replace('{count}', String(kpis.unique_pages || 0))} T={T} />
        <KPICard label={tx('admin.pagePerformance.kpi.violations', 'Violations')} value={kpis.total_violations || 0} unit="" icon="alert-circle" color={kpis.total_violations > 0 ? T.danger : T.good} subtitle={tx('admin.pagePerformance.kpi.violationRateWithValue', '{value}% of loads').replace('{value}', String(kpis.violation_pct || 0))} T={T} />
      </View>

      {/* Health bar */}
      <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, marginBottom: 20, flexDirection: 'row', alignItems: 'center', gap: 12 }} data-testid="page-perf-health-bar" testID="page-perf-health-bar">
        <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: kpis.avg_ms <= 600 ? T.good : kpis.avg_ms <= 1000 ? T.warn : T.danger }} />
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '600' }}>
          {tx('admin.pagePerformance.health.platformHealthWithStatus', 'Platform Health: {status}').replace('{status}', kpis.avg_ms <= 600 ? tx('admin.pagePerformance.health.excellent', 'Excellent') : kpis.avg_ms <= 1000 ? tx('admin.pagePerformance.health.good', 'Good') : tx('admin.pagePerformance.health.needsAttention', 'Needs Attention'))}
        </Text>
        <Text style={{ color: T.textMuted, fontSize: 12, flex: 1, textAlign: 'right' }}>
          {tx('admin.pagePerformance.health.summaryWithValues', '{loads} page loads in period | {good}/{total} pages under threshold')
            .replace('{loads}', String(kpis.total_loads || 0))
            .replace('{good}', String(pages.filter((p: any) => p.status === 'good').length))
            .replace('{total}', String(pages.length))}
        </Text>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 4, marginBottom: 16 }}>
        {tabs.map(tab => (
          <TouchableOpacity accessibilityLabel={tx('admin.pagePerformancePanel.auto.accessibility.002', 'Switch performance metric tab')}
            key={tab.id}
            onPress={() => setActiveTab(tab.id as any)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
              backgroundColor: activeTab === tab.id ? (globalThis as any).__alphaColor(T.accent, '20') : 'transparent',
              borderWidth: 1, borderColor: activeTab === tab.id ? (globalThis as any).__alphaColor(T.accent, '40') : 'transparent',
            }}
            data-testid={`page-perf-tab-${tab.id}`} testID={`page-perf-tab-${tab.id}`}
          >
            <Ionicons name={tab.icon as any} size={14} color={activeTab === tab.id ? T.accent : T.textMuted} />
            <Text style={{ color: activeTab === tab.id ? T.accent : T.textMuted, fontSize: 12, fontWeight: '600' }}>{tab.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Tab content */}
      {activeTab === 'overview' && (
        <View style={{ gap: 16 }}>
          {/* Quick summary cards */}
          <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12 }}>
            {/* Fastest pages */}
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Ionicons name="flash" size={16} color={T.good} />
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '600' }}>{tx('admin.pagePerformancePanel.auto.text.001', 'Fastest Pages')}</Text>
              </View>
              {pages.filter((p: any) => p.status === 'good').slice(0, 5).map((p: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: i < 4 ? 1 : 0, borderBottomColor: T.border }}>
                  <Text style={{ color: T.textMuted, fontSize: 12 }} numberOfLines={1}>{p.page}</Text>
                  <Text style={{ color: T.good, fontSize: 12, fontWeight: '600' }}>{p.avg_ms}ms</Text>
                </View>
              ))}
              {pages.filter((p: any) => p.status === 'good').length === 0 && (
                <Text style={{ color: T.textDim, fontSize: 12, fontStyle: 'italic' }}>{tx('admin.pagePerformancePanel.auto.text.002', 'No data yet. Navigate pages to collect metrics.')}</Text>
              )}
            </View>

            {/* Slowest pages */}
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Ionicons name="hourglass" size={16} color={T.danger} />
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '600' }}>{tx('admin.pagePerformancePanel.auto.text.003', 'Slowest Pages')}</Text>
              </View>
              {pages.filter((p: any) => p.status !== 'good').slice(0, 5).map((p: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: i < 4 ? 1 : 0, borderBottomColor: T.border }}>
                  <Text style={{ color: T.textMuted, fontSize: 12 }} numberOfLines={1}>{p.page}</Text>
                  <Text style={{ color: p.status === 'critical' ? T.danger : T.warn, fontSize: 12, fontWeight: '600' }}>{p.avg_ms}ms</Text>
                </View>
              ))}
              {pages.filter((p: any) => p.status !== 'good').length === 0 && (
                <Text style={{ color: T.good, fontSize: 12 }}>{tx('admin.pagePerformancePanel.auto.text.004', 'All pages are within the 1-second threshold!')}</Text>
              )}
            </View>
          </View>

          {/* Timeline mini */}
          {timeline.length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Ionicons name="analytics" size={16} color={T.accent} />
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '600' }}>{tx('admin.pagePerformancePanel.auto.text.005', 'Load Time Trend')}</Text>
                <View style={{ flex: 1 }} />
                <Text style={{ color: T.textDim, fontSize: 11 }}>{tx('admin.pagePerformancePanel.auto.text.006', 'Avg ms per hour')}</Text>
              </View>
              <BarChart
                data={timeline.map((t: any) => ({ value: t.avg_ms, label: t.time }))}
                color={T.accent}
                label=""
                T={T}
              />
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
                <Text style={{ color: T.textDim, fontSize: 10 }}>
                  {timeline[0]?.time ? new Date(timeline[0].time).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                </Text>
                <View style={{ height: 1, flex: 1, backgroundColor: T.border, alignSelf: 'center', marginHorizontal: 8 }} />
                <Text style={{ color: T.textDim, fontSize: 10 }}>
                  {timeline[timeline.length - 1]?.time ? new Date(timeline[timeline.length - 1].time).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                </Text>
              </View>
            </View>
          )}
        </View>
      )}

      {activeTab === 'pages' && (
        <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }} data-testid="page-perf-heatmap" testID="page-perf-heatmap">
          {/* Table header */}
          <View style={{ flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: 2, borderBottomColor: T.border, backgroundColor: T.bg }}>
            <Text style={{ flex: 3, color: T.textMuted, fontSize: 11, fontWeight: '600', minWidth: 160 }}>{tx('admin.pagePerformancePanel.auto.text.007', 'PAGE')}</Text>
            <Text style={{ flex: 2, color: T.textMuted, fontSize: 11, fontWeight: '600', paddingHorizontal: 8 }}>{tx('admin.pagePerformancePanel.auto.text.008', 'AVG LOAD')}</Text>
            <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '600', textAlign: 'center' }}>P95</Text>
            <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '600', textAlign: 'center' }}>{tx('admin.pagePerformancePanel.auto.text.009', 'LOADS')}</Text>
            <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '600', textAlign: 'center' }}>{tx('admin.pagePerformancePanel.auto.text.010', 'VIOLATIONS')}</Text>
            <Text style={{ width: 60, color: T.textMuted, fontSize: 11, fontWeight: '600', textAlign: 'right' }}>{tx('admin.pagePerformancePanel.auto.text.011', 'STATUS')}</Text>
          </View>
          {pages.length > 0 ? pages.map((p: any, i: number) => (
            <HeatmapRow key={i} {...p} T={T} />
          )) : (
            <View style={{ padding: 40, alignItems: 'center' }}>
              <Ionicons name="analytics-outline" size={40} color={T.textDim} />
              <Text style={{ color: T.textDim, fontSize: 14, marginTop: 12 }}>{tx('admin.pagePerformancePanel.auto.text.012', 'No page performance data yet')}</Text>
              <Text style={{ color: T.textDim, fontSize: 12, marginTop: 4 }}>{tx('admin.pagePerformancePanel.auto.text.013', 'Navigate through the platform to collect metrics')}</Text>
            </View>
          )}
        </View>
      )}

      {activeTab === 'alerts' && (
        <View style={{ gap: 10 }} data-testid="page-perf-alerts" testID="page-perf-alerts">
          {alerts.length === 0 ? (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 40, borderWidth: 1, borderColor: T.border, alignItems: 'center' }}>
              <Ionicons name="checkmark-circle" size={48} color={T.good} />
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '600', marginTop: 12 }}>{tx('admin.pagePerformancePanel.auto.text.014', 'All Clear')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 13, marginTop: 4 }}>No pages are exceeding the {(kpis.threshold_ms || 1000)}ms threshold</Text>
            </View>
          ) : (
            alerts.map((a: any, i: number) => (
              <View key={i} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: a.severity === 'critical' ? (globalThis as any).__alphaColor(T.danger, '40') : T.warn + '40', borderLeftWidth: 4, borderLeftColor: a.severity === 'critical' ? T.danger : T.warn }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="alert-circle" size={16} color={a.severity === 'critical' ? T.danger : T.warn} />
                    <Text style={{ color: T.text, fontSize: 14, fontWeight: '600' }}>{a.page}</Text>
                  </View>
                  <View style={{ backgroundColor: a.severity === 'critical' ? (globalThis as any).__alphaColor(T.danger, '20') : T.warn + '20', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                    <Text style={{ color: a.severity === 'critical' ? T.danger : T.warn, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{a.severity}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', gap: 20 }}>
                  <View>
                    <Text style={{ color: T.textDim, fontSize: 11 }}>{tx('admin.pagePerformancePanel.auto.text.015', 'Avg Load')}</Text>
                    <Text style={{ color: T.danger, fontSize: 16, fontWeight: '700' }}>{a.avg_ms}ms</Text>
                  </View>
                  <View>
                    <Text style={{ color: T.textDim, fontSize: 11 }}>{tx('admin.pagePerformancePanel.auto.text.016', 'Peak')}</Text>
                    <Text style={{ color: T.warn, fontSize: 16, fontWeight: '700' }}>{a.max_ms}ms</Text>
                  </View>
                  <View>
                    <Text style={{ color: T.textDim, fontSize: 11 }}>{tx('admin.pagePerformancePanel.auto.text.017', 'Occurrences')}</Text>
                    <Text style={{ color: T.text, fontSize: 16, fontWeight: '700' }}>{a.count}</Text>
                  </View>
                </View>
              </View>
            ))
          )}
        </View>
      )}

      {activeTab === 'timeline' && (
        <View style={{ gap: 12 }} data-testid="page-perf-timeline" testID="page-perf-timeline">
          {timeline.length > 0 ? (
            <>
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '600', marginBottom: 12 }}>{tx('admin.pagePerformancePanel.auto.text.018', 'Average Load Time')}</Text>
                <BarChart data={timeline.map((t: any) => ({ value: t.avg_ms }))} color={T.accent} label="Avg (ms)" T={T} />
              </View>
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '600', marginBottom: 12 }}>{tx('admin.pagePerformancePanel.auto.text.019', 'Page Loads per Hour')}</Text>
                <BarChart data={timeline.map((t: any) => ({ value: t.count }))} color={T.good} label="Loads" T={T} />
              </View>
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '600', marginBottom: 12 }}>{tx('admin.pagePerformancePanel.auto.text.020', 'Threshold Violations')}</Text>
                <BarChart data={timeline.map((t: any) => ({ value: t.violations }))} color={T.danger} label="Violations" T={T} />
              </View>
            </>
          ) : (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 40, borderWidth: 1, borderColor: T.border, alignItems: 'center' }}>
              <Ionicons name="analytics-outline" size={40} color={T.textDim} />
              <Text style={{ color: T.textDim, fontSize: 14, marginTop: 12 }}>{tx('admin.pagePerformancePanel.auto.text.021', 'No timeline data yet')}</Text>
              <Text style={{ color: T.textDim, fontSize: 12, marginTop: 4 }}>{tx('admin.pagePerformancePanel.auto.text.022', 'Data will appear as users navigate the platform')}</Text>
            </View>
          )}
        </View>
      )}

      {activeTab === 'autofix' && (
        <View style={{ gap: 10 }} data-testid="page-perf-autofix-log" testID="page-perf-autofix-log">
          {autofixLogs.length === 0 ? (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 40, borderWidth: 1, borderColor: T.border, alignItems: 'center' }}>
              <Ionicons name="shield-checkmark" size={48} color={T.good} />
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '600', marginTop: 12 }}>{tx('admin.pagePerformancePanel.auto.text.023', 'No Auto-Fixes Applied')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 13, marginTop: 4, textAlign: 'center' }}>{tx('admin.pagePerformancePanel.auto.text.024', 'The system monitors page performance hourly. When a regression is detected, it will automatically apply safe optimizations and log them here.')}</Text>
            </View>
          ) : (
            autofixLogs.map((log: any, i: number) => {
              const isRevert = log.status === 'reverted';
              const borderColor = isRevert ? T.accent + '40' : T.good + '40';
              const iconColor = isRevert ? T.accent : T.good;
              const iconName = isRevert ? 'arrow-undo' : 'construct';
              return (
                <View key={log.fix_id || i} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor, borderLeftWidth: 4, borderLeftColor: iconColor }} data-testid={`autofix-log-entry-${i}`} testID={`autofix-log-entry-${i}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Ionicons name={iconName as any} size={16} color={iconColor} />
                      <Text style={{ color: T.text, fontSize: 14, fontWeight: '600' }}>{log.page}</Text>
                    </View>
                    <View style={{ backgroundColor: isRevert ? (globalThis as any).__alphaColor(T.accent, '20') : T.good + '20', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                      <Text style={{ color: iconColor, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{log.status}</Text>
                    </View>
                  </View>
                  {!isRevert && (
                    <>
                      <View style={{ flexDirection: 'row', gap: 20, marginBottom: 10 }}>
                        <View>
                          <Text style={{ color: T.textDim, fontSize: 11 }}>{tx('admin.pagePerformancePanel.auto.text.025', 'Detected Avg')}</Text>
                          <Text style={{ color: T.danger, fontSize: 16, fontWeight: '700' }}>{log.avg_ms}ms</Text>
                        </View>
                        <View>
                          <Text style={{ color: T.textDim, fontSize: 11 }}>{tx('admin.pagePerformancePanel.auto.text.026', '7-Day Baseline')}</Text>
                          <Text style={{ color: T.textMuted, fontSize: 16, fontWeight: '700' }}>{log.baseline_ms}ms</Text>
                        </View>
                        <View>
                          <Text style={{ color: T.textDim, fontSize: 11 }}>{tx('admin.pagePerformancePanel.auto.text.027', 'Spike Ratio')}</Text>
                          <Text style={{ color: T.warn, fontSize: 16, fontWeight: '700' }}>{log.spike_ratio}x</Text>
                        </View>
                        <View>
                          <Text style={{ color: T.textDim, fontSize: 11 }}>{tx('admin.pagePerformancePanel.auto.text.028', 'Fixes Applied')}</Text>
                          <Text style={{ color: T.good, fontSize: 16, fontWeight: '700' }}>{log.fix_count}</Text>
                        </View>
                      </View>
                      {log.fixes_applied && log.fixes_applied.length > 0 && (
                        <View style={{ backgroundColor: T.bg, borderRadius: 10, padding: 12, gap: 6 }}>
                          {log.fixes_applied.map((fix: any, fi: number) => (
                            <View key={fi} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                              <Ionicons name="checkmark-circle" size={14} color={T.good} />
                              <Text style={{ color: T.textMuted, fontSize: 12 }}>
                                {fix.action.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
                              </Text>
                            </View>
                          ))}
                        </View>
                      )}
                    </>
                  )}
                  {log.timestamp && (
                    <Text style={{ color: T.textDim, fontSize: 11, marginTop: 8 }}>
                      {new Date(log.timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </Text>
                  )}
                </View>
              );
            })
          )}
        </View>
      )}
    </View>
  );
}
