import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput, StyleSheet, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type Tab = 'overview' | 'responses' | 'ai-analysis' | 'auto-improve' | 'digest' | 'heatmaps';

// Shared StyleSheet hook — used by the main panel AND its sub-components.
// Sub-components reference `cs.*` keys at render time, so they MUST call this
// hook themselves (can't close over a `cs` defined inside the main component).
function useTicketIntelStyles() {
  const colors = useAdminTheme();
  return React.useMemo(() => StyleSheet.create({
    root: { flex: 1, padding: 0 },
    header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16, flexWrap: 'wrap', gap: 12 },
    title: { fontSize: 22, fontWeight: '800', color: colors.text, letterSpacing: -0.5 },
    subtitle: { fontSize: 13, color: colors.textSec, marginTop: 2 },
    periodBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
    periodActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
    periodText: { fontSize: 12, fontWeight: '600', color: colors.textMuted },
    periodTextActive: { color: colors.primary },
    tabRow: { flexDirection: 'row', gap: 4, marginBottom: 20, borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: 0 },
    tabBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: 'transparent' },
    tabActive: { borderBottomColor: colors.primary },
    tabText: { fontSize: 13, fontWeight: '600', color: colors.textMuted },
    tabTextActive: { color: colors.primary },
    grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 },
    gridDesktop: {},
    statCard: { backgroundColor: colors.card, borderRadius: 12, padding: 16, borderWidth: 1, minWidth: 160, flex: 1 },
    statIcon: { width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
    statLabel: { fontSize: 12, color: colors.textSec, fontWeight: '600' },
    statValue: { fontSize: 28, fontWeight: '800', marginTop: 8, letterSpacing: -1 },
    statSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
    chartsRow: { gap: 12, marginBottom: 16 },
    chartCard: { backgroundColor: colors.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border },
    miniTitle: { fontSize: 13, fontWeight: '700', color: colors.text, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 },
    distContainer: {},
    distRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
    distLabel: { fontSize: 12, color: colors.textSec, width: 14, textAlign: 'right', fontWeight: '600' },
    distBarBg: { flex: 1, height: 8, backgroundColor: colors.border, borderRadius: 4, overflow: 'hidden' },
    distBarFill: { height: '100%', borderRadius: 4 },
    distCount: { fontSize: 11, color: colors.textMuted, width: 28, textAlign: 'right' },
    heatContainer: {},
    heatRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: `${colors.border}50` },
    heatDot: { width: 8, height: 8, borderRadius: 4 },
    heatLabel: { flex: 1, fontSize: 12, color: colors.text, fontWeight: '500', textTransform: 'capitalize' },
    heatScore: { fontSize: 13, fontWeight: '700', width: 32, textAlign: 'right' },
    heatCount: { fontSize: 11, color: colors.textMuted, width: 32 },
    heatCsat: { fontSize: 11, fontWeight: '700', width: 36, textAlign: 'right' },
    trendContainer: { alignItems: 'center' },
    priRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
    priBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
    priBadgeText: { fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
    priAvg: { fontSize: 13, fontWeight: '700', color: colors.text },
    priCount: { fontSize: 11, color: colors.textMuted },
    filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 12, alignItems: 'center' },
    searchBox: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: 10, flex: 1, minWidth: 200 },
    searchInput: { flex: 1, paddingVertical: 8, fontSize: 13, color: colors.text, outlineStyle: 'none' as any },
    filterChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
    filterChipActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
    filterChipText: { fontSize: 11, fontWeight: '600', color: colors.textMuted },
    filterChipTextActive: { color: colors.primary },
    exportBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
    exportText: { fontSize: 11, fontWeight: '700' },
    responseCount: { fontSize: 12, color: colors.textMuted, marginBottom: 8 },
    responseCard: { backgroundColor: colors.card, borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: colors.border },
    ticketNum: { fontSize: 12, fontWeight: '700', color: colors.primary, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined },
    catBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
    catBadgeText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
    responseSubject: { fontSize: 13, fontWeight: '600', color: colors.text, marginTop: 6 },
    responseComment: { fontSize: 12, color: colors.textSec, fontStyle: 'italic', marginTop: 4, lineHeight: 18 },
    responseMeta: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
    responseMetaText: { fontSize: 11, color: colors.textMuted },
    pagination: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 16, paddingVertical: 12 },
    pageBtn: { padding: 8, borderRadius: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border },
    pageInfo: { fontSize: 12, color: colors.textSec, fontWeight: '600' },
    aiEmptyState: { alignItems: 'center', paddingVertical: 40, gap: 12 },
    aiEmptyTitle: { fontSize: 18, fontWeight: '700', color: colors.text },
    aiEmptyDesc: { fontSize: 13, color: colors.textSec, textAlign: 'center', maxWidth: 480, lineHeight: 20 },
    aiRunBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.purple, paddingHorizontal: 20, paddingVertical: 12, borderRadius: 10, marginTop: 8 },
    aiRunBtnText: { fontSize: 14, fontWeight: '700', color: colors.primaryText },
    healthScoreCard: { backgroundColor: colors.card, borderRadius: 12, padding: 20, borderWidth: 1, borderColor: colors.border, alignItems: 'center', marginBottom: 16 },
    healthLabel: { fontSize: 12, fontWeight: '700', color: colors.textSec, textTransform: 'uppercase', letterSpacing: 1 },
    healthValue: { fontSize: 48, fontWeight: '900', marginVertical: 4, letterSpacing: -2 },
    healthSummary: { fontSize: 13, color: colors.textSec, textAlign: 'center', lineHeight: 20, maxWidth: 500 },
    sentimentCard: { backgroundColor: colors.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border, marginBottom: 16 },
    sentPct: { fontSize: 20, fontWeight: '800', marginTop: 4 },
    sentLabel: { fontSize: 11, color: colors.textMuted, textTransform: 'capitalize' },
    sectionCard: { backgroundColor: colors.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border, marginBottom: 16 },
    painRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: `${colors.border}50` },
    sevBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
    sevText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
    painIssue: { fontSize: 13, fontWeight: '600', color: colors.text },
    painCat: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
    recRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: `${colors.border}50` },
    recAction: { fontSize: 13, fontWeight: '600', color: colors.text },
    recImpact: { fontSize: 11, color: colors.textSec, marginTop: 2 },
    strengthRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 6 },
    strengthText: { fontSize: 13, fontWeight: '600', color: colors.text },
    strengthEvidence: { fontSize: 11, color: colors.textSec, marginTop: 2 },
    improveCard: { backgroundColor: `${colors.card}`, borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: `${colors.success}30` },
    improveTitle: { fontSize: 14, fontWeight: '700', color: colors.text },
    improveDesc: { fontSize: 12, color: colors.textSec, marginTop: 4, lineHeight: 18 },
    improveImpact: { fontSize: 11, color: colors.successText, marginTop: 4, fontWeight: '600' },
    typeBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
    typeBadgeText: { fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
    histRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: `${colors.border}50` },
    histTitle: { flex: 1, fontSize: 12, color: colors.text },
    histDate: { fontSize: 11, color: colors.textMuted },
    toggleTrack: { width: 44, height: 24, borderRadius: 12, backgroundColor: colors.border, justifyContent: 'center', padding: 2 },
    toggleTrackOn: { backgroundColor: colors.success },
    toggleThumb: { width: 20, height: 20, borderRadius: 10, backgroundColor: colors.primaryText },
    toggleThumbOn: { alignSelf: 'flex-end' as any },
  }), [colors]);
}

// ── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, icon, color, trend }: { label: string; value: string | number; sub?: string; icon: string; color: string; trend?: number }) {
  const T = useExecTheme();
  const cs = useTicketIntelStyles();
  return (
    <View style={[cs.statCard, { borderColor: `${color}30` }]} data-testid={`stat-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`stat-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <View style={[cs.statIcon, { backgroundColor: `${color}15` }]}>
          <Ionicons name={icon as any} size={18} color={color} />
        </View>
        <Text style={cs.statLabel}>{label}</Text>
      </View>
      <Text style={[cs.statValue, { color }]}>{value}</Text>
      {sub && <Text style={cs.statSub}>{sub}</Text>}
      {trend !== undefined && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 }}>
          <Ionicons name={trend >= 0 ? 'trending-up' : 'trending-down'} size={12} color={trend >= 0 ? T.success : T.error} />
          <Text style={{ fontSize: 11, color: trend >= 0 ? T.success : T.error, fontWeight: '600' }}>{trend > 0 ? '+' : ''}{trend}%</Text>
        </View>
      )}
    </View>
  );
}

// ── Rating Stars ─────────────────────────────────────────────────────────────
function Stars({ rating }: { rating: number }) {
  const T = useExecTheme();
  return (
    <View style={{ flexDirection: 'row', gap: 2 }}>
      {[1, 2, 3, 4, 5].map(i => (
        <Ionicons key={i} name={i <= rating ? 'star' : 'star-outline'} size={14} color={i <= rating ? T.warning : T.textMuted} />
      ))}
    </View>
  );
}

