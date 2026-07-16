import { useTranslation } from '../../hooks/useTranslation';
import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput } from 'react-native';
import { useTheme } from '../../context/ThemeContext';

type HealthOverview = {
  latest_scan?: any;
  latest_nightly?: any;
  matrix_summary?: { total_surfaces?: number; pass?: number; watch?: number; attention?: number };
  route_pass_matrix?: any[];
  regression_timeline?: any[];
  recent_runs?: any[];
  open_tickets?: any[];
};

const tx = (_key: string, fallback: string) => fallback;

const formatTs = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

function HealthMetric({ label, value, accent, palette, testId }: { label: string; value: string | number; accent: string; palette: any; testId: string }) {
  return (
    <View style={{ flex: 1, minWidth: 130, backgroundColor: palette.cardAlt, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: palette.border }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }} data-testid={`${testId}-label`} testID={`${testId}-label`}>
        {label}
      </Text>
      <Text style={{ color: accent, fontSize: 22, fontWeight: '900', marginTop: 6 }} data-testid={`${testId}-value`} testID={`${testId}-value`}>
        {value}
      </Text>
    </View>
  );
}

export const ThemeHealthCenterPanel = ({ overview }: { overview: HealthOverview | null }) => {
  const { colors } = useTheme();
  const [statusFilter, setStatusFilter] = useState<'all' | 'attention' | 'watch' | 'pass'>('all');
  const [surfaceQuery, setSurfaceQuery] = useState('');

  const palette = useMemo(() => ({
    card: colors.surface,
    cardAlt: colors.surfaceHover,
    border: colors.border,
    text: colors.text,
    textMuted: colors.textMuted,
    textSec: colors.textSec,
    primary: colors.primary,
    primarySoft: colors.primarySoft || `${colors.primary}14`,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    info: colors.info || colors.primary,
  }), [colors]);

  const latestScan = overview?.latest_scan || {};
  const latestNightly = overview?.latest_nightly || {};
  const matrixSummary = overview?.matrix_summary || {};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const routePassMatrix = Array.isArray(overview?.route_pass_matrix) ? overview?.route_pass_matrix : [];
  const regressionTimeline = Array.isArray(overview?.regression_timeline) ? overview?.regression_timeline : [];
  const recentRuns = Array.isArray(overview?.recent_runs) ? overview?.recent_runs.slice(0, 6) : [];
  const openTickets = Array.isArray(overview?.open_tickets) ? overview?.open_tickets : [];
  const ticketSummary = latestNightly?.ticket_summary || {};

  const filteredMatrix = useMemo(
    () => routePassMatrix.filter((row) => {
      const statusOk = statusFilter === 'all' ? true : row?.status === statusFilter;
      const query = surfaceQuery.trim().toLowerCase();
      const text = `${row?.surface || ''} ${row?.file || ''} ${(row?.sample_rules || []).join(' ')}`.toLowerCase();
      return statusOk && (!query || text.includes(query));
    }),
    [routePassMatrix, statusFilter, surfaceQuery],
  );

  return (
    <View style={{ gap: 16 }} data-testid="theme-health-center-panel" testID="theme-health-center-panel">
      <Card palette={palette} testId="theme-health-center-hero" gap={14}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 260 }}>
            <Text style={{ color: palette.text, fontSize: 18, fontWeight: '800' }} data-testid="theme-health-center-title" testID="theme-health-center-title">{tx('admin.themeHealthCenterPanel.auto.text.001', 'Theme Health Center')}</Text>
            <Text style={{ color: palette.textMuted, fontSize: 12, marginTop: 4 }} data-testid="theme-health-center-subtitle" testID="theme-health-center-subtitle">{tx('admin.themeHealthCenterPanel.auto.text.002', 'Instant visual governance across route parity, drift tickets, and regression movement.')}</Text>
          </View>

          <View style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, backgroundColor: palette.primarySoft, borderWidth: 1, borderColor: `${palette.primary}35` }} data-testid="theme-health-center-latest-pill" testID="theme-health-center-latest-pill">
            <Text style={{ color: palette.primary, fontSize: 11, fontWeight: '800' }}>Latest scan: {formatTs(latestScan?.checked_at)}</Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <HealthMetric label="Health Score" value={latestScan?.theme_guardrail_score ?? 0} accent={palette.primary} palette={palette} testId="theme-health-center-score" />
          <HealthMetric label="Attention" value={matrixSummary.attention ?? 0} accent={palette.error} palette={palette} testId="theme-health-center-attention" />
          <HealthMetric label="Watch" value={matrixSummary.watch ?? 0} accent={palette.warning} palette={palette} testId="theme-health-center-watch" />
          <HealthMetric label="Pass" value={matrixSummary.pass ?? 0} accent={palette.success} palette={palette} testId="theme-health-center-pass" />
          <HealthMetric label="Open Tickets" value={ticketSummary.open_tickets ?? 0} accent={palette.info} palette={palette} testId="theme-health-center-open-tickets" />
        </View>
      </Card>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
        <Card palette={palette} testId="theme-health-center-matrix-card" gap={12} style={{ flex: 1.25, minWidth: 340 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <Text style={{ color: palette.text, fontSize: 15, fontWeight: '800' }} data-testid="theme-health-center-matrix-title" testID="theme-health-center-matrix-title">{tx('admin.themeHealthCenterPanel.auto.text.003', 'Route Pass Matrix')}</Text>
            <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
              {(['all', 'attention', 'watch', 'pass'] as const).map((item) => {
                const active = statusFilter === item;
                return (
                  <TouchableOpacity
                    key={item}
                    onPress={() => setStatusFilter(item)}
                    style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: active ? `${palette.primary}55` : palette.border, backgroundColor: active ? palette.primarySoft : palette.cardAlt }}
                    data-testid={`theme-health-center-filter-${item}`}
                    testID={`theme-health-center-filter-${item}`}
                  >
                    <Text style={{ color: active ? palette.primary : palette.textSec, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{item}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <TextInput
            value={surfaceQuery}
            onChangeText={setSurfaceQuery}
            placeholder={tx('admin.themeHealthCenterPanel.auto.placeholder.001', 'Filter by route, file, or rule')}
            placeholderTextColor={palette.textMuted}
            style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, color: palette.text, backgroundColor: palette.cardAlt, fontSize: 12 }}
            data-testid="theme-health-center-search-input"
            testID="theme-health-center-search-input"
          />

          <View style={{ gap: 8 }} data-testid="theme-health-center-matrix-list" testID="theme-health-center-matrix-list">
            {filteredMatrix.slice(0, 10).map((row, index) => {
              const tone = row?.status === 'attention' ? palette.error : row?.status === 'watch' ? palette.warning : palette.success;
              return (
                <View key={`${row?.file || 'row'}-${index}`} style={{ backgroundColor: palette.cardAlt, borderRadius: 12, borderWidth: 1, borderColor: palette.border, padding: 12, gap: 5 }} data-testid={`theme-health-center-matrix-row-${index + 1}`} testID={`theme-health-center-matrix-row-${index + 1}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <Text style={{ color: palette.text, fontSize: 11, fontWeight: '800', flex: 1 }} numberOfLines={1} data-testid={`theme-health-center-matrix-row-${index + 1}-surface`} testID={`theme-health-center-matrix-row-${index + 1}-surface`}>
                      {row?.surface || row?.file}
                    </Text>
                    <View style={{ paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999, backgroundColor: `${tone}14`, borderWidth: 1, borderColor: `${tone}35` }} data-testid={`theme-health-center-matrix-row-${index + 1}-status`} testID={`theme-health-center-matrix-row-${index + 1}-status`}>
                      <Text style={{ color: tone, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{row?.status || 'pass'}</Text>
                    </View>
                  </View>
                  <Text style={{ color: palette.textMuted, fontSize: 10 }} numberOfLines={1}>{row?.file}</Text>
                  <Text style={{ color: palette.textSec, fontSize: 10 }} data-testid={`theme-health-center-matrix-row-${index + 1}-issues`} testID={`theme-health-center-matrix-row-${index + 1}-issues`}>
                    Issues: {row?.issues_total || 0} • H:{row?.issues_by_severity?.high || 0} M:{row?.issues_by_severity?.medium || 0} L:{row?.issues_by_severity?.low || 0}
                  </Text>
                </View>
              );
            })}

            {filteredMatrix.length === 0 ? (
              <View style={{ backgroundColor: palette.cardAlt, borderRadius: 12, borderWidth: 1, borderColor: palette.border, padding: 14 }} data-testid="theme-health-center-matrix-empty" testID="theme-health-center-matrix-empty">
                <Text style={{ color: palette.textMuted, fontSize: 11 }}>{tx('admin.themeHealthCenterPanel.auto.text.004', 'No surfaces match the current filter.')}</Text>
              </View>
            ) : null}
          </View>
        </Card>

        <View style={{ flex: 0.9, minWidth: 320, gap: 16 }}>
          <Card palette={palette} testId="theme-health-center-tickets-card" gap={10}>
            <Text style={{ color: palette.text, fontSize: 15, fontWeight: '800' }} data-testid="theme-health-center-tickets-title" testID="theme-health-center-tickets-title">{tx('admin.themeHealthCenterPanel.auto.text.005', 'Open Drift Tickets')}</Text>
            {openTickets.length === 0 ? (
              <Text style={{ color: palette.textMuted, fontSize: 11 }} data-testid="theme-health-center-tickets-empty" testID="theme-health-center-tickets-empty">{tx('admin.themeHealthCenterPanel.auto.text.006', 'No open drift tickets right now.')}</Text>
            ) : openTickets.slice(0, 5).map((ticket, index) => (
              <View key={ticket?.ticket_id || index} style={{ backgroundColor: palette.cardAlt, borderRadius: 12, borderWidth: 1, borderColor: palette.border, padding: 12, gap: 4 }} data-testid={`theme-health-center-ticket-${index + 1}`} testID={`theme-health-center-ticket-${index + 1}`}>
                <Text style={{ color: palette.text, fontSize: 11, fontWeight: '800' }}>{ticket?.ticket_id}</Text>
                <Text style={{ color: palette.textSec, fontSize: 10 }} numberOfLines={1}>{ticket?.file}</Text>
                <Text style={{ color: palette.textMuted, fontSize: 10 }}>Severity: {ticket?.severity || 'unknown'} • Hits: {ticket?.occurrence_count || 0}</Text>
              </View>
            ))}
          </Card>

          <Card palette={palette} testId="theme-health-center-regression-card" gap={10}>
            <Text style={{ color: palette.text, fontSize: 15, fontWeight: '800' }} data-testid="theme-health-center-regression-title" testID="theme-health-center-regression-title">{tx('admin.themeHealthCenterPanel.auto.text.007', 'Regression Timeline')}</Text>
            {regressionTimeline.length === 0 ? (
              <Text style={{ color: palette.textMuted, fontSize: 11 }}>{tx('admin.themeHealthCenterPanel.auto.text.008', 'No timeline data yet.')}</Text>
            ) : regressionTimeline.slice(-6).map((row, index) => (
              <View key={row?.run_id || index} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid={`theme-health-center-timeline-${index + 1}`} testID={`theme-health-center-timeline-${index + 1}`}>
                <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: row?.status === 'PASS' ? palette.success : palette.error }} />
                <View style={{ flex: 1 }}>
                  <Text style={{ color: palette.text, fontSize: 11, fontWeight: '700' }}>{formatTs(row?.checked_at)} • Score {row?.theme_guardrail_score ?? 0}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 10 }}>Issues: {row?.issues_total ?? 0} • H:{row?.high ?? 0} M:{row?.medium ?? 0} L:{row?.low ?? 0}</Text>
                </View>
              </View>
            ))}
          </Card>
        </View>
      </View>

      <Card palette={palette} testId="theme-health-center-runs-card" gap={12}>
        <Text style={{ color: palette.text, fontSize: 15, fontWeight: '800' }} data-testid="theme-health-center-runs-title" testID="theme-health-center-runs-title">{tx('admin.themeHealthCenterPanel.auto.text.009', 'Recent Theme Guardrail Runs')}</Text>
        {recentRuns.length === 0 ? (
          <Text style={{ color: palette.textMuted, fontSize: 11 }} data-testid="theme-health-center-runs-empty" testID="theme-health-center-runs-empty">{tx('admin.themeHealthCenterPanel.auto.text.010', 'No recent runs yet.')}</Text>
        ) : recentRuns.map((run, index) => (
          <View key={run?.run_id || index} style={{ backgroundColor: palette.cardAlt, borderRadius: 12, borderWidth: 1, borderColor: palette.border, padding: 12, gap: 4 }} data-testid={`theme-health-center-run-${index + 1}`} testID={`theme-health-center-run-${index + 1}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <Text style={{ color: palette.text, fontSize: 11, fontWeight: '800' }}>{run?.run_id}</Text>
              <Text style={{ color: run?.status === 'PASS' ? palette.success : palette.error, fontSize: 10, fontWeight: '800' }}>{run?.status || 'NOT_RUN'}</Text>
            </View>
            <Text style={{ color: palette.textMuted, fontSize: 10 }}>Checked: {formatTs(run?.checked_at)} • Score: {run?.theme_guardrail_score ?? 0}</Text>
            <Text style={{ color: palette.textSec, fontSize: 10 }}>Issues: {run?.issues_total ?? 0} • Files scanned: {run?.files_scanned ?? 0}</Text>
          </View>
        ))}
      </Card>
    </View>
  );
};

function Card({ palette, children, testId, style, gap = 0 }: { palette: any; children: React.ReactNode; testId: string; style?: any; gap?: number }) {
  return (
    <View style={[{ backgroundColor: palette.card, borderRadius: 18, borderWidth: 1, borderColor: palette.border, padding: 18, gap }, style]} data-testid={testId} testID={testId}>
      {children}
    </View>
  );
}
/* i18n-probe t('i18n.auto.probe') */
