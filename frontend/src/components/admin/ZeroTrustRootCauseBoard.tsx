import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

type RootCauseData = {
  latest: any;
  history: any[];
  watchdogState: any;
  zeroTrustLatest: any;
  trend: any;
};

const nonPass = (value: any) => {
  const v = String(value || '').toUpperCase();
  return Boolean(v) && v !== 'PASS' && v !== 'ACTIVE' && v !== 'YES' && v !== 'NONE';
};

export default function ZeroTrustRootCauseBoard() {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [runningWatchdog, setRunningWatchdog] = useState(false);
  const [note, setNote] = useState('');
  const [data, setData] = useState<RootCauseData | null>(null);

  const fetchData = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') setLoading(true);
    else setRefreshing(true);
    try {
      const [latestRes, historyRes, watchdogRes, zeroTrustRes, trendRes] = await Promise.all([
        api.get('/admin/gtec-scan-v2/latest', { silentLoading: true }),
        api.get('/admin/gtec-scan-v2/history', { silentLoading: true }),
        api.get('/admin/gtec-scan-v2/watchdog/state', { silentLoading: true }).catch(() => ({ data: {} })),
        api.get('/admin/autonomous-engine/zero-trust/active-defense/latest', { silentLoading: true }).catch(() => ({ data: {} })),
        api.get('/admin/autonomous-engine/zero-trust/active-defense/trend?days=14', { silentLoading: true }).catch(() => ({ data: {} })),
      ]);

      setData({
        latest: latestRes.data?.report || {},
        history: Array.isArray(historyRes.data?.items) ? historyRes.data.items : [],
        watchdogState: watchdogRes.data || {},
        zeroTrustLatest: zeroTrustRes.data || {},
        trend: trendRes.data || {},
      });
      setNote('');
    } catch {
      setNote('Unable to fetch zero-trust RCA telemetry.');
      setData((prev) => prev || { latest: {}, history: [], watchdogState: {}, zeroTrustLatest: {}, trend: {} });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const runWatchdog = useCallback(async () => {
    setRunningWatchdog(true);
    try {
      const res = await api.post('/admin/gtec-scan-v2/watchdog/run');
      setNote(`Watchdog run complete: ${res.data?.status || res.data?.summary?.status || 'DONE'}`);
      await fetchData('refresh');
    } catch {
      setNote('Watchdog run failed.');
    } finally {
      setRunningWatchdog(false);
    }
  }, [fetchData]);

  useEffect(() => {
    fetchData('initial');
  }, [fetchData]);

  const latest = data?.latest || {};
  const history = data?.history || [];
  const watchdogState = data?.watchdogState || {};
  const zeroTrustLatest = data?.zeroTrustLatest || {};
  const trend = data?.trend || {};

  const failRate = useMemo(() => {
    if (!history.length) return 0;
    const failures = history.filter((item) => String(item?.status || '').toUpperCase() !== 'PASS').length;
    return Math.round((failures / history.length) * 100);
  }, [history]);

  const rootCauseVectors = useMemo(() => {
    const vectors: { key: string; label: string; value: string; weight: number; tone: string }[] = [];
    const severity = latest?.severity_counts || {};
    if (Number(severity.critical || 0) > 0) vectors.push({ key: 'critical', label: 'Critical findings', value: `${severity.critical}`, weight: 120, tone: colors.error });
    if (Number(severity.high || 0) > 0) vectors.push({ key: 'high', label: 'High findings', value: `${severity.high}`, weight: 90, tone: colors.warningText || colors.warning });
    if (nonPass(latest?.security_scan)) vectors.push({ key: 'security_scan', label: 'Security scan gate', value: String(latest?.security_scan || 'FAIL'), weight: 80, tone: colors.error });
    if (nonPass(latest?.performance)) vectors.push({ key: 'performance', label: 'Performance gate', value: String(latest?.performance || 'FAIL'), weight: 64, tone: colors.warningText || colors.warning });
    if (nonPass(latest?.rbac_status)) vectors.push({ key: 'rbac', label: 'RBAC gate', value: String(latest?.rbac_status || 'FAIL'), weight: 72, tone: colors.error });
    if (nonPass(latest?.i18n_status)) vectors.push({ key: 'i18n', label: 'i18n gate', value: String(latest?.i18n_status || 'FAIL'), weight: 55, tone: colors.warningText || colors.warning });

    const sections = zeroTrustLatest?.sections || {};
    Object.entries(sections).forEach(([name, section]: [string, any]) => {
      if (nonPass(section?.status)) {
        vectors.push({
          key: `zt_${name}`,
          label: `Zero-trust: ${name.replace(/_/g, ' ')}`,
          value: String(section?.status || 'FAIL'),
          weight: 50,
          tone: colors.error,
        });
      }
    });

    return vectors.sort((a, b) => b.weight - a.weight).slice(0, 10);
  }, [latest, zeroTrustLatest, colors.error, colors.warning, colors.warningText]);

  if (loading) {
    return (
      <View style={{ paddingVertical: 72, alignItems: 'center' }} data-testid="zero-trust-root-cause-board-loading" testID="zero-trust-root-cause-board-loading">
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 18, gap: 14 }} data-testid="zero-trust-root-cause-board" testID="zero-trust-root-cause-board">
      <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 16, gap: 12 }} data-testid="zero-trust-root-cause-hero" testID="zero-trust-root-cause-hero">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 19, fontWeight: '800' }} data-testid="zero-trust-root-cause-title" testID="zero-trust-root-cause-title">{tx('admin.zeroTrustRootCauseBoard.header.title', 'Zero-Trust Root-Cause Board')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="zero-trust-root-cause-subtitle" testID="zero-trust-root-cause-subtitle">{tx('admin.zeroTrustRootCauseBoard.header.subtitle', 'Recurring security and compliance failure vectors with watchdog escalation visibility')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={() => fetchData('refresh')}
              disabled={refreshing}
              style={{ paddingHorizontal: 11, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="zero-trust-root-cause-refresh-button"
              testID="zero-trust-root-cause-refresh-button"
            >
              {refreshing ? <ActivityIndicator size="small" color={colors.textSec} /> : <Ionicons name="refresh" size={13} color={colors.textSec} />}
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.zeroTrustRootCauseBoard.actions.refresh', 'Refresh')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runWatchdog}
              disabled={runningWatchdog}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: runningWatchdog ? `${colors.error}66` : colors.error, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="zero-trust-root-cause-run-watchdog-button"
              testID="zero-trust-root-cause-run-watchdog-button"
            >
              {runningWatchdog ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="shield-checkmark" size={13} color={colors.primaryText} />}
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{runningWatchdog ? 'Running...' : 'Run Watchdog'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {note ? (
          <View style={{ borderWidth: 1, borderColor: `${colors.primary}35`, backgroundColor: `${colors.primary}12`, borderRadius: 10, padding: 9 }} data-testid="zero-trust-root-cause-note" testID="zero-trust-root-cause-note">
            <Text style={{ color: colors.text, fontSize: 11 }}>{note}</Text>
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="zero-trust-root-cause-metrics" testID="zero-trust-root-cause-metrics">
          {[
            { label: 'Latest GTEC Status', value: String(latest?.status || 'NOT_RUN'), tone: String(latest?.status || '').toUpperCase() === 'PASS' ? colors.successText || colors.success : colors.error },
            { label: 'Latest Zero-Trust', value: String(zeroTrustLatest?.zero_trust_status || 'NOT_SCANNED'), tone: String(zeroTrustLatest?.zero_trust_status || '').toUpperCase() === 'PASS' ? colors.successText || colors.success : colors.error },
            { label: 'History Failure Rate', value: `${failRate}%`, tone: failRate > 40 ? colors.error : colors.warningText || colors.warning },
            { label: 'Watchdog Cleared', value: `${watchdogState?.summary?.cleared || watchdogState?.cleared_count || 0}`, tone: colors.accent || colors.primary },
          ].map((metric) => (
            <View key={metric.label} style={{ flex: 1, minWidth: 150, borderWidth: 1, borderColor: `${metric.tone}35`, backgroundColor: `${metric.tone}12`, borderRadius: 12, padding: 10 }} data-testid={`zero-trust-root-cause-metric-${metric.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`zero-trust-root-cause-metric-${metric.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
              <Text style={{ color: colors.textMuted, fontSize: 9, textTransform: 'uppercase', fontWeight: '700' }}>{metric.label}</Text>
              <Text style={{ color: metric.tone, fontSize: 16, marginTop: 5, fontWeight: '900' }}>{metric.value}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="zero-trust-root-cause-vectors-card" testID="zero-trust-root-cause-vectors-card">
        <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="zero-trust-root-cause-vectors-title" testID="zero-trust-root-cause-vectors-title">{tx('admin.zeroTrustRootCauseBoard.vectors.title', 'Top Root-Cause Vectors')}</Text>
        {rootCauseVectors.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="zero-trust-root-cause-vectors-empty" testID="zero-trust-root-cause-vectors-empty">{tx('admin.zeroTrustRootCauseBoard.vectors.empty', 'No active failure vectors detected in the latest scans.')}</Text>
        ) : rootCauseVectors.map((vector, index) => (
          <View key={vector.key} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.surfaceHover, padding: 10, gap: 4 }} data-testid={`zero-trust-root-cause-vector-${index + 1}`} testID={`zero-trust-root-cause-vector-${index + 1}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800', flex: 1 }}>{vector.label}</Text>
              <Text style={{ color: vector.tone, fontSize: 11, fontWeight: '800' }}>{vector.value}</Text>
            </View>
            <View style={{ height: 6, borderRadius: 3, backgroundColor: colors.border }}>
              <View style={{ width: `${Math.min(100, vector.weight)}%`, height: 6, borderRadius: 3, backgroundColor: vector.tone }} />
            </View>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <View style={{ flex: 1.05, minWidth: 330, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="zero-trust-root-cause-history-card" testID="zero-trust-root-cause-history-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="zero-trust-root-cause-history-title" testID="zero-trust-root-cause-history-title">{tx('admin.zeroTrustRootCauseBoard.history.title', 'Recent GTEC History')}</Text>
          {history.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="zero-trust-root-cause-history-empty" testID="zero-trust-root-cause-history-empty">{tx('admin.zeroTrustRootCauseBoard.history.empty', 'No history rows available.')}</Text>
          ) : history.slice(0, 8).map((row: any, index: number) => {
            const isPass = String(row?.status || '').toUpperCase() === 'PASS';
            return (
              <View key={row?.task_id || index} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.surfaceHover, padding: 9, gap: 3 }} data-testid={`zero-trust-root-cause-history-row-${index + 1}`} testID={`zero-trust-root-cause-history-row-${index + 1}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <Text style={{ color: colors.text, fontSize: 10, fontWeight: '800', flex: 1 }} numberOfLines={1}>{row?.task_id || 'unknown_task'}</Text>
                  <Text style={{ color: isPass ? colors.successText || colors.success : colors.error, fontSize: 10, fontWeight: '800' }}>{String(row?.status || 'UNKNOWN')}</Text>
                </View>
                <Text style={{ color: colors.textSec, fontSize: 10 }}>Critical {row?.critical_vulns || 0} • High {row?.high_vulns || 0} • Medium {row?.medium_vulns || 0}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 9 }}>{row?.generated_at ? new Date(row.generated_at).toLocaleString() : 'Unknown time'}</Text>
              </View>
            );
          })}
        </View>

        <View style={{ flex: 0.95, minWidth: 320, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="zero-trust-root-cause-watchdog-card" testID="zero-trust-root-cause-watchdog-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="zero-trust-root-cause-watchdog-title" testID="zero-trust-root-cause-watchdog-title">{tx('admin.zeroTrustRootCauseBoard.watchdog.title', 'Watchdog + Trend Snapshot')}</Text>

          <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="zero-trust-root-cause-watchdog-summary" testID="zero-trust-root-cause-watchdog-summary">
            Last checked {watchdogState?.last_checked_at ? new Date(watchdogState.last_checked_at).toLocaleString() : 'N/A'}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="zero-trust-root-cause-watchdog-open-blockers" testID="zero-trust-root-cause-watchdog-open-blockers">
            Open blockers: {watchdogState?.summary?.open_blockers || watchdogState?.open_blockers || 0}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="zero-trust-root-cause-trend-pass-rate" testID="zero-trust-root-cause-trend-pass-rate">
            14-day pass rate: {trend?.pass_rate || 0}% • scans: {trend?.total_scans || 0}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="zero-trust-root-cause-trend-blocked" testID="zero-trust-root-cause-trend-blocked">
            Auto-blocked IPs: {trend?.total_blocked_ips || 0}
          </Text>
        </View>
      </View>
    </ScrollView>
  );
}
