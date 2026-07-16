import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTheme } from '../../context/ThemeContext';
import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

const getPalette = (darkMode: boolean) => {
  const AC = getAdminColors(darkMode);
  return {
    bg: AC.bg,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    muted: AC.textMuted,
    sec: AC.textSec,
    green: AC.success,
    red: AC.error,
    blue: AC.primary,
    yellow: AC.warning,
    purple: AC.purple,
    cyan: AC.info,
    success: AC.success,
    emerald: AC.success,
    amber: AC.warning,
    rose: AC.error,
  };
};

let C = getPalette(false);

const getSegmentColors = (palette: any): Record<string, string> => ({
  'Power User': palette.green,
  'Regular': palette.blue,
  'At Risk': palette.yellow,
  'Dormant': palette.muted,
});

function StatCard({ label, value, sub, icon, color }: { label: string; value: string | number; sub?: string; icon: string; color: string }) {
  return (
    <View data-testid={`stat-card-${label.toLowerCase().replace(/\s+/g, '-')}`} testID={`stat-card-${label.toLowerCase().replace(/\s+/g, '-')}`} style={{ flex: 1, minWidth: 160, backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text style={{ color: C.sec, fontSize: 12, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
        <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={14} color={color} />
        </View>
      </View>
      <Text style={{ color: C.text, fontSize: 24, fontWeight: '800', letterSpacing: -0.5 }}>{value}</Text>
      {sub && <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{sub}</Text>}
    </View>
  );
}

function BarChart({ data, maxVal, color, label }: { data: { date: string; count: number }[]; maxVal: number; color: string; label: string }) {
  if (!data.length) return null;
  return (
    <View data-testid="dau-trend-chart" testID="dau-trend-chart" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
      <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 120, gap: 2 }}>
        {data.map((d, i) => {
          const h = maxVal > 0 ? (d.count / maxVal) * 100 : 0;
          return (
            <View key={i} style={{ flex: 1, alignItems: 'center' }}>
              <Text style={{ color: C.muted, fontSize: 9, marginBottom: 2 }}>{d.count}</Text>
              <View style={{ width: '80%', height: `${Math.max(h, 2)}%`, backgroundColor: color, borderRadius: 3, minHeight: 2 }} />
              <Text style={{ color: C.muted, fontSize: 8, marginTop: 4, transform: [{ rotate: '-45deg' }] }}>{d.date.slice(0, 6)}</Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

function FunnelChart({ funnel }: { funnel: { stage: string; count: number; rate: number }[] }) {
  const maxCount = Math.max(...funnel.map(s => s.count), 1);
  const colors = [C.blue, C.cyan, C.green, C.success, C.purple];
  return (
    <View data-testid="referral-funnel-chart" testID="referral-funnel-chart" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
      <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 16 }}>{tx('admin.platformAnalyticsPanel.auto.text.001', 'Referral Conversion Funnel')}</Text>
      {funnel.map((s, i) => (
        <View key={i} style={{ marginBottom: 10 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
            <Text style={{ color: C.sec, fontSize: 12, fontWeight: '600' }}>{s.stage}</Text>
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{s.count} <Text style={{ color: C.muted, fontWeight: '500' }}>({s.rate}%)</Text></Text>
          </View>
          <View style={{ height: 8, backgroundColor: C.border, borderRadius: 4, overflow: 'hidden' }}>
            <View style={{ height: '100%', width: `${maxCount > 0 ? (s.count / maxCount) * 100 : 0}%`, backgroundColor: colors[i % colors.length], borderRadius: 4 }} />
          </View>
        </View>
      ))}
    </View>
  );
}

function HeatmapGrid({ heatmap }: { heatmap: { day: string; day_num: number; hour: number; count: number }[] }) {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const dayNumMap: Record<string, number> = { Mon: 2, Tue: 3, Wed: 4, Thu: 5, Fri: 6, Sat: 7, Sun: 1 };
  const maxCount = Math.max(...heatmap.map(h => h.count), 1);

  const getCount = (dayName: string, hour: number) => {
    const entry = heatmap.find(h => h.day_num === dayNumMap[dayName] && h.hour === hour);
    return entry?.count || 0;
  };

  const getColor = (count: number) => {
    if (count === 0) return C.border;
    const intensity = count / maxCount;
    if (intensity > 0.75) return 'var(--app-success)';
    if (intensity > 0.5) return 'var(--app-success)';
    if (intensity > 0.25) return 'var(--app-primary)';
    return 'var(--app-primary)';
  };

  return (
    <View data-testid="peak-hours-heatmap" testID="peak-hours-heatmap" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
      <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.platformAnalyticsPanel.auto.text.002', 'Peak Usage Hours')}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View>
          {/* Hour headers */}
          <View style={{ flexDirection: 'row', marginBottom: 4, paddingLeft: 40 }}>
            {Array.from({ length: 24 }, (_, i) => (
              <Text key={i} style={{ width: 22, textAlign: 'center', color: C.muted, fontSize: 8 }}>
                {i % 3 === 0 ? `${i}` : ''}
              </Text>
            ))}
          </View>
          {/* Rows */}
          {days.map(day => (
            <View key={day} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 2 }}>
              <Text style={{ width: 36, color: C.sec, fontSize: 10, fontWeight: '600' }}>{day}</Text>
              {Array.from({ length: 24 }, (_, hour) => {
                const count = getCount(day, hour);
                return (
                  <View key={hour} style={{
                    width: 20, height: 16, marginHorizontal: 1, borderRadius: 2,
                    backgroundColor: getColor(count),
                  }} />
                );
              })}
            </View>
          ))}
          {/* Legend */}
          <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 8, paddingLeft: 40, gap: 4 }}>
            <Text style={{ color: C.muted, fontSize: 9, marginRight: 4 }}>{tx('admin.platformAnalyticsPanel.auto.text.003', 'Less')}</Text>
            {[C.card, 'var(--app-primary)', 'var(--app-primary)', 'var(--app-success)', 'var(--app-success)'].map((c, i) => (
              <View key={i} style={{ width: 14, height: 10, borderRadius: 2, backgroundColor: c }} />
            ))}
            <Text style={{ color: C.muted, fontSize: 9, marginLeft: 4 }}>{tx('admin.platformAnalyticsPanel.auto.text.004', 'More')}</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

function SegmentPie({ segments }: { segments: Record<string, number> }) {
  const segmentColors = getSegmentColors(C);
  const total = Object.values(segments).reduce((a, b) => a + b, 0) || 1;
  return (
    <View data-testid="engagement-segments" testID="engagement-segments" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
      <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.platformAnalyticsPanel.auto.text.005', 'User Segments')}</Text>
      {Object.entries(segments).map(([seg, count]) => (
        <View key={seg} style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: segmentColors[seg] || C.muted }} />
              <Text style={{ color: C.sec, fontSize: 12, fontWeight: '600' }}>{seg}</Text>
            </View>
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{count} <Text style={{ color: C.muted, fontWeight: '500' }}>({Math.round(count / total * 100)}%)</Text></Text>
          </View>
          <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
            <View style={{ height: '100%', width: `${(count / total) * 100}%`, backgroundColor: segmentColors[seg] || C.muted, borderRadius: 3 }} />
          </View>
        </View>
      ))}
    </View>
  );
}

function FeatureAdoptionBars({ features }: { features: { feature: string; unique_users: number; adoption_rate: number }[] }) {
  return (
    <View data-testid="feature-adoption-bars" testID="feature-adoption-bars" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
      <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.platformAnalyticsPanel.auto.text.006', 'Feature Adoption')}</Text>
      {features.map((f, i) => (
        <View key={i} style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
            <Text style={{ color: C.sec, fontSize: 11, fontWeight: '600' }}>{f.feature}</Text>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{f.unique_users} <Text style={{ color: C.muted, fontWeight: '500' }}>({f.adoption_rate}%)</Text></Text>
          </View>
          <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
            <View style={{ height: '100%', width: `${Math.max(f.adoption_rate, 0.5)}%`, backgroundColor: C.cyan, borderRadius: 3 }} />
          </View>
        </View>
      ))}
    </View>
  );
}

type TabKey = 'overview' | 'funnel' | 'engagement' | 'trends';

export default function PlatformAnalyticsPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const { width } = useWindowDimensions();
  const isCompact = width < 900;
  C = getPalette(darkMode);
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  const { data: engagement, loading, refetch: refetchEngagement } = useLiveQuery('/admin/platform-analytics/engagement?days=30', { entity: 'platform_analytics', pollInterval: 60000 });
  const { data: featureAdoption, refetch: refetchFeatureAdoption } = useLiveQuery('/admin/platform-analytics/feature-adoption', { entity: 'platform_analytics', pollInterval: 60000 });
  const { data: peakHours, refetch: refetchPeakHours } = useLiveQuery('/admin/platform-analytics/peak-hours', { entity: 'platform_analytics', pollInterval: 60000 });
  const { data: funnel, refetch: refetchFunnel } = useLiveQuery('/admin/platform-analytics/referral-funnel', { entity: 'platform_analytics', pollInterval: 60000 });
  const { data: topReferrers, refetch: refetchTopReferrers } = useLiveQuery('/admin/platform-analytics/top-referrers', { entity: 'platform_analytics', pollInterval: 60000 });
  const { data: scores, refetch: refetchScores } = useLiveQuery('/admin/platform-analytics/engagement-scores?limit=20', { entity: 'platform_analytics', pollInterval: 60000 });
  const { data: cohort, refetch: refetchCohort } = useLiveQuery('/admin/platform-analytics/cohort-retention?weeks=8', { entity: 'platform_analytics', pollInterval: 60000 });
  const { data: trends, refetch: refetchTrends } = useLiveQuery('/admin/platform-analytics/engagement-trends?days=60', { entity: 'platform_analytics', pollInterval: 60000 });

  const loadData = async () => {
    await Promise.all([
      refetchEngagement(),
      refetchFeatureAdoption(),
      refetchPeakHours(),
      refetchFunnel(),
      refetchTopReferrers(),
      refetchScores(),
      refetchCohort(),
      refetchTrends(),
    ]);
  };

  const tabs: { key: TabKey; label: string; icon: string }[] = [
    { key: 'overview', label: 'Engagement', icon: 'pulse' },
    { key: 'trends', label: 'Trends & Retention', icon: 'trending-up' },
    { key: 'funnel', label: 'Referral Funnel', icon: 'git-merge' },
    { key: 'engagement', label: 'User Scoring', icon: 'people' },
  ];

  if (loading) {
    return (
      <View data-testid="platform-analytics-loading" testID="platform-analytics-loading" style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ color: C.muted, marginTop: 12 }}>{tx('admin.platformAnalyticsPanel.auto.text.007', 'Loading platform analytics...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView data-testid="platform-analytics-panel" testID="platform-analytics-panel" style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 16 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View>
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.5 }}>{tx('admin.platformAnalyticsPanel.auto.text.008', 'Platform Analytics')}</Text>
          <Text style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>{tx('admin.platformAnalyticsPanel.auto.text.009', 'Real-time engagement, funnels, and user scoring')}</Text>
        </View>
        <TouchableOpacity data-testid="refresh-analytics-btn" testID="refresh-analytics-btn" onPress={loadData} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: C.card, borderRadius: 8, borderWidth: 1, borderColor: C.border }}>
          <Ionicons name="refresh" size={14} color={C.blue} />
          <Text style={{ color: C.blue, fontSize: 12, fontWeight: '600' }}>{tx('admin.platformAnalyticsPanel.auto.text.010', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
        {tabs.map(t => (
          <TouchableOpacity
            key={t.key}
            data-testid={`tab-${t.key}`} testID={`tab-${t.key}`}
            onPress={() => setActiveTab(t.key)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              backgroundColor: activeTab === t.key ? (globalThis as any).__alphaColor(C.blue, '20') : C.card,
              borderWidth: 1, borderColor: activeTab === t.key ? (globalThis as any).__alphaColor(C.blue, '40') : C.border,
            }}
          >
            <Ionicons name={t.icon as any} size={14} color={activeTab === t.key ? C.blue : C.muted} />
            <Text style={{ color: activeTab === t.key ? C.blue : C.sec, fontSize: 12, fontWeight: '600' }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Tab: Overview / Engagement */}
      {activeTab === 'overview' && engagement && (
        <View style={{ gap: 14 }}>
          {/* KPI Cards */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <StatCard label="DAU" value={engagement.dau} sub="Daily Active Users" icon="people" color={C.blue} />
            <StatCard label="WAU" value={engagement.wau} sub="Weekly Active Users" icon="calendar" color={C.cyan} />
            <StatCard label="MAU" value={engagement.mau} sub="Monthly Active Users" icon="bar-chart" color={C.green} />
            <StatCard label="Stickiness" value={`${engagement.stickiness}%`} sub="DAU/MAU ratio" icon="heart" color={C.error} />
            <StatCard label="Sessions" value={engagement.total_sessions.toLocaleString()} sub="Last 30 days" icon="flash" color={C.yellow} />
            <StatCard label="Retention" value={`${engagement.retention_30d}%`} sub="30-day retention" icon="trending-up" color={C.successText} />
          </View>

          {/* DAU Trend */}
          {engagement.dau_trend?.length > 0 && (
            <BarChart
              data={engagement.dau_trend}
              maxVal={Math.max(...engagement.dau_trend.map((d: any) => d.count))}
              color={C.blue}
              label="Daily Active Users Trend"
            />
          )}

          {/* Peak Hours Heatmap */}
          {peakHours?.heatmap?.length > 0 && <HeatmapGrid heatmap={peakHours.heatmap} />}

          {/* Feature Adoption */}
          {featureAdoption?.features?.length > 0 && <FeatureAdoptionBars features={featureAdoption.features} />}
        </View>
      )}

      {/* Tab: Trends & Retention */}
      {activeTab === 'trends' && (
        <View style={{ gap: 14 }}>
          {/* Growth Summary */}
          {trends?.growth && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              <StatCard label="DAU Growth" value={`${trends.growth.dau > 0 ? '+' : ''}${trends.growth.dau}%`} sub={`${trends.period_days}d period`} icon="trending-up" color={trends.growth.dau >= 0 ? C.green : C.red} />
              <StatCard label="WAU Growth" value={`${trends.growth.wau > 0 ? '+' : ''}${trends.growth.wau}%`} sub={`${trends.period_days}d period`} icon="trending-up" color={trends.growth.wau >= 0 ? C.green : C.red} />
              <StatCard label="MAU Growth" value={`${trends.growth.mau > 0 ? '+' : ''}${trends.growth.mau}%`} sub={`${trends.period_days}d period`} icon="trending-up" color={trends.growth.mau >= 0 ? C.green : C.red} />
            </View>
          )}

          {/* DAU/WAU/MAU Trend Lines */}
          {trends?.trends?.length > 0 && (
            <View data-testid="engagement-trends-chart" testID="engagement-trends-chart" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 4 }}>{tx('admin.platformAnalyticsPanel.auto.text.011', 'Engagement Trends')}</Text>
              <Text style={{ color: C.muted, fontSize: 11, marginBottom: 14 }}>DAU / WAU / MAU over {trends.period_days} days (weekly)</Text>
              {/* Multi-line chart */}
              <View style={{ height: 160 }}>
                {(() => {
                  const maxVal = Math.max(...trends.trends.map((t: any) => Math.max(t.dau, t.wau, t.mau)), 1);
                  return (
                    <View style={{ flex: 1 }}>
                      {/* Y-axis labels */}
                      <View style={{ position: 'absolute', left: 0, top: 0, bottom: 20, justifyContent: 'space-between', width: 28 }}>
                        <Text style={{ color: C.muted, fontSize: 9 }}>{maxVal}</Text>
                        <Text style={{ color: C.muted, fontSize: 9 }}>{Math.round(maxVal / 2)}</Text>
                        <Text style={{ color: C.muted, fontSize: 9 }}>0</Text>
                      </View>
                      {/* Bars grouped */}
                      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 140, marginLeft: 32, gap: 4 }}>
                        {trends.trends.map((t: any, i: number) => (
                          <View key={i} style={{ flex: 1, alignItems: 'center', gap: 1 }}>
                            <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 120, gap: 1, width: '100%' }}>
                              <View style={{ flex: 1, justifyContent: 'flex-end', height: '100%' }}>
                                <View style={{ height: `${(t.mau / maxVal) * 100}%`, backgroundColor: C.green, borderRadius: 2, minHeight: t.mau > 0 ? 2 : 0 }} />
                              </View>
                              <View style={{ flex: 1, justifyContent: 'flex-end', height: '100%' }}>
                                <View style={{ height: `${(t.wau / maxVal) * 100}%`, backgroundColor: C.cyan, borderRadius: 2, minHeight: t.wau > 0 ? 2 : 0 }} />
                              </View>
                              <View style={{ flex: 1, justifyContent: 'flex-end', height: '100%' }}>
                                <View style={{ height: `${(t.dau / maxVal) * 100}%`, backgroundColor: C.blue, borderRadius: 2, minHeight: t.dau > 0 ? 2 : 0 }} />
                              </View>
                            </View>
                            <Text style={{ color: C.muted, fontSize: 8, marginTop: 4 }}>{t.date.slice(0, 6)}</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  );
                })()}
              </View>
              {/* Legend */}
              <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 16, marginTop: 8 }}>
                {[{ label: 'MAU', color: C.green }, { label: 'WAU', color: C.cyan }, { label: 'DAU', color: C.blue }].map(l => (
                  <View key={l.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: l.color }} />
                    <Text style={{ color: C.sec, fontSize: 10, fontWeight: '600' }}>{l.label}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Cohort Retention Table */}
          {cohort?.cohorts?.length > 0 && (
            <View data-testid="cohort-retention-table" testID="cohort-retention-table" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
              <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.platformAnalyticsPanel.auto.text.012', 'Cohort Retention')}</Text>
                <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{tx('admin.platformAnalyticsPanel.auto.text.013', 'Signup week → % active in subsequent weeks')}</Text>
              </View>
              {isCompact ? (
                <View style={{ padding: 12, gap: 8 }} data-testid="cohort-retention-compact-list" testID="cohort-retention-compact-list">
                  {cohort.cohorts.map((c: any, ci: number) => (
                    <View key={ci} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.bg, padding: 10, gap: 8 }} data-testid={`cohort-retention-card-${ci}`} testID={`cohort-retention-card-${ci}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{c.week_label}</Text>
                        <Text style={{ color: C.sec, fontSize: 11, fontWeight: '700' }}>{tx('admin.platformAnalyticsPanel.auto.text.015', 'SIZE')}: {c.cohort_size}</Text>
                      </View>
                      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                        {Array.from({ length: 8 }, (_, wi) => {
                          const ret = c.retention?.find((r: any) => r.week === wi);
                          const pct = ret?.pct ?? null;
                          const bgOpacity = pct !== null ? Math.min(pct / 100, 1) : 0;
                          return (
                            <View key={wi} style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: pct !== null ? `rgba(16,185,129,${bgOpacity * 0.3})` : C.card }}>
                              <Text style={{ color: pct !== null ? C.text : C.muted, fontSize: 10, fontWeight: '700' }}>W{wi}: {pct !== null ? `${pct}%` : '-'}</Text>
                            </View>
                          );
                        })}
                      </View>
                    </View>
                  ))}
                </View>
              ) : (
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  <View>
                    {/* Header row */}
                    <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.border, backgroundColor: C.bg }}>
                      <View style={{ width: 100, paddingHorizontal: 12, paddingVertical: 8 }}>
                        <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformAnalyticsPanel.auto.text.014', 'COHORT')}</Text>
                      </View>
                      <View style={{ width: 60, paddingHorizontal: 8, paddingVertical: 8 }}>
                        <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformAnalyticsPanel.auto.text.015', 'SIZE')}</Text>
                      </View>
                      {Array.from({ length: 8 }, (_, i) => (
                        <View key={i} style={{ width: 56, paddingHorizontal: 4, paddingVertical: 8, alignItems: 'center' }}>
                          <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>W{i}</Text>
                        </View>
                      ))}
                    </View>
                    {/* Data rows */}
                    {cohort.cohorts.map((c: any, ci: number) => (
                      <View key={ci} style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.border }}>
                        <View style={{ width: 100, paddingHorizontal: 12, paddingVertical: 8, justifyContent: 'center' }}>
                          <Text style={{ color: C.text, fontSize: 11, fontWeight: '600' }}>{c.week_label}</Text>
                        </View>
                        <View style={{ width: 60, paddingHorizontal: 8, paddingVertical: 8, justifyContent: 'center' }}>
                          <Text style={{ color: C.sec, fontSize: 11, fontWeight: '600' }}>{c.cohort_size}</Text>
                        </View>
                        {Array.from({ length: 8 }, (_, wi) => {
                          const ret = c.retention?.find((r: any) => r.week === wi);
                          const pct = ret?.pct ?? null;
                          const bgOpacity = pct !== null ? Math.min(pct / 100, 1) : 0;
                          return (
                            <View key={wi} style={{
                              width: 56, paddingHorizontal: 4, paddingVertical: 8, alignItems: 'center', justifyContent: 'center',
                              backgroundColor: pct !== null ? `rgba(16,185,129,${bgOpacity * 0.3})` : 'transparent',
                            }}>
                              <Text style={{ color: pct !== null ? C.text : C.muted, fontSize: 11, fontWeight: '600' }}>
                                {pct !== null ? `${pct}%` : '-'}
                              </Text>
                            </View>
                          );
                        })}
                      </View>
                    ))}
                  </View>
                </ScrollView>
              )}
            </View>
          )}
        </View>
      )}

      {/* Tab: Referral Funnel */}
      {activeTab === 'funnel' && (
        <View style={{ gap: 14 }}>
          {funnel?.funnel && <FunnelChart funnel={funnel.funnel} />}

          {/* Top Referrers */}
          {topReferrers?.referrers?.length > 0 && (
            <View data-testid="top-referrers" testID="top-referrers" style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.platformAnalyticsPanel.auto.text.016', 'Top Referrers')}</Text>
              {topReferrers.referrers.map((r: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: i < topReferrers.referrers.length - 1 ? 1 : 0, borderBottomColor: C.border }}>
                  <Text style={{ color: C.muted, fontSize: 12, fontWeight: '700', width: 24 }}>#{i + 1}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{r.name}</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>{r.email}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: C.green, fontSize: 13, fontWeight: '700' }}>{r.total_referrals} referrals</Text>
                    <Text style={{ color: C.muted, fontSize: 11 }}>{r.conversion_rate}% converted</Text>
                  </View>
                </View>
              ))}
            </View>
          )}

          {(!topReferrers?.referrers?.length && !funnel?.funnel?.length) && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="git-merge-outline" size={32} color={C.muted} />
              <Text style={{ color: C.muted, fontSize: 14, marginTop: 8 }}>{tx('admin.platformAnalyticsPanel.auto.text.017', 'No referral data available yet')}</Text>
            </View>
          )}
        </View>
      )}

      {/* Tab: User Engagement Scoring */}
      {activeTab === 'engagement' && scores && (
        <View style={{ gap: 14 }}>
          {/* Summary Cards */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <StatCard label="Avg Score" value={scores.avg_score} sub={`Out of 100`} icon="speedometer" color={C.blue} />
            <StatCard label="Scored Users" value={scores.total_scored} icon="people" color={C.cyan} />
            <StatCard label="Power Users" value={scores.segments['Power User']} icon="flash" color={C.green} />
            <StatCard label="At Risk" value={scores.segments['At Risk']} icon="warning" color={C.yellow} />
          </View>

          {/* Segments */}
          <SegmentPie segments={scores.segments} />

          {/* User Table */}
          <View data-testid="engagement-scores-table" testID="engagement-scores-table" style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
            <View style={{ paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.platformAnalyticsPanel.auto.text.018', 'User Engagement Scores')}</Text>
            </View>
            {/* Header */}
            <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 8, backgroundColor: C.bg, borderBottomWidth: 1, borderBottomColor: C.border }}>
              <Text style={{ flex: 2, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.platformAnalyticsPanel.auto.text.019', 'User')}</Text>
              <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.platformAnalyticsPanel.auto.text.020', 'Score')}</Text>
              <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.platformAnalyticsPanel.auto.text.021', 'Segment')}</Text>
              <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.platformAnalyticsPanel.auto.text.022', 'Logins')}</Text>
              <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.platformAnalyticsPanel.auto.text.023', 'Chats')}</Text>
            </View>
            {/* Rows */}
            {scores.users?.map((u: any, i: number) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <View style={{ flex: 2 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>{u.name}</Text>
                  <Text style={{ color: C.muted, fontSize: 10 }} numberOfLines={1}>{u.email}</Text>
                </View>
                <View style={{ flex: 1, alignItems: 'center' }}>
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor((SEGMENT_COLORS[u.segment] || C.muted), '20'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 }}>
                    <Text style={{ color: SEGMENT_COLORS[u.segment] || C.muted, fontSize: 12, fontWeight: '700' }}>{u.score}</Text>
                  </View>
                </View>
                <View style={{ flex: 1, alignItems: 'center' }}>
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor((SEGMENT_COLORS[u.segment] || C.muted), '18'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                    <Text style={{ color: SEGMENT_COLORS[u.segment] || C.muted, fontSize: 10, fontWeight: '600' }}>{u.segment}</Text>
                  </View>
                </View>
                <Text style={{ flex: 1, color: C.sec, fontSize: 12, fontWeight: '600', textAlign: 'center' }}>{u.logins_30d}</Text>
                <Text style={{ flex: 1, color: C.sec, fontSize: 12, fontWeight: '600', textAlign: 'center' }}>{u.conversations_30d}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </ScrollView>
  );
}
