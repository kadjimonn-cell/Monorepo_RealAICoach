import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { useTheme } from '../../context/ThemeContext';

const fmt = (value: any) => String(value ?? '--');

const statusColor = (status: string, colors: any) => {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'healthy') return colors.success;
  if (normalized === 'warning') return colors.warning;
  if (normalized === 'critical' || normalized === 'error') return colors.error;
  return colors.textMuted;
};

export default function LearningHubAutopilotExecutiveWorkspace() {
  const { colors } = useTheme();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [payload, setPayload] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      setError('');
      const settled = await Promise.allSettled([
        api.get('/ai-learn/admin/executive-insights'),
        api.get('/ai-learn/admin/integrity/status'),
        api.get('/ai-learn/admin/weekly-course-publish/status'),
        api.get('/ai-learn/admin/assurance/status'),
        api.get('/ai-learn/admin/synthetic-canary/status'),
        api.get('/ai-learn/admin/notifications/email-dispatch/status'),
        api.get('/ai-learn/admin/content-relevance/status'),
      ]);

      const pick = (index: number) => {
        const row = settled[index];
        if (!row || row.status !== 'fulfilled') return {};
        return row.value?.data || {};
      };

      const has403 = settled.some((row) => {
        if (row.status !== 'rejected') return false;
        return Number((row.reason as any)?.response?.status || 0) === 403;
      });
      if (has403) {
        setError('Some streams are permission-scoped. Autopilot telemetry will continue with available feeds.');
      }

      setPayload({
        insights: pick(0),
        integrity: pick(1),
        weekly: pick(2),
        assurance: pick(3),
        canary: pick(4),
        emailDispatch: pick(5),
        relevance: pick(6),
      });
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Unable to load Learning Hub autopilot telemetry.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useAutoRefresh(load, { intervalMs: 30000 });

  const overview = payload?.insights?.overview || {};
  const integrityRuntime = payload?.integrity?.runtime || {};
  const assuranceRuntime = payload?.assurance?.runtime || {};
  const canaryRuntime = payload?.canary?.runtime || {};
  const videoRuntime = payload?.relevance?.video_validation_runtime || {};
  const queue = payload?.emailDispatch?.queue || {};
  const retentionCohorts = Array.isArray(payload?.insights?.retention_cohorts) ? payload.insights.retention_cohorts : [];
  const retentionCards = retentionCohorts.length > 0 ? retentionCohorts : [
    { window: '7d', retention_rate_pct: 0, returning_users: 0, current_active_users: 0, previous_active_users: 0, growth_vs_previous_pct: 0 },
    { window: '30d', retention_rate_pct: 0, returning_users: 0, current_active_users: 0, previous_active_users: 0, growth_vs_previous_pct: 0 },
  ];
  const hasData = !!payload;

  const metricCards = useMemo(() => ([
    { id: 'learners', label: 'Weekly Active Learners', value: fmt(overview.weekly_active_learners), icon: 'people-outline' },
    { id: 'completion', label: 'Completion Rate', value: `${Number(overview.completion_rate_pct || 0).toFixed(1)}%`, icon: 'checkmark-circle-outline' },
    { id: 'topic-alignment', label: 'Video Topic Alignment', value: `${Number(overview.video_topic_alignment_pct || 0).toFixed(1)}%`, icon: 'videocam-outline' },
    { id: 'broken-links', label: 'Broken Video Links', value: fmt(overview.video_broken_links), icon: 'alert-circle-outline' },
  ]), [overview]);

  return (
    <View style={{ flex: 1, padding: 16 }} data-testid="executive-learning-hub-autopilot-workspace" testID="executive-learning-hub-autopilot-workspace">
      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 16 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '900' }} data-testid="executive-learning-hub-autopilot-title" testID="executive-learning-hub-autopilot-title">
              Learning Hub Autopilot
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 3 }} data-testid="executive-learning-hub-autopilot-subtitle" testID="executive-learning-hub-autopilot-subtitle">
              Fully automated executive telemetry. No manual controls are exposed on this surface.
            </Text>
          </View>
          <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: `${colors.success}55`, backgroundColor: `${colors.success}18` }} data-testid="executive-learning-hub-autopilot-mode-chip" testID="executive-learning-hub-autopilot-mode-chip">
            <Text style={{ color: colors.success, fontSize: 10, fontWeight: '800' }}>AUTO ENFORCED</Text>
          </View>
        </View>

        {loading ? (
          <View style={{ paddingVertical: 22, alignItems: 'center' }} data-testid="executive-learning-hub-autopilot-loading" testID="executive-learning-hub-autopilot-loading">
            <ActivityIndicator color={colors.primary} />
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 10 }}>Loading automation telemetry...</Text>
          </View>
        ) : null}

        {error ? (
          <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: `${hasData ? colors.warning : colors.error}66`, backgroundColor: `${hasData ? colors.warning : colors.error}16`, padding: 10 }} data-testid="executive-learning-hub-autopilot-error" testID="executive-learning-hub-autopilot-error">
            <Text style={{ color: hasData ? colors.warning : colors.error, fontSize: 12, fontWeight: '700' }}>{error}</Text>
          </View>
        ) : null}

        {!loading && hasData ? (
          <>
            <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="executive-learning-hub-autopilot-kpis" testID="executive-learning-hub-autopilot-kpis">
              {metricCards.map((item) => (
                <View key={item.id} style={{ flex: 1, minWidth: 170, borderRadius: 10, borderWidth: 1, borderColor: colors.borderSoft || colors.border, backgroundColor: colors.surfaceHover, padding: 10 }} data-testid={`executive-learning-hub-autopilot-kpi-${item.id}`} testID={`executive-learning-hub-autopilot-kpi-${item.id}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name={item.icon as any} size={14} color={colors.primary} />
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>{item.label}</Text>
                  </View>
                  <Text style={{ color: colors.text, fontSize: 22, fontWeight: '900', marginTop: 8 }} data-testid={`executive-learning-hub-autopilot-kpi-${item.id}-value`} testID={`executive-learning-hub-autopilot-kpi-${item.id}-value`}>
                    {item.value}
                  </Text>
                </View>
              ))}
            </View>

            <View style={{ marginTop: 14, borderRadius: 10, borderWidth: 1, borderColor: colors.borderSoft || colors.border, backgroundColor: colors.surface, padding: 12 }} data-testid="executive-learning-hub-autopilot-retention-cohorts" testID="executive-learning-hub-autopilot-retention-cohorts">
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="executive-learning-hub-autopilot-retention-title" testID="executive-learning-hub-autopilot-retention-title">Retention Cohort Trend Cards (7d / 30d)</Text>
              <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                {retentionCards.map((cohort: any) => (
                  <View key={String(cohort.window || 'cohort')} style={{ flex: 1, minWidth: 180, borderRadius: 10, borderWidth: 1, borderColor: colors.borderSoft || colors.border, backgroundColor: colors.surfaceHover, padding: 10 }} data-testid={`executive-learning-hub-autopilot-retention-card-${cohort.window}`} testID={`executive-learning-hub-autopilot-retention-card-${cohort.window}`}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '900' }} data-testid={`executive-learning-hub-autopilot-retention-window-${cohort.window}`} testID={`executive-learning-hub-autopilot-retention-window-${cohort.window}`}>{String(cohort.window || '--')} Cohort</Text>
                    <Text style={{ color: colors.primary, fontSize: 20, fontWeight: '900', marginTop: 6 }} data-testid={`executive-learning-hub-autopilot-retention-rate-${cohort.window}`} testID={`executive-learning-hub-autopilot-retention-rate-${cohort.window}`}>{Number(cohort.retention_rate_pct || 0).toFixed(1)}%</Text>
                    <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4 }}>Returning users: {fmt(cohort.returning_users)}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 11 }}>Active users: {fmt(cohort.current_active_users)} (prev {fmt(cohort.previous_active_users)})</Text>
                    <Text style={{ color: Number(cohort.growth_vs_previous_pct || 0) >= 0 ? colors.success : colors.warning, fontSize: 11, fontWeight: '700', marginTop: 4 }} data-testid={`executive-learning-hub-autopilot-retention-growth-${cohort.window}`} testID={`executive-learning-hub-autopilot-retention-growth-${cohort.window}`}>
                      Trend vs previous: {Number(cohort.growth_vs_previous_pct || 0).toFixed(1)}%
                    </Text>
                  </View>
                ))}
              </View>
            </View>

            <View style={{ marginTop: 14, borderRadius: 10, borderWidth: 1, borderColor: colors.borderSoft || colors.border, backgroundColor: colors.surface, padding: 12 }} data-testid="executive-learning-hub-autopilot-pipeline-status" testID="executive-learning-hub-autopilot-pipeline-status">
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="executive-learning-hub-autopilot-pipeline-title" testID="executive-learning-hub-autopilot-pipeline-title">Automation Pipeline Status</Text>
              {[
                { id: 'integrity', label: 'Integrity Guard', status: integrityRuntime.last_status, runAt: integrityRuntime.last_run_at },
                { id: 'assurance', label: 'Assurance Cycle', status: assuranceRuntime.status, runAt: assuranceRuntime.run_at },
                { id: 'synthetic-canary', label: 'Synthetic Canary', status: canaryRuntime.status, runAt: canaryRuntime.run_at },
              ].map((row) => (
                <View key={row.id} style={{ marginTop: 9, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }} data-testid={`executive-learning-hub-autopilot-pipeline-row-${row.id}`} testID={`executive-learning-hub-autopilot-pipeline-row-${row.id}`}>
                  <Text style={{ color: colors.textSec, fontSize: 12 }}>{row.label}</Text>
                  <Text style={{ color: statusColor(String(row.status || ''), colors), fontSize: 12, fontWeight: '800' }} data-testid={`executive-learning-hub-autopilot-pipeline-status-${row.id}`} testID={`executive-learning-hub-autopilot-pipeline-status-${row.id}`}>
                    {String(row.status || 'unknown').toUpperCase()}
                  </Text>
                </View>
              ))}
            </View>

            <View style={{ marginTop: 14, borderRadius: 10, borderWidth: 1, borderColor: colors.borderSoft || colors.border, backgroundColor: colors.surface, padding: 12 }} data-testid="executive-learning-hub-autopilot-self-healing" testID="executive-learning-hub-autopilot-self-healing">
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="executive-learning-hub-autopilot-self-healing-title" testID="executive-learning-hub-autopilot-self-healing-title">Self-Healing Content Ledger</Text>
              <View style={{ marginTop: 8, gap: 6 }}>
                <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="executive-learning-hub-autopilot-topic-alignment-value" testID="executive-learning-hub-autopilot-topic-alignment-value">Topic alignment: {Number(videoRuntime.topic_alignment_pct || 0).toFixed(1)}%</Text>
                <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="executive-learning-hub-autopilot-topic-repairs-value" testID="executive-learning-hub-autopilot-topic-repairs-value">Topic repairs (latest cycle): {fmt(videoRuntime.topic_repaired_lessons)}</Text>
                <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="executive-learning-hub-autopilot-broken-links-value" testID="executive-learning-hub-autopilot-broken-links-value">Broken links remaining: {fmt(videoRuntime.broken_links)}</Text>
                <Text style={{ color: colors.textSec, fontSize: 11 }} data-testid="executive-learning-hub-autopilot-email-queue-value" testID="executive-learning-hub-autopilot-email-queue-value">Email queue — Pending {fmt(queue.pending)} · Failed {fmt(queue.failed)}</Text>
              </View>
            </View>
          </>
        ) : null}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
