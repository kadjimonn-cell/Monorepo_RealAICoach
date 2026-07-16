import React, { useEffect, useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, TouchableOpacity, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

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

// Module-scope fallback for METRIC_ICONS (can't access component-scoped T)
const T = {
  bg: 'var(--app-bg)' as any, bgSoft: 'var(--app-surface)' as any, card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any, text: 'var(--app-text)' as any, textSec: 'var(--app-text-sec)' as any, textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any, success: 'var(--app-success)' as any, warning: 'var(--app-warning)' as any, error: 'var(--app-error)' as any,
  purple: 'var(--app-primary)', cyan: 'var(--app-primary)',
  successText: 'var(--app-success)', warningText: 'var(--app-warning)', purpleText: 'var(--app-primary)',
};

type TabId = 'status' | 'rules' | 'history';

const tx = (_key: string, fallback: string) => fallback;

const METRIC_ICONS: Record<string, { icon: string; color: string; unit: string }> = {
  cpu: { icon: 'hardware-chip', color: T.primary, unit: '%' },
  memory: { icon: 'server', color: T.purpleText, unit: '%' },
  rps: { icon: 'speedometer', color: T.cyan, unit: 'req/s' },
  connections: { icon: 'git-network', color: T.warningText, unit: '' },
  error_rate: { icon: 'alert-circle', color: T.error, unit: '%' },
};

interface Props { colors: any; }

export default function AutoScalingPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<TabId>('status');
  const { data: status, loading, refetch: loadStatus } = useLiveQuery('/admin/scaling/status', { entity: 'scaling', pollInterval: 15000 });
  const { data: rulesData } = useLiveQuery('/admin/scaling/rules', { entity: 'scaling', pollInterval: 60000 });
  const rules = rulesData?.rules || [];
  const [history, setHistory] = useState<any>(null);
  const [scaling, setScaling] = useState(false);
  const [msg, setMsg] = useState({ text: '', type: '' });

  const loadHistory = () => { api.get('/admin/scaling/history').then(r => setHistory(r.data)).catch(() => {}); };
  useEffect(() => { if (msg.text) { const t = setTimeout(() => setMsg({ text: '', type: '' }), 4000); return () => clearTimeout(t); } }, [msg]);

  const triggerScale = async (action: string) => {
    setScaling(true);
    try {
      const res = await api.post('/admin/scaling/trigger', { action, amount: 1, reason: `Manual ${action} from dashboard` });
      setMsg({ text: res.data.message, type: 'success' });
      loadStatus();
      loadHistory();
    } catch (e: any) { setMsg({ text: e.response?.data?.detail || 'Failed', type: 'error' }); }
    finally { setScaling(false); }
  };

  const toggleRule = async (ruleId: string, enabled: boolean) => {
    try {
      await api.put(`/admin/scaling/rules/${ruleId}`, { enabled });
      setRules(rules.map(r => r.rule_id === ruleId ? { ...r, enabled } : r));
    } catch { setMsg({ text: 'Failed to update rule', type: 'error' }); }
  };

  const deleteRule = async (ruleId: string) => {
    try {
      await api.delete(`/admin/scaling/rules/${ruleId}`);
      setRules(rules.filter(r => r.rule_id !== ruleId));
      setMsg({ text: 'Rule deleted', type: 'success' });
    } catch { setMsg({ text: 'Failed to delete rule', type: 'error' }); }
  };

  const tabs: { id: TabId; label: string; icon: string }[] = [
    { id: 'status', label: 'Status', icon: 'speedometer' },
    { id: 'rules', label: 'Rules', icon: 'options' },
    { id: 'history', label: 'History', icon: 'time' },
  ];

  return (
    <View data-testid="auto-scaling-panel" testID="auto-scaling-panel">
      <AutoFixBanner domain="auto_scaling" />
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="auto-scaling-title" testID="auto-scaling-title">{tx('admin.autoScalingPanel.auto.text.001', 'Auto-Scaling Engine')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 4 }}>{tx('admin.autoScalingPanel.auto.text.002', 'Dynamic infrastructure scaling & resource management')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <TouchableOpacity onPress={() => triggerScale('scale_up')} disabled={scaling} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: T.success }} data-testid="scale-up-btn" testID="scale-up-btn">
            <Ionicons name="arrow-up" size={14} color="var(--app-primary-text)" />
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryText }}>{tx('admin.autoScalingPanel.auto.text.003', 'Scale Up')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => triggerScale('scale_down')} disabled={scaling} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: T.warning }} data-testid="scale-down-btn" testID="scale-down-btn">
            <Ionicons name="arrow-down" size={14} color="var(--app-primary-text)" />
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryText }}>{tx('admin.autoScalingPanel.auto.text.004', 'Scale Down')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {msg.text ? (
        <View style={{ backgroundColor: msg.type === 'success' ? 'var(--app-success-soft)' : 'var(--app-error-soft)', borderRadius: 10, padding: 10, marginBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: msg.type === 'success' ? 'var(--app-success-soft)' : 'var(--app-error-soft)' }}>
          <Ionicons name={msg.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={16} color={msg.type === 'success' ? T.success : T.error} />
          <Text style={{ color: msg.type === 'success' ? T.success : T.error, fontSize: 12, flex: 1 }}>{msg.text}</Text>
        </View>
      ) : null}

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {tabs.map(t => (
          <TouchableOpacity key={t.id} onPress={() => { setTab(t.id); if (t.id === 'history' && !history) loadHistory(); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8, backgroundColor: tab === t.id ? T.primary : T.card, borderWidth: 1, borderColor: tab === t.id ? T.primary : T.border }} data-testid={`scaling-tab-${t.id}`} testID={`scaling-tab-${t.id}`}>
            <Ionicons name={t.icon as any} size={13} color={tab === t.id ? 'var(--app-primary-text)' : T.textMuted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: tab === t.id ? 'var(--app-primary-text)' : T.textMuted }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Status Tab */}
      {tab === 'status' && (
        loading ? <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View> :
        status ? (
          <View>
            {/* Instance Gauge */}
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border, alignItems: 'center', marginBottom: 16 }} data-testid="instance-gauge" testID="instance-gauge">
              <View style={{ width: 100, height: 100, borderRadius: 50, borderWidth: 5, borderColor: (globalThis as any).__alphaColor(T.primary, '40'), alignItems: 'center', justifyContent: 'center', marginBottom: 10 }}>
                <Text style={{ color: T.primary, fontSize: 32, fontWeight: '900' }}>{status.instances?.current || 0}</Text>
              </View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.autoScalingPanel.auto.text.005', 'Active Instances')}</Text>
              <View style={{ flexDirection: 'row', gap: 16, marginTop: 10 }}>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.autoScalingPanel.auto.text.006', 'Min')}</Text>
                  <Text style={{ color: T.warningText, fontSize: 14, fontWeight: '700' }}>{status.instances?.min || 1}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.autoScalingPanel.auto.text.007', 'Desired')}</Text>
                  <Text style={{ color: T.successText, fontSize: 14, fontWeight: '700' }}>{status.instances?.desired || 2}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.autoScalingPanel.auto.text.008', 'Max')}</Text>
                  <Text style={{ color: T.error, fontSize: 14, fontWeight: '700' }}>{status.instances?.max || 20}</Text>
                </View>
              </View>
            </View>

            {/* Resource Metrics */}
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="resource-metrics" testID="resource-metrics">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.autoScalingPanel.auto.text.009', 'Resource Metrics')}</Text>
              <View style={{ gap: 10 }}>
                <MetricBar label="CPU" value={status.metrics?.cpu_pct || 0} color={T.primary} icon="hardware-chip" />
                <MetricBar label="Memory" value={status.metrics?.memory_pct || 0} color={T.purpleText} icon="server" extra={`${status.metrics?.memory_used_gb || 0}/${status.metrics?.memory_total_gb || 0} GB`} />
                <MetricBar label="Disk" value={status.metrics?.disk_pct || 0} color={T.cyan} icon="disc" />
              </View>
            </View>

            {/* Traffic KPIs */}
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }} data-testid="traffic-kpis" testID="traffic-kpis">
              <KPI label="Sessions" value={status.metrics?.active_sessions || 0} icon="people" color={T.primary} />
              <KPI label="RPS" value={status.metrics?.rps_estimate || 0} icon="speedometer" color={T.successText} />
              <KPI label="Latency" value={`${status.metrics?.avg_response_ms || 0}ms`} icon="time" color={T.warningText} />
              <KPI label="Errors" value={`${status.metrics?.error_rate_pct || 0}%`} icon="alert" color={T.error} />
            </View>

            {/* Recent Events */}
            {status.recent_events?.length > 0 && (
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="recent-scale-events" testID="recent-scale-events">
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 10 }}>{tx('admin.autoScalingPanel.auto.text.010', 'Recent Events')}</Text>
                {status.recent_events.slice(0, 5).map((e: any, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: T.border }}>
                    <Ionicons name={e.action === 'scale_up' ? 'arrow-up-circle' : 'arrow-down-circle'} size={16} color={e.action === 'scale_up' ? T.success : T.warning} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{e.from_instances} &rarr; {e.to_instances} instances</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10 }}>{e.reason}</Text>
                    </View>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{e.timestamp?.slice(11, 16)}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        ) : <Text style={{ color: T.error, padding: 20 }}>{tx('admin.autoScalingPanel.auto.text.011', 'Failed to load status')}</Text>
      )}

      {/* Rules Tab */}
      {tab === 'rules' && (
        <View>
          {rules.length === 0 ? (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 30, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
              <Ionicons name="options-outline" size={32} color={T.textMuted} />
              <Text style={{ color: T.textSec, fontSize: 13, marginTop: 8 }}>{tx('admin.autoScalingPanel.auto.text.012', 'No scaling rules configured')}</Text>
            </View>
          ) : (
            <View style={{ gap: 10 }}>
              {rules.map(rule => {
                const mi = METRIC_ICONS[rule.metric] || { icon: 'ellipse', color: T.textMuted, unit: '' };
                return (
                  <View key={rule.rule_id} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: rule.enabled ? T.border : T.border, borderLeftWidth: 3, borderLeftColor: rule.enabled ? mi.color : T.textMuted, opacity: rule.enabled ? 1 : 0.6 }} data-testid={`rule-${rule.rule_id}`} testID={`rule-${rule.rule_id}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <Ionicons name={mi.icon as any} size={16} color={mi.color} />
                        <View>
                          <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{rule.name}</Text>
                          <Text style={{ color: T.textMuted, fontSize: 10 }}>Metric: {rule.metric} {mi.unit}</Text>
                        </View>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <Switch value={rule.enabled} onValueChange={v => toggleRule(rule.rule_id, v)} trackColor={{ false: T.bgSoft, true: T.success + '60' }} thumbColor={rule.enabled ? T.success : T.textMuted} />
                        <TouchableOpacity onPress={() => deleteRule(rule.rule_id)} data-testid={`delete-rule-${rule.rule_id}`} testID={`delete-rule-${rule.rule_id}`}>
                          <Ionicons name="trash-outline" size={16} color={T.error} />
                        </TouchableOpacity>
                      </View>
                    </View>
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 8, padding: 8, alignItems: 'center' }}>
                        <Ionicons name="arrow-up" size={12} color={T.successText} />
                        <Text style={{ color: T.successText, fontSize: 14, fontWeight: '800' }}>{rule.threshold_up}{mi.unit}</Text>
                        <Text style={{ color: T.textMuted, fontSize: 9 }}>Scale Up +{rule.scale_up_by}</Text>
                      </View>
                      <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 8, padding: 8, alignItems: 'center' }}>
                        <Ionicons name="arrow-down" size={12} color={T.warningText} />
                        <Text style={{ color: T.warningText, fontSize: 14, fontWeight: '800' }}>{rule.threshold_down}{mi.unit}</Text>
                        <Text style={{ color: T.textMuted, fontSize: 9 }}>Scale Down -{rule.scale_down_by}</Text>
                      </View>
                      <View style={{ flex: 1, backgroundColor: T.bgSoft, borderRadius: 8, padding: 8, alignItems: 'center' }}>
                        <Ionicons name="time" size={12} color={T.cyan} />
                        <Text style={{ color: T.cyan, fontSize: 14, fontWeight: '800' }}>{rule.cooldown_seconds}s</Text>
                        <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.autoScalingPanel.auto.text.013', 'Cooldown')}</Text>
                      </View>
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}

      {/* History Tab */}
      {tab === 'history' && (
        history ? (
          <View>
            {/* Stats */}
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }} data-testid="scaling-stats" testID="scaling-stats">
              <KPI label="24h Events" value={history.stats?.events_24h || 0} icon="pulse" color={T.primary} />
              <KPI label="7d Events" value={history.stats?.events_7d || 0} icon="calendar" color={T.cyan} />
              <KPI label="Scale Ups" value={history.stats?.scale_ups_7d || 0} icon="arrow-up" color={T.successText} />
              <KPI label="Scale Downs" value={history.stats?.scale_downs_7d || 0} icon="arrow-down" color={T.warningText} />
            </View>

            {/* Event List */}
            {(history.events || []).length === 0 ? (
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 30, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
                <Ionicons name="time-outline" size={32} color={T.textMuted} />
                <Text style={{ color: T.textSec, fontSize: 13, marginTop: 8 }}>{tx('admin.autoScalingPanel.auto.text.014', 'No scaling events yet')}</Text>
              </View>
            ) : (
              <View style={{ gap: 8 }}>
                {(history.events || []).map((e: any, i: number) => (
                  <View key={i} style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: e.action === 'scale_up' ? T.success : T.warning }} data-testid={`history-event-${i}`} testID={`history-event-${i}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        <Ionicons name={e.action === 'scale_up' ? 'trending-up' : 'trending-down'} size={14} color={e.action === 'scale_up' ? T.success : T.warning} />
                        <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{e.action?.replace('_', ' ')}</Text>
                        <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(T.primary, '20') }}>
                          <Text style={{ color: T.primary, fontSize: 9, fontWeight: '700' }}>{e.trigger}</Text>
                        </View>
                      </View>
                      <Text style={{ color: T.textMuted, fontSize: 10 }}>{e.timestamp?.slice(0, 16)?.replace('T', ' ')}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Text style={{ color: T.textSec, fontSize: 18, fontWeight: '800' }}>{e.from_instances}</Text>
                      <Ionicons name="arrow-forward" size={12} color={T.textMuted} />
                      <Text style={{ color: e.action === 'scale_up' ? T.success : T.warning, fontSize: 18, fontWeight: '800' }}>{e.to_instances}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 11, marginLeft: 6 }}>{tx('admin.autoScalingPanel.auto.text.015', 'instances')}</Text>
                    </View>
                    <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{e.reason}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        ) : (
          <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>
        )
      )}
    </View>
  );
}

