import React from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getAdminColors, useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';

export function getExecTheme(AC: ReturnType<typeof getAdminColors>) {
  return {
    bg: 'transparent', bgSoft: AC.cardSoft, card: AC.card, cardHover: AC.surfaceHover,
    border: AC.border, text: AC.text, textSec: AC.textSec, textMuted: AC.textMuted,
    primary: AC.primary, primarySoft: AC.primarySoft, primaryText: AC.primaryText || AC.buttonText || AC.text,
    success: AC.success, successSoft: AC.successSoft,
    successText: AC.successText, warningText: AC.warningText, errorText: AC.errorText, orangeText: AC.orangeText,
    warning: AC.warning, warningSoft: AC.warningSoft, error: AC.error, errorSoft: AC.errorSoft,
    purple: AC.purple, purpleSoft: AC.purpleSoft, purpleText: AC.purpleText || AC.purple, cyan: AC.info, cyanSoft: AC.infoSoft,
    cardAlt: AC.cardSoft, textDim: AC.textMuted, brand: AC.primary, green: AC.success, indigo: AC.indigo || AC.primary, red: AC.error,
    pink: AC.purple, pinkSoft: AC.purpleSoft, orange: AC.orange, orangeSoft: AC.orangeSoft,
    teal: AC.primary, tealSoft: AC.primarySoft,
    overlay: AC.overlay,
  };
}

/** Dynamic theme hook — the only supported way to read exec-theme colors. */
export function useExecTheme() {
  const AC = useAdminTheme();
  return React.useMemo(() => getExecTheme(AC), [AC]);
}

const tx = (_key: string, fallback: string) => fallback;

