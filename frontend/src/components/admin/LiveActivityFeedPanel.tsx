import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, useWindowDimensions, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);

const tx = (_key: string, fallback: string) => fallback;

const EVENT_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  login: { icon: 'log-in-outline', color: C.cyan, label: 'Login' },
  logout: { icon: 'log-out-outline', color: C.muted, label: 'Logout' },
  feature_usage: { icon: 'flash-outline', color: C.purpleText, label: 'Feature' },
  page_view: { icon: 'eye-outline', color: C.blue, label: 'View' },
  completion: { icon: 'trophy-outline', color: C.yellow, label: 'Complete' },
  error: { icon: 'warning-outline', color: C.red, label: 'Error' },
  upgrade: { icon: 'star-outline', color: C.orangeText, label: 'Upgrade' },
  api_call: { icon: 'code-slash-outline', color: C.green, label: 'API' },
  admin_action: { icon: 'shield-checkmark-outline', color: C.error, label: 'Admin' },
  signup: { icon: 'person-add-outline', color: C.accent, label: 'Signup' },
  payment: { icon: 'card-outline', color: C.green, label: 'Payment' },
  support: { icon: 'chatbox-outline', color: C.orangeText, label: 'Support' },
};

/* ---- Metric Card ---- */
function MetricCard({ label, value, trend, trendValue, icon, color, compact }: {
  label: string; value: number | string; trend?: string; trendValue?: string;
  icon: string; color: string; compact?: boolean;
}) {
  const isUp = trend === 'up';
  const isDown = trend === 'down';
  return (
    <View style={{
      flex: compact ? undefined : 1, minWidth: compact ? 130 : 150,
      backgroundColor: C.card, borderRadius: 14, padding: compact ? 14 : 18,
      borderWidth: 1, borderColor: C.border,
    }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '15'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={15} color={color} />
        </View>
        {trend && (
          <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: (globalThis as any).__alphaColor((isUp ? C.green : isDown ? C.red : C.muted), '15'), borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
            <Ionicons name={isUp ? 'trending-up' : isDown ? 'trending-down' : 'remove-outline'} size={11} color={isUp ? C.green : isDown ? C.red : C.muted} />
            {trendValue && <Text style={{ fontSize: 10, fontWeight: '700', color: isUp ? C.green : isDown ? C.red : C.muted, marginLeft: 3 }}>{trendValue}</Text>}
          </View>
        )}
      </View>
      <Text style={{ fontSize: compact ? 22 : 26, fontWeight: '800', color: C.text, fontVariant: ['tabular-nums'], letterSpacing: -0.5 }}>{typeof value === 'number' ? value.toLocaleString() : value}</Text>
      <Text style={{ fontSize: 11, color: C.muted, fontWeight: '500', marginTop: 2 }}>{label}</Text>
    </View>
  );
}

/* ---- Hourly Sparkline ---- */
function HourlyChart({ data, color }: { data: Record<string, number>; color: string }) {
  const max = Math.max(...Object.values(data).map(Number), 1);
  const currentHour = new Date().getUTCHours();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 48, gap: 1 }}>
      {Array.from({ length: 24 }, (_, h) => {
        const key = String(h).padStart(2, '0');
        const val = data[key] || 0;
        const isCurrent = h === currentHour;
        return (
          <View key={h} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
            <View style={{
              width: '75%', height: Math.max(2, (val / max) * 44),
              backgroundColor: (globalThis as any).__alphaColor(isCurrent ? color : color, '45'),
              borderRadius: 2,
            }} />
          </View>
        );
      })}
    </View>
  );
}

/* ---- Top Users Row ---- */
function TopUserRow({ user, rank }: { user: { email: string; count: number }; rank: number }) {
  const initial = (user.email?.[0] || '?').toUpperCase();
  const colors = [C.cyan, C.purple, C.orange, C.green, C.error];
  const c = colors[rank % colors.length];
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, paddingHorizontal: 2 }}>
      <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(c, '20'), alignItems: 'center', justifyContent: 'center', marginRight: 10 }}>
        <Text style={{ fontSize: 12, fontWeight: '700', color: c }}>{initial}</Text>
      </View>
      <Text style={{ flex: 1, fontSize: 12, color: C.text, fontWeight: '500' }} numberOfLines={1}>{user.email}</Text>
      <Text style={{ fontSize: 12, fontWeight: '700', color: C.sec, fontVariant: ['tabular-nums'] }}>{user.count}</Text>
    </View>
  );
}

