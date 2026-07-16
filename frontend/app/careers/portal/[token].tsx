// Public candidate portal — magic link, no auth required.
// Route: /careers/portal/[token]
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../../src/context/ThemeContext';
import { useTranslation } from '../../../src/hooks/useTranslation';

const API = typeof window !== 'undefined' && window.location?.origin ? window.location.origin : (process.env.EXPO_PUBLIC_BACKEND_URL || '');

const STEP_ICONS: Record<number, any> = { 1: 'mail', 2: 'search', 3: 'videocam', 4: 'document-text', 5: 'trophy' };

export default function CandidatePortalPage() {
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
    success: colors.success,
    successSoft: colors.successSoft,
    warning: colors.warning,
    warningSoft: colors.warningSoft,
    error: colors.error,
    errorSoft: colors.errorSoft,
    onPrimary: colors.primaryText,
  }), [colors]);

  const params = useLocalSearchParams<{ token: string }>();
  const token = String(params?.token || '');

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const r = await fetch(`${API}/api/careers/portal/${token}`, { credentials: 'omit' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e: any) {
      setErr(e?.message || tx('candidatePortal.errors.notFound', 'Portal not found'));
    }
    setLoading(false);
  }, [token]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center' }} data-testid="portal-loading" testID="portal-loading">
        <ActivityIndicator size="large" color={C.primary} />
      </View>
    );
  }

  if (err || !data) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center', padding: 30 }} data-testid="portal-error" testID="portal-error">
        <Ionicons name="lock-closed" size={48} color={C.textMuted} />
        <Text style={{ color: C.text, fontSize: 18, fontWeight: '800', marginTop: 16, textAlign: 'center' }}>
          {tx('candidatePortal.errors.notFound', 'Portal not found')}
        </Text>
        <Text style={{ color: C.textSec, fontSize: 13, marginTop: 6, textAlign: 'center', maxWidth: 420 }}>
          {tx('candidatePortal.errors.expired', 'The link may have expired or been rotated. Please contact the recruiter who invited you.')}
        </Text>
      </View>
    );
  }

  const step = data.status_step || 1;
  const total = data.status_steps_total || 5;
  const iv = data.interview;
  const offer = data.offer_summary;

  return (
    <>
      <Stack.Screen options={{ title: tx('candidatePortal.page.titleWithPosition', 'Your application · {position}').replace('{position}', String(data.position || '')), headerShown: false }} />
      <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ padding: 24, alignItems: 'center' }}>
        <View style={{ maxWidth: 960, width: '100%' }} data-testid="candidate-portal" testID="candidate-portal">
          {/* Header */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 24 }}>
            <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: C.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="briefcase" size={22} color={C.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 1 }}>{tx('candidatePortal.labels.yourApplication', 'YOUR APPLICATION')}</Text>
              <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }} data-testid="portal-position" testID="portal-position">
                {data.position}
              </Text>
            </View>
          </View>

          {/* Greeting */}
          <Text style={{ color: C.text, fontSize: 16, marginBottom: 24 }} data-testid="portal-greeting" testID="portal-greeting">
            {tx('candidatePortal.greeting', 'Hi {name}, here\'s your live application status.')
              .replace('{name}', data.candidate_name.split(' ')[0] || data.candidate_name)}
          </Text>

          {/* Status progress */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 16 }} data-testid="portal-status-card" testID="portal-status-card">
            <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 1, marginBottom: 10 }}>{tx('candidatePortal.labels.currentStage', 'CURRENT STAGE')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <Ionicons name={STEP_ICONS[step] || 'ellipsis-horizontal'} size={22} color={C.primary} />
              <Text style={{ color: C.text, fontSize: 18, fontWeight: '800' }} data-testid="portal-status-label" testID="portal-status-label">
                {data.status_label}
              </Text>
            </View>
            {/* Progress bar */}
            <View style={{ flexDirection: 'row', gap: 4 }}>
              {Array.from({ length: total }).map((_, i) => (
                <View
                  key={i}
                  style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: i < step ? C.primary : C.border }}
                />
              ))}
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
              {[
                tx('candidatePortal.stages.received', 'Received'),
                tx('candidatePortal.stages.review', 'Review'),
                tx('candidatePortal.stages.interview', 'Interview'),
                tx('candidatePortal.stages.offer', 'Offer'),
                tx('candidatePortal.stages.decision', 'Decision'),
              ].map((l, i) => (
                <Text key={i} style={{ color: i < step ? C.primary : C.textMuted, fontSize: 9, fontWeight: '700', flex: 1, textAlign: i === 0 ? 'left' : i === total - 1 ? 'right' : 'center' }}>
                  {l}
                </Text>
              ))}
            </View>
          </View>

          {/* Interview details */}
          {iv && iv.date && (
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 16 }} data-testid="portal-interview-card" testID="portal-interview-card">
              <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 1, marginBottom: 10 }}>{tx('candidatePortal.labels.interview', 'INTERVIEW')}</Text>
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>
                {iv.date} · {iv.time || '—'}
              </Text>
              <Text style={{ color: C.textSec, fontSize: 13, marginTop: 4 }}>
                {tx('candidatePortal.labels.format', 'Format: {value}').replace('{value}', String(iv.type || 'video').replace('-', ' ').replace(/^./, (c: string) => c.toUpperCase()))}
              </Text>
              {iv.candidate_response && (
                <View style={{ marginTop: 10, flexDirection: 'row', gap: 6, alignItems: 'center' }}>
                  <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('candidatePortal.labels.yourResponse', 'Your response:')}</Text>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: iv.candidate_response === 'accepted' ? C.successSoft : iv.candidate_response === 'reschedule_requested' ? C.warningSoft : C.border }}>
                    <Text style={{ color: iv.candidate_response === 'accepted' ? C.success : iv.candidate_response === 'reschedule_requested' ? C.warning : C.textSec, fontSize: 11, fontWeight: '800' }}>
                      {String(iv.candidate_response).toUpperCase().replace('_', ' ')}
                    </Text>
                  </View>
                </View>
              )}
              {iv.candidate_response !== 'accepted' && iv.public_confirm_url ? (
                <TouchableOpacity
                  onPress={() => { if (typeof window !== 'undefined') window.location.href = iv.public_confirm_url; }}
                  style={{ marginTop: 14, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: C.primary, alignSelf: 'flex-start' }}
                  data-testid="portal-confirm-interview" testID="portal-confirm-interview"
                >
                  <Text style={{ color: C.onPrimary, fontSize: 13, fontWeight: '800' }}>{tx('candidatePortal.actions.confirmOrReschedule', 'Confirm or reschedule')}</Text>
                </TouchableOpacity>
              ) : null}
              {iv.candidate_response === 'accepted' && iv.video_url ? (
                <TouchableOpacity
                  onPress={() => { if (typeof window !== 'undefined') window.location.href = iv.video_url; }}
                  style={{ marginTop: 14, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: C.success, alignSelf: 'flex-start' }}
                  data-testid="portal-join-interview" testID="portal-join-interview"
                >
                  <Text style={{ color: C.onPrimary, fontSize: 13, fontWeight: '800' }}>{tx('candidatePortal.actions.joinInterview', 'Join interview')}</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          )}

          {/* Offer */}
          {offer && offer.status && (
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 16 }} data-testid="portal-offer-card" testID="portal-offer-card">
              <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 1, marginBottom: 8 }}>{tx('candidatePortal.labels.offer', 'OFFER')}</Text>
              <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>
                {String(offer.status).replace('_', ' ').toUpperCase()}
              </Text>
              {offer.accept_url ? (
                <TouchableOpacity
                  onPress={() => { if (typeof window !== 'undefined') window.location.href = offer.accept_url; }}
                  style={{ marginTop: 14, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: C.primary, alignSelf: 'flex-start' }}
                  data-testid="portal-review-offer" testID="portal-review-offer"
                >
                  <Text style={{ color: C.onPrimary, fontSize: 13, fontWeight: '800' }}>{tx('candidatePortal.actions.reviewOffer', 'Review offer')}</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          )}

          {/* Footer */}
          <Text style={{ color: C.textMuted, fontSize: 11, textAlign: 'center', marginTop: 24 }}>
            {tx('candidatePortal.footer.realtimeHint', 'This page updates in real time. Bookmark it to check your status anytime.')}
          </Text>
          <Text style={{ color: C.textMuted, fontSize: 10, textAlign: 'center', marginTop: 4 }}>
            {tx('candidatePortal.footer.applicationId', 'Application #{id}').replace('{id}', String(data.application_id || ''))}
          </Text>
        </View>
      </ScrollView>
    </>
  );
}
