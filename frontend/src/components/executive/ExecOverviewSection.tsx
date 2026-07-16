import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useExecTheme, KPICard, RevenueChart, RegionTable, RiskPanel, useExecStyles } from '../admin/ExecDashboardPanels';
import DataFreshnessIndicator from '../DataFreshnessIndicator';

interface ExecOverviewSectionProps {
  activeSection: string;
  kpis: any;
  financial: any;
  risk: any;
  heatmap: any;
  securityScore: any;
  period: string;
  setPeriod: (p: string) => void;
  lastRefresh: Date;
  refreshing: boolean;
  loadData: () => void;
}

export function ExecOverviewSection({
  activeSection, kpis, financial, risk, heatmap, securityScore,
  period, setPeriod, lastRefresh, refreshing, loadData,
}: ExecOverviewSectionProps) {
  const s = useExecStyles();
  const THEME = useExecTheme();
  const router = useRouter();
  const truthCards = kpis?.truth_cards || {};
  const engineTruth = truthCards?.last_verified_engine_run;
  const auditTruth = truthCards?.global_audit_status;

  return (
    <>
      {/* KPI Header Strip */}
      {(activeSection === 'overview' || activeSection === 'financial') && kpis?.kpis && (
        <View data-testid="kpi-metrics-panel" testID="kpi-metrics-panel">
          <View style={s.sectionHeader}>
            <Text style={s.sectionTitle}>Executive Overview</Text>
            <DataFreshnessIndicator lastUpdated={lastRefresh} onRefresh={() => { loadData(); }} isRefreshing={refreshing} accentColor={THEME.primary} textColor={THEME.textMuted} />
          </View>
          <View style={s.kpiGrid}>
            {kpis.kpis.map((k: any) => <KPICard key={k.id} kpi={k} />)}
          </View>
          <View style={s.summaryStrip}>
            <View style={s.summaryItem}>
              <Ionicons name="people" size={16} color={THEME.primary} />
              <Text style={s.summaryText}>{kpis.total_users} Total Users</Text>
            </View>
            <View style={s.summaryItem}>
              <Ionicons name="star" size={16} color={THEME.warningText} />
              <Text style={s.summaryText}>{kpis.premium_users} Premium</Text>
            </View>
            <View style={s.summaryItem}>
              <Ionicons name="pulse" size={16} color={THEME.successText} />
              <Text style={s.summaryText}>{kpis.active_today} Active Today</Text>
            </View>
            <View style={s.summaryItem}>
              <Ionicons name="person-add" size={16} color={THEME.cyan} />
              <Text style={s.summaryText}>{kpis.new_users_week} New This Week</Text>
            </View>
          </View>
        </View>
      )}

      {activeSection === 'overview' && (engineTruth || auditTruth) && (
        <View style={s.panel} data-testid="executive-truth-cards-panel" testID="executive-truth-cards-panel">
          <View style={s.panelHeader}>
            <Text style={s.panelTitle}>Executive Truth Cards</Text>
            <Text style={{ color: THEME.textMuted, fontSize: 11 }}>Fast visibility into live engine verification and latest global audit confidence.</Text>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14 }}>
            <View style={{ flex: 1, minWidth: 280, backgroundColor: THEME.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: THEME.border }} data-testid="executive-last-verified-engine-run-card" testID="executive-last-verified-engine-run-card">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <View>
                  <Text style={{ color: THEME.text, fontSize: 15, fontWeight: '800' }}>Last Verified Engine Run</Text>
                  <Text style={{ color: THEME.textMuted, fontSize: 11, marginTop: 4 }}>Live truth from the Autonomous Engine freshness gate.</Text>
                </View>
                <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: engineTruth?.status === 'PASS' ? 'var(--app-success-soft)' : 'var(--app-warning-soft)' }} data-testid="executive-engine-run-status-pill" testID="executive-engine-run-status-pill">
                  <Text style={{ color: engineTruth?.status === 'PASS' ? 'var(--app-success)' : 'var(--app-warning)', fontSize: 10, fontWeight: '800' }}>{engineTruth?.status || 'UNKNOWN'}</Text>
                </View>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 14 }}>
                {[
                  { id: 'run', label: 'Run ID', value: engineTruth?.run_id || '—', color: THEME.primary },
                  { id: 'gate', label: 'Gate', value: engineTruth?.gate_open ? 'OPEN' : 'CLOSED', color: engineTruth?.gate_open ? THEME.success : THEME.error },
                  { id: 'freshness', label: 'Freshness', value: engineTruth?.freshness || 'Unknown', color: engineTruth?.freshness === 'Fresh' ? THEME.success : THEME.warning },
                  { id: 'minutes', label: 'Minutes Since PASS', value: String(engineTruth?.minutes_since_last_pass ?? '—'), color: THEME.cyan },
                ].map((item) => (
                  <View key={item.id} style={{ flex: 1, minWidth: 120, backgroundColor: (globalThis as any).__alphaColor(item.color, '10'), borderRadius: 12, padding: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(item.color, '25') }} data-testid={`executive-engine-run-metric-${item.id}`} testID={`executive-engine-run-metric-${item.id}`}>
                    <Text style={{ fontSize: 10, color: THEME.textMuted, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                    <Text style={{ fontSize: 16, color: item.color, fontWeight: '900', marginTop: 6 }} numberOfLines={1}>{item.value}</Text>
                  </View>
                ))}
              </View>

              <Text style={{ color: THEME.textMuted, fontSize: 11, marginTop: 12 }} data-testid="executive-engine-run-checked-at" testID="executive-engine-run-checked-at">
                Checked: {engineTruth?.checked_at ? new Date(engineTruth.checked_at).toLocaleString() : 'Unknown'}
              </Text>

              <TouchableOpacity onPress={() => router.push('/admin-console?category=operations&tab=autonomous-engine' as any)} style={{ marginTop: 12, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(THEME.primary, '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(THEME.primary, '30') }} data-testid="executive-open-engine-truth-button" testID="executive-open-engine-truth-button">
                <Text style={{ color: THEME.primary, fontSize: 12, fontWeight: '700' }}>Open Autonomous Engine</Text>
              </TouchableOpacity>
            </View>

            <View style={{ flex: 1, minWidth: 280, backgroundColor: THEME.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: THEME.border }} data-testid="executive-global-audit-status-card" testID="executive-global-audit-status-card">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <View>
                  <Text style={{ color: THEME.text, fontSize: 15, fontWeight: '800' }}>Global Audit Status</Text>
                  <Text style={{ color: THEME.textMuted, fontSize: 11, marginTop: 4 }}>Latest full-system audit snapshot surfaced directly for leadership.</Text>
                </View>
                <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: auditTruth?.status === 'PASS' ? 'var(--app-success-soft)' : 'var(--app-warning-soft)' }} data-testid="executive-global-audit-status-pill" testID="executive-global-audit-status-pill">
                  <Text style={{ color: auditTruth?.status === 'PASS' ? 'var(--app-success)' : 'var(--app-warning)', fontSize: 10, fontWeight: '800' }}>{auditTruth?.status || 'UNKNOWN'}</Text>
                </View>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 14 }}>
                {[
                  { id: 'report', label: 'Report', value: auditTruth?.report_id || '—', color: THEME.primary },
                  { id: 'confidence', label: 'Confidence', value: auditTruth?.confidence || 'UNKNOWN', color: auditTruth?.confidence === 'HIGH' ? THEME.success : THEME.warning },
                  { id: 'backend', label: 'Backend', value: auditTruth?.backend_success || 'N/A', color: THEME.cyan },
                  { id: 'frontend', label: 'Frontend', value: auditTruth?.frontend_success || 'N/A', color: THEME.purpleText },
                ].map((item) => (
                  <View key={item.id} style={{ flex: 1, minWidth: 120, backgroundColor: (globalThis as any).__alphaColor(item.color, '10'), borderRadius: 12, padding: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(item.color, '25') }} data-testid={`executive-global-audit-metric-${item.id}`} testID={`executive-global-audit-metric-${item.id}`}>
                    <Text style={{ fontSize: 10, color: THEME.textMuted, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                    <Text style={{ fontSize: 16, color: item.color, fontWeight: '900', marginTop: 6 }} numberOfLines={1} data-testid={`executive-global-audit-metric-${item.id}-value`} testID={`executive-global-audit-metric-${item.id}-value`}>{item.value}</Text>
                  </View>
                ))}
              </View>

              <Text style={{ color: THEME.textMuted, fontSize: 11, marginTop: 12 }} data-testid="executive-global-audit-checked-at" testID="executive-global-audit-checked-at">
                Checked: {auditTruth?.checked_at ? new Date(auditTruth.checked_at).toLocaleString() : 'Unknown'} · {auditTruth?.staleness_label || 'Unknown age'}
              </Text>
              <Text style={{ color: THEME.textSec, fontSize: 11, marginTop: 6, lineHeight: 18 }} data-testid="executive-global-audit-summary" testID="executive-global-audit-summary">
                {auditTruth?.summary || 'No audit summary available.'}
              </Text>

              <TouchableOpacity onPress={() => router.push('/admin-console?category=operations&tab=platform-health' as any)} style={{ marginTop: 12, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(THEME.cyan, '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(THEME.cyan, '30') }} data-testid="executive-open-global-audit-button" testID="executive-open-global-audit-button">
                <Text style={{ color: THEME.cyan, fontSize: 12, fontWeight: '700' }}>Open Platform Health</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      {/* Security Score Widget */}
      {activeSection === 'overview' && securityScore && (
        <View style={s.panel} data-testid="security-score-panel" testID="security-score-panel">
          <View style={s.panelHeader}>
            <Text style={s.panelTitle}>Security Posture</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
            <View style={{ alignItems: 'center', justifyContent: 'center', minWidth: 160, paddingVertical: 12 }}>
              <View style={{ width: 110, height: 110, borderRadius: 55, borderWidth: 6, borderColor: securityScore.score >= 75 ? 'var(--app-success)' : securityScore.score >= 50 ? 'var(--app-warning)' : 'var(--app-error)', alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor((securityScore.score >= 75 ? 'var(--app-success)' : securityScore.score >= 50 ? 'var(--app-warning)' : 'var(--app-error)'), '10') }}>
                <Text style={{ fontSize: 36, fontWeight: '900', color: securityScore.score >= 75 ? 'var(--app-success)' : securityScore.score >= 50 ? 'var(--app-warning)' : 'var(--app-error)' }}>{securityScore.score}</Text>
                <Text style={{ fontSize: 11, fontWeight: '700', color: THEME.textMuted }}>/ 100</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 }}>
                <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: securityScore.score >= 75 ? 'var(--app-success-soft)' : securityScore.score >= 50 ? 'var(--app-warning-soft)' : 'var(--app-error-soft)' }}>
                  <Text style={{ fontSize: 13, fontWeight: '800', color: securityScore.score >= 75 ? 'var(--app-success)' : securityScore.score >= 50 ? 'var(--app-warning)' : 'var(--app-error)' }}>Grade {securityScore.grade}</Text>
                </View>
                <Text style={{ fontSize: 12, fontWeight: '600', color: THEME.textSec }}>{securityScore.status}</Text>
              </View>
            </View>
            <View style={{ flex: 1, minWidth: 250 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10, paddingHorizontal: 4 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: THEME.text }}>Deduction Factors</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <Ionicons name={securityScore.trend_pct > 0 ? 'trending-up' : 'trending-down'} size={14} color={securityScore.trend_pct > 10 ? 'var(--app-error)' : 'var(--app-success)'} />
                  <Text style={{ fontSize: 11, fontWeight: '700', color: securityScore.trend_pct > 10 ? 'var(--app-error)' : 'var(--app-success)' }}>
                    {securityScore.trend_pct > 0 ? '+' : ''}{securityScore.trend_pct}% events vs prev week
                  </Text>
                </View>
              </View>
              {securityScore.factors?.map((f: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: i < securityScore.factors.length - 1 ? 1 : 0, borderBottomColor: THEME.border }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: f.severity === 'critical' ? 'var(--app-error)' : f.severity === 'high' ? 'var(--app-warning)' : 'var(--app-primary)' }} />
                  <Text style={{ flex: 1, fontSize: 12, fontWeight: '600', color: THEME.text }}>{f.label}</Text>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: THEME.textSec, width: 40, textAlign: 'right' }}>{f.value}</Text>
                  <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: f.impact > 0 ? 'var(--app-error-soft)' : 'var(--app-success-soft)', minWidth: 36, alignItems: 'center' }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: f.impact > 0 ? 'var(--app-error)' : 'var(--app-success)' }}>{f.impact > 0 ? `-${f.impact}` : '0'}</Text>
                  </View>
                </View>
              ))}
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 10, paddingTop: 8, borderTopWidth: 1, borderTopColor: THEME.border }}>
                <Text style={{ fontSize: 11, color: THEME.textMuted }}>Events this week: {securityScore.events_7d?.toLocaleString()}</Text>
                <Text style={{ fontSize: 11, color: THEME.textMuted }}>Previous week: {securityScore.events_prev_7d?.toLocaleString()}</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {/* Financial Intelligence */}
      {(activeSection === 'overview' || activeSection === 'financial') && financial && (
        <View style={s.panel} data-testid="financial-intelligence-panel" testID="financial-intelligence-panel">
          <View style={s.panelHeader}>
            <Text style={s.panelTitle}>Financial Intelligence</Text>
            <View style={s.periodTabs}>
              {['7d', '30d', '90d'].map(p => (
                <TouchableOpacity key={p} style={[s.periodTab, period === p && s.periodTabActive]} accessibilityLabel="Set period in exec overview section button" onPress={() => setPeriod(p)}>
                  <Text style={[s.periodLabel, period === p && s.periodLabelActive]}>{p}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
          <RevenueChart data={financial.revenue_timeline} />
          <RegionTable data={financial.revenue_by_region} />
          <View style={s.metricsRow}>
            <View style={s.metricBox}>
              <Text style={s.metricLabel}>Loan Default Rate</Text>
              <Text style={[s.metricValue, { color: financial.loan_default_rate > 3 ? THEME.error : THEME.success }]}>{financial.loan_default_rate}%</Text>
            </View>
            <View style={s.metricBox}>
              <Text style={s.metricLabel}>Cashback Payout</Text>
              <Text style={s.metricValue}>${financial.cashback_payout?.toLocaleString()}</Text>
            </View>
            <View style={s.metricBox}>
              <Text style={s.metricLabel}>Token Circulation</Text>
              <Text style={s.metricValue}>{financial.token_circulation?.toLocaleString()}</Text>
            </View>
            <View style={s.metricBox}>
              <Text style={s.metricLabel}>ProfitGuard Margin</Text>
              <Text style={[s.metricValue, { color: THEME.successText }]}>{financial.profit_guard_margin}%</Text>
            </View>
          </View>
        </View>
      )}

      {/* Risk Control */}
      {(activeSection === 'overview' || activeSection === 'risk') && risk && (
        <View style={s.panel}>
          <RiskPanel data={risk} onActionComplete={loadData} />
        </View>
      )}

      {/* Global Heatmap */}
      {activeSection === 'overview' && heatmap && (
        <View style={s.panel} data-testid="global-heatmap-panel" testID="global-heatmap-panel">
          <Text style={s.chartTitle}>Global Presence</Text>
          <View style={s.heatmapGrid}>
            {heatmap.regions?.map((r: any, i: number) => (
              <View key={i} style={s.heatmapCard}>
                <View style={s.heatmapHeader}>
                  <Text style={s.heatmapCode}>{r.code}</Text>
                  <Text style={s.heatmapName}>{r.name}</Text>
                </View>
                <Text style={s.heatmapRevenue}>${r.revenue.toLocaleString()}</Text>
                <View style={s.heatmapMeta}>
                  <Text style={s.heatmapUsers}>{r.users} users</Text>
                  {r.fraud_alerts > 0 && (
                    <View style={s.fraudAlertBadge}>
                      <Ionicons name="warning" size={10} color={THEME.error} />
                      <Text style={s.fraudAlertText}>{r.fraud_alerts}</Text>
                    </View>
                  )}
                </View>
                <Text style={s.heatmapTrending}>Trending: {r.trending}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
