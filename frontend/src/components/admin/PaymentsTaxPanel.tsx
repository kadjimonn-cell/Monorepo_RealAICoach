import React, { useCallback, useEffect, useMemo, useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { ActivityIndicator, Platform, ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { HeartbeatPulse } from '../common/HeartbeatPulse';
import { BillingGlossaryLabel } from '../payment/BillingGlossaryTooltip';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTheme } from '../../context/ThemeContext';
let Recharts: any = null;
if (Platform.OS === 'web') {
  Recharts = require('recharts');
}

// ── Static colors for module-level helpers ──
const T_STATIC = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  bgAlt: 'var(--app-card-muted)' as any,
  cardAlt: 'var(--app-card-muted)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textDim: 'var(--app-text-muted)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  finance: 'var(--app-primary)',
  success: 'var(--app-success)',
  warning: 'var(--app-warning)',
  error: 'var(--app-error)',
  cyan: 'var(--app-primary)',
};

const PERIODS = ['24h', '7d', '30d', '90d', '365d'];
const PROVIDERS = ['all', 'stripe', 'paypal', 'fedapay', 'apple', 'google'];
const SECTIONS = ['overview', 'ops-queue', 'reconciliation', 'disputes', 'forecasting', 'audit-report', 'audit-timeline', 'webhook-taxonomy'] as const;

const severityColor = (severity: string) => severity === 'high' ? T_STATIC.error : severity === 'medium' ? T_STATIC.warning : T_STATIC.success;
const statusColor = (status: string) => status === 'completed' ? T_STATIC.success : status === 'failed' ? T_STATIC.error : status === 'refunded' ? T_STATIC.warning : T_STATIC.cyan;

