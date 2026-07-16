/**
 * (`var(--app-success)` success pill, `var(--app-primary-text)` white text on colored buttons, `var(--app-error)`
 * error text on error surfaces) are intentional brand/status tokens that must
 * remain constant across light/dark themes. Structural chrome (backgrounds,
 * borders, primary/secondary text) uses `AC.*` via useAdminTheme().
 */
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, TextInput, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type ThreadMessage = {
  thread_id: string;
  application_id: string;
  direction: 'outbound' | 'inbound' | string;
  from_email: string;
  to_email: string;
  subject: string;
  body_text: string;
  body_html: string;
  message_id: string;
  correlation_signal: string;
  received_at: string;
};

type ThreadResponse = {
  application_id: string;
  messages: ThreadMessage[];
  total: number;
  unread_inbound: number;
};

const _fmt = (iso: string) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
};

export const ApplicantThreadPanel: React.FC<{ applicationId: string }> = ({ applicationId }) => {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [data, setData] = useState<ThreadResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);
  const [err, setErr] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const res = await api.get(`/careers/applications/${applicationId}/thread`);
      setData(res.data as ThreadResponse);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Unable to load conversation');
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    load();
  }, [load]);

  const markRead = useCallback(async () => {
    if (!data || data.unread_inbound === 0) return;
    try {
      await api.post(`/careers/applications/${applicationId}/thread/mark-read`, {});
      setData((d) => (d ? { ...d, unread_inbound: 0 } : d));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ApplicantThreadPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [applicationId, data]);

  // ── Recruiter reply composer ─────────────────────────────────────
  const [composerOpen, setComposerOpen] = useState(false);
  const [replyBody, setReplyBody] = useState('');
  const [sending, setSending] = useState(false);

  const sendReply = useCallback(async () => {
    const body = replyBody.trim();
    if (!body) return;
    setSending(true);
    try {
      const res = await api.post(`/careers/applications/${applicationId}/thread/reply`, { body });
      if (res?.data?.ok) {
        setReplyBody('');
        setComposerOpen(false);
        await load();
      } else {
        Alert.alert(tx('admin.applicantThreadPanel.alerts.replyFailedTitle', 'Reply failed'), res?.data?.detail || 'Please try again');
      }
    } catch (e: any) {
      Alert.alert(
        tx('admin.applicantThreadPanel.alerts.replyFailedTitle', 'Reply failed'),
        e?.response?.data?.detail || 'Unable to send — check email provider configuration.',
      );
    } finally {
      setSending(false);
    }
  }, [applicationId, replyBody, load]);

  const messages = data?.messages || [];
  const unread = data?.unread_inbound || 0;

  return (
    <View
      style={{
        marginTop: 14,
        marginBottom: 14,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: AC.border,
        backgroundColor: AC.surface,
        overflow: 'hidden',
      }}
      data-testid="applicant-thread-panel"
      testID="applicant-thread-panel"
    >
      <TouchableOpacity accessibilityLabel="Applicant thread toggle button"
        onPress={() => setExpanded((v) => !v)}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingVertical: 12,
          paddingHorizontal: 14,
          backgroundColor: AC.surfaceAlt,
        }}
        data-testid="applicant-thread-toggle"
        testID="applicant-thread-toggle"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="chatbubbles-outline" size={16} color={AC.accent} />
          <Text style={{ fontSize: 13, fontWeight: '800', color: AC.primaryText }}>
            {tx('admin.applicantThreadPanel.header.title', 'Conversation Thread')}
          </Text>
          <Text style={{ fontSize: 11, color: AC.textDim }}>
            ({messages.length} message{messages.length === 1 ? '' : 's'})
          </Text>
          {unread > 0 && (
            <View
              style={{
                backgroundColor: AC.success,
                borderRadius: 10,
                paddingHorizontal: 7,
                paddingVertical: 2,
              }}
              data-testid="applicant-thread-unread-pill"
              testID="applicant-thread-unread-pill"
            >
              <Text style={{ color: AC.primaryText, fontSize: 10, fontWeight: '800' }}>
                {unread} new
              </Text>
            </View>
          )}
        </View>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={16}
          color={AC.textDim}
        />
      </TouchableOpacity>

      {expanded && (
        <View style={{ padding: 12 }}>
          {loading && <ActivityIndicator size="small" color={AC.accent} />}

          {!loading && err && (
            <Text style={{ color: AC.error, fontSize: 12 }}>{err}</Text>
          )}

          {!loading && !err && messages.length === 0 && (
            <View
              style={{
                padding: 14,
                borderRadius: 10,
                backgroundColor: AC.surfaceAlt,
                borderWidth: 1,
                borderColor: AC.border,
                borderStyle: 'dashed' as any,
              }}
              data-testid="applicant-thread-empty"
              testID="applicant-thread-empty"
            >
              <Text style={{ color: AC.textDim, fontSize: 12, lineHeight: 18 }}>
                No messages yet. When this applicant replies to the confirmation email
                (to <Text style={{ fontWeight: '700', color: AC.primaryText }}>{tx('admin.applicantThreadPanel.labels.hiringEmail', 'hiring@realaicoach.app')}</Text>),
                their replies will appear here automatically, threaded by Application ID.
              </Text>
            </View>
          )}

          {!loading && !err && messages.length > 0 && (
            <ScrollView
              style={{ maxHeight: 260 }}
              contentContainerStyle={{ gap: 8 }}
              data-testid="applicant-thread-messages"
              testID="applicant-thread-messages"
            >
              {messages.map((msg) => {
                const isInbound = msg.direction === 'inbound';
                return (
                  <View
                    key={msg.thread_id}
                    style={{
                      padding: 10,
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: isInbound ? `${AC.success}33` : AC.border,
                      backgroundColor: isInbound ? AC.successSoft : AC.surfaceAlt,
                      borderLeftWidth: 3,
                      borderLeftColor: isInbound ? AC.success : AC.accent,
                    }}
                    data-testid={`thread-msg-${msg.thread_id}`}
                    testID={`thread-msg-${msg.thread_id}`}
                  >
                    <View
                      style={{
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        marginBottom: 4,
                      }}
                    >
                      <Text style={{ fontSize: 11, fontWeight: '800', color: isInbound ? AC.successText : AC.accent }}>
                        {isInbound ? 'APPLICANT' : 'RECRUITER'}
                      </Text>
                      <Text style={{ fontSize: 10, color: AC.textDim }}>
                        {_fmt(msg.received_at)}
                      </Text>
                    </View>
                    <Text style={{ fontSize: 11, color: AC.textDim, marginBottom: 4 }} numberOfLines={1}>
                      {isInbound
                        ? `From: ${msg.from_email}`
                        : `To: ${msg.to_email}`}
                    </Text>
                    <Text
                      style={{ fontSize: 12, fontWeight: '700', color: AC.primaryText, marginBottom: 4 }}
                      numberOfLines={1}
                    >
                      {msg.subject || '(no subject)'}
                    </Text>
                    {!!msg.body_text && (
                      <Text
                        style={{ fontSize: 12, color: AC.primaryText, lineHeight: 18 }}
                        numberOfLines={6}
                      >
                        {msg.body_text}
                      </Text>
                    )}
                  </View>
                );
              })}
            </ScrollView>
          )}

          {!loading && unread > 0 && (
            <TouchableOpacity accessibilityLabel="Applicant thread mark read button"
              onPress={markRead}
              style={{
                marginTop: 10,
                alignSelf: 'flex-start',
                paddingVertical: 6,
                paddingHorizontal: 12,
                borderRadius: 8,
                backgroundColor: AC.surfaceAlt,
                borderWidth: 1,
                borderColor: AC.border,
              }}
              data-testid="applicant-thread-mark-read"
              testID="applicant-thread-mark-read"
            >
              <Text style={{ fontSize: 11, fontWeight: '700', color: AC.primaryText }}>
                {tx('admin.applicantThreadPanel.actions.markAllRead', 'Mark all read')}
              </Text>
            </TouchableOpacity>
          )}

          {/* Recruiter reply composer */}
          {!loading && !err && (
            <View style={{ marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: AC.border }}>
              {!composerOpen ? (
                <TouchableOpacity accessibilityLabel="Applicant thread compose open button"
                  onPress={() => setComposerOpen(true)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 6,
                    alignSelf: 'flex-start',
                    paddingVertical: 8,
                    paddingHorizontal: 14,
                    borderRadius: 10,
                    backgroundColor: AC.accent,
                  }}
                  data-testid="applicant-thread-compose-open"
                  testID="applicant-thread-compose-open"
                >
                  <Ionicons name="create-outline" size={14} color={AC.primaryText} />
                  <Text style={{ color: AC.primaryText, fontWeight: '800', fontSize: 12 }}>
                    {tx('admin.applicantThreadPanel.actions.replyToApplicant', 'Reply to applicant')}
                  </Text>
                </TouchableOpacity>
              ) : (
                <View data-testid="applicant-thread-composer" testID="applicant-thread-composer">
                  <Text style={{ fontSize: 11, fontWeight: '700', color: AC.textDim, marginBottom: 6 }}>
                    Reply to applicant via {` `}
                    <Text style={{ color: AC.primaryText }}>{tx('admin.applicantThreadPanel.labels.hiringEmail', 'hiring@realaicoach.app')}</Text>
                  </Text>
                  <TextInput
                    value={replyBody}
                    onChangeText={setReplyBody}
                    multiline
                    placeholder={tx('admin.applicantThreadPanel.inputs.replyPlaceholder', 'Type your reply — the applicant will receive it from hiring@realaicoach.app and their reply will auto-thread here.')}
                    placeholderTextColor={AC.textDim}
                    style={{
                      minHeight: 110,
                      borderWidth: 1,
                      borderColor: AC.border,
                      borderRadius: 10,
                      padding: 10,
                      color: AC.primaryText,
                      backgroundColor: AC.surface,
                      fontSize: 13,
                      lineHeight: 19,
                      textAlignVertical: 'top' as any,
                    }}
                    data-testid="applicant-thread-reply-input"
                    testID="applicant-thread-reply-input"
                    editable={!sending}
                  />
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                    <TouchableOpacity accessibilityLabel="Applicant thread send reply button"
                      onPress={sendReply}
                      disabled={sending || !replyBody.trim()}
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 6,
                        paddingVertical: 8,
                        paddingHorizontal: 14,
                        borderRadius: 10,
                        backgroundColor: sending || !replyBody.trim() ? AC.surfaceAlt : AC.accent,
                        opacity: sending || !replyBody.trim() ? 0.6 : 1,
                      }}
                      data-testid="applicant-thread-send-reply"
                      testID="applicant-thread-send-reply"
                    >
                      {sending ? (
                        <ActivityIndicator size="small" color={AC.primaryText} />
                      ) : (
                        <Ionicons name="send" size={13} color={AC.primaryText} />
                      )}
                      <Text style={{ color: AC.primaryText, fontWeight: '800', fontSize: 12 }}>
                        {sending ? 'Sending…' : 'Send reply'}
                      </Text>
                    </TouchableOpacity>
                    <TouchableOpacity accessibilityLabel="Applicant thread cancel reply button"
                      onPress={() => {
                        setComposerOpen(false);
                        setReplyBody('');
                      }}
                      disabled={sending}
                      style={{
                        paddingVertical: 8,
                        paddingHorizontal: 14,
                        borderRadius: 10,
                        borderWidth: 1,
                        borderColor: AC.border,
                      }}
                      data-testid="applicant-thread-cancel-reply"
                      testID="applicant-thread-cancel-reply"
                    >
                      <Text style={{ color: AC.textDim, fontWeight: '700', fontSize: 12 }}>
                        {tx('admin.applicantThreadPanel.actions.cancel', 'Cancel')}
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </View>
          )}
        </View>
      )}
    </View>
  );
};

export default ApplicantThreadPanel;
