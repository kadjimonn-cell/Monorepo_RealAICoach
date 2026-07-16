import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Linking, Modal, Platform, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

type SportsItem = {
  item_id: string;
  title: string;
  category?: string;
  league?: string;
  creator?: string;
  event_stage?: string;
  stream_url?: string;
  audio_url?: string;
  official_watch_url?: string;
  thumbnail_url?: string;
  duration_seconds?: number;
  min_plan?: 'free' | 'basic' | 'premium' | string;
  is_live?: boolean;
  kickoff_at?: string;
  blackout_blocked?: boolean;
  blackout_reason?: string;
  is_embeddable_playable?: boolean;
  is_watchable_now?: boolean;
  embeddability_score?: number;
};

type SportsBootstrap = {
  feature_id?: string;
  quota?: { plan?: string; scope_label?: string };
  categories?: string[];
  catalog?: SportsItem[];
  featured_item?: SportsItem | null;
  adaptive_next_queue?: SportsItem[];
  behavioral_ai?: { reengagement_nudge?: string; best_time_to_return?: { label?: string; window?: string } };
  daily_drop_inbox?: { items?: (SportsItem & { listened?: boolean })[]; unread?: number };
  sports_playability_summary?: { playable_count?: number; watchable_count?: number; total_count?: number };
  matchday_streak?: {
    current_streak_days?: number;
    longest_streak_days?: number;
    status?: string;
    comeback_prompt?: string;
    rewards?: {
      current_badge?: string;
      badges_unlocked?: { days?: number; badge?: string; reward?: string }[];
      next_milestone?: { badge?: string; required_days?: number; remaining_days?: number; progress_pct?: number };
    };
  };
  prediction_challenge_rail?: {
    day_key?: string;
    total?: number;
    submitted?: number;
    points_claimed?: number;
    points_available?: number;
    challenges?: {
      challenge_id: string;
      title?: string;
      subtitle?: string;
      prompt?: string;
      points_reward?: number;
      option_keys?: string[];
      option_labels?: Record<string, string>;
      submitted?: boolean;
      submitted_option_key?: string;
    }[];
  };
};

const PLAN_LEVEL = { free: 0, basic: 1, premium: 2 };

