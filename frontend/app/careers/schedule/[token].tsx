import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, TextInput, Platform } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../../../src/utils/runtimeBaseUrl';

const API = `${resolveRuntimeBaseUrl()}/api`;

// Public page — not authenticated. The backend CSRF middleware accepts
// X-Requested-With as a valid anti-CSRF header for anonymous fetches.
async function apiGet<T = any>(path: string, query?: Record<string, string>): Promise<T> {
  const qs = query ? `?${new URLSearchParams(query).toString()}` : '';
  const res = await fetch(`${API}${path}${qs}`, {
    method: 'GET',
    headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body && (body as any).detail) || `HTTP ${res.status}`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return body as T;
}

async function apiPost<T = any>(path: string, payload: any): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body && (body as any).detail) || `HTTP ${res.status}`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return body as T;
}

type Slot = {
  utc: string;
  applicant_local: string;
  applicant_label: string;
  interviewer_local: string;
  interviewer_label: string;
};

type Invite = {
  application_id: string;
  candidate_name: string;
  role_title: string;
  interviewer_name: string;
  interviewer_tz: string;
  duration_minutes: number;
  interview_type: string;
  status: string;
  booked_slot_utc: string | null;
  applicant_tz: string | null;
};

function detectApplicantTz(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; }
  catch { return 'UTC'; }
}

