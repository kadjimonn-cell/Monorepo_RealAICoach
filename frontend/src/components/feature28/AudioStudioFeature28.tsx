import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Linking, Platform, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import {
  MAX_RETRY_ATTEMPTS,
  PlaybackChaosController,
  evaluateResilienceDecision,
  getNextQueueCandidateIndex,
} from './playbackResilience';

type AudioItem = {
  item_id: string;
  title: string;
  description?: string;
  category?: string;
  creator?: string;
  artist_name?: string;
  album_name?: string;
  audio_url?: string;
  thumbnail_url?: string;
  duration_seconds?: number;
  min_plan?: 'free' | 'basic' | 'premium' | string;
};

type BootstrapData = {
  feature_id?: string;
  quota?: { plan?: string; daily_play_limit?: number; daily_play_used?: number; daily_play_remaining?: number; scope_label?: string };
  categories?: string[];
  catalog?: AudioItem[];
  featured_item?: AudioItem | null;
  source_health?: {
    status?: string;
    reason_code?: string;
    total_items?: number;
    playable_items?: number;
    secure_https_ratio?: number;
  };
  daily_drop_inbox?: { items?: AudioItem[]; unread?: number };
};

const formatDuration = (seconds?: number) => {
  const mins = Math.max(1, Math.round(Number(seconds || 0) / 60));
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${m}m`;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const AudioStudioFeature28 = () => {
  const { colors } = useTheme();
  const sessionKeyRef = useRef(`audio28-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);
  const promptViewTrackedRef = useRef(false);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [bootstrap, setBootstrap] = useState<BootstrapData | null>(null);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedItem, setSelectedItem] = useState<AudioItem | null>(null);
  const [playError, setPlayError] = useState('');
  const [syncingPlay, setSyncingPlay] = useState(false);
  const [playbackRetryCount, setPlaybackRetryCount] = useState(0);
  const [autoAdvanceEnabled, setAutoAdvanceEnabled] = useState(true);
  const [queueSeedId, setQueueSeedId] = useState<string>('');
  const [dailyDropItems, setDailyDropItems] = useState<AudioItem[]>([]);

  const queueCursorRef = useRef(0);
  const chaosControllerRef = useRef(new PlaybackChaosController('none'));

  const loadBootstrap = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const tz = (() => {
        try {
          if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
        } catch (error) {
          handleAppRecoverableError({ scope: 'src/components/feature28/AudioStudioFeature28.tsx#timezone', error, message: 'Something went wrong. Please retry.', notifyMode: 'silent' });
        }
        return 'UTC';
      })();

      const res = await api.get(`/audio-studio/v2/bootstrap?tz=${encodeURIComponent(tz)}`, { silentLoading: true, skipDedupe: true });
      const data: BootstrapData = res?.data || {};
      setBootstrap(data);
      setDailyDropItems((data?.daily_drop_inbox?.items || []).slice(0, 12));
      const first = data?.featured_item || (data?.catalog || [])[0] || null;
      setSelectedItem(first);
      setQueueSeedId(String(first?.item_id || ''));
      queueCursorRef.current = 0;
    } catch (error: any) {
      const msg = String(error?.response?.data?.detail || error?.message || 'Unable to load Audio Studio');
      setLoadError(msg);
      setBootstrap(null);
      setSelectedItem(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBootstrap();
  }, [loadBootstrap]);

  const plan = String(bootstrap?.quota?.plan || 'free').toLowerCase();
  const planLevel = useMemo(() => ({ free: 0, basic: 1, premium: 2 }), []);

  const categories = useMemo(() => ['all', ...((bootstrap?.categories || []).filter(Boolean))], [bootstrap?.categories]);

  const visibleItems = useMemo(() => {
    const all = (bootstrap?.catalog || []) as AudioItem[];
    const filtered = selectedCategory === 'all'
      ? all
      : all.filter((item) => String(item.category || '').toLowerCase() === String(selectedCategory).toLowerCase());
    return filtered;
  }, [bootstrap?.catalog, selectedCategory]);

  const adaptiveQueue = useMemo(() => {
    const all = visibleItems;
    if (!selectedItem?.item_id) return all;
    const currentIndex = all.findIndex((item) => item.item_id === selectedItem.item_id);
    if (currentIndex < 0) return all;
    return [...all.slice(currentIndex + 1), ...all.slice(0, currentIndex)].filter((row) => row.item_id !== selectedItem.item_id);
  }, [selectedItem?.item_id, visibleItems]);

  const isLocked = useCallback((item: AudioItem) => {
    const required = planLevel[String(item?.min_plan || 'free').toLowerCase() as 'free' | 'basic' | 'premium'] ?? 0;
    const current = planLevel[plan as 'free' | 'basic' | 'premium'] ?? 0;
    return required > current;
  }, [plan, planLevel]);

  const openUpgrade = useCallback(() => {
    void api.post('/subscription-conversion/telemetry', {
      session_key: sessionKeyRef.current,
      event_type: 'plan_cta_click',
      plan_id: 'basic',
      billing_period: 'monthly',
      role: 'listener',
      device_bucket: Platform.OS === 'web' ? 'web' : 'native',
      route: '/features/audio-studio',
      source: 'audio_studio_v2',
    }, { silentLoading: true });

    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.location.assign('/subscription/plans');
      return;
    }
    void Linking.openURL('/subscription/plans');
  }, []);

  const syncPlayToServer = useCallback(async (item: AudioItem) => {
    const response = await api.post(
      '/audio-studio/v2/play',
      { item_id: item.item_id, listen_seconds: 0, completed: false, source: 'feature28_v2_catalog_tap' },
      { silentLoading: true },
    );
    const status = Number(response?.status || 200);
    const result = chaosControllerRef.current.inject({ ok: status >= 200 && status < 300, status, detail: '' });
    if (!result.ok) {
      const chaosError: any = new Error(String(result.detail || 'Playback failed'));
      chaosError.response = {
        status: Number(result.status || 500),
        data: { detail: String(result.detail || 'Playback failed') },
      };
      throw chaosError;
    }
    return (response?.data?.item || item) as AudioItem;
  }, []);

  const playItemWithResilience = useCallback(async (item: AudioItem, origin: 'manual' | 'queue' = 'manual') => {
    if (!item?.item_id) return;
    if (isLocked(item)) {
      setPlayError(`Locked: requires ${String(item.min_plan || 'premium').toUpperCase()} plan`);
      setPlaybackRetryCount(0);
      return;
    }

    setSelectedItem(item);
    setQueueSeedId(item.item_id);
    queueCursorRef.current = 0;
    setSyncingPlay(true);
    setPlayError('');

    for (let attempt = 0; attempt < MAX_RETRY_ATTEMPTS; attempt += 1) {
      try {
        const merged = await syncPlayToServer(item);
        setSelectedItem({ ...item, ...merged });
        setPlaybackRetryCount(attempt);
        setSyncingPlay(false);
        return;
      } catch (error: any) {
        const status = Number(error?.response?.status || 0);
        const detail = String(error?.response?.data?.detail || error?.message || 'Playback failed');
        const decision = evaluateResilienceDecision(attempt, { ok: false, status, detail });

        if (decision.shouldRetry) {
          setPlayError(`Retrying playback (${attempt + 1}/${MAX_RETRY_ATTEMPTS})...`);
          await sleep(decision.nextDelayMs);
          continue;
        }

        setPlayError(decision.terminalErrorMessage || detail);
        setSyncingPlay(false);
        setPlaybackRetryCount(MAX_RETRY_ATTEMPTS);

        if (decision.shouldOpenUpgrade) {
          openUpgrade();
          return;
        }

        if (origin === 'queue') {
          const next = adaptiveQueue.find((row) => !isLocked(row));
          if (next && next.item_id !== item.item_id) {
            setTimeout(() => {
              void playItemWithResilience(next, 'queue');
            }, 250);
          }
        }
        return;
      }
    }
  }, [adaptiveQueue, isLocked, openUpgrade, syncPlayToServer]);

  const playNextInQueue = useCallback(() => {
    if (!autoAdvanceEnabled) return;
    if (!adaptiveQueue.length) return;

    const { nextCursor, selectedIndex } = getNextQueueCandidateIndex(queueCursorRef.current, adaptiveQueue.length);
    queueCursorRef.current = nextCursor;
    const nextIndex = selectedIndex;
    const next = adaptiveQueue[nextIndex];
    if (!next) return;
    void playItemWithResilience(next, 'queue');
  }, [adaptiveQueue, autoAdvanceEnabled, playItemWithResilience]);

  const handleAudioEnded = useCallback(async (event: any) => {
    const currentItem = selectedItem;
    if (currentItem?.item_id) {
      const listenSeconds = Math.max(0, Math.round(Number(event?.currentTarget?.currentTime || event?.target?.currentTime || currentItem?.duration_seconds || 0)));
      try {
        await api.post(
          '/audio-studio/v2/play',
          { item_id: currentItem.item_id, listen_seconds: listenSeconds, completed: true, source: 'feature28_v2_track_ended' },
          { silentLoading: true },
        );
      } catch (error) {
        handleAppRecoverableError({
          scope: 'src/components/feature28/AudioStudioFeature28.tsx#handleAudioEnded',
          error,
          message: 'Playback tracking degraded. You can continue listening.',
          notifyMode: 'silent',
        });
      }
    }
    playNextInQueue();
  }, [playNextInQueue, selectedItem]);

  const markInboxListened = useCallback(async (item: AudioItem) => {
    if (!item?.item_id) return;
    try {
      await api.post('/audio-studio/v2/daily-drop-inbox/mark-listened', { item_id: item.item_id }, { silentLoading: true });
      setDailyDropItems((prev) => prev.filter((row) => row.item_id !== item.item_id));
    } catch (error) {
      handleAppRecoverableError({
        scope: 'src/components/feature28/AudioStudioFeature28.tsx#markInboxListened',
        error,
        message: 'Could not update daily drop state. Please retry.',
        notifyMode: 'toast',
      });
    }
  }, []);

  useEffect(() => {
    if (promptViewTrackedRef.current) return;
    if (!bootstrap?.quota) return;
    promptViewTrackedRef.current = true;

    const plan = String(bootstrap?.quota?.plan || 'free').toLowerCase();
    void api.post('/subscription-prompt/telemetry', {
      session_key: sessionKeyRef.current,
      current_plan: plan,
      required_plan: 'basic',
      source: 'audio_studio_v2',
      endpoint: '/audio-studio/v2/play',
      route: '/features/audio-studio',
    }, { silentLoading: true });

    void api.post('/subscription-conversion/telemetry', {
      session_key: sessionKeyRef.current,
      event_type: 'plan_card_view',
      plan_id: 'basic',
      billing_period: 'monthly',
      role: 'listener',
      device_bucket: Platform.OS === 'web' ? 'web' : 'native',
      route: '/features/audio-studio',
      source: 'audio_studio_v2',
    }, { silentLoading: true });
  }, [bootstrap?.quota]);

  const sourceHealth = bootstrap?.source_health || {};
  const sourceHealthStatus = String(sourceHealth?.status || 'UNKNOWN').toUpperCase();
  const sourceHealthTone = sourceHealthStatus === 'HEALTHY'
    ? colors.successText
    : sourceHealthStatus === 'DEGRADED'
      ? colors.warningText
      : colors.errorText;

  if (loading) {
    return (
      <View style={{ minHeight: 360, justifyContent: 'center', alignItems: 'center' }} data-testid="feature28-audio-studio-v2-loading" testID="feature28-audio-studio-v2-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, marginTop: 8, fontSize: 12 }}>Loading Audio Studio v2...</Text>
      </View>
    );
  }

  if (loadError) {
    return (
      <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} data-testid="feature28-audio-studio-v2-error-card" testID="feature28-audio-studio-v2-error-card">
        <Text style={{ color: colors.errorText, fontSize: 12, fontWeight: '800' }} data-testid="feature28-audio-studio-v2-error-text" testID="feature28-audio-studio-v2-error-text">{loadError}</Text>
        <TouchableOpacity onPress={loadBootstrap} style={{ marginTop: 8, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: colors.primary, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="feature28-audio-studio-v2-error-retry-button" testID="feature28-audio-studio-v2-error-retry-button">
          <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 24 }} data-testid="feature28-audio-studio-v2-root" testID="feature28-audio-studio-v2-root">
      <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} data-testid="feature28-audio-studio-v2-hero-card" testID="feature28-audio-studio-v2-hero-card">
        <Text style={{ color: colors.text, fontSize: 20, fontWeight: '900' }} data-testid="feature28-audio-studio-v2-title" testID="feature28-audio-studio-v2-title">Audio Studio v2</Text>
        <Text style={{ color: colors.textSec, marginTop: 4, fontSize: 12 }} data-testid="feature28-audio-studio-v2-subtitle" testID="feature28-audio-studio-v2-subtitle">
          YouTube-audio style: curated queue, resilient playback, and continuous listening.
        </Text>

        <View style={{ marginTop: 9, borderRadius: 10, borderWidth: 1, borderColor: `${sourceHealthTone}55`, backgroundColor: `${sourceHealthTone}12`, padding: 10 }} data-testid="feature28-audio-studio-v2-source-health-banner" testID="feature28-audio-studio-v2-source-health-banner">
          <Text style={{ color: sourceHealthTone, fontSize: 11, fontWeight: '800' }} data-testid="feature28-audio-studio-v2-source-health-status" testID="feature28-audio-studio-v2-source-health-status">{`Source health: ${sourceHealthStatus}`}</Text>
          <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 3 }} data-testid="feature28-audio-studio-v2-source-health-reason" testID="feature28-audio-studio-v2-source-health-reason">{String(sourceHealth?.reason_code || 'AUDIO_STUDIO_SOURCE_HEALTH_UNKNOWN')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }} data-testid="feature28-audio-studio-v2-source-health-metrics" testID="feature28-audio-studio-v2-source-health-metrics">
            {`Playable ${Number(sourceHealth?.playable_items || 0)}/${Number(sourceHealth?.total_items || 0)} · HTTPS ${(Number(sourceHealth?.secure_https_ratio || 0) * 100).toFixed(0)}%`}
          </Text>
        </View>

        <Text style={{ marginTop: 8, color: colors.textMuted, fontSize: 11 }} data-testid="feature28-audio-studio-v2-plan-quota-text" testID="feature28-audio-studio-v2-plan-quota-text">
          {`Plan ${String(bootstrap?.quota?.plan || 'free').toUpperCase()} · Remaining plays ${Number(bootstrap?.quota?.daily_play_remaining || 0)}`}
        </Text>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 12 }} data-testid="feature28-audio-studio-v2-categories-scroll" testID="feature28-audio-studio-v2-categories-scroll">
        {categories.map((cat) => {
          const active = selectedCategory === cat;
          return (
            <TouchableOpacity
              key={`f28-cat-${cat}`}
              onPress={() => { setSelectedCategory(cat); queueCursorRef.current = 0; }}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? `${colors.primary}1A` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid={`feature28-audio-studio-v2-category-${String(cat).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
              testID={`feature28-audio-studio-v2-category-${String(cat).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
            >
              <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700' }}>{cat === 'all' ? 'All' : cat}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={{ marginTop: 12, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="feature28-audio-studio-v2-player-card" testID="feature28-audio-studio-v2-player-card">
        <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
          <View style={{ width: 120, aspectRatio: '16 / 10', borderRadius: 10, overflow: 'hidden', backgroundColor: colors.bgSoft }}>
            {selectedItem?.thumbnail_url ? <Image source={{ uri: selectedItem.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="feature28-current-cover" /> : null}
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} numberOfLines={1} data-testid="feature28-audio-studio-v2-player-title" testID="feature28-audio-studio-v2-player-title">{selectedItem?.title || 'Pick a track'}</Text>
            <Text style={{ color: colors.textSec, fontSize: 11.5, marginTop: 2 }} numberOfLines={1} data-testid="feature28-audio-studio-v2-player-meta" testID="feature28-audio-studio-v2-player-meta">
              {`${selectedItem?.artist_name || selectedItem?.creator || 'Curated Artist'} • ${selectedItem?.album_name || 'Studio Album'}`}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 2 }} data-testid="feature28-audio-studio-v2-player-duration" testID="feature28-audio-studio-v2-player-duration">{formatDuration(selectedItem?.duration_seconds)}</Text>
            {syncingPlay ? <ActivityIndicator size="small" color={colors.primary} style={{ marginTop: 6 }} /> : null}
          </View>
        </View>

        {Platform.OS === 'web' && selectedItem?.audio_url ? (
          <audio
            controls
            autoPlay
            src={selectedItem.audio_url}
            onEnded={(event) => { void handleAudioEnded(event); }}
            style={{ width: '100%', height: 38, marginTop: 8 }}
            data-testid="feature28-audio-studio-v2-web-player"
          />
        ) : null}

        <View style={{ marginTop: 8, flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <TouchableOpacity onPress={() => selectedItem && playItemWithResilience(selectedItem, 'manual')} style={{ borderRadius: 999, backgroundColor: `${colors.primary}20`, borderWidth: 1, borderColor: `${colors.primary}66`, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="feature28-audio-studio-v2-player-replay-button" testID="feature28-audio-studio-v2-player-replay-button">
            <Text style={{ color: colors.primary, fontSize: 10.5, fontWeight: '800' }}>Replay</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={playNextInQueue} style={{ borderRadius: 999, backgroundColor: `${colors.successText}14`, borderWidth: 1, borderColor: `${colors.successText}66`, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="feature28-audio-studio-v2-player-next-button" testID="feature28-audio-studio-v2-player-next-button">
            <Text style={{ color: colors.successText, fontSize: 10.5, fontWeight: '800' }}>Play Next</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setAutoAdvanceEnabled((prev) => !prev)} style={{ borderRadius: 999, backgroundColor: autoAdvanceEnabled ? `${colors.primary}14` : colors.bgSoft, borderWidth: 1, borderColor: autoAdvanceEnabled ? `${colors.primary}66` : colors.border, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="feature28-audio-studio-v2-auto-advance-toggle" testID="feature28-audio-studio-v2-auto-advance-toggle">
            <Text style={{ color: autoAdvanceEnabled ? colors.primary : colors.textSec, fontSize: 10.5, fontWeight: '800' }}>{`Auto-next ${autoAdvanceEnabled ? 'ON' : 'OFF'}`}</Text>
          </TouchableOpacity>
        </View>

        {playError ? (
          <View style={{ marginTop: 8, borderRadius: 8, borderWidth: 1, borderColor: `${colors.errorText}55`, backgroundColor: `${colors.errorText}10`, padding: 8 }} data-testid="feature28-audio-studio-v2-playback-error-banner" testID="feature28-audio-studio-v2-playback-error-banner">
            <Text style={{ color: colors.errorText, fontSize: 10.5, fontWeight: '700' }} data-testid="feature28-audio-studio-v2-playback-error-text" testID="feature28-audio-studio-v2-playback-error-text">{playError}</Text>
            {playError.toLowerCase().includes('requires') || playError.toLowerCase().includes('plan') || playError.toLowerCase().includes('cap reached') ? (
              <TouchableOpacity onPress={openUpgrade} style={{ marginTop: 6, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: colors.primary, paddingHorizontal: 8, paddingVertical: 5 }} data-testid="feature28-audio-studio-v2-upgrade-cta-button" testID="feature28-audio-studio-v2-upgrade-cta-button">
                <Text style={{ color: colors.primary, fontSize: 10.5, fontWeight: '800' }}>Upgrade Plan</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}

        <Text style={{ marginTop: 6, color: colors.textMuted, fontSize: 10.5 }} data-testid="feature28-audio-studio-v2-retry-counter" testID="feature28-audio-studio-v2-retry-counter">
          {`Resilience retries: ${playbackRetryCount}/${MAX_RETRY_ATTEMPTS}`}
        </Text>
      </View>

      <View style={{ marginTop: 12, gap: 8 }} data-testid="feature28-audio-studio-v2-grid" testID="feature28-audio-studio-v2-grid">
        {visibleItems.map((item) => {
          const locked = isLocked(item);
          return (
            <TouchableOpacity
              key={`f28-item-${item.item_id}`}
              onPress={() => void playItemWithResilience(item, 'manual')}
              style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10, flexDirection: 'row', alignItems: 'center', gap: 9 }}
              data-testid={`feature28-audio-studio-v2-item-${item.item_id}`}
              testID={`feature28-audio-studio-v2-item-${item.item_id}`}
            >
              <View style={{ width: 76, aspectRatio: '16 / 10', borderRadius: 8, overflow: 'hidden', backgroundColor: colors.bgSoft }}>
                {item.thumbnail_url ? <Image source={{ uri: item.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="feature28-item-cover" /> : null}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} numberOfLines={2}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 2 }} numberOfLines={1}>{`${item.artist_name || item.creator || 'Curated'} • ${item.category || 'General'}`}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{formatDuration(item.duration_seconds)}</Text>
              </View>
              <View style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: locked ? `${colors.warningText}18` : `${colors.primary}18` }}>
                <Text style={{ color: locked ? colors.warningText : colors.primary, fontSize: 10, fontWeight: '800' }}>{locked ? 'LOCKED' : 'PLAY'}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={{ marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid="feature28-audio-studio-v2-queue-panel" testID="feature28-audio-studio-v2-queue-panel">
        <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800' }}>Up Next Queue</Text>
        <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 2 }} data-testid="feature28-audio-studio-v2-queue-seed" testID="feature28-audio-studio-v2-queue-seed">{`Queue seed: ${queueSeedId || 'none'}`}</Text>
        <View style={{ marginTop: 6, gap: 6 }}>
          {adaptiveQueue.slice(0, 6).map((item, idx) => (
            <View key={`f28-q-${item.item_id}`} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid={`feature28-audio-studio-v2-queue-item-${item.item_id}`} testID={`feature28-audio-studio-v2-queue-item-${item.item_id}`}>
              <Text style={{ color: colors.textSec, fontSize: 10.5, flex: 1 }} numberOfLines={1}>{`${idx + 1}. ${item.title}`}</Text>
              <Ionicons name="play-forward" size={12} color={colors.textMuted} />
            </View>
          ))}
        </View>
      </View>

      {dailyDropItems.length > 0 ? (
        <View style={{ marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid="feature28-audio-studio-v2-daily-drop-panel" testID="feature28-audio-studio-v2-daily-drop-panel">
          <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800' }}>Daily Drop Inbox</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 2 }} data-testid="feature28-audio-studio-v2-daily-drop-unread" testID="feature28-audio-studio-v2-daily-drop-unread">{`${dailyDropItems.length} items pending`}</Text>
          <View style={{ marginTop: 7, gap: 7 }}>
            {dailyDropItems.slice(0, 5).map((item) => (
              <View key={`f28-daily-${item.item_id}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 8, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`feature28-audio-studio-v2-daily-drop-item-${item.item_id}`} testID={`feature28-audio-studio-v2-daily-drop-item-${item.item_id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700' }} numberOfLines={2}>{item.title}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }} numberOfLines={1}>{item.artist_name || item.creator || 'Curated artist'}</Text>
                </View>
                <TouchableOpacity onPress={() => void playItemWithResilience(item, 'manual')} style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}14`, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`feature28-audio-studio-v2-daily-drop-play-${item.item_id}`} testID={`feature28-audio-studio-v2-daily-drop-play-${item.item_id}`}>
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>Play</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => void markInboxListened(item)} style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`feature28-audio-studio-v2-daily-drop-mark-${item.item_id}`} testID={`feature28-audio-studio-v2-daily-drop-mark-${item.item_id}`}>
                  <Text style={{ color: colors.textSec, fontSize: 10, fontWeight: '700' }}>Done</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </View>
      ) : null}
    </ScrollView>
  );
};

export default AudioStudioFeature28;
