import React, { useMemo, useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity,
  Alert, Platform, Keyboard, useWindowDimensions, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useLanguage } from '../src/i18n/LanguageContext';
import { useAuth } from '../src/context/AuthContext';
import { useFeatures } from '../src/context/FeaturesContext';
import { useGlobalPlatformState } from '../src/hooks/useGlobalPlatformState';
import AppShell from '../src/components/AppShell';
import type {
  ChatMessage,
  FAQItem,
  TabKey,
  ContactMode,
  ThemeColors,
  SupportAISuggestion,
  SupportAttachmentDraft,
  SupportCategory,
  SupportDuplicateHint,
  SupportFAQHint,
  SupportInsights,
  SupportPriority,
} from '../src/components/help/helpTypes';
import SupportHeroTab from '../src/components/help/SupportHeroTab';
import FAQSection from '../src/components/help/FAQSection';
import FeatureIndexTab from '../src/components/help/FeatureIndexTab';
import NovaChatPanel from '../src/components/help/NovaChatPanel';
import { buildNovaQuickQuestionFallbacks } from '../src/constants/novaPersona';
import EmailFormEnterprise from '../src/components/help/EmailFormEnterprise';
import { NovaSurfaceShell } from '../src/components/nova/NovaSurfaceShell';
import { HelpSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import GpsLabelBlocker from '../src/components/GpsLabelBlocker';
import { GpsDataStatusCard } from '../src/components/GpsDataStatusCard';
import { reportClientCrash } from '../src/services/clientErrorReporter';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

type FavoriteItem = { message_id: string; conversation_id: string; content: string; updated_at?: string };
type PinItem = { conversation_id: string; preview?: string; updated_at?: string };
const NOVA_HUB_PREFILL_KEY = 'nova_hub_prefill_prompt';

export default function HelpScreen() {
  const pageReady = usePageReady();
  const router = useRouter();
  const { colors, darkMode } = useTheme();
  const { languageCode, t } = useLanguage();
  const { width } = useWindowDimensions();
  const { user, loading } = useAuth();
  const {
    state: gpsState,
    getMissingLabels,
    loading: gpsLoading,
    error: gpsError,
    refetch: gpsRefetch,
    diagnostics: gpsDiagnostics,
  } = useGlobalPlatformState();
  const isWide = width >= 768;
  const isTablet = width >= 768 && width < 1024;
  const isUltraCompact = width < 360;
  const useCompactNovaFooter = width < 768;
  const requiredHelpLabelKeys = ['help.surface.ready'];
  const missingHelpLabels = getMissingLabels(requiredHelpLabelKeys);

  // ─── Tab & Navigation State ───
  const [activeTab, setActiveTab] = useState<TabKey>('contact');
  const [contactMode, setContactMode] = useState<ContactMode>('chat');

  // ─── FAQ State ───
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedFAQ, setExpandedFAQ] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [faqs, setFaqs] = useState<FAQItem[]>([]);
  const [faqLoading, setFaqLoading] = useState(true);
  const [faqVotes, setFaqVotes] = useState<Record<string, 'up' | 'down'>>({});
  const [uiLabels, setUiLabels] = useState<Record<string, string>>({});

  // ─── Feature Index State ───
  const [featureSearch, setFeatureSearch] = useState('');
  const [featureCat, setFeatureCat] = useState<string | null>(null);

  // ─── Chat State ───
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [retryPrompt, setRetryPrompt] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [attachmentPreview, setAttachmentPreview] = useState<{ name: string; type: string; uri: string } | null>(null);
  const [favoriteMessageIds, setFavoriteMessageIds] = useState<string[]>([]);
  const [favoriteItems, setFavoriteItems] = useState<FavoriteItem[]>([]);
  const [pinnedItems, setPinnedItems] = useState<PinItem[]>([]);
  const [conversationPinned, setConversationPinned] = useState(false);
  const [curationLoaded, setCurationLoaded] = useState(false);
  const mediaRecorderRef = useRef<any>(null);
  const audioChunksRef = useRef<any[]>([]);
  const recordingTimerRef = useRef<any>(null);
  const fileInputRef = useRef<any>(null);
  const chatScrollRef = useRef<ScrollView>(null);

  // ─── Email State ───
  const [emailName, setEmailName] = useState('');
  const [emailAddress, setEmailAddress] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [emailMessage, setEmailMessage] = useState('');
  const [emailCategory, setEmailCategory] = useState<SupportCategory>('general');
  const [emailPriority, setEmailPriority] = useState<SupportPriority>('medium');
  const [emailAttachments, setEmailAttachments] = useState<SupportAttachmentDraft[]>([]);
  const [emailSending, setEmailSending] = useState(false);
  const [emailSuccess, setEmailSuccess] = useState<string | null>(null);
  const [emailSuggesting, setEmailSuggesting] = useState(false);
  const [emailInsights, setEmailInsights] = useState<SupportInsights | null>(null);
  const [aiSuggestion, setAiSuggestion] = useState<SupportAISuggestion | null>(null);
  const [duplicateHints, setDuplicateHints] = useState<SupportDuplicateHint[]>([]);
  const [faqHints, setFaqHints] = useState<SupportFAQHint[]>([]);
  const [reuseLastContextLoading, setReuseLastContextLoading] = useState(false);
  const [reuseLastContextMessage, setReuseLastContextMessage] = useState<string>('Prefill from your most recent resolved ticket.');

  // Redirect unauthenticated users via useEffect so subsequent hooks are
  // always called in the same order (rules-of-hooks compliance). Gate on
  // `loading` so we don't kick authenticated users out mid-hydration.
  useEffect(() => {
    if (!loading && !user) router.replace('/contact');
  }, [user, loading, router]);

  // ─── Theme Colors ───
  const C: ThemeColors = useMemo(() => ({
    primary: colors.primary, bg: colors.bg, bgSoft: colors.bgSoft, card: colors.card,
    text: colors.text, textSec: colors.textSec, textMuted: colors.textMuted, border: colors.border,
    success: colors.success, warning: colors.warning, error: colors.error, violet: colors.purple,
  }), [colors]);

  const L = useCallback((key: string, fallback?: string) => uiLabels[key] || fallback || key, [uiLabels]);

  // ─── Effects ───
  useEffect(() => {
    (async () => {
      setFaqLoading(true);
      try {
        const res = await api.get(`/support/faq?lang=${languageCode}`);
        setFaqs(res.data.faqs || []);
        if (res.data.labels) setUiLabels(res.data.labels);
      } catch (error) {
        handleAppRecoverableError({
          scope: 'help.tsx#catch1',
          error,
          message: 'Something went wrong. Please retry.',
          onRetry: () => { if (Platform.OS === 'web') window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
      } finally { setFaqLoading(false); }
    })();
  }, [languageCode]);

  useEffect(() => {
    if (chatScrollRef.current && messages.length > 0) {
      setTimeout(() => chatScrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [messages]);

  // Auto-prompt feedback after 4+ user messages
  useEffect(() => {
    const userMsgCount = messages.filter(m => m.role === 'user').length;
    if (userMsgCount >= 4 && !showFeedback && !feedbackSent && conversationId) {
      setShowFeedback(true);
    }
  }, [messages, showFeedback, feedbackSent, conversationId]);

  // ─── Computed ───
  const filteredFAQs = useMemo(() => {
    let list = faqs;
    if (activeCategory) list = list.filter(f => f.category === activeCategory);
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(f => f.q.toLowerCase().includes(q) || f.a.toLowerCase().includes(q));
    }
    return list;
  }, [faqs, activeCategory, searchQuery]);

  const { features: dynamicFeatures } = useFeatures();
  const allFeatures = useMemo(
    () => (dynamicFeatures.length > 0 ? dynamicFeatures : (gpsState?.features || []))
      .filter((feature) => feature?.enabled !== false && feature?.soft_deactivated !== true),
    [dynamicFeatures, gpsState?.features],
  );

  const quickQuestions = useMemo(() => {
    const qs = gpsState?.messaging?.quick_questions;
    const fromGps = Array.isArray(qs) ? qs.filter((q) => typeof q === 'string' && q.trim().length > 0) : [];
    return fromGps.length > 0 ? fromGps : buildNovaQuickQuestionFallbacks(t);
  }, [gpsState?.messaging, t]);

  const openNovaChat = useCallback(() => {
    setActiveTab('contact');
    setContactMode('chat');
  }, []);

  const openSupportEmail = useCallback(() => {
    setActiveTab('contact');
    setContactMode('email');
  }, []);

  const filteredFeatures = useMemo(() => {
    let list = allFeatures;
    if (featureCat) list = list.filter(f => f.category === featureCat);
    if (featureSearch.trim()) {
      const q = featureSearch.toLowerCase();
      list = list.filter(f => f.title.toLowerCase().includes(q) || f.description.toLowerCase().includes(q));
    }
    return list;
  }, [featureCat, featureSearch, allFeatures]);

  // ─── Handlers ───
  const voteFaq = useCallback(async (question: string, helpful: boolean) => {
    if (faqVotes[question]) return;
    setFaqVotes(prev => ({ ...prev, [question]: helpful ? 'up' : 'down' }));
    try {
      await api.post('/support/faq/feedback', { question, helpful });
    } catch (error) {
      handleAppRecoverableError({
        scope: 'help.tsx#catch2',
        error,
        message: 'Something went wrong. Please retry.',
        onRetry: async () => { await api.post('/support/faq/feedback', { question, helpful }); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, [faqVotes]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return;
    setMessages(prev => [...prev, { id: `u-${Date.now()}`, role: 'user', content: text.trim(), timestamp: new Date().toISOString() }]);
    setInputText('');
    setIsLoading(true);
    Keyboard.dismiss();
    try {
      const payload: any = { message: text.trim() };
      if (conversationId) payload.conversation_id = conversationId;
      const res = await api.post('/support/chat', payload, { timeout: 20000 });
      if (!conversationId) setConversationId(res.data.conversation_id);
      setRetryPrompt(null);
      setMessages(prev => [...prev, {
        id: `a-${Date.now()}`,
        message_id: res.data?.assistant_message_id,
        role: 'assistant',
        content: res.data.message,
        timestamp: res.data.timestamp,
        gps_context: res.data?.gps_context,
      }]);
    } catch (error: any) {
      const status = Number(error?.status || error?.response?.status || 0);
      const timeoutError = status === 408 || status === 504 || String(error?.message || '').toLowerCase().includes('timed out');
      reportClientCrash({
        panelId: 'help-nova-chat',
        panelName: 'Help Nova Chat',
        message: `help nova send failed status=${status || 'unknown'} timeout=${timeoutError ? '1' : '0'}`,
        stack: String(error?.stack || ''),
      });
      if (timeoutError) {
        setRetryPrompt(text.trim());
      } else {
        setRetryPrompt(null);
      }
      const content = status === 401
        ? (t('help.chat.signInRequired') || 'Please sign in again to continue chatting with Nova.')
        : timeoutError
          ? (t('help.chat.timeout') || 'Nova is taking longer than expected. Please try again in a moment.')
          : (t('help.chat.connectionIssue') || "I'm having trouble connecting. Please try again or email support@realaicoach.app.");
      setMessages(prev => [...prev, { id: `e-${Date.now()}`, role: 'assistant', content, timestamp: new Date().toISOString() }]);
    } finally { setIsLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, conversationId, user?.user_id]);

  const retryTimedOutMessage = useCallback(() => {
    if (!retryPrompt || isLoading) return;
    void sendMessage(retryPrompt);
  }, [retryPrompt, isLoading, sendMessage]);

  const loadFavorites = useCallback(async () => {
    if (!conversationId) {
      setFavoriteItems([]);
      setFavoriteMessageIds([]);
      return;
    }
    if (curationLoaded) return;
    try {
      const res = await api.get(`/support/chat/messages/favorites?conversation_id=${encodeURIComponent(conversationId)}`, {
        timeout: 10000,
        silentLoading: true,
      });
      const items = Array.isArray(res?.data?.favorites) ? res.data.favorites : [];
      setFavoriteItems(items);
      setFavoriteMessageIds(items.map((item: FavoriteItem) => item.message_id).filter(Boolean));
    } catch {
      setFavoriteItems([]);
      setFavoriteMessageIds([]);
    } finally {
      setCurationLoaded(true);
    }
  }, [conversationId, curationLoaded]);

  const loadPins = useCallback(async () => {
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
  }, [conversationId, curationLoaded]);

  const toggleFavoriteMessage = useCallback(async (message: ChatMessage) => {
    if (!conversationId || !message?.message_id) return;
    try {
      if (favoriteMessageIds.includes(message.message_id)) {
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

  const handleAttachment = useCallback(async () => {
    if (Platform.OS !== 'web') return;
    fileInputRef.current?.click();
  }, []);

  const onFileSelected = useCallback(async (e: any) => {
    const file = e?.target?.files?.[0];
    if (!file) return;
    const allowed = [
      'image/png',
      'image/jpeg',
      'image/webp',
      'image/gif',
      'application/pdf',
      'text/plain',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ];
    if (!allowed.includes(file.type)) {
      window.alert(t('help.upload.supportedFiles') || 'Please upload PNG, JPEG, WebP, GIF, PDF, TXT, or DOCX files.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) { window.alert('File too large. Max 10MB.'); return; }
    setAttachmentPreview({ name: file.name, type: file.type, uri: URL.createObjectURL(file) });
    setIsLoading(true);
    const userMsg = inputText.trim() || `Sent attachment: ${file.name}`;
    setMessages(prev => [...prev, { id: `u-${Date.now()}`, role: 'user', content: userMsg, timestamp: new Date().toISOString(), attachment: { url: URL.createObjectURL(file), filename: file.name, content_type: file.type } }]);
    setInputText('');
    setAttachmentPreview(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('conversation_id', conversationId || '');
      fd.append('message', userMsg);
      const res = await api.post('/support/chat/attachment', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (!conversationId) setConversationId(res.data.conversation_id);
      setMessages(prev => [...prev, {
        id: `a-${Date.now()}`,
        message_id: res.data?.assistant_message_id,
        role: 'assistant',
        content: res.data.message,
        timestamp: res.data.timestamp,
        gps_context: res.data?.gps_context,
      }]);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'help.chat.attachment-upload',
        error,
        message: t('help.errors.attachmentAnalysisFailed') || 'I received your file but had trouble analyzing it. Could you describe what you need help with?',
        onRetry: () => { if (e?.target?.files?.length) { void onFileChange(e as any); } },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setMessages(prev => [...prev, { id: `e-${Date.now()}`, role: 'assistant', content: "I received your file but had trouble analyzing it. Could you describe what you need help with?", timestamp: new Date().toISOString() }]);
    } finally { setIsLoading(false); if (e?.target) e.target.value = ''; }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, inputText, user]);

  const startRecording = useCallback(async () => {
    if (Platform.OS !== 'web') return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      audioChunksRef.current = [];
      recorder.ondataavailable = (e: any) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      setRecordingTime(0);
      recordingTimerRef.current = setInterval(() => setRecordingTime(t => t + 1), 1000);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'help.audio.start-recording',
        error,
        message: t('help.audio.accessDenied') || 'Microphone access denied. Please allow microphone access to use voice messages.',
        onRetry: () => { void startRecording(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopRecording = useCallback(async () => {
    if (!mediaRecorderRef.current) return;
    clearInterval(recordingTimerRef.current);
    return new Promise<void>((resolve) => {
      mediaRecorderRef.current.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        mediaRecorderRef.current.stream.getTracks().forEach((t: any) => t.stop());
        setIsRecording(false);
        setRecordingTime(0);
        if (blob.size < 100) { window.alert(t('help.audio.tooShort') || 'Recording too short.'); resolve(); return; }
        setIsLoading(true);
        setMessages(prev => [...prev, { id: `u-${Date.now()}`, role: 'user', content: 'Sent a voice message...', timestamp: new Date().toISOString() }]);
        try {
          const fd = new FormData();
          fd.append('audio', blob, 'recording.webm');
          fd.append('conversation_id', conversationId || '');
          const res = await api.post('/support/chat/audio', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
          if (!conversationId) setConversationId(res.data.conversation_id);
          if (res.data.transcription) {
            setMessages(prev => prev.map((m, i) => i === prev.length - 1 && m.role === 'user' ? { ...m, content: res.data.transcription, transcription: res.data.transcription } : m));
          }
          setMessages(prev => [...prev, {
            id: `a-${Date.now()}`,
            message_id: res.data?.assistant_message_id,
            role: 'assistant',
            content: res.data.message,
            timestamp: res.data.timestamp,
            gps_context: res.data?.gps_context,
          }]);
        } catch (error) {
          handleAppRecoverableError({
            scope: 'help.audio.process-recording',
            error,
            message: t('help.audio.processingFailed') || "I couldn't process the voice message. Please try typing your question instead.",
            onRetry: () => { void stopRecording(); },
          
        notifyMode: 'dialog',
        userInitiated: true,
      });
          setMessages(prev => [...prev, { id: `e-${Date.now()}`, role: 'assistant', content: t('help.audio.processingFailed') || "I couldn't process the voice message. Please try typing your question instead.", timestamp: new Date().toISOString() }]);
        } finally { setIsLoading(false); }
        resolve();
      };
      mediaRecorderRef.current.stop();
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, user]);

  const submitFeedback = useCallback(async () => {
    if (!feedbackRating || !conversationId) return;
    try {
      await api.post('/support/chat/feedback', {
        conversation_id: conversationId,
        rating: feedbackRating,
        comment: feedbackComment, helpful: feedbackRating >= 4,
      });
      setFeedbackSent(true);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'help.feedback.submit',
        error,
        message: t('help.feedback.submitFailed') || 'Could not submit feedback. Please try again.',
        onRetry: () => { void submitFeedback(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, [feedbackRating, feedbackComment, conversationId, t]);

  useEffect(() => {
    if (contactMode !== 'chat' || curationLoaded || !conversationId) return;
    void loadFavorites();
  }, [contactMode, conversationId, curationLoaded, loadFavorites]);

  useEffect(() => {
    if (contactMode !== 'chat' || curationLoaded || messages.length === 0) return;
    void loadPins();
  }, [contactMode, curationLoaded, loadPins, messages.length]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    try {
      const prefill = String(window.localStorage.getItem(NOVA_HUB_PREFILL_KEY) || '').trim();
      if (!prefill) return;
      window.localStorage.removeItem(NOVA_HUB_PREFILL_KEY);
      setActiveTab('contact');
      setContactMode('chat');
      setInputText(prefill.slice(0, 400));
    } catch (error) { handleAppRecoverableError({ scope: 'help.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const onNewChat = useCallback(() => {
    setMessages([]); setConversationId(null); setShowFeedback(false);
    setFeedbackSent(false); setFeedbackRating(0); setFeedbackComment('');
    setFavoriteItems([]); setFavoriteMessageIds([]); setConversationPinned(false);
    setCurationLoaded(false);
  }, []);

  const fetchSupportEmailInsights = useCallback(async () => {
    try {
      const email = (emailAddress || user?.email || '').trim();
      if (!email) return;
      const res = await api.get(`/support/email/insights?email=${encodeURIComponent(email)}`, { silentLoading: true });
      setEmailInsights(res?.data?.insights || null);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'help.support-email-insights',
        error,
        message: t('contact.errors.supportInsightsFailed', 'Could not load support insights right now.'),
        onRetry: () => { void fetchSupportEmailInsights(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setEmailInsights(null);
    }
  }, [emailAddress, t, user?.email]);

  useEffect(() => {
    if (contactMode !== 'email') return;
    if (!emailName && user?.name) setEmailName(user.name);
    if (!emailAddress && user?.email) setEmailAddress(user.email);
    void fetchSupportEmailInsights();
  }, [contactMode, emailName, emailAddress, user?.name, user?.email, fetchSupportEmailInsights]);

  const addEmailAttachments = useCallback((files: FileList | File[]) => {
    if (Platform.OS !== 'web') return;
    const incoming = Array.from(files || []);
    if (incoming.length === 0) return;
    const allowed = ['image/png', 'image/jpeg', 'image/webp', 'image/gif', 'application/pdf', 'text/plain', 'text/csv', 'application/json'];
    const next: SupportAttachmentDraft[] = [];
    for (const file of incoming) {
      if (!allowed.includes(file.type)) {
        window.alert(t('help.upload.supportedFiles') || 'Unsupported file type. Use PNG, JPEG, WebP, GIF, PDF, TXT, CSV, or JSON.');
        continue;
      }
      if (file.size > 5 * 1024 * 1024) {
        window.alert('Each attachment must be 5MB or smaller.');
        continue;
      }
      next.push({ id: `att-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, name: file.name, type: file.type, size: file.size, file });
    }
    setEmailAttachments(prev => {
      const merged = [...prev, ...next].slice(0, 3);
      if (prev.length + next.length > 3) {
        window.alert('Maximum 3 attachments per request.');
      }
      return merged;
    });
  }, [t]);

  const removeEmailAttachment = useCallback((id: string) => {
    setEmailAttachments(prev => prev.filter(att => att.id !== id));
  }, []);

  const requestAiSupportSuggestion = useCallback(async (intent: 'draft' | 'improve_tone' | 'shorten' | 'expand' = 'draft') => {
    if (!emailMessage.trim()) {
      if (Platform.OS === 'web') {
        window.alert('Please write a short issue summary before requesting AI suggestion.');
      } else {
        Alert.alert('Missing details', 'Please write a short issue summary before requesting AI suggestion.');
      }
      return;
    }
    setEmailSuggesting(true);
    try {
      const payload = {
        name: emailName || user?.name || '',
        email: emailAddress || user?.email || '',
        subject: emailSubject,
        message: emailMessage,
        category: emailCategory,
        priority: emailPriority,
        intent,
        lang: languageCode,
      };
      const res = await api.post('/support/email/assist', payload, { silentLoading: true });
      const suggestion = res?.data?.suggestion;
      if (suggestion) {
        setEmailSubject(suggestion.subject || emailSubject);
        setEmailMessage(suggestion.message || emailMessage);
        setEmailCategory((suggestion.category || emailCategory) as SupportCategory);
        setEmailPriority((suggestion.priority || emailPriority) as SupportPriority);
        setAiSuggestion(suggestion);
      }
      setDuplicateHints(Array.isArray(res?.data?.duplicate_hints) ? res.data.duplicate_hints : []);
      setFaqHints(Array.isArray(res?.data?.faq_hints) ? res.data.faq_hints : []);
      if (res?.data?.insights) setEmailInsights(res.data.insights);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'help.ai-support-suggestion',
        error,
        message: t('contact.errors.aiSuggestionUnavailable', 'AI suggestion is temporarily unavailable. You can still submit your request manually.'),
        onRetry: () => { void requestAiSupportSuggestion(intent); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    } finally {
      setEmailSuggesting(false);
    }
  }, [emailMessage, emailName, user?.name, emailAddress, user?.email, emailSubject, emailCategory, emailPriority, languageCode, t]);

  const reuseLastTicketContext = useCallback(async () => {
    setReuseLastContextLoading(true);
    try {
      const res = await api.get('/support/latest-context', { silentLoading: true });
      const context = res?.data?.context;
      if (!context) {
        setReuseLastContextMessage('No resolved tickets found yet. Submit this one and we’ll learn from it.');
        return;
      }

      if (context.subject) setEmailSubject(context.subject);
      if (context.message) setEmailMessage(context.message);
      if (context.category) setEmailCategory(context.category as SupportCategory);
      if (context.priority) setEmailPriority(context.priority as SupportPriority);
      setReuseLastContextMessage(`Prefilled from ${context.ticket_id || 'your last resolved ticket'}.`);
    } catch (error: any) {
      const detail = String(error?.response?.data?.detail || '').toLowerCase();
      if (detail.includes('not authenticated')) {
        setReuseLastContextMessage('Please sign in to reuse previous ticket context.');
      } else {
        setReuseLastContextMessage('Could not load previous ticket context right now.');
      }
    } finally {
      setReuseLastContextLoading(false);
    }
  }, []);

  const handleSubmitEmail = async () => {
    if (!emailName.trim() || !emailAddress.trim() || !emailMessage.trim()) {
      if (Platform.OS === 'web') {
        window.alert(t('help.email.fillRequired') || 'Please fill in all required fields.');
      } else {
        Alert.alert(t('help.email.missingTitle') || 'Missing Fields', t('help.email.fillRequired') || 'Please fill in all required fields.');
      }
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailAddress)) {
      if (Platform.OS === 'web') {
        window.alert(t('help.email.invalidAddress') || 'Please enter a valid email address.');
      } else {
        Alert.alert(t('help.email.invalidTitle') || 'Invalid Email', t('help.email.invalidAddress') || 'Please enter a valid email address.');
      }
      return;
    }
    setEmailSending(true); setEmailSuccess(null);
    try {
      const formData = new FormData();
      formData.append('name', emailName.trim());
      formData.append('email', emailAddress.trim());
      formData.append('subject', (emailSubject || 'Support Request').trim());
      formData.append('message', emailMessage.trim());
      formData.append('category', emailCategory);
      formData.append('priority', emailPriority);
      formData.append('ai_suggested', aiSuggestion ? 'true' : 'false');
      if (aiSuggestion?.confidence !== undefined) {
        formData.append('ai_confidence', String(aiSuggestion.confidence));
      }
      formData.append('suggestion_intent', aiSuggestion?.intent || 'draft');
      if (Platform.OS === 'web') {
        emailAttachments.forEach((att) => {
          if (att.file) formData.append('attachments', att.file);
        });
      }

      const res = await api.post('/support/email/submit', formData);
      if (res.data.success) {
        setEmailSuccess(res.data.ticket_id || '');
        setEmailName(user?.name || '');
        setEmailAddress(user?.email || '');
        setEmailSubject('');
        setEmailMessage('');
        setEmailCategory('general');
        setEmailPriority('medium');
        setEmailAttachments([]);
        setAiSuggestion(null);
        setDuplicateHints([]);
        setFaqHints([]);
        await fetchSupportEmailInsights();
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'help.submit-email',
        error,
        message: t('help.email.sendFailed') || 'Could not send your message.',
        onRetry: () => { void handleSubmitEmail(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      if (Platform.OS === 'web') {
        window.alert(t('help.email.sendFailed') || 'Could not send your message.');
      } else {
        Alert.alert(t('common.error') || 'Error', t('help.email.sendFailedLater') || 'Could not send. Try again later.');
      }
    }
    finally { setEmailSending(false); }
  };

  // ─── Tab Config ───
  const TABS = [
    { key: 'support' as const, icon: 'home', label: 'Support' },
    { key: 'faq' as const, icon: 'help-circle', label: 'FAQ' },
    { key: 'features' as const, icon: 'apps', label: 'Features' },
    { key: 'contact' as const, icon: 'chatbubbles', label: 'Contact', badge: '24/7' },
  ];

  const renderTabButton = (tab: typeof TABS[number], compact = false) => (
    <TouchableOpacity
      key={tab.key}
      data-testid={`tab-${tab.key}`}
      testID={`tab-${tab.key}`}
      style={[
        s.tab,
        compact ? s.tabCompact : s.tabWide,
        {
          backgroundColor: activeTab === tab.key ? (globalThis as any).__alphaColor(C.primary, '12') : C.bgSoft,
          borderWidth: 1,
          borderColor: activeTab === tab.key ? (globalThis as any).__alphaColor(C.primary, '45') : C.border,
        },
      ]}
      onPress={() => setActiveTab(tab.key)}
    >
      <Ionicons name={tab.icon as any} size={compact ? 13 : !isWide ? 14 : 16} color={activeTab === tab.key ? C.primary : C.textMuted} />
      <Text numberOfLines={1} style={{ fontSize: compact ? 11 : !isWide ? 10 : 12, fontWeight: activeTab === tab.key ? '700' : '600', color: activeTab === tab.key ? C.primary : C.textMuted }}>
        {tab.label}
      </Text>
      {tab.badge && isWide && <View style={[s.tabBadge, { backgroundColor: C.success }]}><Text style={{ fontSize: 8, fontWeight: '800', color: colors.primaryText }}>{tab.badge}</Text></View>}
    </TouchableOpacity>
  );

  // ─── Contact Tab Renderer ───
  const renderContactTab = () => (
    <View style={{ flex: 1, minHeight: 0, backgroundColor: C.bg }} data-testid="help-contact-surface" testID="help-contact-surface">
      <View style={[s.contactToggle, isUltraCompact && s.contactToggleCompact, { borderBottomColor: C.border, backgroundColor: C.card }]}> 
        <TouchableOpacity data-testid="contact-mode-chat" testID="contact-mode-chat" style={[s.contactToggleBtn, isUltraCompact && s.contactToggleBtnCompact, { borderColor: contactMode === 'chat' ? (globalThis as any).__alphaColor(C.primary, '45') : C.border, backgroundColor: contactMode === 'chat' ? (globalThis as any).__alphaColor(C.primary, '12') : C.bgSoft }]} onPress={() => setContactMode('chat')}>
          <Ionicons name="chatbubbles" size={16} color={contactMode === 'chat' ? C.primary : C.textMuted} />
          <Text style={{ fontSize: isUltraCompact ? 12 : 13, fontWeight: contactMode === 'chat' ? '700' : '500', color: contactMode === 'chat' ? C.primary : C.textMuted }}>{t("feature.tabs.chat")}</Text>
          {!isUltraCompact ? <View style={[s.liveBadge, { backgroundColor: C.success }]}><Text style={{ fontSize: 8, fontWeight: '800', color: colors.primaryText }}>LIVE</Text></View> : null}
        </TouchableOpacity>
        <TouchableOpacity data-testid="contact-mode-email" testID="contact-mode-email" style={[s.contactToggleBtn, isUltraCompact && s.contactToggleBtnCompact, { borderColor: contactMode === 'email' ? (globalThis as any).__alphaColor(C.primary, '45') : C.border, backgroundColor: contactMode === 'email' ? (globalThis as any).__alphaColor(C.primary, '12') : C.bgSoft }]} onPress={() => setContactMode('email')}>
          <Ionicons name="mail" size={16} color={contactMode === 'email' ? C.primary : C.textMuted} />
          <Text style={{ fontSize: isUltraCompact ? 12 : 13, fontWeight: contactMode === 'email' ? '700' : '500', color: contactMode === 'email' ? C.primary : C.textMuted }}>{t("auth.email")}</Text>
        </TouchableOpacity>
      </View>

      {contactMode === 'chat' ? (
        <View style={{ flex: 1, minHeight: 0 }} data-testid="help-contact-chat-layout" testID="help-contact-chat-layout">
          <NovaSurfaceShell
            colors={{ card: C.card, bgSoft: C.bgSoft, border: C.border, text: C.text, textMuted: C.textMuted }}
            shellTestId="help-nova-surface-shell"
            headerTestId="help-nova-surface-header"
            titleTestId="help-nova-surface-title"
            avatarWrapTestId="help-nova-avatar-frame"
            avatarImageTestId="help-nova-avatar-image"
            metaTestId="help-nova-surface-meta"
            title="Nova"
            shellStyle={{ borderWidth: 0, borderRadius: 0 }}
            headerStyle={{ paddingHorizontal: 16, paddingVertical: 12 }}
            headerMeta={<View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 1 }}><View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success }} /><Text style={{ fontSize: 11, color: colors.successText, fontWeight: '600' }}>Available 24/7</Text></View>}
            headerActions={messages.length > 0 ? (
              <>
                <TouchableOpacity
                  data-testid="chat-conversation-pin-toggle"
                  testID="chat-conversation-pin-toggle"
                  style={{ width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center', borderWidth: 1, backgroundColor: C.bgSoft, borderColor: C.border }}
                  onPress={togglePinConversation}
                  disabled={!conversationId}
                >
                  <Ionicons name={conversationPinned ? 'bookmark' : 'bookmark-outline'} size={16} color={conversationPinned ? colors.warningText : C.primary} />
                </TouchableOpacity>
                <TouchableOpacity data-testid="chat-new-btn" testID="chat-new-btn" style={{ width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center', borderWidth: 1, backgroundColor: C.bgSoft, borderColor: C.border }} onPress={onNewChat}>
                  <Ionicons name="add" size={18} color={C.primary} />
                </TouchableOpacity>
              </>
            ) : null}
            bodyTestId="help-nova-surface-body"
            body={(
              <NovaChatPanel
                C={C} t={t} messages={messages} inputText={inputText} setInputText={setInputText}
                isLoading={isLoading} isRecording={isRecording} recordingTime={recordingTime}
                showFeedback={showFeedback} setShowFeedback={setShowFeedback}
                feedbackRating={feedbackRating} setFeedbackRating={setFeedbackRating}
                feedbackComment={feedbackComment} setFeedbackComment={setFeedbackComment}
                feedbackSent={feedbackSent} attachmentPreview={attachmentPreview} setAttachmentPreview={setAttachmentPreview}
                quickQuestions={quickQuestions}
                sendMessage={sendMessage} retryPrompt={retryPrompt} onRetryTimeout={retryTimedOutMessage}
                handleAttachment={handleAttachment} onFileSelected={onFileSelected}
                startRecording={startRecording} stopRecording={stopRecording} submitFeedback={submitFeedback}
                onNewChat={onNewChat} chatScrollRef={chatScrollRef} fileInputRef={fileInputRef}
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
            footerTestId="help-nova-quick-tools"
            footer={(
              <View style={{ gap: 8, display: isUltraCompact ? 'none' : 'flex' }}>
                <TouchableOpacity
                  onPress={() => router.push('/nova-curation-hub')}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: C.primary, backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 8, alignSelf: useCompactNovaFooter ? 'stretch' : 'flex-start' }}
                  data-testid="help-nova-open-curation-hub-button"
                  testID="help-nova-open-curation-hub-button"
                >
                  <Text style={{ color: C.primaryText || C.text, fontSize: 11, fontWeight: '800', textAlign: useCompactNovaFooter ? 'center' : 'left' }}>Open full Pinned & Favorites hub</Text>
                </TouchableOpacity>

                {useCompactNovaFooter ? (
                  <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="help-nova-mobile-summary-strip" testID="help-nova-mobile-summary-strip">
                    <View style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingHorizontal: 10, paddingVertical: 7 }} data-testid="help-nova-pinned-summary" testID="help-nova-pinned-summary">
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }} data-testid="help-nova-pinned-summary-title" testID="help-nova-pinned-summary-title">
                        Pinned {pinnedItems.length}
                      </Text>
                    </View>
                    <View style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingHorizontal: 10, paddingVertical: 7 }} data-testid="help-nova-favorites-summary" testID="help-nova-favorites-summary">
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }} data-testid="help-nova-favorites-summary-title" testID="help-nova-favorites-summary-title">
                        Favorites {favoriteItems.length}
                      </Text>
                    </View>
                  </View>
                ) : (
                  <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 8 }}>
                    <View style={{ flex: 1, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }} data-testid="help-nova-pinned-summary" testID="help-nova-pinned-summary">
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="help-nova-pinned-summary-title" testID="help-nova-pinned-summary-title">
                        Pinned conversations
                      </Text>
                      <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 6 }} data-testid="help-nova-pinned-summary-copy" testID="help-nova-pinned-summary-copy">
                        {pinnedItems.length > 0 ? `${pinnedItems.length} saved threads ready in your hub.` : 'No pinned conversations yet.'}
                      </Text>
                    </View>

                    <View style={{ flex: 1, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }} data-testid="help-nova-favorites-summary" testID="help-nova-favorites-summary">
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="help-nova-favorites-summary-title" testID="help-nova-favorites-summary-title">
                        Favorite answers
                      </Text>
                      <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 6 }} data-testid="help-nova-favorites-summary-copy" testID="help-nova-favorites-summary-copy">
                        {favoriteItems.length > 0 ? `${favoriteItems.length} saved replies available to reuse.` : 'No favorite answers yet.'}
                      </Text>
                    </View>
                  </View>
                )}
              </View>
            )}
          />
        </View>
      ) : (
        <EmailFormEnterprise
          C={C} isWide={isWide} L={L}
          emailName={emailName} setEmailName={setEmailName}
          emailAddress={emailAddress} setEmailAddress={setEmailAddress}
          emailSubject={emailSubject} setEmailSubject={setEmailSubject}
          emailMessage={emailMessage} setEmailMessage={setEmailMessage}
          emailCategory={emailCategory} setEmailCategory={setEmailCategory}
          emailPriority={emailPriority} setEmailPriority={setEmailPriority}
          emailAttachments={emailAttachments}
          addEmailAttachments={addEmailAttachments}
          removeEmailAttachment={removeEmailAttachment}
          emailSending={emailSending} emailSuccess={emailSuccess} setEmailSuccess={setEmailSuccess}
          emailSuggesting={emailSuggesting}
          emailInsights={emailInsights}
          aiSuggestion={aiSuggestion}
          duplicateHints={duplicateHints}
          faqHints={faqHints}
          requestAiSupportSuggestion={requestAiSupportSuggestion}
          onReuseLastContext={reuseLastTicketContext}
          reuseLastContextLoading={reuseLastContextLoading}
          reuseLastContextAvailable={Boolean(user)}
          reuseLastContextMessage={reuseLastContextMessage}
          reuseLastContextHint="Prefill from your most recent resolved ticket."
          setContactMode={setContactMode} handleSubmitEmail={handleSubmitEmail}
        />
      )}
    </View>
  );

  if (!pageReady) return <HelpSkeleton />;
  if (gpsLoading && !gpsError) {
    return (
      <AppShell>
        <View style={{ flex: 1, backgroundColor: C.bg, paddingHorizontal: 16, paddingTop: 20 }}>
          <GpsDataStatusCard
            surfaceName="help"
            loading={gpsLoading}
            error={gpsError}
            onRetry={() => void gpsRefetch()}
            colors={{
              bg: C.bg,
              card: C.card,
              text: C.text,
              textSec: C.textSec,
              textMuted: C.textMuted,
              border: C.border,
              borderSoft: C.border,
              primary: C.primary,
              error: C.error,
              success: C.success,
              warning: C.warning,
            }}
            diagnostics={gpsDiagnostics}
            testIdPrefix="help"
          />
        </View>
      </AppShell>
    );
  }
  if (missingHelpLabels.length > 0 && !gpsError && gpsDiagnostics?.mode === 'live') {
    return <GpsLabelBlocker surfaceName="help" missingKeys={missingHelpLabels} colors={C} />;
  }
  if (loading || !user) return <HelpSkeleton />;
  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
        {gpsError ? (
          <View
            style={{ paddingHorizontal: 16, paddingTop: 12 }}
            data-testid="help-inline-gps-status-wrapper"
            testID="help-inline-gps-status-wrapper"
          >
            <GpsDataStatusCard
              surfaceName="help"
              loading={false}
              error={gpsError}
              onRetry={() => void gpsRefetch()}
              colors={{
                bg: C.bg,
                card: C.card,
                text: C.text,
                textSec: C.textSec,
                textMuted: C.textMuted,
                border: C.border,
                borderSoft: C.border,
                primary: C.primary,
                error: C.error,
                success: C.success,
                warning: C.warning,
              }}
              diagnostics={gpsDiagnostics}
              testIdPrefix="help"
            />
          </View>
        ) : null}

        {/* Header */}
        <View style={[s.header, { backgroundColor: C.card, borderBottomColor: C.border }]} data-testid="help-header" testID="help-header">
          <TouchableOpacity data-testid="help-back-btn" testID="help-back-btn" style={[s.backBtn, { backgroundColor: C.bgSoft }]} onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={22} color={C.text} />
          </TouchableOpacity>
          <Text style={[s.headerTitle, { color: C.text, fontSize: isWide ? 20 : 18 }]}>{t('help.title')}</Text>
          <View style={{ width: 40 }} />
        </View>

        {/* Tabs */}
        <View style={[s.tabs, isUltraCompact && s.tabsCompact, { borderBottomColor: C.border, backgroundColor: C.card }]} data-testid="help-tabs" testID="help-tabs">
          {isUltraCompact ? (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={s.tabsCompactScrollContent}
              data-testid="help-tabs-scroll"
              testID="help-tabs-scroll"
            >
              {TABS.map((tab) => renderTabButton(tab, true))}
            </ScrollView>
          ) : (
            TABS.map((tab) => renderTabButton(tab))
          )}
        </View>

        {/* Content */}
        <View style={{ flex: 1, minHeight: 0 }}>
          {activeTab === 'support' && (
            <SupportHeroTab C={C} darkMode={darkMode} isWide={isWide} L={L}
              searchQuery={searchQuery} setSearchQuery={setSearchQuery}
              setActiveTab={setActiveTab} setActiveCategory={setActiveCategory} openNovaChat={openNovaChat} openSupportEmail={openSupportEmail} />
          )}
          {activeTab === 'faq' && (
            <FAQSection C={C} darkMode={darkMode} L={L}
              searchQuery={searchQuery} setSearchQuery={setSearchQuery}
              activeCategory={activeCategory} setActiveCategory={setActiveCategory}
              faqs={faqs} faqLoading={faqLoading} expandedFAQ={expandedFAQ} setExpandedFAQ={setExpandedFAQ}
              faqVotes={faqVotes} voteFaq={voteFaq} filteredFAQs={filteredFAQs} setActiveTab={setActiveTab}
              languageCode={languageCode} />
          )}
          {activeTab === 'features' && (
            <FeatureIndexTab C={C} darkMode={darkMode} isWide={isWide} isTablet={isTablet}
              featureSearch={featureSearch} setFeatureSearch={setFeatureSearch}
              featureCat={featureCat} setFeatureCat={setFeatureCat}
              filteredFeatures={filteredFeatures} onFeaturePress={(route) => router.push(route as any)} />
          )}
          {activeTab === 'contact' && renderContactTab()}
        </View>
      </SafeAreaView>
    </AppShell>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1 },
  backBtn: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: 17, fontWeight: '700', letterSpacing: -0.3 },
  tabs: { flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 10, gap: 8, borderBottomWidth: 1 },
  tabsCompact: { paddingHorizontal: 8, paddingVertical: 8 },
  tabsCompactScrollContent: { gap: 8, paddingHorizontal: 4 },
  tab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: 10, gap: 6 },
  tabWide: { flex: 1 },
  tabCompact: { minWidth: 86, paddingHorizontal: 12 },
  tabBadge: { paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  contactToggle: { flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 10, gap: 10, borderBottomWidth: 1 },
  contactToggleCompact: { flexDirection: 'column', paddingHorizontal: 12, gap: 8, paddingVertical: 8 },
  contactToggleBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: 10, gap: 7, borderWidth: 1 },
  contactToggleBtnCompact: { flex: 0, width: '100%' },
  liveBadge: { paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
});
