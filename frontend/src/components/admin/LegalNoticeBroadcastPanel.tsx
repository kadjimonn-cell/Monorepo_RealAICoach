// Legal Notice Broadcast — ToS / Privacy Policy updates.
// Safety rail flow: compose → DRY RUN (returns recipient count) → type
// "SEND" to unlock confirm → final send → audit log entry.
import { useTranslation } from '../../hooks/useTranslation';
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

const tx = (_key: string, fallback: string) => fallback;

const C = {
  bg: 'var(--app-bg)' as any,
  bgSoft: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any, primarySoft: 'var(--app-primary-soft)',
  success: 'var(--app-success)', successSoft: 'var(--app-success-soft)',
  warning: 'var(--app-warning)', warningSoft: 'var(--app-warning-soft)',
  error: 'var(--app-error)', errorSoft: 'var(--app-error-soft)',
  cyan: 'var(--app-primary)' as any,
};

type Broadcast = {
  broadcast_id: string;
  policy_type: string;
  effective_date: string;
  summary_of_changes: string;
  recipient_count: number;
  sent_ok: number;
  sent_failed: number;
  broadcast_by: string;
  sent_at: string;
};

type DryRunResp = {
  dry_run: true;
  recipient_count: number;
  audience: string;
  preview_subject: string;
  rate_limit_seconds: number;
};

type LockablePolicyType = 'Terms of Service' | 'Privacy Policy' | 'Cookie Policy';

interface Props {
  // When set, the policy-type pill picker is hidden and the value is
  // locked. Used by CookiePolicyBroadcastPanel / PrivacyPolicyBroadcastPanel
  // so dedicated Operations tabs can't accidentally send the wrong variant.
  lockedPolicyType?: LockablePolicyType;
  // Optional header override so a locked-variant panel reads naturally
  // (e.g. "Cookie Policy Broadcast" instead of the generic "Legal Notice").
  headingLabel?: string;
  headingSubtitle?: string;
}

