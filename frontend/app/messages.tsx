import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, RefreshControl, KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useRealtime } from '../src/context/RealtimeContext';
import AppShell from '../src/components/AppShell';
import { ChatSkeleton} from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

interface Message {
  message_id: string;
  sender_id: string;
  sender_name: string;
  content: string;
  read: boolean;
  read_at?: string;
  created_at: string;
}

interface Conversation {
  conversation_id: string;
  participants: string[];
  other_user?: { user_id: string; name: string; email: string };
  last_message: string;
  last_message_at: string;
  last_sender_id: string;
  my_unread: number;
  subject?: string;
}

interface SearchUser {
  user_id: string;
  name: string;
  email: string;
  roles?: string[];
}

export function MessagesContent() {
  return <MessagesInner />;
}

function MessagesInner() {
  const _router = useRouter();
  const { colors } = useTheme();
  const { t } = useTranslation();

  const [view, setView] = useState<'inbox' | 'thread' | 'new'>('inbox');
  const [convos, setConvos] = useState<Conversation[]>([]);
  const [totalUnread, setTotalUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeConv, setActiveConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [messageText, setMessageText] = useState('');
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const [currentUserId, setCurrentUserId] = useState('');

  // New conversation
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchUser[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedRecipient, setSelectedRecipient] = useState<SearchUser | null>(null);
  const [newSubject, setNewSubject] = useState('');
  const [newMessage, setNewMessage] = useState('');
  const [otherTyping, setOtherTyping] = useState(false);
  const [recoverableError, setRecoverableError] = useState('');
  const _typingTimerRef = useRef<any>(null);
  const lastTypingSentRef = useRef(0);
  const { subscribeType } = useRealtime();

  const C = useMemo(() => ({
    primary: colors.primary, bg: colors.surface, bgSoft: colors.surfaceHover, card: colors.card,
    text: colors.text, textSec: colors.textSec, textMuted: colors.textMuted, border: colors.border, primaryText: colors.primaryText,
  }), [colors]);

  // Get current user
  useEffect(() => {
    api.get('/auth/me')
      .then(r => setCurrentUserId(r.data?.user_id || ''))
      .catch((error) => {
        handleAppRecoverableError({
          scope: 'messages.auth-me',
          error,
          message: 'Could not resolve current profile context.',
          setError: setRecoverableError,
          onRetry: () => { void fetchInbox(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
      });
  }, []);

  const fetchInbox = useCallback(async () => {
    try {
      const res = await api.get('/messages/conversations');
      setConvos(res.data.conversations || []);
      setTotalUnread(res.data.total_unread || 0);
      setRecoverableError('');
    } catch (e) {
      handleAppRecoverableError({
        scope: 'messages.fetch-inbox',
        error: e,
        message: 'Unable to load inbox right now.',
        setError: setRecoverableError,
        onRetry: () => { void fetchInbox(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { fetchInbox(); }, [fetchInbox]);

  const refreshThreadMessages = useCallback(async (conversationId: string, markRead: boolean = false) => {
    try {
      const res = await api.get(`/messages/conversations/${conversationId}`);
      setMessages(res.data.messages || []);
      if (markRead) {
        api.post(`/messages/conversations/${conversationId}/read`).catch(() => {});
      }
    } catch (e) {
      handleAppRecoverableError({
        scope: 'messages.refresh-thread',
        error: e,
        message: 'Unable to refresh conversation thread.',
        setError: setRecoverableError,
        onRetry: () => { void refreshThreadMessages(conversationId, markRead); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, []);

  // Realtime updates for inbox/thread via shared RealtimeContext WS bus
  useEffect(() => {
    const unsubNewMessage = subscribeType('new_message', (evt) => {
      void fetchInbox();

      if (!activeConv?.conversation_id || evt?.conversation_id !== activeConv.conversation_id) return;
      const shouldMarkRead = String(evt?.sender_id || '') !== currentUserId;
      void refreshThreadMessages(activeConv.conversation_id, shouldMarkRead);
    });

    const unsubReadReceipt = subscribeType('read_receipt', (evt) => {
      if (activeConv?.conversation_id && evt?.conversation_id === activeConv.conversation_id) {
        void refreshThreadMessages(activeConv.conversation_id, false);
      }
      void fetchInbox();
    });

    const unsubTypingIndicator = subscribeType('typing_indicator', (evt) => {
      if (!activeConv?.conversation_id || evt?.conversation_id !== activeConv.conversation_id) return;
      if (String(evt?.user_id || '') === currentUserId) return;

      setOtherTyping(true);
      if (_typingTimerRef.current) clearTimeout(_typingTimerRef.current);
      _typingTimerRef.current = setTimeout(() => setOtherTyping(false), 2500);
    });

    return () => {
      unsubNewMessage();
      unsubReadReceipt();
      unsubTypingIndicator();
      if (_typingTimerRef.current) {
        clearTimeout(_typingTimerRef.current);
        _typingTimerRef.current = null;
      }
    };
  }, [activeConv?.conversation_id, currentUserId, fetchInbox, refreshThreadMessages, subscribeType]);

  const openThread = async (conv: Conversation) => {
    setActiveConv(conv);
    setView('thread');
    setMsgLoading(true);
    setOtherTyping(false);
    try {
      await refreshThreadMessages(conv.conversation_id, true);
      fetchInbox();
      setTimeout(() => scrollRef.current?.scrollToEnd?.({ animated: false }), 200);
      setRecoverableError('');
    } catch (e) {
      handleAppRecoverableError({
        scope: 'messages.open-thread',
        error: e,
        message: 'Unable to open this conversation right now.',
        setError: setRecoverableError,
        onRetry: () => { void openThread(conv); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
    finally { setMsgLoading(false); }
  };

  const handleSend = async () => {
    if (!messageText.trim() || !activeConv) return;
    setSending(true);
    try {
      const res = await api.post(`/messages/conversations/${activeConv.conversation_id}/send`, {
        message: messageText,
      });
      if (res.data.success) {
        setMessages(prev => [...prev, res.data.message]);
        setMessageText('');
        setTimeout(() => scrollRef.current?.scrollToEnd?.({ animated: true }), 100);
        fetchInbox();
      }
    } catch (e: any) {
      handleAppRecoverableError({
        scope: 'messages.send',
        error: e,
        message: e?.response?.data?.detail || 'Failed to send message.',
        setError: setRecoverableError,
        onRetry: () => { void handleSend(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      if (Platform.OS === 'web') window.alert(e?.response?.data?.detail || 'Failed to send');
    } finally { setSending(false); }
  };

  const handleTyping = useCallback((text: string) => {
    setMessageText(text);
    if (!activeConv) return;
    const now = Date.now();
    if (now - lastTypingSentRef.current > 3000) {
      lastTypingSentRef.current = now;
      api.post(`/messages/conversations/${activeConv.conversation_id}/typing`).catch(() => {});
    }
  }, [activeConv]);

  const handleSearch = async (q: string) => {
    setSearchQuery(q);
    if (q.length < 2) { setSearchResults([]); return; }
    setSearching(true);
    try {
      const res = await api.get(`/messages/search-users?q=${encodeURIComponent(q)}`);
      setSearchResults(res.data.users || []);
    } catch (_e) { setSearchResults([]); }
    finally { setSearching(false); }
  };

  const handleStartConversation = async () => {
    if (!selectedRecipient || !newMessage.trim()) return;
    setSending(true);
    try {
      const res = await api.post('/messages/conversations', {
        recipient_id: selectedRecipient.user_id,
        message: newMessage,
        subject: newSubject || undefined,
      });
      if (res.data.success) {
        setNewMessage(''); setNewSubject(''); setSearchQuery('');
        setSelectedRecipient(null); setSearchResults([]);
        fetchInbox();
        // Open the new conversation
        const convRes = await api.get(`/messages/conversations/${res.data.conversation_id}`);
        setActiveConv(convRes.data.conversation);
        setMessages(convRes.data.messages || []);
        setView('thread');
      }
    } catch (e: any) {
      if (Platform.OS === 'web') window.alert(e?.response?.data?.detail || 'Failed');
    } finally { setSending(false); }
  };

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffH = diffMs / (1000 * 60 * 60);
      if (diffH < 1) return `${Math.max(1, Math.floor(diffMs / 60000))}m ago`;
      if (diffH < 24) return `${Math.floor(diffH)}h ago`;
      if (diffH < 168) return d.toLocaleDateString('en-US', { weekday: 'short' });
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { return ''; }
  };

  // ── Inbox View ──
  const renderInbox = () => (
    <ScrollView showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchInbox(); }} tintColor={C.primary} />}
      contentContainerStyle={{ paddingBottom: 60 }}>

      {loading ? (
        <ChatSkeleton />
      ) : convos.length === 0 ? (
        <View style={{ alignItems: 'center', paddingVertical: 60 }} data-testid="empty-inbox" testID="empty-inbox">
          <Ionicons name="chatbubbles-outline" size={52} color={C.textMuted} />
          <Text style={{ fontSize: 18, fontWeight: '700', color: C.text, marginTop: 14 }}>{t("autofix.precision12.no.messages.yet")}</Text>
          <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 4 }}>{t("autofix.precision12.start.a.conversation.with.an.employer.or.candidate")}</Text>
          <TouchableOpacity data-testid="empty-new-msg-btn" testID="empty-new-msg-btn" style={[ss.actionBtn, { backgroundColor: C.primary, marginTop: 18 }]} onPress={() => setView('new')}>
            <Ionicons name="create" size={16} color={C.primaryText} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.primaryText }}>{t("autofix.batch2.new.message")}</Text>
          </TouchableOpacity>
        </View>
      ) : (
        convos.map(conv => {
          const other = conv.other_user || {};
          const hasUnread = (conv.my_unread || 0) > 0;
          return (
            <TouchableOpacity key={conv.conversation_id} data-testid={`conv-${conv.conversation_id}`} testID={`conv-${conv.conversation_id}`}
              style={[ss.convCard, { borderBottomColor: C.border }, hasUnread && { backgroundColor: (globalThis as any).__alphaColor(C.primary, '06') }]}
              onPress={() => openThread(conv)} activeOpacity={0.7}>
              <View style={[ss.avatar, { backgroundColor: hasUnread ? C.primary : C.bgSoft }]}>
                <Text style={{ fontSize: 15, fontWeight: '700', color: hasUnread ? C.primaryText : C.textMuted }}>
                  {(other.name || '?')[0]?.toUpperCase()}
                </Text>
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ fontSize: 14, fontWeight: hasUnread ? '800' : '600', color: C.text }} numberOfLines={1}>
                    {other.name || other.email || 'User'}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>{formatTime(conv.last_message_at)}</Text>
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 2 }}>
                  <Text style={{ flex: 1, fontSize: 12, color: hasUnread ? C.text : C.textMuted, fontWeight: hasUnread ? '600' : '400' }} numberOfLines={1}>
                    {conv.last_sender_id === currentUserId ? 'You: ' : ''}{conv.last_message}
                  </Text>
                  {hasUnread && (
                    <View style={[ss.badge, { backgroundColor: C.primary }]}>
                      <Text style={{ fontSize: 10, fontWeight: '800', color: C.primaryText }}>{conv.my_unread}</Text>
                    </View>
                  )}
                </View>
              </View>
            </TouchableOpacity>
          );
        })
      )}
    </ScrollView>
  );

  // ── Thread View ──
  const renderThread = () => {
    const other = activeConv?.other_user || {};
    return (
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {/* Thread Header */}
        <View style={[ss.threadHeader, { backgroundColor: C.card, borderBottomColor: C.border }]} data-testid="thread-header" testID="thread-header">
          <TouchableOpacity style={[ss.backBtn, { backgroundColor: C.bgSoft }]} onPress={() => setView('inbox')} data-testid="thread-back-btn" testID="thread-back-btn">
            <Ionicons name="arrow-back" size={20} color={C.text} />
          </TouchableOpacity>
          <View style={[ss.headerAvatar, { backgroundColor: C.primary }]}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.primaryText }}>{(other.name || '?')[0]?.toUpperCase()}</Text>
          </View>
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={{ fontSize: 15, fontWeight: '700', color: C.text }}>{other.name || 'User'}</Text>
            <Text style={{ fontSize: 11, color: C.textMuted }}>{other.email || ''}</Text>
          </View>
        </View>

        {/* Messages */}
        <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ padding: 14, paddingBottom: 10 }}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd?.({ animated: false })}>
          {msgLoading ? (
            <View style={{ alignItems: 'center', paddingVertical: 40 }}><ActivityIndicator color={C.primary} /></View>
          ) : messages.length === 0 ? (
            <View style={{ alignItems: 'center', paddingVertical: 40 }}>
              <Ionicons name="chatbubble-outline" size={36} color={C.textMuted} />
              <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 8 }}>{t("autofix.precision12.start.the.conversation")}</Text>
            </View>
          ) : (
            messages.map(msg => {
              const isMe = msg.sender_id === currentUserId;
              return (
                <View key={msg.message_id} style={[ss.msgRow, isMe && { justifyContent: 'flex-end' }]} data-testid={`msg-${msg.message_id}`} testID={`msg-${msg.message_id}`}>
                  <View style={[ss.msgBubble,
                    isMe ? { backgroundColor: C.primary, borderBottomRightRadius: 4 } : { backgroundColor: C.bgSoft, borderBottomLeftRadius: 4 }]}>
                    <Text style={{ fontSize: 14, color: isMe ? C.primaryText : C.text, lineHeight: 20 }}>{msg.content}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', marginTop: 4, gap: 4 }}>
                      <Text style={{ fontSize: 10, color: isMe ? 'rgba(255,255,255,0.6)' : C.textMuted }}>
                        {formatTime(msg.created_at)}
                      </Text>
                      {isMe && (
                        <Ionicons
                          name={msg.read ? 'checkmark-done' : 'checkmark'}
                          size={12}
                          color={msg.read ? colors.success : 'rgba(255,255,255,0.5)'}
                          data-testid={`msg-read-indicator-${msg.message_id}`} testID={`msg-read-indicator-${msg.message_id}`}
                        />
                      )}
                    </View>
                  </View>
                </View>
              );
            })
          )}
        </ScrollView>

        {/* Typing Indicator */}
        {otherTyping && (
          <View style={{ paddingHorizontal: 14, paddingVertical: 6 }} data-testid="typing-indicator" testID="typing-indicator">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ flexDirection: 'row', gap: 3 }}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.textMuted, opacity: 0.6 }} />
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.textMuted, opacity: 0.4 }} />
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.textMuted, opacity: 0.2 }} />
              </View>
              <Text style={{ fontSize: 11, color: C.textMuted, fontStyle: 'italic' }}>{other.name || 'User'}{t("autofix.precision12.is.typing")}</Text>
            </View>
          </View>
        )}

        {/* Message Input */}
        <View style={[ss.inputBar, { backgroundColor: C.card, borderTopColor: C.border }]}>
          <View style={[ss.inputWrap, { backgroundColor: C.bgSoft, borderColor: C.border }]}>
            <TextInput data-testid="message-input" testID="message-input" style={[ss.messageInput, { color: C.text }]}
              placeholder="Type a message..." placeholderTextColor={C.textMuted}
              value={messageText} onChangeText={handleTyping} multiline maxLength={2000}
              onSubmitEditing={handleSend} />
            <TouchableOpacity data-testid="send-message-btn" testID="send-message-btn"
              style={[ss.sendBtn, { backgroundColor: C.primary }, (!messageText.trim() || sending) && { opacity: 0.4 }]}
              onPress={handleSend} disabled={!messageText.trim() || sending}>
              {sending ? <ActivityIndicator size="small" color={C.primaryText} /> : <Ionicons name="send" size={16} color={C.primaryText} />}
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    );
  };

  // ── New Conversation View ──
  const renderNewConversation = () => (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: 16, paddingBottom: 60 }}>
      <View style={[ss.formCard, { backgroundColor: C.card, borderColor: C.border }]} data-testid="new-message-form" testID="new-message-form">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 18 }}>
          <View style={[ss.formIcon, { backgroundColor: (globalThis as any).__alphaColor(C.primary, '14') }]}>
            <Ionicons name="create" size={20} color={C.primary} />
          </View>
          <Text style={{ fontSize: 17, fontWeight: '800', color: C.text }}>{t("autofix.batch2.new.message")}</Text>
        </View>

        {/* Recipient Search */}
        <Text style={[ss.label, { color: C.text }]}>To</Text>
        {selectedRecipient ? (
          <View style={[ss.selectedRecip, { backgroundColor: C.bgSoft, borderColor: C.border }]}>
            <View style={[ss.recipAvatar, { backgroundColor: C.primary }]}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.primaryText }}>{selectedRecipient.name[0]?.toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{selectedRecipient.name}</Text>
              <Text style={{ fontSize: 11, color: C.textMuted }}>{selectedRecipient.email}</Text>
            </View>
            <TouchableOpacity onPress={() => setSelectedRecipient(null)} data-testid="clear-recipient-btn" testID="clear-recipient-btn">
              <Ionicons name="close-circle" size={20} color={C.textMuted} />
            </TouchableOpacity>
          </View>
        ) : (
          <>
            <View style={[ss.searchWrap, { backgroundColor: C.bgSoft, borderColor: C.border }]}>
              <Ionicons name="search" size={16} color={C.textMuted} />
              <TextInput data-testid="search-recipient-input" testID="search-recipient-input" style={[ss.searchInput, { color: C.text }]}
                placeholder="Search by name or email..." placeholderTextColor={C.textMuted}
                value={searchQuery} onChangeText={handleSearch} />
              {searching && <ActivityIndicator size="small" color={C.primary} />}
            </View>
            {searchResults.length > 0 && (
              <View style={[ss.searchResults, { backgroundColor: C.card, borderColor: C.border }]}>
                {searchResults.map(u => (
                  <TouchableOpacity key={u.user_id} data-testid={`user-result-${u.user_id}`} testID={`user-result-${u.user_id}`}
                    style={[ss.userResult, { borderBottomColor: C.border }]}
                    onPress={() => { setSelectedRecipient(u); setSearchResults([]); setSearchQuery(''); }}>
                    <View style={[ss.recipAvatar, { backgroundColor: (globalThis as any).__alphaColor(C.primary, '20') }]}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.primary }}>{u.name[0]?.toUpperCase()}</Text>
                    </View>
                    <View>
                      <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{u.name}</Text>
                      <Text style={{ fontSize: 11, color: C.textMuted }}>{u.email}</Text>
                    </View>
                  </TouchableOpacity>
                ))}
              </View>
            )}
          </>
        )}

        {/* Subject (optional) */}
        <Text style={[ss.label, { color: C.text, marginTop: 14 }]}>{t("autofix.precision12.subject.optional")}</Text>
        <View style={[ss.fieldWrap, { backgroundColor: C.bgSoft, borderColor: C.border }]}>
          <TextInput data-testid="new-msg-subject" testID="new-msg-subject" style={[ss.fieldInput, { color: C.text }]}
            placeholder="e.g. Regarding Job Application" placeholderTextColor={C.textMuted}
            value={newSubject} onChangeText={setNewSubject} maxLength={200} />
        </View>

        {/* Message */}
        <Text style={[ss.label, { color: C.text, marginTop: 14 }]}>{t("autofix.precision12.message")}</Text>
        <View style={[ss.fieldWrap, { backgroundColor: C.bgSoft, borderColor: C.border, alignItems: 'flex-start' }]}>
          <TextInput data-testid="new-msg-body" testID="new-msg-body" style={[ss.fieldInput, { color: C.text, minHeight: 100, textAlignVertical: 'top' }]}
            placeholder="Type your message..." placeholderTextColor={C.textMuted}
            value={newMessage} onChangeText={setNewMessage} multiline maxLength={2000} />
        </View>

        <TouchableOpacity data-testid="send-new-msg-btn" testID="send-new-msg-btn"
          style={[ss.submitBtn, { backgroundColor: C.primary }, (!selectedRecipient || !newMessage.trim() || sending) && { opacity: 0.4 }]}
          onPress={handleStartConversation} disabled={!selectedRecipient || !newMessage.trim() || sending}>
          {sending ? <ActivityIndicator color={C.primaryText} /> : (
            <><Ionicons name="send" size={16} color={C.primaryText} /><Text style={{ fontSize: 14, fontWeight: '700', color: C.primaryText }}>{t("autofix.precision12.send.message")}</Text></>
          )}
        </TouchableOpacity>
      </View>
    </ScrollView>
  );

  return (
    <View style={{ flex: 1, backgroundColor: C.bg }}>
        {recoverableError ? (
          <View
            style={{ marginHorizontal: 14, marginTop: 12, marginBottom: 6, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: C.primary + '35', backgroundColor: C.bgSoft, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
            data-testid="messages-recoverable-error-banner"
            testID="messages-recoverable-error-banner"
          >
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', flex: 1 }} data-testid="messages-recoverable-error-text" testID="messages-recoverable-error-text">{recoverableError}</Text>
            <TouchableOpacity
              onPress={() => { void fetchInbox(); }}
              style={{ backgroundColor: C.primary, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}
              data-testid="messages-recoverable-error-retry"
              testID="messages-recoverable-error-retry"
            >
              <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '800' }}>{t('common.retry')}</Text>
            </TouchableOpacity>
          </View>
        ) : null}
        {/* Header */}
        <View style={[ss.header, { backgroundColor: C.card, borderBottomColor: C.border }]} data-testid="messages-header" testID="messages-header">
          {view === 'inbox' ? (
            <>
              <Text style={{ fontSize: 18, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>{t("autofix.precision12.messages")}</Text>
              {totalUnread > 0 && (
                <View style={[ss.headerBadge, { backgroundColor: C.primary }]}>
                  <Text style={{ fontSize: 11, fontWeight: '800', color: C.primaryText }}>{totalUnread}</Text>
                </View>
              )}
              <View style={{ flex: 1 }} />
              <TouchableOpacity data-testid="new-msg-header-btn" testID="new-msg-header-btn" style={[ss.headerBtn, { backgroundColor: C.primary }]} onPress={() => setView('new')}>
                <Ionicons name="create" size={18} color={C.primaryText} />
              </TouchableOpacity>
            </>
          ) : (
            <>
              <TouchableOpacity data-testid="msg-back-btn" testID="msg-back-btn" style={[ss.backBtn, { backgroundColor: C.bgSoft }]}
                onPress={() => { setView('inbox'); setSelectedRecipient(null); setSearchResults([]); }}>
                <Ionicons name="arrow-back" size={20} color={C.text} />
              </TouchableOpacity>
              <Text style={{ fontSize: 17, fontWeight: '700', color: C.text, marginLeft: 12 }}>
                {view === 'new' ? 'New Message' : ''}
              </Text>
              <View style={{ flex: 1 }} />
            </>
          )}
        </View>

        {view === 'inbox' && renderInbox()}
        {view === 'thread' && renderThread()}
        {view === 'new' && renderNewConversation()}
    </View>
  );
}

export default function MessagesScreen() {
  const { t } = useTranslation();
  t('i18n.route.messages.probe');
  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1 }} edges={['top']}>
        <MessagesContent />
      </SafeAreaView>
    </AppShell>
  );
}

