import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Platform, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

type Props = {
  colors: any;
};

export default function PreviewBrowserE2ECard({ colors }: Props) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState('');
  const [latest, setLatest] = useState<any>({});
  const [trend, setTrend] = useState<any>({ total: 0, pass_count: 0, fail_count: 0, blocked_count: 0, pass_rate: 0, window_days: 7 });
  const [alertState, setAlertState] = useState<any>({});
  const [heartbeat, setHeartbeat] = useState<any>({});
  const [liveCheckLoading, setLiveCheckLoading] = useState(false);
  const [liveCheck, setLiveCheck] = useState<any>({});
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
  const liveCheckInFlightRef = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/platform-health/preview-browser-e2e/latest?limit=20&window_days=7', { silentLoading: true });
      setLatest(res?.data?.latest || {});
      setTrend(res?.data?.trend || { total: 0, pass_count: 0, fail_count: 0, blocked_count: 0, pass_rate: 0, window_days: 7 });
      setAlertState(res?.data?.alert_state || {});
      setHeartbeat(res?.data?.heartbeat || {});
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.previewBrowserE2E.messages.loadFailed', 'Failed to load nightly browser E2E monitor.'));
    } finally {
      setLoading(false);
    }
  }, [tx]);

  useEffect(() => {
    void load();
  }, [load]);

  const runLiveCheck = useCallback(async (force = false) => {
    if (liveCheckInFlightRef.current) {
      return;
    }
    liveCheckInFlightRef.current = true;
    setLiveCheckLoading(true);
    setMessage('');
    try {
      const suffix = force ? '?force=true' : '';
      const res = await api.get(`/admin/platform-health/preview-adapter-live-check${suffix}`, { silentLoading: true });
      setLiveCheck(res?.data || {});
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.previewBrowserE2E.messages.liveCheckFailed', 'Failed to run preview adapter live check.'));
    } finally {
      setLiveCheckLoading(false);
      liveCheckInFlightRef.current = false;
    }
  }, [tx]);

  useEffect(() => {
    void runLiveCheck(false);
  }, [runLiveCheck]);

  useHybridPolling({
    enabled: autoRefreshEnabled,
    errorScope: 'admin/preview-browser-e2e/hybrid-refresh',
    onTick: () => runLiveCheck(true),
    runOnMount: false,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  const runNow = useCallback(async () => {
    setRunning(true);
    setMessage('');
    try {
      const res = await api.post('/admin/platform-health/preview-browser-e2e/run?triggered_by=manual:admin');
      if (res?.data?.accepted) {
        setMessage(tx('operationsConsole.previewBrowserE2E.messages.runAccepted', 'Browser E2E run accepted and started.'));
      }
      setTimeout(() => {
        void load();
      }, 2000);
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.previewBrowserE2E.messages.runFailed', 'Failed to start browser E2E run.'));
    } finally {
      setRunning(false);
    }
  }, [load, tx]);

  const status = useMemo(() => String(latest?.status || 'unknown').toUpperCase(), [latest?.status]);
  const statusColor = status === 'PASS' ? colors.successText : status === 'FAIL' ? colors.error : status === 'BLOCKED' ? colors.warning : colors.textMuted;
  const reasonCode = useMemo(() => String(latest?.status_reason_code || latest?.blocking_reason || 'N/A'), [latest?.status_reason_code, latest?.blocking_reason]);
  const externalLaneStatus = useMemo(() => String(latest?.external_lane_status || 'unknown').toUpperCase(), [latest?.external_lane_status]);
  const localhostFallbackStatus = useMemo(() => String(latest?.localhost_fallback_status || 'not_run').toUpperCase(), [latest?.localhost_fallback_status]);
  const liveStatus = useMemo(() => String(liveCheck?.status || 'unknown').toUpperCase(), [liveCheck?.status]);
  const liveStatusColor = liveStatus === 'PASS' ? colors.successText : liveStatus === 'FAIL' ? colors.error : colors.textMuted;
  const liveRootCheck = useMemo(() => liveCheck?.checks?.preview_root || {}, [liveCheck?.checks?.preview_root]);
  const liveApiHealthCheck = useMemo(() => liveCheck?.checks?.api_health || {}, [liveCheck?.checks?.api_health]);
  const liveFailureReasons = useMemo(() => (
    Array.isArray(liveCheck?.failure_reasons) ? liveCheck.failure_reasons.slice(0, 2) : []
  ), [liveCheck?.failure_reasons]);

  const screenshotList = useMemo(() => (
    Array.isArray(latest?.screenshots) ? latest.screenshots.slice(0, 4) : []
  ), [latest?.screenshots]);

  const openScreenshot = useCallback((path: string) => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.open(path, '_blank', 'noopener,noreferrer');
      return;
    }
    setMessage(tx('operationsConsole.previewBrowserE2E.messages.webOnlyOpen', 'Screenshot link open is available in web console.'));
  }, [tx]);

  return (
    <View
      style={{
        marginTop: 12,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.card,
        padding: 12,
        gap: 8,
      }}
      data-testid="preview-browser-e2e-card"
      testID="preview-browser-e2e-card"
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="preview-browser-e2e-card-title" testID="preview-browser-e2e-card-title">
            {tx('operationsConsole.previewBrowserE2E.title', 'Nightly Browser E2E Wake-and-Run')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }} data-testid="preview-browser-e2e-card-subtitle" testID="preview-browser-e2e-card-subtitle">
            {tx('operationsConsole.previewBrowserE2E.subtitle', 'State-change alerts + 7-day trend with route screenshot evidence.')}
          </Text>
        </View>
        <View style={{ borderRadius: 999, backgroundColor: `${statusColor}20`, paddingHorizontal: 10, paddingVertical: 4 }} data-testid="preview-browser-e2e-card-status-pill" testID="preview-browser-e2e-card-status-pill">
          <Text style={{ color: statusColor, fontSize: 10, fontWeight: '800' }} data-testid="preview-browser-e2e-card-status-text" testID="preview-browser-e2e-card-status-text">{status}</Text>
        </View>
      </View>

      {loading ? (
        <View style={{ paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="preview-browser-e2e-card-loading" testID="preview-browser-e2e-card-loading">
          <ActivityIndicator size="small" color={colors.primary} />
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('operationsConsole.previewBrowserE2E.loading', 'Loading monitor...')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-reason-code" testID="preview-browser-e2e-card-reason-code">
              {tx('operationsConsole.previewBrowserE2E.reasonCode', 'Reason code')}: {reasonCode || 'PENDING_LOAD'}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-lane-status" testID="preview-browser-e2e-card-lane-status">
              {tx('operationsConsole.previewBrowserE2E.laneStatus', 'External/Localhost lane')}: {externalLaneStatus} / {localhostFallbackStatus}
            </Text>
          </View>
        </View>
      ) : (
        <>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-last-run" testID="preview-browser-e2e-card-last-run">
            {tx('operationsConsole.previewBrowserE2E.lastRun', 'Last run')}: {latest?.ran_at ? new Date(latest.ran_at).toLocaleString() : tx('operationsConsole.previewBrowserE2E.never', 'Never')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-trend" testID="preview-browser-e2e-card-trend">
            {tx('operationsConsole.previewBrowserE2E.trend', '7-day pass rate')}: {trend?.pass_rate || 0}% ({trend?.pass_count || 0}/{trend?.total || 0})
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-trend-breakdown" testID="preview-browser-e2e-card-trend-breakdown">
            {tx('operationsConsole.previewBrowserE2E.breakdown', 'Fail/Blocked')}: {trend?.fail_count || 0}/{trend?.blocked_count || 0}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-heartbeat" testID="preview-browser-e2e-card-heartbeat">
            {tx('operationsConsole.previewBrowserE2E.heartbeat', 'Scheduler heartbeat')}: {String(heartbeat?.status || 'unknown').toUpperCase()} • {heartbeat?.last_run ? new Date(heartbeat.last_run).toLocaleString() : '-'}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-transition" testID="preview-browser-e2e-card-transition">
            {tx('operationsConsole.previewBrowserE2E.transition', 'Last transition')}: {alertState?.transition || 'N/A'}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-reason-code" testID="preview-browser-e2e-card-reason-code">
            {tx('operationsConsole.previewBrowserE2E.reasonCode', 'Reason code')}: {reasonCode}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-browser-e2e-card-lane-status" testID="preview-browser-e2e-card-lane-status">
            {tx('operationsConsole.previewBrowserE2E.laneStatus', 'External/Localhost lane')}: {externalLaneStatus} / {localhostFallbackStatus}
          </Text>

          <View
            style={{
              marginTop: 6,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.surface,
              padding: 10,
              gap: 6,
            }}
            data-testid="preview-adapter-live-check-block"
            testID="preview-adapter-live-check-block"
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }} data-testid="preview-adapter-live-check-title" testID="preview-adapter-live-check-title">
                {tx('operationsConsole.previewBrowserE2E.liveCheck.title', 'Preview Adapter Live Check')}
              </Text>
              <View style={{ borderRadius: 999, backgroundColor: `${liveStatusColor}20`, paddingHorizontal: 8, paddingVertical: 3 }} data-testid="preview-adapter-live-check-status-pill" testID="preview-adapter-live-check-status-pill">
                <Text style={{ color: liveStatusColor, fontSize: 10, fontWeight: '800' }} data-testid="preview-adapter-live-check-status-text" testID="preview-adapter-live-check-status-text">
                  {liveStatus}
                </Text>
              </View>
            </View>

            <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-adapter-live-check-last-checked" testID="preview-adapter-live-check-last-checked">
              {tx('operationsConsole.previewBrowserE2E.liveCheck.lastChecked', 'Last checked')}: {liveCheck?.checked_at ? new Date(liveCheck.checked_at).toLocaleString() : tx('operationsConsole.previewBrowserE2E.never', 'Never')}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-adapter-live-check-root-result" testID="preview-adapter-live-check-root-result">
              {tx('operationsConsole.previewBrowserE2E.liveCheck.root', 'Preview root')}: {liveRootCheck?.ok ? tx('operationsConsole.previewBrowserE2E.liveCheck.pass', 'PASS') : tx('operationsConsole.previewBrowserE2E.liveCheck.fail', 'FAIL')} • HTTP {liveRootCheck?.status_code || 0}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-adapter-live-check-api-health-result" testID="preview-adapter-live-check-api-health-result">
              {tx('operationsConsole.previewBrowserE2E.liveCheck.apiHealth', '/api/health')}: {liveApiHealthCheck?.ok ? tx('operationsConsole.previewBrowserE2E.liveCheck.pass', 'PASS') : tx('operationsConsole.previewBrowserE2E.liveCheck.fail', 'FAIL')} • HTTP {liveApiHealthCheck?.status_code || 0}
            </Text>

            {liveFailureReasons.length > 0 ? (
              <View data-testid="preview-adapter-live-check-failure-reasons" testID="preview-adapter-live-check-failure-reasons">
                {liveFailureReasons.map((reason: string, idx: number) => (
                  <Text
                    key={`${reason}-${idx}`}
                    style={{ color: colors.warning, fontSize: 10 }}
                    data-testid={`preview-adapter-live-check-failure-reason-${idx}`}
                    testID={`preview-adapter-live-check-failure-reason-${idx}`}
                  >
                    • {reason}
                  </Text>
                ))}
              </View>
            ) : null}

            {liveCheckLoading ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="preview-adapter-live-check-loading-row" testID="preview-adapter-live-check-loading-row">
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-adapter-live-check-loading-text" testID="preview-adapter-live-check-loading-text">
                  {tx('operationsConsole.previewBrowserE2E.liveCheck.loading', 'Running live check...')}
                </Text>
              </View>
            ) : null}

            <View
              style={{
                marginTop: 2,
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
              }}
              data-testid="preview-adapter-live-check-auto-refresh-row"
              testID="preview-adapter-live-check-auto-refresh-row"
            >
              <Text
                style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}
                data-testid="preview-adapter-live-check-auto-refresh-status"
                testID="preview-adapter-live-check-auto-refresh-status"
              >
                {tx('operationsConsole.previewBrowserE2E.liveCheck.autoRefresh', 'Auto-refresh (60s)')}: {autoRefreshEnabled ? tx('operationsConsole.previewBrowserE2E.liveCheck.enabled', 'ON') : tx('operationsConsole.previewBrowserE2E.liveCheck.disabled', 'OFF')}
              </Text>

              <TouchableOpacity accessibilityLabel="Preview adapter live check auto refresh toggle button"
                onPress={() => setAutoRefreshEnabled((prev: boolean) => !prev)}
                style={{
                  borderRadius: 999,
                  paddingHorizontal: 10,
                  paddingVertical: 6,
                  backgroundColor: autoRefreshEnabled ? `${colors.successText}22` : `${colors.textMuted}22`,
                  borderWidth: 1,
                  borderColor: autoRefreshEnabled ? `${colors.successText}55` : `${colors.border}`,
                }}
                data-testid="preview-adapter-live-check-auto-refresh-toggle"
                testID="preview-adapter-live-check-auto-refresh-toggle"
              >
                <Text style={{ color: autoRefreshEnabled ? colors.successText : colors.textMuted, fontSize: 10, fontWeight: '800' }}>
                  {autoRefreshEnabled ? tx('operationsConsole.previewBrowserE2E.liveCheck.turnOff', 'Turn Off') : tx('operationsConsole.previewBrowserE2E.liveCheck.turnOn', 'Turn On')}
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {screenshotList.length > 0 ? (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="preview-browser-e2e-card-screenshot-list" testID="preview-browser-e2e-card-screenshot-list">
              {screenshotList.map((path: string, idx: number) => (
                <TouchableOpacity accessibilityLabel="Open screenshot in preview browser e2 ecard button"
                  key={`${path}-${idx}`}
                  onPress={() => openScreenshot(path)}
                  style={{
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: colors.border,
                    backgroundColor: `${colors.primary}12`,
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                  }}
                  data-testid={`preview-browser-e2e-card-open-screenshot-${idx}`}
                  testID={`preview-browser-e2e-card-open-screenshot-${idx}`}
                >
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '700' }}>
                    {tx('operationsConsole.previewBrowserE2E.openScreenshot', 'Open screenshot')} {idx + 1}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}
        </>
      )}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        <TouchableOpacity accessibilityLabel="Preview browser e2e card run now button"
          onPress={runNow}
          disabled={running}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
            borderRadius: 9,
            paddingHorizontal: 12,
            paddingVertical: 8,
            backgroundColor: colors.primary,
            opacity: running ? 0.7 : 1,
          }}
          data-testid="preview-browser-e2e-card-run-now-button"
          testID="preview-browser-e2e-card-run-now-button"
        >
          {running ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="play-circle-outline" size={14} color={colors.primaryText} />}
          <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>
            {running
              ? tx('operationsConsole.previewBrowserE2E.running', 'Starting...')
              : tx('operationsConsole.previewBrowserE2E.runNow', 'Run Browser E2E Now')}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity accessibilityLabel="Preview browser e2e card refresh button"
          onPress={() => void load()}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
            borderRadius: 9,
            paddingHorizontal: 12,
            paddingVertical: 8,
            backgroundColor: `${colors.info}18`,
            borderWidth: 1,
            borderColor: `${colors.info}45`,
          }}
          data-testid="preview-browser-e2e-card-refresh-button"
          testID="preview-browser-e2e-card-refresh-button"
        >
          <Ionicons name="refresh-outline" size={14} color={colors.info} />
          <Text style={{ color: colors.info, fontSize: 11, fontWeight: '800' }}>
            {tx('operationsConsole.previewBrowserE2E.refresh', 'Refresh Status')}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity accessibilityLabel="Preview adapter live check run button"
          onPress={() => void runLiveCheck(true)}
          disabled={liveCheckLoading}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
            borderRadius: 9,
            paddingHorizontal: 12,
            paddingVertical: 8,
            backgroundColor: `${colors.successText}16`,
            borderWidth: 1,
            borderColor: `${colors.successText}48`,
            opacity: liveCheckLoading ? 0.7 : 1,
          }}
          data-testid="preview-adapter-live-check-run-button"
          testID="preview-adapter-live-check-run-button"
        >
          {liveCheckLoading ? <ActivityIndicator size="small" color={colors.successText} /> : <Ionicons name="pulse-outline" size={14} color={colors.successText} />}
          <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800' }} data-testid="preview-adapter-live-check-run-button-text" testID="preview-adapter-live-check-run-button-text">
            {liveCheckLoading
              ? tx('operationsConsole.previewBrowserE2E.liveCheck.running', 'Checking...')
              : tx('operationsConsole.previewBrowserE2E.liveCheck.runNow', 'Run Live Check')}
          </Text>
        </TouchableOpacity>
      </View>

      {message ? (
        <Text style={{ color: colors.warning, fontSize: 10 }} data-testid="preview-browser-e2e-card-message" testID="preview-browser-e2e-card-message">{message}</Text>
      ) : null}
    </View>
  );
}