export default function LegalNoticeBroadcastPanel({ lockedPolicyType, headingLabel, headingSubtitle }: Props = {}) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [policyType, setPolicyType] = useState<LockablePolicyType>(lockedPolicyType ?? 'Terms of Service');
  const [effectiveDate, setEffectiveDate] = useState('');
  const [summary, setSummary] = useState('');
  const [reviewUrl, setReviewUrl] = useState('');
  const [audience] = useState<'all_users'>('all_users');

  const [preview, setPreview] = useState<DryRunResp | null>(null);
  const [confirmPhrase, setConfirmPhrase] = useState('');
  const [busy, setBusy] = useState<'idle' | 'dryrun' | 'sending'>('idle');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [history, setHistory] = useState<Broadcast[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const { data } = await api.get('/admin/legal-notice/broadcasts');
      setHistory(data?.items || []);
    } catch { /* silent */ }
    setHistoryLoading(false);
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  const canDryRun = policyType && effectiveDate.length >= 2 && summary.length >= 10;

  const handleDryRun = async () => {
    if (!canDryRun) { setErr('Fill policy_type, effective_date, and a summary (≥10 chars) first.'); return; }
    setErr(''); setMsg(''); setBusy('dryrun'); setConfirmPhrase('');
    try {
      const { data } = await api.post('/admin/legal-notice/broadcast', {
        policy_type: policyType,
        effective_date: effectiveDate,
        summary_of_changes: summary,
        review_url: reviewUrl,
        audience,
        dry_run: true,
      });
      setPreview(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Dry-run failed.');
    } finally { setBusy('idle'); }
  };

  const handleSend = async () => {
    if (!preview) return;
    if (confirmPhrase.trim() !== 'SEND') { setErr('Type "SEND" exactly to confirm.'); return; }
    if (typeof window !== 'undefined' && !window.confirm?.(`Send the legal notice to ${preview.recipient_count} users? This cannot be undone.`)) return;
    setErr(''); setMsg(''); setBusy('sending');
    try {
      const { data } = await api.post('/admin/legal-notice/broadcast', {
        policy_type: policyType,
        effective_date: effectiveDate,
        summary_of_changes: summary,
        review_url: reviewUrl,
        audience,
        dry_run: false,
        confirm_phrase: 'SEND',
      });
      setMsg(`Broadcast sent. Delivered ${data?.sent_ok ?? 0} / failed ${data?.sent_failed ?? 0}.`);
      setPreview(null); setConfirmPhrase('');
      setPolicyType('Terms of Service'); setEffectiveDate(''); setSummary(''); setReviewUrl('');
      loadHistory();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Send failed.');
    } finally { setBusy('idle'); }
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ padding: 16 }}
      data-testid="legal-notice-broadcast-panel" testID="legal-notice-broadcast-panel">

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <Ionicons name={lockedPolicyType === 'Cookie Policy' ? 'nutrition' : 'document-text'} size={20} color={C.primary} />
        <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }}>{headingLabel ?? 'Legal Notice Broadcast'}</Text>
      </View>
      <Text style={{ color: C.textMuted, fontSize: 11, marginBottom: 16 }}>
        {headingSubtitle ?? `Send a ${lockedPolicyType ?? 'Terms of Service / Privacy Policy'} update email to every user. Dry-run first → type "SEND" to confirm → audited in the Compliance Digest Hub.`}
      </Text>

      {/* Composer card */}
      <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12, padding: 14, marginBottom: 12 }}
        data-testid="legal-notice-composer" testID="legal-notice-composer">
        {/* Policy-type pill selector is hidden when the panel is locked
            to a single variant (e.g. the dedicated Cookie Policy tab). */}
        {!lockedPolicyType && (
          <>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 6 }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.001', 'POLICY TYPE')}</Text>
            <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
              {(['Terms of Service', 'Privacy Policy', 'Cookie Policy'] as const).map((p) => (
                <TouchableOpacity key={p} onPress={() => setPolicyType(p)}
                  style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: policyType === p ? C.primary : C.bgSoft, borderColor: policyType === p ? C.primary : C.border, borderWidth: 1 }}
                  data-testid={`legal-notice-policy-${p.replace(/\s+/g, '-').toLowerCase()}`}>
                  <Text style={{ color: policyType === p ? 'var(--app-primary-text)' : C.textSec, fontSize: 10, fontWeight: '800' }}>{p}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}
        {lockedPolicyType && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 12, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.primarySoft, borderColor: C.primary, borderWidth: 1, alignSelf: 'flex-start' }}
            data-testid={`legal-notice-locked-${lockedPolicyType.replace(/\s+/g, '-').toLowerCase()}`}>
            <Ionicons name="lock-closed" size={11} color={C.primary} />
            <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>{lockedPolicyType}</Text>
          </View>
        )}

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.002', 'EFFECTIVE DATE')}</Text>
        <TextInput value={effectiveDate} onChangeText={setEffectiveDate} placeholder={tx('admin.legalNoticeBroadcastPanel.auto.placeholder.001', 'e.g. May 1, 2026')} placeholderTextColor={C.textMuted}
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, marginBottom: 10 }}
          data-testid="legal-notice-effective-date" />

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.003', 'SUMMARY OF CHANGES')}</Text>
        <TextInput value={summary} onChangeText={setSummary} placeholder={tx('admin.legalNoticeBroadcastPanel.auto.placeholder.002', 'Plain-language bullet summary (≥10 chars, ≤2000). Users will see this verbatim.')} placeholderTextColor={C.textMuted}
          multiline
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, minHeight: 80, marginBottom: 10 }}
          maxLength={2000}
          data-testid="legal-notice-summary" />

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.004', 'REVIEW URL (OPTIONAL)')}</Text>
        <TextInput value={reviewUrl} onChangeText={setReviewUrl} placeholder={tx('admin.legalNoticeBroadcastPanel.auto.placeholder.003', 'https://realaicoach.app/legal')} placeholderTextColor={C.textMuted}
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, marginBottom: 10 }}
          data-testid="legal-notice-review-url" />

        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={handleDryRun} disabled={!canDryRun || busy !== 'idle'}
            style={{ flex: 1, backgroundColor: C.primarySoft, borderColor: C.primary, borderWidth: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center', opacity: !canDryRun || busy !== 'idle' ? 0.5 : 1 }}
            data-testid="legal-notice-dryrun-btn">
            <Text style={{ color: C.primary, fontSize: 12, fontWeight: '800' }}>{busy === 'dryrun' ? 'Previewing…' : '1. Dry-run · Preview recipients'}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Dry-run preview + confirm */}
      {preview && (
        <View style={{ backgroundColor: C.warningSoft, borderColor: C.warning, borderWidth: 1, borderRadius: 12, padding: 14, marginBottom: 12 }}
          data-testid="legal-notice-preview-card">
          <Text style={{ color: C.warning, fontSize: 11, fontWeight: '800', marginBottom: 4 }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.005', 'DRY-RUN PREVIEW · NOT YET SENT')}</Text>
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 6 }}>
            Will email <Text style={{ color: C.warning }}>{Number(preview.recipient_count || 0).toLocaleString()}</Text> users
          </Text>
          <Text style={{ color: C.textSec, fontSize: 11, marginBottom: 10 }}>Subject line: "{preview.preview_subject}"</Text>

          <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>
            TYPE <Text style={{ color: C.warning }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.006', 'SEND')}</Text> TO CONFIRM
          </Text>
          <TextInput value={confirmPhrase} onChangeText={setConfirmPhrase} placeholder={tx('admin.legalNoticeBroadcastPanel.auto.placeholder.004', 'SEND')} placeholderTextColor={C.textMuted}
            style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 13, marginBottom: 10, letterSpacing: 1 }}
            autoCapitalize="characters"
            data-testid="legal-notice-confirm-phrase" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={() => { setPreview(null); setConfirmPhrase(''); }}
              style={{ flex: 1, backgroundColor: C.bgSoft, borderColor: C.border, borderWidth: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' }}
              data-testid="legal-notice-cancel">
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.007', 'Cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleSend} disabled={confirmPhrase.trim() !== 'SEND' || busy === 'sending'}
              style={{ flex: 2, backgroundColor: confirmPhrase.trim() === 'SEND' ? C.primary : C.bgSoft, borderColor: C.primary, borderWidth: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center', opacity: busy === 'sending' ? 0.6 : 1 }}
              data-testid="legal-notice-send-btn">
              <Text style={{ color: confirmPhrase.trim() === 'SEND' ? 'var(--app-primary-text)' : C.textMuted, fontSize: 12, fontWeight: '800' }}>
                {busy === 'sending' ? 'Sending…' : `2. Send to ${Number(preview.recipient_count || 0).toLocaleString()} users`}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {err ? <Text style={{ color: C.error, fontSize: 11, marginBottom: 10 }} data-testid="legal-notice-error">{err}</Text> : null}
      {msg ? <Text style={{ color: C.success, fontSize: 11, marginBottom: 10 }} data-testid="legal-notice-success">{msg}</Text> : null}

      {/* History / audit trail */}
      <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12, padding: 12 }}
        data-testid="legal-notice-history">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.008', 'Recent broadcasts')}</Text>
          <TouchableOpacity onPress={loadHistory} data-testid="legal-notice-history-refresh">
            <Ionicons name="refresh" size={14} color={C.textSec} />
          </TouchableOpacity>
        </View>
        {historyLoading ? <ActivityIndicator color={C.primary} /> : history.length === 0 ? (
          <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('admin.legalNoticeBroadcastPanel.auto.text.009', 'No broadcasts sent yet.')}</Text>
        ) : history.map((b) => (
          <View key={b.broadcast_id} style={{ borderTopColor: C.border, borderTopWidth: 1, paddingVertical: 8 }}
            data-testid={`legal-notice-history-row-${b.broadcast_id}`}>
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{b.policy_type} · {b.effective_date}</Text>
            <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }}>
              by {b.broadcast_by || '—'} · {b.sent_at ? new Date(b.sent_at).toLocaleString() : '—'} · {Number(b.recipient_count || 0).toLocaleString()} users · ✓{b.sent_ok ?? 0} ✗{b.sent_failed ?? 0}
            </Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}
