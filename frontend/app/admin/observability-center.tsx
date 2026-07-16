import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';

import AppShell from '../../src/components/AppShell';
import api from '../../src/services/api';
import { useTheme } from '../../src/context/ThemeContext';

type OverviewPayload = any;

export default function ObservabilityCenterPage() {
  const { colors } = useTheme();
  const [loading, setLoading] = useState(false);
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [correlationRows, setCorrelationRows] = useState<any[]>([]);

  const appSummary = overview?.application || {};
  const uxSummary = overview?.frontend_experience || {};
  const alertSummary = overview?.alerts || {};
  const gpsSummary = overview?.gps_health || {};

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [overviewRes, auditRes] = await Promise.all([
        api.get('/admin/observability/overview', { silentLoading: true }),
        api.get('/admin/observability/correlation-audit', { silentLoading: true }),
      ]);
      setOverview(overviewRes.data || null);
      setCorrelationRows(Array.isArray(auditRes.data?.rows) ? auditRes.data.rows : []);
    } catch {
      setOverview(null);
      setCorrelationRows([]);
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
        data-testid="admin-observability-center-page"
        testID="admin-observability-center-page"
      >
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }}>
          <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="admin-observability-center-title" testID="admin-observability-center-title">
            Unified Observability Center
          </Text>
          <Text style={{ color: colors.muted, fontSize: 12, marginTop: 6 }} data-testid="admin-observability-center-subtitle" testID="admin-observability-center-subtitle">
            Real-time health, UX vitals, alerts, and correlation coverage from live platform telemetry.
          </Text>

          <TouchableOpacity
            onPress={() => { void load(); }}
            style={{ marginTop: 12, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceElevated }}
            data-testid="admin-observability-refresh-button"
            testID="admin-observability-refresh-button"
          >
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{loading ? 'Refreshing…' : 'Refresh live data'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }} data-testid="admin-observability-overview-card" testID="admin-observability-overview-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>System & App Summary</Text>
          {overview ? (
            <View style={{ marginTop: 10, gap: 8 }}>
              <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, backgroundColor: colors.bg }} data-testid="admin-observability-app-summary" testID="admin-observability-app-summary">
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>Application</Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 4 }}>
                  snapshots (1h): {appSummary.api_snapshots_1h ?? 0} • perf alerts (24h): {appSummary.perf_alerts_24h ?? 0}
                </Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 2 }}>
                  client errors (24h): {appSummary.client_errors_24h ?? 0} • security events (24h): {appSummary.security_events_24h ?? 0}
                </Text>
              </View>

              <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, backgroundColor: colors.bg }} data-testid="admin-observability-ux-summary" testID="admin-observability-ux-summary">
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>Frontend Experience (24h)</Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 4 }}>
                  samples: {uxSummary.samples_24h ?? 0} • LCP: {uxSummary.avg_lcp ?? 0} • CLS: {uxSummary.avg_cls ?? 0}
                </Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 2 }}>
                  INP: {uxSummary.avg_inp ?? 0} • TTFB: {uxSummary.avg_ttfb ?? 0}
                </Text>
              </View>

              <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, backgroundColor: colors.bg }} data-testid="admin-observability-alerts-summary" testID="admin-observability-alerts-summary">
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>Alerts & GPS</Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 4 }}>
                  SIEM open: {alertSummary.siem_open ?? 0} • performance alerts (24h): {alertSummary.performance_24h ?? 0}
                </Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 2 }}>
                  GPS component: {gpsSummary.component || 'n/a'} • severity: {gpsSummary.severity || 'n/a'}
                </Text>
              </View>
            </View>
          ) : (
            <Text style={{ color: colors.muted, fontSize: 12, marginTop: 8 }} data-testid="admin-observability-overview-empty" testID="admin-observability-overview-empty">No data yet.</Text>
          )}
        </View>

        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.card, padding: 14 }} data-testid="admin-observability-correlation-card" testID="admin-observability-correlation-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>Correlation Coverage (24h)</Text>
          <View style={{ marginTop: 10, gap: 8 }}>
            {correlationRows.map((row, index) => (
              <View key={`${row.collection}-${index}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 10, backgroundColor: colors.bg }} data-testid={`admin-observability-correlation-row-${index}`} testID={`admin-observability-correlation-row-${index}`}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{row.collection}</Text>
                <Text style={{ color: colors.muted, fontSize: 11, marginTop: 4 }}>
                  trace: {row.with_trace_id}/{row.total} ({row.trace_coverage_pct}%) • correlation: {row.with_correlation_id}/{row.total} ({row.correlation_coverage_pct}%)
                </Text>
              </View>
            ))}
            {!correlationRows.length ? (
              <Text style={{ color: colors.muted, fontSize: 12 }} data-testid="admin-observability-correlation-empty" testID="admin-observability-correlation-empty">No correlation rows available.</Text>
            ) : null}
          </View>
        </View>
      </ScrollView>
    </AppShell>
  );
}

/* i18n-probe t('i18n.auto.probe') */