/* ---- Activity Event Row ---- */
const ActivityRow = React.memo(function ActivityRow({ event, isNew }: { event: any; isNew?: boolean }) {
  const config = EVENT_CONFIG[event.event_type] || { icon: 'ellipse-outline', color: C.muted, label: event.event_type };
  const timeAgo = useMemo(() => {
    const diff = Date.now() - new Date(event.timestamp).getTime();
    if (diff < 60000) return 'now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`;
    return `${Math.floor(diff / 86400000)}d`;
  }, [event.timestamp]);

  return (
    <View
      data-testid={`activity-row-${event.event_type}`} testID={`activity-row-${event.event_type}`}
      style={{
        flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 14,
        borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '30'),
        backgroundColor: isNew ? (globalThis as any).__alphaColor(config.color, '06') : 'transparent',
      }}
    >
      <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(config.color, '14'), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={config.icon as any} size={14} color={config.color} />
      </View>
      <View style={{ flex: 1, marginLeft: 10 }}>
        <Text style={{ fontSize: 12.5, color: C.text, fontWeight: '500' }} numberOfLines={1}>{event.detail || 'Activity event'}</Text>
        <Text style={{ fontSize: 10.5, color: C.muted, marginTop: 1 }}>{event.user_email || 'System'}</Text>
      </View>
      <View style={{ alignItems: 'flex-end', marginLeft: 6 }}>
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(config.color, '14'), borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1.5 }}>
          <Text style={{ fontSize: 8.5, color: config.color, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.3 }}>{config.label}</Text>
        </View>
        <Text style={{ fontSize: 9.5, color: C.muted, marginTop: 2, fontVariant: ['tabular-nums'] }}>{timeAgo}</Text>
      </View>
    </View>
  );
});

/* ---- Alert Banner ---- */
function AlertBanner({ alerts }: { alerts: any[] }) {
  if (!alerts || alerts.length === 0) return null;
  const alert = alerts[0];
  const isC = alert.level === 'critical';
  const color = isC ? C.red : C.yellow;
  return (
    <View data-testid="activity-alert-banner" testID="activity-alert-banner" style={{
      flexDirection: 'row', alignItems: 'center', backgroundColor: (globalThis as any).__alphaColor(color, '10'),
      borderRadius: 10, padding: 12, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '30'),
    }}>
      <Ionicons name={isC ? 'alert-circle' : 'warning'} size={18} color={color} />
      <Text style={{ flex: 1, fontSize: 12, color, fontWeight: '600', marginLeft: 10 }}>{alert.message}</Text>
      <View style={{ backgroundColor: (globalThis as any).__alphaColor(color, '20'), borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}>
        <Text style={{ fontSize: 9, fontWeight: '800', color, textTransform: 'uppercase' }}>{alert.level}</Text>
      </View>
    </View>
  );
}

