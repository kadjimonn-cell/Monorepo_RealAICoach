import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

type ThemeData = {
  healthOverview: any;
  compliance: any;
  guardrailStatus: any;
};

const tx = (_key: string, fallback: string) => fallback;

export default function ThemeGovernanceDashboard() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [running, setRunning] = useState(false);
  const [data, setData] = useState<ThemeData | null>(null);
  const [note, setNote] = useState('');

  const fetchData = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') setLoading(true);
    else setRefreshing(true);
    try {
      const [overviewRes, complianceRes, guardrailRes] = await Promise.all([
        api.get('/admin/autonomous-engine/theme-health-center/overview?matrix_limit=50&run_limit=10&ticket_limit=12', { silentLoading: true }),
        api.get('/admin/platform-perf/theme-compliance-summary', { silentLoading: true }),
        api.get('/admin/autonomous-engine/theme-guardrail/status', { silentLoading: true }),
      ]);
      setData({
        healthOverview: overviewRes.data || {},
        compliance: complianceRes.data || {},
        guardrailStatus: guardrailRes.data || {},
      });
      setNote('');
    } catch {
      setNote('Unable to refresh governance telemetry right now.');
      setData((prev) => prev || { healthOverview: {}, compliance: {}, guardrailStatus: {} });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const runGuardrailNow = useCallback(async () => {
    setRunning(true);
    try {
      const res = await api.post('/admin/autonomous-engine/theme-guardrail/run');
      setNote(`Guardrail run ${res.data?.run_id || ''} finished with ${res.data?.status || 'UNKNOWN'}.`);
      await fetchData('refresh');
    } catch {
      setNote('Guardrail run failed.');
    } finally {
      setRunning(false);
    }
  }, [fetchData]);

  useEffect(() => {
    fetchData('initial');
  }, [fetchData]);

  const latestScan = data?.healthOverview?.latest_scan || {};
  const matrixSummary = data?.healthOverview?.matrix_summary || {};
  const openTickets = Array.isArray(data?.healthOverview?.open_tickets) ? data?.healthOverview.open_tickets : [];
  const routePassMatrix = Array.isArray(data?.healthOverview?.route_pass_matrix) ? data?.healthOverview.route_pass_matrix : [];
  const timeline = Array.isArray(data?.healthOverview?.regression_timeline) ? data?.healthOverview.regression_timeline : [];
  const complianceCurrent = data?.compliance?.current || {};
  const guardrailStatus = data?.guardrailStatus || {};

  const riskyRoutes = useMemo(
    () => routePassMatrix.filter((row: any) => row?.status !== 'pass').slice(0, 8),
    [routePassMatrix],
  );

  if (loading) {
    return (
      <View style={{ paddingVertical: 72, alignItems: 'center' }} data-testid="theme-governance-dashboard-loading" testID="theme-governance-dashboard-loading">
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 18, gap: 14 }} data-testid="theme-governance-dashboard" testID="theme-governance-dashboard">
      <View style={{ backgroundColor: colors.card, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 16, gap: 12 }} data-testid="theme-governance-hero" testID="theme-governance-hero">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 19, fontWeight: '800' }} data-testid="theme-governance-title" testID="theme-governance-title">{tx('admin.themeGovernanceDashboard.auto.text.001', 'Theme Governance Dashboard')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="theme-governance-subtitle" testID="theme-governance-subtitle">{tx('admin.themeGovernanceDashboard.auto.text.002', 'Zero-trust oversight for token drift, route parity, and remediation lifecycle')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={() => fetchData('refresh')}
              disabled={refreshing}
              style={{ paddingHorizontal: 11, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="theme-governance-refresh-button"
              testID="theme-governance-refresh-button"
            >
              {refreshing ? <ActivityIndicator size="small" color={colors.textSec} /> : <Ionicons name="refresh" size={13} color={colors.textSec} />}
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.themeGovernanceDashboard.auto.text.003', 'Refresh')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runGuardrailNow}
              disabled={running}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: running ? `${colors.primary}66` : colors.primary, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="theme-governance-run-guardrail-button"
              testID="theme-governance-run-guardrail-button"
            >
              {running ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="flash" size={13} color={colors.primaryText} />}
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{running ? 'Running...' : 'Run Guardrail'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {note ? (
          <View style={{ backgroundColor: `${colors.accent || colors.primary}15`, borderWidth: 1, borderColor: `${colors.accent || colors.primary}35`, borderRadius: 10, padding: 9 }} data-testid="theme-governance-note" testID="theme-governance-note">
            <Text style={{ color: colors.text, fontSize: 11 }}>{note}</Text>
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="theme-governance-kpi-row" testID="theme-governance-kpi-row">
          {[
            { label: 'Compliance Grade', value: complianceCurrent.grade || '—', tone: colors.primary },
            { label: 'Guardrail Score', value: `${guardrailStatus.theme_guardrail_score || latestScan.theme_guardrail_score || 0}`, tone: colors.successText || colors.success },
            { label: 'Attention Routes', value: `${matrixSummary.attention || 0}`, tone: colors.error },
            { label: 'Open Drift Tickets', value: `${openTickets.length}`, tone: colors.warningText || colors.warning },
          ].map((metric) => (
            <View key={metric.label} style={{ flex: 1, minWidth: 140, backgroundColor: `${metric.tone}12`, borderWidth: 1, borderColor: `${metric.tone}30`, borderRadius: 12, padding: 10 }} data-testid={`theme-governance-metric-${metric.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`theme-governance-metric-${metric.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{metric.label}</Text>
              <Text style={{ color: metric.tone, fontSize: 18, fontWeight: '900', marginTop: 5 }}>{metric.value}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <View style={{ flex: 1.1, minWidth: 340, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="theme-governance-risky-routes-card" testID="theme-governance-risky-routes-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="theme-governance-risky-routes-title" testID="theme-governance-risky-routes-title">{tx('admin.themeGovernanceDashboard.auto.text.004', 'Routes Requiring Governance Action')}</Text>
          {riskyRoutes.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="theme-governance-risky-routes-empty" testID="theme-governance-risky-routes-empty">{tx('admin.themeGovernanceDashboard.auto.text.005', 'No risky routes detected in current matrix.')}</Text>
          ) : riskyRoutes.map((row: any, index: number) => {
            const tone = row?.status === 'attention' ? colors.error : colors.warningText || colors.warning;
            return (
              <View key={`${row?.file || 'route'}-${index}`} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.surfaceHover, padding: 10, gap: 4 }} data-testid={`theme-governance-risky-route-${index + 1}`} testID={`theme-governance-risky-route-${index + 1}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800', flex: 1 }} numberOfLines={1}>{row?.surface || row?.file || 'Unknown route'}</Text>
                  <View style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3, backgroundColor: `${tone}15`, borderWidth: 1, borderColor: `${tone}30` }}>
                    <Text style={{ color: tone, fontSize: 9, fontWeight: '800' }}>{String(row?.status || 'watch').toUpperCase()}</Text>
                  </View>
                </View>
                <Text style={{ color: colors.textMuted, fontSize: 10 }} numberOfLines={1}>{row?.file}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10 }}>Issues {row?.issues_total || 0} • H:{row?.issues_by_severity?.high || 0} M:{row?.issues_by_severity?.medium || 0} L:{row?.issues_by_severity?.low || 0}</Text>
              </View>
            );
          })}
        </View>

        <View style={{ flex: 0.9, minWidth: 320, gap: 12 }}>
          <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="theme-governance-open-tickets-card" testID="theme-governance-open-tickets-card">
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="theme-governance-open-tickets-title" testID="theme-governance-open-tickets-title">{tx('admin.themeGovernanceDashboard.auto.text.006', 'Open Drift Tickets')}</Text>
            {openTickets.length === 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="theme-governance-open-tickets-empty" testID="theme-governance-open-tickets-empty">{tx('admin.themeGovernanceDashboard.auto.text.007', 'No open tickets right now.')}</Text>
            ) : openTickets.slice(0, 6).map((ticket: any, index: number) => (
              <View key={ticket?.ticket_id || index} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 9 }} data-testid={`theme-governance-ticket-${index + 1}`} testID={`theme-governance-ticket-${index + 1}`}>
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>{ticket?.ticket_id}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10 }} numberOfLines={1}>{ticket?.file}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>Severity {ticket?.severity || 'unknown'} • Hits {ticket?.occurrence_count || 0}</Text>
              </View>
            ))}
          </View>

          <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="theme-governance-regression-card" testID="theme-governance-regression-card">
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="theme-governance-regression-title" testID="theme-governance-regression-title">{tx('admin.themeGovernanceDashboard.auto.text.008', 'Regression Timeline')}</Text>
            {timeline.length === 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="theme-governance-regression-empty" testID="theme-governance-regression-empty">{tx('admin.themeGovernanceDashboard.auto.text.009', 'No timeline entries yet.')}</Text>
            ) : timeline.slice(-6).map((row: any, index: number) => (
              <View key={row?.run_id || index} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`theme-governance-regression-row-${index + 1}`} testID={`theme-governance-regression-row-${index + 1}`}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: row?.status === 'PASS' ? colors.successText || colors.success : colors.error }} />
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>{row?.checked_at ? new Date(row.checked_at).toLocaleString() : 'Unknown'} • Score {row?.theme_guardrail_score || 0}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>Issues {row?.issues_total || 0}</Text>
                </View>
              </View>
            ))}
          </View>
        </View>
      </View>
    </ScrollView>
  );
}
