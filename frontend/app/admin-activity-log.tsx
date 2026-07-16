import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, ActivityIndicator,
  StyleSheet, Platform, useWindowDimensions, TextInput,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../src/services/api';
import { useAuth } from '../src/context/AuthContext';
import { useRealtime } from '../src/context/RealtimeContext';
import AppShell from '../src/components/AppShell';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';
import { TableListSkeleton, FadeSlideIn } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';
import { alphaColorSafe, ensureGlobalAlphaColor } from '../src/utils/colorAlpha';

import { useAdminTheme } from '../src/hooks/useAdminTheme';
import { useTheme } from '../src/context/ThemeContext';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
const C = {
  purpleText: 'var(--app-info)' as any,
  bg: 'transparent', surface: 'var(--app-card-bg)', surfaceAlt: 'var(--app-card-bg)',
  border: 'rgba(255,255,255,0.08)', borderMd: 'rgba(255,255,255,0.12)',
  white: 'var(--app-text)' as any,
  gray100: 'var(--app-text-sec)' as any,
  gray300: 'var(--app-text-muted)' as any,
  gray400: 'var(--app-text-muted)' as any,
  teal: 'var(--app-primary)', indigo: 'var(--app-primary)', gold: 'var(--app-warning)', rose: 'var(--app-primary)',
  sky: 'var(--app-primary)', emerald: 'var(--app-success)', purple: 'var(--app-primary)',
};
const RISK_COLORS: Record<string, string> = { low: C.emerald, medium: C.gold, high: C.rose, critical: 'var(--app-error)' };
ensureGlobalAlphaColor();

