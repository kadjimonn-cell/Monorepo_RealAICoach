import React, { useEffect, useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const tx = (_key: string, fallback: string) => fallback;

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

// Module-scope theme-aware palette (CSS-var-backed) — exposes `T` at module
// scope so helper sub-components declared outside the default-exported
// component (sevColor, statusColor, KPI, etc.) resolve `T.*` references
// correctly in both light and dark modes.
const T = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  purpleText: 'var(--app-primary)',
  success: 'var(--app-success)', successText: 'var(--app-success)', successSoft: 'var(--app-success-soft)',
  warning: 'var(--app-warning)', warningText: 'var(--app-warning)', warningSoft: 'var(--app-warning-soft)',
  error: 'var(--app-error)', errorText: 'var(--app-error)', errorSoft: 'var(--app-error-soft)',
  purple: 'var(--app-primary)', cyan: 'var(--app-primary)' as any,
};

type Tab = 'monitoring' | 'incidents' | 'config';

export default function AutoDetectPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<Tab>('monitoring');
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<any>(null);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [config, setConfig] = useState<any>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [sRes, iRes, cRes] = await Promise.all([
        api.get('/admin/auto-detect/status'),
        api.get('/admin/auto-detect/incidents?limit=20'),
        api.get('/admin/auto-detect/config'),
      ]);
      setStatus(sRes.data);
      setIncidents(iRes.data.incidents || []);
      setConfig(cRes.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/auto-detect/hybrid-refresh',
    onTick: fetchAll,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const updateConfig = async (updates: any) => {
    try {
      const res = await api.post('/admin/auto-detect/config', updates);
      setConfig(res.data);
    } catch (e) { console.error(e); }
  };

  const acknowledgeIncident = async (incidentId: string) => {
    try {
      await api.post('/admin/auto-detect/acknowledge', { incident_id: incidentId });
      fetchAll();
    } catch (e) { console.error(e); }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }} data-testid="auto-detect-loading" testID="auto-detect-loading">
      <AutoFixBanner domain="threat_detection" />
      <ActivityIndicator size="large" color={T.error} />
      <Text style={{ color: T.textSec, marginTop: 12 }}>{tx('admin.autoDetectPanel.auto.text.001', 'Loading monitoring...')}</Text>
    </View>
  );

  const live = status?.live_metrics;
  const thresholds = status?.thresholds || {};
  const activeIncidents = incidents.filter(i => i.status !== 'resolved');

  const TABS: { id: Tab; label: string; icon: string; badge?: number }[] = [
    { id: 'monitoring', label: 'Live Metrics', icon: 'pulse' },
    { id: 'incidents', label: 'Incidents', icon: 'warning', badge: activeIncidents.length },
    { id: 'config', label: 'Configuration', icon: 'settings' },
  ];

  return (
    <ScrollView style={{ flex: 1 }} data-testid="auto-detect-panel" testID="auto-detect-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: status?.monitoring_enabled ? 'var(--app-primary)' : 'var(--app-primary)', alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="shield-checkmark" size={22} color={status?.monitoring_enabled ? T.success : T.error} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }}>{tx('admin.autoDetectPanel.auto.text.002', 'AI Incident Auto-Detection')}</Text>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.autoDetectPanel.auto.text.003', 'Real-Time Monitoring + Auto-Remediation')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: status?.monitoring_enabled ? T.success : T.error }} />
          <Text style={{ color: status?.monitoring_enabled ? T.success : T.error, fontSize: 12, fontWeight: '600' }}>
            {status?.monitoring_enabled ? 'ACTIVE' : 'PAUSED'}
          </Text>
        </View>
      </View>

      {/* Quick Stats */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <MetricGauge label="CPU" value={live?.cpu_percent || 0} threshold={thresholds.cpu_percent || 90} unit="%" />
        <MetricGauge label="Memory" value={live?.memory_percent || 0} threshold={thresholds.memory_percent || 85} unit="%" />
        <MetricGauge label="Disk" value={live?.disk_percent || 0} threshold={thresholds.disk_percent || 90} unit="%" />
        <MetricGauge label="API Latency" value={live?.api_latency_ms || 0} threshold={thresholds.api_latency_ms || 5000} unit="ms" />
      </View>

      {/* Active Incidents Banner */}
      {activeIncidents.length > 0 && (
        <View data-testid="active-incidents-banner" testID="active-incidents-banner" style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '18'), borderRadius: 10, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '55') }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="alert-circle" size={20} color={T.error} />
            <Text style={{ color: T.error, fontWeight: '700', fontSize: 14 }}>{activeIncidents.length} Active Incident{activeIncidents.length > 1 ? 's' : ''}</Text>
          </View>
        </View>
      )}

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {TABS.map(t => (
          <TouchableOpacity key={t.id} data-testid={`auto-detect-tab-${t.id}`} testID={`auto-detect-tab-${t.id}`} onPress={() => setTab(t.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              backgroundColor: tab === t.id ? (globalThis as any).__alphaColor(T.error, '20') : T.card, borderWidth: 1, borderColor: tab === t.id ? (globalThis as any).__alphaColor(T.error, '40') : T.border }}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? T.error : T.textMuted} />
            <Text style={{ color: tab === t.id ? T.error : T.textSec, fontSize: 12, fontWeight: '600' }}>{t.label}</Text>
            {t.badge ? <View style={{ backgroundColor: T.error, borderRadius: 10, paddingHorizontal: 6, paddingVertical: 1 }}>
              <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{t.badge}</Text>
            </View> : null}
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'monitoring' && <MonitoringTab status={status} />}
      {tab === 'incidents' && <IncidentsTab incidents={incidents} onAcknowledge={acknowledgeIncident} />}
      {tab === 'config' && config && <ConfigTab config={config} onUpdate={updateConfig} />}
    </ScrollView>
  );
}