export default function PublicSchedulePage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const C = useMemo(() => ({
    bg: colors.bg,
    card: colors.card,
    border: colors.border,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    primary: colors.primary,
    primarySoft: colors.primarySoft,
    accent: colors.accent,
    accentSoft: colors.accentSoft,
    success: colors.success,
    error: colors.error,
    errorSoft: colors.errorSoft,
    onPrimary: colors.primaryText,
  }), [colors]);

  const params = useLocalSearchParams<{ token?: string }>();
  const token = String(params?.token || '');
  const [invite, setInvite] = useState<Invite | null>(null);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [tz, _setTz] = useState<string>(detectApplicantTz());
  const [selected, setSelected] = useState<Slot | null>(null);
  const [booking, setBooking] = useState(false);
  const [bookedSlot, setBookedSlot] = useState<{ slot_utc: string } | null>(null);
  const [err, setErr] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState('');

  const loadInvite = useCallback(async () => {
    if (!token) return;
    setLoading(true); setErr('');
    try {
      const data = await apiGet<Invite>(`/careers/schedule/${token}`);
      setInvite(data);
      if (data?.status === 'booked' && data?.booked_slot_utc) {
        setBookedSlot({ slot_utc: data.booked_slot_utc });
      }
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || tx('careersSchedule.errors.loadInterviewLink', 'Could not load interview link'));
    } finally {
      setLoading(false);
    }
  }, [token]);

  const loadSlots = useCallback(async () => {
    if (!token) return;
    try {
      const data = await apiGet<{ slots: Slot[] }>(`/careers/schedule/${token}/slots`, { tz });
      setSlots(data?.slots || []);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || tx('careersSchedule.errors.loadSlots', 'Could not load slots'));
    }
  }, [token, tz]);

  useEffect(() => { loadInvite(); }, [loadInvite]);
  useEffect(() => { if (invite && invite.status !== 'booked') loadSlots(); }, [invite, loadSlots]);

  const slotsByDay = useMemo(() => {
    const map: Record<string, Slot[]> = {};
    slots.forEach((s) => {
      const day = s.applicant_label.split(' · ')[0];
      if (!map[day]) map[day] = [];
      map[day].push(s);
    });
    return map;
  }, [slots]);

  const handleBook = async () => {
    if (!selected || !token) return;
    setBooking(true); setErr('');
    try {
      const isReschedule = invite?.status === 'booked';
      const url = isReschedule
        ? `/careers/schedule/${token}/reschedule`
        : `/careers/schedule/${token}/book`;
      const data = await apiPost<{ slot_utc: string }>(url, {
        slot_utc: selected.utc,
        applicant_tz: tz,
        applicant_notes: notes || undefined,
      });
      setBookedSlot({ slot_utc: data?.slot_utc || selected.utc });
      setInvite((v) => v ? { ...v, status: 'booked', booked_slot_utc: data?.slot_utc || selected.utc, applicant_tz: tz } : v);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || tx('careersSchedule.errors.bookingFailed', 'Booking failed'));
    } finally {
      setBooking(false);
    }
  };

  const handleStartReschedule = () => {
    setBookedSlot(null);
    setSelected(null);
    setInvite((v) => v ? { ...v, status: 'pending' } : v);
    loadSlots();
  };

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={C.primary} size="large" />
      </View>
    );
  }

  if (!invite) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center', padding: 24 }} data-testid="scheduler-error" testID="scheduler-error">
        <Text style={{ color: C.error, fontSize: 16, fontWeight: '700' }}>{tx('careersSchedule.errors.linkNotValid', 'Link not valid')}</Text>
        <Text style={{ color: C.textSec, fontSize: 13, marginTop: 8, textAlign: 'center' }}>{err || tx('careersSchedule.errors.invalidOrExpired', 'This scheduling link is invalid or has expired. Please contact the hiring team.')}</Text>
      </View>
    );
  }

  const isBooked = !!bookedSlot;

  return (
    <View style={{ flex: 1, backgroundColor: C.bg }} data-testid="scheduler-page" testID="scheduler-page">
      <Stack.Screen options={{ title: tx('careersSchedule.page.title', 'Schedule your interview'), headerShown: false }} />
      <ScrollView contentContainerStyle={{ padding: 20, maxWidth: 960, alignSelf: 'center', width: '100%' }}>
        {/* Header card */}
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
          <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' }}>{tx('careersSchedule.labels.interviewScheduling', 'Interview scheduling')}</Text>
          <Text style={{ color: C.text, fontSize: 22, fontWeight: '800', marginTop: 4 }} data-testid="scheduler-role" testID="scheduler-role">
            {invite.role_title || tx('careersSchedule.labels.interviewFallback', 'Interview')}
          </Text>
          <Text style={{ color: C.textSec, fontSize: 13, marginTop: 4 }}>
            {tx('careersSchedule.labels.withInterviewer', 'with {name} · {duration}-minute {type} interview')
              .replace('{name}', String(invite.interviewer_name || tx('careersSchedule.labels.ourTeam', 'our team')))
              .replace('{duration}', String(invite.duration_minutes || 0))
              .replace('{type}', String(invite.interview_type || 'video'))}
          </Text>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
            <View style={{ backgroundColor: C.accentSoft, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 }} data-testid="scheduler-applicant-tz" testID="scheduler-applicant-tz">
              <Text style={{ color: C.accent, fontSize: 10, fontWeight: '700' }}>{tx('careersSchedule.labels.yourTimezone', 'Your TZ: {tz}').replace('{tz}', String(tz))}</Text>
            </View>
            <View style={{ backgroundColor: C.primarySoft, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 }}>
              <Text style={{ color: C.primary, fontSize: 10, fontWeight: '700' }}>{tx('careersSchedule.labels.interviewerTimezone', 'Interviewer TZ: {tz}').replace('{tz}', String(invite.interviewer_tz || 'UTC'))}</Text>
            </View>
          </View>
        </View>

        {isBooked ? (
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.success, marginBottom: 16 }} data-testid="scheduler-booked-card" testID="scheduler-booked-card">
            <Text style={{ color: C.success, fontSize: 18, fontWeight: '800' }}>{tx('careersSchedule.states.booked', "You're booked")}</Text>
            <Text style={{ color: C.text, fontSize: 14, marginTop: 6 }}>
              {new Date(bookedSlot!.slot_utc).toLocaleString(undefined, { timeZone: tz, weekday: 'long', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} <Text style={{ color: C.textMuted }}>({tz})</Text>
            </Text>
            <Text style={{ color: C.textSec, fontSize: 12, marginTop: 10 }}>
              {tx('careersSchedule.states.bookedHint', 'A confirmation email with calendar invites was just sent. You can reschedule below if needed.')}
            </Text>
            <TouchableOpacity
              onPress={handleStartReschedule}
              style={{ alignSelf: 'flex-start', marginTop: 12, paddingHorizontal: 14, paddingVertical: 8, backgroundColor: C.bg, borderRadius: 10, borderColor: C.border, borderWidth: 1 }}
              data-testid="scheduler-reschedule-btn" testID="scheduler-reschedule-btn"
            >
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('careersSchedule.actions.reschedule', 'Reschedule')}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 8 }}>{tx('careersSchedule.labels.pickTime', 'Pick a time that works for you')}</Text>
            <Text style={{ color: C.textSec, fontSize: 12, marginBottom: 12 }}>{tx('careersSchedule.slots.timezoneNote', 'All slots shown in your local time')} ({tz}).</Text>

            {Object.keys(slotsByDay).length === 0 ? (
              <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 20, borderWidth: 1, borderColor: C.border, alignItems: 'center' }} data-testid="scheduler-no-slots" testID="scheduler-no-slots">
                <Text style={{ color: C.textSec, fontSize: 13 }}>{tx('careersSchedule.states.noSlots', 'No slots available right now. Please try again later or email the hiring team.')}</Text>
              </View>
            ) : (
              Object.entries(slotsByDay).map(([day, daySlots]) => (
                <View key={day} style={{ marginBottom: 14 }} data-testid={`scheduler-day-${day.replace(/\s+/g, '-')}`} testID={`scheduler-day-${day.replace(/\s+/g, '-')}`}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>{day}</Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {daySlots.map((s) => {
                      const isSel = selected?.utc === s.utc;
                      const timeLabel = s.applicant_label.split(' · ')[1] || s.applicant_local.split(' ')[1];
                      return (
                        <TouchableOpacity
                          key={s.utc}
                          onPress={() => setSelected(s)}
                          style={{
                            paddingVertical: 10, paddingHorizontal: 14, borderRadius: 10,
                            borderWidth: 1,
                            borderColor: isSel ? C.primary : C.border,
                            backgroundColor: isSel ? C.primary : C.card,
                          }}
                          data-testid={`scheduler-slot-${s.utc}`}
                          testID={`scheduler-slot-${s.utc}`}
                        >
                          <Text style={{ color: isSel ? C.onPrimary : C.text, fontSize: 13, fontWeight: '700' }}>{timeLabel}</Text>
                          <Text style={{ color: isSel ? C.onPrimary : C.textMuted, fontSize: 9, marginTop: 1 }}>{tx('careersSchedule.labels.interviewer', 'Interviewer: {name}').replace('{name}', String(s.interviewer_label.split(' · ')[1] || ''))}</Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              ))
            )}

            {selected ? (
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.primary, marginTop: 8 }} data-testid="scheduler-confirm-card" testID="scheduler-confirm-card">
                <Text style={{ color: C.primary, fontSize: 12, fontWeight: '800', letterSpacing: 0.4, textTransform: 'uppercase' }}>{tx('careersSchedule.actions.confirmThisTime', 'Confirm this time')}</Text>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginTop: 4 }}>{selected.applicant_label} ({tz})</Text>
                <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }}>{tx('careersSchedule.labels.interviewerWithTimezone', 'Interviewer: {name} ({tz})').replace('{name}', String(selected.interviewer_label || '')).replace('{tz}', String(invite.interviewer_tz || 'UTC'))}</Text>
                <TextInput
                  value={notes}
                  onChangeText={setNotes}
                  placeholder={tx('careersSchedule.placeholders.interviewerNotes', 'Anything the interviewer should know? (optional)')}
                  placeholderTextColor={C.textMuted}
                  multiline
                  style={{ marginTop: 10, backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 10, fontSize: 13, color: C.text, minHeight: 52 }}
                  data-testid="scheduler-notes" testID="scheduler-notes"
                />
                <TouchableOpacity
                  onPress={handleBook}
                  disabled={booking}
                  style={{ marginTop: 12, backgroundColor: C.primary, paddingVertical: 12, borderRadius: 10, alignItems: 'center', opacity: booking ? 0.6 : 1 }}
                  data-testid="scheduler-confirm-btn" testID="scheduler-confirm-btn"
                  {...(Platform.OS === 'web' ? { onClick: handleBook } : {})}
                >
                  <Text style={{ color: C.onPrimary, fontSize: 14, fontWeight: '800' }}>{booking ? tx('careersSchedule.states.booking', 'Booking…') : tx('careersSchedule.actions.confirmBooking', 'Confirm booking')}</Text>
                </TouchableOpacity>
              </View>
            ) : null}
          </>
        )}

        {err ? (
          <View style={{ backgroundColor: C.errorSoft, borderRadius: 10, padding: 10, marginTop: 12 }} data-testid="scheduler-error-msg" testID="scheduler-error-msg">
            <Text style={{ color: C.error, fontSize: 12 }}>{err}</Text>
          </View>
        ) : null}

        <Text style={{ color: C.textMuted, fontSize: 10, textAlign: 'center', marginTop: 18 }}>
          {tx('careersSchedule.footer.poweredBy', 'Scheduling powered by RealAICoach · Times auto-converted to your local zone.')}
        </Text>
      </ScrollView>
    </View>
  );
}
