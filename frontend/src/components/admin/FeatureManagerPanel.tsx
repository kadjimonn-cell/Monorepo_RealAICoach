import React, { useState, useCallback, useMemo } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

interface Feature {
  feature_id: string;
  title: string;
  description: string;
  icon: string;
  route: string;
  category: string;
  color: string;
  is_new: boolean;
  premium: boolean;
  enabled: boolean;
  sort_order: number;
  soft_deactivated?: boolean;
  soft_deactivated_at?: string;
  soft_deactivation_reason?: string;
  usage_30d?: number;
  usage_90d?: number;
  phase1_candidate?: boolean;
  phase1_candidate_priority?: 'high' | 'medium' | 'healthy';
  phase2_candidate?: boolean;
  phase2_candidate_priority?: 'ready' | 'review' | 'already_retired';
  phase2_candidate_reason?: string | null;
  phase2_blockers?: string[];
  phase2_deactivated?: boolean;
  phase2_deactivated_at?: string;
  soft_hidden_days?: number;
}

interface RetirementPhase1Payload {
  summary: {
    total_enabled_features: number;
    soft_hidden_features: number;
    phase1_candidates: number;
    high_priority_candidates: number;
  };
  candidates: Feature[];
  features: Feature[];
}

interface RetirementPhase2Payload {
  summary: {
    total_features: number;
    phase2_candidates: number;
    phase2_retired: number;
    blocked_candidates: number;
  };
  candidates: Feature[];
  features: Feature[];
}

const tx = (_key: string, fallback: string) => fallback;

const CATEGORY_OPTIONS = [
  { id: 'all', label: 'All' },
  { id: 'productivity', label: 'Productivity' },
  { id: 'business', label: 'Business' },
  { id: 'finance', label: 'Finance' },
  { id: 'health', label: 'Health' },
  { id: 'lifestyle', label: 'Lifestyle' },
  { id: 'entertainment', label: 'Entertainment' },
  { id: 'tech', label: 'Tech & Media' },
  { id: 'education', label: 'Education' },
];

const COLOR_PRESETS = ['var(--app-primary)', 'var(--app-success)', 'var(--app-warning)', 'var(--app-error)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-error)', 'var(--app-warning)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)'];