function MetricGauge({ label, value, threshold, unit }: { label: string; value: number; threshold: number; unit: string }) {
  const pct = Math.min((value / threshold) * 100, 100);
  const color = pct >= 100 ? T.error : pct >= 80 ? T.warning : T.success;
  return (
    <View style={{ flex: 1, minWidth: 130, backgroundColor: T.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: T.border }}>
      <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 4 }}>{label}</Text>
      <Text style={{ color, fontSize: 22, fontWeight: '800' }}>{value}{unit}</Text>
      <View style={{ height: 4, backgroundColor: T.bg, borderRadius: 2, marginTop: 6 }}>
        <View style={{ height: 4, backgroundColor: color, borderRadius: 2, width: `${Math.min(pct, 100)}%` } as any} />
      </View>
      <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>Threshold: {threshold}{unit}</Text>
    </View>
  );
}

function MonitoringTab({ status }: { status: any }) {
  const metrics = status?.recent_metrics || [];
  return (
    <View data-testid="monitoring-tab" testID="monitoring-tab">
      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: T.border }}>
        <Text style={{ color: T.text, fontWeight: '600', fontSize: 13, marginBottom: 8 }}>{tx('admin.autoDetectPanel.auto.text.004', 'Incident Statistics')}</Text>
        <View style={{ flexDirection: 'row', gap: 16 }}>
          <StatItem label="Total" value={status?.incidents?.total || 0} color={T.primary} />
          <StatItem label="Active" value={status?.incidents?.active || 0} color={T.error} />
          <StatItem label="Resolved" value={status?.incidents?.resolved || 0} color={T.successText} />
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
        <Text style={{ color: T.text, fontWeight: '600', fontSize: 13, marginBottom: 8 }}>{tx('admin.autoDetectPanel.auto.text.005', 'Recent Metric Snapshots')}</Text>
        {metrics.length === 0 ? (
          <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.autoDetectPanel.auto.text.006', 'Collecting data... snapshots appear every 60s')}</Text>
        ) : metrics.slice(0, 5).map((m: any, i: number) => (
          <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4, borderBottomWidth: i < 4 ? 1 : 0, borderColor: T.border }}>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>{new Date(m.timestamp).toLocaleTimeString()}</Text>
            <Text style={{ color: T.textSec, fontSize: 11 }}>CPU {m.cpu_percent}% | Mem {m.memory_percent}% | API {m.api_latency_ms}ms</Text>
            {m.breaches_count > 0 && <Ionicons name="alert-circle" size={12} color={T.error} />}
          </View>
        ))}
      </View>
    </View>
  );
}

