import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import DataFreshnessIndicator from '../DataFreshnessIndicator';
import AutoFixBanner from './AutoFixBanner';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
interface Props { colors: any; }

function makeT(AC: any) { return {
  bg: 'rgba(10,14,26,0.2)', surface: 'rgba(15,22,41,0.2)', card: AC.surface, border: 'rgba(26,37,64,0.35)',
  text: AC.text, textSec: AC.textMuted, textMuted: AC.textDim,
  primary: 'var(--app-primary)', primarySoft: 'var(--app-primary-soft)',
}; }

const DOW_LABELS = ['', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const DATE_RANGES = [
  { label: '7d', value: 7 }, { label: '14d', value: 14 },
  { label: '30d', value: 30 }, { label: '60d', value: 60 }, { label: '90d', value: 90 },
];

export default function UBADashboardPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<'overview' | 'heatmap' | 'features' | 'funnel' | 'cohorts' | 'clicks'>('overview');
  const [days, setDays] = useState(30);

  const { data: overview, loading: ovLoading, lastUpdated, refetch: refetchOverview } = useLiveQuery('/admin/uba/overview', { entity: 'uba', pollInterval: 60000 });
  const { data: hmData } = useLiveQuery(`/admin/uba/heatmap?days=${days}`, { entity: 'uba', pollInterval: 60000, deps: [days] });
  const { data: ftData } = useLiveQuery(`/admin/uba/features?days=${days}`, { entity: 'uba', pollInterval: 60000, deps: [days] });
  const { data: fnData } = useLiveQuery('/admin/uba/funnel', { entity: 'uba', pollInterval: 60000 });
  const { data: chData } = useLiveQuery('/admin/uba/cohorts?weeks=8', { entity: 'uba', pollInterval: 60000 });
  const { data: clData } = useLiveQuery(`/admin/uba/click-heatmap?days=${days}`, { entity: 'uba', pollInterval: 60000, deps: [days] });

  const loading = ovLoading;
  const heatmap = hmData?.cells || [];
  const features = ftData?.features || [];
  const funnel = fnData?.funnel || [];
  const cohorts = chData?.cohorts || [];
  const clickData = clData || { cells: [], pages: [], total_clicks: 0 };

  const exportSection = (section: string) => {
    if (Platform.OS === 'web') {
      const token = localStorage.getItem('session_token') || '';
      const url = `${(typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.EXPO_PUBLIC_BACKEND_URL || ''))}/api/admin/uba/export/${section}?days=${days}`;
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `uba_${section}_${days}d.csv`);
      // Set auth header via fetch + blob
      fetch(url, { headers: { Authorization: `Bearer ${token}` } })
        .then(r => r.blob())
        .then(blob => {
          const blobUrl = URL.createObjectURL(blob);
          link.href = blobUrl;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(blobUrl);
        });
    }
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  const tabs = [
    { id: 'overview', label: 'Overview', icon: 'people' },
    { id: 'heatmap', label: 'Activity Heatmap', icon: 'grid' },
    { id: 'features', label: 'Feature Usage', icon: 'rocket' },
    { id: 'funnel', label: 'User Funnel', icon: 'funnel' },
    { id: 'cohorts', label: 'Cohort Retention', icon: 'calendar' },
    { id: 'clicks', label: 'Click Heatmap', icon: 'finger-print' },
  ] as const;

  const maxHeat = Math.max(...heatmap.map(c => c.count), 1);
  const maxFeature = features.length > 0 ? features[0].count : 1;
  const funnelMax = funnel.length > 0 ? funnel[0].count : 1;

  return (
    <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
      <AutoFixBanner domain="uba" />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="uba-title" testID="uba-title">{tx('admin.uBADashboardPanel.auto.text.001', 'User Behavior Analytics')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 2 }}>{tx('admin.uBADashboardPanel.auto.text.002', 'Engagement insights & retention analysis')}</Text>
        </View>
        <DataFreshnessIndicator lastUpdated={lastUpdated} onRefresh={refetchOverview} isRefreshing={loading} accentColor={T.primary} textColor={T.textMuted} />
      </View>

      {/* Date Range Selector */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14 }} data-testid="uba-date-range" testID="uba-date-range">
        <Ionicons name="calendar-outline" size={14} color={T.textMuted} />
        <Text style={{ fontSize: 11, color: T.textMuted, fontWeight: '600' }}>{tx('admin.uBADashboardPanel.auto.text.003', 'Range:')}</Text>
        {DATE_RANGES.map(r => (
          <TouchableOpacity key={r.value} onPress={() => setDays(r.value)}
            style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: days === r.value ? T.primary : T.card, borderWidth: 1, borderColor: days === r.value ? T.primary : T.border }}
            data-testid={`uba-range-${r.value}`} testID={`uba-range-${r.value}`}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: days === r.value ? 'var(--app-primary-text)' : T.textSec }}>{r.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Tab Bar */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20, flexWrap: 'wrap' }} data-testid="uba-tabs" testID="uba-tabs">
        {tabs.map(t => (
          <TouchableOpacity key={t.id} onPress={() => setTab(t.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: tab === t.id ? T.primary : T.card, borderWidth: 1, borderColor: tab === t.id ? T.primary : T.border }}
            data-testid={`uba-tab-${t.id}`} testID={`uba-tab-${t.id}`}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? 'var(--app-primary-text)' : T.textMuted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: tab === t.id ? 'var(--app-primary-text)' : T.textSec }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'overview' && overview && (
        <View>
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }} data-testid="uba-kpis" testID="uba-kpis">
            {[
              { label: 'Total Users', value: overview.total_users, icon: 'people', color: colors.primary },
              { label: 'DAU', value: overview.dau, icon: 'person', color: colors.successText },
              { label: 'WAU', value: overview.wau, icon: 'people-circle', color: colors.accent },
              { label: 'MAU', value: overview.mau, icon: 'globe', color: colors.warningText },
              { label: 'DAU/WAU %', value: `${overview.dau_wau_ratio}%`, icon: 'trending-up', color: colors.accent },
            ].map(k => (
              <View key={k.label} style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
                <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(k.color, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
                  <Ionicons name={k.icon as any} size={16} color={k.color} />
                </View>
                <Text style={{ fontSize: 22, fontWeight: '800', color: T.text }}>{typeof k.value === 'number' ? k.value.toLocaleString() : k.value}</Text>
                <Text style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', marginTop: 2 }}>{k.label}</Text>
              </View>
            ))}
          </View>

          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
            <View style={{ flex: 1, minWidth: 250, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 8 }}>{tx('admin.uBADashboardPanel.auto.text.004', 'AI Sessions (7d)')}</Text>
              <Text style={{ fontSize: 28, fontWeight: '800', color: T.primary }}>{overview.ai_sessions_7d}</Text>
              <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>Avg {overview.avg_sessions_per_user_7d}/user | Max {overview.max_sessions_user_7d}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 250, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 8 }}>{tx('admin.uBADashboardPanel.auto.text.005', 'Total AI Sessions')}</Text>
              <Text style={{ fontSize: 28, fontWeight: '800', color: colors.successText }}>{overview.total_ai_sessions}</Text>
              <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>{tx('admin.uBADashboardPanel.auto.text.006', 'Across all time')}</Text>
            </View>
          </View>
          <TouchableOpacity onPress={() => exportSection('overview')} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-end', marginTop: 12, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid="uba-export-overview" testID="uba-export-overview">
            <Ionicons name="download-outline" size={14} color={T.primary} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: T.primary }}>{tx('admin.uBADashboardPanel.auto.text.007', 'Export CSV')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {tab === 'heatmap' && (
        <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border }} data-testid="uba-heatmap" testID="uba-heatmap">
          <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 14 }}>Activity Heatmap (Login by day & hour, {days}d)</Text>
          <View style={{ flexDirection: 'row' }}>
            <View style={{ width: 40, marginRight: 4 }}>
              <View style={{ height: 20 }} />
              {[1, 2, 3, 4, 5, 6, 7].map(d => (
                <View key={d} style={{ height: 20, justifyContent: 'center' }}>
                  <Text style={{ fontSize: 9, color: T.textMuted, fontWeight: '600' }}>{DOW_LABELS[d]}</Text>
                </View>
              ))}
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View>
                <View style={{ flexDirection: 'row' }}>
                  {Array.from({ length: 24 }, (_, h) => (
                    <View key={h} style={{ width: 20, height: 20, alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ fontSize: 7, color: T.textMuted }}>{h}</Text>
                    </View>
                  ))}
                </View>
                {[1, 2, 3, 4, 5, 6, 7].map(dow => (
                  <View key={dow} style={{ flexDirection: 'row' }}>
                    {Array.from({ length: 24 }, (_, h) => {
                      const cell = heatmap.find(c => c.dow === dow && c.hour === h);
                      const count = cell?.count || 0;
                      const intensity = count / maxHeat;
                      const bg = count === 0 ? T.border : `rgba(139, 92, 246, ${0.15 + intensity * 0.85})`;
                      return <View key={h} style={{ width: 20, height: 20, backgroundColor: bg, borderRadius: 3, margin: 0.5 }} />;
                    })}
                  </View>
                ))}
              </View>
            </ScrollView>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6, marginTop: 10 }}>
            <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.uBADashboardPanel.auto.text.008', 'Less')}</Text>
            {[0.1, 0.3, 0.5, 0.7, 1].map((v, i) => (
              <View key={i} style={{ width: 14, height: 14, borderRadius: 3, backgroundColor: `rgba(139, 92, 246, ${0.15 + v * 0.85})` }} />
            ))}
            <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.uBADashboardPanel.auto.text.009', 'More')}</Text>
          </View>
        </View>
      )}

      {tab === 'features' && (
        <View>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border }} data-testid="uba-features" testID="uba-features">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>Feature Usage Ranking ({days}d)</Text>
              <TouchableOpacity onPress={() => exportSection('features')} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(T.primary, '20') }} data-testid="uba-export-features" testID="uba-export-features">
                <Ionicons name="download-outline" size={12} color={T.primary} />
                <Text style={{ fontSize: 10, fontWeight: '700', color: T.primary }}>{tx('admin.uBADashboardPanel.auto.text.010', 'CSV')}</Text>
              </TouchableOpacity>
            </View>
            {features.length === 0 && <Text style={{ fontSize: 12, color: T.textMuted }}>{tx('admin.uBADashboardPanel.auto.text.011', 'No feature usage data available')}</Text>}
            {features.map((f, i) => (
              <View key={f.feature} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <Text style={{ width: 20, fontSize: 12, fontWeight: '800', color: i < 3 ? 'var(--app-warning)' : T.textMuted, textAlign: 'center' }}>#{i + 1}</Text>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: T.text }}>{f.feature}</Text>
                    <Text style={{ fontSize: 11, color: T.textSec }}>{f.count} uses | {f.unique_users} users</Text>
                  </View>
                  <View style={{ height: 6, borderRadius: 3, backgroundColor: T.border }}>
                    <View style={{ width: `${(f.count / maxFeature) * 100}%`, height: 6, borderRadius: 3, backgroundColor: i < 3 ? 'var(--app-primary)' : 'var(--app-primary)' }} />
                  </View>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {tab === 'funnel' && (
        <View>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border }} data-testid="uba-funnel" testID="uba-funnel">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('admin.uBADashboardPanel.auto.text.012', 'User Journey Funnel')}</Text>
              <TouchableOpacity onPress={() => exportSection('funnel')} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(T.primary, '20') }} data-testid="uba-export-funnel" testID="uba-export-funnel">
                <Ionicons name="download-outline" size={12} color={T.primary} />
                <Text style={{ fontSize: 10, fontWeight: '700', color: T.primary }}>{tx('admin.uBADashboardPanel.auto.text.013', 'CSV')}</Text>
              </TouchableOpacity>
            </View>
            {funnel.map((step, i) => {
              const pct = funnelMax > 0 ? (step.count / funnelMax) * 100 : 0;
              const dropoff = i > 0 && funnel[i - 1].count > 0 ? Math.round((1 - step.count / funnel[i - 1].count) * 100) : 0;
              const barColors = ['var(--app-primary)', 'var(--app-primary)', 'var(--app-success)', 'var(--app-warning)', 'var(--app-primary)'];
              return (
                <View key={step.step} style={{ marginBottom: 14 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: T.text }}>{step.step}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Text style={{ fontSize: 13, fontWeight: '800', color: barColors[i % barColors.length] }}>{step.count}</Text>
                      {i > 0 && dropoff > 0 && <Text style={{ fontSize: 10, color: colors.error, fontWeight: '600' }}>-{dropoff}%</Text>}
                    </View>
                  </View>
                  <View style={{ height: 10, borderRadius: 5, backgroundColor: T.border }}>
                    <View style={{ width: `${pct}%`, height: 10, borderRadius: 5, backgroundColor: barColors[i % barColors.length] }} />
                  </View>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {tab === 'cohorts' && (
        <View>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border }} data-testid="uba-cohorts" testID="uba-cohorts">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('admin.uBADashboardPanel.auto.text.014', 'Cohort Retention (by signup week)')}</Text>
              <TouchableOpacity onPress={() => exportSection('cohorts')} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(T.primary, '20') }} data-testid="uba-export-cohorts" testID="uba-export-cohorts">
                <Ionicons name="download-outline" size={12} color={T.primary} />
                <Text style={{ fontSize: 10, fontWeight: '700', color: T.primary }}>{tx('admin.uBADashboardPanel.auto.text.015', 'CSV')}</Text>
              </TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: T.border, paddingBottom: 8, marginBottom: 4 }}>
              <Text style={{ width: 70, fontSize: 10, fontWeight: '700', color: T.textMuted }}>{tx('admin.uBADashboardPanel.auto.text.016', 'Week')}</Text>
              <Text style={{ width: 60, fontSize: 10, fontWeight: '700', color: T.textMuted, textAlign: 'center' }}>{tx('admin.uBADashboardPanel.auto.text.017', 'Signups')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: T.textMuted, textAlign: 'center' }}>{tx('admin.uBADashboardPanel.auto.text.018', 'Week 1')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: T.textMuted, textAlign: 'center' }}>{tx('admin.uBADashboardPanel.auto.text.019', 'Week 2')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: T.textMuted, textAlign: 'center' }}>{tx('admin.uBADashboardPanel.auto.text.020', 'Week 4')}</Text>
            </View>
            {cohorts.map((c, i) => {
              const r1p = c.signups > 0 ? Math.round((c.retained_1w / c.signups) * 100) : 0;
              const r2p = c.signups > 0 ? Math.round((c.retained_2w / c.signups) * 100) : 0;
              const r4p = c.signups > 0 ? Math.round((c.retained_4w / c.signups) * 100) : 0;
              const cc = (p: number) => p >= 50 ? 'var(--app-success)' : p >= 25 ? 'var(--app-warning)' : p > 0 ? 'var(--app-error)' : T.border;
              return (
                <View key={i} style={{ flexDirection: 'row', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: 'rgba(30,45,74,0.25)' }}>
                  <Text style={{ width: 70, fontSize: 11, color: T.textSec, fontWeight: '600' }}>{c.week}</Text>
                  <Text style={{ width: 60, fontSize: 11, color: T.text, fontWeight: '700', textAlign: 'center' }}>{c.signups}</Text>
                  {[r1p, r2p, r4p].map((p, j) => (
                    <View key={j} style={{ flex: 1, alignItems: 'center' }}>
                      <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(cc(p), '20') }}>
                        <Text style={{ fontSize: 11, fontWeight: '700', color: cc(p) }}>{p}%</Text>
                      </View>
                    </View>
                  ))}
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* Click Heatmap Tab */}
      {tab === 'clicks' && (
        <View data-testid="uba-click-heatmap" testID="uba-click-heatmap">
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border, marginBottom: 16 }}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 4 }}>Click Heatmap ({days}d)</Text>
            <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 14 }}>{clickData.total_clicks} total clicks tracked</Text>

            {clickData.pages?.length > 0 ? (
              <View>
                <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.uBADashboardPanel.auto.text.021', 'Pages by Click Volume')}</Text>
                {clickData.pages.map((p: any, i: number) => {
                  const maxClicks = clickData.pages[0]?.clicks || 1;
                  return (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      <Text style={{ width: 20, fontSize: 11, fontWeight: '800', color: i < 3 ? 'var(--app-warning)' : T.textMuted, textAlign: 'center' }}>#{i + 1}</Text>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
                          <Text style={{ fontSize: 12, fontWeight: '600', color: T.text }} numberOfLines={1}>{p.page || 'Unknown'}</Text>
                          <Text style={{ fontSize: 11, color: T.textSec }}>{p.clicks} clicks | {p.unique_users} users</Text>
                        </View>
                        <View style={{ height: 6, borderRadius: 3, backgroundColor: T.border }}>
                          <View style={{ width: `${(p.clicks / maxClicks) * 100}%`, height: 6, borderRadius: 3, backgroundColor: colors.accent }} />
                        </View>
                      </View>
                    </View>
                  );
                })}
              </View>
            ) : (
              <View style={{ padding: 30, alignItems: 'center' }}>
                <Ionicons name="finger-print" size={32} color={T.textMuted} />
                <Text style={{ fontSize: 13, color: T.textMuted, marginTop: 8 }}>{tx('admin.uBADashboardPanel.auto.text.022', 'No click data collected yet')}</Text>
                <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 4, textAlign: 'center' }}>{tx('admin.uBADashboardPanel.auto.text.023', 'Click tracking is active. Data will appear as users interact with the platform.')}</Text>
              </View>
            )}
          </View>

          {/* Heatmap Grid Visualization */}
          {clickData.cells?.length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.uBADashboardPanel.auto.text.024', 'Click Density Grid')}</Text>
              <View style={{ height: 200, position: 'relative', borderRadius: 8, backgroundColor: T.bg, overflow: 'hidden' }}>
                {clickData.cells.slice(0, 100).map((c: any, i: number) => {
                  const maxC = clickData.cells[0]?.count || 1;
                  const opacity = 0.2 + (c.count / maxC) * 0.8;
                  return (
                    <View key={i} style={{
                      position: 'absolute', left: `${Math.min(c.x / 19.2, 95)}%`, top: `${Math.min(c.y / 8, 90)}%`,
                      width: 12, height: 12, borderRadius: 6, backgroundColor: `rgba(139, 92, 246, ${opacity})`,
                    }} />
                  );
                })}
              </View>
            </View>
          )}
        </View>
      )}
    </ScrollView>
  );
}
