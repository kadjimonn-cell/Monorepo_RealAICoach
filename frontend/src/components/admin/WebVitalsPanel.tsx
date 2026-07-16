import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { useHybridPolling } from '../../hooks/useHybridPolling';

interface Metric {
  key: string; label: string; value: number; unit: string;
  grade: 'good' | 'needs-improvement' | 'poor';
  good: number; poor: number; description: string;
}
interface TrendPoint { date: string; lcp: number; fid: number; cls: number; fcp: number; inp: number; samples: number; }
interface DeviceData { lcp: number; cls: number; inp: number; samples: number; }
interface PageData { url: string; lcp: number; cls: number; samples: number; }
interface DashboardData {
  overall_grade: string; metrics: Metric[]; trend: TrendPoint[];
  devices: Record<string, DeviceData>; pages: PageData[]; total_samples_24h: number;
}

const VITALS_POLL_MAX_INTERVAL_MS = 30000;
const VITALS_POLL_MIN_INTERVAL_MS = 12000;

const GRADE_COLORS = {
  good: 'var(--app-success)', // @theme-ok brand/role/state identifier
  'needs-improvement': 'var(--app-warning)', // @theme-ok brand/role/state identifier
  poor: 'var(--app-error)', // @theme-ok brand/role/state identifier
} as const;

const GRADE_LABELS = {
  good: 'Good',
  'needs-improvement': 'Needs Work',
  poor: 'Poor',
};

const GRADE_ICONS = {
  good: 'checkmark-circle',
  'needs-improvement': 'warning',
  poor: 'alert-circle',
};

function GaugeBar({ value, good, poor, grade }: { value: number; good: number; poor: number; grade: string }) {
  const max = poor * 1.5;
  const pct = Math.min(100, (value / max) * 100);
  const color = GRADE_COLORS[grade as keyof typeof GRADE_COLORS] || 'var(--app-text-muted)';
  return (
    <View style={{ height: 6, borderRadius: 3, backgroundColor: 'rgba(148,163,184,0.15)', overflow: 'hidden', marginTop: 8 }}>
      <View style={{ height: 6, borderRadius: 3, backgroundColor: color, width: `${pct}%` as any, transition: 'width 0.6s ease' } as any} />
    </View>
  );
}

function SparkLine({ data, dataKey, color }: { data: TrendPoint[]; dataKey: string; color: string }) {
  if (!Array.isArray(data) || data.length < 2) return null;
  const values = data.map(d => (d as any)[dataKey] || 0);
  const max = Math.max(...values) || 1;
  const min = Math.min(...values);
  const range = max - min || 1;
  const w = 200;
  const h = 40;
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(' ');
  const fillPoints = `0,${h} ${points} ${w},${h}`;

  if (Platform.OS !== 'web') return null;
  return (
    <View style={{ width: w, height: h }}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' } as any}>
        <defs>
          <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={fillPoints} fill={`url(#grad-${dataKey})`} />
        <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {values.length > 0 && (
          <circle cx={(values.length - 1) / (values.length - 1) * w} cy={h - ((values[values.length - 1] - min) / range) * (h - 4) - 2} r="3" fill={color} />
        )}
      </svg>
    </View>
  );
}

interface AlertRecord {
  type: string;
  timestamp: string;
  degraded_metrics: { metric: string; value: number; threshold: number; unit: string; severity: string }[];
  sample_count: number;
  recipients: string[];
}
interface AlertSettings {
  enabled: boolean;
  recipients: string[];
  cooldown_hours: number;
  min_samples: number;
}

