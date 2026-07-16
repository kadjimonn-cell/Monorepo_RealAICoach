import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, useWindowDimensions, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);
const TOPICS = ['billing', 'technical', 'account', 'feature_request', 'bug_report', 'general'];
const TOPIC_COLORS: any = { billing: C.green, technical: C.blue, account: C.indigo, feature_request: C.purple, bug_report: C.red, general: C.muted };
const TOPIC_ICONS: any = { billing: 'card', technical: 'code-slash', account: 'person', feature_request: 'bulb', bug_report: 'bug', general: 'help-circle' };

const tx = (_key: string, fallback: string) => fallback;

export default function TicketAssignmentPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const { width } = useWindowDimensions();
  const isWide = width >= 900;

  const [tab, setTab] = useState<'agents' | 'rules' | 'stats'>('agents');
  const { data: agentsData, loading: agentsLoading, refetch: refetchAgents } = useLiveQuery('/admin/manage/support-agents', { entity: 'ticket_assignment', pollInterval: 30000 });
  const { data: statsData, refetch: refetchStats } = useLiveQuery('/admin/manage/assignment-stats', { entity: 'ticket_assignment', pollInterval: 30000 });
  const { data: rulesData, refetch: refetchRules } = useLiveQuery('/admin/manage/assignment-rules', { entity: 'ticket_assignment', pollInterval: 60000 });

  const agents = agentsData?.agents || [];
  const stats = statsData || null;
  const rules = rulesData || null;
  const loading = agentsLoading;

  const loadAll = useCallback(async () => {
    await Promise.all([refetchAgents(), refetchStats(), refetchRules()]);
  }, [refetchAgents, refetchStats, refetchRules]);
  const [editAgent, setEditAgent] = useState<any>(null);
  const [formName, setFormName] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formTopics, setFormTopics] = useState<string[]>([]);
  const [formMaxConcurrent, setFormMaxConcurrent] = useState('10');
  const [saving, setSaving] = useState(false);

  // Agent form
  const [showForm, setShowForm] = useState(false);
  const [autoAssigning, setAutoAssigning] = useState(false);

  const resetForm = () => {
    setFormName(''); setFormEmail(''); setFormTopics([]); setFormMaxConcurrent('10');
    setEditAgent(null); setShowForm(false);
  };

  const openEdit = (agent: any) => {
    setEditAgent(agent);
    setFormName(agent.name);
    setFormEmail(agent.email);
    setFormTopics(agent.topics || []);
    setFormMaxConcurrent(String(agent.max_concurrent || 10));
    setShowForm(true);
  };

  const saveAgent = async () => {
    if (!formName.trim() || !formEmail.trim()) return;
    setSaving(true);
    try {
      if (editAgent) {
        await api.put(`/admin/manage/support-agents/${editAgent.agent_id}`, {
          name: formName, email: formEmail, topics: formTopics, max_concurrent: parseInt(formMaxConcurrent) || 10,
        });
      } else {
        await api.post('/admin/manage/support-agents', {
          name: formName, email: formEmail, topics: formTopics, max_concurrent: parseInt(formMaxConcurrent) || 10,
        });
      }
      resetForm();
      await loadAll();
    } catch (e: any) { Alert.alert(tx('admin.ticketAssignmentPanel.auto.alert.error', 'Error'), e?.response?.data?.detail || tx('admin.ticketAssignmentPanel.auto.alert.saveFailed', 'Save failed')); }
    setSaving(false);
  };

  const deleteAgent = async (agentId: string) => {
    try {
      await api.delete(`/admin/manage/support-agents/${agentId}`);
      await loadAll();
    } catch (e: any) { Alert.alert(tx('admin.ticketAssignmentPanel.auto.alert.error', 'Error'), e?.response?.data?.detail || tx('admin.ticketAssignmentPanel.auto.alert.deleteFailed', 'Delete failed')); }
  };

  const toggleAvailability = async (agent: any) => {
    try {
      await api.put(`/admin/manage/support-agents/${agent.agent_id}`, { is_available: !agent.is_available });
      await loadAll();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketAssignmentPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const toggleTopic = (topic: string) => {
    setFormTopics(prev => prev.includes(topic) ? prev.filter(t => t !== topic) : [...prev, topic]);
  };

  const saveRules = async (updates: any) => {
    try {
      await api.post('/admin/manage/assignment-rules', { ...rules, ...updates });
      const res = await api.get('/admin/manage/assignment-rules');
      setRules(res.data);
    } catch (e: any) { Alert.alert(tx('admin.ticketAssignmentPanel.auto.alert.error', 'Error'), e?.response?.data?.detail || tx('admin.ticketAssignmentPanel.auto.alert.saveFailed', 'Save failed')); }
  };

  const triggerAutoAssign = async () => {
    setAutoAssigning(true);
    try {
      const res = await api.post('/admin/manage/tickets/auto-assign');
      Alert.alert(
        tx('admin.ticketAssignmentPanel.auto.alert.autoAssignmentComplete', 'Auto-Assignment Complete'),
        tx('admin.ticketAssignmentPanel.auto.alert.autoAssignmentMessage', '{assigned} tickets assigned out of {total} unassigned.')
          .replace('{assigned}', String(res.data.assigned))
          .replace('{total}', String(res.data.total_unassigned))
      );
      await loadAll();
    } catch (e: any) { Alert.alert(tx('admin.ticketAssignmentPanel.auto.alert.error', 'Error'), e?.response?.data?.detail || tx('admin.ticketAssignmentPanel.auto.alert.autoAssignFailed', 'Auto-assign failed')); }
    setAutoAssigning(false);
  };

  if (loading) return <ActivityIndicator color={C.blue} style={{ padding: 40 }} />;

  return (
    <View data-testid="ticket-assignment-panel" testID="ticket-assignment-panel">
      <AutoFixBanner domain="ticket_assignment" />
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.cyan, '15'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="git-branch" size={20} color={C.cyan} />
          </View>
          <View>
            <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }}>{tx('admin.ticketAssignmentPanel.auto.text.001', 'Ticket Assignment')}</Text>
            <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.ticketAssignmentPanel.auto.text.002', 'AI-powered auto-assignment engine')}</Text>
          </View>
        </View>
        <TouchableOpacity onPress={loadAll} style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center' }} data-testid="assignment-refresh-btn" testID="assignment-refresh-btn">
          <Ionicons name="refresh" size={16} color={C.blue} />
        </TouchableOpacity>
      </View>

      {/* Quick Stats Bar */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        {[
          { l: 'Agents', v: stats?.total_agents || 0, c: C.blue, icon: 'people' },
          { l: 'Available', v: stats?.available_agents || 0, c: C.green, icon: 'checkmark-circle' },
          { l: 'Unassigned', v: stats?.unassigned_tickets || 0, c: C.yellow, icon: 'alert-circle' },
          { l: 'Engine', v: rules?.enabled ? 'ON' : 'OFF', c: rules?.enabled ? C.green : C.red, icon: 'flash' },
        ].map(s => (
          <View key={s.l} style={{ flex: 1, minWidth: 80, backgroundColor: (globalThis as any).__alphaColor(s.c, '08'), borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.c, '18') }}>
            <Ionicons name={s.icon as any} size={16} color={s.c} style={{ marginBottom: 4 }} />
            <Text style={{ fontSize: 20, fontWeight: '800', color: s.c, letterSpacing: -0.5 }}>{s.v}</Text>
            <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginTop: 2 }}>{s.l}</Text>
          </View>
        ))}
      </View>

      {/* Tab Bar */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {([
          { key: 'agents', label: 'Support Agents', icon: 'people' },
          { key: 'rules', label: 'Assignment Rules', icon: 'settings' },
          { key: 'stats', label: 'Workload Stats', icon: 'bar-chart' },
        ] as const).map(t => (
          <TouchableOpacity key={t.key} onPress={() => setTab(t.key)} style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 11, borderRadius: 10, backgroundColor: tab === t.key ? (globalThis as any).__alphaColor(C.blue, '15') : C.card, borderWidth: 1, borderColor: tab === t.key ? (globalThis as any).__alphaColor(C.blue, '30') : C.border }} data-testid={`assignment-tab-${t.key}`} testID={`assignment-tab-${t.key}`}>
            <Ionicons name={t.icon as any} size={15} color={tab === t.key ? C.blue : C.muted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: tab === t.key ? C.blue : C.muted }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ═══ Agents Tab ═══ */}
      {tab === 'agents' && (
        <View>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>Support Agents ({agents.length})</Text>
            <TouchableOpacity onPress={() => { resetForm(); setShowForm(true); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '30') }} data-testid="add-agent-btn" testID="add-agent-btn">
              <Ionicons name="add" size={16} color={C.blue} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.blue }}>{tx('admin.ticketAssignmentPanel.auto.text.003', 'Add Agent')}</Text>
            </TouchableOpacity>
          </View>

          {/* Agent Form */}
          {showForm && (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '30') }} data-testid="agent-form" testID="agent-form">
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }}>{editAgent ? 'Edit Agent' : 'New Agent'}</Text>
                <TouchableOpacity onPress={resetForm} data-testid="close-agent-form" testID="close-agent-form">
                  <Ionicons name="close" size={18} color={C.muted} />
                </TouchableOpacity>
              </View>
              <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 10, marginBottom: 12 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, marginBottom: 4, textTransform: 'uppercase' }}>{tx('admin.ticketAssignmentPanel.auto.text.004', 'Name')}</Text>
                  <TextInput value={formName} onChangeText={setFormName} placeholder={tx('admin.ticketAssignmentPanel.auto.placeholder.001', 'Agent name...')} placeholderTextColor={C.muted} style={{ backgroundColor: C.bg, borderRadius: 8, padding: 12, color: C.text, fontSize: 13, borderWidth: 1, borderColor: C.border }} data-testid="agent-name-input" testID="agent-name-input" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, marginBottom: 4, textTransform: 'uppercase' }}>{tx('admin.ticketAssignmentPanel.auto.text.005', 'Email')}</Text>
                  <TextInput value={formEmail} onChangeText={setFormEmail} placeholder={tx('admin.ticketAssignmentPanel.auto.placeholder.002', 'agent@email.com')} placeholderTextColor={C.muted} style={{ backgroundColor: C.bg, borderRadius: 8, padding: 12, color: C.text, fontSize: 13, borderWidth: 1, borderColor: C.border }} data-testid="agent-email-input" testID="agent-email-input" />
                </View>
                <View style={{ width: isWide ? 100 : '100%' }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, marginBottom: 4, textTransform: 'uppercase' }}>{tx('admin.ticketAssignmentPanel.auto.text.006', 'Max Load')}</Text>
                  <TextInput value={formMaxConcurrent} onChangeText={setFormMaxConcurrent} keyboardType="numeric" style={{ backgroundColor: C.bg, borderRadius: 8, padding: 12, color: C.text, fontSize: 13, borderWidth: 1, borderColor: C.border }} data-testid="agent-max-load-input" testID="agent-max-load-input" accessibilityLabel={tx('admin.ticketAssignmentPanel.auto.accessibility.001', 'Topic Specialties')} />
                </View>
              </View>
              <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, marginBottom: 6, textTransform: 'uppercase' }}>{tx('admin.ticketAssignmentPanel.auto.text.007', 'Topic Specialties')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
                {TOPICS.map(topic => {
                  const active = formTopics.includes(topic);
                  const tc = TOPIC_COLORS[topic] || C.muted;
                  return (
                    <TouchableOpacity key={topic} onPress={() => toggleTopic(topic)} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: active ? (globalThis as any).__alphaColor(tc, '20') : C.bg, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(tc, '40') : C.border }} data-testid={`topic-toggle-${topic}`} testID={`topic-toggle-${topic}`}>
                      <Ionicons name={(TOPIC_ICONS[topic] || 'help-circle') as any} size={13} color={active ? tc : C.muted} />
                      <Text style={{ fontSize: 11, fontWeight: '700', color: active ? tc : C.muted }}>{topic.replace(/_/g, ' ')}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
              <TouchableOpacity onPress={saveAgent} disabled={saving} style={{ backgroundColor: saving ? C.border : C.blue, borderRadius: 10, padding: 12, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }} data-testid="save-agent-btn" testID="save-agent-btn">
                {saving ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="checkmark" size={16} color="var(--app-primary-text)" />}
                <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 13 }}>{editAgent ? 'Update Agent' : 'Create Agent'}</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Agent List */}
          {agents.length === 0 ? (
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 40, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="people-outline" size={40} color={C.border} />
              <Text style={{ color: C.muted, marginTop: 10, fontSize: 13 }}>{tx('admin.ticketAssignmentPanel.auto.text.008', 'No agents configured yet')}</Text>
              <Text style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>{tx('admin.ticketAssignmentPanel.auto.text.009', 'Add support agents to enable ticket assignment')}</Text>
            </View>
          ) : (
            <View style={{ gap: 8 }}>
              {agents.map(agent => {
                const load = agent.current_load || 0;
                const max = agent.max_concurrent || 10;
                const pct = Math.min(100, (load / max) * 100);
                const loadColor = pct >= 80 ? C.red : pct >= 50 ? C.yellow : C.green;

                return (
                  <View key={agent.agent_id} style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(agent.is_available ? C.border : C.red, '20') }} data-testid={`agent-card-${agent.agent_id}`} testID={`agent-card-${agent.agent_id}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                        <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: agent.is_available ? (globalThis as any).__alphaColor(C.blue, '15') : C.red + '10', alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name="person" size={18} color={agent.is_available ? C.blue : C.red} />
                        </View>
                        <View>
                          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{agent.name}</Text>
                          <Text style={{ fontSize: 11, color: C.muted }}>{agent.email}</Text>
                        </View>
                      </View>
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        <TouchableOpacity onPress={() => toggleAvailability(agent)} style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: agent.is_available ? (globalThis as any).__alphaColor(C.green, '12') : C.red + '12', alignItems: 'center', justifyContent: 'center' }} data-testid={`toggle-avail-${agent.agent_id}`} testID={`toggle-avail-${agent.agent_id}`}>
                          <Ionicons name={agent.is_available ? 'checkmark-circle' : 'close-circle'} size={16} color={agent.is_available ? C.green : C.red} />
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => openEdit(agent)} style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.blue, '12'), alignItems: 'center', justifyContent: 'center' }} data-testid={`edit-agent-${agent.agent_id}`} testID={`edit-agent-${agent.agent_id}`}>
                          <Ionicons name="create" size={14} color={C.blue} />
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => deleteAgent(agent.agent_id)} style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.red, '08'), alignItems: 'center', justifyContent: 'center' }} data-testid={`delete-agent-${agent.agent_id}`} testID={`delete-agent-${agent.agent_id}`}>
                          <Ionicons name="trash" size={14} color={C.red} />
                        </TouchableOpacity>
                      </View>
                    </View>
                    {/* Topics */}
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 10 }}>
                      {(agent.topics || []).map((t: string) => (
                        <View key={t} style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor((TOPIC_COLORS[t] || C.muted), '12'), borderRadius: 6, paddingHorizontal: 7, paddingVertical: 3 }}>
                          <Ionicons name={(TOPIC_ICONS[t] || 'help-circle') as any} size={10} color={TOPIC_COLORS[t] || C.muted} />
                          <Text style={{ fontSize: 10, fontWeight: '600', color: TOPIC_COLORS[t] || C.muted }}>{t.replace(/_/g, ' ')}</Text>
                        </View>
                      ))}
                      {(agent.topics || []).length === 0 && <Text style={{ fontSize: 10, color: C.muted, fontStyle: 'italic' }}>{tx('admin.ticketAssignmentPanel.auto.text.010', 'No topics assigned')}</Text>}
                    </View>
                    {/* Workload bar */}
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <View style={{ flex: 1, height: 6, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
                        <View style={{ width: `${pct}%`, height: '100%', backgroundColor: loadColor, borderRadius: 3 }} />
                      </View>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: loadColor }}>{load}/{max}</Text>
                      <View style={{ backgroundColor: agent.is_available ? (globalThis as any).__alphaColor(C.green, '15') : C.red + '15', borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}>
                        <Text style={{ fontSize: 9, fontWeight: '800', color: agent.is_available ? C.green : C.red }}>{agent.is_available ? 'ONLINE' : 'OFFLINE'}</Text>
                      </View>
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}

      {/* ═══ Rules Tab ═══ */}
      {tab === 'rules' && (
        <View>
          {/* Enable Toggle */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 14, borderWidth: 1, borderColor: C.border }} data-testid="assignment-rules-card" testID="assignment-rules-card">
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="flash" size={18} color={rules?.enabled ? C.green : C.red} />
                <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{tx('admin.ticketAssignmentPanel.auto.text.011', 'Auto-Assignment Engine')}</Text>
              </View>
              <TouchableOpacity onPress={() => saveRules({ enabled: !rules?.enabled })} style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: rules?.enabled ? (globalThis as any).__alphaColor(C.green, '15') : C.red + '10', borderWidth: 1, borderColor: rules?.enabled ? (globalThis as any).__alphaColor(C.green, '30') : C.red + '20' }} data-testid="toggle-assignment-btn" testID="toggle-assignment-btn">
                <Text style={{ fontSize: 12, fontWeight: '800', color: rules?.enabled ? C.green : C.red }}>{rules?.enabled ? 'ENABLED' : 'DISABLED'}</Text>
              </TouchableOpacity>
            </View>

            {/* Strategy */}
            <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.ticketAssignmentPanel.auto.text.012', 'Assignment Strategy')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
              {[
                { key: 'round_robin', label: 'Round Robin', desc: 'Distribute evenly across agents', icon: 'sync' },
                { key: 'least_loaded', label: 'Least Loaded', desc: 'Assign to agent with fewest tickets', icon: 'trending-down' },
              ].map(s => (
                <TouchableOpacity key={s.key} onPress={() => saveRules({ strategy: s.key })} style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: rules?.strategy === s.key ? (globalThis as any).__alphaColor(C.blue, '10') : C.bg, borderWidth: 1, borderColor: rules?.strategy === s.key ? (globalThis as any).__alphaColor(C.blue, '30') : C.border }} data-testid={`strategy-${s.key}`} testID={`strategy-${s.key}`}>
                  <Ionicons name={s.icon as any} size={18} color={rules?.strategy === s.key ? C.blue : C.muted} style={{ marginBottom: 6 }} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: rules?.strategy === s.key ? C.blue : C.text }}>{s.label}</Text>
                  <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{s.desc}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* How it works */}
            <View style={{ backgroundColor: C.bg, borderRadius: 10, padding: 14 }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: C.cyan, marginBottom: 8 }}>{tx('admin.ticketAssignmentPanel.auto.text.013', 'How Auto-Assignment Works')}</Text>
              {[
                'When a new ticket is submitted, AI classifies it by topic',
                'The engine finds agents who specialize in that topic',
                'It picks the best agent based on the selected strategy',
                'If no specialist is available, it falls back to any available agent',
                'Agents at max capacity are skipped',
              ].map((step, i) => (
                <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: 5 }}>
                  <View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: (globalThis as any).__alphaColor(C.cyan, '15'), alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ fontSize: 9, fontWeight: '800', color: C.cyan }}>{i + 1}</Text>
                  </View>
                  <Text style={{ flex: 1, fontSize: 11, color: C.sec, lineHeight: 16 }}>{step}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Manual trigger */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Ionicons name="play-circle" size={18} color={C.orangeText} />
              <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }}>{tx('admin.ticketAssignmentPanel.auto.text.014', 'Manual Trigger')}</Text>
            </View>
            <Text style={{ fontSize: 12, color: C.muted, marginBottom: 14 }}>
              Run auto-assignment on all currently unassigned tickets. This will assign {stats?.unassigned_tickets || 0} unassigned ticket(s) to available agents.
            </Text>
            <TouchableOpacity onPress={triggerAutoAssign} disabled={autoAssigning || !rules?.enabled} style={{ backgroundColor: autoAssigning || !rules?.enabled ? C.border : C.orange, borderRadius: 10, padding: 13, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }} data-testid="trigger-auto-assign-btn" testID="trigger-auto-assign-btn">
              {autoAssigning ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="flash" size={16} color="var(--app-primary-text)" />}
              <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 13 }}>{autoAssigning ? 'Assigning...' : 'Run Auto-Assignment Now'}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* ═══ Stats Tab ═══ */}
      {tab === 'stats' && stats && (
        <View>
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 14, borderWidth: 1, borderColor: C.border }} data-testid="workload-stats-card" testID="workload-stats-card">
            <Text style={{ fontSize: 14, fontWeight: '800', color: C.text, marginBottom: 14 }}>{tx('admin.ticketAssignmentPanel.auto.text.015', 'Agent Workload Distribution')}</Text>
            {(stats.agents || []).length === 0 ? (
              <View style={{ padding: 30, alignItems: 'center' }}>
                <Ionicons name="people-outline" size={40} color={C.border} />
                <Text style={{ color: C.muted, marginTop: 10, fontSize: 13 }}>{tx('admin.ticketAssignmentPanel.auto.text.016', 'No agents to show')}</Text>
              </View>
            ) : (stats.agents || []).map((agent: any) => {
              const loadColor = agent.utilization >= 80 ? C.red : agent.utilization >= 50 ? C.yellow : C.green;
              return (
                <View key={agent.agent_id} style={{ marginBottom: 14, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: C.border }} data-testid={`stat-agent-${agent.agent_id}`} testID={`stat-agent-${agent.agent_id}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: agent.is_available ? C.green : C.red }} />
                      <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{agent.name}</Text>
                    </View>
                    <Text style={{ fontSize: 11, fontWeight: '800', color: loadColor }}>{agent.utilization}%</Text>
                  </View>
                  {/* Progress bar */}
                  <View style={{ height: 8, backgroundColor: C.border, borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                    <View style={{ width: `${Math.min(100, agent.utilization)}%`, height: '100%', backgroundColor: loadColor, borderRadius: 4 }} />
                  </View>
                  <View style={{ flexDirection: 'row', gap: 12 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.yellow }} />
                      <Text style={{ fontSize: 10, color: C.muted }}>Open: <Text style={{ fontWeight: '700', color: C.text }}>{agent.open_tickets}</Text></Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.green }} />
                      <Text style={{ fontSize: 10, color: C.muted }}>Resolved: <Text style={{ fontWeight: '700', color: C.text }}>{agent.resolved_tickets}</Text></Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.blue }} />
                      <Text style={{ fontSize: 10, color: C.muted }}>Total: <Text style={{ fontWeight: '700', color: C.text }}>{agent.total_assigned}</Text></Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Ionicons name="speedometer" size={10} color={C.muted} />
                      <Text style={{ fontSize: 10, color: C.muted }}>Max: <Text style={{ fontWeight: '700', color: C.text }}>{agent.max_concurrent}</Text></Text>
                    </View>
                  </View>
                  {/* Topics */}
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 3, marginTop: 8 }}>
                    {(agent.topics || []).map((t: string) => (
                      <View key={t} style={{ backgroundColor: (globalThis as any).__alphaColor((TOPIC_COLORS[t] || C.muted), '10'), borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}>
                        <Text style={{ fontSize: 9, fontWeight: '600', color: TOPIC_COLORS[t] || C.muted }}>{t.replace(/_/g, ' ')}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              );
            })}
          </View>
        </View>
      )}
    </View>
  );
}
