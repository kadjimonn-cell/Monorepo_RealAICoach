import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, Switch, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useHybridPolling } from '../../hooks/useHybridPolling';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
interface Issue {
  id: string; severity: string; title: string;
  metric: string; value: number; target: number; auto_fixable: boolean;
}
interface TrendPoint { time: string; lcp: number; fcp: number; ttfb: number; samples: number; }
interface FixResult { fix_id: string; status: string; details: string; }
interface FixRecord { timestamp: string; results: FixResult[]; triggered_by: string; }
interface GuardianData {
  status: string; status_label: string; status_color: string;
  target_load_time: number; auto_fix_enabled: boolean;
  current_metrics: { lcp: number; fcp: number; ttfb: number; cls: number; inp: number; p95_lcp: number };
  samples_1h: number; samples_24h: number;
  issues: Issue[]; trend: TrendPoint[]; recent_fixes: FixRecord[];
}

const PERFORMANCE_POLL_MAX_INTERVAL_MS = 30000;
const PERFORMANCE_POLL_MIN_INTERVAL_MS = 12000;

const STATUS_CONFIG: Record<string, { bg: string; icon: string; pulse: boolean }> = {
  healthy: { bg: 'var(--app-success)' as any, icon: 'shield-checkmark', pulse: false },
  warning: { bg: 'var(--app-warning)' as any, icon: 'warning', pulse: true },
  critical: { bg: 'var(--app-error)' as any, icon: 'alert-circle', pulse: true },
  no_data: { bg: 'var(--app-bg)' as any, icon: 'help-circle', pulse: false },
};

function MetricCard({ label, value, unit, target, color, cardBg, mutedText, subtleText }: {
  label: string; value: number; unit: string; target: number; color: string; cardBg: string; mutedText: string; subtleText: string;
}) {
  const isGood = unit === 's' ? value <= target : value <= target;
  const pct = Math.min(100, (value / (target * 2)) * 100);
  return (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: cardBg, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: isGood ? 'var(--app-success-soft)' as any : 'var(--app-warning-soft)' as any }} data-testid={`metric-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`metric-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <Text style={{ fontSize: 11, color: mutedText, fontWeight: '600', letterSpacing: 0.5, textTransform: 'uppercase' }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', marginTop: 4, gap: 2 }}>
        <Text style={{ fontSize: 28, fontWeight: '800', color }}>{value.toFixed(2)}</Text>
        <Text style={{ fontSize: 13, color: mutedText, fontWeight: '600' }}>{unit}</Text>
      </View>
      <View style={{ height: 4, borderRadius: 2, backgroundColor: 'var(--app-border)' as any, marginTop: 8, overflow: 'hidden' }}>
        <View style={{ height: 4, borderRadius: 2, backgroundColor: isGood ? 'var(--app-success)' as any : 'var(--app-warning)' as any, width: `${pct}%` as any }} />
      </View>
      <Text style={{ fontSize: 10, color: subtleText, marginTop: 4 }}>Target: {target}{unit}</Text>
    </View>
  );
}

function TrendChart({ data, targetLine }: { data: TrendPoint[]; targetLine: number }) {
  if (Platform.OS !== 'web' || !data || data.length < 2) return null;
  const w = 500, h = 100, pad = 20;
  const values = data.map(d => d.lcp);
  const max = Math.max(...values, targetLine * 1.5) || 1;
  const points = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - 2 * pad);
    const y = h - pad - ((v / max) * (h - 2 * pad));
    return `${x},${y}`;
  }).join(' ');
  const targetY = h - pad - ((targetLine / max) * (h - 2 * pad));
  return (
    <View style={{ width: w, height: h + 20 }} data-testid="trend-chart" testID="trend-chart">
      <svg width={w} height={h + 20} viewBox={`0 0 ${w} ${h + 20}`}>
        <defs>
          <linearGradient id="lcpGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={'var(--app-primary)'} stopOpacity="0.3" />
            <stop offset="100%" stopColor={'var(--app-primary)'} stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Target line */}
        <line x1={pad} y1={targetY} x2={w - pad} y2={targetY} stroke={'var(--app-error)'} strokeWidth="1" strokeDasharray="4,4" opacity="0.6" />
        <text x={w - pad + 4} y={targetY + 4} fill={'var(--app-error)'} fontSize="9" fontFamily="monospace">{targetLine}s</text>
        {/* Area fill */}
        <polygon points={`${pad},${h - pad} ${points} ${w - pad},${h - pad}`} fill="url(#lcpGrad)" />
        {/* Line */}
        <polyline points={points} fill="none" stroke={'var(--app-primary)'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {/* Dots */}
        {values.map((v, i) => {
          const x = pad + (i / (values.length - 1)) * (w - 2 * pad);
          const y = h - pad - ((v / max) * (h - 2 * pad));
          const c = v <= targetLine ? 'var(--app-success)' : 'var(--app-error)';
          return <circle key={i} cx={x} cy={y} r="3" fill={c} />;
        })}
        {/* X labels */}
        {data.filter((_, i) => i % Math.ceil(data.length / 6) === 0).map((d, i) => {
          const idx = data.indexOf(d);
          const x = pad + (idx / (data.length - 1)) * (w - 2 * pad);
          const label = d.time.split('T')[1] || d.time;
          return <text key={i} x={x} y={h + 10} fill="var(--app-text-muted)" fontSize="9" textAnchor="middle" fontFamily="monospace">{label}</text>;
        })}
      </svg>
    </View>
  );
}

