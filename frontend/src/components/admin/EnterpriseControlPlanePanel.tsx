import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

// Fallback theme colors for use outside component scope
const FALLBACK_COLORS = {
  bg: 'var(--app-bg)' as any,
  bgAlt: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  surface: 'var(--app-surface)' as any,
  surfaceHover: 'var(--app-surface-hover)' as any,
  border: 'var(--app-border)' as any,
  borderStrong: 'var(--app-border-strong)' as any,
  bgSoft: 'var(--app-surface)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  textDim: 'var(--app-text-muted)' as any,
  primaryText: 'var(--app-primary-text)' as any,
  primary: 'var(--app-primary)' as any,
  success: 'var(--app-success)' as any,
  warning: 'var(--app-warning)' as any,
  error: 'var(--app-error)' as any,
};

const tx = (_key: string, fallback: string) => fallback;

const AC = FALLBACK_COLORS;

const statusColor = (status: string) => {
  if (status === 'insufficient_data' || status === 'unknown') return AC.textMuted;
  if (status === 'healthy' || status === 'completed' || status === 'restored') return AC.success;
  if (status === 'warning') return AC.warning;
  return AC.error;
};

const badgeBg = (status: string) => `${statusColor(status)}20`;

const formatNumber = (value: any, decimals = 1) => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(decimals) : '--';
};

const formatSignedNumber = (value: any, decimals = 1) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return '--';
  return `${num >= 0 ? '+' : ''}${num.toFixed(decimals)}`;
};

const triggerFileDownload = (filename: string, content: string, mimeType: string) => {
  if (Platform.OS !== 'web' || typeof window === 'undefined' || typeof document === 'undefined') {
    return false;
  }
  const blob = new Blob([content], { type: mimeType });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
  return true;
};

const buildRunbookCsv = (report: any) => {
  const rows: [string, string][] = [
    ['Report ID', String(report?.report_id || '')],
    ['Generated At', String(report?.generated_at || '')],
    ['Runbook Status', String(report?.runbook?.status || '')],
    ['Runbook Phase', String(report?.runbook?.phase || '')],
    ['Duration Seconds', String(report?.runbook?.duration_seconds ?? '')],
    ['Final Score', String(report?.final_state?.score ?? '')],
    ['Final Issues', String(report?.final_state?.issues ?? '')],
    ['Stable', String(report?.final_state?.stable ?? '')],
    ['Baseline Score', String(report?.baseline?.score ?? '')],
    ['Baseline Issues', String(report?.baseline?.issues ?? '')],
    ['Post Enforcement Score', String(report?.post_enforcement?.score ?? '')],
    ['Post Enforcement Issues', String(report?.post_enforcement?.issues ?? '')],
    ['Enterprise Audit Score', String(report?.enterprise_audit?.score ?? '')],
    ['Enterprise Audit Issues', String(report?.enterprise_audit?.issues ?? '')],
    ['Fedapay Sync Status', String(report?.reliability?.fedapay_sync_status || '')],
    ['Fedapay Retry Queue', String(report?.reliability?.fedapay_retry_processed ?? '')],
    ['Fedapay Dead Replay', String(report?.reliability?.fedapay_dead_replayed ?? '')],
    ['Learning Hub Assurance', String(report?.reliability?.learning_hub_status || '')],
  ];

  const escaped = rows.map(([k, v]) => `"${String(k).replace(/"/g, '""')}","${String(v).replace(/"/g, '""')}"`);
  return ['Metric,Value', ...escaped].join('\n');
};

