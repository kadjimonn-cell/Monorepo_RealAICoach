import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  TextInput,
  ScrollView,
  useWindowDimensions,
  Animated,
  Easing,
  Pressable,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { reportClientCrash } from '../../services/clientErrorReporter';
import { NOVA_INTRO_FALLBACK } from '../../constants/novaPersona';
import { NovaAvatarBadge } from '../common/NovaIdentityBadge';
import NovaChatPanel from '../help/NovaChatPanel';
import type { ChatMessage } from '../help/helpTypes';
import { NovaSurfaceShell } from '../nova/NovaSurfaceShell';
import { useTheme } from '../../context/ThemeContext';

type NovaMessage = {
  id: string;
  message_id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  transcription?: string;
  attachment?: { url: string; filename: string; content_type: string };
  gps_context?: {
    gps_source?: string;
    gps_live?: boolean;
    gps_version?: number;
    gps_updated_at?: string;
    gps_freshness_sec?: number | null;
    gps_counts?: { features?: number; plans?: number; faq?: number; knowledge_docs?: number };
    gps_failed_checks?: string[];
  };
  feedback_submitted?: boolean;
};

type FavoriteItem = { message_id: string; conversation_id: string; content: string; updated_at?: string };
type PinItem = { conversation_id: string; preview?: string; updated_at?: string };

interface Props {
  colors: any;
  userId?: string;
  responsiveWidth?: number;
  featureCount: number;
  planCount: number;
  quickPrompts?: string[];
  labels: {
    fabTemplate: string;
    panelTitle: string;
    panelSubtitle: string;
    inputPlaceholder: string;
    sendLabel: string;
    closeLabel: string;
    welcomeMessage: string;
    unauthorizedError: string;
    genericError: string;
    contextSummaryTemplate: string;
    launcherAriaLabel: string;
    searchPrefill: string;
    contextTitle: string;
    loadingLabel: string;
    searchAccessibilityLabel: string;
    closeAccessibilityLabel: string;
    sendAccessibilityLabel: string;
    enterpriseIntro?: string;
    compactLatestReply?: string;
    compactExpandCta?: string;
    compactCollapse?: string;
    compactEmpty?: string;
  };
  stackAboveTourButton?: boolean;
}

