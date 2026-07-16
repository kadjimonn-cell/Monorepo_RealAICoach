import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, ScrollView} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTranslation } from '../../hooks/useTranslation';

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
  cyan: 'var(--app-primary)' as any, cyanSoft: 'var(--app-primary-soft)',
  purple: 'var(--app-primary)', purpleSoft: 'var(--app-primary-soft)',
  onPrimaryText: 'var(--app-primary-text)' as any,
};

const REC_COLOR: Record<string, string> = {
  strong_hire: C.success,
  lean_hire: C.cyan,
  no_hire: C.warning,
  strong_no_hire: C.error,
};
const REC_LABEL: Record<string, string> = {
  strong_hire: 'Strong hire',
  lean_hire: 'Lean hire',
  no_hire: 'No hire',
  strong_no_hire: 'Strong no hire',
};

type Rubric = { role_key: string; display_name: string; criteria: { id: string; label: string; weight: number }[] };

// ─────────────────────────────────────────────────────────────────────────────
// Stalled-candidate badge — lives in the widget row as a red chip
// ─────────────────────────────────────────────────────────────────────────────

export function StalledBadge({ onOpen }: { onOpen?: () => void }) {
  const { t } = useTranslation();
  const [count, setCount] = useState(0);
  const [severity, setSeverity] = useState({ critical: 0, warning: 0 });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/careers/applications/stalled?days=5');
      setCount(r.data?.count || 0);
      setSeverity(r.data?.severity || { critical: 0, warning: 0 });
    } catch { /* silent */ }
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading || count === 0) return null;
  const col = severity.critical > 0 ? C.error : C.warning;
  return (
    <TouchableOpacity
      onPress={onOpen}
      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(col, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(col, '44') }}
      data-testid="stalled-badge" testID="stalled-badge"
    >
      <Ionicons name="hourglass" size={12} color={col} />
      <Text style={{ color: col, fontSize: 10, fontWeight: '800' }}>
        {t('careerEnhancements.stalled.badge', 'Stalled')} · {count}
      </Text>
    </TouchableOpacity>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Stalled-candidate modal (list view)
// ─────────────────────────────────────────────────────────────────────────────