export default function WebVitalsPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedMetric, setSelectedMetric] = useState('LCP');
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [alertSettings, setAlertSettings] = useState<AlertSettings>({ enabled: true, recipients: [], cooldown_hours: 6, min_samples: 5 });
  const [savingSettings, setSavingSettings] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [dashRes, alertRes] = await Promise.all([
        api.get('/admin/web-vitals/dashboard'),
        api.get('/admin/web-vitals/alerts'),
      ]);
      setData(dashRes.data);
      setAlerts(alertRes.data.alerts || []);
      setAlertSettings(alertRes.data.settings || { enabled: true, recipients: [], cooldown_hours: 6, min_samples: 5 });
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load Web Vitals');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/web-vitals/hybrid-refresh',
    onTick: fetchData,
    runOnMount: false,
    slowIntervalMs: VITALS_POLL_MAX_INTERVAL_MS,
    fastIntervalMs: VITALS_POLL_MIN_INTERVAL_MS,
  });

  const toggleAlerts = async () => {
    setSavingSettings(true);
    try {
      await api.put('/admin/web-vitals/alerts/settings', { enabled: !alertSettings.enabled });
      setAlertSettings(prev => ({ ...prev, enabled: !prev.enabled }));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/WebVitalsPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setSavingSettings(false);
    }
  };

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
        <Text style={{ color: colors.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.webVitalsPanel.auto.text.001', 'Loading performance metrics...')}</Text>
      </View>
    );
  }

  if (error || !data) {
    return (
      <View style={{ padding: 20, alignItems: 'center' }}>
        <Ionicons name="alert-circle" size={32} color={'var(--app-error)'} />
        <Text style={{ color: colors.error, marginTop: 8, fontSize: 14 }}>{error || 'No data'}</Text>
        <TouchableOpacity onPress={fetchData} style={{ marginTop: 12, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.primary }} accessibilityLabel={tx('admin.webVitalsPanel.auto.accessibility.001', 'Retry')}>
          <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '600' }}>{tx('admin.webVitalsPanel.auto.text.002', 'Retry')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const overallColor = GRADE_COLORS[data.overall_grade as keyof typeof GRADE_COLORS] || colors.textMuted;
  const coreMetrics = (data.metrics || []).slice(0, 4); // LCP, FID, CLS, INP
  const extraMetrics = (data.metrics || []).slice(4); // FCP, TTFB
  const selectedTrend = data.trend || [];

  return (
    <ScrollView style={{ flex: 1, padding: 16 }} data-testid="web-vitals-panel" testID="web-vitals-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <View>
          <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text }}>{tx('admin.webVitalsPanel.auto.text.003', 'Core Web Vitals')}</Text>
          <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>{tx('admin.webVitalsPanel.auto.text.004', 'Real user performance metrics from browser sessions')}</Text>
        </View>
        <TouchableOpacity onPress={fetchData} style={{ padding: 8, borderRadius: 8, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }} data-testid="vitals-refresh-btn" testID="vitals-refresh-btn">
          <Ionicons name="refresh" size={18} color={colors.textMuted} />
        </TouchableOpacity>
      </View>

      {/* Overall Grade + Samples */}
      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20 }}>
        <View style={{ flex: 1, padding: 16, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(overallColor, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(overallColor, '30'), flexDirection: 'row', alignItems: 'center', gap: 12 }} data-testid="vitals-overall-grade" testID="vitals-overall-grade">
          <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: (globalThis as any).__alphaColor(overallColor, '20'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={GRADE_ICONS[data.overall_grade as keyof typeof GRADE_ICONS] as any || 'help-circle'} size={24} color={overallColor} />
          </View>
          <View>
            <Text style={{ fontSize: 20, fontWeight: '800', color: overallColor }}>
              {(GRADE_LABELS[data.overall_grade as keyof typeof GRADE_LABELS] || data.overall_grade).toUpperCase()}
            </Text>
            <Text style={{ fontSize: 11, color: colors.textMuted }}>{tx('admin.webVitalsPanel.auto.text.005', 'Overall Assessment')}</Text>
          </View>
        </View>
        <View style={{ flex: 1, padding: 16, borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, justifyContent: 'center' }}>
          <Text style={{ fontSize: 28, fontWeight: '800', color: colors.text }}>{data.total_samples_24h}</Text>
          <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>{tx('admin.webVitalsPanel.auto.text.006', 'Samples (24h)')}</Text>
        </View>
      </View>

      {/* Core Metrics Grid */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {coreMetrics.map(metric => {
          const mColor = GRADE_COLORS[metric.grade] || colors.textMuted;
          const isSelected = selectedMetric === metric.key;
          return (
            <TouchableOpacity accessibilityLabel={tx('admin.webVitalsPanel.auto.accessibility.002', 'Select web vitals metric')}
              key={metric.key}
              onPress={() => setSelectedMetric(metric.key)}
              style={{
                flex: 1, minWidth: 180, padding: 16, borderRadius: 14,
                backgroundColor: isSelected ? (globalThis as any).__alphaColor(mColor, '10') : colors.surface,
                borderWidth: 1.5, borderColor: isSelected ? (globalThis as any).__alphaColor(mColor, '40') : colors.border,
              }}
              data-testid={`vitals-metric-${metric.key.toLowerCase()}`} testID={`vitals-metric-${metric.key.toLowerCase()}`}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: colors.textMuted, letterSpacing: 0.5 }}>{metric.key}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(mColor, '15') }}>
                  <Ionicons name={GRADE_ICONS[metric.grade] as any} size={12} color={mColor} />
                  <Text style={{ fontSize: 10, fontWeight: '700', color: mColor }}>{GRADE_LABELS[metric.grade]}</Text>
                </View>
              </View>
              <Text style={{ fontSize: 28, fontWeight: '800', color: colors.text, marginTop: 8 }}>
                {metric.value}{metric.unit}
              </Text>
              <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }} numberOfLines={1}>{metric.description}</Text>
              <GaugeBar value={metric.value} good={metric.good} poor={metric.poor} grade={metric.grade} />
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 }}>
                <Text style={{ fontSize: 9, color: colors.successText }}>Good: ≤{metric.good}{metric.unit}</Text>
                <Text style={{ fontSize: 9, color: colors.error }}>Poor: {'>'}{metric.poor}{metric.unit}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* 7-Day Trend */}
      <View style={{ padding: 16, borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, marginBottom: 20 }} data-testid="vitals-trend-chart" testID="vitals-trend-chart">
        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('admin.webVitalsPanel.auto.text.007', '7-Day Trend')}</Text>
        <View style={{ flexDirection: 'row', gap: 12, marginBottom: 12 }}>
          {['LCP', 'CLS', 'INP'].map(key => (
            <TouchableOpacity accessibilityLabel={tx('admin.webVitalsPanel.auto.accessibility.003', 'key')}
              key={key}
              onPress={() => setSelectedMetric(key)}
              style={{ paddingHorizontal: 12, paddingVertical: 4, borderRadius: 12, backgroundColor: selectedMetric === key ? colors.primarySoft : 'transparent', borderWidth: 1, borderColor: selectedMetric === key ? (globalThis as any).__alphaColor(colors.primary, '40') : colors.border }}
            >
              <Text style={{ fontSize: 11, fontWeight: '700', color: selectedMetric === key ? 'var(--app-primary)' : colors.textMuted }}>{key}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <SparkLine
          data={selectedTrend}
          dataKey={selectedMetric.toLowerCase()}
          color={GRADE_COLORS[(data.metrics?.find(m => m.key === selectedMetric)?.grade || 'good') as keyof typeof GRADE_COLORS]}
        />
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
          {selectedTrend.length > 0 && <Text style={{ fontSize: 10, color: colors.textMuted }}>{selectedTrend[0].date}</Text>}
          {selectedTrend.length > 1 && <Text style={{ fontSize: 10, color: colors.textMuted }}>{selectedTrend[selectedTrend.length - 1].date}</Text>}
        </View>
      </View>

      {/* Bottom Row: Device Breakdown + Top Pages */}
      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20 }}>
        {/* Device Breakdown */}
        <View style={{ flex: 1, padding: 16, borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }} data-testid="vitals-device-breakdown" testID="vitals-device-breakdown">
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('admin.webVitalsPanel.auto.text.008', 'Device Performance')}</Text>
          {Object.entries(data.devices || {}).map(([device, d]: [string, any]) => (
            <View key={device} style={{ marginBottom: 12, padding: 12, borderRadius: 10, backgroundColor: colors.background || 'var(--app-primary)' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Ionicons name={device === 'mobile' ? 'phone-portrait' : 'desktop'} size={16} color={'var(--app-primary)'} />
                <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text, textTransform: 'capitalize' }}>{device}</Text>
                <Text style={{ fontSize: 11, color: colors.textMuted, marginLeft: 'auto' as any }}>{d.samples} samples</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 16 }}>
                <View>
                  <Text style={{ fontSize: 10, color: colors.textMuted }}>{tx('admin.webVitalsPanel.auto.text.009', 'LCP')}</Text>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: GRADE_COLORS[d.lcp <= 2.5 ? 'good' : d.lcp <= 4 ? 'needs-improvement' : 'poor'] }}>{d.lcp}s</Text>
                </View>
                <View>
                  <Text style={{ fontSize: 10, color: colors.textMuted }}>{tx('admin.webVitalsPanel.auto.text.010', 'CLS')}</Text>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: GRADE_COLORS[d.cls <= 0.1 ? 'good' : d.cls <= 0.25 ? 'needs-improvement' : 'poor'] }}>{d.cls}</Text>
                </View>
                <View>
                  <Text style={{ fontSize: 10, color: colors.textMuted }}>{tx('admin.webVitalsPanel.auto.text.011', 'INP')}</Text>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: GRADE_COLORS[d.inp <= 200 ? 'good' : d.inp <= 500 ? 'needs-improvement' : 'poor'] }}>{d.inp}ms</Text>
                </View>
              </View>
            </View>
          ))}
        </View>

        {/* Top Pages */}
        <View style={{ flex: 1, padding: 16, borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }} data-testid="vitals-top-pages" testID="vitals-top-pages">
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('admin.webVitalsPanel.auto.text.012', 'Page Performance')}</Text>
          {(data.pages || []).map((page, i) => {
            const lcpColor = GRADE_COLORS[page.lcp <= 2.5 ? 'good' : page.lcp <= 4 ? 'needs-improvement' : 'poor'];
            return (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: i < (data.pages || []).length - 1 ? 1 : 0, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '40') }}>
                <Text style={{ flex: 1, fontSize: 12, color: colors.text, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }} numberOfLines={1}>{page.url}</Text>
                <Text style={{ fontSize: 12, fontWeight: '700', color: lcpColor, marginLeft: 12, minWidth: 45, textAlign: 'right' as any }}>{page.lcp}s</Text>
                <Text style={{ fontSize: 10, color: colors.textMuted, marginLeft: 8, minWidth: 20 }}>{page.samples}</Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Extra Metrics */}
      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20 }}>
        {extraMetrics.map(metric => {
          const mColor = GRADE_COLORS[metric.grade] || colors.textMuted;
          return (
            <View key={metric.key} style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted }}>{metric.key}</Text>
                <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(mColor, '15') }}>
                  <Text style={{ fontSize: 9, fontWeight: '700', color: mColor }}>{GRADE_LABELS[metric.grade]}</Text>
                </View>
              </View>
              <Text style={{ fontSize: 22, fontWeight: '800', color: colors.text, marginTop: 4 }}>{metric.value}{metric.unit}</Text>
              <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>{metric.description}</Text>
            </View>
          );
        })}
      </View>

      {/* Info */}
      <View style={{ padding: 12, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '08'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '20'), marginBottom: 20 }}>
        <Text style={{ fontSize: 11, color: colors.textMuted, lineHeight: 16 }}>{tx('admin.webVitalsPanel.auto.text.013', 'Metrics are collected from real user browser sessions using the Web Vitals API. Thresholds follow Google\'s Core Web Vitals program. Data refreshes automatically as users interact with the platform.')}</Text>
      </View>

      {/* Performance Alerts Section */}
      <View style={{ padding: 16, borderRadius: 14, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, marginBottom: 20 }} data-testid="vitals-alerts-section" testID="vitals-alerts-section">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <View>
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.webVitalsPanel.auto.text.014', 'Performance Alerts')}</Text>
            <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>{tx('admin.webVitalsPanel.auto.text.015', 'Email notifications when metrics degrade below "Good" threshold')}</Text>
          </View>
          <TouchableOpacity
            onPress={toggleAlerts}
            disabled={savingSettings}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: alertSettings.enabled ? colors.successSoft : colors.background || 'var(--app-primary)', borderWidth: 1, borderColor: alertSettings.enabled ? (globalThis as any).__alphaColor(colors.success, '40') : colors.border }}
            data-testid="vitals-alert-toggle" testID="vitals-alert-toggle"
          >
            <Ionicons name={alertSettings.enabled ? 'notifications' : 'notifications-off'} size={16} color={alertSettings.enabled ? 'var(--app-success)' : colors.textMuted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: alertSettings.enabled ? 'var(--app-success)' : colors.textMuted }}>
              {savingSettings ? 'Saving...' : alertSettings.enabled ? 'Enabled' : 'Disabled'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Alert Config Info */}
        <View style={{ flexDirection: 'row', gap: 12, marginBottom: 12 }}>
          <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: 8, backgroundColor: colors.background || 'var(--app-primary)' }}>
            <Ionicons name="time" size={14} color={colors.textMuted} />
            <Text style={{ fontSize: 11, color: colors.textMuted }}>Check every <Text style={{ fontWeight: '700', color: colors.text }}>{tx('admin.webVitalsPanel.auto.text.016', '2 hours')}</Text></Text>
          </View>
          <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: 8, backgroundColor: colors.background || 'var(--app-primary)' }}>
            <Ionicons name="hourglass" size={14} color={colors.textMuted} />
            <Text style={{ fontSize: 11, color: colors.textMuted }}>Cooldown: <Text style={{ fontWeight: '700', color: colors.text }}>{alertSettings.cooldown_hours}h</Text></Text>
          </View>
          <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: 8, backgroundColor: colors.background || 'var(--app-primary)' }}>
            <Ionicons name="bar-chart" size={14} color={colors.textMuted} />
            <Text style={{ fontSize: 11, color: colors.textMuted }}>Min samples: <Text style={{ fontWeight: '700', color: colors.text }}>{alertSettings.min_samples}</Text></Text>
          </View>
        </View>

        {/* Recipients */}
        {(alertSettings.recipients || []).length > 0 && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12 }}>
            <Ionicons name="mail" size={14} color={colors.textMuted} />
            <Text style={{ fontSize: 11, color: colors.textMuted }}>{tx('admin.webVitalsPanel.auto.text.017', 'Recipients:')}</Text>
            {(alertSettings.recipients || []).map((r, i) => (
              <View key={i} style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }}>
                <Text style={{ fontSize: 11, color: colors.primary, fontWeight: '600' }}>{r}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Alert History */}
        {alerts.length > 0 ? (
          <View>
            <Text style={{ fontSize: 12, fontWeight: '700', color: colors.textMuted, marginBottom: 8, letterSpacing: 0.5 }}>{tx('admin.webVitalsPanel.auto.text.018', 'RECENT ALERTS')}</Text>
            {alerts.slice(0, 5).map((alert, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, padding: 10, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.error, '08'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '15'), marginBottom: 6 }}>
                <Ionicons name="warning" size={16} color={'var(--app-warning)'} style={{ marginTop: 2 }} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 12, color: colors.text, fontWeight: '600' }}>
                    {(alert.degraded_metrics || []).map(m => m.metric).join(', ')} degraded
                  </Text>
                  <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>
                    {new Date(alert.timestamp).toLocaleDateString()} at {new Date(alert.timestamp).toLocaleTimeString()} — {alert.sample_count} samples
                  </Text>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
                    {(alert.degraded_metrics || []).map((m, j) => {
                      const mColor = m.severity === 'poor' ? 'var(--app-error)' : 'var(--app-warning)';
                      return (
                        <Text key={j} style={{ fontSize: 10, color: mColor, fontWeight: '700' }}>
                          {m.metric}: {m.value}{m.unit} (threshold: {m.threshold}{m.unit})
                        </Text>
                      );
                    })}
                  </View>
                </View>
              </View>
            ))}
          </View>
        ) : (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.success, '08') }}>
      <AutoFixBanner domain="web_vitals" />
            <Ionicons name="checkmark-circle" size={16} color={'var(--app-success)'} />
            <Text style={{ fontSize: 12, color: colors.successText, fontWeight: '600' }}>{tx('admin.webVitalsPanel.auto.text.019', 'No performance alerts in the last 30 days')}</Text>
          </View>
        )}
      </View>
    </ScrollView>
  );
}
