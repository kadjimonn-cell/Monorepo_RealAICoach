import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';

type Props = {
  colors: any;
  onNavigateToIncidentBoard?: () => void;
};

export default function GlobalParityAuditCard({ colors, onNavigateToIncidentBoard }: Props) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [acking, setAcking] = useState(false);
  const [previewIncidentActing, setPreviewIncidentActing] = useState(false);
  const [message, setMessage] = useState('');
  const [latest, setLatest] = useState<any>(null);
  const [incident, setIncident] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [trend, setTrend] = useState<any>({ total: 0, pass_count: 0, fail_count: 0, pass_rate: 0 });
  const [safeRuntime, setSafeRuntime] = useState<any>({ safe_mode_active: false, latest_safe_reasons: [] });
  const [safeConfig, setSafeConfig] = useState<any>(null);
  const [draftConfig, setDraftConfig] = useState<any>({});
  const [savingConfig, setSavingConfig] = useState(false);
  const [relaxing, setRelaxing] = useState(false);
  const [visualRunning, setVisualRunning] = useState(false);
  const [visualLatest, setVisualLatest] = useState<any>(null);
  const [visualHistory, setVisualHistory] = useState<any[]>([]);
  const [visualTrend, setVisualTrend] = useState<any>({ total: 0, pass_count: 0, fail_count: 0, pass_rate: 0 });
  const [visualRuntime, setVisualRuntime] = useState<any>({ safe_mode_active: false, latest_safe_reasons: [] });
  const [visualEscalationState, setVisualEscalationState] = useState<any>({});
  const [visualOpenIncident, setVisualOpenIncident] = useState<any>({});
  const [visualIncidentPolicy, setVisualIncidentPolicy] = useState<any>({ min_failed_baselines_to_open: 2, strict_diff_threshold: 0.12 });
  const [downloadingEvidenceJson, setDownloadingEvidenceJson] = useState(false);
  const [downloadingEvidenceCsv, setDownloadingEvidenceCsv] = useState(false);
  const [previewHygieneRunning, setPreviewHygieneRunning] = useState(false);
  const [previewHygieneLatest, setPreviewHygieneLatest] = useState<any>(null);
  const [previewHygieneTrend, setPreviewHygieneTrend] = useState<any>({ total: 0, pass_count: 0, fail_count: 0, pass_rate: 0 });
  const [previewHygieneAlertState, setPreviewHygieneAlertState] = useState<any>({});
  const [previewHygieneOpenIncident, setPreviewHygieneOpenIncident] = useState<any>({});
  const [previewHygienePolicy, setPreviewHygienePolicy] = useState<any>({ min_fail_streak_to_open: 2 });

  const updateDraft = useCallback((key: string, value: string) => {
    setDraftConfig((prev: any) => ({ ...prev, [key]: value }));
  }, []);

  const loadLatest = useCallback(async () => {
    setLoading(true);
    try {
      const [res, visualRes, previewHygieneRes] = await Promise.all([
        api.get('/admin/platform-health/global-parity-audit/latest', { silentLoading: true }),
        api.get('/admin/platform-health/fee-visibility-visual-audit/latest', { silentLoading: true }),
        api.get('/admin/platform-health/preview-cache-hygiene/latest', { silentLoading: true }),
      ]);
      setLatest(res?.data?.latest || null);
      setIncident(res?.data?.latest_open_incident || null);
      setHistory(res?.data?.history || []);
      setTrend(res?.data?.trend || { total: 0, pass_count: 0, fail_count: 0, pass_rate: 0 });
      const cfg = res?.data?.safe_config || null;
      const runtime = res?.data?.safe_runtime || { safe_mode_active: false, latest_safe_reasons: [] };
      setSafeConfig(cfg);
      setSafeRuntime(runtime);

      setVisualLatest(visualRes?.data?.latest || null);
      setVisualHistory(visualRes?.data?.history || []);
      setVisualTrend(visualRes?.data?.trend || { total: 0, pass_count: 0, fail_count: 0, pass_rate: 0 });
      setVisualRuntime(visualRes?.data?.safe_runtime || { safe_mode_active: false, latest_safe_reasons: [] });
      setVisualEscalationState(visualRes?.data?.escalation_state || {});
      setVisualOpenIncident(visualRes?.data?.latest_open_incident || {});
      setVisualIncidentPolicy(visualRes?.data?.incident_policy || { min_failed_baselines_to_open: 2, strict_diff_threshold: 0.12 });

      setPreviewHygieneLatest(previewHygieneRes?.data?.latest || null);
      setPreviewHygieneTrend(previewHygieneRes?.data?.trend || { total: 0, pass_count: 0, fail_count: 0, pass_rate: 0 });
      setPreviewHygieneAlertState(previewHygieneRes?.data?.alert_state || {});
      setPreviewHygieneOpenIncident(previewHygieneRes?.data?.latest_open_incident || {});
      setPreviewHygienePolicy(previewHygieneRes?.data?.incident_policy || { min_fail_streak_to_open: 2 });

      if (cfg) {
        setDraftConfig({
          hourly_min_interval_minutes: String(cfg?.hourly_min_interval_minutes ?? ''),
          nightly_min_interval_minutes: String(cfg?.nightly_min_interval_minutes ?? ''),
          min_disk_mb: String(cfg?.min_disk_mb ?? ''),
          max_load_avg: String(cfg?.max_load_avg ?? ''),
          max_runtime_seconds: String(cfg?.max_runtime_seconds ?? ''),
        });
      }
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.globalParityAudit.messages.failedToLoad', 'Failed to load global parity status.'));
    } finally {
      setLoading(false);
    }
  }, [tx]);

  useEffect(() => {
    void loadLatest();
  }, [loadLatest]);

  const runAudit = useCallback(async () => {
    setRunning(true);
    setMessage('');
    try {
      const res = await api.post('/admin/platform-health/global-parity-audit/run?run_admin_checks=true');
      setLatest(res?.data?.audit || null);
      setIncident(res?.data?.incident || null);
      const outcome = res?.data?.audit?.overall_status === 'pass'
        ? tx('operationsConsole.globalParityAudit.messages.pass', 'Parity audit passed.')
        : tx('operationsConsole.globalParityAudit.messages.fail', 'Parity audit failed and incident has been created.');
      setMessage(outcome);
      await loadLatest();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.globalParityAudit.messages.failedToRun', 'Failed to run parity audit.'));
    } finally {
      setRunning(false);
    }
  }, [tx, loadLatest]);

  const runVisualAudit = useCallback(async () => {
    setVisualRunning(true);
    setMessage('');
    try {
      const res = await api.post('/admin/platform-health/fee-visibility-visual-audit/run?triggered_by=manual:admin');
      setVisualLatest(res?.data?.audit || null);
      setVisualEscalationState((prev: any) => ({
        ...(prev || {}),
        ...(res?.data?.escalation || {}),
        last_audit_id: res?.data?.audit?.audit_id || prev?.last_audit_id,
      }));
      const outcome = res?.data?.audit?.overall_status === 'pass'
        ? tx('operationsConsole.feeVisibilityAudit.messages.pass', 'Fee visibility visual audit passed.')
        : tx('operationsConsole.feeVisibilityAudit.messages.fail', 'Visual drift detected in fee visibility contract.');
      const escalationSent = Number(res?.data?.escalation?.sent || 0);
      const incidentOpened = Boolean(res?.data?.incident?.opened);
      const escalationText = escalationSent > 0
        ? ` ${tx('operationsConsole.feeVisibilityAudit.messages.escalationSent', 'Escalation notification dispatched to admins.')}`
        : '';
      const incidentText = incidentOpened
        ? ` ${tx('operationsConsole.feeVisibilityAudit.messages.incidentOpened', 'Visual drift incident opened automatically.')}`
        : '';
      setMessage(`${outcome}${escalationText}${incidentText}`);
      await loadLatest();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.feeVisibilityAudit.messages.failedToRun', 'Failed to run fee visibility visual audit.'));
    } finally {
      setVisualRunning(false);
    }
  }, [tx, loadLatest]);

  const downloadVisualEvidence = useCallback(async (format: 'json' | 'csv') => {
    if (format === 'json') {
      setDownloadingEvidenceJson(true);
    } else {
      setDownloadingEvidenceCsv(true);
    }
    setMessage('');
    try {
      const endpoint = format === 'json'
        ? '/admin/platform-health/fee-visibility-visual-audit/evidence/latest.json'
        : '/admin/platform-health/fee-visibility-visual-audit/evidence/latest.csv';
      const res = await api.get(endpoint, { responseType: 'text', silentLoading: true, timeout: 45000 });
      const content = typeof res?.data === 'string'
        ? res.data
        : format === 'json'
          ? JSON.stringify(res?.data || {}, null, 2)
          : String(res?.data || '');

      if (typeof window === 'undefined') {
        setMessage(tx('operationsConsole.feeVisibilityAudit.messages.downloadWebOnly', 'Evidence download is available on web session.'));
        return;
      }

      const mime = format === 'json' ? 'application/json' : 'text/csv;charset=utf-8;';
      const blob = new Blob([content], { type: mime });
      const objectUrl = window.URL.createObjectURL(blob);
      const auditId = String(visualLatest?.audit_id || 'latest');
      const fileName = format === 'json'
        ? `fee-visibility-visual-evidence-${auditId}.json`
        : `fee-visibility-visual-evidence-${auditId}.csv`;

      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = fileName;
      anchor.setAttribute('data-testid', `fee-visibility-visual-audit-download-${format}-anchor`);
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.URL.revokeObjectURL(objectUrl);
      setMessage(tx('operationsConsole.feeVisibilityAudit.messages.downloaded', 'Evidence file downloaded.'));
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.feeVisibilityAudit.messages.downloadFailed', 'Failed to download evidence bundle.'));
    } finally {
      if (format === 'json') {
        setDownloadingEvidenceJson(false);
      } else {
        setDownloadingEvidenceCsv(false);
      }
    }
  }, [tx, visualLatest?.audit_id]);

  const runPreviewHygiene = useCallback(async () => {
    setPreviewHygieneRunning(true);
    setMessage('');
    try {
      const res = await api.post('/admin/platform-health/preview-cache-hygiene/run?triggered_by=manual:admin');
      setPreviewHygieneLatest(res?.data?.scan || null);
      const outcome = String(res?.data?.scan?.status || '').toLowerCase() === 'pass'
        ? tx('operationsConsole.previewHygiene.messages.pass', 'Preview cache hygiene check passed.')
        : tx('operationsConsole.previewHygiene.messages.fail', 'Preview cache hygiene drift detected.');
      const alertSent = Number(res?.data?.alert?.sent || 0);
      const incidentOpened = Boolean(res?.data?.incident?.opened);
      const extra = `${alertSent > 0 ? ' Admin alerts sent.' : ''}${incidentOpened ? ' Incident opened automatically.' : ''}`;
      setMessage(`${outcome}${extra}`.trim());
      await loadLatest();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.previewHygiene.messages.failedToRun', 'Failed to run preview cache hygiene scan.'));
    } finally {
      setPreviewHygieneRunning(false);
    }
  }, [tx, loadLatest]);

  const acknowledgePreviewIncident = useCallback(async () => {
    if (!previewHygieneOpenIncident?.incident_id) return;
    setPreviewIncidentActing(true);
    setMessage('');
    try {
      await api.post(`/admin/platform-health/global-parity-audit/incidents/${previewHygieneOpenIncident.incident_id}/ack`);
      setMessage(tx('operationsConsole.previewHygiene.messages.incidentAcknowledged', 'Preview hygiene incident acknowledged.'));
      await loadLatest();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.previewHygiene.messages.incidentAckFailed', 'Failed to acknowledge preview hygiene incident.'));
    } finally {
      setPreviewIncidentActing(false);
    }
  }, [previewHygieneOpenIncident?.incident_id, tx, loadLatest]);

  const resolvePreviewIncident = useCallback(async () => {
    if (!previewHygieneOpenIncident?.incident_id) return;
    setPreviewIncidentActing(true);
    setMessage('');
    try {
      await api.post(`/admin/platform-health/global-parity-audit/incidents/${previewHygieneOpenIncident.incident_id}/resolve?note=resolved_from_preview_hygiene_widget`);
      setMessage(tx('operationsConsole.previewHygiene.messages.incidentResolved', 'Preview hygiene incident resolved.'));
      await loadLatest();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.previewHygiene.messages.incidentResolveFailed', 'Failed to resolve preview hygiene incident.'));
    } finally {
      setPreviewIncidentActing(false);
    }
  }, [previewHygieneOpenIncident?.incident_id, tx, loadLatest]);

  const saveSafeConfig = useCallback(async () => {
    setSavingConfig(true);
    setMessage('');
    try {
      const payload = {
        hourly_min_interval_minutes: Number(draftConfig?.hourly_min_interval_minutes || 0),
        nightly_min_interval_minutes: Number(draftConfig?.nightly_min_interval_minutes || 0),
        min_disk_mb: Number(draftConfig?.min_disk_mb || 0),
        max_load_avg: Number(draftConfig?.max_load_avg || 0),
        max_runtime_seconds: Number(draftConfig?.max_runtime_seconds || 0),
      };
      const res = await api.post('/admin/platform-health/global-parity-audit/safe-config', payload);
      setSafeConfig(res?.data?.safe_config || safeConfig);
      setMessage(tx('operationsConsole.globalParityAudit.messages.configSaved', 'Safe thresholds saved.'));
      await loadLatest();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.globalParityAudit.messages.configSaveFailed', 'Failed to save safe thresholds.'));
    } finally {
      setSavingConfig(false);
    }
  }, [draftConfig, safeConfig, tx, loadLatest]);

  const relaxGuardrails = useCallback(async () => {
    setRelaxing(true);
    setMessage('');
    try {
      await api.post('/admin/platform-health/global-parity-audit/safe-config/relax-temporary');
      setMessage(tx('operationsConsole.globalParityAudit.messages.relaxed', 'Safe guardrails relaxed for 30 minutes. Automatic rollback enabled.'));
      await loadLatest();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.globalParityAudit.messages.relaxFailed', 'Failed to relax guardrails.'));
    } finally {
      setRelaxing(false);
    }
  }, [tx, loadLatest]);

  const acknowledgeIncident = useCallback(async () => {
    if (!incident?.incident_id) return;
    setAcking(true);
    try {
      const res = await api.post(`/admin/platform-health/global-parity-audit/incidents/${incident.incident_id}/ack`);
      setIncident(res?.data?.incident || incident);
      setMessage(tx('operationsConsole.globalParityAudit.messages.acknowledged', 'Incident acknowledged.'));
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || tx('operationsConsole.globalParityAudit.messages.ackFailed', 'Failed to acknowledge incident.'));
    } finally {
      setAcking(false);
    }
  }, [incident, tx]);

  const status = useMemo(() => {
    const raw = String(latest?.overall_status || '').toLowerCase();
    if (raw === 'pass') return 'PASS';
    if (raw === 'fail') return 'FAIL';
    return 'UNKNOWN';
  }, [latest]);

  const statusColor = status === 'PASS' ? colors.successText : status === 'FAIL' ? colors.error : colors.warning;
  const safeModeActive = Boolean(safeRuntime?.safe_mode_active || safeConfig?.maintenance_relax_active);
  const safeModeColor = safeModeActive ? colors.warning : colors.successText;
  const safeReasons = (safeRuntime?.latest_safe_reasons || []) as string[];
  const visualStatus = useMemo(() => {
    const raw = String(visualLatest?.overall_status || '').toLowerCase();
    if (raw === 'pass') return 'PASS';
    if (raw === 'fail') return 'FAIL';
    return 'UNKNOWN';
  }, [visualLatest]);
  const visualStatusColor = visualStatus === 'PASS' ? colors.successText : visualStatus === 'FAIL' ? colors.error : colors.warning;
  const visualSafeReasons = (visualRuntime?.latest_safe_reasons || []) as string[];
  const visualConsecutiveFails = Number(visualEscalationState?.consecutive_fail_count || 0);
  const visualEscalationSentCount = Number(visualEscalationState?.sent || 0);
  const incidentThreshold = Number(visualIncidentPolicy?.min_failed_baselines_to_open || 2);
  const strictDiffThreshold = Number(visualIncidentPolicy?.strict_diff_threshold || 0.12);
  const previewHygieneStatus = useMemo(() => {
    const raw = String(previewHygieneLatest?.status || '').toLowerCase();
    if (raw === 'pass') return 'PASS';
    if (raw === 'fail') return 'FAIL';
    return 'UNKNOWN';
  }, [previewHygieneLatest]);
  const previewHygieneStatusColor = previewHygieneStatus === 'PASS' ? colors.successText : previewHygieneStatus === 'FAIL' ? colors.error : colors.warning;
  const previewHygieneFailStreak = Number(previewHygieneAlertState?.fail_streak || 0);
  const previewHygieneAlertSent = Number(previewHygieneAlertState?.sent || 0);
  const previewHygieneIncidentThreshold = Number(previewHygienePolicy?.min_fail_streak_to_open || 2);

  return (
    <View style={{
      borderRadius: 14,
      borderWidth: 1,
      borderColor: status === 'FAIL' ? colors.error : colors.border,
      backgroundColor: colors.card,
      padding: 14,
      marginBottom: 12,
    }} data-testid="global-parity-audit-card" testID="global-parity-audit-card">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} data-testid="global-parity-audit-title" testID="global-parity-audit-title">
            {tx('operationsConsole.globalParityAudit.title', 'Global Parity Audit')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="global-parity-audit-subtitle" testID="global-parity-audit-subtitle">
            {tx('operationsConsole.globalParityAudit.subtitle', 'One-click external-vs-runtime contract verification with incident creation.')}
          </Text>
        </View>
        <View style={{ backgroundColor: `${statusColor}20`, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="global-parity-audit-status-pill" testID="global-parity-audit-status-pill">
          <Text style={{ color: statusColor, fontSize: 11, fontWeight: '800' }} data-testid="global-parity-audit-status-text" testID="global-parity-audit-status-text">
            {status}
          </Text>
        </View>
      </View>

      <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <View
          style={{ backgroundColor: `${safeModeColor}20`, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }}
          data-testid="global-parity-safe-mode-pill"
          testID="global-parity-safe-mode-pill"
        >
          <Text style={{ color: safeModeColor, fontSize: 11, fontWeight: '800' }}>
            {safeModeActive
              ? tx('operationsConsole.globalParityAudit.safeModeActive', 'Safe Mode Active')
              : tx('operationsConsole.globalParityAudit.safeModeNormal', 'Safe Mode Normal')}
          </Text>
        </View>
        {!!safeConfig?.maintenance_relax_until && (
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="global-parity-relax-until" testID="global-parity-relax-until">
            {tx('operationsConsole.globalParityAudit.relaxedUntil', 'Relaxed until')}: {new Date(safeConfig.maintenance_relax_until).toLocaleTimeString()}
          </Text>
        )}
      </View>

      <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 6 }} data-testid="global-parity-safe-reasons" testID="global-parity-safe-reasons">
        {tx('operationsConsole.globalParityAudit.safeReasons', 'Latest safe_reasons')}: {safeReasons.length ? safeReasons.join(', ') : tx('operationsConsole.globalParityAudit.none', 'none')}
      </Text>

      {loading ? (
        <View style={{ marginTop: 12, alignItems: 'center' }} data-testid="global-parity-audit-loading" testID="global-parity-audit-loading">
          <ActivityIndicator size="small" color={colors.primary} />
        </View>
      ) : (
        <View style={{ marginTop: 12, gap: 6 }}>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="global-parity-audit-local-instance" testID="global-parity-audit-local-instance">
            {tx('operationsConsole.globalParityAudit.localInstance', 'Local Instance')}: {latest?.local_instance_id || '—'}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="global-parity-audit-external-instance" testID="global-parity-audit-external-instance">
            {tx('operationsConsole.globalParityAudit.externalInstance', 'External Instance')}: {latest?.external_instance_id || '—'}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="global-parity-audit-last-run-at" testID="global-parity-audit-last-run-at">
            {tx('operationsConsole.globalParityAudit.lastRun', 'Last run')}: {latest?.created_at ? new Date(latest.created_at).toLocaleString() : tx('operationsConsole.globalParityAudit.never', 'Never')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="global-parity-audit-instance-match" testID="global-parity-audit-instance-match">
            {tx('operationsConsole.globalParityAudit.instanceMatch', 'Instance match')}: {latest?.instance_match ? tx('operationsConsole.globalParityAudit.yes', 'Yes') : tx('operationsConsole.globalParityAudit.no', 'No')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="global-parity-audit-trend-summary" testID="global-parity-audit-trend-summary">
            {tx('operationsConsole.globalParityAudit.trend', 'Trend (last checks)')}: {trend?.pass_count || 0} {tx('operationsConsole.globalParityAudit.pass', 'pass')} / {trend?.fail_count || 0} {tx('operationsConsole.globalParityAudit.fail', 'fail')} ({trend?.pass_rate || 0}% {tx('operationsConsole.globalParityAudit.passRate', 'pass rate')})
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }} data-testid="global-parity-audit-trend-points" testID="global-parity-audit-trend-points">
            {history.slice(0, 12).map((item, idx) => {
              const ok = String(item?.overall_status || '').toLowerCase() === 'pass';
              return (
                <View
                  key={item?.audit_id || idx}
                  style={{ width: 10, height: 10, borderRadius: 999, backgroundColor: ok ? colors.successText : colors.error, opacity: 0.9 }}
                  data-testid={`global-parity-audit-trend-point-${idx}`}
                  testID={`global-parity-audit-trend-point-${idx}`}
                />
              );
            })}
          </View>
        </View>
      )}

      {!!message && (
        <Text style={{ marginTop: 10, color: colors.text, fontSize: 12 }} data-testid="global-parity-audit-message" testID="global-parity-audit-message">
          {message}
        </Text>
      )}

      <View
        style={{
          marginTop: 12,
          padding: 10,
          borderWidth: 1,
          borderColor: colors.border,
          borderRadius: 10,
          backgroundColor: `${colors.primary}08`,
          gap: 8,
        }}
        data-testid="global-parity-safe-config-panel"
        testID="global-parity-safe-config-panel"
      >
        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>
          {tx('operationsConsole.globalParityAudit.safeConfigTitle', 'Safe Threshold Controls')}
        </Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {[
            { key: 'hourly_min_interval_minutes', label: tx('operationsConsole.globalParityAudit.hourlyCooldown', 'Hourly Cooldown (min)') },
            { key: 'nightly_min_interval_minutes', label: tx('operationsConsole.globalParityAudit.nightlyCooldown', 'Nightly Cooldown (min)') },
            { key: 'min_disk_mb', label: tx('operationsConsole.globalParityAudit.minDisk', 'Min Disk MB') },
            { key: 'max_load_avg', label: tx('operationsConsole.globalParityAudit.maxLoad', 'Max Load Avg') },
            { key: 'max_runtime_seconds', label: tx('operationsConsole.globalParityAudit.maxRuntime', 'Max Runtime (s)') },
          ].map((field) => (
            <View key={field.key} style={{ minWidth: 160, flex: 1 }}>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginBottom: 4 }}>{field.label}</Text>
              <TextInput accessibilityLabel="Text input"
                value={String(draftConfig?.[field.key] ?? '')}
                onChangeText={(text) => updateDraft(field.key, text)}
                keyboardType="numeric"
                style={{
                  borderWidth: 1,
                  borderColor: colors.border,
                  borderRadius: 8,
                  paddingHorizontal: 10,
                  paddingVertical: 7,
                  color: colors.text,
                  backgroundColor: colors.card,
                  fontSize: 12,
                }}
                data-testid={`global-parity-safe-config-${field.key}-input`}
                testID={`global-parity-safe-config-${field.key}-input`}
              />
            </View>
          ))}
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TouchableOpacity accessibilityLabel="Global parity safe config save button"
            onPress={saveSafeConfig}
            disabled={savingConfig}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8,
              backgroundColor: colors.primary, opacity: savingConfig ? 0.7 : 1,
            }}
            data-testid="global-parity-safe-config-save-button"
            testID="global-parity-safe-config-save-button"
          >
            {savingConfig ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="save-outline" size={14} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>
              {tx('operationsConsole.globalParityAudit.saveThresholds', 'Save Thresholds')}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity accessibilityLabel="Global parity safe relax button"
            onPress={relaxGuardrails}
            disabled={relaxing}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8,
              backgroundColor: `${colors.warning}20`, borderWidth: 1, borderColor: `${colors.warning}60`, opacity: relaxing ? 0.7 : 1,
            }}
            data-testid="global-parity-safe-relax-button"
            testID="global-parity-safe-relax-button"
          >
            {relaxing ? <ActivityIndicator size="small" color={colors.warning} /> : <Ionicons name="timer-outline" size={14} color={colors.warning} />}
            <Text style={{ color: colors.warning, fontSize: 12, fontWeight: '800' }}>
              {tx('operationsConsole.globalParityAudit.relaxFor30', 'Temporarily Relax Safe Guardrails (30m)')}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      <View
        style={{
          marginTop: 12,
          padding: 10,
          borderWidth: 1,
          borderColor: visualStatus === 'FAIL' ? colors.error : colors.border,
          borderRadius: 10,
          backgroundColor: `${colors.primary}08`,
          gap: 8,
        }}
        data-testid="fee-visibility-visual-audit-panel"
        testID="fee-visibility-visual-audit-panel"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="fee-visibility-visual-audit-title" testID="fee-visibility-visual-audit-title">
              {tx('operationsConsole.feeVisibilityAudit.title', 'Customer-safe Fee Visibility Contract')}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }} data-testid="fee-visibility-visual-audit-subtitle" testID="fee-visibility-visual-audit-subtitle">
              {tx('operationsConsole.feeVisibilityAudit.subtitle', 'Pixel-diff visual baseline monitor with safe auto-runs (hourly/nightly).')}
            </Text>
          </View>
          <View style={{ backgroundColor: `${visualStatusColor}20`, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="fee-visibility-visual-audit-status-pill" testID="fee-visibility-visual-audit-status-pill">
            <Text style={{ color: visualStatusColor, fontSize: 10, fontWeight: '800' }} data-testid="fee-visibility-visual-audit-status-text" testID="fee-visibility-visual-audit-status-text">
              {visualStatus}
            </Text>
          </View>
        </View>

        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="fee-visibility-visual-audit-last-run" testID="fee-visibility-visual-audit-last-run">
          {tx('operationsConsole.feeVisibilityAudit.lastRun', 'Last run')}: {visualLatest?.created_at ? new Date(visualLatest.created_at).toLocaleString() : tx('operationsConsole.globalParityAudit.never', 'Never')}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="fee-visibility-visual-audit-metrics" testID="fee-visibility-visual-audit-metrics">
          {tx('operationsConsole.feeVisibilityAudit.metrics', 'Drift / Missing / Baselines')}: {visualLatest?.drift_count || 0} / {visualLatest?.missing_count || 0} / {visualLatest?.baseline_count || 0}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="fee-visibility-visual-audit-pass-rate" testID="fee-visibility-visual-audit-pass-rate">
          {tx('operationsConsole.feeVisibilityAudit.trend', 'Trend pass rate')}: {visualTrend?.pass_rate || 0}% ({visualTrend?.pass_count || 0}/{visualTrend?.total || 0})
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="fee-visibility-visual-audit-incident-policy" testID="fee-visibility-visual-audit-incident-policy">
          {tx('operationsConsole.feeVisibilityAudit.incidentPolicy', 'Incident policy')}: {tx('operationsConsole.feeVisibilityAudit.threshold', 'open when failed baselines ≥')} {incidentThreshold} • {tx('operationsConsole.feeVisibilityAudit.strictDiff', 'strict diff threshold')} {strictDiffThreshold}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="fee-visibility-visual-audit-open-incident" testID="fee-visibility-visual-audit-open-incident">
          {tx('operationsConsole.feeVisibilityAudit.latestIncident', 'Latest open incident')}: {visualOpenIncident?.incident_id || tx('operationsConsole.globalParityAudit.none', 'none')}
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }} data-testid="fee-visibility-visual-audit-trend-points" testID="fee-visibility-visual-audit-trend-points">
          {(visualHistory || []).slice(0, 12).map((item: any, idx: number) => {
            const ok = String(item?.overall_status || '').toLowerCase() === 'pass';
            return (
              <View
                key={`${item?.audit_id || idx}`}
                style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: ok ? colors.successText : colors.error, opacity: 0.9 }}
                data-testid={`fee-visibility-visual-audit-trend-point-${idx}`}
                testID={`fee-visibility-visual-audit-trend-point-${idx}`}
              />
            );
          })}
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="fee-visibility-visual-audit-safe-reasons" testID="fee-visibility-visual-audit-safe-reasons">
          {tx('operationsConsole.feeVisibilityAudit.safeReasons', 'Latest safe_reasons')}: {visualSafeReasons.length ? visualSafeReasons.join(', ') : tx('operationsConsole.globalParityAudit.none', 'none')}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="fee-visibility-visual-audit-fail-streak" testID="fee-visibility-visual-audit-fail-streak">
          {tx('operationsConsole.feeVisibilityAudit.failStreak', 'Consecutive failed runs')}: {visualConsecutiveFails}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="fee-visibility-visual-audit-escalation-sent" testID="fee-visibility-visual-audit-escalation-sent">
          {tx('operationsConsole.feeVisibilityAudit.escalationSent', 'Escalation notifications sent (latest run)')}: {visualEscalationSentCount}
        </Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TouchableOpacity accessibilityLabel="Fee visibility visual audit run button"
            onPress={runVisualAudit}
            disabled={visualRunning}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8,
              backgroundColor: colors.primary, opacity: visualRunning ? 0.7 : 1,
            }}
            data-testid="fee-visibility-visual-audit-run-button"
            testID="fee-visibility-visual-audit-run-button"
          >
            {visualRunning ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="scan" size={14} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>
              {visualRunning
                ? tx('operationsConsole.feeVisibilityAudit.running', 'Running...')
                : tx('operationsConsole.feeVisibilityAudit.runNow', 'Run Visual Contract Audit')}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity accessibilityLabel="Fee visibility visual audit download json button"
            onPress={() => downloadVisualEvidence('json')}
            disabled={downloadingEvidenceJson}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8,
              backgroundColor: `${colors.successText}20`, borderWidth: 1, borderColor: `${colors.successText}55`,
              opacity: downloadingEvidenceJson ? 0.7 : 1,
            }}
            data-testid="fee-visibility-visual-audit-download-json-button"
            testID="fee-visibility-visual-audit-download-json-button"
          >
            {downloadingEvidenceJson ? <ActivityIndicator size="small" color={colors.successText} /> : <Ionicons name="download-outline" size={14} color={colors.successText} />}
            <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '800' }}>
              {downloadingEvidenceJson
                ? tx('operationsConsole.feeVisibilityAudit.downloadingJson', 'Downloading JSON...')
                : tx('operationsConsole.feeVisibilityAudit.downloadJson', 'Download Evidence JSON')}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity accessibilityLabel="Fee visibility visual audit download csv button"
            onPress={() => downloadVisualEvidence('csv')}
            disabled={downloadingEvidenceCsv}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8,
              backgroundColor: `${colors.warning}20`, borderWidth: 1, borderColor: `${colors.warning}55`,
              opacity: downloadingEvidenceCsv ? 0.7 : 1,
            }}
            data-testid="fee-visibility-visual-audit-download-csv-button"
            testID="fee-visibility-visual-audit-download-csv-button"
          >
            {downloadingEvidenceCsv ? <ActivityIndicator size="small" color={colors.warning} /> : <Ionicons name="download-outline" size={14} color={colors.warning} />}
            <Text style={{ color: colors.warning, fontSize: 12, fontWeight: '800' }}>
              {downloadingEvidenceCsv
                ? tx('operationsConsole.feeVisibilityAudit.downloadingCsv', 'Downloading CSV...')
                : tx('operationsConsole.feeVisibilityAudit.downloadCsv', 'Download Evidence CSV')}
            </Text>
          </TouchableOpacity>
        </View>

        {Array.isArray(visualLatest?.comparisons) && visualLatest.comparisons.length > 0 ? (
          <View style={{ gap: 4 }} data-testid="fee-visibility-visual-audit-comparisons" testID="fee-visibility-visual-audit-comparisons">
            {visualLatest.comparisons.slice(0, 3).map((item: any, idx: number) => (
              <Text
                key={`${item?.baseline_key || idx}`}
                style={{ color: colors.textMuted, fontSize: 10 }}
                data-testid={`fee-visibility-visual-audit-comparison-${idx}`}
                testID={`fee-visibility-visual-audit-comparison-${idx}`}
              >
                {item?.label || item?.baseline_key}: {item?.status || 'unknown'} {typeof item?.best_diff_ratio === 'number' ? `(${Math.round(item.best_diff_ratio * 10000) / 100}% diff)` : ''}
              </Text>
            ))}
          </View>
        ) : null}
      </View>

      <View
        style={{
          marginTop: 12,
          padding: 10,
          borderWidth: 1,
          borderColor: previewHygieneStatus === 'FAIL' ? colors.error : colors.border,
          borderRadius: 10,
          backgroundColor: `${colors.primary}08`,
          gap: 8,
        }}
        data-testid="preview-cache-hygiene-panel"
        testID="preview-cache-hygiene-panel"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="preview-cache-hygiene-title" testID="preview-cache-hygiene-title">
              {tx('operationsConsole.previewHygiene.title', 'Preview Cache Hygiene Monitor')}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }} data-testid="preview-cache-hygiene-subtitle" testID="preview-cache-hygiene-subtitle">
              {tx('operationsConsole.previewHygiene.subtitle', 'Auto-checks stale preview routing and service-worker cache drift hourly/nightly.')}
            </Text>
          </View>
          <View style={{ backgroundColor: `${previewHygieneStatusColor}20`, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="preview-cache-hygiene-status-pill" testID="preview-cache-hygiene-status-pill">
            <Text style={{ color: previewHygieneStatusColor, fontSize: 10, fontWeight: '800' }} data-testid="preview-cache-hygiene-status-text" testID="preview-cache-hygiene-status-text">
              {previewHygieneStatus}
            </Text>
          </View>
        </View>

        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-cache-hygiene-last-run" testID="preview-cache-hygiene-last-run">
          {tx('operationsConsole.previewHygiene.lastRun', 'Last run')}: {previewHygieneLatest?.created_at ? new Date(previewHygieneLatest.created_at).toLocaleString() : tx('operationsConsole.globalParityAudit.never', 'Never')}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-cache-hygiene-trend" testID="preview-cache-hygiene-trend">
          {tx('operationsConsole.previewHygiene.trend', 'Trend pass rate')}: {previewHygieneTrend?.pass_rate || 0}% ({previewHygieneTrend?.pass_count || 0}/{previewHygieneTrend?.total || 0})
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-cache-hygiene-fail-streak" testID="preview-cache-hygiene-fail-streak">
          {tx('operationsConsole.previewHygiene.failStreak', 'Fail streak')}: {previewHygieneFailStreak} • {tx('operationsConsole.previewHygiene.alertSent', 'alerts sent')}: {previewHygieneAlertSent}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-cache-hygiene-policy" testID="preview-cache-hygiene-policy">
          {tx('operationsConsole.previewHygiene.policy', 'Incident policy')}: {tx('operationsConsole.previewHygiene.openOnStreak', 'open incident when fail streak ≥')} {previewHygieneIncidentThreshold}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="preview-cache-hygiene-open-incident" testID="preview-cache-hygiene-open-incident">
          {tx('operationsConsole.previewHygiene.latestIncident', 'Latest open incident')}: {previewHygieneOpenIncident?.incident_id || tx('operationsConsole.globalParityAudit.none', 'none')}
        </Text>

        {Array.isArray(previewHygieneOpenIncident?.incident_actions) && previewHygieneOpenIncident.incident_actions.length > 0 ? (
          <View style={{ gap: 4 }} data-testid="preview-cache-hygiene-incident-timeline" testID="preview-cache-hygiene-incident-timeline">
            <Text style={{ color: colors.text, fontSize: 10, fontWeight: '800' }} data-testid="preview-cache-hygiene-incident-timeline-title" testID="preview-cache-hygiene-incident-timeline-title">
              {tx('operationsConsole.previewHygiene.timeline', 'Incident action timeline')}
            </Text>
            {previewHygieneOpenIncident.incident_actions.slice().reverse().slice(0, 6).map((entry: any, idx: number) => (
              <Text
                key={`${entry?.at || 'na'}-${idx}`}
                style={{ color: colors.textMuted, fontSize: 10 }}
                data-testid={`preview-cache-hygiene-incident-timeline-item-${idx}`}
                testID={`preview-cache-hygiene-incident-timeline-item-${idx}`}
              >
                {`${String(entry?.action || 'action').toUpperCase()} • ${entry?.actor_email || entry?.actor_id || 'system'} • ${entry?.at ? new Date(entry.at).toLocaleString() : '-'}`}
              </Text>
            ))}
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <TouchableOpacity accessibilityLabel="Preview cache hygiene run button"
            onPress={runPreviewHygiene}
            disabled={previewHygieneRunning}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8,
              backgroundColor: colors.primary, opacity: previewHygieneRunning ? 0.7 : 1,
            }}
            data-testid="preview-cache-hygiene-run-button"
            testID="preview-cache-hygiene-run-button"
          >
            {previewHygieneRunning ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="shield-checkmark-outline" size={14} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>
              {previewHygieneRunning
                ? tx('operationsConsole.previewHygiene.running', 'Running...')
                : tx('operationsConsole.previewHygiene.runNow', 'Run Preview Hygiene Check')}
            </Text>
          </TouchableOpacity>

          {!!previewHygieneOpenIncident?.incident_id && previewHygieneOpenIncident?.status !== 'acknowledged' && previewHygieneOpenIncident?.status !== 'resolved' && (
            <TouchableOpacity accessibilityLabel="Preview cache hygiene ack incident button"
              onPress={acknowledgePreviewIncident}
              disabled={previewIncidentActing}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8,
                backgroundColor: colors.card,
                borderWidth: 1,
                borderColor: colors.border,
                opacity: previewIncidentActing ? 0.7 : 1,
              }}
              data-testid="preview-cache-hygiene-ack-incident-button"
              testID="preview-cache-hygiene-ack-incident-button"
            >
              {previewIncidentActing ? <ActivityIndicator size="small" color={colors.text} /> : <Ionicons name="checkmark-done" size={14} color={colors.text} />}
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>
                {tx('operationsConsole.previewHygiene.ackIncident', 'Acknowledge Incident')}
              </Text>
            </TouchableOpacity>
          )}

          {!!previewHygieneOpenIncident?.incident_id && previewHygieneOpenIncident?.status !== 'resolved' && (
            <TouchableOpacity accessibilityLabel="Preview cache hygiene resolve incident button"
              onPress={resolvePreviewIncident}
              disabled={previewIncidentActing}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                borderRadius: 9, paddingHorizontal: 12, paddingVertical: 8,
                backgroundColor: `${colors.successText}18`,
                borderWidth: 1,
                borderColor: `${colors.successText}45`,
                opacity: previewIncidentActing ? 0.7 : 1,
              }}
              data-testid="preview-cache-hygiene-resolve-incident-button"
              testID="preview-cache-hygiene-resolve-incident-button"
            >
              {previewIncidentActing ? <ActivityIndicator size="small" color={colors.successText} /> : <Ionicons name="checkmark-circle-outline" size={14} color={colors.successText} />}
              <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '800' }}>
                {tx('operationsConsole.previewHygiene.resolveIncident', 'Resolve Incident')}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        <TouchableOpacity accessibilityLabel="Global parity audit run button"
          onPress={runAudit}
          disabled={running}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
            paddingHorizontal: 12,
            paddingVertical: 9,
            borderRadius: 10,
            backgroundColor: colors.primary,
            opacity: running ? 0.7 : 1,
          }}
          data-testid="global-parity-audit-run-button"
          testID="global-parity-audit-run-button"
        >
          {running ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="pulse" size={14} color={colors.primaryText} />}
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>
            {running ? tx('operationsConsole.globalParityAudit.running', 'Running...') : tx('operationsConsole.globalParityAudit.runNow', 'Run Global Parity Audit')}
          </Text>
        </TouchableOpacity>

        {!!incident?.incident_id && (
          <TouchableOpacity accessibilityLabel="Global parity audit open incident board button"
            onPress={onNavigateToIncidentBoard}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              paddingHorizontal: 12,
              paddingVertical: 9,
              borderRadius: 10,
              backgroundColor: `${colors.error}14`,
              borderWidth: 1,
              borderColor: `${colors.error}35`,
            }}
            data-testid="global-parity-audit-open-incident-board-button"
            testID="global-parity-audit-open-incident-board-button"
          >
            <Ionicons name="warning" size={14} color={colors.error} />
            <Text style={{ color: colors.error, fontSize: 12, fontWeight: '800' }}>
              {tx('operationsConsole.globalParityAudit.openIncidentBoard', 'Open Incident Board')}
            </Text>
          </TouchableOpacity>
        )}

        {!!incident?.incident_id && incident?.status !== 'acknowledged' && (
          <TouchableOpacity accessibilityLabel="Global parity audit ack incident button"
            onPress={acknowledgeIncident}
            disabled={acking}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              paddingHorizontal: 12,
              paddingVertical: 9,
              borderRadius: 10,
              backgroundColor: colors.card,
              borderWidth: 1,
              borderColor: colors.border,
              opacity: acking ? 0.7 : 1,
            }}
            data-testid="global-parity-audit-ack-incident-button"
            testID="global-parity-audit-ack-incident-button"
          >
            {acking ? <ActivityIndicator size="small" color={colors.text} /> : <Ionicons name="checkmark-done" size={14} color={colors.text} />}
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>
              {tx('operationsConsole.globalParityAudit.ackIncident', 'Acknowledge Incident')}
            </Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}
