import React, { useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useHybridPolling } from '../../hooks/useHybridPolling';

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
  apple: 'var(--app-primary)',
  google: 'var(--app-success)',
}; }

// Module-scope theme-aware palette (CSS-var-backed) — exposes `T` at module
// scope so helper sub-components declared outside the default-exported
// component (sevColor, statusColor, KPI, etc.) resolve `T.*` references
// correctly in both light and dark modes.
const T = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  purpleText: 'var(--app-primary)',
  success: 'var(--app-success)', successText: 'var(--app-success)', successSoft: 'var(--app-success-soft)',
  warning: 'var(--app-warning)', warningText: 'var(--app-warning)', warningSoft: 'var(--app-warning-soft)',
  error: 'var(--app-error)', errorText: 'var(--app-error)', errorSoft: 'var(--app-error-soft)',
  purple: 'var(--app-primary)', cyan: 'var(--app-primary)' as any,
};

type Tab = 'overview' | 'reports' | 'recommendations';

export default function UnifiedASOPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<Tab>('overview');
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [generating, setGenerating] = useState(false);

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, repRes] = await Promise.all([
        api.get('/admin/aso-unified/dashboard'),
        api.get('/admin/aso-unified/reports?limit=10'),
      ]);
      setDashboard(dashRes.data);
      setReports(repRes.data.reports || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/unified-aso/hybrid-refresh',
    onTick: fetchDashboard,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const generateReport = async () => {
    setGenerating(true);
    try {
      await api.post('/admin/aso-unified/reports/generate');
      await fetchDashboard();
    } catch (e) {
      console.error(e);
    } finally {
      setGenerating(false);
    }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }} data-testid="aso-unified-loading" testID="aso-unified-loading">
      <AutoFixBanner domain="unified_aso" />
      <ActivityIndicator size="large" color={T.primary} />
      <Text style={{ color: T.textSec, marginTop: 12, fontSize: 14 }}>{tx('admin.unifiedASOPanel.auto.text.001', 'Loading Unified ASO Dashboard...')}</Text>
    </View>
  );

  const live = dashboard?.live_status;
  const latest = dashboard?.latest_report;
  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'overview', label: 'Overview', icon: 'layers' },
    { id: 'reports', label: `Reports (${reports.length})`, icon: 'document-text' },
    { id: 'recommendations', label: 'Actions', icon: 'bulb' },
  ];

  return (
    <ScrollView style={{ flex: 1 }} data-testid="aso-unified-panel" testID="aso-unified-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: `${T.cyan}22`, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="analytics" size={22} color={T.cyan} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }}>{tx('admin.unifiedASOPanel.auto.text.002', 'Unified ASO Dashboard')}</Text>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.unifiedASOPanel.auto.text.003', 'Cross-Platform App Store Optimization')}</Text>
          </View>
        </View>
        <TouchableOpacity
          data-testid="aso-generate-report-btn" testID="aso-generate-report-btn"
          onPress={generateReport}
          disabled={generating}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: T.primary,
            borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8, opacity: generating ? 0.6 : 1,
          }}
        >
          {generating ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="add-circle" size={16} color="var(--app-primary-text)" />}
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '600' }}>{tx('admin.unifiedASOPanel.auto.text.004', 'Generate Report')}</Text>
        </TouchableOpacity>
      </View>

      {/* Platform Status Cards */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }}>
        <PlatformCard
          icon="logo-apple"
          name="App Store Connect"
          connected={live?.apple?.connected}
          detail={`${live?.apple?.apps_count || 0} apps`}
          color={T.apple}
        />
        <PlatformCard
          icon="logo-google-playstore"
          name="Google Play Console"
          connected={live?.google?.connected}
          detail="Android Publisher v3"
          color={T.google}
        />
      </View>

      {/* Health Score */}
      {latest && (
        <View data-testid="aso-health-score" testID="aso-health-score" style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: T.border }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <View>
              <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 4 }}>{tx('admin.unifiedASOPanel.auto.text.005', 'Overall Health Score')}</Text>
              <Text style={{ color: scoreColor(latest.overall_health_score), fontSize: 36, fontWeight: '800' }}>
                {latest.overall_health_score}%
              </Text>
            </View>
            <View style={{ alignItems: 'flex-end' }}>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.unifiedASOPanel.auto.text.006', 'Last Report')}</Text>
              <Text style={{ color: T.textSec, fontSize: 12 }}>{new Date(latest.generated_at).toLocaleDateString()}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: latest.trigger === 'scheduled_weekly' ? T.cyan : T.purple }} />
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{latest.trigger}</Text>
              </View>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 16, marginTop: 14 }}>
            <StatBadge label="Platforms" value={`${latest.cross_platform_summary?.total_platforms_connected || 0}/2`} />
            <StatBadge label="Apps" value={latest.cross_platform_summary?.total_apps_tracked ?? 0} />
            <StatBadge label="Reviews" value={latest.cross_platform_summary?.total_cached_reviews ?? 0} />
            <StatBadge label="Sales Data" value={latest.cross_platform_summary?.total_cached_sales ?? 0} />
          </View>
        </View>
      )}

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        {TABS.map(t => (
          <TouchableOpacity
            key={t.id}
            data-testid={`aso-tab-${t.id}`} testID={`aso-tab-${t.id}`}
            onPress={() => setTab(t.id)}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              backgroundColor: tab === t.id ? (globalThis as any).__alphaColor(T.primary, '20') : T.card,
              borderWidth: 1, borderColor: tab === t.id ? (globalThis as any).__alphaColor(T.primary, '40') : T.border,
            }}
          >
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? T.primary : T.textMuted} />
            <Text style={{ color: tab === t.id ? T.primary : T.textSec, fontSize: 12, fontWeight: '600' }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'overview' && <OverviewTab latest={latest} />}
      {tab === 'reports' && <ReportsTab reports={reports} />}
      {tab === 'recommendations' && <RecommendationsTab latest={latest} />}

      {/* Scheduler Info */}
      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, marginTop: 16, borderWidth: 1, borderColor: T.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="time" size={16} color={T.cyan} />
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{tx('admin.unifiedASOPanel.auto.text.007', 'Automated Schedule')}</Text>
        </View>
        <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 6 }}>{tx('admin.unifiedASOPanel.auto.text.008', 'Reports are automatically generated every Monday at 08:00 UTC and emailed to platform admins.')}</Text>
        <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>
          Total reports generated: {dashboard?.total_reports || 0}
        </Text>
      </View>
    </ScrollView>
  );
}

