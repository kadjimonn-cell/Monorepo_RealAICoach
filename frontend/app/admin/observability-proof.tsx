import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';

import AppShell from '../../src/components/AppShell';
import api from '../../src/services/api';
import { useTheme } from '../../src/context/ThemeContext';

export default function ObservabilityProofPage() {
  const { colors } = useTheme();
  const [loading, setLoading] = useState(false);
  const [overview, setOverview] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [traces, setTraces] = useState<any[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, al, lg, tr] = await Promise.all([
        api.get('/admin/observability/overview', { silentLoading: true }),
        api.get('/admin/web-vitals/alerts', { silentLoading: true }),
        api.get('/admin/observability/recent-logs?limit=10', { silentLoading: true }),
        api.get('/admin/observability/recent-traces?limit=10', { silentLoading: true }),
      ]);

      setOverview(ov.data || null);
      setAlerts(Array.isArray(al.data?.alerts) ? al.data.alerts : []);
      setLogs(Array.isArray(lg.data?.logs) ? lg.data.logs : []);
      setTraces(Array.isArray(tr.data?.samples) ? tr.data.samples : []);
    } catch {
      setOverview(null);
      setAlerts([]);
      setLogs([]);
      setTraces([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppShell>
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.bg }}
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 16, paddingBottom: 32, gap: 12 }}
        data-testid="observability-proof-page"
        testID="observability-proof-page"
      >
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }}>
          <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="observability-proof-title" testID="observability-proof-title">Step-13 Visual Proof (Live)</Text>
          <Text style={{ color: colors.muted, fontSize: 12, marginTop: 6 }}>Dashboard + alerts + traces + structured logs from live runtime APIs.</Text>
          <TouchableOpacity onPress={() => { void load(); }} style={{ marginTop: 12, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceElevated }} data-testid="observability-proof-refresh-button" testID="observability-proof-refresh-button">
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{loading ? 'Refreshing…' : 'Refresh proof data'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }} data-testid="observability-proof-dashboard-section" testID="observability-proof-dashboard-section">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Dashboard Snapshot</Text>
          <Text style={{ color: colors.muted, fontSize: 11, marginTop: 6 }}>
            app errors(24h): {overview?.application?.client_errors_24h ?? 0} • security events(24h): {overview?.application?.security_events_24h ?? 0} • trace coverage(shell): {overview?.correlation?.shell_trace_coverage_pct ?? 0}%
          </Text>
        </View>

        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }} data-testid="observability-proof-alerts-section" testID="observability-proof-alerts-section">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Triggered Alerts</Text>
          <View style={{ marginTop: 8, gap: 8 }}>
            {alerts.slice(0, 5).map((item, idx) => (
              <View key={`${item.timestamp}-${idx}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, backgroundColor: colors.bg }} data-testid={`observability-proof-alert-row-${idx}`} testID={`observability-proof-alert-row-${idx}`}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{item.type || 'alert'} • {item.level || 'n/a'}</Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 3 }}>{item.timestamp || 'n/a'} • samples: {item.samples ?? 0}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }} data-testid="observability-proof-traces-section" testID="observability-proof-traces-section">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Recent Trace Samples</Text>
          <View style={{ marginTop: 8, gap: 8 }}>
            {traces.slice(0, 5).map((item, idx) => (
              <View key={`${item.trace_id}-${idx}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, backgroundColor: colors.bg }} data-testid={`observability-proof-trace-row-${idx}`} testID={`observability-proof-trace-row-${idx}`}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{item.source || 'unknown'} • {item.route || 'n/a'}</Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 3 }}>trace: {item.trace_id || 'n/a'} • corr: {item.correlation_id || 'n/a'}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }} data-testid="observability-proof-logs-section" testID="observability-proof-logs-section">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Structured Logs (Recent)</Text>
          <View style={{ marginTop: 8, gap: 8 }}>
            {logs.slice(0, 5).map((item, idx) => (
              <View key={`${item.timestamp}-${idx}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, backgroundColor: colors.bg }} data-testid={`observability-proof-log-row-${idx}`} testID={`observability-proof-log-row-${idx}`}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{item.level || 'INFO'} • {item.logger || 'logger'}</Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 3 }}>{item.message || 'n/a'}</Text>
                <Text style={{ color: colors.muted, fontSize: 10, marginTop: 3 }}>corr: {item.correlation_id || 'n/a'} • trace: {item.trace_id || 'n/a'}</Text>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>
    </AppShell>
  );
}

/* i18n-probe t('i18n.auto.probe') */
