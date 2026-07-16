import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import AutoFixBanner from './AutoFixBanner';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';

/* ─── Mini Chart ─── */
function SparkLine({ data, color, height = 60 }: { data: number[]; color: string; height?: number }) {
  if (!data.length) return null;
  const max = Math.max(...data, 1);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _w = 100 / data.length;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 1 }}>
      {data.map((v, i) => (
        <View key={i} style={{
          flex: 1, backgroundColor: (globalThis as any).__alphaColor(color, '30'), borderRadius: 2,
          height: Math.max((v / max) * height, 2),
          ...(i === data.length - 1 ? { backgroundColor: color } : {}),
        }} />
      ))}
    </View>
  );
}

/* ─── Bar Chart Row ─── */
function BarRow({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const T = useExecTheme();
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 10 }}>
      <Text style={{ color: T.textSec, fontSize: 13, fontWeight: '500', minWidth: 100, textTransform: 'capitalize' }}>{label}</Text>
      <View style={{ flex: 1, height: 8, backgroundColor: T.card, borderRadius: 4, overflow: 'hidden' }}>
        <View style={{ height: '100%', width: `${Math.max(pct, 3)}%`, backgroundColor: color, borderRadius: 4 }} />
      </View>
      <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', minWidth: 30, textAlign: 'right' }}>{value}</Text>
      <Text style={{ color: T.textMuted, fontSize: 11, minWidth: 40 }}>{pct.toFixed(0)}%</Text>
    </View>
  );
}

/* ─── Funnel Step ─── */
function FunnelStep({ label, value, total, icon, color }: any) {
  const T = useExecTheme();
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <View style={{ marginBottom: 14 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name={icon} size={14} color={color} />
          <Text style={{ color: T.textSec, fontSize: 13, fontWeight: '600' }}>{label}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4 }}>
          <Text style={{ color: T.text, fontSize: 20, fontWeight: '800' }}>{value}</Text>
          <Text style={{ color: T.textMuted, fontSize: 11 }}>({pct.toFixed(0)}%)</Text>
        </View>
      </View>
      <View style={{ height: 8, backgroundColor: T.card, borderRadius: 4, overflow: 'hidden', borderWidth: 1, borderColor: T.border }}>
        <View style={{ height: '100%', width: `${Math.max(pct, 2)}%`, backgroundColor: color, borderRadius: 4 }} />
      </View>
    </View>
  );
}

