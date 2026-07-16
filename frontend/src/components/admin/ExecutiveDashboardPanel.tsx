import React, { Suspense, lazy } from 'react';
import { View, Text, ActivityIndicator, useWindowDimensions, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import DashboardLayoutManager from './DashboardLayoutManager';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import CodeHealthWidget from './CodeHealthWidget';
import SecurityScoreWidget from './SecurityScoreWidget';
import StaleLinkRiskScoreWidget from './StaleLinkRiskScoreWidget';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
const ActivitySummaryWidget = lazy(() => import('./ActivitySummaryWidget'));

const tx = (_key: string, fallback: string) => fallback;

function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);

function StatCard({ label, value, icon, color, sub }: any) {
  return (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: (globalThis as any).__alphaColor(color, '10'), borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '20') }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text style={{ fontSize: 11, color: C.muted, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
        <Ionicons name={icon} size={16} color={color} />
      </View>
      <Text style={{ fontSize: 26, fontWeight: '800', color }}>{value}</Text>
      {sub && <Text style={{ fontSize: 11, color: C.sec, marginTop: 2 }}>{sub}</Text>}
    </View>
  );
}

function MiniChart({ data, color, height = 40 }: { data: number[]; color: string; height?: number }) {
  if (!data.length) return null;
  const max = Math.max(...data, 1);
  const barW = Math.min(24, Math.floor(260 / data.length));
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 2, marginTop: 8 }}>
      {data.map((v, i) => (
        <View key={i} style={{ width: barW, height: Math.max(2, (v / max) * height), backgroundColor: (globalThis as any).__alphaColor(color, '60'), borderRadius: 3 }} />
      ))}
    </View>
  );
}

