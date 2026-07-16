import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Image,
  Linking,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type PrayerAudioItem = {
  audio_id: string;
  title: string;
  description: string;
  scripture: string;
  category: string;
  audio_url: string;
  image_url: string;
  duration_sec: number;
  animation?: {
    preset?: string;
    duration_ms?: number;
    overlay?: string;
  };
  locked?: boolean;
  available?: boolean;
  semantic_score?: number;
  match_reasons?: string[];
};

const FALLBACK_PRAYER_AUDIO_BASE_CATEGORIES = [
  'Morning Gratitude', 'Evening Surrender', 'Anxiety Relief', 'Peace & Stillness', 'Healing & Recovery',
  'Family & Marriage', 'Parenting Wisdom', 'Financial Provision', 'Work & Career', 'Students & Exams',
  'Strength in Trials', 'Hope in Waiting', 'Forgiveness', 'Guidance & Discernment', 'Protection & Safety',
  'Deliverance & Freedom', 'Leadership & Service', 'Community & Unity', 'Nation & Governance', 'Missions & Compassion',
  'Sleep & Rest', 'Joy & Celebration', 'Grief & Comfort', 'New Beginnings', 'Thanksgiving & Testimony',
];

const FALLBACK_PRAYER_AUDIO_CATEGORIES = [
  ...FALLBACK_PRAYER_AUDIO_BASE_CATEGORIES,
  ...FALLBACK_PRAYER_AUDIO_BASE_CATEGORIES.flatMap((base) => [
    `${base} · for Students`,
    `${base} · for Professionals`,
    `${base} · for Families`,
    `${base} · for Leaders`,
    `${base} · for Recovery`,
  ]),
];

const FALLBACK_PRAYER_AUDIO_ITEMS: PrayerAudioItem[] = [
  {
    audio_id: 'fallback-audio-1',
    title: 'Peace & Stillness Prayer',
    description: 'A calming guided prayer for an overwhelmed heart.',
    scripture: 'Psalm 46:10 — Be still, and know that I am God.',
    category: 'Peace & Stillness',
    audio_url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
    image_url: 'https://images.unsplash.com/photo-1506126613408-eca07ce68773?auto=format&fit=crop&w=1600&q=80',
    duration_sec: 180,
    animation: { preset: 'soft-glow', duration_ms: 6000, overlay: '#14B8A6' }, // @theme-ok animation overlay constant
    locked: false,
    available: true,
  },
  {
    audio_id: 'fallback-audio-2',
    title: 'Hope in Waiting Prayer',
    description: 'A gentle prayer for patience and trust.',
    scripture: 'Isaiah 40:31 — Those who hope in the Lord will renew their strength.',
    category: 'Hope in Waiting',
    audio_url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3',
    image_url: 'https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?auto=format&fit=crop&w=1600&q=80',
    duration_sec: 210,
    animation: { preset: 'particle-drift', duration_ms: 8000, overlay: '#38BDF8' }, // @theme-ok animation overlay constant
    locked: false,
    available: true,
  },
  {
    audio_id: 'fallback-audio-3',
    title: 'Morning Gratitude Prayer',
    description: 'Start your day with gratitude and surrender.',
    scripture: 'Lamentations 3:22-23 — His mercies are new every morning.',
    category: 'Morning Gratitude',
    audio_url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3',
    image_url: 'https://images.unsplash.com/photo-1465101046530-73398c7f28ca?auto=format&fit=crop&w=1600&q=80',
    duration_sec: 200,
    animation: { preset: 'gentle-parallax', duration_ms: 7000, overlay: '#22C55E' }, // @theme-ok animation overlay constant
    locked: false,
    available: true,
  },
];

const SEMANTIC_INTENTS = ['peace', 'healing', 'guidance', 'provision', 'family', 'protection', 'strength', 'gratitude'];
const SEMANTIC_MOODS = ['anxious', 'overwhelmed', 'tired', 'grateful', 'hopeful', 'sad', 'fearful'];

