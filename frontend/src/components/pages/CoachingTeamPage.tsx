import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, TextInput, useWindowDimensions, KeyboardAvoidingView, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../AppShell';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';

type Coach = {
  coach_key: string; name: string; role: string; description: string;
  icon?: string; color?: string; tagline?: string; available: boolean; preview_available?: boolean;
};
type ChatMessage = { role: 'user' | 'assistant'; content: string; at: string };
type Status = { tier: string; daily_limit: number; used_today: number; remaining_today: number; all_coaches_unlocked: boolean };

export const CoachingTeamPage = () => {
  const { colors: C } = useTheme();
  const { t } = useTranslation();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isCompact = width < 760;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [sessions, setSessions] = useState<any[]>([]);
  const [activeSession, setActiveSession] = useState<any | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [previewGate, setPreviewGate] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  const loadAll = useCallback(async () => {
    try {
      setError(null);
      const [c, st, se] = await Promise.all([
        api.get('/ai-coaching-team/coaches'),
        api.get('/ai-coaching-team/status'),
        api.get('/ai-coaching-team/sessions'),
      ]);
      setCoaches(c.data?.coaches || []);
      setStatus(st.data);
      setSessions(se.data?.sessions || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const startSession = async (coach: Coach) => {
    if (!coach.available && !coach.preview_available) {
      router.push('/subscription/plans');
      return;
    }
    setCreating(coach.coach_key);
    try {
      const r = await api.post('/ai-coaching-team/sessions', { coach_key: coach.coach_key });
      setActiveSession(r.data);
      setMessages([]);
      setNotice(null);
      setPreviewGate(false);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setNotice(detail?.message || detail || 'Could not start session');
    } finally {
      setCreating(null);
    }
  };

  const openSession = async (sessionId: string) => {
    try {
      const r = await api.get(`/ai-coaching-team/sessions/${sessionId}`);
      setActiveSession(r.data);
      setMessages(r.data?.messages || []);
      setNotice(null);
      setPreviewGate(Boolean(r.data?.preview_gate));
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: false }), 150);
    } catch {
      setNotice('Could not open session');
    }
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || !activeSession || sending) return;
    setSending(true);
    setInput('');
    const now = new Date().toISOString();
    setMessages((prev) => [...prev, { role: 'user', content: text, at: now }]);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    try {
      const r = await api.post(`/ai-coaching-team/sessions/${activeSession.session_id}/message`, { message: text });
      setMessages((prev) => [...prev, { role: 'assistant', content: r.data?.reply || '', at: new Date().toISOString() }]);
      if (r.data?.preview_gate) setPreviewGate(true);
      if (status && status.daily_limit !== -1) {
        setStatus({ ...status, used_today: status.used_today + 1, remaining_today: r.data?.remaining_today ?? status.remaining_today });
      }
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (detail?.code === 'DAILY_LIMIT_REACHED') {
        setNotice(t('coachingTeam.quotaReached'));
      } else if (detail?.code === 'PREVIEW_USED') {
        setPreviewGate(true);
      } else {
        setNotice(detail?.message || detail || 'Message failed. Please try again.');
      }
    } finally {
      setSending(false);
    }
  };

  const coachOf = (key: string) => coaches.find((c) => c.coach_key === key);
  const s = makeStyles(C, isCompact);

  if (loading) {
    return (
      <AppShell>
        <View style={[s.center, { paddingTop: 80 }]} testID="coaching-team-loading">
          <ActivityIndicator size="large" color={C.primary} />
        </View>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
      <ScrollView ref={scrollRef} style={s.page} contentContainerStyle={s.content} testID="coaching-team-page">
        <View style={s.headerRow}>
          {activeSession ? (
            <TouchableOpacity onPress={() => { setActiveSession(null); setMessages([]); loadAll(); }} style={s.backBtn} testID="coaching-team-back-to-coaches" accessibilityLabel="arrow back button">
              <Ionicons name="arrow-back" size={20} color={C.text} />
            </TouchableOpacity>
          ) : null}
          <View style={{ flex: 1 }}>
            <Text style={s.title} testID="coaching-team-title">
              {activeSession ? activeSession.coach_name : t('coachingTeam.title')}
            </Text>
            <Text style={s.subtitle}>{t('coachingTeam.subtitle')}</Text>
          </View>
          {status ? (
            <View style={s.quotaChip} testID="coaching-team-quota">
              <Ionicons name="flash" size={13} color={C.accentText} />
              <Text style={s.quotaText}>
                {status.daily_limit === -1 ? '∞' : `${Math.max(0, status.remaining_today)}`} {t('coachingTeam.remaining')}
              </Text>
            </View>
          ) : null}
        </View>

        {error ? <View style={s.noticeBox}><Text style={{ color: C.errorText }} testID="coaching-team-error">{error}</Text></View> : null}
        {notice ? (
          <View style={s.noticeBox} testID="coaching-team-notice">
            <Text style={{ color: C.warningText, flex: 1 }}>{notice}</Text>
            <TouchableOpacity onPress={() => router.push('/subscription/plans')} style={s.upgradeBtn} testID="coaching-team-upgrade-cta" accessibilityLabel="Interactive element">
              <Text style={s.upgradeBtnText}>{t('coachingTeam.upgradeCta')}</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {!activeSession ? (
          <>
            <Text style={s.sectionLabel}>{t('coachingTeam.chooseCoach')}</Text>
            <View style={s.coachGrid}>
              {coaches.map((coach) => (
                <TouchableOpacity
                  key={coach.coach_key}
                  style={[s.coachCard, !coach.available && s.coachCardLocked]}
                  onPress={() => startSession(coach)}
                  disabled={creating !== null}
                  testID={`coach-card-${coach.coach_key}`}
                >
                  <View style={[s.coachIconWrap, { backgroundColor: (coach.color || C.primary) + '22' }]}>
                    <Ionicons name={(coach.icon || 'person') as any} size={22} color={coach.color || C.primary} />
                  </View>
                  <Text style={s.coachName}>{coach.name}</Text>
                  <Text style={s.coachTagline}>{coach.tagline || coach.role}</Text>
                  <Text style={s.coachDesc} numberOfLines={3}>{coach.description}</Text>
                  {creating === coach.coach_key ? (
                    <ActivityIndicator size="small" color={C.primary} />
                  ) : coach.available ? (
                    <View style={s.startBtn} testID={`coach-start-${coach.coach_key}`}>
                      <Ionicons name="chatbubbles" size={13} color={C.primaryText} />
                      <Text style={s.startBtnText}>{t('coachingTeam.newSession')}</Text>
                    </View>
                  ) : coach.preview_available ? (
                    <View style={s.previewBtn} testID={`coach-preview-${coach.coach_key}`}>
                      <Ionicons name="gift" size={13} color={C.accentText} />
                      <Text style={s.previewBtnText}>{t('coachingTeam.tryPreview')}</Text>
                    </View>
                  ) : (
                    <View style={s.lockedBadge} testID={`coach-locked-${coach.coach_key}`}>
                      <Ionicons name="lock-closed" size={12} color={C.warningText} />
                      <Text style={s.lockedText}>{t('coachingTeam.locked')}</Text>
                    </View>
                  )}
                </TouchableOpacity>
              ))}
            </View>

            {!status?.all_coaches_unlocked ? (
              <View style={s.upsellCard} testID="coaching-team-upsell">
                <Ionicons name="sparkles" size={18} color={C.accentText} />
                <Text style={s.upsellText}>{t('coachingTeam.upgradeBody')}</Text>
                <TouchableOpacity onPress={() => router.push('/subscription/plans')} style={s.upgradeBtn} testID="coaching-team-upsell-cta" accessibilityLabel="Interactive element">
                  <Text style={s.upgradeBtnText}>{t('coachingTeam.upgradeCta')}</Text>
                </TouchableOpacity>
              </View>
            ) : null}

            {sessions.length > 0 ? (
              <>
                <Text style={s.sectionLabel}>{t('coachingTeam.sessions')}</Text>
                {sessions.slice(0, 8).map((session) => (
                  <TouchableOpacity
                    key={session.session_id}
                    style={s.sessionRow}
                    onPress={() => openSession(session.session_id)}
                    testID={`session-row-${session.session_id}`}
                  >
                    <View style={[s.coachIconWrap, { width: 34, height: 34, backgroundColor: (coachOf(session.coach_key)?.color || C.primary) + '22' }]}>
                      <Ionicons name={(coachOf(session.coach_key)?.icon || 'person') as any} size={16} color={coachOf(session.coach_key)?.color || C.primary} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.sessionTitle}>{session.coach_name}</Text>
                      <Text style={s.sessionMeta}>{new Date(session.updated_at).toLocaleString()} · {session.message_count || 0} ✉</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={C.textDim} />
                  </TouchableOpacity>
                ))}
              </>
            ) : null}
          </>
        ) : (
          <>
            {activeSession.is_preview && !previewGate ? (
              <View style={s.previewBanner} testID="coaching-team-preview-banner">
                <Ionicons name="gift" size={14} color={C.accentText} />
                <Text style={s.previewBannerText}>{t('coachingTeam.previewBanner')}</Text>
              </View>
            ) : null}
            <View style={s.chatBox} testID="coaching-team-chat">
              {messages.length === 0 ? (
                <View style={s.center}>
                  <Ionicons name="chatbubbles-outline" size={30} color={C.textDim} />
                  <Text style={s.emptyText}>{t('coachingTeam.emptyChat')}</Text>
                </View>
              ) : messages.map((m, i) => (
                <View key={i} style={[s.bubble, m.role === 'user' ? s.bubbleUser : s.bubbleCoach]} testID={`chat-message-${i}`}>
                  <Text style={m.role === 'user' ? s.bubbleUserText : s.bubbleCoachText}>{m.content}</Text>
                </View>
              ))}
              {sending ? (
                <View style={[s.bubble, s.bubbleCoach, { flexDirection: 'row', alignItems: 'center', gap: 8 }]} testID="coach-thinking">
                  <ActivityIndicator size="small" color={C.primary} />
                  <Text style={s.bubbleCoachText}>{t('coachingTeam.thinking')}</Text>
                </View>
              ) : null}
            </View>
            {previewGate ? (
              <View style={s.previewGateCard} testID="coaching-team-preview-gate">
                <Ionicons name="sparkles" size={20} color={C.accentText} />
                <Text style={s.previewGateTitle}>{t('coachingTeam.previewGateTitle')}</Text>
                <Text style={s.previewGateBody}>{t('coachingTeam.previewGateBody')}</Text>
                <TouchableOpacity onPress={() => router.push('/subscription/plans')} style={s.upgradeBtn} testID="coaching-team-preview-gate-cta" accessibilityLabel="Interactive element">
                  <Text style={s.upgradeBtnText}>{t('coachingTeam.upgradeCta')}</Text>
                </TouchableOpacity>
              </View>
            ) : (
            <View style={s.inputRow}>
              <TextInput
                style={s.chatInput}
                value={input}
                onChangeText={setInput}
                placeholder={t('coachingTeam.inputPlaceholder')}
                placeholderTextColor={C.textDim}
                multiline
                testID="coaching-team-input"
              />
              <TouchableOpacity accessibilityLabel="send button"
                style={[s.sendBtn, { opacity: sending || !input.trim() ? 0.5 : 1 }]}
                disabled={sending || !input.trim()}
                onPress={sendMessage}
                testID="coaching-team-send"
              >
                <Ionicons name="send" size={17} color={C.primaryText} />
              </TouchableOpacity>
            </View>
            )}
          </>
        )}
      </ScrollView>
      </KeyboardAvoidingView>
    </AppShell>
  );
};

const makeStyles = (C: any, isCompact: boolean) => StyleSheet.create({
  page: { flex: 1, backgroundColor: C.bg },
  content: { padding: isCompact ? 14 : 24, paddingBottom: 60, maxWidth: 960, width: '100%', alignSelf: 'center' },
  center: { alignItems: 'center', justifyContent: 'center', gap: 10, padding: 24 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 14 },
  backBtn: { padding: 8, borderRadius: 10, backgroundColor: C.card, borderWidth: 1, borderColor: C.border },
  title: { fontSize: isCompact ? 20 : 24, fontWeight: '800', color: C.text },
  subtitle: { fontSize: 12, color: C.textSecondary, marginTop: 2 },
  quotaChip: {
    flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: C.accentSoft,
    paddingVertical: 6, paddingHorizontal: 12, borderRadius: 999,
  },
  quotaText: { fontSize: 11, fontWeight: '700', color: C.accentText },
  noticeBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.warningSoft,
    borderRadius: 12, padding: 12, marginBottom: 12, flexWrap: 'wrap',
  },
  sectionLabel: { fontSize: 12, fontWeight: '800', color: C.textDim, letterSpacing: 1, textTransform: 'uppercase', marginTop: 8, marginBottom: 10 },
  coachGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 },
  coachCard: {
    flexGrow: 1, flexBasis: isCompact ? '100%' : '46%', backgroundColor: C.card,
    borderRadius: 16, borderWidth: 1, borderColor: C.border, padding: 16, gap: 8,
  },
  coachCardLocked: { opacity: 0.75 },
  coachIconWrap: { width: 42, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  coachName: { fontSize: 15, fontWeight: '700', color: C.text },
  coachTagline: { fontSize: 12, fontWeight: '600', color: C.accentText },
  coachDesc: { fontSize: 12, color: C.textSecondary, lineHeight: 18 },
  startBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.primary,
    paddingVertical: 7, paddingHorizontal: 14, borderRadius: 999, alignSelf: 'flex-start', marginTop: 4,
  },
  startBtnText: { color: C.primaryText, fontSize: 12, fontWeight: '700' },
  lockedBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: C.warningSoft,
    paddingVertical: 6, paddingHorizontal: 12, borderRadius: 999, alignSelf: 'flex-start', marginTop: 4,
  },
  lockedText: { fontSize: 11, fontWeight: '700', color: C.warningText },
  previewBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.accentSoft,
    paddingVertical: 7, paddingHorizontal: 14, borderRadius: 999, alignSelf: 'flex-start', marginTop: 4,
  },
  previewBtnText: { color: C.accentText, fontSize: 12, fontWeight: '700' },
  previewBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.accentSoft,
    borderRadius: 12, padding: 10, marginBottom: 12,
  },
  previewBannerText: { flex: 1, fontSize: 12, fontWeight: '600', color: C.accentText },
  previewGateCard: {
    alignItems: 'center', gap: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border,
    borderRadius: 16, padding: 20,
  },
  previewGateTitle: { fontSize: 16, fontWeight: '800', color: C.text, textAlign: 'center' },
  previewGateBody: { fontSize: 13, color: C.textSecondary, textAlign: 'center', lineHeight: 19, maxWidth: 380 },
  upsellCard: {
    flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.card,
    borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14, marginBottom: 16, flexWrap: 'wrap',
  },
  upsellText: { flex: 1, fontSize: 13, color: C.textSecondary, minWidth: 180 },
  upgradeBtn: { backgroundColor: C.primary, paddingVertical: 8, paddingHorizontal: 16, borderRadius: 999 },
  upgradeBtnText: { color: C.primaryText, fontSize: 12, fontWeight: '700' },
  sessionRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.card,
    borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 8,
  },
  sessionTitle: { fontSize: 13, fontWeight: '700', color: C.text },
  sessionMeta: { fontSize: 11, color: C.textDim, marginTop: 2 },
  chatBox: { gap: 10, marginBottom: 14, minHeight: 200 },
  bubble: { borderRadius: 16, padding: 12, maxWidth: '86%' },
  bubbleUser: { alignSelf: 'flex-end', backgroundColor: C.primary },
  bubbleCoach: { alignSelf: 'flex-start', backgroundColor: C.card, borderWidth: 1, borderColor: C.border },
  bubbleUserText: { color: C.primaryText, fontSize: 13, lineHeight: 20 },
  bubbleCoachText: { color: C.text, fontSize: 13, lineHeight: 20 },
  emptyText: { fontSize: 13, color: C.textDim, textAlign: 'center' },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 10 },
  chatInput: {
    flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 12,
    minHeight: 46, maxHeight: 140, color: C.text, backgroundColor: C.card, fontSize: 13, textAlignVertical: 'top',
  },
  sendBtn: {
    width: 46, height: 46, borderRadius: 999, backgroundColor: C.primary,
    alignItems: 'center', justifyContent: 'center',
  },
});

export default CoachingTeamPage;
