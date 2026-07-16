import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import { useAuth } from '../../src/context/AuthContext';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

import { useTranslation } from '../../src/hooks/useTranslation';
const ssoColors = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-surface)' as any,
  cardAlt: 'var(--app-surface-hover)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  muted: 'var(--app-text-muted)' as any,
  cyan: 'var(--app-primary)' as any,
  green: 'var(--app-success)' as any,
  amber: 'var(--app-warning)' as any,
  red: 'var(--app-error)' as any,
  blue: 'var(--app-info)' as any,
};

const blur = Platform.OS === 'web' ? ({ backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any) : {};

type ProviderStatus = {
  provider: string;
  status: string;
  callback_url?: string;
  issues?: string[];
};

type DebugEvent = {
  event_id: string;
  timestamp: string;
  provider: string;
  phase: string;
  user_id?: string | null;
  details?: Record<string, any>;
};

type DebugPayload = {
  deployment_domain: string;
  summary: { health: string; total: number; configured: number; issues: number };
  providers: ProviderStatus[];
  events: DebugEvent[];
  count: number;
  stored_count?: number;
  retention_policy?: { retention_days: number; max_events: number };
};

export default function SSODebugPage() {
  const { t } = useTranslation();
  t('i18n.route.auth.sso-debug.probe');
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState('');
  const [error, setError] = useState('');
  const [data, setData] = useState<DebugPayload | null>(null);

  const fetchDebug = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      setError('');
      const res = await api.get('/admin/sso-debug?limit=80');
      setData(res.data);
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Failed to load SSO debug data';
      handleAppRecoverableError({
        scope: 'auth.sso-debug.fetch',
        error: e,
        message,
        setError,
        onRetry: () => { void fetchDebug(isManual); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchDebug();
    const iv = setInterval(() => fetchDebug(), 10000);
    return () => clearInterval(iv);
  }, [fetchDebug]);

  const runCleanup = useCallback(async () => {
    setCleanupLoading(true);
    setCleanupMessage('Running cleanup...');
    try {
      const res = await api.post('/admin/sso-debug/cleanup');
      const payload = res.data || {};
      setCleanupMessage(`Cleanup complete · old: ${payload.removed_old ?? 0} · overflow: ${payload.removed_overflow ?? 0} · stored: ${payload.total_after ?? 0}`);
      await fetchDebug(true);
    } catch (e: any) {
      const message = e?.response?.data?.detail || 'Cleanup failed';
      handleAppRecoverableError({
        scope: 'auth.sso-debug.cleanup',
        error: e,
        message,
        setError: setCleanupMessage,
        onRetry: () => { void runCleanup(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setCleanupMessage(message);
    } finally {
      setCleanupLoading(false);
    }
  }, [fetchDebug]);

  if (!user) {
    return (
      <View style={s.root}>
        <View style={s.center} data-testid="sso-debug-auth-required" testID="sso-debug-auth-required">
          <Text style={s.errText}>Please sign in to view SSO diagnostics.</Text>
        </View>
      </View>
    );
  }

  if (!user.is_admin) {
    return (
      <View style={s.root}>
        <View style={s.center} data-testid="sso-debug-admin-required" testID="sso-debug-admin-required">
          <Text style={s.errText}>Admin access required.</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={s.root} data-testid="sso-debug-page" testID="sso-debug-page">
      <ScrollView contentContainerStyle={s.content}>
          <View style={s.headerRow}>
            <View>
              <Text style={s.title} data-testid="sso-debug-title" testID="sso-debug-title">SSO Debug Console</Text>
              <Text style={s.sub} data-testid="sso-debug-domain" testID="sso-debug-domain">{data?.deployment_domain || 'Loading domain...'}</Text>
            </View>
            <View style={s.headerActions}>
              <TouchableOpacity
                style={s.refreshBtn}
                onPress={() => fetchDebug(true)}
                {...(Platform.OS === 'web' ? ({ onClick: () => fetchDebug(true) } as any) : {})}
                disabled={refreshing}
                data-testid="sso-debug-refresh-button" testID="sso-debug-refresh-button"
              >
                {refreshing ? <ActivityIndicator size="small" color={ssoColors.cyan} /> : <Ionicons name="refresh" size={16} color={ssoColors.cyan} />}
                <Text style={s.refreshText}>Refresh</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={s.cleanupBtn}
                onPress={runCleanup}
                {...(Platform.OS === 'web' ? ({ onClick: runCleanup } as any) : {})}
                disabled={cleanupLoading}
                data-testid="sso-debug-cleanup-button" testID="sso-debug-cleanup-button"
              >
                {cleanupLoading ? <ActivityIndicator size="small" color={ssoColors.amber} /> : <Ionicons name="trash-outline" size={16} color={ssoColors.amber} />}
                <Text style={s.cleanupText}>Cleanup</Text>
              </TouchableOpacity>
            </View>
          </View>

          {error ? (
            <View style={s.errorCard} data-testid="sso-debug-error" testID="sso-debug-error">
              <Ionicons name="warning-outline" size={16} color={ssoColors.red} />
              <Text style={s.errText}>{error}</Text>
            </View>
          ) : null}

          <View style={s.summaryCard} data-testid="sso-debug-summary-card" testID="sso-debug-summary-card">
            <Text style={s.sectionTitle}>Health: <Text data-testid="sso-debug-health-value" testID="sso-debug-health-value">{data?.summary?.health || '—'}</Text></Text>
            <Text style={s.meta} data-testid="sso-debug-summary-counts" testID="sso-debug-summary-counts">
              Providers: {data?.summary?.configured ?? 0}/{data?.summary?.total ?? 0} configured · Issues: {data?.summary?.issues ?? 0}
            </Text>
            <Text style={s.meta} data-testid="sso-debug-retention-policy" testID="sso-debug-retention-policy">
              Retention: {data?.retention_policy?.retention_days ?? 30} days · Max events: {data?.retention_policy?.max_events ?? 10000} · Stored: {data?.stored_count ?? 0}
            </Text>
            {cleanupMessage ? (
              <Text style={s.cleanupMsg} data-testid="sso-debug-cleanup-message" testID="sso-debug-cleanup-message">{cleanupMessage}</Text>
            ) : null}
          </View>

          <Text style={s.sectionTitle} data-testid="sso-debug-provider-section-title" testID="sso-debug-provider-section-title">Provider Status</Text>
          {(data?.providers || []).map((provider) => (
            <View key={provider.provider} style={s.providerCard} data-testid={`sso-debug-provider-${provider.provider}`} testID={`sso-debug-provider-${provider.provider}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="shield-checkmark" size={15} color={provider.status === 'configured' ? ssoColors.green : ssoColors.amber} />
                <Text style={s.providerName}>{provider.provider.toUpperCase()}</Text>
                <Text style={[s.badge, { color: provider.status === 'configured' ? ssoColors.green : ssoColors.amber }]} data-testid={`sso-debug-status-${provider.provider}`} testID={`sso-debug-status-${provider.provider}`}>
                  {provider.status}
                </Text>
              </View>
              <Text style={s.meta} data-testid={`sso-debug-callback-${provider.provider}`} testID={`sso-debug-callback-${provider.provider}`}>{provider.callback_url || 'No callback URL'}</Text>
              {!!provider.issues?.length && <Text style={s.issueText}>Issues: {provider.issues.join(' · ')}</Text>}
            </View>
          ))}

          <Text style={s.sectionTitle} data-testid="sso-debug-events-section-title" testID="sso-debug-events-section-title">Recent SSO Telemetry ({data?.count ?? 0})</Text>
          {loading ? (
            <View style={s.loadingCard} data-testid="sso-debug-loading" testID="sso-debug-loading">
              <ActivityIndicator size="small" color={ssoColors.cyan} />
              <Text style={s.meta}>Loading telemetry events...</Text>
            </View>
          ) : (data?.events || []).length === 0 ? (
            <View style={s.loadingCard} data-testid="sso-debug-no-events" testID="sso-debug-no-events">
              <Text style={s.meta}>No telemetry events yet. Trigger SSO buttons in preview first.</Text>
            </View>
          ) : (
            (data?.events || []).map((evt, idx) => (
              <View key={`${evt.event_id}-${idx}`} style={s.eventCard} data-testid={`sso-debug-event-${idx}`} testID={`sso-debug-event-${idx}`}>
                <Text style={s.eventHead}>{evt.provider?.toUpperCase()} · {evt.phase}</Text>
                <Text style={s.meta} data-testid={`sso-debug-event-time-${idx}`} testID={`sso-debug-event-time-${idx}`}>{evt.timestamp}</Text>
                <Text style={s.meta}>
                  iframe={String(evt.details?.iframe_mode)} · crossOrigin={String(evt.details?.cross_origin_iframe)} · method={evt.details?.popup_method || '—'}
                </Text>
                {evt.details?.note ? <Text style={s.issueText}>note: {evt.details.note}</Text> : null}
              </View>
            ))
          )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: ssoColors.bg },
  content: { padding: 16, paddingBottom: 80, gap: 12 },
  center: { flex: 1, minHeight: 320, justifyContent: 'center', alignItems: 'center', backgroundColor: ssoColors.bg },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 24, fontWeight: '800', color: ssoColors.text },
  sub: { fontSize: 12, color: ssoColors.muted, marginTop: 4 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: ssoColors.text },
  refreshBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(ssoColors.cyan, '55'), backgroundColor: (globalThis as any).__alphaColor(ssoColors.cyan, '12'), borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 },
  refreshText: { color: ssoColors.cyan, fontSize: 12, fontWeight: '700' },
  cleanupBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(ssoColors.amber, '55'), backgroundColor: (globalThis as any).__alphaColor(ssoColors.amber, '10'), borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 },
  cleanupText: { color: ssoColors.amber, fontSize: 12, fontWeight: '700' },
  cleanupMsg: { color: ssoColors.green, fontSize: 11, marginTop: 6 },
  summaryCard: { borderWidth: 1, borderColor: ssoColors.border, borderRadius: 12, backgroundColor: ssoColors.card, padding: 12, ...blur },
  providerCard: { borderWidth: 1, borderColor: ssoColors.border, borderRadius: 12, backgroundColor: ssoColors.cardAlt, padding: 12, gap: 6, ...blur },
  eventCard: { borderWidth: 1, borderColor: ssoColors.border, borderRadius: 10, backgroundColor: ssoColors.card, padding: 10, gap: 4, ...blur },
  loadingCard: { borderWidth: 1, borderColor: ssoColors.border, borderRadius: 10, backgroundColor: ssoColors.card, padding: 14, alignItems: 'center', gap: 8 },
  errorCard: { borderWidth: 1, borderColor: (globalThis as any).__alphaColor(ssoColors.red, '55'), borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(ssoColors.red, '10'), padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8 },
  providerName: { color: ssoColors.text, fontWeight: '700', fontSize: 13 },
  badge: { fontWeight: '700', fontSize: 11, textTransform: 'uppercase' },
  eventHead: { color: ssoColors.text, fontSize: 12, fontWeight: '700' },
  meta: { color: ssoColors.muted, fontSize: 11 },
  issueText: { color: ssoColors.amber, fontSize: 11 },
  errText: { color: ssoColors.red, fontSize: 13, fontWeight: '600' },
});