const formatMoney = (value: number, currency = 'USD') => `${currency} ${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const downloadBlob = (blob: Blob, filename: string) => {
  const href = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(href);
};

export default function PaymentsTaxPanel({ colors }: { colors: any }) {
  const { darkMode } = useTheme();
  const _AC = getAdminColors(darkMode);
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const panelTitle = t('paymentsTax.header.title');
  const panelSubtitle = t('paymentsTax.header.subtitle');
  const T: any = { ..._AC, cardAlt: _AC.bgAlt, textMuted: _AC.textDim, finance: 'var(--app-primary)', success: 'var(--app-success)', warning: 'var(--app-warning)', error: 'var(--app-error)', cyan: 'var(--app-primary)', successText: (_AC as any).successText || 'var(--app-success)', warningText: (_AC as any).warningText || 'var(--app-warning)', primaryText: (_AC as any).primaryText || 'var(--app-primary-text)' };
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const isWide = width >= 1200;
  const isCompact = width < 900;
  const [period, setPeriod] = useState('30d');
  const [activeSection, setActiveSection] = useState<typeof SECTIONS[number]>('overview');
  const [provider, setProvider] = useState('all');
  const [search, setSearch] = useState('');
  const [overview, setOverview] = useState<any>(null);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [transactionsLoading, setTransactionsLoading] = useState(false);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState<'csv' | 'pdf' | ''>('');
  const [selectedTx, setSelectedTx] = useState<any | null>(null);
  const [explanation, setExplanation] = useState<any | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState(Date.now());
  const [heartbeatSec, setHeartbeatSec] = useState(0);
  const [reconciliation, setReconciliation] = useState<any>(null);
  const [disputes, setDisputes] = useState<any>(null);
  const [opsQueue, setOpsQueue] = useState<any>(null);
  const [forecast, setForecast] = useState<any>(null);
  const [auditReferenceId, setAuditReferenceId] = useState('');
  const [auditReport, setAuditReport] = useState<any>(null);
  const [auditTimeline, setAuditTimeline] = useState<any>(null);
  const [selectedReconciliationRefs, setSelectedReconciliationRefs] = useState<string[]>([]);
  const [selectedDisputeRefs, setSelectedDisputeRefs] = useState<string[]>([]);
  const [selectedQueueRefs, setSelectedQueueRefs] = useState<string[]>([]);
  const [opsBusy, setOpsBusy] = useState(false);
  const [opsMessage, setOpsMessage] = useState('');
  const [timelineAckNote, setTimelineAckNote] = useState('');
  const [taxonomy, setTaxonomy] = useState<any>(null);
  const [autoTriggerPolicy, setAutoTriggerPolicy] = useState<any>(null);
  const [opsOwnerFilter, setOpsOwnerFilter] = useState('all');
  const [opsStatusFilter, setOpsStatusFilter] = useState('open');
  const [fallbackDrilldown, setFallbackDrilldown] = useState<any>(null);
  const [brandAudit, setBrandAudit] = useState<any>(null);
  const [scenarioCatalog, setScenarioCatalog] = useState<any[]>([]);
  const [scenarioBusyId, setScenarioBusyId] = useState('');
  const [scenarioMessage, setScenarioMessage] = useState('');

  const loadOverview = useCallback(async () => {
    const res = await api.get('/admin/payments-tax-intelligence/overview', { params: { period } });
    setOverview(res.data || null);
  }, [period]);

  const loadTransactions = useCallback(async () => {
    setTransactionsLoading(true);
    try {
      const res = await api.get('/admin/payments-tax-intelligence/transactions', {
        params: { period, provider, search, limit: 60 },
      });
      setTransactions(res.data?.transactions || []);
    } finally {
      setTransactionsLoading(false);
    }
  }, [period, provider, search]);

  const loadReconciliation = useCallback(async () => {
    const res = await api.get('/admin/payments-tax-intelligence/reconciliation', { params: { period } });
    setReconciliation(res.data || null);
  }, [period]);

  const loadDisputes = useCallback(async () => {
    const res = await api.get('/admin/payments-tax-intelligence/disputes', { params: { period } });
    setDisputes(res.data || null);
  }, [period]);

  const loadOpsQueue = useCallback(async () => {
    const res = await api.get('/admin/payments-tax-intelligence/ops-queue', {
      params: { period, owner: opsOwnerFilter, status: opsStatusFilter, limit: 80 },
    });
    setOpsQueue(res.data || null);
  }, [opsOwnerFilter, opsStatusFilter, period]);

  const loadForecast = useCallback(async () => {
    const res = await api.get('/admin/payments-tax-intelligence/forecast', { params: { period } });
    setForecast(res.data || null);
  }, [period]);

  const loadAuditReport = useCallback(async (referenceId?: string) => {
    const id = referenceId || auditReferenceId;
    if (!id) return;
    const res = await api.get(`/admin/payments-tax-intelligence/audit-report/${encodeURIComponent(id)}`);
    setAuditReport(res.data || null);
  }, [auditReferenceId]);

  const loadAuditTimeline = useCallback(async (referenceId?: string) => {
    const id = referenceId || auditReferenceId;
    if (!id) return;
    const res = await api.get(`/admin/payments-tax-intelligence/audit-timeline/${encodeURIComponent(id)}`);
    setAuditTimeline(res.data || null);
  }, [auditReferenceId]);

  const loadWebhookTaxonomy = useCallback(async () => {
    const res = await api.get('/admin/payments-tax-intelligence/webhook-taxonomy');
    setTaxonomy(res.data || null);
    setAutoTriggerPolicy(res.data?.auto_trigger_policy || null);
  }, []);

  const loadFallbackDrilldown = useCallback(async () => {
    const res = await api.get('/admin/payments-tax-intelligence/fallback-analytics/drilldown', { params: { period, limit: 40 } });
    setFallbackDrilldown(res.data || null);
  }, [period]);

  const loadBrandAudit = useCallback(async () => {
    const res = await api.get('/i18n/brand-protection/audit', { params: { limit: 24 } });
    setBrandAudit(res.data || null);
  }, []);

  const loadScenarioRunner = useCallback(async () => {
    const res = await api.get('/admin/payments-tax-intelligence/scenario-runner');
    setScenarioCatalog(res.data?.scenarios || []);
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const tasks = [loadOverview(), loadTransactions()];
      if (activeSection === 'overview') tasks.push(loadFallbackDrilldown(), loadBrandAudit(), loadScenarioRunner(), loadOpsQueue());
      if (activeSection === 'ops-queue') tasks.push(loadOpsQueue());
      if (activeSection === 'reconciliation') tasks.push(loadReconciliation());
      if (activeSection === 'disputes') tasks.push(loadDisputes());
      if (activeSection === 'forecasting') tasks.push(loadForecast());
      if (activeSection === 'audit-report' && auditReferenceId) tasks.push(loadAuditReport(auditReferenceId));
      if (activeSection === 'audit-timeline' && auditReferenceId) tasks.push(loadAuditTimeline(auditReferenceId));
      if (activeSection === 'webhook-taxonomy') tasks.push(loadWebhookTaxonomy());
      await Promise.all(tasks);
      setLastSyncAt(Date.now());
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Unable to load Payments & Tax Intelligence.');
    } finally {
      setLoading(false);
    }
  }, [activeSection, auditReferenceId, loadOverview, loadTransactions, loadFallbackDrilldown, loadBrandAudit, loadScenarioRunner, loadOpsQueue, loadReconciliation, loadDisputes, loadForecast, loadAuditReport, loadAuditTimeline, loadWebhookTaxonomy]);

  useEffect(() => { loadAll(); }, [loadAll]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/payments-tax/hybrid-refresh',
    onTick: loadAll,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  useEffect(() => {
    const interval = setInterval(() => setHeartbeatSec(Math.max(0, Math.floor((Date.now() - lastSyncAt) / 1000))), 1000);
    return () => clearInterval(interval);
  }, [lastSyncAt]);

  useEffect(() => {
    if (!auditReferenceId && transactions.length > 0) {
      const firstId = transactions[0]?.transaction_id || transactions[0]?.payment_id || transactions[0]?.session_id || '';
      if (firstId) setAuditReferenceId(firstId);
    }
  }, [transactions, auditReferenceId]);

  useEffect(() => {
    if (!auditReferenceId) return;
    if (activeSection === 'audit-report') {
      void loadAuditReport(auditReferenceId);
    }
    if (activeSection === 'audit-timeline') {
      void loadAuditTimeline(auditReferenceId);
    }
  }, [activeSection, auditReferenceId, loadAuditReport, loadAuditTimeline]);

  const handleExport = async (mode: 'csv' | 'pdf') => {
    setExporting(mode);
    try {
      const res = await api.get(`/admin/payments-tax-intelligence/export/${mode}`, {
        params: { period, provider, search },
        responseType: 'blob',
      });
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        downloadBlob(res.data as Blob, `payments-tax-intelligence-${period}.${mode}`);
      }
    } finally {
      setExporting('');
    }
  };

  const loadExplanation = async (tx: any) => {
    setSelectedTx(tx);
    setAuditReferenceId(tx?.transaction_id || tx?.payment_id || tx?.session_id || '');
    setExplanation(null);
    setExplaining(true);
    try {
      const id = tx?.transaction_id || tx?.payment_id || tx?.session_id;
      const res = await api.get(`/admin/payments-tax-intelligence/transaction/${encodeURIComponent(id)}/explain`);
      setExplanation(res.data || null);
    } catch (e: any) {
      setExplanation({ summary: e?.response?.data?.detail || 'Unable to explain transaction.' });
    } finally {
      setExplaining(false);
    }
  };

  const exportAudit = async (mode: 'csv' | 'pdf') => {
    if (!auditReferenceId) return;
    const res = await api.get(`/admin/payments-tax-intelligence/audit-report/${encodeURIComponent(auditReferenceId)}/${mode}`, {
      responseType: 'blob',
    });
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      downloadBlob(res.data as Blob, `payment-confirmation-audit-${auditReferenceId}.${mode}`);
    }
  };

  const toggleSelection = (section: 'reconciliation' | 'disputes' | 'ops-queue', referenceId: string) => {
    const setter = section === 'reconciliation'
      ? setSelectedReconciliationRefs
      : section === 'disputes'
        ? setSelectedDisputeRefs
        : setSelectedQueueRefs;
    setter((prev) => prev.includes(referenceId) ? prev.filter((item) => item !== referenceId) : [...prev, referenceId]);
  };

  const runOpsAction = async (section: 'reconciliation' | 'disputes' | 'ops-queue', action: 'retry_notifications' | 'replay_webhook' | 'assign_owner' | 'resolve_case') => {
    const refs = section === 'reconciliation'
      ? selectedReconciliationRefs
      : section === 'disputes'
        ? selectedDisputeRefs
        : selectedQueueRefs;
    if (!refs.length) {
      setOpsMessage(tx('paymentsTax.ops.selectReferenceFirst', 'Select at least one reference first.'));
      return;
    }
    setOpsBusy(true);
    setOpsMessage('');
    try {
      const res = await api.post('/admin/payments-tax-intelligence/ops/actions', {
        action,
        reference_ids: refs,
        owner_email: action === 'assign_owner' ? (user?.email || undefined) : undefined,
        note: action === 'resolve_case' ? 'Resolved from Payments & Tax panel' : undefined,
      });
      setOpsMessage(`${action.replace(/_/g, ' ')} completed for ${res.data?.total || refs.length} item(s).`);
      if (section === 'reconciliation') setSelectedReconciliationRefs([]);
      if (section === 'disputes') setSelectedDisputeRefs([]);
      if (section === 'ops-queue') setSelectedQueueRefs([]);
      await Promise.all([loadOpsQueue(), loadReconciliation(), loadDisputes(), loadTransactions()]);
    } catch (e: any) {
      setOpsMessage(e?.response?.data?.detail || tx('paymentsTax.ops.runActionFailed', 'Unable to run operator action.'));
    } finally {
      setOpsBusy(false);
    }
  };

  const runScenario = async (scenarioId: string) => {
    setScenarioBusyId(scenarioId);
    setScenarioMessage('');
    try {
      const res = await api.post(`/admin/payments-tax-intelligence/scenario-runner/${encodeURIComponent(scenarioId)}/run`);
      const run = res.data?.run;
      setScenarioMessage(`${run?.status === 'passed' ? tx('paymentsTax.scenario.passed', 'Scenario passed') : tx('paymentsTax.scenario.completedWithIssues', 'Scenario completed with issues')} — ${run?.scenario_id || scenarioId}`);
      await loadScenarioRunner();
    } catch (e: any) {
      setScenarioMessage(e?.response?.data?.detail || tx('paymentsTax.scenario.runFailed', 'Unable to run scenario replay.'));
    } finally {
      setScenarioBusyId('');
    }
  };

  const acknowledgeTimeline = async () => {
    if (!auditReferenceId) return;
    setOpsBusy(true);
    try {
      await api.post(`/admin/payments-tax-intelligence/audit-timeline/${encodeURIComponent(auditReferenceId)}/acknowledge`, {
        note: timelineAckNote || 'Acknowledged from Payments & Tax timeline',
      });
      setTimelineAckNote('');
      await loadAuditTimeline(auditReferenceId);
      setOpsMessage(tx('paymentsTax.timeline.acknowledged', 'Timeline acknowledged.'));
    } catch (e: any) {
      setOpsMessage(e?.response?.data?.detail || tx('paymentsTax.timeline.acknowledgeFailed', 'Unable to acknowledge timeline.'));
    } finally {
      setOpsBusy(false);
    }
  };

  const saveAutoTriggerPolicy = async (enabled: boolean) => {
    setOpsBusy(true);
    try {
      const res = await api.put('/admin/payments-tax-intelligence/webhook-auto-trigger-policy', {
        enabled,
        dead_threshold: autoTriggerPolicy?.dead_threshold || 5,
        replay_limit: autoTriggerPolicy?.replay_limit || 30,
      });
      setAutoTriggerPolicy(res.data?.policy || null);
      await loadWebhookTaxonomy();
      setOpsMessage(tx('paymentsTax.autoTrigger.updated', 'Auto-trigger policy updated.'));
    } catch (e: any) {
      setOpsMessage(e?.response?.data?.detail || tx('paymentsTax.autoTrigger.updateFailed', 'Unable to update auto-trigger policy.'));
    } finally {
      setOpsBusy(false);
    }
  };

  const evaluateAutoTriggerPolicy = async () => {
    setOpsBusy(true);
    try {
      const res = await api.post('/admin/payments-tax-intelligence/webhook-auto-trigger-policy/evaluate');
      setOpsMessage(res.data?.triggered ? tx('paymentsTax.autoTrigger.executed', 'Dead-letter replay auto-trigger executed.') : tx('paymentsTax.autoTrigger.notMet', 'Auto-trigger conditions not met yet.'));
      await loadWebhookTaxonomy();
    } catch (e: any) {
      setOpsMessage(e?.response?.data?.detail || tx('paymentsTax.autoTrigger.evaluateFailed', 'Unable to evaluate auto-trigger policy.'));
    } finally {
      setOpsBusy(false);
    }
  };

  const chartData = overview?.trend || [];
  const topProtectedBrands = useMemo(() => {
    const brandMap: Record<string, number> = {};
    (brandAudit?.rows || []).forEach((row: any) => {
      (row?.violations || []).forEach((item: any) => {
        const key = String(item?.brand || 'Protected brand');
        brandMap[key] = (brandMap[key] || 0) + 1;
      });
    });
    return Object.entries(brandMap)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([brand, count]) => ({ brand, count }));
  }, [brandAudit]);
  const kpis = useMemo(() => {
    const data = overview?.kpis || {};
    return [
      { id: 'mrr', label: tx('paymentsTax.kpis.netRevenueMrr', 'Net Revenue (MRR)'), value: formatMoney(data.mrr || 0), sub: tx('paymentsTax.kpis.monthlyRecurringRevenue', 'Monthly recurring revenue'), color: T.finance },
      { id: 'arr', label: tx('paymentsTax.kpis.arr', 'ARR'), value: formatMoney(data.arr || 0), sub: tx('paymentsTax.kpis.annualizedRecurringRevenue', 'Annualized recurring revenue'), color: T.cyan },
      { id: 'ltv', label: tx('paymentsTax.kpis.ltv', 'LTV'), value: formatMoney(data.ltv || 0), sub: tx('paymentsTax.kpis.customerLifetimeValue', 'Customer lifetime value'), color: T.successText },
      { id: 'churn', label: tx('paymentsTax.kpis.churn', 'Churn'), value: `${Number(data.churn_rate || 0).toFixed(1)}%`, sub: tx('paymentsTax.kpis.currentChurnRate', 'Current churn rate'), color: T.warningText },
      { id: 'tax', label: tx('paymentsTax.kpis.taxLiability', 'Tax Liability'), value: formatMoney(data.tax_liability || 0), sub: tx('paymentsTax.kpis.estimatedTaxExposure', 'Estimated tax exposure'), color: colors.warningText },
      { id: 'health', label: tx('paymentsTax.kpis.financeHealth', 'Finance Health'), value: `${Number(data.finance_health_score || 0).toFixed(0)}`, sub: tx('paymentsTax.kpis.complianceOpsHealth', 'Compliance + ops health'), color: T.error },
    ];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overview, tx]);

  const sectionLabels: Record<typeof SECTIONS[number], string> = useMemo(() => ({
    overview: tx('paymentsTax.sections.overview', 'OVERVIEW'),
    'ops-queue': tx('paymentsTax.sections.opsQueue', 'OPS QUEUE'),
    reconciliation: tx('paymentsTax.sections.reconciliation', 'RECONCILIATION'),
    disputes: tx('paymentsTax.sections.disputes', 'DISPUTES'),
    forecasting: tx('paymentsTax.sections.forecasting', 'FORECASTING'),
    'audit-report': tx('paymentsTax.sections.auditReport', 'AUDIT REPORT'),
    'audit-timeline': tx('paymentsTax.sections.auditTimeline', 'AUDIT TIMELINE'),
    'webhook-taxonomy': tx('paymentsTax.sections.webhookTaxonomy', 'WEBHOOK TAXONOMY'),
  }), [tx]);

  if (loading && !overview) {
    return <View style={{ padding: 40, alignItems: 'center' }} data-testid="payments-tax-panel-loading" testID="payments-tax-panel-loading"><ActivityIndicator size="large" color={T.finance} /></View>;
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 32 }} data-testid="payments-tax-panel" testID="payments-tax-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, flexWrap: 'wrap', gap: 10 }}>
        <View>
          <Text style={{ fontSize: 22, fontWeight: '800', color: colors?.text || T.text }} data-testid="payments-tax-title" testID="payments-tax-title">{panelTitle === 'paymentsTax.header.title' ? 'Global Financial Intelligence' : panelTitle}</Text>
          <Text style={{ fontSize: 12, color: T.textMuted, marginTop: 4 }}>{panelSubtitle === 'paymentsTax.header.subtitle' ? 'Stripe, PayPal, FedaPay, Apple IAP, Google IAP — one realtime control center.' : panelSubtitle}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }} data-testid="payments-tax-live-badge" testID="payments-tax-live-badge">
            <View style={{ width: 8, height: 8, borderRadius: 8, backgroundColor: T.success }} />
            <Text style={{ color: T.successText, fontSize: 11, fontWeight: '800' }}>{tx('paymentsTax.header.liveSync', 'LIVE SYNC')}</Text>
          </View>
          <HeartbeatPulse tick={heartbeatSec} warningAfterSeconds={60} criticalAfterSeconds={120} dataTestId="payments-tax-heartbeat" testID="payments-tax-heartbeat">
            <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{heartbeatSec >= 120 ? tx('paymentsTax.header.heartbeat.criticalStale', 'Critical stale') : heartbeatSec >= 60 ? tx('paymentsTax.header.heartbeat.stale', 'Stale') : tx('paymentsTax.header.heartbeat.updated', 'Updated')} {heartbeatSec}s {tx('paymentsTax.header.heartbeat.ago', 'ago')}</Text>
          </HeartbeatPulse>
          <TouchableOpacity onPress={() => handleExport('csv')} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-export-csv-button" testID="payments-tax-export-csv-button"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{exporting === 'csv' ? tx('paymentsTax.header.exporting', 'Exporting...') : tx('paymentsTax.header.exportCsv', 'Export CSV')}</Text></TouchableOpacity>
          <TouchableOpacity onPress={() => handleExport('pdf')} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-export-pdf-button" testID="payments-tax-export-pdf-button"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{exporting === 'pdf' ? tx('paymentsTax.header.exporting', 'Exporting...') : tx('paymentsTax.header.exportPdf', 'Export PDF')}</Text></TouchableOpacity>
          <TouchableOpacity onPress={() => { void loadAll(); }} style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: T.finance, alignItems: 'center', justifyContent: 'center' }} data-testid="payments-tax-refresh-button" testID="payments-tax-refresh-button"><Ionicons name="refresh" size={16} color={T.primaryText} /></TouchableOpacity>
        </View>
      </View>

      {error ? <Text style={{ color: T.error, fontSize: 12, marginBottom: 12 }} data-testid="payments-tax-error" testID="payments-tax-error">{error}</Text> : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 18 }} data-testid="payments-tax-section-tabs" testID="payments-tax-section-tabs">
        {SECTIONS.map((section) => (
          <TouchableOpacity
            key={section}
            onPress={() => setActiveSection(section)}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: activeSection === section ? T.finance : T.border, backgroundColor: activeSection === section ? 'var(--app-primary-soft)' : T.card }}
            data-testid={`payments-tax-section-${section}`} testID={`payments-tax-section-${section}`}
          >
            <Text style={{ color: activeSection === section ? T.finance : T.textSec, fontSize: 11, fontWeight: '800' }}>{sectionLabels[section]}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {activeSection === 'overview' ? (
        <>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16, marginBottom: 20 }}>
        {kpis.map((item) => (
          <View key={item.id} style={{ flex: isWide ? 1 : undefined, minWidth: isWide ? 180 : '47%', backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid={`payments-tax-kpi-${item.id}`} testID={`payments-tax-kpi-${item.id}`}>
            <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>{item.label}</Text>
            <Text style={{ color: item.color, fontSize: 28, fontWeight: '800', marginTop: 10 }}>{item.value}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginTop: 6 }}>{item.sub}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        <View style={{ flex: 2, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-revenue-chart-card" testID="payments-tax-revenue-chart-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.paymentsTaxPanel.auto.text.001', 'Revenue / Tax / Fees Trend')}</Text>
          {Platform.OS === 'web' && Recharts ? (
            <View style={{ height: 280, width: '100%', minWidth: 320 }}>
              <Recharts.ResponsiveContainer width="99%" height={280}>
                <Recharts.AreaChart data={chartData}>
                  <Recharts.CartesianGrid strokeDasharray="3 3" stroke="var(--app-text)" />
                  <Recharts.XAxis dataKey="date" stroke="var(--app-text-muted)" />
                  <Recharts.YAxis stroke="var(--app-text-muted)" />
                  <Recharts.Tooltip />
                  <Recharts.Legend />
                  <Recharts.Area type="monotone" dataKey="revenue" stroke={T.finance} fill={'var(--app-primary-soft)'} />
                  <Recharts.Area type="monotone" dataKey="tax" stroke={T.warningText} fill={'var(--app-warning-soft)'} />
                  <Recharts.Area type="monotone" dataKey="fees" stroke={T.cyan} fill={'var(--app-primary-soft)'} />
                </Recharts.AreaChart>
              </Recharts.ResponsiveContainer>
            </View>
          ) : <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.paymentsTaxPanel.auto.text.002', 'Chart view is available on web.')}</Text>}
        </View>

        <View style={{ flex: 1, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-ai-insights-card" testID="payments-tax-ai-insights-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.paymentsTaxPanel.auto.text.003', 'AI Finance Brief')}</Text>
          <Text style={{ color: T.finance, fontSize: 13, fontWeight: '700' }} data-testid="payments-tax-ai-headline" testID="payments-tax-ai-headline">{overview?.ai_brief?.headline || 'No AI brief available yet.'}</Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 6 }}>Risk: {(overview?.ai_brief?.risk_level || 'medium').toUpperCase()}</Text>
          <View style={{ marginTop: 12, gap: 10 }}>
            {(overview?.ai_brief?.highlights || overview?.alerts || []).slice(0, 4).map((item: any, idx: number) => {
              const title = typeof item === 'string' ? 'Finance insight' : item.title;
              const message = typeof item === 'string' ? item : item.message;
              const color = severityColor(typeof item === 'string' ? 'medium' : item.severity || 'medium');
              return (
                <View key={`${title}-${idx}`} style={{ borderLeftWidth: 3, borderLeftColor: color, paddingLeft: 10 }} data-testid={`payments-tax-ai-insight-${idx}`} testID={`payments-tax-ai-insight-${idx}`}>
                  <Text style={{ color, fontSize: 11, fontWeight: '800' }}>{title}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11, marginTop: 2 }}>{message}</Text>
                </View>
              );
            })}
          </View>
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16, marginBottom: 20 }} data-testid="payments-tax-providers-card" testID="payments-tax-providers-card">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.paymentsTaxPanel.auto.text.004', 'Provider Operations')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {(overview?.provider_summaries || []).map((item: any) => (
            <View key={item.provider} style={{ minWidth: 170, flex: isWide ? 1 : undefined, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid={`payments-tax-provider-${item.provider.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`payments-tax-provider-${item.provider.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{item.provider}</Text>
              <Text style={{ color: statusColor(item.status), fontSize: 11, fontWeight: '700', marginTop: 4 }}>{String(item.status).toUpperCase()}</Text>
              <Text style={{ color: T.textSec, fontSize: 11, marginTop: 8 }}>Gross {formatMoney(item.gross || 0)}</Text>
              <Text style={{ color: T.textSec, fontSize: 11 }}>Tax {formatMoney(item.tax || 0)}</Text>
              <Text style={{ color: T.textSec, fontSize: 11 }}>Success {Number(item.success_rate || 0).toFixed(1)}%</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16, marginBottom: 20 }} data-testid="payments-tax-ops-overview-card" testID="payments-tax-ops-overview-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.005', 'Finance Ops Queue')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{tx('admin.paymentsTaxPanel.auto.text.006', 'SLA-aware inbox for disputes, reconciliation gaps, and operator follow-ups.')}</Text>
          </View>
          <TouchableOpacity onPress={() => setActiveSection('ops-queue')} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-open-ops-queue-button" testID="payments-tax-open-ops-queue-button">
            <Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.007', 'Open Queue')}</Text>
          </TouchableOpacity>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 12 }}>
          {[
            { id: 'open', label: 'Open Cases', value: opsQueue?.summary?.open_cases || 0, color: T.text },
            { id: 'breached', label: 'Breached SLA', value: opsQueue?.summary?.breached || 0, color: T.error },
            { id: 'due-soon', label: 'Due Soon', value: opsQueue?.summary?.due_soon || 0, color: T.warningText },
            { id: 'my-inbox', label: 'Assigned to Me', value: opsQueue?.summary?.assigned_to_me || 0, color: T.cyan },
          ].map((item) => (
            <View key={item.id} style={{ minWidth: 170, flex: isWide ? 1 : undefined, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid={`payments-tax-ops-overview-${item.id}`} testID={`payments-tax-ops-overview-${item.id}`}>
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
              <Text style={{ color: item.color, fontSize: 24, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16, marginBottom: 20 }} data-testid="payments-tax-fallback-analytics-card" testID="payments-tax-fallback-analytics-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
          <View>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.008', 'FedaPay → Stripe Fallback Analytics')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{tx('admin.paymentsTaxPanel.auto.text.009', 'Drilldown shows each fallback reason, final conversion outcome, and recovered revenue.')}</Text>
          </View>
          <TouchableOpacity onPress={() => { void loadFallbackDrilldown(); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-fallback-drilldown-refresh" testID="payments-tax-fallback-drilldown-refresh">
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.010', 'Refresh Drilldown')}</Text>
          </TouchableOpacity>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
          {[
            { id: 'count', label: 'Fallback Count', value: String(overview?.fallback_analytics?.fallback_total || 0), color: T.warningText },
            { id: 'conversion', label: 'Fallback Conversion', value: `${Number(overview?.fallback_analytics?.fallback_conversion_rate || 0).toFixed(1)}%`, color: T.successText },
            { id: 'revenue', label: 'Recovered Revenue', value: formatMoney(overview?.fallback_analytics?.fallback_revenue || 0), color: T.finance },
          ].map((item) => (
            <View key={item.id} style={{ minWidth: 180, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid={`payments-tax-fallback-${item.id}`} testID={`payments-tax-fallback-${item.id}`}>
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
              <Text style={{ color: item.color, fontSize: 20, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
            </View>
          ))}
        </View>
        <View style={{ gap: 8 }}>
          {(overview?.fallback_analytics?.recent_reasons || []).slice(0, 4).map((item: any, idx: number) => (
            <View key={`${item.payment_id || item.transaction_id}-${idx}`} style={{ borderLeftWidth: 3, borderLeftColor: T.warning, paddingLeft: 10 }} data-testid={`payments-tax-fallback-reason-${idx}`} testID={`payments-tax-fallback-reason-${idx}`}>
              <Text style={{ color: T.textSec, fontSize: 11 }}>{item.fedapay_error || 'No recorded FedaPay error text'}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{item.created_at}</Text>
            </View>
          ))}
        </View>
        {!!fallbackDrilldown?.top_reasons?.length && (
          <View style={{ marginTop: 16, gap: 8 }} data-testid="payments-tax-fallback-top-reasons-panel" testID="payments-tax-fallback-top-reasons-panel">
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.011', 'Top Trigger Reasons')}</Text>
            {fallbackDrilldown.top_reasons.map((item: any, idx: number) => (
              <View key={`${item.reason}-${idx}`} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }} data-testid={`payments-tax-fallback-top-reason-${idx}`} testID={`payments-tax-fallback-top-reason-${idx}`}>
                <Text style={{ color: T.textSec, fontSize: 11, flex: 1 }}>{item.reason}</Text>
                <Text style={{ color: T.warningText, fontSize: 11, fontWeight: '800' }}>{item.count}</Text>
              </View>
            ))}
          </View>
        )}
        {!!fallbackDrilldown?.cases?.length && (
          <View style={{ marginTop: 16 }} data-testid="payments-tax-fallback-drilldown-cases-card" testID="payments-tax-fallback-drilldown-cases-card">
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.012', 'Fallback Case Drilldown')}</Text>
            {(fallbackDrilldown.cases || []).slice(0, 8).map((item: any, idx: number) => (
              <View key={`${item.reference_id}-${idx}`} style={{ paddingVertical: 10, borderBottomWidth: idx < Math.min((fallbackDrilldown.cases || []).length, 8) - 1 ? 1 : 0, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-fallback-case-${idx}`} testID={`payments-tax-fallback-case-${idx}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{item.reference_id}</Text>
                    <Text style={{ color: T.textSec, fontSize: 11, marginTop: 3 }}>{item.reason}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>{item.plan_id || 'plan'} • {item.billing_period || 'period'} • {item.created_at}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: item.converted ? T.success : T.warning, fontSize: 11, fontWeight: '800' }}>{item.final_provider} • {String(item.final_status).toUpperCase()}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>{formatMoney(item.total_amount || 0, item.currency || 'USD')}</Text>
                  </View>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>

      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 16, marginBottom: 20 }}>
        <View style={{ flex: 1, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-brand-protection-card" testID="payments-tax-brand-protection-card">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.013', 'Brand Protection Dashboard')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{tx('admin.paymentsTaxPanel.auto.text.014', 'Recent brand-name corrections from the translation safety system.')}</Text>
            </View>
            <Text style={{ color: T.finance, fontSize: 22, fontWeight: '800' }} data-testid="payments-tax-brand-protection-total" testID="payments-tax-brand-protection-total">{brandAudit?.total_recent || 0}</Text>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
            <View style={{ minWidth: 140, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid="payments-tax-brand-protection-violations" testID="payments-tax-brand-protection-violations">
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.paymentsTaxPanel.auto.text.015', 'Recent Violations')}</Text>
              <Text style={{ color: T.warningText, fontSize: 20, fontWeight: '800', marginTop: 8 }}>{brandAudit?.violations_recent || 0}</Text>
            </View>
            {topProtectedBrands.map((item) => (
              <View key={item.brand} style={{ minWidth: 120, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid={`payments-tax-brand-protection-brand-${item.brand.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`payments-tax-brand-protection-brand-${item.brand.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.brand}</Text>
                <Text style={{ color: T.text, fontSize: 18, fontWeight: '800', marginTop: 8 }}>{item.count}</Text>
              </View>
            ))}
          </View>
          <View style={{ marginTop: 12, gap: 8 }}>
            {(brandAudit?.rows || []).slice(0, 4).map((row: any, idx: number) => (
              <View key={`${row.audit_id || row.created_at}-${idx}`} style={{ borderLeftWidth: 3, borderLeftColor: row?.violations?.length ? T.warning : T.success, paddingLeft: 10 }} data-testid={`payments-tax-brand-audit-row-${idx}`} testID={`payments-tax-brand-audit-row-${idx}`}>
                <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{String(row?.source_text || '').slice(0, 90) || 'Protected brand check'}</Text>
                <Text style={{ color: T.textSec, fontSize: 10, marginTop: 3 }}>Lang {String(row?.target_lang || 'en').toUpperCase()} • Status {String(row?.status || 'clean').toUpperCase()}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>{row?.created_at}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flex: 1, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-scenario-runner-card" testID="payments-tax-scenario-runner-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.016', 'Reusable Scenario Runner')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{tx('admin.paymentsTaxPanel.auto.text.017', 'One-click replay for key payment scenarios and regression suites.')}</Text>
          {!!scenarioMessage ? <Text style={{ color: T.warningText, fontSize: 11, marginTop: 10 }} data-testid="payments-tax-scenario-runner-message" testID="payments-tax-scenario-runner-message">{scenarioMessage}</Text> : null}
          <View style={{ marginTop: 12, gap: 10 }}>
            {scenarioCatalog.slice(0, 5).map((scenario: any, idx: number) => (
              <View key={scenario.scenario_id} style={{ backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid={`payments-tax-scenario-item-${idx}`} testID={`payments-tax-scenario-item-${idx}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{scenario.label}</Text>
                    <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>{scenario.description}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{scenario.provider} • {scenario.jurisdiction} • {scenario.plan}</Text>
                    {scenario.latest_run ? (
                      <Text style={{ color: scenario.latest_run.status === 'passed' ? T.success : T.warning, fontSize: 10, marginTop: 6 }} data-testid={`payments-tax-scenario-last-run-${idx}`} testID={`payments-tax-scenario-last-run-${idx}`}>
                        Last run: {String(scenario.latest_run.status).toUpperCase()} • {scenario.latest_run.finished_at || scenario.latest_run.started_at}
                      </Text>
                    ) : null}
                  </View>
                  <TouchableOpacity onPress={() => { void runScenario(scenario.scenario_id); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid={`payments-tax-scenario-run-${scenario.scenario_id}`} testID={`payments-tax-scenario-run-${scenario.scenario_id}`}>
                    <Text style={{ color: T.primaryText, fontSize: 11, fontWeight: '800' }}>{scenarioBusyId === scenario.scenario_id ? 'Running...' : 'Run'}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-explorer-card" testID="payments-tax-explorer-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.018', 'Transaction Explorer')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {PERIODS.map((item) => (
              <TouchableOpacity key={item} onPress={() => setPeriod(item)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: period === item ? T.finance : T.border, backgroundColor: period === item ? 'var(--app-primary-soft)' : T.cardAlt }} data-testid={`payments-tax-period-${item}`} testID={`payments-tax-period-${item}`}><Text style={{ color: period === item ? T.finance : T.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text></TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 10, marginBottom: 12 }}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }} data-testid="payments-tax-provider-filter-scroll" testID="payments-tax-provider-filter-scroll">
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {PROVIDERS.map((item) => (
                <TouchableOpacity key={item} onPress={() => setProvider(item)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: provider === item ? T.cyan : T.border, backgroundColor: provider === item ? 'var(--app-primary-soft)' : T.cardAlt }} data-testid={`payments-tax-provider-filter-${item}`} testID={`payments-tax-provider-filter-${item}`}>
                  <Text style={{ color: provider === item ? T.cyan : T.textSec, fontSize: 11, fontWeight: '700' }}>{item.toUpperCase()}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
          <TextInput value={search} onChangeText={setSearch} placeholder={tx('admin.paymentsTaxPanel.auto.placeholder.001', 'Search tx / payment / user')} placeholderTextColor={T.textMuted} style={{ flex: 1, minWidth: isCompact ? undefined : 220, width: isCompact ? '100%' : undefined, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 10, color: T.text, paddingHorizontal: 12, paddingVertical: 10 }} data-testid="payments-tax-search-input" testID="payments-tax-search-input" />
          <TouchableOpacity onPress={() => { void loadTransactions(); }} style={{ paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-apply-filters-button" testID="payments-tax-apply-filters-button"><Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.019', 'Apply')}</Text></TouchableOpacity>
        </View>

        {transactionsLoading ? <ActivityIndicator color={T.finance} /> : (
          isWide ? (
            <ScrollView horizontal data-testid="payments-tax-transactions-scroll" testID="payments-tax-transactions-scroll">
              <View style={{ minWidth: 1120 }}>
                <View style={{ flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: T.border, paddingBottom: 8, marginBottom: 6 }}>
                  {['Status', 'ID', 'Provider', 'Amount', 'Tax', 'Jurisdiction', 'Lang', 'Notification', 'Risk'].map((label) => (
                    <Text key={label} style={{ width: label === 'ID' ? 210 : 120, color: T.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{label}</Text>
                  ))}
                </View>
                {transactions.map((row) => {
                  const jurisdiction = row?.jurisdiction || {};
                  return (
                    <TouchableOpacity key={`${row.transaction_id}-${row.created_at}`} onPress={() => { void loadExplanation(row); }} style={{ flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-row-${String(row.transaction_id || row.payment_id).slice(-8)}`} testID={`payments-tax-row-${String(row.transaction_id || row.payment_id).slice(-8)}`}>
                      <Text style={{ width: 120, color: statusColor(row.status), fontSize: 11, fontWeight: '800' }}>{String(row.status).toUpperCase()}</Text>
                      <Text style={{ width: 210, color: T.textSec, fontSize: 11, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>{row.transaction_id || row.payment_id}</Text>
                      <Text style={{ width: 120, color: T.text, fontSize: 11 }}>{row.provider}</Text>
                      <Text style={{ width: 120, color: T.text, fontSize: 11 }}>{formatMoney(row.total_amount, row.currency)}</Text>
                      <Text style={{ width: 120, color: T.warningText, fontSize: 11 }}>{formatMoney(row.tax_amount, row.currency)}</Text>
                      <Text style={{ width: 120, color: T.textSec, fontSize: 11 }}>{jurisdiction.country || '--'}{jurisdiction.state ? `-${jurisdiction.state}` : ''}</Text>
                      <Text style={{ width: 120, color: T.textSec, fontSize: 11 }}>{String(row.resolved_language || 'en').toUpperCase()}</Text>
                      <Text style={{ width: 120, color: row.notification_status === 'recovery_pending' ? T.warning : T.success, fontSize: 11 }}>{row.notification_status}</Text>
                      <Text style={{ width: 120, color: row.risk_score >= 70 ? T.error : row.risk_score >= 45 ? T.warning : T.success, fontSize: 11, fontWeight: '800' }}>{row.risk_score}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </ScrollView>
          ) : (
            <View style={{ gap: 8 }} data-testid="payments-tax-transactions-mobile-list" testID="payments-tax-transactions-mobile-list">
              {transactions.map((row, idx) => {
                const jurisdiction = row?.jurisdiction || {};
                const txKey = String(row.transaction_id || row.payment_id || row.created_at || idx);
                return (
                  <TouchableOpacity key={txKey} onPress={() => { void loadExplanation(row); }} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, backgroundColor: T.cardAlt, padding: 10, gap: 4 }} data-testid={`payments-tax-mobile-row-${String(txKey).slice(-8)}`} testID={`payments-tax-mobile-row-${String(txKey).slice(-8)}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text style={{ color: statusColor(row.status), fontSize: 11, fontWeight: '800' }}>{String(row.status).toUpperCase()}</Text>
                      <Text style={{ color: row.risk_score >= 70 ? T.error : row.risk_score >= 45 ? T.warning : T.success, fontSize: 11, fontWeight: '800' }}>Risk {row.risk_score}</Text>
                    </View>
                    <Text style={{ color: T.textSec, fontSize: 11, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }} numberOfLines={1}>{row.transaction_id || row.payment_id}</Text>
                    <Text style={{ color: T.text, fontSize: 11 }}>{row.provider} • {formatMoney(row.total_amount, row.currency)}</Text>
                    <Text style={{ color: T.warningText, fontSize: 11 }}>Tax {formatMoney(row.tax_amount, row.currency)}</Text>
                    <Text style={{ color: T.textSec, fontSize: 10 }}>{jurisdiction.country || '--'}{jurisdiction.state ? `-${jurisdiction.state}` : ''} • {String(row.resolved_language || 'en').toUpperCase()} • {row.notification_status}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          )
        )}
      </View>

      {(selectedTx || explanation) ? (
        <View style={{ marginTop: 20, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-explanation-card" testID="payments-tax-explanation-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.020', 'Transaction Explanation')}</Text>
          {explaining ? <ActivityIndicator color={T.finance} /> : (
            <>
              <Text style={{ color: T.textSec, fontSize: 12 }}>{explanation?.summary || 'Select a transaction row to inspect tax, language, FX, and notification status.'}</Text>
              {explanation?.tax_basis ? <Text style={{ color: T.warningText, fontSize: 11, marginTop: 8 }}>Tax Basis: {explanation.tax_basis}</Text> : null}
              {explanation?.localization ? <Text style={{ color: T.cyan, fontSize: 11, marginTop: 4 }}>Localization: {explanation.localization}</Text> : null}
              {explanation?.notification_status ? <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>Notification Status: {explanation.notification_status}</Text> : null}
            </>
          )}
        </View>
      ) : null}
        </>
      ) : null}

      {activeSection === 'ops-queue' ? (
        <View style={{ gap: 16 }} data-testid="payments-tax-ops-queue-panel" testID="payments-tax-ops-queue-panel">
          {!!opsMessage ? <Text style={{ color: T.warningText, fontSize: 11 }} data-testid="payments-tax-ops-queue-message" testID="payments-tax-ops-queue-message">{opsMessage}</Text> : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {[
              { id: 'open', label: 'Open Cases', value: opsQueue?.summary?.open_cases || 0, color: T.text },
              { id: 'assigned', label: 'Assigned to Me', value: opsQueue?.summary?.assigned_to_me || 0, color: T.cyan },
              { id: 'unassigned', label: 'Unassigned', value: opsQueue?.summary?.unassigned || 0, color: T.warningText },
              { id: 'breached', label: 'Breached SLA', value: opsQueue?.summary?.breached || 0, color: T.error },
            ].map((item) => (
              <View key={item.id} style={{ minWidth: 180, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid={`payments-tax-ops-queue-kpi-${item.id}`} testID={`payments-tax-ops-queue-kpi-${item.id}`}>
                <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                <Text style={{ color: item.color, fontSize: 26, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
              </View>
            ))}
          </View>

          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-ops-queue-filters-card" testID="payments-tax-ops-queue-filters-card">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.021', 'Owner Inbox + SLA Filters')}</Text>
              <TouchableOpacity onPress={() => { void loadOpsQueue(); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-ops-queue-refresh-button" testID="payments-tax-ops-queue-refresh-button"><Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.022', 'Refresh Queue')}</Text></TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
              {['all', 'me', 'unassigned'].map((item) => (
                <TouchableOpacity key={item} onPress={() => setOpsOwnerFilter(item)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: opsOwnerFilter === item ? T.finance : T.border, backgroundColor: opsOwnerFilter === item ? 'var(--app-primary-soft)' : T.cardAlt }} data-testid={`payments-tax-ops-owner-filter-${item}`} testID={`payments-tax-ops-owner-filter-${item}`}>
                  <Text style={{ color: opsOwnerFilter === item ? T.finance : T.textSec, fontSize: 11, fontWeight: '700' }}>{item.toUpperCase()}</Text>
                </TouchableOpacity>
              ))}
              {['open', 'breached', 'resolved', 'all'].map((item) => (
                <TouchableOpacity key={item} onPress={() => setOpsStatusFilter(item)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: opsStatusFilter === item ? T.cyan : T.border, backgroundColor: opsStatusFilter === item ? 'var(--app-primary-soft)' : T.cardAlt }} data-testid={`payments-tax-ops-status-filter-${item}`} testID={`payments-tax-ops-status-filter-${item}`}>
                  <Text style={{ color: opsStatusFilter === item ? T.cyan : T.textSec, fontSize: 11, fontWeight: '700' }}>{item.toUpperCase()}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
              <TouchableOpacity onPress={() => { void runOpsAction('ops-queue', 'assign_owner'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-ops-queue-assign-button" testID="payments-tax-ops-queue-assign-button"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.023', 'Assign to Me')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void runOpsAction('ops-queue', 'resolve_case'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }} data-testid="payments-tax-ops-queue-resolve-button" testID="payments-tax-ops-queue-resolve-button"><Text style={{ color: T.successText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.024', 'Bulk Resolve')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void runOpsAction('ops-queue', 'retry_notifications'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-ops-queue-retry-button" testID="payments-tax-ops-queue-retry-button"><Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{opsBusy ? 'Working...' : 'Retry Notifications'}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void runOpsAction('ops-queue', 'replay_webhook'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-ops-queue-replay-button" testID="payments-tax-ops-queue-replay-button"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.025', 'Replay Webhook')}</Text></TouchableOpacity>
            </View>
          </View>

          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-owner-inbox-card" testID="payments-tax-owner-inbox-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.026', 'Owner Inbox Summary')}</Text>
            {(opsQueue?.owner_summary || []).slice(0, 8).map((item: any, idx: number) => (
              <View key={`${item.owner_email}-${idx}`} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, paddingVertical: 8, borderBottomWidth: idx < Math.min((opsQueue?.owner_summary || []).length, 8) - 1 ? 1 : 0, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-owner-inbox-row-${idx}`} testID={`payments-tax-owner-inbox-row-${idx}`}>
                <Text style={{ width: 220, color: T.text, fontSize: 12, fontWeight: '700' }}>{item.owner_email}</Text>
                <Text style={{ width: 120, color: T.textSec, fontSize: 11 }}>Open {item.open_cases}</Text>
                <Text style={{ width: 120, color: T.error, fontSize: 11 }}>Breached {item.breached}</Text>
                <Text style={{ width: 120, color: T.warningText, fontSize: 11 }}>Due Soon {item.due_soon}</Text>
              </View>
            ))}
          </View>

          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-ops-queue-list-card" testID="payments-tax-ops-queue-list-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.027', 'Operations Queue')}</Text>
            {(opsQueue?.items || []).slice(0, 40).map((item: any, idx: number) => {
              const selected = selectedQueueRefs.includes(item.reference_id);
              const slaColor = item.sla_status === 'breached' ? T.error : item.sla_status === 'due_soon' ? T.warning : item.sla_status === 'resolved' ? T.success : T.cyan;
              return (
                <TouchableOpacity key={`${item.reference_id}-${idx}`} onPress={() => toggleSelection('ops-queue', item.reference_id)} style={{ paddingVertical: 12, borderBottomWidth: idx < Math.min((opsQueue?.items || []).length, 40) - 1 ? 1 : 0, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-ops-queue-item-${idx}`} testID={`payments-tax-ops-queue-item-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: selected ? T.finance : T.text, fontSize: 12, fontWeight: '800' }}>{selected ? '● ' : '○ '}{item.reference_id}</Text>
                      <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>{item.issue_summary}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{item.provider} • {String(item.queue_type).toUpperCase()} • Owner: {item.owner_email || 'Unassigned'} • {item.currency} {Number(item.amount || 0).toFixed(2)}</Text>
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={{ color: slaColor, fontSize: 11, fontWeight: '800' }}>{String(item.sla_status).toUpperCase()}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>Age {item.minutes_open}m</Text>
                      <Text style={{ color: T.textMuted, fontSize: 10 }}>Due {item.due_at}</Text>
                    </View>
                  </View>
                  {!!item.history?.length && (
                    <View style={{ marginTop: 8, gap: 4 }} data-testid={`payments-tax-ops-queue-history-${idx}`} testID={`payments-tax-ops-queue-history-${idx}`}>
                      {item.history.slice(-2).map((historyItem: any, historyIdx: number) => (
                        <Text key={`${historyItem.event_id || historyIdx}`} style={{ color: T.textMuted, fontSize: 10 }}>{historyItem.created_at} • {historyItem.actor_email} • {historyItem.action}</Text>
                      ))}
                    </View>
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      ) : null}

      {activeSection === 'reconciliation' ? (
        <View style={{ gap: 16 }} data-testid="payments-tax-reconciliation-panel" testID="payments-tax-reconciliation-panel">
          {!!opsMessage ? <Text style={{ color: T.warningText, fontSize: 11 }} data-testid="payments-tax-ops-message" testID="payments-tax-ops-message">{opsMessage}</Text> : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {[
              { id: 'scanned', label: 'Transactions Scanned', value: reconciliation?.summary?.transactions_scanned || 0 },
              { id: 'ledger', label: 'Ledger Gaps', value: reconciliation?.summary?.ledger_gaps || 0 },
              { id: 'notif', label: 'Recovery Pending', value: reconciliation?.summary?.notification_recovery_pending || 0 },
              { id: 'webhooks', label: 'Dead Webhooks', value: reconciliation?.summary?.fedapay_dead_webhooks || 0 },
            ].map((item) => (
              <View key={item.id} style={{ minWidth: 180, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid={`payments-tax-reconciliation-kpi-${item.id}`} testID={`payments-tax-reconciliation-kpi-${item.id}`}>
                <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                <Text style={{ color: T.text, fontSize: 26, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
              </View>
            ))}
          </View>
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.028', 'Provider Matrix')}</Text>
            {(reconciliation?.providers || []).map((item: any) => (
              <View key={item.provider} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-reconciliation-provider-${item.provider.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} testID={`payments-tax-reconciliation-provider-${item.provider.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                <Text style={{ width: 140, color: T.text, fontSize: 12, fontWeight: '700' }}>{item.provider}</Text>
                <Text style={{ width: 110, color: T.textSec, fontSize: 11 }}>Count {item.count}</Text>
                <Text style={{ width: 110, color: T.warningText, fontSize: 11 }}>Ledger {item.ledger_gaps}</Text>
                <Text style={{ width: 140, color: T.cyan, fontSize: 11 }}>Recovery {item.recovery_pending}</Text>
                <Text style={{ width: 140, color: T.textMuted, fontSize: 11 }}>Localization {item.localization_gaps}</Text>
              </View>
            ))}
          </View>
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-reconciliation-exceptions-card" testID="payments-tax-reconciliation-exceptions-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.029', 'Exception Queue')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <TouchableOpacity onPress={() => { void runOpsAction('reconciliation', 'retry_notifications'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-reconciliation-retry-button" testID="payments-tax-reconciliation-retry-button"><Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{opsBusy ? 'Working...' : 'Retry Notifications'}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void runOpsAction('reconciliation', 'replay_webhook'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-reconciliation-replay-button" testID="payments-tax-reconciliation-replay-button"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.030', 'Replay Webhook')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void runOpsAction('reconciliation', 'assign_owner'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-reconciliation-assign-button" testID="payments-tax-reconciliation-assign-button"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.031', 'Assign to Me')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void runOpsAction('reconciliation', 'resolve_case'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }} data-testid="payments-tax-reconciliation-resolve-button" testID="payments-tax-reconciliation-resolve-button"><Text style={{ color: T.successText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.032', 'Resolve')}</Text></TouchableOpacity>
            </View>
            {(reconciliation?.exceptions || []).slice(0, 30).map((item: any, idx: number) => {
              const ref = item.transaction_id;
              const selected = selectedReconciliationRefs.includes(ref);
              return (
                <TouchableOpacity key={`${ref}-${idx}`} onPress={() => toggleSelection('reconciliation', ref)} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-reconciliation-exception-${idx}`} testID={`payments-tax-reconciliation-exception-${idx}`}>
                  <Text style={{ color: selected ? T.finance : T.text, fontSize: 12, fontWeight: '800' }}>{selected ? '● ' : '○ '}{item.provider} • {item.status?.toUpperCase()} • {ref}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>Notification: {item.notification_status} • Owner: {item.ops_case?.owner_email || 'Unassigned'} • Case: {item.ops_case?.status || 'open'}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      ) : null}

      {activeSection === 'disputes' ? (
        <View style={{ gap: 16 }} data-testid="payments-tax-disputes-panel" testID="payments-tax-disputes-panel">
          {!!opsMessage ? <Text style={{ color: T.warningText, fontSize: 11 }} data-testid="payments-tax-disputes-ops-message" testID="payments-tax-disputes-ops-message">{opsMessage}</Text> : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {[
              { id: 'failed', label: 'Failed', value: disputes?.summary?.failed || 0, color: T.error },
              { id: 'refunded', label: 'Refunded', value: disputes?.summary?.refunded || 0, color: T.warningText },
              { id: 'disputed', label: 'Disputed', value: disputes?.summary?.disputed || 0, color: T.finance },
              { id: 'risk', label: 'High Risk', value: disputes?.summary?.high_risk || 0, color: T.cyan },
            ].map((item) => (
              <View key={item.id} style={{ minWidth: 180, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid={`payments-tax-disputes-kpi-${item.id}`} testID={`payments-tax-disputes-kpi-${item.id}`}>
                <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                <Text style={{ color: item.color, fontSize: 26, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
              </View>
            ))}
          </View>
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.033', 'Issue Queue')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <TouchableOpacity onPress={() => { void runOpsAction('disputes', 'assign_owner'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-disputes-assign-button" testID="payments-tax-disputes-assign-button"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.034', 'Assign to Me')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void runOpsAction('disputes', 'resolve_case'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }} data-testid="payments-tax-disputes-resolve-button" testID="payments-tax-disputes-resolve-button"><Text style={{ color: T.successText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.035', 'Resolve')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void runOpsAction('disputes', 'retry_notifications'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-disputes-retry-button" testID="payments-tax-disputes-retry-button"><Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{opsBusy ? 'Working...' : 'Retry Notifications'}</Text></TouchableOpacity>
            </View>
            {(disputes?.items || []).slice(0, 30).map((item: any, idx: number) => (
              <TouchableOpacity key={`${item.transaction_id}-${idx}`} onPress={() => toggleSelection('disputes', item.transaction_id)} style={{ paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-dispute-item-${idx}`} testID={`payments-tax-dispute-item-${idx}`}>
                <Text style={{ color: selectedDisputeRefs.includes(item.transaction_id) ? T.finance : statusColor(item.status), fontSize: 11, fontWeight: '800' }}>{selectedDisputeRefs.includes(item.transaction_id) ? '● ' : '○ '}{String(item.status).toUpperCase()} • {item.provider}</Text>
                <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>{item.diagnostic}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{item.transaction_id} • Owner: {item.ops_case?.owner_email || 'Unassigned'} • Case: {item.ops_case?.status || 'open'}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ) : null}

      {activeSection === 'forecasting' ? (
        <View style={{ gap: 16 }} data-testid="payments-tax-forecasting-panel" testID="payments-tax-forecasting-panel">
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.036', 'Scenario Forecast')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {Object.entries(forecast?.scenarios || {}).map(([key, value]: any) => (
                <View key={key} style={{ minWidth: 220, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 14 }} data-testid={`payments-tax-forecast-${key}`} testID={`payments-tax-forecast-${key}`}>
                  <Text style={{ color: T.finance, fontSize: 12, fontWeight: '800', textTransform: 'uppercase' }}>{key}</Text>
                  <Text style={{ color: T.text, fontSize: 18, fontWeight: '800', marginTop: 8 }}>{formatMoney(value.projected_30d_revenue || 0)}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>Tax {formatMoney(value.projected_30d_tax || 0)}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11 }}>Fees {formatMoney(value.projected_30d_fees || 0)}</Text>
                </View>
              ))}
            </View>
          </View>
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-forecast-ai-card" testID="payments-tax-forecast-ai-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{forecast?.ai_forecast?.headline || 'Forecast Commentary'}</Text>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{forecast?.ai_forecast?.commentary || forecast?.deterministic_commentary}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 8 }}>Risk: {(forecast?.ai_forecast?.risk_level || 'medium').toUpperCase()}</Text>
          </View>
        </View>
      ) : null}

      {activeSection === 'audit-report' ? (
        <View style={{ gap: 16 }} data-testid="payments-tax-audit-report-panel" testID="payments-tax-audit-report-panel">
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.037', 'Payment Confirmation Audit Report')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.038', 'Select a recent payment reference to inspect receipt, notification, and provider references.')}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} data-testid="payments-tax-audit-reference-scroll" testID="payments-tax-audit-reference-scroll">
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {transactions.slice(0, 10).map((row) => {
                  const id = row.transaction_id || row.payment_id || row.session_id;
                  return (
                    <TouchableOpacity key={id} onPress={() => { setAuditReferenceId(id); void loadAuditReport(id); }} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: auditReferenceId === id ? T.finance : T.border, backgroundColor: auditReferenceId === id ? 'var(--app-primary-soft)' : T.cardAlt }} data-testid={`payments-tax-audit-ref-${String(id).slice(-8)}`} testID={`payments-tax-audit-ref-${String(id).slice(-8)}`}>
                      <Text style={{ color: auditReferenceId === id ? T.finance : T.textSec, fontSize: 11, fontWeight: '700' }}>{String(id).slice(0, 14)}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </ScrollView>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
              <TouchableOpacity onPress={() => { void loadAuditReport(); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-audit-load-button" testID="payments-tax-audit-load-button"><Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.039', 'Load Report')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void exportAudit('csv'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-audit-export-csv" testID="payments-tax-audit-export-csv"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.040', 'Export CSV')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void exportAudit('pdf'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-audit-export-pdf" testID="payments-tax-audit-export-pdf"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.041', 'Export PDF')}</Text></TouchableOpacity>
            </View>
          </View>

          {auditReport ? (
            <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-audit-report-card" testID="payments-tax-audit-report-card">
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.paymentsTaxPanel.auto.text.042', 'Audit Snapshot')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
                {[
                  { id: 'receipt', label: 'Receipt Number', value: auditReport?.receipt_number || 'N/A' },
                  { id: 'ticket', label: 'Ticket ID', value: auditReport?.ticket_id || 'N/A' },
                  { id: 'customer-total', label: 'Customer Charge Total', value: formatMoney(auditReport?.customer_charge_total || 0, auditReport?.transaction?.currency || 'USD') },
                  { id: 'net-settlement', label: 'Net Settlement After Fee', value: formatMoney(auditReport?.net_settlement_after_fee || 0, auditReport?.transaction?.currency || 'USD') },
                ].map((item) => (
                  <View key={item.id} style={{ minWidth: 200, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid={`payments-tax-audit-kpi-${item.id}`} testID={`payments-tax-audit-kpi-${item.id}`}>
                    <BillingGlossaryLabel
                      accentColor={T.finance}
                      dataTestId={`payments-tax-audit-kpi-${item.id}-glossary`}
                      glossaryKey={item.id === 'customer-total' ? 'customer_charge_total' : item.id === 'net-settlement' ? 'net_settlement' : undefined}
                      label={item.label}
                      textColor={T.textMuted}
                    />
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
                  </View>
                ))}
              </View>
              <View style={{ marginTop: 14, gap: 6 }}>
                <Text style={{ color: T.textSec, fontSize: 11 }}>User Notifications: {(auditReport?.notifications?.user_notification_ids || []).join(' | ') || 'N/A'}</Text>
                <Text style={{ color: T.textSec, fontSize: 11 }}>Admin Notifications: {(auditReport?.notifications?.admin_notification_ids || []).join(' | ') || 'N/A'}</Text>
                <Text style={{ color: T.textSec, fontSize: 11 }}>Recovery Queue Entries: {(auditReport?.recovery_queue || []).length}</Text>
                <Text style={{ color: T.textSec, fontSize: 11 }}>Ledger Entries: {auditReport?.ledger?.count || 0}</Text>
              </View>
            </View>
          ) : null}
        </View>
      ) : null}

      {activeSection === 'audit-timeline' ? (
        <View style={{ gap: 16 }} data-testid="payments-tax-audit-timeline-panel" testID="payments-tax-audit-timeline-panel">
          {!!opsMessage ? <Text style={{ color: T.warningText, fontSize: 11 }} data-testid="payments-tax-audit-timeline-message" testID="payments-tax-audit-timeline-message">{opsMessage}</Text> : null}
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.043', 'Immutable Audit Timeline')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <TouchableOpacity onPress={() => { void loadAuditTimeline(); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-audit-timeline-load-button" testID="payments-tax-audit-timeline-load-button"><Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.044', 'Load Timeline')}</Text></TouchableOpacity>
              <TextInput value={timelineAckNote} onChangeText={setTimelineAckNote} placeholder={tx('admin.paymentsTaxPanel.auto.placeholder.002', 'Acknowledgement note')} placeholderTextColor={T.textMuted} style={{ minWidth: 220, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 10, color: T.text, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="payments-tax-audit-ack-note" testID="payments-tax-audit-ack-note" />
              <TouchableOpacity onPress={() => { void acknowledgeTimeline(); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }} data-testid="payments-tax-audit-ack-button" testID="payments-tax-audit-ack-button"><Text style={{ color: T.successText, fontSize: 12, fontWeight: '800' }}>{opsBusy ? 'Working...' : 'Acknowledge'}</Text></TouchableOpacity>
            </View>
          </View>
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }} data-testid="payments-tax-audit-timeline-card" testID="payments-tax-audit-timeline-card">
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.paymentsTaxPanel.auto.text.045', 'Timeline Events')}</Text>
            {auditTimeline?.events?.length ? auditTimeline.events.map((event: any, idx: number) => (
              <View key={`${event.timestamp}-${idx}`} style={{ flexDirection: 'row', gap: 12, paddingVertical: 10, borderBottomWidth: idx < auditTimeline.events.length - 1 ? 1 : 0, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-audit-timeline-event-${idx}`} testID={`payments-tax-audit-timeline-event-${idx}`}>
                <View style={{ width: 10, height: 10, borderRadius: 10, backgroundColor: event.immutable ? T.success : T.warning, marginTop: 4 }} />
                <View style={{ flex: 1 }}>
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '800' }}>{event.title}</Text>
                  <Text style={{ color: T.textSec, fontSize: 11, marginTop: 2 }}>{event.detail}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{event.timestamp} • {event.source}</Text>
                </View>
              </View>
            )) : <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.paymentsTaxPanel.auto.text.046', 'Load a payment reference to inspect the immutable audit timeline.')}</Text>}
            {!!auditTimeline?.acknowledgements?.length && (
              <View style={{ marginTop: 16 }} data-testid="payments-tax-audit-ack-history" testID="payments-tax-audit-ack-history">
                <Text style={{ color: T.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }}>{tx('admin.paymentsTaxPanel.auto.text.047', 'Acknowledgement History')}</Text>
                {auditTimeline.acknowledgements.map((ack: any, idx: number) => (
                  <Text key={`${ack.ack_id}-${idx}`} style={{ color: T.textSec, fontSize: 11, marginBottom: 4 }} data-testid={`payments-tax-audit-ack-history-${idx}`} testID={`payments-tax-audit-ack-history-${idx}`}>{ack.created_at} • {ack.actor_email} • {ack.note}</Text>
                ))}
              </View>
            )}
          </View>
        </View>
      ) : null}

      {activeSection === 'webhook-taxonomy' ? (
        <View style={{ gap: 16 }} data-testid="payments-tax-webhook-taxonomy-panel" testID="payments-tax-webhook-taxonomy-panel">
          {!!opsMessage ? <Text style={{ color: T.warningText, fontSize: 11 }} data-testid="payments-tax-webhook-message" testID="payments-tax-webhook-message">{opsMessage}</Text> : null}
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }}>
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.paymentsTaxPanel.auto.text.048', 'Webhook Error Taxonomy')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 12 }}>{tx('admin.paymentsTaxPanel.auto.text.049', 'Categorizes retry/dead FedaPay webhook failures by dominant error family.')}</Text>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <TouchableOpacity onPress={() => { void loadWebhookTaxonomy(); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.finance }} data-testid="payments-tax-taxonomy-refresh" testID="payments-tax-taxonomy-refresh"><Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.050', 'Refresh')}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void saveAutoTriggerPolicy(!(autoTriggerPolicy?.enabled)); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: autoTriggerPolicy?.enabled ? 'var(--app-success-soft)' : T.cardAlt, borderWidth: 1, borderColor: autoTriggerPolicy?.enabled ? 'var(--app-success-soft)' : T.border }} data-testid="payments-tax-auto-trigger-toggle" testID="payments-tax-auto-trigger-toggle"><Text style={{ color: autoTriggerPolicy?.enabled ? T.success : T.textSec, fontSize: 12, fontWeight: '800' }}>{autoTriggerPolicy?.enabled ? 'Auto-Trigger Enabled' : 'Enable Auto-Trigger'}</Text></TouchableOpacity>
              <TouchableOpacity onPress={() => { void evaluateAutoTriggerPolicy(); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border }} data-testid="payments-tax-auto-trigger-evaluate" testID="payments-tax-auto-trigger-evaluate"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.paymentsTaxPanel.auto.text.051', 'Evaluate Policy')}</Text></TouchableOpacity>
            </View>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>Dead queue threshold: {autoTriggerPolicy?.dead_threshold || 5} • Replay limit: {autoTriggerPolicy?.replay_limit || 30} • Dead total: {taxonomy?.dead_total || 0}</Text>
          </View>
          <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 16 }}>
            {(taxonomy?.categories || []).map((bucket: any, idx: number) => (
              <View key={`${bucket.category}-${idx}`} style={{ paddingVertical: 10, borderBottomWidth: idx < (taxonomy?.categories || []).length - 1 ? 1 : 0, borderBottomColor: 'var(--app-border)' }} data-testid={`payments-tax-taxonomy-bucket-${bucket.category}`} testID={`payments-tax-taxonomy-bucket-${bucket.category}`}>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '800' }}>{bucket.category.toUpperCase()} • {bucket.count}</Text>
                {bucket.events?.slice(0, 2).map((event: any, eventIdx: number) => (
                  <Text key={`${bucket.category}-${eventIdx}`} style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>{event.event_key || 'event'} • {event.last_error || 'No error text'} </Text>
                ))}
              </View>
            ))}
          </View>
        </View>
      ) : null}
    </ScrollView>
  );
}