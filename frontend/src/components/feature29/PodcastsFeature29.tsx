import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Linking, Platform, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type AudioItem = {
  item_id: string;
  title: string;
  description?: string;
  category?: string;
  creator?: string;
  host_name?: string;
  series_name?: string;
  audio_url?: string;
  stream_url?: string;
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
  behavioral_ai?: { reengagement_nudge?: string; best_time_to_return?: { label?: string; window?: string } };
  behavioral_rails?: { title?: string; items?: AudioItem[] }[];
  smart_follow_up_items?: AudioItem[];
  adaptive_next_queue?: AudioItem[];
  podcast_story_arc?: { series_name?: string; items?: AudioItem[] };
  season_binge_rails?: { title?: string; series_name?: string; items?: AudioItem[] }[];
  daily_drop_inbox?: { items?: (AudioItem & { listened?: boolean })[]; unread?: number };
};

const PLAN_LEVEL = { free: 0, basic: 1, premium: 2 };
const MAX_RETRY_ATTEMPTS = 3;

const formatDuration = (seconds?: number) => {
  const mins = Math.max(1, Math.round(Number(seconds || 0) / 60));
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${m}m`;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const PodcastsFeature29 = () => {
  const { colors } = useTheme();
  const sessionKeyRef = useRef(`pod29-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [bootstrap, setBootstrap] = useState<BootstrapData | null>(null);
  const [continueItems, setContinueItems] = useState<AudioItem[]>([]);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedItem, setSelectedItem] = useState<AudioItem | null>(null);
  const [playError, setPlayError] = useState('');
  const [syncingPlay, setSyncingPlay] = useState(false);
  const [playbackRetryCount, setPlaybackRetryCount] = useState(0);
  const [autoPlayStoryArcEnabled, setAutoPlayStoryArcEnabled] = useState(true);

  const queueCursorRef = useRef(0);

  const loadBootstrap = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const tz = (() => {
        try {
          if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
        } catch (error) {
          handleAppRecoverableError({ scope: 'src/components/feature29/PodcastsFeature29.tsx#timezone', error, message: 'Something went wrong. Please retry.', notifyMode: 'silent' });
        }
        return 'UTC';
      })();

      const [bootstrapRes, continueRes] = await Promise.all([
        api.get(`/podcasts/v2/bootstrap?tz=${encodeURIComponent(tz)}`, { silentLoading: true, skipDedupe: true }),
        api.get('/podcasts/v2/continue-listening', { silentLoading: true, skipDedupe: true }),
      ]);

      const data: BootstrapData = bootstrapRes?.data || {};
      setBootstrap(data);
      setContinueItems((continueRes?.data?.items || []).slice(0, 12));
      const first = data?.featured_item || (data?.catalog || [])[0] || null;
      setSelectedItem(first);
      queueCursorRef.current = 0;
    } catch (error: any) {
      const msg = String(error?.response?.data?.detail || error?.message || 'Unable to load My Podcasts');
      setLoadError(msg);
      setBootstrap(null);
      setSelectedItem(null);
      setContinueItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBootstrap();
  }, [loadBootstrap]);

  const plan = String(bootstrap?.quota?.plan || 'free').toLowerCase();
  const categories = useMemo(() => ['all', ...((bootstrap?.categories || []).filter(Boolean))], [bootstrap?.categories]);

  const visibleItems = useMemo(() => {
    const all = (bootstrap?.catalog || []) as AudioItem[];
    return selectedCategory === 'all'
      ? all
      : all.filter((item) => String(item.category || '').toLowerCase() === String(selectedCategory).toLowerCase());
  }, [bootstrap?.catalog, selectedCategory]);

  const storyArcItems = useMemo(() => (bootstrap?.podcast_story_arc?.items || []).slice(0, 10), [bootstrap?.podcast_story_arc?.items]);

  const adaptiveQueue = useMemo(() => {
    const rows = ((bootstrap?.adaptive_next_queue || []) as AudioItem[]).filter(Boolean);
    if (!rows.length) return visibleItems;
    return rows;
  }, [bootstrap?.adaptive_next_queue, visibleItems]);

  const isLocked = useCallback((item: AudioItem) => {
    const required = PLAN_LEVEL[String(item?.min_plan || 'free').toLowerCase() as 'free' | 'basic' | 'premium'] ?? 0;
    const current = PLAN_LEVEL[plan as 'free' | 'basic' | 'premium'] ?? 0;
    return required > current;
  }, [plan]);

  const openUpgrade = useCallback(() => {
    void api.post('/subscription-conversion/telemetry', {
      session_key: sessionKeyRef.current,
      event_type: 'plan_cta_click',
      plan_id: 'basic',
      billing_period: 'monthly',
      role: 'listener',
      device_bucket: Platform.OS === 'web' ? 'web' : 'native',
      route: '/features/my-podcasts',
      source: 'podcasts_v2',
    }, { silentLoading: true });

    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.location.assign('/subscription/plans');
      return;
    }
    void Linking.openURL('/subscription/plans');
  }, []);

  const syncPlayToServer = useCallback(async (item: AudioItem, source: string, completed: boolean, listenSeconds: number) => {
    const response = await api.post(
      '/podcasts/v2/play',
      { item_id: item.item_id, listen_seconds: listenSeconds, completed, source },
      { silentLoading: true },
    );
    return (response?.data?.item || item) as AudioItem;
  }, []);

  const playItem = useCallback(async (item: AudioItem, source: 'manual' | 'queue' | 'inbox' | 'story_arc' = 'manual') => {
    if (!item?.item_id) return;
    if (isLocked(item)) {
      setPlayError(`Locked: requires ${String(item.min_plan || 'premium').toUpperCase()} plan`);
      setPlaybackRetryCount(0);
      return;
    }

    setSelectedItem(item);
    setSyncingPlay(true);
    setPlayError('');

    for (let attempt = 0; attempt < MAX_RETRY_ATTEMPTS; attempt += 1) {
      try {
        const merged = await syncPlayToServer(item, `feature29_v2_${source}`, false, 0);
        setSelectedItem({ ...item, ...merged });
        setPlaybackRetryCount(attempt);
        setSyncingPlay(false);
        return;
      } catch (error: any) {
        const status = Number(error?.response?.status || 0);
        const detail = String(error?.response?.data?.detail || error?.message || 'Playback failed');
        const retryable = status >= 500 || status === 429 || status === 0;

        if (retryable && attempt < MAX_RETRY_ATTEMPTS - 1) {
          setPlayError(`Retrying playback (${attempt + 1}/${MAX_RETRY_ATTEMPTS})...`);
          await sleep((attempt + 1) * 500);
          continue;
        }

        setPlayError(detail);
        setSyncingPlay(false);
        setPlaybackRetryCount(MAX_RETRY_ATTEMPTS);

        if (status === 403 || /requires/i.test(detail)) {
          openUpgrade();
          return;
        }

        if (source === 'queue') {
          const next = adaptiveQueue.find((row) => !isLocked(row));
          if (next && next.item_id !== item.item_id) {
            setTimeout(() => {
              void playItem(next, 'queue');
            }, 250);
          }
        }
        return;
      }
    }
  }, [adaptiveQueue, isLocked, openUpgrade, syncPlayToServer]);

  const playNext = useCallback(() => {
    if (!autoPlayStoryArcEnabled) return;
    const queue = storyArcItems.length > 0 ? storyArcItems : adaptiveQueue;
    if (!queue.length) return;
    const nextIndex = queueCursorRef.current % queue.length;
    queueCursorRef.current = queueCursorRef.current + 1;
    const next = queue[nextIndex];
    if (!next) return;
    void playItem(next, 'queue');
  }, [adaptiveQueue, autoPlayStoryArcEnabled, playItem, storyArcItems]);

  const markInboxListened = useCallback(async (item: AudioItem) => {
    if (!item?.item_id) return;
    await api.post('/podcasts/v2/daily-drop-inbox/mark-listened', { item_id: item.item_id }, { silentLoading: true });
    setBootstrap((prev: any) => {
      if (!prev?.daily_drop_inbox?.items) return prev;
      const nextItems = (prev.daily_drop_inbox.items || []).map((row: any) => (
        row?.item_id === item.item_id ? { ...row, listened: true } : row
      ));
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

  const cardWidth = '31.5%';

  if (loading) {
    return (
      <View style={{ minHeight: 380, justifyContent: 'center', alignItems: 'center' }} data-testid="podcasts-v2-loading-state">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ marginTop: 10, color: colors.textSec }}>Loading My Podcasts…</Text>
      </View>
    );
  }

  if (loadError || !bootstrap) {
    return (
      <View style={{ minHeight: 320, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 16, justifyContent: 'center', alignItems: 'center' }} data-testid="podcasts-v2-error-state">
        <Ionicons name="alert-circle-outline" size={22} color={colors.primary} />
        <Text style={{ color: colors.text, fontWeight: '800', marginTop: 8 }}>My Podcasts temporarily unavailable</Text>
        <Text style={{ color: colors.textSec, marginTop: 4, textAlign: 'center' }}>{loadError || 'Please retry. This does not affect other features.'}</Text>
        <TouchableOpacity onPress={loadBootstrap} style={{ marginTop: 10, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: `${colors.primary}18`, borderWidth: 1, borderColor: `${colors.primary}66` }} data-testid="podcasts-v2-retry-button">
          <Text style={{ color: colors.primary, fontWeight: '800' }}>Retry My Podcasts</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: 28 }} showsVerticalScrollIndicator={false} data-testid="podcasts-v2-scroll-root">
      <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} data-testid="podcasts-v2-hero">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="podcasts-v2-hero-title">My Podcasts v2</Text>
            <Text style={{ color: colors.textSec, marginTop: 4, fontSize: 12.5 }}>Auto-curated feed. Zero user files. No manual setup.</Text>
            <Text style={{ color: colors.textMuted, marginTop: 3, fontSize: 11 }}>Feature 29 • Enterprise rebuild</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12` }} data-testid="podcasts-v2-plan-pill">
              <Text style={{ color: colors.primary, fontWeight: '800', fontSize: 11.5 }}>{String(bootstrap?.quota?.plan || 'free').toUpperCase()}</Text>
            </View>
            <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft }} data-testid="podcasts-v2-scope-pill">
              <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 11.5 }}>{String(bootstrap?.quota?.scope_label || 'Limited access')}</Text>
            </View>
          </View>
        </View>
        <Text style={{ marginTop: 8, color: colors.textMuted, fontSize: 11.5 }} data-testid="podcasts-v2-daily-drop-note">Auto adds daily episodes with in-app + email nudges.</Text>
      </View>

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="podcasts-v2-player-card">
        <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <View style={{ width: 92, height: 92, borderRadius: 10, overflow: 'hidden', backgroundColor: colors.bgSoft }}>
            {selectedItem?.thumbnail_url ? (
              <Image source={{ uri: selectedItem.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="Decorative image" />
            ) : null}
          </View>
          <View style={{ flex: 1, minWidth: 220 }}>
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14.5 }} numberOfLines={1} data-testid="podcasts-v2-player-title">
              {selectedItem?.title || 'Choose an episode'}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 3 }} numberOfLines={1}>
              {(selectedItem?.host_name || selectedItem?.creator || 'Featured Host')} • {selectedItem?.series_name || 'Podcast Series'}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 2 }} numberOfLines={1}>{formatDuration(Number(selectedItem?.duration_seconds || 0))}</Text>
            {syncingPlay ? <ActivityIndicator size="small" color={colors.primary} style={{ marginTop: 8 }} /> : null}
            {(selectedItem?.audio_url || selectedItem?.stream_url) ? (
              Platform.OS === 'web' ? (
                <View style={{ marginTop: 8 }} data-testid="podcasts-v2-web-player-wrap">
                  <audio controls src={selectedItem.audio_url || selectedItem.stream_url} autoPlay onEnded={playNext} style={{ width: '100%', height: 38 }} data-testid="podcasts-v2-web-player" />
                </View>
              ) : (
                <TouchableOpacity style={{ marginTop: 8, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: `${colors.primary}15`, alignSelf: 'flex-start' }} onPress={() => Linking.openURL(selectedItem.audio_url || selectedItem.stream_url || '')} data-testid="podcasts-v2-open-stream-button">
                  <Text style={{ color: colors.primary, fontWeight: '700' }}>Open audio stream</Text>
                </TouchableOpacity>
              )
            ) : null}
          </View>
        </View>
      </View>

      {playError ? (
        <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}14`, padding: 10 }} data-testid="podcasts-v2-playback-warning">
          <Text style={{ color: colors.warningText, fontSize: 11.5, fontWeight: '700' }}>{playError}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 4 }}>{`Retries: ${playbackRetryCount}/${MAX_RETRY_ATTEMPTS}`}</Text>
        </View>
      ) : null}

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: `${colors.primary}12`, padding: 12 }} data-testid="podcasts-v2-behavioral-nudge">
        <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>Smart Momentum Nudge</Text>
        <Text style={{ color: colors.text, marginTop: 5, fontSize: 12.5, fontWeight: '600' }}>
          {bootstrap?.behavioral_ai?.reengagement_nudge || 'Your next best episode is ready.'}
        </Text>
        <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 10.8 }} data-testid="podcasts-v2-best-return-time">
          {`Best time to return: ${bootstrap?.behavioral_ai?.best_time_to_return?.label || '8:00 PM'} (${bootstrap?.behavioral_ai?.best_time_to_return?.window || 'evening'})`}
        </Text>
      </View>

      {continueItems.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="podcasts-v2-continue-listening-rail">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }}>Continue Listening</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {continueItems.map((item) => (
              <TouchableOpacity key={`continue-${item.item_id}`} onPress={() => playItem(item, 'manual')} style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9 }} data-testid={`podcasts-v2-continue-item-${item.item_id}`}>
                <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700' }} numberOfLines={2}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.category} • {item.creator}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {storyArcItems.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="podcasts-v2-story-arc-rail">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 4 }}>Podcast Story Arc</Text>
            <TouchableOpacity onPress={() => setAutoPlayStoryArcEnabled((prev) => !prev)} style={{ borderRadius: 999, borderWidth: 1, borderColor: autoPlayStoryArcEnabled ? `${colors.primary}66` : colors.border, backgroundColor: autoPlayStoryArcEnabled ? `${colors.primary}15` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="podcasts-v2-story-arc-autoplay-toggle">
              <Text style={{ color: autoPlayStoryArcEnabled ? colors.primary : colors.textSec, fontSize: 10.5, fontWeight: '800' }}>{`Auto-play next: ${autoPlayStoryArcEnabled ? 'ON' : 'OFF'}`}</Text>
            </TouchableOpacity>
          </View>
          <Text style={{ color: colors.textSec, fontSize: 11.5, marginBottom: 8 }} numberOfLines={1}>{`Continue ${bootstrap?.podcast_story_arc?.series_name || 'Series'} in sequence`}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {storyArcItems.map((item, idx) => (
              <TouchableOpacity key={`story-arc-${item.item_id}`} onPress={() => playItem(item, 'story_arc')} style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9 }} data-testid={`podcasts-v2-story-arc-item-${item.item_id}`}>
                <View style={{ alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 7, paddingVertical: 3 }}>
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{`EP ${idx + 1}`}</Text>
                </View>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', marginTop: 6 }} numberOfLines={2}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.host_name || item.creator} • {item.series_name || 'Series'}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {(bootstrap?.season_binge_rails || []).length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="podcasts-v2-season-binge-rails">
          {(bootstrap?.season_binge_rails || []).slice(0, 4).map((rail, ridx) => (
            <View key={`season-binge-${ridx}`} style={{ marginBottom: 10 }} data-testid={`podcasts-v2-season-binge-rail-${ridx}`}>
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 6 }}>{rail?.title || 'Binge Rail'}</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                {(rail?.items || []).slice(0, 8).map((item) => (
                  <TouchableOpacity key={`season-item-${item.item_id}`} onPress={() => playItem(item, 'queue')} style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9 }} data-testid={`podcasts-v2-season-binge-item-${item.item_id}`}>
                    <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700' }} numberOfLines={2}>{item.title}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.category} • {item.creator}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          ))}
        </View>
      ) : null}

      {(bootstrap?.smart_follow_up_items || []).length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="podcasts-v2-smart-follow-up-rail">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }}>Smart Follow-up Episodes</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {(bootstrap?.smart_follow_up_items || []).slice(0, 10).map((item) => (
              <TouchableOpacity key={`sf-${item.item_id}`} onPress={() => playItem(item, 'queue')} style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9 }} data-testid={`podcasts-v2-smart-follow-item-${item.item_id}`}>
                <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700' }} numberOfLines={2}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.category} • {item.creator}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {(bootstrap?.behavioral_rails || []).length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="podcasts-v2-behavioral-rails">
          {(bootstrap?.behavioral_rails || []).slice(0, 3).map((rail: any, rIdx: number) => (
            <View key={`br-pod-${rIdx}`} style={{ marginBottom: 10 }} data-testid={`podcasts-v2-behavioral-rail-${rIdx}`}>
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 6 }}>{rail?.title || 'Dynamic Rail'}</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                {(rail?.items || []).slice(0, 10).map((item: AudioItem) => (
                  <TouchableOpacity key={`br-item-pod-${item.item_id}`} onPress={() => playItem(item, 'queue')} style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9 }} data-testid={`podcasts-v2-behavioral-item-${item.item_id}`}>
                    <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700' }} numberOfLines={2}>{item.title}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.category} • {item.creator}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          ))}
        </View>
      ) : null}

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="podcasts-v2-daily-drop-inbox">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14.5 }}>Daily Drop Inbox</Text>
          <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 8, paddingVertical: 4 }}>
            <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{bootstrap?.daily_drop_inbox?.unread || 0} unread</Text>
          </View>
        </View>
        <View style={{ marginTop: 8, gap: 8 }}>
          {(bootstrap?.daily_drop_inbox?.items || []).slice(0, 6).map((item: AudioItem & { listened?: boolean }) => (
            <View key={`inbox-${item.item_id}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <View style={{ flex: 1 }}>
                <View style={{ alignSelf: 'flex-start', marginBottom: 4, borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}14`, paddingHorizontal: 7, paddingVertical: 3 }} data-testid={`podcasts-v2-inbox-type-badge-${item.item_id}`}>
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>PODCAST</Text>
                </View>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5 }}>{item.category} • {item.listened ? 'Listened' : 'New drop'}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                <TouchableOpacity onPress={() => playItem(item, 'inbox')} style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 5, backgroundColor: `${colors.primary}18` }} data-testid={`podcasts-v2-inbox-play-${item.item_id}`}>
                  <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 10.5 }}>Play</Text>
                </TouchableOpacity>
                {!item.listened ? (
                  <TouchableOpacity onPress={() => markInboxListened(item)} style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 5, borderWidth: 1, borderColor: colors.border }} data-testid={`podcasts-v2-inbox-mark-listened-${item.item_id}`}>
                    <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 10.5 }}>Mark listened</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>
          ))}
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 12 }} data-testid="podcasts-v2-categories-bar">
        {categories.map((cat) => {
          const active = selectedCategory === cat;
          return (
            <TouchableOpacity key={cat} onPress={() => setSelectedCategory(cat)} style={{ borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, borderColor: active ? `${colors.primary}66` : colors.border, backgroundColor: active ? `${colors.primary}12` : colors.bgSoft }} data-testid={`podcasts-v2-category-${String(cat).toLowerCase().replace(/\s+/g, '-')}`}>
              <Text style={{ color: active ? colors.primary : colors.textSec, fontWeight: active ? '800' : '600', fontSize: 11.5 }}>{cat === 'all' ? 'All Categories' : cat}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 10, alignItems: 'stretch' }} data-testid="podcasts-v2-catalog-grid">
        {visibleItems.map((item) => {
          const locked = isLocked(item);
          return (
            <TouchableOpacity key={item.item_id} onPress={() => playItem(item, 'manual')} style={{ width: cardWidth as any, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }} data-testid={`podcasts-v2-catalog-item-${item.item_id}`}>
              <View style={{ width: '100%', aspectRatio: '1 / 1', backgroundColor: colors.bgSoft }}>
                <Image source={{ uri: item.thumbnail_url || 'https://picsum.photos/seed/podcast-v2/640/640' }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="podcast cover" />
                <View style={{ position: 'absolute', top: 8, right: 8, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: 'rgba(0,0,0,0.55)', flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  {locked ? <Ionicons name="lock-closed-outline" size={10} color="var(--app-primary-text)" /> : <Ionicons name="play" size={10} color="var(--app-primary-text)" />}
                  <Text style={{ color: 'var(--app-primary-text)', fontSize: 10.5, fontWeight: '700' }}>{String(item.min_plan || 'free').toUpperCase()}</Text>
                </View>
              </View>
              <View style={{ padding: 10 }}>
                <View style={{ alignSelf: 'flex-start', marginBottom: 4, borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}14`, paddingHorizontal: 7, paddingVertical: 3 }} data-testid={`podcasts-v2-catalog-item-type-badge-${item.item_id}`}>
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>PODCAST</Text>
                </View>
                <Text numberOfLines={2} style={{ color: colors.text, fontWeight: '700', fontSize: 12.5 }}>{item.title}</Text>
                <Text numberOfLines={1} style={{ marginTop: 4, color: colors.textSec, fontSize: 11.5 }}>{item.category} • {item.creator}</Text>
                <Text numberOfLines={1} style={{ marginTop: 2, color: colors.textMuted, fontSize: 10.5 }}>{item.host_name || item.creator} • {item.series_name || 'Podcast Show'}</Text>
                <Text style={{ marginTop: 2, color: colors.textMuted, fontSize: 10.5 }}>{formatDuration(item.duration_seconds)}</Text>
                {locked ? (
                  <TouchableOpacity onPress={openUpgrade} style={{ marginTop: 6, alignSelf: 'flex-start', borderRadius: 999, paddingHorizontal: 8, paddingVertical: 5, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}25` }} data-testid={`podcasts-v2-upgrade-cta-${item.item_id}`}>
                    <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '800' }}>Upgrade to unlock</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </TouchableOpacity>
          );
        })}
      </View>
    </ScrollView>
  );
};

export default PodcastsFeature29;
