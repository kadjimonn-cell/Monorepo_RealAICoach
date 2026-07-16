import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle, Line } from 'react-native-svg';
import { useLocalSearchParams } from 'expo-router';
import AppShell from '../src/components/AppShell';
import api from '../src/services/api';
import { useAuth } from '../src/context/AuthContext';
import { getNetworkIncidents, subscribeNetworkIncidents } from '../src/services/networkIncidentTimeline';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

import { useAdminTheme } from '../src/hooks/useAdminTheme';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';

export default function PerformanceObservabilityPage() {
  const { t } = useTranslation();
  t('i18n.route.performance-observability.probe');
  const { colors } = useTheme();
  const AC = useAdminTheme();
  const C = {
    bg: AC.bg,
    card: AC.card,
    cardAlt: AC.bgSoft,
    border: AC.border,
    text: AC.text,
    muted: AC.textMuted,
    primary: colors.info,
    success: colors.success,
    warn: colors.warning,
    error: colors.error,
  };
  const { user, loading: authLoading } = useAuth();
  const accessLoading = false;
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [forbidden, setForbidden] = useState(false);
  const [unified, setUnified] = useState(null);
  const [pagePerf, setPagePerf] = useState(null);
  const [platformPerf, setPlatformPerf] = useState(null);
  const [bundle, setBundle] = useState(null);
  const [shellHealth, setShellHealth] = useState(null);
  const [perfTrend, setPerfTrend] = useState(null);
  const [incidentTimeline, setIncidentTimeline] = useState([]);
  const [shellWindowHours, setShellWindowHours] = useState(24);
  const params = useLocalSearchParams();
  const focusShellHealth = String(params?.focus || '') === 'shell-health';

  const loadIncidentTimeline = useCallback(() => {
    setIncidentTimeline(getNetworkIncidents(18));
  }, []);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    setForbidden(false);
    try {
      const [u, p, pf, b, sh, pt] = await Promise.allSettled([
        api.get('/admin/platform-perf/unified'),
        api.get('/admin/page-performance/dashboard?period=24h'),
        api.get('/admin/platform/performance'),
        api.get('/admin/platform-perf/bundle-budget'),
        api.get(`/admin/platform-perf/shell-health?hours=${shellWindowHours}`),
        api.get('/admin/platform-perf/trend?hours=24'),
      ]);

      let successCount = 0;

      if (u.status === 'fulfilled') {
        setUnified(u.value.data);
        successCount += 1;
      }
      if (p.status === 'fulfilled') {
        setPagePerf(p.value.data);
        successCount += 1;
      }
      if (pf.status === 'fulfilled') {
        setPlatformPerf(pf.value.data);
        successCount += 1;
      }
      if (b.status === 'fulfilled') {
        setBundle(b.value.data);
        successCount += 1;
      }
      if (sh.status === 'fulfilled') {
        setShellHealth(sh.value.data);
        successCount += 1;
      }
      if (pt.status === 'fulfilled') {
        setPerfTrend(pt.value.data);
        successCount += 1;
      }

      if (successCount === 0) {
        setError('Unable to load observability metrics right now.');
      }
    } catch (e) {
      if (e?.response?.status === 403) {
        setForbidden(true);
      } else {
        setError('Unable to load observability metrics right now.');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [shellWindowHours]);

  useEffect(() => {
    void load();
    const iv = setInterval(() => { void load(true); }, 30000);
    return () => clearInterval(iv);
  }, [load]);

  useEffect(() => {
    loadIncidentTimeline();
    const unsubscribe = subscribeNetworkIncidents(() => {
      loadIncidentTimeline();
    });
    const iv = setInterval(loadIncidentTimeline, 30000);
    return () => {
      unsubscribe();
      clearInterval(iv);
    };
  }, [loadIncidentTimeline]);

  const score = unified?.score?.overall ?? 0;
  const apiP95 = unified?.api?.api_p95_ms ?? 0;
  const routeP95 = pagePerf?.kpis?.p95_ms ?? 0;
  const bundleLargest = bundle?.current?.largest_bundle_mb ?? 0;
  const bundleTotal = bundle?.current?.total_bundle_mb ?? 0;
  const shellTotals = shellHealth?.totals || {};
  const shellAlert = shellHealth?.alert || {};
  const shellBands = shellHealth?.alert_rules?.band_thresholds || {};
  const shellAlertStatus = String(shellAlert?.status || 'normal');
  const shellAlertColor = shellAlertStatus === 'critical' ? colors.error : shellAlertStatus === 'warning' ? C.warn : C.success;
  const webVitals = unified?.web_vitals || {};
  const trendSnapshots = Array.isArray(perfTrend?.snapshots) ? perfTrend.snapshots : [];
  const lcpSeries = trendSnapshots.map((entry) => Number(entry?.web_vitals?.lcp_s || 0));
  const clsSeries = trendSnapshots.map((entry) => Number(entry?.web_vitals?.cls || 0));
  const inpSeries = trendSnapshots.map((entry) => Number(entry?.web_vitals?.inp_ms || 0));

  return (
    <AdminRouteGate returnTo="/performance-observability">
    <AppShell>
      <View style={{ flex: 1, backgroundColor: C.bg }}>
        <ScrollView
          contentContainerStyle={{ padding: 20, paddingBottom: 90 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }} tintColor={C.primary} />}
          data-testid="performance-observability-page" testID="performance-observability-page"
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <View>
              <Text style={{ color: C.text, fontSize: 26, fontWeight: '800' }} data-testid="performance-observability-title" testID="performance-observability-title">{t("autofix.precision12.performance.observability")}</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>{t("autofix.precision12.bundle.trend.api.p95.route.paint.p95")}</Text>
            </View>
            <TouchableOpacity
              onPress={() => void load()}
              style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardAlt, paddingHorizontal: 12, paddingVertical: 8 }}
              data-testid="performance-observability-refresh-button" testID="performance-observability-refresh-button"
            >
              <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{t("abTesting.actions.refresh")}</Text>
            </TouchableOpacity>
          </View>

          {error ? <Text style={{ color: colors.error, marginBottom: 10 }} data-testid="performance-observability-error" testID="performance-observability-error">{error}</Text> : null}

          {focusShellHealth ? (
            <View style={{ marginBottom: 10, borderRadius: 10, borderWidth: 1, borderColor: C.primary, backgroundColor: 'rgba(56, 189, 248, 0.13)', paddingHorizontal: 12, paddingVertical: 8 }} data-testid="shell-health-focus-hint" testID="shell-health-focus-hint">
              <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700' }}>{t("autofix.precision12.showing.shell.health.diagnostics.from.degraded.network.warning")}</Text>
            </View>
          ) : null}

          {loading ? (
            <View style={{ marginTop: 24, alignItems: 'center' }} data-testid="performance-observability-loading" testID="performance-observability-loading">
              <ActivityIndicator color={C.primary} />
            </View>
          ) : (
            <>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                <Metric label="Unified Score" value={`${score}`} tone={score >= 85 ? C.success : score >= 65 ? C.warn : colors.error} testId="metric-unified-score" palette={C} />
                <Metric label="API p95" value={`${apiP95} ms`} tone={apiP95 <= 500 ? C.success : C.warn} testId="metric-api-p95" palette={C} />
                <Metric label="Route Paint p95" value={`${routeP95} ms`} tone={routeP95 <= 1000 ? C.success : C.warn} testId="metric-route-p95" palette={C} />
                <Metric label="Largest Bundle" value={`${bundleLargest.toFixed(2)} MB`} tone={bundleLargest <= 4 ? C.success : colors.error} testId="metric-bundle-largest" palette={C} />
                <Metric label="Total Bundle" value={`${bundleTotal.toFixed(2)} MB`} tone={bundleTotal <= 10 ? C.success : colors.error} testId="metric-bundle-total" palette={C} />
              </View>

              <View style={{ marginTop: 16, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 14 }} data-testid="web-vitals-trend-card" testID="web-vitals-trend-card">
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }}>{t("autofix.precision12.web.vitals.trends.24h")}</Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>{t("autofix.precision12.lcp.cls.and.inp.trend.cards.with.latest")}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
                  <VitalTrendCard
                    label="LCP"
                    unit="s"
                    value={Number(webVitals?.lcp_s || 0)}
                    target={2.5}
                    critical={4.0}
                    series={lcpSeries}
                    testId="web-vital-lcp-card"
                    palette={C}
                    t={t}
                  />
                  <VitalTrendCard
                    label="CLS"
                    unit=""
                    value={Number(webVitals?.cls || 0)}
                    target={0.1}
                    critical={0.25}
                    series={clsSeries}
                    precision={3}
                    testId="web-vital-cls-card"
                    palette={C}
                    t={t}
                  />
                  <VitalTrendCard
                    label="INP"
                    unit="ms"
                    value={Number(webVitals?.inp_ms || 0)}
                    target={200}
                    critical={500}
                    series={inpSeries}
                    precision={1}
                    testId="web-vital-inp-card"
                    palette={C}
                    t={t}
                  />
                </View>
              </View>

              <View style={{ marginTop: 16, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 14 }} data-testid="bundle-trend-card" testID="bundle-trend-card">
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }}>{t("autofix.precision12.bundle.trend.recent.snapshots")}</Text>
                <View style={{ marginTop: 10, gap: 8 }}>
                  {(bundle?.trend || []).slice(-8).map((row, idx) => (
                    <View key={`${row.timestamp}-${idx}`} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`bundle-trend-row-${idx}`} testID={`bundle-trend-row-${idx}`}>
                      <Text style={{ color: C.muted, fontSize: 10 }}>{new Date(row.timestamp).toLocaleString()}</Text>
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{t("autofix.precision12.largest")}{Number(row.largest_bundle_mb || 0).toFixed(2)}{t("autofix.precision12.mb.total")}{Number(row.total_bundle_mb || 0).toFixed(2)} MB</Text>
                    </View>
                  ))}
                </View>
              </View>

              <View style={{ marginTop: 16, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 14 }} data-testid="slow-endpoints-card" testID="slow-endpoints-card">
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }}>{t("autofix.precision12.top.slow.endpoints")}</Text>
                <View style={{ marginTop: 10, gap: 8 }}>
                  {(platformPerf?.top_endpoints || []).slice(0, 8).map((ep, idx) => (
                    <View key={`${ep.path}-${idx}`} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`slow-endpoint-row-${idx}`} testID={`slow-endpoint-row-${idx}`}>
                      <View style={{ flex: 1, paddingRight: 10 }}>
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>{ep.path}</Text>
                        <Text style={{ color: C.muted, fontSize: 10 }}>{t("autofix.precision12.count")}{ep.count}</Text>
                      </View>
                      <Text style={{ color: C.warn, fontSize: 11, fontWeight: '800' }}>{t("autofix.precision12.p95")}{Number(ep.p95_ms || 0).toFixed(1)} ms</Text>
                    </View>
                  ))}
                </View>
              </View>

              <View style={{ marginTop: 16, borderRadius: 14, borderWidth: 1, borderColor: focusShellHealth ? C.primary : C.border, backgroundColor: C.card, padding: 14 }} data-testid="shell-health-monitor-card" testID="shell-health-monitor-card">
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }}>{t("autofix.precision12.shell.health.monitor")}</Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>{t("autofix.precision12.client.side.resilience.telemetry.from.live.shell.sessions")}</Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }} data-testid="shell-health-window-selector" testID="shell-health-window-selector">
                  {[24, 72, 168].map((windowHours) => (
                    <TouchableOpacity
                      key={windowHours}
                      onPress={() => setShellWindowHours(windowHours)}
                      style={{
                        borderRadius: 999,
                        borderWidth: 1,
                        borderColor: shellWindowHours === windowHours ? C.primary : C.border,
                        backgroundColor: shellWindowHours === windowHours ? 'rgba(56, 189, 248, 0.16)' : C.cardAlt,
                        paddingHorizontal: 12,
                        paddingVertical: 6,
                      }}
                      data-testid={`shell-health-window-${windowHours}h-button`} testID={`shell-health-window-${windowHours}h-button`}
                    >
                      <Text style={{ color: shellWindowHours === windowHours ? C.primary : C.text, fontSize: 11, fontWeight: '700' }}>{windowHours}h</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <View style={{ marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: shellAlertColor, backgroundColor: `${shellAlertColor}22`, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="shell-health-alert-banner" testID="shell-health-alert-banner">
                  <Text style={{ color: shellAlertColor, fontSize: 11, fontWeight: '800' }} data-testid="shell-health-alert-status" testID="shell-health-alert-status">
                    {shellAlertStatus.toUpperCase()} BAND
                  </Text>
                  <Text style={{ color: C.text, fontSize: 11, marginTop: 3 }} data-testid="shell-health-alert-summary" testID="shell-health-alert-summary">
                    {shellAlert?.summary || 'Shell telemetry is within healthy operating bands.'}
                  </Text>
                </View>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 10 }} data-testid="shell-health-alert-band-thresholds" testID="shell-health-alert-band-thresholds">
                  <BandPill
                    label="Warning Band"
                    value={`Score ≥ ${Number(shellBands.warning_stress_score || 18)}`}
                    tone={C.warn}
                    testId="shell-health-warning-band-pill"
                    palette={C}
                    secondaryTextColor={AC.textSec}
                  />
                  <BandPill
                    label="Critical Band"
                    value={`Score ≥ ${Number(shellBands.critical_stress_score || 40)}`}
                    tone={colors.error}
                    testId="shell-health-critical-band-pill"
                    palette={C}
                    secondaryTextColor={AC.textSec}
                  />
                </View>

                <View style={{ marginTop: 12 }} data-testid="shell-health-sparkline-card" testID="shell-health-sparkline-card">
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("autofix.precision12.resilience.drift.sparkline")}</Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }} data-testid="shell-health-sparkline-subtitle" testID="shell-health-sparkline-subtitle">{t("autofix.precision12.spikes.represent.rising.fallback.activations.and.background.429")}</Text>
                  <View style={{ marginTop: 8 }} data-testid="shell-health-sparkline-chart" testID="shell-health-sparkline-chart">
                    <ShellHealthTrendSparkline
                      points={Array.isArray(shellHealth?.trend) ? shellHealth.trend : []}
                      warningThreshold={Number(shellBands.warning_stress_score || 18)}
                      criticalThreshold={Number(shellBands.critical_stress_score || 40)}
                      palette={C}
                      t={t}
                    />
                  </View>
                </View>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
                  <Metric label="Dedupe Hits" value={`${Number(shellTotals.dedupe_hits || 0)}`} tone={C.success} testId="metric-shell-dedupe-hits" palette={C} />
                  <Metric label="Fallback Activations" value={`${Number(shellTotals.fallback_activations || 0)}`} tone={Number(shellTotals.fallback_activations || 0) > 0 ? C.warn : C.success} testId="metric-shell-fallbacks" palette={C} />
                  <Metric label="Route Recoveries" value={`${Number(shellTotals.route_recoveries || 0)}`} tone={Number(shellTotals.route_recoveries || 0) > 0 ? C.warn : C.success} testId="metric-shell-route-recoveries" palette={C} />
                  <Metric label="Background 429s" value={`${Number(shellTotals.rate_limit_429s || 0)}`} tone={Number(shellTotals.rate_limit_429s || 0) > 0 ? C.warn : C.success} testId="metric-shell-rate-limits" palette={C} />
                </View>

                <View style={{ marginTop: 14, gap: 8 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("autofix.precision12.recent.shell.events")}</Text>
                  {(shellHealth?.recent_events || []).slice(0, 8).map((event, idx) => (
                    <View key={`${event.timestamp}-${idx}`} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`shell-health-event-row-${idx}`} testID={`shell-health-event-row-${idx}`}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{String(event.metric || 'event').replace(/_/g, ' ')}</Text>
                        <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }} numberOfLines={1}>{event.pathname || 'unknown route'}</Text>
                      </View>
                      <Text style={{ color: C.muted, fontSize: 10 }}>{event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '-'}</Text>
                    </View>
                  ))}
                  {(!shellHealth?.recent_events || shellHealth.recent_events.length === 0) ? (
                    <Text style={{ color: C.muted, fontSize: 11 }} data-testid="shell-health-empty-state" testID="shell-health-empty-state">{t("autofix.precision12.no.client.telemetry.events.recorded.in.the.selected")}</Text>
                  ) : null}
                </View>

                <View style={{ marginTop: 14, gap: 8 }} data-testid="network-incident-timeline-panel" testID="network-incident-timeline-panel">
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{t("autofix.precision12.network.incident.timeline")}</Text>
                  <Text style={{ color: C.muted, fontSize: 10 }}>{t("autofix.precision12.degraded.offline.transitions.captured.from.shell.clients")}</Text>
                  {incidentTimeline.map((incident, idx) => (
                    <View key={`${incident.id || incident.timestamp}-${idx}`} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`network-incident-row-${idx}`} testID={`network-incident-row-${idx}`}>
                      <View style={{ flex: 1, paddingRight: 8 }}>
                        <Text style={{ color: incident.type === 'offline' ? colors.error : incident.type === 'degraded_warning' ? C.warn : C.success, fontSize: 11, fontWeight: '800' }}>
                          {formatIncidentLabel(incident.type)}
                        </Text>
                        <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }} numberOfLines={1}>
                          {incident?.detail?.source ? `source: ${incident.detail.source}` : 'source: shell-event'}
                        </Text>
                      </View>
                      <Text style={{ color: C.muted, fontSize: 10 }}>{incident?.timestamp ? new Date(incident.timestamp).toLocaleTimeString() : '-'}</Text>
                    </View>
                  ))}
                  {incidentTimeline.length === 0 ? (
                    <Text style={{ color: C.muted, fontSize: 11 }} data-testid="network-incident-empty-state" testID="network-incident-empty-state">{t("autofix.precision12.no.degraded.offline.transition.incidents.captured.yet")}</Text>
                  ) : null}
                </View>
              </View>
            </>
          )}
        </ScrollView>
      </View>
    </AppShell>
    </AdminRouteGate>
  );
}