function PlatformCard({ icon, name, connected, detail, color }: any) {
  return (
    <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Ionicons name={icon} size={20} color={color} />
        <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }} numberOfLines={1}>{name}</Text>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: connected ? T.success : T.error }} />
        <Text style={{ color: connected ? T.success : T.error, fontSize: 11, fontWeight: '600' }}>
          {connected ? 'Connected' : 'Disconnected'}
        </Text>
      </View>
      <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{detail}</Text>
    </View>
  );
}

function OverviewTab({ latest }: { latest: any }) {
  if (!latest) return (
    <View style={{ padding: 30, alignItems: 'center' }} data-testid="aso-overview-empty" testID="aso-overview-empty">
      <Ionicons name="document-text-outline" size={48} color={T.textMuted} />
      <Text style={{ color: T.textSec, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.unifiedASOPanel.auto.text.009', 'No Reports Yet')}</Text>
      <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4, textAlign: 'center' }}>{tx('admin.unifiedASOPanel.auto.text.010', 'Click "Generate Report" to create your first unified ASO report.')}</Text>
    </View>
  );

  return (
    <View data-testid="aso-overview-tab" testID="aso-overview-tab" style={{ gap: 10 }}>
      {/* Apple Detail */}
      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Ionicons name="logo-apple" size={16} color={T.apple} />
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{tx('admin.unifiedASOPanel.auto.text.011', 'Apple App Store')}</Text>
          <Text style={{ color: latest.platforms?.apple?.connected ? T.success : T.error, fontSize: 11, fontWeight: '600', marginLeft: 'auto' }}>
            Score: {latest.platforms?.apple?.health_score ?? 0}%
          </Text>
        </View>
        <Row label="Apps Tracked" value={latest.platforms?.apple?.apps_count ?? 0} />
        <Row label="Sales Reports Cached" value={latest.platforms?.apple?.cached_sales_count ?? 0} />
      </View>

      {/* Google Detail */}
      <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Ionicons name="logo-google-playstore" size={16} color={T.google} />
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{tx('admin.unifiedASOPanel.auto.text.012', 'Google Play Store')}</Text>
          <Text style={{ color: latest.platforms?.google?.connected ? T.success : T.error, fontSize: 11, fontWeight: '600', marginLeft: 'auto' }}>
            Score: {latest.platforms?.google?.health_score ?? 0}%
          </Text>
        </View>
        <Row label="Reviews Cached" value={latest.platforms?.google?.cached_reviews_count ?? 0} />
        <Row label="Service Account" value={latest.platforms?.google?.service_account?.split('.')[0] || '—'} />
      </View>
    </View>
  );
}

