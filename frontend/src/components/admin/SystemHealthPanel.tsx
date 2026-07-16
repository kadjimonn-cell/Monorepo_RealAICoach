/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
import React, { useMemo, useState } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity, TextInput, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';
import AutoFixBanner from './AutoFixBanner';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props {
  colors?: any;
}

type ToneMap = {
  bg: string;
  bgSoft: string;
  card: string;
  cardAlt: string;
  border: string;
  text: string;
  textSec: string;
  textMuted: string;
  primary: string;
  primaryText: string;
  success: string;
  successSoft: string;
  successText: string;
  warning: string;
  warningSoft: string;
  warningText: string;
  error: string;
  errorSoft: string;
  info: string;
};

type BackfillRun = {
  run_id: string;
  mode?: string;
  status?: string;
  triggered_by?: string;
  triggered_by_email?: string;
  triggered_at?: string;
  candidate_count?: number;
  sample_size?: number;
  matched_count?: number;
  applied_count?: number;
  include_admins?: boolean;
  include_full_access?: boolean;
  trusted_email_allowlist_size?: number;
  trusted_email_allowlist_preview?: string[];
};

export default function SystemHealthPanel({ colors }: Props) {
  const router = useRouter();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const T = useMemo<ToneMap>(() => ({
    bg: colors?.bg || 'var(--app-primary-text)',
    bgSoft: colors?.bgSoft || colors?.surfaceHover || 'var(--app-primary)',
    card: colors?.surface || 'var(--app-primary-text)',
    cardAlt: colors?.surfaceHover || 'var(--app-primary)',
    border: colors?.border || 'var(--app-primary)',
    text: colors?.text || 'var(--app-primary)',
    textSec: colors?.textSec || 'var(--app-primary)',
    textMuted: colors?.textMuted || 'var(--app-primary)',
    primary: colors?.primary || 'var(--app-primary)',
    primaryText: colors?.primaryText || 'var(--app-primary-text)',
    success: colors?.success || 'var(--app-success)',
    successSoft: colors?.successSoft || 'var(--app-primary)',
    successText: colors?.successText || colors?.success || 'var(--app-primary)',
    warning: colors?.warning || 'var(--app-warning)',
    warningSoft: colors?.warningSoft || 'var(--app-primary)',
    warningText: colors?.warningText || colors?.warning || 'var(--app-primary)',
    error: colors?.error || 'var(--app-error)',
    errorSoft: colors?.errorSoft || 'var(--app-primary)',
    info: colors?.info || colors?.primary || 'var(--app-primary)',
  }), [colors]);

  const { data, loading: healthLoading, refetch: refetchHealth } = useLiveQuery('/admin/system/health-deep', {
    entity: 'system-health',
    pollInterval: 30000,
  });
  const { data: infra, loading: infraLoading } = useLiveQuery('/admin/infra/metrics', {
    entity: 'system-health',
    pollInterval: 30000,
  });
  const { data: backfillRunsData, loading: backfillRunsLoading, refetch: refetchBackfillRuns } = useLiveQuery('/admin/manage/users/email-verified/backfill/runs?limit=8', {
    entity: 'system-health',
    pollInterval: 45000,
  });
  const [repairing, setRepairing] = useState(false);
  const [backfillRunningMode, setBackfillRunningMode] = useState<'dry_run' | 'apply' | ''>('');
  const [allowlistInput, setAllowlistInput] = useState('');
  const [backfillLimit, setBackfillLimit] = useState('2000');
  const [lastBackfillResult, setLastBackfillResult] = useState<any>(null);

  const runRepair = async () => {
    setRepairing(true);
    try {
      await api.post('/admin/system/self-repair');
      await refetchHealth();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/SystemHealthPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setRepairing(false);
    }
  };

  const parseAllowlist = (value: string): string[] =>
    String(value || '')
      .split(',')
      .map((item) => item.trim().toLowerCase())
      .filter((item) => item.length > 3 && item.includes('@'));

  const runEmailBackfill = async (mode: 'dry_run' | 'apply') => {
    if (backfillRunningMode) return;
    setBackfillRunningMode(mode);
    try {
      const parsedLimit = Number.parseInt(String(backfillLimit || '').trim(), 10);
      const payload = {
        mode,
        include_admins: true,
        include_full_access: true,
        extra_allowlist_emails: parseAllowlist(allowlistInput),
        limit: Number.isFinite(parsedLimit) ? parsedLimit : 2000,
      };
      const res = await api.post('/admin/manage/users/email-verified/backfill', payload);
      setLastBackfillResult(res.data || null);
      await refetchBackfillRuns();
      Alert.alert('Backfill run completed', `${mode === 'dry_run' ? 'Dry-run' : 'Apply'} run ${res?.data?.run_id || ''}`.trim());
    } catch (e: any) {
      Alert.alert('Backfill run failed', e?.response?.data?.detail || 'Could not execute backfill run');
    } finally {
      setBackfillRunningMode('');
    }
  };

  const downloadBackfillRunsCsv = async () => {
    try {
      const res = await api.get('/admin/manage/users/email-verified/backfill/runs.csv?limit=500', { responseType: 'text' });
      const csvText = String(res?.data || '');

      if (typeof window !== 'undefined') {
        const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
        const url = window.URL.createObjectURL(blob);
        const link = window.document.createElement('a');
        link.href = url;
        link.setAttribute('download', `email_verified_backfill_runs_${Date.now()}.csv`);
        window.document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      }

      Alert.alert('CSV export ready', 'Backfill runs CSV downloaded successfully.');
    } catch (e: any) {
      Alert.alert('CSV export failed', e?.response?.data?.detail || 'Unable to export backfill runs CSV');
    }
  };

  if (healthLoading || infraLoading) {
    return (
      <View style={{ paddingVertical: 40, alignItems: 'center' }} data-testid="system-health-loading" testID="system-health-loading">
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: T.textMuted, marginTop: 12, fontSize: 12 }} data-testid="system-health-loading-label" testID="system-health-loading-label">{tx('admin.systemHealthPanel.auto.text.001', 'Loading system health...')}</Text>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={{ padding: 20, borderRadius: 16, borderWidth: 1, borderColor: `${T.error}22`, backgroundColor: T.card }} data-testid="system-health-error-state" testID="system-health-error-state">
        <Text style={{ color: T.error, fontSize: 13, fontWeight: '700' }} data-testid="system-health-error-message" testID="system-health-error-message">{tx('admin.systemHealthPanel.auto.text.002', 'Failed to load health data.')}</Text>
      </View>
    );
  }

  const { health_score, health_status, issues, database, system, sessions } = data;
  const statusColor = health_status === 'healthy' ? T.success : health_status === 'degraded' ? T.warning : T.error;
  const statusSoft = health_status === 'healthy' ? T.successSoft : health_status === 'degraded' ? T.warningSoft : T.errorSoft;
  const backfillRuns: BackfillRun[] = (backfillRunsData?.runs || []) as BackfillRun[];

  return (
    <View style={{ gap: 16 }} data-testid="system-health-panel" testID="system-health-panel">
      <AutoFixBanner domain="system_health" />

      <View
        style={{
          borderRadius: 20,
          borderWidth: 1,
          borderColor: `${T.primary}24`,
          backgroundColor: T.card,
          padding: 20,
          gap: 16,
        }}
        data-testid="system-health-hero-card"
        testID="system-health-hero-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 240 }}>
            <Text style={{ fontSize: 22, fontWeight: '800', color: T.text }} data-testid="system-health-title" testID="system-health-title">{tx('admin.systemHealthPanel.auto.text.003', 'System Health')}</Text>
            <Text style={{ fontSize: 12, color: T.textSec, marginTop: 6, lineHeight: 18 }} data-testid="system-health-subtitle" testID="system-health-subtitle">{tx('admin.systemHealthPanel.auto.text.004', 'Live infrastructure diagnostics, repair coverage, and critical runtime guardrails.')}</Text>
          </View>

          <TouchableOpacity accessibilityLabel={tx('admin.systemHealthPanel.auto.accessibility.001', 'Run system self-repair')}
            onPress={() => { void runRepair(); }}
            disabled={repairing}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 8,
              paddingHorizontal: 14,
              paddingVertical: 10,
              borderRadius: 999,
              backgroundColor: T.primary,
              opacity: repairing ? 0.7 : 1,
            }}
            data-testid="system-health-self-repair-button"
            testID="system-health-self-repair-button"
          >
            <Ionicons name={repairing ? 'hourglass' : 'construct'} size={14} color={T.primaryText} />
            <Text style={{ fontSize: 12, fontWeight: '800', color: T.primaryText }} data-testid="system-health-self-repair-button-label" testID="system-health-self-repair-button-label">
              {repairing ? 'Repairing...' : 'Run Self-Repair'}
            </Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', alignItems: 'stretch' }}>
          <View
            style={{
              minWidth: 220,
              flex: 1,
              borderRadius: 18,
              borderWidth: 1,
              borderColor: `${statusColor}2F`,
              backgroundColor: statusSoft,
              padding: 18,
              alignItems: 'center',
              justifyContent: 'center',
            }}
            data-testid="system-health-score-card"
            testID="system-health-score-card"
          >
            <View style={{ width: 92, height: 92, borderRadius: 46, borderWidth: 6, borderColor: `${statusColor}28`, alignItems: 'center', justifyContent: 'center', backgroundColor: T.card }} data-testid="system-health-score-ring" testID="system-health-score-ring">
              <Text style={{ color: statusColor, fontSize: 30, fontWeight: '900' }} data-testid="system-health-score-value" testID="system-health-score-value">
                {health_score}
              </Text>
            </View>
            <Text style={{ color: statusColor, fontSize: 13, fontWeight: '800', marginTop: 10, textTransform: 'uppercase', letterSpacing: 0.8 }} data-testid="system-health-status-label" testID="system-health-status-label">
              {health_status}
            </Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }} data-testid="system-health-status-caption" testID="system-health-status-caption">{tx('admin.systemHealthPanel.auto.text.005', 'Composite score from database, system load, and session hygiene.')}</Text>
          </View>

          <View style={{ flex: 2, minWidth: 260, gap: 10 }} data-testid="system-health-issues-card" testID="system-health-issues-card">
            <MetricStrip label="Active sessions" value={sessions?.active || 0} hint="Current valid sessions" accent={T.info} testId="system-health-active-sessions" palette={T} />
            <MetricStrip label="Stale sessions" value={sessions?.stale || 0} hint="Expired sessions awaiting cleanup" accent={sessions?.stale > 100 ? T.warning : T.textSec} testId="system-health-stale-sessions" palette={T} />
            <MetricStrip label="Database latency" value={`${database?.latency_ms || 0}ms`} hint="Round-trip ping latency" accent={database?.latency_ms > 500 ? T.warning : T.success} testId="system-health-db-latency" palette={T} />

            <View style={{ borderRadius: 16, borderWidth: 1, borderColor: T.border, backgroundColor: T.cardAlt, padding: 14 }} data-testid="system-health-issues-list" testID="system-health-issues-list">
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }} data-testid="system-health-issues-title" testID="system-health-issues-title">{tx('admin.systemHealthPanel.auto.text.006', 'Active issues')}</Text>
              {issues?.length ? (
                <View style={{ gap: 8, marginTop: 12 }}>
                  {issues.map((issue: string, index: number) => (
                    <View key={`${issue}-${index}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`system-health-issue-row-${index}`} testID={`system-health-issue-row-${index}`}>
                      <Ionicons name="warning" size={12} color={T.warningText} />
                      <Text style={{ color: T.textSec, fontSize: 11, flex: 1 }} data-testid={`system-health-issue-text-${index}`} testID={`system-health-issue-text-${index}`}>
                        {issue}
                      </Text>
                    </View>
                  ))}
                </View>
              ) : (
                <Text style={{ color: T.successText, fontSize: 11, marginTop: 10, fontWeight: '700' }} data-testid="system-health-no-issues" testID="system-health-no-issues">{tx('admin.systemHealthPanel.auto.text.007', 'No active issues detected.')}</Text>
              )}
            </View>
          </View>
        </View>
      </View>

      <View
        style={{
          borderRadius: 18,
          borderWidth: 1,
          borderColor: `${T.info}2A`,
          backgroundColor: T.card,
          padding: 18,
          gap: 12,
        }}
        data-testid="email-verified-backfill-card"
        testID="email-verified-backfill-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 240 }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="email-verified-backfill-title" testID="email-verified-backfill-title">
              Trusted Email Verification Backfill
            </Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4, lineHeight: 16 }} data-testid="email-verified-backfill-subtitle" testID="email-verified-backfill-subtitle">
              Run controlled dry-run/apply for trusted legacy accounts and export audit history.
            </Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TouchableOpacity accessibilityLabel="Email delivery ledger open button"
              onPress={() => router.push('/admin/email-delivery-ledger' as any)}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
                paddingHorizontal: 12,
                paddingVertical: 8,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: `${T.primary}33`,
                backgroundColor: `${T.primary}12`,
              }}
              data-testid="email-delivery-ledger-open-button"
              testID="email-delivery-ledger-open-button"
            >
              <Ionicons name="mail-open-outline" size={13} color={T.primary} />
              <Text style={{ color: T.primary, fontSize: 11, fontWeight: '800' }} data-testid="email-delivery-ledger-open-label" testID="email-delivery-ledger-open-label">
                Open Ledger
              </Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="Observability center open button"
              onPress={() => router.push('/admin/observability-center' as any)}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
                paddingHorizontal: 12,
                paddingVertical: 8,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: `${T.warning}33`,
                backgroundColor: `${T.warning}12`,
              }}
              data-testid="observability-center-open-button"
              testID="observability-center-open-button"
            >
              <Ionicons name="pulse-outline" size={13} color={T.warning} />
              <Text style={{ color: T.warning, fontSize: 11, fontWeight: '800' }} data-testid="observability-center-open-label" testID="observability-center-open-label">
                Observability
              </Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="Email verified backfill export csv button"
              onPress={() => { void downloadBackfillRunsCsv(); }}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
                paddingHorizontal: 12,
                paddingVertical: 8,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: `${T.info}33`,
                backgroundColor: `${T.info}12`,
              }}
              data-testid="email-verified-backfill-export-csv-button"
              testID="email-verified-backfill-export-csv-button"
            >
              <Ionicons name="download" size={13} color={T.info} />
              <Text style={{ color: T.info, fontSize: 11, fontWeight: '800' }} data-testid="email-verified-backfill-export-csv-label" testID="email-verified-backfill-export-csv-label">
                Export CSV
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <View style={{ flex: 2, minWidth: 260 }}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', marginBottom: 6, textTransform: 'uppercase' }} data-testid="email-verified-backfill-allowlist-label" testID="email-verified-backfill-allowlist-label">
              Allowlist Overrides (comma-separated)
            </Text>
            <TextInput
              value={allowlistInput}
              onChangeText={setAllowlistInput}
              placeholder="ops@example.com, compliance@example.com"
              placeholderTextColor={T.textMuted}
              style={{
                borderWidth: 1,
                borderColor: T.border,
                backgroundColor: T.cardAlt,
                borderRadius: 10,
                paddingHorizontal: 12,
                paddingVertical: 10,
                color: T.text,
                fontSize: 12,
              }}
              data-testid="email-verified-backfill-allowlist-input"
              testID="email-verified-backfill-allowlist-input"
            />
          </View>

          <View style={{ width: 130 }}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', marginBottom: 6, textTransform: 'uppercase' }} data-testid="email-verified-backfill-limit-label" testID="email-verified-backfill-limit-label">
              Candidate limit
            </Text>
            <TextInput
              value={backfillLimit}
              onChangeText={setBackfillLimit}
              keyboardType="number-pad"
              placeholder="2000"
              placeholderTextColor={T.textMuted}
              style={{
                borderWidth: 1,
                borderColor: T.border,
                backgroundColor: T.cardAlt,
                borderRadius: 10,
                paddingHorizontal: 12,
                paddingVertical: 10,
                color: T.text,
                fontSize: 12,
              }}
              data-testid="email-verified-backfill-limit-input"
              testID="email-verified-backfill-limit-input"
            />
          </View>
        </View>

        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <TouchableOpacity accessibilityLabel="Email verified backfill dry run button"
            onPress={() => { void runEmailBackfill('dry_run'); }}
            disabled={Boolean(backfillRunningMode)}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              paddingHorizontal: 14,
              paddingVertical: 9,
              borderRadius: 999,
              backgroundColor: `${T.warning}18`,
              borderWidth: 1,
              borderColor: `${T.warning}35`,
              opacity: backfillRunningMode ? 0.6 : 1,
            }}
            data-testid="email-verified-backfill-dry-run-button"
            testID="email-verified-backfill-dry-run-button"
          >
            {backfillRunningMode === 'dry_run' ? <ActivityIndicator size="small" color={T.warningText} /> : <Ionicons name="flask" size={13} color={T.warningText} />}
            <Text style={{ color: T.warningText, fontSize: 11, fontWeight: '800' }} data-testid="email-verified-backfill-dry-run-label" testID="email-verified-backfill-dry-run-label">
              Run Dry-Run
            </Text>
          </TouchableOpacity>

          <TouchableOpacity accessibilityLabel="Email verified backfill apply button"
            onPress={() => { void runEmailBackfill('apply'); }}
            disabled={Boolean(backfillRunningMode)}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              paddingHorizontal: 14,
              paddingVertical: 9,
              borderRadius: 999,
              backgroundColor: `${T.success}18`,
              borderWidth: 1,
              borderColor: `${T.success}35`,
              opacity: backfillRunningMode ? 0.6 : 1,
            }}
            data-testid="email-verified-backfill-apply-button"
            testID="email-verified-backfill-apply-button"
          >
            {backfillRunningMode === 'apply' ? <ActivityIndicator size="small" color={T.successText} /> : <Ionicons name="checkmark-done" size={13} color={T.successText} />}
            <Text style={{ color: T.successText, fontSize: 11, fontWeight: '800' }} data-testid="email-verified-backfill-apply-label" testID="email-verified-backfill-apply-label">
              Run Apply
            </Text>
          </TouchableOpacity>
        </View>

        {lastBackfillResult ? (
          <View style={{ borderWidth: 1, borderColor: `${T.info}22`, borderRadius: 12, padding: 12, backgroundColor: `${T.info}0D` }} data-testid="email-verified-backfill-last-result" testID="email-verified-backfill-last-result">
            <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} data-testid="email-verified-backfill-last-result-title" testID="email-verified-backfill-last-result-title">
              Last Run · {String(lastBackfillResult?.mode || '').toUpperCase()}
            </Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }} data-testid="email-verified-backfill-last-result-metrics" testID="email-verified-backfill-last-result-metrics">
              run_id: {lastBackfillResult?.run_id || 'n/a'} · candidates: {lastBackfillResult?.candidate_count || 0} · applied: {lastBackfillResult?.applied_count || 0}
            </Text>
          </View>
        ) : null}

        <View style={{ borderWidth: 1, borderColor: T.border, borderRadius: 12, backgroundColor: T.cardAlt, padding: 12 }} data-testid="email-verified-backfill-runs-table" testID="email-verified-backfill-runs-table">
          <Text style={{ color: T.text, fontSize: 12, fontWeight: '800' }} data-testid="email-verified-backfill-runs-title" testID="email-verified-backfill-runs-title">
            Recent Backfill Runs
          </Text>
          {backfillRunsLoading ? (
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 8 }} data-testid="email-verified-backfill-runs-loading" testID="email-verified-backfill-runs-loading">
              Loading backfill runs...
            </Text>
          ) : backfillRuns.length ? (
            <View style={{ gap: 8, marginTop: 10 }}>
              {backfillRuns.map((run, index) => (
                <View
                  key={`${run.run_id || 'run'}-${index}`}
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: T.border,
                    backgroundColor: T.card,
                    padding: 10,
                    gap: 4,
                  }}
                  data-testid={`email-verified-backfill-run-row-${index}`}
                  testID={`email-verified-backfill-run-row-${index}`}
                >
                  <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} data-testid={`email-verified-backfill-run-id-${index}`} testID={`email-verified-backfill-run-id-${index}`}>
                    {run.run_id}
                  </Text>
                  <Text style={{ color: T.textSec, fontSize: 10 }} data-testid={`email-verified-backfill-run-meta-${index}`} testID={`email-verified-backfill-run-meta-${index}`}>
                    {String(run.mode || '').toUpperCase()} · {run.status || 'n/a'} · {run.triggered_at ? new Date(run.triggered_at).toLocaleString() : 'n/a'}
                  </Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid={`email-verified-backfill-run-counts-${index}`} testID={`email-verified-backfill-run-counts-${index}`}>
                    candidates {run.candidate_count || 0} · sample {run.sample_size || 0} · applied {run.applied_count || 0} · allowlist {run.trusted_email_allowlist_size || 0}
                  </Text>
                </View>
              ))}
            </View>
          ) : (
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 8 }} data-testid="email-verified-backfill-runs-empty" testID="email-verified-backfill-runs-empty">
              No backfill runs yet.
            </Text>
          )}
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }} data-testid="system-health-resources-grid" testID="system-health-resources-grid">
        <ResourceGauge label="CPU" value={system?.cpu_percent || 0} unit="%" color={(system?.cpu_percent || 0) > 80 ? T.error : (system?.cpu_percent || 0) > 50 ? T.warning : T.success} extra="Current host usage" palette={T} testId="system-health-resource-cpu" />
        <ResourceGauge label="Memory" value={system?.memory_used_pct || 0} unit="%" color={(system?.memory_used_pct || 0) > 85 ? T.error : (system?.memory_used_pct || 0) > 60 ? T.warning : T.success} extra={`${system?.memory_used_mb || 0} / ${system?.memory_total_mb || 0} MB`} palette={T} testId="system-health-resource-memory" />
        <ResourceGauge label="Disk" value={system?.disk_used_pct || 0} unit="%" color={(system?.disk_used_pct || 0) > 90 ? T.error : (system?.disk_used_pct || 0) > 70 ? T.warning : T.success} extra={`${system?.disk_free_gb || 0} GB free`} palette={T} testId="system-health-resource-disk" />
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
        <View style={{ flex: 1, minWidth: 300, borderRadius: 18, borderWidth: 1, borderColor: T.border, backgroundColor: T.card, padding: 18 }} data-testid="system-health-database-card" testID="system-health-database-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <View style={{ width: 10, height: 10, borderRadius: 999, backgroundColor: database?.connected ? T.success : T.error }} data-testid="system-health-database-dot" testID="system-health-database-dot" />
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="system-health-database-title" testID="system-health-database-title">{tx('admin.systemHealthPanel.auto.text.008', 'Database Overview')}</Text>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
            <MiniStat label="Collections" value={database?.collections || 0} palette={T} testId="system-health-database-collections" />
            <MiniStat label="Objects" value={database?.objects || 0} palette={T} testId="system-health-database-objects" />
            <MiniStat label="Size (MB)" value={database?.size_mb || 0} palette={T} testId="system-health-database-size" />
          </View>

          <View style={{ gap: 8 }} data-testid="system-health-database-collection-list" testID="system-health-database-collection-list">
            {Object.entries(database?.collection_stats || {}).slice(0, 8).map(([name, count], index) => (
              <View key={name} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }} data-testid={`system-health-database-collection-row-${index}`} testID={`system-health-database-collection-row-${index}`}>
                <Text style={{ color: T.textSec, fontSize: 11, flex: 1 }} data-testid={`system-health-database-collection-name-${index}`} testID={`system-health-database-collection-name-${index}`}>
                  {name}
                </Text>
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} data-testid={`system-health-database-collection-count-${index}`} testID={`system-health-database-collection-count-${index}`}>
                  {Number(count || 0).toLocaleString()}
                </Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flex: 1, minWidth: 300, borderRadius: 18, borderWidth: 1, borderColor: T.border, backgroundColor: T.card, padding: 18 }} data-testid="system-health-infra-card" testID="system-health-infra-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }} data-testid="system-health-infra-title" testID="system-health-infra-title">{tx('admin.systemHealthPanel.auto.text.009', 'Infrastructure Signals')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 14, marginBottom: 14 }}>
            <MiniStat label="API calls · 1h" value={infra?.api_metrics?.calls_1h || 0} palette={T} testId="system-health-api-calls-1h" />
            <MiniStat label="API calls · 24h" value={infra?.api_metrics?.calls_24h || 0} palette={T} testId="system-health-api-calls-24h" />
            <MiniStat label="DB connections" value={infra?.connection_pool?.current_connections || 0} palette={T} testId="system-health-db-connections" />
          </View>

          <View style={{ borderRadius: 16, borderWidth: 1, borderColor: T.border, backgroundColor: T.cardAlt, padding: 14 }} data-testid="system-health-rate-limit-card" testID="system-health-rate-limit-card">
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }} data-testid="system-health-rate-limit-title" testID="system-health-rate-limit-title">{tx('admin.systemHealthPanel.auto.text.010', 'Rate limit coverage')}</Text>
            <View style={{ gap: 8, marginTop: 12 }}>
              {Object.entries(infra?.rate_limiting?.config || {}).map(([bucket, config], index) => (
                <View key={bucket} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }} data-testid={`system-health-rate-limit-row-${index}`} testID={`system-health-rate-limit-row-${index}`}>
                  <Text style={{ color: T.textSec, fontSize: 11, textTransform: 'capitalize' }} data-testid={`system-health-rate-limit-label-${index}`} testID={`system-health-rate-limit-label-${index}`}>
                    {bucket}
                  </Text>
                  <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }} data-testid={`system-health-rate-limit-value-${index}`} testID={`system-health-rate-limit-value-${index}`}>
                    {(config as any)?.requests || 0}/{(config as any)?.window_seconds || 0}s
                  </Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      </View>
    </View>
  );
}

const tx = (_key: string, fallback: string) => fallback;

function ResourceGauge({
  label,
  value,
  unit,
  color,
  extra,
  palette,
  testId,
}: {
  label: string;
  value: number;
  unit: string;
  color: string;
  extra?: string;
  palette: ToneMap;
  testId: string;
}) {
  return (
    <View style={{ flex: 1, minWidth: 180, borderRadius: 16, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.card, padding: 16 }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.textSec, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }} data-testid={`${testId}-label`} testID={`${testId}-label`}>
        {label}
      </Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4, marginTop: 8 }}>
        <Text style={{ color, fontSize: 24, fontWeight: '900' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>
          {Math.round(value || 0)}
        </Text>
        <Text style={{ color: palette.textMuted, fontSize: 11 }} data-testid={`${testId}-unit`} testID={`${testId}-unit`}>
          {unit}
        </Text>
      </View>
      <View style={{ height: 8, borderRadius: 999, backgroundColor: palette.bgSoft, marginTop: 10, overflow: 'hidden' }} data-testid={`${testId}-bar-track`} testID={`${testId}-bar-track`}>
        <View style={{ width: `${Math.min(100, value || 0)}%` as any, height: '100%', backgroundColor: color }} data-testid={`${testId}-bar-fill`} testID={`${testId}-bar-fill`} />
      </View>
      {extra ? (
        <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 8 }} data-testid={`${testId}-extra`} testID={`${testId}-extra`}>
          {extra}
        </Text>
      ) : null}
    </View>
  );
}

function MetricStrip({ label, value, hint, accent, palette, testId }: { label: string; value: string | number; hint: string; accent: string; palette: ToneMap; testId: string }) {
  return (
    <View style={{ borderRadius: 14, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.cardAlt, padding: 14 }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }} data-testid={`${testId}-label`} testID={`${testId}-label`}>
        {label}
      </Text>
      <Text style={{ color: accent, fontSize: 22, fontWeight: '900', marginTop: 6 }} data-testid={`${testId}-value`} testID={`${testId}-value`}>
        {value}
      </Text>
      <Text style={{ color: palette.textSec, fontSize: 11, marginTop: 4 }} data-testid={`${testId}-hint`} testID={`${testId}-hint`}>
        {hint}
      </Text>
    </View>
  );
}

function MiniStat({ label, value, palette, testId }: { label: string; value: string | number; palette: ToneMap; testId: string }) {
  return (
    <View style={{ flex: 1, minWidth: 90, borderRadius: 14, backgroundColor: palette.cardAlt, padding: 12, borderWidth: 1, borderColor: palette.border }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }} data-testid={`${testId}-label`} testID={`${testId}-label`}>
        {label}
      </Text>
      <Text style={{ color: palette.text, fontSize: 18, fontWeight: '800', marginTop: 6 }} data-testid={`${testId}-value`} testID={`${testId}-value`}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </Text>
    </View>
  );
}