export default function ExecutiveDashboardPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const { data: health, loading: hLoading } = useLiveQuery('/admin/manage/system/health', { entity: 'system-health', pollInterval: 30000 });
  const { data: security, loading: sLoading } = useLiveQuery('/admin/manage/security/overview', { entity: 'security', pollInterval: 30000 });
  const { data: emailStats, loading: eLoading } = useLiveQuery('/email-notifications/logs/stats', { entity: 'email-stats', pollInterval: 60000 });
  const { data: ticketStats, loading: tLoading } = useLiveQuery('/admin/manage/tickets/stats/overview', { entity: 'tickets', pollInterval: 60000 });
  const { data: integrity, loading: iLoading } = useLiveQuery('/admin/platform-integrity/overview', { entity: 'platform-integrity', pollInterval: 60000 });
  const { data: qualityTrends } = useLiveQuery('/admin/platform-health/executive/quality-trends?days=14', { entity: 'quality-trends', pollInterval: 120000 });
  const { data: secPosture } = useLiveQuery('/admin/autonomous-engine/executive/security-posture', { entity: 'exec-security-posture', pollInterval: 60000 });
  const loading = hLoading || sLoading || eLoading || tLoading || iLoading;

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={C.blue} /></View>;

  const dailyEvents = security?.daily_events?.map((d: any) => d.count) || [];
  const dailyLabels = security?.daily_events?.map((d: any) => d.day) || [];

  return (
    <View data-testid="executive-dashboard-panel" testID="executive-dashboard-panel">
      <AutoFixBanner domain="executive" />
      {/* Dashboard Customization */}
      <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginBottom: 12 }}>
        <DashboardLayoutManager dashboardType="executive" colors={{ primary: C.blue, card: C.card, border: C.border, text: C.text, textMuted: C.muted, textSec: C.sec, bg: C.bg }} />
      </View>
      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <StatCard label="Total Users" value={health?.total_users || 0} icon="people" color={C.blue} sub={`${health?.active_users_24h || 0} active today`} />
        <StatCard label="Active Sessions" value={health?.active_sessions || 0} icon="pulse" color={C.green} sub="Real-time" />
        <StatCard label="DB Latency" value={`${health?.db_latency_ms || 0}ms`} icon="server" color={C.cyan} sub="Response time" />
        <StatCard label="Emails Sent" value={emailStats?.totals?.sent || 0} icon="mail" color={C.purpleText} sub={`${emailStats?.totals?.failed || 0} failed`} />
      </View>

      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 20 }} data-testid="executive-integrity-summary-card" testID="executive-integrity-summary-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.executiveDashboardPanel.auto.text.001', 'AI Platform Integrity Snapshot')}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>{tx('admin.executiveDashboardPanel.auto.text.002', 'Leadership visibility into the latest autonomous integrity cycle and enforcement status.')}</Text>
          </View>
          <TouchableOpacity onPress={() => router.push('/admin-console?category=operations&tab=ai-platform-integrity' as any)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '30') }} data-testid="executive-open-integrity-engine-button" testID="executive-open-integrity-engine-button">
            <Text style={{ color: C.blue, fontSize: 12, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.003', 'Open Integrity Engine')}</Text>
          </TouchableOpacity>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 14 }}>
          {[
            { id: 'score', label: 'Integrity Score', value: `${integrity?.latest_run?.final_score || integrity?.platform_scan?.score || 0}/100`, color: C.blue, sub: integrity?.latest_run?.status ? `Status ${String(integrity.latest_run.status).toUpperCase()}` : 'No run yet' },
            { id: 'global', label: 'Global Validation', value: String(integrity?.global_validation?.status || 'healthy').toUpperCase(), color: integrity?.global_validation?.status === 'critical' ? C.red : integrity?.global_validation?.status === 'warning' ? C.yellow : C.green, sub: `${integrity?.global_validation?.summary?.healthy || 0} healthy checks` },
            { id: 'critical', label: 'Critical Checks', value: String(integrity?.global_validation?.summary?.critical || 0), color: C.red, sub: `${integrity?.global_validation?.summary?.warning || 0} warnings` },
            { id: 'lock', label: 'Regression Lock', value: integrity?.latest_lock?.lock_id ? 'LOCKED' : 'PENDING', color: integrity?.latest_lock?.lock_id ? C.green : C.yellow, sub: integrity?.latest_lock?.lock_id || 'Awaiting lock snapshot' },
          ].map((item) => (
            <View key={item.id} style={{ flex: 1, minWidth: 170, backgroundColor: (globalThis as any).__alphaColor(item.color, '10'), borderRadius: 12, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(item.color, '20') }} data-testid={`executive-integrity-stat-${item.id}`} testID={`executive-integrity-stat-${item.id}`}>
              <Text style={{ fontSize: 11, color: C.muted, fontWeight: '600', textTransform: 'uppercase' }}>{item.label}</Text>
              <Text style={{ fontSize: 24, color: item.color, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
              <Text style={{ fontSize: 11, color: C.sec, marginTop: 4 }}>{item.sub}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Live Security Posture Command Center */}
      {secPosture && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 20 }} data-testid="executive-security-posture-card" testID="executive-security-posture-card">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
            <View>
              <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.executiveDashboardPanel.auto.text.004', 'Security Command Center')}</Text>
              <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{tx('admin.executiveDashboardPanel.auto.text.005', 'Live zero-trust posture, threat monitoring, and drift ticket status')}</Text>
            </View>
            <View style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: secPosture.zero_trust_status === 'PASS' ? (globalThis as any).__alphaColor(C.green, '20') : C.red + '20' }} data-testid="executive-zt-status-badge" testID="executive-zt-status-badge">
              <Text style={{ fontSize: 12, fontWeight: '900', color: secPosture.zero_trust_status === 'PASS' ? C.green : C.red }}>{secPosture.zero_trust_status || 'N/A'}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-sec-threat" testID="executive-sec-threat">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.006', 'Threat Level')}</Text>
              <Text style={{ fontSize: 20, fontWeight: '900', color: secPosture.threat_level === 'NONE' ? C.green : secPosture.threat_level === 'LOW' ? C.lime : secPosture.threat_level === 'MEDIUM' ? C.yellow : C.red, marginTop: 3 }}>{secPosture.threat_level || '--'}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-sec-confidence" testID="executive-sec-confidence">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.007', 'Confidence')}</Text>
              <Text style={{ fontSize: 20, fontWeight: '900', color: secPosture.confidence === 'HIGH' ? C.green : secPosture.confidence === 'MEDIUM' ? C.yellow : C.red, marginTop: 3 }}>{secPosture.confidence || '--'}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-sec-pass-rate" testID="executive-sec-pass-rate">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.008', '7d Pass Rate')}</Text>
              <Text style={{ fontSize: 20, fontWeight: '900', color: (secPosture.pass_rate_7d || 0) >= 80 ? C.green : C.yellow, marginTop: 3 }}>{secPosture.pass_rate_7d || 0}%</Text>
            </View>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-sec-events" testID="executive-sec-events">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.009', 'Events (24h)')}</Text>
              <Text style={{ fontSize: 20, fontWeight: '900', color: (secPosture.security_events_24h || 0) > 100 ? C.yellow : C.green, marginTop: 3 }}>{secPosture.security_events_24h || 0}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-sec-drift-tickets" testID="executive-sec-drift-tickets">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.010', 'Open Drift Tickets')}</Text>
              <Text style={{ fontSize: 20, fontWeight: '900', color: (secPosture.drift_tickets?.high_severity_open || 0) > 0 ? C.red : C.green, marginTop: 3 }}>{secPosture.drift_tickets?.open || 0}</Text>
              {(secPosture.drift_tickets?.high_severity_open || 0) > 0 && <Text style={{ fontSize: 9, color: C.red, fontWeight: '700', marginTop: 2 }}>{secPosture.drift_tickets.high_severity_open} HIGH</Text>}
            </View>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-sec-blocked" testID="executive-sec-blocked">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.011', 'Blocked IPs')}</Text>
              <Text style={{ fontSize: 20, fontWeight: '900', color: (secPosture.blocked_ips_active || 0) > 0 ? C.orange : C.green, marginTop: 3 }}>{secPosture.blocked_ips_active || 0}</Text>
            </View>
          </View>
          {(secPosture.scans_7d || []).length > 0 && (
            <View style={{ marginTop: 12 }}>
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginBottom: 4 }}>{tx('admin.executiveDashboardPanel.auto.text.012', '7-Day Scan Results')}</Text>
              <MiniChart data={(secPosture.scans_7d || []).map((s: any) => s.pass_count || 0)} color={C.green} height={30} />
            </View>
          )}
        </View>
      )}

      {/* Quality Trend Analytics */}
      {qualityTrends?.summary && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 20 }} data-testid="executive-quality-trends-card" testID="executive-quality-trends-card">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <View>
              <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{tx('admin.executiveDashboardPanel.auto.text.013', 'Quality Trend Analytics')}</Text>
              <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{tx('admin.executiveDashboardPanel.auto.text.014', 'Cross-dashboard quality trends (14 days)')}</Text>
            </View>
            <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: qualityTrends.summary.health_grade === 'A' ? (globalThis as any).__alphaColor(C.green, '20') : qualityTrends.summary.health_grade === 'B' ? C.blue + '20' : C.yellow + '20' }} data-testid="executive-quality-grade-badge" testID="executive-quality-grade-badge">
              <Text style={{ fontSize: 14, fontWeight: '900', color: qualityTrends.summary.health_grade === 'A' ? C.green : qualityTrends.summary.health_grade === 'B' ? C.blue : C.yellow }}>Grade {qualityTrends.summary.health_grade}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <View style={{ flex: 1, minWidth: 100, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-quality-health-score" testID="executive-quality-health-score">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.015', 'Health Score')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: C.blue, marginTop: 2 }}>{qualityTrends.summary.avg_health_score}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 100, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-quality-gate-rate" testID="executive-quality-gate-rate">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.016', 'Gate Pass Rate')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: C.green, marginTop: 2 }}>{qualityTrends.summary.gate_pass_rate}%</Text>
            </View>
            <View style={{ flex: 1, minWidth: 100, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-quality-slo-breaches" testID="executive-quality-slo-breaches">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.017', 'SLO Breaches')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: qualityTrends.summary.slo_breach_count > 0 ? C.red : C.green, marginTop: 2 }}>{qualityTrends.summary.slo_breach_count}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 100, backgroundColor: C.bg, borderRadius: 10, padding: 12, alignItems: 'center' }} data-testid="executive-quality-enforcement-score" testID="executive-quality-enforcement-score">
              <Text style={{ fontSize: 9, color: C.muted, fontWeight: '700' }}>{tx('admin.executiveDashboardPanel.auto.text.018', 'Enforcement')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: C.purpleText, marginTop: 2 }}>{qualityTrends.summary.avg_enforcement_score || '--'}</Text>
            </View>
          </View>
          {qualityTrends.trend?.length > 0 && (
            <View style={{ marginTop: 12 }}>
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginBottom: 4 }}>{tx('admin.executiveDashboardPanel.auto.text.019', 'Daily Health Score Trend')}</Text>
              <MiniChart data={qualityTrends.trend.map((t: any) => t.avg_health_score || 0)} color={C.blue} height={36} />
            </View>
          )}
        </View>
      )}

      <StaleLinkRiskScoreWidget />

      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        {/* Security Chart */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 4 }}>{tx('admin.executiveDashboardPanel.auto.text.020', 'Security Events (7 days)')}</Text>
          <View style={{ flexDirection: 'row', gap: 16, marginBottom: 8 }}>
            <Text style={{ fontSize: 12, color: C.green }}>Logins: {security?.successful_logins_24h || 0}</Text>
            <Text style={{ fontSize: 12, color: C.red }}>Failed: {security?.failed_logins_24h || 0}</Text>
            <Text style={{ fontSize: 12, color: C.yellow }}>Frozen: {security?.frozen_accounts || 0}</Text>
          </View>
          <MiniChart data={dailyEvents} color={C.blue} height={50} />
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 }}>
            {dailyLabels.map((l: string, i: number) => <Text key={i} style={{ fontSize: 9, color: C.muted }}>{l}</Text>)}
          </View>
        </View>

        {/* Support Stats */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.executiveDashboardPanel.auto.text.021', 'Support Tickets')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <View style={{ flex: 1, minWidth: 80, backgroundColor: (globalThis as any).__alphaColor(C.yellow, '12'), borderRadius: 10, padding: 12, alignItems: 'center' }}>
              <Text style={{ fontSize: 20, fontWeight: '800', color: C.yellow }}>{ticketStats?.open || 0}</Text>
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.executiveDashboardPanel.auto.text.022', 'Open')}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 80, backgroundColor: (globalThis as any).__alphaColor(C.blue, '12'), borderRadius: 10, padding: 12, alignItems: 'center' }}>
              <Text style={{ fontSize: 20, fontWeight: '800', color: C.blue }}>{ticketStats?.pending || 0}</Text>
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.executiveDashboardPanel.auto.text.023', 'Pending')}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 80, backgroundColor: (globalThis as any).__alphaColor(C.red, '12'), borderRadius: 10, padding: 12, alignItems: 'center' }}>
              <Text style={{ fontSize: 20, fontWeight: '800', color: C.red }}>{ticketStats?.escalated || 0}</Text>
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.executiveDashboardPanel.auto.text.024', 'Escalated')}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 80, backgroundColor: (globalThis as any).__alphaColor(C.green, '12'), borderRadius: 10, padding: 12, alignItems: 'center' }}>
              <Text style={{ fontSize: 20, fontWeight: '800', color: C.green }}>{ticketStats?.resolved || 0}</Text>
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.executiveDashboardPanel.auto.text.025', 'Resolved')}</Text>
            </View>
          </View>
        </View>
      </View>

      {/* Collections / DB */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 16 }}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.executiveDashboardPanel.auto.text.026', 'Database Collections')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {Object.entries(health?.collections || {}).sort(([, a]: any, [, b]: any) => b - a).slice(0, 12).map(([name, count]: any) => (
            <View key={name} style={{ backgroundColor: C.bg, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Text style={{ fontSize: 12, color: C.sec }}>{name}</Text>
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.blue }}>{count}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Live Activity Summary Widget */}
      <View style={{ marginBottom: 16 }}>
        <Suspense fallback={<View style={{ padding: 20, alignItems: 'center' }}><ActivityIndicator color={C.blue} /></View>}>
          <ActivitySummaryWidget colors={colors} />
        </Suspense>
      </View>

      {/* Code Health Widget */}
      <View style={{ marginBottom: 16 }}>
        <CodeHealthWidget colors={colors} />
      </View>

      {/* Security Score Widget */}
      <View style={{ marginBottom: 16 }}>
        <SecurityScoreWidget colors={colors} />
      </View>

      {/* Recent Audit */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.executiveDashboardPanel.auto.text.027', 'Recent Activity')}</Text>
        {(security?.recent_audit || []).slice(0, 8).map((e: any, i: number) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: C.border }}>
            <Ionicons name={e.event_type?.includes('success') ? 'checkmark-circle' : e.event_type?.includes('fail') ? 'close-circle' : 'information-circle'} size={16} color={e.event_type?.includes('success') ? C.green : e.event_type?.includes('fail') ? C.red : C.blue} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, color: C.text }}>{e.event_type?.replace(/_/g, ' ')}</Text>
              <Text style={{ fontSize: 10, color: C.muted }}>{e.user_id} - {e.timestamp ? new Date(e.timestamp).toLocaleString() : ''}</Text>
            </View>
            <View style={{ backgroundColor: e.severity === 'high' ? (globalThis as any).__alphaColor(C.red, '20') : e.severity === 'medium' ? C.yellow + '20' : C.green + '20', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
              <Text style={{ fontSize: 9, fontWeight: '700', color: e.severity === 'high' ? C.red : e.severity === 'medium' ? C.yellow : C.green }}>{e.severity}</Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}
