import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

type Props = {
  colors: any;
};

type AssignedHostConfigDraft = {
  enabled: boolean;
  check_interval_minutes: string;
  failure_streak_threshold: string;
  repeated_failure_alert_every: string;
  restart_cooldown_minutes: string;
  auto_fallback_enabled: boolean;
  auto_fix_sync_env: boolean;
  auto_fix_restart_services: boolean;
  state_change_alerts_enabled: boolean;
  in_app_alerts_enabled: boolean;
  email_alerts_enabled: boolean;
};

const defaultDraft: AssignedHostConfigDraft = {
  enabled: true,
  check_interval_minutes: '5',
  failure_streak_threshold: '2',
  repeated_failure_alert_every: '3',
  restart_cooldown_minutes: '20',
  auto_fallback_enabled: true,
  auto_fix_sync_env: true,
  auto_fix_restart_services: true,
  state_change_alerts_enabled: true,
  in_app_alerts_enabled: true,
  email_alerts_enabled: true,
};

const boolLabel = (value: boolean) => (value ? 'ON' : 'OFF');

export default function AssignedHostControlCenterPanel({ colors }: Props) {
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [forceRunning, setForceRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const [latest, setLatest] = useState<any>({});
  const [history, setHistory] = useState<any[]>([]);
  const [trend, setTrend] = useState<any>({ total: 0, pass_count: 0, fail_count: 0, pass_rate: 0 });
  const [state, setState] = useState<any>({});
  const [heartbeat, setHeartbeat] = useState<any>({});
  const [draft, setDraft] = useState<AssignedHostConfigDraft>(defaultDraft);

  const hydrateDraft = useCallback((cfg: any) => {
    if (!cfg || typeof cfg !== 'object') return;
    setDraft({
      enabled: Boolean(cfg?.enabled ?? true),
      check_interval_minutes: String(cfg?.check_interval_minutes ?? 5),
      failure_streak_threshold: String(cfg?.failure_streak_threshold ?? 2),
      repeated_failure_alert_every: String(cfg?.repeated_failure_alert_every ?? 3),
      restart_cooldown_minutes: String(cfg?.restart_cooldown_minutes ?? 20),
      auto_fallback_enabled: Boolean(cfg?.auto_fallback_enabled ?? true),
      auto_fix_sync_env: Boolean(cfg?.auto_fix_sync_env ?? true),
      auto_fix_restart_services: Boolean(cfg?.auto_fix_restart_services ?? true),
      state_change_alerts_enabled: Boolean(cfg?.state_change_alerts_enabled ?? true),
      in_app_alerts_enabled: Boolean(cfg?.in_app_alerts_enabled ?? true),
      email_alerts_enabled: Boolean(cfg?.email_alerts_enabled ?? true),
    });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/platform-health/assigned-host/latest?limit=40', { silentLoading: true });
      setLatest(res?.data?.latest || {});
      setHistory(Array.isArray(res?.data?.history) ? res.data.history : []);
      setTrend(res?.data?.trend || { total: 0, pass_count: 0, fail_count: 0, pass_rate: 0 });
      setState(res?.data?.state || {});
      setHeartbeat(res?.data?.heartbeat || {});
      hydrateDraft(res?.data?.config || defaultDraft);
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Failed to load Assigned Host control center.');
    } finally {
      setLoading(false);
    }
  }, [hydrateDraft]);

  useEffect(() => {
    void load();
  }, [load]);

  const status = useMemo(() => {
    const s = String(latest?.status || state?.last_status || 'unknown').toLowerCase();
    if (s === 'pass') return 'PASS';
    if (s === 'fail') return 'FAIL';
    return 'UNKNOWN';
  }, [latest?.status, state?.last_status]);

  const statusColor = status === 'PASS' ? colors.successText : status === 'FAIL' ? colors.error : colors.warning;
  const currentFailStreak = Number(trend?.current_fail_streak || latest?.fail_streak || 0);
  const failureThreshold = Number(draft?.failure_streak_threshold || 2);
  const cooldownRemainingSeconds = Number(latest?.auto_fallback?.cooldown_remaining_seconds || 0);
  const failureReasons: string[] = Array.isArray(latest?.failure_reasons) ? latest.failure_reasons : [];
  const hasRedirectRegression = failureReasons.some((reason) => String(reason || '').includes('redirect_regression'));

  const escalationLevel = useMemo(() => {
    if (status === 'FAIL' && (hasRedirectRegression || currentFailStreak >= failureThreshold)) return 'CRITICAL';
    if (status === 'FAIL' || currentFailStreak > 0 || cooldownRemainingSeconds > 0) return 'WARNING';
    return 'INFO';
  }, [status, hasRedirectRegression, currentFailStreak, failureThreshold, cooldownRemainingSeconds]);

  const fallbackNextRunText = useMemo(() => {
    if (!draft.auto_fallback_enabled) return 'Auto fallback disabled by policy.';
    if (cooldownRemainingSeconds > 0) {
      const mins = Math.ceil(cooldownRemainingSeconds / 60);
      return `Cooldown active (${mins} min remaining). Next run checks again automatically.`;
    }
    if (currentFailStreak >= failureThreshold) {
      return `Next run will auto-trigger fallback (fail streak ${currentFailStreak} ≥ threshold ${failureThreshold}).`;
    }
    return `Next run will trigger fallback when fail streak reaches ${failureThreshold} (current ${currentFailStreak}).`;
  }, [draft.auto_fallback_enabled, cooldownRemainingSeconds, currentFailStreak, failureThreshold]);

  const toggleDraft = useCallback((key: keyof AssignedHostConfigDraft) => {
    setDraft((prev) => ({ ...prev, [key]: !prev[key as keyof AssignedHostConfigDraft] }));
  }, []);

  const updateDraft = useCallback((key: keyof AssignedHostConfigDraft, value: string) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }, []);

  const runNow = useCallback(async (forceFallback = false) => {
    if (forceFallback) {
      setForceRunning(true);
    } else {
      setRunning(true);
    }
    setMessage('');
    try {
      const endpoint = forceFallback
        ? '/admin/platform-health/assigned-host/run?triggered_by=manual:admin:force-fallback&allow_auto_fallback=true&force_fallback=true'
        : '/admin/platform-health/assigned-host/run?triggered_by=manual:admin&allow_auto_fallback=true';
      const res = await api.post(endpoint);
      setLatest(res?.data?.run || {});
      setMessage(forceFallback ? 'Safe fallback cycle executed.' : 'Assigned host monitor run completed.');
      await load();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Failed to run assigned host monitor.');
    } finally {
      if (forceFallback) {
        setForceRunning(false);
      } else {
        setRunning(false);
      }
    }
  }, [load]);

  const saveConfig = useCallback(async () => {
    setSaving(true);
    setMessage('');
    try {
      const payload = {
        enabled: Boolean(draft.enabled),
        check_interval_minutes: Number(draft.check_interval_minutes || 5),
        failure_streak_threshold: Number(draft.failure_streak_threshold || 2),
        repeated_failure_alert_every: Number(draft.repeated_failure_alert_every || 3),
        restart_cooldown_minutes: Number(draft.restart_cooldown_minutes || 20),
        auto_fallback_enabled: Boolean(draft.auto_fallback_enabled),
        auto_fix_sync_env: Boolean(draft.auto_fix_sync_env),
        auto_fix_restart_services: Boolean(draft.auto_fix_restart_services),
        state_change_alerts_enabled: Boolean(draft.state_change_alerts_enabled),
        in_app_alerts_enabled: Boolean(draft.in_app_alerts_enabled),
        email_alerts_enabled: Boolean(draft.email_alerts_enabled),
      };
      await api.post('/admin/platform-health/assigned-host/config', payload);
      setMessage('Assigned Host policy saved.');
      await load();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Failed to save assigned host policy.');
    } finally {
      setSaving(false);
    }
  }, [draft, load]);

  const kpi = [
    { label: 'Expected Host', value: latest?.expected_host || state?.expected_host || '—', testId: 'assigned-host-kpi-expected-host' },
    { label: 'Resolved Host', value: latest?.resolved_host || '—', testId: 'assigned-host-kpi-resolved-host' },
    { label: 'Fail Streak', value: String(trend?.current_fail_streak || 0), testId: 'assigned-host-kpi-fail-streak' },
    { label: 'Pass Rate', value: `${trend?.pass_rate || 0}%`, testId: 'assigned-host-kpi-pass-rate' },
  ];

  const configToggleKeys: Array<{ key: keyof AssignedHostConfigDraft; label: string }> = [
    { key: 'enabled', label: 'Auto-run enabled' },
    { key: 'auto_fallback_enabled', label: 'Safe auto fallback enabled' },
    { key: 'auto_fix_sync_env', label: 'Auto-sync env host keys' },
    { key: 'auto_fix_restart_services', label: 'Auto-restart services' },
    { key: 'state_change_alerts_enabled', label: 'State-change alerts' },
    { key: 'in_app_alerts_enabled', label: 'In-app alerts' },
    { key: 'email_alerts_enabled', label: 'Email alerts' },
  ];

  return (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={{ gap: 12, paddingBottom: 22 }}
      data-testid="assigned-host-control-center-panel"
      testID="assigned-host-control-center-panel"
    >
      <View
        style={{ borderRadius: 14, borderWidth: 1, borderColor: status === 'FAIL' ? colors.error : colors.border, backgroundColor: colors.card, padding: 14 }}
        data-testid="assigned-host-header-card"
        testID="assigned-host-header-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="assigned-host-title" testID="assigned-host-title">
              Assigned Host Control Center
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }} data-testid="assigned-host-subtitle" testID="assigned-host-subtitle">
              Global preview host guardrail with safe auto-runs, safe auto fallback, and admin alerting.
            </Text>
          </View>
          <View style={{ borderRadius: 999, backgroundColor: `${statusColor}22`, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="assigned-host-status-pill" testID="assigned-host-status-pill">
            <Text style={{ color: statusColor, fontSize: 11, fontWeight: '800' }} data-testid="assigned-host-status-pill-text" testID="assigned-host-status-pill-text">{status}</Text>
          </View>
        </View>

        <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 8 }} data-testid="assigned-host-last-run-text" testID="assigned-host-last-run-text">
          Last run: {latest?.created_at ? new Date(latest.created_at).toLocaleString() : 'Never'}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }} data-testid="assigned-host-heartbeat-text" testID="assigned-host-heartbeat-text">
          Scheduler heartbeat: {String(heartbeat?.status || 'unknown').toUpperCase()} • {heartbeat?.last_run ? new Date(heartbeat.last_run).toLocaleString() : '-'}
        </Text>

        <View
          style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: `${statusColor}55`, backgroundColor: `${statusColor}14`, padding: 10, gap: 8 }}
          data-testid="assigned-host-escalation-ladder"
          testID="assigned-host-escalation-ladder"
        >
          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="assigned-host-escalation-title" testID="assigned-host-escalation-title">
            Escalation Ladder (Info / Warning / Critical)
          </Text>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[
              { level: 'INFO', color: colors.info, note: 'Host healthy, no fallback pressure.' },
              { level: 'WARNING', color: colors.warning, note: 'Detected drift/failures; monitoring auto-run progression.' },
              { level: 'CRITICAL', color: colors.error, note: 'Regression/high fail streak; fallback path is active.' },
            ].map((item) => {
              const active = escalationLevel === item.level;
              return (
                <View
                  key={item.level}
                  style={{ minWidth: 220, flexGrow: 1, borderRadius: 9, borderWidth: 1, borderColor: active ? `${item.color}99` : colors.border, backgroundColor: active ? `${item.color}1f` : colors.surface, padding: 8 }}
                  data-testid={`assigned-host-escalation-level-${item.level.toLowerCase()}`}
                  testID={`assigned-host-escalation-level-${item.level.toLowerCase()}`}
                >
                  <Text style={{ color: active ? item.color : colors.textMuted, fontSize: 10, fontWeight: '800' }} data-testid={`assigned-host-escalation-level-${item.level.toLowerCase()}-label`} testID={`assigned-host-escalation-level-${item.level.toLowerCase()}-label`}>
                    {item.level}{active ? ' (CURRENT)' : ''}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }} data-testid={`assigned-host-escalation-level-${item.level.toLowerCase()}-note`} testID={`assigned-host-escalation-level-${item.level.toLowerCase()}-note`}>
                    {item.note}
                  </Text>
                </View>
              );
            })}
          </View>

          <Text style={{ color: statusColor, fontSize: 10, fontWeight: '700' }} data-testid="assigned-host-escalation-current-level-text" testID="assigned-host-escalation-current-level-text">
            Current level: {escalationLevel}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="assigned-host-escalation-trigger-summary" testID="assigned-host-escalation-trigger-summary">
            {fallbackNextRunText}
          </Text>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="assigned-host-kpi-grid" testID="assigned-host-kpi-grid">
        {kpi.map((item) => (
          <View
            key={item.testId}
            style={{ minWidth: 200, flexGrow: 1, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }}
            data-testid={item.testId}
            testID={item.testId}
          >
            <Text style={{ color: colors.textMuted, fontSize: 10 }}>{item.label}</Text>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', marginTop: 4 }}>{item.value}</Text>
          </View>
        ))}
      </View>

      <View
        style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12, gap: 8 }}
        data-testid="assigned-host-actions-card"
        testID="assigned-host-actions-card"
      >
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="assigned-host-actions-title" testID="assigned-host-actions-title">
          Safe Auto Runs
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TouchableOpacity
            onPress={() => void runNow(false)}
            disabled={running}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: colors.primary, opacity: running ? 0.7 : 1 }}
            data-testid="assigned-host-run-now-button"
            testID="assigned-host-run-now-button"
          >
            {running ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="play-circle-outline" size={14} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{running ? 'Running...' : 'Run Guard Now'}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => void runNow(true)}
            disabled={forceRunning}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: `${colors.warning}22`, borderWidth: 1, borderColor: `${colors.warning}66`, opacity: forceRunning ? 0.7 : 1 }}
            data-testid="assigned-host-force-fallback-button"
            testID="assigned-host-force-fallback-button"
          >
            {forceRunning ? <ActivityIndicator size="small" color={colors.warning} /> : <Ionicons name="shield-checkmark-outline" size={14} color={colors.warning} />}
            <Text style={{ color: colors.warning, fontSize: 11, fontWeight: '800' }}>{forceRunning ? 'Running...' : 'Run Safe Fallback'}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => void load()}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}
            data-testid="assigned-host-refresh-button"
            testID="assigned-host-refresh-button"
          >
            <Ionicons name="refresh-outline" size={14} color={colors.textMuted} />
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800' }}>Refresh</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View
        style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12, gap: 10 }}
        data-testid="assigned-host-config-card"
        testID="assigned-host-config-card"
      >
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="assigned-host-config-title" testID="assigned-host-config-title">
          Safe Auto Fallback Policy
        </Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {[
            { key: 'check_interval_minutes', label: 'Auto-run interval (min)' },
            { key: 'failure_streak_threshold', label: 'Fallback start at fail streak' },
            { key: 'repeated_failure_alert_every', label: 'Repeat alert every N fails' },
            { key: 'restart_cooldown_minutes', label: 'Fallback restart cooldown (min)' },
          ].map((field) => (
            <View key={field.key} style={{ minWidth: 220, flexGrow: 1 }}>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginBottom: 4 }}>{field.label}</Text>
              <TextInput accessibilityLabel="Text input"
                value={(draft as any)[field.key]}
                onChangeText={(value) => updateDraft(field.key as keyof AssignedHostConfigDraft, value)}
                keyboardType="number-pad"
                style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, backgroundColor: colors.surface, color: colors.text, paddingHorizontal: 10, paddingVertical: 8, fontSize: 12 }}
                data-testid={`assigned-host-config-input-${field.key}`}
                testID={`assigned-host-config-input-${field.key}`}
              />
            </View>
          ))}
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {configToggleKeys.map((toggle) => {
            const active = Boolean(draft[toggle.key]);
            return (
              <TouchableOpacity
                key={toggle.key}
                onPress={() => toggleDraft(toggle.key)}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? `${colors.successText}77` : colors.border, backgroundColor: active ? `${colors.successText}22` : colors.surface, paddingHorizontal: 10, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
                data-testid={`assigned-host-toggle-${toggle.key}`}
                testID={`assigned-host-toggle-${toggle.key}`}
              >
                <Ionicons name={active ? 'checkmark-circle' : 'ellipse-outline'} size={13} color={active ? colors.successText : colors.textMuted} />
                <Text style={{ color: active ? colors.successText : colors.textMuted, fontSize: 10, fontWeight: '800' }}>{toggle.label}: {boolLabel(active)}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <TouchableOpacity
          onPress={() => void saveConfig()}
          disabled={saving}
          style={{ marginTop: 2, alignSelf: 'flex-start', borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: colors.info, opacity: saving ? 0.75 : 1, flexDirection: 'row', alignItems: 'center', gap: 6 }}
          data-testid="assigned-host-save-policy-button"
          testID="assigned-host-save-policy-button"
        >
          {saving ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="save-outline" size={14} color={colors.primaryText} />}
          <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{saving ? 'Saving...' : 'Save Policy'}</Text>
        </TouchableOpacity>
      </View>

      <View
        style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}
        data-testid="assigned-host-history-card"
        testID="assigned-host-history-card"
      >
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="assigned-host-history-title" testID="assigned-host-history-title">
          Recent Assigned Host Runs
        </Text>
        {loading ? (
          <View style={{ marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="assigned-host-loading-row" testID="assigned-host-loading-row">
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>Loading run history...</Text>
          </View>
        ) : (
          <View style={{ marginTop: 10, gap: 8 }} data-testid="assigned-host-history-list" testID="assigned-host-history-list">
            {(history || []).slice(0, 10).map((item: any, idx: number) => {
              const itemStatus = String(item?.status || 'unknown').toUpperCase();
              const itemStatusColor = itemStatus === 'PASS' ? colors.successText : itemStatus === 'FAIL' ? colors.error : colors.warning;
              const failReasons = Array.isArray(item?.failure_reasons) ? item.failure_reasons.slice(0, 2).join(', ') : 'none';
              const fallbackApplied = Boolean(item?.auto_fallback?.applied);
              return (
                <View
                  key={`${item?.run_id || 'run'}-${idx}`}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 10 }}
                  data-testid={`assigned-host-history-item-${idx}`}
                  testID={`assigned-host-history-item-${idx}`}
                >
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }} data-testid={`assigned-host-history-item-run-id-${idx}`} testID={`assigned-host-history-item-run-id-${idx}`}>
                      {item?.run_id || '—'}
                    </Text>
                    <Text style={{ color: itemStatusColor, fontSize: 10, fontWeight: '800' }} data-testid={`assigned-host-history-item-status-${idx}`} testID={`assigned-host-history-item-status-${idx}`}>
                      {itemStatus}
                    </Text>
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }} data-testid={`assigned-host-history-item-created-at-${idx}`} testID={`assigned-host-history-item-created-at-${idx}`}>
                    {item?.created_at ? new Date(item.created_at).toLocaleString() : '-'} • fail streak {item?.fail_streak || 0}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }} data-testid={`assigned-host-history-item-reasons-${idx}`} testID={`assigned-host-history-item-reasons-${idx}`}>
                    reasons: {failReasons || 'none'}
                  </Text>
                  <Text style={{ color: fallbackApplied ? colors.successText : colors.textMuted, fontSize: 10, marginTop: 2 }} data-testid={`assigned-host-history-item-fallback-${idx}`} testID={`assigned-host-history-item-fallback-${idx}`}>
                    safe fallback: {fallbackApplied ? 'applied' : 'not applied'}
                  </Text>
                </View>
              );
            })}
            {(!history || history.length === 0) && (
              <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="assigned-host-history-empty" testID="assigned-host-history-empty">
                No assigned-host runs yet.
              </Text>
            )}
          </View>
        )}
      </View>

      {!!message && (
        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: `${statusColor}66`, backgroundColor: `${statusColor}16`, padding: 10 }} data-testid="assigned-host-message-banner" testID="assigned-host-message-banner">
          <Text style={{ color: statusColor, fontSize: 11, fontWeight: '700' }} data-testid="assigned-host-message-text" testID="assigned-host-message-text">
            {message}
          </Text>
        </View>
      )}
    </ScrollView>
  );
}

/* i18n-probe t('i18n.auto.probe') */
