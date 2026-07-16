import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ScrollView, ActivityIndicator, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

type Submission = {
  submission_id?: string;
  name: string;
  email: string;
  subject: string;
  message: string;
  status: string;
  context?: string;
  priority?: string;
  tags?: string[];
  created_at: string;
  followed_up?: boolean;
  followed_up_at?: string;
  responded_at?: string;
  admin_reply?: string;
  admin_notes?: string;
};

type Stats = {
  total: number;
  new: number;
  in_review: number;
  responded: number;
  closed: number;
  followed_up: number;
  lockout_support?: number;
};

type Analytics = {
  avg_response_hours: number | null;
  sla_24h_pct: number | null;
  response_rate: number;
  total_in_period: number;
  topic_distribution: { topic: string; count: number }[];
};

const tx = (_key: string, fallback: string) => fallback;

const LOCKOUT_COLOR = 'var(--app-error)' as any;
const AI_COLOR = 'var(--app-info)' as any;

// Module-scope fallback for helper components (theme-aware version lives in the main component)
const STATUS_META: Record<string, { label: string; color: string; icon: string }> = {
  new: { label: 'New', color: 'var(--app-primary)' as any, icon: 'mail-unread' },
  in_review: { label: 'In Review', color: 'var(--app-warning)' as any, icon: 'eye' },
  responded: { label: 'Responded', color: 'var(--app-success)' as any, icon: 'checkmark-circle' },
  closed: { label: 'Closed', color: 'var(--app-text-muted)' as any, icon: 'lock-closed' },
};

const isLockoutSubmission = (sub: Submission) => sub.context === 'login-lockout' || (sub.tags || []).includes('lockout_support') || sub.priority === 'high';

