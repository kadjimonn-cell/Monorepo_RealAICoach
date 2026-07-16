import React, { useState, useEffect, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useExecTheme} from './ExecDashboardPanels';
import { Tab, ConfirmAction } from './session-management/types';
import TabBar from './session-management/TabBar';
import SecurityPanel from './session-management/SecurityPanel';
import SessionsTab from './session-management/SessionsTab';
import SuspiciousPanel from './session-management/SuspiciousPanel';
import GeoMapPanel from './session-management/GeoMapPanel';
import PoliciesPanel from './session-management/PoliciesPanel';
import AlertsPanel from './session-management/AlertsPanel';
import BlocklistPanel from './session-management/BlocklistPanel';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

export default function SessionManagementPanel() {
  const _colors = useAdminTheme();
  const T = useExecTheme();
  const ON_PRIMARY = T.primaryText || 'rgb(254,254,254)';
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [tab, setTab] = useState<Tab>('security');
  const [sessions, setSessions] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [suspicious, setSuspicious] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [suspLoading, setSuspLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [revoking, setRevoking] = useState('');
  const [confirmModal, setConfirmModal] = useState<ConfirmAction>(null);
  const [expandedUser, setExpandedUser] = useState<string | null>(null);
  const [policies, setPolicies] = useState<any[]>([]);
  const [polLoading, setPolLoading] = useState(true);
  const [polHistory, setPolHistory] = useState<any[]>([]);
  const [showNewPolicy, setShowNewPolicy] = useState(false);
  const [newPol, setNewPol] = useState({ name: '', rule_type: 'max_age_days', threshold: '30' });
  const [runningPolicy, setRunningPolicy] = useState('');
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [alertSettings, setAlertSettings] = useState<any>(null);
  const [alertHistory, setAlertHistory] = useState<any[]>([]);
  const [alertLoading, setAlertLoading] = useState(true);
  const [savingAlerts, setSavingAlerts] = useState(false);
  const [editAlerts, setEditAlerts] = useState<any>(null);
  const [geoData, setGeoData] = useState<any>(null);
  const [geoLoading, setGeoLoading] = useState(true);
  const [selectedMarker, setSelectedMarker] = useState<any>(null);
  const [liveFeed, setLiveFeed] = useState<any[]>([]);
  const [liveCount, setLiveCount] = useState(0);
  const [liveActive, setLiveActive] = useState(true);
  const seenSessionIds = useRef<Set<string>>(new Set());
  const [newEventIds, setNewEventIds] = useState<Set<string>>(new Set());
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [anomalySummary, setAnomalySummary] = useState<any>({ critical: 0, warning: 0, info: 0 });
  const [arRules, setArRules] = useState<any[]>([]);
  const [arLog, setArLog] = useState<any[]>([]);
  const [arLoading, setArLoading] = useState(true);
  const [arShowCreate, setArShowCreate] = useState(false);
  const [arExecuting, setArExecuting] = useState(false);
  const [arNewRule, setArNewRule] = useState({ name: '', trigger_type: 'rapid_fire_ip', action: 'block_ip', threshold: 5, cooldown_minutes: 15 });
  const [schedulerConfig, setSchedulerConfig] = useState<any>({ enabled: false, interval_minutes: 5, last_run: null });
  const [blocklist, setBlocklist] = useState<any>({ blocked: [], whitelisted: [], stats: { total_blocked: 0, auto_blocked: 0, manual_blocked: 0, whitelisted: 0 } });
  const [blLoading, setBlLoading] = useState(true);
  const [blNewIp, setBlNewIp] = useState('');
  const [blNewReason, setBlNewReason] = useState('');
  const [secOverview, setSecOverview] = useState<any>(null);
  const [secLoading, setSecLoading] = useState(true);

  // ── Primary Data (real-time via useLiveQuery) ──
  const { data: sessionsData, loading: sessLoad, refetch: refetchSessions } = useLiveQuery(
    `/admin/sessions?page=${page}&limit=15&search=${encodeURIComponent(search)}`,
    { entity: 'sessions', pollInterval: 30000, deps: [page, search] }
  );
  const { data: statsData } = useLiveQuery('/admin/sessions/stats', { entity: 'sessions', pollInterval: 30000 });

  useEffect(() => { if (sessionsData) { setSessions(sessionsData.sessions || []); setTotal(sessionsData.total || 0); setPages(sessionsData.pages || 1); } }, [sessionsData]);
  useEffect(() => { if (statsData) setStats(statsData); }, [statsData]);
  useEffect(() => { setLoading(sessLoad); }, [sessLoad]);

  const loadSuspicious = useCallback(async () => {
    try { setSuspLoading(true); const r = await api.get('/admin/sessions/suspicious'); setSuspicious(r.data); }
    catch (e) { console.error(e); } finally { setSuspLoading(false); }
  }, []);

  const loadPolicies = useCallback(async () => {
    try {
      setPolLoading(true);
      const [polR, histR] = await Promise.all([api.get('/admin/session-policies'), api.get('/admin/session-policies/history')]);
      setPolicies(polR.data.policies || []);
      setPolHistory(histR.data.history || []);
    } catch (e) { console.error(e); } finally { setPolLoading(false); }
  }, []);

  const loadAlerts = useCallback(async () => {
    try {
      setAlertLoading(true);
      const [setR, histR] = await Promise.all([api.get('/admin/session-alerts/settings'), api.get('/admin/session-alerts/history')]);
      setAlertSettings(setR.data);
      setEditAlerts(setR.data);
      setAlertHistory(histR.data.alerts || []);
    } catch (e) { console.error(e); } finally { setAlertLoading(false); }
  }, []);

  const loadGeoMap = useCallback(async () => {
    try { setGeoLoading(true); const r = await api.get('/admin/sessions/geo-summary'); setGeoData(r.data); }
    catch (e) { console.error(e); } finally { setGeoLoading(false); }
  }, []);

  const loadAutoResponse = useCallback(async () => {
    try {
      setArLoading(true);
      const [rulesR, logR, schedR] = await Promise.all([
        api.get('/admin/sessions/auto-response/rules'),
        api.get('/admin/sessions/auto-response/log'),
        api.get('/admin/sessions/auto-response/scheduler'),
      ]);
      setArRules(rulesR.data.rules || []);
      setArLog(logR.data.logs || []);
      setSchedulerConfig(schedR.data || { enabled: false, interval_minutes: 5 });
    } catch (e) { console.error(e); } finally { setArLoading(false); }
  }, []);

  const createArRule = async () => {
    if (!arNewRule.name.trim()) return;
    try {
      await api.post('/admin/sessions/auto-response/rules', arNewRule);
      setArNewRule({ name: '', trigger_type: 'rapid_fire_ip', action: 'block_ip', threshold: 5, cooldown_minutes: 15 });
      setArShowCreate(false);
      loadAutoResponse();
    } catch (e) { console.error(e); }
  };

  const toggleArRule = async (ruleId: string, enabled: boolean) => {
    try { await api.put(`/admin/sessions/auto-response/rules/${ruleId}`, { enabled }); loadAutoResponse(); }
    catch (e) { console.error(e); }
  };

  const deleteArRule = async (ruleId: string) => {
    try { await api.delete(`/admin/sessions/auto-response/rules/${ruleId}`); loadAutoResponse(); }
    catch (e) { console.error(e); }
  };

  const executeAutoResponse = async () => {
    try {
      setArExecuting(true);
      const r = await api.post('/admin/sessions/auto-response/execute');
      loadAutoResponse();
      if (r.data.executed > 0) alert(`Executed ${r.data.executed} auto-response action(s)`);
      else alert(tx('admin.sessionManagement.alerts.noMatchingAnomalies', 'No matching anomalies found for active rules'));
    } catch (e) { console.error(e); } finally { setArExecuting(false); }
  };

  const toggleScheduler = async (enabled: boolean) => {
    try {
      const r = await api.put('/admin/sessions/auto-response/scheduler', { enabled });
      setSchedulerConfig(r.data);
    } catch (e) { console.error(e); }
  };

  const loadBlocklist = useCallback(async () => {
    try { setBlLoading(true); const r = await api.get('/admin/sessions/blocked-ips'); setBlocklist(r.data); }
    catch (e) { console.error(e); } finally { setBlLoading(false); }
  }, []);

  const blockIp = async () => {
    if (!blNewIp.trim()) return;
    try { await api.post('/admin/sessions/blocked-ips', { ip: blNewIp.trim(), reason: blNewReason.trim() || 'manual' }); setBlNewIp(''); setBlNewReason(''); loadBlocklist(); }
    catch (e: any) { alert(e.response?.data?.error || 'Failed to block IP'); }
  };

  const unblockIp = async (ip: string) => {
    try { await api.delete(`/admin/sessions/blocked-ips/${ip}`); loadBlocklist(); }
    catch (e) { console.error(e); }
  };

  const whitelistIp = async (ip: string) => {
    try { await api.post(`/admin/sessions/blocked-ips/${ip}/whitelist`); loadBlocklist(); }
    catch (e) { console.error(e); }
  };

  const removeWhitelist = async (ip: string) => {
    try { await api.delete(`/admin/sessions/blocked-ips/${ip}/whitelist`); loadBlocklist(); }
    catch (e) { console.error(e); }
  };

  const loadSecOverview = useCallback(async () => {
    try { setSecLoading(true); const r = await api.get('/admin/sessions/security-overview'); setSecOverview(r.data); }
    catch (e) { console.error(e); } finally { setSecLoading(false); }
  }, []);

  const loadLiveFeed = useCallback(async () => {
    try {
      const r = await api.get('/admin/sessions/live-feed?seconds=60');
      const events = r.data.events || [];
      setLiveCount(r.data.count || 0);
      const fresh = new Set<string>();
      events.forEach((e: any) => {
        if (!seenSessionIds.current.has(e.session_id)) {
          fresh.add(e.session_id);
          seenSessionIds.current.add(e.session_id);
        }
      });
      if (fresh.size > 0) setNewEventIds(fresh);
      if (fresh.size > 0) setTimeout(() => setNewEventIds(new Set()), 4000);
      setLiveFeed(events);
    } catch (e) { console.error('Live feed error:', e); }
    try {
      const anomR = await api.get('/admin/sessions/anomalies', { params: { window_minutes: 30 } });
      setAnomalies(anomR.data.anomalies || []);
      setAnomalySummary(anomR.data.summary || { critical: 0, warning: 0, info: 0 });
    } catch (e) { console.error('Anomaly load error:', e); }
  }, []);

  // ── Tab-based lazy loading ──
  useEffect(() => { if (tab === 'suspicious' && !suspicious) loadSuspicious(); }, [tab, suspicious, loadSuspicious]);
  useEffect(() => { if (tab === 'policies') loadPolicies(); }, [tab, loadPolicies]);
  useEffect(() => { if (tab === 'alerts') loadAlerts(); }, [tab, loadAlerts]);
  useEffect(() => { if (tab === 'map') loadGeoMap(); }, [tab, loadGeoMap]);
  useEffect(() => { if (tab === 'map') loadAutoResponse(); }, [tab, loadAutoResponse]);
  useEffect(() => { if (tab === 'blocklist') loadBlocklist(); }, [tab, loadBlocklist]);
  useEffect(() => { if (tab === 'security') loadSecOverview(); }, [tab, loadSecOverview]);

  useHybridPolling({
    enabled: tab === 'map' && liveActive,
    errorScope: 'admin/session-management/live-feed-hybrid',
    onTick: loadLiveFeed,
    runOnMount: true,
    slowIntervalMs: 30000,
    fastIntervalMs: 10000,
  });

  // ── Actions ──
  const revokeSession = async (token: string) => {
    setRevoking(token);
    try { await api.delete(`/admin/sessions/${encodeURIComponent(token)}`); await refetchSessions(); }
    catch (e) { console.error(e); } finally { setRevoking(''); setConfirmModal(null); }
  };
  const revokeUserSessions = async (userId: string) => {
    setRevoking(userId);
    try { await api.delete(`/admin/sessions/user/${userId}`); await refetchSessions(); if (suspicious) loadSuspicious(); }
    catch (e) { console.error(e); } finally { setRevoking(''); setConfirmModal(null); }
  };

  return (
    <View data-testid="session-management-panel" testID="session-management-panel">
      <TabBar
        tab={tab} setTab={setTab}
        suspiciousTotal={suspicious?.total_flagged}
        activePolicies={policies.filter(p => p.enabled).length || undefined}
        totalBlocked={blocklist.stats?.total_blocked || undefined}
      />
      {tab === 'security' && <SecurityPanel secLoading={secLoading} secOverview={secOverview} loadSecOverview={loadSecOverview} setTab={setTab} />}
      {tab === 'sessions' && <SessionsTab stats={stats} sessions={sessions} loading={loading} search={search} setSearch={setSearch} page={page} setPage={setPage} pages={pages} total={total} revoking={revoking} setConfirmModal={setConfirmModal} loadSessions={refetchSessions} />}
      {tab === 'suspicious' && <SuspiciousPanel suspicious={suspicious} suspLoading={suspLoading} loadSuspicious={loadSuspicious} setSuspicious={setSuspicious} expandedUser={expandedUser} setExpandedUser={setExpandedUser} setConfirmModal={setConfirmModal} />}
      {tab === 'map' && <GeoMapPanel geoData={geoData} geoLoading={geoLoading} loadGeoMap={loadGeoMap} loadLiveFeed={loadLiveFeed} selectedMarker={selectedMarker} setSelectedMarker={setSelectedMarker} liveActive={liveActive} setLiveActive={setLiveActive} liveCount={liveCount} liveFeed={liveFeed} newEventIds={newEventIds} anomalies={anomalies} anomalySummary={anomalySummary} arRules={arRules} arLog={arLog} arLoading={arLoading} arShowCreate={arShowCreate} setArShowCreate={setArShowCreate} arNewRule={arNewRule} setArNewRule={setArNewRule} arExecuting={arExecuting} executeAutoResponse={executeAutoResponse} createArRule={createArRule} toggleArRule={toggleArRule} deleteArRule={deleteArRule} schedulerConfig={schedulerConfig} toggleScheduler={toggleScheduler} setGeoData={setGeoData} />}
      {tab === 'policies' && <PoliciesPanel polLoading={polLoading} policies={policies} polHistory={polHistory} showNewPolicy={showNewPolicy} setShowNewPolicy={setShowNewPolicy} newPol={newPol} setNewPol={setNewPol} runningPolicy={runningPolicy} setRunningPolicy={setRunningPolicy} loadPolicies={loadPolicies} />}
      {tab === 'alerts' && <AlertsPanel alertLoading={alertLoading} editAlerts={editAlerts} setEditAlerts={setEditAlerts} alertHistory={alertHistory} savingAlerts={savingAlerts} setSavingAlerts={setSavingAlerts} loadAlerts={loadAlerts} />}
      {tab === 'blocklist' && <BlocklistPanel blLoading={blLoading} blocklist={blocklist} blNewIp={blNewIp} setBlNewIp={setBlNewIp} blNewReason={blNewReason} setBlNewReason={setBlNewReason} blockIp={blockIp} unblockIp={unblockIp} whitelistIp={whitelistIp} removeWhitelist={removeWhitelist} />}

      {/* Confirm Modal */}
      <Modal visible={!!confirmModal} transparent animationType="fade" onRequestClose={() => setConfirmModal(null)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center' }}>
          <View style={{ backgroundColor: T.card, borderRadius: 16, padding: 24, maxWidth: 400, width: '90%', borderWidth: 1, borderColor: T.border }} data-testid="session-confirm-modal" testID="session-confirm-modal">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: T.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="warning" size={22} color={T.error} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>
                  {confirmModal?.type === 'user' ? 'Revoke All Sessions' : 'Revoke Session'}
                </Text>
                <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.sessionManagement.modal.warning', 'This cannot be undone')}</Text>
              </View>
            </View>
            <Text style={{ color: T.textSec, fontSize: 12, marginBottom: 20, lineHeight: 18 }}>
              {confirmModal?.type === 'user'
                ? `This will terminate ALL active sessions for ${confirmModal?.label}. The user will be logged out from all devices.`
                : `This will terminate the session for ${confirmModal?.label}. They will need to log in again.`}
            </Text>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => setConfirmModal(null)}
                style={{ flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: T.bgSoft, alignItems: 'center' }} data-testid="session-confirm-cancel" testID="session-confirm-cancel">
                <Text style={{ color: T.textSec, fontWeight: '600', fontSize: 13 }}>{tx('admin.sessionManagement.actions.cancel', 'Cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => { if (confirmModal?.type === 'user') revokeUserSessions(confirmModal.target); else if (confirmModal?.type === 'single') revokeSession(confirmModal.target); }}
                style={{ flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: T.error, alignItems: 'center' }} data-testid="session-confirm-revoke" testID="session-confirm-revoke">
                <Text style={{ color: ON_PRIMARY, fontWeight: '700', fontSize: 13 }}>{revoking ? 'Revoking...' : 'Revoke'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}
