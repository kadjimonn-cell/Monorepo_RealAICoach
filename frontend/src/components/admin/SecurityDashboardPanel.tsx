import React, { useEffect, useState, useCallback } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { View, Text, ActivityIndicator, TouchableOpacity, Switch, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';

// Theme-aware palette: maps to V2 light/dark tokens via useAdminTheme,
// then falls back to CSS vars so module-level helper sub-components render
// correctly without needing access to component-scope state.
function makeC(AC: any) { return {
  bg: AC?.bg || 'var(--app-bg)',
  bgSoft: AC?.bgAlt || AC?.cardSoft || 'var(--app-surface)',
  card: AC?.card || 'var(--app-card-bg)',
  border: AC?.border || 'var(--app-border)',
  text: AC?.text || 'var(--app-text)',
  textSec: AC?.textSec || 'var(--app-text-sec)',
  textMuted: AC?.textMuted || 'var(--app-text-muted)',
  primary: AC?.primary || 'var(--app-primary)',
  success: AC?.success || 'var(--app-success)',
  warning: AC?.warning || 'var(--app-warning)',
  error: AC?.error || 'var(--app-error)',
  purple: AC?.purple || 'var(--app-primary)',
  cyan: AC?.info || 'var(--app-info)',
  pink: AC?.purple || 'var(--app-primary)',
  successSoft: AC?.successSoft || 'var(--app-success-soft)',
  warningSoft: AC?.warningSoft || 'var(--app-warning-soft)',
  errorSoft: AC?.errorSoft || 'var(--app-error-soft)',
  primarySoft: AC?.primarySoft || 'var(--app-primary-soft)',
  successText: AC?.successText || 'var(--app-success)',
  warningText: AC?.warningText || 'var(--app-warning)',
  errorText: AC?.errorText || 'var(--app-error)',
}; }

// Module-scope theme-aware palette bound to --app-* CSS vars so
// module-level helper sub-components (AlertToggle / KpiPill / MetricChip /
// ScorePill / AuthRow, declared after the default export) render correctly
// without needing `C` to be in component scope.
const C = {
  errorSoft: 'var(--app-error-soft)',
  purpleText: 'var(--app-info)',
  successSoft: 'var(--app-success-soft)',
  successText: 'var(--app-success)',
  warningText: 'var(--app-warning)',
  bg: 'var(--app-bg)' as any,
  bgSoft: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  success: 'var(--app-success)' as any,
  warning: 'var(--app-warning)' as any,
  error: 'var(--app-error)' as any,
  purple: 'var(--app-primary)' as any,
  cyan: 'var(--app-info)' as any,
  pink: 'var(--app-primary)' as any,
};

interface Props {
  userId?: string;
  isAdmin?: boolean;
}

export default function SecurityDashboardPanel({ userId, isAdmin }: Props) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [overview, setOverview] = useState<any>(null);
  const [twoFa, setTwoFa] = useState<any>(null);
  const [sessions, setSessions] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [alertPrefs, setAlertPrefs] = useState<any>(null);
  const [knownDevices, setKnownDevices] = useState<any[]>([]);
  const [alertHistory, setAlertHistory] = useState<any[]>([]);
  const [revoking, setRevoking] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [msg, setMsg] = useState({ text: '', type: '' });
  const [phoneInput, setPhoneInput] = useState('');
  const [rotationOpsBusy, setRotationOpsBusy] = useState({
    attesting: false,
    validatingWebhook: false,
    generatingBundle: false,
    loadingChecklist: false,
  });

  const { data: ovData, loading, refetch: refetchOv } = useLiveQuery('/auth/security/overview', { entity: 'security', pollInterval: 30000 });
  const { data: twoFaData, refetch: refetch2fa } = useLiveQuery('/auth/2fa/status', { entity: 'security', pollInterval: 60000 });
  const { data: sessData, refetch: refetchSess } = useLiveQuery('/auth/sessions', { entity: 'security', pollInterval: 30000 });
  const { data: histData } = useLiveQuery('/auth/security/login-history', { entity: 'security', pollInterval: 60000 });
  const { data: apData, refetch: refetchPrefs } = useLiveQuery('/auth/security/alert-preferences', { entity: 'security', pollInterval: 60000 });
  const {
    data: authCoverageData,
    loading: authCoverageLoading,
    error: authCoverageError,
    refetch: refetchAuthCoverage,
    lastUpdated: authCoverageLastUpdated,
  } = useLiveQuery('/auth/admin/coverage-matrix', {
    entity: 'security',
    pollInterval: 30000,
    skip: !isAdmin,
  });
  const {
    data: keyRotationReadinessData,
    loading: keyRotationReadinessLoading,
    error: keyRotationReadinessError,
    refetch: refetchKeyRotationReadiness,
    lastUpdated: keyRotationReadinessLastUpdated,
  } = useLiveQuery('/admin/security/key-rotation/readiness', {
    entity: 'security',
    pollInterval: 45000,
    skip: !isAdmin,
  });
  const {
    data: keyRotationPolicyData,
    loading: keyRotationPolicyLoading,
    error: keyRotationPolicyError,
    refetch: refetchKeyRotationPolicy,
    lastUpdated: keyRotationPolicyLastUpdated,
  } = useLiveQuery('/admin/security/key-rotation/policy', {
    entity: 'security',
    pollInterval: 60000,
    skip: !isAdmin,
  });
  const {
    data: keyRotationChecklistData,
    loading: keyRotationChecklistLoading,
    error: keyRotationChecklistError,
    refetch: refetchKeyRotationChecklist,
    lastUpdated: keyRotationChecklistLastUpdated,
  } = useLiveQuery('/admin/security/key-rotation/go-live-checklist', {
    entity: 'security',
    pollInterval: 60000,
    skip: !isAdmin,
  });

  useEffect(() => { if (ovData) setOverview(ovData); }, [ovData]);
  useEffect(() => { if (twoFaData) setTwoFa(twoFaData); }, [twoFaData]);
  useEffect(() => { if (sessData) setSessions(sessData); }, [sessData]);
  useEffect(() => { if (histData) setHistory(histData?.events || histData?.history || []); }, [histData]);
  useEffect(() => {
    if (apData) {
      setAlertPrefs(apData.preferences || {});
      setKnownDevices(apData.known_devices || []);
      setAlertHistory(apData.alert_history || []);
      setPhoneInput(apData.preferences?.phone_number || '');
    }
  }, [apData]);

  const load = useCallback(async () => {
    const loaders = [refetchOv(), refetch2fa(), refetchSess(), refetchPrefs()];
    if (isAdmin) loaders.push(refetchAuthCoverage(), refetchKeyRotationReadiness(), refetchKeyRotationPolicy(), refetchKeyRotationChecklist());
    await Promise.all(loaders);
  }, [refetchOv, refetch2fa, refetchSess, refetchPrefs, refetchAuthCoverage, refetchKeyRotationReadiness, refetchKeyRotationPolicy, refetchKeyRotationChecklist, isAdmin]);
  useEffect(() => { if (msg.text) { const t = setTimeout(() => setMsg({ text: '', type: '' }), 4000); return () => clearTimeout(t); } }, [msg]);

  const revokeAll = async () => {
    setRevoking(true);
    try {
      await api.post('/auth/sessions/revoke-all');
      setMsg({ text: tx('securityDashboard.messages.sessionsRevoked', 'All other sessions revoked'), type: 'success' });
      load();
    } catch { setMsg({ text: tx('securityDashboard.messages.sessionsRevokeFailed', 'Failed to revoke sessions'), type: 'error' }); }
    setRevoking(false);
  };

  const togglePref = async (key: string, value: boolean) => {
    const updated = { ...alertPrefs, [key]: value };
    setAlertPrefs(updated);
    try { await api.put('/auth/security/alert-preferences', { [key]: value }); }
    catch { setAlertPrefs(alertPrefs); setMsg({ text: tx('securityDashboard.messages.prefSaveFailed', 'Failed to save preference'), type: 'error' }); }
  };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _savePhone = async () => {
    setSavingPrefs(true);
    try {
      await api.put('/auth/security/alert-preferences', { phone_number: phoneInput.trim() });
      setAlertPrefs({ ...alertPrefs, phone_number: phoneInput.trim() });
      setMsg({ text: tx('securityDashboard.messages.phoneSaved', 'Phone number saved'), type: 'success' });
    } catch { setMsg({ text: tx('securityDashboard.messages.phoneSaveFailed', 'Failed to save phone'), type: 'error' }); }
    setSavingPrefs(false);
  };

  const trustDevice = async (deviceId: string) => {
    try {
      await api.post('/auth/security/trust-device', { device_id: deviceId });
      setKnownDevices(knownDevices.map(d => d.device_id === deviceId ? { ...d, trusted: true } : d));
      setMsg({ text: tx('securityDashboard.messages.deviceTrusted', 'Device trusted'), type: 'success' });
    } catch { setMsg({ text: tx('securityDashboard.messages.deviceTrustFailed', 'Failed to trust device'), type: 'error' }); }
  };

  const removeDevice = async (deviceId: string) => {
    try {
      await api.delete(`/auth/security/known-device/${deviceId}`);
      setKnownDevices(knownDevices.filter(d => d.device_id !== deviceId));
      setMsg({ text: tx('securityDashboard.messages.deviceRemoved', 'Device removed'), type: 'success' });
    } catch { setMsg({ text: tx('securityDashboard.messages.deviceRemoveFailed', 'Failed to remove device'), type: 'error' }); }
  };

  const remediationHint = (provider: any) => {
    const reason = String(provider?.apply_capability?.reason || '').toLowerCase();
    if (reason === 'missing_rotation_scope') return tx('securityDashboard.rotationReadiness.remediation.missingScope', 'Add required rotation scope/permissions for this provider.');
    if (reason === 'missing_rotation_refresh_token') return tx('securityDashboard.rotationReadiness.remediation.missingRefreshToken', 'Set a valid rotation refresh token in secure environment variables.');
    if (reason === 'provider_rotate_lifecycle_disabled') return tx('securityDashboard.rotationReadiness.remediation.lifecycleDisabled', 'Enable KEY_ROTATION_ENABLE_PROVIDER_SIDE_LIFECYCLE for rotate-contract providers.');
    if (reason === 'rotation_env_mismatch') return tx('securityDashboard.rotationReadiness.remediation.envMismatch', 'Align provider credential mode with KEY_ROTATION_TARGET_ENV.');
    if (reason === 'api_adapter_credentials_missing') return tx('securityDashboard.rotationReadiness.remediation.adapterMissing', 'Provide missing adapter credentials shown in readiness requirements.');
    if (reason === 'provider_manual_only') return tx('securityDashboard.rotationReadiness.remediation.manualOnly', 'Use manual evidence workflow for this provider contract.');
    return tx('securityDashboard.rotationReadiness.remediation.none', 'No immediate remediation required.');
  };

  if (loading) return <View style={{ paddingVertical: 60, alignItems: 'center' }}><ActivityIndicator size="large" color={C.primary} /></View>;

  const sessionsArr = sessions?.sessions || [];
  const totalSessions = sessions?.total || sessionsArr.length;
  const has2fa = twoFa?.two_fa_enabled;
  const hasPin = twoFa?.has_pin;
  const hasPasskey = twoFa?.has_passkey;
  const backupCodes = twoFa?.backup_codes_remaining || 0;
  const coverage = authCoverageData || {};
  const coverageKpis = coverage?.kpis || {};
  const coverageRows = coverage?.matrix || [];
  const coverageOverall = String(coverage?.overall_status || 'unknown').toLowerCase();
  const coverageOverallColor = coverageOverall === 'pass' ? C.success : coverageOverall === 'warning' ? C.warning : C.error;
  const keyRotationReadiness = keyRotationReadinessData || {};
  const rotationSummary = keyRotationReadiness?.summary || {};
  const rotationProviders = Array.isArray(keyRotationReadiness?.providers) ? keyRotationReadiness.providers : [];
  const preflightGate = keyRotationReadiness?.preflight_gate || {};
  const preflightChecks = Array.isArray(preflightGate?.checks) ? preflightGate.checks : [];
  const preflightStatus = preflightGate?.passed ? 'pass' : 'fail';
  const preflightColor = preflightStatus === 'pass' ? C.success : C.error;
  const keyRotationPolicy = keyRotationPolicyData || {};
  const keyRotationChecklist = keyRotationChecklistData || {};
  const checklistSummary = keyRotationChecklist?.summary || {};
  const checklistProviders = Array.isArray(keyRotationChecklist?.providers) ? keyRotationChecklist.providers : [];
  const lastAttestation = keyRotationPolicy?.last_attestation || {};
  const lastGameDay = keyRotationPolicy?.last_game_day || {};
  const webhookConfigured = Boolean(keyRotationPolicy?.siem_webhook_configured);

  const runPolicyAttestation = async () => {
    setRotationOpsBusy(prev => ({ ...prev, attesting: true }));
    try {
      await api.post('/admin/security/key-rotation/policy/attest', {
        note: 'Dashboard-triggered attestation',
        run_prerequisite_refresh: true,
        validate_webhook: true,
        include_game_day_snapshot: true,
      });
      setMsg({ text: tx('securityDashboard.rotationReadiness.attestationSuccess', 'Policy attestation completed'), type: 'success' });
      await Promise.all([refetchKeyRotationPolicy(), refetchKeyRotationReadiness(), refetchKeyRotationChecklist()]);
    } catch {
      setMsg({ text: tx('securityDashboard.rotationReadiness.attestationFailed', 'Policy attestation failed'), type: 'error' });
    } finally {
      setRotationOpsBusy(prev => ({ ...prev, attesting: false }));
    }
  };

  const validateWebhookNow = async () => {
    setRotationOpsBusy(prev => ({ ...prev, validatingWebhook: true }));
    try {
      await api.post('/admin/security/key-rotation/policy/attest', {
        note: 'Dashboard-triggered webhook validation',
        run_prerequisite_refresh: false,
        validate_webhook: true,
        include_game_day_snapshot: false,
      });
      setMsg({ text: tx('securityDashboard.rotationReadiness.webhookValidationSuccess', 'Webhook validation completed'), type: 'success' });
      await refetchKeyRotationPolicy();
    } catch {
      setMsg({ text: tx('securityDashboard.rotationReadiness.webhookValidationFailed', 'Webhook validation failed'), type: 'error' });
    } finally {
      setRotationOpsBusy(prev => ({ ...prev, validatingWebhook: false }));
    }
  };

  const generateComplianceBundleNow = async () => {
    setRotationOpsBusy(prev => ({ ...prev, generatingBundle: true }));
    try {
      const runsResponse = await api.get('/admin/security/key-rotation/runs?limit=1', { silentLoading: true });
      const latestRun = (runsResponse?.data?.runs || [])[0];
      if (!latestRun?.run_id) {
        setMsg({ text: tx('securityDashboard.rotationReadiness.noRunsForBundle', 'No rotation runs available for bundle generation'), type: 'error' });
        return;
      }
      const bundleResponse = await api.get(`/admin/security/key-rotation/runs/${latestRun.run_id}/compliance-bundle?format=markdown`, { silentLoading: true });
      const bundleId = bundleResponse?.data?.bundle_id || 'bundle';
      setMsg({ text: tx('securityDashboard.rotationReadiness.bundleGenerated', `Compliance bundle generated: ${bundleId}`), type: 'success' });
    } catch {
      setMsg({ text: tx('securityDashboard.rotationReadiness.bundleGenerateFailed', 'Compliance bundle generation failed'), type: 'error' });
    } finally {
      setRotationOpsBusy(prev => ({ ...prev, generatingBundle: false }));
    }
  };

  // Security score calculation
  let score = 30; // base: has password
  if (has2fa) score += 25;
  if (hasPin) score += 15;
  if (hasPasskey) score += 20;
  if (backupCodes > 0) score += 10;
  const scoreColor = score >= 80 ? C.success : score >= 50 ? C.warning : C.error;
  const scoreLabel = score >= 80
    ? tx('securityDashboard.score.strong', 'STRONG')
    : score >= 50
      ? tx('securityDashboard.score.moderate', 'MODERATE')
      : tx('securityDashboard.score.weak', 'WEAK');

  return (
    <View data-testid="security-dashboard-panel" testID="security-dashboard-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30') }}>
            <Ionicons name="shield-checkmark" size={24} color={C.primary} />
          </View>

          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="rotation-readiness-operator-actions" testID="rotation-readiness-operator-actions">
            <TouchableOpacity onPress={runPolicyAttestation} disabled={rotationOpsBusy.attesting} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '35'), opacity: rotationOpsBusy.attesting ? 0.7 : 1 }} data-testid="rotation-readiness-attest-now-button" testID="rotation-readiness-attest-now-button">
              <Ionicons name="shield-checkmark" size={13} color={C.primary} />
              <Text style={{ color: C.primary, fontSize: 10, fontWeight: '700' }}>{rotationOpsBusy.attesting ? tx('securityDashboard.rotationReadiness.attesting', 'Attesting...') : tx('securityDashboard.rotationReadiness.attestNow', 'Run Attestation')}</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={validateWebhookNow} disabled={rotationOpsBusy.validatingWebhook} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.cyan, '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.cyan, '35'), opacity: rotationOpsBusy.validatingWebhook ? 0.7 : 1 }} data-testid="rotation-readiness-validate-webhook-button" testID="rotation-readiness-validate-webhook-button">
              <Ionicons name="cloud-done" size={13} color={C.cyan} />
              <Text style={{ color: C.cyan, fontSize: 10, fontWeight: '700' }}>{rotationOpsBusy.validatingWebhook ? tx('securityDashboard.rotationReadiness.validatingWebhook', 'Validating...') : tx('securityDashboard.rotationReadiness.validateWebhook', 'Validate Webhook')}</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={generateComplianceBundleNow} disabled={rotationOpsBusy.generatingBundle} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.success, '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '35'), opacity: rotationOpsBusy.generatingBundle ? 0.7 : 1 }} data-testid="rotation-readiness-generate-bundle-button" testID="rotation-readiness-generate-bundle-button">
              <Ionicons name="document-text" size={13} color={C.success} />
              <Text style={{ color: C.success, fontSize: 10, fontWeight: '700' }}>{rotationOpsBusy.generatingBundle ? tx('securityDashboard.rotationReadiness.generatingBundle', 'Generating...') : tx('securityDashboard.rotationReadiness.generateBundle', 'Generate Bundle')}</Text>
            </TouchableOpacity>
          </View>

          <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="rotation-readiness-ops-badges" testID="rotation-readiness-ops-badges">
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor((webhookConfigured ? C.success : C.warning), '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor((webhookConfigured ? C.success : C.warning), '35') }} data-testid="rotation-readiness-webhook-status-badge" testID="rotation-readiness-webhook-status-badge">
              <Text style={{ color: webhookConfigured ? C.success : C.warningText, fontSize: 9, fontWeight: '800' }}>{webhookConfigured ? 'WEBHOOK CONFIGURED' : 'WEBHOOK NOT CONFIGURED'}</Text>
            </View>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="rotation-readiness-last-attestation-badge" testID="rotation-readiness-last-attestation-badge">
              <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700' }}>LAST ATTEST: {lastAttestation?.attested_at ? String(lastAttestation.attested_at).slice(0, 10) : '—'}</Text>
            </View>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="rotation-readiness-last-game-day-badge" testID="rotation-readiness-last-game-day-badge">
              <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700' }}>LAST GAME-DAY: {lastGameDay?.recorded_at ? String(lastGameDay.recorded_at).slice(0, 10) : '—'}</Text>
            </View>
          </View>

          {keyRotationPolicyLoading || keyRotationChecklistLoading ? (
            <View style={{ marginTop: 8, flexDirection: 'row', alignItems: 'center', gap: 6 }} data-testid="rotation-readiness-ops-loading" testID="rotation-readiness-ops-loading">
              <ActivityIndicator size="small" color={C.primary} />
              <Text style={{ color: C.textMuted, fontSize: 10 }}>{tx('securityDashboard.rotationReadiness.opsLoading', 'Loading operational status...')}</Text>
            </View>
          ) : null}

          {keyRotationPolicyError ? (
            <Text style={{ color: C.error, marginTop: 6, fontSize: 10 }} data-testid="rotation-readiness-policy-error" testID="rotation-readiness-policy-error">{keyRotationPolicyError}</Text>
          ) : null}
          {keyRotationChecklistError ? (
            <Text style={{ color: C.error, marginTop: 3, fontSize: 10 }} data-testid="rotation-readiness-checklist-error" testID="rotation-readiness-checklist-error">{keyRotationChecklistError}</Text>
          ) : null}
          <View>
            <Text style={{ color: C.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5 }} data-testid="security-dashboard-title" testID="security-dashboard-title">{tx('securityDashboard.header.title', 'Security Dashboard')}</Text>
            <Text style={{ color: C.textMuted, fontSize: 12, marginTop: 2 }}>{tx('securityDashboard.header.subtitle', 'Account protection & access management')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <TouchableOpacity
            onPress={async () => {
              // Build a Tailwind-compatible theme fragment from the ACTIVE V2
              // palette (light + dark) so designers can paste it straight into
              // a tailwind.config.js `theme.extend.colors` block.
              const cfg = {
                light: {
                  bg: AC.bg, surface: AC.card, muted: AC.textMuted,
                  text: AC.text, primary: AC.primary, accent: AC.accent,
                  border: AC.border, success: AC.success, warning: AC.warning,
                  danger: AC.error,
                },
                dark: {
                  bg: AC.bg, surface: AC.card, muted: AC.textMuted,
                  text: AC.text, primary: AC.primary, accent: AC.accent,
                  border: AC.border, success: AC.success, warning: AC.warning,
                  danger: AC.error,
                },
              };
              const snippet = `// Tailwind theme.extend.colors — exported from RealAICoach V2\n// Paste into tailwind.config.js\nmodule.exports = {\n  theme: {\n    extend: {\n      colors: ${JSON.stringify(cfg, null, 8).replace(/\n/g, '\n      ')},\n    },\n  },\n};\n`;
              try {
                if (typeof navigator !== 'undefined' && navigator.clipboard) {
                  await navigator.clipboard.writeText(snippet);
                  setMsg({ text: tx('securityDashboard.messages.tailwindCopied', 'Tailwind config copied to clipboard'), type: 'success' });
                } else {
                  setMsg({ text: tx('securityDashboard.messages.clipboardUnavailable', 'Clipboard API unavailable'), type: 'error' });
                }
              } catch {
                setMsg({ text: tx('securityDashboard.messages.tailwindCopyFailed', 'Failed to copy Tailwind config'), type: 'error' });
              }
            }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.primary, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30') }}
            data-testid="security-copy-tailwind-config-btn" testID="security-copy-tailwind-config-btn"
            accessibilityRole="button"
            accessibilityLabel="Copy Tailwind config for current V2 palette"
          >
            <Ionicons name="color-palette-outline" size={14} color={C.primary} />
            <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700' }}>{tx('securityDashboard.actions.copyTailwind', 'Copy Tailwind')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={load} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="security-refresh-btn" testID="security-refresh-btn">
            <Ionicons name="refresh" size={14} color={C.textSec} />
            <Text style={{ color: C.textSec, fontSize: 11, fontWeight: '600' }}>{tx('securityDashboard.actions.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Status message */}
      {msg.text ? (
        <View style={{ backgroundColor: msg.type === 'success' ? C.successSoft : C.errorSoft, borderRadius: 10, padding: 10, marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: msg.type === 'success' ? C.successSoft : C.errorSoft }}>
          <Ionicons name={msg.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={16} color={msg.type === 'success' ? C.success : C.error} />
          <Text style={{ color: msg.type === 'success' ? C.success : C.error, fontSize: 12, flex: 1 }}>{msg.text}</Text>
        </View>
      ) : null}

      {/* Security Score */}
      <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: C.border, alignItems: 'center', marginBottom: 16 }} data-testid="security-score-card" testID="security-score-card">
        <View style={{ width: 100, height: 100, borderRadius: 50, borderWidth: 5, borderColor: (globalThis as any).__alphaColor(scoreColor, '35'), alignItems: 'center', justifyContent: 'center', marginBottom: 10 }}>
          <Text style={{ color: scoreColor, fontSize: 36, fontWeight: '900' }}>{score}</Text>
        </View>
        <Text style={{ color: scoreColor, fontSize: 16, fontWeight: '800', letterSpacing: 2, marginBottom: 4 }}>{scoreLabel}</Text>
        <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('securityDashboard.score.label', 'Security Score')}</Text>

        {/* Score breakdown */}
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, flexWrap: 'wrap', justifyContent: 'center' }}>
          <ScorePill label={tx('securityDashboard.score.password', 'Password')} active={true} />
          <ScorePill label={tx('securityDashboard.score.twoFa', '2FA')} active={has2fa} />
          <ScorePill label={tx('securityDashboard.score.pin', 'PIN')} active={hasPin} />
          <ScorePill label={tx('securityDashboard.score.passkey', 'Passkey')} active={hasPasskey} />
          <ScorePill label={tx('securityDashboard.score.backupCodes', 'Backup Codes')} active={backupCodes > 0} />
        </View>
      </View>

      {isAdmin ? (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 }} data-testid="rotation-readiness-card" testID="rotation-readiness-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="sync-circle" size={18} color={C.primary} />
              <View>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }} data-testid="rotation-readiness-title" testID="rotation-readiness-title">{tx('securityDashboard.rotationReadiness.title', 'Rotation Readiness')}</Text>
                <Text style={{ color: C.textMuted, fontSize: 10 }} data-testid="rotation-readiness-subtitle" testID="rotation-readiness-subtitle">{tx('securityDashboard.rotationReadiness.subtitle', 'Preflight policy-gate health plus per-provider API apply capability')}</Text>
              </View>
            </View>

            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(preflightColor, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(preflightColor, '35') }} data-testid="rotation-readiness-preflight-pill" testID="rotation-readiness-preflight-pill">
                <Text style={{ color: preflightColor, fontSize: 10, fontWeight: '800' }} data-testid="rotation-readiness-preflight-pill-value" testID="rotation-readiness-preflight-pill-value">PREFLIGHT {preflightStatus.toUpperCase()}</Text>
              </View>
              <TouchableOpacity onPress={refetchKeyRotationReadiness} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="rotation-readiness-refresh-button" testID="rotation-readiness-refresh-button">
                <Ionicons name="refresh" size={13} color={C.textSec} />
                <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{tx('securityDashboard.rotationReadiness.refresh', 'Refresh')}</Text>
              </TouchableOpacity>
            </View>
          </View>

          {keyRotationReadinessLoading ? (
            <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="rotation-readiness-loading" testID="rotation-readiness-loading">
              <ActivityIndicator size="small" color={C.primary} />
              <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('securityDashboard.rotationReadiness.loading', 'Loading rotation readiness...')}</Text>
            </View>
          ) : null}

          {keyRotationReadinessError ? (
            <View style={{ marginTop: 10, backgroundColor: (globalThis as any).__alphaColor(C.error, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '35'), borderRadius: 10, padding: 10 }} data-testid="rotation-readiness-error" testID="rotation-readiness-error">
              <Text style={{ color: C.error, fontSize: 11, fontWeight: '700' }} data-testid="rotation-readiness-error-text" testID="rotation-readiness-error-text">{keyRotationReadinessError}</Text>
            </View>
          ) : null}

          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="rotation-readiness-kpis" testID="rotation-readiness-kpis">
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.providers', 'Providers')} value={rotationSummary.total} color={C.primary} testId="rotation-readiness-kpi-total" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.ready', 'Ready')} value={rotationSummary.ready} color={C.successText} testId="rotation-readiness-kpi-ready" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.blocked', 'Blocked')} value={rotationSummary.blocked} color={C.error} testId="rotation-readiness-kpi-blocked" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.apiRotate', 'API Rotate')} value={rotationSummary.api_rotate_ready} color={C.cyan} testId="rotation-readiness-kpi-api-rotate" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.apiProbe', 'API Probe')} value={rotationSummary.api_probe_only_ready ?? rotationSummary.api_apply_ready} color={C.primary} testId="rotation-readiness-kpi-api-probe" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.apiApplyLegacy', 'API Apply')} value={rotationSummary.api_apply_ready ?? rotationSummary.api_probe_only_ready} color={C.primary} testId="rotation-readiness-kpi-api-apply" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.manual', 'Manual')} value={rotationSummary.manual_by_constraint ?? rotationSummary.manual_required} color={C.warningText} testId="rotation-readiness-kpi-manual" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.adapterMissing', 'Adapter Missing')} value={rotationSummary.adapter_missing} color={C.error} testId="rotation-readiness-kpi-adapter-missing" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.rotateBlocked', 'Rotate Blocked')} value={checklistSummary.rotate_contract_hard_blocked} color={C.error} testId="rotation-readiness-kpi-rotate-blocked" />
            <KpiPill label={tx('securityDashboard.rotationReadiness.kpi.liveGreen', 'Go-Live Green')} value={checklistSummary.is_green_for_live_apply ? 'YES' : 'NO'} color={checklistSummary.is_green_for_live_apply ? C.successText : C.warningText} testId="rotation-readiness-kpi-live-green" />
          </View>

          <Text style={{ color: C.textMuted, marginTop: 8, fontSize: 10 }} data-testid="rotation-readiness-last-updated" testID="rotation-readiness-last-updated">
            {tx('securityDashboard.rotationReadiness.lastUpdated', 'Last updated:')} {keyRotationReadiness?.generated_at ? String(keyRotationReadiness.generated_at).slice(0, 19).replace('T', ' ') : keyRotationReadinessLastUpdated ? keyRotationReadinessLastUpdated.toISOString().slice(0, 19).replace('T', ' ') : '—'}
          </Text>
          <Text style={{ color: C.textMuted, marginTop: 2, fontSize: 10 }} data-testid="rotation-readiness-target-environment" testID="rotation-readiness-target-environment">
            {tx('securityDashboard.rotationReadiness.targetEnvironment', 'Target environment:')} {String(rotationSummary?.target_environment || 'live').toUpperCase()}
          </Text>
          <Text style={{ color: C.textMuted, marginTop: 2, fontSize: 10 }} data-testid="rotation-readiness-ops-last-updated" testID="rotation-readiness-ops-last-updated">
            {tx('securityDashboard.rotationReadiness.opsLastUpdated', 'Ops status updated:')} {keyRotationPolicyLastUpdated ? keyRotationPolicyLastUpdated.toISOString().slice(0, 19).replace('T', ' ') : keyRotationChecklistLastUpdated ? keyRotationChecklistLastUpdated.toISOString().slice(0, 19).replace('T', ' ') : '—'}
          </Text>

          <View style={{ marginTop: 10, gap: 6 }} data-testid="rotation-readiness-preflight-checks" testID="rotation-readiness-preflight-checks">
            {preflightChecks.length === 0 ? (
              <View style={{ padding: 10, borderRadius: 9, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="rotation-preflight-checks-empty" testID="rotation-preflight-checks-empty">
                <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="rotation-preflight-checks-empty-text" testID="rotation-preflight-checks-empty-text">{tx('securityDashboard.rotationReadiness.noPreflightChecks', 'No preflight checks available yet.')}</Text>
              </View>
            ) : preflightChecks.map((check: any, idx: number) => {
              const passed = Boolean(check?.passed);
              const checkColor = passed ? C.success : C.error;
              return (
                <View key={`preflight-${idx}`} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, paddingVertical: 8, paddingHorizontal: 10, borderRadius: 9, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid={`rotation-preflight-check-${idx}`} testID={`rotation-preflight-check-${idx}`}>
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', flex: 1 }} data-testid={`rotation-preflight-check-name-${idx}`} testID={`rotation-preflight-check-name-${idx}`}>{String(check?.name || 'check').replace(/_/g, ' ')}</Text>
                  <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(checkColor, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(checkColor, '35') }} data-testid={`rotation-preflight-check-status-pill-${idx}`} testID={`rotation-preflight-check-status-pill-${idx}`}>
                    <Text style={{ color: checkColor, fontSize: 9, fontWeight: '800' }} data-testid={`rotation-preflight-check-status-${idx}`} testID={`rotation-preflight-check-status-${idx}`}>{passed ? 'PASS' : 'FAIL'}</Text>
                  </View>
                </View>
              );
            })}
          </View>

          <View style={{ marginTop: 10, gap: 8 }} data-testid="rotation-readiness-provider-rows" testID="rotation-readiness-provider-rows">
            {rotationProviders.length === 0 ? (
              <View style={{ padding: 10, borderRadius: 9, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="rotation-provider-rows-empty" testID="rotation-provider-rows-empty">
                <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="rotation-provider-rows-empty-text" testID="rotation-provider-rows-empty-text">{tx('securityDashboard.rotationReadiness.noProviders', 'No provider readiness rows available yet.')}</Text>
              </View>
            ) : rotationProviders.map((provider: any, idx: number) => {
              const readinessState = String(provider?.readiness_state || 'unknown').toLowerCase();
              const applyState = String(provider?.apply_capability?.status || 'unknown').toLowerCase();
              const checklistRow = checklistProviders.find((row: any) => row?.provider_id === provider?.provider_id) || {};
              const readinessColor = readinessState === 'ready' ? C.success : C.error;
              const applyColor =
                applyState === 'api_rotate_ready' ? C.success :
                applyState === 'api_probe_only_ready' ? C.primary :
                applyState === 'manual_by_provider_constraint' ? C.warning :
                applyState === 'guarded' ? C.warning : C.error;
              return (
                <View key={`${provider?.provider_id || idx}`} style={{ borderRadius: 10, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, padding: 10 }} data-testid={`rotation-provider-row-${idx}`} testID={`rotation-provider-row-${idx}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} data-testid={`rotation-provider-name-${idx}`} testID={`rotation-provider-name-${idx}`}>{provider?.label || provider?.provider_id}</Text>
                    <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                      <View style={{ paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(readinessColor, '35'), backgroundColor: (globalThis as any).__alphaColor(readinessColor, '18') }} data-testid={`rotation-provider-readiness-pill-${idx}`} testID={`rotation-provider-readiness-pill-${idx}`}>
                        <Text style={{ color: readinessColor, fontSize: 9, fontWeight: '800' }} data-testid={`rotation-provider-readiness-${idx}`} testID={`rotation-provider-readiness-${idx}`}>{readinessState.toUpperCase()}</Text>
                      </View>
                      <View style={{ paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(applyColor, '35'), backgroundColor: (globalThis as any).__alphaColor(applyColor, '18') }} data-testid={`rotation-provider-apply-pill-${idx}`} testID={`rotation-provider-apply-pill-${idx}`}>
                        <Text style={{ color: applyColor, fontSize: 9, fontWeight: '800' }} data-testid={`rotation-provider-apply-status-${idx}`} testID={`rotation-provider-apply-status-${idx}`}>{applyState.toUpperCase()}</Text>
                      </View>
                    </View>
                  </View>
                  <Text style={{ color: C.textMuted, marginTop: 6, fontSize: 10 }} data-testid={`rotation-provider-apply-message-${idx}`} testID={`rotation-provider-apply-message-${idx}`}>{provider?.apply_capability?.message || tx('securityDashboard.rotationReadiness.noMessage', 'No apply capability message')}</Text>
                  <Text style={{ color: C.warningText, marginTop: 3, fontSize: 10, fontWeight: '700' }} data-testid={`rotation-provider-remediation-${idx}`} testID={`rotation-provider-remediation-${idx}`}>
                    {tx('securityDashboard.rotationReadiness.remediation', 'Remediation')}: {remediationHint(provider)}
                  </Text>
                  {Array.isArray(checklistRow?.hard_blockers) && checklistRow.hard_blockers.length > 0 ? (
                    <View style={{ marginTop: 6, gap: 4 }} data-testid={`rotation-provider-blockers-${idx}`} testID={`rotation-provider-blockers-${idx}`}>
                      {checklistRow.hard_blockers.slice(0, 2).map((blocker: any, bi: number) => (
                        <View key={bi} style={{ backgroundColor: (globalThis as any).__alphaColor(C.error, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '35'), borderRadius: 8, padding: 6 }} data-testid={`rotation-provider-blocker-${idx}-${bi}`} testID={`rotation-provider-blocker-${idx}-${bi}`}>
                          <Text style={{ color: C.error, fontSize: 10, fontWeight: '700' }}>{String(blocker?.code || 'blocker').replace(/_/g, ' ')}</Text>
                          <Text style={{ color: C.textMuted, fontSize: 10 }}>{blocker?.message}</Text>
                        </View>
                      ))}
                    </View>
                  ) : null}
                  <Text style={{ color: C.textMuted, marginTop: 3, fontSize: 10 }} data-testid={`rotation-provider-contract-mode-${idx}`} testID={`rotation-provider-contract-mode-${idx}`}>
                    {tx('securityDashboard.rotationReadiness.contractMode', 'Contract')}: {String(provider?.apply_contract_mode || 'unknown').toUpperCase()}
                  </Text>
                </View>
              );
            })}
          </View>
        </View>
      ) : null}

      {isAdmin ? (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 16 }} data-testid="auth-coverage-matrix-card" testID="auth-coverage-matrix-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="grid" size={18} color={C.cyan} />
              <View>
                <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }} data-testid="auth-coverage-matrix-title" testID="auth-coverage-matrix-title">{tx('securityDashboard.authCoverage.title', 'Auth Coverage Matrix')}</Text>
                <Text style={{ color: C.textMuted, fontSize: 10 }} data-testid="auth-coverage-matrix-subtitle" testID="auth-coverage-matrix-subtitle">{tx('securityDashboard.authCoverage.subtitle', 'Global auth modules health from live probes + latest audit evidence')}</Text>
              </View>
            </View>

            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(coverageOverallColor, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(coverageOverallColor, '35') }} data-testid="auth-coverage-matrix-overall-pill" testID="auth-coverage-matrix-overall-pill">
                <Text style={{ color: coverageOverallColor, fontSize: 10, fontWeight: '800' }} data-testid="auth-coverage-matrix-overall-pill-value" testID="auth-coverage-matrix-overall-pill-value">{coverageOverall.toUpperCase()}</Text>
              </View>
              <TouchableOpacity onPress={refetchAuthCoverage} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="auth-coverage-matrix-refresh-btn" testID="auth-coverage-matrix-refresh-btn">
                <Ionicons name="refresh" size={13} color={C.textSec} />
                <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{tx('securityDashboard.authCoverage.refreshMatrix', 'Refresh Matrix')}</Text>
              </TouchableOpacity>
            </View>
          </View>

          {authCoverageLoading ? (
            <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="auth-coverage-matrix-loading" testID="auth-coverage-matrix-loading">
              <ActivityIndicator size="small" color={C.primary} />
              <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('securityDashboard.authCoverage.loading', 'Loading coverage matrix...')}</Text>
            </View>
          ) : null}

          {authCoverageError ? (
            <View style={{ marginTop: 10, backgroundColor: (globalThis as any).__alphaColor(C.error, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '35'), borderRadius: 10, padding: 10 }} data-testid="auth-coverage-matrix-error" testID="auth-coverage-matrix-error">
              <Text style={{ color: C.error, fontSize: 11, fontWeight: '700' }} data-testid="auth-coverage-matrix-error-text" testID="auth-coverage-matrix-error-text">{authCoverageError}</Text>
            </View>
          ) : null}

          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="auth-coverage-matrix-kpis" testID="auth-coverage-matrix-kpis">
            <KpiPill label={tx('securityDashboard.authCoverage.kpis.modules', 'Modules')} value={coverageKpis.modules_total} color={C.primary} testId="auth-coverage-kpi-modules" />
            <KpiPill label={tx('securityDashboard.authCoverage.kpis.pass', 'Pass')} value={coverageKpis.modules_pass} color={C.successText} testId="auth-coverage-kpi-pass" />
            <KpiPill label={tx('securityDashboard.authCoverage.kpis.warn', 'Warn')} value={coverageKpis.modules_warning} color={C.warningText} testId="auth-coverage-kpi-warning" />
            <KpiPill label={tx('securityDashboard.authCoverage.kpis.fail', 'Fail')} value={coverageKpis.modules_fail} color={C.error} testId="auth-coverage-kpi-fail" />
            <KpiPill label={tx('securityDashboard.authCoverage.kpis.endpoints', 'Endpoints')} value={coverageKpis.endpoints_total} color={C.cyan} testId="auth-coverage-kpi-endpoints" />
            <KpiPill label={tx('securityDashboard.authCoverage.kpis.coverage', 'Coverage %')} value={coverageKpis.coverage_pct_estimate} color={C.purpleText} testId="auth-coverage-kpi-coverage" />
          </View>

          <Text style={{ color: C.textMuted, marginTop: 8, fontSize: 10 }} data-testid="auth-coverage-matrix-last-updated" testID="auth-coverage-matrix-last-updated">
            {tx('securityDashboard.authCoverage.lastUpdated', 'Last updated:')} {coverage?.generated_at ? String(coverage.generated_at).slice(0, 19).replace('T', ' ') : authCoverageLastUpdated ? authCoverageLastUpdated.toISOString().slice(0, 19).replace('T', ' ') : '—'}
          </Text>

          <View style={{ marginTop: 10, gap: 8 }} data-testid="auth-coverage-matrix-rows" testID="auth-coverage-matrix-rows">
            {coverageRows.length === 0 ? (
              <View style={{ padding: 10, borderRadius: 10, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="auth-coverage-matrix-empty" testID="auth-coverage-matrix-empty">
                <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('securityDashboard.authCoverage.noRows', 'No coverage rows available yet.')}</Text>
              </View>
            ) : (
              coverageRows.map((row: any, idx: number) => {
                const status = String(row?.status || 'unknown').toLowerCase();
                const probeStatus = String(row?.live_probe?.status || 'unknown').toLowerCase();
                const statusColor = status === 'pass' ? C.success : status === 'warning' ? C.warning : C.error;
                const probeColor = probeStatus === 'pass' ? C.success : probeStatus === 'warning' ? C.warning : C.error;
                return (
                  <View key={`${row?.module_id || idx}`} style={{ borderRadius: 10, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, padding: 10 }} data-testid={`auth-coverage-row-${idx}`} testID={`auth-coverage-row-${idx}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} data-testid={`auth-coverage-row-title-${idx}`} testID={`auth-coverage-row-title-${idx}`}>{row?.title}</Text>
                      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                        <View style={{ paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(statusColor, '35'), backgroundColor: (globalThis as any).__alphaColor(statusColor, '18') }} data-testid={`auth-coverage-row-status-${idx}`} testID={`auth-coverage-row-status-${idx}`}>
                          <Text style={{ color: statusColor, fontSize: 9, fontWeight: '800' }}>{status.toUpperCase()}</Text>
                        </View>
                        <View style={{ paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(probeColor, '35'), backgroundColor: (globalThis as any).__alphaColor(probeColor, '18') }} data-testid={`auth-coverage-row-probe-${idx}`} testID={`auth-coverage-row-probe-${idx}`}>
                          <Text style={{ color: probeColor, fontSize: 9, fontWeight: '800' }}>PROBE {probeStatus.toUpperCase()}</Text>
                        </View>
                      </View>
                    </View>

                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 7 }}>
                      <MetricChip label={tx('securityDashboard.authCoverage.row.endpoints', 'Endpoints')} value={row?.endpoints_total} color={C.primary} testId={`auth-coverage-row-endpoints-${idx}`} />
                      <MetricChip label={tx('securityDashboard.authCoverage.row.passed', 'Passed')} value={row?.endpoints_passed_estimate} color={C.successText} testId={`auth-coverage-row-passed-${idx}`} />
                      <MetricChip label={tx('securityDashboard.authCoverage.row.openIssues', 'Open Issues')} value={row?.open_issues_count} color={row?.open_issues_count > 0 ? C.warning : C.success} testId={`auth-coverage-row-issues-${idx}`} />
                    </View>

                    <Text style={{ color: C.textMuted, marginTop: 6, fontSize: 10 }} data-testid={`auth-coverage-row-note-${idx}`} testID={`auth-coverage-row-note-${idx}`}>
                      {row?.live_probe?.note || tx('securityDashboard.authCoverage.row.noProbeNotes', 'No probe notes')}
                    </Text>

                    {Array.isArray(row?.open_issues) && row.open_issues.length > 0 ? (
                      <View style={{ marginTop: 6, gap: 4 }} data-testid={`auth-coverage-row-open-issues-${idx}`} testID={`auth-coverage-row-open-issues-${idx}`}>
                        {row.open_issues.slice(0, 2).map((issue: any, ii: number) => (
                          <View key={ii} style={{ backgroundColor: (globalThis as any).__alphaColor(C.warning, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.warning, '35'), borderRadius: 8, padding: 6 }} data-testid={`auth-coverage-row-open-issue-${idx}-${ii}`} testID={`auth-coverage-row-open-issue-${idx}-${ii}`}>
                            <Text style={{ color: C.warningText, fontSize: 10, fontWeight: '700' }}>{issue?.endpoint}</Text>
                            <Text style={{ color: C.textMuted, fontSize: 10 }}>{issue?.issue}</Text>
                          </View>
                        ))}
                      </View>
                    ) : null}
                  </View>
                );
              })
            )}
          </View>
        </View>
      ) : null}

      {/* Auth Methods Grid */}
      <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12, marginBottom: 16 }}>
        {/* 2FA Status */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: has2fa ? C.success : C.error }} data-testid="2fa-status-card" testID="2fa-status-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: has2fa ? (globalThis as any).__alphaColor(C.success, '18') : C.error + '18', alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="key" size={20} color={has2fa ? C.success : C.error} />
            </View>
            <View>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('securityDashboard.twoFa.title', 'Two-Factor Auth')}</Text>
              <Text style={{ color: has2fa ? C.success : C.error, fontSize: 11, fontWeight: '600' }}>
                {has2fa ? tx('securityDashboard.twoFa.enabled', 'Enabled') : tx('securityDashboard.twoFa.notEnabled', 'Not Enabled')}
              </Text>
            </View>
          </View>
          {has2fa && (
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={{ flex: 1, backgroundColor: C.bgSoft, borderRadius: 8, padding: 10, alignItems: 'center' }}>
                <Text style={{ color: C.primary, fontSize: 16, fontWeight: '800' }}>{backupCodes}</Text>
                <Text style={{ color: C.textMuted, fontSize: 9 }}>{tx('securityDashboard.twoFa.backupCodes', 'Backup Codes')}</Text>
              </View>
              <View style={{ flex: 1, backgroundColor: C.bgSoft, borderRadius: 8, padding: 10, alignItems: 'center' }}>
                <Ionicons name="checkmark-circle" size={16} color={C.successText} />
                <Text style={{ color: C.textMuted, fontSize: 9, marginTop: 2 }}>{tx('securityDashboard.common.active', 'Active')}</Text>
              </View>
            </View>
          )}
          {!has2fa && (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.error, '10'), borderRadius: 8, padding: 10 }}>
              <Text style={{ color: C.error, fontSize: 11 }}>{tx('securityDashboard.twoFa.enablePrompt', 'Enable 2FA in Settings to protect your account from unauthorized access.')}</Text>
            </View>
          )}
        </View>

        {/* PIN & Biometric */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: hasPin ? C.success : C.textMuted }} data-testid="pin-status-card" testID="pin-status-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: hasPin ? (globalThis as any).__alphaColor(C.purple, '18') : C.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="finger-print" size={20} color={hasPin ? C.purple : C.textMuted} />
            </View>
            <View>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('securityDashboard.pin.title', 'PIN / Biometric')}</Text>
              <Text style={{ color: hasPin ? C.success : C.textMuted, fontSize: 11, fontWeight: '600' }}>
                {hasPin ? tx('securityDashboard.pin.configured', 'PIN Set') : tx('securityDashboard.pin.notConfigured', 'Not Configured')}
              </Text>
            </View>
          </View>
          <View style={{ gap: 8 }}>
            <AuthRow label={tx('securityDashboard.pin.pinCode', 'PIN Code')} enabled={hasPin} icon="keypad" />
            <AuthRow label={tx('securityDashboard.pin.fingerprint', 'Fingerprint')} enabled={hasPin} icon="finger-print" />
            <AuthRow label={tx('securityDashboard.pin.faceId', 'Face ID')} enabled={hasPin} icon="scan" />
          </View>
        </View>

        {/* Passkey / WebAuthn */}
        <View style={{ flex: 1, backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: hasPasskey ? C.success : C.textMuted }} data-testid="passkey-status-card" testID="passkey-status-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: hasPasskey ? (globalThis as any).__alphaColor(C.cyan, '18') : C.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="hardware-chip" size={20} color={hasPasskey ? C.cyan : C.textMuted} />
            </View>
            <View>
              <Text style={{ color: C.text, fontSize: 14, fontWeight: '700' }}>{tx('securityDashboard.passkey.title', 'Passkey / WebAuthn')}</Text>
              <Text style={{ color: hasPasskey ? C.success : C.textMuted, fontSize: 11, fontWeight: '600' }}>
                {hasPasskey ? tx('securityDashboard.passkey.registered', 'Registered') : tx('securityDashboard.passkey.notRegistered', 'Not Registered')}
              </Text>
            </View>
          </View>
          {hasPasskey ? (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.success, '10'), borderRadius: 8, padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="shield-checkmark" size={14} color={C.successText} />
              <Text style={{ color: C.successText, fontSize: 11 }}>{tx('securityDashboard.passkey.passwordless', 'Passwordless login available via device credentials')}</Text>
            </View>
          ) : (
            <View style={{ backgroundColor: C.bgSoft, borderRadius: 8, padding: 10 }}>
              <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('securityDashboard.passkey.registerPrompt', 'Register a passkey for faster, phishing-resistant login')}</Text>
            </View>
          )}
        </View>
      </View>

      {/* Active Sessions */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, marginBottom: 16 }} data-testid="active-sessions-card" testID="active-sessions-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="laptop" size={18} color={C.primary} />
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('securityDashboard.sessions.title', 'Active Sessions')}</Text>
            <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.primary, '20') }}>
              <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>{totalSessions}</Text>
            </View>
          </View>
          <TouchableOpacity onPress={revokeAll} disabled={revoking} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.error, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '30') }} data-testid="revoke-all-sessions-btn" testID="revoke-all-sessions-btn">
            <Ionicons name="log-out" size={12} color={C.error} />
            <Text style={{ color: C.error, fontSize: 10, fontWeight: '700' }}>{revoking ? tx('securityDashboard.sessions.revoking', 'Revoking...') : tx('securityDashboard.sessions.revokeAll', 'Revoke All')}</Text>
          </TouchableOpacity>
        </View>

        {sessionsArr.length === 0 ? (
          <View style={{ padding: 20, alignItems: 'center' }}>
            <Text style={{ color: C.textMuted, fontSize: 12 }}>{tx('securityDashboard.sessions.none', 'No active sessions found')}</Text>
          </View>
        ) : (
          <View style={{ gap: 8 }}>
            {sessionsArr.slice(0, 10).map((sess: any, i: number) => {
              const isCurrent = sess.is_current;
              return (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10, backgroundColor: isCurrent ? (globalThis as any).__alphaColor(C.primary, '08') : C.bgSoft, borderWidth: 1, borderColor: isCurrent ? (globalThis as any).__alphaColor(C.primary, '25') : C.border }} data-testid={`session-${i}`} testID={`session-${i}`}>
                  <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: isCurrent ? (globalThis as any).__alphaColor(C.primary, '18') : C.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={sess.device_type === 'mobile' ? 'phone-portrait' : 'laptop'} size={16} color={isCurrent ? C.primary : C.textMuted} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{sess.ip_address || tx('securityDashboard.sessions.unknownIp', 'Unknown IP')}</Text>
                      {isCurrent && (
                        <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(C.success, '20') }}>
                          <Text style={{ color: C.successText, fontSize: 8, fontWeight: '800' }}>{tx('securityDashboard.sessions.current', 'CURRENT')}</Text>
                        </View>
                      )}
                    </View>
                    <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }}>{sess.user_agent?.slice(0, 50) || tx('securityDashboard.sessions.unknownDevice', 'Unknown device')}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: C.textMuted, fontSize: 9 }}>{sess.created_at?.slice(0, 16)?.replace('T', ' ') || '—'}</Text>
                    <Text style={{ color: C.textMuted, fontSize: 9, marginTop: 2 }}>{sess.expires_at ? `${tx('securityDashboard.sessions.expires', 'Expires:')} ${sess.expires_at.slice(5, 16).replace('T', ' ')}` : ''}</Text>
                  </View>
                </View>
              );
            })}
          </View>
        )}
      </View>

      {/* Login History */}
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border }} data-testid="login-history-card" testID="login-history-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
          <Ionicons name="time" size={18} color={C.cyan} />
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('securityDashboard.loginHistory.title', 'Login History')}</Text>
        </View>

        {history.length === 0 ? (
          <View style={{ padding: 20, alignItems: 'center' }}>
            <Text style={{ color: C.textMuted, fontSize: 12 }}>{tx('securityDashboard.loginHistory.none', 'No login history available')}</Text>
          </View>
        ) : (
          <View style={{ gap: 6 }}>
            {history.slice(0, 15).map((evt: any, i: number) => {
              const isSuccess = evt.event_type?.includes('success') || evt.type?.includes('success');
              const isFailed = evt.event_type?.includes('fail') || evt.type?.includes('fail');
              const evtColor = isSuccess ? C.success : isFailed ? C.error : C.warning;
              const evtIcon = isSuccess ? 'checkmark-circle' : isFailed ? 'close-circle' : 'alert-circle';
              const evtLabel = evt.event_type || evt.type || tx('securityDashboard.loginHistory.unknown', 'unknown');
              return (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: i < Math.min(history.length, 15) - 1 ? 1 : 0, borderBottomColor: C.border }} data-testid={`login-event-${i}`} testID={`login-event-${i}`}>
                  <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(evtColor, '15'), alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={evtIcon as any} size={14} color={evtColor} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{evtLabel.replace(/_/g, ' ')}</Text>
                    <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 1 }}>{evt.ip_address || ''} {evt.user_agent ? `- ${evt.user_agent.slice(0, 40)}` : ''}</Text>
                  </View>
                  <Text style={{ color: C.textMuted, fontSize: 9 }}>{(evt.timestamp || evt.created_at || '').slice(0, 16)?.replace('T', ' ')}</Text>
                </View>
              );
            })}
          </View>
        )}
      </View>

      {/* Alert Preferences */}
      {alertPrefs && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, marginTop: 16 }} data-testid="alert-preferences-card" testID="alert-preferences-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <Ionicons name="notifications" size={18} color={C.warningText} />
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('securityDashboard.alertPrefs.title', 'Alert Preferences')}</Text>
          </View>

          {/* Email Alerts */}
          <View style={{ marginBottom: 14 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
              <Ionicons name="mail" size={14} color={C.primary} />
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('securityDashboard.alertPrefs.emailAlerts', 'Email Alerts')}</Text>
            </View>
            <AlertToggle label={tx('securityDashboard.alertPrefs.newLoginDetected', 'New login detected')} pref="email_new_login" value={alertPrefs.email_new_login} onToggle={togglePref} />
            <AlertToggle label={tx('securityDashboard.alertPrefs.unrecognizedDevice', 'Unrecognized device')} pref="email_unrecognized_device" value={alertPrefs.email_unrecognized_device} onToggle={togglePref} />
            <AlertToggle label={tx('securityDashboard.alertPrefs.unrecognizedLocation', 'Unrecognized location')} pref="email_unrecognized_location" value={alertPrefs.email_unrecognized_location} onToggle={togglePref} />
            <AlertToggle label={tx('securityDashboard.alertPrefs.failedLoginAttempt', 'Failed login attempt')} pref="email_failed_login_attempt" value={alertPrefs.email_failed_login_attempt} onToggle={togglePref} />
            <AlertToggle label={tx('securityDashboard.alertPrefs.passwordChange', 'Password change')} pref="email_password_change" value={alertPrefs.email_password_change} onToggle={togglePref} />
            <AlertToggle label={tx('securityDashboard.alertPrefs.twoFaChange', '2FA settings change')} pref="email_2fa_change" value={alertPrefs.email_2fa_change} onToggle={togglePref} />
          </View>
        </View>
      )}

      {/* Known Devices */}
      {knownDevices.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, marginTop: 16 }} data-testid="known-devices-card" testID="known-devices-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="phone-portrait" size={18} color={C.purpleText} />
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('securityDashboard.knownDevices.title', 'Known Devices')}</Text>
            <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.purple, '20') }}>
              <Text style={{ color: C.purpleText, fontSize: 10, fontWeight: '800' }}>{knownDevices.length}</Text>
            </View>
          </View>
          <View style={{ gap: 8 }}>
            {knownDevices.map((dev: any, i: number) => (
              <View key={dev.device_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10, backgroundColor: dev.trusted ? (globalThis as any).__alphaColor(C.success, '08') : C.bgSoft, borderWidth: 1, borderColor: dev.trusted ? (globalThis as any).__alphaColor(C.success, '20') : C.border }} data-testid={`device-${i}`} testID={`device-${i}`}>
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: dev.device_type === 'mobile' ? (globalThis as any).__alphaColor(C.error, '18') : C.primary + '18', alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={dev.device_type === 'mobile' ? 'phone-portrait' : 'laptop'} size={16} color={dev.device_type === 'mobile' ? C.error : C.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{dev.ip_address}</Text>
                    {dev.trusted && (
                      <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(C.success, '20') }}>
                        <Text style={{ color: C.successText, fontSize: 8, fontWeight: '800' }}>{tx('securityDashboard.knownDevices.trusted', 'TRUSTED')}</Text>
                      </View>
                    )}
                  </View>
                  <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 1 }} numberOfLines={1}>{dev.user_agent?.slice(0, 50) || tx('securityDashboard.knownDevices.unknown', 'Unknown')}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 9, marginTop: 1 }}>{tx('securityDashboard.knownDevices.loginsLastWithValues', 'Logins: {logins} | Last: {last}').replace('{logins}', String(dev.login_count || 1)).replace('{last}', dev.last_seen?.slice(0, 16)?.replace('T', ' ') || '—')}</Text>
                </View>
                <View style={{ gap: 4 }}>
                  {!dev.trusted && (
                    <TouchableOpacity onPress={() => trustDevice(dev.device_id)} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.success, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '30') }} data-testid={`trust-device-${i}`} testID={`trust-device-${i}`}>
                      <Text style={{ color: C.successText, fontSize: 9, fontWeight: '700' }}>{tx('securityDashboard.knownDevices.actions.trust', 'Trust')}</Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity onPress={() => removeDevice(dev.device_id)} style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.error, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '30') }} data-testid={`remove-device-${i}`} testID={`remove-device-${i}`}>
                    <Text style={{ color: C.error, fontSize: 9, fontWeight: '700' }}>{tx('securityDashboard.knownDevices.actions.remove', 'Remove')}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Alert History */}
      {alertHistory.length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, marginTop: 16 }} data-testid="alert-history-card" testID="alert-history-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Ionicons name="megaphone" size={18} color={C.warningText} />
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '700' }}>{tx('securityDashboard.alertHistory.title', 'Alert History')}</Text>
          </View>
          <View style={{ gap: 6 }}>
            {alertHistory.slice(0, 10).map((a: any, i: number) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }} data-testid={`alert-${i}`} testID={`alert-${i}`}>
                <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: a.is_new_device ? (globalThis as any).__alphaColor(C.warning, '18') : C.primary + '18', alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={a.is_new_device ? 'warning' : 'notifications'} size={14} color={a.is_new_device ? C.warning : C.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>
                    {a.is_new_device ? tx('securityDashboard.alertHistory.newDeviceDetected', 'New device detected') : tx('securityDashboard.alertHistory.loginAlertSent', 'Login alert sent')}
                  </Text>
                  <Text style={{ color: C.textMuted, fontSize: 10 }}>{a.ip_address} {a.country !== 'Unknown' ? `(${a.country})` : ''}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 9 }}>{(a.alert_types || []).join(', ')}</Text>
                </View>
                <Text style={{ color: C.textMuted, fontSize: 9 }}>{a.timestamp?.slice(0, 16)?.replace('T', ' ')}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </View>
  );
}

