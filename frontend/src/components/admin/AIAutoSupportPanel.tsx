import React, { useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, TouchableOpacity, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

function makeT(AC: any) { return {
  bg: AC.bg,
  bgSoft: AC.bgSoft,
  card: AC.card,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  primary: AC.primary,
  success: AC.success,
  warning: AC.warning,
  error: AC.error,
  purple: AC.purple,
  cyan: AC.cyan || AC.info,
  pink: AC.purple,
  orange: AC.orange,
  successText: AC.successText || AC.success,
  warningText: AC.warningText || AC.warning,
  purpleText: AC.purpleText || AC.purple,
  primaryText: AC.primaryText || 'var(--app-primary-text)',
}; }

interface Props { colors: any; }

export default function AIAutoSupportPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { data, loading, refetch: load } = useLiveQuery('/admin/ai-support/dashboard', { entity: 'ai-support', pollInterval: 30000 });
  const [tab, setTab] = useState('dashboard');
  const [logs, setLogs] = useState<any[]>([]);
  const [bulking, setBulking] = useState(false);
  const [bulkResult, setBulkResult] = useState<any>(null);

  const loadLogs = () => {
    api.get('/admin/ai-support/log').then(r => setLogs(r.data.logs || [])).catch(() => {});
  };

  const bulkResolve = async () => {
    setBulking(true);
    try {
      const r = await api.post('/admin/ai-support/bulk-resolve');
      setBulkResult(r.data);
      load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AIAutoSupportPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setBulking(false);
  };

  const toggleEnabled = async () => {
    if (!data) return;
    const newEnabled = !data.config?.enabled;
    try {
      await api.post('/admin/ai-support/configure', { enabled: newEnabled });
      load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/AIAutoSupportPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (loading) return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;
  if (!data) return <Text style={{ color: T.error, padding: 20 }}>{tx('admin.aIAutoSupportPanel.auto.text.001', 'Failed to load support data')}</Text>;

  const { overview, category_breakdown, daily_trend, confidence_distribution, ai_summary, config } = data;
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: 'grid' },
    { id: 'trends', label: 'Trends', icon: 'trending-up' },
    { id: 'logs', label: 'Logs', icon: 'list' },
    { id: 'config', label: 'Settings', icon: 'settings' },
  ];

  return (
    <View data-testid="ai-auto-support-panel" testID="ai-auto-support-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="ai-support-title" testID="ai-support-title">{tx('admin.aIAutoSupportPanel.auto.text.002', 'AI Auto-Support')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 4 }}>{tx('admin.aIAutoSupportPanel.auto.text.003', 'Automated ticket resolution with AI')}</Text>
        </View>
        <TouchableOpacity onPress={bulkResolve} disabled={bulking} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: T.primary }} data-testid="bulk-resolve-btn" testID="bulk-resolve-btn">
          {bulking ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="flash" size={14} color={T.primaryText} />}
          <Text style={{ fontSize: 12, fontWeight: '700', color: T.primaryText }}>{tx('admin.aIAutoSupportPanel.auto.text.004', 'Bulk Resolve')}</Text>
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {tabs.map(t => (
          <TouchableOpacity key={t.id} onPress={() => { setTab(t.id); if (t.id === 'logs') loadLogs(); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: tab === t.id ? T.primary : T.bgSoft }}
            data-testid={`support-tab-${t.id}`} testID={`support-tab-${t.id}`}>
            <Ionicons name={t.icon as any} size={13} color={tab === t.id ? T.primaryText : T.textSec} />
            <Text style={{ fontSize: 11, fontWeight: '600', color: tab === t.id ? T.primaryText : T.textSec }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Bulk result */}
      {bulkResult && (
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.success, '15'), borderRadius: 10, padding: 12, marginBottom: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '30') }}>
          <Text style={{ color: T.successText, fontSize: 12, fontWeight: '700' }}>{tx('admin.aIAutoSupportPanel.auto.text.005', 'Bulk Resolve Complete')}</Text>
          <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>
            Attempted: {bulkResult.attempted} | Resolved: {bulkResult.resolved} | Escalated: {bulkResult.escalated} | Failed: {bulkResult.failed}
          </Text>
        </View>
      )}

      {/* Dashboard */}
      {tab === 'dashboard' && (
        <View style={{ gap: 12 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="support-kpis" testID="support-kpis">
            <KPI icon="chatbubbles" color={T.primary} label="Total Interactions" value={overview.total_interactions} T={T} />
            <KPI icon="checkmark-circle" color={T.successText} label="Auto-Resolved" value={overview.auto_resolved} T={T} />
            <KPI icon="trending-up" color={T.cyan} label="Resolution Rate" value={`${overview.resolution_rate}%`} T={T} />
            <KPI icon="speedometer" color={T.warningText} label="Avg Confidence" value={`${overview.avg_confidence}%`} T={T} />
            <KPI icon="alert-circle" color={T.error} label="Open Tickets" value={overview.open_tickets} T={T} />
            <KPI icon="time" color={T.purpleText} label="Recent (7d)" value={overview.recent_7d} T={T} />
          </View>

          {/* Confidence Distribution */}
          {confidence_distribution && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="conf-distribution" testID="conf-distribution">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIAutoSupportPanel.auto.text.006', 'Confidence Distribution')}</Text>
              <View style={{ flexDirection: 'row', gap: 10 }}>
                {[{ label: 'High (80%+)', value: confidence_distribution.high, color: T.successText },
                  { label: 'Medium (50-80%)', value: confidence_distribution.medium, color: T.warningText },
                  { label: 'Low (<50%)', value: confidence_distribution.low, color: T.error }].map(d => (
                  <View key={d.label} style={{ flex: 1, alignItems: 'center', paddingVertical: 10, backgroundColor: (globalThis as any).__alphaColor(d.color, '10'), borderRadius: 10 }}>
                    <Text style={{ fontSize: 20, fontWeight: '800', color: d.color }}>{d.value}</Text>
                    <Text style={{ fontSize: 9, color: T.textMuted, marginTop: 4 }}>{d.label}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Category Breakdown */}
          {(category_breakdown || []).length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIAutoSupportPanel.auto.text.007', 'Category Breakdown')}</Text>
              {category_breakdown.map((c: any) => (
                <View key={c.category} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}>
                  <Text style={{ color: T.text, fontSize: 12, textTransform: 'capitalize' }}>{c.category}</Text>
                  <View style={{ flexDirection: 'row', gap: 12 }}>
                    <Text style={{ color: T.textSec, fontSize: 11 }}>Total: {c.total}</Text>
                    <Text style={{ color: T.successText, fontSize: 11 }}>Resolved: {c.resolved}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}

          {/* AI Summary */}
          {ai_summary && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '30') }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <Ionicons name="sparkles" size={14} color={T.purpleText} />
                <Text style={{ color: T.purpleText, fontSize: 12, fontWeight: '700' }}>{tx('admin.aIAutoSupportPanel.auto.text.008', 'AI Resolution Summary')}</Text>
              </View>
              {ai_summary.split('\n').filter((l: string) => l.trim()).map((line: string, i: number) => (
                <View key={i} style={{ flexDirection: 'row', gap: 6, marginBottom: 6 }}>
                  <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: T.purple, marginTop: 6 }} />
                  <Text style={{ color: T.text, fontSize: 11, lineHeight: 18, flex: 1 }}>{line.replace(/^[\s\-*•]+/, '').trim()}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Trends */}
      {tab === 'trends' && (
        <View style={{ gap: 12 }}>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIAutoSupportPanel.auto.text.009', '7-Day Resolution Trend')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: 100 }}>
              {(daily_trend || []).map((d: any, i: number) => {
                const max = Math.max(...(daily_trend || []).map((x: any) => x.total), 1);
                return (
                  <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                    <View style={{ width: '100%', height: Math.max(4, (d.total / max) * 80), borderRadius: 4, overflow: 'hidden' }}>
                      <View style={{ height: '100%', backgroundColor: (globalThis as any).__alphaColor(T.primary, '30') }} />
                      <View style={{ position: 'absolute', bottom: 0, width: '100%', height: d.total > 0 ? `${(d.resolved / d.total) * 100}%` : '0%' as any, backgroundColor: T.success }} />
                    </View>
                    <Text style={{ fontSize: 8, color: T.textMuted, marginTop: 4 }}>{d.date}</Text>
                    <Text style={{ fontSize: 8, color: T.textSec }}>{d.total}</Text>
                  </View>
                );
              })}
            </View>
            <View style={{ flexDirection: 'row', gap: 12, marginTop: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: (globalThis as any).__alphaColor(T.primary, '30') }} />
                <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.aIAutoSupportPanel.auto.text.010', 'Total')}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: T.success }} />
                <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.aIAutoSupportPanel.auto.text.011', 'Resolved')}</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {/* Logs */}
      {tab === 'logs' && (
        <View style={{ gap: 6 }}>
          {logs.length === 0 && <Text style={{ color: T.textMuted, padding: 20, textAlign: 'center' }}>{tx('admin.aIAutoSupportPanel.auto.text.012', 'No AI support logs yet')}</Text>}
          {logs.map((log: any, i: number) => (
            <View key={i} style={{ backgroundColor: T.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: log.auto_resolved ? (globalThis as any).__alphaColor(T.success, '30') : T.border, borderLeftWidth: 3, borderLeftColor: log.auto_resolved ? T.success : T.warning }} data-testid={`support-log-${i}`} testID={`support-log-${i}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }}>Ticket: {(log.ticket_id || '').slice(0, 16)}...</Text>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  <View style={{ backgroundColor: log.auto_resolved ? (globalThis as any).__alphaColor(T.success, '20') : T.warning + '20', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                    <Text style={{ fontSize: 9, fontWeight: '700', color: log.auto_resolved ? T.success : T.warning }}>{log.auto_resolved ? 'RESOLVED' : 'ESCALATED'}</Text>
                  </View>
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.primary, '20'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                    <Text style={{ fontSize: 9, fontWeight: '700', color: T.primary }}>{Math.round((log.confidence || 0) * 100)}%</Text>
                  </View>
                </View>
              </View>
              <Text style={{ color: T.textSec, fontSize: 10 }} numberOfLines={2}>{log.response}</Text>
              <Text style={{ color: T.textMuted, fontSize: 9, marginTop: 4 }}>{log.trigger} | {log.category} | {new Date(log.created_at).toLocaleString()}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Config */}
      {tab === 'config' && config && (
        <View style={{ gap: 12 }}>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 16 }}>{tx('admin.aIAutoSupportPanel.auto.text.013', 'AI Support Configuration')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <View>
                <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{tx('admin.aIAutoSupportPanel.auto.text.014', 'AI Auto-Support')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.aIAutoSupportPanel.auto.text.015', 'Automatically respond to new tickets')}</Text>
              </View>
              <Switch value={config.enabled} onValueChange={toggleEnabled} trackColor={{ false: T.bgSoft, true: T.primary + '40' }} thumbColor={config.enabled ? T.primary : T.textMuted} />
            </View>
            <ConfigRow label="Auto-Resolve Threshold" value={`${(config.auto_resolve_confidence || 0.8) * 100}%`} T={T} />
            <ConfigRow label="Max Auto-Responses" value={config.max_auto_responses_per_ticket || 2} T={T} />
            <ConfigRow label="Escalation Keywords" value={(config.escalation_keywords || []).join(', ')} T={T} />
          </View>
        </View>
      )}
    </View>
  );
}

function KPI({ icon, color, label, value, T }: { icon: string; color: string; label: string; value: number | string; T: any }) {
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: color, minWidth: 140, flex: 1 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <View style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={12} color={color} />
        </View>
        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600', flex: 1 }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 20, fontWeight: '800' }}>{typeof value === 'number' ? value.toLocaleString() : value}</Text>
    </View>
  );
}

function ConfigRow({ label, value, T }: { label: string; value: any; T: any }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border }}>
      <Text style={{ color: T.textSec, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{String(value)}</Text>
    </View>
  );
}