export default function EnterpriseControlPlanePanel() {
  const { colors } = useTheme();
  const adminTheme = useAdminTheme();
  const AC = adminTheme || FALLBACK_COLORS;
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [loading, setLoading] = useState(true);
  const [runningAudit, setRunningAudit] = useState(false);
  const [restoringId, setRestoringId] = useState('');
  const [notice, setNotice] = useState('');
  const [controlPlane, setControlPlane] = useState<any>(null);
  const [runbookRunning, setRunbookRunning] = useState(false);
  const [runbookRunId, setRunbookRunId] = useState('');
  const [runbookRuntime, setRunbookRuntime] = useState<any>(null);
  const [closingRunbook, setClosingRunbook] = useState(false);
  const [runbookCloseResult, setRunbookCloseResult] = useState<any>(null);
  const [closureAlertToast, setClosureAlertToast] = useState<{ message: string; failingGate?: string; failingGateUrl?: string } | null>(null);
  const [emailingAdmins, setEmailingAdmins] = useState(false);
  const [emailDistribution, setEmailDistribution] = useState<any>(null);
  const [savingSloPolicy, setSavingSloPolicy] = useState(false);
  const [runningSloMitigation, setRunningSloMitigation] = useState(false);
  const [factoryGate, setFactoryGate] = useState<any>(null);
  const panelTitle = t('enterpriseControlPlane.header.title');

  const loadControlPlane = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/admin/platform-health/enterprise-control-plane');
      setControlPlane(data || null);
    } catch {
      setControlPlane(null);
      setNotice('Unable to load Enterprise Control Plane data right now.');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadControlPlane();
    // Load factory gate data
    api.get('/admin/platform-health/factory-gate/summary').then(({ data }) => setFactoryGate(data)).catch(() => {});
  }, [loadControlPlane]);

  const runEnterpriseAudit = useCallback(async () => {
    setRunningAudit(true);
    setNotice('');
    try {
      const { data } = await api.post('/admin/platform-health/enterprise-auto-audit');
      const score = data?.final_state?.score ?? '--';
      setNotice(`Enterprise audit completed. Latest score: ${score}.`);
      await loadControlPlane();
    } catch {
      setNotice('Enterprise audit failed. Please retry.');
    }
    setRunningAudit(false);
  }, [loadControlPlane]);

  const runEnterpriseIntegrityRunbook = useCallback(async () => {
    if (runbookRunning) return;
    setRunbookRunning(true);
    setNotice('');
    try {
      const { data } = await api.post('/admin/platform-health/enterprise-standard/enforce-now');
      const accepted = Boolean(data?.accepted);
      const runId = String(data?.run_id || '');
      if (!accepted || !runId) {
        throw new Error('Runbook request was not accepted.');
      }
      setRunbookRunId(runId);
      setEmailDistribution(null);
      setRunbookCloseResult(null);
      setRunbookRuntime({
        run_id: runId,
        status: 'running',
        phase: 'queued',
        duration_seconds: 0,
      });
      setNotice('Enterprise Integrity Runbook started. Monitoring progress...');
    } catch (error: any) {
      setRunbookRunning(false);
      setRunbookRuntime(null);
      setNotice(error?.response?.data?.detail || error?.message || 'Runbook start failed.');
    }
  }, [runbookRunning]);

  const pollRunbook = useCallback(async () => {
    if (!runbookRunId) return;
    try {
      const { data } = await api.get(`/admin/platform-health/enterprise-standard/enforcement/${runbookRunId}`);
      setRunbookRuntime(data || null);

      const status = String(data?.status || '').toLowerCase();
      const phase = String(data?.phase || '').toLowerCase();
      const done = ['healthy', 'warning', 'critical', 'error'].includes(status) || ['completed', 'failed'].includes(phase);
      if (done) {
        setRunbookRunning(false);
        setRunbookRunId('');
        setNotice(status === 'error' || phase === 'failed' ? 'Runbook finished with errors. Download report for details.' : 'Runbook completed. Compliance report is ready to download.');
        if (data?.closure) setRunbookCloseResult(data.closure);
        await loadControlPlane();
      }
    } catch {
      // noop: keep polling until runbook completes or id resets
    }
  }, [loadControlPlane, runbookRunId]);

  useHybridPolling({
    enabled: Boolean(runbookRunId),
    errorScope: 'admin/enterprise-control-plane/runbook-polling',
    onTick: pollRunbook,
    runOnMount: true,
    slowIntervalMs: 9000,
    fastIntervalMs: 4500,
    wsEnabled: false,
  });

  const sendComplianceReportToAdmins = useCallback(async () => {
    const runId = String(runbookRuntime?.run_id || '');
    if (!runId || emailingAdmins) return;
    setEmailingAdmins(true);
    setNotice('');
    try {
      const { data } = await api.post(`/admin/platform-health/enterprise-standard/enforcement/${runId}/email-report`);
      const distribution = data?.email_distribution || null;
      setEmailDistribution(distribution);
      setRunbookRuntime((prev: any) => ({
        ...(prev || {}),
        compliance_report: {
          ...((prev || {})?.compliance_report || {}),
          email_distribution: distribution,
        },
      }));
      setNotice(`Compliance report emailed to ${distribution?.sent_count ?? 0}/${distribution?.recipients_count ?? 0} admin recipients.`);
    } catch (error: any) {
      setNotice(error?.response?.data?.detail || 'Compliance email distribution failed.');
    }
    setEmailingAdmins(false);
  }, [emailingAdmins, runbookRuntime?.run_id]);

  const closeRunbookWithStrictGate = useCallback(async () => {
    const runId = String(runbookRuntime?.run_id || '');
    if (!runId || closingRunbook) return;
    setClosingRunbook(true);
    setNotice('');
    try {
      const { data } = await api.post(`/admin/platform-health/enterprise-standard/enforcement/${runId}/close`, {
        close_reason: 'admin_manual_signoff',
      });
      setClosureAlertToast(null);
      setRunbookCloseResult(data?.closure || null);
      if (data?.run) {
        setRunbookRuntime(data.run);
      }
      const closedBy = data?.closure?.closed_by || 'admin';
      setNotice(`Runbook closed successfully by ${closedBy}.`);
      await loadControlPlane();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      if (error?.response?.status === 423) {
        const msg = detail?.message || 'Runbook closure blocked by Autonomous Engine strict hard-gate.';
        setNotice(msg);
        setClosureAlertToast({
          message: msg,
          failingGate: String(detail?.failing_gate || 'STATUS'),
          failingGateUrl: String(detail?.failing_gate_url || ''),
        });
        setTimeout(() => setClosureAlertToast(null), 8000);
      } else {
        setNotice(detail || 'Runbook closure failed.');
      }
    }
    setClosingRunbook(false);
  }, [closingRunbook, loadControlPlane, runbookRuntime?.run_id]);

  const complianceReport = useMemo(() => {
    if (!runbookRuntime) return null;
    const runId = String(runbookRuntime?.run_id || runbookRuntime?.event_id || 'enterprise_integrity_report');
    const now = new Date().toISOString();
    const baseline = runbookRuntime?.baseline || {};
    const finalScan = runbookRuntime?.final_scan || {};
    const finalState = runbookRuntime?.final_state || {};
    const enterpriseAudit = runbookRuntime?.enterprise_audit || {};
    const fedapay = runbookRuntime?.fedapay || {};
    return {
      report_id: `eir_${runId}`,
      generated_at: now,
      runbook: {
        run_id: runId,
        status: String(runbookRuntime?.status || 'unknown'),
        phase: String(runbookRuntime?.phase || 'unknown'),
        duration_seconds: Number(runbookRuntime?.duration_seconds || 0),
      },
      baseline: {
        score: Number(baseline?.score || 0),
        issues: Number(baseline?.total_issues || 0),
      },
      final_state: {
        score: Number(finalState?.score || 0),
        issues: Number(finalState?.issues || 0),
        stable: Boolean(finalState?.stable),
      },
      post_enforcement: {
        score: Number(finalScan?.score || 0),
        issues: Number(finalScan?.total_issues || 0),
      },
      enterprise_audit: {
        score: Number(enterpriseAudit?.final_state?.score || enterpriseAudit?.latest_scan?.score || 0),
        issues: Number(enterpriseAudit?.final_state?.issues || enterpriseAudit?.latest_scan?.total_issues || 0),
      },
      reliability: {
        fedapay_sync_status: String(fedapay?.sync?.status || 'unknown'),
        fedapay_retry_processed: Number(fedapay?.retry?.processed || 0),
        fedapay_dead_replayed: Number(fedapay?.dead_replay?.replayed || 0),
        learning_hub_status: String(runbookRuntime?.learning_hub_assurance?.status || 'unknown'),
      },
      raw: runbookRuntime,
    };
  }, [runbookRuntime]);

  const latestEmailDistribution = useMemo(
    () => emailDistribution || runbookRuntime?.compliance_report?.email_distribution || runbookRuntime?.email_distribution || null,
    [emailDistribution, runbookRuntime],
  );

  const downloadComplianceReportJson = useCallback(() => {
    if (!complianceReport) return;
    const filename = `enterprise_integrity_compliance_${new Date().toISOString().slice(0, 10)}.json`;
    const content = JSON.stringify(complianceReport, null, 2);
    const ok = triggerFileDownload(filename, content, 'application/json');
    if (!ok) {
      setNotice('Compliance download is currently available on web admin.');
      return;
    }
    setNotice('Compliance JSON report download started.');
  }, [complianceReport]);

  const downloadComplianceReportCsv = useCallback(() => {
    if (!complianceReport) return;
    const filename = `enterprise_integrity_compliance_${new Date().toISOString().slice(0, 10)}.csv`;
    const content = buildRunbookCsv(complianceReport);
    const ok = triggerFileDownload(filename, content, 'text/csv;charset=utf-8');
    if (!ok) {
      setNotice('Compliance download is currently available on web admin.');
      return;
    }
    setNotice('Compliance CSV report download started.');
  }, [complianceReport]);

  const restoreCheckpoint = useCallback(async (checkpointId: string) => {
    setRestoringId(checkpointId);
    setNotice('');
    try {
      await api.post(`/admin/platform-health/enterprise-control-plane/rollback/${checkpointId}/restore`);
      setNotice(`Rollback restored from checkpoint ${checkpointId}.`);
      await loadControlPlane();
    } catch {
      setNotice(`Rollback restore failed for checkpoint ${checkpointId}.`);
    }
    setRestoringId('');
  }, [loadControlPlane]);

  const pipeline = controlPlane?.pipeline || {};
  const finalState = pipeline?.final_state || {};
  const diff = controlPlane?.latest_autofix_diff || {};
  const enforcement = controlPlane?.enforcement_rule_health || {};
  const autoRemediation = controlPlane?.auto_remediation_kpis || {};
  const taxCenter = controlPlane?.tax_reconciliation_command_center || {};
  const rollback = controlPlane?.rollback || {};
  const checkpoints = rollback?.recent_checkpoints || [];
  const providerRows = taxCenter?.providers || [];
  const mttr24 = autoRemediation?.mttr?.window_24h || {};
  const mttr7d = autoRemediation?.mttr?.window_7d || {};
  const stale24 = autoRemediation?.stale_cache_recurrence?.window_24h || {};
  const stale7d = autoRemediation?.stale_cache_recurrence?.window_7d || {};
  const route24 = autoRemediation?.route_health_score?.window_24h || {};
  const route7d = autoRemediation?.route_health_score?.window_7d || {};
  const executiveRollup = autoRemediation?.executive_rollup || {};
  const sloAutoMitigation = controlPlane?.slo_auto_mitigation || {};
  const sloPolicy = sloAutoMitigation?.policy || {};
  const sloRuntime = sloAutoMitigation?.runtime || {};
  const sloPerformance = sloAutoMitigation?.current_performance || {};
  const effectiveClosure = runbookCloseResult || runbookRuntime?.closure || null;
  const isRunbookClosed = Boolean(effectiveClosure?.closed);

  const updateSloPolicy = useCallback(async (payload: any) => {
    setSavingSloPolicy(true);
    setNotice('');
    try {
      await api.post('/admin/platform-health/enterprise-standard/slo-auto-mitigation/config', payload);
      setNotice('SLO auto-mitigation policy updated.');
      await loadControlPlane();
    } catch (error: any) {
      setNotice(error?.response?.data?.detail || 'Unable to update SLO auto-mitigation policy.');
    }
    setSavingSloPolicy(false);
  }, [loadControlPlane]);

  const toggleSloAutoMitigation = useCallback(async () => {
    await updateSloPolicy({ enabled: !Boolean(sloPolicy?.enabled) });
  }, [sloPolicy?.enabled, updateSloPolicy]);

  const runSloAutoMitigationNow = useCallback(async () => {
    if (runningSloMitigation) return;
    setRunningSloMitigation(true);
    setNotice('');
    try {
      const { data } = await api.post('/admin/platform-health/enterprise-standard/slo-auto-mitigation/run-now');
      setNotice(`SLO mitigation cycle: ${String(data?.status || 'completed')}.`);
      await loadControlPlane();
    } catch (error: any) {
      setNotice(error?.response?.data?.detail || 'SLO mitigation cycle failed.');
    }
    setRunningSloMitigation(false);
  }, [loadControlPlane, runningSloMitigation]);

  const summaryCards = useMemo(() => {
    const colors = adminTheme || FALLBACK_COLORS;
    return [
      { key: 'score', label: 'Health Score', value: finalState?.score ?? '--', icon: 'pulse', color: colors.successText, testId: 'control-plane-health-score' },
      { key: 'issues', label: 'Open Issues', value: finalState?.issues ?? '--', icon: 'warning', color: colors.warningText, testId: 'control-plane-open-issues' },
      { key: 'severity', label: 'Severity Band', value: pipeline?.severity_band || 'low', icon: 'flag', color: colors.primary, testId: 'control-plane-severity-band' },
      { key: 'checkpoints', label: 'Rollback Points', value: rollback?.total_recent ?? 0, icon: 'save', color: colors.textSec, testId: 'control-plane-checkpoint-count' },
    ];
  }, [finalState?.issues, finalState?.score, pipeline?.severity_band, rollback?.total_recent, adminTheme]);

  const taxSummaryCards = useMemo(() => {
    const colors = adminTheme || FALLBACK_COLORS;
    return [
      {
        key: 'overall-tax-accuracy',
        label: 'Overall Tax Accuracy',
        value: `${Number(taxCenter?.overall_tax_accuracy_rate ?? 0).toFixed(1)}%`,
        color: Number(taxCenter?.overall_tax_accuracy_rate ?? 0) >= 99 ? colors.success : colors.warning,
        icon: 'shield-checkmark',
        testId: 'tax-recon-overall-tax-accuracy',
      },
      {
        key: 'overall-webhook-lag',
        label: 'Avg Webhook Lag',
        value: `${Number(taxCenter?.overall_avg_webhook_lag_seconds ?? 0).toFixed(1)}s`,
        color: Number(taxCenter?.overall_avg_webhook_lag_seconds ?? 0) < 60 ? colors.success : Number(taxCenter?.overall_avg_webhook_lag_seconds ?? 0) <= 300 ? colors.warning : colors.error,
        icon: 'timer',
        testId: 'tax-recon-overall-webhook-lag',
      },
      {
        key: 'ledger-integrity',
        label: 'Ledger Integrity',
        value: `${Number(taxCenter?.ledger_integrity?.score ?? 0).toFixed(1)}%`,
        color: Number(taxCenter?.ledger_integrity?.score ?? 0) >= 99 ? colors.success : colors.warning,
        icon: 'git-network',
        testId: 'tax-recon-ledger-integrity-score',
      },
      {
        key: 'window',
        label: 'Realtime Window',
        value: `${taxCenter?.window_hours ?? 24}h`,
        color: colors.textSec,
        icon: 'time',
        testId: 'tax-recon-window-hours',
      },
      {
        key: 'tax-alerts',
        label: 'Missing Tax Alerts',
        value: `${Number(taxCenter?.receipt_tax_alerts?.open_in_window ?? 0)}`,
        color: Number(taxCenter?.receipt_tax_alerts?.open_in_window ?? 0) === 0 ? colors.success : colors.warning,
        icon: 'warning',
        testId: 'tax-recon-missing-tax-alerts',
      },
    ];
  }, [taxCenter?.ledger_integrity?.score, taxCenter?.overall_avg_webhook_lag_seconds, taxCenter?.overall_tax_accuracy_rate, taxCenter?.window_hours, taxCenter?.receipt_tax_alerts?.open_in_window, adminTheme]);

  if (loading) {
    return (
      <View style={{ paddingVertical: 64, alignItems: 'center' }} data-testid="enterprise-control-plane-loading" testID="enterprise-control-plane-loading">
        <ActivityIndicator size="large" color={AC.primary} />
        <Text style={{ color: AC.textSec, marginTop: 10, fontSize: 13 }}>{tx('enterpriseControlPlane.states.loading', 'Loading Enterprise Control Plane...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 18, gap: 14 }} data-testid="enterprise-control-plane-panel" testID="enterprise-control-plane-panel">
      <View style={{ backgroundColor: AC.card, borderWidth: 1, borderColor: AC.border, borderRadius: 16, padding: 16 }} data-testid="enterprise-control-plane-hero" testID="enterprise-control-plane-hero">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: `${AC.primary}22`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="construct" size={18} color={AC.primary} />
            </View>
            <View>
              <Text style={{ color: AC.text, fontSize: 19, fontWeight: '800' }} data-testid="enterprise-control-plane-title" testID="enterprise-control-plane-title">{panelTitle === 'enterpriseControlPlane.header.title' ? 'Enterprise Control Plane' : panelTitle}</Text>
              <Text style={{ color: AC.textMuted, fontSize: 11 }} data-testid="enterprise-control-plane-subtitle" testID="enterprise-control-plane-subtitle">{tx('admin.enterpriseControlPlanePanel.auto.text.001', 'Pipeline status, auto-fix diff, rule health, rollback checkpoints')}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TouchableOpacity
              onPress={loadControlPlane}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: AC.border, backgroundColor: AC.bgSoft }}
              data-testid="enterprise-control-plane-refresh-button" testID="enterprise-control-plane-refresh-button"
            >
              <Text style={{ color: AC.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.002', 'Refresh')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runEnterpriseAudit}
              disabled={runningAudit}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: runningAudit ? `${AC.primary}55` : AC.primary }}
              data-testid="enterprise-control-plane-run-audit-button" testID="enterprise-control-plane-run-audit-button"
            >
              <Text style={{ color: AC.primaryText, fontSize: 12, fontWeight: '800' }}>{runningAudit ? 'Running...' : 'Run Enterprise Audit'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runEnterpriseIntegrityRunbook}
              disabled={runbookRunning}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: runbookRunning ? `${AC.success}55` : AC.success }}
              data-testid="enterprise-integrity-runbook-run-button" testID="enterprise-integrity-runbook-run-button"
            >
              <Text style={{ color: AC.primaryText, fontSize: 12, fontWeight: '800' }}>{runbookRunning ? tx('enterpriseControlPlane.actions.runbookRunning', 'Runbook Running…') : tx('enterpriseControlPlane.actions.runIntegrityRunbook', 'Run Enterprise Integrity Runbook')}</Text>
            </TouchableOpacity>
          </View>
        </View>
        {notice ? (
          <Text style={{ color: notice.includes('failed') ? AC.error : AC.success, fontSize: 11, marginTop: 10 }} data-testid="enterprise-control-plane-notice" testID="enterprise-control-plane-notice">{notice}</Text>
        ) : null}
        {closureAlertToast ? (
          <View
            style={{
              marginTop: 10,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: `${AC.error}66`,
              backgroundColor: `${AC.error}1A`,
              paddingHorizontal: 10,
              paddingVertical: 8,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 10,
              flexWrap: 'wrap',
            }}
            data-testid="enterprise-runbook-blocked-toast"
            testID="enterprise-runbook-blocked-toast"
          >
            <Text style={{ color: colors.errorText, fontSize: 10, fontWeight: '700', flex: 1 }} data-testid="enterprise-runbook-blocked-toast-message" testID="enterprise-runbook-blocked-toast-message">
              {closureAlertToast.message} Failing gate: {closureAlertToast.failingGate || 'STATUS'}.
            </Text>
            <TouchableOpacity accessibilityLabel={tx('admin.enterpriseControlPlanePanel.auto.accessibility.001', 'Open failing gate details')}
              onPress={() => {
                if (typeof window !== 'undefined') {
                  const target = closureAlertToast.failingGateUrl || '/admin-console?category=operations&tab=autonomous-engine';
                  window.open(target, '_blank');
                }
              }}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.error, borderWidth: 1, borderColor: colors.errorText }}
              data-testid="enterprise-runbook-blocked-toast-open-gate"
              testID="enterprise-runbook-blocked-toast-open-gate"
            >
              <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.003', 'Open Failing Gate')}</Text>
            </TouchableOpacity>
          </View>
        ) : null}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="enterprise-control-plane-summary-cards" testID="enterprise-control-plane-summary-cards">
        {summaryCards.map((card) => (
          <View key={card.key} style={{ flex: 1, minWidth: 160, backgroundColor: AC.card, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: AC.border }} data-testid={card.testId} testID={card.testId}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={card.icon as any} size={14} color={card.color} />
              <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
            </View>
            <Text style={{ color: card.color, fontSize: 20, fontWeight: '900', marginTop: 6 }} data-testid={`${card.testId}-value`} testID={`${card.testId}-value`}>{String(card.value)}</Text>
          </View>
        ))}
      </View>

      {/* Factory Gate Health Card */}
      <View style={{ backgroundColor: AC.card, borderRadius: 14, borderWidth: 1, borderColor: AC.border, padding: 14 }} data-testid="factory-gate-health-card" testID="factory-gate-health-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: `${AC.primary}22`, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="git-branch" size={16} color={AC.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.004', 'Factory Gate Health')}</Text>
            <Text style={{ color: AC.textMuted, fontSize: 10 }}>{tx('admin.enterpriseControlPlanePanel.auto.text.005', 'CI/CD pipeline PASS/FAIL trends')}</Text>
          </View>
          {factoryGate?.last_run && (
            <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: factoryGate.last_run.status === 'pass' ? `${AC.success}20` : `${AC.error}20` }} data-testid="factory-gate-last-status-badge" testID="factory-gate-last-status-badge">
              <Text style={{ color: factoryGate.last_run.status === 'pass' ? AC.success : AC.error, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>
                {factoryGate.last_run.status}
              </Text>
            </View>
          )}
        </View>
        {factoryGate?.week_trends ? (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <View style={{ flex: 1, minWidth: 80, backgroundColor: AC.bgSoft, borderRadius: 8, padding: 8, alignItems: 'center' }} data-testid="factory-gate-pass-rate" testID="factory-gate-pass-rate">
              <Text style={{ color: AC.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.006', 'Pass Rate')}</Text>
              <Text style={{ color: factoryGate.week_trends.pass_rate >= 80 ? AC.success : AC.warning, fontSize: 18, fontWeight: '900', marginTop: 2 }}>
                {factoryGate.week_trends.pass_rate}%
              </Text>
            </View>
            <View style={{ flex: 1, minWidth: 80, backgroundColor: AC.bgSoft, borderRadius: 8, padding: 8, alignItems: 'center' }} data-testid="factory-gate-total-runs" testID="factory-gate-total-runs">
              <Text style={{ color: AC.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.007', 'Runs (7d)')}</Text>
              <Text style={{ color: AC.text, fontSize: 18, fontWeight: '900', marginTop: 2 }}>{factoryGate.week_trends.total_runs}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 80, backgroundColor: AC.bgSoft, borderRadius: 8, padding: 8, alignItems: 'center' }} data-testid="factory-gate-streak" testID="factory-gate-streak">
              <Text style={{ color: AC.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.008', 'Streak')}</Text>
              <Text style={{ color: AC.successText, fontSize: 18, fontWeight: '900', marginTop: 2 }}>{factoryGate.week_trends.current_streak}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 80, backgroundColor: AC.bgSoft, borderRadius: 8, padding: 8, alignItems: 'center' }} data-testid="factory-gate-failures" testID="factory-gate-failures">
              <Text style={{ color: AC.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.009', 'Failures')}</Text>
              <Text style={{ color: factoryGate.week_trends.failed > 0 ? AC.error : AC.success, fontSize: 18, fontWeight: '900', marginTop: 2 }}>{factoryGate.week_trends.failed}</Text>
            </View>
          </View>
        ) : (
          <Text style={{ color: AC.textMuted, fontSize: 11 }}>{tx('admin.enterpriseControlPlanePanel.auto.text.010', 'No CI gate data recorded yet. Gate results are recorded automatically by the CI pipeline.')}</Text>
        )}
        {factoryGate?.last_run && (
          <View style={{ marginTop: 8, flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
            <Text style={{ color: AC.textMuted, fontSize: 9 }}>Last: {factoryGate.last_run.pipeline} ({factoryGate.last_run.trigger})</Text>
            <Text style={{ color: AC.textMuted, fontSize: 9 }}>Tests: {factoryGate.last_run.test_pass_count}P / {factoryGate.last_run.test_fail_count}F</Text>
            <Text style={{ color: AC.textMuted, fontSize: 9 }}>Duration: {factoryGate.last_run.duration_seconds}s</Text>
          </View>
        )}
      </View>

      <View style={{ backgroundColor: AC.card, borderRadius: 14, borderWidth: 1, borderColor: AC.border, padding: 14 }} data-testid="enterprise-control-plane-auto-remediation-kpis-section" testID="enterprise-control-plane-auto-remediation-kpis-section">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          <View>
            <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }} data-testid="enterprise-control-plane-auto-remediation-kpis-title" testID="enterprise-control-plane-auto-remediation-kpis-title">{tx('admin.enterpriseControlPlanePanel.auto.text.011', 'Auto-Remediation KPI Board')}</Text>
            <Text style={{ color: AC.textMuted, fontSize: 10 }} data-testid="enterprise-control-plane-auto-remediation-kpis-subtitle" testID="enterprise-control-plane-auto-remediation-kpis-subtitle">{tx('admin.enterpriseControlPlanePanel.auto.text.012', 'MTTR, stale-cache recurrence, and route-health score across 24h + 7d windows.')}</Text>
          </View>
          <View style={{ backgroundColor: badgeBg(executiveRollup?.status || 'unknown'), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="enterprise-control-plane-auto-remediation-rollup-status" testID="enterprise-control-plane-auto-remediation-rollup-status">
            <Text style={{ color: statusColor(executiveRollup?.status || 'unknown'), fontSize: 10, fontWeight: '800' }} data-testid="enterprise-control-plane-auto-remediation-rollup-status-value" testID="enterprise-control-plane-auto-remediation-rollup-status-value">{String(executiveRollup?.status || 'unknown').toUpperCase()}</Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="enterprise-control-plane-auto-remediation-kpi-cards" testID="enterprise-control-plane-auto-remediation-kpi-cards">
          <View style={{ flex: 1, minWidth: 190, backgroundColor: AC.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: AC.border, padding: 12 }} data-testid="control-plane-kpi-mttr" testID="control-plane-kpi-mttr">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
              <Ionicons name="timer" size={14} color={statusColor(mttr24?.status || 'unknown')} />
              <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.013', 'MTTR (24h)')}</Text>
            </View>
            <Text style={{ color: statusColor(mttr24?.status || 'unknown'), fontSize: 20, fontWeight: '900', marginTop: 6 }} data-testid="control-plane-kpi-mttr-value" testID="control-plane-kpi-mttr-value">{formatNumber(mttr24?.mean_minutes, 1)} min</Text>
            <Text style={{ color: AC.textSec, fontSize: 10, marginTop: 4 }} data-testid="control-plane-kpi-mttr-aux" testID="control-plane-kpi-mttr-aux">{t("autofix.7d.avg")} {formatNumber(mttr7d?.mean_minutes, 1)} min · samples {String(mttr24?.sample_count ?? 0)} / {String(mttr7d?.sample_count ?? 0)}</Text>
          </View>

          <View style={{ flex: 1, minWidth: 190, backgroundColor: AC.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: AC.border, padding: 12 }} data-testid="control-plane-kpi-stale-cache-recurrence" testID="control-plane-kpi-stale-cache-recurrence">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
              <Ionicons name="layers" size={14} color={statusColor(stale24?.status || 'unknown')} />
              <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.014', 'Stale Cache Recurrence (24h)')}</Text>
            </View>
            <Text style={{ color: statusColor(stale24?.status || 'unknown'), fontSize: 20, fontWeight: '900', marginTop: 6 }} data-testid="control-plane-kpi-stale-cache-recurrence-value" testID="control-plane-kpi-stale-cache-recurrence-value">{String(stale24?.recurrence_count ?? 0)}</Text>
            <Text style={{ color: AC.textSec, fontSize: 10, marginTop: 4 }} data-testid="control-plane-kpi-stale-cache-recurrence-aux" testID="control-plane-kpi-stale-cache-recurrence-aux">7d recurrences {String(stale7d?.recurrence_count ?? 0)} · stale scans {String(stale24?.scans_with_stale_cache ?? 0)}/{String(stale24?.scans_total ?? 0)}</Text>
          </View>

          <View style={{ flex: 1, minWidth: 190, backgroundColor: AC.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: AC.border, padding: 12 }} data-testid="control-plane-kpi-route-health-score" testID="control-plane-kpi-route-health-score">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
              <Ionicons name="git-network" size={14} color={statusColor(route24?.status || 'unknown')} />
              <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.015', 'Route Health Score (24h)')}</Text>
            </View>
            <Text style={{ color: statusColor(route24?.status || 'unknown'), fontSize: 20, fontWeight: '900', marginTop: 6 }} data-testid="control-plane-kpi-route-health-score-value" testID="control-plane-kpi-route-health-score-value">{formatNumber(route24?.score, 1)}/100</Text>
            <Text style={{ color: AC.textSec, fontSize: 10, marginTop: 4 }} data-testid="control-plane-kpi-route-health-score-aux" testID="control-plane-kpi-route-health-score-aux">{t("autofix.7d.avg")} {formatNumber(route7d?.score, 1)} · trend {formatSignedNumber(route24?.trend_delta, 1)} · source {route24?.source || 'n/a'}</Text>
          </View>
        </View>
      </View>

      <View style={{ backgroundColor: AC.card, borderRadius: 14, borderWidth: 1, borderColor: AC.border, padding: 14 }} data-testid="enterprise-control-plane-pipeline-section" testID="enterprise-control-plane-pipeline-section">
        <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }} data-testid="enterprise-control-plane-pipeline-title" testID="enterprise-control-plane-pipeline-title">{tx('admin.enterpriseControlPlanePanel.auto.text.016', 'Pipeline Stage Status')}</Text>
        <Text style={{ color: AC.textMuted, fontSize: 10, marginBottom: 10 }} data-testid="enterprise-control-plane-last-run" testID="enterprise-control-plane-last-run">{t("autofix.last.run")} {pipeline?.last_run_at ? new Date(pipeline.last_run_at).toLocaleString() : 'No run yet'}</Text>
        <View style={{ gap: 8 }}>
          {(pipeline?.stages || []).map((stage: any) => (
            <View key={stage.id} style={{ backgroundColor: AC.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: AC.border, padding: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }} data-testid={`enterprise-control-plane-stage-${stage.id}`} testID={`enterprise-control-plane-stage-${stage.id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
                <Ionicons name={stage.status === 'healthy' ? 'checkmark-circle' : 'alert-circle'} size={15} color={statusColor(stage.status)} />
                <View style={{ flex: 1 }}>
                  <Text style={{ color: AC.text, fontSize: 12, fontWeight: '700' }} data-testid={`enterprise-control-plane-stage-${stage.id}-label`} testID={`enterprise-control-plane-stage-${stage.id}-label`}>{stage.label}</Text>
                  <Text style={{ color: AC.textMuted, fontSize: 10 }} data-testid={`enterprise-control-plane-stage-${stage.id}-detail`} testID={`enterprise-control-plane-stage-${stage.id}-detail`}>{stage.detail}</Text>
                </View>
              </View>
              <View style={{ backgroundColor: badgeBg(stage.status), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
                <Text style={{ color: statusColor(stage.status), fontSize: 10, fontWeight: '800' }} data-testid={`enterprise-control-plane-stage-${stage.id}-status`} testID={`enterprise-control-plane-stage-${stage.id}-status`}>{stage.status}</Text>
              </View>
            </View>
          ))}
        </View>
      </View>

      <View style={{ backgroundColor: AC.card, borderWidth: 1, borderColor: AC.border, borderRadius: 14, padding: 14 }} data-testid="enterprise-integrity-runbook-panel" testID="enterprise-integrity-runbook-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <View>
            <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }} data-testid="enterprise-integrity-runbook-title" testID="enterprise-integrity-runbook-title">{tx('admin.enterpriseControlPlanePanel.auto.text.017', 'Enterprise Integrity Runbook')}</Text>
            <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 3 }} data-testid="enterprise-integrity-runbook-subtitle" testID="enterprise-integrity-runbook-subtitle">{tx('admin.enterpriseControlPlanePanel.auto.text.018', 'One-click chain: auto-fix + enterprise audits + localization assurance + compliance export.')}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ backgroundColor: badgeBg(String(runbookRuntime?.status || 'unknown')), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="enterprise-integrity-runbook-status-pill" testID="enterprise-integrity-runbook-status-pill">
              <Text style={{ color: statusColor(String(runbookRuntime?.status || 'unknown')), fontSize: 10, fontWeight: '800' }} data-testid="enterprise-integrity-runbook-status-value" testID="enterprise-integrity-runbook-status-value">
                {String(runbookRuntime?.status || (runbookRunning ? 'running' : 'idle')).toUpperCase()}
              </Text>
            </View>
            <View style={{ backgroundColor: isRunbookClosed ? `${AC.success}20` : `${AC.warning}20`, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="enterprise-integrity-runbook-closure-pill" testID="enterprise-integrity-runbook-closure-pill">
              <Text style={{ color: isRunbookClosed ? AC.success : AC.warning, fontSize: 10, fontWeight: '800' }} data-testid="enterprise-integrity-runbook-closure-value" testID="enterprise-integrity-runbook-closure-value">
                {isRunbookClosed ? 'CLOSED' : 'OPEN'}
              </Text>
            </View>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 10 }}>
          <MetricPill
            label="Run ID"
            value={String(runbookRuntime?.run_id || '--')}
            valueColor={AC.textSec}
            testId="enterprise-integrity-runbook-run-id"
          />
          <MetricPill
            label="Phase"
            value={String(runbookRuntime?.phase || '--')}
            valueColor={statusColor(String(runbookRuntime?.status || 'unknown'))}
            testId="enterprise-integrity-runbook-phase"
          />
          <MetricPill
            label="Duration"
            value={`${formatNumber(runbookRuntime?.duration_seconds || 0, 1)}s`}
            valueColor={AC.textSec}
            testId="enterprise-integrity-runbook-duration"
          />
          <MetricPill
            label="Final Score"
            value={`${Number(runbookRuntime?.final_state?.score || 0)}`}
            valueColor={Number(runbookRuntime?.final_state?.score || 0) >= 95 ? AC.success : AC.warning}
            testId="enterprise-integrity-runbook-final-score"
          />
          <MetricPill
            label="Final Issues"
            value={`${Number(runbookRuntime?.final_state?.issues || 0)}`}
            valueColor={Number(runbookRuntime?.final_state?.issues || 0) === 0 ? AC.success : AC.warning}
            testId="enterprise-integrity-runbook-final-issues"
          />
          <MetricPill
            label="Closure"
            value={isRunbookClosed ? 'Closed' : 'Pending'}
            valueColor={isRunbookClosed ? AC.success : AC.warning}
            testId="enterprise-integrity-runbook-closure-state"
          />
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          <TouchableOpacity
            onPress={downloadComplianceReportJson}
            disabled={!complianceReport}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: complianceReport ? AC.primary : `${AC.primary}44` }}
            data-testid="enterprise-integrity-runbook-download-json-button" testID="enterprise-integrity-runbook-download-json-button"
          >
            <Text style={{ color: AC.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.019', 'Download Compliance JSON')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={downloadComplianceReportCsv}
            disabled={!complianceReport}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: complianceReport ? AC.bgSoft : `${AC.bgSoft}66`, borderWidth: 1, borderColor: AC.border }}
            data-testid="enterprise-integrity-runbook-download-csv-button" testID="enterprise-integrity-runbook-download-csv-button"
          >
            <Text style={{ color: complianceReport ? AC.text : AC.textMuted, fontSize: 11, fontWeight: '800' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.020', 'Download Compliance CSV')}</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel={tx('admin.enterpriseControlPlanePanel.auto.accessibility.002', 'Download signed compliance PDF')}
            onPress={() => {
              if (!runbookRuntime?.run_id) return;
              const base = (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '').replace(/\/+$/, '');
              const url = `${base}/api/admin/platform-health/enterprise-standard/enforcement/${runbookRuntime.run_id}/compliance-report/pdf`;
              if (typeof window !== 'undefined') window.open(url, '_blank');
            }}
            disabled={!runbookRuntime?.run_id}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: runbookRuntime?.run_id ? (globalThis as any).__alphaColor(AC.error, '20') : `${AC.bgSoft}66`, borderWidth: 1, borderColor: runbookRuntime?.run_id ? (globalThis as any).__alphaColor(AC.error, '40') : AC.border }}
            data-testid="enterprise-integrity-runbook-download-pdf-button" testID="enterprise-integrity-runbook-download-pdf-button"
          >
            <Text style={{ color: runbookRuntime?.run_id ? AC.error : AC.textMuted, fontSize: 11, fontWeight: '800' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.021', 'Download Signed PDF')}</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel={tx('admin.enterpriseControlPlanePanel.auto.accessibility.003', 'Send compliance report to admins')}
            onPress={sendComplianceReportToAdmins}
            disabled={!runbookRuntime?.run_id || emailingAdmins}
            style={{
              paddingHorizontal: 12,
              paddingVertical: 8,
              borderRadius: 10,
              backgroundColor: runbookRuntime?.run_id && !emailingAdmins ? AC.success : `${AC.success}55`,
            }}
            data-testid="enterprise-integrity-runbook-email-admins-button" testID="enterprise-integrity-runbook-email-admins-button"
          >
            <Text style={{ color: AC.primaryText, fontSize: 11, fontWeight: '800' }}>{emailingAdmins ? 'Sending…' : 'Email Report to Admins'}</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel={tx('admin.enterpriseControlPlanePanel.auto.accessibility.004', 'Close runbook with strict gate')}
            onPress={closeRunbookWithStrictGate}
            disabled={!runbookRuntime?.run_id || closingRunbook || isRunbookClosed}
            style={{
              paddingHorizontal: 12,
              paddingVertical: 8,
              borderRadius: 10,
              backgroundColor: isRunbookClosed ? `${AC.textMuted}44` : closingRunbook ? `${AC.warning}55` : AC.warning,
            }}
            data-testid="enterprise-integrity-runbook-close-button" testID="enterprise-integrity-runbook-close-button"
          >
            <Text style={{ color: AC.primaryText, fontSize: 11, fontWeight: '800' }}>
              {isRunbookClosed ? 'Runbook Closed' : closingRunbook ? 'Checking Gate…' : 'Close Runbook'}
            </Text>
          </TouchableOpacity>
        </View>

        {effectiveClosure?.closed_at ? (
          <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 8 }} data-testid="enterprise-integrity-runbook-closed-meta" testID="enterprise-integrity-runbook-closed-meta">
            Closed by {String(effectiveClosure?.closed_by || 'admin')} at {String(effectiveClosure?.closed_at || '').slice(0, 19)} • Reason: {String(effectiveClosure?.close_reason || 'manual_runbook_closure')}
          </Text>
        ) : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 10 }} data-testid="enterprise-integrity-runbook-email-distribution-metrics" testID="enterprise-integrity-runbook-email-distribution-metrics">
          <MetricPill
            label="Email Distribution"
            value={String(latestEmailDistribution?.status || '--')}
            valueColor={statusColor(String(latestEmailDistribution?.status || 'unknown'))}
            testId="enterprise-integrity-runbook-email-status"
          />
          <MetricPill
            label="Emails Sent"
            value={`${Number(latestEmailDistribution?.sent_count || 0)}/${Number(latestEmailDistribution?.recipients_count || 0)}`}
            valueColor={Number(latestEmailDistribution?.sent_count || 0) > 0 ? AC.success : AC.textSec}
            testId="enterprise-integrity-runbook-email-sent-count"
          />
          <MetricPill
            label="Failed Deliveries"
            value={`${Array.isArray(latestEmailDistribution?.failed) ? latestEmailDistribution.failed.length : 0}`}
            valueColor={Array.isArray(latestEmailDistribution?.failed) && latestEmailDistribution.failed.length > 0 ? AC.warning : AC.success}
            testId="enterprise-integrity-runbook-email-failed-count"
          />
        </View>
      </View>

      <View style={{ backgroundColor: AC.card, borderWidth: 1, borderColor: AC.border, borderRadius: 14, padding: 14 }} data-testid="enterprise-slo-auto-mitigation-panel" testID="enterprise-slo-auto-mitigation-panel">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View>
            <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800' }} data-testid="enterprise-slo-auto-mitigation-title" testID="enterprise-slo-auto-mitigation-title">{tx('admin.enterpriseControlPlanePanel.auto.text.022', 'SLO Breach Auto-Mitigation')}</Text>
            <Text style={{ color: AC.textMuted, fontSize: 10, marginTop: 3 }} data-testid="enterprise-slo-auto-mitigation-subtitle" testID="enterprise-slo-auto-mitigation-subtitle">{tx('admin.enterpriseControlPlanePanel.auto.text.023', 'Always-on guard: detects p95 latency breaches and runs targeted safe fix recipes.')}</Text>
          </View>
          <View style={{ backgroundColor: badgeBg(Boolean(sloPolicy?.enabled) ? 'healthy' : 'unknown'), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="enterprise-slo-auto-mitigation-enabled-pill" testID="enterprise-slo-auto-mitigation-enabled-pill">
            <Text style={{ color: statusColor(Boolean(sloPolicy?.enabled) ? 'healthy' : 'unknown'), fontSize: 10, fontWeight: '800' }} data-testid="enterprise-slo-auto-mitigation-enabled-value" testID="enterprise-slo-auto-mitigation-enabled-value">
              {Boolean(sloPolicy?.enabled) ? 'ENABLED' : 'DISABLED'}
            </Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 10 }} data-testid="enterprise-slo-auto-mitigation-metrics" testID="enterprise-slo-auto-mitigation-metrics">
          <MetricPill
            label="Current p95"
            value={`${formatNumber(sloPerformance?.global_p95_ms || 0, 1)}ms`}
            valueColor={Number(sloPerformance?.global_p95_ms || 0) <= Number(sloPolicy?.p95_latency_threshold_ms || 300) ? AC.success : AC.warning}
            testId="enterprise-slo-auto-mitigation-current-p95"
          />
          <MetricPill
            label="Threshold"
            value={`${Number(sloPolicy?.p95_latency_threshold_ms || 300)}ms`}
            valueColor={AC.textSec}
            testId="enterprise-slo-auto-mitigation-threshold"
          />
          <MetricPill
            label="Samples"
            value={`${Number(sloPerformance?.sample_count || 0)}`}
            valueColor={AC.textSec}
            testId="enterprise-slo-auto-mitigation-sample-count"
          />
          <MetricPill
            label="Last Result"
            value={String(sloRuntime?.last_result || '--')}
            valueColor={statusColor(String(sloRuntime?.last_result || 'unknown'))}
            testId="enterprise-slo-auto-mitigation-last-result"
          />
          <MetricPill
            label="Breach Streak"
            value={`${Number(sloRuntime?.consecutive_breach_count || 0)}`}
            valueColor={Number(sloRuntime?.consecutive_breach_count || 0) > 0 ? AC.warning : AC.success}
            testId="enterprise-slo-auto-mitigation-breach-streak"
          />
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          <TouchableOpacity
            onPress={toggleSloAutoMitigation}
            disabled={savingSloPolicy}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: savingSloPolicy ? `${AC.primary}55` : AC.primary }}
            data-testid="enterprise-slo-auto-mitigation-toggle-button" testID="enterprise-slo-auto-mitigation-toggle-button"
          >
            <Text style={{ color: AC.primaryText, fontSize: 11, fontWeight: '800' }}>{savingSloPolicy ? 'Saving…' : (Boolean(sloPolicy?.enabled) ? 'Disable Auto-Mitigation' : 'Enable Auto-Mitigation')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={runSloAutoMitigationNow}
            disabled={runningSloMitigation}
            style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: runningSloMitigation ? `${AC.success}55` : AC.success }}
            data-testid="enterprise-slo-auto-mitigation-run-now-button" testID="enterprise-slo-auto-mitigation-run-now-button"
          >
            <Text style={{ color: AC.primaryText, fontSize: 11, fontWeight: '800' }}>{runningSloMitigation ? 'Running…' : 'Run Mitigation Now'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Safe Mode Profile Presets */}
      <View style={{ backgroundColor: AC.card, borderWidth: 1, borderColor: AC.border, borderRadius: 14, padding: 14 }} data-testid="slo-safe-mode-presets-panel" testID="slo-safe-mode-presets-panel">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: `${AC.warning}22`, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="shield-checkmark" size={14} color={AC.warningText} />
          </View>
          <View>
            <Text style={{ color: AC.text, fontSize: 13, fontWeight: '800' }}>{tx('admin.enterpriseControlPlanePanel.auto.text.024', 'Safe Mode Profile Presets')}</Text>
            <Text style={{ color: AC.textMuted, fontSize: 10 }}>{tx('admin.enterpriseControlPlanePanel.auto.text.025', 'One-click SLO policy tuning')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {(['conservative', 'balanced', 'aggressive'] as const).map((preset) => {
            const labels: Record<string, { label: string; desc: string; icon: string; color: string }> = {
              conservative: { label: 'Conservative', desc: 'Strict / Low tolerance', icon: 'lock-closed', color: AC.error },
              balanced: { label: 'Balanced', desc: 'Moderate / Default', icon: 'options', color: AC.primary },
              aggressive: { label: 'Aggressive', desc: 'Relaxed / Dev-friendly', icon: 'flash', color: AC.successText },
            };
            const p = labels[preset];
            return (
              <TouchableOpacity accessibilityLabel={tx('admin.enterpriseControlPlanePanel.auto.accessibility.005', 'Apply safe mode preset')}
                key={preset}
                onPress={async () => {
                  try {
                    await api.post('/admin/platform-health/enterprise-standard/slo-auto-mitigation/apply-preset', { preset });
                    loadControlPlane();
                    setNotice(`Applied ${p.label} preset`);
                  } catch { setNotice('Failed to apply preset'); }
                }}
                style={{ flex: 1, minWidth: 130, backgroundColor: AC.bgSoft, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: AC.border, alignItems: 'center' }}
                data-testid={`slo-preset-${preset}-button`} testID={`slo-preset-${preset}-button`}
              >
                <Ionicons name={p.icon as any} size={16} color={p.color} />
                <Text style={{ color: AC.text, fontSize: 11, fontWeight: '800', marginTop: 4 }}>{p.label}</Text>
                <Text style={{ color: AC.textMuted, fontSize: 9, marginTop: 2, textAlign: 'center' }}>{p.desc}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flex: 1, minWidth: 290, backgroundColor: AC.card, borderRadius: 14, borderWidth: 1, borderColor: AC.border, padding: 14 }} data-testid="enterprise-control-plane-diff-section" testID="enterprise-control-plane-diff-section">
          <Text style={{ color: AC.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }} data-testid="enterprise-control-plane-diff-title" testID="enterprise-control-plane-diff-title">{tx('admin.enterpriseControlPlanePanel.auto.text.026', 'Last Auto-Fix Diff')}</Text>
          <Row label="Stale URLs before" value={String(diff?.stale_urls_before ?? 0)} testId="enterprise-control-plane-diff-before" />
          <Row label="Stale URLs after" value={String(diff?.stale_urls_after ?? 0)} testId="enterprise-control-plane-diff-after" />
          <Row label="Total fixed" value={String(diff?.total_fixed ?? 0)} testId="enterprise-control-plane-diff-fixed" />
          <Row label="Caches cleared" value={String(diff?.caches_cleared ?? 0)} testId="enterprise-control-plane-diff-caches" />
          <Row label="Rebuild status" value={diff?.rebuild_status || 'unknown'} testId="enterprise-control-plane-diff-rebuild" />
        </View>

        <View style={{ flex: 1, minWidth: 290, backgroundColor: AC.card, borderRadius: 14, borderWidth: 1, borderColor: AC.border, padding: 14 }} data-testid="enterprise-control-plane-enforcement-section" testID="enterprise-control-plane-enforcement-section">
          <Text style={{ color: AC.text, fontSize: 13, fontWeight: '800', marginBottom: 8 }} data-testid="enterprise-control-plane-enforcement-title" testID="enterprise-control-plane-enforcement-title">{tx('admin.enterpriseControlPlanePanel.auto.text.027', 'Enforcement Rule Health')}</Text>
          <Row label="Rule health score" value={`${enforcement?.health_score ?? 0}/100`} testId="enterprise-control-plane-enforcement-score" />
          <Row label="Rules status" value={enforcement?.status || 'unknown'} testId="enterprise-control-plane-enforcement-status" />
          <Row label="Regression gate" value={enforcement?.latest_regression_gate?.gate_passed ? 'passed' : 'warning'} testId="enterprise-control-plane-enforcement-regression" />
          <Row label="Growth monitor" value={enforcement?.latest_growth_monitor?.status || 'unknown'} testId="enterprise-control-plane-enforcement-growth" />
          <Row label="Admin tabs uniqueness" value={enforcement?.latest_admin_tabs_audit?.is_unique ? 'healthy' : 'duplicates'} testId="enterprise-control-plane-enforcement-tabs" />
        </View>
      </View>

      <View style={{ backgroundColor: AC.card, borderRadius: 14, borderWidth: 1, borderColor: AC.border, padding: 14 }} data-testid="tax-reconciliation-command-center-section" testID="tax-reconciliation-command-center-section">
        <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }} data-testid="tax-reconciliation-command-center-title" testID="tax-reconciliation-command-center-title">{tx('admin.enterpriseControlPlanePanel.auto.text.028', 'Tax + Reconciliation Command Center')}</Text>
        <Text style={{ color: AC.textMuted, fontSize: 10, marginBottom: 10 }} data-testid="tax-reconciliation-command-center-description" testID="tax-reconciliation-command-center-description">{tx('admin.enterpriseControlPlanePanel.auto.text.029', 'Real-time provider tax accuracy, webhook lag, and immutable ledger integrity.')}</Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 10 }} data-testid="tax-reconciliation-summary-cards" testID="tax-reconciliation-summary-cards">
          {taxSummaryCards.map((card) => (
            <View key={card.key} style={{ flex: 1, minWidth: 160, backgroundColor: AC.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: AC.border, padding: 10 }} data-testid={card.testId} testID={card.testId}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name={card.icon as any} size={13} color={card.color} />
                <Text style={{ color: AC.textMuted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
              </View>
              <Text style={{ color: card.color, fontSize: 18, fontWeight: '900', marginTop: 6 }} data-testid={`${card.testId}-value`} testID={`${card.testId}-value`}>{card.value}</Text>
            </View>
          ))}
        </View>

        <View style={{ gap: 8 }} data-testid="tax-reconciliation-provider-rows" testID="tax-reconciliation-provider-rows">
          {providerRows.length === 0 ? (
            <Text style={{ color: AC.textSec, fontSize: 11 }} data-testid="tax-reconciliation-empty" testID="tax-reconciliation-empty">{tx('admin.enterpriseControlPlanePanel.auto.text.030', 'No provider data in current window.')}</Text>
          ) : (
            providerRows.map((row: any) => {
              const rowColor = row?.status === 'healthy' ? AC.success : row?.status === 'warning' ? AC.warning : AC.error;
              return (
                <View key={row.provider} style={{ backgroundColor: AC.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: AC.border, padding: 10 }} data-testid={`tax-reconciliation-provider-${row.provider}`} testID={`tax-reconciliation-provider-${row.provider}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: AC.text, fontSize: 12, fontWeight: '800' }} data-testid={`tax-reconciliation-provider-${row.provider}-name`} testID={`tax-reconciliation-provider-${row.provider}-name`}>{row.provider_label}</Text>
                      <Text style={{ color: AC.textMuted, fontSize: 10 }} data-testid={`tax-reconciliation-provider-${row.provider}-samples`} testID={`tax-reconciliation-provider-${row.provider}-samples`}>
                        Samples: {row.sample_count} · Reconciled: {row.reconciliation_rate}%
                      </Text>
                    </View>
                    <View style={{ backgroundColor: `${rowColor}20`, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
                      <Text style={{ color: rowColor, fontSize: 9, fontWeight: '800' }} data-testid={`tax-reconciliation-provider-${row.provider}-status`} testID={`tax-reconciliation-provider-${row.provider}-status`}>{row.status}</Text>
                    </View>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                    <MetricPill
                      label="Tax Accuracy"
                      value={`${Number(row.tax_accuracy_rate ?? 0).toFixed(1)}%`}
                      valueColor={Number(row.tax_accuracy_rate ?? 0) >= 99 ? AC.success : AC.warning}
                      testId={`tax-reconciliation-provider-${row.provider}-accuracy`}
                    />
                    <MetricPill
                      label="Webhook Lag"
                      value={`${Number(row.avg_webhook_lag_seconds ?? 0).toFixed(1)}s`}
                      valueColor={Number(row.avg_webhook_lag_seconds ?? 0) < 60 ? AC.success : Number(row.avg_webhook_lag_seconds ?? 0) <= 300 ? AC.warning : AC.error}
                      testId={`tax-reconciliation-provider-${row.provider}-lag`}
                    />
                  </View>
                </View>
              );
            })
          )}
        </View>
      </View>

      <View style={{ backgroundColor: AC.card, borderRadius: 14, borderWidth: 1, borderColor: AC.border, padding: 14 }} data-testid="enterprise-control-plane-rollback-section" testID="enterprise-control-plane-rollback-section">
        <Text style={{ color: AC.text, fontSize: 14, fontWeight: '800', marginBottom: 8 }} data-testid="enterprise-control-plane-rollback-title" testID="enterprise-control-plane-rollback-title">{tx('admin.enterpriseControlPlanePanel.auto.text.031', 'Automated Remediation Rollback Checkpoints')}</Text>
        <Text style={{ color: AC.textMuted, fontSize: 10, marginBottom: 10 }} data-testid="enterprise-control-plane-rollback-description" testID="enterprise-control-plane-rollback-description">{tx('admin.enterpriseControlPlanePanel.auto.text.032', 'Checkpoints are auto-created by severity band and can restore enforcement/performance rules quickly.')}</Text>
        {checkpoints.length === 0 ? (
          <Text style={{ color: AC.textSec, fontSize: 11 }} data-testid="enterprise-control-plane-no-checkpoints" testID="enterprise-control-plane-no-checkpoints">{tx('admin.enterpriseControlPlanePanel.auto.text.033', 'No rollback checkpoints yet.')}</Text>
        ) : (
          <View style={{ gap: 8 }}>
            {checkpoints.map((cp: any) => {
              const bandColor = cp?.severity_band === 'critical' ? AC.error : cp?.severity_band === 'high' ? AC.warning : cp?.severity_band === 'medium' ? AC.primary : AC.success;
              const isRestoring = restoringId === cp.checkpoint_id;
              return (
                <View key={cp.checkpoint_id} style={{ backgroundColor: AC.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: AC.border, padding: 10 }} data-testid={`enterprise-control-plane-checkpoint-${cp.checkpoint_id}`} testID={`enterprise-control-plane-checkpoint-${cp.checkpoint_id}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: AC.text, fontSize: 11, fontWeight: '700' }} data-testid={`enterprise-control-plane-checkpoint-${cp.checkpoint_id}-id`} testID={`enterprise-control-plane-checkpoint-${cp.checkpoint_id}-id`}>{cp.checkpoint_id}</Text>
                      <Text style={{ color: AC.textMuted, fontSize: 10 }} data-testid={`enterprise-control-plane-checkpoint-${cp.checkpoint_id}-meta`} testID={`enterprise-control-plane-checkpoint-${cp.checkpoint_id}-meta`}>
                        {cp.created_at ? new Date(cp.created_at).toLocaleString() : 'Unknown time'} · Score {cp.score ?? '--'} · Issues {cp.issues ?? '--'}
                      </Text>
                    </View>
                    <View style={{ backgroundColor: `${bandColor}22`, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
                      <Text style={{ color: bandColor, fontSize: 9, fontWeight: '800' }} data-testid={`enterprise-control-plane-checkpoint-${cp.checkpoint_id}-band`} testID={`enterprise-control-plane-checkpoint-${cp.checkpoint_id}-band`}>{cp.severity_band || 'low'}</Text>
                    </View>
                    <TouchableOpacity
                      onPress={() => restoreCheckpoint(cp.checkpoint_id)}
                      disabled={!cp.restore_ready || isRestoring}
                      style={{ backgroundColor: !cp.restore_ready ? `${AC.textMuted}33` : `${AC.primary}22`, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 }}
                      data-testid={`enterprise-control-plane-restore-${cp.checkpoint_id}-button`} testID={`enterprise-control-plane-restore-${cp.checkpoint_id}-button`}
                    >
                      <Text style={{ color: !cp.restore_ready ? AC.textMuted : AC.primary, fontSize: 10, fontWeight: '800' }}>
                        {isRestoring ? 'Restoring...' : 'Restore'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              );
            })}
          </View>
        )}
      </View>
    </ScrollView>
  );
}

function Row({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }} data-testid={testId} testID={testId}>
      <Text style={{ color: AC.textMuted, fontSize: 10 }}>{label}</Text>
      <Text style={{ color: AC.textSec, fontSize: 11, fontWeight: '700' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{value}</Text>
    </View>
  );
}

function MetricPill({ label, value, valueColor, testId }: { label: string; value: string; valueColor: string; testId: string }) {    const { colors } = useTheme();
  return (
    <View style={{ backgroundColor: colors.bgSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: colors.border }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '700' }}>{label}</Text>
      <Text style={{ color: valueColor, fontSize: 11, fontWeight: '900' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{value}</Text>
    </View>
  );
}
