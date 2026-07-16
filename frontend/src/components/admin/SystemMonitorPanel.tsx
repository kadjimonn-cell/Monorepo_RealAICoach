import { useTranslation } from '../../hooks/useTranslation';
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, useWindowDimensions, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

const MAX_HISTORY = 30;

interface MetricData {
  timestamp: string;
  cpu: { percent: number; count: number; load_1m: number; load_5m: number; load_15m: number };
  memory: { percent: number; used_gb: number; total_gb: number; available_gb: number };
  disk: { percent: number; used_gb: number; total_gb: number; free_gb: number };
  network: { bytes_sent_rate: number; bytes_recv_rate: number; total_sent_gb: number; total_recv_gb: number };
  processes: number;
}

function MiniChart({ values, color, height = 48, maxVal }: { values: number[]; color: string; height?: number; maxVal?: number }) {
  const max = maxVal ?? Math.max(...values, 1);
  const w = 100 / Math.max(values.length - 1, 1);
  const points = values.map((v, i) => `${i * w},${height - (v / max) * (height - 4)}`).join(' ');
  const fill = `${points} ${100},${height} 0,${height}`;

  return (
    <View style={{ height, width: '100%', overflow: 'hidden' }} data-testid="mini-chart" testID="mini-chart">
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%' } as any}>
        <defs>
          <linearGradient id={`g-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <polygon points={fill} fill={`url(#g-${color.replace('#', '')})`} />
        <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </View>
  );
}

function GaugeRing({ percent, color, size = 80, label, value }: { percent: number; color: string; size?: number; label: string; value: string }) {    const { colors } = useTheme();
  const r = (size - 10) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (percent / 100) * circ;

  return (
    <View style={{ alignItems: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: [{ rotate: '-90deg' }] } as any}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={'var(--app-text)'} strokeWidth="6" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="6" strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" />
      </svg>
      <View style={{ position: 'absolute', top: size / 2 - 14, alignItems: 'center' }}>
        <Text style={{ fontSize: 16, fontWeight: '900', color: colors.primaryText }}>{value}</Text>
      </View>
      <Text style={{ fontSize: 10, fontWeight: '600', color: colors.textMuted, marginTop: 4 }}>{label}</Text>
    </View>
  );
}

export default function SystemMonitorPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const [connected, setConnected] = useState(false);
  const [wsError, setWsError] = useState('');
  const [current, setCurrent] = useState<MetricData | null>(null);
  const [cpuHistory, setCpuHistory] = useState<number[]>([]);
  const [memHistory, setMemHistory] = useState<number[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [netSentHistory, setNetSentHistory] = useState<number[]>([]);
  const [netRecvHistory, setNetRecvHistory] = useState<number[]>([]);
  const [lastUpdate, setLastUpdate] = useState<string>('');

  const C = useMemo(() => ({
    bg: colors.bg, card: colors.card, text: colors.text, muted: colors.textMuted,
    border: colors.border, primary: colors.primary, bgSoft: colors.bgSoft,
  }), [colors]);

  const buildWsUrl = useCallback(async () => {
    const baseUrl = (api.defaults.baseURL || '').replace(/^http/, 'ws');
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'system_metrics' });
    const wsTicket = String(ticketResp?.data?.ticket || '').trim();
    if (!wsTicket) {
      throw new Error('Missing websocket ticket for system metrics');
    }
    return `${baseUrl}/ws/system-metrics?ticket=${encodeURIComponent(wsTicket)}`;
  }, []);

  const { lastError } = useManagedWebSocket({
    enabled: true,
    buildUrl: buildWsUrl,
    errorScope: 'admin/system-monitor',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1200,
    onOpen: () => {
      setConnected(true);
      setWsError('');
    },
    onClose: () => {
      setConnected(false);
    },
    onError: () => {
      setConnected(false);
      setWsError('Live system metrics connection issue. Reconnecting...');
    },
    onReconnectAttempt: (attempt) => {
      setConnected(false);
      setWsError(`Reconnecting system metrics (${attempt})...`);
    },
    onMessage: (e) => {
      try {
        const d: MetricData = JSON.parse(e.data);
        setCurrent(d);
        setLastUpdate(new Date().toLocaleTimeString());
        setCpuHistory(prev => [...prev.slice(-(MAX_HISTORY - 1)), d.cpu.percent]);
        setMemHistory(prev => [...prev.slice(-(MAX_HISTORY - 1)), d.memory.percent]);
        setNetSentHistory(prev => [...prev.slice(-(MAX_HISTORY - 1)), d.network.bytes_sent_rate]);
        setNetRecvHistory(prev => [...prev.slice(-(MAX_HISTORY - 1)), d.network.bytes_recv_rate]);
        setWsError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/system-monitor/parse',
          fallbackMessage: 'A live metrics update could not be processed.',
          setMessage: setWsError,
        });
      }
    },
  });

  useEffect(() => {
    let active = true;
    api.get('/admin/system/metrics').then(r => {
      if (!active) return;
      const d = r.data;
      setCurrent(d);
      setCpuHistory([d.cpu.percent]);
      setMemHistory([d.memory.percent]);
      setNetSentHistory([d.network.bytes_sent_rate]);
      setNetRecvHistory([d.network.bytes_recv_rate]);
      setWsError('');
    }).catch((error) => {
      handleRecoverableError(error, {
        scope: 'admin/system-monitor/bootstrap',
        fallbackMessage: 'Unable to load initial system metrics.',
        setMessage: setWsError,
      });
    });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!lastError) return;
    setConnected(false);
    setWsError(lastError);
  }, [lastError]);

  const formatBytes = (b: number) => {
    if (b < 1024) return `${b} B/s`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB/s`;
    return `${(b / (1024 * 1024)).toFixed(1)} MB/s`;
  };

  const statusColor = (pct: number) => pct > 90 ? colors.error : pct > 70 ? colors.warning : colors.success;

  if (!current) {
    return (
      <View style={{ padding: 60, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={C.primary} />
        <Text style={{ color: C.muted, fontSize: 13, marginTop: 12 }}>{tx('admin.systemMonitorPanel.auto.text.001', 'Connecting to system metrics...')}</Text>
      </View>
    );
  }

  return (
    <View style={{ gap: 16, paddingBottom: 20 }} data-testid="system-monitor-panel" testID="system-monitor-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View>
          <Text style={{ color: C.text, fontSize: 22, fontWeight: '900', letterSpacing: -0.5 }}>{tx('admin.systemMonitorPanel.auto.text.002', 'System Monitor')}</Text>
          <Text style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>{tx('admin.systemMonitorPanel.auto.text.003', 'Real-time infrastructure metrics via psutil')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: connected ? colors.success : colors.error }} />
          <Text style={{ color: connected ? colors.success : colors.error, fontSize: 11, fontWeight: '700' }}>{connected ? 'LIVE' : 'OFFLINE'}</Text>
          {lastUpdate && <Text style={{ color: C.muted, fontSize: 10 }}>{lastUpdate}</Text>}
        </View>
      </View>

      {!!wsError && (
        <View data-testid="system-monitor-ws-error" testID="system-monitor-ws-error" style={{ backgroundColor: (globalThis as any).__alphaColor(colors.error, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '45'), borderRadius: 10, padding: 10 }}>
          <Text style={{ color: colors.error, fontSize: 11, fontWeight: '600' }}>{wsError}</Text>
        </View>
      )}

      {/* Gauge Row */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-around', backgroundColor: C.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="gauge-row" testID="gauge-row">
        <GaugeRing percent={current.cpu.percent} color={statusColor(current.cpu.percent)} label="CPU" value={`${current.cpu.percent}%`} />
        <GaugeRing percent={current.memory.percent} color={statusColor(current.memory.percent)} label="Memory" value={`${current.memory.percent}%`} />
        <GaugeRing percent={current.disk.percent} color={statusColor(current.disk.percent)} label="Disk" value={`${current.disk.percent}%`} />
      </View>

      {/* Metric Cards Grid */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12 }}>
        {/* CPU Card */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="cpu-card" testID="cpu-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="hardware-chip" size={16} color={colors.primary} />
              </View>
              <View>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.systemMonitorPanel.auto.text.004', 'CPU')}</Text>
                <Text style={{ color: C.muted, fontSize: 10 }}>{current.cpu.count} cores</Text>
              </View>
            </View>
            <Text style={{ color: statusColor(current.cpu.percent), fontSize: 20, fontWeight: '900' }}>{current.cpu.percent}%</Text>
          </View>
          <MiniChart values={cpuHistory} color={colors.primary} maxVal={100} />
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
            <Text style={{ color: C.muted, fontSize: 10 }}>Load: {current.cpu.load_1m} / {current.cpu.load_5m} / {current.cpu.load_15m}</Text>
            <Text style={{ color: C.muted, fontSize: 10 }}>{tx('admin.systemMonitorPanel.auto.text.005', '1m / 5m / 15m')}</Text>
          </View>
        </View>

        {/* Memory Card */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="memory-card" testID="memory-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.purpleSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="server" size={16} color={colors.purpleText} />
              </View>
              <View>
                <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.systemMonitorPanel.auto.text.006', 'Memory')}</Text>
                <Text style={{ color: C.muted, fontSize: 10 }}>{current.memory.used_gb} / {current.memory.total_gb} GB</Text>
              </View>
            </View>
            <Text style={{ color: statusColor(current.memory.percent), fontSize: 20, fontWeight: '900' }}>{current.memory.percent}%</Text>
          </View>
          <MiniChart values={memHistory} color={colors.purpleText} maxVal={100} />
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
            <Text style={{ color: C.muted, fontSize: 10 }}>Available: {current.memory.available_gb} GB</Text>
            <Text style={{ color: C.muted, fontSize: 10 }}>Used: {current.memory.used_gb} GB</Text>
          </View>
        </View>
      </View>

      {/* Network & Disk Row */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 12 }}>
        {/* Network Card */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="network-card" testID="network-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="swap-vertical" size={16} color={colors.successText} />
            </View>
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.systemMonitorPanel.auto.text.007', 'Network')}</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 14, marginBottom: 8 }}>
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <Ionicons name="arrow-up" size={12} color={colors.warningText} />
                <Text style={{ color: colors.warningText, fontSize: 13, fontWeight: '800' }}>{formatBytes(current.network.bytes_sent_rate)}</Text>
              </View>
              <Text style={{ color: C.muted, fontSize: 9 }}>{tx('admin.systemMonitorPanel.auto.text.008', 'Upload')}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <Ionicons name="arrow-down" size={12} color={colors.primary} />
                <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '800' }}>{formatBytes(current.network.bytes_recv_rate)}</Text>
              </View>
              <Text style={{ color: C.muted, fontSize: 9 }}>{tx('admin.systemMonitorPanel.auto.text.009', 'Download')}</Text>
            </View>
          </View>
          <MiniChart values={netRecvHistory.length > 0 ? netRecvHistory : [0]} color={colors.successText} />
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
            <Text style={{ color: C.muted, fontSize: 10 }}>Total sent: {current.network.total_sent_gb} GB</Text>
            <Text style={{ color: C.muted, fontSize: 10 }}>Total recv: {current.network.total_recv_gb} GB</Text>
          </View>
        </View>

        {/* Disk & Process Card */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="disk-card" testID="disk-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.warningSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="disc" size={16} color={colors.warningText} />
            </View>
            <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.systemMonitorPanel.auto.text.010', 'Disk & Processes')}</Text>
          </View>
          {/* Disk bar */}
          <View style={{ marginBottom: 14 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
              <Text style={{ color: C.muted, fontSize: 11, fontWeight: '600' }}>{tx('admin.systemMonitorPanel.auto.text.011', 'Disk Usage')}</Text>
              <Text style={{ color: statusColor(current.disk.percent), fontSize: 11, fontWeight: '700' }}>{current.disk.percent}%</Text>
            </View>
            <View style={{ height: 8, backgroundColor: C.border, borderRadius: 4, overflow: 'hidden' }}>
              <View style={{ height: 8, backgroundColor: statusColor(current.disk.percent), borderRadius: 4, width: `${current.disk.percent}%` }} />
            </View>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 }}>
              <Text style={{ color: C.muted, fontSize: 10 }}>Used: {current.disk.used_gb} GB</Text>
              <Text style={{ color: C.muted, fontSize: 10 }}>Free: {current.disk.free_gb} GB</Text>
            </View>
          </View>
          {/* Process count */}
          <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, padding: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="layers" size={16} color={C.primary} />
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{tx('admin.systemMonitorPanel.auto.text.012', 'Active Processes')}</Text>
            </View>
            <Text style={{ color: C.primary, fontSize: 18, fontWeight: '900' }}>{current.processes}</Text>
          </View>
          <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, padding: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="disc" size={16} color={colors.warningText} />
              <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>{tx('admin.systemMonitorPanel.auto.text.013', 'Total Disk')}</Text>
            </View>
            <Text style={{ color: colors.warningText, fontSize: 18, fontWeight: '900' }}>{current.disk.total_gb} GB</Text>
          </View>
        </View>
      </View>
    </View>
  );
}
