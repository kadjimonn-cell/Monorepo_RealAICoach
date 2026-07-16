import React, { useEffect, useState, useMemo } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, StyleSheet, Alert, Linking, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import api, { setCachedToken } from '../../src/services/api';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AgendaSkeleton } from '../../src/components/SkeletonLoaders';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

const API_BASE = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.EXPO_PUBLIC_BACKEND_URL || '');

const fmtTime = (s: string) => {
  try { return new Date(s).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return s; }
};

export default function BookingPage() {
  const { t } = useTranslation();
  t('i18n.route.book.[token].probe');
  const { token } = useLocalSearchParams();
  const _router = useRouter();
  const { colors } = useTheme();

  // @autofix-moved: was module-level const makeStyles
  function makeStyles(colors: any) { return StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', padding: 20 },
    titleText: { fontSize: 20, fontWeight: '800', color: colors.text, marginBottom: 4 },
    subText: { fontSize: 13, color: colors.textMuted, marginTop: 4 },
    header: { alignItems: 'center', paddingVertical: 24, marginBottom: 8 },
    chip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: colors.surface },
    chipText: { fontSize: 11, color: colors.textMuted, fontWeight: '600' },
    sectionLabel: { fontSize: 13, fontWeight: '700', color: colors.textSec, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 },
    dateBtn: { width: 64, paddingVertical: 12, borderRadius: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface, alignItems: 'center', gap: 2 },
    dateDow: { fontSize: 10, fontWeight: '600', color: colors.textMuted },
    dateDay: { fontSize: 18, fontWeight: '800', color: colors.textSec },
    dateMon: { fontSize: 10, fontWeight: '600', color: colors.textMuted },
    emptySlots: { alignItems: 'center', paddingVertical: 24, gap: 8 },
    slotBtn: { paddingHorizontal: 18, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface },
    slotText: { fontSize: 13, fontWeight: '700', color: colors.textSec },
    formCard: { backgroundColor: colors.surface, borderRadius: 16, padding: 18, borderWidth: 1, borderColor: colors.surface, marginBottom: 16 },
    selectedSlotBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.primarySoft, marginBottom: 14 },
    input: { borderWidth: 1, borderColor: colors.surface, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: colors.textSec, backgroundColor: colors.surface, marginBottom: 10 },
    bookBtn: { backgroundColor: colors.primary, paddingVertical: 14, borderRadius: 12, alignItems: 'center', marginTop: 6 },
    confirmCard: { alignItems: 'center', padding: 30, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface, maxWidth: 400, width: '100%' },
    confirmDetails: { marginTop: 16, gap: 8, width: '100%' },
    confirmRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
    confirmText: { fontSize: 13, color: colors.textSec },
    icsBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: colors.success, paddingVertical: 12, paddingHorizontal: 20, borderRadius: 12, marginTop: 20, width: '100%' },
    icsBtnText: { fontSize: 13, fontWeight: '700', color: colors.primaryText, marginLeft: 6 },
    emailNotice: { flexDirection: 'row', alignItems: 'center', marginTop: 14, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.primarySoft },
    emailNoticeText: { fontSize: 12, color: colors.textMuted, marginLeft: 6, flex: 1 },
    recurrenceBtn: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface },
    recurrenceBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
    recurrenceBtnText: { fontSize: 12, fontWeight: '700', color: colors.textMuted },
    countBtn: { width: 40, height: 36, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface },
    countBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
    countBtnText: { fontSize: 13, fontWeight: '700', color: colors.textMuted },
    recurrenceSummary: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.primarySoft },
    authToggle: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
    authToggleActive: { backgroundColor: colors.primary },
    authToggleText: { fontSize: 13, fontWeight: '700', color: colors.textMuted },
    googleBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: colors.primary, borderRadius: 14, padding: 14 },
  }); }
  const s = useMemo(() => makeStyles(colors), [colors]);

  // Direct auth check - bypasses AuthContext for reliable state on public routes
  const [checkedUser, setCheckedUser] = useState<any>(undefined); // undefined=checking, null=no auth, object=authed
  useEffect(() => {
    AsyncStorage.getItem('session_token').then(t => {
      if (t) {
        setCachedToken(t);
        api.get('/auth/me').then(r => setCheckedUser(r.data)).catch(() => setCheckedUser(null));
      } else {
        setCheckedUser(null);
      }
    }).catch(() => setCheckedUser(null));
  }, []);

  const [page, setPage] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Date & slots
  const [selectedDate, setSelectedDate] = useState('');
  const [slots, setSlots] = useState<any[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [recoverableBookingError, setRecoverableBookingError] = useState('');

  // Booking form
  const [selectedSlot, setSelectedSlot] = useState<any>(null);
  const [guestName, setGuestName] = useState('');
  const [guestEmail, setGuestEmail] = useState('');
  const [booking, setBooking] = useState(false);
  const [confirmed, setConfirmed] = useState<any>(null);
  const [allBookings, setAllBookings] = useState<any[]>([]);

  // Recurrence
  const [recurrenceType, setRecurrenceType] = useState('none');
  const [recurrenceCount, setRecurrenceCount] = useState(4);

  // Inline auth
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authName, setAuthName] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  // Generate next 14 dates
  const dates = useMemo(() => {
    const d: string[] = [];
    const now = new Date();
    const ahead = page?.days_ahead || 14;
    for (let i = 0; i < ahead; i++) {
      const dt = new Date(now); dt.setDate(now.getDate() + i);
      const dow = dt.getDay();
      if (dow !== 0 && dow !== 6) { // Skip weekends
        d.push(dt.toISOString().slice(0, 10));
      }
    }
    return d;
  }, [page]);

  useEffect(() => {
    if (!token) { setError('Invalid booking link'); setLoading(false); return; }
    (async () => {
      try {
        const res = await api.get(`/calendar/booking/${token}`);
        setPage(res.data?.page || null);
      } catch (e: any) {
        const message = e?.response?.data?.detail || 'Booking page not found';
        handleAppRecoverableError({
          scope: 'book.token.load-page',
          error: e,
          message,
          setError,
          onRetry: () => { if (typeof window !== 'undefined') window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        setError(message);
      }
      finally { setLoading(false); }
    })();
  }, [token]);

  // Auto-fill name/email when user is authenticated
  useEffect(() => {
    if (checkedUser) {
      setGuestName(checkedUser.name || '');
      setGuestEmail(checkedUser.email || '');
    }
  }, [checkedUser]);

  const loadSlots = async (date: string) => {
    setSelectedDate(date);
    setSelectedSlot(null);
    setSlotsLoading(true);
    try {
      const res = await api.get(`/calendar/booking/${token}?date=${date}`);
      setSlots(res.data?.slots || []);
      setRecoverableBookingError('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'book.token.load-slots',
        error,
        message: 'Unable to load available slots right now.',
        setError: setRecoverableBookingError,
        onRetry: () => { void loadSlots(date); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setSlots([]);
    }
    finally { setSlotsLoading(false); }
  };

  const handleInlineAuth = async () => {
    if (!authEmail.trim() || !authPassword.trim()) {
      setAuthError('Email and password are required');
      return;
    }
    setAuthLoading(true);
    setAuthError('');
    try {
      if (authMode === 'register') {
        if (!authName.trim()) { setAuthError('Name is required'); setAuthLoading(false); return; }
        await api.post('/auth/register', { email: authEmail.trim(), password: authPassword, name: authName.trim() });
      }
      const res = await api.post('/auth/login', { email: authEmail.trim(), password: authPassword });
      const { session_token, ..._userData } = res.data;
      await AsyncStorage.setItem('session_token', session_token);
      setCachedToken(session_token);
      // Reload user state - force page to re-render with auth
      window.location.reload();
    } catch (e: any) {
      setAuthError(e?.response?.data?.detail || (authMode === 'register' ? 'Registration failed' : 'Invalid credentials'));
    } finally { setAuthLoading(false); }
  };

  const handleGoogleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = (`https://${window.location.host}`) + `/book/${token}`;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleBook = async () => {
    if (!selectedSlot || !guestName.trim() || !guestEmail.trim()) {
      Alert.alert('Missing Info', 'Please enter your name and email.');
      return;
    }
    setBooking(true);
    try {
      const res = await api.post(`/calendar/booking/${token}/book`, {
        name: guestName.trim(), email: guestEmail.trim(),
        start: selectedSlot.start, end: selectedSlot.end,
        recurrence_type: recurrenceType,
        recurrence_count: recurrenceType !== 'none' ? recurrenceCount : 1,
      });
      setConfirmed(res.data?.booking);
      setAllBookings(res.data?.all_bookings || [res.data?.booking]);
      setRecoverableBookingError('');
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Unable to book this slot.';
      handleAppRecoverableError({
        scope: 'book.token.submit-booking',
        error: e,
        message,
        setError: setRecoverableBookingError,
        onRetry: () => { void handleBook(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      Alert.alert('Booking Failed', message);
    } finally { setBooking(false); }
  };

  if (loading) {
    return (
      <SafeAreaView style={[s.container, { backgroundColor: colors.bg }]} data-testid="booking-loading" testID="booking-loading">
        <AgendaSkeleton />
      </SafeAreaView>
    );
  }

  if (error || !page) {
    return (
      <SafeAreaView style={[s.container, { backgroundColor: colors.bg }]} data-testid="booking-error" testID="booking-error">
        <Ionicons name="calendar-outline" size={48} color={colors.textMuted} />
        <Text style={s.titleText}>Booking Not Found</Text>
        <Text style={s.subText}>{error}</Text>
      </SafeAreaView>
    );
  }

  if (confirmed) {
    const icsUrl = `${API_BASE}/api/calendar/booking/ics/${confirmed.booking_id || ''}`;
    const isRecurring = allBookings.length > 1;
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} data-testid="booking-confirmed" testID="booking-confirmed">
        <ScrollView contentContainerStyle={{ flexGrow: 1, alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <View style={s.confirmCard}>
            <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
              <Ionicons name="checkmark-circle" size={32} color={colors.successText} />
            </View>
            <Text style={[s.titleText, { color: colors.successText }]}>Booking Confirmed!</Text>
            <Text style={s.subText}>
              {isRecurring ? `${allBookings.length} recurring meetings scheduled.` : 'Your meeting has been scheduled.'}
            </Text>
            <View style={s.confirmDetails}>
              {isRecurring ? (
                allBookings.map((b: any, i: number) => (
                  <View key={i} style={[s.confirmRow, { backgroundColor: i % 2 === 0 ? '#1E203008' : 'transparent', borderRadius: 8, paddingHorizontal: 8 }]}>
                    <Ionicons name="calendar" size={14} color={colors.textMuted} />
                    <Text style={s.confirmText}>
                      {new Date(b.start).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })} at {fmtTime(b.start)}
                    </Text>
                    {b.status === 'confirmed' && <Ionicons name="checkmark-circle" size={14} color={colors.successText} />}
                  </View>
                ))
              ) : (
                <>
                  <View style={s.confirmRow}>
                    <Ionicons name="calendar" size={14} color={colors.textMuted} />
                    <Text style={s.confirmText}>{new Date(confirmed.start).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}</Text>
                  </View>
                  <View style={s.confirmRow}>
                    <Ionicons name="time" size={14} color={colors.textMuted} />
                    <Text style={s.confirmText}>{fmtTime(confirmed.start)} - {fmtTime(confirmed.end)}</Text>
                  </View>
                </>
              )}
              <View style={s.confirmRow}>
                <Ionicons name="person" size={14} color={colors.textMuted} />
                <Text style={s.confirmText}>with {page.owner_name}</Text>
              </View>
            </View>
            <TouchableOpacity
              style={s.icsBtn}
              onPress={() => {
                try {
                  if (Platform.OS === 'web') {
                    window.open(icsUrl, '_blank');
                  } else {
                    Linking.openURL(icsUrl);
                  }
                } catch (error) {
                  handleAppRecoverableError({
                    scope: 'book.token.download-ics',
                    error,
                    message: 'Unable to download calendar file right now.',
                    setError: setRecoverableBookingError,
                    onRetry: () => {
                      if (Platform.OS === 'web') {
                        window.open(icsUrl, '_blank');
                      } else {
                        Linking.openURL(icsUrl);
                      }
                    },
                  
        notifyMode: 'dialog',
        userInitiated: true,
      });
                }
              }}
              data-testid="booking-download-ics" testID="booking-download-ics"
            >
              <Ionicons name="cloud-download" size={16} color={colors.primaryText} />
              <Text style={s.icsBtnText}>Add to Calendar</Text>
            </TouchableOpacity>
            <View style={s.emailNotice} data-testid="booking-email-notice" testID="booking-email-notice">
              <Ionicons name="mail" size={14} color={colors.indigoText} />
              <Text style={s.emailNoticeText}>A confirmation email has been sent to your inbox</Text>
            </View>
            <Text style={{ color: colors.textMuted, fontSize: 11, textAlign: 'center', marginTop: 4, lineHeight: 16, paddingHorizontal: 16 }}>
              Don't see it? Check your spam or promotions folder.
            </Text>
            <TouchableOpacity
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, paddingVertical: 8, paddingHorizontal: 16, borderRadius: 8, backgroundColor: colors.indigoSoft, borderWidth: 1, borderColor: colors.indigoSoft }}
              onPress={async () => {
                try {
                  const res = await api.post(`/calendar/booking/${token}/resend-confirmation`, { booking_id: confirmed.booking_id });
                  if (res.data?.success) alert('Confirmation email resent!');
                } catch (error) {
                  handleAppRecoverableError({
                    scope: 'book.token.resend-confirmation',
                    error,
                    message: 'Could not resend confirmation email. Please try again.',
                    setError: setRecoverableBookingError,
                    onRetry: async () => {
                      await api.post(`/calendar/booking/${token}/resend-confirmation`, { booking_id: confirmed.booking_id });
                    },
                  
        notifyMode: 'dialog',
        userInitiated: true,
      });
                  alert('Could not resend. Please try again.');
                }
              }}
              data-testid="booking-resend-email-btn" testID="booking-resend-email-btn"
            >
              <Ionicons name="refresh" size={13} color={colors.indigoText} />
              <Text style={{ color: colors.indigoText, fontSize: 12, fontWeight: '600' }}>Resend Confirmation Email</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} data-testid="booking-page" testID="booking-page">
      <ScrollView contentContainerStyle={{ padding: 20, maxWidth: 600, alignSelf: 'center', width: '100%' }}>
        {/* Header */}
        <View style={s.header} data-testid="booking-header" testID="booking-header">
          <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: colors.indigoSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
            <Ionicons name="videocam" size={22} color={colors.indigoText} />
          </View>
          <Text style={s.titleText}>{page.title}</Text>
          <Text style={s.subText}>{page.owner_name}</Text>
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 8 }}>
            <View style={s.chip}><Ionicons name="time-outline" size={12} color={colors.textMuted} /><Text style={s.chipText}>{page.durations?.[0] || 30} min</Text></View>
            <View style={s.chip}><Ionicons name="globe-outline" size={12} color={colors.textMuted} /><Text style={s.chipText}>{page.owner_timezone}</Text></View>
          </View>
        </View>

        {/* Date Picker */}
        {recoverableBookingError ? (
          <View
            style={{ marginBottom: 14, padding: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.error + '35', backgroundColor: colors.errorSoft, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}
            data-testid="booking-recoverable-error-banner"
            testID="booking-recoverable-error-banner"
          >
            <Text style={{ color: colors.errorText, fontSize: 12, fontWeight: '700', flex: 1 }} data-testid="booking-recoverable-error-text" testID="booking-recoverable-error-text">
              {recoverableBookingError}
            </Text>
            <TouchableOpacity
              onPress={() => { if (selectedDate) { void loadSlots(selectedDate); } }}
              style={{ backgroundColor: colors.error, borderRadius: 8, paddingHorizontal: 11, paddingVertical: 8 }}
              data-testid="booking-recoverable-error-retry"
              testID="booking-recoverable-error-retry"
            >
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{t('common.retry')}</Text>
            </TouchableOpacity>
          </View>
        ) : null}
        <Text style={s.sectionLabel}>Select a Date</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 20 }}>
          <View style={{ flexDirection: 'row', gap: 8, paddingVertical: 4 }}>
            {dates.map(d => {
              const dt = new Date(d + 'T00:00:00');
              const active = selectedDate === d;
              return (
                <TouchableOpacity key={d} style={[s.dateBtn, active && { backgroundColor: colors.indigo, borderColor: colors.indigo }]}
                  onPress={() => loadSlots(d)} data-testid={`booking-date-${d}`} testID={`booking-date-${d}`}>
                  <Text style={[s.dateDow, active && { color: colors.primaryText }]}>{dt.toLocaleDateString([], { weekday: 'short' })}</Text>
                  <Text style={[s.dateDay, active && { color: colors.primaryText }]}>{dt.getDate()}</Text>
                  <Text style={[s.dateMon, active && { color: colors.primaryText }]}>{dt.toLocaleDateString([], { month: 'short' })}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </ScrollView>

        {/* Slots */}
        {selectedDate && (
          <View>
            <Text style={s.sectionLabel}>Available Times</Text>
            {slotsLoading ? (
              <ActivityIndicator size="small" color={colors.indigoText} style={{ marginVertical: 20 }} />
            ) : slots.length === 0 ? (
              <View style={s.emptySlots}>
                <Ionicons name="close-circle-outline" size={24} color={colors.textMuted} />
                <Text style={s.subText}>No available slots on this day</Text>
              </View>
            ) : (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 20 }} data-testid="booking-slots" testID="booking-slots">
                {slots.map((slot: any, i: number) => {
                  const active = selectedSlot?.start === slot.start;
                  return (
                    <TouchableOpacity key={i} style={[s.slotBtn, active && { backgroundColor: colors.indigo, borderColor: colors.indigo }]}
                      onPress={() => setSelectedSlot(slot)} data-testid={`booking-slot-${i}`} testID={`booking-slot-${i}`}>
                      <Text style={[s.slotText, active && { color: colors.primaryText }]}>{fmtTime(slot.start)}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}
          </View>
        )}

        {/* Auth Gate or Booking Form */}
        {selectedSlot && checkedUser === undefined && (
          <AgendaSkeleton />
        )}
        {selectedSlot && checkedUser === null && (
          <View style={s.formCard} data-testid="booking-auth-gate" testID="booking-auth-gate">
            <View style={{ alignItems: 'center', marginBottom: 16 }}>
              <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: colors.warningSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 10 }}>
                <Ionicons name="lock-closed" size={20} color={colors.warningText} />
              </View>
              <Text style={{ fontSize: 15, fontWeight: '800', color: colors.text, marginBottom: 4 }}>Sign in to Book</Text>
              <Text style={{ fontSize: 12, color: colors.textMuted, textAlign: 'center' }}>You need an account to book meetings. It only takes a moment.</Text>
            </View>
            <View style={s.selectedSlotBadge}>
              <Ionicons name="calendar" size={14} color={colors.indigoText} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: colors.textDim }}>
                {new Date(selectedDate + 'T00:00:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })} at {fmtTime(selectedSlot.start)}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', backgroundColor: colors.card, borderRadius: 10, padding: 3, marginBottom: 14 }}>
              <TouchableOpacity
                style={[s.authToggle, authMode === 'login' && s.authToggleActive]}
                onPress={() => { setAuthMode('login'); setAuthError(''); }}
                data-testid="auth-toggle-login" testID="auth-toggle-login"
              >
                <Text style={[s.authToggleText, authMode === 'login' && { color: colors.primaryText }]}>Log In</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.authToggle, authMode === 'register' && s.authToggleActive]}
                onPress={() => { setAuthMode('register'); setAuthError(''); }}
                data-testid="auth-toggle-register" testID="auth-toggle-register"
              >
                <Text style={[s.authToggleText, authMode === 'register' && { color: colors.primaryText }]}>Sign Up</Text>
              </TouchableOpacity>
            </View>
            {authMode === 'register' && (
              <TextInput style={s.input} placeholder="Full Name" placeholderTextColor={colors.placeholder}
                value={authName} onChangeText={setAuthName} data-testid="auth-name" testID="auth-name" />
            )}
            <TextInput style={s.input} placeholder="Email" placeholderTextColor={colors.placeholder}
              value={authEmail} onChangeText={setAuthEmail} keyboardType="email-address" autoCapitalize="none" data-testid="auth-email" testID="auth-email" />
            <TextInput style={s.input} placeholder="Password" placeholderTextColor={colors.placeholder}
              value={authPassword} onChangeText={setAuthPassword} secureTextEntry data-testid="auth-password" testID="auth-password" />
            {authError ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <Ionicons name="alert-circle" size={14} color={colors.error} />
                <Text style={{ fontSize: 12, color: colors.error }} data-testid="auth-error" testID="auth-error">{authError}</Text>
              </View>
            ) : null}
            <TouchableOpacity style={s.bookBtn} onPress={handleInlineAuth} disabled={authLoading} data-testid="auth-submit-btn" testID="auth-submit-btn">
              {authLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> :
                <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>
                  {authMode === 'login' ? 'Log In & Continue' : 'Create Account & Continue'}
                </Text>}
            </TouchableOpacity>
            <View style={{ flexDirection: 'row', alignItems: 'center', marginVertical: 14 }}>
              <View style={{ flex: 1, height: 1, backgroundColor: colors.card }} />
              <Text style={{ fontSize: 11, color: colors.textDim, paddingHorizontal: 12 }}>or</Text>
              <View style={{ flex: 1, height: 1, backgroundColor: colors.card }} />
            </View>
            <TouchableOpacity style={s.googleBtn} onPress={handleGoogleLogin} data-testid="auth-google-btn" testID="auth-google-btn">
              <Ionicons name="logo-google" size={18} color={colors.primaryText} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>Continue with Google</Text>
            </TouchableOpacity>
          </View>
        )}
        {selectedSlot && checkedUser !== undefined && checkedUser !== null && (
          <View style={s.formCard} data-testid="booking-form" testID="booking-form">
            <Text style={[s.sectionLabel, { marginBottom: 12 }]}>Your Details</Text>
            <View style={s.selectedSlotBadge}>
              <Ionicons name="calendar" size={14} color={colors.indigoText} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: colors.textDim }}>
                {new Date(selectedDate + 'T00:00:00').toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })} at {fmtTime(selectedSlot.start)}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.successSoft }} data-testid="booking-logged-in-badge" testID="booking-logged-in-badge">
              <Ionicons name="checkmark-circle" size={16} color={colors.successText} />
              <Text style={{ fontSize: 12, color: colors.successText, fontWeight: '700' }}>Logged in as {checkedUser?.name || checkedUser?.email}</Text>
            </View>
            <TextInput style={s.input} placeholder="Your Name" placeholderTextColor={colors.placeholder}
              value={guestName} onChangeText={setGuestName} data-testid="booking-name" testID="booking-name" />
            <TextInput style={s.input} placeholder="Your Email" placeholderTextColor={colors.placeholder}
              value={guestEmail} onChangeText={setGuestEmail} keyboardType="email-address" autoCapitalize="none" data-testid="booking-email" testID="booking-email" />
            <Text style={[s.sectionLabel, { marginTop: 8, marginBottom: 8 }]}>Repeat Meeting</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 }} data-testid="recurrence-selector" testID="recurrence-selector">
              {([
                { key: 'none', label: 'One-time' },
                { key: 'weekly', label: 'Weekly' },
                { key: 'biweekly', label: 'Bi-weekly' },
                { key: 'monthly', label: 'Monthly' },
              ] as const).map(opt => (
                <TouchableOpacity
                  key={opt.key}
                  style={[s.recurrenceBtn, recurrenceType === opt.key && s.recurrenceBtnActive]}
                  onPress={() => setRecurrenceType(opt.key)}
                  data-testid={`recurrence-${opt.key}`} testID={`recurrence-${opt.key}`}
                >
                  <Text style={[s.recurrenceBtnText, recurrenceType === opt.key && { color: colors.primaryText }]}>{opt.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {recurrenceType !== 'none' && (
              <View style={{ marginBottom: 14 }}>
                <Text style={{ fontSize: 12, color: colors.textMuted, marginBottom: 6 }}>How many occurrences?</Text>
                <View style={{ flexDirection: 'row', gap: 6 }} data-testid="recurrence-count-selector" testID="recurrence-count-selector">
                  {[2, 4, 6, 8, 12].map(n => (
                    <TouchableOpacity
                      key={n}
                      style={[s.countBtn, recurrenceCount === n && s.countBtnActive]}
                      onPress={() => setRecurrenceCount(n)}
                      data-testid={`recurrence-count-${n}`} testID={`recurrence-count-${n}`}
                    >
                      <Text style={[s.countBtnText, recurrenceCount === n && { color: colors.primaryText }]}>{n}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <View style={s.recurrenceSummary} data-testid="recurrence-summary" testID="recurrence-summary">
                  <Ionicons name="repeat" size={14} color={colors.indigoText} />
                  <Text style={{ fontSize: 12, color: colors.textDim, flex: 1 }}>
                    {recurrenceCount} meetings, {recurrenceType === 'weekly' ? 'every week' : recurrenceType === 'biweekly' ? 'every 2 weeks' : 'every month'}
                  </Text>
                </View>
              </View>
            )}
            <TouchableOpacity style={s.bookBtn} onPress={handleBook} disabled={booking} data-testid="booking-confirm-btn" testID="booking-confirm-btn">
              {booking ? <ActivityIndicator size="small" color={colors.primaryText} /> :
                <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>
                  {recurrenceType !== 'none' ? `Book ${recurrenceCount} Meetings` : 'Confirm Booking'}
                </Text>}
            </TouchableOpacity>
          </View>
        )}

        <View style={{ alignItems: 'center', paddingVertical: 24 }}>
          <Text style={{ fontSize: 11, color: colors.textSec }}>Powered by RealAICoach Calendar</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}