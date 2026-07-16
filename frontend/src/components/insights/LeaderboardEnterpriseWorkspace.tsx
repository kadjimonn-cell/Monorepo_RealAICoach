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
import { LeaderboardSkeleton } from '../SkeletonLoaders';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';

type Period = 'all_time' | 'weekly' | 'monthly';

const TIER_COLORS: Record<string, string> = {
  starter: 'var(--app-primary)',
  bronze: 'var(--app-primary)',
  silver: 'var(--app-primary)',
  gold: 'var(--app-primary)',
};

export default function LeaderboardEnterpriseWorkspace() {
  const { colors } = useTheme();
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
  const [period, setPeriod] = useState<Period>('all_time');
  const [leaderboard, setLeaderboard] = useState<any>(null);
  const [activityFeed, setActivityFeed] = useState<any[]>([]);
  const [referralData, setReferralData] = useState<any>(null);
  const [socialProof, setSocialProof] = useState<any>(null);

  const loadData = useCallback(async () => {
    try {
      const [lbRes, feedRes, refRes, socialRes] = await Promise.allSettled([
        api.get(`/gamification/leaderboard?period=${period}`, { silentLoading: true }),
        api.get('/gamification/activity-feed?limit=12', { silentLoading: true }),
        api.get('/referrals/leaderboard-highlights', { silentLoading: true }),
        api.get('/referrals/recent-activity', { silentLoading: true }),
      ]);

      if (lbRes.status === 'fulfilled') setLeaderboard(lbRes.value?.data || null);
      if (feedRes.status === 'fulfilled') setActivityFeed(feedRes.value?.data?.feed || []);
      if (refRes.status === 'fulfilled') setReferralData(refRes.value?.data || null);
      if (socialRes.status === 'fulfilled') setSocialProof(socialRes.value?.data || null);

      api.post('/gamification/check-achievements').catch(() => undefined);
    } catch {
      setLeaderboard(null);
      setActivityFeed([]);
      setReferralData(null);
      setSocialProof(null);
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

  const myRank = leaderboard?.my_rank || 0;
  const myLevel = leaderboard?.level?.level || 1;
  const myProgress = Number(leaderboard?.level?.progress || 0);
  const topRows = useMemo(() => {
    const rows = Array.isArray(referralData?.leaderboard) ? referralData.leaderboard : [];
    return rows;
  }, [referralData?.leaderboard]);

  if (loading) {
    return (
      <AppShell>
        <LeaderboardSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top']} data-testid="leaderboard-enterprise-page" testID="leaderboard-enterprise-page">
        <ScrollView
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          contentContainerStyle={{
            paddingBottom: 80,
            maxWidth: 1240,
            width: '100%' as any,
            alignSelf: 'center' as any,
          }}
          data-testid="leaderboard-enterprise-scroll"
          testID="leaderboard-enterprise-scroll"
        >
          <View
            style={{
              marginTop: 14,
              marginHorizontal: pad,
              borderRadius: 20,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.card,
              padding: isDesktop ? 22 : 16,
              gap: 12,
            }}
            data-testid="leaderboard-enterprise-header"
            testID="leaderboard-enterprise-header"
          >
            <Text style={{ color: colors.text, fontSize: isDesktop ? 38 : 30, fontWeight: '900', letterSpacing: -0.7 }} data-testid="leaderboard-enterprise-title" testID="leaderboard-enterprise-title">
              {tx('leaderboard.enterprise.title', 'Leaderboard Intelligence Center')}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 2 }} data-testid="leaderboard-enterprise-subtitle" testID="leaderboard-enterprise-subtitle">
              {tx('leaderboard.enterprise.subtitle', 'Live performance standings, referral champions, and competitive activity signals.')}
            </Text>

            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="leaderboard-enterprise-period-group" testID="leaderboard-enterprise-period-group">
              {[
                { id: 'all_time', label: tx('leaderboard.enterprise.period.all', 'All Time') },
                { id: 'weekly', label: tx('leaderboard.enterprise.period.weekly', 'This Week') },
                { id: 'monthly', label: tx('leaderboard.enterprise.period.monthly', 'This Month') },
              ].map((item) => {
                const active = period === item.id;
                return (
                  <TouchableOpacity accessibilityLabel="Set period in leaderboard enterprise workspace button"
                    key={item.id}
                    onPress={() => setPeriod(item.id as Period)}
                    style={{
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: active ? colors.primary : colors.border,
                      backgroundColor: active ? `${colors.primary}18` : colors.surface,
                      paddingHorizontal: 12,
                      paddingVertical: 7,
                    }}
                    data-testid={`leaderboard-enterprise-period-${item.id}`}
                    testID={`leaderboard-enterprise-period-${item.id}`}
                  >
                    <Text style={{ color: active ? colors.primary : colors.textMuted, fontSize: 11, fontWeight: '800' }}>
                      {item.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={{ marginTop: 14, marginHorizontal: pad, borderRadius: 18, borderWidth: 1, borderColor: `${colors.primary}44`, backgroundColor: colors.card, padding: 16, gap: 12 }} data-testid="leaderboard-enterprise-rank-hero" testID="leaderboard-enterprise-rank-hero">
            <View style={{ flexDirection: isTablet ? 'column' : 'row', alignItems: isTablet ? 'flex-start' : 'center', justifyContent: 'space-between', gap: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <View style={{ width: 74, height: 74, borderRadius: 37, borderWidth: 3, borderColor: colors.primary, alignItems: 'center', justifyContent: 'center', backgroundColor: `${colors.primary}14` }}>
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{tx('leaderboard.enterprise.rankLabel', 'RANK')}</Text>
                  <Text style={{ color: colors.primary, fontSize: 28, fontWeight: '900', marginTop: -2 }} data-testid="leaderboard-enterprise-my-rank" testID="leaderboard-enterprise-my-rank">
                    #{myRank}
                  </Text>
                </View>

                <View>
                  <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="leaderboard-enterprise-level" testID="leaderboard-enterprise-level">
                    {tx('leaderboard.enterprise.level', 'Level')} {myLevel}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('leaderboard.enterprise.totalXp', 'Total XP')}: {leaderboard?.total_xp || 0}</Text>
                </View>
              </View>

              <View style={{ minWidth: 220, width: isTablet ? '100%' : 240 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 5 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('leaderboard.enterprise.progressToNext', 'Progress to next level')}</Text>
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{myProgress}%</Text>
                </View>
                <View style={{ height: 8, borderRadius: 999, backgroundColor: colors.surfaceHover || colors.cardMuted }}>
                  <View style={{ height: '100%', width: `${Math.min(100, Math.max(0, myProgress))}%`, borderRadius: 999, backgroundColor: colors.primary }} />
                </View>
              </View>
            </View>
          </View>

          <View style={{ marginTop: 14, marginHorizontal: pad, flexDirection: isDesktop ? 'row' : 'column', gap: 12 }} data-testid="leaderboard-enterprise-main-row" testID="leaderboard-enterprise-main-row">
            <View style={{ flex: 1.1, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }} data-testid="leaderboard-enterprise-table-panel" testID="leaderboard-enterprise-table-panel">
              <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('leaderboard.enterprise.table.title', 'Referral Champions')}</Text>
              </View>
              {topRows.length === 0 ? (
                <View style={{ padding: 16 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('leaderboard.enterprise.table.empty', 'No leaderboard entries available yet.')}</Text>
                </View>
              ) : (
                topRows.slice(0, 12).map((row: any, idx: number) => {
                  const tierKey = String(row?.tier?.id || 'starter').toLowerCase();
                  const tierColor = TIER_COLORS[tierKey] || colors.primary;
                  return (
                    <View key={`${row?.rank || idx}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, backgroundColor: row?.is_self ? `${colors.primary}10` : 'transparent' }} data-testid={`leaderboard-enterprise-row-${idx}`} testID={`leaderboard-enterprise-row-${idx}`}>
                      <Text style={{ width: 36, color: colors.text, fontSize: 13, fontWeight: '800' }}>#{row?.rank || idx + 1}</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: row?.is_self ? colors.primary : colors.text, fontSize: 12, fontWeight: '800' }}>
                          {row?.is_self ? `${row?.display_name || 'You'} (You)` : row?.display_name || tx('leaderboard.enterprise.unknown', 'Unknown')}
                        </Text>
                        <Text style={{ color: colors.textMuted, fontSize: 10 }}>{row?.total_signups || 0} {tx('leaderboard.enterprise.referrals', 'referrals')}</Text>
                      </View>
                      <View style={{ borderRadius: 8, backgroundColor: `${tierColor}20`, paddingHorizontal: 8, paddingVertical: 3 }}>
                        <Text style={{ color: tierColor, fontSize: 10, fontWeight: '800' }}>{row?.tier?.name || 'Starter'}</Text>
                      </View>
                    </View>
                  );
                })
              )}
            </View>

            <View style={{ flex: 1, gap: 12 }}>
              <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 10 }} data-testid="leaderboard-enterprise-activity-panel" testID="leaderboard-enterprise-activity-panel">
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('leaderboard.enterprise.activity.title', 'Recent Activity')}</Text>
                {(activityFeed || []).slice(0, 8).map((event: any, idx: number) => (
                  <View key={`${event?.id || idx}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`leaderboard-enterprise-activity-row-${idx}`} testID={`leaderboard-enterprise-activity-row-${idx}`}>
                    <Ionicons name="pulse-outline" size={13} color={colors.primary} />
                    <Text style={{ color: colors.text, fontSize: 11, flex: 1 }} numberOfLines={2}>{event?.message || tx('leaderboard.enterprise.activity.update', 'Leaderboard update')}</Text>
                  </View>
                ))}
              </View>

              <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 10 }} data-testid="leaderboard-enterprise-social-proof-panel" testID="leaderboard-enterprise-social-proof-panel">
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('leaderboard.enterprise.socialProof.title', 'Social Proof Signals')}</Text>
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  {[
                    { label: tx('leaderboard.enterprise.socialProof.activeReferrers', 'Active Referrers'), value: socialProof?.stats?.total_referrers || 0, icon: 'people', tone: colors.primary },
                    { label: tx('leaderboard.enterprise.socialProof.signups', 'Total Signups'), value: socialProof?.stats?.total_signups || 0, icon: 'person-add', tone: colors.successText || 'var(--app-success)' },
                    { label: tx('leaderboard.enterprise.socialProof.weeklySignups', 'This Week'), value: socialProof?.stats?.this_week_signups || 0, icon: 'trending-up', tone: colors.warningText || 'var(--app-warning)' },
                  ].map((stat, idx) => (
                    <View key={idx} style={{ flex: 1, minWidth: 120, borderRadius: 12, borderWidth: 1, borderColor: `${stat.tone}45`, backgroundColor: `${stat.tone}15`, padding: 10, gap: 4 }} data-testid={`leaderboard-enterprise-stat-${idx}`} testID={`leaderboard-enterprise-stat-${idx}`}>
                      <Ionicons name={stat.icon as any} size={13} color={stat.tone} />
                      <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900' }}>{stat.value}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{stat.label}</Text>
                    </View>
                  ))}
                </View>
              </View>
            </View>
          </View>

          <View style={{ marginTop: 14, marginHorizontal: pad, flexDirection: isTablet ? 'column' : 'row', gap: 10 }}>
            <TouchableOpacity accessibilityLabel="Leaderboard enterprise call to action referrals button"
              onPress={() => router.push('/referrals')}
              style={{
                flex: 1,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: `${colors.primary}45`,
                backgroundColor: `${colors.primary}16`,
                paddingVertical: 13,
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'row',
                gap: 8,
              }}
              data-testid="leaderboard-enterprise-cta-referrals"
              testID="leaderboard-enterprise-cta-referrals"
            >
              <Ionicons name="gift-outline" size={15} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('leaderboard.enterprise.cta.referrals', 'Open Referral Program')}</Text>
            </TouchableOpacity>

            <TouchableOpacity accessibilityLabel="Leaderboard enterprise call to action analytics button"
              onPress={() => router.push('/my-analytics')}
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
              data-testid="leaderboard-enterprise-cta-analytics"
              testID="leaderboard-enterprise-cta-analytics"
            >
              <Ionicons name="analytics-outline" size={15} color={colors.info || colors.primary} />
              <Text style={{ color: colors.info || colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('leaderboard.enterprise.cta.analytics', 'Open Analytics Center')}</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    </AppShell>
  );
}
