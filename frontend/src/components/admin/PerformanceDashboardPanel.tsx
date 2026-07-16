import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import DataFreshnessIndicator from '../DataFreshnessIndicator';
import { useAiInsight, AIInsightPanel, FindingItem, PriorityItem } from './AIInsightHelpers';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
interface Props { colors: any; }

const tx = (_key: string, fallback: string) => fallback;

function makeT(AC: any) { return {
  bg: 'var(--app-bg)', surface: 'var(--app-card-bg)', card: AC.surface, border: 'var(--app-border)',
  text: AC.text, textSec: AC.textMuted, textMuted: AC.textDim,
  primary: 'var(--app-primary)',
}; }

function Gauge({ value, max, label, unit, color }: { value: number; max: number; label: string; unit: string; color: string }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  const pct = Math.min((value / max) * 100, 100);
  return (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
      <Text style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', marginBottom: 8 }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4 }}>
        <Text style={{ fontSize: 24, fontWeight: '800', color }}>{typeof value === 'number' ? (value > 100 ? value.toFixed(0) : value.toFixed(1)) : value}</Text>
        <Text style={{ fontSize: 11, fontWeight: '600', color: T.textMuted, marginBottom: 3 }}>{unit}</Text>
      </View>
      <View style={{ height: 6, borderRadius: 3, backgroundColor: T.border, marginTop: 8 }}>
        <View style={{ width: `${pct}%`, height: 6, borderRadius: 3, backgroundColor: pct > 80 ? colors.error : pct > 60 ? colors.warning : color }} />
      </View>
    </View>
  );
}