const webGlass = Platform.OS === 'web' ? { backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' } : {};

/** Build the shared StyleSheet from live theme colors (light/dark aware). */
export function buildExecStyles(AC: ReturnType<typeof getAdminColors>) {
  const T = getExecTheme(AC);
  return StyleSheet.create({
    // ── Layout ──
    container: { flex: 1, backgroundColor: 'transparent', minHeight: '100vh' as any },
    mainLayout: { flex: 1, flexDirection: 'row' as const },
    sidebar: { width: 250, backgroundColor: AC.bgAlt, borderRightWidth: 1, borderRightColor: T.border, paddingVertical: 16, paddingHorizontal: 12, ...webGlass } as any,
    sidebarMobile: { position: 'absolute' as const, left: 0, top: 0, bottom: 0, zIndex: 100, width: 260 },
    sidebarBrand: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10, paddingHorizontal: 8, marginBottom: 20 },
    brandDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: T.primary },
    brandName: { color: T.text, fontSize: 16, fontWeight: '800' as const },
    brandSub: { color: T.textMuted, fontSize: 10, fontWeight: '600' as const },
    sidebarDivider: { height: 1, backgroundColor: T.border, marginVertical: 12 },
    sidebarSectionTitle: { color: T.textMuted, fontSize: 9, fontWeight: '800' as const, letterSpacing: 1.2, paddingHorizontal: 8, marginBottom: 8 },
    navItem: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 10, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 8, marginBottom: 2 },
    navItemActive: { backgroundColor: T.primarySoft },
    navLabel: { color: T.textSec, fontSize: 13, fontWeight: '500' as const },
    navLabelActive: { color: T.primary, fontWeight: '600' as const },
    activeIndicator: { width: 3, height: 16, backgroundColor: T.primary, borderRadius: 2, marginLeft: 'auto' as any },
    sidebarFooter: { paddingHorizontal: 8, paddingTop: 8, gap: 2 },
    footerText: { color: T.textMuted, fontSize: 10 },
    contentArea: { flex: 1, backgroundColor: 'transparent' },
    headerStrip: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, paddingHorizontal: 24, paddingVertical: 16, borderBottomWidth: 1, borderBottomColor: T.border, backgroundColor: AC.bgAlt, ...webGlass } as any,
    headerGreeting: { color: T.text, fontSize: 18, fontWeight: '700' as const },
    headerDate: { color: T.textMuted, fontSize: 12, marginTop: 2 },
    headerActions: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 12 },
    liveIndicator: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6, backgroundColor: T.successSoft, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20 },
    statusDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: T.success },
    statusText: { color: T.successText, fontSize: 11, fontWeight: '700' as const },
    refreshBtn: { width: 36, height: 36, borderRadius: 10, backgroundColor: T.bgSoft, alignItems: 'center' as const, justifyContent: 'center' as const, borderWidth: 1, borderColor: T.border },
    topBar: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, paddingHorizontal: 16, paddingVertical: 12, backgroundColor: AC.bgAlt, borderBottomWidth: 1, borderBottomColor: T.border, ...webGlass } as any,
    topBarTitle: { color: T.text, fontSize: 16, fontWeight: '700' as const },
    topBarRight: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6 },
    scrollContent: { flex: 1 },
    scrollInner: { padding: 24, gap: 20 },
    loadingWrap: { flex: 1, alignItems: 'center' as const, justifyContent: 'center' as const, paddingVertical: 100 },
    backBtn: { marginTop: 16, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: T.primary },
    // ── Content ──
    panel: { backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, ...webGlass } as any,
    panelHeader: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, marginBottom: 12 },
    panelTitle: { color: T.text, fontSize: 16, fontWeight: '700' as const },
    sectionHeader: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, marginBottom: 16 },
    sectionTitle: { color: T.text, fontSize: 20, fontWeight: '800' as const },
    lastUpdated: { color: T.textMuted, fontSize: 11 },
    kpiGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 12, marginBottom: 16 },
    summaryStrip: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 20, backgroundColor: T.bgSoft, padding: 12, borderRadius: 10 },
    summaryItem: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6 },
    summaryText: { color: T.textSec, fontSize: 12, fontWeight: '500' as const },
    periodTabs: { flexDirection: 'row' as const, gap: 4 },
    periodTab: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: T.bgSoft },
    periodTabActive: { backgroundColor: T.primarySoft },
    periodLabel: { color: T.textMuted, fontSize: 11, fontWeight: '600' as const },
    periodLabelActive: { color: T.primary },
    metricsRow: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 12, marginTop: 12 },
    metricBox: { backgroundColor: T.bgSoft, borderRadius: 10, padding: 14, minWidth: 140, flex: 1 },
    metricLabel: { color: T.textMuted, fontSize: 11, fontWeight: '600' as const },
    metricValue: { color: T.text, fontSize: 20, fontWeight: '800' as const, marginTop: 4 },
    heatmapGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 10 },
    heatmapCard: { backgroundColor: T.bgSoft, borderRadius: 10, padding: 12, minWidth: 150, flex: 1 },
    heatmapHeader: { flexDirection: 'row' as const, gap: 8, alignItems: 'center' as const, marginBottom: 8 },
    heatmapCode: { color: T.primary, fontSize: 14, fontWeight: '800' as const },
    heatmapName: { color: T.textSec, fontSize: 12 },
    heatmapRevenue: { color: T.text, fontSize: 18, fontWeight: '700' as const },
    heatmapMeta: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, marginTop: 6 },
    heatmapUsers: { color: T.textMuted, fontSize: 11 },
    fraudAlertBadge: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 3, backgroundColor: T.errorSoft, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
    fraudAlertText: { color: T.error, fontSize: 10, fontWeight: '700' as const },
    heatmapTrending: { color: T.textMuted, fontSize: 10, marginTop: 4, fontStyle: 'italic' as const },
    placeholderWrap: { alignItems: 'center' as const, paddingVertical: 40 },
    placeholderText: { color: T.textMuted, fontSize: 13, marginTop: 8 },
    planBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: 'flex-start' as const },
    planText: { fontSize: 11, fontWeight: '600' as const },
    // ── Shared component styles ──
    kpiCard: { backgroundColor: T.card, borderRadius: 14, padding: 14, flex: 1, minWidth: 150, borderWidth: 1, borderColor: T.border, ...webGlass } as any,
    kpiHeader: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, marginBottom: 10 },
    kpiIconWrap: { width: 34, height: 34, borderRadius: 10, alignItems: 'center' as const, justifyContent: 'center' as const },
    kpiChangeTag: { flexDirection: 'row' as const, alignItems: 'center' as const, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
    kpiValue: { color: T.text, fontSize: 22, fontWeight: '800' as const, marginBottom: 2 },
    kpiLabel: { color: T.textMuted, fontSize: 12, fontWeight: '500' as const },
    kpiFooter: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, marginTop: 8 },
    kpiWeekly: { color: T.textMuted, fontSize: 10, fontWeight: '500' as const },
    chartContainer: { backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border },
    chartTitle: { color: T.text, fontSize: 16, fontWeight: '700' as const, marginBottom: 12 },
    barChart: { flexDirection: 'row' as const, alignItems: 'flex-end' as const, justifyContent: 'space-between' as const, height: 140, gap: 2 },
    barGroup: { flex: 1, alignItems: 'center' as const },
    bar: { width: '80%' as any, borderRadius: 4, overflow: 'hidden' as const, justifyContent: 'flex-end' as const },
    barSegment: { width: '100%' as any, borderRadius: 2 },
    barLabel: { color: T.textMuted, fontSize: 9, marginTop: 4 },
    legendRow: { flexDirection: 'row' as const, gap: 16, marginTop: 12 },
    legendItem: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6 },
    legendDot: { width: 8, height: 8, borderRadius: 4 },
    legendText: { color: T.textMuted, fontSize: 11 },
    tableHeader: { flexDirection: 'row' as const, paddingVertical: 8, borderBottomWidth: 1, borderColor: T.border },
    th: { color: T.textMuted, fontSize: 11, fontWeight: '600' as const, textTransform: 'uppercase' as const },
    tableRow: { flexDirection: 'row' as const, paddingVertical: 10, borderBottomWidth: 1, borderColor: T.border },
    td: { color: T.textSec, fontSize: 13 },
    sectionLabel: { color: T.textSec, fontSize: 13, fontWeight: '600' as const, marginTop: 16, marginBottom: 8 },
    riskHeader: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, marginBottom: 12 },
    riskBadge: { flexDirection: 'row' as const, alignItems: 'center' as const, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10 },
    complianceRow: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 10 },
    complianceItem: { backgroundColor: T.bgSoft, borderLeftWidth: 3, borderRadius: 8, padding: 10, minWidth: 120 },
    complianceType: { color: T.text, fontSize: 12, fontWeight: '600' as const },
    complianceCount: { fontSize: 13, fontWeight: '700' as const, marginTop: 4 },
    amlGrid: { flexDirection: 'row' as const, flexWrap: 'wrap' as const, gap: 10 },
    amlItem: { backgroundColor: T.bgSoft, borderRadius: 10, padding: 12, minWidth: 90, alignItems: 'center' as const },
    amlValue: { color: T.text, fontSize: 20, fontWeight: '800' as const },
    amlLabel: { color: T.textMuted, fontSize: 10, marginTop: 4 },
    fraudTrend: { flexDirection: 'row' as const, alignItems: 'flex-end' as const, justifyContent: 'space-between' as const, height: 80 },
    fraudDay: { flex: 1, alignItems: 'center' as const },
    fraudBars: { flexDirection: 'row' as const, gap: 2, alignItems: 'flex-end' as const },
    fraudBar: { width: 6, borderRadius: 3 },
    fraudDate: { color: T.textMuted, fontSize: 9, marginTop: 4 },
    suspiciousRow: { flexDirection: 'row' as const, justifyContent: 'space-between' as const, alignItems: 'center' as const, backgroundColor: T.bgSoft, padding: 10, borderRadius: 8, marginBottom: 6 },
    suspiciousType: { color: T.text, fontSize: 13, fontWeight: '600' as const },
    suspiciousAmount: { color: T.textSec, fontSize: 12, marginTop: 2 },
    statusTag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
    capitalMetrics: { flexDirection: 'row' as const, gap: 12, marginBottom: 16, flexWrap: 'wrap' as const },
    capitalCard: { backgroundColor: T.bgSoft, borderRadius: 12, padding: 14, minWidth: 130, flex: 1 },
    capitalLabel: { color: T.textMuted, fontSize: 11, fontWeight: '600' as const },
    capitalValue: { color: T.text, fontSize: 22, fontWeight: '800' as const, marginTop: 6 },
    capitalSubtext: { color: T.textMuted, fontSize: 11, marginTop: 2 },
    fundingBars: { gap: 10 },
    fundingItem: { gap: 4 },
    fundingInfo: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8 },
    fundingLabel: { color: T.textSec, fontSize: 12, flex: 1 },
    fundingAmount: { color: T.text, fontSize: 12, fontWeight: '600' as const },
    fundingBarBg: { height: 8, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' as const },
    fundingBarFill: { height: '100%' as any, borderRadius: 4 },
    searchRow: { flexDirection: 'row' as const, alignItems: 'center' as const, marginBottom: 12, gap: 10 },
    searchBox: { flex: 1, flexDirection: 'row' as const, alignItems: 'center' as const, backgroundColor: T.bgSoft, borderRadius: 10, paddingHorizontal: 12, height: 40, borderWidth: 1, borderColor: T.border },
    searchInput: { flex: 1, color: T.text, marginLeft: 8, fontSize: 14 },
    totalCount: { color: T.textMuted, fontSize: 12, fontWeight: '600' as const },
    planTag: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, alignSelf: 'flex-start' as const },
    paginationRow: { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'center' as const, gap: 16, marginTop: 12 },
    pageBtn: { width: 32, height: 32, borderRadius: 8, backgroundColor: T.bgSoft, alignItems: 'center' as const, justifyContent: 'center' as const },
    pageText: { color: T.textSec, fontSize: 13, fontWeight: '600' as const },
  });
}

