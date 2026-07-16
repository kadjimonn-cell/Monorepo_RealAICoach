import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../AppShell';
import { ProgressSkeleton } from '../SkeletonLoaders';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';

type FilterPeriod = '7d' | '30d' | '90d';

interface ProgressApiData {
  xp?: number;
  current_streak?: number;
  streak_days?: number;
  completed_conversations?: number;
  total_messages_sent?: number;
  category_progress?: Record<string, number>;
  updated_at?: string;
}

interface ProgressTrendsData {
  total_activity_days?: number;
  daily_activity?: Array<{ date: string; count: number }>;
  top_features?: Array<{ feature?: string; tool_id?: string; count?: number }>;
  generated_at?: string;
}

const CATEGORY_ICON: Record<string, string> = {
  dating: 'heart-outline',
  workplace: 'briefcase-outline',
  friendship: 'people-outline',
  family: 'home-outline',
  networking: 'git-network-outline',
  conflict: 'flash-outline',
};

const FEATURE_COLORS = ['var(--app-primary)', 'var(--app-primary)', 'var(--app-success)', 'var(--app-primary)', 'var(--app-warning)', 'var(--app-primary)'];

const MetricCard = ({
  title,
  value,
  subtitle,
  icon,
  tone,
  colors,
  testId,
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: string;
  tone: string;
  colors: any;
  testId: string;
}) => (
  <View
    style={{
      flex: 1,
      minWidth: 190,
      borderRadius: 16,
      borderWidth: 1,
      borderColor: `${tone}55`,
      backgroundColor: colors.card,
      padding: 14,
      gap: 8,
    }}
    data-testid={testId}
    testID={testId}
  >
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{title}</Text>
      <View style={{ borderRadius: 999, backgroundColor: `${tone}22`, padding: 6 }}>
        <Ionicons name={icon as any} size={13} color={tone} />
      </View>
    </View>
    <Text style={{ color: colors.text, fontSize: 24, fontWeight: '900' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>
      {value}
    </Text>
    <Text style={{ color: colors.textMuted, fontSize: 11 }}>{subtitle}</Text>
  </View>
);

const HeatCell = ({ count, colors }: { count: number; colors: any }) => {
  const tone =
    count <= 0
      ? colors.surfaceHover || colors.cardMuted || colors.card
      : count === 1
      ? `${colors.info || colors.primary}40`
      : count <= 3
      ? `${colors.primary}66`
      : `${colors.successText || 'var(--app-success)'}80`;
  return <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: tone }} />;
};