export function StalledModal({ onClose, onOpenApp }: { onClose: () => void; onOpenApp?: (id: string) => void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(5);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/careers/applications/stalled?days=${days}`);
      setItems(r.data?.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [days]);
  useEffect(() => { load(); }, [load]);

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(8,14,36,0.72)', zIndex: 25, alignItems: 'center', justifyContent: 'center', padding: 20 }} data-testid="stalled-modal" testID="stalled-modal">
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, maxWidth: 960, width: '100%', maxHeight: '80%' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="hourglass" size={20} color={C.warning} />
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }}>{t('careerEnhancements.stalled.title', 'Stalled candidates')} · {days}+ {t('careerEnhancements.stalled.days', 'days')}</Text>
          </View>
          <TouchableOpacity onPress={onClose} data-testid="stalled-modal-close" testID="stalled-modal-close">
            <Ionicons name="close" size={20} color={C.textSec} />
          </TouchableOpacity>
        </View>
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 10 }}>
          {[3, 5, 10, 14].map((d) => (
            <TouchableOpacity
              key={d}
              onPress={() => setDays(d)}
              style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: days === d ? C.primarySoft : C.bgSoft, borderWidth: 1, borderColor: days === d ? C.primary : C.border }}
              data-testid={`stalled-filter-${d}`} testID={`stalled-filter-${d}`}
            >
              <Text style={{ color: days === d ? C.primary : C.textSec, fontSize: 10, fontWeight: '700' }}>{d}+ days</Text>
            </TouchableOpacity>
          ))}
        </View>
        <ScrollView style={{ maxHeight: 420 }}>
          {loading ? (
            <View style={{ padding: 30, alignItems: 'center' }}><ActivityIndicator color={C.primary} /></View>
          ) : items.length === 0 ? (
            <View style={{ padding: 20 }} data-testid="stalled-modal-empty" testID="stalled-modal-empty">
              <Text style={{ color: C.textMuted, fontSize: 12, textAlign: 'center' }}>
                {t('careerEnhancements.stalled.empty', 'No stalled candidates at this threshold.')}
              </Text>
            </View>
          ) : items.map((it, idx) => {
            const sev = it.days_stalled >= 10 ? C.error : C.warning;
            return (
              <TouchableOpacity
                key={it.application_id || idx}
                onPress={() => onOpenApp && onOpenApp(it.application_id)}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 10, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, marginBottom: 6 }}
                data-testid={`stalled-row-${idx}`} testID={`stalled-row-${idx}`}
              >
                <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(sev, '22'), alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ color: sev, fontSize: 12, fontWeight: '800' }}>{it.days_stalled}d</Text>
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{it.full_name || '—'}</Text>
                  <Text style={{ color: C.textMuted, fontSize: 10 }} numberOfLines={1}>
                    {it.position} · {it.status}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={14} color={C.textMuted} />
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Duplicate-detection badge + modal
// ─────────────────────────────────────────────────────────────────────────────

export function DuplicatesBadge({ onOpen }: { onOpen?: () => void }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/careers/applications/duplicates');
        setCount(r.data?.group_count || 0);
      } catch { /* silent */ }
    })();
  }, []);
  if (count === 0) return null;
  return (
    <TouchableOpacity
      onPress={onOpen}
      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.purpleSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '44') }}
      data-testid="duplicates-badge" testID="duplicates-badge"
    >
      <Ionicons name="copy" size={12} color={C.purple} />
      <Text style={{ color: C.purple, fontSize: 10, fontWeight: '800' }}>Dupes · {count}</Text>
    </TouchableOpacity>
  );
}

export function DuplicatesModal({ onClose, onMerged }: { onClose: () => void; onMerged: () => void }) {
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [mergingKey, setMergingKey] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/careers/applications/duplicates');
      setGroups(r.data?.groups || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const mergeGroup = async (group: any) => {
    if (!group?.rows || group.rows.length < 2) return;
    const primary = group.rows[0];
    const secondary = group.rows.slice(1).map((r: any) => r.application_id);
    setMergingKey(group.match_value);
    try {
      await api.post(`/careers/applications/${primary.application_id}/merge`, {
        secondary_ids: secondary, keep_notes: true,
      });
      await load();
      onMerged();
    } catch { /* silent */ }
    setMergingKey('');
  };

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(8,14,36,0.72)', zIndex: 25, alignItems: 'center', justifyContent: 'center', padding: 20 }} data-testid="duplicates-modal" testID="duplicates-modal">
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, maxWidth: 960, width: '100%', maxHeight: '86%' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="copy" size={20} color={C.purple} />
            <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }}>{tx('admin.careerEnhancements.auto.text.001', 'Duplicate candidate clusters')}</Text>
          </View>
          <TouchableOpacity onPress={onClose} data-testid="duplicates-modal-close" testID="duplicates-modal-close">
            <Ionicons name="close" size={20} color={C.textSec} />
          </TouchableOpacity>
        </View>
        <ScrollView style={{ maxHeight: 500 }}>
          {loading ? (
            <View style={{ padding: 30, alignItems: 'center' }}><ActivityIndicator color={C.primary} /></View>
          ) : groups.length === 0 ? (
            <View style={{ padding: 20 }} data-testid="duplicates-empty" testID="duplicates-empty">
              <Text style={{ color: C.textMuted, fontSize: 12, textAlign: 'center' }}>{tx('admin.careerEnhancements.auto.text.002', 'No duplicate clusters found. Candidate data is clean.')}</Text>
            </View>
          ) : groups.map((g, gi) => {
            const isMerging = mergingKey === g.match_value;
            return (
              <View
                key={`${g.match_type}-${g.match_value}-${gi}`}
                style={{ marginBottom: 10, padding: 12, backgroundColor: C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: C.border }}
                data-testid={`dup-group-${gi}`} testID={`dup-group-${gi}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 999, backgroundColor: C.purpleSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '44') }}>
                      <Text style={{ color: C.purple, fontSize: 9, fontWeight: '800' }}>{g.match_type.toUpperCase()}</Text>
                    </View>
                    <Text style={{ color: C.textSec, fontSize: 11 }} numberOfLines={1}>{g.match_value}</Text>
                    <Text style={{ color: C.textMuted, fontSize: 10 }}>· {g.size} rows</Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => mergeGroup(g)}
                    disabled={isMerging}
                    style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: C.primary, opacity: isMerging ? 0.6 : 1 }}
                    data-testid={`dup-merge-${gi}`} testID={`dup-merge-${gi}`}
                  >
                    <Text style={{ color: C.onPrimaryText, fontSize: 10, fontWeight: '800' }}>
                      {isMerging ? 'Merging…' : 'Merge into #1'}
                    </Text>
                  </TouchableOpacity>
                </View>
                {g.rows.map((r: any, ri: number) => (
                  <View
                    key={r.application_id}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 5, borderTopWidth: ri === 0 ? 0 : 1, borderTopColor: C.border }}
                  >
                    <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: ri === 0 ? C.primarySoft : C.border, alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ color: ri === 0 ? C.primary : C.textMuted, fontSize: 9, fontWeight: '800' }}>{ri === 0 ? 'P' : ri}</Text>
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} numberOfLines={1}>{r.full_name || '—'}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 9 }} numberOfLines={1}>
                        {r.email} · {r.position} · {r.status}
                      </Text>
                    </View>
                  </View>
                ))}
              </View>
            );
          })}
        </ScrollView>
      </View>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Portal link button (used inside the detail modal)