/** Dynamic StyleSheet hook — returns theme-aware styles (light/dark).
 *  Use inside components: `const s = useExecStyles();` */
export function useExecStyles() {
  const AC = useAdminTheme();
  return React.useMemo(() => buildExecStyles(AC), [AC]);
}

export function MiniSparkline({ data, color, width = 80, height = 28 }: { data: number[]; color: string; width?: number; height?: number }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(' ');

  return (
    <View style={{ width, height, opacity: 0.8 }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={points} />
        <polyline fill={`${color}15`} stroke="none" points={`0,${height} ${points} ${width},${height}`} />
      </svg>
    </View>
  );
}

export function KPICard({ kpi }: { kpi: any }) {
  const AC = useAdminTheme();
  const T = React.useMemo(() => getExecTheme(AC), [AC]);
  const styles = useExecStyles();
  const iconColorMap: Record<string, string> = {
    'trending-up': T.success, cash: T.primary, briefcase: T.purple,
    people: T.warning, card: T.cyan, wallet: T.pink,
    'swap-horizontal': T.teal, calculator: T.orange,
    'shield-checkmark': T.success, pulse: T.success,
  };
  const color = iconColorMap[kpi.icon] || T.primary;
  const isPositive = kpi.daily_change >= 0;
  return (
    <View style={[styles.kpiCard, { borderLeftColor: color, borderLeftWidth: 3, backgroundColor: AC.card, borderColor: AC.border }]} data-testid={`kpi-card-${kpi.id}`} testID={`kpi-card-${kpi.id}`}>
      <View style={styles.kpiHeader}>
        <View style={[styles.kpiIconWrap, { backgroundColor: (globalThis as any).__alphaColor(color, '18') }]}>
          <Ionicons name={kpi.icon as any} size={18} color={color} />
        </View>
        <View style={[styles.kpiChangeTag, { backgroundColor: isPositive ? T.successSoft : T.errorSoft }]}>
          <Ionicons name={isPositive ? 'arrow-up' : 'arrow-down'} size={10} color={isPositive ? T.success : T.error} />
          <Text style={{ color: isPositive ? T.success : T.error, fontSize: 11, fontWeight: '600', marginLeft: 2 }}>
            {Math.abs(kpi.daily_change)}%
          </Text>
        </View>
      </View>
      <Text style={[styles.kpiValue, { color: AC.text }]} data-testid={`kpi-value-${kpi.id}`} testID={`kpi-value-${kpi.id}`}>{kpi.value}</Text>
      <Text style={[styles.kpiLabel, { color: AC.textSec }]}>{kpi.label}</Text>
      <View style={styles.kpiFooter}>
        <MiniSparkline data={kpi.sparkline} color={color} />
        <Text style={[styles.kpiWeekly, { color: AC.textMuted }]}>{kpi.weekly_trend >= 0 ? '+' : ''}{kpi.weekly_trend}% / wk</Text>
      </View>
    </View>
  );
}

export function RevenueChart({ data }: { data: any[] }) {
  const AC = useAdminTheme();
  const T = React.useMemo(() => getExecTheme(AC), [AC]);
  const styles = useExecStyles();
  if (!data || data.length === 0) return null;
  const maxRev = Math.max(...data.map(d => d.revenue));
  return (
    <View style={styles.chartContainer} data-testid="revenue-chart" testID="revenue-chart">
      <Text style={styles.chartTitle}>{tx('admin.execDashboardPanels.auto.text.001', 'Revenue Timeline')}</Text>
      <View style={styles.barChart}>
        {data.slice(-14).map((d, i) => {
          const h = (d.revenue / maxRev) * 120;
          return (
            <View key={i} style={styles.barGroup}>
              <View style={[styles.bar, { height: h, backgroundColor: T.primary }]}>
                <View style={[styles.barSegment, { height: h * (d.streaming / d.revenue), backgroundColor: T.purple }]} />
              </View>
              <Text style={styles.barLabel}>{d.date.slice(5)}</Text>
            </View>
          );
        })}
      </View>
      <View style={styles.legendRow}>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: T.primary }]} /><Text style={styles.legendText}>{tx('admin.execDashboardPanels.auto.text.002', 'Total')}</Text></View>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: T.purple }]} /><Text style={styles.legendText}>{tx('admin.execDashboardPanels.auto.text.003', 'Streaming')}</Text></View>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: T.success }]} /><Text style={styles.legendText}>{tx('admin.execDashboardPanels.auto.text.004', 'Subscriptions')}</Text></View>
      </View>
    </View>
  );
}

