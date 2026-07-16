import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useLiveMetrics } from '../../hooks/useLiveMetrics';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { useHybridPolling } from '../../hooks/useHybridPolling';

type IntegrationConfig = { enabled?: boolean; label?: string; category?: string };

const CATEGORY_TONES = ['primary', 'success', 'warning', 'info'] as const;

export function PlatformIntegrationsDashboard() {
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { data: runtimeConfig, loading: configLoading, refetch: refetchConfig } = useLiveQuery('/config/global', { entity: 'config', pollInterval: 60000 });
  const { data: connectors, loading: connectorsLoading, refetch: refetchConnectors } = useLiveQuery('/integrations/dashboard/stats', { entity: 'integrations', pollInterval: 60000 });
  const { data: availableData } = useLiveQuery('/integrations/available', { entity: 'integrations', pollInterval: 120000 });
  const [busyIntegrationId, setBusyIntegrationId] = useState<string | null>(null);

  // ── Real-time heartbeat: refetch connector status & config on every SSE tick (~5s) ──
  const { data: liveTick, transport: liveTransport } = useLiveMetrics();
  const lastTickRef = useRef<string | null>(null);
  useEffect(() => {
    const ts = liveTick?.timestamp || null;
    if (!ts || ts === lastTickRef.current) return;
    // Skip the very first snapshot (it's just the hydration read-through)
    if (lastTickRef.current !== null) {
      void refetchConnectors();
      void refetchConfig();
    }
    lastTickRef.current = ts;
  }, [liveTick?.timestamp, refetchConnectors, refetchConfig]);
  const liveModeColor = liveTransport === 'sse' ? colors.success : liveTransport === 'poll' ? colors.warning : colors.textMuted;
  const liveModeLabel = liveTransport === 'sse' ? 'LIVE' : liveTransport === 'poll' ? 'POLL' : 'IDLE';

  const integrationEntries = useMemo(() => Object.entries((runtimeConfig?.integrations || {}) as Record<string, IntegrationConfig>), [runtimeConfig]);
  const categoryMeta = useMemo(() => {
    const categories = Array.from(new Set(integrationEntries.map(([, value]) => value?.category || 'Other')));
    return categories.reduce<Record<string, { accent: string; soft: string }>>((acc, category, index) => {
      const tone = CATEGORY_TONES[index % CATEGORY_TONES.length];
      const accent = colors[tone];
      acc[category] = { accent, soft: `${accent}14` };
      return acc;
    }, {});
  }, [colors, integrationEntries]);

  const enabledCount = integrationEntries.filter(([, value]) => value?.enabled !== false).length;
  const connectedCount = connectors?.active_integrations || 0;
  const availableCount = availableData?.integrations?.length || 0;
  const recentSyncs = connectors?.recent_syncs || [];

  const toggleIntegration = async (integrationId: string, currentValue: boolean) => {
    setBusyIntegrationId(integrationId);
    try {
      await api.post('/config/admin/update', { [`integrations.${integrationId}.enabled`]: !currentValue });
      await refetchConfig();
    } finally {
      setBusyIntegrationId(null);
    }
  };

  if (configLoading || connectorsLoading) {
    return <CenteredLoader color={colors.primary} testId="platform-integrations-loading" label="Loading platform integrations…" />;
  }

  return (
    <ScrollView contentContainerStyle={{ gap: 16, paddingBottom: 24 }} data-testid="platform-integrations-dashboard" testID="platform-integrations-dashboard">
      <View style={heroCard(colors, darkMode)} data-testid="platform-integrations-hero" testID="platform-integrations-hero">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 260 }}>
            <Text style={{ color: colors.text, fontSize: 24, fontWeight: '800', letterSpacing: -0.6 }} data-testid="platform-integrations-title" testID="platform-integrations-title">{tx('admin.platformIntegrations.header.title', 'Platform Integrations')}</Text>
            <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20, marginTop: 6 }} data-testid="platform-integrations-subtitle" testID="platform-integrations-subtitle">{tx('admin.platformIntegrations.header.subtitle', 'Control platform-level connectors, monitor hiring syncs, and verify which enterprise workflows are actively wired into the product.')}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: `${liveModeColor}40`, backgroundColor: `${liveModeColor}14` }} data-testid="platform-integrations-live-pill" testID="platform-integrations-live-pill">
              <View style={{ width: 7, height: 7, borderRadius: 999, backgroundColor: liveModeColor }} data-testid="platform-integrations-live-dot" testID="platform-integrations-live-dot" />
              <Text style={{ color: liveModeColor, fontSize: 10, fontWeight: '800', letterSpacing: 0.8 }} data-testid="platform-integrations-live-label" testID="platform-integrations-live-label">{liveModeLabel}</Text>
            </View>
            <TouchableOpacity onPress={() => { void refetchConfig(); void refetchConnectors(); }} style={secondaryButton(colors)} data-testid="platform-integrations-refresh-button" testID="platform-integrations-refresh-button">
              <Ionicons name="refresh" size={14} color={colors.textSec} />
              <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.platformIntegrations.actions.refresh', 'Refresh')}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', marginTop: 16 }} data-testid="platform-integrations-kpis" testID="platform-integrations-kpis">
          <KpiCard label="Enabled Runtime Connectors" value={enabledCount} accent={colors.primary} testId="platform-integrations-enabled-count" />
          <KpiCard label="Connected Hiring Connectors" value={connectedCount} accent={colors.success} testId="platform-integrations-connected-count" />
          <KpiCard label="Available Connectors" value={availableCount} accent={colors.warning} testId="platform-integrations-available-count" />
          <KpiCard label="Recent Sync Jobs" value={recentSyncs.length} accent={colors.info} testId="platform-integrations-sync-count" />
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <View style={{ flex: 2, minWidth: 320 }}>
          <SectionCard title="Runtime Integration Controls" subtitle="Toggle the platform integrations that feed shared product capabilities." colors={colors} testId="platform-integrations-runtime-card">
            <View style={{ gap: 10 }}>
              {integrationEntries.map(([key, value], index) => {
                const category = value?.category || 'Other';
                const meta = categoryMeta[category];
                const enabled = value?.enabled !== false;
                const busy = busyIntegrationId === key;
                return (
                  <View key={key} style={{ borderRadius: 14, borderWidth: 1, borderColor: enabled ? `${meta.accent}35` : colors.border, backgroundColor: colors.bgSoft, padding: 14 }} data-testid={`platform-integration-row-${key}`} testID={`platform-integration-row-${key}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                      <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center', flex: 1, minWidth: 220 }}>
                        <View style={{ width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: meta.soft }}>
                          <Ionicons name={index % 2 === 0 ? 'git-network' : 'link'} size={18} color={meta.accent} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }} data-testid={`platform-integration-label-${key}`} testID={`platform-integration-label-${key}`}>{value?.label || key}</Text>
                          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{category}</Text>
                        </View>
                      </View>
                      <TouchableOpacity onPress={() => { void toggleIntegration(key, enabled); }} disabled={busy} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: enabled ? `${colors.success}40` : colors.border, backgroundColor: enabled ? colors.successSoft : colors.surface, opacity: busy ? 0.6 : 1 }} data-testid={`platform-integration-toggle-${key}`} testID={`platform-integration-toggle-${key}`}>
                        {busy ? <ActivityIndicator size="small" color={enabled ? colors.success : colors.textSec} /> : <Ionicons name={enabled ? 'checkmark-circle' : 'pause-circle'} size={14} color={enabled ? colors.success : colors.textSec} />}
                        <Text style={{ color: enabled ? colors.success : colors.textSec, fontSize: 11, fontWeight: '700' }}>{enabled ? 'Enabled' : 'Disabled'}</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                );
              })}
            </View>
          </SectionCard>
        </View>

        <View style={{ flex: 1, minWidth: 280 }}>
          <SectionCard title="Hiring Connector Health" subtitle="Latest sync coverage from ATS and HRIS connections." colors={colors} testId="platform-integrations-connected-card">
            {(connectors?.integrations || []).length ? (
              <View style={{ gap: 10 }}>
                {connectors.integrations.map((integration: any) => {
                  const syncedAt = integration.sync_status?.last_sync ? new Date(integration.sync_status.last_sync).toLocaleString() : 'Never synced';
                  return (
                    <View key={integration.config_id} style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid={`platform-connected-row-${integration.integration_id}`} testID={`platform-connected-row-${integration.integration_id}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{integration.integration_name}</Text>
                          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{integration.test_mode ? 'Test mode' : 'Live mode'} · {syncedAt}</Text>
                        </View>
                        <View style={{ alignItems: 'flex-end' }}>
                          <Text style={{ color: colors.successText, fontSize: 15, fontWeight: '800' }}>{integration.sync_status?.records_synced || 0}</Text>
                          <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.platformIntegrations.labels.records', 'records')}</Text>
                        </View>
                      </View>
                    </View>
                  );
                })}
              </View>
            ) : (
              <EmptyState colors={colors} icon="git-network-outline" label="No hiring connectors configured yet." testId="platform-integrations-empty-connected" />
            )}
          </SectionCard>

          <SectionCard title="Recent Sync Activity" subtitle="Most recent connector jobs across the platform." colors={colors} testId="platform-integrations-sync-card">
            {recentSyncs.length ? (
              <View style={{ gap: 8 }}>
                {recentSyncs.map((sync: any, index: number) => (
                  <View key={sync.log_id || index} style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} data-testid={`platform-sync-row-${index}`} testID={`platform-sync-row-${index}`}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{sync.integration_id}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }}>{sync.records_synced} records · {sync.errors || 0} errors</Text>
                  </View>
                ))}
              </View>
            ) : (
              <EmptyState colors={colors} icon="time-outline" label="No sync jobs recorded yet." testId="platform-integrations-empty-syncs" />
            )}
          </SectionCard>

          <WebhookAlertsCard colors={colors} />
        </View>
      </View>
    </ScrollView>
  );
}

