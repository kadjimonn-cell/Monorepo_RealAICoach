import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../../services/api';
import { HeartbeatPulse } from '../common/HeartbeatPulse';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';
function makeT(AC: any) { return {
  bg: 'rgba(8,16,31,0.2)',
  card: 'rgba(15,23,42,0.08)',
  cardAlt: AC.bgAlt,
  border: 'var(--app-border)',
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textDim,
  primary: 'var(--app-primary)',
  cyan: 'var(--app-primary)',
  success: 'var(--app-success)' as any,
  warning: 'var(--app-warning)' as any,
  error: 'var(--app-error)' as any,
  purple: 'var(--app-primary)',
}; }

const statusColor = (status: string) => (
  status === 'healthy'
    ? 'var(--app-success)'
    : status === 'warning'
      ? 'var(--app-warning)'
      : status === 'critical'
        ? 'var(--app-error)'
        : 'var(--app-primary)'
);

const formatAgo = (timestamp?: string) => {
  if (!timestamp) return 'No heartbeat yet';
  const diff = Math.max(0, Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000));
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
};

const LAYER_LINKS: Record<string, { href: string; label: string }> = {
  frontend: { href: '/admin-console?category=operations&tab=platform-health', label: 'Open Platform Health' },
  backend: { href: '/admin-console?category=operations&tab=ops-dashboard', label: 'Open Operations Center' },
  db: { href: '/admin-console?category=operations&tab=enterprise-control-plane', label: 'Open Enterprise Control Plane' },
  realtime: { href: '/admin-console?category=operations&tab=platform-trust-center', label: 'Open Platform Trust Center' },
  theme: { href: '/admin-console?category=operations&tab=platform-health', label: 'Open Platform Health' },
  i18n: { href: '/admin-console?category=comms&tab=languages', label: 'Open Languages' },
};