export function RegionTable({ data }: { data: any[] }) {
  const AC = useAdminTheme();
  const T = React.useMemo(() => getExecTheme(AC), [AC]);
  const styles = useExecStyles();
  if (!data || data.length === 0) return null;
  return (
    <View style={styles.chartContainer} data-testid="region-table" testID="region-table">
      <Text style={styles.chartTitle}>{tx('admin.execDashboardPanels.auto.text.005', 'Revenue by Region')}</Text>
      <View style={styles.tableHeader}>
        <Text style={[styles.th, { flex: 2 }]}>{tx('admin.execDashboardPanels.auto.text.006', 'Region')}</Text>
        <Text style={[styles.th, { flex: 1.5 }]}>{tx('admin.execDashboardPanels.auto.text.007', 'Revenue')}</Text>
        <Text style={[styles.th, { flex: 1 }]}>{tx('admin.execDashboardPanels.auto.text.008', 'Users')}</Text>
        <Text style={[styles.th, { flex: 1 }]}>{tx('admin.execDashboardPanels.auto.text.009', 'Growth')}</Text>
      </View>
      {data.map((r, i) => (
        <View key={i} style={[styles.tableRow, i % 2 === 0 && { backgroundColor: T.bgSoft }]}>
          <Text style={[styles.td, { flex: 2, color: T.text }]}>{r.region}</Text>
          <Text style={[styles.td, { flex: 1.5 }]}>${r.revenue.toLocaleString()}</Text>
          <Text style={[styles.td, { flex: 1 }]}>{r.users}</Text>
          <Text style={[styles.td, { flex: 1, color: T.successText }]}>+{r.growth}%</Text>
        </View>
      ))}
    </View>
  );
}

