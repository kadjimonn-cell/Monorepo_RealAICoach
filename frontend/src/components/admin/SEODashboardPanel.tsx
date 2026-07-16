import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, ActivityIndicator, Platform, useWindowDimensions, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from 'recharts';
import ASOAnalyticsSection from './ASOAnalyticsSection';
import MobileIndexingSection from './MobileIndexingSection';
import GlobalPerformanceSection from './GlobalPerformanceSection';
import ResponsivenessSection from './ResponsivenessSection';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

interface Props { colors: any; }
type SubTab = 'seo-overview' | 'aso-analytics' | 'mobile-indexing' | 'global-performance' | 'responsiveness';

interface SEOData {
  seo_score: number;
  performance_score: number;
  security_score: number;
  core_web_vitals: { lcp: number; fid: number; cls: number; fcp: number; ttfb: number; inp: number; measurements: number };
  vitals_trend: { date: string; avg_lcp: number; avg_fid: number; avg_cls: number; count: number }[];
  checklist: { item: string; status: boolean; detail: string }[];
  aso_metrics: { app_name_optimized: boolean; keyword_density: number; description_length: number; screenshots_count: number; ratings_average: number; total_features: number; categories: string[]; supported_languages: number };
  security_headers: Record<string, boolean>;
  sitemap: { total_pages: number; feature_pages: number; static_pages: number };
  page_performance: { page: string; lcp: number; fid: number; cls: number; score: number }[];
  timestamp: string;
  lighthouse_summary?: {
    audit_id: string;
    timestamp: string;
    avg_performance: number;
    avg_seo: number;
    avg_security: number;
    avg_ttfb: number;
    total_audits: number;
  } | null;
}

const SEO_POLL_MAX_INTERVAL_MS = 30000;
const SEO_POLL_MIN_INTERVAL_MS = 12000;

const VITALS_THRESHOLDS = {
  lcp: { good: 2.5, poor: 4.0, unit: 's', label: 'Largest Contentful Paint' },
  fid: { good: 100, poor: 300, unit: 'ms', label: 'First Input Delay' },
  cls: { good: 0.1, poor: 0.25, unit: '', label: 'Cumulative Layout Shift' },
  fcp: { good: 1.8, poor: 3.0, unit: 's', label: 'First Contentful Paint' },
  ttfb: { good: 0.8, poor: 1.8, unit: 's', label: 'Time to First Byte' },
  inp: { good: 200, poor: 500, unit: 'ms', label: 'Interaction to Next Paint' },
};

function getVitalColor(metric: keyof typeof VITALS_THRESHOLDS, value: number): string {
  const t = VITALS_THRESHOLDS[metric];
  if (value <= t.good) return 'var(--app-success)' as any;
  if (value <= t.poor) return 'var(--app-warning)' as any;
  return 'var(--app-error)' as any;
}

function getVitalLabel(metric: keyof typeof VITALS_THRESHOLDS, value: number): string {
  const t = VITALS_THRESHOLDS[metric];
  if (value <= t.good) return 'Good';
  if (value <= t.poor) return 'Needs Improvement';
  return 'Poor';
}

function ScoreGauge({ score, label, color, size = 100, theme }: { score: number; label: string; color: string; size?: number; theme?: any }) {
  const T = theme || { border: 'var(--app-border)' as any, textMuted: 'var(--app-text-muted)' as any };
  const circumference = 2 * Math.PI * (size / 2 - 8);
  const strokeDashoffset = circumference - (score / 100) * circumference;

  if (Platform.OS !== 'web') return (
    <View style={{ alignItems: 'center', gap: 4 }}>
      <Text style={{ fontSize: 28, fontWeight: '800', color }}>{score}</Text>
      <Text style={{ fontSize: 11, color: T.textMuted }}>{label}</Text>
    </View>
  );

  return (
    <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={size / 2 - 8} fill="none" stroke={T.border} strokeWidth="5" />
        <circle cx={size / 2} cy={size / 2} r={size / 2 - 8} fill="none" stroke={color} strokeWidth="5" strokeDasharray={`${circumference}`} strokeDashoffset={`${strokeDashoffset}`} strokeLinecap="round" style={{ transition: 'stroke-dashoffset 1s ease' }} />
      </svg>
      <div style={{ position: 'absolute', textAlign: 'center' }}>
        <div style={{ fontSize: 22, fontWeight: '800', color }}>{score}</div>
        <div style={{ fontSize: 9, color: T.textMuted, fontWeight: '600', letterSpacing: 0.5 }}>{label}</div>
      </div>
    </div>
  );
}

