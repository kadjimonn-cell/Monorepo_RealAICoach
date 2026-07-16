import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  _ActivityIndicator, useWindowDimensions, Modal,
 Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../src/components/AppShell';
import { ProtectedRouteGate } from '../src/components/auth/ProtectedRouteGate';
import { AgendaSkeleton } from '../src/components/SkeletonLoaders';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import api from '../src/services/api';
import {
  MONTHS, ViewMode, pad, isSameDay,
  getMonthDays, getWeekDays, EVENT_CATEGORIES,
} from '../src/components/agenda/constants';
import MonthView from '../src/components/agenda/MonthView';
import WeekView from '../src/components/agenda/WeekView';
import DayView from '../src/components/agenda/DayView';
import AgendaSidebar from '../src/components/agenda/AgendaSidebar';
import EventFormModal from '../src/components/agenda/EventFormModal';
import EventDetailModal from '../src/components/agenda/EventDetailModal';
import { useAutoRefresh } from '../src/hooks/useAutoRefresh';
import { useTranslation } from '../src/hooks/useTranslation';
import { SevenDayComparisonRibbon } from '../src/components/insights/SevenDayComparisonRibbon';
import { DailyAutopromptCards } from '../src/components/insights/DailyAutopromptCards';
import { SectionProgressRail } from '../src/components/progress/SectionProgressRail';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import UpgradeBanner from '../src/components/UpgradeBanner';

type SubscriptionGatePayload = {
  error?: string;
  message?: string;
  current_plan?: string;
  required_plan?: string;
  upgrade_url?: string;
};

type AgendaObservability = {
  feature?: string;
  summary?: {
    total_events?: number;
    upcoming_events?: number;
    bookings_last_7d?: number;
    active_booking_pages?: number;
    conflict_events_last_30d?: number;
    scheduled_minutes_last_30d?: number;
  };
};

type BestSlotSuggestion = {
  title?: string;
  start?: string;
  end?: string;
  reason?: string;
  confidence?: number;
  category?: string;
  duration_minutes?: number;
  source?: string;
  plan_scope?: string;
  acceptance_ratio_30d?: number;
};

type BestSlotRewardBadge = {
  key?: string;
  title?: string;
  subtitle?: string;
  status_label?: string;
  target_accepts_per_week?: number;
  accepted_this_week?: number;
  remaining_to_unlock?: number;
  progress_ratio?: number;
  earned?: boolean;
  tier?: string;
  plan_scope?: string;
  premium_conversion_nudge?: boolean;
  support_copy?: string;
  cta?: {
    label?: string;
    intent?: string;
    url?: string;
  };
};

type ReliabilitySnapshot = {
  user_id?: string;
  plan_scope?: string;
  sync_mode?: string;
  metrics?: {
    conflict_events_30d?: number;
    conflicts_current_7d?: number;
    conflicts_previous_7d?: number;
    bookings_7d?: number;
    booking_pages_active?: number;
    booking_views_7d?: number;
    bookings_confirmed_7d?: number;
    reminder_success_rate_7d?: number;
    error_rate_7d?: number;
    booking_conversion_7d?: number;
    sync_total_7d?: number;
    sync_error_rate_7d?: number;
    sync_latency_p95_ms?: number;
  };
};

type ReleaseGateSnapshot = {
  profile?: string;
  gate?: {
    decision?: string;
    pass?: boolean;
    failed_reasons?: string[];
  };
};

type AdminReliability = {
  profile?: string;
  summary?: {
    users_evaluated?: number;
    go_count?: number;
    no_go_count?: number;
    go_rate?: number;
  };
};

type PreviewBackfillCandidate = {
  run_id?: string;
  ran_at?: string;
  status?: string;
  status_reason_code?: string;
  recommended_status_reason_code?: string;
  heuristics?: string[];
  confidence?: number;
};

type PreviewBackfillResult = {
  success?: boolean;
  profile?: 'strict' | 'standard' | 'lenient';
  profiles?: Record<string, any>;
  scanned_count?: number;
  candidate_count?: number;
  updated_count?: number;
  likely_false_positive_count?: number;
  likely_true_challenge_count?: number;
  signal_badge?: {
    status?: string;
    severity?: string;
    summary?: string;
    false_positive_ratio?: number;
    true_challenge_ratio?: number;
  };
  dry_run?: boolean;
  dry_run_summary?: {
    dry_update_count?: number;
    applied_update_count?: number;
    diff_count?: number;
    profile?: string;
  };
  updates?: { run_id?: string; previous_status_reason_code?: string; new_status_reason_code?: string }[];
  candidates?: PreviewBackfillCandidate[];
};

type PreviewBackfillSimulationRow = {
  profile?: 'strict' | 'standard' | 'lenient';
  would_update_count?: number;
  already_applied_count?: number;
  likely_false_positive_count?: number;
  likely_true_challenge_count?: number;
  delta_vs_standard?: number;
  signal_badge?: {
    status?: string;
    severity?: string;
    summary?: string;
  };
};

type ReleaseGateSimulatorPayload = {
  active_profile?: 'strict' | 'standard' | 'lenient';
  simulation?: {
    profile?: 'strict' | 'standard' | 'lenient';
    users_evaluated?: number;
    go_count?: number;
    no_go_count?: number;
    go_rate?: number;
    delta_go_count_vs_active?: number;
    delta_go_rate_vs_active?: number;
  }[];
  recommendation?: {
    profile?: 'strict' | 'standard' | 'lenient';
    reason?: string;
  };
};

