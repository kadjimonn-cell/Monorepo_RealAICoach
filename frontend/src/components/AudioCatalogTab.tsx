import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Linking, Modal, Platform, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useTranslation } from '../hooks/useTranslation';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

type Mode = 'audio_studio' | 'podcasts' | 'sports';

type AudioItem = {
  item_id: string;
  title: string;
  description: string;
  category: string;
  creator: string;
  content_kind?: 'music' | 'podcast' | string;
  series_name?: string;
  host_name?: string;
  artist_name?: string;
  album_name?: string;
  audio_url: string;
  thumbnail_url: string;
  duration_seconds: number;
  min_plan: 'free' | 'basic' | 'premium' | string;
  source_label?: string;
  league?: string;
  event_stage?: string;
  playback_type?: 'audio' | 'video' | 'youtube' | string;
  stream_url?: string;
  youtube_embed_url?: string;
  is_live?: boolean;
  kickoff_at?: string;
  stream_protection?: string;
  stream_token_ttl_seconds?: number;
  blackout_blocked?: boolean;
  blackout_reason?: string;
  blackout_rule_id?: string;
  is_embeddable_playable?: boolean;
  embeddability_score?: number;
  embeddability_reason?: string;
  embeddability_checked_at?: string;
  fallback_applied?: boolean;
  fallback_from_league?: string;
  official_watch_url?: string;
  is_watchable_now?: boolean;
  watch_now_mode?: 'in_app_embed' | 'external_link' | 'none' | string;
};

const MODE_CONFIG: Record<Mode, { endpoint: string; playEndpoint: string; title: string; subtitle: string; accent: string }> = {
  audio_studio: {
    endpoint: '/audio-studio/v2/bootstrap',
    playEndpoint: '/audio-studio/v2/play',
    title: 'Audio Studio',
    subtitle: 'Premium music thumbnails, personalized rails, and instant playback.',
    accent: 'var(--app-primary)',
  },
  podcasts: {
    endpoint: '/podcasts/v2/bootstrap',
    playEndpoint: '/podcasts/v2/play',
    title: 'My Podcasts',
    subtitle: 'Editorial podcast drops with binge-ready episode thumbnails.',
    accent: 'var(--app-primary)',
  },
  sports: {
    endpoint: '/sports/v2/bootstrap',
    playEndpoint: '/sports/v2/play',
    title: 'Sports',
    subtitle: 'LIVE sports rails, league hubs, weekly drops, and enterprise-grade stream control.',
    accent: 'var(--app-warning)',
  },
};

const PLAN_LEVELS: Record<string, number> = { free: 0, basic: 1, premium: 2 };

