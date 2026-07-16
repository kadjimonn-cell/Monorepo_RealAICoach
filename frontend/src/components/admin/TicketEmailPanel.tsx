import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, Switch } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface Props { colors: any }

type Tab = 'inbox' | 'config' | 'templates' | 'routing';

export default function TicketEmailPanel({ colors: _colors }: Props) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [tab, setTab] = useState<Tab>('inbox');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedTicket, setSelectedTicket] = useState<any>(null);
  const [replyText, setReplyText] = useState('');
  const [noteText, setNoteText] = useState('');
  const [saving, setSaving] = useState(false);
  const [reclassifying, setReclassifying] = useState('');
  const [msg, setMsg] = useState({ text: '', type: '' });
  const [editingTemplate, setEditingTemplate] = useState<string | null>(null);
  const [templateDraft, setTemplateDraft] = useState<any>({});
  const [editingRule, setEditingRule] = useState<string | null>(null);
  const [ruleDraft, setRuleDraft] = useState<any>({});
  const [config, setConfig] = useState<any>(null);

  const C = colors;
  const panelTitle = t('ticketEmail.header.title');

  const { data: statsData, loading: statsLoading, refetch: refetchStats } = useLiveQuery('/admin/ticket-email/stats', { entity: 'ticket_email', pollInterval: 30000 });
  const { data: inboxData, refetch: refetchInbox } = useLiveQuery(`/admin/ticket-email/inbox?status=${statusFilter}`, { entity: 'ticket_email', pollInterval: 30000, deps: [statusFilter] });
  const { data: configData, refetch: refetchConfig } = useLiveQuery('/admin/ticket-email/config', { entity: 'ticket_email', pollInterval: 60000 });
  const { data: templatesData, refetch: refetchTemplates } = useLiveQuery('/admin/ticket-email/templates', { entity: 'ticket_email', pollInterval: 60000 });
  const { data: routingData } = useLiveQuery('/admin/ticket-email/routing', { entity: 'ticket_email', pollInterval: 60000 });
  const { data: csatData } = useLiveQuery('/admin/ticket-email/csat-stats', { entity: 'ticket_email', pollInterval: 60000 });
  const { data: healthData } = useLiveQuery('/admin/ticket-email/email-health', { entity: 'ticket_email', pollInterval: 60000 });

  const stats = statsData || null;
  const tickets = inboxData?.tickets || [];
  const templates = templatesData?.templates || [];
  const routingRules = routingData?.rules || {};
  const csatStats = csatData || null;
  const emailHealth = healthData || null;
  const loading = statsLoading;

  useEffect(() => { if (configData?.config) setConfig(configData.config); }, [configData]);
  const load = useCallback(async () => { await Promise.all([refetchStats(), refetchInbox(), refetchConfig(), refetchTemplates()]); }, [refetchStats, refetchInbox, refetchConfig, refetchTemplates]);
  useEffect(() => { if (msg.text) { const t = setTimeout(() => setMsg({ text: '', type: '' }), 4000); return () => clearTimeout(t); } }, [msg]);

  const saveConfig = async (updates: any) => {
    setSaving(true);
    try {
      await api.put('/admin/ticket-email/config', updates);
      setConfig({ ...config, ...updates });
      setMsg({ text: 'Config saved', type: 'success' });
    } catch { setMsg({ text: 'Failed to save config', type: 'error' }); }
    setSaving(false);
  };

  const updateTicket = async (ticketId: string, updates: any) => {
    try {
      await api.put(`/admin/ticket-email/ticket/${ticketId}`, updates);
      setMsg({ text: `Ticket ${ticketId} updated`, type: 'success' });
      load();
    } catch { setMsg({ text: 'Failed to update ticket', type: 'error' }); }
  };

  const sendReply = async (ticketId: string) => {
    if (!replyText.trim()) return;
    setSaving(true);
    try {
      await api.post(`/admin/ticket-email/ticket/${ticketId}/reply`, { message: replyText.trim() });
      setMsg({ text: 'Reply sent successfully', type: 'success' });
      setReplyText('');
      load();
    } catch { setMsg({ text: 'Failed to send reply', type: 'error' }); }
    setSaving(false);
  };

  const reclassifyTicket = async (ticketId: string) => {
    setReclassifying(ticketId);
    try {
      const res = await api.post(`/admin/ticket-email/reclassify/${ticketId}`);
      setMsg({ text: `Re-classified: ${res.data?.classification?.topic} / ${res.data?.classification?.priority}`, type: 'success' });
      load();
    } catch { setMsg({ text: 'Re-classification failed', type: 'error' }); }
    setReclassifying('');
  };

  const saveTemplate = async (templateId: string) => {
    setSaving(true);
    try {
      await api.put(`/admin/ticket-email/template/${templateId}`, templateDraft);
      setMsg({ text: 'Template saved', type: 'success' });
      setEditingTemplate(null);
      load();
    } catch { setMsg({ text: 'Failed to save template', type: 'error' }); }
    setSaving(false);
  };

  const saveRoutingRule = async (topic: string) => {
    setSaving(true);
    try {
      const updated = { ...routingRules, [topic]: ruleDraft };
      await api.put('/admin/ticket-email/routing', { rules: updated });
      setRoutingRules(updated);
      setEditingRule(null);
      setMsg({ text: `Route for "${topic}" saved`, type: 'success' });
    } catch { setMsg({ text: 'Failed to save routing', type: 'error' }); }
    setSaving(false);
  };

  if (loading) return <View style={{ paddingVertical: 60, alignItems: 'center' }}><ActivityIndicator size="large" color={C.primary} /></View>;

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'inbox', label: tx('ticketEmail.tabs.inbox', 'Inbox'), icon: 'mail' },
    { id: 'routing', label: tx('ticketEmail.tabs.aiRouting', 'AI Routing'), icon: 'git-branch' },
    { id: 'config', label: tx('ticketEmail.tabs.configuration', 'Configuration'), icon: 'settings' },
    { id: 'templates', label: tx('ticketEmail.tabs.templates', 'Templates'), icon: 'document-text' },
  ];

  const statusColors: Record<string, string> = {
    open: C.warning, new: C.primary, in_progress: C.cyan, 'in-progress': C.cyan,
    resolved: C.success, closed: C.textMuted,
  };

  const priorityColors: Record<string, string> = {
    critical: C.error, high: C.orange, medium: C.warning, low: C.textMuted,
  };

  const topicIcons: Record<string, string> = {
    billing: 'card', technical: 'code-slash', account: 'person', feature_request: 'bulb',
    bug_report: 'bug', general: 'chatbubbles',
  };

  const moodConfig: Record<string, { icon: string; color: string; label: string }> = {
    happy: { icon: 'happy', color: colors.successText, label: 'Happy' },
    neutral: { icon: 'remove-circle', color: colors.textMuted, label: 'Neutral' },
    confused: { icon: 'help-circle', color: colors.warningText, label: 'Confused' },
    frustrated: { icon: 'sad', color: colors.warningText, label: 'Frustrated' },
    angry: { icon: 'flame', color: colors.error, label: 'Angry' },
    desperate: { icon: 'warning', color: colors.error, label: 'Desperate' },
    disappointed: { icon: 'thumbs-down', color: colors.warningText, label: 'Disappointed' },
  };

  const getFrustrationBar = (level: number) => {
    const clr = level >= 7 ? C.error : level >= 5 ? C.orange : level >= 3 ? C.warning : C.success;
    return { width: `${level * 10}%`, color: clr };
  };

  return (
    <View data-testid="ticket-email-panel" testID="ticket-email-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30') }}>
            <Ionicons name="mail" size={22} color={C.primary} />
          </View>
          <View>
            <Text style={{ color: C.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.5 }} data-testid="ticket-email-title" testID="ticket-email-title">{panelTitle === 'ticketEmail.header.title' ? 'Ticket Email Management' : panelTitle}</Text>
            <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }}>{tx('ticketEmail.header.subtitle', 'AI-powered routing, templates & inbox')}</Text>
          </View>
        </View>
        <TouchableOpacity onPress={load} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="ticket-email-refresh" testID="ticket-email-refresh">
          <Ionicons name="refresh" size={14} color={C.textMuted} />
          <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('ticketEmail.actions.refresh', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* Status msg */}
      {msg.text ? (
        <View style={{ backgroundColor: msg.type === 'success' ? C.successSoft : C.errorSoft, borderRadius: 10, padding: 10, marginBottom: 12, flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: msg.type === 'success' ? C.successSoft : C.errorSoft }}>
          <Ionicons name={msg.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={16} color={msg.type === 'success' ? C.success : C.error} />
          <Text style={{ color: msg.type === 'success' ? C.success : C.error, fontSize: 12, flex: 1 }}>{msg.text}</Text>
        </View>
      ) : null}

      {/* Stats Strip */}
      {stats && (
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }} data-testid="ticket-stats-strip" testID="ticket-stats-strip">
          {[
            { label: tx('ticketEmail.stats.total', 'Total'), value: stats.total, color: C.primary, icon: 'documents' },
            { label: tx('ticketEmail.stats.open', 'Open'), value: stats.open, color: colors.warningText, icon: 'mail-open' },
            { label: tx('ticketEmail.stats.inProgress', 'In Progress'), value: stats.in_progress, color: colors.accent, icon: 'hourglass' },
            { label: tx('ticketEmail.stats.resolved', 'Resolved'), value: stats.resolved, color: colors.successText, icon: 'checkmark-done' },
          ].map((s, i) => (
            <View key={i} style={{ flex: 1, minWidth: 120, backgroundColor: C.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: s.color }} data-testid={`ticket-stat-${s.label.toLowerCase().replace(' ', '-')}`} testID={`ticket-stat-${s.label.toLowerCase().replace(' ', '-')}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Ionicons name={s.icon as any} size={14} color={s.color} />
                <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>{s.label}</Text>
              </View>
              <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }}>{s.value}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Email Health Alert */}
      {emailHealth && emailHealth.health !== 'healthy' && (
        <View style={{ backgroundColor: emailHealth.health === 'down' ? C.errorSoft : C.warningSoft, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: emailHealth.health === 'down' ? C.errorSoft : C.warningSoft, flexDirection: 'row', alignItems: 'center', gap: 12 }} data-testid="email-health-alert" testID="email-health-alert">
          <Ionicons name={emailHealth.health === 'down' ? 'warning' : 'alert-circle'} size={20} color={emailHealth.health === 'down' ? C.error : C.warning} />
          <View style={{ flex: 1 }}>
            <Text style={{ color: emailHealth.health === 'down' ? C.error : C.warning, fontSize: 13, fontWeight: '700' }}>
              Email Service {emailHealth.health === 'down' ? 'DOWN' : 'DEGRADED'} — {emailHealth.failed}/{emailHealth.total_recent} recent emails failed
            </Text>
            {emailHealth.last_error ? (
              <Text style={{ color: colors.warningText, fontSize: 10, marginTop: 2 }} numberOfLines={2}>
                {emailHealth.last_error}
              </Text>
            ) : null}
          </View>
        </View>
      )}

      {/* CSAT Score Card */}
      {csatStats && csatStats.total_ratings > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 14 }} data-testid="csat-stats-card" testID="csat-stats-card">
          <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: csatStats.satisfaction_score >= 70 ? C.successSoft : csatStats.satisfaction_score >= 40 ? C.warningSoft : C.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ color: csatStats.satisfaction_score >= 70 ? C.success : csatStats.satisfaction_score >= 40 ? C.warning : C.error, fontSize: 18, fontWeight: '800' }}>{csatStats.satisfaction_score}%</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.ticketEmailPanel.auto.text.001', 'Customer Satisfaction (CSAT)')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 4 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <Ionicons name="thumbs-up" size={12} color={C.success} />
                <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '600' }}>{csatStats.positive} Satisfied</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <Ionicons name="thumbs-down" size={12} color={C.error} />
                <Text style={{ color: colors.error, fontSize: 11, fontWeight: '600' }}>{csatStats.negative} Not Satisfied</Text>
              </View>
              <Text style={{ color: C.textMuted, fontSize: 10 }}>{csatStats.total_ratings} total</Text>
            </View>
          </View>
        </View>
      )}

      {/* Tab Bar */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {TABS.map(t => (
          <TouchableOpacity
            key={t.id}
            onPress={() => { setTab(t.id); setSelectedTicket(null); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10, backgroundColor: tab === t.id ? C.primary : C.card, borderWidth: 1, borderColor: tab === t.id ? C.primary : C.border }}
            data-testid={`tab-${t.id}`} testID={`tab-${t.id}`}
          >
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? colors.primaryText : C.textMuted} />
            <Text style={{ color: tab === t.id ? colors.primaryText : C.textMuted, fontSize: 12, fontWeight: '700' }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ═══ INBOX TAB ═══ */}
      {tab === 'inbox' && (
        <View data-testid="ticket-inbox-section" testID="ticket-inbox-section">
          {/* Status filter */}
          <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12 }}>
            {['all', 'open', 'in_progress', 'resolved', 'closed'].map(s => (
              <TouchableOpacity key={s} onPress={() => setStatusFilter(s)} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: statusFilter === s ? (globalThis as any).__alphaColor(C.primary, '20') : C.card, borderWidth: 1, borderColor: statusFilter === s ? (globalThis as any).__alphaColor(C.primary, '40') : C.border }} data-testid={`filter-${s}`} testID={`filter-${s}`}>
                <Text style={{ color: statusFilter === s ? C.primary : C.textMuted, fontSize: 10, fontWeight: '700' }}>{s.replace('_', ' ').toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {selectedTicket ? (
            /* ─── Ticket Detail ─── */
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }} data-testid="ticket-detail" testID="ticket-detail">
              <TouchableOpacity onPress={() => setSelectedTicket(null)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 14 }} data-testid="back-to-inbox" testID="back-to-inbox">
                <Ionicons name="arrow-back" size={16} color={C.primary} />
                <Text style={{ color: C.primary, fontSize: 12, fontWeight: '600' }}>{tx('admin.ticketEmailPanel.auto.text.002', 'Back to inbox')}</Text>
              </TouchableOpacity>

              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>{selectedTicket.subject}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }}>
                    {selectedTicket.ticket_id} | {selectedTicket.name} ({selectedTicket.email})
                  </Text>
                </View>
                {selectedTicket.csat_rating && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8, backgroundColor: selectedTicket.csat_rating === 'positive' ? C.successSoft : C.errorSoft, borderWidth: 1, borderColor: selectedTicket.csat_rating === 'positive' ? C.successSoft : C.errorSoft, marginRight: 8 }} data-testid="ticket-csat-badge" testID="ticket-csat-badge">
                    <Ionicons name={selectedTicket.csat_rating === 'positive' ? 'thumbs-up' : 'thumbs-down'} size={12} color={selectedTicket.csat_rating === 'positive' ? C.success : C.error} />
                    <Text style={{ color: selectedTicket.csat_rating === 'positive' ? C.success : C.error, fontSize: 10, fontWeight: '700' }}>{selectedTicket.csat_rating === 'positive' ? 'Satisfied' : 'Not Satisfied'}</Text>
                  </View>
                )}
                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor((statusColors[selectedTicket.status] || C.textMuted), '20') }}>
                  <Text style={{ color: statusColors[selectedTicket.status] || C.textMuted, fontSize: 10, fontWeight: '800' }}>{(selectedTicket.status || 'open').toUpperCase()}</Text>
                </View>
              </View>

              {/* AI Classification Card */}
              {selectedTicket.ai_classification && (
                <View style={{ backgroundColor: colors.primarySoft, borderRadius: 12, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: colors.primarySoft }} data-testid="ai-classification-card" testID="ai-classification-card">
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name="sparkles" size={14} color={colors.primary} />
                      </View>
                      <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('admin.ticketEmailPanel.auto.text.003', 'AI Classification')}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 9 }}>{selectedTicket.ai_classification.model} | {Math.round((selectedTicket.ai_classification.confidence || 0) * 100)}% confidence</Text>
                    </View>
                    <TouchableOpacity
                      onPress={() => reclassifyTicket(selectedTicket.ticket_id)}
                      disabled={reclassifying === selectedTicket.ticket_id}
                      style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }}
                      data-testid="reclassify-btn" testID="reclassify-btn"
                    >
                      <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>
                        {reclassifying === selectedTicket.ticket_id ? 'Classifying...' : 'Re-classify'}
                      </Text>
                    </TouchableOpacity>
                  </View>

                  <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                    {/* Topic badge */}
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30') }}>
                      <Ionicons name={(topicIcons[selectedTicket.ai_classification.topic] || 'chatbubbles') as any} size={12} color={C.primary} />
                      <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>{(selectedTicket.ai_classification.topic || '').replace('_', ' ').toUpperCase()}</Text>
                    </View>
                    {/* Priority badge */}
                    <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((priorityColors[selectedTicket.ai_classification.priority] || C.textMuted), '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor((priorityColors[selectedTicket.ai_classification.priority] || C.textMuted), '30') /* @theme-ok priority-colored pill w/ alpha fallback */ }}>
                      <Text style={{ color: priorityColors[selectedTicket.ai_classification.priority] || C.textMuted, fontSize: 10, fontWeight: '800' }}>{(selectedTicket.ai_classification.priority || '').toUpperCase()} PRIORITY</Text>
                    </View>
                    {/* Tags */}
                    {(selectedTicket.ai_tags || []).map((tag: string, i: number) => (
                      <View key={i} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }}>
                        <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '600' }}>#{tag}</Text>
                      </View>
                    ))}
                  </View>

                  {/* Reasoning */}
                  <Text style={{ color: C.textMuted, fontSize: 11, lineHeight: 16, marginBottom: 8 }}>
                    {selectedTicket.ai_classification.reasoning}
                  </Text>

                  {/* Customer Mood Indicator */}
                  {selectedTicket.ai_classification.sentiment && (() => {
                    const s = selectedTicket.ai_classification.sentiment;
                    const mc = moodConfig[s.mood] || moodConfig.neutral;
                    const fb = getFrustrationBar(s.frustration_level || 3);
                    return (
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(mc.color, '08'), borderRadius: 10, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(mc.color, '20') }} data-testid="customer-mood-card" testID="customer-mood-card">
                        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                            <View style={{ width: 30, height: 30, borderRadius: 15, backgroundColor: (globalThis as any).__alphaColor(mc.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                              <Ionicons name={mc.icon as any} size={16} color={mc.color} />
                            </View>
                            <View>
                              <Text style={{ color: mc.color, fontSize: 12, fontWeight: '800' }}>Customer Mood: {mc.label}</Text>
                              <Text style={{ color: C.textMuted, fontSize: 9 }}>Frustration Level: {s.frustration_level}/10</Text>
                            </View>
                          </View>
                          {s.auto_escalate && (
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: colors.errorSoft, borderWidth: 1, borderColor: colors.errorSoft }} data-testid="auto-escalated-badge" testID="auto-escalated-badge">
                              <Ionicons name="alert-circle" size={12} color={colors.error} />
                              <Text style={{ color: colors.error, fontSize: 9, fontWeight: '800' }}>{tx('admin.ticketEmailPanel.auto.text.004', 'AUTO-ESCALATED')}</Text>
                            </View>
                          )}
                        </View>
                        {/* Frustration bar */}
                        <View style={{ height: 6, borderRadius: 3, backgroundColor: C.bg, marginBottom: 6, overflow: 'hidden' }}>
                          <View style={{ height: '100%', borderRadius: 3, backgroundColor: fb.color, width: fb.width }} />
                        </View>
                        {/* Tone indicators */}
                        {(s.tone_indicators || []).length > 0 && (
                          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                            {s.tone_indicators.map((t: string, i: number) => (
                              <View key={i} style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(mc.color, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(mc.color, '20') }}>
                                <Text style={{ color: mc.color, fontSize: 9, fontWeight: '600', fontStyle: 'italic' }}>"{t}"</Text>
                              </View>
                            ))}
                          </View>
                        )}
                      </View>
                    );
                  })()}

                  {/* Routing info */}
                  {selectedTicket.ai_routing && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingTop: 8, borderTopWidth: 1, borderTopColor: C.border }}>
                      <Ionicons name="git-branch" size={12} color={colors.accent} />
                      <Text style={{ color: colors.accent, fontSize: 10, fontWeight: '700' }}>Routed to: {selectedTicket.ai_routing.team}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 10 }}>({selectedTicket.ai_routing.assigned_to})</Text>
                    </View>
                  )}
                </View>
              )}

              {/* AI Suggested Response */}
              {selectedTicket.ai_classification?.suggested_response ? (
                <View style={{ backgroundColor: colors.successSoft, borderRadius: 12, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: colors.successSoft }} data-testid="ai-suggested-response" testID="ai-suggested-response">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <Ionicons name="chatbox-ellipses" size={14} color={colors.success} />
                    <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '800' }}>{tx('admin.ticketEmailPanel.auto.text.005', 'AI Suggested Response')}</Text>
                  </View>
                  <Text style={{ color: C.text, fontSize: 12, lineHeight: 18 }}>{selectedTicket.ai_classification.suggested_response}</Text>
                  <TouchableOpacity
                    onPress={() => setReplyText(selectedTicket.ai_classification.suggested_response)}
                    style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }}
                    data-testid="use-suggested-response-btn" testID="use-suggested-response-btn"
                  >
                    <Ionicons name="copy" size={12} color={colors.success} />
                    <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '700' }}>{tx('admin.ticketEmailPanel.auto.text.006', 'Use as Reply')}</Text>
                  </TouchableOpacity>
                </View>
              ) : !selectedTicket.ai_classification ? (
                <TouchableOpacity
                  onPress={() => reclassifyTicket(selectedTicket.ticket_id)}
                  disabled={reclassifying === selectedTicket.ticket_id}
                  style={{ backgroundColor: colors.primarySoft, borderRadius: 12, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: colors.primarySoft, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 }}
                  data-testid="classify-ticket-btn" testID="classify-ticket-btn"
                >
                  <Ionicons name="sparkles" size={16} color={colors.primary} />
                  <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>
                    {reclassifying === selectedTicket.ticket_id ? 'Classifying...' : 'Run AI Classification'}
                  </Text>
                </TouchableOpacity>
              ) : null}

              {/* Message */}
              <View style={{ backgroundColor: C.bg, borderRadius: 10, padding: 14, marginBottom: 14, borderWidth: 1, borderColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 13, lineHeight: 20 }}>{selectedTicket.message}</Text>
                <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 8 }}>Submitted: {selectedTicket.created_at?.slice(0, 16)?.replace('T', ' ')}</Text>
              </View>

              {/* Status actions */}
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14 }}>
                {['open', 'in_progress', 'resolved', 'closed'].map(s => (
                  <TouchableOpacity key={s} onPress={() => updateTicket(selectedTicket.ticket_id, { status: s })} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: selectedTicket.status === s ? (globalThis as any).__alphaColor((statusColors[s] || C.textMuted), '25') : C.bg, borderWidth: 1, borderColor: selectedTicket.status === s ? (globalThis as any).__alphaColor((statusColors[s] || C.textMuted), '50') : C.border }} data-testid={`set-status-${s}`} testID={`set-status-${s}`}>
                    <Text style={{ color: selectedTicket.status === s ? (statusColors[s] || C.textMuted) : C.textMuted, fontSize: 10, fontWeight: '700' }}>{s.replace('_', ' ').toUpperCase()}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Admin notes */}
              {(selectedTicket.admin_notes || []).length > 0 && (
                <View style={{ marginBottom: 14 }}>
                  <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', marginBottom: 8, textTransform: 'uppercase' }}>{tx('admin.ticketEmailPanel.auto.text.007', 'Notes & Replies')}</Text>
                  {selectedTicket.admin_notes.map((n: any, i: number) => (
                    <View key={i} style={{ backgroundColor: n.text?.startsWith('[EMAIL REPLY]') ? C.primarySoft : C.bg, borderRadius: 8, padding: 10, marginBottom: 6, borderWidth: 1, borderColor: n.text?.startsWith('[EMAIL REPLY]') ? C.primarySoft : C.border }} data-testid={`note-${i}`} testID={`note-${i}`}>
                      <Text style={{ color: C.text, fontSize: 12 }}>{n.text?.replace('[EMAIL REPLY] ', '')}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 9, marginTop: 4 }}>{n.at?.slice(0, 16)?.replace('T', ' ')} by {n.by}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Add note */}
              <View style={{ marginBottom: 14 }}>
                <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', marginBottom: 6, textTransform: 'uppercase' }}>{tx('admin.ticketEmailPanel.auto.text.008', 'Add Internal Note')}</Text>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TextInput value={noteText} onChangeText={setNoteText} placeholder={tx('admin.ticketEmailPanel.auto.placeholder.001', 'Internal note...')} placeholderTextColor={C.textMuted} style={{ flex: 1, backgroundColor: C.bg, borderRadius: 8, padding: 10, color: C.text, borderWidth: 1, borderColor: C.border, fontSize: 12 }} data-testid="note-input" testID="note-input" />
                  <TouchableOpacity onPress={() => { if (noteText.trim()) { updateTicket(selectedTicket.ticket_id, { note: noteText.trim() }); setNoteText(''); } }} style={{ paddingHorizontal: 14, justifyContent: 'center', borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }} data-testid="add-note-btn" testID="add-note-btn">
                    <Ionicons name="add" size={18} color={C.text} />
                  </TouchableOpacity>
                </View>
              </View>

              {/* Reply by email */}
              <View>
                <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', marginBottom: 6, textTransform: 'uppercase' }}>{tx('admin.ticketEmailPanel.auto.text.009', 'Reply via Email')}</Text>
                <TextInput
                  value={replyText} onChangeText={setReplyText} placeholder={tx('admin.ticketEmailPanel.auto.placeholder.002', 'Type your reply...')} placeholderTextColor={C.textMuted} multiline numberOfLines={3}
                  style={{ backgroundColor: C.bg, borderRadius: 8, padding: 10, color: C.text, borderWidth: 1, borderColor: C.border, fontSize: 12, minHeight: 70, textAlignVertical: 'top' }}
                  data-testid="reply-input" testID="reply-input"
                />
                <TouchableOpacity onPress={() => sendReply(selectedTicket.ticket_id)} disabled={saving || !replyText.trim()} style={{ marginTop: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 8, backgroundColor: replyText.trim() ? C.primary : C.card, borderWidth: 1, borderColor: replyText.trim() ? C.primary : C.border }} data-testid="send-reply-btn" testID="send-reply-btn">
                  <Ionicons name="send" size={14} color={replyText.trim() ? colors.primaryText : C.textMuted} />
                  <Text style={{ color: replyText.trim() ? colors.primaryText : C.textMuted, fontSize: 12, fontWeight: '700' }}>{saving ? 'Sending...' : 'Send Reply'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            /* ─── Ticket List ─── */
            <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="ticket-list" testID="ticket-list">
              {tickets.length === 0 ? (
                <View style={{ padding: 40, alignItems: 'center' }}>
                  <Ionicons name="mail-open" size={32} color={C.textMuted} />
                  <Text style={{ color: C.textMuted, fontSize: 13, marginTop: 10 }}>{tx('admin.ticketEmailPanel.auto.text.010', 'No tickets found')}</Text>
                </View>
              ) : tickets.map((t, i) => (
                <TouchableOpacity key={t.ticket_id || i} onPress={() => { setSelectedTicket(t); setReplyText(''); setNoteText(''); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderBottomWidth: i < tickets.length - 1 ? 1 : 0, borderBottomColor: C.border }} data-testid={`ticket-row-${i}`} testID={`ticket-row-${i}`}>
                  <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor((statusColors[t.status] || C.border), '15'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={t.ai_classification ? (topicIcons[t.ai_classification.topic] || 'chatbubbles') as any : (t.status === 'resolved' || t.status === 'closed' ? 'checkmark-circle' : 'mail')} size={16} color={statusColors[t.status] || C.textMuted} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', flex: 1 }} numberOfLines={1}>{t.subject || 'No subject'}</Text>
                      {/* Priority badge from AI */}
                      {t.ai_classification?.priority && (
                        <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor((priorityColors[t.ai_classification.priority] || C.textMuted), '18') }}>
                          <Text style={{ color: priorityColors[t.ai_classification.priority] || C.textMuted, fontSize: 7, fontWeight: '800' }}>{t.ai_classification.priority.toUpperCase()}</Text>
                        </View>
                      )}
                      <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor((statusColors[t.status] || C.textMuted), '18') }}>
                        <Text style={{ color: statusColors[t.status] || C.textMuted, fontSize: 8, fontWeight: '800' }}>{(t.status || 'open').toUpperCase()}</Text>
                      </View>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 }}>
                      <Text style={{ color: C.textMuted, fontSize: 10 }}>{t.name} ({t.email}) | {t.ticket_id}</Text>
                      {t.ai_classification && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                          <Ionicons name="sparkles" size={9} color={colors.primary} />
                          <Text style={{ color: colors.primary, fontSize: 9, fontWeight: '600' }}>{t.ai_classification.topic?.replace('_', ' ')}</Text>
                        </View>
                      )}
                      {t.ai_routing?.team && (
                        <Text style={{ color: colors.accent, fontSize: 9, fontWeight: '600' }}>{t.ai_routing.team}</Text>
                      )}
                      {/* Mood indicator in list */}
                      {t.ai_classification?.sentiment?.mood && (() => {
                        const mc = moodConfig[t.ai_classification.sentiment.mood] || moodConfig.neutral;
                        return (
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }} data-testid={`mood-indicator-${i}`} testID={`mood-indicator-${i}`}>
                            <Ionicons name={mc.icon as any} size={10} color={mc.color} />
                            <Text style={{ color: mc.color, fontSize: 8, fontWeight: '700' }}>{t.ai_classification.sentiment.frustration_level}/10</Text>
                          </View>
                        );
                      })()}
                      {t.auto_escalated && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3, backgroundColor: colors.errorSoft }}>
                          <Ionicons name="alert-circle" size={8} color={colors.error} />
                          <Text style={{ color: colors.error, fontSize: 7, fontWeight: '800' }}>{tx('admin.ticketEmailPanel.auto.text.011', 'ESC')}</Text>
                        </View>
                      )}
                    </View>
                  </View>
                  <Text style={{ color: C.textMuted, fontSize: 9 }}>{t.created_at?.slice(0, 10)}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>
      )}

      {/* ═══ AI ROUTING TAB ═══ */}
      {tab === 'routing' && (
        <View data-testid="ticket-routing-section" testID="ticket-routing-section">
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="git-branch" size={16} color={colors.accent} />
              </View>
              <View>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.ticketEmailPanel.auto.text.012', 'AI Routing Rules')}</Text>
                <Text style={{ color: C.textMuted, fontSize: 10 }}>{tx('admin.ticketEmailPanel.auto.text.013', 'Map ticket topics to team members. AI auto-classifies incoming tickets.')}</Text>
              </View>
            </View>

            {Object.entries(routingRules).map(([topic, rule]: [string, any]) => (
              <View key={topic} style={{ borderBottomWidth: 1, borderBottomColor: C.border, paddingVertical: 12 }} data-testid={`routing-rule-${topic}`} testID={`routing-rule-${topic}`}>
                {editingRule === topic ? (
                  <View style={{ gap: 8 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Ionicons name={(topicIcons[topic] || 'chatbubbles') as any} size={16} color={C.primary} />
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{topic.replace('_', ' ').toUpperCase()}</Text>
                    </View>
                    <TextInput value={ruleDraft.team || ''} onChangeText={v => setRuleDraft({ ...ruleDraft, team: v })} placeholder={tx('admin.ticketEmailPanel.auto.placeholder.003', 'Team name')} placeholderTextColor={C.textMuted} style={{ backgroundColor: C.bg, borderRadius: 8, padding: 10, color: C.text, borderWidth: 1, borderColor: C.border, fontSize: 12 }} data-testid={`routing-team-${topic}`} testID={`routing-team-${topic}`} />
                    <TextInput value={ruleDraft.assigned_to || ''} onChangeText={v => setRuleDraft({ ...ruleDraft, assigned_to: v })} placeholder={tx('admin.ticketEmailPanel.auto.placeholder.004', 'Assigned to (email)')} placeholderTextColor={C.textMuted} style={{ backgroundColor: C.bg, borderRadius: 8, padding: 10, color: C.text, borderWidth: 1, borderColor: C.border, fontSize: 12 }} data-testid={`routing-email-${topic}`} testID={`routing-email-${topic}`} />
                    <View style={{ flexDirection: 'row', gap: 8 }}>
                      <TouchableOpacity onPress={() => saveRoutingRule(topic)} disabled={saving} style={{ flex: 1, paddingVertical: 8, borderRadius: 8, backgroundColor: C.primary, alignItems: 'center' }} data-testid={`save-routing-${topic}`} testID={`save-routing-${topic}`}>
                        <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{saving ? 'Saving...' : 'Save'}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity accessibilityLabel={tx('admin.ticketEmailPanel.auto.accessibility.001', 'Cancel')} onPress={() => setEditingRule(null)} style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: C.bg, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
                        <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.ticketEmailPanel.auto.text.014', 'Cancel')}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ) : (
                  <TouchableOpacity accessibilityLabel={tx('admin.ticketEmailPanel.auto.accessibility.002', 'Edit routing rule')} onPress={() => { setEditingRule(topic); setRuleDraft(rule); }} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={(topicIcons[topic] || 'chatbubbles') as any} size={14} color={C.primary} />
                      </View>
                      <View>
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{topic.replace('_', ' ').toUpperCase()}</Text>
                        <Text style={{ color: C.textMuted, fontSize: 10 }}>{rule.team} ({rule.assigned_to})</Text>
                      </View>
                    </View>
                    <Ionicons name="pencil" size={14} color={C.textMuted} />
                  </TouchableOpacity>
                )}
              </View>
            ))}
          </View>

          {/* How it works */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="routing-explainer" testID="routing-explainer">
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>{tx('admin.ticketEmailPanel.auto.text.015', 'How Smart Routing Works')}</Text>
            {[
              { icon: 'document-text', text: 'User submits a support ticket', color: colors.primary },
              { icon: 'sparkles', text: 'GPT-4o analyzes topic, priority, and generates a suggested response', color: colors.warningText },
              { icon: 'git-branch', text: 'Ticket is auto-routed to the correct team based on rules above', color: colors.accent },
              { icon: 'checkmark-circle', text: 'Admin reviews AI classification and uses suggested reply or writes custom one', color: colors.successText },
            ].map((step, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8 }}>
                <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(step.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ color: step.color, fontSize: 11, fontWeight: '800' }}>{i + 1}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 }}>
                  <Ionicons name={step.icon as any} size={14} color={step.color} />
                  <Text style={{ color: C.text, fontSize: 11, flex: 1 }}>{step.text}</Text>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* ═══ CONFIG TAB ═══ */}
      {tab === 'config' && config && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }} data-testid="ticket-config-section" testID="ticket-config-section">
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 16 }}>{tx('admin.ticketEmailPanel.auto.text.016', 'Email Configuration')}</Text>
          <ConfigField label="Support Email Address" desc="Where ticket submission emails are sent" value={config.support_email} onSave={(v: string) => saveConfig({ support_email: v })} colors={C} testId="config-support-email" />
          <ConfigField label="Reply-To Email" desc="Reply-to address on outgoing emails" value={config.reply_to_email} onSave={(v: string) => saveConfig({ reply_to_email: v })} colors={C} testId="config-reply-to" />
          <ConfigField label="Email Signature" desc="Appended to all outgoing ticket replies" value={config.signature} onSave={(v: string) => saveConfig({ signature: v })} colors={C} testId="config-signature" multiline />

          <View style={{ marginTop: 16, gap: 12 }}>
            <ToggleRow label="Auto-Reply on New Tickets" value={config.auto_reply_enabled} onToggle={(v: boolean) => saveConfig({ auto_reply_enabled: v })} colors={C} testId="config-auto-reply" />
            <ToggleRow label="CC Admins on New Tickets" value={config.cc_admins_on_new_ticket} onToggle={(v: boolean) => saveConfig({ cc_admins_on_new_ticket: v })} colors={C} testId="config-cc-admins" />
            <ToggleRow label="Escalation Alerts" value={config.escalation_enabled} onToggle={(v: boolean) => saveConfig({ escalation_enabled: v })} colors={C} testId="config-escalation" />
          </View>

          {config.escalation_enabled && (
            <View style={{ marginTop: 12 }}>
              <ConfigField label="Escalation Email" desc="Receives alerts for overdue tickets" value={config.escalation_email} onSave={(v: string) => saveConfig({ escalation_email: v })} colors={C} testId="config-escalation-email" />
              <ConfigField label="Escalate After (hours)" desc="Hours before a ticket is considered overdue" value={String(config.escalation_after_hours || 48)} onSave={(v: string) => saveConfig({ escalation_after_hours: parseInt(v) || 48 })} colors={C} testId="config-escalation-hours" />
            </View>
          )}
        </View>
      )}

      {/* ═══ TEMPLATES TAB ═══ */}
      {tab === 'templates' && (
        <View data-testid="ticket-templates-section" testID="ticket-templates-section">
          {templates.map((tmpl, i) => (
            <View key={tmpl.template_id} style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 12 }} data-testid={`template-${tmpl.template_id}`} testID={`template-${tmpl.template_id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: tmpl.active ? (globalThis as any).__alphaColor(C.primary, '15') : C.bg, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="document-text" size={16} color={tmpl.active ? C.primary : C.textMuted} />
                  </View>
                  <View>
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{tmpl.name}</Text>
                    <Text style={{ color: C.textMuted, fontSize: 10 }}>Trigger: {tmpl.trigger} | {tmpl.active ? 'Active' : 'Inactive'}</Text>
                  </View>
                </View>
                <TouchableOpacity onPress={() => { if (editingTemplate === tmpl.template_id) { setEditingTemplate(null); } else { setEditingTemplate(tmpl.template_id); setTemplateDraft({ name: tmpl.name, subject: tmpl.subject, body: tmpl.body, active: tmpl.active }); } }} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }} data-testid={`edit-template-${tmpl.template_id}`} testID={`edit-template-${tmpl.template_id}`}>
                  <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>{editingTemplate === tmpl.template_id ? 'Cancel' : 'Edit'}</Text>
                </TouchableOpacity>
              </View>

              {editingTemplate === tmpl.template_id ? (
                <View style={{ gap: 8 }}>
                  <TextInput value={templateDraft.subject} onChangeText={v => setTemplateDraft({ ...templateDraft, subject: v })} placeholder={tx('admin.ticketEmailPanel.auto.placeholder.005', 'Subject')} placeholderTextColor={C.textMuted} style={{ backgroundColor: C.bg, borderRadius: 8, padding: 10, color: C.text, borderWidth: 1, borderColor: C.border, fontSize: 12 }} data-testid={`template-subject-${tmpl.template_id}`} testID={`template-subject-${tmpl.template_id}`} />
                  <TextInput value={templateDraft.body} onChangeText={v => setTemplateDraft({ ...templateDraft, body: v })} placeholder={tx('admin.ticketEmailPanel.auto.placeholder.006', 'Body')} placeholderTextColor={C.textMuted} multiline numberOfLines={5} style={{ backgroundColor: C.bg, borderRadius: 8, padding: 10, color: C.text, borderWidth: 1, borderColor: C.border, fontSize: 12, minHeight: 100, textAlignVertical: 'top' }} data-testid={`template-body-${tmpl.template_id}`} testID={`template-body-${tmpl.template_id}`} />
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('admin.ticketEmailPanel.auto.text.017', 'Active')}</Text>
                      <Switch value={templateDraft.active} onValueChange={v => setTemplateDraft({ ...templateDraft, active: v })} trackColor={{ false: C.bg, true: C.primary + '50' }} thumbColor={templateDraft.active ? C.primary : C.textMuted} />
                    </View>
                    <TouchableOpacity onPress={() => saveTemplate(tmpl.template_id)} disabled={saving} style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: C.primary }} data-testid={`save-template-${tmpl.template_id}`} testID={`save-template-${tmpl.template_id}`}>
                      <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{saving ? 'Saving...' : 'Save'}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ) : (
                <View>
                  <View style={{ backgroundColor: C.bg, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: C.border }}>
                    <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>Subject: {tmpl.subject}</Text>
                    <Text style={{ color: C.text, fontSize: 11, lineHeight: 16 }} numberOfLines={3}>{tmpl.body}</Text>
                  </View>
                </View>
              )}
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const tx = (_key: string, fallback: string) => fallback;

function ConfigField({ label, desc, value, onSave, colors: C, testId, multiline }: any) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || '');

  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{label}</Text>
      <Text style={{ color: C.textMuted, fontSize: 10, marginBottom: 6 }}>{desc}</Text>
      {editing ? (
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput value={draft} onChangeText={setDraft} multiline={multiline} style={{ flex: 1, backgroundColor: C.bg, borderRadius: 8, padding: 10, color: C.text, borderWidth: 1, borderColor: C.border, fontSize: 12, ...(multiline ? { minHeight: 60, textAlignVertical: 'top' } : {}) }} data-testid={`${testId}-input`} testID={`${testId}-input`} accessibilityLabel={tx('admin.ticketEmailPanel.auto.accessibility.003', 'Save')} />
          <TouchableOpacity onPress={() => { onSave(draft); setEditing(false); }} style={{ paddingHorizontal: 12, justifyContent: 'center', borderRadius: 8, backgroundColor: C.primary }} data-testid={`${testId}-save`} testID={`${testId}-save`}>
            <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.ticketEmailPanel.auto.text.018', 'Save')}</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel={tx('admin.ticketEmailPanel.auto.accessibility.004', 'close button')} onPress={() => { setEditing(false); setDraft(value); }} style={{ paddingHorizontal: 10, justifyContent: 'center', borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}>
            <Ionicons name="close" size={14} color={C.textMuted} />
          </TouchableOpacity>
        </View>
      ) : (
        <TouchableOpacity onPress={() => setEditing(true)} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.bg, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: C.border }} data-testid={testId} testID={testId}>
          <Text style={{ color: C.text, fontSize: 12, flex: 1 }} numberOfLines={2}>{value || '—'}</Text>
          <Ionicons name="pencil" size={14} color={C.textMuted} />
        </TouchableOpacity>
      )}
    </View>
  );
}

function ToggleRow({ label, value, onToggle, colors: C, testId }: any) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }} data-testid={testId} testID={testId}>
      <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{label}</Text>
      <Switch value={value} onValueChange={onToggle} trackColor={{ false: C.bg, true: C.primary + '50' }} thumbColor={value ? C.primary : C.textMuted} />
    </View>
  );
}
