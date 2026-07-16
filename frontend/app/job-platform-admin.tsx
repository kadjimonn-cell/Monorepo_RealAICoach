import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, Text, TextInput, View, TouchableOpacity } from 'react-native';
import AppShell from '../src/components/AppShell';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { useAuth } from '../src/context/AuthContext';
import api from '../src/services/api';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import { hasAdminConsoleVisibility } from '../src/utils/adminAccess';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

type WorkflowEvent = {
  event_id: string;
  event_type: string;
  user_id: string;
  path?: string;
  created_at?: string;
};

type DeprecationTelemetry = {
  total_events: number;
  migration_progress_pct: number;
  active_legacy_users: number;
  remaining_legacy_operations: string[];
  top_operations: { operation: string; count: number }[];
};

type CanaryControls = {
  canary_enabled: boolean;
  legacy_allow_pct: number;
  auto_rollback_enabled: boolean;
  rollback_window_hours: number;
  rollback_legacy_event_threshold: number;
  legacy_retirement_enabled?: boolean;
  retirement_phase?: string;
  retired_legacy_route_families?: string[];
  retirement_gate_lookback_hours?: number;
  retirement_gate_max_events?: number;
  retirement_gate_max_active_users?: number;
  retirement_force_apply?: boolean;
  retirement_override_user_ids?: string[];
};

type PremiumCohort = {
  repeat_rate_pct: number;
  churn_signal_pct: number;
  activation_users: number;
  repeat_users: number;
  total_events: number;
};

type EmployerFunnel = {
  generated_at: string;
  lookback_days: number;
  funnel: {
    trial_started: number;
    approved_employer: number;
    first_hire: number;
  };
  conversion_rates_pct: {
    trial_to_approved: number;
    approved_to_first_hire: number;
    trial_to_first_hire: number;
  };
  dropoff: {
    trial_to_approved: number;
    approved_to_first_hire: number;
  };
  insights: string[];
};

type CanarySimulatorResponse = {
  summary?: {
    projected_allowed_events?: number;
    projected_blocked_events?: number;
    projected_blocked_pct?: number;
    projected_impacted_users?: number;
    would_trigger_auto_rollback?: boolean;
    rollback_risk_level?: string;
    recommendation?: string;
  };
  operations?: {
    operation: string;
    projected_blocked_events: number;
    projected_blocked_pct: number;
    v2_endpoint?: string;
  }[];
};

type RetirementFamilyReadiness = {
  route_family: string;
  total_events: number;
  active_users: number;
  gate_met: boolean;
  readiness_score: number;
};

type RetirementReadinessResponse = {
  retirement_phase?: string;
  target_route_families?: string[];
  target_phase_gate_ready?: boolean;
  recommended_phase?: string;
  family_readiness?: RetirementFamilyReadiness[];
};

type LegacyRemovalFamilyWindow = {
  route_family: string;
  total_events: number;
  active_users: number;
  gate_met: boolean;
  readiness_score: number;
};

type LegacyRemovalWindow = {
  window_label: string;
  lookback_hours: number;
  gate_met: boolean;
  family_readiness: LegacyRemovalFamilyWindow[];
};

type LegacyRemovalReadinessResponse = {
  sustained_gate_met?: boolean;
  ready_for_legacy_code_removal?: boolean;
  recommended_action?: string;
  mode?: string;
  exclude_synthetic?: boolean;
  windows?: LegacyRemovalWindow[];
};