function IncidentsTab({ incidents, onAcknowledge }: { incidents: any[]; onAcknowledge: (id: string) => void }) {
  if (!incidents.length) return (
    <View style={{ padding: 30, alignItems: 'center' }} data-testid="incidents-empty" testID="incidents-empty">
      <Ionicons name="checkmark-circle" size={48} color={T.successText} />
      <Text style={{ color: T.successText, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.autoDetectPanel.auto.text.007', 'No Incidents Detected')}</Text>
      <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.autoDetectPanel.auto.text.008', 'All systems within thresholds')}</Text>
    </View>
  );

  return (
    <View data-testid="incidents-tab" testID="incidents-tab" style={{ gap: 10 }}>
      {incidents.map((inc: any, i: number) => (
        <View key={i} style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: inc.status === 'resolved' ? T.border : 'var(--app-error)' }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name={inc.status === 'resolved' ? 'checkmark-circle' : 'alert-circle'} size={16} color={inc.status === 'resolved' ? T.success : T.error} />
              <Text style={{ color: sevColor(inc.breach?.severity), fontSize: 11, fontWeight: '700' }}>{inc.breach?.severity?.toUpperCase()}</Text>
            </View>
            <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6,
              backgroundColor: (globalThis as any).__alphaColor(statusColor(inc.status), '20') }}>
              <Text style={{ color: statusColor(inc.status), fontSize: 10, fontWeight: '600' }}>{inc.status}</Text>
            </View>
          </View>
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{inc.breach?.message}</Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>
            {inc.breach?.metric}: {inc.breach?.value} (limit: {inc.breach?.threshold}) | {inc.detected_at ? new Date(inc.detected_at).toLocaleString() : ''}
          </Text>
          {inc.remediation_id && (
            <Text style={{ color: T.cyan, fontSize: 11, marginTop: 4 }}>Remediation: {inc.remediation_id}</Text>
          )}
          {inc.status !== 'resolved' && (
            <TouchableOpacity data-testid={`acknowledge-${inc.incident_id}`} testID={`acknowledge-${inc.incident_id}`} onPress={() => onAcknowledge(inc.incident_id)}
              style={{ marginTop: 8, backgroundColor: (globalThis as any).__alphaColor(T.success, '20'), borderRadius: 6, paddingVertical: 6, alignItems: 'center' }}>
              <Text style={{ color: T.successText, fontSize: 12, fontWeight: '600' }}>{tx('admin.autoDetectPanel.auto.text.009', 'Acknowledge & Resolve')}</Text>
            </TouchableOpacity>
          )}
        </View>
      ))}
    </View>
  );
}

function ConfigTab({ config, onUpdate }: { config: any; onUpdate: (u: any) => void }) {
  return (
    <View data-testid="config-tab" testID="config-tab" style={{ gap: 12 }}>
      {/* Toggles */}
      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
        <Text style={{ color: T.text, fontWeight: '600', fontSize: 14, marginBottom: 12 }}>{tx('admin.autoDetectPanel.auto.text.010', 'Monitoring Controls')}</Text>
        <ToggleRow label="Monitoring Enabled" value={config.enabled} onToggle={(v: boolean) => onUpdate({ enabled: v })} testId="toggle-monitoring" />
        <ToggleRow label="Auto-Remediate on Breach" value={config.auto_remediate} onToggle={(v: boolean) => onUpdate({ auto_remediate: v })} testId="toggle-auto-remediate" />
        <ToggleRow label="Email Notifications" value={config.notify_email} onToggle={(v: boolean) => onUpdate({ notify_email: v })} testId="toggle-email-notify" />
      </View>

      {/* Thresholds */}
      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
        <Text style={{ color: T.text, fontWeight: '600', fontSize: 14, marginBottom: 12 }}>{tx('admin.autoDetectPanel.auto.text.011', 'Alert Thresholds')}</Text>
        <ThresholdRow label="CPU Usage %" value={config.thresholds?.cpu_percent} />
        <ThresholdRow label="Memory Usage %" value={config.thresholds?.memory_percent} />
        <ThresholdRow label="Disk Usage %" value={config.thresholds?.disk_percent} />
        <ThresholdRow label="API Latency (ms)" value={config.thresholds?.api_latency_ms} />
        <ThresholdRow label="Cooldown (min)" value={config.cooldown_minutes} />
      </View>

      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="time" size={16} color={T.cyan} />
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{tx('admin.autoDetectPanel.auto.text.012', 'Scheduler Info')}</Text>
        </View>
        <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 6 }}>{tx('admin.autoDetectPanel.auto.text.013', 'Detection cycle runs every 60 seconds. When a threshold breach is detected, an incident is created and AI remediation is auto-triggered (if enabled). Cooldown prevents duplicate incidents for the same metric.')}</Text>
      </View>
    </View>
  );
}

function ToggleRow({ label, value, onToggle, testId }: { label: string; value: boolean; onToggle: (v: boolean) => void; testId: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6 }}>
      <Text style={{ color: T.textSec, fontSize: 13 }}>{label}</Text>
      <Switch data-testid={testId} testID={testId} value={value} onValueChange={onToggle} trackColor={{ false: T.textMuted, true: T.success + '60' }} thumbColor={value ? T.success : T.textMuted} />
    </View>
  );
}

function ThresholdRow({ label, value }: { label: string; value: any }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }}>
      <Text style={{ color: T.textMuted, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600' }}>{value}</Text>
    </View>
  );
}

function StatItem({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={{ alignItems: 'center' }}>
      <Text style={{ color, fontSize: 20, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: T.textMuted, fontSize: 10 }}>{label}</Text>
    </View>
  );
}

function sevColor(s: string) { return s === 'critical' ? T.error : s === 'high' ? T.warning : s === 'medium' ? T.primary : T.textMuted; }
function statusColor(s: string) { return s === 'resolved' ? T.success : s === 'remediating' ? T.cyan : s === 'detected' ? T.error : T.warning; }
