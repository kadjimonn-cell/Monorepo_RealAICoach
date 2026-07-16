import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Linking, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

export default function IAPManagementPanel() {
  const s = useExecStyles();
  const colors = useAdminTheme();
  const T = useExecTheme();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const isCompact = width < 920;
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [config, setConfig] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [slo, setSlo] = useState<any>(null);
  const [bundles, setBundles] = useState<any[]>([]);
  const [commissionPolicy, setCommissionPolicy] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'transactions' | 'webhooks' | 'slo' | 'bundles' | 'config'>('overview');
  const [simulating, setSimulating] = useState(false);
  const [sandboxRunning, setSandboxRunning] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [drillRunning, setDrillRunning] = useState(false);
  const [simulationResult, setSimulationResult] = useState<any>(null);
  const [sandboxResult, setSandboxResult] = useState<any>(null);
  const [retryResult, setRetryResult] = useState<any>(null);
  const [drillResult, setDrillResult] = useState<any>(null);
  const [showAdvancedControls, setShowAdvancedControls] = useState(false);
  const panelTitle = t('iapManagement.header.title');

  const loadData = useCallback(async () => {
    try {
      const [cfgRes, statsRes, prodRes, sloRes, bundlesRes, policyRes] = await Promise.all([
        api.get('/iap/admin/config'),
        api.get('/iap/admin/stats'),
        api.get('/iap/products'),
        api.get('/iap/admin/slo').catch(() => ({ data: {} })),
        api.get('/iap/admin/compliance-bundles?limit=20').catch(() => ({ data: { bundles: [] } })),
        api.get('/iap/admin/commission-policy').catch(() => ({ data: null })),
      ]);
      setConfig(cfgRes.data);
      setStats(statsRes.data);
      setProducts(prodRes.data.products || []);
      setSlo(sloRes.data?.slo || null);
      setBundles(bundlesRes.data?.bundles || []);
      setCommissionPolicy(policyRes.data || null);
    } catch (e) {
      console.error('IAP load error:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const runScenarioSimulation = useCallback(async () => {
    setSimulating(true);
    try {
      const { data } = await api.post('/iap/admin/simulate-production-e2e', {
        email: 'realaicoach@gmail.com',
        plan: 'basic',
        period: 'monthly',
        platform: 'google',
        city: 'Oklahoma City',
        state_code: 'OK',
        country_code: 'US',
        postal_code: '73102',
        simulate_failure_case: true,
      });
      setSimulationResult(data || null);
      await loadData();
    } catch (e) {
      console.error('IAP simulation error:', e);
      setSimulationResult({ error: 'Simulation failed. Check backend logs.' });
    } finally {
      setSimulating(false);
    }
  }, [loadData]);

  const runSandboxValidation = useCallback(async () => {
    setSandboxRunning(true);
    try {
      const { data } = await api.post('/iap/admin/run-live-sandbox-validation', {});
      setSandboxResult(data || null);
      await loadData();
    } catch (e) {
      console.error('IAP sandbox validation error:', e);
      setSandboxResult({ error: 'Sandbox validation failed.' });
    } finally {
      setSandboxRunning(false);
    }
  }, [loadData]);

  const runRetryCycle = useCallback(async () => {
    setRetrying(true);
    try {
      const { data } = await api.post('/iap/admin/retry-webhooks');
      setRetryResult(data || null);
      await loadData();
    } catch (e) {
      console.error('IAP retry cycle error:', e);
      setRetryResult({ error: 'Retry cycle failed.' });
    } finally {
      setRetrying(false);
    }
  }, [loadData]);

  const runHealthDrillNow = useCallback(async () => {
    setDrillRunning(true);
    try {
      const { data } = await api.post('/iap/admin/run-health-drill');
      setDrillResult(data || null);
      await loadData();
    } catch (e) {
      console.error('IAP health drill error:', e);
      setDrillResult({ error: 'Health drill failed.' });
    } finally {
      setDrillRunning(false);
    }
  }, [loadData]);

  const setProviderTier = (provider: 'apple' | 'google', tier: 'reduced' | 'standard') => {
    setCommissionPolicy((prev: any) => ({
      ...(prev || {}),
      providers: {
        ...(prev?.providers || {}),
        [provider]: {
          ...(prev?.providers?.[provider] || {}),
          default_tier: tier,
        },
      },
    }));
  };

  const saveCommissionPolicy = useCallback(async () => {
    if (!commissionPolicy) return;
    setSavingPolicy(true);
    try {
      const { data } = await api.put('/iap/admin/commission-policy', {
        providers: commissionPolicy.providers,
        segment_rules: commissionPolicy.segment_rules || [],
      });
      setCommissionPolicy(data || null);
      await loadData();
    } catch (e) {
      console.error('IAP commission policy save error:', e);
    } finally {
      setSavingPolicy(false);
    }
  }, [commissionPolicy, loadData]);

  const downloadBundlePdf = async (transactionId: string) => {
    try {
      const base = (api.defaults.baseURL || '').replace(/\/$/, '');
      await Linking.openURL(`${base}/iap/admin/compliance-bundles/${transactionId}/receipt.pdf`);
    } catch (e) {
      console.error('IAP bundle download error:', e);
    }
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /><Text style={{ color: T.textMuted, fontSize: 12, marginTop: 8 }}>{tx('iapManagement.states.loading', 'Loading IAP data...')}</Text></View>;

  const tabs = [
    { id: 'overview', label: tx('iapManagement.tabs.overview', 'Overview'), icon: 'grid-outline' },
    { id: 'transactions', label: tx('iapManagement.tabs.transactions', 'Transactions'), icon: 'receipt-outline' },
    { id: 'webhooks', label: tx('iapManagement.tabs.webhooks', 'Webhooks'), icon: 'git-branch-outline' },
    { id: 'slo', label: tx('iapManagement.tabs.slo', 'SLO'), icon: 'pulse-outline' },
    { id: 'bundles', label: tx('iapManagement.tabs.bundles', 'Bundles'), icon: 'archive-outline' },
    { id: 'config', label: tx('iapManagement.tabs.configuration', 'Configuration'), icon: 'settings-outline' },
  ] as const;

  const platformIcon = (p: string) => p === 'apple' ? 'logo-apple' : 'logo-google-playstore';
  const appleNeutral = colors.textDim || T.textMuted;
  const platformColor = (p: string) => p === 'apple' ? appleNeutral : T.success;
  const statusColor = (st: string) => st === 'active' ? T.success : st === 'expired' ? T.error : T.warning;

  return (
    <View style={s.panel} data-testid="iap-management-panel" testID="iap-management-panel">
      <View style={[s.panelHeader, { marginBottom: 16 }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: T.purpleSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="phone-portrait-outline" size={18} color={T.purpleText} />
          </View>
          <View>
            <Text style={s.panelTitle}>{panelTitle === 'iapManagement.header.title' ? 'In-App Purchases' : panelTitle}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('iapManagement.header.subtitle', 'App Store & Google Play subscriptions')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <TouchableOpacity
            onPress={() => setShowAdvancedControls((prev) => !prev)}
            style={{ ...s.refreshBtn, width: 'auto', paddingHorizontal: 10, backgroundColor: T.bgSoft, borderColor: T.border }}
            data-testid="iap-toggle-advanced-controls"
            testID="iap-toggle-advanced-controls"
          >
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>
              {showAdvancedControls ? tx('iapManagement.actions.hideAdvanced', 'Hide Advanced') : tx('iapManagement.actions.showAdvanced', 'Advanced')}
            </Text>
          </TouchableOpacity>
          {showAdvancedControls && (
            <>
              <TouchableOpacity
                onPress={runScenarioSimulation}
                style={{ ...s.refreshBtn, width: 'auto', paddingHorizontal: 10, backgroundColor: T.primarySoft, borderColor: `${T.primary}66` }}
                data-testid="iap-run-production-simulation-button" testID="iap-run-production-simulation-button"
              >
                <Text style={{ color: T.primary, fontSize: 11, fontWeight: '700' }}>{simulating ? tx('iapManagement.actions.simulating', 'Simulating...') : tx('iapManagement.actions.runGoogleScenario', 'Run Google IAP Scenario')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={runSandboxValidation}
                style={{ ...s.refreshBtn, width: 'auto', paddingHorizontal: 10, backgroundColor: `${colors.info}22`, borderColor: `${colors.info}66` }}
                data-testid="iap-run-sandbox-validation-button" testID="iap-run-sandbox-validation-button"
              >
                <Text style={{ color: colors.info, fontSize: 11, fontWeight: '700' }}>{sandboxRunning ? tx('iapManagement.actions.validating', 'Validating...') : tx('iapManagement.actions.runSandboxValidation', 'Run Live Sandbox Validation')}</Text>
              </TouchableOpacity>
            </>
          )}
          <TouchableOpacity onPress={() => { setLoading(true); loadData(); }} style={s.refreshBtn} data-testid="iap-refresh-btn" testID="iap-refresh-btn">
            <Ionicons name="refresh" size={16} color={T.textSec} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 4, marginBottom: 16, flexWrap: 'wrap' }}>
        {tabs.map(tab => (
          <TouchableOpacity
            key={tab.id}
            onPress={() => setActiveTab(tab.id)}
            style={[s.periodTab, activeTab === tab.id && s.periodTabActive, { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, minWidth: isCompact ? '48%' as any : undefined }]}
            data-testid={`iap-tab-${tab.id}`} testID={`iap-tab-${tab.id}`}
          >
            <Ionicons name={tab.icon} size={14} color={activeTab === tab.id ? T.primary : T.textMuted} />
            <Text style={[s.periodLabel, activeTab === tab.id && s.periodLabelActive]}>{tab.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <View style={{ gap: 16 }}>
          {simulationResult && (
            <View style={[s.panel, { backgroundColor: T.bgSoft }]} data-testid="iap-simulation-result-card" testID="iap-simulation-result-card">
              <Text style={[s.sectionLabel, { marginTop: 0 }]}>{tx('admin.iAPManagementPanel.auto.text.001', 'Production-like Google IAP Simulation')}</Text>
              {simulationResult.error ? (
                <Text style={{ color: T.error, fontSize: 11 }}>{simulationResult.error}</Text>
              ) : (
                <>
                  <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 8 }}>
                    Scenario: {simulationResult?.scenario?.email} • {simulationResult?.scenario?.plan} ({simulationResult?.scenario?.period}) • {simulationResult?.scenario?.platform}
                  </Text>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>Base ${Number(simulationResult?.pricing_breakdown?.base_plan_price || 0).toFixed(2)} • Fee ${Number(simulationResult?.pricing_breakdown?.platform_fee || 0).toFixed(2)} • Tax ${Number(simulationResult?.pricing_breakdown?.taxes || 0).toFixed(2)} • Total ${Number(simulationResult?.pricing_breakdown?.final_total || 0).toFixed(2)}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>Latency: {simulationResult?.notification_latency_ms ?? 'N/A'}ms • Active: {String(simulationResult?.checks?.subscription_active)}</Text>
                </>
              )}
            </View>
          )}

          {/* KPIs */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {[
              { label: 'Apple Subscribers', value: stats?.active_apple_subscribers ?? 0, icon: 'logo-apple', color: appleNeutral },
              { label: 'Google Subscribers', value: stats?.active_google_subscribers ?? 0, icon: 'logo-google-playstore', color: T.successText },
              { label: 'Total Transactions', value: stats?.total_transactions ?? 0, icon: 'receipt-outline', color: T.primary },
              { label: 'Estimated MRR', value: `$${(stats?.estimated_mrr ?? 0).toFixed(2)}`, icon: 'trending-up', color: T.cyan },
            ].map((kpi, i) => (
              <View key={i} style={[s.kpiCard, { flex: 1, minWidth: 160, borderLeftColor: kpi.color, borderLeftWidth: 3 }]} data-testid={`iap-kpi-${i}`} testID={`iap-kpi-${i}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name={kpi.icon as any} size={16} color={kpi.color} />
                  <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '600', textTransform: 'uppercase' }}>{kpi.label}</Text>
                </View>
                <Text style={{ color: T.text, fontSize: 26, fontWeight: '700', marginTop: 6 }}>{kpi.value}</Text>
              </View>
            ))}
          </View>

          <View style={[s.panel, { backgroundColor: colors.card }]} data-testid="iap-overview-slo-card" testID="iap-overview-slo-card">
            <Text style={s.sectionLabel}>{tx('admin.iAPManagementPanel.auto.text.002', 'Webhook Reliability (24h)')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11 }}>Total {slo?.total_webhooks || 0} • Errors {slo?.error_count || 0} ({Number(slo?.error_rate_pct || 0).toFixed(2)}%)</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Latency Avg {slo?.latency_avg_ms || 0}ms • P95 {slo?.latency_p95_ms || 0}ms • Retry Pending {slo?.retry_queue_pending || 0}</Text>
          </View>

          {sandboxResult && (
            <View style={[s.panel, { backgroundColor: colors.surface || colors.card }]} data-testid="iap-sandbox-result-card" testID="iap-sandbox-result-card">
              <Text style={s.sectionLabel}>{tx('admin.iAPManagementPanel.auto.text.003', 'Live Sandbox Validation')}</Text>
              {sandboxResult.error ? (
                <Text style={{ color: T.error, fontSize: 11 }}>{sandboxResult.error}</Text>
              ) : (
                <>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>Apple: {sandboxResult?.apple?.executed ? (sandboxResult?.apple?.valid ? 'VALID' : `INVALID (${sandboxResult?.apple?.detail})`) : 'SKIPPED'}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>Google: {sandboxResult?.google?.executed ? (sandboxResult?.google?.valid ? 'VALID' : `INVALID (${sandboxResult?.google?.detail})`) : 'SKIPPED'}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Credentials — Apple key: {String(sandboxResult?.credentials_detected?.apple_key_path)} • Google SA: {String(sandboxResult?.credentials_detected?.google_service_account)}</Text>
                </>
              )}
            </View>
          )}

          {/* Platform Breakdown */}
          {stats?.platform_breakdown?.length > 0 && (
            <View style={[s.panel, { backgroundColor: T.bgSoft }]}>
              <Text style={[s.sectionLabel, { marginTop: 0 }]}>{tx('admin.iAPManagementPanel.auto.text.004', 'Platform Breakdown')}</Text>
              <View style={{ gap: 8 }}>
                {stats.platform_breakdown.map((item: any, i: number) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: T.card, padding: 10, borderRadius: 8 }}>
                    <Ionicons name={platformIcon(item.platform)} size={18} color={platformColor(item.platform)} />
                    <Text style={{ color: T.text, fontSize: 13, flex: 1 }}>{item.platform === 'apple' ? 'Apple' : 'Google'} - {item.plan}</Text>
                    <Text style={{ color: T.primary, fontSize: 16, fontWeight: '700' }}>{item.count}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* Products */}
          <View style={[s.panel, { backgroundColor: T.bgSoft }]}>
            <Text style={[s.sectionLabel, { marginTop: 0 }]}>{tx('admin.iAPManagementPanel.auto.text.005', 'IAP Products')}</Text>
            <View style={{ gap: 8 }}>
              {products.map((p, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: T.card, padding: 12, borderRadius: 8, borderWidth: 1, borderColor: T.border }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: p.plan === 'premium' ? T.purple : T.primary }} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{p.display_name}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>{p.product_id}</Text>
                  </View>
                  <Text style={{ color: T.successText, fontSize: 15, fontWeight: '700' }}>${p.price}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      )}

      {/* Transactions Tab */}
      {activeTab === 'transactions' && (
        <View style={{ gap: 12 }}>
          {(!stats?.recent_transactions || stats.recent_transactions.length === 0) ? (
            <View style={s.placeholderWrap}>
              <Ionicons name="receipt-outline" size={40} color={T.textMuted} />
              <Text style={s.placeholderText}>{tx('admin.iAPManagementPanel.auto.text.006', 'No IAP transactions yet')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{tx('admin.iAPManagementPanel.auto.text.007', 'Transactions will appear here when users make in-app purchases')}</Text>
            </View>
          ) : isCompact ? (
            <View style={{ gap: 8 }} data-testid="iap-transactions-compact-list" testID="iap-transactions-compact-list">
              {stats.recent_transactions.map((tx: any, i: number) => (
                <View key={i} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10, backgroundColor: T.card }} data-testid={`iap-tx-row-${i}`} testID={`iap-tx-row-${i}`}>
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{tx.user_id}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Ionicons name={platformIcon(tx.platform)} size={14} color={platformColor(tx.platform)} />
                      <Text style={{ color: T.textSec, fontSize: 11 }}>{tx.platform}</Text>
                    </View>
                    <View style={[s.planBadge, { backgroundColor: tx.plan === 'premium' ? T.purpleSoft : T.primarySoft }]}>
                      <Text style={[s.planText, { color: tx.plan === 'premium' ? T.purple : T.primary }]}>{tx.plan}</Text>
                    </View>
                    <View style={[s.statusTag, { backgroundColor: (globalThis as any).__alphaColor(statusColor(tx.status), '18') }]}>
                      <Text style={{ color: statusColor(tx.status), fontSize: 11, fontWeight: '600' }}>{tx.status}</Text>
                    </View>
                  </View>
                  <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 6 }}>{tx.created_at ? new Date(tx.created_at).toLocaleDateString() : '-'}</Text>
                </View>
              ))}
            </View>
          ) : (
            <>
              <View style={[s.tableHeader, { paddingHorizontal: 12 }]}>
                <Text style={[s.th, { flex: 1 }]}>{tx('admin.iAPManagementPanel.auto.text.008', 'User')}</Text>
                <Text style={[s.th, { width: 80 }]}>{tx('admin.iAPManagementPanel.auto.text.009', 'Platform')}</Text>
                <Text style={[s.th, { width: 80 }]}>{tx('admin.iAPManagementPanel.auto.text.010', 'Plan')}</Text>
                <Text style={[s.th, { width: 80 }]}>{tx('admin.iAPManagementPanel.auto.text.011', 'Status')}</Text>
                <Text style={[s.th, { width: 120 }]}>{tx('admin.iAPManagementPanel.auto.text.012', 'Date')}</Text>
              </View>
              {stats.recent_transactions.map((tx: any, i: number) => (
                <View key={i} style={[s.tableRow, { paddingHorizontal: 12 }]} data-testid={`iap-tx-row-${i}`} testID={`iap-tx-row-${i}`}>
                  <Text style={[s.td, { flex: 1 }]} numberOfLines={1}>{tx.user_id}</Text>
                  <View style={{ width: 80, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <Ionicons name={platformIcon(tx.platform)} size={14} color={platformColor(tx.platform)} />
                    <Text style={s.td}>{tx.platform}</Text>
                  </View>
                  <View style={{ width: 80 }}>
                    <View style={[s.planBadge, { backgroundColor: tx.plan === 'premium' ? T.purpleSoft : T.primarySoft }]}>
                      <Text style={[s.planText, { color: tx.plan === 'premium' ? T.purple : T.primary }]}>{tx.plan}</Text>
                    </View>
                  </View>
                  <View style={{ width: 80 }}>
                    <View style={[s.statusTag, { backgroundColor: (globalThis as any).__alphaColor(statusColor(tx.status), '18') }]}>
                      <Text style={{ color: statusColor(tx.status), fontSize: 11, fontWeight: '600' }}>{tx.status}</Text>
                    </View>
                  </View>
                  <Text style={[s.td, { width: 120, fontSize: 11 }]}>{tx.created_at ? new Date(tx.created_at).toLocaleDateString() : '-'}</Text>
                </View>
              ))}
            </>
          )}
        </View>
      )}

      {/* Webhooks Tab */}
      {activeTab === 'webhooks' && (
        <View style={{ gap: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <TouchableOpacity onPress={runRetryCycle} style={{ ...s.refreshBtn, width: 'auto', paddingHorizontal: 10 }} data-testid="iap-retry-webhooks-button" testID="iap-retry-webhooks-button">
              <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{retrying ? 'Retrying...' : 'Run Retry Cycle'}</Text>
            </TouchableOpacity>
            {retryResult ? <Text style={{ color: T.textMuted, fontSize: 11 }}>Processed {retryResult?.processed || 0} • Failed {retryResult?.failed || 0} • Pending {retryResult?.pending_backlog || 0}</Text> : null}
          </View>

          {(!stats?.recent_webhooks || stats.recent_webhooks.length === 0) ? (
            <View style={s.placeholderWrap}>
              <Ionicons name="git-branch-outline" size={40} color={T.textMuted} />
              <Text style={s.placeholderText}>{tx('admin.iAPManagementPanel.auto.text.013', 'No webhook notifications yet')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{tx('admin.iAPManagementPanel.auto.text.014', 'S2S notifications from Apple and Google will appear here')}</Text>
            </View>
          ) : isCompact ? (
            <View style={{ gap: 8 }} data-testid="iap-webhooks-compact-list" testID="iap-webhooks-compact-list">
              {stats.recent_webhooks.map((wh: any, i: number) => (
                <View key={i} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10, backgroundColor: T.card }} data-testid={`iap-webhook-row-${i}`} testID={`iap-webhook-row-${i}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Ionicons name={platformIcon(wh.platform)} size={14} color={platformColor(wh.platform)} />
                      <Text style={{ color: T.textSec, fontSize: 11 }}>{wh.platform}</Text>
                    </View>
                    <Ionicons name={wh.processed ? 'checkmark-circle' : 'time-outline'} size={16} color={wh.processed ? T.success : T.warning} />
                  </View>
                  <Text style={{ color: T.text, fontSize: 12, marginTop: 6 }} numberOfLines={2}>{wh.notification_type}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 6 }}>{wh.created_at ? new Date(wh.created_at).toLocaleDateString() : '-'}</Text>
                </View>
              ))}
            </View>
          ) : (
            <>
              <View style={[s.tableHeader, { paddingHorizontal: 12 }]}>
                <Text style={[s.th, { width: 80 }]}>{tx('admin.iAPManagementPanel.auto.text.015', 'Platform')}</Text>
                <Text style={[s.th, { flex: 1 }]}>{tx('admin.iAPManagementPanel.auto.text.016', 'Type')}</Text>
                <Text style={[s.th, { width: 80 }]}>{tx('admin.iAPManagementPanel.auto.text.017', 'Processed')}</Text>
                <Text style={[s.th, { width: 120 }]}>{tx('admin.iAPManagementPanel.auto.text.018', 'Date')}</Text>
              </View>
              {stats.recent_webhooks.map((wh: any, i: number) => (
                <View key={i} style={[s.tableRow, { paddingHorizontal: 12 }]} data-testid={`iap-webhook-row-${i}`} testID={`iap-webhook-row-${i}`}>
                  <View style={{ width: 80, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <Ionicons name={platformIcon(wh.platform)} size={14} color={platformColor(wh.platform)} />
                    <Text style={s.td}>{wh.platform}</Text>
                  </View>
                  <Text style={[s.td, { flex: 1 }]}>{wh.notification_type}</Text>
                  <View style={{ width: 80 }}>
                    <Ionicons name={wh.processed ? 'checkmark-circle' : 'time-outline'} size={16} color={wh.processed ? T.success : T.warning} />
                  </View>
                  <Text style={[s.td, { width: 120, fontSize: 11 }]}>{wh.created_at ? new Date(wh.created_at).toLocaleDateString() : '-'}</Text>
                </View>
              ))}
            </>
          )}
        </View>
      )}

      {/* SLO Tab */}
      {activeTab === 'slo' && (
        <View style={s.panel} data-testid="iap-slo-panel" testID="iap-slo-panel">
          <Text style={s.sectionLabel}>{tx('admin.iAPManagementPanel.auto.text.019', 'SLO Dashboard (24h)')}</Text>
          {[
            { label: 'Total Webhooks', value: String(slo?.total_webhooks || 0) },
            { label: 'Error Rate', value: `${Number(slo?.error_rate_pct || 0).toFixed(2)}%` },
            { label: 'Latency Avg', value: `${slo?.latency_avg_ms || 0}ms` },
            { label: 'Latency P95', value: `${slo?.latency_p95_ms || 0}ms` },
            { label: 'Retry Pending', value: String(slo?.retry_queue_pending || 0) },
            { label: 'Retry Failed', value: String(slo?.retry_queue_failed || 0) },
          ].map((item) => (
            <View key={item.label} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: T.border }}>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{item.label}</Text>
              <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{item.value}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Compliance Bundles Tab */}
      {activeTab === 'bundles' && (
        <View style={s.panel} data-testid="iap-bundles-panel" testID="iap-bundles-panel">
          <Text style={s.sectionLabel}>{tx('admin.iAPManagementPanel.auto.text.020', 'Signed Compliance Bundles')}</Text>
          {(bundles || []).length === 0 ? (
            <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.iAPManagementPanel.auto.text.021', 'No archived bundles yet.')}</Text>
          ) : (
            bundles.map((bundle, idx) => (
              <View key={bundle.transaction_id || idx} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 10, marginBottom: idx < bundles.length - 1 ? 8 : 0 }}>
                <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{bundle.transaction_id}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{bundle.platform} • {bundle.plan}/{bundle.period} • {bundle.created_at}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>Compliance {bundle.compliance_audit_id || 'n/a'} • Fraud {bundle.fraud_audit_id || 'n/a'}</Text>
                <TouchableOpacity onPress={() => downloadBundlePdf(bundle.transaction_id)} data-testid={`iap-download-bundle-${bundle.transaction_id}`} testID={`iap-download-bundle-${bundle.transaction_id}`} style={{ marginTop: 8 }}>
                  <Text style={{ color: T.primary, fontSize: 11, fontWeight: '700' }}>{tx('admin.iAPManagementPanel.auto.text.022', 'Download Receipt PDF')}</Text>
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>
      )}

      {/* Config Tab */}
      {activeTab === 'config' && config && (
        <View style={{ gap: 16 }}>
          {/* Apple Config */}
          <View style={[s.panel, { backgroundColor: T.bgSoft }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <Ionicons name="logo-apple" size={22} color={appleNeutral} />
              <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.iAPManagementPanel.auto.text.023', 'Apple App Store')}</Text>
              <View style={[s.statusTag, { backgroundColor: config.apple.configured ? T.successSoft : T.errorSoft, marginLeft: 'auto' }]}>
                <Text style={{ color: config.apple.configured ? T.success : T.error, fontSize: 11, fontWeight: '600' }}>
                  {config.apple.configured ? 'Connected' : 'Not Configured'}
                </Text>
              </View>
            </View>
            <View style={{ gap: 6 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.iAPManagementPanel.auto.text.024', 'Key ID')}</Text>
                <Text style={{ color: T.textSec, fontSize: 12, fontFamily: 'monospace' }}>{config.apple.key_id || 'N/A'}</Text>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.iAPManagementPanel.auto.text.025', 'Issuer ID')}</Text>
                <Text style={{ color: T.textSec, fontSize: 12, fontFamily: 'monospace' }}>{config.apple.issuer_id || 'N/A'}</Text>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.iAPManagementPanel.auto.text.026', 'Bundle ID')}</Text>
                <Text style={{ color: T.textSec, fontSize: 12, fontFamily: 'monospace' }}>{config.apple.bundle_id || 'N/A'}</Text>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.iAPManagementPanel.auto.text.027', 'Webhook URL')}</Text>
                <Text style={{ color: T.cyan, fontSize: 12, fontFamily: 'monospace' }}>{config.webhook_urls?.apple}</Text>
              </View>
            </View>
          </View>

          {/* Google Config */}
          <View style={[s.panel, { backgroundColor: T.bgSoft }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <Ionicons name="logo-google-playstore" size={22} color={T.successText} />
              <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>{tx('admin.iAPManagementPanel.auto.text.028', 'Google Play Store')}</Text>
              <View style={[s.statusTag, { backgroundColor: config.google.configured ? T.successSoft : T.errorSoft, marginLeft: 'auto' }]}>
                <Text style={{ color: config.google.configured ? T.success : T.error, fontSize: 11, fontWeight: '600' }}>
                  {config.google.configured ? 'Connected' : 'Not Configured'}
                </Text>
              </View>
            </View>
            <View style={{ gap: 6 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.iAPManagementPanel.auto.text.029', 'Package Name')}</Text>
                <Text style={{ color: T.textSec, fontSize: 12, fontFamily: 'monospace' }}>{config.google.package_name || 'N/A'}</Text>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.iAPManagementPanel.auto.text.030', 'Service Account')}</Text>
                <Text style={{ color: T.textSec, fontSize: 12, fontFamily: 'monospace' }}>{config.google.service_account}</Text>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.iAPManagementPanel.auto.text.031', 'Webhook URL')}</Text>
                <Text style={{ color: T.cyan, fontSize: 12, fontFamily: 'monospace' }}>{config.webhook_urls?.google}</Text>
              </View>
            </View>
          </View>

          {/* Products List */}
          <View style={[s.panel, { backgroundColor: T.bgSoft }]}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 10 }}>{tx('admin.iAPManagementPanel.auto.text.032', 'Registered Product IDs')}</Text>
            <View style={{ gap: 6 }}>
              {(config.products || []).map((pid: string, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 8, backgroundColor: T.card, borderRadius: 6 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: pid.includes('premium') ? T.purple : T.primary }} />
                  <Text style={{ color: T.textSec, fontSize: 12, fontFamily: 'monospace' }}>{pid}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* Commission Policy */}
          <View style={[s.panel, { backgroundColor: colors.card }]} data-testid="iap-commission-policy-card" testID="iap-commission-policy-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 8 }}>{tx('admin.iAPManagementPanel.auto.text.033', 'Adaptive Commission Policy')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 10 }}>{tx('admin.iAPManagementPanel.auto.text.034', 'Choose default commission tier per provider. Segment rules remain active in backend policy.')}</Text>
            {(['apple', 'google'] as const).map((provider) => {
              const tier = commissionPolicy?.providers?.[provider]?.default_tier || 'standard';
              return (
                <View key={provider} style={{ marginBottom: 8 }}>
                  <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 4 }}>{provider === 'apple' ? 'Apple App Store' : 'Google Play'} Tier</Text>
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    {(['reduced', 'standard'] as const).map((candidate) => (
                      <TouchableOpacity
                        key={candidate}
                        onPress={() => setProviderTier(provider, candidate)}
                        style={{ borderWidth: 1, borderColor: tier === candidate ? T.primary : T.border, backgroundColor: tier === candidate ? `${T.primary}20` : T.cardAlt, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }}
                        data-testid={`iap-${provider}-tier-${candidate}`} testID={`iap-${provider}-tier-${candidate}`}
                      >
                        <Text style={{ color: tier === candidate ? T.primary : T.textMuted, fontSize: 10, fontWeight: '700' }}>{candidate === 'reduced' ? 'Reduced (15%)' : 'Standard (30%)'}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              );
            })}
            <TouchableOpacity onPress={saveCommissionPolicy} style={{ ...s.refreshBtn, width: 'auto', paddingHorizontal: 12 }} data-testid="iap-save-commission-policy-button" testID="iap-save-commission-policy-button">
              <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{savingPolicy ? 'Saving...' : 'Save Commission Policy'}</Text>
            </TouchableOpacity>
          </View>

          {/* Nightly drill */}
          <View style={[s.panel, { backgroundColor: colors.surface || colors.card }]} data-testid="iap-health-drill-card" testID="iap-health-drill-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '700', marginBottom: 8 }}>{tx('admin.iAPManagementPanel.auto.text.035', 'Nightly IAP Health Drill')}</Text>
            <TouchableOpacity onPress={runHealthDrillNow} style={{ ...s.refreshBtn, width: 'auto', paddingHorizontal: 12 }} data-testid="iap-run-health-drill-button" testID="iap-run-health-drill-button">
              <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{drillRunning ? 'Running...' : 'Run Health Drill Now'}</Text>
            </TouchableOpacity>
            {drillResult ? <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>Latest drill: {drillResult?.report_id || 'completed'} • Platforms {(drillResult?.results || []).length}</Text> : null}
          </View>
        </View>
      )}
    </View>
  );
}
