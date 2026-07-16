import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  Alert, ActivityIndicator, Platform, Linking, useWindowDimensions, Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AppShell from '../AppShell';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { AgendaSkeleton, FadeSlideIn } from '../SkeletonLoaders';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

/* ─── Helpers ─── */
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const detectTZ = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return 'UTC'; } };

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

const toLocalISO = (d: Date) => {
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const fmtTime = (s: string) => {
  try { const d = new Date(s); return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return s; }
};

const fmtDate = (s: string) => {
  try { return new Date(s).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }); } catch { return s; }
};

const getMonthGrid = (year: number, month: number) => {
  const first = new Date(year, month, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const rows: (number | null)[][] = [];
  let row: (number | null)[] = Array(startOffset).fill(null);
  for (let d = 1; d <= daysInMonth; d++) {
    row.push(d);
    if (row.length === 7) { rows.push(row); row = []; }
  }
  if (row.length > 0) { while (row.length < 7) row.push(null); rows.push(row); }
  return rows;
};

const REMINDER_OPTIONS = [
  { label: 'None', value: 0 },
  { label: '5 min', value: 5 },
  { label: '10 min', value: 10 },
  { label: '15 min', value: 15 },
  { label: '30 min', value: 30 },
  { label: '45 min', value: 45 },
  { label: '1 hour', value: 60 },
  { label: '1 day', value: 1440 },
];

/* ─── Browser Notifications ─── */
const requestNotifPermission = async () => {
  if (Platform.OS !== 'web' || typeof Notification === 'undefined') return false;
  if (Notification.permission === 'granted') return true;
  const p = await Notification.requestPermission();
  return p === 'granted';
};

const showBrowserNotif = (title: string, body: string) => {
  if (Platform.OS !== 'web' || typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  new Notification(title, { body, icon: '/favicon.ico' });
};

const getBrowserNotifPermission = (): string => {
  if (Platform.OS !== 'web' || typeof Notification === 'undefined') return 'unsupported';
  return Notification.permission;
};

/* ─── Main Component ─── */
export default function CalendarScreen() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const { user } = useAuth();
  const { colors: C } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const calendarTitle = t('calendar.header.title');

  const [status, setStatus] = useState<any>({ google_available: false, google_connected: false });
  const [calendars, setCalendars] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [connecting, setConnecting] = useState(false);

  // Views & navigation
  const [viewMode, setViewMode] = useState<'month' | 'day' | 'list'>('month');
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [userTZ, setUserTZ] = useState(detectTZ());

  // Event form
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({ title: '', start: '', end: '', location: '', description: '', notes: '', reminderMinutes: 30 });
  const [submitting, setSubmitting] = useState(false);

  // Settings panel
  const [showSettings, setShowSettings] = useState(false);
  const [notifPermission, setNotifPermission] = useState<string>(getBrowserNotifPermission());

  // Smart scheduling
  const [showSmart, setShowSmart] = useState(false);
  const [smartData, setSmartData] = useState<any>(null);
  const [smartLoading, setSmartLoading] = useState(false);
  const [creatingBlocks, setCreatingBlocks] = useState(false);

  // Sharing
  const [showShare, setShowShare] = useState(false);
  const [shares, setShares] = useState<any[]>([]);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareDays, setShareDays] = useState(7);
  const [shareTitles, setShareTitles] = useState(false);
  const [shareName, setShareName] = useState('My Availability');
  const [creatingShare, setCreatingShare] = useState(false);
  const [copiedToken, setCopiedToken] = useState('');

  // Booking pages
  const [bookingPages, setBookingPages] = useState<any[]>([]);
  const [bookingTitle, setBookingTitle] = useState('My Agenda');
  const [bookingDuration, setBookingDuration] = useState(30);
  const [creatingBooking, setCreatingBooking] = useState(false);

  // My Bookings (user view)
  const [myBookings, setMyBookings] = useState<any[]>([]);
  const [bookingsLoading, setBookingsLoading] = useState(false);
  const [bookingFilter, setBookingFilter] = useState<'upcoming' | 'past' | 'cancelled'>('upcoming');
  const [cancellingId, setCancellingId] = useState('');

  // Reminder polling
  const reminderRef = useRef<NodeJS.Timeout | null>(null);
  const notifiedRef = useRef<Set<string>>(new Set());

  /* ─── Data Loading ─── */
  const loadStatus = useCallback(async () => {
    try {
      const res = await api.get('/calendar/status');
      setStatus(res.data || {});
      if (res.data?.timezone && res.data.timezone !== userTZ) {
        setUserTZ(res.data.timezone);
      }
      return res.data;
    } catch { return null; }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadCalendars = useCallback(async () => {
    try { const res = await api.get('/calendar/calendars'); setCalendars(res.data?.calendars || []); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const loadEvents = useCallback(async () => {
    if (!user?.user_id) return;
    try { const res = await api.get(`/calendar/events/${user.user_id}`); setEvents(res.data?.events || []); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [user?.user_id]);

  const saveTZ = useCallback(async (tz: string) => {
    try { await api.put('/calendar/timezone', { timezone: tz }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      const s = await loadStatus();
      if (s?.google_connected) await Promise.all([loadCalendars(), loadEvents()]);
      else await loadEvents();
      // Auto-detect and save timezone
      const detected = detectTZ();
      setUserTZ(detected);
      saveTZ(detected);
      setLoading(false);
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id]);

  // 30-second auto-refresh for real-time calendar data
  useAutoRefresh(loadEvents, { intervalMs: 30000 });

  // Auto-sync on tab focus
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handleFocus = () => { if (status.google_connected) { loadEvents(); } };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [status.google_connected, loadEvents]);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const syncPermission = () => setNotifPermission(getBrowserNotifPermission());
    syncPermission();
    window.addEventListener('focus', syncPermission);
    return () => window.removeEventListener('focus', syncPermission);
  }, []);

  // Connected param from OAuth callback
  useEffect(() => {
    if (params?.connected) {
      Alert.alert('Google Calendar Connected', 'Your calendar is now synced! Events will appear shortly.');
      loadStatus().then(s => { if (s?.google_connected) { loadCalendars(); loadEvents(); } });
    }
    if (params?.error) {
      const errors: Record<string, string> = {
        access_denied: 'You denied access to Google Calendar. Please try again if you want to connect.',
        not_configured: 'Google Calendar is not configured on this server.',
        token_exchange_failed: 'Failed to exchange token with Google. Please try again.',
        invalid_state: 'Session expired. Please try connecting again.',
        connection_failed: 'Connection failed. Please try again.',
        missing_params: 'Invalid callback. Please try connecting again.',
      };
      Alert.alert('Connection Failed', errors[params.error as string] || `Error: ${params.error}`);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params?.connected, params?.error]);

  // Reminder polling (every 60s)
  useEffect(() => {
    const poll = async () => {
      if (!user?.user_id) return;
      try {
        const res = await api.get(`/calendar/reminders/${user.user_id}`);
        (res.data?.reminders || []).forEach((evt: any) => {
          if (!notifiedRef.current.has(evt.id)) {
            notifiedRef.current.add(evt.id);
            showBrowserNotif('Upcoming Event', `${evt.title} starts at ${fmtTime(evt.start)}`);
          }
        });
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    };
    poll();
    reminderRef.current = setInterval(poll, 60000);
    return () => { if (reminderRef.current) clearInterval(reminderRef.current); };
  }, [user?.user_id]);

  /* ─── Actions ─── */
  const handleConnect = async () => {
    if (!user?.user_id) { Alert.alert('Sign in required'); return; }
    if (!status.google_available) { Alert.alert('Not available', 'Google Calendar is not configured.'); return; }
    setConnecting(true);
    try {
      const res = await api.get('/integrations/calendar/auth');
      const url = res.data?.authorization_url;
      if (!url) throw new Error('No URL');
      if (Platform.OS === 'web' && typeof window !== 'undefined') window.location.href = url;
      else await Linking.openURL(url);
    } catch (e: any) {
      Alert.alert('Connection failed', e?.response?.data?.detail || 'Unable to connect.');
    } finally { setConnecting(false); }
  };

  const handleDisconnect = () => {
    Alert.alert('Disconnect', 'Remove Google Calendar connection?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Disconnect', style: 'destructive', onPress: async () => {
        try { await api.post('/calendar/disconnect'); setStatus((p: any) => ({ ...p, google_connected: false })); setCalendars([]); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }},
    ]);
  };

  const handleSelectCalendar = async (calId: string) => {
    try {
      await api.post('/calendar/select', { calendar_id: calId });
      setStatus((p: any) => ({ ...p, selected_calendar_id: calId }));
      await loadEvents();
    } catch { Alert.alert('Error', 'Failed to select calendar.'); }
  };

  const handleSync = async () => {
    setSyncing(true);
    try { await api.post('/calendar/sync'); await loadEvents(); } catch { Alert.alert('Sync failed'); }
    finally { setSyncing(false); }
  };

  const handleSmartAnalyze = async () => {
    if (!user?.user_id) { Alert.alert('Sign in required'); return; }
    setShowSmart(true);
    setSmartLoading(true);
    setSmartData(null);
    try {
      const res = await api.get(`/calendar/smart-suggestions/${user.user_id}`);
      setSmartData(res.data?.analysis || null);
    } catch (e: any) {
      Alert.alert('AI Error', e?.response?.data?.detail || 'Failed to analyze calendar.');
      setShowSmart(false);
    } finally { setSmartLoading(false); }
  };

  const handleAcceptSlot = (slot: any) => {
    setForm({
      title: slot.title || '', start: slot.start ? toLocalISO(new Date(slot.start)) : '',
      end: slot.end ? toLocalISO(new Date(slot.end)) : '', location: '', description: slot.reason || '',
      notes: '', reminderMinutes: 30,
    });
    setEditingId(null);
    setShowSmart(false);
    setShowForm(true);
  };

  const handleCreateFocusBlocks = async () => {
    if (!user?.user_id || !smartData?.focus_blocks?.length) return;
    setCreatingBlocks(true);
    try {
      await api.post(`/calendar/auto-focus-blocks/${user.user_id}`, { blocks: smartData.focus_blocks });
      await loadEvents();
      Alert.alert('Focus Time Added', `${smartData.focus_blocks.length} focus blocks created on your calendar.`);
      setShowSmart(false);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed to create focus blocks.'); }
    finally { setCreatingBlocks(false); }
  };

  /* ─── Share Handlers ─── */
  const loadShares = useCallback(async () => {
    if (!user?.user_id) return;
    setShareLoading(true);
    try { const res = await api.get(`/calendar/shares/${user.user_id}`); setShares(res.data?.shares || []); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setShareLoading(false); }
  }, [user?.user_id]);

  const handleOpenShare = () => { setShowShare(true); loadShares(); loadBookingPages(); loadMyBookings(); };

  const handleCreateShare = async () => {
    if (!user?.user_id) return;
    setCreatingShare(true);
    try {
      const res = await api.post('/calendar/share', { days: shareDays, show_titles: shareTitles, name: shareName });
      if (res.data?.share) setShares(prev => [res.data.share, ...prev]);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed to create share link.'); }
    finally { setCreatingShare(false); }
  };

  const handleCopyLink = (token: string) => {
    const url = `${typeof window !== 'undefined' ? (`https://${window.location.host}`) : ''}/shared-calendar/${token}`;
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(url);
      setCopiedToken(token);
      setTimeout(() => setCopiedToken(''), 2000);
    } else { Alert.alert('Share Link', url); }
  };

  const handleRevokeShare = async (token: string) => {
    try { await api.delete(`/calendar/share/${token}`); setShares(prev => prev.filter(s => s.token !== token)); }
    catch { Alert.alert('Error', 'Failed to revoke link.'); }
  };

  /* ─── Booking Handlers ─── */
  const loadBookingPages = useCallback(async () => {
    if (!user?.user_id) return;
    try { const res = await api.get(`/calendar/booking-pages/${user.user_id}`); setBookingPages(res.data?.pages || []); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [user?.user_id]);

  const handleCreateBookingPage = async () => {
    if (!user?.user_id) return;
    setCreatingBooking(true);
    try {
      const res = await api.post('/calendar/booking-page', { title: bookingTitle, durations: [bookingDuration] });
      if (res.data?.page) setBookingPages(prev => [res.data.page, ...prev]);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed to create booking page.'); }
    finally { setCreatingBooking(false); }
  };

  const handleCopyBookingLink = (token: string) => {
    const url = `${typeof window !== 'undefined' ? (`https://${window.location.host}`) : ''}/book/${token}`;
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(url);
      setCopiedToken(token);
      setTimeout(() => setCopiedToken(''), 2000);
    } else { Alert.alert('Booking Link', url); }
  };

  const handleDeleteBookingPage = async (token: string) => {
    try { await api.delete(`/calendar/booking-page/${token}`); setBookingPages(prev => prev.filter(p => p.token !== token)); }
    catch { Alert.alert('Error', 'Failed to delete.'); }
  };

  const loadMyBookings = useCallback(async () => {
    if (!user?.user_id) return;
    setBookingsLoading(true);
    try { const res = await api.get(`/calendar/bookings/${user.user_id}`); setMyBookings(res.data?.bookings || []); }
    catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch8', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setBookingsLoading(false); }
  }, [user?.user_id]);

  const handleCancelBooking = async (bookingId: string) => {
    setCancellingId(bookingId);
    try {
      await api.post(`/calendar/bookings/${bookingId}/cancel`);
      setMyBookings(prev => prev.map(b => b.booking_id === bookingId ? { ...b, status: 'cancelled' } : b));
      loadEvents();
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed to cancel.'); }
    finally { setCancellingId(''); }
  };

  const filteredBookings = useMemo(() => {
    const now = new Date().toISOString();
    return myBookings.filter(b => {
      if (bookingFilter === 'cancelled') return b.status === 'cancelled';
      if (bookingFilter === 'upcoming') return b.status !== 'cancelled' && b.start >= now;
      return b.status !== 'cancelled' && b.start < now;
    });
  }, [myBookings, bookingFilter]);

  const openNewEvent = (date?: Date) => {
    const d = date || selectedDate;
    const start = new Date(d); start.setHours(9, 0, 0, 0);
    const end = new Date(d); end.setHours(10, 0, 0, 0);
    setForm({ title: '', start: toLocalISO(start), end: toLocalISO(end), location: '', description: '', notes: '', reminderMinutes: 30 });
    setEditingId(null);
    setShowForm(true);
  };

  const openEditEvent = (evt: any) => {
    setForm({
      title: evt.title || '', start: evt.start ? toLocalISO(new Date(evt.start)) : '',
      end: evt.end ? toLocalISO(new Date(evt.end)) : '', location: evt.location || '',
      description: evt.description || '', notes: evt.notes || '',
      reminderMinutes: evt.reminders?.overrides?.[0]?.minutes || 30,
    });
    setEditingId(evt.id);
    setShowForm(true);
  };

  const handleSubmit = async () => {
    if (!user?.user_id) { Alert.alert('Sign in required'); return; }
    if (!form.title || !form.start || !form.end) { Alert.alert('Missing', 'Title, start and end are required.'); return; }
    setSubmitting(true);
    try {
      const payload = {
        title: form.title, start: new Date(form.start).toISOString(), end: new Date(form.end).toISOString(),
        location: form.location, description: form.description, notes: form.notes,
        reminder_minutes: form.reminderMinutes || undefined,
      };
      if (editingId) await api.put(`/calendar/events/${editingId}`, payload);
      else await api.post('/calendar/events', { user_id: user.user_id, ...payload });
      await loadEvents();
      setShowForm(false);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed to save.'); }
    finally { setSubmitting(false); }
  };

  const handleDelete = (id: string) => {
    Alert.alert('Delete', 'Remove this event?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try { await api.delete(`/calendar/events/${id}`); await loadEvents(); setShowForm(false); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/CalendarInner.tsx#catch9', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }},
    ]);
  };

  const handleEnableNotifications = async () => {
    const before = getBrowserNotifPermission();
    if (before === 'unsupported') {
      Alert.alert('Unsupported', 'Browser notifications are not supported on this device.');
      return;
    }

    const ok = await requestNotifPermission();
    const after = getBrowserNotifPermission();
    setNotifPermission(after);

    if (ok) {
      showBrowserNotif('Calendar Notifications Enabled', 'You will now receive reminder alerts for upcoming events.');
      Alert.alert('Enabled', 'Notifications are enabled. A test notification was sent.');
      return;
    }

    if (after === 'denied') {
      Alert.alert('Blocked', 'Notifications are blocked for this site. Open browser site settings to allow notifications.');
      return;
    }

    Alert.alert('Not enabled', 'Notifications were not enabled. You can try again from Calendar Settings.');
  };

  /* ─── Computed ─── */
  const monthGrid = useMemo(() => getMonthGrid(currentYear, currentMonth), [currentYear, currentMonth]);

  const eventsByDate = useMemo(() => {
    const map: Record<string, any[]> = {};
    events.forEach(e => {
      const d = e.start?.slice(0, 10);
      if (d) { if (!map[d]) map[d] = []; map[d].push(e); }
    });
    return map;
  }, [events]);

  const selectedDateStr = useMemo(() => {
    const y = selectedDate.getFullYear();
    const m = (selectedDate.getMonth() + 1).toString().padStart(2, '0');
    const d = selectedDate.getDate().toString().padStart(2, '0');
    return `${y}-${m}-${d}`;
  }, [selectedDate]);

  const selectedDayEvents = useMemo(() => eventsByDate[selectedDateStr] || [], [eventsByDate, selectedDateStr]);

  const upcomingEvents = useMemo(() => {
    const now = new Date().toISOString();
    return events.filter(e => e.start >= now).sort((a, b) => a.start.localeCompare(b.start)).slice(0, 20);
  }, [events]);

  const enterpriseMetrics = useMemo(() => {
    const nextEvent = upcomingEvents[0] || null;
    return {
      totalEvents: events.length,
      upcomingCount: upcomingEvents.length,
      connectedCalendars: status.google_connected ? Math.max(calendars.length, 1) : 0,
      nextEvent,
    };
  }, [events.length, upcomingEvents, status.google_connected, calendars.length]);

  const readiness = useMemo(() => {
    if (notifPermission === 'granted') {
      return {
        label: 'Reminders Active',
        subtitle: 'This browser can show event reminders.',
        toneBg: C.successSoft,
        toneText: C.successText,
        icon: 'checkmark-circle-outline' as const,
      };
    }
    if (notifPermission === 'denied') {
      return {
        label: 'Reminders Blocked',
        subtitle: 'Enable notifications in browser settings.',
        toneBg: C.errorSoft,
        toneText: C.error,
        icon: 'warning-outline' as const,
      };
    }
    if (notifPermission === 'unsupported') {
      return {
        label: 'Reminders Unsupported',
        subtitle: 'Browser notification API is unavailable.',
        toneBg: C.bgSoft,
        toneText: C.textMuted,
        icon: 'ban-outline' as const,
      };
    }
    return {
      label: 'Reminders Not Enabled',
      subtitle: 'Open Settings → Push Notifications to enable.',
      toneBg: C.warningSoft,
      toneText: C.warningText,
      icon: 'notifications-outline' as const,
    };
  }, [notifPermission, C]);

  const todayStr = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')}`;
  }, []);

  /* ─── Nav ─── */
  const prevMonth = () => { if (currentMonth === 0) { setCurrentMonth(11); setCurrentYear(y => y - 1); } else setCurrentMonth(m => m - 1); };
  const nextMonth = () => { if (currentMonth === 11) { setCurrentMonth(0); setCurrentYear(y => y + 1); } else setCurrentMonth(m => m + 1); };
  const goToday = () => { const now = new Date(); setCurrentMonth(now.getMonth()); setCurrentYear(now.getFullYear()); setSelectedDate(now); };

  /* ─── Loading ─── */
  if (loading) {
    return (
      <AppShell>
        <AgendaSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <FadeSlideIn>
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} data-testid="calendar-screen" testID="calendar-screen">
        {/* Header */}
        <View style={[s.header, { backgroundColor: C.card, borderBottomColor: C.border }]} data-testid="calendar-header" testID="calendar-header">
          <TouchableOpacity style={[s.iconBtn, { backgroundColor: C.bgSoft }]} onPress={() => router.back()} data-testid="calendar-back" testID="calendar-back">
            <Ionicons name="arrow-back" size={18} color={C.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 17, fontWeight: '800', color: C.text }} data-testid="calendar-title" testID="calendar-title">{calendarTitle === 'calendar.header.title' ? 'Calendar' : calendarTitle}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 }}>
              <Ionicons name="globe-outline" size={11} color={C.textMuted} />
              <Text style={{ fontSize: 10, color: C.textMuted }} data-testid="calendar-tz" testID="calendar-tz">{userTZ}</Text>
              {status.google_connected && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, marginLeft: 6 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.success }} />
                  <Text style={{ fontSize: 10, color: C.successText, fontWeight: '600' }}>{tx('calendar.header.synced', 'Synced')}</Text>
                </View>
              )}
            </View>

            <TouchableOpacity
              accessibilityLabel="Calendar notification readiness widget button"
              onPress={() => setShowSettings(true)}
              activeOpacity={0.88}
              style={{ marginTop: 6, alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: readiness.toneBg }}
              data-testid="calendar-notification-readiness-widget"
              testID="calendar-notification-readiness-widget"
            >
              <Ionicons name={readiness.icon} size={11} color={readiness.toneText} />
              <Text style={{ fontSize: 10, fontWeight: '700', color: readiness.toneText }} data-testid="calendar-notification-readiness-label" testID="calendar-notification-readiness-label">
                {readiness.label}
              </Text>
              <Text style={{ fontSize: 9, color: readiness.toneText, opacity: 0.9 }} data-testid="calendar-notification-readiness-subtitle" testID="calendar-notification-readiness-subtitle">
                {readiness.subtitle}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity style={[s.iconBtn, { backgroundColor: C.info }]} onPress={handleOpenShare} data-testid="calendar-share-btn" testID="calendar-share-btn">
              <Ionicons name="share-social" size={18} color={C.primaryText} />
            </TouchableOpacity>
            <TouchableOpacity style={[s.iconBtn, { backgroundColor: C.purple }]} onPress={handleSmartAnalyze} data-testid="calendar-smart-btn" testID="calendar-smart-btn">
              <Ionicons name="sparkles" size={18} color={C.primaryText} />
            </TouchableOpacity>
            <TouchableOpacity style={[s.iconBtn, { backgroundColor: C.bgSoft }]} onPress={() => setShowSettings(true)} data-testid="calendar-settings-btn" testID="calendar-settings-btn">
              <Ionicons name="settings-outline" size={18} color={C.text} />
            </TouchableOpacity>
            {status.google_connected && (
              <TouchableOpacity style={[s.iconBtn, { backgroundColor: C.primary }]} onPress={handleSync} data-testid="calendar-sync-btn" testID="calendar-sync-btn">
                {syncing ? <ActivityIndicator size="small" color={C.primaryText} /> : <Ionicons name="sync" size={18} color={C.primaryText} />}
              </TouchableOpacity>
            )}
            <TouchableOpacity style={[s.iconBtn, { backgroundColor: C.success }]} onPress={() => openNewEvent()} data-testid="calendar-add-btn" testID="calendar-add-btn">
              <Ionicons name="add" size={20} color={C.primaryText} />
            </TouchableOpacity>
          </View>
        </View>

        {/* View Tabs */}
        <View style={[s.tabBar, { backgroundColor: C.card, borderBottomColor: C.border }]} data-testid="calendar-view-tabs" testID="calendar-view-tabs">
          {(['month', 'day', 'list'] as const).map(v => (
            <TouchableOpacity key={v} style={[s.tab, viewMode === v && { backgroundColor: C.primary }]}
              onPress={() => setViewMode(v)} data-testid={`calendar-tab-${v}`} testID={`calendar-tab-${v}`}>
              <Ionicons name={v === 'month' ? 'grid-outline' : v === 'day' ? 'today-outline' : 'list-outline'} size={14}
                color={viewMode === v ? C.primaryText : C.textMuted} />
              <Text style={[s.tabText, viewMode === v && { color: C.primaryText }]}>{v.charAt(0).toUpperCase() + v.slice(1)}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: isMobile ? 12 : 20, paddingBottom: 40 }} data-testid="calendar-scroll" testID="calendar-scroll">
          <View
            style={{
              borderRadius: 16,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.card,
              padding: 14,
              marginBottom: 12,
              gap: 10,
            }}
            data-testid="calendar-command-strip"
            testID="calendar-command-strip"
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <View>
                <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }} data-testid="calendar-command-strip-title" testID="calendar-command-strip-title">
                  Enterprise Agenda Workspace
                </Text>
                <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="calendar-command-strip-subtitle" testID="calendar-command-strip-subtitle">
                  Live two-way sync and scheduling operations
                </Text>
              </View>
              <TouchableOpacity
                onPress={() => router.push('/book-meeting')}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: C.bgSoft }}
                data-testid="calendar-open-book-meeting-btn"
                testID="calendar-open-book-meeting-btn"
              >
                <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>Open My Agenda</Text>
              </TouchableOpacity>
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="calendar-command-strip-kpis" testID="calendar-command-strip-kpis">
              <View style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 10, backgroundColor: C.bgSoft }} data-testid="calendar-kpi-total-events" testID="calendar-kpi-total-events">
                <Text style={{ fontSize: 10, color: C.textMuted }}>Total Events</Text>
                <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }}>{enterpriseMetrics.totalEvents}</Text>
              </View>
              <View style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 10, backgroundColor: C.bgSoft }} data-testid="calendar-kpi-upcoming-events" testID="calendar-kpi-upcoming-events">
                <Text style={{ fontSize: 10, color: C.textMuted }}>Upcoming</Text>
                <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }}>{enterpriseMetrics.upcomingCount}</Text>
              </View>
              <View style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 10, backgroundColor: C.bgSoft }} data-testid="calendar-kpi-connected-calendars" testID="calendar-kpi-connected-calendars">
                <Text style={{ fontSize: 10, color: C.textMuted }}>Connected Calendars</Text>
                <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }}>{enterpriseMetrics.connectedCalendars}</Text>
              </View>
            </View>

            <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="calendar-next-event-summary" testID="calendar-next-event-summary">
              {enterpriseMetrics.nextEvent
                ? `Next event: ${fmtDate(enterpriseMetrics.nextEvent.start)} at ${fmtTime(enterpriseMetrics.nextEvent.start)}`
                : 'No upcoming events. Create one to start your schedule.'}
            </Text>
          </View>

          {/* Google Calendar Reconnect Banner (connection lost) */}
          {status.connection_lost && !status.google_connected && status.google_available && (
            <TouchableOpacity
              style={[s.connectBanner, { borderColor: C.warningSoft, backgroundColor: C.warningSoft }]}
              onPress={handleConnect} disabled={connecting} data-testid="calendar-reconnect-banner" testID="calendar-reconnect-banner">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: C.warningSoft, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="warning-outline" size={18} color={C.warningText} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.warningText }}>{tx('calendar.banner.disconnected', 'Google Calendar Disconnected')}</Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>Your connection was lost. Tap to reconnect now.</Text>
                </View>
              </View>
              {connecting ? <ActivityIndicator size="small" color={C.warningText} /> :
                <View style={{ backgroundColor: C.warning, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 }}>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.primaryText }}>Reconnect</Text>
                </View>}
            </TouchableOpacity>
          )}

          {/* Google Connect Banner (never connected) */}
          {!status.google_connected && status.google_available && !status.connection_lost && (
            <TouchableOpacity style={[s.connectBanner, { borderColor: C.border, backgroundColor: C.card }]}
              onPress={handleConnect} disabled={connecting} data-testid="calendar-connect-banner" testID="calendar-connect-banner">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: `${C.primary}15`, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="logo-google" size={18} color="var(--app-primary)" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{tx('calendar.banner.connectGoogle', 'Connect Google Calendar')}</Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>Tap to enable two-way sync</Text>
                </View>
              </View>
              {connecting ? <ActivityIndicator size="small" color={C.primary} /> :
                <Ionicons name="chevron-forward" size={18} color={C.textMuted} />}
            </TouchableOpacity>
          )}

          {/* ─── MONTH VIEW ─── */}
          {viewMode === 'month' && (
            <View data-testid="calendar-month-view" testID="calendar-month-view">
              {/* Month Nav */}
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <TouchableOpacity onPress={prevMonth} style={[s.iconBtn, { backgroundColor: C.bgSoft }]} data-testid="calendar-prev-month" testID="calendar-prev-month">
                  <Ionicons name="chevron-back" size={18} color={C.text} />
                </TouchableOpacity>
                <TouchableOpacity onPress={goToday} data-testid="calendar-month-label" testID="calendar-month-label">
                  <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>{MONTHS[currentMonth]} {currentYear}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={nextMonth} style={[s.iconBtn, { backgroundColor: C.bgSoft }]} data-testid="calendar-next-month" testID="calendar-next-month">
                  <Ionicons name="chevron-forward" size={18} color={C.text} />
                </TouchableOpacity>
              </View>

              {/* Day Headers */}
              <View style={{ flexDirection: 'row', marginBottom: 6 }}>
                {DAYS.map(d => (
                  <View key={d} style={{ flex: 1, alignItems: 'center' }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: C.textMuted }}>{d}</Text>
                  </View>
                ))}
              </View>

              {/* Grid */}
              {monthGrid.map((row, ri) => (
                <View key={ri} style={{ flexDirection: 'row' }}>
                  {row.map((day, ci) => {
                    if (!day) return <View key={ci} style={{ flex: 1, aspectRatio: isMobile ? 0.85 : 1, padding: 2 }} />;
                    const dateStr = `${currentYear}-${(currentMonth+1).toString().padStart(2,'0')}-${day.toString().padStart(2,'0')}`;
                    const dayEvents = eventsByDate[dateStr] || [];
                    const isToday = dateStr === todayStr;
                    const isSelected = dateStr === selectedDateStr;
                    return (
                      <TouchableOpacity key={ci} style={{ flex: 1, aspectRatio: isMobile ? 0.85 : 1, padding: 2 }}
                        onPress={() => { setSelectedDate(new Date(currentYear, currentMonth, day)); setViewMode('day'); }}
                        data-testid={`calendar-day-${dateStr}`} testID={`calendar-day-${dateStr}`}>
                        <View style={[s.dayCell, {
                          backgroundColor: isSelected ? (globalThis as any).__alphaColor(C.primary, '15') : C.card,
                          borderColor: isToday ? C.primary : C.border,
                          borderWidth: isToday ? 2 : 1,
                        }]}>
                          <Text style={[s.dayNum, { color: isToday ? C.primary : C.text, fontWeight: isToday ? '800' : '600' }]}>{day}</Text>
                          {dayEvents.length > 0 && (
                            <View style={{ flexDirection: 'row', gap: 2, flexWrap: 'wrap', marginTop: 2 }}>
                              {dayEvents.slice(0, isMobile ? 2 : 3).map((e: any, i: number) => (
                                <View key={i} style={{ height: 4, flex: 1, minWidth: 8, borderRadius: 2,
                                  backgroundColor: e.source === 'google' ? 'var(--app-primary)' : C.primary }} />
                              ))}
                            </View>
                          )}
                          {!isMobile && dayEvents.slice(0, 2).map((e: any) => (
                            <Text key={e.id} style={{ fontSize: 9, color: C.textMuted, marginTop: 1 }} numberOfLines={1}>
                              {fmtTime(e.start)} {e.title}
                            </Text>
                          ))}
                          {dayEvents.length > (isMobile ? 0 : 2) && (
                            <Text style={{ fontSize: 8, color: C.primary, fontWeight: '700', marginTop: 1 }}>
                              {isMobile ? dayEvents.length : `+${dayEvents.length - 2}`}
                            </Text>
                          )}
                        </View>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ))}
            </View>
          )}

          {/* ─── DAY VIEW ─── */}
          {viewMode === 'day' && (
            <View data-testid="calendar-day-view" testID="calendar-day-view">
              {/* Day Nav */}
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <TouchableOpacity onPress={() => setSelectedDate(d => { const n = new Date(d); n.setDate(n.getDate()-1); return n; })}
                  style={[s.iconBtn, { backgroundColor: C.bgSoft }]} data-testid="calendar-prev-day" testID="calendar-prev-day">
                  <Ionicons name="chevron-back" size={18} color={C.text} />
                </TouchableOpacity>
                <TouchableOpacity onPress={goToday} data-testid="calendar-day-label" testID="calendar-day-label">
                  <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>
                    {selectedDate.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setSelectedDate(d => { const n = new Date(d); n.setDate(n.getDate()+1); return n; })}
                  style={[s.iconBtn, { backgroundColor: C.bgSoft }]} data-testid="calendar-next-day" testID="calendar-next-day">
                  <Ionicons name="chevron-forward" size={18} color={C.text} />
                </TouchableOpacity>
              </View>

              {/* Summary */}
              <View style={[s.card, { borderColor: C.border, backgroundColor: C.card, marginBottom: 16 }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Ionicons name="today" size={16} color={C.primary} />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{selectedDayEvents.length} event{selectedDayEvents.length !== 1 ? 's' : ''}</Text>
                  <TouchableOpacity style={{ marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 4,
                    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: C.success }}
                    onPress={() => openNewEvent(selectedDate)} data-testid="calendar-day-add" testID="calendar-day-add">
                    <Ionicons name="add" size={14} color={C.primaryText} />
                    <Text style={{ fontSize: 11, fontWeight: '700', color: C.primaryText }}>Add</Text>
                  </TouchableOpacity>
                </View>
              </View>

              {/* Timeline */}
              {Array.from({ length: 14 }, (_, i) => i + 7).map(hour => {
                const slotEvents = selectedDayEvents.filter((e: any) => {
                  const h = new Date(e.start).getHours();
                  return h === hour;
                });
                return (
                  <TouchableOpacity key={hour} style={[s.timeSlot, { borderBottomColor: C.border }]}
                    onPress={() => {
                      const d = new Date(selectedDate); d.setHours(hour, 0, 0, 0);
                      openNewEvent(d);
                    }} data-testid={`calendar-slot-${hour}`} testID={`calendar-slot-${hour}`}>
                    <Text style={{ width: 44, fontSize: 11, fontWeight: '600', color: C.textMuted }}>
                      {hour.toString().padStart(2, '0')}:00
                    </Text>
                    <View style={{ flex: 1, minHeight: 44, gap: 4 }}>
                      {slotEvents.map((e: any) => (
                        <TouchableOpacity key={e.id} style={[s.eventChip, {
                          backgroundColor: (globalThis as any).__alphaColor(e.source === 'google' ? 'var(--app-primary-soft)' : C.primary, '15'),
                          borderLeftColor: e.source === 'google' ? 'var(--app-primary)' : C.primary,
                        }]} onPress={() => openEditEvent(e)} data-testid={`calendar-event-${e.id}`} testID={`calendar-event-${e.id}`}>
                          <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }} numberOfLines={1}>{e.title}</Text>
                          <Text style={{ fontSize: 10, color: C.textMuted }}>
                            {fmtTime(e.start)} - {fmtTime(e.end)}{e.location ? ` | ${e.location}` : ''}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          )}

          {/* ─── LIST VIEW ─── */}
          {viewMode === 'list' && (
            <View data-testid="calendar-list-view" testID="calendar-list-view">
              <Text style={{ fontSize: 15, fontWeight: '800', color: C.text, marginBottom: 12 }}>Upcoming Events</Text>
              {upcomingEvents.length === 0 ? (
                <View style={[s.card, { borderColor: C.border, backgroundColor: C.card, alignItems: 'center', paddingVertical: 30 }]}>
                  <Ionicons name="calendar-outline" size={32} color={C.textMuted} />
                  <Text style={{ color: C.textMuted, marginTop: 8, fontSize: 13 }}>No upcoming events</Text>
                  <TouchableOpacity style={{ marginTop: 12, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 10, backgroundColor: C.primary }}
                    onPress={() => openNewEvent()} data-testid="calendar-list-add" testID="calendar-list-add">
                    <Text style={{ color: C.primaryText, fontWeight: '700', fontSize: 12 }}>Create Event</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <View style={{ gap: 8 }}>
                  {upcomingEvents.map((e: any) => (
                    <TouchableOpacity key={e.id} style={[s.card, { borderColor: C.border, backgroundColor: C.card }]}
                      onPress={() => openEditEvent(e)} data-testid={`calendar-list-event-${e.id}`} testID={`calendar-list-event-${e.id}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
                        <View style={{ width: 44, alignItems: 'center', paddingTop: 2 }}>
                          <Text style={{ fontSize: 18, fontWeight: '800', color: C.primary }}>{new Date(e.start).getDate()}</Text>
                          <Text style={{ fontSize: 10, fontWeight: '600', color: C.textMuted }}>
                            {new Date(e.start).toLocaleDateString([], { month: 'short' })}
                          </Text>
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{e.title}</Text>
                          <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>
                            {fmtTime(e.start)} - {fmtTime(e.end)}
                          </Text>
                          {e.location ? <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 1 }}>{e.location}</Text> : null}
                        </View>
                        <View style={{ flexDirection: 'row', gap: 4 }}>
                          {e.source === 'google' && <Ionicons name="logo-google" size={12} color="var(--app-primary)" />}
                          <TouchableOpacity onPress={() => handleDelete(e.id)} data-testid={`calendar-list-delete-${e.id}`} testID={`calendar-list-delete-${e.id}`}>
                            <Ionicons name="trash-outline" size={16} color={C.error} />
                          </TouchableOpacity>
                        </View>
                      </View>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </View>
          )}
        </ScrollView>

        {/* ─── Event Form Modal ─── */}
        <Modal visible={showForm} transparent animationType="slide" data-testid="calendar-event-modal" testID="calendar-event-modal">
          <View style={s.modalOverlay}>
            <View style={[s.modalSheet, { backgroundColor: C.card, borderColor: C.border }]} data-testid="calendar-event-form" testID="calendar-event-form">
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>{editingId ? 'Edit Event' : 'New Event'}</Text>
                <TouchableOpacity onPress={() => setShowForm(false)} data-testid="calendar-form-close" testID="calendar-form-close">
                  <Ionicons name="close" size={22} color={C.textMuted} />
                </TouchableOpacity>
              </View>
              <ScrollView style={{ maxHeight: 420 }}>
                <FormField label="Title" value={form.title} onChange={v => setForm(f => ({...f, title: v}))} placeholder="Event title" C={C} testId="calendar-form-title" />
                <FormField label="Start" value={form.start} onChange={v => setForm(f => ({...f, start: v}))} placeholder="2026-02-26T09:00" type="datetime-local" C={C} testId="calendar-form-start" />
                <FormField label="End" value={form.end} onChange={v => setForm(f => ({...f, end: v}))} placeholder="2026-02-26T10:00" type="datetime-local" C={C} testId="calendar-form-end" />
                <FormField label="Location" value={form.location} onChange={v => setForm(f => ({...f, location: v}))} placeholder="Office, Zoom link..." C={C} testId="calendar-form-location" />
                <FormField label="Description" value={form.description} onChange={v => setForm(f => ({...f, description: v}))} placeholder="Details..." C={C} testId="calendar-form-desc" multiline />
                <FormField label="Notes" value={form.notes} onChange={v => setForm(f => ({...f, notes: v}))} placeholder="Personal notes..." C={C} testId="calendar-form-notes" multiline />

                {/* Reminder Picker */}
                <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 6 }}>Reminder</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 14 }} data-testid="calendar-form-reminders" testID="calendar-form-reminders">
                  {REMINDER_OPTIONS.map(opt => (
                    <TouchableOpacity key={opt.value}
                      style={[s.reminderChip, { backgroundColor: form.reminderMinutes === opt.value ? C.primary : C.bgSoft, borderColor: C.border }]}
                      onPress={() => setForm(f => ({...f, reminderMinutes: opt.value}))}
                      data-testid={`calendar-reminder-${opt.value}`} testID={`calendar-reminder-${opt.value}`}>
                      <Text style={{ fontSize: 11, fontWeight: '600', color: form.reminderMinutes === opt.value ? C.primaryText : C.textMuted }}>
                        {opt.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>

              <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
                {editingId && (
                  <TouchableOpacity style={[s.formBtn, { backgroundColor: C.errorSoft, flexGrow: 0, flexShrink: 0, paddingHorizontal: 16 }]}
                    onPress={() => handleDelete(editingId)} data-testid="calendar-form-delete" testID="calendar-form-delete">
                    <Ionicons name="trash-outline" size={16} color={C.error} />
                  </TouchableOpacity>
                )}
                <TouchableOpacity style={[s.formBtn, { backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }]}
                  onPress={() => setShowForm(false)} data-testid="calendar-form-cancel" testID="calendar-form-cancel">
                  <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.formBtn, { backgroundColor: C.primary }]}
                  onPress={handleSubmit} disabled={submitting} data-testid="calendar-form-save" testID="calendar-form-save">
                  {submitting ? <ActivityIndicator size="small" color={C.primaryText} /> :
                    <Text style={{ fontSize: 13, fontWeight: '700', color: C.primaryText }}>{editingId ? 'Update' : 'Create'}</Text>}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* ─── Settings Modal ─── */}
        <Modal visible={showSettings} transparent animationType="slide" data-testid="calendar-settings-modal" testID="calendar-settings-modal">
          <View style={s.modalOverlay}>
            <View style={[s.modalSheet, { backgroundColor: C.card, borderColor: C.border }]} data-testid="calendar-settings" testID="calendar-settings">
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>Calendar Settings</Text>
                <TouchableOpacity onPress={() => setShowSettings(false)} data-testid="calendar-settings-close" testID="calendar-settings-close">
                  <Ionicons name="close" size={22} color={C.textMuted} />
                </TouchableOpacity>
              </View>

              {/* Timezone */}
              <View style={[s.settingsRow, { borderBottomColor: C.border }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="globe-outline" size={16} color={C.primary} />
                  <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>Time Zone</Text>
                </View>
                <Text style={{ fontSize: 12, color: C.textMuted }} data-testid="calendar-settings-tz" testID="calendar-settings-tz">{userTZ}</Text>
              </View>

              {/* Google Connection */}
              <View style={[s.settingsRow, { borderBottomColor: C.border }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="logo-google" size={16} color="var(--app-primary)" />
                  <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>Google Calendar</Text>
                </View>
                {status.google_connected ? (
                  <TouchableOpacity style={{ paddingHorizontal: 12, paddingVertical: 5, borderRadius: 8, backgroundColor: C.errorSoft }}
                    onPress={handleDisconnect} data-testid="calendar-settings-disconnect" testID="calendar-settings-disconnect">
                    <Text style={{ fontSize: 11, fontWeight: '700', color: C.error }}>Disconnect</Text>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity style={{ paddingHorizontal: 12, paddingVertical: 5, borderRadius: 8, backgroundColor: C.primary }}
                    onPress={handleConnect} data-testid="calendar-settings-connect" testID="calendar-settings-connect">
                    <Text style={{ fontSize: 11, fontWeight: '700', color: C.primaryText }}>Connect</Text>
                  </TouchableOpacity>
                )}
              </View>

              {/* Calendar Selection */}
              {status.google_connected && calendars.length > 0 && (
                <View style={{ marginTop: 12 }}>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    Select Calendar
                  </Text>
                  {calendars.map((cal: any) => {
                    const active = status.selected_calendar_id === cal.id || (!status.selected_calendar_id && cal.primary);
                    return (
                      <TouchableOpacity key={cal.id} style={[s.calRow, { borderColor: C.border, backgroundColor: active ? (globalThis as any).__alphaColor(C.primary, '10') : 'transparent' }]}
                        onPress={() => handleSelectCalendar(cal.id)} data-testid={`calendar-settings-cal-${cal.id}`} testID={`calendar-settings-cal-${cal.id}`}>
                        <View>
                          <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{cal.summary}</Text>
                          <Text style={{ fontSize: 10, color: C.textMuted }}>{cal.timeZone}</Text>
                        </View>
                        {active && <Ionicons name="checkmark-circle" size={18} color={C.primary} />}
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}

              {/* Notifications */}
              <View style={[s.settingsRow, { borderBottomColor: C.border, marginTop: 12 }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="notifications-outline" size={16} color={C.warningText} />
                  <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>Push Notifications</Text>
                </View>
                <Text
                  style={{ fontSize: 11, color: notifPermission === 'granted' ? C.successText : notifPermission === 'denied' ? C.error : C.textMuted, marginLeft: 'auto', marginRight: 8 }}
                  data-testid="calendar-settings-notif-status"
                  testID="calendar-settings-notif-status"
                >
                  {notifPermission === 'granted' ? 'Enabled' : notifPermission === 'denied' ? 'Blocked' : notifPermission === 'unsupported' ? 'Unsupported' : 'Not enabled'}
                </Text>
                <TouchableOpacity style={{ paddingHorizontal: 12, paddingVertical: 5, borderRadius: 8, backgroundColor: C.bgSoft }}
                  onPress={handleEnableNotifications}
                  data-testid="calendar-settings-notif" testID="calendar-settings-notif">
                  <Text style={{ fontSize: 11, fontWeight: '600', color: C.text }}>
                    {notifPermission === 'granted' ? 'Send Test' : notifPermission === 'denied' ? 'Fix in Browser' : 'Enable'}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        {/* ─── Smart Schedule Modal ─── */}
        <Modal visible={showSmart} transparent animationType="slide" data-testid="smart-schedule-modal" testID="smart-schedule-modal">
          <View style={s.modalOverlay}>
            <View style={[s.modalSheet, { backgroundColor: C.card, borderColor: C.border, maxHeight: '90%' }]} data-testid="smart-schedule-panel" testID="smart-schedule-panel">
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="sparkles" size={18} color={C.purpleText} />
                  <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>Smart Schedule</Text>
                </View>
                <TouchableOpacity onPress={() => setShowSmart(false)} data-testid="smart-close" testID="smart-close">
                  <Ionicons name="close" size={22} color={C.textMuted} />
                </TouchableOpacity>
              </View>

              {smartLoading ? (
                <View style={{ alignItems: 'center', paddingVertical: 40 }}>
                  <ActivityIndicator size="large" color={C.purpleText} />
                  <Text style={{ color: C.textMuted, marginTop: 12, fontSize: 13 }}>Analyzing your calendar patterns...</Text>
                </View>
              ) : smartData ? (
                <ScrollView style={{ maxHeight: 500 }}>
                  {/* Busy Score */}
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16,
                    padding: 14, borderRadius: 12, backgroundColor: C.bgSoft }} data-testid="smart-busy-score" testID="smart-busy-score">
                    <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: (smartData.busy_score || 0) > 60 ? C.errorSoft : C.successSoft,
                      alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ fontSize: 18, fontWeight: '800', color: (smartData.busy_score || 0) > 60 ? C.error : C.success }}>
                        {smartData.busy_score || 0}
                      </Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>Busy Score</Text>
                      <Text style={{ fontSize: 11, color: C.textMuted }}>{smartData.recommendation || 'Looking good!'}</Text>
                    </View>
                  </View>

                  {/* Patterns */}
                  {smartData.patterns?.length > 0 && (
                    <View style={{ marginBottom: 16 }}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Patterns Detected</Text>
                      {smartData.patterns.map((p: string, i: number) => (
                        <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
                          <Ionicons name="bulb-outline" size={14} color={C.warningText} style={{ marginTop: 1 }} />
                          <Text style={{ fontSize: 12, color: C.text, flex: 1 }}>{p}</Text>
                        </View>
                      ))}
                    </View>
                  )}

                  {/* Suggested Slots */}
                  {smartData.suggested_slots?.length > 0 && (
                    <View style={{ marginBottom: 16 }}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Suggested Time Slots</Text>
                      {smartData.suggested_slots.map((slot: any, i: number) => (
                        <View key={i} style={{ padding: 12, borderRadius: 10, backgroundColor: C.bgSoft, marginBottom: 8, borderLeftWidth: 3,
                          borderLeftColor: slot.type === 'focus' ? C.purple : slot.type === 'exercise' ? C.success : C.primary }}
                          data-testid={`smart-slot-${i}`} testID={`smart-slot-${i}`}>
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                            <View style={{ flex: 1 }}>
                              <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{slot.title}</Text>
                              <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>
                                {slot.start ? fmtDate(slot.start) : ''} {slot.start ? fmtTime(slot.start) : ''} - {slot.end ? fmtTime(slot.end) : ''}
                              </Text>
                              <Text style={{ fontSize: 10, color: C.textMuted, marginTop: 2 }}>{slot.reason}</Text>
                            </View>
                            <TouchableOpacity style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: C.primary }}
                              onPress={() => handleAcceptSlot(slot)} data-testid={`smart-accept-${i}`} testID={`smart-accept-${i}`}>
                              <Text style={{ fontSize: 11, fontWeight: '700', color: C.primaryText }}>Add</Text>
                            </TouchableOpacity>
                          </View>
                        </View>
                      ))}
                    </View>
                  )}

                  {/* Focus Blocks */}
                  {smartData.focus_blocks?.length > 0 && (
                    <View style={{ marginBottom: 16 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 }}>Focus Time Blocks</Text>
                        <TouchableOpacity style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6,
                          borderRadius: 8, backgroundColor: C.purple }}
                          onPress={handleCreateFocusBlocks} disabled={creatingBlocks} data-testid="smart-create-focus-blocks" testID="smart-create-focus-blocks">
                          {creatingBlocks ? <ActivityIndicator size="small" color={C.primaryText} /> :
                            <><Ionicons name="add-circle" size={14} color={C.primaryText} /><Text style={{ fontSize: 11, fontWeight: '700', color: C.primaryText }}>Add All</Text></>}
                        </TouchableOpacity>
                      </View>
                      {smartData.focus_blocks.map((block: any, i: number) => (
                        <View key={i} style={{ padding: 12, borderRadius: 10, backgroundColor: C.purpleSoft, marginBottom: 6,
                          borderLeftWidth: 3, borderLeftColor: C.purple }} data-testid={`smart-focus-${i}`} testID={`smart-focus-${i}`}>
                          <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }}>{block.title}</Text>
                          <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>
                            {block.start ? fmtDate(block.start) : ''} {block.start ? fmtTime(block.start) : ''} - {block.end ? fmtTime(block.end) : ''}
                          </Text>
                          <Text style={{ fontSize: 10, color: C.textMuted, marginTop: 2 }}>{block.reason}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                </ScrollView>
              ) : null}
            </View>
          </View>
        </Modal>

        {/* ─── Share Modal ─── */}
        <Modal visible={showShare} transparent animationType="slide" data-testid="share-modal" testID="share-modal">
          <View style={s.modalOverlay}>
            <View style={[s.modalSheet, { backgroundColor: C.card, borderColor: C.border, maxHeight: '85%' }]} data-testid="share-panel" testID="share-panel">
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="share-social" size={18} color={C.info} />
                  <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>Share Calendar</Text>
                </View>
                <TouchableOpacity onPress={() => setShowShare(false)} data-testid="share-close" testID="share-close">
                  <Ionicons name="close" size={22} color={C.textMuted} />
                </TouchableOpacity>
              </View>

              <ScrollView style={{ maxHeight: 450 }}>
                {/* Create New Share */}
                <View style={{ padding: 14, borderRadius: 12, backgroundColor: C.bgSoft, marginBottom: 16 }} data-testid="share-create-section" testID="share-create-section">
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10 }}>Create Share Link</Text>

                  <Text style={{ fontSize: 11, fontWeight: '600', color: C.textMuted, marginBottom: 6 }}>Link Name</Text>
                  <TextInput
                    style={{ borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, fontSize: 13, color: C.text, backgroundColor: C.card, marginBottom: 12 }}
                    value={shareName} onChangeText={setShareName} placeholder="My Availability"
                    placeholderTextColor={C.textMuted} data-testid="share-name-input" testID="share-name-input" />

                  <Text style={{ fontSize: 11, fontWeight: '600', color: C.textMuted, marginBottom: 6 }}>Duration</Text>
                  <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12 }} data-testid="share-days-picker" testID="share-days-picker">
                    {[7, 14, 30].map(d => (
                      <TouchableOpacity key={d} style={{
                        flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center',
                        backgroundColor: shareDays === d ? C.info : C.card, borderWidth: 1, borderColor: C.border,
                      }} onPress={() => setShareDays(d)} data-testid={`share-days-${d}`} testID={`share-days-${d}`}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: shareDays === d ? C.primaryText : C.textMuted }}>{d} days</Text>
                      </TouchableOpacity>
                    ))}
                  </View>

                  <TouchableOpacity style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}
                    onPress={() => setShareTitles(!shareTitles)} data-testid="share-titles-toggle" testID="share-titles-toggle">
                    <View style={{
                      width: 20, height: 20, borderRadius: 4, borderWidth: 2,
                      borderColor: shareTitles ? C.info : C.border,
                      backgroundColor: shareTitles ? C.info : 'transparent',
                      alignItems: 'center', justifyContent: 'center',
                    }}>
                      {shareTitles && <Ionicons name="checkmark" size={14} color={C.primaryText} />}
                    </View>
                    <Text style={{ fontSize: 12, color: C.text }}>Show event titles (otherwise shows "Busy")</Text>
                  </TouchableOpacity>

                  <TouchableOpacity style={{
                    backgroundColor: C.info, paddingVertical: 10, borderRadius: 10, alignItems: 'center',
                  }} onPress={handleCreateShare} disabled={creatingShare} data-testid="share-create-btn" testID="share-create-btn">
                    {creatingShare ? <ActivityIndicator size="small" color={C.primaryText} /> :
                      <Text style={{ fontSize: 13, fontWeight: '700', color: C.primaryText }}>Generate Link</Text>}
                  </TouchableOpacity>
                </View>

                {/* Active Share Links */}
                {shareLoading ? <ActivityIndicator size="small" color={C.primary} /> : (
                  shares.length > 0 && (
                    <View data-testid="share-links-list" testID="share-links-list">
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Active Links</Text>
                      {shares.map((sh: any) => (
                        <View key={sh.token} style={{
                          padding: 12, borderRadius: 10, backgroundColor: C.bgSoft, marginBottom: 8,
                          borderWidth: 1, borderColor: C.border,
                        }} data-testid={`share-link-${sh.token}`} testID={`share-link-${sh.token}`}>
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{sh.name}</Text>
                            <View style={{ flexDirection: 'row', gap: 6 }}>
                              <TouchableOpacity style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: copiedToken === sh.token ? C.success : C.info }}
                                onPress={() => handleCopyLink(sh.token)} data-testid={`share-copy-${sh.token}`} testID={`share-copy-${sh.token}`}>
                                <Text style={{ fontSize: 10, fontWeight: '700', color: C.primaryText }}>{copiedToken === sh.token ? 'Copied!' : 'Copy'}</Text>
                              </TouchableOpacity>
                              <TouchableOpacity style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: C.errorSoft }}
                                onPress={() => handleRevokeShare(sh.token)} data-testid={`share-revoke-${sh.token}`} testID={`share-revoke-${sh.token}`}>
                                <Ionicons name="trash-outline" size={12} color={C.error} />
                              </TouchableOpacity>
                            </View>
                          </View>
                          <Text style={{ fontSize: 10, color: C.textMuted }}>
                            {sh.days} days | {sh.show_titles ? 'Titles visible' : 'Busy/Free only'} | Created {new Date(sh.created_at).toLocaleDateString()}
                          </Text>
                        </View>
                      ))}
                    </View>
                  )
                )}

                {/* Booking Links Section */}
                <View style={{ marginTop: 20, paddingTop: 16, borderTopWidth: 1, borderTopColor: C.border }} data-testid="booking-section" testID="booking-section">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Ionicons name="videocam" size={16} color={C.indigoText} />
                    <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>Meeting Booking Links</Text>
                  </View>
                  <Text style={{ fontSize: 11, color: C.textMuted, marginBottom: 12 }}>Let anyone book a time slot on your calendar</Text>

                  <View style={{ padding: 14, borderRadius: 12, backgroundColor: C.bgSoft, marginBottom: 12 }}>
                    <Text style={{ fontSize: 11, fontWeight: '600', color: C.textMuted, marginBottom: 6 }}>Page Title</Text>
                    <TextInput
                      style={{ borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, fontSize: 13, color: C.text, backgroundColor: C.card, marginBottom: 10 }}
                      value={bookingTitle} onChangeText={setBookingTitle} placeholder="My Agenda" placeholderTextColor={C.textMuted}
                      data-testid="booking-title-input" testID="booking-title-input" />

                    <Text style={{ fontSize: 11, fontWeight: '600', color: C.textMuted, marginBottom: 6 }}>Meeting Duration</Text>
                    <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12 }}>
                      {[15, 30, 60].map(d => (
                        <TouchableOpacity key={d} style={{
                          flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center',
                          backgroundColor: bookingDuration === d ? C.indigo : C.card, borderWidth: 1, borderColor: C.border,
                        }} onPress={() => setBookingDuration(d)} data-testid={`booking-dur-${d}`} testID={`booking-dur-${d}`}>
                          <Text style={{ fontSize: 12, fontWeight: '700', color: bookingDuration === d ? C.primaryText : C.textMuted }}>{d} min</Text>
                        </TouchableOpacity>
                      ))}
                    </View>

                    <TouchableOpacity style={{ backgroundColor: C.indigo, paddingVertical: 10, borderRadius: 10, alignItems: 'center' }}
                      onPress={handleCreateBookingPage} disabled={creatingBooking} data-testid="booking-create-btn" testID="booking-create-btn">
                      {creatingBooking ? <ActivityIndicator size="small" color={C.primaryText} /> :
                        <Text style={{ fontSize: 13, fontWeight: '700', color: C.primaryText }}>Create Booking Page</Text>}
                    </TouchableOpacity>
                  </View>

                  {/* Active Booking Pages */}
                  {bookingPages.length > 0 && (
                    <View data-testid="booking-pages-list" testID="booking-pages-list">
                      <Text style={{ fontSize: 11, fontWeight: '700', color: C.textMuted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>Active Booking Pages</Text>
                      {bookingPages.map((pg: any) => (
                        <View key={pg.token} style={{
                          padding: 12, borderRadius: 10, backgroundColor: C.bgSoft, marginBottom: 6,
                          borderWidth: 1, borderColor: C.border,
                        }} data-testid={`booking-page-${pg.token}`} testID={`booking-page-${pg.token}`}>
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                            <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>{pg.title}</Text>
                            <View style={{ flexDirection: 'row', gap: 6 }}>
                              <TouchableOpacity style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: copiedToken === pg.token ? C.success : C.indigo }}
                                onPress={() => handleCopyBookingLink(pg.token)} data-testid={`booking-copy-${pg.token}`} testID={`booking-copy-${pg.token}`}>
                                <Text style={{ fontSize: 10, fontWeight: '700', color: C.primaryText }}>{copiedToken === pg.token ? 'Copied!' : 'Copy'}</Text>
                              </TouchableOpacity>
                              <TouchableOpacity style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: C.errorSoft }}
                                onPress={() => handleDeleteBookingPage(pg.token)} data-testid={`booking-delete-${pg.token}`} testID={`booking-delete-${pg.token}`}>
                                <Ionicons name="trash-outline" size={12} color={C.error} />
                              </TouchableOpacity>
                            </View>
                          </View>
                          <Text style={{ fontSize: 10, color: C.textMuted }}>{pg.durations?.[0] || 30} min | {pg.available_start}:00 - {pg.available_end}:00 | {pg.owner_timezone}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                </View>

                {/* My Bookings Section */}
                <View style={{ marginTop: 20, paddingTop: 16, borderTopWidth: 1, borderTopColor: C.border }} data-testid="my-bookings-section" testID="my-bookings-section">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Ionicons name="people" size={16} color={C.successText} />
                    <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>My Bookings</Text>
                    <TouchableOpacity onPress={loadMyBookings} style={{ marginLeft: 'auto', padding: 4 }} data-testid="bookings-refresh" testID="bookings-refresh">
                      <Ionicons name="refresh" size={14} color={C.textMuted} />
                    </TouchableOpacity>
                  </View>

                  {/* Filter tabs */}
                  <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12 }}>
                    {([
                      { key: 'upcoming' as const, label: 'Upcoming', icon: 'arrow-forward' },
                      { key: 'past' as const, label: 'Past', icon: 'time' },
                      { key: 'cancelled' as const, label: 'Cancelled', icon: 'close-circle' },
                    ]).map(f => (
                      <TouchableOpacity key={f.key} accessibilityLabel="f.label" onPress={() => setBookingFilter(f.key)} style={{
                        flex: 1, flexDirection: 'row', gap: 4, alignItems: 'center', justifyContent: 'center',
                        paddingVertical: 7, borderRadius: 8,
                        backgroundColor: bookingFilter === f.key ? (f.key === 'cancelled' ? C.errorSoft : C.successSoft) : C.bgSoft,
                        borderWidth: 1, borderColor: bookingFilter === f.key ? (f.key === 'cancelled' ? C.error : C.success) : C.border,
                      }} data-testid={`bookings-filter-${f.key}`} testID={`bookings-filter-${f.key}`}>
                        <Ionicons name={f.icon as any} size={12} color={bookingFilter === f.key ? (f.key === 'cancelled' ? C.error : C.success) : C.textMuted} />
                        <Text style={{ fontSize: 11, fontWeight: '600', color: bookingFilter === f.key ? (f.key === 'cancelled' ? C.error : C.success) : C.textMuted }}>{f.label}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>

                  {bookingsLoading ? (
                    <ActivityIndicator size="small" color={C.textMuted} style={{ paddingVertical: 20 }} />
                  ) : filteredBookings.length === 0 ? (
                    <View style={{ paddingVertical: 20, alignItems: 'center' }}>
                      <Ionicons name={bookingFilter === 'cancelled' ? 'close-circle-outline' : 'calendar-outline'} size={24} color={C.textMuted} />
                      <Text style={{ fontSize: 12, color: C.textMuted, marginTop: 6 }}>
                        {bookingFilter === 'upcoming' ? 'No upcoming bookings' : bookingFilter === 'past' ? 'No past bookings' : 'No cancelled bookings'}
                      </Text>
                    </View>
                  ) : (
                    <View data-testid="bookings-list" testID="bookings-list">
                      {filteredBookings.map((bk: any) => {
                        const isUpcoming = bk.start >= new Date().toISOString() && bk.status !== 'cancelled';
                        return (
                          <View key={bk.booking_id} style={{
                            padding: 12, borderRadius: 10, backgroundColor: C.bgSoft, marginBottom: 6,
                            borderWidth: 1, borderColor: C.border,
                            opacity: bk.status === 'cancelled' ? 0.6 : 1,
                          }} data-testid={`booking-item-${bk.booking_id}`} testID={`booking-item-${bk.booking_id}`}>
                            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 }}>
                                <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: bk.status === 'cancelled' ? C.errorSoft : C.indigoSoft, alignItems: 'center', justifyContent: 'center' }}>
                                  <Ionicons name={bk.status === 'cancelled' ? 'close' : 'person'} size={14} color={bk.status === 'cancelled' ? C.error : C.indigo} />
                                </View>
                                <View style={{ flex: 1 }}>
                                  <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }} numberOfLines={1}>{bk.guest_name}</Text>
                                  <Text style={{ fontSize: 10, color: C.textMuted }}>{bk.guest_email}</Text>
                                </View>
                              </View>
                              {bk.status === 'cancelled' ? (
                                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: C.errorSoft }}>
                                  <Text style={{ fontSize: 9, fontWeight: '700', color: C.error }}>CANCELLED</Text>
                                </View>
                              ) : isUpcoming ? (
                                <TouchableOpacity
                                  style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: C.errorSoft }}
                                  onPress={() => handleCancelBooking(bk.booking_id)}
                                  disabled={cancellingId === bk.booking_id}
                                  data-testid={`cancel-booking-${bk.booking_id}`} testID={`cancel-booking-${bk.booking_id}`}
                                >
                                  {cancellingId === bk.booking_id ? (
                                    <ActivityIndicator size="small" color={C.error} />
                                  ) : (
                                    <Text style={{ fontSize: 10, fontWeight: '700', color: C.error }}>Cancel</Text>
                                  )}
                                </TouchableOpacity>
                              ) : (
                                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: C.successSoft }}>
                                  <Text style={{ fontSize: 9, fontWeight: '700', color: C.successText }}>COMPLETED</Text>
                                </View>
                              )}
                            </View>
                            <View style={{ flexDirection: 'row', gap: 12, marginTop: 6 }}>
                              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                                <Ionicons name="calendar" size={11} color={C.textMuted} />
                                <Text style={{ fontSize: 10, color: C.textMuted }}>{fmtDate(bk.start)}</Text>
                              </View>
                              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                                <Ionicons name="time" size={11} color={C.textMuted} />
                                <Text style={{ fontSize: 10, color: C.textMuted }}>{fmtTime(bk.start)} - {fmtTime(bk.end)}</Text>
                              </View>
                              {bk.reminder_sent && (
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                                  <Ionicons name="notifications" size={10} color={C.warningText} />
                                  <Text style={{ fontSize: 9, color: C.warningText }}>Reminded</Text>
                                </View>
                              )}
                            </View>
                          </View>
                        );
                      })}
                    </View>
                  )}
                </View>
              </ScrollView>
            </View>
          </View>
        </Modal>
      </SafeAreaView>
      </FadeSlideIn>
    </AppShell>
  );
}

/* ─── Form Field Component ─── */
function FormField({ label, value, onChange, placeholder, type, C, testId, multiline }: {
  label: string; value: string; onChange: (v: string) => void; placeholder: string;
  type?: string; C: any; testId: string; multiline?: boolean;
}) {
  const isWeb = Platform.OS === 'web';
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 4 }}>{label}</Text>
      {isWeb && (type === 'datetime-local') ? (
        <input
          type="datetime-local"
          value={value}
          onChange={(e: any) => onChange(e.target.value)}
          placeholder={placeholder}
          data-testid={testId}
          style={{
            width: '100%', padding: 10, borderRadius: 10, border: `1px solid ${C.border}`,
            backgroundColor: C.bgSoft, color: C.text, fontSize: 13, fontFamily: 'inherit',
            outline: 'none', boxSizing: 'border-box',
          }}
        />
      ) : (
        <TextInput accessibilityLabel="Text input"
          style={{
            borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 12,
            paddingVertical: 10, fontSize: 13, color: C.text, backgroundColor: C.bgSoft,
            ...(multiline ? { minHeight: 60, textAlignVertical: 'top' } : {}),
          }}
          placeholder={placeholder} placeholderTextColor={C.textMuted}
          value={value} onChangeText={onChange} multiline={multiline}
          data-testid={testId} testID={testId} dataSet={{ testid: testId }}
        />
      )}
    </View>
  );
}

/* ─── Styles ─── */
const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: 1 },
  iconBtn: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  tabBar: { flexDirection: 'row', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderBottomWidth: 1 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 7, borderRadius: 8 },
  tabText: { fontSize: 12, fontWeight: '600', color: 'var(--app-primary)' }, // @theme-ok reviewed semantic hex
  connectBanner: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, borderRadius: 14, borderWidth: 1, marginBottom: 16 },
  card: { borderRadius: 14, borderWidth: 1, padding: 14 },
  dayCell: { flex: 1, borderRadius: 8, padding: 4, minHeight: 44, overflow: 'hidden' },
  dayNum: { fontSize: 12, textAlign: 'center' },
  timeSlot: { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 8, borderBottomWidth: 1 },
  eventChip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderLeftWidth: 3 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  modalSheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, borderWidth: 1, maxHeight: '85%' },
  formBtn: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 12, borderRadius: 12 },
  reminderChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  settingsRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 14, borderBottomWidth: 1 },
  calRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 6 },
});
