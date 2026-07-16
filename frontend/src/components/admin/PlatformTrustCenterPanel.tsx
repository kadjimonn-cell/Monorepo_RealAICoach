import React, { useCallback, useMemo, useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { getAdminColors } from '../../hooks/useAdminTheme';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';

function makeT(AC: any) { return {
  card: AC.card,
  bgSoft: AC.surfaceHover,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  primary: AC.primary,
  success: AC.success,
  warning: AC.warning,
  error: AC.error,
  successText: AC.successText || AC.success,
}; }

let STATUS_THEME = makeT(getAdminColors(false));

const tx = (_key: string, fallback: string) => fallback;

const statusColor = (status: string) => {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'healthy' || normalized === 'fresh' || normalized === 'ok') return STATUS_THEME.success;
  if (normalized === 'warning' || normalized === 'degraded' || normalized === 'stale') return STATUS_THEME.warning;
  if (normalized === 'critical' || normalized === 'error') return STATUS_THEME.error;
  return STATUS_THEME.textSec;
};

const statusBg = (status: string) => `${statusColor(status)}20`;

const toFixedOrDash = (value: any, decimals = 1) => {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(decimals) : '--';
};

const relativeTime = (iso?: string | null) => {
  if (!iso) return 'Unavailable';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'Unavailable';
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.max(0, Math.round(diffMs / 60000));
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.round(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
};

const labelizeAction = (raw: string) => String(raw || 'unknown').replace(/_/g, ' ');

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

const computeStartupRisk = ({
  appReadyP95Ms,
  fallbackActivations,
  routeRecoveries,
  rateLimit429s,
  shellAlertStatus,
  whiteScreenHints,
  directIntegrityPct,
}: {
  appReadyP95Ms: number;
  fallbackActivations: number;
  routeRecoveries: number;
  rateLimit429s: number;
  shellAlertStatus: string;
  whiteScreenHints: number;
  directIntegrityPct: number;
}) => {
  const latencyRisk = appReadyP95Ms > 0 ? clamp(((appReadyP95Ms - 1400) / 2600) * 45, 0, 45) : 0;
  const fallbackRisk = clamp(fallbackActivations * 5, 0, 25);
  const recoveryRisk = clamp(routeRecoveries * 4, 0, 20);
  const rateLimitRisk = clamp(rateLimit429s * 2, 0, 10);
  const alertBandRisk = shellAlertStatus === 'critical' ? 20 : shellAlertStatus === 'warning' ? 10 : 0;
  const whiteHintRisk = clamp(whiteScreenHints * 10, 0, 20);
  const integrityRisk = directIntegrityPct < 95 ? clamp((95 - directIntegrityPct) * 0.8, 0, 10) : 0;

  const score = Math.round(clamp(
    latencyRisk + fallbackRisk + recoveryRisk + rateLimitRisk + alertBandRisk + whiteHintRisk + integrityRisk,
    0,
    100,
  ));

  const band = score >= 60 ? 'critical' : score >= 25 ? 'elevated' : 'low';
  return {
    score,
    band,
    components: {
      latencyRisk: Math.round(latencyRisk),
      fallbackRisk: Math.round(fallbackRisk),
      recoveryRisk: Math.round(recoveryRisk),
      rateLimitRisk: Math.round(rateLimitRisk),
      alertBandRisk: Math.round(alertBandRisk),
      whiteHintRisk: Math.round(whiteHintRisk),
      integrityRisk: Math.round(integrityRisk),
    },
  };
};

export default function PlatformTrustCenterPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  STATUS_THEME = T;
  const [refreshing, setRefreshing] = useState(false);

  const {
    data: liveServices,
    loading: liveLoading,
    refetch: refetchLiveServices,
    lastUpdated: liveUpdated,
  } = useLiveQuery('/admin/platform-health/live-services', {
    entity: 'platform-health-live',
    pollInterval: 45000,
  });

  const {
    data: enterpriseStatus,
    loading: enterpriseLoading,
    refetch: refetchEnterpriseStatus,
  } = useLiveQuery('/admin/platform-health/enterprise-standard/status', {
    entity: 'enterprise-standard-status',
    pollInterval: 60000,
  });

  const {
    data: fixHistory,
    loading: fixHistoryLoading,
    refetch: refetchFixHistory,
  } = useLiveQuery('/admin/platform-health/fix-history?limit=6', {
    entity: 'platform-health-fixes',
    pollInterval: 90000,
  });

  const {
    data: pagePerf,
    loading: pagePerfLoading,
    refetch: refetchPagePerf,
    lastUpdated: pagePerfUpdated,
  } = useLiveQuery('/admin/page-performance/dashboard?period=1h', {
    entity: 'trust-center-page-perf-1h',
    pollInterval: 30000,
  });

  const {
    data: shellHealth,
    loading: shellHealthLoading,
    refetch: refetchShellHealth,
    lastUpdated: shellHealthUpdated,
  } = useLiveQuery('/admin/platform-perf/shell-health?hours=24', {
    entity: 'trust-center-shell-health-24h',
    pollInterval: 30000,
  });

  const {
    data: routeHealth,
    loading: routeHealthLoading,
    refetch: refetchRouteHealth,
    lastUpdated: routeHealthUpdated,
  } = useLiveQuery('/admin/platform-perf/route-health', {
    entity: 'trust-center-route-health',
    pollInterval: 120000,
  });

  const {
    data: ssoDriftSentinel,
    refetch: refetchSsoDrift,
  } = useLiveQuery('/auth/admin/sso-redirect-drift-sentinel', {
    entity: 'trust-center-sso-drift-sentinel',
    pollInterval: 60000,
  });

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([
      refetchLiveServices(),
      refetchEnterpriseStatus(),
      refetchFixHistory(),
      refetchPagePerf(),
      refetchShellHealth(),
      refetchRouteHealth(),
      refetchSsoDrift(),
    ]);
    setRefreshing(false);
  }, [refetchEnterpriseStatus, refetchFixHistory, refetchLiveServices, refetchPagePerf, refetchRouteHealth, refetchShellHealth, refetchSsoDrift]);

  const frameworkStatus = String(enterpriseStatus?.framework_status || 'unknown');
  const live = liveServices || {};
  const realtime = live.realtime || {};
  const scheduler = live.scheduler || {};
  const email = live.email || {};
  const platform = enterpriseStatus?.platform || {};
  const latestScan = platform.latest_scan || {};
  const latestFix = platform.latest_fix || {};
  const latestBuild = latestScan?.build || {};
  const cadence = enterpriseStatus?.cadence || {};
  const realtimeHealth = String(realtime?.reconnect_health_status || 'unknown');
  const appReadyP95Ms = Number(pagePerf?.kpis?.p95_ms || 0);
  const appReadyAvgMs = Number(pagePerf?.kpis?.avg_ms || 0);
  const shellTotals = shellHealth?.totals || {};
  const shellAlertStatus = String(shellHealth?.alert?.status || 'normal').toLowerCase();
  const directRoutes = Array.isArray(routeHealth?.direct_routes) ? routeHealth.direct_routes : [];
  const whiteScreenHints = directRoutes.filter((row: any) => row?.white_screen_hint === true).length;
  const directIntegrityPct = Number(routeHealth?.summary?.direct_integrity_pct || 100);

  const startupRisk = computeStartupRisk({
    appReadyP95Ms,
    fallbackActivations: Number(shellTotals?.fallback_activations || 0),
    routeRecoveries: Number(shellTotals?.route_recoveries || 0),
    rateLimit429s: Number(shellTotals?.rate_limit_429s || 0),
    shellAlertStatus,
    whiteScreenHints,
    directIntegrityPct,
  });

  const appReadyStatus = appReadyP95Ms === 0 ? 'no_data' : appReadyP95Ms > 4000 ? 'critical' : appReadyP95Ms > 2000 ? 'degraded' : 'healthy';
  const appReadyColor = appReadyStatus === 'critical' ? T.error : appReadyStatus === 'degraded' ? T.warning : appReadyStatus === 'healthy' ? T.success : T.textSec;
  const startupRiskColor = startupRisk.band === 'critical' ? T.error : startupRisk.band === 'elevated' ? T.warning : T.success;
  const startupRiskLabel = startupRisk.band === 'critical' ? 'Critical Risk' : startupRisk.band === 'elevated' ? 'Elevated Risk' : 'Low Risk';
  const startupLatencyLabel = appReadyP95Ms > 0 ? `${Math.round(appReadyP95Ms)} ms` : '--';
  const startupUpdatedAt = [liveUpdated, pagePerfUpdated, shellHealthUpdated, routeHealthUpdated]
    .filter(Boolean)
    .map((entry) => entry as Date)
    .sort((a, b) => b.getTime() - a.getTime())[0];
  const sentinelStatus = String(ssoDriftSentinel?.status || ssoDriftSentinel?.state || 'unknown').toLowerCase();
  const sentinelProviders = Array.isArray(ssoDriftSentinel?.drift_providers)
    ? ssoDriftSentinel.drift_providers
    : Array.isArray(ssoDriftSentinel?.snapshot?.drift_providers)
    ? ssoDriftSentinel.snapshot.drift_providers
    : [];

  const summaryCards = useMemo(() => ([
    {
      key: 'uptime',
      label: 'Runtime Uptime',
      value: `${toFixedOrDash(live?.uptime_hours, 1)}h`,
      icon: 'time',
      color: T.successText,
      testId: 'trust-center-uptime-hours',
    },
    {
      key: 'score',
      label: 'Health Score',
      value: String(latestScan?.score ?? '--'),
      icon: 'pulse',
      color: statusColor(frameworkStatus),
      testId: 'trust-center-health-score',
    },
    {
      key: 'issues',
      label: 'Open Issues',
      value: String(latestScan?.total_issues ?? '--'),
      icon: 'warning',
      color: Number(latestScan?.total_issues ?? 0) > 0 ? T.warning : T.success,
      testId: 'trust-center-open-issues',
    },
    {
      key: 'reconnect-success',
      label: 'Realtime Success (30m)',
      value: `${toFixedOrDash(realtime?.connect_success_rate_30m, 1)}%`,
      icon: 'git-network',
      color: statusColor(realtimeHealth),
      testId: 'trust-center-reconnect-success-rate',
    },
    {
      key: 'scheduler-health',
      label: 'Scheduler Heartbeats',
      value: `${scheduler?.heartbeats_healthy ?? 0}/${scheduler?.heartbeats_total ?? 0}`,
      icon: 'sync',
      color: Number(scheduler?.heartbeats_healthy ?? 0) >= Number(scheduler?.heartbeats_total ?? 0) ? T.success : T.warning,
      testId: 'trust-center-scheduler-heartbeats',
    },
    {
      key: 'email-delivery',
      label: 'Email Success Rate',
      value: `${toFixedOrDash(email?.success_rate, 1)}%`,
      icon: 'mail',
      color: Number(email?.success_rate ?? 0) >= 98 ? T.success : T.warning,
      testId: 'trust-center-email-success-rate',
    },
    {
      key: 'sso-redirect-drift',
      label: 'SSO Redirect Drift Sentinel',
      value: sentinelStatus === 'critical' || sentinelStatus === 'drift' ? 'DRIFT' : sentinelStatus === 'healthy' ? 'Healthy' : '--',
      icon: 'shield',
      color: sentinelStatus === 'critical' || sentinelStatus === 'drift' ? T.error : sentinelStatus === 'healthy' ? T.success : T.textSec,
      testId: 'trust-center-sso-redirect-drift-sentinel',
      detail: sentinelProviders.length ? `Providers: ${sentinelProviders.join(', ')}` : 'No divergence',
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ]), [
    email?.success_rate,
    frameworkStatus,
    latestScan?.score,
    latestScan?.total_issues,
    live?.uptime_hours,
    realtime?.connect_success_rate_30m,
    realtimeHealth,
    scheduler?.heartbeats_healthy,
    scheduler?.heartbeats_total,
    sentinelProviders,
    sentinelStatus,
  ]);

  const repairEvents = useMemo(() => {
    const fromLatest = Array.isArray(latestFix?.actions)
      ? latestFix.actions.map((action: any, idx: number) => ({
          id: `latest-${idx}`,
          action: labelizeAction(action?.action),
          status: String(action?.status || (action?.fixed_count > 0 ? 'healthy' : 'info')),
          detail: action?.message || (typeof action?.fixed_count === 'number' ? `${action.fixed_count} items fixed` : null),
          timestamp: latestFix?.fixed_at || latestFix?._stored_at,
        }))
      : [];

    const historyRows = Array.isArray(fixHistory?.fixes)
      ? fixHistory.fixes.flatMap((fix: any, fixIndex: number) =>
          (Array.isArray(fix?.actions) ? fix.actions : []).slice(0, 2).map((action: any, actionIndex: number) => ({
            id: `history-${fixIndex}-${actionIndex}`,
            action: labelizeAction(action?.action),
            status: String(action?.status || (action?.fixed_count > 0 ? 'healthy' : 'info')),
            detail: action?.message || (typeof action?.fixed_count === 'number' ? `${action.fixed_count} items fixed` : null),
            timestamp: fix?.fixed_at || fix?._stored_at,
          })),
        )
      : [];

    return [...fromLatest, ...historyRows].slice(0, 10);
  }, [fixHistory?.fixes, latestFix?.actions, latestFix?._stored_at, latestFix?.fixed_at]);

  if (liveLoading && enterpriseLoading && !liveServices && !enterpriseStatus) {
    return (
      <View style={{ paddingVertical: 64, alignItems: 'center' }} data-testid="platform-trust-center-loading" testID="platform-trust-center-loading">
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: colors?.textMuted || T.textSec, marginTop: 10, fontSize: 13 }}>{tx('admin.platformTrustCenterPanel.auto.text.001', 'Loading Platform Trust Center...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 18, gap: 14 }} data-testid="platform-trust-center-panel" testID="platform-trust-center-panel">
      <View
        style={{
          backgroundColor: T.card,
          borderWidth: 1,
          borderColor: T.border,
          borderRadius: 16,
          padding: 16,
          gap: 12,
        }}
        data-testid="platform-trust-center-hero" testID="platform-trust-center-hero"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: `${T.primary}22`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="shield-checkmark" size={18} color={T.primary} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 19, fontWeight: '800' }} data-testid="platform-trust-center-title" testID="platform-trust-center-title">{tx('admin.platformTrustCenterPanel.auto.text.002', 'Platform Trust Center')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="platform-trust-center-subtitle" testID="platform-trust-center-subtitle">{tx('admin.platformTrustCenterPanel.auto.text.003', 'Live uptime, freshness posture, and self-repair visibility')}</Text>
            </View>
          </View>

          <TouchableOpacity accessibilityLabel={tx('admin.platformTrustCenterPanel.auto.accessibility.001', 'Refresh trust center data')}
            onPress={handleRefresh}
            disabled={refreshing}
            style={{
              paddingHorizontal: 12,
              paddingVertical: 8,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: T.border,
              backgroundColor: refreshing ? `${T.primary}44` : T.bgSoft,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
            }}
            data-testid="platform-trust-center-refresh-button" testID="platform-trust-center-refresh-button"
          >
            {refreshing ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="refresh" size={14} color={T.textSec} />}
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{refreshing ? 'Refreshing...' : 'Refresh'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ backgroundColor: statusBg(frameworkStatus), borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4 }} data-testid="platform-trust-framework-status" testID="platform-trust-framework-status">
            <Text style={{ color: statusColor(frameworkStatus), fontSize: 10, fontWeight: '800' }} data-testid="platform-trust-framework-status-value" testID="platform-trust-framework-status-value">Framework: {frameworkStatus.toUpperCase()}</Text>
          </View>
          <View style={{ backgroundColor: statusBg(realtimeHealth), borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4 }} data-testid="platform-trust-realtime-status" testID="platform-trust-realtime-status">
            <Text style={{ color: statusColor(realtimeHealth), fontSize: 10, fontWeight: '800' }} data-testid="platform-trust-realtime-status-value" testID="platform-trust-realtime-status-value">Realtime: {realtimeHealth.toUpperCase()}</Text>
          </View>
          <View style={{ backgroundColor: statusBg(String(latestBuild?.status || 'unknown')), borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4 }} data-testid="platform-trust-build-status" testID="platform-trust-build-status">
            <Text style={{ color: statusColor(String(latestBuild?.status || 'unknown')), fontSize: 10, fontWeight: '800' }} data-testid="platform-trust-build-status-value" testID="platform-trust-build-status-value">Build: {String(latestBuild?.status || 'unknown').toUpperCase()}</Text>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid="platform-trust-last-updated" testID="platform-trust-last-updated">Live update: {liveUpdated ? relativeTime(liveUpdated.toISOString()) : 'Unavailable'}</Text>
        </View>
      </View>

      <View
        style={{
          backgroundColor: `${startupRiskColor}14`,
          borderRadius: 14,
          borderWidth: 1,
          borderColor: `${startupRiskColor}66`,
          padding: 14,
          gap: 10,
        }}
        data-testid="startup-stability-guard-banner" testID="startup-stability-guard-banner"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 30, height: 30, borderRadius: 9, backgroundColor: `${startupRiskColor}22`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="shield" size={14} color={startupRiskColor} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="startup-stability-guard-title" testID="startup-stability-guard-title">{tx('admin.platformTrustCenterPanel.auto.text.004', 'Startup Stability Guard')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid="startup-stability-guard-subtitle" testID="startup-stability-guard-subtitle">{tx('admin.platformTrustCenterPanel.auto.text.005', 'Always-on startup monitor with real-time app-ready and white-screen risk telemetry')}</Text>
            </View>
          </View>
          <View style={{ backgroundColor: `${startupRiskColor}24`, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="startup-stability-guard-risk-band" testID="startup-stability-guard-risk-band">
            <Text style={{ color: startupRiskColor, fontSize: 10, fontWeight: '900' }} data-testid="startup-stability-guard-risk-band-value" testID="startup-stability-guard-risk-band-value">{startupRiskLabel.toUpperCase()}</Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="startup-stability-guard-metrics-row" testID="startup-stability-guard-metrics-row">
          <View style={{ flex: 1, minWidth: 170, backgroundColor: `${T.bgSoft}CC`, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10 }} data-testid="startup-stability-guard-app-ready-p95" testID="startup-stability-guard-app-ready-p95">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformTrustCenterPanel.auto.text.006', 'App-Ready Latency (p95)')}</Text>
            <Text style={{ color: appReadyColor, fontSize: 22, fontWeight: '900', marginTop: 5 }} data-testid="startup-stability-guard-app-ready-p95-value" testID="startup-stability-guard-app-ready-p95-value">{startupLatencyLabel}</Text>
            <Text style={{ color: T.textSec, fontSize: 10, marginTop: 2 }} data-testid="startup-stability-guard-app-ready-threshold" testID="startup-stability-guard-app-ready-threshold">{tx('admin.platformTrustCenterPanel.auto.text.007', 'Target: &lt; 2000 ms • Critical: &gt; 4000 ms')}</Text>
          </View>

          <View style={{ flex: 1, minWidth: 170, backgroundColor: `${T.bgSoft}CC`, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10 }} data-testid="startup-stability-guard-risk-score" testID="startup-stability-guard-risk-score">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformTrustCenterPanel.auto.text.008', 'White-Screen Risk Score')}</Text>
            <Text style={{ color: startupRiskColor, fontSize: 22, fontWeight: '900', marginTop: 5 }} data-testid="startup-stability-guard-risk-score-value" testID="startup-stability-guard-risk-score-value">{startupRisk.score}/100</Text>
            <Text style={{ color: T.textSec, fontSize: 10, marginTop: 2 }} data-testid="startup-stability-guard-risk-threshold" testID="startup-stability-guard-risk-threshold">{tx('admin.platformTrustCenterPanel.auto.text.009', 'Bands: 0–24 low • 25–59 elevated • 60+ critical')}</Text>
          </View>

          <View style={{ flex: 1, minWidth: 170, backgroundColor: `${T.bgSoft}CC`, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10 }} data-testid="startup-stability-guard-signal-breakdown" testID="startup-stability-guard-signal-breakdown">
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformTrustCenterPanel.auto.text.010', 'Live Signal Breakdown (24h)')}</Text>
            <Text style={{ color: T.text, fontSize: 11, marginTop: 5 }} data-testid="startup-stability-guard-signal-row-fallbacks" testID="startup-stability-guard-signal-row-fallbacks">Fallback activations: {Number(shellTotals?.fallback_activations || 0)}</Text>
            <Text style={{ color: T.text, fontSize: 11, marginTop: 2 }} data-testid="startup-stability-guard-signal-row-recoveries" testID="startup-stability-guard-signal-row-recoveries">Route recoveries: {Number(shellTotals?.route_recoveries || 0)}</Text>
            <Text style={{ color: T.text, fontSize: 11, marginTop: 2 }} data-testid="startup-stability-guard-signal-row-429s" testID="startup-stability-guard-signal-row-429s">Background 429s: {Number(shellTotals?.rate_limit_429s || 0)}</Text>
            <Text style={{ color: T.text, fontSize: 11, marginTop: 2 }} data-testid="startup-stability-guard-signal-row-white-hints" testID="startup-stability-guard-signal-row-white-hints">White-screen hints: {whiteScreenHints}</Text>
          </View>
        </View>

        <View style={{ backgroundColor: `${T.bgSoft}D9`, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10 }} data-testid="startup-stability-guard-footer" testID="startup-stability-guard-footer">
          <Text style={{ color: T.textSec, fontSize: 10 }} data-testid="startup-stability-guard-last-update" testID="startup-stability-guard-last-update">
            Last update: {startupUpdatedAt ? relativeTime(startupUpdatedAt.toISOString()) : 'Unavailable'} • avg app-ready {appReadyAvgMs > 0 ? `${Math.round(appReadyAvgMs)} ms` : '--'} • route integrity {toFixedOrDash(directIntegrityPct, 1)}%
          </Text>
          <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }} data-testid="startup-stability-guard-risk-components" testID="startup-stability-guard-risk-components">
            Risk components — latency {startupRisk.components.latencyRisk}, fallback {startupRisk.components.fallbackRisk}, recoveries {startupRisk.components.recoveryRisk}, 429 {startupRisk.components.rateLimitRisk}, band {startupRisk.components.alertBandRisk}, hints {startupRisk.components.whiteHintRisk}.
          </Text>
        </View>

        {(pagePerfLoading || shellHealthLoading || routeHealthLoading) ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="startup-stability-guard-live-loading" testID="startup-stability-guard-live-loading">
            <ActivityIndicator size="small" color={startupRiskColor} />
            <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.platformTrustCenterPanel.auto.text.011', 'Refreshing guard telemetry…')}</Text>
          </View>
        ) : null}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="platform-trust-center-summary-cards" testID="platform-trust-center-summary-cards">
        {summaryCards.map((card) => (
          <View key={card.key} style={{ flex: 1, minWidth: 165, backgroundColor: T.card, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border }} data-testid={card.testId} testID={card.testId}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={card.icon as any} size={14} color={card.color} />
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
            </View>
            <Text style={{ color: card.color, fontSize: 20, fontWeight: '900', marginTop: 6 }} data-testid={`${card.testId}-value`} testID={`${card.testId}-value`}>{card.value}</Text>
            {card.detail ? (
              <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }} numberOfLines={2} data-testid={`${card.testId}-detail`} testID={`${card.testId}-detail`}>
                {card.detail}
              </Text>
            ) : null}
          </View>
        ))}
      </View>

      <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 14 }} data-testid="platform-trust-center-freshness-section" testID="platform-trust-center-freshness-section">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="platform-trust-center-freshness-title" testID="platform-trust-center-freshness-title">{tx('admin.platformTrustCenterPanel.auto.text.012', 'Freshness & Reliability Signals')}</Text>
        <View style={{ marginTop: 10, gap: 8 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
            <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.platformTrustCenterPanel.auto.text.013', 'Latest scan')}</Text>
            <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} data-testid="platform-trust-latest-scan-time" testID="platform-trust-latest-scan-time">{relativeTime(latestScan?.scanned_at || latestScan?._stored_at)}</Text>
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
            <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.platformTrustCenterPanel.auto.text.014', 'Build age')}</Text>
            <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} data-testid="platform-trust-build-age-hours" testID="platform-trust-build-age-hours">{toFixedOrDash(latestBuild?.age_hours, 1)}h</Text>
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
            <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.platformTrustCenterPanel.auto.text.015', 'Latest auto-fix')}</Text>
            <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} data-testid="platform-trust-latest-fix-time" testID="platform-trust-latest-fix-time">{relativeTime(latestFix?.fixed_at || latestFix?._stored_at)}</Text>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid="platform-trust-build-message" testID="platform-trust-build-message">{latestBuild?.message || 'No build freshness message available.'}</Text>
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 14 }} data-testid="platform-trust-center-repair-events-section" testID="platform-trust-center-repair-events-section">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="platform-trust-center-repair-events-title" testID="platform-trust-center-repair-events-title">{tx('admin.platformTrustCenterPanel.auto.text.016', 'Recent Repair Events')}</Text>
          {fixHistoryLoading ? <ActivityIndicator size="small" color={T.primary} /> : null}
        </View>

        <View style={{ marginTop: 10, gap: 8 }} data-testid="platform-trust-center-repair-events-list" testID="platform-trust-center-repair-events-list">
          {repairEvents.length === 0 ? (
            <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="platform-trust-center-repair-events-empty" testID="platform-trust-center-repair-events-empty">{tx('admin.platformTrustCenterPanel.auto.text.017', 'No repair events found yet.')}</Text>
          ) : (
            repairEvents.map((event, index) => (
              <View
                key={event.id}
                style={{
                  backgroundColor: T.bgSoft,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: T.border,
                  padding: 10,
                  gap: 4,
                }}
                data-testid={`platform-trust-repair-event-${index}`} testID={`platform-trust-repair-event-${index}`}
              >
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <Text style={{ color: T.text, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }} data-testid={`platform-trust-repair-event-${index}-action`} testID={`platform-trust-repair-event-${index}-action`}>{event.action}</Text>
                  <View style={{ backgroundColor: statusBg(event.status), borderRadius: 999, paddingHorizontal: 7, paddingVertical: 2 }}>
                    <Text style={{ color: statusColor(event.status), fontSize: 9, fontWeight: '800' }}>{String(event.status).toUpperCase()}</Text>
                  </View>
                </View>
                <Text style={{ color: T.textSec, fontSize: 10 }} data-testid={`platform-trust-repair-event-${index}-detail`} testID={`platform-trust-repair-event-${index}-detail`}>{event.detail || 'No additional detail available.'}</Text>
                <Text style={{ color: T.textMuted, fontSize: 9 }} data-testid={`platform-trust-repair-event-${index}-time`} testID={`platform-trust-repair-event-${index}-time`}>{relativeTime(event.timestamp)}</Text>
              </View>
            ))
          )}
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 14 }} data-testid="platform-trust-center-cadence-section" testID="platform-trust-center-cadence-section">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="platform-trust-center-cadence-title" testID="platform-trust-center-cadence-title">{tx('admin.platformTrustCenterPanel.auto.text.018', 'Enforcement Cadence')}</Text>
        <View style={{ marginTop: 10, gap: 7 }}>
          {Object.keys(cadence).length === 0 ? (
            <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="platform-trust-center-cadence-empty" testID="platform-trust-center-cadence-empty">{tx('admin.platformTrustCenterPanel.auto.text.019', 'Cadence metadata unavailable.')}</Text>
          ) : (
            Object.entries(cadence).map(([key, value], idx) => (
              <View key={key} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }} data-testid={`platform-trust-cadence-${idx}`} testID={`platform-trust-cadence-${idx}`}>
                <Text style={{ color: T.textSec, fontSize: 10, textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</Text>
                <Text style={{ color: T.text, fontSize: 10, fontWeight: '700' }} data-testid={`platform-trust-cadence-${idx}-value`} testID={`platform-trust-cadence-${idx}-value`}>{String(value)}</Text>
              </View>
            ))
          )}
        </View>
      </View>
    </ScrollView>
  );
}