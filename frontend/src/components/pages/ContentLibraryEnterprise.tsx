import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
  Share,
  Modal,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import AppShell from '../AppShell';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import { SevenDayComparisonRibbon } from '../insights/SevenDayComparisonRibbon';
import { DailyAutopromptCards } from '../insights/DailyAutopromptCards';
import { SectionProgressRail } from '../progress/SectionProgressRail';
import { useHybridPolling } from '../../hooks/useHybridPolling';
import { LibraryFilterPanel } from '../content-library/LibraryFilterPanel';
import { LibraryContentGrid } from '../content-library/LibraryContentGrid';

interface ContentItem {
  title: string;
  url: string;
  type: string;
  category: string;
  added_date: string;
  source?: string;
  content?: string;
  bookmarked?: boolean;
  ai_categorized?: boolean;
  score?: number;
  recency_rank?: number;
  affinity_rank?: number;
  bookmark_rank?: number;
  recommendation_reasons?: string[];
}

interface LibraryInsights {
  window_days: number;
  top_searched_topics: { topic: string; count: number }[];
  most_opened_type: { type: string; count: number } | null;
  bookmark_trend: {
    current_count: number;
    previous_count: number;
    delta: number;
    direction: 'up' | 'down' | 'flat';
    series: { date: string; count: number }[];
  };
  has_enough_activity: boolean;
}

interface LibrarySubscriptionGate {
  error: string;
  message: string;
  current_plan: string;
  required_plan: string;
  upgrade_url: string;
}

interface LibraryRolloutHoldback {
  message: string;
  rollout_percentage: number;
  bucket: number;
  reason: string;
}

interface LibraryEngagementLoop {
  window_days: number;
  streak_days: number;
  continue_item: {
    title: string;
    type: string;
    category: string;
    url: string;
    source?: string;
    last_opened_at: string;
  } | null;
  daily_mission: {
    target: { opens: number; bookmarks: number };
    progress: { opens: number; bookmarks: number };
    completed: boolean;
    adaptive_context?: {
      mode: 'baseline' | 'adaptive';
      history_days_used: number;
      active_days: number;
      consistency_ratio: number;
      weighted_avg: {
        opens: number;
        bookmarks: number;
      };
      baseline_target?: {
        opens: number;
        bookmarks: number;
      };
      target_delta?: {
        opens: number;
        bookmarks: number;
      };
      change_direction?: 'increased' | 'decreased' | 'stable' | 'adjusted';
      tone_profile?: 'free' | 'basic' | 'premium';
      change_reason_short?: string;
      change_reason_detail?: string[];
    };
  };
  weekly_summary?: {
    wins: number;
    misses: number;
    streak_risk: 'low' | 'medium' | 'high';
    current_streak: number;
  };
}

interface LibraryRecommendationTelemetry {
  window_days: number;
  events: {
    recommendation_reason_click: number;
    open_after_recommendation: number;
    bookmark_after_recommendation: number;
  };
  conversion: {
    open_after_reason_click_rate: number;
    bookmark_after_open_rate: number;
  };
  top_reasons: { reason: string; count: number }[];
}

interface AdminRecommendationTuning {
  window_days: number;
  plans_covered: string[];
  by_plan: Record<string, {
    events: {
      recommendation_reason_click: number;
      open_after_recommendation: number;
      bookmark_after_recommendation: number;
    };
    reason_level_conversion: {
      reason: string;
      clicks: number;
      opens: number;
      bookmarks: number;
      open_after_click_rate: number;
      bookmark_after_open_rate: number;
    }[];
  }>;
}

const CAT_COLORS: Record<string, string> = {
  productivity: 'var(--app-primary)',
  planning: 'var(--app-primary)',
  health: 'var(--app-success)',
  finance: 'var(--app-warning)',
  learning: 'var(--app-primary)',
  fitness: 'var(--app-error)',
  wellness: 'var(--app-primary)',
  'real-estate': 'var(--app-primary)',
  career: 'var(--app-warning)',
  travel: 'var(--app-primary)',
  personal: 'var(--app-primary)',
};

const toTitle = (value: string) => value.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

const formatDate = (value: string) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

