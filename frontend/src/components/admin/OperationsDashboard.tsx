import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, ActivityIndicator, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import PricingMismatchAlertsCard from './PricingMismatchAlertsCard';
import { PROTECTED_BRANDS } from '../../utils/brandProtection';
import { useTranslation } from '../../hooks/useTranslation';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';
import { useHybridPolling } from '../../hooks/useHybridPolling';

import { useAdminTheme } from '../../hooks/useAdminTheme';

// Module-level theme constants for helper functions outside component scope
const AC = {
  textMuted: 'var(--app-text-muted)',
  textDim: 'var(--app-text-muted)',
  textSec: 'var(--app-text-sec)',
  border: 'var(--app-border)',
  text: 'var(--app-text)',
  bgAlt: 'var(--app-bg)',
  card: 'var(--app-card-bg)',
};

const tx = (_key: string, fallback: string) => fallback;

const REFRESH_INTERVAL = 30000;
const WS_RECONNECT_DELAY = 3000;

interface SystemMetrics {
  cpu: { percent: number; count: number };
  memory: { percent: number; total_gb: number; used_gb: number; available_gb: number };
  disk: { percent: number; total_gb: number; used_gb: number; free_gb: number };
  network: { total_sent_gb: number; total_recv_gb: number };
  processes: number;
}

interface AIDecision {
  decision: string;
  confidence: number;
  amount: number;
  reasoning: string;
  risk_level: string;
  predicted_trend: string;
  recommendation: string;
}

interface ScalingState {
  instances: { current: number; desired: number; min: number; max: number };
  metrics: { cpu_pct: number; memory_pct: number; disk_pct: number };
  rules_active: number;
  scaling_mode: string;
  last_ai_analysis?: { ai_decision: AIDecision; timestamp: string };
}

interface ScalingEvent {
  event_id: string;
  action: string;
  trigger: string;
  rule_name?: string;
  from_instances: number;
  to_instances: number;
  reason?: string;
  timestamp: string;
}

interface TimelinePoint {
  timestamp: string;
  cpu: number;
  memory: number;
  disk: number;
  instances: number;
  decision: string;
  confidence: number;
  risk_level: string;
  predicted_trend: string;
  reasoning: string;
  recommendation: string;
}

interface TimelineSummary {
  total_analyses: number;
  scale_ups: number;
  scale_downs: number;
  holds: number;
  avg_confidence: number;
}

// ── Reusable Components ──