export default function PerformanceDashboardPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [liveConnected, setLiveConnected] = useState(false);
  const [wsError, setWsError] = useState('');

  const loadData = useCallback(async () => {
    try {
      const [m, h] = await Promise.all([
        api.get('/admin/system/metrics'),
        api.get('/admin/siem/perf/history?minutes=30'),
      ]);
      setMetrics(m.data);
      setHistory(h.data.metrics || []);
      setWsError('');
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/performance-dashboard/load',
        fallbackMessage: 'Unable to load performance metrics.',
        setMessage: setWsError,
      });
    }
    setLoading(false);
    setLastUpdated(new Date());
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadData(); }, []);

  const buildWsUrl = useCallback(async () => {
    const wsOrigin = (typeof window !== 'undefined' && (`https://${window.location.host}`)
      ? (`https://${window.location.host}`)
      : (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '')).replace('https://', 'wss://').replace('http://', 'ws://');
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'system_metrics' });
    const wsTicket = String(ticketResp?.data?.ticket || '').trim();
    if (!wsTicket) {
      throw new Error('Missing websocket ticket for performance dashboard');
    }
    return `${wsOrigin}/api/ws/system-metrics?ticket=${encodeURIComponent(wsTicket)}`;
  }, []);

  const { lastError } = useManagedWebSocket({
    enabled: Platform.OS === 'web',
    buildUrl: buildWsUrl,
    errorScope: 'admin/performance-dashboard/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1200,
    onOpen: () => {
      setLiveConnected(true);
      setWsError('');
    },
    onClose: () => {
      setLiveConnected(false);
    },
    onError: () => {
      setLiveConnected(false);
      setWsError('Live performance stream interrupted. Reconnecting...');
    },
    onReconnectAttempt: (attempt) => {
      setLiveConnected(false);
      setWsError(`Reconnecting performance stream (${attempt})...`);
    },
    onMessage: (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.cpu !== undefined) {
          setMetrics(data);
          setLastUpdated(new Date());
        }
        setWsError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/performance-dashboard/parse',
          fallbackMessage: 'A live performance update could not be read.',
          setMessage: setWsError,
        });
      }
    },
  });

  useEffect(() => {
    if (!lastError) return;
    setLiveConnected(false);
    setWsError(lastError);
  }, [lastError]);

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  const m = metrics || {};
  const cpuPct = m.cpu?.percent || 0;
  const memPct = m.memory?.percent || 0;
  const diskPct = m.disk?.percent || 0;
  const memUsedGB = ((m.memory?.used || 0) / 1073741824).toFixed(1);
  const memTotalGB = ((m.memory?.total || 0) / 1073741824).toFixed(1);
  const diskUsedGB = ((m.disk?.used || 0) / 1073741824).toFixed(1);
  const diskTotalGB = ((m.disk?.total || 0) / 1073741824).toFixed(1);
  const netSentMB = ((m.network?.bytes_sent || 0) / 1048576).toFixed(0);
  const netRecvMB = ((m.network?.bytes_recv || 0) / 1048576).toFixed(0);

  // History chart helpers
  const histCpu = history.map(h => h.cpu?.percent || 0);
  const histMem = history.map(h => h.memory?.percent || 0);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _maxCpu = Math.max(...histCpu, 1);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _maxMem = Math.max(...histMem, 1);

  return (
    <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="perf-title" testID="perf-title">{tx('admin.performanceDashboardPanel.auto.text.001', 'Performance Monitor')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: liveConnected ? colors.success : colors.warning }} />
            <Text style={{ fontSize: 11, color: T.textSec }}>{liveConnected ? 'Live updates' : 'Polling mode'}</Text>
          </View>
          {!!wsError && (
            <Text data-testid="perf-ws-error" testID="perf-ws-error" style={{ fontSize: 11, color: colors.error, marginTop: 6 }}>{wsError}</Text>
          )}
        </View>
        <DataFreshnessIndicator lastUpdated={lastUpdated} onRefresh={loadData} isRefreshing={loading} accentColor={T.primary} textColor={T.textMuted} />
      </View>

      {/* Real-time Gauges */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }} data-testid="perf-gauges" testID="perf-gauges">
        <Gauge value={cpuPct} max={100} label="CPU Usage" unit="%" color={'var(--app-primary)'} />
        <Gauge value={memPct} max={100} label="Memory" unit="%" color={'var(--app-primary)'} />
        <Gauge value={diskPct} max={100} label="Disk" unit="%" color={'var(--app-warning)'} />
        <Gauge value={m.cpu?.count || 0} max={16} label="CPU Cores" unit="cores" color={'var(--app-success)'} />
      </View>

      {/* System Details */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 200, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.performanceDashboardPanel.auto.text.002', 'Memory Details')}</Text>
          {[
            { label: 'Used', value: `${memUsedGB} GB` },
            { label: 'Total', value: `${memTotalGB} GB` },
            { label: 'Usage', value: `${memPct}%` },
          ].map(r => (
            <View key={r.label} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }}>
              <Text style={{ fontSize: 11, color: T.textMuted }}>{r.label}</Text>
              <Text style={{ fontSize: 11, fontWeight: '700', color: T.text }}>{r.value}</Text>
            </View>
          ))}
        </View>
        <View style={{ flex: 1, minWidth: 200, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.performanceDashboardPanel.auto.text.003', 'Disk Details')}</Text>
          {[
            { label: 'Used', value: `${diskUsedGB} GB` },
            { label: 'Total', value: `${diskTotalGB} GB` },
            { label: 'Usage', value: `${diskPct}%` },
          ].map(r => (
            <View key={r.label} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }}>
              <Text style={{ fontSize: 11, color: T.textMuted }}>{r.label}</Text>
              <Text style={{ fontSize: 11, fontWeight: '700', color: T.text }}>{r.value}</Text>
            </View>
          ))}
        </View>
        <View style={{ flex: 1, minWidth: 200, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.performanceDashboardPanel.auto.text.004', 'Network I/O')}</Text>
          {[
            { label: 'Sent', value: `${netSentMB} MB` },
            { label: 'Received', value: `${netRecvMB} MB` },
            { label: 'Connections', value: `${m.network?.connections || 0}` },
          ].map(r => (
            <View key={r.label} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }}>
              <Text style={{ fontSize: 11, color: T.textMuted }}>{r.label}</Text>
              <Text style={{ fontSize: 11, fontWeight: '700', color: T.text }}>{r.value}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Process Info */}
      {m.process && (
        <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 20 }}>
          <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.performanceDashboardPanel.auto.text.005', 'Process Info')}</Text>
          <View style={{ flexDirection: 'row', gap: 20, flexWrap: 'wrap' }}>
            {[
              { label: 'Threads', value: m.process.threads },
              { label: 'Uptime', value: `${Math.round((m.process.uptime || 0) / 60)}min` },
              { label: 'Proc Memory', value: `${((m.process.memory_rss || 0) / 1048576).toFixed(0)} MB` },
            ].map(r => (
              <View key={r.label}>
                <Text style={{ fontSize: 10, color: T.textMuted, marginBottom: 2 }}>{r.label}</Text>
                <Text style={{ fontSize: 14, fontWeight: '700', color: T.primary }}>{r.value}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Historical CPU/Memory Chart */}
      {history.length > 0 && (
        <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="perf-history" testID="perf-history">
          <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 14 }}>{tx('admin.performanceDashboardPanel.auto.text.006', 'CPU & Memory History (30min)')}</Text>
          <View style={{ height: 100, flexDirection: 'row', alignItems: 'flex-end', gap: 2 }}>
            {histCpu.map((cpu, i) => (
              <View key={i} style={{ flex: 1, alignItems: 'center', gap: 1 }}>
                <View style={{ width: '60%', height: Math.max((cpu / 100) * 80, 2), backgroundColor: colors.primary, borderRadius: 2 }} />
                <View style={{ width: '60%', height: Math.max((histMem[i] / 100) * 80, 2), backgroundColor: colors.accentSoft, borderRadius: 2 }} />
              </View>
            ))}
          </View>
          <View style={{ flexDirection: 'row', gap: 16, marginTop: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary }} />
              <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.performanceDashboardPanel.auto.text.007', 'CPU')}</Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.accent }} />
              <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.performanceDashboardPanel.auto.text.008', 'Memory')}</Text>
            </View>
          </View>
        </View>
      )}

      {/* AI Performance Forecaster */}
      <PerformanceAISection />

      <View style={{ height: 20 }} />
    </ScrollView>
  );
}

