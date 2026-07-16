import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

type RollupRow = {
  provider: string;
  incidents: number;
  critical: number;
  high: number;
  medium: number;
  last_incident_at?: string;
};

type TimelineRow = {
  source: string;
  provider: string;
  status: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  incident_id: string;
  amount?: number | null;
  currency?: string | null;
  created_at?: string;
  meta?: Record<string, any>;
};

const HOURS_OPTIONS = [24, 72, 168];

export default function ProviderIncidentTimelinePanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  t('i18n.route.admin.provider.incidents.probe');
  const [hours, setHours] = useState(72);
  const [providerFilter, setProviderFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [runningCanaryId, setRunningCanaryId] = useState('');
  const [drilldown, setDrilldown] = useState<any>(null);
  const [canary, setCanary] = useState<any>(null);
  const [error, setError] = useState('');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    try {
      const [drillRes, canaryRes] = await Promise.all([
        api.get(`/admin/payment-analytics/provider-incidents/drilldown?hours=${hours}&provider=${encodeURIComponent(providerFilter)}&limit=220`, { silentLoading: true }),
        api.get('/admin/payment-analytics/provider-incidents/canary-status', { silentLoading: true }),
      ]);
      setDrilldown(drillRes?.data || null);
      setCanary(canaryRes?.data || null);
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || 'Unable to load provider incidents right now.'));
    } finally {
      setLoading(false);
    }
  }, [hours, providerFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/provider-incidents/hybrid-refresh',
    onTick: () => load(true),
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const runCanaryNow = useCallback(async (canaryId: string) => {
    if (runningCanaryId) return;
    setRunningCanaryId(canaryId);
    setError('');
    try {
      await api.post('/admin/payment-analytics/provider-incidents/canary-run-now', { canary_id: canaryId });
      await load(true);
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || 'Failed to run canary now.'));
    } finally {
      setRunningCanaryId('');
    }
  }, [load, runningCanaryId]);

  const rollup: RollupRow[] = Array.isArray(drilldown?.provider_rollup) ? drilldown.provider_rollup : [];
  const timeline: TimelineRow[] = Array.isArray(drilldown?.incident_timeline) ? drilldown.incident_timeline : [];
  const queueRows = Array.isArray(drilldown?.webhook_retry_queue) ? drilldown.webhook_retry_queue : [];
  const canaryJobs = Array.isArray(canary?.jobs) ? canary.jobs : [];

  const baseProviders = ['all'];
  const fromRollupProviders = rollup.map((row) => String(row.provider || '').trim().toLowerCase()).filter(Boolean);
  const providerChoices = Array.from(new Set([...baseProviders, ...fromRollupProviders])).slice(0, 12);

  const severityColor = useCallback((severity: string) => {
    const tone = String(severity || '').toLowerCase();
    if (tone === 'critical') return colors.error;
    if (tone === 'high') return colors.warning;
    if (tone === 'medium') return colors.info;
    return colors.textMuted;
  }, [colors]);

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }} data-testid="provider-incidents-panel" testID="provider-incidents-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }} data-testid="provider-incidents-title" testID="provider-incidents-title">Provider Drilldown & Incident Timeline</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="provider-incidents-subtitle" testID="provider-incidents-subtitle">
            Live checkout failures and webhook incident timeline by provider.
          </Text>
        </View>
        <TouchableOpacity
          onPress={() => void load()}
          style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }}
          data-testid="provider-incidents-refresh-button"
          testID="provider-incidents-refresh-button"
        >
          <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Refresh</Text>
        </TouchableOpacity>
      </View>

      {error ? (
        <Text style={{ color: colors.error, fontSize: 12 }} data-testid="provider-incidents-error" testID="provider-incidents-error">{error}</Text>
      ) : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="provider-incidents-hours-filter" testID="provider-incidents-hours-filter">
        {HOURS_OPTIONS.map((option) => {
          const active = hours === option;
          return (
            <TouchableOpacity accessibilityLabel="Set hours in provider incident timeline panel"
              key={option}
              onPress={() => setHours(option)}
              style={{
                paddingHorizontal: 10,
                paddingVertical: 7,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: active ? colors.primary : colors.border,
                backgroundColor: active ? colors.primary : colors.bgSoft,
              }}
              data-testid={`provider-incidents-hours-${option}`}
              testID={`provider-incidents-hours-${option}`}
            >
              <Text style={{ color: active ? (colors.primaryText || colors.text) : colors.text, fontSize: 11, fontWeight: '700' }}>
                Last {option}h
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="provider-incidents-provider-filter" testID="provider-incidents-provider-filter">
        {providerChoices.map((name) => {
          const active = providerFilter === name;
          return (
            <TouchableOpacity accessibilityLabel="Set provider filter in provider incident timeline panel"
              key={name}
              onPress={() => setProviderFilter(name)}
              style={{
                paddingHorizontal: 10,
                paddingVertical: 7,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: active ? colors.primary : colors.border,
                backgroundColor: active ? colors.primary : colors.bgSoft,
              }}
              data-testid={`provider-incidents-provider-${name}`}
              testID={`provider-incidents-provider-${name}`}
            >
              <Text style={{ color: active ? (colors.primaryText || colors.text) : colors.text, fontSize: 11, fontWeight: '700' }}>
                {name === 'all' ? 'All providers' : name}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {loading ? (
        <View style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 28 }} data-testid="provider-incidents-loading" testID="provider-incidents-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <MetricCard label="Total Incidents" value={String(drilldown?.summary?.total_incidents || 0)} colors={colors} testId="provider-incidents-total" />
            <MetricCard label="Critical" value={String(drilldown?.summary?.critical_incidents || 0)} colors={colors} tone="critical" testId="provider-incidents-critical" />
            <MetricCard label="High" value={String(drilldown?.summary?.high_incidents || 0)} colors={colors} tone="warning" testId="provider-incidents-high" />
            <MetricCard label="Impacted Providers" value={String(drilldown?.summary?.providers_impacted || 0)} colors={colors} testId="provider-incidents-providers" />
          </View>

          <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="provider-incidents-rollup-card" testID="provider-incidents-rollup-card">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="provider-incidents-rollup-title" testID="provider-incidents-rollup-title">Provider Failure Rollup</Text>
            <View style={{ marginTop: 10, gap: 8 }}>
              {rollup.length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="provider-incidents-rollup-empty" testID="provider-incidents-rollup-empty">No provider incidents in this window.</Text>
              ) : rollup.map((row, idx) => (
                <View key={`${row.provider}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`provider-incidents-rollup-row-${idx}`} testID={`provider-incidents-rollup-row-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{row.provider}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{row.incidents} incidents</Text>
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 5 }}>
                    Critical {row.critical} • High {row.high} • Medium {row.medium}
                  </Text>
                </View>
              ))}
            </View>
          </View>

          <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="provider-incidents-timeline-card" testID="provider-incidents-timeline-card">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="provider-incidents-timeline-title" testID="provider-incidents-timeline-title">Incident Timeline</Text>
            <View style={{ marginTop: 10, gap: 8 }}>
              {timeline.length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="provider-incidents-timeline-empty" testID="provider-incidents-timeline-empty">No incidents captured in this timeframe.</Text>
              ) : timeline.slice(0, 90).map((row, idx) => (
                <View key={`${row.incident_id}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`provider-incidents-timeline-row-${idx}`} testID={`provider-incidents-timeline-row-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800', flex: 1 }} numberOfLines={1}>{row.provider} • {row.source}</Text>
                    <Text style={{ color: severityColor(row.severity), fontSize: 10, fontWeight: '900' }}>{String(row.severity || '').toUpperCase()}</Text>
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }} numberOfLines={1}>
                    {row.status} • {row.incident_id} • {row.created_at || 'n/a'}
                  </Text>
                  {typeof row.amount === 'number' ? (
                    <Text style={{ color: colors.textSec, fontSize: 10, marginTop: 4 }}>
                      Amount: {row.amount} {row.currency || ''}
                    </Text>
                  ) : null}
                </View>
              ))}
            </View>
          </View>

          <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="provider-incidents-replay-queue-card" testID="provider-incidents-replay-queue-card">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="provider-incidents-replay-queue-title" testID="provider-incidents-replay-queue-title">Webhook Replay Queue by Provider</Text>
            <View style={{ marginTop: 10, gap: 8 }}>
              {queueRows.length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="provider-incidents-replay-queue-empty" testID="provider-incidents-replay-queue-empty">No replay queue records in this scope.</Text>
              ) : queueRows.map((row: any, idx: number) => (
                <View key={`${row.provider}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`provider-incidents-replay-queue-row-${idx}`} testID={`provider-incidents-replay-queue-row-${idx}`}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{row.provider}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }}>
                    Pending {row.pending || 0} • Processing {row.processing || 0} • Exhausted {row.exhausted || 0} • Success {row.success || 0}
                  </Text>
                </View>
              ))}
            </View>
          </View>

          <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="provider-incidents-canaries-card" testID="provider-incidents-canaries-card">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="provider-incidents-canaries-title" testID="provider-incidents-canaries-title">Scheduled Integrity Canaries</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }} data-testid="provider-incidents-canaries-summary" testID="provider-incidents-canaries-summary">
              Healthy {canary?.summary?.healthy || 0} • Warning {canary?.summary?.warning || 0} • Critical {canary?.summary?.critical || 0}
            </Text>
            <View style={{ marginTop: 10, gap: 8 }}>
              {canaryJobs.map((job: any, idx: number) => {
                const canRun = ['critical_journey_monitor', 'platform_e2e_regression_gate', 'growth_integrity_monitor'].includes(String(job?.job_id || ''));
                const running = runningCanaryId === job?.job_id;
                const tone = String(job?.health || '').toLowerCase();
                const chipColor = tone === 'critical' ? colors.error : tone === 'warning' ? colors.warning : colors.successText;
                return (
                  <View key={`${job?.job_id}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid={`provider-incidents-canary-row-${idx}`} testID={`provider-incidents-canary-row-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{job?.label}</Text>
                        <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }}>
                          {job?.status || 'unknown'} • Last run: {job?.last_run || 'n/a'}
                        </Text>
                      </View>
                      <Text style={{ color: chipColor, fontSize: 10, fontWeight: '900' }}>{String(job?.health || 'unknown').toUpperCase()}</Text>
                    </View>
                    {canRun ? (
                      <TouchableOpacity
                        onPress={() => void runCanaryNow(String(job?.job_id || ''))}
                        disabled={Boolean(runningCanaryId)}
                        style={{ marginTop: 8, alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primary, opacity: runningCanaryId && !running ? 0.6 : 1 }}
                        data-testid={`provider-incidents-canary-run-${job?.job_id}`}
                        testID={`provider-incidents-canary-run-${job?.job_id}`}
                      >
                        <Text style={{ color: colors.primaryText || colors.text, fontSize: 10, fontWeight: '800' }}>{running ? 'Running…' : 'Run now'}</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                );
              })}
            </View>
          </View>
        </>
      )}
    </ScrollView>
  );
}

function MetricCard({ label, value, colors, tone = 'normal', testId }: { label: string; value: string; colors: any; tone?: 'normal' | 'critical' | 'warning'; testId: string }) {
  const color = tone === 'critical' ? colors.error : tone === 'warning' ? colors.warning : colors.text;
  return (
    <View style={{ minWidth: 150, flexGrow: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{label}</Text>
      <Text style={{ color, fontSize: 18, fontWeight: '900', marginTop: 6 }}>{value}</Text>
    </View>
  );
}
