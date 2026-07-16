import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import PlatformFinanceIntegrityPanel from './PlatformFinanceIntegrityPanel';
import { HeartbeatPulse } from '../common/HeartbeatPulse';
import { CIATrustScoreWidget } from './CIATrustScoreWidget';
import { useTranslation } from '../../hooks/useTranslation';
import { ResponsiveDataGrid } from './ResponsiveDataGrid';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { useHybridPolling } from '../../hooks/useHybridPolling';

function makeT(AC: any) { return {
  bg: AC.bg,
  bgSoft: AC.bgSoft,
  card: AC.card,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  textDim: AC.textDim || AC.textMuted,
  primary: AC.primary,
  success: AC.success,
  successText: AC.successText || AC.success,
  successSoft: AC.successSoft || `${AC.success}20`,
  warning: AC.warning,
  warningText: AC.warningText || AC.warning,
  warningSoft: AC.warningSoft || `${AC.warning}20`,
  error: AC.error,
  errorText: AC.errorText || AC.error,
  errorSoft: AC.errorSoft || `${AC.error}20`,
  purple: AC.purple,
  purpleText: AC.purpleText || AC.purple,
  cyan: AC.cyan || AC.info,
  teal: AC.teal || AC.cyan || AC.info,
  ai: AC.cyan || AC.info,
  orange: AC.orange,
  orangeText: AC.orangeText || AC.orange,
  pink: AC.pink || AC.purple,
  successBg: AC.successSoft || `${AC.success}20`,
  warningBg: AC.warningSoft || `${AC.warning}20`,
  errorBg: AC.errorSoft || `${AC.error}20`,
  cyanBg: `${(AC.cyan || AC.info)}20`,
}; }

// Module-scope fallback for grade/status helpers (they live outside the main component
// so they can't see the component-scoped `T = React.useMemo(() => makeT(AC), [AC])`).
const T = {
  bg: 'var(--app-bg)' as any,
  bgSoft: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  primaryText: 'var(--app-primary-text)' as any,
  success: 'var(--app-success)' as any,
  successBg: 'var(--app-success-soft)' as any,
  warning: 'var(--app-warning)' as any,
  warningBg: 'var(--app-warning-soft)' as any,
  error: 'var(--app-error)' as any,
  errorBg: 'var(--app-error-soft)' as any,
  cyan: 'var(--app-info)' as any,
  cyanBg: 'var(--app-info-soft)' as any,
  purple: 'var(--app-primary)' as any,
  teal: 'var(--app-primary)' as any,
};

const tx = (_key: string, fallback: string) => fallback;

const gradeColor = (g: string) => g === 'A' ? T.success : g === 'B' ? T.cyan : g === 'C' ? T.warning : T.error;
const statusColor = (s: string) => s === 'healthy' ? T.success : s === 'warning' ? T.warning : T.error;
const statusBg = (s: string) => s === 'healthy' ? T.successBg : s === 'warning' ? T.warningBg : T.errorBg;
const statusIcon = (s: string): string => s === 'healthy' ? 'checkmark-circle' : s === 'warning' ? 'alert-circle' : 'close-circle';

const RUNBOOK_SNAPSHOT_KEY = 'admin_gateway_status_snapshot_v1';
const RUNBOOK_EVENTS_KEY = 'admin_gateway_runbook_events_v1';

const normalizeGatewayRunbookStatus = (provider: string, cfg: any, fedapayHealth: string) => {
  if (provider === 'fedapay') {
    if (fedapayHealth === 'healthy') return 'live_ready';
    if (fedapayHealth === 'warning') return 'degraded';
    return 'unavailable';
  }

  const availabilityFlag = provider === 'stripe' ? Boolean(cfg?.stripe_available) : Boolean(cfg?.paypal_available);
  if (!availabilityFlag) return 'unavailable';

  const rawLabel = String(provider === 'stripe' ? cfg?.stripe_status_label : cfg?.paypal_status_label).toLowerCase();
  if (rawLabel.includes('live ready')) return 'live_ready';
  if (rawLabel.includes('unavailable')) return 'unavailable';
  if (rawLabel.includes('degraded') || rawLabel.includes('fallback')) return 'degraded';
  return 'degraded';
};

const normalizeIapRunbookStatus = (provider: 'apple' | 'google', iapReadiness: any) => {
  const p = iapReadiness?.providers?.[provider] || {};
  const state = String(p?.readiness_state || '').toLowerCase();
  if (state === 'live_ready') return 'live_ready';
  if (state === 'sandbox_ready' || state === 'test_ready') return 'degraded';
  return 'unavailable';
};

const gatewayRunbookSteps = (provider: string, targetStatus: string) => {
  if (provider === 'stripe') {
    return [
      'Verify STRIPE publishable/secret key pair and live-mode alignment.',
      'Run quick payment E2E smoke to validate checkout route + webhook delivery.',
      'If degraded persists, route card volume to PayPal/FedaPay until Stripe recovers.',
    ];
  }
  if (provider === 'paypal') {
    return [
      'Validate PAYPAL client credentials and live mode consistency.',
      'Run quick payment E2E smoke for redirect checkout + receipt chain.',
      'Temporarily prioritize Stripe for card flows while PayPal recovers.',
    ];
  }
  if (provider === 'apple') {
    return [
      'Run Apple IAP readiness probe and verify App Store Connect credential set.',
      'Validate app bundle + product mapping consistency for live environment.',
      'Route premium mobile upsell prompts through web fallback until Apple readiness recovers.',
    ];
  }
  if (provider === 'google') {
    return [
      'Run Google Play IAP readiness probe and verify service-account permissions.',
      'Validate package name + product identifiers for production tier.',
      'Route premium mobile upsell prompts through web fallback until Google readiness recovers.',
    ];
  }
  return [
    'Run FedaPay webhook resync + dead-letter replay action.',
    'Validate webhook URL integrity and queue dead/retry counts.',
    'Temporarily route mobile-heavy traffic through fallback card channels if needed.',
  ];
};

interface ScanResult {
  score: number;
  grade: string;
  scan_time: number;
  scanned_at: string;
  stale_urls: { count: number; issues: any[] };
  build: { status: string; age_hours: number; build_time: string; stale: boolean; message: string; source_newer_than_build?: boolean; stale_domains_in_build?: boolean };
  caches: { label: string; exists: boolean; size_mb: number; age_hours: number; status: string; stale: boolean }[];
  env: { status: string; frontend_url: string; issues: any[] };
  categories: Record<string, { status: string; count?: number }>;
  total_issues: number;
  fixable_issues: number;
}

interface FixResult {
  status: string;
  fix_time: number;
  actions: { action: string; fixed_count?: number; fixed_files?: string[]; cleared?: string[]; status?: string; message?: string }[];
  before: { stale_urls: number; stale_caches: number; build_stale: boolean };
  after: { stale_urls: number; rebuild: string };
}