// ─────────────────────────────────────────────────────────────────────────────

export function PortalLinkButton({ appId }: { appId: string }) {
  const [loading, setLoading] = useState(false);
  const [url, setUrl] = useState('');
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState('');

  const generate = async () => {
    setLoading(true); setErr('');
    try {
      const r = await api.post(`/careers/applications/${appId}/portal-link`, {});
      setUrl(r.data?.url || '');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Failed to generate link');
    }
    setLoading(false);
  };

  const copy = async () => {
    try {
      if (typeof navigator !== 'undefined' && (navigator as any).clipboard) {
        await (navigator as any).clipboard.writeText(url);
        setCopied(true);
        setTimeout(() => setCopied(false), 2200);
      }
    } catch { /* silent */ }
  };

  return (
    <View style={{ padding: 12, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, marginBottom: 10 }} data-testid="portal-link-section" testID="portal-link-section">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Ionicons name="link" size={14} color={C.cyan} />
        <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{tx('admin.careerEnhancements.auto.text.003', 'Candidate portal link')}</Text>
      </View>
      <Text style={{ color: C.textMuted, fontSize: 10, marginBottom: 8 }}>{tx('admin.careerEnhancements.auto.text.004', 'Generates a magic URL the candidate can open (no login) to see their live application status, next steps, and interview slot.')}</Text>
      {!url ? (
        <TouchableOpacity
          onPress={generate}
          disabled={loading}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: C.cyan, alignSelf: 'flex-start', opacity: loading ? 0.6 : 1 }}
          data-testid="portal-generate-btn" testID="portal-generate-btn"
        >
          {loading ? <ActivityIndicator size="small" color={C.onPrimaryText} /> : <Ionicons name="key" size={12} color={C.onPrimaryText} />}
          <Text style={{ color: C.onPrimaryText, fontSize: 11, fontWeight: '800' }}>
            {loading ? 'Generating…' : 'Generate portal link'}
          </Text>
        </TouchableOpacity>
      ) : (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <TextInput accessibilityLabel={tx('admin.careerEnhancements.auto.accessibility.001', 'Text input')}
            value={url}
            editable={false}
            style={{ flex: 1, backgroundColor: C.card, color: C.text, fontSize: 11, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: C.border }}
            data-testid="portal-url-input" testID="portal-url-input"
          />
          <TouchableOpacity
            onPress={copy}
            style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, backgroundColor: copied ? C.success : C.primary }}
            data-testid="portal-copy-btn" testID="portal-copy-btn"
          >
            <Text style={{ color: C.onPrimaryText, fontSize: 11, fontWeight: '800' }}>{copied ? '✓ Copied' : 'Copy'}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={generate}
            disabled={loading}
            style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: C.border }}
            data-testid="portal-rotate-btn" testID="portal-rotate-btn"
          >
            <Ionicons name="refresh" size={12} color={C.textSec} />
          </TouchableOpacity>
        </View>
      )}
      {err ? <Text style={{ color: C.error, fontSize: 10, marginTop: 6 }}>{err}</Text> : null}
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scorecards section (used inside the detail modal)
// ─────────────────────────────────────────────────────────────────────────────