function AlertToggle({ label, pref, value, onToggle }: { label: string; pref: string; value: boolean; onToggle: (key: string, value: boolean) => void }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border }}>
      <Text style={{ color: C.text, fontSize: 12 }}>{label}</Text>
      <Switch
        value={value}
        onValueChange={(newValue) => onToggle(pref, newValue)}
        trackColor={{ false: C.bgSoft, true: C.primary + '50' }}
        thumbColor={value ? C.primary : C.textMuted}
      />
    </View>
  );
}

function KpiPill({ label, value, color, testId }: { label: string; value: any; color: string; testId: string }) {
  return (
    <View style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '35'), backgroundColor: (globalThis as any).__alphaColor(color, '15') }} data-testid={testId} testID={testId}>
      <Text style={{ color, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' }} data-testid={`${testId}-label`} testID={`${testId}-label`}>{label}</Text>
      <Text style={{ color, fontSize: 12, fontWeight: '800' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{String(value ?? 0)}</Text>
    </View>
  );
}

function MetricChip({ label, value, color, testId }: { label: string; value: any; color: string; testId: string }) {
  return (
    <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '35'), backgroundColor: (globalThis as any).__alphaColor(color, '12'), flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid={testId} testID={testId}>
      <Text style={{ color, fontSize: 9, fontWeight: '700' }} data-testid={`${testId}-label`} testID={`${testId}-label`}>{label}</Text>
      <Text style={{ color, fontSize: 9, fontWeight: '900' }} data-testid={`${testId}-value`} testID={`${testId}-value`}>{String(value ?? 0)}</Text>
    </View>
  );
}

function ScorePill({ label, active }: { label: string; active: boolean }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: active ? (globalThis as any).__alphaColor(C.success, '15') : C.bgSoft, borderWidth: 1, borderColor: active ? (globalThis as any).__alphaColor(C.success, '30') : C.border }}>
      <Ionicons name={active ? 'checkmark-circle' : 'ellipse-outline'} size={10} color={active ? C.success : C.textMuted} />
      <Text style={{ color: active ? C.success : C.textMuted, fontSize: 9, fontWeight: '700' }}>{label}</Text>
    </View>
  );
}

function AuthRow({ label, enabled, icon }: { label: string; enabled: boolean; icon: string }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }}>
      <Ionicons name={icon as any} size={14} color={enabled ? C.purple : C.textMuted} />
      <Text style={{ color: C.text, fontSize: 12, flex: 1 }}>{label}</Text>
      <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: enabled ? (globalThis as any).__alphaColor(C.success, '18') : C.bgSoft }}>
        <Text style={{ color: enabled ? C.success : C.textMuted, fontSize: 9, fontWeight: '700' }}>{enabled ? 'ON' : 'OFF'}</Text>
      </View>
    </View>
  );
}
