import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import AutoFixBanner from './AutoFixBanner';
import { resolveRuntimeBaseUrl } from '../../utils/runtimeBaseUrl';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { clientLogger } from '../../utils/clientLogger';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';

let T = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  success: 'var(--app-success)' as any,
  warning: 'var(--app-warning)' as any,
  error: 'var(--app-error)' as any,
  purple: 'var(--app-primary)' as any,
  purpleText: 'var(--app-primary)' as any,
  cyan: 'var(--app-info)' as any,
  teal: 'var(--app-primary)' as any,
  successSoft: 'var(--app-success-soft)' as any,
  warningSoft: 'var(--app-warning-soft)' as any,
  errorSoft: 'var(--app-error-soft)' as any,
  primarySoft: 'var(--app-primary-soft)' as any,
  infoSoft: 'var(--app-info-soft)' as any,
};

function urlBase64ToUint8Array(base64String: string) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) outputArray[i] = rawData.charCodeAt(i);
  return outputArray;
}

interface DashboardData {
  automation_score: number;
  system_metrics: { cpu_percent: number; memory_percent: number; memory_used_gb: number; memory_total_gb: number; disk_percent: number; disk_used_gb: number; disk_total_gb: number };
  incident_stats: { total: number; open: number; resolved_24h: number; auto_healed: number; mttr_minutes: number };
  rules: { active: number; total: number };
  actions_24h: number;
  heartbeats: { service: string; status: string; uptime: string; last_check: string; response_time_ms: number }[];
  recent_incidents: any[];
  uptime_timeline: { hour: string; uptime: number; incidents: number }[];
}

