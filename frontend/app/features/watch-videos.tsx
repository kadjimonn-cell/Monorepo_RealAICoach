import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Animated,
  Image,
  ImageBackground,
  Linking,
  Platform,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import AudioCatalogTab from '../../src/components/AudioCatalogTab';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { WatchVideosShell } from '../../src/components/watch-videos/WatchVideosShell';
import { WatchVideosPlayerPane } from '../../src/components/watch-videos/WatchVideosPlayerPane';
import { WatchVideosRecommendationPanel } from '../../src/components/watch-videos/WatchVideosRecommendationPanel';
import { WatchVideosWatchlistPanel } from '../../src/components/watch-videos/WatchVideosWatchlistPanel';
import { WatchVideosCatalogGrid } from '../../src/components/watch-videos/WatchVideosCatalogGrid';
import { WatchVideosRetentionPanel } from '../../src/components/watch-videos/WatchVideosRetentionPanel';
import { WatchVideosLoadingSkeleton } from '../../src/components/watch-videos/WatchVideosLoadingSkeleton';

type VideoItem = {
  video_id: string;
  title: string;
  description: string;
  category: string;
  duration_seconds: number;
  video_url: string;
  fallback_video_url?: string;
  playback_type?: 'youtube' | 'mp4';
  youtube_video_id?: string;
  youtube_embed_url?: string;
  source_label?: string;
  source_trust_badge?: 'Official' | 'Trailer' | 'Clip' | string;
  source_channel?: string;
  saga_key?: string;
  saga_name?: string;
  saga_order?: number;
  spoiler_safe_recap?: string;
  thumbnail_url: string;
  min_plan: string;
  tags: string[];
  studio: string;
  year: number;
  language: string;
  rating: string;
  quality_label: string;
  view_count: number;
  like_count: number;
  drop_key: string;
  released_at: string;
  progress_seconds: number;
  completed: boolean;
  feedback: string;
  watchlisted?: boolean;
  recommendation_reason?: string[];
  recommendation_score?: number;
  recommendation_signals?: string[];
};

type RetentionProfilePayload = {
  score: number;
  level: string;
  churn_risk: 'low' | 'medium' | 'high' | string;
  mission_focus: string;
  risk_pct: number;
  adaptive_signals?: {
    watch_sessions_7d?: number;
    completion_rate_recent_pct?: number;
    likes_ratio_pct?: number;
    continue_queue_depth?: number;
    watchlist_depth?: number;
    recommendation_quality_avg?: number;
  };
  next_best_actions?: string[];
  streak_rewards?: {
    current_streak_days?: number;
    total_watch_days?: number;
    streak_status?: 'active' | 'at_risk' | 'cold' | string;
    points?: number;
    current_badge?: string;
    badges_unlocked?: Array<{
      badge_key?: string;
      badge_title?: string;
      reward_label?: string;
      required_days?: number;
    }>;
    next_milestone?: {
      required_days?: number;
      badge_title?: string;
      reward_label?: string;
      remaining_days?: number;
      progress_pct?: number;
    };
  };
};

type QueueInsight = {
  headline: string;
  reason: string;
  source?: string;
};

type QueueShortcuts = {
  watchlist_count: number;
  continue_count: number;
  watchlist_first_video_id: string;
  continue_first_video_id: string;
  queue_insight?: QueueInsight;
};

type WatchlistSortMode = 'recent' | 'duration' | 'category';
type WatchlistSortDirection = 'desc' | 'asc';

type VisualPreferences = {
  show_recommendation_reasons: boolean;
  watchlist_sort_mode: WatchlistSortMode;
  watchlist_sort_direction: WatchlistSortDirection;
  autoplay_next_enabled: boolean;
};

type VisualThemeConfig = {
  theme_cycle: string;
  default_style_pack: 'cinematic' | 'documentary' | 'creator';
  category_style_packs: Record<string, 'cinematic' | 'documentary' | 'creator'>;
  updated_at?: string;
};

type QuotaPayload = {
  plan: string;
  scope_label: string;
  limit: number;
  used: number;
  remaining: number;
};

const DEFAULT_QUOTA_PAYLOAD: QuotaPayload = {
  plan: 'free',
  scope_label: 'Limited access',
  limit: 5,
  used: 0,
  remaining: 5,
};

type SagaResumePayload = {
  saga_key: string;
  saga_name: string;
  resume_video: VideoItem | null;
  last_watched_video_id: string;
  last_watched_at: string;
  resume_reason: string;
  has_next_part: boolean;
};

type BootstrapPayload = {
  plan: string;
  scope_label: string;
  quota: QuotaPayload;
  total_visible: number;
  total_catalog: number;
  categories: string[];
  featured_video: VideoItem | null;
  today_drop: VideoItem[];
  continue_watching: VideoItem[];
  continue_queue?: VideoItem[];
  saga_resume_item?: SagaResumePayload | null;
  watchlist?: VideoItem[];
  retention_profile?: RetentionProfilePayload | null;
  queue_shortcuts?: QueueShortcuts;
  visual_preferences?: VisualPreferences;
  can_admin_visuals?: boolean;
  visual_theme?: VisualThemeConfig | null;
  recommended_for_you: VideoItem[];
  trending_now: VideoItem[];
  new_releases: VideoItem[];
  category_rows: Record<string, VideoItem[]>;
  feedback_by_video: Record<string, string>;
  catalog: VideoItem[];
  selected_video: VideoItem | null;
};

type CatalogPayload = {
  quota: QuotaPayload;
  total: number;
  has_more: boolean;
  sort_by: string;
  items: VideoItem[];
};

type FeedTab = 'home' | 'trending' | 'new' | 'library';
type SortOption = 'latest' | 'trending' | 'duration_desc' | 'duration_asc' | 'alphabetical';

type UndoFeedbackToast = {
  videoId: string;
  previousFeedback: string;
  nextFeedback: 'like' | 'dislike';
};

type StylePackOption = 'cinematic' | 'documentary' | 'creator';

const PROGRESS_SYNC_INTERVAL_SECONDS = 8;
const DEFAULT_VISUAL_PREFERENCES: VisualPreferences = {
  show_recommendation_reasons: true,
  watchlist_sort_mode: 'recent',
  watchlist_sort_direction: 'desc',
  autoplay_next_enabled: true,
};

const SORT_OPTIONS: Array<{ key: SortOption; label: string; icon: keyof typeof Ionicons.glyphMap }> = [
  { key: 'latest', label: 'Latest', icon: 'time-outline' },
  { key: 'trending', label: 'Trending', icon: 'flame-outline' },
  { key: 'duration_desc', label: 'Long form', icon: 'timer-outline' },
  { key: 'alphabetical', label: 'A-Z', icon: 'text-outline' },
];

const FEED_TABS: Array<{ key: FeedTab; label: string }> = [
  { key: 'home', label: 'Home' },
  { key: 'trending', label: 'Trending' },
  { key: 'new', label: 'New Releases' },
  { key: 'library', label: 'Library' },
];

const formatDuration = (seconds: number): string => {
  const safe = Math.max(0, Number(seconds || 0));
  const hrs = Math.floor(safe / 3600);
  const mins = Math.floor((safe % 3600) / 60);
  if (hrs > 0) {
    return `${hrs}h ${mins}m`;
  }
  return `${Math.max(1, mins)}m`;
};

const compactNumber = (value: number): string => {
  const safe = Math.max(0, Number(value || 0));
  if (safe >= 1_000_000) return `${(safe / 1_000_000).toFixed(1)}M`;
  if (safe >= 1_000) return `${(safe / 1_000).toFixed(1)}K`;
  return String(safe);
};

