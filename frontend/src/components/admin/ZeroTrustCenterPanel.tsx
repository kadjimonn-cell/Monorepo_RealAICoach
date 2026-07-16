import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import api from '../../services/api';
import { SecurityTrendDashboard, DriftAlertConfigPanel } from './SecurityTrendDashboard';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

const _levelColor = (level: string, T: any) => {
  const n = String(level || '').toUpperCase();
  if (n === 'PASS' || n === 'ACTIVE' || n === 'NONE' || n === 'HIGH' && level === 'HIGH') return T.success;
  if (n === 'FAIL' || n === 'INACTIVE' || n === 'CRITICAL') return T.error;
  if (n === 'WARN' || n === 'MEDIUM') return T.warning;
  if (n === 'LOW') return T.successText;
  return T.textSec;
};

const statusColor = (status: string, T: any) => {
  const s = String(status || '').toUpperCase();
  if (s === 'PASS' || s === 'ACTIVE') return T.success;
  if (s === 'FAIL' || s === 'INACTIVE') return T.error;
  if (s === 'WARN') return T.warning;
  return T.textSec;
};

const threatColor = (level: string, T: any) => {
  const s = String(level || '').toUpperCase();
  if (s === 'NONE') return T.success;
  if (s === 'LOW') return T.successText;
  if (s === 'MEDIUM') return T.warning;
  if (s === 'HIGH') return T.orange;
  if (s === 'CRITICAL') return T.error;
  return T.textSec;
};

const confidenceColor = (c: string, T: any) => {
  const s = String(c || '').toUpperCase();
  if (s === 'HIGH') return T.success;
  if (s === 'MEDIUM') return T.warning;
  return T.error;
};

function StatusBadge({ status, T }: { status: string; T: any }) {
  const color = statusColor(status, T);
  return (
    <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: `${color}18`, borderWidth: 1, borderColor: `${color}40` }}>
      <Text style={{ color, fontSize: 10, fontWeight: '800', letterSpacing: 0.5 }}>{String(status || '--').toUpperCase()}</Text>
    </View>
  );
}

function SectionCard({ title, icon, status, children, T, testId }: { title: string; icon: string; status: string; children: React.ReactNode; T: any; testId: string }) {
  const [expanded, setExpanded] = useState(status === 'FAIL' || status === 'INACTIVE');
  const color = statusColor(status, T);
  return (
    <View style={{ backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }} data-testid={testId} testID={testId}>
      <TouchableOpacity
        onPress={() => setExpanded(!expanded)}
        style={{ flexDirection: 'row', alignItems: 'center', padding: 14, gap: 10 }}
        data-testid={`${testId}-header`} testID={`${testId}-header`}
      >
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: `${color}18`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={16} color={color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>{title}</Text>
        </View>
        <StatusBadge status={status} T={T} />
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={T.textMuted} />
      </TouchableOpacity>
      {expanded && (
        <View style={{ borderTopWidth: 1, borderTopColor: T.border, padding: 14, gap: 10, backgroundColor: `${T.bgSoft}80` }} data-testid={`${testId}-body`} testID={`${testId}-body`}>
          {children}
        </View>
      )}
    </View>
  );
}

function MetricRow({ label, value, color, T }: { label: string; value: string | number; color?: string; T: any }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 3 }}>
      <Text style={{ color: T.textSec, fontSize: 11 }}>{label}</Text>
      <Text style={{ color: color || T.text, fontSize: 11, fontWeight: '700' }}>{value}</Text>
    </View>
  );
}

function FindingItem({ finding, T }: { finding: any; T: any }) {
  const sevColor = finding.severity === 'high' ? T.error : finding.severity === 'medium' ? T.warning : T.success;
  return (
    <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, padding: 10, gap: 4 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
        <Text style={{ color: T.text, fontSize: 10, fontWeight: '700', flex: 1 }} numberOfLines={1}>{finding.rule || finding.test || finding.attack || finding.check || finding.control || 'Finding'}</Text>
        <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 999, backgroundColor: `${sevColor}18` }}>
          <Text style={{ color: sevColor, fontSize: 9, fontWeight: '800' }}>{String(finding.severity || finding.status || '').toUpperCase()}</Text>
        </View>
      </View>
      {finding.file && <Text style={{ color: T.primary, fontSize: 10 }} numberOfLines={1}>{finding.file}{finding.line ? `:${finding.line}` : ''}</Text>}
      {finding.snippet && <Text style={{ color: T.textMuted, fontSize: 9 }} numberOfLines={2}>{finding.snippet}</Text>}
      {finding.detail && <Text style={{ color: T.textSec, fontSize: 10 }}>{finding.detail}</Text>}
      {finding.target && <Text style={{ color: T.textMuted, fontSize: 9 }}>Target: {finding.target}</Text>}
    </View>
  );
}

