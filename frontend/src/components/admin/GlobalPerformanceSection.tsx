import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, Platform, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface RegionResult {
  region_id: string;
  region_name: string;
  flag: string;
  avg_load_time: number;
  slow_pages: number;
  status: string;
  pages: { page: string; load_time: number | null; rating: string }[];
}

interface GPAData {
  analysis_id: string;
  timestamp: string;
  global_avg_load_time: number;
  regions_tested: number;
  fastest_region: { name: string; time: number } | null;
  slowest_region: { name: string; time: number } | null;
  cdn_status: { detected: boolean; provider: string | null; recommendation: string };
  cdn_recommendations: { provider: string; tier: string; features: string[]; estimated_improvement: string; setup_complexity: string }[];
  region_results: RegionResult[];
  optimization_tips: { tip: string; impact: string }[];
}

const statusColors: Record<string, string> = { fast: 'var(--app-success)', moderate: 'var(--app-warning)', slow: 'var(--app-error)', error: 'var(--app-text-muted)' };
const impactColors: Record<string, string> = { critical: 'var(--app-error)', high: 'var(--app-warning)', medium: 'var(--app-primary)', low: 'var(--app-text-muted)' };

export default function GlobalPerformanceSection({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [data, setData] = useState<GPAData | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [hasReport, setHasReport] = useState(true);
  // V2 Teal theme-driven panel tokens (replaces earlier dark-only hardcodes).
  const PANEL_BG = colors.card;
  const PANEL_BORDER = colors.border;
  const TEXT_PRIMARY = colors.text;
  const TEXT_MUTED = colors.textMuted;
  const TEXT_SECONDARY = colors.textSec;
  const SOFT_BG = colors.surfaceHover;

  const fetchLatest = () => {
    api.get('/admin/seo/global-performance/latest')
      .then(r => {
        if (r.data.status === 'no_reports') {
          setHasReport(false);
          setData(null);
        } else {
          setHasReport(true);
          setData(r.data);
        }
      })
      .catch(() => setHasReport(false))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchLatest(); }, []);

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const res = await api.post('/admin/seo/global-performance/analyze');
      setData(res.data);
      setHasReport(true);
    } catch (e) {
      console.error('Global performance analysis failed:', e);
    } finally {
      setAnalyzing(false);
    }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator size="large" color={'var(--app-success)'} />
      <Text style={{ color: TEXT_SECONDARY, marginTop: 12, fontSize: 13 }}>{tx('admin.globalPerformance.states.loading', 'Loading Global Performance...')}</Text>
    </View>
  );

  if (Platform.OS !== 'web') return (
    <View style={{ padding: 20 }}>
      <Text style={{ color: TEXT_PRIMARY, fontSize: 16, fontWeight: '700' }}>{tx('admin.globalPerformance.mobile.title', 'Global Performance')}</Text>
      <Text style={{ color: TEXT_MUTED, fontSize: 12, marginTop: 4 }}>{tx('admin.globalPerformance.mobile.desktopOnly', 'Available on desktop')}</Text>
    </View>
  );

  if (!hasReport || !data) return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 48, gap: 16 }} data-testid="gpa-no-report">
      <div style={{ width: 64, height: 64, borderRadius: 16, backgroundColor: 'rgba(16,185,129,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name="earth" size={28} color={'var(--app-success)'} />
      </div>
      <Text style={{ fontSize: 16, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.globalPerformance.states.noReportTitle', 'No Global Performance Report')}</Text>
      <Text style={{ fontSize: 12, color: TEXT_MUTED, textAlign: 'center', maxWidth: 400 }}>
        {tx('admin.globalPerformance.states.noReportSubtitle', 'Run a global analysis to measure page load times across 8 worldwide regions and get CDN recommendations.')}
      </Text>
      <TouchableOpacity onPress={runAnalysis} disabled={analyzing} data-testid="run-gpa-analysis-btn" testID="run-gpa-analysis-btn"
        style={{ backgroundColor: colors.success, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10, marginTop: 8, opacity: analyzing ? 0.6 : 1 }}>
        <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>
          {analyzing ? 'Analyzing 8 Regions...' : 'Run Global Performance Analysis'}
        </Text>
      </TouchableOpacity>
    </div>
  );

  const chartData = data.region_results.map(r => ({
    name: r.region_name.split('(')[0].trim(),
    time: r.avg_load_time,
    status: r.status,
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }} data-testid="gpa-section">
      {/* Summary Header */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 12, padding: 16, border: `1px solid ${PANEL_BORDER}`, textAlign: 'center' }} data-testid="gpa-global-avg">
          <div style={{ fontSize: 28, fontWeight: '800', color: data.global_avg_load_time <= 1.5 ? 'var(--app-success)' : data.global_avg_load_time <= 3 ? 'var(--app-warning)' : 'var(--app-error)' }}>
            {data.global_avg_load_time}s
          </div>
          <div style={{ fontSize: 10, color: TEXT_MUTED, fontWeight: '600', marginTop: 4 }}>GLOBAL AVG LOAD TIME</div>
        </div>
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 12, padding: 16, border: `1px solid ${PANEL_BORDER}`, textAlign: 'center' }} data-testid="gpa-fastest">
          <div style={{ fontSize: 16, fontWeight: '800', color: colors.successText }}>
            {data.fastest_region?.time}s
          </div>
          <div style={{ fontSize: 10, color: colors.successText, fontWeight: '600', marginTop: 2 }}>{data.fastest_region?.name}</div>
          <div style={{ fontSize: 9, color: TEXT_MUTED, marginTop: 2 }}>FASTEST REGION</div>
        </div>
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 12, padding: 16, border: `1px solid ${PANEL_BORDER}`, textAlign: 'center' }} data-testid="gpa-slowest">
          <div style={{ fontSize: 16, fontWeight: '800', color: colors.error }}>
            {data.slowest_region?.time}s
          </div>
          <div style={{ fontSize: 10, color: colors.error, fontWeight: '600', marginTop: 2 }}>{data.slowest_region?.name}</div>
          <div style={{ fontSize: 9, color: TEXT_MUTED, marginTop: 2 }}>SLOWEST REGION</div>
        </div>
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 12, padding: 16, border: `1px solid ${data.cdn_status.detected ? 'rgba(34,197,94,0.2)' : 'rgba(245,158,11,0.2)'}`, textAlign: 'center' }} data-testid="gpa-cdn-status">
          <Ionicons name={data.cdn_status.detected ? 'shield-checkmark' : 'warning'} size={20} color={data.cdn_status.detected ? 'var(--app-success)' : 'var(--app-warning)'} />
          <div style={{ fontSize: 12, fontWeight: '700', color: data.cdn_status.detected ? 'var(--app-success)' : 'var(--app-warning)', marginTop: 4 }}>
            {data.cdn_status.detected ? data.cdn_status.provider : 'No CDN'}
          </div>
          <div style={{ fontSize: 9, color: TEXT_MUTED, marginTop: 2 }}>CDN STATUS</div>
        </div>
      </div>

      {/* Regional Performance Chart */}
      <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="gpa-chart">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <Ionicons name="bar-chart" size={16} color={'var(--app-primary)'} />
          <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.globalPerformance.sections.regionalLoadTimes', 'Regional Load Times')}</Text>
          <TouchableOpacity onPress={runAnalysis} disabled={analyzing} data-testid="rerun-gpa-btn" testID="rerun-gpa-btn"
            style={{ marginLeft: 'auto', backgroundColor: colors.success, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6, opacity: analyzing ? 0.6 : 1 }}>
            <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>
              {analyzing ? 'Running...' : 'Re-run'}
            </Text>
          </TouchableOpacity>
        </div>
        <div style={{ width: '100%', height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={PANEL_BORDER} />
              <XAxis dataKey="name" tick={{ fill: TEXT_MUTED, fontSize: 9 }} axisLine={false} tickLine={false} angle={-15} textAnchor="end" height={50} />
              <YAxis tick={{ fill: TEXT_MUTED, fontSize: 10 }} axisLine={false} tickLine={false} label={{ value: 'seconds', position: 'insideTopLeft', style: { fill: TEXT_MUTED, fontSize: 9 } }} />
              <Tooltip contentStyle={{ backgroundColor: SOFT_BG, border: `1px solid ${PANEL_BORDER}`, borderRadius: 8, fontSize: 11, color: TEXT_PRIMARY }}
                formatter={(value: number) => [`${value}s`, 'Load Time']} />
              <Bar dataKey="time" name="Load Time" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, idx) => (
                  <Cell key={idx} fill={statusColors[entry.status] || colors.textMuted} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8 }}>
          {[{ label: 'Fast (<1.5s)', color: colors.successText }, { label: 'Moderate (1.5-3s)', color: colors.warningText }, { label: 'Slow (>3s)', color: colors.error }].map(l => (
            <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: l.color }} />
              <span style={{ fontSize: 9, color: TEXT_MUTED }}>{l.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Two columns: Region Details + CDN Recommendations */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: 16 }}>
        {/* Region Details */}
        <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="gpa-region-details">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="globe" size={16} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.globalPerformance.sections.regionDetails', 'Region Details')}</Text>
          </div>
          {data.region_results.map((region, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: i < data.region_results.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }} data-testid={`gpa-region-${region.region_id}`}>
              <div style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: `${statusColors[region.status]}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center' }}>{/^[A-Za-z]{2}$/.test(region.flag || '') ? <img src={`https://flagcdn.com/w40/${region.flag.toLowerCase()}.png`} alt={`${region.flag} flag`} style={{ width: 16, height: 12, borderRadius: 2, objectFit: 'cover' }} data-testid={`perf-region-flag-${region.flag.toLowerCase()}`} /> : '\u{1F30D}'}</span>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: '600', color: TEXT_SECONDARY }}>{region.region_name}</div>
                <div style={{ fontSize: 10, color: TEXT_MUTED }}>{region.slow_pages} slow page{region.slow_pages !== 1 ? 's' : ''}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 13, fontWeight: '700', color: statusColors[region.status] }}>{region.avg_load_time}s</div>
                <div style={{ fontSize: 9, color: statusColors[region.status], textTransform: 'uppercase', fontWeight: '600' }}>{region.status}</div>
              </div>
            </div>
          ))}
        </div>

        {/* CDN Recommendations + Optimization Tips */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="cdn-recommendations">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <Ionicons name="cloud" size={16} color={'var(--app-primary)'} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.globalPerformance.sections.cdnRecommendations', 'CDN Recommendations')}</Text>
            </div>
            {data.cdn_recommendations.map((cdn, i) => (
              <div key={i} style={{ padding: '10px 0', borderBottom: i < data.cdn_recommendations.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 13, fontWeight: '700', color: TEXT_PRIMARY }}>{cdn.provider}</span>
                  <span style={{ fontSize: 10, color: TEXT_MUTED, backgroundColor: SOFT_BG, padding: '2px 6px', borderRadius: 4 }}>{cdn.tier}</span>
                </div>
                <div style={{ fontSize: 10, color: colors.successText, marginTop: 4 }}>~{cdn.estimated_improvement} improvement</div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                  {cdn.features.slice(0, 4).map(f => (
                    <span key={f} style={{ fontSize: 9, color: colors.primary, backgroundColor: 'rgba(59,130,246,0.1)', padding: '2px 6px', borderRadius: 3 }}>{f}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div style={{ backgroundColor: PANEL_BG, borderRadius: 16, padding: 20, border: `1px solid ${PANEL_BORDER}` }} data-testid="optimization-tips">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <Ionicons name="rocket" size={16} color={'var(--app-warning)'} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: TEXT_PRIMARY }}>{tx('admin.globalPerformance.sections.optimizationTips', 'Optimization Tips')}</Text>
            </div>
            {data.optimization_tips.map((tip, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: i < data.optimization_tips.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                <div style={{ backgroundColor: `${impactColors[tip.impact] || colors.border}20`, padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>
                  <span style={{ fontSize: 9, fontWeight: '700', color: impactColors[tip.impact] || colors.textMuted, textTransform: 'uppercase' }}>{tip.impact}</span>
                </div>
                <span style={{ fontSize: 11, color: TEXT_SECONDARY }}>{tip.tip}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CDN Status Banner */}
      <div style={{ backgroundColor: data.cdn_status.detected ? 'rgba(34,197,94,0.06)' : 'rgba(245,158,11,0.06)', borderRadius: 12, padding: 14, border: `1px solid ${data.cdn_status.detected ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.15)'}`, display: 'flex', alignItems: 'center', gap: 10 }} data-testid="cdn-banner">
        <Ionicons name={data.cdn_status.detected ? 'checkmark-circle' : 'information-circle'} size={16} color={data.cdn_status.detected ? 'var(--app-success)' : 'var(--app-warning)'} />
        <span style={{ fontSize: 11, color: data.cdn_status.detected ? 'var(--app-success)' : 'var(--app-warning)' }}>{data.cdn_status.recommendation}</span>
      </div>
    </div>
  );
}
