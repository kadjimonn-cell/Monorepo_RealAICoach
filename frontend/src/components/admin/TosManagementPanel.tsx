import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, TextInput, ActivityIndicator, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useExecTheme} from './ExecDashboardPanels';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

interface TosVersion {
  version_id: string;
  version_number: string;
  title: string;
  content_sections: { heading: string; body: string }[];
  change_summary: string;
  status: 'draft' | 'published' | 'archived';
  created_by: string;
  created_at: string;
  published_at: string | null;
}

interface TosStats {
  active_version: { version_id: string; version_number: string; title: string; published_at: string } | null;
  total_users: number;
  accepted_count: number;
  pending_count: number;
  acceptance_rate: number;
}

/* ── Stat Card ── */
function StatCard({ label, value, color, icon, T }: { label: string; value: string | number; color: string; icon: string; T: any }) {
  return (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }} data-testid={`tos-stat-${label.toLowerCase().replace(/\s/g, '-')}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(color, '18'), alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={16} color={color} />
        </View>
        <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 26, fontWeight: '800' }}>{value}</Text>
    </View>
  );
}

/* ── Section Editor Row ── */
function SectionRow({ section, index, onChange, onRemove, T }: { section: { heading: string; body: string }; index: number; onChange: (i: number, field: string, val: string) => void; onRemove: (i: number) => void; T: any }) {
  return (
    <View style={{ backgroundColor: T.bgSoft, borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: T.border }} data-testid={`tos-section-${index}`}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700' }}>Section {index + 1}</Text>
        <TouchableOpacity onPress={() => onRemove(index)} data-testid={`tos-remove-section-${index}`}>
          <Ionicons name="close-circle" size={18} color={T.error} />
        </TouchableOpacity>
      </View>
      <TextInput
        value={section.heading}
        onChangeText={(v) => onChange(index, 'heading', v)}
        placeholder={tx('admin.tosManagementPanel.auto.placeholder.001', 'Section heading...')}
        placeholderTextColor={T.textMuted}
        style={{ color: T.text, fontSize: 14, fontWeight: '700', borderWidth: 1, borderColor: T.border, borderRadius: 8, padding: 10, marginBottom: 8, backgroundColor: T.card } as any}
        data-testid={`tos-section-heading-${index}`}
      />
      <TextInput
        value={section.body}
        onChangeText={(v) => onChange(index, 'body', v)}
        placeholder={tx('admin.tosManagementPanel.auto.placeholder.002', 'Section content...')}
        placeholderTextColor={T.textMuted}
        multiline
        numberOfLines={4}
        style={{ color: T.text, fontSize: 13, borderWidth: 1, borderColor: T.border, borderRadius: 8, padding: 10, minHeight: 80, backgroundColor: T.card, textAlignVertical: 'top' } as any}
        data-testid={`tos-section-body-${index}`}
      />
    </View>
  );
}

/* ── Version Row ── */
function VersionRow({ v, isActive, onPublish, onEdit, T }: { v: TosVersion; isActive: boolean; onPublish: (id: string) => void; onEdit: (v: TosVersion) => void; T: any }) {
  const statusColor = v.status === 'published' ? T.success : v.status === 'draft' ? T.warning : T.textMuted;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: isActive ? T.primarySoft : T.card, borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: isActive ? (globalThis as any).__alphaColor(T.primary, '40') : T.border, flexWrap: 'wrap', gap: 8 }} data-testid={`tos-version-${v.version_id}`}>
      <View style={{ flex: 1, minWidth: 200 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={{ color: T.text, fontSize: 15, fontWeight: '700' }}>v{v.version_number}</Text>
          <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(statusColor, '18') }}>
            <Text style={{ color: statusColor, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{v.status}</Text>
          </View>
        </View>
        <Text style={{ color: T.textSec, fontSize: 12, marginTop: 2 }}>{v.title}</Text>
        {v.change_summary ? <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{v.change_summary}</Text> : null}
        <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>
          Created {new Date(v.created_at).toLocaleDateString()} by {v.created_by}
          {v.published_at ? ` | Published ${new Date(v.published_at).toLocaleDateString()}` : ''}
        </Text>
      </View>
      <View style={{ flexDirection: 'row', gap: 6 }}>
        {v.status === 'draft' && (
          <>
            <TouchableOpacity onPress={() => onEdit(v)} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: T.primarySoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.primary, '40') }} data-testid={`tos-edit-${v.version_id}`}>
              <Text style={{ color: T.primary, fontSize: 12, fontWeight: '700' }}>{tx('admin.tosManagementPanel.auto.text.001', 'Edit')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => onPublish(v.version_id)} style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(T.success, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '40') }} data-testid={`tos-publish-${v.version_id}`}>
              <Text style={{ color: T.successText, fontSize: 12, fontWeight: '700' }}>{tx('admin.tosManagementPanel.auto.text.002', 'Publish')}</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </View>
  );
}

/* ── Main Panel ── */
export default function TosManagementPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const T = useExecTheme();
  const { width } = useWindowDimensions();
  const m = width < 768;

  const [versions, setVersions] = useState<TosVersion[]>([]);
  const [stats, setStats] = useState<TosStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'overview' | 'create' | 'edit'>('overview');

  // Form state
  const [formTitle, setFormTitle] = useState('Terms of Service');
  const [formVersion, setFormVersion] = useState('');
  const [formSummary, setFormSummary] = useState('');
  const [formSections, setFormSections] = useState<{ heading: string; body: string }[]>([
    { heading: '1. Acceptance of Terms', body: '' },
  ]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [_publishing, setPublishing] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [vRes, sRes] = await Promise.all([
        api.get('/admin/tos/versions'),
        api.get('/admin/tos/stats'),
      ]);
      setVersions(vRes.data?.versions || []);
      setStats(sRes.data || null);
    } catch (e) {
      console.error('TOS fetch error:', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSectionChange = (idx: number, field: string, val: string) => {
    setFormSections(prev => prev.map((s, i) => i === idx ? { ...s, [field]: val } : s));
  };

  const handleRemoveSection = (idx: number) => {
    setFormSections(prev => prev.filter((_, i) => i !== idx));
  };

  const handleAddSection = () => {
    setFormSections(prev => [...prev, { heading: `${prev.length + 1}. New Section`, body: '' }]);
  };

  const resetForm = () => {
    setFormTitle('Terms of Service');
    setFormVersion('');
    setFormSummary('');
    setFormSections([{ heading: '1. Acceptance of Terms', body: '' }]);
    setEditingId(null);
  };

  const handleSave = async () => {
    if (!formVersion.trim()) return alert(tx('admin.tosManagementPanel.auto.alert.versionRequired', 'Version number is required'));
    if (formSections.length === 0) return alert(tx('admin.tosManagementPanel.auto.alert.sectionsRequired', 'At least one section is required'));

    setSaving(true);
    try {
      const payload = {
        title: formTitle,
        version_number: formVersion,
        change_summary: formSummary,
        content_sections: formSections,
      };

      if (editingId) {
        await api.put(`/admin/tos/versions/${editingId}`, payload);
      } else {
        await api.post('/admin/tos/versions', payload);
      }
      resetForm();
      setTab('overview');
      await fetchData();
    } catch (e: any) {
      alert(e?.response?.data?.detail || e?.data?.detail || 'Failed to save');
    }
    setSaving(false);
  };

  const handlePublish = async (versionId: string) => {
    if (!confirm(tx('admin.tosManagementPanel.auto.alert.publishConfirm', 'Publishing will require ALL users to re-accept the Terms of Service. Continue?'))) return;
    setPublishing(versionId);
    try {
      await api.put(`/admin/tos/versions/${versionId}/publish`);
      await fetchData();
    } catch (e: any) {
      alert(e?.response?.data?.detail || e?.data?.detail || 'Failed to publish');
    }
    setPublishing(null);
  };

  const handleEdit = (v: TosVersion) => {
    setEditingId(v.version_id);
    setFormTitle(v.title);
    setFormVersion(v.version_number);
    setFormSummary(v.change_summary);
    setFormSections(v.content_sections || []);
    setTab('edit');
  };

  if (loading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }} data-testid="tos-loading">
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: T.textSec, fontSize: 13, marginTop: 12 }}>{tx('admin.tosManagementPanel.auto.text.003', 'Loading TOS management...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: m ? 16 : 24 }} data-testid="tos-management-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: T.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="document-text" size={20} color={T.primary} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 20, fontWeight: '800' }} data-testid="tos-panel-title">{tx('admin.tosManagementPanel.auto.text.004', 'Terms of Service')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.tosManagementPanel.auto.text.005', 'Version management & user acceptance tracking')}</Text>
          </View>
        </View>
        {tab === 'overview' && (
          <TouchableOpacity
            onPress={() => { resetForm(); setTab('create'); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: T.primary }}
            data-testid="tos-create-version-btn"
          >
            <Ionicons name="add" size={16} color="var(--app-primary-text)" />
            <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('admin.tosManagementPanel.auto.text.006', 'New Version')}</Text>
          </TouchableOpacity>
        )}
        {(tab === 'create' || tab === 'edit') && (
          <TouchableOpacity
            onPress={() => { resetForm(); setTab('overview'); }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: T.bgSoft, borderWidth: 1, borderColor: T.border }}
            data-testid="tos-back-btn"
          >
            <Ionicons name="arrow-back" size={16} color={T.textSec} />
            <Text style={{ color: T.textSec, fontSize: 13, fontWeight: '700' }}>{tx('admin.tosManagementPanel.auto.text.007', 'Back')}</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Stats Row */}
      {tab === 'overview' && stats && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 24 }} data-testid="tos-stats-row">
          <StatCard label="Active Version" value={stats.active_version ? `v${stats.active_version.version_number}` : 'None'} color={T.primary} icon="document-text" T={T} />
          <StatCard label="Total Users" value={stats.total_users} color={T.purpleText} icon="people" T={T} />
          <StatCard label="Accepted" value={stats.accepted_count} color={T.successText} icon="checkmark-circle" T={T} />
          <StatCard label="Pending" value={stats.pending_count} color={T.warningText} icon="time" T={T} />
          <StatCard label="Acceptance Rate" value={`${stats.acceptance_rate}%`} color={T.cyan} icon="analytics" T={T} />
        </View>
      )}

      {/* Quick broadcast hand-off — publishing a new version doesn't
          automatically email users; this card keeps the Publish +
          Broadcast flow visible in one place so admins don't forget the
          "notify every user" half of the job. */}
      {tab === 'overview' && (
        <View
          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, backgroundColor: T.card, borderColor: T.primarySoft, borderWidth: 1, borderRadius: 14, padding: 14, marginBottom: 20 }}
          data-testid="tos-broadcast-handoff-card"
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: T.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="megaphone" size={18} color={T.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>{tx('admin.tosManagementPanel.auto.text.008', 'Email users about this update')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.tosManagementPanel.auto.text.009', 'Publishing a new version only flips the re-acceptance flag. Open the Legal Notice Broadcast panel to actually email every user about the change.')}</Text>
            </View>
          </View>
          <TouchableOpacity accessibilityLabel={tx('admin.tosManagementPanel.auto.accessibility.001', 'Open policy broadcast panel')}
            onPress={() => {
              if (typeof window !== 'undefined') {
                try {
                  const url = new URL(window.location.href);
                  url.searchParams.set('tab', 'legal-notice-broadcast');
                  window.location.assign(url.toString());
                } catch { /* noop */ }
              }
            }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, backgroundColor: T.primary }}
            data-testid="tos-open-broadcast-panel-btn"
          >
            <Ionicons name="send" size={14} color={T.primaryText} />
            <Text style={{ color: T.primaryText, fontSize: 12, fontWeight: '700' }}>{tx('admin.tosManagementPanel.auto.text.010', 'Open Broadcast Panel')}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Overview Tab — List versions */}
      {tab === 'overview' && (
        <View data-testid="tos-versions-list">
          <Text style={{ color: T.textSec, fontSize: 13, fontWeight: '700', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.tosManagementPanel.auto.text.011', 'All Versions')}</Text>
          {versions.length === 0 ? (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 32, alignItems: 'center', borderWidth: 1, borderColor: T.border }} data-testid="tos-empty-state">
              <Ionicons name="document-text-outline" size={40} color={T.textMuted} />
              <Text style={{ color: T.textSec, fontSize: 15, fontWeight: '700', marginTop: 12 }}>{tx('admin.tosManagementPanel.auto.text.012', 'No TOS versions yet')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{tx('admin.tosManagementPanel.auto.text.013', 'Create your first Terms of Service version to get started.')}</Text>
            </View>
          ) : (
            versions.map(v => (
              <VersionRow
                key={v.version_id}
                v={v}
                isActive={v.status === 'published'}
                onPublish={handlePublish}
                onEdit={handleEdit}
                T={T}
              />
            ))
          )}
        </View>
      )}

      {/* Create / Edit Tab */}
      {(tab === 'create' || tab === 'edit') && (
        <View style={{ backgroundColor: T.card, borderRadius: 16, padding: m ? 16 : 24, borderWidth: 1, borderColor: T.border }} data-testid="tos-editor">
          <Text style={{ color: T.text, fontSize: 17, fontWeight: '800', marginBottom: 16 }}>
            {tab === 'edit' ? 'Edit Draft' : 'Create New Version'}
          </Text>

          {/* Version Number */}
          <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 6 }}>{tx('admin.tosManagementPanel.auto.text.014', 'Version Number *')}</Text>
          <TextInput
            value={formVersion}
            onChangeText={setFormVersion}
            placeholder={tx('admin.tosManagementPanel.auto.placeholder.003', 'e.g. 2.0')}
            placeholderTextColor={T.textMuted}
            style={{ color: T.text, fontSize: 14, borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 12, marginBottom: 16, backgroundColor: T.bgSoft } as any}
            data-testid="tos-form-version"
          />

          {/* Title */}
          <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 6 }}>{tx('admin.tosManagementPanel.auto.text.015', 'Title')}</Text>
          <TextInput
            value={formTitle}
            onChangeText={setFormTitle}
            placeholder={tx('admin.tosManagementPanel.auto.placeholder.004', 'Terms of Service')}
            placeholderTextColor={T.textMuted}
            style={{ color: T.text, fontSize: 14, borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 12, marginBottom: 16, backgroundColor: T.bgSoft } as any}
            data-testid="tos-form-title"
          />

          {/* Change Summary */}
          <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 6 }}>{tx('admin.tosManagementPanel.auto.text.016', 'Change Summary (shown to users during re-acceptance)')}</Text>
          <TextInput
            value={formSummary}
            onChangeText={setFormSummary}
            placeholder={tx('admin.tosManagementPanel.auto.placeholder.005', 'Briefly describe what changed in this version...')}
            placeholderTextColor={T.textMuted}
            multiline
            numberOfLines={3}
            style={{ color: T.text, fontSize: 13, borderWidth: 1, borderColor: T.border, borderRadius: 10, padding: 12, marginBottom: 16, minHeight: 60, backgroundColor: T.bgSoft, textAlignVertical: 'top' } as any}
            data-testid="tos-form-summary"
          />

          {/* Content Sections */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '700' }}>Content Sections ({formSections.length})</Text>
            <TouchableOpacity onPress={handleAddSection} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: T.primarySoft }} data-testid="tos-add-section-btn">
              <Ionicons name="add" size={14} color={T.primary} />
              <Text style={{ color: T.primary, fontSize: 11, fontWeight: '700' }}>{tx('admin.tosManagementPanel.auto.text.017', 'Add Section')}</Text>
            </TouchableOpacity>
          </View>

          {formSections.map((s, i) => (
            <SectionRow key={i} section={s} index={i} onChange={handleSectionChange} onRemove={handleRemoveSection} T={T} />
          ))}

          {/* Save Button */}
          <TouchableOpacity
            onPress={handleSave}
            disabled={saving}
            style={{ marginTop: 16, paddingVertical: 14, borderRadius: 12, backgroundColor: saving ? T.textMuted : T.primary, alignItems: 'center' }}
            data-testid="tos-save-btn"
          >
            {saving ? (
              <ActivityIndicator size="small" color="var(--app-primary-text)" />
            ) : (
              <Text style={{ color: colors.primaryText, fontSize: 14, fontWeight: '800' }}>{tab === 'edit' ? 'Update Draft' : 'Save Draft'}</Text>
            )}
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
}
