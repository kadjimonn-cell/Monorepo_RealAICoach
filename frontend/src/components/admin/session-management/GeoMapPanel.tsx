import { useTranslation } from '../../../hooks/useTranslation';
import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from '../ExecDashboardPanels';

interface GeoMapPanelProps {
  geoData: any;
  geoLoading: boolean;
  loadGeoMap: () => void;
  loadLiveFeed: () => void;
  selectedMarker: any;
  setSelectedMarker: (m: any) => void;
  liveActive: boolean;
  setLiveActive: (b: boolean) => void;
  liveCount: number;
  liveFeed: any[];
  newEventIds: Set<string>;
  anomalies: any[];
  anomalySummary: any;
  arRules: any[];
  arLog: any[];
  arLoading: boolean;
  arShowCreate: boolean;
  setArShowCreate: (b: boolean) => void;
  arNewRule: any;
  setArNewRule: (fn: (p: any) => any) => void;
  arExecuting: boolean;
  executeAutoResponse: () => void;
  createArRule: () => void;
  toggleArRule: (id: string, enabled: boolean) => void;
  deleteArRule: (id: string) => void;
  schedulerConfig: any;
  toggleScheduler: (enabled: boolean) => void;
  setGeoData: (d: any) => void;
}

export default function GeoMapPanel({
  geoData, geoLoading, loadGeoMap, loadLiveFeed,
  selectedMarker, setSelectedMarker,
  liveActive, setLiveActive, liveCount, liveFeed, newEventIds,
  anomalies, anomalySummary,
  arRules, arLog, arLoading, arShowCreate, setArShowCreate,
  arNewRule, setArNewRule, arExecuting,
  executeAutoResponse, createArRule, toggleArRule, deleteArRule,
  schedulerConfig, toggleScheduler, setGeoData,
}: GeoMapPanelProps) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const T = useExecTheme();
  if (geoLoading) return <ActivityIndicator size="small" color={T.primary} style={{ paddingVertical: 30 }} />;

  const markers = geoData?.markers || [];
  const totalSessions = geoData?.total_sessions || 0;
  const geolocated = geoData?.geolocated || 0;
  const uniqueLocs = geoData?.unique_locations || 0;
  const maxCount = Math.max(...markers.map((m: any) => m.session_count), 1);

  const W = 1000, H = 500;
  const toX = (lon: number) => ((lon + 180) / 360) * W;
  const toY = (lat: number) => ((90 - lat) / 180) * H;
  const dotColor = (count: number) => {
    if (count > maxCount * 0.6) return T.error;
    if (count > maxCount * 0.3) return T.warning;
    return T.cyan;
  };
  const dotSize = (count: number) => Math.max(5, Math.min(18, 5 + (count / maxCount) * 13));

  return (
    <View data-testid="geo-map-panel" testID="geo-map-panel">
      <View style={s.panel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="globe" size={18} color={T.cyan} />
            <Text style={s.chartTitle}>{tx('admin.geoMapPanel.auto.text.001', 'Session Geolocation Map')}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <TouchableOpacity onPress={() => setLiveActive(!liveActive)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: liveActive ? 'var(--app-success-soft)' : T.bgSoft, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: liveActive ? (globalThis as any).__alphaColor(T.success, '30') : T.border }}
              data-testid="geo-live-toggle" testID="geo-live-toggle">
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: liveActive ? T.success : T.textMuted }}>
                {liveActive && <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: T.success, opacity: 0.5 }} />}
              </View>
              <Text style={{ color: liveActive ? T.success : T.textMuted, fontSize: 11, fontWeight: '700' }}>
                {liveActive ? 'LIVE' : 'PAUSED'}
              </Text>
              {liveActive && liveCount > 0 && (
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.success, '25'), borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1 }}>
                  <Text style={{ color: T.successText, fontSize: 9, fontWeight: '800' }}>{liveCount} in 60s</Text>
                </View>
              )}
            </TouchableOpacity>
            <TouchableOpacity onPress={() => { setGeoData(null); loadGeoMap(); loadLiveFeed(); }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="geo-map-refresh-btn" testID="geo-map-refresh-btn">
              <Ionicons name="refresh" size={14} color={T.primary} />
              <Text style={{ color: T.primary, fontSize: 11, fontWeight: '600' }}>{tx('admin.geoMapPanel.auto.text.002', 'Refresh')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={s.metricsRow}>
          <View style={s.metricBox} data-testid="geo-total-sessions" testID="geo-total-sessions">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Ionicons name="key" size={14} color={T.primary} />
              <Text style={s.metricLabel}>{tx('admin.geoMapPanel.auto.text.003', 'Total Sessions')}</Text>
            </View>
            <Text style={s.metricValue}>{totalSessions}</Text>
          </View>
          <View style={s.metricBox} data-testid="geo-located-count" testID="geo-located-count">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Ionicons name="location" size={14} color={T.cyan} />
              <Text style={s.metricLabel}>{tx('admin.geoMapPanel.auto.text.004', 'Geolocated')}</Text>
            </View>
            <Text style={s.metricValue}>{geolocated}</Text>
          </View>
          <View style={s.metricBox} data-testid="geo-unique-locations" testID="geo-unique-locations">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Ionicons name="pin" size={14} color={T.successText} />
              <Text style={s.metricLabel}>{tx('admin.geoMapPanel.auto.text.005', 'Unique Locations')}</Text>
            </View>
            <Text style={s.metricValue}>{uniqueLocs}</Text>
          </View>
          <View style={s.metricBox} data-testid="geo-private-count" testID="geo-private-count">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Ionicons name="eye-off" size={14} color={T.textMuted} />
              <Text style={s.metricLabel}>{tx('admin.geoMapPanel.auto.text.006', 'Private/Local IPs')}</Text>
            </View>
            <Text style={s.metricValue}>{totalSessions - geolocated}</Text>
          </View>
        </View>
      </View>

      {/* Anomaly Alert Bar */}
      {anomalies.length > 0 && (
        <View style={[s.panel, { borderWidth: 1, borderColor: anomalySummary.critical > 0 ? (globalThis as any).__alphaColor(T.error, '40') : T.warning + '40', paddingVertical: 10 }]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="shield" size={16} color={anomalySummary.critical > 0 ? T.error : T.warning} />
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.geoMapPanel.auto.text.007', 'Anomaly Detection')}</Text>
              <View style={{ backgroundColor: anomalySummary.critical > 0 ? (globalThis as any).__alphaColor(T.error, '20') : T.warning + '20', borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1 }}>
                <Text style={{ color: anomalySummary.critical > 0 ? T.error : T.warning, fontSize: 9, fontWeight: '800' }}>
                  {anomalies.length} alert{anomalies.length !== 1 ? 's' : ''}
                </Text>
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {anomalySummary.critical > 0 && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(T.error, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: T.error }} />
                  <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{anomalySummary.critical} Critical</Text>
                </View>
              )}
              {anomalySummary.warning > 0 && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(T.warning, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: T.warning }} />
                  <Text style={{ color: T.warningText, fontSize: 10, fontWeight: '700' }}>{anomalySummary.warning} Warning</Text>
                </View>
              )}
              {anomalySummary.info > 0 && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(T.primary, '15'), borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: T.primary }} />
                  <Text style={{ color: T.primary, fontSize: 10, fontWeight: '700' }}>{anomalySummary.info} Info</Text>
                </View>
              )}
            </View>
          </View>
          {anomalies.map((a: any, i: number) => {
            const sevColors: any = { critical: T.error, warning: T.warning, info: T.primary };
            const sevIcons: any = { critical: 'alert-circle', warning: 'warning', info: 'information-circle' };
            const col = sevColors[a.severity] || T.textMuted;
            return (
              <View key={i} style={{
                flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 8,
                borderRadius: 8, marginBottom: 2, backgroundColor: (globalThis as any).__alphaColor(col, '08'),
                borderLeftWidth: 3, borderLeftColor: col,
              }}>
                <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(col, '18'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={sevIcons[a.severity] || 'alert-circle'} size={14} color={col} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{a.title}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 9 }}>{a.description}</Text>
                </View>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(col, '18'), borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                  <Text style={{ color: col, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }}>{a.severity}</Text>
                </View>
              </View>
            );
          })}
        </View>
      )}

      {/* Auto-Response Rules */}
      <View style={[s.panel, { borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '25') }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="flash" size={16} color={T.purpleText} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.geoMapPanel.auto.text.008', 'Auto-Response Rules')}</Text>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.purple, '20'), borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1 }}>
              <Text style={{ color: T.purpleText, fontSize: 9, fontWeight: '800' }}>
                {arRules.filter(r => r.enabled).length} active
              </Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={executeAutoResponse} disabled={arExecuting || arRules.filter(r => r.enabled).length === 0}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(arExecuting ? T.bgSoft : T.error, '15'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5, opacity: arExecuting || arRules.filter(r => r.enabled).length === 0 ? 0.5 : 1 }}
              data-testid="ar-execute-btn" testID="ar-execute-btn">
              <Ionicons name="play" size={12} color={T.error} />
              <Text style={{ color: T.error, fontSize: 10, fontWeight: '700' }}>{arExecuting ? 'Running...' : 'Run Now'}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setArShowCreate(!arShowCreate)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(T.primary, '15'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }}
              data-testid="ar-add-rule-btn" testID="ar-add-rule-btn">
              <Ionicons name={arShowCreate ? 'close' : 'add'} size={12} color={T.primary} />
              <Text style={{ color: T.primary, fontSize: 10, fontWeight: '700' }}>{arShowCreate ? 'Cancel' : 'Add Rule'}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => toggleScheduler(!schedulerConfig.enabled)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: schedulerConfig.enabled ? (globalThis as any).__alphaColor(T.success, '12') : T.bgSoft, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: schedulerConfig.enabled ? (globalThis as any).__alphaColor(T.success, '30') : T.border }}
              data-testid="ar-scheduler-toggle" testID="ar-scheduler-toggle">
              <Ionicons name="timer" size={12} color={schedulerConfig.enabled ? T.success : T.textMuted} />
              <Text style={{ color: schedulerConfig.enabled ? T.success : T.textMuted, fontSize: 10, fontWeight: '700' }}>
                {schedulerConfig.enabled ? 'Scheduled' : 'Manual'}
              </Text>
              {schedulerConfig.enabled && (
                <Text style={{ color: T.successText, fontSize: 8, fontWeight: '600' }}>every {schedulerConfig.interval_minutes || 5}min</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>

        {arShowCreate && (
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 10, padding: 12, marginBottom: 10, gap: 8 }}>
            <TextInput value={arNewRule.name} onChangeText={(t: string) => setArNewRule((p: any) => ({ ...p, name: t }))}
              placeholder={tx('admin.geoMapPanel.auto.placeholder.001', 'Rule name (e.g. Block rapid-fire IPs)')} placeholderTextColor={T.textMuted}
              style={{ color: T.text, backgroundColor: T.bg, borderRadius: 8, padding: 10, fontSize: 12, borderWidth: 1, borderColor: T.border }}
              data-testid="ar-rule-name-input" testID="ar-rule-name-input" />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.textSec, fontSize: 9, fontWeight: '700', marginBottom: 4 }}>{tx('admin.geoMapPanel.auto.text.009', 'TRIGGER')}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                  {[{ k: 'rapid_fire_ip', l: 'Rapid-Fire IP' }, { k: 'session_flood', l: 'Session Flood' }, { k: 'ip_hopping', l: 'IP Hopping' }].map(t => (
                    <TouchableOpacity key={t.k} accessibilityLabel={tx('admin.geoMapPanel.auto.accessibility.001', 't.l')} onPress={() => setArNewRule((p: any) => ({ ...p, trigger_type: t.k }))}
                      style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: arNewRule.trigger_type === t.k ? (globalThis as any).__alphaColor(T.primary, '25') : T.bgSoft, borderWidth: 1, borderColor: arNewRule.trigger_type === t.k ? T.primary : T.border }}>
                      <Text style={{ color: arNewRule.trigger_type === t.k ? T.primary : T.textMuted, fontSize: 10, fontWeight: '600' }}>{t.l}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.textSec, fontSize: 9, fontWeight: '700', marginBottom: 4 }}>{tx('admin.geoMapPanel.auto.text.010', 'ACTION')}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                  {[{ k: 'block_ip', l: 'Block IP', i: 'ban' }, { k: 'revoke_sessions', l: 'Revoke Sessions', i: 'close-circle' }, { k: 'lock_account', l: 'Lock Account', i: 'lock-closed' }, { k: 'notify_admin', l: 'Notify Admin', i: 'mail' }].map(a => (
                    <TouchableOpacity key={a.k} accessibilityLabel={tx('admin.geoMapPanel.auto.accessibility.002', 'a.l')} onPress={() => setArNewRule((p: any) => ({ ...p, action: a.k }))}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: arNewRule.action === a.k ? (globalThis as any).__alphaColor(T.error, '15') : T.bgSoft, borderWidth: 1, borderColor: arNewRule.action === a.k ? T.error : T.border }}>
                      <Ionicons name={a.i as any} size={10} color={arNewRule.action === a.k ? T.error : T.textMuted} />
                      <Text style={{ color: arNewRule.action === a.k ? T.error : T.textMuted, fontSize: 10, fontWeight: '600' }}>{a.l}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.textSec, fontSize: 9, fontWeight: '700', marginBottom: 4 }}>{tx('admin.geoMapPanel.auto.text.011', 'THRESHOLD')}</Text>
                <TextInput value={String(arNewRule.threshold)} accessibilityLabel={tx('admin.geoMapPanel.auto.accessibility.003', 'COOLDOWN (min)')} onChangeText={(t: string) => setArNewRule((p: any) => ({ ...p, threshold: parseInt(t) || 1 }))}
                  keyboardType="numeric" style={{ color: T.text, backgroundColor: T.bg, borderRadius: 8, padding: 8, fontSize: 12, borderWidth: 1, borderColor: T.border, textAlign: 'center' }} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.textSec, fontSize: 9, fontWeight: '700', marginBottom: 4 }}>{tx('admin.geoMapPanel.auto.text.012', 'COOLDOWN (min)')}</Text>
                <TextInput value={String(arNewRule.cooldown_minutes)} accessibilityLabel={tx('admin.geoMapPanel.auto.accessibility.004', 'Create Rule')} onChangeText={(t: string) => setArNewRule((p: any) => ({ ...p, cooldown_minutes: parseInt(t) || 1 }))}
                  keyboardType="numeric" style={{ color: T.text, backgroundColor: T.bg, borderRadius: 8, padding: 8, fontSize: 12, borderWidth: 1, borderColor: T.border, textAlign: 'center' }} />
              </View>
              <TouchableOpacity onPress={createArRule} disabled={!arNewRule.name.trim()}
                style={{ flex: 1, backgroundColor: T.primary, borderRadius: 8, alignItems: 'center', justifyContent: 'center', opacity: arNewRule.name.trim() ? 1 : 0.4 }}
                data-testid="ar-create-rule-submit" testID="ar-create-rule-submit">
                <Text style={{ color: T.primaryText || 'var(--app-primary)', fontSize: 12, fontWeight: '700' }}>{tx('admin.geoMapPanel.auto.text.013', 'Create Rule')}</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {arLoading ? <ActivityIndicator size="small" color={T.primary} /> : arRules.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: 12 }}>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.geoMapPanel.auto.text.014', 'No auto-response rules configured yet')}</Text>
          </View>
        ) : arRules.map((rule: any) => {
          const actionIcons: any = { block_ip: 'ban', revoke_sessions: 'close-circle', lock_account: 'lock-closed', notify_admin: 'mail' };
          const actionColors: any = { block_ip: T.error, revoke_sessions: T.warning, lock_account: T.error, notify_admin: T.primary };
          const triggerLabels: any = { rapid_fire_ip: 'Rapid-Fire IP', session_flood: 'Session Flood', ip_hopping: 'IP Hopping' };
          const actionLabels: any = { block_ip: 'Block IP', revoke_sessions: 'Revoke Sessions', lock_account: 'Lock Account', notify_admin: 'Notify Admin' };
          return (
            <View key={rule.rule_id} style={{
              flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 8,
              borderRadius: 8, marginBottom: 4, backgroundColor: rule.enabled ? T.bgSoft : 'transparent',
              borderWidth: 1, borderColor: rule.enabled ? (globalThis as any).__alphaColor(T.purple, '20') : T.border,
            }}>
              <TouchableOpacity onPress={() => toggleArRule(rule.rule_id, !rule.enabled)}
                style={{ width: 36, height: 20, borderRadius: 10, backgroundColor: rule.enabled ? T.success : T.bgSoft, justifyContent: 'center', paddingHorizontal: 2 }}
                data-testid={`ar-toggle-${rule.rule_id}`} testID={`ar-toggle-${rule.rule_id}`}>
                <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: T.primaryText || 'var(--app-primary)', alignSelf: rule.enabled ? 'flex-end' : 'flex-start' }} />
              </TouchableOpacity>
              <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor((actionColors[rule.action] || T.primary), '18'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={actionIcons[rule.action] || 'flash'} size={14} color={actionColors[rule.action] || T.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{rule.name}</Text>
                <Text style={{ color: T.textMuted, fontSize: 9 }}>
                  {triggerLabels[rule.trigger_type] || rule.trigger_type} | {actionLabels[rule.action] || rule.action} | Threshold: {rule.threshold} | Cooldown: {rule.cooldown_minutes}min
                </Text>
              </View>
              {rule.trigger_count > 0 && (
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.warning, '20'), borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                  <Text style={{ color: T.warningText, fontSize: 9, fontWeight: '800' }}>{rule.trigger_count}x fired</Text>
                </View>
              )}
              <TouchableOpacity onPress={() => deleteArRule(rule.rule_id)} data-testid={`ar-delete-${rule.rule_id}`} testID={`ar-delete-${rule.rule_id}`}>
                <Ionicons name="trash" size={14} color={T.error + '80'} />
              </TouchableOpacity>
            </View>
          );
        })}

        {arLog.length > 0 && (
          <View style={{ marginTop: 10, borderTopWidth: 1, borderTopColor: T.border, paddingTop: 10 }}>
            <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 6 }}>RECENT ACTIONS ({arLog.length})</Text>
            {arLog.slice(0, 5).map((log: any, i: number) => (
              <View key={log.log_id || i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 }}>
                <Ionicons name={log.result?.success ? 'checkmark-circle' : 'close-circle'} size={12} color={log.result?.success ? T.success : T.error} />
                <Text style={{ color: T.text, fontSize: 10, flex: 1 }}>
                  {log.rule_name}: {log.result?.detail || log.action}
                </Text>
                <Text style={{ color: T.textMuted, fontSize: 9 }}>
                  {new Date(log.executed_at).toLocaleTimeString()}
                </Text>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* Map */}
      <View style={[s.panel, { padding: 0, overflow: 'hidden' }]}>
        <View style={{ backgroundColor: T.bgSoft, borderRadius: 14, overflow: 'hidden' }}>
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
            {[-60, -30, 0, 30, 60].map(lat => (
              <line key={`lat${lat}`} x1={0} y1={toY(lat)} x2={W} y2={toY(lat)} stroke={T.border} strokeWidth="0.5" strokeDasharray="4,4" />
            ))}
            {[-120, -60, 0, 60, 120].map(lon => (
              <line key={`lon${lon}`} x1={toX(lon)} y1={0} x2={toX(lon)} y2={H} stroke={T.border} strokeWidth="0.5" strokeDasharray="4,4" />
            ))}
            <line x1={0} y1={toY(0)} x2={W} y2={toY(0)} stroke={T.textMuted + '30'} strokeWidth="1" />
            <line x1={toX(0)} y1={0} x2={toX(0)} y2={H} stroke={T.textMuted + '30'} strokeWidth="1" />
            {[
              { x: 80, y: 70, w: 200, h: 150, label: 'NA' },
              { x: 190, y: 250, w: 110, h: 180, label: 'SA' },
              { x: 430, y: 60, w: 130, h: 120, label: 'EU' },
              { x: 430, y: 180, w: 130, h: 200, label: 'AF' },
              { x: 560, y: 50, w: 280, h: 200, label: 'AS' },
              { x: 720, y: 300, w: 150, h: 100, label: 'OC' },
            ].map(c => (
              <g key={c.label}>
                <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={8} fill={T.bgSoft + '60'} stroke={T.border} strokeWidth="0.5" />
                <text x={c.x + c.w / 2} y={c.y + c.h / 2} textAnchor="middle" dominantBaseline="middle"
                  fill={T.textMuted + '40'} fontSize="16" fontWeight="700" fontFamily="system-ui">{c.label}</text>
              </g>
            ))}
            {markers.map((m: any, i: number) => {
              const cx = toX(m.lon);
              const cy = toY(m.lat);
              const r = dotSize(m.session_count);
              const color = dotColor(m.session_count);
              const isSelected = selectedMarker?.lat === m.lat && selectedMarker?.lon === m.lon;
              return (
                <g key={i} onClick={() => setSelectedMarker(isSelected ? null : m)} style={{ cursor: 'pointer' }}>
                  {m.session_count > maxCount * 0.3 && (
                    <circle cx={cx} cy={cy} r={r + 6} fill="none" stroke={color} strokeWidth="1.5" opacity="0.3">
                      <animate attributeName="r" from={String(r + 2)} to={String(r + 12)} dur="2s" repeatCount="indefinite" />
                      <animate attributeName="opacity" from="0.4" to="0" dur="2s" repeatCount="indefinite" />
                    </circle>
                  )}
                  {isSelected && <circle cx={cx} cy={cy} r={r + 4} fill="none" stroke="var(--app-primary-text)" strokeWidth="2" />}
                  <circle cx={cx} cy={cy} r={r} fill={color} fillOpacity="0.85" stroke={color} strokeWidth="1.5" />
                  {r > 8 && (
                    <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle"
                      fill="var(--app-primary-text)" fontSize="8" fontWeight="800" fontFamily="system-ui">{m.session_count}</text>
                  )}
                </g>
              );
            })}
            {markers.length === 0 && (
              <text x={W / 2} y={H / 2} textAnchor="middle" dominantBaseline="middle"
                fill={T.textMuted} fontSize="16" fontFamily="system-ui">
                No geolocated sessions — private/local IPs cannot be mapped
              </text>
            )}
          </svg>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 20, paddingVertical: 12, paddingHorizontal: 16 }}>
          {[
            { color: T.cyan, label: 'Low traffic' },
            { color: T.warningText, label: 'Medium traffic' },
            { color: T.error, label: 'High traffic' },
          ].map(l => (
            <View key={l.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: l.color }} />
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{l.label}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Selected marker detail */}
      {selectedMarker && (
        <View style={[s.panel, { borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.cyan, '40') }]} data-testid="geo-marker-detail" testID="geo-marker-detail">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: T.cyanSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="location" size={18} color={T.cyan} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>
                {selectedMarker.city}{selectedMarker.city && selectedMarker.country ? ', ' : ''}{selectedMarker.country}
              </Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>
                {selectedMarker.country_code} | {selectedMarker.session_count} sessions | {selectedMarker.user_count} users | ISP: {selectedMarker.isp || 'Unknown'}
              </Text>
            </View>
            <TouchableOpacity onPress={() => setSelectedMarker(null)} data-testid="geo-close-detail" testID="geo-close-detail">
              <Ionicons name="close" size={18} color={T.textMuted} />
            </TouchableOpacity>
          </View>
          <View style={{ gap: 4 }}>
            <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginBottom: 2 }}>{tx('admin.geoMapPanel.auto.text.015', 'USERS AT THIS LOCATION')}</Text>
            {selectedMarker.users?.map((u: any, ui: number) => (
              <View key={ui} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: T.bgSoft, borderRadius: 6, padding: 8 }}>
                <Ionicons name="person" size={12} color={T.primary} />
                <Text style={{ color: T.text, fontSize: 11 }}>{u.email}</Text>
              </View>
            ))}
            {selectedMarker.ips?.length > 0 && (
              <>
                <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', marginTop: 8, marginBottom: 2 }}>{tx('admin.geoMapPanel.auto.text.016', 'IP ADDRESSES')}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
                  {selectedMarker.ips.map((ip: string, ipi: number) => (
                    <View key={ipi} style={{ backgroundColor: T.bgSoft, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 }}>
                      <Text style={{ color: T.textSec, fontSize: 10, fontFamily: 'monospace' }}>{ip}</Text>
                    </View>
                  ))}
                </View>
              </>
            )}
          </View>
        </View>
      )}

      {/* Location list */}
      {markers.length > 0 && (
        <View style={s.panel}>
          <Text style={[s.chartTitle, { marginBottom: 12 }]}>Session Locations ({markers.length})</Text>
          {markers.slice(0, 15).map((m: any, i: number) => {
            const pct = Math.round((m.session_count / maxCount) * 100);
            return (
              <TouchableOpacity key={i} onPress={() => setSelectedMarker(m)}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}
                data-testid={`geo-location-${i}`} testID={`geo-location-${i}`}
              >
                <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(dotColor(m.session_count), '20'), alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ color: dotColor(m.session_count), fontSize: 10, fontWeight: '800' }}>{m.session_count}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>
                    {m.city || 'Unknown'}{m.city && m.country_code ? ', ' : ''}{m.country_code || ''}
                  </Text>
                  <Text style={{ color: T.textMuted, fontSize: 10 }}>{m.user_count} user(s) | {m.isp || 'Unknown ISP'}</Text>
                </View>
                <View style={{ flex: 1.5, height: 8, backgroundColor: T.bgSoft, borderRadius: 4, overflow: 'hidden' }}>
                  <View style={{ width: `${pct}%`, height: '100%', backgroundColor: dotColor(m.session_count), borderRadius: 4 }} />
                </View>
                <Ionicons name="chevron-forward" size={14} color={T.textMuted} />
              </TouchableOpacity>
            );
          })}
        </View>
      )}

      {/* Live Feed Ticker */}
      <View style={[s.panel, { borderWidth: 1, borderColor: liveActive ? (globalThis as any).__alphaColor(T.success, '25') : T.border }]} data-testid="live-feed-panel" testID="live-feed-panel">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: liveActive ? T.success : T.textMuted }} />
            <Text style={[s.chartTitle, { fontSize: 13 }]}>{tx('admin.geoMapPanel.auto.text.017', 'Live Session Feed')}</Text>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.primary, '20'), borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1 }}>
              <Text style={{ color: T.primary, fontSize: 9, fontWeight: '800' }}>{tx('admin.geoMapPanel.auto.text.018', '10s refresh')}</Text>
            </View>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 10 }}>{liveFeed.length} event{liveFeed.length !== 1 ? 's' : ''} in last 60s</Text>
        </View>
        {liveFeed.length === 0 ? (
          <View style={{ alignItems: 'center', paddingVertical: 16 }}>
            <Ionicons name="radio-outline" size={24} color={T.textMuted} />
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>{tx('admin.geoMapPanel.auto.text.019', 'Waiting for new sessions...')}</Text>
          </View>
        ) : (
          <ScrollView style={{ maxHeight: 200 }} data-testid="live-feed-scroll" testID="live-feed-scroll">
            {liveFeed.map((ev: any, i: number) => {
              const isNew = newEventIds.has(ev.session_id);
              const ago = Math.max(0, Math.round((Date.now() - new Date(ev.created_at).getTime()) / 1000));
              const agoStr = ago < 60 ? `${ago}s ago` : `${Math.round(ago / 60)}m ago`;
              return (
                <View key={ev.session_id || i}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 8,
                    borderRadius: 8, marginBottom: 4,
                    backgroundColor: isNew ? (globalThis as any).__alphaColor(T.success, '12') : 'transparent',
                    borderLeftWidth: 3, borderLeftColor: isNew ? T.success : T.border,
                  }}
                  data-testid={`live-event-${i}`} testID={`live-event-${i}`}
                >
                  <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: isNew ? (globalThis as any).__alphaColor(T.success, '20') : T.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={isNew ? 'flash' : 'person'} size={14} color={isNew ? T.success : T.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.text, fontSize: 11, fontWeight: '600' }}>{ev.email}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 9 }}>
                      {ev.city || 'Private IP'}{ev.country_code ? `, ${ev.country_code}` : ''} | {ev.ip_address} | {ev.device || 'Unknown'}
                    </Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: isNew ? T.success : T.textMuted, fontSize: 10, fontWeight: '700' }}>{agoStr}</Text>
                    {isNew && <Text style={{ color: T.successText, fontSize: 8, fontWeight: '800' }}>{tx('admin.geoMapPanel.auto.text.020', 'NEW')}</Text>}
                  </View>
                </View>
              );
            })}
          </ScrollView>
        )}
      </View>
    </View>
  );
}
