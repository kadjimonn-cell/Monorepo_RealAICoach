/**
 * Admin · GDPR Self-Service Dashboard
 * -----------------------------------
 * Read-only compliance audit view:
 *   • KPIs: total requests, last 24h, pending, exports, deletes
 *   • Request table (filter by status + action)
 *   • Audit log tail (who did what, when, how many rows)
 */
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { AdminRouteGate } from '../../src/components/auth/AdminRouteGate';
import { resolveRuntimeBaseUrl } from '../../src/utils/runtimeBaseUrl';

const API = resolveRuntimeBaseUrl();

interface GDPRRequest {
  request_id: string;
  email_hash: string;
  action: 'export' | 'delete';
  status: string;
  created_at: string;
  completed_at?: string;
  record_counts_at_request?: Record<string, number>;
  record_counts_at_execute?: Record<string, number>;
  deleted_counts?: Record<string, number>;
  ip?: string;
}

interface AuditEntry {
  request_id: string;
  email_hash: string;
  action: string;
  result: string;
  counts: Record<string, number>;
  timestamp: string;
  ip?: string;
}

function Chip({ label, active, onPress, color, inactiveBorder, inactiveText }: any) {
  return (
    <TouchableOpacity
      onPress={onPress}
      data-testid={`gdpr-admin-chip-${label.toLowerCase().replace(/\s+/g, '-')}`}
      style={{
        paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999,
        borderWidth: 1.5, borderColor: active ? color : inactiveBorder,
        backgroundColor: active ? (globalThis as any).__alphaColor(color, '18') : 'transparent', marginRight: 8, marginBottom: 8,
      }}>
      <Text style={{ color: active ? color : inactiveText, fontSize: 12, fontWeight: '700' }}>{label}</Text>
    </TouchableOpacity>
  );
}