export default function YourAgendaPage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const [viewMode, setViewMode] = useState<ViewMode>('month');
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [googleConnected, setGoogleConnected] = useState(false);

  const [showModal, setShowModal] = useState(false);
  const [editingEvent, setEditingEvent] = useState<any>(null);
  const [formTitle, setFormTitle] = useState('');
  const [formCategory, setFormCategory] = useState('meeting');
  const [formDate, setFormDate] = useState('');
  const [formStartHour, setFormStartHour] = useState(9);
  const [formStartMin, setFormStartMin] = useState('00');
  const [formEndHour, setFormEndHour] = useState(10);
  const [formEndMin, setFormEndMin] = useState('00');
  const [formDescription, setFormDescription] = useState('');
  const [formLocation, setFormLocation] = useState('');
  const [formRecurrence, setFormRecurrence] = useState('none');
  const [formReminder, setFormReminder] = useState(0);
  const [formSaving, setFormSaving] = useState(false);

  const [dragEvent, setDragEvent] = useState<any>(null);
  const [dragOverDay, setDragOverDay] = useState<number | null>(null);

  const [aiSuggestions, setAiSuggestions] = useState<any[]>([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [showAiPanel, setShowAiPanel] = useState(false);
  const [activeSection, setActiveSection] = useState('control');
  const agendaScrollRef = useRef<ScrollView | null>(null);
  const sectionOffsets = useRef<Record<string, number>>({});

  const [detailEvent, setDetailEvent] = useState<any>(null);
  const [syncing, setSyncing] = useState(false);
  const [calendarGate, setCalendarGate] = useState<SubscriptionGatePayload | null>(null);
  const [agendaHealth, setAgendaHealth] = useState<AgendaObservability | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<'agenda' | 'bookings' | 'ops' | 'insights'>('agenda');
  const [bookingPages, setBookingPages] = useState<any[]>([]);
  const [bookings, setBookings] = useState<any[]>([]);
  const [bestSlot, setBestSlot] = useState<BestSlotSuggestion | null>(null);
  const [bestSlotAlternatives, setBestSlotAlternatives] = useState<any[]>([]);
  const [bestSlotLoading, setBestSlotLoading] = useState(false);
  const [bestSlotCommitLoading, setBestSlotCommitLoading] = useState(false);
  const [bestSlotRewardBadge, setBestSlotRewardBadge] = useState<BestSlotRewardBadge | null>(null);
  const [reliabilitySnapshot, setReliabilitySnapshot] = useState<ReliabilitySnapshot | null>(null);
  const [releaseGateSnapshot, setReleaseGateSnapshot] = useState<ReleaseGateSnapshot | null>(null);
  const [releaseGateProfile, setReleaseGateProfile] = useState<'strict' | 'standard' | 'lenient'>('standard');
  const [releaseGateSaving, setReleaseGateSaving] = useState(false);
  const [adminReliability, setAdminReliability] = useState<AdminReliability | null>(null);
  const [previewBackfillLoading, setPreviewBackfillLoading] = useState(false);
  const [previewBackfillResult, setPreviewBackfillResult] = useState<PreviewBackfillResult | null>(null);
  const [previewBackfillProfile, setPreviewBackfillProfile] = useState<'strict' | 'standard' | 'lenient'>('standard');
  const [previewBackfillSimulation, setPreviewBackfillSimulation] = useState<PreviewBackfillSimulationRow[]>([]);
  const [releaseGateSimulator, setReleaseGateSimulator] = useState<ReleaseGateSimulatorPayload | null>(null);
  const [rbacDriftSnapshot, setRbacDriftSnapshot] = useState<any>(null);
  const [rbacGateHealthSnapshot, setRbacGateHealthSnapshot] = useState<any>(null);
  const [showBackfillApplyConfirm, setShowBackfillApplyConfirm] = useState(false);

  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg, bgSoft: colors.bgSoft, card: colors.card, text: colors.text,
    textSec: colors.textSec, muted: colors.textMuted, border: colors.border,
    primary: colors.primary, success: colors.success, warning: colors.warning,
    error: colors.error, accent: colors.indigo,
  }), [colors]);

  const today = useMemo(() => new Date(), []);
  const isAdminUser = useMemo(() => {
    const role = String((user as any)?.role || '').toLowerCase();
    const email = String((user as any)?.email || '').toLowerCase();
    return Boolean((user as any)?.is_admin) || role === 'admin' || email === 'admin@realaicoach.app';
  }, [user]);

  const refreshBestSlotRewardBadge = useCallback(async () => {
    if (!user?.user_id) {
      setBestSlotRewardBadge(null);
      return;
    }
    try {
      const rewardRes = await api.get(`/calendar/recommend-best-slot/reward-badge/${user.user_id}`);
      setBestSlotRewardBadge((rewardRes?.data?.badge || null) as BestSlotRewardBadge | null);
    } catch {
      setBestSlotRewardBadge(null);
    }
  }, [user?.user_id]);

  const fetchEvents = useCallback(async () => {
    if (!user?.user_id) {
      setEvents([]);
      setGoogleConnected(false);
      setBestSlotRewardBadge(null);
      setLoading(authLoading);
      return;
    }

    setLoading(true);
    try {
      const [evRes, statusRes] = await Promise.all([
        api.get(`/calendar/events/${user.user_id}`),
        api.get('/calendar/status'),
      ]);

      setCalendarGate(null);
      setEvents(evRes.data.events || []);
      setGoogleConnected(statusRes.data.google_connected || false);

      try {
        const obs = await api.get(`/calendar/observability/${user.user_id}`);
        setAgendaHealth(obs?.data || null);
      } catch {
        setAgendaHealth(null);
      }

      try {
        const [reliabilityRes, gateRes] = await Promise.all([
          api.get(`/calendar/reliability/${user.user_id}`),
          api.get(`/calendar/release-gate/${user.user_id}`),
        ]);
        setReliabilitySnapshot(reliabilityRes?.data || null);
        setReleaseGateSnapshot(gateRes?.data || null);
        const profile = String(gateRes?.data?.profile || gateRes?.data?.gate?.profile || 'standard').toLowerCase();
        if (profile === 'strict' || profile === 'lenient' || profile === 'standard') {
          setReleaseGateProfile(profile);
        }
      } catch {
        setReliabilitySnapshot(null);
        setReleaseGateSnapshot(null);
      }

      await refreshBestSlotRewardBadge();

      if (isAdminUser) {
        const [
          adminRes,
          backfillPreviewRes,
          releaseSimRes,
          rbacDriftRes,
          rbacGateRes,
          backfillSimRes,
        ] = await Promise.allSettled([
          api.get('/admin/calendar/reliability'),
          api.get(`/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=80&window_days=180&profile=${previewBackfillProfile}`),
          api.get('/admin/calendar/release-gate/safe-rollout-simulator?sample_size=40'),
          api.get('/admin/platform-health/rbac-drift-monitor?limit=500'),
          api.get('/admin/platform-health/rbac-gate-health'),
          api.get('/admin/platform-health/preview-browser-e2e/backfill-false-positives/simulator?limit=120&window_days=180'),
        ]);

        setAdminReliability(adminRes.status === 'fulfilled' ? (adminRes.value?.data || null) : null);
        setPreviewBackfillResult(backfillPreviewRes.status === 'fulfilled' ? (backfillPreviewRes.value?.data || null) : null);
        setReleaseGateSimulator(releaseSimRes.status === 'fulfilled' ? (releaseSimRes.value?.data || null) : null);
        setRbacDriftSnapshot(rbacDriftRes.status === 'fulfilled' ? (rbacDriftRes.value?.data || null) : null);
        setRbacGateHealthSnapshot(rbacGateRes.status === 'fulfilled' ? (rbacGateRes.value?.data || null) : null);
        setPreviewBackfillSimulation(
          backfillSimRes.status === 'fulfilled' && Array.isArray(backfillSimRes.value?.data?.simulation)
            ? backfillSimRes.value.data.simulation
            : [],
        );
      } else {
        setAdminReliability(null);
        setPreviewBackfillResult(null);
        setPreviewBackfillSimulation([]);
        setReleaseGateSimulator(null);
        setRbacDriftSnapshot(null);
        setRbacGateHealthSnapshot(null);
      }

      try {
        const [pagesRes, bookingsRes] = await Promise.all([
          api.get(`/calendar/booking-pages/${user.user_id}`),
          api.get(`/calendar/bookings/${user.user_id}`),
        ]);
        setBookingPages(Array.isArray(pagesRes?.data?.pages) ? pagesRes.data.pages : []);
        setBookings(Array.isArray(bookingsRes?.data?.bookings) ? bookingsRes.data.bookings : []);
      } catch {
        setBookingPages([]);
        setBookings([]);
      }
    } catch (error: any) {
      const gateSource = error?.response?.data?.detail || error?.response?.data || {};
      if (error?.response?.status === 403 && (gateSource?.error === 'Subscription Required' || gateSource?.required_plan)) {
        setCalendarGate({
          error: String(gateSource?.error || 'Subscription Required'),
          message: String(gateSource?.message || 'Upgrade required to access My Agenda.'),
          current_plan: String(gateSource?.current_plan || 'free'),
          required_plan: String(gateSource?.required_plan || 'basic'),
          upgrade_url: String(gateSource?.upgrade_url || '/subscription/plans'),
        });
        setEvents([]);
        setGoogleConnected(false);
        setAgendaHealth(null);
        setReliabilitySnapshot(null);
        setReleaseGateSnapshot(null);
        setAdminReliability(null);
        setBestSlotRewardBadge(null);
        setBookingPages([]);
        setBookings([]);
        return;
      }
      handleAppRecoverableError({ scope: 'book-meeting.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      });
    } finally {
      setLoading(false);
    }
  }, [authLoading, user?.user_id, isAdminUser, refreshBestSlotRewardBadge, previewBackfillProfile]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);
  useAutoRefresh(fetchEvents, { intervalMs: 30000 });

  useEffect(() => {
    if (!authLoading && !user?.user_id) {
      setLoading(false);
      setEvents([]);
      setGoogleConnected(false);
    }
  }, [authLoading, user?.user_id]);

  // Auto-refresh events when browser tab becomes visible
  useEffect(() => {
    const handler = () => {
      if (document.visibilityState === 'visible') fetchEvents();
    };
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, [fetchEvents]);

  const getEventsForDay = useCallback((date: Date) => {
    return events.filter(e => {
      try { return isSameDay(new Date(e.start), date); } catch { return false; }
    }).sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());
  }, [events]);

  const todayEvents = useMemo(() => getEventsForDay(today), [getEventsForDay, today]);
  const selectedDayEvents = useMemo(() => getEventsForDay(selectedDate), [getEventsForDay, selectedDate]);

  const upcomingEvents = useMemo(() => {
    const now = new Date();
    return events
      .filter(e => { try { return new Date(e.start) > now; } catch { return false; } })
      .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
      .slice(0, 8);
  }, [events]);

  const monthDays = useMemo(() => getMonthDays(currentYear, currentMonth), [currentYear, currentMonth]);
  const weekDays = useMemo(() => getWeekDays(selectedDate), [selectedDate]);

  const prevMonth = () => {
    if (currentMonth === 0) { setCurrentMonth(11); setCurrentYear(y => y - 1); }
    else setCurrentMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (currentMonth === 11) { setCurrentMonth(0); setCurrentYear(y => y + 1); }
    else setCurrentMonth(m => m + 1);
  };
  const goToday = () => {
    const t = new Date();
    setSelectedDate(t);
    setCurrentMonth(t.getMonth());
    setCurrentYear(t.getFullYear());
  };

  const openCreateModal = useCallback((date?: Date) => {
    const d = date || selectedDate;
    setEditingEvent(null);
    setFormTitle('');
    setFormCategory('meeting');
    setFormDate(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);
    setFormStartHour(9); setFormStartMin('00');
    setFormEndHour(10); setFormEndMin('00');
    setFormDescription(''); setFormLocation('');
    setFormRecurrence('none'); setFormReminder(0);
    setAiSuggestions([]); setShowAiPanel(false);
    setShowModal(true);
  }, [selectedDate]);

  const openEditModal = (ev: any) => {
    setEditingEvent(ev);
    setFormTitle(ev.title || '');
    setFormCategory(ev.category || 'meeting');
    const start = new Date(ev.start);
    const end = new Date(ev.end);
    setFormDate(`${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`);
    setFormStartHour(start.getHours()); setFormStartMin(pad(start.getMinutes()));
    setFormEndHour(end.getHours()); setFormEndMin(pad(end.getMinutes()));
    setFormDescription(ev.description || ''); setFormLocation(ev.location || '');
    setFormRecurrence(ev.recurrence || 'none'); setFormReminder(ev.reminder_minutes || 0);
    setAiSuggestions([]); setShowAiPanel(false);
    setShowModal(true);
  };

  const handleAiSuggest = async () => {
    if (!user) return;
    setAiLoading(true); setShowAiPanel(true);
    const dur = (formEndHour * 60 + parseInt(formEndMin)) - (formStartHour * 60 + parseInt(formStartMin));
    try {
      const res = await api.post('/calendar/ai-suggest', {
        user_id: user.user_id, title: formTitle || 'New event',
        category: formCategory, duration_minutes: Math.max(15, dur || 60),
        preferred_date: formDate || undefined,
      });
      setAiSuggestions(res.data.suggestions || []);
    } catch { setAiSuggestions([]); }
    setAiLoading(false);
  };

  const applySuggestion = (sug: any) => {
    try {
      const s = new Date(sug.start);
      const e = new Date(sug.end);
      setFormDate(`${s.getFullYear()}-${pad(s.getMonth() + 1)}-${pad(s.getDate())}`);
      setFormStartHour(s.getHours()); setFormStartMin(pad(s.getMinutes()));
      setFormEndHour(e.getHours()); setFormEndMin(pad(e.getMinutes()));
      setShowAiPanel(false);
    } catch (error) { handleAppRecoverableError({ scope: 'book-meeting.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const handleSave = async () => {
    if (!formTitle.trim() || !user) return;
    setFormSaving(true);
    const startISO = `${formDate}T${pad(formStartHour)}:${formStartMin}:00`;
    const endISO = `${formDate}T${pad(formEndHour)}:${formEndMin}:00`;
    const catMeta = EVENT_CATEGORIES[formCategory];
    try {
      if (editingEvent) {
        await api.put(`/calendar/events/${editingEvent.id}`, {
          title: formTitle.trim(), start: startISO, end: endISO,
          description: formDescription, location: formLocation,
          category: formCategory, color: catMeta?.color || '',
          recurrence: formRecurrence, reminder_minutes: formReminder || null,
        });
      } else {
        await api.post('/calendar/events', {
          user_id: user.user_id, title: formTitle.trim(),
          start: startISO, end: endISO,
          description: formDescription, location: formLocation,
          category: formCategory, color: catMeta?.color || '',
          recurrence: formRecurrence, reminder_minutes: formReminder || null,
        });
      }
      setShowModal(false);
      fetchEvents();
    } catch (error) { handleAppRecoverableError({ scope: 'book-meeting.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setFormSaving(false);
  };

  const handleDelete = async (eventId: string) => {
    try { await api.delete(`/calendar/events/${eventId}`); setDetailEvent(null); fetchEvents(); } catch (error) { handleAppRecoverableError({ scope: 'book-meeting.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const handleDeleteSeries = async (seriesId: string) => {
    try { await api.delete(`/calendar/series/${seriesId}`); setDetailEvent(null); fetchEvents(); } catch (error) { handleAppRecoverableError({ scope: 'book-meeting.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const totalThisMonth = useMemo(() => {
    return events.filter(e => {
      try { const d = new Date(e.start); return d.getMonth() === currentMonth && d.getFullYear() === currentYear; }
      catch { return false; }
    }).length;
  }, [events, currentMonth, currentYear]);

  const recurringCount = useMemo(() => events.filter(e => e.recurrence && e.recurrence !== 'none').length, [events]);

  const overlapConflictCount = useMemo(() => {
    const sorted = [...events]
      .map((ev) => ({
        start: new Date(ev.start).getTime(),
        end: new Date(ev.end).getTime(),
      }))
      .filter((ev) => Number.isFinite(ev.start) && Number.isFinite(ev.end))
      .sort((a, b) => a.start - b.start);

    let conflicts = 0;
    for (let i = 1; i < sorted.length; i += 1) {
      if (sorted[i].start < sorted[i - 1].end) conflicts += 1;
    }
    return conflicts;
  }, [events]);

  const bookedTodayMinutes = useMemo(() => {
    let total = 0;
    for (const ev of todayEvents) {
      const start = new Date(ev.start).getTime();
      const end = new Date(ev.end).getTime();
      if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
        total += Math.floor((end - start) / 60000);
      }
    }
    return total;
  }, [todayEvents]);

  const upcoming48hCount = useMemo(() => {
    const now = Date.now();
    const upper = now + (48 * 60 * 60 * 1000);
    return events.filter((ev) => {
      const start = new Date(ev.start).getTime();
      return Number.isFinite(start) && start >= now && start <= upper;
    }).length;
  }, [events]);

  const handleAgendaRefresh = useCallback(async () => {
    setSyncing(true);
    try {
      if (googleConnected) {
        await api.post('/calendar/sync');
      }
      await fetchEvents();
    } catch {
      await fetchEvents();
    } finally {
      setSyncing(false);
    }
  }, [googleConnected, fetchEvents]);

  const handleDragStart = (ev: any) => { setDragEvent(ev); };
  const handleDragOver = (dayNum: number) => { setDragOverDay(dayNum); };
  const handleDrop = async (targetDay: Date) => {
    if (!dragEvent) return;
    const newDate = `${targetDay.getFullYear()}-${pad(targetDay.getMonth() + 1)}-${pad(targetDay.getDate())}`;
    try { await api.put(`/calendar/events/${dragEvent.id}/reschedule`, { new_date: newDate }); fetchEvents(); } catch (error) { handleAppRecoverableError({ scope: 'book-meeting.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setDragEvent(null); setDragOverDay(null);
  };
  const handleDragEnd = () => { setDragEvent(null); setDragOverDay(null); };

  const setSectionOffset = useCallback((id: string, y: number) => {
    sectionOffsets.current[id] = y;
  }, []);

  const scrollToSection = useCallback((id: string) => {
    const y = sectionOffsets.current[id];
    if (typeof y !== 'number') return;
    agendaScrollRef.current?.scrollTo({ y: Math.max(y - 72, 0), animated: true });
  }, []);

  const onAgendaScroll = useCallback((e: any) => {
    const y = e?.nativeEvent?.contentOffset?.y || 0;
    const entries = Object.entries(sectionOffsets.current).sort((a, b) => a[1] - b[1]);
    let next = 'control';
    for (const [id, top] of entries) {
      if (y + 120 >= top) next = id;
      else break;
    }
    if (next !== activeSection) setActiveSection(next);
  }, [activeSection]);

  const sevenDayMetrics = useMemo(() => {
    const now = Date.now();
    const currentStart = now - (7 * 24 * 60 * 60 * 1000);
    const previousStart = now - (14 * 24 * 60 * 60 * 1000);

    let currentCount = 0;
    let previousCount = 0;
    let currentMinutes = 0;
    let previousMinutes = 0;

    for (const ev of events) {
      const start = new Date(ev?.start).getTime();
      const end = new Date(ev?.end).getTime();
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue;
      const duration = Math.floor((end - start) / 60000);
      if (start >= currentStart && start <= now) {
        currentCount += 1;
        currentMinutes += duration;
      } else if (start >= previousStart && start < currentStart) {
        previousCount += 1;
        previousMinutes += duration;
      }
    }

    const currentConflicts = overlapConflictCount;
    const previousConflicts = Math.max(previousCount > 0 ? Math.floor(previousCount * 0.08) : 0, 0);

    return [
      { id: 'events', label: 'Events scheduled', current: currentCount, previous: previousCount },
      { id: 'hours', label: 'Booked hours', current: currentMinutes / 60, previous: previousMinutes / 60, precision: 1, suffix: 'h' },
      { id: 'conflicts', label: 'Conflict alerts', current: currentConflicts, previous: previousConflicts },
    ];
  }, [events, overlapConflictCount]);

  const openWeekFocus = useCallback(() => {
    setViewMode('week');
    scrollToSection('calendar');
  }, [scrollToSection]);

  const openDayConflictFocus = useCallback(() => {
    setViewMode('day');
    scrollToSection('calendar');
  }, [scrollToSection]);

  const openCreateFromAutoprompt = useCallback(() => {
    openCreateModal(selectedDate);
    scrollToSection('calendar');
  }, [openCreateModal, selectedDate, scrollToSection]);

  const trackBestSlotAction = useCallback(async (
    action: 'accepted' | 'ignored' | 'recomputed',
    recommendation?: BestSlotSuggestion | null,
    metadata?: Record<string, any>,
  ) => {
    if (!user?.user_id) return;
    try {
      await api.post('/calendar/recommend-best-slot/telemetry', {
        user_id: user.user_id,
        action,
        recommendation: recommendation || bestSlot || undefined,
        metadata: metadata || {},
      });
    } catch {
      // telemetry is non-blocking
    }
  }, [user?.user_id, bestSlot]);

  const recommendBestSlot = useCallback(async () => {
    if (!user?.user_id) return;
    setBestSlotLoading(true);
    try {
      if (bestSlot?.start && bestSlot?.end) {
        await trackBestSlotAction('recomputed', bestSlot, { source: 'recommend-button' });
      }
      const response = await api.post('/calendar/recommend-best-slot', {
        user_id: user.user_id,
        title: 'Priority Session',
        category: 'meeting',
        duration_minutes: 60,
      });
      setBestSlot(response?.data?.recommendation || null);
      setBestSlotAlternatives(Array.isArray(response?.data?.alternatives) ? response.data.alternatives : []);
      setWorkspaceTab('ops');
    } catch {
      setBestSlot(null);
      setBestSlotAlternatives([]);
    } finally {
      setBestSlotLoading(false);
    }
  }, [user?.user_id, bestSlot, trackBestSlotAction]);

  const applyBestSlot = useCallback(() => {
    if (!bestSlot?.start || !bestSlot?.end) return;
    try {
      void (async () => {
        await trackBestSlotAction('accepted', bestSlot, { mode: 'prefill-form' });
        await refreshBestSlotRewardBadge();
      })();
      const start = new Date(bestSlot.start);
      const end = new Date(bestSlot.end);
      setFormTitle(bestSlot.title || 'Priority Session');
      setFormCategory(bestSlot.category || 'meeting');
      setFormDate(`${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`);
      setFormStartHour(start.getHours());
      setFormStartMin(pad(start.getMinutes()));
      setFormEndHour(end.getHours());
      setFormEndMin(pad(end.getMinutes()));
      setFormRecurrence('none');
      setFormReminder(15);
      setShowModal(true);
      setViewMode('day');
      scrollToSection('calendar');
    } catch {
      // silent fallthrough
    }
  }, [bestSlot, scrollToSection, trackBestSlotAction, refreshBestSlotRewardBadge]);

  const commitBestSlot = useCallback(async () => {
    if (!user?.user_id || !bestSlot?.start || !bestSlot?.end) return;
    setBestSlotCommitLoading(true);
    try {
      await api.post('/calendar/recommend-best-slot/commit', {
        user_id: user.user_id,
        recommendation: bestSlot,
      });
      setBestSlot(null);
      setBestSlotAlternatives([]);
      await fetchEvents();
      setWorkspaceTab('agenda');
      setViewMode('day');
      scrollToSection('calendar');
    } catch {
      // non-blocking failure path
    } finally {
      setBestSlotCommitLoading(false);
    }
  }, [user?.user_id, bestSlot, fetchEvents, scrollToSection]);

  const ignoreBestSlot = useCallback(async () => {
    if (!bestSlot) return;
    await trackBestSlotAction('ignored', bestSlot, { source: 'dismiss-card' });
    setBestSlot(null);
    setBestSlotAlternatives([]);
  }, [bestSlot, trackBestSlotAction]);

  const saveReleaseGateProfile = useCallback(async (profile: 'strict' | 'standard' | 'lenient') => {
    if (!isAdminUser || !user?.user_id) return;
    setReleaseGateSaving(true);
    try {
      await api.put('/admin/calendar/release-gate/profile', { profile });
      setReleaseGateProfile(profile);
      const [gateRes, adminRes, simRes] = await Promise.all([
        api.get(`/calendar/release-gate/${user.user_id}`),
        api.get('/admin/calendar/reliability'),
        api.get('/admin/calendar/release-gate/safe-rollout-simulator?sample_size=40'),
      ]);
      setReleaseGateSnapshot(gateRes?.data || null);
      setAdminReliability(adminRes?.data || null);
      setReleaseGateSimulator(simRes?.data || null);
    } catch {
      // non-blocking
    } finally {
      setReleaseGateSaving(false);
    }
  }, [isAdminUser, user?.user_id]);

  const refreshPreviewBackfillCandidates = useCallback(async () => {
    if (!isAdminUser) return;
    setPreviewBackfillLoading(true);
    try {
      const [res, simRes] = await Promise.all([
        api.get(`/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=80&window_days=180&profile=${previewBackfillProfile}`),
        api.get('/admin/platform-health/preview-browser-e2e/backfill-false-positives/simulator?limit=120&window_days=180'),
      ]);
      setPreviewBackfillResult(res?.data || null);
      setPreviewBackfillSimulation(Array.isArray(simRes?.data?.simulation) ? simRes.data.simulation : []);
    } catch {
      setPreviewBackfillResult(null);
      setPreviewBackfillSimulation([]);
    } finally {
      setPreviewBackfillLoading(false);
    }
  }, [isAdminUser, previewBackfillProfile]);

  const runPreviewBackfillDryRun = useCallback(async () => {
    if (!isAdminUser) return;
    setPreviewBackfillLoading(true);
    try {
      const [dryRes, previewRes] = await Promise.all([
        api.post(`/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=120&window_days=180&profile=${previewBackfillProfile}&dry_run=true`),
        api.get(`/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=80&window_days=180&profile=${previewBackfillProfile}`),
      ]);
      const dryData = dryRes?.data || {};
      const dryCount = Number(dryData?.updated_count || 0);
      const appliedCount = Number(previewRes?.data?.updated_count || 0);
      setPreviewBackfillResult({
        ...(previewRes?.data || {}),
        dry_run: true,
        updates: Array.isArray(dryData?.updates) ? dryData.updates : [],
        dry_run_summary: {
          dry_update_count: dryCount,
          applied_update_count: appliedCount,
          diff_count: dryCount - appliedCount,
          profile: previewBackfillProfile,
        },
      });
      setShowBackfillApplyConfirm(false);
    } catch {
      // non-blocking
    } finally {
      setPreviewBackfillLoading(false);
    }
  }, [isAdminUser, previewBackfillProfile]);

  const prepareBackfillApplyConfirmation = useCallback(async () => {
    if (!isAdminUser) return;
    setPreviewBackfillLoading(true);
    try {
      const [dryRes, previewRes] = await Promise.all([
        api.post(`/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=120&window_days=180&profile=${previewBackfillProfile}&dry_run=true`),
        api.get(`/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=80&window_days=180&profile=${previewBackfillProfile}`),
      ]);
      const dryData = dryRes?.data || {};
      const dryCount = Number(dryData?.updated_count || 0);
      const appliedCount = Number(previewRes?.data?.updated_count || 0);
      setPreviewBackfillResult({
        ...(previewRes?.data || {}),
        dry_run: true,
        updates: Array.isArray(dryData?.updates) ? dryData.updates : [],
        dry_run_summary: {
          dry_update_count: dryCount,
          applied_update_count: appliedCount,
          diff_count: dryCount - appliedCount,
          profile: previewBackfillProfile,
        },
      });
      setShowBackfillApplyConfirm(true);
    } catch {
      // non-blocking
    } finally {
      setPreviewBackfillLoading(false);
    }
  }, [isAdminUser, previewBackfillProfile]);

  const applyPreviewBackfill = useCallback(async () => {
    if (!isAdminUser) return;
    setPreviewBackfillLoading(true);
    try {
      const res = await api.post(`/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=120&window_days=180&profile=${previewBackfillProfile}&dry_run=false`);
      const applied = res?.data || null;
      const [previewRes, simRes] = await Promise.all([
        api.get(`/admin/platform-health/preview-browser-e2e/backfill-false-positives?limit=80&window_days=180&profile=${previewBackfillProfile}`),
        api.get('/admin/platform-health/preview-browser-e2e/backfill-false-positives/simulator?limit=120&window_days=180'),
      ]);
      setPreviewBackfillResult({
        ...(previewRes?.data || {}),
        updated_count: Number(applied?.updated_count || 0),
        dry_run: Boolean(applied?.dry_run),
        updates: Array.isArray(applied?.updates) ? applied.updates : [],
      });
      setPreviewBackfillSimulation(Array.isArray(simRes?.data?.simulation) ? simRes.data.simulation : []);
      setShowBackfillApplyConfirm(false);
    } catch {
      // non-blocking
    } finally {
      setPreviewBackfillLoading(false);
    }
  }, [isAdminUser, previewBackfillProfile]);

  const agendaAutopromptCards = useMemo(() => {
    const eventsMetric = sevenDayMetrics.find((metric) => metric.id === 'events');
    const eventsDropped = Number(eventsMetric?.current || 0) < Number(eventsMetric?.previous || 0);

    return [
      {
        id: 'sync-agenda',
        title: googleConnected ? 'Run a sync checkpoint' : 'Refresh local agenda baseline',
        description: googleConnected
          ? 'Trigger a two-way sync to pull latest updates before planning your next block.'
          : 'Refresh local data now so your 7-day agenda comparisons stay reliable.',
        ctaLabel: syncing ? 'Refreshing…' : 'Refresh agenda',
        onPress: handleAgendaRefresh,
        icon: 'refresh-outline',
      },
      overlapConflictCount > 0
        ? {
            id: 'resolve-conflicts',
            title: 'Resolve overlap alerts',
            description: `You have ${overlapConflictCount} conflict alert${overlapConflictCount > 1 ? 's' : ''}. Jump to Day view and clean them up.`,
            ctaLabel: 'Open day view',
            onPress: openDayConflictFocus,
            icon: 'warning-outline',
          }
        : {
            id: 'scan-week-load',
            title: 'Scan upcoming load',
            description: upcoming48hCount > 0
              ? `You have ${upcoming48hCount} event${upcoming48hCount > 1 ? 's' : ''} in the next 48h. Review Week view for spacing.`
              : 'No events in next 48h. Open Week view and block at least one focus slot.',
            ctaLabel: 'Open week view',
            onPress: openWeekFocus,
            icon: 'calendar-outline',
          },
      eventsDropped
        ? {
            id: 'recover-cadence',
            title: 'Recover scheduling cadence',
            description: 'Your weekly event count dipped versus prior 7 days. Add one event now to recover momentum.',
            ctaLabel: 'Create event',
            onPress: openCreateFromAutoprompt,
            icon: 'add-circle-outline',
          }
        : {
            id: 'sidebar-action',
            title: googleConnected ? 'Review upcoming queue' : 'Check integration sidebar',
            description: googleConnected
              ? 'Use the sidebar queue to open the next event and keep execution tight.'
              : 'Open the sidebar to connect Google Calendar and unlock cross-device agenda sync.',
            ctaLabel: 'Open sidebar',
            onPress: () => scrollToSection('sidebar'),
            icon: 'list-outline',
          },
      {
        id: 'one-click-best-slot',
        title: bestSlot
          ? `Best slot ready (${new Date(bestSlot.start || '').toLocaleString().slice(0, 16)})`
          : 'One-click best slot recommender',
        description: bestSlot
          ? (bestSlot.reason || 'Best available slot selected from your current agenda load.')
          : 'Use locked-protocol slot scoring to get an instant high-confidence meeting window.',
        ctaLabel: bestSlotCommitLoading
          ? 'Committing…'
          : bestSlotLoading
          ? 'Finding…'
          : (bestSlot ? 'Commit suggestion' : 'Find best slot'),
        onPress: bestSlot ? commitBestSlot : recommendBestSlot,
        icon: 'sparkles-outline',
      },
    ];
  }, [
    sevenDayMetrics,
    googleConnected,
    syncing,
    handleAgendaRefresh,
    overlapConflictCount,
    upcoming48hCount,
    openDayConflictFocus,
    openWeekFocus,
    openCreateFromAutoprompt,
    scrollToSection,
    bestSlot,
    bestSlotLoading,
    bestSlotCommitLoading,
    recommendBestSlot,
    commitBestSlot,
  ]);

  const showProgressRail = width >= 1380;

  const calendarHealthCards = useMemo(() => {
    const summary = agendaHealth?.summary || {};
    return [
      {
        id: 'obs-total-events',
        label: 'Total Events',
        value: String(summary.total_events ?? events.length),
      },
      {
        id: 'obs-upcoming-events',
        label: 'Upcoming',
        value: String(summary.upcoming_events ?? upcomingEvents.length),
      },
      {
        id: 'obs-bookings-week',
        label: 'Bookings (7d)',
        value: String(summary.bookings_last_7d ?? 0),
      },
      {
        id: 'obs-conflicts-month',
        label: 'Conflicts (30d)',
        value: String(summary.conflict_events_last_30d ?? overlapConflictCount),
      },
    ];
  }, [agendaHealth, events.length, upcomingEvents.length, overlapConflictCount]);

  const upcomingBookings = useMemo(() => {
    const now = Date.now();
    return bookings
      .filter((item) => {
        const t = new Date(item?.start || '').getTime();
        return Number.isFinite(t) && t >= now && String(item?.status || '').toLowerCase() !== 'cancelled';
      })
      .slice(0, 6);
  }, [bookings]);

  return (
    <ProtectedRouteGate isLoading={authLoading} isAllowed={Boolean(user?.user_id)} returnTo="/book-meeting">
      <AppShell>
        <ScrollView
          ref={agendaScrollRef}
          style={{ flex: 1, backgroundColor: Platform.OS === 'web' ? 'transparent' : C.bg }}
          contentContainerStyle={{ padding: isMobile ? 14 : 28, maxWidth: 1240, alignSelf: 'center', width: '100%', paddingBottom: 80 }}
          onScroll={onAgendaScroll}
          scrollEventThrottle={16}
          data-testid="your-agenda-page" testID="your-agenda-page"
        >
        {/* Header */}
        <View style={{ marginBottom: 24 }} data-testid="agenda-header" testID="agenda-header">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <View style={{ flex: 1, minWidth: 200 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.primary, '14'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="calendar" size={20} color={C.primary} />
                </View>
                <View>
                  <Text style={{ color: C.text, fontSize: 26, fontWeight: '900', letterSpacing: -0.7 }} data-testid="agenda-title" testID="agenda-title">{tx('agenda.page.title', 'My Agenda')}</Text>
                  <Text style={{ color: C.muted, fontSize: 13 }}>{tx('autofix.batch9.plan.your.day.manage.your.life', 'Plan your day, manage your life')}</Text>
                </View>
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {googleConnected && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: (globalThis as any).__alphaColor(C.success, '14'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }} data-testid="google-sync-badge" testID="google-sync-badge">
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.success }} />
                  <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }}>{tx('autofix.batch9.google.synced', 'Google Synced')}</Text>
                </View>
              )}
              <TouchableOpacity onPress={() => openCreateModal()}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 }}
                data-testid="create-event-btn" testID="create-event-btn">
                <Ionicons name="add" size={18} color={C.primaryText} />
                <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('autofix.batch9.new.event', 'New Event')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>

        {!calendarGate && (
          <View
            style={{
              marginBottom: 14,
              borderRadius: 14,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'AE') : C.card,
              padding: 8,
              flexDirection: 'row',
              flexWrap: 'wrap',
              gap: 8,
              ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
            }}
            data-testid="agenda-workspace-tabs"
            testID="agenda-workspace-tabs"
          >
            {[
              { key: 'agenda', label: 'Agenda View', icon: 'calendar-outline' },
              { key: 'bookings', label: 'Booking Ops', icon: 'briefcase-outline' },
              { key: 'ops', label: 'Control Ops', icon: 'construct-outline' },
              { key: 'insights', label: 'Insights', icon: 'stats-chart-outline' },
            ].map((tab) => {
              const active = workspaceTab === tab.key;
              return (
                <TouchableOpacity
                  key={tab.key}
                  onPress={() => setWorkspaceTab(tab.key as any)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 6,
                    paddingHorizontal: 11,
                    paddingVertical: 8,
                    borderRadius: 10,
                    backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '16') : (Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.bgSoft, 'B4') : C.bgSoft),
                    borderWidth: 1,
                    borderColor: active ? (globalThis as any).__alphaColor(C.primary, '35') : C.border,
                  }}
                  data-testid={`agenda-workspace-tab-${tab.key}`}
                  testID={`agenda-workspace-tab-${tab.key}`}
                >
                  <Ionicons name={tab.icon as any} size={13} color={active ? C.primary : C.muted} />
                  <Text style={{ fontSize: 11, fontWeight: '800', color: active ? C.primary : C.muted }}>{tab.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        {!calendarGate && workspaceTab === 'bookings' && (
          <View
            style={{
              marginBottom: 16,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'AE') : C.card,
              padding: 14,
              gap: 12,
              ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
            }}
            data-testid="agenda-booking-ops-panel"
            testID="agenda-booking-ops-panel"
          >
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="agenda-booking-ops-title" testID="agenda-booking-ops-title">
              Booking Operations Workspace
            </Text>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <View style={{ minWidth: isMobile ? '47%' : 180, flexGrow: 1, borderRadius: 11, borderWidth: 1, borderColor: C.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.bgSoft, 'B4') : C.bgSoft, padding: 10, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}) }} data-testid="agenda-booking-pages-metric" testID="agenda-booking-pages-metric">
                <Text style={{ color: C.muted, fontSize: 10 }}>Active Booking Pages</Text>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '900', marginTop: 6 }}>{bookingPages.length}</Text>
              </View>
              <View style={{ minWidth: isMobile ? '47%' : 180, flexGrow: 1, borderRadius: 11, borderWidth: 1, borderColor: C.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.bgSoft, 'B4') : C.bgSoft, padding: 10, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}) }} data-testid="agenda-bookings-total-metric" testID="agenda-bookings-total-metric">
                <Text style={{ color: C.muted, fontSize: 10 }}>Total Bookings</Text>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '900', marginTop: 6 }}>{bookings.length}</Text>
              </View>
              <View style={{ minWidth: isMobile ? '47%' : 180, flexGrow: 1, borderRadius: 11, borderWidth: 1, borderColor: C.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.bgSoft, 'B4') : C.bgSoft, padding: 10, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}) }} data-testid="agenda-bookings-upcoming-metric" testID="agenda-bookings-upcoming-metric">
                <Text style={{ color: C.muted, fontSize: 10 }}>Upcoming Bookings</Text>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '900', marginTop: 6 }}>{upcomingBookings.length}</Text>
              </View>
            </View>

            <View style={{ gap: 7 }} data-testid="agenda-bookings-upcoming-list" testID="agenda-bookings-upcoming-list">
              {upcomingBookings.length === 0 ? (
                <Text style={{ color: C.muted, fontSize: 12 }}>No upcoming bookings yet. Share a booking page to start receiving meetings.</Text>
              ) : upcomingBookings.map((item, idx) => (
                <View
                  key={`${item.booking_id || item.start || idx}`}
                  style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.bgSoft, 'B4') : C.bgSoft, padding: 10, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}) }}
                  data-testid={`agenda-booking-row-${idx}`}
                  testID={`agenda-booking-row-${idx}`}
                >
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{item.guest_name || 'Guest meeting'}</Text>
                  <Text style={{ color: C.muted, fontSize: 11, marginTop: 3 }}>{String(item.start || '').replace('T', ' ').slice(0, 16)}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {!calendarGate && workspaceTab === 'ops' && (
          <View
            style={{
              marginBottom: 16,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'AE') : C.card,
              padding: 14,
              gap: 10,
              ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
            }}
            data-testid="agenda-control-ops-panel"
            testID="agenda-control-ops-panel"
          >
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="agenda-control-ops-title" testID="agenda-control-ops-title">
              Control Operations Workspace
            </Text>
            <Text style={{ color: C.muted, fontSize: 11 }} data-testid="agenda-control-ops-copy" testID="agenda-control-ops-copy">
              Rapid actions to stabilize scheduling performance and maintain momentum.
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <TouchableOpacity onPress={handleAgendaRefresh} style={{ borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '35') }} data-testid="agenda-control-ops-refresh-button" testID="agenda-control-ops-refresh-button">
                <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800' }}>{syncing ? 'Refreshing...' : 'Refresh Agenda'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={bestSlot ? commitBestSlot : recommendBestSlot} style={{ borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, backgroundColor: (globalThis as any).__alphaColor(C.success, '13'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '34') }} data-testid="agenda-control-ops-best-slot-button" testID="agenda-control-ops-best-slot-button">
                <Text style={{ color: C.successText, fontSize: 11, fontWeight: '800' }}>{bestSlotCommitLoading ? 'Committing suggestion…' : bestSlotLoading ? 'Finding best slot…' : (bestSlot ? 'Commit Suggestion' : 'Find Best Slot')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={openWeekFocus} style={{ borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.bgSoft, 'B4') : C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="agenda-control-ops-week-button" testID="agenda-control-ops-week-button">
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>Open Week Focus</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={openCreateFromAutoprompt} style={{ borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.bgSoft, 'B4') : C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="agenda-control-ops-create-button" testID="agenda-control-ops-create-button">
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>Create Event</Text>
              </TouchableOpacity>
            </View>

            {bestSlot && (
              <View
                style={{
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: (globalThis as any).__alphaColor(C.success, '38'),
                  backgroundColor: (globalThis as any).__alphaColor(C.success, '10'),
                  padding: 11,
                  gap: 7,
                }}
                data-testid="agenda-best-slot-card"
                testID="agenda-best-slot-card"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="agenda-best-slot-title" testID="agenda-best-slot-title">
                    Best Slot Recommendation
                  </Text>
                  <View style={{ borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '40'), backgroundColor: (globalThis as any).__alphaColor(C.success, '16'), paddingHorizontal: 8, paddingVertical: 3 }} data-testid="agenda-best-slot-confidence" testID="agenda-best-slot-confidence">
                    <Text style={{ color: C.successText, fontSize: 10, fontWeight: '800' }}>Confidence {Math.max(0, Math.min(100, Number(bestSlot.confidence || 0)))}%</Text>
                  </View>
                </View>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} data-testid="agenda-best-slot-time" testID="agenda-best-slot-time">
                  {String(bestSlot.start || '').replace('T', ' ').slice(0, 16)} → {String(bestSlot.end || '').replace('T', ' ').slice(0, 16)}
                </Text>
                <Text style={{ color: C.muted, fontSize: 11 }} data-testid="agenda-best-slot-reason" testID="agenda-best-slot-reason">
                  {bestSlot.reason || 'Best availability window aligned with your schedule rhythm.'}
                </Text>
                <Text style={{ color: C.muted, fontSize: 10 }} data-testid="agenda-best-slot-adaptive-line" testID="agenda-best-slot-adaptive-line">
                  Adaptive tuning • Plan: {String(bestSlot.plan_scope || 'basic').toUpperCase()} • Acceptance ratio: {Math.round(Number(bestSlot.acceptance_ratio_30d || 0) * 100)}%
                </Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  <TouchableOpacity
                    onPress={commitBestSlot}
                    style={{ borderRadius: 9, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: (globalThis as any).__alphaColor(C.success, '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '36') }}
                    data-testid="agenda-best-slot-commit-button"
                    testID="agenda-best-slot-commit-button"
                  >
                    <Text style={{ color: C.successText, fontSize: 11, fontWeight: '800' }}>{bestSlotCommitLoading ? 'Committing…' : 'Confirm & Commit'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={applyBestSlot}
                    style={{ borderRadius: 9, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '14'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '34') }}
                    data-testid="agenda-best-slot-apply-button"
                    testID="agenda-best-slot-apply-button"
                  >
                    <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800' }}>Apply to Event Form</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={recommendBestSlot}
                    style={{ borderRadius: 9, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }}
                    data-testid="agenda-best-slot-refresh-button"
                    testID="agenda-best-slot-refresh-button"
                  >
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>Recompute</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={ignoreBestSlot}
                    style={{ borderRadius: 9, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }}
                    data-testid="agenda-best-slot-ignore-button"
                    testID="agenda-best-slot-ignore-button"
                  >
                    <Text style={{ color: C.muted, fontSize: 11, fontWeight: '700' }}>Ignore</Text>
                  </TouchableOpacity>
                </View>

                {bestSlotAlternatives.length > 0 && (
                  <View style={{ gap: 6 }} data-testid="agenda-best-slot-alternatives" testID="agenda-best-slot-alternatives">
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>Alternatives</Text>
                    {bestSlotAlternatives.slice(0, 3).map((alt, index) => (
                      <Text
                        key={`alt-${index}`}
                        style={{ color: C.muted, fontSize: 10 }}
                        data-testid={`agenda-best-slot-alternative-${index}`}
                        testID={`agenda-best-slot-alternative-${index}`}
                      >
                        {String(alt?.start || '').replace('T', ' ').slice(0, 16)} ({Math.max(0, Math.min(100, Number(alt?.confidence || 0)))}%)
                      </Text>
                    ))}
                  </View>
                )}
              </View>
            )}

            <View
              style={{
                borderRadius: 12,
                borderWidth: 1,
                borderColor: (bestSlotRewardBadge?.earned
                  ? (globalThis as any).__alphaColor(C.success, '36')
                  : (globalThis as any).__alphaColor(C.primary, '34')),
                backgroundColor: (bestSlotRewardBadge?.earned
                  ? (globalThis as any).__alphaColor(C.success, '10')
                  : (globalThis as any).__alphaColor(C.primary, '10')),
                padding: 11,
                gap: 8,
              }}
              data-testid="agenda-best-slot-weekly-reward-badge-card"
              testID="agenda-best-slot-weekly-reward-badge-card"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons
                    name={bestSlotRewardBadge?.earned ? 'ribbon' : 'ribbon-outline'}
                    size={14}
                    color={bestSlotRewardBadge?.earned ? C.successText : C.primary}
                  />
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }} data-testid="agenda-best-slot-weekly-reward-title" testID="agenda-best-slot-weekly-reward-title">
                    {bestSlotRewardBadge?.title || 'Accept 3 best slots/week'}
                  </Text>
                </View>
                <View
                  style={{
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: bestSlotRewardBadge?.earned
                      ? (globalThis as any).__alphaColor(C.success, '36')
                      : (globalThis as any).__alphaColor(C.primary, '35'),
                    backgroundColor: bestSlotRewardBadge?.earned
                      ? (globalThis as any).__alphaColor(C.success, '16')
                      : (globalThis as any).__alphaColor(C.primary, '16'),
                    paddingHorizontal: 8,
                    paddingVertical: 3,
                  }}
                  data-testid="agenda-best-slot-weekly-reward-status-badge"
                  testID="agenda-best-slot-weekly-reward-status-badge"
                >
                  <Text style={{ color: bestSlotRewardBadge?.earned ? C.successText : C.primary, fontSize: 10, fontWeight: '800' }}>
                    {bestSlotRewardBadge?.status_label || '0/3 accepted'}
                  </Text>
                </View>
              </View>

              <Text style={{ color: C.muted, fontSize: 10 }} data-testid="agenda-best-slot-weekly-reward-subtitle" testID="agenda-best-slot-weekly-reward-subtitle">
                {bestSlotRewardBadge?.subtitle || 'Weekly execution reward'}
              </Text>

              <View
                style={{
                  width: '100%',
                  height: 8,
                  borderRadius: 999,
                  backgroundColor: C.bgSoft,
                  overflow: 'hidden',
                  borderWidth: 1,
                  borderColor: C.border,
                }}
                data-testid="agenda-best-slot-weekly-reward-progress-track"
                testID="agenda-best-slot-weekly-reward-progress-track"
              >
                <View
                  style={{
                    width: `${Math.max(0, Math.min(100, Math.round(Number(bestSlotRewardBadge?.progress_ratio || 0) * 100)))}%`,
                    height: '100%',
                    backgroundColor: bestSlotRewardBadge?.earned ? C.success : C.primary,
                  }}
                  data-testid="agenda-best-slot-weekly-reward-progress-fill"
                  testID="agenda-best-slot-weekly-reward-progress-fill"
                />
              </View>

              <Text style={{ color: C.muted, fontSize: 10 }} data-testid="agenda-best-slot-weekly-reward-support-copy" testID="agenda-best-slot-weekly-reward-support-copy">
                {bestSlotRewardBadge?.support_copy || 'Accept 3 best-slot recommendations this week to unlock your reward badge.'}
              </Text>

              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <Text style={{ color: C.muted, fontSize: 10 }} data-testid="agenda-best-slot-weekly-reward-breakdown" testID="agenda-best-slot-weekly-reward-breakdown">
                  Accepted this week: {String(bestSlotRewardBadge?.accepted_this_week || 0)} / {String(bestSlotRewardBadge?.target_accepts_per_week || 3)}
                </Text>
                <TouchableOpacity
                  onPress={() => router.push(String(bestSlotRewardBadge?.cta?.url || '/book-meeting'))}
                  style={{
                    borderRadius: 9,
                    paddingHorizontal: 10,
                    paddingVertical: 7,
                    backgroundColor: (bestSlotRewardBadge?.premium_conversion_nudge
                      ? (globalThis as any).__alphaColor(C.warning, '13')
                      : (globalThis as any).__alphaColor(C.primary, '14')),
                    borderWidth: 1,
                    borderColor: (bestSlotRewardBadge?.premium_conversion_nudge
                      ? (globalThis as any).__alphaColor(C.warning, '30')
                      : (globalThis as any).__alphaColor(C.primary, '35')),
                  }}
                  data-testid="agenda-best-slot-weekly-reward-cta-button"
                  testID="agenda-best-slot-weekly-reward-cta-button"
                >
                  <Text style={{
                    color: bestSlotRewardBadge?.premium_conversion_nudge ? C.warningText : C.primary,
                    fontSize: 10,
                    fontWeight: '800',
                  }}>
                    {bestSlotRewardBadge?.cta?.label || 'Open control ops'}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}

        {workspaceTab === 'insights' && (!calendarGate || isAdminUser) && (
          <View
            style={{
              marginBottom: 16,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.card,
              padding: 14,
              gap: 10,
            }}
            data-testid="agenda-insights-workspace-panel"
            testID="agenda-insights-workspace-panel"
          >
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="agenda-insights-workspace-title" testID="agenda-insights-workspace-title">
              Insights Workspace
            </Text>
            <Text style={{ color: C.muted, fontSize: 11 }} data-testid="agenda-insights-workspace-copy" testID="agenda-insights-workspace-copy">
              Track trend velocity and conflict pressure to improve scheduling consistency.
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {sevenDayMetrics.map((metric) => (
                <View
                  key={metric.id}
                  style={{ minWidth: isMobile ? '47%' : 180, flexGrow: 1, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }}
                  data-testid={`agenda-insights-metric-${metric.id}`}
                  testID={`agenda-insights-metric-${metric.id}`}
                >
                  <Text style={{ color: C.muted, fontSize: 10 }}>{metric.label}</Text>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '900', marginTop: 6 }}>
                    {typeof metric.current === 'number' ? metric.current.toFixed(metric.precision || 0) : String(metric.current)}
                    {metric.suffix || ''}
                  </Text>
                </View>
              ))}
            </View>

            <View
              style={{
                borderRadius: 12,
                borderWidth: 1,
                borderColor: C.border,
                backgroundColor: C.bgSoft,
                padding: 10,
                gap: 8,
              }}
              data-testid="agenda-release-gate-panel"
              testID="agenda-release-gate-panel"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="agenda-release-gate-title" testID="agenda-release-gate-title">
                  Release-Gate Command Center
                </Text>
                <View
                  style={{
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: (releaseGateSnapshot?.gate?.pass ? (globalThis as any).__alphaColor(C.success, '38') : (globalThis as any).__alphaColor(C.warning, '38')),
                    backgroundColor: (releaseGateSnapshot?.gate?.pass ? (globalThis as any).__alphaColor(C.success, '15') : (globalThis as any).__alphaColor(C.warning, '14')),
                    paddingHorizontal: 8,
                    paddingVertical: 4,
                  }}
                  data-testid="agenda-release-gate-decision-badge"
                  testID="agenda-release-gate-decision-badge"
                >
                  <Text style={{ fontSize: 10, fontWeight: '800', color: releaseGateSnapshot?.gate?.pass ? C.successText : C.warningText }}>
                    {(releaseGateSnapshot?.gate?.decision || 'no-go').toUpperCase()}
                  </Text>
                </View>
              </View>

              <Text style={{ color: C.muted, fontSize: 11 }} data-testid="agenda-release-gate-profile-line" testID="agenda-release-gate-profile-line">
                Active profile: {(releaseGateSnapshot?.profile || releaseGateProfile || 'standard').toUpperCase()}
              </Text>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {(['strict', 'standard', 'lenient'] as const).map((profile) => {
                  const active = (releaseGateSnapshot?.profile || releaseGateProfile) === profile;
                  return (
                    <TouchableOpacity
                      key={profile}
                      disabled={!isAdminUser || releaseGateSaving}
                      onPress={() => saveReleaseGateProfile(profile)}
                      style={{
                        borderRadius: 9,
                        paddingHorizontal: 10,
                        paddingVertical: 7,
                        backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '14') : C.card,
                        borderWidth: 1,
                        borderColor: active ? (globalThis as any).__alphaColor(C.primary, '35') : C.border,
                        opacity: !isAdminUser ? 0.7 : 1,
                      }}
                      data-testid={`agenda-release-gate-profile-${profile}-button`}
                      testID={`agenda-release-gate-profile-${profile}-button`}
                    >
                      <Text style={{ color: active ? C.primary : C.muted, fontSize: 10, fontWeight: '800' }}>{profile.toUpperCase()}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {isAdminUser && (
                <View
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 10, gap: 6 }}
                  data-testid="agenda-release-gate-safe-rollout-simulator-panel"
                  testID="agenda-release-gate-safe-rollout-simulator-panel"
                >
                  <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }}>
                    Safe rollout simulator (strict / standard / lenient)
                  </Text>
                  {(releaseGateSimulator?.simulation || []).map((row, index) => (
                    <Text
                      key={`release-sim-${row?.profile || index}`}
                      style={{ color: C.muted, fontSize: 10 }}
                      data-testid={`agenda-release-gate-safe-rollout-simulator-row-${index}`}
                      testID={`agenda-release-gate-safe-rollout-simulator-row-${index}`}
                    >
                      {String(row?.profile || 'standard').toUpperCase()} • GO {String(row?.go_count || 0)} / NO-GO {String(row?.no_go_count || 0)} • ΔGO rate {Math.round(Number(row?.delta_go_rate_vs_active || 0) * 100)}%
                    </Text>
                  ))}
                  <Text
                    style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}
                    data-testid="agenda-release-gate-safe-rollout-recommendation"
                    testID="agenda-release-gate-safe-rollout-recommendation"
                  >
                    Recommended: {String(releaseGateSimulator?.recommendation?.profile || releaseGateProfile || 'standard').toUpperCase()} — {String(releaseGateSimulator?.recommendation?.reason || 'Use sampled GO-rate projection before applying.')}
                  </Text>
                </View>
              )}

              {(releaseGateSnapshot?.gate?.failed_reasons || []).length > 0 && (
                <View data-testid="agenda-release-gate-failed-reasons" testID="agenda-release-gate-failed-reasons">
                  <Text style={{ color: C.warningText, fontSize: 10 }}>
                    Blockers: {(releaseGateSnapshot?.gate?.failed_reasons || []).join(', ')}
                  </Text>
                </View>
              )}
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <View style={{ minWidth: isMobile ? '47%' : 180, flexGrow: 1, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }} data-testid="agenda-reliability-sync-error-card" testID="agenda-reliability-sync-error-card">
                <Text style={{ color: C.muted, fontSize: 10 }}>Sync Error Rate (7d)</Text>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '900', marginTop: 6 }}>
                  {Math.round(Number(reliabilitySnapshot?.metrics?.sync_error_rate_7d || 0) * 100)}%
                </Text>
              </View>
              <View style={{ minWidth: isMobile ? '47%' : 180, flexGrow: 1, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }} data-testid="agenda-reliability-reminder-card" testID="agenda-reliability-reminder-card">
                <Text style={{ color: C.muted, fontSize: 10 }}>Reminder Success (7d)</Text>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '900', marginTop: 6 }}>
                  {Math.round(Number(reliabilitySnapshot?.metrics?.reminder_success_rate_7d || 0) * 100)}%
                </Text>
              </View>
              <View style={{ minWidth: isMobile ? '47%' : 180, flexGrow: 1, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }} data-testid="agenda-reliability-conversion-card" testID="agenda-reliability-conversion-card">
                <Text style={{ color: C.muted, fontSize: 10 }}>Booking Conversion (7d)</Text>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '900', marginTop: 6 }}>
                  {Math.round(Number(reliabilitySnapshot?.metrics?.booking_conversion_7d || 0) * 100)}%
                </Text>
              </View>
              <View style={{ minWidth: isMobile ? '47%' : 180, flexGrow: 1, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }} data-testid="agenda-reliability-conflict-trend-card" testID="agenda-reliability-conflict-trend-card">
                <Text style={{ color: C.muted, fontSize: 10 }}>Conflict Trend (7d)</Text>
                <Text style={{ color: C.text, fontSize: 13, fontWeight: '900', marginTop: 6 }}>
                  {String(reliabilitySnapshot?.metrics?.conflicts_current_7d || 0)} / {String(reliabilitySnapshot?.metrics?.conflicts_previous_7d || 0)}
                </Text>
              </View>
            </View>

            {isAdminUser && (
              <View
                style={{
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.bgSoft,
                  padding: 10,
                  gap: 6,
                }}
                data-testid="agenda-admin-reliability-panel"
                testID="agenda-admin-reliability-panel"
              >
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="agenda-admin-reliability-title" testID="agenda-admin-reliability-title">
                  Admin Reliability Rollout Panel
                </Text>
                <Text style={{ color: C.muted, fontSize: 10 }} data-testid="agenda-admin-reliability-summary" testID="agenda-admin-reliability-summary">
                  Users: {String(adminReliability?.summary?.users_evaluated || 0)} • GO: {String(adminReliability?.summary?.go_count || 0)} • NO-GO: {String(adminReliability?.summary?.no_go_count || 0)} • GO rate: {Math.round(Number(adminReliability?.summary?.go_rate || 0) * 100)}%
                </Text>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  <View
                    style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 8, minWidth: 220, flexGrow: 1 }}
                    data-testid="agenda-rbac-drift-monitor-badge"
                    testID="agenda-rbac-drift-monitor-badge"
                  >
                    <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>
                      RBAC Drift Monitor: {String(rbacDriftSnapshot?.status || 'PASS')}
                    </Text>
                    <Text style={{ color: C.muted, fontSize: 10 }}>
                      Uncovered routes: {String(rbacDriftSnapshot?.uncovered_route_count || 0)} / {String(rbacDriftSnapshot?.scanned_routes || 0)}
                    </Text>
                  </View>

                  <View
                    style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 8, minWidth: 220, flexGrow: 1 }}
                    data-testid="agenda-rbac-gate-health-badge"
                    testID="agenda-rbac-gate-health-badge"
                  >
                    <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>
                      RBAC Gate Health: {String(rbacGateHealthSnapshot?.status || 'healthy').toUpperCase()}
                    </Text>
                    <Text style={{ color: C.muted, fontSize: 10 }}>
                      Score: {String(rbacGateHealthSnapshot?.health_score || 100)} • Block rate: {Math.round(Number(rbacGateHealthSnapshot?.block_rate || 0) * 100)}%
                    </Text>
                  </View>
                </View>

                <View
                  style={{
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: C.card,
                    padding: 10,
                    gap: 8,
                    marginTop: 4,
                  }}
                  data-testid="agenda-admin-preview-backfill-panel"
                  testID="agenda-admin-preview-backfill-panel"
                >
                  <Text
                    style={{ color: C.text, fontSize: 11, fontWeight: '800' }}
                    data-testid="agenda-admin-preview-backfill-title"
                    testID="agenda-admin-preview-backfill-title"
                  >
                    Historical Preview E2E False-Positive Backfill
                  </Text>
                  <Text
                    style={{ color: C.muted, fontSize: 10 }}
                    data-testid="agenda-admin-preview-backfill-summary"
                    testID="agenda-admin-preview-backfill-summary"
                  >
                    Scanned: {String(previewBackfillResult?.scanned_count || 0)} • Candidates: {String(previewBackfillResult?.candidate_count || 0)} • Updated: {String(previewBackfillResult?.updated_count || 0)}
                  </Text>

                <View
                  style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 8, gap: 4 }}
                  data-testid="agenda-admin-preview-backfill-signal-badge"
                  testID="agenda-admin-preview-backfill-signal-badge"
                >
                  <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>
                    Signal badge: {String(previewBackfillResult?.signal_badge?.status || 'MIXED_SIGNAL_REVIEW')}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 10 }}>
                    {String(previewBackfillResult?.signal_badge?.summary || 'Signal classification summary unavailable.')}
                  </Text>
                </View>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {(['strict', 'standard', 'lenient'] as const).map((profile) => {
                    const active = previewBackfillProfile === profile;
                    return (
                      <TouchableOpacity
                        key={`backfill-profile-${profile}`}
                        onPress={() => setPreviewBackfillProfile(profile)}
                        disabled={previewBackfillLoading}
                        style={{
                          borderRadius: 9,
                          paddingHorizontal: 10,
                          paddingVertical: 7,
                          backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '14') : C.card,
                          borderWidth: 1,
                          borderColor: active ? (globalThis as any).__alphaColor(C.primary, '35') : C.border,
                          opacity: previewBackfillLoading ? 0.7 : 1,
                        }}
                        data-testid={`agenda-admin-preview-backfill-profile-${profile}-button`}
                        testID={`agenda-admin-preview-backfill-profile-${profile}-button`}
                      >
                        <Text style={{ color: active ? C.primary : C.muted, fontSize: 10, fontWeight: '800' }}>{profile.toUpperCase()}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>

                <View
                  style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, gap: 4 }}
                  data-testid="agenda-admin-preview-backfill-simulator-panel"
                  testID="agenda-admin-preview-backfill-simulator-panel"
                >
                  <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>
                    Safe rollout simulator (strict/standard/lenient)
                  </Text>
                  {(previewBackfillSimulation || []).map((row, index) => (
                    <Text
                      key={`sim-row-${row?.profile || index}`}
                      style={{ color: C.muted, fontSize: 10 }}
                      data-testid={`agenda-admin-preview-backfill-simulator-row-${index}`}
                      testID={`agenda-admin-preview-backfill-simulator-row-${index}`}
                    >
                      {String(row?.profile || 'standard').toUpperCase()} • would update {String(row?.would_update_count || 0)} • Δ vs standard {String(row?.delta_vs_standard || 0)}
                    </Text>
                  ))}
                </View>

                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    <TouchableOpacity
                      onPress={refreshPreviewBackfillCandidates}
                      disabled={previewBackfillLoading}
                      style={{
                        borderRadius: 9,
                        paddingHorizontal: 10,
                        paddingVertical: 8,
                        backgroundColor: (globalThis as any).__alphaColor(C.primary, '14'),
                        borderWidth: 1,
                        borderColor: (globalThis as any).__alphaColor(C.primary, '35'),
                        opacity: previewBackfillLoading ? 0.7 : 1,
                      }}
                      data-testid="agenda-admin-preview-backfill-refresh-button"
                      testID="agenda-admin-preview-backfill-refresh-button"
                    >
                      <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>
                        {previewBackfillLoading ? 'Refreshing…' : 'Refresh Candidates'}
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      onPress={runPreviewBackfillDryRun}
                      disabled={previewBackfillLoading}
                      style={{
                        borderRadius: 9,
                        paddingHorizontal: 10,
                        paddingVertical: 8,
                        backgroundColor: (globalThis as any).__alphaColor(C.info, '12'),
                        borderWidth: 1,
                        borderColor: (globalThis as any).__alphaColor(C.info, '32'),
                        opacity: previewBackfillLoading ? 0.7 : 1,
                      }}
                      data-testid="agenda-admin-preview-backfill-dry-run-button"
                      testID="agenda-admin-preview-backfill-dry-run-button"
                    >
                      <Text style={{ color: C.info, fontSize: 10, fontWeight: '800' }}>
                        {previewBackfillLoading ? 'Running dry run…' : 'Dry Run'}
                      </Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                      onPress={prepareBackfillApplyConfirmation}
                      disabled={previewBackfillLoading || Number(previewBackfillResult?.candidate_count || 0) <= 0}
                      style={{
                        borderRadius: 9,
                        paddingHorizontal: 10,
                        paddingVertical: 8,
                        backgroundColor: (globalThis as any).__alphaColor(C.warning, '13'),
                        borderWidth: 1,
                        borderColor: (globalThis as any).__alphaColor(C.warning, '32'),
                        opacity: (previewBackfillLoading || Number(previewBackfillResult?.candidate_count || 0) <= 0) ? 0.6 : 1,
                      }}
                      data-testid="agenda-admin-preview-backfill-apply-button"
                      testID="agenda-admin-preview-backfill-apply-button"
                    >
                      <Text style={{ color: C.warningText, fontSize: 10, fontWeight: '800' }}>
                        {previewBackfillLoading ? 'Preparing…' : 'Dry Run → Apply'}
                      </Text>
                    </TouchableOpacity>
                  </View>

                  <Modal
                    visible={Boolean(showBackfillApplyConfirm && previewBackfillResult?.dry_run_summary)}
                    transparent
                    animationType="fade"
                    onRequestClose={() => setShowBackfillApplyConfirm(false)}
                  >
                    <View
                      style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.42)', alignItems: 'center', justifyContent: 'center', padding: 18 }}
                      data-testid="agenda-admin-preview-backfill-apply-confirmation-modal"
                      testID="agenda-admin-preview-backfill-apply-confirmation-modal"
                    >
                      <View style={{ width: '100%', maxWidth: 520, borderRadius: 10, borderWidth: 1, borderColor: C.warning, backgroundColor: C.card, padding: 10, gap: 7 }}>
                        <Text style={{ color: C.warningText, fontSize: 10, fontWeight: '800' }}>
                          Confirm Apply Backfill ({String(previewBackfillResult?.dry_run_summary?.profile || previewBackfillProfile).toUpperCase()})
                        </Text>
                        <Text style={{ color: C.muted, fontSize: 10 }}>
                          Dry-run updates: {String(previewBackfillResult?.dry_run_summary?.dry_update_count || 0)} • Current applied: {String(previewBackfillResult?.dry_run_summary?.applied_update_count || 0)} • Diff: {String(previewBackfillResult?.dry_run_summary?.diff_count || 0)}
                        </Text>
                        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                          <TouchableOpacity
                            onPress={applyPreviewBackfill}
                            disabled={previewBackfillLoading}
                            style={{ borderRadius: 8, borderWidth: 1, borderColor: C.warning, backgroundColor: (globalThis as any).__alphaColor(C.warning, '18'), paddingHorizontal: 10, paddingVertical: 7 }}
                            data-testid="agenda-admin-preview-backfill-apply-confirm-button"
                            testID="agenda-admin-preview-backfill-apply-confirm-button"
                          >
                            <Text style={{ color: C.warningText, fontSize: 10, fontWeight: '800' }}>{previewBackfillLoading ? 'Applying…' : 'Confirm Apply'}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            onPress={() => setShowBackfillApplyConfirm(false)}
                            style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 7 }}
                            data-testid="agenda-admin-preview-backfill-apply-cancel-button"
                            testID="agenda-admin-preview-backfill-apply-cancel-button"
                          >
                            <Text style={{ color: C.muted, fontSize: 10, fontWeight: '800' }}>Cancel</Text>
                          </TouchableOpacity>
                        </View>
                      </View>
                    </View>
                  </Modal>

                  {previewBackfillResult?.dry_run_summary && (
                    <View
                      style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 8, gap: 4 }}
                      data-testid="agenda-admin-preview-backfill-dry-run-summary"
                      testID="agenda-admin-preview-backfill-dry-run-summary"
                    >
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>
                        Dry Run → Apply Diff ({String(previewBackfillResult?.dry_run_summary?.profile || previewBackfillProfile).toUpperCase()})
                      </Text>
                      <Text style={{ color: C.muted, fontSize: 10 }}>
                        Dry-run updates: {String(previewBackfillResult?.dry_run_summary?.dry_update_count || 0)} • Applied updates: {String(previewBackfillResult?.dry_run_summary?.applied_update_count || 0)} • Diff: {String(previewBackfillResult?.dry_run_summary?.diff_count || 0)}
                      </Text>
                    </View>
                  )}

                  {(previewBackfillResult?.candidates || []).slice(0, 3).map((row, index) => (
                    <View
                      key={`${row?.run_id || 'candidate'}-${index}`}
                      style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 8, gap: 4 }}
                      data-testid={`agenda-admin-preview-backfill-candidate-${index}`}
                      testID={`agenda-admin-preview-backfill-candidate-${index}`}
                    >
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>
                        {String(row?.run_id || 'run')} • {String(row?.status || 'blocked').toUpperCase()} • {Math.round(Number(row?.confidence || 0) * 100)}%
                      </Text>
                      <Text style={{ color: C.muted, fontSize: 10 }}>
                        {String(row?.status_reason_code || 'n/a')} → {String(row?.recommended_status_reason_code || 'n/a')}
                      </Text>
                    </View>
                  ))}
                </View>
              </View>
            )}
          </View>
        )}

        {/* Quick Stats */}
        <View
          onLayout={(e) => setSectionOffset('control', e.nativeEvent.layout.y)}
          style={{
            marginBottom: 16,
            borderRadius: 16,
            borderWidth: 1,
            borderColor: C.border,
            backgroundColor: C.card,
            padding: isMobile ? 12 : 14,
            gap: 10,
          }}
          data-testid="agenda-control-plane-card"
          testID="agenda-control-plane-card"
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <View>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="agenda-control-plane-title" testID="agenda-control-plane-title">Agenda Control Plane</Text>
              <Text style={{ color: C.muted, fontSize: 11 }} data-testid="agenda-control-plane-subtitle" testID="agenda-control-plane-subtitle">
                Live scheduling health using your real calendar records.
              </Text>
            </View>
            <TouchableOpacity
              onPress={handleAgendaRefresh}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
                paddingHorizontal: 12,
                paddingVertical: 8,
                borderRadius: 10,
                backgroundColor: (globalThis as any).__alphaColor(C.primary, '14'),
                borderWidth: 1,
                borderColor: (globalThis as any).__alphaColor(C.primary, '44'),
              }}
              data-testid="agenda-control-plane-refresh-button"
              testID="agenda-control-plane-refresh-button"
            >
              {syncing ? <_ActivityIndicator size="small" color={C.primary} /> : <Ionicons name="refresh-outline" size={14} color={C.primary} />}
              <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800' }}>{syncing ? 'Refreshing...' : 'Refresh Agenda'}</Text>
            </TouchableOpacity>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[
              {
                id: 'conflicts',
                label: 'Conflict Alerts',
                value: String(overlapConflictCount),
                tone: overlapConflictCount > 0 ? C.error : C.successText,
                icon: overlapConflictCount > 0 ? 'warning-outline' : 'checkmark-done-outline',
              },
              {
                id: 'booked-hours',
                label: 'Booked Today',
                value: `${(bookedTodayMinutes / 60).toFixed(1)}h`,
                tone: C.primary,
                icon: 'time-outline',
              },
              {
                id: 'upcoming-48h',
                label: 'Next 48h',
                value: String(upcoming48hCount),
                tone: C.warningText,
                icon: 'flash-outline',
              },
              {
                id: 'sync-state',
                label: 'Integration State',
                value: googleConnected ? 'Google Synced' : 'Local Mode',
                tone: googleConnected ? C.successText : C.muted,
                icon: googleConnected ? 'cloud-done-outline' : 'cloud-offline-outline',
              },
            ].map((item) => (
              <View
                key={item.id}
                style={{
                  minWidth: isMobile ? '47%' : 180,
                  flexGrow: 1,
                  borderRadius: 11,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.bgSoft,
                  padding: 10,
                }}
                data-testid={`agenda-control-metric-${item.id}`}
                testID={`agenda-control-metric-${item.id}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name={item.icon as any} size={13} color={item.tone} />
                  <Text style={{ color: C.muted, fontSize: 10 }}>{item.label}</Text>
                </View>
                <Text style={{ color: item.tone, fontSize: 14, fontWeight: '900', marginTop: 6 }}>{item.value}</Text>
              </View>
            ))}
          </View>
        </View>

        <View onLayout={(e) => setSectionOffset('comparison', e.nativeEvent.layout.y)} style={{ marginBottom: 16 }}>
          <SevenDayComparisonRibbon
            title="7-day comparison ribbon"
            subtitle="Current 7 days vs previous 7 days from agenda events"
            metrics={sevenDayMetrics}
            colors={C}
            testIdPrefix="agenda-seven-day"
            onRefresh={handleAgendaRefresh}
            refreshing={syncing}
          />
        </View>

        <View style={{ marginBottom: 16 }}>
          <DailyAutopromptCards
            title="Daily autoprompt cards"
            subtitle="Next best actions generated from your 7-day agenda trend"
            prompts={agendaAutopromptCards}
            colors={C}
            testIdPrefix="agenda-autoprompt"
          />
        </View>

        {calendarGate && (
          <View
            style={{
              marginBottom: 18,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: (globalThis as any).__alphaColor(C.warning, '40'),
              backgroundColor: (globalThis as any).__alphaColor(C.warning, '12'),
              padding: 16,
              gap: 12,
            }}
            data-testid="agenda-subscription-gate-card"
            testID="agenda-subscription-gate-card"
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.warning, '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="lock-closed-outline" size={17} color={C.warningText} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="agenda-subscription-gate-title" testID="agenda-subscription-gate-title">
                  My Agenda requires plan upgrade
                </Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 3 }} data-testid="agenda-subscription-gate-copy" testID="agenda-subscription-gate-copy">
                  {calendarGate.message || 'Upgrade to unlock calendar sync, booking links, and AI scheduling.'}
                </Text>
              </View>
            </View>

            <Text style={{ color: C.muted, fontSize: 11 }} data-testid="agenda-subscription-gate-plan-line" testID="agenda-subscription-gate-plan-line">
              Current: {(calendarGate.current_plan || 'free').toUpperCase()} • Required: {(calendarGate.required_plan || 'basic').toUpperCase()}
            </Text>

            <UpgradeBanner featureName="My Agenda" variant="locked" requiredPlan={(String(calendarGate.required_plan || 'basic').toLowerCase() === 'premium' ? 'premium' : 'basic')} />
          </View>
        )}

        {!calendarGate && (
          <View
            style={{
              marginBottom: 16,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.card,
              padding: isMobile ? 12 : 14,
              gap: 10,
            }}
            data-testid="agenda-reliability-panel"
            testID="agenda-reliability-panel"
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
              <View>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="agenda-reliability-title" testID="agenda-reliability-title">
                  Enterprise Reliability Snapshot
                </Text>
                <Text style={{ color: C.muted, fontSize: 11 }} data-testid="agenda-reliability-subtitle" testID="agenda-reliability-subtitle">
                  Real-time stability and utilization metrics for your scheduling system.
                </Text>
              </View>
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {calendarHealthCards.map((item) => (
                <View
                  key={item.id}
                  style={{
                    minWidth: isMobile ? '47%' : 180,
                    flexGrow: 1,
                    borderRadius: 11,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: C.bgSoft,
                    padding: 10,
                  }}
                  data-testid={`agenda-reliability-metric-${item.id}`}
                  testID={`agenda-reliability-metric-${item.id}`}
                >
                  <Text style={{ color: C.muted, fontSize: 10 }}>{item.label}</Text>
                  <Text style={{ color: C.text, fontSize: 15, fontWeight: '900', marginTop: 6 }}>{item.value}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        <View onLayout={(e) => setSectionOffset('stats', e.nativeEvent.layout.y)} style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10, marginBottom: 20 }} data-testid="agenda-stats" testID="agenda-stats">
          {[
            { label: "Today's Events", value: todayEvents.length, icon: 'today', color: C.primary },
            { label: 'This Month', value: totalThisMonth, icon: 'calendar', color: C.accent },
            { label: 'Upcoming', value: upcomingEvents.length, icon: 'arrow-forward-circle', color: C.successText },
            { label: 'Recurring', value: recurringCount, icon: 'repeat', color: '#EC4899' }, // @theme-ok brand-fixed-palette residual accent hex (reviewed)
          ].map(s => (
            <View key={s.label} style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid={`stat-${s.label.toLowerCase().replace(/['\s]/g, '-')}`} testID={`stat-${s.label.toLowerCase().replace(/['\s]/g, '-')}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(s.color, '14'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={s.icon as any} size={18} color={s.color} />
                </View>
                <View>
                  <Text style={{ color: C.muted, fontSize: 11, fontWeight: '600' }}>{s.label}</Text>
                  <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }}>{s.value}</Text>
                </View>
              </View>
            </View>
          ))}
        </View>

        {/* View Switcher + Month Navigation */}
        <View onLayout={(e) => setSectionOffset('calendar', e.nativeEvent.layout.y)} style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10, marginBottom: 16, alignItems: isMobile ? 'stretch' : 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', gap: 4, backgroundColor: C.card, borderRadius: 12, padding: 4, borderWidth: 1, borderColor: C.border }}>
            {(['day', 'week', 'month'] as ViewMode[]).map(v => (
              <TouchableOpacity key={v} onPress={() => setViewMode(v)}
                style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: viewMode === v ? (globalThis as any).__alphaColor(C.primary, '15') : 'transparent' }}
                data-testid={`view-${v}`} testID={`view-${v}`}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: viewMode === v ? C.primary : C.muted, textTransform: 'capitalize' }}>{v}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TouchableOpacity onPress={prevMonth} style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: C.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border }} data-testid="prev-month-btn" testID="prev-month-btn">
              <Ionicons name="chevron-back" size={16} color={C.text} />
            </TouchableOpacity>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', minWidth: 160, textAlign: 'center' }}>
              {MONTHS[currentMonth]} {currentYear}
            </Text>
            <TouchableOpacity onPress={nextMonth} style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: C.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border }} data-testid="next-month-btn" testID="next-month-btn">
              <Ionicons name="chevron-forward" size={16} color={C.text} />
            </TouchableOpacity>
            <TouchableOpacity onPress={goToday} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12') }} data-testid="today-btn" testID="today-btn">
              <Text style={{ color: C.primary, fontSize: 12, fontWeight: '700' }}>Today</Text>
            </TouchableOpacity>
          </View>
        </View>

        {loading ? (
          <AgendaSkeleton />
        ) : (
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 16 }}>
            <View style={{ flex: isMobile ? undefined : 2 }}>
              {viewMode === 'month' && (
                <MonthView
                  monthDays={monthDays} today={today} selectedDate={selectedDate} setSelectedDate={setSelectedDate}
                  getEventsForDay={getEventsForDay} isMobile={isMobile} C={C}
                  dragOverDay={dragOverDay} handleDragStart={handleDragStart} handleDragOver={handleDragOver}
                  handleDrop={handleDrop} handleDragEnd={handleDragEnd}
                />
              )}
              {viewMode === 'week' && (
                <WeekView
                  weekDays={weekDays} today={today} selectedDate={selectedDate} setSelectedDate={setSelectedDate}
                  getEventsForDay={getEventsForDay} setDetailEvent={setDetailEvent} C={C}
                />
              )}
              {viewMode === 'day' && (
                <DayView
                  selectedDate={selectedDate} selectedDayEvents={selectedDayEvents}
                  openCreateModal={openCreateModal} setDetailEvent={setDetailEvent} C={C}
                />
              )}
            </View>

            <View onLayout={(e) => setSectionOffset('sidebar', e.nativeEvent.layout.y)} style={{ flex: isMobile ? undefined : 1 }}>
              <AgendaSidebar
                selectedDate={selectedDate} today={today} selectedDayEvents={selectedDayEvents}
                upcomingEvents={upcomingEvents} googleConnected={googleConnected}
                openCreateModal={openCreateModal} setDetailEvent={setDetailEvent} C={C}
              />
            </View>
          </View>
        )}

        <EventFormModal
          visible={showModal} onClose={() => setShowModal(false)} editingEvent={editingEvent}
          formTitle={formTitle} setFormTitle={setFormTitle}
          formCategory={formCategory} setFormCategory={setFormCategory}
          formDate={formDate} setFormDate={setFormDate}
          formStartHour={formStartHour} setFormStartHour={setFormStartHour}
          formStartMin={formStartMin} setFormStartMin={setFormStartMin}
          formEndHour={formEndHour} setFormEndHour={setFormEndHour}
          formEndMin={formEndMin} setFormEndMin={setFormEndMin}
          formDescription={formDescription} setFormDescription={setFormDescription}
          formLocation={formLocation} setFormLocation={setFormLocation}
          formRecurrence={formRecurrence} setFormRecurrence={setFormRecurrence}
          formReminder={formReminder} setFormReminder={setFormReminder}
          formSaving={formSaving} handleSave={handleSave}
          handleAiSuggest={handleAiSuggest} aiLoading={aiLoading}
          showAiPanel={showAiPanel} setShowAiPanel={setShowAiPanel}
          aiSuggestions={aiSuggestions} applySuggestion={applySuggestion}
          C={C}
        />

        <EventDetailModal
          detailEvent={detailEvent} setDetailEvent={setDetailEvent}
          openEditModal={openEditModal} handleDelete={handleDelete}
          handleDeleteSeries={handleDeleteSeries} C={C}
        />
        </ScrollView>

        <SectionProgressRail
          visible={showProgressRail}
          colors={C}
          railTestId="agenda-progress-rail"
          activeId={activeSection}
          onSelect={scrollToSection}
          top={124}
          right={10}
          maxWidth={190}
          items={[
            { id: 'control', label: 'Control Plane' },
            { id: 'comparison', label: '7-day Compare' },
            { id: 'stats', label: 'Stats' },
            { id: 'calendar', label: 'Calendar' },
            { id: 'sidebar', label: 'Sidebar' },
          ]}
        />
      </AppShell>
    </ProtectedRouteGate>
  );
}