// ── Distribution Bar ─────────────────────────────────────────────────────────
function DistributionBar({ distribution }: { distribution: Record<string, number> }) {
  const T = useExecTheme();
  const cs = useTicketIntelStyles();
  const total = Object.values(distribution).reduce((a, b) => a + b, 0);
  return (
    <View style={cs.distContainer}>
      <Text style={cs.miniTitle}>{tx('admin.ticketFeedbackIntelPanel.auto.text.001', 'Rating Distribution')}</Text>
      {[5, 4, 3, 2, 1].map((star, idx) => {
        const count = distribution[String(star)] || 0;
        const pct = total > 0 ? (count / total) * 100 : 0;
        return (
          <View key={star} style={cs.distRow} data-testid={`dist-${star}-star`} testID={`dist-${star}-star`}>
            <Text style={cs.distLabel}>{star}</Text>
            <Ionicons name="star" size={11} color={T.warning} />
            <View style={cs.distBarBg}>
              <View style={[cs.distBarFill, { width: `${pct}%`, backgroundColor: [T.error, T.orange || T.warning, T.warning, T.successText, T.success][5 - star] || T.primary }]} />
            </View>
            <Text style={cs.distCount}>{count}</Text>
          </View>
        );
      })}
    </View>
  );
}

// ── Category Heatmap ─────────────────────────────────────────────────────────
function CategoryHeatmap({ data }: { data: Record<string, { avg: number; count: number; csat: number }> }) {
  const T = useExecTheme();
  const cs = useTicketIntelStyles();
  const entries = Object.entries(data).sort((a, b) => b[1].count - a[1].count);
  return (
    <View style={cs.heatContainer}>
      <Text style={cs.miniTitle}>{tx('admin.ticketFeedbackIntelPanel.auto.text.002', 'Satisfaction by Category')}</Text>
      {entries.map(([cat, v]) => {
        const hue = v.avg >= 4 ? T.success : v.avg >= 3 ? T.warning : T.error;
        return (
          <View key={cat} style={cs.heatRow} data-testid={`cat-${cat}`} testID={`cat-${cat}`}>
            <View style={[cs.heatDot, { backgroundColor: hue }]} />
            <Text style={cs.heatLabel}>{cat.replace(/_/g, ' ')}</Text>
            <Text style={[cs.heatScore, { color: hue }]}>{v.avg.toFixed(1)}</Text>
            <Text style={cs.heatCount}>({v.count})</Text>
            <Text style={[cs.heatCsat, { color: v.csat >= 70 ? T.success : v.csat >= 50 ? T.warning : T.error }]}>{v.csat}%</Text>
          </View>
        );
      })}
    </View>
  );
}

// ── Trend Chart (SVG) ────────────────────────────────────────────────────────
function TrendChart({ trend }: { trend: { month: string; avg: number; count: number }[] }) {
  const T = useExecTheme();
  const cs = useTicketIntelStyles();
  if (!trend || trend.length < 2) return null;
  const W = 320, H = 100, PAD = 20;
  const maxAvg = Math.max(...trend.map(t => t.avg), 5);
  const minAvg = Math.min(...trend.map(t => t.avg), 0);
  const range = maxAvg - minAvg || 1;
  const points = trend.map((t, i) => {
    const x = PAD + (i / (trend.length - 1)) * (W - 2 * PAD);
    const y = PAD + (1 - (t.avg - minAvg) / range) * (H - 2 * PAD);
    return `${x},${y}`;
  }).join(' ');
  return (
    <View style={cs.trendContainer} data-testid="trend-chart" testID="trend-chart">
      <Text style={cs.miniTitle}>{tx('admin.ticketFeedbackIntelPanel.auto.text.003', 'Rating Trend')}</Text>
      <svg width={W} height={H + 20} viewBox={`0 0 ${W} ${H + 20}`}>
        {[1, 2, 3, 4, 5].map(v => {
          const y = PAD + (1 - (v - minAvg) / range) * (H - 2 * PAD);
          return <line key={v} x1={PAD} y1={y} x2={W - PAD} y2={y} stroke={T.border} strokeWidth="0.5" />;
        })}
        <polyline fill="none" stroke={T.primary} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" points={points} />
        <polyline fill={`${T.primary}12`} stroke="none" points={`${PAD},${H - PAD} ${points} ${W - PAD},${H - PAD}`} />
        {trend.map((t, i) => {
          const x = PAD + (i / (trend.length - 1)) * (W - 2 * PAD);
          const y = PAD + (1 - (t.avg - minAvg) / range) * (H - 2 * PAD);
          return (
            <React.Fragment key={i}>
              <circle cx={x} cy={y} r="4" fill={T.primary} stroke={T.card} strokeWidth="2" />
              <text x={x} y={H + 14} textAnchor="middle" fill={T.textMuted} fontSize="9">{t.month.slice(5)}</text>
            </React.Fragment>
          );
        })}
      </svg>
    </View>
  );
}