export default function PlatformHealthPanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [fixResult, setFixResult] = useState<FixResult | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [fedapayActionRunning, setFedapayActionRunning] = useState(false);
  const [fedapayActionResult, setFedapayActionResult] = useState<any | null>(null);
  const [fedapayStatusCheckedAt, setFedapayStatusCheckedAt] = useState(Date.now());
  const [fedapayStatusHeartbeatSec, setFedapayStatusHeartbeatSec] = useState(0);
  const [gatewayRunbooks, setGatewayRunbooks] = useState<any[]>([]);
  const [runbookActionBusy, setRunbookActionBusy] = useState(false);
  const [runbookActionMessage, setRunbookActionMessage] = useState('');
  const [gatewayRetryAtMs, setGatewayRetryAtMs] = useState(0);
  const [realtimeTelemetryCheckedAt, setRealtimeTelemetryCheckedAt] = useState(Date.now());
  const [realtimeTelemetryHeartbeatSec, setRealtimeTelemetryHeartbeatSec] = useState(0);
  const [ssoValidation, setSsoValidation] = useState<any>(null);
  const [ssoValidationLoading, setSsoValidationLoading] = useState(false);
  const [policyGateRecoveryRunning, setPolicyGateRecoveryRunning] = useState(false);
  const [policyGateRecoveryResult, setPolicyGateRecoveryResult] = useState<any>(null);
  const runbookBootstrapRef = useRef(false);
  const panelTitle = t('platformHealth.header.title');

  // Live services data with auto-refresh
  const { data: liveServices, loading: liveLoading } = useLiveQuery(
    '/admin/platform-health/live-services',
    { entity: 'platform-health-live', pollInterval: 60000 }
  );

  const {
    data: fedapayIntegrity,
    loading: fedapayIntegrityLoading,
    refetch: refetchFedapayIntegrity,
  } = useLiveQuery(
    '/admin/platform-health/fedapay-webhook-integrity',
    { entity: 'fedapay-webhook-integrity', pollInterval: 90000 }
  );

  const {
    data: gatewayConfig,
    loading: gatewayConfigLoading,
    refetch: refetchGatewayConfig,
  } = useLiveQuery(
    '/subscriptions/gateway-config',
    { entity: 'payment-gateway-config', pollInterval: 90000 }
  );

  const {
    data: iapReadiness,
    loading: iapReadinessLoading,
    refetch: refetchIapReadiness,
  } = useLiveQuery(
    '/iap/readiness',
    { entity: 'iap-readiness-config', pollInterval: 90000 }
  );

  const gatewayRefreshCooldownSec = Math.max(0, Math.ceil((gatewayRetryAtMs - Date.now()) / 1000));

  const safeRefetchGatewayConfig = useCallback(async () => {
    if (Date.now() < gatewayRetryAtMs) {
      setRunbookActionMessage(`Gateway refresh cooling down (${gatewayRefreshCooldownSec}s) to avoid 429 storms.`);
      return;
    }

    try {
      await refetchGatewayConfig();
      setRunbookActionMessage('Gateway status refreshed.');
    } catch (error: any) {
      if (error?.response?.status === 429) {
        setGatewayRetryAtMs(Date.now() + 30000);
        setRunbookActionMessage('Gateway refresh rate-limited (429). Backing off for 30s.');
        return;
      }
      setRunbookActionMessage(error?.response?.data?.detail || 'Gateway refresh failed.');
    }
  }, [gatewayRetryAtMs, gatewayRefreshCooldownSec, refetchGatewayConfig]);

  const runSsoE2EValidation = useCallback(async () => {
    if (ssoValidationLoading) return;
    setSsoValidationLoading(true);
    try {
      const response = await api.post('/auth/admin/sso-validate-e2e', {});
      setSsoValidation(response?.data || null);
    } catch (error: any) {
      setSsoValidation({
        passed: false,
        severity: 'warning',
        validated_at: new Date().toISOString(),
        checks: [{ name: 'request_failed', passed: false, details: error?.response?.data?.detail || 'Validation request failed' }],
      });
    }
    setSsoValidationLoading(false);
  }, [ssoValidationLoading]);

  const runPolicyGateRecovery = useCallback(async () => {
    if (policyGateRecoveryRunning) return;
    setPolicyGateRecoveryRunning(true);
    try {
      const response = await api.post('/admin/security/policy-gate/recover-prerequisites', {});
      setPolicyGateRecoveryResult(response?.data || null);
      await runSsoE2EValidation();
    } catch (error: any) {
      setPolicyGateRecoveryResult({
        ok: false,
        recovery_success: false,
        message: error?.response?.data?.message || error?.response?.data?.detail || 'Prerequisite recovery failed',
        before: null,
        after: null,
        actions: [],
      });
    }
    setPolicyGateRecoveryRunning(false);
  }, [policyGateRecoveryRunning, runSsoE2EValidation]);

  const runScan = useCallback(async () => {
    setScanning(true);
    setFixResult(null);
    try {
      const { data } = await api.get('/admin/platform-health/scan');
      setScan(data);
    } catch { /* ignore */ }
    setScanning(false);
  }, []);

  // Auto-scan on mount
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { runScan(); }, []);

  const runAutoFix = useCallback(async () => {
    setFixing(true);
    try {
      const { data } = await api.post('/admin/platform-health/auto-fix');
      setFixResult(data);
      const { data: newScan } = await api.get('/admin/platform-health/scan');
      setScan(newScan);
    } catch { /* ignore */ }
    setFixing(false);
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const { data } = await api.get('/admin/platform-health/history?limit=10');
      setHistory(data.scans || []);
      setShowHistory(true);
    } catch { /* ignore */ }
  }, []);

  const runFedapayResyncReplay = useCallback(async () => {
    setFedapayActionRunning(true);
    setFedapayActionResult(null);
    try {
      const { data } = await api.post('/admin/platform-health/fedapay-webhook-resync-replay?limit=30');
      setFedapayActionResult(data);
      await refetchFedapayIntegrity();
    } catch (error: any) {
      setFedapayActionResult({
        ok: false,
        message: error?.response?.data?.detail || 'Failed to execute recovery action',
      });
    }
    setFedapayActionRunning(false);
  }, [refetchFedapayIntegrity]);

  const ls = liveServices || {};
  const fwi = fedapayIntegrity || {};
  const email = ls.email || {};
  const push = ls.push || {};
  const notifs = ls.notifications || {};
  const sched = ls.scheduler || {};
  const rt = ls.realtime || {};
  const rtBackoff = rt.adaptive_backoff || {};
  const rtLatestEvent = rt.latest_event || {};
  const rtHealthStatus = String(rt.reconnect_health_status || 'healthy');

  const safeAutoFix = useCallback(async (entry: any, source: 'auto' | 'manual' = 'manual') => {
    try {
      await api.post('/admin/live-activity/log-event', {
        event_type: 'admin_action',
        detail: `gateway_readiness_drop_${entry.provider}`,
        metadata: {
          source,
          provider: entry.provider,
          from: entry.from,
          to: entry.to,
          severity: entry.severity,
        },
      });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformHealthPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

    try {
      await api.post('/admin/notifications/test-push', {
        severity: entry.severity === 'critical' ? 'critical' : 'warning',
        title: `Gateway readiness drop: ${String(entry.provider).toUpperCase()}`,
        message: `${String(entry.provider).toUpperCase()} shifted ${String(entry.from).toUpperCase()} → ${String(entry.to).toUpperCase()}. Safe-Auto-Fix engaged.`,
      });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformHealthPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

    try {
      if (entry.provider === 'fedapay') {
        await runFedapayResyncReplay();
      } else {
        await api.post('/admin/payment-analytics/subscriptions/payment-e2e/run?full_suite=false');
      }

      await refetchGatewayConfig();
      await refetchFedapayIntegrity();
      await refetchIapReadiness();

      setGatewayRunbooks((prev) => {
        const next = prev.map((item) => (item.id === entry.id ? { ...item, remediation_applied: true, acknowledged: true, auto_triggered: source === 'auto' } : item));
        if (typeof window !== 'undefined') {
          try {
            window.localStorage.setItem(RUNBOOK_EVENTS_KEY, JSON.stringify(next));
          } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformHealthPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        }
        return next;
      });
    } catch (error: any) {
      setRunbookActionMessage(error?.response?.data?.detail || 'Safe-Auto-Fix skipped due current security gate state.');
    }
  }, [refetchGatewayConfig, refetchFedapayIntegrity, refetchIapReadiness, runFedapayResyncReplay]);
  const unifiedReadinessRows = [
    {
      provider: 'stripe',
      label: 'Stripe',
      state: normalizeGatewayRunbookStatus('stripe', gatewayConfig, fwi.health_status || 'unknown'),
      status_label: gatewayConfig?.stripe_status_label || 'Unavailable',
    },
    {
      provider: 'paypal',
      label: 'PayPal',
      state: normalizeGatewayRunbookStatus('paypal', gatewayConfig, fwi.health_status || 'unknown'),
      status_label: gatewayConfig?.paypal_status_label || 'Unavailable',
    },
    {
      provider: 'fedapay',
      label: 'FedaPay',
      state: normalizeGatewayRunbookStatus('fedapay', gatewayConfig, fwi.health_status || 'unknown'),
      status_label: (fwi.health_status || 'unknown') === 'healthy' ? 'Live Ready' : (fwi.health_status || 'unknown') === 'warning' ? 'Degraded' : 'Unavailable',
    },
    {
      provider: 'apple',
      label: 'Apple IAP',
      state: normalizeIapRunbookStatus('apple', iapReadiness),
      status_label: iapReadiness?.providers?.apple?.status_label || 'Unavailable',
    },
    {
      provider: 'google',
      label: 'Google IAP',
      state: normalizeIapRunbookStatus('google', iapReadiness),
      status_label: iapReadiness?.providers?.google?.status_label || 'Unavailable',
    },
  ];

  useEffect(() => {
    if (runbookBootstrapRef.current) return;
    runbookBootstrapRef.current = true;
    if (typeof window === 'undefined') return;
    try {
      const stored = window.localStorage.getItem(RUNBOOK_EVENTS_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) setGatewayRunbooks(parsed.slice(0, 16));
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformHealthPanel.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/platform-health/sso-validation-hybrid',
    onTick: runSsoE2EValidation,
    runOnMount: true,
    slowIntervalMs: 600000,
    fastIntervalMs: 300000,
  });

  useEffect(() => {
    if (!gatewayConfig || !iapReadiness) return;

    const currentSnapshot = {
      stripe: normalizeGatewayRunbookStatus('stripe', gatewayConfig, fwi.health_status || 'unknown'),
      paypal: normalizeGatewayRunbookStatus('paypal', gatewayConfig, fwi.health_status || 'unknown'),
      fedapay: normalizeGatewayRunbookStatus('fedapay', gatewayConfig, fwi.health_status || 'unknown'),
      apple: normalizeIapRunbookStatus('apple', iapReadiness),
      google: normalizeIapRunbookStatus('google', iapReadiness),
      captured_at: new Date().toISOString(),
    };

    if (typeof window === 'undefined') return;

    const readPreviousSnapshot = () => {
      try {
        const raw = window.localStorage.getItem(RUNBOOK_SNAPSHOT_KEY);
        return raw ? JSON.parse(raw) : null;
      } catch {
        return null;
      }
    };

    const previous = readPreviousSnapshot();
    if (previous) {
      const shifts = ['stripe', 'paypal', 'fedapay', 'apple', 'google']
        .map((provider) => ({
          provider,
          from: String(previous?.[provider] || 'unknown'),
          to: String((currentSnapshot as any)[provider] || 'unknown'),
        }))
        .filter((entry) => entry.from === 'live_ready' && (entry.to === 'degraded' || entry.to === 'unavailable'));

      if (shifts.length) {
        const generated = shifts.map((shift) => ({
          id: `${Date.now()}-${shift.provider}-${Math.random().toString(36).slice(2, 6)}`,
          provider: shift.provider,
          from: shift.from,
          to: shift.to,
          created_at: new Date().toISOString(),
          severity: shift.to === 'unavailable' ? 'critical' : 'warning',
          acknowledged: false,
          remediation_applied: false,
          steps: gatewayRunbookSteps(shift.provider, shift.to),
        }));

        setGatewayRunbooks((prev) => {
          const next = [...generated, ...prev].slice(0, 16);
          try {
            window.localStorage.setItem(RUNBOOK_EVENTS_KEY, JSON.stringify(next));
          } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformHealthPanel.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
          return next;
        });

        generated.forEach((entry) => {
          void safeAutoFix(entry, 'auto');
        });
      }
    }

    try {
      window.localStorage.setItem(RUNBOOK_SNAPSHOT_KEY, JSON.stringify(currentSnapshot));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformHealthPanel.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [gatewayConfig, fwi.health_status, iapReadiness, safeAutoFix]);

  const acknowledgeRunbook = useCallback((id: string) => {
    setGatewayRunbooks((prev) => {
      const next = prev.map((entry) => (entry.id === id ? { ...entry, acknowledged: true } : entry));
      if (typeof window !== 'undefined') {
        try {
          window.localStorage.setItem(RUNBOOK_EVENTS_KEY, JSON.stringify(next));
        } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformHealthPanel.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }
      return next;
    });
  }, []);

  const applyRunbook = useCallback(async (entry: any) => {
    setRunbookActionBusy(true);
    setRunbookActionMessage('');
    try {
      await safeAutoFix(entry, 'manual');
      setRunbookActionMessage(`Runbook applied for ${String(entry.provider).toUpperCase()} — verification cycle triggered.`);
    } catch (error: any) {
      if (error?.response?.status === 429) {
        setGatewayRetryAtMs(Date.now() + 30000);
        setRunbookActionMessage('Runbook call hit rate limit (429). Cooldown enabled for 30s before retry.');
        setRunbookActionBusy(false);
        return;
      }
      setRunbookActionMessage(error?.response?.data?.detail || 'Runbook action failed. Please review gateway logs.');
    }
    setRunbookActionBusy(false);
  }, [safeAutoFix]);

  useEffect(() => {
    setFedapayStatusCheckedAt(Date.now());
  }, [fwi.health_status, fwi.latest_sync?.created_at, fwi.queue_state?.dead, fwi.queue_state?.retry_or_dead_last_30m]);

  useEffect(() => {
    setRealtimeTelemetryCheckedAt(Date.now());
  }, [rt.connect_attempts_30m, rt.disconnected_30m, rt.errors_30m, rt.connect_success_rate_30m, rtBackoff.current_ms, rtLatestEvent.timestamp]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      setFedapayStatusHeartbeatSec(Math.max(0, Math.floor((Date.now() - fedapayStatusCheckedAt) / 1000)));
    }, 1000);
    return () => clearInterval(intervalId);
  }, [fedapayStatusCheckedAt]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      setRealtimeTelemetryHeartbeatSec(Math.max(0, Math.floor((Date.now() - realtimeTelemetryCheckedAt) / 1000)));
    }, 1000);
    return () => clearInterval(intervalId);
  }, [realtimeTelemetryCheckedAt]);

  const ScoreRing = ({ score, grade }: { score: number; grade: string }) => {
    const gc = gradeColor(grade);
    const circumference = 2 * Math.PI * 44;
    const offset = circumference - (score / 100) * circumference;
    return (
      <View style={{ alignItems: 'center', justifyContent: 'center', width: 100, height: 100 }} data-testid="health-score-ring" testID="health-score-ring">
        <svg width="100" height="100" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="44" fill="none" stroke={T.border} strokeWidth="6" />
          <circle cx="50" cy="50" r="44" fill="none" stroke={gc} strokeWidth="6" strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={offset}
            transform="rotate(-90 50 50)" style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
        </svg>
        <View style={{ position: 'absolute', alignItems: 'center' }}>
          <Text style={{ fontSize: 26, fontWeight: '900', color: gc }}>{score}</Text>
          <Text style={{ fontSize: 9, fontWeight: '700', color: T.textMuted, marginTop: -2 }}>{grade}</Text>
        </View>
      </View>
    );
  };

  const ServiceCard = ({ icon, label, value, sub, color, status }: { icon: string; label: string; value: string | number; sub: string; color: string; status?: string }) => (
    <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, flex: 1, minWidth: 155 }} data-testid={`service-${label.toLowerCase().replace(/\s/g, '-')}`} testID={`service-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={15} color={color} />
        </View>
        <Text style={{ fontSize: 12, fontWeight: '600', color: T.textSec, flex: 1 }}>{label}</Text>
        {status && (
          <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: status === 'ok' ? T.success : T.warning }} />
        )}
      </View>
      <Text style={{ fontSize: 22, fontWeight: '800', color: T.text }}>{value}</Text>
      <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>{sub}</Text>
    </View>
  );

  const CategoryCard = ({ id, label, icon, status, detail }: { id: string; label: string; icon: string; status: string; detail: string }) => (
    <TouchableOpacity
      onPress={() => setExpanded(expanded === id ? null : id)}
      style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: expanded === id ? (globalThis as any).__alphaColor(statusColor(status), '60') : T.border, flex: 1, minWidth: 200 }}
      data-testid={`health-category-${id}`} testID={`health-category-${id}`}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: statusBg(status), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={16} color={statusColor(status)} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{label}</Text>
          <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{detail}</Text>
        </View>
        <Ionicons name={expanded === id ? 'chevron-up' : 'chevron-down'} size={14} color={T.textMuted} />
      </View>
    </TouchableOpacity>
  );

  // Loading state
  if (scanning && !scan) {
    return (
      <View data-testid="platform-health-scanning" testID="platform-health-scanning" style={{ padding: 40, alignItems: 'center' }}>
        <ActivityIndicator size="large" color={T.cyan} />
        <Text style={{ fontSize: 14, color: T.textSec, marginTop: 16 }}>{tx('platformHealth.states.scanning', 'Scanning platform health...')}</Text>
      </View>
    );
  }

  return (
    <View data-testid="platform-health-panel" testID="platform-health-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }}>{panelTitle === 'platformHealth.header.title' ? 'Platform Health' : panelTitle}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.success, '18') }}>
              <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: T.success }} />
              <Text style={{ fontSize: 10, fontWeight: '600', color: T.successText }}>{tx('admin.platformHealthPanel.auto.text.001', 'LIVE')}</Text>
            </View>
          </View>
          {scan && (
            <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>
              Last scan: {new Date(scan.scanned_at).toLocaleString()} ({scan.scan_time}s)
            </Text>
          )}
        </View>
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <TouchableOpacity onPress={runScan} disabled={scanning} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border }} data-testid="rescan-btn" testID="rescan-btn">
            <Ionicons name="refresh" size={14} color={T.cyan} />
            <Text style={{ fontSize: 12, fontWeight: '600', color: T.cyan }}>{scanning ? tx('platformHealth.actions.scanning', 'Scanning...') : tx('platformHealth.actions.reScan', 'Re-Scan')}</Text>
          </TouchableOpacity>
          {scan && scan.fixable_issues > 0 && (
            <TouchableOpacity onPress={runAutoFix} disabled={fixing} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: fixing ? T.bgSoft : T.success }} data-testid="auto-fix-btn" testID="auto-fix-btn">
              <Ionicons name={fixing ? 'hourglass' : 'hammer'} size={14} color={colors.primaryText} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>{fixing ? tx('platformHealth.actions.fixing', 'Fixing...') : tx('platformHealth.actions.autoFixCount', 'Auto-Fix ({count})').replace('{count}', String(scan.fixable_issues))}</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={loadHistory} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border }} data-testid="history-btn" testID="history-btn">
            <Ionicons name="time" size={14} color={T.textSec} />
            <Text style={{ fontSize: 12, fontWeight: '600', color: T.textSec }}>{tx('platformHealth.actions.history', 'History')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Fix Result Banner */}
      {fixResult && (
        <View style={{ backgroundColor: fixResult.after.stale_urls === 0 ? T.successBg : T.warningBg, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: fixResult.after.stale_urls === 0 ? (globalThis as any).__alphaColor(T.success, '30') : T.warning + '30' }} data-testid="fix-result-banner" testID="fix-result-banner">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name={fixResult.after.stale_urls === 0 ? 'checkmark-circle' : 'alert-circle'} size={18} color={fixResult.after.stale_urls === 0 ? T.success : T.warning} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>Auto-Fix Complete ({fixResult.fix_time}s)</Text>
          </View>
          {fixResult.actions.map((a, i) => (
            <Text key={i} style={{ fontSize: 11, color: T.textSec, marginTop: 4, marginLeft: 26 }}>
              {a.action === 'fix_stale_urls' ? `Fixed ${a.fixed_count} stale URL files` : a.action === 'clear_caches' ? `Cleared: ${(a.cleared || []).join(', ')}` : a.action === 'rebuild' ? `Rebuild: ${a.status} - ${a.message || ''}` : a.action}
            </Text>
          ))}
        </View>
      )}

      <CIATrustScoreWidget />

      {/* Live Services Grid */}
      <View style={{ marginBottom: 16 }}>
        <Text style={{ fontSize: 13, fontWeight: '700', color: T.textSec, marginBottom: 10, letterSpacing: 0.5 }}>{tx('admin.platformHealthPanel.auto.text.002', 'LIVE SERVICES')}</Text>
        {liveLoading && !liveServices ? (
          <View style={{ padding: 20, alignItems: 'center' }}>
            <ActivityIndicator size="small" color={T.cyan} />
          </View>
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <ServiceCard
              icon="mail" label="Email" color={T.cyan}
              value={email.total_sent?.toLocaleString() || '0'}
              sub={`${email.success_rate || 0}% delivered · ${email.last_hour || 0} last hour`}
              status={email.success_rate >= 95 ? 'ok' : 'warn'}
            />
            <ServiceCard
              icon="notifications" label="Notifications" color={T.purpleText}
              value={notifs.total?.toLocaleString() || '0'}
              sub={`${notifs.unread || 0} unread · ${notifs.today || 0} today`}
              status="ok"
            />
            <ServiceCard
              icon="phone-portrait" label="Push" color={T.teal}
              value={push.subscribers || 0}
              sub={push.configured ? 'VAPID configured' : 'Not configured'}
              status={push.configured ? 'ok' : 'warn'}
            />
            <ServiceCard
              icon="pulse" label="Scheduler" color={T.warningText}
              value={`${sched.rules_enabled || 0}/${sched.rules_total || 0}`}
              sub={`${sched.heartbeats_healthy || 0}/${sched.heartbeats_total || 0} heartbeats healthy`}
              status={sched.heartbeats_healthy >= sched.heartbeats_total ? 'ok' : 'warn'}
            />
            <ServiceCard
              icon="radio" label="WebSocket" color={T.successText}
              value={rt.ws_connections || 0}
              sub={`${rt.active_sessions || 0} active sessions · ${rt.connect_success_rate_30m || 100}% success (30m)`}
              status={rtHealthStatus === 'healthy' ? 'ok' : 'warn'}
            />
            {ls.uptime_hours !== undefined && (
              <ServiceCard
                icon="time" label="Uptime" color={T.primary}
                value={`${ls.uptime_hours}h`}
                sub="Backend process"
                status="ok"
              />
            )}
          </View>
        )}
      </View>

      {/* Realtime Connection Telemetry + Adaptive Backoff */}
      <View style={{ marginBottom: 16 }} data-testid="realtime-connection-telemetry-section" testID="realtime-connection-telemetry-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: '700', color: T.textSec, letterSpacing: 0.5 }} data-testid="realtime-connection-telemetry-title" testID="realtime-connection-telemetry-title">{tx('admin.platformHealthPanel.auto.text.003', 'REALTIME CONNECTION TELEMETRY')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <HeartbeatPulse
              tick={realtimeTelemetryHeartbeatSec}
              warningAfterSeconds={70}
              criticalAfterSeconds={140}
              dataTestId="realtime-connection-telemetry-heartbeat"
              testID="realtime-connection-telemetry-heartbeat"
            >
              <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>
                {realtimeTelemetryHeartbeatSec >= 140 ? 'Critical stale' : realtimeTelemetryHeartbeatSec >= 70 ? 'Stale' : 'Last telemetry'} {realtimeTelemetryHeartbeatSec}s ago
              </Text>
            </HeartbeatPulse>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: statusBg(rtHealthStatus) }} data-testid="realtime-connection-telemetry-status-pill" testID="realtime-connection-telemetry-status-pill">
              <Text style={{ fontSize: 10, fontWeight: '700', color: statusColor(rtHealthStatus) }}>{rtHealthStatus.toUpperCase()}</Text>
            </View>
          </View>
        </View>

        <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }} data-testid="realtime-connection-telemetry-card" testID="realtime-connection-telemetry-card">
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 10 }} data-testid="realtime-connection-telemetry-description" testID="realtime-connection-telemetry-description">{tx('admin.platformHealthPanel.auto.text.004', 'Shows websocket reconnect reliability and adaptive backoff behavior from live browser telemetry.')}</Text>

          <View style={{ gap: 4 }}>
            <Row label="Connect Attempts (30m)" value={String(rt.connect_attempts_30m || 0)} testId="realtime-connect-attempts-30m" />
            <Row label="Connected Events (30m)" value={String(rt.connected_30m || 0)} testId="realtime-connected-30m" />
            <Row label="Disconnect Events (30m)" value={String(rt.disconnected_30m || 0)} color={(rt.disconnected_30m || 0) >= 6 ? T.warning : T.success} testId="realtime-disconnected-30m" />
            <Row label="Error Events (30m)" value={String(rt.errors_30m || 0)} color={(rt.errors_30m || 0) >= 5 ? T.warning : T.success} testId="realtime-errors-30m" />
            <Row label="Reconnect Success Rate" value={`${rt.connect_success_rate_30m || 100}%`} color={(rt.connect_success_rate_30m || 100) < 85 ? T.warning : T.success} testId="realtime-success-rate-30m" />
            <Row label="Adaptive Backoff (Current)" value={`${rtBackoff.current_ms || 0} ms`} color={(rtBackoff.current_ms || 0) >= 20000 ? T.warning : T.success} testId="realtime-backoff-current" />
            <Row label="Adaptive Backoff (Avg/30m)" value={`${rtBackoff.avg_ms_30m || 0} ms`} testId="realtime-backoff-avg-30m" />
            <Row label="Adaptive Backoff (Max/30m)" value={`${rtBackoff.max_ms_30m || 0} ms`} color={(rtBackoff.max_ms_30m || 0) >= 45000 ? T.error : T.text} testId="realtime-backoff-max-30m" />
            <Row label="Consecutive Failures (Latest)" value={String(rtLatestEvent.consecutive_failures || 0)} color={(rtLatestEvent.consecutive_failures || 0) >= 4 ? T.warning : T.success} testId="realtime-consecutive-failures-latest" />
            <Row label="Latest Event" value={`${String(rtLatestEvent.event_type || 'none')} ${rtLatestEvent.timestamp ? `· ${new Date(rtLatestEvent.timestamp).toLocaleString()}` : ''}`.trim()} testId="realtime-latest-event" />
            <Row label="Latest Close Code" value={String(rtLatestEvent.close_code || 'N/A')} testId="realtime-latest-close-code" />
            <Row label="Latest Close Reason" value={String(rtLatestEvent.close_reason || 'N/A')} testId="realtime-latest-close-reason" />
          </View>
        </View>
      </View>

      {/* FedaPay Webhook Integrity */}
      <View style={{ marginBottom: 16 }} data-testid="fedapay-webhook-integrity-section" testID="fedapay-webhook-integrity-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: '700', color: T.textSec, letterSpacing: 0.5 }} data-testid="fedapay-webhook-integrity-title" testID="fedapay-webhook-integrity-title">{tx('admin.platformHealthPanel.auto.text.005', 'FEDAPAY WEBHOOK INTEGRITY')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={runFedapayResyncReplay}
              disabled={fedapayActionRunning}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: fedapayActionRunning ? T.bgSoft : T.warning, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(fedapayActionRunning ? T.border : T.warning, '66') }}
              data-testid="fedapay-webhook-resync-replay-button" testID="fedapay-webhook-resync-replay-button"
            >
              {fedapayActionRunning ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="construct" size={12} color={colors.primaryText} />}
              <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryText }}>{fedapayActionRunning ? 'Running...' : 'Resync + Replay Dead'}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={refetchFedapayIntegrity}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border }}
              data-testid="fedapay-webhook-integrity-refresh-button" testID="fedapay-webhook-integrity-refresh-button"
            >
              <Ionicons name="refresh" size={12} color={T.textSec} />
              <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec }}>{fedapayIntegrityLoading ? 'Refreshing...' : 'Refresh'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }} data-testid="fedapay-webhook-integrity-card" testID="fedapay-webhook-integrity-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="git-network" size={16} color={statusColor(fwi.health_status || 'warning')} />
              <Text style={{ fontSize: 12, fontWeight: '700', color: T.text }} data-testid="fedapay-webhook-integrity-status-text" testID="fedapay-webhook-integrity-status-text">
                Status: {(fwi.health_status || 'unknown').toUpperCase()}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <HeartbeatPulse
                tick={fedapayStatusHeartbeatSec}
                warningAfterSeconds={60}
                criticalAfterSeconds={120}
                dataTestId="fedapay-webhook-integrity-heartbeat"
                testID="fedapay-webhook-integrity-heartbeat"
              >
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700' }}>
                  {fedapayStatusHeartbeatSec >= 120 ? 'Critical stale' : fedapayStatusHeartbeatSec >= 60 ? 'Stale' : 'Last checked'} {fedapayStatusHeartbeatSec}s ago
                </Text>
              </HeartbeatPulse>
              <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: statusBg(fwi.health_status || 'warning') }} data-testid="fedapay-webhook-integrity-status-pill" testID="fedapay-webhook-integrity-status-pill">
                <Text style={{ fontSize: 10, fontWeight: '700', color: statusColor(fwi.health_status || 'warning') }}>{fwi.health_status || 'unknown'}</Text>
              </View>
            </View>
          </View>

          <View style={{ marginTop: 10, gap: 6 }}>
            <Row label="Expected URL" value={fwi.expected_webhook_url || 'N/A'} testId="fedapay-webhook-expected-url" />
            <Row label="Retry/Dead (30m)" value={String(fwi.queue_state?.retry_or_dead_last_30m || 0)} color={(fwi.queue_state?.retry_or_dead_last_30m || 0) >= 3 ? T.warning : T.success} testId="fedapay-webhook-retry-dead-30m" />
            <Row label="Dead Queue" value={String(fwi.queue_state?.dead || 0)} color={(fwi.queue_state?.dead || 0) > 0 ? T.error : T.success} testId="fedapay-webhook-dead-queue" />
            <Row label="Processed (24h)" value={String(fwi.queue_state?.processed_last_24h || 0)} testId="fedapay-webhook-processed-24h" />
            <Row label="Last Sync" value={fwi.latest_sync?.created_at ? new Date(fwi.latest_sync.created_at).toLocaleString() : 'N/A'} testId="fedapay-webhook-last-sync" />
            <Row label="Sync Action" value={fwi.latest_sync?.sync_result?.action || 'none'} testId="fedapay-webhook-sync-action" />
          </View>

          {(fwi.recent_failures || []).length > 0 && (
            <View style={{ marginTop: 10, borderTopWidth: 1, borderTopColor: T.border, paddingTop: 10 }} data-testid="fedapay-webhook-recent-failures" testID="fedapay-webhook-recent-failures">
              <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec, marginBottom: 6 }}>{tx('admin.platformHealthPanel.auto.text.006', 'Recent Failures')}</Text>
              {(fwi.recent_failures || []).slice(0, 3).map((item: any, idx: number) => (
                <Text key={idx} style={{ fontSize: 10, color: T.textMuted, marginBottom: 3 }} data-testid={`fedapay-webhook-failure-${idx}`} testID={`fedapay-webhook-failure-${idx}`}>
                  {item.status} · attempts {item.attempts || 0} · {(item.last_error || 'no error').slice(0, 110)}
                </Text>
              ))}
            </View>
          )}
        </View>

        {fedapayActionResult && (
          <View
            style={{ marginTop: 10, backgroundColor: fedapayActionResult.ok ? T.successBg : T.errorBg, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: fedapayActionResult.ok ? (globalThis as any).__alphaColor(T.success, '44') : T.error + '44' }}
            data-testid="fedapay-webhook-resync-replay-result" testID="fedapay-webhook-resync-replay-result"
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: fedapayActionResult.ok ? T.success : T.error }} data-testid="fedapay-webhook-resync-replay-result-title" testID="fedapay-webhook-resync-replay-result-title">
              {fedapayActionResult.ok ? 'Recovery Action Completed' : 'Recovery Action Failed'}
            </Text>
            <Text style={{ fontSize: 10, color: T.textSec, marginTop: 4 }} data-testid="fedapay-webhook-resync-replay-result-message" testID="fedapay-webhook-resync-replay-result-message">
              {fedapayActionResult.message || 'No message'}
            </Text>
            {fedapayActionResult.ok && (
              <View style={{ marginTop: 6, gap: 2 }}>
                <Row label="Sync Action" value={fedapayActionResult.sync_result?.action || 'none'} testId="fedapay-webhook-resync-sync-action" />
                <Row label="Promoted Dead" value={String(fedapayActionResult.dead_replay_result?.promoted_to_retry || 0)} testId="fedapay-webhook-resync-promoted-dead" />
                <Row label="Processed" value={String(fedapayActionResult.dead_replay_result?.processed || 0)} testId="fedapay-webhook-resync-processed" />
                <Row label="Dead Remaining" value={String(fedapayActionResult.queue_state?.dead || 0)} color={(fedapayActionResult.queue_state?.dead || 0) > 0 ? T.warning : T.success} testId="fedapay-webhook-resync-dead-remaining" />
              </View>
            )}
          </View>
        )}
      </View>

      {/* Unified Cross-Channel Readiness Board */}
      <View style={{ marginBottom: 16 }} data-testid="unified-readiness-board-section" testID="unified-readiness-board-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: '700', color: T.textSec, letterSpacing: 0.5 }} data-testid="unified-readiness-board-title" testID="unified-readiness-board-title">{tx('admin.platformHealthPanel.auto.text.007', 'UNIFIED CROSS-CHANNEL READINESS BOARD')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: (gatewayConfigLoading || iapReadinessLoading) ? T.warningBg : T.successBg }} data-testid="safe-auto-fix-engine-pill" testID="safe-auto-fix-engine-pill">
              <Text style={{ fontSize: 10, fontWeight: '700', color: (gatewayConfigLoading || iapReadinessLoading) ? T.warning : T.success }}>
                {(gatewayConfigLoading || iapReadinessLoading) ? 'SYNCING' : 'SAFE-AUTO-FIX ACTIVE'}
              </Text>
            </View>
          </View>
        </View>

        <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }} data-testid="unified-readiness-board-card" testID="unified-readiness-board-card">
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 10 }}>{tx('admin.platformHealthPanel.auto.text.008', 'Automatic repair engine + alert routing is enabled for Stripe, PayPal, FedaPay, Apple IAP, and Google IAP readiness drops.')}</Text>
          <View style={{ gap: 8 }}>
            {unifiedReadinessRows.map((row, idx) => {
              const tone = row.state === 'live_ready' ? T.success : row.state === 'degraded' ? T.warning : T.error;
              return (
                <View key={`${row.provider}-${idx}`} style={{ borderRadius: 10, borderWidth: 1, borderColor: `${tone}66`, backgroundColor: row.state === 'live_ready' ? T.successBg : row.state === 'degraded' ? T.warningBg : T.errorBg, paddingHorizontal: 10, paddingVertical: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }} data-testid={`unified-readiness-row-${row.provider}`} testID={`unified-readiness-row-${row.provider}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: tone, fontSize: 11, fontWeight: '800' }}>{row.label}: {row.status_label}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>State: {String(row.state).toUpperCase()}</Text>
                  </View>
                  <Ionicons name={row.state === 'live_ready' ? 'checkmark-circle' : row.state === 'degraded' ? 'warning' : 'close-circle'} size={16} color={tone} />
                </View>
              );
            })}
          </View>

          <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: T.border, backgroundColor: T.bgSoft, padding: 10 }} data-testid="sso-e2e-validation-card" testID="sso-e2e-validation-card">
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <View>
                <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{tx('admin.platformHealthPanel.auto.text.009', 'Microsoft + Apple SSO E2E Integrity')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{tx('admin.platformHealthPanel.auto.text.010', 'One-click validation for callback/base wiring in forked environments.')}</Text>
              </View>
              <TouchableOpacity
                onPress={() => { void runSsoE2EValidation(); }}
                disabled={ssoValidationLoading}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: T.primary, opacity: ssoValidationLoading ? 0.6 : 1 }}
                data-testid="sso-e2e-validate-button" testID="sso-e2e-validate-button"
              >
                {ssoValidationLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformHealthPanel.auto.text.011', 'Validate SSO E2E')}</Text>}
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => { void runPolicyGateRecovery(); }}
                disabled={policyGateRecoveryRunning}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: T.warning, opacity: policyGateRecoveryRunning ? 0.6 : 1 }}
                data-testid="policy-gate-recovery-button" testID="policy-gate-recovery-button"
              >
                {policyGateRecoveryRunning ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformHealthPanel.auto.text.012', 'Run Prerequisite Recovery')}</Text>}
              </TouchableOpacity>
            </View>

            {ssoValidation ? (
              <View style={{ marginTop: 8, gap: 4 }}>
                <Text style={{ color: ssoValidation?.passed ? T.success : T.warning, fontSize: 10, fontWeight: '800' }} data-testid="sso-e2e-validation-status" testID="sso-e2e-validation-status">
                  {ssoValidation?.passed ? 'PASS' : 'WARNING'} • {ssoValidation?.validated_at ? new Date(ssoValidation.validated_at).toLocaleString() : 'just now'}
                </Text>
                {(ssoValidation?.checks || []).slice(0, 3).map((check: any, idx: number) => (
                  <Text key={`sso-check-${idx}`} style={{ color: check?.passed ? T.success : T.warning, fontSize: 10 }} data-testid={`sso-e2e-validation-check-${idx}`} testID={`sso-e2e-validation-check-${idx}`}>
                    • {check?.name}: {check?.passed ? 'ok' : 'needs-attention'}
                  </Text>
                ))}
              </View>
            ) : null}

            {policyGateRecoveryResult ? (
              <View style={{ marginTop: 8, borderRadius: 8, borderWidth: 1, borderColor: policyGateRecoveryResult?.recovery_success ? `${T.success}66` : `${T.warning}66`, backgroundColor: policyGateRecoveryResult?.recovery_success ? T.successBg : T.warningBg, padding: 8 }} data-testid="policy-gate-recovery-result" testID="policy-gate-recovery-result">
                <Text style={{ color: policyGateRecoveryResult?.recovery_success ? T.success : T.warning, fontSize: 10, fontWeight: '800' }} data-testid="policy-gate-recovery-result-title" testID="policy-gate-recovery-result-title">
                  {policyGateRecoveryResult?.recovery_success ? 'Policy Gate Recovery: PASS' : 'Policy Gate Recovery: Still Blocked'}
                </Text>
                {policyGateRecoveryResult?.message ? (
                  <Text style={{ color: T.textSec, fontSize: 10, marginTop: 2 }} data-testid="policy-gate-recovery-result-message" testID="policy-gate-recovery-result-message">
                    {policyGateRecoveryResult.message}
                  </Text>
                ) : null}
                {!!policyGateRecoveryResult?.before || !!policyGateRecoveryResult?.after ? (
                  <View style={{ marginTop: 4, gap: 2 }}>
                    <Text style={{ color: T.textSec, fontSize: 10 }} data-testid="policy-gate-recovery-before-checks" testID="policy-gate-recovery-before-checks">
                      Before failed checks: {((policyGateRecoveryResult?.before?.failed_checks || []) as string[]).join(', ') || 'none'}
                    </Text>
                    <Text style={{ color: T.textSec, fontSize: 10 }} data-testid="policy-gate-recovery-after-checks" testID="policy-gate-recovery-after-checks">
                      After failed checks: {((policyGateRecoveryResult?.after?.failed_checks || []) as string[]).join(', ') || 'none'}
                    </Text>
                  </View>
                ) : null}
              </View>
            ) : null}
          </View>
        </View>
      </View>

      {/* Gateway Shift Auto-Remediation Runbooks */}
      <View style={{ marginBottom: 16 }} data-testid="gateway-shift-runbooks-section" testID="gateway-shift-runbooks-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ fontSize: 13, fontWeight: '700', color: T.textSec, letterSpacing: 0.5 }} data-testid="gateway-shift-runbooks-title" testID="gateway-shift-runbooks-title">{tx('admin.platformHealthPanel.auto.text.013', 'GATEWAY SHIFT AUTO-REMEDIATION RUNBOOKS')}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: gatewayConfigLoading ? T.warningBg : T.successBg }} data-testid="gateway-shift-runbooks-status-pill" testID="gateway-shift-runbooks-status-pill">
              <Text style={{ fontSize: 10, fontWeight: '700', color: gatewayConfigLoading ? T.warning : T.success }}>
                {gatewayConfigLoading ? 'SYNCING' : 'ACTIVE'}
              </Text>
            </View>
            <TouchableOpacity
              onPress={() => { void safeRefetchGatewayConfig(); }}
              disabled={gatewayRefreshCooldownSec > 0}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border }}
              data-testid="gateway-shift-runbooks-refresh-button" testID="gateway-shift-runbooks-refresh-button"
            >
              <Ionicons name="refresh" size={12} color={T.textSec} />
              <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec }}>{gatewayRefreshCooldownSec > 0 ? `Retry in ${gatewayRefreshCooldownSec}s` : 'Refresh'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }} data-testid="gateway-shift-runbooks-card" testID="gateway-shift-runbooks-card">
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 10 }}>{tx('admin.platformHealthPanel.auto.text.014', 'Auto-creates runbooks when Stripe/PayPal/FedaPay/Apple/Google shift from LIVE_READY to DEGRADED/UNAVAILABLE and triggers Safe-Auto-Fix with alert routing.')}</Text>

          {!!runbookActionMessage ? (
            <Text style={{ color: T.cyan, fontSize: 11, marginBottom: 10 }} data-testid="gateway-shift-runbooks-action-message" testID="gateway-shift-runbooks-action-message">{runbookActionMessage}</Text>
          ) : null}

          {gatewayRunbooks.length === 0 ? (
            <Text style={{ color: T.textSec, fontSize: 11 }} data-testid="gateway-shift-runbooks-empty-state" testID="gateway-shift-runbooks-empty-state">{tx('admin.platformHealthPanel.auto.text.015', 'No gateway shifts from Live Ready detected yet.')}</Text>
          ) : (
            <View style={{ gap: 10 }}>
              {gatewayRunbooks.map((entry, idx) => (
                <View key={entry.id || idx} style={{ borderRadius: 10, borderWidth: 1, borderColor: entry.severity === 'critical' ? `${T.error}66` : `${T.warning}66`, backgroundColor: entry.severity === 'critical' ? T.errorBg : T.warningBg, padding: 10 }} data-testid={`gateway-shift-runbook-${idx}`} testID={`gateway-shift-runbook-${idx}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: entry.severity === 'critical' ? T.error : T.warning, fontSize: 11, fontWeight: '800' }}>
                        {String(entry.provider).toUpperCase()} shift: {String(entry.from).toUpperCase()} → {String(entry.to).toUpperCase()}
                      </Text>
                      <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 3 }}>{new Date(entry.created_at).toLocaleString()}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      {entry.auto_triggered ? <Ionicons name="flash" size={14} color={T.warningText} /> : null}
                      {entry.acknowledged ? <Ionicons name="checkmark-done" size={14} color={T.successText} /> : null}
                      {entry.remediation_applied ? <Ionicons name="construct" size={14} color={T.cyan} /> : null}
                    </View>
                  </View>

                  <View style={{ marginTop: 8, gap: 4 }}>
                    {(entry.steps || []).map((step: string, stepIdx: number) => (
                      <Text key={`${entry.id}-step-${stepIdx}`} style={{ color: T.textSec, fontSize: 10 }} data-testid={`gateway-shift-runbook-${idx}-step-${stepIdx}`} testID={`gateway-shift-runbook-${idx}-step-${stepIdx}`}>
                        {stepIdx + 1}. {step}
                      </Text>
                    ))}
                  </View>

                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                    <TouchableOpacity
                      onPress={() => applyRunbook(entry)}
                      disabled={runbookActionBusy}
                      style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: T.primary, opacity: runbookActionBusy ? 0.6 : 1 }}
                      data-testid={`gateway-shift-runbook-apply-${idx}`} testID={`gateway-shift-runbook-apply-${idx}`}
                    >
                      {runbookActionBusy ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformHealthPanel.auto.text.016', 'Apply Runbook')}</Text>}
                    </TouchableOpacity>

                    {!entry.acknowledged ? (
                      <TouchableOpacity
                        onPress={() => acknowledgeRunbook(entry.id)}
                        style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border }}
                        data-testid={`gateway-shift-runbook-ack-${idx}`} testID={`gateway-shift-runbook-ack-${idx}`}
                      >
                        <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700' }}>{tx('admin.platformHealthPanel.auto.text.017', 'Acknowledge')}</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>

      {/* Scan Results */}
      {scan && (
        <>
          <Text style={{ fontSize: 13, fontWeight: '700', color: T.textSec, marginBottom: 10, letterSpacing: 0.5 }}>{tx('admin.platformHealthPanel.auto.text.018', 'BUILD & CODE HEALTH')}</Text>
          <View style={{ flexDirection: 'row', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
            <View style={{ backgroundColor: T.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: T.border, alignItems: 'center', minWidth: 140 }}>
              <ScoreRing score={scan.score} grade={scan.grade} />
              <View style={{ flexDirection: 'row', gap: 16, marginTop: 14 }}>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: scan.total_issues === 0 ? T.success : T.warning }}>{scan.total_issues}</Text>
                  <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.platformHealthPanel.auto.text.019', 'Issues')}</Text>
                </View>
                <View style={{ alignItems: 'center' }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: T.cyan }}>{scan.fixable_issues}</Text>
                  <Text style={{ fontSize: 10, color: T.textMuted }}>{tx('admin.platformHealthPanel.auto.text.020', 'Fixable')}</Text>
                </View>
              </View>
            </View>

            {/* Category Cards */}
            <View style={{ flex: 1, gap: 10, minWidth: 250 }}>
              <CategoryCard id="stale_urls" label="Stale URLs" icon="link" status={scan.categories.stale_urls?.status || 'healthy'} detail={scan.stale_urls.count === 0 ? 'No hardcoded URLs found' : `${scan.stale_urls.count} stale URL${scan.stale_urls.count > 1 ? 's' : ''} detected`} />
              <CategoryCard id="build" label="Build Freshness" icon="cube" status={scan.categories.build_freshness?.status || 'healthy'} detail={scan.build.message} />
              <CategoryCard id="cache" label="Cache Health" icon="server" status={scan.categories.cache_health?.status || 'healthy'} detail={scan.caches.filter(c => c.stale).length === 0 ? 'All caches healthy' : `${scan.caches.filter(c => c.stale).length} stale cache(s)`} />
              <CategoryCard id="env" label="Environment" icon="settings" status={scan.categories.env_consistency?.status || 'healthy'} detail={scan.env.issues.length === 0 ? 'Config consistent' : `${scan.env.issues.length} issue(s)`} />
            </View>
          </View>

          {/* Expanded Details */}
          {expanded === 'stale_urls' && scan.stale_urls.issues.length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: T.border }} data-testid="stale-urls-detail" testID="stale-urls-detail">
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.platformHealthPanel.auto.text.021', 'Stale URL Details')}</Text>
              {scan.stale_urls.issues.map((issue: any, i: number) => (
                <View key={i} style={{ paddingVertical: 8, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: issue.severity === 'high' ? T.errorBg : T.warningBg }}>
                      <Text style={{ fontSize: 9, fontWeight: '700', color: issue.severity === 'high' ? T.error : T.warning }}>{issue.severity.toUpperCase()}</Text>
                    </View>
                    <Text style={{ fontSize: 11, color: T.cyan, flex: 1 }} numberOfLines={1}>{issue.file}:{issue.line}</Text>
                    {issue.fixable && <Ionicons name="hammer" size={12} color={T.successText} />}
                  </View>
                  <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 4, fontFamily: 'monospace' }} numberOfLines={1}>{issue.code}</Text>
                </View>
              ))}
            </View>
          )}

          {expanded === 'build' && (
            <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: T.border }} data-testid="build-detail" testID="build-detail">
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.platformHealthPanel.auto.text.022', 'Build Details')}</Text>
              <View style={{ gap: 6 }}>
                <Row label="Status" value={scan.build.status} color={scan.build.stale ? T.error : T.success} />
                <Row label="Build Time" value={new Date(scan.build.build_time).toLocaleString()} />
                <Row label="Age" value={`${scan.build.age_hours} hours`} />
                <Row label="Source Newer" value={scan.build.source_newer_than_build ? 'Yes' : 'No'} color={scan.build.source_newer_than_build ? T.warning : T.success} />
                <Row label="Stale Domains" value={scan.build.stale_domains_in_build ? 'Found' : 'Clean'} color={scan.build.stale_domains_in_build ? T.error : T.success} />
              </View>
            </View>
          )}

          {expanded === 'cache' && (
            <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: T.border }} data-testid="cache-detail" testID="cache-detail">
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.platformHealthPanel.auto.text.023', 'Cache Details')}</Text>
              {scan.caches.map((cache, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border, gap: 8 }}>
                  <Ionicons name={statusIcon(cache.status) as any} size={14} color={statusColor(cache.status)} />
                  <Text style={{ fontSize: 12, color: T.text, flex: 1 }}>{cache.label}</Text>
                  <Text style={{ fontSize: 11, color: T.textMuted }}>{cache.exists ? `${cache.size_mb} MB` : 'Not found'}</Text>
                  <Text style={{ fontSize: 11, color: T.textMuted }}>{cache.exists ? `${cache.age_hours}h` : '-'}</Text>
                </View>
              ))}
            </View>
          )}

          {expanded === 'env' && (
            <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: T.border }} data-testid="env-detail" testID="env-detail">
              <Text style={{ fontSize: 13, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.platformHealthPanel.auto.text.024', 'Environment Details')}</Text>
              <Row label="Frontend URL" value={scan.env.frontend_url || 'Not set'} />
              <Row label="Status" value={scan.env.status} color={statusColor(scan.env.status)} />
              {scan.env.issues.length === 0 ? (
                <Text style={{ fontSize: 11, color: T.successText, marginTop: 8 }}>{tx('admin.platformHealthPanel.auto.text.025', 'All environment variables are consistent')}</Text>
              ) : scan.env.issues.map((issue: any, i: number) => (
                <Text key={i} style={{ fontSize: 11, color: T.error, marginTop: 4 }}>{issue.field}: {issue.issue}</Text>
              ))}
            </View>
          )}

          {/* All-Clear Banner */}
          {scan.total_issues === 0 && (
            <View style={{ backgroundColor: T.successBg, borderRadius: 12, padding: 16, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '30') }} data-testid="all-clear-banner" testID="all-clear-banner">
              <Ionicons name="shield-checkmark" size={28} color={T.successText} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.successText, marginTop: 8 }}>{tx('admin.platformHealthPanel.auto.text.026', 'All Clear')}</Text>
              <Text style={{ fontSize: 11, color: T.textSec, marginTop: 4 }}>{tx('admin.platformHealthPanel.auto.text.027', 'No stale URLs, build is fresh, all caches healthy.')}</Text>
            </View>
          )}
        </>
      )}

      {/* Scan History */}
      <PlatformFinanceIntegrityPanel />

      {/* Scan History */}
      {showHistory && (
        <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 14, marginTop: 16, borderWidth: 1, borderColor: T.border }} data-testid="scan-history" testID="scan-history">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{tx('admin.platformHealthPanel.auto.text.028', 'Scan History')}</Text>
            <TouchableOpacity accessibilityLabel={tx('admin.platformHealthPanel.auto.accessibility.001', 'No previous scans')} onPress={() => setShowHistory(false)} data-testid="scan-history-close-button" testID="scan-history-close-button">
              <Ionicons name="close" size={16} color={T.textMuted} />
            </TouchableOpacity>
          </View>
          {history.length === 0 ? (
            <Text style={{ fontSize: 11, color: T.textMuted }}>{tx('admin.platformHealthPanel.auto.text.029', 'No previous scans')}</Text>
          ) : (
            <ResponsiveDataGrid
              compactBreakpoint={980}
              desktopTestId="scan-history-desktop-table"
              compactTestId="scan-history-compact-list"
              renderDesktop={() => (
                <>
                  <View style={{ flexDirection: 'row', alignItems: 'center', paddingBottom: 8, borderBottomWidth: 1, borderBottomColor: T.border, marginBottom: 4 }}>
                    <Text style={{ width: 64, fontSize: 10, color: T.textMuted, fontWeight: '700' }}>GRADE</Text>
                    <Text style={{ flex: 1, fontSize: 10, color: T.textMuted, fontWeight: '700' }}>SCORE</Text>
                    <Text style={{ width: 120, fontSize: 10, color: T.textMuted, fontWeight: '700', textAlign: 'right' }}>DATE</Text>
                  </View>
                  {history.map((h, i) => (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: T.border, gap: 10 }} data-testid={`scan-history-row-${i}`} testID={`scan-history-row-${i}`}>
                      <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(gradeColor(h.grade), '15'), alignItems: 'center', justifyContent: 'center' }}>
                        <Text style={{ fontSize: 14, fontWeight: '800', color: gradeColor(h.grade) }}>{h.grade}</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 12, color: T.text, fontWeight: '600' }}>{h.score}/100</Text>
                        <Text style={{ fontSize: 10, color: T.textMuted }}>{h.total_issues} issue{h.total_issues !== 1 ? 's' : ''}</Text>
                      </View>
                      <Text style={{ fontSize: 10, color: T.textMuted, width: 120, textAlign: 'right' }}>{new Date(h.scanned_at).toLocaleDateString()}</Text>
                    </View>
                  ))}
                </>
              )}
              renderCompact={() => (
                <View style={{ gap: 8 }}>
                  {history.map((h, i) => (
                    <View key={i} style={{ borderWidth: 1, borderColor: T.border, borderRadius: 10, backgroundColor: T.bgSoft, padding: 10, gap: 6 }} data-testid={`scan-history-row-${i}`} testID={`scan-history-row-${i}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                        <View style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(gradeColor(h.grade), '15'), alignItems: 'center', justifyContent: 'center' }}>
                          <Text style={{ fontSize: 14, fontWeight: '800', color: gradeColor(h.grade) }}>{h.grade}</Text>
                        </View>
                        <Text style={{ fontSize: 10, color: T.textMuted }}>{new Date(h.scanned_at).toLocaleDateString()}</Text>
                      </View>
                      <Text style={{ fontSize: 12, color: T.text, fontWeight: '700' }}>{h.score}/100</Text>
                      <Text style={{ fontSize: 10, color: T.textMuted }}>{h.total_issues} issue{h.total_issues !== 1 ? 's' : ''}</Text>
                    </View>
                  ))}
                </View>
              )}
            />
          )}
        </View>
      )}
    </View>
  );
}

function Row({ label, value, color, testId }: { label: string; value: string; color?: string; testId?: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }} data-testid={testId || undefined} testID={testId || undefined}>
      <Text style={{ fontSize: 11, color: T.textMuted }}>{label}</Text>
      <Text style={{ fontSize: 11, fontWeight: '600', color: color || T.text }} data-testid={testId ? `${testId}-value` : undefined} testID={testId ? `${testId}-value` : undefined}>{value}</Text>
    </View>
  );
}
