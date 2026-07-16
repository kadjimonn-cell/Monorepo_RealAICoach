import React, { useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';

const tx = (_key: string, fallback: string) => fallback;

function makeT(AC: any) { return {
  bg: AC.bg,
  bgSoft: AC.bgSoft,
  card: AC.card,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  textDim: AC.textDim || AC.textMuted,
  primary: AC.primary,
  success: AC.success,
  successText: AC.successText || AC.success,
  successSoft: AC.successSoft || `${AC.success}20`,
  warning: AC.warning,
  warningText: AC.warningText || AC.warning,
  warningSoft: AC.warningSoft || `${AC.warning}20`,
  error: AC.error,
  errorText: AC.errorText || AC.error,
  errorSoft: AC.errorSoft || `${AC.error}20`,
  purple: AC.purple,
  purpleText: AC.purpleText || AC.purple,
  cyan: AC.cyan || AC.info,
  teal: AC.teal || AC.cyan || AC.info,
  ai: AC.cyan || AC.info,
  orange: AC.orange,
  orangeText: AC.orangeText || AC.orange,
  pink: AC.pink || AC.purple,
}; }

interface Props { colors: any; }

function MiniBar({ data, color, h = 32 }: { data: number[]; color: string; h?: number }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data, 1);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: h }}>
      {data.map((v, i) => (
        <View key={i} style={{ flex: 1, height: Math.max(2, (v / max) * h), backgroundColor: color, borderRadius: 2, opacity: 0.4 + (i / data.length) * 0.6 }} />
      ))}
    </View>
  );
}

export default function AIFeatureAnalyticsPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { data, loading, refetch: refresh } = useLiveQuery('/admin/ai-feature-analytics', { entity: 'ai-analytics', pollInterval: 60000 });
  const [section, setSection] = useState('overview');
  const refreshing = false;

  if (loading) return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;
  if (!data) return <Text style={{ color: T.error, padding: 20 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.001', 'Failed to load analytics')}</Text>;

  const { overview, feature_stats, power_users, feature_correlations, ai_insights } = data;

  const sections = [
    { id: 'overview', label: 'Overview', icon: 'grid' },
    { id: 'features', label: 'Features', icon: 'apps' },
    { id: 'users', label: 'Power Users', icon: 'people' },
    { id: 'insights', label: 'AI Insights', icon: 'sparkles' },
  ];

  return (
    <View data-testid="ai-feature-analytics-panel" testID="ai-feature-analytics-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="ai-feature-analytics-title" testID="ai-feature-analytics-title">{tx('admin.aIFeatureAnalyticsPanel.auto.text.002', 'AI Feature Intelligence')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 4 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.003', 'Which AI tools drive the most engagement and value')}</Text>
        </View>
        <TouchableOpacity onPress={refresh} disabled={refreshing} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.bgSoft }} data-testid="refresh-analytics-btn" testID="refresh-analytics-btn">
          <Ionicons name="refresh" size={14} color={refreshing ? T.textMuted : T.primary} />
          <Text style={{ fontSize: 11, fontWeight: '600', color: refreshing ? T.textMuted : T.primary }}>{refreshing ? 'Loading...' : 'Refresh'}</Text>
        </TouchableOpacity>
      </View>

      {/* Section Tabs */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20, flexWrap: 'wrap' }} data-testid="analytics-section-tabs" testID="analytics-section-tabs">
        {sections.map(s => (
          <TouchableOpacity key={s.id} style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8,
            borderRadius: 10, backgroundColor: section === s.id ? T.primary : T.bgSoft,
          }} onPress={() => setSection(s.id)} data-testid={`analytics-tab-${s.id}`} testID={`analytics-tab-${s.id}`}>
            <Ionicons name={s.icon as any} size={14} color={section === s.id ? 'var(--app-primary-text)' : T.textSec} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: section === s.id ? 'var(--app-primary-text)' : T.textSec }}>{s.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Overview */}
      {section === 'overview' && (
        <View style={{ gap: 16 }}>
          {/* KPI Grid */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="overview-kpis" testID="overview-kpis">
            <KPI icon="flash" color={T.primary} label="AI Requests (7d)" value={overview.total_usage_7d} />
            <KPI icon="calendar" color={T.cyan} label="AI Requests (30d)" value={overview.total_usage_30d} />
            <KPI icon="people" color={T.successText} label="Active AI Users (7d)" value={overview.active_ai_users_7d} />
            <KPI icon="trending-up" color={T.teal} label="Adoption Rate" value={`${overview.adoption_rate}%`} />
            <KPI icon="layers" color={T.purpleText} label="Items Created" value={overview.total_items_created} />
            <KPI icon="git-merge" color={T.orangeText} label="Multi-Feature Users" value={overview.multi_feature_users} />
          </View>

          {/* Feature Leaderboard */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="feature-leaderboard" testID="feature-leaderboard">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.004', 'Feature Engagement Leaderboard')}</Text>
            {(feature_stats || []).map((f: any, i: number) => (
              <View key={f.feature_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: i < feature_stats.length - 1 ? 1 : 0, borderBottomColor: T.border }} data-testid={`leaderboard-${f.feature_id}`} testID={`leaderboard-${f.feature_id}`}>
                <View style={{ width: 26, height: 26, borderRadius: 8, backgroundColor: i === 0 ? '#0F766E20' : i === 1 ? '#0F766E20' : i === 2 ? '#0F766E20' : T.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ fontSize: 11, fontWeight: '800', color: i === 0 ? 'var(--app-primary)' : i === 1 ? 'var(--app-primary)' : i === 2 ? 'var(--app-primary)' : T.textMuted }}>#{i + 1}</Text>
                </View>
                <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(f.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={f.icon} size={16} color={f.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{f.name}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{f.unique_users_7d} users | {f.usage_7d} uses</Text>
                </View>
                {/* Engagement bar */}
                <View style={{ width: 60, height: 8, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
                  <View style={{ width: `${Math.min(f.engagement_score, 100)}%` as any, height: '100%', backgroundColor: f.color, borderRadius: 4 }} />
                </View>
                <Text style={{ color: f.color, fontSize: 12, fontWeight: '700', width: 30, textAlign: 'right' }}>{f.engagement_score}</Text>
              </View>
            ))}
          </View>

          {/* Feature Correlations */}
          {(feature_correlations || []).length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '30') }} data-testid="feature-correlations" testID="feature-correlations">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Ionicons name="git-merge" size={16} color={T.purpleText} />
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.005', 'Feature Combos')}</Text>
              </View>
              <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 10 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.006', 'Features frequently used together by the same users')}</Text>
              {feature_correlations.map((c: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: T.border }}>
                  <Text style={{ flex: 1, color: T.text, fontSize: 12 }}>{c.pair}</Text>
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.purple, '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                    <Text style={{ color: T.purpleText, fontSize: 10, fontWeight: '700' }}>{c.users} users</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Features Detail */}
      {section === 'features' && (
        <View style={{ gap: 12 }}>
          {(feature_stats || []).map((f: any) => (
            <View key={f.feature_id} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: f.color }} data-testid={`feature-card-${f.feature_id}`} testID={`feature-card-${f.feature_id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(f.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={f.icon} size={18} color={f.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{f.name}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>Engagement: {f.engagement_score}/100</Text>
                </View>
                <View style={{ width: 50, height: 50, borderRadius: 25, backgroundColor: (globalThis as any).__alphaColor(f.color, '10'), alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: (globalThis as any).__alphaColor(f.color, '40') }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: f.color }}>{f.engagement_score}</Text>
                </View>
              </View>

              {/* Stats Row */}
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
                <Stat label="Today" value={f.usage_today} color={T.primary} />
                <Stat label="7-day" value={f.usage_7d} color={T.cyan} />
                <Stat label="30-day" value={f.usage_30d} color={T.teal} />
                <Stat label="Users (7d)" value={f.unique_users_7d} color={T.successText} />
                <Stat label="Items" value={f.items_total} color={T.purpleText} />
              </View>

              {/* Completion Rate */}
              {f.completion_rate > 0 && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.007', 'Completion:')}</Text>
                  <View style={{ flex: 1, height: 6, backgroundColor: T.bgSoft, borderRadius: 3, overflow: 'hidden' }}>
                    <View style={{ width: `${f.completion_rate}%` as any, height: '100%', backgroundColor: T.success, borderRadius: 3 }} />
                  </View>
                  <Text style={{ color: T.successText, fontSize: 11, fontWeight: '700' }}>{f.completion_rate}%</Text>
                </View>
              )}

              {/* Mini Trend */}
              <View>
                <Text style={{ color: T.textMuted, fontSize: 10, marginBottom: 4 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.008', '7-Day Trend')}</Text>
                <MiniBar data={(f.daily_trend || []).map((d: any) => d.count)} color={f.color} h={28} />
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 }}>
                  {(f.daily_trend || []).map((d: any, i: number) => (
                    <Text key={i} style={{ color: T.textMuted, fontSize: 8 }}>{d.date}</Text>
                  ))}
                </View>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Power Users */}
      {section === 'users' && (
        <View style={{ gap: 12 }}>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="power-users-card" testID="power-users-card">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <Ionicons name="trophy" size={18} color={T.warningText} />
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.009', 'Top AI Power Users (7 days)')}</Text>
            </View>
            {(!power_users || power_users.length === 0) ? (
              <View style={{ paddingVertical: 24, alignItems: 'center' }}>
                <Ionicons name="people-outline" size={32} color={T.textMuted} />
                <Text style={{ color: T.textSec, fontSize: 13, marginTop: 8 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.010', 'No active AI users in this period')}</Text>
              </View>
            ) : (
              <View style={{ gap: 2 }}>
                {/* Header */}
                <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 8, backgroundColor: T.bgSoft, borderRadius: 8 }}>
                  <Text style={{ width: 28, color: T.textMuted, fontSize: 10, fontWeight: '700' }}>#</Text>
                  <Text style={{ flex: 2, color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.011', 'USER')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.012', 'PLAN')}</Text>
                  <Text style={{ flex: 0.7, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.013', 'USES')}</Text>
                  <Text style={{ flex: 0.7, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.014', 'TOOLS')}</Text>
                </View>
                {power_users.map((u: any, i: number) => {
                  const medalColor = i === 0 ? 'var(--app-primary)' : i === 1 ? 'var(--app-primary)' : i === 2 ? 'var(--app-primary)' : T.textMuted;
                  const planColor = u.plan === 'premium' ? T.warning : u.plan === 'basic' ? T.primary : T.textMuted;
                  return (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: T.border }} data-testid={`power-user-${i}`} testID={`power-user-${i}`}>
                      <View style={{ width: 28 }}>
                        <Text style={{ fontSize: 12, fontWeight: '800', color: medalColor }}>{i + 1}</Text>
                      </View>
                      <View style={{ flex: 2 }}>
                        <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>{u.name || 'User'}</Text>
                        <Text style={{ color: T.textMuted, fontSize: 10 }} numberOfLines={1}>{u.email}</Text>
                      </View>
                      <View style={{ flex: 1, alignItems: 'center' }}>
                        <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(planColor, '20') }}>
                          <Text style={{ color: planColor, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{u.plan}</Text>
                        </View>
                      </View>
                      <Text style={{ flex: 0.7, color: T.text, fontSize: 13, fontWeight: '700', textAlign: 'center' }}>{u.total_usage}</Text>
                      <Text style={{ flex: 0.7, color: T.cyan, fontSize: 13, fontWeight: '700', textAlign: 'center' }}>{u.features_count}</Text>
                    </View>
                  );
                })}
              </View>
            )}
          </View>

          {/* Multi-feature stats */}
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <KPI icon="git-merge" color={T.purpleText} label="Multi-Feature Users" value={overview.multi_feature_users} />
            <KPI icon="apps" color={T.cyan} label="Features Available" value={overview.features_count} />
          </View>
        </View>
      )}

      {/* AI Insights */}
      {section === 'insights' && (
        <View style={{ gap: 14 }}>
          <View style={{ backgroundColor: T.card, borderRadius: 16, padding: 18, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '30') }} data-testid="ai-insights-card" testID="ai-insights-card">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.purple, '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="sparkles" size={18} color={T.purpleText} />
              </View>
              <View>
                <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.015', 'AI-Generated Insights')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.016', 'Powered by AI analysis of your platform data')}</Text>
              </View>
            </View>
            <View style={{ backgroundColor: T.bgSoft, borderRadius: 12, padding: 14 }}>
              {(ai_insights || '').split('\n').filter((l: string) => l.trim()).map((line: string, i: number) => (
                <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: T.purple, marginTop: 6 }} />
                  <Text style={{ color: T.text, fontSize: 12, lineHeight: 20, flex: 1 }}>{line.replace(/^[\s\-*•]+/, '').trim()}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Quick Stats Summary */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="quick-stats-summary" testID="quick-stats-summary">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIFeatureAnalyticsPanel.auto.text.017', 'Executive Summary')}</Text>
            <View style={{ gap: 10 }}>
              <SummaryRow icon="people" color={T.successText} label="Platform Adoption" value={`${overview.adoption_rate}% of ${overview.total_users} users`} />
              <SummaryRow icon="flash" color={T.primary} label="AI Requests (7d)" value={overview.total_usage_7d.toString()} />
              <SummaryRow icon="layers" color={T.purpleText} label="Content Created" value={`${overview.total_items_created} items across all features`} />
              <SummaryRow icon="git-merge" color={T.orangeText} label="Cross-Feature" value={`${overview.multi_feature_users} users use 2+ AI tools`} />
              <SummaryRow icon="trophy" color={T.warningText} label="Top Feature" value={feature_stats?.[0]?.name || 'N/A'} />
            </View>
          </View>
        </View>
      )}
    </View>
  );
}

function KPI({ icon, color, label, value }: { icon: string; color: string; label: string; value: number | string }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: color, minWidth: 140, flex: 1 }} data-testid={`kpi-${label.replace(/\s/g, '-').toLowerCase()}`} testID={`kpi-${label.replace(/\s/g, '-').toLowerCase()}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <View style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={12} color={color} />
        </View>
        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600', flex: 1 }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 20, fontWeight: '800' }}>{typeof value === 'number' ? value.toLocaleString() : value}</Text>
    </View>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ flex: 1, alignItems: 'center', paddingVertical: 6, backgroundColor: (globalThis as any).__alphaColor(color, '08'), borderRadius: 8 }}>
      <Text style={{ color, fontSize: 14, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: T.textMuted, fontSize: 9, marginTop: 2 }}>{label}</Text>
    </View>
  );
}

function SummaryRow({ icon, color, label, value }: { icon: string; color: string; label: string; value: string }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}>
      <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '15'), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon as any} size={14} color={color} />
      </View>
      <Text style={{ color: T.textSec, fontSize: 12, flex: 1 }}>{label}</Text>
      <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{value}</Text>
    </View>
  );
}
