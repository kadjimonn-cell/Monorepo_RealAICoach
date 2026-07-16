import { useTranslation } from '../../hooks/useTranslation';
import React, { useState, useMemo, useCallback, useEffect } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

const C = {
  bg: 'var(--app-bg)' as any,
  bgSoft: 'var(--app-surface)' as any,
  card: 'var(--app-card-bg)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any, primarySoft: 'var(--app-primary-soft)', primaryText: 'var(--app-primary-text)' as any,
  success: 'var(--app-success)', successSoft: 'var(--app-success-soft)',
  warning: 'var(--app-warning)', warningSoft: 'var(--app-warning-soft)',
  error: 'var(--app-error)', errorSoft: 'var(--app-error-soft)',
  cyan: 'var(--app-primary)' as any, cyanSoft: 'var(--app-primary-soft)',
  purple: 'var(--app-primary)', purpleSoft: 'var(--app-primary-soft)',
};

export const KANBAN_COLUMNS = [
  { id: 'received', label: 'Received', color: C.textSec },
  { id: 'screening', label: 'Screening', color: C.cyan },
  { id: 'interview', label: 'Interview', color: C.warning },
  { id: 'offer', label: 'Offer', color: C.purple },
  { id: 'hired', label: 'Hired', color: C.success },
  { id: 'rejected', label: 'Rejected', color: C.error },
];

function scoreColor(score: number): string {
  if (score >= 85) return C.success;
  if (score >= 70) return C.cyan;
  if (score >= 50) return C.warning;
  return C.error;
}

// ─────────────────────────────────────────────────────────────────────────────
// Resume Score badge (inline row badge + single-row action)
// ─────────────────────────────────────────────────────────────────────────────

export function ResumeScoreBadge({ app, onScored }: { app: any; onScored?: (rs: any) => void }) {
  const [busy, setBusy] = useState(false);
  const [_err, setErr] = useState('');
  const rs = app.resume_score;

  const run = async (e?: any) => {
    try { e?.stopPropagation && e.stopPropagation(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/CareerTier1.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setBusy(true); setErr('');
    try {
      const r = await api.post(`/careers/applications/${app.application_id}/resume-score`, { persist: true });
      onScored?.(r.data?.resume_score);
    } catch (ex: any) {
      setErr(ex?.response?.data?.detail?.slice?.(0, 60) || 'Failed');
    }
    setBusy(false);
  };

  if (!rs) {
    return (
      <TouchableOpacity
        onPress={run}
        disabled={busy}
        style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, backgroundColor: C.purpleSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '44'), opacity: busy ? 0.6 : 1 }}
        data-testid={`resume-score-run-${app.application_id}`} testID={`resume-score-run-${app.application_id}`}
      >
        {busy ? <ActivityIndicator size="small" color={C.purple} /> : <Ionicons name="sparkles" size={10} color={C.purple} />}
        <Text style={{ color: C.purple, fontSize: 9, fontWeight: '800' }}>{busy ? '…' : 'AI score'}</Text>
      </TouchableOpacity>
    );
  }

  const col = scoreColor(rs.score || 0);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(col, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(col, '44') }} data-testid={`resume-score-${app.application_id}`} testID={`resume-score-${app.application_id}`}>
      <Ionicons name="sparkles" size={9} color={col} />
      <Text style={{ color: col, fontSize: 10, fontWeight: '800' }}>{rs.score}</Text>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// View toggle (Table | Kanban)
// ─────────────────────────────────────────────────────────────────────────────

