import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

interface SSOProvider {
  provider: string;
  label: string;
  icon: string;
  status: 'configured' | 'misconfigured' | 'not_configured';
  configured: boolean;
  callback_url: string;
  callback_registered?: boolean | null;
  registered_callbacks?: string[];
  auth_url?: string;
  client_id?: string;
  issues: string[];
  action: string | null;
}

interface SSOStatusData {
  deployment_domain: string;
  active_redirect_base?: string;
  allowed_sso_host_suffixes?: string[];
  strict_registered_callbacks?: boolean;
  sso_redirect_drift_sentinel?: any;
  multi_region_auth_probe?: any;
  provider_registration_alignment?: any;
  live_provider_signoff?: any;
  providers: SSOProvider[];
  summary: { total: number; configured: number; issues: number; health: string };
}

export default function SSOStatusPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const STATUS_CONFIG = {
    configured: { color: colors.successText, bg: 'var(--app-success-soft)', label: 'Active', icon: 'checkmark-circle' },
    misconfigured: { color: colors.warningText, bg: 'var(--app-warning-soft)', label: 'Issues', icon: 'warning' },
    not_configured: { color: colors.error, bg: 'var(--app-error-soft)', label: 'Not Set', icon: 'close-circle' },
  } as const;
  const HEALTH_CONFIG = {
    healthy: { color: colors.successText, label: 'All Systems Go', icon: 'shield-checkmark' },
    degraded: { color: colors.warningText, label: 'Partial', icon: 'warning' },
    critical: { color: colors.error, label: 'Critical', icon: 'alert-circle' },
  } as const;
  const [data, setData] = useState<SSOStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copiedUrl, setCopiedUrl] = useState('');

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/admin/sso-status');
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to fetch SSO status');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchStatus(); }, [fetchStatus]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/sso-status/hybrid-refresh',
    onTick: fetchStatus,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });
  const copyToClipboard = (text: string) => {
    if (Platform.OS === 'web' && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedUrl(text);
      setTimeout(() => setCopiedUrl(''), 2000);
    }
  };

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 }}>
      <AutoFixBanner domain="sso" />
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
        <Text style={{ color: colors.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.sSOStatusPanel.auto.text.001', 'Checking SSO providers...')}</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={{ padding: 20, alignItems: 'center' }}>
        <Ionicons name="alert-circle" size={32} color={'var(--app-error)'} />
        <Text style={{ color: colors.error, marginTop: 8, fontSize: 14 }}>{error}</Text>
        <TouchableOpacity onPress={fetchStatus} style={{ marginTop: 12, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.primary }} accessibilityLabel={tx('admin.sSOStatusPanel.auto.accessibility.001', 'Retry')}>
          <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '600' }}>{tx('admin.sSOStatusPanel.auto.text.002', 'Retry')}</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (!data) return null;

  const health = HEALTH_CONFIG[data.summary.health as keyof typeof HEALTH_CONFIG] || HEALTH_CONFIG.critical;
  const driftState = String(data.sso_redirect_drift_sentinel?.state || data.sso_redirect_drift_sentinel?.snapshot?.status || 'unknown').toLowerCase();
  const driftProviders = data.sso_redirect_drift_sentinel?.snapshot?.drift_providers || [];
  const probeState = String(data.multi_region_auth_probe?.state || 'unknown').toLowerCase();
  const probeViolations = Array.isArray(data.multi_region_auth_probe?.slo_violations) ? data.multi_region_auth_probe.slo_violations.length : 0;
  const alignmentResult = data.provider_registration_alignment?.result || {};
  const liveSignoffStatus = String(data.live_provider_signoff?.status || 'not_run').toLowerCase();

  return (
    <View style={{ flex: 1, padding: 16 }} data-testid="sso-status-panel" testID="sso-status-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <View>
          <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text }}>{tx('admin.sSOStatusPanel.auto.text.003', 'SSO Provider Status')}</Text>
          <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>{tx('admin.sSOStatusPanel.auto.text.004', 'Monitor authentication provider health and configuration')}</Text>
        </View>
        <TouchableOpacity onPress={fetchStatus} style={{ padding: 8, borderRadius: 8, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }} data-testid="sso-refresh-btn" testID="sso-refresh-btn">
          <Ionicons name="refresh" size={18} color={colors.textMuted} />
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 18, flexWrap: 'wrap' }} data-testid="sso-governance-cards" testID="sso-governance-cards">
        <View style={{ flex: 1, minWidth: 220, padding: 12, borderRadius: 10, backgroundColor: driftState === 'drift' ? 'var(--app-error-soft)' : 'var(--app-success-soft)', borderWidth: 1, borderColor: driftState === 'drift' ? 'var(--app-error-soft)' : 'var(--app-success-soft)' }} data-testid="sso-drift-sentinel-card" testID="sso-drift-sentinel-card">
          <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted, marginBottom: 4 }}>{tx('admin.sSOStatusPanel.auto.text.005', 'SSO Redirect Drift Sentinel')}</Text>
          <Text style={{ fontSize: 13, fontWeight: '800', color: driftState === 'drift' ? 'var(--app-error)' : 'var(--app-success)' }}>
            {driftState === 'drift' ? 'DRIFT DETECTED' : driftState === 'healthy' ? 'HEALTHY' : 'UNKNOWN'}
          </Text>
          <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 4 }} numberOfLines={2}>
            {driftProviders.length ? `Providers: ${driftProviders.join(', ')}` : 'No provider divergence detected'}
          </Text>
        </View>

        <View style={{ flex: 1, minWidth: 220, padding: 12, borderRadius: 10, backgroundColor: probeState === 'fail' ? 'var(--app-warning-soft)' : 'var(--app-success-soft)', borderWidth: 1, borderColor: probeState === 'fail' ? 'var(--app-warning-soft)' : 'var(--app-success-soft)' }} data-testid="sso-multi-region-probe-card" testID="sso-multi-region-probe-card">
          <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted, marginBottom: 4 }}>{tx('admin.sSOStatusPanel.auto.text.006', 'Multi-region Auth Probe')}</Text>
          <Text style={{ fontSize: 13, fontWeight: '800', color: probeState === 'fail' ? 'var(--app-warning)' : 'var(--app-success)' }}>
            {probeState === 'fail' ? 'SLO VIOLATIONS' : probeState === 'pass' ? 'SLO HEALTHY' : 'UNKNOWN'}
          </Text>
          <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 4 }} numberOfLines={2}>
            Route violations: {probeViolations}
          </Text>
        </View>

        <View style={{ flex: 1, minWidth: 220, padding: 12, borderRadius: 10, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft }} data-testid="sso-provider-alignment-card" testID="sso-provider-alignment-card">
          <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted, marginBottom: 4 }}>{tx('admin.sSOStatusPanel.auto.text.007', 'Provider Console Alignment')}</Text>
          <Text style={{ fontSize: 13, fontWeight: '800', color: colors.primary }}>
            Azure: {alignmentResult?.microsoft?.aligned ? 'ALIGNED' : alignmentResult?.microsoft?.attempted ? 'FAILED' : 'NOT RUN'}
          </Text>
          <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 4 }} numberOfLines={2}>
            Apple: {alignmentResult?.apple?.manual_required ? 'MANUAL REQUIRED' : 'ALIGNED'}
          </Text>
        </View>

        <View style={{ flex: 1, minWidth: 220, padding: 12, borderRadius: 10, backgroundColor: liveSignoffStatus === 'ready_for_live_run' ? 'var(--app-success-soft)' : 'var(--app-warning-soft)', borderWidth: 1, borderColor: liveSignoffStatus === 'ready_for_live_run' ? 'var(--app-success-soft)' : 'var(--app-warning-soft)' }} data-testid="sso-live-signoff-card" testID="sso-live-signoff-card">
          <Text style={{ fontSize: 11, fontWeight: '700', color: colors.textMuted, marginBottom: 4 }}>{tx('admin.sSOStatusPanel.auto.text.008', 'Live Provider Signoff')}</Text>
          <Text style={{ fontSize: 13, fontWeight: '800', color: liveSignoffStatus === 'ready_for_live_run' ? 'var(--app-success)' : 'var(--app-warning)' }}>
            {liveSignoffStatus === 'ready_for_live_run' ? 'READY' : liveSignoffStatus === 'blocked_missing_test_credentials' ? 'BLOCKED' : 'NOT RUN'}
          </Text>
          <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 4 }} numberOfLines={2}>
            Strict enforcement: {data.strict_registered_callbacks ? 'ON' : 'OFF'}
          </Text>
        </View>
      </View>

      {/* Summary Bar */}
      <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20 }} data-testid="sso-summary-bar" testID="sso-summary-bar">
        <View style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(health.color, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(health.color, '30'), flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: (globalThis as any).__alphaColor(health.color, '20'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={health.icon as any} size={20} color={health.color} />
          </View>
          <View>
            <Text style={{ fontSize: 15, fontWeight: '700', color: health.color }}>{health.label}</Text>
            <Text style={{ fontSize: 11, color: colors.textMuted }}>{data.summary.configured}/{data.summary.total} providers active</Text>
          </View>
        </View>
        <View style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '600', letterSpacing: 0.5, marginBottom: 4 }}>{tx('admin.sSOStatusPanel.auto.text.009', 'DEPLOYMENT DOMAIN')}</Text>
          <Text style={{ fontSize: 12, color: colors.primary, fontWeight: '600' }} numberOfLines={1}>{data.deployment_domain.replace('https://', '')}</Text>
          <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4 }} numberOfLines={1} data-testid="sso-active-redirect-base" testID="sso-active-redirect-base">
            Active redirect: {(data.active_redirect_base || data.deployment_domain || '').replace('https://', '')}
          </Text>
        </View>
      </View>

      {/* Provider Cards */}
      {data.providers.map((provider) => {
        const statusCfg = STATUS_CONFIG[provider.status] || STATUS_CONFIG.not_configured;
        return (
          <View
            key={provider.provider}
            style={{ marginBottom: 12, padding: 16, borderRadius: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }}
            data-testid={`sso-provider-${provider.provider}`} testID={`sso-provider-${provider.provider}`}
          >
            {/* Provider Header */}
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: statusCfg.bg, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={provider.icon as any} size={18} color={statusCfg.color} />
                </View>
                <View>
                  <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{provider.label}</Text>
                  {provider.client_id && (
                    <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 1 }}>ID: {provider.client_id}</Text>
                  )}
                </View>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20, backgroundColor: statusCfg.bg }}>
                <Ionicons name={statusCfg.icon as any} size={14} color={statusCfg.color} />
                <Text style={{ fontSize: 11, fontWeight: '700', color: statusCfg.color }}>{statusCfg.label}</Text>
              </View>
            </View>

            {/* Callback URL */}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.background || 'var(--app-primary)', borderRadius: 8, padding: 10, marginBottom: provider.issues.length > 0 || provider.action ? 10 : 0 }}>
              <Text style={{ fontSize: 11, color: colors.textMuted, fontWeight: '600', minWidth: 60 }}>{tx('admin.sSOStatusPanel.auto.text.010', 'Callback:')}</Text>
              <Text style={{ fontSize: 11, color: colors.text, flex: 1, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }} numberOfLines={1}>{provider.callback_url}</Text>
              <TouchableOpacity
                onPress={() => copyToClipboard(provider.callback_url)}
                style={{ padding: 4 }}
                data-testid={`sso-copy-${provider.provider}`} testID={`sso-copy-${provider.provider}`}
              >
                <Ionicons name={copiedUrl === provider.callback_url ? 'checkmark' : 'copy-outline'} size={14} color={copiedUrl === provider.callback_url ? 'var(--app-success)' : colors.textMuted} />
              </TouchableOpacity>
            </View>

            {provider.callback_registered === false && (
              <View style={{ marginBottom: provider.issues.length > 0 || provider.action ? 10 : 0, borderRadius: 8, borderWidth: 1, borderColor: colors.warningSoft, backgroundColor: colors.warningSoft, padding: 10 }} data-testid={`sso-provider-${provider.provider}-redirect-mismatch`} testID={`sso-provider-${provider.provider}-redirect-mismatch`}>
                <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }}>{tx('admin.sSOStatusPanel.auto.text.011', 'Redirect URI mismatch risk')}</Text>
                <Text style={{ color: colors.warningText, fontSize: 10, marginTop: 4 }} numberOfLines={2}>{tx('admin.sSOStatusPanel.auto.text.012', 'Active callback is not present in registered redirect base list.')}</Text>
              </View>
            )}

            {/* Issues */}
            {provider.issues.length > 0 && (
              <View style={{ gap: 4, marginBottom: provider.action ? 10 : 0 }}>
                {provider.issues.map((issue, i) => (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="alert-circle" size={12} color={'var(--app-warning)'} />
                    <Text style={{ fontSize: 12, color: colors.warningText }}>{issue}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* Action Required */}
            {provider.action && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingTop: 8, borderTopWidth: 1, borderTopColor: colors.border }}>
                <Ionicons name="information-circle" size={14} color={'var(--app-primary)'} />
                <Text style={{ fontSize: 12, color: colors.primary, flex: 1 }}>{provider.action}</Text>
              </View>
            )}
          </View>
        );
      })}

      {/* Info Footer */}
      <View style={{ marginTop: 8, padding: 12, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '08'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '20') }}>
        <Text style={{ fontSize: 11, color: colors.textMuted, lineHeight: 16 }}>{tx('admin.sSOStatusPanel.auto.text.013', 'After domain changes (platform forks), register the callback URLs above with each SSO provider. The backend self-healing mechanism automatically corrects corrupted Azure credentials on startup.')}</Text>
      </View>
    </View>
  );
}