export default function HomeNovaAssistantWidget({ colors, userId: _userId, responsiveWidth, featureCount, planCount, quickPrompts = [], labels, stackAboveTourButton = false }: Props) {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const { darkMode } = useTheme();
  const contentWidth = responsiveWidth || width;
  const isMobile = contentWidth < 768;
  const isPhone = contentWidth < 480;
  const isTablet = contentWidth >= 480 && contentWidth < 1024;
  const isShortViewport = height < 880;
  const useCompactDesktopLauncher = Platform.OS === 'web' && !isMobile && (contentWidth < 1760 || isShortViewport);
  const useDenseDesktopPanelChrome = !isMobile && (contentWidth < 1360 || height < 920);
  const [isOpen, setIsOpen] = useState(false);
  const [panelMode, setPanelMode] = useState<'compact' | 'expanded'>('compact');
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [attachmentPreview, setAttachmentPreview] = useState<{ name: string; type: string; uri: string } | null>(null);
  const [feedbackTargetMessageId, setFeedbackTargetMessageId] = useState<string | null>(null);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [favoriteMessageIds, setFavoriteMessageIds] = useState<string[]>([]);
  const [favoriteItems, setFavoriteItems] = useState<FavoriteItem[]>([]);
  const [conversationPinned, setConversationPinned] = useState(false);
  const [pinnedItems, setPinnedItems] = useState<PinItem[]>([]);
  const [retryPrompt, setRetryPrompt] = useState<string | null>(null);
  const [novaHealth, setNovaHealth] = useState<'checking' | 'healthy' | 'degraded'>('checking');
  const [curationLoaded, setCurationLoaded] = useState(false);
  const [messages, setMessages] = useState<NovaMessage[]>([
    { id: 'nova-welcome', role: 'assistant', content: labels.welcomeMessage, timestamp: new Date().toISOString() },
  ]);
  const [conversationId] = useState(`home-nova-${Date.now().toString(36)}`);
  const scrollRef = useRef<ScrollView>(null);
  const inputRef = useRef<TextInput>(null);
  const fileInputRef = useRef<any>(null);
  const mediaRecorderRef = useRef<any>(null);
  const audioChunksRef = useRef<any[]>([]);
  const recordingTimerRef = useRef<any>(null);
  const panelAnim = useRef(new Animated.Value(0)).current;
  const bubblePosition = useRef(new Animated.ValueXY({ x: 0, y: 0 })).current;
  const bubbleHintScale = useRef(new Animated.Value(1)).current;
  const bubbleHintPlayedRef = useRef(false);
  const bubbleDragRef = useRef({
    active: false,
    moved: false,
    pointerStartX: 0,
    pointerStartY: 0,
    bubbleStartX: 0,
    bubbleStartY: 0,
  });
  const [isDraggingBubble, setIsDraggingBubble] = useState(false);
  const launcherSize = isPhone ? 52 : isTablet ? 58 : 64;
  const launcherWide = Platform.OS === 'web' && !isMobile && !useCompactDesktopLauncher;
  const launcherShellWidth = launcherWide ? 188 : launcherSize;
  const launcherShellHeight = launcherSize;
  const launcherRight = isPhone ? 18 : isMobile ? 22 : useCompactDesktopLauncher ? 18 : 28;
  const safeAreaBottomInset = Math.max(0, Number(insets?.bottom || 0));
  const baseLauncherBottom = isPhone ? 14 : isMobile ? 18 : useCompactDesktopLauncher ? 22 : 88;
  const launcherBottom = Math.max(baseLauncherBottom, stackAboveTourButton ? 82 : 0) + safeAreaBottomInset;
  const panelBottom = (isPhone ? 10 : isMobile ? 14 : 24) + safeAreaBottomInset;
  const dragPadding = isPhone ? 10 : 14;
  const panelWidth = isPhone ? width - 24 : Math.min(Math.max(width - 48, 336), isTablet ? 420 : useDenseDesktopPanelChrome ? 410 : 440);
  const panelHeight = (() => {
    const available = Math.max(340, height - (isPhone ? 28 : isMobile ? 34 : useDenseDesktopPanelChrome ? 120 : 150));
    const preferred = isPhone ? 540 : isTablet ? 600 : useDenseDesktopPanelChrome ? 600 : 660;
    const minimum = isPhone ? 420 : isTablet ? 480 : 520;
    return Math.max(Math.min(minimum, available), Math.min(preferred, available));
  })();
  const nova = {
    ink: colors.text,
    muted: colors.textMuted || colors.textSec,
    line: colors.border,
    surface: colors.card,
    soft: colors.bgSoft,
    bubble: colors.info || colors.primary,
    bubbleText: colors.primaryText,
    success: colors.successText || colors.success || colors.primary,
  };

  useEffect(() => {
    Animated.timing(panelAnim, {
      toValue: isOpen ? 1 : 0,
      duration: 220,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [isOpen, panelAnim]);

  useEffect(() => {
    setMessages([{ id: 'nova-welcome', role: 'assistant', content: labels.welcomeMessage, timestamp: new Date().toISOString() }]);
  }, [labels.welcomeMessage]);

  const scrollMessagesToLatest = useCallback((animated = true) => {
    if (!scrollRef.current) return;
    requestAnimationFrame(() => {
      setTimeout(() => {
        scrollRef.current?.scrollToEnd({ animated });
      }, animated ? 120 : 40);
    });
  }, []);

  useEffect(() => {
    return () => {
      if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
      if (Platform.OS === 'web' && typeof window !== 'undefined' && (window as any).speechSynthesis) {
        (window as any).speechSynthesis.cancel();
      }
    };
  }, []);

  const pollNovaHealth = useCallback(async () => {
    try {
      const res = await api.get('/support/nova/health?hours=1', { timeout: 10000, silentLoading: true });
      const status = String(res?.data?.status || '').toLowerCase();
      setNovaHealth(status === 'healthy' ? 'healthy' : 'degraded');
    } catch {
      setNovaHealth('degraded');
    }
  }, []);

  const clampBubblePosition = useCallback((x: number, y: number) => {
    const minX = dragPadding;
    const maxX = Math.max(minX, width - launcherShellWidth - dragPadding);
    const minY = dragPadding;
    const maxY = Math.max(minY, height - launcherShellHeight - dragPadding);
    return {
      x: Math.max(minX, Math.min(maxX, x)),
      y: Math.max(minY, Math.min(maxY, y)),
    };
  }, [dragPadding, height, launcherShellHeight, launcherShellWidth, width]);

  const getDefaultBubblePosition = useCallback(() => {
    const defaultX = width - launcherShellWidth - launcherRight;
    const defaultY = height - launcherShellHeight - launcherBottom;
    return clampBubblePosition(defaultX, defaultY);
  }, [clampBubblePosition, width, height, launcherShellWidth, launcherRight, launcherBottom, launcherShellHeight]);

  useEffect(() => {
    bubblePosition.setValue(getDefaultBubblePosition());
  }, [bubblePosition, getDefaultBubblePosition]);

  useEffect(() => {
    if (bubbleHintPlayedRef.current) return;
    bubbleHintPlayedRef.current = true;

    const timer = setTimeout(() => {
      Animated.sequence([
        Animated.timing(bubbleHintScale, {
          toValue: 1.08,
          duration: 170,
          easing: Easing.out(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(bubbleHintScale, {
          toValue: 1,
          duration: 170,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ]).start();
    }, 900);

    return () => clearTimeout(timer);
  }, [bubbleHintScale]);

  const contextSummary = useMemo(
    () =>
      labels.contextSummaryTemplate
        .replace('{{features}}', String(featureCount))
        .replace('{{plans}}', String(planCount)),
    [labels.contextSummaryTemplate, featureCount, planCount],
  );
  const enterpriseIntro = (labels.enterpriseIntro || '').trim() || NOVA_INTRO_FALLBACK;
  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((msg) => msg.role === 'assistant') || null,
    [messages],
  );
  const hasLiveAssistantReply = useMemo(
    () => messages.some((msg) => msg.role === 'assistant' && !!msg.message_id),
    [messages],
  );
  const hasMeaningfulConversation = useMemo(
    () => messages.some((msg) => msg.role === 'user' || !!msg.message_id) || messages.length > 1,
    [messages],
  );
  const resolvedQuickPrompts = useMemo(() => quickPrompts.filter(Boolean).slice(0, 3), [quickPrompts]);
  const showCondensedFloatingSummary = useDenseDesktopPanelChrome || isTablet || isPhone;
  useEffect(() => {
    if (!isOpen) return;
    if (!hasMeaningfulConversation) return;
    scrollMessagesToLatest(messages.length > 2);
  }, [hasMeaningfulConversation, isOpen, messages.length, scrollMessagesToLatest]);

  const statusCards = useMemo(() => ([
    {
      id: 'health',
      label: 'Nova status',
      value: novaHealth === 'healthy' ? 'Live' : novaHealth === 'degraded' ? 'Needs review' : 'Checking',
      tone: novaHealth === 'healthy' ? colors.successText : novaHealth === 'degraded' ? colors.warningText : colors.primary,
    },
    {
      id: 'favorites',
      label: 'Favorites',
      value: String(favoriteItems.length),
      tone: colors.primary,
    },
    {
      id: 'pins',
      label: 'Pinned',
      value: String(pinnedItems.length),
      tone: colors.warningText,
    },
  ]), [colors.primary, colors.successText, colors.warningText, favoriteItems.length, novaHealth, pinnedItems.length]);

  const panelTheme = useMemo(() => ({
    primary: colors.primary,
    bg: colors.bg,
    bgSoft: colors.bgSoft,
    card: colors.card,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    violet: colors.purple,
  }), [colors]);

  const fakeTranslator = useCallback((key: string) => {
    const map: Record<string, string> = {
      'help.nova.welcome': labels.panelTitle,
      'help.nova.subtitle': labels.panelSubtitle,
      'help.nova.attachments': 'Attachments',
      'help.nova.voice': 'Voice',
      'help.nova.voiceMessage': 'Voice message',
      'help.nova.recording': 'Recording…',
      'help.nova.stopSend': 'Stop & send',
      'help.nova.placeholder': labels.inputPlaceholder,
      'help.feedback.title': 'Add optional feedback for the last response',
      'help.feedback.subtitle': 'Rate the response and share details if helpful.',
      'help.feedback.placeholder': 'Share details (optional)',
      'help.feedback.submit': feedbackSending ? 'Submitting…' : 'Submit',
      'help.feedback.thanks': 'Thanks for the feedback.',
      'help.chat.signInRequired': labels.unauthorizedError,
      'help.chat.timeout': 'Nova is taking longer than expected. Please try again in a moment.',
      'help.chat.connectionIssue': labels.genericError,
      'help.chat.stopAudio': 'Stop',
      'help.chat.playAudio': 'Play audio',
      'help.chat.retryHint': 'Nova timed out on your last request. You can retry safely.',
      'help.chat.retryAction': 'Retry',
      'help.chat.novaNeedsAttentionShort': 'Nova Degraded',
      'help.chat.novaHealthy': 'Nova Healthy',
      'help.chat.novaReady': 'Nova Ready',
      'help.chat.novaNeedsAttention': 'Nova needs attention right now.',
      'help.chat.novaLiveReplies': 'Live replies are responding in this session.',
      'help.chat.novaConversationPrompt': 'Health checks only service readiness. Send a message to confirm live replies.',
      'help.nova.enterpriseIntro': enterpriseIntro,
    };
    return map[key] || key;
  }, [enterpriseIntro, feedbackSending, labels.genericError, labels.inputPlaceholder, labels.panelSubtitle, labels.panelTitle, labels.unauthorizedError]);

  const panelMessages = useMemo<ChatMessage[]>(() => messages.map((msg) => ({
    id: msg.id,
    message_id: msg.message_id,
    role: msg.role,
    content: msg.content,
    timestamp: msg.timestamp || new Date().toISOString(),
    attachment: msg.attachment,
    transcription: msg.transcription,
    gps_context: msg.gps_context,
    feedback_submitted: msg.feedback_submitted,
  })), [messages]);

  const favoriteSnippets = useMemo(() => favoriteItems.map((item) => ({
    message_id: item.message_id,
    content: item.content,
  })), [favoriteItems]);

  const loadFavorites = useCallback(async () => {
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
      setConversationPinned(items.some((pin: PinItem) => pin.conversation_id === conversationId));
    } catch {
      setPinnedItems([]);
      setConversationPinned(false);
    } finally {
      setCurationLoaded(true);
    }
  }, [conversationId, curationLoaded]);

  useEffect(() => {
    if (!isOpen) return;
    void pollNovaHealth();
    const timer = setInterval(() => { void pollNovaHealth(); }, 60000);
    return () => clearInterval(timer);
  }, [isOpen, pollNovaHealth]);

  useEffect(() => {
    if (!isOpen || curationLoaded || messages.length <= 1) return;
    void loadFavorites();
    void loadPins();
  }, [curationLoaded, isOpen, loadFavorites, loadPins, messages.length]);

  const toggleFavoriteMessage = useCallback(async (message: NovaMessage) => {
    if (!message?.message_id) {
      setMessages((prev) => [...prev, {
        id: `fav-${Date.now()}`,
        role: 'assistant',
        content: 'This answer cannot be saved yet. Send a new response and try again.',
        timestamp: new Date().toISOString(),
      }]);
      return;
    }
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
      setMessages((prev) => [...prev, {
        id: `faverr-${Date.now()}`,
        role: 'assistant',
        content: 'Could not update favorites right now. Please retry.',
        timestamp: new Date().toISOString(),
      }]);
    }
  }, [conversationId, favoriteMessageIds, loadFavorites]);

  const togglePinConversation = useCallback(async () => {
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
      setMessages((prev) => [...prev, {
        id: `pinerr-${Date.now()}`,
        role: 'assistant',
        content: 'Start a conversation first, then pin it for quick access.',
        timestamp: new Date().toISOString(),
      }]);
    }
  }, [conversationId, conversationPinned, loadPins]);

  const send = async (overrideText?: string) => {
    const text = String(overrideText ?? input).trim();
    if (!text || sending) return;

    const userMsg: NovaMessage = { id: `u-${Date.now()}`, role: 'user', content: text, timestamp: new Date().toISOString() };
    setMessages((prev) => [...prev, userMsg]);
    if (!overrideText) setInput('');
    setSending(true);
    try {
      const response = await api.post('/support/chat', {
        message: text,
        conversation_id: conversationId,
      }, { timeout: 20000 });
      const candidate = response?.data?.message ?? response?.data?.response ?? response?.data?.data;
      let reply = '';
      if (typeof candidate === 'string') {
        reply = candidate.trim();
      } else if (candidate && typeof candidate === 'object') {
        reply = String((candidate as any).message || (candidate as any).text || (candidate as any).content || '').trim();
      }
      if (!reply) {
        reportClientCrash({
          panelId: 'home-nova-chat',
          panelName: 'Home Nova Assistant',
          message: `Nova empty payload fallback: conversation=${conversationId}`,
        });
      }
      if (!reply) reply = labels.genericError;
      setRetryPrompt(null);
      setFeedbackTargetMessageId(null);
      const assistantId = `a-${Date.now()}`;
      setMessages((prev) => [...prev, {
        id: assistantId,
        message_id: response?.data?.assistant_message_id,
        role: 'assistant',
        content: reply,
        timestamp: response?.data?.timestamp || new Date().toISOString(),
        gps_context: response?.data?.gps_context,
      }]);
      setFeedbackTargetMessageId(assistantId);
      setFeedbackComment('');
    } catch (error: any) {
      const status = Number(error?.status || error?.response?.status || 0);
      const backendCode = String(error?.response?.data?.code || error?.response?.data?.detail?.code || 'unknown');
      reportClientCrash({
        panelId: 'home-nova-chat',
        panelName: 'Home Nova Assistant',
        message: `Nova request failed: status=${status || 'unknown'} code=${backendCode} conversation=${conversationId}`,
        stack: String(error?.stack || ''),
      });
      const timeoutError = status === 408 || status === 504 || String(error?.message || '').toLowerCase().includes('timed out');
      if (timeoutError) {
        setRetryPrompt(text);
      } else {
        setRetryPrompt(null);
      }
      setFeedbackTargetMessageId(null);

      const message = status === 401
        ? labels.unauthorizedError
        : (timeoutError
          ? "Nova is taking longer than expected. Please try again in a moment."
          : labels.genericError);
      setMessages((prev) => [...prev, { id: `e-${Date.now()}`, role: 'assistant', content: message, timestamp: new Date().toISOString() }]);
    } finally {
      setSending(false);
    }
  };

  const submitFeedback = async (rating: number, comment: string) => {
    if (!feedbackTargetMessageId || feedbackSending) return;
    setFeedbackSending(true);
    try {
      await api.post('/support/chat/feedback', {
        conversation_id: conversationId,
        rating,
        comment,
        helpful: rating >= 4,
      });
      setMessages((prev) => prev.map((msg) => (
        msg.id === feedbackTargetMessageId ? { ...msg, feedback_submitted: true } : msg
      )));
      setFeedbackTargetMessageId(null);
      setFeedbackComment('');
    } catch {
      setMessages((prev) => [...prev, {
        id: `fb-${Date.now()}`,
        role: 'assistant',
        content: 'Feedback could not be submitted. Please try again.',
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setFeedbackSending(false);
    }
  };

  const handleAttachment = () => {
    if (Platform.OS !== 'web') return;
    fileInputRef.current?.click();
  };

  const onFileSelected = async (event: any) => {
    const file = event?.target?.files?.[0];
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
      window.alert('Use PNG, JPEG, WebP, GIF, PDF, TXT, or DOCX files.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      window.alert('File too large. Max 10MB.');
      return;
    }

    const userMsg = input.trim() || `Sent attachment: ${file.name}`;
    if (input.trim()) setInput('');
    setAttachmentPreview({ name: file.name, type: file.type, uri: URL.createObjectURL(file) });
    setMessages((prev) => [...prev, {
      id: `u-${Date.now()}`,
      role: 'user',
      content: userMsg,
      timestamp: new Date().toISOString(),
      attachment: { url: URL.createObjectURL(file), filename: file.name, content_type: file.type },
    }]);
    setSending(true);

    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('conversation_id', conversationId);
      fd.append('message', userMsg);
      const res = await api.post('/support/chat/attachment', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const assistantId = `a-${Date.now()}`;
      setMessages((prev) => [...prev, {
        id: assistantId,
        message_id: res.data?.assistant_message_id,
        role: 'assistant',
        content: res.data?.message || labels.genericError,
        timestamp: res.data?.timestamp || new Date().toISOString(),
        gps_context: res.data?.gps_context,
      }]);
      setFeedbackTargetMessageId(assistantId);
      setFeedbackComment('');
    } catch {
      setMessages((prev) => [...prev, {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: 'I received your file but had trouble analyzing it. Please try again.',
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setAttachmentPreview(null);
      setSending(false);
      if (event?.target) event.target.value = '';
    }
  };

  const startRecording = async () => {
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
      window.alert('Microphone permission was denied.');
    }
  };

  const stopRecording = async () => {
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

        setMessages((prev) => [...prev, {
          id: `u-${Date.now()}`,
          role: 'user',
          content: 'Sent a voice message...',
          timestamp: new Date().toISOString(),
        }]);
        setSending(true);
        try {
          const fd = new FormData();
          fd.append('audio', blob, 'recording.webm');
          fd.append('conversation_id', conversationId);
          const res = await api.post('/support/chat/audio', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
          const assistantId = `a-${Date.now()}`;
          setMessages((prev) => {
            const updated = [...prev];
            if (res.data?.transcription) {
              const last = updated[updated.length - 1];
              if (last && last.role === 'user') {
                last.content = res.data.transcription;
                last.transcription = res.data.transcription;
              }
            }
            updated.push({
              id: assistantId,
              message_id: res.data?.assistant_message_id,
              role: 'assistant',
              content: res.data?.message || labels.genericError,
              timestamp: res.data?.timestamp || new Date().toISOString(),
              gps_context: res.data?.gps_context,
            });
            return updated;
          });
          setFeedbackTargetMessageId(assistantId);
          setFeedbackComment('');
        } catch {
          setMessages((prev) => [...prev, {
            id: `e-${Date.now()}`,
            role: 'assistant',
            content: "I couldn't process your voice message. Please try typing instead.",
            timestamp: new Date().toISOString(),
          }]);
        } finally {
          setSending(false);
        }
        resolve();
      };
      mediaRecorderRef.current.stop();
    });
  };

  const panelTranslate = panelAnim.interpolate({ inputRange: [0, 1], outputRange: [32, 0] });
  const panelOpacity = panelAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 1] });

  const openSearch = () => {
    setIsOpen(true);
    setPanelMode('expanded');
    setInput((prev) => prev || labels.searchPrefill);
    if (hasMeaningfulConversation) scrollMessagesToLatest(false);
    setTimeout(() => inputRef.current?.focus(), 180);
  };

  const openChat = () => {
    setIsOpen(true);
    setPanelMode('compact');
  };

  const expandToConversation = (prompt?: string) => {
    setPanelMode('expanded');
    if (prompt) {
      void send(prompt);
      return;
    }
    if (hasMeaningfulConversation) scrollMessagesToLatest(false);
    setTimeout(() => inputRef.current?.focus(), 180);
  };

  const startBubbleDrag = (pageX: number, pageY: number) => {
    bubbleDragRef.current.active = true;
    bubbleDragRef.current.moved = false;
    bubbleDragRef.current.pointerStartX = pageX;
    bubbleDragRef.current.pointerStartY = pageY;
    setIsDraggingBubble(true);
    bubblePosition.stopAnimation((current) => {
      const currentPos = typeof current === 'number' ? { x: 0, y: 0 } : current;
      bubbleDragRef.current.bubbleStartX = currentPos.x;
      bubbleDragRef.current.bubbleStartY = currentPos.y;
    });

    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const onMouseMove = (event: MouseEvent) => {
        moveBubbleDrag(event.clientX, event.clientY);
      };

      const onMouseUp = () => {
        finishBubbleDrag();
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
      };

      const onTouchMove = (event: TouchEvent) => {
        const touch = event.touches?.[0];
        if (!touch) return;
        moveBubbleDrag(touch.clientX, touch.clientY);
        event.preventDefault();
      };

      const onTouchEnd = () => {
        finishBubbleDrag();
        window.removeEventListener('touchmove', onTouchMove);
        window.removeEventListener('touchend', onTouchEnd);
        window.removeEventListener('touchcancel', onTouchEnd);
      };

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
      window.addEventListener('touchmove', onTouchMove, { passive: false });
      window.addEventListener('touchend', onTouchEnd);
      window.addEventListener('touchcancel', onTouchEnd);
    }
  };

  const moveBubbleDrag = (pageX: number, pageY: number) => {
    if (!bubbleDragRef.current.active) return;
    const dx = pageX - bubbleDragRef.current.pointerStartX;
    const dy = pageY - bubbleDragRef.current.pointerStartY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      bubbleDragRef.current.moved = true;
    }
    const next = clampBubblePosition(
      bubbleDragRef.current.bubbleStartX + dx,
      bubbleDragRef.current.bubbleStartY + dy,
    );
    bubblePosition.setValue(next);
  };

  const finishBubbleDrag = () => {
    if (!bubbleDragRef.current.active) return;
    const wasMoved = bubbleDragRef.current.moved;
    bubbleDragRef.current.active = false;
    bubbleDragRef.current.moved = false;
    setIsDraggingBubble(false);

    if (!wasMoved) {
      openChat();
      return;
    }

    const anchor = getDefaultBubblePosition();
    bubblePosition.stopAnimation(() => {
      Animated.spring(bubblePosition, {
        toValue: anchor,
        useNativeDriver: false,
        tension: 150,
        friction: 12,
      }).start();
    });
  };

  const handleBubbleGrant = (event: any) => {
    const pageX = Number(event?.nativeEvent?.pageX || 0);
    const pageY = Number(event?.nativeEvent?.pageY || 0);
    startBubbleDrag(pageX, pageY);
  };

  const handleBubbleMove = (event: any) => {
    const pageX = Number(event?.nativeEvent?.pageX || 0);
    const pageY = Number(event?.nativeEvent?.pageY || 0);
    moveBubbleDrag(pageX, pageY);
  };

  const handleBubbleRelease = () => {
    finishBubbleDrag();
  };

  return (
    <>
      {!isOpen ? (
        <Animated.View
          data-testid="home-nova-widget-shell"
          testID="home-nova-widget-shell"
          style={{
            position: (Platform.OS === 'web' ? 'fixed' : 'absolute') as any,
            ...(Platform.OS === 'web'
              ? {
                  right: launcherRight,
                  bottom: launcherBottom,
                }
              : {
                  left: bubblePosition.x,
                  top: bubblePosition.y,
                }),
            width: launcherShellWidth,
            height: launcherSize,
            borderRadius: launcherWide ? 999 : launcherSize / 2,
            zIndex: 9993,
            shadowColor: nova.bubble,
            shadowOpacity: 0.34,
            shadowRadius: isPhone ? 16 : 22,
            shadowOffset: { width: 0, height: isPhone ? 8 : 12 },
            elevation: isPhone ? 12 : 16,
            transform: [{ scale: bubbleHintScale }],
            ...(Platform.OS === 'web'
              ? ({
                  touchAction: 'none',
                  cursor: isDraggingBubble ? 'grabbing' : 'grab',
                  userSelect: 'none',
                } as any)
              : null),
          }}
        >
          <Pressable
            data-testid="home-nova-fab-button"
            testID="home-nova-fab-button"
            accessibilityRole="button"
            accessibilityLabel={labels.launcherAriaLabel}
            onStartShouldSetResponder={() => Platform.OS !== 'web'}
            onMoveShouldSetResponder={() => Platform.OS !== 'web'}
            onResponderGrant={Platform.OS === 'web' ? undefined : handleBubbleGrant}
            onResponderMove={Platform.OS === 'web' ? undefined : handleBubbleMove}
            onResponderRelease={Platform.OS === 'web' ? undefined : handleBubbleRelease}
            onResponderTerminate={Platform.OS === 'web' ? undefined : handleBubbleRelease}
            onMouseDown={(event: any) => {
              if (Platform.OS !== 'web') return;
              event.preventDefault?.();
              startBubbleDrag(Number(event?.nativeEvent?.pageX || event?.pageX || event?.clientX || 0), Number(event?.nativeEvent?.pageY || event?.pageY || event?.clientY || 0));
            }}
            onTouchStart={(event: any) => {
              if (Platform.OS !== 'web') return;
              const touch = event?.nativeEvent?.touches?.[0] || event?.touches?.[0];
              if (!touch) return;
              startBubbleDrag(Number(touch.pageX || touch.clientX || 0), Number(touch.pageY || touch.clientY || 0));
            }}
            onKeyDown={(event: any) => {
              if (event?.key === 'Enter' || event?.key === ' ') {
                event.preventDefault?.();
                openChat();
              }
            }}
            style={{
              width: launcherShellWidth,
              height: launcherSize,
              borderRadius: launcherWide ? 999 : launcherSize / 2,
              backgroundColor: colors.card,
              alignItems: 'center',
              justifyContent: launcherWide ? 'space-between' : 'center',
              flexDirection: launcherWide ? 'row' : 'column',
              borderWidth: 2,
              borderColor: colors.error,
              overflow: 'hidden',
              paddingHorizontal: launcherWide ? 8 : 0,
              ...(Platform.OS === 'web'
                ? ({ cursor: isDraggingBubble ? 'grabbing' : 'grab' } as any)
                : null),
            }}
          >
            <NovaAvatarBadge
              size={launcherSize}
              ringColor={colors.error}
              surfaceColor={colors.card}
              animationPreset="interactive"
              showOnlineDot
              onlineDotColor={colors.successText || colors.success}
              wrapTestId="home-nova-fab-avatar-wrap"
              imageTestId="home-nova-fab-avatar-image"
              dotTestId="home-nova-fab-online-dot"
            />
            {launcherWide ? (
              <View style={{ flex: 1, minWidth: 0, paddingLeft: 10, paddingRight: 6 }} data-testid="home-nova-fab-label-wrap" testID="home-nova-fab-label-wrap">
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '900' }} numberOfLines={1} data-testid="home-nova-fab-title" testID="home-nova-fab-title">
                  {labels.panelTitle}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', marginTop: 2, textTransform: 'uppercase' }} numberOfLines={1} data-testid="home-nova-fab-subtitle" testID="home-nova-fab-subtitle">
                  {labels.panelSubtitle}
                </Text>
              </View>
            ) : null}
          </Pressable>
        </Animated.View>
      ) : null}

      {isOpen && panelMode === 'compact' ? (
        <Animated.View
          data-testid="home-nova-compact-panel"
          testID="home-nova-compact-panel"
          style={{
            position: (Platform.OS === 'web' ? 'fixed' : 'absolute') as any,
            right: isPhone ? 12 : isMobile ? 18 : 28,
            left: isPhone ? 12 : undefined,
            bottom: panelBottom,
            width: isMobile ? undefined : panelWidth,
            maxHeight: Math.min(430, height - 40),
            borderRadius: isPhone ? 18 : 20,
            backgroundColor: nova.surface,
            borderWidth: 1,
            borderColor: nova.line,
            overflow: 'hidden',
            zIndex: 9994,
            shadowColor: colors.text,
            shadowOpacity: 0.24,
            shadowRadius: 28,
            shadowOffset: { width: 0, height: 16 },
            elevation: 18,
            opacity: panelOpacity,
            transform: [{ translateY: panelTranslate }],
            padding: 14,
            gap: 10,
            ...(Platform.OS === 'web' && isPhone ? ({ maxWidth: 'calc(100vw - 24px)' } as any) : null),
          }}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }} data-testid="home-nova-compact-header" testID="home-nova-compact-header">
            <NovaAvatarBadge
              size={40}
              ringColor={colors.error}
              surfaceColor={colors.card}
              animationPreset="interactive"
              showOnlineDot
              onlineDotColor={colors.successText || colors.success}
              wrapTestId="home-nova-compact-avatar-wrap"
              imageTestId="home-nova-compact-avatar-image"
              dotTestId="home-nova-compact-online-dot"
            />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={{ color: nova.ink, fontSize: 14, fontWeight: '900' }} numberOfLines={1} data-testid="home-nova-compact-title" testID="home-nova-compact-title">{labels.panelTitle}</Text>
              <Text style={{ color: nova.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', marginTop: 2 }} numberOfLines={1}>{labels.panelSubtitle}</Text>
            </View>
            <TouchableOpacity
              onPress={() => expandToConversation()}
              data-testid="home-nova-expand-button"
              testID="home-nova-expand-button"
              accessibilityRole="button"
              accessibilityLabel={labels.compactExpandCta || 'Open full conversation'}
              style={{ width: 34, height: 34, borderRadius: 11, backgroundColor: nova.soft, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: nova.line }}
            >
              <Ionicons name="expand-outline" size={16} color={nova.ink} />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setIsOpen(false)}
              data-testid="home-nova-compact-close-button"
              testID="home-nova-compact-close-button"
              accessibilityRole="button"
              accessibilityLabel={labels.closeAccessibilityLabel}
              style={{ width: 34, height: 34, borderRadius: 11, backgroundColor: nova.soft, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: nova.line }}
            >
              <Ionicons name="chevron-down" size={16} color={nova.ink} />
            </TouchableOpacity>
          </View>

          <View style={{ borderRadius: 14, backgroundColor: nova.soft, borderWidth: 1, borderColor: nova.line, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="home-nova-compact-latest-reply" testID="home-nova-compact-latest-reply">
            <Text style={{ color: nova.muted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{labels.compactLatestReply || 'Latest reply'}</Text>
            <Text style={{ color: nova.ink, fontSize: 12, marginTop: 5, lineHeight: 17 }} numberOfLines={3}>
              {hasMeaningfulConversation && latestAssistantMessage?.content
                ? String(latestAssistantMessage.content)
                : (labels.compactEmpty || 'No conversation yet - pick a quick prompt to get started.')}
            </Text>
          </View>

          <View style={{ borderRadius: 14, backgroundColor: nova.soft, borderWidth: 1, borderColor: nova.line, paddingHorizontal: 12, paddingVertical: 9 }} data-testid="home-nova-compact-context" testID="home-nova-compact-context">
            <Text style={{ color: nova.ink, fontSize: 11, fontWeight: '900' }} numberOfLines={1}>{labels.contextTitle}</Text>
            <Text style={{ color: nova.muted, fontSize: 11, marginTop: 3 }} numberOfLines={1}>{contextSummary}</Text>
          </View>

          {resolvedQuickPrompts.length > 0 ? (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid="home-nova-compact-prompts" testID="home-nova-compact-prompts">
              {resolvedQuickPrompts.slice(0, 3).map((prompt, idx) => (
                <TouchableOpacity
                  key={prompt}
                  onPress={() => expandToConversation(prompt)}
                  data-testid={`home-nova-compact-prompt-${idx}`}
                  testID={`home-nova-compact-prompt-${idx}`}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}40`, backgroundColor: `${colors.primary}10`, paddingHorizontal: 11, paddingVertical: 7, maxWidth: '100%' }}
                >
                  <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>{prompt}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}

          <TouchableOpacity
            onPress={() => expandToConversation()}
            data-testid="home-nova-compact-open-conversation"
            testID="home-nova-compact-open-conversation"
            accessibilityRole="button"
            style={{ borderRadius: 12, backgroundColor: colors.primary, paddingVertical: 11, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 }}
          >
            <Ionicons name="chatbubbles-outline" size={15} color={colors.primaryText} />
            <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '900' }}>{labels.compactExpandCta || 'Open full conversation'}</Text>
          </TouchableOpacity>
        </Animated.View>
      ) : null}

      {isOpen && panelMode === 'expanded' ? (
        <Animated.View
          data-testid="home-nova-chat-panel"
          testID="home-nova-chat-panel"
          style={{
            position: (Platform.OS === 'web' ? 'fixed' : 'absolute') as any,
            right: isPhone ? 12 : isMobile ? 18 : 28,
            left: isPhone ? 12 : undefined,
            bottom: panelBottom,
            width: isMobile ? undefined : panelWidth,
            height: panelHeight,
            maxHeight: height - (isPhone ? 24 : 40),
            borderRadius: isPhone ? 18 : 22,
            backgroundColor: nova.surface,
            borderWidth: 1,
            borderColor: nova.line,
            overflow: 'hidden',
            zIndex: 9994,
            shadowColor: colors.text,
            shadowOpacity: 0.28,
            shadowRadius: 34,
            shadowOffset: { width: 0, height: 22 },
            elevation: 22,
            opacity: panelOpacity,
            transform: [{ translateY: panelTranslate }],
            ...(Platform.OS === 'web' && isPhone
              ? ({ maxWidth: 'calc(100vw - 24px)' } as any)
              : null),
          }}
        >
          <NovaSurfaceShell
            colors={{ card: nova.surface, bgSoft: nova.soft, border: nova.line, text: nova.ink, textMuted: nova.muted }}
            shellTestId="home-nova-surface-shell"
            headerTestId="home-nova-widget-header"
            titleTestId="home-nova-panel-title"
            avatarWrapTestId="home-nova-panel-avatar"
            avatarImageTestId="home-nova-panel-avatar-image"
            metaTestId="home-nova-panel-subtitle"
            title={labels.panelTitle}
            shellStyle={{ borderWidth: 1, borderRadius: isPhone ? 18 : 22, borderColor: `${colors.primary}40`, backgroundColor: nova.surface, ...(Platform.OS === 'web' ? { boxShadow: `0 0 0 1px ${colors.primary}22 inset, 0 26px 48px rgba(2,6,23,0.36)` } as any : null) }}
            headerStyle={{ paddingHorizontal: isPhone ? 12 : 14, paddingVertical: isPhone ? 10 : useDenseDesktopPanelChrome ? 10 : 12, backgroundColor: Platform.OS === 'web' ? (darkMode ? 'rgba(7,17,30,0.92)' : 'rgba(255,255,255,0.92)') : nova.surface }}
            headerMeta={<Text style={{ color: nova.muted, fontSize: 11, marginTop: 2, fontWeight: '800', textTransform: 'uppercase' }} numberOfLines={1}>{labels.panelSubtitle}</Text>}
            headerActions={(
              <>
                <TouchableOpacity
                  onPress={() => void togglePinConversation()}
                  data-testid="home-nova-pin-conversation-button"
                  testID="home-nova-pin-conversation-button"
                  accessibilityRole="button"
                  accessibilityLabel="Pin conversation"
                  style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: nova.soft, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: nova.line }}
                >
                  <Ionicons name={conversationPinned ? 'bookmark' : 'bookmark-outline'} size={16} color={conversationPinned ? colors.warningText : nova.ink} />
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={openSearch}
                  data-testid="home-nova-panel-search-button"
                  testID="home-nova-panel-search-button"
                  accessibilityRole="button"
                  accessibilityLabel={labels.searchAccessibilityLabel}
                  style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: nova.soft, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: nova.line }}
                >
                  <Ionicons name="search" size={16} color={nova.ink} />
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => setPanelMode('compact')}
                  data-testid="home-nova-collapse-button"
                  testID="home-nova-collapse-button"
                  accessibilityRole="button"
                  accessibilityLabel={labels.compactCollapse || 'Compact view'}
                  style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: nova.soft, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: nova.line }}
                >
                  <Ionicons name="contract-outline" size={16} color={nova.ink} />
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => setIsOpen(false)}
                  data-testid="home-nova-close-button"
                  testID="home-nova-close-button"
                  accessibilityRole="button"
                  accessibilityLabel={labels.closeAccessibilityLabel}
                  style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: nova.soft, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: nova.line }}
                >
                  <Ionicons name="chevron-down" size={18} color={nova.ink} />
                </TouchableOpacity>
              </>
            )}
            headerSupplement={(
              <View style={{ gap: useDenseDesktopPanelChrome ? 6 : 8 }}>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="home-nova-status-strip" testID="home-nova-status-strip">
                  {statusCards.map((card) => (
                    <View key={card.id} style={{ borderRadius: 999, borderWidth: 1, borderColor: `${card.tone}30`, backgroundColor: `${card.tone}12`, paddingHorizontal: useDenseDesktopPanelChrome ? 9 : 10, paddingVertical: useDenseDesktopPanelChrome ? 6 : 7 }} data-testid={`home-nova-status-card-${card.id}`} testID={`home-nova-status-card-${card.id}`}>
                      <Text style={{ color: card.tone, fontSize: useDenseDesktopPanelChrome ? 9 : 10, fontWeight: '800', textTransform: 'uppercase' }}>{card.label}</Text>
                      <Text style={{ color: nova.ink, fontSize: 12, fontWeight: '800', marginTop: 3 }}>{card.value}</Text>
                    </View>
                  ))}
                </View>

                <View style={{ borderRadius: 14, backgroundColor: nova.soft, borderWidth: 1, borderColor: nova.line, paddingHorizontal: 10, paddingVertical: useDenseDesktopPanelChrome ? 8 : 9 }} data-testid="home-nova-context-summary" testID="home-nova-context-summary">
                  <Text style={{ color: nova.ink, fontSize: 12, fontWeight: '900' }} numberOfLines={1}>{labels.contextTitle}</Text>
                  <Text style={{ color: nova.muted, fontSize: 11, marginTop: 4, lineHeight: 16 }} numberOfLines={showCondensedFloatingSummary ? 1 : 2}>{contextSummary}</Text>
                </View>
              </View>
            )}
            bodyTestId="home-nova-surface-body"
            bodyStyle={{ flex: 1, minHeight: 0 }}
            body={(
              <NovaChatPanel
                C={panelTheme}
                t={fakeTranslator}
                messages={panelMessages}
                inputText={input}
                setInputText={setInput}
                isLoading={sending}
                isRecording={isRecording}
                recordingTime={recordingTime}
                showFeedback={Boolean(feedbackTargetMessageId)}
                setShowFeedback={(value) => {
                  if (!value) {
                    setFeedbackTargetMessageId(null);
                    setFeedbackComment('');
                  }
                }}
                feedbackRating={0}
                setFeedbackRating={(value) => {
                  if (!feedbackTargetMessageId || value <= 0) return;
                  void submitFeedback(value, feedbackComment || (value >= 4 ? 'Great response' : 'Needs improvement'));
                }}
                feedbackComment={feedbackComment}
                setFeedbackComment={setFeedbackComment}
                feedbackSent={false}
                quickQuestions={resolvedQuickPrompts}
                attachmentPreview={attachmentPreview}
                setAttachmentPreview={setAttachmentPreview}
                sendMessage={(msg) => { void send(msg); }}
                retryPrompt={retryPrompt}
                onRetryTimeout={() => { if (retryPrompt) void send(retryPrompt); }}
                handleAttachment={handleAttachment}
                onFileSelected={onFileSelected}
                startRecording={() => { void startRecording(); }}
                stopRecording={() => { void stopRecording(); }}
                submitFeedback={() => {
                  if (!feedbackTargetMessageId) return;
                  void submitFeedback(5, feedbackComment || 'Helpful response');
                }}
                onNewChat={() => {
                  setMessages([{ id: 'nova-welcome', role: 'assistant', content: labels.welcomeMessage, timestamp: new Date().toISOString() }]);
                  setInput('');
                  setRetryPrompt(null);
                  setAttachmentPreview(null);
                  setFeedbackTargetMessageId(null);
                  setFeedbackComment('');
                }}
                chatScrollRef={scrollRef}
                fileInputRef={fileInputRef}
                inputRef={inputRef}
                conversationId={conversationId}
                conversationPinned={conversationPinned}
                onToggleConversationPin={() => { void togglePinConversation(); }}
                favoriteMessageIds={favoriteMessageIds}
                onToggleFavoriteMessage={(msg) => { void toggleFavoriteMessage(msg as any); }}
                favoriteSnippets={favoriteSnippets}
                onUseFavoriteSnippet={(content) => setInput(content.slice(0, 160))}
                surfaceVariant="floating"
                statusOverride={{
                  health: novaHealth,
                  hasLiveAssistantReply,
                  latestAssistantMessage: latestAssistantMessage as any,
                  favoriteSnippets,
                  pinnedCount: pinnedItems.length,
                  conversationPinned,
                }}
              />
            )}
          />
        </Animated.View>
      ) : null}
    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