// ── Main Panel ───────────────────────────────────────────────────────────────
export default function TicketFeedbackIntelPanel({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const cs = useTicketIntelStyles();
  const T = useExecTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const panelTitle = t('ticketFeedbackIntel.header.title');
  const panelSubtitle = t('ticketFeedbackIntel.header.subtitle');
  const [tab, setTab] = useState<Tab>('overview');
  const [period, setPeriod] = useState('all');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [filterRating, setFilterRating] = useState<number | null>(null);
  const [filterCat] = useState('');
  const [exporting, setExporting] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState<any>(null);
  const [improveLoading, setImproveLoading] = useState(false);
  const [improvements, setImprovements] = useState<any[]>([]);
  const [improvementHistory, setImprovementHistory] = useState<any[]>([]);
  const [digestConfig, setDigestConfig] = useState<any>(null);
  const [digestLoading, setDigestLoading] = useState(false);
  const [digestSending, setDigestSending] = useState(false);
  const [heatmapData, setHeatmapData] = useState<any>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [alertConfig, setAlertConfig] = useState<any>(null);
  const [alertConfigLoading, setAlertConfigLoading] = useState(false);
  const [alertHistory, setAlertHistory] = useState<any[]>([]);
  const [alertHistoryLoading, setAlertHistoryLoading] = useState(false);
  const [summaryConfig, setSummaryConfig] = useState<any>(null);
  const [summaryConfigLoading, setSummaryConfigLoading] = useState(false);
  const [sendingNow, setSendingNow] = useState(false);
  const [drillDown, setDrillDown] = useState<any>(null);
  const [drillDownLoading, setDrillDownLoading] = useState(false);
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const { data: analytics, loading: analyticsLoading } = useLiveQuery(`/admin/ticket-feedback/analytics?period=${period}`, { entity: 'ticket-feedback', pollInterval: 30000 });
  const { data: responsesData, loading: responsesLoading, refetch: refetchResponses } = useLiveQuery(
    `/admin/ticket-feedback/responses?page=${page}&limit=15${filterRating ? `&rating=${filterRating}` : ''}${filterCat ? `&category=${filterCat}` : ''}${search ? `&search=${encodeURIComponent(search)}` : ''}`,
    { entity: 'ticket-feedback-responses', pollInterval: 60000 }
  );

  const handleExport = useCallback(async (format: 'csv' | 'pdf') => {
    setExporting(format);
    try {
      if (format === 'csv') {
        const resp = await api.get(`/admin/ticket-feedback/export/csv${filterRating ? `?rating=${filterRating}` : ''}${filterCat ? `${filterRating ? '&' : '?'}category=${filterCat}` : ''}`);
        if (Platform.OS === 'web') {
          const blob = new Blob([resp.data], { type: 'text/csv' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url; a.download = `ticket_feedback_${new Date().toISOString().slice(0, 10)}.csv`;
          a.click(); URL.revokeObjectURL(url);
        }
      } else {
        const resp = await api.get('/admin/ticket-feedback/export/pdf');
        const d = resp.data;
        if (Platform.OS === 'web') {
          const content = `TICKET FEEDBACK REPORT\nGenerated: ${new Date(d.generated_at).toLocaleString()}\n\nSummary: ${d.summary.total} responses | Avg: ${d.summary.avg_rating}/5 | CSAT: ${d.summary.csat_pct}%\n\n${d.rows.map((r: any) => `${r.ticket} | ${r.subject} | ${r.rating}/5 | ${r.comment}`).join('\n')}`;
          const blob = new Blob([content], { type: 'text/plain' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url; a.download = `ticket_feedback_report_${new Date().toISOString().slice(0, 10)}.txt`;
          a.click(); URL.revokeObjectURL(url);
        }
      }
    } catch (e) { console.error('Export failed', e); }
    setExporting('');
  }, [filterRating, filterCat]);

  const runAiAnalysis = useCallback(async () => {
    setAiLoading(true);
    try {
      const resp = await api.get('/admin/ticket-feedback/ai-analysis');
      setAiAnalysis(resp.data);
    } catch (e) { console.error('AI analysis failed', e); }
    setAiLoading(false);
  }, []);

  const runAutoImprove = useCallback(async () => {
    setImproveLoading(true);
    try {
      const resp = await api.post('/admin/ticket-feedback/ai-auto-improve');
      setImprovements(resp.data.actions || []);
      // Refresh history
      const hist = await api.get('/admin/ticket-feedback/improvements?limit=50');
      setImprovementHistory(hist.data.improvements || []);
    } catch (e) { console.error('Auto-improve failed', e); }
    setImproveLoading(false);
  }, []);

  const loadImprovementHistory = useCallback(async () => {
    try {
      const resp = await api.get('/admin/ticket-feedback/improvements?limit=50');
      setImprovementHistory(resp.data.improvements || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const loadDigestConfig = useCallback(async () => {
    try {
      const resp = await api.get('/admin/ticket-feedback/digest/config');
      setDigestConfig(resp.data);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const toggleDigest = useCallback(async (enabled: boolean) => {
    setDigestLoading(true);
    try {
      const resp = await api.put('/admin/ticket-feedback/digest/config', { enabled, frequency: digestConfig?.frequency || 'weekly' });
      setDigestConfig((prev: any) => ({ ...prev, ...resp.data }));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setDigestLoading(false);
  }, [digestConfig]);

  const changeFrequency = useCallback(async (frequency: string) => {
    setDigestLoading(true);
    try {
      const resp = await api.put('/admin/ticket-feedback/digest/config', { enabled: digestConfig?.enabled ?? true, frequency });
      setDigestConfig((prev: any) => ({ ...prev, ...resp.data }));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setDigestLoading(false);
  }, [digestConfig]);

  const sendDigestNow = useCallback(async () => {
    setDigestSending(true);
    try {
      await api.post('/admin/ticket-feedback/digest/send-now');
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setDigestSending(false);
    loadDigestConfig();
  }, [loadDigestConfig]);

  const responses = responsesData?.responses || [];
  const totalPages = responsesData?.pages || 1;
  const totalResponses = responsesData?.total || 0;

  // Heatmap data
  useEffect(() => {
    if (tab !== 'heatmaps') return;
    setHeatmapLoading(true);
    api.get(`/admin/ticket-feedback/heatmap-data?period=${period}`)
      .then(r => { if (r.data?.ok) setHeatmapData(r.data); })
      .catch(() => {})
      .finally(() => setHeatmapLoading(false));
    // Also load alert config + history
    setAlertConfigLoading(true);
    api.get('/admin/ticket-feedback/sentiment-alerts/config')
      .then(r => setAlertConfig(r.data))
      .catch(() => {})
      .finally(() => setAlertConfigLoading(false));
    setAlertHistoryLoading(true);
    api.get('/admin/ticket-feedback/sentiment-alerts/history')
      .then(r => setAlertHistory(r.data?.alerts || []))
      .catch(() => {})
      .finally(() => setAlertHistoryLoading(false));
    // Load weekly summary config
    setSummaryConfigLoading(true);
    api.get('/admin/ticket-feedback/sentiment-summary/config')
      .then(r => setSummaryConfig(r.data))
      .catch(() => {})
      .finally(() => setSummaryConfigLoading(false));
  }, [tab, period]);

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'overview', label: tx('ticketFeedbackIntel.tabs.overview', 'Overview'), icon: 'grid' },
    { id: 'responses', label: tx('ticketFeedbackIntel.tabs.feedback', 'Feedback'), icon: 'chatbox-ellipses' },
    { id: 'ai-analysis', label: tx('ticketFeedbackIntel.tabs.aiAnalysis', 'AI Analysis'), icon: 'bulb' },
    { id: 'auto-improve', label: tx('ticketFeedbackIntel.tabs.autoImprove', 'Auto-Improve'), icon: 'flash' },
    { id: 'digest', label: tx('ticketFeedbackIntel.tabs.emailDigest', 'Email Digest'), icon: 'mail' },
    { id: 'heatmaps', label: tx('ticketFeedbackIntel.tabs.heatmaps', 'Heatmaps'), icon: 'flame' },
  ];

  return (
    <View style={cs.root} data-testid="ticket-feedback-intel-panel" testID="ticket-feedback-intel-panel">
      {/* Header */}
      <View style={cs.header}>
        <View style={{ flex: 1 }}>
          <Text style={cs.title}>{panelTitle === 'ticketFeedbackIntel.header.title' ? 'Ticket Feedback Intelligence' : panelTitle}</Text>
          <Text style={cs.subtitle}>{panelSubtitle === 'ticketFeedbackIntel.header.subtitle' ? 'Analyze, understand, and auto-improve from user support feedback' : panelSubtitle}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {['7d', '30d', '90d', 'all'].map(p => (
            <TouchableOpacity key={p} onPress={() => setPeriod(p)} style={[cs.periodBtn, period === p && cs.periodActive]} data-testid={`period-${p}`} testID={`period-${p}`}>
              <Text style={[cs.periodText, period === p && cs.periodTextActive]}>{p === 'all' ? tx('ticketFeedbackIntel.period.all', 'All') : p}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Tabs */}
      <View style={cs.tabRow}>
        {tabs.map(t => (
          <TouchableOpacity key={t.id} onPress={() => { setTab(t.id); if (t.id === 'auto-improve') loadImprovementHistory(); if (t.id === 'digest') loadDigestConfig(); }}
            style={[cs.tabBtn, tab === t.id && cs.tabActive]} data-testid={`tab-${t.id}`} testID={`tab-${t.id}`}>
            <Ionicons name={t.icon as any} size={16} color={tab === t.id ? T.primary : T.textMuted} />
            <Text style={[cs.tabText, tab === t.id && cs.tabTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Tab Content */}
      {tab === 'overview' && (
        <View data-testid="overview-tab" testID="overview-tab">
          {analyticsLoading ? <ActivityIndicator size="large" color={T.primary} style={{ marginTop: 40 }} /> : analytics && (
            <>
              {/* KPI Row */}
              <View style={[cs.grid, isDesktop && cs.gridDesktop]}>
                <StatCard label={tx('ticketFeedbackIntel.kpis.totalFeedback', 'Total Feedback')} value={analytics.total_feedback} sub={tx('ticketFeedbackIntel.kpis.responseRate', '{rate}% response rate').replace('{rate}', String(analytics.response_rate))} icon="chatbubbles" color={T.primary} />
                <StatCard label={tx('ticketFeedbackIntel.kpis.avgRating', 'Avg Rating')} value={`${analytics.avg_rating}/5`} sub={tx('ticketFeedbackIntel.kpis.fromResponses', 'From {count} responses').replace('{count}', String(analytics.period_feedback))} icon="star" color={T.warningText} />
                <StatCard label={tx('ticketFeedbackIntel.kpis.csatScore', 'CSAT Score')} value={`${analytics.csat_pct}%`} sub={tx('ticketFeedbackIntel.kpis.ratedFourOrFive', 'Rated 4 or 5 stars')} icon="happy" color={analytics.csat_pct >= 70 ? T.success : analytics.csat_pct >= 50 ? T.warning : T.error} />
                <StatCard label={tx('ticketFeedbackIntel.kpis.nps', 'NPS')} value={analytics.nps} sub={analytics.nps >= 0 ? tx('ticketFeedbackIntel.kpis.positiveSentiment', 'Positive sentiment') : tx('ticketFeedbackIntel.kpis.needsImprovement', 'Needs improvement')} icon="pulse" color={analytics.nps >= 0 ? T.success : T.error} />
                <StatCard label={tx('ticketFeedbackIntel.kpis.resolutionTime', 'Resolution Time')} value={`${analytics.avg_resolution_hours}h`} sub={tx('ticketFeedbackIntel.kpis.avgTimeResolve', 'Avg time to resolve')} icon="time" color={T.cyan} />
                <StatCard label={tx('ticketFeedbackIntel.kpis.totalResolved', 'Total Resolved')} value={analytics.total_resolved} sub={tx('ticketFeedbackIntel.kpis.totalRated', '{count} rated').replace('{count}', String(analytics.total_feedback))} icon="checkmark-circle" color={T.successText} />
              </View>

              {/* Charts Row */}
              <View style={[cs.chartsRow, isDesktop && { flexDirection: 'row' }]}>
                <View style={[cs.chartCard, isDesktop && { flex: 1 }]}>
                  <DistributionBar distribution={analytics.distribution || {}} />
                </View>
                <View style={[cs.chartCard, isDesktop && { flex: 1.5 }]}>
                  <TrendChart trend={analytics.trend || []} />
                </View>
              </View>

              {/* Category + Priority */}
              <View style={[cs.chartsRow, isDesktop && { flexDirection: 'row' }]}>
                <View style={[cs.chartCard, isDesktop && { flex: 1 }]}>
                  <CategoryHeatmap data={analytics.category_breakdown || {}} />
                </View>
                <View style={[cs.chartCard, isDesktop && { flex: 1 }]}>
                  <Text style={cs.miniTitle}>{tx('ticketFeedbackIntel.priority.title', 'By Priority')}</Text>
                  {Object.entries(analytics.priority_breakdown || {}).sort((a: any, b: any) => b[1].count - a[1].count).map(([pri, v]: [string, any]) => (
                    <View key={pri} style={cs.priRow}>
                      <View style={[cs.priBadge, { backgroundColor: pri === 'urgent' ? T.errorSoft : pri === 'high' ? T.warningSoft : pri === 'medium' ? T.primarySoft : T.successSoft }]}>
                        <Text style={[cs.priBadgeText, { color: pri === 'urgent' ? T.error : pri === 'high' ? T.warning : pri === 'medium' ? T.primary : T.success }]}>{pri}</Text>
                      </View>
                      <Text style={cs.priAvg}>{v.avg.toFixed(1)}/5</Text>
                      <Text style={cs.priCount}>{tx('ticketFeedbackIntel.priority.reviews', '{count} reviews').replace('{count}', String(v.count))}</Text>
                    </View>
                  ))}
                </View>
              </View>
            </>
          )}
        </View>
      )}

      {tab === 'responses' && (
        <View data-testid="responses-tab" testID="responses-tab">
          {/* Filters */}
          <View style={cs.filterRow}>
            <View style={cs.searchBox}>
              <Ionicons name="search" size={16} color={T.textMuted} />
              <TextInput
                style={cs.searchInput}
                placeholder={tx('ticketFeedbackIntel.responses.searchPlaceholder', 'Search feedback...')}
                placeholderTextColor={T.textMuted}
                value={search}
                onChangeText={setSearch}
                onSubmitEditing={() => { setPage(1); refetchResponses(); }}
                data-testid="search-input" testID="search-input"
              />
            </View>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              {[null, 5, 4, 3, 2, 1].map(r => (
                <TouchableOpacity key={r ?? 'all'} onPress={() => { setFilterRating(r); setPage(1); }}
                  style={[cs.filterChip, filterRating === r && cs.filterChipActive]} data-testid={`filter-rating-${r ?? 'all'}`} testID={`filter-rating-${r ?? 'all'}`}>
                  <Text style={[cs.filterChipText, filterRating === r && cs.filterChipTextActive]}>
                    {r ? `${r}★` : tx('ticketFeedbackIntel.period.all', 'All')}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity onPress={() => handleExport('csv')} style={cs.exportBtn} disabled={!!exporting} data-testid="export-csv-btn" testID="export-csv-btn">
                {exporting === 'csv' ? <ActivityIndicator size="small" color={T.successText} /> : <Ionicons name="download" size={14} color={T.successText} />}
                <Text style={[cs.exportText, { color: T.successText }]}>{tx('admin.ticketFeedbackIntelPanel.auto.text.004', 'CSV')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => handleExport('pdf')} style={cs.exportBtn} disabled={!!exporting} data-testid="export-pdf-btn" testID="export-pdf-btn">
                {exporting === 'pdf' ? <ActivityIndicator size="small" color={T.error} /> : <Ionicons name="document" size={14} color={T.error} />}
                <Text style={[cs.exportText, { color: T.error }]}>{tx('admin.ticketFeedbackIntelPanel.auto.text.005', 'PDF')}</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Responses List */}
          <Text style={cs.responseCount}>{tx('ticketFeedbackIntel.responses.count', '{count} feedback responses').replace('{count}', String(totalResponses))}</Text>
          {responsesLoading ? <ActivityIndicator size="large" color={T.primary} style={{ marginTop: 20 }} /> : (
            <>
              {responses.map((r: any, idx: number) => (
                <View key={r.submission_id || idx} style={cs.responseCard} data-testid={`response-${idx}`} testID={`response-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Text style={cs.ticketNum}>{r.ticket_number}</Text>
                      <View style={[cs.catBadge, { backgroundColor: `${T.primary}15` }]}>
                        <Text style={[cs.catBadgeText, { color: T.primary }]}>{(r.category || '').replace(/_/g, ' ')}</Text>
                      </View>
                      <View style={[cs.catBadge, {
                        backgroundColor: r.priority === 'urgent' ? T.errorSoft : r.priority === 'high' ? T.warningSoft : T.primarySoft
                      }]}>
                        <Text style={[cs.catBadgeText, {
                          color: r.priority === 'urgent' ? T.error : r.priority === 'high' ? T.warning : T.primary
                        }]}>{r.priority}</Text>
                      </View>
                    </View>
                    <Stars rating={r.satisfaction?.rating || 0} />
                  </View>
                  <Text style={cs.responseSubject} numberOfLines={1}>{r.subject}</Text>
                  {r.satisfaction?.comment && <Text style={cs.responseComment}>"{r.satisfaction.comment}"</Text>}
                  <View style={cs.responseMeta}>
                    <Text style={cs.responseMetaText}>{r.user_name || tx('ticketFeedbackIntel.responses.anonymous', 'Anonymous')}</Text>
                    <Text style={cs.responseMetaText}>{r.satisfaction?.rated_at ? new Date(r.satisfaction.rated_at).toLocaleDateString() : ''}</Text>
                  </View>
                </View>
              ))}
              {/* Pagination */}
              <View style={cs.pagination}>
                <TouchableOpacity accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.001', 'chevron back button')} onPress={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} style={[cs.pageBtn, page <= 1 && { opacity: 0.3 }]}>
                  <Ionicons name="chevron-back" size={16} color={T.text} />
                </TouchableOpacity>
                <Text style={cs.pageInfo}>{tx('ticketFeedbackIntel.responses.pageOf', 'Page {page} of {total}').replace('{page}', String(page)).replace('{total}', String(totalPages))}</Text>
                <TouchableOpacity accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.002', 'chevron forward button')} onPress={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} style={[cs.pageBtn, page >= totalPages && { opacity: 0.3 }]}>
                  <Ionicons name="chevron-forward" size={16} color={T.text} />
                </TouchableOpacity>
              </View>
            </>
          )}
        </View>
      )}

      {tab === 'ai-analysis' && (
        <View data-testid="ai-analysis-tab" testID="ai-analysis-tab">
          {!aiAnalysis && !aiLoading && (
            <View style={cs.aiEmptyState}>
              <Ionicons name="bulb" size={48} color={T.purpleText} />
              <Text style={cs.aiEmptyTitle}>{tx('ticketFeedbackIntel.ai.title', 'AI-Powered Feedback Analysis')}</Text>
              <Text style={cs.aiEmptyDesc}>{tx('ticketFeedbackIntel.ai.subtitle', 'Get deep insights from your ticket feedback — recurring themes, pain points, strengths, and actionable recommendations.')}</Text>
              <TouchableOpacity onPress={runAiAnalysis} style={cs.aiRunBtn} data-testid="run-ai-analysis-btn" testID="run-ai-analysis-btn">
                <Ionicons name="sparkles" size={18} color={colors.primaryText} />
                <Text style={cs.aiRunBtnText}>{tx('ticketFeedbackIntel.ai.generate', 'Generate Analysis')}</Text>
              </TouchableOpacity>
            </View>
          )}
          {aiLoading && (
            <View style={cs.aiEmptyState}>
              <ActivityIndicator size="large" color={T.purpleText} />
              <Text style={[cs.aiEmptyTitle, { marginTop: 16 }]}>{tx('ticketFeedbackIntel.ai.analyzing', 'Analyzing feedback patterns...')}</Text>
            </View>
          )}
          {aiAnalysis && !aiLoading && (
            <>
              {/* Health Score */}
              <View style={cs.healthScoreCard} data-testid="health-score" testID="health-score">
                <Text style={cs.healthLabel}>{tx('ticketFeedbackIntel.ai.healthScore', 'Support Health Score')}</Text>
                <Text style={[cs.healthValue, { color: (aiAnalysis.health_score || 0) >= 70 ? T.success : (aiAnalysis.health_score || 0) >= 50 ? T.warning : T.error }]}>
                  {aiAnalysis.health_score || 0}/100
                </Text>
                <Text style={cs.healthSummary}>{aiAnalysis.summary}</Text>
              </View>

              {/* Sentiment */}
              {aiAnalysis.sentiment_breakdown && (
                <View style={cs.sentimentCard}>
                  <Text style={cs.miniTitle}>{tx('ticketFeedbackIntel.ai.sentimentBreakdown', 'Sentiment Breakdown')}</Text>
                  <View style={{ flexDirection: 'row', gap: 16, marginTop: 8 }}>
                    {[
                      { key: 'positive', color: T.successText, icon: 'happy' },
                      { key: 'neutral', color: T.warningText, icon: 'remove-circle' },
                      { key: 'negative', color: T.error, icon: 'sad' },
                    ].map(s => (
                      <View key={s.key} style={{ alignItems: 'center', flex: 1 }}>
                        <Ionicons name={s.icon as any} size={22} color={s.color} />
                        <Text style={[cs.sentPct, { color: s.color }]}>{aiAnalysis.sentiment_breakdown[s.key] || 0}%</Text>
                        <Text style={cs.sentLabel}>{s.key}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              )}

              {/* Pain Points */}
              {aiAnalysis.pain_points?.length > 0 && (
                <View style={cs.sectionCard}>
                  <Text style={cs.miniTitle}>{tx('ticketFeedbackIntel.ai.painPoints', 'Pain Points')}</Text>
                  {aiAnalysis.pain_points.map((p: any, i: number) => (
                    <View key={i} style={cs.painRow}>
                      <View style={[cs.sevBadge, { backgroundColor: p.severity === 'critical' ? T.errorSoft : p.severity === 'high' ? T.warningSoft : T.primarySoft }]}>
                        <Text style={[cs.sevText, { color: p.severity === 'critical' ? T.error : p.severity === 'high' ? T.warning : T.primary }]}>{p.severity}</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={cs.painIssue}>{p.issue}</Text>
                        {p.category && <Text style={cs.painCat}>{p.category}</Text>}
                      </View>
                    </View>
                  ))}
                </View>
              )}

              {/* Recommendations */}
              {aiAnalysis.recommendations?.length > 0 && (
                <View style={cs.sectionCard}>
                  <Text style={cs.miniTitle}>{tx('ticketFeedbackIntel.ai.recommendations', 'Recommendations')}</Text>
                  {aiAnalysis.recommendations.map((r: any, i: number) => (
                    <View key={i} style={cs.recRow}>
                      <View style={[cs.priBadge, { backgroundColor: r.priority === 'P0' ? T.errorSoft : r.priority === 'P1' ? T.warningSoft : T.successSoft }]}>
                        <Text style={[cs.priBadgeText, { color: r.priority === 'P0' ? T.error : r.priority === 'P1' ? T.warning : T.success }]}>{r.priority}</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={cs.recAction}>{r.action}</Text>
                        {r.impact && <Text style={cs.recImpact}>{r.impact}</Text>}
                      </View>
                    </View>
                  ))}
                </View>
              )}

              {/* Strengths */}
              {aiAnalysis.strengths?.length > 0 && (
                <View style={cs.sectionCard}>
                  <Text style={cs.miniTitle}>{tx('ticketFeedbackIntel.ai.strengths', 'Strengths')}</Text>
                  {aiAnalysis.strengths.map((s: any, i: number) => (
                    <View key={i} style={cs.strengthRow}>
                      <Ionicons name="checkmark-circle" size={16} color={T.successText} />
                      <View style={{ flex: 1 }}>
                        <Text style={cs.strengthText}>{s.strength}</Text>
                        {s.evidence && <Text style={cs.strengthEvidence}>{s.evidence}</Text>}
                      </View>
                    </View>
                  ))}
                </View>
              )}

              <TouchableOpacity onPress={runAiAnalysis} style={[cs.aiRunBtn, { alignSelf: 'center', marginTop: 16 }]} data-testid="refresh-analysis-btn" testID="refresh-analysis-btn">
                <Ionicons name="refresh" size={16} color={colors.primaryText} />
                <Text style={cs.aiRunBtnText}>{tx('ticketFeedbackIntel.ai.refresh', 'Refresh Analysis')}</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      )}

      {tab === 'auto-improve' && (
        <View data-testid="auto-improve-tab" testID="auto-improve-tab">
          <View style={cs.aiEmptyState}>
            <Ionicons name="flash" size={48} color={T.warningText} />
            <Text style={cs.aiEmptyTitle}>{tx('ticketFeedbackIntel.autoImprove.title', 'AI Auto-Improvement Engine')}</Text>
            <Text style={cs.aiEmptyDesc}>{tx('ticketFeedbackIntel.autoImprove.subtitle', 'Automatically generates and executes 100% safe improvements based on feedback patterns. No manual intervention required.')}</Text>
            <TouchableOpacity onPress={runAutoImprove} style={[cs.aiRunBtn, { backgroundColor: T.warning }]} disabled={improveLoading} data-testid="run-auto-improve-btn" testID="run-auto-improve-btn">
              {improveLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="flash" size={18} color={colors.primaryText} />}
              <Text style={cs.aiRunBtnText}>{improveLoading ? tx('ticketFeedbackIntel.autoImprove.generating', 'Generating...') : tx('ticketFeedbackIntel.autoImprove.run', 'Run Auto-Improve')}</Text>
            </TouchableOpacity>
          </View>

          {/* Current Actions */}
          {improvements.length > 0 && (
            <View style={cs.sectionCard}>
              <Text style={cs.miniTitle}>Actions Executed ({improvements.length})</Text>
              {improvements.map((a: any, i: number) => (
                <View key={i} style={cs.improveCard} data-testid={`improvement-${i}`} testID={`improvement-${i}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <View style={[cs.typeBadge, { backgroundColor: T.successSoft }]}>
                      <Text style={[cs.typeBadgeText, { color: T.successText }]}>{(a.type || '').replace(/_/g, ' ')}</Text>
                    </View>
                    <View style={[cs.typeBadge, { backgroundColor: T.primarySoft }]}>
                      <Text style={[cs.typeBadgeText, { color: T.primary }]}>{a.confidence || 0}% confidence</Text>
                    </View>
                    <Ionicons name="checkmark-circle" size={16} color={T.successText} />
                  </View>
                  <Text style={cs.improveTitle}>{a.title}</Text>
                  <Text style={cs.improveDesc}>{a.description}</Text>
                  {a.impact && <Text style={cs.improveImpact}>{a.impact}</Text>}
                </View>
              ))}
            </View>
          )}

          {/* History */}
          {improvementHistory.length > 0 && (
            <View style={cs.sectionCard}>
              <Text style={cs.miniTitle}>Improvement History ({improvementHistory.length})</Text>
              {improvementHistory.slice(0, 20).map((h: any, i: number) => (
                <View key={i} style={cs.histRow}>
                  <Ionicons name="checkmark-done" size={14} color={T.successText} />
                  <Text style={cs.histTitle}>{h.title}</Text>
                  <Text style={cs.histDate}>{h.executed_at ? new Date(h.executed_at).toLocaleDateString() : ''}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {tab === 'digest' && (
        <View data-testid="digest-tab" testID="digest-tab">
          <View style={cs.aiEmptyState}>
            <Ionicons name="mail" size={48} color={T.primary} />
            <Text style={cs.aiEmptyTitle}>{tx('admin.ticketFeedbackIntelPanel.auto.text.006', 'Automated Feedback Digest')}</Text>
            <Text style={cs.aiEmptyDesc}>{tx('admin.ticketFeedbackIntelPanel.auto.text.007', 'Receive periodic email digests with key feedback metrics, category insights, and AI improvement actions — delivered straight to your inbox.')}</Text>
          </View>

          <View style={[cs.sectionCard, { maxWidth: 500, alignSelf: 'center', width: '100%' }]}>
            <Text style={cs.miniTitle}>{tx('admin.ticketFeedbackIntelPanel.auto.text.008', 'Digest Settings')}</Text>

            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: `${T.border}50` }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 14, fontWeight: '600', color: T.text }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.009', 'Enable Digest Emails')}</Text>
                <Text style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.010', 'Send automated reports to all admin accounts')}</Text>
              </View>
              <TouchableOpacity onPress={() => toggleDigest(!digestConfig?.enabled)} disabled={digestLoading}
                style={[cs.toggleTrack, digestConfig?.enabled && cs.toggleTrackOn]} data-testid="digest-toggle" testID="digest-toggle">
                <View style={[cs.toggleThumb, digestConfig?.enabled && cs.toggleThumbOn]} />
              </TouchableOpacity>
            </View>

            <View style={{ paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: `${T.border}50` }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: T.text, marginBottom: 8 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.011', 'Frequency')}</Text>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {['weekly', 'monthly'].map(f => (
                  <TouchableOpacity key={f} onPress={() => changeFrequency(f)}
                    style={[cs.periodBtn, digestConfig?.frequency === f && cs.periodActive]}
                    disabled={digestLoading} data-testid={`digest-freq-${f}`} testID={`digest-freq-${f}`}>
                    <Text style={[cs.periodText, digestConfig?.frequency === f && cs.periodTextActive]}>
                      {f === 'weekly' ? 'Weekly (Mon 9:30 UTC)' : 'Monthly (1st of month)'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            {digestConfig?.last_sent && (
              <View style={{ paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: `${T.border}50` }}>
                <Text style={{ fontSize: 12, color: T.textMuted }}>Last sent: {new Date(digestConfig.last_sent).toLocaleString()}</Text>
              </View>
            )}

            <View style={{ paddingTop: 16, alignItems: 'center' }}>
              <TouchableOpacity onPress={sendDigestNow} disabled={digestSending}
                style={[cs.aiRunBtn, { backgroundColor: T.primary }]} data-testid="send-digest-now-btn" testID="send-digest-now-btn">
                {digestSending ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="send" size={16} color={colors.primaryText} />}
                <Text style={cs.aiRunBtnText}>{digestSending ? 'Sending...' : 'Send Digest Now'}</Text>
              </TouchableOpacity>
              <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 8 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.012', 'Sends immediately to all admin emails')}</Text>
            </View>
          </View>
        </View>
      )}

      {/* ── Heatmaps Tab ── */}
      {tab === 'heatmaps' && (
        <View data-testid="feedback-heatmaps-tab" testID="feedback-heatmaps-tab">
          {heatmapLoading ? (
            <View style={{ alignItems: 'center', paddingVertical: 40 }}>
              <ActivityIndicator size="large" color={T.primary} />
              <Text style={{ color: T.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.013', 'Loading heatmap data...')}</Text>
            </View>
          ) : !heatmapData ? (
            <View style={{ alignItems: 'center', paddingVertical: 40 }}>
              <Ionicons name="flame-outline" size={40} color={T.textMuted} />
              <Text style={{ color: T.textMuted, fontSize: 14, marginTop: 12 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.014', 'No heatmap data available yet')}</Text>
            </View>
          ) : (
            <View style={{ gap: 16 }}>
              {/* ── Response Time Heatmap: day-of-week x hour ── */}
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="rt-heatmap-card" testID="rt-heatmap-card">
                <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 4 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.015', 'Response Time Heatmap')}</Text>
                <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 14 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.016', 'Avg resolution hours by day-of-week and time-of-day')}</Text>
                {Platform.OS === 'web' && (() => {
                  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
                  const HOURS = Array.from({ length: 24 }, (_, i) => i);
                  const gridMap: Record<string, { avg_hours: number; count: number }> = {};
                  let maxHours = 0;
                  (heatmapData.response_time_heatmap || []).forEach((e: any) => {
                    gridMap[`${e.day}-${e.hour}`] = e;
                    if (e.avg_hours > maxHours) maxHours = e.avg_hours;
                  });
                  const rtColor = (h: number) => {
                    if (!maxHours) return T.border;
                    const ratio = h / maxHours;
                    if (ratio < 0.25) return colors.success;
                    if (ratio < 0.5) return colors.warning;
                    if (ratio < 0.75) return colors.orange;
                    return colors.error;
                  };
                  const cellW = Math.max(18, Math.min(28, (isDesktop ? 700 : 320) / 26));
                  const cellH = cellW;
                  return (
                    <View style={{ overflowX: 'auto' } as any}>
                      <View style={{ flexDirection: 'row' }}>
                        <View style={{ width: 36 }} />
                        {HOURS.filter((_, i) => i % 3 === 0).map(h => (
                          <Text key={h} style={{ width: cellW * 3, fontSize: 9, color: T.textMuted, textAlign: 'center' }}>
                            {h === 0 ? '12a' : h < 12 ? `${h}a` : h === 12 ? '12p' : `${h - 12}p`}
                          </Text>
                        ))}
                      </View>
                      {DAYS.map((day, d) => (
                        <View key={day} style={{ flexDirection: 'row', alignItems: 'center' }}>
                          <Text style={{ width: 36, fontSize: 10, color: T.textSec, fontWeight: '600' }}>{day}</Text>
                          {HOURS.map(h => {
                            const cell = gridMap[`${d}-${h}`];
                            return (
                              <TouchableOpacity accessibilityLabel="Cell in ticket feedback intel panel"
                                key={h}
                                onPress={() => {
                                  if (!cell) return;
                                  setDrillDownLoading(true);
                                  setDrillDown({ day: d, day_name: day, hour: h, loading: true, tickets: [], count: 0, avg_hours: cell.avg_hours });
                                  api.get(`/admin/ticket-feedback/heatmap-drill-down?day=${d}&hour=${h}&period=${period}`)
                                    .then(r => { if (r.data?.ok) setDrillDown(r.data); })
                                    .catch(() => {})
                                    .finally(() => setDrillDownLoading(false));
                                }}
                                style={{
                                  width: cellW, height: cellH, borderRadius: 3, margin: 1,
                                  backgroundColor: cell ? rtColor(cell.avg_hours) : `${T.border}30`,
                                  alignItems: 'center', justifyContent: 'center',
                                  ...(cell ? { cursor: 'pointer' } as any : {}),
                                }}
                                testID={`rt-cell-${d}-${h}`}
                                accessibilityLabel={cell ? `${day} ${h}:00 ${cell.avg_hours}h avg ${cell.count} tickets` : tx('admin.ticketFeedbackIntelPanel.auto.accessibility.003', `${day} ${h}:00 No data`)}
                              >
                                {cell && cellW >= 22 && (
                                  <Text style={{ fontSize: 7, color: colors.primaryText, fontWeight: '700' }}>{Math.round(cell.avg_hours)}</Text>
                                )}
                              </TouchableOpacity>
                            );
                          })}
                        </View>
                      ))}
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, justifyContent: 'center' }}>
                        <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.017', 'Fast')}</Text>
                        {[colors.success, colors.warning, colors.orange, colors.error].map(c => (
                          <View key={c} style={{ width: 16, height: 10, borderRadius: 2, backgroundColor: c }} />
                        ))}
                        <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.018', 'Slow')}</Text>
                      </View>
                      <Text style={{ fontSize: 10, color: T.primary, textAlign: 'center', marginTop: 6, opacity: 0.7 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.019', 'Click any colored cell to see contributing tickets')}</Text>
                    </View>
                  );
                })()}

                {/* ── Drill-Down Panel ── */}
                {drillDown && (
                  <View style={{ backgroundColor: `${T.border}15`, borderRadius: 12, padding: 14, marginTop: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '40') }} data-testid="drill-down-panel" testID="drill-down-panel">
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <Ionicons name="search" size={16} color={T.primary} />
                        <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>
                          {drillDown.day_name} {drillDown.hour_label || `${drillDown.hour}:00`}
                        </Text>
                        <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(T.primary, '20') }}>
                          <Text style={{ fontSize: 10, fontWeight: '700', color: T.primary }}>{drillDown.count} ticket{drillDown.count !== 1 ? 's' : ''}</Text>
                        </View>
                        {drillDown.avg_hours > 0 && (
                          <Text style={{ fontSize: 10, color: T.textMuted }}>avg {drillDown.avg_hours}h</Text>
                        )}
                      </View>
                      <TouchableOpacity onPress={() => setDrillDown(null)} data-testid="drill-down-close" testID="drill-down-close">
                        <Ionicons name="close-circle" size={20} color={T.textMuted} />
                      </TouchableOpacity>
                    </View>
                    {drillDownLoading ? (
                      <ActivityIndicator size="small" color={T.primary} />
                    ) : drillDown.tickets?.length === 0 ? (
                      <Text style={{ fontSize: 12, color: T.textMuted, textAlign: 'center', paddingVertical: 8 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.020', 'No tickets found for this time slot')}</Text>
                    ) : (
                      <View>
                        {/* Table header */}
                        <View style={{ flexDirection: 'row', paddingBottom: 6, borderBottomWidth: 1, borderBottomColor: `${T.border}40`, marginBottom: 4 }}>
                          <Text style={{ flex: 1, fontSize: 9, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase' }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.021', 'Ticket')}</Text>
                          <Text style={{ flex: 2, fontSize: 9, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase' }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.022', 'Subject')}</Text>
                          <Text style={{ flex: 1, fontSize: 9, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase' }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.023', 'Category')}</Text>
                          <Text style={{ width: 50, fontSize: 9, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.024', 'Hours')}</Text>
                          <Text style={{ width: 40, fontSize: 9, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', textAlign: 'center' }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.025', 'Rating')}</Text>
                        </View>
                        {(drillDown.tickets || []).slice(0, 15).map((t: any, i: number) => {
                          const rtColor = t.resolution_hours < 24 ? colors.success : t.resolution_hours < 48 ? colors.warning : colors.error;
                          const ratingColor = t.rating >= 4 ? colors.success : t.rating === 3 ? colors.warning : colors.error;
                          return (
                            <View key={t.ticket_number || i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: i < Math.min((drillDown.tickets || []).length, 15) - 1 ? 1 : 0, borderBottomColor: `${T.border}20` }} data-testid={`drill-ticket-${i}`} testID={`drill-ticket-${i}`}>
                              <Text style={{ flex: 1, fontSize: 10, color: T.primary, fontWeight: '600' }}>{t.ticket_number}</Text>
                              <View style={{ flex: 2 }}>
                                <Text style={{ fontSize: 11, color: T.text }} numberOfLines={1}>{t.subject}</Text>
                                {t.feedback ? <Text style={{ fontSize: 9, color: T.textMuted, marginTop: 1 }} numberOfLines={1}>"{t.feedback}"</Text> : null}
                              </View>
                              <Text style={{ flex: 1, fontSize: 10, color: T.textSec, textTransform: 'capitalize' }}>{(t.category || '').replace(/_/g, ' ')}</Text>
                              <View style={{ width: 50, alignItems: 'center' }}>
                                <Text style={{ fontSize: 11, fontWeight: '700', color: rtColor }}>{t.resolution_hours}h</Text>
                              </View>
                              <View style={{ width: 40, alignItems: 'center' }}>
                                <Text style={{ fontSize: 11, fontWeight: '700', color: ratingColor }}>{t.rating}/5</Text>
                              </View>
                            </View>
                          );
                        })}
                      </View>
                    )}
                  </View>
                )}
              </View>

              {/* ── Sentiment by Category ── */}
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="sentiment-category-card" testID="sentiment-category-card">
                <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 4 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.026', 'Sentiment by Category')}</Text>
                <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 14 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.027', 'Positive / Neutral / Negative distribution per category')}</Text>
                {Object.entries(heatmapData.sentiment_by_category || {}).map(([cat, v]: [string, any]) => {
                  const barH = 18;
                  return (
                    <View key={cat} style={{ marginBottom: 10 }} data-testid={`sentiment-cat-${cat}`} testID={`sentiment-cat-${cat}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                        <Text style={{ fontSize: 12, fontWeight: '600', color: T.text, textTransform: 'capitalize' }}>{cat.replace(/_/g, ' ')}</Text>
                        <Text style={{ fontSize: 11, color: T.textMuted }}>{v.avg_rating}/5 ({v.count} tickets)</Text>
                      </View>
                      <View style={{ flexDirection: 'row', height: barH, borderRadius: barH / 2, overflow: 'hidden', backgroundColor: `${T.border}30` }}>
                        {v.positive > 0 && (
                          <View style={{ width: `${v.positive}%` as any, backgroundColor: colors.success, alignItems: 'center', justifyContent: 'center' }}>
                            {v.positive >= 15 && <Text style={{ fontSize: 8, color: colors.primaryText, fontWeight: '700' }}>{v.positive}%</Text>}
                          </View>
                        )}
                        {v.neutral > 0 && (
                          <View style={{ width: `${v.neutral}%` as any, backgroundColor: colors.warning, alignItems: 'center', justifyContent: 'center' }}>
                            {v.neutral >= 15 && <Text style={{ fontSize: 8, color: colors.primaryText, fontWeight: '700' }}>{v.neutral}%</Text>}
                          </View>
                        )}
                        {v.negative > 0 && (
                          <View style={{ width: `${v.negative}%` as any, backgroundColor: colors.error, alignItems: 'center', justifyContent: 'center' }}>
                            {v.negative >= 15 && <Text style={{ fontSize: 8, color: colors.primaryText, fontWeight: '700' }}>{v.negative}%</Text>}
                          </View>
                        )}
                      </View>
                    </View>
                  );
                })}
                <View style={{ flexDirection: 'row', gap: 16, marginTop: 8, justifyContent: 'center' }}>
                  {[{ label: 'Positive', color: colors.successText }, { label: 'Neutral', color: colors.warningText }, { label: 'Negative', color: colors.error }].map(l => (
                    <View key={l.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: l.color }} />
                      <Text style={{ fontSize: 10, color: T.textMuted }}>{l.label}</Text>
                    </View>
                  ))}
                </View>
              </View>

              {/* ── Response Time by Category ── */}
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="rt-category-card" testID="rt-category-card">
                <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 4 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.028', 'Response Time by Category')}</Text>
                <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 14 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.029', 'Avg / P95 resolution hours per category')}</Text>
                {(() => {
                  const cats = Object.entries(heatmapData.response_time_by_category || {});
                  const maxAvg = Math.max(...cats.map(([, v]: [string, any]) => v.p95_hours || v.avg_hours), 1);
                  return cats.map(([cat, v]: [string, any]) => {
                    const avgPct = (v.avg_hours / maxAvg) * 100;
                    const p95Pct = ((v.p95_hours || v.avg_hours) / maxAvg) * 100;
                    const barColor = v.avg_hours < 24 ? colors.success : v.avg_hours < 48 ? colors.warning : colors.error;
                    return (
                      <View key={cat} style={{ marginBottom: 10 }} data-testid={`rt-cat-${cat}`} testID={`rt-cat-${cat}`}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
                          <Text style={{ fontSize: 12, fontWeight: '600', color: T.text, textTransform: 'capitalize' }}>{cat.replace(/_/g, ' ')}</Text>
                          <Text style={{ fontSize: 11, color: T.textMuted }}>avg {v.avg_hours}h / p95 {v.p95_hours}h</Text>
                        </View>
                        <View style={{ height: 14, borderRadius: 7, overflow: 'hidden', backgroundColor: `${T.border}30` }}>
                          <View style={{ position: 'absolute', top: 0, left: 0, height: '100%' as any, width: `${p95Pct}%` as any, backgroundColor: `${barColor}30`, borderRadius: 7 }} />
                          <View style={{ height: '100%' as any, width: `${avgPct}%` as any, backgroundColor: barColor, borderRadius: 7 }} />
                        </View>
                      </View>
                    );
                  });
                })()}
              </View>

              {/* ── Weekly Sentiment Trend ── */}
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="sentiment-trend-card" testID="sentiment-trend-card">
                <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 4 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.030', 'Weekly Sentiment Trend')}</Text>
                <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 14 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.031', 'Sentiment distribution over time')}</Text>
                {(heatmapData.sentiment_trend || []).length > 0 ? (
                  <View>
                    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 120, marginBottom: 8 }}>
                      {(heatmapData.sentiment_trend || []).map((w: any, i: number) => {
                        const barW = Math.max(14, Math.min(40, (isDesktop ? 600 : 280) / (heatmapData.sentiment_trend.length + 1)));
                        return (
                          <View key={i} style={{ width: barW, height: '100%' as any, justifyContent: 'flex-end' }} data-testid={`trend-bar-${i}`} testID={`trend-bar-${i}`}>
                            <View style={{ flexDirection: 'column', borderRadius: 4, overflow: 'hidden' }}>
                              {w.negative_pct > 0 && <View style={{ height: Math.max(2, w.negative_pct * 1.1), backgroundColor: colors.error }} />}
                              {w.neutral_pct > 0 && <View style={{ height: Math.max(2, w.neutral_pct * 1.1), backgroundColor: colors.warning }} />}
                              {w.positive_pct > 0 && <View style={{ height: Math.max(2, w.positive_pct * 1.1), backgroundColor: colors.success }} />}
                            </View>
                          </View>
                        );
                      })}
                    </View>
                    <View style={{ flexDirection: 'row', gap: 3 }}>
                      {(heatmapData.sentiment_trend || []).map((w: any, i: number) => {
                        const barW = Math.max(14, Math.min(40, (isDesktop ? 600 : 280) / (heatmapData.sentiment_trend.length + 1)));
                        return (
                          <Text key={i} style={{ width: barW, fontSize: 7, color: T.textMuted, textAlign: 'center' }}>{w.week.replace('2026-', '')}</Text>
                        );
                      })}
                    </View>
                    <View style={{ flexDirection: 'row', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
                      {(() => {
                        const latest = heatmapData.sentiment_trend[heatmapData.sentiment_trend.length - 1];
                        return (
                          <>
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success }} />
                              <Text style={{ fontSize: 11, color: T.textSec }}>Latest positive: <Text style={{ fontWeight: '700', color: colors.successText }}>{latest.positive_pct}%</Text></Text>
                            </View>
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.warning }} />
                              <Text style={{ fontSize: 11, color: T.textSec }}>Neutral: <Text style={{ fontWeight: '700', color: colors.warningText }}>{latest.neutral_pct}%</Text></Text>
                            </View>
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.error }} />
                              <Text style={{ fontSize: 11, color: T.textSec }}>Negative: <Text style={{ fontWeight: '700', color: colors.error }}>{latest.negative_pct}%</Text></Text>
                            </View>
                            <Text style={{ fontSize: 11, color: T.textSec }}>Avg: <Text style={{ fontWeight: '700', color: T.primary }}>{latest.avg_rating}/5</Text></Text>
                          </>
                        );
                      })()}
                    </View>
                  </View>
                ) : (
                  <View style={{ alignItems: 'center', paddingVertical: 20 }}>
                    <Text style={{ fontSize: 12, color: T.textMuted }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.032', 'Not enough data for weekly trend')}</Text>
                  </View>
                )}
              </View>

              {/* Summary KPI cards */}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                <View style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }} data-testid="heatmap-kpi-tickets" testID="heatmap-kpi-tickets">
                  <Ionicons name="ticket" size={18} color={T.primary} />
                  <Text style={{ fontSize: 24, fontWeight: '800', color: T.text, marginTop: 4 }}>{heatmapData.total_tickets}</Text>
                  <Text style={{ fontSize: 11, color: T.textMuted }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.033', 'Total Rated Tickets')}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }} data-testid="heatmap-kpi-categories" testID="heatmap-kpi-categories">
                  <Ionicons name="layers" size={18} color={T.purple || T.primary} />
                  <Text style={{ fontSize: 24, fontWeight: '800', color: T.text, marginTop: 4 }}>{Object.keys(heatmapData.sentiment_by_category || {}).length}</Text>
                  <Text style={{ fontSize: 11, color: T.textMuted }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.034', 'Categories Tracked')}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }} data-testid="heatmap-kpi-weeks" testID="heatmap-kpi-weeks">
                  <Ionicons name="calendar" size={18} color={T.successText} />
                  <Text style={{ fontSize: 24, fontWeight: '800', color: T.text, marginTop: 4 }}>{(heatmapData.sentiment_trend || []).length}</Text>
                  <Text style={{ fontSize: 11, color: T.textMuted }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.035', 'Weeks of Data')}</Text>
                </View>
              </View>
            </View>
          )}

          {/* ── Sentiment Drop Alerts ── */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.errorSoft, marginTop: 16 }} data-testid="sentiment-alerts-section" testID="sentiment-alerts-section">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Ionicons name="notifications" size={18} color={T.error} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, flex: 1 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.036', 'Sentiment Drop Alerts')}</Text>
              {alertConfigLoading ? <ActivityIndicator size="small" color={T.primary} /> : (
                <TouchableOpacity accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.004', 'Toggle sentiment drop alerts')}
                  onPress={async () => {
                    const next = !alertConfig?.enabled;
                    setAlertConfig((p: any) => ({ ...p, enabled: next }));
                    try { await api.put('/admin/ticket-feedback/sentiment-alerts/config', { ...alertConfig, enabled: next }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                  }}
                  style={[cs.toggleTrack, alertConfig?.enabled && cs.toggleTrackOn]}
                  data-testid="sentiment-alert-toggle" testID="sentiment-alert-toggle"
                >
                  <View style={[cs.toggleThumb, alertConfig?.enabled && cs.toggleThumbOn]} />
                </TouchableOpacity>
              )}
            </View>
            <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 14, lineHeight: 16 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.037', 'Get email alerts when negative sentiment in any category exceeds the threshold or spikes week-over-week. Checks run hourly.')}</Text>

            {/* Config controls */}
            {alertConfig && (
              <View style={{ gap: 12 }}>
                <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 12 }}>
                  <View style={{ flex: 1, backgroundColor: `${T.border}20`, borderRadius: 10, padding: 12 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.038', 'Negative Threshold')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      {[15, 20, 25, 30, 40, 50].map(v => (
                        <TouchableOpacity key={v} accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.005', 'Set negative sentiment threshold')}
                          onPress={async () => {
                            setAlertConfig((p: any) => ({ ...p, threshold_pct: v }));
                            try { await api.put('/admin/ticket-feedback/sentiment-alerts/config', { ...alertConfig, threshold_pct: v }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                          }}
                          style={[cs.periodBtn, alertConfig.threshold_pct === v && { backgroundColor: colors.errorSoft, borderColor: colors.error }]}
                          data-testid={`threshold-${v}`} testID={`threshold-${v}`}
                        >
                          <Text style={[cs.periodText, alertConfig.threshold_pct === v && { color: colors.error }]}>{v}%</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                  <View style={{ flex: 1, backgroundColor: `${T.border}20`, borderRadius: 10, padding: 12 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.039', 'Spike Detection')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      {[5, 10, 15, 20, 30].map(v => (
                        <TouchableOpacity key={v} accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.006', 'Set spike detection threshold')}
                          onPress={async () => {
                            setAlertConfig((p: any) => ({ ...p, spike_pct: v }));
                            try { await api.put('/admin/ticket-feedback/sentiment-alerts/config', { ...alertConfig, spike_pct: v }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch8', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                          }}
                          style={[cs.periodBtn, alertConfig.spike_pct === v && { backgroundColor: colors.warningSoft, borderColor: colors.warning }]}
                          data-testid={`spike-${v}`} testID={`spike-${v}`}
                        >
                          <Text style={[cs.periodText, alertConfig.spike_pct === v && { color: colors.warningText }]}>+{v}pp</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                </View>
                <View style={{ backgroundColor: `${T.border}20`, borderRadius: 10, padding: 12 }}>
                  <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.040', 'Cooldown (suppress duplicate alerts)')}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    {[6, 12, 24, 48, 72].map(v => (
                      <TouchableOpacity key={v} accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.007', 'Set alert cooldown hours')}
                        onPress={async () => {
                          setAlertConfig((p: any) => ({ ...p, cooldown_hours: v }));
                          try { await api.put('/admin/ticket-feedback/sentiment-alerts/config', { ...alertConfig, cooldown_hours: v }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch9', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                        }}
                        style={[cs.periodBtn, alertConfig.cooldown_hours === v && cs.periodActive]}
                        data-testid={`cooldown-${v}`} testID={`cooldown-${v}`}
                      >
                        <Text style={[cs.periodText, alertConfig.cooldown_hours === v && cs.periodTextActive]}>{v}h</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
                {alertConfig.last_checked && (
                  <Text style={{ fontSize: 10, color: T.textMuted, textAlign: 'right' }}>Last checked: {new Date(alertConfig.last_checked).toLocaleString()}</Text>
                )}
              </View>
            )}

            {/* Alert History */}
            <View style={{ marginTop: 16, borderTopWidth: 1, borderTopColor: `${T.border}50`, paddingTop: 12 }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 8 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.041', 'Alert History')}</Text>
              {alertHistoryLoading ? <ActivityIndicator size="small" color={T.primary} /> : alertHistory.length === 0 ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 12 }}>
                  <Ionicons name="checkmark-circle" size={16} color={T.successText} />
                  <Text style={{ fontSize: 12, color: T.textMuted }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.042', 'No sentiment alerts triggered yet — all clear!')}</Text>
                </View>
              ) : (
                alertHistory.slice(0, 10).map((a: any, i: number) => (
                  <View key={a.alert_id || i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 8, borderBottomWidth: i < Math.min(alertHistory.length, 10) - 1 ? 1 : 0, borderBottomColor: `${T.border}30` }} data-testid={`alert-${i}`} testID={`alert-${i}`}>
                    <Ionicons name="warning" size={14} color={T.error} style={{ marginTop: 2 }} />
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, textTransform: 'capitalize' }}>{(a.category || '').replace(/_/g, ' ')}</Text>
                        <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: a.negative_pct >= 50 ? T.errorSoft : T.warningSoft }}>
                          <Text style={{ fontSize: 10, fontWeight: '700', color: a.negative_pct >= 50 ? T.error : T.orange || T.warning }}>{a.negative_pct}% neg</Text>
                        </View>
                      </View>
                      {a.reasons?.map((r: string, ri: number) => (
                        <Text key={ri} style={{ fontSize: 11, color: T.textSec, lineHeight: 16 }}>{r}</Text>
                      ))}
                      {a.example_tickets?.length > 0 && (
                        <View style={{ marginTop: 4 }}>
                          {a.example_tickets.map((ex: any, ei: number) => (
                            <Text key={ei} style={{ fontSize: 10, color: T.textMuted }}>{ex.ticket} — {ex.subject} ({ex.rating}/5)</Text>
                          ))}
                        </View>
                      )}
                    </View>
                    <Text style={{ fontSize: 10, color: T.textMuted }}>{a.triggered_at ? new Date(a.triggered_at).toLocaleDateString() : ''}</Text>
                  </View>
                ))
              )}
            </View>
          </View>

          {/* ── Weekly Sentiment Summary Email ── */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.accentSoft, marginTop: 16 }} data-testid="sentiment-summary-section" testID="sentiment-summary-section">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Ionicons name="mail" size={18} color={colors.accent} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, flex: 1 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.043', 'Weekly Sentiment Summary')}</Text>
              {summaryConfigLoading ? <ActivityIndicator size="small" color={T.primary} /> : (
                <TouchableOpacity accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.008', 'Toggle weekly sentiment summary')}
                  onPress={async () => {
                    const next = !summaryConfig?.enabled;
                    setSummaryConfig((p: any) => ({ ...p, enabled: next }));
                    try { await api.put('/admin/ticket-feedback/sentiment-summary/config', { ...summaryConfig, enabled: next }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch10', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                  }}
                  style={[cs.toggleTrack, summaryConfig?.enabled && cs.toggleTrackOn]}
                  data-testid="summary-toggle" testID="summary-toggle"
                >
                  <View style={[cs.toggleThumb, summaryConfig?.enabled && cs.toggleThumbOn]} />
                </TouchableOpacity>
              )}
            </View>
            <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 14, lineHeight: 16 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.044', 'Receive a weekly email with sentiment health score, category snapshot (improving vs declining), and week-over-week trends.')}</Text>

            {summaryConfig && (
              <View style={{ gap: 12 }}>
                <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 12 }}>
                  <View style={{ flex: 1, backgroundColor: `${T.border}20`, borderRadius: 10, padding: 12 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.045', 'Send Day')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      {['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map(d => (
                        <TouchableOpacity key={d} accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.009', 'Set summary send day')}
                          onPress={async () => {
                            setSummaryConfig((p: any) => ({ ...p, day: d }));
                            try { await api.put('/admin/ticket-feedback/sentiment-summary/config', { ...summaryConfig, day: d }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch11', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                          }}
                          style={[cs.periodBtn, summaryConfig.day === d && { backgroundColor: colors.accentSoft, borderColor: colors.accent }]}
                          data-testid={`summary-day-${d}`} testID={`summary-day-${d}`}
                        >
                          <Text style={[cs.periodText, summaryConfig.day === d && { color: colors.accent }]}>{d.slice(0, 3).toUpperCase()}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                  <View style={{ flex: 1, backgroundColor: `${T.border}20`, borderRadius: 10, padding: 12 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.ticketFeedbackIntelPanel.auto.text.046', 'Send Hour (UTC)')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      {[6, 9, 12, 15, 18].map(h => (
                        <TouchableOpacity key={h} accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.010', 'Set summary send hour')}
                          onPress={async () => {
                            setSummaryConfig((p: any) => ({ ...p, hour: h }));
                            try { await api.put('/admin/ticket-feedback/sentiment-summary/config', { ...summaryConfig, hour: h }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch12', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                          }}
                          style={[cs.periodBtn, summaryConfig.hour === h && { backgroundColor: colors.accentSoft, borderColor: colors.accent }]}
                          data-testid={`summary-hour-${h}`} testID={`summary-hour-${h}`}
                        >
                          <Text style={[cs.periodText, summaryConfig.hour === h && { color: colors.accent }]}>{h}:00</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                </View>

                {/* Send Now + Last Sent */}
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <TouchableOpacity accessibilityLabel={tx('admin.ticketFeedbackIntelPanel.auto.accessibility.011', 'Send summary email now')}
                    onPress={async () => {
                      setSendingNow(true);
                      try {
                        const res = await api.post('/admin/ticket-feedback/sentiment-summary/send-now');
                        if (res.data?.sent) {
                          setSummaryConfig((p: any) => ({ ...p, last_sent: new Date().toISOString() }));
                        }
                      } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/TicketFeedbackIntelPanel.tsx#catch13', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setSendingNow(false); }
                    }}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accent }}
                    disabled={sendingNow}
                    data-testid="send-summary-now" testID="send-summary-now"
                  >
                    {sendingNow ? <ActivityIndicator size="small" color={colors.accent} /> : <Ionicons name="send" size={14} color={colors.accent} />}
                    <Text style={{ fontSize: 12, fontWeight: '700', color: colors.accent }}>{sendingNow ? 'Sending...' : 'Send Now'}</Text>
                  </TouchableOpacity>
                  {summaryConfig.last_sent && (
                    <Text style={{ fontSize: 10, color: T.textMuted }}>Last sent: {new Date(summaryConfig.last_sent).toLocaleString()}</Text>
                  )}
                </View>
              </View>
            )}
          </View>
        </View>
      )}
    </View>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────