export default function AdminGDPRRequests() {
  const { t } = useTranslation();
  t('i18n.route.admin.gdpr-requests.probe');
  const { colors } = useTheme();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const isNarrow = width < 900;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requests, setRequests] = useState<GDPRRequest[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending_verification' | 'completed'>('all');
  const [actionFilter, setActionFilter] = useState<'all' | 'export' | 'delete'>('all');

  const kpis = [
    { label: tx('admin.gdpr.kpi.totalRequests', 'Total requests'), value: counts.total ?? 0, icon: 'albums-outline', color: colors.indigoText || colors.primary },
    { label: tx('admin.gdpr.kpi.last24h', 'Last 24h'), value: counts.last_24h ?? 0, icon: 'time-outline', color: colors.primary },
    { label: tx('admin.gdpr.kpi.pendingVerify', 'Pending verify'), value: counts.pending_verification ?? 0, icon: 'mail-unread-outline', color: colors.warningText },
    { label: tx('admin.gdpr.kpi.exportsDone', 'Exports done'), value: counts.exports_completed ?? 0, icon: 'download-outline', color: colors.successText },
    { label: tx('admin.gdpr.kpi.deletesDone', 'Deletes done'), value: counts.deletes_completed ?? 0, icon: 'trash-outline', color: colors.error },
  ];

  // Retention policy state
  const [retentionDays, setRetentionDays] = useState<number>(0);
  const [retentionUpdatedAt, setRetentionUpdatedAt] = useState<string | null>(null);
  const [retentionMetrics, setRetentionMetrics] = useState<{ runs_completed: number; total_purged: number } | null>(null);
  const [savingRetention, setSavingRetention] = useState(false);

  // Email health summary state
  const [emailHealth, setEmailHealth] = useState<any>(null);

  // Email template preview modal state
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<{ subject: string; html: string; label?: string } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const openTemplatePreview = useCallback(async (key: string) => {
    setPreviewKey(key);
    setPreviewData(null);
    setPreviewError(null);
    setPreviewLoading(true);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('session_token') : '';
      const res = await fetch(`${API}/api/admin/executive/templates/${encodeURIComponent(key)}/preview`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json', Authorization: `Bearer ${token || ''}` },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error(tx('admin.gdpr.errors.previewUnavailableWithHttp', 'Preview unavailable (HTTP {status})').replace('{status}', String(res.status)));
      const json = await res.json();
      setPreviewData({ subject: json.subject || '', html: json.html || '', label: json.label });
    } catch (e: any) {
      setPreviewError(e.message || tx('admin.gdpr.errors.previewFailed', 'Preview failed'));
    } finally {
      setPreviewLoading(false);
    }
  }, [tx]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('session_token') : '';
      const hdrs = { 'X-Requested-With': 'XMLHttpRequest', Authorization: `Bearer ${token || ''}` };
      const [rRes, aRes, pRes, mRes, ehRes] = await Promise.all([
        fetch(`${API}/api/gdpr/admin/requests?status=${statusFilter}&action=${actionFilter}&limit=100`, { headers: hdrs }),
        fetch(`${API}/api/gdpr/admin/audit-log?limit=100`, { headers: hdrs }),
        fetch(`${API}/api/gdpr/admin/retention-policy`, { headers: hdrs }),
        fetch(`${API}/api/gdpr/admin/retention/metrics?days_back=30`, { headers: hdrs }),
        fetch(`${API}/api/admin/email-health/summary?window_hours=24`, { headers: hdrs }),
      ]);
      if (!rRes.ok || !aRes.ok) {
        throw new Error(tx('admin.gdpr.errors.httpWithStatuses', 'HTTP {rStatus}/{aStatus}')
          .replace('{rStatus}', String(rRes.status))
          .replace('{aStatus}', String(aRes.status)));
      }
      const rJson = await rRes.json();
      const aJson = await aRes.json();
      setRequests(rJson.requests || []);
      setCounts(rJson.counts || {});
      setAudit(aJson.entries || []);
      if (pRes.ok) {
        const pJson = await pRes.json();
        setRetentionDays(pJson.policy?.retention_days ?? 0);
        setRetentionUpdatedAt(pJson.policy?.updated_at || null);
      }
      if (mRes.ok) {
        const mJson = await mRes.json();
        setRetentionMetrics({ runs_completed: mJson.runs_completed || 0, total_purged: mJson.total_purged || 0 });
      }
      if (ehRes.ok) {
        setEmailHealth(await ehRes.json());
      }
    } catch (e: any) {
      setError(e.message || tx('admin.gdpr.errors.failedToLoad', 'Failed to load'));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, actionFilter, tx]);

  const saveRetention = useCallback(async (days: number) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('session_token') : '';
    setSavingRetention(true);
    try {
      const res = await fetch(`${API}/api/gdpr/admin/retention-policy`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          Authorization: `Bearer ${token || ''}`,
        },
        body: JSON.stringify({ retention_days: days }),
      });
      if (!res.ok) throw new Error(await res.text());
      setRetentionDays(days);
      const j = await res.json();
      setRetentionUpdatedAt(j.updated_at || null);
    } catch (e: any) {
      if (typeof window !== 'undefined') {
        window.alert(tx('admin.gdpr.alerts.saveFailedWithError', 'Save failed: {error}').replace('{error}', e.message || tx('common.error', 'Something went wrong')));
      }
    } finally {
      setSavingRetention(false);
    }
  }, [tx]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const fmtDate = (iso?: string) => iso ? new Date(iso).toLocaleString() : tx('admin.gdpr.common.naDash', '—');
  const sumCounts = (c?: Record<string, number>) => c ? Object.entries(c).filter(([k]) => k !== 'total').reduce((a, [, v]) => a + (v || 0), 0) : 0;

  return (
    <AdminRouteGate returnTo="/admin/gdpr-requests">
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: isNarrow ? 16 : 28 }}
      data-testid="admin-gdpr-dashboard">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 26, fontWeight: '800' }}>{tx('admin.gdpr.header.title', 'GDPR Self-Service')}</Text>
          <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 2 }}>
            {tx('admin.gdpr.header.subtitle', 'Compliance audit — export & deletion requests, permanent trail')}
          </Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <TouchableOpacity
            onPress={fetchData}
            data-testid="admin-gdpr-refresh"
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10, borderWidth: 1, borderColor: colors.glassBorder }}>
            <Ionicons name="refresh-outline" size={16} color={colors.text} />
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.gdpr.actions.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={async () => {
              const tk = typeof window !== 'undefined' ? localStorage.getItem('session_token') : '';
              try {
                const r = await fetch(`${API}/api/gdpr/admin/send-digest-now`, {
                  method: 'POST',
                  headers: { 'X-Requested-With': 'XMLHttpRequest', Authorization: `Bearer ${tk || ''}` },
                });
                const j = await r.json();
                if (!r.ok) throw new Error(j.detail || tx('admin.gdpr.errors.failed', 'failed'));
                if (typeof window !== 'undefined') window.alert(
                  tx('admin.gdpr.alerts.digestResult', 'Digest {status} to {recipient}\n{count} request(s) in window.')
                    .replace('{status}', j.sent_ok ? tx('admin.gdpr.common.sent', 'sent') : tx('admin.gdpr.common.failedUpper', 'FAILED'))
                    .replace('{recipient}', String(j.recipient || ''))
                    .replace('{count}', String(j.summary?.total_requests ?? 0))
                );
              } catch (e: any) {
                if (typeof window !== 'undefined') {
                  window.alert(tx('admin.gdpr.alerts.digestErrorWithMessage', 'Digest error: {message}').replace('{message}', e.message || tx('common.error', 'Something went wrong')));
                }
              }
            }}
            data-testid="admin-gdpr-send-digest-now"
            style={{ marginLeft: 8, flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10, backgroundColor: colors.primary }}>
            <Ionicons name="mail-outline" size={16} color={colors.primaryText} />
            <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('admin.gdpr.actions.sendDigestNow', 'Send digest now')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* KPIs */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }}>
        {kpis.map((k) => (
          <View
            key={k.label}
            data-testid={`gdpr-kpi-${k.label.toLowerCase().replace(/\s+/g, '-')}`}
            style={{
              flex: isNarrow ? undefined : 1, minWidth: 160,
              backgroundColor: colors.card, borderColor: colors.glassBorder, borderWidth: 1,
              borderLeftColor: k.color, borderLeftWidth: 4,
              borderRadius: 12, padding: 14,
            }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={k.icon as any} size={18} color={k.color} />
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.4 }}>{k.label}</Text>
            </View>
            <Text style={{ color: k.color, fontSize: 26, fontWeight: '800', marginTop: 6 }}>{k.value}</Text>
          </View>
        ))}
      </View>

      {/* Email Health card */}
      {emailHealth && (
        <View
          data-testid="email-health-card"
          style={{
            backgroundColor: colors.card,
            borderColor: colors.glassBorder,
            borderWidth: 1,
            borderLeftColor: emailHealth.template_key_violations > 0 ? 'var(--app-error)' : 'var(--app-success)',
            borderLeftWidth: 4,
            borderRadius: 12,
            padding: 16,
            marginBottom: 16,
          }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Ionicons name="mail-outline" size={18} color={emailHealth.template_key_violations > 0 ? 'var(--app-error)' : 'var(--app-success)'} />
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 15 }}>{tx('admin.gdpr.emailHealth.title', 'Email health · last 24h')}</Text>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14 }}>
            <View data-testid="email-health-sent"><Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.gdpr.emailHealth.labels.sent', 'Sent')}</Text><Text style={{ color: colors.text, fontSize: 22, fontWeight: '800' }}>{emailHealth.sent}</Text></View>
            <View data-testid="email-health-violations"><Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.gdpr.emailHealth.labels.v7Violations', 'v7 violations')}</Text><Text style={{ color: emailHealth.template_key_violations > 0 ? colors.error : colors.success, fontSize: 22, fontWeight: '800' }}>{emailHealth.template_key_violations}</Text></View>
            <View data-testid="email-health-bounced"><Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.gdpr.emailHealth.labels.bounced', 'Bounced')}</Text><Text style={{ color: emailHealth.bounced > 0 ? colors.warning : colors.text, fontSize: 22, fontWeight: '800' }}>{emailHealth.bounced}</Text></View>
            <View data-testid="email-health-complained"><Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.gdpr.emailHealth.labels.complaints', 'Complaints')}</Text><Text style={{ color: emailHealth.complained > 0 ? colors.error : colors.text, fontSize: 22, fontWeight: '800' }}>{emailHealth.complained}</Text></View>
            <View data-testid="email-health-delivery-rate"><Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.gdpr.emailHealth.labels.deliveryRate', 'Delivery rate')}</Text><Text style={{ color: colors.text, fontSize: 22, fontWeight: '800' }}>{emailHealth.delivery_rate}%</Text></View>
          </View>
          {Array.isArray(emailHealth.top_templates) && emailHealth.top_templates.length > 0 && (
            <View style={{ marginTop: 12 }}>
              <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', marginBottom: 6 }}>{tx('admin.gdpr.emailHealth.topTemplates', 'Top templates · tap to preview')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                {emailHealth.top_templates.slice(0, 6).map((t: any) => (
                  <TouchableOpacity
                    key={t.template}
                    onPress={() => openTemplatePreview(t.template)}
                    data-testid={`email-health-top-${t.template}`}
                    accessibilityLabel={tx('admin.gdpr.emailHealth.previewTemplateWithName', 'Preview {name} email template').replace('{name}', t.template)}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.glassBorder, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 }}>
                    <Ionicons name="eye-outline" size={12} color={colors.primary} />
                    <Text style={{ color: colors.textSec, fontSize: 12 }}>{t.template} <Text style={{ color: colors.text, fontWeight: '700' }}>· {t.count}</Text></Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}
        </View>
      )}

      {/* Email template preview modal */}
      {previewKey && (
        <View data-testid="email-template-preview-modal" style={{ position: 'absolute' as any, top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 9999, alignItems: 'center', justifyContent: 'center', padding: 16 } as any}>
          <View style={{ backgroundColor: colors.card, borderRadius: 14, borderWidth: 1, borderColor: colors.glassBorder, width: '100%' as any, maxWidth: 960, maxHeight: '90%' as any, overflow: 'hidden' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.glassBorder }}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.gdpr.preview.title', 'Email preview')}</Text>
                <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800' }} numberOfLines={1}>{previewData?.label || previewKey}</Text>
                {previewData?.subject ? (
                  <Text style={{ color: colors.textSec, fontSize: 12, marginTop: 2 }} numberOfLines={1}>{tx('admin.gdpr.preview.subject', 'Subject')}: {previewData.subject}</Text>
                ) : null}
              </View>
              <TouchableOpacity
                data-testid="email-template-preview-close"
                onPress={() => { setPreviewKey(null); setPreviewData(null); setPreviewError(null); }}
                style={{ padding: 8, borderRadius: 8, backgroundColor: colors.bg, marginLeft: 12 }}>
                <Ionicons name="close" size={18} color={colors.text} />
              </TouchableOpacity>
            </View>
            <ScrollView style={{ flex: 1, backgroundColor: colors.primaryText }} contentContainerStyle={{ padding: 16 }}>
              {previewLoading ? (
                <View data-testid="email-template-preview-loading" style={{ padding: 48, alignItems: 'center' }}>
                  <ActivityIndicator size="large" color={colors.primary} />
                  <Text style={{ marginTop: 10, color: colors.textMuted }}>{tx('admin.gdpr.preview.rendering', 'Rendering preview…')}</Text>
                </View>
              ) : previewError ? (
                <View data-testid="email-template-preview-error" style={{ padding: 24, alignItems: 'center' }}>
                  <Ionicons name="warning-outline" size={22} color="var(--app-error)" />
                  <Text style={{ marginTop: 8, color: colors.error, fontWeight: '600' }}>{previewError}</Text>
                </View>
              ) : previewData?.html ? (
                // @ts-ignore — react-native-web supports iframe
                <iframe
                  data-testid="email-template-preview-iframe"
                  srcDoc={previewData.html}
                  title={tx('admin.gdpr.preview.iframeTitleWithName', 'Preview: {name}').replace('{name}', previewData.label || previewKey || '')}
                  sandbox=""
                  style={{ width: '100%', minHeight: 520, border: 'none', background: colors.primaryText } as any}
                />
              ) : null}
            </ScrollView>
          </View>
        </View>
      )}

      {/* Retention Policy card */}
      <View
        data-testid="gdpr-retention-card"
        style={{
          backgroundColor: colors.card,
          borderColor: colors.glassBorder,
          borderWidth: 1,
          borderRadius: 12,
          padding: 16,
          marginBottom: 24,
          flexDirection: isNarrow ? 'column' : 'row',
          alignItems: isNarrow ? 'flex-start' : 'center',
          gap: 16,
        }}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <Ionicons name="timer-outline" size={18} color="var(--app-primary)" />
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 15 }}>{tx('admin.gdpr.retention.title', 'Data retention policy')}</Text>
          </View>
          <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 17 }}>
            {tx('admin.gdpr.retention.description', 'Auto-purges contact submissions, support tickets, and feedback older than the selected window. Runs nightly at 03:45 UTC.')}
            {retentionUpdatedAt ? tx('admin.gdpr.retention.lastUpdatedWithTime', ' · Last updated: {time}').replace('{time}', new Date(retentionUpdatedAt).toLocaleString()) : ''}
          </Text>
          {retentionMetrics && (
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 6 }} data-testid="gdpr-retention-metrics">
              {tx('admin.gdpr.retention.last30Days', 'Last 30 days')}: <Text style={{ color: colors.text, fontWeight: '700' }}>{retentionMetrics.runs_completed}</Text> {tx('admin.gdpr.retention.runs', 'runs')} ·{' '}
              <Text style={{ color: colors.error, fontWeight: '700' }}>{retentionMetrics.total_purged}</Text> {tx('admin.gdpr.retention.recordsPurged', 'records purged')}
            </Text>
          )}
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {([0, 30, 90, 180, 365] as const).map((d) => {
            const selected = retentionDays === d;
            const label = d === 0 ? tx('admin.gdpr.retention.never', 'Never') : `${d}d`;
            return (
              <TouchableOpacity
                key={d}
                disabled={savingRetention}
                onPress={() => saveRetention(d)}
                data-testid={`gdpr-retention-set-${d}`}
                style={{
                  paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8,
                  borderWidth: 1.5,
                  borderColor: selected ? colors.accent : colors.glassBorder,
                  backgroundColor: selected ? colors.accentSoft : 'transparent',
                  opacity: savingRetention ? 0.6 : 1,
                }}>
                <Text style={{ color: selected ? colors.accent : colors.text, fontSize: 13, fontWeight: '700' }}>{label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {/* Filters */}
      <View style={{ marginBottom: 16 }}>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700', marginBottom: 8, textTransform: 'uppercase' }}>{tx('admin.gdpr.filters.status', 'Status')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          {(['all', 'pending_verification', 'completed'] as const).map((s) => (
            <Chip key={s} label={s === 'pending_verification' ? tx('admin.gdpr.status.pending', 'Pending') : tx(`admin.gdpr.status.${s}`, s[0].toUpperCase() + s.slice(1))}
                  active={statusFilter === s} onPress={() => setStatusFilter(s)} color={colors.indigoText || colors.primary} inactiveBorder={colors.textSecondary + '33'} inactiveText={colors.textMuted} />
          ))}
        </View>
        <Text style={{ color: colors.textSec, fontSize: 11, fontWeight: '700', marginBottom: 8, marginTop: 6, textTransform: 'uppercase' }}>{tx('admin.gdpr.filters.action', 'Action')}</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          {(['all', 'export', 'delete'] as const).map((a) => (
            <Chip key={a} label={tx(`admin.gdpr.action.${a}`, a[0].toUpperCase() + a.slice(1))} active={actionFilter === a} onPress={() => setActionFilter(a)} color={a === 'delete' ? colors.error : colors.successText} inactiveBorder={colors.textSecondary + '33'} inactiveText={colors.textMuted} />
          ))}
        </View>
      </View>

      {loading ? (
        <View style={{ paddingVertical: 60, alignItems: 'center' }}>
          <ActivityIndicator color={colors.text} />
        </View>
      ) : error ? (
        <Text style={{ color: colors.error }}>{error}</Text>
      ) : (
        <>
          {/* Requests table */}
          <View style={{ backgroundColor: colors.card, borderColor: colors.glassBorder, borderWidth: 1, borderRadius: 12, overflow: 'hidden', marginBottom: 24 }} data-testid="gdpr-requests-table">
            <View style={{ flexDirection: 'row', padding: 12, backgroundColor: colors.bg, borderBottomWidth: 1, borderColor: colors.glassBorder }}>
              <Text style={{ color: colors.textSec, flex: 2, fontSize: 11, fontWeight: '700' }}>{tx('admin.gdpr.table.request', 'REQUEST')}</Text>
              <Text style={{ color: colors.textSec, flex: 1, fontSize: 11, fontWeight: '700' }}>{tx('admin.gdpr.table.action', 'ACTION')}</Text>
              <Text style={{ color: colors.textSec, flex: 1, fontSize: 11, fontWeight: '700' }}>{tx('admin.gdpr.table.status', 'STATUS')}</Text>
              <Text style={{ color: colors.textSec, flex: 1, fontSize: 11, fontWeight: '700' }}>{tx('admin.gdpr.table.records', 'RECORDS')}</Text>
              {!isNarrow && <Text style={{ color: colors.textSec, flex: 2, fontSize: 11, fontWeight: '700' }}>{tx('admin.gdpr.table.created', 'CREATED')}</Text>}
            </View>
            {requests.length === 0 ? (
              <Text style={{ color: colors.textMuted, padding: 20, textAlign: 'center' }}>{tx('admin.gdpr.states.noRequestsMatchFilters', 'No requests match the current filters.')}</Text>
            ) : requests.map((r) => {
              const records = sumCounts(r.record_counts_at_execute || r.deleted_counts || r.record_counts_at_request);
              return (
                <View key={r.request_id} data-testid={`gdpr-request-row-${r.request_id}`} style={{ flexDirection: 'row', padding: 12, borderBottomWidth: 1, borderColor: colors.glassBorder }}>
                  <View style={{ flex: 2 }}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>{r.request_id}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 11 }} numberOfLines={1}>{tx('admin.gdpr.table.hash', 'hash')}: {r.email_hash.slice(0, 16)}…</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: r.action === 'delete' ? colors.error : colors.success, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' }}>{r.action}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: r.status === 'completed' ? colors.success : colors.warning, fontSize: 12, fontWeight: '600' }}>
                      {r.status === 'pending_verification' ? tx('admin.gdpr.status.pendingLower', 'pending') : r.status}
                    </Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{records}</Text>
                  </View>
                  {!isNarrow && (
                    <View style={{ flex: 2 }}>
                      <Text style={{ color: colors.textSec, fontSize: 12 }} numberOfLines={1}>{fmtDate(r.created_at)}</Text>
                      {r.completed_at && <Text style={{ color: colors.textMuted, fontSize: 11 }} numberOfLines={1}>{tx('admin.gdpr.table.done', 'done')}: {fmtDate(r.completed_at)}</Text>}
                    </View>
                  )}
                </View>
              );
            })}
          </View>

          {/* Audit log */}
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginBottom: 12 }}>{tx('admin.gdpr.audit.title', 'Permanent audit log')}</Text>
          <View style={{ backgroundColor: colors.card, borderColor: colors.glassBorder, borderWidth: 1, borderRadius: 12, overflow: 'hidden' }} data-testid="gdpr-audit-table">
            {audit.length === 0 ? (
              <Text style={{ color: colors.textMuted, padding: 20, textAlign: 'center' }}>{tx('admin.gdpr.audit.noEntriesYet', 'No audit entries yet.')}</Text>
            ) : audit.map((a, i) => (
              <View key={i} data-testid={`gdpr-audit-row-${i}`} style={{ flexDirection: 'row', padding: 12, borderBottomWidth: i === audit.length - 1 ? 0 : 1, borderColor: colors.glassBorder, alignItems: 'center' }}>
                <Ionicons name={a.result === 'deleted' ? 'trash-outline' : 'download-outline'} size={16} color={a.result === 'deleted' ? 'var(--app-error)' : 'var(--app-success)'} style={{ marginRight: 10 }} />
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }}>
                    {a.result === 'deleted' ? tx('admin.gdpr.audit.deleted', 'Deleted') : tx('admin.gdpr.audit.exported', 'Exported')} {sumCounts(a.counts)} {tx('admin.gdpr.audit.records', 'records')}
                  </Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11 }} numberOfLines={1}>
                    {a.request_id} · {tx('admin.gdpr.table.hash', 'hash')}: {a.email_hash.slice(0, 16)}… · {fmtDate(a.timestamp)}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        </>
      )}
    </ScrollView>
    </AdminRouteGate>
  );
}