export default function ZeroTrustCenterPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [runningMitigation, setRunningMitigation] = useState(false);
  const [approvingQueueId, setApprovingQueueId] = useState('');
  const [actionNote, setActionNote] = useState('');

  const T = useMemo(() => ({
    card: colors?.card,
    bgSoft: colors?.bgSoft,
    border: colors?.border,
    text: colors?.text,
    textSec: colors?.textSec || colors?.textSecondary,
    textMuted: colors?.textMuted,
    primary: colors?.primary,
    primaryText: colors?.primaryText,
    success: colors?.success,
    warning: colors?.warning,
    error: colors?.error,
    orange: colors?.orange || colors?.warning,
    successText: (colors as any)?.successText || colors?.success,
    warningText: (colors as any)?.warningText || colors?.warning,
  }), [colors]);

  const { data: latestScan, loading: latestLoading, refetch: refetchLatest } = useLiveQuery('/admin/autonomous-engine/zero-trust/active-defense/latest', {
    entity: 'active-defense-latest',
    pollInterval: 60000,
  });

  const { data: mitigationStatusData, refetch: refetchMitigationStatus } = useLiveQuery('/admin/autonomous-engine/zero-trust/auto-mitigation/status', {
    entity: 'zt-mitigation-status',
    pollInterval: 30000,
  });

  const { data: mitigationQueueData, refetch: refetchMitigationQueue } = useLiveQuery('/admin/autonomous-engine/zero-trust/auto-mitigation/queue?status=pending_approval&limit=8', {
    entity: 'zt-mitigation-queue',
    pollInterval: 30000,
  });

  const { data: nightlyConfig, refetch: refetchNightlyConfig } = useLiveQuery('/admin/autonomous-engine/zero-trust/active-defense/nightly/config', {
    entity: 'zt-nightly-config',
    pollInterval: 120000,
  });

  const { data: nightlyHistory, refetch: refetchNightlyHistory } = useLiveQuery('/admin/autonomous-engine/zero-trust/active-defense/nightly/history?limit=5', {
    entity: 'zt-nightly-history',
    pollInterval: 60000,
  });

  const scan = scanResult || latestScan;
  const sections = scan?.sections || {};
  const mitigationPolicy = mitigationStatusData?.policy || {};
  const mitigationLatest = mitigationStatusData?.latest_run || {};
  const mitigationQueue = Array.isArray(mitigationQueueData?.queue) ? mitigationQueueData.queue : [];
  const nightlyRuns = Array.isArray(nightlyHistory?.runs) ? nightlyHistory.runs : [];
  const [runningNightly, setRunningNightly] = useState(false);

  const runFullScan = useCallback(async () => {
    setScanning(true);
    setActionNote('');
    try {
      const res = await api.post('/admin/autonomous-engine/zero-trust/active-defense/scan');
      setScanResult(res.data || null);
      setActionNote(`Scan ${res.data?.scan_id || ''} complete: ${res.data?.zero_trust_status || 'UNKNOWN'}`);
    } catch (e: any) {
      setActionNote(e?.response?.data?.detail || 'Active Defense scan failed.');
    }
    setScanning(false);
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([refetchLatest(), refetchMitigationStatus(), refetchMitigationQueue(), refetchNightlyConfig(), refetchNightlyHistory()]);
    setRefreshing(false);
  }, [refetchLatest, refetchMitigationStatus, refetchMitigationQueue, refetchNightlyConfig, refetchNightlyHistory]);

  const runNightlyScan = useCallback(async () => {
    setRunningNightly(true);
    setActionNote('');
    try {
      const res = await api.post('/admin/autonomous-engine/zero-trust/active-defense/nightly/run');
      const r = res.data || {};
      setActionNote(`Nightly scan ${r.run_id || ''}: ${r.zero_trust_status || r.status || 'UNKNOWN'} — ${r.pass_count || 0}/${r.total_checks || 8} checks, ${(r.auto_blocked_ips || []).length} blocked, email ${(r.email || {}).status || 'n/a'}`);
      await Promise.all([refetchNightlyHistory(), refetchLatest()]);
    } catch (e: any) {
      setActionNote(e?.response?.data?.detail || 'Nightly scan failed.');
    }
    setRunningNightly(false);
  }, [refetchNightlyHistory, refetchLatest]);

  const runMitigation = useCallback(async () => {
    setRunningMitigation(true);
    setActionNote('');
    try {
      const res = await api.post('/admin/autonomous-engine/zero-trust/auto-mitigation/run');
      const run = res.data || {};
      setActionNote(`Mitigation ${run.run_id || 'n/a'}: ${run.status || 'UNKNOWN'} - applied ${run.actions?.applied || 0}, queued ${run.actions?.queued || 0}`);
    } catch (e: any) {
      setActionNote(e?.response?.data?.detail || 'Mitigation cycle failed.');
    }
    await Promise.all([refetchMitigationStatus(), refetchMitigationQueue()]);
    setRunningMitigation(false);
  }, [refetchMitigationQueue, refetchMitigationStatus]);

  const approveQueueAction = useCallback(async (queueId: string) => {
    setApprovingQueueId(queueId);
    try {
      const res = await api.post(`/admin/autonomous-engine/zero-trust/auto-mitigation/queue/${encodeURIComponent(queueId)}/approve`);
      setActionNote(`Approved ${queueId}: ${res.data?.execution_result?.detail || res.data?.execution_result?.status || 'done'}`);
    } catch (e: any) {
      setActionNote(e?.response?.data?.detail || `Failed to approve ${queueId}`);
    }
    await Promise.all([refetchMitigationStatus(), refetchMitigationQueue()]);
    setApprovingQueueId('');
  }, [refetchMitigationQueue, refetchMitigationStatus]);

  if (latestLoading && !scan) {
    return (
      <View style={{ paddingVertical: 64, alignItems: 'center' }} data-testid="zero-trust-center-loading" testID="zero-trust-center-loading">
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: T.textMuted, marginTop: 10, fontSize: 13 }}>{tx('admin.zeroTrustCenterPanel.auto.text.001', 'Loading Active Defense Control Center...')}</Text>
      </View>
    );
  }

  const ztStatus = String(scan?.zero_trust_status || 'NOT_SCANNED').toUpperCase();
  const threatLevel = String(scan?.threat_level || 'UNKNOWN').toUpperCase();
  const confidence = String(scan?.confidence || 'NONE').toUpperCase();
  const passCount = Number(scan?.pass_count || 0);
  const totalChecks = Number(scan?.total_checks || 8);
  const activeAttacks = Number(scan?.active_attack_count || 0);
  const scanTime = scan?.completed_at ? new Date(scan.completed_at).toLocaleString() : 'Never';

  return (
    <ScrollView contentContainerStyle={{ padding: 18, gap: 14 }} data-testid="zero-trust-center-panel" testID="zero-trust-center-panel">
      {/* Global Security Status Hero */}
      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 18, gap: 14 }} data-testid="zero-trust-hero" testID="zero-trust-hero">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: `${statusColor(ztStatus, T)}18`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="shield-checkmark" size={20} color={statusColor(ztStatus, T)} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 19, fontWeight: '800' }} data-testid="zero-trust-center-title" testID="zero-trust-center-title">{tx('admin.zeroTrustCenterPanel.auto.text.002', 'Active Defense Control Center')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="zero-trust-center-subtitle" testID="zero-trust-center-subtitle">{tx('admin.zeroTrustCenterPanel.auto.text.003', 'Zero-trust security posture with automated scanning, attack simulation, and breach detection')}</Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={handleRefresh}
              disabled={refreshing}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: T.border, backgroundColor: T.bgSoft, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: refreshing ? 0.6 : 1 }}
              data-testid="zero-trust-center-refresh-button" testID="zero-trust-center-refresh-button"
            >
              {refreshing ? <ActivityIndicator size="small" color={T.textSec} /> : <Ionicons name="refresh" size={14} color={T.textSec} />}
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.004', 'Refresh')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={runFullScan}
              disabled={scanning}
              style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: scanning ? `${T.error}44` : T.error, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: scanning ? 0.7 : 1 }}
              data-testid="zero-trust-run-scan-button" testID="zero-trust-run-scan-button"
            >
              {scanning ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="scan" size={14} color={T.primaryText} />}
              <Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '800' }}>{scanning ? 'Scanning...' : 'Run Full Scan'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Status Cards Row */}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="zero-trust-status-cards" testID="zero-trust-status-cards">
          <View style={{ flex: 1, minWidth: 140, backgroundColor: T.bgSoft, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border }} data-testid="zero-trust-status-card" testID="zero-trust-status-card">
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.zeroTrustCenterPanel.auto.text.005', 'Zero-Trust Status')}</Text>
            <Text style={{ color: statusColor(ztStatus, T), fontSize: 22, fontWeight: '900', marginTop: 4 }} data-testid="zero-trust-status-value" testID="zero-trust-status-value">{ztStatus}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 140, backgroundColor: T.bgSoft, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border }} data-testid="zero-trust-threat-card" testID="zero-trust-threat-card">
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.zeroTrustCenterPanel.auto.text.006', 'Threat Level')}</Text>
            <Text style={{ color: threatColor(threatLevel, T), fontSize: 22, fontWeight: '900', marginTop: 4 }} data-testid="zero-trust-threat-value" testID="zero-trust-threat-value">{threatLevel}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 140, backgroundColor: T.bgSoft, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border }} data-testid="zero-trust-attacks-card" testID="zero-trust-attacks-card">
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.zeroTrustCenterPanel.auto.text.007', 'Active Attacks')}</Text>
            <Text style={{ color: activeAttacks > 0 ? T.error : T.success, fontSize: 22, fontWeight: '900', marginTop: 4 }} data-testid="zero-trust-attacks-value" testID="zero-trust-attacks-value">{activeAttacks}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 140, backgroundColor: T.bgSoft, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border }} data-testid="zero-trust-confidence-card" testID="zero-trust-confidence-card">
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.zeroTrustCenterPanel.auto.text.008', 'Confidence')}</Text>
            <Text style={{ color: confidenceColor(confidence, T), fontSize: 22, fontWeight: '900', marginTop: 4 }} data-testid="zero-trust-confidence-value" testID="zero-trust-confidence-value">{confidence}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 140, backgroundColor: T.bgSoft, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border }} data-testid="zero-trust-scan-time-card" testID="zero-trust-scan-time-card">
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.zeroTrustCenterPanel.auto.text.009', 'Last Scan')}</Text>
            <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', marginTop: 6 }} data-testid="zero-trust-scan-time-value" testID="zero-trust-scan-time-value">{scanTime}</Text>
          </View>
        </View>

        {/* Pass/Fail summary bar */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700' }}>Checks: {passCount}/{totalChecks}</Text>
          <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: T.border }}>
            <View style={{ width: `${(passCount / totalChecks) * 100}%` as any, height: 6, borderRadius: 3, backgroundColor: passCount === totalChecks ? T.success : passCount >= 6 ? T.warning : T.error }} />
          </View>
        </View>

        {actionNote ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 10, backgroundColor: actionNote.toLowerCase().includes('fail') ? `${T.error}14` : `${T.success}14`, borderWidth: 1, borderColor: actionNote.toLowerCase().includes('fail') ? `${T.error}35` : `${T.success}35` }} data-testid="zero-trust-action-note" testID="zero-trust-action-note">
            <Ionicons name={actionNote.toLowerCase().includes('fail') ? 'alert-circle' : 'checkmark-circle'} size={14} color={actionNote.toLowerCase().includes('fail') ? T.error : T.success} />
            <Text style={{ color: T.text, fontSize: 11, fontWeight: '600', flex: 1 }}>{actionNote}</Text>
          </View>
        ) : null}
      </View>

      {/* Final Output Summary */}
      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 14, gap: 6 }} data-testid="zero-trust-final-output" testID="zero-trust-final-output">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.zeroTrustCenterPanel.auto.text.010', 'Security Verdict')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
          {[
            { key: 'sast', label: 'SAST' },
            { key: 'dast', label: 'DAST' },
            { key: 'waf', label: 'WAF' },
            { key: 'red_team', label: 'Attack Sim' },
            { key: 'breach_mode', label: 'Breach Response' },
            { key: 'core_controls', label: 'Controls' },
            { key: 'monitoring', label: 'Monitoring' },
            { key: 'evidence', label: 'Evidence' },
          ].map(item => {
            const s = sections[item.key]?.status || '--';
            const c = statusColor(s, T);
            return (
              <View key={item.key} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: `${c}14`, borderWidth: 1, borderColor: `${c}35` }} data-testid={`zero-trust-verdict-${item.key}`} testID={`zero-trust-verdict-${item.key}`}>
                <Ionicons name={s === 'PASS' || s === 'ACTIVE' ? 'checkmark-circle' : 'close-circle'} size={12} color={c} />
                <Text style={{ color: c, fontSize: 10, fontWeight: '700' }}>{item.label}: {s}</Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Core Zero-Trust Controls */}
      <SectionCard title="Core Zero-Trust Controls" icon="lock-closed" status={sections.core_controls?.status || '--'} T={T} testId="zero-trust-section-controls">
        {(sections.core_controls?.controls || []).map((ctrl: any, idx: number) => (
          <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: idx < (sections.core_controls?.controls?.length || 0) - 1 ? 1 : 0, borderBottomColor: T.border }}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={{ color: T.text, fontSize: 11, fontWeight: '700' }}>{String(ctrl.control || '').replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{ctrl.detail}</Text>
            </View>
            <StatusBadge status={ctrl.status} T={T} />
          </View>
        ))}
        <MetricRow label="Passing" value={`${sections.core_controls?.passing || 0}/${sections.core_controls?.total || 0}`} color={T.successText} T={T} />
      </SectionCard>

      {/* SAST */}
      <SectionCard title="SAST (Static Analysis)" icon="code-slash" status={sections.sast?.status || '--'} T={T} testId="zero-trust-section-sast">
        <MetricRow label="Files Scanned" value={sections.sast?.scanned_files || 0} T={T} />
        <MetricRow label="Findings" value={sections.sast?.findings_count || 0} color={(sections.sast?.findings_count || 0) > 0 ? T.warning : T.success} T={T} />
        <MetricRow label="Hardcoded Secrets" value={sections.sast?.categories?.hardcoded_secrets || 0} color={(sections.sast?.categories?.hardcoded_secrets || 0) > 0 ? T.error : T.success} T={T} />
        <MetricRow label="Injection Risks" value={sections.sast?.categories?.injection_risks || 0} color={(sections.sast?.categories?.injection_risks || 0) > 0 ? T.warning : T.success} T={T} />
        <MetricRow label="Unsafe Patterns" value={sections.sast?.categories?.unsafe_patterns || 0} color={(sections.sast?.categories?.unsafe_patterns || 0) > 0 ? T.warning : T.success} T={T} />
        {(sections.sast?.findings || []).slice(0, 5).map((f: any, idx: number) => <FindingItem key={idx} finding={f} T={T} />)}
      </SectionCard>

      {/* DAST */}
      <SectionCard title="DAST (Dynamic Testing)" icon="flash" status={sections.dast?.status || '--'} T={T} testId="zero-trust-section-dast">
        <MetricRow label="Total Tests" value={sections.dast?.total_tests || 0} T={T} />
        <MetricRow label="Blocked" value={sections.dast?.blocked || 0} color={T.successText} T={T} />
        <MetricRow label="Passed Through" value={sections.dast?.passed_through || 0} color={(sections.dast?.passed_through || 0) > 0 ? T.error : T.success} T={T} />
        {(sections.dast?.results || []).map((r: any, idx: number) => (
          <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 }}>
            <Text style={{ color: T.textSec, fontSize: 10, flex: 1 }}>{r.test}{r.payload ? `: ${r.payload}` : ''}</Text>
            <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, backgroundColor: r.blocked ? `${T.success}18` : `${T.error}18` }}>
              <Text style={{ color: r.blocked ? T.success : T.error, fontSize: 9, fontWeight: '800' }}>{r.blocked ? 'BLOCKED' : 'PASSED'}</Text>
            </View>
          </View>
        ))}
      </SectionCard>

      {/* WAF */}
      <SectionCard title="WAF (Web Application Firewall)" icon="shield" status={sections.waf?.status || '--'} T={T} testId="zero-trust-section-waf">
        <MetricRow label="Status" value={sections.waf?.status || '--'} color={statusColor(sections.waf?.status, T)} T={T} />
        <MetricRow label="Blocked IPs (Active)" value={sections.waf?.blocked_ips?.total || 0} T={T} />
        <MetricRow label="Auto-Blocked" value={sections.waf?.blocked_ips?.auto || 0} T={T} />
        <MetricRow label="Blocked Requests (24h)" value={sections.waf?.blocked_requests_24h || 0} T={T} />
        <MetricRow label="Rate Limit Events (24h)" value={sections.waf?.rate_limit_events_24h || 0} T={T} />
        {(sections.waf?.attack_types || []).length > 0 && (
          <View style={{ gap: 4, marginTop: 4 }}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.011', 'Attack Types Detected:')}</Text>
            {(sections.waf?.attack_types || []).map((at: any, idx: number) => (
              <View key={idx} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ color: T.textSec, fontSize: 10 }}>{at.type}</Text>
                <Text style={{ color: T.warningText, fontSize: 10, fontWeight: '700' }}>{at.count}</Text>
              </View>
            ))}
          </View>
        )}
      </SectionCard>

      {/* Red Team Simulation */}
      <SectionCard title="Red Team Simulation" icon="bug" status={sections.red_team?.status || '--'} T={T} testId="zero-trust-section-redteam">
        <MetricRow label="Total Attacks Simulated" value={sections.red_team?.total_attacks || 0} T={T} />
        <MetricRow label="All Blocked" value={sections.red_team?.all_blocked ? 'YES' : 'NO'} color={sections.red_team?.all_blocked ? T.success : T.error} T={T} />
        {(sections.red_team?.simulations || []).map((s: any, idx: number) => (
          <View key={idx} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4, borderBottomWidth: idx < (sections.red_team?.simulations?.length || 0) - 1 ? 1 : 0, borderBottomColor: T.border }}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={{ color: T.text, fontSize: 10, fontWeight: '700' }}>{String(s.attack || '').replace(/_/g, ' ').toUpperCase()}</Text>
              <Text style={{ color: T.textMuted, fontSize: 9 }}>Target: {s.target}</Text>
            </View>
            <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, backgroundColor: s.blocked ? `${T.success}18` : `${T.error}18` }}>
              <Text style={{ color: s.blocked ? T.success : T.error, fontSize: 9, fontWeight: '800' }}>{s.blocked ? 'BLOCKED' : 'BREACHED'}</Text>
            </View>
          </View>
        ))}
      </SectionCard>

      {/* Assume Breach Mode */}
      <SectionCard title="Assume Breach Mode" icon="warning" status={sections.breach_mode?.status || '--'} T={T} testId="zero-trust-section-breach">
        <MetricRow label="Detection" value={sections.breach_mode?.detection_active ? 'ACTIVE' : 'INACTIVE'} color={sections.breach_mode?.detection_active ? T.success : T.error} T={T} />
        <MetricRow label="Containment" value={sections.breach_mode?.containment_active ? 'ACTIVE' : 'INACTIVE'} color={sections.breach_mode?.containment_active ? T.success : T.error} T={T} />
        <MetricRow label="Response Automation" value={sections.breach_mode?.response_active ? 'ACTIVE' : 'INACTIVE'} color={sections.breach_mode?.response_active ? T.success : T.warning} T={T} />
        {(sections.breach_mode?.checks || []).map((ch: any, idx: number) => (
          <FindingItem key={idx} finding={ch} T={T} />
        ))}
      </SectionCard>

      {/* Live Security Monitoring */}
      <SectionCard title="Live Security Monitoring" icon="pulse" status={sections.monitoring?.status || '--'} T={T} testId="zero-trust-section-monitoring">
        <MetricRow label="Failed Logins (1h)" value={sections.monitoring?.failed_logins?.last_1h || 0} color={(sections.monitoring?.failed_logins?.last_1h || 0) > 10 ? T.warning : T.success} T={T} />
        <MetricRow label="Failed Logins (24h)" value={sections.monitoring?.failed_logins?.last_24h || 0} T={T} />
        <MetricRow label="Suspicious Activity (1h)" value={sections.monitoring?.suspicious_activity?.last_1h || 0} color={(sections.monitoring?.suspicious_activity?.last_1h || 0) > 0 ? T.warning : T.success} T={T} />
        <MetricRow label="Suspicious Activity (24h)" value={sections.monitoring?.suspicious_activity?.last_24h || 0} T={T} />
        <MetricRow label="API Abuse (24h)" value={sections.monitoring?.api_abuse?.last_24h || 0} color={(sections.monitoring?.api_abuse?.last_24h || 0) > 0 ? T.warning : T.success} T={T} />
        <MetricRow label="Total Events (24h)" value={sections.monitoring?.total_events_24h || 0} T={T} />
        <MetricRow label="Alert Triggers" value={sections.monitoring?.alert_triggers_active ? 'ACTIVE' : 'INACTIVE'} color={sections.monitoring?.alert_triggers_active ? T.success : T.error} T={T} />
      </SectionCard>

      {/* Security Evidence */}
      <SectionCard title="Security Evidence" icon="document-text" status={sections.evidence?.status || '--'} T={T} testId="zero-trust-section-evidence">
        <MetricRow label="Logs Available" value={sections.evidence?.logs_available ? 'YES' : 'NO'} color={sections.evidence?.logs_available ? T.success : T.error} T={T} />
        <MetricRow label="Scan Results" value={sections.evidence?.scan_results_available ? 'YES' : 'NO'} color={T.successText} T={T} />
        <MetricRow label="Attack Simulations Recorded" value={sections.evidence?.attack_simulations_recorded ? 'YES' : 'NO'} color={T.successText} T={T} />
        <MetricRow label="Response Actions Logged" value={sections.evidence?.response_actions_logged ? 'YES' : 'NO'} color={sections.evidence?.response_actions_logged ? T.success : T.warning} T={T} />
        <MetricRow label="Security Events (24h)" value={sections.evidence?.summary?.security_events_24h || 0} T={T} />
        <MetricRow label="Mitigation Runs" value={sections.evidence?.summary?.mitigation_runs || 0} T={T} />
        <MetricRow label="Blocked IPs" value={sections.evidence?.summary?.blocked_ips || 0} T={T} />
        <MetricRow label="Auto-Response Rules" value={sections.evidence?.summary?.auto_response_rules || 0} T={T} />
      </SectionCard>

      {/* Security Posture Trend */}
      <SecurityTrendDashboard />

      {/* Slack / Teams Drift Alert Config */}
      <DriftAlertConfigPanel />

      {/* Nightly Active Defense Scans */}
      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 14, gap: 10 }} data-testid="zero-trust-nightly-card" testID="zero-trust-nightly-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="moon" size={14} color={T.primary} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }} data-testid="zero-trust-nightly-title" testID="zero-trust-nightly-title">{tx('admin.zeroTrustCenterPanel.auto.text.012', 'Nightly Active Defense Scans')}</Text>
          </View>
          <TouchableOpacity
            onPress={runNightlyScan}
            disabled={runningNightly}
            style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, backgroundColor: runningNightly ? `${T.primary}44` : `${T.primary}20`, borderWidth: 1, borderColor: `${T.primary}55`, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: runningNightly ? 0.6 : 1 }}
            data-testid="zero-trust-nightly-run-btn" testID="zero-trust-nightly-run-btn"
          >
            {runningNightly ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="play" size={12} color={T.primary} />}
            <Text style={{ color: T.primary, fontSize: 11, fontWeight: '800' }}>{runningNightly ? 'Scanning...' : 'Run Nightly Now'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 9, paddingVertical: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.013', 'SCHEDULE')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }} data-testid="zero-trust-nightly-schedule" testID="zero-trust-nightly-schedule">{String(nightlyConfig?.scan_hour_utc ?? 3).padStart(2, '0')}:{String(nightlyConfig?.scan_minute_utc ?? 0).padStart(2, '0')} UTC</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 9, paddingVertical: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.014', 'ENABLED')}</Text>
            <Text style={{ color: nightlyConfig?.enabled !== false ? T.success : T.error, fontSize: 11, fontWeight: '800' }} data-testid="zero-trust-nightly-enabled" testID="zero-trust-nightly-enabled">{nightlyConfig?.enabled !== false ? 'YES' : 'NO'}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 9, paddingVertical: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.015', 'AUTO-BLOCK')}</Text>
            <Text style={{ color: nightlyConfig?.auto_block_on_fail !== false ? T.warning : T.textSec, fontSize: 11, fontWeight: '800' }} data-testid="zero-trust-nightly-autoblock" testID="zero-trust-nightly-autoblock">{nightlyConfig?.auto_block_on_fail !== false ? 'ON' : 'OFF'}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 9, paddingVertical: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.016', 'EMAIL REPORT')}</Text>
            <Text style={{ color: nightlyConfig?.send_email_report !== false ? T.success : T.textSec, fontSize: 11, fontWeight: '800' }} data-testid="zero-trust-nightly-email" testID="zero-trust-nightly-email">{nightlyConfig?.send_email_report !== false ? 'ON' : 'OFF'}</Text>
          </View>
        </View>

        <View style={{ gap: 8 }} data-testid="zero-trust-nightly-history" testID="zero-trust-nightly-history">
          <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.017', 'Recent Nightly Runs')}</Text>
          {nightlyRuns.length === 0 ? (
            <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="zero-trust-nightly-empty" testID="zero-trust-nightly-empty">{tx('admin.zeroTrustCenterPanel.auto.text.018', 'No nightly scans recorded yet.')}</Text>
          ) : nightlyRuns.slice(0, 5).map((run: any, idx: number) => {
            const zt = String(run.zero_trust_status || 'UNKNOWN');
            const ztColor = zt === 'PASS' ? T.success : T.error;
            const blocked = (run.auto_blocked_ips || []).length;
            const emailStat = (run.email || {}).status || 'n/a';
            const scanDate = run.completed_at ? new Date(run.completed_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--';
            return (
              <View key={run.run_id || idx} style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10, gap: 4 }} data-testid={`zero-trust-nightly-run-${idx}`} testID={`zero-trust-nightly-run-${idx}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <Text style={{ color: T.text, fontSize: 10, fontWeight: '700' }} numberOfLines={1}>{run.run_id || '--'}</Text>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, backgroundColor: `${ztColor}18` }}>
                    <Text style={{ color: ztColor, fontSize: 9, fontWeight: '800' }}>{zt}</Text>
                  </View>
                </View>
                <Text style={{ color: T.textSec, fontSize: 10 }}>
                  {scanDate} | Threat: {run.threat_level || '--'} | {run.pass_count || 0}/{run.total_checks || 8} checks | Blocked: {blocked} | Email: {emailStat}
                </Text>
              </View>
            );
          })}
        </View>
      </View>

      {/* Auto-Mitigation + Queue */}
      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 14, gap: 10 }} data-testid="zero-trust-auto-mitigation-card" testID="zero-trust-auto-mitigation-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="flash" size={14} color={T.primary} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }} data-testid="zero-trust-auto-mitigation-title" testID="zero-trust-auto-mitigation-title">{tx('admin.zeroTrustCenterPanel.auto.text.019', 'Auto-Fix + Active Mitigation')}</Text>
          </View>
          <TouchableOpacity
            onPress={runMitigation}
            disabled={runningMitigation}
            style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, borderWidth: 1, borderColor: `${T.primary}55`, backgroundColor: `${T.primary}20`, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: runningMitigation ? 0.6 : 1 }}
            data-testid="zero-trust-run-mitigation-button" testID="zero-trust-run-mitigation-button"
          >
            {runningMitigation ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="play" size={12} color={T.primary} />}
            <Text style={{ color: T.primary, fontSize: 11, fontWeight: '800' }}>{runningMitigation ? 'Running...' : 'Run Now'}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 9, paddingVertical: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.020', 'MODE')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }} data-testid="zero-trust-mitigation-trigger-mode" testID="zero-trust-mitigation-trigger-mode">{String(mitigationPolicy?.trigger_mode || 'both').toUpperCase()}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 9, paddingVertical: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.021', 'SAFETY')}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }} data-testid="zero-trust-mitigation-safety-level" testID="zero-trust-mitigation-safety-level">{String(mitigationPolicy?.safety_level || 'auto_low_medium_queue_high').toUpperCase()}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 9, paddingVertical: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.022', 'LATEST RUN')}</Text>
            <Text style={{ color: statusColor(mitigationLatest?.status, T), fontSize: 11, fontWeight: '800' }} data-testid="zero-trust-mitigation-latest-status" testID="zero-trust-mitigation-latest-status">{String(mitigationLatest?.status || 'NOT_RUN').toUpperCase()}</Text>
          </View>
          <View style={{ backgroundColor: T.bgSoft, borderRadius: 8, borderWidth: 1, borderColor: T.border, paddingHorizontal: 9, paddingVertical: 6 }}>
            <Text style={{ color: T.textMuted, fontSize: 9, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.023', 'PENDING')}</Text>
            <Text style={{ color: (mitigationStatusData?.pending_approvals || 0) > 0 ? T.warning : T.success, fontSize: 11, fontWeight: '800' }} data-testid="zero-trust-mitigation-pending-approvals" testID="zero-trust-mitigation-pending-approvals">{Number(mitigationStatusData?.pending_approvals || 0)}</Text>
          </View>
        </View>

        <View style={{ gap: 8 }} data-testid="zero-trust-mitigation-approval-queue" testID="zero-trust-mitigation-approval-queue">
          <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.zeroTrustCenterPanel.auto.text.024', 'High/Critical Queue (approval required)')}</Text>
          {mitigationQueue.slice(0, 5).map((item: any, idx: number) => (
            <View key={item.queue_id || idx} style={{ backgroundColor: T.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: T.border, padding: 10, gap: 6 }} data-testid={`zero-trust-queue-item-${idx}`} testID={`zero-trust-queue-item-${idx}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: T.text, fontSize: 10, fontWeight: '700' }} numberOfLines={1}>{item.action?.action_type || 'action'} - {item.queue_id}</Text>
                <Text style={{ color: item.severity === 'critical' ? T.error : T.warning, fontSize: 10, fontWeight: '800' }}>{String(item.severity || '').toUpperCase()}</Text>
              </View>
              <Text style={{ color: T.textSec, fontSize: 10 }} numberOfLines={2}>{item.action?.reason || 'No reason provided'}</Text>
              <TouchableOpacity
                onPress={() => approveQueueAction(item.queue_id)}
                disabled={approvingQueueId === item.queue_id}
                style={{ alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: `${T.primary}55`, backgroundColor: `${T.primary}1A`, flexDirection: 'row', alignItems: 'center', gap: 6, opacity: approvingQueueId === item.queue_id ? 0.7 : 1 }}
                data-testid={`zero-trust-approve-queue-button-${idx}`} testID={`zero-trust-approve-queue-button-${idx}`}
              >
                {approvingQueueId === item.queue_id ? <ActivityIndicator size="small" color={T.primary} /> : <Ionicons name="checkmark-circle" size={12} color={T.primary} />}
                <Text style={{ color: T.primary, fontSize: 10, fontWeight: '800' }}>{approvingQueueId === item.queue_id ? 'Approving...' : 'Approve & Execute'}</Text>
              </TouchableOpacity>
            </View>
          ))}
          {mitigationQueue.length === 0 && (
            <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid="zero-trust-queue-empty" testID="zero-trust-queue-empty">{tx('admin.zeroTrustCenterPanel.auto.text.025', 'No pending high/critical approvals.')}</Text>
          )}
        </View>
      </View>
    </ScrollView>
  );
}
