/**
 * GtecScanV2Panel
 * ---------------
 * Upgraded "GTEC C5 — Global System Directive" panel for the Security
 * Dashboard. Replaces/augments the v1 crawler panel and enforces the
 * non-bypassable directive pipeline:
 *
 *   SAST + Dependency + DAST + RBAC + Subscription + Responsiveness + Perf
 *
 * UI controls:
 *   - MANUAL SCAN BUTTON
 *   - SAFE AUTO RUNS (toggle)
 *   - SCHEDULE SAFE AUTO RUN (interval hours picker)
 *
 * Backend: /api/admin/gtec-scan-v2/*
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, ScrollView, Text, TouchableOpacity, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

type V3Output = {
  SYSTEM_STATUS?: 'PASS' | 'FAIL';
  SECURITY_STATUS?: 'PASS' | 'FAIL';
  PERFORMANCE_STATUS?: 'PASS' | 'FAIL';
  I18N_STATUS?: 'PASS' | 'FAIL';
  RBAC_STATUS?: 'PASS' | 'FAIL';
  REGRESSION_STATUS?: 'PASS' | 'FAIL';
  ERROR_COUNT?: string | number;
  ACTIVE_FIXES?: 'YES' | 'NO';
  MONITORING?: 'ACTIVE' | 'INACTIVE';
  LEARNING_MEMORY?: 'UPDATED' | 'NOT UPDATED';
  CONFIDENCE_LEVEL?: 'HIGH' | 'MEDIUM' | 'LOW';
};

type Report = {
  task_id?: string;
  execution_hash?: string;
  status?: 'PASS' | 'FAIL';
  critical_vulns?: number;
  high_vulns?: number;
  medium_vulns?: number;
  low_vulns?: number;
  regressions?: 'YES' | 'NO';
  security_scan?: 'PASS' | 'FAIL';
  e2e_tests?: 'PASS' | 'FAIL';
  responsiveness?: 'PASS' | 'FAIL';
  performance?: 'PASS' | 'FAIL';
  rbac_status?: 'PASS' | 'FAIL';
  subscription_enforcement?: 'PASS' | 'FAIL';
  i18n_status?: 'PASS' | 'FAIL';
  learning_memory_updated?: 'YES' | 'NO';
  summary?: string;
  severity_counts?: { critical?: number; high?: number; medium?: number; low?: number };
  triggered_by?: string;
  actor?: string;
  generated_at?: string;
  elapsed_ms?: number;
  // GTEC SCAN v3 §13 — additive output (does NOT replace v2 §12)
  v3_output?: V3Output;
};

type Schedule = {
  enabled: boolean;
  interval_hours: number;
  enforced_interval_hours?: number;
  requested_interval_hours?: number;
  viewports?: string;
  updated_at?: string;
  updated_by?: string;
};

type PipelineState = {
  declared_mode?: 'soft-block' | 'hard-block' | string;
  effective_mode?: 'soft-block' | 'hard-block' | string;
  soft_block_started_at?: string;
  hard_block_after_hours?: number;
  hard_block_at?: string;
  updated_at?: string;
};

type ReleaseCertificate = {
  certificate_id?: string;
  trust_score_percent?: number;
  is_trust_grade_100?: boolean;
  checks?: {
    theme_v2?: { latest_score?: number; checked_at?: string };
    email_v7_darkmode?: { status?: string; scanned_at?: string };
    i18n_missing_open?: number;
    pipeline_enforcement?: PipelineState;
    db_security_hardening?: { status?: string; checked_at?: string; failed_indexes?: any[] };
    white_screen_sentry?: {
      status?: 'PASS' | 'FAIL' | 'UNKNOWN' | string;
      run_id?: string;
      failed_checks?: number;
      total_checks?: number;
      routes_tested?: number;
      generated_at?: string;
      route_source?: string;
    };
    responsive_viewport_matrix?: {
      viewports?: string[];
      matrix_summary?: Record<string, { pass?: number; fail?: number; total?: number }>;
      artifact_count?: number;
    };
    matrix64_pipeline?: {
      status?: string;
      strict_passed?: boolean;
      run_id?: string;
      generated_at?: string;
      required_total_checks?: number;
      total_checks?: number;
      failed_checks?: number;
      artifact_path?: string;
    };
  };
  generated_at?: string;
};

type Matrix64Run = {
  run_id?: string;
  status?: string;
  strict_passed?: boolean;
  generated_at?: string;
  dimensions?: { required_total_checks?: number };
  counts?: { total_checks?: number; failed_checks?: number };
  artifact_path?: string;
};

type GoNoGoDrill = {
  drill_id?: string;
  drill_at?: string;
  simulated_hard_block?: boolean;
  decision?: 'GO' | 'NO_GO' | string;
  reason?: string;
  trust_score_percent?: number;
  validation?: {
    hard_block_validation_passed?: boolean;
    all_gates_pass?: boolean;
  };
};

type ExternalCertificationRun = {
  certification_id?: string;
  status?: 'pass' | 'fail' | 'skipped_proxy_unstable' | 'busy' | string;
  reason?: string;
  triggered_by?: string;
  base_url?: string;
  started_at?: string;
  finished_at?: string;
  health?: { stable?: boolean; checks?: Array<{ path?: string; ok?: boolean; status_code?: number }> };
  white_screen?: { gate_passed?: boolean; failed_checks?: number; total_checks?: number; run_id?: string };
  drill?: { decision?: 'GO' | 'NO_GO' | string; drill_id?: string };
};

type IncidentLifecycleItem = {
  incident_id?: string;
  incident_key?: string;
  label?: string;
  severity?: string;
  status?: string;
  containment?: string;
  clean_rescan_streak?: number;
  pending_verification_started_at?: string;
  pending_verification_deadline?: string;
  resolution_reason?: string;
  task_id?: string;
  updated_at?: string;
  events?: Array<{ kind?: string; at?: string; task_id?: string }>;
};

const tx = (_key: string, fallback: string) => fallback;

function fmtRelative(iso?: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diff = Math.round((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  } catch { return iso; }
}

function withAlpha(color: string, hexAlpha: string): string {
  const a = Math.max(0, Math.min(1, parseInt(hexAlpha, 16) / 255));
  const c = String(color || '');
  if (c.startsWith('var(')) {
    const t = c.toLowerCase();
    if (t.includes('success')) return `rgba(16,185,129,${a})`;
    if (t.includes('warning')) return `rgba(245,158,11,${a})`;
    if (t.includes('error')) return `rgba(239,68,68,${a})`;
    if (t.includes('info')) return `rgba(14,165,233,${a})`;
    if (t.includes('muted') || t.includes('text')) return `rgba(100,116,139,${a})`;
    return `rgba(99,102,241,${a})`;
  }
  if (c.startsWith('#')) return `${c}${hexAlpha}`;
  return c;
}

export default function GtecScanV2Panel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const C = React.useMemo(() => ({
    bg: AC?.bg || 'var(--app-bg)',
    card: AC?.card || 'var(--app-card-bg)',
    cardAlt: AC?.bgAlt || AC?.cardSoft || 'var(--app-surface)',
    border: AC?.border || 'var(--app-border)',
    text: AC?.text || 'var(--app-text)',
    textSec: AC?.textSec || 'var(--app-text-sec)',
    muted: AC?.textMuted || 'var(--app-text-muted)',
    primary: AC?.primary || 'var(--app-primary)',
    success: AC?.success || 'var(--app-success)',
    warning: AC?.warning || 'var(--app-warning)',
    danger: AC?.error || 'var(--app-error)',
    accent: AC?.info || 'var(--app-primary)',
    purple: AC?.purple || AC?.primary || 'var(--app-primary)',
  }), [AC]);

  const [latest, setLatest] = useState<Report | null>(null);
  const [history, setHistory] = useState<Report[]>([]);
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [policy, setPolicy] = useState<{ mode?: string; manual_input_allowed?: boolean } | null>(null);
  const [incidentsOpen, setIncidentsOpen] = useState(0);
  const [directive, setDirective] = useState<{ text?: string; version?: string } | null>(null);
  const [directiveOpen, setDirectiveOpen] = useState(false);
  const [releaseCert, setReleaseCert] = useState<ReleaseCertificate | null>(null);
  const [pipelineState, setPipelineState] = useState<PipelineState | null>(null);
  const [lastDrill, setLastDrill] = useState<GoNoGoDrill | null>(null);
  const [drillBusy, setDrillBusy] = useState(false);
  const [externalCert, setExternalCert] = useState<ExternalCertificationRun | null>(null);
  const [externalCertBusy, setExternalCertBusy] = useState(false);
  const [matrix64Run, setMatrix64Run] = useState<Matrix64Run | null>(null);
  const [err, setErr] = useState('');
  // i18n v2 — per-locale coverage telemetry (auto-translation v2 dashboard badge)
  const [i18nCov, setI18nCov] = useState<{
    aggregate_coverage_pct?: number;
    health?: 'green' | 'amber' | 'red';
    drift_locales?: string[];
    full_locales?: string[];
    source_keys?: number;
    non_source_locales?: number;
  } | null>(null);
  const [i18nAdoption, setI18nAdoption] = useState<{
    adoption_pct?: number;
    hardcoded_copy_pct?: number;
    files_scanned?: number;
    files_using_t?: number;
  } | null>(null);
  const [incidentTimeline, setIncidentTimeline] = useState<IncidentLifecycleItem[]>([]);
  const [timelineBusy, setTimelineBusy] = useState(false);

  const loadLatest = useCallback(async () => {
    try {
      const r = await api.get('/admin/gtec-scan-v2/latest');
      setLatest(r.data?.report || null);
    } catch { /* ignore */ }
  }, []);
  const loadHistory = useCallback(async () => {
    try {
      const r = await api.get('/admin/gtec-scan-v2/history');
      setHistory(r.data?.items || []);
    } catch { /* ignore */ }
  }, []);
  const loadSchedule = useCallback(async () => {
    try {
      const r = await api.get('/admin/gtec-scan-v2/schedule');
      setSchedule({
        enabled: Boolean(r.data?.enabled),
        interval_hours: Number(r.data?.interval_hours ?? 6),
        viewports: r.data?.viewports || 'desktop',
        updated_at: r.data?.updated_at,
        updated_by: r.data?.updated_by,
      });
    } catch { /* ignore */ }
  }, []);
  const loadPolicy = useCallback(async () => {
    try {
      const [policyRes, incidentsRes] = await Promise.all([
        api.get('/admin/gtec-scan-v2/policy/effective'),
        api.get('/admin/gtec-scan-v2/incidents?status=open&limit=200'),
      ]);
      setPolicy(policyRes.data || null);
      setIncidentsOpen(Number(incidentsRes.data?.count || 0));
    } catch { /* ignore */ }
  }, []);
  const loadDirective = useCallback(async () => {
    try {
      const r = await api.get('/admin/gtec-scan-v2/directive');
      setDirective({ text: r.data?.directive_text, version: r.data?.directive_version });
    } catch { /* ignore */ }
  }, []);
  const loadReleaseCertificate = useCallback(async () => {
    try {
      const r = await api.get('/admin/gtec-scan-v2/release-certificate');
      const cert = r.data || null;
      setReleaseCert(cert);
      setPipelineState((cert?.checks?.pipeline_enforcement as PipelineState) || null);
    } catch { /* ignore */ }
  }, []);
  const loadLastDrill = useCallback(async () => {
    try {
      const r = await api.get('/admin/gtec-scan-v2/pipeline/go-no-go-drill/latest');
      setLastDrill((r.data?.drill || null) as GoNoGoDrill | null);
    } catch { /* ignore */ }
  }, []);
  const loadExternalCertification = useCallback(async () => {
    try {
      const r = await api.get('/admin/gtec-scan-v2/pipeline/external-host-certification/latest');
      setExternalCert((r.data?.certification_run || null) as ExternalCertificationRun | null);
    } catch { /* ignore */ }
  }, []);
  const loadMatrix64 = useCallback(async () => {
    try {
      const r = await api.get('/admin/gtec-scan-v2/pipeline/matrix64/latest');
      setMatrix64Run((r.data?.run || null) as Matrix64Run | null);
    } catch { /* ignore */ }
  }, []);
  const runFormalDrill = useCallback(async () => {
    setDrillBusy(true);
    setErr('');
    try {
      const r = await api.post('/admin/gtec-scan-v2/pipeline/go-no-go-drill', { simulate_hard_block: true });
      setLastDrill((r.data || null) as GoNoGoDrill | null);
      await loadReleaseCertificate();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Failed to run GO/NO-GO drill');
    } finally {
      setDrillBusy(false);
    }
  }, [loadReleaseCertificate]);
  const rerunExternalCertification = useCallback(async () => {
    setExternalCertBusy(true);
    setErr('');
    try {
      const r = await api.post('/admin/gtec-scan-v2/pipeline/external-host-certification/rerun', {
        force: false,
        include_release_drill: true,
        simulate_hard_block: true,
      });
      setExternalCert((r.data?.certification_run || null) as ExternalCertificationRun | null);
      await loadReleaseCertificate();
      await loadLastDrill();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Failed to run external-host certification rerun');
    } finally {
      setExternalCertBusy(false);
    }
  }, [loadLastDrill, loadReleaseCertificate]);
  const loadI18nCoverage = useCallback(async () => {
    try {
      const r = await api.get('/admin/i18n/coverage');
      setI18nCov({
        aggregate_coverage_pct: r.data?.aggregate_coverage_pct,
        health: r.data?.health,
        drift_locales: r.data?.drift_locales || [],
        full_locales: r.data?.full_locales || [],
        source_keys: r.data?.source_keys,
        non_source_locales: r.data?.non_source_locales,
      });
    } catch { /* ignore */ }
  }, []);
  const loadI18nAdoption = useCallback(async () => {
    try {
      const r = await api.get('/admin/i18n/adoption');
      setI18nAdoption({
        adoption_pct: r.data?.summary?.adoption_pct,
        hardcoded_copy_pct: r.data?.summary?.hardcoded_copy_pct,
        files_scanned: r.data?.summary?.files_scanned,
        files_using_t: r.data?.summary?.files_using_t,
      });
    } catch { /* ignore */ }
  }, []);
  const loadIncidentTimeline = useCallback(async () => {
    setTimelineBusy(true);
    try {
      const r = await api.get('/admin/gtec-scan-v2/incidents/lifecycle-timeline?limit=12');
      setIncidentTimeline((r.data?.items || []) as IncidentLifecycleItem[]);
    } catch { /* ignore */ }
    setTimelineBusy(false);
  }, []);

  useEffect(() => {
    void loadLatest();
    void loadHistory();
    void loadSchedule();
    void loadPolicy();
    void loadDirective();
    void loadReleaseCertificate();
    void loadLastDrill();
    void loadExternalCertification();
    void loadMatrix64();
    void loadI18nCoverage();
    void loadI18nAdoption();
    void loadIncidentTimeline();
  }, [loadLatest, loadHistory, loadSchedule, loadPolicy, loadDirective, loadReleaseCertificate, loadLastDrill, loadExternalCertification, loadMatrix64, loadI18nCoverage, loadI18nAdoption, loadIncidentTimeline]);
  const overallStatus = latest?.status;
  const statusColor = overallStatus === 'PASS' ? C.success : overallStatus === 'FAIL' ? C.danger : C.muted;
  const i18nCoveragePill = React.useMemo(() => {
    if (!i18nCov) return null;
    const tone = i18nCov.health === 'green' ? { bg: withAlpha(C.success, '22'), fg: C.success, label: 'i18n ✓' }
      : i18nCov.health === 'red' ? { bg: withAlpha(C.danger, '22'), fg: C.danger, label: 'i18n ✗' }
        : { bg: withAlpha(C.warning, '22'), fg: C.warning, label: 'i18n ⚠' };
    const driftCount = i18nCov.drift_locales?.length ?? 0;
    const tooltip = `i18n coverage: ${i18nCov.aggregate_coverage_pct}% across ${i18nCov.non_source_locales} locales · ${driftCount} drifting`;
    return { ...tone, tooltip };
  }, [i18nCov, C]);

  return (
    <View
      data-testid="gtec-scan-v2-panel"
      testID="gtec-scan-v2-panel"
      style={{
        marginTop: 16, borderRadius: 16, borderWidth: 1,
        borderColor: C.border, backgroundColor: C.card, padding: 18,
      }}
    >
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 4, flexWrap: 'wrap' }}>
        <View style={{
          width: 44, height: 44, borderRadius: 12, backgroundColor: withAlpha(C.accent, '18'),
          alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: withAlpha(C.accent, '32'),
        }}>
          <Ionicons name="shield-half" size={22} color={C.accent} />
        </View>
        <View style={{ flex: 1, minWidth: 220 }}>
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', letterSpacing: -0.3 }}
                data-testid="gtec-v2-title" testID="gtec-v2-title">{tx('admin.gtecScanV2Panel.auto.text.001', 'GTEC C5 — Global System Directive')}</Text>
          <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{tx('admin.gtecScanV2Panel.auto.text.002', 'SAST · Dependency · DAST · RBAC · Subscription · Responsiveness · Performance')}</Text>
        </View>
        <View
          data-testid="gtec-v2-directive-pill"
          testID="gtec-v2-directive-pill"
          style={{
            paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999,
            backgroundColor: withAlpha(C.success, '18'), borderWidth: 1, borderColor: withAlpha(C.success, '3A'),
          }}>
          <Text style={{ color: C.success, fontSize: 10, fontWeight: '800', letterSpacing: 0.4 }}>{tx('admin.gtecScanV2Panel.auto.text.003', 'ALWAYS ACTIVE')}</Text>
        </View>
        {i18nCoveragePill ? (
          <View
            style={{
              paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999,
              backgroundColor: i18nCoveragePill.bg,
              borderWidth: 1,
              borderColor: withAlpha(i18nCoveragePill.fg, '44'),
            }}
            data-testid="i18n-coverage-pill"
            testID="i18n-coverage-pill"
          >
            <Text
              style={{ color: i18nCoveragePill.fg, fontSize: 10, fontWeight: '800', letterSpacing: 0.4 }}
              // @ts-ignore — title is web-only, used as native tooltip
              title={i18nCoveragePill.tooltip}
            >
              {i18nCoveragePill.label} {i18nCov?.aggregate_coverage_pct}%
            </Text>
          </View>
        ) : null}
      </View>
      {schedule?.requested_interval_hours && schedule.requested_interval_hours !== schedule.interval_hours ? (
        <Text
          style={{ color: C.warning, fontSize: 10, marginTop: 6 }}
          data-testid="gtec-v2-enforced-interval-note"
          testID="gtec-v2-enforced-interval-note"
        >
          Requested interval {schedule.requested_interval_hours}h overridden by directive policy → enforced {schedule.interval_hours}h.
        </Text>
      ) : null}

      {/* i18n parity + adoption telemetry */}
      <View
        style={{
          marginTop: 10,
          marginBottom: 12,
          borderRadius: 12,
          borderWidth: 1,
          borderColor: C.border,
          backgroundColor: C.cardAlt,
          padding: 12,
          gap: 10,
        }}
        data-testid="i18n-metrics-dual-card"
        testID="i18n-metrics-dual-card"
      >
        <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{tx('admin.gtecScanV2Panel.auto.text.004', 'i18n telemetry — parity vs usage adoption')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <View
            style={{
              flex: 1,
              minWidth: 240,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.card,
              padding: 10,
            }}
            data-testid="i18n-key-parity-metric"
            testID="i18n-key-parity-metric"
          >
            <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{tx('admin.gtecScanV2Panel.auto.text.005', 'Key parity')}</Text>
            <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', marginTop: 2 }}>
              {i18nCov?.aggregate_coverage_pct ?? '—'}%
            </Text>
            <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
              {i18nCov?.source_keys ?? '—'} source keys · {i18nCov?.non_source_locales ?? '—'} locales
            </Text>
          </View>

          <View
            style={{
              flex: 1,
              minWidth: 240,
              borderRadius: 10,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.card,
              padding: 10,
            }}
            data-testid="i18n-ui-adoption-metric"
            testID="i18n-ui-adoption-metric"
          >
            <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{tx('admin.gtecScanV2Panel.auto.text.006', 'UI adoption')}</Text>
            <Text style={{ color: C.text, fontSize: 18, fontWeight: '900', marginTop: 2 }}>
              {i18nAdoption?.adoption_pct ?? '—'}%
            </Text>
            <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
              {i18nAdoption?.files_using_t ?? '—'} of {i18nAdoption?.files_scanned ?? '—'} files use t()
            </Text>
            <Text style={{ color: C.muted, fontSize: 10, marginTop: 1 }}>
              Hardcoded copy footprint: {i18nAdoption?.hardcoded_copy_pct ?? '—'}%
            </Text>
          </View>
        </View>
      </View>

      {/* Directive summary + expand */}
      <TouchableOpacity
        onPress={() => setDirectiveOpen(o => !o)}
        data-testid="gtec-v2-directive-toggle" testID="gtec-v2-directive-toggle"
        style={{
          flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12, marginBottom: 10,
          alignSelf: 'flex-start',
        }}>
        <Ionicons name={directiveOpen ? 'chevron-down' : 'chevron-forward'} size={13} color={C.textSec} />
        <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.gtecScanV2Panel.auto.text.007', 'View directive')}</Text>
        {directive?.version ? (
          <Text style={{ color: C.muted, fontSize: 10 }}>v{directive.version}</Text>
        ) : null}
      </TouchableOpacity>
      {directiveOpen && directive?.text ? (
        <ScrollView
          style={{
            maxHeight: 220, borderWidth: 1, borderColor: C.border, borderRadius: 10,
            backgroundColor: C.cardAlt, padding: 10, marginBottom: 14,
          }}
          data-testid="gtec-v2-directive-text" testID="gtec-v2-directive-text"
        >
          <Text style={{ color: C.textSec, fontSize: 11, lineHeight: 16 }}>{directive.text}</Text>
        </ScrollView>
      ) : null}

      {/* ── Autonomous policy row (read-only) ── */}
      <View
        data-testid="gtec-v2-auto-run-row"
        testID="gtec-v2-auto-run-row"
        style={{
          borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardAlt,
          padding: 12, marginBottom: 14,
        }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }} data-testid="gtec-v2-autonomous-title" testID="gtec-v2-autonomous-title">
              Autonomous-only execution policy
            </Text>
            <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
              Manual scan/schedule mutations are disabled. Runs are fully automated via scheduler/events.
            </Text>
          </View>
          <View data-testid="gtec-v2-auto-run-toggle" testID="gtec-v2-auto-run-toggle" style={{ borderRadius: 999, borderWidth: 1, borderColor: withAlpha(C.success, '44'), backgroundColor: withAlpha(C.success, '22'), paddingHorizontal: 10, paddingVertical: 6 }}>
            <Text style={{ color: C.success, fontSize: 10, fontWeight: '800' }}>LOCKED ON</Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12, flexWrap: 'wrap' }}
              data-testid="gtec-v2-schedule-row" testID="gtec-v2-schedule-row">
          <Ionicons name="time-outline" size={13} color={C.textSec} />
          <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '700', marginRight: 4 }}>Schedule every</Text>
          <View data-testid="gtec-v2-schedule-3h" testID="gtec-v2-schedule-3h" style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: C.accent, backgroundColor: withAlpha(C.accent, '18') }}>
            <Text style={{ color: C.accent, fontSize: 10, fontWeight: '800' }}>{schedule?.interval_hours || 3}h</Text>
          </View>
          <Text style={{ color: C.muted, fontSize: 10 }}>runtime immutable</Text>
          <Text data-testid="gtec-v2-policy-mode" testID="gtec-v2-policy-mode" style={{ color: C.muted, fontSize: 10 }}>
            mode: {policy?.mode || 'autonomous_only'}
          </Text>
          <Text data-testid="gtec-v2-open-incidents" testID="gtec-v2-open-incidents" style={{ color: incidentsOpen > 0 ? C.warning : C.success, fontSize: 10, fontWeight: '700' }}>
            open incidents: {incidentsOpen}
          </Text>
        </View>
        {schedule?.updated_at ? (
          <Text style={{ color: C.muted, fontSize: 9, marginTop: 8 }}
                data-testid="gtec-v2-schedule-updated-at" testID="gtec-v2-schedule-updated-at">
            Updated {fmtRelative(schedule.updated_at)} by {schedule.updated_by || '—'}
          </Text>
        ) : null}
      </View>

      {/* ── Incident lifecycle timeline (auto-close evidence) ── */}
      <View
        data-testid="gtec-c5-incident-lifecycle-card"
        testID="gtec-c5-incident-lifecycle-card"
        style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: C.border,
          backgroundColor: C.cardAlt,
          padding: 12,
          marginBottom: 14,
          gap: 8,
        }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }} data-testid="gtec-c5-incident-lifecycle-title" testID="gtec-c5-incident-lifecycle-title">
            Incident lifecycle timeline
          </Text>
          <TouchableOpacity
            data-testid="gtec-c5-incident-lifecycle-refresh-button"
            testID="gtec-c5-incident-lifecycle-refresh-button"
            onPress={loadIncidentTimeline}
            disabled={timelineBusy}
            style={{
              borderRadius: 999,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: C.card,
              paddingHorizontal: 10,
              paddingVertical: 6,
              opacity: timelineBusy ? 0.7 : 1,
            }}
          >
            <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '800' }}>{timelineBusy ? 'Refreshing…' : 'Refresh timeline'}</Text>
          </TouchableOpacity>
        </View>

        {incidentTimeline.length === 0 ? (
          <Text style={{ color: C.muted, fontSize: 10 }} data-testid="gtec-c5-incident-lifecycle-empty" testID="gtec-c5-incident-lifecycle-empty">
            No incident lifecycle events yet.
          </Text>
        ) : (
          <View style={{ gap: 8 }}>
            {incidentTimeline.map((inc, idx) => {
              const sev = String(inc.severity || '').toUpperCase();
              const status = String(inc.status || 'unknown').toUpperCase();
              const sevColor = sev === 'CRITICAL' || sev === 'HIGH' ? C.danger : sev === 'MEDIUM' ? C.warning : C.success;
              const statusColor = status === 'CLOSED' ? C.success : status.includes('PENDING') ? C.warning : C.text;
              return (
                <View
                  key={`${inc.incident_id || inc.incident_key || 'incident'}-${idx}`}
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, gap: 4 }}
                  data-testid={`gtec-c5-incident-lifecycle-row-${idx}`}
                  testID={`gtec-c5-incident-lifecycle-row-${idx}`}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }} data-testid={`gtec-c5-incident-lifecycle-row-key-${idx}`} testID={`gtec-c5-incident-lifecycle-row-key-${idx}`}>
                      {inc.label || inc.incident_key || 'Incident'}
                    </Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Text style={{ color: sevColor, fontSize: 9, fontWeight: '800' }} data-testid={`gtec-c5-incident-lifecycle-row-severity-${idx}`} testID={`gtec-c5-incident-lifecycle-row-severity-${idx}`}>
                        {sev || '—'}
                      </Text>
                      <Text style={{ color: statusColor, fontSize: 9, fontWeight: '800' }} data-testid={`gtec-c5-incident-lifecycle-row-status-${idx}`} testID={`gtec-c5-incident-lifecycle-row-status-${idx}`}>
                        {status}
                      </Text>
                    </View>
                  </View>

                  <Text style={{ color: C.muted, fontSize: 9 }} data-testid={`gtec-c5-incident-lifecycle-row-streak-${idx}`} testID={`gtec-c5-incident-lifecycle-row-streak-${idx}`}>
                    clean rescans: {inc.clean_rescan_streak ?? 0}
                    {inc.pending_verification_deadline ? ` · pending until ${fmtRelative(inc.pending_verification_deadline)}` : ''}
                  </Text>
                  {inc.resolution_reason ? (
                    <Text style={{ color: C.muted, fontSize: 9 }} data-testid={`gtec-c5-incident-lifecycle-row-reason-${idx}`} testID={`gtec-c5-incident-lifecycle-row-reason-${idx}`}>
                      reason: {inc.resolution_reason}
                    </Text>
                  ) : null}
                  <Text style={{ color: C.muted, fontSize: 9 }} data-testid={`gtec-c5-incident-lifecycle-row-updated-${idx}`} testID={`gtec-c5-incident-lifecycle-row-updated-${idx}`}>
                    updated {fmtRelative(inc.updated_at)}
                  </Text>
                </View>
              );
            })}
          </View>
        )}
      </View>

      {/* ── Executive release certificate + pipeline mode (read-only) ── */}
      <View
        data-testid="gtec-c5-exec-certificate-card"
        testID="gtec-c5-exec-certificate-card"
        style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: C.border,
          backgroundColor: C.cardAlt,
          padding: 12,
          marginBottom: 14,
          gap: 8,
        }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }} data-testid="gtec-c5-exec-certificate-title" testID="gtec-c5-exec-certificate-title">
            Executive release certificate · GO/NO-GO readiness
          </Text>
          <View
            data-testid="gtec-c5-exec-trust-pill"
            testID="gtec-c5-exec-trust-pill"
            style={{
              borderRadius: 999,
              borderWidth: 1,
              borderColor: withAlpha((releaseCert?.is_trust_grade_100 ? C.success : C.warning), '44'),
              backgroundColor: withAlpha((releaseCert?.is_trust_grade_100 ? C.success : C.warning), '22'),
              paddingHorizontal: 10,
              paddingVertical: 5,
            }}
          >
            <Text style={{ color: releaseCert?.is_trust_grade_100 ? C.success : C.warning, fontSize: 10, fontWeight: '800' }}>
              TRUST {releaseCert?.trust_score_percent ?? '—'}%
            </Text>
          </View>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, minWidth: 170 }} data-testid="gtec-c5-pipeline-mode-card" testID="gtec-c5-pipeline-mode-card">
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>Pipeline mode</Text>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginTop: 2 }}>
              {pipelineState?.effective_mode || 'soft-block'}
            </Text>
            <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>
              hard-block at {pipelineState?.hard_block_at ? fmtRelative(pipelineState.hard_block_at) : '—'}
            </Text>
          </View>

          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, minWidth: 170 }} data-testid="gtec-c5-theme-v2-card" testID="gtec-c5-theme-v2-card">
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>Theme v2</Text>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginTop: 2 }}>
              score {releaseCert?.checks?.theme_v2?.latest_score ?? '—'}
            </Text>
          </View>

          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, minWidth: 170 }} data-testid="gtec-c5-email-v7-card" testID="gtec-c5-email-v7-card">
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>Email v7 dark/light</Text>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginTop: 2 }}>
              {String(releaseCert?.checks?.email_v7_darkmode?.status || 'unknown').toUpperCase()}
            </Text>
          </View>

          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, minWidth: 170 }} data-testid="gtec-c5-i18n-card" testID="gtec-c5-i18n-card">
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>i18n open drift</Text>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginTop: 2 }}>
              {releaseCert?.checks?.i18n_missing_open ?? '—'}
            </Text>
          </View>

          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, minWidth: 170 }} data-testid="gtec-c5-db-hardening-card" testID="gtec-c5-db-hardening-card">
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>DB hardening</Text>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginTop: 2 }}>
              {String(releaseCert?.checks?.db_security_hardening?.status || 'unknown').toUpperCase()}
            </Text>
          </View>

          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, minWidth: 210 }} data-testid="gtec-c5-white-screen-sentry-card" testID="gtec-c5-white-screen-sentry-card">
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>White-screen sentry gate</Text>
            <Text
              style={{
                color:
                  releaseCert?.checks?.white_screen_sentry?.status === 'PASS'
                    ? C.success
                    : releaseCert?.checks?.white_screen_sentry?.status === 'FAIL'
                      ? C.danger
                      : C.warning,
                fontSize: 11,
                fontWeight: '800',
                marginTop: 2,
              }}
            >
              {String(releaseCert?.checks?.white_screen_sentry?.status || 'UNKNOWN').toUpperCase()}
            </Text>
            <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>
              {releaseCert?.checks?.white_screen_sentry?.failed_checks ?? '—'}/
              {releaseCert?.checks?.white_screen_sentry?.total_checks ?? '—'} failed checks
            </Text>
          </View>

          <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8, minWidth: 210 }} data-testid="gtec-c5-viewport-matrix-card" testID="gtec-c5-viewport-matrix-card">
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>Responsive matrix artifacts</Text>
            <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginTop: 2 }}>
              {releaseCert?.checks?.responsive_viewport_matrix?.artifact_count ?? 0} screenshots
            </Text>
            <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>
              source: {releaseCert?.checks?.white_screen_sentry?.route_source || '—'}
            </Text>
          </View>
        </View>

        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8 }} data-testid="gtec-c5-last-drill-card" testID="gtec-c5-last-drill-card">
          <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>Last GO/NO-GO drill</Text>
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginTop: 2 }} data-testid="gtec-c5-last-drill-decision" testID="gtec-c5-last-drill-decision">
            {lastDrill?.decision || 'NOT RUN'}
          </Text>
          <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
            {lastDrill?.reason || 'Run a formal drill to validate hard-block behavior at boundary.'}
          </Text>
          {lastDrill?.drill_at ? (
            <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>at {fmtRelative(lastDrill.drill_at)}</Text>
          ) : null}
        </View>

        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8 }} data-testid="gtec-c5-external-cert-card" testID="gtec-c5-external-cert-card">
          <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>External-host certification</Text>
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginTop: 2 }} data-testid="gtec-c5-external-cert-status" testID="gtec-c5-external-cert-status">
            {(externalCert?.status || 'NOT RUN').toUpperCase()}
          </Text>
          <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
            {externalCert?.reason || (externalCert?.white_screen?.gate_passed ? 'White-screen gate clean on external host' : 'Awaiting stable proxy or clean sentry run')}
          </Text>
          {externalCert?.finished_at ? (
            <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>last run {fmtRelative(externalCert.finished_at)}</Text>
          ) : null}
        </View>

        <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 8 }} data-testid="gtec-c5-matrix64-pipeline-card" testID="gtec-c5-matrix64-pipeline-card">
          <Text style={{ color: C.muted, fontSize: 9, fontWeight: '700' }}>Global Matrix64 nightly pipeline</Text>
          <Text
            style={{
              color:
                (releaseCert?.checks?.matrix64_pipeline?.status || matrix64Run?.status) === 'PASS'
                  ? C.success
                  : (releaseCert?.checks?.matrix64_pipeline?.status || matrix64Run?.status) === 'FAIL'
                    ? C.danger
                    : C.warning,
              fontSize: 11,
              fontWeight: '800',
              marginTop: 2,
            }}
            data-testid="gtec-c5-matrix64-status"
            testID="gtec-c5-matrix64-status"
          >
            {(releaseCert?.checks?.matrix64_pipeline?.status || matrix64Run?.status || 'UNKNOWN').toUpperCase()}
          </Text>
          <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }} data-testid="gtec-c5-matrix64-checks" testID="gtec-c5-matrix64-checks">
            {(releaseCert?.checks?.matrix64_pipeline?.total_checks ?? matrix64Run?.counts?.total_checks ?? 0)}/
            {(releaseCert?.checks?.matrix64_pipeline?.required_total_checks ?? matrix64Run?.dimensions?.required_total_checks ?? 64)} checks
          </Text>
          <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }} data-testid="gtec-c5-matrix64-failed" testID="gtec-c5-matrix64-failed">
            failed: {releaseCert?.checks?.matrix64_pipeline?.failed_checks ?? matrix64Run?.counts?.failed_checks ?? 0}
          </Text>
          <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }} data-testid="gtec-c5-matrix64-run-id" testID="gtec-c5-matrix64-run-id">
            run: {releaseCert?.checks?.matrix64_pipeline?.run_id || matrix64Run?.run_id || '—'}
          </Text>
          <Text style={{ color: C.muted, fontSize: 9, marginTop: 2 }} data-testid="gtec-c5-matrix64-updated" testID="gtec-c5-matrix64-updated">
            updated {fmtRelative(releaseCert?.checks?.matrix64_pipeline?.generated_at || matrix64Run?.generated_at)}
          </Text>
        </View>

        <TouchableOpacity
          data-testid="gtec-c5-run-go-no-go-drill-button"
          testID="gtec-c5-run-go-no-go-drill-button"
          onPress={runFormalDrill}
          disabled={drillBusy}
          style={{
            alignSelf: 'flex-start',
            borderRadius: 999,
            borderWidth: 1,
            borderColor: C.primary,
            backgroundColor: withAlpha(C.primary, '18'),
            paddingHorizontal: 12,
            paddingVertical: 8,
            opacity: drillBusy ? 0.6 : 1,
          }}
        >
          {drillBusy ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <ActivityIndicator size="small" color={C.primary} />
              <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800' }}>Running drill…</Text>
            </View>
          ) : (
            <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800' }}>Run formal GO/NO-GO drill (simulated hard-block)</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          data-testid="gtec-c5-rerun-external-cert-button"
          testID="gtec-c5-rerun-external-cert-button"
          onPress={rerunExternalCertification}
          disabled={externalCertBusy}
          style={{
            alignSelf: 'flex-start',
            borderRadius: 999,
            borderWidth: 1,
            borderColor: C.accent,
            backgroundColor: withAlpha(C.accent, '16'),
            paddingHorizontal: 12,
            paddingVertical: 8,
            opacity: externalCertBusy ? 0.6 : 1,
          }}
        >
          {externalCertBusy ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <ActivityIndicator size="small" color={C.accent} />
              <Text style={{ color: C.accent, fontSize: 11, fontWeight: '800' }}>Running external certification…</Text>
            </View>
          ) : (
            <Text style={{ color: C.accent, fontSize: 11, fontWeight: '800' }}>Re-run external-host certification</Text>
          )}
        </TouchableOpacity>
      </View>

      {err ? (
        <Text style={{ color: C.danger, fontSize: 11, marginBottom: 10 }}
              data-testid="gtec-v2-error" testID="gtec-v2-error">{err}</Text>
      ) : null}

      {/* ── Latest report card ── */}
      {latest ? (
        <View
          data-testid="gtec-v2-latest-card"
          testID="gtec-v2-latest-card"
          style={{
            borderRadius: 14, borderWidth: 1, borderColor: withAlpha(statusColor, '55'),
            backgroundColor: withAlpha(statusColor, '0E'), padding: 14, marginBottom: 14,
          }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <View style={{
              paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999,
              backgroundColor: withAlpha(statusColor, '22'), borderWidth: 1, borderColor: withAlpha(statusColor, '44'),
            }}>
              <Text style={{ color: statusColor, fontSize: 11, fontWeight: '900', letterSpacing: 0.5 }}
                    data-testid="gtec-v2-status-pill" testID="gtec-v2-status-pill">
                STATUS: {overallStatus || '—'}
              </Text>
            </View>
            <Text style={{ color: C.muted, fontSize: 10 }}>
              {latest.triggered_by || 'manual'} · {fmtRelative(latest.generated_at)}
              {latest.elapsed_ms ? ` · ${Math.round(latest.elapsed_ms / 1000)}s` : ''}
            </Text>
          </View>

          <View style={{ marginTop: 10, gap: 4 }}>
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '800', letterSpacing: 0.4 }}>{tx('admin.gtecScanV2Panel.auto.text.011', 'TASK_ID')}</Text>
            <Text style={{ color: C.text, fontSize: 11, fontFamily: 'monospace' }}
                  data-testid="gtec-v2-task-id" testID="gtec-v2-task-id">
              {latest.task_id || '—'}
            </Text>
            <Text style={{ color: C.muted, fontSize: 9, fontWeight: '800', letterSpacing: 0.4, marginTop: 6 }}>{tx('admin.gtecScanV2Panel.auto.text.012', 'EXECUTION_HASH')}</Text>
            <Text style={{ color: C.text, fontSize: 11, fontFamily: 'monospace' }}
                  data-testid="gtec-v2-execution-hash" testID="gtec-v2-execution-hash">
              {latest.execution_hash || '—'}
            </Text>
          </View>

          {/* Severity counters */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
            <Sev label="CRITICAL" value={latest.critical_vulns ?? 0} color={C.danger} C={C}
                 testId="gtec-v2-sev-critical" />
            <Sev label="HIGH" value={latest.high_vulns ?? 0}
                 color={(latest.high_vulns ?? 0) > 0 ? C.warning : C.success} C={C}
                 testId="gtec-v2-sev-high" />
            <Sev label="MED" value={latest.medium_vulns ?? latest.severity_counts?.medium ?? 0} color={C.muted} C={C}
                 testId="gtec-v2-sev-medium" />
            <Sev label="LOW" value={latest.low_vulns ?? latest.severity_counts?.low ?? 0} color={C.muted} C={C}
                 testId="gtec-v2-sev-low" />
            <Sev label="REGRESSIONS" value={latest.regressions === 'YES' ? 1 : 0}
                 color={latest.regressions === 'YES' ? C.danger : C.success} C={C}
                 testId="gtec-v2-sev-regressions" />
          </View>

          {/* Pillars */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            <Pillar label="SECURITY"        value={latest.security_scan} C={C} testId="gtec-v2-pillar-security" />
            <Pillar label="E2E TESTS"       value={latest.e2e_tests} C={C} testId="gtec-v2-pillar-e2e" />
            <Pillar label="RESPONSIVENESS"  value={latest.responsiveness} C={C} testId="gtec-v2-pillar-resp" />
            <Pillar label="PERFORMANCE"     value={latest.performance} C={C} testId="gtec-v2-pillar-perf" />
            <Pillar label="RBAC"            value={latest.rbac_status} C={C} testId="gtec-v2-pillar-rbac" />
            <Pillar label="SUBSCRIPTION"    value={latest.subscription_enforcement} C={C} testId="gtec-v2-pillar-sub" />
          </View>

          {/* GTEC SCAN v3 §13 — additive output (does NOT replace v2 §12) */}
          {latest.v3_output ? (
            <View
              style={{
                marginTop: 12, borderRadius: 12, borderWidth: 1, borderColor: C.border,
                backgroundColor: C.cardAlt, padding: 12,
              }}
              data-testid="gtec-v3-output" testID="gtec-v3-output"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <Text style={{ color: C.muted, fontSize: 9, fontWeight: '800', letterSpacing: 0.4 }}>{tx('admin.gtecScanV2Panel.auto.text.013', '§13 v3 FINAL OUTPUT — GTEC SCAN v3 UPGRADE (ADDITIVE)')}</Text>
              </View>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                <Pillar label="SYSTEM"      value={latest.v3_output.SYSTEM_STATUS}     C={C} testId="gtec-v3-system" />
                <Pillar label="SECURITY"    value={latest.v3_output.SECURITY_STATUS}   C={C} testId="gtec-v3-security" />
                <Pillar label="PERFORMANCE" value={latest.v3_output.PERFORMANCE_STATUS} C={C} testId="gtec-v3-performance" />
                <Pillar label="I18N"        value={latest.v3_output.I18N_STATUS}       C={C} testId="gtec-v3-i18n" />
                <Pillar label="RBAC"        value={latest.v3_output.RBAC_STATUS}       C={C} testId="gtec-v3-rbac" />
                <Pillar label="REGRESSION"  value={latest.v3_output.REGRESSION_STATUS} C={C} testId="gtec-v3-regression" />
              </View>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 10 }}>
                <Text style={{ color: C.muted, fontSize: 10, fontFamily: 'monospace' }}
                      data-testid="gtec-v3-error-count" testID="gtec-v3-error-count">
                  ERROR_COUNT: <Text style={{ color: C.text, fontWeight: '800' }}>{String(latest.v3_output.ERROR_COUNT ?? 0)}</Text>
                </Text>
                <Text style={{ color: C.muted, fontSize: 10, fontFamily: 'monospace' }}
                      data-testid="gtec-v3-active-fixes" testID="gtec-v3-active-fixes">
                  ACTIVE_FIXES: <Text style={{ color: C.text, fontWeight: '800' }}>{latest.v3_output.ACTIVE_FIXES || '—'}</Text>
                </Text>
                <Text style={{ color: C.muted, fontSize: 10, fontFamily: 'monospace' }}
                      data-testid="gtec-v3-monitoring" testID="gtec-v3-monitoring">
                  MONITORING: <Text style={{ color: latest.v3_output.MONITORING === 'ACTIVE' ? C.success : C.danger, fontWeight: '800' }}>
                    {latest.v3_output.MONITORING || '—'}
                  </Text>
                </Text>
                <Text style={{ color: C.muted, fontSize: 10, fontFamily: 'monospace' }}
                      data-testid="gtec-v3-learning-memory" testID="gtec-v3-learning-memory">
                  LEARNING_MEMORY: <Text style={{ color: C.text, fontWeight: '800' }}>{latest.v3_output.LEARNING_MEMORY || '—'}</Text>
                </Text>
                <Text style={{ color: C.muted, fontSize: 10, fontFamily: 'monospace' }}
                      data-testid="gtec-v3-confidence" testID="gtec-v3-confidence">
                  CONFIDENCE_LEVEL: <Text style={{
                      color: latest.v3_output.CONFIDENCE_LEVEL === 'HIGH' ? C.success
                           : latest.v3_output.CONFIDENCE_LEVEL === 'LOW' ? C.danger
                           : C.warning,
                      fontWeight: '800',
                    }}>
                    {latest.v3_output.CONFIDENCE_LEVEL || '—'}
                  </Text>
                </Text>
              </View>
            </View>
          ) : null}

          {latest.summary ? (
            <Text
              style={{ color: C.textSec, fontSize: 11, marginTop: 12, lineHeight: 16 }}
              data-testid="gtec-v2-summary" testID="gtec-v2-summary"
            >
              {latest.summary}
            </Text>
          ) : null}
        </View>
      ) : (
        <View
          style={{
            borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardAlt,
            padding: 12, marginBottom: 14, alignItems: 'center',
          }}
          data-testid="gtec-v2-no-report" testID="gtec-v2-no-report"
        >
          <Text style={{ color: C.muted, fontSize: 11 }}>{tx('admin.gtecScanV2Panel.auto.text.014', 'No C5 scan yet. Autonomous scheduler will run it automatically when due.')}</Text>
        </View>
      )}

      {/* History */}
      {history.length > 0 ? (
        <View data-testid="gtec-v2-history" testID="gtec-v2-history">
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginBottom: 6 }}>{tx('admin.gtecScanV2Panel.auto.text.015', 'Recent C5 scans')}</Text>
          {history.slice(0, 5).map((h, idx) => {
            const tone = h.status === 'PASS' ? C.success : h.status === 'FAIL' ? C.danger : C.muted;
            return (
              <View
                key={h.task_id || idx}
                data-testid={`gtec-v2-history-${idx}`} testID={`gtec-v2-history-${idx}`}
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 8,
                  paddingHorizontal: 10, paddingVertical: 7, borderWidth: 1, borderColor: C.border,
                  borderRadius: 10, backgroundColor: C.cardAlt, marginTop: idx ? 5 : 0,
                }}>
                <View style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: tone }} />
                <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>{h.triggered_by || 'manual'}</Text>
                <Text style={{ color: C.muted, fontSize: 10 }} numberOfLines={1}>
                  crit={h.critical_vulns ?? 0} · high={h.high_vulns ?? 0} · med={h.medium_vulns ?? h.severity_counts?.medium ?? 0} · low={h.low_vulns ?? h.severity_counts?.low ?? 0}
                </Text>
                <Text style={{ color: tone, fontSize: 10, fontWeight: '800', marginLeft: 'auto' as any }}>
                  {h.status}
                </Text>
                <Text style={{ color: C.muted, fontSize: 10 }}>{fmtRelative(h.generated_at)}</Text>
              </View>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

