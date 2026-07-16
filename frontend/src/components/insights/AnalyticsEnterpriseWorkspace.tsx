import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  useWindowDimensions,
  Share,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../AppShell';
import { AnalyticsSkeleton } from '../SkeletonLoaders';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';
import { getShadow } from '../../utils/themeShadows';
import { SectionProgressRail } from '../progress/SectionProgressRail';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type AnalyticsPeriod = 7 | 30 | 90;

const MetricCard = ({
  label,
  value,
  hint,
  icon,
  tone,
  colors,
  dark,
  testId,
}: {
  label: string;
  value: string;
  hint: string;
  icon: string;
  tone: string;
  colors: any;
  dark: boolean;
  testId: string;
}) => (
  <View
    style={{
      flex: 1,
      minWidth: 190,
      borderRadius: 16,
      borderWidth: 1,
      borderColor: `${tone}55`,
      backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, dark ? 'A8' : 'D8') : colors.card,
      padding: 14,
      gap: 8,
      ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
      ...getShadow('sm', Boolean(dark)),
    }}
    data-testid={testId}
    testID={testId}
  >
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{label}</Text>
      <View style={{ borderRadius: 999, backgroundColor: `${tone}20`, padding: 6 }}>
        <Ionicons name={icon as any} size={13} color={tone} />
      </View>
    </View>
    <Text style={{ color: colors.text, fontSize: 24, fontWeight: '900' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>
      {value}
    </Text>
    <Text style={{ color: colors.textMuted, fontSize: 11 }}>{hint}</Text>
  </View>
);

export default function AnalyticsEnterpriseWorkspace() {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback(
    (key: string, fallback: string) => {
      const value = t(key);
      return value === key ? fallback : value;
    },
    [t],
  );
  const router = useRouter();
  const { width } = useWindowDimensions();

  const isDesktop = width >= 1200;
  const isTablet = width >= 768 && width < 1200;
  const pad = isDesktop ? 28 : isTablet ? 22 : 14;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [period, setPeriod] = useState<AnalyticsPeriod>(30);

  const [dashboard, setDashboard] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [radar, setRadar] = useState<any>(null);
  const [recommendations, setRecommendations] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [achievements, setAchievements] = useState<any>(null);
  const [activeSection, setActiveSection] = useState('overview');
  const scrollRef = useRef<ScrollView | null>(null);
  const sectionOffsetsRef = useRef<Record<string, number>>({});
  const activeSectionRef = useRef('overview');
  const showProgressRail = width >= 768;

  const loadData = useCallback(async () => {
    try {
      const [d, u, r, rec, rep, ach] = await Promise.allSettled([
        api.get('/user-analytics/dashboard', { silentLoading: true }),
        api.get(`/user-analytics/ai-usage-patterns?days=${period}`, { silentLoading: true }),
        api.get('/user-analytics/skill-radar', { silentLoading: true }),
        api.get('/user-analytics/recommendations', { silentLoading: true }),
        api.get('/user-analytics/weekly-report', { silentLoading: true }),
        api.get('/user-analytics/achievements', { silentLoading: true }),
      ]);

      if (d.status === 'fulfilled') setDashboard(d.value?.data || null);
      if (u.status === 'fulfilled') setUsage(u.value?.data || null);
      if (r.status === 'fulfilled') setRadar(r.value?.data || null);
      if (rec.status === 'fulfilled') setRecommendations(rec.value?.data || null);
      if (rep.status === 'fulfilled') setReport(rep.value?.data || null);
      if (ach.status === 'fulfilled') setAchievements(ach.value?.data || null);
    } catch {
      setDashboard(null);
      setUsage(null);
      setRadar(null);
      setRecommendations(null);
      setReport(null);
      setAchievements(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [period]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const interval = setInterval(() => {
      void loadData();
    }, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const onRefresh = () => {
    setRefreshing(true);
    void loadData();
  };

  const setSectionOffset = (key: string, y: number) => {
    sectionOffsetsRef.current[key] = y;
  };

  const scrollToSection = (key: string) => {
    const y = sectionOffsetsRef.current[key];
    if (typeof y !== 'number' || !Number.isFinite(y)) return;
    scrollRef.current?.scrollTo?.({ y: Math.max(0, y - 70), animated: true });
  };

  const onAnalyticsScroll = (event: any) => {
    const y = event?.nativeEvent?.contentOffset?.y || 0;
    const ordered = Object.entries(sectionOffsetsRef.current)
      .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
      .sort((a, b) => a[1] - b[1]);

    let next = 'overview';
    for (const [key, offsetY] of ordered) {
      if (y + 140 >= offsetY) {
        next = key;
      }
    }

    if (next !== activeSectionRef.current) {
      activeSectionRef.current = next;
      setActiveSection(next);
    }
  };

  const onShareReport = async () => {
    if (!report?.highlights) return;
    const h = report.highlights;
    const message = [
      tx('analytics.enterprise.share.title', 'My RealAICoach Weekly Analytics'),
      `${tx('analytics.enterprise.share.requests', 'AI Requests')}: ${h.ai_requests ?? 0}`,
      `${tx('analytics.enterprise.share.conversations', 'Conversations')}: ${h.conversations ?? 0}`,
      `${tx('analytics.enterprise.share.streak', 'Streak')}: ${h.streak ?? 0}`,
      `${tx('analytics.enterprise.share.level', 'Level')}: ${h.level ?? 1}`,
      `${tx('analytics.enterprise.share.topFeature', 'Top Feature')}: ${h.top_feature || tx('analytics.enterprise.notAvailable', 'Not available')}`,
    ].join('\n');

    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && (navigator as any)?.share) {
        await (navigator as any).share({ title: tx('analytics.enterprise.share.nativeTitle', 'Weekly Analytics'), text: message });
        return;
      }
      await Share.share({ title: tx('analytics.enterprise.share.nativeTitle', 'Weekly Analytics'), message });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/insights/AnalyticsEnterpriseWorkspace.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const summary = dashboard?.summary || {};
  const coaching = dashboard?.coaching || {};
  const dailyTrend = Array.isArray(usage?.daily_trend) ? usage.daily_trend : [];
  const maxDailyRequests = dailyTrend.length ? Math.max(...dailyTrend.map((d: any) => Number(d?.requests || 0)), 1) : 1;

  const topFeatures = useMemo(() => {
    const rows = Array.isArray(usage?.by_feature) ? usage.by_feature : [];
    return rows.slice(0, 6);
  }, [usage?.by_feature]);

  if (loading) {
    return (
      <AppShell>
        <AnalyticsSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: 'transparent' }} edges={['top']} data-testid="analytics-enterprise-page" testID="analytics-enterprise-page">
        <ScrollView
          ref={scrollRef}
          onScroll={onAnalyticsScroll}
          scrollEventThrottle={16}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          contentContainerStyle={{
            paddingBottom: 80,
            maxWidth: 1240,
            width: '100%' as any,
            alignSelf: 'center' as any,
          }}
          data-testid="analytics-enterprise-scroll"
          testID="analytics-enterprise-scroll"
        >
          <View
            onLayout={(e) => setSectionOffset('overview', e.nativeEvent.layout.y)}
            style={{
              marginTop: 14,
              marginHorizontal: pad,
              borderRadius: 20,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'AE' : 'DE') : colors.card,
              padding: isDesktop ? 22 : 16,
              gap: 12,
              ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}),
            }}
            data-testid="analytics-enterprise-header"
            testID="analytics-enterprise-header"
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
              <View style={{ maxWidth: 960 }}>
                <Text style={{ color: colors.text, fontSize: isDesktop ? 38 : 30, fontWeight: '900', letterSpacing: -0.7 }} data-testid="analytics-enterprise-title" testID="analytics-enterprise-title">
                  {tx('analytics.enterprise.title', 'Analytics Intelligence Center')}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 4, lineHeight: 19 }} data-testid="analytics-enterprise-subtitle" testID="analytics-enterprise-subtitle">
                  {tx('analytics.enterprise.subtitle', 'Enterprise-grade insights from your real platform usage, skill growth, and outcomes.')}
                </Text>
              </View>

              <TouchableOpacity accessibilityLabel="Analytics enterprise share button"
                onPress={onShareReport}
                style={{
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: `${colors.primary}55`,
                  backgroundColor: `${colors.primary}16`,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                }}
                data-testid="analytics-enterprise-share-button"
                testID="analytics-enterprise-share-button"
              >
                <Ionicons name="share-outline" size={14} color={colors.primary} />
                <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{tx('analytics.enterprise.share', 'Share')}</Text>
              </TouchableOpacity>
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="analytics-enterprise-period-group" testID="analytics-enterprise-period-group">
              {[7, 30, 90].map((item) => {
                const active = period === item;
                return (
                  <TouchableOpacity accessibilityLabel="Set period in analytics enterprise workspace button"
                    key={item}
                    onPress={() => setPeriod(item as AnalyticsPeriod)}
                    style={{
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: active ? colors.primary : colors.border,
                      backgroundColor: active ? `${colors.primary}18` : colors.surface,
                      paddingHorizontal: 12,
                      paddingVertical: 7,
                    }}
                    data-testid={`analytics-enterprise-period-${item}`}
                    testID={`analytics-enterprise-period-${item}`}
                  >
                    <Text style={{ color: active ? colors.primary : colors.textMuted, fontSize: 11, fontWeight: '800' }}>
                      {item}d
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View onLayout={(e) => setSectionOffset('metrics', e.nativeEvent.layout.y)} style={{ marginTop: 14, marginHorizontal: pad, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="analytics-enterprise-metrics" testID="analytics-enterprise-metrics">
            <MetricCard
              label={tx('analytics.enterprise.cards.requests', 'AI Requests (7d)')}
              value={String(summary?.ai_requests_7d || 0)}
              hint={tx('analytics.enterprise.cards.requestsHint', 'Total requests in current 7-day window')}
              icon="flash"
              tone={colors.primary}
              colors={colors}
              dark={darkMode}
              testId="analytics-enterprise-card-requests"
            />
            <MetricCard
              label={tx('analytics.enterprise.cards.conversations', 'Conversations')}
              value={String(summary?.conversations_total || 0)}
              hint={tx('analytics.enterprise.cards.conversationsHint', 'Total AI conversation sessions')}
              icon="chatbubbles"
              tone={colors.successText || 'var(--app-success)'}
              colors={colors}
              dark={darkMode}
              testId="analytics-enterprise-card-conversations"
            />
            <MetricCard
              label={tx('analytics.enterprise.cards.streak', 'Current Streak')}
              value={`${coaching?.current_streak || 0}d`}
              hint={tx('analytics.enterprise.cards.streakHint', 'Consecutive active days')}
              icon="flame"
              tone={colors.warningText || 'var(--app-warning)'}
              colors={colors}
              dark={darkMode}
              testId="analytics-enterprise-card-streak"
            />
            <MetricCard
              label={tx('analytics.enterprise.cards.level', 'Level')}
              value={`L${coaching?.level || 1}`}
              hint={`${tx('analytics.enterprise.cards.xp', 'XP')}: ${coaching?.xp || 0}`}
              icon="trophy"
              tone={colors.purpleText || colors.accent || colors.primary}
              colors={colors}
              dark={darkMode}
              testId="analytics-enterprise-card-level"
            />
          </View>

          <View onLayout={(e) => setSectionOffset('usage', e.nativeEvent.layout.y)} style={{ marginTop: 14, marginHorizontal: pad, flexDirection: isDesktop ? 'row' : 'column', gap: 12 }} data-testid="analytics-enterprise-usage-skills-row" testID="analytics-enterprise-usage-skills-row">
            <View style={{ flex: 1.1, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'A8' : 'DA') : colors.card, padding: 16, gap: 12, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="analytics-enterprise-usage-panel" testID="analytics-enterprise-usage-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('analytics.enterprise.usage.title', 'Daily Usage Trend')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: 150 }} data-testid="analytics-enterprise-usage-bars" testID="analytics-enterprise-usage-bars">
                {dailyTrend.slice(-(isDesktop ? 24 : 12)).map((row: any, idx: number) => {
                  const h = Math.max(4, Math.round((Number(row?.requests || 0) / maxDailyRequests) * 100));
                  return (
                    <View key={`${row?.date || idx}`} style={{ flex: 1, alignItems: 'center' }}>
                      <View style={{ width: '86%', height: `${h}%`, borderRadius: 6, backgroundColor: Number(row?.requests || 0) > 0 ? colors.primary : colors.surfaceHover || colors.cardMuted }} />
                    </View>
                  );
                })}
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>{dailyTrend[0]?.date || ''}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>{dailyTrend[dailyTrend.length - 1]?.date || ''}</Text>
              </View>
            </View>

            <View style={{ flex: 1, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'A8' : 'DA') : colors.card, padding: 16, gap: 12, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="analytics-enterprise-skills-panel" testID="analytics-enterprise-skills-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('analytics.enterprise.skills.title', 'Skill Performance')}</Text>
              {(radar?.skills || []).slice(0, 6).map((skill: any, idx: number) => {
                const score = Number(skill?.score || 0);
                const name = String(skill?.skill || tx('analytics.enterprise.skills.unknown', 'Unknown')).replace(/_/g, ' ');
                return (
                  <View key={`${skill?.skill || idx}`} style={{ gap: 5 }} data-testid={`analytics-enterprise-skill-row-${idx}`} testID={`analytics-enterprise-skill-row-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{name}</Text>
                      <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{score}/100</Text>
                    </View>
                    <View style={{ height: 7, borderRadius: 999, backgroundColor: colors.surfaceHover || colors.cardMuted }}>
                      <View style={{ height: '100%', width: `${Math.min(100, Math.max(0, score))}%`, borderRadius: 999, backgroundColor: colors.primary }} />
                    </View>
                  </View>
                );
              })}
            </View>
          </View>

          <View onLayout={(e) => setSectionOffset('features', e.nativeEvent.layout.y)} style={{ marginTop: 14, marginHorizontal: pad, flexDirection: isDesktop ? 'row' : 'column', gap: 12 }} data-testid="analytics-enterprise-secondary-row" testID="analytics-enterprise-secondary-row">
            <View style={{ flex: 1, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'A8' : 'DA') : colors.card, padding: 16, gap: 12, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="analytics-enterprise-features-panel" testID="analytics-enterprise-features-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('analytics.enterprise.features.title', 'Top Features')}</Text>
              {topFeatures.length === 0 ? (
                <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('analytics.enterprise.features.empty', 'No feature usage data available yet.')}</Text>
              ) : (
                topFeatures.map((feature: any, idx: number) => {
                  const top = Number(topFeatures[0]?.requests || 1);
                  const req = Number(feature?.requests || 0);
                  const widthPct = `${Math.max(4, Math.round((req / top) * 100))}%`;
                  return (
                    <View key={`${feature?.feature || idx}`} style={{ gap: 5 }} data-testid={`analytics-enterprise-feature-row-${idx}`} testID={`analytics-enterprise-feature-row-${idx}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{String(feature?.feature || '').replace(/[-_]/g, ' ')}</Text>
                        <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{req}</Text>
                      </View>
                      <View style={{ height: 7, borderRadius: 999, backgroundColor: colors.surfaceHover || colors.cardMuted }}>
                        <View style={{ height: '100%', width: widthPct, borderRadius: 999, backgroundColor: colors.primary }} />
                      </View>
                    </View>
                  );
                })
              )}
            </View>

            <View style={{ flex: 1, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'A8' : 'DA') : colors.card, padding: 16, gap: 10, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="analytics-enterprise-achievements-panel" testID="analytics-enterprise-achievements-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('analytics.enterprise.achievements.title', 'Achievements')}</Text>
              {(achievements?.achievements || []).slice(0, 6).map((achievement: any, idx: number) => {
                const unlocked = Boolean(achievement?.unlocked);
                return (
                  <View key={`${achievement?.id || idx}`} style={{ borderRadius: 12, borderWidth: 1, borderColor: unlocked ? `${colors.successText || 'var(--app-success)'}45` : colors.border, backgroundColor: unlocked ? `${colors.successText || 'var(--app-success)'}12` : colors.surface, padding: 10, gap: 4 }} data-testid={`analytics-enterprise-achievement-row-${idx}`} testID={`analytics-enterprise-achievement-row-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{achievement?.title || tx('analytics.enterprise.achievements.untitled', 'Achievement')}</Text>
                      <Ionicons name={unlocked ? 'checkmark-circle' : 'lock-closed'} size={14} color={unlocked ? colors.successText || 'var(--app-success)' : colors.textMuted} />
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 11 }}>{achievement?.description || tx('analytics.enterprise.notAvailable', 'Not available')}</Text>
                  </View>
                );
              })}
            </View>
          </View>

          <View onLayout={(e) => setSectionOffset('recommendations', e.nativeEvent.layout.y)} style={{ marginTop: 14, marginHorizontal: pad, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, darkMode ? 'A8' : 'DA') : colors.card, padding: 16, gap: 10, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="analytics-enterprise-recommendations-panel" testID="analytics-enterprise-recommendations-panel">
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('analytics.enterprise.recommendations.title', 'Recommended Next Actions')}</Text>
            {(recommendations?.recommendations || []).slice(0, 4).map((row: any, idx: number) => (
              <TouchableOpacity
                key={`${row?.title || idx}`}
                onPress={() => row?.action_route ? router.push(row.action_route) : null}
                style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10 }}
                data-testid={`analytics-enterprise-recommendation-${idx}`}
                testID={`analytics-enterprise-recommendation-${idx}`}
              >
                <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: `${row?.color || colors.primary}20`, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={(row?.icon || 'sparkles') as any} size={14} color={row?.color || colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{row?.title || tx('analytics.enterprise.notAvailable', 'Not available')}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11 }} numberOfLines={2}>{row?.description || ''}</Text>
                </View>
                <Ionicons name="chevron-forward" size={14} color={colors.textMuted} />
              </TouchableOpacity>
            ))}
          </View>

          <View onLayout={(e) => setSectionOffset('actions', e.nativeEvent.layout.y)} style={{ marginTop: 14, marginHorizontal: pad, flexDirection: isTablet ? 'column' : 'row', gap: 10 }}>
            <TouchableOpacity accessibilityLabel="Analytics enterprise call to action leaderboard button"
              onPress={() => router.push('/leaderboard')}
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
              data-testid="analytics-enterprise-cta-leaderboard"
              testID="analytics-enterprise-cta-leaderboard"
            >
              <Ionicons name="podium" size={15} color={colors.info || colors.primary} />
              <Text style={{ color: colors.info || colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('analytics.enterprise.cta.leaderboard', 'Open Leaderboard')}</Text>
            </TouchableOpacity>

            <TouchableOpacity accessibilityLabel="Analytics enterprise call to action progress button"
              onPress={() => router.push('/progress')}
              style={{
                flex: 1,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: `${colors.successText || 'var(--app-success)'}45`,
                backgroundColor: `${colors.successText || 'var(--app-success)'}16`,
                paddingVertical: 13,
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'row',
                gap: 8,
              }}
              data-testid="analytics-enterprise-cta-progress"
              testID="analytics-enterprise-cta-progress"
            >
              <Ionicons name="trending-up" size={15} color={colors.successText || 'var(--app-success)'} />
              <Text style={{ color: colors.successText || 'var(--app-success)', fontSize: 12, fontWeight: '800' }}>{tx('analytics.enterprise.cta.progress', 'Open Progress Center')}</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>

        <SectionProgressRail
          visible={showProgressRail}
          colors={colors}
          railTestId="analytics-progress-rail"
          activeId={activeSection}
          onSelect={scrollToSection}
          top={124}
          right={14}
          items={[
            { id: 'overview', label: 'Overview' },
            { id: 'metrics', label: 'Metrics' },
            { id: 'usage', label: 'Usage' },
            { id: 'features', label: 'Features' },
            { id: 'recommendations', label: 'Recommendations' },
            { id: 'actions', label: 'Actions' },
          ]}
        />
      </SafeAreaView>
    </AppShell>
  );
}
