import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, Platform, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Props { colors: any; }

const tx = (_key: string, fallback: string) => fallback;

export default function ChangelogAdminPanel({ colors: _colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const CATEGORIES = [
    { id: 'feature', label: 'Feature', color: colors.primary, icon: 'rocket' },
    { id: 'improvement', label: 'Improvement', color: colors.accent, icon: 'trending-up' },
    { id: 'fix', label: 'Bug Fix', color: colors.successText, icon: 'build' },
    { id: 'security', label: 'Security', color: colors.error, icon: 'shield-checkmark' },
  ];
  const C = colors;
  const [page, setPage] = useState(1);
  const { data: entriesData, loading: eLoading, refetch: fetchData } = useLiveQuery(`/changelog/entries?page=${page}&limit=15`, { pollInterval: 30000, entity: 'changelog' });
  const { data: stats, loading: sLoading } = useLiveQuery('/changelog/stats', { pollInterval: 30000, entity: 'changelog' });
  const entries = entriesData?.entries || [];
  const totalPages = entriesData?.pages || 1;
  const loading = eLoading || sLoading;
  const [generating, setGenerating] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', category: 'feature', version: '', highlights: '' });
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await api.post('/changelog/auto-generate');
      alert(`AI generated ${res.data.generated} changelog entries (as drafts).`);
      fetchData();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'AI generation failed');
    } finally { setGenerating(false); }
  };

  const handleBulkPublish = async () => {
    setPublishing(true);
    try {
      const res = await api.post('/changelog/bulk-publish');
      alert(`Published ${res.data.published_count} draft entries.`);
      fetchData();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ChangelogAdminPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setPublishing(false); }
  };

  const handleSave = async () => {
    if (!form.title.trim() || !form.description.trim()) return;
    setSaving(true);
    try {
      const payload = {
        title: form.title,
        description: form.description,
        category: form.category,
        version: form.version || undefined,
        highlights: form.highlights.split('\n').filter(h => h.trim()),
      };
      if (editingId) {
        await api.put(`/changelog/entries/${editingId}`, payload);
      } else {
        await api.post('/changelog/entries', payload);
      }
      setShowForm(false);
      setEditingId(null);
      setForm({ title: '', description: '', category: 'feature', version: '', highlights: '' });
      fetchData();
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const handleEdit = (entry: any) => {
    setForm({
      title: entry.title,
      description: entry.description,
      category: entry.category,
      version: entry.version || '',
      highlights: (entry.highlights || []).join('\n'),
    });
    setEditingId(entry.entry_id);
    setShowForm(true);
  };

  const handleDelete = async (entryId: string) => {
    if (!confirm(tx('admin.changelogAdminPanel.auto.confirm.deleteEntry', 'Delete this changelog entry?'))) return;
    try {
      await api.delete(`/changelog/entries/${entryId}`);
      fetchData();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ChangelogAdminPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const handleTogglePublish = async (entry: any) => {
    try {
      await api.put(`/changelog/entries/${entry.entry_id}`, { is_published: !entry.is_published });
      fetchData();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ChangelogAdminPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const catForEntry = (cat: string) => CATEGORIES.find(c => c.id === cat) || CATEGORIES[0];

  return (
    <View data-testid="changelog-admin-panel" testID="changelog-admin-panel">
      <AutoFixBanner domain="changelog" />
      {/* Stats Cards */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Entries', value: stats?.total ?? '...', color: colors.primary, icon: 'document-text' },
          { label: 'Published', value: stats?.published ?? '...', color: colors.successText, icon: 'checkmark-circle' },
          { label: 'Drafts', value: stats?.drafts ?? '...', color: colors.warningText, icon: 'create' },
          { label: 'AI Generated', value: stats?.ai_generated ?? '...', color: colors.accent, icon: 'sparkles' },
          { label: 'Seen by Users', value: stats?.seen_by_users ?? '...', color: colors.accent, icon: 'eye' },
        ].map((m, i) => (
          <View key={i} style={{
            flex: 1, minWidth: 130, backgroundColor: C.card, borderRadius: 12,
            padding: 14, borderWidth: 1, borderColor: C.border,
          }} data-testid={`changelog-stat-${i}`} testID={`changelog-stat-${i}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <Ionicons name={m.icon as any} size={14} color={m.color} />
              <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '600' }}>{m.label}</Text>
            </View>
            <Text style={{ fontSize: 22, fontWeight: '900', color: C.text }}>{m.value}</Text>
          </View>
        ))}
      </View>

      {/* Category Breakdown */}
      {stats?.category_breakdown && (
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16 }}>
          {CATEGORIES.map(cat => (
            <View key={cat.id} style={{
              flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6,
              backgroundColor: (globalThis as any).__alphaColor(cat.color, '10'), paddingHorizontal: 10, paddingVertical: 8, borderRadius: 8,
              borderWidth: 1, borderColor: (globalThis as any).__alphaColor(cat.color, '20'),
            }}>
              <Ionicons name={cat.icon as any} size={12} color={cat.color} />
              <Text style={{ fontSize: 11, color: cat.color, fontWeight: '700' }}>{cat.label}</Text>
              <Text style={{ fontSize: 13, color: C.text, fontWeight: '900', marginLeft: 'auto' }}>{stats.category_breakdown[cat.id] || 0}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Action Bar */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <TouchableOpacity onPress={() => { setShowForm(true); setEditingId(null); setForm({ title: '', description: '', category: 'feature', version: '', highlights: '' }); }}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10 }}
          data-testid="changelog-create-btn" testID="changelog-create-btn">
          <Ionicons name="add-circle" size={16} color="var(--app-primary-text)" />
          <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.changelogAdminPanel.auto.text.001', 'New Entry')}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={handleGenerate} disabled={generating}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.accentSoft, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.accentSoft, opacity: generating ? 0.6 : 1 }}
          data-testid="changelog-ai-generate-btn" testID="changelog-ai-generate-btn">
          {generating ? <ActivityIndicator size="small" color={'var(--app-primary)'} /> : <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />}
          <Text style={{ color: colors.accent, fontSize: 12, fontWeight: '700' }}>{generating ? 'Generating...' : 'AI Auto-Generate'}</Text>
        </TouchableOpacity>
        {(stats?.drafts || 0) > 0 && (
          <TouchableOpacity onPress={handleBulkPublish} disabled={publishing}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.successSoft, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.successSoft }}
            data-testid="changelog-bulk-publish-btn" testID="changelog-bulk-publish-btn">
            {publishing ? <ActivityIndicator size="small" color={'var(--app-success)'} /> : <Ionicons name="cloud-upload" size={16} color={'var(--app-success)'} />}
            <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '700' }}>Publish All Drafts ({stats?.drafts})</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity onPress={fetchData}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: C.border }}
          data-testid="changelog-refresh-btn" testID="changelog-refresh-btn">
          <Ionicons name="refresh" size={16} color={C.textMuted} />
        </TouchableOpacity>
      </View>

      {/* Create/Edit Form */}
      {showForm && (
        <View style={{
          backgroundColor: C.card, borderRadius: 14, padding: 18, marginBottom: 16,
          borderWidth: 1, borderColor: colors.primarySoft,
        }} data-testid="changelog-entry-form" testID="changelog-entry-form">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{editingId ? 'Edit Entry' : 'New Entry'}</Text>
            <TouchableOpacity accessibilityLabel={tx('admin.changelogAdminPanel.auto.accessibility.001', 'close button')} onPress={() => { setShowForm(false); setEditingId(null); }}>
              <Ionicons name="close" size={18} color={C.textMuted} />
            </TouchableOpacity>
          </View>
          <TextInput value={form.title} onChangeText={v => setForm(f => ({ ...f, title: v }))}
            placeholder={tx('admin.changelogAdminPanel.auto.placeholder.001', 'Entry title...')} placeholderTextColor={C.textMuted}
            style={{ color: C.text, fontSize: 14, fontWeight: '600', borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 10, marginBottom: 10, ...(Platform.OS === 'web' ? { outline: 'none', boxShadow: '0 0 0 2px transparent' } : {}) } as any}
            data-testid="changelog-form-title" testID="changelog-form-title" />
          <TextInput value={form.description} onChangeText={v => setForm(f => ({ ...f, description: v }))}
            placeholder={tx('admin.changelogAdminPanel.auto.placeholder.002', 'Description...')} placeholderTextColor={C.textMuted} multiline numberOfLines={3}
            style={{ color: C.text, fontSize: 12, borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 10, marginBottom: 10, minHeight: 60, textAlignVertical: 'top', ...(Platform.OS === 'web' ? { outline: 'none', boxShadow: '0 0 0 2px transparent' } : {}) } as any}
            data-testid="changelog-form-description" testID="changelog-form-description" />
          <View style={{ flexDirection: 'row', gap: 6, marginBottom: 10 }}>
            {CATEGORIES.map(cat => (
              <TouchableOpacity key={cat.id} accessibilityLabel={tx('admin.changelogAdminPanel.auto.accessibility.002', 'Select changelog category')} onPress={() => setForm(f => ({ ...f, category: cat.id }))}
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 4,
                  paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
                  backgroundColor: form.category === cat.id ? (globalThis as any).__alphaColor(cat.color, '20') : 'transparent',
                  borderWidth: 1, borderColor: form.category === cat.id ? (globalThis as any).__alphaColor(cat.color, '40') : C.border,
                }}
                data-testid={`changelog-form-cat-${cat.id}`} testID={`changelog-form-cat-${cat.id}`}>
                <Ionicons name={cat.icon as any} size={11} color={form.category === cat.id ? cat.color : C.textMuted} />
                <Text style={{ fontSize: 10, fontWeight: '700', color: form.category === cat.id ? cat.color : C.textMuted }}>{cat.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <TextInput value={form.version} onChangeText={v => setForm(f => ({ ...f, version: v }))}
            placeholder={tx('admin.changelogAdminPanel.auto.placeholder.003', 'Version (e.g. v2025.03.11)')} placeholderTextColor={C.textMuted}
            style={{ color: C.text, fontSize: 12, borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 10, marginBottom: 10, ...(Platform.OS === 'web' ? { outline: 'none', boxShadow: '0 0 0 2px transparent' } : {}) } as any}
            data-testid="changelog-form-version" testID="changelog-form-version" />
          <TextInput value={form.highlights} onChangeText={v => setForm(f => ({ ...f, highlights: v }))}
            placeholder={tx('admin.changelogAdminPanel.auto.placeholder.004', 'Highlights (one per line)...')} placeholderTextColor={C.textMuted} multiline numberOfLines={3}
            style={{ color: C.text, fontSize: 12, borderWidth: 1, borderColor: C.border, borderRadius: 8, padding: 10, marginBottom: 14, minHeight: 60, textAlignVertical: 'top', ...(Platform.OS === 'web' ? { outline: 'none', boxShadow: '0 0 0 2px transparent' } : {}) } as any}
            data-testid="changelog-form-highlights" testID="changelog-form-highlights" />
          <View style={{ flexDirection: 'row', gap: 8, justifyContent: 'flex-end' }}>
            <TouchableOpacity accessibilityLabel={tx('admin.changelogAdminPanel.auto.accessibility.003', 'Cancel')} onPress={() => { setShowForm(false); setEditingId(null); }}
              style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ color: C.textMuted, fontSize: 12, fontWeight: '600' }}>{tx('admin.changelogAdminPanel.auto.text.002', 'Cancel')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleSave} disabled={saving}
              style={{ backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 8, borderRadius: 8, opacity: saving ? 0.6 : 1 }}
              data-testid="changelog-form-save" testID="changelog-form-save">
              <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }}>{saving ? 'Saving...' : editingId ? 'Update' : 'Create'}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Entries List */}
      {loading ? (
        <View style={{ padding: 40, alignItems: 'center' }}>
          <ActivityIndicator size="large" color={'var(--app-primary)'} />
        </View>
      ) : entries.length === 0 ? (
        <View style={{ padding: 40, alignItems: 'center', backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border }}>
          <Ionicons name="document-text-outline" size={40} color={C.textMuted} />
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '600', marginTop: 12 }}>{tx('admin.changelogAdminPanel.auto.text.003', 'No changelog entries yet')}</Text>
          <Text style={{ color: C.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.changelogAdminPanel.auto.text.004', 'Create one manually or use AI auto-generation')}</Text>
        </View>
      ) : (
        <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }}>
          {entries.map((entry, i) => {
            const cat = catForEntry(entry.category);
            return (
              <View key={entry.entry_id} style={{
                flexDirection: 'row', alignItems: 'center', gap: 12,
                paddingHorizontal: 14, paddingVertical: 12,
                borderBottomWidth: i < entries.length - 1 ? 1 : 0, borderBottomColor: C.border,
                backgroundColor: !entry.is_published ? 'var(--app-warning-soft)' : 'transparent',
              }} data-testid={`changelog-admin-entry-${entry.entry_id}`} testID={`changelog-admin-entry-${entry.entry_id}`}>
                <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(cat.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={cat.icon as any} size={14} color={cat.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, flex: 1 }} numberOfLines={1}>{entry.title}</Text>
                    {!entry.is_published && (
                      <View style={{ backgroundColor: colors.warningSoft, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                        <Text style={{ fontSize: 8, fontWeight: '800', color: colors.warningText }}>{tx('admin.changelogAdminPanel.auto.text.005', 'DRAFT')}</Text>
                      </View>
                    )}
                    {entry.ai_generated && (
                      <View style={{ backgroundColor: colors.accentSoft, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                        <Text style={{ fontSize: 8, fontWeight: '800', color: colors.accent }}>{tx('admin.changelogAdminPanel.auto.text.006', 'AI')}</Text>
                      </View>
                    )}
                  </View>
                  <Text style={{ fontSize: 10, color: C.textMuted, marginTop: 2 }} numberOfLines={1}>{entry.description}</Text>
                </View>
                <Text style={{ fontSize: 9, color: C.textMuted, width: 65 }}>{entry.version || '-'}</Text>
                <View style={{ flexDirection: 'row', gap: 4 }}>
                  <TouchableOpacity onPress={() => handleTogglePublish(entry)} style={{ padding: 4 }} data-testid={`changelog-toggle-${entry.entry_id}`} testID={`changelog-toggle-${entry.entry_id}`}>
                    <Ionicons name={entry.is_published ? 'eye' : 'eye-off'} size={14} color={entry.is_published ? 'var(--app-success)' : 'var(--app-warning)'} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleEdit(entry)} style={{ padding: 4 }} data-testid={`changelog-edit-${entry.entry_id}`} testID={`changelog-edit-${entry.entry_id}`}>
                    <Ionicons name="create-outline" size={14} color={'var(--app-primary)'} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleDelete(entry.entry_id)} style={{ padding: 4 }} data-testid={`changelog-delete-${entry.entry_id}`} testID={`changelog-delete-${entry.entry_id}`}>
                    <Ionicons name="trash-outline" size={14} color={'var(--app-error)'} />
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
          {/* Pagination */}
          {totalPages > 1 && (
            <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8, padding: 12, borderTopWidth: 1, borderTopColor: C.border }}>
              <TouchableOpacity accessibilityLabel={tx('admin.changelogAdminPanel.auto.accessibility.004', 'chevron back button')} onPress={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                style={{ padding: 6, opacity: page === 1 ? 0.3 : 1 }}>
                <Ionicons name="chevron-back" size={16} color={C.textMuted} />
              </TouchableOpacity>
              <Text style={{ fontSize: 11, color: C.textMuted }}>Page {page} of {totalPages}</Text>
              <TouchableOpacity accessibilityLabel={tx('admin.changelogAdminPanel.auto.accessibility.005', 'chevron forward button')} onPress={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                style={{ padding: 6, opacity: page === totalPages ? 0.3 : 1 }}>
                <Ionicons name="chevron-forward" size={16} color={C.textMuted} />
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}
    </View>
  );
}