export default function AIPlatformIntegrityPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const router = useRouter();
  const [overview, setOverview] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [activating, setActivating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [lastSyncAt, setLastSyncAt] = useState(Date.now());
  const [heartbeatSec, setHeartbeatSec] = useState(0);
  const [previewRecipient, setPreviewRecipient] = useState('realaicoach@gmail.com');
  const [previewBusy, setPreviewBusy] = useState('');

  const loadAll = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const [overviewRes, historyRes] = await Promise.all([
        api.get('/admin/platform-integrity/overview'),
        api.get('/admin/platform-integrity/history', { params: { limit: 8 } }),
      ]);
      setOverview(overviewRes.data || null);
      setHistory(historyRes.data?.runs || []);
      setLastSyncAt(Date.now());
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to load AI Platform Integrity data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadAll(); }, [loadAll]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/ai-platform-integrity/hybrid-refresh',
    onTick: loadAll,
    runOnMount: false,
    slowIntervalMs: 60000,
    fastIntervalMs: 20000,
  });

  useEffect(() => {
    const interval = setInterval(() => setHeartbeatSec(Math.max(0, Math.floor((Date.now() - lastSyncAt) / 1000))), 1000);
    return () => clearInterval(interval);
  }, [lastSyncAt]);

  const runCycle = async () => {
    setRunning(true);
    setMessage('');
    try {
      const res = await api.post('/admin/platform-integrity/run-cycle');
      setMessage(`Integrity cycle ${String(res.data?.status || 'completed').toUpperCase()} • score ${res.data?.final_score || 0}/100`);
      await loadAll();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to run integrity cycle.');
    } finally {
      setRunning(false);
    }
  };

  const activateFullAutonomous = async () => {
    setActivating(true);
    setMessage('');
    try {
      const res = await api.post('/admin/platform-integrity/activate-full-autonomous-mode');
      const activation = res.data?.activation_run || {};
      setMessage(
        `Full autonomous mode active • ${String(activation.status || 'healthy').toUpperCase()} • score ${activation.final_score || 0}/100`
      );
      await loadAll();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to activate full autonomous mode.');
    } finally {
      setActivating(false);
    }
  };

  const toggleAlerts = async () => {
    if (!overview?.config) return;
    setSaving(true);
    try {
      await api.put('/admin/platform-integrity/config', {
        alert_on_critical_fix: !overview.config.alert_on_critical_fix,
        realtime_interval_minutes: overview.config.realtime_interval_minutes,
        daily_scan_hour_utc: overview.config.daily_scan_hour_utc,
      });
      await loadAll();
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to update integrity alert policy.');
    } finally {
      setSaving(false);
    }
  };

  const openEmailPreview = async (previewType: string, theme: 'light' | 'dark') => {
    setPreviewBusy(`${previewType}-${theme}`);
    setMessage('');
    try {
      const res = await api.get(`/admin/platform-integrity/email-preview/${previewType}`, { params: { theme } });
      if (typeof window !== 'undefined' && window.open) {
        const popup = window.open('', '_blank');
        popup?.document.open();
        popup?.document.write(res.data?.html || '<p>Preview unavailable.</p>');
        popup?.document.close();
      } else {
        setMessage('Email previews open in-browser on web.');
      }
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to open email preview.');
    } finally {
      setPreviewBusy('');
    }
  };

  const sendPreviewAlert = async (previewType: string) => {
    setPreviewBusy(`send-${previewType}`);
    setMessage('');
    try {
      const res = await api.post('/admin/platform-integrity/send-preview-alert', {
        preview_type: previewType,
        recipient_email: previewRecipient,
        recipient_name: 'Preview Recipient',
      });
      setMessage(`Preview email sent to ${res.data?.recipient_email || previewRecipient} (${previewType}).`);
    } catch (e: any) {
      setMessage(e?.response?.data?.detail || 'Unable to send preview alert email.');
    } finally {
      setPreviewBusy('');
    }
  };

  const scoreCards = useMemo(() => {
    const latestRun = overview?.latest_run || {};
    const scan = overview?.platform_scan || {};
    const domains = overview?.domain_rollup?.summary || {};
    return [
      { id: 'score', label: 'Platform Score', value: `${scan?.score || 0}/100`, color: T.primary, sub: `Grade ${scan?.grade || 'N/A'}` },
      { id: 'issues', label: 'Open Issues', value: String(scan?.total_issues || 0), color: T.warningText, sub: `${scan?.fixable_issues || 0} auto-fixable` },
      { id: 'repairs', label: 'Last Cycle Fixes', value: String((latestRun?.platform_fixes || 0) + (latestRun?.domain_fixes || 0) + (latestRun?.self_repairs || 0) + (latestRun?.ai_applied || 0)), color: T.successText, sub: latestRun?.status ? `Status ${String(latestRun.status).toUpperCase()}` : 'No run yet' },
      { id: 'review', label: 'AI Review Queue', value: String(overview?.review_queue || 0), color: T.purpleText, sub: `${domains?.warning || 0} warning domains` },
    ];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overview]);

  const coverageCards = useMemo(() => {
    const registry = overview?.global_registry || {};
    return [
      { id: 'frontend', label: 'Frontend Routes', value: registry?.frontend_routes?.count || 0 },
      { id: 'admin', label: 'Admin Surfaces', value: registry?.admin_tabs?.count || 0 },
      { id: 'api', label: 'API Endpoints', value: registry?.api_routes?.count || 0 },
      { id: 'db', label: 'DB Collections', value: registry?.db_collections?.count || 0 },
      { id: 'jobs', label: 'Guardian Jobs', value: registry?.scheduler_jobs?.count || 0 },
    ];
  }, [overview]);

  if (loading && !overview) {
    return <View style={{ padding: 40, alignItems: 'center' }} data-testid="ai-platform-integrity-loading" testID="ai-platform-integrity-loading"><ActivityIndicator size="large" color={T.primary} /></View>;
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 40 }} data-testid="ai-platform-integrity-panel" testID="ai-platform-integrity-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 18 }}>
        <View>
          <Text style={{ color: colors?.text || T.text, fontSize: 22, fontWeight: '800' }} data-testid="ai-platform-integrity-title" testID="ai-platform-integrity-title">{tx('admin.aIPlatformIntegrityPanel.auto.text.001', 'AI Platform Integrity & Auto-Fix Engine')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.002', 'Permanent autonomous rule: scan → detect → auto-fix → validate across frontend, backend, APIs, DB, admin, user, realtime, theme, and i18n.')}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }} data-testid="ai-platform-integrity-lock-badge" testID="ai-platform-integrity-lock-badge">
            <View style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: T.success }} />
            <Text style={{ color: T.successText, fontSize: 11, fontWeight: '800' }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.003', 'ALWAYS ON')}</Text>
          </View>
          <HeartbeatPulse tick={heartbeatSec} warningAfterSeconds={120} criticalAfterSeconds={240} dataTestId="ai-platform-integrity-heartbeat" testID="ai-platform-integrity-heartbeat">
            <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{heartbeatSec >= 240 ? 'Critical stale' : heartbeatSec >= 120 ? 'Stale' : 'Updated'} {heartbeatSec}s ago</Text>
          </HeartbeatPulse>
          <TouchableOpacity onPress={() => { void loadAll(); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid="ai-platform-integrity-refresh-button" testID="ai-platform-integrity-refresh-button"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.004', 'Refresh')}</Text></TouchableOpacity>
          <TouchableOpacity onPress={toggleAlerts} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid="ai-platform-integrity-alert-toggle" testID="ai-platform-integrity-alert-toggle"><Text style={{ color: T.textSec, fontSize: 12, fontWeight: '800' }}>{saving ? 'Saving...' : overview?.config?.alert_on_critical_fix ? 'Alerts ON' : 'Alerts OFF'}</Text></TouchableOpacity>
          <TouchableOpacity onPress={activateFullAutonomous} style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: T.success }} data-testid="ai-platform-integrity-activate-full-autonomous-button" testID="ai-platform-integrity-activate-full-autonomous-button"><Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{activating ? 'Activating...' : 'Activate Full Autonomous'}</Text></TouchableOpacity>
          <TouchableOpacity onPress={runCycle} style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: T.primary }} data-testid="ai-platform-integrity-run-cycle-button" testID="ai-platform-integrity-run-cycle-button"><Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{running ? 'Running...' : 'Run Integrity Cycle'}</Text></TouchableOpacity>
        </View>
      </View>

      {!!message ? <Text style={{ color: T.warningText, fontSize: 12, marginBottom: 12 }} data-testid="ai-platform-integrity-message" testID="ai-platform-integrity-message">{message}</Text> : null}

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 18 }} data-testid="ai-platform-integrity-rule-card" testID="ai-platform-integrity-rule-card">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.005', 'Autonomous Enforcement Rule')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 12 }}>
          {[
            `Realtime cadence: every ${overview?.config?.realtime_interval_minutes || 15}m`,
            `Daily full cycle: ${overview?.config?.daily_scan_hour_utc ?? 4}:00 UTC`,
            `Safe mode: ${overview?.config?.safe_mode ? 'deterministic remediations only' : 'extended'}`,
            `Critical fix alerts: ${overview?.config?.alert_on_critical_fix ? 'enabled' : 'disabled'}`,
            `Global E2E validation: ${overview?.config?.global_e2e_validation ? 'enforced' : 'off'}`,
            `Zero-error policy: ${overview?.config?.zero_error_policy ? 'enforced' : 'off'}`,
            `Auto lock regressions: ${overview?.config?.auto_lock_regressions ? 'enabled' : 'off'}`,
          ].map((item) => (
            <View key={item} style={{ backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 }}>
              <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>{item}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginBottom: 18 }}>
        {scoreCards.map((card) => (
          <View key={card.id} style={{ minWidth: 200, flex: 1, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16 }} data-testid={`ai-platform-integrity-score-${card.id}`} testID={`ai-platform-integrity-score-${card.id}`}>
            <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{card.label}</Text>
            <Text style={{ color: card.color, fontSize: 26, fontWeight: '800', marginTop: 10 }}>{card.value}</Text>
            <Text style={{ color: T.textSec, fontSize: 11, marginTop: 6 }}>{card.sub}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16, marginBottom: 18 }}>
        <View style={{ flex: 1, minWidth: 320, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16 }} data-testid="ai-platform-integrity-global-coverage-card" testID="ai-platform-integrity-global-coverage-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.006', 'Global Coverage Registry')}</Text>
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 12 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.007', 'Persistent autonomous coverage across frontend, backend, APIs, DB, admin, user, and scheduler surfaces.')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            {coverageCards.map((item) => (
              <View key={item.id} style={{ minWidth: 140, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 10 }} data-testid={`ai-platform-integrity-coverage-${item.id}`} testID={`ai-platform-integrity-coverage-${item.id}`}>
                <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                <Text style={{ color: T.cyan, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{item.value}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flex: 1, minWidth: 320, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16 }} data-testid="ai-platform-integrity-zero-error-card" testID="ai-platform-integrity-zero-error-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.008', 'Zero-Error Enforcement')}</Text>
          <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
            <View style={{ backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="ai-platform-integrity-zero-error-healthy-count" testID="ai-platform-integrity-zero-error-healthy-count">
              <Text style={{ color: T.successText, fontSize: 11, fontWeight: '800' }}>Healthy {(overview?.global_validation?.summary?.healthy ?? 0)}</Text>
            </View>
            <View style={{ backgroundColor: colors.warningSoft, borderWidth: 1, borderColor: colors.warningSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="ai-platform-integrity-zero-error-warning-count" testID="ai-platform-integrity-zero-error-warning-count">
              <Text style={{ color: T.warningText, fontSize: 11, fontWeight: '800' }}>Warning {(overview?.global_validation?.summary?.warning ?? 0)}</Text>
            </View>
            <View style={{ backgroundColor: colors.errorSoft, borderWidth: 1, borderColor: colors.errorSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 }} data-testid="ai-platform-integrity-zero-error-critical-count" testID="ai-platform-integrity-zero-error-critical-count">
              <Text style={{ color: T.error, fontSize: 11, fontWeight: '800' }}>Critical {(overview?.global_validation?.summary?.critical ?? 0)}</Text>
            </View>
          </View>
          {(overview?.global_validation?.checks || []).map((check: any, idx: number) => (
            <View key={check.id || idx} style={{ paddingVertical: 9, borderBottomWidth: idx < (overview?.global_validation?.checks || []).length - 1 ? 1 : 0, borderBottomColor: 'var(--app-border)' }} data-testid={`ai-platform-integrity-zero-error-check-${check.id || idx}`} testID={`ai-platform-integrity-zero-error-check-${check.id || idx}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', flex: 1 }}>{check.label}</Text>
                <Text style={{ color: statusColor(String(check.status || 'warning')), fontSize: 10, fontWeight: '800' }}>{String(check.status || 'warning').toUpperCase()}</Text>
              </View>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{check.detail}</Text>
              {Array.isArray(check.affected_jobs) && check.affected_jobs.length ? (
                <Text
                  style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}
                  data-testid={`ai-platform-integrity-zero-error-check-affected-jobs-${check.id || idx}`} testID={`ai-platform-integrity-zero-error-check-affected-jobs-${check.id || idx}`}
                >
                  Affected jobs: {check.affected_jobs.slice(0, 5).join(', ')}
                </Text>
              ) : null}
            </View>
          ))}
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 18 }} data-testid="ai-platform-integrity-layers-card" testID="ai-platform-integrity-layers-card">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.009', 'Integrity Layers')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {(overview?.integrity_layers || []).map((layer: any) => {
            const destination = LAYER_LINKS[layer.id] || LAYER_LINKS.frontend;
            return (
            <TouchableOpacity key={layer.id} onPress={() => router.push(destination.href as any)} style={{ minWidth: 220, flex: 1, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 14 }} data-testid={`ai-platform-integrity-layer-${layer.id}`} testID={`ai-platform-integrity-layer-${layer.id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '700', flex: 1 }}>{layer.label}</Text>
                <Text style={{ color: statusColor(layer.status), fontSize: 11, fontWeight: '800' }}>{String(layer.status).toUpperCase()}</Text>
              </View>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 8 }}>{layer.detail}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 }} data-testid={`ai-platform-integrity-layer-link-${layer.id}`} testID={`ai-platform-integrity-layer-link-${layer.id}`}>
                <Ionicons name="arrow-forward-circle" size={14} color={T.cyan} />
                <Text style={{ color: T.cyan, fontSize: 11, fontWeight: '700' }}>{destination.label}</Text>
              </View>
            </TouchableOpacity>
          )})}
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
        <View style={{ flex: 1, minWidth: 320, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16 }} data-testid="ai-platform-integrity-autonomous-jobs-card" testID="ai-platform-integrity-autonomous-jobs-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.010', 'Autonomous Jobs')}</Text>
          {(overview?.autonomous_jobs || []).map((job: any, idx: number) => (
            <View key={`${job.job_id}-${idx}`} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 10, borderBottomWidth: idx < (overview?.autonomous_jobs || []).length - 1 ? 1 : 0, borderBottomColor: 'var(--app-border)' }} data-testid={`ai-platform-integrity-job-${idx}`} testID={`ai-platform-integrity-job-${idx}`}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{job.job_id}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{formatAgo(job.last_run)}</Text>
              </View>
              <Text style={{ color: statusColor(job.status), fontSize: 11, fontWeight: '800' }}>{String(job.status || 'unknown').toUpperCase()}</Text>
            </View>
          ))}
        </View>

        <View style={{ flex: 1, minWidth: 320, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16 }} data-testid="ai-platform-integrity-domain-summary-card" testID="ai-platform-integrity-domain-summary-card">
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.011', 'Domain Auto-Fix Coverage')}</Text>
          {Object.entries(overview?.domain_rollup?.summary || {}).map(([key, value]: any) => (
            <View key={key} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 8 }} data-testid={`ai-platform-integrity-domain-summary-${key}`} testID={`ai-platform-integrity-domain-summary-${key}`}>
              <Text style={{ color: T.textSec, fontSize: 12 }}>{key.replace(/_/g, ' ')}</Text>
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '800' }}>{value}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginBottom: 18 }} data-testid="ai-platform-integrity-latest-run-card" testID="ai-platform-integrity-latest-run-card">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.012', 'Latest Integrity Cycle')}</Text>
        {overview?.latest_run?.run_id ? (
          <>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              {[
                { id: 'trigger', label: 'Trigger', value: overview.latest_run.trigger },
                { id: 'baseline', label: 'Baseline Score', value: String(overview.latest_run.baseline_score || 0) },
                { id: 'final', label: 'Final Score', value: String(overview.latest_run.final_score || 0) },
                { id: 'ai', label: 'AI Fixes', value: String(overview.latest_run.ai_applied || 0) },
                { id: 'domain', label: 'Domain Fixes', value: String(overview.latest_run.domain_fixes || 0) },
                { id: 'repair', label: 'Self Repairs', value: String(overview.latest_run.self_repairs || 0) },
              ].map((item) => (
                <View key={item.id} style={{ minWidth: 160, backgroundColor: T.cardAlt, borderWidth: 1, borderColor: T.border, borderRadius: 12, padding: 12 }} data-testid={`ai-platform-integrity-latest-${item.id}`} testID={`ai-platform-integrity-latest-${item.id}`}>
                  <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
                  <Text style={{ color: T.text, fontSize: 18, fontWeight: '800', marginTop: 8 }}>{item.value}</Text>
                </View>
              ))}
            </View>
            <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 12 }}>Started {overview.latest_run.started_at} • Finished {overview.latest_run.finished_at}</Text>
            {!!overview?.latest_lock?.lock_id ? (
              <View style={{ marginTop: 10, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft, borderRadius: 10, padding: 10 }} data-testid="ai-platform-integrity-latest-lock-banner" testID="ai-platform-integrity-latest-lock-banner">
                <Text style={{ color: T.successText, fontSize: 11, fontWeight: '800' }}>LOCKED: {overview.latest_lock.lock_id}</Text>
                <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>Validation {String(overview.latest_lock.validation_status || 'healthy').toUpperCase()} • Signature {String(overview.latest_lock.lock_signature || '').slice(0, 14)}</Text>
              </View>
            ) : null}
          </>
        ) : (
          <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.013', 'No integrity cycle has been recorded yet.')}</Text>
        )}
      </View>

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16 }} data-testid="ai-platform-integrity-history-card" testID="ai-platform-integrity-history-card">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', marginBottom: 12 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.014', 'Recent Cycle History')}</Text>
        {history.length ? history.map((run, idx) => (
          <View key={run.run_id || idx} style={{ paddingVertical: 10, borderBottomWidth: idx < history.length - 1 ? 1 : 0, borderBottomColor: 'var(--app-border)' }} data-testid={`ai-platform-integrity-history-row-${idx}`} testID={`ai-platform-integrity-history-row-${idx}`}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{run.run_id}</Text>
                <Text style={{ color: T.textSec, fontSize: 11, marginTop: 4 }}>{run.trigger} • {run.mode} • started {run.started_at}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={{ color: statusColor(run.status), fontSize: 11, fontWeight: '800' }}>{String(run.status).toUpperCase()}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>Final {run.final_score || 0}/100</Text>
              </View>
            </View>
          </View>
        )) : <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.015', 'No history yet.')}</Text>}
      </View>

      <View style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 16, padding: 16, marginTop: 18 }} data-testid="ai-platform-integrity-email-preview-matrix-card" testID="ai-platform-integrity-email-preview-matrix-card">
        <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.016', 'Email Preview Matrix')}</Text>
        <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.017', 'Preview dark/light alert rendering before sending, and send a fresh preview directly to your inbox.')}</Text>
        <View style={{ marginTop: 12 }}>
          <Text style={{ color: T.textSec, fontSize: 11, marginBottom: 6 }}>{tx('admin.aIPlatformIntegrityPanel.auto.text.018', 'Preview recipient')}</Text>
          <TextInput accessibilityLabel={tx('admin.aIPlatformIntegrityPanel.auto.accessibility.001', 'Text input')}
            value={previewRecipient}
            onChangeText={setPreviewRecipient}
            autoCapitalize="none"
            keyboardType="email-address"
            style={{ borderWidth: 1, borderColor: T.border, backgroundColor: T.cardAlt, color: T.text, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13 }}
            data-testid="ai-platform-integrity-preview-recipient-input" testID="ai-platform-integrity-preview-recipient-input"
          />
        </View>
        <View style={{ marginTop: 14, gap: 10 }}>
          {[
            { id: 'integrity', label: 'Integrity Alert' },
            { id: 'performance', label: 'Performance Alert' },
            { id: 'payment-e2e', label: 'Payment E2E Alert' },
          ].map((item) => (
            <View key={item.id} style={{ borderWidth: 1, borderColor: T.border, backgroundColor: T.cardAlt, borderRadius: 14, padding: 14 }} data-testid={`ai-platform-integrity-email-preview-row-${item.id}`} testID={`ai-platform-integrity-email-preview-row-${item.id}`}>
              <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{item.label}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
                <TouchableOpacity onPress={() => { void openEmailPreview(item.id, 'light'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid={`ai-platform-integrity-preview-light-${item.id}`} testID={`ai-platform-integrity-preview-light-${item.id}`}>
                  <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '800' }}>{previewBusy === `${item.id}-light` ? 'Opening...' : 'Open Light'}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => { void openEmailPreview(item.id, 'dark'); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.card, borderWidth: 1, borderColor: T.border }} data-testid={`ai-platform-integrity-preview-dark-${item.id}`} testID={`ai-platform-integrity-preview-dark-${item.id}`}>
                  <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '800' }}>{previewBusy === `${item.id}-dark` ? 'Opening...' : 'Open Dark'}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => { void sendPreviewAlert(item.id); }} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: T.primary }} data-testid={`ai-platform-integrity-send-preview-${item.id}`} testID={`ai-platform-integrity-send-preview-${item.id}`}>
                  <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{previewBusy === `send-${item.id}` ? 'Sending...' : 'Send Preview'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}
