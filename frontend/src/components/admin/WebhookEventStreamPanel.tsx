import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { useHybridPolling } from '../../hooks/useHybridPolling';
import { getWorkflowPollingPreset } from '../../utils/hybridPolling';

const WORKFLOW_POLLING_PRESET = getWorkflowPollingPreset('webhook-stream-fallback');

const TYPE_COLORS: Record<string, string> = {
  'candidate.created': 'var(--app-success)', 'candidate.updated': 'var(--app-primary)', 'job.opened': 'var(--app-primary)', 'job.closed': 'var(--app-text)', // @theme-ok brand/role/state identifier
  'interview.scheduled': 'var(--app-warning)', 'interview.completed': 'var(--app-success)', 'offer.sent': 'var(--app-primary)', 'offer.accepted': 'var(--app-primary)', // @theme-ok brand/role/state identifier
};

type StreamMode = 'off' | 'connecting' | 'live' | 'polling';

export default function WebhookEventStreamPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const INTEGRATION_COLORS: Record<string, { color: string; icon: string }> = {
    greenhouse: { color: 'var(--app-primary)', icon: 'leaf' }, // @theme-ok brand/role/state identifier
    lever: { color: colors.primary, icon: 'git-branch' },
    workday: { color: colors.warningText, icon: 'business' },
  };
  const [filter, setFilter] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [streamMode, setStreamMode] = useState<StreamMode>('connecting');
  const [liveEvents, setLiveEvents] = useState<any[]>([]);
  const [streamEnabled, setStreamEnabled] = useState(true);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const lastEventTimeRef = useRef<string | null>(null);

  const { data: initialData, loading: initialLoading, refetch: load } = useLiveQuery(
    `/webhook-events/stream${filter ? `?integration_id=${filter}` : ''}`,
    { entity: 'webhooks', pollInterval: 30000, deps: [filter] }
  );
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (initialData) {
      setData(initialData);
      if (initialData?.events?.[0]?.created_at) {
        lastEventTimeRef.current = initialData.events[0].created_at;
      }
      setLoading(false);
    }
    if (!initialLoading && !initialData) setLoading(false);
  }, [initialData, initialLoading]);

  // Poll for new events (fallback when SSE doesn't work through proxy)
  const pollForEvents = useCallback(async () => {
    try {
      const params = filter ? `?integration_id=${filter}` : '';
      const r = await api.get(`/webhook-events/stream${params}`);
      const events = r.data?.events || [];
      if (events.length > 0 && events[0].created_at !== lastEventTimeRef.current) {
        const newEvents = lastEventTimeRef.current
          ? events.filter((e: any) => e.created_at > lastEventTimeRef.current!)
          : [];
        if (newEvents.length > 0) {
          setLiveEvents(prev => [...newEvents, ...prev].slice(0, 50));
        }
        lastEventTimeRef.current = events[0].created_at;
        setData(r.data);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/WebhookEventStreamPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [filter]);

  const startPolling = useCallback(() => {
    setPollingEnabled(true);
    setStreamMode('polling');
  }, []);

  const stopPolling = useCallback(() => {
    setPollingEnabled(false);
  }, []);

  useHybridPolling({
    enabled: pollingEnabled,
    errorScope: 'admin/webhook-event-stream/poll-fallback',
    onTick: pollForEvents,
    runOnMount: WORKFLOW_POLLING_PRESET.runOnMount,
    slowIntervalMs: WORKFLOW_POLLING_PRESET.slowIntervalMs,
    fastIntervalMs: WORKFLOW_POLLING_PRESET.fastIntervalMs,
    wsEnabled: WORKFLOW_POLLING_PRESET.wsEnabled,
  });

  // SSE Connection with polling fallback
  useEffect(() => {
    if (!streamEnabled || Platform.OS !== 'web') {
      stopPolling();
      setStreamMode('off');
      return;
    }
    setStreamMode('connecting');

    const backendUrl = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.REACT_APP_BACKEND_URL || '');
    const token = typeof localStorage !== 'undefined' ? localStorage.getItem('session_token') : null;
    if (!token || !backendUrl) { startPolling(); return; }

    const params = new URLSearchParams({ token });
    if (filter) params.set('integration_id', filter);
    const url = `${backendUrl}/api/webhook-events/sse?${params.toString()}`;

    let sseWorking = false;
    // Fallback timer: if SSE doesn't deliver data within 8s, switch to polling
    const fallbackTimer = setTimeout(() => {
      if (!sseWorking) {
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }
        startPolling();
      }
    }, 8000);

    try {
      const es = new EventSource(url);
      eventSourceRef.current = es;
      es.onmessage = (event) => {
        sseWorking = true;
        clearTimeout(fallbackTimer);
        stopPolling();
        setStreamMode('live');
        try {
          const evt = JSON.parse(event.data);
          setLiveEvents(prev => [evt, ...prev].slice(0, 50));
        } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/WebhookEventStreamPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      };
      es.onerror = () => {
        if (!sseWorking) {
          clearTimeout(fallbackTimer);
          es.close();
          eventSourceRef.current = null;
          startPolling();
        }
      };
    } catch {
      clearTimeout(fallbackTimer);
      startPolling();
    }

    return () => {
      clearTimeout(fallbackTimer);
      stopPolling();
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [streamEnabled, filter, startPolling, stopPolling]);

  const simulate = async () => {
    setSimulating(true);
    try {
      await api.post('/webhook-events/simulate');
      load();
      // Immediately poll if in polling mode
      if (streamMode === 'polling') setTimeout(pollForEvents, 1000);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/WebhookEventStreamPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSimulating(false);
  };

  // Merge live events with loaded events (dedup)
  const allEvents = React.useMemo(() => {
    const loaded = data?.events || [];
    const liveIds = new Set(liveEvents.map(e => e.event_id));
    const merged = [...liveEvents, ...loaded.filter((e: any) => !liveIds.has(e.event_id))];
    return merged.slice(0, 30);
  }, [data, liveEvents]);

  if (loading && !data) return <ActivityIndicator color={'var(--app-primary)'} />;

  return (
    <View data-testid="admin-webhook-stream" testID="admin-webhook-stream">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.webhookEventStreamPanel.auto.text.001', 'Webhook Event Stream')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.webhookEventStreamPanel.auto.text.002', 'Real-time integration events from ATS/HRIS platforms')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {/* Stream Status */}
          <TouchableOpacity onPress={() => setStreamEnabled(!streamEnabled)} data-testid="sse-toggle-btn" testID="sse-toggle-btn"
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: streamMode === 'live' ? 'var(--app-success-soft)' : streamMode === 'polling' ? 'var(--app-primary-soft)' : colors.card, borderWidth: 1, borderColor: streamMode === 'live' ? 'var(--app-success-soft)' : streamMode === 'polling' ? 'var(--app-primary-soft)' : colors.border }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: streamMode === 'live' ? 'var(--app-success)' : streamMode === 'polling' ? 'var(--app-primary)' : colors.textMuted }} />
            <Text style={{ color: streamMode === 'live' ? 'var(--app-success)' : streamMode === 'polling' ? 'var(--app-primary)' : colors.textMuted, fontSize: 10, fontWeight: '700' }}>
              {streamMode === 'live' ? 'LIVE' : streamMode === 'polling' ? 'POLLING' : streamMode === 'connecting' ? 'Connecting...' : 'OFF'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={simulate} disabled={simulating} data-testid="simulate-webhook-btn" testID="simulate-webhook-btn"
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, opacity: simulating ? 0.6 : 1 }}>
            <Ionicons name="flash" size={14} color="var(--app-primary-text)" />
            <Text style={{ color: colors.buttonText, fontSize: 11, fontWeight: '700' }}>{simulating ? 'Generating...' : 'Simulate Event'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Stats */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, marginBottom: 16 }}>
        <View style={{ flex: 1, backgroundColor: colors.primarySoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.primarySoft }}>
          <Text style={{ color: colors.primary, fontSize: 20, fontWeight: '800' }}>{data?.total || 0}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.webhookEventStreamPanel.auto.text.003', 'Total Events')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.successSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.successSoft }}>
          <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '800' }}>{data?.event_type_stats?.length || 0}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.webhookEventStreamPanel.auto.text.004', 'Event Types')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.warningSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.warningSoft }}>
          <Text style={{ color: colors.warningText, fontSize: 20, fontWeight: '800' }}>{liveEvents.length}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.webhookEventStreamPanel.auto.text.005', 'Live Queue')}</Text>
        </View>
      </View>

      {/* Integration Filters */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 14 }} data-testid="webhook-filter-wrap" testID="webhook-filter-wrap">
        <TouchableOpacity onPress={() => setFilter(null)} data-testid="filter-all" testID="filter-all"
          style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: !filter ? 'var(--app-primary)' : colors.bgAlt, borderWidth: 1, borderColor: !filter ? 'var(--app-primary)' : colors.border }}>
          <Text style={{ color: !filter ? 'var(--app-primary-text)' : colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('admin.webhookEventStreamPanel.auto.text.006', 'All')}</Text>
        </TouchableOpacity>
        {Object.entries(INTEGRATION_COLORS).map(([id, meta]) => (
          <TouchableOpacity key={id} onPress={() => setFilter(filter === id ? null : id)} data-testid={`filter-${id}`} testID={`filter-${id}`}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: filter === id ? (globalThis as any).__alphaColor(meta.color, '20') : colors.bgAlt, borderWidth: 1, borderColor: filter === id ? meta.color: colors.border }}>
            <Ionicons name={meta.icon as any} size={12} color={meta.color} />
            <Text style={{ color: filter === id ? meta.color : colors.text, fontSize: 11, fontWeight: '600', textTransform: 'capitalize' }}>{id}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Event Type Stats */}
      {(data?.event_type_stats || []).length > 0 && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 14 }}>
          {(data.event_type_stats || []).map((s: any) => (
            <View key={s.type} style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor((TYPE_COLORS[s.type] || colors.border), '10'), paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
              <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: TYPE_COLORS[s.type] || colors.border }} />
              <Text style={{ color: colors.text, fontSize: 9, fontWeight: '600' }}>{s.type}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '800' }}>x{s.count}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Event Feed */}
      <View style={{ backgroundColor: colors.bgAlt || colors.bg, borderRadius: 12, padding: 2, borderWidth: 1, borderColor: colors.border }}>
        {allEvents.length === 0 ? (
          <View style={{ padding: 32, alignItems: 'center' }}>
            <Ionicons name="radio-outline" size={32} color={colors.textMuted} />
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{tx('admin.webhookEventStreamPanel.auto.text.007', 'No events yet. Click "Simulate Event" to test.')}</Text>
          </View>
        ) : allEvents.slice(0, 20).map((evt: any, idx: number) => {
          const ic = INTEGRATION_COLORS[evt.integration_id] || { color: colors.textSec, icon: 'link' };
          const tc = TYPE_COLORS[evt.event_type] || colors.textMuted;
          const isLive = liveEvents.some(le => le.event_id === evt.event_id);
          return (
            <View key={evt.event_id || idx} data-testid={`webhook-event-${idx}`} testID={`webhook-event-${idx}`}
              style={{ flexDirection: 'row', alignItems: 'center', padding: 10, borderBottomWidth: idx < 19 ? 1 : 0, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '40'), gap: 10, backgroundColor: isLive ? (globalThis as any).__alphaColor(tc, '05') : 'transparent' }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: tc }} />
              <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(ic.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={ic.icon as any} size={14} color={ic.color} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{evt.event_type}</Text>
                  <Text style={{ color: ic.color, fontSize: 9, fontWeight: '600', textTransform: 'uppercase' }}>{evt.integration_id}</Text>
                  {isLive && (
                    <View style={{ backgroundColor: colors.successSoft, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3 }}>
                      <Text style={{ color: colors.successText, fontSize: 7, fontWeight: '800' }}>{tx('admin.webhookEventStreamPanel.auto.text.008', 'LIVE')}</Text>
                    </View>
                  )}
                </View>
                <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 1 }}>
                  {evt.payload?.candidate || ''} {evt.payload?.position ? `- ${evt.payload.position}` : ''}
                </Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <View style={{ backgroundColor: evt.status === 'received' ? 'var(--app-success-soft)' : 'var(--app-warning-soft)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                  <Text style={{ color: evt.status === 'received' ? 'var(--app-success)' : 'var(--app-warning)', fontSize: 8, fontWeight: '800' }}>{(evt.status || '').toUpperCase()}</Text>
                </View>
                <Text style={{ color: colors.textMuted + '80', fontSize: 9, marginTop: 2 }}>
                  {evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : ''}
                </Text>
              </View>
            </View>
          );
        })}
      </View>

      <TouchableOpacity onPress={load} data-testid="refresh-events-btn" testID="refresh-events-btn"
        style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, marginTop: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.bgAlt || colors.bg, borderWidth: 1, borderColor: colors.border }}>
        <Ionicons name="refresh" size={14} color={'var(--app-text-muted)'} />
        <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('admin.webhookEventStreamPanel.auto.text.009', 'Refresh')}</Text>
      </TouchableOpacity>
    </View>
  );
}
