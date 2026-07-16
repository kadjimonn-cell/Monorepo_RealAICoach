import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import OnboardingABPanel from './OnboardingABPanel';
import { AutonomousContentMarketingCard } from './AutonomousContentMarketingCard';
import { useLanguage } from '../../i18n/LanguageContext';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTheme } from '../../context/ThemeContext';
function makeT(AC: any) { return {
  bg: AC.bg,
  card: AC.surface,
  border: AC.border,
  text: AC.text,
  muted: AC.textMuted,
  blue: AC.primary,
  primaryText: AC.primaryText,
}; }

const tx = (_key: string, fallback: string) => fallback;

const GATE_ICONS: Record<string, string> = {
  tests: 'flask-outline',
  validation: 'shield-checkmark-outline',
  performance: 'speedometer-outline',
  e2e: 'navigate-outline',
  visual: 'eye-outline',
};

const GATE_LABELS: Record<string, string> = {
  tests: 'autonomousEngine.gates.tests',
  validation: 'autonomousEngine.gates.validation',
  performance: 'autonomousEngine.gates.performance',
  e2e: 'autonomousEngine.gates.e2e',
  visual: 'autonomousEngine.gates.visual',
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

function StatusBadge({ status }: { status: string }) {
  const bg = status === 'PASS' ? 'var(--app-success)' : status === 'FAIL' ? 'var(--app-error)' : status === 'SKIP' ? 'var(--app-text)' : 'var(--app-warning)';
  return (
    <View style={{ paddingHorizontal: 10, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(bg, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(bg, '40') }} data-testid={`status-badge-${status.toLowerCase()}`} testID={`status-badge-${status.toLowerCase()}`}>
      <Text style={{ fontSize: 10, fontWeight: '800', color: bg, letterSpacing: 0.5 }}>{status}</Text>
    </View>
  );
}

function GateCard({ gate, data, focused = false }: { gate: string; data: any; focused?: boolean }) {    const AC = useAdminTheme();
  const { colors } = useTheme();
  const { t } = useLanguage();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const C = T;
  const [expanded, setExpanded] = useState(Boolean(focused));
  const status = data?.status || 'SKIP';
  const details = data?.details || {};
  const issues = data?.issues || [];

  useEffect(() => {
    if (focused) setExpanded(true);
  }, [focused]);

  return (
    <View style={{ backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: focused ? (globalThis as any).__alphaColor('var(--app-primary-soft)', '40') : status === 'FAIL' ? (globalThis as any).__alphaColor(colors.error, '40') : C.border, padding: 14, marginBottom: 8 }} data-testid={`gate-card-${gate}`} testID={`gate-card-${gate}`}>
      <TouchableOpacity onPress={() => setExpanded(!expanded)} accessibilityLabel={t(GATE_LABELS[gate] || gate)} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name={GATE_ICONS[gate] as any || 'help-outline'} size={18} color={status === 'PASS' ? 'var(--app-success)' : status === 'FAIL' ? 'var(--app-error)' : C.muted} />
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{t(GATE_LABELS[gate] || gate)}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <StatusBadge status={status} />
          <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={C.muted} />
        </View>
      </TouchableOpacity>

      {expanded && (
        <View style={{ marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border }}>
          {Object.entries(details).map(([k, v]: [string, any]) => (
            <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 5 }}>
              <Text style={{ fontSize: 11, color: C.muted, flex: 1 }}>{k}</Text>
              <StatusBadge status={v?.status || '?'} />
            </View>
          ))}

          {gate === 'tests' && details?.backend_pytest?.status === 'FAIL' && (
            <View
              style={{ marginTop: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.errorSoft, backgroundColor: colors.errorSoft, padding: 10 }}
              data-testid="tests-gate-root-cause-panel"
              testID="tests-gate-root-cause-panel"
            >
              <Text style={{ color: colors.errorText, fontSize: 11, fontWeight: '800', marginBottom: 6 }}>{tx('admin.autonomousEnginePanel.auto.text.001', 'ROOT-CAUSE TRACE')}</Text>
              <Text style={{ color: colors.errorText, fontSize: 10, lineHeight: 15 }} data-testid="tests-gate-failure-type" testID="tests-gate-failure-type">
                failure_type: {String(details?.backend_pytest?.failure_type || 'unknown_failure')}
              </Text>
              <Text style={{ color: colors.errorText, fontSize: 10, lineHeight: 15 }} data-testid="tests-gate-failing-test" testID="tests-gate-failing-test">
                failing_test: {String(details?.backend_pytest?.failing_test_name || '-')}
              </Text>
              <Text style={{ color: colors.errorText, fontSize: 10, lineHeight: 15 }} data-testid="tests-gate-failing-line" testID="tests-gate-failing-line">
                failing_line: {String(details?.backend_pytest?.failing_file || '-')}:{String(details?.backend_pytest?.failing_line || '-')}
              </Text>
              <Text style={{ color: colors.errorText, fontSize: 10, lineHeight: 15, marginTop: 6, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }} data-testid="tests-gate-stack-trace" testID="tests-gate-stack-trace">
                {String(details?.backend_pytest?.stack_trace || details?.backend_pytest?.output_tail || '').slice(-1600)}
              </Text>
            </View>
          )}

          {issues.length > 0 && (
            <View style={{ marginTop: 8, padding: 10, backgroundColor: (globalThis as any).__alphaColor(colors.error, '10'), borderRadius: 8 }}>
              {issues.map((iss: string, i: number) => (
                <Text key={i} style={{ fontSize: 10, color: colors.error, lineHeight: 16 }}>{iss}</Text>
              ))}
            </View>
          )}
        </View>
      )}
    </View>
  );
}