function VitalCard({ metric, value, theme }: { metric: keyof typeof VITALS_THRESHOLDS; value: number; theme?: any }) {
  const T = theme || { card: 'transparent', border: 'var(--app-border)' as any, textSec: 'var(--app-text-sec)' as any, text: 'var(--app-text)' as any, textMuted: 'var(--app-text-muted)' as any };
  const t = VITALS_THRESHOLDS[metric];
  const color = getVitalColor(metric, value);
  const status = getVitalLabel(metric, value);
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, flex: 1, minWidth: 140 }} data-testid={`vital-${metric}`} testID={`vital-${metric}`}>
      <Text style={{ fontSize: 10, color: T.textSec, fontWeight: '700', letterSpacing: 0.5, marginBottom: 6 }}>{t.label.toUpperCase()}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4 }}>
        <Text style={{ fontSize: 24, fontWeight: '800', color }}>{value}</Text>
        {t.unit ? <Text style={{ fontSize: 12, color: T.textMuted }}>{t.unit}</Text> : null}
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 6 }}>
        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: color }} />
        <Text style={{ fontSize: 10, color, fontWeight: '600' }}>{status}</Text>
      </View>
      {/* Progress bar */}
      <View style={{ height: 3, backgroundColor: T.border, borderRadius: 2, marginTop: 8, overflow: 'hidden' }}>
        {Platform.OS === 'web' && (
          <div style={{ height: '100%', width: `${Math.min(100, (value / t.poor) * 100)}%`, backgroundColor: color, borderRadius: 2, transition: 'width 0.5s ease' }} />
        )}
      </View>
    </View>
  );
}