function Sev({ label, value, color, C, testId }:
  { label: string; value: number; color: string; C: any; testId: string }) {
  return (
    <View
      data-testid={testId} testID={testId}
      style={{
        borderRadius: 10, borderWidth: 1, borderColor: withAlpha(color, '3A'),
        backgroundColor: withAlpha(color, '14'), paddingHorizontal: 10, paddingVertical: 7, minWidth: 82,
      }}>
      <Text style={{ color, fontSize: 9, fontWeight: '900', letterSpacing: 0.5 }}>{label}</Text>
      <Text style={{ color, fontSize: 16, fontWeight: '900', marginTop: 3 }}
            data-testid={`${testId}-value`} testID={`${testId}-value`}>
        {value}
      </Text>
    </View>
  );
}

function Pillar({ label, value, C, testId }:
  { label: string; value?: 'PASS' | 'FAIL'; C: any; testId: string }) {
  const tone = value === 'PASS' ? C.success : value === 'FAIL' ? C.danger : C.muted;
  return (
    <View
      data-testid={testId} testID={testId}
      style={{
        paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999,
        borderWidth: 1, borderColor: withAlpha(tone, '3A'), backgroundColor: withAlpha(tone, '12'),
        flexDirection: 'row', alignItems: 'center', gap: 6,
      }}>
      <View style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: tone }} />
      <Text style={{ color: tone, fontSize: 9, fontWeight: '800', letterSpacing: 0.4 }}>
        {label} · {value || '—'}
      </Text>
    </View>
  );
}