export default function AutonomousEnginePanel() {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const C = T;
  const [status, setStatus] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [completionAudit, setCompletionAudit] = useState<any[]>([]);
  const [certificateHistory, setCertificateHistory] = useState<any[]>([]);
  const [certificateTotal, setCertificateTotal] = useState(0);
  const [certificateRange, setCertificateRange] = useState<'all' | '24h' | '7d' | 'custom'>('all');
  const [certificateCustomStartAt, setCertificateCustomStartAt] = useState<string>('');
  const [certificateCustomEndAt, setCertificateCustomEndAt] = useState<string>('');
  const [certificateIssuerFilter, setCertificateIssuerFilter] = useState('');
  const [certificateRunIdFilter, setCertificateRunIdFilter] = useState('');
  const [auditSummary, setAuditSummary] = useState<{ total: number; blocked_count: number; allowed_count: number }>({ total: 0, blocked_count: 0, allowed_count: 0 });
  const [auditRange, setAuditRange] = useState<'all' | '24h' | '7d' | 'custom'>('all');
  const [customStartAt, setCustomStartAt] = useState<string>('');
  const [customEndAt, setCustomEndAt] = useState<string>('');
  const [nightlyExportRunning, setNightlyExportRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'command' | 'dashboard' | 'history' | 'audit' | 'certificates' | 'features' | 'failure_memory' | 'memory' | 'experiments' | 'config'>('dashboard');
  const [focusedGate, setFocusedGate] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [featureBuilds, setFeatureBuilds] = useState<any[]>([]);
  const [featureFilter, setFeatureFilter] = useState<'all' | 'in_progress' | 'blocked' | 'completed'>('all');
  const [featureLoading, setFeatureLoading] = useState(false);
  const [showNewFeature, setShowNewFeature] = useState(false);
  const [newFeatureName, setNewFeatureName] = useState('');
  const [newFeatureDesc, setNewFeatureDesc] = useState('');
  const [newFeatureTests, setNewFeatureTests] = useState('');
  const [advancingId, setAdvancingId] = useState<string | null>(null);
  const [driftRunning, setDriftRunning] = useState(false);
  const [feedbackRunning, setFeedbackRunning] = useState(false);
  const [predictiveRunning, setPredictiveRunning] = useState(false);
  const [resolvingFailureKey, setResolvingFailureKey] = useState<string | null>(null);
  const [assigningFailureKey, setAssigningFailureKey] = useState<string | null>(null);
  const [reconcilingFailureMemory, setReconcilingFailureMemory] = useState(false);
  const [controlledScalingStatus, setControlledScalingStatus] = useState<any>(null);
  const [continuousStatus, setContinuousStatus] = useState<any>(null);
  const [failureDashboard, setFailureDashboard] = useState<any>(null);
  const [memoryDashboard, setMemoryDashboard] = useState<any>(null);
  const [contentMarketingStatus, setContentMarketingStatus] = useState<any>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const auditQuery = new URLSearchParams();
      auditQuery.set('limit', '5000');
      if (auditRange === '24h' || auditRange === '7d') {
        auditQuery.set('range', auditRange);
      } else if (auditRange === 'custom' && customStartAt && customEndAt) {
        auditQuery.set('range', 'custom');
        auditQuery.set('start_at', customStartAt);
        auditQuery.set('end_at', customEndAt);
      }

      const certQuery = new URLSearchParams();
      certQuery.set('limit', '200');
      if (certificateRange === '24h' || certificateRange === '7d') {
        certQuery.set('range', certificateRange);
      } else if (certificateRange === 'custom' && certificateCustomStartAt && certificateCustomEndAt) {
        certQuery.set('range', 'custom');
        certQuery.set('start_at', certificateCustomStartAt);
        certQuery.set('end_at', certificateCustomEndAt);
      }
      if (certificateIssuerFilter.trim()) certQuery.set('issuer', certificateIssuerFilter.trim());
      if (certificateRunIdFilter.trim()) certQuery.set('run_id', certificateRunIdFilter.trim());

      const [statusRes, configRes, historyRes, auditRes, certRes, scalingRes, continuousRes, failureRes, memoryRes, contentMarketingRes] = await Promise.all([
        api.get('/admin/autonomous-engine/status'),
        api.get('/admin/autonomous-engine/config'),
        api.get('/admin/autonomous-engine/history?limit=10'),
        api.get(`/admin/autonomous-engine/completion-audit?${auditQuery.toString()}`),
        api.get(`/admin/autonomous-engine/baseline/certificate-history?${certQuery.toString()}`),
        api.get('/admin/autonomous-engine/controlled-scaling/status'),
        api.get('/admin/autonomous-engine/continuous/status'),
        api.get('/admin/autonomous-engine/failure-memory/dashboard?days=30&limit=8'),
        api.get('/admin/autonomous-engine/memory/dashboard').catch(() => ({ data: null })),
        api.get('/admin/autonomous-engine/content-marketing/weekly/status').catch(() => ({ data: null })),
      ]);
      setStatus(statusRes.data);
      setConfig(configRes.data);
      setHistory(historyRes.data?.runs || []);
      setCompletionAudit(auditRes.data?.entries || []);
      setAuditSummary({
        total: Number(auditRes.data?.total || 0),
        blocked_count: Number(auditRes.data?.blocked_count || 0),
        allowed_count: Number(auditRes.data?.allowed_count || 0),
      });
      setCertificateHistory(certRes.data?.items || []);
      setCertificateTotal(Number(certRes.data?.total || 0));
      setControlledScalingStatus(scalingRes.data || null);
      setContinuousStatus(continuousRes.data || null);
      setFailureDashboard(failureRes.data || null);
      setMemoryDashboard(memoryRes.data || null);
      setContentMarketingStatus(contentMarketingRes.data || null);
      if (statusRes.data?.last_run) setLastResult(statusRes.data.last_run);
    } catch (e) {
      console.error('Failed to load engine data', e);
    } finally { setLoading(false); }
  }, [
    auditRange,
    customEndAt,
    customStartAt,
    certificateRange,
    certificateCustomStartAt,
    certificateCustomEndAt,
    certificateIssuerFilter,
    certificateRunIdFilter,
  ]);

  useEffect(() => { loadData(); }, [loadData]);

  const loadFeatures = useCallback(async () => {
    setFeatureLoading(true);
    try {
      const res = await api.get('/admin/autonomous-engine/feature/list?limit=50');
      setFeatureBuilds(res.data?.features || []);
    } catch (e) { console.error('Failed to load features', e); }
    finally { setFeatureLoading(false); }
  }, []);

  useEffect(() => { if (activeTab === 'features') loadFeatures(); }, [activeTab, loadFeatures]);

  const startNewFeature = async () => {
    if (!newFeatureName.trim()) return;
    try {
      const testFiles = newFeatureTests.split(',').map(s => s.trim()).filter(Boolean);
      await api.post('/admin/autonomous-engine/feature/start', { name: newFeatureName, description: newFeatureDesc, test_files: testFiles });
      setNewFeatureName(''); setNewFeatureDesc(''); setNewFeatureTests(''); setShowNewFeature(false);
      setActionMessage({ type: 'success', text: 'Feature build started' });
      loadFeatures();
    } catch (e: any) { setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to start feature' }); }
  };

  const advanceFeature = async (featureId: string) => {
    setAdvancingId(featureId);
    try {
      const res = await api.post(`/admin/autonomous-engine/feature/advance/${featureId}`);
      const r = res.data?.result || '';
      setActionMessage({ type: r === 'BLOCKED' ? 'error' : 'success', text: `${featureId}: ${r} — ${res.data?.step_label || res.data?.step_completed || ''}` });
      loadFeatures();
    } catch (e: any) { setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Advance failed' }); }
    finally { setAdvancingId(null); }
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const focusGate = String(new URLSearchParams(window.location.search).get('focus_gate') || '').trim().toUpperCase();
    const normalized = focusGate.toLowerCase();
    if (['tests', 'validation', 'performance', 'e2e', 'visual'].includes(normalized)) {
      setActiveTab('dashboard');
      setFocusedGate(normalized);
      setActionMessage({ type: 'info', text: `Focused failing gate: ${normalized.toUpperCase()}.` });
    }
  }, []);

  const runPipeline = async () => {
    setRunning(true);
    setActionMessage({ type: 'info', text: 'Running strict autonomous pipeline…' });
    try {
      const res = await api.post('/admin/autonomous-engine/run');
      setLastResult(res.data);
      setActionMessage({ type: 'success', text: 'Pipeline passed. Hard-gate is OPEN.' });
      await loadData();
    } catch (e: any) {
      const detail = e?.response?.data?.detail || {};
      if (e?.response?.status === 409 && detail?.result) {
        setLastResult(detail.result);
        setActionMessage({
          type: 'error',
          text: detail?.message || 'Pipeline failed. Hard-gate remains BLOCKED until STATUS=PASS.',
        });
      } else {
        setActionMessage({
          type: 'error',
          text: e?.response?.data?.detail || e?.message || 'Pipeline execution failed.',
        });
      }
      console.error('Pipeline failed', e);
    } finally { setRunning(false); }
  };

  const runForeverLoopNow = async () => {
    setRunning(true);
    setActionMessage({ type: 'info', text: 'Running FOREVER LOOP now: Monitor → Detect → Fix → Test → Validate → Optimize → Deploy → Learn → Repeat…' });
    try {
      const res = await api.post('/admin/autonomous-engine/continuous/run-now');
      const cycle = res.data?.cycle || {};
      const status = cycle?.status || 'UNKNOWN';
      const anomalyCount = Number(cycle?.anomaly_count || 0);
      setActionMessage({
        type: status === 'FAIL' ? 'error' : 'success',
        text: `Forever loop completed with status ${status}. anomalies=${anomalyCount}.`,
      });
      await loadData();
    } catch (e: any) {
      setActionMessage({
        type: 'error',
        text: e?.response?.data?.detail || e?.message || 'Failed to run Forever Loop.',
      });
    } finally {
      setRunning(false);
    }
  };

  const _runSingleGate = async (gate: string) => {
    setRunning(true);
    try {
      const res = await api.post(`/admin/autonomous-engine/run-gate/${gate}`);
      setLastResult((prev: any) => prev ? { ...prev, gates: { ...prev.gates, [gate]: res.data } } : { gates: { [gate]: res.data } });
    } catch (e) {
      console.error(`Gate ${gate} failed`, e);
    } finally { setRunning(false); }
  };

  const updateConfig = async (updates: any) => {
    try {
      const res = await api.put('/admin/autonomous-engine/config', updates);
      setConfig(res.data);
      setActionMessage({ type: 'success', text: 'Engine configuration updated.' });
    } catch (e) { console.error('Config update failed', e); }
  };

  const checkGateLock = async () => {
    try {
      const res = await api.get('/admin/autonomous-engine/gate-lock');
      const lock = res.data || {};
      const lockLatestStatus = String(lock?.latest_run_status || 'UNKNOWN').toUpperCase();
      const lockLatestRunId = String(lock?.latest_run_id || 'n/a');
      const lockRecentWindow = Number(lock?.require_recent_pass_minutes || status?.require_recent_pass_minutes || 240);
      const lockHasRecentPass = Boolean(lock?.has_recent_pass);
      const lockMinutesSincePass = Number(lock?.minutes_since_last_pass ?? -1);
      setActionMessage({
        type: lock.gate_open ? 'success' : 'error',
        text: lock.gate_open
          ? `Release gate OPEN. Latest run ${lockLatestRunId} is PASS within ${lockRecentWindow}m window.`
          : lockLatestStatus !== 'PASS'
            ? `Release gate BLOCKED. Latest run ${lockLatestRunId} is ${lockLatestStatus}. Run Full Pipeline until PASS.`
            : lockHasRecentPass
              ? 'Release gate BLOCKED by strict policy. Validate gate settings.'
              : `Release gate BLOCKED. Last PASS is ${lockMinutesSincePass >= 0 ? `${lockMinutesSincePass}m` : 'outside'} beyond ${lockRecentWindow}m window.`,
      });
      await loadData();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to fetch gate lock state.' });
    }
  };

  const lockPassBaseline = async () => {
    try {
      const res = await api.post('/admin/autonomous-engine/baseline/lock', { note: 'manual_admin_lock' });
      const baseline = res.data || {};
      setActionMessage({
        type: 'success',
        text: `PASS baseline locked (run: ${baseline.baseline_run_id || 'n/a'}). Regression auto-rollback is now enforced.`,
      });
      await loadData();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to lock PASS baseline.' });
    }
  };

  const runDriftCheck = async () => {
    setDriftRunning(true);
    setActionMessage({ type: 'info', text: 'Running drift detection: compare → optimize → re-validate…' });
    try {
      const res = await api.post('/admin/autonomous-engine/drift/run');
      const result = res.data || {};
      setActionMessage({
        type: result?.detected ? (result?.restored ? 'success' : 'error') : 'success',
        text: result?.detected
          ? (result?.restored ? 'Drift detected, auto-optimized, and restored.' : 'Drift detected. Auto-optimization completed, but re-validation still shows degradation.')
          : 'No drift detected. System remains stable.',
      });
      await loadData();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to run drift detection.' });
    } finally {
      setDriftRunning(false);
    }
  };

  const analyzeFeedbackLoop = async () => {
    setFeedbackRunning(true);
    setActionMessage({ type: 'info', text: 'Analyzing real-user feedback and generating optimization tasks…' });
    try {
      const res = await api.post('/admin/autonomous-engine/feedback/analyze');
      const result = res.data || {};
      const frictionCount = Array.isArray(result?.friction_detected) ? result.friction_detected.length : 0;
      const generatedCount = Array.isArray(result?.generated_tasks) ? result.generated_tasks.length : 0;
      setActionMessage({
        type: frictionCount > 0 ? 'success' : 'info',
        text: frictionCount > 0
          ? `Detected ${frictionCount} friction pattern(s) and generated ${generatedCount} optimization task(s).`
          : 'No major user friction detected in the current analysis window.',
      });
      await Promise.all([loadData(), loadFeatures()]);
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to analyze user feedback.' });
    } finally {
      setFeedbackRunning(false);
    }
  };

  const updatePredictivePolicy = async (updates: any) => {
    try {
      await api.post('/admin/autonomous-engine/predictive/policy', updates);
      setActionMessage({ type: 'success', text: 'Predictive policy updated.' });
      await loadData();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to update predictive policy.' });
    }
  };

  const runPredictivePrevention = async () => {
    setPredictiveRunning(true);
    setActionMessage({ type: 'info', text: 'Predicting likely failures and running preventive actions…' });
    try {
      const res = await api.post('/admin/autonomous-engine/predictive/run');
      const result = res.data || {};
      const highRisk = Number(result?.high_risk_count || 0);
      const actions = Number(result?.preemptive?.actions?.length || 0);
      const validationStatus = String(result?.validation?.status || 'SKIP');
      const isStrong = result?.status === 'PREEMPTED_AND_VALIDATED';
      setActionMessage({
        type: isStrong ? 'success' : highRisk > 0 ? 'info' : 'success',
        text:
          highRisk > 0
            ? `Predicted ${highRisk} high-risk failure pattern(s). Preventive actions: ${actions}. Validation: ${validationStatus}.`
            : 'No high-risk failure pattern detected in the current lookback window.',
      });
      await loadData();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Predictive prevention run failed.' });
    } finally {
      setPredictiveRunning(false);
    }
  };

  const refreshDarkmodeScanStatus = async () => {
    try {
      await loadData();
      setActionMessage({ type: 'success', text: 'Nightly dark-mode scan status refreshed.' });
    } catch {
      setActionMessage({ type: 'error', text: 'Unable to refresh dark-mode scan status.' });
    }
  };

  const resolveFailureEntry = async (entry: any) => {
    if (!entry?.logged_at || !entry?.failure_type || !entry?.component) {
      setActionMessage({ type: 'error', text: 'Unable to resolve this failure entry.' });
      return;
    }
    let fixNote = 'resolved_from_failure_memory_dashboard';
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const noteInput = window.prompt('Enter remediation note (optional)', fixNote);
      if (noteInput === null) return;
      fixNote = noteInput.trim() || fixNote;
    }

    const rowKey = `${entry.logged_at}|${entry.failure_type}|${entry.component}`;
    setResolvingFailureKey(rowKey);
    try {
      const res = await api.post('/admin/autonomous-engine/failure-memory/resolve', {
        logged_at: entry.logged_at,
        failure_type: entry.failure_type,
        component: entry.component,
        fix_applied: fixNote,
      });
      setActionMessage({
        type: 'success',
        text: `Resolved ${entry.failure_type} @ ${entry.component}. Remaining unresolved: ${res?.data?.remaining_unresolved ?? 'updated'}.`,
      });
      await loadData();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to resolve failure entry.' });
    } finally {
      setResolvingFailureKey(null);
    }
  };

  const assignFailureOwner = async (entry: any) => {
    if (!entry?.logged_at || !entry?.failure_type || !entry?.component) {
      setActionMessage({ type: 'error', text: 'Unable to assign owner for this failure entry.' });
      return;
    }

    const rowKey = `${entry.logged_at}|${entry.failure_type}|${entry.component}`;
    setAssigningFailureKey(rowKey);
    try {
      let owner = String(entry?.owner || '').trim() || 'qa-oncall';
      let severity = String(entry?.severity || '').trim().toLowerCase() || 'high';

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const ownerInput = window.prompt('Assign owner (required)', owner);
        if (ownerInput === null) return;
        owner = ownerInput.trim();
        if (!owner) {
          setActionMessage({ type: 'error', text: 'Owner is required for assignment.' });
          return;
        }

        const severityInput = window.prompt('Set severity: critical | high | medium', severity);
        if (severityInput !== null && severityInput.trim()) {
          severity = severityInput.trim().toLowerCase();
        }
      }

      const res = await api.post('/admin/autonomous-engine/failure-memory/assign-owner', {
        logged_at: entry.logged_at,
        failure_type: entry.failure_type,
        component: entry.component,
        owner,
        severity,
      });

      setActionMessage({
        type: 'success',
        text: `Assigned ${res?.data?.failure_type} @ ${res?.data?.component} to ${res?.data?.owner}. SLA: ${res?.data?.sla_status}.`,
      });
      await loadData();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to assign owner.' });
    } finally {
      setAssigningFailureKey(null);
    }
  };

  const reconcileFailureMemory = async () => {
    setReconcilingFailureMemory(true);
    try {
      const res = await api.post('/admin/autonomous-engine/failure-memory/reconcile', {
        quiet_minutes: 60,
        limit: 1000,
        resolution_note: 'auto_reconciled_after_global_pass',
      });
      const resolved = Number(res?.data?.resolved_entries || 0);
      const remaining = Number(res?.data?.remaining_unresolved || 0);
      setActionMessage({
        type: resolved > 0 ? 'success' : 'info',
        text: resolved > 0
          ? `Auto-reconciliation resolved ${resolved} incidents. Remaining unresolved: ${remaining}.`
          : `Auto-reconciliation completed. No eligible incidents to close. Remaining unresolved: ${remaining}.`,
      });
      await loadData();
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Auto-reconciliation failed.' });
    } finally {
      setReconcilingFailureMemory(false);
    }
  };

  const downloadReleaseReadinessCertificate = async () => {
    try {
      const res = await api.get('/admin/autonomous-engine/baseline/release-readiness-certificate/pdf', {
        responseType: 'blob',
      } as any);

      if (Platform.OS === 'web' && typeof window !== 'undefined' && typeof document !== 'undefined') {
        const blob = new Blob([res.data], { type: 'application/pdf' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `release_readiness_certificate_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }

      setActionMessage({ type: 'success', text: 'Release Readiness Certificate download started.' });
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || 'Failed to download Release Readiness Certificate.' });
    }
  };

  const downloadCertificateFromHistory = async (certificateId: string) => {
    try {
      const res = await api.get(`/admin/autonomous-engine/baseline/certificate/download/${encodeURIComponent(certificateId)}`, {
        responseType: 'blob',
      } as any);

      if (Platform.OS === 'web' && typeof window !== 'undefined' && typeof document !== 'undefined') {
        const blob = new Blob([res.data], { type: 'application/pdf' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `release_readiness_certificate_${certificateId}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }

      setActionMessage({ type: 'success', text: `Certificate ${certificateId} download started.` });
    } catch (e: any) {
      setActionMessage({ type: 'error', text: e?.response?.data?.detail || `Failed to download ${certificateId}.` });
    }
  };

  const openCertificateVerification = (certificate: any) => {
    const verifyUrl = certificate?.verification_url;
    if (Platform.OS === 'web' && typeof window !== 'undefined' && verifyUrl) {
      window.open(verifyUrl, '_blank');
      return;
    }
    setActionMessage({ type: 'info', text: verifyUrl ? `Verification URL: ${verifyUrl}` : 'Verification URL is unavailable.' });
  };

  const applyAuditPreset = (preset: 'all' | '24h' | '7d') => {
    setAuditRange(preset);
    if (preset !== 'custom') {
      setActionMessage({ type: 'info', text: `Audit range set to ${preset === 'all' ? 'all time' : preset}.` });
    }
  };

  const applyCustomAuditRange = () => {
    if (typeof window === 'undefined') {
      setActionMessage({ type: 'info', text: 'Custom range picker is available on web only.' });
      return;
    }
    const defaultStart = customStartAt || new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
    const defaultEnd = customEndAt || new Date().toISOString();
    const startInput = window.prompt('Enter custom start datetime (ISO format)', defaultStart);
    if (!startInput) return;
    const endInput = window.prompt('Enter custom end datetime (ISO format)', defaultEnd);
    if (!endInput) return;

    const startMs = Date.parse(startInput);
    const endMs = Date.parse(endInput);
    if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs < startMs) {
      setActionMessage({ type: 'error', text: 'Invalid custom range. Use ISO datetime and ensure end >= start.' });
      return;
    }

    const normalizedStart = new Date(startMs).toISOString();
    const normalizedEnd = new Date(endMs).toISOString();
    setCustomStartAt(normalizedStart);
    setCustomEndAt(normalizedEnd);
    setAuditRange('custom');
    setActionMessage({ type: 'info', text: 'Custom range applied for audit export/filter.' });
  };

  const applyCertificateRangePreset = (preset: 'all' | '24h' | '7d') => {
    setCertificateRange(preset);
    if (preset !== 'custom') {
      setActionMessage({ type: 'info', text: `Certificate range set to ${preset === 'all' ? 'all time' : preset}.` });
    }
  };

  const applyCertificateCustomRange = () => {
    if (typeof window === 'undefined') {
      setActionMessage({ type: 'info', text: 'Custom range picker is available on web only.' });
      return;
    }
    const defaultStart = certificateCustomStartAt || new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
    const defaultEnd = certificateCustomEndAt || new Date().toISOString();
    const startInput = window.prompt('Certificate custom start datetime (ISO)', defaultStart);
    if (!startInput) return;
    const endInput = window.prompt('Certificate custom end datetime (ISO)', defaultEnd);
    if (!endInput) return;

    const startMs = Date.parse(startInput);
    const endMs = Date.parse(endInput);
    if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs < startMs) {
      setActionMessage({ type: 'error', text: 'Invalid certificate custom range. Use ISO datetime and end >= start.' });
      return;
    }

    setCertificateCustomStartAt(new Date(startMs).toISOString());
    setCertificateCustomEndAt(new Date(endMs).toISOString());
    setCertificateRange('custom');
    setActionMessage({ type: 'info', text: 'Custom certificate range applied.' });
  };

  const exportCompletionAuditJson = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      range: auditRange,
      custom_start_at: customStartAt || null,
      custom_end_at: customEndAt || null,
      summary: auditSummary,
      entries: completionAudit,
    };
    const content = JSON.stringify(payload, null, 2);
    const filename = `autonomous_completion_audit_${new Date().toISOString().slice(0, 10)}.json`;
    const ok = triggerFileDownload(filename, content, 'application/json');
    setActionMessage({
      type: ok ? 'success' : 'info',
      text: ok ? 'Completion audit JSON export started.' : 'Audit export is currently available on web only.',
    });
  };

  const exportCompletionAuditCsv = () => {
    const escapeCell = (value: any) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const headers = [
      'range',
      'audit_id',
      'attempted_at',
      'blocked',
      'workflow_type',
      'workflow_id',
      'close_reason',
      'actor_email',
      'source_endpoint',
      'latest_run_status',
      'latest_run_id',
      'has_recent_pass',
      'minutes_since_last_pass',
    ];
    const rows = completionAudit.map((entry: any) => [
      auditRange === 'custom' && customStartAt && customEndAt ? `${customStartAt}..${customEndAt}` : auditRange,
      entry.audit_id,
      entry.attempted_at,
      entry.blocked,
      entry.workflow_type,
      entry.workflow_id,
      entry.close_reason,
      entry?.actor?.email || '',
      entry.source_endpoint,
      entry?.gate_lock?.latest_run_status || '',
      entry?.gate_lock?.latest_run_id || '',
      entry?.gate_lock?.has_recent_pass,
      entry?.gate_lock?.minutes_since_last_pass,
    ]);
    const csv = [
      headers.map(escapeCell).join(','),
      ...rows.map((r: any[]) => r.map(escapeCell).join(',')),
    ].join('\n');
    const filename = `autonomous_completion_audit_${new Date().toISOString().slice(0, 10)}.csv`;
    const ok = triggerFileDownload(filename, csv, 'text/csv;charset=utf-8');
    setActionMessage({
      type: ok ? 'success' : 'info',
      text: ok ? 'Completion audit CSV export started.' : 'Audit export is currently available on web only.',
    });
  };

  const triggerNightlyExportNow = async () => {
    setNightlyExportRunning(true);
    try {
      const res = await api.post('/admin/autonomous-engine/completion-audit/export-nightly-now');
      const summary = res.data?.latest_export || {};
      setActionMessage({
        type: 'success',
        text: `Nightly export sent. Blocked attempts: ${summary.blocked_attempt_count ?? 0}, recipients: ${summary.recipients_count ?? 0}.`,
      });
    } catch (e: any) {
      setActionMessage({
        type: 'error',
        text: e?.response?.data?.detail || 'Nightly export trigger failed.',
      });
    }
    setNightlyExportRunning(false);
  };

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ marginTop: 12, color: C.muted, fontSize: 12 }}>{t('autonomousEngine.loading')}</Text>
      </View>
    );
  }

  const finalOutput = lastResult?.final_output || {};
  const overallStatus = finalOutput.STATUS || 'N/A';
  const gateLock = status?.gate_lock || {};
  const gateIsOpen = Boolean(gateLock?.gate_open);
  const latestRunStatus = String(gateLock?.latest_run_status || overallStatus || 'UNKNOWN').toUpperCase();
  const latestRunId = String(gateLock?.latest_run_id || lastResult?.run_id || 'n/a');
  const latestPassRunId = String(gateLock?.latest_pass_run_id || 'n/a');
  const hasRecentPass = Boolean(gateLock?.has_recent_pass);
  const recentPassWindowMinutes = Number(gateLock?.require_recent_pass_minutes || status?.require_recent_pass_minutes || 240);
  const minutesSinceLastPass = Number(gateLock?.minutes_since_last_pass ?? -1);
  const gateBlockReason = gateIsOpen
    ? `Release gate open. PASS confirmed within ${recentPassWindowMinutes} minutes.`
    : latestRunStatus !== 'PASS'
      ? `Blocked: latest pipeline run ${latestRunId} is ${latestRunStatus}.`
      : !hasRecentPass
        ? `Blocked: latest PASS is outside ${recentPassWindowMinutes}-minute enforcement window.`
        : 'Blocked: strict hard-gate policy requires a fresh PASS snapshot.';
  const gateBlockDetail = gateIsOpen
    ? `Latest run ${latestRunId} is PASS${minutesSinceLastPass >= 0 ? ` • ${minutesSinceLastPass}m since PASS` : ''}.`
    : `Latest run: ${latestRunId} (${latestRunStatus}) • Last PASS run: ${latestPassRunId}${minutesSinceLastPass >= 0 ? ` • ${minutesSinceLastPass}m ago` : ''}`;
  const passProtection = status?.pass_state_protection || {};
  const baselineLocked = Boolean(passProtection?.locked);
  const driftDetection = status?.drift_detection || {};
  const driftLatest = driftDetection?.latest_event || {};
  const driftStatus = driftLatest?.status || (driftDetection?.enabled ? 'ARMED' : 'DISABLED');
  const driftColor = driftStatus === 'RESTORED'
    ? colors.success
    : driftStatus === 'DETECTED'
      ? colors.error
      : driftStatus === 'DISABLED'
        ? C.muted
        : colors.info;
  const feedbackLoop = status?.feedback_loop || {};
  const feedbackLatest = feedbackLoop?.latest_run || {};
  const feedbackStatus = feedbackLatest?.status || (feedbackLoop?.enabled ? 'ARMED' : 'DISABLED');
  const feedbackColor = feedbackStatus === 'FRICTION_DETECTED'
    ? colors.orange
    : feedbackStatus === 'DISABLED'
      ? C.muted
      : colors.success;
  const predictivePrevention = status?.predictive_prevention || {};
  const predictiveLatest = predictivePrevention?.latest_run || {};
  const predictivePolicy = predictivePrevention?.policy || {};
  const predictiveStatus = predictiveLatest?.status || (predictivePrevention?.enabled ? 'ARMED' : 'DISABLED');
  const predictiveColor = predictiveStatus === 'PREEMPTED_AND_VALIDATED'
    ? colors.success
    : predictiveStatus === 'HIGH_RISK_PREDICTED' || predictiveStatus === 'PREEMPTIVE_ACTION_EXECUTED'
      ? colors.orange
      : predictiveStatus === 'DISABLED'
        ? C.muted
        : colors.info;
  const predictiveConfig = config?.predictive_policy || predictivePolicy || {};
  const darkmodeScan = status?.nightly_darkmode_scan || {};
  const darkmodeLatestScan = darkmodeScan?.latest_scan || {};
  const darkmodeFailures = Array.isArray(darkmodeScan?.latest_failures) ? darkmodeScan.latest_failures : [];
  const darkmodeStatus = String(darkmodeScan?.status || 'NOT_RUN').toUpperCase();
  const darkmodeColor = darkmodeStatus === 'PASS'
    ? colors.success
    : darkmodeStatus === 'FAIL'
      ? colors.error
      : colors.warning;
  const darkmodeTicketMap = ((darkmodeLatestScan?.ticketing?.tickets || []) as any[]).reduce((acc: Record<string, string>, item: any) => {
    if (item?.template_key && item?.ticket_id) acc[item.template_key] = item.ticket_id;
    return acc;
  }, {});
  const commandStatuses = [
    { key: 'hard_gate', label: 'Hard Gate', healthy: Boolean(gateIsOpen), detail: gateIsOpen ? 'OPEN' : 'BLOCKED' },
    { key: 'baseline_lock', label: 'Baseline Lock', healthy: Boolean(baselineLocked), detail: baselineLocked ? 'LOCKED' : 'UNLOCKED' },
    { key: 'drift_detection', label: 'Drift Detection', healthy: driftStatus !== 'DETECTED', detail: driftStatus },
    { key: 'feedback_loop', label: 'Feedback Loop', healthy: feedbackStatus !== 'FRICTION_DETECTED', detail: feedbackStatus },
    { key: 'predictive_mode', label: 'Predictive Mode', healthy: predictiveStatus !== 'HIGH_RISK_PREDICTED', detail: predictiveStatus },
    { key: 'darkmode_scan', label: 'Dark-Mode Scan', healthy: darkmodeStatus === 'PASS', detail: darkmodeStatus },
    {
      key: 'controlled_scaling',
      label: 'Controlled Scaling',
      healthy: Boolean(controlledScalingStatus?.active) && Boolean(controlledScalingStatus?.all_subsystems_enforced),
      detail: controlledScalingStatus?.active ? (controlledScalingStatus?.all_subsystems_enforced ? 'ACTIVE + ENFORCED' : 'ACTIVE + DRIFTED') : 'INACTIVE',
    },
    {
      key: 'continuous_mode',
      label: '24/7 Continuous',
      healthy: Boolean(continuousStatus?.enabled),
      detail: continuousStatus?.enabled
        ? `ON (${continuousStatus?.interval_minutes || 30}m) • ${continuousStatus?.forever_loop?.enabled ? 'FOREVER LOOP' : 'LEGACY'}`
        : 'OFF',
    },
    { key: 'pipeline_status', label: 'Pipeline Status', healthy: overallStatus === 'PASS', detail: overallStatus },
    {
      key: 'completion_block_rate',
      label: 'Completion Block Rate',
      healthy: Number(auditSummary.total || 0) === 0 ? true : (Number(auditSummary.blocked_count || 0) / Math.max(Number(auditSummary.total || 1), 1)) < 0.2,
      detail: `${auditSummary.blocked_count}/${auditSummary.total}`,
    },
  ];
  const commandHealthyCount = commandStatuses.filter((item) => item.healthy).length;
  const failureSummary = failureDashboard?.summary || {};
  const failureTrend = Array.isArray(failureDashboard?.trend) ? failureDashboard.trend : [];
  const failureTypes = Array.isArray(failureDashboard?.top_failure_types) ? failureDashboard.top_failure_types : [];
  const failureRootCauses = Array.isArray(failureDashboard?.top_root_causes) ? failureDashboard.top_root_causes : [];
  const failureOwners = Array.isArray(failureDashboard?.top_owners) ? failureDashboard.top_owners : [];
  const unresolvedFailures = Array.isArray(failureDashboard?.unresolved_entries) ? failureDashboard.unresolved_entries : [];

  return (
    <ScrollView style={{ flex: 1, padding: 16 }} contentContainerStyle={{ paddingBottom: 40 }}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }} data-testid="ae-header" testID="ae-header">
        <View>
          <Text style={{ fontSize: 18, fontWeight: '800', color: C.text, letterSpacing: -0.3 }}>{t('autonomousEngine.header.title')}</Text>
          <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{t('autonomousEngine.header.subtitle')}</Text>
        </View>
        <TouchableOpacity
          onPress={runPipeline}
          disabled={running}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 10, paddingHorizontal: 18, borderRadius: 10, backgroundColor: running ? C.border : colors.primary }}
          data-testid="ae-run-pipeline-btn" testID="ae-run-pipeline-btn"
        >
          {running ? <ActivityIndicator size="small" color={T.primaryText} /> : <Ionicons name="play" size={14} color={T.primaryText} />}
          <Text style={{ fontSize: 12, fontWeight: '700', color: T.primaryText }}>{running ? t('autonomousEngine.actions.running') : t('autonomousEngine.actions.runFullPipeline')}</Text>
        </TouchableOpacity>
      </View>

      <View
        style={{
          marginBottom: 14,
          borderRadius: 10,
          borderWidth: 1,
          borderColor: gateIsOpen ? colors.successSoft : colors.errorSoft,
          backgroundColor: gateIsOpen ? colors.successSoft : colors.errorSoft,
          padding: 12,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
        }}
        data-testid="ae-strict-gate-banner"
        testID="ae-strict-gate-banner"
      >
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 11, fontWeight: '800', color: gateIsOpen ? colors.success : colors.error }}>
            STRICT HARD-GATE: {gateIsOpen ? 'OPEN' : 'BLOCKED'}
          </Text>
          <Text style={{ fontSize: 10, color: C.text, marginTop: 4 }} data-testid="ae-gate-lock-reason" testID="ae-gate-lock-reason">
            {gateBlockReason}
          </Text>
          <Text style={{ fontSize: 10, color: C.muted, marginTop: 4 }} data-testid="ae-gate-lock-detail" testID="ae-gate-lock-detail">
            {gateBlockDetail}
          </Text>
        </View>
        <TouchableOpacity
          onPress={checkGateLock}
          style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }}
          data-testid="ae-check-gate-lock-btn"
          testID="ae-check-gate-lock-btn"
        >
          <Text style={{ fontSize: 10, fontWeight: '700', color: C.text }}>{tx('admin.autonomousEnginePanel.auto.text.002', 'Check Lock')}</Text>
        </TouchableOpacity>
      </View>

      <View
        style={{
          marginBottom: 14,
          borderRadius: 10,
          borderWidth: 1,
          borderColor: baselineLocked ? colors.successSoft : colors.warningSoft,
          backgroundColor: baselineLocked ? colors.successSoft : colors.warningSoft,
          padding: 12,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
        data-testid="ae-pass-baseline-banner"
        testID="ae-pass-baseline-banner"
      >
        <View style={{ flex: 1, minWidth: 260 }}>
          <Text style={{ fontSize: 11, fontWeight: '800', color: baselineLocked ? colors.success : colors.warning }}>
            PASS STATE PROTECTION: {baselineLocked ? 'LOCKED' : 'UNLOCKED'}
          </Text>
          <Text style={{ fontSize: 10, color: C.text, marginTop: 4 }} data-testid="ae-pass-baseline-reason" testID="ae-pass-baseline-reason">
            {baselineLocked
              ? `Baseline run ${passProtection?.baseline_run_id || '-'} locked by ${passProtection?.locked_by || 'admin'}. Any regression triggers auto-rollback.`
              : 'Lock current PASS run as immutable baseline for regression-protected operations.'}
          </Text>
        </View>
        <TouchableOpacity accessibilityLabel={tx('admin.autonomousEnginePanel.auto.accessibility.001', 'Lock pass baseline checkpoint')}
          onPress={lockPassBaseline}
          disabled={baselineLocked}
          style={{
            paddingHorizontal: 10,
            paddingVertical: 8,
            borderRadius: 8,
            backgroundColor: baselineLocked ? colors.successSoft : colors.warningSoft,
            borderWidth: 1,
            borderColor: baselineLocked ? colors.successSoft : colors.warningSoft,
            opacity: baselineLocked ? 0.75 : 1,
          }}
          data-testid="ae-lock-pass-baseline-btn"
          testID="ae-lock-pass-baseline-btn"
        >
          <Text style={{ fontSize: 10, fontWeight: '700', color: baselineLocked ? colors.success : 'var(--app-primary)' }}>
            {baselineLocked ? 'Baseline Locked' : 'Lock PASS Baseline'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity accessibilityLabel={tx('admin.autonomousEnginePanel.auto.accessibility.002', 'Download release readiness certificate')}
          onPress={downloadReleaseReadinessCertificate}
          disabled={!baselineLocked}
          style={{
            paddingHorizontal: 10,
            paddingVertical: 8,
            borderRadius: 8,
            backgroundColor: baselineLocked ? colors.primarySoft : colors.primarySoft,
            borderWidth: 1,
            borderColor: baselineLocked ? colors.primarySoft : colors.primarySoft,
            opacity: baselineLocked ? 1 : 0.6,
          }}
          data-testid="ae-download-release-certificate-btn"
          testID="ae-download-release-certificate-btn"
        >
          <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primary }}>{tx('admin.autonomousEnginePanel.auto.text.003', 'Download Certificate')}</Text>
        </TouchableOpacity>
      </View>

      <View
        style={{
          marginBottom: 14,
          borderRadius: 10,
          borderWidth: 1,
          borderColor: `${driftColor}55`,
          backgroundColor: `${driftColor}1A`,
          padding: 12,
          gap: 10,
        }}
        data-testid="ae-drift-detection-banner"
        testID="ae-drift-detection-banner"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 260 }}>
            <Text style={{ fontSize: 11, fontWeight: '800', color: driftColor }} data-testid="ae-drift-status-label" testID="ae-drift-status-label">
              DRIFT DETECTION: {driftStatus}
            </Text>
            <Text style={{ fontSize: 10, color: C.text, marginTop: 4 }} data-testid="ae-drift-status-summary" testID="ae-drift-status-summary">
              Baseline mode: {String(driftDetection?.policy?.baseline_mode || 'dual').toUpperCase()} • Latest check: {driftLatest?.checked_at?.slice(0, 19) || 'Not run yet'}
            </Text>
            <Text style={{ fontSize: 10, color: C.muted, marginTop: 4 }}>
              Perf baseline: {driftDetection?.baseline?.performance_baseline_ms ?? '—'}ms • Test baseline: {driftDetection?.baseline?.tests_passed_baseline ?? '—'} passed
            </Text>
          </View>
          <TouchableOpacity
            onPress={runDriftCheck}
            disabled={driftRunning}
            style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: `${driftColor}22`, borderWidth: 1, borderColor: `${driftColor}55`, opacity: driftRunning ? 0.75 : 1 }}
            data-testid="ae-run-drift-check-btn"
            testID="ae-run-drift-check-btn"
          >
            <Text style={{ fontSize: 10, fontWeight: '700', color: driftColor }}>{driftRunning ? 'Checking…' : 'Run Drift Check'}</Text>
          </TouchableOpacity>
        </View>
        {driftLatest?.detected && (
          <Text style={{ fontSize: 10, color: driftColor }} data-testid="ae-drift-latest-signal" testID="ae-drift-latest-signal">
            Latest drift signal count: {Array.isArray(driftLatest?.signals) ? driftLatest.signals.length : 0}
          </Text>
        )}
      </View>

      <View
        style={{
          marginBottom: 14,
          borderRadius: 10,
          borderWidth: 1,
          borderColor: `${feedbackColor}55`,
          backgroundColor: `${feedbackColor}15`,
          padding: 12,
          gap: 10,
        }}
        data-testid="ae-feedback-loop-banner"
        testID="ae-feedback-loop-banner"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 260 }}>
            <Text style={{ fontSize: 11, fontWeight: '800', color: feedbackColor }} data-testid="ae-feedback-loop-status" testID="ae-feedback-loop-status">
              USER FEEDBACK LOOP: {feedbackStatus}
            </Text>
            <Text style={{ fontSize: 10, color: C.text, marginTop: 4 }}>
              Events: {feedbackLoop?.stats?.total_events ?? 0} • Open optimization tasks: {feedbackLoop?.stats?.open_tasks ?? 0}
            </Text>
            <Text style={{ fontSize: 10, color: C.muted, marginTop: 4 }} data-testid="ae-feedback-loop-summary" testID="ae-feedback-loop-summary">
              Latest analysis: {feedbackLatest?.analyzed_at?.slice(0, 19) || 'Not run yet'} • Friction findings: {Array.isArray(feedbackLatest?.friction_detected) ? feedbackLatest.friction_detected.length : 0}
            </Text>
          </View>
          <TouchableOpacity
            onPress={analyzeFeedbackLoop}
            disabled={feedbackRunning}
            style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: `${feedbackColor}22`, borderWidth: 1, borderColor: `${feedbackColor}55`, opacity: feedbackRunning ? 0.75 : 1 }}
            data-testid="ae-feedback-loop-analyze-btn"
            testID="ae-feedback-loop-analyze-btn"
          >
            <Text style={{ fontSize: 10, fontWeight: '700', color: feedbackColor }}>{feedbackRunning ? 'Analyzing…' : 'Analyze Feedback'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View
        style={{
          marginBottom: 14,
          borderRadius: 10,
          borderWidth: 1,
          borderColor: `${darkmodeColor}55`,
          backgroundColor: `${darkmodeColor}15`,
          padding: 12,
          gap: 10,
        }}
        data-testid="ae-darkmode-scan-banner"
        testID="ae-darkmode-scan-banner"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 260 }}>
            <Text style={{ fontSize: 11, fontWeight: '800', color: darkmodeColor }} data-testid="ae-darkmode-scan-status" testID="ae-darkmode-scan-status">
              NIGHTLY DARK-MODE SCAN: {darkmodeStatus}
            </Text>
            <Text style={{ fontSize: 10, color: C.text, marginTop: 4 }} data-testid="ae-darkmode-scan-summary" testID="ae-darkmode-scan-summary">
              Last scan: {darkmodeLatestScan?.scanned_at?.slice(0, 19) || 'Not run yet'} • Failed templates: {darkmodeLatestScan?.failed_templates ?? 0} • Open tickets: {darkmodeScan?.open_tickets ?? 0}
            </Text>
            {darkmodeFailures.length > 0 ? (
              <View style={{ marginTop: 6, gap: 4 }}>
                {darkmodeFailures.slice(0, 3).map((failure: any, index: number) => (
                  <Text key={`${failure?.key || 'failure'}-${index}`} style={{ fontSize: 10, color: darkmodeColor }} data-testid={`ae-darkmode-failure-${index + 1}`} testID={`ae-darkmode-failure-${index + 1}`}>
                    • {failure?.key || 'unknown'} — {(failure?.issues || []).slice(0, 2).join(', ') || 'issues_detected'}{darkmodeTicketMap[failure?.key] ? ` (ticket: ${darkmodeTicketMap[failure.key]})` : ''}
                  </Text>
                ))}
              </View>
            ) : (
              <Text style={{ fontSize: 10, color: colors.successText, marginTop: 4 }} data-testid="ae-darkmode-no-failures" testID="ae-darkmode-no-failures">{tx('admin.autonomousEnginePanel.auto.text.004', 'No dark-mode regressions in the latest nightly scan.')}</Text>
            )}
          </View>
          <TouchableOpacity
            onPress={refreshDarkmodeScanStatus}
            style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: `${darkmodeColor}22`, borderWidth: 1, borderColor: `${darkmodeColor}55` }}
            data-testid="ae-darkmode-refresh-btn"
            testID="ae-darkmode-refresh-btn"
          >
            <Text style={{ fontSize: 10, fontWeight: '700', color: darkmodeColor }}>{tx('admin.autonomousEnginePanel.auto.text.005', 'Refresh Scan')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View
        style={{
          marginBottom: 14,
          borderRadius: 10,
          borderWidth: 1,
          borderColor: `${predictiveColor}55`,
          backgroundColor: `${predictiveColor}15`,
          padding: 12,
          gap: 10,
        }}
        data-testid="ae-predictive-banner"
        testID="ae-predictive-banner"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 260 }}>
            <Text style={{ fontSize: 11, fontWeight: '800', color: predictiveColor }} data-testid="ae-predictive-status" testID="ae-predictive-status">
              PREDICTIVE FAILURE PREVENTION: {predictiveStatus}
            </Text>
            <Text style={{ fontSize: 10, color: C.text, marginTop: 4 }} data-testid="ae-predictive-summary" testID="ae-predictive-summary">
              Lookback: {predictivePolicy?.analyze_window_hours ?? 72}h • Threshold: {predictivePolicy?.confidence_threshold ?? 75} • Last run: {predictiveLatest?.predicted_at?.slice(0, 19) || 'Not run yet'}
            </Text>
            <Text style={{ fontSize: 10, color: C.muted, marginTop: 4 }} data-testid="ae-predictive-counters" testID="ae-predictive-counters">
              Predictions: {predictiveLatest?.prediction_count ?? 0} • High-risk: {predictiveLatest?.high_risk_count ?? 0} • Preventive actions: {predictiveLatest?.preemptive?.actions?.length ?? 0}
            </Text>
          </View>
          <TouchableOpacity
            onPress={runPredictivePrevention}
            disabled={predictiveRunning}
            style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, backgroundColor: `${predictiveColor}22`, borderWidth: 1, borderColor: `${predictiveColor}55`, opacity: predictiveRunning ? 0.75 : 1 }}
            data-testid="ae-run-predictive-btn"
            testID="ae-run-predictive-btn"
          >
            <Text style={{ fontSize: 10, fontWeight: '700', color: predictiveColor }}>{predictiveRunning ? 'Predicting…' : 'Run Predictive Mode'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {actionMessage && (
        <View
          style={{
            marginBottom: 14,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: actionMessage.type === 'success' ? colors.successSoft : actionMessage.type === 'error' ? colors.errorSoft : colors.primarySoft,
            backgroundColor: actionMessage.type === 'success' ? colors.successSoft : actionMessage.type === 'error' ? colors.errorSoft : colors.primarySoft,
            padding: 10,
          }}
          data-testid="ae-action-message"
          testID="ae-action-message"
        >
          <Text style={{ fontSize: 10, fontWeight: '700', color: actionMessage.type === 'success' ? colors.success : actionMessage.type === 'error' ? colors.error : colors.primary }}>
            {actionMessage.text}
          </Text>
        </View>
      )}

      {/* Status Summary */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }} data-testid="ae-status-summary" testID="ae-status-summary">
        <View style={{ flex: 1, minWidth: 140, backgroundColor: overallStatus === 'PASS' ? (globalThis as any).__alphaColor(colors.success, '15') : overallStatus === 'FAIL' ? colors.error + '15' : C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: overallStatus === 'PASS' ? (globalThis as any).__alphaColor(colors.success, '30') : overallStatus === 'FAIL' ? colors.error + '30' : C.border }}>
          <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginBottom: 6 }}>{tx('admin.autonomousEnginePanel.auto.text.006', 'PIPELINE RESULT')}</Text>
          <Text style={{ fontSize: 22, fontWeight: '900', color: overallStatus === 'PASS' ? colors.success : overallStatus === 'FAIL' ? colors.error : C.text }}>{overallStatus}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 130, backgroundColor: gateIsOpen ? (globalThis as any).__alphaColor(colors.success, '15') : colors.error + '15', borderRadius: 12, padding: 16, borderWidth: 1, borderColor: gateIsOpen ? colors.successSoft : colors.errorSoft }} data-testid="ae-release-gate-summary" testID="ae-release-gate-summary">
          <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginBottom: 6 }}>{tx('admin.autonomousEnginePanel.auto.text.007', 'RELEASE GATE')}</Text>
          <Text style={{ fontSize: 22, fontWeight: '900', color: gateIsOpen ? colors.success : colors.error }}>{gateIsOpen ? 'OPEN' : 'BLOCKED'}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 100, backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginBottom: 6 }}>{tx('admin.autonomousEnginePanel.auto.text.008', 'TOTAL RUNS')}</Text>
          <Text style={{ fontSize: 22, fontWeight: '900', color: C.text }}>{status?.total_runs || 0}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 100, backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginBottom: 6 }}>{tx('admin.autonomousEnginePanel.auto.text.009', 'PASS RATE')}</Text>
          <Text style={{ fontSize: 22, fontWeight: '900', color: colors.successText }}>{status?.pass_rate || 'N/A'}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 100, backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ fontSize: 10, color: C.muted, fontWeight: '600', marginBottom: 6 }}>{tx('admin.autonomousEnginePanel.auto.text.010', 'HEAL CYCLES')}</Text>
          <Text style={{ fontSize: 22, fontWeight: '900', color: colors.warningText }}>{lastResult?.heal_cycles?.length || 0}</Text>
        </View>
      </View>

      <AutonomousContentMarketingCard data={contentMarketingStatus} onRefresh={loadData} />

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 4, marginBottom: 16, backgroundColor: C.bg, borderRadius: 10, padding: 4 }}>
        {([
          'command',
          'dashboard',
          'history',
          'audit',
          'certificates',
          'features',
          'failure_memory',
          'memory',
          'experiments',
          'config',
        ] as const).map(tab => (
          <TouchableOpacity
            key={tab}
            onPress={() => setActiveTab(tab)}
            style={{ flex: 1, paddingVertical: 8, borderRadius: 8, backgroundColor: activeTab === tab ? C.card : 'transparent', alignItems: 'center' }}
            data-testid={`ae-tab-${tab}`} testID={`ae-tab-${tab}`}
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: activeTab === tab ? C.text : C.muted, textTransform: 'capitalize' }}>
              {tab === 'failure_memory' ? 'failure memory' : tab}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {activeTab === 'memory' && (
        <View data-testid="ae-memory-tab" testID="ae-memory-tab">
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="ae-memory-summary-card" testID="ae-memory-summary-card">
            <Text style={{ fontSize: 14, fontWeight: '800', color: C.text, marginBottom: 6 }} data-testid="ae-memory-title" testID="ae-memory-title">{tx('admin.autonomousEnginePanel.auto.text.011', 'System Knowledge Memory')}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginBottom: 12 }} data-testid="ae-memory-subtitle" testID="ae-memory-subtitle">{tx('admin.autonomousEnginePanel.auto.text.012', 'Failures, fixes, optimizations, and test patterns are auto-captured and reused before task solving.')}</Text>
            <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
              {[
                { key: 'total', label: 'Total', value: memoryDashboard?.stats?.total || 0, color: colors.info },
                { key: 'failure', label: 'Failures', value: memoryDashboard?.stats?.by_type?.failure || 0, color: colors.error },
                { key: 'fix', label: 'Fixes', value: memoryDashboard?.stats?.by_type?.fix || 0, color: colors.successText },
                { key: 'optimization', label: 'Optimizations', value: memoryDashboard?.stats?.by_type?.optimization || 0, color: colors.warningText },
                { key: 'test_pattern', label: 'Test Patterns', value: memoryDashboard?.stats?.by_type?.test_pattern || 0, color: colors.purpleText },
              ].map((item) => (
                <View key={item.key} style={{ minWidth: 110, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, backgroundColor: C.card }} data-testid={`ae-memory-stat-${item.key}`} testID={`ae-memory-stat-${item.key}`}>
                  <Text style={{ fontSize: 10, color: C.muted }}>{item.label}</Text>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: item.color }}>{item.value}</Text>
                </View>
              ))}
            </View>
          </View>

          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="ae-memory-top-reused-card" testID="ae-memory-top-reused-card">
            <Text style={{ fontSize: 13, fontWeight: '800', color: C.text, marginBottom: 8 }} data-testid="ae-memory-top-reused-title" testID="ae-memory-top-reused-title">{tx('admin.autonomousEnginePanel.auto.text.013', 'Top Reused Solutions')}</Text>
            {(memoryDashboard?.top_reused || []).slice(0, 6).map((item: any, idx: number) => (
              <View key={item.memory_id || idx} style={{ paddingVertical: 8, borderBottomWidth: idx < 5 ? 1 : 0, borderBottomColor: C.border }} data-testid={`ae-memory-reused-row-${idx}`} testID={`ae-memory-reused-row-${idx}`}>
                <Text style={{ fontSize: 11, color: C.text, fontWeight: '700' }} data-testid={`ae-memory-reused-signature-${idx}`} testID={`ae-memory-reused-signature-${idx}`}>{item.signature}</Text>
                <Text style={{ fontSize: 10, color: C.muted }} data-testid={`ae-memory-reused-solution-${idx}`} testID={`ae-memory-reused-solution-${idx}`}>{item.solution_summary}</Text>
              </View>
            ))}
            {(!memoryDashboard?.top_reused || memoryDashboard.top_reused.length === 0) && (
              <Text style={{ fontSize: 11, color: C.muted }} data-testid="ae-memory-empty" testID="ae-memory-empty">{tx('admin.autonomousEnginePanel.auto.text.014', 'No memory entries yet. Run pipeline/tasks to start learning.')}</Text>
            )}
          </View>
        </View>
      )}

      {/* Executive Command Center Tab */}
      {activeTab === 'command' && (
        <View data-testid="ae-command-center-tab" testID="ae-command-center-tab">
          <View style={{ backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border, padding: 14, marginBottom: 12 }}>
            <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }} data-testid="ae-command-center-title" testID="ae-command-center-title">
              {t('autonomousEngine.commandCenter.title')}
            </Text>
            <Text style={{ fontSize: 10, color: C.muted, marginTop: 4 }} data-testid="ae-command-center-summary" testID="ae-command-center-summary">
              Healthy systems: {commandHealthyCount}/{commandStatuses.length} • Last refresh: {new Date().toISOString().slice(0, 19)}
            </Text>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
              <TouchableOpacity onPress={runPipeline} style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.primarySoft, backgroundColor: colors.primarySoft }} data-testid="ae-command-run-pipeline-btn" testID="ae-command-run-pipeline-btn">
                <Text style={{ fontSize: 10, color: colors.primary, fontWeight: '700' }}>{t('autonomousEngine.actions.runPipeline')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={runDriftCheck} style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '55'), backgroundColor: colors.infoSoft }} data-testid="ae-command-run-drift-btn" testID="ae-command-run-drift-btn">
                <Text style={{ fontSize: 10, color: colors.infoText, fontWeight: '700' }}>{t('autonomousEngine.actions.runDrift')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={analyzeFeedbackLoop} style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.warningSoft, backgroundColor: colors.warningSoft }} data-testid="ae-command-run-feedback-btn" testID="ae-command-run-feedback-btn">
                <Text style={{ fontSize: 10, color: colors.warningText, fontWeight: '700' }}>{t('autonomousEngine.actions.analyzeFeedback')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={runPredictivePrevention} style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.successSoft, backgroundColor: colors.successSoft }} data-testid="ae-command-run-predictive-btn" testID="ae-command-run-predictive-btn">
                <Text style={{ fontSize: 10, color: colors.successText, fontWeight: '700' }}>{t('autonomousEngine.actions.runPredictive')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={runForeverLoopNow} style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.purpleSoft, backgroundColor: colors.purpleSoft }} data-testid="ae-command-run-forever-loop-btn" testID="ae-command-run-forever-loop-btn">
                <Text style={{ fontSize: 10, color: colors.purpleText, fontWeight: '700' }}>{t('autonomousEngine.actions.runForeverLoop')}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={loadData} style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft || colors.cardMuted || colors.bg }} data-testid="ae-command-refresh-btn" testID="ae-command-refresh-btn">
                <Text style={{ fontSize: 10, color: AC.textSec, fontWeight: '700' }}>{t('autonomousEngine.actions.refreshAll')}</Text>
              </TouchableOpacity>
            </View>
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {commandStatuses.map((item) => (
              <View
                key={item.key}
                style={{ flex: 1, minWidth: 220, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: item.healthy ? colors.successSoft : colors.errorSoft, padding: 12 }}
                data-testid={`ae-command-status-${item.key}`}
                testID={`ae-command-status-${item.key}`}
              >
                <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700', marginBottom: 4 }}>{item.label}</Text>
                <Text style={{ fontSize: 13, fontWeight: '800', color: item.healthy ? colors.success : colors.error }}>{item.healthy ? t('autonomousEngine.health.healthy') : t('autonomousEngine.health.attention')}</Text>
                <Text style={{ fontSize: 10, color: C.text, marginTop: 4 }}>{item.detail}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && (
        <View data-testid="ae-dashboard-tab" testID="ae-dashboard-tab">
          {/* Standardized Output */}
          {lastResult?.final_output && (
            <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: C.border }} data-testid="ae-final-output" testID="ae-final-output">
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.autonomousEnginePanel.auto.text.015', 'Pipeline Output')}</Text>
              <View style={{ fontFamily: Platform.OS === 'web' ? 'monospace' : undefined } as any}>
                {['STATUS', 'TESTS', 'VALIDATION', 'PERFORMANCE', 'E2E', 'VISUAL'].map(k => (
                  <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4, borderBottomWidth: 1, borderBottomColor: C.border }}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>{k}</Text>
                    <StatusBadge status={finalOutput[k] || 'N/A'} />
                  </View>
                ))}
              </View>
              {lastResult.run_id && (
                <Text style={{ fontSize: 9, color: C.muted, marginTop: 8 }}>Run: {lastResult.run_id} | {lastResult.completed_at?.slice(0, 19)}</Text>
              )}
            </View>
          )}

          {/* Gate Cards */}
          <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.016', 'Gate Details')}</Text>
          {lastResult?.gates ? (
            Object.entries(lastResult.gates).map(([gate, data]) => (
              <GateCard key={gate} gate={gate} data={data} focused={focusedGate === String(gate).toLowerCase()} />
            ))
          ) : (
            <View style={{ padding: 30, alignItems: 'center', backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="rocket-outline" size={32} color={C.muted} />
              <Text style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.017', 'Run the pipeline to see gate results')}</Text>
            </View>
          )}
        </View>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <View data-testid="ae-history-tab" testID="ae-history-tab">
          {history.length === 0 ? (
            <View style={{ padding: 30, alignItems: 'center', backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.018', 'No pipeline runs yet')}</Text>
            </View>
          ) : history.map((run, i) => (
            <View key={i} style={{ backgroundColor: C.card, borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: run.status === 'PASS' ? (globalThis as any).__alphaColor(colors.success, '30') : colors.error + '30' }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name={run.status === 'PASS' ? 'checkmark-circle' : 'close-circle'} size={16} color={run.status === 'PASS' ? colors.success : colors.error} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{run.run_id}</Text>
                </View>
                <StatusBadge status={run.status || '?'} />
              </View>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                {['TESTS', 'VALIDATION', 'PERFORMANCE', 'E2E', 'VISUAL'].map(k => {
                  const val = run.final_output?.[k] || 'SKIP';
                  return (
                    <Text key={k} style={{ fontSize: 9, color: val === 'PASS' ? colors.success : val === 'FAIL' ? colors.error : C.muted, fontWeight: '700' }}>
                      {k}: {val}
                    </Text>
                  );
                })}
              </View>
              <Text style={{ fontSize: 9, color: C.muted, marginTop: 4 }}>
                {run.triggered_by} | {run.completed_at?.slice(0, 19)} | Heals: {run.heal_cycles?.length || 0}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Completion Audit Tab */}
      {activeTab === 'audit' && (
        <View data-testid="ae-audit-tab" testID="ae-audit-tab">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
            <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
              {([
                { key: 'all', label: 'All' },
                { key: '24h', label: 'Last 24h' },
                { key: '7d', label: 'Last 7d' },
              ] as const).map(item => (
                <TouchableOpacity accessibilityLabel={tx('admin.autonomousEnginePanel.auto.accessibility.003', 'Apply audit date preset')}
                  key={item.key}
                  onPress={() => applyAuditPreset(item.key)}
                  style={{
                    paddingHorizontal: 10,
                    paddingVertical: 7,
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: auditRange === item.key ? colors.primarySoft : C.border,
                    backgroundColor: auditRange === item.key ? colors.primarySoft : C.card,
                  }}
                  data-testid={`ae-audit-range-${item.key}-btn`}
                  testID={`ae-audit-range-${item.key}-btn`}
                >
                  <Text style={{ fontSize: 10, color: auditRange === item.key ? colors.primary : C.text, fontWeight: '700' }}>{item.label}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity accessibilityLabel={tx('admin.autonomousEnginePanel.auto.accessibility.004', 'Apply custom audit date range')}
                onPress={applyCustomAuditRange}
                style={{
                  paddingHorizontal: 10,
                  paddingVertical: 7,
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: auditRange === 'custom' ? colors.primarySoft : C.border,
                  backgroundColor: auditRange === 'custom' ? colors.primarySoft : C.card,
                }}
                data-testid="ae-audit-range-custom-btn"
                testID="ae-audit-range-custom-btn"
              >
                <Text style={{ fontSize: 10, color: auditRange === 'custom' ? colors.primary : C.text, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.019', 'Custom')}</Text>
              </TouchableOpacity>
            </View>
            <Text style={{ fontSize: 10, color: C.muted }} data-testid="ae-audit-range-active" testID="ae-audit-range-active">
              Range: {auditRange === 'custom' && customStartAt && customEndAt ? `${customStartAt.slice(0, 16)} → ${customEndAt.slice(0, 16)}` : auditRange}
            </Text>
          </View>

          <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={triggerNightlyExportNow}
              disabled={nightlyExportRunning}
              style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.successSoft, backgroundColor: nightlyExportRunning ? colors.successSoft : colors.successSoft }}
              data-testid="ae-audit-nightly-export-now-btn"
              testID="ae-audit-nightly-export-now-btn"
            >
              <Text style={{ fontSize: 10, color: colors.successText, fontWeight: '700' }}>{nightlyExportRunning ? 'Sending...' : 'Run Nightly Export Now'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={exportCompletionAuditCsv}
              style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.card }}
              data-testid="ae-audit-export-csv-btn"
              testID="ae-audit-export-csv-btn"
            >
              <Text style={{ fontSize: 10, color: C.text, fontWeight: '700' }}>{t("paymentsTax.header.exportCsv")}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={exportCompletionAuditJson}
              style={{ paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.card }}
              data-testid="ae-audit-export-json-btn"
              testID="ae-audit-export-json-btn"
            >
              <Text style={{ fontSize: 10, color: C.text, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.020', 'Export JSON')}</Text>
            </TouchableOpacity>
          </View>

          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-audit-total" testID="ae-audit-total">
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.021', 'TOTAL ATTEMPTS')}</Text>
              <Text style={{ fontSize: 18, color: C.text, fontWeight: '900', marginTop: 4 }} data-testid="ae-audit-total-value" testID="ae-audit-total-value">{auditSummary.total}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: colors.errorSoft, padding: 12 }} data-testid="ae-audit-blocked" testID="ae-audit-blocked">
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.022', 'BLOCKED')}</Text>
              <Text style={{ fontSize: 18, color: colors.error, fontWeight: '900', marginTop: 4 }} data-testid="ae-audit-blocked-value" testID="ae-audit-blocked-value">{auditSummary.blocked_count}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 120, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: colors.successSoft, padding: 12 }} data-testid="ae-audit-allowed" testID="ae-audit-allowed">
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.023', 'ALLOWED')}</Text>
              <Text style={{ fontSize: 18, color: colors.successText, fontWeight: '900', marginTop: 4 }} data-testid="ae-audit-allowed-value" testID="ae-audit-allowed-value">{auditSummary.allowed_count}</Text>
            </View>
          </View>

          {completionAudit.length === 0 ? (
            <View style={{ padding: 24, alignItems: 'center', backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border }} data-testid="ae-audit-empty" testID="ae-audit-empty">
              <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.024', 'No completion attempts logged yet.')}</Text>
            </View>
          ) : (
            completionAudit.map((entry: any, index: number) => (
              <View
                key={entry.audit_id || `audit-${index}`}
                style={{
                  backgroundColor: C.card,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: entry.blocked ? colors.errorSoft : colors.successSoft,
                  padding: 12,
                  marginBottom: 8,
                }}
                data-testid={`ae-audit-entry-${index}`}
                testID={`ae-audit-entry-${index}`}
              >
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: 8 }}>
                  <Text style={{ fontSize: 11, color: C.text, fontWeight: '800' }} data-testid={`ae-audit-entry-${index}-workflow`} testID={`ae-audit-entry-${index}-workflow`}>
                    {entry.workflow_type || 'generic_completion'} {entry.workflow_id ? `• ${entry.workflow_id}` : ''}
                  </Text>
                  <StatusBadge status={entry.blocked ? 'FAIL' : 'PASS'} />
                </View>
                <Text style={{ fontSize: 10, color: C.muted }} data-testid={`ae-audit-entry-${index}-actor`} testID={`ae-audit-entry-${index}-actor`}>
                  Actor: {entry?.actor?.email || entry?.actor?.user_id || 'unknown'}
                </Text>
                <Text style={{ fontSize: 10, color: C.muted, marginTop: 3 }} data-testid={`ae-audit-entry-${index}-reason`} testID={`ae-audit-entry-${index}-reason`}>
                  Reason: {entry.close_reason || 'unspecified'}
                </Text>
                <Text style={{ fontSize: 10, color: C.muted, marginTop: 3 }} data-testid={`ae-audit-entry-${index}-timestamp`} testID={`ae-audit-entry-${index}-timestamp`}>
                  Attempted: {(entry.attempted_at || '').slice(0, 19)}
                </Text>
                <Text style={{ fontSize: 10, color: C.muted, marginTop: 3 }} data-testid={`ae-audit-entry-${index}-endpoint`} testID={`ae-audit-entry-${index}-endpoint`}>
                  Endpoint: {entry.source_endpoint || '-'}
                </Text>
              </View>
            ))
          )}
        </View>
      )}

      {/* Certificate History Tab */}
      {activeTab === 'certificates' && (
        <View data-testid="ae-certificates-tab" testID="ae-certificates-tab">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.autonomousEnginePanel.auto.text.025', 'Certificate History')}</Text>
            <Text style={{ fontSize: 10, color: C.muted }} data-testid="ae-certificate-total" testID="ae-certificate-total">
              Total issued: {certificateTotal}
            </Text>
          </View>

          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
            {([
              { key: 'all', label: 'All' },
              { key: '24h', label: 'Last 24h' },
              { key: '7d', label: 'Last 7d' },
            ] as const).map(item => (
              <TouchableOpacity accessibilityLabel={tx('admin.autonomousEnginePanel.auto.accessibility.005', 'Apply certificate date preset')}
                key={item.key}
                onPress={() => applyCertificateRangePreset(item.key)}
                style={{
                  paddingHorizontal: 10,
                  paddingVertical: 7,
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: certificateRange === item.key ? colors.primarySoft : C.border,
                  backgroundColor: certificateRange === item.key ? colors.primarySoft : C.card,
                }}
                data-testid={`ae-certificate-range-${item.key}-btn`}
                testID={`ae-certificate-range-${item.key}-btn`}
              >
                <Text style={{ fontSize: 10, color: certificateRange === item.key ? colors.primary : C.text, fontWeight: '700' }}>{item.label}</Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity accessibilityLabel={tx('admin.autonomousEnginePanel.auto.accessibility.006', 'Apply custom certificate date range')}
              onPress={applyCertificateCustomRange}
              style={{
                paddingHorizontal: 10,
                paddingVertical: 7,
                borderRadius: 8,
                borderWidth: 1,
                borderColor: certificateRange === 'custom' ? colors.primarySoft : C.border,
                backgroundColor: certificateRange === 'custom' ? colors.primarySoft : C.card,
              }}
              data-testid="ae-certificate-range-custom-btn"
              testID="ae-certificate-range-custom-btn"
            >
              <Text style={{ fontSize: 10, color: certificateRange === 'custom' ? colors.primary : C.text, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.026', 'Custom')}</Text>
            </TouchableOpacity>
          </View>

          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
            <View style={{ flex: 1, minWidth: 220 }}>
              <TextInput
                value={certificateIssuerFilter}
                onChangeText={setCertificateIssuerFilter}
                placeholder={tx('admin.autonomousEnginePanel.auto.placeholder.001', 'Filter by issuer')}
                placeholderTextColor={C.muted}
                style={{
                  height: 36,
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.card,
                  color: C.text,
                  paddingHorizontal: 10,
                  fontSize: 11,
                }}
                data-testid="ae-certificate-filter-issuer-input"
                testID="ae-certificate-filter-issuer-input"
              />
            </View>
            <View style={{ flex: 1, minWidth: 220 }}>
              <TextInput
                value={certificateRunIdFilter}
                onChangeText={setCertificateRunIdFilter}
                placeholder={tx('admin.autonomousEnginePanel.auto.placeholder.002', 'Filter by run ID')}
                placeholderTextColor={C.muted}
                style={{
                  height: 36,
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.card,
                  color: C.text,
                  paddingHorizontal: 10,
                  fontSize: 11,
                }}
                data-testid="ae-certificate-filter-runid-input"
                testID="ae-certificate-filter-runid-input"
              />
            </View>
          </View>

          <Text style={{ fontSize: 10, color: C.muted, marginBottom: 10 }} data-testid="ae-certificate-filter-active" testID="ae-certificate-filter-active">
            Active filters: range={certificateRange}
            {certificateRange === 'custom' && certificateCustomStartAt && certificateCustomEndAt ? ` (${certificateCustomStartAt.slice(0, 16)} → ${certificateCustomEndAt.slice(0, 16)})` : ''}
            {certificateIssuerFilter.trim() ? ` • issuer=${certificateIssuerFilter.trim()}` : ''}
            {certificateRunIdFilter.trim() ? ` • run_id=${certificateRunIdFilter.trim()}` : ''}
          </Text>

          {certificateHistory.length === 0 ? (
            <View style={{ padding: 24, alignItems: 'center', backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border }} data-testid="ae-certificate-empty" testID="ae-certificate-empty">
              <Text style={{ fontSize: 12, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.027', 'No certificates issued yet. Generate one from dashboard.')}</Text>
            </View>
          ) : (
            certificateHistory.map((cert: any, index: number) => (
              <View
                key={cert.certificate_id || `cert-${index}`}
                style={{ backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 8 }}
                data-testid={`ae-certificate-entry-${index}`}
                testID={`ae-certificate-entry-${index}`}
              >
                <Text style={{ fontSize: 11, fontWeight: '800', color: C.text }} data-testid={`ae-certificate-entry-${index}-id`} testID={`ae-certificate-entry-${index}-id`}>
                  {cert.certificate_id}
                </Text>
                <Text style={{ fontSize: 10, color: C.muted, marginTop: 3 }} data-testid={`ae-certificate-entry-${index}-issued`} testID={`ae-certificate-entry-${index}-issued`}>
                  Issued: {(cert.issued_at || '').slice(0, 19)} • By: {cert.issued_by || 'admin'}
                </Text>
                <Text style={{ fontSize: 10, color: C.muted, marginTop: 3 }} data-testid={`ae-certificate-entry-${index}-run`} testID={`ae-certificate-entry-${index}-run`}>
                  Baseline: {cert.baseline_run_id || '-'} • Latest: {cert.latest_run_id || '-'}
                </Text>
                <Text style={{ fontSize: 10, color: C.muted, marginTop: 3 }} data-testid={`ae-certificate-entry-${index}-hash`} testID={`ae-certificate-entry-${index}-hash`}>
                  Hash: {String(cert.certificate_hash || '').slice(0, 20)}...
                </Text>

                <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                  <TouchableOpacity
                    onPress={() => downloadCertificateFromHistory(cert.certificate_id)}
                    style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg }}
                    data-testid={`ae-certificate-entry-${index}-download-btn`}
                    testID={`ae-certificate-entry-${index}-download-btn`}
                  >
                    <Text style={{ fontSize: 10, color: C.text, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.028', 'Download PDF')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => openCertificateVerification(cert)}
                    style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: colors.primarySoft, backgroundColor: colors.primarySoft }}
                    data-testid={`ae-certificate-entry-${index}-verify-btn`}
                    testID={`ae-certificate-entry-${index}-verify-btn`}
                  >
                    <Text style={{ fontSize: 10, color: colors.primary, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.029', 'Verify')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))
          )}
        </View>
      )}

      {/* Features Tab */}
      {activeTab === 'features' && (
        <View data-testid="ae-features-tab" testID="ae-features-tab">
          {/* Header + New Feature Button */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }}>{tx('admin.autonomousEnginePanel.auto.text.030', 'Feature Builds')}</Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity onPress={loadFeatures} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: C.card, borderWidth: 1, borderColor: C.border }} data-testid="features-refresh-btn" testID="features-refresh-btn">
                {featureLoading ? <ActivityIndicator size="small" color={C.blue} /> : <Ionicons name="refresh" size={14} color={C.blue} />}
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setShowNewFeature(!showNewFeature)} style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6, backgroundColor: colors.primary }} data-testid="new-feature-btn" testID="new-feature-btn">
                <Text style={{ fontSize: 11, fontWeight: '700', color: T.primaryText }}>{showNewFeature ? 'Cancel' : '+ New Feature'}</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* New Feature Form */}
          {showNewFeature && (
            <View style={{ backgroundColor: C.card, borderRadius: 10, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: colors.primarySoft }} data-testid="new-feature-form" testID="new-feature-form">
              <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.031', 'Start New Feature Build')}</Text>
              <TextInput placeholder={tx('admin.autonomousEnginePanel.auto.placeholder.003', 'Feature name')} placeholderTextColor={C.muted} value={newFeatureName} onChangeText={setNewFeatureName} style={{ backgroundColor: C.bg, borderWidth: 1, borderColor: C.border, borderRadius: 6, padding: 8, color: C.text, fontSize: 12, marginBottom: 6 }} data-testid="new-feature-name-input" testID="new-feature-name-input" />
              <TextInput placeholder={tx('admin.autonomousEnginePanel.auto.placeholder.004', 'Description (optional)')} placeholderTextColor={C.muted} value={newFeatureDesc} onChangeText={setNewFeatureDesc} style={{ backgroundColor: C.bg, borderWidth: 1, borderColor: C.border, borderRadius: 6, padding: 8, color: C.text, fontSize: 12, marginBottom: 6 }} data-testid="new-feature-desc-input" testID="new-feature-desc-input" />
              <TextInput placeholder={tx('admin.autonomousEnginePanel.auto.placeholder.005', 'Test files (comma-separated, optional)')} placeholderTextColor={C.muted} value={newFeatureTests} onChangeText={setNewFeatureTests} style={{ backgroundColor: C.bg, borderWidth: 1, borderColor: C.border, borderRadius: 6, padding: 8, color: C.text, fontSize: 12, marginBottom: 10 }} data-testid="new-feature-tests-input" testID="new-feature-tests-input" />
              <TouchableOpacity onPress={startNewFeature} style={{ backgroundColor: colors.primary, paddingVertical: 8, borderRadius: 6, alignItems: 'center' }} data-testid="start-feature-btn" testID="start-feature-btn">
                <Text style={{ fontSize: 12, fontWeight: '700', color: T.primaryText }}>{tx('admin.autonomousEnginePanel.auto.text.032', 'Start Feature Build')}</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Filter Tabs */}
          <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12 }}>
            {(['all', 'in_progress', 'blocked', 'completed'] as const).map(f => (
              <TouchableOpacity key={f} onPress={() => setFeatureFilter(f)} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, backgroundColor: featureFilter === f ? (globalThis as any).__alphaColor(C.blue, '30') : C.card, borderWidth: 1, borderColor: featureFilter === f ? C.blue : C.border }} data-testid={`feature-filter-${f}`} testID={`feature-filter-${f}`}>
                <Text style={{ fontSize: 10, fontWeight: '700', color: featureFilter === f ? C.blue : C.muted, textTransform: 'capitalize' }}>{f.replace('_', ' ')}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Feature Cards */}
          {featureBuilds.filter(fb => featureFilter === 'all' || fb.status === featureFilter).map((fb: any) => {
            const STEPS = ['tests_first', 'implement', 'full_pipeline', 'performance_impact', 'regression', 'deploy'];
            const STEP_LABELS: Record<string, string> = { tests_first: 'Tests', implement: 'Impl', full_pipeline: 'Pipeline', performance_impact: 'Perf', regression: 'Regress', deploy: 'Deploy' };
            const statusColor = fb.status === 'completed' ? colors.success : fb.status === 'blocked' ? colors.error : colors.warning;
            const stepStatuses = fb.steps || {};

            return (
              <View key={fb.feature_id} style={{ backgroundColor: C.card, borderRadius: 10, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(statusColor, '40') }} data-testid={`feature-card-${fb.feature_id}`} testID={`feature-card-${fb.feature_id}`}>
                {/* Header */}
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, fontWeight: '800', color: C.text }} numberOfLines={1}>{fb.name}</Text>
                    {fb.description ? <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }} numberOfLines={1}>{fb.description}</Text> : null}
                    <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{fb.feature_id}</Text>
                  </View>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(statusColor, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(statusColor, '40') }}>
                    <Text style={{ fontSize: 9, fontWeight: '800', color: statusColor, textTransform: 'uppercase' }}>{fb.final_verdict || fb.status}</Text>
                  </View>
                </View>

                {/* Step Progression Bar */}
                <View style={{ flexDirection: 'row', gap: 3, marginBottom: 8 }}>
                  {STEPS.map(s => {
                    const sd = stepStatuses[s] || {};
                    const sColor = sd.status === 'PASS' ? colors.success : sd.status === 'FAIL' ? colors.error : fb.current_step === s ? colors.warning : AC.borderStrong;
                    return (
                      <View key={s} style={{ flex: 1, alignItems: 'center' }}>
                        <View style={{ width: '100%', height: 4, borderRadius: 2, backgroundColor: sColor + (sd.status ? '' : '40') }} />
                        <Text style={{ fontSize: 7, color: sColor, marginTop: 3, fontWeight: '700' }}>{STEP_LABELS[s]}</Text>
                      </View>
                    );
                  })}
                </View>

                {/* Blocked Reason */}
                {fb.blocked_reason && (
                  <Text style={{ fontSize: 10, color: colors.error, marginBottom: 6 }} numberOfLines={2}>{fb.blocked_reason}</Text>
                )}

                {/* Action */}
                {fb.status === 'in_progress' && (
                  <TouchableOpacity onPress={() => advanceFeature(fb.feature_id)} disabled={advancingId === fb.feature_id} style={{ backgroundColor: advancingId === fb.feature_id ? C.border : colors.primary, paddingVertical: 6, borderRadius: 6, alignItems: 'center', marginTop: 4 }} data-testid={`advance-feature-${fb.feature_id}`} testID={`advance-feature-${fb.feature_id}`}>
                    {advancingId === fb.feature_id ? <ActivityIndicator size="small" color={T.primaryText} /> : <Text style={{ fontSize: 11, fontWeight: '700', color: T.primaryText }}>Advance: {STEP_LABELS[fb.current_step] || fb.current_step}</Text>}
                  </TouchableOpacity>
                )}

                {/* Timestamps */}
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
                  <Text style={{ fontSize: 9, color: C.muted }}>Started: {fb.started_at ? new Date(fb.started_at).toLocaleDateString() : '—'}</Text>
                  {fb.completed_at && <Text style={{ fontSize: 9, color: C.muted }}>Completed: {new Date(fb.completed_at).toLocaleDateString()}</Text>}
                </View>
              </View>
            );
          })}

          {featureBuilds.filter(fb => featureFilter === 'all' || fb.status === featureFilter).length === 0 && (
            <View style={{ backgroundColor: C.card, borderRadius: 10, padding: 20, alignItems: 'center', borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 12, color: C.muted }}>No feature builds{featureFilter !== 'all' ? ` with status "${featureFilter}"` : ''}. Start one above.</Text>
            </View>
          )}
        </View>
      )}

      {/* Failure Memory Dashboard Tab */}
      {activeTab === 'failure_memory' && (
        <View data-testid="ae-failure-memory-tab" testID="ae-failure-memory-tab">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
            <View style={{ flex: 1, minWidth: 160, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-failure-summary-total" testID="ae-failure-summary-total">
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.033', 'TOTAL FAILURES (30D)')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: C.text, marginTop: 4 }}>{Number(failureSummary?.total_entries || 0)}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 160, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-failure-summary-fix-rate" testID="ae-failure-summary-fix-rate">
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.034', 'FIX SUCCESS RATE')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: colors.successText, marginTop: 4 }}>{Number(failureSummary?.fix_success_rate_pct || 0)}%</Text>
            </View>
            <View style={{ flex: 1, minWidth: 160, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-failure-summary-unresolved" testID="ae-failure-summary-unresolved">
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.035', 'UNRESOLVED')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: colors.error, marginTop: 4 }}>{Number(failureSummary?.unresolved_count || 0)}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 160, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-failure-summary-sla-breached" testID="ae-failure-summary-sla-breached">
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.036', 'SLA BREACHED')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: colors.warningText, marginTop: 4 }}>{Number(failureSummary?.sla_breached_count || 0)}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 160, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-failure-summary-assigned" testID="ae-failure-summary-assigned">
              <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700' }}>{tx('admin.autonomousEnginePanel.auto.text.037', 'ASSIGNED OWNERS')}</Text>
              <Text style={{ fontSize: 22, fontWeight: '900', color: colors.info, marginTop: 4 }}>{Number(failureSummary?.assigned_count || 0)}</Text>
            </View>
          </View>

          <View style={{ backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12, marginBottom: 12 }} data-testid="ae-failure-trend-card" testID="ae-failure-trend-card">
            <Text style={{ fontSize: 12, color: C.text, fontWeight: '800', marginBottom: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.038', 'Failure Trend (Daily)')}</Text>
            {failureTrend.length === 0 ? (
              <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.039', 'No trend data yet.')}</Text>
            ) : failureTrend.slice(-10).map((row: any, idx: number) => (
              <View key={`${row?.date || 'd'}-${idx}`} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 }} data-testid={`ae-failure-trend-row-${idx + 1}`} testID={`ae-failure-trend-row-${idx + 1}`}>
                <Text style={{ fontSize: 10, color: C.muted, width: 90 }}>{row?.date}</Text>
                <View style={{ flex: 1, marginHorizontal: 8, height: 6, borderRadius: 4, backgroundColor: AC.borderStrong }}>
                  <View style={{ width: `${Math.min(100, Number(row?.failures || 0) * 12)}%`, height: 6, borderRadius: 4, backgroundColor: colors.error }} />
                </View>
                <Text style={{ fontSize: 10, color: C.text, width: 84, textAlign: 'right' }}>{row?.failures || 0} fail / {row?.confirmed || 0} fixed</Text>
              </View>
            ))}
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <View style={{ flex: 1, minWidth: 280, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-failure-types-card" testID="ae-failure-types-card">
              <Text style={{ fontSize: 12, color: C.text, fontWeight: '800', marginBottom: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.040', 'Top Failure Types')}</Text>
              {failureTypes.length === 0 ? <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.041', 'No failure type data.')}</Text> : failureTypes.map((row: any, idx: number) => (
                <Text key={`${row?.failure_type || 'type'}-${idx}`} style={{ fontSize: 10, color: C.text, marginBottom: 4 }} data-testid={`ae-failure-type-row-${idx + 1}`} testID={`ae-failure-type-row-${idx + 1}`}>
                  {idx + 1}. {row?.failure_type || 'unknown'} — {row?.count || 0}
                </Text>
              ))}
            </View>

            <View style={{ flex: 1, minWidth: 280, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-root-causes-card" testID="ae-root-causes-card">
              <Text style={{ fontSize: 12, color: C.text, fontWeight: '800', marginBottom: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.042', 'Top Root Causes')}</Text>
              {failureRootCauses.length === 0 ? <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.043', 'No root-cause data.')}</Text> : failureRootCauses.map((row: any, idx: number) => (
                <Text key={`${row?.root_cause || 'cause'}-${idx}`} style={{ fontSize: 10, color: C.text, marginBottom: 4 }} numberOfLines={2} data-testid={`ae-root-cause-row-${idx + 1}`} testID={`ae-root-cause-row-${idx + 1}`}>
                  {idx + 1}. {row?.root_cause || 'unknown'} — {row?.count || 0}
                </Text>
              ))}
            </View>

            <View style={{ flex: 1, minWidth: 280, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12 }} data-testid="ae-failure-owners-card" testID="ae-failure-owners-card">
              <Text style={{ fontSize: 12, color: C.text, fontWeight: '800', marginBottom: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.044', 'Top Owners')}</Text>
              {failureOwners.length === 0 ? <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.045', 'No owner assignments yet.')}</Text> : failureOwners.map((row: any, idx: number) => (
                <Text key={`${row?.owner || 'owner'}-${idx}`} style={{ fontSize: 10, color: C.text, marginBottom: 4 }} data-testid={`ae-failure-owner-row-${idx + 1}`} testID={`ae-failure-owner-row-${idx + 1}`}>
                  {idx + 1}. {row?.owner || 'unassigned'} — {row?.count || 0}
                </Text>
              ))}
            </View>
          </View>

          <View style={{ backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 12, marginTop: 12 }} data-testid="ae-unresolved-failures-card" testID="ae-unresolved-failures-card">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text style={{ fontSize: 12, color: C.text, fontWeight: '800' }}>{tx('admin.autonomousEnginePanel.auto.text.046', 'Unresolved Failures')}</Text>
              <TouchableOpacity
                onPress={reconcileFailureMemory}
                disabled={reconcilingFailureMemory}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 7, borderWidth: 1, borderColor: `${colors.info}55`, backgroundColor: `${colors.info}22`, opacity: reconcilingFailureMemory ? 0.7 : 1 }}
                data-testid="ae-failure-reconcile-btn"
                testID="ae-failure-reconcile-btn"
              >
                <Text style={{ fontSize: 9, color: colors.info, fontWeight: '700' }}>{reconcilingFailureMemory ? 'Reconciling…' : 'Run Auto-Reconcile'}</Text>
              </TouchableOpacity>
            </View>
            {unresolvedFailures.length === 0 ? <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.047', 'No unresolved failures in selected window.')}</Text> : unresolvedFailures.map((row: any, idx: number) => {
              const rowKey = `${row?.logged_at || ''}|${row?.failure_type || ''}|${row?.component || ''}`;
              const isResolving = resolvingFailureKey === rowKey;
              const isAssigning = assigningFailureKey === rowKey;
              const owner = String(row?.owner || 'unassigned');
              const severity = String(row?.severity || 'high').toUpperCase();
              const slaStatus = String(row?.sla_status || 'ON_TRACK').toUpperCase();
              const slaDueAt = String(row?.sla_due_at || '').slice(0, 19);
              const slaColor = slaStatus === 'BREACHED' ? colors.warning : colors.success;
              return (
              <View key={`${row?.logged_at || 'entry'}-${idx}`} style={{ borderBottomWidth: idx === unresolvedFailures.length - 1 ? 0 : 1, borderBottomColor: C.border, paddingVertical: 6 }} data-testid={`ae-unresolved-failure-row-${idx + 1}`} testID={`ae-unresolved-failure-row-${idx + 1}`}>
                <Text style={{ fontSize: 10, color: colors.errorText, fontWeight: '700' }}>{row?.failure_type || 'unknown'} • {row?.component || 'unknown'}</Text>
                <Text style={{ fontSize: 10, color: C.text, marginTop: 2 }} numberOfLines={2}>{row?.root_cause || row?.error_signature || 'No root cause'}</Text>
                <Text style={{ fontSize: 9, color: C.muted, marginTop: 3 }} data-testid={`ae-unresolved-failure-row-${idx + 1}-owner`} testID={`ae-unresolved-failure-row-${idx + 1}-owner`}>
                  Owner: {owner} • Severity: {severity} • Occurrences: {Number(row?.occurrence_count || 1)}
                </Text>
                <Text style={{ fontSize: 9, color: slaColor, marginTop: 2, fontWeight: '700' }} data-testid={`ae-unresolved-failure-row-${idx + 1}-sla`} testID={`ae-unresolved-failure-row-${idx + 1}-sla`}>
                  SLA: {slaStatus}{slaDueAt ? ` • Due ${slaDueAt}` : ''}
                </Text>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
                  <Text style={{ fontSize: 9, color: C.muted }}>{String(row?.logged_at || '').slice(0, 19)}</Text>
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <TouchableOpacity
                      onPress={() => assignFailureOwner(row)}
                      disabled={isAssigning}
                      style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 7, borderWidth: 1, borderColor: `${colors.info}55`, backgroundColor: `${colors.info}22`, opacity: isAssigning ? 0.7 : 1 }}
                      data-testid={`ae-unresolved-failure-row-${idx + 1}-assign-btn`}
                      testID={`ae-unresolved-failure-row-${idx + 1}-assign-btn`}
                    >
                      <Text style={{ fontSize: 9, color: colors.info, fontWeight: '700' }}>{isAssigning ? 'Assigning…' : 'Assign Owner'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => resolveFailureEntry(row)}
                      disabled={isResolving}
                      style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 7, borderWidth: 1, borderColor: colors.successSoft, backgroundColor: colors.successSoft, opacity: isResolving ? 0.7 : 1 }}
                      data-testid={`ae-unresolved-failure-row-${idx + 1}-resolve-btn`}
                      testID={`ae-unresolved-failure-row-${idx + 1}-resolve-btn`}
                    >
                      <Text style={{ fontSize: 9, color: colors.successText, fontWeight: '700' }}>{isResolving ? 'Resolving…' : 'Resolve Ticket'}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            );})}
          </View>
        </View>
      )}

      {activeTab === 'experiments' && (
        <View data-testid="ae-experiments-tab" testID="ae-experiments-tab">
          <OnboardingABPanel colors={C} />
        </View>
      )}

      {/* Config Tab */}
      {activeTab === 'config' && config && (
        <View data-testid="ae-config-tab" testID="ae-config-tab">
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.autonomousEnginePanel.auto.text.048', 'Engine Settings')}</Text>

            {/* Toggle switches */}
            {[
              { key: 'enabled', label: 'Engine Enabled', icon: 'power' },
              { key: 'auto_heal_enabled', label: 'Auto-Heal Loop', icon: 'refresh' },
              { key: 'strict_hard_gate', label: 'Strict Hard-Gate Enforcement', icon: 'lock-closed' },
              { key: 'notify_on_fail', label: 'Notify on FAIL', icon: 'notifications' },
              { key: 'notify_on_pass', label: 'Notify on PASS', icon: 'checkmark-circle' },
            ].map(({ key, label, icon }) => (
              <TouchableOpacity
                key={key}
                onPress={() => updateConfig({ [key]: !config[key] })}
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.border }}
                data-testid={`ae-config-${key}`} testID={`ae-config-${key}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <Ionicons name={icon as any} size={16} color={C.muted} />
                  <Text style={{ fontSize: 12, color: C.text }}>{label}</Text>
                </View>
                <View style={{ width: 40, height: 22, borderRadius: 11, backgroundColor: config[key] ? colors.success : C.border, justifyContent: 'center', paddingHorizontal: 2 }}>
                  <View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: T.primaryText, alignSelf: config[key] ? 'flex-end' : 'flex-start' }} />
                </View>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.049', 'Completion Gate Window')}</Text>
            <Text style={{ fontSize: 10, color: C.muted, marginBottom: 10 }}>{tx('admin.autonomousEnginePanel.auto.text.050', 'Require a PASS run within this many minutes before completion is allowed.')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text style={{ fontSize: 18, fontWeight: '900', color: colors.warningText }} data-testid="ae-require-pass-window" testID="ae-require-pass-window">
                {config.require_recent_pass_minutes || 240} min
              </Text>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity
                  onPress={() => updateConfig({ require_recent_pass_minutes: Math.max(1, Number(config.require_recent_pass_minutes || 240) - 30) })}
                  style={{ width: 34, height: 30, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }}
                  data-testid="ae-window-decrease-btn"
                  testID="ae-window-decrease-btn"
                >
                  <Ionicons name="remove" size={14} color={C.text} />
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => updateConfig({ require_recent_pass_minutes: Number(config.require_recent_pass_minutes || 240) + 30 })}
                  style={{ width: 34, height: 30, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }}
                  data-testid="ae-window-increase-btn"
                  testID="ae-window-increase-btn"
                >
                  <Ionicons name="add" size={14} color={C.text} />
                </TouchableOpacity>
              </View>
            </View>
          </View>

          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }} data-testid="ae-predictive-config-card" testID="ae-predictive-config-card">
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 8 }}>{tx('admin.autonomousEnginePanel.auto.text.051', 'Predictive Failure Prevention')}</Text>
            <Text style={{ fontSize: 10, color: C.muted, marginBottom: 10 }}>{tx('admin.autonomousEnginePanel.auto.text.052', 'Predict likely failures, apply preventive fixes, and validate before customer impact.')}</Text>

            {[
              { key: 'enabled', label: 'Predictive Mode Enabled' },
              { key: 'auto_preemptive_fix', label: 'Auto Preemptive Fix' },
              { key: 'run_validation_after_fix', label: 'Run Validation After Fix' },
              { key: 'scheduler_enabled', label: 'Scheduler Enabled' },
            ].map(({ key, label }) => (
              <TouchableOpacity
                key={key}
                onPress={() => updatePredictivePolicy({ [key]: !Boolean(predictiveConfig?.[key]) })}
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: C.border }}
                data-testid={`ae-predictive-toggle-${key}`}
                testID={`ae-predictive-toggle-${key}`}
              >
                <Text style={{ fontSize: 11, color: C.text }}>{label}</Text>
                <View style={{ width: 36, height: 20, borderRadius: 10, backgroundColor: predictiveConfig?.[key] ? colors.success : C.border, justifyContent: 'center', paddingHorizontal: 2 }}>
                  <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: T.primaryText, alignSelf: predictiveConfig?.[key] ? 'flex-end' : 'flex-start' }} />
                </View>
              </TouchableOpacity>
            ))}

            <View style={{ marginTop: 12, gap: 10 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.053', 'Confidence Threshold')}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <TouchableOpacity
                    onPress={() => updatePredictivePolicy({ confidence_threshold: Math.max(1, Number(predictiveConfig?.confidence_threshold || 75) - 5) })}
                    style={{ width: 30, height: 26, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }}
                    data-testid="ae-predictive-threshold-decrease-btn"
                    testID="ae-predictive-threshold-decrease-btn"
                  >
                    <Ionicons name="remove" size={14} color={C.text} />
                  </TouchableOpacity>
                  <Text style={{ fontSize: 11, color: colors.warningText, fontWeight: '700' }} data-testid="ae-predictive-threshold-value" testID="ae-predictive-threshold-value">
                    {Number(predictiveConfig?.confidence_threshold || 75)}
                  </Text>
                  <TouchableOpacity
                    onPress={() => updatePredictivePolicy({ confidence_threshold: Math.min(99, Number(predictiveConfig?.confidence_threshold || 75) + 5) })}
                    style={{ width: 30, height: 26, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }}
                    data-testid="ae-predictive-threshold-increase-btn"
                    testID="ae-predictive-threshold-increase-btn"
                  >
                    <Ionicons name="add" size={14} color={C.text} />
                  </TouchableOpacity>
                </View>
              </View>

              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.autonomousEnginePanel.auto.text.054', 'Scheduler Interval (min)')}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <TouchableOpacity
                    onPress={() => updatePredictivePolicy({ scheduled_interval_minutes: Math.max(5, Number(predictiveConfig?.scheduled_interval_minutes || 30) - 5) })}
                    style={{ width: 30, height: 26, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }}
                    data-testid="ae-predictive-interval-decrease-btn"
                    testID="ae-predictive-interval-decrease-btn"
                  >
                    <Ionicons name="remove" size={14} color={C.text} />
                  </TouchableOpacity>
                  <Text style={{ fontSize: 11, color: colors.primary, fontWeight: '700' }} data-testid="ae-predictive-interval-value" testID="ae-predictive-interval-value">
                    {Number(predictiveConfig?.scheduled_interval_minutes || 30)}
                  </Text>
                  <TouchableOpacity
                    onPress={() => updatePredictivePolicy({ scheduled_interval_minutes: Math.min(1440, Number(predictiveConfig?.scheduled_interval_minutes || 30) + 5) })}
                    style={{ width: 30, height: 26, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg, borderWidth: 1, borderColor: C.border }}
                    data-testid="ae-predictive-interval-increase-btn"
                    testID="ae-predictive-interval-increase-btn"
                  >
                    <Ionicons name="add" size={14} color={C.text} />
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          </View>

          {/* Gate Toggles */}
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.autonomousEnginePanel.auto.text.055', 'Gate Toggles')}</Text>
            {Object.keys(config.gates_enabled || {}).map(gate => (
              <TouchableOpacity
                key={gate}
                onPress={() => updateConfig({ gates_enabled: { ...config.gates_enabled, [gate]: !config.gates_enabled[gate] } })}
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}
                data-testid={`ae-gate-toggle-${gate}`} testID={`ae-gate-toggle-${gate}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <Ionicons name={GATE_ICONS[gate] as any || 'help-outline'} size={14} color={C.muted} />
                  <Text style={{ fontSize: 12, color: C.text }}>{GATE_LABELS[gate] || gate}</Text>
                </View>
                <View style={{ width: 36, height: 20, borderRadius: 10, backgroundColor: config.gates_enabled[gate] ? colors.primary : C.border, justifyContent: 'center', paddingHorizontal: 2 }}>
                  <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: T.primaryText, alignSelf: config.gates_enabled[gate] ? 'flex-end' : 'flex-start' }} />
                </View>
              </TouchableOpacity>
            ))}
          </View>

          {/* Performance Thresholds */}
          <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 12 }}>{tx('admin.autonomousEnginePanel.auto.text.056', 'Performance Thresholds (Hard Enforced)')}</Text>
            {Object.entries(config.performance_thresholds || {}).map(([k, v]) => (
              <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }}>
                <Text style={{ fontSize: 11, color: C.muted }}>{k.replace(/_/g, ' ')}</Text>
                <Text style={{ fontSize: 11, fontWeight: '700', color: colors.warningText }}>{String(v)}{k.includes('ms') ? 'ms' : k.includes('kb') ? 'KB' : k.includes('_s') ? 's' : ''}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </ScrollView>
  );
}
