import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import {
  deleteEmailGuardrailTemplatePolicy,
  fetchEmailGuardrailBlocklist,
  fetchEmailGuardrailEvents,
  fetchEmailGuardrailOverview,
  fetchEmailGuardrailTemplatePolicies,
  unblockEmailGuardrailRecipient,
  upsertEmailGuardrailBlocklist,
  upsertEmailGuardrailTemplatePolicy,
} from '../../services/emailGuardrailControl';
import { fetchTabAliasTelemetrySummary } from '../../services/tabAliasTelemetry';

const txFallback = (t: (key: string) => string, key: string, fallback: string) => {
  const v = t(key);
  return v === key ? fallback : v;
};

const fmtDate = (v?: string) => {
  if (!v) return '—';
  try { return new Date(v).toLocaleString(); } catch { return String(v); }
};

const SectionCard = ({ children, colors, testId }: { children: React.ReactNode; colors: any; testId: string }) => (
  <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 16, backgroundColor: colors.cardBg, padding: 14, gap: 10 }} data-testid={testId} testID={testId}>
    {children}
  </View>
);

const ActionButton = ({ label, onPress, colors, testId, danger, disabled }: { label: string; onPress: () => void; colors: any; testId: string; danger?: boolean; disabled?: boolean }) => (
  <TouchableOpacity accessibilityLabel="On press in email guardrail control center workspace button"
    onPress={onPress}
    disabled={disabled}
    style={{
      paddingHorizontal: 12,
      paddingVertical: 9,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: danger ? `${colors.error}66` : colors.border,
      backgroundColor: danger ? `${colors.error}12` : colors.bgSoft,
      opacity: disabled ? 0.5 : 1,
    }}
    data-testid={testId}
    testID={testId}
  >
    <Text style={{ color: danger ? colors.error : colors.text, fontSize: 11, fontWeight: '800' }}>{label}</Text>
  </TouchableOpacity>
);

