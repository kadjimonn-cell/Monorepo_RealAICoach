import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const CAT_COLORS: Record<string, string> = {
  productivity: 'var(--app-primary)', planning: 'var(--app-primary)', health: 'var(--app-success)',
  finance: 'var(--app-warning)', learning: 'var(--app-primary)', fitness: 'var(--app-error)',
  wellness: 'var(--app-primary)', 'real-estate': 'var(--app-primary)', career: 'var(--app-warning)',
  travel: 'var(--app-primary)', personal: 'var(--app-text)', unknown: 'var(--app-text-muted)',
};

const TYPE_COLORS: Record<string, string> = {
  article: 'var(--app-primary)', guide: 'var(--app-success)', template: 'var(--app-primary)',
  workout: 'var(--app-warning)', checklist: 'var(--app-error)', generated: 'var(--app-primary)', unknown: 'var(--app-text-muted)',
};

interface Props { colors: any; }

export default function CatAnalyticsPanel({ colors: C }: Props) {
  const colors = useAdminTheme();
  const { width } = useWindowDimensions();
  const isMobile = width < 900;
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { data, loading, refetch } = useLiveQuery('/admin/categorization-analytics', { entity: 'categorization', pollInterval: 60000 });

  const toTitle = (s: string) => s.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  if (loading) {
    return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={C.primary} /></View>;
  }

  if (!data) {
    return <View style={{ padding: 20 }}><Text style={{ color: C.textMuted }}>{tx('admin.catAnalyticsPanel.states.loadFailed', 'Failed to load analytics.')}</Text></View>;
  }

  const ov = data.overview;
  const maxTrend = Math.max(...data.weekly_trends.map((w: any) => w.count), 1);
  const maxCat = Math.max(...(data.category_distribution?.map((c: any) => c.count) || [1]));
  const maxType = Math.max(...(data.type_distribution?.map((t: any) => t.count) || [1]));

  return (
    <View data-testid="cat-analytics-panel" testID="cat-analytics-panel">
      {/* Header */}
      <View style={{ marginBottom: 20 }}>
        <Text style={{ fontSize: 20, fontWeight: '800', color: C.text }} data-testid="cat-analytics-title" testID="cat-analytics-title">{tx('admin.catAnalyticsPanel.header.title', 'Categorization Analytics')}</Text>
        <Text style={{ fontSize: 13, color: C.textMuted, marginTop: 4 }}>{tx('admin.catAnalyticsPanel.header.subtitle', 'AI categorization performance and content insights')}</Text>
      </View>

      {/* Overview Cards */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 24, flexWrap: 'wrap' }} data-testid="overview-cards" testID="overview-cards">
        {[
          { label: 'Coverage', value: `${ov.coverage_pct}%`, sub: `${ov.categorized}/${ov.total_content}`, icon: 'pie-chart', color: colors.successText },
          { label: 'Today', value: ov.today_count, sub: 'items processed', icon: 'today', color: colors.primary },
          { label: 'Success Rate', value: `${ov.success_rate}%`, sub: 'batch accuracy', icon: 'checkmark-done', color: colors.accent },
          { label: 'Uncategorized', value: ov.uncategorized, sub: 'remaining', icon: 'alert-circle', color: ov.uncategorized > 0 ? 'var(--app-error)' : 'var(--app-success)' },
        ].map(card => (
          <View key={card.label} style={{
            flex: 1, minWidth: 140, backgroundColor: C.card, borderRadius: 14,
            padding: 16, borderWidth: 1, borderColor: C.border, gap: 6,
          }} data-testid={`analytics-card-${card.label.toLowerCase().replace(' ', '-')}`} testID={`analytics-card-${card.label.toLowerCase().replace(' ', '-')}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(card.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={card.icon as any} size={16} color={card.color} />
              </View>
              <Text style={{ fontSize: 11, fontWeight: '600', color: C.textMuted }}>{card.label}</Text>
            </View>
            <Text style={{ fontSize: 24, fontWeight: '800', color: card.color }}>{card.value}</Text>
            <Text style={{ fontSize: 10, color: C.textMuted }}>{card.sub}</Text>
          </View>
        ))}
      </View>

      {/* Weekly Trends */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 20 }}
        data-testid="weekly-trends-section" testID="weekly-trends-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Ionicons name="trending-up" size={16} color={'var(--app-primary)'} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.catAnalyticsPanel.weeklyTrends.title', 'Weekly Trends')}</Text>
          <Text style={{ fontSize: 10, color: C.textMuted, marginLeft: 'auto' }}>{tx('admin.catAnalyticsPanel.weeklyTrends.period', 'Last 8 weeks')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: 100 }}>
          {data.weekly_trends.map((w: any, i: number) => {
            const pct = maxTrend > 0 ? (w.count / maxTrend) * 100 : 0;
            const barH = Math.max(pct, 4);
            return (
              <View key={i} style={{ flex: 1, alignItems: 'center', gap: 4 }}>
                <Text style={{ fontSize: 9, fontWeight: '700', color: w.count > 0 ? 'var(--app-primary)' : C.textMuted }}>{w.count}</Text>
                <View style={{
                  width: '100%', borderRadius: 6, backgroundColor: w.count > 0 ? 'var(--app-primary)' : C.bgSoft,
                  height: `${barH}%`, minHeight: 4,
                }} />
                <Text style={{ fontSize: 8, color: C.textMuted }} numberOfLines={1}>{w.week}</Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Category & Type Distribution side by side */}
      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        {/* Category Distribution */}
        <View style={{ flex: 1, minWidth: isMobile ? '100%' as any : 280, backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}
          data-testid="category-distribution" testID="category-distribution">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Ionicons name="folder" size={16} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.catAnalyticsPanel.categories.title', 'Categories')}</Text>
          </View>
          {(data.category_distribution?.length > 0) ? (
            <View style={{ gap: 8 }}>
              {data.category_distribution.map((c: any) => {
                const pct = maxCat > 0 ? (c.count / maxCat) * 100 : 0;
                const color = CAT_COLORS[c.name] || 'var(--app-text-muted)';
                return (
                  <View key={c.name} style={{ gap: 3 }} data-testid={`cat-bar-${c.name}`} testID={`cat-bar-${c.name}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <Text style={{ fontSize: 11, fontWeight: '600', color: C.text }}>{toTitle(c.name)}</Text>
                      <Text style={{ fontSize: 11, fontWeight: '700', color }}>{c.count}</Text>
                    </View>
                    <View style={{ height: 6, borderRadius: 3, backgroundColor: C.bgSoft, overflow: 'hidden' }}>
                      <View style={{ height: '100%', borderRadius: 3, backgroundColor: color, width: `${pct}%` }} />
                    </View>
                  </View>
                );
              })}
            </View>
          ) : (
            <Text style={{ fontSize: 11, color: C.textMuted }}>{tx('admin.catAnalyticsPanel.states.noData', 'No data yet')}</Text>
          )}
        </View>

        {/* Type Distribution */}
        <View style={{ flex: 1, minWidth: isMobile ? '100%' as any : 280, backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}
          data-testid="type-distribution" testID="type-distribution">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Ionicons name="document-text" size={16} color={'var(--app-warning)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.catAnalyticsPanel.contentTypes.title', 'Content Types')}</Text>
          </View>
          {(data.type_distribution?.length > 0) ? (
            <View style={{ gap: 8 }}>
              {data.type_distribution.map((t: any) => {
                const pct = maxType > 0 ? (t.count / maxType) * 100 : 0;
                const color = TYPE_COLORS[t.name] || 'var(--app-text-muted)';
                return (
                  <View key={t.name} style={{ gap: 3 }} data-testid={`type-bar-${t.name}`} testID={`type-bar-${t.name}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <Text style={{ fontSize: 11, fontWeight: '600', color: C.text }}>{toTitle(t.name)}</Text>
                      <Text style={{ fontSize: 11, fontWeight: '700', color }}>{t.count}</Text>
                    </View>
                    <View style={{ height: 6, borderRadius: 3, backgroundColor: C.bgSoft, overflow: 'hidden' }}>
                      <View style={{ height: '100%', borderRadius: 3, backgroundColor: color, width: `${pct}%` }} />
                    </View>
                  </View>
                );
              })}
            </View>
          ) : (
            <Text style={{ fontSize: 11, color: C.textMuted }}>{tx('admin.catAnalyticsPanel.states.noData', 'No data yet')}</Text>
          )}
        </View>
      </View>

      {/* Recent Jobs */}
      {data.recent_jobs?.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 20 }}
          data-testid="recent-jobs-section" testID="recent-jobs-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Ionicons name="time" size={16} color={'var(--app-warning)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.catAnalyticsPanel.recentJobs.title', 'Recent Batch Jobs')}</Text>
          </View>
          <View style={{ gap: 8 }}>
            {data.recent_jobs.map((j: any) => (
              <View key={j.job_id} style={{
                flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border,
              }} data-testid={`job-row-${j.job_id}`} testID={`job-row-${j.job_id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons
                    name={j.status === 'completed' ? 'checkmark-circle' : 'sync'}
                    size={14}
                    color={j.status === 'completed' ? 'var(--app-success)' : 'var(--app-warning)'}
                  />
                  <Text style={{ fontSize: 11, fontWeight: '600', color: C.text }}>{j.job_id}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                  <Text style={{ fontSize: 10, color: colors.successText, fontWeight: '700' }}>{j.succeeded} ok</Text>
                  {j.failed > 0 && <Text style={{ fontSize: 10, color: colors.error, fontWeight: '700' }}>{j.failed} fail</Text>}
                  <Text style={{ fontSize: 9, color: C.textMuted }}>
                    {j.started_at ? new Date(j.started_at).toLocaleDateString() : ''}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Schedule Status */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}
        data-testid="schedule-status" testID="schedule-status">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Ionicons name="moon" size={16} color={'var(--app-primary)'} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.catAnalyticsPanel.schedule.title', 'Nightly Schedule Status')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{
            paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8,
            backgroundColor: data.schedule.enabled ? 'var(--app-success-soft)' : 'var(--app-error-soft)',
          }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: data.schedule.enabled ? 'var(--app-success)' : 'var(--app-error)' }}>
              {data.schedule.enabled ? 'ACTIVE' : 'DISABLED'}
            </Text>
          </View>
          <Text style={{ fontSize: 11, color: C.textMuted }}>Runs at {data.schedule.hour}:00 UTC</Text>
          {data.schedule.last_run_at && (
            <Text style={{ fontSize: 10, color: C.textMuted, marginLeft: 'auto' }}>
              Last: {new Date(data.schedule.last_run_at).toLocaleDateString()}
            </Text>
          )}
        </View>
      </View>

      {/* Refresh */}
      <TouchableOpacity onPress={() => { refetch(); }}
        style={{ marginTop: 16, alignItems: 'center', paddingVertical: 10 }}
        data-testid="refresh-analytics-btn" testID="refresh-analytics-btn">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name="refresh" size={14} color={C.textMuted} />
          <Text style={{ fontSize: 12, fontWeight: '600', color: C.textMuted }}>{tx('admin.catAnalyticsPanel.actions.refresh', 'Refresh Analytics')}</Text>
        </View>
      </TouchableOpacity>
    </View>
  );
}