function Metric({ label, value, tone, testId, palette }) {
  return (
    <View style={{ flexBasis: '48%', minWidth: 170, borderRadius: 12, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.card, padding: 12 }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.muted, fontSize: 10, textTransform: 'uppercase', fontWeight: '700' }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 8, gap: 6 }}>
        <Ionicons name="analytics-outline" size={15} color={tone} />
        <Text style={{ color: tone, fontSize: 17, fontWeight: '900' }}>{value}</Text>
      </View>
    </View>
  );
}

function BandPill({ label, value, tone, testId, palette, secondaryTextColor }) {
  return (
    <View style={{ borderRadius: 10, borderWidth: 1, borderColor: `${tone}77`, backgroundColor: `${tone}22`, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={testId} testID={testId}>
      <Text style={{ color: tone, fontSize: 10, fontWeight: '800' }}>{label}</Text>
      <Text style={{ color: secondaryTextColor || palette.muted, fontSize: 11, fontWeight: '700', marginTop: 2 }}>{value}</Text>
    </View>
  );
}

function VitalTrendCard({ label, unit, value, target, critical, series, precision = 2, testId, palette, t }) {
  const tone = value > critical ? palette.error : value > target ? palette.warn : palette.success;
  const formattedValue = unit === '' ? value.toFixed(precision) : `${value.toFixed(precision)} ${unit}`;
  const first = series?.[0] ?? value;
  const delta = Number(value - first);
  const deltaLabel = `${delta >= 0 ? '+' : ''}${delta.toFixed(unit === '' ? 3 : 1)} ${unit}`.trim();

  return (
    <View style={{ flexBasis: '31%', minWidth: 170, borderRadius: 12, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.cardAlt, padding: 10 }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{label}</Text>
      <Text style={{ color: tone, fontSize: 18, fontWeight: '900', marginTop: 6 }}>{formattedValue}</Text>
      <Text style={{ color: palette.muted, fontSize: 10, marginTop: 2 }} data-testid={`${testId}-delta`} testID={`${testId}-delta`}>{t("autofix.precision12.24h.delta")}{deltaLabel}</Text>
      <View style={{ marginTop: 8 }} data-testid={`${testId}-sparkline`} testID={`${testId}-sparkline`}>
        <TinySparkline points={series} tone={tone} palette={palette} t={t} />
      </View>
      <Text style={{ color: palette.muted, fontSize: 10, marginTop: 6 }}>{t("autofix.precision12.target")}{target}{unit}{t("autofix.precision12.critical")}{critical}{unit}</Text>
    </View>
  );
}

function TinySparkline({ points, tone, palette, t }) {
  const { width } = useWindowDimensions();
  const chartWidth = Math.max(130, Math.min((width - 100) / 3, 210));
  const chartHeight = 44;
  const values = (points || []).slice(-16);

  if (!values.length) {
    return <Text style={{ color: palette.muted, fontSize: 10 }} data-testid="web-vital-sparkline-empty" testID="web-vital-sparkline-empty">{t("autofix.precision12.no.samples")}</Text>;
  }

  const max = Math.max(...values, 1);
  const step = values.length > 1 ? (chartWidth - 12) / (values.length - 1) : 0;
  const toY = (v) => chartHeight - (Math.max(v, 0) / max) * (chartHeight - 10);

  const coords = values.map((value, idx) => ({ x: 6 + (idx * step), y: toY(Number(value || 0)) }));

  return (
    <Svg width={chartWidth} height={chartHeight + 4}>
      {coords.map((point, idx) => {
        const next = coords[idx + 1];
        if (!next) return null;
        return <Line key={`trend-seg-${idx}`} x1={point.x} y1={point.y} x2={next.x} y2={next.y} stroke={tone} strokeWidth="2" />;
      })}
      {coords.map((point, idx) => (
        <Circle key={`trend-dot-${idx}`} cx={point.x} cy={point.y} r="1.8" fill={tone} />
      ))}
    </Svg>
  );
}

function formatIncidentLabel(type) {
  const labels = {
    degraded_warning: 'Degraded warning shown',
    offline: 'Offline event detected',
    online_restored: 'Connection restored',
    diagnostics_opened: 'Diagnostics opened',
  };
  return labels[type] || String(type || 'incident').replace(/_/g, ' ');
}

function ShellHealthTrendSparkline({ points, warningThreshold, criticalThreshold, palette, t }) {
  const { width } = useWindowDimensions();
  const chartWidth = Math.max(220, Math.min(width - 80, 540));
  const chartHeight = 88;

  if (!points?.length) {
    return <Text style={{ color: palette.muted, fontSize: 11 }} data-testid="shell-health-sparkline-empty-state" testID="shell-health-sparkline-empty-state">{t("autofix.precision12.no.trend.points.captured.yet")}</Text>;
  }

  const scores = points.map((point) => Number(point?.stress_score || 0));
  const maxY = Math.max(criticalThreshold * 1.3, ...scores, 1);
  const step = points.length > 1 ? (chartWidth - 24) / (points.length - 1) : 0;
  const toY = (value) => chartHeight - (Math.max(0, value) / maxY) * (chartHeight - 20);

  const coords = scores.map((score, idx) => ({
    x: 12 + (idx * step),
    y: toY(score),
    value: score,
  }));

  const warningY = toY(warningThreshold);
  const criticalY = toY(criticalThreshold);

  return (
    <Svg width={chartWidth} height={chartHeight + 16}>
      <Line x1={10} y1={warningY} x2={chartWidth - 8} y2={warningY} stroke={palette.warn} strokeWidth="1" strokeDasharray="4 3" />
      <Line x1={10} y1={criticalY} x2={chartWidth - 8} y2={criticalY} stroke={palette.error} strokeWidth="1" strokeDasharray="4 3" />
      <Line x1={10} y1={chartHeight} x2={chartWidth - 8} y2={chartHeight} stroke={palette.border} strokeWidth="1" />

      {coords.map((point, idx) => {
        const next = coords[idx + 1];
        if (!next) return null;
        const segmentColor = point.value >= criticalThreshold || next.value >= criticalThreshold
          ? palette.error
          : point.value >= warningThreshold || next.value >= warningThreshold
            ? palette.warn
            : palette.success;
        return <Line key={`shell-seg-${idx}`} x1={point.x} y1={point.y} x2={next.x} y2={next.y} stroke={segmentColor} strokeWidth="2" />;
      })}

      {coords.map((point, idx) => (
        <Circle
          key={`shell-point-${idx}`}
          cx={point.x}
          cy={point.y}
          r="2.7"
          fill={point.value >= criticalThreshold ? palette.error : point.value >= warningThreshold ? palette.warn : palette.success}
        />
      ))}
    </Svg>
  );
}