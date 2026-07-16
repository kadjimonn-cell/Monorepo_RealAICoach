import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import FeatureToolbar from '../../src/components/FeatureToolbar';
import AIFeedbackBar from '../../src/components/AIFeedbackBar';
import MarkdownDisplay from '../../src/components/MarkdownDisplay';
import { useTranslation } from '../../src/hooks/useTranslation';
import { useAppStore } from '../../src/store/appStore';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const MODES = ['planner', 'executor', 'coach', 'critic'];

export default function AIChatbotScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.ai-chatbot.probe');
  const { width } = useWindowDimensions();
  const { colors } = useTheme();
  const { user } = useAuth();
  const { userId, initializeUser } = useAppStore();
  const accent = colors.primary;
  const isWide = width >= 1080;

  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [actions, setActions] = useState([]);
  const [memoryNotes, setMemoryNotes] = useState([]);
  const [stats, setStats] = useState({ sessions_count: 0, pending_actions: 0, memory_count: 0 });
  const [usage, setUsage] = useState(null);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [upgradeMessage, setUpgradeMessage] = useState('');

  const [composer, setComposer] = useState('');
  const [sessionTitle, setSessionTitle] = useState('');
  const [newActionTitle, setNewActionTitle] = useState('');
  const [newMemoryNote, setNewMemoryNote] = useState('');
  const [mode, setMode] = useState('planner');

  const [bootstrapLoading, setBootstrapLoading] = useState(true);
  const [messageLoading, setMessageLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [dailyBriefLoading, setDailyBriefLoading] = useState(false);
  const [dailyBrief, setDailyBrief] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [localGuestId] = useState(() => `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78));

  const fallbackUserId = useMemo(() => user?.user_id || userId || localGuestId || '', [localGuestId, user?.user_id, userId]);

  const s = {
    card: { backgroundColor: colors.card, borderRadius: 16, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: colors.border },
    title: { fontSize: 15, fontWeight: '800', color: colors.text, marginBottom: 10 },
    input: { backgroundColor: colors.bg, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, color: colors.text, borderWidth: 1, borderColor: colors.border },
    btnPrimary: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: 12, paddingVertical: 11, gap: 8, backgroundColor: accent },
    btnSecondary: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: 12, paddingVertical: 11, gap: 8, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border },
  };

  const loadSession = useCallback(async (sessionId) => {
    if (!fallbackUserId || !sessionId) return;
    try {
      const res = await api.get(`/personal-assistant/sessions/${sessionId}`, {
        params: { fallback_user_id: fallbackUserId },
      });
      setMessages(res?.data?.messages || []);
      setActiveSessionId(sessionId);
      setMode((res?.data?.session?.last_mode || 'planner').toLowerCase());
    } catch (error) {
      handleAppRecoverableError({ scope: 'features/ai-chatbot#loadSession', error, message: 'Failed to load assistant session',
        notifyMode: 'silent',
      });
      setErrorMessage('Could not load selected session.');
    }
  }, [fallbackUserId]);

  const loadBootstrap = useCallback(async () => {
    if (!fallbackUserId) return;
    setBootstrapLoading(true);
    try {
      const res = await api.get('/personal-assistant/bootstrap', { params: { fallback_user_id: fallbackUserId } });
      const incomingSessions = res?.data?.sessions || [];
      setSessions(incomingSessions);
      setActions(res?.data?.actions || []);
      setMemoryNotes(res?.data?.memory_notes || []);
      setStats(res?.data?.stats || { sessions_count: 0, pending_actions: 0, memory_count: 0 });
      setUsage(res?.data?.usage || null);
      if (incomingSessions.length > 0) {
        await loadSession(incomingSessions[0].session_id);
      } else {
        setMessages([]);
        setActiveSessionId('');
      }
      setErrorMessage('');
    } catch (error) {
      handleAppRecoverableError({ scope: 'features/ai-chatbot#bootstrap', error, message: 'Failed to initialize assistant workspace',
        notifyMode: 'silent',
      });
      setErrorMessage('Assistant workspace failed to load.');
    } finally {
      setBootstrapLoading(false);
    }
  }, [fallbackUserId, loadSession]);

  useEffect(() => {
    initializeUser();
  }, [initializeUser]);

  useEffect(() => {
    if (!fallbackUserId) return;
    const timer = setTimeout(() => {
      void loadBootstrap();
    }, 0);
    return () => clearTimeout(timer);
  }, [fallbackUserId, loadBootstrap]);

  const ensureFallbackIdentity = useCallback(async () => {
    let identity = fallbackUserId || localGuestId || '';
    if (identity) return identity;

    const initialized = await initializeUser();
    identity = initialized || useAppStore.getState().userId || '';
    if (identity) return identity;

    return `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78);
  }, [fallbackUserId, initializeUser, localGuestId]);

  const createSession = async () => {
    const effectiveFallback = await ensureFallbackIdentity();
    if (!effectiveFallback) {
      setErrorMessage('Session identity unavailable. Please refresh and retry.');
      return null;
    }
    try {
      const res = await api.post('/personal-assistant/sessions', {
        title: (sessionTitle || 'New Assistant Session').trim(),
        fallback_user_id: effectiveFallback,
      });
      const session = res?.data?.session;
      if (!session) return null;
      setSessions((prev) => [session, ...prev.filter((item) => item.session_id !== session.session_id)]);
      setSessionTitle('');
      await loadSession(session.session_id);
      return session;
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/ai-chatbot#createSession',
        error,
        message: 'Failed to create session',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void createSession(); },
      });
      setErrorMessage('Could not create new assistant session.');
      return null;
    }
  };

  const sendMessage = async () => {
    if (!composer.trim()) {
      Alert.alert('', 'Please enter your request');
      return;
    }
    
    // Check if at limit before sending
    if (usage && usage.limit_reached) {
      const tier = usage.tier || 'free';
      const nextTier = tier === 'free' ? 'Basic' : 'Premium';
      setUpgradeMessage(`You've reached your daily limit of ${usage.daily_limit} messages. Upgrade to ${nextTier} for ${tier === 'free' ? '200 messages/day' : 'unlimited messages'}!`);
      setShowUpgradeModal(true);
      return;
    }
    
    setMessageLoading(true);
    try {
      const effectiveFallback = await ensureFallbackIdentity();
      if (!effectiveFallback) {
        setErrorMessage('Session identity unavailable. Please refresh and retry.');
        setMessageLoading(false);
        return;
      }

      let sessionId = activeSessionId;
      if (!sessionId) {
        const created = await createSession();
        sessionId = created?.session_id || '';
      }
      if (!sessionId) {
        setMessageLoading(false);
        return;
      }

      const userMessage = { message_id: `local-${Date.now()}`, role: 'user', content: composer.trim(), created_at: new Date().toISOString() };
      setMessages((prev) => [...prev, userMessage]);
      const sendText = composer.trim();
      setComposer('');

      const res = await api.post(`/personal-assistant/sessions/${sessionId}/messages`, {
        content: sendText,
        mode,
        fallback_user_id: effectiveFallback,
        idempotency_key: `${sessionId}:${Date.now()}`,
      });
      const assistantMessage = res?.data?.assistant_message;
      if (assistantMessage) {
        setMessages((prev) => [...prev.filter((msg) => msg.message_id !== userMessage.message_id), res.data.user_message || userMessage, assistantMessage]);
      }
      await loadBootstrap();
      setErrorMessage('');
    } catch (error) {
      // Check for tier limit error
      if (error?.response?.status === 403 && error?.response?.data?.detail?.upgrade_prompt) {
        const detail = error.response.data.detail;
        setUpgradeMessage(detail.message || 'Daily message limit reached. Upgrade for more messages!');
        setShowUpgradeModal(true);
        await loadBootstrap(); // Refresh usage
      } else {
        handleAppRecoverableError({
          scope: 'features/ai-chatbot#sendMessage',
          error,
          message: 'Assistant response failed',
          notifyMode: 'dialog',
          userInitiated: true,
          onRetry: () => { void sendMessage(); },
        });
        setErrorMessage('Assistant response failed. Retry your message.');
      }
    } finally {
      setMessageLoading(false);
    }
  };

  const addAction = async () => {
    if (!newActionTitle.trim()) return;
    const effectiveFallback = await ensureFallbackIdentity();
    if (!effectiveFallback) {
      setErrorMessage('Session identity unavailable. Please refresh and retry.');
      return;
    }
    setActionLoading(true);
    try {
      const res = await api.post('/personal-assistant/actions', {
        title: newActionTitle.trim(),
        due_hint: '',
        fallback_user_id: effectiveFallback,
      });
      const action = res?.data?.action;
      if (action) {
        setActions((prev) => [action, ...prev]);
      }
      setNewActionTitle('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/ai-chatbot#addAction',
        error,
        message: 'Failed to add action',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void addAction(); },
      });
      setErrorMessage('Could not add action item.');
    } finally {
      setActionLoading(false);
    }
  };

  const toggleAction = async (action) => {
    const effectiveFallback = await ensureFallbackIdentity();
    if (!effectiveFallback) {
      setErrorMessage('Session identity unavailable. Please refresh and retry.');
      return;
    }
    try {
      const res = await api.patch(`/personal-assistant/actions/${action.action_id}`, {
        done: !action.done,
        fallback_user_id: effectiveFallback,
      });
      const updated = res?.data?.action;
      if (updated) {
        setActions((prev) => prev.map((item) => item.action_id === updated.action_id ? updated : item));
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/ai-chatbot#toggleAction',
        error,
        message: 'Failed to toggle action',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void toggleAction(action); },
      });
      setErrorMessage('Could not update action item.');
    }
  };

  const addMemory = async () => {
    if (!newMemoryNote.trim()) return;
    const effectiveFallback = await ensureFallbackIdentity();
    if (!effectiveFallback) {
      setErrorMessage('Session identity unavailable. Please refresh and retry.');
      return;
    }
    setMemoryLoading(true);
    try {
      const res = await api.post('/personal-assistant/memory', {
        note: newMemoryNote.trim(),
        fallback_user_id: effectiveFallback,
      });
      const note = res?.data?.note;
      if (note) setMemoryNotes((prev) => [note, ...prev]);
      setNewMemoryNote('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/ai-chatbot#addMemory',
        error,
        message: 'Failed to add memory note',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void addMemory(); },
      });
      setErrorMessage('Could not save memory note.');
    } finally {
      setMemoryLoading(false);
    }
  };

  const generateBrief = async () => {
    const effectiveFallback = await ensureFallbackIdentity();
    if (!effectiveFallback) {
      setErrorMessage('Session identity unavailable. Please refresh and retry.');
      return;
    }
    setDailyBriefLoading(true);
    try {
      const res = await api.post('/personal-assistant/daily-brief', null, {
        params: { fallback_user_id: effectiveFallback },
      });
      setDailyBrief(String(res?.data?.daily_brief?.content || '').trim());
    } catch (error) {
      handleAppRecoverableError({
        scope: 'features/ai-chatbot#dailyBrief',
        error,
        message: 'Failed to generate daily brief',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void generateBrief(); },
      });
      setErrorMessage('Unable to generate daily brief right now.');
    } finally {
      setDailyBriefLoading(false);
    }
  };

  const renderSessions = (
    <View style={[s.card, { flex: isWide ? 0.32 : 1 }]} data-testid="personal-ai-assistant-sessions-card" testID="personal-ai-assistant-sessions-card">
      <Text style={s.title} data-testid="personal-ai-assistant-sessions-title" testID="personal-ai-assistant-sessions-title">Assistant Sessions</Text>
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
        <TextInput value={sessionTitle} onChangeText={setSessionTitle} style={[s.input, { flex: 1 }]} placeholder="Session title" placeholderTextColor={colors.textMuted} data-testid="personal-ai-assistant-new-session-input" testID="personal-ai-assistant-new-session-input" />
        <TouchableOpacity style={[s.btnSecondary, { width: 46 }]} onPress={() => void createSession()} data-testid="personal-ai-assistant-create-session-button" testID="personal-ai-assistant-create-session-button" accessibilityRole="button">
          <Ionicons name="add" size={18} color={colors.text} />
        </TouchableOpacity>
      </View>
      <View style={{ gap: 8 }}>
        {sessions.length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="personal-ai-assistant-empty-sessions-message" testID="personal-ai-assistant-empty-sessions-message">No sessions yet.</Text> : sessions.map((session) => {
          const selected = activeSessionId === session.session_id;
          return (
            <TouchableOpacity key={session.session_id} onPress={() => void loadSession(session.session_id)} style={{ borderWidth: 1, borderColor: selected ? colors.primary : colors.border, backgroundColor: selected ? colors.primarySoft : colors.bg, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`personal-ai-assistant-session-item-${session.session_id}`} testID={`personal-ai-assistant-session-item-${session.session_id}`} accessibilityRole="button">
              <Text style={{ color: selected ? colors.primary : colors.text, fontWeight: '700', fontSize: 12 }}>{session.title}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>{session.message_count || 0} msgs • {session.last_mode || 'planner'}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );

  return (
    <FeatureLayout feature="ai-chatbot" title="Personal AI Assistant" subtitle="Enterprise assistant workspace with persistent sessions, memory, action tracking, and daily briefings" icon="chatbubbles" color={accent}>
      <ScrollView contentContainerStyle={{ paddingVertical: 14, paddingBottom: 40 }} data-testid="personal-ai-assistant-v2-root" testID="personal-ai-assistant-v2-root">
        <View style={[s.card, { marginBottom: 10 }]} data-testid="personal-ai-assistant-kpi-strip" testID="personal-ai-assistant-kpi-strip">
          <Text style={s.title} data-testid="personal-ai-assistant-kpi-title" testID="personal-ai-assistant-kpi-title">Assistant Momentum</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="personal-ai-assistant-kpi-sessions" testID="personal-ai-assistant-kpi-sessions"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Sessions: {stats.sessions_count}</Text></View>
            <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="personal-ai-assistant-kpi-actions" testID="personal-ai-assistant-kpi-actions"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Pending: {stats.pending_actions}</Text></View>
            <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="personal-ai-assistant-kpi-memory" testID="personal-ai-assistant-kpi-memory"><Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Memory: {stats.memory_count}</Text></View>
            {usage && (
              <View style={{ backgroundColor: usage.daily_limit === -1 ? colors.primarySoft : usage.limit_reached ? colors.errorSoft : usage.messages_used_today / usage.daily_limit > 0.8 ? colors.warningSoft : colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: usage.daily_limit === -1 ? colors.primary : usage.limit_reached ? colors.error : usage.messages_used_today / usage.daily_limit > 0.8 ? colors.warning : colors.border }} data-testid="personal-ai-assistant-usage-badge" testID="personal-ai-assistant-usage-badge">
                <Text style={{ color: usage.daily_limit === -1 ? colors.primary : usage.limit_reached ? colors.errorText : usage.messages_used_today / usage.daily_limit > 0.8 ? colors.warningText : colors.text, fontSize: 11, fontWeight: '800' }}>
                  {usage.daily_limit === -1 ? '∞ Unlimited (Premium)' : `${usage.messages_used_today}/${usage.daily_limit} messages today`}
                </Text>
              </View>
            )}
          </View>
        </View>

        {bootstrapLoading ? (
          <View style={[s.card, { alignItems: 'center', justifyContent: 'center', paddingVertical: 24 }]} data-testid="personal-ai-assistant-bootstrap-loading" testID="personal-ai-assistant-bootstrap-loading">
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={{ color: colors.textMuted, marginTop: 8 }}>Loading assistant workspace...</Text>
          </View>
        ) : null}

        {errorMessage ? (
          <View style={[s.card, { borderColor: colors.errorSoft, backgroundColor: colors.errorSoft }]} data-testid="personal-ai-assistant-error-banner" testID="personal-ai-assistant-error-banner">
            <Text style={{ color: colors.error, fontWeight: '700' }} data-testid="personal-ai-assistant-error-text" testID="personal-ai-assistant-error-text">{errorMessage}</Text>
            <TouchableOpacity style={[s.btnSecondary, { marginTop: 10, borderColor: colors.error, backgroundColor: colors.card }]} onPress={() => void sendMessage()} data-testid="personal-ai-assistant-error-retry-button" testID="personal-ai-assistant-error-retry-button" accessibilityRole="button">
              <Ionicons name="refresh" size={15} color={colors.error} />
              <Text style={{ color: colors.error, fontWeight: '700' }}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {isWide ? (
          <View style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-start' }}>
            {renderSessions}
            <View style={{ flex: 0.68 }}>
              <View style={s.card} data-testid="personal-ai-assistant-chat-card" testID="personal-ai-assistant-chat-card">
                <Text style={s.title} data-testid="personal-ai-assistant-chat-title" testID="personal-ai-assistant-chat-title">Conversation</Text>
                <ScrollView style={{ maxHeight: 320, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bg, padding: 10 }} data-testid="personal-ai-assistant-messages-scroll" testID="personal-ai-assistant-messages-scroll">
                  {messages.length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="personal-ai-assistant-empty-messages" testID="personal-ai-assistant-empty-messages">No messages yet. Ask your assistant to plan, execute, or coach.</Text> : messages.map((message) => (
                    <View key={message.message_id} style={{ marginBottom: 10 }} data-testid={`personal-ai-assistant-message-${message.message_id}`} testID={`personal-ai-assistant-message-${message.message_id}`}>
                      <Text style={{ color: message.role === 'user' ? colors.primary : colors.textMuted, fontSize: 11, fontWeight: '700', marginBottom: 4 }}>{message.role === 'user' ? 'You' : 'Assistant'}</Text>
                      {message.role === 'assistant' ? <MarkdownDisplay content={message.content || ''} /> : <Text style={{ color: colors.text, fontSize: 13 }}>{message.content}</Text>}
                    </View>
                  ))}
                </ScrollView>

                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 10 }} data-testid="personal-ai-assistant-mode-scroll" testID="personal-ai-assistant-mode-scroll">
                  {MODES.map((modeItem) => {
                    const selected = modeItem === mode;
                    return (
                      <TouchableOpacity key={modeItem} onPress={() => setMode(modeItem)} style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 7, borderWidth: 1, borderColor: selected ? colors.primary : colors.border, backgroundColor: selected ? colors.primarySoft : colors.bg }} data-testid={`personal-ai-assistant-mode-${modeItem}`} testID={`personal-ai-assistant-mode-${modeItem}`} accessibilityRole="button">
                        <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 12, fontWeight: '700' }}>{modeItem}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </ScrollView>

                <TextInput style={[s.input, { minHeight: 95, textAlignVertical: 'top', marginTop: 10 }]} multiline value={composer} onChangeText={setComposer} placeholder="Ask for planning, execution, coaching, or critique..." placeholderTextColor={colors.textMuted} data-testid="personal-ai-assistant-composer-input" testID="personal-ai-assistant-composer-input" />
                <TouchableOpacity style={[s.btnPrimary, { marginTop: 10 }]} onPress={() => void sendMessage()} disabled={messageLoading} data-testid="personal-ai-assistant-send-button" testID="personal-ai-assistant-send-button" accessibilityRole="button">
                  {messageLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <><Ionicons name="send" size={16} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '800' }}>Send to Assistant</Text></>}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        ) : (
          <>
            {renderSessions}
            <View style={s.card} data-testid="personal-ai-assistant-chat-card" testID="personal-ai-assistant-chat-card">
              <Text style={s.title} data-testid="personal-ai-assistant-chat-title" testID="personal-ai-assistant-chat-title">Conversation</Text>
              <ScrollView
                style={{ maxHeight: 280, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bg, padding: 10 }}
                data-testid="personal-ai-assistant-messages-scroll"
                testID="personal-ai-assistant-messages-scroll"
              >
                {messages.length === 0 ? (
                  <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="personal-ai-assistant-empty-messages" testID="personal-ai-assistant-empty-messages">
                    No messages yet. Ask your assistant to plan, execute, or coach.
                  </Text>
                ) : messages.map((message) => (
                  <View key={message.message_id} style={{ marginBottom: 10 }} data-testid={`personal-ai-assistant-message-${message.message_id}`} testID={`personal-ai-assistant-message-${message.message_id}`}>
                    <Text style={{ color: message.role === 'user' ? colors.primary : colors.textMuted, fontSize: 11, fontWeight: '700', marginBottom: 4 }}>
                      {message.role === 'user' ? 'You' : 'Assistant'}
                    </Text>
                    {message.role === 'assistant' ? <MarkdownDisplay content={message.content || ''} /> : <Text style={{ color: colors.text, fontSize: 13 }}>{message.content}</Text>}
                  </View>
                ))}
              </ScrollView>

              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={{ gap: 8, marginTop: 10 }}
                data-testid="personal-ai-assistant-mode-scroll"
                testID="personal-ai-assistant-mode-scroll"
              >
                {MODES.map((modeItem) => {
                  const selected = modeItem === mode;
                  return (
                    <TouchableOpacity
                      key={modeItem}
                      onPress={() => setMode(modeItem)}
                      style={{
                        borderRadius: 999,
                        paddingHorizontal: 10,
                        paddingVertical: 7,
                        borderWidth: 1,
                        borderColor: selected ? colors.primary : colors.border,
                        backgroundColor: selected ? colors.primarySoft : colors.bg,
                      }}
                      data-testid={`personal-ai-assistant-mode-${modeItem}`}
                      testID={`personal-ai-assistant-mode-${modeItem}`}
                      accessibilityRole="button"
                    >
                      <Text style={{ color: selected ? colors.primary : colors.text, fontSize: 12, fontWeight: '700' }}>{modeItem}</Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>

              <TextInput style={[s.input, { minHeight: 95, textAlignVertical: 'top', marginTop: 10 }]} multiline value={composer} onChangeText={setComposer} placeholder="Ask your assistant..." placeholderTextColor={colors.textMuted} data-testid="personal-ai-assistant-composer-input" testID="personal-ai-assistant-composer-input" />
              <TouchableOpacity style={[s.btnPrimary, { marginTop: 10 }]} onPress={() => void sendMessage()} disabled={messageLoading} data-testid="personal-ai-assistant-send-button" testID="personal-ai-assistant-send-button" accessibilityRole="button">
                {messageLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <><Ionicons name="send" size={16} color={colors.primaryText} /><Text style={{ color: colors.primaryText, fontWeight: '800' }}>Send</Text></>}
              </TouchableOpacity>
            </View>
          </>
        )}

        <View style={s.card} data-testid="personal-ai-assistant-actions-card" testID="personal-ai-assistant-actions-card">
          <Text style={s.title} data-testid="personal-ai-assistant-actions-title" testID="personal-ai-assistant-actions-title">Action Tracker</Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TextInput value={newActionTitle} onChangeText={setNewActionTitle} style={[s.input, { flex: 1 }]} placeholder="New action item" placeholderTextColor={colors.textMuted} data-testid="personal-ai-assistant-new-action-input" testID="personal-ai-assistant-new-action-input" />
            <TouchableOpacity style={[s.btnSecondary, { width: 72 }]} onPress={() => void addAction()} disabled={actionLoading} data-testid="personal-ai-assistant-create-action-button" testID="personal-ai-assistant-create-action-button" accessibilityRole="button">
              {actionLoading ? <ActivityIndicator size="small" color={colors.text} /> : <Text style={{ color: colors.text, fontWeight: '700' }}>Add</Text>}
            </TouchableOpacity>
          </View>
          <View style={{ gap: 8, marginTop: 10 }}>
            {actions.length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="personal-ai-assistant-empty-actions-message" testID="personal-ai-assistant-empty-actions-message">No action items yet.</Text> : actions.map((action) => (
              <TouchableOpacity key={action.action_id} onPress={() => void toggleAction(action)} style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: action.done ? colors.successSoft : colors.bg, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`personal-ai-assistant-action-item-${action.action_id}`} testID={`personal-ai-assistant-action-item-${action.action_id}`} accessibilityRole="button">
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 12 }}>{action.done ? '✅' : '⬜'} {action.title}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={s.card} data-testid="personal-ai-assistant-memory-card" testID="personal-ai-assistant-memory-card">
          <Text style={s.title} data-testid="personal-ai-assistant-memory-title" testID="personal-ai-assistant-memory-title">Pinned Memory</Text>
          <TextInput value={newMemoryNote} onChangeText={setNewMemoryNote} style={[s.input, { minHeight: 72, textAlignVertical: 'top' }]} multiline placeholder="Add memory note (preferences, constraints, goals)" placeholderTextColor={colors.textMuted} data-testid="personal-ai-assistant-new-memory-input" testID="personal-ai-assistant-new-memory-input" />
          <TouchableOpacity style={[s.btnSecondary, { marginTop: 10 }]} onPress={() => void addMemory()} disabled={memoryLoading} data-testid="personal-ai-assistant-add-memory-button" testID="personal-ai-assistant-add-memory-button" accessibilityRole="button">
            {memoryLoading ? <ActivityIndicator size="small" color={colors.text} /> : <><Ionicons name="bookmark-outline" size={16} color={colors.text} /><Text style={{ color: colors.text, fontWeight: '700' }}>Pin Memory</Text></>}
          </TouchableOpacity>
          <View style={{ gap: 8, marginTop: 10 }}>
            {memoryNotes.length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="personal-ai-assistant-empty-memory-message" testID="personal-ai-assistant-empty-memory-message">No memory notes yet.</Text> : memoryNotes.map((note) => (
              <View key={note.note_id} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: colors.bg }} data-testid={`personal-ai-assistant-memory-item-${note.note_id}`} testID={`personal-ai-assistant-memory-item-${note.note_id}`}>
                <Text style={{ color: colors.text, fontSize: 12 }}>{note.note}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={s.card} data-testid="personal-ai-assistant-daily-brief-card" testID="personal-ai-assistant-daily-brief-card">
          <Text style={s.title} data-testid="personal-ai-assistant-daily-brief-title" testID="personal-ai-assistant-daily-brief-title">Daily Executive Brief</Text>
          <TouchableOpacity style={s.btnSecondary} onPress={() => void generateBrief()} disabled={dailyBriefLoading} data-testid="personal-ai-assistant-generate-brief-button" testID="personal-ai-assistant-generate-brief-button" accessibilityRole="button">
            {dailyBriefLoading ? <ActivityIndicator size="small" color={colors.text} /> : <><Ionicons name="newspaper-outline" size={16} color={colors.text} /><Text style={{ color: colors.text, fontWeight: '700' }}>Generate Daily Brief</Text></>}
          </TouchableOpacity>
          {dailyBrief ? (
            <View style={{ marginTop: 10 }} data-testid="personal-ai-assistant-daily-brief-content" testID="personal-ai-assistant-daily-brief-content">
              <MarkdownDisplay content={dailyBrief} />
              <FeatureToolbar content={dailyBrief} featureKey="ai-chatbot" title="Daily Brief" onClear={() => setDailyBrief('')} />
              <AIFeedbackBar feature="ai-chatbot" response={dailyBrief} />
            </View>
          ) : null}
        </View>
      </ScrollView>
      
      {/* Upgrade Modal */}
      {showUpgradeModal && (
        <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }} data-testid="personal-ai-assistant-upgrade-modal" testID="personal-ai-assistant-upgrade-modal">
          <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: 20, marginHorizontal: 20, maxWidth: 480, width: '100%', borderWidth: 2, borderColor: colors.primary }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text }}>🚀 Upgrade Required</Text>
              <TouchableOpacity onPress={() => setShowUpgradeModal(false)} accessibilityRole="button">
                <Ionicons name="close" size={24} color={colors.textMuted} />
              </TouchableOpacity>
            </View>
            <Text style={{ fontSize: 14, color: colors.text, lineHeight: 22, marginBottom: 16 }}>{upgradeMessage || 'Daily message limit reached. Upgrade for more!'}</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity onPress={() => setShowUpgradeModal(false)} style={{ flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.bgSoft, alignItems: 'center', borderWidth: 1, borderColor: colors.border }} data-testid="personal-ai-assistant-upgrade-modal-cancel" testID="personal-ai-assistant-upgrade-modal-cancel" accessibilityRole="button">
                <Text style={{ color: colors.text, fontWeight: '700' }}>Maybe Later</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => {
                setShowUpgradeModal(false);
                // Navigate to subscriptions (you can implement routing here)
                Alert.alert('Upgrade', 'Navigate to subscriptions page to upgrade your plan.');
              }} style={{ flex: 1, paddingVertical: 12, borderRadius: 10, backgroundColor: accent, alignItems: 'center' }} data-testid="personal-ai-assistant-upgrade-modal-confirm" testID="personal-ai-assistant-upgrade-modal-confirm" accessibilityRole="button">
                <Text style={{ color: colors.primaryText, fontWeight: '800' }}>Upgrade Now</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </FeatureLayout>
  );
}