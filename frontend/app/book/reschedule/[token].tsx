import React, { useCallback, useEffect, useState, useMemo } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet, Platform, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import api from '../../../src/services/api';
import { AgendaSkeleton } from '../../../src/components/SkeletonLoaders';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../../src/utils/appRecoverableError';

const API_BASE = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.EXPO_PUBLIC_BACKEND_URL || '');

const fmtTime = (s: string) => {
  try { return new Date(s).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return s; }
};
const fmtDate = (s: string) => {
  try { return new Date(s).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }); } catch { return s; }
};

export default function ReschedulePage() {
  const { token } = useLocalSearchParams<{ token: string }>();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // @autofix-moved: was module-level const makeStyles
  function makeStyles(colors: any) { return StyleSheet.create({
    container: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', padding: 20 },
    loadingText: { fontSize: 13, color: colors.textMuted, marginTop: 12 },
    errorCard: { alignItems: 'center', padding: 30, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface, maxWidth: 400 },
    titleText: { fontSize: 20, fontWeight: '800', marginTop: 12 },
    subText: { fontSize: 13, color: colors.textMuted, marginTop: 4 },
    currentCard: { backgroundColor: colors.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.errorSoft, borderLeftWidth: 3, borderLeftColor: colors.error },
    newTimeCard: { backgroundColor: colors.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.successSoft, borderLeftWidth: 3, borderLeftColor: colors.success, marginBottom: 16 },
    dateBtn: { width: 56, height: 72, borderRadius: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface, alignItems: 'center', justifyContent: 'center', gap: 2 },
    dateBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
    slotBtn: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface },
    slotBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
    confirmBtn: { backgroundColor: colors.primary, paddingVertical: 14, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
    confirmCard: { alignItems: 'center', padding: 30, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.surface, maxWidth: 400, width: '100%' },
    iconCircle: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
    confirmDetails: { marginTop: 16, gap: 8, width: '100%' },
    confirmRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
    confirmText: { fontSize: 13, color: colors.textSec },
    icsBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', backgroundColor: colors.success, paddingVertical: 12, paddingHorizontal: 20, borderRadius: 12, marginTop: 20, width: '100%' },
    icsBtnText: { fontSize: 13, fontWeight: '700', color: colors.primaryText, marginLeft: 6 },
    emailNotice: { flexDirection: 'row', alignItems: 'center', marginTop: 14, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.primarySoft },
    emailNoticeText: { fontSize: 12, color: colors.textMuted, marginLeft: 6, flex: 1 },
  }); }
  const s = useMemo(() => makeStyles(colors), [colors]);
  const [info, setInfo] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDate, setSelectedDate] = useState('');
  const [slots, setSlots] = useState<any[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState<any>(null);

  const loadRescheduleInfo = useCallback(async () => {
    if (!token) return;
    try {
      const res = await api.get(`/calendar/booking/reschedule/${token}`);
      setInfo(res.data);
      setError('');
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Failed to load booking info';
      handleAppRecoverableError({
        scope: 'book.reschedule.load-info',
        error: e,
        message,
        setError,
        onRetry: () => { void loadRescheduleInfo(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(message);
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    void loadRescheduleInfo();
  }, [loadRescheduleInfo]);

  // Generate date options (next 14 days, weekdays only)
  const dateOptions = useMemo(() => {
    const days: { date: string; label: string; dayName: string; dayNum: number }[] = [];
    const now = new Date();
    for (let i = 1; i <= 21 && days.length < 14; i++) {
      const d = new Date(now.getTime() + i * 86400000);
      const dow = d.getDay();
      if (dow === 0 || dow === 6) continue;
      days.push({
        date: d.toISOString().slice(0, 10),
        label: d.toLocaleDateString([], { month: 'short', day: 'numeric' }),
        dayName: d.toLocaleDateString([], { weekday: 'short' }),
        dayNum: d.getDate(),
      });
    }
    return days;
  }, []);

  const handleDateSelect = async (date: string) => {
    setSelectedDate(date);
    setSelectedSlot(null);
    setSlotsLoading(true);
    try {
      const res = await api.get(`/calendar/booking/reschedule/${token}?date=${date}`);
      setSlots(res.data?.slots || []);
      setError('');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'book.reschedule.load-slots',
        error,
        message: 'Unable to load available slots right now.',
        setError,
        onRetry: () => { void handleDateSelect(date); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setSlots([]);
    }
    finally { setSlotsLoading(false); }
  };

  const handleReschedule = async () => {
    if (!selectedSlot) return;
    setSubmitting(true);
    try {
      const res = await api.post(`/calendar/booking/reschedule/${token}`, {
        start: selectedSlot.start,
        end: selectedSlot.end,
      });
      setConfirmed(res.data?.booking);
      setError('');
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Failed to reschedule';
      handleAppRecoverableError({
        scope: 'book.reschedule.submit',
        error: e,
        message,
        setError,
        onRetry: () => { void handleReschedule(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(message);
    } finally { setSubmitting(false); }
  };

  // Loading state
  if (loading) {
    return (
      <SafeAreaView style={[s.container, { backgroundColor: colors.bg }]}>
        <AgendaSkeleton />
      </SafeAreaView>
    );
  }

  // Error state
  if (error && !info) {
    return (
      <SafeAreaView style={[s.container, { backgroundColor: colors.bg }]}>
        <View style={s.errorCard}>
          <Ionicons name="alert-circle" size={40} color={colors.error} />
          <Text style={[s.titleText, { color: colors.error }]}>{error}</Text>
          <TouchableOpacity
            onPress={() => { void loadRescheduleInfo(); }}
            style={{ marginTop: 14, backgroundColor: colors.error, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 8 }}
            data-testid="reschedule-error-retry-button"
            testID="reschedule-error-retry-button"
          >
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // Confirmed state
  if (confirmed) {
    const icsUrl = `${API_BASE}/api/calendar/booking/ics/${confirmed.booking_id || ''}`;
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} data-testid="reschedule-confirmed" testID="reschedule-confirmed">
        <ScrollView contentContainerStyle={{ flexGrow: 1, alignItems: 'center', justifyContent: 'center', padding: 20 }}>
          <View style={s.confirmCard}>
            <View style={s.iconCircle}>
              <Ionicons name="checkmark-circle" size={32} color={colors.successText} />
            </View>
            <Text style={[s.titleText, { color: colors.successText }]}>Rescheduled!</Text>
            <Text style={s.subText}>Your meeting has been moved to a new time.</Text>
            <View style={s.confirmDetails}>
              <View style={s.confirmRow}>
                <Ionicons name="calendar" size={14} color={colors.textMuted} />
                <Text style={s.confirmText}>{fmtDate(confirmed.start)}</Text>
              </View>
              <View style={s.confirmRow}>
                <Ionicons name="time" size={14} color={colors.textMuted} />
                <Text style={s.confirmText}>{fmtTime(confirmed.start)} - {fmtTime(confirmed.end)}</Text>
              </View>
            </View>
            <TouchableOpacity
              style={s.icsBtn}
              onPress={() => { try { if (Platform.OS === 'web') { window.open(icsUrl, '_blank'); } else { Linking.openURL(icsUrl); } } catch (error) { handleAppRecoverableError({ scope: 'book/reschedule/[token].tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }}
              data-testid="reschedule-download-ics" testID="reschedule-download-ics"
            >
              <Ionicons name="cloud-download" size={16} color={colors.primaryText} />
              <Text style={s.icsBtnText}>Add to Calendar</Text>
            </TouchableOpacity>
            <View style={s.emailNotice}>
              <Ionicons name="mail" size={14} color={colors.indigoText} />
              <Text style={s.emailNoticeText}>Updated confirmation email sent to your inbox</Text>
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  const booking = info?.booking;
  const page = info?.page;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} data-testid="reschedule-page" testID="reschedule-page">
      <ScrollView contentContainerStyle={{ padding: 20, maxWidth: 480, alignSelf: 'center', width: '100%' }}>
        {/* Header */}
        <View style={{ alignItems: 'center', marginBottom: 20 }}>
          <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: colors.indigoSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 10 }}>
            <Ionicons name="swap-horizontal" size={24} color={colors.indigoText} />
          </View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: colors.text }}>{tx('rescheduleMeeting.page.title', 'Reschedule Meeting')}</Text>
          <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 4 }}>{tx('rescheduleMeeting.withHost', 'with')} {page?.owner_name || tx('rescheduleMeeting.hostFallback', 'Host')}</Text>
        </View>

        {/* Current booking */}
        <View style={s.currentCard} data-testid="current-booking-info" testID="current-booking-info">
          <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted, textTransform: 'uppercase', marginBottom: 8 }}>Current Meeting</Text>
          <View style={{ flexDirection: 'row', gap: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Ionicons name="calendar" size={13} color={colors.error} />
              <Text style={{ fontSize: 13, color: colors.error, fontWeight: '600' }}>{fmtDate(booking?.start)}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Ionicons name="time" size={13} color={colors.error} />
              <Text style={{ fontSize: 13, color: colors.error, fontWeight: '600' }}>{fmtTime(booking?.start)} - {fmtTime(booking?.end)}</Text>
            </View>
          </View>
        </View>

        {/* New heading */}
        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginTop: 20, marginBottom: 12 }}>{tx('rescheduleMeeting.pickDate', 'Pick a new date')}</Text>

        {/* Date picker */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {dateOptions.map(d => {
              const isSelected = selectedDate === d.date;
              return (
                <TouchableOpacity key={d.date} onPress={() => handleDateSelect(d.date)}
                  style={[s.dateBtn, isSelected && s.dateBtnActive]}
                  data-testid={`reschedule-date-${d.dayNum}`} testID={`reschedule-date-${d.dayNum}`}
                >
                  <Text style={{ fontSize: 10, color: isSelected ? colors.primaryText : colors.skeleton, fontWeight: '600' }}>{d.dayName}</Text>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: isSelected ? colors.primaryText : colors.textDim }}>{d.dayNum}</Text>
                  <Text style={{ fontSize: 9, color: isSelected ? colors.primaryText : colors.skeleton }}>{d.label.split(' ')[0]}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </ScrollView>

        {/* Slots */}
        {selectedDate && (
          <View>
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('rescheduleMeeting.availableTimes', 'Available times')}</Text>
            {slotsLoading ? (
              <ActivityIndicator size="small" color={colors.indigoText} style={{ paddingVertical: 20 }} />
            ) : slots.length === 0 ? (
              <View style={{ paddingVertical: 20, alignItems: 'center' }}>
                <Ionicons name="calendar-outline" size={24} color={colors.textMuted} />
                <Text style={{ fontSize: 13, color: colors.textDim, marginTop: 6 }}>No available slots on this day</Text>
              </View>
            ) : (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="reschedule-slots" testID="reschedule-slots">
                {slots.map((slot: any, i: number) => {
                  const isSelected = selectedSlot?.start === slot.start;
                  return (
                    <TouchableOpacity key={i} onPress={() => setSelectedSlot(slot)}
                      style={[s.slotBtn, isSelected && s.slotBtnActive]}
                      data-testid={`reschedule-slot-${i}`} testID={`reschedule-slot-${i}`}
                    >
                      <Text style={{ fontSize: 13, fontWeight: '600', color: isSelected ? colors.primaryText : colors.textDim }}>
                        {fmtTime(slot.start)}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}
          </View>
        )}

        {/* Confirm button */}
        {selectedSlot && (
          <View style={{ marginTop: 20 }}>
            <View style={s.newTimeCard}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted, textTransform: 'uppercase', marginBottom: 6 }}>New Time</Text>
              <View style={{ flexDirection: 'row', gap: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <Ionicons name="calendar" size={13} color={colors.successText} />
                  <Text style={{ fontSize: 13, color: colors.successText, fontWeight: '600' }}>{fmtDate(selectedSlot.start)}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <Ionicons name="time" size={13} color={colors.successText} />
                  <Text style={{ fontSize: 13, color: colors.successText, fontWeight: '600' }}>{fmtTime(selectedSlot.start)} - {fmtTime(selectedSlot.end)}</Text>
                </View>
              </View>
            </View>

            <TouchableOpacity style={s.confirmBtn} onPress={handleReschedule} disabled={submitting} data-testid="reschedule-confirm-btn" testID="reschedule-confirm-btn">
              {submitting ? (
                <ActivityIndicator size="small" color={colors.primaryText} />
              ) : (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="swap-horizontal" size={18} color={colors.primaryText} />
                  <Text style={{ fontSize: 15, fontWeight: '800', color: colors.primaryText }}>Confirm Reschedule</Text>
                </View>
              )}
            </TouchableOpacity>
          </View>
        )}

        {error && info && (
          <View style={{ marginTop: 12, padding: 12, borderRadius: 10, backgroundColor: colors.errorSoft }}>
            <Text style={{ fontSize: 12, color: colors.error }}>{error}</Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}