export default function FeatureManagerPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const EMPTY_FORM = {
    feature_id: '', title: '', description: '', icon: 'apps', route: '',
    category: 'productivity', color: colors.primary, is_new: false, premium: false, enabled: true,
  };
  const { width } = useWindowDimensions();
  const isMobile = width < 768;

  const { data, loading, refetch } = useLiveQuery<{ features: Feature[]; categories: any[]; total: number }>(
    '/features/registry/all', { entity: 'features', pollInterval: 30000 }
  );
  const {
    data: phase1Retirement,
    refetch: refetchPhase1Retirement,
  } = useLiveQuery<RetirementPhase1Payload>(
    '/admin/features/retirement-phase1/candidates',
    { entity: 'features', pollInterval: 45000 },
  );
  const {
    data: phase2Retirement,
    refetch: refetchPhase2Retirement,
  } = useLiveQuery<RetirementPhase2Payload>(
    '/admin/features/retirement-phase2/candidates',
    { entity: 'features', pollInterval: 45000 },
  );

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const features = data?.features || [];

  const [search, setSearch] = useState('');
  const [filterCat, setFilterCat] = useState('all');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const filtered = useMemo(() => {
    let list = features;
    if (filterCat !== 'all') list = list.filter(f => f.category === filterCat);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(f => f.title.toLowerCase().includes(q) || f.feature_id.toLowerCase().includes(q) || f.description.toLowerCase().includes(q));
    }
    return list;
  }, [features, filterCat, search]);

  const phase1FeatureMap = useMemo(() => {
    const map = new Map<string, Feature>();
    (phase1Retirement?.features || []).forEach((row) => {
      if (row?.feature_id) map.set(row.feature_id, row);
    });
    return map;
  }, [phase1Retirement?.features]);

  const topPhase1Candidates = useMemo(() => (phase1Retirement?.candidates || []).slice(0, 6), [phase1Retirement?.candidates]);

  const phase2FeatureMap = useMemo(() => {
    const map = new Map<string, Feature>();
    (phase2Retirement?.features || []).forEach((row) => {
      if (row?.feature_id) map.set(row.feature_id, row);
    });
    return map;
  }, [phase2Retirement?.features]);

  const topPhase2Candidates = useMemo(() => (phase2Retirement?.candidates || []).slice(0, 6), [phase2Retirement?.candidates]);

  const refetchAll = useCallback(() => {
    refetch();
    refetchPhase1Retirement();
    refetchPhase2Retirement();
  }, [refetch, refetchPhase1Retirement, refetchPhase2Retirement]);

  const stats = useMemo(() => ({
    total: features.length,
    enabled: features.filter(f => f.enabled).length,
    disabled: features.filter(f => !f.enabled).length,
    premium: features.filter(f => f.premium).length,
    isNew: features.filter(f => f.is_new).length,
    softHidden: phase1Retirement?.summary?.soft_hidden_features || 0,
    phase1Candidates: phase1Retirement?.summary?.phase1_candidates || 0,
    phase2Candidates: phase2Retirement?.summary?.phase2_candidates || 0,
    phase2Retired: phase2Retirement?.summary?.phase2_retired || 0,
  }), [
    features,
    phase1Retirement?.summary?.phase1_candidates,
    phase1Retirement?.summary?.soft_hidden_features,
    phase2Retirement?.summary?.phase2_candidates,
    phase2Retirement?.summary?.phase2_retired,
  ]);

  const openCreate = useCallback(() => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openEdit = useCallback((f: Feature) => {
    setEditingId(f.feature_id);
    setForm({
      feature_id: f.feature_id, title: f.title, description: f.description,
      icon: f.icon, route: f.route, category: f.category, color: f.color,
      is_new: f.is_new, premium: f.premium, enabled: f.enabled,
    });
    setShowForm(true);
  }, []);

  const handleSave = useCallback(async () => {
    if (!form.feature_id.trim() || !form.title.trim()) return;
    setSaving(true);
    try {
      if (editingId) {
        await api.put(`/admin/features/registry/${editingId}`, form);
      } else {
        await api.post('/admin/features/registry', form);
      }
      setShowForm(false);
      setEditingId(null);
      setForm(EMPTY_FORM);
      refetchAll();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to save';
      if (Platform.OS === 'web') alert(msg);
    }
    setSaving(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, editingId, refetchAll]);

  const handleDelete = useCallback(async (featureId: string) => {
    setDeleting(true);
    try {
      await api.delete(`/admin/features/registry/${featureId}`);
      setDeleteConfirm(null);
      refetchAll();
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (e: any) {
      if (Platform.OS === 'web') alert(tx('admin.featureManagerPanel.auto.alert.deleteFailed', 'Failed to delete'));
    }
    setDeleting(false);
  }, [refetchAll, tx]);

  const toggleField = useCallback(async (featureId: string, field: 'enabled' | 'premium' | 'is_new', current: boolean) => {
    try {
      await api.put(`/admin/features/registry/${featureId}`, { [field]: !current });
      refetchAll();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/FeatureManagerPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [refetchAll]);

  const phase1SoftHide = useCallback(async (featureId: string) => {
    try {
      await api.post(`/admin/features/registry/${featureId}/phase1-soft-hide`, {
        reason: 'Phase 1 safe retirement (UI hidden) based on live low usage window.',
      });
      refetchAll();
    } catch (e: any) {
      if (Platform.OS === 'web') alert(e?.response?.data?.detail || tx('admin.featureManagerPanel.auto.alert.softHideFailed', 'Failed to soft-hide feature'));
    }
  }, [refetchAll, tx]);

  const phase1Restore = useCallback(async (featureId: string) => {
    try {
      await api.post(`/admin/features/registry/${featureId}/phase1-restore`, {
        reason: 'Phase 1 rollback restore requested by admin.',
      });
      refetchAll();
    } catch (e: any) {
      if (Platform.OS === 'web') alert(e?.response?.data?.detail || tx('admin.featureManagerPanel.auto.alert.restoreFailed', 'Failed to restore feature'));
    }
  }, [refetchAll, tx]);

  const phase2Deactivate = useCallback(async (featureId: string) => {
    try {
      await api.post(`/admin/features/registry/${featureId}/phase2-deactivate`, {
        reason: 'Phase 2 retirement (registry deactivated) after low-usage validation.',
      });
      refetchAll();
    } catch (e: any) {
      if (Platform.OS === 'web') {
        alert(e?.response?.data?.detail || tx('admin.featureManagerPanel.auto.alert.phase2DeactivateFailed', 'Failed to deactivate feature in Phase 2'));
      }
    }
  }, [refetchAll, tx]);

  const phase2Restore = useCallback(async (featureId: string) => {
    try {
      await api.post(`/admin/features/registry/${featureId}/phase2-restore`, {
        reason: 'Phase 2 restore requested by admin.',
      });
      refetchAll();
    } catch (e: any) {
      if (Platform.OS === 'web') {
        alert(e?.response?.data?.detail || tx('admin.featureManagerPanel.auto.alert.phase2RestoreFailed', 'Failed to restore feature from Phase 2'));
      }
    }
  }, [refetchAll, tx]);

  if (loading) {
    return (
      <View style={{ padding: 40, alignItems: 'center' }} data-testid="feature-manager-loading" testID="feature-manager-loading">
      <AutoFixBanner domain="feature_manager" />
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
        <Text style={{ color: colors.textMuted, marginTop: 12, fontSize: 13 }}>{tx('admin.featureManagerPanel.auto.text.001', 'Loading features...')}</Text>
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }} data-testid="feature-manager-panel" testID="feature-manager-panel">
      {/* Header */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', justifyContent: 'space-between', marginBottom: 20, gap: 12 }}>
        <View>
          <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text, letterSpacing: -0.3 }} data-testid="feature-manager-title" testID="feature-manager-title">{tx('admin.featureManagerPanel.auto.text.002', 'Feature Registry')}</Text>
          <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>{tx('admin.featureManagerPanel.auto.text.003', 'Manage platform features, categories, and visibility')}</Text>
        </View>
        <TouchableOpacity onPress={openCreate}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 }}
          data-testid="feature-create-btn" testID="feature-create-btn">
          <Ionicons name="add-circle" size={16} color={colors.primaryText} />
          <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{tx('admin.featureManagerPanel.auto.text.004', 'Add Feature')}</Text>
        </TouchableOpacity>
      </View>

      {/* Stats */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 18 }}>
        <StatCard label="Total" value={stats.total} icon="apps" color={'var(--app-primary)'} colors={colors} testId="stat-total" />
        <StatCard label="Enabled" value={stats.enabled} icon="checkmark-circle" color={'var(--app-success)'} colors={colors} testId="stat-enabled" />
        <StatCard label="Disabled" value={stats.disabled} icon="close-circle" color={'var(--app-error)'} colors={colors} testId="stat-disabled" />
        <StatCard label="Premium" value={stats.premium} icon="diamond" color={'var(--app-primary)'} colors={colors} testId="stat-premium" />
        <StatCard label="New" value={stats.isNew} icon="sparkles" color={'var(--app-warning)'} colors={colors} testId="stat-new" />
        <StatCard label="Soft Hidden" value={stats.softHidden} icon="eye-off" color={colors.warning} colors={colors} testId="stat-soft-hidden" />
        <StatCard label="Phase 1 Candidates" value={stats.phase1Candidates} icon="shield-checkmark" color={colors.accent} colors={colors} testId="stat-phase1-candidates" />
        <StatCard label="Phase 2 Ready" value={stats.phase2Candidates} icon="archive" color={colors.info} colors={colors} testId="stat-phase2-candidates" />
        <StatCard label="Phase 2 Retired" value={stats.phase2Retired} icon="lock-closed" color={colors.error} colors={colors} testId="stat-phase2-retired" />
      </View>

      <View
        style={{ marginBottom: 16, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 12 }}
        data-testid="feature-phase1-candidates-panel"
        testID="feature-phase1-candidates-panel"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="feature-phase1-candidates-title" testID="feature-phase1-candidates-title">
            {tx('admin.featureManagerPanel.auto.text.phase1Candidates', 'Phase 1 Safe Retirement Candidates (Live usage)')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="feature-phase1-candidates-count" testID="feature-phase1-candidates-count">
            {topPhase1Candidates.length} {tx('admin.featureManagerPanel.auto.text.phase1Visible', 'visible')}
          </Text>
        </View>
        {topPhase1Candidates.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="feature-phase1-candidates-empty" testID="feature-phase1-candidates-empty">
            {tx('admin.featureManagerPanel.auto.text.phase1NoCandidates', 'No low-usage candidates right now. Live usage data is healthy.')}
          </Text>
        ) : (
          <View style={{ gap: 8 }}>
            {topPhase1Candidates.map((candidate) => (
              <View
                key={`phase1-${candidate.feature_id}`}
                style={{
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: candidate.phase1_candidate_priority === 'high' ? `${colors.error}55` : `${colors.warning}55`,
                  backgroundColor: candidate.phase1_candidate_priority === 'high' ? colors.errorSoft : colors.warningSoft,
                  padding: 10,
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                }}
                data-testid={`feature-phase1-candidate-${candidate.feature_id}`}
                testID={`feature-phase1-candidate-${candidate.feature_id}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{candidate.title}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 2 }}>
                    30d: {candidate.usage_30d || 0} · 90d: {candidate.usage_90d || 0}
                  </Text>
                </View>
                <TouchableOpacity accessibilityLabel="Phase1 soft hide in feature manager panel"
                  onPress={() => phase1SoftHide(candidate.feature_id)}
                  style={{
                    borderRadius: 8,
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                    borderWidth: 1,
                    borderColor: `${colors.primary}66`,
                    backgroundColor: `${colors.primary}14`,
                  }}
                  data-testid={`feature-phase1-soft-hide-${candidate.feature_id}`}
                  testID={`feature-phase1-soft-hide-${candidate.feature_id}`}
                >
                  <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '800' }}>
                    {tx('admin.featureManagerPanel.auto.text.phase1SoftHide', 'Soft Hide')}
                  </Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}
      </View>

      <View
        style={{ marginBottom: 16, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 12 }}
        data-testid="feature-phase2-candidates-panel"
        testID="feature-phase2-candidates-panel"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="feature-phase2-candidates-title" testID="feature-phase2-candidates-title">
            {tx('admin.featureManagerPanel.auto.text.phase2Candidates', 'Phase 2 Registry Deactivation Candidates (Validated)')}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="feature-phase2-candidates-count" testID="feature-phase2-candidates-count">
            {topPhase2Candidates.length} {tx('admin.featureManagerPanel.auto.text.phase2Visible', 'ready')}
          </Text>
        </View>
        {topPhase2Candidates.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="feature-phase2-candidates-empty" testID="feature-phase2-candidates-empty">
            {tx('admin.featureManagerPanel.auto.text.phase2NoCandidates', 'No Phase 2-ready candidates yet. Features need enough soft-hide soak and near-zero usage.')}
          </Text>
        ) : (
          <View style={{ gap: 8 }}>
            {topPhase2Candidates.map((candidate) => (
              <View
                key={`phase2-${candidate.feature_id}`}
                style={{
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: `${colors.error}44`,
                  backgroundColor: colors.errorSoft,
                  padding: 10,
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                }}
                data-testid={`feature-phase2-candidate-${candidate.feature_id}`}
                testID={`feature-phase2-candidate-${candidate.feature_id}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{candidate.title}</Text>
                  <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 2 }}>
                    30d: {candidate.usage_30d || 0} · 90d: {candidate.usage_90d || 0} · Soft hidden: {candidate.soft_hidden_days || 0}d
                  </Text>
                </View>
                <TouchableOpacity accessibilityLabel="Phase2 deactivate in feature manager panel"
                  onPress={() => phase2Deactivate(candidate.feature_id)}
                  style={{
                    borderRadius: 8,
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                    borderWidth: 1,
                    borderColor: `${colors.error}66`,
                    backgroundColor: `${colors.error}15`,
                  }}
                  data-testid={`feature-phase2-deactivate-${candidate.feature_id}`}
                  testID={`feature-phase2-deactivate-${candidate.feature_id}`}
                >
                  <Text style={{ color: colors.error, fontSize: 11, fontWeight: '800' }}>
                    {tx('admin.featureManagerPanel.auto.text.phase2Deactivate', 'Deactivate')}
                  </Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* Search + Filter */}
      <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10, marginBottom: 16 }}>
        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, borderRadius: 10, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12, height: 40 }}>
          <Ionicons name="search" size={16} color={colors.textMuted} />
          <TextInput
            value={search} onChangeText={setSearch}
            placeholder={tx('admin.featureManagerPanel.auto.placeholder.001', 'Search features...')} placeholderTextColor={colors.textMuted}
            style={{ flex: 1, color: colors.text, fontSize: 13, marginLeft: 8, outlineStyle: 'none' } as any}
            data-testid="feature-search-input" testID="feature-search-input"
          />
          {search.length > 0 && (
            <TouchableOpacity onPress={() => setSearch('')} data-testid="feature-search-clear" testID="feature-search-clear">
              <Ionicons name="close-circle" size={16} color={colors.textMuted} />
            </TouchableOpacity>
          )}
        </View>
        {Platform.OS === 'web' ? (
          <div style={{ display: 'flex', flexDirection: 'row', gap: 4, overflowX: 'auto', flexShrink: 0 } as any}>
            {CATEGORY_OPTIONS.map(c => (
              <TouchableOpacity key={c.id} accessibilityLabel={tx('admin.featureManagerPanel.auto.accessibility.001', 'c.label')} onPress={() => setFilterCat(c.id)}
                style={{
                  paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8,
                  backgroundColor: filterCat === c.id ? '#0F766E20' : colors.surface,
                  borderWidth: 1, borderColor: filterCat === c.id ? '#0F766E40' : colors.border,
                }}
                data-testid={`filter-cat-${c.id}`} testID={`filter-cat-${c.id}`}>
                <Text style={{ color: filterCat === c.id ? 'var(--app-primary)' : colors.textMuted, fontSize: 11, fontWeight: '600' }}>{c.label}</Text>
              </TouchableOpacity>
            ))}
          </div>
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4 }}>
            {CATEGORY_OPTIONS.map(c => (
              <TouchableOpacity key={c.id} accessibilityLabel={tx('admin.featureManagerPanel.auto.accessibility.002', 'c.label')} onPress={() => setFilterCat(c.id)}
                style={{
                  paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8,
                  backgroundColor: filterCat === c.id ? '#0F766E20' : colors.surface,
                  borderWidth: 1, borderColor: filterCat === c.id ? '#0F766E40' : colors.border,
                }}
                data-testid={`filter-cat-${c.id}`} testID={`filter-cat-${c.id}`}>
                <Text style={{ color: filterCat === c.id ? 'var(--app-primary)' : colors.textMuted, fontSize: 11, fontWeight: '600' }}>{c.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}
      </View>

      {/* Results count */}
      <Text style={{ color: colors.textMuted, fontSize: 11, marginBottom: 10 }} data-testid="feature-results-count" testID="feature-results-count">
        Showing {filtered.length} of {features.length} features
      </Text>

      {/* Feature List */}
      {filtered.length === 0 ? (
        <View style={{ padding: 40, alignItems: 'center', backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}>
          <Ionicons name="search" size={32} color={colors.textMuted} />
          <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 8 }}>{tx('admin.featureManagerPanel.auto.text.005', 'No features match your filters')}</Text>
        </View>
      ) : (
        <View style={{ gap: 8 }}>
          {filtered.map(f => (
            <FeatureRow key={f.feature_id} feature={f} colors={colors} isMobile={isMobile}
              usage={phase2FeatureMap.get(f.feature_id) || phase1FeatureMap.get(f.feature_id)}
              onEdit={() => openEdit(f)}
              onDelete={() => setDeleteConfirm(f.feature_id)}
              onToggle={toggleField}
              onPhase1SoftHide={phase1SoftHide}
              onPhase1Restore={phase1Restore}
              onPhase2Deactivate={phase2Deactivate}
              onPhase2Restore={phase2Restore}
            />
          ))}
        </View>
      )}

      {/* Create/Edit Modal */}
      {showForm && (
        <FeatureFormModal
          form={form} setForm={setForm} isEdit={!!editingId} saving={saving}
          onSave={handleSave} onClose={() => { setShowForm(false); setEditingId(null); }}
          colors={colors} isMobile={isMobile}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <DeleteConfirmModal
          featureId={deleteConfirm} deleting={deleting}
          onConfirm={() => handleDelete(deleteConfirm)}
          onCancel={() => setDeleteConfirm(null)}
          colors={colors}
        />
      )}
    </View>
  );
}