function MetricBar({ label, value, color, icon, extra }: { label: string; value: number; color: string; icon: string; extra?: string }) {
  const barColor = value > 90 ? T.error : value > 70 ? T.warning : color;
  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name={icon as any} size={12} color={barColor} />
          <Text style={{ color: T.textSec, fontSize: 12 }}>{label}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          {extra && <Text style={{ color: T.textMuted, fontSize: 10 }}>{extra}</Text>}
          <Text style={{ color: barColor, fontSize: 12, fontWeight: '700' }}>{value.toFixed(1)}%</Text>
        </View>
      </View>
      <View style={{ height: 6, backgroundColor: T.bgSoft, borderRadius: 3, overflow: 'hidden', flexDirection: 'row' }}>
        <View style={{ height: 6, flex: Math.max(value, 1), backgroundColor: barColor, borderRadius: 3 }} />
        <View style={{ flex: Math.max(100 - value, 1) }} />
      </View>
    </View>
  );
}

function KPI({ label, value, icon, color }: { label: string; value: string | number; icon: string; color: string }) {
  return (
    <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 10, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
      <Ionicons name={icon as any} size={16} color={color} style={{ marginBottom: 4 }} />
      <Text style={{ color, fontSize: 16, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: T.textMuted, fontSize: 9, marginTop: 2 }}>{label}</Text>
    </View>
  );
}