const formatDuration = (seconds: number) => {
  const mins = Math.max(1, Math.round(Number(seconds || 0) / 60));
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${m}m`;
};

export default function AudioCatalogTab({ mode }: { mode: Mode }) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const cfg = MODE_CONFIG[mode];
  const timezone = useMemo(() => {
    try {
      if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AudioCatalogTab.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    return 'UTC';
  }, []);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [bootstrap, setBootstrap] = useState<any>(null);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedItem, setSelectedItem] = useState<AudioItem | null>(null);
  const [autoPlayStoryArcEnabled, setAutoPlayStoryArcEnabled] = useState(true);
  const [followedArtists, setFollowedArtists] = useState<string[]>([]);
  const [followedLeagues, setFollowedLeagues] = useState<string[]>([]);
  const [leagueReminderMap, setLeagueReminderMap] = useState<Record<string, { pre_kickoff_15_enabled: boolean }>>({});
  const [lockedReasonById, setLockedReasonById] = useState<Record<string, string>>({});
  const [syncingPlay, setSyncingPlay] = useState(false);
  const [countdownTick, setCountdownTick] = useState(Date.now());
  const [sportsPlayableOnly, setSportsPlayableOnly] = useState(false);
  const [watchInstantlyReady, setWatchInstantlyReady] = useState(false);
  const [externalConfirmVisible, setExternalConfirmVisible] = useState(false);
  const [externalTargetUrl, setExternalTargetUrl] = useState('');
  const [rememberExternalConfirmSession, setRememberExternalConfirmSession] = useState(false);

  const lockTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const deepLinkHandledRef = useRef(false);

  const plan = String(bootstrap?.quota?.plan || 'free').toLowerCase();

  const getAuthHeaders = useCallback(() => ({} as Record<string, string>), []);

  const loadBootstrap = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    let lastError = '';
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const endpointWithTimezone = `${cfg.endpoint}?tz=${encodeURIComponent(timezone)}`;
        const res = await api.get(endpointWithTimezone, { silentLoading: true, skipDedupe: true, headers: getAuthHeaders() });
        const data = res?.data || null;
        const expectedFeatureId = mode === 'audio_studio'
          ? 'watch-videos-audio-studio'
          : mode === 'podcasts'
            ? 'watch-videos-my-podcasts'
            : 'watch-videos-sports';
        if (data?.feature_id && data.feature_id !== expectedFeatureId) {
          throw new Error(`Mismatched dataset (${data.feature_id})`);
        }
        setBootstrap(data);
        setFollowedArtists((data?.followed_artists || []).map((x: any) => String(x || '')));
        setFollowedLeagues((data?.followed_leagues || []).map((x: any) => String(x || '')));
        const settingsRows = (data?.league_reminder_settings || []) as Array<{ league_name?: string; pre_kickoff_15_enabled?: boolean }>;
        const mapped = settingsRows.reduce((acc, row) => {
          const league = String(row?.league_name || '').trim().toLowerCase();
          if (!league) return acc;
          acc[league] = { pre_kickoff_15_enabled: Boolean(row?.pre_kickoff_15_enabled) };
          return acc;
        }, {} as Record<string, { pre_kickoff_15_enabled: boolean }>);
        setLeagueReminderMap(mapped);
        setSelectedItem(data?.featured_item || (data?.catalog || [])[0] || null);
        setLoading(false);
        return;
      } catch (error: any) {
        lastError = String(error?.response?.data?.detail || error?.message || 'Unable to load right now.');
        if (attempt === 0) {
          await new Promise((resolve) => setTimeout(resolve, 450));
          continue;
        }
      }
    }
    setBootstrap(null);
    setSelectedItem(null);
    setLoadError(lastError || 'Unable to load this catalog.');
    setLoading(false);
  }, [cfg.endpoint, getAuthHeaders, mode, timezone]);

  useEffect(() => {
    loadBootstrap();
    return () => {
      Object.values(lockTimersRef.current).forEach((id) => clearTimeout(id));
    };
  }, [loadBootstrap]);

  useEffect(() => {
    if (mode !== 'sports') return;
    const id = setInterval(() => setCountdownTick(Date.now()), 30_000);
    return () => clearInterval(id);
  }, [mode]);

  const categories = useMemo(() => ['all', ...(bootstrap?.categories || [])], [bootstrap?.categories]);
  const primaryMeta = mode === 'audio_studio'
    ? 'Music discovery'
    : mode === 'podcasts'
      ? 'Podcast episodes'
      : 'Live + scheduled sports events';
  const contentTypeBadge = mode === 'audio_studio' ? 'MUSIC' : mode === 'podcasts' ? 'PODCAST' : 'SPORTS';
  const deepLinkItemId = useMemo(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return '';
    const value = new URLSearchParams(window.location.search).get('playItem') || '';
    return String(value).trim();
  }, [mode]);

  const isEmbeddablePlayable = useCallback((item: AudioItem) => {
    if (mode !== 'sports') return true;
    return Boolean(item?.is_embeddable_playable);
  }, [mode]);

  const isWatchableNow = useCallback((item: AudioItem) => {
    if (mode !== 'sports') return true;
    return Boolean(item?.is_watchable_now || item?.is_embeddable_playable || (item?.official_watch_url && String(item.official_watch_url).startsWith('https://')));
  }, [mode]);

  const visibleItems = useMemo(() => {
    const items = (bootstrap?.catalog || []) as AudioItem[];
    const categoryFiltered = selectedCategory === 'all'
      ? items
      : items.filter((item) => String(item.category || '').toLowerCase() === String(selectedCategory || '').toLowerCase());

    if (mode !== 'sports') return categoryFiltered;

    const ranked = [...categoryFiltered].sort((a, b) => {
      const aWatchable = isWatchableNow(a) ? 1 : 0;
      const bWatchable = isWatchableNow(b) ? 1 : 0;
      if (aWatchable !== bWatchable) return bWatchable - aWatchable;
      const aEmbeddable = a?.is_embeddable_playable ? 1 : 0;
      const bEmbeddable = b?.is_embeddable_playable ? 1 : 0;
      if (aEmbeddable !== bEmbeddable) return bEmbeddable - aEmbeddable;
      const aScore = Number(a?.embeddability_score || 0);
      const bScore = Number(b?.embeddability_score || 0);
      if (aScore !== bScore) return bScore - aScore;
      return String(b?.released_at || '').localeCompare(String(a?.released_at || ''));
    });
    return sportsPlayableOnly ? ranked.filter((item) => isWatchableNow(item)) : ranked;
  }, [bootstrap?.catalog, isWatchableNow, mode, selectedCategory, sportsPlayableOnly]);

  const topPlayableSportsItem = useMemo(() => {
    if (mode !== 'sports') return null;
    const all = (bootstrap?.catalog || []) as AudioItem[];
    return all.find((item) => isWatchableNow(item) && !Boolean(item?.blackout_blocked)) || null;
  }, [bootstrap?.catalog, isWatchableNow, mode]);

  const podcastStoryArc = useMemo(() => {
    if (mode !== 'podcasts') return { seriesName: '', items: [] as AudioItem[] };
    const allItems = (bootstrap?.catalog || []) as AudioItem[];
    const bySeries: Record<string, AudioItem[]> = {};
    for (const item of allItems) {
      const series = String(item?.series_name || '').trim();
      if (!series) continue;
      if (!bySeries[series]) bySeries[series] = [];
      bySeries[series].push(item);
    }
    const entries = Object.entries(bySeries)
      .map(([series, items]) => ({ series, items }))
      .filter((entry) => entry.items.length >= 3)
      .sort((a, b) => b.items.length - a.items.length);
    if (!entries.length) return { seriesName: '', items: [] as AudioItem[] };

    const selected = entries[0];
    const ordered = [...selected.items].sort((a, b) => String(a.item_id || '').localeCompare(String(b.item_id || '')));
    return {
      seriesName: selected.series,
      items: ordered.slice(0, 8),
    };
  }, [bootstrap?.catalog, mode]);

  const artistSpotlights = useMemo(() => {
    if (mode !== 'audio_studio') return [] as Array<{ artist: string; album: string; items: AudioItem[] }>;
    const allItems = (bootstrap?.catalog || []) as AudioItem[];
    const byArtist: Record<string, AudioItem[]> = {};
    for (const item of allItems) {
      const artist = String(item?.artist_name || item?.creator || '').trim();
      if (!artist) continue;
      if (!byArtist[artist]) byArtist[artist] = [];
      byArtist[artist].push(item);
    }
    return Object.entries(byArtist)
      .map(([artist, items]) => {
        const ordered = [...items].sort((a, b) => String(a.item_id || '').localeCompare(String(b.item_id || '')));
        return {
          artist,
          album: String(ordered[0]?.album_name || 'Featured Album'),
          items: ordered.slice(0, 4),
        };
      })
      .sort((a, b) => b.items.length - a.items.length)
      .slice(0, 12);
  }, [bootstrap?.catalog, mode]);

  const sportsLeagueRails = useMemo(() => {
    if (mode !== 'sports') return [] as Array<{ league: string; items: AudioItem[] }>;
    const allItems = (bootstrap?.catalog || []) as AudioItem[];
    const byLeague: Record<string, AudioItem[]> = {};
    for (const item of allItems) {
      const league = String(item?.league || item?.category || 'Sports').trim();
      if (!byLeague[league]) byLeague[league] = [];
      byLeague[league].push(item);
    }
    return Object.entries(byLeague)
      .map(([league, items]) => ({ league, items: items.slice(0, 14) }))
      .sort((a, b) => b.items.length - a.items.length)
      .slice(0, 5);
  }, [bootstrap?.catalog, mode]);

  const sportsLiveRail = useMemo(() => {
    if (mode !== 'sports') return [] as AudioItem[];
    const source = (bootstrap?.catalog || []) as AudioItem[];
    return source
      .filter((item) => item?.is_live)
      .filter((item) => isWatchableNow(item))
      .filter((item) => !Boolean(item?.blackout_blocked))
      .slice(0, 16);
  }, [bootstrap?.catalog, isWatchableNow, mode]);

  const sportsReplayRail = useMemo(() => {
    if (mode !== 'sports') return [] as AudioItem[];
    const source = (bootstrap?.catalog || []) as AudioItem[];
    return source
      .filter((item) => !item?.is_live)
      .filter((item) => isWatchableNow(item))
      .filter((item) => !Boolean(item?.blackout_blocked))
      .slice(0, 18);
  }, [bootstrap?.catalog, isWatchableNow, mode]);

  const formatCountdownLabel = useCallback((kickoffAt?: string, isLive?: boolean) => {
    if (isLive) return 'LIVE NOW';
    if (!kickoffAt) return 'Starts soon';
    const kickoffMs = new Date(kickoffAt).getTime();
    if (!Number.isFinite(kickoffMs)) return 'Starts soon';
    const delta = kickoffMs - countdownTick;
    if (delta <= 0) return 'Starting now';
    const totalMinutes = Math.ceil(delta / 60000);
    const days = Math.floor(totalMinutes / (60 * 24));
    const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
    const mins = totalMinutes % 60;
    if (days > 0) return `${days}d ${hours}h to kickoff`;
    if (hours > 0) return `${hours}h ${mins}m to kickoff`;
    return `${Math.max(1, mins)}m to kickoff`;
  }, [countdownTick]);

  const isLeagueFollowed = useCallback((leagueName: string) => {
    const key = String(leagueName || '').trim().toLowerCase();
    return followedLeagues.some((league) => String(league || '').trim().toLowerCase() === key);
  }, [followedLeagues]);

  const toggleLeagueReminder = useCallback(async (leagueName: string) => {
    const cleanLeague = String(leagueName || '').trim();
    if (!cleanLeague || mode !== 'sports') return;
    const currentlyFollowed = isLeagueFollowed(cleanLeague);
    const endpoint = currentlyFollowed ? '/sports/v2/unfollow-league' : '/sports/v2/follow-league';
    await api.post(endpoint, { league_name: cleanLeague }, { silentLoading: true, headers: getAuthHeaders() });
    setFollowedLeagues((prev) => {
      const key = cleanLeague.toLowerCase();
      if (currentlyFollowed) {
        setLeagueReminderMap((prevMap) => {
          const next = { ...prevMap };
          delete next[key];
          return next;
        });
        return prev.filter((league) => String(league || '').trim().toLowerCase() !== key);
      }
      setLeagueReminderMap((prevMap) => ({ ...prevMap, [key]: { pre_kickoff_15_enabled: prevMap[key]?.pre_kickoff_15_enabled ?? false } }));
      return [cleanLeague, ...prev.filter((league) => String(league || '').trim().toLowerCase() !== key)].slice(0, 30);
    });
  }, [getAuthHeaders, isLeagueFollowed, mode]);

  const isPreKickoffEnabled = useCallback((leagueName: string) => {
    const key = String(leagueName || '').trim().toLowerCase();
    return Boolean(leagueReminderMap[key]?.pre_kickoff_15_enabled);
  }, [leagueReminderMap]);

  const togglePreKickoffReminder = useCallback(async (leagueName: string) => {
    const cleanLeague = String(leagueName || '').trim();
    if (!cleanLeague || mode !== 'sports') return;
    const key = cleanLeague.toLowerCase();
    const nextState = !isPreKickoffEnabled(cleanLeague);

    if (!isLeagueFollowed(cleanLeague)) {
      await api.post('/sports/v2/follow-league', { league_name: cleanLeague }, { silentLoading: true, headers: getAuthHeaders() });
      setFollowedLeagues((prev) => [cleanLeague, ...prev.filter((league) => String(league || '').trim().toLowerCase() !== key)].slice(0, 30));
    }

    await api.post(
      '/sports/v2/reminder-settings',
      { league_name: cleanLeague, pre_kickoff_15_enabled: nextState },
      { silentLoading: true, headers: getAuthHeaders() },
    );
    setLeagueReminderMap((prev) => ({ ...prev, [key]: { pre_kickoff_15_enabled: nextState } }));
  }, [getAuthHeaders, isLeagueFollowed, isPreKickoffEnabled, mode]);

  const isLocked = useCallback((item: AudioItem) => {
    const need = PLAN_LEVELS[String(item?.min_plan || 'free').toLowerCase()] ?? 0;
    const has = PLAN_LEVELS[plan] ?? 0;
    return need > has;
  }, [plan]);

  const isRegionBlocked = useCallback((item: AudioItem) => {
    return Boolean(item?.blackout_blocked);
  }, []);

  const showLockReason = useCallback((item: AudioItem) => {
    const reason = isRegionBlocked(item)
      ? (item.blackout_reason || 'Regional blackout: this event is unavailable in your current location.')
      : `Locked: Requires ${String(item.min_plan || 'premium').toUpperCase()} plan to play.`;
    const itemId = item.item_id;
    setLockedReasonById((prev) => ({ ...prev, [itemId]: reason }));
    if (lockTimersRef.current[itemId]) clearTimeout(lockTimersRef.current[itemId]);
    lockTimersRef.current[itemId] = setTimeout(() => {
      setLockedReasonById((prev) => {
        const next = { ...prev };
        delete next[itemId];
        return next;
      });
      delete lockTimersRef.current[itemId];
    }, 3200);
  }, [isRegionBlocked]);

  const openUpgrade = useCallback(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.location.assign('/subscription/plans');
      return;
    }
    void Linking.openURL('/subscription/plans');
  }, []);

  const playItem = useCallback(async (item: AudioItem) => {
    if (!item?.item_id) return;
    if (isRegionBlocked(item)) {
      showLockReason(item);
      return;
    }
    if (mode === 'sports' && !isEmbeddablePlayable(item) && String(item?.official_watch_url || '').startsWith('https://')) {
      const targetUrl = String(item.official_watch_url || '');
      const key = 'sports-external-open-confirm-skip-v1';
      const skipConfirm = Platform.OS === 'web' && typeof window !== 'undefined' && window.sessionStorage.getItem(key) === '1';
      if (skipConfirm) {
        await Linking.openURL(targetUrl);
        return;
      }
      setExternalTargetUrl(targetUrl);
      setExternalConfirmVisible(true);
      return;
    }
    if (mode === 'sports' && !isWatchableNow(item)) {
      const itemId = item.item_id;
      const reason = item?.embeddability_reason || 'This stream is currently unavailable. Auto-fallback is being applied to playable official sources.';
      setLockedReasonById((prev) => ({ ...prev, [itemId]: reason }));
      return;
    }
    if (isLocked(item)) {
      showLockReason(item);
      return;
    }

    setSelectedItem(item);
    setSyncingPlay(true);
    try {
      const response = await api.post(
        cfg.playEndpoint,
        { item_id: item.item_id, listen_seconds: 0, completed: false, source: 'catalog_tap' },
        { silentLoading: true, headers: getAuthHeaders() },
      );
      const serverItem = response?.data?.item as AudioItem | undefined;
      if (serverItem?.item_id === item.item_id) {
        setSelectedItem({ ...item, ...serverItem });
      }
    } catch (error: any) {
      const apiMessage = String(error?.response?.data?.detail || '').trim();
      if (apiMessage) {
        const itemId = item.item_id;
        setLockedReasonById((prev) => ({ ...prev, [itemId]: apiMessage }));
      }
    } finally {
      setSyncingPlay(false);
    }
  }, [cfg.playEndpoint, getAuthHeaders, isEmbeddablePlayable, isLocked, isRegionBlocked, isWatchableNow, mode, showLockReason]);

  const confirmExternalOpen = useCallback(async () => {
    const key = 'sports-external-open-confirm-skip-v1';
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

  const playWatchInstantly = useCallback(async () => {
    if (!topPlayableSportsItem) return;
    await playItem(topPlayableSportsItem);
  }, [playItem, topPlayableSportsItem]);

  useEffect(() => {
    if (mode !== 'sports') return;
    if (!topPlayableSportsItem) return;
    if (!watchInstantlyReady) {
      setWatchInstantlyReady(true);
      return;
    }

    const key = 'sports-watch-instantly-opened-v1';
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const opened = window.sessionStorage.getItem(key) === '1';
      if (opened) return;
      window.sessionStorage.setItem(key, '1');
      void playWatchInstantly();
      return;
    }

    void playWatchInstantly();
  }, [mode, playWatchInstantly, topPlayableSportsItem, watchInstantlyReady]);

  const playNextStoryArcItem = useCallback(() => {
    if (mode !== 'podcasts' || !autoPlayStoryArcEnabled || !selectedItem?.item_id) return;
    const items = podcastStoryArc.items || [];
    const currentIndex = items.findIndex((row) => row.item_id === selectedItem.item_id);
    if (currentIndex < 0) return;
    const next = items[currentIndex + 1];
    if (!next) return;
    void playItem(next);
  }, [autoPlayStoryArcEnabled, mode, playItem, podcastStoryArc.items, selectedItem?.item_id]);

  useEffect(() => {
    if (!deepLinkItemId || !bootstrap?.catalog || deepLinkHandledRef.current) return;
    const target = (bootstrap.catalog as AudioItem[]).find((item) => String(item.item_id || '') === deepLinkItemId);
    if (!target) return;
    deepLinkHandledRef.current = true;
    void playItem(target);
  }, [bootstrap?.catalog, deepLinkItemId, playItem]);

  const isArtistFollowed = useCallback((artistName: string) => {
    const key = String(artistName || '').trim().toLowerCase();
    return followedArtists.some((artist) => String(artist || '').trim().toLowerCase() === key);
  }, [followedArtists]);

  const toggleFollowArtist = useCallback(async (artistName: string) => {
    const cleanArtist = String(artistName || '').trim();
    if (!cleanArtist || mode !== 'audio_studio') return;
    const currentlyFollowed = isArtistFollowed(cleanArtist);
    const endpoint = currentlyFollowed ? '/audio-studio/v2/unfollow-artist' : '/audio-studio/v2/follow-artist';
    await api.post(endpoint, { artist_name: cleanArtist }, { silentLoading: true, headers: getAuthHeaders() });
    setFollowedArtists((prev) => {
      const lower = cleanArtist.toLowerCase();
      if (currentlyFollowed) {
        return prev.filter((name) => String(name || '').trim().toLowerCase() !== lower);
      }
      return [cleanArtist, ...prev.filter((name) => String(name || '').trim().toLowerCase() !== lower)].slice(0, 100);
    });
    setBootstrap((prev: any) => {
      if (!prev) return prev;
      const allCatalog = (prev.catalog || []) as AudioItem[];
      const nextFollowed = currentlyFollowed
        ? followedArtists.filter((name) => String(name || '').trim().toLowerCase() !== cleanArtist.toLowerCase())
        : [cleanArtist, ...followedArtists];
      const followedSet = new Set(nextFollowed.map((name) => String(name || '').trim().toLowerCase()));
      const releases = allCatalog.filter((item) => followedSet.has(String(item.artist_name || item.creator || '').trim().toLowerCase())).slice(0, 24);
      return {
        ...prev,
        followed_artists: nextFollowed,
        followed_artist_new_releases: releases,
      };
    });
  }, [followedArtists, getAuthHeaders, isArtistFollowed, mode]);

  const markInboxListened = useCallback(async (item: AudioItem) => {
    if (!item?.item_id) return;
    const endpoint = mode === 'audio_studio'
      ? '/audio-studio/v2/daily-drop-inbox/mark-listened'
      : mode === 'podcasts'
        ? '/podcasts/v2/daily-drop-inbox/mark-listened'
        : '/sports/v2/daily-drop-inbox/mark-listened';
    await api.post(endpoint, { item_id: item.item_id }, { silentLoading: true, headers: getAuthHeaders() });
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
  }, [getAuthHeaders, mode]);

  const cardWidth = width >= 1400 ? '18.9%' : width >= 1100 ? '23.5%' : width >= 800 ? '31.5%' : '48.4%';
  const watchableNowCount = Number(
    bootstrap?.sports_playability_summary?.watchable_count
    || (Array.isArray(bootstrap?.catalog) ? bootstrap.catalog : []).filter((item) => isWatchableNow(item)).length,
  );
  const audioTabPlayerTestId = `audio-tab-player-${mode}`;
  const sourceHealth = mode === 'audio_studio' ? (bootstrap?.source_health || null) : null;
  const sourceHealthStatus = String(sourceHealth?.status || '').toUpperCase();
  const sourceHealthReason = String(sourceHealth?.reason_code || '').trim();
  const sourceHealthLabel = sourceHealthStatus || 'UNKNOWN';
  const sourceHealthTone = sourceHealthStatus === 'HEALTHY'
    ? colors.successText
    : sourceHealthStatus === 'DEGRADED'
      ? colors.warningText
      : sourceHealthStatus === 'UNAVAILABLE'
        ? colors.errorText
        : colors.textSec;
  const sourceHealthBg = sourceHealthStatus === 'HEALTHY'
    ? `${colors.successText}14`
    : sourceHealthStatus === 'DEGRADED'
      ? `${colors.warningText}14`
      : sourceHealthStatus === 'UNAVAILABLE'
        ? `${colors.errorText}12`
        : colors.bgSoft;
  const sourceHealthBorder = sourceHealthStatus === 'HEALTHY'
    ? `${colors.successText}66`
    : sourceHealthStatus === 'DEGRADED'
      ? `${colors.warningText}66`
      : sourceHealthStatus === 'UNAVAILABLE'
        ? `${colors.errorText}66`
        : colors.border;

  if (loading) {
    return (
      <View style={{ minHeight: 380, justifyContent: 'center', alignItems: 'center' }} data-testid={`audio-tab-loading-${mode}`}>
        <ActivityIndicator size="large" color={cfg.accent} />
        <Text style={{ marginTop: 10, color: colors.textSec }}>Loading {cfg.title}…</Text>
      </View>
    );
  }

  if (loadError || !bootstrap) {
    return (
      <View style={{ minHeight: 320, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 16, justifyContent: 'center', alignItems: 'center' }} data-testid={`audio-tab-error-${mode}`}>
        <Ionicons name="alert-circle-outline" size={22} color={cfg.accent} />
        <Text style={{ color: colors.text, fontWeight: '800', marginTop: 8 }}>{cfg.title} temporarily unavailable</Text>
        <Text style={{ color: colors.textSec, marginTop: 4, textAlign: 'center' }}>{loadError || 'Please retry. This does not affect the other tab catalog.'}</Text>
        <TouchableOpacity onPress={loadBootstrap} style={{ marginTop: 10, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: `${cfg.accent}18`, borderWidth: 1, borderColor: `${cfg.accent}66` }} data-testid={`audio-tab-retry-${mode}`}>
          <Text style={{ color: cfg.accent, fontWeight: '800' }}>Retry {cfg.title}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: 28 }} showsVerticalScrollIndicator={false} data-testid={`audio-tab-scroll-${mode}`}>
      <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} data-testid={`audio-tab-hero-${mode}`}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <View>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid={`audio-tab-title-${mode}`}>{cfg.title}</Text>
            <Text style={{ color: colors.textSec, marginTop: 4, fontSize: 12.5 }}>{cfg.subtitle}</Text>
            <Text style={{ color: colors.textMuted, marginTop: 3, fontSize: 11 }}>{primaryMeta}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}12` }} data-testid={`audio-tab-plan-pill-${mode}`}>
              <Text style={{ color: cfg.accent, fontWeight: '800', fontSize: 11.5 }}>{String(bootstrap?.quota?.plan || 'free').toUpperCase()}</Text>
            </View>
            <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft }} data-testid={`audio-tab-scope-pill-${mode}`}>
              <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 11.5 }}>{String(bootstrap?.quota?.scope_label || '').trim() || 'Limited access'}</Text>
            </View>
            <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft }}>
              <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 11.5 }}>{bootstrap?.total_visible || 0} unlocked</Text>
            </View>
          </View>
        </View>
        <Text style={{ marginTop: 8, color: colors.textMuted, fontSize: 11.5 }} data-testid={`audio-tab-daily-drop-note-${mode}`}>
          {mode === 'sports'
            ? 'Auto adds weekly sports events with in-app + email notifications.'
            : 'Auto adds 6+ new releases daily with in-app + email notifications.'}
        </Text>
        <Text style={{ marginTop: 4, color: colors.textSec, fontSize: 11.5, fontWeight: '700' }} data-testid={`audio-tab-scope-label-${mode}`}>
          {`Access scope: ${String(bootstrap?.quota?.scope_label || 'Limited access')}`}
        </Text>
        {mode === 'audio_studio' ? (
          <View
            style={{ marginTop: 8, borderRadius: 10, borderWidth: 1, borderColor: sourceHealthBorder, backgroundColor: sourceHealthBg, paddingHorizontal: 10, paddingVertical: 8 }}
            data-testid="audio-studio-source-health-banner"
            testID="audio-studio-source-health-banner"
          >
            <Text style={{ color: sourceHealthTone, fontSize: 11, fontWeight: '800' }} data-testid="audio-studio-source-health-status" testID="audio-studio-source-health-status">
              {`Source health: ${sourceHealthLabel}`}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 3 }} data-testid="audio-studio-source-health-reason" testID="audio-studio-source-health-reason">
              {sourceHealthReason || 'Source health reason unavailable'}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 3 }} data-testid="audio-studio-source-health-metrics" testID="audio-studio-source-health-metrics">
              {`Playable ${Number(sourceHealth?.playable_items || 0)}/${Number(sourceHealth?.total_items || 0)} · HTTPS ${(Number(sourceHealth?.secure_https_ratio || 0) * 100).toFixed(0)}%`}
            </Text>
          </View>
        ) : null}
        {mode === 'sports' ? (
          <View style={{ marginTop: 6, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <Text style={{ color: colors.textSec, fontSize: 11.5, fontWeight: '700' }} data-testid="sports-hero-countdown" testID="sports-hero-countdown">
              {`Next kickoff: ${formatCountdownLabel(selectedItem?.kickoff_at, selectedItem?.is_live)}`}
            </Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <TouchableOpacity
                onPress={playWatchInstantly}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: `${colors.successText}16`, paddingHorizontal: 10, paddingVertical: 6 }}
                data-testid="sports-watch-instantly-button"
                testID="sports-watch-instantly-button"
              >
                <Text style={{ color: colors.successText, fontSize: 10.5, fontWeight: '800' }}>Watch Instantly</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => setSportsPlayableOnly((prev) => !prev)}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: sportsPlayableOnly ? `${cfg.accent}14` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }}
                data-testid="sports-only-playable-toggle"
                testID="sports-only-playable-toggle"
              >
                <Text style={{ color: sportsPlayableOnly ? cfg.accent : colors.textSec, fontSize: 10.5, fontWeight: '800' }}>
                  {sportsPlayableOnly ? 'Only playable now: ON' : 'Only playable now'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : null}
        {mode === 'sports' ? (
          <Text style={{ marginTop: 4, color: colors.textMuted, fontSize: 10.5 }} data-testid="sports-playable-count" testID="sports-playable-count">
            {`Watchable now: ${watchableNowCount} / ${bootstrap?.total_visible || 0}`}
          </Text>
        ) : null}
      </View>

      <View
        style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }}
        data-testid="audio-tab-player"
        testID={audioTabPlayerTestId}
      >
        <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <View style={{ width: 92, height: 92, borderRadius: 10, overflow: 'hidden', backgroundColor: colors.bgSoft }}>
            {selectedItem?.thumbnail_url ? (
              <Image accessibilityLabel="Decorative image"
                source={{ uri: selectedItem.thumbnail_url }}
                style={{ width: '100%', height: '100%' }}
                resizeMode="cover"
                accessibilityLabel="Decorative image"
              />
            ) : null}
          </View>
          <View style={{ flex: 1, minWidth: 220 }}>
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14.5 }} numberOfLines={1} data-testid={`audio-tab-player-title-${mode}`}>
              {selectedItem?.title || `Choose something in ${cfg.title}`}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 3 }} numberOfLines={1}>
              {mode === 'audio_studio'
                ? `${(selectedItem?.artist_name || selectedItem?.creator || 'Curated Artist')} • ${selectedItem?.album_name || 'Studio Album'}`
                : mode === 'podcasts'
                  ? `${(selectedItem?.host_name || selectedItem?.creator || 'Featured Host')} • ${selectedItem?.series_name || 'Podcast Series'}`
                  : `${selectedItem?.league || selectedItem?.category || 'Sports'} • ${selectedItem?.event_stage || 'Live Event'}`}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 2 }} numberOfLines={1}>
              {formatDuration(Number(selectedItem?.duration_seconds || 0))}
            </Text>
            {syncingPlay ? <ActivityIndicator size="small" color={cfg.accent} style={{ marginTop: 8 }} /> : null}
            {(selectedItem?.stream_url || selectedItem?.audio_url || selectedItem?.youtube_embed_url) ? (
              Platform.OS === 'web' ? (
                <View style={{ marginTop: 8 }} data-testid={`audio-tab-web-player-${mode}`}>
                  {mode === 'sports' && selectedItem?.playback_type === 'youtube' && selectedItem?.youtube_embed_url ? (
                    <iframe
                      src={selectedItem.youtube_embed_url}
                      title={selectedItem.title || 'Sports stream'}
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                      allowFullScreen
                      style={{ width: '100%', minHeight: 280, border: 'none', borderRadius: 10 }}
                      data-testid={`audio-tab-web-player-native-${mode}`}
                    />
                  ) : mode === 'sports' ? (
                    <video
                      controls
                      src={selectedItem.stream_url || selectedItem.audio_url}
                      autoPlay
                      style={{ width: '100%', maxHeight: 300, borderRadius: 10 }}
                      data-testid={`audio-tab-web-player-native-${mode}`}
                    />
                  ) : (
                    <audio
                      controls
                      src={selectedItem.audio_url}
                      autoPlay
                      onEnded={playNextStoryArcItem}
                      style={{ width: '100%', height: 38 }}
                      data-testid={`audio-tab-web-player-native-${mode}`}
                    />
                  )}
                </View>
              ) : (
                <TouchableOpacity style={{ marginTop: 8, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: `${cfg.accent}15`, alignSelf: 'flex-start' }} accessibilityLabel="Linking in audio catalog tab" onPress={() => Linking.openURL(selectedItem.stream_url || selectedItem.audio_url || selectedItem.youtube_embed_url || '')}>
                  <Text style={{ color: cfg.accent, fontWeight: '700' }}>{mode === 'sports' ? 'Open video stream' : 'Open audio stream'}</Text>
                </TouchableOpacity>
              )
            ) : null}
          </View>
        </View>
      </View>

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: `${cfg.accent}55`, backgroundColor: `${cfg.accent}12`, padding: 12 }} data-testid={`audio-tab-ai-nudge-${mode}`} testID={`audio-tab-ai-nudge-${mode}`}>
        <Text style={{ color: cfg.accent, fontSize: 11, fontWeight: '800' }}>GPT-5.2 Smart Nudge</Text>
        <Text style={{ color: colors.text, marginTop: 5, fontSize: 12.5, fontWeight: '600' }}>
          {bootstrap?.behavioral_ai?.reengagement_nudge || 'Stay in flow—your next best pick is ready.'}
        </Text>
        <Text style={{ color: colors.textSec, marginTop: 6, fontSize: 10.8 }} data-testid={`audio-tab-best-return-time-${mode}`} testID={`audio-tab-best-return-time-${mode}`}>
          {`Best time to return: ${bootstrap?.behavioral_ai?.best_time_to_return?.label || '8:00 PM'} (${bootstrap?.behavioral_ai?.best_time_to_return?.window || 'evening'})`}
        </Text>
      </View>

      {(bootstrap?.smart_follow_up_items || []).length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid={`audio-tab-smart-follow-up-${mode}`} testID={`audio-tab-smart-follow-up-${mode}`}>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }}>Smart Follow-up Episodes</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {(bootstrap?.smart_follow_up_items || []).slice(0, 10).map((item: AudioItem) => (
              <TouchableOpacity key={`sf-${item.item_id}`} onPress={() => playItem(item)} style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9 }} data-testid={`audio-tab-smart-follow-item-${mode}-${item.item_id}`} testID={`audio-tab-smart-follow-item-${mode}-${item.item_id}`}>
                <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700' }} numberOfLines={2}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.category} • {item.creator}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {mode === 'audio_studio' && artistSpotlights.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="audio-studio-artist-spotlight-rail" testID="audio-studio-artist-spotlight-rail">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 6 }}>Official Artist Spotlight</Text>
          <Text style={{ color: colors.textSec, fontSize: 11.5, marginBottom: 8 }}>Verified artists with top album picks</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {artistSpotlights.map((spotlight) => {
              const hero = spotlight.items[0];
              return (
                <TouchableOpacity
                  key={`artist-spotlight-${spotlight.artist}`}
                  onPress={() => playItem(hero)}
                  style={{ width: '100%', maxWidth: 960, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }}
                  data-testid={`audio-studio-artist-spotlight-item-${spotlight.artist.replace(/\s+/g, '-').toLowerCase()}`}
                  testID={`audio-studio-artist-spotlight-item-${spotlight.artist.replace(/\s+/g, '-').toLowerCase()}`}
                >
                  <View style={{ width: '100%', aspectRatio: '16 / 10', backgroundColor: colors.bgSoft }}>
                    <Image source={{ uri: hero?.thumbnail_url || '' }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="ARTIST SPOTLIGHT" />
                  </View>
                  <View style={{ padding: 10 }}>
                    <View style={{ alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}14`, paddingHorizontal: 8, paddingVertical: 3 }}>
                      <Text style={{ color: cfg.accent, fontSize: 10, fontWeight: '800' }}>ARTIST SPOTLIGHT</Text>
                    </View>
                    <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800', marginTop: 7 }} numberOfLines={1}>{spotlight.artist}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 3 }} numberOfLines={1}>{spotlight.album}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10.5, marginTop: 6 }} numberOfLines={2}>
                      {spotlight.items.map((item) => item.title).slice(0, 2).join(' • ')}
                    </Text>
                    <TouchableOpacity
                      onPress={() => toggleFollowArtist(spotlight.artist)}
                      style={{ marginTop: 8, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: isArtistFollowed(spotlight.artist) ? `${cfg.accent}20` : 'transparent', paddingHorizontal: 8, paddingVertical: 5 }}
                      data-testid={`audio-studio-follow-artist-${spotlight.artist.replace(/\s+/g, '-').toLowerCase()}`}
                      testID={`audio-studio-follow-artist-${spotlight.artist.replace(/\s+/g, '-').toLowerCase()}`}
                    >
                      <Text style={{ color: cfg.accent, fontSize: 10.5, fontWeight: '800' }}>
                        {isArtistFollowed(spotlight.artist) ? 'Following' : 'Follow Artist'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      ) : null}

      {mode === 'audio_studio' && (bootstrap?.followed_artist_new_releases || []).length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="audio-studio-followed-artists-rail" testID="audio-studio-followed-artists-rail">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 6 }}>New from Followed Artists</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {(bootstrap?.followed_artist_new_releases || []).slice(0, 20).map((item: AudioItem) => (
              <TouchableOpacity
                key={`followed-release-${item.item_id}`}
                onPress={() => playItem(item)}
                style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9 }}
                data-testid={`audio-studio-followed-artist-item-${item.item_id}`}
                testID={`audio-studio-followed-artist-item-${item.item_id}`}
              >
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={2}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.artist_name || item.creator} • {item.album_name || 'Album'}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {mode === 'podcasts' && podcastStoryArc.items.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="podcast-story-arc-rail" testID="podcast-story-arc-rail">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 4 }}>Podcast Story Arc</Text>
            <TouchableOpacity
              onPress={() => setAutoPlayStoryArcEnabled((prev) => !prev)}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: autoPlayStoryArcEnabled ? `${cfg.accent}66` : colors.border, backgroundColor: autoPlayStoryArcEnabled ? `${cfg.accent}15` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }}
              data-testid="podcast-story-arc-autoplay-toggle"
              testID="podcast-story-arc-autoplay-toggle"
            >
              <Text style={{ color: autoPlayStoryArcEnabled ? cfg.accent : colors.textSec, fontSize: 10.5, fontWeight: '800' }}>
                {`Auto-play next: ${autoPlayStoryArcEnabled ? 'ON' : 'OFF'}`}
              </Text>
            </TouchableOpacity>
          </View>
          <Text style={{ color: colors.textSec, fontSize: 11.5, marginBottom: 8 }} numberOfLines={1}>
            {`Continue ${podcastStoryArc.seriesName} in sequence`}
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {podcastStoryArc.items.map((item, idx) => (
              <TouchableOpacity
                key={`story-arc-${item.item_id}`}
                onPress={() => playItem(item)}
                style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9 }}
                data-testid={`podcast-story-arc-item-${item.item_id}`}
                testID={`podcast-story-arc-item-${item.item_id}`}
              >
                <View style={{ alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}12`, paddingHorizontal: 7, paddingVertical: 3 }}>
                  <Text style={{ color: cfg.accent, fontSize: 10, fontWeight: '800' }}>{`EP ${idx + 1}`}</Text>
                </View>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', marginTop: 6 }} numberOfLines={2}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.host_name || item.creator} • {item.series_name || 'Series'}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {mode === 'sports' && sportsLiveRail.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="sports-live-events-rail" testID="sports-live-events-rail">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 6 }}>LIVE EVENTS</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {sportsLiveRail.map((item) => (
              <TouchableOpacity
                key={`sports-live-item-${item.item_id}`}
                onPress={() => playItem(item)}
                style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }}
                data-testid={`sports-live-item-${item.item_id}`}
                testID={`sports-live-item-${item.item_id}`}
              >
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

      {mode === 'sports' && sportsReplayRail.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="sports-non-live-events-rail" testID="sports-non-live-events-rail">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 6 }}>NON-LIVE EVENTS</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {sportsReplayRail.map((item) => (
              <TouchableOpacity
                key={`sports-replay-item-${item.item_id}`}
                onPress={() => playItem(item)}
                style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }}
                data-testid={`sports-replay-item-${item.item_id}`}
                testID={`sports-replay-item-${item.item_id}`}
              >
                <View style={{ width: '100%', aspectRatio: '16 / 9', backgroundColor: colors.bgSoft }}>
                  <Image source={{ uri: item.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="REPLAY" />
                </View>
                <View style={{ padding: 9 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 10.5, fontWeight: '800' }}>REPLAY</Text>
                  <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800', marginTop: 4 }} numberOfLines={2}>{item.title}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 2 }} numberOfLines={1}>{item.category} • {item.league}</Text>
                </View>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      {mode === 'sports' && sportsLeagueRails.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="sports-league-rails" testID="sports-league-rails">
          {sportsLeagueRails.map((rail) => (
            <View key={`sports-rail-${rail.league}`} style={{ marginBottom: 10 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{rail.league}</Text>
                <View style={{ alignItems: 'flex-end', gap: 6 }}>
                  <TouchableOpacity
                    onPress={() => toggleLeagueReminder(rail.league)}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: isLeagueFollowed(rail.league) ? `${cfg.accent}16` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }}
                    data-testid={`sports-league-reminder-toggle-${rail.league.replace(/\s+/g, '-').toLowerCase()}`}
                    testID={`sports-league-reminder-toggle-${rail.league.replace(/\s+/g, '-').toLowerCase()}`}
                  >
                    <Text style={{ color: isLeagueFollowed(rail.league) ? cfg.accent : colors.textSec, fontSize: 10.5, fontWeight: '800' }}>
                      {isLeagueFollowed(rail.league) ? 'Reminders On' : 'Remind Me Weekly'}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    onPress={() => togglePreKickoffReminder(rail.league)}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: isPreKickoffEnabled(rail.league) ? `${colors.successText}16` : colors.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }}
                    data-testid={`sports-league-prekick-toggle-${rail.league.replace(/\s+/g, '-').toLowerCase()}`}
                    testID={`sports-league-prekick-toggle-${rail.league.replace(/\s+/g, '-').toLowerCase()}`}
                  >
                    <Text style={{ color: isPreKickoffEnabled(rail.league) ? colors.successText : colors.textSec, fontSize: 10.5, fontWeight: '800' }}>
                      {isPreKickoffEnabled(rail.league) ? '15m Reminder On' : 'Remind 15m Before'}
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
                {rail.items.map((item) => (
                  <TouchableOpacity
                    key={`sports-rail-item-${item.item_id}`}
                    onPress={() => playItem(item)}
                    style={{ width: '100%', maxWidth: 960, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }}
                    data-testid={`sports-league-rail-item-${item.item_id}`}
                    testID={`sports-league-rail-item-${item.item_id}`}
                  >
                    <View style={{ width: '100%', aspectRatio: '16 / 9', backgroundColor: colors.bgSoft }}>
                      <Image source={{ uri: item.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="SPORTS" />
                    </View>
                    <View style={{ padding: 9 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}16`, paddingHorizontal: 7, paddingVertical: 3 }}>
                          <Text style={{ color: cfg.accent, fontSize: 10, fontWeight: '800' }}>SPORTS</Text>
                        </View>
                        {item.is_live ? (
                          <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: `${colors.successText}14`, paddingHorizontal: 7, paddingVertical: 3 }}>
                            <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800' }}>LIVE</Text>
                          </View>
                        ) : null}
                      </View>
                      <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800', marginTop: 6 }} numberOfLines={2}>{item.title}</Text>
                      <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 3 }} numberOfLines={1}>{item.event_stage || 'Match'} • {item.creator}</Text>
                      <Text
                        style={{ color: item.is_live ? colors.successText : colors.textMuted, fontSize: 10.5, marginTop: 3, fontWeight: '700' }}
                        data-testid={`sports-card-countdown-${item.item_id}`}
                        testID={`sports-card-countdown-${item.item_id}`}
                      >
                        {formatCountdownLabel(item.kickoff_at, item.is_live)}
                      </Text>
                    </View>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          ))}
        </View>
      ) : null}

      {(bootstrap?.behavioral_rails || []).length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid={`audio-tab-behavioral-rails-${mode}`} testID={`audio-tab-behavioral-rails-${mode}`}>
          {(bootstrap?.behavioral_rails || []).slice(0, 3).map((rail: any, rIdx: number) => (
            <View key={`br-${mode}-${rIdx}`} style={{ marginBottom: 10 }}>
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginBottom: 6 }}>{rail?.title || 'Dynamic Rail'}</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                {(rail?.items || []).slice(0, 10).map((item: AudioItem) => (
                  <TouchableOpacity key={`br-item-${item.item_id}`} onPress={() => playItem(item)} style={{ width: 200, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9, flexShrink: 1 }} data-testid={`audio-tab-behavioral-rail-item-${mode}-${item.item_id}`} testID={`audio-tab-behavioral-rail-item-${mode}-${item.item_id}`}>
                    <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700' }} numberOfLines={2}>{item.title}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }} numberOfLines={1}>{item.category} • {item.creator}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          ))}
        </View>
      ) : null}

      <View style={{ marginTop: 12, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid={`audio-tab-daily-inbox-${mode}`} testID={`audio-tab-daily-inbox-${mode}`}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14.5 }}>{mode === 'sports' ? 'Weekly Event Inbox' : 'Daily Drop Inbox'}</Text>
          <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 8, paddingVertical: 4 }}>
            <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700' }}>{bootstrap?.daily_drop_inbox?.unread || 0} unread</Text>
          </View>
        </View>
        <View style={{ marginTop: 8, gap: 8 }}>
          {(bootstrap?.daily_drop_inbox?.items || []).slice(0, 6).map((item: AudioItem & { listened?: boolean }) => (
            <View key={`inbox-${item.item_id}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 9, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <View style={{ flex: 1 }}>
                <View style={{ alignSelf: 'flex-start', marginBottom: 4, borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}14`, paddingHorizontal: 7, paddingVertical: 3 }} data-testid={`audio-tab-content-type-badge-inbox-${mode}-${item.item_id}`} testID={`audio-tab-content-type-badge-inbox-${mode}-${item.item_id}`}>
                  <Text style={{ color: cfg.accent, fontSize: 10, fontWeight: '800' }}>{contentTypeBadge}</Text>
                </View>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5 }}>{item.category} • {item.listened ? 'Listened' : 'New drop'}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                <TouchableOpacity onPress={() => playItem(item)} style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 5, backgroundColor: `${cfg.accent}18` }} data-testid={`audio-tab-inbox-play-${mode}-${item.item_id}`} testID={`audio-tab-inbox-play-${mode}-${item.item_id}`}>
                  <Text style={{ color: cfg.accent, fontWeight: '700', fontSize: 10.5 }}>Play</Text>
                </TouchableOpacity>
                {!item.listened ? (
                  <TouchableOpacity onPress={() => markInboxListened(item)} style={{ borderRadius: 999, paddingHorizontal: 8, paddingVertical: 5, borderWidth: 1, borderColor: colors.border }} data-testid={`audio-tab-inbox-mark-${mode}-${item.item_id}`} testID={`audio-tab-inbox-mark-${mode}-${item.item_id}`}>
                    <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 10.5 }}>Mark listened</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>
          ))}
        </View>
      </View>

      {(bootstrap?.locked_premium_picks || []).length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid={`audio-tab-locked-picks-${mode}`} testID={`audio-tab-locked-picks-${mode}`}>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }}>Locked Premium Picks</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {(bootstrap?.locked_premium_picks || []).slice(0, 12).map((item: AudioItem) => {
              const locked = isLocked(item);
              return (
                <TouchableOpacity key={`lp-${item.item_id}`} onPress={() => playItem(item)} style={{ width: 200, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: 'hidden', backgroundColor: colors.card }} data-testid={`audio-tab-locked-pick-item-${mode}-${item.item_id}`} testID={`audio-tab-locked-pick-item-${mode}-${item.item_id}`}>
                  <View style={{ width: '100%', aspectRatio: '1 / 1', backgroundColor: colors.bgSoft }}>
                    <Image source={{ uri: item.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="contentTypeBadge" />
                  </View>
                  <View style={{ padding: 8 }}>
                    <View style={{ alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}14`, paddingHorizontal: 7, paddingVertical: 3 }} data-testid={`audio-tab-content-type-badge-locked-${mode}-${item.item_id}`} testID={`audio-tab-content-type-badge-locked-${mode}-${item.item_id}`}>
                      <Text style={{ color: cfg.accent, fontSize: 10, fontWeight: '800' }}>{contentTypeBadge}</Text>
                    </View>
                    <Text style={{ color: colors.text, fontWeight: '700', fontSize: 11.5 }} numberOfLines={2}>{item.title}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 3 }}>{String(item.min_plan || 'premium').toUpperCase()}</Text>
                    {locked ? (
                      <TouchableOpacity onPress={openUpgrade} style={{ marginTop: 6, borderRadius: 999, backgroundColor: `${colors.warningText}22`, paddingHorizontal: 8, paddingVertical: 5, alignSelf: 'flex-start' }} data-testid={`audio-tab-locked-pick-upgrade-${mode}-${item.item_id}`} testID={`audio-tab-locked-pick-upgrade-${mode}-${item.item_id}`}>
                        <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '800' }}>Upgrade</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      ) : null}

      {(bootstrap?.adaptive_next_queue || []).length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid={`audio-tab-adaptive-queue-${mode}`} testID={`audio-tab-adaptive-queue-${mode}`}>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }}>Adaptive Next Up (Taste Vector v1)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {(bootstrap?.adaptive_next_queue || []).slice(0, 14).map((item: AudioItem) => (
              <TouchableOpacity key={`aq-${item.item_id}`} onPress={() => playItem(item)} style={{ width: 200, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 9, flexShrink: 1 }} data-testid={`audio-tab-adaptive-item-${mode}-${item.item_id}`} testID={`audio-tab-adaptive-item-${mode}-${item.item_id}`}>
                <View style={{ alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}14`, paddingHorizontal: 7, paddingVertical: 3 }} data-testid={`audio-tab-content-type-badge-adaptive-${mode}-${item.item_id}`} testID={`audio-tab-content-type-badge-adaptive-${mode}-${item.item_id}`}>
                  <Text style={{ color: cfg.accent, fontSize: 10, fontWeight: '800' }}>{contentTypeBadge}</Text>
                </View>
                <Text style={{ color: colors.text, fontWeight: '700', fontSize: 11.5 }} numberOfLines={2}>{item.title}</Text>
                <Text style={{ color: colors.textSec, fontSize: 10.5, marginTop: 4 }}>{item.category} • {item.creator}</Text>
                <View style={{ marginTop: 7, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}12`, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`audio-tab-adaptive-why-chip-${mode}-${item.item_id}`} testID={`audio-tab-adaptive-why-chip-${mode}-${item.item_id}`}>
                  <Text style={{ color: cfg.accent, fontSize: 10, fontWeight: '700' }} numberOfLines={1}>
                    {(item as any).why_recommended || 'Why recommended'}
                  </Text>
                </View>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      ) : null}

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 12 }} data-testid={`audio-tab-categories-${mode}`}>
        {categories.map((cat) => {
          const active = selectedCategory === cat;
          return (
            <TouchableOpacity
              key={cat}
              onPress={() => setSelectedCategory(cat)}
              style={{ borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, borderColor: active ? `${cfg.accent}66` : colors.border, backgroundColor: active ? `${cfg.accent}12` : colors.bgSoft }}
              data-testid={`audio-tab-category-${mode}-${String(cat).toLowerCase().replace(/\s+/g, '-')}`}
            >
              <Text style={{ color: active ? cfg.accent : colors.textSec, fontWeight: active ? '800' : '600', fontSize: 11.5 }}>{cat === 'all' ? 'All Categories' : cat}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 10, alignItems: 'stretch' }} data-testid={`audio-tab-grid-${mode}`}>
        {visibleItems.map((item) => {
          const regionBlocked = isRegionBlocked(item);
          const notPlayable = mode === 'sports' && !isWatchableNow(item);
          const locked = regionBlocked || notPlayable || isLocked(item);
          return (
            <TouchableOpacity
              key={item.item_id}
              onPress={() => playItem(item)}
              style={{ width: cardWidth as any, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }}
              data-testid={`audio-tab-item-${mode}-${item.item_id}`}
            >
              <View style={{ width: '100%', aspectRatio: '1 / 1', backgroundColor: colors.bgSoft }}>
                <Image source={{ uri: item.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel="lock closed outline button" />
                <View style={{ position: 'absolute', top: 8, right: 8, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: 'rgba(0,0,0,0.55)', flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  {locked ? <Ionicons name="lock-closed-outline" size={10} color="var(--app-primary-text)" /> : <Ionicons name="play" size={10} color="var(--app-primary-text)" />}
                  <Text style={{ color: 'var(--app-primary-text)', fontSize: 10.5, fontWeight: '700' }}>
                    {regionBlocked ? 'BLACKOUT' : notPlayable ? 'UNAVAILABLE' : String(item.min_plan || 'free').toUpperCase()}
                  </Text>
                </View>
              </View>
              <View style={{ padding: 10 }}>
                <View style={{ alignSelf: 'flex-start', marginBottom: 4, borderRadius: 999, borderWidth: 1, borderColor: `${cfg.accent}66`, backgroundColor: `${cfg.accent}14`, paddingHorizontal: 7, paddingVertical: 3 }} data-testid={`audio-tab-content-type-badge-grid-${mode}-${item.item_id}`} testID={`audio-tab-content-type-badge-grid-${mode}-${item.item_id}`}>
                  <Text style={{ color: cfg.accent, fontSize: 10, fontWeight: '800' }}>{contentTypeBadge}</Text>
                </View>
                <Text numberOfLines={2} style={{ color: colors.text, fontWeight: '700', fontSize: 12.5 }}>{item.title}</Text>
                <Text numberOfLines={1} style={{ marginTop: 4, color: colors.textSec, fontSize: 11.5 }}>{item.category} • {item.creator}</Text>
                <Text numberOfLines={1} style={{ marginTop: 2, color: colors.textMuted, fontSize: 10.5 }}>
                  {mode === 'audio_studio'
                    ? `${item.artist_name || item.creator} • ${item.album_name || 'Studio Release'}`
                    : mode === 'podcasts'
                      ? `${item.host_name || item.creator} • ${item.series_name || 'Podcast Show'}`
                      : `${item.league || item.category} • ${item.event_stage || 'Sports Event'}`}
                </Text>
                {mode === 'sports' ? (
                  <Text numberOfLines={1} style={{ marginTop: 2, color: isWatchableNow(item) ? colors.successText : colors.warningText, fontSize: 10.5, fontWeight: '700' }}>
                    {isWatchableNow(item)
                      ? (isEmbeddablePlayable(item)
                        ? `Playable score ${Math.max(0, Number(item.embeddability_score || 0))}`
                        : 'Watch now via official source link')
                      : `Unavailable (${item.embeddability_reason || 'precheck'})`}
                  </Text>
                ) : null}
                <Text style={{ marginTop: 2, color: colors.textMuted, fontSize: 10.5 }}>{formatDuration(item.duration_seconds)}</Text>

                {lockedReasonById[item.item_id] ? (
                  <View style={{ marginTop: 7, borderRadius: 9, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}15`, padding: 7 }} data-testid={`audio-tab-lock-tooltip-${mode}-${item.item_id}`}>
                    <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '700' }}>{lockedReasonById[item.item_id]}</Text>
                    {!regionBlocked && !notPlayable ? (
                      <TouchableOpacity onPress={openUpgrade} style={{ marginTop: 6, alignSelf: 'flex-start', borderRadius: 999, paddingHorizontal: 8, paddingVertical: 5, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}25` }} data-testid={`audio-tab-upgrade-cta-${mode}-${item.item_id}`}>
                        <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '800' }}>Upgrade to unlock</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                ) : null}
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      <Modal
        visible={externalConfirmVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setExternalConfirmVisible(false)}
      >
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center', alignItems: 'center', padding: 16 }} data-testid="sports-external-open-modal-overlay" testID="sports-external-open-modal-overlay">
          <View style={{ width: '100%', maxWidth: 420, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14 }} data-testid="sports-external-open-modal" testID="sports-external-open-modal">
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 16 }}>{t('sports.externalModal.title')}</Text>
            <Text style={{ marginTop: 8, color: colors.textSec, fontSize: 12.5 }}>
              {t('sports.externalModal.description')}
            </Text>

            <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }} data-testid="sports-external-open-trust-badges" testID="sports-external-open-trust-badges">
              <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: `${colors.successText}16`, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="sports-external-open-badge-source-verified" testID="sports-external-open-badge-source-verified">
                <Text style={{ color: colors.successText, fontSize: 10.5, fontWeight: '800' }}>{t('sports.externalModal.badge.sourceVerified')}</Text>
              </View>
              <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}16`, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="sports-external-open-badge-legal-stream" testID="sports-external-open-badge-legal-stream">
                <Text style={{ color: colors.primary, fontSize: 10.5, fontWeight: '800' }}>{t('sports.externalModal.badge.legalStream')}</Text>
              </View>
              <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}16`, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="sports-external-open-badge-official-page" testID="sports-external-open-badge-official-page">
                <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '800' }}>{t('sports.externalModal.badge.opensOfficialPage')}</Text>
              </View>
            </View>

            <TouchableOpacity
              onPress={() => setRememberExternalConfirmSession((prev) => !prev)}
              style={{ marginTop: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }}
              data-testid="sports-external-open-remember-toggle"
              testID="sports-external-open-remember-toggle"
            >
              <Ionicons name={rememberExternalConfirmSession ? 'checkbox' : 'square-outline'} size={18} color={rememberExternalConfirmSession ? colors.primary : colors.textSec} />
              <Text style={{ color: colors.textSec, fontSize: 12 }}>{t('sports.externalModal.rememberSession')}</Text>
            </TouchableOpacity>

            <View style={{ marginTop: 14, flexDirection: 'row', justifyContent: 'flex-end', gap: 10 }}>
              <TouchableOpacity
                onPress={() => setExternalConfirmVisible(false)}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, paddingVertical: 8 }}
                data-testid="sports-external-open-cancel"
                testID="sports-external-open-cancel"
              >
                <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>{t('sports.externalModal.cancel')}</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={confirmExternalOpen}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}77`, backgroundColor: `${colors.successText}16`, paddingHorizontal: 12, paddingVertical: 8 }}
                data-testid="sports-external-open-confirm"
                testID="sports-external-open-confirm"
              >
                <Text style={{ color: colors.successText, fontWeight: '800', fontSize: 12 }}>{t('sports.externalModal.continueOfficial')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}