export default function ExecutiveProgressWorkspace() {
  const { t } = useTranslation();
  t('i18n.route.progress.enterprise.probe');
  const tx = useCallback(
    (key: string, fallback: string) => {
      const val = t(key);
      return val === key ? fallback : val;
    },
    [t],
  );

  const { colors } = useTheme();
  const { user } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();

  const isDesktop = width >= 1200;
  const isTablet = width >= 768 && width < 1200;
  const contentPadding = isDesktop ? 28 : isTablet ? 22 : 14;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [period, setPeriod] = useState<FilterPeriod>('30d');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [progress, setProgress] = useState<ProgressApiData>({});
  const [trends, setTrends] = useState<ProgressTrendsData>({});
  const [sessions, setSessions] = useState<any[]>([]);

  const days = period === '7d' ? 7 : period === '30d' ? 30 : 90;

  const loadData = useCallback(async () => {
    const uid = user?.user_id;
    if (!uid) {
      setLoading(false);
      return;
    }
    try {
      const [progressRes, trendsRes, sessionsRes] = await Promise.allSettled([
        api.get(`/progress/${uid}`, { silentLoading: true }),
        api.get(`/progress-trends/${uid}?days=${days}`, { silentLoading: true }),
        api.get(`/session-history/${uid}?limit=40`, { silentLoading: true }),
      ]);

      if (progressRes.status === 'fulfilled') {
        setProgress(progressRes.value?.data || {});
      }
      if (trendsRes.status === 'fulfilled') {
        setTrends(trendsRes.value?.data || {});
      }
      if (sessionsRes.status === 'fulfilled') {
        setSessions(sessionsRes.value?.data?.sessions || []);
      }
    } catch {
      setProgress({});
      setTrends({});
      setSessions([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [days, user?.user_id]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useAutoRefresh(loadData, { intervalMs: 30000 });

  const onRefresh = () => {
    setRefreshing(true);
    void loadData();
  };

  const totalXp = Number(progress?.xp || 0);
  const sessionsCount = Number(progress?.completed_conversations || 0);
  const streak = Number(progress?.current_streak || progress?.streak_days || 0);
  const totalMessages = Number(progress?.total_messages_sent || 0);
  const totalActivityDays = Number(trends?.total_activity_days || 0);

  const categoryRows = useMemo(() => {
    const raw = progress?.category_progress || {};
    return Object.entries(raw)
      .map(([key, value]) => ({ key, value: Number(value || 0) }))
      .sort((a, b) => b.value - a.value);
  }, [progress?.category_progress]);

  const topFeatures = useMemo(() => {
    return (trends?.top_features || [])
      .map((item, idx) => ({
        name: String(item?.feature || item?.tool_id || tx('progress.enterprise.unknownTool', 'Unknown Tool')),
        count: Number(item?.count || 0),
        color: FEATURE_COLORS[idx % FEATURE_COLORS.length],
      }))
      .filter((item) => item.count > 0)
      .slice(0, 8);
  }, [trends?.top_features, tx]);

  const maxFeatureCount = useMemo(() => {
    return topFeatures.length ? Math.max(...topFeatures.map((f) => f.count), 1) : 1;
  }, [topFeatures]);

  const dailyActivity = useMemo(() => {
    const list = Array.isArray(trends?.daily_activity) ? trends.daily_activity : [];
    return list.slice(-days);
  }, [days, trends?.daily_activity]);

  const availableCategories = useMemo(() => {
    return categoryRows.map((c) => c.key);
  }, [categoryRows]);

  const filteredSessions = useMemo(() => {
    if (categoryFilter === 'all') return sessions;
    return sessions.filter((s) => String(s?.category || '') === categoryFilter);
  }, [categoryFilter, sessions]);

  const lastUpdated = trends?.generated_at || progress?.updated_at;

  if (loading) {
    return (
      <AppShell>
        <ProgressSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top']} testID="progress-enterprise-page" data-testid="progress-enterprise-page">
        <ScrollView
          contentContainerStyle={{
            paddingBottom: 120,
            maxWidth: 1240,
            width: '100%' as any,
            alignSelf: 'center' as any,
          }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          showsVerticalScrollIndicator={false}
          testID="progress-enterprise-scroll"
          data-testid="progress-enterprise-scroll"
        >
          <View
            style={{
              marginTop: 14,
              marginHorizontal: contentPadding,
              padding: isDesktop ? 22 : 16,
              borderRadius: 20,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.card,
              gap: 12,
            }}
            testID="progress-enterprise-header"
            data-testid="progress-enterprise-header"
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
              <View style={{ maxWidth: 960 }}>
                <Text style={{ color: colors.text, fontSize: isDesktop ? 38 : 30, fontWeight: '900', letterSpacing: -0.8 }} testID="progress-enterprise-title" data-testid="progress-enterprise-title">
                  {tx('progress.enterprise.title', 'Progress Intelligence Center')}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 4, lineHeight: 19 }} testID="progress-enterprise-subtitle" data-testid="progress-enterprise-subtitle">
                  {tx('progress.enterprise.subtitle', 'Real-time performance, milestones, and behavior trends powered by your platform activity data.')}
                </Text>
                <Text style={{ color: colors.textSec || colors.textMuted, fontSize: 11, marginTop: 6 }} testID="progress-enterprise-last-updated" data-testid="progress-enterprise-last-updated">
                  {tx('progress.enterprise.lastUpdated', 'Last updated')}: {lastUpdated ? new Date(lastUpdated).toLocaleString() : tx('progress.enterprise.notAvailable', 'Not available')}
                </Text>
              </View>

              <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                <TouchableOpacity accessibilityLabel="Progress enterprise refresh button"
                  onPress={onRefresh}
                  style={{
                    borderRadius: 12,
                    borderWidth: 1,
                    borderColor: `${colors.primary}55`,
                    backgroundColor: `${colors.primary}18`,
                    paddingHorizontal: 12,
                    paddingVertical: 8,
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 6,
                  }}
                  testID="progress-enterprise-refresh-button"
                  data-testid="progress-enterprise-refresh-button"
                >
                  <Ionicons name="refresh" size={14} color={colors.primary} />
                  <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{tx('progress.enterprise.refresh', 'Refresh')}</Text>
                </TouchableOpacity>

                {Boolean(user?.is_admin) ? (
                  <TouchableOpacity accessibilityLabel="Progress enterprise open executive button"
                    onPress={() => router.push('/executive-dashboard?section=exec-command-center')}
                    style={{
                      borderRadius: 12,
                      borderWidth: 1,
                      borderColor: `${colors.info || colors.primary}66`,
                      backgroundColor: `${colors.info || colors.primary}18`,
                      paddingHorizontal: 12,
                      paddingVertical: 8,
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 6,
                    }}
                    testID="progress-enterprise-open-executive-button"
                    data-testid="progress-enterprise-open-executive-button"
                  >
                    <Ionicons name="shield-checkmark" size={14} color={colors.info || colors.primary} />
                    <Text style={{ color: colors.info || colors.primary, fontSize: 11, fontWeight: '800' }}>
                      {tx('progress.enterprise.openExecutive', 'Open Executive Dashboard')}
                    </Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} testID="progress-enterprise-period-group" data-testid="progress-enterprise-period-group">
              {(['7d', '30d', '90d'] as FilterPeriod[]).map((item) => {
                const isActive = period === item;
                return (
                  <TouchableOpacity accessibilityLabel="Set period in executive progress workspace button"
                    key={item}
                    onPress={() => setPeriod(item)}
                    style={{
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: isActive ? colors.primary : colors.border,
                      backgroundColor: isActive ? `${colors.primary}18` : colors.surface,
                      paddingHorizontal: 12,
                      paddingVertical: 7,
                    }}
                    testID={`progress-enterprise-period-${item}`}
                    data-testid={`progress-enterprise-period-${item}`}
                  >
                    <Text style={{ color: isActive ? colors.primary : colors.textMuted, fontSize: 11, fontWeight: '800' }}>
                      {item === '7d'
                        ? tx('progress.enterprise.period.7d', 'Last 7 Days')
                        : item === '30d'
                        ? tx('progress.enterprise.period.30d', 'Last 30 Days')
                        : tx('progress.enterprise.period.90d', 'Last 90 Days')}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View
            style={{
              marginTop: 14,
              marginHorizontal: contentPadding,
              flexDirection: 'row',
              flexWrap: 'wrap',
              gap: 10,
            }}
            testID="progress-enterprise-metrics-grid"
            data-testid="progress-enterprise-metrics-grid"
          >
            <MetricCard
              title={tx('progress.enterprise.metric.xp', 'Total XP')}
              value={totalXp.toLocaleString()}
              subtitle={tx('progress.enterprise.metric.xpSub', 'Accumulated platform learning score')}
              icon="sparkles"
              tone={colors.primary}
              colors={colors}
              testId="progress-enterprise-metric-xp"
            />
            <MetricCard
              title={tx('progress.enterprise.metric.sessions', 'Completed Sessions')}
              value={sessionsCount.toLocaleString()}
              subtitle={tx('progress.enterprise.metric.sessionsSub', 'AI-assisted practice sessions')}
              icon="chatbubbles"
              tone={colors.successText || colors.success}
              colors={colors}
              testId="progress-enterprise-metric-sessions"
            />
            <MetricCard
              title={tx('progress.enterprise.metric.streak', 'Current Streak')}
              value={streak > 0 ? `${streak}d` : '0d'}
              subtitle={tx('progress.enterprise.metric.streakSub', 'Consecutive active days')}
              icon="flame"
              tone={colors.warningText || colors.warning}
              colors={colors}
              testId="progress-enterprise-metric-streak"
            />
            <MetricCard
              title={tx('progress.enterprise.metric.activityDays', 'Active Days')}
              value={`${totalActivityDays}`}
              subtitle={`${days} ${tx('progress.enterprise.metric.daysWindow', 'day window')}`}
              icon="calendar"
              tone={colors.info || colors.primary}
              colors={colors}
              testId="progress-enterprise-metric-active-days"
            />
            <MetricCard
              title={tx('progress.enterprise.metric.messages', 'Messages Sent')}
              value={totalMessages.toLocaleString()}
              subtitle={tx('progress.enterprise.metric.messagesSub', 'Total interactions captured')}
              icon="chatbox-ellipses"
              tone={colors.accent || colors.primary}
              colors={colors}
              testId="progress-enterprise-metric-messages"
            />
          </View>

          <View
            style={{
              marginTop: 14,
              marginHorizontal: contentPadding,
              flexDirection: isDesktop ? 'row' : 'column',
              gap: 12,
            }}
            testID="progress-enterprise-main-panels"
            data-testid="progress-enterprise-main-panels"
          >
            <View
              style={{
                flex: 1.05,
                borderRadius: 18,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.card,
                padding: 16,
                gap: 12,
              }}
              testID="progress-enterprise-category-panel"
              data-testid="progress-enterprise-category-panel"
            >
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} testID="progress-enterprise-category-title" data-testid="progress-enterprise-category-title">
                {tx('progress.enterprise.categories.title', 'Category Mastery')}
              </Text>

              {categoryRows.length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 12 }} testID="progress-enterprise-category-empty" data-testid="progress-enterprise-category-empty">
                  {tx('progress.enterprise.categories.empty', 'No category mastery data available yet.')}
                </Text>
              ) : (
                categoryRows.map((row, idx) => {
                  const barWidth = `${Math.max(4, Math.min(100, row.value))}%`;
                  const color = FEATURE_COLORS[idx % FEATURE_COLORS.length];
                  return (
                    <View key={row.key} style={{ gap: 6 }} testID={`progress-enterprise-category-row-${row.key}`} data-testid={`progress-enterprise-category-row-${row.key}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <Ionicons name={(CATEGORY_ICON[row.key] || 'analytics-outline') as any} size={13} color={colors.textMuted} />
                          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{row.key.replace(/-/g, ' ')}</Text>
                        </View>
                        <Text style={{ color, fontSize: 11, fontWeight: '800' }}>{row.value}%</Text>
                      </View>
                      <View style={{ height: 7, borderRadius: 999, backgroundColor: colors.surfaceHover || colors.cardMuted }}>
                        <View style={{ height: '100%', width: barWidth, borderRadius: 999, backgroundColor: color }} />
                      </View>
                    </View>
                  );
                })
              )}
            </View>

            <View
              style={{
                flex: 1,
                borderRadius: 18,
                borderWidth: 1,
                borderColor: colors.border,
                backgroundColor: colors.card,
                padding: 16,
                gap: 12,
              }}
              testID="progress-enterprise-feature-panel"
              data-testid="progress-enterprise-feature-panel"
            >
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} testID="progress-enterprise-feature-title" data-testid="progress-enterprise-feature-title">
                {tx('progress.enterprise.features.title', 'Top Tool Usage')}
              </Text>

              {topFeatures.length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 12 }} testID="progress-enterprise-feature-empty" data-testid="progress-enterprise-feature-empty">
                  {tx('progress.enterprise.features.empty', 'No tool usage data available yet.')}
                </Text>
              ) : (
                topFeatures.map((feature, idx) => {
                  const widthPct = `${Math.round((feature.count / maxFeatureCount) * 100)}%`;
                  return (
                    <View key={`${feature.name}-${idx}`} style={{ gap: 5 }} testID={`progress-enterprise-feature-row-${idx}`} data-testid={`progress-enterprise-feature-row-${idx}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>
                          {feature.name.replace(/-/g, ' ')}
                        </Text>
                        <Text style={{ color: feature.color, fontSize: 11, fontWeight: '800' }}>{feature.count}</Text>
                      </View>
                      <View style={{ height: 7, borderRadius: 999, backgroundColor: colors.surfaceHover || colors.cardMuted }}>
                        <View style={{ height: '100%', width: widthPct, borderRadius: 999, backgroundColor: feature.color }} />
                      </View>
                    </View>
                  );
                })
              )}
            </View>
          </View>

          <View
            style={{
              marginTop: 14,
              marginHorizontal: contentPadding,
              borderRadius: 18,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.card,
              padding: 16,
              gap: 10,
            }}
            testID="progress-enterprise-heatmap-panel"
            data-testid="progress-enterprise-heatmap-panel"
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} testID="progress-enterprise-heatmap-title" data-testid="progress-enterprise-heatmap-title">
                {tx('progress.enterprise.heatmap.title', 'Activity Heatmap')}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 11 }} testID="progress-enterprise-heatmap-window" data-testid="progress-enterprise-heatmap-window">
                {days} {tx('progress.enterprise.heatmap.dayWindow', 'day window')}
              </Text>
            </View>

            {dailyActivity.length === 0 ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }} testID="progress-enterprise-heatmap-empty" data-testid="progress-enterprise-heatmap-empty">
                {tx('progress.enterprise.heatmap.empty', 'No daily activity data available yet.')}
              </Text>
            ) : (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }} testID="progress-enterprise-heatmap-grid" data-testid="progress-enterprise-heatmap-grid">
                {dailyActivity.map((item, idx) => (
                  <View key={`${item.date}-${idx}`} style={{ alignItems: 'center', gap: 4 }}>
                    <HeatCell count={Number(item.count || 0)} colors={colors} />
                  </View>
                ))}
              </View>
            )}
          </View>

          <View
            style={{
              marginTop: 14,
              marginHorizontal: contentPadding,
              borderRadius: 18,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.card,
              padding: 16,
              gap: 12,
            }}
            testID="progress-enterprise-session-panel"
            data-testid="progress-enterprise-session-panel"
          >
            <View style={{ flexDirection: isTablet ? 'column' : 'row', justifyContent: 'space-between', alignItems: isTablet ? 'flex-start' : 'center', gap: 10 }}>
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} testID="progress-enterprise-session-title" data-testid="progress-enterprise-session-title">
                {tx('progress.enterprise.sessions.title', 'Recent Activity Timeline')}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} testID="progress-enterprise-category-filter-group" data-testid="progress-enterprise-category-filter-group">
                {['all', ...availableCategories].map((cat) => {
                  const selected = categoryFilter === cat;
                  return (
                    <TouchableOpacity accessibilityLabel="Set category filter in executive progress workspace button"
                      key={cat}
                      onPress={() => setCategoryFilter(cat)}
                      style={{
                        borderRadius: 999,
                        borderWidth: 1,
                        borderColor: selected ? colors.primary : colors.border,
                        backgroundColor: selected ? `${colors.primary}18` : colors.surface,
                        paddingHorizontal: 10,
                        paddingVertical: 5,
                      }}
                      testID={`progress-enterprise-category-filter-${cat}`}
                      data-testid={`progress-enterprise-category-filter-${cat}`}
                    >
                      <Text style={{ color: selected ? colors.primary : colors.textMuted, fontSize: 10, fontWeight: '800', textTransform: 'capitalize' }}>
                        {cat}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            {filteredSessions.length === 0 ? (
              <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16, alignItems: 'center', gap: 8 }} testID="progress-enterprise-session-empty" data-testid="progress-enterprise-session-empty">
                <Ionicons name="time-outline" size={20} color={colors.textMuted} />
                <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('progress.enterprise.sessions.empty', 'No sessions found for this filter.')}</Text>
              </View>
            ) : (
              filteredSessions.slice(0, 12).map((session, idx) => {
                const title = String(session?.summary || session?.scenario_title || tx('progress.enterprise.sessions.defaultTitle', 'AI Session')).trim();
                const dateText = session?.timestamp
                  ? new Date(session.timestamp).toLocaleString()
                  : tx('progress.enterprise.notAvailable', 'Not available');
                const category = String(session?.category || tx('progress.enterprise.sessions.uncategorized', 'uncategorized'));

                return (
                  <View
                    key={`${session?.session_id || session?.id || idx}`}
                    style={{
                      borderRadius: 14,
                      borderWidth: 1,
                      borderColor: colors.border,
                      backgroundColor: colors.surface,
                      padding: 12,
                      gap: 6,
                    }}
                    testID={`progress-enterprise-session-row-${idx}`}
                    data-testid={`progress-enterprise-session-row-${idx}`}
                  >
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', flex: 1 }}>{title}</Text>
                      <View style={{ borderRadius: 8, backgroundColor: `${colors.primary}16`, borderWidth: 1, borderColor: `${colors.primary}45`, paddingHorizontal: 8, paddingVertical: 3 }}>
                        <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800', textTransform: 'capitalize' }}>{category}</Text>
                      </View>
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>{dateText}</Text>
                    {session?.overall_feedback ? (
                      <Text style={{ color: colors.textSec || colors.textMuted, fontSize: 11 }} numberOfLines={2}>
                        {String(session.overall_feedback)}
                      </Text>
                    ) : null}
                  </View>
                );
              })
            )}
          </View>

          <View style={{ marginTop: 14, marginHorizontal: contentPadding, flexDirection: isTablet ? 'column' : 'row', gap: 10 }}>
            <TouchableOpacity accessibilityLabel="Progress enterprise call to action practice button"
              onPress={() => router.push('/practice')}
              style={{
                flex: 1,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: `${colors.successText || colors.success}45`,
                backgroundColor: `${colors.successText || colors.success}16`,
                paddingVertical: 13,
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'row',
                gap: 8,
              }}
              testID="progress-enterprise-cta-practice"
              data-testid="progress-enterprise-cta-practice"
            >
              <Ionicons name="chatbubbles" size={15} color={colors.successText || colors.success} />
              <Text style={{ color: colors.successText || colors.success, fontSize: 12, fontWeight: '800' }}>
                {tx('progress.enterprise.cta.practice', 'Start Practice Session')}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity accessibilityLabel="Progress enterprise call to action learning hub button"
              onPress={() => router.push('/ai-learning-hub')}
              style={{
                flex: 1,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: `${colors.info || colors.primary}45`,
                backgroundColor: `${colors.info || colors.primary}16`,
                paddingVertical: 13,
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'row',
                gap: 8,
              }}
              testID="progress-enterprise-cta-learning-hub"
              data-testid="progress-enterprise-cta-learning-hub"
            >
              <Ionicons name="school" size={15} color={colors.info || colors.primary} />
              <Text style={{ color: colors.info || colors.primary, fontSize: 12, fontWeight: '800' }}>
                {tx('progress.enterprise.cta.learningHub', 'Open Learning Hub')}
              </Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    </AppShell>
  );
}
