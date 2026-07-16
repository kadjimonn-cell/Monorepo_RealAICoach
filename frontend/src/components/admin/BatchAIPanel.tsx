import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';
import { getWorkflowPollingPreset } from '../../utils/hybridPolling';

const WORKFLOW_POLLING_PRESET = getWorkflowPollingPreset('batch-job-status');

const CAT_COLORS: Record<string, string> = {
  productivity: 'var(--app-primary)', planning: 'var(--app-primary)', health: 'var(--app-success)', // @theme-ok brand/role/state identifier
  finance: 'var(--app-warning)', learning: 'var(--app-primary)', fitness: 'var(--app-error)', // @theme-ok brand/role/state identifier
  wellness: 'var(--app-primary)', 'real-estate': 'var(--app-primary)', career: 'var(--app-warning)', // @theme-ok brand/role/state identifier
  travel: 'var(--app-primary)', personal: 'var(--app-text)', unknown: 'var(--app-text-muted)', // @theme-ok brand/role/state identifier
};

const TYPE_COLORS: Record<string, string> = {
  article: 'var(--app-primary)', guide: 'var(--app-success)', template: 'var(--app-primary)', // @theme-ok brand/role/state identifier
  workout: 'var(--app-warning)', checklist: 'var(--app-error)', generated: 'var(--app-primary)', unknown: 'var(--app-text-muted)', // @theme-ok brand/role/state identifier
};

interface Props {
  colors: any;
}