function MetricBar({ label, value, max, color, unit }: { label: string; value: number; max: number; color: string; unit: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <View style={{ marginBottom: 8 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
        <Text style={{ fontSize: 11, color: AC.textMuted, fontWeight: '500' }}>{label}</Text>
        <Text style={{ fontSize: 11, color, fontWeight: '700' }}>{value.toFixed(1)}{unit}</Text>
      </View>
      <View style={{ height: 6, backgroundColor: AC.border, borderRadius: 3, overflow: 'hidden' }}>
        <View style={{ height: '100%', width: `${pct}%`, backgroundColor: color, borderRadius: 3 }} />
      </View>
    </View>
  );
}

function TimeAgo({ timestamp }: { timestamp: string }) {
  const now = new Date();
  const then = new Date(timestamp);
  const diffMin = Math.floor((now.getTime() - then.getTime()) / 60000);
  if (diffMin < 1) return <Text style={{ fontSize: 10, color: AC.textDim }}>{tx('admin.operationsDashboard.auto.text.001', 'just now')}</Text>;
  if (diffMin < 60) return <Text style={{ fontSize: 10, color: AC.textDim }}>{diffMin}m ago</Text>;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return <Text style={{ fontSize: 10, color: AC.textDim }}>{diffHr}h ago</Text>;
  return <Text style={{ fontSize: 10, color: AC.textDim }}>{Math.floor(diffHr / 24)}d ago</Text>;
}

const RISK_COLORS: Record<string, string> = { low: 'var(--app-success)', medium: 'var(--app-warning)', high: 'var(--app-error)' };
const TREND_ICONS: Record<string, string> = { increasing: 'trending-up', stable: 'remove-outline', decreasing: 'trending-down' };
const DECISION_COLORS: Record<string, string> = { scale_up: 'var(--app-success)', scale_down: 'var(--app-warning)', no_action: AC.textDim };

// ── Timeline Chart Component ──

function TimelineChart({ data, isDark }: { data: TimelinePoint[]; isDark: boolean }) {
  const W = 800, H = 180, PAD_L = 40, PAD_R = 16, PAD_T = 12, PAD_B = 30;
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const border = isDark ? AC.border : AC.textSec;
  const subtext = isDark ? AC.textDim : AC.textMuted;

  if (data.length < 2) {
    return (
      <View style={{ height: H, justifyContent: 'center', alignItems: 'center' }}>
        <Ionicons name="analytics-outline" size={28} color={subtext} />
        <Text style={{ fontSize: 12, color: subtext, marginTop: 6 }}>{tx('admin.operationsDashboard.auto.text.002', 'Collecting data... AI analyses will appear here')}</Text>
      </View>
    );
  }

  const xScale = (i: number) => PAD_L + (i / (data.length - 1)) * plotW;
  const yScale = (v: number, max: number) => PAD_T + plotH - (v / max) * plotH;

  const buildPath = (values: number[], max: number) => {
    return values.map((v, i) => `${i === 0 ? 'M' : 'L'}${xScale(i).toFixed(1)},${yScale(v, max).toFixed(1)}`).join(' ');
  };

  const cpuPath = buildPath(data.map(d => d.cpu), 100);
  const memPath = buildPath(data.map(d => d.memory), 100);
  const confPath = buildPath(data.map(d => d.confidence * 100), 100);

  // Grid lines
  const gridLines = [0, 25, 50, 75, 100].map(v => ({
    y: yScale(v, 100),
    label: `${v}%`,
  }));

  // Time labels (first, middle, last)
  const timeLabels = [0, Math.floor(data.length / 2), data.length - 1].map(i => ({
    x: xScale(i),
    label: new Date(data[i].timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
  }));

  return (
    <View style={{ width: '100%', overflow: 'hidden' }} data-testid="ai-timeline-chart" testID="ai-timeline-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" style={{ width: '100%', height: H } as any}>
        {/* Grid */}
        {gridLines.map((g, i) => (
          <React.Fragment key={i}>
            <line x1={PAD_L} y1={g.y} x2={W - PAD_R} y2={g.y} stroke={border} strokeWidth="0.5" strokeDasharray="4,4" />
            <text x={PAD_L - 6} y={g.y + 3} textAnchor="end" fontSize="9" fill={subtext}>{g.label}</text>
          </React.Fragment>
        ))}

        {/* Confidence area fill */}
        <path
          d={`${confPath} L${xScale(data.length - 1).toFixed(1)},${(PAD_T + plotH).toFixed(1)} L${PAD_L.toFixed(1)},${(PAD_T + plotH).toFixed(1)} Z`}
          fill={'var(--app-primary)'} opacity="0.06"
        />

        {/* Lines */}
        <path d={cpuPath} fill="none" stroke={'var(--app-success)'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d={memPath} fill="none" stroke={'var(--app-primary)'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d={confPath} fill="none" stroke={'var(--app-primary)'} strokeWidth="1.5" strokeDasharray="4,3" strokeLinecap="round" />

        {/* Decision markers */}
        {data.map((d, i) => {
          if (d.decision === 'no_action') return null;
          const cx = xScale(i);
          const cy = yScale(d.cpu, 100);
          const color = DECISION_COLORS[d.decision] || AC.textDim;
          return (
            <React.Fragment key={`marker-${i}`}>
              <circle cx={cx} cy={cy} r="6" fill={color} opacity="0.2" />
              <circle cx={cx} cy={cy} r="3.5" fill={color} />
              <text x={cx} y={cy - 10} textAnchor="middle" fontSize="8" fill={color} fontWeight="bold">
                {d.decision === 'scale_up' ? '+' + d.instances : '-' + d.instances}
              </text>
            </React.Fragment>
          );
        })}

        {/* Data points for CPU */}
        {data.map((d, i) => (
          <circle key={`cpu-${i}`} cx={xScale(i)} cy={yScale(d.cpu, 100)} r="2" fill={'var(--app-success)'} />
        ))}

        {/* Time labels */}
        {timeLabels.map((t, i) => (
          <text key={`time-${i}`} x={t.x} y={H - 6} textAnchor="middle" fontSize="9" fill={subtext}>{t.label}</text>
        ))}
      </svg>
    </View>
  );
}

// ── Decision History List ──

function DecisionHistoryList({ data, isDark, colors }: { data: TimelinePoint[]; isDark: boolean; colors: any }) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _text = isDark ? AC.text : AC.bgAlt;
  const subtext = isDark ? AC.textMuted : AC.textDim;
  const border = isDark ? AC.border : AC.textSec;
  const reversed = [...data].reverse();

  return (
    <View>
      {reversed.slice(0, 8).map((d, i) => {
        const decColor = DECISION_COLORS[d.decision] || AC.textDim;
        const riskColor = RISK_COLORS[d.risk_level] || AC.textDim;
        const time = new Date(d.timestamp);
        return (
          <View key={i} style={{ flexDirection: 'row', gap: 10, paddingVertical: 10, borderBottomWidth: i < 7 ? 1 : 0, borderBottomColor: border }}>
            {/* Decision indicator */}
            <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: (globalThis as any).__alphaColor(decColor, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons
                name={d.decision === 'scale_up' ? 'arrow-up' : d.decision === 'scale_down' ? 'arrow-down' : 'checkmark'}
                size={14} color={decColor}
              />
            </View>
            {/* Content */}
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: decColor }}>
                  {d.decision === 'no_action' ? 'HOLD' : d.decision.replace('_', ' ').toUpperCase()}
                </Text>
                <View style={{ backgroundColor: colors.cardMuted, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 6 }}>
                  <Text style={{ fontSize: 9, color: colors.text, fontWeight: '600' }}>{(d.confidence * 100).toFixed(0)}%</Text>
                </View>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(riskColor, '20'), paddingHorizontal: 5, paddingVertical: 1, borderRadius: 6 }}>
                  <Text style={{ fontSize: 9, color: riskColor, fontWeight: '600' }}>{d.risk_level.toUpperCase()}</Text>
                </View>
              </View>
              <Text style={{ fontSize: 11, color: subtext, lineHeight: 15 }} numberOfLines={2}>{d.reasoning}</Text>
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
                <Text style={{ fontSize: 10, color: subtext }}>CPU {d.cpu}%</Text>
                <Text style={{ fontSize: 10, color: subtext }}>MEM {d.memory}%</Text>
                <Text style={{ fontSize: 10, color: subtext }}>{d.instances} inst</Text>
              </View>
            </View>
            {/* Time */}
            <Text style={{ fontSize: 10, color: subtext }}>{time.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</Text>
          </View>
        );
      })}
      {data.length === 0 && (
        <View style={{ alignItems: 'center', paddingVertical: 24 }}>
          <Text style={{ fontSize: 12, color: subtext }}>{tx('admin.operationsDashboard.auto.text.003', 'No AI decisions recorded yet')}</Text>
        </View>
      )}
    </View>
  );
}

// ── Main Dashboard ──

export default function OperationsDashboard() {
  const AC = useAdminTheme();
  const router = useRouter();
  const {darkMode, colors} = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const isDark = darkMode;
  const bg = isDark ? AC.card : AC.text;
  const cardBg = isDark ? colors.cardMuted : colors.card;
  const border = isDark ? AC.border : AC.textSec;
  const text = isDark ? AC.text : AC.bgAlt;
  const subtext = isDark ? AC.textMuted : AC.textDim;

  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [scaling, setScaling] = useState<ScalingState | null>(null);
  const [scalingEvents, setScalingEvents] = useState<ScalingEvent[]>([]);
  const [aiAnalysis, setAiAnalysis] = useState<AIDecision | null>(null);
  const [aiTimestamp, setAiTimestamp] = useState<string>('');
  const [aiLoading, setAiLoading] = useState(false);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [timelineSummary, setTimelineSummary] = useState<TimelineSummary | null>(null);
  const [perfData, setPerfData] = useState<any>(null);
  const [healthData, setHealthData] = useState<any>(null);
  const [imageStats, setImageStats] = useState<any>(null);
  const [errorsData, setErrorsData] = useState<any>(null);
  const [brandAudit, setBrandAudit] = useState<any>(null);
  const [showFullBrandAudit, setShowFullBrandAudit] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsError, setWsError] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const [scaleRes, histRes, aiHistRes, perfRes, healthRes, imgRes, errRes, brandAuditRes] = await Promise.all([
        api.get('/admin/scaling/status').catch(() => ({ data: null })),
        api.get('/admin/scaling/history?limit=10').catch(() => ({ data: { events: [] } })),
        api.get('/admin/scaling/ai-history?limit=50').catch(() => ({ data: { timeline: [], summary: null } })),
        api.get('/admin/platform/performance').catch(() => ({ data: null })),
        api.get('/admin/platform/health').catch(() => ({ data: null })),
        api.get('/admin/platform/image-stats').catch(() => ({ data: null })),
        api.get('/admin/platform/errors').catch(() => ({ data: null })),
        api.get('/i18n/brand-protection/audit', { params: { limit: 12 } }).catch(() => ({ data: null })),
      ]);
      if (scaleRes.data) {
        setScaling(scaleRes.data);
        if (scaleRes.data.last_ai_analysis) {
          setAiAnalysis(scaleRes.data.last_ai_analysis.ai_decision);
          setAiTimestamp(scaleRes.data.last_ai_analysis.timestamp);
        }
      }
      setScalingEvents(histRes.data.events || []);
      setTimeline(aiHistRes.data.timeline || []);
      setTimelineSummary(aiHistRes.data.summary || null);
      setPerfData(perfRes.data);
      setHealthData(healthRes.data);
      setImageStats(imgRes.data);
      setErrorsData(errRes.data);
      setBrandAudit(brandAuditRes.data);
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/operations-dashboard/fetch',
        fallbackMessage: 'Unable to refresh operations dashboard data.',
        setMessage: setWsError,
      });
    }
    setLoading(false);
  }, []);

  const runAiAnalysis = useCallback(async () => {
    setAiLoading(true);
    try {
      const res = await api.post('/admin/scaling/ai-analyze');
      if (res.data?.ai_decision) {
        setAiAnalysis(res.data.ai_decision);
        setAiTimestamp(res.data.timestamp);
        fetchData();
      }
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/operations-dashboard/ai-analyze',
        fallbackMessage: 'AI scaling analysis failed. Please retry.',
        setMessage: setWsError,
      });
    }
    setAiLoading(false);
  }, [fetchData]);

  const buildWsUrl = useCallback(async () => {
    const baseUrl = (api.defaults.baseURL || '').replace(/^http/, 'ws');
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'system_metrics' });
    const wsTicket = String(ticketResp?.data?.ticket || '').trim();
    if (!wsTicket) {
      throw new Error('Missing websocket ticket for operations dashboard');
    }
    return `${baseUrl}/ws/system-metrics?ticket=${encodeURIComponent(wsTicket)}`;
  }, []);

  const { lastError } = useManagedWebSocket({
    enabled: true,
    buildUrl: buildWsUrl,
    errorScope: 'admin/operations-dashboard/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: WS_RECONNECT_DELAY,
    onOpen: () => {
      setWsConnected(true);
      setWsError('');
    },
    onClose: () => {
      setWsConnected(false);
    },
    onError: () => {
      setWsConnected(false);
      setWsError('Operations live stream interrupted. Reconnecting...');
    },
    onReconnectAttempt: (attempt) => {
      setWsConnected(false);
      setWsError(`Reconnecting operations stream (${attempt})...`);
    },
    onMessage: (e) => {
      try {
        setMetrics(JSON.parse(e.data));
        setWsError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/operations-dashboard/parse',
          fallbackMessage: 'A live operations metric update could not be processed.',
          setMessage: setWsError,
        });
      }
    },
  });

  useEffect(() => {
    if (!lastError) return;
    setWsConnected(false);
    setWsError(lastError);
  }, [lastError]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/operations-dashboard/hybrid-refresh',
    onTick: fetchData,
    runOnMount: false,
    slowIntervalMs: REFRESH_INTERVAL,
    fastIntervalMs: 12000,
    buildWsUrl,
    wsEnabled: true,
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: WS_RECONNECT_DELAY,
  });

  if (loading && !metrics) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: bg, padding: 40 }}>
      <AutoFixBanner domain="ops" />
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: subtext, marginTop: 12, fontSize: 13 }}>{tx('admin.operationsDashboard.auto.text.004', 'Loading Operations Dashboard...')}</Text>
      </View>
    );
  }

  const cpuColor = (metrics?.cpu.percent || 0) > 80 ? colors.error : (metrics?.cpu.percent || 0) > 50 ? colors.warning : colors.success;
  const memColor = (metrics?.memory.percent || 0) > 80 ? colors.error : (metrics?.memory.percent || 0) > 50 ? colors.warning : colors.primary;
  const diskColor = (metrics?.disk.percent || 0) > 80 ? colors.error : (metrics?.disk.percent || 0) > 50 ? colors.warning : colors.purple;
  const dashboardTitle = t('operationsDashboard.header.title');

  return (
    <ScrollView style={{ flex: 1, backgroundColor: bg }} data-testid="operations-dashboard" testID="operations-dashboard">
      <View style={{ padding: 16, maxWidth: 1440 }}>
        {/* Header */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <View>
            <Text style={{ fontSize: 22, fontWeight: '800', color: text, letterSpacing: -0.5 }} data-testid="ops-dashboard-title" testID="ops-dashboard-title">
              {dashboardTitle === 'operationsDashboard.header.title' ? 'Operations Command Center' : dashboardTitle}
            </Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 }}>
              <Text style={{ fontSize: 12, color: subtext }}>{tx('operationsDashboard.header.subtitle', 'AI-powered infrastructure monitoring')}</Text>
              <View style={{ backgroundColor: colors.primarySoft, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 }}>
                <Text style={{ fontSize: 9, color: colors.info, fontWeight: '700' }}>{tx('admin.operationsDashboard.auto.text.005', 'GPT-4o')}</Text>
              </View>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: wsConnected ? colors.successSoft : colors.warningSoft, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20 }}>
              <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: wsConnected ? colors.success : colors.warning }} />
              <Text style={{ fontSize: 10, color: wsConnected ? colors.successText : colors.warningText, fontWeight: '600' }}>
                {wsConnected ? tx('operationsDashboard.header.live', 'LIVE') : tx('operationsDashboard.header.reconnecting', 'RECONNECTING')}
              </Text>
            </View>
            <Pressable onPress={fetchData} style={{ padding: 6 }} data-testid="ops-refresh-btn" testID="ops-refresh-btn">
              <Ionicons name="refresh" size={18} color={subtext} />
            </Pressable>
          </View>
        </View>

        {!!wsError && (
          <View data-testid="ops-ws-error" testID="ops-ws-error" style={{ backgroundColor: (globalThis as any).__alphaColor(colors.error, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '35'), borderRadius: 10, padding: 10, marginBottom: 14 }}>
            <Text style={{ color: colors.error, fontSize: 11, fontWeight: '600' }}>{wsError}</Text>
          </View>
        )}

        {/* Top Stats Row */}
        <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }} data-testid="ops-stats-row" testID="ops-stats-row">
          {[
            { label: tx('operationsDashboard.stats.instances', 'Instances'), value: `${scaling?.instances?.current || 0}`, icon: 'server-outline' as const, color: colors.purpleText, sub: tx('operationsDashboard.stats.ofMax', 'of {count} max').replace('{count}', String(scaling?.instances?.max || 0)) },
            { label: tx('operationsDashboard.stats.cpu', 'CPU'), value: `${metrics?.cpu.percent?.toFixed(1) || 0}%`, icon: 'hardware-chip-outline' as const, color: cpuColor, sub: tx('operationsDashboard.stats.cores', '{count} cores').replace('{count}', String(metrics?.cpu.count || 0)) },
            { label: tx('operationsDashboard.stats.memory', 'Memory'), value: `${metrics?.memory.percent?.toFixed(1) || 0}%`, icon: 'bar-chart-outline' as const, color: memColor, sub: `${metrics?.memory.used_gb?.toFixed(1) || 0} / ${metrics?.memory.total_gb?.toFixed(1) || 0} GB` },
            { label: tx('operationsDashboard.stats.disk', 'Disk'), value: `${metrics?.disk.percent?.toFixed(1) || 0}%`, icon: 'pie-chart-outline' as const, color: diskColor, sub: `${metrics?.disk.used_gb?.toFixed(1) || 0} / ${metrics?.disk.total_gb?.toFixed(1) || 0} GB` },
            { label: tx('operationsDashboard.stats.processes', 'Processes'), value: `${metrics?.processes || 0}`, icon: 'apps-outline' as const, color: colors.info, sub: tx('operationsDashboard.stats.running', 'running') },
          ].map((stat) => (
            <View key={stat.label} style={{ flex: 1, minWidth: 140, backgroundColor: cardBg, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Ionicons name={stat.icon} size={14} color={stat.color} />
                <Text style={{ fontSize: 11, color: subtext, fontWeight: '500' }}>{stat.label}</Text>
              </View>
              <Text style={{ fontSize: 22, fontWeight: '800', color: stat.color, letterSpacing: -0.5 }}>{stat.value}</Text>
              <Text style={{ fontSize: 10, color: subtext, marginTop: 2 }}>{stat.sub}</Text>
            </View>
          ))}
        </View>

        <View style={{ backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border, marginBottom: 16 }} data-testid="ops-brand-protection-dashboard-card" testID="ops-brand-protection-dashboard-card">
          <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <View>
              <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.006', 'Brand Protection Dashboard')}</Text>
              <Text style={{ fontSize: 11, color: subtext, marginTop: 4 }}>{tx('admin.operationsDashboard.auto.text.007', 'Protected-brand inventory, recent corrections, and duplicate-occurrence safety coverage.')}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <Pressable onPress={() => router.push('/admin-console?category=comms&tab=languages' as any)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: isDark ? AC.bgAlt : colors.card, borderWidth: 1, borderColor: border }} data-testid="ops-brand-protection-open-languages" testID="ops-brand-protection-open-languages">
                <Text style={{ fontSize: 11, color: text, fontWeight: '700' }}>{tx('admin.operationsDashboard.auto.text.008', 'Open Languages')}</Text>
              </Pressable>
              <Pressable onPress={() => setShowFullBrandAudit((prev) => !prev)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft }} data-testid="ops-brand-protection-toggle-audit" testID="ops-brand-protection-toggle-audit">
                <Text style={{ fontSize: 11, color: colors.primary, fontWeight: '700' }}>{showFullBrandAudit ? 'Collapse Audit' : 'Show Full Audit'}</Text>
              </Pressable>
            </View>
          </View>
          <View style={{ padding: 14 }}>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
              {[
                { id: 'inventory', label: 'Protected Brands', value: PROTECTED_BRANDS.length, color: colors.primary, sub: 'Platform-wide inventory' },
                { id: 'recent', label: 'Recent Audit Rows', value: brandAudit?.total_recent || 0, color: colors.purpleText, sub: `${brandAudit?.violations_recent || 0} with violations` },
                { id: 'brands', label: 'Brands Seen', value: new Set((brandAudit?.rows || []).flatMap((row: any) => (row?.violations || []).map((item: any) => item.brand))).size, color: colors.successText, sub: 'Recent impacted brands' },
              ].map((item) => (
                <View key={item.id} style={{ flex: 1, minWidth: 150, backgroundColor: isDark ? AC.bgAlt : colors.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: border }} data-testid={`ops-brand-protection-kpi-${item.id}`} testID={`ops-brand-protection-kpi-${item.id}`}>
                  <Text style={{ fontSize: 10, color: subtext, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                  <Text style={{ fontSize: 22, color: item.color, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
                  <Text style={{ fontSize: 10, color: subtext, marginTop: 4 }}>{item.sub}</Text>
                </View>
              ))}
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              {PROTECTED_BRANDS.map((brand) => (
                <View key={brand} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primary }} data-testid={`ops-brand-chip-${brand.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`ops-brand-chip-${brand.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                  <Text style={{ fontSize: 10, color: colors.primary, fontWeight: '700' }}>{brand}</Text>
                </View>
              ))}
            </View>

            {(brandAudit?.rows || []).slice(0, showFullBrandAudit ? 12 : 4).map((row: any, idx: number) => (
              <View key={`${row.audit_id || idx}`} style={{ paddingVertical: 10, borderBottomWidth: idx < Math.min((brandAudit?.rows || []).length, showFullBrandAudit ? 12 : 4) - 1 ? 1 : 0, borderBottomColor: border }} data-testid={`ops-brand-audit-row-${idx}`} testID={`ops-brand-audit-row-${idx}`}>
                <Text style={{ fontSize: 12, color: text, fontWeight: '700' }}>{String(row?.source_text || '').slice(0, 110) || 'Protected brand audit row'}</Text>
                <Text style={{ fontSize: 10, color: subtext, marginTop: 4 }}>Lang {String(row?.target_lang || 'en').toUpperCase()} • Status {String(row?.status || 'clean').toUpperCase()} • {row?.created_at}</Text>
                {!!row?.violations?.length && (
                  <Text style={{ fontSize: 10, color: colors.warningText, marginTop: 4 }}>
                    {row.violations.map((item: any) => `${item.brand}${item.required_occurrences ? ` (${item.found_occurrences || 0}/${item.required_occurrences})` : ''}`).join(' • ')}
                  </Text>
                )}
              </View>
            ))}
          </View>
        </View>

        <PricingMismatchAlertsCard />

        {/* AI Scaling Advisor Panel */}
        <View style={{ backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border, marginBottom: 16 }} data-testid="ops-ai-analysis" testID="ops-ai-analysis">
          <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.009', 'AI Scaling Advisor')}</Text>
              <View style={{ backgroundColor: colors.primarySoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 }}>
                <Text style={{ fontSize: 9, color: colors.info, fontWeight: '700' }}>{tx('admin.operationsDashboard.auto.text.010', 'GPT-4o POWERED')}</Text>
              </View>
            </View>
            <Pressable
              onPress={runAiAnalysis}
              disabled={aiLoading}
              data-testid="ai-analyze-btn" testID="ai-analyze-btn"
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                backgroundColor: aiLoading ? AC.border : colors.primary,
                paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
              }}
            >
              {aiLoading ? <ActivityIndicator size="small" color={colors.primarySoft} /> : <Ionicons name="sparkles" size={14} color="var(--app-primary-text)" />}
              <Text style={{ fontSize: 12, color: colors.primaryText, fontWeight: '600' }}>
                {aiLoading ? 'Analyzing...' : 'Run AI Analysis'}
              </Text>
            </Pressable>
          </View>
          <View style={{ padding: 14 }}>
            {aiAnalysis ? (
              <View>
                <View style={{ flexDirection: 'row', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
                  {[
                    { label: 'Decision', value: aiAnalysis.decision === 'no_action' ? 'HOLD' : aiAnalysis.decision.replace('_', ' ').toUpperCase(), color: DECISION_COLORS[aiAnalysis.decision] || AC.textDim },
                    { label: 'Confidence', value: `${(aiAnalysis.confidence * 100).toFixed(0)}%`, color: colors.primary },
                    { label: 'Risk Level', value: (aiAnalysis.risk_level || 'low').toUpperCase(), color: RISK_COLORS[aiAnalysis.risk_level] || AC.textDim },
                  ].map(card => (
                    <View key={card.label} style={{ flex: 1, minWidth: 120, backgroundColor: isDark ? AC.bgAlt : colors.card, borderRadius: 8, padding: 10 }}>
                      <Text style={{ fontSize: 10, color: subtext, marginBottom: 4 }}>{card.label}</Text>
                      <Text style={{ fontSize: 16, fontWeight: '800', color: card.color }}>{card.value}</Text>
                    </View>
                  ))}
                  <View style={{ flex: 1, minWidth: 120, backgroundColor: isDark ? AC.bgAlt : colors.card, borderRadius: 8, padding: 10 }}>
                    <Text style={{ fontSize: 10, color: subtext, marginBottom: 4 }}>{tx('admin.operationsDashboard.auto.text.011', 'Trend')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Ionicons name={(TREND_ICONS[aiAnalysis.predicted_trend] || 'remove-outline') as any} size={16} color={text} />
                      <Text style={{ fontSize: 13, fontWeight: '700', color: text }}>
                        {(aiAnalysis.predicted_trend || 'stable').charAt(0).toUpperCase() + (aiAnalysis.predicted_trend || 'stable').slice(1)}
                      </Text>
                    </View>
                  </View>
                </View>
                <View style={{ backgroundColor: isDark ? AC.bgAlt : colors.card, borderRadius: 8, padding: 12, marginBottom: 10 }}>
                  <Text style={{ fontSize: 11, fontWeight: '600', color: subtext, marginBottom: 4 }}>{tx('admin.operationsDashboard.auto.text.012', 'AI Reasoning')}</Text>
                  <Text style={{ fontSize: 12, color: text, lineHeight: 18 }}>{aiAnalysis.reasoning}</Text>
                </View>
                {aiAnalysis.recommendation && (
                  <View style={{ backgroundColor: colors.primarySoft, borderRadius: 8, padding: 12, borderLeftWidth: 3, borderLeftColor: colors.primary }}>
                    <Text style={{ fontSize: 11, fontWeight: '600', color: colors.primary, marginBottom: 4 }}>{tx('admin.operationsDashboard.auto.text.013', 'Recommendation')}</Text>
                    <Text style={{ fontSize: 12, color: text, lineHeight: 18 }}>{aiAnalysis.recommendation}</Text>
                  </View>
                )}
                {aiTimestamp && (
                  <Text style={{ fontSize: 10, color: subtext, marginTop: 8, textAlign: 'right' }}>
                    Last analysis: <TimeAgo timestamp={aiTimestamp} />
                  </Text>
                )}
              </View>
            ) : (
              <View style={{ alignItems: 'center', paddingVertical: 20 }}>
                <Ionicons name="sparkles-outline" size={28} color={subtext} />
                <Text style={{ fontSize: 12, color: subtext, marginTop: 8 }}>{tx('admin.operationsDashboard.auto.text.014', 'Click "Run AI Analysis" to get GPT-4o scaling recommendations')}</Text>
              </View>
            )}
          </View>
        </View>

        {/* AI Decision History Timeline */}
        <View style={{ backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border, marginBottom: 16 }} data-testid="ops-ai-timeline" testID="ops-ai-timeline">
          <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.015', 'AI Decision Timeline')}</Text>
              {timelineSummary && (
                <Text style={{ fontSize: 10, color: subtext }}>{timelineSummary.total_analyses} analyses</Text>
              )}
            </View>
            {/* Legend */}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              {[
                { label: 'CPU', color: colors.successText },
                { label: 'Memory', color: colors.purpleText },
                { label: 'Confidence', color: colors.primary, dashed: true },
              ].map(l => (
                <View key={l.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <View style={{ width: 14, height: 2, backgroundColor: l.color, borderRadius: 1 }} />
                  <Text style={{ fontSize: 9, color: subtext }}>{l.label}</Text>
                </View>
              ))}
            </View>
          </View>
          <View style={{ padding: 14 }}>
            <TimelineChart data={timeline} isDark={isDark} />
            {/* Summary badges */}
            {timelineSummary && timelineSummary.total_analyses > 0 && (
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
                {[
                  { label: 'Scale Ups', value: timelineSummary.scale_ups, color: colors.successText },
                  { label: 'Scale Downs', value: timelineSummary.scale_downs, color: colors.warningText },
                  { label: 'Holds', value: timelineSummary.holds, color: AC.textDim },
                  { label: 'Avg Confidence', value: `${(timelineSummary.avg_confidence * 100).toFixed(0)}%`, color: colors.primary },
                ].map(b => (
                  <View key={b.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: isDark ? AC.bgAlt : colors.card, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 }}>
                    <Text style={{ fontSize: 14, fontWeight: '800', color: b.color }}>{b.value}</Text>
                    <Text style={{ fontSize: 10, color: subtext }}>{b.label}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        </View>

        {/* AI Decision History List */}
        <View style={{ backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border, marginBottom: 16 }} data-testid="ops-ai-decisions" testID="ops-ai-decisions">
          <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border }}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.016', 'Decision History')}</Text>
          </View>
          <View style={{ padding: 14 }}>
            <DecisionHistoryList data={timeline} isDark={isDark} colors={colors} />
          </View>
        </View>

        {/* Main Grid: System Health + Auto-Scaling */}
        <View style={{ flexDirection: 'row', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          {/* Live Metrics Panel */}
          <View style={{ flex: 1, minWidth: 320, backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border }} data-testid="ops-live-metrics" testID="ops-live-metrics">
            <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.017', 'System Health')}</Text>
            </View>
            <View style={{ padding: 14 }}>
              <MetricBar label="CPU" value={metrics?.cpu.percent || 0} max={100} color={cpuColor} unit="%" />
              <MetricBar label="Memory" value={metrics?.memory.percent || 0} max={100} color={memColor} unit="%" />
              <MetricBar label="Disk" value={metrics?.disk.percent || 0} max={100} color={diskColor} unit="%" />
              <View style={{ marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: border }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                  <Text style={{ fontSize: 11, color: subtext }}>{tx('admin.operationsDashboard.auto.text.018', 'Network Out')}</Text>
                  <Text style={{ fontSize: 11, color: colors.info, fontWeight: '600' }}>{((metrics?.network.total_sent_gb || 0) * 1024).toFixed(1)} MB</Text>
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                  <Text style={{ fontSize: 11, color: subtext }}>{tx('admin.operationsDashboard.auto.text.019', 'Network In')}</Text>
                  <Text style={{ fontSize: 11, color: colors.info, fontWeight: '600' }}>{((metrics?.network.total_recv_gb || 0) * 1024).toFixed(1)} MB</Text>
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={{ fontSize: 11, color: subtext }}>{tx('admin.operationsDashboard.auto.text.020', 'Processes')}</Text>
                  <Text style={{ fontSize: 11, color: text, fontWeight: '600' }}>{metrics?.processes || 0}</Text>
                </View>
              </View>
            </View>
          </View>

          {/* Auto-Scaling Status */}
          <View style={{ flex: 1, minWidth: 320, backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border }} data-testid="ops-auto-scaling" testID="ops-auto-scaling">
            <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.021', 'Auto-Scaling')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.primarySoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 }}>
                  <Ionicons name="sparkles" size={10} color={colors.primary} />
                  <Text style={{ fontSize: 9, color: colors.primary, fontWeight: '600' }}>{tx('admin.operationsDashboard.auto.text.022', 'AI-POWERED')}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.successSoft, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 }}>
                  <Ionicons name="flash" size={10} color={colors.successText} />
                  <Text style={{ fontSize: 9, color: colors.successText, fontWeight: '600' }}>{scaling?.rules_active || 0} RULES</Text>
                </View>
              </View>
            </View>
            <View style={{ padding: 14 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 14 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 36, fontWeight: '900', color: colors.purpleText, letterSpacing: -1 }}>{scaling?.instances?.current || 0}</Text>
                  <Text style={{ fontSize: 10, color: subtext, marginTop: -2 }}>{tx('admin.operationsDashboard.auto.text.023', 'instances running')}</Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ fontSize: 11, color: subtext }}>Min: {scaling?.instances?.min || 0}</Text>
                  <Text style={{ fontSize: 11, color: subtext }}>Max: {scaling?.instances?.max || 0}</Text>
                  <Text style={{ fontSize: 11, color: subtext }}>Desired: {scaling?.instances?.desired || 0}</Text>
                </View>
              </View>
              <View style={{ height: 8, backgroundColor: AC.border, borderRadius: 4, overflow: 'hidden', marginBottom: 14 }}>
                <View style={{
                  height: '100%', borderRadius: 4,
                  width: `${Math.min(((scaling?.instances?.current || 0) / (scaling?.instances?.max || 20)) * 100, 100)}%`,
                  backgroundColor: colors.purple,
                }} />
              </View>
              <Text style={{ fontSize: 11, fontWeight: '600', color: subtext, marginBottom: 8 }}>{tx('admin.operationsDashboard.auto.text.024', 'Recent Scaling Events')}</Text>
              {scalingEvents.slice(0, 5).map((evt, i) => (
                <View key={evt.event_id || i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: i < 4 ? 1 : 0, borderBottomColor: border }}>
                  <View style={{
                    width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
                    backgroundColor: evt.trigger === 'ai' ? 'var(--app-primary)' : evt.action === 'scale_up' ? 'var(--app-primary)' : 'var(--app-primary)',
                  }}>
                    <Ionicons
                      name={evt.trigger === 'ai' ? 'sparkles' : evt.action === 'scale_up' ? 'arrow-up' : 'arrow-down'}
                      size={12}
                      color={evt.trigger === 'ai' ? colors.primary : evt.action === 'scale_up' ? colors.success : colors.warning}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 11, color: text, fontWeight: '600' }}>
                      {evt.from_instances} {'->'} {evt.to_instances} instances
                    </Text>
                    <Text style={{ fontSize: 9, color: subtext }}>
                      {evt.trigger === 'ai' ? 'AI decision' : evt.trigger === 'auto' ? `Auto: ${evt.rule_name}` : 'Manual'}
                    </Text>
                  </View>
                  <TimeAgo timestamp={evt.timestamp} />
                </View>
              ))}
              {scalingEvents.length === 0 && <Text style={{ fontSize: 11, color: subtext, fontStyle: 'italic' }}>{tx('admin.operationsDashboard.auto.text.025', 'No scaling events yet')}</Text>}
            </View>
          </View>
        </View>

        {/* Platform Health + Performance Row */}
        <View style={{ flexDirection: 'row', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          {/* Platform Health */}
          <View style={{ flex: 1, minWidth: 320, backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border }} data-testid="ops-platform-health" testID="ops-platform-health">
            <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.026', 'Platform Health')}</Text>
                {healthData && (
                  <View style={{
                    backgroundColor: healthData.overall === 'operational' ? 'var(--app-primary)' : 'var(--app-primary)',
                    paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12,
                  }}>
                    <Text style={{
                      fontSize: 9, fontWeight: '700',
                      color: healthData.overall === 'operational' ? colors.success : 'var(--app-primary)',
                    }}>
                      {(healthData.overall || 'unknown').toUpperCase()}
                    </Text>
                  </View>
                )}
              </View>
              <Pressable accessibilityLabel={tx('admin.operationsDashboard.auto.accessibility.001', 'Email daily operations report')}
                onPress={async () => {
                  setReportLoading(true);
                  try {
                    await api.post('/admin/platform/send-report', { period: 'daily' });
                    setWsError('');
                  } catch (error) {
                    handleRecoverableError(error, {
                      scope: 'admin/operations-dashboard/send-report',
                      fallbackMessage: 'Daily report email failed to send.',
                      setMessage: setWsError,
                    });
                  }
                  setReportLoading(false);
                }}
                disabled={reportLoading}
                data-testid="send-report-btn" testID="send-report-btn"
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 5,
                  backgroundColor: reportLoading ? AC.border : colors.purple,
                  paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
                }}
              >
                {reportLoading ? <ActivityIndicator size="small" color="var(--app-primary)" /> : <Ionicons name="mail-outline" size={13} color="var(--app-primary-text)" />}
                <Text style={{ fontSize: 11, color: colors.primaryText, fontWeight: '600' }}>
                  {reportLoading ? 'Sending...' : 'Email Report'}
                </Text>
              </Pressable>
            </View>
            <View style={{ padding: 14 }}>
              {healthData?.checks ? Object.entries(healthData.checks).map(([key, val]: [string, any]) => {
                const isOk = val.status === 'healthy' || val.status === 'configured';
                return (
                  <View key={key} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: border }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: isOk ? colors.success : colors.warning }} />
                      <Text style={{ fontSize: 12, color: text, fontWeight: '500' }}>{key.charAt(0).toUpperCase() + key.slice(1)}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      {val.latency_ms !== undefined && <Text style={{ fontSize: 10, color: subtext }}>{val.latency_ms}ms</Text>}
                      {val.collections !== undefined && <Text style={{ fontSize: 10, color: subtext }}>{val.collections} collections</Text>}
                      <Text style={{ fontSize: 10, color: isOk ? colors.success : colors.warning, fontWeight: '600' }}>{val.status}</Text>
                    </View>
                  </View>
                );
              }) : <Text style={{ fontSize: 11, color: subtext }}>{tx('admin.operationsDashboard.auto.text.027', 'Loading...')}</Text>}
              {healthData?.uptime && (
                <Text style={{ fontSize: 10, color: subtext, marginTop: 8 }}>Uptime: {healthData.uptime}</Text>
              )}
            </View>
          </View>

          {/* API Performance */}
          <View style={{ flex: 1, minWidth: 320, backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border }} data-testid="ops-api-performance" testID="ops-api-performance">
            <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.028', 'API Performance')}</Text>
            </View>
            <View style={{ padding: 14 }}>
              {perfData ? (
                <View>
                  <View style={{ flexDirection: 'row', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
                    {[
                      { label: 'Uptime', value: perfData.uptime_human || '0m', color: colors.successText },
                      { label: 'Requests', value: String(perfData.total_requests || 0), color: colors.primary },
                      { label: 'Errors', value: String(perfData.total_errors || 0), color: perfData.total_errors > 0 ? colors.error : colors.success },
                      { label: 'Error Rate', value: `${perfData.error_rate_pct || 0}%`, color: (perfData.error_rate_pct || 0) > 5 ? colors.error : colors.success },
                      { label: 'RPM', value: String(perfData.requests_per_minute || 0), color: colors.purpleText },
                    ].map(s => (
                      <View key={s.label} style={{ backgroundColor: isDark ? AC.bgAlt : colors.card, borderRadius: 8, padding: 8, minWidth: 80 }}>
                        <Text style={{ fontSize: 9, color: subtext }}>{s.label}</Text>
                        <Text style={{ fontSize: 16, fontWeight: '800', color: s.color }}>{s.value}</Text>
                      </View>
                    ))}
                  </View>
                  <Text style={{ fontSize: 11, fontWeight: '600', color: subtext, marginBottom: 6 }}>{tx('admin.operationsDashboard.auto.text.029', 'Slowest Endpoints')}</Text>
                  {(perfData.top_endpoints || []).slice(0, 5).map((ep: any, i: number) => (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 }}>
                      <Text style={{ fontSize: 10, color: text, flex: 1 }} numberOfLines={1}>{ep.path}</Text>
                      <View style={{ flexDirection: 'row', gap: 8 }}>
                        <Text style={{ fontSize: 10, color: subtext }}>{ep.count}x</Text>
                        <Text style={{ fontSize: 10, color: ep.avg_ms > 500 ? colors.warning : colors.success, fontWeight: '600' }}>
                          {ep.avg_ms}ms avg
                        </Text>
                        <Text style={{ fontSize: 10, color: subtext }}>p95: {ep.p95_ms}ms</Text>
                      </View>
                    </View>
                  ))}
                  {(perfData.top_endpoints || []).length === 0 && (
                    <Text style={{ fontSize: 10, color: subtext, fontStyle: 'italic' }}>{tx('admin.operationsDashboard.auto.text.030', 'Collecting data...')}</Text>
                  )}
                </View>
              ) : <Text style={{ fontSize: 11, color: subtext }}>{tx('admin.operationsDashboard.auto.text.031', 'Loading...')}</Text>}
            </View>
          </View>
        </View>

        {/* Image Generation Monitor + Error Tracking Row */}
        <View style={{ flexDirection: 'row', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          {/* Image Generation Stats */}
          <View style={{ flex: 1, minWidth: 320, backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border }} data-testid="ops-image-stats" testID="ops-image-stats">
            <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.032', 'Image Generation Monitor')}</Text>
            </View>
            <View style={{ padding: 14 }}>
              {imageStats ? (
                <View>
                  <View style={{ flexDirection: 'row', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
                    {[
                      { label: 'Total (24h)', value: String(imageStats.totals?.last_24h || 0), color: colors.primary },
                      { label: 'Success Rate', value: `${imageStats.last_24h?.success_rate || 0}%`, color: (imageStats.last_24h?.success_rate || 0) >= 90 ? colors.success : colors.warning },
                      { label: 'Failed (24h)', value: String(imageStats.last_24h?.failed || 0), color: (imageStats.last_24h?.failed || 0) > 0 ? colors.error : colors.success },
                      { label: 'Retried', value: String(imageStats.last_24h?.retried || 0), color: colors.warningText },
                      { label: 'Retry Effective', value: `${imageStats.retry_effectiveness || 0}%`, color: colors.purpleText },
                    ].map(s => (
                      <View key={s.label} style={{ backgroundColor: isDark ? AC.bgAlt : colors.card, borderRadius: 8, padding: 8, minWidth: 80 }}>
                        <Text style={{ fontSize: 9, color: subtext }}>{s.label}</Text>
                        <Text style={{ fontSize: 16, fontWeight: '800', color: s.color }}>{s.value}</Text>
                      </View>
                    ))}
                  </View>
                  {imageStats.avg_duration_ms > 0 && (
                    <Text style={{ fontSize: 11, color: subtext }}>Avg generation: {imageStats.avg_duration_ms}ms | Avg retries: {imageStats.avg_retries}</Text>
                  )}
                  {(imageStats.last_7d?.success || 0) > 0 && (
                    <View style={{ marginTop: 8, padding: 10, backgroundColor: isDark ? AC.bgAlt : colors.card, borderRadius: 8 }}>
                      <Text style={{ fontSize: 11, fontWeight: '600', color: subtext, marginBottom: 4 }}>{tx('admin.operationsDashboard.auto.text.033', '7-Day Summary')}</Text>
                      <Text style={{ fontSize: 11, color: text }}>
                        {imageStats.last_7d.success} success / {imageStats.last_7d.failed} failed ({imageStats.last_7d.success_rate}% rate)
                      </Text>
                    </View>
                  )}
                  {imageStats.totals?.all_time === 0 && (
                    <View style={{ alignItems: 'center', paddingVertical: 12 }}>
                      <Ionicons name="image-outline" size={24} color={subtext} />
                      <Text style={{ fontSize: 11, color: subtext, marginTop: 6 }}>{tx('admin.operationsDashboard.auto.text.034', 'No image generations tracked yet')}</Text>
                    </View>
                  )}
                </View>
              ) : <Text style={{ fontSize: 11, color: subtext }}>{tx('admin.operationsDashboard.auto.text.035', 'Loading...')}</Text>}
            </View>
          </View>

          {/* Error Tracking */}
          <View style={{ flex: 1, minWidth: 320, backgroundColor: cardBg, borderRadius: 12, borderWidth: 1, borderColor: border }} data-testid="ops-error-tracking" testID="ops-error-tracking">
            <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: text }}>{tx('admin.operationsDashboard.auto.text.036', 'Error Tracking')}</Text>
              {errorsData && (
                <View style={{
                  backgroundColor: (errorsData.total_errors || 0) === 0 ? 'var(--app-primary)' : 'var(--app-error)',
                  paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10,
                }}>
                  <Text style={{ fontSize: 9, color: (errorsData.total_errors || 0) === 0 ? colors.success : 'var(--app-error)', fontWeight: '700' }}>
                    {errorsData.total_errors || 0} ERRORS
                  </Text>
                </View>
              )}
            </View>
            <View style={{ padding: 14 }}>
              {errorsData ? (
                <View>
                  {(errorsData.top_error_paths || []).length > 0 && (
                    <View style={{ marginBottom: 10 }}>
                      <Text style={{ fontSize: 11, fontWeight: '600', color: subtext, marginBottom: 6 }}>{tx('admin.operationsDashboard.auto.text.037', 'Top Error Paths')}</Text>
                      {errorsData.top_error_paths.slice(0, 5).map((ep: any, i: number) => (
                        <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 }}>
                          <Text style={{ fontSize: 10, color: text, flex: 1 }} numberOfLines={1}>{ep.path}</Text>
                          <Text style={{ fontSize: 10, color: colors.error, fontWeight: '600' }}>{ep.count}x</Text>
                        </View>
                      ))}
                    </View>
                  )}
                  {(errorsData.recent_errors || []).slice(0, 5).map((err: any, i: number) => (
                    <View key={i} style={{ paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: border }}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 }}>
                        <Text style={{ fontSize: 10, color: text, fontWeight: '600' }}>{err.method} {err.path}</Text>
                        <Text style={{ fontSize: 10, color: colors.error, fontWeight: '600' }}>{err.status}</Text>
                      </View>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                        <Text style={{ fontSize: 9, color: subtext }} numberOfLines={1}>{err.detail || 'No detail'}</Text>
                        <Text style={{ fontSize: 9, color: subtext }}>{err.duration_ms}ms</Text>
                      </View>
                    </View>
                  ))}
                  {(errorsData.total_errors || 0) === 0 && (
                    <View style={{ alignItems: 'center', paddingVertical: 12 }}>
                      <Ionicons name="checkmark-circle-outline" size={24} color={colors.successText} />
                      <Text style={{ fontSize: 11, color: colors.successText, marginTop: 6, fontWeight: '600' }}>{tx('admin.operationsDashboard.auto.text.038', 'No errors detected')}</Text>
                    </View>
                  )}
                </View>
              ) : <Text style={{ fontSize: 11, color: subtext }}>{tx('admin.operationsDashboard.auto.text.039', 'Loading...')}</Text>}
            </View>
          </View>
        </View>
      </View>
    </ScrollView>
  );
}