function PerformanceAISection() {
  const colors = useAdminTheme();
  const ai = useAiInsight('performance_forecast', 'performance-forecast');
  const [show, setShow] = useState(false);

  return (
    <View style={{ marginTop: 16 }}>
      <TouchableOpacity onPress={() => setShow(!show)} style={{ backgroundColor: `${colors.accent}20`, borderWidth: 1, borderColor: `${colors.accent}40`, borderRadius: 12, padding: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }} data-testid="perf-ai-toggle" testID="perf-ai-toggle">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
          <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '700' }}>{tx('admin.performanceDashboardPanel.auto.text.009', 'AI Performance Forecaster')}</Text>
        </View>
        <Ionicons name={show ? 'chevron-up' : 'chevron-down'} size={16} color={'var(--app-primary)'} />
      </TouchableOpacity>
      {show && (
        <View style={{ marginTop: 12 }}>
          <AIInsightPanel
            config={{
              cacheKey: 'performance_forecast', postEndpoint: 'performance-forecast',
              title: 'AI Performance Forecaster', subtitle: 'performance metrics',
              scoreKey: 'performance_score', scoreLabel: 'Performance Score',
              summaryKey: 'forecast_summary',
              sections: [
                { key: 'degradation_risks', title: 'Degradation Risks', icon: 'warning', renderItem: (item, idx, total) => <FindingItem key={idx} item={{...item, finding: item.component, severity: item.risk_level, recommendation: item.mitigation}} idx={idx} total={total} /> },
                { key: 'optimization_opportunities', title: 'Optimization Opportunities', icon: 'rocket', renderItem: (item, idx, total) => <PriorityItem key={idx} item={{...item, strategy: item.area, description: `${item.current_metric} -> ${item.target_metric}: ${item.approach}`}} idx={idx} total={total} /> },
              ],
            }}
            data={ai.data}
            loading={ai.loading}
            onRun={ai.run}
          />
        </View>
      )}
    </View>
  );
}