export default function BatchAIPanel({ colors: C }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const { data: statsData, loading, refetch: loadStats } = useLiveQuery('/admin/batch-categorize/stats', { entity: 'batch-ai', pollInterval: 30000 });
  const [stats, setStats] = useState<any>(null);
  const [starting, setStarting] = useState(false);
  const [jobPolling, setJobPolling] = useState(false);
  const [activeJobId, setActiveJobId] = useState('');

  // Nightly schedule state
  const [schedule, setSchedule] = useState<any>(null);
  const [scheduleLoading, setScheduleLoading] = useState(true);
  const [savingSchedule, setSavingSchedule] = useState(false);

  useEffect(() => { loadSchedule(); }, []);

  useEffect(() => {
    if (statsData) setStats(statsData);
  }, [statsData]);

  async function loadSchedule() {
    try {
      const res = await api.get('/admin/auto-categorize/config');
      setSchedule(res.data);
    } catch { /* ignore */ }
    finally { setScheduleLoading(false); }
  }

  const toggleSchedule = async () => {
    setSavingSchedule(true);
    try {
      const res = await api.put('/admin/auto-categorize/config', { enabled: !schedule?.enabled });
      setSchedule(res.data);
    } catch { Alert.alert(tx('admin.batchAIPanel.auto.alert.error', 'Error'), tx('admin.batchAIPanel.auto.alert.updateScheduleFailed', 'Failed to update schedule')); }
    finally { setSavingSchedule(false); }
  };

  const updateHour = async (hour: number) => {
    setSavingSchedule(true);
    try {
      const res = await api.put('/admin/auto-categorize/config', { hour });
      setSchedule(res.data);
    } catch { Alert.alert(tx('admin.batchAIPanel.auto.alert.error', 'Error'), tx('admin.batchAIPanel.auto.alert.updateScheduleFailed', 'Failed to update schedule')); }
    finally { setSavingSchedule(false); }
  };

  const pollBatchJob = useCallback(async () => {
    if (!activeJobId) return;
    try {
      const res = await api.get(`/admin/batch-categorize/status/${activeJobId}`);
      const job = res.data.job;
      setStats((prev: any) => prev ? { ...prev, running_job: job } : prev);
      if (job.status === 'completed') {
        setActiveJobId('');
        setJobPolling(false);
        await loadStats();
      }
    } catch {
      setActiveJobId('');
      setJobPolling(false);
    }
  }, [activeJobId, loadStats]);

  useHybridPolling({
    enabled: Boolean(activeJobId) && jobPolling,
    errorScope: 'admin/batch-ai/job-polling',
    onTick: pollBatchJob,
    runOnMount: WORKFLOW_POLLING_PRESET.runOnMount,
    slowIntervalMs: WORKFLOW_POLLING_PRESET.slowIntervalMs,
    fastIntervalMs: WORKFLOW_POLLING_PRESET.fastIntervalMs,
    wsEnabled: WORKFLOW_POLLING_PRESET.wsEnabled,
  });

  const handleStart = async () => {
    if (stats?.uncategorized === 0) {
      Alert.alert(
        tx('admin.batchAIPanel.auto.alert.allDone', 'All Done'),
        tx('admin.batchAIPanel.auto.alert.noUncategorizedContent', 'No uncategorized content to process.')
      );
      return;
    }
    Alert.alert(
      tx('admin.batchAIPanel.auto.alert.startBatchRecategorization', 'Start Batch Re-categorization'),
      `This will AI-categorize ${stats?.uncategorized || 0} items using gpt-4o-mini. Each item costs ~0.001 credits. Continue?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Start', onPress: async () => {
            setStarting(true);
            try {
              const res = await api.post('/admin/batch-categorize/start');
              if (res.data.error) {
                Alert.alert(tx('admin.batchAIPanel.auto.alert.error', 'Error'), res.data.error);
              } else if (res.data.job) {
                setStats((prev: any) => prev ? { ...prev, running_job: res.data.job } : prev);
                setActiveJobId(String(res.data.job.job_id || ''));
                setJobPolling(true);
              }
            } catch { Alert.alert(tx('admin.batchAIPanel.auto.alert.error', 'Error'), tx('admin.batchAIPanel.auto.alert.startBatchFailed', 'Failed to start batch job')); }
            finally { setStarting(false); }
          }
        },
      ]
    );
  };

  const toTitle = (s: string) => s.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  if (loading) {
    return (
      <View style={{ paddingVertical: 40, alignItems: 'center' }}>
      <AutoFixBanner domain="batch_ai" />
        <ActivityIndicator size="large" color={C.primary} />
      </View>
    );
  }

  const job = stats?.running_job;
  const progress = job ? (job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0) : 0;

  return (
    <View data-testid="batch-ai-panel" testID="batch-ai-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 20, fontWeight: '800', color: C.text }} data-testid="batch-ai-title" testID="batch-ai-title">{tx('admin.batchAIPanel.auto.text.001', 'Batch Re-categorization')}</Text>
          <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 4 }}>{tx('admin.batchAIPanel.auto.text.002', 'Re-run AI categorization on all existing uncategorized content')}</Text>
        </View>
      </View>

      {/* Stats Cards */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Content', value: stats?.total || 0, icon: 'documents', color: colors.primary },
          { label: 'Uncategorized', value: stats?.uncategorized || 0, icon: 'alert-circle', color: colors.error },
          { label: 'AI Categorized', value: stats?.categorized || 0, icon: 'checkmark-circle', color: colors.successText },
        ].map(s => (
          <View key={s.label}
            style={{ flex: 1, minWidth: 120, backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, alignItems: 'center', gap: 8 }}
            data-testid={`batch-stat-${s.label.toLowerCase().replace(' ', '-')}`} testID={`batch-stat-${s.label.toLowerCase().replace(' ', '-')}`}>
            <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(s.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={s.icon as any} size={20} color={s.color} />
            </View>
            <Text style={{ fontSize: 22, fontWeight: '800', color: s.color }}>{s.value}</Text>
            <Text style={{ fontSize: 11, fontWeight: '600', color: C.textMuted }}>{s.label}</Text>
          </View>
        ))}
      </View>

      {/* Running Job Status */}
      {job && job.status === 'running' && (
        <View style={{ backgroundColor: colors.warningSoft, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.warningSoft, marginBottom: 20 }}
          data-testid="batch-job-running" testID="batch-job-running">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <ActivityIndicator size="small" color={'var(--app-warning)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.warningText }}>{tx('admin.batchAIPanel.auto.text.003', 'Processing...')}</Text>
            <Text style={{ fontSize: 12, color: C.textMuted, marginLeft: 'auto' }}>
              {job.processed}/{job.total} items
            </Text>
          </View>
          {/* Progress Bar */}
          <View style={{ height: 8, borderRadius: 4, backgroundColor: C.bgSoft, overflow: 'hidden' }}>
            <View style={{ height: '100%', borderRadius: 4, backgroundColor: colors.warning, width: `${progress}%` }} />
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
            <Text style={{ fontSize: 11, color: C.textMuted }}>{progress}% complete</Text>
            <Text style={{ fontSize: 11, color: C.textMuted }}>
              {job.succeeded} succeeded, {job.failed} failed
            </Text>
          </View>
        </View>
      )}

      {/* Completed Job Status */}
      {job && job.status === 'completed' && (
        <View style={{ backgroundColor: colors.successSoft, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.successSoft, marginBottom: 20 }}
          data-testid="batch-job-completed" testID="batch-job-completed">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Ionicons name="checkmark-circle" size={20} color={'var(--app-success)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.successText }}>{tx('admin.batchAIPanel.auto.text.004', 'Batch Complete')}</Text>
          </View>
          <Text style={{ fontSize: 12, color: C.textMuted }}>
            Processed {job.total} items: {job.succeeded} succeeded, {job.failed} failed
          </Text>
          {job.completed_at && (
            <Text style={{ fontSize: 10, color: C.textMuted, marginTop: 4 }}>
              Completed at {new Date(job.completed_at).toLocaleString()}
            </Text>
          )}
        </View>
      )}

      {/* Start Button */}
      <TouchableOpacity accessibilityLabel={tx('admin.batchAIPanel.auto.accessibility.001', 'Start batch AI processing')}
        onPress={handleStart}
        disabled={starting || (job?.status === 'running')}
        style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
          paddingVertical: 16, borderRadius: 14,
          backgroundColor: (stats?.uncategorized || 0) === 0 ? C.bgSoft : 'var(--app-card-muted)',
          opacity: starting || job?.status === 'running' ? 0.5 : 1,
          marginBottom: 24,
        }}
        data-testid="batch-start-btn" testID="batch-start-btn"
        accessibilityRole="button"
      >
        {starting ? (
          <ActivityIndicator size="small" color="var(--app-primary-text)" />
        ) : (
          <>
            <Ionicons name="color-wand" size={18} color={(stats?.uncategorized || 0) === 0 ? C.textMuted : 'var(--app-text-muted)'} />
            <Text style={{ fontSize: 15, fontWeight: '800', color: (stats?.uncategorized || 0) === 0 ? C.textMuted : 'var(--app-text-muted)' }}>
              {(stats?.uncategorized || 0) === 0 ? 'All Content Categorized' : `Categorize ${stats?.uncategorized} Items`}
            </Text>
          </>
        )}
      </TouchableOpacity>

      {/* Category Distribution */}
      {(stats?.category_distribution?.length > 0) && (
        <View style={{ marginBottom: 20 }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.batchAIPanel.auto.text.005', 'Category Distribution')}</Text>
          <View style={{ gap: 6 }}>
            {stats.category_distribution.map((c: any) => {
              const maxCount = Math.max(...stats.category_distribution.map((x: any) => x.count));
              const pct = maxCount > 0 ? (c.count / maxCount) * 100 : 0;
              const color = CAT_COLORS[c.category] || 'var(--app-text-muted)';
              return (
                <View key={c.category} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid={`batch-cat-${c.category}`} testID={`batch-cat-${c.category}`}>
                  <Text style={{ fontSize: 11, color: C.textMuted, width: 80, textAlign: 'right' }} numberOfLines={1}>{toTitle(c.category)}</Text>
                  <View style={{ flex: 1, height: 20, borderRadius: 6, backgroundColor: C.bgSoft, overflow: 'hidden' }}>
                    <View style={{ height: '100%', borderRadius: 6, backgroundColor: color, width: `${pct}%` }} />
                  </View>
                  <Text style={{ fontSize: 11, fontWeight: '700', color, width: 30, textAlign: 'right' }}>{c.count}</Text>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* Type Distribution */}
      {(stats?.type_distribution?.length > 0) && (
        <View style={{ marginBottom: 20 }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.batchAIPanel.auto.text.006', 'Type Distribution')}</Text>
          <View style={{ gap: 6 }}>
            {stats.type_distribution.map((t: any) => {
              const maxCount = Math.max(...stats.type_distribution.map((x: any) => x.count));
              const pct = maxCount > 0 ? (t.count / maxCount) * 100 : 0;
              const color = TYPE_COLORS[t.type] || 'var(--app-text-muted)';
              return (
                <View key={t.type} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid={`batch-type-${t.type}`} testID={`batch-type-${t.type}`}>
                  <Text style={{ fontSize: 11, color: C.textMuted, width: 80, textAlign: 'right' }} numberOfLines={1}>{toTitle(t.type)}</Text>
                  <View style={{ flex: 1, height: 20, borderRadius: 6, backgroundColor: C.bgSoft, overflow: 'hidden' }}>
                    <View style={{ height: '100%', borderRadius: 6, backgroundColor: color, width: `${pct}%` }} />
                  </View>
                  <Text style={{ fontSize: 11, fontWeight: '700', color, width: 30, textAlign: 'right' }}>{t.count}</Text>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* Nightly Auto-Categorization Schedule */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 20 }}
        data-testid="nightly-schedule-section" testID="nightly-schedule-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="moon" size={18} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{tx('admin.batchAIPanel.auto.text.007', 'Nightly Auto-Categorization')}</Text>
          </View>
          {!scheduleLoading && (
            <TouchableOpacity accessibilityLabel={tx('admin.batchAIPanel.auto.accessibility.002', 'Toggle batch AI schedule')}
              onPress={toggleSchedule}
              disabled={savingSchedule}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20,
                backgroundColor: schedule?.enabled ? 'var(--app-success-soft)' : C.bgSoft,
              }}
              data-testid="nightly-toggle-btn" testID="nightly-toggle-btn">
              {savingSchedule ? (
                <ActivityIndicator size="small" color={C.textMuted} />
              ) : (
                <>
                  <View style={{
                    width: 36, height: 20, borderRadius: 10,
                    backgroundColor: schedule?.enabled ? 'var(--app-success)' : 'var(--app-primary-soft)',
                    justifyContent: 'center',
                    paddingHorizontal: 2,
                  }}>
                    <View style={{
                      width: 16, height: 16, borderRadius: 8, backgroundColor: colors.primaryText,
                      alignSelf: schedule?.enabled ? 'flex-end' : 'flex-start',
                    }} />
                  </View>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: schedule?.enabled ? 'var(--app-success)' : C.textMuted }}>
                    {schedule?.enabled ? 'ON' : 'OFF'}
                  </Text>
                </>
              )}
            </TouchableOpacity>
          )}
        </View>

        {scheduleLoading ? (
          <ActivityIndicator size="small" color={C.primary} />
        ) : (
          <>
            <Text style={{ fontSize: 12, color: C.textMuted, marginBottom: 12 }}>{tx('admin.batchAIPanel.auto.text.008', 'Automatically categorizes new uncategorized content every night.')}</Text>

            {/* Time Selector */}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <Ionicons name="time" size={16} color={C.textMuted} />
              <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }}>{tx('admin.batchAIPanel.auto.text.009', 'Run at:')}</Text>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                {[0, 1, 2, 3, 4, 5, 6].map(h => (
                  <TouchableOpacity accessibilityLabel={tx('admin.batchAIPanel.auto.accessibility.003', 'Set schedule hour')}
                    key={h}
                    onPress={() => updateHour(h)}
                    disabled={savingSchedule}
                    style={{
                      paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8,
                      backgroundColor: schedule?.hour === h ? 'var(--app-primary)' : C.bgSoft,
                    }}
                    data-testid={`hour-btn-${h}`} testID={`hour-btn-${h}`}>
                    <Text style={{
                      fontSize: 11, fontWeight: '700',
                      color: schedule?.hour === h ? 'var(--app-primary-text)' : C.textMuted,
                    }}>{h}:00</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={{ fontSize: 10, color: C.textMuted }}>{tx('admin.batchAIPanel.auto.text.010', 'UTC')}</Text>
            </View>

            {/* Last Run Info */}
            {schedule?.last_run_at && (
              <View style={{
                flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 12,
                borderTopWidth: 1, borderTopColor: C.border,
              }} data-testid="last-run-info" testID="last-run-info">
                <Ionicons name="checkmark-done" size={14} color={'var(--app-success)'} />
                <Text style={{ fontSize: 11, color: C.textMuted }}>
                  Last run: {new Date(schedule.last_run_at).toLocaleString()}
                </Text>
                {schedule.last_run_result && (
                  <Text style={{ fontSize: 11, color: colors.successText, fontWeight: '600' }}>
                    ({schedule.last_run_result.succeeded}/{schedule.last_run_result.total} succeeded)
                  </Text>
                )}
              </View>
            )}
            {!schedule?.last_run_at && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name="hourglass" size={12} color={C.textMuted} />
                <Text style={{ fontSize: 11, color: C.textMuted }}>No runs yet — first run scheduled at {schedule?.hour || 2}:00 UTC</Text>
              </View>
            )}
          </>
        )}
      </View>

      {/* Info */}
      <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <Ionicons name="information-circle" size={16} color={C.primary} />
          <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.batchAIPanel.auto.text.011', 'How it works')}</Text>
        </View>
        <Text style={{ fontSize: 11, color: C.textMuted, lineHeight: 18 }}>{tx('admin.batchAIPanel.auto.text.012', 'Each uncategorized content item is sent to gpt-4o-mini which analyzes the title, content, and feature context to assign the best category and type. Items are processed with a 0.5s delay between each to avoid rate limits. Already categorized items are skipped. The nightly job runs automatically at your configured time.')}</Text>
      </View>
    </View>
  );
}
