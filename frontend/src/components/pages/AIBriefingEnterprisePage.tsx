import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  ScrollView,
  Platform,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import AppShell from '../AppShell';
import { AIFeatureSkeleton } from '../SkeletonLoaders';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { useTranslation } from '../../hooks/useTranslation';
import { SevenDayComparisonRibbon } from '../insights/SevenDayComparisonRibbon';
import { DailyAutopromptCards } from '../insights/DailyAutopromptCards';
import { SectionProgressRail } from '../progress/SectionProgressRail';

const ACCENTS = {
  green: 'var(--app-success)',
  red: 'var(--app-error)',
  blue: 'var(--app-primary)',
  yellow: 'var(--app-warning)',
  purple: 'var(--app-primary)',
  cyan: 'var(--app-primary)',
  orange: 'var(--app-warning)',
};

const MOOD_COLORS: Record<string, string> = {
  energetic: ACCENTS.orange,
  focused: ACCENTS.blue,
  calm: ACCENTS.cyan,
  motivated: ACCENTS.green,
};

const formatDateLabel = (dateValue?: string) => {
  if (!dateValue) return '—';
  try {
    return new Date(dateValue).toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return dateValue;
  }
};

const getCount = (value: unknown): number => (Array.isArray(value) ? value.length : 0);