const ss = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, gap: 6 },
  headerBadge: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 10, marginLeft: 4 },
  headerBtn: { width: 38, height: 38, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  backBtn: { width: 38, height: 38, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },

  // Inbox
  convCard: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  avatar: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  badge: { minWidth: 20, height: 20, borderRadius: 10, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 5 },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 },

  // Thread
  threadHeader: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: 1 },
  headerAvatar: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', marginLeft: 8 },
  msgRow: { flexDirection: 'row', marginBottom: 8 },
  msgBubble: { maxWidth: '75%', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 18 },
  inputBar: { padding: 8, borderTopWidth: 1 },
  inputWrap: { flexDirection: 'row', alignItems: 'flex-end', borderRadius: 22, paddingLeft: 14, paddingRight: 4, paddingVertical: 4, borderWidth: 1 },
  messageInput: { flex: 1, fontSize: 14, maxHeight: 80, paddingVertical: 8 },
  sendBtn: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },

  // New Conversation
  formCard: { borderRadius: 14, padding: 18, borderWidth: 1 },
  formIcon: { width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  label: { fontSize: 13, fontWeight: '600', marginBottom: 8 },
  selectedRecip: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 10, borderWidth: 1 },
  recipAvatar: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  searchWrap: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12, borderRadius: 10, borderWidth: 1 },
  searchInput: { flex: 1, fontSize: 14, paddingVertical: 10 },
  searchResults: { borderRadius: 10, borderWidth: 1, marginTop: 4, overflow: 'hidden' },
  userResult: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderBottomWidth: 1 },
  fieldWrap: { borderRadius: 10, paddingHorizontal: 12, borderWidth: 1 },
  fieldInput: { fontSize: 14, paddingVertical: 10 },
  submitBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 12, paddingVertical: 14, marginTop: 16 },
});