function ReportsTab({ reports }: { reports: any[] }) {
  if (!reports.length) return (
    <View style={{ padding: 30, alignItems: 'center' }} data-testid="aso-reports-empty" testID="aso-reports-empty">
      <Ionicons name="folder-open-outline" size={48} color={T.textMuted} />
      <Text style={{ color: T.textSec, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.unifiedASOPanel.auto.text.013', 'No Reports')}</Text>
    </View>
  );

  return (
    <View data-testid="aso-reports-tab" testID="aso-reports-tab" style={{ gap: 10 }}>
      {reports.map((r: any, i: number) => (
        <View key={i} style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{
                width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center',
                backgroundColor: (globalThis as any).__alphaColor(scoreColor(r.overall_health_score), '20'),
              }}>
                <Text style={{ color: scoreColor(r.overall_health_score), fontWeight: '800', fontSize: 13 }}>
                  {r.overall_health_score}
                </Text>
              </View>
              <View>
                <Text style={{ color: T.text, fontWeight: '600', fontSize: 13 }}>{r.report_id}</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{new Date(r.generated_at).toLocaleString()}</Text>
              </View>
            </View>
            <View style={{
              paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
              backgroundColor: r.trigger === 'scheduled_weekly' ? (globalThis as any).__alphaColor(T.cyan, '20') : T.purple + '20',
            }}>
              <Text style={{ color: r.trigger === 'scheduled_weekly' ? T.cyan : T.purple, fontSize: 10, fontWeight: '600' }}>
                {r.trigger}
              </Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 10 }}>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>
              Platforms: {r.cross_platform_summary?.total_platforms_connected}/2
            </Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>
              Recommendations: {r.recommendations?.length || 0}
            </Text>
          </View>
        </View>
      ))}
    </View>
  );
}

function RecommendationsTab({ latest }: { latest: any }) {
  const recs = latest?.recommendations || [];
  if (!recs.length) return (
    <View style={{ padding: 30, alignItems: 'center' }} data-testid="aso-recs-empty" testID="aso-recs-empty">
      <Ionicons name="checkmark-circle" size={48} color={T.successText} />
      <Text style={{ color: T.successText, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.unifiedASOPanel.auto.text.014', 'All Good')}</Text>
    </View>
  );

  const priorityIcon: Record<string, { icon: string; color: string }> = {
    high: { icon: 'alert-circle', color: T.error },
    medium: { icon: 'warning', color: T.warningText },
    low: { icon: 'information-circle', color: T.primary },
  };

  return (
    <View data-testid="aso-recs-tab" testID="aso-recs-tab" style={{ gap: 10 }}>
      {recs.map((r: any, i: number) => {
        const p = priorityIcon[r.priority] || priorityIcon.low;
        return (
          <View key={i} style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={p.icon as any} size={18} color={p.color} />
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <Text style={{ color: p.color, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{r.priority}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>({r.platform})</Text>
                </View>
                <Text style={{ color: T.textSec, fontSize: 12 }}>{r.action}</Text>
              </View>
            </View>
          </View>
        );
      })}
    </View>
  );
}

function Row({ label, value }: { label: string; value: any }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 }}>
      <Text style={{ color: T.textMuted, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '500' }}>{String(value)}</Text>
    </View>
  );
}

function StatBadge({ label, value }: { label: string; value: any }) {
  return (
    <View style={{ alignItems: 'center' }}>
      <Text style={{ color: T.text, fontSize: 16, fontWeight: '700' }}>{String(value)}</Text>
      <Text style={{ color: T.textMuted, fontSize: 10 }}>{label}</Text>
    </View>
  );
}

function scoreColor(score: number): string {
  if (score >= 80) return T.success;
  if (score >= 50) return T.warning;
  return T.error;
}