// ── Webhook Alerts (Slack/Teams) ────────────────────────────────────────────
function WebhookAlertsCard({ colors }: { colors: any }) {
  const [cfg, setCfg] = useState<any>(null);
  const [slackUrl, setSlackUrl] = useState('');
  const [teamsUrl, setTeamsUrl] = useState('');
  const [minSeverity, setMinSeverity] = useState<'info' | 'warning' | 'critical'>('warning');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [recent, setRecent] = useState<any[]>([]);

  const loadCfg = async () => {
    try {
      const r = await api.get('/admin/webhook-alerts/config');
      setCfg(r.data);
      setMinSeverity(r.data?.min_severity || 'warning');
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformIntegrationsDashboard.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };
  const loadRecent = async () => {
    try {
      const r = await api.get('/admin/webhook-alerts/recent?limit=5');
      setRecent(r.data?.items || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PlatformIntegrationsDashboard.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };
  useEffect(() => { void loadCfg(); void loadRecent(); }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/platform-integrations/webhook-alerts/hybrid-refresh',
    onTick: loadRecent,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
    wsEnabled: false,
  });

  const save = async () => {
    setSaving(true);
    try {
      const body: any = { min_severity: minSeverity };
      if (slackUrl.trim()) body.slack_webhook_url = slackUrl.trim();
      if (teamsUrl.trim()) body.teams_webhook_url = teamsUrl.trim();
      await api.put('/admin/webhook-alerts/config', body);
      setSlackUrl(''); setTeamsUrl('');
      setToast('Saved');
      await loadCfg();
    } catch (e: any) {
      setToast('Save failed: ' + (e?.message || 'unknown'));
    } finally {
      setSaving(false);
      setTimeout(() => setToast(null), 2500);
    }
  };

  const testFire = async () => {
    setTesting(true);
    try {
      const r = await api.post('/admin/webhook-alerts/test');
      const d = r.data || {};
      setToast(d.dispatched ? `Test dispatched: ${Object.keys(d.results || {}).join(' + ')}` : 'Not dispatched (check config)');
      await loadRecent();
    } catch (e: any) {
      setToast('Test failed: ' + (e?.message || 'unknown'));
    } finally {
      setTesting(false);
      setTimeout(() => setToast(null), 3500);
    }
  };

  const slackOk = !!cfg?.slack_webhook_url_configured;
  const teamsOk = !!cfg?.teams_webhook_url_configured;

  return (
    <View
      style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 18, gap: 14 }}
      data-testid="platform-integrations-webhook-alerts-card" testID="platform-integrations-webhook-alerts-card"
    >
      <View>
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{tx('admin.platformIntegrations.webhooks.title', 'Slack / Teams Alert Webhooks')}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>
          {tx('admin.platformIntegrations.webhooks.subtitle', 'Fire realtime alerts for V7 email guardrail, UIEM crash-layer violations, and nightly theme drift regressions.')}
        </Text>
      </View>
      <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
        <StatusPill label="Slack" ok={slackOk} colors={colors} testId="webhook-alert-status-slack" />
        <StatusPill label="Teams" ok={teamsOk} colors={colors} testId="webhook-alert-status-teams" />
        <StatusPill label={`Min: ${cfg?.min_severity || 'warning'}`} ok={true} colors={colors} testId="webhook-alert-status-severity" neutral />
      </View>
      <View style={{ gap: 8 }}>
        <WebhookInput placeholder={slackOk ? 'Replace Slack URL (optional)' : 'https://hooks.slack.com/services/T…/B…/…'} value={slackUrl} onChangeText={setSlackUrl} colors={colors} testId="webhook-alert-slack-input" />
        <WebhookInput placeholder={teamsOk ? 'Replace Teams URL (optional)' : 'https://<tenant>.webhook.office.com/webhookb2/…'} value={teamsUrl} onChangeText={setTeamsUrl} colors={colors} testId="webhook-alert-teams-input" />
        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {(['info', 'warning', 'critical'] as const).map((sev) => (
            <TouchableOpacity accessibilityLabel="Set min severity in platform integrations dashboard button"
              key={sev}
              onPress={() => setMinSeverity(sev)}
              style={{
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999,
                borderWidth: 1,
                borderColor: minSeverity === sev ? colors.primary : colors.border,
                backgroundColor: minSeverity === sev ? `${colors.primary}18` : 'transparent',
              }}
              data-testid={`webhook-alert-sev-${sev}`} testID={`webhook-alert-sev-${sev}`}
            >
              <Text style={{ color: minSeverity === sev ? colors.primary : colors.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{sev}</Text>
            </TouchableOpacity>
          ))}
          <View style={{ flex: 1 }} />
          <TouchableOpacity onPress={save} disabled={saving} style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: colors.primary, opacity: saving ? 0.6 : 1 }} data-testid="webhook-alert-save-button" testID="webhook-alert-save-button">
            <Text style={{ color: colors.primaryText || 'var(--app-primary-text)', fontSize: 12, fontWeight: '800' }}>{saving ? 'Saving…' : 'Save'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={testFire} disabled={testing || (!slackOk && !teamsOk)} style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, opacity: testing || (!slackOk && !teamsOk) ? 0.5 : 1 }} data-testid="webhook-alert-test-button" testID="webhook-alert-test-button">
            <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>{testing ? 'Firing…' : 'Send Test Alert'}</Text>
          </TouchableOpacity>
        </View>
        {toast && (
          <Text style={{ color: colors.textSec, fontSize: 11, fontStyle: 'italic' }} data-testid="webhook-alert-toast" testID="webhook-alert-toast">{toast}</Text>
        )}
      </View>
      {recent.length > 0 && (
        <View style={{ gap: 6, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12 }}>
          <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>Last {recent.length} alerts</Text>
          {recent.map((r, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`webhook-alert-recent-row-${i}`} testID={`webhook-alert-recent-row-${i}`}>
              <View style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: r.dispatched ? (colors.success || 'var(--app-success)') : (colors.textMuted || 'var(--app-text-muted)') }} />
              <Text style={{ color: colors.text, fontSize: 11, flex: 1 }} numberOfLines={1}>
                [{(r.severity || 'info').toUpperCase()}] {r.title}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>{new Date(r.created_at).toLocaleTimeString()}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function StatusPill({ label, ok, colors, testId, neutral }: { label: string; ok: boolean; colors: any; testId: string; neutral?: boolean }) {
  const color = neutral ? colors.textSec : ok ? (colors.success || 'var(--app-success)') : (colors.textMuted || 'var(--app-text-muted)');
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: `${color}40`, backgroundColor: `${color}14` }} data-testid={testId} testID={testId}>
      {!neutral && <View style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: color }} />}
      <Text style={{ color, fontSize: 11, fontWeight: '700' }}>{label}{!neutral ? (ok ? ' connected' : ' not set') : ''}</Text>
    </View>
  );
}

