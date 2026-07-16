import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

// Theme adapter — maps the v2 admin theme shape onto the short-name palette
// this panel uses. Same pattern as AccessibilityPanel / CodeHealthPanel so
// theme changes propagate through React state.
function makeC(AC: any) {
  return {
    bg: AC.bg,
    bgSoft: AC.surfaceHover,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    textSec: AC.textSec,
    textMuted: AC.textMuted,
    primary: AC.primary,
    primaryText: AC.primaryText || AC.text,
    primarySoft: AC.primarySoft,
    success: AC.success,
    successSoft: AC.successSoft,
    warning: AC.warning,
    warningSoft: AC.warningSoft,
    error: AC.error,
    errorSoft: AC.errorSoft,
    cyan: AC.primary,
    purple: AC.accent || AC.primary,
  };
}

type Entry = {
  entry_id: string;
  kind: string;
  kind_label: string;
  subject: string;
  summary: string;
  recipients: string[];
  recipient_count: number;
  sent_ok: number;
  sent_failed: number;
  payload?: any;
  trigger: string;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  review_notes?: string;
};

type KindStat = { kind: string; label: string; total: number; unreviewed: number };

function formatAgo(iso: string, tx: (key: string, fallback: string) => string): string {
  if (!iso) return tx('admin.complianceDigestHub.common.dash', '—');
  try {
    const t = new Date(iso).getTime();
    const m = Math.floor((Date.now() - t) / 60000);
    if (m < 1) return tx('admin.complianceDigestHub.time.justNow', 'just now');
    if (m < 60) return tx('admin.complianceDigestHub.time.minutesAgo', '{minutes}m ago').replace('{minutes}', String(m));
    const h = Math.floor(m / 60);
    if (h < 24) return tx('admin.complianceDigestHub.time.hoursAgo', '{hours}h ago').replace('{hours}', String(h));
    const d = Math.floor(h / 24);
    return tx('admin.complianceDigestHub.time.daysAgo', '{days}d ago').replace('{days}', String(d));
  } catch { return iso.slice(0, 16); }
}