interface AlertRecord {
  timestamp: string;
  type: string;
  level: string;
  alerts: { metric: string; value: number; level: string; threshold: number; unit: string }[];
  samples: number;
}

export default function PerformanceGuardianPanel({ colors, darkMode = false }: { colors: any; darkMode?: boolean }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const [data, setData] = useState<GuardianData | null>(null);
  const [loading, setLoading] = useState(true);
  const [fixing, setFixing] = useState(false);
  const [fixResult, setFixResult] = useState<any>(null);
  const [autoFixEnabled, setAutoFixEnabled] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [alertHistory, setAlertHistory] = useState<AlertRecord[]>([]);
  const [activeAlert, setActiveAlert] = useState<any>(null);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await api.get('/admin/performance-guardian/alerts?limit=10');
      setAlertHistory(res.data.alerts || []);
      setActiveAlert(res.data.active_alert || null);
    } catch (e) {
      console.error('Alerts fetch failed:', e);
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get('/admin/performance-guardian/status');
      setData(res.data);
      setAutoFixEnabled(res.data.auto_fix_enabled);
    } catch (e) {
      console.error('Guardian fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStatus(); fetchAlerts(); }, [fetchStatus, fetchAlerts]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/performance-guardian/hybrid-refresh',
    onTick: async () => {
      await Promise.all([fetchStatus(), fetchAlerts()]);
    },
    runOnMount: false,
    slowIntervalMs: PERFORMANCE_POLL_MAX_INTERVAL_MS,
    fastIntervalMs: PERFORMANCE_POLL_MIN_INTERVAL_MS,
  });

  const runAutoFix = async () => {
    setFixing(true);
    setFixResult(null);
    try {
      const res = await api.post('/admin/performance-guardian/auto-fix', { run_all: true });
      setFixResult(res.data);
      setTimeout(fetchStatus, 5000);
    } catch (e: any) {
      setFixResult({ success: false, message: e.message || 'Auto-fix failed' });
    } finally {
      setFixing(false);
    }
  };

  const toggleAutoFix = async (val: boolean) => {
    setSettingsLoading(true);
    try {
      await api.put('/admin/performance-guardian/settings', { auto_fix_enabled: val });
      setAutoFixEnabled(val);
    } catch (e) {
      console.error('Failed to update settings:', e);
    } finally {
      setSettingsLoading(false);
    }
  };

  const isDark = Boolean(darkMode);
  const cardBg = isDark ? AC.card : colors.surface;
  const softCardBg = isDark ? AC.cardSoft : colors.surfaceHover;
  const mutedText = isDark ? AC.textSec : AC.textDim;
  const subtleText = isDark ? AC.textMuted : AC.borderStrong;
  const softBlueBg = isDark ? AC.infoSoft : colors.infoSoft;
  const softBlueBorder = isDark ? AC.info : colors.info;

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }} data-testid="guardian-loading" testID="guardian-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: mutedText, marginTop: 12, fontSize: 13 }}>{tx('admin.performanceGuardianPanel.auto.text.001', 'Loading Performance Guardian...')}</Text>
      </View>
    );
  }

  const cfg = STATUS_CONFIG[data?.status || 'no_data'];
  const metrics = data?.current_metrics;
  const target = data?.target_load_time || 2.0;

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, gap: 16 }} data-testid="performance-guardian-panel" testID="performance-guardian-panel">
      <AutoFixBanner domain="perf_advisor" />
      {/* Header with status beacon */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="guardian-header" testID="guardian-header">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: cfg.bg, justifyContent: 'center', alignItems: 'center', ...(cfg.pulse ? { shadowColor: cfg.bg, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.5, shadowRadius: 12 } : {}) } as any} data-testid="status-beacon" testID="status-beacon">
            <Ionicons name={cfg.icon as any} size={24} color={colors.primaryText} />
          </View>
          <View>
            <Text style={{ fontSize: 20, fontWeight: '800', color: colors.text }}>{tx('admin.performanceGuardianPanel.auto.text.002', 'Performance Guardian')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: cfg.bg }} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: cfg.bg }}>{data?.status_label || 'Unknown'}</Text>
              <Text style={{ fontSize: 11, color: mutedText }}>
                {data?.samples_1h || 0} samples/1h | {data?.samples_24h || 0} samples/24h
              </Text>
            </View>
          </View>
        </View>
        <TouchableOpacity onPress={fetchStatus} style={{ padding: 8 }} data-testid="refresh-btn" testID="refresh-btn">
          <Ionicons name="refresh" size={20} color={mutedText} />
        </TouchableOpacity>
      </View>

      {/* Target badge */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: softBlueBg, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: softBlueBorder }} data-testid="target-badge" testID="target-badge">
        <Ionicons name="flag" size={16} color={colors.primary} />
        <Text style={{ fontSize: 13, fontWeight: '700', color: colors.primary }}>Target: Page load under {target}s</Text>
        <Text style={{ fontSize: 11, color: mutedText, marginLeft: 'auto' as any }}>{tx('admin.performanceGuardianPanel.auto.text.003', 'Enterprise SLA')}</Text>
      </View>

      {/* Active Alert Banner */}
      {activeAlert && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14, borderRadius: 12, backgroundColor: activeAlert.level === 'CRITICAL' ? colors.errorSoft : colors.warningSoft, borderWidth: 1, borderColor: activeAlert.level === 'CRITICAL' ? colors.error : colors.warning }} data-testid="active-alert-banner" testID="active-alert-banner">
          <Ionicons name={activeAlert.level === 'CRITICAL' ? 'alert-circle' : 'warning'} size={22} color={activeAlert.level === 'CRITICAL' ? colors.error : colors.warning} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 14, fontWeight: '800', color: activeAlert.level === 'CRITICAL' ? colors.error : colors.warning }}>
              {activeAlert.level} ALERT
            </Text>
            <Text style={{ fontSize: 12, color: colors.text, marginTop: 2 }}>
              {activeAlert.metric} at {activeAlert.value}s (threshold: {activeAlert.threshold}s)
            </Text>
          </View>
          <View style={{ backgroundColor: activeAlert.level === 'CRITICAL' ? colors.error : colors.warning, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
            <Text style={{ fontSize: 10, fontWeight: '800', color: colors.primaryText }}>{tx('admin.performanceGuardianPanel.auto.text.004', 'ACTIVE')}</Text>
          </View>
        </View>
      )}

      {/* Real-time metrics */}
      <View style={{ gap: 8 }}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.performanceGuardianPanel.auto.text.005', 'Real-Time Metrics (Last Hour)')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <MetricCard label="Page Load (LCP)" value={metrics?.lcp || 0} unit="s" target={target} color={cfg.bg} cardBg={cardBg} mutedText={mutedText} subtleText={subtleText} />
          <MetricCard label="First Paint (FCP)" value={metrics?.fcp || 0} unit="s" target={1.0} color={metrics?.fcp && metrics.fcp <= 1.0 ? colors.success : colors.warning} cardBg={cardBg} mutedText={mutedText} subtleText={subtleText} />
          <MetricCard label="Server (TTFB)" value={metrics?.ttfb || 0} unit="s" target={0.5} color={metrics?.ttfb && metrics.ttfb <= 0.5 ? colors.success : colors.warning} cardBg={cardBg} mutedText={mutedText} subtleText={subtleText} />
          <MetricCard label="P95 Load" value={metrics?.p95_lcp || 0} unit="s" target={target * 1.5} color={metrics?.p95_lcp && metrics.p95_lcp <= target * 1.5 ? colors.success : colors.error} cardBg={cardBg} mutedText={mutedText} subtleText={subtleText} />
        </View>
      </View>

      {/* Trend chart */}
      {data?.trend && data.trend.length > 1 && (
        <View style={{ backgroundColor: softCardBg, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }} data-testid="trend-section" testID="trend-section">
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 8 }}>{tx('admin.performanceGuardianPanel.auto.text.006', 'Load Time Trend (12h)')}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <TrendChart data={data.trend} targetLine={target} />
          </ScrollView>
        </View>
      )}

      {/* Active issues */}
      {data?.issues && data.issues.length > 0 && (
        <View style={{ gap: 8 }} data-testid="issues-section" testID="issues-section">
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>Active Issues ({data.issues.length})</Text>
          {data.issues.map((issue, i) => (
            <View key={issue.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderRadius: 10, backgroundColor: issue.severity === 'critical' ? colors.errorSoft : colors.warningSoft, borderWidth: 1, borderColor: issue.severity === 'critical' ? colors.error : colors.warning }} data-testid={`issue-${issue.id}`} testID={`issue-${issue.id}`}>
              <Ionicons name={issue.severity === 'critical' ? 'alert-circle' : 'warning'} size={18} color={issue.severity === 'critical' ? colors.error : colors.warning} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{issue.title}</Text>
                <Text style={{ fontSize: 11, color: mutedText, marginTop: 2 }}>
                  {issue.auto_fixable ? 'Auto-fixable' : 'Manual intervention needed'}
                </Text>
              </View>
              {issue.auto_fixable && (
                <View style={{ backgroundColor: colors.successSoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: colors.successText }}>{tx('admin.performanceGuardianPanel.auto.text.007', 'AUTO-FIX')}</Text>
                </View>
              )}
            </View>
          ))}
        </View>
      )}

      {/* AI-Powered Auto-Fix Engine */}
      <View style={{ backgroundColor: softCardBg, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border, gap: 14 }} data-testid="autofix-controls" testID="autofix-controls">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: colors.accentSoft, justifyContent: 'center', alignItems: 'center' }}>
              <Ionicons name="sparkles" size={18} color={colors.accent} />
            </View>
            <View>
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.performanceGuardianPanel.auto.text.008', 'AI Auto-Fix Engine')}</Text>
              <Text style={{ fontSize: 11, color: mutedText }}>{tx('admin.performanceGuardianPanel.auto.text.009', 'GPT-4o powered confidence scoring with safe auto-apply')}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {settingsLoading && <ActivityIndicator size="small" />}
            <Switch
              value={autoFixEnabled}
              onValueChange={toggleAutoFix}
              trackColor={{ false: colors.borderStrong, true: colors.accent }}
              data-testid="auto-fix-toggle" testID="auto-fix-toggle"
            />
          </View>
        </View>

        <TouchableOpacity
          onPress={runAutoFix}
          disabled={fixing}
          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: colors.accent, paddingVertical: 12, borderRadius: 10, opacity: fixing ? 0.6 : 1 }}
          data-testid="run-autofix-btn" testID="run-autofix-btn"
        >
          {fixing ? (
            <ActivityIndicator size="small" color={colors.primaryText} />
          ) : (
            <Ionicons name="sparkles" size={18} color={colors.primaryText} />
          )}
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>
            {fixing ? 'AI Analyzing & Fixing...' : 'Run AI Auto-Fix Now'}
          </Text>
        </TouchableOpacity>

        {/* AI Fix Results with confidence scores */}
        {fixResult && (
          <View style={{ backgroundColor: fixResult.success !== false ? colors.accentSoft : colors.errorSoft, borderRadius: 10, padding: 12, gap: 8 }} data-testid="fix-result" testID="fix-result">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
              <Ionicons name={fixResult.success !== false ? 'checkmark-circle' : 'close-circle'} size={16} color={fixResult.success !== false ? colors.accent : colors.error} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: fixResult.successText !== false ? colors.accent : colors.error }}>{fixResult.message}</Text>
            </View>

            {fixResult.ai_powered && fixResult.confidence_threshold && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingLeft: 22, marginBottom: 4 }}>
                <Ionicons name="shield-checkmark" size={12} color={colors.accent} />
                <Text style={{ fontSize: 10, color: mutedText }}>
                  Confidence threshold: {fixResult.confidence_threshold}% | {fixResult.applied || 0} applied, {fixResult.flagged || 0} flagged for review
                </Text>
              </View>
            )}

            {fixResult.results?.map((r: any, i: number) => {
              const isApplied = r.status === 'applied';
              const isFlagged = r.status === 'flagged_for_review';
              const isNotNeeded = r.status === 'not_needed';
              const conf = r.confidence || 0;
              const confColor = conf >= 80 ? colors.success : conf >= 50 ? colors.warning : colors.error;
              const statusColor = isApplied ? colors.success : isFlagged ? colors.warning : isNotNeeded ? colors.primary : colors.textMuted;
              const statusLabel = isApplied ? 'APPLIED' : isFlagged ? 'REVIEW' : isNotNeeded ? 'OK' : r.status?.toUpperCase();

              return (
                <View key={i} style={{ paddingLeft: 22, paddingVertical: 6, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: colors.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: statusColor }} />
                    <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text }}>{r.fix_id?.replace(/_/g, ' ')}</Text>
                    <View style={{ marginLeft: 'auto' as any, flexDirection: 'row', gap: 4 }}>
                      {conf > 0 && (
                        <View style={{ backgroundColor: (globalThis as any).__alphaColor(confColor, '18'), paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                          <Text style={{ color: confColor, fontSize: 9, fontWeight: '800' }}>{conf}%</Text>
                        </View>
                      )}
                      <View style={{ backgroundColor: (globalThis as any).__alphaColor(statusColor, '18'), paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                        <Text style={{ color: statusColor, fontSize: 9, fontWeight: '700' }}>{statusLabel}</Text>
                      </View>
                    </View>
                  </View>
                  <Text style={{ fontSize: 11, color: mutedText, marginTop: 2 }}>{r.details}</Text>
                  {r.reasoning && (
                    <Text style={{ fontSize: 10, color: colors.accent, fontStyle: 'italic', marginTop: 2 }}>AI: {r.reasoning}</Text>
                  )}
                </View>
              );
            })}
          </View>
        )}
      </View>

      {/* What gets fixed section */}
      <View style={{ backgroundColor: softCardBg, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: colors.border }} data-testid="fix-details-section" testID="fix-details-section">
        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 10 }}>{tx('admin.performanceGuardianPanel.auto.text.010', 'AI Auto-Fix Capabilities')}</Text>
        {[
          { icon: 'trash-bin', label: 'Clear Metro Cache', desc: 'Removes stale bundler cache causing slow/failed loads', risk: 'None', ai: true },
          { icon: 'code-slash', label: 'Disable Lazy Loading', desc: 'Prevents ERR_ABORTED failures from Metro lazy bundles', risk: 'None', ai: true },
          { icon: 'analytics', label: 'Purge Stale Vitals', desc: 'Remove old performance data inflating LCP/FCP averages', risk: 'None', ai: true },
          { icon: 'server', label: 'Optimize DB Indexes', desc: 'Create missing indexes on web_vitals for faster queries', risk: 'None', ai: true },
          { icon: 'flash', label: 'Enable Compression', desc: 'Add GZip middleware for 30-70% smaller API responses', risk: 'None', ai: true },
          { icon: 'refresh-circle', label: 'Restart Frontend', desc: 'Graceful restart to apply pending configuration fixes', risk: 'Low', ai: true },
        ].map((fix, i) => (
          <View key={i} style={{ flexDirection: 'row', gap: 10, paddingVertical: 8, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: colors.border }}>
            <Ionicons name={fix.icon as any} size={16} color={colors.accent} style={{ marginTop: 2 }} />
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{fix.label}</Text>
                {fix.ai && <View style={{ backgroundColor: colors.accentSoft, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 }}><Text style={{ fontSize: 8, fontWeight: '700', color: colors.accent }}>{tx('admin.performanceGuardianPanel.auto.text.011', 'AI')}</Text></View>}
              </View>
              <Text style={{ fontSize: 11, color: mutedText, marginTop: 1 }}>{fix.desc}</Text>
            </View>
            <View style={{ backgroundColor: fix.risk === 'None' ? colors.successSoft : colors.warningSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, alignSelf: 'flex-start' }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: fix.risk === 'None' ? colors.success : colors.warning }}>Risk: {fix.risk}</Text>
            </View>
          </View>
        ))}
        <View style={{ marginTop: 10, padding: 10, backgroundColor: colors.accentSoft, borderRadius: 8, borderWidth: 1, borderColor: colors.accent }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Ionicons name="sparkles" size={12} color={colors.accent} />
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.accent }}>{tx('admin.performanceGuardianPanel.auto.text.012', 'Powered by GPT-4o Confidence Scoring')}</Text>
          </View>
          <Text style={{ fontSize: 10, color: mutedText, marginTop: 4 }}>
            Each fix is evaluated by AI for safety and effectiveness. Only fixes with {'>'}80% confidence are auto-applied. Lower confidence actions are flagged for manual review.
          </Text>
        </View>
      </View>

      {/* Recent fix history */}
      {data?.recent_fixes && data.recent_fixes.length > 0 && (
        <View style={{ gap: 8 }} data-testid="fix-history" testID="fix-history">
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.performanceGuardianPanel.auto.text.013', 'Recent Fix History')}</Text>
          {data.recent_fixes.slice(0, 5).map((fix, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 8, backgroundColor: softCardBg, borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name={fix.triggered_by === 'auto' ? 'flash' : 'hand-left'} size={14} color={fix.triggered_by === 'auto' ? colors.success : colors.primary} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text }}>
                  {fix.triggered_by === 'auto' ? 'Automatic Fix' : 'Manual Fix'} — {fix.results?.length || 0} actions
                </Text>
                <Text style={{ fontSize: 10, color: mutedText }}>
                  {new Date(fix.timestamp).toLocaleString()}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 3 }}>
                {fix.results?.map((r: FixResult, j: number) => (
                  <View key={j} style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: r.status === 'applied' ? colors.success : r.status === 'not_needed' ? colors.primary : colors.warning }} />
                ))}
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Performance Alert History */}
      {alertHistory.length > 0 && (
        <View style={{ gap: 8 }} data-testid="alert-history" testID="alert-history">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="notifications" size={16} color={colors.warning} />
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{tx('admin.performanceGuardianPanel.auto.text.014', 'Alert History')}</Text>
            <View style={{ backgroundColor: colors.errorSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8, marginLeft: 'auto' as any }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: colors.error }}>{alertHistory.length} alerts</Text>
            </View>
          </View>
          {alertHistory.slice(0, 8).map((alert, i) => {
            const isCritical = alert.level === 'CRITICAL';
            const alertColor = isCritical ? colors.error : colors.warning;
            const timeDiff = Date.now() - new Date(alert.timestamp).getTime();
            const hoursAgo = Math.floor(timeDiff / 3600000);
            const timeLabel = hoursAgo < 1 ? 'Just now' : hoursAgo < 24 ? `${hoursAgo}h ago` : `${Math.floor(hoursAgo / 24)}d ago`;
            return (
              <View key={i} style={{ padding: 12, borderRadius: 10, backgroundColor: isCritical ? colors.errorSoft : colors.warningSoft, borderWidth: 1, borderColor: isCritical ? colors.error : colors.warning }} data-testid={`alert-${i}`} testID={`alert-${i}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <Ionicons name={isCritical ? 'alert-circle' : 'warning'} size={14} color={alertColor} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: alertColor }}>{alert.level}</Text>
                  <Text style={{ fontSize: 10, color: mutedText, marginLeft: 'auto' as any }}>{timeLabel} | {alert.samples} samples</Text>
                </View>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                  {(alert.alerts || []).map((a, j) => (
                    <View key={j} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: softCardBg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }}>
                      <Text style={{ fontSize: 11, fontWeight: '700', color: a.level === 'CRITICAL' ? colors.error : colors.warning }}>{a.metric}</Text>
                      <Text style={{ fontSize: 10, color: mutedText }}>{a.value}{a.unit} ({'>'}{a.threshold}{a.unit})</Text>
                    </View>
                  ))}
                </View>
              </View>
            );
          })}
        </View>
      )}
    </ScrollView>
  );
}