export function ViewToggle({ value, onChange }: { value: 'table' | 'kanban'; onChange: (v: 'table' | 'kanban') => void }) {
  return (
    <View style={{ flexDirection: 'row', gap: 0, borderRadius: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="view-toggle" testID="view-toggle">
      {(['table', 'kanban'] as const).map((v) => (
        <TouchableOpacity
          key={v}
          onPress={() => onChange(v)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: value === v ? C.primary : 'transparent' }}
          data-testid={`view-toggle-${v}`} testID={`view-toggle-${v}`}
        >
          <Ionicons name={v === 'table' ? 'list' : 'grid'} size={12} color={value === v ? C.primaryText : C.textSec} />
          <Text style={{ color: value === v ? C.primaryText : C.textSec, fontSize: 10, fontWeight: '800' }}>
            {v === 'table' ? 'Table' : 'Kanban'}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Kanban board (HTML5 drag/drop on web)
// ─────────────────────────────────────────────────────────────────────────────

export function KanbanBoard({ apps, onOpen, onStatusChanged }: { apps: any[]; onOpen: (a: any) => void; onStatusChanged: (appId: string, status: string) => void }) {
  const [draggingId, setDraggingId] = useState('');
  const [dropTarget, setDropTarget] = useState('');
  const [sortByScore, setSortByScore] = useState(false);

  const grouped = useMemo(() => {
    const m: Record<string, any[]> = {};
    KANBAN_COLUMNS.forEach((c) => { m[c.id] = []; });
    apps.forEach((a) => {
      const s = (a.status || 'received').toLowerCase();
      if (!m[s]) m[s] = [];
      m[s].push(a);
    });
    if (sortByScore) {
      // Auto-scored on ingest via /careers/apply → auto_score_on_ingest.
      // Sort each column by resume_score.score desc; unscored sink to the bottom.
      Object.keys(m).forEach((k) => {
        m[k] = [...m[k]].sort((a, b) => {
          const sa = typeof a?.resume_score?.score === 'number' ? a.resume_score.score : -1;
          const sb = typeof b?.resume_score?.score === 'number' ? b.resume_score.score : -1;
          return sb - sa;
        });
      });
    }
    return m;
  }, [apps, sortByScore]);

  const handleDrop = async (colId: string) => {
    const id = draggingId;
    setDraggingId('');
    setDropTarget('');
    if (!id) return;
    const app = apps.find((a) => a.application_id === id);
    if (!app || app.status === colId) return;
    try {
      await api.post(`/careers/applications/bulk-action`, {
        application_ids: [id], action: 'set_status', new_status: colId,
      });
      onStatusChanged(id, colId);
    } catch { /* silent */ }
  };

  return (
    <View style={{ marginBottom: 16 }} data-testid="kanban-board" testID="kanban-board">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', marginBottom: 8, gap: 8 }}>
        <Text style={{ color: C.textMuted, fontSize: 10 }}>{tx('admin.careerTier1.auto.text.001', 'Auto-scored on ingest')}</Text>
        <TouchableOpacity onPress={() => setSortByScore((s) => !s)} accessibilityLabel={tx('admin.careerTier1.auto.accessibility.001', 'Sort kanban by AI score')}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 5,
            paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999,
            borderWidth: 1,
            borderColor: sortByScore ? C.primary : C.border,
            backgroundColor: sortByScore ? (globalThis as any).__alphaColor(C.primary, '18') : C.bgSoft,
          }}
          data-testid="kanban-sort-by-score-toggle" testID="kanban-sort-by-score-toggle"
          accessibilityRole="switch"
          accessibilityLabel={tx('admin.careerTier1.auto.accessibility.002', 'Sort Kanban columns by AI resume score')}
          accessibilityState={{ checked: sortByScore }}
        >
          <Ionicons name={sortByScore ? 'flame' : 'flame-outline'} size={12} color={sortByScore ? C.primary : C.textSec} />
          <Text style={{ color: sortByScore ? C.primary : C.textSec, fontSize: 10, fontWeight: '800' }}>
            {sortByScore ? 'Sorted by top score' : 'Sort by top score'}
          </Text>
        </TouchableOpacity>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={{ flexDirection: 'row', gap: 10, paddingBottom: 8 }}>
          {KANBAN_COLUMNS.map((col) => {
            const rows = grouped[col.id] || [];
            const isTarget = dropTarget === col.id;
            return (
              <View
                key={col.id}
                // @ts-ignore — web-only DOM props
                onDragOver={(e: any) => { e.preventDefault(); setDropTarget(col.id); }}
                onDragLeave={() => setDropTarget((t) => (t === col.id ? '' : t))}
                onDrop={() => handleDrop(col.id)}
                style={{ width: 240, minHeight: 200, backgroundColor: isTarget ? (globalThis as any).__alphaColor(col.color, '18') : C.bgSoft, borderRadius: 12, borderWidth: 1, borderColor: isTarget ? col.color : C.border, padding: 8 }}
                data-testid={`kanban-col-${col.id}`} testID={`kanban-col-${col.id}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: col.color }} />
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>{col.label}</Text>
                  </View>
                  <Text style={{ color: C.textMuted, fontSize: 10 }}>{rows.length}</Text>
                </View>
                {rows.map((a) => {
                  const rs = a.resume_score;
                  const col2 = rs ? scoreColor(rs.score || 0) : C.textMuted;
                  return (
                    <View
                      key={a.application_id}
                      // @ts-ignore
                      draggable={true}
                      // @ts-ignore
                      onDragStart={() => setDraggingId(a.application_id)}
                      // @ts-ignore
                      onDragEnd={() => setDraggingId('')}
                      style={{ padding: 8, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: draggingId === a.application_id ? C.primary : C.border, marginBottom: 6, opacity: draggingId === a.application_id ? 0.6 : 1 }}
                      data-testid={`kanban-card-${a.application_id}`} testID={`kanban-card-${a.application_id}`}
                    >
                      <TouchableOpacity onPress={() => onOpen(a)} accessibilityLabel={tx('admin.careerTier1.auto.accessibility.003', 'Open application')}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                          <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', flex: 1 }} numberOfLines={1}>
                            {a.name || a.full_name || '—'}
                          </Text>
                          {rs ? (
                            <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 999, backgroundColor: (globalThis as any).__alphaColor(col2, '22') }}>
                              <Text style={{ color: col2, fontSize: 9, fontWeight: '800' }}>{rs.score}</Text>
                            </View>
                          ) : null}
                        </View>
                        <Text style={{ color: C.textMuted, fontSize: 9 }} numberOfLines={1}>
                          {a.role_title || 'Open role'}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  );
                })}
                {rows.length === 0 && (
                  <Text style={{ color: C.textMuted, fontSize: 10, fontStyle: 'italic', padding: 10, textAlign: 'center' }}>{tx('admin.careerTier1.auto.text.002', 'Drop here')}</Text>
                )}
              </View>
            );
          })}
        </View>
      </ScrollView>
      <Text style={{ color: C.textMuted, fontSize: 9, marginTop: 4, textAlign: 'center' }}>{tx('admin.careerTier1.auto.text.003', 'Tip: drag a card into any column to change its stage. Changes log to the audit trail.')}</Text>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Bulk actions toolbar (floating)
// ─────────────────────────────────────────────────────────────────────────────

export function BulkActionsToolbar({ selectedIds, onClear, onApplied }: { selectedIds: string[]; onClear: () => void; onApplied: () => void }) {
  const [action, setAction] = useState<'set_status' | 'add_tag' | 'soft_delete_gdpr'>('set_status');
  const [status, setStatus] = useState('screening');
  const [tag, setTag] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ updated: number } | null>(null);

  const apply = async () => {
    if (selectedIds.length === 0) return;
    setBusy(true); setResult(null);
    try {
      const body: any = { application_ids: selectedIds, action };
      if (action === 'set_status') body.new_status = status;
      if (action === 'add_tag') body.tag = tag || 'hot';
      if (action === 'soft_delete_gdpr') body.gdpr_reason = 'bulk_admin_gdpr_request';
      const r = await api.post('/careers/applications/bulk-action', body);
      setResult({ updated: r.data?.updated || 0 });
      onApplied();
    } catch { /* silent */ }
    setBusy(false);
  };

  if (selectedIds.length === 0) return null;
  return (
    <View style={{ position: 'fixed' as any, bottom: 20, left: '50%', transform: [{ translateX: '-50%' as any }], backgroundColor: C.card, borderRadius: 14, padding: 12, borderWidth: 1, borderColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 8, zIndex: 30, boxShadow: '0 8px 24px rgba(0,0,0,0.3)' as any, maxWidth: 960 }} data-testid="bulk-toolbar" testID="bulk-toolbar">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="checkmark-done" size={14} color={C.primary} />
        <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="bulk-count" testID="bulk-count">
          {selectedIds.length} selected
        </Text>
      </View>

      <View style={{ flexDirection: 'row', gap: 4 }}>
        {(['set_status', 'add_tag', 'soft_delete_gdpr'] as const).map((a) => (
          <TouchableOpacity
            key={a}
            onPress={() => setAction(a)}
            style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, backgroundColor: action === a ? C.primarySoft : 'transparent', borderWidth: 1, borderColor: action === a ? C.primary : C.border }}
            data-testid={`bulk-action-${a}`} testID={`bulk-action-${a}`}
          >
            <Text style={{ color: action === a ? C.primary : C.textSec, fontSize: 10, fontWeight: '700' }}>
              {a === 'set_status' ? 'Status' : a === 'add_tag' ? 'Tag' : 'GDPR'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {action === 'set_status' && (
        <View style={{ flexDirection: 'row', gap: 3, flexWrap: 'wrap', maxWidth: 320 }}>
          {['screening', 'interview', 'offer', 'hired', 'rejected'].map((s) => (
            <TouchableOpacity
              key={s}
              onPress={() => setStatus(s)}
              style={{ paddingHorizontal: 7, paddingVertical: 4, borderRadius: 999, backgroundColor: status === s ? C.primary : C.bgSoft, borderWidth: 1, borderColor: C.border }}
              data-testid={`bulk-status-${s}`} testID={`bulk-status-${s}`}
            >
              <Text style={{ color: status === s ? C.primaryText : C.textSec, fontSize: 9, fontWeight: '700' }}>{s}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
      {action === 'add_tag' && (
        <TextInput
          value={tag}
          onChangeText={setTag}
          placeholder={tx('admin.careerTier1.auto.placeholder.001', 'Tag (e.g. hot, referral)')}
          placeholderTextColor={C.textMuted}
          style={{ backgroundColor: C.bgSoft, color: C.text, fontSize: 11, padding: 6, borderRadius: 6, borderWidth: 1, borderColor: C.border, minWidth: 140 }}
          data-testid="bulk-tag-input" testID="bulk-tag-input"
        />
      )}

      <TouchableOpacity
        onPress={apply}
        disabled={busy}
        style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: action === 'soft_delete_gdpr' ? C.error : C.primary, opacity: busy ? 0.6 : 1 }}
        data-testid="bulk-apply-btn" testID="bulk-apply-btn"
      >
        <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '800' }}>{busy ? 'Applying…' : 'Apply'}</Text>
      </TouchableOpacity>
      {result && (
        <Text style={{ color: C.success, fontSize: 10, fontWeight: '700' }} data-testid="bulk-result" testID="bulk-result">
          ✓ {result.updated} updated
        </Text>
      )}
      <TouchableOpacity onPress={onClear} data-testid="bulk-clear-btn" testID="bulk-clear-btn">
        <Ionicons name="close" size={14} color={C.textSec} />
      </TouchableOpacity>
    </View>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// GDPR Retention Panel (modal)
// ─────────────────────────────────────────────────────────────────────────────

export function GDPRRetentionPanel({ onClose }: { onClose: () => void }) {
  const [policy, setPolicy] = useState<any>(null);
  const [preview, setPreview] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [purging, setPurging] = useState(false);

  const load = useCallback(async () => {
    try {
      const [pol, prev, aud] = await Promise.all([
        api.get('/careers/gdpr/retention-policy'),
        api.get('/careers/gdpr/purge-preview'),
        api.get('/careers/gdpr/audit?limit=20'),
      ]);
      setPolicy(pol.data?.policy);
      setPreview(prev.data);
      setAudit(aud.data?.items || []);
    } catch { /* silent */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const savePolicy = async () => {
    if (!policy) return;
    setSaving(true);
    try {
      await api.post('/careers/gdpr/retention-policy', {
        rejected_retention_days: parseInt(String(policy.rejected_retention_days), 10) || 180,
        withdrawn_retention_days: parseInt(String(policy.withdrawn_retention_days), 10) || 180,
        audit_enabled: !!policy.audit_enabled,
        auto_purge_enabled: !!policy.auto_purge_enabled,
      });
      await load();
    } catch { /* silent */ }
    setSaving(false);
  };

  const runPurge = async () => {
    if (!preview || !preview.total_eligible) return;
    setPurging(true);
    try {
      await api.post('/careers/gdpr/purge');
      await load();
    } catch { /* silent */ }
    setPurging(false);
  };

  if (!policy) {
    return (
      <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(8,14,36,0.72)', zIndex: 25, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={C.primary} />
      </View>
    );
  }

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(8,14,36,0.78)', zIndex: 25, alignItems: 'center', justifyContent: 'center', padding: 20 }} data-testid="gdpr-panel" testID="gdpr-panel">
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: C.border, maxWidth: 960, width: '100%', maxHeight: '88%' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name="shield-checkmark" size={20} color={C.success} />
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }}>{tx('admin.careerTier1.auto.text.004', 'GDPR Retention Engine')}</Text>
          </View>
          <TouchableOpacity onPress={onClose} data-testid="gdpr-close-btn" testID="gdpr-close-btn">
            <Ionicons name="close" size={20} color={C.textSec} />
          </TouchableOpacity>
        </View>

        <ScrollView style={{ maxHeight: 520 }}>
          {/* Policy */}
          <View style={{ padding: 12, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, marginBottom: 10 }}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700', marginBottom: 8 }}>{tx('admin.careerTier1.auto.text.005', 'RETENTION POLICY')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <Text style={{ color: C.text, fontSize: 11, minWidth: 140 }}>{tx('admin.careerTier1.auto.text.006', 'Rejected retention (days)')}</Text>
              <TextInput accessibilityLabel={tx('admin.careerTier1.auto.accessibility.004', 'Text input')}
                value={String(policy.rejected_retention_days)}
                onChangeText={(v) => setPolicy({ ...policy, rejected_retention_days: v })}
                keyboardType="numeric"
                style={{ backgroundColor: C.card, color: C.text, fontSize: 11, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, borderWidth: 1, borderColor: C.border, width: 80 }}
                data-testid="gdpr-rejected-days" testID="gdpr-rejected-days"
              />
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <Text style={{ color: C.text, fontSize: 11, minWidth: 140 }}>{tx('admin.careerTier1.auto.text.007', 'Withdrawn retention (days)')}</Text>
              <TextInput accessibilityLabel={tx('admin.careerTier1.auto.accessibility.005', 'Text input')}
                value={String(policy.withdrawn_retention_days)}
                onChangeText={(v) => setPolicy({ ...policy, withdrawn_retention_days: v })}
                keyboardType="numeric"
                style={{ backgroundColor: C.card, color: C.text, fontSize: 11, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, borderWidth: 1, borderColor: C.border, width: 80 }}
                data-testid="gdpr-withdrawn-days" testID="gdpr-withdrawn-days"
              />
            </View>
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
              <TouchableOpacity
                onPress={() => setPolicy({ ...policy, audit_enabled: !policy.audit_enabled })}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}
                data-testid="gdpr-toggle-audit" testID="gdpr-toggle-audit"
              >
                <View style={{ width: 16, height: 16, borderRadius: 4, backgroundColor: policy.audit_enabled ? C.primary : C.card, borderWidth: 1, borderColor: policy.audit_enabled ? C.primary : C.border, alignItems: 'center', justifyContent: 'center' }}>
                  {policy.audit_enabled && <Ionicons name="checkmark" size={11} color={C.primaryText} />}
                </View>
                <Text style={{ color: C.textSec, fontSize: 11 }}>{tx('admin.careerTier1.auto.text.008', 'Audit enabled')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setPolicy({ ...policy, auto_purge_enabled: !policy.auto_purge_enabled })}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}
                data-testid="gdpr-toggle-autopurge" testID="gdpr-toggle-autopurge"
              >
                <View style={{ width: 16, height: 16, borderRadius: 4, backgroundColor: policy.auto_purge_enabled ? C.warning : C.card, borderWidth: 1, borderColor: policy.auto_purge_enabled ? C.warning : C.border, alignItems: 'center', justifyContent: 'center' }}>
                  {policy.auto_purge_enabled && <Ionicons name="checkmark" size={11} color={C.primaryText} />}
                </View>
                <Text style={{ color: C.textSec, fontSize: 11 }}>{tx('admin.careerTier1.auto.text.009', 'Auto-purge')}</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity
              onPress={savePolicy}
              disabled={saving}
              style={{ alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: C.primary, opacity: saving ? 0.6 : 1 }}
              data-testid="gdpr-save-policy" testID="gdpr-save-policy"
            >
              <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '800' }}>{saving ? 'Saving…' : 'Save policy'}</Text>
            </TouchableOpacity>

            {/* Scheduler last-run stamp */}
            {policy.last_auto_purge_at && (
              <View style={{ marginTop: 10, padding: 8, backgroundColor: C.card, borderRadius: 8, borderWidth: 1, borderColor: C.border, flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }} data-testid="gdpr-scheduler-stamp" testID="gdpr-scheduler-stamp">
                <Ionicons name="time" size={12} color={C.cyan} />
                <Text style={{ color: C.textSec, fontSize: 10 }}>
                  Last scheduled run: <Text style={{ color: C.text, fontWeight: '700' }}>{String(policy.last_auto_purge_at).slice(0, 19).replace('T', ' ')}</Text>
                </Text>
                <Text style={{ color: C.textMuted, fontSize: 10 }}>
                  · purged {policy.last_auto_purge_count ?? 0}
                </Text>
                <Text style={{ color: C.textMuted, fontSize: 10 }}>
                  · trigger {policy.last_auto_purge_trigger || '—'}
                </Text>
              </View>
            )}
            <TouchableOpacity accessibilityLabel={tx('admin.careerTier1.auto.accessibility.006', 'Run scheduler now')}
              onPress={async () => {
                try {
                  await api.post('/careers/gdpr/auto-purge/run-now', {});
                  await load();
                } catch { /* silent */ }
              }}
              style={{ alignSelf: 'flex-start', marginTop: 8, flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: C.cyanSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.cyan, '44') }}
              data-testid="gdpr-run-scheduler-now" testID="gdpr-run-scheduler-now"
            >
              <Ionicons name="flash" size={10} color={C.cyan} />
              <Text style={{ color: C.cyan, fontSize: 10, fontWeight: '800' }}>{tx('admin.careerTier1.auto.text.010', 'Run scheduler now')}</Text>
            </TouchableOpacity>
          </View>

          {/* Preview + purge */}
          <View style={{ padding: 12, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, marginBottom: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('admin.careerTier1.auto.text.011', 'PURGE PREVIEW')}</Text>
              <Text style={{ color: preview?.total_eligible ? C.warning : C.textMuted, fontSize: 12, fontWeight: '800' }} data-testid="gdpr-eligible-count" testID="gdpr-eligible-count">
                {preview?.total_eligible ?? 0} eligible
              </Text>
            </View>
            {(preview?.preview || []).length === 0 ? (
              <Text style={{ color: C.textMuted, fontSize: 11, fontStyle: 'italic' }}>{tx('admin.careerTier1.auto.text.012', 'No applications currently meet the retention threshold.')}</Text>
            ) : (preview.preview as any[]).slice(0, 10).map((r, idx) => (
              <View key={r.application_id || idx} style={{ flexDirection: 'row', gap: 8, paddingVertical: 4, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: C.border }}>
                <Text style={{ color: C.text, fontSize: 11, flex: 1 }} numberOfLines={1}>{r.name || '—'}</Text>
                <Text style={{ color: C.textMuted, fontSize: 10 }}>{r.status}</Text>
                <Text style={{ color: C.textMuted, fontSize: 10 }}>{String(r.last_activity_at || '').slice(0, 10)}</Text>
              </View>
            ))}
            {preview?.total_eligible > 0 && (
              <TouchableOpacity
                onPress={runPurge}
                disabled={purging}
                style={{ marginTop: 10, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: C.error, opacity: purging ? 0.6 : 1 }}
                data-testid="gdpr-run-purge" testID="gdpr-run-purge"
              >
                <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '800' }}>
                  {purging ? 'Purging…' : `Purge ${preview.total_eligible} now`}
                </Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Audit trail */}
          <View style={{ padding: 12, backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700', marginBottom: 8 }}>AUDIT TRAIL · last {audit.length}</Text>
            {audit.length === 0 ? (
              <Text style={{ color: C.textMuted, fontSize: 11, fontStyle: 'italic' }}>{tx('admin.careerTier1.auto.text.013', 'No audit entries yet.')}</Text>
            ) : audit.map((a, idx) => (
              <View key={a.audit_id || idx} style={{ flexDirection: 'row', gap: 8, paddingVertical: 4, borderTopWidth: idx === 0 ? 0 : 1, borderTopColor: C.border }}>
                <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 999, backgroundColor: a.kind === 'retention_purge' ? C.errorSoft : a.kind === 'soft_delete' ? C.warningSoft : C.primarySoft }}>
                  <Text style={{ color: a.kind === 'retention_purge' ? C.error : a.kind === 'soft_delete' ? C.warning : C.primary, fontSize: 8, fontWeight: '800' }}>
                    {a.kind.toUpperCase().replace('_', ' ')}
                  </Text>
                </View>
                <Text style={{ color: C.textSec, fontSize: 10, flex: 1 }} numberOfLines={1}>{a.actor || 'system'}</Text>
                <Text style={{ color: C.textMuted, fontSize: 9 }}>{String(a.created_at || '').slice(0, 19).replace('T', ' ')}</Text>
              </View>
            ))}
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

export function GDPRButton({ onOpen }: { onOpen: () => void }) {
  return (
    <TouchableOpacity
      onPress={onOpen}
      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.successSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.success, '44') }}
      data-testid="gdpr-open-btn" testID="gdpr-open-btn"
    >
      <Ionicons name="shield-checkmark" size={12} color={C.success} />
      <Text style={{ color: C.success, fontSize: 10, fontWeight: '800' }}>{tx('admin.careerTier1.auto.text.014', 'GDPR')}</Text>
    </TouchableOpacity>
  );
}

/* i18n-probe t('i18n.auto.probe') */
