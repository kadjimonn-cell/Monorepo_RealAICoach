import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Platform, KeyboardAvoidingView, StyleSheet, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { ChatMessage, ThemeColors } from './helpTypes';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { NOVA_INTRO_FALLBACK } from '../../constants/novaPersona';
import { NovaAvatarBadge } from '../common/NovaIdentityBadge';
import { getSpeechSynthesisSupport, loadPreferredNovaVoice } from '../../utils/novaSpeech';
import { NovaFeedbackCard } from './NovaFeedbackCard';
import { NovaComposer } from './NovaComposer';
import { useNovaTypewriter } from './useNovaTypewriter';
import { NovaTypingDots } from './NovaTypingDots';

interface NovaChatPanelProps {
  C: ThemeColors;
  t: (key: string) => string;
  messages: ChatMessage[];
  inputText: string;
  setInputText: (v: string) => void;
  isLoading: boolean;
  isRecording: boolean;
  recordingTime: number;
  showFeedback: boolean;
  setShowFeedback: (v: boolean) => void;
  feedbackRating: number;
  setFeedbackRating: (v: number) => void;
  feedbackComment: string;
  setFeedbackComment: (v: string) => void;
  feedbackSent: boolean;
  quickQuestions: string[];
  attachmentPreview: { name: string; type: string; uri: string } | null;
  setAttachmentPreview: (v: any) => void;
  sendMessage: (msg: string) => void;
  retryPrompt?: string | null;
  onRetryTimeout?: () => void;
  handleAttachment: () => void;
  onFileSelected: (e: any) => void;
  startRecording: () => void;
  stopRecording: () => void;
  submitFeedback: () => void;
  onNewChat: () => void;
  chatScrollRef: React.RefObject<ScrollView>;
  fileInputRef: React.RefObject<any>;
  conversationId?: string | null;
  conversationPinned?: boolean;
  onToggleConversationPin?: () => void;
  favoriteMessageIds?: string[];
  onToggleFavoriteMessage?: (msg: ChatMessage) => void;
  favoriteSnippets?: { message_id: string; content: string }[];
  onUseFavoriteSnippet?: (content: string) => void;
  surfaceVariant?: 'default' | 'embedded' | 'floating';
  inputRef?: React.RefObject<any>;
  statusOverride?: {
    health: 'checking' | 'healthy' | 'degraded';
    hasLiveAssistantReply: boolean;
    latestAssistantMessage?: ChatMessage | null;
    favoriteSnippets?: { message_id: string; content: string }[];
    pinnedCount?: number;
    conversationPinned?: boolean;
  };
}

