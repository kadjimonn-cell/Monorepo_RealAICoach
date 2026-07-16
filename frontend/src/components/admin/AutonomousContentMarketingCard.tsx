import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

type WeeklyRun = {
  run_id?: string | null;
  week_key?: string | null;
  status?: string | null;
  triggered_by?: string | null;
  topic?: string | null;
  quality_score?: number | null;
  blog_slug?: string | null;
  newsletter_sent?: number;
  newsletter_failed?: number;
  newsletter_skipped_existing?: number;
  created_at?: string | null;
};

type WeeklyContentStatus = WeeklyRun & {
  summary?: {
    total_runs?: number;
    completed_runs?: number;
    completed_with_failures_runs?: number;
    failed_runs?: number;
    skipped_runs?: number;
  };
  latest_successful_run?: WeeklyRun | null;
  recent_runs?: WeeklyRun[];
};

const formatDateLabel = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getStatusTone = (status?: string | null, colors?: any) => {
  const normalized = String(status || 'NOT_RUN').toLowerCase();
  if (normalized === 'completed') return { toneColor: colors?.success || 'var(--app-primary)', bg: colors?.successSoft || 'var(--app-primary-soft)' };
  if (normalized === 'completed_with_failures') return { toneColor: colors?.warning || 'var(--app-warning)', bg: colors?.warningSoft || 'var(--app-warning-soft)' };
  if (normalized === 'skipped') return { toneColor: colors?.primary || 'var(--app-primary)', bg: colors?.primarySoft || 'var(--app-primary-soft)' };
  if (normalized === 'failed') return { toneColor: colors?.error || 'var(--app-error)', bg: colors?.errorSoft || 'var(--app-error-soft)' };
  return { toneColor: colors?.textMuted || 'var(--app-text-muted)', bg: colors?.bgSoft };
};