type PrayerAudioStudioProps = {
  userId: string;
  plan: 'free' | 'basic' | 'premium';
  onFeedback?: (message: string, kind: 'success' | 'error') => void;
};

export default function PrayerAudioStudio({ userId, plan, onFeedback }: PrayerAudioStudioProps) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [loading, setLoading] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [todayItems, setTodayItems] = useState<PrayerAudioItem[]>([]);
  const [recommended, setRecommended] = useState<PrayerAudioItem[]>([]);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());
  const [audioCatalogTotal, setAudioCatalogTotal] = useState(0);
  const [selected, setSelected] = useState<PrayerAudioItem | null>(null);
  const [playingAudioId, setPlayingAudioId] = useState('');
  const [actionLoadingId, setActionLoadingId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchScripture, setSearchScripture] = useState('');
  const [searchIntent, setSearchIntent] = useState('peace');
  const [searchMood, setSearchMood] = useState('');
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<PrayerAudioItem[]>([]);
  const [searchTotal, setSearchTotal] = useState(0);

  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 2600, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 2600, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  const pulseScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.03] });
  const pulseOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0.62] });

  const loadData = useCallback(async () => {
    if (!userId) return;
    setLoading(true);

    const withRetry = async <T,>(factory: () => Promise<T>, retries = 2, delayMs = 700): Promise<T> => {
      let lastError: any;
      for (let i = 0; i <= retries; i += 1) {
        try {
          return await factory();
        } catch (err) {
          lastError = err;
          if (i < retries) {
            await new Promise((resolve) => setTimeout(resolve, delayMs));
          }
        }
      }
      throw lastError;
    };

    try {
      const [catSettled, todaySettled, favSettled, recSettled, statsSettled] = await Promise.allSettled([
        withRetry(() => api.get('/travel-visa/daily-meditation/prayer-audio/categories')),
        withRetry(() => api.get(`/travel-visa/daily-meditation/prayer-audio/today/${userId}`)),
        withRetry(() => api.get(`/travel-visa/daily-meditation/prayer-audio/favorites/${userId}`)),
        withRetry(() => api.get(`/travel-visa/daily-meditation/prayer-audio/recommendations/${userId}`)),
        withRetry(() => api.get('/travel-visa/daily-meditation/prayer-audio/catalog/stats')),
      ]);

      const catRes: any = catSettled.status === 'fulfilled' ? catSettled.value : null;
      const todayRes: any = todaySettled.status === 'fulfilled' ? todaySettled.value : null;
      const favRes: any = favSettled.status === 'fulfilled' ? favSettled.value : null;
      const recRes: any = recSettled.status === 'fulfilled' ? recSettled.value : null;
      const statsRes: any = statsSettled.status === 'fulfilled' ? statsSettled.value : null;

      const safeCategories = catRes?.data?.categories || FALLBACK_PRAYER_AUDIO_CATEGORIES;
      let safeToday = todayRes?.data?.items || [];
      if (!safeToday.length) {
        safeToday = FALLBACK_PRAYER_AUDIO_ITEMS.map((it, idx) => ({
          ...it,
          locked: plan === 'free' && idx >= 1,
          available: !(plan === 'free' && idx >= 1),
        }));
      }

      setCategories(safeCategories);
      setTodayItems(safeToday);
      setRecommended(recRes?.data?.items || safeToday.slice(0, 3));
      setAudioCatalogTotal(Number(statsRes?.data?.audio_total || catRes?.data?.total_audio_count || 0));
      const favRows = favRes?.data?.items || [];
      setFavoriteIds(new Set((favRows || []).map((it: any) => String(it.audio_id || ''))));
    } catch (e: any) {
      onFeedback?.(e?.response?.data?.detail || tx('dailyMeditation.prayerAudio.errors.loadFailed', 'Unable to load prayer audio today.'), 'error');
    }
    setLoading(false);
  }, [onFeedback, userId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const runSemanticSearch = useCallback(async () => {
    if (!userId || searchLoading) return;
    if (!searchQuery.trim() && !searchScripture.trim() && !searchIntent.trim() && !searchMood.trim()) {
      onFeedback?.(tx('dailyMeditation.prayerAudio.errors.searchSignalRequired', 'Add at least one search signal (intent, mood, query, or scripture).'), 'error');
      return;
    }
    setSearchLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQuery.trim()) params.append('q', searchQuery.trim());
      if (searchIntent.trim()) params.append('intent', searchIntent.trim());
      if (searchScripture.trim()) params.append('scripture', searchScripture.trim());
      if (searchMood.trim()) params.append('mood', searchMood.trim());
      params.append('limit', '12');
      const res = await api.get(`/travel-visa/daily-meditation/prayer-audio/semantic-search/${userId}?${params.toString()}`);
      const items = (res?.data?.items || []) as PrayerAudioItem[];
      setSearchResults(items);
      setSearchTotal(Number(res?.data?.total_matches || items.length || 0));
      if (!items.length) {
        onFeedback?.(tx('dailyMeditation.prayerAudio.errors.noMatches', 'No close matches found. Try another intent/mood combination.'), 'error');
      }
    } catch (e: any) {
      onFeedback?.(e?.response?.data?.detail || tx('dailyMeditation.prayerAudio.errors.searchUnavailable', 'Semantic search is unavailable right now.'), 'error');
      setSearchResults([]);
      setSearchTotal(0);
    }
    setSearchLoading(false);
  }, [onFeedback, searchIntent, searchLoading, searchMood, searchQuery, searchScripture, userId]);

  const clearSemanticSearch = useCallback(() => {
    setSearchQuery('');
    setSearchScripture('');
    setSearchIntent('peace');
    setSearchMood('');
    setSearchResults([]);
    setSearchTotal(0);
  }, []);

  const playPrayer = useCallback(async (item: PrayerAudioItem) => {
    if (!userId) return;
    setSelected(item);
    setPlayingAudioId(item.audio_id);
    setActionLoadingId(item.audio_id);
    try {
      const res = await api.post('/travel-visa/daily-meditation/prayer-audio/play', {
        user_id: userId,
        audio_id: item.audio_id,
      });
      const audio = (res.data?.audio || item) as PrayerAudioItem;
      setSelected(audio);
      setPlayingAudioId(audio.audio_id);
      onFeedback?.(tx('dailyMeditation.prayerAudio.success.ready', 'Prayer audio ready. Keep this moment calm and present.'), 'success');
    } catch (e: any) {
      onFeedback?.(e?.response?.data?.detail || tx('dailyMeditation.prayerAudio.errors.playFailed', 'Unable to play this prayer audio.'), 'error');
    }
    setActionLoadingId('');
  }, [onFeedback, userId]);

  const saveProgress = useCallback(async (audioId: string, positionSec: number, durationSec: number, completed: boolean) => {
    if (!userId || !audioId) return;
    try {
      await api.post('/travel-visa/daily-meditation/prayer-audio/progress', {
        user_id: userId,
        audio_id: audioId,
        position_sec: Math.max(0, Math.round(positionSec || 0)),
        duration_sec: Math.max(0, Math.round(durationSec || 0)),
        completed,
      });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/daily-meditation/PrayerAudioStudio.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [userId]);

  const toggleFavorite = useCallback(async (audioId: string, favorite: boolean) => {
    if (!userId || !audioId) return;
    try {
      await api.post('/travel-visa/daily-meditation/prayer-audio/favorite', {
        user_id: userId,
        audio_id: audioId,
        favorite,
      });
      setFavoriteIds((prev) => {
        const next = new Set(prev);
        if (favorite) next.add(audioId);
        else next.delete(audioId);
        return next;
      });
    } catch (e: any) {
      onFeedback?.(e?.response?.data?.detail || tx('dailyMeditation.prayerAudio.errors.favoriteUpdateFailed', 'Unable to update favorites.'), 'error');
    }
  }, [onFeedback, userId]);

  const freeCategoryCount = useMemo(() => 8, []);

  return (
    <View
      data-testid="daily-meditation-prayer-audio-section"
      testID="daily-meditation-prayer-audio-section"
      style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, marginBottom: 14 }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
          <Ionicons name="musical-notes-outline" size={16} color={colors.primary} />
          <Text style={{ fontSize: 14, fontWeight: '800', color: colors.text }}>{tx('dailyMeditation.prayerAudio.header.title', 'Prayer Audio + Animated Visuals')}</Text>
        </View>
        <View style={{ flex: 1 }} />
        <TouchableOpacity
          data-testid="daily-meditation-prayer-audio-refresh-button"
          testID="daily-meditation-prayer-audio-refresh-button"
          onPress={loadData}
          style={{ borderRadius: 9, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingHorizontal: 10, paddingVertical: 6 }}
        >
          <Text style={{ fontSize: 11, color: colors.textSec, fontWeight: '700' }}>{loading ? tx('common.loading', 'Loading...') : tx('common.refresh', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      <Text
        data-testid="daily-meditation-prayer-audio-category-count"
        testID="daily-meditation-prayer-audio-category-count"
        style={{ fontSize: 11, color: colors.textMuted, marginBottom: 8 }}
      >
        {tx('dailyMeditation.prayerAudio.header.categorySummary', `150 categories live (${categories.length}) · ${audioCatalogTotal || '500+'} prayer audios. Daily auto-drop: 3.`)}
      </Text>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
        <View style={{ flexDirection: 'row', gap: 7 }}>
          {(categories || []).map((category) => {
            const locked = plan === 'free' && !categories.slice(0, freeCategoryCount).includes(category);
            return (
              <View key={category} style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(locked ? colors.border : colors.success, '33'), backgroundColor: locked ? colors.surfaceHover : colors.successSoft }}>
                <Text style={{ fontSize: 10, color: locked ? colors.textMuted : colors.successText, fontWeight: '700' }}>{category}</Text>
              </View>
            );
          })}
        </View>
      </ScrollView>

      <View
        data-testid="daily-meditation-prayer-audio-semantic-search"
        testID="daily-meditation-prayer-audio-semantic-search"
        style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, padding: 10, marginBottom: 10 }}
      >
        <Text style={{ fontSize: 12, fontWeight: '800', color: colors.text, marginBottom: 6 }}>
          {tx('dailyMeditation.prayerAudio.search.title', 'Semantic Search (intent + scripture + mood)')}
        </Text>
        <TextInput accessibilityLabel="Text input"
          data-testid="daily-meditation-prayer-audio-search-query-input"
          testID="daily-meditation-prayer-audio-search-query-input"
          value={searchQuery}
          onChangeText={setSearchQuery}
          placeholder={tx('dailyMeditation.prayerAudio.search.queryPlaceholder', 'Search by need, phrase, or topic')}
          placeholderTextColor={colors.textMuted}
          style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8, color: colors.text, fontSize: 12, marginBottom: 8 }}
        />
        <TextInput accessibilityLabel="Text input"
          data-testid="daily-meditation-prayer-audio-search-scripture-input"
          testID="daily-meditation-prayer-audio-search-scripture-input"
          value={searchScripture}
          onChangeText={setSearchScripture}
          placeholder={tx('dailyMeditation.prayerAudio.search.scripturePlaceholder', 'Scripture reference (e.g., Psalm 46)')}
          placeholderTextColor={colors.textMuted}
          style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8, color: colors.text, fontSize: 12, marginBottom: 8 }}
        />

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {SEMANTIC_INTENTS.map((intent) => {
              const active = searchIntent === intent;
              return (
                <TouchableOpacity
                  key={intent}
                  data-testid={`daily-meditation-prayer-audio-search-intent-${intent}`}
                  testID={`daily-meditation-prayer-audio-search-intent-${intent}`}
                  onPress={() => setSearchIntent(intent)}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.primary : colors.border, backgroundColor: active ? colors.primarySoft : colors.card, paddingHorizontal: 10, paddingVertical: 5 }}
                >
                  <Text style={{ fontSize: 10, fontWeight: '700', color: active ? colors.primary : colors.textSec }}>{intent}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <TouchableOpacity
              data-testid="daily-meditation-prayer-audio-search-mood-none"
              testID="daily-meditation-prayer-audio-search-mood-none"
              onPress={() => setSearchMood('')}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: !searchMood ? colors.success : colors.border, backgroundColor: !searchMood ? colors.successSoft : colors.card, paddingHorizontal: 10, paddingVertical: 5 }}
            >
              <Text style={{ fontSize: 10, fontWeight: '700', color: !searchMood ? colors.successText : colors.textSec }}>{tx('dailyMeditation.prayerAudio.search.anyMood', 'any mood')}</Text>
            </TouchableOpacity>
            {SEMANTIC_MOODS.map((mood) => {
              const active = searchMood === mood;
              return (
                <TouchableOpacity
                  key={mood}
                  data-testid={`daily-meditation-prayer-audio-search-mood-${mood}`}
                  testID={`daily-meditation-prayer-audio-search-mood-${mood}`}
                  onPress={() => setSearchMood(active ? '' : mood)}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? colors.warning : colors.border, backgroundColor: active ? colors.warningSoft : colors.card, paddingHorizontal: 10, paddingVertical: 5 }}
                >
                  <Text style={{ fontSize: 10, fontWeight: '700', color: active ? colors.warningText : colors.textSec }}>{mood}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </ScrollView>

        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
          <TouchableOpacity
            data-testid="daily-meditation-prayer-audio-semantic-search-run-button"
            testID="daily-meditation-prayer-audio-semantic-search-run-button"
            onPress={() => void runSemanticSearch()}
            disabled={searchLoading}
            style={{ borderRadius: 8, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 7, opacity: searchLoading ? 0.7 : 1 }}
          >
            <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primaryText }}>{searchLoading ? tx('dailyMeditation.prayerAudio.search.searching', 'Searching...') : tx('dailyMeditation.prayerAudio.search.search', 'Search')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            data-testid="daily-meditation-prayer-audio-semantic-search-clear-button"
            testID="daily-meditation-prayer-audio-semantic-search-clear-button"
            onPress={clearSemanticSearch}
            style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: colors.card }}
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textSec }}>{tx('dailyMeditation.prayerAudio.search.clear', 'Clear')}</Text>
          </TouchableOpacity>
          {!!searchTotal && (
            <Text
              data-testid="daily-meditation-prayer-audio-semantic-search-total"
              testID="daily-meditation-prayer-audio-semantic-search-total"
              style={{ fontSize: 10, color: colors.textMuted }}
            >
              {searchTotal} {tx('dailyMeditation.prayerAudio.search.matches', 'matches')}
            </Text>
          )}
        </View>

        {searchResults.length > 0 && (
          <View data-testid="daily-meditation-prayer-audio-semantic-search-results" testID="daily-meditation-prayer-audio-semantic-search-results" style={{ marginTop: 8, gap: 6 }}>
            {searchResults.slice(0, 6).map((item) => (
              <View key={`semantic-${item.audio_id}`} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 8, flexDirection: 'row', alignItems: 'center' }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 11, fontWeight: '800', color: item.locked ? colors.textMuted : colors.text }} numberOfLines={1}>{item.title}</Text>
                  <Text style={{ fontSize: 10, color: colors.textMuted }} numberOfLines={1}>{item.category} • {tx('dailyMeditation.prayerAudio.labels.score', 'score')} {item.semantic_score || 0}</Text>
                </View>
                <TouchableOpacity
                  data-testid={`daily-meditation-prayer-audio-semantic-search-play-${item.audio_id}`}
                  testID={`daily-meditation-prayer-audio-semantic-search-play-${item.audio_id}`}
                  onPress={() => !item.locked && playPrayer(item)}
                  disabled={!!item.locked}
                  style={{ borderRadius: 8, backgroundColor: item.locked ? colors.border : colors.primary, paddingHorizontal: 10, paddingVertical: 6 }}
                >
                  <Text style={{ fontSize: 10, fontWeight: '800', color: item.locked ? colors.textMuted : colors.primaryText }}>{item.locked ? tx('dailyMeditation.prayerAudio.actions.upgrade', 'Upgrade') : tx('dailyMeditation.prayerAudio.actions.play', 'Play')}</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}
      </View>

      <View data-testid="daily-meditation-prayer-audio-today-list" testID="daily-meditation-prayer-audio-today-list" style={{ gap: 9 }}>
        {(todayItems || []).slice(0, 3).map((item) => {
          const isFavorite = favoriteIds.has(item.audio_id);
          const busy = actionLoadingId === item.audio_id;
          const locked = !!item.locked;
          return (
            <View key={item.audio_id} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, overflow: 'hidden' }}>
              <View style={{ flexDirection: 'row' }}>
                <View style={{ width: 120, height: 94, position: 'relative' }}>
                  <Image accessibilityLabel="Decorative image"
                    source={{ uri: item.image_url }}
                    resizeMode="cover"
                    style={{ width: '100%', height: '100%' }}
                    data-testid={`daily-meditation-prayer-audio-image-${item.audio_id}`}
                    testID={`daily-meditation-prayer-audio-image-${item.audio_id}`}
                  />
                  <Animated.View
                    data-testid={`daily-meditation-prayer-audio-animated-image-${item.audio_id}`}
                    testID={`daily-meditation-prayer-audio-animated-image-${item.audio_id}`}
                    style={{
                      position: 'absolute',
                      inset: 0,
                      backgroundColor: `${item.animation?.overlay || colors.primary}55`,
                      transform: [{ scale: pulseScale }],
                      opacity: pulseOpacity,
                    } as any}
                  />
                </View>

                <View style={{ flex: 1, padding: 10 }}>
                  <Text style={{ fontSize: 12, fontWeight: '800', color: colors.text }} numberOfLines={1}>{item.title}</Text>
                  <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 1 }} numberOfLines={1}>{item.category}</Text>
                  <Text style={{ fontSize: 10, color: colors.textSec, marginTop: 5 }} numberOfLines={2}>{item.scripture}</Text>
                  <View style={{ marginTop: 7, flexDirection: 'row', alignItems: 'center' }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 10, color: colors.textMuted }}>{Math.round((item.duration_sec || 0) / 60)} {tx('dailyMeditation.prayerAudio.labels.minutes', 'min')} • {item.animation?.preset || tx('dailyMeditation.prayerAudio.labels.animated', 'animated')}</Text>
                    </View>
                    <TouchableOpacity
                      data-testid={`daily-meditation-prayer-audio-favorite-${item.audio_id}`}
                      testID={`daily-meditation-prayer-audio-favorite-${item.audio_id}`}
                      onPress={() => toggleFavorite(item.audio_id, !isFavorite)}
                      style={{ marginRight: 8 }}
                    >
                      <Ionicons name={isFavorite ? 'heart' : 'heart-outline'} size={16} color={isFavorite ? colors.error : colors.textMuted} />
                    </TouchableOpacity>
                    <TouchableOpacity
                      data-testid={`daily-meditation-prayer-audio-play-${item.audio_id}`}
                      testID={`daily-meditation-prayer-audio-play-${item.audio_id}`}
                      onPress={() => !locked && playPrayer(item)}
                      disabled={busy || locked}
                      style={{
                        borderRadius: 8,
                        backgroundColor: locked ? colors.border : colors.primary,
                        paddingHorizontal: 10,
                        paddingVertical: 6,
                        opacity: busy ? 0.6 : 1,
                      }}
                    >
                      {busy ? (
                        <ActivityIndicator size="small" color={colors.primaryText} />
                      ) : (
                        <Text style={{ fontSize: 10, color: locked ? colors.textMuted : colors.primaryText, fontWeight: '800' }}>{locked ? tx('dailyMeditation.prayerAudio.states.locked', 'Locked') : tx('dailyMeditation.prayerAudio.actions.play', 'Play')}</Text>
                      )}
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            </View>
          );
        })}
      </View>

      {!!selected && (
        <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '44'), backgroundColor: colors.primarySoft, padding: 10 }}>
          <Text style={{ fontSize: 11, color: colors.primary, fontWeight: '800', marginBottom: 3 }}>{tx('dailyMeditation.prayerAudio.nowPlaying.title', 'Now Listening')}</Text>
          <Text data-testid="daily-meditation-prayer-audio-now-playing" testID="daily-meditation-prayer-audio-now-playing" style={{ fontSize: 12, color: colors.text, fontWeight: '700', marginBottom: 6 }}>
            {selected.title}
          </Text>

          {Platform.OS === 'web' ? (
            // eslint-disable-next-line jsx-a11y/media-has-caption
            <audio
              controls
              src={selected.audio_url}
              autoPlay
              data-testid="daily-meditation-prayer-audio-web-player"
              onTimeUpdate={(e: any) => {
                const t = Number(e?.currentTarget?.currentTime || 0);
                const d = Number(e?.currentTarget?.duration || 0);
                void saveProgress(selected.audio_id, t, d, false);
              }}
              onEnded={(e: any) => {
                const d = Number(e?.currentTarget?.duration || 0);
                void saveProgress(selected.audio_id, d, d, true);
              }}
              style={{ width: '100%', height: 36 }}
            />
          ) : (
            <TouchableOpacity
              data-testid="daily-meditation-prayer-audio-open-stream"
              testID="daily-meditation-prayer-audio-open-stream"
              onPress={() => Linking.openURL(selected.audio_url)}
              style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingHorizontal: 10, paddingVertical: 8, alignSelf: 'flex-start' }}
            >
              <Text style={{ fontSize: 11, color: colors.textSec, fontWeight: '700' }}>{tx('dailyMeditation.prayerAudio.actions.openStream', 'Open Prayer Audio Stream')}</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      <View style={{ marginTop: 10 }}>
        <Text style={{ fontSize: 12, color: colors.text, fontWeight: '800', marginBottom: 6 }}>{tx('dailyMeditation.prayerAudio.recommended.title', 'Recommended For You')}</Text>
        <View data-testid="daily-meditation-prayer-audio-recommendations" testID="daily-meditation-prayer-audio-recommendations" style={{ gap: 6 }}>
          {(recommended || []).slice(0, 4).map((item) => (
            <TouchableOpacity
              key={`rec-${item.audio_id}`}
              data-testid={`daily-meditation-prayer-audio-recommendation-${item.audio_id}`}
              testID={`daily-meditation-prayer-audio-recommendation-${item.audio_id}`}
              onPress={() => !item.locked && playPrayer(item)}
              style={{ borderRadius: 9, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceHover, paddingHorizontal: 10, paddingVertical: 8, flexDirection: 'row', alignItems: 'center' }}
            >
              <Ionicons name="sparkles-outline" size={13} color={colors.primary} />
              <Text style={{ marginLeft: 8, flex: 1, fontSize: 11, color: item.locked ? colors.textMuted : colors.text }} numberOfLines={1}>
                {item.title}
              </Text>
              <Text style={{ fontSize: 10, color: colors.textMuted }}>{item.locked ? tx('dailyMeditation.prayerAudio.states.locked', 'Locked') : tx('dailyMeditation.prayerAudio.states.ready', 'Ready')}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
    </View>
  );
}