const relativeTime = (iso?: string) => {
  if (!iso) return 'now';
  const delta = Date.now() - new Date(iso).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

function MetricCard({ label, value, color, colors, icon }: { label: string; value: string | number; color: string; colors: any; icon: string }) {
  return (
    <View style={{ flex: 1, minWidth: 150, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <View style={{ width: 30, height: 30, borderRadius: 10, backgroundColor: `${color}16`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={14} color={color} />
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
      </View>
      <Text style={{ color: colors.text, fontSize: 26, fontWeight: '900' }}>{value}</Text>
    </View>
  );
}

function ReplyTemplateDropdown({ colors, onApply }: { colors: any; onApply: (body: string) => void }) {
  const [open, setOpen] = useState(false);
  const [templates, setTemplates] = useState<any[]>([]);
  const [loadingId, setLoadingId] = useState('');

  const loadTemplates = useCallback(async () => {
    try {
      const res = await api.get('/contact/reply-templates');
      setTemplates(res.data?.templates || []);
    } catch { /* silently fail */ }
  }, []);

  useEffect(() => { if (open && templates.length === 0) loadTemplates(); }, [open, templates.length, loadTemplates]);

  const apply = useCallback(async (tpl: any, contactName: string) => {
    setLoadingId(tpl.id);
    try {
      const res = await api.post('/contact/reply-templates/apply', { template_id: tpl.id, contact_name: contactName });
      onApply(res.data?.rendered_body || tpl.body);
      setOpen(false);
    } catch { onApply(tpl.body); setOpen(false); }
    finally { setLoadingId(''); }
  }, [onApply]);

  return (
    <View style={{ position: 'relative' }}>
      <TouchableOpacity onPress={() => setOpen(!open)} data-testid="reply-templates-dropdown-btn" testID="reply-templates-dropdown-btn" style={{ borderRadius: 999, borderWidth: 1, borderColor: `${LOCKOUT_COLOR}40`, backgroundColor: `${LOCKOUT_COLOR}14`, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
        <Ionicons name="document-text-outline" size={12} color={LOCKOUT_COLOR} />
        <Text style={{ color: LOCKOUT_COLOR, fontSize: 11, fontWeight: '800' }}>{tx('admin.contactSubmissionsPanel.auto.text.001', 'Templates')}</Text>
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={10} color={LOCKOUT_COLOR} />
      </TouchableOpacity>
      {open && (
        <View style={{ position: 'absolute', top: 38, left: 0, zIndex: 999, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, minWidth: 240, shadowColor: colors.overlay, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 12, elevation: 10, overflow: 'hidden' }} data-testid="reply-templates-dropdown-menu" testID="reply-templates-dropdown-menu">
          {templates.map(tpl => (
            <TouchableOpacity key={tpl.id} onPress={() => apply(tpl, '')} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border }} data-testid={`reply-template-${tpl.id}`} testID={`reply-template-${tpl.id}`}>
              <Ionicons name={(tpl.icon || 'document') as any} size={14} color={colors.primary} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{tpl.label}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tpl.category}</Text>
              </View>
              {loadingId === tpl.id && <ActivityIndicator size="small" color={colors.primary} />}
            </TouchableOpacity>
          ))}
          {templates.length === 0 && <View style={{ padding: 14 }}><ActivityIndicator size="small" color={colors.primary} /></View>}
        </View>
      )}
    </View>
  );
}

function SuggestionBar({ colors, onSuggest, loading, onApplyTemplate }: { colors: any; onSuggest: () => Promise<void>; loading: boolean; onApplyTemplate: (body: string) => void }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <TouchableOpacity
        onPress={onSuggest}
        disabled={loading}
        data-testid="ai-suggest-reply-btn"
        testID="ai-suggest-reply-btn"
        style={{ borderRadius: 999, borderWidth: 1, borderColor: `${AI_COLOR}40`, backgroundColor: `${AI_COLOR}14`, paddingHorizontal: 12, paddingVertical: 8 }}
      >
        <Text style={{ color: AI_COLOR, fontSize: 11, fontWeight: '800' }}>{loading ? 'Generating…' : '✨ Suggest Reply'}</Text>
      </TouchableOpacity>
      <ReplyTemplateDropdown colors={colors} onApply={onApplyTemplate} />
    </View>
  );
}

function DetailPane({ submission, colors, onRefresh }: { submission: Submission; colors: any; onRefresh: () => Promise<void> }) {
  const [draftReply, setDraftReply] = useState(submission.admin_reply || '');
  const [newStatus, setNewStatus] = useState(submission.status);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const isLockout = isLockoutSubmission(submission);
  const meta = STATUS_META[submission.status] || STATUS_META.new;

  useEffect(() => {
    setDraftReply(submission.admin_reply || '');
    setNewStatus(submission.status);
    setMessage('');
  }, [submission]);

  const sendReply = useCallback(async () => {
    if (!submission.submission_id || !draftReply.trim()) return;
    setSending(true);
    setMessage('');
    try {
      const res = await api.post(`/contact/submissions/${encodeURIComponent(submission.submission_id)}/reply`, { message: draftReply.trim() });
      setMessage(res.data?.message || 'Reply sent.');
      await onRefresh();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to send reply.');
    } finally {
      setSending(false);
    }
  }, [draftReply, onRefresh, submission.submission_id]);

  const suggestReply = useCallback(async () => {
    if (!submission.submission_id) return;
    setSuggesting(true);
    setMessage('');
    try {
      const res = await api.post(`/contact/submissions/${encodeURIComponent(submission.submission_id)}/suggest-reply`, { tone: isLockout ? 'reassuring' : 'professional' });
      setDraftReply(res.data?.suggested_reply || '');
      setMessage('Suggested reply inserted. Review before sending.');
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to generate suggested reply.');
    } finally {
      setSuggesting(false);
    }
  }, [isLockout, submission.submission_id]);

  const updateStatus = useCallback(async () => {
    if (!submission.submission_id || newStatus === submission.status) return;
    setUpdating(true);
    setMessage('');
    try {
      const res = await api.put(`/contact/submissions/${encodeURIComponent(submission.submission_id)}/status`, { status: newStatus });
      setMessage(res.data?.message || 'Status updated.');
      await onRefresh();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to update status.');
    } finally {
      setUpdating(false);
    }
  }, [newStatus, onRefresh, submission.status, submission.submission_id]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 18 }} data-testid="contact-submission-detail" testID="contact-submission-detail">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220 }}>
          <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900' }}>{submission.name}</Text>
          <Text style={{ color: colors.primary, marginTop: 4, fontSize: 13 }}>{submission.email}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            <View style={{ backgroundColor: `${meta.color}16`, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }}>
              <Text style={{ color: meta.color, fontSize: 10, fontWeight: '800' }}>{meta.label}</Text>
            </View>
            {isLockout ? (
              <View style={{ backgroundColor: `${LOCKOUT_COLOR}14`, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="submission-lockout-priority-pill" testID="submission-lockout-priority-pill">
                <Text style={{ color: LOCKOUT_COLOR, fontSize: 10, fontWeight: '800' }}>{tx('admin.contactSubmissionsPanel.auto.text.002', 'LOCKOUT SUPPORT')}</Text>
              </View>
            ) : null}
            <Text style={{ color: colors.textMuted, fontSize: 11 }}>{relativeTime(submission.created_at)}</Text>
          </View>
        </View>
      </View>

      <ScrollView style={{ marginTop: 16 }} contentContainerStyle={{ gap: 12 }}>
        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 14 }}>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.contactSubmissionsPanel.auto.text.003', 'SUBJECT')}</Text>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{submission.subject || 'General Inquiry'}</Text>
        </View>

        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 14 }}>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.contactSubmissionsPanel.auto.text.004', 'MESSAGE')}</Text>
          <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 22 }}>{submission.message}</Text>
        </View>

        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 14 }}>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 10 }}>{tx('admin.contactSubmissionsPanel.auto.text.005', 'REPLY WORKSPACE')}</Text>
          <SuggestionBar colors={colors} onSuggest={suggestReply} loading={suggesting} onApplyTemplate={(body: string) => setDraftReply(body)} />
          <TextInput
            value={draftReply}
            onChangeText={setDraftReply}
            placeholder={tx('admin.contactSubmissionsPanel.auto.placeholder.001', 'Type or generate your reply...')}
            placeholderTextColor={colors.textMuted}
            multiline
            numberOfLines={6}
            data-testid="reply-input"
            testID="reply-input"
            style={{ marginTop: 12, minHeight: 140, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 14, color: colors.text, fontSize: 13, textAlignVertical: 'top' as any }}
          />
          <TouchableOpacity
            onPress={sendReply}
            disabled={sending || !draftReply.trim()}
            data-testid="send-reply-btn"
            testID="send-reply-btn"
            style={{ marginTop: 12, borderRadius: 12, backgroundColor: sending || !draftReply.trim() ? colors.border : colors.success, paddingVertical: 12, alignItems: 'center', justifyContent: 'center' }}
          >
            {sending ? <ActivityIndicator color={colors.text} /> : <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{tx('admin.contactSubmissionsPanel.auto.text.006', 'Send Reply')}</Text>}
          </TouchableOpacity>
        </View>

        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 14 }}>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 10 }}>{tx('admin.contactSubmissionsPanel.auto.text.007', 'UPDATE STATUS')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(STATUS_META).map(([key, item]) => {
              const active = newStatus === key;
              return (
                <TouchableOpacity
                  key={key}
                  onPress={() => setNewStatus(key)}
                  data-testid={`status-${key}`}
                  testID={`status-${key}`}
                  style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: active ? `${item.color}18` : colors.surface, borderWidth: 1, borderColor: active ? item.color : colors.border }}
                >
                  <Text style={{ color: active ? item.color : colors.textMuted, fontSize: 12, fontWeight: '700' }}>{item.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {newStatus !== submission.status ? (
            <TouchableOpacity
              onPress={updateStatus}
              disabled={updating}
              data-testid="update-status-btn"
              testID="update-status-btn"
              style={{ marginTop: 12, borderRadius: 12, backgroundColor: colors.primary, paddingVertical: 12, alignItems: 'center', justifyContent: 'center' }}
            >
              {updating ? <ActivityIndicator color={colors.text} /> : <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{`Change to ${STATUS_META[newStatus]?.label}`}</Text>}
            </TouchableOpacity>
          ) : null}
        </View>

        {message ? <Text style={{ color: message.toLowerCase().includes('unable') || message.toLowerCase().includes('failed') ? colors.error : colors.success, fontSize: 12, fontWeight: '700' }}>{message}</Text> : null}
      </ScrollView>
    </View>
  );
}

export default function ContactSubmissionsPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();

  // Theme-aware color variants for live rendering
  const STATUS_META: Record<string, { label: string; color: string; icon: string }> = {
    new: { label: 'New', color: colors.primary, icon: 'mail-unread' },
    in_review: { label: 'In Review', color: colors.warningText, icon: 'eye' },
    responded: { label: 'Responded', color: colors.successText, icon: 'checkmark-circle' },
    closed: { label: 'Closed', color: colors.textMuted, icon: 'lock-closed' },
  };
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1100;
  const isMobile = width < 760;
  const [subs, setSubs] = useState<Submission[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [selectedId, setSelectedId] = useState('');

  const load = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    if (mode === 'initial') setLoading(true); else setRefreshing(true);
    try {
      const params = new URLSearchParams({ status: filter, search, limit: '100' });
      const [subRes, analyticsRes] = await Promise.all([
        api.get(`/contact/submissions?${params.toString()}`),
        api.get('/contact/analytics?days=30'),
      ]);
      const subData = subRes.data || {};
      setSubs(subData.submissions || []);
      setStats(subData.stats || null);
      setAnalytics(analyticsRes.data || null);
      setSelectedId((prev) => prev || subData.submissions?.[0]?.submission_id || '');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filter, search]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/contact-submissions/hybrid-refresh',
    onTick: () => load('refresh'),
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const runFollowups = useCallback(async () => {
    setTriggering(true);
    try {
      await api.post('/contact/followup/trigger');
      await load('refresh');
    } finally {
      setTriggering(false);
    }
  }, [load]);

  const selected = useMemo(() => subs.find((sub) => sub.submission_id === selectedId) || subs[0] || null, [selectedId, subs]);

  return (
    <View style={{ flex: 1 }} data-testid="contact-submissions-panel" testID="contact-submissions-panel">
      <AutoFixBanner domain="contact" />

      <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', gap: 12, marginBottom: 18 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 24, fontWeight: '900' }}>{tx('admin.contactSubmissionsPanel.auto.text.008', 'Contact Submissions')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.contactSubmissionsPanel.auto.text.009', 'Guest/public contact inbox with live support triage, AI drafting, and lockout-priority visibility.')}</Text>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TouchableOpacity onPress={runFollowups} disabled={triggering} data-testid="trigger-followup-btn" testID="trigger-followup-btn" style={{ borderRadius: 12, borderWidth: 1, borderColor: `${colors.warning}35`, backgroundColor: `${colors.warning}18`, paddingHorizontal: 14, paddingVertical: 10 }}>
            <Text style={{ color: colors.warningText, fontSize: 12, fontWeight: '800' }}>{triggering ? 'Processing…' : 'Run Follow-ups'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => load('refresh')} data-testid="refresh-submissions-btn" testID="refresh-submissions-btn" style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 14, paddingVertical: 10 }}>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{refreshing ? 'Refreshing…' : 'Refresh'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {stats ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 18 }}>
          <MetricCard label="New" value={stats.new} color={colors.primary} icon="mail-unread" colors={colors} />
          <MetricCard label="In Review" value={stats.in_review} color={colors.warning} icon="eye" colors={colors} />
          <MetricCard label="Responded" value={stats.responded} color={colors.success} icon="checkmark-circle" colors={colors} />
          <MetricCard label="Lockout Support" value={stats.lockout_support || 0} color={LOCKOUT_COLOR} icon="shield-checkmark" colors={colors} />
        </View>
      ) : null}

      {analytics ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 18 }}>
          <MetricCard label="Avg Response" value={analytics.avg_response_hours ?? '—'} color={colors.primary} icon="time" colors={colors} />
          <MetricCard label="SLA (24h)" value={analytics.sla_24h_pct != null ? `${analytics.sla_24h_pct}%` : '—'} color={colors.success} icon="shield-checkmark" colors={colors} />
          <MetricCard label="Response Rate" value={`${analytics.response_rate}%`} color={colors.warning} icon="chatbubbles" colors={colors} />
          <MetricCard label="30d Volume" value={analytics.total_in_period} color={AI_COLOR} icon="analytics" colors={colors} />
        </View>
      ) : null}

      <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 14 }}>
        <View style={{ flex: isDesktop ? 1 : undefined, backgroundColor: colors.surface, borderRadius: 18, borderWidth: 1, borderColor: colors.border, padding: 16 }}>
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10, marginBottom: 14 }}>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, flex: 1 }}>
              {[{ key: 'all', label: 'All' }, ...Object.entries(STATUS_META).map(([key, meta]) => ({ key, label: meta.label }))].map((item) => {
                const active = filter === item.key;
                return (
                  <TouchableOpacity key={item.key} onPress={() => setFilter(item.key)} data-testid={`filter-${item.key}`} testID={`filter-${item.key}`} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: active ? `${colors.primary}18` : colors.surfaceHover, borderWidth: 1, borderColor: active ? colors.primary : colors.border }}>
                    <Text style={{ color: active ? colors.primary : colors.textMuted, fontSize: 12, fontWeight: '700' }}>{item.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <TextInput value={search} onChangeText={setSearch} placeholder={tx('admin.contactSubmissionsPanel.auto.placeholder.002', 'Search name, email, subject...')} placeholderTextColor={colors.textMuted} data-testid="search-input" testID="search-input" style={{ minWidth: isMobile ? '100%' : 240, backgroundColor: colors.surfaceHover, color: colors.text, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, fontSize: 13 } as any} />
          </View>

          {loading ? (
            <View style={{ paddingVertical: 36, alignItems: 'center' }}><ActivityIndicator size="large" color={colors.primary} /></View>
          ) : (
            <ScrollView style={{ maxHeight: isDesktop ? 920 : 420 }} contentContainerStyle={{ gap: 10 }}>
              {subs.map((sub, idx) => {
                const meta = STATUS_META[sub.status] || STATUS_META.new;
                const active = selected?.submission_id === sub.submission_id;
                return (
                  <TouchableOpacity key={sub.submission_id || `${sub.email}-${idx}`} onPress={() => setSelectedId(sub.submission_id || '')} data-testid={`submission-row-${idx}`} testID={`submission-row-${idx}`} style={{ backgroundColor: active ? `${colors.primary}10` : colors.surfaceHover, borderWidth: 1, borderColor: active ? colors.primary : colors.border, borderRadius: 14, padding: 14 }}>
                    <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', gap: 10 }}>
                      <View style={{ flexDirection: 'row', gap: 12, flex: 1 }}>
                        <View style={{ width: 42, height: 42, borderRadius: 21, backgroundColor: `${meta.color}18`, alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name={meta.icon as any} size={18} color={meta.color} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{sub.name}</Text>
                            {isLockoutSubmission(sub) && <View style={{ backgroundColor: `${LOCKOUT_COLOR}18`, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999 }} data-testid={`submission-lockout-tag-${idx}`} testID={`submission-lockout-tag-${idx}`}><Text style={{ color: LOCKOUT_COLOR, fontSize: 9, fontWeight: '800' }}>{tx('admin.contactSubmissionsPanel.auto.text.010', 'LOCKOUT SUPPORT')}</Text></View>}
                          </View>
                  <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 3 }}>{sub.subject || 'General Inquiry'}</Text>
                        </View>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <Text style={{ color: colors.textMuted, fontSize: 11 }}>{relativeTime(sub.created_at)}</Text>
                        <View style={{ backgroundColor: `${meta.color}16`, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999 }}>
                          <Text style={{ color: meta.color, fontSize: 10, fontWeight: '800' }}>{meta.label}</Text>
                        </View>
                      </View>
                    </View>
                  </TouchableOpacity>
                );
              })}
              {!subs.length ? <Text style={{ color: colors.textMuted, textAlign: 'center', paddingVertical: 30 }}>{tx('admin.contactSubmissionsPanel.auto.text.011', 'No submissions found.')}</Text> : null}
            </ScrollView>
          )}
        </View>

        {selected ? <DetailPane submission={selected} colors={colors} onRefresh={() => load('refresh')} /> : null}
      </View>
    </View>
  );
}