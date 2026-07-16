import React, { useState } from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
let T = {
  bg: 'var(--app-bg)' as any,
  bgSoft: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  cardHover: 'var(--app-card-muted)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  primarySoft: 'var(--app-primary-soft)' as any,
  primaryText: 'var(--app-primary-text)' as any,
  success: 'var(--app-success)' as any,
  successSoft: 'var(--app-success-soft)' as any,
  successText: 'var(--app-success)' as any,
  warning: 'var(--app-warning)' as any,
  warningSoft: 'var(--app-warning-soft)' as any,
  warningText: 'var(--app-warning)' as any,
  error: 'var(--app-error)' as any,
  errorSoft: 'var(--app-error-soft)' as any,
  purple: 'var(--app-primary)' as any,
  purpleSoft: 'var(--app-primary-soft)' as any,
  purpleText: 'var(--app-primary)' as any,
  cyan: 'var(--app-info)' as any,
  cyanSoft: 'var(--app-info-soft)' as any,
  pink: 'var(--app-error)' as any,
  pinkSoft: 'var(--app-error-soft)' as any,
  orange: 'var(--app-warning)' as any,
  orangeSoft: 'var(--app-warning-soft)' as any,
  teal: 'var(--app-primary)' as any,
  tealSoft: 'var(--app-primary-soft)' as any,
};

interface Props { colors: any; }

const tx = (_key: string, fallback: string) => fallback;

function MiniBarChart({ data, color, height = 40 }: { data: number[]; color: string; height?: number }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data, 1);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height }} data-testid="mini-bar-chart" testID="mini-bar-chart">
      {data.map((v, i) => (
        <View key={i} style={{ flex: 1, height: Math.max(2, (v / max) * height), backgroundColor: color, borderRadius: 2, opacity: 0.5 + (i / data.length) * 0.5 }} />
      ))}
    </View>
  );
}

function HorizBar({ data, labelKey, valueKey, color }: { data: any[]; labelKey: string; valueKey: string; color: string }) {
  if (!data || data.length === 0) return <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.001', 'No data available')}</Text>;
  const maxVal = Math.max(...data.map(d => d[valueKey] || 0), 1);
  return (
    <View style={{ gap: 6 }}>
      {data.slice(0, 8).map((item, i) => (
        <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={{ color: T.textSec, fontSize: 11, width: 100, textAlign: 'right' }} numberOfLines={1}>{item[labelKey]}</Text>
          <View style={{ flex: 1, height: 18, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
            <View style={{ width: `${Math.max(2, (item[valueKey] / maxVal) * 100)}%` as any, height: '100%', backgroundColor: (globalThis as any).__alphaColor(color, '60'), borderRadius: 4 }} />
          </View>
          <Text style={{ color: T.text, fontSize: 11, fontWeight: '700', minWidth: 36 }}>{item[valueKey]}</Text>
        </View>
      ))}
    </View>
  );
}

function PieVisual({ data, colors: chartColors }: { data: { label: string; value: number }[]; colors: string[] }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16 }} data-testid="pie-visual" testID="pie-visual">
      <View style={{ gap: 3 }}>
        {data.map((d, i) => {
          const pct = Math.round((d.value / total) * 100);
          return (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 }}>
              <View style={{ width: 80, height: 14, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
                <View style={{ width: `${Math.max(3, pct)}%` as any, height: '100%', backgroundColor: chartColors[i % chartColors.length], borderRadius: 4 }} />
              </View>
              <Text style={{ color: T.textSec, fontSize: 11 }}>{d.label}</Text>
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{d.value} ({pct}%)</Text>
            </View>
          );
        })}
      </View>
      <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: T.bgSoft, alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: chartColors[0] }}>
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{total}</Text>
        <Text style={{ color: T.textMuted, fontSize: 8 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.002', 'TOTAL')}</Text>
      </View>
    </View>
  );
}