function WebhookInput({ placeholder, value, onChangeText, colors, testId }: { placeholder: string; value: string; onChangeText: (v: string) => void; colors: any; testId: string }) {
  // Lazy-import React Native's TextInput to avoid the top-of-file noise
  const { TextInput } = require('react-native');
  return (
    <TextInput
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor={colors.textMuted}
      autoCapitalize="none"
      autoCorrect={false}
      style={{
        borderWidth: 1, borderColor: colors.border, borderRadius: 10,
        paddingHorizontal: 12, paddingVertical: 10, color: colors.text,
        backgroundColor: colors.bgSoft, fontSize: 12,
      }}
      data-testid={testId} testID={testId}
    />
  );
}

function KpiCard({ label, value, accent, testId }: { label: string; value: number; accent: string; testId: string }) {    const { colors } = useTheme();
  return (
    <View style={{ flex: 1, minWidth: 180, borderRadius: 14, borderWidth: 1, borderColor: `${accent}30`, backgroundColor: colors.bgSoft, padding: 14 }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6 }}>{label}</Text>
      <Text style={{ color: accent, fontSize: 28, fontWeight: '800', marginTop: 8 }}>{value}</Text>
    </View>
  );
}

function SectionCard({ title, subtitle, children, colors, testId }: { title: string; subtitle: string; children: React.ReactNode; colors: any; testId: string }) {
  return (
    <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 18, gap: 14 }} data-testid={testId} testID={testId}>
      <View>
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{title}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>{subtitle}</Text>
      </View>
      {children}
    </View>
  );
}

function EmptyState({ colors, icon, label, testId }: { colors: any; icon: string; label: string; testId: string }) {
  return (
    <View style={{ alignItems: 'center', paddingVertical: 20 }} data-testid={testId} testID={testId}>
      <Ionicons name={icon as any} size={28} color={colors.textMuted} />
      <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{label}</Text>
    </View>
  );
}

function CenteredLoader({ color, label, testId }: { color: string; label: string; testId: string }) {
  return (
    <View style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 48 }} data-testid={testId} testID={testId}>
      <ActivityIndicator size="large" color={color} />
      <Text style={{ color, fontSize: 12, marginTop: 12 }}>{label}</Text>
    </View>
  );
}

function heroCard(colors: any, darkMode: boolean) {
  return {
    borderRadius: 22,
    borderWidth: 1,
    borderColor: `${colors.primary}32`,
    padding: 20,
    backgroundColor: colors.surface,
    ...(darkMode ? { boxShadow: '0 8px 30px rgba(0,0,0,0.28)' } : { boxShadow: '0 10px 32px rgba(15,118,110,0.10)' }),
  } as any;
}

function secondaryButton(colors: any) {
  return {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgSoft,
  } as any;
}