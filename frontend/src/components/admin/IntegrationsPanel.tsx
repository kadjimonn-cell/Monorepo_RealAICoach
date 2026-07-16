import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

export default function IntegrationsPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const META: Record<string, { color: string; icon: string }> = {
    greenhouse: { color: 'var(--app-primary)', icon: 'leaf' }, // @theme-ok residual semantic hex (reviewed)
    lever: { color: colors.primary, icon: 'git-branch' },
    workday: { color: colors.warningText, icon: 'business' },
  };
  const { data: availData, loading: aLoading, refetch: load } = useLiveQuery('/integrations/available', { entity: 'integrations' });
  const { data: configuredData, loading: cLoading } = useLiveQuery('/integrations/', { entity: 'integrations' });
  const available = availData?.integrations || [];
  const configured = configuredData?.integrations || [];
  const loading = aLoading || cLoading;
  const [showSetup, setShowSetup] = useState<string | null>(null);
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [syncing, setSyncing] = useState<string | null>(null);
  const [selectedLogs, setSelectedLogs] = useState<{ id: string; logs: any[] } | null>(null);
  const [testMode, setTestMode] = useState(false);

  const setup = async (iid: string) => {
    try {
      await api.post('/integrations/', { integration_id: iid, credentials: creds, test_mode: testMode });
      setShowSetup(null); setCreds({}); setTestMode(false); load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/IntegrationsPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const sync = async (cid: string) => {
    setSyncing(cid);
    try { await api.post(`/integrations/${cid}/sync`); load(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/IntegrationsPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSyncing(null);
  };

  const remove = async (cid: string) => {
    try { await api.delete(`/integrations/${cid}`); setSelectedLogs(null); load(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/IntegrationsPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const viewLogs = async (cid: string) => {
    try {
      const r = await api.get(`/integrations/${cid}/logs`);
      setSelectedLogs({ id: cid, logs: r.data.logs || [] });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/IntegrationsPanel.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (loading) return <ActivityIndicator color={'var(--app-primary)'} />;

  return (
    <View data-testid="integrations-panel" testID="integrations-panel">
      <View style={{ marginBottom: 6 }}>
        <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.integrationsPanel.auto.text.001', 'ATS & HRIS Integrations')}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.integrationsPanel.auto.text.002', 'Manage platform connections to Greenhouse, Lever, Workday')}</Text>
      </View>

      {/* Stats */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, marginBottom: 16 }}>
        <View style={{ flex: 1, backgroundColor: colors.successSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.successSoft }}>
          <Text style={{ color: colors.successText, fontSize: 20, fontWeight: '800' }}>{configured.length}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.integrationsPanel.auto.text.003', 'Connected')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.primarySoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.primarySoft }}>
          <Text style={{ color: colors.primary, fontSize: 20, fontWeight: '800' }}>{available.length}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.integrationsPanel.auto.text.004', 'Available')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: colors.accentSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: colors.accentSoft }}>
          <Text style={{ color: colors.accent, fontSize: 20, fontWeight: '800' }}>{configured.reduce((s, c) => s + (c.sync_status?.records_synced || 0), 0)}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.integrationsPanel.auto.text.005', 'Records Synced')}</Text>
        </View>
      </View>

      {/* Active Integrations */}
      {configured.length > 0 && (
        <>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 10 }}>{tx('admin.integrationsPanel.auto.text.006', 'Active Connections')}</Text>
          {configured.map(c => {
            const m = META[c.integration_id] || { color: colors.textSec, icon: 'link' };
            return (
              <View key={c.config_id} data-testid={`admin-connected-${c.integration_id}`} testID={`admin-connected-${c.integration_id}`}
                style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: colors.border, borderLeftWidth: 3, borderLeftColor: m.color }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
                  <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(m.color, '15'), alignItems: 'center', justifyContent: 'center', marginRight: 10 }}>
                    <Ionicons name={m.icon as any} size={16} color={m.color} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{c.integration_name}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                      {c.sync_status?.last_sync ? `Synced: ${new Date(c.sync_status.last_sync).toLocaleString()} | ${c.sync_status.records_synced} records` : 'Never synced'}
                    </Text>
                  </View>
                  <View style={{ backgroundColor: c.test_mode ? 'var(--app-warning-soft)' : 'var(--app-success-soft)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                    <Text style={{ color: c.test_mode ? 'var(--app-warning)' : 'var(--app-success)', fontSize: 9, fontWeight: '800' }}>{c.test_mode ? 'TEST' : 'ACTIVE'}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  <TouchableOpacity onPress={() => sync(c.config_id)} data-testid={`admin-sync-${c.config_id}`} testID={`admin-sync-${c.config_id}`}
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(m.color, '15'), paddingVertical: 8, borderRadius: 8 }}>
                    <Ionicons name="sync" size={12} color={m.color} />
                    <Text style={{ color: m.color, fontSize: 10, fontWeight: '700' }}>{syncing === c.config_id ? 'Syncing...' : 'Sync'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => viewLogs(c.config_id)} data-testid={`admin-logs-${c.config_id}`} testID={`admin-logs-${c.config_id}`}
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, backgroundColor: colors.surfaceHover, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.border }}>
                    <Ionicons name="list" size={12} color={colors.textMuted} />
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.integrationsPanel.auto.text.007', 'Logs')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => remove(c.config_id)} data-testid={`admin-remove-${c.config_id}`} testID={`admin-remove-${c.config_id}`}
                    style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.errorSoft }}>
                    <Ionicons name="trash-outline" size={14} color={'var(--app-error)'} />
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
        </>
      )}

      {/* Sync Logs Modal */}
      {selectedLogs && (
        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30') }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.integrationsPanel.auto.text.008', 'Sync History')}</Text>
            <TouchableOpacity accessibilityLabel={tx('admin.integrationsPanel.auto.accessibility.001', 'No sync logs yet')} onPress={() => setSelectedLogs(null)}><Ionicons name="close" size={16} color={colors.textMuted} /></TouchableOpacity>
          </View>
          {selectedLogs.logs.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 11, textAlign: 'center', padding: 12 }}>{tx('admin.integrationsPanel.auto.text.009', 'No sync logs yet')}</Text>
          ) : selectedLogs.logs.slice(0, 10).map((log, idx) => (
            <View key={log.log_id || idx} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: idx < 9 ? 1 : 0, borderBottomColor: colors.border }}>
              <Ionicons name={log.status === 'completed' ? 'checkmark-circle' : 'warning'} size={14} color={log.status === 'completed' ? 'var(--app-success)' : 'var(--app-warning)'} />
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '600', marginLeft: 8, flex: 1 }}>{log.records_synced} records</Text>
              {log.errors > 0 && <Text style={{ color: colors.error, fontSize: 10, fontWeight: '700', marginRight: 8 }}>{log.errors} err</Text>}
              <Text style={{ color: colors.textMuted, fontSize: 9 }}>{new Date(log.created_at).toLocaleString()}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Available */}
      <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 10, marginTop: 8 }}>{tx('admin.integrationsPanel.auto.text.010', 'Available Connectors')}</Text>
      {available.map(a => {
        const m = META[a.id] || { color: colors.textSec, icon: 'link' };
        const isConfigured = configured.some(c => c.integration_id === a.id);
        return (
          <View key={a.id} data-testid={`admin-available-${a.id}`} testID={`admin-available-${a.id}`}
            style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: showSetup === a.id ? (globalThis as any).__alphaColor(m.color, '40') : colors.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: showSetup === a.id ? 10 : 0 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <View style={{ width: 34, height: 34, borderRadius: 9, backgroundColor: (globalThis as any).__alphaColor(m.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={m.icon as any} size={16} color={m.color} />
                </View>
                <View>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{a.name}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>{a.type} | {a.webhooks?.length || 0} webhooks</Text>
                </View>
              </View>
              {isConfigured ? (
                <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800' }}>{tx('admin.integrationsPanel.auto.text.011', 'CONNECTED')}</Text>
              ) : (
                <TouchableOpacity onPress={() => { setShowSetup(showSetup === a.id ? null : a.id); setCreds({}); }} data-testid={`admin-setup-${a.id}`} testID={`admin-setup-${a.id}`}
                  style={{ backgroundColor: (globalThis as any).__alphaColor(m.color, '15'), paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(m.color, '40') }}>
                  <Text style={{ color: m.color, fontSize: 10, fontWeight: '700' }}>{tx('admin.integrationsPanel.auto.text.012', 'Configure')}</Text>
                </TouchableOpacity>
              )}
            </View>
            {showSetup === a.id && (
              <View>
                {/* Test Mode Toggle */}
                <TouchableOpacity onPress={() => setTestMode(!testMode)} data-testid={`admin-testmode-toggle-${a.id}`} testID={`admin-testmode-toggle-${a.id}`}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8, paddingHorizontal: 10, marginBottom: 10, backgroundColor: testMode ? 'var(--app-warning-soft)' : colors.surface, borderRadius: 8, borderWidth: 1, borderColor: testMode ? 'var(--app-warning-soft)' : colors.border }}>
                  <Ionicons name={testMode ? 'flask' : 'flask-outline'} size={16} color={testMode ? 'var(--app-warning)' : colors.textMuted} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: testMode ? 'var(--app-warning)' : colors.text, fontSize: 11, fontWeight: '700' }}>Test Mode {testMode ? 'ON' : 'OFF'}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 9 }}>{testMode ? 'Uses simulated data, no real API keys needed' : 'Requires real API credentials'}</Text>
                  </View>
                  <View style={{ width: 36, height: 20, borderRadius: 10, backgroundColor: testMode ? 'var(--app-warning)' : colors.border, justifyContent: 'center', paddingHorizontal: 2 }}>
                    <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: colors.primaryText, alignSelf: testMode ? 'flex-end' : 'flex-start' }} />
                  </View>
                </TouchableOpacity>
                {!testMode && (a.fields || []).map((f: string) => (
                  <TextInput key={f} value={creds[f] || ''} onChangeText={v => setCreds({ ...creds, [f]: v })} data-testid={`admin-field-${f}`} testID={`admin-field-${f}`}
                    placeholder={f.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())} placeholderTextColor={colors.textMuted}
                    secureTextEntry={f.includes('secret') || f.includes('key')}
                    style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 8, padding: 10, marginBottom: 6, borderWidth: 1, borderColor: colors.border, fontSize: 12 }} />
                ))}
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 4 }}>
                  <TouchableOpacity onPress={() => setup(a.id)} data-testid={`admin-connect-${a.id}`} testID={`admin-connect-${a.id}`}
                    style={{ flex: 1, backgroundColor: m.color, borderRadius: 8, paddingVertical: 10, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 4 }}>
                    {testMode && <Ionicons name="flask" size={12} color={colors.primaryText} />}
                    <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{testMode ? 'Connect (Test)' : 'Connect'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity accessibilityLabel={tx('admin.integrationsPanel.auto.accessibility.002', 'Cancel')} onPress={() => { setShowSetup(null); setTestMode(false); }} style={{ paddingHorizontal: 16, paddingVertical: 10 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('admin.integrationsPanel.auto.text.013', 'Cancel')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </View>
        );
      })}
    </View>
  );
}
