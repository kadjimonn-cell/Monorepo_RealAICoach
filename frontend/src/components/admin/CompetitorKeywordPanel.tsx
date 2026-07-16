import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, useWindowDimensions, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import api from '../../services/api';
import { KeywordAlertSettings } from './KeywordAlertSettings';
import { KeywordRow } from './KeywordRow';
import { CompetitorSnapshot } from './CompetitorSnapshot';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { clientLogger } from '../../utils/clientLogger';
import { useManagedWebSocket } from '../../hooks/useManagedWebSocket';
import { handleRecoverableError } from '../../utils/handleRecoverableError';

export default function CompetitorKeywordPanel() {
  const s = useExecStyles();
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const T = useExecTheme();
  const { width } = useWindowDimensions();
  const d = width >= 1024;
  const [keywords, setKeywords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKw, setNewKw] = useState('');
  const [adding, setAdding] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedKw, setExpandedKw] = useState<string | null>(null);
  const [scheduleStatus, setScheduleStatus] = useState<any>(null);
  const [showAlertSettings, setShowAlertSettings] = useState(false);
  const [alertSettings, setAlertSettings] = useState<any>({ enabled: false, threshold: 10, alert_email: '', notify_on_improvement: true, notify_on_decline: true });
  const [savingAlerts, setSavingAlerts] = useState(false);
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
  const [wsError, setWsError] = useState('');

  const load = useCallback(async () => {
    try {
      const [kwRes, schedRes, alertRes] = await Promise.all([
        api.get('/admin/aso-unified/keywords'),
        api.get('/admin/aso-unified/keywords/schedule-status').catch(() => null),
        api.get('/admin/aso-unified/keywords/alerts/settings').catch(() => null),
      ]);
      setKeywords(kwRes.data.keywords || []);
      if (schedRes) setScheduleStatus(schedRes.data);
      if (alertRes) setAlertSettings(alertRes.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  const asoRealtimeEnabled = Platform.OS === 'web';

  const buildAsoWsUrl = useCallback(async () => {
    const ticketResp = await api.post('/auth/ws-ticket', { channel: 'aso_dashboard' });
    const wsTicket = String(ticketResp?.data?.ticket || '').trim();
    if (!wsTicket) {
      throw new Error('Missing websocket ticket for ASO dashboard');
    }

    const backendUrl = typeof window !== 'undefined' && (`https://${window.location.host}`)
      ? (`https://${window.location.host}`)
      : (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '');
    const wsProtocol = backendUrl.startsWith('https') ? 'wss' : 'ws';
    const wsHost = backendUrl.replace(/^https?:\/\//, '');
    return `${wsProtocol}://${wsHost}/api/ws/aso-dashboard?ticket=${encodeURIComponent(wsTicket)}`;
  }, []);

  const { lastError: asoWsLastError } = useManagedWebSocket({
    enabled: asoRealtimeEnabled,
    buildUrl: buildAsoWsUrl,
    errorScope: 'admin/aso-dashboard/ws',
    maxReconnectAttempts: 6,
    baseReconnectDelayMs: 1200,
    onOpen: () => {
      setWsStatus('connected');
      setWsError('');
      clientLogger.log('[ASO WS] Connected');
    },
    onClose: () => {
      setWsStatus('disconnected');
    },
    onError: () => {
      setWsStatus('disconnected');
      setWsError('ASO live stream disconnected. Reconnecting...');
    },
    onReconnectAttempt: () => {
      setWsStatus('connecting');
      setWsError('ASO live stream reconnecting...');
    },
    onMessage: (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'aso:update') {
          setKeywords(msg.keywords || []);
          if (msg.last_refresh) setScheduleStatus((prev: any) => ({ ...prev, last_refresh: msg.last_refresh }));
          setWsError('');
        }
      } catch (error) {
        handleRecoverableError(error, {
          scope: 'admin/aso-dashboard/ws-parse',
          fallbackMessage: 'A live ASO update could not be parsed.',
          setMessage: setWsError,
        });
      }
    },
  });

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!asoRealtimeEnabled) {
      setWsStatus('disconnected');
      setWsError('');
    }
  }, [asoRealtimeEnabled]);

  useEffect(() => {
    if (!asoWsLastError) return;
    setWsStatus('disconnected');
    setWsError(asoWsLastError);
  }, [asoWsLastError]);

  const addKeyword = async () => {
    if (!newKw.trim()) return;
    setAdding(true);
    try {
      await api.post('/admin/aso-unified/keywords', { keyword: newKw.trim() });
      setNewKw('');
      await load();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Error');
    } finally { setAdding(false); }
  };

  const removeKeyword = async (kw: string) => {
    try {
      await api.delete(`/admin/aso-unified/keywords/${encodeURIComponent(kw)}`);
      setKeywords(prev => prev.filter(k => k.keyword !== kw));
    } catch (e) { console.error(e); }
  };

  const refreshAll = async () => {
    setRefreshing(true);
    try {
      await api.post('/admin/aso-unified/keywords/refresh');
      await load();
    } catch (e) { console.error(e); }
    finally { setRefreshing(false); }
  };

  const saveAlertSettings = async () => {
    setSavingAlerts(true);
    try {
      const res = await api.put('/admin/aso-unified/keywords/alerts/settings', alertSettings);
      setAlertSettings(res.data);
    } catch (e) { console.error(e); }
    finally { setSavingAlerts(false); }
  };

  const handleExpandToggle = (keyword: string) => {
    setExpandedKw(expandedKw === keyword ? null : keyword);
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  return (
    <View style={s.panel} data-testid="competitor-keyword-panel" testID="competitor-keyword-panel">
      {/* Header */}
      <View style={[s.panelHeader, { marginBottom: 16 }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.purple, '20'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="search" size={18} color={T.purpleText} />
          </View>
          <View>
            <Text style={s.panelTitle}>{tx('admin.competitorKeywordPanel.header.title', 'Keyword Rankings')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.competitorKeywordPanel.header.subtitle', 'Track your ASO keyword positions vs competitors')}</Text>
          </View>
          <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(colors.success, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '40'), marginLeft: 6 }}>
            <Text style={{ color: colors.successText, fontSize: 9, fontWeight: '800', letterSpacing: 0.5 }} data-testid="live-data-badge" testID="live-data-badge">{tx('admin.competitorKeywordPanel.header.liveData', 'LIVE DATA')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
          {/* WS Status */}
          <View data-testid="aso-ws-connection-status" testID="aso-ws-connection-status" style={{ display: 'flex', alignItems: 'center', gap: 5, flexDirection: 'row', padding: '4px 10px', borderRadius: 20, backgroundColor: wsStatus === 'connected' ? 'rgba(34,197,94,0.1)' : wsStatus === 'connecting' ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)', borderWidth: 1, borderColor: wsStatus === 'connected' ? 'rgba(34,197,94,0.3)' : wsStatus === 'connecting' ? 'rgba(245,158,11,0.3)' : 'rgba(239,68,68,0.3)' } as any}>
            <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: wsStatus === 'connected' ? T.success : wsStatus === 'connecting' ? T.warning : T.error }} />
            <Text style={{ fontSize: 10, color: wsStatus === 'connected' ? T.success : wsStatus === 'connecting' ? T.warning : T.error, fontWeight: '600' }}>
              {wsStatus === 'connected' ? 'LIVE' : wsStatus === 'connecting' ? 'CONNECTING...' : 'OFFLINE'}
            </Text>
          </View>
          <TouchableOpacity onPress={refreshAll} disabled={refreshing}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(T.primary, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '30') }}
            data-testid="keyword-refresh-btn" testID="keyword-refresh-btn">
            {refreshing ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="refresh" size={14} color={T.primary} />}
            <Text style={{ color: T.primary, fontSize: 11, fontWeight: '600' }}>{refreshing ? 'Fetching...' : 'Refresh'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {!!wsError && (
        <View data-testid="aso-ws-error" testID="aso-ws-error" style={{ backgroundColor: (globalThis as any).__alphaColor(colors.error, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '32'), borderRadius: 10, padding: 8, marginBottom: 12 }}>
          <Text style={{ color: colors.error, fontSize: 11, fontWeight: '600' }}>{wsError}</Text>
        </View>
      )}

      {/* Alert Settings */}
      <KeywordAlertSettings
        alertSettings={alertSettings}
        setAlertSettings={setAlertSettings}
        showAlertSettings={showAlertSettings}
        setShowAlertSettings={setShowAlertSettings}
        saveAlertSettings={saveAlertSettings}
        savingAlerts={savingAlerts}
      />

      {/* Auto-Refresh Status Bar */}
      {scheduleStatus && (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: (globalThis as any).__alphaColor(T.primary, '08'), borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '15') }}
          data-testid="schedule-status-bar" testID="schedule-status-bar">
          <Ionicons name="timer-outline" size={14} color={T.primary} />
          <Text style={{ color: T.textSec, fontSize: 11 }}>
            Auto-refresh: <Text style={{ fontWeight: '700', color: T.primary }}>{scheduleStatus.schedule}</Text>
          </Text>
          {scheduleStatus.last_refresh?.refreshed_at && (
            <Text style={{ color: T.textMuted, fontSize: 10 }}>
              Last: {new Date(scheduleStatus.last_refresh.refreshed_at).toLocaleString()}
              {scheduleStatus.last_refresh.errors > 0 && ` (${scheduleStatus.last_refresh.errors} errors)`}
            </Text>
          )}
          <Text style={{ color: T.textMuted, fontSize: 10, marginLeft: 'auto' }}>
            {scheduleStatus.data_source}
          </Text>
        </View>
      )}

      {/* Add Keyword */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
        <TextInput
          value={newKw} onChangeText={setNewKw}
          placeholder={tx('admin.competitorKeywordPanel.inputs.keywordPlaceholder', 'Add keyword (e.g. ai coaching app)')}
          placeholderTextColor={T.textMuted}
          style={{ flex: 1, backgroundColor: T.card, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, color: T.text, fontSize: 13, borderWidth: 1, borderColor: T.border }}
          onSubmitEditing={addKeyword}
          data-testid="keyword-input" testID="keyword-input"
        />
        <TouchableOpacity onPress={addKeyword} disabled={adding || !newKw.trim()}
          style={{ paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: T.primary, opacity: adding || !newKw.trim() ? 0.5 : 1, justifyContent: 'center' }}
          data-testid="keyword-add-btn" testID="keyword-add-btn">
          {adding ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="add" size={18} color="var(--app-primary-text)" />}
        </TouchableOpacity>
      </View>

      {/* Keywords Table */}
      {keywords.length === 0 ? (
        <View style={{ padding: 32, alignItems: 'center', backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border }}>
          <Ionicons name="search-outline" size={32} color={T.textMuted} />
          <Text style={{ color: T.textSec, fontSize: 14, fontWeight: '600', marginTop: 10 }}>{tx('admin.competitorKeywordPanel.states.noKeywordsTitle', 'No keywords tracked yet')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.competitorKeywordPanel.states.noKeywordsSubtitle', 'Add keywords above to start tracking rankings across App Store & Google Play')}</Text>
        </View>
      ) : (
        <View style={{ gap: 8 }}>
          {/* Table Header */}
          <View style={{ flexDirection: 'row', paddingHorizontal: 14, paddingVertical: 8 }}>
            <Text style={{ flex: 2, color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.competitorKeywordPanel.table.keyword', 'KEYWORD')}</Text>
            <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.competitorKeywordPanel.table.appStore', 'APP STORE')}</Text>
            <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.competitorKeywordPanel.table.googlePlay', 'GOOGLE PLAY')}</Text>
            {d && <Text style={{ flex: 1, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.competitorKeywordPanel.table.difficulty', 'DIFFICULTY')}</Text>}
            {d && <Text style={{ flex: 1.5, color: T.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.competitorKeywordPanel.table.topCompetitor', 'TOP COMPETITOR')}</Text>}
            <Text style={{ width: 30 }} />
          </View>

          {keywords.map((kw, i) => (
            <KeywordRow
              key={kw.keyword || i}
              kw={kw}
              isExpanded={expandedKw === kw.keyword}
              isDesktop={d}
              onToggle={handleExpandToggle}
              onRemove={removeKeyword}
            />
          ))}
        </View>
      )}

      {/* Competitor Snapshot */}
      <CompetitorSnapshot keywords={keywords} isDesktop={d} />
    </View>
  );
}