export default function NovaChatPanel(props: NovaChatPanelProps) {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const [novaHealth, setNovaHealth] = useState<'checking' | 'healthy' | 'degraded'>('checking');
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null);
  const healthFailureStreakRef = useRef(0);
  const lastStableHealthRef = useRef<'checking' | 'healthy' | 'degraded'>('checking');
  const isPhone = width < 640;
  const isTablet = width >= 640 && width < 1024;
  const panelMinHeight = isPhone ? 520 : isTablet ? 620 : 700;
  const messageMinHeight = isPhone ? 260 : isTablet ? 320 : 380;
  const embeddedMessageMinHeight = isPhone ? 136 : isTablet ? 180 : 220;

  const s = StyleSheet.create({
    qChips: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8 },
    qChip: { paddingHorizontal: 14, paddingVertical: 9, borderRadius: 12, borderWidth: 1 },
    bubble: { flexDirection: 'row', marginBottom: 10 },
    bubbleR: { justifyContent: 'flex-end' },
    bubbleL: { justifyContent: 'flex-start' },
    bubbleAv: { width: 24, height: 24, borderRadius: 8, alignItems: 'center', justifyContent: 'center', marginRight: 6, marginTop: 4 },
    bubbleBody: { maxWidth: '100%', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 14 },
  });
  const { C, t, messages, inputText, setInputText, isLoading, isRecording, recordingTime,
    showFeedback, setShowFeedback, feedbackRating, setFeedbackRating, feedbackComment, setFeedbackComment,
    feedbackSent, quickQuestions, attachmentPreview, setAttachmentPreview, sendMessage, retryPrompt, onRetryTimeout, handleAttachment, onFileSelected,
    startRecording, stopRecording, submitFeedback, chatScrollRef, fileInputRef,
    conversationPinned, favoriteMessageIds = [], onToggleFavoriteMessage,
    favoriteSnippets = [], onUseFavoriteSnippet, surfaceVariant = 'default', inputRef, statusOverride } = props;
  const isEmbedded = surfaceVariant === 'embedded';
  const isFloating = surfaceVariant === 'floating';
  const typewriter = useNovaTypewriter(messages);

  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return !value || value === key ? fallback : value;
  };
  const enterpriseIntro = tx('help.nova.enterpriseIntro', NOVA_INTRO_FALLBACK);
  const panelShellStyle = useMemo(() => {
    if (!isEmbedded && !isFloating) {
      return { minHeight: panelMinHeight };
    }
    return {
      flex: 1,
      minHeight: 0,
      height: undefined,
      overflow: 'hidden' as const,
    };
  }, [isEmbedded, isFloating, panelMinHeight]);
  const hasMeaningfulConversation = useMemo(
    () => messages.some((msg) => msg.role === 'user' || !!msg.message_id) || messages.length > 1,
    [messages],
  );
  const seededAssistantOpening = useMemo(
    () => (!hasMeaningfulConversation ? messages.find((msg) => msg.role === 'assistant') || null : null),
    [hasMeaningfulConversation, messages],
  );
  const showGuidedWelcome = !hasMeaningfulConversation;
  const scrollMinHeight = isEmbedded
    ? embeddedMessageMinHeight
    : isFloating
      ? (isPhone ? 180 : isTablet ? 220 : 260)
      : messageMinHeight;
  const latestAssistantMessage = useMemo(() => {
    const found = [...messages].reverse().find((msg) => msg.role === 'assistant');
    return found || null;
  }, [messages]);
  const hasLiveAssistantReply = useMemo(
    () => messages.some((msg) => msg.role === 'assistant' && !!msg.message_id),
    [messages],
  );
  const resolvedLatestAssistantMessage = statusOverride?.latestAssistantMessage ?? latestAssistantMessage;
  const resolvedHasLiveAssistantReply = typeof statusOverride?.hasLiveAssistantReply === 'boolean'
    ? statusOverride.hasLiveAssistantReply
    : hasLiveAssistantReply;
  const resolvedNovaHealth = statusOverride?.health ?? novaHealth;
  const resolvedFavoriteSnippets = statusOverride?.favoriteSnippets ?? favoriteSnippets;
  const resolvedPinnedCount = typeof statusOverride?.pinnedCount === 'number' ? statusOverride.pinnedCount : undefined;
  const resolvedConversationPinned = typeof statusOverride?.conversationPinned === 'boolean' ? statusOverride.conversationPinned : conversationPinned;

  const speakMessage = (messageId: string, text: string) => {
    if (Platform.OS !== 'web') return;
    const speech = getSpeechSynthesisSupport();
    if (!speech) return;

    if (speakingMessageId === messageId) {
      speech.cancel();
      setSpeakingMessageId(null);
      return;
    }

    speech.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1.08;
    utterance.onend = () => setSpeakingMessageId(null);
    utterance.onerror = () => setSpeakingMessageId(null);
    setSpeakingMessageId(messageId);
    void loadPreferredNovaVoice().then((voice) => {
      if (voice) utterance.voice = voice;
      speech.speak(utterance);
    }).catch(() => {
      speech.speak(utterance);
    });
  };

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      try {
        const res = await api.get('/support/nova/health?hours=1', { timeout: 10000, silentLoading: true });
        if (!mounted) return;
        const status = String(res?.data?.status || '').toLowerCase();
        const nextHealth: 'checking' | 'healthy' | 'degraded' = status === 'healthy'
          ? 'healthy'
          : status === 'degraded'
            ? 'degraded'
            : 'checking';
        healthFailureStreakRef.current = 0;
        if (nextHealth !== 'checking') {
          lastStableHealthRef.current = nextHealth;
        }
        setNovaHealth(nextHealth);
      } catch {
        if (!mounted) return;
        healthFailureStreakRef.current += 1;
        if (lastStableHealthRef.current === 'healthy') {
          setNovaHealth('healthy');
          return;
        }
        setNovaHealth(healthFailureStreakRef.current >= 3 ? 'degraded' : 'checking');
      }
    };

    void poll();
    const timer = setInterval(() => { void poll(); }, 60000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (showGuidedWelcome) return;
    requestAnimationFrame(() => {
      setTimeout(() => {
        chatScrollRef.current?.scrollToEnd({ animated: messages.length > 1 });
      }, 80);
    });
  }, [chatScrollRef, messages.length, isLoading, showGuidedWelcome]);

  return (
    <KeyboardAvoidingView
      style={panelShellStyle}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      data-testid="nova-chat-panel"
      testID="nova-chat-panel"
    >
      <ScrollView
        ref={chatScrollRef}
        style={{ flex: 1, minHeight: scrollMinHeight }}
        contentContainerStyle={{ padding: isEmbedded ? 14 : isFloating ? 12 : 16, paddingBottom: isEmbedded ? 12 : isFloating ? 10 : 8, flexGrow: 1, justifyContent: showGuidedWelcome ? 'flex-start' : 'flex-end' }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        onContentSizeChange={() => {
          if (showGuidedWelcome) return;
          setTimeout(() => chatScrollRef.current?.scrollToEnd({ animated: false }), 40);
        }}
      >
        {showGuidedWelcome ? (
          <View style={{ alignItems: isEmbedded || isFloating ? 'stretch' : 'center', paddingVertical: isEmbedded ? 6 : isFloating ? 4 : 24, minHeight: isEmbedded || isFloating ? undefined : messageMinHeight - 24 }} data-testid="chat-welcome" testID="chat-welcome">
            <NovaAvatarBadge
              size={isEmbedded || isFloating ? 52 : 64}
              ringColor={C.border}
              surfaceColor={C.card}
              animationPreset="subtle"
              wrapTestId="help-nova-welcome-avatar-frame"
              imageTestId="help-nova-welcome-avatar-image"
            />
            <Text style={{ fontSize: isEmbedded || isFloating ? 18 : 20, fontWeight: '800', color: C.text, marginBottom: 4, marginTop: isEmbedded || isFloating ? 10 : 0, letterSpacing: -0.5, textAlign: isEmbedded || isFloating ? 'left' : 'center' }}>{t('help.nova.welcome')}</Text>
            <Text style={{ fontSize: 14, color: C.primary, fontWeight: '600', marginBottom: 8, textAlign: isEmbedded || isFloating ? 'left' : 'center' }}>{t('help.nova.subtitle')}</Text>
            <View
              style={{
                marginBottom: 8,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: colors.warningText,
                backgroundColor: `${colors.warningText}18`,
                paddingHorizontal: 14,
                paddingVertical: 10,
                marginHorizontal: isEmbedded || isFloating ? 0 : 14,
                alignSelf: isEmbedded || isFloating ? 'stretch' : 'auto',
              }}
              data-testid="help-nova-enterprise-intro-card"
              testID="help-nova-enterprise-intro-card"
            >
              <Text style={{ fontSize: 13, color: C.text, textAlign: isEmbedded || isFloating ? 'left' : 'center', lineHeight: 20, fontWeight: '700' }} data-testid="help-nova-enterprise-intro-text" testID="help-nova-enterprise-intro-text">
                {enterpriseIntro}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 6, marginBottom: isEmbedded || isFloating ? 12 : 16, flexWrap: 'wrap', justifyContent: isEmbedded || isFloating ? 'flex-start' : 'center', paddingHorizontal: isEmbedded || isFloating ? 0 : 16 }}>
              {[
                { icon: 'attach' as const, label: t('help.nova.attachments'), action: handleAttachment },
                { icon: 'mic' as const, label: t('help.nova.voice'), action: startRecording },
                { icon: 'sparkles' as const, label: 'GPT-5.2', action: undefined },
              ].map(b => (
                b.action ? (
                  <TouchableOpacity key={b.label} data-testid={`welcome-badge-${b.icon}`} testID={`welcome-badge-${b.icon}`}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: C.bgSoft, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, borderWidth: 1, borderColor: C.border }}
                    onPress={b.action} activeOpacity={0.7}>
                    <Ionicons name={b.icon} size={13} color={C.primary} />
                    <Text style={{ fontSize: 11, color: C.primary, fontWeight: '700' }}>{b.label}</Text>
                  </TouchableOpacity>
                ) : (
                  <View key={b.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
                    <Ionicons name={b.icon} size={13} color={C.textMuted} />
                    <Text style={{ fontSize: 11, color: C.textMuted, fontWeight: '600' }}>{b.label}</Text>
                  </View>
                )
              ))}
            </View>
            <View style={[s.qChips, isEmbedded || isFloating ? { justifyContent: 'flex-start' } : null]}>
              {quickQuestions.map((q, i) => (
                <TouchableOpacity key={i} data-testid={`quick-q-${i}`} testID={`quick-q-${i}`} style={[s.qChip, { backgroundColor: C.card, borderColor: C.border }]} onPress={() => sendMessage(q)}>
                  <Text style={{ fontSize: 12, color: C.textSec, fontWeight: '600' }}>{q}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {seededAssistantOpening?.content ? (
              <View
                style={{
                  marginTop: 14,
                  width: '100%',
                  borderRadius: 16,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.card,
                  paddingHorizontal: 14,
                  paddingVertical: 12,
                  alignSelf: isEmbedded || isFloating ? 'stretch' : 'center',
                  maxWidth: isEmbedded || isFloating ? undefined : 560,
                }}
                data-testid="chat-seeded-assistant-opening"
                testID="chat-seeded-assistant-opening"
              >
                <Text style={{ fontSize: 11, fontWeight: '800', color: colors.successText, marginBottom: 6 }}>Nova</Text>
                <Text style={{ fontSize: 14, lineHeight: 21, color: C.text }}>{seededAssistantOpening.content}</Text>
              </View>
            ) : null}
          </View>
        ) : (
          <>
          {messages.map(msg => (
            <View key={msg.id} style={[s.bubble, msg.role === 'user' ? s.bubbleR : s.bubbleL]}>
              {msg.role === 'assistant' && (
                <View style={[s.bubbleAv, { backgroundColor: colors.success }]}>
                  <Ionicons name="sparkles" size={12} color={colors.primaryText} />
                </View>
              )}
              <View style={{ maxWidth: isPhone ? '92%' : '78%' }}>
                {msg.role === 'assistant' && (
                  <Text style={{ fontSize: 10, fontWeight: '700', color: colors.successText, marginBottom: 3, marginLeft: 2 }}>Nova</Text>
                )}
                {msg.attachment && msg.attachment.content_type?.startsWith('image/') && (
                  <View style={{ marginBottom: 6, borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: C.border }}>
                    <img src={msg.attachment.url} alt={msg.attachment.filename} style={{ maxWidth: 220, maxHeight: 160, objectFit: 'cover', borderRadius: 12, display: 'block' } as any} />
                  </View>
                )}
                {msg.attachment && !msg.attachment.content_type?.startsWith('image/') && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6, backgroundColor: C.bgSoft, padding: 8, borderRadius: 8, borderWidth: 1, borderColor: C.border }}>
                    <Ionicons name="document-attach" size={16} color={C.primary} />
                    <Text style={{ fontSize: 11, color: C.text, fontWeight: '600' }} numberOfLines={1}>{msg.attachment.filename}</Text>
                  </View>
                )}
                {msg.transcription && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4, opacity: 0.7 }}>
                    <Ionicons name="mic" size={10} color={C.primary} />
                    <Text style={{ fontSize: 9, color: C.primary, fontWeight: '600' }}>{t('help.nova.voiceMessage')}</Text>
                  </View>
                )}
                <View style={[s.bubbleBody, msg.role === 'user' ? { backgroundColor: C.primary, borderBottomRightRadius: 4 } : { backgroundColor: C.card, borderBottomLeftRadius: 4, borderWidth: 1, borderColor: C.border }]}> 
                  <Text
                    style={{ fontSize: 14, lineHeight: 21, color: msg.role === 'user' ? colors.primaryText : C.text }}
                    onPress={typewriter.isAnimating(msg) ? typewriter.skip : undefined}
                    data-testid={`chat-message-${msg.id}-content`}
                    testID={`chat-message-${msg.id}-content`}
                  >
                    {typewriter.getVisibleContent(msg)}
                    {typewriter.isAnimating(msg) ? (
                      <Text style={{ color: C.primary }} data-testid={`chat-message-${msg.id}-typewriter-cursor`} testID={`chat-message-${msg.id}-typewriter-cursor`}>▍</Text>
                    ) : null}
                  </Text>
                </View>
                {msg.role === 'assistant' && !typewriter.isAnimating(msg) ? (
                  <View style={{ marginTop: 6, flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    <TouchableOpacity
                      onPress={() => speakMessage(msg.id, msg.content)}
                      data-testid={`chat-message-${msg.id}-audio-button`}
                      testID={`chat-message-${msg.id}-audio-button`}
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 4,
                        borderWidth: 1,
                        borderColor: C.border,
                        backgroundColor: C.bgSoft,
                        borderRadius: 999,
                        paddingHorizontal: 9,
                        paddingVertical: 5,
                      }}
                    >
                      <Ionicons name={speakingMessageId === msg.id ? 'stop-circle-outline' : 'volume-high-outline'} size={13} color={C.primary} />
                      <Text style={{ color: C.primary, fontSize: 10, fontWeight: '700' }}>
                        {speakingMessageId === msg.id ? tx('help.chat.stopAudio', 'Stop') : tx('help.chat.playAudio', 'Play audio')}
                      </Text>
                    </TouchableOpacity>
                    <TouchableOpacity accessibilityLabel="Set feedback rating in nova chat panel"
                      onPress={() => {
                        setFeedbackRating(5);
                        setShowFeedback(true);
                      }}
                      data-testid={`chat-message-${msg.id}-feedback-up`}
                      testID={`chat-message-${msg.id}-feedback-up`}
                      style={{ borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5 }}
                    >
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>👍</Text>
                    </TouchableOpacity>
                    <TouchableOpacity accessibilityLabel="Set feedback rating in nova chat panel"
                      onPress={() => {
                        setFeedbackRating(2);
                        setShowFeedback(true);
                      }}
                      data-testid={`chat-message-${msg.id}-feedback-down`}
                      testID={`chat-message-${msg.id}-feedback-down`}
                      style={{ borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5 }}
                    >
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>👎</Text>
                    </TouchableOpacity>
                    {onToggleFavoriteMessage ? (
                      <TouchableOpacity
                        onPress={() => onToggleFavoriteMessage(msg)}
                        data-testid={`chat-message-${msg.id}-favorite-toggle`}
                        testID={`chat-message-${msg.id}-favorite-toggle`}
                        style={{ borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5, flexDirection: 'row', alignItems: 'center', gap: 4 }}
                      >
                        <Ionicons name={msg.message_id && favoriteMessageIds.includes(msg.message_id) ? 'star' : 'star-outline'} size={12} color={colors.warningText} />
                        <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>
                          {msg.message_id && favoriteMessageIds.includes(msg.message_id) ? 'Saved' : 'Save'}
                        </Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                ) : null}
                <Text style={{ fontSize: 9, color: C.textMuted, marginTop: 3, textAlign: msg.role === 'user' ? 'right' : 'left', marginHorizontal: 4 }}>
                  {new Date(msg.timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                </Text>
              </View>
            </View>
          ))}

          <NovaFeedbackCard
            C={C}
            t={t}
            showFeedback={showFeedback}
            setShowFeedback={setShowFeedback}
            feedbackRating={feedbackRating}
            setFeedbackRating={setFeedbackRating}
            feedbackComment={feedbackComment}
            setFeedbackComment={setFeedbackComment}
            feedbackSent={feedbackSent}
            submitFeedback={submitFeedback}
            isEmbedded={isEmbedded}
            isFloating={isFloating}
          />
          </>
        )}
        {isLoading && (
          <View style={[s.bubble, s.bubbleL]}>
            <View style={[s.bubbleAv, { backgroundColor: colors.success }]}><Ionicons name="sparkles" size={12} color={colors.primaryText} /></View>
            <View style={{ maxWidth: '78%' }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: colors.successText, marginBottom: 3, marginLeft: 2 }}>Nova</Text>
              <View style={[s.bubbleBody, { backgroundColor: C.card, borderBottomLeftRadius: 4, paddingVertical: 14, paddingHorizontal: 18, borderWidth: 1, borderColor: C.border }]} data-testid="chat-typing-indicator" testID="chat-typing-indicator">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={{ fontSize: 12, color: C.textMuted, fontStyle: 'italic' }} data-testid="chat-typing-indicator-text" testID="chat-typing-indicator-text">{tx('help.chat.novaTyping', 'Nova is typing')}</Text>
                  <NovaTypingDots color={C.textMuted} />
                </View>
              </View>
            </View>
          </View>
        )}
      </ScrollView>

      <NovaComposer
        C={C}
        t={t}
        tx={tx}
        inputText={inputText}
        setInputText={setInputText}
        isLoading={isLoading}
        isRecording={isRecording}
        recordingTime={recordingTime}
        attachmentPreview={attachmentPreview}
        setAttachmentPreview={setAttachmentPreview}
        sendMessage={sendMessage}
        retryPrompt={retryPrompt}
        onRetryTimeout={onRetryTimeout}
        handleAttachment={handleAttachment}
        onFileSelected={onFileSelected}
        startRecording={startRecording}
        stopRecording={stopRecording}
        fileInputRef={fileInputRef}
        inputRef={inputRef}
        favoriteSnippets={resolvedFavoriteSnippets}
        onUseFavoriteSnippet={onUseFavoriteSnippet}
        health={resolvedNovaHealth}
        hasLiveAssistantReply={resolvedHasLiveAssistantReply}
        latestAssistantMessage={resolvedLatestAssistantMessage}
        pinnedCount={resolvedPinnedCount}
        conversationPinned={resolvedConversationPinned}
        isPhone={isPhone}
        isEmbedded={isEmbedded}
        isFloating={isFloating}
      />
    </KeyboardAvoidingView>
  );
}