/* ============ MAIN PANEL ============ */
export default function LiveActivityFeedPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const { width } = useWindowDimensions();
  const isWide = width >= 1024;
  const isMed = width >= 768;
  const [filter, setFilter] = useState<string>('');
  const [liveEvents, setLiveEvents] = useState<any[]>([]);
  const [liveCount, setLiveCount] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsError, setWsError] = useState('');

  // Polling: faster for real-time feel
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { data: feedData, loading, refetch: _refetchFeed } = useLiveQuery(
    '/admin/live-activity/feed' + (filter ? `?event_type=${filter}&limit=60` : '?limit=60'),
    { entity: 'live-activity', pollInterval: 8000 }
  );
  const { data: statsData } = useLiveQuery('/admin/live-activity/stats', { entity: 'live-activity-stats', pollInterval: 10000 });
  const { data: summaryData } = useLiveQuery('/admin/live-activity/summary', { entity: 'live-activity-summary', pollInterval: 15000 });
  const { data: alertData } = useLiveQuery('/admin/live-activity/alerts', { entity: 'live-activity-alerts', pollInterval: 20000 });

  const buildWsUrl = useCallback(async () => {
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'admin_activity' });
    const wsTicket = String(ticketResp?.data?.ticket || '').trim();
    if (!wsTicket) {
      throw new Error('Missing websocket ticket for admin activity stream');
    }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/api/ws/admin-activity?ticket=${encodeURIComponent(wsTicket)}`;
  }, []);

  const { lastError } = useManagedWebSocket({
    enabled: Platform.OS === 'web',
    buildUrl: buildWsUrl,
    errorScope: 'admin/live-activity/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1200,
    onOpen: () => {
      setWsConnected(true);
      setWsError('');
    },
    onClose: () => {
      setWsConnected(false);
    },
    onError: () => {
      setWsConnected(false);
      setWsError('Live activity stream interrupted. Reconnecting...');
    },
    onReconnectAttempt: (attempt) => {
      setWsConnected(false);
      setWsError(`Reconnecting live activity stream (${attempt})...`);
    },
    onMessage: (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'activity_event' && msg.data) {
          setLiveEvents(prev => [msg.data, ...prev].slice(0, 30));
          setLiveCount(c => c + 1);
          setWsError('');
        }
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/live-activity/parse',
          fallbackMessage: 'A live activity event could not be processed.',
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

  const allEvents = useMemo(() => {
    const feedEvents = feedData?.events || [];
    const merged = [...liveEvents, ...feedEvents];
    const seen = new Set<string>();
    return merged.filter(e => {
      const key = e.timestamp + e.detail;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).slice(0, 60);
  }, [feedData?.events, liveEvents]);

  const typeCounts = feedData?.type_counts || {};
  const stats = statsData || {};
  const summary = summaryData || {};
  const alerts = alertData?.alerts || [];

  const filterTypes = useMemo(() => [
    '', 'login', 'feature_usage', 'page_view', 'completion', 'upgrade', 'api_call', 'admin_action', 'error'
  ], []);

  const [exporting, setExporting] = useState<string>('');
  const handleExport = useCallback(async (format: 'csv' | 'pdf' | 'json') => {
    if (Platform.OS !== 'web') return;
    setExporting(format);
    try {
      const params = new URLSearchParams({ hours: '24' });
      if (filter) params.append('event_type', filter);
      const resp = await api.get(`/admin/live-activity/export/${format}?${params}`, { responseType: 'blob' });
      const blob = new Blob([resp.data], { type: format === 'pdf' ? 'application/pdf' : format === 'json' ? 'application/json' : 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `activity_feed.${format}`; a.click();
      URL.revokeObjectURL(url);
      setWsError('');
    } catch (error) {
      handleRecoverableError(error, {
        scope: 'admin/live-activity/export',
        fallbackMessage: `Unable to export ${format.toUpperCase()} right now.`,
        setMessage: setWsError,
      });
    }
    setExporting('');
  }, [filter]);

  if (loading && !feedData) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <AutoFixBanner domain="live_activity" />
        <ActivityIndicator size="large" color={C.cyan} />
        <Text style={{ color: C.muted, marginTop: 12, fontSize: 13 }}>{tx('admin.liveActivityFeedPanel.auto.text.001', 'Loading activity feed...')}</Text>
      </View>
    );
  }

  const topUsers = summary.most_active_users || [];
  const topTypes = summary.top_event_types || [];
  const trendDir = summary.trend || 'stable';
  const changePct = summary.change_percent ?? 0;

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: isMed ? 24 : 14 }} role="region" aria-label="Live Activity Feed">
      <AutoFixBanner domain="live_activity" />

      {/* Header */}
      <View style={{ flexDirection: isMed ? 'row' : 'column', alignItems: isMed ? 'center' : 'flex-start', marginBottom: 20, gap: isMed ? 0 : 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
          <View style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.cyan, '15'), alignItems: 'center', justifyContent: 'center', marginRight: 12 }}>
            <Ionicons name="pulse" size={20} color={C.cyan} />
          </View>
          <View>
            <Text data-testid="activity-feed-title" testID="activity-feed-title" style={{ fontSize: 18, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>{tx('admin.liveActivityFeedPanel.auto.text.002', 'Live Activity Feed')}</Text>
            <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.liveActivityFeedPanel.auto.text.003', 'Real-time platform monitoring')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          {(['csv', 'pdf', 'json'] as const).map(fmt => (
            <TouchableOpacity key={fmt} onPress={() => handleExport(fmt)} disabled={!!exporting}
              style={{ backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: C.border, opacity: exporting ? 0.5 : 1 }}
              data-testid={`export-${fmt}-btn`} testID={`export-${fmt}-btn`} accessibilityRole="button">
              {exporting === fmt ? <ActivityIndicator size={10} color={C.sec} /> : <Text style={{ fontSize: 10, fontWeight: '600', color: C.sec, textTransform: 'uppercase' }}>{fmt}</Text>}
            </TouchableOpacity>
          ))}
          <View data-testid="activity-feed-ws-status" testID="activity-feed-ws-status" style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: (globalThis as any).__alphaColor(wsConnected ? C.green : C.yellow, '12'), borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(wsConnected ? C.green : C.yellow, '25') }}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: wsConnected ? C.green : C.yellow, marginRight: 6 }} />
            <Text style={{ fontSize: 11, color: wsConnected ? C.green : C.yellow, fontWeight: '700' }}>{wsConnected ? tx('admin.liveActivityFeedPanel.auto.text.004', 'LIVE') : tx('admin.liveActivityFeedPanel.auto.text.014', 'RECONNECTING')}</Text>
            {liveCount > 0 && <Text style={{ fontSize: 9, color: C.green, fontWeight: '700', marginLeft: 4 }}>+{liveCount}</Text>}
          </View>
        </View>
      </View>

      {!!wsError && (
        <View data-testid="activity-feed-ws-error" testID="activity-feed-ws-error" style={{ backgroundColor: (globalThis as any).__alphaColor(C.red, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '30'), borderRadius: 10, padding: 10, marginBottom: 14 }}>
          <Text style={{ color: C.red, fontSize: 11, fontWeight: '600' }}>{wsError}</Text>
        </View>
      )}

      {/* Alert Banner */}
      <AlertBanner alerts={alerts} />

      {/* Metric Cards */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <MetricCard label="Events (24h)" value={stats.events_24h ?? summary.current_total ?? 0} icon="analytics-outline" color={C.cyan}
          trend={trendDir} trendValue={changePct !== 0 ? `${changePct > 0 ? '+' : ''}${changePct.toFixed(1)}%` : undefined} />
        <MetricCard label="Events (1h)" value={stats.events_1h ?? 0} icon="time-outline" color={C.blue} />
        <MetricCard label="Active Users" value={stats.unique_users_24h ?? 0} icon="people-outline" color={C.green} />
        {isWide && <MetricCard label="Errors (1h)" value={alertData?.metrics?.errors_1h ?? 0} icon="bug-outline" color={C.red}
          trend={(alertData?.metrics?.errors_1h ?? 0) > 5 ? 'up' : undefined} />}
      </View>

      {/* Main content: Two-column on desktop */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16 }}>
        {/* Left: Feed */}
        <View style={{ flex: isWide ? 3 : undefined }}>
          {/* Filter Pills */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }} contentContainerStyle={{ gap: 5 }}>
            {filterTypes.map(type => {
              const active = filter === type;
              const config = type ? EVENT_CONFIG[type] : null;
              const label = type ? (config?.label || type) : 'All';
              const count = type ? (typeCounts[type] || 0) : Object.values(typeCounts).reduce((a: number, b: any) => a + b, 0);
              return (
                <TouchableOpacity accessibilityLabel={tx('admin.liveActivityFeedPanel.auto.accessibility.001', 'Filter live activity events')}
                  key={type || 'all'} onPress={() => setFilter(type)}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 3,
                    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8,
                    backgroundColor: active ? (globalThis as any).__alphaColor((config?.color || C.cyan), '18') : C.card,
                    borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor((config?.color || C.cyan), '35') : C.border,
                  }}
                  accessibilityRole="button" data-testid={`filter-${type || 'all'}`} testID={`filter-${type || 'all'}`}
                >
                  {config && <Ionicons name={config.icon as any} size={11} color={active ? config.color : C.muted} />}
                  <Text style={{ fontSize: 10.5, fontWeight: '600', color: active ? (config?.color || C.cyan) : C.sec }}>{label}</Text>
                  {count > 0 && <Text style={{ fontSize: 9, color: C.muted, fontVariant: ['tabular-nums'] }}>{count}</Text>}
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          {/* Events List */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden', maxHeight: isWide ? 520 : undefined }} role="list" aria-label="Activity events">
            {allEvents.length === 0 ? (
              <View style={{ padding: 40, alignItems: 'center' }}>
                <Ionicons name="pulse-outline" size={28} color={C.muted} />
                <Text style={{ color: C.muted, fontSize: 13, marginTop: 8 }}>{tx('admin.liveActivityFeedPanel.auto.text.005', 'No events match this filter')}</Text>
              </View>
            ) : (
              allEvents.map((event, i) => (
                <ActivityRow key={event.timestamp + event.detail + i} event={event}
                  isNew={liveEvents.some(le => le.timestamp === event.timestamp && le.detail === event.detail)} />
              ))
            )}
          </View>
        </View>

        {/* Right: Sidebar (analytics) */}
        <View style={{ flex: isWide ? 1 : undefined, gap: 16 }}>
          {/* Hourly Activity Chart */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 16 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{tx('admin.liveActivityFeedPanel.auto.text.006', 'Hourly Activity')}</Text>
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.liveActivityFeedPanel.auto.text.007', 'Last 24h')}</Text>
            </View>
            <HourlyChart data={stats.events_per_hour || {}} color={C.cyan} />
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 }}>
              <Text style={{ fontSize: 8, color: C.muted }}>00:00</Text>
              <Text style={{ fontSize: 8, color: C.muted }}>12:00</Text>
              <Text style={{ fontSize: 8, color: C.muted }}>23:00</Text>
            </View>
          </View>

          {/* Top Event Types */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 16 }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.liveActivityFeedPanel.auto.text.008', 'Top Event Types')}</Text>
            {topTypes.slice(0, 5).map((t: any, i: number) => {
              const cfg = EVENT_CONFIG[t.type] || { icon: 'ellipse-outline', color: C.muted, label: t.type };
              const maxCount = topTypes[0]?.count || 1;
              return (
                <View key={t.type} style={{ marginBottom: 10 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Ionicons name={cfg.icon as any} size={12} color={cfg.color} />
                      <Text style={{ fontSize: 11, color: C.text, fontWeight: '500' }}>{cfg.label}</Text>
                    </View>
                    <Text style={{ fontSize: 11, color: C.sec, fontWeight: '700', fontVariant: ['tabular-nums'] }}>{t.count}</Text>
                  </View>
                  <View style={{ height: 4, backgroundColor: C.border, borderRadius: 2 }}>
                    <View style={{ height: 4, width: `${(t.count / maxCount) * 100}%`, backgroundColor: cfg.color, borderRadius: 2 }} />
                  </View>
                </View>
              );
            })}
          </View>

          {/* Most Active Users */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 16 }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('admin.liveActivityFeedPanel.auto.text.009', 'Most Active Users')}</Text>
            {topUsers.length === 0 ? (
              <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.liveActivityFeedPanel.auto.text.010', 'No active users yet')}</Text>
            ) : (
              topUsers.slice(0, 5).map((u: any, i: number) => (
                <TopUserRow key={u.email} user={u} rank={i} />
              ))
            )}
          </View>

          {/* Quick Stats */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 16 }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.liveActivityFeedPanel.auto.text.011', 'Period Comparison')}</Text>
            <View style={{ gap: 8 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.liveActivityFeedPanel.auto.text.012', 'Current 24h')}</Text>
                <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, fontVariant: ['tabular-nums'] }}>{(summary.current_total || 0).toLocaleString()}</Text>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.liveActivityFeedPanel.auto.text.013', 'Previous 24h')}</Text>
                <Text style={{ fontSize: 13, fontWeight: '700', color: C.sec, fontVariant: ['tabular-nums'] }}>{(summary.previous_total || 0).toLocaleString()}</Text>
              </View>
              <View style={{ height: 1, backgroundColor: C.border, marginVertical: 2 }} />
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.liveActivityFeedPanel.auto.text.014', 'Change')}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <Ionicons
                    name={changePct > 0 ? 'arrow-up' : changePct < 0 ? 'arrow-down' : 'remove'}
                    size={12} color={changePct > 0 ? C.green : changePct < 0 ? C.red : C.muted}
                  />
                  <Text style={{ fontSize: 13, fontWeight: '800', color: changePct > 0 ? C.green : changePct < 0 ? C.red : C.muted }}>
                    {Math.abs(changePct).toFixed(1)}%
                  </Text>
                </View>
              </View>
            </View>
          </View>
        </View>
      </View>
    </ScrollView>
  );
}