export function ScorecardsSection({ appId, interviewerDefault }: { appId: string; interviewerDefault?: string }) {
  const { t } = useTranslation();
  const [rubric, setRubric] = useState<Rubric | null>(null);
  const [items, setItems] = useState<any[]>([]);
  const [consensus, setConsensus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  // form
  const [interviewer, setInterviewer] = useState(interviewerDefault || '');
  const [rec, setRec] = useState<'strong_hire' | 'lean_hire' | 'no_hire' | 'strong_no_hire'>('lean_hire');
  const [comments, setComments] = useState('');
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState(false);
  // AI
  const [transcript, setTranscript] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiPreview, setAiPreview] = useState<any>(null);
  const [formOpen, setFormOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, cons, rub] = await Promise.all([
        api.get(`/careers/applications/${appId}/scorecards`),
        api.get(`/careers/applications/${appId}/scorecards/consensus`),
        api.get(`/careers/scorecard-rubrics`),
      ]);
      setItems(list.data?.items || []);
      setConsensus(cons.data?.consensus || null);
      // choose rubric from first existing scorecard, or fall back to role-resolved via server rubric list
      let r: Rubric | null = null;
      const firstSnap = (list.data?.items || [])[0]?.rubric_snapshot;
      if (firstSnap) r = firstSnap;
      if (!r) {
        // let the server resolve when we POST; use generic for the UI form until then
        const gen = (rub.data?.rubrics || []).find((x: Rubric) => x.role_key === 'generic');
        r = gen || (rub.data?.rubrics || [])[0];
      }
      setRubric(r);
      if (r) {
        const seed: Record<string, number> = {};
        r.criteria.forEach((c) => { seed[c.id] = 3; });
        setRatings(seed);
      }
    } catch { /* silent */ }
    setLoading(false);
  }, [appId]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!rubric || !interviewer.trim()) return;
    setSaving(true);
    try {
      await api.post(`/careers/applications/${appId}/scorecards`, {
        interviewer_name: interviewer.trim(),
        stage: 'interview',
        ratings,
        overall: 3,
        hire_recommendation: rec,
        comments: comments.trim(),
      });
      setFormOpen(false);
      setComments('');
      await load();
    } catch { /* silent */ }
    setSaving(false);
  };

  const saveAi = async () => {
    if (!aiPreview) return;
    setAiBusy(true);
    try {
      await api.post(`/careers/applications/${appId}/scorecards/ai-score`, {
        transcript, interviewer_name: aiPreview.interviewer_name || 'AI Scorecard', persist: true,
      });
      setAiPreview(null);
      setTranscript('');
      await load();
    } catch { /* silent */ }
    setAiBusy(false);
  };

  const runAi = async () => {
    if (transcript.length < 50) return;
    setAiBusy(true); setAiPreview(null);
    try {
      const r = await api.post(`/careers/applications/${appId}/scorecards/ai-score`, {
        transcript, interviewer_name: 'AI Scorecard', persist: false,
      });
      setAiPreview(r.data?.scorecard || null);
    } catch { /* silent */ }
    setAiBusy(false);
  };

  if (loading) {
    return <View style={{ paddingVertical: 20, alignItems: 'center' }}><ActivityIndicator color={C.primary} /></View>;
  }

  return (
    <View data-testid="scorecards-section" testID="scorecards-section">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="clipboard" size={14} color={C.primary} />
          <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }}>{t('careerEnhancements.scorecards.title', 'Interview scorecards')}</Text>
          <Text style={{ color: C.textMuted, fontSize: 10 }}>· {items.length} {t('careerEnhancements.scorecards.submitted', 'submitted')}</Text>
        </View>
        <TouchableOpacity
          onPress={() => setFormOpen((v) => !v)}
          style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: C.primary }}
          data-testid="scorecard-new-btn" testID="scorecard-new-btn"
        >
          <Text style={{ color: C.onPrimaryText, fontSize: 10, fontWeight: '800' }}>{formOpen ? t('careerEnhancements.actions.cancel', 'Cancel') : t('careerEnhancements.actions.newScorecard', '+ New scorecard')}</Text>
        </TouchableOpacity>
      </View>

      {/* Consensus */}
      {consensus && (
        <View style={{ padding: 10, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, marginBottom: 10, flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap' }} data-testid="scorecards-consensus" testID="scorecards-consensus">
          <View style={{ width: 54, height: 54, borderRadius: 12, backgroundColor: C.primarySoft, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '44') }}>
            <Text style={{ color: C.primary, fontSize: 18, fontWeight: '900' }} data-testid="consensus-mean" testID="consensus-mean">{consensus.mean_overall}</Text>
            <Text style={{ color: C.textMuted, fontSize: 8 }}>{t('careerEnhancements.scorecards.avg', 'AVG')}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 120 }}>
            <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700' }}>{t('careerEnhancements.scorecards.consensus', 'CONSENSUS')}</Text>
            <View style={{ marginTop: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor((REC_COLOR[consensus.top_recommendation] || C.textSec), '22'), alignSelf: 'flex-start' }}>
              <Text style={{ color: REC_COLOR[consensus.top_recommendation] || C.textSec, fontSize: 10, fontWeight: '800' }}>
                {REC_LABEL[consensus.top_recommendation] || consensus.top_recommendation}
              </Text>
            </View>
          </View>
          {(consensus.top_strengths?.length || 0) > 0 && (
            <View style={{ flex: 1, minWidth: 160 }}>
              <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700' }}>{t('careerEnhancements.scorecards.topStrengths', 'TOP STRENGTHS')}</Text>
              <Text style={{ color: C.success, fontSize: 10, marginTop: 2 }} numberOfLines={2}>
                {consensus.top_strengths.map(([k, n]: [string, number]) => `${k} (${n})`).join(' · ')}
              </Text>
            </View>
          )}
          {(consensus.top_concerns?.length || 0) > 0 && (
            <View style={{ flex: 1, minWidth: 160 }}>
              <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700' }}>{t('careerEnhancements.scorecards.topConcerns', 'TOP CONCERNS')}</Text>
              <Text style={{ color: C.warning, fontSize: 10, marginTop: 2 }} numberOfLines={2}>
                {consensus.top_concerns.map(([k, n]: [string, number]) => `${k} (${n})`).join(' · ')}
              </Text>
            </View>
          )}
        </View>
      )}

      {/* AI Scorecard box */}
      <View style={{ padding: 10, backgroundColor: C.purpleSoft, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '44'), marginBottom: 10 }} data-testid="ai-scorecard-box" testID="ai-scorecard-box">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <Ionicons name="sparkles" size={12} color={C.purple} />
          <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{t('careerEnhancements.ai.title', 'AI scorecard from transcript')}</Text>
        </View>
        <TextInput
          value={transcript}
          onChangeText={setTranscript}
          placeholder={t('careerEnhancements.ai.placeholder', 'Paste interview transcript or notes (min 50 chars). Claude will fill the rubric.')}
          placeholderTextColor={C.textMuted}
          multiline
          numberOfLines={4}
          style={{ backgroundColor: C.card, color: C.text, fontSize: 11, padding: 8, borderRadius: 8, borderWidth: 1, borderColor: C.border, minHeight: 70, textAlignVertical: 'top' }}
          data-testid="ai-scorecard-transcript" testID="ai-scorecard-transcript"
        />
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6 }}>
          <TouchableOpacity
            onPress={runAi}
            disabled={aiBusy || transcript.length < 50}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.purple, opacity: aiBusy || transcript.length < 50 ? 0.5 : 1 }}
            data-testid="ai-scorecard-run" testID="ai-scorecard-run"
          >
            {aiBusy ? <ActivityIndicator size="small" color={C.onPrimaryText} /> : <Ionicons name="flash" size={12} color={C.onPrimaryText} />}
            <Text style={{ color: C.onPrimaryText, fontSize: 10, fontWeight: '800' }}>{aiBusy ? t('careerEnhancements.ai.thinking', 'Thinking…') : t('careerEnhancements.ai.run', 'Run AI')}</Text>
          </TouchableOpacity>
          <Text style={{ color: C.textMuted, fontSize: 9 }}>{transcript.length} chars</Text>
        </View>
        {aiPreview && (
          <View style={{ marginTop: 10, padding: 8, backgroundColor: C.card, borderRadius: 8, borderWidth: 1, borderColor: C.border }} data-testid="ai-scorecard-preview" testID="ai-scorecard-preview">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{t('careerEnhancements.ai.suggestion', 'AI suggestion')} · {t('careerEnhancements.ai.overall', 'overall')} {aiPreview.overall}/5</Text>
              <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor((REC_COLOR[aiPreview.hire_recommendation] || C.textSec), '22') }}>
                <Text style={{ color: REC_COLOR[aiPreview.hire_recommendation] || C.textSec, fontSize: 9, fontWeight: '800' }}>
                  {REC_LABEL[aiPreview.hire_recommendation] || aiPreview.hire_recommendation}
                </Text>
              </View>
            </View>
            {(aiPreview.strengths?.length || 0) > 0 && (
              <Text style={{ color: C.success, fontSize: 10, marginTop: 2 }}>
                + {aiPreview.strengths.join(' · ')}
              </Text>
            )}
            {(aiPreview.concerns?.length || 0) > 0 && (
              <Text style={{ color: C.warning, fontSize: 10, marginTop: 2 }}>
                − {aiPreview.concerns.join(' · ')}
              </Text>
            )}
            {aiPreview.comments ? (
              <Text style={{ color: C.textSec, fontSize: 10, marginTop: 4 }} numberOfLines={3}>{aiPreview.comments}</Text>
            ) : null}
            <TouchableOpacity
              onPress={saveAi}
              disabled={aiBusy}
              style={{ marginTop: 8, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.success, alignSelf: 'flex-start' }}
              data-testid="ai-scorecard-save" testID="ai-scorecard-save"
            >
              <Text style={{ color: C.onPrimaryText, fontSize: 10, fontWeight: '800' }}>{t('careerEnhancements.ai.saveAsScorecard', 'Save as AI scorecard')}</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* Manual form */}
      {formOpen && rubric && (
        <View style={{ padding: 10, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, marginBottom: 10 }} data-testid="scorecard-form" testID="scorecard-form">
          <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700', marginBottom: 6 }}>
            RUBRIC: {rubric.display_name.toUpperCase()}
          </Text>
          <TextInput
            value={interviewer}
            onChangeText={setInterviewer}
            placeholder={t('careerEnhancements.scorecards.interviewerPlaceholder', 'Your name (interviewer)')}
            placeholderTextColor={C.textMuted}
            style={{ backgroundColor: C.card, color: C.text, fontSize: 11, padding: 8, borderRadius: 8, borderWidth: 1, borderColor: C.border, marginBottom: 8 }}
            data-testid="scorecard-interviewer" testID="scorecard-interviewer"
          />
          {rubric.criteria.map((c) => (
            <View key={c.id} style={{ marginBottom: 8 }}>
              <Text style={{ color: C.textSec, fontSize: 11, marginBottom: 3 }}>{c.label}</Text>
              <View style={{ flexDirection: 'row', gap: 4 }}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <TouchableOpacity
                    key={n}
                    onPress={() => setRatings((p) => ({ ...p, [c.id]: n }))}
                    style={{ flex: 1, paddingVertical: 7, borderRadius: 6, backgroundColor: ratings[c.id] === n ? C.primary : C.card, borderWidth: 1, borderColor: ratings[c.id] === n ? C.primary : C.border, alignItems: 'center' }}
                    data-testid={`scorecard-rate-${c.id}-${n}`} testID={`scorecard-rate-${c.id}-${n}`}
                  >
                    <Text style={{ color: ratings[c.id] === n ? C.onPrimaryText : C.textSec, fontSize: 11, fontWeight: '800' }}>{n}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          ))}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {(['strong_hire', 'lean_hire', 'no_hire', 'strong_no_hire'] as const).map((r) => (
              <TouchableOpacity
                key={r}
                onPress={() => setRec(r)}
                style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, backgroundColor: rec === r ? (REC_COLOR[r] || C.primary) : C.card, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(REC_COLOR[r], '44') }}
                data-testid={`scorecard-rec-${r}`} testID={`scorecard-rec-${r}`}
              >
                <Text style={{ color: rec === r ? C.onPrimaryText : REC_COLOR[r], fontSize: 10, fontWeight: '800' }}>{REC_LABEL[r]}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TextInput
            value={comments}
            onChangeText={setComments}
            placeholder={t('careerEnhancements.scorecards.commentsPlaceholder', 'Comments (optional)')}
            placeholderTextColor={C.textMuted}
            multiline
            numberOfLines={3}
            style={{ backgroundColor: C.card, color: C.text, fontSize: 11, padding: 8, borderRadius: 8, borderWidth: 1, borderColor: C.border, marginTop: 8, minHeight: 60, textAlignVertical: 'top' }}
            data-testid="scorecard-comments" testID="scorecard-comments"
          />
          <TouchableOpacity
            onPress={save}
            disabled={saving || !interviewer.trim()}
            style={{ marginTop: 8, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: C.primary, alignSelf: 'flex-start', opacity: saving || !interviewer.trim() ? 0.5 : 1 }}
            data-testid="scorecard-save-btn" testID="scorecard-save-btn"
          >
            <Text style={{ color: C.onPrimaryText, fontSize: 11, fontWeight: '800' }}>{saving ? t('careerEnhancements.actions.saving', 'Saving…') : t('careerEnhancements.actions.saveScorecard', 'Save scorecard')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Existing scorecards */}
      {items.length === 0 ? (
        <Text style={{ color: C.textMuted, fontSize: 11, fontStyle: 'italic' }} data-testid="scorecards-empty" testID="scorecards-empty">
          {t('careerEnhancements.scorecards.empty', 'No scorecards yet. Run an AI scorecard from a transcript or fill one manually above.')}
        </Text>
      ) : items.map((it, idx) => (
        <View
          key={it.scorecard_id || idx}
          style={{ padding: 10, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, marginBottom: 6 }}
          data-testid={`scorecard-row-${idx}`} testID={`scorecard-row-${idx}`}
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{it.interviewer_name}</Text>
              {it.source === 'ai' && (
                <View style={{ paddingHorizontal: 5, paddingVertical: 2, borderRadius: 999, backgroundColor: C.purpleSoft }}>
                  <Text style={{ color: C.purple, fontSize: 8, fontWeight: '800' }}>{tx('admin.careerEnhancements.auto.text.005', 'AI')}</Text>
                </View>
              )}
            </View>
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
              <Text style={{ color: C.primary, fontSize: 13, fontWeight: '800' }}>{it.overall}/5</Text>
              <View style={{ paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor((REC_COLOR[it.hire_recommendation] || C.textSec), '22') }}>
                <Text style={{ color: REC_COLOR[it.hire_recommendation] || C.textSec, fontSize: 9, fontWeight: '800' }}>
                  {REC_LABEL[it.hire_recommendation] || it.hire_recommendation}
                </Text>
              </View>
            </View>
          </View>
          {it.comments ? <Text style={{ color: C.textSec, fontSize: 11, marginTop: 4 }} numberOfLines={3}>{it.comments}</Text> : null}
          <Text style={{ color: C.textMuted, fontSize: 9, marginTop: 4 }}>
            {String(it.created_at || '').slice(0, 19).replace('T', ' ')}
          </Text>
        </View>
      ))}
    </View>
  );
}