export default function ActivityLog() {
  const { colors } = useTheme();
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { user } = useAuth();
  const { subscribeType } = useRealtime();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [filters, setFilters] = useState<{ event_types: string[]; risk_levels: string[] }>({ event_types: [], risk_levels: [] });

  // Active filters
  const [eventType, setEventType] = useState('');
  const [riskLevel, setRiskLevel] = useState('');
  const [searchUser, setSearchUser] = useState('');
  const [exporting, setExporting] = useState<string | null>(null);
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [anomalySummary, setAnomalySummary] = useState<any>(null);
  const [showAnomalies, setShowAnomalies] = useState(true);
  const [alertSettings, setAlertSettings] = useState<any>(null);
  const [showAlertSettings, setShowAlertSettings] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [alertHistory, setAlertHistory] = useState<any[]>([]);
  const [showAlertHistory, setShowAlertHistory] = useState(false);
  const [triggeringTest, setTriggeringTest] = useState(false);
  const [wsAlert, setWsAlert] = useState<any>(null);
  const wsAlertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const realtimeRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pageTitle = t('adminActivity.header.title');

  const fetchLog = useCallback(async (p = 1) => {
    setLoading(true);
    try {
      const params: any = { page: p, per_page: 50 };
      if (eventType) params.event_type = eventType;
      if (riskLevel) params.risk_level = riskLevel;
      const qs = new URLSearchParams(params).toString();
      const r = await api.get(`/admin/activity-log?${qs}`);
      setEvents(r.data.events || []);
      setTotal(r.data.total || 0);
      setPage(r.data.page || 1);
      setPages(r.data.pages || 1);
      if (r.data.filters) setFilters(r.data.filters);
    } catch (error) { handleAppRecoverableError({ scope: 'admin-activity-log.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setLoading(false); }
  }, [eventType, riskLevel]);

  const refreshAnomalyData = useCallback(() => {
    api.get('/admin/activity-log/anomalies').then(r => {
      setAnomalies(r.data.anomalies || []);
      setAnomalySummary(r.data.summary || null);
    }).catch(() => {});
    api.get('/admin/anomaly-alerts?limit=20').then(r => setAlertHistory(r.data.alerts || [])).catch(() => {});
  }, []);

  useEffect(() => {
    fetchLog(1);
    refreshAnomalyData();
    // Fetch alert settings and history
    api.get('/admin/anomaly-alerts/settings').then(r => setAlertSettings(r.data)).catch(() => {});
    return () => {
      if (wsAlertTimerRef.current) {
        clearTimeout(wsAlertTimerRef.current);
        wsAlertTimerRef.current = null;
      }
      if (realtimeRefreshTimerRef.current) {
        clearTimeout(realtimeRefreshTimerRef.current);
        realtimeRefreshTimerRef.current = null;
      }
    };
  }, [fetchLog, refreshAnomalyData]);

  useEffect(() => {
    if (!loading) return;
    const timeoutId = setTimeout(() => {
      setLoading(false);
    }, 12000);
    return () => clearTimeout(timeoutId);
  }, [loading]);

  useEffect(() => {
    return subscribeType('admin_alert', (msg: any) => {
      if (msg?.alert_type !== 'anomaly_detected') return;
      setWsAlert(msg);
      if (wsAlertTimerRef.current) clearTimeout(wsAlertTimerRef.current);
      wsAlertTimerRef.current = setTimeout(() => setWsAlert(null), 10000);
      refreshAnomalyData();
      fetchLog(page);
    });
  }, [fetchLog, page, refreshAnomalyData, subscribeType]);

  useEffect(() => {
    return subscribeType('data_change', (msg: any) => {
      const entity = String(msg?.entity || '').toLowerCase();
      if (!entity) return;
      const relevant = ['activity', 'anomaly', 'audit', 'admin_activity', 'admin_alert'];
      if (!relevant.some((token) => entity.includes(token))) return;

      if (realtimeRefreshTimerRef.current) {
        clearTimeout(realtimeRefreshTimerRef.current);
      }
      realtimeRefreshTimerRef.current = setTimeout(() => {
        refreshAnomalyData();
        fetchLog(page);
      }, 300);
    });
  }, [fetchLog, page, refreshAnomalyData, subscribeType]);

  useEffect(() => {
    return () => {
      if (wsAlertTimerRef.current) {
        clearTimeout(wsAlertTimerRef.current);
        wsAlertTimerRef.current = null;
      }
      if (realtimeRefreshTimerRef.current) {
        clearTimeout(realtimeRefreshTimerRef.current);
        realtimeRefreshTimerRef.current = null;
      }
    };
  }, []);

  const handleExport = async (format: 'csv' | 'pdf') => {
    setExporting(format);
    try {
      const token = await AsyncStorage.getItem('session_token');
      const baseUrl = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.EXPO_PUBLIC_BACKEND_URL || '');
      const params: any = {};
      if (eventType) params.event_type = eventType;
      if (riskLevel) params.risk_level = riskLevel;
      const qs = new URLSearchParams(params).toString();
      const url = `${baseUrl}/api/admin/activity-log/export/${format}?token=${token}&${qs}`;
      if (Platform.OS === 'web') {
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        iframe.src = url;
        document.body.appendChild(iframe);
        setTimeout(() => document.body.removeChild(iframe), 10000);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'admin-activity-log.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setTimeout(() => setExporting(null), 2000); }
  };

  const handlePrint = () => {
    if (Platform.OS !== 'web' || events.length === 0) return;
    const rows = events.map(e => `<tr><td>${fmt(e.timestamp)}</td><td>${fmtType(e.event_type)}</td><td>${e.risk_level}</td><td>${e.user_email || e.user_id?.slice(0,12) || '—'}</td><td>${e.ip_address || '—'}</td></tr>`).join('');
    const html = `<!DOCTYPE html><html><head><title>Activity Log</title><style>body{font-family:-apple-system,sans-serif;padding:32px;color:var(--app-text)}table{width:100%;border-collapse:collapse;margin-top:16px}th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--app-primary);font-size:12px}th{background:var(--app-primary-text);font-weight:600;text-transform:uppercase;font-size:11px;color:var(--app-primary)}h1{font-size:20px}p{color:var(--app-primary);font-size:13px}@media print{.no-print{display:none}}</style></head><body><h1>Security Activity Log</h1><p>Total: ${total} events &mdash; ${new Date().toLocaleDateString()}</p><table><thead><tr><th>Time</th><th>Event</th><th>Risk</th><th>User</th><th>IP</th></tr></thead><tbody>${rows}</tbody></table></body></html>`; // @theme-ok html-export-fixed-palette
    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:800px;height:600px;border:none;';
    document.body.appendChild(iframe);
    const iDoc = iframe.contentDocument || iframe.contentWindow?.document;
    if (iDoc) { iDoc.open(); iDoc.write(html); iDoc.close(); setTimeout(() => { iframe.contentWindow?.focus(); iframe.contentWindow?.print(); setTimeout(() => document.body.removeChild(iframe), 2000); }, 500); }
  };

  const fmt = (ts: string) => { try { const d = new Date(ts); return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }); } catch { return ts; } };
  const fmtType = (t: string) => t?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || '';

  const displayed = searchUser ? events.filter(e => (e.user_email || '').toLowerCase().includes(searchUser.toLowerCase()) || (e.user_name || '').toLowerCase().includes(searchUser.toLowerCase())) : events;
  const eventRowHeight = isDesktop ? 56 : 92;

  const getEventItemLayout = useCallback((_: ArrayLike<any> | null | undefined, index: number) => ({
    length: eventRowHeight,
    offset: eventRowHeight * index,
    index,
  }), [eventRowHeight]);

  const renderEventItem = useCallback(({ item: e, index: i }: { item: any; index: number }) => {
    if (isDesktop) {
      return (
        <View style={[s.tableRow, { backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(17,27,53,0.25)' }]} data-testid={`event-row-${i}`} testID={`event-row-${i}`}>
          <Text style={[s.td, { flex: 1.5 }]}>{fmt(e.timestamp)}</Text>
          <Text style={[s.td, { flex: 2, fontWeight: '600' }]}>{fmtType(e.event_type)}</Text>
          <View style={{ flex: 0.8, flexDirection: 'row', alignItems: 'center' }}>
            <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: alphaColorSafe((RISK_COLORS[e.risk_level] || C.gray400), '18') }}>
              <Text style={{ fontSize: 10, fontWeight: '700', color: RISK_COLORS[e.risk_level] || C.gray400, textTransform: 'uppercase' }}>{e.risk_level}</Text>
            </View>
          </View>
          <Text style={[s.td, { flex: 2 }]} numberOfLines={1}>{e.user_email || e.user_name || e.user_id?.slice(0, 16) || '—'}</Text>
          <Text style={[s.td, { flex: 1.2, fontFamily: 'monospace' }]}>{e.ip_address || '—'}</Text>
        </View>
      );
    }

    return (
      <View style={[s.mobileCard, { marginBottom: 8 }]} data-testid={`event-card-${i}`} testID={`event-card-${i}`}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.white }}>{fmtType(e.event_type)}</Text>
          <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: alphaColorSafe((RISK_COLORS[e.risk_level] || C.gray400), '18') }}>
            <Text style={{ fontSize: 9, fontWeight: '700', color: RISK_COLORS[e.risk_level] || C.gray400 }}>{e.risk_level?.toUpperCase()}</Text>
          </View>
        </View>
        <Text style={{ fontSize: 11, color: C.gray300 }}>{e.user_email || e.user_id?.slice(0, 16) || '—'}</Text>
        <Text style={{ fontSize: 10, color: C.gray400, marginTop: 2 }}>{fmt(e.timestamp)} &bull; {e.ip_address || 'no IP'}</Text>
      </View>
    );
  }, [isDesktop]);

  const saveAlertSettings = async (updates: any) => {
    setSavingSettings(true);
    try {
      const r = await api.put('/admin/anomaly-alerts/settings', updates);
      setAlertSettings(r.data);
    } catch (error) { handleAppRecoverableError({ scope: 'admin-activity-log.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setSavingSettings(false); }
  };

  const triggerAlertTest = async () => {
    setTriggeringTest(true);
    try { await api.post('/admin/anomaly-alerts/test'); } catch (error) { handleAppRecoverableError({ scope: 'admin-activity-log.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setTriggeringTest(false); }
  };

  return (
    <AdminRouteGate returnTo="/admin-activity-log">
    <AppShell>
      <View style={{ flex: 1, backgroundColor: AC.bg }}>
      <View style={{ flex: 1 }}>
        {/* Real-time Alert Toast */}
        {wsAlert && (
          <View style={s.alertToast} data-testid="realtime-alert-toast" testID="realtime-alert-toast">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
              <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="notifications" size={16} color={colors.error} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: C.white }}>{wsAlert.title}</Text>
                <Text style={{ fontSize: 11, color: C.gray300, marginTop: 1 }}>{wsAlert.message}</Text>
              </View>
              <TouchableOpacity onPress={() => setWsAlert(null)} data-testid="dismiss-alert-toast" testID="dismiss-alert-toast">
                <Ionicons name="close" size={18} color={C.gray400} />
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Header */}
        <View style={{ padding: isDesktop ? 32 : 16, paddingBottom: 0 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <View>
              <Text style={s.title} data-testid="activity-log-title" testID="activity-log-title">{pageTitle === 'adminActivity.header.title' ? 'Activity Log' : pageTitle}</Text>
              <Text style={s.subtitle}>{tx('adminActivity.header.securityEvents', '{count} security events').replace('{count}', total.toLocaleString())}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity style={[s.exportBtn, { borderColor: alphaColorSafe(C.emerald, '40'), backgroundColor: alphaColorSafe(C.emerald, '12') }]} onPress={() => handleExport('csv')} disabled={exporting !== null} data-testid="export-csv-btn" testID="export-csv-btn">
                {exporting === 'csv' ? <ActivityIndicator size="small" color={C.emerald} /> : <Ionicons name="document-outline" size={15} color={C.emerald} />}
                <Text style={[s.exportText, { color: C.emerald }]}>CSV</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.exportBtn, { borderColor: alphaColorSafe(C.rose, '40'), backgroundColor: alphaColorSafe(C.rose, '12') }]} onPress={() => handleExport('pdf')} disabled={exporting !== null} data-testid="export-pdf-btn" testID="export-pdf-btn">
                {exporting === 'pdf' ? <ActivityIndicator size="small" color={C.rose} /> : <Ionicons name="document-text-outline" size={15} color={C.rose} />}
                <Text style={[s.exportText, { color: C.rose }]}>PDF</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.exportBtn, { borderColor: alphaColorSafe(C.sky, '40'), backgroundColor: alphaColorSafe(C.sky, '12') }]} onPress={handlePrint} data-testid="print-btn" testID="print-btn">
                <Ionicons name="print-outline" size={15} color={C.sky} />
                <Text style={[s.exportText, { color: C.sky }]}>{t("paymentHistory.actions.print")}</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Filters */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 16, marginBottom: 12 }}>
            <View style={s.filterWrap}>
              <Ionicons name="funnel-outline" size={13} color={C.gray400} />
              <select style={{ background: 'transparent', border: 'none', color: C.gray300, fontSize: 12, outline: 'none', cursor: 'pointer' } as any} value={eventType} onChange={(e: any) => setEventType(e.target.value)} data-testid="filter-event-type">
                <option value="" style={{ background: C.surface }}>{tx('adminActivity.filters.allEvents', 'All Events')}</option>
                {filters.event_types.map(t => <option key={t} value={t} style={{ background: C.surface }}>{fmtType(t)}</option>)}
              </select>
            </View>
            <View style={s.filterWrap}>
              <Ionicons name="shield-outline" size={13} color={C.gray400} />
              <select style={{ background: 'transparent', border: 'none', color: C.gray300, fontSize: 12, outline: 'none', cursor: 'pointer' } as any} value={riskLevel} onChange={(e: any) => setRiskLevel(e.target.value)} data-testid="filter-risk-level">
                <option value="" style={{ background: C.surface }}>{tx('adminActivity.filters.allRisk', 'All Risk')}</option>
                {filters.risk_levels.map(r => <option key={r} value={r} style={{ background: C.surface }}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
              </select>
            </View>
            <View style={[s.filterWrap, { flex: 1, minWidth: 180 }]}>
              <Ionicons name="search-outline" size={13} color={C.gray400} />
              <TextInput
                style={{ flex: 1, color: C.gray300, fontSize: 12, outlineStyle: 'none' } as any}
                placeholder={tx('adminActivity.filters.searchByUser', 'Search by user...')}
                placeholderTextColor={C.gray400}
                value={searchUser}
                onChangeText={setSearchUser}
                data-testid="filter-user-search" testID="filter-user-search"
              />
            </View>
          </View>
        </View>

        {/* Content */}
        <View style={{ flex: 1, paddingHorizontal: isDesktop ? 32 : 16, paddingBottom: 80 }}>
          {/* Anomaly Detection Panel */}
          {anomalies.length > 0 && (
            <View style={s.anomalyPanel} data-testid="anomaly-panel" testID="anomaly-panel">
              <TouchableOpacity
                style={s.anomalyHeader}
                onPress={() => setShowAnomalies(!showAnomalies)}
                activeOpacity={0.7}
                data-testid="anomaly-toggle-btn" testID="anomaly-toggle-btn"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <View style={s.anomalyIcon}>
                    <Ionicons name="warning" size={16} color={C.rose} />
                  </View>
                  <View>
                    <Text style={{ fontSize: 14, fontWeight: '700', color: C.white }}>{tx('adminActivity.anomaly.title', 'Anomaly Detection')}</Text>
                    <Text style={{ fontSize: 11, color: C.gray400, marginTop: 1 }}>
                      {anomalySummary?.total_anomalies || anomalies.length}{t("autofix.watchSweep1.threat")}{(anomalySummary?.total_anomalies || anomalies.length) !== 1 ? 's' : ''}{t("autofix.watchSweep1.detected")}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  {anomalySummary?.critical > 0 && (
                    <View style={[s.severityPill, { backgroundColor: colors.errorSoft, borderColor: colors.errorSoft }]}>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: colors.error }}>{anomalySummary.critical} CRIT</Text>
                    </View>
                  )}
                  {anomalySummary?.high > 0 && (
                    <View style={[s.severityPill, { backgroundColor: alphaColorSafe(C.rose, '18'), borderColor: alphaColorSafe(C.rose, '40') }]}> 
                      <Text style={{ fontSize: 10, fontWeight: '700', color: C.rose }}>{anomalySummary.high} HIGH</Text>
                    </View>
                  )}
                  {anomalySummary?.medium > 0 && (
                    <View style={[s.severityPill, { backgroundColor: alphaColorSafe(C.gold, '18'), borderColor: alphaColorSafe(C.gold, '40') }]}> 
                      <Text style={{ fontSize: 10, fontWeight: '700', color: C.gold }}>{anomalySummary.medium} MED</Text>
                    </View>
                  )}
                  {anomalySummary?.low > 0 && (
                    <View style={[s.severityPill, { backgroundColor: alphaColorSafe(C.emerald, '18'), borderColor: alphaColorSafe(C.emerald, '40') }]}> 
                      <Text style={{ fontSize: 10, fontWeight: '700', color: C.emerald }}>{anomalySummary.low} LOW</Text>
                    </View>
                  )}
                  <Ionicons name={showAnomalies ? 'chevron-up' : 'chevron-down'} size={18} color={C.gray400} />
                </View>
              </TouchableOpacity>

              {showAnomalies && (
                <View style={{ padding: isDesktop ? 16 : 12, gap: 8 }} data-testid="anomaly-list" testID="anomaly-list">
                  {anomalies.map((a: any, i: number) => {
                    const sevColor = a.severity === 'critical' ? colors.error : a.severity === 'high' ? C.rose : a.severity === 'medium' ? C.gold : C.emerald;
                    const typeIcon = a.type === 'rate_limit_abuse' ? 'speedometer-outline'
                      : a.type === 'privilege_escalation' ? 'lock-closed-outline'
                      : a.type === 'multi_ip_login' ? 'globe-outline'
                      : a.type === 'brute_force' ? 'key-outline'
                      : a.type === 'unusual_hours' ? 'moon-outline'
                      : 'alert-circle-outline';
                    return (
                      <View key={`anomaly-${i}`} style={[s.anomalyCard, { borderLeftColor: sevColor }]} data-testid={`anomaly-card-${i}`} testID={`anomaly-card-${i}`}>
                        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
                          <View style={[s.anomalyTypeIcon, { backgroundColor: alphaColorSafe(sevColor, '14') }]}> 
                            <Ionicons name={typeIcon as any} size={14} color={sevColor} />
                          </View>
                          <View style={{ flex: 1 }}>
                            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                              <Text style={{ fontSize: 13, fontWeight: '700', color: C.white }} numberOfLines={1}>{a.title}</Text>
                              <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 4, backgroundColor: alphaColorSafe(sevColor, '18') }}>
                                <Text style={{ fontSize: 9, fontWeight: '800', color: sevColor, textTransform: 'uppercase', letterSpacing: 0.5 }}>{a.severity}</Text>
                              </View>
                            </View>
                            <Text style={{ fontSize: 11, color: C.gray300, marginTop: 3 }}>{a.description}</Text>
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 6 }}>
                              {a.user_email && (
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                                  <Ionicons name="person-outline" size={10} color={C.gray400} />
                                  <Text style={{ fontSize: 10, color: C.gray400 }}>{a.user_email}</Text>
                                </View>
                              )}
                              {a.count && (
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                                  <Ionicons name="repeat-outline" size={10} color={C.gray400} />
                                  <Text style={{ fontSize: 10, color: C.gray400 }}>{a.count}{t("autofix.watchSweep1.occurrences")}</Text>
                                </View>
                              )}
                              {a.last_seen && (
                                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                                  <Ionicons name="time-outline" size={10} color={C.gray400} />
                                  <Text style={{ fontSize: 10, color: C.gray400 }}>{t("autofix.watchSweep1.last")}{fmt(a.last_seen)}</Text>
                                </View>
                              )}
                            </View>
                          </View>
                        </View>
                      </View>
                    );
                  })}
                </View>
              )}
            </View>
          )}

          {/* Alert Settings & History Panel */}
          <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 12, marginBottom: 16 }}>
            {/* Alert Settings */}
            <View style={[s.settingsCard, { flex: 1 }]} data-testid="alert-settings-panel" testID="alert-settings-panel">
              <TouchableOpacity
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
                onPress={() => setShowAlertSettings(!showAlertSettings)}
                activeOpacity={0.7}
                data-testid="alert-settings-toggle" testID="alert-settings-toggle"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="notifications-outline" size={16} color={C.teal} />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.white }}>{t("anomalyDetection.views.alertSettings")}</Text>
                  {alertSettings?.enabled && (
                    <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: alphaColorSafe(C.emerald, '18') }}>
                      <Text style={{ fontSize: 9, fontWeight: '700', color: C.emerald }}>ACTIVE</Text>
                    </View>
                  )}
                </View>
                <Ionicons name={showAlertSettings ? 'chevron-up' : 'chevron-down'} size={16} color={C.gray400} />
              </TouchableOpacity>

              {showAlertSettings && alertSettings && (
                <View style={{ marginTop: 12, gap: 10 }}>
                  {/* Enable toggle */}
                  <TouchableOpacity
                    style={s.settingRow}
                    onPress={() => saveAlertSettings({ enabled: !alertSettings.enabled })}
                    disabled={savingSettings}
                    data-testid="alert-enabled-toggle" testID="alert-enabled-toggle"
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: '600', color: C.white }}>{t("autofix.watchSweep1.real.time.alerts")}</Text>
                      <Text style={{ fontSize: 10, color: C.gray400, marginTop: 1 }}>{t("autofix.watchSweep1.scan.for.anomalies.every.15.minutes")}</Text>
                    </View>
                    <View style={[s.toggle, alertSettings.enabled && s.toggleOn]}>
                      <View style={[s.toggleDot, alertSettings.enabled && s.toggleDotOn]} />
                    </View>
                  </TouchableOpacity>

                  {/* Email toggle */}
                  <TouchableOpacity
                    style={s.settingRow}
                    onPress={() => saveAlertSettings({ email_enabled: !alertSettings.email_enabled })}
                    disabled={savingSettings}
                    data-testid="alert-email-toggle" testID="alert-email-toggle"
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: '600', color: C.white }}>{t("settings.item.emailNotifications.title")}</Text>
                      <Text style={{ fontSize: 10, color: C.gray400, marginTop: 1 }}>{t("autofix.watchSweep1.send.email.when.anomalies.detected")}</Text>
                    </View>
                    <View style={[s.toggle, alertSettings.email_enabled && s.toggleOn]}>
                      <View style={[s.toggleDot, alertSettings.email_enabled && s.toggleDotOn]} />
                    </View>
                  </TouchableOpacity>

                  {/* Min severity selector */}
                  <View style={s.settingRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: '600', color: C.white }}>{t("autofix.watchSweep1.minimum.severity")}</Text>
                      <Text style={{ fontSize: 10, color: C.gray400, marginTop: 1 }}>{t("autofix.watchSweep1.only.alert.for.this.level.and.above")}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', gap: 4 }}>
                      {['critical', 'high', 'medium', 'low'].map(sev => {
                        const active = alertSettings.min_severity === sev;
                        const sevCol = sev === 'critical' ? colors.error : sev === 'high' ? C.rose : sev === 'medium' ? C.gold : C.emerald;
                        return (
                          <TouchableOpacity
                            key={sev}
                            style={[s.sevBtn, active && { backgroundColor: alphaColorSafe(sevCol, '20'), borderColor: alphaColorSafe(sevCol, '60') }]}
                            onPress={() => saveAlertSettings({ min_severity: sev })}
                            disabled={savingSettings}
                            data-testid={`alert-severity-${sev}`} testID={`alert-severity-${sev}`}
                          >
                            <Text style={{ fontSize: 9, fontWeight: '700', color: active ? sevCol : C.gray400, textTransform: 'uppercase' }}>{sev.slice(0, 4)}</Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  </View>

                  {/* Test trigger */}
                  <TouchableOpacity
                    style={[s.exportBtn, { borderColor: alphaColorSafe(C.purple, '40'), backgroundColor: alphaColorSafe(C.purple, '12'), alignSelf: 'flex-start' }]}
                    onPress={triggerAlertTest}
                    disabled={triggeringTest}
                    data-testid="trigger-alert-test-btn" testID="trigger-alert-test-btn"
                  >
                    {triggeringTest ? <ActivityIndicator size="small" color={C.purpleText} /> : <Ionicons name="flash-outline" size={14} color={C.purpleText} />}
                    <Text style={[s.exportText, { color: C.purpleText }]}>{t("autofix.watchSweep1.test.alert.now")}</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>

            {/* Alert History */}
            <View style={[s.settingsCard, { flex: 1 }]} data-testid="alert-history-panel" testID="alert-history-panel">
              <TouchableOpacity
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
                onPress={() => setShowAlertHistory(!showAlertHistory)}
                activeOpacity={0.7}
                data-testid="alert-history-toggle" testID="alert-history-toggle"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="time-outline" size={16} color={C.gold} />
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.white }}>{t("securityDashboard.alertHistory.title")}</Text>
                  {alertHistory.length > 0 && (
                    <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: alphaColorSafe(C.gold, '18') }}>
                      <Text style={{ fontSize: 9, fontWeight: '700', color: C.gold }}>{alertHistory.length}</Text>
                    </View>
                  )}
                </View>
                <Ionicons name={showAlertHistory ? 'chevron-up' : 'chevron-down'} size={16} color={C.gray400} />
              </TouchableOpacity>

              {showAlertHistory && (
                <View style={{ marginTop: 10, gap: 6 }}>
                  {alertHistory.length === 0 ? (
                    <Text style={{ fontSize: 11, color: C.gray400, textAlign: 'center', padding: 12 }}>{t("autofix.watchSweep1.no.alerts.sent.yet")}</Text>
                  ) : alertHistory.slice(0, 10).map((a: any, i: number) => {
                    const sevColor = a.severity === 'critical' ? colors.error : a.severity === 'high' ? C.rose : a.severity === 'medium' ? C.gold : C.emerald;
                    return (
                      <View key={`hist-${i}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }} data-testid={`alert-history-item-${i}`} testID={`alert-history-item-${i}`}>
                        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: sevColor }} />
                        <Text style={{ fontSize: 11, color: C.white, flex: 1 }} numberOfLines={1}>{a.anomaly?.title || a.alert_key}</Text>
                        <Text style={{ fontSize: 10, color: C.gray400 }}>{fmt(a.alerted_at)}</Text>
                      </View>
                    );
                  })}
                </View>
              )}
            </View>
          </View>

          {/* Event Table */}
          {loading ? <TableListSkeleton /> : (
            <FadeSlideIn>
              {/* Table header */}
              {isDesktop && (
                <View style={[s.tableRow, { backgroundColor: C.surfaceAlt, borderRadius: 10, marginBottom: 4 }]}>
                  <Text style={[s.th, { flex: 1.5 }]}>{t("gallery.featureDetail.export.time")}</Text>
                  <Text style={[s.th, { flex: 2 }]}>{t("gallery.featureDetail.export.event")}</Text>
                  <Text style={[s.th, { flex: 0.8 }]}>{t("autofix.watchSweep1.risk")}</Text>
                  <Text style={[s.th, { flex: 2 }]}>{t("admin.subscriptionDashboard.subscribers.table.user")}</Text>
                  <Text style={[s.th, { flex: 1.2 }]}>{t("autofix.watchSweep1.ip.address")}</Text>
                </View>
              )}

              <FlatList
                data={displayed}
                keyExtractor={(item: any, index) => String(item.event_id || `event-${index}`)}
                renderItem={renderEventItem}
                getItemLayout={getEventItemLayout}
                initialNumToRender={12}
                maxToRenderPerBatch={12}
                windowSize={7}
                removeClippedSubviews={Platform.OS !== 'web'}
                showsVerticalScrollIndicator={false}
                data-testid="activity-events-virtual-list"
                testID="activity-events-virtual-list"
                ListEmptyComponent={
                  <View style={s.emptyCard} data-testid="activity-events-empty" testID="activity-events-empty">
                    <Ionicons name="shield-outline" size={32} color={C.gray400} />
                    <Text style={{ color: C.gray400, fontSize: 14, marginTop: 8 }}>{t("autofix.watchSweep1.no.events.match.your.filters")}</Text>
                  </View>
                }
                ListFooterComponent={pages > 1 ? (
                  <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 12, marginTop: 20 }}>
                    <TouchableOpacity style={[s.pageBtn, page <= 1 && { opacity: 0.3 }]} onPress={() => { if (page > 1) fetchLog(page - 1); }} disabled={page <= 1} data-testid="prev-page-btn" testID="prev-page-btn">
                      <Ionicons name="chevron-back" size={16} color={C.white} />
                    </TouchableOpacity>
                    <Text style={{ color: C.gray300, fontSize: 13 }}>{t("autofix.watchSweep1.page")}{page} of {pages}</Text>
                    <TouchableOpacity style={[s.pageBtn, page >= pages && { opacity: 0.3 }]} onPress={() => { if (page < pages) fetchLog(page + 1); }} disabled={page >= pages} data-testid="next-page-btn" testID="next-page-btn">
                      <Ionicons name="chevron-forward" size={16} color={C.white} />
                    </TouchableOpacity>
                  </View>
                ) : <View style={{ height: 8 }} />}
              />
            </FadeSlideIn>
          )}
        </View>
      </View>
      </View>
    </AppShell>
    </AdminRouteGate>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', minHeight: 300 },
  title: { fontSize: 24, fontWeight: '800', color: C.white },
  subtitle: { fontSize: 13, color: C.gray400, marginTop: 2 },
  exportBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, borderWidth: 1 },
  exportText: { fontSize: 12, fontWeight: '600' },
  filterWrap: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.surface, borderRadius: 8, borderWidth: 1, borderColor: C.border, paddingHorizontal: 10, paddingVertical: 8 },
  tableRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: C.border },
  th: { fontSize: 10, fontWeight: '700', color: C.gray400, textTransform: 'uppercase', letterSpacing: 0.5 },
  td: { fontSize: 12, color: C.gray300 },
  mobileCard: { backgroundColor: C.surface, borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: C.border },
  emptyCard: { backgroundColor: C.surface, borderRadius: 14, padding: 40, alignItems: 'center', borderWidth: 1, borderColor: C.border },
  pageBtn: { width: 36, height: 36, borderRadius: 8, backgroundColor: C.surface, borderWidth: 1, borderColor: C.borderMd, alignItems: 'center', justifyContent: 'center' },
  anomalyPanel: { backgroundColor: C.surface, borderRadius: 14, borderWidth: 1, borderColor: alphaColorSafe(C.rose, '30'), marginBottom: 16, overflow: 'hidden' },
  anomalyHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border },
  anomalyIcon: { width: 32, height: 32, borderRadius: 8, backgroundColor: alphaColorSafe(C.rose, '14'), alignItems: 'center', justifyContent: 'center' },
  severityPill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, borderWidth: 1 },
  anomalyCard: { backgroundColor: C.surfaceAlt, borderRadius: 10, padding: 12, borderLeftWidth: 3, borderWidth: 1, borderColor: C.border },
  anomalyTypeIcon: { width: 28, height: 28, borderRadius: 7, alignItems: 'center', justifyContent: 'center', marginTop: 1 },
  alertToast: { position: 'absolute' as any, top: 0, left: 0, right: 0, zIndex: 100, backgroundColor: alphaColorSafe(C.rose, '15'), borderBottomWidth: 1, borderBottomColor: alphaColorSafe(C.rose, '15'), paddingHorizontal: 20, paddingVertical: 12 },
  settingsCard: { backgroundColor: C.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border },
  settingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border },
  toggle: { width: 36, height: 20, borderRadius: 10, backgroundColor: C.surfaceAlt, borderWidth: 1, borderColor: C.borderMd, justifyContent: 'center', paddingHorizontal: 2 },
  toggleOn: { backgroundColor: alphaColorSafe(C.teal, '30'), borderColor: alphaColorSafe(C.teal, '60') },
  toggleDot: { width: 14, height: 14, borderRadius: 7, backgroundColor: C.gray400 },
  toggleDotOn: { backgroundColor: C.teal, alignSelf: 'flex-end' as any },
  sevBtn: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, borderWidth: 1, borderColor: C.border, backgroundColor: C.surfaceAlt },
});
