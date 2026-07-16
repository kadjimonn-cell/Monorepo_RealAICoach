import React, { useState, useEffect } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { View, Text, ActivityIndicator, TouchableOpacity, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

function makeT(AC: any) { return {
  bg: AC.bg,
  bgSoft: AC.bgSoft,
  card: AC.card,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  textDim: AC.textDim || AC.textMuted,
  primary: AC.primary,
  success: AC.success,
  successText: AC.successText || AC.success,
  successSoft: AC.successSoft || `${AC.success}20`,
  warning: AC.warning,
  warningText: AC.warningText || AC.warning,
  warningSoft: AC.warningSoft || `${AC.warning}20`,
  error: AC.error,
  errorText: AC.errorText || AC.error,
  errorSoft: AC.errorSoft || `${AC.error}20`,
  purple: AC.purple,
  purpleText: AC.purpleText || AC.purple,
  cyan: AC.cyan || AC.info,
  teal: AC.teal || AC.cyan || AC.info,
  ai: AC.cyan || AC.info,
  orange: AC.orange,
  orangeText: AC.orangeText || AC.orange,
  pink: AC.pink || AC.purple,
  primaryText: AC.primaryText || 'var(--app-primary-text)',
}; }

// Module-scope fallback for REPAIR_ICONS (can't use component-scoped T here)
const T = {
  bg: 'var(--app-bg)', bgSoft: 'var(--app-card-muted)', card: 'var(--app-card-bg)',
  border: 'var(--app-border)', text: 'var(--app-text)', textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)',
  primary: 'var(--app-primary)', success: 'var(--app-success)', warning: 'var(--app-warning)', error: 'var(--app-error)',
  purple: 'var(--app-primary)', cyan: 'var(--app-primary)',
  successText: 'var(--app-success)', warningText: 'var(--app-warning)', purpleText: 'var(--app-primary)',
  primaryText: 'var(--app-primary-text)',
};

interface Props { colors: any; }

type TabId = 'dashboard' | 'history' | 'config';

const REPAIR_ICONS: Record<string, { icon: string; color: string }> = {
  stale_sessions_cleared: { icon: 'time', color: T.cyan },
  old_notifications_purged: { icon: 'notifications-off', color: T.warningText },
  missing_plans_fixed: { icon: 'card', color: T.primary },
  missing_admin_flag_fixed: { icon: 'shield', color: T.purpleText },
  ticket_status_fixed: { icon: 'chatbubble', color: T.successText },
  indexes_verified: { icon: 'git-branch', color: T.primary },
  rate_limit_cache_cleared: { icon: 'speedometer', color: T.warningText },
  orphaned_tickets_flagged: { icon: 'flag', color: T.error },
  old_error_logs_cleared: { icon: 'trash', color: T.textMuted },
};

