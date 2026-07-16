import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import AutoFixBanner from './AutoFixBanner';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
interface Props { colors: any; }

interface Summary {
  last_24h: { issues: number; fixes: number; runs: number; active_domains: number };
  last_7d: { issues: number; fixes: number; runs: number; active_domains: number };
  domain_health: { healthy: number; warning: number; critical: number };
  total_domains: number;
}

interface Hotspot {
  domain: string;
  issues: number;
  fixes: number;
  runs: number;
  last_run: string | null;
  fix_rate: number;
}

interface RecentEvent {
  domain: string;
  action: string;
  issues_found: number;
  fixes_applied: number;
  timestamp: string;
  status: string;
}

interface TrendPoint { day: string; issues: number; fixes: number; runs: number; }

const tx = (_key: string, fallback: string) => fallback;

export default function AnomalyDetectionPanel({ colors }: Props) {
  const s = StyleSheet.create({
    tab: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, borderWidth: 1 },
    metricCard: { minWidth: 150, flex: 1, padding: 16, borderRadius: 12, borderWidth: 1 },
    iconCircle: { width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center' },
    card: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 16 },
    dot: { width: 8, height: 8, borderRadius: 4 },
    liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success },
    eventRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1 },
    periodBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6, borderWidth: 1 },
    toggle: { width: 44, height: 24, borderRadius: 12, justifyContent: 'center', padding: 2 },
    toggleDot: { width: 20, height: 20, borderRadius: 10, backgroundColor: colors.primaryText },
    settingRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1 },
    thresholdInput: { fontSize: 14, fontWeight: '700', textAlign: 'center', width: 80, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1 },
  });

  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [hotspots, setHotspots] = useState<Hotspot[]>([]);
  const [events, setEvents] = useState<RecentEvent[]>([]);
  const [trends, setTrends] = useState<Record<string, TrendPoint[]>>({});
  const [alertConfig, setAlertConfig] = useState<any>(null);
  const [alertHistory, setAlertHistory] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [activeView, setActiveView] = useState<'overview' | 'hotspots' | 'events' | 'trends' | 'alerts'>('overview');
  const [trendDays, setTrendDays] = useState(7);

  const C = useMemo(() => ({
    ...colors,
    bg: AC.card,
    text: AC.text,
    muted: AC.textMuted,
    border: AC.borderStrong || colors.borderStrong,
    primary: colors.primary,
    success: colors.success,
    warning: colors.warning,
    danger: colors.error,
    accent: colors.info,
    surface: colors.surface || AC.bgAlt,
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [colors]);

  const [loading, setLoading] = useState(true);
  const panelTitle = t('anomalyDetection.header.title');

  const loadData = useCallback(async () => {
    try {
      const [summaryRes, hotspotsRes, eventsRes, trendsRes, configRes, historyRes] = await Promise.all([
        api.get('/admin/anomaly-detection/summary'),
        api.get('/admin/anomaly-detection/hotspots'),
        api.get('/admin/anomaly-detection/recent-events?limit=50'),
        api.get(`/admin/anomaly-detection/trends?days=${trendDays}`),
        api.get('/admin/anomaly-detection/alert-config'),
        api.get('/admin/anomaly-detection/alert-history?limit=15'),
      ]);
      setSummary(summaryRes.data);
      setHotspots(hotspotsRes.data.hotspots || []);
      setEvents(eventsRes.data.events || []);
      setTrends(trendsRes.data.trends || {});
      setAlertConfig(configRes.data.config || {});
      setAlertHistory(historyRes.data.history || []);
    } catch (err) {
      console.error('Failed to load anomaly data:', err);
    } finally {
      setLoading(false);
    }
  }, [trendDays]);

  useEffect(() => { loadData(); }, [loadData]);
  useAutoRefresh(loadData, { intervalMs: 15000 });

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator size="large" color={C.primary} />
      <Text style={{ color: C.muted, marginTop: 12, fontSize: 13 }}>{tx('anomalyDetection.states.loading', 'Loading anomaly data...')}</Text>
    </View>
  );

  const views = [
    { id: 'overview' as const, label: tx('anomalyDetection.views.overview', 'Overview'), icon: 'grid' },
    { id: 'hotspots' as const, label: tx('anomalyDetection.views.hotspots', 'Hotspots'), icon: 'flame' },
    { id: 'events' as const, label: tx('anomalyDetection.views.liveEvents', 'Live Events'), icon: 'pulse' },
    { id: 'trends' as const, label: tx('anomalyDetection.views.trends', 'Trends'), icon: 'trending-up' },
    { id: 'alerts' as const, label: tx('anomalyDetection.views.alertSettings', 'Alert Settings'), icon: 'notifications' },
  ];

  const healthPct = summary ? Math.round((summary.domain_health.healthy / summary.total_domains) * 100) : 0;
  const fixRate = summary && summary.last_24h.issues > 0
    ? Math.round((summary.last_24h.fixes / summary.last_24h.issues) * 100)
    : 100;

  return (
    <ScrollView style={{ flex: 1, padding: 16 }}>
      <AutoFixBanner domain="anomaly_detection" />

      {/* Header */}
      <View style={{ marginBottom: 20 }} data-testid="anomaly-detection-header" testID="anomaly-detection-header">
        <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, letterSpacing: -0.5 }}>
          {panelTitle === 'anomalyDetection.header.title' ? 'Anomaly Detection' : panelTitle}
        </Text>
        <Text style={{ fontSize: 13, color: C.muted, marginTop: 4 }}>
          {tx('anomalyDetection.header.subtitle', 'Real-time pattern analysis across {count} platform domains').replace('{count}', String(summary?.total_domains || 50))}
        </Text>
      </View>

      {/* View Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20, flexWrap: 'wrap' }}>
        {views.map(v => (
          <TouchableOpacity accessibilityLabel={tx('admin.anomalyDetectionPanel.auto.accessibility.001', 'Switch anomaly view tab')}
            key={v.id}
            onPress={() => setActiveView(v.id)}
            style={[s.tab, {
              backgroundColor: activeView === v.id ? C.primary : C.bg,
              borderColor: activeView === v.id ? C.primary : C.border,
            }]}
            data-testid={`anomaly-tab-${v.id}`} testID={`anomaly-tab-${v.id}`}
          >
            <Ionicons name={v.icon as any} size={14} color={activeView === v.id ? C.primaryText : C.muted} />
            <Text style={{ fontSize: 12, fontWeight: '600', color: activeView === v.id ? C.primaryText : C.text, marginLeft: 6 }}>
              {v.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {activeView === 'overview' && (
        <OverviewSection summary={summary} healthPct={healthPct} fixRate={fixRate} C={C} />
      )}
      {activeView === 'hotspots' && (
        <HotspotsSection hotspots={hotspots} C={C} />
      )}
      {activeView === 'events' && (
        <EventsSection events={events} C={C} />
      )}
      {activeView === 'trends' && (
        <TrendsSection trends={trends} trendDays={trendDays} setTrendDays={setTrendDays} C={C} />
      )}
      {activeView === 'alerts' && (
        <AlertsSection config={alertConfig} history={alertHistory} saving={saving} setSaving={setSaving} setConfig={setAlertConfig} reload={loadData} C={C} />
      )}
    </ScrollView>
  );
}

/* ── Overview ── */
function OverviewSection({ summary, healthPct, fixRate, C }: { summary: Summary | null; healthPct: number; fixRate: number; C: any }) {
  const colors = useAdminTheme();
  if (!summary) return null;

  const cards = [
    { label: 'Issues (24h)', value: summary.last_24h.issues, icon: 'alert-circle', color: summary.last_24h.issues > 0 ? C.warning : C.success },
    { label: 'Fixes (24h)', value: summary.last_24h.fixes, icon: 'checkmark-circle', color: C.successText },
    { label: 'Fix Rate', value: `${fixRate}%`, icon: 'shield-checkmark', color: fixRate >= 90 ? C.success : fixRate >= 70 ? C.warning : C.danger },
    { label: 'Sweeps (24h)', value: summary.last_24h.runs, icon: 'refresh-circle', color: C.primary },
    { label: 'Active Domains', value: summary.last_24h.active_domains, icon: 'earth', color: C.accent },
    { label: 'Platform Health', value: `${healthPct}%`, icon: 'pulse', color: healthPct >= 90 ? C.success : healthPct >= 70 ? C.warning : C.danger },
  ];

  return (
    <View data-testid="anomaly-overview" testID="anomaly-overview">
      {/* Metric Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }}>
        {cards.map((c, i) => (
          <View key={i} style={[s.metricCard, { backgroundColor: C.bg, borderColor: C.border }]} data-testid={`metric-${c.label.replace(/\s+/g, '-').toLowerCase()}`} testID={`metric-${c.label.replace(/\s+/g, '-').toLowerCase()}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
              <View style={[s.iconCircle, { backgroundColor: (globalThis as any).__alphaColor(c.color, '20') }]}>
                <Ionicons name={c.icon as any} size={16} color={c.color} />
              </View>
              <Text style={{ fontSize: 11, color: C.muted, marginLeft: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>{c.label}</Text>
            </View>
            <Text style={{ fontSize: 28, fontWeight: '800', color: C.text }}>{c.value}</Text>
          </View>
        ))}
      </View>

      {/* Domain Health Bar */}
      <View style={[s.card, { backgroundColor: C.bg, borderColor: C.border }]} data-testid="domain-health-bar" testID="domain-health-bar">
        <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.anomalyDetectionPanel.auto.text.001', 'Domain Health Distribution')}</Text>
        <View style={{ flexDirection: 'row', height: 28, borderRadius: 14, overflow: 'hidden', backgroundColor: C.surface }}>
          {summary.domain_health.healthy > 0 && (
            <View style={{ flex: summary.domain_health.healthy, backgroundColor: C.success, justifyContent: 'center', alignItems: 'center' }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primaryText }}>{summary.domain_health.healthy} Healthy</Text>
            </View>
          )}
          {summary.domain_health.warning > 0 && (
            <View style={{ flex: summary.domain_health.warning, backgroundColor: C.warning, justifyContent: 'center', alignItems: 'center' }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primaryText }}>{summary.domain_health.warning} Warning</Text>
            </View>
          )}
          {summary.domain_health.critical > 0 && (
            <View style={{ flex: summary.domain_health.critical, backgroundColor: C.danger, justifyContent: 'center', alignItems: 'center' }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primaryText }}>{summary.domain_health.critical} Critical</Text>
            </View>
          )}
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
          <Text style={{ fontSize: 11, color: C.muted }}>7-day issues: {summary.last_7d.issues}</Text>
          <Text style={{ fontSize: 11, color: C.muted }}>7-day fixes: {summary.last_7d.fixes}</Text>
          <Text style={{ fontSize: 11, color: C.muted }}>7-day sweeps: {summary.last_7d.runs}</Text>
        </View>
      </View>
    </View>
  );
}

