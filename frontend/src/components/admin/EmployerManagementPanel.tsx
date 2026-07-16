import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, Alert, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);
const STATUS_COLORS: any = { pending: C.yellow, in_review: C.purple, approved: C.green, rejected: C.red, on_hold: C.muted, needs_info: C.cyan, escalated: C.red };

const tx = (_key: string, fallback: string) => fallback;

export default function EmployerManagementPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const [filter, setFilter] = useState('all');
  const { data: stats, loading: stLoading, refetch: loadData } = useLiveQuery('/employers/admin/stats', { entity: 'employers', pollInterval: 30000 });
  const { data: appsData, loading: apLoading } = useLiveQuery(`/employers/admin/applications?status=${filter}`, { entity: 'employers', pollInterval: 30000 });
  const apps = appsData?.applications || [];
  const loading = stLoading || apLoading;
  const [selected, setSelected] = useState<any>(null);
  const [detailTab, setDetailTab] = useState('info');
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [processing, setProcessing] = useState(false);
  const [auditTrail, setAuditTrail] = useState<any[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [newMsg, setNewMsg] = useState('');
  const [sendingMsg, setSendingMsg] = useState(false);
  const [downloadingDocId, setDownloadingDocId] = useState('');

  const loadDetail = useCallback(async (employerId: string) => {
    try {
      const [detailRes, msgRes] = await Promise.all([
        api.get(`/employers/admin/application/${employerId}`),
        api.get(`/employers/messages/${employerId}`).catch(() => ({ data: { messages: [] } })),
      ]);
      setAuditTrail(detailRes.data.audit_trail || []);
      setMessages(msgRes.data.messages || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/EmployerManagementPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const handleSelect = (app: any) => {
    if (selected?.employer_id === app.employer_id) {
      setSelected(null);
      setDetailTab('info');
    } else {
      setSelected(app);
      setDetailTab('info');
      loadDetail(app.employer_id);
    }
  };

  const handleAction = async (employerId: string, action: string) => {
    setProcessing(true);
    try {
      await api.post(`/hiring/v2/admin/employers/review/${employerId}`, { action, reason: reason || undefined, internal_note: note || undefined });
      setSelected(null);
      setReason('');
      setNote('');
      loadData();
    } catch (e: any) {
      Alert.alert(
        tx('admin.employerManagementPanel.auto.alert.error', 'Error'),
        e?.response?.data?.detail || tx('admin.employerManagementPanel.auto.alert.actionFailed', 'Action failed')
      );
    }
    setProcessing(false);
  };

  const sendMessage = async (employerId: string) => {
    if (!newMsg.trim()) return;
    setSendingMsg(true);
    try {
      await api.post(`/hiring/v2/admin/employers/messages/${employerId}`, { message: newMsg.trim() });
      setNewMsg('');
      loadDetail(employerId);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/EmployerManagementPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSendingMsg(false);
  };

  const addNote = async (employerId: string) => {
    if (!note.trim()) return;
    try {
      await api.post(`/hiring/v2/admin/employers/add-note/${employerId}`, { note: note.trim() });
      setNote('');
      loadDetail(employerId);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/EmployerManagementPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const downloadDoc = async (employerId: string, doc: any) => {
    if (!doc?.doc_id) return;
    setDownloadingDocId(String(doc.doc_id));
    try {
      const res = await api.get(`/employers/documents/${employerId}/${doc.doc_id}/download`, { responseType: 'blob' as any });
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const blob = res.data instanceof Blob ? res.data : new Blob([res.data], { type: doc.content_type || 'application/octet-stream' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = doc.original_filename || doc.filename || `${doc.doc_id}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      }
    } catch (e: any) {
      Alert.alert(
        tx('admin.employerManagementPanel.auto.alert.downloadFailed', 'Download failed'),
        e?.response?.data?.detail || tx('admin.employerManagementPanel.auto.alert.downloadUnable', 'Unable to download document')
      );
    } finally {
      setDownloadingDocId('');
    }
  };

  return (
    <View data-testid="employer-management-panel" testID="employer-management-panel">
      {/* Stats Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
        {[
          { label: 'Total', value: stats?.total ?? '--', color: C.blue, icon: 'business' as const },
          { label: 'Pending', value: stats?.pending ?? 0, color: C.yellow, icon: 'time' as const },
          { label: 'In Review', value: stats?.in_review ?? 0, color: C.purpleText, icon: 'eye' as const },
          { label: 'Approved', value: stats?.approved ?? 0, color: C.green, icon: 'checkmark-circle' as const },
          { label: 'Rejected', value: stats?.rejected ?? 0, color: C.red, icon: 'close-circle' as const },
        ].map(s => (
          <View key={s.label} style={{ flex: 1, minWidth: 100, backgroundColor: (globalThis as any).__alphaColor(s.color, '10'), borderRadius: 14, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.color, '20') }} data-testid={`emp-stat-${s.label.toLowerCase()}`} testID={`emp-stat-${s.label.toLowerCase()}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', textTransform: 'uppercase' }}>{s.label}</Text>
              <Ionicons name={s.icon} size={14} color={s.color} />
            </View>
            <Text style={{ fontSize: 24, fontWeight: '800', color: s.color }}>{s.value}</Text>
          </View>
        ))}
      </View>

      {/* Metrics */}
      {stats?.approval_rate != null && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: C.border, flexDirection: 'row', justifyContent: 'space-around' }}>
          <View style={{ alignItems: 'center' }}>
            <Text style={{ color: C.muted, fontSize: 10, marginBottom: 4 }}>{tx('admin.employerManagementPanel.auto.text.001', 'Approval Rate')}</Text>
            <Text style={{ color: C.green, fontSize: 22, fontWeight: '800' }}>{stats.approval_rate}%</Text>
          </View>
          {stats.avg_approval_hours && (
            <View style={{ alignItems: 'center' }}>
              <Text style={{ color: C.muted, fontSize: 10, marginBottom: 4 }}>{tx('admin.employerManagementPanel.auto.text.002', 'Avg Approval')}</Text>
              <Text style={{ color: C.blue, fontSize: 22, fontWeight: '800' }}>{stats.avg_approval_hours}h</Text>
            </View>
          )}
          <View style={{ alignItems: 'center' }}>
            <Text style={{ color: C.muted, fontSize: 10, marginBottom: 4 }}>{tx('admin.employerManagementPanel.auto.text.003', 'On Hold')}</Text>
            <Text style={{ color: C.yellow, fontSize: 22, fontWeight: '800' }}>{stats?.on_hold ?? 0}</Text>
          </View>
          <View style={{ alignItems: 'center' }}>
            <Text style={{ color: C.muted, fontSize: 10, marginBottom: 4 }}>{tx('admin.employerManagementPanel.auto.text.004', 'Escalated')}</Text>
            <Text style={{ color: C.red, fontSize: 22, fontWeight: '800' }}>{stats?.escalated ?? 0}</Text>
          </View>
        </View>
      )}

      {/* Filter Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {['all', 'pending', 'in_review', 'approved', 'rejected', 'on_hold', 'needs_info', 'escalated'].map(f => (
          <TouchableOpacity key={f} onPress={() => setFilter(f)} style={{
            paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8,
            backgroundColor: filter === f ? (globalThis as any).__alphaColor(C.blue, '20') : C.card,
            borderWidth: 1, borderColor: filter === f ? (globalThis as any).__alphaColor(C.blue, '40') : C.border,
          }} data-testid={`emp-filter-${f}`} testID={`emp-filter-${f}`}>
            <Text style={{ color: filter === f ? C.blue : C.sec, fontSize: 11, fontWeight: '600', textTransform: 'capitalize' }}>
              {f.replace(/_/g, ' ')}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Applications List */}
      {loading ? (
        <ActivityIndicator color={C.blue} style={{ padding: 30 }} />
      ) : apps.length === 0 ? (
        <View style={{ backgroundColor: C.card, padding: 30, borderRadius: 14, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
          <Ionicons name="business-outline" size={36} color={C.border} />
          <Text style={{ color: C.muted, fontSize: 13, marginTop: 8 }}>{tx('admin.employerManagementPanel.auto.text.005', 'No employer applications found')}</Text>
        </View>
      ) : (
        apps.map(app => (
          <View key={app.employer_id} style={{
            backgroundColor: selected?.employer_id === app.employer_id ? (globalThis as any).__alphaColor(C.blue, '08') : C.card,
            padding: 16, borderRadius: 14, marginBottom: 8, borderWidth: 1,
            borderColor: selected?.employer_id === app.employer_id ? (globalThis as any).__alphaColor(C.blue, '30') : C.border,
          }} data-testid={`emp-app-${app.employer_id}`} testID={`emp-app-${app.employer_id}`}>
            <TouchableOpacity accessibilityLabel={tx('admin.employerManagementPanel.auto.accessibility.001', 'app.business_name')} onPress={() => handleSelect(app)}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{app.business_name}</Text>
                  <Text style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>{app.industry} · {app.country}</Text>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor((STATUS_COLORS[app.status] || C.muted), '20') }}>
                      <Text style={{ color: STATUS_COLORS[app.status] || C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{app.status?.replace(/_/g, ' ')}</Text>
                    </View>
                    <Text style={{ color: C.muted, fontSize: 10, alignSelf: 'center' }}>Docs: {app.documents?.length ?? 0}</Text>
                    <Text style={{ color: C.muted, fontSize: 10, alignSelf: 'center' }}>{app.submitted_at ? new Date(app.submitted_at).toLocaleDateString() : ''}</Text>
                  </View>
                </View>
                <Ionicons name={selected?.employer_id === app.employer_id ? 'chevron-up' : 'chevron-down'} size={16} color={C.muted} />
              </View>
            </TouchableOpacity>

            {/* Expanded Detail */}
            {selected?.employer_id === app.employer_id && (
              <View style={{ marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: C.border }}>
                {/* Detail Tabs */}
                <View style={{ flexDirection: 'row', gap: 4, marginBottom: 14 }}>
                  {[
                    { key: 'info', label: 'Info', icon: 'information-circle' },
                    { key: 'docs', label: 'Docs', icon: 'document-attach' },
                    { key: 'messages', label: 'Messages', icon: 'chatbubbles' },
                    { key: 'audit', label: 'Audit', icon: 'time' },
                  ].map(t => (
                    <TouchableOpacity key={t.key} onPress={() => setDetailTab(t.key)} data-testid={`emp-detail-tab-${t.key}`} testID={`emp-detail-tab-${t.key}`}
                      style={{
                        flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
                        paddingVertical: 8, borderRadius: 8,
                        backgroundColor: detailTab === t.key ? (globalThis as any).__alphaColor(C.blue, '20') : 'transparent',
                        borderWidth: 1, borderColor: detailTab === t.key ? (globalThis as any).__alphaColor(C.blue, '30') : 'transparent',
                      }}>
                      <Ionicons name={t.icon as any} size={12} color={detailTab === t.key ? C.blue : C.muted} />
                      <Text style={{ color: detailTab === t.key ? C.blue : C.muted, fontSize: 10, fontWeight: '600' }}>{t.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* Info tab */}
                {detailTab === 'info' && (
                  <View>
                    <View style={{ gap: 6, marginBottom: 14 }}>
                      {[
                        { label: 'Email', value: app.business_email },
                        { label: 'Reg#', value: app.registration_number },
                        { label: 'Contact', value: `${app.contact_person_name} (${app.contact_person_role || 'N/A'})` },
                        { label: 'Phone', value: app.contact_person_phone },
                        ...(app.website ? [{ label: 'Web', value: app.website }] : []),
                        ...(app.description ? [{ label: 'About', value: app.description }] : []),
                      ].map(f => (
                        <Text key={f.label} style={{ color: C.muted, fontSize: 11 }}>{f.label}: <Text style={{ color: C.text }}>{f.value}</Text></Text>
                      ))}
                    </View>

                    {app.status !== 'approved' && app.status !== 'rejected' && (
                      <View>
                        <TextInput value={reason} onChangeText={setReason} placeholder={tx('admin.employerManagementPanel.auto.placeholder.001', 'Reason (for reject/info request)')} placeholderTextColor={C.muted}
                          style={{ backgroundColor: C.bg, color: C.text, borderRadius: 8, padding: 10, fontSize: 12, borderWidth: 1, borderColor: C.border, marginBottom: 6 }} data-testid="emp-reason-input" testID="emp-reason-input" />
                        <TextInput value={note} onChangeText={setNote} placeholder={tx('admin.employerManagementPanel.auto.placeholder.002', 'Internal note (optional)')} placeholderTextColor={C.muted}
                          style={{ backgroundColor: C.bg, color: C.text, borderRadius: 8, padding: 10, fontSize: 12, borderWidth: 1, borderColor: C.border, marginBottom: 10 }} data-testid="emp-note-input" testID="emp-note-input" />
                        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                          {[
                            { action: 'approve', label: 'Approve', color: C.green },
                            { action: 'reject', label: 'Reject', color: C.red },
                            { action: 'request_info', label: 'Request Info', color: C.yellow },
                            { action: 'hold', label: 'Hold', color: C.muted },
                            { action: 'escalate', label: 'Escalate', color: C.purpleText },
                          ].map(a => (
                            <TouchableOpacity key={a.action} onPress={() => handleAction(app.employer_id, a.action)} disabled={processing}
                              style={{ backgroundColor: a.color, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 8, opacity: processing ? 0.6 : 1 }}
                              data-testid={`emp-action-${a.action}-${app.employer_id}`} testID={`emp-action-${a.action}-${app.employer_id}`}>
                              {processing ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{a.label}</Text>}
                            </TouchableOpacity>
                          ))}
                        </View>
                      </View>
                    )}

                    {/* Internal notes */}
                    {(app.internal_notes?.length > 0) && (
                      <View style={{ marginTop: 14 }}>
                        <Text style={{ color: C.muted, fontSize: 11, fontWeight: '700', marginBottom: 6 }}>{tx('admin.employerManagementPanel.auto.text.006', 'Internal Notes')}</Text>
                        {app.internal_notes.map((n: any, i: number) => (
                          <View key={i} style={{ backgroundColor: C.bg, borderRadius: 8, padding: 10, marginBottom: 4, borderLeftWidth: 3, borderLeftColor: C.purple }}>
                            <Text style={{ color: C.text, fontSize: 11 }}>{n.note}</Text>
                            <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>{new Date(n.created_at).toLocaleString()}</Text>
                          </View>
                        ))}
                      </View>
                    )}

                    {/* Quick add note */}
                    {app.status !== 'approved' && (
                      <View style={{ flexDirection: 'row', gap: 6, marginTop: 10 }}>
                        <TextInput value={note} onChangeText={setNote} placeholder={tx('admin.employerManagementPanel.auto.placeholder.003', 'Quick internal note...')} placeholderTextColor={C.muted}
                          style={{ flex: 1, backgroundColor: C.bg, color: C.text, borderRadius: 8, padding: 8, fontSize: 11, borderWidth: 1, borderColor: C.border }} />
                        <TouchableOpacity onPress={() => addNote(app.employer_id)} data-testid={`emp-add-note-${app.employer_id}`} testID={`emp-add-note-${app.employer_id}`}
                          style={{ backgroundColor: C.purple, borderRadius: 8, paddingHorizontal: 12, justifyContent: 'center' }}>
                          <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.employerManagementPanel.auto.text.007', 'Add Note')}</Text>
                        </TouchableOpacity>
                      </View>
                    )}
                  </View>
                )}

                {/* Documents tab */}
                {detailTab === 'docs' && (
                  <View>
                    {(app.documents?.length > 0) ? app.documents.map((doc: any) => (
                      <View key={doc.doc_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.bg, borderRadius: 10, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: C.border }}>
                        <Ionicons name={doc.content_type?.includes('pdf') ? 'document-text' : 'image'} size={20} color={C.cyan} />
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{doc.type?.replace(/_/g, ' ')}</Text>
                          <Text style={{ color: C.muted, fontSize: 10 }}>{doc.filename} · {(doc.file_size / 1024).toFixed(0)} KB</Text>
                          {!!doc.purpose && <Text style={{ color: C.muted, fontSize: 9 }}>Purpose: {String(doc.purpose).replace(/_/g, ' ')}</Text>}
                          <Text style={{ color: C.muted, fontSize: 9 }}>Uploaded: {new Date(doc.uploaded_at).toLocaleDateString()}</Text>
                        </View>
                        <TouchableOpacity
                          onPress={() => downloadDoc(app.employer_id, doc)}
                          disabled={downloadingDocId === String(doc.doc_id)}
                          style={{ backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '30'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }}
                          data-testid={`emp-doc-download-${doc.doc_id}`}
                          testID={`emp-doc-download-${doc.doc_id}`}
                        >
                          {downloadingDocId === String(doc.doc_id) ? (
                            <ActivityIndicator size="small" color={C.blue} />
                          ) : (
                            <Text style={{ color: C.blue, fontSize: 10, fontWeight: '700' }}>{tx('admin.employerManagementPanel.auto.text.008', 'Download')}</Text>
                          )}
                        </TouchableOpacity>
                      </View>
                    )) : (
                      <View style={{ padding: 20, alignItems: 'center' }}>
                        <Ionicons name="document-outline" size={28} color={C.border} />
                        <Text style={{ color: C.muted, fontSize: 12, marginTop: 6 }}>{tx('admin.employerManagementPanel.auto.text.009', 'No documents uploaded')}</Text>
                      </View>
                    )}
                  </View>
                )}

                {/* Messages tab */}
                {detailTab === 'messages' && (
                  <View>
                    {messages.length === 0 ? (
                      <Text style={{ color: C.muted, fontSize: 12, padding: 12 }}>{tx('admin.employerManagementPanel.auto.text.010', 'No messages yet')}</Text>
                    ) : (
                      <View style={{ gap: 6, marginBottom: 10, maxHeight: 300 }}>
                        {messages.map((m: any) => (
                          <View key={m.message_id} style={{
                            backgroundColor: m.sender_role === 'admin' ? (globalThis as any).__alphaColor(C.blue, '10') : C.bg,
                            borderRadius: 8, padding: 10, borderWidth: 1,
                            borderColor: m.sender_role === 'admin' ? (globalThis as any).__alphaColor(C.blue, '20') : C.border,
                          }}>
                            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 }}>
                              <Text style={{ color: m.sender_role === 'admin' ? C.blue : C.green, fontSize: 10, fontWeight: '700' }}>
                                {m.sender_role === 'admin' ? `Admin (${m.sender_name})` : m.sender_name || 'Employer'}
                              </Text>
                              <Text style={{ color: C.muted, fontSize: 9 }}>{new Date(m.created_at).toLocaleString()}</Text>
                            </View>
                            <Text style={{ color: C.text, fontSize: 11, lineHeight: 16 }}>{m.message}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                    <View style={{ flexDirection: 'row', gap: 6 }}>
                      <TextInput value={newMsg} onChangeText={setNewMsg} placeholder={tx('admin.employerManagementPanel.auto.placeholder.004', 'Reply to employer...')} placeholderTextColor={C.muted}
                        data-testid={`emp-admin-msg-input-${app.employer_id}`} testID={`emp-admin-msg-input-${app.employer_id}`}
                        style={{ flex: 1, backgroundColor: C.bg, color: C.text, borderRadius: 8, padding: 8, fontSize: 11, borderWidth: 1, borderColor: C.border }} />
                      <TouchableOpacity onPress={() => sendMessage(app.employer_id)} disabled={sendingMsg || !newMsg.trim()}
                        data-testid={`emp-admin-send-msg-${app.employer_id}`} testID={`emp-admin-send-msg-${app.employer_id}`}
                        style={{ backgroundColor: C.blue, borderRadius: 8, paddingHorizontal: 12, justifyContent: 'center', opacity: sendingMsg || !newMsg.trim() ? 0.5 : 1 }}>
                        <Ionicons name="send" size={12} color="var(--app-primary-text)" />
                      </TouchableOpacity>
                    </View>
                  </View>
                )}

                {/* Audit Trail tab */}
                {detailTab === 'audit' && (
                  <View>
                    {auditTrail.length === 0 ? (
                      <Text style={{ color: C.muted, fontSize: 12, padding: 12 }}>{tx('admin.employerManagementPanel.auto.text.011', 'No audit events')}</Text>
                    ) : (
                      auditTrail.map((event: any, i: number) => (
                        <View key={event.audit_id || i} style={{ flexDirection: 'row', gap: 10, marginBottom: 8 }}>
                          <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.blue, marginTop: 6 }} />
                          <View style={{ flex: 1 }}>
                            <Text style={{ color: C.text, fontSize: 11, fontWeight: '600' }}>{event.action?.replace(/_/g, ' ')}</Text>
                            {event.details?.reason && <Text style={{ color: C.muted, fontSize: 10 }}>Reason: {event.details.reason}</Text>}
                            <Text style={{ color: C.muted, fontSize: 9 }}>{new Date(event.created_at).toLocaleString()} · {event.actor_id === 'system' ? 'System' : event.actor_id}</Text>
                          </View>
                        </View>
                      ))
                    )}
                  </View>
                )}
              </View>
            )}
          </View>
        ))
      )}
    </View>
  );
}