export const AIBriefingEnterprisePage = () => {
  const { _user } = useAuth();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const { t } = useTranslation();

  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const isWide = width >= 1180;
  const isTabletOrAbove = width >= 768;
  const onPrimary = colors.primaryText || colors.buttonText || colors.card;
  const C = {
    ...colors,
    muted: colors.textMuted,
    surface: colors.surface || colors.card,
    ...ACCENTS,
  };

  const [briefing, setBriefing] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState<any[]>([]);
  const [preferences, setPreferences] = useState<any>(null);
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [historySearch, setHistorySearch] = useState('');
  const [compareBriefingId, setCompareBriefingId] = useState<string>('');
  const [exportingPdf, setExportingPdf] = useState(false);
  const [activeSection, setActiveSection] = useState('overview');
  const scrollRef = useRef<ScrollView | null>(null);
  const sectionOffsets = useRef<Record<string, number>>({});

  const loadAll = useCallback(async (opts?: { forceGenerate?: boolean; silent?: boolean }) => {
    const shouldForce = Boolean(opts?.forceGenerate);
    const silent = Boolean(opts?.silent);

    if (!silent) {
      setLoading(true);
      setError('');
    }

    try {
      const [todayResult, historyResult, prefsResult] = await Promise.allSettled([
        api.get(`/ai-briefing/today${shouldForce ? '?force=true' : ''}`),
        api.get('/ai-briefing/history'),
        api.get('/ai-briefing/preferences'),
      ]);

      const hasToday = todayResult.status === 'fulfilled';
      const hasHistory = historyResult.status === 'fulfilled';

      if (hasToday) {
        setBriefing(todayResult.value?.data || null);
      }
      if (hasHistory) {
        setHistory(Array.isArray(historyResult.value?.data?.briefings) ? historyResult.value.data.briefings : []);
      }
      if (prefsResult.status === 'fulfilled') {
        setPreferences(prefsResult.value?.data || null);
      }

      if (hasToday || hasHistory) {
        setError('');
      }

      if (!hasToday && !hasHistory) {
        setError('Unable to load Daily Briefing right now. Please retry.');
      }
    } catch {
      setError('Unable to load Daily Briefing right now. Please retry.');
    } finally {
      setLoading(false);
      setRefreshing(false);
      setGenerating(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useAutoRefresh(
    useCallback(async () => {
      setRefreshing(true);
      await loadAll({ silent: true });
    }, [loadAll]),
    { intervalMs: 45000 },
  );

  const selectedCompare = useMemo(
    () => history.find((item) => item?.briefing_id && item.briefing_id === compareBriefingId) || null,
    [history, compareBriefingId],
  );

  const filteredHistory = useMemo(() => {
    const q = historySearch.trim().toLowerCase();
    if (!q) return history;
    return history.filter((item) => `${item?.date || ''} ${item?.greeting || ''}`.toLowerCase().includes(q));
  }, [history, historySearch]);

  const briefingKpis = useMemo(() => {
    const source = briefing || {};
    return [
      { key: 'priorities', label: 'Priorities', value: String(getCount(source?.top_priorities)), icon: 'flag-outline' as const, tone: C.red },
      { key: 'learning', label: 'Learning Picks', value: String(getCount(source?.learning_picks)), icon: 'school-outline' as const, tone: C.purple },
      { key: 'insights', label: 'Industry Signals', value: String(getCount(source?.industry_insights)), icon: 'trending-up-outline' as const, tone: C.cyan },
      {
        key: 'mood',
        label: 'Focus Mode',
        value: String(source?.weather_mood || 'n/a').toUpperCase(),
        icon: 'sunny-outline' as const,
        tone: MOOD_COLORS[String(source?.weather_mood || '').toLowerCase()] || C.primary,
      },
    ];
  }, [briefing, C]);

  const compareInsights = useMemo(() => {
    if (!briefing || !selectedCompare) return null;
    const currentPriorities = getCount(briefing.top_priorities);
    const previousPriorities = getCount(selectedCompare.top_priorities);
    const currentLearning = getCount(briefing.learning_picks);
    const previousLearning = getCount(selectedCompare.learning_picks);
    return {
      baselineDate: selectedCompare.date,
      prioritiesDelta: currentPriorities - previousPriorities,
      learningDelta: currentLearning - previousLearning,
      moodChanged: String(briefing.weather_mood || '') !== String(selectedCompare.weather_mood || ''),
    };
  }, [briefing, selectedCompare]);

  const moodColor = MOOD_COLORS[String(briefing?.weather_mood || '').toLowerCase()] || C.blue;

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadAll({ silent: true });
  }, [loadAll]);

  const onGenerate = useCallback(async () => {
    setGenerating(true);
    await loadAll({ forceGenerate: true });
  }, [loadAll]);

  const onStartCompare = useCallback(() => {
    const candidate = history.find((row) => row?.briefing_id && row.briefing_id !== briefing?.briefing_id);
    if (!candidate?.briefing_id) return;
    setCompareBriefingId(candidate.briefing_id);
    if (!isWide) setShowHistoryDrawer(true);
  }, [history, briefing?.briefing_id, isWide]);

  const openHistoryRow = useCallback((row: any) => {
    setBriefing(row);
    setShowHistoryDrawer(false);
  }, []);

  const setSectionOffset = useCallback((id: string, y: number) => {
    sectionOffsets.current[id] = y;
  }, []);

  const scrollToSection = useCallback((id: string) => {
    const y = sectionOffsets.current[id];
    if (typeof y !== 'number') return;
    scrollRef.current?.scrollTo({ y: Math.max(y - 72, 0), animated: true });
  }, []);

  const onBriefingScroll = useCallback((e: any) => {
    const y = e?.nativeEvent?.contentOffset?.y || 0;
    const entries = Object.entries(sectionOffsets.current)
      .sort((a, b) => a[1] - b[1]);
    let next = 'overview';
    for (const [id, top] of entries) {
      if (y + 120 >= top) next = id;
      else break;
    }
    if (next !== activeSection) setActiveSection(next);
  }, [activeSection]);

  const sevenDayMetrics = useMemo(() => {
    const rows = [...history].filter(Boolean).slice(0, 14);
    const current = rows.slice(0, 7);
    const previous = rows.slice(7, 14);
    const avgCount = (arr: any[], key: string) => {
      if (!arr.length) return 0;
      const total = arr.reduce((sum, row) => sum + getCount(row?.[key]), 0);
      return total / arr.length;
    };

    return [
      {
        id: 'briefings',
        label: 'Briefings generated',
        current: current.length,
        previous: previous.length,
      },
      {
        id: 'priorities',
        label: 'Avg priorities/day',
        current: avgCount(current, 'top_priorities'),
        previous: avgCount(previous, 'top_priorities'),
        precision: 1,
      },
      {
        id: 'learning',
        label: 'Avg learning picks/day',
        current: avgCount(current, 'learning_picks'),
        previous: avgCount(previous, 'learning_picks'),
        precision: 1,
      },
    ];
  }, [history]);

  const onExportBriefingPdf = useCallback(async () => {
    if (!briefing) return;
    setExportingPdf(true);
    try {
      const priorities = Array.isArray(briefing?.top_priorities)
        ? briefing.top_priorities.map((row: any, idx: number) => `${idx + 1}. ${row?.title || 'Untitled'}`).join('\n')
        : '';
      const learning = Array.isArray(briefing?.learning_picks)
        ? briefing.learning_picks.map((row: any, idx: number) => `${idx + 1}. ${row?.title || 'Learning topic'}`).join('\n')
        : '';
      const summary = [
        `Date: ${formatDateLabel(briefing?.date)}`,
        `Mood: ${briefing?.weather_mood || 'neutral'}`,
        '',
        `Greeting: ${briefing?.greeting || 'N/A'}`,
        '',
        'Top Priorities:',
        priorities || 'No priorities',
        '',
        'Learning Picks:',
        learning || 'No learning picks',
        '',
        `Motivation: ${briefing?.motivation || 'N/A'}`,
      ].join('\n');

      const response = await api.post('/actions/export', {
        feature_key: 'ai-briefing',
        title: 'Daily Briefing Report',
        format: 'pdf',
        content: summary,
      }, { responseType: 'blob' } as any);

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const blob = response?.data instanceof Blob ? response.data : new Blob([response?.data], { type: 'application/pdf' });
        const link = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = link;
        anchor.download = `daily_briefing_${briefing?.date || 'report'}.pdf`;
        anchor.click();
        window.URL.revokeObjectURL(link);
      }
    } catch {
      setError('Unable to export PDF right now. Please retry.');
    } finally {
      setExportingPdf(false);
    }
  }, [briefing]);

  const briefingAutopromptCards = useMemo(() => {
    const prioritiesMetric = sevenDayMetrics.find((metric) => metric.id === 'priorities');
    const learningMetric = sevenDayMetrics.find((metric) => metric.id === 'learning');

    const cards = [
      briefing
        ? {
            id: 'refresh-signals',
            title: 'Capture latest signals',
            description: 'Run a fresh pull so today’s priorities and picks stay current before your next focus block.',
            ctaLabel: refreshing ? 'Refreshing...' : 'Refresh briefing',
            onPress: onRefresh,
            icon: 'refresh-outline',
          }
        : {
            id: 'generate-first-briefing',
            title: 'Create today’s snapshot',
            description: 'No live briefing found yet. Generate one now to unlock today’s action view and timeline.',
            ctaLabel: generating ? 'Generating...' : 'Generate now',
            onPress: onGenerate,
            icon: 'sparkles-outline',
          },
      history.some((row) => row?.briefing_id && row.briefing_id !== briefing?.briefing_id)
        ? {
            id: 'compare-latest',
            title: 'Run a quick compare',
            description: 'Compare today against your most recent prior briefing to spot shifts in priorities and learning.',
            ctaLabel: 'Compare latest',
            onPress: onStartCompare,
            icon: 'git-compare-outline',
          }
        : {
            id: 'open-timeline',
            title: 'Build continuity history',
            description: 'Open timeline and keep generating daily entries so comparisons become more actionable.',
            ctaLabel: 'Open history',
            onPress: () => setShowHistoryDrawer(true),
            icon: 'time-outline',
          },
      (Number(prioritiesMetric?.current || 0) < Number(prioritiesMetric?.previous || 0)
        || Number(learningMetric?.current || 0) < Number(learningMetric?.previous || 0))
        ? {
            id: 'rebalance-learning',
            title: 'Rebalance today’s focus',
            description: 'Your 7-day trend dipped. Jump to Learning and adjust one pick to recover momentum.',
            ctaLabel: 'Go to learning',
            onPress: () => scrollToSection('learning'),
            icon: 'school-outline',
          }
        : {
            id: 'archive-pdf',
            title: 'Archive a daily checkpoint',
            description: 'Trends are stable. Export this briefing to keep a lightweight audit trail.',
            ctaLabel: exportingPdf ? 'Exporting...' : 'Export PDF',
            onPress: onExportBriefingPdf,
            icon: 'download-outline',
          },
    ];

    return cards;
  }, [
    briefing,
    sevenDayMetrics,
    refreshing,
    generating,
    history,
    onRefresh,
    onGenerate,
    onStartCompare,
    scrollToSection,
    exportingPdf,
    onExportBriefingPdf,
  ]);

  const showProgressRail = width >= 1360;

  const renderHistoryPanel = () => (
    <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12, gap: 10 }} data-testid="briefing-history-panel" testID="briefing-history-panel">
      <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }} data-testid="briefing-history-panel-title" testID="briefing-history-panel-title">Briefing Timeline</Text>
      <TextInput
        value={historySearch}
        onChangeText={setHistorySearch}
        placeholder="Search by date or greeting"
        placeholderTextColor={C.muted}
        style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, color: C.text, backgroundColor: C.surface, fontSize: 12 }}
        data-testid="briefing-history-search-input"
        testID="briefing-history-search-input"
      />

      <ScrollView style={{ maxHeight: isWide ? 440 : 360 }} contentContainerStyle={{ gap: 8, paddingBottom: 8 }} data-testid="briefing-history-list" testID="briefing-history-list">
        {filteredHistory.map((row, idx) => {
          const isCurrent = row?.briefing_id && briefing?.briefing_id && row.briefing_id === briefing.briefing_id;
          const isCompare = row?.briefing_id && compareBriefingId === row.briefing_id;
          return (
            <View key={row?.briefing_id || `history-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: isCurrent ? C.primary : C.border, backgroundColor: C.surface, padding: 10, gap: 8 }} data-testid={`briefing-history-row-${idx}`} testID={`briefing-history-row-${idx}`}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{row?.date || '—'}</Text>
              <Text style={{ fontSize: 11, color: C.muted }} numberOfLines={2}>{row?.greeting || 'No greeting available'}</Text>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity onPress={() => openHistoryRow(row)} style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: isCurrent ? `${C.primary}22` : C.card, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`briefing-history-open-${idx}`} testID={`briefing-history-open-${idx}`}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: isCurrent ? C.primary : C.text }}>Open</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setCompareBriefingId(isCompare ? '' : (row?.briefing_id || ''))} style={{ borderRadius: 8, borderWidth: 1, borderColor: isCompare ? `${C.warning}88` : C.border, backgroundColor: isCompare ? `${C.warning}1d` : C.card, paddingHorizontal: 10, paddingVertical: 6 }} data-testid={`briefing-history-compare-${idx}`} testID={`briefing-history-compare-${idx}`}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: isCompare ? C.warning : C.text }}>{isCompare ? 'Compared' : 'Compare'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        })}

        {filteredHistory.length === 0 && (
          <View style={{ paddingVertical: 16 }} data-testid="briefing-history-empty" testID="briefing-history-empty">
            <Text style={{ fontSize: 11, color: C.muted }}>No briefing history matches your search.</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );

  if (loading) {
    return (
      <AppShell>
        <AIFeatureSkeleton />
      </AppShell>
    );
  }

  const b = briefing;

  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: C.bg }} data-testid="ai-briefing-screen" testID="ai-briefing-screen">
        <View style={{ margin: 14, borderRadius: 16, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 14, paddingVertical: 12, flexDirection: isTabletOrAbove ? 'row' : 'column', alignItems: isTabletOrAbove ? 'center' : 'flex-start', justifyContent: 'space-between', gap: 10 }} data-testid="briefing-header" testID="briefing-header">
          <View style={{ gap: 4 }}>
            <Text style={{ fontSize: 19, fontWeight: '800', color: C.text }} data-testid="briefing-title" testID="briefing-title">{tx('aiBriefing.page.title', 'Daily Briefing')}</Text>
            <Text style={{ fontSize: 11, color: C.muted }} data-testid="briefing-current-date" testID="briefing-current-date">
              {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </Text>
            {!!preferences?.briefing_time && (
              <Text style={{ fontSize: 10, color: C.muted }} data-testid="briefing-preferred-time" testID="briefing-preferred-time">
                Preferred briefing time: {preferences.briefing_time}
              </Text>
            )}
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <TouchableOpacity onPress={onRefresh} disabled={refreshing} style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: refreshing ? 0.7 : 1 }} data-testid="briefing-refresh-button" testID="briefing-refresh-button">
              {refreshing ? <ActivityIndicator size="small" color={C.primary} /> : <Ionicons name="refresh-outline" size={14} color={C.primary} />}
              <Text style={{ fontSize: 11, fontWeight: '700', color: C.primary }}>Refresh</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={onGenerate} disabled={generating} style={{ borderRadius: 10, backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: generating ? 0.75 : 1 }} data-testid="briefing-generate-button" testID="briefing-generate-button">
              {generating ? <ActivityIndicator size="small" color={onPrimary} /> : <Ionicons name="sparkles-outline" size={14} color={onPrimary} />}
              <Text style={{ fontSize: 11, fontWeight: '700', color: onPrimary }}>{tx('aiBriefing.actions.generate', 'Generate Briefing')}</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={onExportBriefingPdf} disabled={exportingPdf || !briefing} style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: exportingPdf ? 0.75 : 1 }} data-testid="briefing-export-pdf-button" testID="briefing-export-pdf-button">
              {exportingPdf ? <ActivityIndicator size="small" color={C.primary} /> : <Ionicons name="download-outline" size={14} color={C.primary} />}
              <Text style={{ fontSize: 11, fontWeight: '700', color: C.primary }}>Export PDF</Text>
            </TouchableOpacity>

            {!isWide && (
              <TouchableOpacity onPress={() => setShowHistoryDrawer(true)} style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="briefing-history-open-drawer" testID="briefing-history-open-drawer">
                <Ionicons name="time-outline" size={14} color={C.text} />
                <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{tx('aiBriefing.actions.history', 'History')}</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        <View style={{ flex: 1, paddingHorizontal: 14, paddingBottom: 14, flexDirection: isWide ? 'row' : 'column', gap: 12 }}>
          <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ gap: 12, paddingBottom: 28 }} onScroll={onBriefingScroll} scrollEventThrottle={16} data-testid="briefing-main-scroll" testID="briefing-main-scroll">
            {!!error && (
              <View style={{ borderRadius: 12, borderWidth: 1, borderColor: `${C.error}66`, backgroundColor: `${C.error}15`, padding: 12 }} data-testid="briefing-error-banner" testID="briefing-error-banner">
                <Text style={{ color: C.error, fontSize: 12, fontWeight: '700' }}>{error}</Text>
              </View>
            )}

            <SevenDayComparisonRibbon
              title="7-day performance comparison"
              subtitle="Current 7 days vs previous 7 days from briefing history"
              metrics={sevenDayMetrics}
              colors={C}
              testIdPrefix="briefing-seven-day"
              onRefresh={onRefresh}
              refreshing={refreshing}
            />

            <DailyAutopromptCards
              title="Daily autoprompt cards"
              subtitle="Next best actions derived from your 7-day briefing trend"
              prompts={briefingAutopromptCards}
              colors={C}
              testIdPrefix="briefing-autoprompt"
            />

            {b ? (
              <>
                <View onLayout={(e) => setSectionOffset('overview', e.nativeEvent.layout.y)} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="briefing-kpi-grid" testID="briefing-kpi-grid">
                  {briefingKpis.map((kpi) => (
                    <View key={kpi.key} style={{ minWidth: 170, flexGrow: 1, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12, gap: 5 }} data-testid={`briefing-kpi-${kpi.key}`} testID={`briefing-kpi-${kpi.key}`}>
                      <Ionicons name={kpi.icon} size={15} color={kpi.tone} />
                      <Text style={{ fontSize: 10, color: C.muted }}>{kpi.label}</Text>
                      <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }}>{kpi.value}</Text>
                    </View>
                  ))}
                </View>

                <View style={{ borderRadius: 14, borderWidth: 1, borderColor: `${moodColor}66`, backgroundColor: `${moodColor}14`, padding: 14, gap: 8 }} data-testid="briefing-greeting-card" testID="briefing-greeting-card">
                  <Text style={{ fontSize: 16, fontWeight: '800', color: C.text, lineHeight: 24 }} data-testid="briefing-greeting-text" testID="briefing-greeting-text">
                    {b.greeting || 'No greeting available'}
                  </Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: moodColor }} />
                    <Text style={{ fontSize: 11, color: moodColor, fontWeight: '700' }} data-testid="briefing-mood-text" testID="briefing-mood-text">{String(b.weather_mood || 'neutral')} mode</Text>
                    <Text style={{ fontSize: 10, color: C.muted }} data-testid="briefing-active-date" testID="briefing-active-date">• {formatDateLabel(b.date)}</Text>
                  </View>
                </View>

                {!!compareInsights && (
                  <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12, gap: 5 }} data-testid="briefing-compare-insights" testID="briefing-compare-insights">
                    <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }}>Compare vs {formatDateLabel(compareInsights.baselineDate)}</Text>
                    <Text style={{ fontSize: 11, color: C.muted }}>
                      Priority delta: {compareInsights.prioritiesDelta >= 0 ? '+' : ''}{compareInsights.prioritiesDelta} • Learning delta: {compareInsights.learningDelta >= 0 ? '+' : ''}{compareInsights.learningDelta} • Mood changed: {compareInsights.moodChanged ? 'Yes' : 'No'}
                    </Text>
                  </View>
                )}

                <View onLayout={(e) => setSectionOffset('priorities', e.nativeEvent.layout.y)} style={{ gap: 10 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="flag-outline" size={14} color={C.red} />
                    <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }}>Top Priorities</Text>
                  </View>
                  {Array.isArray(b.top_priorities) && b.top_priorities.length > 0 ? (
                    b.top_priorities.map((p: any, i: number) => (
                      <View key={`priority-${i}`} style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12 }}>
                        <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{p?.title || 'Untitled priority'}</Text>
                        {!!p?.description && <Text style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{p.description}</Text>}
                        {!!p?.action && <Text style={{ fontSize: 11, color: C.primary, marginTop: 6, fontWeight: '700' }}>{p.action}</Text>}
                      </View>
                    ))
                  ) : (
                    <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12 }}>
                      <Text style={{ fontSize: 11, color: C.muted }}>No priority items available from platform data.</Text>
                    </View>
                  )}
                </View>

                <View onLayout={(e) => setSectionOffset('learning', e.nativeEvent.layout.y)} style={{ gap: 10 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="school-outline" size={14} color={C.purple} />
                    <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }}>Learning Picks</Text>
                  </View>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {Array.isArray(b.learning_picks) && b.learning_picks.length > 0 ? (
                      b.learning_picks.map((pick: any, i: number) => (
                        <View key={`learning-${i}`} style={{ minWidth: 220, flexGrow: 1, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12 }}>
                          <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{pick?.title || 'Learning topic'}</Text>
                          {!!pick?.description && <Text style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{pick.description}</Text>}
                          {!!pick?.estimated_time && <Text style={{ fontSize: 10, color: C.primary, marginTop: 6 }}>{pick.estimated_time}</Text>}
                        </View>
                      ))
                    ) : (
                      <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12 }}>
                        <Text style={{ fontSize: 11, color: C.muted }}>No learning picks available from platform data.</Text>
                      </View>
                    )}
                  </View>
                </View>

                <View onLayout={(e) => setSectionOffset('insights', e.nativeEvent.layout.y)} style={{ gap: 10 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="trending-up-outline" size={14} color={C.cyan} />
                    <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }}>Industry Insights</Text>
                  </View>
                  {Array.isArray(b.industry_insights) && b.industry_insights.length > 0 ? (
                    b.industry_insights.map((ins: any, i: number) => (
                      <View key={`insight-${i}`} style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12 }}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{ins?.headline || 'Insight'}</Text>
                        {!!ins?.summary && <Text style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{ins.summary}</Text>}
                        {!!ins?.relevance && <Text style={{ fontSize: 10, color: C.primary, marginTop: 6 }}>{ins.relevance}</Text>}
                      </View>
                    ))
                  ) : (
                    <View style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12 }}>
                      <Text style={{ fontSize: 11, color: C.muted }}>No industry insights available from platform data.</Text>
                    </View>
                  )}
                </View>

                {!!b.motivation && (
                  <View style={{ borderRadius: 12, borderWidth: 1, borderColor: `${C.yellow}55`, backgroundColor: `${C.yellow}14`, padding: 12 }} data-testid="briefing-motivation-card" testID="briefing-motivation-card">
                    <Text style={{ fontSize: 11, fontWeight: '800', color: C.yellow }}>Motivation</Text>
                    <Text style={{ fontSize: 12, color: C.text, marginTop: 6, lineHeight: 20 }}>{b.motivation}</Text>
                  </View>
                )}

                <View onLayout={(e) => setSectionOffset('extras', e.nativeEvent.layout.y)} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {!!b.wellness_tip && (
                    <View style={{ minWidth: 220, flexGrow: 1, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12 }}>
                      <Text style={{ fontSize: 11, fontWeight: '800', color: C.green }}>Wellness Tip</Text>
                      <Text style={{ fontSize: 11, color: C.text, marginTop: 5 }}>{b.wellness_tip}</Text>
                    </View>
                  )}
                  {!!b.fun_fact && (
                    <View style={{ minWidth: 220, flexGrow: 1, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 12 }}>
                      <Text style={{ fontSize: 11, fontWeight: '800', color: C.orange }}>Fun Fact</Text>
                      <Text style={{ fontSize: 11, color: C.text, marginTop: 5 }}>{b.fun_fact}</Text>
                    </View>
                  )}
                </View>
              </>
            ) : (
              <View style={{ alignItems: 'center', justifyContent: 'center', borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingVertical: 42, paddingHorizontal: 18, gap: 10 }} data-testid="briefing-empty-state" testID="briefing-empty-state">
                <Ionicons name="sunny-outline" size={46} color={C.muted} />
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('aiBriefing.states.empty', 'No briefing available')}</Text>
                <Text style={{ fontSize: 11, color: C.muted, textAlign: 'center', maxWidth: 420 }}>
                  We only render platform-generated briefing data. Generate now to create your current daily briefing snapshot.
                </Text>
                <TouchableOpacity onPress={onGenerate} style={{ borderRadius: 10, backgroundColor: C.primary, paddingHorizontal: 16, paddingVertical: 9 }} data-testid="briefing-empty-generate-button" testID="briefing-empty-generate-button">
                  <Text style={{ color: onPrimary, fontSize: 11, fontWeight: '700' }}>{tx('aiBriefing.actions.generate', 'Generate Briefing')}</Text>
                </TouchableOpacity>
              </View>
            )}
          </ScrollView>

          {isWide && <View style={{ width: '100%', maxWidth: 960 }}>{renderHistoryPanel()}</View>}
        </View>

        {!isWide && (
          <Modal visible={showHistoryDrawer} transparent animationType="fade" onRequestClose={() => setShowHistoryDrawer(false)}>
            <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'flex-end' }}>
              <View style={{ maxHeight: '78%', backgroundColor: C.bg, borderTopLeftRadius: 16, borderTopRightRadius: 16, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="briefing-history-modal" testID="briefing-history-modal">
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }}>Briefing History</Text>
                  <TouchableOpacity onPress={() => setShowHistoryDrawer(false)} data-testid="briefing-history-modal-close" testID="briefing-history-modal-close">
                    <Ionicons name="close" size={18} color={C.text} />
                  </TouchableOpacity>
                </View>
                {renderHistoryPanel()}
              </View>
            </View>
          </Modal>
        )}

        <SectionProgressRail
          visible={showProgressRail}
          colors={C}
          railTestId="briefing-progress-rail"
          activeId={activeSection}
          onSelect={scrollToSection}
          top={126}
          right={10}
          maxWidth={190}
          items={[
            { id: 'overview', label: 'Overview' },
            { id: 'priorities', label: 'Priorities' },
            { id: 'learning', label: 'Learning' },
            { id: 'insights', label: 'Insights' },
            { id: 'extras', label: 'Extras' },
          ]}
        />
      </View>
    </AppShell>
  );
};

export default AIBriefingEnterprisePage;
