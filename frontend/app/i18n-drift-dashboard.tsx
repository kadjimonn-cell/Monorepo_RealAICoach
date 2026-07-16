import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import AppShell from '../src/components/AppShell';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { useAuth } from '../src/context/AuthContext';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

interface DriftPayload {
  nightly?: { generated_at?: string; newly_missing_count?: number; resolved_from_baseline_count?: number; status?: string };
  baseline?: { remaining_count?: number };
  burndown?: {
    selected_count?: number;
    unresolved_top_keys?: Array<{ key?: string; usage?: number; value?: string }>;
  };
}

export default function I18nDriftDashboardPage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const { isAuthenticated, loading: authLoading } = useAuth();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [loading, setLoading] = useState(true);
  const [drift, setDrift] = useState<DriftPayload | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const { data } = await api.get('/public/i18n/nightly-drift-summary');
        if (active) setDrift(data || null);
      } catch {
        if (active) setDrift(null);
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, []);

  return (
    <AdminRouteGate returnTo="/i18n-drift-dashboard">
      <AppShell>
        <ScrollView contentContainerStyle={s.wrap}>
          <Text style={[s.title, { color: colors.text }]} data-testid="i18n-drift-dashboard-title" testID="i18n-drift-dashboard-title">
            {tx('i18nDriftDashboard.title', 'i18n Drift Dashboard')}
          </Text>
          <Text style={[s.subtitle, { color: colors.textMuted }]} data-testid="i18n-drift-dashboard-subtitle" testID="i18n-drift-dashboard-subtitle">
            {tx('i18nDriftDashboard.subtitle', 'Nightly trend for Product and QA: missing key drift and baseline burn-down.')}
          </Text>

          {loading ? (
            <View style={s.center} data-testid="i18n-drift-dashboard-loading" testID="i18n-drift-dashboard-loading"><ActivityIndicator /></View>
          ) : (
            <>
              <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="i18n-drift-dashboard-card" testID="i18n-drift-dashboard-card">
                <Metric label={tx('adminSystem.i18nDrift.newlyMissing', 'New Missing')} value={Number(drift?.nightly?.newly_missing_count || 0)} testId="i18n-drift-dashboard-new-missing" color={colors.error} />
                <Metric label={tx('adminSystem.i18nDrift.resolved', 'Resolved')} value={Number(drift?.nightly?.resolved_from_baseline_count || 0)} testId="i18n-drift-dashboard-resolved" color={colors.successText} />
                <Metric label={tx('adminSystem.i18nDrift.baselineRemaining', 'Baseline Remaining')} value={Number(drift?.baseline?.remaining_count || 0)} testId="i18n-drift-dashboard-baseline-remaining" color={colors.primary} />
                <Metric label={tx('adminSystem.i18nDrift.weeklyBatch', 'Weekly Batch')} value={Number(drift?.burndown?.selected_count || 0)} testId="i18n-drift-dashboard-weekly-batch" color={colors.warningText} />
                <Text style={{ color: colors.textMuted, marginTop: 8 }} data-testid="i18n-drift-dashboard-last-run" testID="i18n-drift-dashboard-last-run">
                  {tx('adminSystem.i18nDrift.lastRun', 'Last nightly run:')} {drift?.nightly?.generated_at ? new Date(drift.nightly.generated_at).toLocaleString() : '—'}
                </Text>
              </View>

              <View style={[s.card, { backgroundColor: colors.card, borderColor: colors.border }]} data-testid="i18n-unresolved-frequency-table" testID="i18n-unresolved-frequency-table">
                <Text style={[s.tableTitle, { color: colors.text }]} data-testid="i18n-unresolved-frequency-title" testID="i18n-unresolved-frequency-title">
                  {tx('i18nDriftDashboard.unresolvedTitle', 'Top Unresolved Keys by Frequency')}
                </Text>
                <Text style={[s.tableSubtitle, { color: colors.textMuted }]} data-testid="i18n-unresolved-frequency-subtitle" testID="i18n-unresolved-frequency-subtitle">
                  {tx('i18nDriftDashboard.unresolvedSubtitle', 'Prioritize these keys in the next 100-key burn-down batch.')}
                </Text>

                <View style={[s.tableHeader, { borderColor: colors.border }]}> 
                  <Text style={[s.headerCellKey, { color: colors.textMuted }]}>{tx('i18nDriftDashboard.columns.key', 'Key')}</Text>
                  <Text style={[s.headerCellUsage, { color: colors.textMuted }]}>{tx('i18nDriftDashboard.columns.usage', 'Usage')}</Text>
                </View>

                {(drift?.burndown?.unresolved_top_keys || []).slice(0, 15).map((row, idx) => (
                  <View
                    key={`${row?.key || 'unknown'}-${idx}`}
                    style={[s.tableRow, { borderColor: colors.border }]}
                    data-testid={`i18n-unresolved-row-${idx}`}
                    testID={`i18n-unresolved-row-${idx}`}
                  >
                    <Text style={[s.rowKey, { color: colors.text }]} numberOfLines={2}>{row?.key || '—'}</Text>
                    <Text style={[s.rowUsage, { color: colors.warningText || colors.primary }]}>{Number(row?.usage || 0).toLocaleString()}</Text>
                  </View>
                ))}

                {(drift?.burndown?.unresolved_top_keys || []).length === 0 ? (
                  <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 10 }} data-testid="i18n-unresolved-empty" testID="i18n-unresolved-empty">
                    {tx('i18nDriftDashboard.unresolvedEmpty', 'No unresolved keys available in the current report.')}
                  </Text>
                ) : null}
              </View>
            </>
          )}
        </ScrollView>
      </AppShell>
    </AdminRouteGate>
  );
}

function Metric({ label, value, color, testId }: { label: string; value: number; color: string; testId: string }) {
  const { colors } = useTheme();
  return (
    <View style={s.metric} data-testid={testId} testID={testId}>
      <Text style={[s.metricValue, { color }]}>{value.toLocaleString()}</Text>
      <Text style={[s.metricLabel, { color: colors.textMuted }]}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { padding: 20, paddingBottom: 80, gap: 10 },
  title: { fontSize: 26, fontWeight: '800' },
  subtitle: { fontSize: 13, marginBottom: 6 },
  card: { borderWidth: 1, borderRadius: 14, padding: 14, gap: 8 },
  tableTitle: { fontSize: 16, fontWeight: '800' },
  tableSubtitle: { fontSize: 12, marginBottom: 6 },
  tableHeader: { flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, paddingBottom: 6 },
  headerCellKey: { flex: 1, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  headerCellUsage: { width: 72, textAlign: 'right', fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  tableRow: { flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, paddingVertical: 8, gap: 8 },
  rowKey: { flex: 1, fontSize: 12, fontWeight: '600' },
  rowUsage: { width: 72, textAlign: 'right', fontSize: 12, fontWeight: '800' },
  metric: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: 'rgba(148,163,184,0.2)' },
  metricValue: { fontSize: 22, fontWeight: '800' },
  metricLabel: { fontSize: 12 },
  center: { flex: 1, minHeight: 260, justifyContent: 'center', alignItems: 'center' },
});
