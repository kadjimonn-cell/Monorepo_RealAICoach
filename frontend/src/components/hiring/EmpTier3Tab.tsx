/**
 * EmpTier3Tab — Careers Tier 3 Admin Console
 * -------------------------------------------
 * Three-in-one admin tab embedded in `/hiring-hub` (employer view):
 *   - Counteroffer Queue: candidate counter-proposals + accept/reject
 *   - Talent Pool: silver-medalist candidates + manual tagging
 *   - Nurture: one-click run-now, next-cadence info
 *
 * All backend endpoints live under `/api/careers/*` and are admin-only.
 *
 * on colored primary/success CTA buttons ("Accept counter", "Run nurture
 * cadence", "Send invite"). Semantic brand/state tokens constant across
 * themes. Structural chrome uses `colors.*` from useTheme().
 */
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

type Colors = {
  bg: string; card: string; text: string; muted: string; border: string;
  primary: string; success: string; warning: string; error: string; accent: string;
};

type CounterRow = {
  offer_id: string;
  application_id?: string;
  candidate_name?: string;
  candidate_email?: string;
  role?: string;
  role_title?: string;
  counter_message?: string;
  counter_amount?: number | null;
  counter_currency?: string;
  counter_submitted_at?: string;
  decision?: string | null;
  pending_counter?: any;
  current_base_salary?: number | null;
  ai_recommendation?: AiRecommendation | null;
};

type AiRecommendation = {
  recommendation: 'accept' | 'revise' | 'reject';
  confidence: number;
  rationale: string;
  generated_at?: string;
  cached?: boolean;
  fair_counter?: { base_salary?: number | null; equity?: string | null; signing_bonus?: number | null };
};

type TalentRow = {
  application_id: string;
  full_name?: string;
  email?: string;
  role?: string;
  resume_score?: { score?: number };
  is_silver_medalist?: boolean;
  nurture_last_sent_at?: string | null;
};

type NurtureResult = {
  ok?: boolean;
  sent?: number;
  skipped?: number;
  errors?: number;
};