export default function SEODashboardPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const SUB_TABS: { id: SubTab; label: string; icon: string; color: string }[] = [
    { id: 'seo-overview', label: 'SEO Overview', icon: 'search', color: colors.primary },
    { id: 'aso-analytics', label: 'ASO Analytics', icon: 'storefront', color: colors.accent },
    { id: 'mobile-indexing', label: 'Mobile-First', icon: 'phone-portrait', color: colors.accent },
    { id: 'global-performance', label: 'Global CDN', icon: 'earth', color: colors.successText },
    { id: 'responsiveness', label: 'Responsiveness', icon: 'resize', color: colors.warningText },
  ];
  const AC = useAdminTheme();
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('seo-overview');
  const [data, setData] = useState<SEOData | null>(null);
  const [lhHistory, setLhHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;
  const isTablet = width >= 768;
  const PANEL_BG = AC.card;
  const PANEL_BORDER = AC.border;
  const TEXT_PRIMARY = AC.text;
  const TEXT_SECONDARY = AC.textSec;
  const TEXT_MUTED = AC.textMuted;
  const SOFT_BG = AC.bgAlt || AC.card;
  const SEO_THEME = { card: PANEL_BG, border: PANEL_BORDER, text: TEXT_PRIMARY, textSec: TEXT_SECONDARY, textMuted: TEXT_MUTED };

  const fetchSeoOverview = useCallback(async () => {
    if (activeSubTab !== 'seo-overview') return;
    try {
      const [seoRes, histRes] = await Promise.all([
        api.get('/admin/seo/analytics'),
        api.get('/admin/seo/lighthouse/history').catch(() => ({ data: { audits: [] } })),
      ]);
      setData(seoRes.data);
      setLhHistory(histRes.data.audits || []);
    } catch (e) {
      console.error('SEO analytics error:', e);
    } finally {
      setLoading(false);
    }
  }, [activeSubTab]);

  useEffect(() => {
    void fetchSeoOverview();
  }, [fetchSeoOverview]);

  useHybridPolling({
    enabled: activeSubTab === 'seo-overview',
    errorScope: 'admin/seo-dashboard/hybrid-refresh',
    onTick: fetchSeoOverview,
    runOnMount: false,
    slowIntervalMs: SEO_POLL_MAX_INTERVAL_MS,
    fastIntervalMs: SEO_POLL_MIN_INTERVAL_MS,
  });

  const renderSubTabContent = () => {
    if (activeSubTab === 'aso-analytics') return <ASOAnalyticsSection colors={colors} />;
    if (activeSubTab === 'mobile-indexing') return <MobileIndexingSection colors={colors} />;
    if (activeSubTab === 'global-performance') return <GlobalPerformanceSection colors={colors} />;
    if (activeSubTab === 'responsiveness') return <ResponsivenessSection colors={colors} />;
    return null;
  };

  const seoColor = data ? (data.seo_score >= 90 ? colors.success : data.seo_score >= 70 ? colors.warning : colors.error) : PANEL_BORDER;
  const perfColor = data ? (data.performance_score >= 90 ? colors.success : data.performance_score >= 70 ? colors.warning : colors.error) : PANEL_BORDER;
  const secColor = data ? (data.security_score >= 90 ? colors.success : data.security_score >= 70 ? colors.warning : colors.error) : PANEL_BORDER;

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: isDesktop ? 24 : 12, gap: 20, paddingBottom: 40 }} data-testid="seo-dashboard-panel" testID="seo-dashboard-panel">
      <AutoFixBanner domain="seo" />
      {/* Header */}
      <View style={{ flexDirection: isTablet ? 'row' : 'column', alignItems: isTablet ? 'center' : 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <View>
          <Text style={{ fontSize: 22, fontWeight: '800', color: TEXT_PRIMARY, letterSpacing: -0.5 }}>{tx('admin.sEODashboardPanel.auto.text.001', 'SEO & ASO Command Center')}</Text>
          <Text style={{ fontSize: 12, color: TEXT_MUTED, marginTop: 2 }}>{tx('admin.sEODashboardPanel.auto.text.002', 'Real-time search visibility, performance & security analytics')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success }} />
          <Text style={{ fontSize: 11, color: TEXT_MUTED }}>{tx('admin.sEODashboardPanel.auto.text.003', 'Auto-refresh 30s')}</Text>
        </View>
      </View>

      {/* Sub-Tab Navigation */}
      {Platform.OS === 'web' ? (
        <div style={{ display: 'flex', flexDirection: 'row', gap: 6, overflowX: 'auto', paddingBottom: 4 } as any} data-testid="seo-sub-tabs">
          {SUB_TABS.map(tab => {
            const isActive = activeSubTab === tab.id;
            return (
              <TouchableOpacity key={tab.id} onPress={() => setActiveSubTab(tab.id)}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10, backgroundColor: isActive ? `${tab.color}18` : PANEL_BG, borderWidth: 1, borderColor: isActive ? `${tab.color}50` : PANEL_BORDER }}
                data-testid={`seo-subtab-${tab.id}`} testID={`seo-subtab-${tab.id}`}>
                <Ionicons name={tab.icon as any} size={14} color={isActive ? tab.color : TEXT_MUTED} />
                <Text style={{ fontSize: 12, fontWeight: isActive ? '700' : '500', color: isActive ? tab.color : TEXT_SECONDARY }}>{tab.label}</Text>
              </TouchableOpacity>
            );
          })}
        </div>
      ) : (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 4 }}>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {SUB_TABS.map(tab => {
              const isActive = activeSubTab === tab.id;
              return (
                <TouchableOpacity key={tab.id} onPress={() => setActiveSubTab(tab.id)}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10, backgroundColor: isActive ? `${tab.color}18` : PANEL_BG, borderWidth: 1, borderColor: isActive ? `${tab.color}50` : PANEL_BORDER }}
                  data-testid={`seo-subtab-${tab.id}`} testID={`seo-subtab-${tab.id}`}>
                  <Ionicons name={tab.icon as any} size={14} color={isActive ? tab.color : TEXT_MUTED} />
                  <Text style={{ fontSize: 12, fontWeight: isActive ? '700' : '500', color: isActive ? tab.color : TEXT_SECONDARY }}>{tab.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </ScrollView>
      )}

      {/* Render sub-tab content or SEO overview */}
      {activeSubTab !== 'seo-overview' ? renderSubTabContent() : (<>

      {loading ? (
        <View style={{ padding: 40, alignItems: 'center' }}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={{ color: TEXT_SECONDARY, marginTop: 12, fontSize: 13 }}>{tx('admin.sEODashboardPanel.auto.text.004', 'Loading SEO Analytics...')}</Text>
        </View>
      ) : !data ? (
        <View style={{ padding: 40, alignItems: 'center' }}>
          <Ionicons name="alert-circle" size={32} color={colors.error} />
          <Text style={{ color: colors.error, marginTop: 8 }}>{tx('admin.sEODashboardPanel.auto.text.005', 'Failed to load SEO data')}</Text>
        </View>
      ) : (<>

      {/* Score Gauges */}
      {Platform.OS === 'web' ? (
        <div style={{ display: 'grid', gridTemplateColumns: isDesktop ? '1fr 1fr 1fr' : isTablet ? '1fr 1fr 1fr' : '1fr', gap: 16 } as any} data-testid="seo-score-gauges">
          {[
            { score: data.seo_score, label: 'SEO SCORE', color: seoColor },
            { score: data.performance_score, label: 'PERFORMANCE', color: perfColor },
            { score: data.security_score, label: 'SECURITY', color: secColor },
          ].map(g => (
            <div key={g.label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', backgroundColor: PANEL_BG, borderRadius: 16, padding: 24, border: `1px solid ${PANEL_BORDER}` }}>
              <ScoreGauge score={g.score} label={g.label} color={g.color} theme={SEO_THEME} />
            </div>
          ))}
        </div>
      ) : (
        <View style={{ flexDirection: 'row', gap: 12, justifyContent: 'center' }}>
          {[
            { score: data.seo_score, label: 'SEO', color: seoColor },
            { score: data.performance_score, label: 'PERF', color: perfColor },
            { score: data.security_score, label: 'SEC', color: secColor },
          ].map(g => (
            <ScoreGauge key={g.label} score={g.score} label={g.label} color={g.color} size={80} theme={SEO_THEME} />
          ))}
        </View>
      )}

      {/* Core Web Vitals */}
      <View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Ionicons name="speedometer" size={18} color={colors.primary} />
          <Text style={{ fontSize: 16, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.sEODashboardPanel.auto.text.006', 'Core Web Vitals')}</Text>
          <Text style={{ fontSize: 10, color: TEXT_MUTED, backgroundColor: SOFT_BG, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
            {data.core_web_vitals.measurements} measurements
          </Text>
        </View>
        {Platform.OS === 'web' ? (
          <div style={{ display: 'grid', gridTemplateColumns: isDesktop ? 'repeat(3, 1fr)' : isTablet ? 'repeat(2, 1fr)' : '1fr', gap: 12 } as any}>
            <VitalCard metric="lcp" value={data.core_web_vitals.lcp} theme={SEO_THEME} />
            <VitalCard metric="fid" value={data.core_web_vitals.fid} theme={SEO_THEME} />
            <VitalCard metric="cls" value={data.core_web_vitals.cls} theme={SEO_THEME} />
            <VitalCard metric="fcp" value={data.core_web_vitals.fcp} theme={SEO_THEME} />
            <VitalCard metric="ttfb" value={data.core_web_vitals.ttfb} theme={SEO_THEME} />
            <VitalCard metric="inp" value={data.core_web_vitals.inp} theme={SEO_THEME} />
          </div>
        ) : (
          <View style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <VitalCard metric="lcp" value={data.core_web_vitals.lcp} theme={SEO_THEME} />
              <VitalCard metric="fid" value={data.core_web_vitals.fid} theme={SEO_THEME} />
            </View>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <VitalCard metric="cls" value={data.core_web_vitals.cls} theme={SEO_THEME} />
              <VitalCard metric="fcp" value={data.core_web_vitals.fcp} theme={SEO_THEME} />
            </View>
          </View>
        )}
      </View>

      {/* Vitals Trend Chart — Recharts */}
      {data.vitals_trend.length > 0 && Platform.OS === 'web' && (
        <View style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: PANEL_BORDER }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY, marginBottom: 16 }}>{tx('admin.sEODashboardPanel.auto.text.007', 'Performance Trend (7 Days)')}</Text>
          <div style={{ width: '100%', height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.vitals_trend.map(d => ({ ...d, day: d.date?.slice(5) || '' }))} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="lcpGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={colors.primary} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={colors.primary} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="fidGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={colors.accent} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={colors.accent} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="clsGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={colors.success} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={colors.success} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={PANEL_BORDER} />
                <XAxis dataKey="day" tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: SOFT_BG, border: `1px solid ${PANEL_BORDER}`, borderRadius: 8, fontSize: 11, color: TEXT_PRIMARY }}
                  labelStyle={{ color: TEXT_SECONDARY, fontWeight: 600 }}
                />
                <Legend wrapperStyle={{ fontSize: 10, color: TEXT_SECONDARY }} />
                <Area type="monotone" dataKey="avg_lcp" name="LCP (s)" stroke={colors.primary} fill="url(#lcpGrad)" strokeWidth={2} dot={false} />
                <Area type="monotone" dataKey="avg_fid" name="FID (ms)" stroke={colors.accent} fill="url(#fidGrad)" strokeWidth={2} dot={false} />
                <Area type="monotone" dataKey="avg_cls" name="CLS" stroke={colors.success} fill="url(#clsGrad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </View>
      )}

      {/* Page Performance Bar Chart */}
      {Platform.OS === 'web' && data.page_performance.length > 0 && (
        <View style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: PANEL_BORDER }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY, marginBottom: 16 }}>{tx('admin.sEODashboardPanel.auto.text.008', 'Page Performance Scores')}</Text>
          <div style={{ width: '100%', height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.page_performance} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={PANEL_BORDER} />
                <XAxis dataKey="page" tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: PANEL_BG, border: `1px solid ${PANEL_BORDER}`, borderRadius: 8, fontSize: 11, color: TEXT_PRIMARY }} />
                <Bar dataKey="score" name="Performance Score" fill={colors.primary} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </View>
      )}

      {/* Two-column layout: SEO Checklist + ASO Metrics */}
      {Platform.OS === 'web' ? (
        <div style={{ display: 'grid', gridTemplateColumns: isDesktop ? '1fr 1fr' : '1fr', gap: 16 } as any}>
          {/* SEO Checklist */}
          <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.sEODashboardPanel.auto.text.009', 'SEO Checklist')}</Text>
              <Text style={{ fontSize: 10, color: colors.successText, fontWeight: '700' }}>
                {data.checklist.filter(c => c.status).length}/{data.checklist.length} Passed
              </Text>
            </div>
            {data.checklist.map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 8, paddingBottom: 8, borderBottom: i < data.checklist.length - 1 ? `1px solid ${PANEL_BORDER}` : 'none' }} data-testid={`seo-check-${i}`}>
                <div style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: item.status ? `${colors.success}26` : `${colors.error}26`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Ionicons name={item.status ? 'checkmark' : 'close'} size={12} color={item.status ? colors.success : colors.error} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: '600', color: TEXT_MUTED }}>{item.item}</div>
                  <div style={{ fontSize: 10, color: TEXT_MUTED, marginTop: 1 }}>{item.detail}</div>
                </div>
              </div>
            ))}
          </div>

          {/* ASO & Sitemap */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="aso-metrics">
              <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY, marginBottom: 14 }}>{tx('admin.sEODashboardPanel.auto.text.010', 'App Store Optimization')}</Text>
              {[
                { label: 'Total Features', value: data.aso_metrics.total_features, icon: 'apps' },
                { label: 'Rating', value: `${data.aso_metrics.ratings_average}/5`, icon: 'star' },
                { label: 'Description Length', value: `${data.aso_metrics.description_length} chars`, icon: 'document-text' },
                { label: 'Keyword Density', value: `${data.aso_metrics.keyword_density}%`, icon: 'search' },
                { label: 'Screenshots', value: data.aso_metrics.screenshots_count, icon: 'images' },
                { label: 'Languages', value: data.aso_metrics.supported_languages, icon: 'language' },
              ].map((m, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 8, paddingBottom: 8, borderBottom: i < 5 ? `1px solid ${PANEL_BORDER}` : 'none' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Ionicons name={m.icon as any} size={14} color={TEXT_MUTED} />
                    <Text style={{ fontSize: 12, color: TEXT_MUTED }}>{m.label}</Text>
                  </div>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: TEXT_PRIMARY }}>{m.value}</Text>
                </div>
              ))}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
                {data.aso_metrics.categories.map(c => (
                  <div key={c} style={{ fontSize: 10, color: colors.primary, backgroundColor: `${colors.primary}1A`, padding: '3px 8px', borderRadius: 4, fontWeight: '600' }}>{c}</div>
                ))}
              </div>
            </div>

            {/* Sitemap Health */}
            <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="sitemap-health">
              <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY, marginBottom: 14 }}>{tx('admin.sEODashboardPanel.auto.text.011', 'Sitemap Health')}</Text>
              <div style={{ display: 'flex', gap: 12 }}>
                {[
                  { label: 'Total Pages', value: data.sitemap.total_pages, color: colors.primary },
                  { label: 'Feature Pages', value: data.sitemap.feature_pages, color: colors.accent },
                  { label: 'Static Pages', value: data.sitemap.static_pages, color: colors.successText },
                ].map(s => (
                  <div key={s.label} style={{ flex: 1, textAlign: 'center', backgroundColor: `${s.color}10`, borderRadius: 10, padding: 12 }}>
                    <div style={{ fontSize: 22, fontWeight: '800', color: s.color }}>{s.value}</div>
                    <div style={{ fontSize: 9, color: TEXT_MUTED, marginTop: 2, fontWeight: '600' }}>{s.label}</div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 10, color: TEXT_MUTED, marginTop: 10, textAlign: 'center' }}>
                Auto-updated when features are added/removed
              </div>
            </div>

            {/* Security Headers */}
            <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="security-headers">
              <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY, marginBottom: 14 }}>{tx('admin.sEODashboardPanel.auto.text.012', 'Security Headers')}</Text>
              {Object.entries(data.security_headers).map(([key, enabled], i) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 6, paddingBottom: 6 }}>
                  <div style={{ width: 18, height: 18, borderRadius: 4, backgroundColor: enabled ? `${colors.success}26` : `${colors.error}26`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={enabled ? 'checkmark' : 'close'} size={10} color={enabled ? colors.success : colors.error} />
                  </div>
                  <Text style={{ fontSize: 11, color: TEXT_MUTED, fontWeight: '500' }}>{key.replace(/_/g, '-')}</Text>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <View style={{ gap: 16 }}>
          {/* Mobile: simplified checklist */}
          <View style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: PANEL_BORDER }}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY, marginBottom: 8 }}>SEO Checklist: {data.checklist.filter(c => c.status).length}/{data.checklist.length}</Text>
            {data.checklist.map((item, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 }}>
                <Ionicons name={item.status ? 'checkmark-circle' : 'close-circle'} size={16} color={item.status ? colors.success : colors.error} />
                <Text style={{ fontSize: 12, color: TEXT_MUTED, flex: 1 }}>{item.item}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Lighthouse Auto-Auditor Section */}
      {Platform.OS === 'web' && (
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="lighthouse-section">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Ionicons name="flash" size={16} color={colors.warning} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.sEODashboardPanel.auto.text.013', 'Lighthouse Auto-Auditor')}</Text>
            </div>
            {data.lighthouse_summary ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success }} />
                <Text style={{ fontSize: 10, color: TEXT_MUTED }}>
                  {data.lighthouse_summary.total_audits} audit{data.lighthouse_summary.total_audits !== 1 ? 's' : ''} completed
                </Text>
              </div>
            ) : (
              <Text style={{ fontSize: 10, color: TEXT_MUTED }}>{tx('admin.sEODashboardPanel.auto.text.014', 'Waiting for first audit...')}</Text>
            )}
          </div>

          {data.lighthouse_summary ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 } as any}>
              {[
                { label: 'Performance', value: data.lighthouse_summary.avg_performance, color: data.lighthouse_summary.avg_performance >= 90 ? colors.success : data.lighthouse_summary.avg_performance >= 70 ? colors.warning : colors.error },
                { label: 'SEO', value: data.lighthouse_summary.avg_seo, color: data.lighthouse_summary.avg_seo >= 90 ? colors.success : data.lighthouse_summary.avg_seo >= 70 ? colors.warning : colors.error },
                { label: 'Security', value: data.lighthouse_summary.avg_security, color: data.lighthouse_summary.avg_security >= 90 ? colors.success : data.lighthouse_summary.avg_security >= 70 ? colors.warning : colors.error },
                { label: 'Avg TTFB', value: `${data.lighthouse_summary.avg_ttfb}s`, color: data.lighthouse_summary.avg_ttfb <= 0.8 ? colors.success : data.lighthouse_summary.avg_ttfb <= 1.8 ? colors.warning : colors.error },
              ].map((m, i) => (
                <div key={i} style={{ textAlign: 'center', padding: 12, borderRadius: 10, backgroundColor: AC.cardSoft, border: `1px solid ${PANEL_BORDER}` }}>
                  <div style={{ fontSize: 22, fontWeight: '800', color: m.color, letterSpacing: -0.5 }}>{m.value}</div>
                  <div style={{ fontSize: 9, color: TEXT_MUTED, marginTop: 4, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{m.label}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: 16, textAlign: 'center' }}>
              <Text style={{ fontSize: 12, color: TEXT_MUTED }}>{tx('admin.sEODashboardPanel.auto.text.015', 'First automated audit runs 30s after startup, then every 60 minutes')}</Text>
            </div>
          )}
        </div>
      )}

      {/* Lighthouse Score History Chart */}
      {Platform.OS === 'web' && lhHistory.length >= 2 && (
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="lighthouse-history-chart">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="trending-up" size={16} color={colors.primary} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.sEODashboardPanel.auto.text.016', 'Lighthouse Score Trends')}</Text>
            <Text style={{ fontSize: 10, color: TEXT_MUTED, marginLeft: 'auto' }}>{lhHistory.length} audits</Text>
          </div>
          <div style={{ width: '100%', height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={[...lhHistory].reverse().map(a => ({
                  time: typeof a.timestamp === 'string'
                    ? a.timestamp.slice(11, 16)
                    : new Date(a.timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
                  Performance: a.avg_performance_score,
                  SEO: a.avg_seo_score,
                  Security: a.avg_security_score,
                }))}
                margin={{ top: 8, right: 12, left: -16, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="perfGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={colors.primary} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={colors.primary} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="seoGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={colors.success} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={colors.success} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="secGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={colors.warning} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={colors.warning} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={PANEL_BORDER} />
                <XAxis dataKey="time" tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: PANEL_BG, border: `1px solid ${PANEL_BORDER}`, borderRadius: 8, fontSize: 11, color: TEXT_PRIMARY }}
                  labelStyle={{ color: TEXT_MUTED, fontWeight: 600 }}
                  formatter={(value: number) => [`${value}/100`, undefined]}
                />
                <Legend wrapperStyle={{ fontSize: 10, color: TEXT_MUTED }} />
                <Area type="monotone" dataKey="Performance" stroke={colors.primary} fill="url(#perfGrad)" strokeWidth={2} dot={{ r: 3, fill: colors.primary }} />
                <Area type="monotone" dataKey="SEO" stroke={colors.success} fill="url(#seoGrad)" strokeWidth={2} dot={{ r: 3, fill: colors.success }} />
                <Area type="monotone" dataKey="Security" stroke={colors.warning} fill="url(#secGrad)" strokeWidth={2} dot={{ r: 3, fill: colors.warning }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Auto-update notice */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 8 }}>
        <Ionicons name="sync" size={12} color={TEXT_MUTED} />
        <Text style={{ fontSize: 10, color: TEXT_MUTED }}>{tx('admin.sEODashboardPanel.auto.text.017', 'All data auto-collected. No manual input required. Sitemap auto-updates with feature changes.')}</Text>
      </View>
      </>)}
      </>)}
    </ScrollView>
  );
}