export default function SelfRepairPanel({ colors }: Props) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<TabId>('dashboard');
  const { data: health, loading: loadingHealth, refetch: loadHealth } = useLiveQuery('/admin/system/health-deep', { entity: 'system-health', pollInterval: 30000 });
  const [history, setHistory] = useState<any>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [repairResult, setRepairResult] = useState<any>(null);
  const [configSaving, setConfigSaving] = useState(false);
  const [localConfig, setLocalConfig] = useState<any>(null);

  const loadHistory = () => {
    setLoadingHistory(true);
    api.get('/admin/system/repair-history').then(r => {
      setHistory(r.data);
      if (!localConfig && r.data.config) setLocalConfig(r.data.config);
    }).catch(() => {}).finally(() => setLoadingHistory(false));
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadHealth(); loadHistory(); }, []);

  const runRepair = async () => {
    setRepairing(true);
    setRepairResult(null);
    try {
      const res = await api.post('/admin/system/self-repair');
      setRepairResult(res.data);
      loadHealth();
      loadHistory();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/SelfRepairPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setRepairing(false); }
  };

  const saveConfig = async (key: string, value: any) => {
    const updated = { ...localConfig, [key]: value };
    setLocalConfig(updated);
    setConfigSaving(true);
    try {
      await api.post('/admin/system/repair-config', { [key]: value });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/SelfRepairPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setConfigSaving(false); }
  };

  const tabs: { id: TabId; label: string; icon: string }[] = [
    { id: 'dashboard', label: 'Health', icon: 'pulse' },
    { id: 'history', label: 'Repair History', icon: 'time' },
    { id: 'config', label: 'Config', icon: 'settings' },
  ];

  return (
    <View data-testid="self-repair-panel" testID="self-repair-panel">
      <AutoFixBanner domain="system_health" />
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="self-repair-title" testID="self-repair-title">{tx('admin.selfRepairPanel.header.title', 'Self-Repair Engine')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 4 }}>{tx('admin.selfRepairPanel.header.subtitle', 'Autonomous system health monitoring & auto-repair')}</Text>
        </View>
        <TouchableOpacity
          onPress={runRepair}
          disabled={repairing}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: repairing ? T.bgSoft : T.success }}
          data-testid="run-repair-btn" testID="run-repair-btn"
        >
          <Ionicons name={repairing ? 'hourglass' : 'construct'} size={14} color={T.primaryText} />
          <Text style={{ fontSize: 12, fontWeight: '700', color: T.primaryText }}>{repairing ? 'Repairing...' : 'Run Repair'}</Text>
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {tabs.map(t => (
          <TouchableOpacity
            key={t.id}
            onPress={() => { setTab(t.id); if (t.id === 'history' && !history) loadHistory(); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8, backgroundColor: tab === t.id ? T.primary : T.card, borderWidth: 1, borderColor: tab === t.id ? T.primary : T.border }}
            data-testid={`repair-tab-${t.id}`} testID={`repair-tab-${t.id}`}
          >
            <Ionicons name={t.icon as any} size={13} color={tab === t.id ? T.primaryText : T.textMuted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: tab === t.id ? T.primaryText : T.textMuted }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Repair Result Banner */}
      {repairResult && (
        <View style={{ backgroundColor: repairResult.total > 0 ? 'var(--app-success-soft)' : 'var(--app-primary-soft)', borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: repairResult.total > 0 ? 'var(--app-success-soft)' : 'var(--app-primary-soft)' }} data-testid="repair-result-banner" testID="repair-result-banner">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Ionicons name={repairResult.total > 0 ? 'construct' : 'checkmark-circle'} size={18} color={repairResult.total > 0 ? T.success : T.primary} />
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>
              {repairResult.total > 0 ? `${repairResult.total} repairs applied` : 'System is healthy — no repairs needed'}
            </Text>
          </View>
          {(repairResult.repairs || []).map((r: any, i: number) => {
            const ri = REPAIR_ICONS[r.type] || { icon: 'ellipse', color: T.textMuted };
            return (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 }}>
                <Ionicons name={ri.icon as any} size={12} color={ri.color} />
                <Text style={{ color: T.textSec, fontSize: 12 }}>{r.type.replace(/_/g, ' ')}: {r.count}</Text>
              </View>
            );
          })}
        </View>
      )}

      {/* Dashboard Tab */}
      {tab === 'dashboard' && (
        loadingHealth ? (
          <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>
        ) : health ? (
          <View>
            {/* Health Score */}
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border, alignItems: 'center', marginBottom: 16 }} data-testid="health-score-card" testID="health-score-card">
              <View style={{
                width: 90, height: 90, borderRadius: 45, borderWidth: 5,
                borderColor: health.health_score >= 90 ? (globalThis as any).__alphaColor(T.success, '50') : health.health_score >= 60 ? T.warning + '50' : T.error + '50',
                alignItems: 'center', justifyContent: 'center', marginBottom: 10,
              }}>
                <Text style={{ color: health.health_score >= 90 ? T.success : health.health_score >= 60 ? T.warning : T.error, fontSize: 28, fontWeight: '900' }}>
                  {health.health_score}
                </Text>
              </View>
              <Text style={{
                color: health.health_status === 'healthy' ? T.success : health.health_status === 'degraded' ? T.warning : T.error,
                fontSize: 16, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase',
              }}>
                {health.health_status}
              </Text>
              {health.issues?.length > 0 && (
                <View style={{ marginTop: 10, gap: 4 }}>
                  {health.issues.map((issue: string, i: number) => (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Ionicons name="warning" size={12} color={T.warningText} />
                      <Text style={{ color: T.warningText, fontSize: 11 }}>{issue}</Text>
                    </View>
                  ))}
                </View>
              )}
            </View>

            {/* System Resources */}
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="system-resources-card" testID="system-resources-card">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.selfRepairPanel.dashboard.systemResources', 'System Resources')}</Text>
              <View style={{ gap: 10 }}>
                <ResourceBar label="CPU" value={health.system?.cpu_percent || 0} color={T.primary} />
                <ResourceBar label="Memory" value={health.system?.memory_used_pct || 0} color={T.purpleText} />
                <ResourceBar label="Disk" value={health.system?.disk_used_pct || 0} color={T.cyan} />
              </View>
            </View>

            {/* Database */}
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="database-status-card" testID="database-status-card">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.selfRepairPanel.dashboard.database', 'Database')}</Text>
              <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                <StatBox label="Status" value={health.database?.connected ? 'OK' : 'DOWN'} color={health.database?.connected ? T.success : T.error} />
                <StatBox label="Latency" value={`${health.database?.latency_ms || 0}ms`} color={T.primary} />
                <StatBox label="Size" value={`${health.database?.size_mb || 0}MB`} color={T.purpleText} />
                <StatBox label="Collections" value={health.database?.collections || 0} color={T.cyan} />
              </View>
            </View>

            {/* Sessions */}
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="sessions-card" testID="sessions-card">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.selfRepairPanel.dashboard.sessions', 'Sessions')}</Text>
              <View style={{ flexDirection: 'row', gap: 10 }}>
                <StatBox label="Active" value={health.sessions?.active || 0} color={T.successText} />
                <StatBox label="Stale" value={health.sessions?.stale || 0} color={health.sessions?.stale > 50 ? T.warning : T.textMuted} />
              </View>
            </View>
          </View>
        ) : (
          <Text style={{ color: T.error, padding: 20 }}>{tx('admin.selfRepairPanel.states.healthLoadFailed', 'Failed to load health data')}</Text>
        )
      )}

      {/* History Tab */}
      {tab === 'history' && (
        loadingHistory ? (
          <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>
        ) : history ? (
          <View>
            {/* Aggregate Stats */}
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }} data-testid="repair-stats" testID="repair-stats">
              <StatBox label="Total Cycles" value={history.stats?.total_cycles || 0} color={T.primary} />
              <StatBox label="Total Repairs" value={history.stats?.total_repairs || 0} color={T.successText} />
            </View>

            {/* Repair Type Breakdown */}
            {history.stats?.repair_types && Object.keys(history.stats.repair_types).length > 0 && (
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="repair-type-breakdown" testID="repair-type-breakdown">
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.selfRepairPanel.history.typeBreakdown', 'Repair Type Breakdown')}</Text>
                {Object.entries(history.stats.repair_types).map(([type, count]: [string, any], i: number) => {
                  const ri = REPAIR_ICONS[type] || { icon: 'ellipse', color: T.textMuted };
                  return (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: T.border }}>
                      <Ionicons name={ri.icon as any} size={14} color={ri.color} />
                      <Text style={{ color: T.text, fontSize: 12, flex: 1 }}>{type.replace(/_/g, ' ')}</Text>
                      <Text style={{ color: ri.color, fontSize: 13, fontWeight: '700' }}>{count}</Text>
                    </View>
                  );
                })}
              </View>
            )}

            {/* History Timeline */}
            <View style={{ gap: 10 }}>
              {(history.history || []).map((entry: any, idx: number) => (
                <View key={idx} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid={`repair-history-${idx}`} testID={`repair-history-${idx}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: (entry.total_repairs || entry.repairs?.length || 0) > 0 ? T.success : T.primary }} />
                      <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>
                        {(entry.total_repairs || entry.repairs?.length || 0)} repairs
                      </Text>
                    </View>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>
                      {entry.timestamp?.slice(0, 16)?.replace('T', ' ')}
                    </Text>
                  </View>
                  {(entry.repairs || []).map((r: any, ri: number) => {
                    const icon = REPAIR_ICONS[r.type] || { icon: 'ellipse', color: T.textMuted };
                    return (
                      <View key={ri} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 3 }}>
                        <Ionicons name={icon.icon as any} size={11} color={icon.color} />
                        <Text style={{ color: T.textSec, fontSize: 11 }}>{r.type.replace(/_/g, ' ')}: {r.count}</Text>
                        <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, backgroundColor: r.severity === 'medium' ? (globalThis as any).__alphaColor(T.warning, '20') : T.primary + '20' }}>
                          <Text style={{ color: r.severity === 'medium' ? T.warning : T.primary, fontSize: 9, fontWeight: '600' }}>{r.severity}</Text>
                        </View>
                      </View>
                    );
                  })}
                </View>
              ))}
              {(!history.history || history.history.length === 0) && (
                <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 30, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
                  <Ionicons name="construct-outline" size={36} color={T.textMuted} />
                  <Text style={{ color: T.textSec, fontSize: 14, marginTop: 10 }}>{tx('admin.selfRepairPanel.history.empty', 'No repair history yet')}</Text>
                </View>
              )}
            </View>
          </View>
        ) : null
      )}

      {/* Config Tab */}
      {tab === 'config' && localConfig && (
        <View>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="repair-config-panel" testID="repair-config-panel">
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.selfRepairPanel.config.title', 'Repair Configuration')}</Text>
              {configSaving && <ActivityIndicator size="small" color={T.primary} />}
            </View>
            <ConfigToggle label="Engine Enabled" value={localConfig.enabled} onChange={v => saveConfig('enabled', v)} />
            <ConfigToggle label="Alert on Repair" value={localConfig.alert_on_repair} onChange={v => saveConfig('alert_on_repair', v)} />
            <ConfigToggle label="Auto-Clear Stale Sessions" value={localConfig.auto_clear_stale_sessions} onChange={v => saveConfig('auto_clear_stale_sessions', v)} />
            <ConfigToggle label="Auto-Fix Missing Fields" value={localConfig.auto_fix_missing_fields} onChange={v => saveConfig('auto_fix_missing_fields', v)} />
            <ConfigToggle label="Auto-Purge Old Notifications" value={localConfig.auto_purge_old_notifications} onChange={v => saveConfig('auto_purge_old_notifications', v)} />
            <ConfigToggle label="Auto-Repair Indexes" value={localConfig.auto_repair_indexes} onChange={v => saveConfig('auto_repair_indexes', v)} />
            <ConfigToggle label="Auto-Clear Rate Limits" value={localConfig.auto_clear_rate_limits} onChange={v => saveConfig('auto_clear_rate_limits', v)} />
          </View>

          {/* Numeric Settings */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="repair-numeric-config" testID="repair-numeric-config">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.selfRepairPanel.config.thresholds', 'Thresholds')}</Text>
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 10, padding: 14, alignItems: 'center' }}>
                <Text style={{ color: T.primary, fontSize: 24, fontWeight: '800' }}>{localConfig.stale_session_hours || 24}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{tx('admin.selfRepairPanel.config.staleSessionHours', 'Stale Session Hours')}</Text>
              </View>
              <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 10, padding: 14, alignItems: 'center' }}>
                <Text style={{ color: T.purpleText, fontSize: 24, fontWeight: '800' }}>{localConfig.old_notification_days || 30}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{tx('admin.selfRepairPanel.config.oldNotifDays', 'Old Notif Days')}</Text>
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}

function ResourceBar({ label, value, color }: { label: string; value: number; color: string }) {
  const barColor = value > 90 ? T.error : value > 70 ? T.warning : color;
  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text style={{ color: T.textSec, fontSize: 12 }}>{label}</Text>
        <Text style={{ color: barColor, fontSize: 12, fontWeight: '700' }}>{value.toFixed(1)}%</Text>
      </View>
      <View style={{ height: 6, backgroundColor: T.bgSoft, borderRadius: 3, overflow: 'hidden' }}>
        <View style={{ height: 6, width: `${Math.min(value, 100)}%` as any, backgroundColor: barColor, borderRadius: 3 }} />
      </View>
    </View>
  );
}

function StatBox({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 10, padding: 12, alignItems: 'center', minWidth: 70 }}>
      <Text style={{ color, fontSize: 18, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{label}</Text>
    </View>
  );
}

function ConfigToggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border }}>
      <Text style={{ color: T.text, fontSize: 13 }}>{label}</Text>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: T.bgSoft, true: T.success + '60' }}
        thumbColor={value ? T.success : T.textMuted}
      />
    </View>
  );
}