export default function EmailGuardrailControlCenterWorkspace() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((k: string, fb: string) => txFallback(t, k, fb), [t]);
  const { width } = useWindowDimensions();
  const isMobile = width < 760;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string>('');

  const [overview, setOverview] = useState<any>(null);
  const [aliasTelemetry, setAliasTelemetry] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [blocklist, setBlocklist] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);

  const [eventsTemplateFilter, setEventsTemplateFilter] = useState('');
  const [eventsRecipientFilter, setEventsRecipientFilter] = useState('');
  const [eventsHoursFilter, setEventsHoursFilter] = useState('72');

  const [blockRecipient, setBlockRecipient] = useState('');
  const [blockReason, setBlockReason] = useState('manual_guardrail_review');
  const [blockApplyCanonical, setBlockApplyCanonical] = useState(false);

  const [policyTemplateKey, setPolicyTemplateKey] = useState('');
  const [policyCapValue, setPolicyCapValue] = useState('2');
  const [policyNote, setPolicyNote] = useState('');

  const pendingRef = useRef(false);
  const aliveRef = useRef(true);

  const loadAll = useCallback(async (mode: 'initial' | 'refresh' | 'silent' = 'initial') => {
    if (pendingRef.current) return;
    pendingRef.current = true;
    if (mode === 'initial') setLoading(true);
    if (mode === 'refresh') setRefreshing(true);
    setError(null);
    try {
      const [ov, ev, bl, pol, alias] = await Promise.all([
        fetchEmailGuardrailOverview(24),
        fetchEmailGuardrailEvents({
          hours: Number(eventsHoursFilter || '72') || 72,
          template_key: eventsTemplateFilter.trim() || undefined,
          recipient: eventsRecipientFilter.trim() || undefined,
          limit: 200,
        }),
        fetchEmailGuardrailBlocklist({ active_only: false, limit: 200 }),
        fetchEmailGuardrailTemplatePolicies(false),
        fetchTabAliasTelemetrySummary(30),
      ]);
      if (!aliveRef.current) return;
      setOverview(ov || null);
      setAliasTelemetry(alias || null);
      setEvents(Array.isArray(ev?.items) ? ev.items : []);
      setBlocklist(Array.isArray(bl?.items) ? bl.items : []);
      setPolicies(Array.isArray(pol?.items) ? pol.items : []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load guardrail control center');
    } finally {
      pendingRef.current = false;
      if (aliveRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [eventsHoursFilter, eventsRecipientFilter, eventsTemplateFilter]);

  useEffect(() => {
    loadAll('initial');
    const timer = setInterval(() => loadAll('silent'), 60000);
    return () => {
      aliveRef.current = false;
      clearInterval(timer);
    };
  }, [loadAll]);

  const activeBlocklist = useMemo(() => blocklist.filter((b) => b?.active !== false), [blocklist]);

  const applyBlocklist = async (active: boolean) => {
    if (!blockRecipient.trim()) {
      setMessage('Recipient email is required.');
      return;
    }
    try {
      await upsertEmailGuardrailBlocklist({
        recipient_email: blockRecipient.trim(),
        active,
        apply_to_canonical: blockApplyCanonical,
        reason: blockReason.trim() || 'manual_guardrail_review',
      });
      setMessage(active ? 'Recipient added/updated in blocklist.' : 'Recipient updated to inactive.');
      setBlockRecipient('');
      await loadAll('silent');
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to update blocklist.');
    }
  };

  const savePolicy = async () => {
    if (!policyTemplateKey.trim()) {
      setMessage('Template key is required.');
      return;
    }
    const cap = Number(policyCapValue || '2');
    if (!Number.isFinite(cap) || cap < 1 || cap > 20) {
      setMessage('Max per fingerprint must be between 1 and 20.');
      return;
    }
    try {
      await upsertEmailGuardrailTemplatePolicy(policyTemplateKey.trim(), {
        max_per_fingerprint: cap,
        active: true,
        note: policyNote.trim(),
      });
      setMessage('Template cap policy saved.');
      await loadAll('silent');
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to save template policy.');
    }
  };

  const removePolicy = async (templateKey: string) => {
    try {
      await deleteEmailGuardrailTemplatePolicy(templateKey);
      setMessage(`Removed policy for ${templateKey}.`);
      await loadAll('silent');
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to delete policy.');
    }
  };

  const unblockRecipient = async (email: string) => {
    try {
      await unblockEmailGuardrailRecipient(email);
      setMessage(`Unblocked ${email}.`);
      await loadAll('silent');
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to unblock recipient.');
    }
  };

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }} data-testid="email-guardrail-loading" testID="email-guardrail-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('emailGuardrail.loading', 'Loading Email Guardrail Control Center...')}</Text>
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }} data-testid="email-guardrail-control-center" testID="email-guardrail-control-center">
      <View style={{ paddingHorizontal: isMobile ? 12 : 20, paddingTop: 14, paddingBottom: 8, gap: 8 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <View>
            <Text style={{ color: colors.text, fontSize: isMobile ? 23 : 30, fontWeight: '900' }} data-testid="email-guardrail-title" testID="email-guardrail-title">
              Email Guardrail Control Center
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="email-guardrail-subtitle" testID="email-guardrail-subtitle">
              Live cap events, unblock review, and template-wise cap policy governance.
            </Text>
          </View>
          <ActionButton label={refreshing ? 'Refreshing...' : 'Refresh'} onPress={() => loadAll('refresh')} colors={colors} testId="email-guardrail-refresh-button" disabled={refreshing} />
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: isMobile ? 12 : 20, paddingBottom: 30, gap: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadAll('refresh')} tintColor={colors.primary} />}
        data-testid="email-guardrail-scroll-root"
        testID="email-guardrail-scroll-root"
      >
        {!!error && (
          <View style={{ borderWidth: 1, borderColor: `${colors.error}66`, backgroundColor: `${colors.error}12`, borderRadius: 10, padding: 10 }} data-testid="email-guardrail-error-banner" testID="email-guardrail-error-banner">
            <Text style={{ color: colors.error, fontSize: 11 }}>{error}</Text>
          </View>
        )}
        {!!message && (
          <View style={{ borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}10`, borderRadius: 10, padding: 10 }} data-testid="email-guardrail-message-banner" testID="email-guardrail-message-banner">
            <Text style={{ color: colors.text, fontSize: 11 }}>{message}</Text>
          </View>
        )}

        <SectionCard colors={colors} testId="email-guardrail-overview-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="email-guardrail-overview-title" testID="email-guardrail-overview-title">Live Guardrail Snapshot (24h)</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-kpi-blocked-events" testID="email-guardrail-kpi-blocked-events">Blocked events: {overview?.blocked_events ?? 0}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-kpi-blocklist" testID="email-guardrail-kpi-blocklist">Active blocklist: {overview?.active_blocklist_entries ?? 0}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-kpi-template-policies" testID="email-guardrail-kpi-template-policies">Template policies: {overview?.active_template_policies ?? 0}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-kpi-capped-keys" testID="email-guardrail-kpi-capped-keys">Capped keys: {overview?.capped_fingerprint_keys ?? 0}</Text>
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="email-guardrail-alias-telemetry-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="email-guardrail-alias-telemetry-title" testID="email-guardrail-alias-telemetry-title">
            Legacy Alias Hit Telemetry (30d)
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-alias-total-hits" testID="email-guardrail-alias-total-hits">Total hits: {aliasTelemetry?.total_hits ?? 0}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-alias-exec-hits" testID="email-guardrail-alias-exec-hits">Executive: {aliasTelemetry?.by_console?.executive ?? 0}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-alias-ops-hits" testID="email-guardrail-alias-ops-hits">Operations: {aliasTelemetry?.by_console?.operations ?? 0}</Text>
          </View>

          <View style={{ gap: 8 }}>
            {(Array.isArray(aliasTelemetry?.top_pairs) ? aliasTelemetry.top_pairs : []).slice(0, 12).map((pair: any, idx: number) => (
              <View key={`${pair?.source_tab_id || idx}-${pair?.canonical_tab_id || idx}`} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingTop: idx === 0 ? 0 : 8 }} data-testid={`email-guardrail-alias-pair-row-${idx}`} testID={`email-guardrail-alias-pair-row-${idx}`}>
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{pair?.source_tab_id || '--'} ➜ {pair?.canonical_tab_id || '--'}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>hits: {pair?.hit_count ?? 0} • exec: {pair?.console_breakdown?.executive ?? 0} • ops: {pair?.console_breakdown?.operations ?? 0}</Text>
              </View>
            ))}
            {(!aliasTelemetry?.top_pairs || aliasTelemetry.top_pairs.length === 0) && (
              <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-alias-pairs-empty" testID="email-guardrail-alias-pairs-empty">
                No legacy alias hits captured in selected window.
              </Text>
            )}
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="email-guardrail-events-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="email-guardrail-events-title" testID="email-guardrail-events-title">Cap Block Events</Text>
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
            <TextInput value={eventsHoursFilter} onChangeText={setEventsHoursFilter} placeholder="Hours" placeholderTextColor={colors.textMuted} style={{ flex: 0.5, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, color: colors.text, fontSize: 12 }} data-testid="email-guardrail-events-hours-input" testID="email-guardrail-events-hours-input" />
            <TextInput value={eventsTemplateFilter} onChangeText={setEventsTemplateFilter} placeholder="Template key filter" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, color: colors.text, fontSize: 12 }} data-testid="email-guardrail-events-template-filter" testID="email-guardrail-events-template-filter" />
            <TextInput value={eventsRecipientFilter} onChangeText={setEventsRecipientFilter} placeholder="Recipient filter" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, color: colors.text, fontSize: 12 }} data-testid="email-guardrail-events-recipient-filter" testID="email-guardrail-events-recipient-filter" />
            <ActionButton label="Apply" onPress={() => loadAll('refresh')} colors={colors} testId="email-guardrail-events-apply-filter-button" />
          </View>
          <View style={{ gap: 8 }}>
            {events.slice(0, 30).map((event, idx) => (
              <View key={event?.event_id || idx} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingTop: idx === 0 ? 0 : 8 }} data-testid={`email-guardrail-event-row-${idx}`} testID={`email-guardrail-event-row-${idx}`}>
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{event?.template_key || '(unknown)'} • {event?.canonical_recipient || '--'}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>count={event?.current_count ?? 0} max={event?.max_allowed ?? 0} • {fmtDate(event?.created_at)}</Text>
              </View>
            ))}
            {events.length === 0 && <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-events-empty" testID="email-guardrail-events-empty">No cap-block events for current filter.</Text>}
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="email-guardrail-blocklist-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="email-guardrail-blocklist-title" testID="email-guardrail-blocklist-title">Recipient Blocklist Review</Text>
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
            <TextInput value={blockRecipient} onChangeText={setBlockRecipient} placeholder="recipient@example.com" placeholderTextColor={colors.textMuted} style={{ flex: 1.3, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, color: colors.text, fontSize: 12 }} data-testid="email-guardrail-block-recipient-input" testID="email-guardrail-block-recipient-input" />
            <TextInput value={blockReason} onChangeText={setBlockReason} placeholder="Reason" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, color: colors.text, fontSize: 12 }} data-testid="email-guardrail-block-reason-input" testID="email-guardrail-block-reason-input" />
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <ActionButton label={`Apply canonical: ${blockApplyCanonical ? 'ON' : 'OFF'}`} onPress={() => setBlockApplyCanonical((v) => !v)} colors={colors} testId="email-guardrail-block-canonical-toggle" />
            <ActionButton label="Block / Update" onPress={() => applyBlocklist(true)} colors={colors} testId="email-guardrail-block-save-button" danger />
            <ActionButton label="Deactivate" onPress={() => applyBlocklist(false)} colors={colors} testId="email-guardrail-block-deactivate-button" />
          </View>

          <View style={{ gap: 8 }}>
            {activeBlocklist.slice(0, 25).map((item, idx) => (
              <View key={item?.recipient_email || idx} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingTop: idx === 0 ? 0 : 8, flexDirection: 'row', justifyContent: 'space-between', gap: 8 }} data-testid={`email-guardrail-blocklist-row-${idx}`} testID={`email-guardrail-blocklist-row-${idx}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{item?.recipient_email || '--'}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>reason: {item?.reason || '--'} • updated: {fmtDate(item?.updated_at)}</Text>
                </View>
                <ActionButton label="Unblock" onPress={() => unblockRecipient(String(item?.recipient_email || ''))} colors={colors} testId={`email-guardrail-unblock-button-${idx}`} />
              </View>
            ))}
            {activeBlocklist.length === 0 && <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-blocklist-empty" testID="email-guardrail-blocklist-empty">No active blocklist entries.</Text>}
          </View>
        </SectionCard>

        <SectionCard colors={colors} testId="email-guardrail-policies-card">
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="email-guardrail-policies-title" testID="email-guardrail-policies-title">Template-wise Cap Policy</Text>
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 8 }}>
            <TextInput value={policyTemplateKey} onChangeText={setPolicyTemplateKey} placeholder="template_key (e.g. daily_digest)" placeholderTextColor={colors.textMuted} style={{ flex: 1.3, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, color: colors.text, fontSize: 12 }} data-testid="email-guardrail-policy-template-input" testID="email-guardrail-policy-template-input" />
            <TextInput value={policyCapValue} onChangeText={setPolicyCapValue} placeholder="max_per_fingerprint" placeholderTextColor={colors.textMuted} style={{ flex: 0.7, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, color: colors.text, fontSize: 12 }} data-testid="email-guardrail-policy-cap-input" testID="email-guardrail-policy-cap-input" />
            <TextInput value={policyNote} onChangeText={setPolicyNote} placeholder="note" placeholderTextColor={colors.textMuted} style={{ flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9, color: colors.text, fontSize: 12 }} data-testid="email-guardrail-policy-note-input" testID="email-guardrail-policy-note-input" />
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            <ActionButton label="Save policy" onPress={savePolicy} colors={colors} testId="email-guardrail-policy-save-button" />
          </View>
          <View style={{ gap: 8 }}>
            {policies.slice(0, 30).map((policy, idx) => (
              <View key={policy?.template_key || idx} style={{ borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: colors.border, paddingTop: idx === 0 ? 0 : 8, flexDirection: 'row', justifyContent: 'space-between', gap: 8 }} data-testid={`email-guardrail-policy-row-${idx}`} testID={`email-guardrail-policy-row-${idx}`}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{policy?.template_key || '--'} • cap={policy?.max_per_fingerprint ?? '--'}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>active: {String(policy?.active !== false)} • note: {policy?.note || '--'}</Text>
                </View>
                <ActionButton label="Delete" onPress={() => removePolicy(String(policy?.template_key || ''))} colors={colors} danger testId={`email-guardrail-policy-delete-button-${idx}`} />
              </View>
            ))}
            {policies.length === 0 && <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="email-guardrail-policy-empty" testID="email-guardrail-policy-empty">No template override policies configured.</Text>}
          </View>
        </SectionCard>
      </ScrollView>
    </View>
  );
}