export default function AIUsageAnalyticsPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  T = {
    ...T,
    bg: AC.bg,
    bgSoft: AC.card,
    card: AC.card,
    cardHover: AC.surfaceHover,
    border: AC.border,
    text: AC.text,
    textSec: AC.textSec,
    textMuted: AC.textDim,
    primary: AC.primary,
    primarySoft: AC.primarySoft,
    primaryText: AC.primaryText,
    success: AC.success,
    successSoft: AC.successSoft,
    successText: AC.successText,
    warning: AC.warning,
    warningSoft: AC.warningSoft,
    warningText: AC.warningText,
    error: AC.error,
    errorSoft: AC.errorSoft,
    purple: AC.purple,
    purpleSoft: AC.purpleSoft,
    purpleText: AC.purpleText,
    cyan: AC.info,
    cyanSoft: AC.infoSoft,
    orange: AC.orange,
    orangeSoft: AC.orangeSoft,
    teal: AC.teal,
    tealSoft: AC.infoSoft,
    pink: AC.error,
    pinkSoft: AC.errorSoft,
  };
  const { data, loading } = useLiveQuery('/admin/ai-usage-analytics', { entity: 'ai-usage', pollInterval: 60000 });
  const [section, setSection] = useState('overview');

  if (loading) return <View style={{ paddingVertical: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;
  if (!data) return <Text style={{ color: T.error, padding: 20 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.003', 'Failed to load analytics')}</Text>;

  const { overview, tier_distribution, tier_usage, daily_trend, top_features, limit_hit_users, conversion_funnel, upgrade_stats } = data;
  const trendRequests = daily_trend?.map((d: any) => d.requests) || [];
  const trendUsers = daily_trend?.map((d: any) => d.unique_users) || [];

  const sections = [
    { id: 'overview', label: 'Overview', icon: 'grid' },
    { id: 'usage', label: 'Usage Trends', icon: 'trending-up' },
    { id: 'limits', label: 'Limit Hits', icon: 'warning' },
    { id: 'conversions', label: 'Conversions', icon: 'swap-horizontal' },
  ];

  return (
    <View data-testid="ai-usage-analytics-panel" testID="ai-usage-analytics-panel">
      <View style={{ marginBottom: 16 }}>
        <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="ai-usage-analytics-title" testID="ai-usage-analytics-title">{tx('admin.aIUsageAnalyticsPanel.auto.text.004', 'AI Usage Intelligence')}</Text>
        <Text style={{ fontSize: 12, color: T.textSec, marginTop: 4 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.005', 'Track usage patterns, limit hits, and tier conversion insights')}</Text>
      </View>

      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20, flexWrap: 'wrap' }} data-testid="ai-usage-section-tabs" testID="ai-usage-section-tabs">
        {sections.map(s => (
          <TouchableOpacity key={s.id} style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8,
            borderRadius: 10, backgroundColor: section === s.id ? T.primary : T.bgSoft,
          }} onPress={() => setSection(s.id)} data-testid={`ai-usage-tab-${s.id}`} testID={`ai-usage-tab-${s.id}`}>
            <Ionicons name={s.icon as any} size={14} color={section === s.id ? T.primaryText : T.textSec} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: section === s.id ? T.primaryText : T.textSec }}>{s.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {section === 'overview' && (
        <View style={{ gap: 16 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }} data-testid="ai-usage-kpis" testID="ai-usage-kpis">
            <KPI icon="flash" color={T.primary} label="Requests Today" value={overview.total_requests_today} spark={trendRequests} />
            <KPI icon="calendar" color={T.cyan} label="Requests (7d)" value={overview.total_requests_7d} />
            <KPI icon="people" color={T.successText} label="Active Users Today" value={overview.unique_users_today} spark={trendUsers} />
            <KPI icon="people" color={T.teal} label="Active Users (7d)" value={overview.unique_users_7d} />
            <KPI icon="warning" color={T.warningText} label="Limit Hits (7d)" value={overview.limit_hits_7d} />
            <KPI icon="arrow-up-circle" color={T.purpleText} label="Requests (30d)" value={overview.total_requests_30d} />
          </View>

          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="tier-distribution-card" testID="tier-distribution-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.006', 'Tier Distribution')}</Text>
            <PieVisual
              data={[
                { label: 'Free', value: tier_distribution?.free || 0 },
                { label: 'Basic', value: tier_distribution?.basic || 0 },
                { label: 'Premium', value: tier_distribution?.premium || 0 },
              ]}
              colors={[T.textMuted, T.primary, T.warning]}
            />
          </View>

          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="tier-usage-card" testID="tier-usage-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.007', 'Usage by Tier (7 days)')}</Text>
            <View style={{ gap: 10 }}>
              {(['free', 'basic', 'premium'] as const).map(plan => {
                const tu = tier_usage?.[plan];
                const tierColor = plan === 'free' ? T.textMuted : plan === 'basic' ? T.primary : T.warning;
                return (
                  <View key={plan} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }} data-testid={`tier-usage-${plan}`} testID={`tier-usage-${plan}`}>
                    <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(tierColor, '20'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name={plan === 'free' ? 'flash-outline' : plan === 'basic' ? 'rocket-outline' : 'diamond-outline'} size={14} color={tierColor} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{plan.charAt(0).toUpperCase() + plan.slice(1)}</Text>
                      <Text style={{ color: T.textSec, fontSize: 11 }}>{tu?.user_count || 0} users</Text>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{tu?.total_requests || 0}</Text>
                      <Text style={{ color: T.textSec, fontSize: 10 }}>{tu?.avg_per_user || 0} avg/user</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          </View>
        </View>
      )}

      {section === 'usage' && (
        <View style={{ gap: 16 }}>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="daily-trend-card" testID="daily-trend-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 4 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.008', 'Daily Requests (14 days)')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.009', 'AI request volume over time')}</Text>
            <MiniBarChart data={trendRequests} color={T.primary} height={48} />
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
              {daily_trend?.slice(-7).map((d: any, i: number) => (
                <View key={i} style={{ alignItems: 'center', minWidth: 36 }}>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{d.date?.slice(5)}</Text>
                  <Text style={{ color: T.text, fontSize: 10, fontWeight: '600' }}>{d.requests}</Text>
                </View>
              ))}
            </View>
          </View>

          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="user-trend-card" testID="user-trend-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 4 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.010', 'Active Users Trend')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.011', 'Unique users per day')}</Text>
            <MiniBarChart data={trendUsers} color={T.successText} height={48} />
          </View>

          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="top-features-card" testID="top-features-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.012', 'Top AI Features (7 days)')}</Text>
            <HorizBar data={top_features} labelKey="feature" valueKey="requests" color={T.cyan} />
          </View>
        </View>
      )}

      {section === 'limits' && (
        <View style={{ gap: 16 }}>
          <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
            <KPI icon="warning" color={T.warningText} label="Total Limit Hits (7d)" value={overview.limit_hits_7d} />
            <KPI icon="people" color={T.error} label="Unique Users Hit" value={conversion_funnel?.users_hit_limit || 0} />
          </View>

          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="limit-hit-users-card" testID="limit-hit-users-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 4 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.013', 'Users Hitting Limits')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.014', 'Users who reached their daily AI request limit in the last 7 days')}</Text>
            {(!limit_hit_users || limit_hit_users.length === 0) ? (
              <View style={{ paddingVertical: 20, alignItems: 'center' }}>
                <Ionicons name="checkmark-circle" size={32} color={T.successText} />
                <Text style={{ color: T.textSec, fontSize: 13, marginTop: 8 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.015', 'No users hit their limits recently')}</Text>
              </View>
            ) : (
              <View style={{ gap: 1 }}>
                <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 8, backgroundColor: T.bgSoft, borderRadius: 8 }}>
                  <Text style={{ flex: 2, color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.016', 'USER')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.017', 'PLAN')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.018', 'HITS')}</Text>
                  <Text style={{ flex: 1.5, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.019', 'LAST HIT')}</Text>
                </View>
                {limit_hit_users.map((u: any, i: number) => {
                  const planColor = u.plan === 'free' ? T.textMuted : u.plan === 'basic' ? T.primary : T.warning;
                  return (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: T.border }} data-testid={`limit-user-row-${i}`} testID={`limit-user-row-${i}`}>
                      <View style={{ flex: 2 }}>
                        <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>{u.name || 'User'}</Text>
                        <Text style={{ color: T.textMuted, fontSize: 10 }} numberOfLines={1}>{u.email}</Text>
                      </View>
                      <View style={{ flex: 1, alignItems: 'center' }}>
                        <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(planColor, '20') }}>
                          <Text style={{ color: planColor, fontSize: 10, fontWeight: '700' }}>{u.plan?.toUpperCase()}</Text>
                        </View>
                      </View>
                      <Text style={{ flex: 1, color: T.warningText, fontSize: 13, fontWeight: '700', textAlign: 'center' }}>{u.hits}x</Text>
                      <Text style={{ flex: 1.5, color: T.textSec, fontSize: 10, textAlign: 'center' }}>{u.days?.[0]?.date?.slice(5) || '-'}</Text>
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        </View>
      )}

      {section === 'conversions' && (
        <View style={{ gap: 16 }}>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="conversion-funnel-card" testID="conversion-funnel-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.020', 'Conversion Funnel')}</Text>
            <View style={{ gap: 12 }}>
              <FunnelStep label="Users Hit Limit" value={conversion_funnel?.users_hit_limit || 0} color={T.warningText} total={conversion_funnel?.users_hit_limit || 0} />
              <View style={{ alignItems: 'center' }}><Ionicons name="arrow-down" size={16} color={T.textMuted} /></View>
              <FunnelStep label="Users Upgraded" value={conversion_funnel?.users_upgraded || 0} color={T.successText} total={conversion_funnel?.users_hit_limit || 1} />
              <View style={{ alignSelf: 'center', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 10, backgroundColor: (conversion_funnel?.conversion_rate || 0) > 0 ? T.successSoft : T.warningSoft }}>
                <Text style={{ color: (conversion_funnel?.conversion_rate || 0) > 0 ? T.success : T.warning, fontSize: 16, fontWeight: '800' }}>
                  {conversion_funnel?.conversion_rate || 0}% Conversion Rate
                </Text>
              </View>
            </View>
          </View>

          {upgrade_stats && upgrade_stats.length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="upgrade-revenue-card" testID="upgrade-revenue-card">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.021', 'Upgrade Revenue (30 days)')}</Text>
              {upgrade_stats.map((s: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}>
                  <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: T.successSoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="card" size={16} color={T.successText} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{s.plan?.charAt(0).toUpperCase() + s.plan?.slice(1)} Plan</Text>
                    <Text style={{ color: T.textSec, fontSize: 11 }}>{s.conversions} conversion{s.conversions !== 1 ? 's' : ''}</Text>
                  </View>
                  <Text style={{ color: T.successText, fontSize: 15, fontWeight: '800' }}>${(s.revenue || 0).toFixed(2)}</Text>
                </View>
              ))}
            </View>
          )}

          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="conversions-log-card" testID="conversions-log-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.022', 'Recent Activity Log')}</Text>
            {(!data.conversions || data.conversions.length === 0) ? (
              <Text style={{ color: T.textMuted, fontSize: 12, textAlign: 'center', paddingVertical: 16 }}>{tx('admin.aIUsageAnalyticsPanel.auto.text.023', 'No conversion events recorded yet')}</Text>
            ) : (
              <View style={{ gap: 6 }}>
                {data.conversions.slice(0, 10).map((c: any, i: number) => {
                  const actionColor = c.action?.includes('upgrade') ? T.success : c.action?.includes('downgrade') ? T.error : T.textSec;
                  return (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: T.border }}>
                      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: actionColor }} />
                      <Text style={{ color: T.text, fontSize: 11, flex: 1 }} numberOfLines={1}>{c.user_id?.slice(0, 12) || ''}...</Text>
                      <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(actionColor, '20') }}>
                        <Text style={{ color: actionColor, fontSize: 10, fontWeight: '600' }}>{c.action}</Text>
                      </View>
                      <Text style={{ color: T.textMuted, fontSize: 10 }}>{c.timestamp?.slice(0, 10) || '-'}</Text>
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        </View>
      )}
    </View>
  );
}

function KPI({ icon, color, label, value, spark }: { icon: string; color: string; label: string; value: number; spark?: number[] }) {
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: color, minWidth: 150, flex: 1 }} data-testid={`kpi-${label.replace(/\s/g, '-').toLowerCase()}`} testID={`kpi-${label.replace(/\s/g, '-').toLowerCase()}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <View style={{ width: 24, height: 24, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={13} color={color} />
        </View>
        <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600', flex: 1 }}>{label}</Text>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{typeof value === 'number' ? value.toLocaleString() : value}</Text>
        {spark && <MiniBarChart data={spark} color={color} height={24} />}
      </View>
    </View>
  );
}

function FunnelStep({ label, value, color, total }: { label: string; value: number; color: string; total: number }) {
  const pct = total > 0 ? Math.max(5, (value / total) * 100) : 5;
  return (
    <View style={{ alignItems: 'center', gap: 4 }}>
      <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{label}</Text>
      <View style={{ width: '80%', height: 32, backgroundColor: T.bgSoft, borderRadius: 8, overflow: 'hidden', justifyContent: 'center' }}>
        <View style={{ width: `${pct}%` as any, height: '100%', backgroundColor: (globalThis as any).__alphaColor(color, '40'), borderRadius: 8 }} />
        <Text style={{ position: 'absolute', alignSelf: 'center', color: T.text, fontSize: 14, fontWeight: '800' }}>{value}</Text>
      </View>
    </View>
  );
}