export default function ContentLibraryScreen() {
  const { t } = useTranslation();
  t('i18n.route.content-library.probe');
  const tr = useCallback((txt: string) => t(txt), [t]);
  const { colors } = useTheme();
  const { user } = useAuth();
  const { width } = useWindowDimensions();

  const isMobile = width < 768;
  const isTablet = width >= 768 && width < 1200;
  const columns = width >= 1400 ? 3 : width >= 920 ? 2 : 1;
  const cardWidth = columns === 3 ? '32.2%' : columns === 2 ? '49%' : '100%';

  const TYPE_ICONS: Record<string, { icon: string; color: string }> = {
    article: { icon: 'newspaper', color: colors.primary },
    guide: { icon: 'book', color: colors.successText },
    template: { icon: 'grid', color: colors.accent },
    workout: { icon: 'barbell', color: colors.warningText },
    checklist: { icon: 'checkbox', color: colors.error },
    generated: { icon: 'sparkles', color: colors.accent },
  };

  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg,
    bgSoft: colors.bgSoft,
    card: colors.card,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
    primary: colors.primary,
  }), [colors]);

  const uid = user?.user_id || '';
  const normalizedUserPlan = String((user as any)?.subscription_plan || '').trim().toLowerCase();
  const isAdminUser = Boolean((user as any)?.is_admin);

  const [items, setItems] = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState<string[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [catFilter, setCatFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortBy, setSortBy] = useState<'recommended' | 'newest' | 'oldest'>('recommended');
  const [viewMode, setViewMode] = useState<'all' | 'bookmarked'>('all');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [bookmarkedSet, setBookmarkedSet] = useState<Set<string>>(new Set());
  const [showExportModal, setShowExportModal] = useState(false);
  const [showAdaptiveReasonModal, setShowAdaptiveReasonModal] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [toast, setToast] = useState('');
  const [libraryGate, setLibraryGate] = useState<LibrarySubscriptionGate | null>(null);
  const [rolloutHoldback, setRolloutHoldback] = useState<LibraryRolloutHoldback | null>(null);
  const [insights, setInsights] = useState<LibraryInsights | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [engagementLoop, setEngagementLoop] = useState<LibraryEngagementLoop | null>(null);
  const [telemetry, setTelemetry] = useState<LibraryRecommendationTelemetry | null>(null);
  const [adminTuning, setAdminTuning] = useState<AdminRecommendationTuning | null>(null);
  const [actionHistory, setActionHistory] = useState<any[]>([]);
  const [activeSection, setActiveSection] = useState('overview');
  const scrollRef = useRef<ScrollView | null>(null);
  const sectionOffsets = useRef<Record<string, number>>({});
  const fetchLibraryRef = useRef<(targetPage?: number, force?: boolean) => Promise<void>>(async () => {});
  const pageRef = useRef(1);
  const LIBRARY_POLL_MAX_INTERVAL_MS = 60000;
  const LIBRARY_POLL_MIN_INTERVAL_MS = 30000;

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2500);
  }, []);

  useEffect(() => {
    setLibraryGate(null);
    setRolloutHoldback(null);
  }, [uid]);

  useEffect(() => {
    if (!uid) return;

    if (!isAdminUser && normalizedUserPlan === 'free') {
      setRolloutHoldback(null);
      setLibraryGate({
        error: 'Subscription Required',
        message: tr('Library is available for Basic and Premium plans.'),
        current_plan: 'free',
        required_plan: 'basic',
        upgrade_url: '/subscription/plans',
      });
      setLoading(false);
      setItems([]);
      setTotal(0);
      setTotalPages(1);
      setPage(1);
      setCategories([]);
      setTypes([]);
      return;
    }

    setLibraryGate(null);
    setRolloutHoldback(null);
  }, [uid, isAdminUser, normalizedUserPlan, tr]);

  const logLibraryEvent = useCallback(async (action: string, details: Record<string, any> = {}) => {
    if (!uid) return;
    try {
      await api.post('/actions/log', {
        user_id: uid,
        feature_key: 'content-library',
        action,
        details,
      });
    } catch {
      return;
    }
  }, [uid]);

  const fetchLibraryInsights = useCallback(async () => {
    if (libraryGate || rolloutHoldback) {
      setInsights(null);
      setActionHistory([]);
      return;
    }
    if (!uid) {
      setInsights(null);
      return;
    }
    setInsightsLoading(true);
    try {
      const [response, historyResponse] = await Promise.all([
        api.get(`/content/library/insights/${uid}?days=7`),
        api.get(`/actions/history/${uid}?feature_key=content-library&limit=300`),
      ]);
      setInsights(response.data || null);
      setActionHistory(Array.isArray(historyResponse?.data?.history) ? historyResponse.data.history : []);
    } catch {
      setInsights(null);
      setActionHistory([]);
    } finally {
      setInsightsLoading(false);
    }
  }, [uid, libraryGate, rolloutHoldback]);

  const fetchEngagementLoop = useCallback(async () => {
    if (!uid || libraryGate || rolloutHoldback) {
      setEngagementLoop(null);
      setTelemetry(null);
      return;
    }
    try {
      const [loopResponse, telemetryResponse] = await Promise.all([
        api.get(`/content/library/engagement-loop/${uid}?days=30`),
        api.get(`/content/library/recommendation-telemetry/${uid}?days=14`),
      ]);
      setEngagementLoop(loopResponse?.data || null);
      setTelemetry(telemetryResponse?.data || null);

      if (user?.is_admin) {
        try {
          const tuningResponse = await api.get('/admin/content-library/recommendation-tuning?days=14');
          setAdminTuning(tuningResponse?.data || null);
        } catch {
          setAdminTuning(null);
        }
      } else {
        setAdminTuning(null);
      }
    } catch {
      setEngagementLoop(null);
      setTelemetry(null);
      setAdminTuning(null);
    }
  }, [uid, libraryGate, rolloutHoldback, user?.is_admin]);

  const extractLibraryGate = useCallback((error: any): LibrarySubscriptionGate | null => {
    const status = Number(error?.response?.status || 0);
    if (status !== 403) return null;

    const payload = error?.response?.data || {};
    const source = payload?.detail && typeof payload.detail === 'object' ? payload.detail : payload;
    const rawError = String(source?.error || '').trim();
    const normalizedError = rawError.toLowerCase().replace(/[\s-]+/g, '_');
    const isSubscriptionGate = normalizedError === 'subscription_required' || normalizedError === 'subscriptionrequired';
    if (!isSubscriptionGate) return null;

    return {
      error: rawError || 'Subscription Required',
      message: String(source?.message || tr('This feature requires a Basic plan or higher.')),
      current_plan: String(source?.current_plan || 'free'),
      required_plan: String(source?.required_plan || 'basic'),
      upgrade_url: String(source?.upgrade_url || '/subscription/plans'),
    };
  }, [tr]);

  const extractRolloutHoldback = useCallback((error: any): LibraryRolloutHoldback | null => {
    const status = Number(error?.response?.status || 0);
    if (status !== 423) return null;
    const payload = error?.response?.data || {};
    if (String(payload?.error || '').trim().toLowerCase() !== 'feature_rollout_holdback') return null;

    return {
      message: String(payload?.message || tr('Feature is in phased rollout. Please retry shortly.')),
      rollout_percentage: Number(payload?.rollout_percentage || 0),
      bucket: Number(payload?.bucket || 0),
      reason: String(payload?.reason || 'holdback'),
    };
  }, [tr]);

  const setSectionOffset = useCallback((id: string, y: number) => {
    sectionOffsets.current[id] = y;
  }, []);

  const scrollToSection = useCallback((id: string) => {
    const y = sectionOffsets.current[id];
    if (typeof y !== 'number') return;
    scrollRef.current?.scrollTo({ y: Math.max(y - 72, 0), animated: true });
  }, []);

  const onLibraryScroll = useCallback((e: any) => {
    const y = e?.nativeEvent?.contentOffset?.y || 0;
    const entries = Object.entries(sectionOffsets.current).sort((a, b) => a[1] - b[1]);
    let next = 'overview';
    for (const [id, top] of entries) {
      if (y + 120 >= top) next = id;
      else break;
    }
    if (next !== activeSection) setActiveSection(next);
  }, [activeSection]);

  const fetchLibrary = useCallback(async (targetPage = 1, force = false) => {
    if (!uid) {
      setLoading(false);
      return;
    }

    if ((libraryGate || rolloutHoldback) && !force) {
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(targetPage),
        per_page: '12',
        sort: sortBy,
      });
      if (uid) params.append('user_id', uid);
      if (query) params.append('q', query);
      if (catFilter !== 'all') params.append('category', catFilter);
      if (typeFilter !== 'all') params.append('type', typeFilter);
      if (viewMode === 'bookmarked') params.append('bookmarked_only', 'true');

      const res = await api.get(`/content/library?${params}`);
      const data = res.data || {};
      const nextItems: ContentItem[] = data.items || [];

      setItems(nextItems);
      setTotal(data.total || 0);
      setTotalPages(Math.max(data.total_pages || 1, 1));
      setPage(data.page || 1);
      setCategories(data.categories || []);
      setTypes(data.types || []);

      const fetchedBookmarkSet = new Set<string>();
      for (const entry of nextItems) {
        if (entry.bookmarked && entry.url) fetchedBookmarkSet.add(entry.url);
      }
      setBookmarkedSet(prev => {
        const merged = new Set(prev);
        for (const key of fetchedBookmarkSet) merged.add(key);
        return merged;
      });
      setLibraryGate(null);
      setRolloutHoldback(null);
    } catch (error: any) {
      const gate = extractLibraryGate(error);
      if (gate) {
        setLibraryGate(gate);
        setRolloutHoldback(null);
        setItems([]);
        setTotal(0);
        setTotalPages(1);
        setPage(1);
        setCategories([]);
        setTypes([]);
        return;
      }
      const holdback = extractRolloutHoldback(error);
      if (holdback) {
        setRolloutHoldback(holdback);
        setLibraryGate(null);
        setItems([]);
        setTotal(0);
        setTotalPages(1);
        setPage(1);
        setCategories([]);
        setTypes([]);
        return;
      }
      Alert.alert(tr('Error'), tr('Failed to load content library'));
    } finally {
      setLoading(false);
    }
  }, [uid, query, catFilter, typeFilter, sortBy, viewMode, tr, libraryGate, rolloutHoldback, extractLibraryGate, extractRolloutHoldback]);

  useEffect(() => {
    fetchLibraryRef.current = fetchLibrary;
  }, [fetchLibrary]);

  useEffect(() => {
    pageRef.current = page;
  }, [page]);

  useEffect(() => {
    if (libraryGate || rolloutHoldback) {
      setBookmarkedSet(new Set());
      return;
    }
    if (!uid) return;
    (async () => {
      try {
        const res = await api.get(`/content/bookmarks/${uid}`);
        const bookmarkIds = new Set((res.data.bookmarks || []).map((b: any) => b.content_id));
        setBookmarkedSet(bookmarkIds);
      } catch {
        setBookmarkedSet(new Set());
      }
    })();
  }, [uid, libraryGate, rolloutHoldback]);

  useEffect(() => {
    if (!uid || libraryGate || rolloutHoldback) return;
    fetchLibrary(1);
  }, [fetchLibrary, libraryGate, rolloutHoldback, uid]);

  useEffect(() => {
    if (!uid || libraryGate || rolloutHoldback) return;
    fetchLibraryInsights();
  }, [fetchLibraryInsights, libraryGate, rolloutHoldback, uid]);

  useEffect(() => {
    if (!uid || libraryGate || rolloutHoldback) return;
    fetchEngagementLoop();
  }, [fetchEngagementLoop, libraryGate, rolloutHoldback, uid]);

  useHybridPolling({
    enabled: Boolean(uid) && !libraryGate && !rolloutHoldback,
    errorScope: 'feature33/content-library/hybrid-refresh',
    onTick: async () => {
      await fetchLibraryRef.current(pageRef.current);
    },
    runOnMount: false,
    slowIntervalMs: LIBRARY_POLL_MAX_INTERVAL_MS,
    fastIntervalMs: LIBRARY_POLL_MIN_INTERVAL_MS,
    wsEnabled: false,
  });

  const handleSearch = () => {
    const normalizedQuery = searchInput.trim();
    setQuery(normalizedQuery);
    setPage(1);
    if (normalizedQuery) {
      logLibraryEvent('search', {
        query: normalizedQuery,
        category: catFilter,
        type: typeFilter,
        view_mode: viewMode,
      });
      fetchLibraryInsights();
    }
  };

  const handleResetFilters = () => {
    setSearchInput('');
    setQuery('');
    setCatFilter('all');
    setTypeFilter('all');
    setSortBy('recommended');
    setViewMode('all');
    setPage(1);
  };

  const handleToggleBookmark = async (item: ContentItem) => {
    if (!uid) {
      Alert.alert(tr('Login Required'), tr('Please login to bookmark content'));
      return;
    }
    const contentId = item.url;
    try {
      const res = await api.post('/content/bookmarks/toggle', {
        user_id: uid,
        content_id: contentId,
        title: item.title,
      });
      const isBookmarked = !!res.data?.bookmarked;
      setBookmarkedSet(prev => {
        const next = new Set(prev);
        if (isBookmarked) next.add(contentId);
        else next.delete(contentId);
        return next;
      });
      setItems(prev => prev.map(i => (i.url === contentId ? { ...i, bookmarked: isBookmarked } : i)));
      showToast(isBookmarked ? tr('Bookmarked!') : tr('Bookmark removed'));
      logLibraryEvent('bookmark_toggle', {
        content_id: contentId,
        title: item.title,
        type: item.type,
        category: item.category,
        bookmarked: isBookmarked,
      });
      fetchLibraryInsights();
      if (sortBy === 'recommended') {
        logLibraryEvent('bookmark_after_recommendation', {
          content_id: contentId,
          title: item.title,
          reasons: item.recommendation_reasons || [],
          score: item.score || 0,
        });
      }
      fetchEngagementLoop();
    } catch {
      Alert.alert(tr('Error'), tr('Failed to toggle bookmark'));
    }
  };

  const handleShareItem = async (item: ContentItem) => {
    if (!uid) {
      Alert.alert(tr('Login Required'));
      return;
    }
    try {
      const res = await api.post('/share/create', {
        user_id: uid,
        feature_key: 'content-library',
        content: `${item.title}\n\n${tr('Type')}: ${item.type}\n${tr('Category')}: ${item.category}\n\n${item.content || item.url}`,
        title: item.title,
        expires_in_hours: 72,
      });
      const baseUrl = Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.origin : 'https://realaicoach.app';
      const link = `${baseUrl}/shared/${res.data.token}`;
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(link);
        showToast(tr('Share link copied!'));
      } else {
        await Share.share({ message: link, title: item.title });
      }
      logLibraryEvent('share', { title: item.title, type: item.type, category: item.category });
    } catch {
      Alert.alert(tr('Error'), tr('Failed to create share link'));
    }
  };

  const handleOpenItem = (item: ContentItem) => {
    logLibraryEvent('open', {
      title: item.title,
      type: item.type,
      category: item.category,
      source: item.source || 'library',
    });
    if (sortBy === 'recommended') {
      logLibraryEvent('open_after_recommendation', {
        title: item.title,
        type: item.type,
        category: item.category,
        url: item.url,
        reasons: item.recommendation_reasons || [],
        score: item.score || 0,
      });
    }
    fetchLibraryInsights();
    fetchEngagementLoop();
    if (item.source === 'generated' || item.url.startsWith('generated:')) {
      Alert.alert(item.title, item.content || tr('No content'));
      return;
    }
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.open(item.url, '_blank', 'noopener,noreferrer');
    }
  };

  const handleExport = async (format: 'txt' | 'csv') => {
    setExporting(true);
    try {
      const resp = await api.post('/content/library/export', { items, format }, { responseType: 'blob' });
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const mimeMap: Record<string, string> = { csv: 'text/csv', txt: 'text/plain' };
        const blob = new Blob([resp.data], { type: mimeMap[format] });
        const link = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = link;
        anchor.download = `content_library.${format}`;
        anchor.click();
        URL.revokeObjectURL(link);
      }
      showToast(format === 'csv' ? tr('CSV exported!') : tr('TXT exported!'));
      logLibraryEvent('export', { format, item_count: items.length });
      setShowExportModal(false);
    } catch {
      Alert.alert(tr('Error'), tr('Export failed'));
    } finally {
      setExporting(false);
    }
  };

  const goToPage = (nextPage: number) => {
    if (nextPage < 1 || nextPage > totalPages) return;
    setPage(nextPage);
    fetchLibrary(nextPage);
  };

  const handleRecommendationReasonClick = useCallback((item: ContentItem, reason: string) => {
    logLibraryEvent('recommendation_reason_click', {
      reason,
      reasons: item.recommendation_reasons || [],
      score: item.score || 0,
      title: item.title,
      type: item.type,
      category: item.category,
      url: item.url,
    });
    const reasonLabel = reason === 'fresh'
      ? tr('Fresh content based on recency')
      : reason === 'matches_activity'
        ? tr('Matches your recent activity patterns')
        : reason === 'bookmarked'
          ? tr('You previously bookmarked similar content')
          : reason === 'saved_generated'
            ? tr('Based on your saved generated content')
            : tr('Recommended by your engagement profile');
    Alert.alert(tr('Why this was recommended'), reasonLabel);
    fetchEngagementLoop();
  }, [fetchEngagementLoop, logLibraryEvent, tr]);

  const handleExplainRecommendation = useCallback((item: ContentItem) => {
    const reasons = (item.recommendation_reasons || []).map((reason) => {
      if (reason === 'fresh') return tr('Fresh recency signal');
      if (reason === 'matches_activity') return tr('Behavior affinity signal');
      if (reason === 'bookmarked') return tr('Bookmark signal');
      if (reason === 'saved_generated') return tr('Saved generated signal');
      return tr('Recommendation signal');
    });

    const message = [
      `${tr('Score')}: ${Number(item.score || 0).toFixed(1)}`,
      `${tr('Recency')}: ${Number(item.recency_rank || 0).toFixed(1)}`,
      `${tr('Affinity')}: ${Number(item.affinity_rank || 0).toFixed(1)}`,
      `${tr('Bookmark boost')}: ${Number(item.bookmark_rank || 0).toFixed(1)}`,
      reasons.length ? `${tr('Signals')}: ${reasons.join(', ')}` : '',
    ].filter(Boolean).join('\n');

    Alert.alert(tr('Why this was recommended'), message || tr('Recommendation signals are being collected.'));
  }, [tr]);

  const metricCards = useMemo(() => ([
    {
      id: 'total',
      title: tr('Total Library Items'),
      value: `${total}`,
      icon: 'albums-outline',
      color: colors.primary,
      bg: colors.primarySoft,
      testId: 'library-metric-total-items',
    },
    {
      id: 'visible',
      title: tr('Visible in Current View'),
      value: `${items.length}`,
      icon: 'eye-outline',
      color: colors.info,
      bg: colors.infoSoft,
      testId: 'library-metric-visible-items',
    },
    {
      id: 'bookmarks',
      title: tr('Bookmarked Items'),
      value: `${bookmarkedSet.size}`,
      icon: 'bookmark-outline',
      color: colors.warning,
      bg: colors.warningSoft,
      testId: 'library-metric-bookmarked-items',
    },
    {
      id: 'classification',
      title: tr('Category / Type Coverage'),
      value: `${categories.length} / ${types.length}`,
      icon: 'pricetags-outline',
      color: colors.success,
      bg: colors.successSoft,
      testId: 'library-metric-coverage',
    },
  ]), [
    tr,
    total,
    items.length,
    bookmarkedSet.size,
    categories.length,
    types.length,
    colors.primary,
    colors.primarySoft,
    colors.info,
    colors.infoSoft,
    colors.warning,
    colors.warningSoft,
    colors.success,
    colors.successSoft,
  ]);

  const activeFiltersCount = [catFilter !== 'all', typeFilter !== 'all', query !== '', viewMode === 'bookmarked'].filter(Boolean).length;
  const generatedVisibleCount = useMemo(
    () => items.filter(item => item.source === 'generated' || (item.url || '').startsWith('generated:')).length,
    [items],
  );
  const aiTaggedVisibleCount = useMemo(
    () => items.filter(item => Boolean(item.ai_categorized)).length,
    [items],
  );
  const curatedVisibleCount = Math.max(items.length - generatedVisibleCount, 0);
  const topSearchedTopics = useMemo(() => insights?.top_searched_topics || [], [insights?.top_searched_topics]);
  const mostOpenedType = insights?.most_opened_type || null;
  const bookmarkSeries = insights?.bookmark_trend?.series || [];
  const maxBookmarkSeriesValue = Math.max(...bookmarkSeries.map(point => point.count), 1);
  const bookmarkDirection = insights?.bookmark_trend?.direction || 'flat';
  const bookmarkDelta = insights?.bookmark_trend?.delta || 0;
  const bookmarkTrendColor = bookmarkDirection === 'up' ? colors.success : bookmarkDirection === 'down' ? colors.error : C.textMuted;

  const bookmarkTrendLabel = bookmarkDirection === 'up'
    ? tr('Upward')
    : bookmarkDirection === 'down'
      ? tr('Downward')
      : tr('Flat');

  const sevenDayMetrics = useMemo(() => {
    const now = Date.now();
    const currentStart = now - (7 * 24 * 60 * 60 * 1000);
    const previousStart = now - (14 * 24 * 60 * 60 * 1000);

    let currentInteractions = 0;
    let previousInteractions = 0;
    let currentOpens = 0;
    let previousOpens = 0;
    let currentBookmarks = 0;
    let previousBookmarks = 0;

    for (const row of actionHistory) {
      const ts = new Date(row?.timestamp || '').getTime();
      if (!Number.isFinite(ts)) continue;
      const inCurrent = ts >= currentStart && ts <= now;
      const inPrevious = ts >= previousStart && ts < currentStart;
      if (!inCurrent && !inPrevious) continue;

      const action = String(row?.action || '').toLowerCase();
      if (inCurrent) {
        currentInteractions += 1;
        if (action === 'open') currentOpens += 1;
        if (action === 'bookmark_toggle') currentBookmarks += 1;
      } else {
        previousInteractions += 1;
        if (action === 'open') previousOpens += 1;
        if (action === 'bookmark_toggle') previousBookmarks += 1;
      }
    }

    return [
      { id: 'interactions', label: 'Interactions', current: currentInteractions, previous: previousInteractions },
      { id: 'opens', label: 'Content opens', current: currentOpens, previous: previousOpens },
      {
        id: 'bookmarks',
        label: 'Bookmark saves',
        current: Number(insights?.bookmark_trend?.current_count || currentBookmarks),
        previous: Number(insights?.bookmark_trend?.previous_count || previousBookmarks),
      },
    ];
  }, [actionHistory, insights]);

  const runAutopromptTopTopic = useCallback(async () => {
    const topic = String(topSearchedTopics?.[0]?.topic || '').trim();
    if (!topic) return;
    setSearchInput(topic);
    setQuery(topic);
    setPage(1);
    await logLibraryEvent('search', {
      query: topic,
      category: catFilter,
      type: typeFilter,
      view_mode: viewMode,
      source: 'daily_autoprompt',
    });
    await fetchLibrary(1);
    await fetchLibraryInsights();
  }, [topSearchedTopics, logLibraryEvent, catFilter, typeFilter, viewMode, fetchLibrary, fetchLibraryInsights]);

  const runAutopromptMostOpenedType = useCallback(async () => {
    const nextType = String(mostOpenedType?.type || '').trim();
    if (!nextType) return;
    setTypeFilter(nextType);
    setPage(1);
    await fetchLibrary(1);
  }, [mostOpenedType?.type, fetchLibrary]);

  const runAutopromptBookmarkReview = useCallback(async () => {
    setViewMode('bookmarked');
    setPage(1);
    await fetchLibrary(1);
    await fetchLibraryInsights();
  }, [fetchLibrary, fetchLibraryInsights]);

  const libraryAutopromptCards = useMemo(() => {
    const topTopic = String(topSearchedTopics?.[0]?.topic || '').trim();
    const openedType = String(mostOpenedType?.type || '').trim();
    const hasActiveFilters = [catFilter !== 'all', typeFilter !== 'all', query !== '', viewMode === 'bookmarked'].some(Boolean);

    return [
      {
        id: 'refresh-insights',
        title: 'Refresh behavior insights',
        description: 'Sync latest 7-day interaction signals before deciding your next content action.',
        ctaLabel: insightsLoading ? 'Refreshing…' : 'Refresh insights',
        onPress: fetchLibraryInsights,
        icon: 'refresh-outline',
      },
      topTopic
        ? {
            id: 'search-top-topic',
            title: 'Replay top search intent',
            description: `Your leading search topic is “${topTopic}”. Re-run it and pull the newest matching assets.`,
            ctaLabel: 'Search topic',
            onPress: runAutopromptTopTopic,
            icon: 'search-outline',
          }
        : openedType
          ? {
              id: 'focus-opened-type',
              title: 'Double down on top-opened format',
              description: `${toTitle(openedType)} is your most-opened type. Filter now to continue that momentum.`,
              ctaLabel: 'Filter type',
              onPress: runAutopromptMostOpenedType,
              icon: 'funnel-outline',
            }
          : {
              id: 'reset-discovery',
              title: 'Broaden discovery scope',
              description: 'No dominant topic yet. Reset filters and explore fresh assets from all categories.',
              ctaLabel: 'Reset view',
              onPress: () => {
                handleResetFilters();
                fetchLibrary(1);
              },
              icon: 'shuffle-outline',
            },
      bookmarkDirection === 'down'
        ? {
            id: 'recover-bookmarks',
            title: 'Recover bookmark momentum',
            description: 'Bookmark trend dipped this week. Switch to bookmarked mode and promote one useful asset.',
            ctaLabel: 'Review bookmarks',
            onPress: runAutopromptBookmarkReview,
            icon: 'bookmark-outline',
          }
        : {
            id: 'keep-curation-fresh',
            title: 'Keep curation sharp',
            description: hasActiveFilters
              ? 'You are in a narrowed view. Keep it, then open one additional item to feed better recommendations.'
              : 'Your trend is stable. Open one new item now to keep recommendations diverse and current.',
            ctaLabel: 'Open content set',
            onPress: () => scrollToSection('content'),
            icon: 'sparkles-outline',
          },
    ];
  }, [
    topSearchedTopics,
    mostOpenedType,
    catFilter,
    typeFilter,
    query,
    viewMode,
    insightsLoading,
    fetchLibraryInsights,
    runAutopromptTopTopic,
    runAutopromptMostOpenedType,
    bookmarkDirection,
    runAutopromptBookmarkReview,
    scrollToSection,
    fetchLibrary,
  ]);

  const showProgressRail = width >= 1460;

  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: 'transparent' }} edges={['top']} data-testid="content-library-screen" testID="content-library-screen">
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={{
            paddingHorizontal: isMobile ? 14 : 24,
            paddingVertical: isMobile ? 14 : 18,
            paddingBottom: 64,
          }}
          onScroll={onLibraryScroll}
          scrollEventThrottle={16}
          showsVerticalScrollIndicator={false}
          data-testid="content-library-scroll-root"
          testID="content-library-scroll-root"
        >
          <View style={{ width: '100%', maxWidth: 1240, alignSelf: 'center' }} data-testid="content-library-layout-wrap" testID="content-library-layout-wrap">
            <View
              onLayout={(e) => setSectionOffset('overview', e.nativeEvent.layout.y)}
              style={{
                backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(C.card, 'B2') : C.card,
                borderRadius: 18,
                borderWidth: 1,
                borderColor: C.border,
                padding: isMobile ? 14 : 20,
                marginBottom: 14,
                gap: 14,
                ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
                shadowColor: 'var(--app-text)',
                shadowOpacity: 0.06,
                shadowRadius: 10,
                shadowOffset: { width: 0, height: 4 },
                elevation: 2,
              }}
              data-testid="content-library-command-center"
              testID="content-library-command-center"
            >
              <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', justifyContent: 'space-between', gap: 12 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: isMobile ? 24 : 30, fontWeight: '900', color: C.text }} data-testid="content-library-title" testID="content-library-title">
                    {tr('Library Workspace')}
                  </Text>
                  <Text style={{ fontSize: 12, color: C.textMuted, marginTop: 4 }} data-testid="content-library-subtitle" testID="content-library-subtitle">
                    {tr('Enterprise view powered by live platform content data only')}
                  </Text>
                </View>

                <View style={{ flexDirection: isMobile ? 'row' : 'row', flexWrap: 'wrap', gap: 8 }}>
                  <TouchableOpacity accessibilityLabel="Content library refresh button"
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 6,
                      paddingHorizontal: 12,
                      paddingVertical: 10,
                      borderRadius: 999,
                      backgroundColor: colors.infoSoft,
                      borderWidth: 1,
                      borderColor: colors.infoSoft,
                    }}
                    onPress={() => {
                      setLibraryGate(null);
                      fetchLibrary(page, true);
                      fetchLibraryInsights();
                    }}
                    data-testid="content-library-refresh-btn"
                    testID="content-library-refresh-btn"
                    accessibilityRole="button"
                  >
                    <Ionicons name="refresh" size={15} color={colors.info} />
                    <Text style={{ fontSize: 11, fontWeight: '700', color: colors.info }}>{tr('Refresh')}</Text>
                  </TouchableOpacity>

                  <TouchableOpacity accessibilityLabel="Content library export button"
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 6,
                      paddingHorizontal: 12,
                      paddingVertical: 10,
                      borderRadius: 999,
                      backgroundColor: colors.successSoft,
                      borderWidth: 1,
                      borderColor: colors.successSoft,
                    }}
                    onPress={() => setShowExportModal(true)}
                    data-testid="content-library-export-btn"
                    testID="content-library-export-btn"
                    accessibilityRole="button"
                  >
                    <Ionicons name="download-outline" size={15} color={colors.successText} />
                    <Text style={{ fontSize: 11, fontWeight: '700', color: colors.successText }}>{tr('Export')}</Text>
                  </TouchableOpacity>
                </View>
              </View>

              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="content-library-live-state" testID="content-library-live-state">
                <Ionicons name={loading ? 'sync' : 'checkmark-circle'} size={14} color={loading ? colors.warning : colors.success} />
                <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="content-library-live-state-text" testID="content-library-live-state-text">
                  {loading ? tr('Syncing library data...') : tr('Library synced with latest platform records')}
                </Text>
              </View>

              {libraryGate && (
                <View
                  style={{
                    backgroundColor: colors.warningSoft,
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: colors.warning,
                    padding: 12,
                    gap: 8,
                  }}
                  data-testid="content-library-subscription-gate-card"
                  testID="content-library-subscription-gate-card"
                >
                  <Text
                    style={{ fontSize: 13, fontWeight: '800', color: colors.warningText }}
                    data-testid="content-library-subscription-gate-title"
                    testID="content-library-subscription-gate-title"
                  >
                    {tr('Upgrade Your Plan')}
                  </Text>
                  <Text
                    style={{ fontSize: 12, color: C.text }}
                    data-testid="content-library-subscription-gate-message"
                    testID="content-library-subscription-gate-message"
                  >
                    {libraryGate.message}
                  </Text>
                  <Text
                    style={{ fontSize: 11, color: C.textMuted }}
                    data-testid="content-library-subscription-gate-plan-detail"
                    testID="content-library-subscription-gate-plan-detail"
                  >
                    {`${tr('Current plan')}: ${toTitle(libraryGate.current_plan)} • ${tr('Required')}: ${toTitle(libraryGate.required_plan)}`}
                  </Text>
                  <TouchableOpacity
                    accessibilityRole="button"
                    onPress={() => {
                      const target = libraryGate.upgrade_url || '/subscription/plans';
                      if (Platform.OS === 'web' && typeof window !== 'undefined') {
                        window.location.href = target;
                        return;
                      }
                      Alert.alert(tr('Upgrade'), tr('Open the subscription plans page to upgrade your account.'));
                    }}
                    style={{
                      alignSelf: 'flex-start',
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 6,
                      borderRadius: 999,
                      paddingHorizontal: 12,
                      paddingVertical: 8,
                      backgroundColor: colors.warning,
                    }}
                    data-testid="content-library-subscription-gate-upgrade-button"
                    testID="content-library-subscription-gate-upgrade-button"
                  >
                    <Ionicons name="rocket-outline" size={13} color={colors.primaryText} />
                    <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>
                      {tr('Upgrade now')}
                    </Text>
                  </TouchableOpacity>
                </View>
              )}

              {rolloutHoldback && (
                <View
                  style={{
                    backgroundColor: colors.infoSoft,
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: colors.info,
                    padding: 12,
                    gap: 8,
                  }}
                  data-testid="content-library-rollout-holdback-card"
                  testID="content-library-rollout-holdback-card"
                >
                  <Text style={{ fontSize: 13, fontWeight: '800', color: colors.info }} data-testid="content-library-rollout-holdback-title" testID="content-library-rollout-holdback-title">
                    {tr('Phased rollout in progress')}
                  </Text>
                  <Text style={{ fontSize: 12, color: C.text }} data-testid="content-library-rollout-holdback-message" testID="content-library-rollout-holdback-message">
                    {rolloutHoldback.message}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="content-library-rollout-holdback-detail" testID="content-library-rollout-holdback-detail">
                    {`${tr('Current rollout')}: ${Math.max(0, rolloutHoldback.rollout_percentage)}% • ${tr('Bucket')}: ${Math.max(0, rolloutHoldback.bucket)}`}
                  </Text>
                  <TouchableOpacity
                    accessibilityRole="button"
                    onPress={() => {
                      setRolloutHoldback(null);
                      fetchLibrary(page, true);
                    }}
                    style={{
                      alignSelf: 'flex-start',
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 6,
                      borderRadius: 999,
                      paddingHorizontal: 12,
                      paddingVertical: 8,
                      backgroundColor: colors.info,
                    }}
                    data-testid="content-library-rollout-holdback-retry-button"
                    testID="content-library-rollout-holdback-retry-button"
                  >
                    <Ionicons name="refresh-outline" size={14} color={colors.primaryText} />
                    <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryText }}>{tr('Retry now')}</Text>
                  </TouchableOpacity>
                </View>
              )}

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="content-library-metrics-row" testID="content-library-metrics-row">
                {metricCards.map(metric => (
                  <View
                    key={metric.id}
                    style={{
                      flexGrow: 1,
                      minWidth: isMobile ? '46%' : isTablet ? '23%' : '23%',
                      backgroundColor: C.bgSoft,
                      borderRadius: 12,
                      borderWidth: 1,
                      borderColor: C.border,
                      padding: 12,
                      gap: 6,
                    }}
                    data-testid={metric.testId}
                    testID={metric.testId}
                  >
                    <View style={{ width: 28, height: 28, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: metric.bg }}>
                      <Ionicons name={metric.icon as any} size={14} color={metric.color} />
                    </View>
                    <Text style={{ fontSize: 10, color: C.textMuted }}>{metric.title}</Text>
                    <Text style={{ fontSize: 17, fontWeight: '900', color: C.text }}>{metric.value}</Text>
                  </View>
                ))}
              </View>

              <View
                style={{
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.bgSoft,
                  padding: 12,
                  gap: 10,
                }}
                data-testid="library-data-integrity-strip"
                testID="library-data-integrity-strip"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                  <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }} data-testid="library-data-integrity-title" testID="library-data-integrity-title">
                    Data Integrity & Source Mix
                  </Text>
                  <Text style={{ fontSize: 10, color: C.textMuted }} data-testid="library-data-integrity-subtitle" testID="library-data-integrity-subtitle">
                    Platform records only • No fabricated content
                  </Text>
                </View>

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {[
                    { key: 'curated', label: 'Curated Visible', value: curatedVisibleCount, tone: colors.info },
                    { key: 'generated', label: 'Generated Visible', value: generatedVisibleCount, tone: colors.successText },
                    { key: 'ai-tagged', label: 'AI Tagged Visible', value: aiTaggedVisibleCount, tone: colors.warningText },
                  ].map(metric => (
                    <View
                      key={metric.key}
                      style={{
                        minWidth: isMobile ? '47%' : 170,
                        flexGrow: 1,
                        borderRadius: 10,
                        borderWidth: 1,
                        borderColor: C.border,
                        backgroundColor: C.card,
                        padding: 10,
                      }}
                      data-testid={`library-integrity-metric-${metric.key}`}
                      testID={`library-integrity-metric-${metric.key}`}
                    >
                      <Text style={{ fontSize: 10, color: C.textMuted }}>{metric.label}</Text>
                      <Text style={{ fontSize: 14, fontWeight: '900', color: metric.tone, marginTop: 4 }}>{metric.value}</Text>
                    </View>
                  ))}
                </View>
              </View>
            </View>

            <View
              onLayout={(e) => setSectionOffset('insights', e.nativeEvent.layout.y)}
              style={{
                backgroundColor: C.card,
                borderRadius: 16,
                borderWidth: 1,
                borderColor: C.border,
                padding: isMobile ? 12 : 14,
                marginBottom: 14,
                gap: 12,
              }}
              data-testid="library-usage-insights-strip"
              testID="library-usage-insights-strip"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <View>
                  <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }} data-testid="library-usage-insights-title" testID="library-usage-insights-title">
                    {tr('Library Usage Insights')}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-usage-insights-subtitle" testID="library-usage-insights-subtitle">
                    {tr('Last 7 days, based on existing platform events')}
                  </Text>
                </View>
                <TouchableOpacity accessibilityLabel="Library usage insights refresh button"
                  onPress={fetchLibraryInsights}
                  style={{
                    paddingHorizontal: 10,
                    paddingVertical: 7,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: C.bgSoft,
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 5,
                  }}
                  data-testid="library-usage-insights-refresh-btn"
                  testID="library-usage-insights-refresh-btn"
                  accessibilityRole="button"
                >
                  {insightsLoading ? <ActivityIndicator size="small" color={C.textMuted} /> : <Ionicons name="refresh-outline" size={13} color={C.textMuted} />}
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.textMuted }}>{tr('Refresh')}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="library-usage-insights-cards" testID="library-usage-insights-cards">
                <View
                  style={{
                    flex: 1,
                    minWidth: isMobile ? '100%' : '31%',
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: C.bgSoft,
                    padding: 11,
                    gap: 7,
                  }}
                  data-testid="library-insight-top-searches"
                  testID="library-insight-top-searches"
                >
                  <Text style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>{tr('Top searched topics')}</Text>
                  {topSearchedTopics.length > 0 ? (
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                      {topSearchedTopics.slice(0, 3).map(topic => (
                        <View key={topic.topic} style={{ paddingHorizontal: 9, paddingVertical: 5, borderRadius: 999, backgroundColor: colors.infoSoft }}>
                          <Text style={{ fontSize: 10, fontWeight: '700', color: colors.info }}>{topic.topic} ({topic.count})</Text>
                        </View>
                      ))}
                    </View>
                  ) : (
                    <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-insight-top-searches-empty" testID="library-insight-top-searches-empty">
                      {tr('Not enough activity yet')}
                    </Text>
                  )}
                </View>

                <View
                  style={{
                    flex: 1,
                    minWidth: isMobile ? '100%' : '31%',
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: C.bgSoft,
                    padding: 11,
                    gap: 6,
                  }}
                  data-testid="library-insight-most-opened-type"
                  testID="library-insight-most-opened-type"
                >
                  <Text style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>{tr('Most opened content type')}</Text>
                  {mostOpenedType ? (
                    <>
                      <Text style={{ fontSize: 15, fontWeight: '900', color: C.text }}>{toTitle(mostOpenedType.type)}</Text>
                      <Text style={{ fontSize: 11, color: C.textMuted }}>{mostOpenedType.count} {tr('opens')}</Text>
                    </>
                  ) : (
                    <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-insight-most-opened-empty" testID="library-insight-most-opened-empty">
                      {tr('Not enough activity yet')}
                    </Text>
                  )}
                </View>

                <View
                  style={{
                    flex: 1,
                    minWidth: isMobile ? '100%' : '31%',
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: C.bgSoft,
                    padding: 11,
                    gap: 7,
                  }}
                  data-testid="library-insight-bookmark-trend"
                  testID="library-insight-bookmark-trend"
                >
                  <Text style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>{tr('Bookmark trend')}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons
                      name={bookmarkDirection === 'up' ? 'trending-up' : bookmarkDirection === 'down' ? 'trending-down' : 'remove'}
                      size={14}
                      color={bookmarkTrendColor}
                    />
                    <Text style={{ fontSize: 12, fontWeight: '800', color: bookmarkTrendColor }} data-testid="library-insight-bookmark-direction" testID="library-insight-bookmark-direction">
                      {bookmarkTrendLabel} ({bookmarkDelta >= 0 ? '+' : ''}{bookmarkDelta})
                    </Text>
                  </View>
                  {bookmarkSeries.length > 0 ? (
                    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3, minHeight: 24 }}>
                      {bookmarkSeries.map(point => (
                        <View
                          key={point.date}
                          style={{
                            width: 8,
                            height: 6 + Math.round((point.count / maxBookmarkSeriesValue) * 18),
                            borderRadius: 3,
                            backgroundColor: colors.primary,
                          }}
                        />
                      ))}
                    </View>
                  ) : (
                    <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-insight-bookmark-empty" testID="library-insight-bookmark-empty">
                      {tr('Not enough activity yet')}
                    </Text>
                  )}
                </View>
              </View>
            </View>

            <View onLayout={(e) => setSectionOffset('comparison', e.nativeEvent.layout.y)}>
              <SevenDayComparisonRibbon
                title="7-day comparison ribbon"
                subtitle="Current 7 days vs previous 7 days (library activity only)"
                metrics={sevenDayMetrics}
                colors={C}
                testIdPrefix="library-seven-day"
                onRefresh={fetchLibraryInsights}
                refreshing={insightsLoading}
              />
            </View>

            <View style={{ marginTop: 10, marginBottom: 14 }}>
              <DailyAutopromptCards
                title="Daily autoprompt cards"
                subtitle="Next best actions generated from your 7-day Library behavior"
                prompts={libraryAutopromptCards}
                colors={C}
                testIdPrefix="library-autoprompt"
              />
            </View>

            <View
              onLayout={(e) => setSectionOffset('retention', e.nativeEvent.layout.y)}
              style={{
                backgroundColor: C.card,
                borderRadius: 16,
                borderWidth: 1,
                borderColor: C.border,
                padding: isMobile ? 12 : 14,
                marginBottom: 14,
                gap: 12,
              }}
              data-testid="library-retention-loop-panel"
              testID="library-retention-loop-panel"
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <View>
                  <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }} data-testid="library-retention-title" testID="library-retention-title">
                    {tr('Continue where you left off')}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-retention-subtitle" testID="library-retention-subtitle">
                    {tr('Daily mission + streak loops to increase return behavior')}
                  </Text>
                </View>
                <TouchableOpacity
                  onPress={fetchEngagementLoop}
                  style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft }}
                  data-testid="library-retention-refresh-btn"
                  testID="library-retention-refresh-btn"
                  accessibilityRole="button"
                >
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.textMuted }}>{tr('Refresh loop')}</Text>
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                <View style={{ flex: 1, minWidth: isMobile ? '100%' : '48%', borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 12, gap: 8 }} data-testid="library-continue-rail-card" testID="library-continue-rail-card">
                  <Text style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>{tr('Continue rail')}</Text>
                  {engagementLoop?.continue_item ? (
                    <>
                      <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }} numberOfLines={2} data-testid="library-continue-item-title" testID="library-continue-item-title">
                        {engagementLoop.continue_item.title || tr('Untitled')}
                      </Text>
                      <Text style={{ fontSize: 11, color: C.textMuted }}>
                        {toTitle(engagementLoop.continue_item.type || 'item')} • {toTitle(engagementLoop.continue_item.category || 'general')}
                      </Text>
                      <TouchableOpacity
                        onPress={() => handleOpenItem({
                          title: engagementLoop.continue_item?.title || tr('Untitled'),
                          url: engagementLoop.continue_item?.url || '',
                          type: engagementLoop.continue_item?.type || 'article',
                          category: engagementLoop.continue_item?.category || 'general',
                          added_date: engagementLoop.continue_item?.last_opened_at || new Date().toISOString(),
                          source: engagementLoop.continue_item?.source || 'library',
                        })}
                        style={{ alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 999, backgroundColor: C.primary }}
                        data-testid="library-continue-item-open-btn"
                        testID="library-continue-item-open-btn"
                        accessibilityRole="button"
                      >
                        <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primaryText }}>{tr('Resume item')}</Text>
                      </TouchableOpacity>
                    </>
                  ) : (
                    <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-continue-empty" testID="library-continue-empty">
                      {tr('Open content to activate your continue rail.')}
                    </Text>
                  )}
                </View>

                <View style={{ flex: 1, minWidth: isMobile ? '100%' : '48%', borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 12, gap: 8 }} data-testid="library-daily-mission-card" testID="library-daily-mission-card">
                  <Text style={{ fontSize: 10, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>{tr('Daily mission & streak')}</Text>
                  <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }} data-testid="library-streak-days" testID="library-streak-days">
                    {tr('Current streak')}: {engagementLoop?.streak_days || 0} {tr('days')}
                  </Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                    <Text style={{ fontSize: 10, color: C.textMuted }} data-testid="library-daily-mission-mode" testID="library-daily-mission-mode">
                      {tr('Mission mode')}: {toTitle(engagementLoop?.daily_mission?.adaptive_context?.mode || 'baseline')}
                    </Text>
                    <TouchableOpacity
                      accessibilityRole="button"
                      onPress={() => setShowAdaptiveReasonModal(true)}
                      style={{ width: 20, height: 20, borderRadius: 999, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center', backgroundColor: C.card }}
                      data-testid="library-adaptive-mission-reason-trigger"
                      testID="library-adaptive-mission-reason-trigger"
                    >
                      <Ionicons name="information-circle-outline" size={13} color={C.textMuted} />
                    </TouchableOpacity>
                  </View>
                  <Text style={{ fontSize: 10, color: C.textMuted }} data-testid="library-adaptive-mission-change-direction" testID="library-adaptive-mission-change-direction">
                    {tr('Goal trend')}: {toTitle(engagementLoop?.daily_mission?.adaptive_context?.change_direction || 'stable')}
                  </Text>
                  <Text style={{ fontSize: 10, color: C.textMuted }} data-testid="library-adaptive-mission-tone-profile" testID="library-adaptive-mission-tone-profile">
                    {tr('Coaching tone')}: {toTitle(engagementLoop?.daily_mission?.adaptive_context?.tone_profile || normalizedUserPlan || 'free')}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>
                    {tr('Open goal')}: {engagementLoop?.daily_mission?.progress?.opens || 0}/{engagementLoop?.daily_mission?.target?.opens || 2}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>
                    {tr('Bookmark goal')}: {engagementLoop?.daily_mission?.progress?.bookmarks || 0}/{engagementLoop?.daily_mission?.target?.bookmarks || 1}
                  </Text>
                  <Text style={{ fontSize: 10, color: C.textMuted }} data-testid="library-daily-mission-history-days" testID="library-daily-mission-history-days">
                    {tr('History used')}: {engagementLoop?.daily_mission?.adaptive_context?.history_days_used ?? 0} {tr('days')} • {tr('Active days')}: {engagementLoop?.daily_mission?.adaptive_context?.active_days ?? 0}
                  </Text>
                  <View style={{ alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: (engagementLoop?.daily_mission?.completed ? colors.successSoft : colors.warningSoft) }}>
                    <Text style={{ fontSize: 10, fontWeight: '800', color: engagementLoop?.daily_mission?.completed ? colors.successText : colors.warningText }} data-testid="library-daily-mission-status" testID="library-daily-mission-status">
                      {engagementLoop?.daily_mission?.completed ? tr('Mission complete') : tr('Mission in progress')}
                    </Text>
                  </View>
                </View>
              </View>

              <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 12, gap: 8 }} data-testid="library-telemetry-panel" testID="library-telemetry-panel">
                <Text style={{ fontSize: 11, fontWeight: '800', color: C.text }} data-testid="library-telemetry-title" testID="library-telemetry-title">
                  {tr('Recommendation telemetry')}
                </Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-telemetry-reason-clicks" testID="library-telemetry-reason-clicks">
                    {tr('Reason clicks')}: {telemetry?.events?.recommendation_reason_click || 0}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-telemetry-open-after" testID="library-telemetry-open-after">
                    {tr('Open-after-recommendation')}: {telemetry?.events?.open_after_recommendation || 0}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-telemetry-bookmark-after" testID="library-telemetry-bookmark-after">
                    {tr('Bookmark-after-recommendation')}: {telemetry?.events?.bookmark_after_recommendation || 0}
                  </Text>
                </View>
              </View>

              <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 12, gap: 8 }} data-testid="library-weekly-summary-card" testID="library-weekly-summary-card">
                <Text style={{ fontSize: 11, fontWeight: '800', color: C.text }} data-testid="library-weekly-summary-title" testID="library-weekly-summary-title">
                  {tr('Weekly mission summary')}
                </Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-weekly-summary-wins" testID="library-weekly-summary-wins">
                    {tr('Wins')}: {engagementLoop?.weekly_summary?.wins ?? 0}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-weekly-summary-misses" testID="library-weekly-summary-misses">
                    {tr('Misses')}: {engagementLoop?.weekly_summary?.misses ?? 0}
                  </Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }} data-testid="library-weekly-summary-streak-risk" testID="library-weekly-summary-streak-risk">
                    {tr('Streak risk')}: {toTitle(engagementLoop?.weekly_summary?.streak_risk || 'low')}
                  </Text>
                </View>
              </View>

              {user?.is_admin && adminTuning && (
                <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 12, gap: 8 }} data-testid="library-admin-ranking-tuning-panel" testID="library-admin-ranking-tuning-panel">
                  <Text style={{ fontSize: 11, fontWeight: '800', color: C.text }} data-testid="library-admin-ranking-tuning-title" testID="library-admin-ranking-tuning-title">
                    {tr('Admin ranking tuning by plan')}
                  </Text>
                  {Object.entries(adminTuning.by_plan || {}).map(([plan, payload]) => {
                    const topReason = payload.reason_level_conversion?.[0];
                    return (
                      <View key={plan} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, gap: 5 }} data-testid={`library-admin-plan-${plan}`} testID={`library-admin-plan-${plan}`}>
                        <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{toTitle(plan)}</Text>
                        <Text style={{ fontSize: 10, color: C.textMuted }}>
                          {tr('Reason clicks')}: {payload.events?.recommendation_reason_click || 0} • {tr('Open-after')}: {payload.events?.open_after_recommendation || 0}
                        </Text>
                        {topReason ? (
                          <Text style={{ fontSize: 10, color: C.textMuted }} data-testid={`library-admin-plan-top-reason-${plan}`} testID={`library-admin-plan-top-reason-${plan}`}>
                            {tr('Top reason')}: {toTitle(topReason.reason)} • {tr('Open rate')}: {(topReason.open_after_click_rate * 100).toFixed(1)}%
                          </Text>
                        ) : (
                          <Text style={{ fontSize: 10, color: C.textMuted }}>{tr('No reason-level telemetry yet')}</Text>
                        )}
                      </View>
                    );
                  })}
                </View>
              )}
            </View>

            <LibraryFilterPanel
              C={C}
              colors={colors}
              isMobile={isMobile}
              tr={tr}
              searchInput={searchInput}
              setSearchInput={setSearchInput}
              handleSearch={handleSearch}
              handleResetFilters={handleResetFilters}
              categories={categories}
              types={types}
              catFilter={catFilter}
              typeFilter={typeFilter}
              sortBy={sortBy}
              viewMode={viewMode}
              setCatFilter={setCatFilter}
              setTypeFilter={setTypeFilter}
              setSortBy={setSortBy}
              setViewMode={setViewMode}
              setQuery={setQuery}
              setPage={setPage}
              activeFiltersCount={activeFiltersCount}
              page={page}
              totalPages={totalPages}
              catColors={CAT_COLORS}
              typeIcons={TYPE_ICONS}
              toTitle={toTitle}
              onLayoutY={(y) => setSectionOffset('filters', y)}
            />

            <LibraryContentGrid
              C={C}
              colors={colors}
              tr={tr}
              loading={loading}
              items={items}
              viewMode={viewMode}
              bookmarkedSet={bookmarkedSet}
              columns={columns}
              cardWidth={cardWidth}
              typeIcons={TYPE_ICONS}
              catColors={CAT_COLORS}
              formatDate={formatDate}
              handleToggleBookmark={handleToggleBookmark}
              handleOpenItem={handleOpenItem}
              handleShareItem={handleShareItem}
              onRecommendationReasonPress={handleRecommendationReasonClick}
              onExplainRecommendation={handleExplainRecommendation}
              toTitle={toTitle}
              sortBy={sortBy}
              onLayoutY={(y) => setSectionOffset('content', y)}
            />

            {totalPages > 1 && !loading && (
              <View
                onLayout={(e) => setSectionOffset('pagination', e.nativeEvent.layout.y)}
                style={{
                  marginTop: 18,
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexWrap: 'wrap',
                  gap: 8,
                }}
                data-testid="content-library-pagination"
                testID="content-library-pagination"
              >
                <TouchableOpacity accessibilityLabel="Content page prev button"
                  disabled={page <= 1}
                  onPress={() => goToPage(page - 1)}
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 11,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: C.card,
                    alignItems: 'center',
                    justifyContent: 'center',
                    opacity: page <= 1 ? 0.4 : 1,
                  }}
                  data-testid="content-page-prev"
                  testID="content-page-prev"
                  accessibilityRole="button"
                >
                  <Ionicons name="chevron-back" size={17} color={C.text} />
                </TouchableOpacity>

                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let p = i + 1;
                  if (totalPages > 5) {
                    if (page <= 3) p = i + 1;
                    else if (page >= totalPages - 2) p = totalPages - 4 + i;
                    else p = page - 2 + i;
                  }
                  const active = p === page;
                  return (
                    <TouchableOpacity accessibilityLabel="Go to to page in content library enterprise"
                      key={p}
                      onPress={() => goToPage(p)}
                      style={{
                        width: 38,
                        height: 38,
                        borderRadius: 11,
                        borderWidth: 1,
                        borderColor: active ? C.primary : C.border,
                        backgroundColor: active ? C.primary : C.card,
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                      data-testid={`content-page-${p}`}
                      testID={`content-page-${p}`}
                      accessibilityRole="button"
                    >
                      <Text style={{ fontSize: 12, fontWeight: '800', color: active ? colors.primaryText : C.textMuted }}>{p}</Text>
                    </TouchableOpacity>
                  );
                })}

                <TouchableOpacity accessibilityLabel="Content page next button"
                  disabled={page >= totalPages}
                  onPress={() => goToPage(page + 1)}
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 11,
                    borderWidth: 1,
                    borderColor: C.border,
                    backgroundColor: C.card,
                    alignItems: 'center',
                    justifyContent: 'center',
                    opacity: page >= totalPages ? 0.4 : 1,
                  }}
                  data-testid="content-page-next"
                  testID="content-page-next"
                  accessibilityRole="button"
                >
                  <Ionicons name="chevron-forward" size={17} color={C.text} />
                </TouchableOpacity>
              </View>
            )}

            {!loading && items.length > 0 && (
              <Text style={{ textAlign: 'center', fontSize: 11, color: C.textMuted, marginTop: 10 }} data-testid="content-library-page-meta" testID="content-library-page-meta">
                {tr('Page')} {page} {tr('of')} {totalPages} ({total} {tr('items')})
              </Text>
            )}

          </View>
        </ScrollView>

        <SectionProgressRail
          visible={showProgressRail}
          colors={C}
          railTestId="library-progress-rail"
          activeId={activeSection}
          onSelect={scrollToSection}
          top={128}
          right={8}
          maxWidth={190}
          items={[
            { id: 'overview', label: 'Overview' },
            { id: 'insights', label: 'Insights' },
            { id: 'comparison', label: '7-day Compare' },
            { id: 'retention', label: 'Retention Loop' },
            { id: 'filters', label: 'Filters' },
            { id: 'content', label: 'Content' },
            { id: 'pagination', label: 'Pagination' },
          ]}
        />

        {toast !== '' && (
          <View
            style={{
              position: 'absolute',
              bottom: 18,
              left: 20,
              right: 20,
              backgroundColor: colors.success,
              borderRadius: 12,
              paddingVertical: 12,
              paddingHorizontal: 14,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 8,
              zIndex: 1000,
            }}
            data-testid="library-toast"
            testID="library-toast"
          >
            <Ionicons name="checkmark-circle" size={18} color={colors.primaryText} />
            <Text style={{ flex: 1, color: colors.primaryText, fontSize: 12, fontWeight: '800' }} data-testid="library-toast-message" testID="library-toast-message">
              {toast}
            </Text>
          </View>
        )}

        <Modal visible={showExportModal} transparent animationType="fade">
          <View
            style={{
              flex: 1,
              backgroundColor: 'rgba(0,0,0,0.55)',
              justifyContent: 'center',
              alignItems: 'center',
              padding: 18,
            }}
            data-testid="export-modal-overlay"
            testID="export-modal-overlay"
          >
            <View
              style={{
                width: '100%',
                maxWidth: 380,
                backgroundColor: C.card,
                borderRadius: 16,
                borderWidth: 1,
                borderColor: C.border,
                padding: 18,
              }}
              data-testid="export-modal-card"
              testID="export-modal-card"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '900' }} data-testid="export-modal-title" testID="export-modal-title">
                  {tr('Export Library')}
                </Text>
                <TouchableOpacity
                  onPress={() => setShowExportModal(false)}
                  data-testid="export-modal-close"
                  testID="export-modal-close"
                  accessibilityRole="button"
                >
                  <Ionicons name="close" size={21} color={C.textMuted} />
                </TouchableOpacity>
              </View>

              <Text style={{ color: C.textMuted, fontSize: 12, marginBottom: 12 }} data-testid="export-modal-subtitle" testID="export-modal-subtitle">
                {tr('Export')} {items.length} {tr('items from your current filtered view')}
              </Text>

              {exporting ? (
                <ActivityIndicator color={C.primary} style={{ marginVertical: 18 }} />
              ) : (
                <View style={{ gap: 8 }}>
                  {[
                    { format: 'txt' as const, icon: 'document-text-outline', color: colors.successText, label: tr('Plain Text (.txt)') },
                    { format: 'csv' as const, icon: 'grid-outline', color: colors.primary, label: tr('Spreadsheet (.csv)') },
                  ].map(option => (
                    <TouchableOpacity accessibilityLabel="Export in content library enterprise button"
                      key={option.format}
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 10,
                        padding: 12,
                        borderRadius: 12,
                        backgroundColor: C.bgSoft,
                        borderWidth: 1,
                        borderColor: C.border,
                      }}
                      onPress={() => handleExport(option.format)}
                      data-testid={`export-${option.format}-btn`}
                      testID={`export-${option.format}-btn`}
                      accessibilityRole="button"
                    >
                      <View
                        style={{
                          width: 34,
                          height: 34,
                          borderRadius: 9,
                          backgroundColor: `${option.color}20`,
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <Ionicons name={option.icon as any} size={17} color={option.color} />
                      </View>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{option.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </View>
          </View>
        </Modal>

        <Modal visible={showAdaptiveReasonModal} transparent animationType="fade" onRequestClose={() => setShowAdaptiveReasonModal(false)}>
          <View
            style={{
              flex: 1,
              backgroundColor: 'rgba(0,0,0,0.55)',
              justifyContent: 'center',
              alignItems: 'center',
              padding: 18,
            }}
            data-testid="library-adaptive-mission-reason-modal-overlay"
            testID="library-adaptive-mission-reason-modal-overlay"
          >
            <View
              style={{
                width: '100%',
                maxWidth: 460,
                backgroundColor: C.card,
                borderRadius: 16,
                borderWidth: 1,
                borderColor: C.border,
                padding: 18,
                gap: 10,
              }}
              data-testid="library-adaptive-mission-reason-modal-card"
              testID="library-adaptive-mission-reason-modal-card"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '900' }} data-testid="library-adaptive-mission-reason-modal-title" testID="library-adaptive-mission-reason-modal-title">
                  {tr('Why your mission changed')}
                </Text>
                <TouchableOpacity
                  accessibilityRole="button"
                  onPress={() => setShowAdaptiveReasonModal(false)}
                  data-testid="library-adaptive-mission-reason-modal-close"
                  testID="library-adaptive-mission-reason-modal-close"
                >
                  <Ionicons name="close" size={20} color={C.textMuted} />
                </TouchableOpacity>
              </View>

              <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} data-testid="library-adaptive-mission-reason-short" testID="library-adaptive-mission-reason-short">
                {engagementLoop?.daily_mission?.adaptive_context?.change_reason_short || tr('Mission goals are currently using baseline defaults.')}
              </Text>

              <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="library-adaptive-mission-reason-tone" testID="library-adaptive-mission-reason-tone">
                {tr('Tone profile')}: {toTitle(engagementLoop?.daily_mission?.adaptive_context?.tone_profile || normalizedUserPlan || 'free')}
              </Text>

              <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10, gap: 6 }} data-testid="library-adaptive-mission-reason-detail" testID="library-adaptive-mission-reason-detail">
                {(engagementLoop?.daily_mission?.adaptive_context?.change_reason_detail || []).slice(0, 4).map((line, idx) => (
                  <Text key={`adaptive-reason-${idx}`} style={{ color: C.textMuted, fontSize: 11 }} data-testid={`library-adaptive-mission-reason-detail-line-${idx}`} testID={`library-adaptive-mission-reason-detail-line-${idx}`}>
                    • {line}
                  </Text>
                ))}
                {(!engagementLoop?.daily_mission?.adaptive_context?.change_reason_detail || engagementLoop?.daily_mission?.adaptive_context?.change_reason_detail?.length === 0) && (
                  <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="library-adaptive-mission-reason-detail-fallback" testID="library-adaptive-mission-reason-detail-fallback">
                    • {tr('Open and bookmark content over a few days to unlock adaptive mission tuning.')}
                  </Text>
                )}
              </View>

              <TouchableOpacity
                accessibilityRole="button"
                onPress={() => setShowAdaptiveReasonModal(false)}
                style={{ alignSelf: 'flex-start', borderRadius: 999, backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 8 }}
                data-testid="library-adaptive-mission-reason-modal-dismiss"
                testID="library-adaptive-mission-reason-modal-dismiss"
              >
                <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{tr('Got it')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      </SafeAreaView>
    </AppShell>
  );
}