import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
const PRIORITY_COLORS: Record<string, string> = {
  critical: 'var(--app-error)' as any,
  warning: 'var(--app-warning)' as any,
  success: 'var(--app-success)' as any,
  info: 'var(--app-info)' as any,
};
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const PRIORITY_ICONS: Record<string, string> = { critical: 'alert-circle', warning: 'warning', success: 'checkmark-circle', info: 'information-circle' };

interface Analytics {
  overall_score: number; recent_score: number; trend: number; nps: number;
  total_responses: number; total_sent: number; response_rate: number; total_users: number;
  category_averages: Record<string, number>;
  question_averages: { id: string; text: string; category: string; average: number; count: number }[];
  distribution: Record<string, number>;
  monthly_trend: { label: string; score: number; count: number }[];
  recent_responses: { email: string; average_score: number; nps_score: number; feedback: string; submitted_at: string }[];
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface Suggestion { category: string; score: number; priority: string; suggestion: string }

interface AutomationStatus {
  automation_enabled: boolean; schedule: string; reminder_schedule: string;
  next_survey_run: string; last_survey_run: string | null; last_reminder_run: string | null;
  token_expiry_days: number; survey_interval_days: number;
  pending_surveys: number; expired_tokens: number;
  total_sent: number; total_completed: number; total_reminders_sent: number; completion_rate: number;
}

export default function CsatDashboardPanel({ colors, darkMode }: { colors: any; darkMode?: boolean }) {
  const s = StyleSheet.create({
    kpiRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 16 },
    kpiCard: { flex: 1, minWidth: 150, borderRadius: 14, padding: 16, borderWidth: 1, alignItems: 'center' },
    kpiIcon: { width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center', marginBottom: 8 },
    kpiValue: { fontSize: 28, fontWeight: '800' },
    kpiSub: { fontSize: 12, fontWeight: '500' },
    kpiLabel: { fontSize: 11, fontWeight: '600', textTransform: 'uppercase' as any, marginTop: 4 },
    sendBtn: { backgroundColor: colors.success, borderRadius: 10, padding: 12, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8, marginBottom: 16 },
    sendBtnText: { color: colors.primaryText, fontSize: 13, fontWeight: '700' },
    tabRow: { flexDirection: 'row', borderBottomWidth: 1, marginBottom: 16, gap: 4 },
    tabBtn: { paddingVertical: 10, paddingHorizontal: 16, borderBottomWidth: 2, borderBottomColor: 'transparent' },
    tabText: { fontSize: 13, fontWeight: '600' },
    section: { borderRadius: 14, padding: 20, borderWidth: 1, marginBottom: 16 },
    sectionTitle: { fontSize: 15, fontWeight: '700', marginBottom: 16 },
    catRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 10, gap: 10 },
    catLabel: { width: 90, fontSize: 12, fontWeight: '500' },
    catBarWrap: { flex: 1, height: 8, backgroundColor: 'var(--app-border)' as any, borderRadius: 4, overflow: 'hidden' },
    catBar: { height: '100%' as any, borderRadius: 4 },
    catScore: { width: 36, fontSize: 13, fontWeight: '700', textAlign: 'right' },
    chartRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
    chartCol: { flex: 1, alignItems: 'center' },
    chartVal: { fontSize: 11, fontWeight: '600', marginBottom: 4 },
    chartBarWrap: { width: '100%' as any, height: 80, backgroundColor: 'var(--app-border)' as any, borderRadius: 4, justifyContent: 'flex-end', overflow: 'hidden' },
    chartBar: { width: '100%' as any, borderRadius: 4, minHeight: 2 },
    chartLabel: { fontSize: 11, fontWeight: '500', marginTop: 4 },
    chartCount: { fontSize: 9 },
    distRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 4 },
    distCol: { flex: 1, alignItems: 'center' },
    distCount: { fontSize: 11, fontWeight: '600', marginBottom: 4 },
    distBarWrap: { width: '100%' as any, height: 60, backgroundColor: 'var(--app-border)' as any, borderRadius: 4, justifyContent: 'flex-end', overflow: 'hidden' },
    distBar: { width: '100%' as any, borderRadius: 4, minHeight: 2 },
    distLabel: { fontSize: 11, marginTop: 4, fontWeight: '600' },
    qCard: { borderRadius: 12, padding: 16, borderWidth: 1, marginBottom: 10 },
    qIdx: { width: 24, height: 24, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
    qBar: { height: 4, borderRadius: 2, overflow: 'hidden' },
    sugHeader: { fontSize: 16, fontWeight: '700', marginBottom: 12 },
    sugCard: { borderRadius: 12, padding: 16, borderWidth: 1, marginBottom: 10 },
    scorePill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
    respCard: { borderRadius: 12, padding: 14, borderWidth: 1, marginBottom: 10 },
    respAvatar: { width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center' },
  });
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { data, loading: dLoading } = useLiveQuery<Analytics>('/csat/analytics', { entity: 'csat', pollInterval: 60000 });
  const { data: suggestionsData } = useLiveQuery('/csat/suggestions', { entity: 'csat', pollInterval: 60000 });
  const { data: autoStatus } = useLiveQuery<AutomationStatus>('/csat/automation-status', { entity: 'csat', pollInterval: 60000 });
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _suggestions = suggestionsData?.suggestions || [];
  const loading = dLoading;
  const [sending, setSending] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState<any>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiRunning, setAiRunning] = useState(false);
  const [reportConfig, setReportConfig] = useState<any>(null);
  const [reportConfigLoading, setReportConfigLoading] = useState(false);
  const [reportSending, setReportSending] = useState(false);
  const [tab, setTab] = useState<'overview' | 'questions' | 'ai-intel' | 'responses' | 'automation'>('overview');
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  // Auto-load latest AI analysis + report config when switching to AI Intelligence tab
  useEffect(() => {
    if (tab !== 'ai-intel') return;
    setAiLoading(true);
    api.get('/csat/ai-analysis/latest')
      .then(r => { if (r.data?.ok) setAiAnalysis(r.data); })
      .catch(() => {})
      .finally(() => setAiLoading(false));
    setReportConfigLoading(true);
    api.get('/csat/ai-report/config')
      .then(r => setReportConfig(r.data))
      .catch(() => {})
      .finally(() => setReportConfigLoading(false));
  }, [tab]);