function fmtRelative(iso?: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diff = Math.round((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  } catch {
    return iso;
  }
}

export default function EmpTier3Tab({ C }: { C: Colors }) {
  const [section, setSection] = useState<'counters' | 'talent' | 'nurture'>('counters');

  return (
    <View data-testid="emp-tier3-tab" testID="emp-tier3-tab" style={{ gap: 14 }}>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        {(
          [
            { k: 'counters' as const, label: 'Counteroffer Queue', icon: 'cash-outline' },
            { k: 'talent' as const, label: 'Talent Pool', icon: 'people-outline' },
            { k: 'nurture' as const, label: 'Nurture', icon: 'mail-outline' },
          ]
        ).map((s) => (
          <TouchableOpacity
            key={s.k}
            onPress={() => setSection(s.k)}
            data-testid={`tier3-section-${s.k}`}
            testID={`tier3-section-${s.k}`}
            style={{
              paddingHorizontal: 12,
              paddingVertical: 8,
              borderRadius: 999,
              borderWidth: 1,
              flexDirection: 'row',
              gap: 6,
              alignItems: 'center',
              backgroundColor: section === s.k ? (globalThis as any).__alphaColor(C.accent, '22') : C.card,
              borderColor: section === s.k ? C.accent : C.border,
            }}
          >
            <Ionicons name={s.icon as any} size={14} color={section === s.k ? C.accent : C.muted} />
            <Text style={{ color: section === s.k ? C.accent : C.text, fontSize: 12, fontWeight: '700' }}>{s.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {section === 'counters' && <CounterQueue C={C} />}
      {section === 'talent' && <TalentPool C={C} />}
      {section === 'nurture' && <NurtureConsole C={C} />}
    </View>
  );
}

// ─────────────────── Counteroffer Queue ───────────────────

function CounterQueue({ C }: { C: Colors }) {
  const [rows, setRows] = useState<CounterRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string>('');
  const [aiBusy, setAiBusy] = useState<string>('');
  const [err, setErr] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const r = await api.get('/careers/offers/counter-queue');
      setRows(Array.isArray(r.data?.items) ? r.data.items : []);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Failed to load counter queue');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const decide = async (offerId: string, decision: 'accept' | 'reject') => {
    setBusy(offerId);
    try {
      await api.post(`/careers/offers/${offerId}/counter/decide`, { decision });
      await load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Decision failed');
    } finally {
      setBusy('');
    }
  };

  const analyze = async (offerId: string) => {
    setAiBusy(offerId);
    setErr('');
    try {
      const r = await api.post(`/careers/offers/${offerId}/counter/ai-analyze`);
      setRows((prev) => prev.map((row) => row.offer_id === offerId ? { ...row, ai_recommendation: r.data } : row));
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'AI analysis failed');
    } finally {
      setAiBusy('');
    }
  };

  if (loading) return <ActivityIndicator color={C.accent} />;
  if (err) return <Text style={{ color: C.error, fontSize: 12 }} data-testid="tier3-counter-error" testID="tier3-counter-error">{err}</Text>;

  return (
    <View data-testid="tier3-counter-queue" testID="tier3-counter-queue" style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>Pending counter-offers ({rows.length})</Text>
        <TouchableOpacity onPress={load} data-testid="tier3-counter-refresh" testID="tier3-counter-refresh">
          <Ionicons name="refresh" size={16} color={C.muted} />
        </TouchableOpacity>
      </View>
      {rows.length === 0 ? (
        <Text style={{ color: C.muted, fontSize: 12 }} data-testid="tier3-counter-empty" testID="tier3-counter-empty">
          No counter-offers awaiting review. They appear here the moment a candidate submits one.
        </Text>
      ) : null}
      {rows.map((r, idx) => (
        <View
          key={r.offer_id}
          data-testid={`tier3-counter-row-${idx}`}
          testID={`tier3-counter-row-${idx}`}
          style={{
            borderWidth: 1,
            borderColor: C.border,
            borderRadius: 12,
            backgroundColor: C.card,
            padding: 12,
            gap: 6,
          }}
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }} numberOfLines={1}>
              {r.candidate_name || r.candidate_email || r.offer_id}
            </Text>
            <Text style={{ color: C.muted, fontSize: 10 }}>{fmtRelative(r.counter_submitted_at)}</Text>
          </View>
          {r.role ? <Text style={{ color: C.muted, fontSize: 11 }}>{r.role}</Text> : null}
          {r.counter_amount != null ? (
            <Text style={{ color: C.accent, fontSize: 13, fontWeight: '700' }}>
              Counter: {Intl.NumberFormat().format(r.counter_amount)} {r.counter_currency || 'USD'}
            </Text>
          ) : null}
          {r.counter_message ? (
            <Text style={{ color: C.text, fontSize: 12 }} numberOfLines={5}>{r.counter_message}</Text>
          ) : null}

          {/* AI recommendation */}
          {r.ai_recommendation ? (
            <AiRecommendationPill C={C} rec={r.ai_recommendation} testIdSuffix={String(idx)} />
          ) : null}

          <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
            <TouchableOpacity
              disabled={aiBusy === r.offer_id}
              onPress={() => analyze(r.offer_id)}
              data-testid={`tier3-counter-ai-analyze-${idx}`}
              testID={`tier3-counter-ai-analyze-${idx}`}
              style={{ paddingHorizontal: 10, paddingVertical: 9, borderRadius: 10, backgroundColor: C.card, borderWidth: 1, borderColor: C.accent, opacity: aiBusy === r.offer_id ? 0.5 : 1, flexDirection: 'row', alignItems: 'center', gap: 6 }}
            >
              {aiBusy === r.offer_id ? (
                <ActivityIndicator color={C.accent} size="small" />
              ) : (
                <Ionicons name="sparkles-outline" size={13} color={C.accent} />
              )}
              <Text style={{ color: C.accent, fontSize: 11, fontWeight: '800' }}>
                {r.ai_recommendation ? 'Re-analyze' : 'AI analyze'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              disabled={busy === r.offer_id}
              onPress={() => decide(r.offer_id, 'accept')}
              data-testid={`tier3-counter-accept-${idx}`}
              testID={`tier3-counter-accept-${idx}`}
              style={{ flex: 1, backgroundColor: C.success, borderRadius: 10, paddingVertical: 9, alignItems: 'center', opacity: busy === r.offer_id ? 0.5 : 1 }}
            >
              <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>Accept counter</Text>
            </TouchableOpacity>
            <TouchableOpacity
              disabled={busy === r.offer_id}
              onPress={() => decide(r.offer_id, 'reject')}
              data-testid={`tier3-counter-reject-${idx}`}
              testID={`tier3-counter-reject-${idx}`}
              style={{ flex: 1, backgroundColor: C.card, borderWidth: 1, borderColor: C.error, borderRadius: 10, paddingVertical: 9, alignItems: 'center' }}
            >
              <Text style={{ color: C.error, fontSize: 12, fontWeight: '800' }}>Reject</Text>
            </TouchableOpacity>
          </View>
        </View>
      ))}
    </View>
  );
}

function AiRecommendationPill({ C, rec, testIdSuffix }: { C: Colors; rec: AiRecommendation; testIdSuffix: string }) {
  const tone = rec.recommendation === 'accept' ? C.success : rec.recommendation === 'reject' ? C.error : C.warning;
  const label = rec.recommendation === 'accept' ? 'Accept' : rec.recommendation === 'reject' ? 'Reject' : 'Revise';
  const fair = rec.fair_counter || {};
  const hasFair = fair.base_salary != null || fair.equity || fair.signing_bonus != null;
  return (
    <View
      data-testid={`tier3-counter-ai-rec-${testIdSuffix}`}
      testID={`tier3-counter-ai-rec-${testIdSuffix}`}
      style={{
        marginTop: 6,
        paddingVertical: 8,
        paddingHorizontal: 10,
        borderRadius: 10,
        borderWidth: 1,
        borderColor: (globalThis as any).__alphaColor(tone, '55'),
        backgroundColor: (globalThis as any).__alphaColor(tone, '14'),
      }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="sparkles" size={12} color={tone} />
        <Text style={{ color: tone, fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 0.6 }}>
          AI suggests {label}
        </Text>
        <View style={{ marginLeft: 'auto' as any, backgroundColor: (globalThis as any).__alphaColor(tone, '33'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
          <Text style={{ color: tone, fontSize: 10, fontWeight: '800' }}>{rec.confidence}% conf</Text>
        </View>
      </View>
      {rec.rationale ? (
        <Text style={{ color: C.text, fontSize: 11, marginTop: 4 }}>{rec.rationale}</Text>
      ) : null}
      {hasFair ? (
        <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }}>
          Fair counter: {fair.base_salary != null ? `base ${Intl.NumberFormat().format(fair.base_salary)}` : ''}
          {fair.equity ? ` · equity ${fair.equity}` : ''}
          {fair.signing_bonus != null ? ` · signing ${Intl.NumberFormat().format(fair.signing_bonus)}` : ''}
        </Text>
      ) : null}
    </View>
  );
}

// ─────────────────── Talent Pool ───────────────────

function TalentPool({ C }: { C: Colors }) {
  const [rows, setRows] = useState<TalentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string>('');
  const [err, setErr] = useState<string>('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const r = await api.get('/careers/talent-pool');
      setRows(Array.isArray(r.data?.items) ? r.data.items : []);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Failed to load talent pool');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const toggleTag = async (appId: string, next: boolean) => {
    setBusy(appId);
    try {
      await api.post(`/careers/talent-pool/${appId}/tag`, { silver: next });
      await load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Tag update failed');
    } finally {
      setBusy('');
    }
  };

  if (loading) return <ActivityIndicator color={C.accent} />;
  if (err) return <Text style={{ color: C.error, fontSize: 12 }} data-testid="tier3-talent-error" testID="tier3-talent-error">{err}</Text>;

  return (
    <View data-testid="tier3-talent-pool" testID="tier3-talent-pool" style={{ gap: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>Silver-medalists ({rows.length})</Text>
        <TouchableOpacity onPress={load} data-testid="tier3-talent-refresh" testID="tier3-talent-refresh">
          <Ionicons name="refresh" size={16} color={C.muted} />
        </TouchableOpacity>
      </View>
      {rows.length === 0 ? (
        <Text style={{ color: C.muted, fontSize: 12 }} data-testid="tier3-talent-empty" testID="tier3-talent-empty">
          No silver-medalists yet. Candidates are auto-tagged when rejected with a strong AI resume-score.
        </Text>
      ) : null}
      {rows.map((r, idx) => (
        <View
          key={r.application_id}
          data-testid={`tier3-talent-row-${idx}`}
          testID={`tier3-talent-row-${idx}`}
          style={{
            borderWidth: 1,
            borderColor: C.border,
            borderRadius: 12,
            backgroundColor: C.card,
            padding: 12,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <View style={{ flex: 1 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }} numberOfLines={1}>{r.full_name || r.email || r.application_id}</Text>
            <Text style={{ color: C.muted, fontSize: 11 }} numberOfLines={1}>{r.role || '—'}</Text>
            <Text style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
              Last nurtured {fmtRelative(r.nurture_last_sent_at)} · score {r.resume_score?.score ?? '—'}
            </Text>
          </View>
          <TouchableOpacity
            disabled={busy === r.application_id}
            onPress={() => toggleTag(r.application_id, !(r.is_silver_medalist ?? true))}
            data-testid={`tier3-talent-toggle-${idx}`}
            testID={`tier3-talent-toggle-${idx}`}
            style={{
              paddingHorizontal: 12,
              paddingVertical: 7,
              borderRadius: 999,
              backgroundColor: r.is_silver_medalist ? (globalThis as any).__alphaColor(C.accent, '22') : C.card,
              borderWidth: 1,
              borderColor: r.is_silver_medalist ? C.accent : C.border,
              opacity: busy === r.application_id ? 0.5 : 1,
            }}
          >
            <Text style={{ color: r.is_silver_medalist ? C.accent : C.muted, fontSize: 11, fontWeight: '700' }}>
              {r.is_silver_medalist ? 'Tagged' : 'Tag'}
            </Text>
          </TouchableOpacity>
        </View>
      ))}
    </View>
  );
}

// ─────────────────── Nurture Console ───────────────────

function NurtureConsole({ C }: { C: Colors }) {
  const [result, setResult] = useState<NurtureResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const runNow = async () => {
    setBusy(true);
    setErr('');
    try {
      const r = await api.post('/careers/talent-pool/nurture/run-now');
      setResult(r.data || {});
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Run failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View data-testid="tier3-nurture" testID="tier3-nurture" style={{ gap: 12 }}>
      <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.card, padding: 12 }}>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 6 }}>Silver-medalist nurture cadence</Text>
        <Text style={{ color: C.muted, fontSize: 11, lineHeight: 16 }}>
          Runs automatically once per day for all silver-medalist candidates who haven't been touched in the past 14 days.
          Each recipient receives at most one email per cadence cycle. Use the button below to trigger an immediate run.
        </Text>
      </View>

      <TouchableOpacity
        disabled={busy}
        onPress={runNow}
        data-testid="tier3-nurture-run-now"
        testID="tier3-nurture-run-now"
        style={{
          backgroundColor: C.accent,
          borderRadius: 12,
          paddingVertical: 12,
          alignItems: 'center',
          opacity: busy ? 0.5 : 1,
        }}
      >
        {busy ? (
          <ActivityIndicator color={C.primaryText} />
        ) : (
          <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '800' }}>Run nurture cadence now</Text>
        )}
      </TouchableOpacity>

      {err ? (
        <Text style={{ color: C.error, fontSize: 12 }} data-testid="tier3-nurture-error" testID="tier3-nurture-error">{err}</Text>
      ) : null}

      {result ? (
        <View data-testid="tier3-nurture-result" testID="tier3-nurture-result" style={{ flexDirection: 'row', gap: 8 }}>
          {([
            { label: 'Sent', value: result.sent ?? 0, tone: C.success },
            { label: 'Skipped', value: result.skipped ?? 0, tone: C.muted },
            { label: 'Errors', value: result.errors ?? 0, tone: C.error },
          ] as const).map((s) => (
            <View key={s.label} style={{ flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.card, padding: 10 }}>
              <Text style={{ color: C.muted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{s.label}</Text>
              <Text style={{ color: s.tone, fontSize: 18, fontWeight: '900', marginTop: 4 }}>{s.value}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <VideoQaInviteComposer C={C} />
    </View>
  );
}

// ─────────────────── Async Video-QA invite composer ───────────────────

function VideoQaInviteComposer({ C }: { C: Colors }) {
  const [appId, setAppId] = useState('');
  const [inviteUrl, setInviteUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const send = async () => {
    if (!appId.trim()) return;
    setBusy(true);
    setErr('');
    setInviteUrl('');
    try {
      const r = await api.post(`/careers/applications/${appId.trim()}/video-qa/invite`, {});
      setInviteUrl(r.data?.invite_url || r.data?.url || '');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Invite failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View data-testid="tier3-video-qa-invite" testID="tier3-video-qa-invite" style={{ borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.card, padding: 12, gap: 8 }}>
      <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>Async Video-QA invite</Text>
      <Text style={{ color: C.muted, fontSize: 11, lineHeight: 16 }}>
        Generate a public magic link so the candidate can record role-specific answers on their own time.
      </Text>
      <TextInput
        value={appId}
        onChangeText={setAppId}
        placeholder="Application id (e.g. app_abc123)"
        placeholderTextColor={C.muted}
        data-testid="tier3-video-qa-app-id"
        testID="tier3-video-qa-app-id"
        style={{
          borderWidth: 1,
          borderColor: C.border,
          borderRadius: 10,
          paddingHorizontal: 12,
          paddingVertical: 10,
          color: C.text,
          fontSize: 12,
        }}
      />
      <TouchableOpacity
        onPress={send}
        disabled={busy || !appId.trim()}
        data-testid="tier3-video-qa-send-invite"
        testID="tier3-video-qa-send-invite"
        style={{
          backgroundColor: C.accent,
          borderRadius: 10,
          paddingVertical: 10,
          alignItems: 'center',
          opacity: busy || !appId.trim() ? 0.5 : 1,
        }}
      >
        {busy ? <ActivityIndicator color={C.primaryText} /> : (
          <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>Send invite</Text>
        )}
      </TouchableOpacity>
      {err ? <Text style={{ color: C.error, fontSize: 11 }} data-testid="tier3-video-qa-error" testID="tier3-video-qa-error">{err}</Text> : null}
      {inviteUrl ? (
        <Text
          data-testid="tier3-video-qa-invite-url"
          testID="tier3-video-qa-invite-url"
          style={{ color: C.success, fontSize: 11, fontWeight: '700' }}
          selectable
        >
          {inviteUrl}
        </Text>
      ) : null}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