export function RiskPanel({ data, onActionComplete }: { data: any; onActionComplete?: () => void }) {
  const AC = useAdminTheme();
  const T = React.useMemo(() => getExecTheme(AC), [AC]);
  const styles = useExecStyles();
  const [actionLoading, setActionLoading] = React.useState<string>('');
  if (!data) return null;

  const riskLabel = String(data.risk_level || 'Low');
  const riskTone = riskLabel.toLowerCase() === 'low' ? T.success : riskLabel.toLowerCase() === 'medium' ? T.warning : T.error;
  const riskSoft = riskLabel.toLowerCase() === 'low' ? T.successSoft : riskLabel.toLowerCase() === 'medium' ? T.warningSoft : T.errorSoft;

  const runRiskAction = async (action: string, userId: string) => {
    const actionKey = `${action}:${userId}`;
    setActionLoading(actionKey);
    try {
      await api.post('/admin/executive/risk-actions', {
        action,
        user_id: userId,
      });
      onActionComplete?.();
    } catch (e: any) {
      alert(e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Risk action failed');
    } finally {
      setActionLoading('');
    }
  };

  return (
    <View data-testid="risk-control-panel" testID="risk-control-panel">
      <View style={styles.riskHeader}>
        <Text style={styles.chartTitle}>{tx('admin.execDashboardPanels.auto.text.010', 'Risk Control Center')}</Text>
        <View style={[styles.riskBadge, { backgroundColor: riskSoft }]}>
          <Ionicons name={riskLabel.toLowerCase() === 'low' ? 'shield-checkmark' : 'warning'} size={14} color={riskTone} />
          <Text style={{ color: riskTone, fontWeight: '700', fontSize: 12, marginLeft: 4 }} data-testid="risk-overall-pill" testID="risk-overall-pill">
            Risk: {riskLabel} ({data.overall_risk_score})
          </Text>
        </View>
      </View>

      <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 12, marginBottom: 12 }} data-testid="risk-engine-output-block" testID="risk-engine-output-block">
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', marginBottom: 8 }} data-testid="risk-engine-status-title" testID="risk-engine-status-title">{tx('admin.execDashboardPanels.auto.text.011', 'Progressive Risk Engine Status')}</Text>
        <Text style={{ color: T.textSec, fontSize: 11, fontFamily: Platform.OS === 'web' ? 'monospace' as any : undefined, lineHeight: 18 }} data-testid="risk-engine-output-text" testID="risk-engine-output-text">
          {data.risk_engine?.output_block || 'RISK_ENGINE_STATUS: ACTIVE'}
        </Text>
      </View>

      <Text style={styles.sectionLabel}>{tx('admin.execDashboardPanels.auto.text.012', 'Progressive Actions')}</Text>
      <View style={{ gap: 6, marginBottom: 12 }}>
        {(data.risk_engine?.progressive_actions || []).map((line: string, idx: number) => (
          <View key={`${line}-${idx}`} style={{ backgroundColor: T.bgSoft, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8 }} data-testid={`risk-progressive-action-${idx}`} testID={`risk-progressive-action-${idx}`}>
            <Text style={{ color: T.textSec, fontSize: 11 }}>{line}</Text>
          </View>
        ))}
      </View>

      <Text style={styles.sectionLabel}>{tx('admin.execDashboardPanels.auto.text.013', 'Compliance Alerts')}</Text>
      <View style={styles.complianceRow}>
        {data.compliance_alerts?.map((a: any, i: number) => (
          <View key={i} style={[styles.complianceItem, { borderLeftColor: a.severity === 'high' ? T.error : a.severity === 'medium' ? T.warning : T.success }]}>
            <Text style={styles.complianceType}>{a.type}</Text>
            <Text style={[styles.complianceCount, { color: a.count > 0 ? T.warning : T.success }]}>{a.count} alerts</Text>
          </View>
        ))}
      </View>
      <Text style={styles.sectionLabel}>{tx('admin.execDashboardPanels.auto.text.014', 'AML Summary')}</Text>
      <View style={styles.amlGrid}>
        <View style={styles.amlItem}><Text style={styles.amlValue}>{data.aml_summary?.total_screened}</Text><Text style={styles.amlLabel}>{tx('admin.execDashboardPanels.auto.text.015', 'Screened')}</Text></View>
        <View style={styles.amlItem}><Text style={[styles.amlValue, { color: T.warningText }]}>{data.aml_summary?.flagged}</Text><Text style={styles.amlLabel}>{tx('admin.execDashboardPanels.auto.text.016', 'Flagged')}</Text></View>
        <View style={styles.amlItem}><Text style={[styles.amlValue, { color: T.successText }]}>{data.aml_summary?.cleared}</Text><Text style={styles.amlLabel}>{tx('admin.execDashboardPanels.auto.text.017', 'Cleared')}</Text></View>
        <View style={styles.amlItem}><Text style={[styles.amlValue, { color: T.orangeText }]}>{data.aml_summary?.pending_review}</Text><Text style={styles.amlLabel}>{tx('admin.execDashboardPanels.auto.text.018', 'Pending')}</Text></View>
      </View>
      <Text style={styles.sectionLabel}>{tx('admin.execDashboardPanels.auto.text.019', 'Fraud Trend (7 Days)')}</Text>
      <View style={styles.fraudTrend}>
        {data.fraud_trend?.map((f: any, i: number) => (
          <View key={i} style={styles.fraudDay}>
            <View style={styles.fraudBars}>
              <View style={[styles.fraudBar, { height: f.attempts * 4, backgroundColor: (globalThis as any).__alphaColor(T.error, '60') }]} />
              <View style={[styles.fraudBar, { height: f.blocked * 4, backgroundColor: (globalThis as any).__alphaColor(T.success, '80') }]} />
            </View>
            <Text style={styles.fraudDate}>{f.date.slice(5)}</Text>
          </View>
        ))}
      </View>
      <Text style={styles.sectionLabel}>{tx('admin.execDashboardPanels.auto.text.020', 'Suspicious Transactions')}</Text>
      {data.suspicious_transactions?.slice(0, 3).map((t: any, i: number) => (
        <View key={i} style={styles.suspiciousRow}>
          <View>
            <Text style={styles.suspiciousType}>{t.type}</Text>
            <Text style={styles.suspiciousAmount}>${t.amount.toLocaleString()}</Text>
          </View>
          <View style={[styles.statusTag, { backgroundColor: t.status === 'blocked' ? T.errorSoft : T.warningSoft }]}>
            <Text style={{ color: t.status === 'blocked' ? T.error : T.warning, fontSize: 11, fontWeight: '600' }}>{t.status}</Text>
          </View>
        </View>
      ))}

      <Text style={styles.sectionLabel}>{tx('admin.execDashboardPanels.auto.text.021', 'High-Risk Accounts')}</Text>
      {(data.high_risk_accounts || []).slice(0, 5).map((account: any, index: number) => {
        const level = String(account.risk_level || 'high').toLowerCase();
        const levelColor = level === 'critical' ? T.error : level === 'high' ? T.warning : T.success;
        const levelSoft = level === 'critical' ? T.errorSoft : level === 'high' ? T.warningSoft : T.successSoft;
        const lockKey = `lock_session:${account.user_id}`;
        const idvKey = `force_id_verification:${account.user_id}`;
        return (
          <View key={`${account.user_id}-${index}`} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10, marginBottom: 8 }} data-testid={`high-risk-account-${index}`} testID={`high-risk-account-${index}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', flex: 1 }} numberOfLines={1}>{account.email || account.user_id}</Text>
              <View style={{ backgroundColor: levelSoft, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
                <Text style={{ color: levelColor, fontSize: 10, fontWeight: '800' }} data-testid={`high-risk-level-${index}`} testID={`high-risk-level-${index}`}>
                  {level.toUpperCase()} · {account.risk_score}
                </Text>
              </View>
            </View>
            <Text style={{ color: T.textMuted, fontSize: 10, marginBottom: 8 }}>{account.reason}</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity
                accessibilityLabel={tx('admin.execDashboardPanels.auto.accessibility.001', 'Lock high-risk user session')}
                style={{ backgroundColor: T.errorSoft, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6 }}
                onPress={() => runRiskAction('lock_session', account.user_id)}
                disabled={actionLoading === lockKey}
                data-testid={`risk-lock-session-${index}`}
                testID={`risk-lock-session-${index}`}
              >
                <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{actionLoading === lockKey ? 'Locking...' : 'Lock Session'}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                accessibilityLabel={tx('admin.execDashboardPanels.auto.accessibility.002', 'Force user ID verification')}
                style={{ backgroundColor: T.warningSoft, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6 }}
                onPress={() => runRiskAction('force_id_verification', account.user_id)}
                disabled={actionLoading === idvKey}
                data-testid={`risk-force-idv-${index}`}
                testID={`risk-force-idv-${index}`}
              >
                <Text style={{ color: T.warning, fontSize: 10, fontWeight: '700' }}>{actionLoading === idvKey ? 'Triggering...' : 'Force ID Verification'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        );
      })}
    </View>
  );
}

export function UserManagement({ users, total, search, setSearch, page, setPage, pages }: any) {
  const AC = useAdminTheme();
  const T = React.useMemo(() => getExecTheme(AC), [AC]);
  const styles = useExecStyles();
  return (
    <View data-testid="user-management-panel" testID="user-management-panel">
      <Text style={styles.chartTitle}>{tx('admin.execDashboardPanels.auto.text.022', 'User Management')}</Text>
      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={16} color={T.textMuted} />
          <TextInput
            style={styles.searchInput}
            placeholder={tx('admin.execDashboardPanels.auto.placeholder.001', 'Search users...')}
            placeholderTextColor={T.textMuted}
            value={search}
            onChangeText={setSearch}
            data-testid="user-search-input" testID="user-search-input"
          />
        </View>
        <Text style={styles.totalCount}>{total} users</Text>
      </View>
      <View style={styles.tableHeader}>
        <Text style={[styles.th, { flex: 2 }]}>{tx('admin.execDashboardPanels.auto.text.023', 'User')}</Text>
        <Text style={[styles.th, { flex: 1.5 }]}>{tx('admin.execDashboardPanels.auto.text.024', 'Email')}</Text>
        <Text style={[styles.th, { flex: 1 }]}>{tx('admin.execDashboardPanels.auto.text.025', 'Role')}</Text>
        <Text style={[styles.th, { flex: 1 }]}>{tx('admin.execDashboardPanels.auto.text.026', 'Plan')}</Text>
      </View>
      {users.map((u: any, i: number) => (
        <View key={u.user_id || i} style={[styles.tableRow, i % 2 === 0 && { backgroundColor: T.bgSoft }]} data-testid={`user-row-${i}`} testID={`user-row-${i}`}>
          <Text style={[styles.td, { flex: 2, color: T.text }]}>{u.name || 'N/A'}</Text>
          <Text style={[styles.td, { flex: 1.5 }]}>{u.email}</Text>
          <Text style={[styles.td, { flex: 1 }]}>{u.role || 'user'}</Text>
          <View style={{ flex: 1 }}>
            <View style={[styles.planTag, { backgroundColor: u.subscription_plan === 'premium' ? T.warningSoft : u.subscription_plan === 'basic' ? T.primarySoft : T.bgSoft }]}>
              <Text style={{ fontSize: 11, fontWeight: '600', color: u.subscription_plan === 'premium' ? T.warning : u.subscription_plan === 'basic' ? T.primary : T.textMuted }}>
                {u.subscription_plan || 'free'}
              </Text>
            </View>
          </View>
        </View>
      ))}
      {pages > 1 && (
        <View style={styles.paginationRow}>
          <TouchableOpacity disabled={page <= 1} accessibilityLabel={tx('admin.execDashboardPanels.auto.accessibility.003', 'chevron back button')} onPress={() => setPage(page - 1)} style={[styles.pageBtn, page <= 1 && { opacity: 0.3 }]}>
            <Ionicons name="chevron-back" size={16} color={T.text} />
          </TouchableOpacity>
          <Text style={styles.pageText}>{page} / {pages}</Text>
          <TouchableOpacity disabled={page >= pages} accessibilityLabel={tx('admin.execDashboardPanels.auto.accessibility.004', 'chevron forward button')} onPress={() => setPage(page + 1)} style={[styles.pageBtn, page >= pages && { opacity: 0.3 }]}>
            <Ionicons name="chevron-forward" size={16} color={T.text} />
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