export default function JobPlatformAdminRoute() {
  const { user } = useAuth();
  const { colors } = useTheme();
  const { tx } = useTranslation();
  const isAdmin = hasAdminConsoleVisibility(user as any);
  const copy = useCallback((key: string, fallback: string) => {
    const value = tx(key, fallback);
    return value === key ? fallback : value;
  }, [tx]);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [deprecation, setDeprecation] = useState<DeprecationTelemetry | null>(null);
  const [canary, setCanary] = useState<CanaryControls | null>(null);
  const [premiumCohort, setPremiumCohort] = useState<PremiumCohort | null>(null);
  const [employerFunnel, setEmployerFunnel] = useState<EmployerFunnel | null>(null);
  const [simAllowPct, setSimAllowPct] = useState('65');
  const [simWindowHours, setSimWindowHours] = useState('72');
  const [simThreshold, setSimThreshold] = useState('500');
  const [simOperations, setSimOperations] = useState('candidate_save_job, employer_offer_build');
  const [simulator, setSimulator] = useState<CanarySimulatorResponse | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [retirementReadiness, setRetirementReadiness] = useState<RetirementReadinessResponse | null>(null);
  const [retirementEnabled, setRetirementEnabled] = useState(true);
  const [retirementPhase, setRetirementPhase] = useState('phase1_jobs_writes');
  const [retirementLookbackHours, setRetirementLookbackHours] = useState('72');
  const [retirementMaxEvents, setRetirementMaxEvents] = useState('20');
  const [retirementMaxActiveUsers, setRetirementMaxActiveUsers] = useState('10');
  const [retirementForceApply, setRetirementForceApply] = useState(false);
  const [retirementOverrideUsers, setRetirementOverrideUsers] = useState('');
  const [retirementLoading, setRetirementLoading] = useState(false);
  const [removalReadiness, setRemovalReadiness] = useState<LegacyRemovalReadinessResponse | null>(null);
  const [removalLoading, setRemovalLoading] = useState(false);
  const [removalMode, setRemovalMode] = useState<'strict_zero' | 'near_zero'>('strict_zero');
  const [removalExcludeSynthetic, setRemovalExcludeSynthetic] = useState(false);
  const [statusText, setStatusText] = useState('');

  useEffect(() => {
    if (!isAdmin) {
      setStatusText(copy('jobsPortal.admin.accessDenied', 'Administrator access is required for this workspace.'));
      setEvents([]);
      setDeprecation(null);
      setCanary(null);
      setPremiumCohort(null);
      setEmployerFunnel(null);
      setRetirementReadiness(null);
      setRemovalReadiness(null);
      return;
    }

    const run = async () => {
      try {
        const [res, depRes, canaryRes, cohortRes, funnelRes, retirementRes] = await Promise.all([
          api.get('/hiring/v2/admin/workflow-events?limit=12', { skipDedupe: true }),
          api.get('/hiring/v2/admin/deprecation-telemetry?lookback_days=14&limit=1000', { skipDedupe: true }),
          api.get('/hiring/v2/admin/canary-controls', { skipDedupe: true }),
          api.get('/hiring/v2/admin/premium-conversion-cohorts?lookback_days=30', { skipDedupe: true }),
          api.get('/hiring/v2/admin/employer-conversion-funnel?lookback_days=30', { skipDedupe: true }),
          api.get('/hiring/v2/admin/legacy-retirement-readiness?lookback_hours=72', { skipDedupe: true }),
        ]);
        setEvents(res?.data?.events || []);
        setDeprecation(depRes?.data || null);
        const canaryControls = canaryRes?.data?.controls || null;
        setCanary(canaryControls);
        setPremiumCohort(cohortRes?.data || null);
        setEmployerFunnel(funnelRes?.data || null);
        setRetirementReadiness(retirementRes?.data || null);
        const removalRes = await api.get('/hiring/v2/admin/legacy-removal-readiness?mode=strict_zero&exclude_synthetic=false', { skipDedupe: true });
        setRemovalReadiness(removalRes?.data || null);
        if (canaryControls) {
          setRetirementEnabled(Boolean(canaryControls.legacy_retirement_enabled));
          setRetirementPhase(String(canaryControls.retirement_phase || 'observe'));
          setRetirementLookbackHours(String(canaryControls.retirement_gate_lookback_hours ?? 72));
          setRetirementMaxEvents(String(canaryControls.retirement_gate_max_events ?? 20));
          setRetirementMaxActiveUsers(String(canaryControls.retirement_gate_max_active_users ?? 10));
          setRetirementForceApply(Boolean(canaryControls.retirement_force_apply));
          setRetirementOverrideUsers((canaryControls.retirement_override_user_ids || []).join(', '));
        }
        setStatusText(`Loaded ${res?.data?.total ?? 0} workflow events • migration progress ${depRes?.data?.migration_progress_pct ?? 0}%`);
      } catch (error) {
        handleAppRecoverableError({
          scope: 'job-platform-admin.workflow-events',
          error,
          message: copy('jobsPortal.admin.eventsLoadFailed', 'Failed to load workflow events.'),
          setError: setStatusText,
          notifyMode: 'silent',
        });
      }
    };
    void run();
  }, [isAdmin, copy]);

  const runCanarySimulation = async () => {
    setSimLoading(true);
    try {
      const operations = simOperations.split(',').map((item) => item.trim()).filter(Boolean);
      const result = await api.post('/hiring/v2/admin/canary-simulator', {
        canary_enabled: true,
        legacy_allow_pct: Number(simAllowPct || 65),
        lookback_hours: Number(simWindowHours || 72),
        rollback_window_hours: Number(simWindowHours || 72),
        rollback_legacy_event_threshold: Number(simThreshold || 500),
        operations,
      });
      setSimulator(result?.data || null);
      setStatusText(copy('jobsPortal.admin.simulatorRan', 'Canary simulation generated successfully.'));
    } catch (error) {
      handleAppRecoverableError({
        scope: 'job-platform-admin.canary-simulator',
        error,
        message: copy('jobsPortal.admin.simulatorFailed', 'Unable to run canary simulation right now.'),
        setError: setStatusText,
        notifyMode: 'silent',
      });
    } finally {
      setSimLoading(false);
    }
  };

  const loadRetirementReadiness = async () => {
    setRetirementLoading(true);
    try {
      const result = await api.get(`/hiring/v2/admin/legacy-retirement-readiness?lookback_hours=${Number(retirementLookbackHours || 72)}`, { skipDedupe: true });
      setRetirementReadiness(result?.data || null);
      setStatusText(copy('jobsPortal.admin.retirementReadinessLoaded', 'Legacy retirement readiness updated.'));
    } catch (error) {
      handleAppRecoverableError({
        scope: 'job-platform-admin.retirement-readiness',
        error,
        message: copy('jobsPortal.admin.retirementReadinessFailed', 'Unable to load retirement readiness right now.'),
        setError: setStatusText,
        notifyMode: 'silent',
      });
    } finally {
      setRetirementLoading(false);
    }
  };

  const applyRetirementControls = async () => {
    setRetirementLoading(true);
    try {
      const overrideIds = retirementOverrideUsers.split(',').map((item) => item.trim()).filter(Boolean);
      const payload = {
        legacy_retirement_enabled: retirementEnabled,
        retirement_phase: retirementPhase,
        retirement_gate_lookback_hours: Number(retirementLookbackHours || 72),
        retirement_gate_max_events: Number(retirementMaxEvents || 20),
        retirement_gate_max_active_users: Number(retirementMaxActiveUsers || 10),
        retirement_force_apply: retirementForceApply,
        retirement_override_user_ids: overrideIds,
      };
      const result = await api.post('/hiring/v2/admin/legacy-retirement-controls', payload);
      setCanary(result?.data?.controls || null);
      setRetirementReadiness({
        retirement_phase: result?.data?.controls?.retirement_phase,
        target_route_families: result?.data?.controls?.retired_legacy_route_families || [],
        target_phase_gate_ready: true,
        family_readiness: result?.data?.family_readiness || [],
      });
      setStatusText(copy('jobsPortal.admin.retirementControlsApplied', 'Legacy retirement controls updated successfully.'));
    } catch (error: any) {
      const apiMessage = error?.response?.data?.detail?.message;
      handleAppRecoverableError({
        scope: 'job-platform-admin.retirement-controls',
        error,
        message: apiMessage || copy('jobsPortal.admin.retirementControlsFailed', 'Unable to apply retirement controls right now.'),
        setError: setStatusText,
        notifyMode: 'silent',
      });
    } finally {
      setRetirementLoading(false);
    }
  };

  const loadRemovalReadiness = async () => {
    setRemovalLoading(true);
    try {
      const result = await api.get(
        `/hiring/v2/admin/legacy-removal-readiness?mode=${removalMode}&exclude_synthetic=${removalExcludeSynthetic}`,
        { skipDedupe: true },
      );
      setRemovalReadiness(result?.data || null);
      setStatusText(copy('jobsPortal.admin.removalReadinessLoaded', 'Legacy code removal readiness refreshed.'));
    } catch (error) {
      handleAppRecoverableError({
        scope: 'job-platform-admin.legacy-removal-readiness',
        error,
        message: copy('jobsPortal.admin.removalReadinessFailed', 'Unable to evaluate legacy code removal readiness right now.'),
        setError: setStatusText,
        notifyMode: 'silent',
      });
    } finally {
      setRemovalLoading(false);
    }
  };

  return (
    <AdminRouteGate returnTo="/job-platform-admin">
    <AppShell>
      <View style={{ flex: 1, backgroundColor: colors.bg }} data-testid="job-platform-admin-route" testID="job-platform-admin-route">
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 36 }}>
          <View style={{ maxWidth: 1240, width: '100%', alignSelf: 'center', gap: 12 }}>
            <View style={{ borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 14 }}>
              <Text style={{ color: colors.text, fontSize: 22, fontWeight: '900' }} data-testid="job-platform-admin-title" testID="job-platform-admin-title">{copy('jobsPortal.admin.workspaceTitle', 'Admin Hiring Command Center')}</Text>
              <Text style={{ color: colors.textMuted, marginTop: 6, fontSize: 12 }}>{copy('jobsPortal.admin.workspaceSubtitle', 'Dedicated Feature 26 module for observability, event audit, and operations oversight.')}</Text>
              {!!statusText && <Text style={{ color: colors.primary, marginTop: 8, fontSize: 12 }} data-testid="job-platform-admin-status" testID="job-platform-admin-status">{statusText}</Text>}
              <TouchableOpacity
                onPress={() => router.push('/admin/talent-network' as any)}
                style={{
                  marginTop: 10,
                  alignSelf: 'flex-start',
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: colors.primary,
                  backgroundColor: `${colors.primary}14`,
                  paddingHorizontal: 12,
                  paddingVertical: 7,
                }}
                data-testid="job-platform-admin-talent-network-ops-deeplink"
                testID="job-platform-admin-talent-network-ops-deeplink"
              >
                <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>
                  Open Talent Network Ops tab
                </Text>
              </TouchableOpacity>
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-admin-events" testID="job-platform-admin-events">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{copy('jobsPortal.admin.latestWorkflowEventsTitle', 'Latest workflow events')}</Text>
              <View style={{ marginTop: 8, gap: 6 }}>
                {events.map((event, idx) => (
                  <View key={`${event.event_id}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid={`job-platform-admin-event-${idx}`} testID={`job-platform-admin-event-${idx}`}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{event.event_type}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{event.user_id} • {event.path || '-'}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{event.created_at || '-'}</Text>
                  </View>
                ))}
                {events.length === 0 && (
                  <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="job-platform-admin-events-empty" testID="job-platform-admin-events-empty">{copy('jobsPortal.admin.noWorkflowEvents', 'No workflow events found in current window.')}</Text>
                )}
              </View>
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-admin-deprecation-panel" testID="job-platform-admin-deprecation-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{copy('jobsPortal.admin.deprecationTitle', 'Legacy → v2 migration telemetry')}</Text>
              {deprecation ? (
                <View style={{ marginTop: 8, gap: 6 }}>
                  <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="job-platform-admin-deprecation-progress" testID="job-platform-admin-deprecation-progress">
                    Migration progress: {deprecation.migration_progress_pct}%
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="job-platform-admin-deprecation-events" testID="job-platform-admin-deprecation-events">
                    Legacy write events: {deprecation.total_events} • Active users: {deprecation.active_legacy_users}
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{copy('jobsPortal.admin.topRemainingOperations', 'Top remaining operations')}</Text>
                  {deprecation.top_operations.slice(0, 6).map((row, idx) => (
                    <Text key={`${row.operation}-${idx}`} style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`job-platform-admin-deprecation-op-${idx}`} testID={`job-platform-admin-deprecation-op-${idx}`}>
                      {row.operation}: {row.count}
                    </Text>
                  ))}
                </View>
              ) : (
                <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }} data-testid="job-platform-admin-deprecation-empty" testID="job-platform-admin-deprecation-empty">{copy('jobsPortal.admin.noDeprecationTelemetry', 'No deprecation telemetry available.')}</Text>
              )}
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-admin-canary-panel" testID="job-platform-admin-canary-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{copy('jobsPortal.admin.canaryTitle', 'Canary rollout + rollback controls')}</Text>
              {canary ? (
                <View style={{ marginTop: 8, gap: 4 }}>
                  <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="job-platform-admin-canary-status" testID="job-platform-admin-canary-status">
                    Canary: {canary.canary_enabled ? 'Enabled' : 'Disabled'} • Legacy Allow %: {canary.legacy_allow_pct}
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 12 }}>
                    Auto rollback: {canary.auto_rollback_enabled ? 'On' : 'Off'} • Window: {canary.rollback_window_hours}h • Threshold: {canary.rollback_legacy_event_threshold}
                  </Text>
                </View>
              ) : (
                <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{copy('jobsPortal.admin.canaryUnavailable', 'Canary controls unavailable.')}</Text>
              )}
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-admin-canary-simulator-panel" testID="job-platform-admin-canary-simulator-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="job-platform-admin-canary-simulator-title" testID="job-platform-admin-canary-simulator-title">
                {copy('jobsPortal.admin.canarySimulatorTitle', 'Canary Policy Simulator')}
              </Text>
              <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 12 }}>
                {copy('jobsPortal.admin.canarySimulatorSubtitle', 'Preview blocked legacy operations, impacted users, and rollback risk before applying stricter policy.')}
              </Text>

              <View style={{ marginTop: 10, gap: 8 }}>
                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Legacy Allow %</Text>
                  <TextInput
                    value={simAllowPct}
                    onChangeText={setSimAllowPct}
                    keyboardType="numeric"
                    placeholder="65"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-simulator-allow-pct-input"
                    testID="job-platform-admin-simulator-allow-pct-input"
                  />
                </View>

                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Lookback/Window Hours</Text>
                  <TextInput
                    value={simWindowHours}
                    onChangeText={setSimWindowHours}
                    keyboardType="numeric"
                    placeholder="72"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-simulator-window-hours-input"
                    testID="job-platform-admin-simulator-window-hours-input"
                  />
                </View>

                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Rollback Threshold</Text>
                  <TextInput
                    value={simThreshold}
                    onChangeText={setSimThreshold}
                    keyboardType="numeric"
                    placeholder="500"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-simulator-threshold-input"
                    testID="job-platform-admin-simulator-threshold-input"
                  />
                </View>

                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Operation Scope (comma-separated)</Text>
                  <TextInput
                    value={simOperations}
                    onChangeText={setSimOperations}
                    placeholder="candidate_save_job, employer_offer_build"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-simulator-operations-input"
                    testID="job-platform-admin-simulator-operations-input"
                  />
                </View>

                <TouchableOpacity
                  onPress={runCanarySimulation}
                  disabled={simLoading}
                  style={{ backgroundColor: colors.primary, paddingVertical: 10, borderRadius: 10, alignItems: 'center', opacity: simLoading ? 0.7 : 1 }}
                  data-testid="job-platform-admin-simulator-run-button"
                  testID="job-platform-admin-simulator-run-button"
                >
                  <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>
                    {simLoading ? copy('jobsPortal.admin.simulatorRunning', 'Running Simulation...') : copy('jobsPortal.admin.simulatorRun', 'Run Canary Simulation')}
                  </Text>
                </TouchableOpacity>
              </View>

              {simulator?.summary && (
                <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid="job-platform-admin-simulator-results" testID="job-platform-admin-simulator-results">
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} data-testid="job-platform-admin-simulator-risk-level" testID="job-platform-admin-simulator-risk-level">
                    Risk: {(simulator.summary.rollback_risk_level || 'low').toUpperCase()} • Blocked: {simulator.summary.projected_blocked_events ?? 0} ({simulator.summary.projected_blocked_pct ?? 0}%)
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4 }} data-testid="job-platform-admin-simulator-impact" testID="job-platform-admin-simulator-impact">
                    Allowed: {simulator.summary.projected_allowed_events ?? 0} • Impacted users: {simulator.summary.projected_impacted_users ?? 0} • Auto-rollback trigger: {simulator.summary.would_trigger_auto_rollback ? 'Likely' : 'Not likely'}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 6 }} data-testid="job-platform-admin-simulator-recommendation" testID="job-platform-admin-simulator-recommendation">
                    {simulator.summary.recommendation || 'No recommendation available.'}
                  </Text>

                  <View style={{ marginTop: 8, gap: 4 }}>
                    {(simulator.operations || []).slice(0, 5).map((op, idx) => (
                      <Text key={`${op.operation}-${idx}`} style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`job-platform-admin-simulator-op-${idx}`} testID={`job-platform-admin-simulator-op-${idx}`}>
                        {op.operation}: {op.projected_blocked_events} blocked ({op.projected_blocked_pct}%)
                      </Text>
                    ))}
                  </View>
                </View>
              )}
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-admin-retirement-panel" testID="job-platform-admin-retirement-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="job-platform-admin-retirement-title" testID="job-platform-admin-retirement-title">
                {copy('jobsPortal.admin.retirementTitle', 'P2 Legacy v1 Retirement Gates')}
              </Text>
              <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 12 }}>
                {copy('jobsPortal.admin.retirementSubtitle', 'Phase out /api/jobs and /api/employers writes only when telemetry gates are satisfied.')}
              </Text>

              <View style={{ marginTop: 10, gap: 8 }}>
                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Retirement Phase</Text>
                  <TextInput
                    value={retirementPhase}
                    onChangeText={setRetirementPhase}
                    placeholder="observe | phase1_jobs_writes | phase2_jobs_employers_writes"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-retirement-phase-input"
                    testID="job-platform-admin-retirement-phase-input"
                  />
                </View>

                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Gate Lookback Hours</Text>
                  <TextInput
                    value={retirementLookbackHours}
                    onChangeText={setRetirementLookbackHours}
                    keyboardType="numeric"
                    placeholder="72"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-retirement-lookback-input"
                    testID="job-platform-admin-retirement-lookback-input"
                  />
                </View>

                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Max Legacy Events</Text>
                  <TextInput
                    value={retirementMaxEvents}
                    onChangeText={setRetirementMaxEvents}
                    keyboardType="numeric"
                    placeholder="20"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-retirement-max-events-input"
                    testID="job-platform-admin-retirement-max-events-input"
                  />
                </View>

                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Max Active Legacy Users</Text>
                  <TextInput
                    value={retirementMaxActiveUsers}
                    onChangeText={setRetirementMaxActiveUsers}
                    keyboardType="numeric"
                    placeholder="10"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-retirement-max-users-input"
                    testID="job-platform-admin-retirement-max-users-input"
                  />
                </View>

                <View>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginBottom: 4 }}>Retirement Override Users (comma-separated)</Text>
                  <TextInput
                    value={retirementOverrideUsers}
                    onChangeText={setRetirementOverrideUsers}
                    placeholder="admin_user_id_1, admin_user_id_2"
                    placeholderTextColor={colors.textMuted}
                    style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, color: colors.text, paddingHorizontal: 10, paddingVertical: 8 }}
                    data-testid="job-platform-admin-retirement-overrides-input"
                    testID="job-platform-admin-retirement-overrides-input"
                  />
                </View>

                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TouchableOpacity
                    onPress={() => setRetirementEnabled((prev) => !prev)}
                    style={{ flex: 1, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingVertical: 10, borderRadius: 10, alignItems: 'center' }}
                    data-testid="job-platform-admin-retirement-enable-toggle"
                    testID="job-platform-admin-retirement-enable-toggle"
                  >
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>
                      Retirement: {retirementEnabled ? 'Enabled' : 'Disabled'}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => setRetirementForceApply((prev) => !prev)}
                    style={{ flex: 1, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingVertical: 10, borderRadius: 10, alignItems: 'center' }}
                    data-testid="job-platform-admin-retirement-force-toggle"
                    testID="job-platform-admin-retirement-force-toggle"
                  >
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>
                      Force Apply: {retirementForceApply ? 'On' : 'Off'}
                    </Text>
                  </TouchableOpacity>
                </View>

                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TouchableOpacity
                    onPress={loadRetirementReadiness}
                    disabled={retirementLoading}
                    style={{ flex: 1, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingVertical: 10, borderRadius: 10, alignItems: 'center', opacity: retirementLoading ? 0.7 : 1 }}
                    data-testid="job-platform-admin-retirement-readiness-button"
                    testID="job-platform-admin-retirement-readiness-button"
                  >
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>
                      {retirementLoading ? 'Loading...' : 'Evaluate Readiness'}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    onPress={applyRetirementControls}
                    disabled={retirementLoading}
                    style={{ flex: 1, backgroundColor: colors.primary, paddingVertical: 10, borderRadius: 10, alignItems: 'center', opacity: retirementLoading ? 0.7 : 1 }}
                    data-testid="job-platform-admin-retirement-apply-button"
                    testID="job-platform-admin-retirement-apply-button"
                  >
                    <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>
                      {retirementLoading ? 'Applying...' : 'Apply Retirement Phase'}
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>

              {retirementReadiness && (
                <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid="job-platform-admin-retirement-readiness" testID="job-platform-admin-retirement-readiness">
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} data-testid="job-platform-admin-retirement-phase-status" testID="job-platform-admin-retirement-phase-status">
                    Phase: {retirementReadiness.retirement_phase || 'observe'} • Gate Ready: {retirementReadiness.target_phase_gate_ready ? 'Yes' : 'No'}
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4 }} data-testid="job-platform-admin-retirement-recommended-phase" testID="job-platform-admin-retirement-recommended-phase">
                    Recommended next phase: {retirementReadiness.recommended_phase || 'observe'}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }} data-testid="job-platform-admin-retirement-target-families" testID="job-platform-admin-retirement-target-families">
                    Target route families: {(retirementReadiness.target_route_families || []).join(', ') || 'none'}
                  </Text>
                  <View style={{ marginTop: 8, gap: 4 }}>
                    {(retirementReadiness.family_readiness || []).map((row, idx) => (
                      <Text key={`${row.route_family}-${idx}`} style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`job-platform-admin-retirement-family-${idx}`} testID={`job-platform-admin-retirement-family-${idx}`}>
                        {row.route_family}: events={row.total_events}, users={row.active_users}, readiness={row.readiness_score}, gate={row.gate_met ? 'met' : 'open'}
                      </Text>
                    ))}
                  </View>
                </View>
              )}
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-admin-premium-cohort-panel" testID="job-platform-admin-premium-cohort-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }}>{copy('jobsPortal.admin.premiumCohortsTitle', 'Premium conversion cohorts')}</Text>
              {premiumCohort ? (
                <View style={{ marginTop: 8, gap: 4 }}>
                  <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="job-platform-admin-premium-repeat-rate" testID="job-platform-admin-premium-repeat-rate">
                    Repeat rate: {premiumCohort.repeat_rate_pct}% • Churn signal: {premiumCohort.churn_signal_pct}%
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 12 }}>
                    Activation users: {premiumCohort.activation_users} • Repeat users: {premiumCohort.repeat_users} • Events: {premiumCohort.total_events}
                  </Text>
                </View>
              ) : (
                <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{copy('jobsPortal.admin.premiumCohortsUnavailable', 'Premium cohort data unavailable.')}</Text>
              )}
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-admin-employer-funnel-panel" testID="job-platform-admin-employer-funnel-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="job-platform-admin-employer-funnel-title" testID="job-platform-admin-employer-funnel-title">
                {copy('jobsPortal.admin.employerFunnelTitle', 'Employer conversion funnel')}
              </Text>
              <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 12 }}>
                {copy('jobsPortal.admin.employerFunnelSubtitle', 'Track trial → approved → first-hire conversion and identify drop-off stages.')}
              </Text>

              {employerFunnel ? (
                <View style={{ marginTop: 8, gap: 8 }}>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="job-platform-admin-funnel-trial-chip" testID="job-platform-admin-funnel-trial-chip">
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{copy('jobsPortal.admin.funnelTrial', 'Trial')}</Text>
                      <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }}>{employerFunnel.funnel.trial_started}</Text>
                    </View>
                    <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="job-platform-admin-funnel-approved-chip" testID="job-platform-admin-funnel-approved-chip">
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{copy('jobsPortal.admin.funnelApproved', 'Approved')}</Text>
                      <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }}>{employerFunnel.funnel.approved_employer}</Text>
                    </View>
                    <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="job-platform-admin-funnel-first-hire-chip" testID="job-platform-admin-funnel-first-hire-chip">
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{copy('jobsPortal.admin.funnelFirstHire', 'First Hire')}</Text>
                      <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }}>{employerFunnel.funnel.first_hire}</Text>
                    </View>
                  </View>

                  <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }}>
                    <Text style={{ color: colors.textSec, fontSize: 12 }} data-testid="job-platform-admin-funnel-rates" testID="job-platform-admin-funnel-rates">
                      Trial→Approved: {employerFunnel.conversion_rates_pct.trial_to_approved}% • Approved→First Hire: {employerFunnel.conversion_rates_pct.approved_to_first_hire}% • Trial→First Hire: {employerFunnel.conversion_rates_pct.trial_to_first_hire}%
                    </Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }} data-testid="job-platform-admin-funnel-dropoff" testID="job-platform-admin-funnel-dropoff">
                      Drop-off: Trial→Approved {employerFunnel.dropoff.trial_to_approved} • Approved→First Hire {employerFunnel.dropoff.approved_to_first_hire}
                    </Text>
                  </View>

                  <View style={{ gap: 4 }}>
                    {employerFunnel.insights.slice(0, 4).map((insight, idx) => (
                      <Text key={`funnel-insight-${idx}`} style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`job-platform-admin-funnel-insight-${idx}`} testID={`job-platform-admin-funnel-insight-${idx}`}>
                        • {insight}
                      </Text>
                    ))}
                  </View>
                </View>
              ) : (
                <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }} data-testid="job-platform-admin-employer-funnel-empty" testID="job-platform-admin-employer-funnel-empty">
                  {copy('jobsPortal.admin.employerFunnelUnavailable', 'Employer funnel data unavailable.')}
                </Text>
              )}
            </View>

            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid="job-platform-admin-removal-readiness-panel" testID="job-platform-admin-removal-readiness-panel">
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="job-platform-admin-removal-readiness-title" testID="job-platform-admin-removal-readiness-title">
                Legacy v1 Code Removal Readiness
              </Text>
              <Text style={{ color: colors.textMuted, marginTop: 4, fontSize: 12 }}>
                Sustained telemetry gate monitor for safe hard deletion of legacy write routes in /api/jobs and /api/employers.
              </Text>

              <View style={{ marginTop: 10, gap: 8 }}>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TouchableOpacity
                    onPress={() => setRemovalMode((prev) => (prev === 'strict_zero' ? 'near_zero' : 'strict_zero'))}
                    style={{ flex: 1, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingVertical: 10, borderRadius: 10, alignItems: 'center' }}
                    data-testid="job-platform-admin-removal-mode-toggle"
                    testID="job-platform-admin-removal-mode-toggle"
                  >
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>
                      Mode: {removalMode === 'strict_zero' ? 'Strict Zero' : 'Near Zero'}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    onPress={() => setRemovalExcludeSynthetic((prev) => !prev)}
                    style={{ flex: 1, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, paddingVertical: 10, borderRadius: 10, alignItems: 'center' }}
                    data-testid="job-platform-admin-removal-synthetic-toggle"
                    testID="job-platform-admin-removal-synthetic-toggle"
                  >
                    <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>
                      Exclude Synthetic: {removalExcludeSynthetic ? 'On' : 'Off'}
                    </Text>
                  </TouchableOpacity>
                </View>

                <TouchableOpacity
                  onPress={loadRemovalReadiness}
                  disabled={removalLoading}
                  style={{ backgroundColor: colors.primary, paddingVertical: 10, borderRadius: 10, alignItems: 'center', opacity: removalLoading ? 0.7 : 1 }}
                  data-testid="job-platform-admin-removal-readiness-button"
                  testID="job-platform-admin-removal-readiness-button"
                >
                  <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>
                    {removalLoading ? 'Checking...' : 'Evaluate Removal Readiness'}
                  </Text>
                </TouchableOpacity>
              </View>

              {removalReadiness && (
                <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 10 }} data-testid="job-platform-admin-removal-readiness-results" testID="job-platform-admin-removal-readiness-results">
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} data-testid="job-platform-admin-removal-readiness-status" testID="job-platform-admin-removal-readiness-status">
                    Sustained gate: {removalReadiness.sustained_gate_met ? 'PASS' : 'NOT READY'} • Remove now: {removalReadiness.ready_for_legacy_code_removal ? 'Yes' : 'No'}
                  </Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 4 }} data-testid="job-platform-admin-removal-readiness-action" testID="job-platform-admin-removal-readiness-action">
                    {removalReadiness.recommended_action || 'No recommendation available.'}
                  </Text>

                  <View style={{ marginTop: 8, gap: 4 }}>
                    {(removalReadiness.windows || []).map((window, idx) => (
                      <Text key={`${window.window_label}-${idx}`} style={{ color: colors.textMuted, fontSize: 11 }} data-testid={`job-platform-admin-removal-window-${idx}`} testID={`job-platform-admin-removal-window-${idx}`}>
                        {window.window_label}: {window.gate_met ? 'pass' : 'fail'} • {window.family_readiness.map((f) => `${f.route_family} e=${f.total_events} u=${f.active_users}`).join(' | ')}
                      </Text>
                    ))}
                  </View>
                </View>
              )}
            </View>
          </View>
        </ScrollView>
      </View>
    </AppShell>
    </AdminRouteGate>
  );
}
