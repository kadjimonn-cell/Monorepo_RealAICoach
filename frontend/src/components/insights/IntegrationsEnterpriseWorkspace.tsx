import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  useWindowDimensions,
  ActivityIndicator,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../AppShell';
import { IntegrationsSkeleton } from '../SkeletonLoaders';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import api from '../../services/api';

const statusTone = (connected: boolean, colors: any) => {
  if (connected) return { bg: `${colors.success}18`, border: `${colors.success}40`, text: colors.successText || 'var(--app-success)' };
  return { bg: `${colors.warning}18`, border: `${colors.warning}40`, text: colors.warningText || 'var(--app-warning)' };
};

const SCHEDULE_OPTIONS = [0, 6, 24, 72];

export default function IntegrationsEnterpriseWorkspace() {
  const { colors } = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();
  const tx = useCallback(
    (key: string, fallback: string) => {
      const value = t(key);
      return value === key ? fallback : value;
    },
    [t],
  );
  const router = useRouter();
  const { width } = useWindowDimensions();

  const isDesktop = width >= 1200;
  const isTablet = width >= 768 && width < 1200;
  const pad = isDesktop ? 28 : isTablet ? 22 : 14;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [availableIntegrations, setAvailableIntegrations] = useState<any[]>([]);
  const [connectedIntegrations, setConnectedIntegrations] = useState<any[]>([]);
  const [integrationStats, setIntegrationStats] = useState<any>(null);
  const [activeConnectorId, setActiveConnectorId] = useState<string | null>(null);
  const [wizardCreds, setWizardCreds] = useState<Record<string, string>>({});
  const [wizardTestMode, setWizardTestMode] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [selectedLogs, setSelectedLogs] = useState<{ configId: string; logs: any[] } | null>(null);
  const [selectedHealth, setSelectedHealth] = useState<any>(null);
  const [opError, setOpError] = useState<string | null>(null);
  const [seedPolicy, setSeedPolicy] = useState<any>(null);

  const loadData = useCallback(async () => {
    setLiveError(null);
    setLiveLoading(true);
    try {
      const [availableRes, connectedRes, statsRes] = await Promise.allSettled([
        api.get('/integrations/available', { silentLoading: true }),
        api.get('/integrations/', { silentLoading: true }),
        api.get('/integrations/dashboard/stats', { silentLoading: true }),
      ]);

      if (availableRes.status === 'fulfilled') {
        setAvailableIntegrations(Array.isArray(availableRes.value?.data?.integrations) ? availableRes.value.data.integrations : []);
      } else {
        setAvailableIntegrations([]);
      }

      if (connectedRes.status === 'fulfilled') {
        const integrations = Array.isArray(connectedRes.value?.data?.integrations) ? connectedRes.value.data.integrations : [];
        setConnectedIntegrations(integrations);
      } else {
        setConnectedIntegrations([]);
      }

      if (statsRes.status === 'fulfilled') {
        setIntegrationStats(statsRes.value?.data || null);
      } else {
        setIntegrationStats(null);
      }

      if (user?.is_admin) {
        try {
          const policyRes = await api.get('/integrations/admin/test-mode-seed-policy', { silentLoading: true });
          setSeedPolicy(policyRes?.data || null);
        } catch {
          setSeedPolicy(null);
        }
      } else {
        setSeedPolicy(null);
      }

      if (availableRes.status === 'rejected' && connectedRes.status === 'rejected' && statsRes.status === 'rejected') {
        setLiveError(tx('integrations.enterprise.error.all', 'Unable to load integration status right now.'));
      }
    } catch {
      setLiveError(tx('integrations.enterprise.error.generic', 'Unable to load integration status right now.'));
      setAvailableIntegrations([]);
      setConnectedIntegrations([]);
      setIntegrationStats(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLiveLoading(false);
    }
  }, [tx, user?.is_admin]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const interval = setInterval(() => {
      void loadData();
    }, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const onRefresh = () => {
    setRefreshing(true);
    void loadData();
  };

  const extractErrorMessage = useCallback(
    (error: any) => {
      const detail = error?.response?.data?.detail;
      if (typeof detail === 'string') return detail;
      if (detail?.message) return detail.message;
      if (error?.response?.data?.message) return error.response.data.message;
      return tx('integrations.enterprise.error.action', 'Action failed. Please retry.');
    },
    [tx],
  );

  const runAction = useCallback(
    async (actionKey: string, action: () => Promise<void>) => {
      setBusyAction(actionKey);
      setOpError(null);
      try {
        await action();
      } catch (error: any) {
        setOpError(extractErrorMessage(error));
      } finally {
        setBusyAction(null);
      }
    },
    [extractErrorMessage],
  );

  const openWizard = useCallback((connectorId: string) => {
    setActiveConnectorId(connectorId);
    setWizardCreds({});
    setWizardTestMode(true);
    setOpError(null);
  }, []);

  const selectedConnector = useMemo(
    () => availableIntegrations.find((item: any) => String(item?.id || '') === String(activeConnectorId || '')),
    [availableIntegrations, activeConnectorId],
  );

  const saveConnector = useCallback(async () => {
    if (!selectedConnector?.id) return;
    await runAction(`connect-${selectedConnector.id}`, async () => {
      await api.post('/integrations/', {
        integration_id: selectedConnector.id,
        credentials: wizardCreds,
        test_mode: wizardTestMode,
      });
      setActiveConnectorId(null);
      setWizardCreds({});
      setWizardTestMode(true);
      await loadData();
    });
  }, [selectedConnector?.id, wizardCreds, wizardTestMode, runAction, loadData]);

  const triggerSync = useCallback(
    async (configId: string) => {
      await runAction(`sync-${configId}`, async () => {
        await api.post(`/integrations/${configId}/sync`);
        await loadData();
      });
    },
    [runAction, loadData],
  );

  const fetchLogs = useCallback(
    async (configId: string) => {
      await runAction(`logs-${configId}`, async () => {
        const response = await api.get(`/integrations/${configId}/logs`, { silentLoading: true });
        setSelectedLogs({ configId, logs: Array.isArray(response?.data?.logs) ? response.data.logs : [] });
      });
    },
    [runAction],
  );

  const fetchHealth = useCallback(
    async (configId: string) => {
      await runAction(`health-${configId}`, async () => {
        const response = await api.get(`/integrations/${configId}/health`, { silentLoading: true });
        setSelectedHealth(response?.data || null);
      });
    },
    [runAction],
  );

  const removeConnector = useCallback(
    async (configId: string) => {
      if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
        const shouldDelete = window.confirm(tx('integrations.enterprise.deleteConfirm', 'Disconnect this integration and remove synced data?'));
        if (!shouldDelete) return;
      }
      await runAction(`delete-${configId}`, async () => {
        await api.delete(`/integrations/${configId}`);
        if (selectedLogs?.configId === configId) setSelectedLogs(null);
        if (selectedHealth?.config_id === configId) setSelectedHealth(null);
        await loadData();
      });
    },
    [runAction, loadData, tx, selectedLogs?.configId, selectedHealth?.config_id],
  );

  const updateSchedule = useCallback(
    async (configId: string, intervalHours: number) => {
      await runAction(`schedule-${configId}-${intervalHours}`, async () => {
        await api.post('/integrations/schedule', { config_id: configId, interval_hours: intervalHours });
        await loadData();
      });
    },
    [runAction, loadData],
  );

  const updateSeedPolicy = useCallback(
    async (retentionHours: number) => {
      if (!user?.is_admin) return;
      await runAction(`seed-policy-${retentionHours}`, async () => {
        const response = await api.put('/integrations/admin/test-mode-seed-policy', {
          enabled: true,
          retention_hours: retentionHours,
          dry_run: false,
        });
        setSeedPolicy({ ...(seedPolicy || {}), policy: response?.data?.policy || {} });
      });
    },
    [runAction, user?.is_admin, seedPolicy],
  );

  const runSeedCleanup = useCallback(
    async (dryRun: boolean) => {
      if (!user?.is_admin) return;
      await runAction(`seed-cleanup-${dryRun ? 'dry' : 'apply'}`, async () => {
        const retention = Number(seedPolicy?.policy?.retention_hours || 72);
        const response = await api.post('/integrations/admin/test-mode-seed-cleanup/run', {
          retention_hours: retention,
          dry_run: dryRun,
        });
        setSeedPolicy((prev: any) => ({ ...(prev || {}), latest_run: response?.data || {} }));
        await loadData();
      });
    },
    [runAction, user?.is_admin, seedPolicy?.policy?.retention_hours, loadData],
  );

  const connectedMap = useMemo(() => {
    const map: Record<string, any> = {};
    connectedIntegrations.forEach((item) => {
      const key = String(item?.integration_id || '').trim();
      if (key) map[key] = item;
    });
    return map;
  }, [connectedIntegrations]);

  const recentSyncs = useMemo(() => {
    return Array.isArray(integrationStats?.recent_syncs) ? integrationStats.recent_syncs : [];
  }, [integrationStats?.recent_syncs]);

  useEffect(() => {
    if (!selectedLogs?.configId) return;
    const exists = connectedIntegrations.some((item: any) => item?.config_id === selectedLogs.configId);
    if (!exists) setSelectedLogs(null);
  }, [connectedIntegrations, selectedLogs]);

  const mergedRows = useMemo(() => {
    const rows: any[] = availableIntegrations.map((integration: any) => {
      const integrationId = String(integration?.id || '').trim();
      const connected = connectedMap[integrationId];
      return {
        id: integrationId,
        name: integration?.name || integrationId,
        icon: integration?.icon || 'link-outline',
        category: integration?.category || tx('integrations.enterprise.unknownCategory', 'General'),
        connected: Boolean(connected),
        mode: connected?.test_mode ? tx('integrations.enterprise.mode.test', 'Test') : tx('integrations.enterprise.mode.live', 'Live'),
        last_sync: connected?.sync_status?.last_sync || null,
        records_synced: connected?.sync_status?.records_synced || 0,
        config_id: connected?.config_id || '',
        sync_health: connected?.sync_health || connected?.sync_status || {},
      };
    });
    return rows;
  }, [availableIntegrations, connectedMap, tx]);

  if (loading) {
    return (
      <AppShell>
        <IntegrationsSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top']} data-testid="integrations-enterprise-page" testID="integrations-enterprise-page">
        <ScrollView
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          contentContainerStyle={{
            paddingBottom: 80,
            maxWidth: 1240,
            width: '100%' as any,
            alignSelf: 'center' as any,
          }}
          data-testid="integrations-enterprise-scroll"
          testID="integrations-enterprise-scroll"
        >
          <View
            style={{
              marginTop: 14,
              marginHorizontal: pad,
              borderRadius: 20,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.card,
              padding: isDesktop ? 22 : 16,
              gap: 12,
            }}
            data-testid="integrations-enterprise-header"
            testID="integrations-enterprise-header"
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
              <View style={{ maxWidth: 960 }}>
                <Text style={{ color: colors.text, fontSize: isDesktop ? 38 : 30, fontWeight: '900', letterSpacing: -0.7 }} data-testid="integrations-enterprise-title" testID="integrations-enterprise-title">
                  {tx('integrations.enterprise.title', 'Integrations Command Center')}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 4, lineHeight: 19 }} data-testid="integrations-enterprise-subtitle" testID="integrations-enterprise-subtitle">
                  {tx('integrations.enterprise.subtitle', 'Live integration health, sync telemetry, and connector readiness powered by platform data.')}
                </Text>
              </View>

              <TouchableOpacity accessibilityLabel="Integrations enterprise refresh button"
                onPress={() => void loadData()}
                style={{
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: `${colors.primary}55`,
                  backgroundColor: `${colors.primary}16`,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                }}
                data-testid="integrations-enterprise-refresh-button"
                testID="integrations-enterprise-refresh-button"
              >
                <Ionicons name="refresh-outline" size={14} color={colors.primary} />
                <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>{tx('integrations.enterprise.refresh', 'Refresh')}</Text>
              </TouchableOpacity>
            </View>

            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }} data-testid="integrations-enterprise-kpi-strip" testID="integrations-enterprise-kpi-strip">
              {[
                {
                  id: 'active',
                  label: tx('integrations.enterprise.kpi.active', 'Active Integrations'),
                  value: integrationStats?.active_integrations ?? connectedIntegrations.length,
                  tone: colors.primary,
                },
                {
                  id: 'candidates',
                  label: tx('integrations.enterprise.kpi.candidates', 'Synced Candidates'),
                  value: integrationStats?.total_candidates ?? 0,
                  tone: colors.info || colors.primary,
                },
                {
                  id: 'jobs',
                  label: tx('integrations.enterprise.kpi.jobs', 'Synced Jobs'),
                  value: integrationStats?.total_jobs ?? 0,
                  tone: colors.successText || 'var(--app-success)',
                },
                {
                  id: 'health',
                  label: tx('integrations.enterprise.kpi.health', 'Health Score'),
                  value: integrationStats?.health_score ?? 0,
                  tone: colors.successText || 'var(--app-success)',
                },
                {
                  id: 'connectors',
                  label: tx('integrations.enterprise.kpi.connectors', 'Available Connectors'),
                  value: availableIntegrations.length,
                  tone: colors.warningText || 'var(--app-warning)',
                },
              ].map((kpi) => (
                <View key={kpi.id} style={{ borderRadius: 12, borderWidth: 1, borderColor: `${kpi.tone}45`, backgroundColor: `${kpi.tone}16`, paddingHorizontal: 10, paddingVertical: 8, minWidth: 150 }} data-testid={`integrations-enterprise-kpi-${kpi.id}`} testID={`integrations-enterprise-kpi-${kpi.id}`}>
                  <Text style={{ color: kpi.tone, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{kpi.label}</Text>
                  <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900', marginTop: 2 }}>{String(kpi.value || 0)}</Text>
                </View>
              ))}
            </View>

            {opError ? (
              <View
                style={{ borderRadius: 12, borderWidth: 1, borderColor: `${colors.error}55`, backgroundColor: `${colors.error}16`, paddingHorizontal: 10, paddingVertical: 8 }}
                data-testid="integrations-enterprise-operation-error"
                testID="integrations-enterprise-operation-error"
              >
                <Text style={{ color: colors.error, fontSize: 11, fontWeight: '700' }}>{opError}</Text>
              </View>
            ) : null}

            {user?.is_admin ? (
              <View
                style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 12, gap: 8 }}
                data-testid="integrations-enterprise-seed-cleanup-policy-panel"
                testID="integrations-enterprise-seed-cleanup-policy-panel"
              >
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="integrations-enterprise-seed-cleanup-policy-title" testID="integrations-enterprise-seed-cleanup-policy-title">
                  Test-mode seed cleanup policy
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="integrations-enterprise-seed-cleanup-policy-summary" testID="integrations-enterprise-seed-cleanup-policy-summary">
                  Retention: {String(seedPolicy?.policy?.retention_hours || 72)}h • Last run: {seedPolicy?.latest_run?.created_at ? new Date(seedPolicy.latest_run.created_at).toLocaleString() : 'Never'}
                </Text>

                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  {[24, 48, 72, 168].map((hours) => {
                    const active = Number(seedPolicy?.policy?.retention_hours || 72) === hours;
                    return (
                      <TouchableOpacity
                        key={`seed-policy-${hours}`}
                        onPress={() => void updateSeedPolicy(hours)}
                        style={{
                          borderRadius: 999,
                          borderWidth: 1,
                          borderColor: active ? `${colors.primary}55` : colors.border,
                          backgroundColor: active ? `${colors.primary}16` : colors.card,
                          paddingHorizontal: 8,
                          paddingVertical: 4,
                        }}
                        data-testid={`integrations-enterprise-seed-cleanup-retention-${hours}-button`}
                        testID={`integrations-enterprise-seed-cleanup-retention-${hours}-button`}
                      >
                        <Text style={{ color: active ? colors.primary : colors.textMuted, fontSize: 10, fontWeight: '800' }}>Retain {hours}h</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>

                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  <TouchableOpacity
                    onPress={() => void runSeedCleanup(true)}
                    style={{ borderRadius: 10, borderWidth: 1, borderColor: `${colors.info || colors.primary}55`, backgroundColor: `${colors.info || colors.primary}16`, paddingHorizontal: 10, paddingVertical: 7 }}
                    data-testid="integrations-enterprise-seed-cleanup-dry-run-button"
                    testID="integrations-enterprise-seed-cleanup-dry-run-button"
                  >
                    <Text style={{ color: colors.info || colors.primary, fontSize: 10, fontWeight: '800' }}>Dry run cleanup</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    onPress={() => void runSeedCleanup(false)}
                    style={{ borderRadius: 10, borderWidth: 1, borderColor: `${colors.warning}55`, backgroundColor: `${colors.warning}16`, paddingHorizontal: 10, paddingVertical: 7 }}
                    data-testid="integrations-enterprise-seed-cleanup-apply-button"
                    testID="integrations-enterprise-seed-cleanup-apply-button"
                  >
                    <Text style={{ color: colors.warningText || 'var(--app-warning)', fontSize: 10, fontWeight: '800' }}>Apply cleanup</Text>
                  </TouchableOpacity>
                </View>

                {seedPolicy?.latest_run ? (
                  <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="integrations-enterprise-seed-cleanup-last-run" testID="integrations-enterprise-seed-cleanup-last-run">
                    Last deleted configs: {String(seedPolicy?.latest_run?.deleted?.configs || 0)} • candidates: {String(seedPolicy?.latest_run?.deleted?.ats_candidates || 0)}
                  </Text>
                ) : null}
              </View>
            ) : null}

            {selectedConnector ? (
              <View
                style={{ borderRadius: 14, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: `${colors.primary}12`, padding: 12, gap: 10 }}
                data-testid="integrations-enterprise-setup-wizard"
                testID="integrations-enterprise-setup-wizard"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="integrations-enterprise-setup-title" testID="integrations-enterprise-setup-title">
                    {tx('integrations.enterprise.setup.title', 'Connector Setup')} · {selectedConnector?.name}
                  </Text>
                  <TouchableOpacity
                    accessibilityLabel="Close connector setup"
                    onPress={() => setActiveConnectorId(null)}
                    style={{ paddingHorizontal: 8, paddingVertical: 6 }}
                    data-testid="integrations-enterprise-setup-close"
                    testID="integrations-enterprise-setup-close"
                  >
                    <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('integrations.enterprise.close', 'Close')}</Text>
                  </TouchableOpacity>
                </View>

                <TouchableOpacity
                  accessibilityLabel="Toggle connector test mode"
                  onPress={() => setWizardTestMode((v) => !v)}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: wizardTestMode ? `${colors.warning}60` : colors.border, backgroundColor: wizardTestMode ? `${colors.warning}18` : colors.surface, paddingHorizontal: 10, paddingVertical: 9 }}
                  data-testid="integrations-enterprise-setup-testmode-toggle"
                  testID="integrations-enterprise-setup-testmode-toggle"
                >
                  <Text style={{ color: wizardTestMode ? colors.warningText || 'var(--app-warning)' : colors.text, fontSize: 11, fontWeight: '800' }}>
                    {tx('integrations.enterprise.setup.testMode', 'Test Mode')}: {wizardTestMode ? tx('integrations.enterprise.on', 'ON') : tx('integrations.enterprise.off', 'OFF')}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>
                    {wizardTestMode
                      ? tx('integrations.enterprise.setup.testDesc', 'Safe simulation. No real connector keys required.')
                      : tx('integrations.enterprise.setup.liveDesc', 'Live mode validates required credentials.')}
                  </Text>
                </TouchableOpacity>

                {!wizardTestMode && Array.isArray(selectedConnector?.fields)
                  ? selectedConnector.fields.map((field: string) => (
                      <TextInput
                        key={field}
                        value={wizardCreds[field] || ''}
                        onChangeText={(value) => setWizardCreds((prev) => ({ ...prev, [field]: value }))}
                        placeholder={field.replace(/_/g, ' ').replace(/\b\w/g, (s) => s.toUpperCase())}
                        placeholderTextColor={colors.textMuted}
                        secureTextEntry={field.includes('secret') || field.includes('key') || field.includes('token')}
                        style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.text, paddingHorizontal: 10, paddingVertical: 10, fontSize: 12 }}
                        data-testid={`integrations-enterprise-setup-field-${field}`}
                        testID={`integrations-enterprise-setup-field-${field}`}
                      />
                    ))
                  : null}

                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  <TouchableOpacity
                    accessibilityLabel="Save connector setup"
                    onPress={() => void saveConnector()}
                    disabled={busyAction === `connect-${selectedConnector.id}`}
                    style={{ borderRadius: 10, borderWidth: 1, borderColor: `${colors.success}55`, backgroundColor: `${colors.success}18`, paddingHorizontal: 12, paddingVertical: 9 }}
                    data-testid="integrations-enterprise-setup-save"
                    testID="integrations-enterprise-setup-save"
                  >
                    <Text style={{ color: colors.successText || 'var(--app-success)', fontSize: 11, fontWeight: '800' }}>
                      {busyAction === `connect-${selectedConnector.id}` ? tx('integrations.enterprise.saving', 'Saving...') : tx('integrations.enterprise.saveConnector', 'Save Connector')}
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : null}
          </View>

          <View style={{ marginTop: 14, marginHorizontal: pad, flexDirection: isDesktop ? 'row' : 'column', gap: 12 }} data-testid="integrations-enterprise-main-row" testID="integrations-enterprise-main-row">
            <View style={{ flex: 1.2, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }} data-testid="integrations-enterprise-connectors-panel" testID="integrations-enterprise-connectors-panel">
              <View style={{ padding: 14, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('integrations.enterprise.connectors.title', 'Connector Health Matrix')}</Text>
                {liveLoading ? <ActivityIndicator size="small" color={colors.primary} /> : null}
              </View>

              {mergedRows.length === 0 ? (
                <View style={{ padding: 14 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="integrations-enterprise-empty-connectors" testID="integrations-enterprise-empty-connectors">
                    {liveError || tx('integrations.enterprise.connectors.empty', 'No connector metadata available right now.')}
                  </Text>
                </View>
              ) : (
                mergedRows.map((row, idx) => {
                  const tone = statusTone(row.connected, colors);
                  return (
                    <View key={row.id || idx} style={{ paddingHorizontal: 14, paddingVertical: 12, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }} data-testid={`integrations-enterprise-row-${row.id || idx}`} testID={`integrations-enterprise-row-${row.id || idx}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
                        <Ionicons name={row.icon as any} size={14} color={row.connected ? colors.success : colors.textMuted} />
                        <View>
                          <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{row.name}</Text>
                          <Text style={{ color: colors.textMuted, fontSize: 10 }}>{row.category}</Text>
                        </View>
                      </View>

                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <View style={{ borderRadius: 999, borderWidth: 1, borderColor: tone.border, backgroundColor: tone.bg, paddingHorizontal: 8, paddingVertical: 4 }}>
                          <Text style={{ color: tone.text, fontSize: 10, fontWeight: '800' }}>{row.connected ? tx('integrations.enterprise.connected', 'CONNECTED') : tx('integrations.enterprise.notConnected', 'NOT CONNECTED')}</Text>
                        </View>
                        {row.connected ? (
                          <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 8, paddingVertical: 4 }}>
                            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('integrations.enterprise.mode', 'Mode')}: {row.mode}</Text>
                          </View>
                        ) : null}
                      </View>

                      <Text style={{ color: colors.textMuted, fontSize: 10, minWidth: 150 }} data-testid={`integrations-enterprise-row-sync-${row.id || idx}`} testID={`integrations-enterprise-row-sync-${row.id || idx}`}>
                        {row.last_sync ? `${tx('integrations.enterprise.lastSync', 'Last sync')}: ${new Date(row.last_sync).toLocaleString()}` : tx('integrations.enterprise.noSyncYet', 'No sync yet')}
                      </Text>

                      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                        {!row.connected ? (
                          <TouchableOpacity
                            accessibilityLabel="Configure connector"
                            onPress={() => openWizard(row.id)}
                            style={{ borderRadius: 8, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: `${colors.primary}16`, paddingHorizontal: 9, paddingVertical: 6 }}
                            data-testid={`integrations-enterprise-configure-${row.id}`}
                            testID={`integrations-enterprise-configure-${row.id}`}
                          >
                            <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{tx('integrations.enterprise.configure', 'Configure')}</Text>
                          </TouchableOpacity>
                        ) : (
                          <>
                            <TouchableOpacity
                              accessibilityLabel="Sync connector now"
                              onPress={() => void triggerSync(row.config_id)}
                              style={{ borderRadius: 8, borderWidth: 1, borderColor: `${colors.success}55`, backgroundColor: `${colors.success}18`, paddingHorizontal: 9, paddingVertical: 6 }}
                              data-testid={`integrations-enterprise-sync-now-${row.id}`}
                              testID={`integrations-enterprise-sync-now-${row.id}`}
                            >
                              <Text style={{ color: colors.successText || 'var(--app-success)', fontSize: 10, fontWeight: '800' }}>
                                {busyAction === `sync-${row.config_id}` ? tx('integrations.enterprise.syncing', 'Syncing...') : tx('integrations.enterprise.syncNow', 'Sync now')}
                              </Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              accessibilityLabel="View connector logs"
                              onPress={() => void fetchLogs(row.config_id)}
                              style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 9, paddingVertical: 6 }}
                              data-testid={`integrations-enterprise-view-logs-${row.id}`}
                              testID={`integrations-enterprise-view-logs-${row.id}`}
                            >
                              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>{tx('integrations.enterprise.logs', 'Logs')}</Text>
                            </TouchableOpacity>
                          </>
                        )}
                      </View>
                    </View>
                  );
                })
              )}
            </View>

            <View style={{ flex: 1, gap: 12 }}>
              <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 10 }} data-testid="integrations-enterprise-connections-panel" testID="integrations-enterprise-connections-panel">
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('integrations.enterprise.connections.title', 'Connected Accounts')}</Text>
                {(connectedIntegrations || []).length === 0 ? (
                  <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('integrations.enterprise.connections.empty', 'No connected integrations found.')}</Text>
                ) : (
                  connectedIntegrations.slice(0, 8).map((item: any, idx: number) => (
                    <View key={item?.config_id || idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 8, gap: 3 }} data-testid={`integrations-enterprise-connected-item-${idx}`} testID={`integrations-enterprise-connected-item-${idx}`}>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid={`integrations-enterprise-connected-name-${item?.config_id || idx}`} testID={`integrations-enterprise-connected-name-${item?.config_id || idx}`}>
                        {item?.integration_name || item?.integration_id || tx('integrations.enterprise.unknownConnector', 'Connector')}
                      </Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                        {item?.test_mode ? tx('integrations.enterprise.mode.test', 'Test') : tx('integrations.enterprise.mode.live', 'Live')} · {item?.sync_status?.records_synced || 0} {tx('integrations.enterprise.recordsSynced', 'records synced')}
                      </Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid={`integrations-enterprise-connected-health-${item?.config_id || idx}`} testID={`integrations-enterprise-connected-health-${item?.config_id || idx}`}>
                        {tx('integrations.enterprise.health', 'Health')}: {item?.sync_health?.status || tx('integrations.enterprise.sync.statusUnknown', 'status unknown')} · {item?.sync_health?.score ?? 0}
                      </Text>

                      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                        <TouchableOpacity
                          accessibilityLabel="Sync connected integration"
                          onPress={() => void triggerSync(item?.config_id)}
                          style={{ borderRadius: 8, borderWidth: 1, borderColor: `${colors.success}55`, backgroundColor: `${colors.success}18`, paddingHorizontal: 8, paddingVertical: 6 }}
                          data-testid={`integrations-enterprise-connected-sync-${item?.config_id}`}
                          testID={`integrations-enterprise-connected-sync-${item?.config_id}`}
                        >
                          <Text style={{ color: colors.successText || 'var(--app-success)', fontSize: 10, fontWeight: '800' }}>
                            {busyAction === `sync-${item?.config_id}` ? tx('integrations.enterprise.syncing', 'Syncing...') : tx('integrations.enterprise.syncNow', 'Sync now')}
                          </Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          accessibilityLabel="View connected integration logs"
                          onPress={() => void fetchLogs(item?.config_id)}
                          style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 8, paddingVertical: 6 }}
                          data-testid={`integrations-enterprise-connected-logs-${item?.config_id}`}
                          testID={`integrations-enterprise-connected-logs-${item?.config_id}`}
                        >
                          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800' }}>{tx('integrations.enterprise.logs', 'Logs')}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          accessibilityLabel="View connected integration health"
                          onPress={() => void fetchHealth(item?.config_id)}
                          style={{ borderRadius: 8, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: `${colors.primary}16`, paddingHorizontal: 8, paddingVertical: 6 }}
                          data-testid={`integrations-enterprise-connected-health-action-${item?.config_id}`}
                          testID={`integrations-enterprise-connected-health-action-${item?.config_id}`}
                        >
                          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{tx('integrations.enterprise.healthAction', 'Health')}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          accessibilityLabel="Disconnect integration"
                          onPress={() => void removeConnector(item?.config_id)}
                          style={{ borderRadius: 8, borderWidth: 1, borderColor: `${colors.error}55`, backgroundColor: `${colors.error}16`, paddingHorizontal: 8, paddingVertical: 6 }}
                          data-testid={`integrations-enterprise-connected-delete-${item?.config_id}`}
                          testID={`integrations-enterprise-connected-delete-${item?.config_id}`}
                        >
                          <Text style={{ color: colors.error, fontSize: 10, fontWeight: '800' }}>
                            {busyAction === `delete-${item?.config_id}` ? tx('integrations.enterprise.deleting', 'Disconnecting...') : tx('integrations.enterprise.disconnect', 'Disconnect')}
                          </Text>
                        </TouchableOpacity>
                      </View>

                      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                        {SCHEDULE_OPTIONS.map((hours) => {
                          const active = Number(item?.auto_sync_interval_hours || 0) === hours;
                          return (
                            <TouchableOpacity
                              key={`${item?.config_id}-${hours}`}
                              accessibilityLabel="Update auto sync schedule"
                              onPress={() => void updateSchedule(item?.config_id, hours)}
                              style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? `${colors.primary}55` : colors.border, backgroundColor: active ? `${colors.primary}16` : colors.card, paddingHorizontal: 8, paddingVertical: 4 }}
                              data-testid={`integrations-enterprise-schedule-${item?.config_id}-${hours}`}
                              testID={`integrations-enterprise-schedule-${item?.config_id}-${hours}`}
                            >
                              <Text style={{ color: active ? colors.primary : colors.textMuted, fontSize: 10, fontWeight: '800' }}>
                                {hours === 0 ? tx('integrations.enterprise.schedule.off', 'Auto-sync off') : tx('integrations.enterprise.schedule.every', 'Every')} {hours === 0 ? '' : `${hours}h`}
                              </Text>
                            </TouchableOpacity>
                          );
                        })}
                      </View>
                    </View>
                  ))
                )}
              </View>

              {selectedHealth ? (
                <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="integrations-enterprise-health-panel" testID="integrations-enterprise-health-panel">
                  <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('integrations.enterprise.healthPanel', 'Connector Health Insight')}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="integrations-enterprise-health-name" testID="integrations-enterprise-health-name">
                    {selectedHealth?.integration_name || selectedHealth?.integration_id}
                  </Text>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} data-testid="integrations-enterprise-health-score" testID="integrations-enterprise-health-score">
                    {tx('integrations.enterprise.health', 'Health')}: {selectedHealth?.sync_health?.status || tx('integrations.enterprise.sync.statusUnknown', 'status unknown')} · {selectedHealth?.sync_health?.score ?? 0}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="integrations-enterprise-health-recommendation" testID="integrations-enterprise-health-recommendation">
                    {selectedHealth?.recommended_action || tx('integrations.enterprise.noRecommendation', 'No recommendation available.')}
                  </Text>
                </View>
              ) : null}

              <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 10 }} data-testid="integrations-enterprise-sync-panel" testID="integrations-enterprise-sync-panel">
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('integrations.enterprise.sync.title', 'Recent Sync Activity')}</Text>
                {recentSyncs.length === 0 ? (
                  <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('integrations.enterprise.sync.empty', 'No recent sync activity yet.')}</Text>
                ) : (
                  recentSyncs.slice(0, 8).map((sync: any, idx: number) => (
                    <View key={`${sync?.config_id || idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 8, gap: 3 }} data-testid={`integrations-enterprise-sync-item-${idx}`} testID={`integrations-enterprise-sync-item-${idx}`}>
                      <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{sync?.integration_id || tx('integrations.enterprise.unknownConnector', 'Connector')}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                        {sync?.status || tx('integrations.enterprise.sync.statusUnknown', 'status unknown')} · {sync?.created_at ? new Date(sync.created_at).toLocaleString() : tx('integrations.enterprise.notAvailable', 'Not available')}
                      </Text>
                    </View>
                  ))
                )}
              </View>

              {selectedLogs ? (
                <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 14, gap: 8 }} data-testid="integrations-enterprise-logs-panel" testID="integrations-enterprise-logs-panel">
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{tx('integrations.enterprise.logsPanel', 'Connector Logs')}</Text>
                    <TouchableOpacity
                      accessibilityLabel="Close logs panel"
                      onPress={() => setSelectedLogs(null)}
                      data-testid="integrations-enterprise-logs-close"
                      testID="integrations-enterprise-logs-close"
                    >
                      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('integrations.enterprise.close', 'Close')}</Text>
                    </TouchableOpacity>
                  </View>
                  {selectedLogs.logs.length === 0 ? (
                    <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="integrations-enterprise-logs-empty" testID="integrations-enterprise-logs-empty">
                      {tx('integrations.enterprise.sync.empty', 'No recent sync activity yet.')}
                    </Text>
                  ) : (
                    selectedLogs.logs.slice(0, 8).map((log: any, idx: number) => (
                      <View key={log?.log_id || idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 10, paddingVertical: 8, gap: 3 }} data-testid={`integrations-enterprise-log-item-${idx}`} testID={`integrations-enterprise-log-item-${idx}`}>
                        <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{log?.status || tx('integrations.enterprise.sync.statusUnknown', 'status unknown')}</Text>
                        <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                          {tx('integrations.enterprise.recordsSynced', 'records synced')}: {log?.records_synced || 0} · {tx('integrations.enterprise.errors', 'errors')}: {log?.errors || 0}
                        </Text>
                        <Text style={{ color: colors.textMuted, fontSize: 10 }}>{log?.created_at ? new Date(log.created_at).toLocaleString() : tx('integrations.enterprise.notAvailable', 'Not available')}</Text>
                      </View>
                    ))
                  )}
                </View>
              ) : null}
            </View>
          </View>

          <View style={{ marginTop: 14, marginHorizontal: pad, flexDirection: isTablet ? 'column' : 'row', gap: 10 }}>
            <TouchableOpacity accessibilityLabel="Integrations enterprise call to action settings button"
              onPress={() => router.push('/settings')}
              style={{
                flex: 1,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: `${colors.primary}45`,
                backgroundColor: `${colors.primary}16`,
                paddingVertical: 13,
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'row',
                gap: 8,
              }}
              data-testid="integrations-enterprise-cta-settings"
              testID="integrations-enterprise-cta-settings"
            >
              <Ionicons name="settings-outline" size={15} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('integrations.enterprise.cta.settings', 'Open Settings')}</Text>
            </TouchableOpacity>

            <TouchableOpacity accessibilityLabel="Integrations enterprise call to action support button"
              onPress={() => router.push('/help')}
              style={{
                flex: 1,
                borderRadius: 14,
                borderWidth: 1,
                borderColor: `${colors.info || colors.primary}45`,
                backgroundColor: `${colors.info || colors.primary}16`,
                paddingVertical: 13,
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'row',
                gap: 8,
              }}
              data-testid="integrations-enterprise-cta-support"
              testID="integrations-enterprise-cta-support"
            >
              <Ionicons name="help-buoy-outline" size={15} color={colors.info || colors.primary} />
              <Text style={{ color: colors.info || colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('integrations.enterprise.cta.support', 'Contact Support')}</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    </AppShell>
  );
}
