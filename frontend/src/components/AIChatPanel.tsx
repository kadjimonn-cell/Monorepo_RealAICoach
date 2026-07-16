import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, ScrollView, TextInput, TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator, Dimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';
import MarkdownDisplay from './MarkdownDisplay';
import AIResponseFeedback from './AIResponseFeedback';
import { handleAppRecoverableError } from '../utils/appRecoverableError';
import { useAppStore } from '../store/appStore';

interface AIChatPanelProps {
  feature: string;
  themeColors?: any;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  ts: number;
  modelLabel?: string;
}

interface ChatModelOption {
  key: string;
  label: string;
  provider: string;
  description?: string;
}

const DEFAULT_CHAT_MODELS: ChatModelOption[] = [
  { key: 'gpt-4o', label: 'GPT-4o', provider: 'openai' },
  { key: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', provider: 'anthropic' },
  { key: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', provider: 'anthropic' },
];

interface ChatSession {
  session_id: string;
  title: string;
  summary?: string;
  tags?: string[];
  last_message: string;
  message_count: number;
  last_at: string;
}

const QUICK_PROMPTS: Record<string, string[]> = {
  default: ['Help me prepare for an interview', 'Review my resume strategy', 'Career growth advice', 'Skill gap analysis'],
};

const useResponsive = () => {
  const [width, setWidth] = useState(Dimensions.get('window').width);
  useEffect(() => {
    const sub = Dimensions.addEventListener('change', ({ window }) => setWidth(window.width));
    return () => sub?.remove();
  }, []);
  return { isMobile: width < 768, isTablet: width >= 768 && width < 1024, isDesktop: width >= 1024, width };
};

export default function AIChatPanel({ feature, themeColors }: AIChatPanelProps) {
  const { user } = useAuth();
  const { colors } = useTheme();
  const { userId, initializeUser } = useAppStore();
  const activeColors = themeColors || colors;
  const { isMobile, isDesktop } = useResponsive();

  const fallbackUserId = useMemo(() => {
    const authId = String((user as any)?.user_id || '').trim();
    if (authId) return authId;
    const storeId = String(userId || '').trim();
    if (storeId) return storeId;
    if (typeof window !== 'undefined') {
      try {
        const existing = window.localStorage.getItem('nova_guest_fallback_user_id');
        if (existing && existing.trim()) return existing.trim();
        const generated = `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78);
        window.localStorage.setItem('nova_guest_fallback_user_id', generated);
        return generated;
      } catch {
        // ignore storage failures
      }
    }
    return `user_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`.slice(0, 78);
  }, [user, userId]);

  const resolveApiErrorMessage = useCallback((error: any, fallback: string) => {
    const payload = error?.response?.data;
    const detail = payload?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (detail && typeof detail === 'object') {
      const nested = detail.message || detail.error || detail.detail;
      if (typeof nested === 'string' && nested.trim()) return nested;
    }
    const direct = payload?.message || payload?.error;
    if (typeof direct === 'string' && direct.trim()) return direct;
    return fallback;
  }, []);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [expandedSummary, setExpandedSummary] = useState<string | null>(null);
  const [chatModels, setChatModels] = useState<ChatModelOption[]>(DEFAULT_CHAT_MODELS);
  const [selectedModel, setSelectedModel] = useState<string>('gpt-4o');
  const scrollViewRef = useRef<ScrollView>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api.get('/personal-assistant/models', { silentLoading: true });
        const list = (res?.data?.models || []).filter((m: any) => m?.key && m?.label);
        if (active && list.length > 0) {
          setChatModels(list);
          const def = String(res?.data?.default || '').trim();
          if (def && list.some((m: any) => m.key === def)) setSelectedModel(def);
        }
      } catch {
        // keep static fallback list
      }
    })();
    return () => { active = false; };
  }, []);

  const lastAssistantMessage = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') return messages[i].content;
    }
    return '';
  }, [messages]);

  const hasSummarizableSessions = useMemo(() => {
    return sessions.length >= 5 && sessions.slice(3).some(s => !s.summary);
  }, [sessions]);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const res = await api.get('/personal-assistant/sessions', {
        params: { fallback_user_id: fallbackUserId },
      });
      const list: ChatSession[] = res.data.sessions || [];
      setSessions(list);
      if (!activeSessionId && list.length > 0) {
        setActiveSessionId(list[0].session_id);
      }
    } catch (error: any) {
      if (error?.response?.status === 401) {
        setSessions([]);
        setActiveSessionId(null);
      } else {
        handleAppRecoverableError({
          scope: 'src/components/AIChatPanel.tsx#catch2',
          error,
          message: resolveApiErrorMessage(error, 'Unable to load chat sessions right now. Please retry.'),
        
        notifyMode: 'silent',
      });
      }
    } finally {
      setSessionsLoading(false);
    }
  }, [activeSessionId, fallbackUserId, resolveApiErrorMessage]);

  const loadHistory = useCallback(async (sessionId: string) => {
    setHistoryLoading(true);
    try {
      const res = await api.get(`/personal-assistant/sessions/${sessionId}`, {
        params: { fallback_user_id: fallbackUserId },
      });
      const msgs: ChatMessage[] = (res.data.messages || []).map((m: any) => ({
        role: m.role === 'assistant' ? 'assistant' : 'user',
        content: String(m.content || ''),
        ts: new Date(m.created_at || Date.now()).getTime(),
        modelLabel: m.model_label ? String(m.model_label) : undefined,
      }));
      setMessages(msgs);
    } catch {
      setMessages([]);
    } finally {
      setHistoryLoading(false);
    }
  }, [fallbackUserId]);

  // Load sessions when user is available
  useEffect(() => {
    void initializeUser();
  }, [initializeUser]);

  useEffect(() => {
    if (fallbackUserId) loadSessions();
  }, [fallbackUserId, loadSessions]);

  // Load history when session changes
  useEffect(() => {
    if (activeSessionId) {
      loadHistory(activeSessionId);
    } else {
      setMessages([]);
    }
  }, [activeSessionId, loadHistory]);

  const createNewSession = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setShowSidebar(false);
  }, []);

  const switchSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
    setShowSidebar(false);
    setExpandedSummary(null);
  }, []);

  const handleSummarize = useCallback(async () => {
    setSummarizing(true);
    try {
      await api.post('/personal-assistant/daily-brief', null, {
        params: { fallback_user_id: fallbackUserId },
      });
      await loadSessions();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIChatPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setSummarizing(false);
    }
  }, [fallbackUserId, loadSessions]);

  const handleSend = useCallback(async (text?: string) => {
    const userMsg = (text || input).trim();
    if (!userMsg || loading) return;
    setInput('');

    let sessionId = activeSessionId || '';

    setMessages(prev => [...prev, { role: 'user', content: userMsg, ts: Date.now() }]);
    setLoading(true);

    try {
      const hasExistingSession = Boolean(sessionId) && sessions.some((s) => s.session_id === sessionId);
      if (!hasExistingSession) {
        const created = await api.post('/personal-assistant/sessions', {
          title: 'New conversation',
          fallback_user_id: fallbackUserId,
        });
        sessionId = String(created?.data?.session?.session_id || '').trim();
        if (!sessionId) throw new Error('assistant_session_create_failed');
        setActiveSessionId(sessionId);
      }

      const res = await api.post(`/personal-assistant/sessions/${sessionId}/messages`, {
        content: userMsg,
        mode: 'planner',
        model: selectedModel,
        fallback_user_id: fallbackUserId,
        idempotency_key: `${sessionId}:${Date.now()}`,
      });
      const assistantMessage = res?.data?.assistant_message?.content || 'No response';
      const assistantModelLabel = res?.data?.assistant_message?.model_label ? String(res.data.assistant_message.model_label) : undefined;
      setMessages(prev => [...prev, { role: 'assistant', content: assistantMessage, ts: Date.now(), modelLabel: assistantModelLabel }]);
      loadSessions();
    } catch (err: any) {
      const detail = resolveApiErrorMessage(err, 'Something went wrong. Please try again.');
      setMessages(prev => [...prev, { role: 'assistant', content: detail, ts: Date.now() }]);
    } finally {
      setLoading(false);
    }
  }, [input, activeSessionId, loading, loadSessions, resolveApiErrorMessage, fallbackUserId, sessions, selectedModel]);

  // Auto-scroll
  useEffect(() => {
    setTimeout(() => scrollViewRef.current?.scrollToEnd({ animated: true }), 120);
  }, [messages, loading]);

  const C = {
    bg: activeColors.bg,
    card: activeColors.card,
    text: activeColors.text,
    muted: activeColors.textMuted,
    border: activeColors.border,
    primary: activeColors.primary,
    userBubble: activeColors.primary,
    aiBubble: activeColors.infoSoft || activeColors.cardMuted || activeColors.bgSoft,
    aiAccent: activeColors.info || activeColors.primary,
    sidebarBg: activeColors.card,
    tagBg: activeColors.primarySoft,
    tagText: activeColors.primary,
    summaryBg: activeColors.warningSoft || activeColors.cardMuted,
    summaryBorder: activeColors.warning || activeColors.borderStrong,
  };

  const prompts = QUICK_PROMPTS[feature] || QUICK_PROMPTS.default;

  const formatSessionLabel = (s: ChatSession) => {
    const text = s.title || s.last_message || 'New conversation';
    return text.length > 40 ? text.slice(0, 40) + '...' : text;
  };

  const formatTime = (isoStr: string) => {
    const d = new Date(isoStr);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  };

  // Sidebar component
  const renderSidebar = () => (
    <View
      style={{
        width: isDesktop ? 300 : '100%',
        height: isDesktop ? '100%' : undefined,
        backgroundColor: C.sidebarBg,
        borderRightWidth: isDesktop ? 1 : 0,
        borderRightColor: C.border,
        ...(isDesktop ? {} : { position: 'absolute' as const, top: 0, left: 0, bottom: 0, zIndex: 20, width: 310 }),
      }}
      data-testid="chat-sidebar" testID="chat-sidebar"
    >
      {/* Sidebar Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: C.border }}>
        <Text style={{ fontSize: 15, fontWeight: '700', color: C.text, letterSpacing: -0.3 }}>Conversations</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {hasSummarizableSessions && (
            <TouchableOpacity
              onPress={handleSummarize}
              disabled={summarizing}
              style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.summaryBorder, '30'), alignItems: 'center', justifyContent: 'center', opacity: summarizing ? 0.5 : 1 }}
              data-testid="summarize-sessions-btn" testID="summarize-sessions-btn"
            >
              {summarizing ? (
                <ActivityIndicator size="small" color={C.tagText} />
              ) : (
                <Ionicons name="sparkles" size={16} color={C.tagText} />
              )}
            </TouchableOpacity>
          )}
          <TouchableOpacity
            onPress={createNewSession}
            style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center' }}
            data-testid="new-chat-btn" testID="new-chat-btn"
          >
            <Ionicons name="add" size={18} color={C.primary} />
          </TouchableOpacity>
          {!isDesktop && (
            <TouchableOpacity
              onPress={() => setShowSidebar(false)}
              style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: C.border, alignItems: 'center', justifyContent: 'center' }}
              data-testid="close-sidebar-btn" testID="close-sidebar-btn"
            >
              <Ionicons name="close" size={18} color={C.muted} />
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Session List */}
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 8 }}>
        {sessionsLoading ? (
          <ActivityIndicator color={C.primary} style={{ marginTop: 20 }} />
        ) : sessions.length === 0 ? (
          <View style={{ alignItems: 'center', paddingTop: 40 }}>
            <Ionicons name="chatbubbles-outline" size={32} color={C.muted} />
            <Text style={{ fontSize: 13, color: C.muted, marginTop: 8, textAlign: 'center' }}>No conversations yet</Text>
          </View>
        ) : (
          sessions.map(s => {
            const isActive = s.session_id === activeSessionId;
            const hasSummary = !!s.summary;
            const isExpanded = expandedSummary === s.session_id;
            return (
              <View key={s.session_id} style={{ marginBottom: 4 }}>
                <TouchableOpacity accessibilityLabel="Switch session in aichat panel"
                  onPress={() => switchSession(s.session_id)}
                  style={{
                    padding: 12, borderRadius: 10,
                    backgroundColor: isActive ? (globalThis as any).__alphaColor(C.primary, '12') : 'transparent',
                    borderWidth: isActive ? 1 : 0,
                    borderColor: isActive ? (globalThis as any).__alphaColor(C.primary, '30') : 'transparent',
                  }}
                  data-testid={`session-item-${s.session_id}`} testID={`session-item-${s.session_id}`}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    {hasSummary && (
                      <TouchableOpacity
                        onPress={() => setExpandedSummary(isExpanded ? null : s.session_id)}
                        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                        data-testid={`summary-toggle-${s.session_id}`} testID={`summary-toggle-${s.session_id}`}
                      >
                        <Ionicons
                          name={isExpanded ? 'chevron-down' : 'document-text-outline'}
                          size={14}
                          color={C.tagText}
                        />
                      </TouchableOpacity>
                    )}
                    <Text style={{ fontSize: 13, fontWeight: isActive ? '700' : '500', color: isActive ? C.primary : C.text, flex: 1 }} numberOfLines={1}>
                      {formatSessionLabel(s)}
                    </Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 }}>
                    <Text style={{ fontSize: 11, color: C.muted }}>{s.message_count} msg{s.message_count !== 1 ? 's' : ''}</Text>
                    <Text style={{ fontSize: 10, color: C.muted }}>{formatTime(s.last_at)}</Text>
                  </View>

                  {/* Tags */}
                  {hasSummary && s.tags && s.tags.length > 0 && (
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                      {s.tags.map((tag, i) => (
                        <View key={i} style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: C.tagBg }}>
                          <Text style={{ fontSize: 9, fontWeight: '600', color: C.tagText }}>{tag}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                </TouchableOpacity>

                {/* Expanded Summary Card */}
                {isExpanded && hasSummary && (
                  <View
                    style={{
                      marginHorizontal: 8, marginTop: 2, marginBottom: 6,
                      padding: 10, borderRadius: 8,
                      backgroundColor: C.summaryBg,
                      borderWidth: 1, borderColor: C.summaryBorder,
                    }}
                    data-testid={`summary-card-${s.session_id}`} testID={`summary-card-${s.session_id}`}
                  >
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                      <Ionicons name="sparkles" size={10} color={C.tagText} />
                      <Text style={{ fontSize: 9, fontWeight: '700', color: C.tagText, textTransform: 'uppercase', letterSpacing: 0.5 }}>AI Summary</Text>
                    </View>
                    <Text style={{ fontSize: 11, lineHeight: 16, color: C.text }}>{s.summary}</Text>
                  </View>
                )}
              </View>
            );
          })
        )}
      </ScrollView>
    </View>
  );

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1, backgroundColor: C.bg }}>
      <View style={{ flex: 1, flexDirection: isDesktop ? 'row' : 'column' }}>
        {/* Desktop sidebar always visible */}
        {isDesktop && renderSidebar()}

        {/* Mobile sidebar overlay */}
        {!isDesktop && showSidebar && (
          <>
            <TouchableOpacity accessibilityLabel="Set show sidebar in aichat panel"
              style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: activeColors.overlay, zIndex: 15 }}
              onPress={() => setShowSidebar(false)}
              activeOpacity={1}
            />
            {renderSidebar()}
          </>
        )}

        {/* Main Chat Area */}
        <View style={{ flex: 1 }}>
          {/* Top bar */}
          <View style={{
            flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
            paddingHorizontal: 16, paddingVertical: 10,
            borderBottomWidth: 1, borderBottomColor: C.border,
            backgroundColor: C.card,
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              {!isDesktop && (
                <TouchableOpacity
                  onPress={() => setShowSidebar(true)}
                  style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), alignItems: 'center', justifyContent: 'center' }}
                  data-testid="open-sidebar-btn" testID="open-sidebar-btn"
                >
                  <Ionicons name="menu" size={20} color={C.primary} />
                </TouchableOpacity>
              )}
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="sparkles" size={18} color={C.primary} />
              </View>
              <View>
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, letterSpacing: -0.3 }}>Nova AI</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: activeColors.success }} />
                  <Text style={{ fontSize: 10, color: activeColors.successText, fontWeight: '600' }}>Online</Text>
                </View>
              </View>
            </View>
            <TouchableOpacity accessibilityLabel="New chat header button"
              onPress={createNewSession}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8,
                backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '25'),
              }}
              data-testid="new-chat-header-btn" testID="new-chat-header-btn"
            >
              <Ionicons name="add-circle-outline" size={16} color={C.primary} />
              <Text style={{ fontSize: 12, fontWeight: '600', color: C.primary }}>New Chat</Text>
            </TouchableOpacity>
          </View>

          {/* Model Picker */}
          <View
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: isMobile ? 12 : 16, paddingVertical: 8,
              borderBottomWidth: 1, borderBottomColor: C.border, backgroundColor: C.card,
            }}
            data-testid="ai-chat-model-picker" testID="ai-chat-model-picker"
          >
            <Ionicons name="hardware-chip-outline" size={13} color={C.muted} />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              {chatModels.map((m) => {
                const active = selectedModel === m.key;
                return (
                  <TouchableOpacity
                    key={m.key}
                    onPress={() => setSelectedModel(m.key)}
                    accessibilityLabel={`Use ${m.label} model`}
                    style={{
                      paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1,
                      borderColor: active ? C.primary : C.border,
                      backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '12') : 'transparent',
                    }}
                    data-testid={`ai-chat-model-option-${m.key}`} testID={`ai-chat-model-option-${m.key}`}
                  >
                    <Text style={{ fontSize: 11, fontWeight: active ? '800' : '600', color: active ? C.primary : C.muted }}>{m.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>

          {/* Messages Area */}
          <ScrollView
            ref={scrollViewRef}
            contentContainerStyle={{ padding: isMobile ? 12 : 20, gap: 12, paddingBottom: 8, flexGrow: 1 }}
            keyboardShouldPersistTaps="handled"
            data-testid={`ai-chat-scroll-${feature}`} testID={`ai-chat-scroll-${feature}`}
          >
            {historyLoading ? (
              <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 60 }}>
                <ActivityIndicator size="large" color={C.primary} />
                <Text style={{ fontSize: 13, color: C.muted, marginTop: 10 }}>Loading conversation...</Text>
              </View>
            ) : messages.length === 0 ? (
              /* Empty State */
              <View style={{ alignItems: 'center', paddingTop: isMobile ? 32 : 60, paddingBottom: 12 }}>
                <View style={{
                  width: 64, height: 64, borderRadius: 20, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'),
                  alignItems: 'center', justifyContent: 'center', marginBottom: 16,
                }}>
                  <Ionicons name="chatbubbles-outline" size={28} color={C.primary} />
                </View>
                <Text style={{ fontSize: isMobile ? 16 : 18, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>How can I help you?</Text>
                <Text style={{ fontSize: 13, color: C.muted, marginTop: 6, textAlign: 'center', maxWidth: 300 }}>
                  Ask me anything about career growth, interviews, or skills
                </Text>
                <View style={{
                  flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8,
                  marginTop: 20, maxWidth: isDesktop ? 500 : '100%',
                  paddingHorizontal: isMobile ? 0 : 20,
                }}>
                  {prompts.map((p, i) => (
                    <TouchableOpacity accessibilityLabel="Send in aichat panel"
                      key={i}
                      onPress={() => handleSend(p)}
                      style={{
                        paddingHorizontal: 14, paddingVertical: 9, borderRadius: 20,
                        backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '25'),
                      }}
                      data-testid={`quick-prompt-${i}`} testID={`quick-prompt-${i}`}
                    >
                      <Text style={{ fontSize: 12, fontWeight: '600', color: C.primary }}>{p}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            ) : (
              /* Messages */
              messages.map((msg, i) => {
                const isUser = msg.role === 'user';
                const time = new Date(msg.ts);
                const timeStr = time.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
                const maxBubble = isMobile ? '92%' : isDesktop ? '70%' : '80%';
                return (
                  <View
                    key={`${msg.ts}-${i}`}
                    style={{ alignSelf: isUser ? 'flex-end' : 'flex-start', maxWidth: maxBubble as any, gap: 4 }}
                    data-testid={`chat-message-${i}-${msg.role}`} testID={`chat-message-${i}-${msg.role}`}
                  >
                    {!isUser && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <View style={{ width: 20, height: 20, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.primary, '20'), alignItems: 'center', justifyContent: 'center' }}>
                          <Ionicons name="sparkles" size={10} color={C.primary} />
                        </View>
                        <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }} data-testid={`chat-message-model-${i}`} testID={`chat-message-model-${i}`}>{msg.modelLabel ? `Nova · ${msg.modelLabel}` : 'Nova'}</Text>
                      </View>
                    )}
                    <View
                      style={{
                        backgroundColor: isUser ? C.userBubble : C.aiBubble,
                        padding: isMobile ? 12 : 14,
                        borderRadius: 16,
                        borderBottomRightRadius: isUser ? 4 : 16,
                        borderBottomLeftRadius: !isUser ? 4 : 16,
                        ...(isUser ? {} : { borderWidth: 1, borderColor: C.aiAccent }),
                      }}
                    >
                      {isUser ? (
                        <Text style={{ color: activeColors.primaryText, fontSize: isMobile ? 14 : 15, lineHeight: isMobile ? 20 : 22 }}>{msg.content}</Text>
                      ) : (
                        <MarkdownDisplay content={msg.content} />
                      )}
                    </View>
                    <Text style={{ fontSize: 9, color: C.muted, alignSelf: isUser ? 'flex-end' : 'flex-start', marginTop: 1, paddingHorizontal: 4 }}>{timeStr}</Text>
                  </View>
                );
              })
            )}

            {/* Typing Indicator */}
            {loading && (
              <View style={{ alignSelf: 'flex-start', maxWidth: '70%' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                  <View style={{ width: 20, height: 20, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.primary, '20'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="sparkles" size={10} color={C.primary} />
                  </View>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Nova</Text>
                </View>
                <View style={{
                  flexDirection: 'row', gap: 5, padding: 14, backgroundColor: C.aiBubble,
                  borderRadius: 16, borderBottomLeftRadius: 4, borderWidth: 1, borderColor: C.aiAccent,
                  alignItems: 'center',
                }}>
                  <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: C.primary, opacity: 0.7 }} />
                  <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: C.primary, opacity: 0.5 }} />
                  <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: C.primary, opacity: 0.3 }} />
                  <Text style={{ fontSize: 12, color: C.muted, marginLeft: 6 }}>Thinking...</Text>
                </View>
              </View>
            )}

            {/* Feedback */}
            {lastAssistantMessage ? (
              <AIResponseFeedback featureKey={feature} responseText={lastAssistantMessage} testId={`ai-chat-feedback-${feature}`} />
            ) : null}
          </ScrollView>

          {/* Input Area */}
          <View style={{
            paddingHorizontal: isMobile ? 12 : 20, paddingVertical: isMobile ? 10 : 12,
            borderTopWidth: 1, borderTopColor: C.border,
            backgroundColor: C.card,
            ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
          }}>
            <View style={{
              flexDirection: 'row', alignItems: 'flex-end', gap: 10,
              maxWidth: isDesktop ? 800 : '100%',
              alignSelf: 'center',
              width: '100%',
            }}>
              <View style={{
                flex: 1, flexDirection: 'row', alignItems: 'flex-end',
                backgroundColor: C.bg, borderRadius: 14, borderWidth: 1, borderColor: C.border,
                paddingHorizontal: 14, paddingVertical: Platform.OS === 'web' ? 4 : 0,
                minHeight: 44,
              }}>
                <TextInput accessibilityLabel="Type a message..."
                  style={{
                    flex: 1, fontSize: isMobile ? 14 : 15, color: C.text,
                    paddingVertical: isMobile ? 10 : 12,
                    maxHeight: 120, lineHeight: 20,
                    ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}),
                  }}
                  placeholder="Type a message..."
                  placeholderTextColor={C.muted}
                  value={input}
                  onChangeText={setInput}
                  onSubmitEditing={() => handleSend()}
                  multiline
                  data-testid="ai-chat-input" testID="ai-chat-input"
                />
              </View>
              <TouchableOpacity onPress={() => handleSend()} accessibilityLabel="Ai chat send button"
                disabled={loading || !input.trim()}
                style={{
                  width: isMobile ? 44 : 48, height: isMobile ? 44 : 48, borderRadius: 14,
                  backgroundColor: input.trim() ? C.primary : C.border,
                  alignItems: 'center', justifyContent: 'center',
                  opacity: loading ? 0.6 : 1,
                  ...(Platform.OS === 'web' && input.trim() ? {
                    transition: 'all 0.2s ease',
                    boxShadow: `0 2px 12px ${C.primary}40`,
                  } as any : {}),
                }}
                data-testid="ai-chat-send-btn" testID="ai-chat-send-btn"
                accessibilityRole="button"
              >
                {loading ? (
                  <ActivityIndicator size="small" color={activeColors.primaryText} />
                ) : (
                  <Ionicons name="send" size={isMobile ? 18 : 20} color={activeColors.primaryText} />
                )}
              </TouchableOpacity>
            </View>
            {!isMobile && Platform.OS === 'web' && (
              <Text style={{ fontSize: 10, color: C.muted, textAlign: 'center', marginTop: 6 }}>
                Press Enter to send
              </Text>
            )}
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

/* i18n-probe t('i18n.auto.probe') */
