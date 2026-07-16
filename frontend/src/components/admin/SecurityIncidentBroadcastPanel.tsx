// Security Incident Broadcast — breach / cyberattack alerts.
// Dual-channel (email + push for critical/high severity). Same safety
// architecture as the legal-notice panel (dry-run → type-SEND gate → rate
// limit → audit log + compliance digest entry).
import { useTranslation } from '../../hooks/useTranslation';
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView } from 'react-native';
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
  critical: 'var(--app-error)', criticalSoft: 'var(--app-error-soft)',
  info: 'var(--app-primary)' as any, infoSoft: 'var(--app-primary-soft)',
};

type Severity = 'critical' | 'high' | 'medium' | 'informational';
type IncidentType =
  | 'data_breach' | 'unauthorized_access' | 'cyberattack'
  | 'credential_leak' | 'third_party_vendor_incident'
  | 'phishing_campaign' | 'other';

const INCIDENT_TYPES: { value: IncidentType; label: string }[] = [
  { value: 'data_breach', label: 'Data Breach' },
  { value: 'unauthorized_access', label: 'Unauthorized Access' },
  { value: 'cyberattack', label: 'Cyberattack' },
  { value: 'credential_leak', label: 'Credential Leak' },
  { value: 'third_party_vendor_incident', label: 'Third-Party Incident' },
  { value: 'phishing_campaign', label: 'Phishing Campaign' },
  { value: 'other', label: 'Other' },
];
const SEVERITIES: { value: Severity; label: string; color: string }[] = [
  { value: 'critical', label: 'Critical', color: C.critical },
  { value: 'high', label: 'High', color: C.primary },
  { value: 'medium', label: 'Medium', color: C.warning },
  { value: 'informational', label: 'Informational', color: C.info },
];

type Broadcast = {
  broadcast_id: string;
  incident_type: string;
  severity: string;
  recipient_count: number;
  sent_email: number;
  failed_email: number;
  sent_push: number;
  failed_push: number;
  push_enabled: boolean;
  push_mode: string;
  broadcast_by: string;
  sent_at: string;
};

type DryRunResp = {
  dry_run: true;
  recipient_count: number;
  audience: string;
  severity: string;
  incident_type: string;
  push_enabled: boolean;
  push_mode: string;
  preview_subject: string;
  rate_limit_seconds: number;
};

export default function SecurityIncidentBroadcastPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [incidentType, setIncidentType] = useState<IncidentType>('data_breach');
  const [severity, setSeverity] = useState<Severity>('high');
  const [incidentDate, setIncidentDate] = useState('');
  const [discoveredDate, setDiscoveredDate] = useState('');
  const [whatHappened, setWhatHappened] = useState('');
  const [dataAffected, setDataAffected] = useState('');
  const [actionRequired, setActionRequired] = useState('');
  const [remediation, setRemediation] = useState('');
  const [contactEmail, setContactEmail] = useState('security@realaicoach.app');
  const [actionUrl, setActionUrl] = useState('');
  const [audience, setAudience] = useState<'all_users' | 'affected_only'>('affected_only');
  const [userIdsRaw, setUserIdsRaw] = useState('');

  const [pushEnabled, setPushEnabled] = useState(true);
  const [pushMode, setPushMode] = useState<'full_detail' | 'minimal_deeplink'>('minimal_deeplink');

  const [preview, setPreview] = useState<DryRunResp | null>(null);
  const [confirmPhrase, setConfirmPhrase] = useState('');
  const [busy, setBusy] = useState<'idle' | 'dryrun' | 'sending'>('idle');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [history, setHistory] = useState<Broadcast[]>([]);

  // Re-default push-enabled whenever severity changes so the admin's intent
  // matches the policy (critical/high default ON, medium/informational OFF).
  useEffect(() => {
    setPushEnabled(severity === 'critical' || severity === 'high');
  }, [severity]);

  const loadHistory = useCallback(async () => {
    try {
      const { data } = await api.get('/admin/security-incident/broadcasts');
      setHistory(data?.items || []);
    } catch { /* silent */ }
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const buildBody = (dry: boolean) => {
    const userIds = audience === 'affected_only'
      ? userIdsRaw.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean)
      : undefined;
    return {
      incident_type: incidentType,
      severity,
      incident_date: incidentDate,
      discovered_date: discoveredDate,
      what_happened: whatHappened,
      data_affected: dataAffected,
      user_action_required: actionRequired,
      remediation_steps: remediation,
      contact_email: contactEmail,
      action_url: actionUrl,
      audience,
      user_ids: userIds,
      push_enabled: pushEnabled,
      push_mode: pushMode,
      dry_run: dry,
      ...(dry ? {} : { confirm_phrase: 'SEND' }),
    };
  };

  const canDryRun =
    incidentDate.length >= 2 && discoveredDate.length >= 2 &&
    whatHappened.length >= 10 && dataAffected.length >= 2 &&
    actionRequired.length >= 2 && remediation.length >= 2 &&
    contactEmail.includes('@') &&
    (audience === 'all_users' || userIdsRaw.trim().length > 0);

  const handleDryRun = async () => {
    if (!canDryRun) { setErr('Fill all required fields first (and at least one user_id for affected_only).'); return; }
    setErr(''); setMsg(''); setBusy('dryrun'); setConfirmPhrase('');
    try {
      const { data } = await api.post('/admin/security-incident/broadcast', buildBody(true));
      setPreview(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Dry-run failed.');
    } finally { setBusy('idle'); }
  };

  const handleSend = async () => {
    if (!preview) return;
    if (confirmPhrase.trim() !== 'SEND') { setErr('Type "SEND" exactly to confirm.'); return; }
    const ch = `email${preview.push_enabled ? ' + push' : ''}`;
    if (typeof window !== 'undefined' && !window.confirm?.(`Send ${preview.severity.toUpperCase()} security notice to ${preview.recipient_count} users via ${ch}? This cannot be undone.`)) return;
    setErr(''); setMsg(''); setBusy('sending');
    try {
      const { data } = await api.post('/admin/security-incident/broadcast', buildBody(false));
      setMsg(`Security notice sent. Email ✓${data?.sent_email ?? 0} ✗${data?.failed_email ?? 0} · Push ✓${data?.sent_push ?? 0} ✗${data?.failed_push ?? 0}.`);
      setPreview(null); setConfirmPhrase('');
      loadHistory();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Send failed.');
    } finally { setBusy('idle'); }
  };

  const sevColor = SEVERITIES.find((s) => s.value === severity)?.color || C.primary;

  return (
    <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ padding: 16 }}
      data-testid="security-incident-broadcast-panel" testID="security-incident-broadcast-panel">

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <Ionicons name="shield-checkmark" size={20} color={sevColor} />
        <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.001', 'Security Incident Broadcast')}</Text>
      </View>
      <Text style={{ color: C.textMuted, fontSize: 11, marginBottom: 16 }}>
        Notify affected users of a breach, cyberattack, or credential leak via email {'\u002B'} push. Dry-run → type "SEND" → audited. Critical/high defaults to push-on.
      </Text>

      <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12, padding: 14, marginBottom: 12 }}
        data-testid="security-incident-composer">

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 6 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.002', 'INCIDENT TYPE')}</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            {INCIDENT_TYPES.map((t) => (
              <TouchableOpacity key={t.value} onPress={() => setIncidentType(t.value)}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: incidentType === t.value ? C.primary : C.bgSoft, borderColor: incidentType === t.value ? C.primary : C.border, borderWidth: 1 }}
                data-testid={`security-incident-type-${t.value}`}>
                <Text style={{ color: incidentType === t.value ? 'var(--app-primary-text)' : C.textSec, fontSize: 10, fontWeight: '800' }}>{t.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 6 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.003', 'SEVERITY')}</Text>
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {SEVERITIES.map((s) => (
            <TouchableOpacity key={s.value} onPress={() => setSeverity(s.value)}
              style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: severity === s.value ? s.color : C.bgSoft, borderColor: severity === s.value ? s.color : C.border, borderWidth: 1 }}
              data-testid={`security-incident-severity-${s.value}`}>
              <Text style={{ color: severity === s.value ? 'var(--app-primary-text)' : C.textSec, fontSize: 10, fontWeight: '800' }}>{s.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.004', 'INCIDENT DATE')}</Text>
            <TextInput value={incidentDate} onChangeText={setIncidentDate} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.001', 'Apr 20, 2026')} placeholderTextColor={C.textMuted}
              style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12 }}
              data-testid="security-incident-date" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.005', 'DISCOVERED DATE')}</Text>
            <TextInput value={discoveredDate} onChangeText={setDiscoveredDate} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.002', 'Apr 21, 2026')} placeholderTextColor={C.textMuted}
              style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12 }}
              data-testid="security-incident-discovered-date" />
          </View>
        </View>

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.006', 'WHAT HAPPENED')}</Text>
        <TextInput value={whatHappened} onChangeText={setWhatHappened} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.003', 'Plain-language description of the incident.')} placeholderTextColor={C.textMuted}
          multiline
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, minHeight: 60, marginBottom: 10 }}
          maxLength={2000} data-testid="security-incident-what-happened" />

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.007', 'DATA POTENTIALLY AFFECTED')}</Text>
        <TextInput value={dataAffected} onChangeText={setDataAffected} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.004', 'e.g. email addresses and hashed passwords')} placeholderTextColor={C.textMuted}
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, marginBottom: 10 }}
          maxLength={500} data-testid="security-incident-data-affected" />

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.008', 'USER ACTION REQUIRED')}</Text>
        <TextInput value={actionRequired} onChangeText={setActionRequired} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.005', 'e.g. Reset your password and enable 2FA immediately.')} placeholderTextColor={C.textMuted}
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, marginBottom: 10 }}
          maxLength={500} data-testid="security-incident-action-required" />

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.009', 'REMEDIATION (WHAT YOU\'VE ALREADY DONE)')}</Text>
        <TextInput value={remediation} onChangeText={setRemediation} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.006', 'e.g. Rotated credentials, closed the access vector, engaged a security firm.')} placeholderTextColor={C.textMuted}
          multiline
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, minHeight: 50, marginBottom: 10 }}
          maxLength={1000} data-testid="security-incident-remediation" />

        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.010', 'CONTACT EMAIL')}</Text>
            <TextInput value={contactEmail} onChangeText={setContactEmail} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.007', 'security@realaicoach.app')} placeholderTextColor={C.textMuted}
              style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12 }}
              autoCapitalize="none" data-testid="security-incident-contact-email" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.011', 'ACTION URL (OPTIONAL)')}</Text>
            <TextInput value={actionUrl} onChangeText={setActionUrl} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.008', '/account/security')} placeholderTextColor={C.textMuted}
              style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12 }}
              autoCapitalize="none" data-testid="security-incident-action-url" />
          </View>
        </View>

        <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 6 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.012', 'AUDIENCE')}</Text>
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 10 }}>
          {(['affected_only', 'all_users'] as const).map((a) => (
            <TouchableOpacity key={a} onPress={() => setAudience(a)}
              style={{ flex: 1, paddingVertical: 8, borderRadius: 8, backgroundColor: audience === a ? C.primary : C.bgSoft, borderColor: audience === a ? C.primary : C.border, borderWidth: 1, alignItems: 'center' }}
              data-testid={`security-incident-audience-${a}`}>
              <Text style={{ color: audience === a ? 'var(--app-primary-text)' : C.textSec, fontSize: 10, fontWeight: '800' }}>
                {a === 'affected_only' ? 'Affected Only (recommended)' : 'All Users'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {audience === 'affected_only' && (
          <View style={{ marginBottom: 10 }}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.013', 'AFFECTED USER IDS (comma or newline separated)')}</Text>
            <TextInput value={userIdsRaw} onChangeText={setUserIdsRaw} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.009', 'user_abc123, user_def456')} placeholderTextColor={C.textMuted}
              multiline
              style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, minHeight: 50 }}
              data-testid="security-incident-user-ids" />
          </View>
        )}

        {/* Push channel controls */}
        <View style={{ backgroundColor: C.bgSoft, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 10, marginBottom: 10 }}
          data-testid="security-incident-push-controls">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.014', 'In-app / web push')}</Text>
            <TouchableOpacity onPress={() => setPushEnabled(!pushEnabled)}
              style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: pushEnabled ? C.successSoft : C.bgSoft, borderColor: pushEnabled ? C.success : C.border, borderWidth: 1 }}
              data-testid="security-incident-push-toggle">
              <Text style={{ color: pushEnabled ? C.success : C.textMuted, fontSize: 10, fontWeight: '800' }}>{pushEnabled ? 'ON' : 'OFF'}</Text>
            </TouchableOpacity>
          </View>
          {pushEnabled && (
            <>
              <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.015', 'PUSH COPY')}</Text>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                {([
                  { v: 'minimal_deeplink', label: 'Minimal + deeplink (recommended)' },
                  { v: 'full_detail', label: 'Full detail (direct instruction)' },
                ] as const).map((p) => (
                  <TouchableOpacity key={p.v} onPress={() => setPushMode(p.v)}
                    style={{ flex: 1, paddingVertical: 6, borderRadius: 6, backgroundColor: pushMode === p.v ? C.primarySoft : 'transparent', borderColor: pushMode === p.v ? C.primary : C.border, borderWidth: 1, alignItems: 'center' }}
                    data-testid={`security-incident-push-mode-${p.v}`}>
                    <Text style={{ color: pushMode === p.v ? C.primary : C.textSec, fontSize: 9, fontWeight: '700' }}>{p.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </>
          )}
        </View>

        <TouchableOpacity onPress={handleDryRun} disabled={!canDryRun || busy !== 'idle'}
          style={{ backgroundColor: (globalThis as any).__alphaColor(sevColor, '22'), borderColor: sevColor, borderWidth: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center', opacity: !canDryRun || busy !== 'idle' ? 0.5 : 1 }}
          data-testid="security-incident-dryrun-btn">
          <Text style={{ color: sevColor, fontSize: 12, fontWeight: '800' }}>{busy === 'dryrun' ? 'Previewing…' : '1. Dry-run · Preview recipients'}</Text>
        </TouchableOpacity>
      </View>

      {preview && (
        <View style={{ backgroundColor: C.criticalSoft, borderColor: C.critical, borderWidth: 1, borderRadius: 12, padding: 14, marginBottom: 12 }}
          data-testid="security-incident-preview-card">
          <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800', marginBottom: 4 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.016', 'DRY-RUN PREVIEW · NOT YET SENT')}</Text>
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '700', marginBottom: 6 }}>
            {(preview.severity || '').toUpperCase()} · {Number(preview.recipient_count || 0).toLocaleString()} users via email{preview.push_enabled ? ` + push (${(preview.push_mode || '').replace('_', ' ')})` : ''}
          </Text>
          <Text style={{ color: C.textSec, fontSize: 11, marginBottom: 10 }}>Subject: "{preview.preview_subject}"</Text>

          <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '800', marginBottom: 4 }}>
            TYPE <Text style={{ color: C.primary }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.017', 'SEND')}</Text> TO CONFIRM
          </Text>
          <TextInput value={confirmPhrase} onChangeText={setConfirmPhrase} placeholder={tx('admin.securityIncidentBroadcastPanel.auto.placeholder.010', 'SEND')} placeholderTextColor={C.textMuted}
            style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 13, marginBottom: 10, letterSpacing: 1 }}
            autoCapitalize="characters" data-testid="security-incident-confirm-phrase" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={() => { setPreview(null); setConfirmPhrase(''); }}
              style={{ flex: 1, backgroundColor: C.bgSoft, borderColor: C.border, borderWidth: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' }}
              data-testid="security-incident-cancel">
              <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.018', 'Cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleSend} disabled={confirmPhrase.trim() !== 'SEND' || busy === 'sending'}
              style={{ flex: 2, backgroundColor: confirmPhrase.trim() === 'SEND' ? C.primary : C.bgSoft, borderColor: C.primary, borderWidth: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center', opacity: busy === 'sending' ? 0.6 : 1 }}
              data-testid="security-incident-send-btn">
              <Text style={{ color: confirmPhrase.trim() === 'SEND' ? 'var(--app-primary-text)' : C.textMuted, fontSize: 12, fontWeight: '800' }}>
                {busy === 'sending' ? 'Sending…' : `2. Broadcast to ${Number(preview.recipient_count || 0).toLocaleString()} users`}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {err ? <Text style={{ color: C.error, fontSize: 11, marginBottom: 10 }} data-testid="security-incident-error">{err}</Text> : null}
      {msg ? <Text style={{ color: C.success, fontSize: 11, marginBottom: 10 }} data-testid="security-incident-success">{msg}</Text> : null}

      <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12, padding: 12 }}
        data-testid="security-incident-history">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.019', 'Recent broadcasts · regulatory audit trail')}</Text>
          <TouchableOpacity onPress={loadHistory} data-testid="security-incident-history-refresh">
            <Ionicons name="refresh" size={14} color={C.textSec} />
          </TouchableOpacity>
        </View>
        {history.length === 0 ? (
          <Text style={{ color: C.textMuted, fontSize: 11 }}>{tx('admin.securityIncidentBroadcastPanel.auto.text.020', 'No security broadcasts sent yet.')}</Text>
        ) : history.map((b) => {
          const sevC = SEVERITIES.find((s) => s.value === b.severity)?.color || C.primary;
          return (
            <View key={b.broadcast_id} style={{ borderTopColor: C.border, borderTopWidth: 1, paddingVertical: 8 }}
              data-testid={`security-incident-history-row-${b.broadcast_id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(sevC, '22'), borderColor: sevC, borderWidth: 1 }}>
                  <Text style={{ color: sevC, fontSize: 8, fontWeight: '800' }}>{(b.severity || '').toUpperCase()}</Text>
                </View>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{(b.incident_type || '').replace(/_/g, ' ')}</Text>
              </View>
              <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }}>
                by {b.broadcast_by || '—'} · {b.sent_at ? new Date(b.sent_at).toLocaleString() : '—'} · {Number(b.recipient_count || 0).toLocaleString()} users
              </Text>
              <Text style={{ color: C.textMuted, fontSize: 10 }}>
                Email ✓{b.sent_email} ✗{b.failed_email}{b.push_enabled ? ` · Push ✓${b.sent_push} ✗${b.failed_push}` : ' · Push: off'}
              </Text>
            </View>
          );
        })}
      </View>
    </ScrollView>
  );
}
