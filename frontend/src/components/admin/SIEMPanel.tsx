import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import DataFreshnessIndicator from '../DataFreshnessIndicator';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
interface Props { colors: any; }

const tx = (_key: string, fallback: string) => fallback;

const RISK_COLORS: Record<string, string> = {
  critical: 'var(--app-error)' as any,
  high: 'var(--app-warning)' as any,
  medium: 'var(--app-primary)' as any,
  low: 'var(--app-success)' as any,
  unknown: 'var(--app-text-muted)' as any,
};

function makeT(AC: any) { return {
  bg: AC.bg,
  surface: AC.surface || AC.card,
  card: AC.card,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textDim,
  primary: AC.primary,
  primarySoft: AC.primarySoft,
}; }

export default function SIEMPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<'overview' | 'events' | 'audit' | 'rules' | 'live' | 'alerts'>('overview');
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsPage, setEventsPage] = useState(1);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [rules, setRules] = useState<any[]>([]);
  const [timeline, setTimeline] = useState<any>(null);
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  // Live feed state
  const [liveEvents, setLiveEvents] = useState<any[]>([]);
  const [livePaused, setLivePaused] = useState(false);
  const [liveConnected, setLiveConnected] = useState(false);
  const [liveWsError, setLiveWsError] = useState('');
  // Triggered alerts
  const [triggeredAlerts, setTriggeredAlerts] = useState<any[]>([]);
  const [alertsTotal, setAlertsTotal] = useState(0);
  // New rule form
  const [newRuleName, setNewRuleName] = useState('');
  const [newRuleEvent, setNewRuleEvent] = useState('login_failed');
  const [newRuleThreshold, setNewRuleThreshold] = useState('5');
  const [newRuleWindow, setNewRuleWindow] = useState('10');

  const loadOverview = useCallback(async () => {
    try {
      const [ov, tl] = await Promise.all([
        api.get('/admin/siem/overview'),
        api.get('/admin/siem/timeline?days=7'),
      ]);
      setOverview(ov.data);
      setTimeline(tl.data);
    } catch (e) { console.error(e); }
  }, []);

  const loadEvents = useCallback(async (page = 1) => {
    try {
      const params: any = { page, limit: 30, days: 7 };
      if (search) params.search = search;
      if (riskFilter) params.risk_level = riskFilter;
      const res = await api.get('/admin/siem/events', { params });
      setEvents(res.data.events);
      setEventsTotal(res.data.total);
      setEventsPage(page);
    } catch (e) { console.error(e); }
  }, [search, riskFilter]);

  const loadAudit = useCallback(async () => {
    try {
      const res = await api.get('/admin/siem/audit-log', { params: { limit: 30, days: 7 } });
      setAuditLogs(res.data.logs);
      setAuditTotal(res.data.total);
    } catch (e) { console.error(e); }
  }, []);

  const loadRules = useCallback(async () => {
    try {
      const res = await api.get('/admin/siem/alert-rules');
      setRules(res.data.rules);
    } catch (e) { console.error(e); }
  }, []);

  const loadAlerts = useCallback(async () => {
    try {
      const res = await api.get('/admin/siem/alerts');
      setTriggeredAlerts(res.data.alerts);
      setAlertsTotal(res.data.total);
    } catch (e) { console.error(e); }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadOverview(), loadEvents(), loadAudit(), loadRules(), loadAlerts()]);
    setLoading(false);
    setLastUpdated(new Date());
  }, [loadOverview, loadEvents, loadAudit, loadRules, loadAlerts]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { refresh(); }, []);

  const siemWsEnabled = tab === 'live' && Platform.OS === 'web';

  const buildSiemWsUrl = useCallback(async () => {
    const wsOrigin = (typeof window !== 'undefined' && (`https://${window.location.host}`)
      ? (`https://${window.location.host}`)
      : (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '')).replace('https://', 'wss://').replace('http://', 'ws://');
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'siem_events' });
    const wsTicket = String(ticketResp?.data?.ticket || '').trim();
    if (!wsTicket) {
      throw new Error('Missing websocket ticket for SIEM live events');
    }
    return `${wsOrigin}/api/ws/siem-events?ticket=${encodeURIComponent(wsTicket)}`;
  }, []);

  const { lastError: siemWsLastError } = useManagedWebSocket({
    enabled: siemWsEnabled,
    buildUrl: buildSiemWsUrl,
    errorScope: 'admin/siem/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1200,
    onOpen: () => {
      setLiveConnected(true);
      setLiveWsError('');
    },
    onClose: () => {
      setLiveConnected(false);
    },
    onError: () => {
      setLiveConnected(false);
      setLiveWsError('SIEM live feed interrupted. Reconnecting...');
    },
    onReconnectAttempt: (attempt) => {
      setLiveConnected(false);
      setLiveWsError(`Reconnecting SIEM live feed (${attempt})...`);
    },
    onMessage: (e) => {
      if (livePaused) return;
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'events' && msg.data) {
          setLiveEvents(prev => [...msg.data, ...prev].slice(0, 100));
        }
        setLiveWsError('');
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/siem/ws-parse',
          fallbackMessage: 'A SIEM live event could not be processed.',
          setMessage: setLiveWsError,
        });
      }
    },
  });

  useEffect(() => {
    if (siemWsEnabled) return;
    setLiveConnected(false);
    setLiveWsError('');
  }, [siemWsEnabled]);

  useEffect(() => {
    if (!siemWsLastError) return;
    setLiveConnected(false);
    setLiveWsError(siemWsLastError);
  }, [siemWsLastError]);

  const createRule = async () => {
    try {
      await api.post('/admin/siem/alert-rules', {
        name: newRuleName || 'New Alert Rule',
        event_type: newRuleEvent,
        threshold: parseInt(newRuleThreshold) || 5,
        window_minutes: parseInt(newRuleWindow) || 10,
        severity: 'high',
      });
      setNewRuleName('');
      loadRules();
    } catch (e) { console.error(e); }
  };

  const deleteRule = async (ruleId: string) => {
    try { await api.delete(`/admin/siem/alert-rules/${ruleId}`); loadRules(); } catch (e) { console.error(e); }
  };

  const resolveAlert = async (alertId: string) => {
    try { await api.post(`/admin/siem/alerts/${alertId}/resolve`); loadAlerts(); } catch (e) { console.error(e); }
  };

  const evaluateNow = async () => {
    try { await api.post('/admin/siem/evaluate-rules'); loadAlerts(); } catch (e) { console.error(e); }
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  const tabs = [
    { id: 'overview', label: 'Overview', icon: 'shield' },
    { id: 'live', label: 'Live Feed', icon: 'pulse' },
    { id: 'events', label: 'Events', icon: 'list' },
    { id: 'audit', label: 'Audit Log', icon: 'document-text' },
    { id: 'rules', label: 'Alert Rules', icon: 'notifications' },
    { id: 'alerts', label: 'Triggered Alerts', icon: 'alert-circle' },
  ] as const;

  const maxDaily = Math.max(...(timeline?.daily || []).map((d: any) => d.low + d.medium + d.high + d.critical), 1);

  return (
    <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="siem-title" testID="siem-title">{tx('admin.sIEMPanel.auto.text.001', 'SIEM / Logging Center')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 2 }}>{tx('admin.sIEMPanel.auto.text.002', 'Centralized security event management')}</Text>
        </View>
        <DataFreshnessIndicator lastUpdated={lastUpdated} onRefresh={refresh} isRefreshing={loading} accentColor={T.primary} textColor={T.textMuted} />
      </View>

      {!!liveWsError && (
        <View data-testid="siem-ws-error" testID="siem-ws-error" style={{ backgroundColor: (globalThis as any).__alphaColor(colors.error, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '32'), borderRadius: 10, padding: 10, marginBottom: 14 }}>
          <Text style={{ fontSize: 11, color: colors.error, fontWeight: '600' }}>{liveWsError}</Text>
        </View>
      )}

      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20, flexWrap: 'wrap' }} data-testid="siem-tabs" testID="siem-tabs">
        {tabs.map(t => (
          <TouchableOpacity key={t.id} onPress={() => setTab(t.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: tab === t.id ? T.primary : T.card, borderWidth: 1, borderColor: tab === t.id ? T.primary : T.border }}
            data-testid={`siem-tab-${t.id}`} testID={`siem-tab-${t.id}`}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? colors.primaryText : T.textMuted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: tab === t.id ? colors.primaryText : T.textSec }}>{t.label}</Text>
            {t.id === 'alerts' && alertsTotal > 0 && (
              <View style={{ backgroundColor: colors.error, borderRadius: 8, paddingHorizontal: 5, minWidth: 16, alignItems: 'center' }}>
                <Text style={{ fontSize: 9, fontWeight: '800', color: colors.primaryText }}>{alertsTotal}</Text>
              </View>
            )}
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'overview' && overview && (
        <View>
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }} data-testid="siem-kpis" testID="siem-kpis">
            {[
              { label: 'Total Events', value: overview.total_events, icon: 'analytics', color: colors.primary },
              { label: 'Events (24h)', value: overview.events_24h, icon: 'time', color: colors.accent },
              { label: 'Critical (24h)', value: overview.critical_24h, icon: 'alert-circle', color: colors.error },
              { label: 'High (24h)', value: overview.high_24h, icon: 'warning', color: colors.warningText },
              { label: 'Active Alerts', value: overview.active_alerts, icon: 'notifications', color: colors.accent },
            ].map(k => (
              <View key={k.label} style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
                <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(k.color, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
                  <Ionicons name={k.icon as any} size={16} color={k.color} />
                </View>
                <Text style={{ fontSize: 22, fontWeight: '800', color: T.text }}>{k.value?.toLocaleString()}</Text>
                <Text style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', marginTop: 2 }}>{k.label}</Text>
              </View>
            ))}
          </View>

          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="siem-severity" testID="siem-severity">
            <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 12 }}>{tx('admin.sIEMPanel.auto.text.003', 'Severity Breakdown (7d)')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {Object.entries(overview.severity_breakdown || {}).map(([level, count]) => (
                <View key={level} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor((RISK_COLORS[level] || AC.textDim), '15') }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: RISK_COLORS[level] || AC.textDim }} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: RISK_COLORS[level] || AC.textDim }}>{level}</Text>
                  <Text style={{ fontSize: 12, fontWeight: '800', color: T.text }}>{(count as number).toLocaleString()}</Text>
                </View>
              ))}
            </View>
          </View>

          {timeline?.daily?.length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="siem-timeline" testID="siem-timeline">
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 12 }}>{tx('admin.sIEMPanel.auto.text.004', 'Event Timeline (7d)')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: 100 }}>
                {timeline.daily.map((d: any, i: number) => {
                  const total = d.low + d.medium + d.high + d.critical;
                  const h = Math.max((total / maxDaily) * 80, 4);
                  return (
                    <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                      <View style={{ width: '80%', height: h, borderRadius: 4, backgroundColor: d.critical > 0 ? colors.error : d.high > 0 ? colors.warning : colors.primary }} />
                      <Text style={{ fontSize: 8, color: T.textMuted, marginTop: 4 }}>{d.day.slice(5)}</Text>
                    </View>
                  );
                })}
              </View>
            </View>
          )}

          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border, marginBottom: 16 }} data-testid="siem-event-types" testID="siem-event-types">
            <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 12 }}>{tx('admin.sIEMPanel.auto.text.005', 'Top Event Types (7d)')}</Text>
            {(overview.event_types || []).map((t: any) => {
              const maxCount = overview.event_types[0]?.count || 1;
              return (
                <View key={t.type} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <Text style={{ fontSize: 11, color: T.textSec, width: 120, fontWeight: '600' }} numberOfLines={1}>{t.type}</Text>
                  <View style={{ flex: 1, height: 8, borderRadius: 4, backgroundColor: T.border }}>
                    <View style={{ width: `${(t.count / maxCount) * 100}%`, height: 8, borderRadius: 4, backgroundColor: colors.primary }} />
                  </View>
                  <Text style={{ fontSize: 11, fontWeight: '800', color: T.text, width: 40, textAlign: 'right' }}>{t.count}</Text>
                </View>
              );
            })}
          </View>

          {overview.critical_events?.length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: colors.errorSoft, marginBottom: 16 }} data-testid="siem-critical" testID="siem-critical">
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.error, marginBottom: 12 }}>{tx('admin.sIEMPanel.auto.text.006', 'Recent Critical/High Events')}</Text>
              {overview.critical_events.map((e: any, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: i < overview.critical_events.length - 1 ? 1 : 0, borderBottomColor: T.border }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: RISK_COLORS[e.risk_level] || AC.textDim }} />
                  <Text style={{ flex: 1, fontSize: 12, color: T.text, fontWeight: '600' }}>{e.event_type}</Text>
                  <Text style={{ fontSize: 10, color: T.textMuted }}>{e.user_id?.slice(0, 12)}</Text>
                  <Text style={{ fontSize: 10, color: T.textMuted }}>{e.timestamp?.slice(0, 16)}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Live Feed Tab */}
      {tab === 'live' && (
        <View data-testid="siem-live-feed" testID="siem-live-feed">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: liveConnected ? colors.success : colors.error }} />
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{liveConnected ? 'Connected' : 'Disconnected'}</Text>
              <Text style={{ fontSize: 11, color: T.textMuted }}>{liveEvents.length} events captured</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity onPress={() => setLivePaused(!livePaused)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: livePaused ? colors.warning : T.card, borderWidth: 1, borderColor: T.border }} data-testid="siem-live-pause" testID="siem-live-pause">
                <Ionicons name={livePaused ? 'play' : 'pause'} size={12} color={livePaused ? colors.text : T.textSec} />
                <Text style={{ fontSize: 11, fontWeight: '700', color: livePaused ? colors.text : T.textSec }}>{livePaused ? 'Resume' : 'Pause'}</Text>
              </TouchableOpacity>
              <TouchableOpacity accessibilityLabel={tx('admin.sIEMPanel.auto.accessibility.001', 'Clear')} onPress={() => setLiveEvents([])} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec }}>{tx('admin.sIEMPanel.auto.text.007', 'Clear')}</Text>
              </TouchableOpacity>
            </View>
          </View>
          {liveEvents.length === 0 && (
            <View style={{ padding: 40, alignItems: 'center', backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border }}>
              <Ionicons name="pulse" size={32} color={T.textMuted} />
              <Text style={{ fontSize: 13, color: T.textMuted, marginTop: 8 }}>{tx('admin.sIEMPanel.auto.text.008', 'Waiting for new security events...')}</Text>
            </View>
          )}
          {liveEvents.map((e, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8, paddingHorizontal: 12, backgroundColor: i === 0 ? (globalThis as any).__alphaColor(T.primary, '10') : T.card, borderRadius: 10, marginBottom: 3, borderWidth: 1, borderColor: i === 0 ? (globalThis as any).__alphaColor(T.primary, '30') : T.border }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: RISK_COLORS[e.risk_level] || AC.textDim }} />
              <Text style={{ width: 120, fontSize: 11, color: T.text, fontWeight: '600' }}>{e.event_type}</Text>
              <Text style={{ flex: 1, fontSize: 10, color: T.textMuted }}>{e.user_id?.slice(0, 16)}</Text>
              <Text style={{ fontSize: 10, color: T.textMuted }}>{e.timestamp?.slice(11, 19)}</Text>
              <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor((RISK_COLORS[e.risk_level] || AC.textDim), '20') }}>
                <Text style={{ fontSize: 9, fontWeight: '700', color: RISK_COLORS[e.risk_level] || AC.textDim }}>{e.risk_level}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {tab === 'events' && (
        <View>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14 }}>
            <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: T.card, borderRadius: 10, paddingHorizontal: 12, borderWidth: 1, borderColor: T.border }}>
              <Ionicons name="search" size={14} color={T.textMuted} />
              <TextInput value={search} onChangeText={setSearch} placeholder={tx('admin.sIEMPanel.auto.placeholder.001', 'Search events...')} placeholderTextColor={T.textMuted}
                style={{ flex: 1, paddingVertical: 8, paddingHorizontal: 8, fontSize: 12, color: T.text }} onSubmitEditing={() => loadEvents(1)} data-testid="siem-search-input" testID="siem-search-input" />
            </View>
            {['', 'critical', 'high', 'medium', 'low'].map(r => (
              <TouchableOpacity key={r} accessibilityLabel={tx('admin.sIEMPanel.auto.accessibility.002', 'Apply')} onPress={() => setRiskFilter(r)}
                style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: riskFilter === r ? (RISK_COLORS[r] || T.primary) : T.card, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: riskFilter === r ? colors.primaryText : T.textSec }}>{r || 'All'}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TouchableOpacity onPress={() => loadEvents(1)} style={{ alignSelf: 'flex-end', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: T.primary, marginBottom: 10 }} data-testid="siem-apply-filter" testID="siem-apply-filter">
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryText }}>{tx('admin.sIEMPanel.auto.text.009', 'Apply')}</Text>
          </TouchableOpacity>
          <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 8 }}>{eventsTotal} events found</Text>
          {events.map((e, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 10, paddingHorizontal: 12, backgroundColor: T.card, borderRadius: 10, marginBottom: 4, borderWidth: 1, borderColor: T.border }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: RISK_COLORS[e.risk_level] || AC.textDim }} />
              <Text style={{ width: 130, fontSize: 11, color: T.text, fontWeight: '600' }}>{e.event_type}</Text>
              <Text style={{ flex: 1, fontSize: 10, color: T.textMuted }}>{e.user_id?.slice(0, 16)}</Text>
              <Text style={{ fontSize: 10, color: T.textMuted }}>{e.timestamp?.slice(0, 19).replace('T', ' ')}</Text>
              <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor((RISK_COLORS[e.risk_level] || AC.textDim), '20') }}>
                <Text style={{ fontSize: 9, fontWeight: '700', color: RISK_COLORS[e.risk_level] || AC.textDim }}>{e.risk_level}</Text>
              </View>
            </View>
          ))}
          {eventsTotal > 30 && (
            <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 8, marginTop: 12 }}>
              <TouchableOpacity disabled={eventsPage <= 1} accessibilityLabel={tx('admin.sIEMPanel.auto.accessibility.003', 'Prev')} onPress={() => loadEvents(eventsPage - 1)} style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ fontSize: 11, color: T.textSec }}>{tx('admin.sIEMPanel.auto.text.010', 'Prev')}</Text></TouchableOpacity>
              <Text style={{ fontSize: 11, color: T.textMuted, alignSelf: 'center' }}>Page {eventsPage}</Text>
              <TouchableOpacity accessibilityLabel={tx('admin.sIEMPanel.auto.accessibility.004', 'Next')} onPress={() => loadEvents(eventsPage + 1)} style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ fontSize: 11, color: T.textSec }}>{tx('admin.sIEMPanel.auto.text.011', 'Next')}</Text></TouchableOpacity>
            </View>
          )}
        </View>
      )}

      {tab === 'audit' && (
        <View>
          <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 8 }}>{auditTotal} audit entries (7d)</Text>
          {auditLogs.map((l, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 10, paddingHorizontal: 12, backgroundColor: T.card, borderRadius: 10, marginBottom: 4, borderWidth: 1, borderColor: T.border }}>
              <Ionicons name="document-text" size={14} color={T.textMuted} />
              <Text style={{ width: 120, fontSize: 11, color: T.text, fontWeight: '600' }}>{l.action}</Text>
              <Text style={{ flex: 1, fontSize: 10, color: T.textMuted }}>{l.user_id?.slice(0, 16)}</Text>
              <Text style={{ fontSize: 10, color: T.textMuted }}>{l.created_at?.slice(0, 19).replace('T', ' ')}</Text>
            </View>
          ))}
        </View>
      )}

      {tab === 'rules' && (
        <View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{tx('admin.sIEMPanel.auto.text.012', 'Alert Rules')}</Text>
            <TouchableOpacity onPress={evaluateNow} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.warning }} data-testid="siem-eval-now" testID="siem-eval-now">
              <Ionicons name="flash" size={12} color={colors.text} />
              <Text style={{ fontSize: 11, fontWeight: '700', color: colors.text }}>{tx('admin.sIEMPanel.auto.text.013', 'Evaluate Now')}</Text>
            </TouchableOpacity>
          </View>

          {/* New Rule Form */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 16 }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.sIEMPanel.auto.text.014', 'Create Alert Rule')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
              <TextInput value={newRuleName} onChangeText={setNewRuleName} placeholder={tx('admin.sIEMPanel.auto.placeholder.002', 'Rule name...')} placeholderTextColor={T.textMuted}
                style={{ flex: 2, minWidth: 150, paddingVertical: 6, paddingHorizontal: 10, fontSize: 12, color: T.text, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.bg }} />
              <TextInput value={newRuleEvent} onChangeText={setNewRuleEvent} placeholder={tx('admin.sIEMPanel.auto.placeholder.003', 'Event type')} placeholderTextColor={T.textMuted}
                style={{ flex: 1, minWidth: 100, paddingVertical: 6, paddingHorizontal: 10, fontSize: 12, color: T.text, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.bg }} />
              <TextInput value={newRuleThreshold} onChangeText={setNewRuleThreshold} placeholder={tx('admin.sIEMPanel.auto.placeholder.004', 'Threshold')} placeholderTextColor={T.textMuted} keyboardType="numeric"
                style={{ width: 70, paddingVertical: 6, paddingHorizontal: 10, fontSize: 12, color: T.text, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.bg }} />
              <TextInput value={newRuleWindow} onChangeText={setNewRuleWindow} placeholder={tx('admin.sIEMPanel.auto.placeholder.005', 'Window min')} placeholderTextColor={T.textMuted} keyboardType="numeric"
                style={{ width: 80, paddingVertical: 6, paddingHorizontal: 10, fontSize: 12, color: T.text, borderRadius: 8, borderWidth: 1, borderColor: T.border, backgroundColor: T.bg }} />
            </View>
            <TouchableOpacity onPress={createRule} style={{ alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: T.primary }} data-testid="siem-add-rule" testID="siem-add-rule">
              <Ionicons name="add" size={14} color={colors.primaryText} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>{tx('admin.sIEMPanel.auto.text.015', 'Add Rule')}</Text>
            </TouchableOpacity>
          </View>

          {rules.length === 0 && <Text style={{ fontSize: 12, color: T.textMuted, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.sIEMPanel.auto.text.016', 'No alert rules configured')}</Text>}
          {rules.map((r, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12, paddingHorizontal: 14, backgroundColor: T.card, borderRadius: 12, marginBottom: 6, borderWidth: 1, borderColor: T.border }}>
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: RISK_COLORS[r.severity] || AC.textDim }} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{r.name}</Text>
                <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>If {r.event_type} &ge; {r.threshold} in {r.window_minutes}min</Text>
              </View>
              <TouchableOpacity accessibilityLabel={tx('admin.sIEMPanel.auto.accessibility.005', 'trash button')} onPress={() => deleteRule(r.rule_id)} style={{ padding: 6 }}>
                <Ionicons name="trash" size={14} color={colors.error} />
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}

      {/* Triggered Alerts Tab */}
      {tab === 'alerts' && (
        <View data-testid="siem-triggered-alerts" testID="siem-triggered-alerts">
          <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 10 }}>{alertsTotal} triggered alerts</Text>
          {triggeredAlerts.length === 0 && (
            <View style={{ padding: 30, alignItems: 'center', backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border }}>
              <Ionicons name="checkmark-circle" size={32} color={colors.success} />
              <Text style={{ fontSize: 13, color: T.textMuted, marginTop: 8 }}>{tx('admin.sIEMPanel.auto.text.017', 'No active alerts')}</Text>
            </View>
          )}
          {triggeredAlerts.map((a, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12, paddingHorizontal: 14, backgroundColor: T.card, borderRadius: 12, marginBottom: 6, borderWidth: 1, borderColor: a.status === 'active' ? colors.errorSoft : T.border }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: a.status === 'active' ? colors.error : colors.success }} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{a.rule_name}</Text>
                <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>{a.event_type}: {a.actual_count}/{a.threshold} in {a.window_minutes}min</Text>
                <Text style={{ fontSize: 9, color: T.textMuted, marginTop: 1 }}>{a.triggered_at?.slice(0, 19).replace('T', ' ')}</Text>
              </View>
              <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: a.status === 'active' ? colors.errorSoft : colors.successSoft }}>
                <Text style={{ fontSize: 10, fontWeight: '700', color: a.status === 'active' ? colors.error : colors.success }}>{a.status}</Text>
              </View>
              {a.status === 'active' && (
                <TouchableOpacity accessibilityLabel={tx('admin.sIEMPanel.auto.accessibility.006', 'Resolve')} onPress={() => resolveAlert(a.alert_id)} style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, backgroundColor: colors.success }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primaryText }}>{tx('admin.sIEMPanel.auto.text.018', 'Resolve')}</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}
