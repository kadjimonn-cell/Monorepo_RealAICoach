import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  ScrollView,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import PrayerAudioStudio from './PrayerAudioStudio';
import { ErrorBoundary } from '../ErrorBoundary';

type MeditationFeature = {
  feature_id: string;
  label: string;
  tier: 'free' | 'basic' | 'premium';
  available: boolean;
};

type NotificationItem = {
  created_at: string;
  title: string;
  message: string;
  read: boolean;
  type: string;
};

const MOODS = ['peaceful', 'hopeful', 'grateful', 'anxious', 'overwhelmed', 'tired'];

const WEB_TRANSITION = Platform.OS === 'web'
  ? ({ transitionProperty: 'transform, opacity, background-color, border-color', transitionDuration: '180ms', transitionTimingFunction: 'ease' } as any)
  : {};

function planColor(plan: string, colors: any) {
  if (plan === 'premium') return colors.primary;
  if (plan === 'basic') return colors.warning;
  return colors.textMuted;
}

function DailyMeditationExperience() {
  const { colors, darkMode } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 920;
  const scrollRef = useRef<ScrollView>(null);

  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState('');
  const [plan, setPlan] = useState<'free' | 'basic' | 'premium'>('free');

  const [features, setFeatures] = useState<MeditationFeature[]>([]);
  const [overview, setOverview] = useState<any>(null);
  const [gift, setGift] = useState<any>(null);
  const [lookback, setLookback] = useState<any>(null);
  const [progress, setProgress] = useState<any>(null);
  const [journeyPlan, setJourneyPlan] = useState<any>(null);
  const [digestPreview, setDigestPreview] = useState<any>(null);

  const [checkins, setCheckins] = useState<any[]>([]);
  const [journalEntries, setJournalEntries] = useState<any[]>([]);
  const [somaticLibrary, setSomaticLibrary] = useState<any[]>([]);
  const [communityPosts, setCommunityPosts] = useState<any[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const [prefs, setPrefs] = useState<any>({
    in_app_enabled: true,
    email_enabled: false,
    quiet_hours_start: 22,
    quiet_hours_end: 6,
    timezone: 'UTC',
    daily_gift_hour_utc: 7,
    weekly_lookback_day: 'sun',
  });

  const [checkinText, setCheckinText] = useState('');
  const [checkinMood, setCheckinMood] = useState('peaceful');
  const [checkinEnergy, setCheckinEnergy] = useState(3);
  const [checkinSupport, setCheckinSupport] = useState(false);

  const [journalTitle, setJournalTitle] = useState('Reflection');
  const [journalText, setJournalText] = useState('');
  const [journalPrayer, setJournalPrayer] = useState('');
  const [journalVisibility, setJournalVisibility] = useState<'private' | 'community'>('private');

  const [communityText, setCommunityText] = useState('');
  const [communityAnon, setCommunityAnon] = useState(true);

  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<{ role: 'user' | 'assistant'; content: string }[]>([]);

  const [safetyResult, setSafetyResult] = useState<any>(null);

  const [savingCheckin, setSavingCheckin] = useState(false);
  const [savingJournal, setSavingJournal] = useState(false);
  const [sendingChat, setSendingChat] = useState(false);
  const [sharingCommunity, setSharingCommunity] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [triggeringReminder, setTriggeringReminder] = useState(false);
  const [generatingPlan, setGeneratingPlan] = useState(false);
  const [previewingDigest, setPreviewingDigest] = useState(false);
  const [sendingDigest, setSendingDigest] = useState(false);

  const [globalSuccess, setGlobalSuccess] = useState('');
  const [globalError, setGlobalError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const isTransientHttpError = useCallback((error: any) => {
    const status = Number(error?.response?.status || 0);
    return status === 429 || status === 403;
  }, []);

  const loadCoreBundle = useCallback(async (uid: string) => {
    const [featureRes, overviewRes, giftRes, lookbackRes, progressRes] = await Promise.allSettled([
      api.get(`/travel-visa/daily-meditation/feature-map?user_id=${encodeURIComponent(uid)}`),
      api.get(`/travel-visa/daily-meditation/overview/${uid}`),
      api.get(`/travel-visa/daily-meditation/daily-gift/${uid}`),
      api.get(`/travel-visa/daily-meditation/lookback/${uid}?days=14&include_ai_summary=false`),
      api.get(`/travel-visa/daily-meditation/progress/${uid}`),
    ]);
    let successCount = 0;

    if (featureRes.status === 'fulfilled') {
      setFeatures(featureRes.value.data?.features || []);
      successCount += 1;
    }
    if (overviewRes.status === 'fulfilled') {
      setOverview(overviewRes.value.data || null);
      setPlan((overviewRes.value.data?.plan || 'free') as 'free' | 'basic' | 'premium');
      successCount += 1;
    }
    if (giftRes.status === 'fulfilled') {
      setGift(giftRes.value.data?.gift || null);
      successCount += 1;
    }
    if (lookbackRes.status === 'fulfilled') {
      setLookback(lookbackRes.value.data || null);
      successCount += 1;
    }
    if (progressRes.status === 'fulfilled') {
      setProgress(progressRes.value.data || null);
      successCount += 1;
    }

    if (successCount === 0) {
      const firstError =
        featureRes.status === 'rejected' ? featureRes.reason :
          overviewRes.status === 'rejected' ? overviewRes.reason :
            giftRes.status === 'rejected' ? giftRes.reason :
              lookbackRes.status === 'rejected' ? lookbackRes.reason :
                progressRes.status === 'rejected' ? progressRes.reason : null;
      throw firstError || new Error('core_bundle_failed');
    }
    return successCount;
  }, []);

  const loadActivityBundle = useCallback(async (uid: string) => {
    const [checkinsRes, journalRes, somaticRes, communityRes] = await Promise.allSettled([
      api.get(`/travel-visa/daily-meditation/checkins/${uid}?limit=20`),
      api.get(`/travel-visa/daily-meditation/journal/${uid}?limit=20`),
      api.get('/travel-visa/daily-meditation/somatic/library'),
      api.get(`/travel-visa/daily-meditation/community/feed/${uid}?limit=20`),
    ]);
    let successCount = 0;

    if (checkinsRes.status === 'fulfilled') {
      setCheckins(checkinsRes.value.data?.checkins || []);
      successCount += 1;
    }
    if (journalRes.status === 'fulfilled') {
      setJournalEntries(journalRes.value.data?.entries || []);
      successCount += 1;
    }
    if (somaticRes.status === 'fulfilled') {
      setSomaticLibrary(somaticRes.value.data?.invitations || []);
      successCount += 1;
    }
    if (communityRes.status === 'fulfilled') {
      setCommunityPosts(communityRes.value.data?.posts || []);
      successCount += 1;
    }

    if (successCount === 0) {
      const firstError =
        checkinsRes.status === 'rejected' ? checkinsRes.reason :
          journalRes.status === 'rejected' ? journalRes.reason :
            somaticRes.status === 'rejected' ? somaticRes.reason :
              communityRes.status === 'rejected' ? communityRes.reason : null;
      throw firstError || new Error('activity_bundle_failed');
    }
    return successCount;
  }, []);

  const loadReminderBundle = useCallback(async (uid: string) => {
    const [prefsRes, notifRes] = await Promise.allSettled([
      api.get(`/travel-visa/daily-meditation/reminders/prefs/${uid}`),
      api.get(`/travel-visa/daily-meditation/notifications/${uid}`),
    ]);
    let successCount = 0;

    if (prefsRes.status === 'fulfilled') {
      setPrefs((prev: any) => prefsRes.value.data?.preferences || prev);
      successCount += 1;
    }
    if (notifRes.status === 'fulfilled') {
      setNotifications(notifRes.value.data?.notifications || []);
      setUnreadCount(notifRes.value.data?.unread_count || 0);
      successCount += 1;
    }

    if (successCount === 0) {
      const firstError = prefsRes.status === 'rejected' ? prefsRes.reason : notifRes.status === 'rejected' ? notifRes.reason : null;
      throw firstError || new Error('reminder_bundle_failed');
    }
    return successCount;
  }, []);

  const runLoad = useCallback(async (uid: string, mode: 'full' | 'soft' = 'full') => {
    if (mode === 'full') setLoading(true);
    if (mode === 'soft') setRefreshing(true);
    setGlobalError('');
    try {
      const results = await Promise.allSettled([
        loadCoreBundle(uid),
        loadActivityBundle(uid),
        loadReminderBundle(uid),
      ]);

      const successfulBundles = results.filter((row) => row.status === 'fulfilled').length;
      if (successfulBundles > 0) {
        setGlobalError('');
      }
      if (successfulBundles === 0) {
        const firstRejected = results.find((row) => row.status === 'rejected') as PromiseRejectedResult | undefined;
        throw firstRejected?.reason || new Error('daily_meditation_load_failed');
      }
    } catch (e: any) {
      if (!isTransientHttpError(e) || mode === 'full') {
        setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.loadFailed', 'Unable to load Daily Meditation data right now.'));
      }
    } finally {
      if (mode === 'full') setLoading(false);
      if (mode === 'soft') setRefreshing(false);
    }
  }, [isTransientHttpError, loadCoreBundle, loadActivityBundle, loadReminderBundle, tx]);

  useEffect(() => {
    let mounted = true;
    const boot = async () => {
      try {
        const me = await api.get('/auth/me');
        const uid = me?.data?.user_id || me?.data?.id || '';
        if (!uid || !mounted) {
          setGlobalError(tx('dailyMeditation.errors.signInRequired', 'Please sign in to use Daily Meditation.'));
          setLoading(false);
          return;
        }
        setUserId(uid);
        await runLoad(uid, 'full');
      } catch {
        if (mounted) {
          setGlobalError(tx('dailyMeditation.errors.authRequired', 'Authentication required to open Daily Meditation.'));
          setLoading(false);
        }
      }
    };
    boot();
    return () => { mounted = false; };
  }, [runLoad]);

  const refreshAll = useCallback(async () => {
    if (!userId) return;
    await runLoad(userId, 'soft');
  }, [runLoad, userId]);

  const refreshCore = useCallback(async () => {
    if (!userId) return;
    await loadCoreBundle(userId);
  }, [userId, loadCoreBundle]);

  const refreshActivity = useCallback(async () => {
    if (!userId) return;
    await loadActivityBundle(userId);
  }, [userId, loadActivityBundle]);

  const refreshReminders = useCallback(async () => {
    if (!userId) return;
    await loadReminderBundle(userId);
  }, [userId, loadReminderBundle]);

  const submitCheckin = useCallback(async () => {
    if (!userId || !checkinText.trim() || savingCheckin) return;
    setSavingCheckin(true);
    setGlobalError('');
    setGlobalSuccess('');
    try {
      await api.post('/travel-visa/daily-meditation/checkin', {
        user_id: userId,
        heart_text: checkinText.trim(),
        mood: checkinMood,
        energy: checkinEnergy,
        request_support: checkinSupport,
      });
      setCheckinText('');
      setCheckinSupport(false);
      setGlobalSuccess(tx('dailyMeditation.success.checkInSaved', 'Check-in saved. Your progress has been updated.'));
      await Promise.all([refreshCore(), refreshActivity()]);
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.checkInSaveFailed', 'Could not save check-in.'));
    }
    setSavingCheckin(false);
  }, [userId, checkinText, checkinMood, checkinEnergy, checkinSupport, savingCheckin, refreshCore, refreshActivity]);

  const runSafetyCheck = useCallback(async () => {
    if (!userId || !checkinText.trim()) return;
    try {
      const res = await api.post('/travel-visa/daily-meditation/safety/check', { user_id: userId, text: checkinText.trim() });
      setSafetyResult(res.data || null);
    } catch {
      setSafetyResult(null);
    }
  }, [userId, checkinText]);

  const saveJournal = useCallback(async () => {
    if (!userId || !journalText.trim() || savingJournal) return;
    setSavingJournal(true);
    setGlobalError('');
    setGlobalSuccess('');
    try {
      await api.post('/travel-visa/daily-meditation/journal', {
        user_id: userId,
        title: journalTitle || 'Reflection',
        content: journalText.trim(),
        prayer_text: journalPrayer.trim(),
        visibility: journalVisibility,
      });
      setJournalText('');
      setJournalPrayer('');
      setGlobalSuccess(tx('dailyMeditation.success.journalSaved', 'Journal reflection saved successfully.'));
      await Promise.all([refreshCore(), refreshActivity()]);
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.journalSaveFailed', 'Could not save journal entry.'));
    }
    setSavingJournal(false);
  }, [userId, journalText, journalPrayer, journalTitle, journalVisibility, refreshCore, refreshActivity, savingJournal]);

  const completeSomatic = useCallback(async (invitation: any) => {
    if (!userId) return;
    setGlobalError('');
    try {
      await api.post('/travel-visa/daily-meditation/somatic/complete', {
        user_id: userId,
        invitation_id: invitation.invitation_id,
        duration_sec: invitation.duration_sec || 120,
        felt_shift: 'more grounded',
      });
      setGlobalSuccess(tx('dailyMeditation.success.somaticCompleted', 'Somatic practice completed. Great consistency.'));
      await Promise.all([refreshCore(), refreshActivity()]);
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.somaticFailed', 'Could not record somatic completion.'));
    }
  }, [userId, refreshCore, refreshActivity]);

  const sendCompanionMessage = useCallback(async () => {
    if (!userId || !chatInput.trim() || sendingChat) return;
    const text = chatInput.trim();
    setChatInput('');
    setChatMessages((prev) => [...prev, { role: 'user', content: text }]);
    setSendingChat(true);
    setGlobalError('');
    try {
      const res = await api.post('/travel-visa/daily-meditation/companion/chat', {
        user_id: userId,
        message: text,
        session_id: chatSessionId,
        language: 'en',
      });
      if (res.data?.session_id) setChatSessionId(res.data.session_id);
      setChatMessages((prev) => [...prev, { role: 'assistant', content: res.data?.response || 'No response generated.' }]);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 150);
    } catch (e: any) {
      setChatMessages((prev) => [...prev, { role: 'assistant', content: e?.response?.data?.detail || 'Companion is temporarily unavailable.' }]);
    }
    setSendingChat(false);
  }, [userId, chatInput, sendingChat, chatSessionId]);

  const shareToCommunity = useCallback(async () => {
    if (!userId || !communityText.trim() || sharingCommunity) return;
    setSharingCommunity(true);
    setGlobalError('');
    try {
      await api.post('/travel-visa/daily-meditation/community/share', {
        user_id: userId,
        text: communityText.trim(),
        anonymized: communityAnon,
        tags: ['community-care'],
      });
      setCommunityText('');
      setGlobalSuccess(tx('dailyMeditation.success.sharedToCommunity', 'Reflection shared in community care.'));
      await refreshActivity();
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.communityShareFailed', 'Unable to share to community.'));
    }
    setSharingCommunity(false);
  }, [userId, communityText, communityAnon, sharingCommunity, refreshActivity]);

  const supportPost = useCallback(async (postId: string) => {
    if (!userId || !postId) return;
    try {
      await api.post('/travel-visa/daily-meditation/community/pray', { user_id: userId, post_id: postId });
      await refreshActivity();
    } catch { /* silent */ }
  }, [userId, refreshActivity]);

  const saveReminderPrefs = useCallback(async () => {
    if (!userId || savingPrefs) return;
    setSavingPrefs(true);
    setGlobalError('');
    try {
      await api.post('/travel-visa/daily-meditation/reminders/prefs', {
        user_id: userId,
        ...prefs,
      });
      setGlobalSuccess(tx('dailyMeditation.success.remindersSaved', 'Reminder preferences saved.'));
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.remindersSaveFailed', 'Could not save reminder preferences.'));
    }
    setSavingPrefs(false);
  }, [userId, prefs, savingPrefs]);

  const triggerNow = useCallback(async () => {
    if (!userId || triggeringReminder) return;
    setTriggeringReminder(true);
    setGlobalError('');
    try {
      await api.post('/travel-visa/daily-meditation/reminders/notify-now', {
        user_id: userId,
        kind: 'daily_gift',
      });
      setGlobalSuccess(tx('dailyMeditation.success.reminderTriggered', 'In-app/email reminder dispatch triggered.'));
      await refreshReminders();
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.reminderTriggerFailed', 'Unable to trigger reminder now.'));
    }
    setTriggeringReminder(false);
  }, [userId, triggeringReminder, refreshReminders]);

  const markNotificationsRead = useCallback(async () => {
    if (!userId) return;
    try {
      await api.post('/travel-visa/daily-meditation/notifications/read', { user_id: userId, notification_timestamps: [] });
      await refreshReminders();
    } catch { /* silent */ }
  }, [userId, refreshReminders]);

  const generatePlan = useCallback(async () => {
    if (!userId || generatingPlan) return;
    setGeneratingPlan(true);
    setGlobalError('');
    try {
      const res = await api.post('/travel-visa/daily-meditation/journey-plan', {
        user_id: userId,
        focus_area: checkinMood,
        timeframe_days: 7,
      });
      setJourneyPlan(res.data?.journey_plan || null);
      setGlobalSuccess(tx('dailyMeditation.success.planGenerated', 'Personalized journey plan generated.'));
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.planGenerationFailed', 'Could not generate journey plan.'));
    }
    setGeneratingPlan(false);
  }, [userId, generatingPlan, checkinMood]);

  const exportCompliance = useCallback(async (format: 'json' | 'csv') => {
    if (!userId) return;
    const endpoint = `/travel-visa/daily-meditation/compliance/export/${userId}?format=${format}`;
    try {
      if (format === 'json') {
        const res = await api.get(endpoint);
        const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
        if (Platform.OS === 'web' && typeof document !== 'undefined') {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `daily_meditation_export_${new Date().toISOString().slice(0, 10)}.json`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }
      } else {
        const res = await api.get(endpoint, { responseType: 'blob' });
        if (Platform.OS === 'web' && typeof document !== 'undefined') {
          const blob = new Blob([res.data], { type: 'text/csv' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `daily_meditation_export_${new Date().toISOString().slice(0, 10)}.csv`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }
      }
      setGlobalSuccess(tx('dailyMeditation.success.exportGenerated', `Compliance export generated (${format.toUpperCase()}).`));
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.exportFailed', 'Unable to generate compliance export.'));
    }
  }, [userId]);

  const previewWeeklyDigest = useCallback(async () => {
    if (!userId || previewingDigest) return;
    setPreviewingDigest(true);
    setGlobalError('');
    try {
      const res = await api.post('/travel-visa/daily-meditation/digest/preview', { user_id: userId, days: 7 });
      setDigestPreview(res.data?.digest || null);
      setGlobalSuccess(tx('dailyMeditation.success.digestPreviewGenerated', '7-day digest preview generated.'));
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.digestPreviewFailed', 'Could not generate digest preview.'));
    }
    setPreviewingDigest(false);
  }, [userId, previewingDigest]);

  const sendWeeklyDigestNow = useCallback(async () => {
    if (!userId || sendingDigest) return;
    setSendingDigest(true);
    setGlobalError('');
    try {
      const res = await api.post('/travel-visa/daily-meditation/digest/send-now', { user_id: userId, days: 7 });
      setDigestPreview(res.data?.digest || null);
      setGlobalSuccess(tx('dailyMeditation.success.digestSent', 'Weekly digest generated and send action executed.'));
      await refreshReminders();
    } catch (e: any) {
      setGlobalError(e?.response?.data?.detail || tx('dailyMeditation.errors.digestSendFailed', 'Unable to send weekly digest now.'));
    }
    setSendingDigest(false);
  }, [userId, sendingDigest, refreshReminders]);

  const availableFeatures = useMemo(() => features.filter((f) => f.available).length, [features]);
  const planAccent = planColor(plan, colors);
  const momentum = useMemo(() => {
    const entries = [...checkins, ...journalEntries].filter((row: any) => !!row?.created_at);
    const daySet = new Set(entries.map((row: any) => String(row.created_at).slice(0, 10)));
    const days = Array.from(daySet).sort().reverse();
    let streak = 0;
    let cursor = new Date();
    cursor.setUTCHours(0, 0, 0, 0);
    for (let i = 0; i < 14; i += 1) {
      const key = cursor.toISOString().slice(0, 10);
      if (daySet.has(key)) streak += 1;
      else break;
      cursor.setUTCDate(cursor.getUTCDate() - 1);
    }
    return {
      active_days_14d: daySet.size,
      current_streak: streak,
      total_entries: entries.length,
      latest_day: days[0] || null,
    };
  }, [checkins, journalEntries]);

  if (loading) {
    return (
      <View data-testid="daily-meditation-loading-state" style={{ padding: 40, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ marginTop: 10, color: colors.textMuted }}>{tx('dailyMeditation.states.loading', 'Loading Daily Meditation...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView
      ref={scrollRef}
      data-testid="daily-meditation-root"
      testID="daily-meditation-root"
      showsVerticalScrollIndicator={false}
      contentContainerStyle={{ paddingBottom: 32 }}
    >
      <View style={{
        borderRadius: 18,
        padding: 20,
        marginBottom: 16,
        backgroundColor: darkMode ? colors.card : colors.infoSoft,
        borderWidth: 1,
        borderColor: colors.border,
      }}>
        <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, alignItems: isMobile ? 'flex-start' : 'center' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(colors.primary, '20') }}>
              <Ionicons name="leaf-outline" size={18} color={colors.primary} />
            </View>
            <View>
              <Text data-testid="daily-meditation-title" testID="daily-meditation-title" style={{ fontSize: 20, fontWeight: '800', color: colors.text }}>
                {tx('dailyMeditation.header.title', 'Daily Meditation')}
              </Text>
              <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>
                {tx('dailyMeditation.header.subtitle', 'Calm, faith-centered daily growth with AI companion support.')}
              </Text>
            </View>
          </View>
          <View style={{ flex: 1 }} />
          <View data-testid="daily-meditation-plan-badge" testID="daily-meditation-plan-badge" style={{
            paddingHorizontal: 12,
            paddingVertical: 6,
            borderRadius: 999,
            borderWidth: 1,
            borderColor: (globalThis as any).__alphaColor(planAccent, '66'),
            backgroundColor: (globalThis as any).__alphaColor(planAccent, '12'),
          }}>
            <Text data-testid="daily-meditation-plan-value" testID="daily-meditation-plan-value" style={{ fontSize: 11, fontWeight: '800', color: planAccent, textTransform: 'uppercase' }}>
              {`${plan} ${tx('dailyMeditation.header.planSuffix', 'plan')}`}
            </Text>
          </View>
          <TouchableOpacity
            data-testid="daily-meditation-refresh-button"
            testID="daily-meditation-refresh-button"
            onPress={refreshAll}
              disabled={refreshing}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.surfaceHover,
              borderRadius: 10,
              paddingHorizontal: 12,
              paddingVertical: 7,
              ...WEB_TRANSITION,
            }}
          >
            {refreshing ? <ActivityIndicator size="small" color={colors.textSec} /> : <Ionicons name="refresh-outline" size={14} color={colors.textSec} />}
            <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{refreshing ? tx('dailyMeditation.states.refreshing', 'Refreshing...') : tx('dailyMeditation.actions.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <View data-testid="daily-meditation-feature-availability" testID="daily-meditation-feature-availability" style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 12, color: colors.text }}>{tx('dailyMeditation.stats.featuresAvailable', 'Features available')}: <Text style={{ fontWeight: '800' }}>{availableFeatures}/{features.length || 25}</Text></Text>
          </View>
          <View data-testid="daily-meditation-progress-score" testID="daily-meditation-progress-score" style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 12, color: colors.text }}>{tx('dailyMeditation.stats.progressScore', 'Progress score')}: <Text style={{ fontWeight: '800' }}>{progress?.progress_score || 0}%</Text></Text>
          </View>
          <View data-testid="daily-meditation-unread-notifications" testID="daily-meditation-unread-notifications" style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 12, color: colors.text }}>{tx('dailyMeditation.stats.unreadReminders', 'Unread reminders')}: <Text style={{ fontWeight: '800' }}>{unreadCount}</Text></Text>
          </View>
        </View>

        <View data-testid="daily-meditation-momentum-card" testID="daily-meditation-momentum-card" style={{
          marginTop: 12,
          borderRadius: 12,
          borderWidth: 1,
          borderColor: (globalThis as any).__alphaColor(colors.primary, '44'),
          backgroundColor: colors.primarySoft,
          padding: 12,
          flexDirection: isMobile ? 'column' : 'row',
          gap: 10,
          alignItems: isMobile ? 'flex-start' : 'center',
        }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primary }}>{tx('dailyMeditation.stats.momentumTitle', 'Daily Momentum')}</Text>
            <Text style={{ fontSize: 11, color: colors.textSec, marginTop: 2 }}>
              {tx('dailyMeditation.stats.momentumSubtitle', 'Build calm consistency with one honest minute each day.')}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <View style={{ borderRadius: 999, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 6 }}>
              <Text data-testid="daily-meditation-streak-value" testID="daily-meditation-streak-value" style={{ fontSize: 11, fontWeight: '800', color: colors.text }}>{momentum.current_streak}d streak</Text>
            </View>
            <View style={{ borderRadius: 999, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 6 }}>
              <Text data-testid="daily-meditation-active-days-value" testID="daily-meditation-active-days-value" style={{ fontSize: 11, fontWeight: '800', color: colors.text }}>{momentum.active_days_14d}/14 active days</Text>
            </View>
          </View>
        </View>

        {plan === 'free' && (
          <View data-testid="daily-meditation-upgrade-value-card" testID="daily-meditation-upgrade-value-card" style={{
            marginTop: 10,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: (globalThis as any).__alphaColor(colors.warning, '55'),
            backgroundColor: colors.warningSoft,
            padding: 10,
          }}>
            <Text style={{ fontSize: 11, fontWeight: '800', color: colors.warningText }}>{tx('dailyMeditation.labels.upgradeNudgeTitle', 'Upgrade to unlock your full rhythm')}</Text>
            <Text style={{ fontSize: 11, color: colors.textSec, marginTop: 3 }}>
              {tx('dailyMeditation.labels.upgradeNudgeCopy', 'Basic unlocks private reflection vault, richer AI insight quotas, and community care sharing for deeper daily transformation.')}
            </Text>
          </View>
        )}
      </View>

      {!!globalError && (
        <View data-testid="daily-meditation-global-error" testID="daily-meditation-global-error" style={{ borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 12, marginBottom: 12 }}>
          <Text style={{ color: colors.errorText, fontSize: 12, fontWeight: '700' }}>{globalError}</Text>
        </View>
      )}
      {!!globalSuccess && (
        <View data-testid="daily-meditation-global-success" testID="daily-meditation-global-success" style={{ borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '55'), backgroundColor: colors.successSoft, padding: 12, marginBottom: 12 }}>
          <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '700' }}>{globalSuccess}</Text>
        </View>
      )}

      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, marginBottom: 14 }}>
        <View style={{ flex: 2, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('dailyMeditation.sections.dailyGift', "Today's Daily Gift")}</Text>
          <Text data-testid="daily-meditation-gift-title" testID="daily-meditation-gift-title" style={{ fontSize: 13, fontWeight: '700', color: colors.primary, marginBottom: 4 }}>{gift?.title || tx('dailyMeditation.states.dailyGiftLoading', 'Daily gift loading...')}</Text>
          <Text data-testid="daily-meditation-gift-scripture" testID="daily-meditation-gift-scripture" style={{ fontSize: 12, color: colors.text, marginBottom: 8 }}>{gift?.scripture || '-'}</Text>
          <Text style={{ fontSize: 12, color: colors.textSec, marginBottom: 6 }}>{gift?.reflection || '-'}</Text>
          <Text style={{ fontSize: 11, color: colors.textMuted }}>{gift?.practice || '-'}</Text>
        </View>

        <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('dailyMeditation.sections.compassionateProgress', 'Compassionate Progress')}</Text>
          <Text data-testid="daily-meditation-next-step" testID="daily-meditation-next-step" style={{ fontSize: 12, color: colors.textSec }}>{progress?.next_step || tx('dailyMeditation.states.nextStepFallback', 'Complete one check-in to begin.')}</Text>
          <View style={{ marginTop: 10, gap: 6 }}>
            {(progress?.milestones || []).slice(0, 4).map((m: any) => (
              <View key={m.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
                <Ionicons name={m.done ? 'checkmark-circle' : 'ellipse-outline'} size={14} color={m.done ? colors.success : colors.textMuted} />
                <Text style={{ fontSize: 11, color: colors.text }}>{m.label}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, marginBottom: 14 }}>
        <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 10 }}>{tx('dailyMeditation.sections.featureAccessMap', '25 Feature Access Map')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
          {features.map((f) => (
            <View key={f.feature_id} data-testid={`daily-meditation-feature-chip-${f.feature_id}`} testID={`daily-meditation-feature-chip-${f.feature_id}`} style={{
              paddingHorizontal: 10,
              paddingVertical: 6,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: f.available ? (globalThis as any).__alphaColor(colors.success, '44') : colors.border,
              backgroundColor: f.available ? colors.successSoft : colors.surfaceHover,
            }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: f.available ? colors.successText : colors.textMuted }}>
                {f.label}
              </Text>
            </View>
          ))}
        </View>
      </View>

      <PrayerAudioStudio
        userId={userId}
        plan={plan}
        onFeedback={(message, kind) => {
          if (kind === 'error') setGlobalError(message);
          else setGlobalSuccess(message);
        }}
      />

      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, marginBottom: 14 }}>
        <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('dailyMeditation.sections.heartCheckIn', 'Heart Check-In')}</Text>
          <TextInput accessibilityLabel="Text input"
            data-testid="daily-meditation-checkin-input"
            testID="daily-meditation-checkin-input"
            multiline
            value={checkinText}
            onChangeText={setCheckinText}
            placeholder={tx('dailyMeditation.placeholders.heartCheckIn', 'What is on your heart today?')}
            placeholderTextColor={colors.placeholder}
            style={{
              minHeight: 100,
              textAlignVertical: 'top',
              borderRadius: 10,
              borderWidth: 1,
              borderColor: colors.inputBorder,
              backgroundColor: colors.input,
              color: colors.inputText,
              fontSize: 13,
              paddingHorizontal: 12,
              paddingVertical: 10,
              ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
            }}
          />
          <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {MOODS.map((m) => (
              <TouchableOpacity
                key={m}
                data-testid={`daily-meditation-mood-${m}`}
                testID={`daily-meditation-mood-${m}`}
                onPress={() => setCheckinMood(m)}
                style={{
                  paddingHorizontal: 9,
                  paddingVertical: 6,
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: checkinMood === m ? colors.primary : colors.border,
                  backgroundColor: checkinMood === m ? colors.primarySoft : colors.surfaceHover,
                }}
              >
                <Text style={{ fontSize: 11, color: checkinMood === m ? colors.primary : colors.textSec, fontWeight: '700' }}>{m}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={{ fontSize: 11, color: colors.textSec }}>{tx('dailyMeditation.labels.energy', 'Energy')}:</Text>
            <TouchableOpacity data-testid="daily-meditation-energy-dec" testID="daily-meditation-energy-dec" onPress={() => setCheckinEnergy((v) => Math.max(1, v - 1))} style={{ width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name="remove" size={14} color={colors.textSec} />
            </TouchableOpacity>
            <Text data-testid="daily-meditation-energy-value" testID="daily-meditation-energy-value" style={{ fontSize: 12, fontWeight: '800', color: colors.text }}>{checkinEnergy}/5</Text>
            <TouchableOpacity data-testid="daily-meditation-energy-inc" testID="daily-meditation-energy-inc" onPress={() => setCheckinEnergy((v) => Math.min(5, v + 1))} style={{ width: 28, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name="add" size={14} color={colors.textSec} />
            </TouchableOpacity>
          </View>
          <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ fontSize: 11, color: colors.textSec }}>{tx('dailyMeditation.labels.requestSupportCheck', 'Request support check')}</Text>
            <Switch
              value={checkinSupport}
              onValueChange={setCheckinSupport}
              trackColor={{ false: colors.border, true: colors.primary + '66' }}
              thumbColor={checkinSupport ? colors.primary : colors.textMuted}
            />
          </View>

          <View style={{ marginTop: 10, flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              data-testid="daily-meditation-safety-check-button"
              testID="daily-meditation-safety-check-button"
              onPress={runSafetyCheck}
              style={{
                flex: 1,
                borderRadius: 10,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.surfaceHover,
                paddingVertical: 10,
                alignItems: 'center',
              }}
            >
              <Text style={{ fontSize: 12, fontWeight: '700', color: colors.textSec }}>{tx('dailyMeditation.actions.safetyCheck', 'Safety Check')}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              data-testid="daily-meditation-checkin-submit-button"
              testID="daily-meditation-checkin-submit-button"
              onPress={submitCheckin}
              disabled={savingCheckin || !checkinText.trim()}
              style={{
                flex: 1,
                borderRadius: 10,
                backgroundColor: colors.primary,
                opacity: savingCheckin || !checkinText.trim() ? 0.6 : 1,
                paddingVertical: 10,
                alignItems: 'center',
              }}
            >
              {savingCheckin ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primaryText }}>{tx('dailyMeditation.actions.saveCheckIn', 'Save Check-In')}</Text>}
            </TouchableOpacity>
          </View>

          {!!safetyResult && (
            <View data-testid="daily-meditation-safety-result" testID="daily-meditation-safety-result" style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: safetyResult.risk_level === 'high' ? (globalThis as any).__alphaColor(colors.error, '55') : colors.warning + '55', backgroundColor: safetyResult.risk_level === 'high' ? colors.errorSoft : colors.warningSoft, padding: 10 }}>
              <Text style={{ fontSize: 11, fontWeight: '800', color: safetyResult.risk_level === 'high' ? colors.errorText : colors.warningText }}>
                {tx('dailyMeditation.labels.riskLevel', 'Risk level')}: {safetyResult.risk_level}
              </Text>
              <Text style={{ fontSize: 11, color: colors.textSec, marginTop: 3 }}>{safetyResult.message}</Text>
            </View>
          )}
        </View>

        <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('dailyMeditation.sections.privatePrayerJournal', 'Private Prayer Journal')}</Text>
          <TextInput accessibilityLabel="Entry title"
            data-testid="daily-meditation-journal-title-input"
            testID="daily-meditation-journal-title-input"
            value={journalTitle}
            onChangeText={setJournalTitle}
            placeholder="Entry title"
            placeholderTextColor={colors.placeholder}
            style={{
              height: 40,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: colors.inputBorder,
              backgroundColor: colors.input,
              color: colors.inputText,
              paddingHorizontal: 12,
              fontSize: 12,
              marginBottom: 8,
              ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
            }}
          />
          <TextInput accessibilityLabel="Write your reflection..."
            data-testid="daily-meditation-journal-content-input"
            testID="daily-meditation-journal-content-input"
            multiline
            value={journalText}
            onChangeText={setJournalText}
            placeholder="Write your reflection..."
            placeholderTextColor={colors.placeholder}
            style={{
              minHeight: 80,
              textAlignVertical: 'top',
              borderRadius: 10,
              borderWidth: 1,
              borderColor: colors.inputBorder,
              backgroundColor: colors.input,
              color: colors.inputText,
              paddingHorizontal: 12,
              paddingVertical: 8,
              fontSize: 12,
              marginBottom: 8,
              ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
            }}
          />
          <TextInput accessibilityLabel="Optional prayer text"
            data-testid="daily-meditation-journal-prayer-input"
            testID="daily-meditation-journal-prayer-input"
            multiline
            value={journalPrayer}
            onChangeText={setJournalPrayer}
            placeholder="Optional prayer text"
            placeholderTextColor={colors.placeholder}
            style={{
              minHeight: 70,
              textAlignVertical: 'top',
              borderRadius: 10,
              borderWidth: 1,
              borderColor: colors.inputBorder,
              backgroundColor: colors.input,
              color: colors.inputText,
              paddingHorizontal: 12,
              paddingVertical: 8,
              fontSize: 12,
              marginBottom: 8,
              ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
            }}
          />
          <View style={{ marginBottom: 8, flexDirection: 'row', gap: 6 }}>
            {(['private', 'community'] as const).map((mode) => (
              <TouchableOpacity
                key={mode}
                data-testid={`daily-meditation-journal-visibility-${mode}`}
                testID={`daily-meditation-journal-visibility-${mode}`}
                onPress={() => setJournalVisibility(mode)}
                style={{
                  paddingHorizontal: 10,
                  paddingVertical: 7,
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: journalVisibility === mode ? colors.primary : colors.border,
                  backgroundColor: journalVisibility === mode ? colors.primarySoft : colors.surfaceHover,
                }}
              >
                <Text style={{ fontSize: 11, fontWeight: '700', color: journalVisibility === mode ? colors.primary : colors.textSec }}>{mode}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TouchableOpacity
            data-testid="daily-meditation-journal-save-button"
            testID="daily-meditation-journal-save-button"
            onPress={saveJournal}
            disabled={savingJournal || !journalText.trim()}
            style={{
              borderRadius: 10,
              backgroundColor: colors.primary,
              opacity: savingJournal || !journalText.trim() ? 0.6 : 1,
              paddingVertical: 10,
              alignItems: 'center',
            }}
          >
            {savingJournal ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primaryText }}>{tx('dailyMeditation.actions.saveJournal', 'Save Journal')}</Text>}
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, marginBottom: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Ionicons name="chatbubbles-outline" size={16} color={colors.primary} />
          <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text }}>{tx('dailyMeditation.sections.companionChat', 'Gentle Companion Chat (Session-based)')}</Text>
        </View>
        <View data-testid="daily-meditation-chat-history" testID="daily-meditation-chat-history" style={{ maxHeight: 200, gap: 7, marginBottom: 8 }}>
          {chatMessages.length === 0 && <Text style={{ fontSize: 12, color: colors.textMuted }}>{tx('dailyMeditation.states.chatEmpty', 'Start a conversation to receive reflective companion guidance.')}</Text>}
          {chatMessages.map((m, i) => (
            <View key={`${m.role}-${i}`} style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '88%',
              borderRadius: 10,
              paddingHorizontal: 10,
              paddingVertical: 8,
              backgroundColor: m.role === 'user' ? colors.primary : colors.surfaceHover,
            }}>
              <Text style={{ fontSize: 12, color: m.role === 'user' ? colors.primaryText : colors.text }}>{m.content}</Text>
            </View>
          ))}
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput accessibilityLabel="Text input"
            data-testid="daily-meditation-chat-input"
            testID="daily-meditation-chat-input"
            value={chatInput}
            onChangeText={setChatInput}
            placeholder={tx('dailyMeditation.placeholders.chatInput', "Share what you're carrying today...")}
            placeholderTextColor={colors.placeholder}
            onSubmitEditing={sendCompanionMessage}
            style={{
              flex: 1,
              height: 42,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: colors.inputBorder,
              backgroundColor: colors.input,
              color: colors.inputText,
              paddingHorizontal: 12,
              fontSize: 12,
              ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
            }}
          />
          <TouchableOpacity
            data-testid="daily-meditation-chat-send-button"
            testID="daily-meditation-chat-send-button"
            onPress={sendCompanionMessage}
            disabled={sendingChat || !chatInput.trim()}
            style={{
              width: 42,
              height: 42,
              borderRadius: 10,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: colors.primary,
              opacity: sendingChat || !chatInput.trim() ? 0.6 : 1,
            }}
          >
            {sendingChat ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="send" size={16} color={colors.primaryText} />}
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, marginBottom: 14 }}>
        <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('dailyMeditation.sections.somaticInvitations', 'Somatic Invitations')}</Text>
          <View style={{ gap: 8 }}>
            {somaticLibrary.map((item) => (
              <View key={item.invitation_id} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 10 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text }}>{item.title}</Text>
                <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>{item.goal}</Text>
                <View style={{ marginTop: 7, flexDirection: 'row', alignItems: 'center' }}>
                  <Text style={{ fontSize: 10, color: colors.textMuted, flex: 1 }}>{Math.round((item.duration_sec || 120) / 60)} min</Text>
                  <TouchableOpacity
                    data-testid={`daily-meditation-somatic-complete-${item.invitation_id}`}
                    testID={`daily-meditation-somatic-complete-${item.invitation_id}`}
                    onPress={() => completeSomatic(item)}
                    style={{ paddingHorizontal: 9, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.primary }}
                  >
                    <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primaryText }}>{tx('dailyMeditation.actions.complete', 'Complete')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
          <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('dailyMeditation.sections.communityCare', 'Community Care')}</Text>
          <TextInput accessibilityLabel="Text input"
            data-testid="daily-meditation-community-share-input"
            testID="daily-meditation-community-share-input"
            multiline
            value={communityText}
            onChangeText={setCommunityText}
            placeholder={tx('dailyMeditation.placeholders.communityShare', 'Share an encouragement request...')}
            placeholderTextColor={colors.placeholder}
            style={{
              minHeight: 78,
              textAlignVertical: 'top',
              borderRadius: 10,
              borderWidth: 1,
              borderColor: colors.inputBorder,
              backgroundColor: colors.input,
              color: colors.inputText,
              paddingHorizontal: 12,
              paddingVertical: 8,
              fontSize: 12,
              ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
            }}
          />
          <View style={{ marginTop: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ fontSize: 11, color: colors.textSec }}>{tx('dailyMeditation.labels.shareAnonymously', 'Share anonymously')}</Text>
            <Switch
              value={communityAnon}
              onValueChange={setCommunityAnon}
              trackColor={{ false: colors.border, true: colors.primary + '66' }}
              thumbColor={communityAnon ? colors.primary : colors.textMuted}
            />
          </View>
          <TouchableOpacity
            data-testid="daily-meditation-community-share-button"
            testID="daily-meditation-community-share-button"
            onPress={shareToCommunity}
            disabled={sharingCommunity || !communityText.trim()}
            style={{
              marginTop: 8,
              borderRadius: 10,
              backgroundColor: colors.primary,
              opacity: sharingCommunity || !communityText.trim() ? 0.6 : 1,
              paddingVertical: 10,
              alignItems: 'center',
            }}
          >
            {sharingCommunity ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primaryText }}>{tx('dailyMeditation.actions.shareToCommunity', 'Share to Community')}</Text>}
          </TouchableOpacity>

          <View data-testid="daily-meditation-community-feed" testID="daily-meditation-community-feed" style={{ marginTop: 10, gap: 8, maxHeight: 220 }}>
            {communityPosts.slice(0, 6).map((post) => (
              <View key={post.post_id} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 10 }}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: colors.text }}>{post.display_name || tx('dailyMeditation.labels.member', 'Member')}</Text>
                <Text style={{ fontSize: 11, color: colors.textSec, marginTop: 3 }}>{post.text}</Text>
                <View style={{ marginTop: 6, flexDirection: 'row', alignItems: 'center' }}>
                  <Text style={{ fontSize: 10, color: colors.textMuted, flex: 1 }}>{tx('dailyMeditation.labels.prayerSupport', 'Prayer support')}: {post.prayer_support_count || 0}</Text>
                  <TouchableOpacity
                    data-testid={`daily-meditation-community-pray-${post.post_id}`}
                    testID={`daily-meditation-community-pray-${post.post_id}`}
                    onPress={() => supportPost(post.post_id)}
                    style={{ paddingHorizontal: 9, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primarySoft }}
                  >
                    <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primary }}>{post.prayed_by_me ? tx('dailyMeditation.states.supported', 'Supported') : tx('dailyMeditation.actions.support', 'Support')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        </View>
      </View>

      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12, marginBottom: 14 }}>
        <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
            <Text style={{ flex: 1, fontSize: 14, fontWeight: '800', color: colors.text }}>{tx('dailyMeditation.sections.lookBack14Days', 'Look Back (14 days)')}</Text>
            <TouchableOpacity data-testid="daily-meditation-lookback-refresh-button" testID="daily-meditation-lookback-refresh-button" onPress={refreshAll} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textSec }}>{tx('dailyMeditation.actions.refresh', 'Refresh')}</Text>
            </TouchableOpacity>
          </View>
          <Text data-testid="daily-meditation-lookback-summary" testID="daily-meditation-lookback-summary" style={{ fontSize: 11, color: colors.textSec }}>{lookback?.summary || '-'}</Text>
          {!!lookback?.ai_summary && (
            <View style={{ marginTop: 8, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '44'), backgroundColor: colors.primarySoft, padding: 10 }}>
              <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primary, marginBottom: 3 }}>{tx('dailyMeditation.labels.aiInsight', 'AI Insight')}</Text>
              <Text data-testid="daily-meditation-lookback-ai-summary" testID="daily-meditation-lookback-ai-summary" style={{ fontSize: 11, color: colors.text }}>{lookback.ai_summary}</Text>
            </View>
          )}
          <View style={{ marginTop: 9, flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {(lookback?.top_tags || []).slice(0, 8).map((t: any, i: number) => (
              <View key={`${t?.[0] || 'tag'}-${i}`} style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover }}>
                <Text style={{ fontSize: 10, color: colors.textSec }}>{`${t?.[0] || ''} (${t?.[1] || 0})`}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
            <Text style={{ flex: 1, fontSize: 14, fontWeight: '800', color: colors.text }}>{tx('dailyMeditation.sections.personalizedJourneyPlan', 'Personalized Journey Plan')}</Text>
            <TouchableOpacity
              data-testid="daily-meditation-generate-journey-plan-button"
              testID="daily-meditation-generate-journey-plan-button"
              onPress={generatePlan}
              disabled={generatingPlan}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.primary, opacity: generatingPlan ? 0.6 : 1 }}
            >
              {generatingPlan ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primaryText }}>{tx('dailyMeditation.actions.generate', 'Generate')}</Text>}
            </TouchableOpacity>
          </View>
          {!journeyPlan?.plan?.days?.length ? (
            <Text style={{ fontSize: 11, color: colors.textMuted }}>{tx('dailyMeditation.states.generatePlanPrompt', 'Generate a weekly plan aligned to your current mood and reflection rhythm.')}</Text>
          ) : (
            <View data-testid="daily-meditation-journey-plan-list" testID="daily-meditation-journey-plan-list" style={{ gap: 7 }}>
              {(journeyPlan.plan.days || []).slice(0, 5).map((d: any) => (
                <View key={`day-${d.day}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 8 }}>
                  <Text style={{ fontSize: 11, fontWeight: '800', color: colors.text }}>Day {d.day}: {d.theme}</Text>
                  <Text style={{ fontSize: 10, color: colors.textSec, marginTop: 2 }}>{d.scripture}</Text>
                  <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>{d.practice}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>

      <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, marginBottom: 14 }}>
        <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('dailyMeditation.sections.smartReminders', 'Smart Reminders (In-app + Email)')}</Text>
        <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 14 }}>
          <View style={{ flex: 1, gap: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text style={{ fontSize: 11, color: colors.textSec }}>{tx('dailyMeditation.labels.inAppNotifications', 'In-app notifications')}</Text>
              <Switch value={!!prefs.in_app_enabled} onValueChange={(v) => setPrefs((p: any) => ({ ...p, in_app_enabled: v }))} trackColor={{ false: colors.border, true: colors.primary + '66' }} thumbColor={prefs.in_app_enabled ? colors.primary : colors.textMuted} />
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text style={{ fontSize: 11, color: colors.textSec }}>{tx('dailyMeditation.labels.emailReminders', 'Email reminders')}</Text>
              <Switch value={!!prefs.email_enabled} onValueChange={(v) => setPrefs((p: any) => ({ ...p, email_enabled: v }))} trackColor={{ false: colors.border, true: colors.primary + '66' }} thumbColor={prefs.email_enabled ? colors.primary : colors.textMuted} />
            </View>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 10, color: colors.textMuted, marginBottom: 4 }}>{tx('dailyMeditation.labels.quietStartUTC', 'Quiet start (UTC)')}</Text>
                <TextInput data-testid="daily-meditation-quiet-start-input" testID="daily-meditation-quiet-start-input" keyboardType="numeric" value={String(prefs.quiet_hours_start ?? 22)} onChangeText={(t) => setPrefs((p: any) => ({ ...p, quiet_hours_start: Math.max(0, Math.min(23, Number(t) || 0)) }))} style={{ height: 38, borderRadius: 9, borderWidth: 1, borderColor: colors.inputBorder, backgroundColor: colors.input, color: colors.inputText, paddingHorizontal: 10, fontSize: 12, ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}) }} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 10, color: colors.textMuted, marginBottom: 4 }}>{tx('dailyMeditation.labels.quietEndUTC', 'Quiet end (UTC)')}</Text>
                <TextInput data-testid="daily-meditation-quiet-end-input" testID="daily-meditation-quiet-end-input" keyboardType="numeric" value={String(prefs.quiet_hours_end ?? 6)} accessibilityLabel="Text input" onChangeText={(t) => setPrefs((p: any) => ({ ...p, quiet_hours_end: Math.max(0, Math.min(23, Number(t) || 0)) }))} style={{ height: 38, borderRadius: 9, borderWidth: 1, borderColor: colors.inputBorder, backgroundColor: colors.input, color: colors.inputText, paddingHorizontal: 10, fontSize: 12, ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}) }} />
              </View>
            </View>
          </View>

          <View style={{ flex: 1, gap: 8 }}>
            <TouchableOpacity data-testid="daily-meditation-save-prefs-button" testID="daily-meditation-save-prefs-button" onPress={saveReminderPrefs} disabled={savingPrefs} style={{ borderRadius: 10, backgroundColor: colors.primary, paddingVertical: 10, alignItems: 'center', opacity: savingPrefs ? 0.6 : 1 }}>
              {savingPrefs ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primaryText }}>{tx('dailyMeditation.actions.saveReminderPreferences', 'Save Reminder Preferences')}</Text>}
            </TouchableOpacity>
            <TouchableOpacity data-testid="daily-meditation-trigger-reminder-button" testID="daily-meditation-trigger-reminder-button" onPress={triggerNow} disabled={triggeringReminder} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingVertical: 10, alignItems: 'center', opacity: triggeringReminder ? 0.6 : 1 }}>
              {triggeringReminder ? <ActivityIndicator size="small" color={colors.textSec} /> : <Text style={{ fontSize: 12, fontWeight: '800', color: colors.textSec }}>{tx('dailyMeditation.actions.triggerReminderNow', 'Trigger Reminder Now')}</Text>}
            </TouchableOpacity>
            <TouchableOpacity data-testid="daily-meditation-mark-read-button" testID="daily-meditation-mark-read-button" onPress={markNotificationsRead} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingVertical: 10, alignItems: 'center' }}>
              <Text style={{ fontSize: 12, fontWeight: '800', color: colors.textSec }}>{tx('dailyMeditation.actions.markNotificationsRead', 'Mark Notifications Read')}</Text>
            </TouchableOpacity>
            <TouchableOpacity data-testid="daily-meditation-preview-digest-button" testID="daily-meditation-preview-digest-button" onPress={previewWeeklyDigest} disabled={previewingDigest} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingVertical: 10, alignItems: 'center', opacity: previewingDigest ? 0.6 : 1 }}>
              {previewingDigest ? <ActivityIndicator size="small" color={colors.textSec} /> : <Text style={{ fontSize: 12, fontWeight: '800', color: colors.textSec }}>{tx('dailyMeditation.actions.preview7DayDigest', 'Preview 7-Day Digest')}</Text>}
            </TouchableOpacity>
            <TouchableOpacity data-testid="daily-meditation-send-digest-button" testID="daily-meditation-send-digest-button" onPress={sendWeeklyDigestNow} disabled={sendingDigest} style={{ borderRadius: 10, backgroundColor: colors.primary, paddingVertical: 10, alignItems: 'center', opacity: sendingDigest ? 0.6 : 1 }}>
              {sendingDigest ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primaryText }}>{tx('dailyMeditation.actions.send7DayDigestNow', 'Send 7-Day Digest Now')}</Text>}
            </TouchableOpacity>
          </View>
        </View>

        {!!digestPreview && (
          <View data-testid="daily-meditation-digest-preview-card" testID="daily-meditation-digest-preview-card" style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 10 }}>
            <Text style={{ fontSize: 11, fontWeight: '800', color: colors.text, marginBottom: 4 }}>{tx('dailyMeditation.labels.digestPreview', '7-Day Digest Preview')}</Text>
            <Text data-testid="daily-meditation-digest-subject" testID="daily-meditation-digest-subject" style={{ fontSize: 11, color: colors.primary, fontWeight: '700', marginBottom: 4 }}>{digestPreview.subject}</Text>
            <Text style={{ fontSize: 11, color: colors.textSec, marginBottom: 4 }}>{digestPreview.headline}</Text>
            {(digestPreview.snippets || []).slice(0, 3).map((s: any, idx: number) => (
              <Text key={`digest-s-${idx}`} style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>• {s.title}: {s.scripture}</Text>
            ))}
          </View>
        )}

        <View data-testid="daily-meditation-notification-list" testID="daily-meditation-notification-list" style={{ marginTop: 10, gap: 7 }}>
          {(notifications || []).slice(0, 6).map((n, i) => (
            <View key={`${n.created_at}-${i}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(n.read ? colors.border : colors.primary, '44'), backgroundColor: n.read ? colors.surfaceHover : colors.primarySoft, padding: 10 }}>
              <Text style={{ fontSize: 11, fontWeight: '800', color: colors.text }}>{n.title}</Text>
              <Text style={{ fontSize: 11, color: colors.textSec, marginTop: 3 }}>{n.message}</Text>
              <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 3 }}>{new Date(n.created_at).toLocaleString()}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }}>
        <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text, marginBottom: 8 }}>{tx('dailyMeditation.sections.enterpriseComplianceExport', 'Enterprise Compliance Export')}</Text>
        <Text style={{ fontSize: 11, color: colors.textMuted, marginBottom: 10 }}>
          {tx('dailyMeditation.sections.enterpriseComplianceExportNote', 'Download your meditation timeline bundle (JSON/CSV) for audit-safe records.')}
        </Text>
        <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
          <TouchableOpacity data-testid="daily-meditation-export-json-button" testID="daily-meditation-export-json-button" onPress={() => exportCompliance('json')} style={{ flex: 1, borderRadius: 10, backgroundColor: colors.primary, paddingVertical: 10, alignItems: 'center' }}>
            <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primaryText }}>{tx('dailyMeditation.actions.exportJson', 'Export JSON')}</Text>
          </TouchableOpacity>
          <TouchableOpacity data-testid="daily-meditation-export-csv-button" testID="daily-meditation-export-csv-button" onPress={() => exportCompliance('csv')} style={{ flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingVertical: 10, alignItems: 'center' }}>
            <Text style={{ fontSize: 12, fontWeight: '800', color: colors.textSec }}>{tx('dailyMeditation.actions.exportCsv', 'Export CSV')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
}

export default function DailyMeditationMain() {
  return (
    <ErrorBoundary panelId="daily-meditation" panelName="Daily Meditation">
      <DailyMeditationExperience />
    </ErrorBoundary>
  );
}