function MiniMetric({ label, value, accent, testId }: { label: string; value: string | number; accent: string; testId: string }) {
  const AC = useAdminTheme();
  return (
    <View
      style={{ flex: 1, minWidth: 120, backgroundColor: AC.cardSoft, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: AC.border }}
      data-testid={testId}
      testID={testId}
    >
      <Text style={{ fontSize: 10, color: AC.textMuted, fontWeight: '700', textTransform: 'uppercase' }} data-testid={`${testId}-label`} testID={`${testId}-label`}>{label}</Text>
      <Text style={{ fontSize: 20, color: accent, fontWeight: '900', marginTop: 6 }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{value}</Text>
    </View>
  );
}

export const AutonomousContentMarketingCard = ({
  data,
  onRefresh,
}: {
  data: WeeklyContentStatus | null;
  onRefresh: () => void;
}) => {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const latest = data || null;
  const summary = latest?.summary || {};
  const recentRuns = Array.isArray(latest?.recent_runs) ? latest?.recent_runs.slice(0, 5) : [];
  const latestSuccess = latest?.latest_successful_run || null;
  const detailRun = latest?.status === 'skipped' && latestSuccess ? latestSuccess : latest;
  const statusTone = getStatusTone(latest?.status, AC);

  return (
    <View
      style={{ backgroundColor: AC.card, borderRadius: 16, borderWidth: 1, borderColor: AC.border, padding: 16, marginBottom: 16, gap: 14 }}
      data-testid="ae-content-marketing-card"
      testID="ae-content-marketing-card"
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 260 }}>
          <Text style={{ color: AC.text, fontSize: 15, fontWeight: '800' }} data-testid="ae-content-marketing-title" testID="ae-content-marketing-title">{tx('admin.autonomousContentMarketing.title', 'Weekly Content Marketing')}</Text>
          <Text style={{ color: AC.textMuted, fontSize: 11, marginTop: 4 }} data-testid="ae-content-marketing-subtitle" testID="ae-content-marketing-subtitle">
            {tx('admin.autonomousContentMarketing.subtitle', 'Live visibility into autonomous blog generation and newsletter delivery.')}
          </Text>
        </View>

        <TouchableOpacity
          onPress={onRefresh}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, backgroundColor: AC.primarySoft, borderWidth: 1, borderColor: `${AC.primary}55` }}
          data-testid="ae-content-marketing-refresh-button"
          testID="ae-content-marketing-refresh-button"
        >
          <Ionicons name="refresh" size={14} color={AC.primary} />
          <Text style={{ color: AC.primary, fontSize: 11, fontWeight: '800' }}>{tx('admin.autonomousContentMarketing.actions.refresh', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      <View style={{ borderRadius: 14, padding: 14, backgroundColor: statusTone.bg, borderWidth: 1, borderColor: `${statusTone.toneColor}44` }} data-testid="ae-content-marketing-latest-run" testID="ae-content-marketing-latest-run">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 240 }}>
            <Text style={{ color: statusTone.toneColor, fontSize: 11, fontWeight: '900', textTransform: 'uppercase' }} data-testid="ae-content-marketing-status" testID="ae-content-marketing-status">
              {latest?.status || 'NOT_RUN'}
            </Text>
            <Text style={{ color: AC.text, fontSize: 13, fontWeight: '700', marginTop: 6 }} numberOfLines={2} data-testid="ae-content-marketing-slug" testID="ae-content-marketing-slug">
              {detailRun?.blog_slug || 'No weekly blog generated yet'}
            </Text>
            <Text style={{ color: AC.textSec, fontSize: 10, marginTop: 6 }} numberOfLines={2} data-testid="ae-content-marketing-topic" testID="ae-content-marketing-topic">
              Topic: {detailRun?.topic || 'Pending first autonomous run'}
            </Text>
            {latest?.status === 'skipped' ? (
              <Text style={{ color: AC.info, fontSize: 10, marginTop: 6 }} data-testid="ae-content-marketing-skip-note" testID="ae-content-marketing-skip-note">
                {tx('admin.autonomousContentMarketing.skipNote', 'Latest trigger skipped this week, so these details reflect the last successful weekly publish.')}
              </Text>
            ) : null}
          </View>
          <View style={{ minWidth: 150 }}>
            <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.autonomousContentMarketing.lastSuccessfulRun', 'Last successful weekly run')}</Text>
            <Text style={{ color: AC.text, fontSize: 12, fontWeight: '800', marginTop: 6 }} data-testid="ae-content-marketing-last-success" testID="ae-content-marketing-last-success">
              {latestSuccess?.week_key || '—'}
            </Text>
            <Text style={{ color: AC.textSec, fontSize: 10, marginTop: 4 }} data-testid="ae-content-marketing-last-success-date" testID="ae-content-marketing-last-success-date">
              {formatDateLabel(latestSuccess?.created_at)}
            </Text>
          </View>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <MiniMetric label="Sent" value={detailRun?.newsletter_sent ?? 0} accent={AC.success} testId="ae-content-marketing-metric-sent" />
        <MiniMetric label="Failed" value={detailRun?.newsletter_failed ?? 0} accent={AC.error} testId="ae-content-marketing-metric-failed" />
        <MiniMetric label="Skipped" value={detailRun?.newsletter_skipped_existing ?? 0} accent={AC.info} testId="ae-content-marketing-metric-skipped" />
        <MiniMetric label="Quality" value={detailRun?.quality_score ?? 0} accent={AC.primary} testId="ae-content-marketing-metric-quality" />
        <MiniMetric label="Total Runs" value={summary.total_runs ?? 0} accent={AC.text} testId="ae-content-marketing-metric-total-runs" />
      </View>

      <View style={{ gap: 8 }}>
        <Text style={{ color: AC.text, fontSize: 12, fontWeight: '800' }} data-testid="ae-content-marketing-recent-runs-title" testID="ae-content-marketing-recent-runs-title">{tx('admin.autonomousContentMarketing.recentRuns.title', 'Recent Weekly Runs')}</Text>
        {recentRuns.length === 0 ? (
          <View style={{ padding: 14, borderRadius: 12, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.cardSoft }} data-testid="ae-content-marketing-empty" testID="ae-content-marketing-empty">
            <Text style={{ color: AC.textMuted, fontSize: 11 }}>{tx('admin.autonomousContentMarketing.recentRuns.empty', 'No weekly marketing runs yet.')}</Text>
          </View>
        ) : recentRuns.map((run, index) => {
          const rowTone = getStatusTone(run.status, AC);
          return (
            <View
              key={run.run_id || `weekly-run-${index}`}
              style={{ borderRadius: 12, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.cardSoft, padding: 12, gap: 6 }}
              data-testid={`ae-content-marketing-run-row-${index + 1}`}
              testID={`ae-content-marketing-run-row-${index + 1}`}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <Text style={{ color: AC.text, fontSize: 11, fontWeight: '800' }} data-testid={`ae-content-marketing-run-row-${index + 1}-week`} testID={`ae-content-marketing-run-row-${index + 1}-week`}>
                  {run.week_key || 'No week'}
                </Text>
                <View style={{ paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999, backgroundColor: rowTone.bg, borderWidth: 1, borderColor: `${rowTone.toneColor}44` }} data-testid={`ae-content-marketing-run-row-${index + 1}-status-pill`} testID={`ae-content-marketing-run-row-${index + 1}-status-pill`}>
                  <Text style={{ color: rowTone.toneColor, fontSize: 10, fontWeight: '900', textTransform: 'uppercase' }}>{run.status || 'NOT_RUN'}</Text>
                </View>
              </View>
              <Text style={{ color: AC.textSec, fontSize: 10 }} numberOfLines={1} data-testid={`ae-content-marketing-run-row-${index + 1}-slug`} testID={`ae-content-marketing-run-row-${index + 1}-slug`}>
                {run.blog_slug || 'No slug recorded'}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                <Text style={{ color: AC.textMuted, fontSize: 10 }} data-testid={`ae-content-marketing-run-row-${index + 1}-sent`} testID={`ae-content-marketing-run-row-${index + 1}-sent`}>Sent: {run.newsletter_sent ?? 0}</Text>
                <Text style={{ color: AC.textMuted, fontSize: 10 }} data-testid={`ae-content-marketing-run-row-${index + 1}-failed`} testID={`ae-content-marketing-run-row-${index + 1}-failed`}>Failed: {run.newsletter_failed ?? 0}</Text>
                <Text style={{ color: AC.textMuted, fontSize: 10 }} data-testid={`ae-content-marketing-run-row-${index + 1}-time`} testID={`ae-content-marketing-run-row-${index + 1}-time`}>{formatDateLabel(run.created_at)}</Text>
              </View>
            </View>
          );
        })}
      </View>
    </View>
  );
};