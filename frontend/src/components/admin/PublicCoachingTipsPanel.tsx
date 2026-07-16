// Admin CMS for the public Welcome tickertape's "Tip of the day" catalog.
// Mutations hit /api/admin/coaching-tips; the public endpoint
// /api/public/coaching-tip-of-the-day rotates through the active set by
// UTC day-of-year so edits take effect at midnight UTC.
import { useTranslation } from '../../hooks/useTranslation';
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, ScrollView } from 'react-native';
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
  primary: 'var(--app-primary)' as any, primarySoft: 'var(--app-primary-soft)', primaryText: 'var(--app-primary-text)' as any,
  warning: 'var(--app-warning)', warningSoft: 'var(--app-warning-soft)',
  success: 'var(--app-success)', successSoft: 'var(--app-success-soft)',
  error: 'var(--app-error)', errorSoft: 'var(--app-error-soft)',
};

type Tip = {
  tip_id: string;
  title: string;
  content: string;
  is_active: boolean;
  position: number;
  created_at?: string;
  updated_at?: string;
  created_by?: string;
};

export default function PublicCoachingTipsPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const [items, setItems] = useState<Tip[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newContent, setNewContent] = useState('');
  const [editId, setEditId] = useState<string>('');
  const [editTitle, setEditTitle] = useState('');
  const [editContent, setEditContent] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const { data } = await api.get('/admin/coaching-tips');
      setItems(data?.items || []);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load tips');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    const title = newTitle.trim(); const content = newContent.trim();
    if (title.length < 2 || content.length < 5) {
      setMsg('Title ≥2 chars, content ≥5 chars'); return;
    }
    if (content.length > 140) { setMsg('Content must be ≤ 140 chars'); return; }
    setBusy('create'); setMsg('');
    try {
      await api.post('/admin/coaching-tips', { title, content, is_active: true });
      setNewTitle(''); setNewContent(''); setMsg('Tip added');
      await load();
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || e?.message || 'Create failed');
    } finally { setBusy(''); }
  };

  const handleSaveEdit = async (tipId: string) => {
    setBusy(`edit-${tipId}`); setMsg('');
    try {
      await api.put(`/admin/coaching-tips/${tipId}`, { title: editTitle.trim(), content: editContent.trim() });
      setEditId(''); await load(); setMsg('Saved');
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || e?.message || 'Save failed');
    } finally { setBusy(''); }
  };

  const handleToggle = async (t: Tip) => {
    setBusy(`toggle-${t.tip_id}`);
    try {
      await api.put(`/admin/coaching-tips/${t.tip_id}`, { is_active: !t.is_active });
      await load();
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || e?.message || 'Toggle failed');
    } finally { setBusy(''); }
  };

  const handleMove = async (tipId: string, delta: number) => {
    setBusy(`move-${tipId}`);
    try {
      await api.post(`/admin/coaching-tips/${tipId}/move`, { delta });
      await load();
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || e?.message || 'Move failed');
    } finally { setBusy(''); }
  };

  const handleDelete = async (tipId: string) => {
    if (typeof window !== 'undefined' && !window.confirm?.('Delete this tip? This cannot be undone.')) return;
    setBusy(`del-${tipId}`);
    try {
      await api.delete(`/admin/coaching-tips/${tipId}`);
      await load(); setMsg('Deleted');
    } catch (e: any) {
      setMsg(e?.response?.data?.detail || e?.message || 'Delete failed');
    } finally { setBusy(''); }
  };

  const activeCount = items.filter((t) => t.is_active).length;

  return (
    <View style={{ padding: 16, backgroundColor: C.bg, minHeight: '100%' }} data-testid="coaching-tips-panel" testID="coaching-tips-panel">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <View>
          <Text style={{ color: C.text, fontSize: 20, fontWeight: '800' }}>{tx('admin.publicCoachingTipsPanel.auto.text.001', 'Welcome Tip-of-the-Day Catalog')}</Text>
          <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 2 }}>
            Curates the rotating "TIP OF THE DAY" fact on /welcome · {activeCount}/{items.length} active · rotation by UTC day
          </Text>
        </View>
        <TouchableOpacity onPress={load} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: C.primarySoft, borderColor: C.primary, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 }}
          data-testid="coaching-tips-refresh" testID="coaching-tips-refresh">
          <Ionicons name="refresh" size={13} color={C.primary} />
          <Text style={{ color: C.primary, fontSize: 11, fontWeight: '700' }}>{tx('admin.publicCoachingTipsPanel.auto.text.002', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* Create row */}
      <View style={{ backgroundColor: C.card, borderColor: C.border, borderWidth: 1, borderRadius: 12, padding: 12, marginBottom: 12 }}
        data-testid="coaching-tips-create-card" testID="coaching-tips-create-card">
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>{tx('admin.publicCoachingTipsPanel.auto.text.003', 'Add a new tip')}</Text>
        <TextInput
          value={newTitle} onChangeText={setNewTitle} placeholder={tx('admin.publicCoachingTipsPanel.auto.placeholder.001', 'Title (e.g. Small reps compound)')} placeholderTextColor={C.textMuted}
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, marginBottom: 8 }}
          data-testid="coaching-tips-new-title" testID="coaching-tips-new-title" maxLength={80}
        />
        <TextInput
          value={newContent} onChangeText={setNewContent} placeholder={tx('admin.publicCoachingTipsPanel.auto.placeholder.002', 'Content (≤ 140 chars — keeps the rotating pill single-line)')} placeholderTextColor={C.textMuted}
          multiline
          style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 8, padding: 8, fontSize: 12, minHeight: 44 }}
          data-testid="coaching-tips-new-content" testID="coaching-tips-new-content" maxLength={140}
        />
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
          <Text style={{ color: C.textMuted, fontSize: 10 }}>{newContent.length}/140</Text>
          <TouchableOpacity
            onPress={handleCreate} disabled={busy === 'create'}
            style={{ backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, opacity: busy === 'create' ? 0.6 : 1 }}
            data-testid="coaching-tips-create-btn" testID="coaching-tips-create-btn"
          >
            <Text style={{ color: C.primaryText, fontSize: 11, fontWeight: '700' }}>{busy === 'create' ? 'Adding…' : 'Add tip'}</Text>
          </TouchableOpacity>
        </View>
        {msg ? <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 6 }}>{msg}</Text> : null}
      </View>

      {loading ? (
        <ActivityIndicator color={C.primary} />
      ) : err ? (
        <Text style={{ color: C.error, fontSize: 11 }}>{err}</Text>
      ) : (
        <ScrollView>
          {items.map((t, i) => (
            <View key={t.tip_id}
              style={{ backgroundColor: C.card, borderColor: t.is_active ? C.primarySoft : C.border, borderWidth: 1, borderRadius: 10, padding: 10, marginBottom: 8, opacity: t.is_active ? 1 : 0.55 }}
              data-testid={`coaching-tips-row-${t.tip_id}`} testID={`coaching-tips-row-${t.tip_id}`}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700' }}>#{t.position + 1} · {t.tip_id}</Text>
                <View style={{ flexDirection: 'row', gap: 4 }}>
                  <TouchableOpacity onPress={() => handleMove(t.tip_id, -1)} disabled={i === 0 || !!busy}
                    style={{ padding: 4, borderRadius: 4, backgroundColor: C.bgSoft, opacity: i === 0 ? 0.3 : 1 }}
                    data-testid={`coaching-tips-move-up-${t.tip_id}`} testID={`coaching-tips-move-up-${t.tip_id}`}>
                    <Ionicons name="arrow-up" size={12} color={C.textSec} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleMove(t.tip_id, 1)} disabled={i === items.length - 1 || !!busy}
                    style={{ padding: 4, borderRadius: 4, backgroundColor: C.bgSoft, opacity: i === items.length - 1 ? 0.3 : 1 }}
                    data-testid={`coaching-tips-move-down-${t.tip_id}`} testID={`coaching-tips-move-down-${t.tip_id}`}>
                    <Ionicons name="arrow-down" size={12} color={C.textSec} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleToggle(t)} disabled={!!busy}
                    style={{ paddingHorizontal: 7, paddingVertical: 3, borderRadius: 999, backgroundColor: t.is_active ? C.successSoft : C.warningSoft, borderColor: t.is_active ? C.success : C.warning, borderWidth: 1 }}
                    data-testid={`coaching-tips-toggle-${t.tip_id}`} testID={`coaching-tips-toggle-${t.tip_id}`}>
                    <Text style={{ color: t.is_active ? C.success : C.warning, fontSize: 9, fontWeight: '800' }}>{t.is_active ? 'ACTIVE' : 'INACTIVE'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => { setEditId(t.tip_id); setEditTitle(t.title); setEditContent(t.content); }}
                    style={{ padding: 4, borderRadius: 4, backgroundColor: C.bgSoft }}
                    data-testid={`coaching-tips-edit-${t.tip_id}`} testID={`coaching-tips-edit-${t.tip_id}`}>
                    <Ionicons name="create" size={12} color={C.primary} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleDelete(t.tip_id)}
                    style={{ padding: 4, borderRadius: 4, backgroundColor: C.errorSoft }}
                    data-testid={`coaching-tips-delete-${t.tip_id}`} testID={`coaching-tips-delete-${t.tip_id}`}>
                    <Ionicons name="trash" size={12} color={C.error} />
                  </TouchableOpacity>
                </View>
              </View>
              {editId === t.tip_id ? (
                <View style={{ marginTop: 6 }}>
                  <TextInput value={editTitle} onChangeText={setEditTitle} maxLength={80} accessibilityLabel={tx('admin.publicCoachingTipsPanel.auto.accessibility.001', 'Text input')}
                    style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 6, padding: 6, fontSize: 12, marginBottom: 6 }}
                    data-testid={`coaching-tips-edit-title-${t.tip_id}`} />
                  <TextInput value={editContent} onChangeText={setEditContent} multiline maxLength={140} accessibilityLabel={tx('admin.publicCoachingTipsPanel.auto.accessibility.002', 'Save')}
                    style={{ backgroundColor: C.bgSoft, color: C.text, borderColor: C.border, borderWidth: 1, borderRadius: 6, padding: 6, fontSize: 12, minHeight: 44 }}
                    data-testid={`coaching-tips-edit-content-${t.tip_id}`} />
                  <View style={{ flexDirection: 'row', gap: 6, marginTop: 6 }}>
                    <TouchableOpacity onPress={() => handleSaveEdit(t.tip_id)} disabled={busy === `edit-${t.tip_id}`}
                      style={{ backgroundColor: C.primary, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, opacity: busy === `edit-${t.tip_id}` ? 0.6 : 1 }}
                      data-testid={`coaching-tips-save-${t.tip_id}`} testID={`coaching-tips-save-${t.tip_id}`}>
                      <Text style={{ color: C.primaryText, fontSize: 10, fontWeight: '700' }}>{tx('admin.publicCoachingTipsPanel.auto.text.004', 'Save')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => setEditId('')}
                      style={{ backgroundColor: C.bgSoft, borderColor: C.border, borderWidth: 1, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6 }}
                      data-testid={`coaching-tips-cancel-${t.tip_id}`}>
                      <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>{tx('admin.publicCoachingTipsPanel.auto.text.005', 'Cancel')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ) : (
                <View style={{ marginTop: 6 }}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700' }}>{t.title}</Text>
                  <Text style={{ color: C.textSec, fontSize: 11, marginTop: 2 }}>{t.content}</Text>
                </View>
              )}
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}
