import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, Platform, useWindowDimensions, RefreshControl, Image, Modal, Pressable, Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { useAutoTranslate } from '../../hooks/useAutoTranslate';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { useTranslation } from '../../hooks/useTranslation';
import { useRealtimeEvent } from '../../context/RealtimeContext';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';
import AppShell from '../AppShell';
import { TicketsSkeleton } from '../SkeletonLoaders';

// ── Types ──
interface Attachment {
  file_id: string;
  original_name: string;
  size: number;
  mime_type: string;
}

interface ReplyLog {
  from: string;
  from_name: string;
  message: string;
  role: string;
  at: string;
  via?: string;
  attachments?: Attachment[];
}

interface Ticket {
  submission_id: string;
  ticket_number: string;
  subject: string;
  message: string;
  category: string;
  priority: string;
  status: string;
  assigned_to: string | null;
  attachments?: Attachment[];
  reply_logs: ReplyLog[];
  history?: { action: string; note: string; by_name?: string; at: string }[];
  satisfaction?: { rating: number; comment: string; rated_at?: string } | null;
  unread_count?: number;
  has_unread?: boolean;
  last_admin_reply_at?: string | null;
  last_user_read_at?: string | null;
  sla?: {
    target_hours: number;
    elapsed_hours: number;
    remaining_hours: number;
    breached: boolean;
    at_risk: boolean;
    state: string;
  };
  created_at: string;
  updated_at: string;
}

interface TicketAnalytics {
  range_days: number;
  kpis: {
    total_tickets: number;
    unread_messages: number;
    sla_breached: number;
    avg_resolution_hours: number | null;
    open_tickets: number;
  };
  breakdowns: {
    status: Record<string, number>;
    priority: Record<string, number>;
    category: Record<string, number>;
  };
}

// ── Constants ──

const CATEGORY_OPTIONS = [
  { value: 'general', label: 'General', icon: 'help-circle' },
  { value: 'billing', label: 'Billing', icon: 'card' },
  { value: 'technical', label: 'Technical', icon: 'construct' },
  { value: 'feature', label: 'Feature Request', icon: 'bulb' },
  { value: 'bug', label: 'Bug Report', icon: 'bug' },
];

// ── Helpers ──
const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const getFileIcon = (mime: string): string => {
  if (mime.startsWith('image/')) return 'image';
  if (mime.startsWith('video/')) return 'videocam';
  if (mime.includes('pdf')) return 'document-text';
  return 'document-attach';
};