const formatDuration = (seconds?: number) => {
  const mins = Math.max(1, Math.round(Number(seconds || 0) / 60));
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${m}m`;
};

const SportsFeature30 = () => {
  const { colors } = useTheme();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [bootstrap, setBootstrap] = useState<SportsBootstrap | null>(null);
  const [liveNow, setLiveNow] = useState<SportsItem[]>([]);
  const [comingUp, setComingUp] = useState<SportsItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<SportsItem | null>(null);
  const [playError, setPlayError] = useState('');
  const [syncingPlay, setSyncingPlay] = useState(false);
  const [submittingPredictionId, setSubmittingPredictionId] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [sportsPlayableOnly, setSportsPlayableOnly] = useState(false);
  const [externalConfirmVisible, setExternalConfirmVisible] = useState(false);
  const [externalTargetUrl, setExternalTargetUrl] = useState('');
  const [rememberExternalConfirmSession, setRememberExternalConfirmSession] = useState(false);

  const queueCursorRef = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const tz = (() => {
        try {
          if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
        } catch {
          return 'UTC';
        }
        return 'UTC';
      })();

      const [bootstrapRes, liveRes] = await Promise.all([
        api.get(`/sports/v2/bootstrap?tz=${encodeURIComponent(tz)}`, { silentLoading: true, skipDedupe: true }),
        api.get('/sports/v2/live-now', { silentLoading: true, skipDedupe: true }),
      ]);

      const data: SportsBootstrap = bootstrapRes?.data || {};
      setBootstrap(data);
      setSelectedItem(data?.featured_item || (data?.catalog || [])[0] || null);
      setLiveNow((liveRes?.data?.live_now || []).slice(0, 16));
      setComingUp((liveRes?.data?.coming_up || []).slice(0, 16));
      queueCursorRef.current = 0;
    } catch (e: any) {
      setError(String(e?.response?.data?.detail || e?.message || 'Unable to load Sports v2 right now'));
      setBootstrap(null);
      setSelectedItem(null);
      setLiveNow([]);
      setComingUp([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const plan = String(bootstrap?.quota?.plan || 'free').toLowerCase();
  const categories = useMemo(() => ['all', ...((bootstrap?.categories || []).filter(Boolean))], [bootstrap?.categories]);

  const isLocked = useCallback((item: SportsItem) => {
    const required = PLAN_LEVEL[String(item?.min_plan || 'free').toLowerCase() as 'free' | 'basic' | 'premium'] ?? 0;
    const current = PLAN_LEVEL[plan as 'free' | 'basic' | 'premium'] ?? 0;
    return required > current;
  }, [plan]);

  const isWatchableNow = useCallback((item: SportsItem) => {
    return Boolean(item?.is_watchable_now || item?.is_embeddable_playable || (item?.official_watch_url && String(item.official_watch_url).startsWith('https://')));
  }, []);

  const visibleItems = useMemo(() => {
    const all = (bootstrap?.catalog || []) as SportsItem[];
    const categoryFiltered = selectedCategory === 'all'
      ? all
      : all.filter((item) => String(item.category || '').toLowerCase() === String(selectedCategory).toLowerCase());

    const sorted = [...categoryFiltered].sort((a, b) => {
      const aLive = a?.is_live ? 1 : 0;
      const bLive = b?.is_live ? 1 : 0;
      if (aLive !== bLive) return bLive - aLive;
      const aWatch = isWatchableNow(a) ? 1 : 0;
      const bWatch = isWatchableNow(b) ? 1 : 0;
      if (aWatch !== bWatch) return bWatch - aWatch;
      return Number(b?.embeddability_score || 0) - Number(a?.embeddability_score || 0);
    });

    return sportsPlayableOnly ? sorted.filter((item) => isWatchableNow(item) && !item?.blackout_blocked) : sorted;
  }, [bootstrap?.catalog, isWatchableNow, selectedCategory, sportsPlayableOnly]);

  const adaptiveQueue = useMemo(() => {
    const rows = ((bootstrap?.adaptive_next_queue || []) as SportsItem[]).filter((row) => !row?.blackout_blocked);
    return rows.length ? rows : visibleItems;
  }, [bootstrap?.adaptive_next_queue, visibleItems]);

  const openUpgrade = useCallback(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.location.assign('/subscription/plans');
      return;
    }
    void Linking.openURL('/subscription/plans');
  }, []);

  const playItem = useCallback(async (item: SportsItem, source: 'manual' | 'queue' | 'inbox' | 'live' = 'manual') => {
    if (!item?.item_id) return;
    if (item?.blackout_blocked) {
      setPlayError(item?.blackout_reason || 'Regional blackout: this event is unavailable in your location.');
      return;
    }
    if (isLocked(item)) {
      setPlayError(`Locked: requires ${String(item.min_plan || 'premium').toUpperCase()} plan`);
      openUpgrade();
      return;
    }

    if (!item?.is_embeddable_playable && String(item?.official_watch_url || '').startsWith('https://')) {
      const targetUrl = String(item?.official_watch_url || '');
      const key = 'sports-v2-external-open-confirm-skip-v1';
      const skipConfirm = Platform.OS === 'web' && typeof window !== 'undefined' && window.sessionStorage.getItem(key) === '1';
      if (skipConfirm) {
        await Linking.openURL(targetUrl);
        return;
      }
      setExternalTargetUrl(targetUrl);
      setExternalConfirmVisible(true);
      return;
    }

    setSelectedItem(item);
    setSyncingPlay(true);
    setPlayError('');
    try {
      const response = await api.post(
        '/sports/v2/play',
        { item_id: item.item_id, listen_seconds: 0, completed: false, source: `feature30_v2_${source}` },
        { silentLoading: true },
      );
      const serverItem = response?.data?.item as SportsItem | undefined;
      if (serverItem?.item_id === item.item_id) {
        setSelectedItem({ ...item, ...serverItem });
      }
    } catch (e: any) {
      const msg = String(e?.response?.data?.detail || e?.message || 'Unable to start this stream');
      setPlayError(msg);
      if (source === 'queue') {
        const next = adaptiveQueue.find((row) => row?.item_id !== item.item_id && !isLocked(row) && !row?.blackout_blocked && isWatchableNow(row));
        if (next) {
          setTimeout(() => {
            void playItem(next, 'queue');
          }, 260);
        }
      }
    } finally {
      setSyncingPlay(false);
    }
  }, [adaptiveQueue, isLocked, isWatchableNow, openUpgrade]);

  const playNext = useCallback(() => {
    const queue = adaptiveQueue;
    if (!queue.length) return;
    const nextIndex = queueCursorRef.current % queue.length;
    queueCursorRef.current = queueCursorRef.current + 1;
    const next = queue[nextIndex];
    if (!next) return;
    void playItem(next, 'queue');
  }, [adaptiveQueue, playItem]);

  const markInboxListened = useCallback(async (item: SportsItem) => {
    if (!item?.item_id) return;
    await api.post('/sports/v2/daily-drop-inbox/mark-listened', { item_id: item.item_id }, { silentLoading: true });
    setBootstrap((prev: any) => {
      if (!prev?.daily_drop_inbox?.items) return prev;
      const nextItems = (prev.daily_drop_inbox.items || []).map((row: any) => (row?.item_id === item.item_id ? { ...row, listened: true } : row));
      const unread = Math.max(0, nextItems.filter((row: any) => !row?.listened).length);
      return {
        ...prev,
        daily_drop_inbox: {
          ...prev.daily_drop_inbox,
          unread,
          items: nextItems,
        },
      };
    });
  }, []);

  const submitPrediction = useCallback(async (challengeId: string, optionKey: string) => {
    if (!challengeId || !optionKey) return;
    setSubmittingPredictionId(challengeId);
    setPlayError('');
    try {
      const res = await api.post('/sports/v2/prediction-challenges/submit', {
        challenge_id: challengeId,
        option_key: optionKey,
      }, { silentLoading: true });

      const rail = res?.data?.prediction_challenge_rail;
      const streak = res?.data?.matchday_streak;
      setBootstrap((prev: any) => ({
        ...(prev || {}),
        prediction_challenge_rail: rail || prev?.prediction_challenge_rail,
        matchday_streak: streak || prev?.matchday_streak,
      }));
    } catch (e: any) {
      setPlayError(String(e?.response?.data?.detail || e?.message || 'Unable to submit prediction'));
    } finally {
      setSubmittingPredictionId('');
    }
  }, []);

  const confirmExternalOpen = useCallback(async () => {
    const key = 'sports-v2-external-open-confirm-skip-v1';
    if (!externalTargetUrl) {
      setExternalConfirmVisible(false);
      return;
    }
    if (rememberExternalConfirmSession && Platform.OS === 'web' && typeof window !== 'undefined') {
      window.sessionStorage.setItem(key, '1');
    }
    setExternalConfirmVisible(false);
    await Linking.openURL(externalTargetUrl);
  }, [externalTargetUrl, rememberExternalConfirmSession]);

  const cardWidth = '31.5%';

  if (loading) {
    return (
      <View style={{ minHeight: 380, justifyContent: 'center', alignItems: 'center' }} data-testid="sports-v2-loading-state" testID="sports-v2-loading-state">
        <ActivityIndicator size="large" color={colors.warningText} />
        <Text style={{ marginTop: 10, color: colors.textSec }}>Loading Sports v2…</Text>
      </View>
    );
  }

  if (error || !bootstrap) {
    return (
      <View style={{ minHeight: 320, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 16, justifyContent: 'center', alignItems: 'center' }} data-testid="sports-v2-error-state" testID="sports-v2-error-state">
        <Ionicons name="alert-circle-outline" size={22} color={colors.warningText} />
        <Text style={{ color: colors.text, fontWeight: '800', marginTop: 8 }}>Sports v2 temporarily unavailable</Text>
        <Text style={{ color: colors.textSec, marginTop: 4, textAlign: 'center' }}>{error || 'Please retry. This does not affect other features.'}</Text>
        <TouchableOpacity onPress={load} style={{ marginTop: 10, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: `${colors.warningText}18`, borderWidth: 1, borderColor: `${colors.warningText}66` }} data-testid="sports-v2-retry-button" testID="sports-v2-retry-button">
          <Text style={{ color: colors.warningText, fontWeight: '800' }}>Retry Sports</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: 28 }} showsVerticalScrollIndicator={false} data-testid="sports-v2-scroll" testID="sports-v2-scroll">
      <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} data-testid="sports-v2-hero" testID="sports-v2-hero">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="sports-v2-hero-title" testID="sports-v2-hero-title">Sports v2</Text>
            <Text style={{ color: colors.textSec, marginTop: 4, fontSize: 12.5 }}>Live rails, league loops, weekly drops, and autoplay continuity.</Text>
            <Text style={{ color: colors.textMuted, marginTop: 3, fontSize: 11 }}>No uploads. No setup forms. One-tap watch flow.</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}12` }} data-testid="sports-v2-plan-pill">
              <Text style={{ color: colors.warningText, fontWeight: '800', fontSize: 11.5 }}>{String(bootstrap?.quota?.plan || 'free').toUpperCase()}</Text>
            </View>
            <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft }} data-testid="sports-v2-scope-pill">
              <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 11.5 }}>{String(bootstrap?.quota?.scope_label || '').trim() || 'Limited access'}</Text>
            </View>
          </View>
        </View>

        <View style={{ marginTop: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <Text style={{ color: colors.textSec, fontSize: 11.5, fontWeight: '700' }} data-testid="sports-v2-watchable-count">
            {`Watchable now: ${Number(bootstrap?.sports_playability_summary?.watchable_count || 0)} / ${Number(bootstrap?.sports_playability_summary?.total_count || 0)}`}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={() => {
                const top = (liveNow.find((item) => !item?.blackout_blocked) || comingUp.find((item) => !item?.blackout_blocked) || visibleItems[0]);
                if (top) void playItem(top, 'live');
              }}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: `${colors.successText}16`, paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="sports-v2-watch-instantly-button"
              testID="sports-v2-watch-instantly-button"
            >
              <Text style={{ color: colors.successText, fontSize: 10.5, fontWeight: '800' }}>Watch Instantly</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => setSportsPlayableOnly((prev) => !prev)}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: sportsPlayableOnly ? `${colors.warningText}14` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="sports-v2-only-playable-toggle"
              testID="sports-v2-only-playable-toggle"
            >
              <Text style={{ color: sportsPlayableOnly ? colors.warningText : colors.textSec, fontSize: 10.5, fontWeight: '800' }}>
                {sportsPlayableOnly ? 'Only playable now: ON' : 'Only playable now'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="sports-v2-player-card" testID="sports-v2-player-card">
        <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <View style={{ width: 92, height: 92, borderRadius: 10, overflow: 'hidden', backgroundColor: colors.bgSoft }}>
            {selectedItem?.thumbnail_url ? (
              <Image source={{ uri: selectedItem.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="Decorative image" />
            ) : null}
          </View>
          <View style={{ flex: 1, minWidth: 220 }}>
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14.5 }} numberOfLines={1} data-testid="sports-v2-player-title">
              {selectedItem?.title || 'Choose a live event'}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 3 }} numberOfLines={1}>
              {(selectedItem?.league || selectedItem?.category || 'Sports')} • {selectedItem?.event_stage || 'Live Event'}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 2 }} numberOfLines={1}>
              {formatDuration(Number(selectedItem?.duration_seconds || 0))}
            </Text>
            {syncingPlay ? <ActivityIndicator size="small" color={colors.warningText} style={{ marginTop: 8 }} /> : null}
            {playError ? <Text style={{ marginTop: 6, color: colors.warningText, fontSize: 11.5, fontWeight: '700' }} data-testid="sports-v2-play-error" testID="sports-v2-play-error">{playError}</Text> : null}

            {(selectedItem?.stream_url || selectedItem?.audio_url) ? (
              Platform.OS === 'web' ? (
                <View style={{ marginTop: 8 }} data-testid="sports-v2-web-player-wrap">
                  <video
                    controls
                    src={selectedItem?.stream_url || selectedItem?.audio_url}
                    autoPlay
                    onEnded={playNext}
                    style={{ width: '100%', maxHeight: 300, borderRadius: 10 }}
                    data-testid="sports-v2-web-player"
                  />
                </View>
              ) : (
                <TouchableOpacity style={{ marginTop: 8, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: `${colors.warningText}15`, alignSelf: 'flex-start' }} onPress={() => Linking.openURL(selectedItem?.stream_url || selectedItem?.audio_url || '')} data-testid="sports-v2-open-stream-link">
                  <Text style={{ color: colors.warningText, fontWeight: '700' }}>Open stream</Text>
                </TouchableOpacity>
              )
            ) : null}
          </View>
        </View>
      </View>

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: `${colors.warningText}55`, backgroundColor: `${colors.warningText}12`, padding: 12 }} data-testid="sports-v2-ai-nudge-card" testID="sports-v2-ai-nudge-card">
        <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '800' }}>GPT-5.2 Momentum Nudge</Text>
        <Text style={{ color: colors.text, marginTop: 5, fontSize: 12.5, fontWeight: '600' }}>
          {bootstrap?.behavioral_ai?.reengagement_nudge || 'Live action is peaking now — your next best event is queued.'}
        </Text>
        <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 10.8 }} data-testid="sports-v2-best-return-time">
          {`Best time to return: ${bootstrap?.behavioral_ai?.best_time_to_return?.label || '8:00 PM'} (${bootstrap?.behavioral_ai?.best_time_to_return?.window || 'evening'})`}
        </Text>
      </View>

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: `${colors.successText}55`, backgroundColor: `${colors.successText}12`, padding: 12 }} data-testid="sports-v2-matchday-streak-card" testID="sports-v2-matchday-streak-card">
        <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800' }}>MATCHDAY STREAK REWARDS</Text>
        <View style={{ marginTop: 6, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="sports-v2-streak-days">
            {`${Number(bootstrap?.matchday_streak?.current_streak_days || 0)} day streak`}
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 11.5 }} data-testid="sports-v2-streak-badge">
            {`Badge: ${bootstrap?.matchday_streak?.rewards?.current_badge || 'Not unlocked'}`}
          </Text>
        </View>
        <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 11.5 }} data-testid="sports-v2-streak-comeback-prompt">
          {bootstrap?.matchday_streak?.comeback_prompt || 'Come back daily to unlock rewards.'}
        </Text>
        <View style={{ marginTop: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, overflow: 'hidden' }} data-testid="sports-v2-streak-progress-track">
          <View style={{ width: `${Math.max(0, Math.min(100, Number(bootstrap?.matchday_streak?.rewards?.next_milestone?.progress_pct || 0)))}%`, height: 8, backgroundColor: colors.successText }} data-testid="sports-v2-streak-progress-fill" />
        </View>
        <Text style={{ color: colors.textMuted, marginTop: 6, fontSize: 10.5 }} data-testid="sports-v2-streak-next-milestone">
          {`Next: ${bootstrap?.matchday_streak?.rewards?.next_milestone?.badge || 'Kickoff'} in ${Number(bootstrap?.matchday_streak?.rewards?.next_milestone?.remaining_days || 0)} day(s)`}
        </Text>
      </View>

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: `${colors.warningText}55`, backgroundColor: colors.card, padding: 12 }} data-testid="sports-v2-prediction-challenges-card" testID="sports-v2-prediction-challenges-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14.5 }}>Prediction Challenge Rail</Text>
          <Text style={{ color: colors.warningText, fontWeight: '800', fontSize: 11.5 }} data-testid="sports-v2-prediction-points-pill">
            {`${Number(bootstrap?.prediction_challenge_rail?.points_claimed || 0)} / ${Number(bootstrap?.prediction_challenge_rail?.points_available || 0)} pts`}
          </Text>
        </View>
        <Text style={{ color: colors.textSec, marginTop: 5, fontSize: 11.5 }} data-testid="sports-v2-prediction-progress-label">
          {`Submitted ${Number(bootstrap?.prediction_challenge_rail?.submitted || 0)} of ${Number(bootstrap?.prediction_challenge_rail?.total || 0)} challenges today`}
        </Text>

        <View style={{ marginTop: 9, gap: 8 }}>
          {(bootstrap?.prediction_challenge_rail?.challenges || []).slice(0, 3).map((challenge) => (
            <View key={challenge.challenge_id} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9 }} data-testid={`sports-v2-prediction-challenge-${challenge.challenge_id}`}>
              <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800' }}>{challenge.title || 'Challenge'}</Text>
              <Text style={{ color: colors.textSec, marginTop: 3, fontSize: 11 }}>{challenge.prompt || challenge.subtitle || 'Make your call for today.'}</Text>
              <View style={{ marginTop: 8, flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                {(challenge.option_keys || []).map((optionKey) => {
                  const selected = String(challenge.submitted_option_key || '').toLowerCase() === String(optionKey).toLowerCase();
                  const disabled = Boolean(challenge.submitted) || submittingPredictionId === challenge.challenge_id;
                  return (
                    <TouchableOpacity
                      key={`${challenge.challenge_id}-${optionKey}`}
                      onPress={() => submitPrediction(challenge.challenge_id, optionKey)}
                      disabled={disabled}
                      style={{
                        borderRadius: 999,
                        borderWidth: 1,
                        borderColor: selected ? `${colors.successText}66` : `${colors.warningText}44`,
                        backgroundColor: selected ? `${colors.successText}16` : colors.card,
                        paddingHorizontal: 10,
                        paddingVertical: 6,
                        opacity: disabled && !selected ? 0.6 : 1,
                      }}
                      data-testid={`sports-v2-prediction-option-${challenge.challenge_id}-${optionKey}`}
                      testID={`sports-v2-prediction-option-${challenge.challenge_id}-${optionKey}`}
                    >
                      <Text style={{ color: selected ? colors.successText : colors.textSec, fontSize: 10.5, fontWeight: '700' }}>
                        {challenge?.option_labels?.[optionKey] || optionKey}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          ))}
        </View>
      </View>

      {liveNow.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="sports-v2-live-events-rail" testID="sports-v2-live-events-rail">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 6 }}>LIVE NOW</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {liveNow.map((item) => (
              <TouchableOpacity key={`sports-v2-live-item-${item.item_id}`} onPress={() => playItem(item, 'live')} style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }} data-testid={`sports-v2-live-item-${item.item_id}`}>
                <View style={{ width: '100%', aspectRatio: '16 / 9', backgroundColor: colors.bgSoft }}>
                  <Image source={{ uri: item.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="LIVE NOW" />
                </View>
                <View style={{ padding: 9 }}>
                  <Text style={{ color: colors.successText, fontSize: 10.5, fontWeight: '800' }}>LIVE NOW</Text>
                  <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800', marginTop: 4 }} numberOfLines={2}>{item.title}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 2 }} numberOfLines={1}>{item.league || item.category}</Text>
                </View>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {comingUp.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="sports-v2-coming-up-rail" testID="sports-v2-coming-up-rail">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 6 }}>COMING UP</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {comingUp.map((item) => (
              <TouchableOpacity key={`sports-v2-coming-item-${item.item_id}`} onPress={() => playItem(item, 'manual')} style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }} data-testid={`sports-v2-coming-item-${item.item_id}`}>
                <View style={{ width: '100%', aspectRatio: '16 / 9', backgroundColor: colors.bgSoft }}>
                  <Image source={{ uri: item.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="COMING UP" />
                </View>
                <View style={{ padding: 9 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 10.5, fontWeight: '800' }}>UPCOMING</Text>
                  <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800', marginTop: 4 }} numberOfLines={2}>{item.title}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 2 }} numberOfLines={1}>{item.category} • {item.league}</Text>
                </View>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="sports-v2-weekly-inbox" testID="sports-v2-weekly-inbox">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14.5 }}>Weekly Event Inbox</Text>
          <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 8, paddingVertical: 4 }}>
            <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{bootstrap?.daily_drop_inbox?.unread || 0} unread</Text>
          </View>
        </View>

        <View style={{ marginTop: 8, gap: 8 }}>
          {(bootstrap?.daily_drop_inbox?.items || []).slice(0, 6).map((item: SportsItem & { listened?: boolean }) => (
            <View key={`sports-v2-inbox-${item.item_id}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }} data-testid={`sports-v2-inbox-item-${item.item_id}`}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5 }}>{item.category} • {item.listened ? 'Watched' : 'New drop'}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                <TouchableOpacity onPress={() => playItem(item, 'inbox')} style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 5, backgroundColor: `${colors.warningText}18` }} data-testid={`sports-v2-inbox-play-${item.item_id}`}>
                  <Text style={{ color: colors.warningText, fontWeight: '700', fontSize: 10.5 }}>Play</Text>
                </TouchableOpacity>
                {!item.listened ? (
                  <TouchableOpacity onPress={() => markInboxListened(item)} style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 5, borderWidth: 1, borderColor: colors.border }} data-testid={`sports-v2-inbox-mark-${item.item_id}`}>
                    <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 10.5 }}>Mark watched</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>
          ))}
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 12 }} data-testid="sports-v2-categories" testID="sports-v2-categories">
        {categories.map((cat) => {
          const active = selectedCategory === cat;
          return (
            <TouchableOpacity
              key={cat}
              onPress={() => setSelectedCategory(cat)}
              style={{ borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, borderColor: active ? `${colors.warningText}66` : colors.border, backgroundColor: active ? `${colors.warningText}12` : colors.bgSoft }}
              data-testid={`sports-v2-category-${String(cat).toLowerCase().replace(/\s+/g, '-')}`}
            >
              <Text style={{ color: active ? colors.warningText : colors.textSec, fontWeight: active ? '800' : '600', fontSize: 11.5 }}>{cat === 'all' ? 'All Leagues' : cat}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 10, alignItems: 'stretch' }} data-testid="sports-v2-grid" testID="sports-v2-grid">
        {visibleItems.map((item) => {
          const regionBlocked = Boolean(item?.blackout_blocked);
          const unavailable = !isWatchableNow(item);
          const locked = regionBlocked || unavailable || isLocked(item);
          return (
            <TouchableOpacity
              key={item.item_id}
              onPress={() => playItem(item, 'manual')}
              style={{ width: cardWidth as any, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }}
              data-testid={`sports-v2-grid-item-${item.item_id}`}
            >
              <View style={{ width: '100%', aspectRatio: '1 / 1', backgroundColor: colors.bgSoft }}>
                <Image source={{ uri: item.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="SPORTS EVENT" />
                <View style={{ position: 'absolute', top: 8, right: 8, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: 'rgba(0,0,0,0.55)', flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  {locked ? <Ionicons name="lock-closed-outline" size={10} color="var(--app-primary-text)" /> : <Ionicons name="play" size={10} color="var(--app-primary-text)" />}
                  <Text style={{ color: 'var(--app-primary-text)', fontSize: 10.5, fontWeight: '700' }}>
                    {regionBlocked ? 'BLACKOUT' : unavailable ? 'UNAVAILABLE' : String(item.min_plan || 'free').toUpperCase()}
                  </Text>
                </View>
              </View>
              <View style={{ padding: 10 }}>
                <Text numberOfLines={2} style={{ color: colors.text, fontWeight: '700', fontSize: 12.5 }}>{item.title}</Text>
                <Text numberOfLines={1} style={{ marginTop: 4, color: colors.textSec, fontSize: 11.5 }}>{item.category} • {item.creator}</Text>
                <Text numberOfLines={1} style={{ marginTop: 2, color: isWatchableNow(item) ? colors.successText : colors.warningText, fontSize: 10.5, fontWeight: '700' }}>
                  {isWatchableNow(item)
                    ? (item?.is_embeddable_playable ? `Playable score ${Math.max(0, Number(item.embeddability_score || 0))}` : 'Watch via official source link')
                    : `Unavailable (${item?.blackout_reason || 'precheck'})`}
                </Text>
                <Text numberOfLines={1} style={{ marginTop: 2, color: colors.textMuted, fontSize: 10.5 }}>
                  {`${item.league || item.category} • ${formatDuration(item.duration_seconds)}`}
                </Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      {externalConfirmVisible ? (
        <Modal animationType="fade" transparent visible={externalConfirmVisible} onRequestClose={() => setExternalConfirmVisible(false)}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center', alignItems: 'center', padding: 16 }} data-testid="sports-v2-external-open-modal-overlay" testID="sports-v2-external-open-modal-overlay">
            <View style={{ width: '100%', maxWidth: 420, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} data-testid="sports-v2-external-open-modal" testID="sports-v2-external-open-modal">
              <Text style={{ color: colors.text, fontWeight: '800', fontSize: 16 }}>Open official stream</Text>
              <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 6 }}>
                This stream opens on the official source so you can watch immediately.
              </Text>
              <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }} data-testid="sports-v2-external-open-trust-badges">
                <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: `${colors.successText}16`, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="sports-v2-external-open-badge-source-verified">
                  <Text style={{ color: colors.successText, fontSize: 10.5, fontWeight: '800' }}>Source verified</Text>
                </View>
                <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}16`, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="sports-v2-external-open-badge-official-page">
                  <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '800' }}>Opens official page</Text>
                </View>
              </View>
              <TouchableOpacity onPress={() => setRememberExternalConfirmSession((prev) => !prev)} style={{ marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="sports-v2-external-open-remember-toggle">
                <Ionicons name={rememberExternalConfirmSession ? 'checkbox-outline' : 'square-outline'} size={18} color={rememberExternalConfirmSession ? colors.warningText : colors.textSec} />
                <Text style={{ color: colors.textSec, fontSize: 12 }}>Don’t ask again this session</Text>
              </TouchableOpacity>
              <View style={{ marginTop: 14, flexDirection: 'row', justifyContent: 'flex-end', gap: 8 }}>
                <TouchableOpacity onPress={() => setExternalConfirmVisible(false)} style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, paddingVertical: 7 }} data-testid="sports-v2-external-open-cancel">
                  <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={confirmExternalOpen} style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: `${colors.successText}16`, paddingHorizontal: 12, paddingVertical: 7 }} data-testid="sports-v2-external-open-confirm">
                  <Text style={{ color: colors.successText, fontWeight: '800', fontSize: 12 }}>Continue to official stream</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      ) : null}
    </ScrollView>
  );
};

export default SportsFeature30;