export default function ComplianceDigestHubPanel() {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [items, setItems] = useState<Entry[]>([]);
  const [kinds, setKinds] = useState<KindStat[]>([]);
  const [filterKind, setFilterKind] = useState<string>('');
  const [filterReviewed, setFilterReviewed] = useState<'all' | 'reviewed' | 'unreviewed'>('unreviewed');
  const [expanded, setExpanded] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>('');
  const [unreviewedTotal, setUnreviewedTotal] = useState(0);
  const [total, setTotal] = useState(0);
  const [_recipients, setRecipients] = useState<string[]>([]);
  const [recipientsInput, setRecipientsInput] = useState('');
  const [recipientsSource, setRecipientsSource] = useState<string>('');
  const [recipientsActive, setRecipientsActive] = useState<string[]>([]);
  const [recipientsSaving, setRecipientsSaving] = useState(false);
  const [recipientsMsg, setRecipientsMsg] = useState<string>('');
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string>('');
  const [platformDigest, setPlatformDigest] = useState<any>(null);

  const fetchFeed = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const params: any = { limit: 50 };
      if (filterKind) params.kind = filterKind;
      if (filterReviewed !== 'all') params.reviewed = filterReviewed;
      const { data } = await api.get('/compliance-digests/feed', { params });
      setItems(data?.items || []);
      setUnreviewedTotal(data?.unreviewed_count || 0);
      setTotal(data?.total || 0);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || tx('admin.complianceDigestHub.errors.loadFeedFailed', 'Failed to load feed'));
    } finally {
      setLoading(false);
    }
  }, [filterKind, filterReviewed]);

  const fetchKinds = useCallback(async () => {
    try {
      const { data } = await api.get('/compliance-digests/kinds');
      setKinds(data?.kinds || []);
    } catch { /* non-fatal */ }
  }, []);

  const fetchRecipients = useCallback(async () => {
    try {
      const { data } = await api.get('/compliance-digests/recipients');
      setRecipients(data?.configured || []);
      setRecipientsActive(data?.active || []);
      setRecipientsSource(data?.active_source || '');
      setRecipientsInput((data?.configured || []).join(', '));
    } catch { /* non-fatal */ }
  }, []);

  const fetchPlatformDigest = useCallback(async () => {
    try {
      const { data } = await api.get('/admin/compliance-digest');
      setPlatformDigest(data?.latest || null);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ComplianceDigestHubPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  useEffect(() => { fetchFeed(); fetchKinds(); fetchRecipients(); fetchPlatformDigest(); }, [fetchFeed, fetchKinds, fetchRecipients, fetchPlatformDigest]);

  const handleMarkReviewed = async (entry_id: string) => {
    setBusyId(entry_id);
    try {
      const notes = reviewNotes[entry_id] || '';
      await api.post(`/compliance-digests/${entry_id}/review`, { notes });
      await fetchFeed(); await fetchKinds();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || tx('admin.complianceDigestHub.errors.markReviewedFailed', 'Mark reviewed failed'));
    } finally { setBusyId(''); }
  };

  const handleUnreview = async (entry_id: string) => {
    setBusyId(entry_id);
    try {
      await api.post(`/compliance-digests/${entry_id}/unreview`);
      await fetchFeed(); await fetchKinds();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || tx('admin.complianceDigestHub.errors.unreviewFailed', 'Unreview failed'));
    } finally { setBusyId(''); }
  };

  const handleSaveRecipients = async () => {
    setRecipientsSaving(true); setRecipientsMsg('');
    try {
      const emails = recipientsInput
        .split(/[,\n]+/)
        .map((e) => e.trim())
        .filter((e) => e.includes('@'));
      await api.put('/compliance-digests/recipients', { emails });
      setRecipientsMsg(
        tx('admin.complianceDigestHub.recipients.savedWithCount', 'Saved ({count} recipient{plural})')
          .replace('{count}', String(emails.length))
          .replace('{plural}', emails.length === 1 ? '' : 's')
      );
      await fetchRecipients();
    } catch (e: any) {
      setRecipientsMsg(
        tx('admin.complianceDigestHub.recipients.saveFailedWithError', 'Save failed: {error}')
          .replace('{error}', e?.response?.data?.detail || e?.message || tx('admin.complianceDigestHub.common.unknown', 'unknown'))
      );
    } finally { setRecipientsSaving(false); }
  };

  const handleRunGdprDigestNow = async () => {
    setBusyId('gdpr_run_now');
    try {
      await api.post('/careers/gdpr/digest/run-now');
      await fetchFeed(); await fetchKinds();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || tx('admin.complianceDigestHub.errors.runNowFailed', 'Run-now failed'));
    } finally { setBusyId(''); }
  };

  const handleRunPlatformDigestNow = async () => {
    setBusyId('platform_run_now');
    try {
      await api.post('/admin/compliance-digest/run-now');
      await fetchPlatformDigest();
      await fetchFeed();
      await fetchKinds();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || tx('admin.complianceDigestHub.errors.platformRunNowFailed', 'Platform digest run-now failed'));
    } finally {
      setBusyId('');
    }
  };

  const pillColor = (k: string): string => {
    if (k.startsWith('careers_gdpr_purge')) return C.primary;
    if (k.startsWith('gdpr_')) return C.cyan;
    if (k.startsWith('platform_quality')) return C.purple;
    if (k.startsWith('webhook_')) return C.warning;
    if (k.startsWith('llm_')) return C.success;
    if (k.startsWith('gtec_c5')) return C.error;
    return C.textSec;
  };

  const visible = useMemo(() => items, [items]);

  return (
    <View style={{ padding: 16, backgroundColor: C.bg, minHeight: '100%' }} data-testid="compliance-digest-hub-panel" testID="compliance-digest-hub-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View>
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }}>{tx('admin.complianceDigestHub.header.title', 'Compliance Digest Hub')}</Text>
          <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }}>
            {tx('admin.complianceDigestHub.header.subtitleWithCounts', 'Aggregated inbox for every governance digest · {total} total · {unreviewed} unreviewed')
              .replace('{total}', String(total))
              .replace('{unreviewed}', String(unreviewedTotal))}
          </Text>
        </View>
        <TouchableOpacity
          onPress={() => { fetchFeed(); fetchKinds(); fetchRecipients(); fetchPlatformDigest(); }}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.primarySoft, borderColor: C.primary, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 }}
          data-testid="compliance-digest-refresh" testID="compliance-digest-refresh"
        >
          <Ionicons name="refresh" size={13} color={C.primary} />
          <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700' }}>{tx('admin.complianceDigestHub.actions.refresh', 'Refresh')}</Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityLabel="Compliance digest export csv button"
          onPress={() => {
            // Stream the CSV directly from the browser — filters mirror
            // what's currently visible in the feed so the export lines
            // up with the admin's on-screen review state.
            const base = (process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
            const qs = new URLSearchParams();
            if (filterKind) qs.set('kind', filterKind);
            if (filterReviewed !== 'all') qs.set('reviewed', filterReviewed);
            const url = `${base}/api/compliance-digests/export.csv${qs.toString() ? '?' + qs.toString() : ''}`;
            if (typeof window !== 'undefined') window.open(url, '_blank');
          }}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.bgSoft, borderColor: C.border, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, marginLeft: 6 }}
          data-testid="compliance-digest-export-csv" testID="compliance-digest-export-csv"
        >
          <Ionicons name="download" size={13} color={C.cyan} />
          <Text style={{ color: C.cyan, fontSize: 11, fontWeight: '700' }}>{tx('admin.complianceDigestHub.actions.exportCsv', 'Export CSV')}</Text>
        </TouchableOpacity>
      </View>

      {/* Platform compliance digest snapshot */}
      <View
        style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12, padding: 14, marginBottom: 12 }}
        data-testid="platform-compliance-digest-card"
        testID="platform-compliance-digest-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <View>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.complianceDigestHub.platformCard.title', 'Platform compliance digest')}</Text>
            <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }} data-testid="platform-compliance-digest-updated" testID="platform-compliance-digest-updated">
              {tx('admin.complianceDigestHub.platformCard.lastRun', 'Last run')}: {platformDigest?.created_at ? formatAgo(platformDigest.created_at, tx) : tx('admin.complianceDigestHub.platformCard.notGeneratedYet', 'not generated yet')}
            </Text>
          </View>
          <TouchableOpacity accessibilityLabel="Platform compliance digest run now button"
            onPress={handleRunPlatformDigestNow}
            disabled={busyId === 'platform_run_now'}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 5,
              paddingHorizontal: 10,
              paddingVertical: 6,
              borderRadius: 8,
              backgroundColor: C.successSoft,
              borderWidth: 1,
              borderColor: C.success,
              opacity: busyId === 'platform_run_now' ? 0.6 : 1,
            }}
            data-testid="platform-compliance-digest-run-now"
            testID="platform-compliance-digest-run-now"
          >
            <Ionicons name="play" size={11} color={C.success} />
            <Text style={{ color: C.success, fontSize: 10, fontWeight: '700' }}>{busyId === 'platform_run_now' ? tx('admin.complianceDigestHub.common.running', 'Running…') : tx('admin.complianceDigestHub.actions.runNow', 'Run now')}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
          {[
            { label: tx('admin.complianceDigestHub.platformCard.metrics.severity', 'Severity'), value: String(platformDigest?.digest?.severity || tx('admin.complianceDigestHub.common.dash', '—')).toUpperCase() },
            { label: tx('admin.complianceDigestHub.platformCard.metrics.openNudges', 'Open nudges'), value: platformDigest?.digest?.metrics?.support_open_nudges ?? tx('admin.complianceDigestHub.common.dash', '—') },
            { label: tx('admin.complianceDigestHub.platformCard.metrics.escalatedOpen', 'Escalated open'), value: platformDigest?.digest?.metrics?.support_escalated_open ?? tx('admin.complianceDigestHub.common.dash', '—') },
            { label: tx('admin.complianceDigestHub.platformCard.metrics.securityHighCritical24h', 'Security H/C 24h'), value: platformDigest?.digest?.metrics?.security_high_critical_24h ?? tx('admin.complianceDigestHub.common.dash', '—') },
            { label: tx('admin.complianceDigestHub.platformCard.metrics.faqMissingLangs', 'FAQ missing langs'), value: (platformDigest?.digest?.metrics?.faq_languages_missing || []).length },
          ].map((m) => (
            <View
              key={m.label}
              style={{ backgroundColor: C.bgSoft, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6 }}
              data-testid={`platform-compliance-digest-metric-${m.label.toLowerCase().replace(/\s+/g, '-')}`}
              testID={`platform-compliance-digest-metric-${m.label.toLowerCase().replace(/\s+/g, '-')}`}
            >
              <Text style={{ color: C.textMuted, fontSize: 9, marginBottom: 2 }}>{m.label}</Text>
              <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{String(m.value)}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Recipient config card */}
      <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12, padding: 14, marginBottom: 12 }}
        data-testid="compliance-digest-recipients-card" testID="compliance-digest-recipients-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{tx('admin.complianceDigestHub.recipients.title', 'Digest recipients')}</Text>
          <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 999, backgroundColor: C.primarySoft }}>
            <Text style={{ color: C.primary, fontSize: 9, fontWeight: '700' }}>{tx('admin.complianceDigestHub.recipients.sourceWithValue', 'source: {value}').replace('{value}', recipientsSource || tx('admin.complianceDigestHub.common.dash', '—'))}</Text>
          </View>
        </View>
        <Text style={{ color: C.textMuted, fontSize: 10, marginBottom: 8 }}>
          {tx('admin.complianceDigestHub.recipients.activeWithValues', 'Active ({count}): {emails}')
            .replace('{count}', String(recipientsActive.length))
            .replace('{emails}', recipientsActive.join(', ') || tx('admin.complianceDigestHub.common.dash', '—'))}
        </Text>
        <TextInput
          value={recipientsInput}
          onChangeText={setRecipientsInput}
          placeholder={tx('admin.complianceDigestHub.recipients.placeholder', 'alice@company.com, bob@company.com')}
          placeholderTextColor={C.textMuted}
          multiline
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, minHeight: 48, fontSize: 11 }}
          data-testid="compliance-digest-recipients-input" testID="compliance-digest-recipients-input"
        />
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 }}>
          <Text style={{ color: C.textMuted, fontSize: 9 }}>{recipientsMsg}</Text>
          <TouchableOpacity
            disabled={recipientsSaving}
            onPress={handleSaveRecipients}
            style={{ backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, opacity: recipientsSaving ? 0.6 : 1 }}
            data-testid="compliance-digest-recipients-save" testID="compliance-digest-recipients-save"
          >
          <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '700' }}>{recipientsSaving ? tx('admin.complianceDigestHub.common.saving', 'Saving…') : tx('admin.complianceDigestHub.recipients.save', 'Save recipients')}</Text>{/* @theme-ok */}
          </TouchableOpacity>
        </View>
      </View>

      {/* Kind filter pills */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <TouchableOpacity
            onPress={() => setFilterKind('')}
            style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: !filterKind ? C.primary : C.bgSoft, borderColor: !filterKind ? C.primary : C.border, borderWidth: 1 }}
            data-testid="compliance-digest-filter-kind-all" testID="compliance-digest-filter-kind-all"
          >
          <Text style={{ color: !filterKind ? C.primaryText : C.textSec, fontSize: 10, fontWeight: '700' }}>{tx('admin.complianceDigestHub.filters.allKinds', 'All kinds')}</Text>
          </TouchableOpacity>
          {kinds.map((k) => (
            <TouchableOpacity
              key={k.kind}
              onPress={() => setFilterKind(k.kind)}
              style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: filterKind === k.kind ? pillColor(k.kind) : C.bgSoft, borderColor: filterKind === k.kind ? pillColor(k.kind) : C.border, borderWidth: 1 }}
              data-testid={`compliance-digest-filter-kind-${k.kind}`} testID={`compliance-digest-filter-kind-${k.kind}`}
            >
                <Text style={{ color: filterKind === k.kind ? C.primaryText : C.textSec, fontSize: 10, fontWeight: '700' }}>
                {k.label} {k.unreviewed > 0 ? `· ${k.unreviewed}` : ''}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* Reviewed-state filter */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 10, alignItems: 'center' }}>
        {(['unreviewed', 'reviewed', 'all'] as const).map((r) => (
          <TouchableOpacity
            key={r}
            onPress={() => setFilterReviewed(r)}
            style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: filterReviewed === r ? C.cyan : C.bgSoft, borderColor: filterReviewed === r ? C.cyan : C.border, borderWidth: 1 }}
            data-testid={`compliance-digest-filter-${r}`} testID={`compliance-digest-filter-${r}`}
          >
                <Text style={{ color: filterReviewed === r ? C.primaryText : C.textSec, fontSize: 10, fontWeight: '700' }}>{tx(`admin.complianceDigestHub.filters.reviewState.${r}`, r.toUpperCase())}</Text>
          </TouchableOpacity>
        ))}
        <View style={{ flex: 1 }} />
        <TouchableOpacity
          onPress={handleRunGdprDigestNow}
          disabled={busyId === 'gdpr_run_now'}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: C.warningSoft, borderColor: C.warning, borderWidth: 1, opacity: busyId === 'gdpr_run_now' ? 0.5 : 1 }}
          data-testid="compliance-digest-run-gdpr-now" testID="compliance-digest-run-gdpr-now"
        >
          <Ionicons name="play" size={11} color={C.warning} />
          <Text style={{ color: C.warning, fontSize: 10, fontWeight: '700' }}>{tx('admin.complianceDigestHub.actions.runGdprDigestNow', 'Run GDPR digest now')}</Text>
        </TouchableOpacity>
      </View>

      {err ? (
        <View style={{ backgroundColor: C.errorSoft, borderColor: C.error, borderWidth: 1, borderRadius: 8, padding: 8, marginBottom: 10 }}>
          <Text style={{ color: C.error, fontSize: 11 }}>{err}</Text>
        </View>
      ) : null}

      {/* Feed */}
      {loading ? (
        <ActivityIndicator color={C.primary} />
      ) : visible.length === 0 ? (
        <View style={{ padding: 24, alignItems: 'center', backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12 }}
          data-testid="compliance-digest-empty" testID="compliance-digest-empty"
        >
          <Ionicons name="mail-open-outline" size={28} color={C.textMuted} />
          <Text style={{ color: C.textSec, fontSize: 12, marginTop: 6 }}>
            {tx('admin.complianceDigestHub.states.noDigestsMatchFilter', 'No digests match this filter.')}
          </Text>
        </View>
      ) : (
        visible.map((e) => {
          const col = pillColor(e.kind);
          const isExpanded = expanded === e.entry_id;
          const isReviewed = !!e.reviewed_at;
          const isGtecReceipt = e.kind === 'gtec_c5_run_receipt';
          const receipt = isGtecReceipt ? (e.payload || {}) : null;
          const receiptDelivery = receipt?.delivery || {};
          const receiptPdf = receipt?.pdf_attachment || {};
          return (
            <View
              key={e.entry_id}
              style={{ backgroundColor: C.card, borderColor: isReviewed ? C.border : col, borderWidth: 1, borderRadius: 12, padding: 12, marginBottom: 8, opacity: isReviewed ? 0.75 : 1 }}
              data-testid={`compliance-digest-entry-${e.entry_id}`} testID={`compliance-digest-entry-${e.entry_id}`}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(col, '22') }}>
                  <Text style={{ color: col, fontSize: 9, fontWeight: '800' }}>{e.kind_label}</Text>
                </View>
                {isReviewed ? (
                  <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 999, backgroundColor: C.successSoft }}>
                    <Text style={{ color: C.success, fontSize: 9, fontWeight: '700' }}>{tx('admin.complianceDigestHub.feed.reviewedBadge', 'REVIEWED')}</Text>
                  </View>
                ) : null}
                <View style={{ flex: 1 }} />
                <Text style={{ color: C.textMuted, fontSize: 10 }}>{formatAgo(e.created_at, tx)}</Text>
              </View>
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', marginTop: 6 }} numberOfLines={2}>{e.subject}</Text>
              <Text style={{ color: C.textSec, fontSize: 10, marginTop: 4 }}>{e.summary}</Text>

              {isGtecReceipt ? (
                <View
                  style={{ marginTop: 8, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 8 }}
                  data-testid={`gtec-c5-receipt-card-${e.entry_id}`}
                  testID={`gtec-c5-receipt-card-${e.entry_id}`}
                >
                  <Text
                    style={{ color: C.text, fontSize: 10, fontWeight: '800', marginBottom: 6 }}
                    data-testid={`gtec-c5-receipt-title-${e.entry_id}`}
                    testID={`gtec-c5-receipt-title-${e.entry_id}`}
                  >
                    GTEC C5 Run Receipt
                  </Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                    <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6 }} data-testid={`gtec-c5-receipt-task-${e.entry_id}`} testID={`gtec-c5-receipt-task-${e.entry_id}`}>
                      <Text style={{ color: C.textMuted, fontSize: 9 }}>Task</Text>
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>{String(receipt?.task_id || '—')}</Text>
                    </View>
                    <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6 }} data-testid={`gtec-c5-receipt-status-${e.entry_id}`} testID={`gtec-c5-receipt-status-${e.entry_id}`}>
                      <Text style={{ color: C.textMuted, fontSize: 9 }}>Status</Text>
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>{String(receipt?.status || '—')}</Text>
                    </View>
                    <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6 }} data-testid={`gtec-c5-receipt-trigger-${e.entry_id}`} testID={`gtec-c5-receipt-trigger-${e.entry_id}`}>
                      <Text style={{ color: C.textMuted, fontSize: 9 }}>Trigger</Text>
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>{String(receipt?.triggered_by || e.trigger || '—')}</Text>
                    </View>
                    <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6 }} data-testid={`gtec-c5-receipt-actor-${e.entry_id}`} testID={`gtec-c5-receipt-actor-${e.entry_id}`}>
                      <Text style={{ color: C.textMuted, fontSize: 9 }}>Actor</Text>
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>{String(receipt?.actor || '—')}</Text>
                    </View>
                    <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6 }} data-testid={`gtec-c5-receipt-delivery-${e.entry_id}`} testID={`gtec-c5-receipt-delivery-${e.entry_id}`}>
                      <Text style={{ color: C.textMuted, fontSize: 9 }}>Delivery</Text>
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }}>
                        {String(receiptDelivery?.sent_ok ?? e.sent_ok)}/{String(receiptDelivery?.total ?? e.recipient_count)}
                        {Number(receiptDelivery?.sent_failed ?? e.sent_failed) > 0 ? ` · fail ${String(receiptDelivery?.sent_failed ?? e.sent_failed)}` : ''}
                      </Text>
                    </View>
                    <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, minWidth: 240 }} data-testid={`gtec-c5-receipt-pdf-${e.entry_id}`} testID={`gtec-c5-receipt-pdf-${e.entry_id}`}>
                      <Text style={{ color: C.textMuted, fontSize: 9 }}>PDF</Text>
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '700' }} numberOfLines={1}>{String(receiptPdf?.filename || '—')}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 9 }} numberOfLines={1}>SHA256 {String(receiptPdf?.sha256 || '—')}</Text>
                    </View>
                  </View>
                </View>
              ) : null}

              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 6 }}>
                <Text style={{ color: C.textMuted, fontSize: 9 }}>
                  {tx('admin.complianceDigestHub.feed.sentWithCounts', 'sent {ok}/{total}{failedPart}')
                    .replace('{ok}', String(e.sent_ok))
                    .replace('{total}', String(e.recipient_count))
                    .replace('{failedPart}', e.sent_failed ? tx('admin.complianceDigestHub.feed.failedWithCount', ' · failed {count}').replace('{count}', String(e.sent_failed)) : '')}
                </Text>
                <Text style={{ color: C.textMuted, fontSize: 9 }}>{tx('admin.complianceDigestHub.feed.triggerWithValue', 'trigger: {value}').replace('{value}', String(e.trigger || ''))}</Text>
                {isReviewed ? (
                  <Text style={{ color: C.textMuted, fontSize: 9 }}>{tx('admin.complianceDigestHub.feed.reviewedByWithValue', 'by {value}').replace('{value}', e.reviewed_by || tx('admin.complianceDigestHub.common.dash', '—'))}</Text>
                ) : null}
              </View>

              {isExpanded ? (
                <View style={{ marginTop: 8, padding: 8, backgroundColor: C.bgSoft, borderRadius: 8, borderColor: C.border, borderWidth: 1 }}>
                  <Text style={{ color: C.textMuted, fontSize: 9, marginBottom: 4 }}>{tx('admin.complianceDigestHub.feed.recipientsWithValue', 'Recipients: {value}').replace('{value}', e.recipients.join(', ') || tx('admin.complianceDigestHub.common.dash', '—'))}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 9, marginBottom: 4 }}>{tx('admin.complianceDigestHub.feed.payload', 'Payload')}:</Text>
                  <Text style={{ color: C.textSec, fontSize: 9, fontFamily: 'monospace' as any }} numberOfLines={12}>
                    {JSON.stringify(e.payload || {}, null, 2)}
                  </Text>
                  {e.review_notes ? (
                    <Text style={{ color: C.textMuted, fontSize: 9, marginTop: 6 }}>{tx('admin.complianceDigestHub.feed.notesWithValue', 'Notes: {value}').replace('{value}', e.review_notes)}</Text>
                  ) : null}
                </View>
              ) : null}

              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 }}>
                <TouchableOpacity
                  onPress={() => setExpanded(isExpanded ? '' : e.entry_id)}
                  style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: C.bgSoft, borderColor: C.border, borderWidth: 1 }}
                  data-testid={`compliance-digest-expand-${e.entry_id}`} testID={`compliance-digest-expand-${e.entry_id}`}
                >
                  <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{isExpanded ? tx('admin.complianceDigestHub.actions.collapse', 'Collapse') : tx('admin.complianceDigestHub.actions.expand', 'Expand')}</Text>
                </TouchableOpacity>
                {!isReviewed ? (
                  <>
                    <TextInput
                      value={reviewNotes[e.entry_id] || ''}
                      onChangeText={(v) => setReviewNotes((s) => ({ ...s, [e.entry_id]: v }))}
                      placeholder={tx('admin.complianceDigestHub.feed.reviewNotePlaceholder', 'Review note (optional)')}
                      placeholderTextColor={C.textMuted}
                      style={{ flex: 1, backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5, fontSize: 10 }}
                      data-testid={`compliance-digest-note-${e.entry_id}`} testID={`compliance-digest-note-${e.entry_id}`}
                    />
                    <TouchableOpacity
                      disabled={busyId === e.entry_id}
                      onPress={() => handleMarkReviewed(e.entry_id)}
                      style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: C.success, opacity: busyId === e.entry_id ? 0.5 : 1 }}
                      data-testid={`compliance-digest-review-${e.entry_id}`} testID={`compliance-digest-review-${e.entry_id}`}
                    >
                  <Text style={{ color: C.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.complianceDigestHub.actions.markReviewed', 'Mark reviewed')}</Text>{/* @theme-ok: white on success-tinted button — correct contrast */}
                    </TouchableOpacity>
                  </>
                ) : (
                  <TouchableOpacity
                    disabled={busyId === e.entry_id}
                    onPress={() => handleUnreview(e.entry_id)}
                    style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: C.warningSoft, borderColor: C.warning, borderWidth: 1, opacity: busyId === e.entry_id ? 0.5 : 1 }}
                    data-testid={`compliance-digest-unreview-${e.entry_id}`} testID={`compliance-digest-unreview-${e.entry_id}`}
                  >
                    <Text style={{ color: C.warning, fontSize: 10, fontWeight: '700' }}>{tx('admin.complianceDigestHub.actions.undoReview', 'Undo review')}</Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          );
        })
      )}
    </View>
  );
}
