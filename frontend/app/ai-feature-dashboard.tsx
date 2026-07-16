import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { View, Text, FlatList, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../src/context/ThemeContext';
import { useRealtime } from '../src/context/RealtimeContext';
import AppShell from '../src/components/AppShell';
import { ExecutiveDashboardSkeleton } from '../src/components/SkeletonLoaders';
import api from '@/src/services/api';
import { useTranslation } from '../src/hooks/useTranslation';
import { reportClientCrash } from '../src/services/clientErrorReporter';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

const RETRYABLE_HTTP_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

const waitFor = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const isRetryableApiError = (error: any) => {
  const status = Number(error?.response?.status || 0);
  if (RETRYABLE_HTTP_STATUS.has(status)) return true;
  const code = String(error?.code || '').toLowerCase();
  return code.includes('timeout') || code.includes('network') || code.includes('econnaborted');
};

const extractErrorText = (error: any, fallback: string) => (
  error?.response?.data?.detail
  || error?.message
  || fallback
);

const reportDashboardRecoverableError = (scope: string, error: any, message: string) => {
  reportClientCrash({
    panelId: `ai-feature-dashboard:${scope}`,
    panelName: 'AIFeatureDashboard',
    message,
    stack: String(error?.stack || error?.message || ''),
  });
};

export default function AIFeatureDashboard() {
  const { t } = useTranslation();
  t('i18n.route.ai-feature-dashboard.probe');
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const C = useMemo(() => ({
    ...colors,
    bg: colors.bg, card: colors.card, cardAlt: colors.bgSoft, text: colors.text,
    muted: colors.textSec, dim: colors.textMuted, border: colors.border,
    primary: colors.primary, success: colors.success, error: colors.error, warn: colors.warning,
    purple: colors.purple, cyan: colors.info, pink: colors.purple, orange: colors.orange,
  }), [colors]);

  const { subscribeType } = useRealtime();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [featureData, setFeatureData] = useState<any>(null);
  const [usageData, setUsageData] = useState<any>(null);
  const [alertsData, setAlertsData] = useState<any>(null);
  const [alertConfig, setAlertConfig] = useState<any>(null);
  const [tab, setTab] = useState<'overview' | 'features' | 'users' | 'insights' | 'alerts'>('overview');
  const [checkingAlerts, setCheckingAlerts] = useState(false);
  const [alertFilter, setAlertFilter] = useState<'all' | 'active' | 'acknowledged'>('all');
  const [alertsError, setAlertsError] = useState<string>('');
  const realtimeRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Realtime alert subscription via shared RealtimeContext
  useEffect(() => {
    if (loading) return;
    return subscribeType('ai_alert', (data: any) => {
      const alert = data?.alert;
      if (!alert) return;
      setAlertsData((prev: any) => {
        if (!prev) return { alerts: [alert], active_count: 1, total: 1 };
        const exists = prev.alerts.some((a: any) => a.alert_id === alert.alert_id);
        if (exists) return prev;
        return {
          alerts: [alert, ...prev.alerts],
          active_count: (prev.active_count || 0) + 1,
          total: (prev.total || 0) + 1,
        };
      });
    });
  }, [loading, subscribeType]);

  const handleAcknowledge = useCallback(async (alertId: string) => {
    try {
      await api.put(`/admin/ai-alerts/${alertId}/acknowledge`);
      setAlertsError('');
      setAlertsData((prev: any) => {
        if (!prev) return prev;
        return {
          ...prev,
          alerts: prev.alerts.map((a: any) =>
            a.alert_id === alertId ? { ...a, acknowledged: true, acknowledged_at: new Date().toISOString() } : a
          ),
          active_count: Math.max(0, (prev.active_count || 1) - 1),
        };
      });
    } catch (error: any) {
      const message = extractErrorText(error, tx('aiFeatureDashboard.alerts.errors.ackFailed', 'Could not acknowledge alert. Please retry.'));
      reportDashboardRecoverableError('acknowledge', error, message);
      setAlertsError(message);
    }
  }, [tx]);

  const handleCheckNow = useCallback(async () => {
    setCheckingAlerts(true);
    setAlertsError('');
    let lastError: any = null;
    try {
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          await api.post('/admin/ai-alerts/check-now');
          const res = await api.get('/admin/ai-alerts');
          setAlertsData(res.data);
          setAlertsError('');
          return;
        } catch (error: any) {
          lastError = error;
          if (!isRetryableApiError(error) || attempt === 2) break;
          await waitFor((attempt + 1) * 1200);
        }
      }
      const message = extractErrorText(lastError, tx('aiFeatureDashboard.alerts.errors.checkNowFailed', 'Alert check failed. Please retry.'));
      reportDashboardRecoverableError('check-now', lastError, message);
      setAlertsError(message);
    } finally {
      setCheckingAlerts(false);
    }
  }, [tx]);

  const refreshAlerts = useCallback(async () => {
    let lastError: any = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const res = await api.get('/admin/ai-alerts', { params: { status: alertFilter } });
        setAlertsData(res.data);
        setAlertsError('');
        return;
      } catch (error: any) {
        lastError = error;
        if (!isRetryableApiError(error) || attempt === 1) break;
        await waitFor((attempt + 1) * 800);
      }
    }
    const message = extractErrorText(lastError, tx('aiFeatureDashboard.alerts.errors.refreshFailed', 'Could not refresh alerts.'));
    reportDashboardRecoverableError('refresh-alerts', lastError, message);
    setAlertsError(message);
  }, [alertFilter, tx]);

  useEffect(() => {
    if (tab === 'alerts' && !loading) refreshAlerts();
  }, [alertFilter, tab, loading, refreshAlerts]);

  const refreshDashboardFromRealtime = useCallback(async () => {
    try {
      const [fRes, uRes, aRes, cRes] = await Promise.all([
        api.get('/admin/ai-feature-analytics'),
        api.get('/admin/ai-usage-analytics'),
        api.get('/admin/ai-alerts', { params: { status: alertFilter } }),
        api.get('/admin/ai-alerts/config'),
      ]);
      setFeatureData(fRes.data);
      setUsageData(uRes.data);
      setAlertsData(aRes.data);
      setAlertConfig(cRes.data?.config);
      setAlertsError('');
    } catch (error: any) {
      const message = extractErrorText(error, tx('aiFeatureDashboard.alerts.errors.refreshFailed', 'Could not refresh alerts.'));
      reportDashboardRecoverableError('refresh-realtime', error, message);
      setAlertsError(message);
    }
  }, [alertFilter, tx]);

  useEffect(() => {
    if (loading) return;
    return subscribeType('data_change', (msg: any) => {
      const entity = String(msg?.entity || '').toLowerCase();
      if (!entity) return;
      const relevant = ['ai_alert', 'ai_alerts', 'ai_feature', 'ai_usage', 'feature_registry', 'config'];
      if (!relevant.some((token) => entity.includes(token))) return;

      if (realtimeRefreshTimerRef.current) clearTimeout(realtimeRefreshTimerRef.current);
      realtimeRefreshTimerRef.current = setTimeout(() => {
        void refreshDashboardFromRealtime();
      }, 300);
    });
  }, [loading, refreshDashboardFromRealtime, subscribeType]);

  useEffect(() => {
    return () => {
      if (realtimeRefreshTimerRef.current) {
        clearTimeout(realtimeRefreshTimerRef.current);
        realtimeRefreshTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    let retries = 0;
    const load = async () => {
      try {
        const [fRes, uRes, aRes, cRes] = await Promise.all([
          api.get('/admin/ai-feature-analytics'),
          api.get('/admin/ai-usage-analytics'),
          api.get('/admin/ai-alerts'),
          api.get('/admin/ai-alerts/config'),
        ]);
        setFeatureData(fRes.data);
        setUsageData(uRes.data);
        setAlertsData(aRes.data);
        setAlertConfig(cRes.data?.config);
        setLoading(false);
      } catch (e: any) {
        if ((e.response?.status === 401 || e.response?.status === 403) && retries < 3) {
          retries++;
          setTimeout(load, 1500);
        } else {
          setLoading(false);
        }
      }
    };
    load();
  }, []);

  useEffect(() => {
    if (!loading) return;
    const timeoutId = setTimeout(() => {
      setLoading(false);
      setAlertsError((prev) => prev || tx('aiFeatureDashboard.alerts.errors.refreshFailed', 'Could not refresh alerts.'));
    }, 12000);
    return () => clearTimeout(timeoutId);
  }, [loading, tx]);

  const getTimeAgo = (isoStr: string) => {
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return tx('aiFeatureDashboard.time.justNow', 'just now');
    if (mins < 60) return tx('aiFeatureDashboard.time.minutesAgo', '{mins}m ago').replace('{mins}', String(mins));
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return tx('aiFeatureDashboard.time.hoursAgo', '{hrs}h ago').replace('{hrs}', String(hrs));
    const days = Math.floor(hrs / 24);
    return tx('aiFeatureDashboard.time.daysAgo', '{days}d ago').replace('{days}', String(days));
  };

  const activeAlertCount = alertsData?.active_count || 0;

  if (loading) {
    return (
      <AdminRouteGate returnTo="/ai-feature-dashboard">
        <AppShell>
          <ExecutiveDashboardSkeleton />
        </AppShell>
      </AdminRouteGate>
    );
  }

  const overview = featureData?.overview || {};
  const features = featureData?.feature_stats || [];
  const powerUsers = featureData?.power_users || [];
  const correlations = featureData?.feature_correlations || [];
  const aiInsights = featureData?.ai_insights || '';
  const usageOverview = usageData?.overview || {};
  const dailyTrend = usageData?.daily_trend || [];
  const tierDist = usageData?.tier_distribution || {};
  const tierUsage = usageData?.tier_usage || {};

  // Mini sparkline
  const Sparkline = ({ data, color, h = 32 }: { data: number[]; color: string; h?: number }) => {
    if (!data.length) return null;
    const max = Math.max(...data, 1);
    const w = 100;
    const pts = data.map((v, i) => `${(i / Math.max(data.length - 1, 1)) * w},${h - (v / max) * h}`).join(' ');
    return (
      <View style={{ width: w, height: h }}>
        <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h}>
          <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </View>
    );
  };

  // Bar chart
  const BarChart = ({ data, maxH = 80 }: { data: { label: string; value: number; color?: string }[]; maxH?: number }) => {
    const max = Math.max(...data.map(d => d.value), 1);
    return (
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: maxH + 20 }}>
        {data.map((d, i) => (
          <View key={i} style={{ flex: 1, alignItems: 'center' }}>
            <Text style={{ color: C.muted, fontSize: 9, marginBottom: 2 }}>{d.value}</Text>
            <View style={{ width: '80%', height: Math.max(4, (d.value / max) * maxH), backgroundColor: d.color || C.primary, borderRadius: 3 }} />
            <Text style={{ color: C.dim, fontSize: 8, marginTop: 3 }}>{d.label}</Text>
          </View>
        ))}
      </View>
    );
  };

  const KPICard = ({ label, value, sub, icon, color }: any) => (
    <View style={{ flex: 1, minWidth: isMobile ? '45%' : 160, backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((color || C.primary), '15'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon} size={16} color={color || C.primary} />
        </View>
        <Text style={{ color: C.dim, fontSize: 11, fontWeight: '600', flex: 1 }}>{label}</Text>
      </View>
      <Text style={{ color: C.text, fontSize: 22, fontWeight: '800' }}>{value}</Text>
      {sub && <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{sub}</Text>}
    </View>
  );

  const tabs = [
    { key: 'overview', label: tx('aiFeatureDashboard.tabs.overview', 'Overview'), icon: 'grid-outline' },
    { key: 'features', label: tx('aiFeatureDashboard.tabs.features', 'Features'), icon: 'flash-outline' },
    { key: 'users', label: tx('aiFeatureDashboard.tabs.powerUsers', 'Power Users'), icon: 'people-outline' },
    { key: 'insights', label: tx('aiFeatureDashboard.tabs.aiInsights', 'AI Insights'), icon: 'sparkles-outline' },
    { key: 'alerts', label: tx('aiFeatureDashboard.tabs.alerts', 'Alerts'), icon: 'notifications-outline', badge: activeAlertCount },
  ];

  return (
    <AdminRouteGate returnTo="/ai-feature-dashboard">
    <AppShell>
      <FlatList
        data={[{ id: 'ai-dashboard-content' }]}
        keyExtractor={(item) => item.id}
        renderItem={() => (
          <>
        {/* Header */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <View>
            <Text data-testid="ai-dashboard-title" testID="ai-dashboard-title" style={{ color: C.text, fontSize: 24, fontWeight: '800' }}>{tx('aiFeatureDashboard.header.title', 'AI Feature Dashboard')}</Text>
            <Text style={{ color: C.muted, fontSize: 13 }}>{tx('aiFeatureDashboard.header.subtitleWithCount', 'Analytics across all {count} AI copilots').replace('{count}', String(overview.features_count || 7))}</Text>
          </View>
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20 }}>
            <Text style={{ color: C.successText, fontSize: 11, fontWeight: '700' }}>{tx('aiFeatureDashboard.header.live', 'LIVE')}</Text>
          </View>
        </View>

        {/* Tabs */}
        <View data-testid="ai-dashboard-tabs" testID="ai-dashboard-tabs" style={{ flexDirection: 'row', gap: 6, marginBottom: 20, flexWrap: 'wrap' }}>
          {tabs.map(t => (
            <TouchableOpacity key={t.key} data-testid={`tab-${t.key}`} testID={`tab-${t.key}`} onPress={() => setTab(t.key as any)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
                backgroundColor: tab === t.key ? C.primary : C.cardAlt, borderWidth: 1, borderColor: tab === t.key ? C.primary : C.border }}>
              <Ionicons name={t.icon as any} size={14} color={tab === t.key ? C.primaryText : C.muted} />
              <Text style={{ color: tab === t.key ? C.primaryText : C.muted, fontSize: 12, fontWeight: '600' }}>{t.label}</Text>
              {t.badge ? (
                <View style={{ backgroundColor: C.error, borderRadius: 8, minWidth: 16, height: 16, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4, marginLeft: 2 }}>
                  <Text style={{ color: colors.primaryText, fontSize: 9, fontWeight: '800' }}>{t.badge > 99 ? '99+' : t.badge}</Text>
                </View>
              ) : null}
            </TouchableOpacity>
          ))}
        </View>

        {/* OVERVIEW TAB */}
        {tab === 'overview' && (
          <View style={{ gap: 16 }}>
            {/* KPI Row */}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              <KPICard label={tx('aiFeatureDashboard.overview.kpi.requests7d', 'Requests (7d)')} value={usageOverview.total_requests_7d || overview.total_usage_7d || 0} sub={tx('aiFeatureDashboard.overview.kpi.apiCallsThisWeek', 'API calls this week')} icon="analytics-outline" color={C.primary} />
              <KPICard label={tx('aiFeatureDashboard.overview.kpi.activeUsers7d', 'Active Users (7d)')} value={usageOverview.unique_users_7d || overview.active_ai_users_7d || 0} sub={tx('aiFeatureDashboard.overview.kpi.ofTotalWithCount', 'of {count} total').replace('{count}', String(overview.total_users || 0))} icon="people-outline" color={C.successText} />
              <KPICard label={tx('aiFeatureDashboard.overview.kpi.adoptionRate', 'Adoption Rate')} value={`${overview.adoption_rate || 0}%`} sub={tx('aiFeatureDashboard.overview.kpi.usersUsingAi', 'Users using AI features')} icon="trending-up-outline" color={C.purpleText} />
              <KPICard label={tx('aiFeatureDashboard.overview.kpi.multiFeatureUsers', 'Multi-Feature Users')} value={overview.multi_feature_users || 0} sub={tx('aiFeatureDashboard.overview.kpi.usingTwoPlus', 'Using 2+ AI features')} icon="layers-outline" color={C.cyan} />
            </View>

            {/* Usage Trend */}
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{tx('aiFeatureDashboard.overview.dailyTrend14d', 'Daily Usage Trend (14d)')}</Text>
              {dailyTrend.length > 0 ? (
                <BarChart data={dailyTrend.map((d: any) => ({ label: d.date?.slice(5) || '', value: d.requests, color: C.primary }))} />
              ) : (
                <Text style={{ color: C.dim, fontSize: 12 }}>{tx('aiFeatureDashboard.overview.noTrendData', 'No trend data yet')}</Text>
              )}
            </View>

            {/* Tier Distribution */}
            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12 }}>
              <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{tx('aiFeatureDashboard.overview.userDistributionByTier', 'User Distribution by Tier')}</Text>
                {Object.entries(tierDist).map(([tier, count]: [string, any]) => {
                  const total = Object.values(tierDist).reduce((a: number, b: any) => a + b, 0) as number;
                  const pct = total ? Math.round((count / total) * 100) : 0;
                  const tierColors: Record<string, string> = { free: C.dim, basic: C.primary, premium: C.purple };
                  return (
                    <View key={tier} style={{ marginBottom: 10 }}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '600', textTransform: 'capitalize' }}>{tier}</Text>
                        <Text style={{ color: C.muted, fontSize: 12 }}>{count} ({pct}%)</Text>
                      </View>
                      <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3 }}>
                        <View style={{ height: 6, width: `${pct}%`, backgroundColor: tierColors[tier] || C.primary, borderRadius: 3 }} />
                      </View>
                    </View>
                  );
                })}
              </View>

              <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{tx('aiFeatureDashboard.overview.avgUsageByTier', 'Avg Usage per User by Tier')}</Text>
                {Object.entries(tierUsage).map(([tier, data]: [string, any]) => (
                  <View key={tier} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '40') }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '600', textTransform: 'capitalize' }}>{tier}</Text>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{tx('aiFeatureDashboard.overview.reqPerUserWithValue', '{value} req/user').replace('{value}', String(data.avg_per_user))}</Text>
                      <Text style={{ color: C.dim, fontSize: 10 }}>{tx('aiFeatureDashboard.overview.totalFromUsersWithValues', '{total} total from {users} users').replace('{total}', String(data.total_requests)).replace('{users}', String(data.user_count))}</Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>

            {/* Feature Correlations */}
            {correlations.length > 0 && (
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{tx('aiFeatureDashboard.overview.featureCombinations', 'Feature Combinations')}</Text>
                <Text style={{ color: C.dim, fontSize: 11, marginBottom: 10 }}>{tx('aiFeatureDashboard.overview.featureCombinationsSubtitle', 'Most popular feature pairs used together')}</Text>
                {correlations.map((c: any, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '30') }}>
                    <Text style={{ color: C.text, fontSize: 12 }}>{c.pair}</Text>
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 }}>
                      <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700' }}>{tx('aiFeatureDashboard.overview.usersWithCount', '{count} users').replace('{count}', String(c.users))}</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* FEATURES TAB */}
        {tab === 'features' && (
          <View style={{ gap: 12 }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>{tx('aiFeatureDashboard.features.title', 'Feature Leaderboard')}</Text>
            <Text style={{ color: C.dim, fontSize: 12, marginBottom: 4 }}>{tx('aiFeatureDashboard.features.subtitle', 'Ranked by engagement score (weighted: usage + unique users + items + completion)')}</Text>

            {features.length === 0 ? (
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 24, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
                <Ionicons name="analytics-outline" size={32} color={C.dim} />
                <Text style={{ color: C.muted, fontSize: 13, marginTop: 8 }}>{tx('aiFeatureDashboard.features.empty', 'No feature usage data yet. Usage data accumulates as users interact with AI features.')}</Text>
              </View>
            ) : (
              <FlatList
                data={features}
                keyExtractor={(item: any, index) => String(item.feature_id || `feature-${index}`)}
                renderItem={({ item: f, index: i }: { item: any; index: number }) => (
                  <View data-testid={`feature-card-${f.feature_id}`} testID={`feature-card-${f.feature_id}`}
                    style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, borderLeftWidth: 4, borderLeftColor: f.color, marginBottom: 12 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                        <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(f.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                          <Text style={{ color: f.color, fontSize: 14, fontWeight: '800' }}>#{i + 1}</Text>
                        </View>
                        <View>
                          <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{f.name}</Text>
                          <Text style={{ color: C.dim, fontSize: 10 }}>{f.feature_id}</Text>
                        </View>
                      </View>
                      <View style={{ backgroundColor: f.engagement_score > 60 ? (globalThis as any).__alphaColor(C.success, '15') : f.engagement_score > 30 ? C.warn + '15' : C.error + '15', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 }}>
                        <Text style={{ color: f.engagement_score > 60 ? C.success : f.engagement_score > 30 ? C.warn : C.error, fontSize: 12, fontWeight: '800' }}>
                          {f.engagement_score}/100
                        </Text>
                      </View>
                    </View>

                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
                      {[
                        { label: tx('aiFeatureDashboard.features.metrics.today', 'Today'), value: f.usage_today },
                        { label: tx('aiFeatureDashboard.features.metrics.7d', '7d'), value: f.usage_7d },
                        { label: tx('aiFeatureDashboard.features.metrics.30d', '30d'), value: f.usage_30d },
                        { label: tx('aiFeatureDashboard.features.metrics.users7d', 'Users (7d)'), value: f.unique_users_7d },
                        { label: tx('aiFeatureDashboard.features.metrics.items', 'Items'), value: f.items_total },
                        { label: tx('aiFeatureDashboard.features.metrics.completion', 'Completion'), value: `${f.completion_rate}%` },
                      ].map(m => (
                        <View key={m.label} style={{ minWidth: 60 }}>
                          <Text style={{ color: C.dim, fontSize: 9, fontWeight: '600' }}>{m.label}</Text>
                          <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{m.value}</Text>
                        </View>
                      ))}
                    </View>

                    {f.daily_trend?.length > 0 && (
                      <View style={{ marginTop: 8 }}>
                        <Sparkline data={f.daily_trend.map((d: any) => d.count)} color={f.color} />
                      </View>
                    )}
                  </View>
                )}
                getItemLayout={(_, index) => ({ length: 188, offset: 188 * index, index })}
                initialNumToRender={6}
                maxToRenderPerBatch={6}
                windowSize={5}
                removeClippedSubviews={Platform.OS !== 'web'}
                scrollEnabled={false}
                showsVerticalScrollIndicator={false}
                data-testid="ai-dashboard-features-virtual-list"
                testID="ai-dashboard-features-virtual-list"
              />
            )}
          </View>
        )}

        {/* POWER USERS TAB */}
        {tab === 'users' && (
          <View style={{ gap: 12 }}>
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>{tx('aiFeatureDashboard.users.title', 'Power Users (Top 10)')}</Text>
            <Text style={{ color: C.dim, fontSize: 12, marginBottom: 4 }}>{tx('aiFeatureDashboard.users.subtitle', 'Highest AI feature usage in the last 7 days')}</Text>

            {powerUsers.length === 0 ? (
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 24, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
                <Ionicons name="people-outline" size={32} color={C.dim} />
                <Text style={{ color: C.muted, fontSize: 13, marginTop: 8 }}>{tx('aiFeatureDashboard.users.empty', 'No power user data yet')}</Text>
              </View>
            ) : (
              <FlatList
                data={powerUsers}
                keyExtractor={(item: any, index) => String(item.user_id || `power-user-${index}`)}
                renderItem={({ item: u, index: i }: { item: any; index: number }) => (
                  <View data-testid={`power-user-${i}`} testID={`power-user-${i}`}
                    style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: i < 3 ? (globalThis as any).__alphaColor(C.primary, '15') : C.cardAlt, alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ color: i < 3 ? C.primary : C.muted, fontSize: 14, fontWeight: '800' }}>#{i + 1}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{u.name || tx('aiFeatureDashboard.users.userFallback', 'User')}</Text>
                      <Text style={{ color: C.dim, fontSize: 11 }}>{u.email}</Text>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>{u.total_usage}</Text>
                      <Text style={{ color: C.dim, fontSize: 10 }}>{tx('aiFeatureDashboard.users.requests', 'requests')}</Text>
                    </View>
                    <View style={{ alignItems: 'center', minWidth: 50 }}>
                      <Text style={{ color: C.primary, fontSize: 14, fontWeight: '700' }}>{u.features_count}</Text>
                      <Text style={{ color: C.dim, fontSize: 9 }}>{tx('aiFeatureDashboard.users.features', 'features')}</Text>
                    </View>
                    <View style={{ backgroundColor: u.plan === 'premium' ? (globalThis as any).__alphaColor(C.purple, '15') : u.plan === 'basic' ? C.primary + '15' : C.cardAlt, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 }}>
                      <Text style={{ color: u.plan === 'premium' ? C.purple : u.plan === 'basic' ? C.primary : C.dim, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{u.plan}</Text>
                    </View>
                  </View>
                )}
                getItemLayout={(_, index) => ({ length: 92, offset: 92 * index, index })}
                initialNumToRender={8}
                maxToRenderPerBatch={8}
                windowSize={6}
                removeClippedSubviews={Platform.OS !== 'web'}
                scrollEnabled={false}
                showsVerticalScrollIndicator={false}
                data-testid="ai-dashboard-power-users-virtual-list"
                testID="ai-dashboard-power-users-virtual-list"
              />
            )}
          </View>
        )}

        {/* AI INSIGHTS TAB */}
        {tab === 'insights' && (
          <View style={{ gap: 16 }}>
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: (globalThis as any).__alphaColor(C.purple, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="sparkles" size={18} color={C.purpleText} />
                </View>
                <View>
                  <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>{tx('aiFeatureDashboard.insights.title', 'AI-Generated Insights')}</Text>
                  <Text style={{ color: C.dim, fontSize: 11 }}>{tx('aiFeatureDashboard.insights.subtitle', 'Powered by GPT-4o analysis of your platform data')}</Text>
                </View>
              </View>
              <View data-testid="ai-insights-content" testID="ai-insights-content" style={{ backgroundColor: C.cardAlt, borderRadius: 10, padding: 16 }}>
                {aiInsights ? aiInsights.split('\n').filter(Boolean).map((line: string, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
                    <Text style={{ color: C.primary, fontSize: 12 }}>
                      {line.startsWith('-') || line.startsWith('*') ? '' : ''}
                    </Text>
                    <Text style={{ color: C.text, fontSize: 12, lineHeight: 18, flex: 1 }}>{line.replace(/^[-*]\s*/, '')}</Text>
                  </View>
                )) : (
                  <Text style={{ color: C.muted, fontSize: 12 }}>{tx('aiFeatureDashboard.insights.empty', 'AI insights will appear once enough usage data is collected.')}</Text>
                )}
              </View>
            </View>

            {/* Quick Stats Summary */}
            <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 12 }}>{tx('aiFeatureDashboard.insights.platformHealthSummary', 'Platform Health Summary')}</Text>
              {[
                { label: tx('aiFeatureDashboard.insights.summary.totalUsers', 'Total Users'), value: overview.total_users || 0, icon: 'people', color: C.primary },
                { label: tx('aiFeatureDashboard.insights.summary.activeUsers7d', 'AI Active Users (7d)'), value: overview.active_ai_users_7d || usageOverview.unique_users_7d || 0, icon: 'pulse', color: C.successText },
                { label: tx('aiFeatureDashboard.insights.summary.totalRequests30d', 'Total AI Requests (30d)'), value: usageOverview.total_requests_30d || overview.total_usage_30d || 0, icon: 'server', color: C.purpleText },
                { label: tx('aiFeatureDashboard.insights.summary.limitHits7d', 'Limit Hits (7d)'), value: usageOverview.limit_hits_7d || 0, icon: 'warning', color: C.warn },
                { label: tx('aiFeatureDashboard.insights.summary.featuresActive', 'AI Features Active'), value: overview.features_count || 7, icon: 'flash', color: C.cyan },
              ].map(s => (
                <View key={s.label} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '30') }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name={s.icon as any} size={16} color={s.color} />
                    <Text style={{ color: C.muted, fontSize: 12 }}>{s.label}</Text>
                  </View>
                  <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{s.value}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* ALERTS TAB */}
        {tab === 'alerts' && (
          <View data-testid="alerts-tab" testID="alerts-tab" style={{ gap: 16 }}>
            {/* Header row */}
            <View style={{ flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', gap: 12 }}>
              <View>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>{tx('aiFeatureDashboard.alerts.title', 'Real-Time Alerts')}</Text>
                <Text style={{ color: C.dim, fontSize: 12 }}>{tx('aiFeatureDashboard.alerts.subtitle', 'Anomaly detection for AI feature engagement')}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity data-testid="alerts-check-now-btn" testID="alerts-check-now-btn" onPress={handleCheckNow} disabled={checkingAlerts}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: C.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, opacity: checkingAlerts ? 0.6 : 1 }}>
                  {checkingAlerts ? <ActivityIndicator size="small" color={C.primaryText} /> : <Ionicons name="scan-outline" size={14} color={C.primaryText} />}
                  <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '600' }}>{checkingAlerts ? tx('aiFeatureDashboard.alerts.checking', 'Checking...') : tx('aiFeatureDashboard.alerts.checkNow', 'Check Now')}</Text>
                </TouchableOpacity>
                <TouchableOpacity data-testid="alerts-refresh-btn" testID="alerts-refresh-btn" onPress={refreshAlerts}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: C.cardAlt, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
                  <Ionicons name="refresh-outline" size={14} color={C.muted} />
                </TouchableOpacity>
              </View>
            </View>

            {!!alertsError && (
              <View data-testid="alerts-error-banner" testID="alerts-error-banner" style={{ backgroundColor: C.error + '14', borderWidth: 1, borderColor: C.error + '40', borderRadius: 10, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="warning-outline" size={16} color={C.error} />
                <Text data-testid="alerts-error-text" testID="alerts-error-text" style={{ color: C.error, fontSize: 11, fontWeight: '600', flex: 1 }}>{alertsError}</Text>
                <TouchableOpacity data-testid="alerts-error-retry-btn" testID="alerts-error-retry-btn" onPress={refreshAlerts} style={{ backgroundColor: C.card, borderColor: C.error + '40', borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }}>
                  <Text style={{ color: C.error, fontSize: 11, fontWeight: '700' }}>{tx('common.retry', 'Retry')}</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Filter pills */}
            <View style={{ flexDirection: 'row', gap: 6 }}>
              {(['all', 'active', 'acknowledged'] as const).map(f => (
                <TouchableOpacity key={f} data-testid={`alert-filter-${f}`} testID={`alert-filter-${f}`} onPress={() => setAlertFilter(f)}
                  style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, backgroundColor: alertFilter === f ? (globalThis as any).__alphaColor(C.primary, '15') : C.cardAlt, borderWidth: 1, borderColor: alertFilter === f ? C.primary : C.border }}>
                  <Text style={{ color: alertFilter === f ? C.primary : C.muted, fontSize: 11, fontWeight: '600', textTransform: 'capitalize' }}>
                    {f}{f === 'active' ? ` (${activeAlertCount})` : ''}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Alert config card */}
            {alertConfig && (
              <View data-testid="alert-config-card" testID="alert-config-card" style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Ionicons name="settings-outline" size={16} color={C.purpleText} />
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{tx('aiFeatureDashboard.alerts.thresholds', 'Alert Thresholds')}</Text>
                  <View style={{ backgroundColor: alertConfig.enabled ? (globalThis as any).__alphaColor(C.success, '15') : C.error + '15', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8, marginLeft: 'auto' }}>
                    <Text style={{ color: alertConfig.enabled ? C.success : C.error, fontSize: 10, fontWeight: '700' }}>{alertConfig.enabled ? tx('aiFeatureDashboard.alerts.enabled', 'ENABLED') : tx('aiFeatureDashboard.alerts.disabled', 'DISABLED')}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
                  {[
                    { label: tx('aiFeatureDashboard.alerts.metrics.engagementDrop', 'Engagement Drop'), value: `${alertConfig.engagement_drop_pct}%`, icon: 'trending-down-outline', color: C.error },
                    { label: tx('aiFeatureDashboard.alerts.metrics.spikeMultiplier', 'Spike Multiplier'), value: `${alertConfig.usage_spike_multiplier}x`, icon: 'trending-up-outline', color: C.warn },
                    { label: tx('aiFeatureDashboard.alerts.metrics.checkWindow', 'Check Window'), value: `${alertConfig.check_window_hours}h`, icon: 'time-outline', color: C.primary },
                    { label: tx('aiFeatureDashboard.alerts.metrics.comparison', 'Comparison'), value: `${alertConfig.comparison_window_days}d`, icon: 'calendar-outline', color: C.cyan },
                  ].map(c => (
                    <View key={c.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minWidth: isMobile ? '45%' : 130 }}>
                      <Ionicons name={c.icon as any} size={13} color={c.color} />
                      <View>
                        <Text style={{ color: C.dim, fontSize: 9, fontWeight: '600' }}>{c.label}</Text>
                        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{c.value}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              </View>
            )}

            {/* Alert list */}
            {(!alertsData?.alerts || alertsData.alerts.length === 0) ? (
              <View data-testid="alerts-empty-state" testID="alerts-empty-state" style={{ backgroundColor: C.card, borderRadius: 14, padding: 32, borderWidth: 1, borderColor: C.border, alignItems: 'center' }}>
                <Ionicons name="checkmark-circle-outline" size={36} color={C.successText} />
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginTop: 10 }}>{tx('aiFeatureDashboard.alerts.allClear', 'All Clear')}</Text>
                <Text style={{ color: C.muted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{tx('aiFeatureDashboard.alerts.empty', 'No alerts detected. The system monitors engagement drops and usage spikes across all AI features.')}</Text>
              </View>
            ) : (
              <FlatList
                data={alertsData.alerts}
                keyExtractor={(item: any, index) => String(item.alert_id || `alert-${index}`)}
                renderItem={({ item: alert }: { item: any }) => {
                const sevColors: Record<string, { bg: string; text: string; icon: string }> = {
                  critical: { bg: C.error + '15', text: C.error, icon: 'alert-circle' },
                  warning: { bg: C.warn + '15', text: C.warn, icon: 'warning' },
                  info: { bg: C.primary + '15', text: C.primary, icon: 'information-circle' },
                };
                const sev = sevColors[alert.severity] || sevColors.info;
                const typeLabels: Record<string, string> = {
                  engagement_drop: tx('aiFeatureDashboard.alerts.types.engagementDrop', 'Engagement Drop'),
                  usage_spike: tx('aiFeatureDashboard.alerts.types.usageSpike', 'Usage Spike'),
                  platform_spike: tx('aiFeatureDashboard.alerts.types.platformSpike', 'Platform Spike'),
                };
                const timeAgo = alert.created_at ? getTimeAgo(alert.created_at) : '';

                  return (
                  <View data-testid={`alert-item-${alert.alert_id}`} testID={`alert-item-${alert.alert_id}`}
                    style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(alert.acknowledged ? C.border : sev.text, '40'),
                      borderLeftWidth: 4, borderLeftColor: alert.acknowledged ? C.dim : sev.text, opacity: alert.acknowledged ? 0.7 : 1, marginBottom: 12 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
                      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: sev.bg, alignItems: 'center', justifyContent: 'center', marginTop: 2 }}>
                        <Ionicons name={sev.icon as any} size={16} color={sev.text} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
                          <View style={{ backgroundColor: sev.bg, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                            <Text style={{ color: sev.text, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>{alert.severity}</Text>
                          </View>
                          <View style={{ backgroundColor: C.cardAlt, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '600' }}>{typeLabels[alert.type] || alert.type}</Text>
                          </View>
                          {alert.acknowledged && (
                            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                              <Text style={{ color: C.successText, fontSize: 9, fontWeight: '700' }}>{tx('aiFeatureDashboard.alerts.acknowledged', 'ACKNOWLEDGED')}</Text>
                            </View>
                          )}
                          <Text style={{ color: C.dim, fontSize: 10, marginLeft: 'auto' }}>{timeAgo}</Text>
                        </View>
                        <Text style={{ color: C.text, fontSize: 13, fontWeight: '600', marginBottom: 3 }}>{alert.message}</Text>
                        <Text style={{ color: C.dim, fontSize: 11 }}>{alert.detail}</Text>
                        {alert.feature_name && (
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 6 }}>
                            <Ionicons name="flash-outline" size={11} color={C.muted} />
                            <Text style={{ color: C.muted, fontSize: 10 }}>{alert.feature_name}</Text>
                          </View>
                        )}
                      </View>
                      {!alert.acknowledged && (
                        <TouchableOpacity data-testid={`acknowledge-btn-${alert.alert_id}`} testID={`acknowledge-btn-${alert.alert_id}`} onPress={() => handleAcknowledge(alert.alert_id)}
                          style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                          <Ionicons name="checkmark" size={14} color={C.successText} />
                          <Text style={{ color: C.successText, fontSize: 10, fontWeight: '700' }}>{tx('aiFeatureDashboard.alerts.ack', 'Ack')}</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                  </View>
                  );
                }}
                getItemLayout={(_, index) => ({ length: 176, offset: 176 * index, index })}
                initialNumToRender={8}
                maxToRenderPerBatch={8}
                windowSize={6}
                removeClippedSubviews={Platform.OS !== 'web'}
                scrollEnabled={false}
                showsVerticalScrollIndicator={false}
                data-testid="ai-dashboard-alerts-virtual-list"
                testID="ai-dashboard-alerts-virtual-list"
              />
            )}
          </View>
        )}

        <View style={{ height: 40 }} />
          </>
        )}
        style={{ flex: 1, backgroundColor: C.bg }}
        contentContainerStyle={{ padding: isMobile ? 12 : 28, maxWidth: 1240, alignSelf: 'center', width: '100%' }}
        showsVerticalScrollIndicator={false}
        removeClippedSubviews={false}
      />
    </AppShell>
    </AdminRouteGate>
  );
}
