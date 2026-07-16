import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);
const LEVEL_COLORS: any = { 0: C.green, 1: C.yellow, 2: C.orange, 3: C.red };
const LEVEL_LABELS: any = { 0: 'Normal', 1: 'Warning', 2: 'Urgent', 3: 'Critical' };
const PRIO_KEYS = ['critical', 'high', 'medium', 'low'];

const tx = (_key: string, fallback: string) => fallback;

export default function EscalationPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const [tab, setTab] = useState<'monitor' | 'policy' | 'analytics' | 'audit'>('monitor');
  const { data: policyData, loading: pLoading, refetch: loadAll } = useLiveQuery('/admin/manage/escalation/policy', { entity: 'escalation', pollInterval: 30000 });
  const { data: activeData, loading: aLoading } = useLiveQuery('/admin/manage/escalation/active', { entity: 'escalation', pollInterval: 15000 });
  const { data: analyticsData, loading: anLoading } = useLiveQuery('/admin/manage/escalation/analytics', { entity: 'escalation', pollInterval: 60000 });
  const { data: historyData, loading: hLoading } = useLiveQuery('/admin/manage/escalation/history?limit=50', { entity: 'escalation', pollInterval: 30000 });
  const policy = policyData;
  const active = activeData?.escalations || [];
  const analytics = analyticsData;
  const history = historyData?.events || [];
  const loading = pLoading || aLoading || anLoading || hLoading;
  const [saving, setSaving] = useState(false);

  const savePolicy = async (updates: any) => {
    setSaving(true);
    try {
      await api.post('/admin/manage/escalation/policy', { ...policy, ...updates });
      const r = await api.get('/admin/manage/escalation/policy');
      setPolicy(r.data);
    } catch (e: any) { Alert.alert(tx('admin.escalationPanel.auto.alert.error', 'Error'), e?.response?.data?.detail || tx('admin.escalationPanel.auto.alert.saveFailed', 'Save failed')); }
    setSaving(false);
  };

  const snoozeTicket = async (ticketId: string) => {
    try {
      await api.post(`/admin/manage/escalation/snooze/${ticketId}`, { minutes: 30 });
      await loadAll();
    } catch (e: any) { Alert.alert(tx('admin.escalationPanel.auto.alert.error', 'Error'), e?.response?.data?.detail || tx('admin.escalationPanel.auto.alert.snoozeFailed', 'Snooze failed')); }
  };

  const overrideEscalation = async (ticketId: string) => {
    try {
      await api.post(`/admin/manage/escalation/override/${ticketId}`, { reason: 'Manual override by admin' });
      await loadAll();
    } catch (e: any) { Alert.alert(tx('admin.escalationPanel.auto.alert.error', 'Error'), e?.response?.data?.detail || tx('admin.escalationPanel.auto.alert.overrideFailed', 'Override failed')); }
  };

  const updateThreshold = (prio: string, level: string, value: string) => {
    const newSla = { ...policy.sla_thresholds };
    if (!newSla[prio]) newSla[prio] = {};
    newSla[prio][level] = parseInt(value) || 0;
    savePolicy({ sla_thresholds: newSla });
  };

  if (loading) return <ActivityIndicator color={C.blue} style={{ padding: 40 }} />;

  return (
    <View data-testid="escalation-panel" testID="escalation-panel">
      <AutoFixBanner domain="escalation" />
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.red, '15'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="alert-circle" size={20} color={C.red} />
          </View>
          <View>
            <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }}>{tx('admin.escalationPanel.auto.text.001', 'Escalation Engine')}</Text>
            <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.escalationPanel.auto.text.002', 'Enterprise SLA compliance & auto-escalation')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <TouchableOpacity onPress={loadAll} style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' }} data-testid="escalation-refresh-btn" testID="escalation-refresh-btn">
            <Ionicons name="refresh" size={16} color={C.blue} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Quick Metrics */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        {[
          { l: 'Active', v: analytics?.active_escalated || 0, c: C.red, icon: 'flame' },
          { l: 'L1 Warning', v: analytics?.by_level?.l1 || 0, c: C.yellow, icon: 'warning' },
          { l: 'L2 Urgent', v: analytics?.by_level?.l2 || 0, c: C.orange, icon: 'alert-circle' },
          { l: 'L3 Critical', v: analytics?.by_level?.l3 || 0, c: C.red, icon: 'skull' },
          { l: 'Breach Rate', v: `${analytics?.sla_breach_rate || 0}%`, c: analytics?.sla_breach_rate > 10 ? C.red : C.green, icon: 'shield' },
          { l: 'Engine', v: policy?.enabled ? 'ON' : 'OFF', c: policy?.enabled ? C.green : C.red, icon: 'flash' },
        ].map(s => (
          <View key={s.l} style={{ flex: 1, minWidth: 80, backgroundColor: (globalThis as any).__alphaColor(s.c, '08'), borderRadius: 12, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.c, '18') }}>
            <Ionicons name={s.icon as any} size={14} color={s.c} style={{ marginBottom: 3 }} />
            <Text style={{ fontSize: 18, fontWeight: '800', color: s.c, letterSpacing: -0.5 }}>{s.v}</Text>
            <Text style={{ fontSize: 9, color: C.muted, fontWeight: '600', marginTop: 2 }}>{s.l}</Text>
          </View>
        ))}
      </View>

      {/* Tab Bar */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {([
          { key: 'monitor', label: 'Live Monitor', icon: 'pulse' },
          { key: 'policy', label: 'SLA Policy', icon: 'settings' },
          { key: 'analytics', label: 'Analytics', icon: 'stats-chart' },
          { key: 'audit', label: 'Audit Trail', icon: 'document-text' },
        ] as const).map(t => (
          <TouchableOpacity key={t.key} onPress={() => setTab(t.key)} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 11, borderRadius: 10, backgroundColor: tab === t.key ? (globalThis as any).__alphaColor(C.red, '12') : C.card, borderWidth: 1, borderColor: tab === t.key ? (globalThis as any).__alphaColor(C.red, '25') : C.border }} data-testid={`escalation-tab-${t.key}`} testID={`escalation-tab-${t.key}`}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.key ? C.red : C.muted} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: tab === t.key ? C.red : C.muted }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ═══ Live Monitor ═══ */}
      {tab === 'monitor' && (
        <View>
          {active.length === 0 ? (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 40, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '20') }} data-testid="no-escalations" testID="no-escalations">
              <Ionicons name="checkmark-circle" size={48} color={C.green} />
              <Text style={{ color: C.green, fontSize: 16, fontWeight: '800', marginTop: 12 }}>{tx('admin.escalationPanel.auto.text.003', 'All Clear')}</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{tx('admin.escalationPanel.auto.text.004', 'No active escalations. All tickets are within SLA.')}</Text>
            </View>
          ) : (
            <View style={{ gap: 8 }}>
              {active.map(ticket => {
                const level = ticket.escalation_level || 0;
                const lc = LEVEL_COLORS[level] || C.red;
                const prio = ticket.ai_classification?.priority || ticket.priority || 'medium';
                return (
                  <View key={ticket.submission_id} style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(lc, '30'), borderLeftWidth: 4, borderLeftColor: lc }} data-testid={`escalated-ticket-${ticket.submission_id}`} testID={`escalated-ticket-${ticket.submission_id}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(lc, '18') }}>
                          <Text style={{ fontSize: 10, fontWeight: '800', color: lc }}>L{level} {LEVEL_LABELS[level]}</Text>
                        </View>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{ticket.ticket_number || ticket.submission_id.slice(0, 12)}</Text>
                      </View>
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        <TouchableOpacity onPress={() => snoozeTicket(ticket.submission_id)} style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.blue, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '20') }} data-testid={`snooze-${ticket.submission_id}`} testID={`snooze-${ticket.submission_id}`}>
                          <Ionicons name="time" size={12} color={C.blue} />
                          <Text style={{ fontSize: 9, fontWeight: '700', color: C.blue }}>{tx('admin.escalationPanel.auto.text.005', 'Snooze')}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => overrideEscalation(ticket.submission_id)} style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.green, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '20') }} data-testid={`override-${ticket.submission_id}`} testID={`override-${ticket.submission_id}`}>
                          <Ionicons name="checkmark" size={12} color={C.green} />
                          <Text style={{ fontSize: 9, fontWeight: '700', color: C.green }}>{tx('admin.escalationPanel.auto.text.006', 'Override')}</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                    <Text style={{ fontSize: 13, fontWeight: '600', color: C.text, marginBottom: 6 }} numberOfLines={1}>{ticket.subject || 'No subject'}</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                      <Text style={{ fontSize: 10, color: C.muted }}>Priority: <Text style={{ fontWeight: '700', color: lc, textTransform: 'uppercase' }}>{prio}</Text></Text>
                      <Text style={{ fontSize: 10, color: C.muted }}>Agent: <Text style={{ fontWeight: '700', color: C.text }}>{ticket.assigned_agent_name || 'Unassigned'}</Text></Text>
                      <Text style={{ fontSize: 10, color: C.muted }}>Status: <Text style={{ fontWeight: '700', color: C.text }}>{ticket.status}</Text></Text>
                      {ticket.created_at && <Text style={{ fontSize: 10, color: C.muted }}>Created: {new Date(ticket.created_at).toLocaleString()}</Text>}
                    </View>
                    {/* Escalation timeline */}
                    {(ticket.escalation_history || []).length > 0 && (
                      <View style={{ marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border }}>
                        {(ticket.escalation_history || []).slice(-3).map((ev: any, i: number) => (
                          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                            <View style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: lc }} />
                            <Text style={{ fontSize: 10, color: C.sec }}>{ev.action?.replace(/_/g, ' ')} — {ev.by_name || 'System'} {ev.at ? `(${new Date(ev.at).toLocaleTimeString()})` : ''}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}

      {/* ═══ SLA Policy ═══ */}
      {tab === 'policy' && policy && (
        <View>
          {/* Enable/Disable */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 14, borderWidth: 1, borderColor: C.border }} data-testid="escalation-policy-card" testID="escalation-policy-card">
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="shield-checkmark" size={18} color={policy.enabled ? C.green : C.red} />
                <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{tx('admin.escalationPanel.auto.text.007', 'Escalation Engine')}</Text>
              </View>
              <TouchableOpacity onPress={() => savePolicy({ enabled: !policy.enabled })} disabled={saving} style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: policy.enabled ? (globalThis as any).__alphaColor(C.green, '15') : C.red + '10', borderWidth: 1, borderColor: policy.enabled ? (globalThis as any).__alphaColor(C.green, '30') : C.red + '20' }} data-testid="toggle-escalation-btn" testID="toggle-escalation-btn">
                <Text style={{ fontSize: 12, fontWeight: '800', color: policy.enabled ? C.green : C.red }}>{policy.enabled ? 'ENABLED' : 'DISABLED'}</Text>
              </TouchableOpacity>
            </View>

            {/* SLA Thresholds */}
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.muted, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.escalationPanel.auto.text.008', 'SLA Response Thresholds (minutes)')}</Text>
            <View style={{ gap: 8, marginBottom: 16 }}>
              {/* Header */}
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <View style={{ width: 80 }} />
                {['L1 Warning', 'L2 Urgent', 'L3 Critical'].map(h => (
                  <View key={h} style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ fontSize: 9, fontWeight: '800', color: h.includes('L1') ? C.yellow : h.includes('L2') ? C.orange : C.red, textTransform: 'uppercase' }}>{h}</Text>
                  </View>
                ))}
              </View>
              {PRIO_KEYS.map(prio => (
                <View key={prio} style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                  <View style={{ width: 80, paddingVertical: 8 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: C.text, textTransform: 'capitalize' }}>{prio}</Text>
                  </View>
                  {['l1', 'l2', 'l3'].map(level => (
                    <View key={level} style={{ flex: 1 }}>
                      <TextInput accessibilityLabel={tx('admin.escalationPanel.auto.accessibility.001', 'Text input')}
                        value={String(policy.sla_thresholds?.[prio]?.[level] || '')}
                        onEndEditing={(e) => updateThreshold(prio, level, e.nativeEvent.text)}
                        keyboardType="numeric"
                        style={{ backgroundColor: C.bg, borderRadius: 8, padding: 10, color: C.text, fontSize: 12, fontWeight: '700', textAlign: 'center', borderWidth: 1, borderColor: C.border }}
                        data-testid={`sla-${prio}-${level}`} testID={`sla-${prio}-${level}`}
                      />
                    </View>
                  ))}
                </View>
              ))}
            </View>

            {/* Notification channels per level */}
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.muted, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.escalationPanel.auto.text.009', 'Notification Channels')}</Text>
            <View style={{ gap: 6, marginBottom: 16 }}>
              {['l1', 'l2', 'l3'].map(level => {
                const lc = level === 'l1' ? C.yellow : level === 'l2' ? C.orange : C.red;
                const notifs = policy.notifications?.[level] || {};
                return (
                  <View key={level} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.bg, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border }}>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(lc, '18') }}>
                      <Text style={{ fontSize: 10, fontWeight: '800', color: lc }}>{level.toUpperCase()}</Text>
                    </View>
                    <TouchableOpacity onPress={() => {
                      const n = { ...policy.notifications };
                      n[level] = { ...n[level], websocket: !notifs.websocket };
                      savePolicy({ notifications: n });
                    }} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: notifs.websocket ? (globalThis as any).__alphaColor(C.blue, '15') : C.bg, borderWidth: 1, borderColor: notifs.websocket ? (globalThis as any).__alphaColor(C.blue, '25') : C.border }} data-testid={`notif-ws-${level}`} testID={`notif-ws-${level}`}>
                      <Ionicons name="flash" size={12} color={notifs.websocket ? C.blue : C.muted} />
                      <Text style={{ fontSize: 10, fontWeight: '700', color: notifs.websocket ? C.blue : C.muted }}>{tx('admin.escalationPanel.auto.text.010', 'WebSocket')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => {
                      const n = { ...policy.notifications };
                      n[level] = { ...n[level], email: !notifs.email };
                      savePolicy({ notifications: n });
                    }} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: notifs.email ? (globalThis as any).__alphaColor(C.purple, '15') : C.bg, borderWidth: 1, borderColor: notifs.email ? (globalThis as any).__alphaColor(C.purple, '25') : C.border }} data-testid={`notif-email-${level}`} testID={`notif-email-${level}`}>
                      <Ionicons name="mail" size={12} color={notifs.email ? C.purple : C.muted} />
                      <Text style={{ fontSize: 10, fontWeight: '700', color: notifs.email ? C.purple : C.muted }}>{tx('admin.escalationPanel.auto.text.011', 'Email')}</Text>
                    </TouchableOpacity>
                  </View>
                );
              })}
            </View>

            {/* Advanced */}
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity onPress={() => savePolicy({ business_hours_only: !policy.business_hours_only })} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, padding: 12, borderRadius: 10, backgroundColor: policy.business_hours_only ? (globalThis as any).__alphaColor(C.indigo, '10') : C.bg, borderWidth: 1, borderColor: policy.business_hours_only ? (globalThis as any).__alphaColor(C.indigo, '25') : C.border }} data-testid="business-hours-toggle" testID="business-hours-toggle">
                <Ionicons name="time" size={14} color={policy.business_hours_only ? C.indigo : C.muted} />
                <View>
                  <Text style={{ fontSize: 11, fontWeight: '700', color: policy.business_hours_only ? C.indigo : C.muted }}>{tx('admin.escalationPanel.auto.text.012', 'Business Hours Only')}</Text>
                  <Text style={{ fontSize: 9, color: C.muted }}>{policy.business_hours?.start || 9}:00 - {policy.business_hours?.end || 18}:00 UTC</Text>
                </View>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => savePolicy({ auto_reassign_on_l3: !policy.auto_reassign_on_l3 })} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, padding: 12, borderRadius: 10, backgroundColor: policy.auto_reassign_on_l3 ? (globalThis as any).__alphaColor(C.orange, '10') : C.bg, borderWidth: 1, borderColor: policy.auto_reassign_on_l3 ? (globalThis as any).__alphaColor(C.orange, '25') : C.border }} data-testid="auto-reassign-toggle" testID="auto-reassign-toggle">
                <Ionicons name="swap-horizontal" size={14} color={policy.auto_reassign_on_l3 ? C.orange : C.muted} />
                <View>
                  <Text style={{ fontSize: 11, fontWeight: '700', color: policy.auto_reassign_on_l3 ? C.orange : C.muted }}>{tx('admin.escalationPanel.auto.text.013', 'Auto-Reassign on L3')}</Text>
                  <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.escalationPanel.auto.text.014', 'Switch agent on SLA breach')}</Text>
                </View>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      {/* ═══ Analytics ═══ */}
      {tab === 'analytics' && analytics && (
        <View style={{ gap: 12 }}>
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }} data-testid="escalation-analytics-card" testID="escalation-analytics-card">
            <Text style={{ fontSize: 14, fontWeight: '800', color: C.text, marginBottom: 14 }}>{tx('admin.escalationPanel.auto.text.015', 'Escalation Metrics')}</Text>
            <View style={{ gap: 12 }}>
              {[
                { l: 'Total Ever Escalated', v: analytics.total_escalated, c: C.orange, icon: 'trending-up' },
                { l: 'Currently Active', v: analytics.active_escalated, c: C.red, icon: 'flame' },
                { l: 'Successfully De-escalated', v: analytics.de_escalated, c: C.green, icon: 'checkmark-circle' },
                { l: 'Events (Last 24h)', v: analytics.recent_events_24h, c: C.blue, icon: 'time' },
                { l: 'Avg Time to Escalation', v: `${analytics.avg_minutes_to_escalation}min`, c: C.cyan, icon: 'speedometer' },
                { l: 'SLA Breach Rate (L3)', v: `${analytics.sla_breach_rate}%`, c: analytics.sla_breach_rate > 10 ? C.red : C.green, icon: 'shield' },
              ].map(m => (
                <View key={m.l} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(m.c, '10'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={m.icon as any} size={16} color={m.c} />
                    </View>
                    <Text style={{ fontSize: 12, color: C.sec }}>{m.l}</Text>
                  </View>
                  <Text style={{ fontSize: 18, fontWeight: '800', color: m.c }}>{m.v}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Level distribution */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 14, fontWeight: '800', color: C.text, marginBottom: 14 }}>{tx('admin.escalationPanel.auto.text.016', 'Active by Level')}</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {[
                { l: 'L1', v: analytics.by_level?.l1 || 0, c: C.yellow },
                { l: 'L2', v: analytics.by_level?.l2 || 0, c: C.orange },
                { l: 'L3', v: analytics.by_level?.l3 || 0, c: C.red },
              ].map(b => {
                const total = Math.max(1, (analytics.by_level?.l1 || 0) + (analytics.by_level?.l2 || 0) + (analytics.by_level?.l3 || 0));
                const pct = (b.v / total) * 100;
                return (
                  <View key={b.l} style={{ flex: 1, alignItems: 'center' }}>
                    <View style={{ width: '100%', height: 80, backgroundColor: C.bg, borderRadius: 8, justifyContent: 'flex-end', overflow: 'hidden', marginBottom: 6 }}>
                      <View style={{ width: '100%', height: `${Math.max(5, pct)}%`, backgroundColor: (globalThis as any).__alphaColor(b.c, '30'), borderRadius: 4 }} />
                    </View>
                    <Text style={{ fontSize: 18, fontWeight: '800', color: b.c }}>{b.v}</Text>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: b.c }}>{b.l}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        </View>
      )}

      {/* ═══ Audit Trail ═══ */}
      {tab === 'audit' && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }} data-testid="escalation-audit-trail" testID="escalation-audit-trail">
          <Text style={{ fontSize: 14, fontWeight: '800', color: C.text, marginBottom: 14 }}>{tx('admin.escalationPanel.auto.text.017', 'Escalation Audit Trail')}</Text>
          {history.length === 0 ? (
            <View style={{ padding: 30, alignItems: 'center' }}>
              <Ionicons name="document-text-outline" size={40} color={C.border} />
              <Text style={{ color: C.muted, marginTop: 8, fontSize: 12 }}>{tx('admin.escalationPanel.auto.text.018', 'No escalation events yet')}</Text>
            </View>
          ) : (
            <View style={{ gap: 1 }}>
              {history.map((ev, i) => {
                const isEscalation = ev.action?.includes('escalated_to');
                const isDeescalation = ev.action === 'de_escalated';
                const isSnoozed = ev.action === 'snoozed';
                const ec = isDeescalation ? C.green : isSnoozed ? C.blue : isEscalation ? C.red : C.muted;
                return (
                  <View key={ev.event_id || i} style={{ flexDirection: 'row', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }} data-testid={`audit-event-${i}`} testID={`audit-event-${i}`}>
                    <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(ec, '12'), alignItems: 'center', justifyContent: 'center', marginTop: 2 }}>
                      <Ionicons name={isDeescalation ? 'checkmark' : isSnoozed ? 'time' : 'arrow-up'} size={14} color={ec} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <Text style={{ fontSize: 11, fontWeight: '700', color: ec }}>{ev.action?.replace(/_/g, ' ').toUpperCase()}</Text>
                        {ev.priority && <Text style={{ fontSize: 9, fontWeight: '700', color: C.muted, textTransform: 'uppercase', backgroundColor: C.bg, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 3 }}>{ev.priority}</Text>}
                      </View>
                      <Text style={{ fontSize: 11, color: C.sec }}>Ticket: {ev.ticket_number || ev.ticket_id?.slice(0, 12)}</Text>
                      {ev.subject && <Text style={{ fontSize: 10, color: C.muted }} numberOfLines={1}>{ev.subject}</Text>}
                      {ev.elapsed_minutes && <Text style={{ fontSize: 10, color: C.muted }}>After {Math.round(ev.elapsed_minutes)}min without response</Text>}
                      {ev.assigned_agent_name && <Text style={{ fontSize: 10, color: C.muted }}>Agent: {ev.assigned_agent_name}</Text>}
                      {ev.reason && <Text style={{ fontSize: 10, color: C.muted }}>Reason: {ev.reason}</Text>}
                      <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{ev.at ? new Date(ev.at).toLocaleString() : ''}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}
    </View>
  );
}