/* ─── KPI Card ─── */
function KPI({ label, value, sub, icon, color, trend }: any) {
  const T = useExecTheme();
  return (
    <View style={{ flex: 1, minWidth: 180, backgroundColor: T.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: color }}
      data-testid={`admin-ref-kpi-${label.replace(/\s+/g, '-').toLowerCase()}`} testID={`admin-ref-kpi-${label.replace(/\s+/g, '-').toLowerCase()}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Ionicons name={icon} size={16} color={color} />
        <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.3, flex: 1 }}>{label}</Text>
        {trend && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
            <Ionicons name={trend > 0 ? 'trending-up' : 'trending-down'} size={12} color={trend > 0 ? T.success : T.error} />
            <Text style={{ color: trend > 0 ? T.success : T.error, fontSize: 10, fontWeight: '700' }}>{Math.abs(trend)}%</Text>
          </View>
        )}
      </View>
      <Text style={{ color: T.text, fontSize: 28, fontWeight: '800', letterSpacing: -0.5 }}>{value}</Text>
      {sub && <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{sub}</Text>}
    </View>
  );
}

/* ═══════════════════════════════════════
   MAIN PANEL
   ═══════════════════════════════════════ */
const CHANNEL_META_MAP: Record<string, string> = {
  twitter: 'Twitter', linkedin: 'LinkedIn', whatsapp: 'WhatsApp',
  email: 'Email', sms: 'SMS', qr: 'QR', direct: 'Direct',
};

export default function ReferralAnalyticsPanel() {
  useExecStyles();
  const T = useExecTheme();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const headerTitle = t('referralAnalytics.header.title');
  const headerSubtitle = t('referralAnalytics.header.subtitle');
  const [seeding, setSeeding] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [sendingTest, setSendingTest] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [showCreateChallenge, setShowCreateChallenge] = useState(false);
  const [newChallenge, setNewChallenge] = useState({ title: '', description: '', goal_count: '3', reward_value: '10', days: '7' });
  const [resolvingAlert, setResolvingAlert] = useState<string | null>(null);
  const [creatingChallenge, setCreatingChallenge] = useState(false);
  const [challengePage, setChallengePage] = useState(1);
  const [challengePageSize] = useState(8);
  const [fraudPage, setFraudPage] = useState(1);
  const [fraudPageSize] = useState(10);
  const [integrityPage, setIntegrityPage] = useState(1);
  const [integrityPageSize] = useState(10);
  const [runningIntegrityEval, setRunningIntegrityEval] = useState(false);
  const [applyingRecommendation, setApplyingRecommendation] = useState(false);
  const [resolvingIntegrityAlert, setResolvingIntegrityAlert] = useState<string | null>(null);
  const [applyingIntegritySuggestion, setApplyingIntegritySuggestion] = useState<string | null>(null);

  const { data: analytics, loading, refetch: refetchAnalytics } = useLiveQuery('/referrals/admin/analytics', { entity: 'referrals', pollInterval: 60000, deps: [refreshKey] });
  const { data: topReferrersData, refetch: refetchTop } = useLiveQuery('/referrals/admin/top-referrers', { entity: 'referrals', pollInterval: 60000 });
  const { data: emailStats } = useLiveQuery('/referrals/admin/email-digest-stats', { entity: 'referrals', pollInterval: 60000 });
  const { data: creditStats } = useLiveQuery('/referrals/admin/credit-analytics', { entity: 'referrals', pollInterval: 60000 });
  const { data: milestoneStats } = useLiveQuery('/referrals/admin/milestone-analytics', { entity: 'referrals', pollInterval: 60000 });
  const { data: channelStats } = useLiveQuery('/referrals/admin/channel-analytics', { entity: 'referrals', pollInterval: 60000 });
  const { data: adminChallenges, refetch: refetchChallenges } = useLiveQuery(
    `/referrals/admin/challenges?page=${challengePage}&page_size=${challengePageSize}`,
    { entity: 'referrals', pollInterval: 60000 },
  );
  const { data: fraudData, refetch: refetchFraud } = useLiveQuery(
    `/referrals/admin/fraud-alerts?page=${fraudPage}&page_size=${fraudPageSize}`,
    { entity: 'referrals', pollInterval: 120000 },
  );
  const { data: opsHealth } = useLiveQuery('/referrals/admin/ops-health', { entity: 'referrals', pollInterval: 60000 });
  const { data: enhancedData } = useLiveQuery('/referrals/admin/enhanced-analytics', { entity: 'referrals', pollInterval: 60000 });
  const { data: integrityAlerts, refetch: refetchIntegrityAlerts } = useLiveQuery(
    `/referrals/admin/integrity-alerts?status=open&page=${integrityPage}&page_size=${integrityPageSize}`,
    { entity: 'referrals', pollInterval: 60000 },
  );
  const { data: integrityTrends, refetch: refetchIntegrityTrends } = useLiveQuery(
    '/referrals/admin/integrity-trends?days=90',
    { entity: 'referrals', pollInterval: 120000 },
  );
  const { data: integrityIncidentTimeline, refetch: refetchIntegrityIncidentTimeline } = useLiveQuery(
    '/referrals/admin/integrity-incident-timeline?limit=8',
    { entity: 'referrals', pollInterval: 120000 },
  );
  const { data: policyRecommendation, refetch: refetchPolicyRecommendation } = useLiveQuery(
    '/referrals/admin/fraud-policy/recommendation',
    { entity: 'referrals', pollInterval: 60000 },
  );

  const topReferrers = topReferrersData?.referrers || [];
  const challengeRows = adminChallenges?.data || adminChallenges?.challenges || [];
  const challengeTotalCount = Number(adminChallenges?.total_count || challengeRows.length || 0);
  const challengeTotalPages = Math.max(1, Math.ceil(challengeTotalCount / challengePageSize));
  const fraudRows = fraudData?.data || fraudData?.alerts || [];
  const fraudTotalCount = Number(fraudData?.total_count || fraudRows.length || 0);
  const fraudTotalPages = Math.max(1, Math.ceil(fraudTotalCount / fraudPageSize));
  const openFraudAlerts = fraudRows.filter((a: any) => a.status === 'open');
  const resolvedFraudAlerts = fraudRows.filter((a: any) => a.status === 'resolved');
  const integrityRows = integrityAlerts?.data || integrityAlerts?.alerts || [];
  const integrityTotalCount = Number(integrityAlerts?.total_count || integrityRows.length || 0);
  const integrityTotalPages = Math.max(1, Math.ceil(integrityTotalCount / integrityPageSize));

  const trendWindow7 = integrityTrends?.windows?.['7'] || null;
  const trendWindow30 = integrityTrends?.windows?.['30'] || null;
  const trendWindow90 = integrityTrends?.windows?.['90'] || null;
  const trendPoints = integrityTrends?.points || [];
  const integrityIncidentRows = integrityIncidentTimeline?.timeline || [];
  const qualitySeries = trendPoints.map((p: any) => Number(p.conversion_quality || 0));
  const duplicateSeries = trendPoints.map((p: any) => Number(p.duplicate_prevention_breaches || 0));

  useEffect(() => {
    if (challengePage > challengeTotalPages) {
      setChallengePage(challengeTotalPages);
    }
  }, [challengePage, challengeTotalPages]);

  useEffect(() => {
    if (fraudPage > fraudTotalPages) {
      setFraudPage(fraudTotalPages);
    }
  }, [fraudPage, fraudTotalPages]);

  useEffect(() => {
    if (integrityPage > integrityTotalPages) {
      setIntegrityPage(integrityTotalPages);
    }
  }, [integrityPage, integrityTotalPages]);

  const loadData = useCallback(async () => {
    await Promise.all([
      refetchAnalytics(),
      refetchTop(),
      refetchChallenges(),
      refetchFraud(),
      refetchIntegrityAlerts(),
      refetchIntegrityTrends(),
      refetchIntegrityIncidentTimeline(),
      refetchPolicyRecommendation(),
    ]);
  }, [refetchAnalytics, refetchTop, refetchChallenges, refetchFraud, refetchIntegrityAlerts, refetchIntegrityTrends, refetchIntegrityIncidentTimeline, refetchPolicyRecommendation]);

  const evaluateIntegrityAlerts = async () => {
    setRunningIntegrityEval(true);
    try {
      await api.post('/referrals/admin/integrity-alerts/evaluate');
      await loadData();
    } catch (e) { console.error(e); }
    finally { setRunningIntegrityEval(false); }
  };

  const applyRecommendedProfile = async () => {
    setApplyingRecommendation(true);
    try {
      await api.post('/referrals/admin/fraud-policy/apply-recommendation');
      await loadData();
    } catch (e) { console.error(e); }
    finally { setApplyingRecommendation(false); }
  };

  const resolveIntegrityAlert = async (alertId: string) => {
    setResolvingIntegrityAlert(alertId);
    try {
      await api.post(`/referrals/admin/integrity-alerts/${alertId}/resolve`, { resolution: 'acknowledged' });
      await loadData();
    } catch (e) { console.error(e); }
    finally { setResolvingIntegrityAlert(null); }
  };

  const applyIntegritySuggestion = async (alertId: string) => {
    setApplyingIntegritySuggestion(alertId);
    try {
      await api.post(`/referrals/admin/integrity-alerts/${alertId}/apply-suggestion`);
      await loadData();
    } catch (e) { console.error(e); }
    finally { setApplyingIntegritySuggestion(null); }
  };

  const seedDemo = async () => {
    setSeeding(true);
    try {
      await api.post('/referrals/admin/seed-demo');
      setRefreshKey(k => k + 1);
    } catch (e) { console.error(e); }
    finally { setSeeding(false); }
  };

  const handleCreateChallenge = async () => {
    setCreatingChallenge(true);
    try {
      const now = new Date();
      const end = new Date(now.getTime() + parseInt(newChallenge.days) * 86400000);
      await api.post('/referrals/admin/challenges', {
        title: newChallenge.title,
        description: newChallenge.description,
        goal_count: parseInt(newChallenge.goal_count),
        reward_type: 'credit',
        reward_value: parseFloat(newChallenge.reward_value),
        start_date: now.toISOString(),
        end_date: end.toISOString(),
      });
      setShowCreateChallenge(false);
      setNewChallenge({ title: '', description: '', goal_count: '3', reward_value: '10', days: '7' });
      loadData();
    } catch (e) { console.error(e); }
    finally { setCreatingChallenge(false); }
  };

  const toggleChallenge = async (challengeId: string, isActive: boolean) => {
    try {
      await api.put(`/referrals/admin/challenges/${challengeId}`, { is_active: !isActive });
      loadData();
    } catch (e) { console.error(e); }
  };

  const resolveAlert = async (alertId: string, resolution: string) => {
    setResolvingAlert(alertId);
    try {
      await api.post(`/referrals/admin/fraud-alerts/${alertId}/resolve`, { resolution });
      loadData();
    } catch (e) { console.error(e); }
    finally { setResolvingAlert(null); }
  };

  const blockReferrer = async (alertId: string) => {
    setResolvingAlert(alertId);
    try {
      await api.post(`/referrals/admin/fraud-alerts/${alertId}/block`);
      loadData();
    } catch (e) { console.error(e); }
    finally { setResolvingAlert(null); }
  };

  const sendTestDigest = async () => {
    setSendingTest(true);
    setTestResult(null);
    try {
      const res = await api.post('/referrals/admin/send-test-digest');
      setTestResult(res.data.message || tx('referralAnalytics.email.sent', 'Sent!'));
      setRefreshKey(k => k + 1);
    } catch (e: any) {
      setTestResult(e?.response?.data?.detail || tx('referralAnalytics.email.failed', 'Failed to send'));
    }
    finally { setSendingTest(false); }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center', backgroundColor: colors.bg }}>
      <AutoFixBanner domain="referrals" />
      <ActivityIndicator size="large" color={T.primary} />
    </View>
  );

  const a = analytics || {};
  const trend = a.trend || [];
  const signupTrend = trend.map((d: any) => d.signups || 0);
  const clickTrend = trend.map((d: any) => d.clicks || 0);
  const convTrend = trend.map((d: any) => d.conversions || 0);
  const statusDist = a.status_distribution || {};
  const planDist = a.plan_distribution || {};
  const tierDist = a.tier_distribution || {};
  const totalEvents = a.total_events || 0;
  const totalReferrers = a.total_referrers || 0;
  const statusColors: Record<string, string> = { clicked: T.textMuted, signed_up: T.warning, subscribed: T.success, churned: T.error };
  const planColors: Record<string, string> = { free: T.textMuted, basic: T.primary, premium: T.purple };
  const tierColors: Record<string, string> = { starter: T.textMuted, bronze: 'var(--app-primary)', silver: 'var(--app-primary)', gold: 'var(--app-primary)' };
  const hasData = totalEvents > 0 || totalReferrers > 0;

  return (
    <View data-testid="referral-analytics-panel" testID="referral-analytics-panel" style={{ padding: 4, backgroundColor: colors.bg }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: T.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="gift" size={18} color={T.primary} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '800', letterSpacing: -0.3 }}>{headerTitle === 'referralAnalytics.header.title' ? 'Referral Program' : headerTitle}</Text>
            <Text style={{ color: T.textMuted, fontSize: 12 }}>{headerSubtitle === 'referralAnalytics.header.subtitle' ? '30% commission · 15% discount' : headerSubtitle}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {!hasData && (
            <TouchableOpacity onPress={seedDemo} disabled={seeding} data-testid="seed-referral-data-btn" testID="seed-referral-data-btn"
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(T.warning, '20'), paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 }}>
              <Ionicons name="sparkles" size={14} color={T.warningText} />
              <Text style={{ color: T.warningText, fontSize: 12, fontWeight: '700' }}>{seeding ? tx('referralAnalytics.actions.seeding', 'Seeding...') : tx('referralAnalytics.actions.seedDemoData', 'Seed Demo Data')}</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => { setRefreshKey(k => k + 1); }} data-testid="refresh-referral-analytics" testID="refresh-referral-analytics"
            style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="refresh" size={16} color={T.primary} />
          </TouchableOpacity>
        </View>
      </View>

      {/* KPI Row */}
      {!!opsHealth && (
        <View
          style={{
            flexDirection: 'row',
            gap: 10,
            flexWrap: 'wrap',
            marginBottom: 14,
            backgroundColor: T.bgSoft,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: T.border,
            padding: 12,
          }}
          data-testid="referral-ops-health-strip"
          testID="referral-ops-health-strip"
        >
          <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>Ops Health</Text>
          <Text style={{ color: T.text, fontSize: 12 }} data-testid="referral-ops-health-conversion" testID="referral-ops-health-conversion">
            Conversion {Number(opsHealth?.funnel?.conversion_rate || 0).toFixed(1)}%
          </Text>
          <Text style={{ color: opsHealth?.flags?.payouts_enabled ? T.successText : T.error, fontSize: 12 }} data-testid="referral-ops-health-payouts" testID="referral-ops-health-payouts">
            Payouts {opsHealth?.flags?.payouts_enabled ? 'ON' : 'OFF'}
          </Text>
          <Text style={{ color: opsHealth?.flags?.fraud_autoscan_enabled ? T.successText : T.warning, fontSize: 12 }} data-testid="referral-ops-health-fraud" testID="referral-ops-health-fraud">
            Fraud Scan {opsHealth?.flags?.fraud_autoscan_enabled ? 'ON' : 'OFF'}
          </Text>
          <Text style={{ color: T.textMuted, fontSize: 12 }} data-testid="referral-ops-health-duplicates" testID="referral-ops-health-duplicates">
            Duplicate Keys 24h: {Number(opsHealth?.idempotency?.duplicate_credit_dedupe_keys_last_24h || 0)}
          </Text>
        </View>
      )}

      <View
        style={{
          flexDirection: 'column',
          gap: 10,
          marginBottom: 14,
          backgroundColor: T.bgSoft,
          borderRadius: 12,
          borderWidth: 1,
          borderColor: T.border,
          padding: 12,
        }}
        data-testid="referral-integrity-alerts-section"
        testID="referral-integrity-alerts-section"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>Integrity Controls</Text>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={evaluateIntegrityAlerts}
              disabled={runningIntegrityEval}
              style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.card }}
              data-testid="evaluate-integrity-alerts-btn"
              testID="evaluate-integrity-alerts-btn"
            >
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{runningIntegrityEval ? 'Evaluating…' : 'Run Evaluation'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={applyRecommendedProfile}
              disabled={applyingRecommendation}
              style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '40'), backgroundColor: (globalThis as any).__alphaColor(T.success, '15') }}
              data-testid="apply-recommended-fraud-profile-btn"
              testID="apply-recommended-fraud-profile-btn"
            >
              <Text style={{ color: T.successText, fontSize: 11, fontWeight: '700' }}>{applyingRecommendation ? 'Applying…' : 'Apply Recommended Profile'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="integrity-trends-section" testID="integrity-trends-section">
          <View style={{ flex: 1, minWidth: 180, borderRadius: 10, borderWidth: 1, borderColor: T.border, backgroundColor: T.card, padding: 10 }} data-testid="integrity-window-7" testID="integrity-window-7">
            <Text style={{ color: T.textMuted, fontSize: 10 }}>7 Day</Text>
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>{Number(trendWindow7?.avg_conversion_quality || 0).toFixed(1)}%</Text>
          </View>
          <View style={{ flex: 1, minWidth: 180, borderRadius: 10, borderWidth: 1, borderColor: T.border, backgroundColor: T.card, padding: 10 }} data-testid="integrity-window-30" testID="integrity-window-30">
            <Text style={{ color: T.textMuted, fontSize: 10 }}>30 Day</Text>
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>{Number(trendWindow30?.avg_conversion_quality || 0).toFixed(1)}%</Text>
          </View>
          <View style={{ flex: 1, minWidth: 180, borderRadius: 10, borderWidth: 1, borderColor: T.border, backgroundColor: T.card, padding: 10 }} data-testid="integrity-window-90" testID="integrity-window-90">
            <Text style={{ color: T.textMuted, fontSize: 10 }}>90 Day</Text>
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>{Number(trendWindow90?.avg_conversion_quality || 0).toFixed(1)}%</Text>
          </View>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <KPI label={tx('referralAnalytics.kpis.totalReferrers', 'Total Referrers')} value={a.total_referrers || 0} sub={tx('referralAnalytics.kpis.newThisWeek', '{count} new this week').replace('{count}', String(a.recent_7d_signups || 0))} icon="people" color={T.primary} />
        <KPI label={tx('referralAnalytics.kpis.totalClicks', 'Total Clicks')} value={a.total_clicks || 0} sub={tx('referralAnalytics.kpis.conversionRate', '{rate}% conversion').replace('{rate}', String(a.conversion_rate || 0))} icon="hand-left" color={T.cyan} />
        <KPI label={tx('referralAnalytics.kpis.signups', 'Signups')} value={a.total_signups || 0} sub={tx('referralAnalytics.kpis.activeSubs', '{count} active subs').replace('{count}', String(a.active_subscribers || 0))} icon="person-add" color={T.successText} />
        <KPI label={tx('referralAnalytics.kpis.commissionPaid', 'Commission Paid')} value={`$${(a.total_commission_paid || 0).toFixed(0)}`} sub={tx('referralAnalytics.kpis.monthlyRecurring', '{value}/mo recurring').replace('{value}', `$${(a.monthly_recurring_commission || 0).toFixed(2)}`)} icon="cash" color={T.purpleText} />
      </View>

      {/* Charts Row */}
      <View style={{ flexDirection: 'row', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        {/* 30-Day Trend */}
        <View style={{ flex: 2, minWidth: 320, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="referral-trend-chart" testID="referral-trend-chart">
          <Text style={{ color: T.text, fontSize: 15, fontWeight: '700', marginBottom: 4 }}>{tx('referralAnalytics.trend.title', '30-Day Referral Trend')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 16 }}>{tx('referralAnalytics.trend.subtitle', 'Daily signups, clicks, and conversions')}</Text>
          <View style={{ gap: 14 }}>
            <View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.primary }} />
                <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{tx('referralAnalytics.trend.clicks', 'Clicks')}</Text>
              </View>
              <SparkLine data={clickTrend} color={T.primary} height={50} />
            </View>
            <View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.success }} />
                <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{tx('referralAnalytics.trend.signups', 'Signups')}</Text>
              </View>
              <SparkLine data={signupTrend} color={T.successText} height={50} />
            </View>
            <View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.purple }} />
                <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{tx('referralAnalytics.trend.conversions', 'Conversions')}</Text>
              </View>
              <SparkLine data={convTrend} color={T.purpleText} height={50} />
            </View>
          </View>
        </View>

        {/* Conversion Funnel */}
        <View style={{ flex: 1, minWidth: 280, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="referral-funnel" testID="referral-funnel">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="funnel" size={14} color={T.primary} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('referralAnalytics.funnel.title', 'Conversion Funnel')}</Text>
          </View>
          <FunnelStep label={tx('referralAnalytics.funnel.linkClicks', 'Link Clicks')} value={a.total_clicks || 0} total={a.total_clicks || 1} icon="link" color={T.primary} />
          <FunnelStep label={tx('referralAnalytics.funnel.signups', 'Signups')} value={a.total_signups || 0} total={a.total_clicks || 1} icon="person-add" color={T.warningText} />
          <FunnelStep label={tx('referralAnalytics.funnel.subscribed', 'Subscribed')} value={a.active_subscribers || 0} total={a.total_clicks || 1} icon="checkmark-circle" color={T.successText} />
        </View>
      </View>

      {/* ═══ Enhanced Analytics: Detailed Conversion Funnel ═══ */}
      {enhancedData && (
        <View style={{ flexDirection: 'row', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
          {/* Detailed Funnel with Drop-offs */}
          <View style={{ flex: 2, minWidth: 340, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="enhanced-conversion-funnel" testID="enhanced-conversion-funnel">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: T.cyanSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="git-network" size={14} color={T.cyan} />
              </View>
              <View>
                <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>{tx('referralAnalytics.pipeline.title', 'Detailed Conversion Pipeline')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('referralAnalytics.pipeline.subtitle', 'Full journey from click to subscription')}</Text>
              </View>
            </View>

            {/* Pipeline Stages */}
            <View style={{ marginTop: 16 }}>
              {(enhancedData.conversion_funnel?.stages || []).map((s: any, i: number, arr: any[]) => {
                const stageColors = [T.primary, T.warning, T.success];
                const isLast = i === arr.length - 1;
                const dropOff = enhancedData.conversion_funnel?.drop_offs?.[i];
                return (
                  <View key={s.label}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 }}>
                      <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(stageColors[i], '18'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={s.icon} size={18} color={stageColors[i]} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{s.label}</Text>
                        <View style={{ height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden', marginTop: 4 }}>
                          <View style={{ height: '100%', width: `${Math.max(s.rate, 2)}%`, backgroundColor: stageColors[i], borderRadius: 3 }} />
                        </View>
                      </View>
                      <View style={{ alignItems: 'flex-end', minWidth: 70 }}>
                        <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{s.value}</Text>
                        <Text style={{ color: stageColors[i], fontSize: 10, fontWeight: '700' }}>{s.rate}%</Text>
                      </View>
                    </View>
                    {!isLast && dropOff && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingLeft: 52, paddingVertical: 6 }}>
                        <View style={{ width: 1, height: 16, backgroundColor: (globalThis as any).__alphaColor(T.error, '40') }} />
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.errorSoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                          <Ionicons name="arrow-down" size={10} color={T.error} />
                          <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{tx('referralAnalytics.pipeline.dropoff', '{pct}% drop-off').replace('{pct}', String(dropOff.drop_pct))}</Text>
                          <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('referralAnalytics.pipeline.lost', '({count} lost)').replace('{count}', String(dropOff.lost))}</Text>
                        </View>
                      </View>
                    )}
                  </View>
                );
              })}
            </View>

            {/* Time to Convert */}
            {enhancedData.conversion_funnel?.time_to_convert && (
              <View style={{ marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: T.border }}>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.3, marginBottom: 8 }}>{tx('referralAnalytics.pipeline.timeToConvert', 'Time to Convert')}</Text>
                <View style={{ flexDirection: 'row', gap: 10 }}>
                  <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 10, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
                    <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>{enhancedData.conversion_funnel.time_to_convert.avg_hours}h</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('referralAnalytics.pipeline.average', 'Average')}</Text>
                  </View>
                  <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 10, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
                    <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>{enhancedData.conversion_funnel.time_to_convert.median_hours}h</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('referralAnalytics.pipeline.median', 'Median')}</Text>
                  </View>
                  <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 10, padding: 10, alignItems: 'center', borderWidth: 1, borderColor: T.border }}>
                    <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>{enhancedData.conversion_funnel.time_to_convert.sample_size}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('referralAnalytics.pipeline.sample', 'Sample')}</Text>
                  </View>
                </View>
              </View>
            )}
          </View>

          {/* Overall Rates + Plan Breakdown */}
          <View style={{ flex: 1, minWidth: 260, gap: 16 }}>
            {/* Conversion Rates Card */}
            <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="conversion-rates-card" testID="conversion-rates-card">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                <Ionicons name="speedometer" size={14} color={T.successText} />
                <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('referralAnalytics.conversionRates.title', 'Conversion Rates')}</Text>
              </View>
              {[
                { label: tx('referralAnalytics.conversionRates.clickToSignup', 'Click → Signup'), value: enhancedData.conversion_funnel?.rates?.click_to_signup || 0, color: T.primary },
                { label: tx('referralAnalytics.conversionRates.signupToSubscribe', 'Signup → Subscribe'), value: enhancedData.conversion_funnel?.rates?.signup_to_subscription || 0, color: T.warningText },
                { label: tx('referralAnalytics.conversionRates.overall', 'Overall (Click → Sub)'), value: enhancedData.conversion_funnel?.rates?.overall || 0, color: T.successText },
              ].map((r) => (
                <View key={r.label} style={{ marginBottom: 12 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{r.label}</Text>
                    <Text style={{ color: r.color, fontSize: 13, fontWeight: '800' }}>{r.value}%</Text>
                  </View>
                  <View style={{ height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden' }}>
                    <View style={{ height: '100%', width: `${Math.max(r.value, 2)}%`, backgroundColor: r.color, borderRadius: 3 }} />
                  </View>
                </View>
              ))}
            </View>

            {/* Plan Conversion Breakdown */}
            <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="plan-conversion-breakdown" testID="plan-conversion-breakdown">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                <Ionicons name="card" size={14} color={T.purpleText} />
                <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('referralAnalytics.planBreakdown.title', 'Subscriptions by Plan')}</Text>
              </View>
              {Object.entries(enhancedData.conversion_funnel?.plan_conversions || {}).filter(([, v]) => (v as number) > 0).map(([plan, count]) => {
                const pColors: Record<string, string> = { free: T.textMuted, basic: T.primary, premium: T.purple };
                const total = Object.values(enhancedData.conversion_funnel?.plan_conversions || {}).reduce((s: number, v: any) => s + (v as number), 0) as number;
                return (
                  <View key={plan} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10, paddingVertical: 8, paddingHorizontal: 10, borderRadius: 10, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }}>
                    <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((pColors[plan] || T.textMuted), '18'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="card" size={14} color={pColors[plan] || T.textMuted} />
                    </View>
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', flex: 1, textTransform: 'capitalize' }}>{plan}</Text>
                    <Text style={{ color: pColors[plan] || T.text, fontSize: 18, fontWeight: '800' }}>{count as number}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, minWidth: 35 }}>{total > 0 ? Math.round(((count as number) / total) * 100) : 0}%</Text>
                  </View>
                );
              })}
              {Object.values(enhancedData.conversion_funnel?.plan_conversions || {}).every((v: any) => v === 0) && (
                <Text style={{ color: T.textMuted, fontSize: 12, textAlign: 'center', paddingVertical: 12 }}>{tx('referralAnalytics.planBreakdown.empty', 'No subscriptions yet')}</Text>
              )}
            </View>
          </View>
        </View>
      )}

      {/* ═══ Cohort Analysis ═══ */}
      {enhancedData?.cohorts && enhancedData.cohorts.length > 0 && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="cohort-analysis-section" testID="cohort-analysis-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: T.orangeSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="calendar" size={18} color={T.orangeText} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.referralAnalyticsPanel.auto.text.001', 'Cohort Analysis')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.referralAnalyticsPanel.auto.text.002', 'Referral performance grouped by signup month')}</Text>
            </View>
          </View>

          {/* Cohort Table */}
          <View style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, overflow: 'hidden' }}>
            {/* Header */}
            <View style={{ flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 12, backgroundColor: T.card, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <Text style={{ flex: 1.2, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.referralAnalyticsPanel.auto.text.003', 'Month')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.004', 'Signups')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.005', 'Subscribed')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.006', 'Conv %')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.007', 'Churned')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.008', 'Revenue')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.009', 'Top Ch.')}</Text>
            </View>
            {/* Rows */}
            {enhancedData.cohorts.map((c: any, i: number) => {
              const monthLabel = (() => {
                try {
                  const [y, m] = c.month.split('-');
                  return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
                } catch { return c.month; }
              })();
              const chLabel = CHANNEL_META_MAP[c.top_channel] || c.top_channel;
              return (
                <View key={c.month} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 12, paddingHorizontal: 12, borderBottomWidth: i < enhancedData.cohorts.length - 1 ? 1 : 0, borderBottomColor: T.border }}
                  data-testid={`cohort-row-${c.month}`} testID={`cohort-row-${c.month}`}>
                  <View style={{ flex: 1.2 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{monthLabel}</Text>
                  </View>
                  <Text style={{ flex: 1, color: T.textSec, fontSize: 13, fontWeight: '600', textAlign: 'center' }}>{c.total_signups}</Text>
                  <Text style={{ flex: 1, color: T.successText, fontSize: 13, fontWeight: '700', textAlign: 'center' }}>{c.subscribed}</Text>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <View style={{ backgroundColor: c.conversion_rate >= 50 ? T.successSoft : c.conversion_rate >= 25 ? T.warningSoft : T.errorSoft, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                      <Text style={{ color: c.conversion_rate >= 50 ? T.success : c.conversion_rate >= 25 ? T.warning : T.error, fontSize: 11, fontWeight: '700' }}>{c.conversion_rate}%</Text>
                    </View>
                  </View>
                  <Text style={{ flex: 1, color: c.churned > 0 ? T.error : T.textMuted, fontSize: 13, fontWeight: '600', textAlign: 'center' }}>{c.churned}</Text>
                  <Text style={{ flex: 1, color: T.purpleText, fontSize: 13, fontWeight: '700', textAlign: 'right' }}>${c.total_revenue}</Text>
                  <Text style={{ flex: 1, color: T.textSec, fontSize: 10, fontWeight: '600', textAlign: 'right' }}>{chLabel}</Text>
                </View>
              );
            })}
          </View>

          {/* Cohort Visual Bars */}
          <View style={{ marginTop: 16 }}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.3, marginBottom: 10 }}>{tx('admin.referralAnalyticsPanel.auto.text.010', 'Signups vs Conversions by Month')}</Text>
            {enhancedData.cohorts.map((c: any) => {
              const maxSignups = Math.max(...enhancedData.cohorts.map((x: any) => x.total_signups), 1);
              const monthLabel = (() => {
                try {
                  const [y, m] = c.month.split('-');
                  return new Date(parseInt(y), parseInt(m) - 1).toLocaleDateString(undefined, { month: 'short' });
                } catch { return c.month; }
              })();
              return (
                <View key={c.month + '-bar'} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600', minWidth: 35 }}>{monthLabel}</Text>
                  <View style={{ flex: 1, gap: 2 }}>
                    <View style={{ height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden' }}>
                      <View style={{ height: '100%', width: `${Math.max((c.total_signups / maxSignups) * 100, 3)}%`, backgroundColor: T.primary, borderRadius: 3 }} />
                    </View>
                    <View style={{ height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden' }}>
                      <View style={{ height: '100%', width: `${Math.max((c.subscribed / maxSignups) * 100, 2)}%`, backgroundColor: T.success, borderRadius: 3 }} />
                    </View>
                  </View>
                  <Text style={{ color: T.textMuted, fontSize: 9, minWidth: 50, textAlign: 'right' }}>{c.total_signups}/{c.subscribed}</Text>
                </View>
              );
            })}
            <View style={{ flexDirection: 'row', gap: 16, marginTop: 4 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.primary }} />
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.referralAnalyticsPanel.auto.text.011', 'Signups')}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.success }} />
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.referralAnalyticsPanel.auto.text.012', 'Subscribed')}</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {/* ═══ Channel Conversion Funnels ═══ */}
      {enhancedData?.channel_funnels && enhancedData.channel_funnels.filter((cf: any) => cf.clicks > 0 || cf.signups > 0).length > 0 && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="channel-funnels-section" testID="channel-funnels-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: T.pinkSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="layers" size={18} color={T.pink} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.referralAnalyticsPanel.auto.text.013', 'Channel Conversion Funnels')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.referralAnalyticsPanel.auto.text.014', 'Conversion rates broken down by referral channel')}</Text>
            </View>
          </View>

          <View style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, overflow: 'hidden' }}>
            <View style={{ flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 12, backgroundColor: T.card, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <Text style={{ flex: 1.5, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.referralAnalyticsPanel.auto.text.015', 'Channel')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.016', 'Clicks')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.017', 'Signups')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.018', 'Subs')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.019', 'Click→Sign')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.020', 'Sign→Sub')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.021', 'Revenue')}</Text>
            </View>
            {enhancedData.channel_funnels.filter((cf: any) => cf.clicks > 0 || cf.signups > 0).map((cf: any, i: number, arr: any[]) => (
              <View key={cf.channel} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: i < arr.length - 1 ? 1 : 0, borderBottomColor: T.border }}
                data-testid={`channel-funnel-${cf.channel}`} testID={`channel-funnel-${cf.channel}`}>
                <View style={{ flex: 1.5, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <View style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(cf.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={cf.channel === 'twitter' ? 'logo-twitter' : cf.channel === 'linkedin' ? 'logo-linkedin' : cf.channel === 'whatsapp' ? 'logo-whatsapp' : cf.channel === 'email' ? 'mail' : cf.channel === 'sms' ? 'chatbubble' : cf.channel === 'qr' ? 'qr-code' : 'link'} size={10} color={cf.color} />
                  </View>
                  <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }}>{cf.label}</Text>
                </View>
                <Text style={{ flex: 1, color: T.textSec, fontSize: 12, textAlign: 'center' }}>{cf.clicks}</Text>
                <Text style={{ flex: 1, color: T.textSec, fontSize: 12, fontWeight: '600', textAlign: 'center' }}>{cf.signups}</Text>
                <Text style={{ flex: 1, color: T.successText, fontSize: 12, fontWeight: '700', textAlign: 'center' }}>{cf.subscriptions}</Text>
                <View style={{ flex: 1, alignItems: 'center' }}>
                  <Text style={{ color: cf.click_to_signup > 30 ? T.success : T.textSec, fontSize: 11, fontWeight: '600' }}>{cf.click_to_signup}%</Text>
                </View>
                <View style={{ flex: 1, alignItems: 'center' }}>
                  <Text style={{ color: cf.signup_to_sub > 50 ? T.success : T.textSec, fontSize: 11, fontWeight: '600' }}>{cf.signup_to_sub}%</Text>
                </View>
                <Text style={{ flex: 1, color: T.purpleText, fontSize: 12, fontWeight: '700', textAlign: 'right' }}>${cf.revenue}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Distribution Row */}
      <View style={{ flexDirection: 'row', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        {/* Status Distribution */}
        <View style={{ flex: 1, minWidth: 260, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="referral-status-dist" testID="referral-status-dist">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="pie-chart" size={14} color={T.cyan} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.022', 'By Status')}</Text>
          </View>
          <View style={{ flexDirection: 'row', height: 10, borderRadius: 5, overflow: 'hidden', marginBottom: 14 }}>
            {Object.entries(statusDist).map(([s, c], i) => (
              <View key={s} style={{ flex: c as number, backgroundColor: statusColors[s] || T.textMuted, marginRight: i < Object.entries(statusDist).length - 1 ? 2 : 0 }} />
            ))}
          </View>
          {Object.entries(statusDist).map(([s, c]) => (
            <BarRow key={s} label={s.replace('_', ' ')} value={c as number} total={totalEvents} color={statusColors[s] || T.textMuted} />
          ))}
        </View>

        {/* Plan Distribution */}
        <View style={{ flex: 1, minWidth: 260, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="referral-plan-dist" testID="referral-plan-dist">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="card" size={14} color={T.purpleText} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.023', 'By Plan')}</Text>
          </View>
          <View style={{ flexDirection: 'row', height: 10, borderRadius: 5, overflow: 'hidden', marginBottom: 14 }}>
            {Object.entries(planDist).map(([p, c], i) => (
              <View key={p} style={{ flex: c as number, backgroundColor: planColors[p] || T.textMuted, marginRight: i < Object.entries(planDist).length - 1 ? 2 : 0 }} />
            ))}
          </View>
          {Object.entries(planDist).map(([p, c]) => (
            <BarRow key={p} label={p} value={c as number} total={totalEvents} color={planColors[p] || T.textMuted} />
          ))}
        </View>
      </View>

      {/* Tier Distribution */}
      <View style={{ flexDirection: 'row', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 280, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="referral-tier-dist" testID="referral-tier-dist">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="shield" size={14} color="var(--app-primary)" />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.024', 'Referrer Tiers')}</Text>
          </View>
          <View style={{ flexDirection: 'row', height: 10, borderRadius: 5, overflow: 'hidden', marginBottom: 14 }}>
            {Object.entries(tierDist).filter(([, c]) => (c as number) > 0).map(([t, c], i, arr) => (
              <View key={t} style={{ flex: c as number, backgroundColor: tierColors[t] || T.textMuted, marginRight: i < arr.length - 1 ? 2 : 0 }} />
            ))}
          </View>
          {Object.entries(tierDist).map(([t, c]) => (
            <BarRow key={t} label={t.charAt(0).toUpperCase() + t.slice(1)} value={c as number} total={totalReferrers} color={tierColors[t] || T.textMuted} />
          ))}
        </View>

        {/* Tier Commission Rates */}
        <View style={{ flex: 1, minWidth: 280, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="referral-tier-rates" testID="referral-tier-rates">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="trending-up" size={14} color={T.successText} />
            <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.025', 'Tier Commission Rates')}</Text>
          </View>
          {(a.tiers || []).map((t: any) => (
            <View key={t.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12, paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }}>
              <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((tierColors[t.id] || T.textMuted), '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="shield" size={16} color={tierColors[t.id] || T.textMuted} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: tierColors[t.id] || T.text, fontSize: 14, fontWeight: '700' }}>{t.name}</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{t.min_referrals}+ referrals</Text>
              </View>
              <Text style={{ color: T.text, fontSize: 18, fontWeight: '800' }}>{Math.round(t.commission * 100)}%</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Top Referrers Leaderboard */}
      <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }} data-testid="top-referrers-table" testID="top-referrers-table">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="trophy" size={16} color={T.warningText} />
          <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.026', 'Top Referrers')}</Text>
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.primary, '20'), borderRadius: 8, paddingHorizontal: 8, paddingVertical: 2, marginLeft: 4 }}>
            <Text style={{ color: T.primary, fontSize: 10, fontWeight: '700' }}>{topReferrers.length}</Text>
          </View>
        </View>
        {topReferrers.length === 0 ? (
          <View style={{ padding: 30, alignItems: 'center' }}>
            <Ionicons name="people-outline" size={36} color={T.textMuted} />
            <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 13 }}>{tx('admin.referralAnalyticsPanel.auto.text.027', 'No referrers yet')}</Text>
          </View>
        ) : (
          <View>
            <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <Text style={{ width: 30, color: T.textMuted, fontSize: 10, fontWeight: '700' }}>#</Text>
              <Text style={{ flex: 2, color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.referralAnalyticsPanel.auto.text.028', 'Referrer')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.029', 'Tier')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.030', 'Clicks')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.031', 'Signups')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.032', 'Active')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.033', 'Monthly')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.034', 'Total')}</Text>
            </View>
            {topReferrers.slice(0, 20).map((r, i) => {
              const medal = i === 0 ? 'var(--app-primary)' : i === 1 ? 'var(--app-primary)' : i === 2 ? 'var(--app-primary)' : '';
              return (
                <View key={r.user_id} style={{ flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: T.border, alignItems: 'center' }}
                  data-testid={`referrer-row-${i}`} testID={`referrer-row-${i}`}>
                  <View style={{ width: 30 }}>
                    {medal ? (
                      <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: (globalThis as any).__alphaColor(medal, '30'), alignItems: 'center', justifyContent: 'center' }}>
                        <Text style={{ color: medal, fontSize: 11, fontWeight: '800' }}>{i + 1}</Text>
                      </View>
                    ) : (
                      <Text style={{ color: T.textMuted, fontSize: 12, fontWeight: '600' }}>{i + 1}</Text>
                    )}
                  </View>
                  <View style={{ flex: 2 }}>
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{r.name || 'Anonymous'}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{r.code}</Text>
                  </View>
                  <View style={{ flex: 1, alignItems: 'center' }}>
                    <View style={{ backgroundColor: (globalThis as any).__alphaColor((tierColors[r.tier?.id] || T.textMuted), '20'), paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 }}>
                      <Text style={{ color: tierColors[r.tier?.id] || T.textMuted, fontSize: 10, fontWeight: '700' }}>{r.tier?.name || 'Starter'}</Text>
                    </View>
                  </View>
                  <Text style={{ flex: 1, color: T.textSec, fontSize: 13, fontWeight: '600', textAlign: 'center' }}>{r.total_clicks}</Text>
                  <Text style={{ flex: 1, color: T.textSec, fontSize: 13, fontWeight: '600', textAlign: 'center' }}>{r.total_signups}</Text>
                  <Text style={{ flex: 1, color: T.successText, fontSize: 13, fontWeight: '600', textAlign: 'center' }}>{r.active_subscribers}</Text>
                  <Text style={{ flex: 1, color: T.purpleText, fontSize: 13, fontWeight: '700', textAlign: 'right' }}>${r.monthly_earnings.toFixed(2)}</Text>
                  <Text style={{ flex: 1, color: T.text, fontSize: 13, fontWeight: '700', textAlign: 'right' }}>${r.total_earnings.toFixed(2)}</Text>
                </View>
              );
            })}
          </View>
        )}
      </View>

      {/* ═══ Channel Analytics Section ═══ */}
      {channelStats && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="admin-channel-analytics-section" testID="admin-channel-analytics-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="analytics" size={18} color={colors.warningText} />
              </View>
              <View>
                <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.referralAnalyticsPanel.auto.text.035', 'Channel Analytics')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.referralAnalyticsPanel.auto.text.036', 'Referral performance by sharing channel')}</Text>
              </View>
            </View>
            {channelStats.best_channel_label ? (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(colors.success, '15'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}>
                <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '700' }}>Top: {channelStats.best_channel_label}</Text>
              </View>
            ) : null}
          </View>

          {/* Channel KPIs */}
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 18 }}>
            {[
              { label: 'Total Clicks', value: channelStats.total_clicks, color: colors.indigoText },
              { label: 'Total Signups', value: channelStats.total_signups, color: colors.successText },
              { label: 'Revenue', value: `$${channelStats.total_revenue}`, color: colors.warningText },
            ].map((kpi) => (
              <View key={kpi.label} style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(kpi.color, '10'), borderRadius: 10, padding: 12, alignItems: 'center' }}>
                <Text style={{ color: kpi.color, fontSize: 18, fontWeight: '800' }}>{kpi.value}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{kpi.label}</Text>
              </View>
            ))}
          </View>

          {/* Channel Breakdown Table */}
          <View style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, overflow: 'hidden' }}>
            {/* Header */}
            <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 12, backgroundColor: T.bgSoft, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <Text style={{ flex: 2, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.referralAnalyticsPanel.auto.text.037', 'Channel')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.038', 'Clicks')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.039', 'Signups')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.040', 'Conv %')}</Text>
              <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.041', 'Share')}</Text>
            </View>
            {/* Rows */}
            {channelStats.channels?.map((ch: any, i: number) => (
              <View key={ch.channel} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: i < channelStats.channels.length - 1 ? 1 : 0, borderBottomColor: T.border }}>
                <View style={{ flex: 2, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <View style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(ch.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={ch.icon} size={12} color={ch.color} />
                  </View>
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{ch.label}</Text>
                </View>
                <Text style={{ flex: 1, color: T.textSec, fontSize: 12, textAlign: 'right' }}>{ch.clicks}</Text>
                <Text style={{ flex: 1, color: T.text, fontSize: 12, fontWeight: '700', textAlign: 'right' }}>{ch.signups}</Text>
                <Text style={{ flex: 1, color: ch.conversion_rate > 30 ? colors.success : T.textSec, fontSize: 12, textAlign: 'right' }}>{ch.conversion_rate}%</Text>
                <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 4 }}>
                  <View style={{ width: Math.max(ch.share_pct * 0.5, 2), height: 6, backgroundColor: ch.color, borderRadius: 3, opacity: 0.7 }} />
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{ch.share_pct}%</Text>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* ═══ Challenge Management Section ═══ */}
      <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="admin-challenges-section" testID="admin-challenges-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.error, '15'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="flame" size={18} color={colors.error} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.referralAnalyticsPanel.auto.text.042', 'Challenge Management')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.referralAnalyticsPanel.auto.text.043', 'Create and manage time-limited referral challenges')}</Text>
            </View>
          </View>
          <TouchableOpacity onPress={() => setShowCreateChallenge(!showCreateChallenge)}
            data-testid="create-challenge-btn" testID="create-challenge-btn"
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.error, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10 }}>
            <Ionicons name={showCreateChallenge ? 'close' : 'add'} size={16} color="var(--app-primary-text)" />
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{showCreateChallenge ? 'Cancel' : 'New Challenge'}</Text>
          </TouchableOpacity>
        </View>

        {/* Create Challenge Form */}
        {showCreateChallenge && (
          <View style={{ backgroundColor: T.bg, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: T.border }}>
            <TextInput placeholder={tx('admin.referralAnalyticsPanel.auto.placeholder.001', 'Challenge Title (e.g., Weekend Blitz)')} placeholderTextColor={T.textMuted}
              value={newChallenge.title} onChangeText={t => setNewChallenge(p => ({ ...p, title: t }))}
              data-testid="challenge-title-input" testID="challenge-title-input"
              style={{ color: T.text, fontSize: 14, paddingVertical: 10, paddingHorizontal: 14, backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, marginBottom: 10 }} />
            <TextInput placeholder={tx('admin.referralAnalyticsPanel.auto.placeholder.002', 'Description (e.g., Get 3 referrals for a $15 bonus!)')} placeholderTextColor={T.textMuted}
              value={newChallenge.description} onChangeText={t => setNewChallenge(p => ({ ...p, description: t }))}
              data-testid="challenge-desc-input" testID="challenge-desc-input"
              style={{ color: T.text, fontSize: 13, paddingVertical: 10, paddingHorizontal: 14, backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, marginBottom: 10 }} />
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 12 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4, textTransform: 'uppercase' }}>{tx('admin.referralAnalyticsPanel.auto.text.044', 'Goal (referrals)')}</Text>
                <TextInput value={newChallenge.goal_count} accessibilityLabel={tx('admin.referralAnalyticsPanel.auto.accessibility.001', 'Reward ($)')} onChangeText={t => setNewChallenge(p => ({ ...p, goal_count: t }))}
                  keyboardType="numeric" data-testid="challenge-goal-input" testID="challenge-goal-input"
                  style={{ color: T.text, fontSize: 14, paddingVertical: 10, paddingHorizontal: 14, backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border }} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4, textTransform: 'uppercase' }}>{tx('admin.referralAnalyticsPanel.auto.text.045', 'Reward ($)')}</Text>
                <TextInput value={newChallenge.reward_value} accessibilityLabel={tx('admin.referralAnalyticsPanel.auto.accessibility.002', 'Duration (days)')} onChangeText={t => setNewChallenge(p => ({ ...p, reward_value: t }))}
                  keyboardType="numeric" data-testid="challenge-reward-input" testID="challenge-reward-input"
                  style={{ color: T.text, fontSize: 14, paddingVertical: 10, paddingHorizontal: 14, backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border }} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4, textTransform: 'uppercase' }}>{tx('admin.referralAnalyticsPanel.auto.text.046', 'Duration (days)')}</Text>
                <TextInput value={newChallenge.days} accessibilityLabel={tx('admin.referralAnalyticsPanel.auto.accessibility.003', 'Text input')} onChangeText={t => setNewChallenge(p => ({ ...p, days: t }))}
                  keyboardType="numeric" data-testid="challenge-days-input" testID="challenge-days-input"
                  style={{ color: T.text, fontSize: 14, paddingVertical: 10, paddingHorizontal: 14, backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border }} />
              </View>
            </View>
            <TouchableOpacity onPress={handleCreateChallenge} disabled={creatingChallenge || !newChallenge.title || !newChallenge.description}
              data-testid="submit-challenge-btn" testID="submit-challenge-btn"
              style={{ backgroundColor: (!newChallenge.title || !newChallenge.description) ? colors.textMuted : colors.error, paddingVertical: 12, borderRadius: 10, alignItems: 'center' }}>
              <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{creatingChallenge ? 'Creating...' : 'Create Challenge'}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Challenge List */}
        {challengeRows.map((ch: any) => (
          <View key={ch.challenge_id} style={{
            backgroundColor: T.bg, borderRadius: 12, padding: 14, marginBottom: 10,
            borderWidth: 1, borderColor: ch.is_running ? (globalThis as any).__alphaColor(colors.error, '30') : T.border,
            borderLeftWidth: 3, borderLeftColor: ch.is_running ? colors.error : ch.is_active ? colors.warning : colors.textMuted,
          }} data-testid={`admin-challenge-${ch.challenge_id}`} testID={`admin-challenge-${ch.challenge_id}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <View style={{ flex: 1, marginRight: 12 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{ch.title}</Text>
                  <View style={{ backgroundColor: ch.is_running ? (globalThis as any).__alphaColor(colors.success, '15') : colors.textMuted + '15', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
                    <Text style={{ color: ch.is_running ? colors.success : colors.textMuted, fontSize: 9, fontWeight: '700' }}>
                      {ch.is_running ? 'LIVE' : ch.is_active ? 'SCHEDULED' : 'INACTIVE'}
                    </Text>
                  </View>
                </View>
                <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 8 }}>{ch.description}</Text>
                <View style={{ flexDirection: 'row', gap: 16 }}>
                  <View>
                    <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{ch.participants}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.referralAnalyticsPanel.auto.text.047', 'Participants')}</Text>
                  </View>
                  <View>
                    <Text style={{ color: colors.successText, fontSize: 14, fontWeight: '700' }}>{ch.completions}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.referralAnalyticsPanel.auto.text.048', 'Completed')}</Text>
                  </View>
                  <View>
                    <Text style={{ color: colors.warningText, fontSize: 14, fontWeight: '700' }}>${ch.total_rewarded}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.referralAnalyticsPanel.auto.text.049', 'Rewarded')}</Text>
                  </View>
                  <View>
                    <Text style={{ color: T.textSec, fontSize: 14, fontWeight: '700' }}>{ch.completion_rate}%</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{tx('admin.referralAnalyticsPanel.auto.text.050', 'Completion')}</Text>
                  </View>
                </View>
              </View>
              <TouchableOpacity onPress={() => toggleChallenge(ch.challenge_id, ch.is_active)}
                data-testid={`toggle-challenge-${ch.challenge_id}`} testID={`toggle-challenge-${ch.challenge_id}`}
                style={{ backgroundColor: ch.is_active ? (globalThis as any).__alphaColor(colors.error, '15') : colors.success + '15', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}>
                <Text style={{ color: ch.is_active ? colors.error : colors.success, fontSize: 10, fontWeight: '700' }}>
                  {ch.is_active ? 'Deactivate' : 'Activate'}
                </Text>
              </TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: T.border }}>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>Goal: {ch.goal_count} referrals | Reward: ${ch.reward_value}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>
                {new Date(ch.start_date).toLocaleDateString()} - {new Date(ch.end_date).toLocaleDateString()}
              </Text>
            </View>
          </View>
        ))}

        {challengeRows.length === 0 && (
          <View style={{ alignItems: 'center', paddingVertical: 20, opacity: 0.6 }}>
            <Ionicons name="flame-outline" size={28} color={T.textMuted} />
            <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 8 }}>{tx('admin.referralAnalyticsPanel.auto.text.051', 'No challenges created yet')}</Text>
          </View>
        )}

        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
          <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="referral-challenges-page-summary" testID="referral-challenges-page-summary">
            Page {challengePage} of {challengeTotalPages} • {challengeTotalCount} total
          </Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={() => setChallengePage((p) => Math.max(1, p - 1))}
              disabled={challengePage <= 1}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, opacity: challengePage <= 1 ? 0.5 : 1 }}
              data-testid="referral-challenges-prev-page"
              testID="referral-challenges-prev-page"
            >
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>Prev</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setChallengePage((p) => Math.min(challengeTotalPages, p + 1))}
              disabled={challengePage >= challengeTotalPages}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, opacity: challengePage >= challengeTotalPages ? 0.5 : 1 }}
              data-testid="referral-challenges-next-page"
              testID="referral-challenges-next-page"
            >
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>Next</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* ═══ Milestone Rewards Section ═══ */}
      {milestoneStats && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="admin-milestone-section" testID="admin-milestone-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="trophy" size={18} color={colors.warningText} />
              </View>
              <View>
                <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.referralAnalyticsPanel.auto.text.052', 'Milestone Rewards')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.referralAnalyticsPanel.auto.text.053', 'Bonus credits for referral achievements')}</Text>
              </View>
            </View>
          </View>

          {/* Milestone KPIs */}
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            {[
              { label: 'Total Achievements', value: milestoneStats.total_achievements, icon: 'medal', color: colors.warningText },
              { label: 'Unique Achievers', value: milestoneStats.unique_achievers, icon: 'people', color: T.primary },
              { label: 'Total Bonus Paid', value: `$${milestoneStats.total_bonus_paid.toFixed(2)}`, icon: 'cash', color: T.successText },
            ].map(k => (
              <View key={k.label} style={{ flex: 1, minWidth: 130, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <Ionicons name={k.icon as any} size={12} color={k.color} />
                  <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{k.label}</Text>
                </View>
                <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{k.value}</Text>
              </View>
            ))}
          </View>

          {/* Milestone Breakdown */}
          <View style={{ marginBottom: 16 }}>
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('admin.referralAnalyticsPanel.auto.text.054', 'Milestone Tiers')}</Text>
            {milestoneStats.milestones.map((m: any, i: number) => {
              const maxAchievers = Math.max(...milestoneStats.milestones.map((x: any) => x.achievers), 1);
              return (
                <View key={m.id} style={{
                  flexDirection: 'row', alignItems: 'center', paddingVertical: 12, gap: 12,
                  borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border,
                }}>
                  <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(m.color, '18'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={m.icon as any} size={16} color={m.color} />
                  </View>
                  <View style={{ flex: 2 }}>
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{m.label}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{m.referrals_required} referrals &middot; +${m.bonus} bonus</Text>
                  </View>
                  <View style={{ flex: 2 }}>
                    <View style={{ height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden' }}>
                      <View style={{ height: '100%', width: `${Math.max((m.achievers / maxAchievers) * 100, 4)}%`, backgroundColor: m.color, borderRadius: 3 }} />
                    </View>
                  </View>
                  <View style={{ minWidth: 55, alignItems: 'flex-end' }}>
                    <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{m.achievers}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>${m.total_paid.toFixed(0)} paid</Text>
                  </View>
                </View>
              );
            })}
          </View>

          {/* Recent Achievements */}
          {milestoneStats.recent_achievements && milestoneStats.recent_achievements.length > 0 && (
            <View>
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('admin.referralAnalyticsPanel.auto.text.055', 'Recent Achievements')}</Text>
              {milestoneStats.recent_achievements.map((a: any, i: number) => (
                <View key={i} style={{
                  flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 10,
                  borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border,
                }} data-testid={`admin-milestone-achievement-${i}`} testID={`admin-milestone-achievement-${i}`}>
                  <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.warning, '15'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="trophy" size={14} color={colors.warningText} />
                  </View>
                  <View style={{ flex: 2 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{a.user_name || 'Unknown'}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>{a.user_email}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600' }}>{a.label}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: T.successText, fontSize: 13, fontWeight: '800' }}>+${a.bonus}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>
                      {a.achieved_at ? new Date(a.achieved_at).toLocaleDateString() : ''}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          )}

          {milestoneStats.recent_achievements && milestoneStats.recent_achievements.length === 0 && (
            <View style={{ alignItems: 'center', paddingVertical: 16 }}>
              <Ionicons name="trophy-outline" size={24} color={T.textMuted} />
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>{tx('admin.referralAnalyticsPanel.auto.text.056', 'No milestone achievements yet')}</Text>
            </View>
          )}
        </View>
      )}

      {/* ═══ Credit & Payouts Section ═══ */}
      {creditStats && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="admin-credit-payouts-section" testID="admin-credit-payouts-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: T.purpleSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="wallet" size={18} color={T.purpleText} />
              </View>
              <View>
                <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.referralAnalyticsPanel.auto.text.057', 'Credits & Payouts')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{creditStats.description || 'Auto-apply referral credits to renewals'}</Text>
              </View>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ backgroundColor: T.successSoft, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '30') }}>
                <Text style={{ color: T.successText, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{creditStats.automation_status}</Text>
              </View>
            </View>
          </View>

          {/* Credit KPIs */}
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            {[
              { label: 'Total Wallets', value: creditStats.total_wallets, icon: 'people', color: T.primary },
              { label: 'Active Balances', value: creditStats.wallets_with_balance, icon: 'wallet', color: T.purpleText },
              { label: 'Total Credited', value: `$${creditStats.total_earned.toFixed(2)}`, icon: 'trending-up', color: T.successText },
              { label: 'Total Applied', value: `$${creditStats.total_applied.toFixed(2)}`, icon: 'checkmark-done', color: T.cyan },
              { label: 'Pending Balance', value: `$${creditStats.total_pending_balance.toFixed(2)}`, icon: 'time', color: T.warningText },
            ].map(k => (
              <View key={k.label} style={{ flex: 1, minWidth: 130, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <Ionicons name={k.icon as any} size={12} color={k.color} />
                  <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{k.label}</Text>
                </View>
                <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{k.value}</Text>
              </View>
            ))}
          </View>

          {/* Transaction Breakdown */}
          <View style={{ flexDirection: 'row', gap: 12, marginBottom: 16 }}>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <Ionicons name="arrow-down" size={14} color={T.successText} />
                <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.058', 'Credit Transactions')}</Text>
              </View>
              <Text style={{ color: T.successText, fontSize: 28, fontWeight: '800' }}>{creditStats.credit_transactions}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.referralAnalyticsPanel.auto.text.059', 'Commissions earned')}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <Ionicons name="arrow-up" size={14} color={T.cyan} />
                <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.060', 'Debit Transactions')}</Text>
              </View>
              <Text style={{ color: T.cyan, fontSize: 28, fontWeight: '800' }}>{creditStats.debit_transactions}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.referralAnalyticsPanel.auto.text.061', 'Applied to renewals')}</Text>
            </View>
          </View>

          {/* Monthly Credit Trend */}
          {creditStats.monthly_trend && creditStats.monthly_trend.length > 0 && (
            <View style={{ marginBottom: 16 }}>
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('admin.referralAnalyticsPanel.auto.text.062', 'Monthly Credit Flow (6 Months)')}</Text>
              {creditStats.monthly_trend.map((m: any, i: number) => {
                const maxVal = Math.max(...creditStats.monthly_trend.map((t: any) => Math.max(t.earned, t.applied, 1)));
                return (
                  <View key={i} style={{ marginBottom: 10 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600', minWidth: 60 }}>{m.month}</Text>
                      <View style={{ flexDirection: 'row', gap: 12 }}>
                        <Text style={{ color: T.successText, fontSize: 10, fontWeight: '600' }}>+${m.earned.toFixed(2)}</Text>
                        <Text style={{ color: T.cyan, fontSize: 10, fontWeight: '600' }}>-${m.applied.toFixed(2)}</Text>
                      </View>
                    </View>
                    <View style={{ flexDirection: 'row', gap: 4 }}>
                      <View style={{ flex: 1, height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden' }}>
                        <View style={{ height: '100%', width: `${Math.max((m.earned / maxVal) * 100, 2)}%`, backgroundColor: T.success, borderRadius: 3 }} />
                      </View>
                      <View style={{ flex: 1, height: 6, backgroundColor: T.card, borderRadius: 3, overflow: 'hidden' }}>
                        <View style={{ height: '100%', width: `${Math.max((m.applied / maxVal) * 100, 2)}%`, backgroundColor: T.cyan, borderRadius: 3 }} />
                      </View>
                    </View>
                  </View>
                );
              })}
              <View style={{ flexDirection: 'row', gap: 16, marginTop: 4 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.success }} />
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.referralAnalyticsPanel.auto.text.063', 'Earned')}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.cyan }} />
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.referralAnalyticsPanel.auto.text.064', 'Applied')}</Text>
                </View>
              </View>
            </View>
          )}

          {/* Top Wallets */}
          {creditStats.top_wallets && creditStats.top_wallets.length > 0 && (
            <View style={{ marginBottom: 16 }}>
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('admin.referralAnalyticsPanel.auto.text.065', 'Top Wallet Balances')}</Text>
              {creditStats.top_wallets.map((w: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border, gap: 10 }}>
                  <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: T.purpleSoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ color: T.purpleText, fontSize: 11, fontWeight: '800' }}>{i + 1}</Text>
                  </View>
                  <View style={{ flex: 2 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{w.name}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{w.email}</Text>
                  </View>
                  <View style={{ backgroundColor: T.primarySoft, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                    <Text style={{ color: T.primary, fontSize: 9, fontWeight: '700', textTransform: 'capitalize' }}>{w.plan}</Text>
                  </View>
                  <Text style={{ color: T.purpleText, fontSize: 14, fontWeight: '800', minWidth: 70, textAlign: 'right' }}>${w.balance.toFixed(2)}</Text>
                </View>
              ))}
            </View>
          )}

          {/* Upcoming Renewals with Credits */}
          {creditStats.upcoming_renewals && creditStats.upcoming_renewals.length > 0 && (
            <View style={{ marginBottom: 16 }}>
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('admin.referralAnalyticsPanel.auto.text.066', 'Upcoming Renewals with Credits')}</Text>
              <View style={{ borderRadius: 10, overflow: 'hidden', borderWidth: 1, borderColor: T.border }}>
                {/* Header */}
                <View style={{ flexDirection: 'row', backgroundColor: T.card, paddingVertical: 8, paddingHorizontal: 10, borderBottomWidth: 1, borderBottomColor: T.border }}>
                  <Text style={{ flex: 2, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.referralAnalyticsPanel.auto.text.067', 'User')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.referralAnalyticsPanel.auto.text.068', 'Plan')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.069', 'Cost')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.070', 'Credits')}</Text>
                  <Text style={{ flex: 1, color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', textAlign: 'right' }}>{tx('admin.referralAnalyticsPanel.auto.text.071', 'Status')}</Text>
                </View>
                {creditStats.upcoming_renewals.map((r: any, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 10, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border, alignItems: 'center' }}
                    data-testid={`renewal-row-${i}`} testID={`renewal-row-${i}`}>
                    <View style={{ flex: 2 }}>
                      <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }}>{r.name}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 9 }}>{r.email}</Text>
                    </View>
                    <Text style={{ flex: 1, color: T.textSec, fontSize: 11, fontWeight: '600', textAlign: 'center', textTransform: 'capitalize' }}>{r.plan}</Text>
                    <Text style={{ flex: 1, color: T.text, fontSize: 11, fontWeight: '600', textAlign: 'right' }}>${r.plan_cost.toFixed(2)}</Text>
                    <Text style={{ flex: 1, color: T.successText, fontSize: 11, fontWeight: '700', textAlign: 'right' }}>${r.credit_balance.toFixed(2)}</Text>
                    <View style={{ flex: 1, alignItems: 'flex-end' }}>
                      <View style={{
                        backgroundColor: r.fully_covered ? T.successSoft : T.warningSoft,
                        paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6,
                      }}>
                        <Text style={{ color: r.fully_covered ? T.success : T.warning, fontSize: 9, fontWeight: '700' }}>
                          {r.fully_covered ? 'Covered' : 'Partial'}
                        </Text>
                      </View>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Recent Credit Transactions (Platform-wide) */}
          {creditStats.recent_transactions && creditStats.recent_transactions.length > 0 && (
            <View>
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('admin.referralAnalyticsPanel.auto.text.072', 'Recent Credit Transactions')}</Text>
              {creditStats.recent_transactions.map((txn: any, i: number) => (
                <View key={i} style={{
                  flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 10,
                  borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border,
                }} data-testid={`admin-credit-txn-${i}`} testID={`admin-credit-txn-${i}`}>
                  <View style={{
                    width: 30, height: 30, borderRadius: 8, alignItems: 'center', justifyContent: 'center',
                    backgroundColor: txn.type === 'credit' ? T.successSoft : T.cyanSoft,
                  }}>
                    <Ionicons name={txn.type === 'credit' ? 'arrow-down' : 'arrow-up'} size={14} color={txn.type === 'credit' ? T.success : T.cyan} />
                  </View>
                  <View style={{ flex: 2 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{txn.user_name || 'Unknown'}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>
                      {txn.type === 'credit' ? 'Commission earned' : 'Applied to renewal'}
                      {txn.details?.referred_name ? ` (${txn.details.referred_name})` : ''}
                    </Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: txn.type === 'credit' ? T.success : T.cyan, fontSize: 13, fontWeight: '800' }}>
                      {txn.type === 'credit' ? '+' : '-'}${txn.amount.toFixed(2)}
                    </Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>
                      {txn.created_at ? new Date(txn.created_at).toLocaleDateString() : ''}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Email Digest Management */}
      <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: T.border }} data-testid="admin-email-digest-section" testID="admin-email-digest-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.primary, '15'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="mail" size={18} color={T.primary} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.referralAnalyticsPanel.auto.text.073', 'Weekly Referral Digest')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{emailStats?.schedule || 'Every Monday 10:00 AM UTC'}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={sendTestDigest}
              disabled={sendingTest}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: (globalThis as any).__alphaColor(T.primary, '15'), paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '30'), opacity: sendingTest ? 0.5 : 1 }}
              data-testid="send-test-digest-btn" testID="send-test-digest-btn"
            >
              {sendingTest ? (
                <ActivityIndicator size="small" color={T.primary} />
              ) : (
                <Ionicons name="paper-plane" size={14} color={T.primary} />
              )}
              <Text style={{ color: T.primary, fontSize: 12, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.074', 'Send Test Email')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {testResult && (
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.success, '15'), borderRadius: 10, padding: 12, marginBottom: 16, flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '30') }}>
            <Ionicons name="checkmark-circle" size={16} color={T.successText} />
            <Text style={{ color: T.successText, fontSize: 12, fontWeight: '600', flex: 1 }}>{testResult}</Text>
            <TouchableOpacity accessibilityLabel={tx('admin.referralAnalyticsPanel.auto.accessibility.004', 'close button')} onPress={() => setTestResult(null)}>
              <Ionicons name="close" size={14} color={T.textMuted} />
            </TouchableOpacity>
          </View>
        )}

        {/* Email KPIs */}
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
          {[
            { label: 'Total Sent', value: emailStats?.total_sent || 0, icon: 'send', color: T.primary },
            { label: 'Last 7 Days', value: emailStats?.sent_7d || 0, icon: 'time', color: T.successText },
            { label: 'Last 30 Days', value: emailStats?.sent_30d || 0, icon: 'calendar', color: colors.purpleText },
            { label: 'Eligible Users', value: emailStats?.total_eligible_users || 0, icon: 'people', color: T.warningText },
          ].map(k => (
            <View key={k.label} style={{ flex: 1, minWidth: 130, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Ionicons name={k.icon as any} size={12} color={k.color} />
                <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{k.label}</Text>
              </View>
              <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{k.value}</Text>
            </View>
          ))}
        </View>

        {/* Tier Breakdown of Recipients */}
        {emailStats?.tier_breakdown && Object.keys(emailStats.tier_breakdown).length > 0 && (
          <View style={{ marginBottom: 16 }}>
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('admin.referralAnalyticsPanel.auto.text.075', 'Recipients by Tier')}</Text>
            <View style={{ flexDirection: 'row', height: 8, borderRadius: 4, overflow: 'hidden', marginBottom: 10 }}>
              {Object.entries(emailStats.tier_breakdown).map(([tier, count], i, arr) => (
                <View key={tier} style={{ flex: count as number, backgroundColor: tierColors[tier] || T.textMuted, marginRight: i < arr.length - 1 ? 2 : 0 }} />
              ))}
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {Object.entries(emailStats.tier_breakdown).map(([tier, count]) => (
                <View key={tier} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: tierColors[tier] || T.textMuted }} />
                  <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600', textTransform: 'capitalize' }}>{tier}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>({count as number})</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Recent Sends */}
        {emailStats?.recent_sends && emailStats.recent_sends.length > 0 && (
          <View>
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 }}>{tx('admin.referralAnalyticsPanel.auto.text.076', 'Recent Sends')}</Text>
            {emailStats.recent_sends.map((s: any, i: number) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border, gap: 10 }}>
                <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((tierColors[s.tier] || T.textMuted), '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="mail" size={12} color={tierColors[s.tier] || T.textMuted} />
                </View>
                <Text style={{ flex: 2, color: T.text, fontSize: 12, fontWeight: '500' }} numberOfLines={1}>{s.email}</Text>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor((tierColors[s.tier] || T.textMuted), '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                  <Text style={{ color: tierColors[s.tier] || T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'capitalize' }}>{s.tier}</Text>
                </View>
                <Text style={{ color: T.textMuted, fontSize: 10, minWidth: 50, textAlign: 'right' }}>Rank #{s.rank}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, minWidth: 80, textAlign: 'right' }}>{s.sent_at ? new Date(s.sent_at).toLocaleDateString() : ''}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Last Send Info */}
        {emailStats?.last_send_at && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: T.border }}>
            <Ionicons name="time-outline" size={12} color={T.textMuted} />
            <Text style={{ color: T.textMuted, fontSize: 11 }}>Last sent: {new Date(emailStats.last_send_at).toLocaleString()}</Text>
          </View>
        )}
      </View>

      {/* ═══ FRAUD DETECTION ═══ */}
      {fraudData && (
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: fraudData.total_open > 0 ? (globalThis as any).__alphaColor(T.error, '40') : T.border, marginTop: 20 }} data-testid="fraud-detection-section" testID="fraud-detection-section">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((fraudData.total_open > 0 ? T.error : T.success), '15'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="shield-checkmark" size={16} color={fraudData.total_open > 0 ? T.error : T.success} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.referralAnalyticsPanel.auto.text.077', 'Fraud Detection')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.referralAnalyticsPanel.auto.text.078', 'Automated referral abuse monitoring')}</Text>
            </View>
            {fraudData.total_open > 0 && (
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.error, '20'), paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
                <Text style={{ color: T.error, fontSize: 12, fontWeight: '800' }}>{fraudData.total_open} Open</Text>
              </View>
            )}
          </View>

          {/* Severity Summary */}
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }}>
            {[
              { key: 'high', label: 'High', color: T.error, icon: 'alert-circle' as const },
              { key: 'medium', label: 'Medium', color: T.warningText, icon: 'warning' as const },
              { key: 'low', label: 'Low', color: colors.textDim, icon: 'information-circle' as const },
            ].map(s => (
              <View key={s.key} style={{ flex: 1, backgroundColor: T.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: s.color }} data-testid={`fraud-severity-${s.key}`} testID={`fraud-severity-${s.key}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                  <Ionicons name={s.icon} size={12} color={s.color} />
                  <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{s.label}</Text>
                </View>
                <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{(fraudData.severity_counts || {})[s.key] || 0}</Text>
              </View>
            ))}
          </View>

          {/* Rules Info */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
            {Object.entries(fraudData.rule_counts || {}).map(([rule, count]) => (
              <View key={rule} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: T.card, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: T.border }}>
                <Ionicons name="analytics" size={10} color={T.primary} />
                <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600', textTransform: 'capitalize' }}>{(rule as string).replace(/_/g, ' ')}</Text>
                <Text style={{ color: T.text, fontSize: 10, fontWeight: '800' }}>{count as number}</Text>
              </View>
            ))}
            {Object.keys(fraudData.rule_counts || {}).length === 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, padding: 8 }}>
                <Ionicons name="checkmark-circle" size={14} color={T.successText} />
                <Text style={{ color: T.successText, fontSize: 12, fontWeight: '600' }}>{tx('admin.referralAnalyticsPanel.auto.text.079', 'No active fraud alerts')}</Text>
              </View>
            )}
          </View>

          {/* Alert List */}
          {openFraudAlerts.map((alert: any) => {
            const sevColor = alert.severity === 'high' ? T.error : alert.severity === 'medium' ? T.warning : colors.skeleton;
            return (
              <View key={alert.alert_id} style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(sevColor, '30'), borderLeftWidth: 3, borderLeftColor: sevColor }} data-testid={`fraud-alert-${alert.alert_id}`} testID={`fraud-alert-${alert.alert_id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <View style={{ backgroundColor: (globalThis as any).__alphaColor(sevColor, '15'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
                    <Text style={{ color: sevColor, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>{alert.severity}</Text>
                  </View>
                  <Text style={{ flex: 1, color: T.text, fontSize: 13, fontWeight: '700' }}>{alert.description}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Ionicons name="person" size={11} color={T.textMuted} />
                  <Text style={{ color: T.textSec, fontSize: 11 }}>{alert.user_name} ({alert.user_email})</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10, marginLeft: 'auto' }}>{alert.created_at ? new Date(alert.created_at).toLocaleDateString() : ''}</Text>
                </View>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TouchableOpacity
                    onPress={() => resolveAlert(alert.alert_id, 'dismissed')}
                    disabled={resolvingAlert === alert.alert_id}
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(T.success, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '30') }}
                    data-testid={`dismiss-alert-${alert.alert_id}`} testID={`dismiss-alert-${alert.alert_id}`}>
                    <Ionicons name="checkmark" size={14} color={T.successText} />
                    <Text style={{ color: T.successText, fontSize: 11, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.080', 'Dismiss')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => blockReferrer(alert.alert_id)}
                    disabled={resolvingAlert === alert.alert_id}
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(T.error, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '30') }}
                    data-testid={`block-alert-${alert.alert_id}`} testID={`block-alert-${alert.alert_id}`}>
                    <Ionicons name="ban" size={14} color={T.error} />
                    <Text style={{ color: T.error, fontSize: 11, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.081', 'Block User')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}

          {/* Resolved Alerts */}
          {resolvedFraudAlerts.length > 0 && (
            <View style={{ marginTop: 8 }}>
              <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '600', marginBottom: 6 }}>Resolved ({resolvedFraudAlerts.length})</Text>
              {resolvedFraudAlerts.slice(0, 5).map((alert: any) => (
                <View key={alert.alert_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderTopWidth: 1, borderTopColor: T.border, opacity: 0.6 }}>
                  <Ionicons name="checkmark-circle" size={14} color={T.successText} />
                  <Text style={{ flex: 1, color: T.textSec, fontSize: 11 }}>{alert.description}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 9, textTransform: 'capitalize' }}>{alert.resolution}</Text>
                </View>
              ))}
            </View>
          )}

          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
            <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="referral-fraud-page-summary" testID="referral-fraud-page-summary">
              Page {fraudPage} of {fraudTotalPages} • {fraudTotalCount} total alerts
            </Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity
                onPress={() => setFraudPage((p) => Math.max(1, p - 1))}
                disabled={fraudPage <= 1}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, opacity: fraudPage <= 1 ? 0.5 : 1 }}
                data-testid="referral-fraud-prev-page"
                testID="referral-fraud-prev-page"
              >
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>Prev</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setFraudPage((p) => Math.min(fraudTotalPages, p + 1))}
                disabled={fraudPage >= fraudTotalPages}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, opacity: fraudPage >= fraudTotalPages ? 0.5 : 1 }}
                data-testid="referral-fraud-next-page"
                testID="referral-fraud-next-page"
              >
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>Next</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Scan Controls & History */}
          <View style={{ marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: T.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name="scan" size={12} color={T.textMuted} />
                <Text style={{ color: T.textMuted, fontSize: 10 }}>Last scan: {fraudData.last_scan ? new Date(fraudData.last_scan).toLocaleString() : 'Never'}</Text>
              </View>
              <TouchableOpacity accessibilityLabel={tx('admin.referralAnalyticsPanel.auto.accessibility.005', 'Run Scan')}
                onPress={async () => {
                  try { await api.post('/referrals/admin/fraud-scan/run'); loadData(); } catch (e) { console.error(e); }
                }}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(T.primary, '15'), paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '25') }}
                data-testid="run-fraud-scan-btn" testID="run-fraud-scan-btn">
                <Ionicons name="refresh" size={12} color={T.primary} />
                <Text style={{ color: T.primary, fontSize: 10, fontWeight: '700' }}>{tx('admin.referralAnalyticsPanel.auto.text.082', 'Run Scan')}</Text>
              </TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: T.bgSoft, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }}>
              <Ionicons name="timer" size={11} color={T.textMuted} />
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.referralAnalyticsPanel.auto.text.083', 'Auto-scans every 6 hours')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 9 }}>|</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.referralAnalyticsPanel.auto.text.084', '7 rules active')}</Text>
            </View>
            {(fraudData.scan_history || []).length > 0 && (
              <View style={{ marginTop: 8 }}>
                <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '600', marginBottom: 4 }}>{tx('admin.referralAnalyticsPanel.auto.text.085', 'Recent Scans')}</Text>
                {(fraudData.scan_history || []).slice(0, 3).map((s: any, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 3 }}>
                    <View style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: s.scan_type === 'manual' ? T.primary : T.textMuted }} />
                    <Text style={{ color: T.textMuted, fontSize: 9, flex: 1 }}>{new Date(s.scan_time).toLocaleString()}</Text>
                    <Text style={{ color: s.alerts_generated > 0 ? T.warning : T.success, fontSize: 9, fontWeight: '600' }}>{s.alerts_generated} alert{s.alerts_generated !== 1 ? 's' : ''}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 8, textTransform: 'capitalize' }}>{s.scan_type}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        </View>
      )}

      {/* ═══ REFERRAL INTEGRITY ALERTS + RECOMMENDER ═══ */}
      <View
        style={{ backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border, marginTop: 20 }}
        data-testid="referral-integrity-alerts-section-detail"
        testID="referral-integrity-alerts-section-detail"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: T.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="alert-circle" size={16} color={T.primary} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '800' }} data-testid="referral-integrity-title" testID="referral-integrity-title">Referral Integrity Alerts</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>Fraud spikes + payout anomalies with proactive notifications</Text>
            </View>
          </View>

          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={evaluateIntegrityAlerts}
              disabled={runningIntegrityEval}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.card }}
              data-testid="evaluate-integrity-alerts-btn-detail"
              testID="evaluate-integrity-alerts-btn-detail"
            >
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{runningIntegrityEval ? 'Evaluating…' : 'Run Evaluation'}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={applyRecommendedProfile}
              disabled={applyingRecommendation}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '40'), backgroundColor: (globalThis as any).__alphaColor(T.success, '15') }}
              data-testid="apply-recommended-fraud-profile-btn-detail"
              testID="apply-recommended-fraud-profile-btn-detail"
            >
              <Text style={{ color: T.successText, fontSize: 11, fontWeight: '700' }}>{applyingRecommendation ? 'Applying…' : 'Apply Recommended Profile'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ marginTop: 14, backgroundColor: T.card, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 12 }} data-testid="fraud-policy-recommendation-card" testID="fraud-policy-recommendation-card">
          <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>Policy Recommendation</Text>
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '800', marginTop: 6 }} data-testid="fraud-policy-recommended-profile" testID="fraud-policy-recommended-profile">
            Active: {policyRecommendation?.active_profile || 'balanced'} → Recommended: {policyRecommendation?.recommendation?.recommended_profile || 'balanced'}
          </Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>
            Confidence {((policyRecommendation?.recommendation?.confidence || 0) * 100).toFixed(0)}% · Reasons: {(policyRecommendation?.recommendation?.reasons || []).join(', ') || 'none'}
          </Text>
        </View>

        <View style={{ marginTop: 14, backgroundColor: T.card, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 12 }} data-testid="integrity-incident-timeline-card" testID="integrity-incident-timeline-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
            <View>
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }} data-testid="integrity-incident-timeline-title" testID="integrity-incident-timeline-title">Integrity Incident Timeline</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Each integrity alert is linked to the most affected referral events in its impact window.</Text>
            </View>
            <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border }} data-testid="integrity-incident-timeline-count" testID="integrity-incident-timeline-count">
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '800' }}>{integrityIncidentRows.length} incidents</Text>
            </View>
          </View>

          {integrityIncidentRows.length === 0 ? (
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 12 }} data-testid="integrity-incident-timeline-empty" testID="integrity-incident-timeline-empty">No integrity incidents have been captured yet.</Text>
          ) : (
            <View style={{ marginTop: 12, gap: 10 }} data-testid="integrity-incident-timeline-list" testID="integrity-incident-timeline-list">
              {integrityIncidentRows.slice(0, 5).map((incident: any, idx: number) => {
                const severityColor = incident?.severity === 'high'
                  ? T.error
                  : incident?.severity === 'medium'
                    ? T.warning
                    : T.primary;
                const events = Array.isArray(incident?.events) ? incident.events : [];
                return (
                  <View
                    key={`${incident?.incident_id || idx}`}
                    style={{ borderRadius: 10, borderWidth: 1, borderColor: T.border, backgroundColor: T.bgSoft, padding: 12 }}
                    data-testid={`integrity-incident-timeline-row-${idx}`}
                    testID={`integrity-incident-timeline-row-${idx}`}
                  >
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                      <Text style={{ color: T.text, fontSize: 12, fontWeight: '800', flex: 1 }} data-testid={`integrity-incident-timeline-row-title-${idx}`} testID={`integrity-incident-timeline-row-title-${idx}`}>{incident?.title || 'Referral Integrity Alert'}</Text>
                      <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${severityColor}55`, backgroundColor: `${severityColor}15`, paddingHorizontal: 8, paddingVertical: 4 }} data-testid={`integrity-incident-timeline-row-severity-${idx}`} testID={`integrity-incident-timeline-row-severity-${idx}`}>
                        <Text style={{ color: severityColor, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{incident?.severity || 'medium'}</Text>
                      </View>
                    </View>

                    <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }} data-testid={`integrity-incident-timeline-row-message-${idx}`} testID={`integrity-incident-timeline-row-message-${idx}`}>
                      {incident?.message || 'No incident summary available.'}
                    </Text>

                    <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
                      <View style={{ borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid={`integrity-incident-timeline-row-events-${idx}`} testID={`integrity-incident-timeline-row-events-${idx}`}>
                        <Text style={{ color: T.text, fontSize: 10, fontWeight: '800' }}>{incident?.affected_events_count || 0} linked events</Text>
                      </View>
                      <View style={{ borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid={`integrity-incident-timeline-row-referrers-${idx}`} testID={`integrity-incident-timeline-row-referrers-${idx}`}>
                        <Text style={{ color: T.text, fontSize: 10, fontWeight: '800' }}>{incident?.impacted_referrers_count || 0} referrers impacted</Text>
                      </View>
                      <View style={{ borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid={`integrity-incident-timeline-row-commission-${idx}`} testID={`integrity-incident-timeline-row-commission-${idx}`}>
                        <Text style={{ color: T.text, fontSize: 10, fontWeight: '800' }}>${Number(incident?.summary?.commission_at_risk || 0).toFixed(2)} at risk</Text>
                      </View>
                    </View>

                    <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 10 }} data-testid={`integrity-incident-timeline-row-signals-${idx}`} testID={`integrity-incident-timeline-row-signals-${idx}`}>
                      Signals: {(incident?.signals || []).join(', ') || 'none'}
                    </Text>

                    <View style={{ marginTop: 10, gap: 8 }} data-testid={`integrity-incident-timeline-row-linked-events-${idx}`} testID={`integrity-incident-timeline-row-linked-events-${idx}`}>
                      {events.length === 0 ? (
                        <Text style={{ color: T.textMuted, fontSize: 10 }} data-testid={`integrity-incident-timeline-row-empty-${idx}`} testID={`integrity-incident-timeline-row-empty-${idx}`}>No linked referral events found for this incident window.</Text>
                      ) : events.slice(0, 3).map((event: any, eventIdx: number) => (
                        <View
                          key={`${event?.referral_id || eventIdx}`}
                          style={{ borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.card, padding: 10 }}
                          data-testid={`integrity-incident-timeline-row-${idx}-event-${eventIdx}`}
                          testID={`integrity-incident-timeline-row-${idx}-event-${eventIdx}`}
                        >
                          <Text style={{ color: T.text, fontSize: 11, fontWeight: '800' }} data-testid={`integrity-incident-timeline-row-${idx}-event-id-${eventIdx}`} testID={`integrity-incident-timeline-row-${idx}-event-id-${eventIdx}`}>
                            Referral {event?.referral_id || 'unknown'}
                          </Text>
                          <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }} data-testid={`integrity-incident-timeline-row-${idx}-event-meta-${eventIdx}`} testID={`integrity-incident-timeline-row-${idx}-event-meta-${eventIdx}`}>
                            Status {event?.status || 'pending'} · Plan {event?.plan || 'free'} · Commission ${Number(event?.commission_earned || 0).toFixed(2)}
                          </Text>
                          <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }} data-testid={`integrity-incident-timeline-row-${idx}-event-actors-${eventIdx}`} testID={`integrity-incident-timeline-row-${idx}-event-actors-${eventIdx}`}>
                            Referrer {String(event?.referrer_id || 'n/a').slice(-8)} → Referred {String(event?.referred_user_id || 'n/a').slice(-8)}
                          </Text>
                        </View>
                      ))}
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>

        <View style={{ marginTop: 14, gap: 8 }}>
          {integrityRows.map((alert: any) => (
            <View key={alert.alert_id} style={{ backgroundColor: T.card, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 12 }} data-testid={`integrity-alert-${alert.alert_id}`} testID={`integrity-alert-${alert.alert_id}`}>
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '800' }}>{alert.title}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{alert.message}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>Signals: {(alert.signals || []).join(', ')}</Text>
              {alert?.suggestion ? (
                <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '35'), backgroundColor: (globalThis as any).__alphaColor(T.success, '10'), padding: 10 }} data-testid={`integrity-alert-suggestion-${alert.alert_id}`} testID={`integrity-alert-suggestion-${alert.alert_id}`}>
                  <Text style={{ color: T.successText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{alert.suggestion.title}</Text>
                  <Text style={{ color: T.text, fontSize: 11, fontWeight: '700', marginTop: 4 }}>{alert.suggestion.reason}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{alert.suggestion.helper}</Text>
                </View>
              ) : null}
              <View style={{ marginTop: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{alert.created_at ? new Date(alert.created_at).toLocaleString() : ''}</Text>
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  {alert?.suggestion ? (
                    <TouchableOpacity
                      onPress={() => applyIntegritySuggestion(alert.alert_id)}
                      disabled={applyingIntegritySuggestion === alert.alert_id}
                      style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '35'), backgroundColor: (globalThis as any).__alphaColor(T.success, '12') }}
                      data-testid={`apply-integrity-suggestion-${alert.alert_id}`}
                      testID={`apply-integrity-suggestion-${alert.alert_id}`}
                    >
                      <Text style={{ color: T.successText, fontSize: 10, fontWeight: '700' }}>{applyingIntegritySuggestion === alert.alert_id ? 'Applying…' : 'Apply Suggestion'}</Text>
                    </TouchableOpacity>
                  ) : null}
                  <TouchableOpacity
                    onPress={() => resolveIntegrityAlert(alert.alert_id)}
                    disabled={resolvingIntegrityAlert === alert.alert_id}
                    style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.bgSoft }}
                    data-testid={`resolve-integrity-alert-${alert.alert_id}`}
                    testID={`resolve-integrity-alert-${alert.alert_id}`}
                  >
                    <Text style={{ color: T.text, fontSize: 10, fontWeight: '700' }}>{resolvingIntegrityAlert === alert.alert_id ? 'Resolving…' : 'Resolve'}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          ))}
          {integrityRows.length === 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 12, alignItems: 'center' }} data-testid="integrity-alerts-empty" testID="integrity-alerts-empty">
              <Text style={{ color: T.successText, fontSize: 12, fontWeight: '700' }}>No open integrity alerts</Text>
            </View>
          )}
        </View>

        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
          <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="integrity-alerts-page-summary" testID="integrity-alerts-page-summary">
            Page {integrityPage} of {integrityTotalPages} • {integrityTotalCount} total alerts
          </Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={() => setIntegrityPage((p) => Math.max(1, p - 1))}
              disabled={integrityPage <= 1}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, opacity: integrityPage <= 1 ? 0.5 : 1 }}
              data-testid="integrity-alerts-prev-page"
              testID="integrity-alerts-prev-page"
            >
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>Prev</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setIntegrityPage((p) => Math.min(integrityTotalPages, p + 1))}
              disabled={integrityPage >= integrityTotalPages}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: T.border, opacity: integrityPage >= integrityTotalPages ? 0.5 : 1 }}
              data-testid="integrity-alerts-next-page"
              testID="integrity-alerts-next-page"
            >
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>Next</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* ═══ 7/30/90 Integrity Trends ═══ */}
      <View style={{ flexDirection: 'row', gap: 16, marginTop: 20, flexWrap: 'wrap' }} data-testid="integrity-trends-section-detail" testID="integrity-trends-section-detail">
        <View style={{ flex: 2, minWidth: 330, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>Conversion Quality Trend (90d)</Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Daily subscribed/signups ratio (%)</Text>
          <View style={{ marginTop: 12 }} data-testid="integrity-conversion-quality-chart" testID="integrity-conversion-quality-chart">
            <SparkLine data={qualitySeries} color={T.successText} height={70} />
          </View>
        </View>

        <View style={{ flex: 1, minWidth: 280, backgroundColor: T.bgSoft, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.text, fontSize: 15, fontWeight: '800' }}>Duplicate Prevention Breaches</Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Daily duplicate dedupe-key count</Text>
          <View style={{ marginTop: 12 }} data-testid="integrity-duplicate-breach-chart" testID="integrity-duplicate-breach-chart">
            <SparkLine data={duplicateSeries} color={T.error} height={70} />
          </View>
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
        {[
          { label: '7 Day', data: trendWindow7, color: T.primary, testId: 'integrity-window-7' },
          { label: '30 Day', data: trendWindow30, color: T.warningText, testId: 'integrity-window-30' },
          { label: '90 Day', data: trendWindow90, color: T.purpleText, testId: 'integrity-window-90' },
        ].map((window) => (
          <View key={window.label} style={{ flex: 1, minWidth: 220, backgroundColor: T.bgSoft, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, borderLeftWidth: 3, borderLeftColor: window.color }} data-testid={`${window.testId}-detail`} testID={`${window.testId}-detail`}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{window.label}</Text>
            <Text style={{ color: T.text, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{Number(window.data?.avg_conversion_quality || 0).toFixed(1)}%</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Avg conversion quality</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Duplicate breaches: {window.data?.duplicate_prevention_breaches || 0}</Text>
          </View>
        ))}
      </View>

    </View>
  );
}