const resolvePlaybackSource = (video: VideoItem | null | undefined, forceFallback = false) => {
  if (!video) {
    return {
      primary_kind: 'none' as const,
      primary_url: '',
      fallback_url: '',
      can_play: false,
      source_label: 'Unavailable',
      source_trust_badge: 'Official',
      source_channel: 'Verified Channel',
    };
  }

  const fallbackUrl = String(video.fallback_video_url || video.video_url || '').trim();
  const youtubeUrl = String(video.youtube_embed_url || '').trim();
  const playbackType = String(video.playback_type || '').toLowerCase();
  const shouldUseYoutube = !forceFallback && playbackType === 'youtube' && Boolean(youtubeUrl);
  const primaryUrl = shouldUseYoutube ? youtubeUrl : fallbackUrl;
  const primaryKind = shouldUseYoutube ? 'youtube' : (primaryUrl ? 'mp4' : 'none');

  return {
    primary_kind: primaryKind,
    primary_url: primaryUrl,
    fallback_url: fallbackUrl,
    can_play: Boolean(primaryUrl),
    source_label: String(video.source_label || (shouldUseYoutube ? 'YouTube' : 'Direct Stream') || 'Stream'),
    source_trust_badge: String(video.source_trust_badge || 'Official'),
    source_channel: String(video.source_channel || video.studio || 'Verified Channel'),
  };
};

const PLAN_LEVELS: Record<string, number> = {
  free: 0,
  basic: 1,
  premium: 2,
};

const normalizePlan = (value: string | undefined | null) => String(value || 'free').trim().toLowerCase();

const getPlanLockReasonForVideo = (video: VideoItem, currentPlan: string): string => {
  const requiredPlan = normalizePlan(video?.min_plan || 'free');
  const activePlan = normalizePlan(currentPlan);
  const requiredRank = PLAN_LEVELS[requiredPlan] ?? 0;
  const activeRank = PLAN_LEVELS[activePlan] ?? 0;
  if (requiredRank <= activeRank) return '';
  return `Locked: Requires ${requiredPlan.toUpperCase()} plan. Upgrade to watch this title.`;
};

const CATEGORY_ACCENT_PALETTE = [
  'rgba(255, 87, 87, 1)',
  'rgba(87, 180, 255, 1)',
  'rgba(255, 175, 74, 1)',
  'rgba(129, 227, 140, 1)',
  'rgba(193, 127, 255, 1)',
  'rgba(255, 120, 194, 1)',
  'rgba(92, 241, 220, 1)',
];

const categoryAccentColor = (category: string) => {
  const text = String(category || 'general').toLowerCase();
  let sum = 0;
  for (let i = 0; i < text.length; i += 1) sum += text.charCodeAt(i);
  return CATEGORY_ACCENT_PALETTE[sum % CATEGORY_ACCENT_PALETTE.length];
};

type ProgressiveImageBackgroundProps = {
  uri: string;
  style: any;
  imageStyle?: any;
  placeholderTestId: string;
  children: React.ReactNode;
};

const toBlurPlaceholderUri = (uri: string) => {
  if (!uri) return '';
  const joiner = uri.includes('?') ? '&' : '?';
  return `${uri}${joiner}blur=8`;
};

const ProgressiveImageBackground = ({ uri, style, imageStyle, placeholderTestId, children }: ProgressiveImageBackgroundProps) => {
  const [loaded, setLoaded] = useState(false);
  const src = String(uri || '').trim();
  const placeholderUri = toBlurPlaceholderUri(src);

  useEffect(() => {
    setLoaded(false);
  }, [src]);

  return (
    <View style={[style, { overflow: 'hidden', backgroundColor: 'rgba(18,22,30,0.72)' }]}>
      {placeholderUri ? (
        <Image
          source={{ uri: placeholderUri }}
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, transform: [{ scale: 1.06 }], opacity: loaded ? 0 : 1 }}
          resizeMode="cover"
        />
      ) : null}

      <ImageBackground
        source={{ uri: src || undefined }}
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
        imageStyle={[imageStyle, { opacity: loaded ? 1 : 0.04 }]}
        onLoadEnd={() => setLoaded(true)}
      >
        {children}
      </ImageBackground>

      {!loaded ? (
        <View
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(16,20,28,0.22)' }}
          data-testid={placeholderTestId}
          testID={placeholderTestId}
          pointerEvents="none"
        />
      ) : null}
    </View>
  );
};

const WebIframe = (props: Record<string, any>) => React.createElement('iframe', props);

const mergeRows = (rows: VideoItem[], videoId: string, patch: Partial<VideoItem>) => (
  (rows || []).map((item) => (item.video_id === videoId ? { ...item, ...patch } : item))
);

const isSameQuota = (left?: QuotaPayload | null, right?: QuotaPayload | null): boolean => {
  if (!left || !right) return false;
  return (
    String(left.plan || '') === String(right.plan || '')
    && String(left.scope_label || '') === String(right.scope_label || '')
    && Number(left.limit || 0) === Number(right.limit || 0)
    && Number(left.used || 0) === Number(right.used || 0)
    && Number(left.remaining || 0) === Number(right.remaining || 0)
  );
};

type RailProps = {
  title: string;
  testId: string;
  items: VideoItem[];
  activeVideoId?: string;
  colors: any;
  showReasons: boolean;
  currentPlan: string;
  lockReasonByVideo: Record<string, string>;
  onBlockedPress: (video: VideoItem, reason: string) => void;
  onUpgradePress: (video: VideoItem) => void;
  onPlay: (video: VideoItem, source: string) => void;
};

