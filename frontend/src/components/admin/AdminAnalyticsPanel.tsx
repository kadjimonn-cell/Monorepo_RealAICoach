import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTheme } from '../../context/ThemeContext';
import { humanizeAdminToken, normalizeAdminRuntimeCopy } from '../../i18n/adminCopyGuard';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}

export default function AdminAnalyticsPanel({ colors }: { colors: any }) {
  const { darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const C = getC(darkMode);
  const { data: generalAnalytics, loading: gLoading } = useLiveQuery('/admin/general-analytics/summary', { entity: 'analytics', pollInterval: 60000 });
  const { data: chartData, loading: cLoading } = useLiveQuery('/admin/general-analytics/charts', { entity: 'analytics', pollInterval: 60000 });
  const [insights, setInsights] = useState<string>('');
  const [insightsLoading, setInsightsLoading] = useState(false);
  const loading = gLoading || cLoading;

  const runInsights = async () => {
    setInsightsLoading(true);
    try {
      const res = await api.post('/admin/general-analytics/insights');
      setInsights(res.data.insight);
    } catch (e) { console.error('Insights error', e); }
    setInsightsLoading(false);
  };

  if (loading) return <View style={{ padding: 30, alignItems: 'center' }}><ActivityIndicator size="large" color={C.blue} /></View>;

  return (
    <View data-testid="admin-general-analytics-section" testID="admin-general-analytics-section">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="stats-chart" size={20} color={C.blue} />
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '700' }}>{tx('admin.adminAnalyticsPanel.header.title', 'General Analytics')}</Text>
        </View>
        <TouchableOpacity style={{ backgroundColor: colors.primary, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }} onPress={runInsights} data-testid="admin-ai-insights-btn" testID="admin-ai-insights-btn">
          {insightsLoading ? <ActivityIndicator color="var(--app-primary)" size="small" /> : <><Ionicons name="sparkles" size={14} color="var(--app-primary)" /><Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 11 }}>{tx('admin.adminAnalyticsPanel.actions.aiInsights', 'AI Insights')}</Text></>}
        </TouchableOpacity>
      </View>

      {/* KPI Cards Row */}
      <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
        {[
          { label: 'Total Users', value: generalAnalytics?.platform?.total_users, color: C.blue, icon: 'people' as const },
          { label: 'Active Users', value: generalAnalytics?.platform?.active_users, color: C.green, icon: 'pulse' as const },
          { label: 'Conversion', value: generalAnalytics?.platform?.subscription_conversion_rate?.toFixed ? `${generalAnalytics.platform.subscription_conversion_rate.toFixed(1)}%` : '--', color: C.yellow, icon: 'trending-up' as const },
          { label: 'Churn Rate', value: generalAnalytics?.platform?.churn_rate?.toFixed ? `${generalAnalytics.platform.churn_rate.toFixed(1)}%` : '--', color: C.red, icon: 'trending-down' as const },
          { label: 'Total Revenue', value: generalAnalytics?.financial?.total_revenue != null ? `$${generalAnalytics.financial.total_revenue}` : '--', color: C.purple, icon: 'cash' as const },
          { label: 'MRR', value: generalAnalytics?.financial?.monthly_recurring_revenue != null ? `$${generalAnalytics.financial.monthly_recurring_revenue}` : '--', color: C.cyan, icon: 'card' as const },
        ].map((kpi, i) => (
          <View key={i} style={{ backgroundColor: C.card, padding: 14, borderRadius: 12, minWidth: 140, flex: 1, borderLeftWidth: 3, borderLeftColor: kpi.color }} data-testid={`kpi-${kpi.label.toLowerCase().replace(/\s/g, '-')}`} testID={`kpi-${kpi.label.toLowerCase().replace(/\s/g, '-')}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
              <Ionicons name={kpi.icon} size={12} color={kpi.color} />
              <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600' }}>{kpi.label}</Text>
            </View>
            <Text style={{ color: kpi.color, fontSize: 22, fontWeight: '800' }}>{kpi.value ?? '--'}</Text>
          </View>
        ))}
      </View>

      {/* Charts */}
      {chartData && (
        <>
          {chartData.user_growth?.length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 12 }} data-testid="chart-user-growth" testID="chart-user-growth">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.adminAnalyticsPanel.charts.userGrowth', 'User Growth (30 days)')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 80 }}>
                {chartData.user_growth.map((d: any, i: number) => {
                  const maxVal = Math.max(...chartData.user_growth.map((x: any) => x.users), 1);
                  const h = Math.max((d.users / maxVal) * 70, 2);
                  return (
                    <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                      <View style={{ width: '80%', height: h, backgroundColor: d.users > 0 ? C.blue : C.border, borderRadius: 2 }} />
                      {i % 5 === 0 && <Text style={{ color: colors.textSec, fontSize: 7, marginTop: 2 }}>{d.date}</Text>}
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          {chartData.daily_active_users?.length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 12 }} data-testid="chart-dau" testID="chart-dau">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.adminAnalyticsPanel.charts.dailyActiveUsers', 'Daily Active Users (14 days)')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 70 }}>
                {chartData.daily_active_users.map((d: any, i: number) => {
                  const maxVal = Math.max(...chartData.daily_active_users.map((x: any) => x.dau), 1);
                  const h = Math.max((d.dau / maxVal) * 60, 2);
                  return (
                    <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                      <Text style={{ color: C.green, fontSize: 8, fontWeight: '700', marginBottom: 2 }}>{d.dau > 0 ? d.dau : ''}</Text>
                      <View style={{ width: '85%', height: h, backgroundColor: d.dau > 0 ? C.green : C.border, borderRadius: 3 }} />
                      <Text style={{ color: colors.textSec, fontSize: 7, marginTop: 2 }}>{d.date}</Text>
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 12 }}>
            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 12, padding: 14 }} data-testid="chart-subscriptions" testID="chart-subscriptions">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.adminAnalyticsPanel.charts.subscriptions', 'Subscriptions')}</Text>
              {(chartData.subscription_distribution || []).map((s: any, i: number) => {
                const total = chartData.subscription_distribution.reduce((a: number, b: any) => a + b.count, 0) || 1;
                const pct = Math.round((s.count / total) * 100);
                const planColors: Record<string, string> = { free: 'var(--app-text)', basic: C.blue, premium: C.yellow };
                const col = planColors[s.plan] || C.purple;
                return (
                  <View key={i} style={{ marginBottom: 8 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
                      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'capitalize' }}>{humanizeAdminToken(s.plan, tx('admin.adminAnalyticsPanel.plan.fallback', 'Plan'))}</Text>
                      <Text style={{ color: col, fontSize: 11, fontWeight: '800' }}>{s.count} ({pct}%)</Text>
                    </View>
                    <View style={{ height: 5, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
                      <View style={{ height: '100%', width: `${pct}%`, backgroundColor: col, borderRadius: 3 }} />
                    </View>
                  </View>
                );
              })}
            </View>

            <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 12, padding: 14 }} data-testid="chart-ai-sentiment" testID="chart-ai-sentiment">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.adminAnalyticsPanel.charts.aiFeedback', 'AI Feedback')}</Text>
              {(() => {
                const pos = chartData.ai_sentiment?.positive || 0;
                const neg = chartData.ai_sentiment?.negative || 0;
                const total = pos + neg || 1;
                const posPct = Math.round((pos / total) * 100);
                return (
                  <>
                    <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 16, marginBottom: 10 }}>
                      <View style={{ alignItems: 'center' }}>
                        <Ionicons name="thumbs-up" size={20} color={C.green} />
                        <Text style={{ color: C.green, fontSize: 18, fontWeight: '800' }}>{pos}</Text>
                      </View>
                      <View style={{ alignItems: 'center' }}>
                        <Ionicons name="thumbs-down" size={20} color={C.red} />
                        <Text style={{ color: C.red, fontSize: 18, fontWeight: '800' }}>{neg}</Text>
                      </View>
                    </View>
                    <View style={{ height: 8, backgroundColor: C.border, borderRadius: 4, overflow: 'hidden', flexDirection: 'row' }}>
                      <View style={{ height: '100%', width: `${posPct}%`, backgroundColor: C.green }} />
                      <View style={{ height: '100%', flex: 1, backgroundColor: C.red }} />
                    </View>
                    <Text style={{ color: C.muted, fontSize: 10, textAlign: 'center', marginTop: 4 }}>{posPct}% positive</Text>
                  </>
                );
              })()}
            </View>
          </View>

          {chartData.top_features?.length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 12 }} data-testid="chart-top-features" testID="chart-top-features">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.adminAnalyticsPanel.charts.topFeatures', 'Top Features by Usage')}</Text>
              {chartData.top_features.slice(0, 8).map((f: any, i: number) => {
                const maxCount = chartData.top_features[0]?.count || 1;
                const pct = Math.round((f.count / maxCount) * 100);
                return (
                  <View key={i} style={{ marginBottom: 6 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 }}>
                      <Text style={{ color: colors.textMuted, fontSize: 11, textTransform: 'capitalize' }}>{humanizeAdminToken(f.feature, tx('admin.adminAnalyticsPanel.feature.fallback', 'Feature'))}</Text>
                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{f.count}</Text>
                    </View>
                    <View style={{ height: 4, backgroundColor: C.border, borderRadius: 2, overflow: 'hidden' }}>
                      <View style={{ height: '100%', width: `${pct}%`, backgroundColor: C.purple, borderRadius: 2 }} />
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {chartData.security_by_type?.length > 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 14, marginBottom: 12 }} data-testid="chart-security-events" testID="chart-security-events">
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.adminAnalyticsPanel.charts.securityEvents', 'Security Events (7d)')}</Text>
              {chartData.security_by_type.map((s: any, i: number) => {
                const maxCount = chartData.security_by_type[0]?.count || 1;
                const pct = Math.round((s.count / maxCount) * 100);
                const isRisky = ['login_failed', 'blocked_ip', 'jwt_invalid', 'admin_access_denied'].includes(s.type);
                const col = isRisky ? C.red : C.blue;
                return (
                  <View key={i} style={{ marginBottom: 6 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 }}>
                      <Text style={{ color: colors.textMuted, fontSize: 11, textTransform: 'capitalize' }}>{humanizeAdminToken(s.type, tx('admin.adminAnalyticsPanel.event.fallback', 'System event'))}</Text>
                      <Text style={{ color: col, fontSize: 10, fontWeight: '700' }}>{s.count}</Text>
                    </View>
                    <View style={{ height: 4, backgroundColor: C.border, borderRadius: 2, overflow: 'hidden' }}>
                      <View style={{ height: '100%', width: `${pct}%`, backgroundColor: col, borderRadius: 2 }} />
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </>
      )}

      {/* AI Insights output */}
      {insights ? (
        <View style={{ backgroundColor: C.bg, padding: 14, borderRadius: 12, marginTop: 4, borderWidth: 1, borderColor: C.border }} data-testid="admin-ai-insights-output" testID="admin-ai-insights-output">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <Ionicons name="sparkles" size={14} color={C.yellow} />
            <Text style={{ color: C.yellow, fontSize: 12, fontWeight: '700' }}>{tx('admin.adminAnalyticsPanel.insights.title', 'AI Insight Engine')}</Text>
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18 }}>{normalizeAdminRuntimeCopy(insights, tx('admin.adminAnalyticsPanel.insights.empty', 'AI insights will appear here after analysis runs.'))}</Text>
        </View>
      ) : null}
    </View>
  );
}