const formatDate = (iso: string) => {
  try {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
};

const relativeTime = (iso: string, tt: (s: string) => string = (s) => s) => {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return tt('Just now');
    if (mins < 60) return `${mins}${tt('m ago')}`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}${tt('h ago')}`;
    const days = Math.floor(hrs / 24);
    return days === 1 ? tt('Yesterday') : `${days}${tt('d ago')}`;
  } catch { return iso; }
};

// ── SLA Indicator Component ──
function SLABadge({ ticket, colors: C }: { ticket: Ticket; colors: any }) {
  const created = new Date(ticket.created_at);
  if (isNaN(created.getTime()) || ['resolved', 'closed'].includes(ticket.status)) return null;
  const slaHours = ticket.priority === 'urgent' ? 4 : ticket.priority === 'high' ? 12 : 24;
  const elapsedMs = Date.now() - created.getTime();
  const elapsedH = elapsedMs / 3600000;
  const pct = Math.min((elapsedH / slaHours) * 100, 100);
  const overdue = elapsedH > slaHours;
  const color = overdue ? 'var(--app-error)' : pct > 75 ? 'var(--app-warning)' : 'var(--app-success)';
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(color, '10'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '25') }}>
      <Ionicons name={overdue ? 'alert-circle' : 'timer-outline'} size={12} color={color} />
      <Text style={{ fontSize: 10, fontWeight: '700', color }}>
        {overdue ? `Overdue (${Math.round(elapsedH - slaHours)}h)` : `${Math.round(slaHours - elapsedH)}h left`}
      </Text>
    </View>
  );
}

// ── Typing Indicator ──
function TypingIndicator({ name, colors: C }: { name: string; colors: any }) {
  const dot1 = useRef(new Animated.Value(0.3)).current;
  const dot2 = useRef(new Animated.Value(0.3)).current;
  const dot3 = useRef(new Animated.Value(0.3)).current;
  useEffect(() => {
    const animate = (val: Animated.Value, delay: number) =>
      Animated.loop(Animated.sequence([
        Animated.delay(delay),
        Animated.timing(val, { toValue: 1, duration: 300, useNativeDriver: Platform.OS !== 'web' }),
        Animated.timing(val, { toValue: 0.3, duration: 300, useNativeDriver: Platform.OS !== 'web' }),
      ]));
    const a1 = animate(dot1, 0); const a2 = animate(dot2, 150); const a3 = animate(dot3, 300);
    a1.start(); a2.start(); a3.start();
    return () => { a1.stop(); a2.stop(); a3.stop(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, paddingHorizontal: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.card, borderRadius: 14, padding: 10, borderWidth: 1, borderColor: colors.warningSoft }}>
        <View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: colors.warningSoft, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="shield" size={8} color={'var(--app-warning)'} />
        </View>
        <Animated.View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.warning, opacity: dot1 }} />
        <Animated.View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.warning, opacity: dot2 }} />
        <Animated.View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.warning, opacity: dot3 }} />
      </View>
      <Text style={{ fontSize: 11, color: C.muted, fontStyle: 'italic' }}>{name || 'Support'} is typing...</Text>
    </View>
  );
}

// ══════════════════════════════════════════════════
// ── MAIN COMPONENT ──
// ══════════════════════════════════════════════════
export default function MyTicketsScreen() {
  const router = useRouter();
  const { darkMode , colors} = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  // @autofix-moved: was module-level const STATUS_META
  const STATUS_META: Record<string, { label: string; color: string; icon: string }> = {
    open: { label: tx('myTickets.status.open', 'Open'), color: colors.primary, icon: 'ellipse' },
    in_progress: { label: tx('myTickets.status.inProgress', 'In Progress'), color: colors.warningText, icon: 'time' },
    awaiting_reply: { label: tx('myTickets.status.awaitingReply', 'Awaiting Reply'), color: colors.accent, icon: 'chatbubble-ellipses' },
    resolved: { label: tx('myTickets.status.resolved', 'Resolved'), color: colors.successText, icon: 'checkmark-circle' },
    closed: { label: tx('myTickets.status.closed', 'Closed'), color: colors.textMuted, icon: 'close-circle' },
    reopened: { label: tx('myTickets.status.reopened', 'Reopened'), color: colors.error, icon: 'refresh' },
  };
  // @autofix-moved: was module-level const PRIORITY_META
  const PRIORITY_META: Record<string, { label: string; color: string }> = {
    low: { label: tx('myTickets.priority.low', 'Low'), color: colors.textMuted },
    medium: { label: tx('myTickets.priority.medium', 'Medium'), color: colors.warningText },
    high: { label: tx('myTickets.priority.high', 'High'), color: colors.error },
    urgent: { label: tx('myTickets.priority.urgent', 'Urgent'), color: colors.error },
  };
  const { user } = useAuth();
  const { tt } = useAutoTranslate();
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const isCompact = width < 480;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _isDesktop = width >= 1024;
  const scrollRef = useRef<ScrollView>(null);

  // ── State ──
  const [view, setView] = useState<'list' | 'detail' | 'new'>('list');
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterPriority, setFilterPriority] = useState('all');
  const [filterCategory, setFilterCategory] = useState('all');
  const [filterSla, setFilterSla] = useState('all');
  const [sortBy, setSortBy] = useState<'updated_at' | 'created_at' | 'priority' | 'status'>('updated_at');
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [listMode, setListMode] = useState<'table' | 'cards'>('table');
  const [searchQuery, setSearchQuery] = useState('');
  const [replyText, setReplyText] = useState('');
  const [replying, setReplying] = useState(false);

  // New ticket form
  const [newSubject, setNewSubject] = useState('');
  const [newMessage, setNewMessage] = useState('');
  const [newCategory, setNewCategory] = useState('general');
  const [newPriority, setNewPriority] = useState('medium');
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [aiTone, setAiTone] = useState<'professional' | 'empathetic' | 'concise'>('professional');
  const [aiGeneratingDraft, setAiGeneratingDraft] = useState(false);
  const [aiRewritingReply, setAiRewritingReply] = useState(false);

  // Attachment state
  const [pendingFiles, setPendingFiles] = useState<{ file: File; name: string; size: number }[]>([]);
  const [uploading, setUploading] = useState(false);
  const [replyPendingFiles, setReplyPendingFiles] = useState<{ file: File; name: string; size: number }[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _fileInputRef = useRef<HTMLInputElement | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _replyFileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  // Satisfaction survey state
  const [surveyRating, setSurveyRating] = useState(0);
  const [surveyHover, setSurveyHover] = useState(0);
  const [surveyComment, setSurveyComment] = useState('');
  const [surveySubmitting, setSurveySubmitting] = useState(false);
  const [surveyDone, setSurveyDone] = useState(false);
  const [ticketSatisfaction, setTicketSatisfaction] = useState<{ rating: number; comment: string } | null>(null);
  const [analytics, setAnalytics] = useState<TicketAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  // WebSocket state
  const wsRef = useRef<WebSocket | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsError, setWsError] = useState('');
  const [typingUser, setTypingUser] = useState<string | null>(null);
  const [onlineMembers, setOnlineMembers] = useState<{ name: string; role: string }[]>([]);
  const typingTimer = useRef<any>(null);

  // Lightbox state
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [lightboxName, setLightboxName] = useState('');
  const [lightboxZoom, setLightboxZoom] = useState(1);
  const newTicketTitle = t('myTickets.newTicket.title');

  const C = useMemo(() => ({
    ...colors,
    primary: colors.primary, bg: colors.bg, bgSoft: colors.bgSoft || (darkMode ? colors.cardMuted : colors.card),
    card: colors.card, text: colors.text, textSec: colors.textSec || colors.textSecondary || colors.textMuted,
    muted: colors.textMuted || colors.textDim, border: colors.border,
    success: colors.success, warning: colors.warning, error: colors.error,
    adminAccent: colors.warning,
  }), [colors, darkMode]);

  // ── WebSocket Connection ──
  const activeTicketId = view === 'detail' ? String(selectedTicket?.submission_id || '') : '';

  const buildTicketWsUrl = useCallback(async () => {
    if (!activeTicketId) return '';
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'ticket_chat' });
    const ticket = String(ticketResp?.data?.ticket || '').trim();
    if (!ticket) {
      throw new Error('Missing ticket websocket token');
    }

    const baseUrl = (api.defaults.baseURL || '').replace('https://', 'wss://').replace('http://', 'ws://');
    return `${baseUrl}/ws/ticket-chat/${activeTicketId}?ticket=${encodeURIComponent(ticket)}`;
  }, [activeTicketId]);

  const { socketRef: managedSocketRef, lastError } = useManagedWebSocket({
    enabled: Boolean(activeTicketId),
    buildUrl: buildTicketWsUrl,
    errorScope: 'my-tickets/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1200,
    onOpen: () => {
      setWsConnected(true);
      setWsError('');
    },
    onClose: () => {
      setWsConnected(false);
      setTypingUser(null);
      setOnlineMembers([]);
    },
    onError: () => {
      setWsConnected(false);
      setWsError('Ticket realtime connection interrupted. Reconnecting...');
    },
    onReconnectAttempt: (attempt) => {
      setWsConnected(false);
      setWsError(`Reconnecting ticket stream (${attempt})...`);
    },
    onMessage: (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'message') {
          setSelectedTicket(prev => {
            if (!prev) return prev;
            const existing = prev.reply_logs || [];
            const isDupe = existing.some(r => r.at === data.at && r.message === data.message);
            if (isDupe) return prev;
            return { ...prev, reply_logs: [...existing, data] };
          });
          setTypingUser(null);
          setTimeout(() => scrollRef.current?.scrollToEnd?.({ animated: true }), 150);
        } else if (data.type === 'typing') {
          if (data.role === 'admin' && data.is_typing) {
            setTypingUser(data.name);
            if (typingTimer.current) clearTimeout(typingTimer.current);
            typingTimer.current = setTimeout(() => setTypingUser(null), 4000);
          } else {
            setTypingUser(null);
          }
        } else if (data.type === 'presence') {
          setOnlineMembers((data.members || []).filter((m: any) => m.role === 'admin'));
        }

        setWsError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'my-tickets/ws-parse',
          fallbackMessage: 'A ticket realtime event could not be processed.',
          setMessage: setWsError,
        });
      }
    },
  });

  useEffect(() => {
    wsRef.current = managedSocketRef.current;
  }, [managedSocketRef, wsConnected]);

  useEffect(() => {
    if (!activeTicketId) {
      setWsConnected(false);
      setTypingUser(null);
      setOnlineMembers([]);
      setWsError('');
    }
  }, [activeTicketId]);

  useEffect(() => {
    if (!lastError) return;
    setWsConnected(false);
    setWsError(lastError);
  }, [lastError]);

  // Connect WS when ticket detail opens, disconnect when leaving
  useEffect(() => {
    if (view === 'detail' && selectedTicket?.submission_id) {
      // Fetch full ticket detail to get satisfaction, full reply_logs, etc.
      api.get(`/tickets/${selectedTicket.submission_id}`).then(res => {
        setSelectedTicket(res.data);
        api.post(`/tickets/${selectedTicket.submission_id}/mark-read`).then(() => {
          setTickets(prev => prev.map(ticket => (
            ticket.submission_id === selectedTicket.submission_id
              ? { ...ticket, unread_count: 0, has_unread: false }
              : ticket
          )));
        }).catch(() => {});
        if (res.data.satisfaction) setTicketSatisfaction(res.data.satisfaction);
      }).catch(() => {});
    }
    return () => {
      if (typingTimer.current) clearTimeout(typingTimer.current);
    };
  }, [view, selectedTicket?.submission_id]);

  // ── Data Fetching ──
  const fetchAnalytics = useCallback(async () => {
    try {
      setAnalyticsLoading(true);
      const res = await api.get('/tickets/my-tickets/analytics?range_days=90');
      setAnalytics(res.data || null);
    } catch (e) {
      console.error('Failed to fetch ticket analytics:', e);
    } finally {
      setAnalyticsLoading(false);
    }
  }, []);

  const fetchTickets = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        status: filterStatus,
        priority: filterPriority,
        category: filterCategory,
        search: searchQuery,
        sla_state: filterSla,
        sort_by: sortBy,
        sort_order: sortOrder,
        limit: '80',
      });
      if (dateFrom.trim()) params.set('date_from', dateFrom.trim());
      if (dateTo.trim()) params.set('date_to', dateTo.trim());
      const res = await api.get(`/tickets/my-tickets?${params.toString()}`);
      setTickets(res.data.tickets || []);
      setTotal(res.data.total || 0);
    } catch (e) { console.error('Failed to fetch tickets:', e); }
    finally { setLoading(false); setRefreshing(false); }
  }, [filterStatus, filterPriority, filterCategory, filterSla, sortBy, sortOrder, dateFrom, dateTo, searchQuery]);

  useEffect(() => { fetchTickets(); }, [fetchTickets]);
  useEffect(() => { fetchAnalytics(); }, [fetchAnalytics]);

  useRealtimeEvent('tickets', () => {
    fetchTickets();
    fetchAnalytics();
  });

  // 30-second auto-refresh for real-time ticket data
  useAutoRefresh(fetchTickets, { intervalMs: 30000 });

  // Filtered tickets by search
  const filteredTickets = useMemo(() => {
    if (!searchQuery.trim()) return tickets;
    const q = searchQuery.toLowerCase();
    return tickets.filter(t =>
      t.subject.toLowerCase().includes(q) || t.ticket_number.toLowerCase().includes(q) ||
      t.message.toLowerCase().includes(q) || t.category.toLowerCase().includes(q)
    );
  }, [tickets, searchQuery]);

  // ── File Operations ──
  const uploadFiles = async (files: { file: File; name: string; size: number }[]): Promise<Attachment[]> => {
    const results: Attachment[] = [];
    for (const f of files) {
      const formData = new FormData();
      formData.append('file', f.file);
      try {
        const res = await api.post('/tickets/upload-attachment', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
        results.push(res.data);
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      } catch (e: any) {
        if (Platform.OS === 'web') window.alert(`Failed to upload ${f.name}`);
      }
    }
    return results;
  };

  const pickFiles = (isReply = false) => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.multiple = true; input.accept = '*/*';
      input.onchange = (e: any) => {
        const files = Array.from(e.target.files || []) as File[];
        const valid = files.filter(f => f.size <= 10 * 1024 * 1024).slice(0, 5);
        if (valid.length < files.length) window.alert('Some files skipped (max 10MB, 5 files)');
        const mapped = valid.map(f => ({ file: f, name: f.name, size: f.size }));
        if (isReply) { setReplyPendingFiles(prev => [...prev, ...mapped].slice(0, 5)); }
        else { setPendingFiles(prev => [...prev, ...mapped].slice(0, 5)); }
      };
      input.click();
    }
  };

  const handleDrop = useCallback((e: any) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false); dragCounter.current = 0;
    if (Platform.OS !== 'web') return;
    const files = Array.from(e.dataTransfer?.files || []) as File[];
    const valid = files.filter(f => f.size <= 10 * 1024 * 1024).slice(0, 5);
    if (valid.length > 0) setPendingFiles(prev => [...prev, ...valid.map(f => ({ file: f, name: f.name, size: f.size }))].slice(0, 5));
  }, []);

  const handleAiDraftSuggestion = async (mode: 'draft' | 'rewrite') => {
    if (aiGeneratingDraft) return;
    setAiGeneratingDraft(true);
    try {
      const res = await api.post('/tickets/ai/suggest-draft', {
        subject: newSubject,
        message: newMessage,
        category: newCategory,
        priority: newPriority,
        tone: aiTone,
        mode,
      });
      if (res.data?.subject) setNewSubject(String(res.data.subject));
      if (res.data?.message) setNewMessage(String(res.data.message));
    } catch (error: any) {
      if (Platform.OS === 'web') window.alert(error?.response?.data?.detail || 'AI suggestion failed');
    } finally {
      setAiGeneratingDraft(false);
    }
  };

  const handleAiRewriteReply = async () => {
    if (!selectedTicket || !replyText.trim() || aiRewritingReply) return;
    setAiRewritingReply(true);
    try {
      const res = await api.post('/tickets/ai/suggest-draft', {
        subject: selectedTicket.subject,
        message: replyText,
        category: selectedTicket.category,
        priority: selectedTicket.priority,
        tone: aiTone,
        mode: 'rewrite',
      });
      if (res.data?.message) {
        setReplyText(String(res.data.message));
      }
    } catch (error: any) {
      if (Platform.OS === 'web') window.alert(error?.response?.data?.detail || 'AI rewrite failed');
    } finally {
      setAiRewritingReply(false);
    }
  };

  // ── Ticket Actions ──
  const handleSubmitTicket = async () => {
    if (!newSubject.trim() || !newMessage.trim()) {
      if (Platform.OS === 'web') window.alert('Please fill in subject and message.');
      return;
    }
    setSubmitting(true);
    try {
      let allAttachments: Attachment[] = [];
      if (pendingFiles.length > 0) {
        setUploading(true);
        allAttachments = await uploadFiles(pendingFiles);
        setUploading(false);
      }
      const res = await api.post('/tickets/submit', {
        subject: newSubject, message: newMessage, category: newCategory, priority: newPriority,
        attachment_ids: allAttachments.map(a => a.file_id),
      });
      if (res.data.success) {
        setSubmitSuccess(res.data.ticket_number);
        setNewSubject(''); setNewMessage(''); setNewCategory('general'); setNewPriority('medium');
        setPendingFiles([]);
        fetchTickets();
        fetchAnalytics();
      }
    } catch (e: any) {
      if (Platform.OS === 'web') window.alert(e?.response?.data?.detail || 'Failed to submit ticket');
    } finally { setSubmitting(false); setUploading(false); }
  };

  const handleReply = async () => {
    if (!replyText.trim() || !selectedTicket) return;
    setReplying(true);
    const msgText = replyText.trim();
    try {
      // Upload reply files
      let replyAtts: Attachment[] = [];
      if (replyPendingFiles.length > 0) { replyAtts = await uploadFiles(replyPendingFiles); }

      // Try WebSocket first
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'message', message: msgText }));
        setReplyText(''); setReplyPendingFiles([]);
        // Optimistic update
        const now = new Date().toISOString();
        setSelectedTicket(prev => prev ? {
          ...prev,
          reply_logs: [...(prev.reply_logs || []), { from: user?.email || '', from_name: user?.name || 'You', message: msgText, role: 'user', at: now, via: 'realtime' }],
        } : prev);
        setTimeout(() => scrollRef.current?.scrollToEnd?.({ animated: true }), 150);
      } else {
        // Fallback to REST
        await api.post(`/tickets/${selectedTicket.submission_id}/reply`, {
          message: msgText, attachment_ids: replyAtts.map(a => a.file_id),
        });
        setReplyText(''); setReplyPendingFiles([]);
        const res = await api.get(`/tickets/${selectedTicket.submission_id}`);
        setSelectedTicket(res.data);
      }
      fetchTickets();
      fetchAnalytics();
      setTimeout(() => scrollRef.current?.scrollToEnd?.({ animated: true }), 300);
    } catch (e: any) {
      if (Platform.OS === 'web') window.alert(e?.response?.data?.detail || 'Failed to send reply');
    } finally { setReplying(false); }
  };

  const handleReopen = async () => {
    if (!selectedTicket) return;
    try {
      await api.post(`/tickets/${selectedTicket.submission_id}/reopen`);
      const res = await api.get(`/tickets/${selectedTicket.submission_id}`);
      setSelectedTicket(res.data);
      fetchTickets();
      fetchAnalytics();
    } catch (e: any) {
      if (Platform.OS === 'web') window.alert(e?.response?.data?.detail || 'Cannot reopen');
    }
  };

  const handleSatisfaction = async () => {
    if (!selectedTicket || !surveyRating) return;
    setSurveySubmitting(true);
    try {
      await api.post(`/tickets/${selectedTicket.submission_id}/satisfaction`, {
        rating: surveyRating, comment: surveyComment,
      });
      setSurveyDone(true);
      setTicketSatisfaction({ rating: surveyRating, comment: surveyComment });
      fetchAnalytics();
    } catch (e: any) {
      if (Platform.OS === 'web') window.alert(e?.response?.data?.detail || 'Failed to submit rating');
    } finally { setSurveySubmitting(false); }
  };

  // Send typing indicator
  const handleInputChange = (text: string) => {
    setReplyText(text);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'typing', is_typing: text.length > 0 }));
    }
  };

  // Lightbox
  const openLightbox = (url: string, name: string) => { setLightboxUrl(url); setLightboxName(name); setLightboxZoom(1); };
  const closeLightbox = () => { setLightboxUrl(null); setLightboxName(''); setLightboxZoom(1); };

  // ── Stat calculations ──
  const stats = useMemo(() => ({
    total, open: tickets.filter(t => ['open', 'reopened'].includes(t.status)).length,
    inProgress: tickets.filter(t => t.status === 'in_progress').length,
    resolved: tickets.filter(t => t.status === 'resolved').length,
  }), [tickets, total]);

  const openTicketDetail = (ticket: Ticket) => {
    setSelectedTicket(ticket);
    setView('detail');
    setReplyText('');
    setSurveyRating(0);
    setSurveyComment('');
    setSurveyDone(false);
    setTicketSatisfaction(ticket.satisfaction || null);
  };

  // ══════════════════════════════════════════
  // ── RENDER: NEW TICKET ──
  // ══════════════════════════════════════════
  const renderNewTicket = () => (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: isWide ? 32 : 16, paddingBottom: 60, maxWidth: 960, alignSelf: 'center', width: '100%' }}>
      {submitSuccess ? (
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '08'), borderRadius: 20, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '25'), marginTop: 20 }} data-testid="ticket-submit-success" testID="ticket-submit-success">
          <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: (globalThis as any).__alphaColor(C.success, '18'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="checkmark-circle" size={36} color={C.successText} />
          </View>
          <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, marginTop: 16 }}>Ticket Created</Text>
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), paddingHorizontal: 20, paddingVertical: 10, borderRadius: 12, marginTop: 12 }}>
            <Text style={{ fontSize: 17, fontWeight: '800', color: C.primary, letterSpacing: 0.5 }} data-testid="success-ticket-number" testID="success-ticket-number">{submitSuccess}</Text>
          </View>
          <Text style={{ fontSize: 13, color: C.textSec, textAlign: 'center', marginTop: 10, lineHeight: 20 }}>
            We'll respond within 24 hours. You'll receive email updates on every reply.
          </Text>
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 24 }}>
            <TouchableOpacity data-testid="ticket-success-list-btn" testID="ticket-success-list-btn" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 12, backgroundColor: C.bgSoft }} onPress={() => { setSubmitSuccess(null); setView('list'); }}>
              <Ionicons name="list" size={16} color={C.text} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>View Tickets</Text>
            </TouchableOpacity>
            <TouchableOpacity data-testid="ticket-success-new-btn" testID="ticket-success-new-btn" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 12, backgroundColor: C.primary }} onPress={() => setSubmitSuccess(null)}>
              <Ionicons name="add" size={16} color={C.primaryText} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: C.primaryText }}>New Ticket</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <View
          style={{ backgroundColor: C.card, borderRadius: 20, padding: isWide ? 28 : 18, borderWidth: isDragging ? 2 : 1, borderColor: isDragging ? C.primary : C.border, ...(isDragging ? { backgroundColor: (globalThis as any).__alphaColor(C.primary, '04') } : {}) }}
          data-testid="new-ticket-form" testID="new-ticket-form"
          {...(Platform.OS === 'web' ? {
            onDragEnter: (e: any) => { e.preventDefault(); dragCounter.current += 1; setIsDragging(true); },
            onDragLeave: (e: any) => { e.preventDefault(); dragCounter.current -= 1; if (dragCounter.current <= 0) { setIsDragging(false); dragCounter.current = 0; } },
            onDragOver: (e: any) => e.preventDefault(),
            onDrop: handleDrop,
          } : {})}
        >
          {/* Form Header */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 24 }}>
            <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="create" size={22} color={C.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: isWide ? 20 : 17, fontWeight: '800', color: C.text }}>{newTicketTitle === 'myTickets.newTicket.title' ? 'New Support Ticket' : newTicketTitle}</Text>
              <Text style={{ fontSize: 12, color: C.muted }}>{tx('myTickets.newTicket.subtitle', 'We typically respond within 24 hours')}</Text>
            </View>
          </View>

          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '0F'), borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '33'), padding: 12, marginBottom: 18 }} data-testid="ticket-ai-assist-panel" testID="ticket-ai-assist-panel">
            <View style={{ flexDirection: isCompact ? 'column' : 'row', justifyContent: 'space-between', alignItems: isCompact ? 'stretch' : 'center', gap: 10 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '22'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="sparkles" size={14} color={C.primary} />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }} data-testid="ticket-ai-assist-title" testID="ticket-ai-assist-title">{tx('myTickets.aiDraft.title', 'AI Draft Assistant')}</Text>
                  <Text style={{ fontSize: 10, color: C.muted, lineHeight: 14 }} data-testid="ticket-ai-assist-subtitle" testID="ticket-ai-assist-subtitle">{tx('myTickets.aiDraft.subtitle', 'Generate or rewrite subject/message instantly')}</Text>
                </View>
              </View>
              <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', width: isCompact ? '100%' : 'auto' }}>
                {(['professional', 'empathetic', 'concise'] as const).map((tone) => {
                  const active = aiTone === tone;
                  const toneLabel = tone === 'professional'
                    ? tx('myTickets.aiDraft.tone.professional', 'Professional')
                    : tone === 'empathetic'
                      ? tx('myTickets.aiDraft.tone.empathetic', 'Empathetic')
                      : tx('myTickets.aiDraft.tone.concise', 'Concise');
                  return (
                    <TouchableOpacity
                      key={tone}
                      data-testid={`ticket-ai-tone-${tone}`}
                      testID={`ticket-ai-tone-${tone}`}
                      style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.primary, '66') : C.border, backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '18') : C.card }}
                      onPress={() => setAiTone(tone)}
                    >
                      <Text style={{ fontSize: 10, fontWeight: '700', color: active ? C.primary : C.muted }}>{toneLabel}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              <TouchableOpacity
                data-testid="ticket-ai-draft-btn"
                testID="ticket-ai-draft-btn"
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, backgroundColor: C.primary, opacity: aiGeneratingDraft ? 0.6 : 1 }}
                disabled={aiGeneratingDraft}
                onPress={() => handleAiDraftSuggestion('draft')}
              >
                {aiGeneratingDraft ? <ActivityIndicator size="small" color={C.primaryText} /> : <Ionicons name="flash" size={14} color={C.primaryText} />}
                <Text style={{ fontSize: 11, fontWeight: '700', color: C.primaryText }}>{tx('myTickets.aiDraft.actions.suggest', 'AI Suggest Draft')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                data-testid="ticket-ai-rewrite-btn"
                testID="ticket-ai-rewrite-btn"
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '1A'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '44'), opacity: aiGeneratingDraft ? 0.6 : 1 }}
                disabled={aiGeneratingDraft || !newMessage.trim()}
                onPress={() => handleAiDraftSuggestion('rewrite')}
              >
                <Ionicons name="create-outline" size={14} color={C.primary} />
                <Text style={{ fontSize: 11, fontWeight: '700', color: C.primary }}>{tx('myTickets.aiDraft.actions.rewrite', 'Rewrite Current')}</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Category */}
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('myTickets.newTicket.category', 'Category')}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 20 }} contentContainerStyle={{ gap: 8 }}>
            {CATEGORY_OPTIONS.map(cat => {
              const active = newCategory === cat.value;
              return (
                <TouchableOpacity key={cat.value} data-testid={`cat-${cat.value}`} testID={`cat-${cat.value}`}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '12') : C.bgSoft, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.primary, '35') : 'transparent' }}
                  onPress={() => setNewCategory(cat.value)}>
                  <Ionicons name={cat.icon as any} size={14} color={active ? C.primary : C.muted} />
                  <Text style={{ fontSize: 12, fontWeight: '600', color: active ? C.primary : C.muted }}>{cat.label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          {/* Priority */}
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('myTickets.newTicket.priority', 'Priority')}</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
            {Object.entries(PRIORITY_META).map(([k, v]) => {
              const active = newPriority === k;
              return (
                <TouchableOpacity key={k} data-testid={`prio-${k}`} testID={`prio-${k}`}
                  style={{ flex: 1, minWidth: 70, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 10, borderRadius: 12, borderWidth: 1, backgroundColor: active ? (globalThis as any).__alphaColor(v.color, '10') : 'transparent', borderColor: active ? (globalThis as any).__alphaColor(v.color, '40') : C.border }}
                  onPress={() => setNewPriority(k)}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: v.color }} />
                  <Text style={{ fontSize: 12, fontWeight: '600', color: active ? v.color : C.muted }}>{v.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Subject */}
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('myTickets.newTicket.subject', 'Subject')} <Text style={{ color: C.error }}>*</Text></Text>
          <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border, paddingHorizontal: 14, marginBottom: 20 }}>
            <TextInput data-testid="ticket-subject-input" testID="ticket-subject-input" style={{ fontSize: 14, color: C.text, paddingVertical: 14, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
              placeholder={tx('myTickets.newTicket.subjectPlaceholder', 'Brief description of your issue')} placeholderTextColor={C.muted}
              value={newSubject} onChangeText={setNewSubject} maxLength={200} />
          </View>

          {/* Message */}
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('myTickets.newTicket.message', 'Message')} <Text style={{ color: C.error }}>*</Text></Text>
          <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border, paddingHorizontal: 14, paddingTop: 4, marginBottom: 4 }}>
            <TextInput data-testid="ticket-message-input" testID="ticket-message-input"
              style={{ fontSize: 14, color: C.text, minHeight: 160, textAlignVertical: 'top', paddingVertical: 12, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
              placeholder={tx('myTickets.newTicket.messagePlaceholder', 'Describe your issue in detail...')}
              placeholderTextColor={C.muted}
              value={newMessage} onChangeText={setNewMessage}
              multiline maxLength={2000} numberOfLines={8}
            />
          </View>
          <Text style={{ fontSize: 11, color: C.muted, textAlign: 'right', marginBottom: 20 }}>{newMessage.length}/2000</Text>

          {/* Attachments */}
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('myTickets.newTicket.attachments', 'Attachments')} <Text style={{ color: C.muted, fontWeight: '500' }}>({tx('myTickets.newTicket.optional', 'optional')})</Text></Text>
          {isDragging ? (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), borderRadius: 14, borderWidth: 2, borderColor: C.primary, borderStyle: 'dashed', padding: 28, alignItems: 'center', marginBottom: 12 }} data-testid="drag-drop-overlay" testID="drag-drop-overlay">
              <Ionicons name="cloud-download-outline" size={36} color={C.primary} />
              <Text style={{ fontSize: 15, fontWeight: '700', color: C.primary, marginTop: 8 }}>{tx('myTickets.newTicket.dropFilesHere', 'Drop files here')}</Text>
            </View>
          ) : (
            <TouchableOpacity data-testid="attach-files-btn" testID="attach-files-btn"
              style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, borderRadius: 12, borderWidth: 1.5, borderColor: C.border, borderStyle: 'dashed', backgroundColor: C.bgSoft, marginBottom: 8 }}
              onPress={() => pickFiles(false)} disabled={pendingFiles.length >= 5}>
              <Ionicons name="cloud-upload-outline" size={20} color={C.primary} />
              <Text style={{ fontSize: 13, fontWeight: '600', color: C.primary }}>{tx('myTickets.newTicket.attachFiles', 'Attach Files')}</Text>
              <Text style={{ fontSize: 11, color: C.muted }}>{tx('myTickets.newTicket.orDragDrop', 'or drag & drop')}</Text>
            </TouchableOpacity>
          )}
          <Text style={{ fontSize: 10, color: C.muted, marginBottom: 4 }}>{tx('myTickets.newTicket.maxFileHint', 'Max 10MB each, up to 5 files')}</Text>
          {pendingFiles.length > 0 && (
            <View style={{ gap: 6, marginBottom: 12 }}>
              {pendingFiles.map((pf, idx) => (
                <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: C.border }} data-testid={`pending-file-${idx}`} testID={`pending-file-${idx}`}>
                  <View style={{ width: 38, height: 38, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="document-attach" size={18} color={C.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }} numberOfLines={1}>{pf.name}</Text>
                    <Text style={{ fontSize: 10, color: C.muted }}>{formatSize(pf.size)}</Text>
                  </View>
                  <TouchableOpacity onPress={() => setPendingFiles(prev => prev.filter((_, i) => i !== idx))} data-testid={`remove-file-${idx}`} testID={`remove-file-${idx}`}>
                    <Ionicons name="close-circle" size={20} color={C.error} />
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          )}
          {uploading && (
            <TicketsSkeleton />
          )}

          {/* Submit */}
          <TouchableOpacity data-testid="submit-ticket-btn" testID="submit-ticket-btn"
            style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 14, paddingVertical: 16, backgroundColor: C.primary, opacity: submitting ? 0.6 : 1 }}
            onPress={handleSubmitTicket} disabled={submitting}>
            {submitting ? <ActivityIndicator color={C.primaryText} /> : (
              <><Ionicons name="send" size={18} color={C.primaryText} /><Text style={{ fontSize: 15, fontWeight: '700', color: C.primaryText }}>{tx('myTickets.actions.submitTicket', 'Submit Ticket')}</Text></>
            )}
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );

  // ══════════════════════════════════════════
  // ── RENDER: TICKET LIST ──
  // ══════════════════════════════════════════
  const renderTicketList = () => (
    <ScrollView
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchTickets(); fetchAnalytics(); }} tintColor={C.primary} />}
      contentContainerStyle={{ padding: isWide ? 24 : 16, paddingBottom: 60, maxWidth: 1240, alignSelf: 'center', width: '100%' }}
    >
      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 16, flexWrap: 'wrap' }} data-testid="ticket-enterprise-kpis" testID="ticket-enterprise-kpis">
        {[
          { key: 'total', label: tx('myTickets.kpi.totalTickets', 'TOTAL TICKETS'), value: analytics?.kpis?.total_tickets ?? stats.total, icon: 'receipt-outline', color: C.primary },
          { key: 'unread', label: tx('myTickets.kpi.unreadMessages', 'UNREAD MESSAGES'), value: analytics?.kpis?.unread_messages ?? tickets.reduce((sum, t) => sum + (t.unread_count || 0), 0), icon: 'mail-unread-outline', color: C.primary },
          { key: 'sla', label: tx('myTickets.kpi.slaBreached', 'SLA BREACHED'), value: analytics?.kpis?.sla_breached ?? tickets.filter(t => t.sla?.state === 'breached').length, icon: 'warning-outline', color: C.error },
          { key: 'resolution', label: tx('myTickets.kpi.avgResolutionHours', 'AVG RESOLUTION (HRS)'), value: analytics?.kpis?.avg_resolution_hours ?? '--', icon: 'speedometer-outline', color: colors.successText },
        ].map(card => (
          <View key={card.key} data-testid={`ticket-kpi-${card.key}`} testID={`ticket-kpi-${card.key}`} style={{ flex: 1, minWidth: 190, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 14 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ fontSize: 10, letterSpacing: 1.1, fontWeight: '700', color: C.muted }}>{card.label}</Text>
              <Ionicons name={card.icon as any} size={15} color={card.color} />
            </View>
            <Text style={{ fontSize: 30, fontWeight: '900', marginTop: 6, color: C.text }} data-testid={`ticket-kpi-value-${card.key}`} testID={`ticket-kpi-value-${card.key}`}>{analyticsLoading ? '…' : card.value}</Text>
          </View>
        ))}
      </View>

      <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 14 }} data-testid="ticket-filters-bar" testID="ticket-filters-bar">
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <View style={{ flex: 1, minWidth: 220, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 10 }}>
            <Ionicons name="search" size={15} color={C.muted} />
            <TextInput
              style={{ flex: 1, fontSize: 13, color: C.text, paddingVertical: 10, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
              placeholder={tx('myTickets.search.placeholder', 'Search tickets...')}
              placeholderTextColor={C.muted}
              value={searchQuery}
              onChangeText={setSearchQuery}
              data-testid="ticket-search-input"
              testID="ticket-search-input"
            />
            {searchQuery.length > 0 && (
              <TouchableOpacity data-testid="clear-search-btn" testID="clear-search-btn" onPress={() => setSearchQuery('')}>
                <Ionicons name="close-circle" size={18} color={C.muted} />
              </TouchableOpacity>
            )}
          </View>

          <TouchableOpacity data-testid="ticket-sort-toggle" testID="ticket-sort-toggle" style={{ paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, flexDirection: 'row', gap: 6, alignItems: 'center' }} onPress={() => setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc')}>
            <Ionicons name={sortOrder === 'desc' ? 'arrow-down' : 'arrow-up'} size={14} color={C.muted} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.muted }}>{sortOrder.toUpperCase()}</Text>
          </TouchableOpacity>

          <TouchableOpacity data-testid="ticket-list-mode-toggle" testID="ticket-list-mode-toggle" style={{ paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, flexDirection: 'row', gap: 6, alignItems: 'center' }} onPress={() => setListMode(prev => prev === 'table' ? 'cards' : 'table')}>
            <Ionicons name={listMode === 'table' ? 'grid-outline' : 'list-outline'} size={14} color={C.muted} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.muted }}>{listMode === 'table' ? 'CARDS' : 'TABLE'}</Text>
          </TouchableOpacity>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 10 }} contentContainerStyle={{ gap: 6 }}>
          {['all', 'open', 'in_progress', 'awaiting_reply', 'resolved', 'closed'].map(s => {
            const active = filterStatus === s;
            return (
              <TouchableOpacity key={s} data-testid={`filter-status-${s}`} testID={`filter-status-${s}`} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 99, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.primary, '33') : C.border, backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '14') : C.bgSoft }} onPress={() => setFilterStatus(s)}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: active ? C.primary : C.muted }}>{s === 'all' ? tx('myTickets.filters.allStatus', 'All Status') : (STATUS_META[s]?.label || s)}</Text>
              </TouchableOpacity>
            );
          })}
          {(['all', 'urgent', 'high', 'medium', 'low'] as const).map(pr => {
            const active = filterPriority === pr;
            return (
              <TouchableOpacity key={pr} data-testid={`filter-priority-${pr}`} testID={`filter-priority-${pr}`} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 99, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.warning, '33') : C.border, backgroundColor: active ? (globalThis as any).__alphaColor(C.warning, '14') : C.bgSoft }} onPress={() => setFilterPriority(pr)}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: active ? C.warningText : C.muted }}>{pr === 'all' ? tx('myTickets.filters.allPriority', 'All Priority') : pr.toUpperCase()}</Text>
              </TouchableOpacity>
            );
          })}
          {(['all', 'general', 'billing', 'technical', 'feature', 'bug'] as const).map(cat => {
            const active = filterCategory === cat;
            return (
              <TouchableOpacity key={cat} data-testid={`filter-category-${cat}`} testID={`filter-category-${cat}`} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 99, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.primary, '55') : C.border, backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '15') : C.bgSoft }} onPress={() => setFilterCategory(cat)}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: active ? C.primary : C.muted }}>{cat === 'all' ? tx('myTickets.filters.allCategory', 'All Category') : cat}</Text>
              </TouchableOpacity>
            );
          })}
          {(['all', 'healthy', 'at_risk', 'breached', 'closed'] as const).map(sla => {
            const active = filterSla === sla;
            return (
              <TouchableOpacity key={sla} data-testid={`filter-sla-${sla}`} testID={`filter-sla-${sla}`} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 99, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.error, '33') : C.border, backgroundColor: active ? (globalThis as any).__alphaColor(C.error, '12') : C.bgSoft }} onPress={() => setFilterSla(sla)}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: active ? C.error : C.muted }}>{sla === 'all' ? tx('myTickets.filters.allSla', 'All SLA') : sla.replace('_', ' ')}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 10 }}>
            <Ionicons name="calendar-outline" size={14} color={C.muted} />
            <TextInput data-testid="filter-date-from" testID="filter-date-from" value={dateFrom} onChangeText={setDateFrom} placeholder={tx('myTickets.filters.fromDate', 'From YYYY-MM-DD')} placeholderTextColor={C.muted} style={{ minWidth: 130, fontSize: 11, color: C.text, paddingVertical: 8, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }} />
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingHorizontal: 10 }}>
            <Ionicons name="calendar-outline" size={14} color={C.muted} />
            <TextInput data-testid="filter-date-to" testID="filter-date-to" value={dateTo} onChangeText={setDateTo} placeholder={tx('myTickets.filters.toDate', 'To YYYY-MM-DD')} placeholderTextColor={C.muted} style={{ minWidth: 120, fontSize: 11, color: C.text, paddingVertical: 8, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }} />
          </View>
          <TouchableOpacity data-testid="filter-reset-btn" testID="filter-reset-btn" onPress={() => { setFilterStatus('all'); setFilterPriority('all'); setFilterCategory('all'); setFilterSla('all'); setDateFrom(''); setDateTo(''); setSearchQuery(''); setSortBy('updated_at'); setSortOrder('desc'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.muted }}>{tx('myTickets.filters.reset', 'Reset Filters')}</Text>
          </TouchableOpacity>
          <TouchableOpacity data-testid="sort-by-updated-btn" testID="sort-by-updated-btn" onPress={() => setSortBy('updated_at')} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: sortBy === 'updated_at' ? (globalThis as any).__alphaColor(C.primary, '33') : C.border, backgroundColor: sortBy === 'updated_at' ? (globalThis as any).__alphaColor(C.primary, '14') : C.bgSoft }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: sortBy === 'updated_at' ? C.primary : C.muted }}>{tx('myTickets.filters.sortUpdated', 'Sort: Updated')}</Text>
          </TouchableOpacity>
          <TouchableOpacity data-testid="sort-by-priority-btn" testID="sort-by-priority-btn" onPress={() => setSortBy('priority')} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: sortBy === 'priority' ? (globalThis as any).__alphaColor(C.primary, '33') : C.border, backgroundColor: sortBy === 'priority' ? (globalThis as any).__alphaColor(C.primary, '14') : C.bgSoft }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: sortBy === 'priority' ? C.primary : C.muted }}>{tx('myTickets.filters.sortPriority', 'Sort: Priority')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading ? <TicketsSkeleton /> : filteredTickets.length === 0 ? (
        <View style={{ alignItems: 'center', paddingVertical: 48 }} data-testid="no-tickets" testID="no-tickets">
          <View style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: (globalThis as any).__alphaColor(C.primary, '08'), alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
            <Ionicons name="chatbubbles-outline" size={32} color={C.muted} />
          </View>
          <Text style={{ fontSize: 18, fontWeight: '800', color: C.text }}>{searchQuery ? tx('myTickets.states.noMatchingTickets', 'No matching tickets') : tx('myTickets.states.noTicketsYet', 'No tickets yet')}</Text>
          <Text style={{ fontSize: 13, color: C.muted, marginTop: 6, textAlign: 'center', maxWidth: 280 }}>{searchQuery ? tx('myTickets.states.tryDifferentSearch', 'Try a different search term') : tx('myTickets.states.needHelpPrompt', 'Need help? Submit a ticket and our team will assist you.')}</Text>
          <TouchableOpacity data-testid="empty-new-ticket-btn" testID="empty-new-ticket-btn" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 20, paddingVertical: 12, borderRadius: 12, backgroundColor: C.primary, marginTop: 20 }} onPress={() => setView('new')}>
            <Ionicons name="add" size={16} color={C.primaryText} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.primaryText }}>{tx('myTickets.actions.createTicket', 'Create Ticket')}</Text>
          </TouchableOpacity>
        </View>
      ) : listMode === 'table' ? (
        <View style={{ borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden', backgroundColor: C.card }} data-testid="ticket-table-view" testID="ticket-table-view">
          <View style={{ flexDirection: 'row', backgroundColor: C.bgSoft, borderBottomWidth: 1, borderBottomColor: C.border, paddingHorizontal: 12, paddingVertical: 10 }}>
            {[tx('myTickets.table.ticket', 'Ticket'), tx('myTickets.table.subject', 'Subject'), tx('myTickets.table.category', 'Category'), tx('myTickets.table.priority', 'Priority'), tx('myTickets.table.status', 'Status'), tx('myTickets.table.sla', 'SLA'), tx('myTickets.table.updated', 'Updated'), tx('myTickets.table.unread', 'Unread')].map((head) => (
              <Text key={head} data-testid={`ticket-table-head-${head.toLowerCase().replace(/\s+/g, '-')}`} testID={`ticket-table-head-${head.toLowerCase().replace(/\s+/g, '-')}`} style={{ flex: head === 'Subject' ? 2 : 1, fontSize: 10, letterSpacing: 0.7, fontWeight: '700', color: C.muted }}>{head}</Text>
            ))}
          </View>
          {filteredTickets.map((ticket) => {
            const st = STATUS_META[ticket.status] || STATUS_META.open;
            const pr = PRIORITY_META[ticket.priority] || PRIORITY_META.medium;
            const unread = Number(ticket.unread_count || 0);
            const slaState = ticket.sla?.state || 'healthy';
            const slaColor = slaState === 'breached' ? C.error : slaState === 'at_risk' ? C.warningText : colors.successText;
            return (
              <TouchableOpacity key={ticket.submission_id} data-testid={`ticket-row-${ticket.ticket_number}`} testID={`ticket-row-${ticket.ticket_number}`} onPress={() => openTicketDetail(ticket)} style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.border, paddingHorizontal: 12, paddingVertical: 11, alignItems: 'center', backgroundColor: ticket.has_unread ? (globalThis as any).__alphaColor(C.primary, '10') : C.card }}>
                <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  {ticket.has_unread ? <View data-testid={`ticket-unread-dot-${ticket.ticket_number}`} testID={`ticket-unread-dot-${ticket.ticket_number}`} style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.primary }} /> : <View style={{ width: 8, height: 8 }} />}
                  <Text style={{ fontSize: 11, fontWeight: '700', color: C.primary }}>{ticket.ticket_number}</Text>
                </View>
                <Text style={{ flex: 2, fontSize: 12, fontWeight: ticket.has_unread ? '800' : '600', color: C.text }} numberOfLines={1} data-testid={`ticket-row-subject-${ticket.ticket_number}`} testID={`ticket-row-subject-${ticket.ticket_number}`}>{ticket.subject}</Text>
                <Text style={{ flex: 1, fontSize: 11, color: C.muted }} numberOfLines={1}>{ticket.category}</Text>
                <Text style={{ flex: 1, fontSize: 11, fontWeight: '700', color: pr.color }}>{pr.label}</Text>
                <Text style={{ flex: 1, fontSize: 11, fontWeight: '700', color: st.color }}>{st.label}</Text>
                <Text style={{ flex: 1, fontSize: 11, fontWeight: '700', color: slaColor, textTransform: 'uppercase' }}>{slaState.replace('_', ' ')}</Text>
                <Text style={{ flex: 1, fontSize: 11, color: C.muted }}>{relativeTime(ticket.updated_at || ticket.created_at)}</Text>
                <Text style={{ flex: 1, fontSize: 11, fontWeight: '700', color: unread > 0 ? C.primary : C.muted }} data-testid={`ticket-row-unread-${ticket.ticket_number}`} testID={`ticket-row-unread-${ticket.ticket_number}`}>{unread}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      ) : (
        filteredTickets.map(ticket => {
          const st = STATUS_META[ticket.status] || STATUS_META.open;
          const pr = PRIORITY_META[ticket.priority] || PRIORITY_META.medium;
          const replyCount = ticket.reply_logs?.length || 0;
          const hasAdminReply = ticket.reply_logs?.some(r => r.role === 'admin');
          return (
            <TouchableOpacity key={ticket.submission_id} data-testid={`ticket-card-${ticket.ticket_number}`} testID={`ticket-card-${ticket.ticket_number}`}
              style={{
                backgroundColor: ticket.has_unread ? (globalThis as any).__alphaColor(C.primary, '10') : C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border,
                padding: isWide ? 18 : 14, marginBottom: 10,
                ...(Platform.OS === 'web' ? { transition: 'all 0.15s ease' } as any : {}),
              }}
              onPress={() => openTicketDetail(ticket)} activeOpacity={0.7}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  {ticket.has_unread ? <View data-testid={`ticket-unread-dot-card-${ticket.ticket_number}`} testID={`ticket-unread-dot-card-${ticket.ticket_number}`} style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.primary }} /> : null}
                  <Text style={{ fontSize: 11, fontWeight: '800', color: C.primary, letterSpacing: 0.3 }}>{ticket.ticket_number}</Text>
                  <SLABadge ticket={ticket} colors={C} />
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(st.color, '14'), paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 }}>
                  <Ionicons name={st.icon as any} size={10} color={st.color} />
                  <Text style={{ fontSize: 10, fontWeight: '700', color: st.color }}>{st.label}</Text>
                </View>
              </View>

              <Text style={{ fontSize: isWide ? 15 : 14, fontWeight: ticket.has_unread ? '800' : '700', color: C.text, marginBottom: 4 }} numberOfLines={1}>{ticket.subject}</Text>
              <Text style={{ fontSize: 12, color: C.muted, lineHeight: 18, marginBottom: 10 }} numberOfLines={2}>{ticket.message}</Text>

              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: pr.color }} />
                    <Text style={{ fontSize: 11, color: C.muted }}>{pr.label}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <Ionicons name="folder-outline" size={11} color={C.muted} />
                    <Text style={{ fontSize: 11, color: C.muted }}>{ticket.category}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  {replyCount > 0 && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                      <Ionicons name="chatbubbles" size={12} color={hasAdminReply ? C.adminAccent : C.primary} />
                      <Text style={{ fontSize: 11, color: hasAdminReply ? C.adminAccent : C.primary, fontWeight: '600' }}>{replyCount}</Text>
                    </View>
                  )}
                    <Text style={{ fontSize: 11, color: ticket.unread_count ? C.primary : C.muted, fontWeight: '700' }}>{ticket.unread_count || 0} {tx('myTickets.list.unread', 'unread')}</Text>
                  <Text style={{ fontSize: 11, color: C.muted }}>{relativeTime(ticket.updated_at || ticket.created_at)}</Text>
                </View>
              </View>
            </TouchableOpacity>
          );
        })
      )}
    </ScrollView>
  );

  // ══════════════════════════════════════════
  // ── RENDER: TICKET DETAIL (CHAT) ──
  // ══════════════════════════════════════════
  const renderTicketDetail = () => {
    if (!selectedTicket) return null;
    const st = STATUS_META[selectedTicket.status] || STATUS_META.open;
    const pr = PRIORITY_META[selectedTicket.priority] || PRIORITY_META.medium;
    const canReply = !['closed', 'resolved'].includes(selectedTicket.status);
    const canReopen = ['closed', 'resolved'].includes(selectedTicket.status);
    const adminOnline = onlineMembers.length > 0;

    return (
      <View style={{ flex: 1 }}>
        <ScrollView ref={scrollRef} showsVerticalScrollIndicator={false}
          contentContainerStyle={{ padding: isWide ? 24 : 14, paddingBottom: canReply ? 110 : 40, maxWidth: 960, alignSelf: 'center', width: '100%' }}>

          {/* Ticket Info Header */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: isWide ? 18 : 14, borderWidth: 1, borderColor: C.border, marginBottom: 16 }} data-testid="ticket-detail-header" testID="ticket-detail-header">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <View style={{ flex: 1, marginRight: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <Text style={{ fontSize: 11, fontWeight: '800', color: C.primary, letterSpacing: 0.5 }}>{selectedTicket.ticket_number}</Text>
                  {/* Real-time Connection Badge */}
                  <View data-testid="my-tickets-ws-status-badge" testID="my-tickets-ws-status-badge" style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: wsConnected ? colors.successSoft : C.bgSoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 }}>
                    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: wsConnected ? colors.success : C.muted }} />
                    <Text style={{ fontSize: 9, fontWeight: '700', color: wsConnected ? colors.success : C.muted }}>{wsConnected ? tx('myTickets.detail.live', 'LIVE') : tx('myTickets.detail.offline', 'OFFLINE')}</Text>
                  </View>
                </View>
                <Text style={{ fontSize: isWide ? 18 : 16, fontWeight: '800', color: C.text }}>{selectedTicket.subject}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(st.color, '14'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10 }}>
                <Ionicons name={st.icon as any} size={12} color={st.color} />
                <Text style={{ fontSize: 11, fontWeight: '700', color: st.color }}>{st.label}</Text>
              </View>
            </View>

            {/* Meta Tags */}
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 }}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: pr.color }} />
                <Text style={{ fontSize: 11, color: C.muted }}>{pr.label}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 }}>
                <Ionicons name="folder" size={12} color={C.muted} />
                <Text style={{ fontSize: 11, color: C.muted }}>{selectedTicket.category}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 }}>
                <Ionicons name="calendar" size={12} color={C.muted} />
                <Text style={{ fontSize: 11, color: C.muted }}>{formatDate(selectedTicket.created_at)}</Text>
              </View>
              <SLABadge ticket={selectedTicket} colors={C} />
              {adminOnline && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.successSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success }} />
                  <Text style={{ fontSize: 11, color: colors.successText, fontWeight: '600' }}>{tx('myTickets.detail.supportOnline', 'Support Online')}</Text>
                </View>
              )}
            </View>

            {!!wsError && (
              <View data-testid="my-tickets-ws-error" testID="my-tickets-ws-error" style={{ marginTop: 10, backgroundColor: (globalThis as any).__alphaColor(C.warn, '14'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.warn, '32'), borderRadius: 10, padding: 8 }}>
                <Text style={{ fontSize: 11, color: C.warn, fontWeight: '600' }}>{wsError}</Text>
              </View>
            )}
          </View>

          {/* Conversation Thread Label */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
            <Ionicons name="chatbubbles-outline" size={14} color={C.muted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('myTickets.detail.conversation', 'Conversation')}</Text>
          </View>

          {/* Original Message (User) */}
          <View style={{ marginBottom: 12, alignItems: 'flex-end' }} data-testid="ticket-original-message" testID="ticket-original-message">
            <View style={{ maxWidth: isWide ? '75%' : '88%', backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), borderRadius: 16, borderBottomRightRadius: 4, padding: 14 }}>
              <Text style={{ fontSize: 14, color: C.text, lineHeight: 22 }}>{selectedTicket.message}</Text>
              {/* Attachments */}
              {selectedTicket.attachments && selectedTicket.attachments.length > 0 && (
                <View style={{ marginTop: 8, gap: 6 }}>
                  {selectedTicket.attachments.map((att, i) => {
                    const isImage = att.mime_type.startsWith('image/');
                    const attUrl = `${api.defaults.baseURL}/tickets/attachment/${att.file_id}`;
                    return isImage ? (
                      <TouchableOpacity key={att.file_id} data-testid={`orig-att-${i}`} testID={`orig-att-${i}`} onPress={() => openLightbox(attUrl, att.original_name)}>
                        <Image source={{ uri: attUrl }} style={{ width: '100%' as any, height: 180, borderRadius: 10 }} resizeMode="cover" accessibilityLabel="Decorative image" />
                        <Text style={{ fontSize: 10, color: C.muted, marginTop: 3 }}>{att.original_name} ({formatSize(att.size)})</Text>
                      </TouchableOpacity>
                    ) : (
                      <TouchableOpacity key={att.file_id} data-testid={`orig-att-${i}`} testID={`orig-att-${i}`}
                        style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(C.primary, '08'), borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '15') }}
                        onPress={() => { if (Platform.OS === 'web') window.open(attUrl, '_blank'); }}>
                        <Ionicons name={getFileIcon(att.mime_type) as any} size={14} color={C.primary} />
                        <Text style={{ fontSize: 11, color: C.primary, fontWeight: '600', flex: 1 }} numberOfLines={1}>{att.original_name}</Text>
                        <Text style={{ fontSize: 10, color: C.muted }}>{formatSize(att.size)}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
              <Text style={{ fontSize: 10, color: C.muted, marginTop: 6, textAlign: 'right' }}>You  {formatDate(selectedTicket.created_at)}</Text>
            </View>
          </View>

          {/* Reply Thread */}
          {selectedTicket.reply_logs?.map((reply, idx) => {
            const isAdmin = reply.role === 'admin';
            return (
              <View key={idx} style={{ marginBottom: 12, alignItems: isAdmin ? 'flex-start' : 'flex-end' }} data-testid={`reply-${idx}`} testID={`reply-${idx}`}>
                {isAdmin && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4, marginLeft: 4 }}>
                    <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: colors.warningSoft, alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="shield" size={10} color={colors.warningText} />
                    </View>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{reply.from_name || tx('myTickets.detail.supportTeam', 'Support Team')}</Text>
                    <View style={{ backgroundColor: colors.warningSoft, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 }}>
                      <Text style={{ fontSize: 8, fontWeight: '800', color: colors.warningText }}>{tx('myTickets.detail.staff', 'STAFF')}</Text>
                    </View>
                    {reply.via === 'realtime' && (
                      <View style={{ backgroundColor: colors.successSoft, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 }}>
                        <Text style={{ fontSize: 8, fontWeight: '800', color: colors.successText }}>{tx('myTickets.detail.live', 'LIVE')}</Text>
                      </View>
                    )}
                  </View>
                )}
                <View style={{
                  maxWidth: isWide ? '75%' : '88%',
                  backgroundColor: (globalThis as any).__alphaColor(isAdmin ? C.card : C.primary, '12'),
                  borderRadius: 16,
                  ...(isAdmin ? { borderBottomLeftRadius: 4, borderWidth: 1, borderColor: colors.warningSoft } : { borderBottomRightRadius: 4 }),
                  padding: 14,
                }}>
                  <Text style={{ fontSize: 14, color: C.text, lineHeight: 22 }}>{reply.message}</Text>
                  {/* Reply Attachments */}
                  {reply.attachments && reply.attachments.length > 0 && (
                    <View style={{ marginTop: 8, gap: 6 }}>
                      {reply.attachments.map((att, ai) => {
                        const isImage = att.mime_type.startsWith('image/');
                        const attUrl = `${api.defaults.baseURL}/tickets/attachment/${att.file_id}`;
                        const acColor = isAdmin ? colors.warning : C.primary;
                        return isImage ? (
                          <TouchableOpacity key={att.file_id} data-testid={`reply-att-${idx}-${ai}`} testID={`reply-att-${idx}-${ai}`} onPress={() => openLightbox(attUrl, att.original_name)}>
                            <Image source={{ uri: attUrl }} style={{ width: '100%' as any, height: 180, borderRadius: 10 }} resizeMode="cover" accessibilityLabel="att.original_name" />
                          </TouchableOpacity>
                        ) : (
                          <TouchableOpacity key={att.file_id} data-testid={`reply-att-${idx}-${ai}`} testID={`reply-att-${idx}-${ai}`}
                            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(acColor, '08'), borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(acColor, '15') }}
                            onPress={() => { if (Platform.OS === 'web') window.open(attUrl, '_blank'); }}>
                            <Ionicons name={getFileIcon(att.mime_type) as any} size={14} color={acColor} />
                            <Text style={{ fontSize: 11, color: acColor, fontWeight: '600', flex: 1 }} numberOfLines={1}>{att.original_name}</Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  )}
                  <Text style={{ fontSize: 10, color: C.muted, marginTop: 6, textAlign: isAdmin ? 'left' : 'right' }}>
                    {isAdmin ? '' : 'You  '}{formatDate(reply.at)}
                  </Text>
                </View>
              </View>
            );
          })}

          {/* Typing Indicator */}
          {typingUser && <TypingIndicator name={typingUser} colors={C} />}

          {/* Satisfaction Survey */}
          {['resolved', 'closed'].includes(selectedTicket.status) && !ticketSatisfaction && !surveyDone && (
            <View style={{
              backgroundColor: C.card, borderRadius: 16, padding: isWide ? 24 : 18, marginTop: 16,
              borderWidth: 1, borderColor: colors.warningSoft,
              ...(Platform.OS === 'web' ? { backgroundImage: 'linear-gradient(135deg, rgba(245,158,11,0.03), rgba(16,185,129,0.03))' } as any : {}),
            }} data-testid="satisfaction-survey" testID="satisfaction-survey">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.warningSoft, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="heart" size={18} color={colors.warningText} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>How was your experience?</Text>
                  <Text style={{ fontSize: 12, color: C.muted }}>Your feedback helps us improve our support</Text>
                </View>
              </View>
              {/* Star Rating */}
              <View style={{ flexDirection: 'row', justifyContent: 'center', gap: isWide ? 12 : 8, marginBottom: 16 }}>
                {[1, 2, 3, 4, 5].map(star => {
                  const active = star <= (surveyHover || surveyRating);
                  const labels = ['', 'Poor', 'Fair', 'Good', 'Great', 'Excellent'];
                  return (
                    <TouchableOpacity key={star} data-testid={`star-${star}`} testID={`star-${star}`}
                      onPress={() => setSurveyRating(star)}
                      {...(Platform.OS === 'web' ? { onMouseEnter: () => setSurveyHover(star), onMouseLeave: () => setSurveyHover(0) } as any : {})}
                      style={{ alignItems: 'center', gap: 4 }}>
                      <View style={{
                        width: isWide ? 52 : 44, height: isWide ? 52 : 44, borderRadius: 14,
                        backgroundColor: active ? colors.warningSoft : C.bgSoft,
                        borderWidth: 2, borderColor: active ? colors.warning : 'transparent',
                        alignItems: 'center', justifyContent: 'center',
                        ...(Platform.OS === 'web' ? { transition: 'all 0.15s ease', cursor: 'pointer' } as any : {}),
                      }}>
                        <Ionicons name={active ? 'star' : 'star-outline'} size={isWide ? 24 : 20} color={active ? colors.warning : C.muted} />
                      </View>
                      <Text style={{ fontSize: 9, color: active ? colors.warning : C.muted, fontWeight: active ? '700' : '500' }}>{labels[star]}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
              {/* Comment */}
              {surveyRating > 0 && (
                <View style={{ marginBottom: 14 }}>
                  <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border, paddingHorizontal: 14, paddingTop: 4 }}>
                    <TextInput data-testid="satisfaction-comment" testID="satisfaction-comment"
                      style={{ fontSize: 13, color: C.text, minHeight: 60, textAlignVertical: 'top', paddingVertical: 10, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
                      placeholder="Any additional feedback? (optional)"
                      placeholderTextColor={C.muted}
                      value={surveyComment} onChangeText={setSurveyComment}
                      multiline maxLength={500}
                    />
                  </View>
                </View>
              )}
              {/* Submit */}
              {surveyRating > 0 && (
                <TouchableOpacity data-testid="submit-satisfaction-btn" testID="submit-satisfaction-btn"
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, borderRadius: 14, backgroundColor: colors.warning, opacity: surveySubmitting ? 0.6 : 1 }}
                  onPress={handleSatisfaction} disabled={surveySubmitting}>
                  {surveySubmitting ? <ActivityIndicator color={C.primaryText} size="small" /> : (
                    <><Ionicons name="send" size={16} color={C.primaryText} /><Text style={{ fontSize: 14, fontWeight: '700', color: C.primaryText }}>Submit Feedback</Text></>
                  )}
                </TouchableOpacity>
              )}
            </View>
          )}

          {/* Already Rated */}
          {ticketSatisfaction && (
            <View style={{ backgroundColor: colors.successSoft, borderRadius: 14, padding: 16, marginTop: 16, borderWidth: 1, borderColor: colors.successSoft, flexDirection: 'row', alignItems: 'center', gap: 12 }} data-testid="satisfaction-done" testID="satisfaction-done">
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="checkmark-circle" size={18} color={colors.successText} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>Thank you for your feedback!</Text>
                  <View style={{ flexDirection: 'row', gap: 2 }}>
                    {[1, 2, 3, 4, 5].map(s => (
                      <Ionicons key={s} name={s <= ticketSatisfaction.rating ? 'star' : 'star-outline'} size={12} color={colors.warningText} />
                    ))}
                  </View>
                </View>
                {ticketSatisfaction.comment && (
                  <Text style={{ fontSize: 11, color: C.muted, marginTop: 3 }}>"{ticketSatisfaction.comment}"</Text>
                )}
              </View>
            </View>
          )}

          {/* Survey Just Submitted */}
          {surveyDone && !ticketSatisfaction && (
            <View style={{ backgroundColor: colors.successSoft, borderRadius: 14, padding: 20, marginTop: 16, borderWidth: 1, borderColor: colors.successSoft, alignItems: 'center' }} data-testid="satisfaction-submitted" testID="satisfaction-submitted">
              <Ionicons name="heart" size={28} color={colors.successText} />
              <Text style={{ fontSize: 15, fontWeight: '800', color: C.text, marginTop: 8 }}>Thank you!</Text>
              <Text style={{ fontSize: 12, color: C.muted, marginTop: 4, textAlign: 'center' }}>Your feedback helps us serve you better.</Text>
            </View>
          )}

          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 14, marginTop: 14, borderWidth: 1, borderColor: C.border }} data-testid="ticket-activity-timeline" testID="ticket-activity-timeline">
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <Text style={{ fontSize: 12, fontWeight: '800', color: C.text, textTransform: 'uppercase', letterSpacing: 0.7 }}>Activity Timeline</Text>
              <Text style={{ fontSize: 11, color: C.muted }} data-testid="ticket-unread-count" testID="ticket-unread-count">Unread: {selectedTicket.unread_count || 0}</Text>
            </View>
            {(selectedTicket.history || []).length === 0 ? (
              <Text style={{ fontSize: 12, color: C.muted }} data-testid="timeline-empty" testID="timeline-empty">No timeline events yet.</Text>
            ) : (
              (selectedTicket.history || []).slice().reverse().slice(0, 8).map((entry, idx) => (
                <View key={`${entry.at}-${idx}`} style={{ flexDirection: 'row', gap: 10, marginBottom: 10 }} data-testid={`timeline-item-${idx}`} testID={`timeline-item-${idx}`}>
                  <View style={{ width: 10, alignItems: 'center' }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.primary, marginTop: 4 }} />
                    {idx < Math.min((selectedTicket.history || []).length, 8) - 1 ? <View style={{ width: 1.5, flex: 1, backgroundColor: C.border, marginTop: 3 }} /> : null}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{(entry.action || 'updated').replace(/_/g, ' ')}</Text>
                    <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{entry.note || 'No note'}</Text>
                    <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>{entry.by_name || 'System'} • {formatDate(entry.at)}</Text>
                  </View>
                </View>
              ))
            )}
          </View>

          {/* Reopen */}
          {canReopen && (
            <TouchableOpacity data-testid="reopen-ticket-btn" testID="reopen-ticket-btn"
              style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.warning, '35'), backgroundColor: (globalThis as any).__alphaColor(C.warning, '08'), marginTop: 12 }}
              onPress={handleReopen}>
              <Ionicons name="refresh" size={16} color={C.warningText} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: C.warningText }}>Reopen Ticket</Text>
            </TouchableOpacity>
          )}
          {!canReply && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.bgSoft, borderRadius: 12, padding: 14, marginTop: 12 }}>
              <Ionicons name="information-circle" size={18} color={C.muted} />
              <Text style={{ fontSize: 12, color: C.muted, flex: 1 }}>This ticket is {selectedTicket.status}. Reopen it to continue.</Text>
            </View>
          )}
        </ScrollView>

        {/* Reply Input Bar */}
        {canReply && (
          <View style={{
            position: 'absolute', bottom: 0, left: 0, right: 0,
            backgroundColor: C.card, borderTopWidth: 1, borderTopColor: C.border,
            paddingHorizontal: isWide ? 24 : 12, paddingVertical: 10,
            ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
          }}>
            {/* Pending reply files */}
            {replyPendingFiles.length > 0 && (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8, maxWidth: 960, alignSelf: 'center', width: '100%' }}>
                {replyPendingFiles.map((pf, idx) => (
                  <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.bgSoft, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5, borderWidth: 1, borderColor: C.border }}>
                    <Ionicons name="document-attach" size={12} color={C.primary} />
                    <Text style={{ fontSize: 10, color: C.text, maxWidth: 100 }} numberOfLines={1}>{pf.name}</Text>
                    <TouchableOpacity accessibilityLabel="close circle button" onPress={() => setReplyPendingFiles(prev => prev.filter((_, i) => i !== idx))}>
                      <Ionicons name="close-circle" size={14} color={C.error} />
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
            )}
            <View style={{ maxWidth: 960, alignSelf: 'center', width: '100%', flexDirection: isCompact ? 'column' : 'row', justifyContent: 'space-between', alignItems: isCompact ? 'stretch' : 'center', gap: 8, marginBottom: 8 }} data-testid="reply-ai-toolbar" testID="reply-ai-toolbar">
              <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                {(['professional', 'empathetic', 'concise'] as const).map((tone) => {
                  const active = aiTone === tone;
                  const toneLabel = tone === 'professional'
                    ? tx('myTickets.aiDraft.tone.professional', 'Professional')
                    : tone === 'empathetic'
                      ? tx('myTickets.aiDraft.tone.empathetic', 'Empathetic')
                      : tx('myTickets.aiDraft.tone.concise', 'Concise');
                  return (
                    <TouchableOpacity
                      key={tone}
                      data-testid={`reply-ai-tone-${tone}`}
                      testID={`reply-ai-tone-${tone}`}
                      style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.primary, '66') : C.border, backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '18') : C.bgSoft }}
                      onPress={() => setAiTone(tone)}
                    >
                      <Text style={{ fontSize: 10, fontWeight: '700', color: active ? C.primary : C.muted }}>{toneLabel}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
              <TouchableOpacity
                data-testid="reply-ai-rewrite-btn"
                testID="reply-ai-rewrite-btn"
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '44'), backgroundColor: (globalThis as any).__alphaColor(C.primary, '12'), opacity: (!replyText.trim() || aiRewritingReply) ? 0.55 : 1, width: isCompact ? '100%' : undefined }}
                disabled={!replyText.trim() || aiRewritingReply}
                onPress={handleAiRewriteReply}
              >
                {aiRewritingReply ? <ActivityIndicator size="small" color={C.primary} /> : <Ionicons name="sparkles" size={13} color={C.primary} />}
                <Text style={{ fontSize: 11, fontWeight: '700', color: C.primary }}>{tx('myTickets.aiDraft.actions.rewriteShort', 'AI Rewrite')}</Text>
              </TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8, maxWidth: 960, alignSelf: 'center', width: '100%' }}>
              <TouchableOpacity data-testid="reply-attach-btn" testID="reply-attach-btn"
                style={{ width: 42, height: 42, borderRadius: 12, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border }}
                onPress={() => pickFiles(true)}>
                <Ionicons name="attach" size={20} color={C.primary} />
              </TouchableOpacity>
              <View style={{ flex: 1, backgroundColor: C.bgSoft, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 4, borderWidth: 1, borderColor: C.border }}>
                <TextInput data-testid="ticket-reply-input" testID="ticket-reply-input"
                  style={{ fontSize: 14, color: C.text, maxHeight: 100, minHeight: 40, paddingVertical: 10, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
                  placeholder="Type your reply..." placeholderTextColor={C.muted}
                  value={replyText} onChangeText={handleInputChange} multiline maxLength={2000}
                  onSubmitEditing={handleReply}
                />
              </View>
              <TouchableOpacity data-testid="ticket-reply-send-btn" testID="ticket-reply-send-btn"
                style={{
                  width: 42, height: 42, borderRadius: 12, backgroundColor: C.primary, alignItems: 'center', justifyContent: 'center',
                  opacity: ((!replyText.trim() && replyPendingFiles.length === 0) || replying) ? 0.4 : 1,
                  ...(Platform.OS === 'web' && replyText.trim() ? { boxShadow: `0 2px 10px ${C.primary}40` } as any : {}),
                }}
                onPress={handleReply} disabled={(!replyText.trim() && replyPendingFiles.length === 0) || replying}>
                {replying ? <ActivityIndicator size="small" color={C.primaryText} /> : <Ionicons name="send" size={18} color={C.primaryText} />}
              </TouchableOpacity>
            </View>
          </View>
        )}
      </View>
    );
  };

  // ══════════════════════════════════════════
  // ── MAIN RENDER ──
  // ══════════════════════════════════════════
  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
        {/* Header */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          paddingHorizontal: isWide ? 24 : 16, paddingVertical: 12,
          backgroundColor: C.card, borderBottomWidth: 1, borderBottomColor: C.border,
        }} data-testid="my-tickets-header" testID="my-tickets-header">
          <TouchableOpacity data-testid="tickets-back-btn" testID="tickets-back-btn"
            style={{ width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bgSoft }}
            onPress={() => {
              if (view === 'detail') { setView('list'); }
              else if (view === 'new') { setView('list'); }
              else { router.back(); }
            }}>
            <Ionicons name="arrow-back" size={20} color={C.text} />
          </TouchableOpacity>
          <View style={{ flex: 1, alignItems: 'center' }}>
            <Text style={{ fontSize: 17, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>
              {view === 'detail' ? (selectedTicket?.ticket_number || tt('Ticket')) : view === 'new' ? tt('New Ticket') : tt('Support Center')}
            </Text>
            {view === 'detail' && (
              <View data-testid="my-tickets-header-ws-status" testID="my-tickets-header-ws-status" style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 }}>
                <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: wsConnected ? colors.success : C.warn }} />
                <Text style={{ fontSize: 10, color: wsConnected ? colors.successText : C.warn, fontWeight: '600' }}>{wsConnected ? tt('Real-time connected') : tt('Realtime reconnecting')}</Text>
              </View>
            )}
          </View>
          {view === 'list' ? (
            <TouchableOpacity data-testid="new-ticket-header-btn" testID="new-ticket-header-btn"
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: C.primary }}
              onPress={() => setView('new')}>
              <Ionicons name="add" size={16} color={C.primaryText} />
              {isWide && <Text style={{ fontSize: 12, fontWeight: '700', color: C.primaryText }}>New Ticket</Text>}
            </TouchableOpacity>
          ) : (
            <View style={{ width: 40 }} />
          )}
        </View>

        {view === 'list' && renderTicketList()}
        {view === 'new' && renderNewTicket()}
        {view === 'detail' && renderTicketDetail()}
      </SafeAreaView>

      {/* Image Lightbox */}
      <Modal visible={!!lightboxUrl} transparent animationType="fade" onRequestClose={closeLightbox}>
        <Pressable style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.92)' /* @theme-ok lightbox always-dark backdrop */, justifyContent: 'center', alignItems: 'center' }} onPress={closeLightbox} data-testid="lightbox-overlay" testID="lightbox-overlay">
          <View style={{ position: 'absolute', top: 0, left: 0, right: 0, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, zIndex: 10 }}>
            <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '600', flex: 1 }} numberOfLines={1}>{lightboxName}</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity data-testid="lightbox-zoom-out" testID="lightbox-zoom-out" style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.12)' /* @theme-ok lightbox glass control */, alignItems: 'center', justifyContent: 'center' }}
                onPress={(e) => { e.stopPropagation?.(); setLightboxZoom(z => Math.max(0.5, z - 0.25)); }}>
                <Ionicons name="remove" size={20} color={C.primaryText} />
              </TouchableOpacity>
              <View style={{ paddingHorizontal: 8, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.12)' /* @theme-ok lightbox glass control */, alignItems: 'center', justifyContent: 'center' }}>
                <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '700' }}>{Math.round(lightboxZoom * 100)}%</Text>
              </View>
              <TouchableOpacity data-testid="lightbox-zoom-in" testID="lightbox-zoom-in" style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.12)' /* @theme-ok lightbox glass control */, alignItems: 'center', justifyContent: 'center' }}
                onPress={(e) => { e.stopPropagation?.(); setLightboxZoom(z => Math.min(4, z + 0.25)); }}>
                <Ionicons name="add" size={20} color={C.primaryText} />
              </TouchableOpacity>
              <TouchableOpacity data-testid="lightbox-download" testID="lightbox-download" style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.12)' /* @theme-ok lightbox glass control */, alignItems: 'center', justifyContent: 'center' }}
                onPress={(e) => { e.stopPropagation?.(); if (Platform.OS === 'web' && lightboxUrl) window.open(lightboxUrl, '_blank'); }}>
                <Ionicons name="download-outline" size={20} color={C.primaryText} />
              </TouchableOpacity>
              <TouchableOpacity data-testid="lightbox-close" testID="lightbox-close" style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.18)' /* @theme-ok lightbox glass control */, alignItems: 'center', justifyContent: 'center' }}
                onPress={closeLightbox}>
                <Ionicons name="close" size={22} color={C.primaryText} />
              </TouchableOpacity>
            </View>
          </View>
          <Pressable onPress={(e) => e.stopPropagation?.()} style={{ maxWidth: '90%', maxHeight: '80%' }}>
            {lightboxUrl && (
              <Image source={{ uri: lightboxUrl }} accessibilityLabel="Click outside or press X to close"
                style={{ width: width * 0.85 * lightboxZoom, height: (width * 0.85 * 0.65) * lightboxZoom, maxWidth: '100%' as any }}
                resizeMode="contain" />
            )}
          </Pressable>
          <View style={{ position: 'absolute', bottom: 20 }}>
            <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>Click outside or press X to close</Text>
          </View>
        </Pressable>
      </Modal>
    </AppShell>
  );
}