const VideoRail = ({
  title,
  testId,
  items,
  activeVideoId,
  colors,
  showReasons,
  currentPlan,
  lockReasonByVideo,
  onBlockedPress,
  onUpgradePress,
  onPlay,
}: RailProps) => {
  if (!items.length) return null;

  return (
    <View
      style={{ marginHorizontal: 16, marginBottom: 18 }}
      data-testid={`${testId}-section`}
      testID={`${testId}-section`}
    >
      <Text
        style={{ color: colors.text, fontSize: 16, fontWeight: '700', marginBottom: 10 }}
        data-testid={`${testId}-title`}
        testID={`${testId}-title`}
      >
        {title}
      </Text>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 10, paddingRight: 4 }}
        data-testid={`${testId}-scroll`}
        testID={`${testId}-scroll`}
      >
        {items.map((video) => {
          const active = activeVideoId === video.video_id;
          const accent = categoryAccentColor(video.category);
          const lockReason = getPlanLockReasonForVideo(video, currentPlan);
          const isLocked = Boolean(lockReason);
          return (
            <TouchableOpacity
              key={video.video_id}
              onPress={() => {
                if (isLocked) {
                  onBlockedPress(video, lockReason);
                  return;
                }
                onPlay(video, `${testId}_rail`);
              }}
              style={{
                width: '100%',
                maxWidth: 960,
                borderRadius: 18,
                overflow: 'hidden',
                borderWidth: 1,
                borderColor: active ? `${accent.replace('1)', '0.75)')}` : colors.border,
                backgroundColor: colors.card,
                shadowColor: 'rgba(0,0,0,0.45)',
                shadowOpacity: 0.35,
                shadowRadius: 8,
                shadowOffset: { width: 0, height: 5 },
              }}
              data-testid={`${testId}-item-${video.video_id}`}
              testID={`${testId}-item-${video.video_id}`}
            >
              <ProgressiveImageBackground
                uri={video.thumbnail_url || ''}
                style={{ aspectRatio: 16 / 9, justifyContent: 'flex-end' }}
                imageStyle={{ opacity: active ? 0.95 : 0.9 }}
                placeholderTestId={`${testId}-thumb-placeholder-${video.video_id}`}
              >
                <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(7,10,18,0.22)' }} />
                <View style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '62%', backgroundColor: 'rgba(7,10,18,0.68)' }} />

                <View style={{ position: 'absolute', top: 8, left: 8, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: accent }} />
                  <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: 'rgba(0,0,0,0.5)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
                    <Text numberOfLines={1} style={{ color: 'rgba(255,255,255,1)', fontSize: 10.5, fontWeight: '700' }}>
                      {video.category}
                    </Text>
                  </View>
                </View>

                <View style={{ position: 'absolute', top: 8, right: 8, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: 'rgba(0,0,0,0.48)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.16)' }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    {isLocked ? <Ionicons name="lock-closed-outline" size={10} color="rgba(255,255,255,0.92)" /> : null}
                    <Text style={{ color: 'rgba(255,255,255,1)', fontSize: 10.5, fontWeight: '700' }}>{video.min_plan.toUpperCase()}</Text>
                  </View>
                </View>

                <View style={{ padding: 10 }}>
                  <Text numberOfLines={1} style={{ color: 'rgba(255,255,255,1)', fontSize: 12.5, fontWeight: '700' }}>
                    {video.quality_label || 'HD'} • {formatDuration(video.duration_seconds)}
                  </Text>
                </View>
              </ProgressiveImageBackground>

              <View style={{ padding: 10 }}>
                <Text numberOfLines={2} style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
                  {video.title}
                </Text>
                <View
                  style={{ marginTop: 6, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 8, paddingVertical: 4 }}
                  data-testid={`${testId}-content-type-badge-${video.video_id}`}
                  testID={`${testId}-content-type-badge-${video.video_id}`}
                >
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>VIDEO</Text>
                </View>
                <Text numberOfLines={1} style={{ marginTop: 4, color: colors.textSec, fontSize: 11.5 }}>
                  {video.category} • {compactNumber(video.view_count)} views
                </Text>
                {lockReasonByVideo[video.video_id] ? (
                  <View
                    style={{ marginTop: 6, borderRadius: 8, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}14`, paddingHorizontal: 8, paddingVertical: 6 }}
                    data-testid={`${testId}-lock-tooltip-${video.video_id}`}
                    testID={`${testId}-lock-tooltip-${video.video_id}`}
                  >
                    <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '700' }} numberOfLines={2}>
                      {lockReasonByVideo[video.video_id]}
                    </Text>
                    <TouchableOpacity
                      onPress={() => onUpgradePress(video)}
                      style={{ marginTop: 6, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}22`, paddingHorizontal: 9, paddingVertical: 5, flexDirection: 'row', alignItems: 'center', gap: 4 }}
                      data-testid={`${testId}-lock-upgrade-cta-${video.video_id}`}
                      testID={`${testId}-lock-upgrade-cta-${video.video_id}`}
                    >
                      <Ionicons name="arrow-up-circle-outline" size={11} color={colors.warningText} />
                      <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '700' }}>Upgrade to unlock</Text>
                    </TouchableOpacity>
                  </View>
                ) : null}
                {showReasons && (video.recommendation_reason || []).length > 0 ? (
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 7 }}>
                    {(video.recommendation_reason || []).slice(0, 2).map((reason, idx) => (
                      <View
                        key={`${video.video_id}-reason-${idx}`}
                        style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}44`, backgroundColor: `${colors.primary}10`, paddingHorizontal: 8, paddingVertical: 4 }}
                        data-testid={`${testId}-reason-${video.video_id}-${idx}`}
                        testID={`${testId}-reason-${video.video_id}-${idx}`}
                      >
                        <Text style={{ color: colors.primary, fontSize: 10.5, fontWeight: '700' }} numberOfLines={1}>
                          {reason}
                        </Text>
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
};

export default function WatchVideosScreen() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  t('i18n.route.features.watch-videos.probe');
  const { width } = useWindowDimensions();

  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [savingProgress, setSavingProgress] = useState(false);
  const [bootstrap, setBootstrap] = useState<BootstrapPayload | null>(null);
  const [catalogState, setCatalogState] = useState<CatalogPayload | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedSort, setSelectedSort] = useState<SortOption>('latest');
  const [activeFeed, setActiveFeed] = useState<FeedTab>('home');
  const [selectedVideo, setSelectedVideo] = useState<VideoItem | null>(null);
  const [playingVideoId, setPlayingVideoId] = useState('');
  const [feedbackByVideo, setFeedbackByVideo] = useState<Record<string, string>>({});
  const [watchlistByVideo, setWatchlistByVideo] = useState<Record<string, boolean>>({});
  const [watchlistSortMode, setWatchlistSortMode] = useState<WatchlistSortMode>('recent');
  const [watchlistSortDirection, setWatchlistSortDirection] = useState<WatchlistSortDirection>('desc');
  const [visualPreferences, setVisualPreferences] = useState<VisualPreferences>(DEFAULT_VISUAL_PREFERENCES);
  const [adminVisualTheme, setAdminVisualTheme] = useState<VisualThemeConfig | null>(null);
  const [observabilitySnapshot, setObservabilitySnapshot] = useState<any>(null);
  const [observabilityLoading, setObservabilityLoading] = useState(false);
  const [adminSelectedCategory, setAdminSelectedCategory] = useState('all');
  const [adminSelectedStylePack, setAdminSelectedStylePack] = useState<StylePackOption>('cinematic');
  const [adminApplyingTheme, setAdminApplyingTheme] = useState(false);
  const [unavailableVideoIds, setUnavailableVideoIds] = useState<Record<string, boolean>>({});
  const [forceFallbackPlaybackByVideo, setForceFallbackPlaybackByVideo] = useState<Record<string, boolean>>({});
  const [currentPlaybackSeconds, setCurrentPlaybackSeconds] = useState(0);
  const [undoFeedbackToast, setUndoFeedbackToast] = useState<UndoFeedbackToast | null>(null);
  const [showRecommendationReasons, setShowRecommendationReasons] = useState(true);
  const [playIntentNonce, setPlayIntentNonce] = useState(0);
  const [playerCardOffsetY, setPlayerCardOffsetY] = useState(0);
  const [youtubeLoadedVideoId, setYoutubeLoadedVideoId] = useState('');
  const [lockReasonByVideo, setLockReasonByVideo] = useState<Record<string, string>>({});
  const [showContentReadyTransition, setShowContentReadyTransition] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const scrollRef = useRef<ScrollView | null>(null);
  const lastSyncedRef = useRef(0);
  const selectedVideoRef = useRef<VideoItem | null>(null);
  const undoFeedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lockReasonTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const inFlightCatalogQueryRef = useRef('');
  const lastLoadedCatalogQueryRef = useRef('');
  const contentReadyOpacity = useRef(new Animated.Value(0)).current;
  const skeletonDissolveOpacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    selectedVideoRef.current = selectedVideo;
    setCurrentPlaybackSeconds(Math.max(0, Number(selectedVideo?.progress_seconds || 0)));
  }, [selectedVideo]);

  useEffect(() => {
    return () => {
      if (undoFeedbackTimerRef.current) {
        clearTimeout(undoFeedbackTimerRef.current);
      }
      Object.values(lockReasonTimersRef.current).forEach((timerId) => clearTimeout(timerId));
    };
  }, []);

  const quota = useMemo(() => {
    return bootstrap?.quota || catalogState?.quota || DEFAULT_QUOTA_PAYLOAD;
  }, [bootstrap?.quota, catalogState?.quota]);

  const categories = useMemo(() => ['all', ...(bootstrap?.categories || [])], [bootstrap?.categories]);

  const showBlockedCardTooltip = useCallback((video: VideoItem, reason: string) => {
    if (!video?.video_id || !reason) return;
    const videoId = video.video_id;
    setLockReasonByVideo((prev) => ({ ...prev, [videoId]: reason }));

    if (lockReasonTimersRef.current[videoId]) {
      clearTimeout(lockReasonTimersRef.current[videoId]);
    }
    lockReasonTimersRef.current[videoId] = setTimeout(() => {
      setLockReasonByVideo((prev) => {
        const next = { ...prev };
        delete next[videoId];
        return next;
      });
      delete lockReasonTimersRef.current[videoId];
    }, 3000);
  }, []);

  const handleUpgradeFromLockedCard = useCallback((_video: VideoItem) => {
    const plansPath = '/subscription/plans';
    if (Platform.OS === 'web' && typeof window !== 'undefined' && window?.location) {
      window.location.assign(plansPath);
      return;
    }
    void Linking.openURL(plansPath);
  }, []);

  const gridColumns = width >= 1500 ? 5 : width >= 1240 ? 4 : width >= 980 ? 3 : width >= 680 ? 2 : 1;
  const gridCardWidth = gridColumns === 5
    ? '19%'
    : gridColumns === 4
      ? '24%'
      : gridColumns === 3
        ? '32.2%'
        : gridColumns === 2
          ? '48.8%'
          : '100%';

  const baseCardStyle = {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    overflow: 'hidden',
  } as any;

  const updateLocalVideoState = useCallback((videoId: string, patch: Partial<VideoItem>) => {
    setSelectedVideo((prev) => (prev?.video_id === videoId ? { ...prev, ...patch } : prev));
    setBootstrap((prev) => {
      if (!prev) return prev;
      const categoryRows: Record<string, VideoItem[]> = {};
      Object.entries(prev.category_rows || {}).forEach(([key, rows]) => {
        categoryRows[key] = mergeRows(rows, videoId, patch);
      });
      return {
        ...prev,
        featured_video: prev.featured_video?.video_id === videoId ? { ...prev.featured_video, ...patch } : prev.featured_video,
        selected_video: prev.selected_video?.video_id === videoId ? { ...prev.selected_video, ...patch } : prev.selected_video,
        today_drop: mergeRows(prev.today_drop || [], videoId, patch),
        continue_watching: mergeRows(prev.continue_watching || [], videoId, patch),
        continue_queue: mergeRows(prev.continue_queue || [], videoId, patch),
        watchlist: mergeRows(prev.watchlist || [], videoId, patch),
        recommended_for_you: mergeRows(prev.recommended_for_you || [], videoId, patch),
        trending_now: mergeRows(prev.trending_now || [], videoId, patch),
        new_releases: mergeRows(prev.new_releases || [], videoId, patch),
        catalog: mergeRows(prev.catalog || [], videoId, patch),
        category_rows: categoryRows,
      };
    });
    setCatalogState((prev) => (prev ? { ...prev, items: mergeRows(prev.items || [], videoId, patch) } : prev));
  }, []);

  const saveVisualPreferences = useCallback(async (patch: Partial<VisualPreferences>) => {
    if (!patch || Object.keys(patch).length === 0) return;
    try {
      const response = await api.post('/videos/preferences', patch);
      const next = { ...DEFAULT_VISUAL_PREFERENCES, ...(response?.data?.preferences || {}) } as VisualPreferences;
      setVisualPreferences(next);
    } catch (error) { handleAppRecoverableError({ scope: 'features/watch-videos.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const applyVisualPreferencePatch = useCallback((patch: Partial<VisualPreferences>) => {
    setVisualPreferences((prev) => ({ ...prev, ...patch }));
    void saveVisualPreferences(patch);
  }, [saveVisualPreferences]);

  const buildExplicitAuthHeaders = useCallback(() => {
    if (typeof window === 'undefined') return {};
    try {
      const token = window.localStorage.getItem('session_token') || '';
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch {
      return {};
    }
  }, []);

  const refreshAdminVisualTheme = useCallback(async () => {
    try {
      const response = await api.get('/videos/admin/visual-theme', { headers: buildExplicitAuthHeaders() });
      const nextTheme = response?.data?.visual_theme || null;
      setAdminVisualTheme(nextTheme);
      const pack = String(nextTheme?.default_style_pack || 'cinematic') as StylePackOption;
      setAdminSelectedStylePack(pack);
    } catch (error) { handleAppRecoverableError({ scope: 'features/watch-videos.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [buildExplicitAuthHeaders]);

  const refreshObservability = useCallback(async () => {
    if (!bootstrap?.can_admin_visuals) return;
    setObservabilityLoading(true);
    try {
      const response = await api.get('/videos/admin/observability?lookback_days=7', { headers: buildExplicitAuthHeaders() });
      const payload = response?.data || null;
      setObservabilitySnapshot(payload);
    } catch (error) { handleAppRecoverableError({ scope: 'features/watch-videos.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally {
      setObservabilityLoading(false);
    }
  }, [bootstrap?.can_admin_visuals, buildExplicitAuthHeaders]);

  const applyAdminStylePack = useCallback(async () => {
    if (!bootstrap?.can_admin_visuals) return;
    setAdminApplyingTheme(true);
    try {
      await api.post('/videos/admin/style-pack', {
        category: adminSelectedCategory,
        style_pack: adminSelectedStylePack,
      }, { headers: buildExplicitAuthHeaders() });
      const snapshot = await api.get('/videos/bootstrap');
      const payload: BootstrapPayload = snapshot.data;
      setBootstrap(payload);
      setSelectedVideo(payload.selected_video || payload.featured_video || payload.trending_now?.[0] || null);
      await refreshAdminVisualTheme();
      Alert.alert('Style pack updated', `Applied ${adminSelectedStylePack} to ${adminSelectedCategory}.`);
    } catch (error: any) {
      Alert.alert('Unable to update style pack', error?.response?.data?.detail || 'Please try again.');
    } finally {
      setAdminApplyingTheme(false);
    }
  }, [adminSelectedCategory, adminSelectedStylePack, bootstrap?.can_admin_visuals, buildExplicitAuthHeaders, refreshAdminVisualTheme]);

  const regenerateVisualTheme = useCallback(async () => {
    if (!bootstrap?.can_admin_visuals) return;
    setAdminApplyingTheme(true);
    try {
      await api.post('/videos/admin/regenerate-visual-theme', { force_new_cycle: true }, { headers: buildExplicitAuthHeaders() });
      const snapshot = await api.get('/videos/bootstrap');
      const payload: BootstrapPayload = snapshot.data;
      setBootstrap(payload);
      setSelectedVideo(payload.selected_video || payload.featured_video || payload.trending_now?.[0] || null);
      await refreshAdminVisualTheme();
      Alert.alert('Visual theme regenerated', 'Fresh thumbnails are now applied across catalog.');
    } catch (error: any) {
      Alert.alert('Unable to regenerate theme', error?.response?.data?.detail || 'Please try again.');
    } finally {
      setAdminApplyingTheme(false);
    }
  }, [bootstrap?.can_admin_visuals, buildExplicitAuthHeaders, refreshAdminVisualTheme]);

  const loadBootstrap = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get('/videos/bootstrap');
      const payload: BootstrapPayload = response.data;
      setBootstrap(payload);
      setAdminVisualTheme(payload.can_admin_visuals ? (payload.visual_theme || null) : null);
      setObservabilitySnapshot(null);
      setFeedbackByVideo(payload.feedback_by_video || {});
      const prefs = { ...DEFAULT_VISUAL_PREFERENCES, ...(payload.visual_preferences || {}) };
      setVisualPreferences(prefs);
      setShowRecommendationReasons(Boolean(prefs.show_recommendation_reasons));
      setWatchlistSortMode(prefs.watchlist_sort_mode || 'recent');
      setWatchlistSortDirection(prefs.watchlist_sort_direction || 'desc');
      const watchMap: Record<string, boolean> = {};
      (payload.watchlist || []).forEach((video) => {
        if (video?.video_id) watchMap[video.video_id] = true;
      });
      setWatchlistByVideo(watchMap);
      setSelectedVideo(payload.selected_video || payload.featured_video || payload.trending_now?.[0] || null);
      if (payload.can_admin_visuals) {
        try {
          const obs = await api.get('/videos/admin/observability?lookback_days=7', { headers: buildExplicitAuthHeaders() });
          setObservabilitySnapshot(obs?.data || null);
        } catch (error) { handleAppRecoverableError({ scope: 'features/watch-videos.tsx#catch7', error, message: 'Something went wrong. Please retry.',
            notifyMode: 'silent',
          }); }
      }
    } catch (error: any) {
      Alert.alert('Unable to load Watch Videos', error?.response?.data?.detail || 'Please try again.');
    } finally {
      setLoading(false);
    }
  }, [buildExplicitAuthHeaders]);

  const loadCatalog = useCallback(async () => {
    const catalogQueryKey = `${searchQuery.trim()}|${selectedCategory}|${selectedSort}`;
    if (inFlightCatalogQueryRef.current === catalogQueryKey) return;
    if (lastLoadedCatalogQueryRef.current === catalogQueryKey) return;

    try {
      inFlightCatalogQueryRef.current = catalogQueryKey;
      setSearching(true);
      const params = new URLSearchParams();
      if (searchQuery.trim()) params.append('query', searchQuery.trim());
      if (selectedCategory !== 'all') params.append('category', selectedCategory);
      params.append('sort_by', selectedSort);
      params.append('limit', '90');
      const response = await api.get(`/videos/catalog?${params.toString()}`);
      const payload: CatalogPayload = response.data;
      setCatalogState(payload);
      setBootstrap((prev) => {
        if (!prev) return prev;
        if (isSameQuota(prev.quota, payload.quota)) return prev;
        return { ...prev, quota: payload.quota };
      });
      lastLoadedCatalogQueryRef.current = catalogQueryKey;
    } catch {
      setCatalogState((prev) => prev || { quota: DEFAULT_QUOTA_PAYLOAD, total: 0, has_more: false, sort_by: selectedSort, items: [] });
    } finally {
      if (inFlightCatalogQueryRef.current === catalogQueryKey) {
        inFlightCatalogQueryRef.current = '';
      }
      setSearching(false);
    }
  }, [searchQuery, selectedCategory, selectedSort]);

  useEffect(() => {
    lastLoadedCatalogQueryRef.current = '';
  }, [searchQuery, selectedCategory, selectedSort]);

  useEffect(() => {
    loadBootstrap();
  }, [loadBootstrap]);

  useEffect(() => {
    const handle = setTimeout(() => {
      void loadCatalog();
    }, 260);
    return () => clearTimeout(handle);
  }, [loadCatalog]);

  useEffect(() => {
    if (loading) {
      setShowContentReadyTransition(false);
      contentReadyOpacity.setValue(0);
      skeletonDissolveOpacity.setValue(1);
      return;
    }

    setShowContentReadyTransition(true);
    contentReadyOpacity.setValue(0);
    skeletonDissolveOpacity.setValue(1);

    const transition = Animated.parallel([
      Animated.timing(contentReadyOpacity, {
        toValue: 1,
        duration: 420,
        useNativeDriver: true,
      }),
      Animated.timing(skeletonDissolveOpacity, {
        toValue: 0,
        duration: 460,
        useNativeDriver: true,
      }),
    ]);

    transition.start(({ finished }) => {
      if (finished) {
        setShowContentReadyTransition(false);
      }
    });

    return () => {
      transition.stop();
    };
  }, [contentReadyOpacity, loading, skeletonDissolveOpacity]);

  const focusPlayerCard = useCallback(() => {
    try {
      if (!scrollRef.current) return;
      scrollRef.current.scrollTo({ y: Math.max(0, playerCardOffsetY - 18), animated: true });
    } catch (error) { handleAppRecoverableError({ scope: 'features/watch-videos.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [playerCardOffsetY]);

  const playVideo = useCallback(async (video: VideoItem, source: string) => {
    const sourceMeta = resolvePlaybackSource(video, Boolean(forceFallbackPlaybackByVideo[video.video_id]));
    try {
      if (!sourceMeta.can_play) {
        setUnavailableVideoIds((prev) => ({ ...prev, [video.video_id]: true }));
        throw new Error('Video URL unavailable');
      }

      if (source.startsWith('autoplay') && unavailableVideoIds[video.video_id]) {
        throw new Error('Video URL previously marked unavailable');
      }

      setPlayingVideoId(video.video_id);
      const payload = {
        video_id: video.video_id,
        progress_seconds: Math.max(0, Number(video.progress_seconds || 0)),
        duration_seconds: Math.max(0, Number(video.duration_seconds || 0)),
        completed: Boolean(video.completed),
        source,
      };
      const response = await api.post('/videos/watch', payload);
      const serverVideo: VideoItem = response?.data?.video || video;
      setForceFallbackPlaybackByVideo((prev) => {
        if (!prev[video.video_id]) return prev;
        const next = { ...prev };
        delete next[video.video_id];
        return next;
      });
      setYoutubeLoadedVideoId('');
      setSelectedVideo(serverVideo);
      setPlayIntentNonce((prev) => prev + 1);
      focusPlayerCard();
      updateLocalVideoState(video.video_id, {
        progress_seconds: Number(response?.data?.history?.progress_seconds || serverVideo.progress_seconds || 0),
        completed: Boolean(response?.data?.history?.completed || serverVideo.completed),
        view_count: Number(serverVideo.view_count || video.view_count || 0),
      });
      setCatalogState((prev) => (prev ? { ...prev, quota: response?.data?.quota || prev.quota } : prev));
      setBootstrap((prev) => (prev ? { ...prev, quota: response?.data?.quota || prev.quota } : prev));
    } catch (error: any) {
      const fallbackPool = [
        ...(bootstrap?.continue_queue || bootstrap?.continue_watching || []),
        ...(bootstrap?.trending_now || []),
        ...(catalogState?.items || bootstrap?.catalog || []),
      ];
      const fallbackVideo = fallbackPool.find((candidate) => {
        if (!candidate || candidate.video_id === video.video_id) return false;
        if (unavailableVideoIds[candidate.video_id]) return false;
        return resolvePlaybackSource(candidate, Boolean(forceFallbackPlaybackByVideo[candidate.video_id])).can_play;
      }) || null;

      if (fallbackVideo && !String(source || '').includes('fallback')) {
        Alert.alert('Primary source unavailable', 'Switched to another playable video automatically.');
        await playVideo(fallbackVideo, `${source}_fallback`);
        return;
      }

      if (!String(source || '').startsWith('autoplay')) {
        Alert.alert('Unable to play video', error?.response?.data?.detail || 'Plan cap reached or video unavailable.');
      }
    } finally {
      setPlayingVideoId('');
    }
  }, [
    bootstrap?.catalog,
    bootstrap?.continue_queue,
    bootstrap?.continue_watching,
    bootstrap?.trending_now,
    catalogState?.items,
    focusPlayerCard,
    forceFallbackPlaybackByVideo,
    unavailableVideoIds,
    updateLocalVideoState,
  ]);

  const toggleWatchlist = useCallback(async (videoId: string) => {
    const previousWatchlisted = Boolean(watchlistByVideo[videoId]);
    try {
      const shouldAdd = !previousWatchlisted;
      setWatchlistByVideo((prev) => ({ ...prev, [videoId]: shouldAdd }));
      updateLocalVideoState(videoId, { watchlisted: shouldAdd });

      const response = await api.post(
        `/videos/watchlist/toggle?sort_mode=${watchlistSortMode}&sort_dir=${watchlistSortDirection}`,
        {
        video_id: videoId,
        action: 'toggle',
        },
      );
      const payload = response?.data || {};
      const nextWatchlisted = Boolean(payload.watchlisted);
      setWatchlistByVideo((prev) => {
        const next = { ...prev };
        if (nextWatchlisted) {
          next[videoId] = true;
        } else {
          delete next[videoId];
        }
        return next;
      });
      updateLocalVideoState(videoId, { watchlisted: nextWatchlisted });

      setBootstrap((prev) => prev ? {
        ...prev,
        watchlist: Array.isArray(payload.watchlist) ? payload.watchlist : (prev.watchlist || []),
        continue_queue: Array.isArray(payload.continue_queue) ? payload.continue_queue : (prev.continue_queue || prev.continue_watching || []),
        queue_shortcuts: {
          ...(prev.queue_shortcuts || {
            watchlist_count: (prev.watchlist || []).length,
            continue_count: (prev.continue_queue || prev.continue_watching || []).length,
            watchlist_first_video_id: '',
            continue_first_video_id: '',
          }),
          watchlist_count: Number(payload.watchlist_count || 0),
          watchlist_first_video_id: String(payload.watchlist?.[0]?.video_id || ''),
          continue_count: Array.isArray(payload.continue_queue) ? payload.continue_queue.length : Number(prev.queue_shortcuts?.continue_count || 0),
          continue_first_video_id: String(payload.continue_queue?.[0]?.video_id || prev.queue_shortcuts?.continue_first_video_id || ''),
          queue_insight: payload.queue_insight || prev.queue_shortcuts?.queue_insight,
        },
      } : prev);
    } catch {
      setWatchlistByVideo((prev) => {
        const next = { ...prev };
        if (previousWatchlisted) {
          next[videoId] = true;
        } else {
          delete next[videoId];
        }
        return next;
      });
      updateLocalVideoState(videoId, { watchlisted: previousWatchlisted });
      Alert.alert('Unable to update watchlist', 'Please try again.');
    }
  }, [watchlistByVideo, watchlistSortDirection, watchlistSortMode, updateLocalVideoState]);

  const syncProgress = useCallback(async (forceComplete: boolean = false) => {
    if (Platform.OS !== 'web' || !videoRef.current || !selectedVideoRef.current) return;
    const currentVideo = selectedVideoRef.current;
    const element = videoRef.current;
    const current = Math.max(0, Math.floor(element.currentTime || 0));
    const duration = Math.max(0, Math.floor(element.duration || currentVideo.duration_seconds || 0));
    const completed = forceComplete || Boolean(currentVideo.completed) || (duration > 0 && current >= duration - 1);

    if (!forceComplete && current < PROGRESS_SYNC_INTERVAL_SECONDS && lastSyncedRef.current === 0) return;
    if (!forceComplete && Math.abs(current - lastSyncedRef.current) < PROGRESS_SYNC_INTERVAL_SECONDS) return;

    try {
      setSavingProgress(true);
      const response = await api.post('/videos/watch', {
        video_id: currentVideo.video_id,
        progress_seconds: current,
        duration_seconds: duration,
        completed,
        source: forceComplete ? 'player_end' : 'player_progress',
      });
      lastSyncedRef.current = current;
      const nextProgress = Number(response?.data?.history?.progress_seconds || current);
      const nextCompleted = Boolean(response?.data?.history?.completed || completed);
      updateLocalVideoState(currentVideo.video_id, { progress_seconds: nextProgress, completed: nextCompleted });
      setCatalogState((prev) => (prev ? { ...prev, quota: response?.data?.quota || prev.quota } : prev));
      setBootstrap((prev) => (prev ? { ...prev, quota: response?.data?.quota || prev.quota } : prev));
    } catch (error) { handleAppRecoverableError({ scope: 'features/watch-videos.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setSavingProgress(false);
    }
  }, [updateLocalVideoState]);

  const handleFeedback = useCallback(async (
    videoId: string,
    feedback: 'like' | 'dislike' | 'clear',
    showUndo = false,
    previousOverride?: string,
  ) => {
    const previous = previousOverride ?? feedbackByVideo[videoId] ?? 'clear';

    setFeedbackByVideo((prev) => {
      const next = { ...prev };
      if (feedback === 'clear') {
        delete next[videoId];
      } else {
        next[videoId] = feedback;
      }
      return next;
    });

    updateLocalVideoState(videoId, {
      feedback: feedback === 'clear' ? '' : feedback,
    });

    try {
      const response = await api.post('/videos/feedback', { video_id: videoId, feedback });
      const serverFeedbackMap = response?.data?.feedback_by_video || {};
      if (serverFeedbackMap && typeof serverFeedbackMap === 'object') {
        setFeedbackByVideo(serverFeedbackMap);
      }
      if (Array.isArray(response?.data?.recommended_for_you)) {
        setBootstrap((prev) => prev ? { ...prev, recommended_for_you: response.data.recommended_for_you } : prev);
      }

      if (showUndo && feedback !== 'clear') {
        if (undoFeedbackTimerRef.current) clearTimeout(undoFeedbackTimerRef.current);
        setUndoFeedbackToast({
          videoId,
          previousFeedback: previous,
          nextFeedback: feedback,
        });
        undoFeedbackTimerRef.current = setTimeout(() => {
          setUndoFeedbackToast(null);
        }, 6000);
      }
    } catch {
      setFeedbackByVideo((prev) => {
        const next = { ...prev };
        if (previous && previous !== 'clear') {
          next[videoId] = previous;
        } else {
          delete next[videoId];
        }
        return next;
      });
      updateLocalVideoState(videoId, { feedback: previous === 'clear' ? '' : previous });
      Alert.alert('Unable to save feedback', 'Please try again.');
    }
  }, [feedbackByVideo, updateLocalVideoState]);

  const undoFeedback = useCallback(async () => {
    if (!undoFeedbackToast) return;
    const rollback = undoFeedbackToast.previousFeedback === 'clear'
      ? 'clear'
      : (undoFeedbackToast.previousFeedback as 'like' | 'dislike');
    const previousForRollback = undoFeedbackToast.nextFeedback;
    setUndoFeedbackToast(null);
    if (undoFeedbackTimerRef.current) clearTimeout(undoFeedbackTimerRef.current);
    await handleFeedback(undoFeedbackToast.videoId, rollback, false, previousForRollback);
  }, [handleFeedback, undoFeedbackToast]);

  const openExternal = useCallback(async () => {
    if (!selectedVideo) return;
    const sourceMeta = resolvePlaybackSource(selectedVideo, Boolean(forceFallbackPlaybackByVideo[selectedVideo.video_id]));
    const watchUrl = selectedVideo.youtube_video_id
      ? `https://www.youtube.com/watch?v=${selectedVideo.youtube_video_id}`
      : sourceMeta.primary_url;
    if (!watchUrl) return;
    try {
      await Linking.openURL(watchUrl);
    } catch {
      Alert.alert('Unable to open video URL', 'Please try again in a moment.');
    }
  }, [forceFallbackPlaybackByVideo, selectedVideo]);

  const displayGridItems = useMemo(() => {
    if (searchQuery.trim() || selectedCategory !== 'all') {
      return catalogState?.items || [];
    }
    if (activeFeed === 'trending') return bootstrap?.trending_now || catalogState?.items || [];
    if (activeFeed === 'new') return bootstrap?.new_releases || catalogState?.items || [];
    if (activeFeed === 'library') return bootstrap?.catalog || catalogState?.items || [];
    return catalogState?.items || bootstrap?.catalog || [];
  }, [activeFeed, bootstrap?.catalog, bootstrap?.new_releases, bootstrap?.trending_now, catalogState?.items, searchQuery, selectedCategory]);

  const featured = selectedVideo || bootstrap?.featured_video || bootstrap?.trending_now?.[0] || null;
  const watchlistItems = bootstrap?.watchlist || [];
  const continueQueueItems = bootstrap?.continue_queue || bootstrap?.continue_watching || [];
  const sagaResumeItem = bootstrap?.saga_resume_item || null;
  const retentionProfile = bootstrap?.retention_profile || null;
  const sagaResumeVideo = sagaResumeItem?.resume_video || null;
  const officialSpotlightItems = useMemo(() => {
    const source = bootstrap?.catalog || [];
    return source
      .filter((video) => {
        const badge = String(video?.source_trust_badge || '').toLowerCase();
        const label = String(video?.source_label || '').toLowerCase();
        return badge.includes('official') || label.includes('official') || label.includes('youtube');
      })
      .slice(0, 30);
  }, [bootstrap?.catalog]);
  const sagaContinuityGroups = useMemo(() => {
    const source = (bootstrap?.catalog || []) as VideoItem[];
    const bySaga: Record<string, VideoItem[]> = {};
    for (const item of source) {
      const key = String(item?.saga_key || '').trim();
      if (!key) continue;
      if (!bySaga[key]) bySaga[key] = [];
      bySaga[key].push(item);
    }
    return Object.entries(bySaga)
      .map(([key, items]) => {
        const ordered = [...items].sort((a, b) => Number(a.saga_order || 1) - Number(b.saga_order || 1));
        return {
          key,
          name: String(ordered[0]?.saga_name || 'Saga Continuity'),
          recap: String(ordered[0]?.spoiler_safe_recap || 'Recap: continue your saga with spoiler-safe momentum.'),
          items: ordered.slice(0, 12),
        };
      })
      .filter((group) => group.items.length >= 3)
      .sort((a, b) => b.items.length - a.items.length)
      .slice(0, 4);
  }, [bootstrap?.catalog]);
  const autoplayNextEnabled = Boolean(visualPreferences.autoplay_next_enabled);
  const sortedWatchlistItems = useMemo(() => {
    const base = [...watchlistItems];

    const applyDirection = (rows: VideoItem[]) => {
      if (watchlistSortDirection === 'asc') {
        return [...rows].reverse();
      }
      return rows;
    };

    if (watchlistSortMode === 'duration') {
      const rows = base.sort((a, b) => Number(b.duration_seconds || 0) - Number(a.duration_seconds || 0));
      return applyDirection(rows);
    }
    if (watchlistSortMode === 'category') {
      const rows = base.sort((a, b) => `${a.category} ${a.title}`.localeCompare(`${b.category} ${b.title}`));
      return watchlistSortDirection === 'asc' ? rows : rows.reverse();
    }
    return applyDirection(base);
  }, [watchlistItems, watchlistSortDirection, watchlistSortMode]);

  const playWatchlistShortcut = useCallback(async () => {
    const first = sortedWatchlistItems[0];
    if (!first) {
      Alert.alert('Watchlist is empty', 'Save a video to your watchlist first.');
      return;
    }
    await playVideo(first, 'hero_watchlist_shortcut');
  }, [playVideo, sortedWatchlistItems]);

  const playContinueShortcut = useCallback(async () => {
    const first = continueQueueItems[0];
    if (!first) {
      Alert.alert('No continue queue yet', 'Start watching a video and it will appear here.');
      return;
    }
    await playVideo(first, 'hero_continue_queue_shortcut');
  }, [continueQueueItems, playVideo]);

  const playResumeSagaShortcut = useCallback(async () => {
    if (!sagaResumeVideo) {
      Alert.alert('No saga to resume yet', 'Watch at least one saga title to unlock Resume Saga.');
      return;
    }
    await playVideo(sagaResumeVideo, 'hero_resume_saga_shortcut');
  }, [playVideo, sagaResumeVideo]);

  const nextUpVideo = useMemo(() => {
    if (!selectedVideo) return null;
    const queue = continueQueueItems.length > 0 ? continueQueueItems : (bootstrap?.catalog || []);
    if (!queue.length) return null;
    const currentIndex = queue.findIndex((item) => item.video_id === selectedVideo.video_id);
    const orderedCandidates = [
      ...queue.slice(currentIndex + 1),
      ...queue.slice(0, Math.max(0, currentIndex)),
    ];
    return orderedCandidates.find((candidate) => (
      candidate
      && candidate.video_id !== selectedVideo.video_id
      && resolvePlaybackSource(candidate, Boolean(forceFallbackPlaybackByVideo[candidate.video_id])).can_play
      && !unavailableVideoIds[candidate.video_id]
    )) || null;
  }, [bootstrap?.catalog, continueQueueItems, forceFallbackPlaybackByVideo, selectedVideo, unavailableVideoIds]);

  const nextUpEtaSeconds = useMemo(() => {
    if (!selectedVideo || !nextUpVideo) return 0;
    const duration = Math.max(0, Number(selectedVideo.duration_seconds || 0));
    const current = Math.max(0, Number(currentPlaybackSeconds || selectedVideo.progress_seconds || 0));
    return Math.max(0, Math.floor(duration - current));
  }, [currentPlaybackSeconds, nextUpVideo, selectedVideo]);

  const playNextInQueue = useCallback(async () => {
    if (!autoplayNextEnabled || !nextUpVideo) return;
    await playVideo(nextUpVideo, 'autoplay_next_queue');
  }, [autoplayNextEnabled, nextUpVideo, playVideo]);

  const skipToNextNow = useCallback(async () => {
    if (!nextUpVideo) {
      Alert.alert('No next video', 'No eligible next item is available in your queue.');
      return;
    }
    await playVideo(nextUpVideo, 'skip_to_next');
  }, [nextUpVideo, playVideo]);

  const toggleAutoplayNext = useCallback(() => {
    const next = !autoplayNextEnabled;
    applyVisualPreferencePatch({ autoplay_next_enabled: next });
  }, [applyVisualPreferencePatch, autoplayNextEnabled]);

  const setFeedTab = useCallback((tab: FeedTab) => {
    setActiveFeed(tab);
    if (tab === 'trending') setSelectedSort('trending');
    if (tab === 'new') setSelectedSort('latest');
    if (tab === 'library') setSelectedSort('alphabetical');
    if (tab === 'home') setSelectedSort('latest');
  }, []);

  const selectedPlayback = useMemo(() => {
    if (!selectedVideo) {
      return resolvePlaybackSource(null);
    }
    return resolvePlaybackSource(selectedVideo, Boolean(forceFallbackPlaybackByVideo[selectedVideo.video_id]));
  }, [forceFallbackPlaybackByVideo, selectedVideo]);

  useEffect(() => {
    if (Platform.OS !== 'web' || selectedPlayback.primary_kind !== 'mp4' || !videoRef.current) return;
    const timer = setTimeout(() => {
      try {
        const promise = videoRef.current?.play?.();
        if (promise && typeof promise.catch === 'function') {
          promise.catch(() => {
            // browser autoplay gate; user can use controls
          });
        }
      } catch (error) { handleAppRecoverableError({ scope: 'features/watch-videos.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }, 120);
    return () => clearTimeout(timer);
  }, [playIntentNonce, selectedPlayback.primary_kind, selectedVideo?.video_id]);

  useEffect(() => {
    if (Platform.OS !== 'web' || !selectedVideo?.video_id) return;
    if (selectedPlayback.primary_kind !== 'youtube') return;
    if (!selectedPlayback.fallback_url) return;
    if (youtubeLoadedVideoId === selectedVideo.video_id) return;

    const timer = setTimeout(() => {
      if (youtubeLoadedVideoId === selectedVideo.video_id) return;
      setForceFallbackPlaybackByVideo((prev) => ({ ...prev, [selectedVideo.video_id]: true }));
      Alert.alert('Primary source unavailable', 'Switched to backup stream for this video.');
      setPlayIntentNonce((prev) => prev + 1);
    }, 6000);

    return () => clearTimeout(timer);
  }, [selectedPlayback.fallback_url, selectedPlayback.primary_kind, selectedVideo?.video_id, youtubeLoadedVideoId]);

  if (loading) {
    return (
      <FeatureLayout
        feature="watch-videos"
        title="Watch Videos"
        subtitle=""
        icon="film"
        color={colors.primary}
        showActions={false}
        scanTabLabel="Audio Studio"
        chatTabLabel="My Podcasts"
        extraTabLabel="Sports"
        scanTabIcon="musical-notes"
        chatTabIcon="mic"
        extraTabIcon="american-football"
        extraContent={<AudioCatalogTab mode="sports" />}
      >
        <WatchVideosLoadingSkeleton colors={colors} baseCardStyle={baseCardStyle} width={width} />
      </FeatureLayout>
    );
  }

  return (
    <FeatureLayout
      feature="watch-videos"
      title="Watch Videos"
      subtitle=""
      icon="film"
      color={colors.primary}
      showActions={false}
      showTransparencyBanner={false}
      scanTabLabel="Audio Studio"
      chatTabLabel="My Podcasts"
      extraTabLabel="Sports"
      scanTabIcon="musical-notes"
      chatTabIcon="mic"
      extraTabIcon="american-football"
      scanContent={<AudioCatalogTab mode="audio_studio" />}
      chatContent={<AudioCatalogTab mode="podcasts" />}
      extraContent={<AudioCatalogTab mode="sports" />}
    >
      <View style={{ position: 'relative' }} data-testid="watch-videos-v2-content-ready-transition-root" testID="watch-videos-v2-content-ready-transition-root">
        {showContentReadyTransition ? (
          <Animated.View
            pointerEvents="none"
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              opacity: skeletonDissolveOpacity,
              zIndex: 5,
            }}
            data-testid="watch-videos-v2-content-ready-skeleton-overlay"
            testID="watch-videos-v2-content-ready-skeleton-overlay"
          >
            <WatchVideosLoadingSkeleton colors={colors} baseCardStyle={baseCardStyle} width={width} />
          </Animated.View>
        ) : null}

        <Animated.View
          style={{ opacity: showContentReadyTransition ? contentReadyOpacity : 1 }}
          data-testid="watch-videos-v2-content-ready-fade-container"
          testID="watch-videos-v2-content-ready-fade-container"
        >
          <ScrollView ref={(node) => { scrollRef.current = node; }} contentContainerStyle={{ paddingVertical: 14, paddingBottom: 28 }} data-testid="watch-videos-v2-scroll" testID="watch-videos-v2-scroll">
            <WatchVideosShell
              colors={colors}
              width={width}
              baseCardStyle={baseCardStyle}
              quota={quota}
              bootstrap={bootstrap}
              featured={featured}
              playingVideoId={playingVideoId}
              watchlistItems={watchlistItems}
              continueQueueItems={continueQueueItems}
              sagaResumeItem={sagaResumeItem}
              sagaResumeVideo={sagaResumeVideo}
              undoFeedbackToast={undoFeedbackToast}
              undoFeedback={undoFeedback}
              showRecommendationReasons={showRecommendationReasons}
              setShowRecommendationReasons={setShowRecommendationReasons}
              applyVisualPreferencePatch={applyVisualPreferencePatch}
              playVideo={playVideo}
              playWatchlistShortcut={playWatchlistShortcut}
              playContinueShortcut={playContinueShortcut}
              playResumeSagaShortcut={playResumeSagaShortcut}
              categories={categories}
              adminSelectedCategory={adminSelectedCategory}
              setAdminSelectedCategory={setAdminSelectedCategory}
              adminSelectedStylePack={adminSelectedStylePack}
              setAdminSelectedStylePack={setAdminSelectedStylePack}
              adminApplyingTheme={adminApplyingTheme}
              applyAdminStylePack={applyAdminStylePack}
              regenerateVisualTheme={regenerateVisualTheme}
              adminVisualTheme={adminVisualTheme}
              observabilitySnapshot={observabilitySnapshot}
              observabilityLoading={observabilityLoading}
              refreshObservability={refreshObservability}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
              searching={searching}
              activeFeed={activeFeed}
              setFeedTab={setFeedTab}
              selectedSort={selectedSort}
              setSelectedSort={setSelectedSort}
              selectedCategory={selectedCategory}
              setSelectedCategory={setSelectedCategory}
              feedTabs={FEED_TABS}
              sortOptions={SORT_OPTIONS}
            />

            <WatchVideosPlayerPane
              colors={colors}
              baseCardStyle={baseCardStyle}
              selectedVideo={selectedVideo}
              selectedPlayback={selectedPlayback}
              youtubeLoadedVideoId={youtubeLoadedVideoId}
              setYoutubeLoadedVideoId={setYoutubeLoadedVideoId}
              setForceFallbackPlaybackByVideo={setForceFallbackPlaybackByVideo}
              setPlayIntentNonce={setPlayIntentNonce}
              playIntentNonce={playIntentNonce}
              videoRef={videoRef}
              setCurrentPlaybackSeconds={setCurrentPlaybackSeconds}
              syncProgress={syncProgress}
              playNextInQueue={playNextInQueue}
              setUnavailableVideoIds={setUnavailableVideoIds}
              openExternal={openExternal}
              savingProgress={savingProgress}
              feedbackByVideo={feedbackByVideo}
              handleFeedback={handleFeedback}
              autoplayNextEnabled={autoplayNextEnabled}
              toggleAutoplayNext={toggleAutoplayNext}
              watchlistByVideo={watchlistByVideo}
              toggleWatchlist={toggleWatchlist}
              nextUpVideo={nextUpVideo}
              nextUpEtaSeconds={nextUpEtaSeconds}
              skipToNextNow={skipToNextNow}
              formatDuration={formatDuration}
              compactNumber={compactNumber}
              setPlayerCardOffsetY={setPlayerCardOffsetY}
            />

            <WatchVideosRecommendationPanel
              colors={colors}
              watchlistSortMode={watchlistSortMode}
              watchlistSortDirection={watchlistSortDirection}
              setWatchlistSortMode={setWatchlistSortMode}
              setWatchlistSortDirection={setWatchlistSortDirection}
              applyVisualPreferencePatch={applyVisualPreferencePatch}
              sagaContinuityGroups={sagaContinuityGroups}
              recommendedItems={bootstrap?.recommended_for_you || []}
              quotaPlan={quota.plan}
              lockReasonByVideo={lockReasonByVideo}
              showBlockedCardTooltip={showBlockedCardTooltip}
              playVideo={playVideo}
              getPlanLockReasonForVideo={getPlanLockReasonForVideo}
            />

            <WatchVideosRetentionPanel
              colors={colors}
              baseCardStyle={baseCardStyle}
              continueQueueItems={continueQueueItems}
              watchlistItems={watchlistItems}
              recommendedItems={bootstrap?.recommended_for_you || []}
              sagaResumeItem={sagaResumeItem}
              retentionProfile={retentionProfile}
              selectedVideo={selectedVideo}
              feedbackByVideo={feedbackByVideo}
              playVideo={playVideo}
            />

            <WatchVideosWatchlistPanel
              colors={colors}
              selectedVideo={selectedVideo}
              showRecommendationReasons={showRecommendationReasons}
              quotaPlan={quota.plan}
              lockReasonByVideo={lockReasonByVideo}
              showBlockedCardTooltip={showBlockedCardTooltip}
              handleUpgradeFromLockedCard={handleUpgradeFromLockedCard}
              playVideo={playVideo}
              sortedWatchlistItems={sortedWatchlistItems}
              continueWatchingItems={bootstrap?.continue_watching || []}
              recommendedItems={bootstrap?.recommended_for_you || []}
              officialSpotlightItems={officialSpotlightItems}
              trendingItems={bootstrap?.trending_now || []}
              todayDropItems={bootstrap?.today_drop || []}
              categoryRows={bootstrap?.category_rows || {}}
            />

            <WatchVideosCatalogGrid
              colors={colors}
              baseCardStyle={baseCardStyle}
              displayGridItems={displayGridItems}
              selectedVideo={selectedVideo}
              gridCardWidth={gridCardWidth}
              gridColumns={gridColumns}
              activeFeed={activeFeed}
              showRecommendationReasons={showRecommendationReasons}
              lockReasonByVideo={lockReasonByVideo}
              watchlistByVideo={watchlistByVideo}
              categoryAccentColor={categoryAccentColor}
              getPlanLockReasonForVideo={getPlanLockReasonForVideo}
              quotaPlan={quota.plan}
              toggleWatchlist={toggleWatchlist}
              playVideo={playVideo}
              showBlockedCardTooltip={showBlockedCardTooltip}
              handleUpgradeFromLockedCard={handleUpgradeFromLockedCard}
              compactNumber={compactNumber}
              ProgressiveImageBackground={ProgressiveImageBackground}
            />

          </ScrollView>
        </Animated.View>
      </View>
    </FeatureLayout>
  );
}