export default function AutomationEnginePanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  T = {
    ...T,
    bg: AC.bg,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    textSec: AC.textSec,
    textMuted: AC.textMuted,
    primary: AC.primary,
    success: AC.success,
    warning: AC.warning,
    error: AC.error,
  };
  const statusColors: Record<string, string> = { healthy: T.success, degraded: T.warning, down: T.error };
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [rules, setRules] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [sendingTest, setSendingTest] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [bulkAutofixLoading, setBulkAutofixLoading] = useState(false);
  const [bulkAutofixResult, setBulkAutofixResult] = useState<string | null>(null);
  const [showCreateRule, setShowCreateRule] = useState(false);
  const [newRule, setNewRule] = useState({ name: '', metric: 'cpu_percent', condition: 'gt', threshold: 90, action: 'alert', autofix_enabled: false, cooldown_minutes: 15, schedule_type: 'always', schedule_cron: '', schedule_window_start: '09:00', schedule_window_end: '17:00', schedule_timezone: 'UTC' });
  const [saving, setSaving] = useState(false);
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
  const [wsError, setWsError] = useState('');

  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushLoading, setPushLoading] = useState(false);
  const panelTitle = t('automationEngine.header.title');

  // Check push notification support on mount
  useEffect(() => {
    if (typeof window !== 'undefined' && 'Notification' in window && 'serviceWorker' in navigator) {
      if (Notification.permission === 'granted') {
        navigator.serviceWorker.ready.then(reg => {
          reg.pushManager.getSubscription().then(sub => {
            if (sub) setPushEnabled(true);
          });
        });
      }
    }
  }, []);

  const togglePushNotifications = async () => {
    setPushLoading(true);
    try {
      if (pushEnabled) {
        // Unsubscribe
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (sub) {
          const endpoint = sub.endpoint;
          await sub.unsubscribe();
          await api.post('/push/unsubscribe', { endpoint });
        }
        setPushEnabled(false);
      } else {
        // Subscribe
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
          setPushLoading(false);
          return;
        }
        const vapidRes = await api.get('/push/vapid-public-key');
        const vapidKey = vapidRes.data.public_key;
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidKey),
        });
        const subJson = sub.toJSON();
        await api.post('/push/subscribe', {
          endpoint: subJson.endpoint,
          keys: subJson.keys,
          user_agent: navigator.userAgent,
        });
        setPushEnabled(true);
      }
    } catch (e) {
      console.error('Push notification toggle error:', e);
    } finally {
      setPushLoading(false);
    }
  };

  const load = async () => {
    try {
      const [dashRes, rulesRes] = await Promise.all([
        api.get('/admin/automation/dashboard'),
        api.get('/admin/automation/rules'),
      ]);
      setData(dashRes.data);
      setRules(rulesRes.data.rules || []);
      setLoading(false);

      api.get('/admin/automation/alert-history?limit=20')
        .then((alertsRes) => setAlerts(alertsRes.data.alerts || []))
        .catch((e) => console.error('Automation alert history load error:', e));
    } catch (e) {
      console.error('Automation engine load error:', e);
      setLoading(false);
    }
  };

  const automationWsEnabled = Platform.OS === 'web';

  const buildAutomationWsUrl = useCallback(async () => {
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'automation_dashboard' });
    const wsTicket = String(ticketResp?.data?.ticket || '').trim();
    if (!wsTicket) {
      throw new Error('Missing websocket ticket for automation dashboard');
    }

    const backendUrl = resolveRuntimeBaseUrl();
    const wsProtocol = backendUrl.startsWith('https') ? 'wss' : 'ws';
    const wsHost = backendUrl.replace(/^https?:\/\//, '');
    return `${wsProtocol}://${wsHost}/api/ws/automation-dashboard?ticket=${encodeURIComponent(wsTicket)}`;
  }, []);

  const { lastError: automationWsLastError } = useManagedWebSocket({
    enabled: automationWsEnabled,
    buildUrl: buildAutomationWsUrl,
    errorScope: 'admin/automation-engine/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1200,
    onOpen: () => {
      setWsStatus('connected');
      setWsError('');
      clientLogger.log('[Automation WS] Connected');
    },
    onClose: () => {
      setWsStatus('disconnected');
    },
    onError: () => {
      setWsStatus('disconnected');
      setWsError('Automation live stream interrupted. Reconnecting...');
    },
    onReconnectAttempt: () => {
      setWsStatus('connecting');
      setWsError('Automation live stream reconnecting...');
    },
    onMessage: (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'automation:update') {
          setData(prev => prev ? {
            ...prev,
            system_metrics: msg.system_metrics,
            heartbeats: msg.heartbeats,
            incident_stats: msg.incident_stats,
            automation_score: msg.automation_score,
            rules: msg.rules,
          } : prev);
        } else if (msg.type === 'automation:incident') {
          load();
        }
        setWsError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/automation-engine/ws-parse',
          fallbackMessage: 'A live automation update could not be processed.',
          setMessage: setWsError,
        });
      }
    },
  });

  // Initial HTTP load
  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!automationWsEnabled) {
      setWsStatus('disconnected');
      setWsError('');
    }
  }, [automationWsEnabled]);

  useEffect(() => {
    if (!automationWsLastError) return;
    setWsStatus('disconnected');
    setWsError(automationWsLastError);
  }, [automationWsLastError]);

  const toggleAutofix = async (ruleId: string, current: boolean) => {
    try {
      await api.post('/admin/automation/toggle-autofix', { rule_id: ruleId, autofix_enabled: !current });
      setRules(prev => prev.map(r => r.rule_id === ruleId ? { ...r, autofix_enabled: !current } : r));
    } catch (e) { console.error('Toggle autofix error:', e); }
  };

  const sendTestAlert = async () => {
    setSendingTest(true);
    setTestResult(null);
    try {
      const res = await api.post('/admin/automation/test-alert');
      const recipients = res.data.recipients || [];
      const successCount = recipients.filter((r: any) => r.success).length;
      setTestResult(`Test alert sent to ${successCount} admin(s)`);
      load();
    } catch {
      setTestResult('Failed to send test alert');
    } finally { setSendingTest(false); }
  };

  const saveNewRule = async () => {
    if (!newRule.name.trim()) return;
    setSaving(true);
    try {
      await api.post('/admin/automation/rules', newRule);
      setShowCreateRule(false);
      setNewRule({ name: '', metric: 'cpu_percent', condition: 'gt', threshold: 90, action: 'alert', autofix_enabled: false, cooldown_minutes: 15, schedule_type: 'always', schedule_cron: '', schedule_window_start: '09:00', schedule_window_end: '17:00', schedule_timezone: 'UTC' });
      load();
    } catch (e) { console.error('Save rule error:', e); }
    finally { setSaving(false); }
  };

  const deleteRule = async (ruleId: string) => {
    try {
      await api.post('/admin/automation/rules/delete', { rule_id: ruleId });
      setRules(prev => prev.filter(r => r.rule_id !== ruleId));
    } catch (e) { console.error('Delete rule error:', e); }
  };

  const enableSupportedAutofix = async () => {
    setBulkAutofixLoading(true);
    setBulkAutofixResult(null);
    try {
      const res = await api.post('/admin/automation/autofix/enable-supported');
      const updated = Number(res.data?.updated_count || 0);
      setBulkAutofixResult(updated > 0 ? `Enabled auto-fix on ${updated} supported rule${updated === 1 ? '' : 's'}.` : 'All supported auto-fix rules were already enabled.');
      await load();
    } catch (e) {
      console.error('Enable supported autofix error:', e);
      setBulkAutofixResult('Failed to enable supported auto-fix rules.');
    } finally {
      setBulkAutofixLoading(false);
    }
  };

  const METRIC_OPTIONS = [
    { value: 'cpu_percent', label: 'CPU Usage (%)' },
    { value: 'memory_percent', label: 'Memory Usage (%)' },
    { value: 'disk_percent', label: 'Disk Usage (%)' },
    { value: 'api_response_ms', label: 'API Response Time (ms)' },
    { value: 'db_connected', label: 'DB Connected (0/1)' },
    { value: 'error_rate_5m', label: 'Error Rate (5min)' },
  ];
  const CONDITION_OPTIONS = [
    { value: 'gt', label: '> Greater Than' },
    { value: 'lt', label: '< Less Than' },
    { value: 'eq', label: '= Equals' },
  ];
  const ACTION_OPTIONS = [
    { value: 'alert', label: 'Send Alert' },
    { value: 'restart', label: 'Auto-Restart' },
    { value: 'clear_cache', label: 'Clear Cache' },
    { value: 'scale_up', label: 'Scale Up' },
  ];

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.cyan} /><Text style={{ color: T.textMuted, marginTop: 8, fontSize: 12 }}>{tx('automationEngine.states.loading', 'Loading automation engine...')}</Text></View>;
      // eslint-disable-next-line no-unused-expressions
      <AutoFixBanner domain="automation_engine" />
  if (!data) return <View style={{ padding: 40, alignItems: 'center' }}><Ionicons name="alert-circle" size={32} color={T.error} /><Text style={{ color: T.error, marginTop: 8 }}>{tx('automationEngine.states.loadFailed', 'Failed to load automation data')}</Text></View>;

  if (Platform.OS !== 'web') return (
    <View style={{ padding: 20 }}>
      <Text style={{ color: T.text, fontSize: 16, fontWeight: '700' }}>{panelTitle === 'automationEngine.header.title' ? 'Automation Engine' : panelTitle}</Text>
      <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{tx('automationEngine.header.score', 'Score')}: {data.automation_score}/100</Text>
    </View>
  );

  const { system_metrics: sys, incident_stats: inc } = data;
  const gaugeColor = (v: number) => v > 85 ? T.error : v > 70 ? T.warning : T.success;
  const remediationCapableRules = rules.filter((rule) => ['restart', 'clear_cache'].includes(String(rule.action || '').toLowerCase()));
  const driftedAutofixRules = remediationCapableRules.filter((rule) => !rule.autofix_enabled);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20, paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }} data-testid="automation-engine-header">
        <div>
          <Text style={{ fontSize: 22, fontWeight: '800', color: T.text, letterSpacing: -0.5 }}>{panelTitle === 'automationEngine.header.title' ? 'Automation Engine' : panelTitle}</Text>
          <Text style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{tx('automationEngine.header.subtitle', 'Automated failure detection, healing & incident management')}</Text>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div data-testid="ws-connection-status" style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 20, backgroundColor: wsStatus === 'connected' ? T.successSoft : wsStatus === 'connecting' ? T.warningSoft : T.errorSoft, border: `1px solid ${wsStatus === 'connected' ? T.success : wsStatus === 'connecting' ? T.warning : T.error}` }}>
            <div style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: wsStatus === 'connected' ? T.success : wsStatus === 'connecting' ? T.warning : T.error, boxShadow: wsStatus === 'connected' ? `0 0 6px ${T.success}` : 'none', animation: wsStatus === 'connected' ? 'pulse 2s infinite' : 'none' }} />
            <Text style={{ fontSize: 10, color: wsStatus === 'connected' ? T.success : wsStatus === 'connecting' ? T.warning : T.error, fontWeight: '600' }}>
              {wsStatus === 'connected' ? tx('automationEngine.header.live', 'LIVE') : wsStatus === 'connecting' ? tx('automationEngine.header.connecting', 'CONNECTING...') : tx('automationEngine.header.offline', 'OFFLINE')}
            </Text>
          </div>
        </div>
      </div>
      <style dangerouslySetInnerHTML={{ __html: `@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }` }} />

      {!!wsError && (
        <View data-testid="automation-ws-error" testID="automation-ws-error" style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '30'), borderRadius: 10, padding: 10 }}>
          <Text style={{ fontSize: 11, color: T.error, fontWeight: '600' }}>{wsError}</Text>
        </View>
      )}

      {/* Top Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }} data-testid="automation-stats">
        {[
          { label: 'Automation Score', value: `${data.automation_score}/100`, color: data.automation_score >= 90 ? T.success : data.automation_score >= 70 ? T.warning : T.error, icon: 'flash' },
          { label: 'Active Rules', value: `${data.rules.active}/${data.rules.total}`, color: T.primary, icon: 'git-branch' },
          { label: 'Open Incidents', value: inc.open, color: inc.open > 0 ? T.error : T.success, icon: 'alert-circle' },
          { label: 'Auto-Healed', value: inc.auto_healed, color: T.teal, icon: 'construct' },
          { label: 'MTTR', value: `${inc.mttr_minutes}m`, color: T.cyan, icon: 'timer' },
          { label: 'Actions (24h)', value: data.actions_24h, color: T.purpleText, icon: 'rocket' },
        ].map((s, i) => (
          <div key={i} style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}`, textAlign: 'center' }}>
            <Ionicons name={s.icon as any} size={18} color={s.color} />
            <div style={{ fontSize: 20, fontWeight: '800', color: s.color, marginTop: 6 }}>{s.value}</div>
            <div style={{ fontSize: 9, color: T.textMuted, fontWeight: '600', marginTop: 2, textTransform: 'uppercase' }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* System Resources */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }} data-testid="system-resources">
        {[
          { label: 'CPU', value: sys.cpu_percent, detail: `${sys.cpu_percent}%` },
          { label: 'Memory', value: sys.memory_percent, detail: `${sys.memory_used_gb}/${sys.memory_total_gb} GB` },
          { label: 'Disk', value: sys.disk_percent, detail: `${sys.disk_used_gb}/${sys.disk_total_gb} GB` },
        ].map((r, i) => (
          <div key={i} style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, border: `1px solid ${T.border}` }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{r.label}</span>
              <span style={{ fontSize: 11, color: gaugeColor(r.value), fontWeight: '700' }}>{r.detail}</span>
            </div>
            <div style={{ height: 6, borderRadius: 3, backgroundColor: T.border, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${r.value}%`, borderRadius: 3, backgroundColor: gaugeColor(r.value), transition: 'width 0.5s ease' }} />
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          backgroundColor: driftedAutofixRules.length > 0 ? T.warningSoft : T.successSoft,
          borderRadius: 16,
          padding: 18,
          border: `1px solid ${driftedAutofixRules.length > 0 ? T.warning : T.success}`,
        }}
        data-testid="autofix-drift-health-card"
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <div style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: driftedAutofixRules.length > 0 ? T.warningSoft : T.successSoft, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={driftedAutofixRules.length > 0 ? 'warning' : 'shield-checkmark'} size={16} color={driftedAutofixRules.length > 0 ? T.warning : T.success} />
            </div>
            <div>
              <Text style={{ fontSize: 14, fontWeight: '800', color: T.text }} data-testid="autofix-drift-health-card-title" testID="autofix-drift-health-card-title">{tx('automationEngine.cards.autofixDrift.title', 'Recommended Auto-Fix Drift')}</Text>
              <Text style={{ fontSize: 11, color: driftedAutofixRules.length > 0 ? T.warning : T.success, marginTop: 3 }} data-testid="autofix-drift-health-card-status" testID="autofix-drift-health-card-status">
                {driftedAutofixRules.length > 0
                  ? `${driftedAutofixRules.length} remediation-capable rule${driftedAutofixRules.length === 1 ? '' : 's'} currently have auto-fix turned off.`
                  : 'All remediation-capable rules are aligned with the recommended auto-fix posture.'}
              </Text>
              {driftedAutofixRules.length > 0 && (
                <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 6 }} data-testid="autofix-drift-health-card-rules" testID="autofix-drift-health-card-rules">
                  {driftedAutofixRules.map((rule) => rule.name).join(' • ')}
                </Text>
              )}
            </div>
          </div>

          {driftedAutofixRules.length > 0 && (
            <button
              onClick={enableSupportedAutofix}
              disabled={bulkAutofixLoading}
              style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: T.successSoft, padding: '8px 12px', borderRadius: 10, border: 'none', cursor: 'pointer', opacity: bulkAutofixLoading ? 0.6 : 1 }}
              data-testid="autofix-drift-health-card-enable-button"
            >
              <Ionicons name="construct" size={12} color={T.successText} />
              <span style={{ fontSize: 11, fontWeight: 700, color: T.successText }}>{bulkAutofixLoading ? 'Enabling...' : 'Restore Recommended Auto-Fix'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Service Heartbeats */}
      <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="service-heartbeats">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Ionicons name="pulse" size={16} color={T.successText} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('automationEngine.cards.serviceHeartbeats.title', 'Service Heartbeats')}</Text>
          <Text style={{ fontSize: 10, color: T.successText, fontWeight: '700' }}>
            {data.heartbeats.filter(h => h.status === 'healthy').length}/{data.heartbeats.length} Healthy
          </Text>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
          {data.heartbeats.map((hb, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10, backgroundColor: T.bg, border: `1px solid ${T.border}` }} data-testid={`heartbeat-${i}`}>
              <div style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: statusColors[hb.status] || T.textMuted, boxShadow: `0 0 6px ${statusColors[hb.status] || T.textMuted}40` }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, fontWeight: '600', color: T.text }}>{hb.service}</div>
                <div style={{ fontSize: 9, color: T.textMuted }}>{hb.uptime} uptime | {hb.response_time_ms}ms</div>
              </div>
              <span style={{ fontSize: 9, fontWeight: '700', color: statusColors[hb.status], textTransform: 'uppercase' }}>{hb.status}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Uptime Timeline Chart */}
      <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="uptime-chart">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="analytics" size={16} color={T.primary} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('automationEngine.cards.uptime.title', 'Uptime (48h)')}</Text>
        </div>
        <div style={{ width: '100%', height: 180 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.uptime_timeline} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="uptimeGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={T.success} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={T.success} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
              <XAxis dataKey="hour" tick={{ fill: T.textMuted, fontSize: 8 }} axisLine={false} tickLine={false} interval={5} />
              <YAxis domain={[98, 100.5]} tick={{ fill: T.textMuted, fontSize: 9 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: T.card, border: `1px solid ${T.border}`, borderRadius: 8, fontSize: 11, color: T.text }} formatter={(v: number) => [`${v}%`, 'Uptime']} />
              <Area type="monotone" dataKey="uptime" stroke={T.successText} fill="url(#uptimeGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Two columns: Alert Rules + Recent Incidents */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: 16 }}>
        {/* Alert Rules */}
        <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="alert-rules">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="git-branch" size={16} color={T.warningText} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('automationEngine.cards.alertRules.title', 'Alert Rules')}</Text>
            <Text style={{ fontSize: 10, color: T.textMuted }}>{rules.length} configured</Text>
            <button onClick={enableSupportedAutofix}
              disabled={bulkAutofixLoading}
              style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.successSoft, padding: '5px 10px', borderRadius: 6, border: 'none', cursor: 'pointer', opacity: bulkAutofixLoading ? 0.6 : 1 }}
              data-testid="enable-supported-autofix-btn">
              <Ionicons name="construct" size={12} color={T.successText} />
              <span style={{ fontSize: 10, fontWeight: 700, color: T.successText }}>{bulkAutofixLoading ? 'Enabling...' : 'Enable Supported Auto-Fix'}</span>
            </button>
            <button onClick={() => setShowCreateRule(!showCreateRule)}
              style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.primarySoft, padding: '5px 10px', borderRadius: 6, border: 'none', cursor: 'pointer' }}
              data-testid="create-rule-btn">
              <Ionicons name={showCreateRule ? 'close' : 'add'} size={12} color={T.purpleText} />
              <span style={{ fontSize: 10, fontWeight: 700, color: T.purpleText }}>{showCreateRule ? 'Cancel' : 'Create Rule'}</span>
            </button>
          </div>

          {bulkAutofixResult && (
            <div
              style={{ padding: '8px 12px', borderRadius: 8, marginBottom: 12, backgroundColor: bulkAutofixResult.includes('Failed') ? T.errorSoft : T.successSoft, border: `1px solid ${bulkAutofixResult.includes('Failed') ? T.error : T.success}` }}
              data-testid="enable-supported-autofix-result"
            >
              <Text style={{ fontSize: 11, color: bulkAutofixResult.includes('Failed') ? T.error : T.success, fontWeight: '600' }}>{bulkAutofixResult}</Text>
            </div>
          )}

          {/* Create Rule Form */}
          {showCreateRule && (
            <div style={{ backgroundColor: T.primarySoft, borderRadius: 12, padding: 16, marginBottom: 14, border: `1px solid ${T.primary}` }} data-testid="create-rule-form">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
                <div>
                  <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Rule Name</label>
                  <input data-testid="rule-name-input" value={newRule.name} onChange={e => setNewRule({...newRule, name: e.target.value})} placeholder={tx('automationEngine.form.ruleNamePlaceholder', 'e.g. High API Latency')}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Metric</label>
                  <select data-testid="rule-metric-select" value={newRule.metric} onChange={e => setNewRule({...newRule, metric: e.target.value})}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none' }}>
                    {METRIC_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Condition</label>
                  <select data-testid="rule-condition-select" value={newRule.condition} onChange={e => setNewRule({...newRule, condition: e.target.value})}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none' }}>
                    {CONDITION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Threshold</label>
                  <input data-testid="rule-threshold-input" type="number" value={newRule.threshold} onChange={e => setNewRule({...newRule, threshold: parseFloat(e.target.value) || 0})}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Action</label>
                  <select data-testid="rule-action-select" value={newRule.action} onChange={e => setNewRule({...newRule, action: e.target.value})}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none' }}>
                    {ACTION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Cooldown (min)</label>
                  <input data-testid="rule-cooldown-input" type="number" value={newRule.cooldown_minutes} onChange={e => setNewRule({...newRule, cooldown_minutes: parseInt(e.target.value) || 5})}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Schedule</label>
                  <select data-testid="rule-schedule-select" value={newRule.schedule_type} onChange={e => setNewRule({...newRule, schedule_type: e.target.value})}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none' }}>
                    <option value="always">Always Active</option>
                    <option value="time_window">Time Window</option>
                    <option value="cron">{t("autofix.cron.expression")}</option>
                  </select>
                </div>
              </div>
              {newRule.schedule_type === 'time_window' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginTop: 10 }}>
                  <div>
                    <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Start Time</label>
                    <input data-testid="rule-window-start" type="time" value={newRule.schedule_window_start} onChange={e => setNewRule({...newRule, schedule_window_start: e.target.value})}
                      style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>End Time</label>
                    <input data-testid="rule-window-end" type="time" value={newRule.schedule_window_end} onChange={e => setNewRule({...newRule, schedule_window_end: e.target.value})}
                      style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>Timezone</label>
                    <select data-testid="rule-timezone-select" value={newRule.schedule_timezone} onChange={e => setNewRule({...newRule, schedule_timezone: e.target.value})}
                      style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none' }}>
                      {['UTC', 'US/Eastern', 'US/Central', 'US/Pacific', 'Europe/London', 'Europe/Paris', 'Asia/Tokyo', 'Asia/Shanghai', 'Australia/Sydney'].map(tz => (
                        <option key={tz} value={tz}>{tz}</option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
              {newRule.schedule_type === 'cron' && (
                <div style={{ marginTop: 10 }}>
                  <label style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', display: 'block', marginBottom: 4 }}>{t("autofix.cron.expression")}</label>
                  <input data-testid="rule-cron-input" type="text" value={newRule.schedule_cron} onChange={e => setNewRule({...newRule, schedule_cron: e.target.value})}
                    placeholder={tx('automationEngine.form.cronPlaceholder', 'e.g., 0 9-17 * * 1-5 (Mon-Fri 9AM-5PM)')}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: `1px solid ${T.border}`, backgroundColor: T.bg, color: T.text, fontSize: 12, outline: 'none', boxSizing: 'border-box' }} />
                  <div style={{ fontSize: 9, color: T.textMuted, marginTop: 4 }}>Format: minute hour day_of_month month day_of_week</div>
                </div>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
                <button onClick={() => setNewRule({...newRule, autofix_enabled: !newRule.autofix_enabled})}
                  style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 6, backgroundColor: newRule.autofix_enabled ? T.successSoft : `${T.textMuted}20`, border: 'none', cursor: 'pointer' }}
                  data-testid="new-rule-autofix-toggle">
                  <Ionicons name={newRule.autofix_enabled ? 'construct' : 'construct-outline'} size={12} color={newRule.autofix_enabled ? T.success : T.textMuted} />
                  <span style={{ fontSize: 10, fontWeight: 700, color: newRule.autofix_enabled ? T.success : T.textMuted }}>Auto-Fix {newRule.autofix_enabled ? 'ON' : 'OFF'}</span>
                </button>
                <button onClick={saveNewRule} disabled={saving || !newRule.name.trim()}
                  style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.purple, padding: '8px 16px', borderRadius: 8, opacity: saving || !newRule.name.trim() ? 0.5 : 1, border: 'none', cursor: 'pointer' }}
                  data-testid="save-rule-btn">
                  <Ionicons name="checkmark" size={14} color={colors.primaryText} />
                  <span style={{ fontSize: 12, fontWeight: 700, color: colors.primaryText }}>{saving ? 'Saving...' : 'Save Rule'}</span>
                </button>
              </div>
            </div>
          )}

          {rules.map((rule, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < rules.length - 1 ? `1px solid ${T.border}` : 'none' }} data-testid={`rule-${i}`}>
              <div style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: rule.enabled ? T.success : T.textMuted }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{rule.name}</div>
                <div style={{ fontSize: 10, color: T.textMuted }}>{rule.metric} {rule.condition} {rule.threshold} → {rule.action} | cooldown: {rule.cooldown_minutes || 15}m
                  {rule.schedule_type && rule.schedule_type !== 'always' && (
                    <span style={{ marginLeft: 6, fontSize: 9, color: T.cyan, backgroundColor: `${T.cyan}15`, padding: '1px 5px', borderRadius: 3 }}>
                      {rule.schedule_type === 'time_window' ? `${rule.schedule_window_start}-${rule.schedule_window_end} ${rule.schedule_timezone || 'UTC'}` : `cron: ${rule.schedule_cron}`}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => toggleAutofix(rule.rule_id, rule.autofix_enabled)}
                style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 4, padding: '4px 8px', borderRadius: 6, backgroundColor: rule.autofix_enabled ? T.successSoft : `${T.textMuted}20`, border: 'none', cursor: 'pointer' }}
                data-testid={`autofix-toggle-${i}`}
              >
                <Ionicons name={rule.autofix_enabled ? 'construct' : 'construct-outline'} size={10} color={rule.autofix_enabled ? T.success : T.textMuted} />
                <span style={{ fontSize: 9, fontWeight: 700, color: rule.autofix_enabled ? T.success : T.textMuted }}>AUTO-FIX {rule.autofix_enabled ? 'ON' : 'OFF'}</span>
              </button>
              <button onClick={() => deleteRule(rule.rule_id)}
                style={{ padding: 4, borderRadius: 4, border: 'none', backgroundColor: 'transparent', cursor: 'pointer' }}
                data-testid={`delete-rule-${i}`}>
                <Ionicons name="trash-outline" size={12} color={T.textMuted} />
              </button>
              <span style={{ fontSize: 9, color: rule.enabled ? T.success : T.textMuted, fontWeight: '600', width: 40, textAlign: 'right' }}>{rule.enabled ? 'ACTIVE' : 'OFF'}</span>
            </div>
          ))}
        </div>

        {/* Recent Incidents */}
        <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="recent-incidents">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="alert-circle" size={16} color={T.error} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('automationEngine.cards.recentIncidents.title', 'Recent Incidents')}</Text>
          </div>
          {data.recent_incidents.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 24 }}>
              <Ionicons name="checkmark-circle" size={28} color={T.successText} />
              <div style={{ fontSize: 12, color: T.successText, marginTop: 8, fontWeight: '600' }}>No incidents recorded</div>
              <div style={{ fontSize: 10, color: T.textMuted, marginTop: 4 }}>All systems operating normally</div>
            </div>
          ) : (
            data.recent_incidents.slice(0, 8).map((inc: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < Math.min(data.recent_incidents.length, 8) - 1 ? `1px solid ${T.border}` : 'none' }}>
                <div style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: inc.status === 'open' ? T.error : T.success }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: '600', color: T.text }}>{inc.title || inc.incident_id}</div>
                  <div style={{ fontSize: 10, color: T.textMuted }}>{inc.created_at}</div>
                </div>
                <span style={{ fontSize: 9, fontWeight: '700', color: inc.status === 'open' ? T.error : T.success, textTransform: 'uppercase' }}>{inc.status}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Alert History + Test Alert */}
      <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="alert-history">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Ionicons name="notifications" size={16} color={T.primary} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{t("securityDashboard.alertHistory.title")}</Text>
          <Text style={{ fontSize: 10, color: T.textMuted }}>{alerts.length} alerts</Text>
          <button onClick={sendTestAlert} disabled={sendingTest}
            style={{ marginLeft: 'auto', display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.primarySoft, padding: '5px 10px', borderRadius: 6, opacity: sendingTest ? 0.5 : 1, border: 'none', cursor: 'pointer' }}
            data-testid="send-test-alert-btn">
            <Ionicons name="mail" size={10} color={T.primary} />
            <span style={{ fontSize: 10, fontWeight: 700, color: T.primary }}>{sendingTest ? 'Sending...' : 'Send Test Alert'}</span>
          </button>
          {typeof window !== 'undefined' && 'Notification' in window && (
            <button onClick={togglePushNotifications} disabled={pushLoading}
              style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: pushEnabled ? T.successSoft : `${T.textMuted}20`, padding: '5px 10px', borderRadius: 6, opacity: pushLoading ? 0.5 : 1, border: 'none', cursor: 'pointer' }}
              data-testid="push-notifications-toggle">
              <Ionicons name={pushEnabled ? 'notifications' : 'notifications-off-outline'} size={10} color={pushEnabled ? T.success : T.textMuted} />
              <span style={{ fontSize: 10, fontWeight: 700, color: pushEnabled ? T.success : T.textMuted }}>
                {pushLoading ? 'Loading...' : pushEnabled ? 'Push ON' : 'Enable Push'}
              </span>
            </button>
          )}
        </div>
        {testResult && (
          <div style={{ padding: '8px 12px', borderRadius: 8, marginBottom: 12, backgroundColor: testResult.includes('Failed') ? T.errorSoft : T.successSoft, border: `1px solid ${testResult.includes('Failed') ? T.error : T.success}` }} data-testid="test-alert-result">
            <Text style={{ fontSize: 11, color: testResult.includes('Failed') ? T.error : T.success, fontWeight: '600' }}>{testResult}</Text>
          </div>
        )}
        {alerts.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Ionicons name="notifications-off-outline" size={24} color={T.textMuted} />
            <div style={{ fontSize: 12, color: T.textMuted, marginTop: 8 }}>No alerts yet</div>
            <div style={{ fontSize: 10, color: T.textMuted, marginTop: 4 }}>Send a test alert to verify email delivery, or wait for the monitor to detect threshold breaches.</div>
          </div>
        ) : (
          alerts.slice(0, 15).map((alert: any, i: number) => {
            const isRecovery = alert.type === 'recovery';
            const isTest = alert.type === 'test';
            const alertColor = isRecovery ? T.success : isTest ? T.primary : T.error;
            const alertIcon = isRecovery ? 'checkmark-circle' : isTest ? 'flask' : 'warning';
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 0', borderBottom: i < Math.min(alerts.length, 15) - 1 ? `1px solid ${T.border}` : 'none' }} data-testid={`alert-${i}`}>
                <div style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: `${alertColor}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2 }}>
                  <Ionicons name={alertIcon as any} size={13} color={alertColor} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 12, fontWeight: '700', color: T.text }}>{alert.rule_name}</span>
                    <span style={{ fontSize: 8, fontWeight: '700', color: alertColor, backgroundColor: `${alertColor}18`, padding: '1px 5px', borderRadius: 3, textTransform: 'uppercase' }}>
                      {isRecovery ? 'RECOVERED' : isTest ? 'TEST' : 'BREACH'}
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>
                    {alert.metric}: {alert.value} {isRecovery ? `| Downtime: ${alert.downtime}` : `(threshold: ${alert.threshold})`}
                  </div>
                  {alert.action_taken && !isRecovery && (
                    <div style={{ fontSize: 10, color: T.warningText, marginTop: 2 }}>Action: {alert.action_taken}</div>
                  )}
                  {isRecovery && alert.fix_applied && (
                    <div style={{ fontSize: 10, color: T.successText, marginTop: 2 }}>Fix: {alert.fix_applied}</div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 3 }}>
                    <span style={{ fontSize: 9, color: T.textMuted }}>{new Date(alert.created_at).toLocaleString()}</span>
                    {alert.notified_emails && (
                      <span style={{ fontSize: 9, color: T.textMuted }}>
                        <Ionicons name="mail-outline" size={9} color={T.textMuted} /> {alert.notified_emails.length} notified
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* How it works banner */}
      <div style={{ backgroundColor: T.primarySoft, borderRadius: 12, padding: 14, border: `1px solid ${T.primary}`, display: 'flex', alignItems: 'flex-start', gap: 10 }} data-testid="how-it-works-banner">
        <Ionicons name="information-circle" size={16} color={T.primary} style={{ marginTop: 2 } as any} />
        <div>
          <Text style={{ fontSize: 11, fontWeight: '700', color: T.primary, marginBottom: 4 }}>{tx('automationEngine.banner.howItWorksTitle', 'How Real-Time Alerting Works')}</Text>
          <Text style={{ fontSize: 10, color: T.textSec, lineHeight: 16 }}>
            {tx('automationEngine.banner.howItWorksBody', 'The monitor checks system metrics every 60s against your alert rules. When a threshold is breached, it creates an incident, attempts a safe auto-fix (if enabled), and sends an instant email alert + browser push notification (if enabled). Rules can run 24/7 or be scheduled using time windows or cron expressions. When the service recovers, a recovery notification is sent with downtime duration and the fix applied.')}
          </Text>
        </div>
      </div>
    </ScrollView>
  );
}
