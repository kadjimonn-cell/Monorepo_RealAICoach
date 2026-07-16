import React, { useEffect, useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { View, Text, ScrollView, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, RadarChart, PolarGrid, PolarAngleAxis, Radar, PolarRadiusAxis } from 'recharts';
import AutoFixBanner from './AutoFixBanner';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

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

const priorityColors: Record<string, string> = { critical: T.error, high: T.warning, medium: T.primary, info: T.success };

interface InsightsData {
  platform_score: number;
  health_factors: Record<string, number>;
  stats: { total_users: number; active_7d: number; active_30d: number; engagement_rate: number; retention_rate: number; total_features: number; open_tickets: number; total_tickets: number };
  recommendations: { id: string; category: string; priority: string; title: string; description: string; impact: string; action: string }[];
  feature_insights: { name: string; category: string; adoption_rate: number; trend: string; satisfaction: number }[];
  engagement_trends: { week: string; dau: number; wau: number; sessions: number; avg_session_min: number }[];
  weekly_report: { period: string; highlights: string[]; top_actions: { action: string; impact: string; effort: string }[] };
}

export default function AIInsightsPanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [data, setData] = useState<InsightsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [llmRecs, setLlmRecs] = useState<any[] | null>(null);
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmMeta, setLlmMeta] = useState<{ model?: string; generated_at?: string; context_summary?: string } | null>(null);

  const fetchInsights = useCallback(async () => {
    try {
      const [dashboardRes, llmRes] = await Promise.all([
        api.get('/admin/ai-insights/dashboard'),
        api.get('/admin/ai-insights/llm-recommendations/latest').catch(() => ({ data: null })),
      ]);

      setData(dashboardRes.data);
      const llmData = llmRes?.data;
      if (llmData?.recommendations?.length) {
        setLlmRecs(llmData.recommendations);
        setLlmMeta({ model: llmData.model, generated_at: llmData.generated_at, context_summary: llmData.context_summary });
      }
    } catch (e) {
      console.error('AI insights error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchInsights();
  }, [fetchInsights]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/ai-insights/hybrid-refresh',
    onTick: fetchInsights,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const generateLlmRecs = async () => {
    setLlmLoading(true);
    try {
      const res = await api.post('/admin/ai-insights/generate-recommendations');
      if (res.data.recommendations?.length) {
        setLlmRecs(res.data.recommendations);
        setLlmMeta({ model: res.data.model, generated_at: res.data.generated_at, context_summary: res.data.context_summary });
      }
    } catch (e) {
      console.error('LLM generation error:', e);
    } finally {
      setLlmLoading(false);
    }
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.purpleText} /></View>;
      // eslint-disable-next-line no-unused-expressions
      <AutoFixBanner domain="ai_insights" />
  if (!data) return <View style={{ padding: 40, alignItems: 'center' }}><Ionicons name="alert-circle" size={32} color={T.error} /><Text style={{ color: T.error, marginTop: 8 }}>{tx('admin.aiInsightsPanel.states.loadFailed', 'Failed to load insights')}</Text></View>;

  if (Platform.OS !== 'web') return (
    <View style={{ padding: 20 }}>
      <Text style={{ color: T.text, fontSize: 16, fontWeight: '700' }}>{tx('admin.aiInsightsPanel.mobile.title', 'AI Insights')}</Text>
      <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>Platform Score: {data.platform_score}/100</Text>
    </View>
  );

  const scoreColor = data.platform_score >= 80 ? T.success : data.platform_score >= 60 ? T.warning : T.error;
  const radarData = Object.entries(data.health_factors).map(([key, val]) => ({
    subject: key.charAt(0).toUpperCase() + key.slice(1).replace('_', ' '),
    value: Math.round(val),
    fullMark: 100,
  }));

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 20, gap: 20, paddingBottom: 40 }}>
      {/* Header */}
      <div data-testid="ai-insights-header">
        <Text style={{ fontSize: 22, fontWeight: '800', color: T.text, letterSpacing: -0.5 }}>{tx('admin.aiInsightsPanel.header.title', 'AI Insights & Recommendations')}</Text>
        <Text style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{tx('admin.aiInsightsPanel.header.subtitle', 'AI-powered platform optimization, engagement insights & weekly reports')}</Text>
      </div>

      {/* Top Stats + Radar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        {/* Platform Score + Key Stats */}
        <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 24, border: `1px solid ${T.border}`, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }} data-testid="platform-score-card">
          <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width={110} height={110} viewBox="0 0 110 110" style={{ transform: 'rotate(-90deg)' }}>
              <circle cx={55} cy={55} r={48} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
              <circle cx={55} cy={55} r={48} fill="none" stroke={scoreColor} strokeWidth="6"
                strokeDasharray={`${2 * Math.PI * 48}`}
                strokeDashoffset={`${2 * Math.PI * 48 - (data.platform_score / 100) * 2 * Math.PI * 48}`}
                strokeLinecap="round" style={{ transition: 'stroke-dashoffset 1s ease' }} />
            </svg>
            <div style={{ position: 'absolute', textAlign: 'center' }}>
              <div style={{ fontSize: 26, fontWeight: '800', color: scoreColor }}>{data.platform_score}</div>
              <div style={{ fontSize: 8, color: T.textMuted, fontWeight: '600' }}>PLATFORM</div>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, width: '100%' }}>
            {[
              { label: 'Users', value: data.stats.total_users, color: T.primary },
              { label: 'Active (7d)', value: data.stats.active_7d, color: T.successText },
              { label: 'Engagement', value: `${data.stats.engagement_rate}%`, color: T.cyan },
              { label: 'Retention', value: `${data.stats.retention_rate}%`, color: T.purpleText },
              { label: 'Features', value: data.stats.total_features, color: T.warningText },
              { label: 'Open Tickets', value: data.stats.open_tickets, color: data.stats.open_tickets > 10 ? T.error : T.success },
            ].map((s, i) => (
              <div key={i} style={{ textAlign: 'center', padding: 6 }}>
                <div style={{ fontSize: 16, fontWeight: '800', color: s.color }}>{s.value}</div>
                <div style={{ fontSize: 9, color: T.textMuted, fontWeight: '600' }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Health Radar */}
        <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="health-radar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Ionicons name="analytics" size={16} color={T.purpleText} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('admin.aiInsightsPanel.sections.healthFactors', 'Health Factors')}</Text>
          </div>
          <div style={{ width: '100%', height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="rgba(255,255,255,0.08)" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: T.textMuted, fontSize: 10 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
                <Radar name="Score" dataKey="value" stroke={T.purpleText} fill={T.purpleText} fillOpacity={0.2} strokeWidth={2} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Engagement Trends */}
      <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="engagement-trends">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="trending-up" size={16} color={T.cyan} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('admin.aiInsightsPanel.sections.engagementTrends', 'Engagement Trends (12 Weeks)')}</Text>
        </div>
        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.engagement_trends} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="dauGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={T.primary} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={T.primary} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="sessGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={T.teal} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={T.teal} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="week" tick={{ fill: T.textMuted, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: T.textMuted, fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: T.card, border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11, color: T.text }} />
              <Legend wrapperStyle={{ fontSize: 10, color: T.textSec }} />
              <Area type="monotone" dataKey="dau" name="DAU" stroke={T.primary} fill="url(#dauGrad)" strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="sessions" name="Sessions" stroke={T.teal} fill="url(#sessGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Two columns: Recommendations + Weekly Report */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: 16 }}>
        {/* AI Recommendations — LLM-Powered */}
        <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="ai-recommendations">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Ionicons name="bulb" size={16} color={T.warningText} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('admin.aiInsightsPanel.sections.aiRecommendations', 'AI Recommendations')}</Text>
              {llmMeta?.model && <span style={{ fontSize: 9, color: T.cyan, backgroundColor: `${T.cyan}18`, padding: '2px 6px', borderRadius: 4 }}>GPT-4o</span>}
            </div>
            <button
              data-testid="generate-ai-recs-btn"
              onClick={generateLlmRecs}
              disabled={llmLoading}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 8, border: 'none', cursor: llmLoading ? 'wait' : 'pointer', backgroundColor: llmLoading ? 'rgba(139,92,246,0.3)' : T.purple, color: colors.primaryText, fontSize: 11, fontWeight: '700', transition: 'all 0.2s' }}
            >
              {llmLoading ? <ActivityIndicator size={12} color="var(--app-primary-text)" /> : <Ionicons name="sparkles" size={12} color="var(--app-primary-text)" />}
              {llmLoading ? 'Generating...' : 'Generate with AI'}
            </button>
          </div>
          {llmMeta?.generated_at && (
            <div style={{ fontSize: 9, color: T.textMuted, marginBottom: 10 }}>
              Generated: {new Date(llmMeta.generated_at).toLocaleString()} | Context: {llmMeta.context_summary}
            </div>
          )}
          {(llmRecs || data.recommendations).map((rec, i) => (
            <div key={i} style={{ padding: '12px 0', borderBottom: i < (llmRecs || data.recommendations).length - 1 ? `1px solid ${T.border}` : 'none' }} data-testid={`rec-${i}`}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 9, fontWeight: '700', color: priorityColors[rec.priority] || T.textMuted, backgroundColor: `${priorityColors[rec.priority] || T.textMuted}18`, padding: '2px 6px', borderRadius: 4, textTransform: 'uppercase' }}>{rec.priority}</span>
                <span style={{ fontSize: 9, color: T.textMuted, backgroundColor: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 4 }}>{rec.category}</span>
                {rec.generated_by && <span style={{ fontSize: 8, color: T.cyan, backgroundColor: `${T.cyan}12`, padding: '1px 4px', borderRadius: 3 }}>{rec.generated_by}</span>}
              </div>
              <div style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 4 }}>{rec.title}</div>
              <div style={{ fontSize: 11, color: T.textSec, lineHeight: '1.5' }}>{rec.description}</div>
              <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
                <span style={{ fontSize: 10, color: T.successText }}>{rec.impact}</span>
                {rec.action && <span style={{ fontSize: 10, color: T.primary }}>Action: {rec.action}</span>}
              </div>
            </div>
          ))}
        </div>

        {/* Weekly Report + Feature Insights */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Weekly Report */}
          <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="weekly-report">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <Ionicons name="document-text" size={16} color={T.primary} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('admin.aiInsightsPanel.sections.weeklyReport', 'Weekly Report')}</Text>
              <span style={{ fontSize: 10, color: T.textMuted }}>{data.weekly_report.period}</span>
            </div>
            {data.weekly_report.highlights.map((h, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 0' }}>
                <Ionicons name="checkmark-circle" size={12} color={T.successText} style={{ marginTop: 2 } as any} />
                <span style={{ fontSize: 11, color: T.textSec }}>{h}</span>
              </div>
            ))}
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${T.border}` }}>
              <div style={{ fontSize: 11, fontWeight: '700', color: T.text, marginBottom: 8 }}>Top Actions</div>
              {data.weekly_report.top_actions.map((a, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
                  <span style={{ fontSize: 9, fontWeight: '700', color: a.impact === 'high' ? T.warning : T.primary, backgroundColor: `${a.impact === 'high' ? T.warning : T.primary}18`, padding: '2px 6px', borderRadius: 4 }}>{a.impact}</span>
                  <span style={{ fontSize: 11, color: T.textSec }}>{a.action}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Top Feature Adoption */}
          <div style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, border: `1px solid ${T.border}` }} data-testid="feature-insights">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <Ionicons name="apps" size={16} color={T.teal} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('admin.aiInsightsPanel.sections.featureAdoption', 'Feature Adoption')}</Text>
            </div>
            {data.feature_insights.slice(0, 8).map((f, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: i < Math.min(data.feature_insights.length, 8) - 1 ? `1px solid ${T.border}` : 'none' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, fontWeight: '600', color: T.text }}>{f.name}</div>
                  <div style={{ fontSize: 9, color: T.textMuted }}>{f.category}</div>
                </div>
                <div style={{ width: 60, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${f.adoption_rate}%`, backgroundColor: f.adoption_rate > 70 ? T.success : f.adoption_rate > 40 ? T.warning : T.error, borderRadius: 2 }} />
                </div>
                <span style={{ fontSize: 10, fontWeight: '700', color: f.adoption_rate > 70 ? T.success : f.adoption_rate > 40 ? T.warning : T.error, width: 32, textAlign: 'right' }}>{f.adoption_rate}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </ScrollView>
  );
}