  const T = {
    card: AC.card,
    cardAlt: AC.cardSoft,
    border: AC.border,
    text: AC.text,
    textSec: AC.textSec,
    textMuted: AC.textMuted,
    highlight: AC.info,
    success: AC.success,
    warning: AC.warning,
    danger: AC.error,
    successText: AC.successText,
    warningText: AC.warningText,
    orange: AC.orange,
  };

  const triggerSend = async () => {
    setSending(true);
    try {
      const res = await api.post('/csat/send-manual', { target: 'all' });
      alert(tx('admin.csat.alerts.sentSurveyCount', 'Sent {count} survey emails!').replace('{count}', String(res.data.sent_count ?? 0)));
    } catch { alert(tx('admin.csat.errors.sendSurveysFailed', 'Failed to send surveys')); }
    finally { setSending(false); }
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator color={T.highlight} size="large" /></View>;
  if (!data) return <View style={{ padding: 20 }}><Text style={{ color: T.textSec }}>{tx('admin.csat.states.noDataYet', 'No CSAT data available yet.')}</Text></View>;

  const scoreColor = (s: number) => s >= 8 ? T.success : s >= 6 ? T.warning : T.danger;
  const maxDist = Math.max(...Object.values(data.distribution), 1);
  const maxTrend = Math.max(...data.monthly_trend.map(t => t.score), 1);

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16 }} data-testid="csat-dashboard" testID="csat-dashboard">
      {/* KPI Cards */}
      <View style={[s.kpiRow, isDesktop && { flexDirection: 'row' }]} data-testid="csat-kpis" testID="csat-kpis">
        {[
          { label: tx('admin.csat.kpi.csatScore', 'CSAT Score'), value: data.overall_score.toFixed(1), sub: '/10', icon: 'star', color: scoreColor(data.overall_score) },
          { label: tx('admin.csat.kpi.npsScore', 'NPS Score'), value: data.nps > 0 ? `+${data.nps}` : `${data.nps}`, sub: tx('admin.csat.kpi.points', 'pts'), icon: 'trending-up', color: data.nps > 0 ? T.success : T.danger },
          { label: tx('admin.csat.kpi.responseRate', 'Response Rate'), value: `${data.response_rate}`, sub: '%', icon: 'mail-open', color: colors.primary },
          { label: tx('admin.csat.kpi.totalResponses', 'Total Responses'), value: `${data.total_responses}`, sub: tx('admin.csat.kpi.sentCount', '/{count} sent').replace('{count}', String(data.total_sent)), icon: 'chatbubbles', color: colors.primary },
        ].map((kpi, i) => (
          <View key={i} style={[s.kpiCard, { backgroundColor: T.card, borderColor: T.border }]} data-testid={`csat-kpi-${i}`} testID={`csat-kpi-${i}`}>
            <View style={[s.kpiIcon, { backgroundColor: (globalThis as any).__alphaColor(kpi.color, '18') }]}><Ionicons name={kpi.icon as any} size={18} color={kpi.color} /></View>
            <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 2 }}>
              <Text style={[s.kpiValue, { color: kpi.color }]}>{kpi.value}</Text>
              <Text style={[s.kpiSub, { color: T.textMuted }]}>{kpi.sub}</Text>
            </View>
            <Text style={[s.kpiLabel, { color: T.textSec }]}>{kpi.label}</Text>
            {i === 0 && data.trend !== 0 && (
              <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 4 }}>
                <Ionicons name={data.trend > 0 ? 'arrow-up' : 'arrow-down'} size={10} color={data.trend > 0 ? T.success : T.danger} />
                <Text style={{ color: data.trend > 0 ? T.success : T.danger, fontSize: 11, fontWeight: '600' }}>{data.trend > 0 ? '+' : ''}{data.trend.toFixed(1)} {tx('admin.csat.kpi.vsPrev', 'vs prev')}</Text>
              </View>
            )}
          </View>
        ))}
      </View>

      {/* Send Survey Button */}
      <TouchableOpacity style={[s.sendBtn, sending && { opacity: 0.6 }]} onPress={triggerSend} disabled={sending} data-testid="csat-send-btn" testID="csat-send-btn">
        {sending ? <ActivityIndicator color={colors.primaryText} size="small" /> : <Ionicons name="mail" size={16} color={colors.primaryText} />}
        <Text style={s.sendBtnText}>{sending ? tx('admin.csat.common.sending', 'Sending...') : tx('admin.csat.actions.sendSurveyToAll', 'Send Survey to All Eligible Users')}</Text>
      </TouchableOpacity>

      {/* Tab Nav */}
      <View style={[s.tabRow, { borderColor: T.border }]}>
        {(['overview', 'questions', 'ai-intel', 'responses', 'automation'] as const).map(t => (
          <TouchableOpacity key={t} style={[s.tabBtn, tab === t && { borderBottomColor: T.highlight, borderBottomWidth: 2 }]} onPress={() => setTab(t as any)} data-testid={`csat-tab-${t}`} testID={`csat-tab-${t}`}>
            <Text style={[s.tabText, { color: tab === t ? T.highlight : T.textMuted }]}>{t === 'ai-intel' ? tx('admin.csat.tabs.aiIntelligence', 'AI Intelligence') : tx(`admin.csat.tabs.${t}`, t.charAt(0).toUpperCase() + t.slice(1))}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <View>
          {/* Category Radar / Bar */}
          <View style={[s.section, { backgroundColor: T.card, borderColor: T.border }]} data-testid="csat-categories" testID="csat-categories">
            <Text style={[s.sectionTitle, { color: T.text }]}>{tx('admin.csat.sections.categoryPerformance', 'Category Performance')}</Text>
            {Object.entries(data.category_averages).sort((a, b) => a[1] - b[1]).map(([cat, avg]) => (
              <View key={cat} style={s.catRow}>
                <Text style={[s.catLabel, { color: T.textSec }]}>{cat}</Text>
                <View style={s.catBarWrap}>
                  <View style={[s.catBar, { width: `${avg * 10}%` as any, backgroundColor: scoreColor(avg) }]} />
                </View>
                <Text style={[s.catScore, { color: scoreColor(avg) }]}>{avg.toFixed(1)}</Text>
              </View>
            ))}
          </View>

          {/* Monthly Trend */}
          <View style={[s.section, { backgroundColor: T.card, borderColor: T.border }]} data-testid="csat-trend" testID="csat-trend">
            <Text style={[s.sectionTitle, { color: T.text }]}>{tx('admin.csat.sections.monthlyTrend', 'Monthly Trend')}</Text>
            <View style={s.chartRow}>
              {data.monthly_trend.map((m, i) => (
                <View key={i} style={s.chartCol}>
                  <Text style={[s.chartVal, { color: m.score > 0 ? T.text : T.textMuted }]}>{m.score > 0 ? m.score.toFixed(1) : '-'}</Text>
                  <View style={s.chartBarWrap}>
                    <View style={[s.chartBar, { height: `${maxTrend > 0 ? (m.score / maxTrend) * 100 : 0}%` as any, backgroundColor: m.score >= 7 ? T.success : m.score >= 5 ? T.warning : m.score > 0 ? T.danger : T.border }]} />
                  </View>
                  <Text style={[s.chartLabel, { color: T.textMuted }]}>{m.label}</Text>
                  <Text style={[s.chartCount, { color: T.textMuted }]}>{m.count}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Score Distribution */}
          <View style={[s.section, { backgroundColor: T.card, borderColor: T.border }]} data-testid="csat-distribution" testID="csat-distribution">
            <Text style={[s.sectionTitle, { color: T.text }]}>{tx('admin.csat.sections.scoreDistribution', 'Score Distribution')}</Text>
            <View style={s.distRow}>
              {Object.entries(data.distribution).map(([score, count]) => (
                <View key={score} style={s.distCol}>
                  <Text style={[s.distCount, { color: T.textSec }]}>{count}</Text>
                  <View style={s.distBarWrap}>
                    <View style={[s.distBar, { height: `${maxDist > 0 ? (count / maxDist) * 100 : 0}%` as any, backgroundColor: PRIORITY_COLORS[parseInt(score) >= 8 ? 'success' : parseInt(score) >= 5 ? 'warning' : 'critical'] }]} />
                  </View>
                  <Text style={[s.distLabel, { color: T.textMuted }]}>{score}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      )}

      {/* Questions Tab */}
      {tab === 'questions' && (
        <View data-testid="csat-questions-tab" testID="csat-questions-tab">
          {data.question_averages.map((q, i) => (
            <View key={q.id} style={[s.qCard, { backgroundColor: T.card, borderColor: T.border }]}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <View style={[s.qIdx, { backgroundColor: (globalThis as any).__alphaColor(T.highlight, '20') }]}><Text style={{ color: T.highlight, fontSize: 11, fontWeight: '700' }}>{i + 1}</Text></View>
                <Text style={{ color: T.highlight, fontSize: 11, fontWeight: '600', textTransform: 'uppercase' }}>{q.category}</Text>
                <View style={{ flex: 1 }} />
                <Text style={{ color: scoreColor(q.average), fontSize: 18, fontWeight: '800' }}>{q.average.toFixed(1)}</Text>
              </View>
              <Text style={{ color: T.textSec, fontSize: 13, lineHeight: 18 }}>{q.text}</Text>
              <View style={[s.qBar, { backgroundColor: T.cardAlt, marginTop: 10 }]}>
                <View style={{ height: 4, borderRadius: 2, width: `${q.average * 10}%` as any, backgroundColor: scoreColor(q.average) }} />
              </View>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{tx('admin.csat.questions.responsesCount', '{count} responses').replace('{count}', String(q.count))}</Text>
            </View>
          ))}
        </View>
      )}

      {/* AI Intelligence Tab */}
      {tab === 'ai-intel' && (
        <View data-testid="csat-ai-intel-tab" testID="csat-ai-intel-tab">
          {/* Run Analysis Button */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <TouchableOpacity accessibilityLabel="Run ai analysis button"
              onPress={async () => {
                setAiRunning(true);
                try {
                  const res = await api.post('/csat/ai-analysis');
                  if (res.data) setAiAnalysis(res.data);
                } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CsatDashboardPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setAiRunning(false); }
              }}
              disabled={aiRunning}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: aiRunning ? `${T.highlight}30` : T.highlight }}
              data-testid="run-ai-analysis" testID="run-ai-analysis"
            >
              {aiRunning ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="sparkles" size={16} color={colors.primaryText} />}
              <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{aiRunning ? tx('admin.csat.ai.analyzing', 'Analyzing with GPT-4o...') : tx('admin.csat.ai.actions.runAnalysis', 'Run AI Analysis')}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="Async in csat dashboard panel"
              onPress={async () => {
                setAiLoading(true);
                try {
                  const res = await api.get('/csat/ai-analysis/latest');
                  if (res.data?.ok) setAiAnalysis(res.data);
                } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CsatDashboardPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setAiLoading(false); }
              }}
              style={{ paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: T.border }}
            >
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600' }}>{tx('admin.csat.ai.actions.loadLatest', 'Load Latest')}</Text>
            </TouchableOpacity>
            {aiAnalysis?.created_at && (
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.csat.ai.lastRun', 'Last')}: {new Date(aiAnalysis.created_at).toLocaleString()}</Text>
            )}
          </View>

          {(aiLoading || aiRunning) && !aiAnalysis && (
            <View style={{ alignItems: 'center', padding: 40 }}>
              <ActivityIndicator size="large" color={T.highlight} />
              <Text style={{ color: T.textMuted, marginTop: 10, fontSize: 12 }}>{tx('admin.csat.ai.runningAnalysis', 'Running AI analysis on CSAT data...')}</Text>
            </View>
          )}

          {!aiAnalysis && !aiLoading && !aiRunning && (
            <View style={{ alignItems: 'center', padding: 40 }}>
              <Ionicons name="sparkles" size={40} color={T.textMuted} />
              <Text style={{ color: T.text, fontSize: 16, fontWeight: '700', marginTop: 12 }}>{tx('admin.csat.ai.suiteTitle', 'AI Intelligence Suite')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 12, textAlign: 'center', marginTop: 6, maxWidth: 400 }}>
                {tx('admin.csat.ai.suiteHint', 'Click "Run AI Analysis" to get GPT-4o powered insights: feedback themes, at-risk categories, root causes, and a prioritized action plan.')}
              </Text>
            </View>
          )}

          {aiAnalysis?.ok && (
            <View style={{ gap: 14 }}>
              {/* Health Score + Prediction */}
              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 12 }}>
                <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, alignItems: 'center' }} data-testid="ai-health-score" testID="ai-health-score">
                  <Text style={{ fontSize: 10, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('admin.csat.ai.sentimentHealth', 'Sentiment Health')}</Text>
                  <Text style={{ fontSize: 48, fontWeight: '900', color: aiAnalysis.health_score >= 70 ? colors.success : aiAnalysis.health_score >= 50 ? colors.warning : colors.error, marginTop: 4 }}>{aiAnalysis.health_score}</Text>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor((aiAnalysis.risk_level === 'low' ? colors.success : aiAnalysis.risk_level === 'medium' ? colors.warning : colors.error), '20'), marginTop: 4 }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: aiAnalysis.risk_level === 'low' ? colors.success : aiAnalysis.risk_level === 'medium' ? colors.warning : colors.error, textTransform: 'uppercase' }}>{aiAnalysis.risk_level} risk</Text>
                  </View>
                </View>
                <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, alignItems: 'center' }} data-testid="ai-prediction" testID="ai-prediction">
                  <Text style={{ fontSize: 10, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('admin.csat.ai.predictedNextMonth', 'Predicted Next Month')}</Text>
                  <Text style={{ fontSize: 48, fontWeight: '900', color: colors.primary, marginTop: 4 }}>{aiAnalysis.predicted_csat}</Text>
                  <Text style={{ fontSize: 10, color: T.textMuted, textAlign: 'center', marginTop: 4, maxWidth: 200 }}>{aiAnalysis.prediction_reasoning}</Text>
                </View>
                <View style={{ flex: 2, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="ai-summary" testID="ai-summary">
                  <Text style={{ fontSize: 10, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>{tx('admin.csat.ai.executiveSummary', 'Executive Summary')}</Text>
                  <Text style={{ fontSize: 13, color: T.text, lineHeight: 20 }}>{aiAnalysis.executive_summary}</Text>
                  {aiAnalysis.data_snapshot && (
                    <View style={{ flexDirection: 'row', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
                      <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.csat.ai.responses', 'Responses')}: <Text style={{ fontWeight: '700', color: T.text }}>{aiAnalysis.data_snapshot.total_responses}</Text></Text>
                      <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.csat.ai.csat', 'CSAT')}: <Text style={{ fontWeight: '700', color: colors.successText }}>{aiAnalysis.data_snapshot.overall_avg}/10</Text></Text>
                      <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.csat.ai.nps', 'NPS')}: <Text style={{ fontWeight: '700', color: colors.primary }}>{aiAnalysis.data_snapshot.nps}</Text></Text>
                    </View>
                  )}
                </View>
              </View>

              {/* Feedback Themes */}
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid="ai-themes" testID="ai-themes">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Ionicons name="chatbubbles" size={16} color={colors.accent} />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.csat.ai.feedbackThemes', 'Feedback Themes')}</Text>
                </View>
                {(aiAnalysis.feedback_themes || []).map((theme: any, i: number) => {
                  const sentColor = theme.sentiment === 'positive' ? colors.success : theme.sentiment === 'negative' ? colors.error : colors.warning;
                  return (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 8, borderBottomWidth: i < (aiAnalysis.feedback_themes || []).length - 1 ? 1 : 0, borderBottomColor: `${T.border}30` }} data-testid={`ai-theme-${i}`} testID={`ai-theme-${i}`}>
                      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: sentColor, marginTop: 5 }} />
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                          <Text style={{ fontSize: 12, fontWeight: '700', color: T.text }}>{theme.theme}</Text>
                          <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(sentColor, '20') }}>
                            <Text style={{ fontSize: 9, fontWeight: '700', color: sentColor }}>{theme.sentiment}</Text>
                          </View>
                          <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, backgroundColor: `${T.border}40` }}>
                            <Text style={{ fontSize: 9, color: T.textMuted }}>{tx('admin.csat.ai.frequencyCount', '{count} freq').replace('{count}', String(theme.frequency))}</Text>
                          </View>
                        </View>
                        <Text style={{ fontSize: 11, color: T.textSec, lineHeight: 16 }}>{theme.summary}</Text>
                      </View>
                    </View>
                  );
                })}
              </View>

              {/* At-Risk Categories + Root Causes (side by side on desktop) */}
              <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 12 }}>
                {/* At-Risk Categories */}
                <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.errorSoft }} data-testid="ai-at-risk" testID="ai-at-risk">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Ionicons name="warning" size={16} color={colors.error} />
                    <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.csat.ai.atRiskCategories', 'At-Risk Categories')}</Text>
                  </View>
                  {(aiAnalysis.at_risk_categories || []).length === 0 ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10 }}>
                      <Ionicons name="checkmark-circle" size={16} color={colors.success} />
                      <Text style={{ fontSize: 12, color: T.textMuted }}>{tx('admin.csat.ai.allCategoriesHealthy', 'All categories healthy')}</Text>
                    </View>
                  ) : (aiAnalysis.at_risk_categories || []).map((cat: any, i: number) => (
                    <View key={i} style={{ paddingVertical: 8, borderBottomWidth: i < (aiAnalysis.at_risk_categories || []).length - 1 ? 1 : 0, borderBottomColor: `${T.border}30` }} data-testid={`ai-risk-${i}`} testID={`ai-risk-${i}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, textTransform: 'capitalize' }}>{cat.category}</Text>
                        <Text style={{ fontSize: 11, fontWeight: '700', color: scoreColor(cat.score) }}>{cat.score}/10</Text>
                        <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor((cat.risk === 'declining' ? colors.error : colors.warning), '20') }}>
                          <Text style={{ fontSize: 9, fontWeight: '700', color: cat.risk === 'declining' ? colors.error : colors.warning }}>{cat.risk}</Text>
                        </View>
                      </View>
                      <Text style={{ fontSize: 11, color: T.textSec }}>{cat.reason}</Text>
                    </View>
                  ))}
                </View>

                {/* Root Causes */}
                <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.warningSoft }} data-testid="ai-root-causes" testID="ai-root-causes">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Ionicons name="git-branch" size={16} color={colors.orange} />
                    <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.csat.ai.rootCauses', 'Root Causes')}</Text>
                  </View>
                  {(aiAnalysis.root_causes || []).map((rc: any, i: number) => {
                    const impactColor = rc.impact === 'high' ? colors.error : rc.impact === 'medium' ? colors.orange : colors.warning;
                    return (
                      <View key={i} style={{ paddingVertical: 8, borderBottomWidth: i < (aiAnalysis.root_causes || []).length - 1 ? 1 : 0, borderBottomColor: `${T.border}30` }} data-testid={`ai-cause-${i}`} testID={`ai-cause-${i}`}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                          <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(impactColor, '20') }}>
                            <Text style={{ fontSize: 9, fontWeight: '700', color: impactColor }}>{tx('admin.csat.ai.impactWithValue', '{impact} impact').replace('{impact}', rc.impact)}</Text>
                          </View>
                          <Text style={{ fontSize: 10, color: T.textMuted }}>{(rc.affected_categories || []).join(', ')}</Text>
                        </View>
                        <Text style={{ fontSize: 12, fontWeight: '600', color: T.text, marginBottom: 2 }}>{rc.issue}</Text>
                        <Text style={{ fontSize: 10, color: T.textSec }}>{rc.evidence}</Text>
                      </View>
                    );
                  })}
                </View>
              </View>

              {/* Action Plan */}
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.primarySoft }} data-testid="ai-action-plan" testID="ai-action-plan">
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Ionicons name="rocket" size={16} color={colors.primary} />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.csat.ai.actionPlan', 'AI Action Plan')}</Text>
                  <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: colors.primarySoft }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primary }}>{tx('admin.csat.ai.actionsCount', '{count} actions').replace('{count}', String((aiAnalysis.action_plan || []).length))}</Text>
                  </View>
                </View>
                {(aiAnalysis.action_plan || []).map((ap: any, i: number) => {
                  const priorityColor = ap.priority <= 2 ? colors.error : ap.priority <= 3 ? colors.orange : colors.primary;
                  const effortColor = ap.effort === 'low' ? colors.success : ap.effort === 'medium' ? colors.warning : colors.error;
                  return (
                    <View key={i} style={{ flexDirection: 'row', gap: 10, paddingVertical: 10, borderBottomWidth: i < (aiAnalysis.action_plan || []).length - 1 ? 1 : 0, borderBottomColor: `${T.border}20` }} data-testid={`ai-action-${i}`} testID={`ai-action-${i}`}>
                      <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(priorityColor, '20'), alignItems: 'center', justifyContent: 'center' }}>
                        <Text style={{ fontSize: 12, fontWeight: '800', color: priorityColor }}>{ap.priority}</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 3 }}>{ap.action}</Text>
                        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                          <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.csat.ai.category', 'Category')}: <Text style={{ fontWeight: '600', color: T.textSec }}>{ap.category}</Text></Text>
                          <Text style={{ fontSize: 10, color: colors.successText, fontWeight: '700' }}>{ap.expected_impact}</Text>
                          <View style={{ paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3, backgroundColor: (globalThis as any).__alphaColor(effortColor, '15') }}>
                            <Text style={{ fontSize: 9, fontWeight: '700', color: effortColor }}>{tx('admin.csat.ai.effortWithValue', '{effort} effort').replace('{effort}', ap.effort)}</Text>
                          </View>
                          <Text style={{ fontSize: 10, color: T.textMuted }}>{ap.timeline}</Text>
                        </View>
                      </View>
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          {/* ── Weekly AI Report Email Config ── */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.accentSoft, marginTop: 14 }} data-testid="csat-report-config" testID="csat-report-config">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Ionicons name="mail" size={18} color={colors.accent} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, flex: 1 }}>{tx('admin.csat.report.title', 'Weekly AI Report Email')}</Text>
              {reportConfigLoading ? <ActivityIndicator size="small" color={T.highlight} /> : (
                <TouchableOpacity accessibilityLabel="Report toggle button"
                  onPress={async () => {
                    const next = !reportConfig?.enabled;
                    setReportConfig((p: any) => ({ ...p, enabled: next }));
                    try { await api.put('/csat/ai-report/config', { ...reportConfig, enabled: next }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CsatDashboardPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                  }}
                  style={{ width: 44, height: 24, borderRadius: 12, padding: 2, backgroundColor: reportConfig?.enabled ? colors.success : `${T.border}60` }}
                  data-testid="report-toggle" testID="report-toggle"
                >
                  <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: colors.primaryText, alignSelf: reportConfig?.enabled ? 'flex-end' as any : 'flex-start' as any }} />
                </TouchableOpacity>
              )}
            </View>
            <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 14, lineHeight: 16 }}>
              {tx('admin.csat.report.description', 'Automatically run GPT-4o analysis and email a branded report with health score, themes, at-risk categories, and top actions to all admins.')}
            </Text>

            {reportConfig && (
              <View style={{ gap: 12 }}>
                <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 12 }}>
                  <View style={{ flex: 1, backgroundColor: darkMode ? `${T.border}20` : T.cardAlt, borderRadius: 10, padding: 12 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.csat.report.sendDay', 'Send Day')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      {['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map(d => (
                        <TouchableOpacity key={d} accessibilityLabel="Async in csat dashboard panel"
                          onPress={async () => {
                            setReportConfig((p: any) => ({ ...p, day: d }));
                            try { await api.put('/csat/ai-report/config', { ...reportConfig, day: d }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CsatDashboardPanel.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                          }}
                          style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, borderWidth: 1, borderColor: reportConfig.day === d ? colors.accent : `${T.border}40`, backgroundColor: reportConfig.day === d ? colors.accentSoft : 'transparent' }}
                          data-testid={`report-day-${d}`} testID={`report-day-${d}`}
                        >
                          <Text style={{ fontSize: 10, fontWeight: '600', color: reportConfig.day === d ? colors.accent : T.textMuted }}>{d.slice(0, 3).toUpperCase()}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                  <View style={{ flex: 1, backgroundColor: darkMode ? `${T.border}20` : T.cardAlt, borderRadius: 10, padding: 12 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{tx('admin.csat.report.sendHourUtc', 'Send Hour (UTC)')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      {[6, 8, 9, 12, 15, 18].map(h => (
                        <TouchableOpacity key={h} accessibilityLabel="Async in csat dashboard panel"
                          onPress={async () => {
                            setReportConfig((p: any) => ({ ...p, hour: h }));
                            try { await api.put('/csat/ai-report/config', { ...reportConfig, hour: h }); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CsatDashboardPanel.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                          }}
                          style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, borderWidth: 1, borderColor: reportConfig.hour === h ? colors.accent : `${T.border}40`, backgroundColor: reportConfig.hour === h ? colors.accentSoft : 'transparent' }}
                          data-testid={`report-hour-${h}`} testID={`report-hour-${h}`}
                        >
                          <Text style={{ fontSize: 10, fontWeight: '600', color: reportConfig.hour === h ? colors.accent : T.textMuted }}>{h}:00</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <TouchableOpacity accessibilityLabel="Send report now button"
                    onPress={async () => {
                      setReportSending(true);
                      try {
                        const res = await api.post('/csat/ai-report/send-now');
                        if (res.data?.sent) setReportConfig((p: any) => ({ ...p, last_sent: new Date().toISOString() }));
                      } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CsatDashboardPanel.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setReportSending(false); }
                    }}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accent }}
                    disabled={reportSending}
                    data-testid="send-report-now" testID="send-report-now"
                  >
                    {reportSending ? <ActivityIndicator size="small" color={colors.accent} /> : <Ionicons name="send" size={14} color={colors.accent} />}
                    <Text style={{ fontSize: 12, fontWeight: '700', color: colors.accent }}>{reportSending ? tx('admin.csat.common.sending', 'Sending...') : tx('admin.csat.report.actions.sendNow', 'Send Now')}</Text>
                  </TouchableOpacity>
                  {reportConfig.last_sent && (
                    <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.csat.report.lastSent', 'Last sent')}: {new Date(reportConfig.last_sent).toLocaleString()}</Text>
                  )}
                </View>
              </View>
            )}
          </View>
        </View>
      )}

      {/* Responses Tab */}
      {tab === 'responses' && (
        <View data-testid="csat-responses-tab" testID="csat-responses-tab">
          {data.recent_responses.length === 0 ? (
            <Text style={{ color: T.textMuted, textAlign: 'center', padding: 40 }}>{tx('admin.csat.states.noResponsesYet', 'No responses yet.')}</Text>
          ) : data.recent_responses.map((r, i) => (
            <View key={i} style={[s.respCard, { backgroundColor: T.card, borderColor: T.border }]}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <View style={[s.respAvatar, { backgroundColor: (globalThis as any).__alphaColor(T.highlight, '18') }]}> 
                  <Ionicons name="person" size={14} color={T.highlight} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{r.email}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>{r.submitted_at ? new Date(r.submitted_at).toLocaleDateString() : ''}</Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ color: scoreColor(r.average_score), fontSize: 16, fontWeight: '800' }}>{r.average_score}/10</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.csat.ai.nps', 'NPS')}: {r.nps_score}</Text>
                </View>
              </View>
              {r.feedback ? <Text style={{ color: T.textSec, fontSize: 12, marginTop: 8, fontStyle: 'italic' }}>"{r.feedback}"</Text> : null}
            </View>
          ))}
        </View>
      )}

      {/* Automation Tab */}
      {tab === 'automation' && autoStatus && (
        <View data-testid="csat-automation-panel" testID="csat-automation-panel">
          {/* Status Header */}
          <View style={[s.section, { backgroundColor: T.card, borderColor: T.border }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: autoStatus.automation_enabled ? T.success : T.danger }} />
              <Text style={[s.sectionTitle, { color: T.text, marginBottom: 0 }]}>
                {tx('admin.csat.automation.titleWithStatus', 'Automation {status}')
                  .replace('{status}', autoStatus.automation_enabled ? tx('admin.csat.automation.active', 'Active') : tx('admin.csat.automation.inactive', 'Inactive'))}
              </Text>
            </View>

            <View style={{ gap: 12 }}>
              {[
                { label: tx('admin.csat.automation.surveySchedule', 'Survey Schedule'), value: autoStatus.schedule, icon: 'calendar' },
                { label: tx('admin.csat.automation.reminderSchedule', 'Reminder Schedule'), value: autoStatus.reminder_schedule, icon: 'alarm' },
                { label: tx('admin.csat.automation.nextSurveyRun', 'Next Survey Run'), value: autoStatus.next_survey_run ? new Date(autoStatus.next_survey_run).toLocaleString() : tx('admin.csat.common.na', 'N/A'), icon: 'time' },
                { label: tx('admin.csat.automation.lastSurveyRun', 'Last Survey Run'), value: autoStatus.last_survey_run ? new Date(autoStatus.last_survey_run).toLocaleString() : tx('admin.csat.common.never', 'Never'), icon: 'checkmark-done' },
                { label: tx('admin.csat.automation.lastReminderRun', 'Last Reminder Run'), value: autoStatus.last_reminder_run ? new Date(autoStatus.last_reminder_run).toLocaleString() : tx('admin.csat.common.never', 'Never'), icon: 'notifications' },
                { label: tx('admin.csat.automation.tokenExpiry', 'Token Expiry'), value: tx('admin.csat.automation.daysWithCount', '{count} days').replace('{count}', String(autoStatus.token_expiry_days)), icon: 'hourglass' },
                { label: tx('admin.csat.automation.surveyInterval', 'Survey Interval'), value: tx('admin.csat.automation.daysWithCount', '{count} days').replace('{count}', String(autoStatus.survey_interval_days)), icon: 'repeat' },
              ].map((item, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: T.border }}>
                  <Ionicons name={item.icon as any} size={16} color={T.highlight} />
                  <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', width: 120 }}>{item.label}</Text>
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '500', flex: 1 }}>{item.value}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Pipeline Stats */}
          <View style={[s.section, { backgroundColor: T.card, borderColor: T.border }]}>
            <Text style={[s.sectionTitle, { color: T.text }]}>{tx('admin.csat.automation.pipelineStats', 'Pipeline Stats')}</Text>
            <View style={[s.kpiRow, { flexDirection: 'row' }]}>
              {[
                { label: tx('admin.csat.automation.totalSent', 'Total Sent'), value: autoStatus.total_sent, color: colors.primary },
                { label: tx('admin.csat.automation.completed', 'Completed'), value: autoStatus.total_completed, color: T.successText },
                { label: tx('admin.csat.automation.pending', 'Pending'), value: autoStatus.pending_surveys, color: T.warningText },
                { label: tx('admin.csat.automation.expired', 'Expired'), value: autoStatus.expired_tokens, color: T.danger },
                { label: tx('admin.csat.automation.reminders', 'Reminders'), value: autoStatus.total_reminders_sent, color: colors.primary },
              ].map((stat, i) => (
                <View key={i} style={{ flex: 1, minWidth: 80, alignItems: 'center', padding: 12, backgroundColor: (globalThis as any).__alphaColor(stat.color, '10'), borderRadius: 10 }}>
                  <Text style={{ fontSize: 22, fontWeight: '800', color: stat.color }}>{stat.value}</Text>
                  <Text style={{ fontSize: 10, fontWeight: '600', color: T.textSec, textTransform: 'uppercase' as any, marginTop: 2 }}>{stat.label}</Text>
                </View>
              ))}
            </View>

            {/* Completion Rate Bar */}
            <View style={{ marginTop: 12 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600' }}>{tx('admin.csat.automation.completionRate', 'Completion Rate')}</Text>
                <Text style={{ color: T.highlight, fontSize: 12, fontWeight: '700' }}>{autoStatus.completion_rate}%</Text>
              </View>
              <View style={{ height: 8, backgroundColor: T.border, borderRadius: 4, overflow: 'hidden' }}>
                <View style={{ height: '100%' as any, width: `${autoStatus.completion_rate}%`, backgroundColor: T.highlight, borderRadius: 4 }} />
              </View>
            </View>
          </View>

          {/* Automation Flow Diagram */}
          <View style={[s.section, { backgroundColor: T.card, borderColor: T.border }]}>
            <Text style={[s.sectionTitle, { color: T.text }]}>{tx('admin.csat.automation.flowTitle', 'Automation Flow')}</Text>
            {[
              { step: '1', label: 'Survey Sent', desc: 'Auto-sent every 45 days to eligible users at 09:00 UTC', icon: 'mail', color: colors.primary },
              { step: '2', label: 'Reminder', desc: 'If no response after 7 days, one gentle reminder at 09:30 UTC', icon: 'alarm', color: T.warningText },
              { step: '3', label: 'Token Expiry', desc: 'Survey links expire after 30 days for security', icon: 'hourglass', color: T.danger },
              { step: '4', label: 'Cooldown', desc: 'User won\'t receive another survey for 45 days after any send', icon: 'timer', color: colors.primary },
            ].map((flow, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: 12, marginBottom: i < 3 ? 12 : 0, alignItems: 'flex-start' }}>
                <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: (globalThis as any).__alphaColor(flow.color, '18'), justifyContent: 'center', alignItems: 'center' }}>
                  <Ionicons name={flow.icon as any} size={16} color={flow.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{flow.label}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11, lineHeight: 16, marginTop: 2 }}>{flow.desc}</Text>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}
      {tab === 'automation' && !autoStatus && (
        <View style={{ padding: 20, alignItems: 'center' }}>
          <Text style={{ color: T.textSec, fontSize: 13 }}>{tx('admin.csat.automation.statusUnavailable', 'Automation status unavailable.')}</Text>
        </View>
      )}
    </ScrollView>
  );
}
