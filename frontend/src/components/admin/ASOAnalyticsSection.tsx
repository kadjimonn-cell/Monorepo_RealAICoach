import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, Legend } from 'recharts';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface ASOData {
  aso_score: number;
  keyword_rankings: { keyword: string; rank: number; trend: string; volume: number; difficulty: number }[];
  store_metrics: Record<string, any>;
  download_trends: { week: string; ios: number; android: number }[];
  rating_distribution: Record<string, number>;
  competitors: { name: string; rating: number; downloads: string; features: number; highlight: boolean }[];
  optimization_checklist: { item: string; status: boolean; detail: string }[];
  total_features: number;
}

export default function ASOAnalyticsSection({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const PANEL_BG = AC.card;
  const PANEL_BORDER = AC.border;
  const TEXT_PRIMARY = AC.text;
  const TEXT_SECONDARY = AC.textSec;
  const TEXT_MUTED = AC.textMuted;
  const SOFT_BG = AC.bgAlt;
  const [data, setData] = useState<ASOData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/admin/seo/aso/analytics')
      .then(r => setData(r.data))
      .catch(e => console.error('ASO fetch error:', e))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator size="large" color={'var(--app-primary)'} />
      <Text style={{ color: TEXT_SECONDARY, marginTop: 12, fontSize: 13 }}>{tx('admin.asoAnalytics.states.loading', 'Loading ASO Analytics...')}</Text>
    </View>
  );

  if (!data) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <Ionicons name="alert-circle" size={32} color={'var(--app-error)'} />
      <Text style={{ color: colors.error, marginTop: 8 }}>{tx('admin.asoAnalytics.states.loadFailed', 'Failed to load ASO data')}</Text>
    </View>
  );

  if (Platform.OS !== 'web') return (
    <View style={{ padding: 20 }}>
      <Text style={{ color: TEXT_PRIMARY, fontSize: 16, fontWeight: '700' }}>{tx('admin.asoAnalytics.mobile.title', 'ASO Analytics')}</Text>
      <Text style={{ color: TEXT_MUTED, fontSize: 12, marginTop: 4 }}>ASO Score: {data.aso_score}/100</Text>
    </View>
  );

  const trendColor = (t: string) => t === 'up' ? 'var(--app-success)' : t === 'down' ? 'var(--app-error)' : 'var(--app-text)';
  const trendIcon = (t: string) => t === 'up' ? 'trending-up' : t === 'down' ? 'trending-down' : 'remove';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} data-testid="aso-analytics-section">
      {/* ASO Score + Store Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        {/* ASO Overall Score */}
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 24, border: `1px solid ${PANEL_BORDER}`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }} data-testid="aso-score-card">
          <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width={120} height={120} viewBox="0 0 120 120" style={{ transform: 'rotate(-90deg)' }}>
              <circle cx={60} cy={60} r={52} fill="none" stroke={PANEL_BORDER} strokeWidth="6" />
              <circle cx={60} cy={60} r={52} fill="none" stroke={'var(--app-primary)'} strokeWidth="6"
                strokeDasharray={`${2 * Math.PI * 52}`}
                strokeDashoffset={`${2 * Math.PI * 52 - (data.aso_score / 100) * 2 * Math.PI * 52}`}
                strokeLinecap="round" style={{ transition: 'stroke-dashoffset 1s ease' }} />
            </svg>
            <div style={{ position: 'absolute', textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: '800', color: colors.accent }}>{data.aso_score}</div>
              <div style={{ fontSize: 9, color: TEXT_SECONDARY, fontWeight: '600' }}>ASO SCORE</div>
            </div>
          </div>
        </div>

        {/* iOS Store */}
        {Object.entries(data.store_metrics).map(([key, store]) => (
          <div key={key} style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid={`store-card-${key}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <Ionicons name={key === 'ios' ? 'logo-apple' : 'logo-google-playstore'} size={18} color={key === 'ios' ? TEXT_PRIMARY : 'var(--app-primary)'} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{store.store}</Text>
              <div style={{ marginLeft: 'auto', backgroundColor: colors.accentSoft, paddingLeft: 8, paddingRight: 8, paddingTop: 2, paddingBottom: 2, borderRadius: 6 }}>
                <Text style={{ fontSize: 10, color: colors.accent, fontWeight: '700' }}>#{store.category_rank} {store.category}</Text>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
              {[
                { label: 'Rating', value: `${store.rating}/5`, icon: 'star' },
                { label: 'Downloads (30d)', value: store.downloads_30d?.toLocaleString(), icon: 'download' },
                { label: 'Retention (7d)', value: `${store.retention_7d}%`, icon: 'refresh' },
                { label: 'Crash-Free', value: `${store.crash_free_rate}%`, icon: 'shield-checkmark' },
                { label: 'Conversion', value: `${store.conversion_rate}%`, icon: 'trending-up' },
                { label: 'Avg Session', value: store.avg_session_duration, icon: 'time' },
              ].map((m, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 0' }}>
                  <Ionicons name={m.icon as any} size={12} color={TEXT_MUTED} />
                  <div>
                    <div style={{ fontSize: 10, color: TEXT_MUTED }}>{m.label}</div>
                    <div style={{ fontSize: 13, fontWeight: '700', color: TEXT_PRIMARY }}>{m.value}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Download Trends Chart */}
      <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="download-trends-chart">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="download" size={16} color={'var(--app-primary)'} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.asoAnalytics.sections.downloadTrends', 'Download Trends (12 Weeks)')}</Text>
        </div>
        <div style={{ width: '100%', height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.download_trends} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="iosGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={'var(--app-primary)'} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={'var(--app-primary)'} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="androidGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={'var(--app-success)'} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={'var(--app-success)'} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={PANEL_BORDER} />
              <XAxis dataKey="week" tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: SOFT_BG, border: `1px solid ${PANEL_BORDER}`, borderRadius: 8, fontSize: 11, color: TEXT_PRIMARY }} />
              <Legend wrapperStyle={{ fontSize: 10, color: TEXT_SECONDARY }} />
              <Area type="monotone" dataKey="ios" name="iOS" stroke={'var(--app-primary)'} fill="url(#iosGrad)" strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="android" name="Android" stroke={'var(--app-success)'} fill="url(#androidGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Two columns: Keywords + Competitors */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: 16 }}>
        {/* Keyword Rankings */}
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="keyword-rankings">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="search" size={16} color={'var(--app-warning)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.asoAnalytics.sections.keywordRankings', 'Keyword Rankings')}</Text>
          </div>
          {data.keyword_rankings.map((kw, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < data.keyword_rankings.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }} data-testid={`keyword-${i}`}>
              <div style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: kw.rank <= 5 ? 'rgba(34,197,94,0.15)' : kw.rank <= 10 ? 'rgba(245,158,11,0.15)' : 'rgba(107,114,128,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <span style={{ fontSize: 11, fontWeight: '800', color: kw.rank <= 5 ? 'var(--app-success)' : kw.rank <= 10 ? 'var(--app-warning)' : 'var(--app-text)' }}>#{kw.rank}</span>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: '600', color: TEXT_SECONDARY }}>{kw.keyword}</div>
                <div style={{ fontSize: 10, color: TEXT_MUTED }}>Vol: {kw.volume.toLocaleString()} | Diff: {kw.difficulty}%</div>
              </div>
              <Ionicons name={trendIcon(kw.trend) as any} size={14} color={trendColor(kw.trend)} />
            </div>
          ))}
        </div>

        {/* Competitors */}
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="competitor-comparison">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="podium" size={16} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.asoAnalytics.sections.competitorComparison', 'Competitor Comparison')}</Text>
          </div>
          {data.competitors.map((c, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < data.competitors.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none', backgroundColor: c.highlight ? 'rgba(139,92,246,0.06)' : 'transparent', borderRadius: c.highlight ? 8 : 0, paddingLeft: c.highlight ? 8 : 0, paddingRight: c.highlight ? 8 : 0 }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: c.highlight ? '800' : '600', color: c.highlight ? 'var(--app-primary)' : TEXT_SECONDARY }}>{c.name}</span>
                  {c.highlight && <span style={{ fontSize: 8, color: colors.accent, backgroundColor: colors.accentSoft, padding: '1px 5px', borderRadius: 4, fontWeight: '700' }}>YOU</span>}
                </div>
                <div style={{ fontSize: 10, color: TEXT_MUTED }}>{c.downloads} downloads | {c.features} features</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Ionicons name="star" size={12} color={'var(--app-warning)'} />
                <span style={{ fontSize: 12, fontWeight: '700', color: TEXT_PRIMARY }}>{c.rating}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ASO Optimization Checklist */}
      <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="aso-checklist">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Ionicons name="checkmark-done-circle" size={16} color={'var(--app-success)'} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.asoAnalytics.sections.optimizationChecklist', 'ASO Optimization Checklist')}</Text>
          <Text style={{ fontSize: 10, color: colors.successText, fontWeight: '700' }}>
            {data.optimization_checklist.filter(c => c.status).length}/{data.optimization_checklist.length} Passed
          </Text>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 0 }}>
          {data.optimization_checklist.map((item, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <div style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: item.status ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Ionicons name={item.status ? 'checkmark' : 'close'} size={12} color={item.status ? 'var(--app-success)' : 'var(--app-error)'} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: '600', color: TEXT_SECONDARY }}>{item.item}</div>
                <div style={{ fontSize: 10, color: TEXT_MUTED }}>{item.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