/* ── Stat Card ── */
function StatCard({ label, value, icon, color, colors, testId }: { label: string; value: number; icon: string; color: string; colors: any; testId: string }) {
  return (
    <View style={{ flex: 1, minWidth: 100, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 6 }} data-testid={testId} testID={testId}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: `${color}18`, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon as any} size={14} color={color} />
        </View>
        <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{label}</Text>
      </View>
      <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800' }}>{value}</Text>
    </View>
  );
}

/* ── Feature Row ── */
function FeatureRow({ feature, colors, isMobile, usage, onEdit, onDelete, onToggle, onPhase1SoftHide, onPhase1Restore, onPhase2Deactivate, onPhase2Restore }: {
  feature: Feature; colors: any; isMobile: boolean;
  usage?: Feature;
  onEdit: () => void; onDelete: () => void;
  onToggle: (id: string, field: 'enabled' | 'premium' | 'is_new', current: boolean) => void;
  onPhase1SoftHide: (id: string) => void;
  onPhase1Restore: (id: string) => void;
  onPhase2Deactivate: (id: string) => void;
  onPhase2Restore: (id: string) => void;
}) {
  const rowState = usage || feature;
  const isPhase2Retired = !!rowState.phase2_deactivated;
  const canPhase2Deactivate = !!rowState.phase2_candidate;

  return (
    <View style={{
      flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center',
      backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border,
      padding: 14, gap: isMobile ? 12 : 14,
    }} data-testid={`feature-row-${feature.feature_id}`} testID={`feature-row-${feature.feature_id}`}>
      {/* Icon + Info */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
        <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: `${feature.color}18`, alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Ionicons name={feature.icon as any} size={18} color={feature.color} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }} numberOfLines={1}>{feature.title}</Text>
            {feature.is_new && (
              <View style={{ backgroundColor: colors.warningSoft, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                <Text style={{ color: colors.warningText, fontSize: 9, fontWeight: '700' }}>{tx('admin.featureManagerPanel.auto.text.006', 'NEW')}</Text>
              </View>
            )}
            {feature.premium && (
              <View style={{ backgroundColor: colors.accentSoft, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                <Text style={{ color: colors.accent, fontSize: 9, fontWeight: '700' }}>{tx('admin.featureManagerPanel.auto.text.007', 'PREMIUM')}</Text>
              </View>
            )}
            {feature.soft_deactivated && (
              <View style={{ backgroundColor: colors.warningSoft, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                <Text style={{ color: colors.warningText, fontSize: 9, fontWeight: '700' }}>{tx('admin.featureManagerPanel.auto.text.softHidden', 'SOFT HIDDEN')}</Text>
              </View>
            )}
            {isPhase2Retired && (
              <View style={{ backgroundColor: colors.errorSoft, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>
                <Text style={{ color: colors.errorText, fontSize: 9, fontWeight: '700' }}>{tx('admin.featureManagerPanel.auto.text.phase2Retired', 'PHASE 2 RETIRED')}</Text>
              </View>
            )}
          </View>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} numberOfLines={1}>{feature.description}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 }}>
            <Text style={{ color: colors.textMuted, fontSize: 10, backgroundColor: `${colors.border}80`, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>{feature.category}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10 }}>{feature.route}</Text>
            {usage ? (
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                30d: {usage.usage_30d || 0} · 90d: {usage.usage_90d || 0}
              </Text>
            ) : null}
            {usage?.soft_hidden_days !== undefined ? (
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>
                Soft hidden: {usage.soft_hidden_days || 0}d
              </Text>
            ) : null}
          </View>
        </View>
      </View>

      {/* Toggles + Actions */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
        <TogglePill label="Enabled" colors={colors} active={feature.enabled} color={'var(--app-success)'}
          onPress={() => onToggle(feature.feature_id, 'enabled', feature.enabled)}
          testId={`toggle-enabled-${feature.feature_id}`} />
        <TogglePill label="Premium" colors={colors} active={feature.premium} color={'var(--app-primary)'}
          onPress={() => onToggle(feature.feature_id, 'premium', feature.premium)}
          testId={`toggle-premium-${feature.feature_id}`} />
        <TogglePill label="New" colors={colors} active={feature.is_new} color={'var(--app-warning)'}
          onPress={() => onToggle(feature.feature_id, 'is_new', feature.is_new)}
          testId={`toggle-new-${feature.feature_id}`} />
        <TouchableOpacity accessibilityLabel="Feature in feature manager panel"
          onPress={() => (feature.soft_deactivated ? onPhase1Restore(feature.feature_id) : onPhase1SoftHide(feature.feature_id))}
          style={{
            borderRadius: 8,
            borderWidth: 1,
            borderColor: feature.soft_deactivated ? `${colors.success}55` : `${colors.warning}55`,
            backgroundColor: feature.soft_deactivated ? colors.successSoft : colors.warningSoft,
            paddingHorizontal: 8,
            paddingVertical: 6,
          }}
          data-testid={`phase1-toggle-${feature.feature_id}`}
          testID={`phase1-toggle-${feature.feature_id}`}
        >
          <Text style={{ color: feature.soft_deactivated ? colors.successText : colors.warningText, fontSize: 10, fontWeight: '700' }}>
            {feature.soft_deactivated
              ? tx('admin.featureManagerPanel.auto.text.restore', 'Restore')
              : tx('admin.featureManagerPanel.auto.text.softHide', 'Soft Hide')}
          </Text>
        </TouchableOpacity>
        {(feature.soft_deactivated || isPhase2Retired) && (
          <TouchableOpacity accessibilityLabel="Is phase2 retired in feature manager panel"
            onPress={() => (isPhase2Retired ? onPhase2Restore(feature.feature_id) : onPhase2Deactivate(feature.feature_id))}
            disabled={!isPhase2Retired && !canPhase2Deactivate}
            style={{
              borderRadius: 8,
              borderWidth: 1,
              borderColor: isPhase2Retired ? `${colors.success}55` : `${colors.error}66`,
              backgroundColor: isPhase2Retired ? colors.successSoft : colors.errorSoft,
              paddingHorizontal: 8,
              paddingVertical: 6,
              opacity: !isPhase2Retired && !canPhase2Deactivate ? 0.55 : 1,
            }}
            data-testid={`phase2-toggle-${feature.feature_id}`}
            testID={`phase2-toggle-${feature.feature_id}`}
          >
            <Text style={{ color: isPhase2Retired ? colors.successText : colors.errorText, fontSize: 10, fontWeight: '700' }}>
              {isPhase2Retired
                ? tx('admin.featureManagerPanel.auto.text.phase2Restore', 'Restore P2')
                : canPhase2Deactivate
                  ? tx('admin.featureManagerPanel.auto.text.phase2DeactivateShort', 'Phase 2')
                  : tx('admin.featureManagerPanel.auto.text.phase2NeedsValidation', 'Not Ready')}
            </Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity onPress={onEdit}
          style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor('var(--app-primary)', '15'), alignItems: 'center', justifyContent: 'center' }}
          data-testid={`edit-btn-${feature.feature_id}`} testID={`edit-btn-${feature.feature_id}`}>
          <Ionicons name="pencil" size={14} color={'var(--app-primary)'} />
        </TouchableOpacity>
        <TouchableOpacity onPress={onDelete}
          style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}
          data-testid={`delete-btn-${feature.feature_id}`} testID={`delete-btn-${feature.feature_id}`}>
          <Ionicons name="trash" size={14} color={'var(--app-error)'} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

/* ── Toggle Pill ── */
function TogglePill({ label, active, color, onPress, testId, colors }: { label: string; active: boolean; color: string; onPress: () => void; testId: string; colors: any }) {
  return (
    <TouchableOpacity onPress={onPress} accessibilityLabel={tx('admin.featureManagerPanel.auto.accessibility.003', 'Press')}
      style={{
        flexDirection: 'row', alignItems: 'center', gap: 4,
        paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6,
        backgroundColor: active ? `${color}18` : 'transparent',
        borderWidth: 1, borderColor: active ? `${color}40` : colors.borderStrong,
      }}
      data-testid={testId} testID={testId}>
      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: active ? color: colors.border }} />
      <Text style={{ color: active ? color : colors.textSec, fontSize: 10, fontWeight: '600' }}>{label}</Text>
    </TouchableOpacity>
  );
}

/* ── Form Modal ── */
function FeatureFormModal({ form, setForm, isEdit, saving, onSave, onClose, colors, isMobile }: {
  form: typeof EMPTY_FORM; setForm: (f: any) => void; isEdit: boolean; saving: boolean;
  onSave: () => void; onClose: () => void; colors: any; isMobile: boolean;
}) {
  const update = (field: string, value: any) => setForm((prev: any) => ({ ...prev, [field]: value }));

  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, alignItems: 'center', justifyContent: 'center' }}
      data-testid="feature-form-modal" testID="feature-form-modal">
      <TouchableOpacity activeOpacity={1} onPress={onClose}
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: colors.overlay }}
        data-testid="feature-form-backdrop" testID="feature-form-backdrop" />
      <View style={{
        width: isMobile ? '94%' : 520, maxHeight: '90%', backgroundColor: colors.surface,
        borderRadius: 16, borderWidth: 1, borderColor: colors.border, overflow: 'hidden',
        ...(Platform.OS === 'web' ? { boxShadow: '0 16px 64px rgba(0,0,0,0.4)' } : {}),
      }}>
        {/* Modal Header */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name={isEdit ? 'pencil' : 'add-circle'} size={18} color={'var(--app-primary)'} />
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{isEdit ? 'Edit Feature' : 'New Feature'}</Text>
          </View>
          <TouchableOpacity onPress={onClose} data-testid="feature-form-close" testID="feature-form-close">
            <Ionicons name="close" size={20} color={colors.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Form Body */}
        <View style={{ padding: 16, gap: 14, ...(Platform.OS === 'web' ? { overflowY: 'auto', maxHeight: 500 } as any : {}) }}>
          {/* Feature ID */}
          <FormField label="Feature ID" colors={colors}>
            <TextInput value={form.feature_id} onChangeText={(v) => update('feature_id', v)}
              editable={!isEdit} placeholder={tx('admin.featureManagerPanel.auto.placeholder.002', 'e.g. ai-translator')}
              placeholderTextColor={colors.textMuted}
              style={{ color: isEdit ? colors.textMuted : colors.text, fontSize: 13, flex: 1, outlineStyle: 'none', opacity: isEdit ? 0.6 : 1 } as any}
              data-testid="form-feature-id" testID="form-feature-id" />
          </FormField>

          {/* Title */}
          <FormField label="Title" colors={colors}>
            <TextInput value={form.title} onChangeText={(v) => update('title', v)}
              placeholder={tx('admin.featureManagerPanel.auto.placeholder.003', 'Feature name')} placeholderTextColor={colors.textMuted}
              style={{ color: colors.text, fontSize: 13, flex: 1, outlineStyle: 'none' } as any}
              data-testid="form-title" testID="form-title" />
          </FormField>

          {/* Description */}
          <FormField label="Description" colors={colors}>
            <TextInput value={form.description} onChangeText={(v) => update('description', v)}
              placeholder={tx('admin.featureManagerPanel.auto.placeholder.004', 'Short description')} placeholderTextColor={colors.textMuted}
              multiline numberOfLines={2}
              style={{ color: colors.text, fontSize: 13, flex: 1, minHeight: 44, outlineStyle: 'none' } as any}
              data-testid="form-description" testID="form-description" />
          </FormField>

          {/* Icon + Route row */}
          <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <FormField label="Icon (Ionicons)" colors={colors}>
                <TextInput value={form.icon} onChangeText={(v) => update('icon', v)}
                  placeholder={tx('admin.featureManagerPanel.auto.placeholder.005', 'apps')} placeholderTextColor={colors.textMuted}
                  style={{ color: colors.text, fontSize: 13, flex: 1, outlineStyle: 'none' } as any}
                  data-testid="form-icon" testID="form-icon" />
              </FormField>
            </View>
            <View style={{ flex: 1 }}>
              <FormField label="Route" colors={colors}>
                <TextInput value={form.route} onChangeText={(v) => update('route', v)}
                  placeholder={tx('admin.featureManagerPanel.auto.placeholder.006', '/features/ai-translator')} placeholderTextColor={colors.textMuted}
                  style={{ color: colors.text, fontSize: 13, flex: 1, outlineStyle: 'none' } as any}
                  data-testid="form-route" testID="form-route" />
              </FormField>
            </View>
          </View>

          {/* Category */}
          <View>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600', marginBottom: 6 }}>{tx('admin.featureManagerPanel.auto.text.008', 'Category')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {CATEGORY_OPTIONS.filter(c => c.id !== 'all').map(c => (
                <TouchableOpacity key={c.id} accessibilityLabel={tx('admin.featureManagerPanel.auto.accessibility.004', 'c.label')} onPress={() => update('category', c.id)}
                  style={{
                    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6,
                    backgroundColor: form.category === c.id ? '#0F766E20' : 'transparent',
                    borderWidth: 1, borderColor: form.category === c.id ? '#0F766E40' : colors.border,
                  }}
                  data-testid={`form-cat-${c.id}`} testID={`form-cat-${c.id}`}>
                  <Text style={{ color: form.category === c.id ? 'var(--app-primary)' : colors.textMuted, fontSize: 11, fontWeight: '600' }}>{c.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Color */}
          <View>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600', marginBottom: 6 }}>{tx('admin.featureManagerPanel.auto.text.009', 'Color')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {COLOR_PRESETS.map(c => (
                <TouchableOpacity key={c} accessibilityLabel={tx('admin.featureManagerPanel.auto.accessibility.005', 'checkmark button')} onPress={() => update('color', c)}
                  style={{
                    width: 28, height: 28, borderRadius: 8, backgroundColor: c,
                    borderWidth: 2, borderColor: form.color === c ? colors.primaryText : 'transparent',
                    alignItems: 'center', justifyContent: 'center',
                  }}
                  data-testid={`form-color-${c.replace('#', '')}`} testID={`form-color-${c.replace('#', '')}`}>
                  {form.color === c && <Ionicons name="checkmark" size={14} color={colors.primaryText} />}
                </TouchableOpacity>
              ))}
            </View>
          </View>

          {/* Toggles */}
          <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
            <FormToggle label="Enabled" active={form.enabled} onToggle={() => update('enabled', !form.enabled)} testId="form-toggle-enabled" />
            <FormToggle label="Premium" active={form.premium} onToggle={() => update('premium', !form.premium)} testId="form-toggle-premium" />
            <FormToggle label="New Badge" active={form.is_new} onToggle={() => update('is_new', !form.is_new)} testId="form-toggle-new" />
          </View>
        </View>

        {/* Modal Footer */}
        <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 10, padding: 16, borderTopWidth: 1, borderTopColor: colors.border }}>
          <TouchableOpacity onPress={onClose}
            style={{ paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.border }}
            data-testid="feature-form-cancel" testID="feature-form-cancel">
            <Text style={{ color: colors.textMuted, fontSize: 13, fontWeight: '600' }}>{tx('admin.featureManagerPanel.auto.text.010', 'Cancel')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onSave} disabled={saving || !form.feature_id.trim() || !form.title.trim()} accessibilityLabel={tx('admin.featureManagerPanel.auto.accessibility.006', 'Save')}
            style={{
              flexDirection: 'row', alignItems: 'center', gap: 6,
              paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10,
              backgroundColor: (!form.feature_id.trim() || !form.title.trim()) ? colors.border : 'var(--app-border)',
              opacity: saving ? 0.7 : 1,
            }}
            data-testid="feature-form-save" testID="feature-form-save">
            {saving ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="checkmark" size={16} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{isEdit ? 'Update' : 'Create'}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

/* ── Form Field Wrapper ── */
function FormField({ label, colors, children }: { label: string; colors: any; children: React.ReactNode }) {
  return (
    <View>
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600', marginBottom: 4 }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surfaceHover, borderRadius: 8, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, minHeight: 38 }}>
        {children}
      </View>
    </View>
  );
}

/* ── Form Toggle ── */
function FormToggle({ label, active, onToggle, testId }: { label: string; active: boolean; onToggle: () => void; testId: string }) {
  const colors = useAdminTheme();
  return (
    <TouchableOpacity onPress={onToggle}
      style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 }}
      data-testid={testId} testID={testId}>
      <View style={{
        width: 36, height: 20, borderRadius: 10,
        backgroundColor: active ? 'var(--app-success)' : colors.border,
        justifyContent: 'center', paddingHorizontal: 2,
      }}>
        <View style={{
          width: 16, height: 16, borderRadius: 8, backgroundColor: colors.primaryText,
          alignSelf: active ? 'flex-end' : 'flex-start',
        }} />
      </View>
      <Text style={{ color: active ? colors.textMuted : colors.textSec, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </TouchableOpacity>
  );
}

/* ── Delete Confirmation ── */
function DeleteConfirmModal({ featureId, deleting, onConfirm, onCancel, colors }: {
  featureId: string; deleting: boolean; onConfirm: () => void; onCancel: () => void; colors: any;
}) {
  return (
    <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, alignItems: 'center', justifyContent: 'center' }}
      data-testid="delete-confirm-modal" testID="delete-confirm-modal">
      <TouchableOpacity activeOpacity={1} onPress={onCancel} accessibilityLabel={tx('admin.featureManagerPanel.auto.accessibility.007', 'Cancel')}
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: colors.overlay }} />
      <View style={{
        width: 380, backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, overflow: 'hidden',
        ...(Platform.OS === 'web' ? { boxShadow: '0 16px 64px rgba(0,0,0,0.4)' } : {}),
      }}>
        <View style={{ padding: 24, alignItems: 'center', gap: 12 }}>
          <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="warning" size={24} color={'var(--app-error)'} />
          </View>
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700' }}>{tx('admin.featureManagerPanel.auto.text.011', 'Delete Feature?')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 13, textAlign: 'center' }}>
            This will permanently remove <Text style={{ color: colors.error, fontWeight: '700' }}>{featureId}</Text> from the registry.
          </Text>
        </View>
        <View style={{ flexDirection: 'row', borderTopWidth: 1, borderTopColor: colors.border }}>
          <TouchableOpacity onPress={onCancel} style={{ flex: 1, paddingVertical: 14, alignItems: 'center', borderRightWidth: 1, borderRightColor: colors.border }}
            data-testid="delete-cancel-btn" testID="delete-cancel-btn">
            <Text style={{ color: colors.textMuted, fontSize: 14, fontWeight: '600' }}>{tx('admin.featureManagerPanel.auto.text.012', 'Cancel')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onConfirm} disabled={deleting} style={{ flex: 1, paddingVertical: 14, alignItems: 'center', opacity: deleting ? 0.6 : 1 }}
            data-testid="delete-confirm-btn" testID="delete-confirm-btn">
            {deleting ? <ActivityIndicator size="small" color={'var(--app-error)'} /> : <Text style={{ color: colors.error, fontSize: 14, fontWeight: '700' }}>{tx('admin.featureManagerPanel.auto.text.013', 'Delete')}</Text>}
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}
