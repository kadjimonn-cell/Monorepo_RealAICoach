import React, { useCallback, useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { ActivityIndicator, ScrollView, Switch, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

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
}; }

// Module-scope fallback for statusColor helper (can't access component-scoped T)
const T = {
  bg: 'var(--app-bg)',
  card: 'var(--app-card-bg)',
  border: 'rgba(148,163,184,0.18)',
  text: 'var(--app-text)',
  textMuted: 'var(--app-text-muted)',
  primary: 'var(--app-primary)',
  success: 'var(--app-success)',
  warning: 'var(--app-warning)',
  error: 'var(--app-error)',
  purple: 'var(--app-primary)',
};

type Tab = 'overview' | 'runs' | 'incidents' | 'settings';

const statusColor = (status?: string) => {
  if (status === 'healthy') return T.success;
  if (status === 'healed' || status === 'degraded') return T.warning;
  if (status === 'failing') return T.error;
  return T.textMuted;
};

export default function CriticalJourneyMonitorPanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<Tab>('overview');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [incidents, setIncidents] = useState<any[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, runsRes, incidentsRes] = await Promise.all([
        api.get('/admin/critical-journeys/status'),
        api.get('/admin/critical-journeys/runs?limit=12'),
        api.get('/admin/critical-journeys/incidents?limit=12'),
      ]);
      setStatus(statusRes.data);
      setRuns(runsRes.data?.runs || []);
      setIncidents(incidentsRes.data?.incidents || []);
    } catch (error) {
      console.error('Critical journey monitor load error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/critical-journey-monitor/hybrid-refresh',
    onTick: load,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const updateConfig = async (updates: any) => {
    setBusy(true);
    try {
      await api.post('/admin/critical-journeys/config', updates);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const runNow = async () => {
    setBusy(true);
    try {
      await api.post('/admin/critical-journeys/run-now', {});
      await load();
    } finally {
      setBusy(false);
    }
  };

  const resolveIncident = async (incidentId: string) => {
    setBusy(true);
    try {
      await api.post('/admin/critical-journeys/incidents/resolve', { incident_id: incidentId });
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <View style={{ padding: 40, alignItems: 'center' }} data-testid="critical-journey-monitor-loading" testID="critical-journey-monitor-loading">
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: T.textMuted, marginTop: 12 }}>{tx('admin.criticalJourneyMonitor.states.loading', 'Loading critical journey monitor...')}</Text>
      </View>
    );
  }

  const latestRun = status?.latest_run || {};
  const currentState = status?.current_state || {};
  const config = status?.config || {};
  const counts = status?.counts || {};
  const openIncidents = status?.open_incidents || [];
  const journeys = latestRun?.journeys || [];
  const tabs: { id: Tab; label: string; icon: string; badge?: number }[] = [
    { id: 'overview', label: 'Overview', icon: 'pulse' },
    { id: 'runs', label: 'Runs', icon: 'time' },
    { id: 'incidents', label: 'Incidents', icon: 'warning', badge: counts.open_incidents || 0 },
    { id: 'settings', label: 'Settings', icon: 'settings' },
  ];

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 18, paddingBottom: 36 }} data-testid="critical-journey-monitor-panel" testID="critical-journey-monitor-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: colors?.text || T.text, fontSize: 24, fontWeight: '800' }} data-testid="critical-journey-monitor-title" testID="critical-journey-monitor-title">{tx('admin.criticalJourneyMonitor.header.title', 'Critical Journey Monitor')}</Text>
          <Text style={{ color: colors?.textMuted || T.textMuted, fontSize: 13, marginTop: 6 }} data-testid="critical-journey-monitor-subtitle" testID="critical-journey-monitor-subtitle">
            {tx('admin.criticalJourneyMonitor.header.subtitle', 'Always-on validation for login, dashboard, executive dashboard, and export reliability with safe auto-heal and incident creation.')}
          </Text>
        </View>
        <TouchableOpacity
          onPress={() => void runNow()}
          disabled={busy}
          style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: T.primary }}
          data-testid="critical-journey-run-now-button" testID="critical-journey-run-now-button"
        >
          <Text style={{ color: colors?.text || T.text, fontSize: 12, fontWeight: '800' }}>{busy ? 'Running…' : 'Run Now'}</Text>
        </TouchableOpacity>
      </View>

      <View style={{ backgroundColor: `${statusColor(currentState.status)}18`, borderRadius: 14, borderWidth: 1, borderColor: `${statusColor(currentState.status)}55`, padding: 16 }} data-testid="critical-journey-state-banner" testID="critical-journey-state-banner">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="shield-checkmark" size={18} color={statusColor(currentState.status)} />
          <Text style={{ color: statusColor(currentState.status), fontSize: 14, fontWeight: '800' }} data-testid="critical-journey-state-label" testID="critical-journey-state-label">
            {String(currentState.status || 'unknown').toUpperCase()}
          </Text>
        </View>
        <Text style={{ color: colors?.textMuted || T.textMuted, fontSize: 12, marginTop: 8 }} data-testid="critical-journey-state-detail" testID="critical-journey-state-detail">
          Last run: {latestRun?.started_at ? new Date(latestRun.started_at).toLocaleString() : 'Never'} · Failed journeys: {(currentState.failed_journeys || []).join(', ') || 'none'}
        </Text>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        {[
          { label: 'Total Runs', value: counts.total_runs || 0, color: T.primary, testId: 'critical-journey-total-runs' },
          { label: 'Open Incidents', value: counts.open_incidents || 0, color: counts.open_incidents ? T.error : T.success, testId: 'critical-journey-open-incidents' },
          { label: 'Resolved Incidents', value: counts.resolved_incidents || 0, color: T.successText, testId: 'critical-journey-resolved-incidents' },
          { label: 'Auto-Heal', value: config.auto_heal_enabled ? 'On' : 'Off', color: config.auto_heal_enabled ? T.purple : T.textMuted, testId: 'critical-journey-auto-heal' },
        ].map((card) => (
          <View key={card.testId} style={{ flex: 1, minWidth: 150, backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 16 }} data-testid={card.testId} testID={card.testId}>
            <Text style={{ color: T.textMuted, fontSize: 11, textTransform: 'uppercase', fontWeight: '700' }}>{card.label}</Text>
            <Text style={{ color: card.color, fontSize: 24, fontWeight: '800', marginTop: 8 }}>{String(card.value)}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {tabs.map((item) => (
          <TouchableOpacity
            key={item.id}
            onPress={() => setTab(item.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, backgroundColor: tab === item.id ? `${T.primary}22` : T.card, borderWidth: 1, borderColor: tab === item.id ? `${T.primary}55` : T.border }}
            data-testid={`critical-journey-tab-${item.id}`} testID={`critical-journey-tab-${item.id}`}
          >
            <Ionicons name={item.icon as any} size={14} color={tab === item.id ? T.primary : T.textMuted} />
            <Text style={{ color: tab === item.id ? T.primary : T.textMuted, fontSize: 12, fontWeight: '700' }}>{item.label}</Text>
            {item.badge ? <View style={{ backgroundColor: T.error, borderRadius: 999, paddingHorizontal: 6, paddingVertical: 1 }}><Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{item.badge}</Text></View> : null}
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'overview' && (
        <View style={{ gap: 14 }} data-testid="critical-journey-overview-tab" testID="critical-journey-overview-tab">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {journeys.map((journey: any) => (
              <View key={journey.journey_id} style={{ flex: 1, minWidth: 220, backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: `${statusColor(journey.status)}55`, padding: 16 }} data-testid={`critical-journey-card-${journey.journey_id}`} testID={`critical-journey-card-${journey.journey_id}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{journey.label}</Text>
                  <Text style={{ color: statusColor(journey.status), fontSize: 11, fontWeight: '800' }}>{String(journey.status).toUpperCase()}</Text>
                </View>
                <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 8 }}>Latency: {journey.latency_ms}ms</Text>
                <Text style={{ color: journey.failed_steps?.length ? T.error : T.success, fontSize: 12, marginTop: 6 }} data-testid={`critical-journey-failed-steps-${journey.journey_id}`} testID={`critical-journey-failed-steps-${journey.journey_id}`}>
                  Failed steps: {journey.failed_steps?.join(', ') || 'none'}
                </Text>
              </View>
            ))}
          </View>

          <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 16 }} data-testid="critical-journey-auto-heal-summary" testID="critical-journey-auto-heal-summary">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.criticalJourneyMonitor.overview.autoHealSummary', 'Auto-Heal Summary')}</Text>
            {(latestRun?.auto_heal_actions || []).length === 0 ? (
              <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.criticalJourneyMonitor.overview.autoHealEmpty', 'No auto-heal actions were needed on the latest run.')}</Text>
            ) : (latestRun.auto_heal_actions || []).map((action: any, index: number) => (
              <View key={`${action.action}-${index}`} style={{ paddingVertical: 8, borderBottomWidth: index < latestRun.auto_heal_actions.length - 1 ? 1 : 0, borderBottomColor: T.border }} data-testid={`critical-journey-auto-heal-action-${index}`} testID={`critical-journey-auto-heal-action-${index}`}>
                <Text style={{ color: action.status === 'applied' ? T.success : T.warning, fontSize: 12, fontWeight: '800' }}>{action.action}</Text>
                <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{action.message}</Text>
              </View>
            ))}
          </View>

          <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 16 }} data-testid="critical-journey-open-incidents-list" testID="critical-journey-open-incidents-list">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.criticalJourneyMonitor.overview.openIncidents', 'Open Incidents')}</Text>
            {openIncidents.length === 0 ? (
              <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.criticalJourneyMonitor.overview.openIncidentsEmpty', 'No active incidents. The monitor is quiet.')}</Text>
            ) : openIncidents.map((incident: any) => (
              <View key={incident.incident_id} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border }} data-testid={`critical-journey-open-incident-${incident.incident_id}`} testID={`critical-journey-open-incident-${incident.incident_id}`}>
                <Text style={{ color: T.error, fontSize: 12, fontWeight: '800' }}>{incident.title}</Text>
                <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{incident.message}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {tab === 'runs' && (
        <View style={{ gap: 12 }} data-testid="critical-journey-runs-tab" testID="critical-journey-runs-tab">
          {runs.map((run: any) => (
            <View key={run.run_id} style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 16 }} data-testid={`critical-journey-run-${run.run_id}`} testID={`critical-journey-run-${run.run_id}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>{run.triggered_by}</Text>
                <Text style={{ color: statusColor(run.summary?.final_status), fontSize: 11, fontWeight: '800' }}>{String(run.summary?.final_status || 'unknown').toUpperCase()}</Text>
              </View>
              <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 6 }}>{run.started_at ? new Date(run.started_at).toLocaleString() : 'Unknown time'} · {run.duration_ms}ms</Text>
              <Text style={{ color: (run.summary?.failed_journeys || []).length ? T.error : T.success, fontSize: 12, marginTop: 6 }}>
                Failed journeys: {(run.summary?.failed_journeys || []).join(', ') || 'none'}
              </Text>
            </View>
          ))}
        </View>
      )}

      {tab === 'incidents' && (
        <View style={{ gap: 12 }} data-testid="critical-journey-incidents-tab" testID="critical-journey-incidents-tab">
          {incidents.length === 0 ? (
            <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 24, alignItems: 'center' }} data-testid="critical-journey-incidents-empty" testID="critical-journey-incidents-empty">
              <Ionicons name="checkmark-circle" size={28} color={T.successText} />
              <Text style={{ color: T.successText, fontSize: 14, fontWeight: '800', marginTop: 10 }}>{tx('admin.criticalJourneyMonitor.incidents.empty', 'No incidents')}</Text>
            </View>
          ) : incidents.map((incident: any) => (
            <View key={incident.incident_id} style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: incident.status === 'resolved' ? T.border : `${T.error}55`, padding: 16 }} data-testid={`critical-journey-incident-${incident.incident_id}`} testID={`critical-journey-incident-${incident.incident_id}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>{incident.title}</Text>
                <Text style={{ color: incident.status === 'resolved' ? T.success : T.error, fontSize: 11, fontWeight: '800' }}>{String(incident.status).toUpperCase()}</Text>
              </View>
              <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 6 }}>{incident.message}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>Journeys: {(incident.failed_journeys || []).join(', ') || 'none'}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Detected: {incident.detected_at ? new Date(incident.detected_at).toLocaleString() : 'Unknown'}</Text>
              {incident.status !== 'resolved' && (
                <TouchableOpacity
                  onPress={() => void resolveIncident(incident.incident_id)}
                  disabled={busy}
                  style={{ marginTop: 10, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: `${T.success}22`, borderWidth: 1, borderColor: `${T.success}55` }}
                  data-testid={`critical-journey-resolve-${incident.incident_id}`} testID={`critical-journey-resolve-${incident.incident_id}`}
                >
                  <Text style={{ color: T.successText, fontSize: 12, fontWeight: '800' }}>{busy ? 'Working…' : 'Resolve Incident'}</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
        </View>
      )}

      {tab === 'settings' && (
        <View style={{ gap: 12 }} data-testid="critical-journey-settings-tab" testID="critical-journey-settings-tab">
          <SettingsToggle label="Monitor Enabled" description="Keep the always-on journey checker running every 5 minutes." value={Boolean(config.enabled)} testId="critical-journey-toggle-enabled" onToggle={(value) => void updateConfig({ enabled: value })} />
          <SettingsToggle label="Safe Auto-Heal" description="Run app-controlled recovery actions when shell or auth drift is detected." value={Boolean(config.auto_heal_enabled)} testId="critical-journey-toggle-auto-heal" onToggle={(value) => void updateConfig({ auto_heal_enabled: value })} />
          <SettingsToggle label="Admin Notifications" description="Raise in-app realtime incidents for new regressions." value={Boolean(config.notify_admins)} testId="critical-journey-toggle-notify" onToggle={(value) => void updateConfig({ notify_admins: value })} />
          <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 16 }} data-testid="critical-journey-settings-meta" testID="critical-journey-settings-meta">
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>{tx('admin.criticalJourneyMonitor.settings.cooldownCadence', 'Cooldown & cadence')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 8 }}>Incident cooldown: {config.incident_cooldown_minutes || 20} minutes</Text>
            <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>Scheduler cadence: {config.check_interval_minutes || 5} minutes</Text>
          </View>
        </View>
      )}
    </ScrollView>
  );
}

function SettingsToggle({ label, description, value, onToggle, testId }: { label: string; description: string; value: boolean; onToggle: (value: boolean) => void; testId: string }) {
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, padding: 16 }} data-testid={`${testId}-card`} testID={`${testId}-card`}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>{label}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 6 }}>{description}</Text>
        </View>
        <Switch value={value} onValueChange={onToggle} data-testid={testId} testID={testId} />
      </View>
    </View>
  );
}