/* ── Hotspots ── */
function HotspotsSection({ hotspots, C }: { hotspots: Hotspot[]; C: any }) {
  return (
    <View data-testid="anomaly-hotspots" testID="anomaly-hotspots">
      <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.anomalyDetectionPanel.auto.text.002', 'Top Issue Domains (Last 24h)')}</Text>
      {hotspots.length === 0 && (
        <View style={[s.card, { backgroundColor: C.bg, borderColor: C.border, alignItems: 'center', padding: 32 }]}>
          <Ionicons name="shield-checkmark" size={36} color={C.successText} />
          <Text style={{ fontSize: 14, fontWeight: '600', color: C.text, marginTop: 12 }}>{tx('admin.anomalyDetectionPanel.auto.text.003', 'All Clear')}</Text>
          <Text style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>{tx('admin.anomalyDetectionPanel.auto.text.004', 'No anomalies detected in the last 24 hours')}</Text>
        </View>
      )}
      {hotspots.map((h, i) => {
        const severity = h.issues === 0 ? 'healthy' : h.issues <= 3 ? 'low' : h.issues <= 10 ? 'medium' : 'high';
        const severityColor = severity === 'healthy' ? C.success : severity === 'low' ? C.primary : severity === 'medium' ? C.warning : C.danger;
        return (
          <View key={h.domain} style={[s.card, { backgroundColor: C.bg, borderColor: C.border, marginBottom: 8 }]} data-testid={`hotspot-${h.domain}`} testID={`hotspot-${h.domain}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
                <Text style={{ fontSize: 13, color: C.muted, width: 24 }}>#{i + 1}</Text>
                <View style={[s.dot, { backgroundColor: severityColor }]} />
                <Text style={{ fontSize: 13, fontWeight: '600', color: C.text, marginLeft: 8 }}>{h.domain.replace(/_/g, ' ')}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 16 }}>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: h.issues > 0 ? C.warning : C.success }}>{h.issues}</Text>
                  <Text style={{ fontSize: 9, color: C.muted, textTransform: 'uppercase' }}>{tx('admin.anomalyDetectionPanel.auto.text.005', 'Issues')}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: C.successText }}>{h.fixes}</Text>
                  <Text style={{ fontSize: 9, color: C.muted, textTransform: 'uppercase' }}>{tx('admin.anomalyDetectionPanel.auto.text.006', 'Fixes')}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: h.fix_rate >= 90 ? C.success : h.fix_rate >= 50 ? C.warning : C.danger }}>{h.fix_rate}%</Text>
                  <Text style={{ fontSize: 9, color: C.muted, textTransform: 'uppercase' }}>{tx('admin.anomalyDetectionPanel.auto.text.007', 'Fix Rate')}</Text>
                </View>
              </View>
            </View>
            {/* Mini progress bar */}
            <View style={{ marginTop: 8, height: 4, borderRadius: 2, backgroundColor: C.surface, overflow: 'hidden' }}>
              <View style={{ width: `${Math.min(h.fix_rate, 100)}%`, height: '100%', backgroundColor: h.fix_rate >= 90 ? C.success : h.fix_rate >= 50 ? C.warning : C.danger, borderRadius: 2 }} />
            </View>
          </View>
        );
      })}
    </View>
  );
}

/* ── Live Events ── */
function EventsSection({ events, C }: { events: RecentEvent[]; C: any }) {
  const timeAgo = (ts: string) => {
    const diff = Date.now() - new Date(ts).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  return (
    <View data-testid="anomaly-events" testID="anomaly-events">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.anomalyDetectionPanel.auto.text.008', 'Recent Auto-Fix Events')}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(C.success, '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 }}>
          <View style={[s.liveDot]} />
          <Text style={{ fontSize: 10, fontWeight: '700', color: C.successText }}>{tx('admin.anomalyDetectionPanel.auto.text.009', 'LIVE')}</Text>
        </View>
      </View>
      {events.slice(0, 25).map((e, i) => (
        <View key={i} style={[s.eventRow, { borderColor: C.border }]} data-testid={`event-${i}`} testID={`event-${i}`}>
          <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
            <Ionicons
              name={e.issues_found > 0 ? (e.fixes_applied > 0 ? 'checkmark-circle' : 'alert-circle') : 'ellipse-outline'}
              size={14}
              color={e.issues_found > 0 ? (e.fixes_applied > 0 ? C.success : C.warning) : C.muted}
            />
            <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginLeft: 8 }}>{e.domain?.replace(/_/g, ' ')}</Text>
            <Text style={{ fontSize: 11, color: C.accent, marginLeft: 8 }}>{e.action?.replace(/_/g, ' ')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
            {e.issues_found > 0 && <Text style={{ fontSize: 11, color: C.warningText }}>{e.issues_found} issues</Text>}
            {e.fixes_applied > 0 && <Text style={{ fontSize: 11, color: C.successText }}>{e.fixes_applied} fixed</Text>}
            <Text style={{ fontSize: 10, color: C.muted }}>{e.timestamp ? timeAgo(e.timestamp) : ''}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

/* ── Trends ── */
function TrendsSection({ trends, trendDays, setTrendDays, C }: { trends: Record<string, TrendPoint[]>; trendDays: number; setTrendDays: (n: number) => void; C: any }) {
  const periods = [3, 7, 14, 30];

  // Aggregate all domains into a daily summary
  const dailyTotals = useMemo(() => {
    const byDay: Record<string, { issues: number; fixes: number; runs: number }> = {};
    Object.values(trends).forEach(pts => {
      pts.forEach(p => {
        if (!byDay[p.day]) byDay[p.day] = { issues: 0, fixes: 0, runs: 0 };
        byDay[p.day].issues += p.issues;
        byDay[p.day].fixes += p.fixes;
        byDay[p.day].runs += p.runs;
      });
    });
    return Object.entries(byDay).sort(([a], [b]) => a.localeCompare(b)).map(([day, data]) => ({ day, ...data }));
  }, [trends]);

  const maxIssues = Math.max(...dailyTotals.map(d => d.issues), 1);

  // Top movers: domains with the most issues in the period
  const topMovers = useMemo(() => {
    return Object.entries(trends)
      .map(([domain, pts]) => ({
        domain,
        totalIssues: pts.reduce((s, p) => s + p.issues, 0),
        totalFixes: pts.reduce((s, p) => s + p.fixes, 0),
      }))
      .sort((a, b) => b.totalIssues - a.totalIssues)
      .slice(0, 8);
  }, [trends]);

  return (
    <View data-testid="anomaly-trends" testID="anomaly-trends">
      {/* Period selector */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.anomalyDetectionPanel.auto.text.010', 'Issue Trends')}</Text>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {periods.map(p => (
            <TouchableOpacity
              key={p}
              onPress={() => setTrendDays(p)}
              style={[s.periodBtn, { backgroundColor: trendDays === p ? C.primary : C.bg, borderColor: trendDays === p ? C.primary : C.border }]}
              data-testid={`trend-period-${p}d`} testID={`trend-period-${p}d`}
            >
              <Text style={{ fontSize: 11, fontWeight: '600', color: trendDays === p ? C.primaryText : C.muted }}>{p}d</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Bar Chart */}
      <View style={[s.card, { backgroundColor: C.bg, borderColor: C.border, marginBottom: 16 }]}>
        <Text style={{ fontSize: 12, fontWeight: '600', color: C.muted, marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.anomalyDetectionPanel.auto.text.011', 'Daily Issues & Fixes')}</Text>
        {dailyTotals.length === 0 ? (
          <Text style={{ fontSize: 12, color: C.muted, textAlign: 'center', padding: 20 }}>{tx('admin.anomalyDetectionPanel.auto.text.012', 'No data for this period')}</Text>
        ) : (
          <View style={{ gap: 6 }}>
            {dailyTotals.map((d, i) => (
              <View key={d.day} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={{ fontSize: 10, color: C.muted, width: 55, textAlign: 'right' }}>{d.day.slice(5)}</Text>
                <View style={{ flex: 1, height: 20, flexDirection: 'row', gap: 2 }}>
                  <View style={{ width: `${(d.issues / maxIssues) * 100}%`, height: '100%', backgroundColor: (globalThis as any).__alphaColor(C.warning, '80'), borderRadius: 3, minWidth: d.issues > 0 ? 4 : 0 }} />
                  <View style={{ width: `${(d.fixes / maxIssues) * 100}%`, height: '100%', backgroundColor: (globalThis as any).__alphaColor(C.success, '80'), borderRadius: 3, minWidth: d.fixes > 0 ? 4 : 0 }} />
                </View>
                <Text style={{ fontSize: 10, color: C.muted, width: 55 }}>{d.issues}i / {d.fixes}f</Text>
              </View>
            ))}
          </View>
        )}
        <View style={{ flexDirection: 'row', gap: 16, marginTop: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(C.warning, '80') }} />
            <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.anomalyDetectionPanel.auto.text.013', 'Issues')}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(C.success, '80') }} />
            <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.anomalyDetectionPanel.auto.text.014', 'Fixes')}</Text>
          </View>
        </View>
      </View>

      {/* Top Movers */}
      <View style={[s.card, { backgroundColor: C.bg, borderColor: C.border }]}>
        <Text style={{ fontSize: 12, fontWeight: '600', color: C.muted, marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          Top Movers ({trendDays}d)
        </Text>
        {topMovers.map((m, i) => (
          <View key={m.domain} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6, borderBottomWidth: i < topMovers.length - 1 ? 1 : 0, borderBottomColor: C.border }}>
            <Text style={{ fontSize: 12, color: C.text, fontWeight: '500' }}>{m.domain.replace(/_/g, ' ')}</Text>
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <Text style={{ fontSize: 12, color: C.warningText, fontWeight: '600' }}>{m.totalIssues} issues</Text>
              <Text style={{ fontSize: 12, color: C.successText, fontWeight: '600' }}>{m.totalFixes} fixes</Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ── Alert Settings ── */
function AlertsSection({ config, history, saving, setSaving, setConfig, reload, C }: {
  config: any; history: any[]; saving: boolean; setSaving: (b: boolean) => void;
  setConfig: (c: any) => void; reload: () => void; C: any;
}) {
  const colors = useAdminTheme();
  const [localConfig, setLocalConfig] = useState(config || {});
  const [triggeringAutofix, setTriggeringAutofix] = useState(false);
  const [sendingTest, setSendingTest] = useState(false);

  useEffect(() => { if (config) setLocalConfig(config); }, [config]);

  const updateField = useCallback((key: string, value: any) => {
    setLocalConfig((prev: any) => ({ ...prev, [key]: value }));
  }, []);

  const saveConfig = useCallback(async () => {
    setSaving(true);
    try {
      await api.put('/admin/anomaly-detection/alert-config', localConfig);
      setConfig(localConfig);
    } catch (err) {
      console.error('Failed to save config:', err);
    } finally {
      setSaving(false);
    }
  }, [localConfig, setSaving, setConfig]);

  const triggerAutoFix = useCallback(async () => {
    setTriggeringAutofix(true);
    try {
      await api.post('/admin/anomaly-detection/trigger-autofix');
    } catch (err) {
      console.error('Failed to trigger auto-fix:', err);
    } finally {
      setTriggeringAutofix(false);
      reload();
    }
  }, [reload]);

  const sendTestDigest = useCallback(async () => {
    setSendingTest(true);
    try {
      await api.post('/admin/anomaly-detection/send-test-digest');
    } catch (err) {
      console.error('Failed to send test digest:', err);
    } finally {
      setSendingTest(false);
      reload();
    }
  }, [reload]);

  const timeAgo = (ts: string) => {
    const diff = Date.now() - new Date(ts).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  const Toggle = ({ value, onToggle, testId }: { value: boolean; onToggle: () => void; testId: string }) => (
    <TouchableOpacity
      onPress={onToggle}
      style={[s.toggle, { backgroundColor: value ? C.success : C.border }]}
      data-testid={testId} testID={testId}
    >
      <View style={[s.toggleDot, { alignSelf: value ? 'flex-end' : 'flex-start' }]} />
    </TouchableOpacity>
  );

  return (
    <View data-testid="anomaly-alerts-settings" testID="anomaly-alerts-settings">
      {/* Main Settings */}
      <View style={[s.card, { backgroundColor: C.bg, borderColor: C.border }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
          <Ionicons name="notifications" size={18} color={C.accent} />
          <Text style={{ fontSize: 15, fontWeight: '700', color: C.text, marginLeft: 8 }}>{tx('admin.anomalyDetectionPanel.auto.text.015', 'Alert Configuration')}</Text>
        </View>

        <View style={[s.settingRow, { borderBottomColor: C.border }]}>
          <View>
            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{tx('admin.anomalyDetectionPanel.auto.text.016', 'Enable Alerts')}</Text>
            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.anomalyDetectionPanel.auto.text.017', 'Master switch for all anomaly alerts')}</Text>
          </View>
          <Toggle value={localConfig.enabled} onToggle={() => updateField('enabled', !localConfig.enabled)} testId="toggle-alerts-enabled" />
        </View>

        <View style={[s.settingRow, { borderBottomColor: C.border }]}>
          <View>
            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{tx('admin.anomalyDetectionPanel.auto.text.018', 'Daily Digest')}</Text>
            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.anomalyDetectionPanel.auto.text.019', 'Send daily summary at 8 AM UTC')}</Text>
          </View>
          <Toggle value={localConfig.daily_digest} onToggle={() => updateField('daily_digest', !localConfig.daily_digest)} testId="toggle-daily-digest" />
        </View>

        <View style={[s.settingRow, { borderBottomColor: C.border }]}>
          <View>
            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{tx('admin.anomalyDetectionPanel.auto.text.020', 'Weekly Digest')}</Text>
            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.anomalyDetectionPanel.auto.text.021', 'Send weekly report every Monday 9 AM UTC')}</Text>
          </View>
          <Toggle value={localConfig.weekly_digest} onToggle={() => updateField('weekly_digest', !localConfig.weekly_digest)} testId="toggle-weekly-digest" />
        </View>

        <View style={[s.settingRow, { borderBottomColor: C.border }]}>
          <View>
            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{tx('admin.anomalyDetectionPanel.auto.text.022', 'Auto-Fix on Spike')}</Text>
            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.anomalyDetectionPanel.auto.text.023', 'Automatically trigger fix engine when spike detected')}</Text>
          </View>
          <Toggle value={localConfig.auto_fix_on_spike} onToggle={() => updateField('auto_fix_on_spike', !localConfig.auto_fix_on_spike)} testId="toggle-autofix-spike" />
        </View>
      </View>

      {/* Thresholds */}
      <View style={[s.card, { backgroundColor: C.bg, borderColor: C.border }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
          <Ionicons name="speedometer" size={18} color={C.warningText} />
          <Text style={{ fontSize: 15, fontWeight: '700', color: C.text, marginLeft: 8 }}>{tx('admin.anomalyDetectionPanel.auto.text.024', 'Thresholds')}</Text>
        </View>

        {[
          { key: 'spike_threshold', label: 'Spike Alert', desc: 'Issues per hour to trigger immediate alert', color: C.danger },
          { key: 'daily_threshold', label: 'Daily Digest', desc: 'Issues per 24h to flag in daily report', color: C.warningText },
          { key: 'weekly_threshold', label: 'Weekly Digest', desc: 'Issues per 7d to flag in weekly report', color: C.primary },
        ].map(t => (
          <View key={t.key} style={[s.settingRow, { borderBottomColor: C.border }]}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{t.label}</Text>
              <Text style={{ fontSize: 11, color: C.muted }}>{t.desc}</Text>
            </View>
            <View style={[s.thresholdInput, { borderColor: t.color, backgroundColor: (globalThis as any).__alphaColor(t.color, '15') }]}>
              <Text
                style={{ fontSize: 14, fontWeight: '700', color: t.color, textAlign: 'center' }}
                onPress={() => {
                  const val = prompt(`Set ${t.label} threshold:`, String(localConfig[t.key] || 0));
                  if (val && !isNaN(Number(val))) updateField(t.key, Number(val));
                }}
                data-testid={`threshold-${t.key}`} testID={`threshold-${t.key}`}
              >
                {localConfig[t.key] || 0}
              </Text>
            </View>
          </View>
        ))}
      </View>

      {/* Action Buttons */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <TouchableOpacity
          onPress={saveConfig}
          style={[s.tab, { backgroundColor: C.primary, borderColor: C.primary, opacity: saving ? 0.6 : 1 }]}
          disabled={saving}
          data-testid="save-alert-config" testID="save-alert-config"
        >
          <Ionicons name="save" size={14} color={C.primaryText} />
          <Text style={{ fontSize: 12, fontWeight: '600', color: colors.primaryText, marginLeft: 6 }}>{saving ? 'Saving...' : 'Save Configuration'}</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={triggerAutoFix}
          style={[s.tab, { backgroundColor: (globalThis as any).__alphaColor(C.success, '20'), borderColor: C.success }]}
          disabled={triggeringAutofix}
          data-testid="trigger-autofix-btn" testID="trigger-autofix-btn"
        >
          <Ionicons name="construct" size={14} color={C.successText} />
          <Text style={{ fontSize: 12, fontWeight: '600', color: C.successText, marginLeft: 6 }}>{triggeringAutofix ? 'Running...' : 'Trigger Auto-Fix Now'}</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={sendTestDigest}
          style={[s.tab, { backgroundColor: (globalThis as any).__alphaColor(C.accent, '20'), borderColor: C.accent }]}
          disabled={sendingTest}
          data-testid="send-test-digest-btn" testID="send-test-digest-btn"
        >
          <Ionicons name="mail" size={14} color={C.accent} />
          <Text style={{ fontSize: 12, fontWeight: '600', color: C.accent, marginLeft: 6 }}>{sendingTest ? 'Sending...' : 'Send Test Digest'}</Text>
        </TouchableOpacity>
      </View>

      {/* Alert History */}
      <View style={[s.card, { backgroundColor: C.bg, borderColor: C.border }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
          <Ionicons name="time" size={18} color={C.muted} />
          <Text style={{ fontSize: 15, fontWeight: '700', color: C.text, marginLeft: 8 }}>{t("securityDashboard.alertHistory.title")}</Text>
        </View>

        {history.length === 0 ? (
          <Text style={{ fontSize: 12, color: C.muted, textAlign: 'center', padding: 20 }}>{tx('admin.anomalyDetectionPanel.auto.text.025', 'No alerts sent yet')}</Text>
        ) : (
          history.map((h, i) => (
            <View key={i} style={[s.eventRow, { borderBottomColor: C.border }]} data-testid={`alert-history-${i}`} testID={`alert-history-${i}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
                <Ionicons
                  name={h.type === 'spike' ? 'flash' : h.type === 'daily' ? 'sunny' : 'calendar'}
                  size={14}
                  color={h.type === 'spike' ? C.danger : h.type === 'daily' ? C.warning : C.primary}
                />
                <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginLeft: 8, textTransform: 'capitalize' }}>{h.type}</Text>
                {h.auto_fix_triggered && (
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '30'), paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, marginLeft: 8 }}>
                    <Text style={{ fontSize: 9, fontWeight: '700', color: C.successText }}>{tx('admin.anomalyDetectionPanel.auto.text.026', 'AUTO-FIX')}</Text>
                  </View>
                )}
              </View>
              <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
                <Text style={{ fontSize: 11, color: C.warningText }}>{h.issues} issues</Text>
                <Text style={{ fontSize: 11, color: C.successText }}>{h.fixes} fixes</Text>
                <Text style={{ fontSize: 10, color: C.muted }}>{h.timestamp ? timeAgo(h.timestamp) : ''}</Text>
              </View>
            </View>
          ))
        )}
      </View>
    </View>
  );
}
