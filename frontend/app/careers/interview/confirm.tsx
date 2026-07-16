/**
 * /careers/interview/confirm?token=<candidate_token>
 * Public two-way handshake: candidate can Accept or Request a reschedule.
 * No auth required — token in URL resolves the interview.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../../../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../../../src/utils/appRecoverableError';

const API = resolveRuntimeBaseUrl();

type InterviewData = {
  application_id: string;
  candidate_name: string;
  candidate_email: string;
  role_title: string;
  interview: {
    date: string;
    time: string;
    duration_minutes: number;
    type: 'video' | 'phone' | 'onsite';
    timezone: string;
    notes?: string;
    video_url?: string;
    candidate_response: 'pending' | 'accepted' | 'reschedule_requested';
    responded_at?: string | null;
    reschedule_reason?: string | null;
    proposed_slots?: { date: string; time: string }[];
  };
};

type ProposedSlot = { date: string; time: string };

const emptySlot = (): ProposedSlot => ({ date: '', time: '' });

export default function CareersInterviewConfirmScreen() {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  t('i18n.route.careers.interview.confirm.probe');
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isMobile = width < 768;
  const params = useLocalSearchParams<{ token?: string }>();
  const token = typeof params.token === 'string' ? params.token : '';

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<InterviewData | null>(null);
  const [err, setErr] = useState<string>('');

  // Reschedule form
  const [showReschedule, setShowReschedule] = useState(false);
  const [reason, setReason] = useState('');
  const [slots, setSlots] = useState<ProposedSlot[]>([emptySlot(), emptySlot()]);
  const [submitting, setSubmitting] = useState(false);

  const fetchData = useCallback(async () => {
    if (!token) { setErr(tx('careersInterviewConfirm.errors.missingToken', 'Missing token — please use the full link from your invitation email.')); setLoading(false); return; }
    try {
      const res = await fetch(`${API}/api/careers/interview/public/${encodeURIComponent(token)}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
      const body = await res.json();
      if (!res.ok || !body.success) {
        setErr(body.detail || tx('careersInterviewConfirm.errors.invalidOrExpired', 'This invitation link is invalid or has expired.'));
      } else {
        setData(body as InterviewData);
      }
    } catch (error) {
      const message = tx('careersInterviewConfirm.errors.loadFailed', 'Unable to load your invitation. Please try again later.');
      handleAppRecoverableError({
        scope: 'careers.interview.confirm.load',
        error,
        message,
        setError: setErr,
        onRetry: () => { void fetchData(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr(message);
    }
    setLoading(false);
  }, [token, tx]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleAccept = async () => {
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/careers/interview/public/${encodeURIComponent(token)}/accept`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
      const body = await res.json();
      if (res.ok && body.success) setData(body as InterviewData);
      else setErr(body.detail || tx('careersInterviewConfirm.errors.confirmFailed', 'Unable to confirm right now. Please try again.'));
    } catch (error) {
      const message = tx('careersInterviewConfirm.errors.network', 'Network error. Please try again.');
      handleAppRecoverableError({
        scope: 'careers.interview.confirm.accept',
        error,
        message,
        setError: setErr,
        onRetry: () => { void handleAccept(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr(message);
    }
    setSubmitting(false);
  };

  const handleReschedule = async () => {
    const cleanSlots = slots.filter(s => s.date && s.time);
    if (!reason.trim() && cleanSlots.length === 0) {
      setErr(tx('careersInterviewConfirm.errors.reasonOrSlotRequired', 'Add a short reason or at least one proposed time.'));
      return;
    }
    setSubmitting(true); setErr('');
    try {
      const res = await fetch(`${API}/api/careers/interview/public/${encodeURIComponent(token)}/reschedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
        body: JSON.stringify({ reason, proposed_slots: cleanSlots }),
      });
      const body = await res.json();
      if (res.ok && body.success) { setData(body as InterviewData); setShowReschedule(false); }
      else setErr(body.detail || tx('careersInterviewConfirm.errors.sendRequestFailed', 'Unable to send your request. Please try again.'));
    } catch (error) {
      const message = tx('careersInterviewConfirm.errors.network', 'Network error. Please try again.');
      handleAppRecoverableError({
        scope: 'careers.interview.confirm.reschedule',
        error,
        message,
        setError: setErr,
        onRetry: () => { void handleReschedule(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setErr(message);
    }
    setSubmitting(false);
  };

  const prettyWhen = useMemo(() => {
    if (!data?.interview?.date) return '';
    try {
      const d = new Date(`${data.interview.date}T${data.interview.time || '00:00'}:00Z`);
      return d.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    } catch { return data.interview.date; }
  }, [data]);

  const cardBg = colors.card;
  const border = colors.border;

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center', alignItems: 'center' }} data-testid="interview-confirm-loading" testID="interview-confirm-loading">
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }

  if (err && !data) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center', alignItems: 'center', padding: 24 }} data-testid="interview-confirm-error" testID="interview-confirm-error">
        <Ionicons name="alert-circle" size={48} color={colors.error} />
        <Text style={{ color: colors.text, fontSize: 20, fontWeight: '700', marginTop: 16, textAlign: 'center' }}>{t("autofix.batch2.invitation.unavailable")}</Text>
        <Text style={{ color: colors.textSec, fontSize: 14, marginTop: 8, textAlign: 'center', maxWidth: 440 }}>{err}</Text>
        <TouchableOpacity
          onPress={() => { void fetchData(); }}
          style={{ marginTop: 14, backgroundColor: colors.error, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 8 }}
          data-testid="interview-confirm-error-retry-button"
          testID="interview-confirm-error-retry-button"
        >
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (!data) return null;
  const response = data.interview.candidate_response;

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ padding: isMobile ? 16 : 32, alignItems: 'center' }}>
      <View style={{ width: '100%', maxWidth: 960 }} data-testid="interview-confirm-page" testID="interview-confirm-page">
        {/* Header */}
        <View style={{ alignItems: 'center', marginBottom: 24, marginTop: isMobile ? 8 : 32 }}>
          <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: colors.primarySoft, justifyContent: 'center', alignItems: 'center', marginBottom: 16 }}>
            <Ionicons name="calendar" size={28} color={colors.primary} />
          </View>
          <Text style={{ color: colors.text, fontSize: isMobile ? 24 : 30, fontWeight: '800', textAlign: 'center', letterSpacing: -0.5 }}>
            {tx('careersInterviewConfirm.hero.titleWithName', 'Hi {name}, you\'re invited to interview').replace('{name}', data.candidate_name.split(' ')[0] || '')}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 15, marginTop: 6, textAlign: 'center' }}>
            {tx('careersInterviewConfirm.hero.subtitlePrefix', 'for the')} <Text style={{ fontWeight: '700', color: colors.text }}>{data.role_title}</Text> {tx('careersInterviewConfirm.hero.subtitleSuffix', 'role at RealAICoach')}
          </Text>
        </View>

        {/* Slot Card */}
        <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: border, marginBottom: 16 }} data-testid="interview-slot-card" testID="interview-slot-card">
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 1 }}>{tx('careersInterviewConfirm.labels.proposedTime', 'PROPOSED TIME')}</Text>
          <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800', marginTop: 6 }}>{prettyWhen}</Text>
          <Text style={{ color: colors.primary, fontSize: 16, fontWeight: '700', marginTop: 4 }}>{data.interview.time} UTC · {data.interview.duration_minutes} min</Text>
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 12 }}>
            <View style={{ backgroundColor: colors.accentSoft, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Ionicons name={data.interview.type === 'video' ? 'videocam' : data.interview.type === 'phone' ? 'call' : 'business'} size={12} color={colors.accent} />
              <Text style={{ color: colors.accent, fontSize: 11, fontWeight: '700' }}>{data.interview.type.toUpperCase()}</Text>
            </View>
          </View>
          {data.interview.notes ? (
            <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 14, lineHeight: 20 }}>{data.interview.notes}</Text>
          ) : null}
        </View>

        {/* State: pending → Accept + Reschedule */}
        {response === 'pending' && !showReschedule && (
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
            <TouchableOpacity
              onPress={handleAccept} disabled={submitting}
              style={{ flex: 1, backgroundColor: colors.primary, paddingVertical: 14, borderRadius: 12, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8 }}
              data-testid="interview-accept-btn" testID="interview-accept-btn"
            >
              {submitting ? <ActivityIndicator color={colors.primaryText} /> : <Ionicons name="checkmark-circle" size={18} color={colors.primaryText} />}
              <Text style={{ color: colors.primaryText, fontSize: 15, fontWeight: '700' }}>{tx('careersInterviewConfirm.actions.acceptTime', 'Accept this time')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setShowReschedule(true)} disabled={submitting}
              style={{ flex: 1, backgroundColor: 'transparent', paddingVertical: 14, borderRadius: 12, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8 }}
              data-testid="interview-reschedule-btn" testID="interview-reschedule-btn"
            >
              <Ionicons name="refresh" size={16} color={colors.text} />
              <Text style={{ color: colors.text, fontSize: 15, fontWeight: '700' }}>{t("autofix.batch2.request.a.different.time")}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Reschedule form */}
        {response === 'pending' && showReschedule && (
          <View style={{ backgroundColor: cardBg, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: border }} data-testid="interview-reschedule-form" testID="interview-reschedule-form">
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: '700', marginBottom: 12 }}>{t("autofix.batch2.request.a.different.time")}</Text>

            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 0.6, marginBottom: 6 }}>{tx('careersInterviewConfirm.labels.reasonOptional', 'REASON (optional)')}</Text>
            <TextInput
              value={reason} onChangeText={setReason}
              placeholder={tx('careersInterviewConfirm.placeholders.reason', 'e.g. I\'m in GMT+8 — would an earlier slot work?')}
              placeholderTextColor={colors.textMuted as any}
              multiline numberOfLines={3}
              style={{ backgroundColor: colors.bgAlt, color: colors.text, borderWidth: 1, borderColor: border, borderRadius: 10, padding: 12, fontSize: 14, minHeight: 70, textAlignVertical: 'top' as any, marginBottom: 16 }}
              data-testid="reschedule-reason-input" testID="reschedule-reason-input"
            />

            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 0.6, marginBottom: 6 }}>{tx('careersInterviewConfirm.labels.proposedTimesOptional', 'PROPOSED TIMES (up to 3 — optional)')}</Text>
            {slots.slice(0, 3).map((slot, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
                <TextInput
                  value={slot.date}
                  onChangeText={(v) => setSlots(prev => prev.map((s, idx) => idx === i ? { ...s, date: v } : s))}
                  placeholder={tx('careersInterviewConfirm.placeholders.dateFormat', 'YYYY-MM-DD')} placeholderTextColor={colors.textMuted as any}
                  style={{ flex: 2, backgroundColor: colors.bgAlt, color: colors.text, borderWidth: 1, borderColor: border, borderRadius: 10, padding: 10, fontSize: 13 }}
                  data-testid={`reschedule-slot-date-${i}`} testID={`reschedule-slot-date-${i}`}
                />
                <TextInput
                  value={slot.time}
                  onChangeText={(v) => setSlots(prev => prev.map((s, idx) => idx === i ? { ...s, time: v } : s))}
                  placeholder={tx('careersInterviewConfirm.placeholders.timeFormat', 'HH:MM')} placeholderTextColor={colors.textMuted as any}
                  style={{ flex: 1, backgroundColor: colors.bgAlt, color: colors.text, borderWidth: 1, borderColor: border, borderRadius: 10, padding: 10, fontSize: 13 }}
                  data-testid={`reschedule-slot-time-${i}`} testID={`reschedule-slot-time-${i}`}
                />
              </View>
            ))}
            {slots.length < 3 && (
              <TouchableOpacity onPress={() => setSlots(prev => [...prev, emptySlot()])}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 }}
                data-testid="reschedule-add-slot-btn" testID="reschedule-add-slot-btn">
                <Ionicons name="add-circle-outline" size={16} color={colors.primary} />
                <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '600' }}>{tx('careersInterviewConfirm.actions.addAnotherOption', 'Add another option')}</Text>
              </TouchableOpacity>
            )}

            {err ? <Text style={{ color: colors.error, fontSize: 12, marginTop: 12 }} data-testid="reschedule-err" testID="reschedule-err">{err}</Text> : null}

            <View style={{ flexDirection: 'row', gap: 10, marginTop: 20 }}>
              <TouchableOpacity onPress={() => { setShowReschedule(false); setErr(''); }} disabled={submitting}
                style={{ flex: 1, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: border, alignItems: 'center' }}
                data-testid="reschedule-cancel-btn" testID="reschedule-cancel-btn">
                <Text style={{ color: colors.textSec, fontSize: 14, fontWeight: '700' }}>{tx('common.back', 'Back')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleReschedule} disabled={submitting}
                style={{ flex: 2, paddingVertical: 12, borderRadius: 10, backgroundColor: submitting ? colors.textMuted : colors.primary, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}
                data-testid="reschedule-send-btn" testID="reschedule-send-btn">
                {submitting ? <ActivityIndicator color={colors.primaryText} size="small" /> : <Ionicons name="send" size={14} color={colors.primaryText} />}
                <Text style={{ color: colors.primaryText, fontSize: 14, fontWeight: '700' }}>{submitting ? tx('careersInterviewConfirm.states.sending', 'Sending…') : tx('careersInterviewConfirm.actions.sendRequest', 'Send request')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* State: accepted */}
        {response === 'accepted' && (
          <View style={{ backgroundColor: colors.successSoft, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: colors.success, alignItems: 'center' }} data-testid="interview-accepted-state" testID="interview-accepted-state">
            <Ionicons name="checkmark-circle" size={44} color={colors.success} />
            <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '700', marginTop: 12, textAlign: 'center' }}>{tx('careersInterviewConfirm.states.confirmed', 'Confirmed — see you then!')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 6, textAlign: 'center', maxWidth: 440 }}>
              {tx('careersInterviewConfirm.states.confirmedHint', 'Your recruiter has been notified. A calendar invite is already in your inbox — add it to your calendar so you don\'t miss it.')}
            </Text>
            {data.interview.type === 'video' && data.interview.video_url ? (
              <a href={data.interview.video_url} target="_blank" rel="noopener noreferrer"
                 style={{ marginTop: 20, padding: '12px 22px', background: colors.primary, color: colors.primaryText as any, textDecoration: 'none', borderRadius: 10, fontWeight: 700, fontSize: 14 }}
                 data-testid="interview-join-btn">
                {tx('careersInterviewConfirm.actions.joinInterviewRoom', 'Join interview room')}
              </a>
            ) : null}
          </View>
        )}

        {/* State: reschedule requested */}
        {response === 'reschedule_requested' && (
          <View style={{ backgroundColor: colors.warningSoft, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: colors.warning, alignItems: 'center' }} data-testid="interview-reschedule-state" testID="interview-reschedule-state">
            <Ionicons name="time" size={44} color={colors.warning} />
            <Text style={{ color: colors.warningText, fontSize: 20, fontWeight: '700', marginTop: 12, textAlign: 'center' }}>{tx('careersInterviewConfirm.states.requestSent', 'Request sent')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 6, textAlign: 'center', maxWidth: 440 }}>
              {tx('careersInterviewConfirm.states.requestSentHint', 'Your recruiter has been notified and will reach out with an updated time. You\'ll receive a new email once a fresh slot is confirmed.')}
            </Text>
          </View>
        )}

        <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 28, textAlign: 'center' }}>
          {tx('careersInterviewConfirm.footer.replyingFrom', 'Replying from {email} · RealAICoach Talent').replace('{email}', String(data.candidate_email || ''))}
        </Text>
      </View>
    </ScrollView>
  );
}