import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Keyboard, Platform, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useGlobalPlatformState } from '../../hooks/useGlobalPlatformState';
import NovaChatPanel from '../help/NovaChatPanel';
import { buildNovaQuickQuestionFallbacks } from '../../constants/novaPersona';
import type { ChatMessage } from '../help/helpTypes';
import { NovaSurfaceShell } from '../nova/NovaSurfaceShell';

type FavoriteItem = { message_id: string; conversation_id: string; content: string; updated_at?: string };
type PinItem = { conversation_id: string; preview?: string; updated_at?: string };

export default function SettingsNovaAssistantPanel() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { colors } = useTheme();
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const { state: gpsState } = useGlobalPlatformState();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [attachmentPreview, setAttachmentPreview] = useState<{ name: string; type: string; uri: string } | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [retryPrompt, setRetryPrompt] = useState<string | null>(null);
  const [favoriteMessageIds, setFavoriteMessageIds] = useState<string[]>([]);
  const [favoriteItems, setFavoriteItems] = useState<FavoriteItem[]>([]);
  const [pinnedItems, setPinnedItems] = useState<PinItem[]>([]);
  const [conversationPinned, setConversationPinned] = useState(false);
  const [curationLoaded, setCurationLoaded] = useState(false);
  const isPhone = width < 640;

  const fileInputRef = useRef<any>(null);
  const chatScrollRef = useRef<ScrollView>(null);
  const mediaRecorderRef = useRef<any>(null);
  const audioChunksRef = useRef<any[]>([]);
  const recordingTimerRef = useRef<any>(null);

  const quickQuestions = useMemo(() => {
    const qs = gpsState?.messaging?.quick_questions;
    const fromGps = Array.isArray(qs) ? qs.filter((q: any) => typeof q === 'string' && q.trim().length > 0) : [];
    return (fromGps.length > 0 ? fromGps : buildNovaQuickQuestionFallbacks(t)).slice(0, 4);
  }, [gpsState?.messaging, t]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return;
    setMessages((prev) => [
      ...prev,
      { id: `su-${Date.now()}`, role: 'user', content: text.trim(), timestamp: new Date().toISOString() },
    ]);
    setInputText('');
    setIsLoading(true);
    Keyboard.dismiss();

    try {
      const payload: any = { message: text.trim() };
      if (conversationId) payload.conversation_id = conversationId;
      const res = await api.post('/support/chat', payload, { timeout: 20000 });
      if (!conversationId) setConversationId(res.data.conversation_id);
      setRetryPrompt(null);
      setFeedbackSent(false);
      setFeedbackRating(0);
      setFeedbackComment('');
      setShowFeedback(true);
      setMessages((prev) => [
        ...prev,
        {
          id: `sa-${Date.now()}`,
          message_id: res.data?.assistant_message_id,
          role: 'assistant',
          content: res.data.message,
          timestamp: res.data.timestamp,
          gps_context: res.data?.gps_context,
        },
      ]);
    } catch (error: any) {
      const status = Number(error?.status || error?.response?.status || 0);
      const timeoutError = status === 408 || status === 504 || String(error?.message || '').toLowerCase().includes('timed out');
      if (timeoutError) setRetryPrompt(text.trim());
      const fallback = status === 401
        ? (t('help.chat.signInRequired') || 'Please sign in again to continue chatting with Nova.')
        : timeoutError
          ? (t('help.chat.timeout') || 'Nova is taking longer than expected. Please try again in a moment.')
          : (t('help.chat.connectionIssue') || "I'm having trouble connecting. Please try again.");
      setMessages((prev) => [
        ...prev,
        { id: `se-${Date.now()}`, role: 'assistant', content: fallback, timestamp: new Date().toISOString() },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [conversationId, isLoading, t]);

  const onRetryTimeout = useCallback(() => {
    if (!retryPrompt || isLoading) return;
    void sendMessage(retryPrompt);
  }, [retryPrompt, isLoading, sendMessage]);

  const handleAttachment = useCallback(async () => {
    if (Platform.OS !== 'web') return;
    fileInputRef.current?.click();
  }, []);

  const onFileSelected = useCallback(async (event: any) => {
    const file = event?.target?.files?.[0];
    if (!file) return;

    const allowed = [
      'image/png', 'image/jpeg', 'image/webp', 'image/gif', 'application/pdf', 'text/plain',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ];
    if (!allowed.includes(file.type)) {
      window.alert('Please upload PNG, JPEG, WebP, GIF, PDF, TXT, or DOCX files.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      window.alert('File too large. Max 10MB.');
      return;
    }

    setAttachmentPreview({ name: file.name, type: file.type, uri: URL.createObjectURL(file) });
    setIsLoading(true);
    const userMsg = inputText.trim() || `Sent attachment: ${file.name}`;
    setMessages((prev) => [...prev, {
      id: `su-${Date.now()}`,
      role: 'user',
      content: userMsg,
      timestamp: new Date().toISOString(),
      attachment: { url: URL.createObjectURL(file), filename: file.name, content_type: file.type },
    }]);
    setInputText('');
    setAttachmentPreview(null);

    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('conversation_id', conversationId || '');
      fd.append('message', userMsg);
      const res = await api.post('/support/chat/attachment', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (!conversationId) setConversationId(res.data.conversation_id);
      setFeedbackSent(false);
      setFeedbackRating(0);
      setFeedbackComment('');
      setShowFeedback(true);
      setMessages((prev) => [...prev, {
        id: `sa-${Date.now()}`,
        message_id: res.data?.assistant_message_id,
        role: 'assistant',
        content: res.data.message,
        timestamp: res.data.timestamp,
        gps_context: res.data?.gps_context,
      }]);
    } catch {
      setMessages((prev) => [...prev, {
        id: `se-${Date.now()}`,
        role: 'assistant',
        content: "I received your file but had trouble analyzing it. Could you describe what you need help with?",
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setIsLoading(false);
      if (event?.target) event.target.value = '';
    }
  }, [conversationId, inputText]);

  const startRecording = useCallback(async () => {
    if (Platform.OS !== 'web') return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunksRef.current = [];
      recorder.ondataavailable = (e: any) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setRecordingTime(0);
      recordingTimerRef.current = setInterval(() => setRecordingTime((time) => time + 1), 1000);
    } catch {
      window.alert('Microphone access denied. Please allow microphone access to use voice messages.');
    }
  }, []);

  const stopRecording = useCallback(async () => {
    if (!mediaRecorderRef.current) return;
    clearInterval(recordingTimerRef.current);
    return new Promise<void>((resolve) => {
      mediaRecorderRef.current.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        mediaRecorderRef.current.stream.getTracks().forEach((track: any) => track.stop());
        setIsRecording(false);
        setRecordingTime(0);
        if (blob.size < 100) {
          window.alert('Recording too short.');
          resolve();
          return;
        }
        setIsLoading(true);
        setMessages((prev) => [...prev, { id: `su-${Date.now()}`, role: 'user', content: 'Sent a voice message...', timestamp: new Date().toISOString() }]);
        try {
          const fd = new FormData();
          fd.append('audio', blob, 'recording.webm');
          fd.append('conversation_id', conversationId || '');
          const res = await api.post('/support/chat/audio', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
          if (!conversationId) setConversationId(res.data.conversation_id);
          if (res.data.transcription) {
            setMessages((prev) => prev.map((m, idx) => (
              idx === prev.length - 1 && m.role === 'user'
                ? { ...m, content: res.data.transcription, transcription: res.data.transcription }
                : m
            )));
          }
          setFeedbackSent(false);
          setFeedbackRating(0);
          setFeedbackComment('');
          setShowFeedback(true);
          setMessages((prev) => [...prev, {
            id: `sa-${Date.now()}`,
            message_id: res.data?.assistant_message_id,
            role: 'assistant',
            content: res.data.message,
            timestamp: res.data.timestamp,
            gps_context: res.data?.gps_context,
          }]);
        } catch {
          setMessages((prev) => [...prev, { id: `se-${Date.now()}`, role: 'assistant', content: "I couldn't process the voice message. Please try typing your question instead.", timestamp: new Date().toISOString() }]);
        } finally {
          setIsLoading(false);
        }
        resolve();
      };
      mediaRecorderRef.current.stop();
    });
  }, [conversationId]);

  const submitFeedback = useCallback(async () => {
    if (!feedbackRating || !conversationId) return;
    try {
      await api.post('/support/chat/feedback', {
        conversation_id: conversationId,
        rating: feedbackRating,
        comment: feedbackComment,
        helpful: feedbackRating >= 4,
      });
      setFeedbackSent(true);
    } catch {
      window.alert?.('Could not submit feedback. Please try again.');
    }
  }, [conversationId, feedbackRating, feedbackComment]);

  const loadFavorites = useCallback(async () => {
    if (!isAuthenticated) return;
    if (curationLoaded) return;
    try {
      const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : '';
      const res = await api.get(`/support/chat/messages/favorites${query}`, { timeout: 10000, silentLoading: true });
      const items = Array.isArray(res?.data?.favorites) ? res.data.favorites : [];
      setFavoriteItems(items);
      setFavoriteMessageIds(items.map((item: FavoriteItem) => item.message_id).filter(Boolean));
    } catch {
      setFavoriteItems([]);
      setFavoriteMessageIds([]);
    } finally {
      setCurationLoaded(true);
    }
  }, [conversationId, curationLoaded, isAuthenticated]);

  const loadPins = useCallback(async () => {
    if (!isAuthenticated) return;
    if (curationLoaded) return;
    try {
      const res = await api.get('/support/chat/conversations/pins', { timeout: 10000, silentLoading: true });
      const items = Array.isArray(res?.data?.pins) ? res.data.pins : [];
      setPinnedItems(items);
      setConversationPinned(Boolean(conversationId && items.some((pin: PinItem) => pin.conversation_id === conversationId)));
    } catch {
      setPinnedItems([]);
      setConversationPinned(false);
    } finally {
      setCurationLoaded(true);
    }
  }, [conversationId, curationLoaded, isAuthenticated]);

  const toggleFavoriteMessage = useCallback(async (message: ChatMessage) => {
    if (!conversationId || !message?.message_id) return;
    const isFavorite = favoriteMessageIds.includes(message.message_id);
    try {
      if (isFavorite) {
        await api.delete('/support/chat/messages/favorite', {
          data: { conversation_id: conversationId, message_id: message.message_id },
          timeout: 10000,
        });
      } else {
        await api.post('/support/chat/messages/favorite', {
          conversation_id: conversationId,
          message_id: message.message_id,
        }, { timeout: 10000 });
      }
      await loadFavorites();
    } catch {
      window.alert('Could not update favorites. Please try again.');
    }
  }, [conversationId, favoriteMessageIds, loadFavorites]);

  const togglePinConversation = useCallback(async () => {
    if (!conversationId) {
      window.alert('Start a conversation first, then pin it.');
      return;
    }
    try {
      if (conversationPinned) {
        await api.delete('/support/chat/conversations/pin', {
          data: { conversation_id: conversationId },
          timeout: 10000,
        });
      } else {
        await api.post('/support/chat/conversations/pin', { conversation_id: conversationId }, { timeout: 10000 });
      }
      await loadPins();
    } catch {
      window.alert('Could not update pinned conversations. Please try again.');
    }
  }, [conversationId, conversationPinned, loadPins]);

  const useFavoriteSnippet = useCallback((content: string) => {
    setInputText(content);
  }, []);

  useEffect(() => {
    requestAnimationFrame(() => {
      setTimeout(() => chatScrollRef.current?.scrollToEnd({ animated: messages.length > 1 }), 80);
    });
  }, [messages.length, isLoading]);

  useEffect(() => {
    if (!isAuthenticated || curationLoaded || !conversationId) return;
    void loadFavorites();
  }, [conversationId, curationLoaded, isAuthenticated, loadFavorites]);

  useEffect(() => {
    if (!isAuthenticated || curationLoaded || messages.length === 0) return;
    void loadPins();
  }, [curationLoaded, isAuthenticated, loadPins, messages.length]);

  const onNewChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setShowFeedback(false);
    setFeedbackSent(false);
    setFeedbackRating(0);
    setFeedbackComment('');
    setFavoriteItems([]);
    setFavoriteMessageIds([]);
    setConversationPinned(false);
    setCurationLoaded(false);
  }, []);

  return (
    <View style={{ minHeight: isPhone ? 560 : 760 }} data-testid="settings-nova-assistant-panel" testID="settings-nova-assistant-panel">
      {!isAuthenticated ? (
        <View
          style={{
            borderRadius: 12,
            borderWidth: 1,
            borderColor: `${colors.warning}55`,
            backgroundColor: `${colors.warning}12`,
            padding: 14,
            marginBottom: 12,
          }}
          data-testid="settings-nova-auth-required"
          testID="settings-nova-auth-required"
        >
          <Text
            style={{ color: colors.warningText, fontSize: 14, fontWeight: '800' }}
            data-testid="settings-nova-auth-required-title"
            testID="settings-nova-auth-required-title"
          >
            Sign in required
          </Text>
          <Text
            style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}
            data-testid="settings-nova-auth-required-subtitle"
            testID="settings-nova-auth-required-subtitle"
          >
            Nova Assistant in Settings is available only for logged-in users.
          </Text>
        </View>
      ) : null}

      {isAuthenticated ? (
        <>
          <NovaSurfaceShell
            colors={{ card: colors.card, bgSoft: colors.bgSoft, border: colors.border, text: colors.text, textMuted: colors.textMuted }}
            shellTestId="settings-nova-surface-shell"
            headerTestId="settings-nova-surface-header"
            titleTestId="settings-nova-surface-title"
            avatarWrapTestId="settings-nova-avatar-frame"
            avatarImageTestId="settings-nova-avatar-image"
            metaTestId="settings-nova-surface-meta"
            title="Nova"
            headerMeta={<View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 1 }}><View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success }} /><Text style={{ fontSize: 11, color: colors.successText, fontWeight: '600' }}>Available 24/7</Text></View>}
            headerActions={messages.length > 0 ? (
              <>
                <TouchableOpacity
                  data-testid="chat-conversation-pin-toggle"
                  testID="chat-conversation-pin-toggle"
                  style={{ width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center', borderWidth: 1, backgroundColor: colors.bgSoft, borderColor: colors.border }}
                  onPress={togglePinConversation}
                  disabled={!conversationId}
                >
                  <Ionicons name={conversationPinned ? 'bookmark' : 'bookmark-outline'} size={16} color={conversationPinned ? colors.warningText : colors.primary} />
                </TouchableOpacity>
                <TouchableOpacity data-testid="chat-new-btn" testID="chat-new-btn" style={{ width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center', borderWidth: 1, backgroundColor: colors.bgSoft, borderColor: colors.border }} onPress={onNewChat}>
                  <Ionicons name="add" size={18} color={colors.primary} />
                </TouchableOpacity>
              </>
            ) : null}
            bodyTestId="settings-nova-surface-body"
            body={(
              <NovaChatPanel
                C={colors as any}
                t={t}
                messages={messages}
                inputText={inputText}
                setInputText={setInputText}
                isLoading={isLoading}
                isRecording={isRecording}
                recordingTime={recordingTime}
                showFeedback={showFeedback}
                setShowFeedback={setShowFeedback}
                feedbackRating={feedbackRating}
                setFeedbackRating={setFeedbackRating}
                feedbackComment={feedbackComment}
                setFeedbackComment={setFeedbackComment}
                feedbackSent={feedbackSent}
                quickQuestions={quickQuestions}
                attachmentPreview={attachmentPreview}
                setAttachmentPreview={setAttachmentPreview}
                sendMessage={sendMessage}
                retryPrompt={retryPrompt}
                onRetryTimeout={onRetryTimeout}
                handleAttachment={handleAttachment}
                onFileSelected={onFileSelected}
                startRecording={startRecording}
                stopRecording={stopRecording}
                submitFeedback={submitFeedback}
                onNewChat={onNewChat}
                chatScrollRef={chatScrollRef}
                fileInputRef={fileInputRef}
                conversationId={conversationId}
                conversationPinned={conversationPinned}
                onToggleConversationPin={togglePinConversation}
                favoriteMessageIds={favoriteMessageIds}
                onToggleFavoriteMessage={toggleFavoriteMessage}
                favoriteSnippets={favoriteItems.map((item) => ({ message_id: item.message_id, content: item.content }))}
                onUseFavoriteSnippet={useFavoriteSnippet}
                surfaceVariant="embedded"
              />
            )}
            footerTestId="settings-nova-curation-panels"
            footer={(
              <View style={{ gap: 10, display: isPhone ? 'none' : 'flex' }}>
                <TouchableOpacity
                  onPress={() => router.push('/nova-curation-hub')}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primary, paddingHorizontal: 10, paddingVertical: 8, alignSelf: 'flex-start' }}
                  data-testid="settings-nova-open-curation-hub-button"
                  testID="settings-nova-open-curation-hub-button"
                >
                  <Text style={{ color: colors.primaryText || colors.text, fontSize: 11, fontWeight: '800' }}>Open full Pinned & Favorites hub</Text>
                </TouchableOpacity>

                <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="settings-nova-pinned-list" testID="settings-nova-pinned-list">
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="settings-nova-pinned-list-title" testID="settings-nova-pinned-list-title">
                    Pinned conversations ({pinnedItems.length})
                  </Text>
                  <View style={{ marginTop: 8, gap: 6 }}>
                    {pinnedItems.slice(0, 3).map((pin) => (
                      <TouchableOpacity
                        key={pin.conversation_id}
                        onPress={() => setInputText((pin.preview || '').slice(0, 120))}
                        style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 8, paddingVertical: 7 }}
                        data-testid={`settings-nova-pinned-item-${pin.conversation_id}`}
                        testID={`settings-nova-pinned-item-${pin.conversation_id}`}
                      >
                        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }} numberOfLines={2}>{pin.preview || pin.conversation_id}</Text>
                      </TouchableOpacity>
                    ))}
                    {pinnedItems.length === 0 ? (
                      <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="settings-nova-pinned-empty" testID="settings-nova-pinned-empty">No pinned conversations yet.</Text>
                    ) : null}
                  </View>
                </View>

                <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="settings-nova-favorites-list" testID="settings-nova-favorites-list">
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="settings-nova-favorites-list-title" testID="settings-nova-favorites-list-title">
                    Favorite answers ({favoriteItems.length})
                  </Text>
                  <View style={{ marginTop: 8, gap: 6 }}>
                    {favoriteItems.slice(0, 4).map((fav) => (
                      <TouchableOpacity
                        key={fav.message_id}
                        onPress={() => setInputText(fav.content.slice(0, 200))}
                        style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 8, paddingVertical: 7 }}
                        data-testid={`settings-nova-favorite-item-${fav.message_id}`}
                        testID={`settings-nova-favorite-item-${fav.message_id}`}
                      >
                        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }} numberOfLines={2}>{fav.content}</Text>
                      </TouchableOpacity>
                    ))}
                    {favoriteItems.length === 0 ? (
                      <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="settings-nova-favorites-empty" testID="settings-nova-favorites-empty">No favorites yet.</Text>
                    ) : null}
                  </View>
                </View>
              </View>
            )}
          />
        </>
      ) : null}
    </View>
  );
}