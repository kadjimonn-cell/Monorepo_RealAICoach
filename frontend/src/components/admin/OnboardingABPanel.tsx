import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  active: { bg: 'var(--app-bg)', text: 'var(--app-success)' },
  paused: { bg: 'var(--app-bg)', text: 'var(--app-warning)' },
  completed: { bg: 'var(--app-bg)', text: 'var(--app-text)' },
};
const VARIANT_COLORS = [
  'var(--app-primary)',
  'var(--app-success)',
  'var(--app-warning)',
  'var(--app-error)',
  'var(--app-primary)',
  'var(--app-error)',
  'var(--app-primary)',
  'var(--app-warning)',
];

export default function OnboardingABPanel({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { data: expData, loading: exLoading, refetch: load } = useLiveQuery('/onboarding-ab/experiments', { entity: 'onboarding-ab', pollInterval: 60000 });
  const { data: winnerData, loading: wLoading } = useLiveQuery('/onboarding-ab/winner-events', { entity: 'onboarding-ab', pollInterval: 60000 });
  const experiments = expData?.experiments || [];
  const steps = expData?.onboarding_steps || [];
  const targetTypes = expData?.target_types || [];
  const scopes = expData?.scopes || [];
  const winnerEvents = winnerData?.winner_events || [];
  const loading = exLoading || wLoading;
  const [showCreate, setShowCreate] = useState(false);
  const [expName, setExpName] = useState('');
  const [targetKey, setTargetKey] = useState('welcome');
  const [targetType, setTargetType] = useState('frontend_feature');
  const [scope, setScope] = useState('frontend_api');
  const [autoWinner, setAutoWinner] = useState(true);
  const [minParticipants, setMinParticipants] = useState('30');
  const [confidenceThreshold, setConfidenceThreshold] = useState('95');
  const [variants, setVariants] = useState<{id: string; label: string; allocation_pct: string}[]>([
    { id: 'control', label: tx('admin.onboardingAB.variants.control', 'Control'), allocation_pct: '50' },
    { id: 'variant_a', label: tx('admin.onboardingAB.variants.variantA', 'Variant A'), allocation_pct: '50' },
  ]);
  const [selectedExp, setSelectedExp] = useState<any>(null);
  const [results, setResults] = useState<any>(null);
  const [view, setView] = useState<'experiments' | 'winners'>('experiments');

  const addVariant = () => {
    const idx = variants.length;
    const next = [...variants, { id: `variant_${String.fromCharCode(97 + idx)}`, label: tx('admin.onboardingAB.variants.variantWithLetter', 'Variant {letter}').replace('{letter}', String.fromCharCode(65 + idx)), allocation_pct: '0' }];
    setVariants(next);
  };
  const removeVariant = (idx: number) => { if (variants.length > 2) setVariants(variants.filter((_, i) => i !== idx)); };
  const updateVariantLabel = (idx: number, label: string) => {
    const updated = [...variants];
    updated[idx] = { ...updated[idx], label };
    setVariants(updated);
  };
  const updateVariantAllocation = (idx: number, allocation_pct: string) => {
    const updated = [...variants];
    updated[idx] = { ...updated[idx], allocation_pct };
    setVariants(updated);
  };

  const create = async () => {
    if (!expName.trim()) return;
    try {
      await api.post('/onboarding-ab/experiments', {
        name: expName.trim(), target_key: targetKey.trim(), step_id: targetKey.trim(), target_type: targetType, scope, auto_winner: autoWinner,
        min_participants: parseInt(minParticipants) || 30,
        confidence_threshold: parseInt(confidenceThreshold) || 95,
        variants: variants.map(v => ({ id: v.id, label: v.label, allocation_pct: parseFloat(v.allocation_pct) || 0, config: {} })),
      });
      setShowCreate(false); setExpName('');
      setTargetKey('welcome'); setTargetType('frontend_feature'); setScope('frontend_api');
      setVariants([
        { id: 'control', label: tx('admin.onboardingAB.variants.control', 'Control'), allocation_pct: '50' },
        { id: 'variant_a', label: tx('admin.onboardingAB.variants.variantA', 'Variant A'), allocation_pct: '50' },
      ]);
      load();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/OnboardingABPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const toggleStatus = async (exp: any) => {
    const newStatus = exp.status === 'active' ? 'paused' : 'active';
    try { await api.put(`/onboarding-ab/experiments/${exp.experiment_id}`, { status: newStatus }); load(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/OnboardingABPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const deleteExp = async (expId: string) => {
    try { await api.delete(`/onboarding-ab/experiments/${expId}`); if (selectedExp?.experiment_id === expId) { setSelectedExp(null); setResults(null); } load(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/OnboardingABPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const viewResults = async (exp: any) => {
    setSelectedExp(exp);
    try { const r = await api.get(`/onboarding-ab/experiments/${exp.experiment_id}/results`); setResults(r.data); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/OnboardingABPanel.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  if (loading) return <ActivityIndicator color={colors.primary} />;

  return (
    <View data-testid="onboarding-ab-panel" testID="onboarding-ab-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.onboardingAB.header.title', 'Experimentation Engine')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.onboardingAB.header.subtitle', 'Variant routing with performance, engagement, error tracking, and auto-promotion')}</Text>
        </View>
        <TouchableOpacity onPress={() => setShowCreate(true)} data-testid="create-experiment-btn" testID="create-experiment-btn"
          style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 }}>
          <Ionicons name="flask" size={14} color={colors.primaryText} />
          <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.onboardingAB.actions.newExperiment', 'New Experiment')}</Text>
        </TouchableOpacity>
      </View>

      {/* KPIs */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, marginBottom: 20 }}>
        <KPI label={tx('admin.onboardingAB.kpi.experiments', 'Experiments')} value={experiments.length} color={colors.primary} icon="flask" colors={colors} />
        <KPI label={tx('admin.onboardingAB.kpi.active', 'Active')} value={experiments.filter(e => e.status === 'active').length} color={colors.success} icon="play-circle" colors={colors} />
        <KPI label={tx('admin.onboardingAB.kpi.completed', 'Completed')} value={experiments.filter(e => e.status === 'completed').length} color={colors.accent} icon="checkmark-circle" colors={colors} />
        <KPI label={tx('admin.onboardingAB.kpi.winnersFound', 'Winners Found')} value={winnerEvents.length} color={colors.warning} icon="trophy" colors={colors} />
      </View>

      {/* View Switcher */}
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {(['experiments', 'winners'] as const).map(v => (
          <TouchableOpacity key={v} onPress={() => setView(v)} data-testid={`ab-view-${v}`} testID={`ab-view-${v}`}
            style={{ paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8, backgroundColor: view === v ? colors.primary : colors.surfaceHover, borderWidth: 1, borderColor: view === v ? colors.primary : colors.border }}>
            <Text style={{ color: view === v ? colors.primaryText : colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{v === 'winners' ? tx('admin.onboardingAB.tabs.autoWinnerLog', 'Auto-Winner Log') : tx(`admin.onboardingAB.tabs.${v}`, v)}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Create Form */}
      {showCreate && (
        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30') }} data-testid="create-experiment-form" testID="create-experiment-form">
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 10 }}>{tx('admin.onboardingAB.create.title', 'Create Multi-Variate Experiment')}</Text>
          <TextInput value={expName} onChangeText={setExpName} placeholder={tx('admin.onboardingAB.create.placeholders.experimentName', 'Experiment name')} placeholderTextColor={colors.textMuted} data-testid="experiment-name-input" testID="experiment-name-input"
            style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 8, padding: 10, marginBottom: 8, borderWidth: 1, borderColor: colors.border, fontSize: 12 }} />

          {/* Target Preset */}
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.onboardingAB.create.targetPreset', 'Target Preset')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 10 }} data-testid="onboarding-ab-target-preset-wrap" testID="onboarding-ab-target-preset-wrap">
            {steps.map((s: any) => (
              <TouchableOpacity key={s.id} onPress={() => setTargetKey(s.id)} data-testid={`step-select-${s.id}`} testID={`step-select-${s.id}`}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: targetKey === s.id ? colors.primarySoft : colors.surface, borderWidth: 1, borderColor: targetKey === s.id ? colors.primary : colors.border }}>
                <Text style={{ color: targetKey === s.id ? colors.primary : colors.textMuted, fontSize: 9, fontWeight: '700' }}>{s.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TextInput value={targetKey} onChangeText={setTargetKey} placeholder={tx('admin.onboardingAB.create.placeholders.targetKey', 'Custom target key, route, or API name')} placeholderTextColor={colors.textMuted} data-testid="experiment-target-key-input" testID="experiment-target-key-input"
            style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 8, padding: 10, marginBottom: 8, borderWidth: 1, borderColor: colors.border, fontSize: 12 }} />

          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.onboardingAB.create.targetType', 'Target Type')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {targetTypes.map((item: any) => (
              <TouchableOpacity key={item.id} onPress={() => setTargetType(item.id)} data-testid={`target-type-${item.id}`} testID={`target-type-${item.id}`}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: targetType === item.id ? colors.primarySoft : colors.surface, borderWidth: 1, borderColor: targetType === item.id ? colors.primary : colors.border }}>
                <Text style={{ color: targetType === item.id ? colors.primary : colors.textMuted, fontSize: 9, fontWeight: '700' }}>{item.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600', marginBottom: 4 }}>{tx('admin.onboardingAB.create.scope', 'Scope')}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {scopes.map((item: any) => (
              <TouchableOpacity key={item.id} onPress={() => setScope(item.id)} data-testid={`scope-${item.id}`} testID={`scope-${item.id}`}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: scope === item.id ? colors.primarySoft : colors.surface, borderWidth: 1, borderColor: scope === item.id ? colors.primary : colors.border }}>
                <Text style={{ color: scope === item.id ? colors.primary : colors.textMuted, fontSize: 9, fontWeight: '700' }}>{item.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Multi-Variate Builder */}
          <View style={{ marginBottom: 10 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.onboardingAB.create.variantsWithCount', 'Variants ({count})').replace('{count}', String(variants.length))}</Text>
              <TouchableOpacity onPress={addVariant} data-testid="add-variant-btn" testID="add-variant-btn"
                style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }}>
                <Ionicons name="add" size={12} color={colors.primary} />
                <Text style={{ color: colors.primary, fontSize: 9, fontWeight: '700' }}>{tx('admin.onboardingAB.actions.addVariant', 'Add Variant')}</Text>
              </TouchableOpacity>
            </View>
            {variants.map((v, idx) => (
              <View key={v.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <View style={{ width: 6, height: 24, borderRadius: 3, backgroundColor: VARIANT_COLORS[idx % VARIANT_COLORS.length] }} />
                <TextInput value={v.label} onChangeText={val => updateVariantLabel(idx, val)} data-testid={`variant-label-${idx}`} testID={`variant-label-${idx}`}
                  style={{ flex: 1, backgroundColor: colors.surface, color: colors.text, borderRadius: 6, padding: 8, borderWidth: 1, borderColor: colors.border, fontSize: 11 }} />
                <TextInput accessibilityLabel="Variant allocation percentage" value={v.allocation_pct} onChangeText={val => updateVariantAllocation(idx, val.replace(/[^0-9.]/g, ''))} data-testid={`variant-allocation-${idx}`} testID={`variant-allocation-${idx}`}
                  style={{ width: 56, backgroundColor: colors.surface, color: colors.text, borderRadius: 6, padding: 8, borderWidth: 1, borderColor: colors.border, fontSize: 11, textAlign: 'center' }} />
                {variants.length > 2 && (
                  <TouchableOpacity onPress={() => removeVariant(idx)} data-testid={`remove-variant-${idx}`} testID={`remove-variant-${idx}`}>
                    <Ionicons name="close-circle" size={18} color={colors.error} />
                  </TouchableOpacity>
                )}
              </View>
            ))}
            <Text style={{ color: colors.textMuted, fontSize: 9, marginTop: 2 }}>{tx('admin.onboardingAB.create.trafficSplitHint', 'Traffic split can be 50/50 or custom percentages per variant.')}</Text>
          </View>

          {/* Auto-Winner Config */}
          <View style={{ backgroundColor: autoWinner ? colors.successSoft : colors.surface, borderRadius: 10, padding: 10, marginBottom: 10, borderWidth: 1, borderColor: autoWinner ? colors.successSoft : colors.border }}>
            <TouchableOpacity onPress={() => setAutoWinner(!autoWinner)} data-testid="auto-winner-toggle" testID="auto-winner-toggle"
              style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={autoWinner ? 'checkbox' : 'square-outline'} size={18} color={autoWinner ? colors.success : colors.textMuted} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: autoWinner ? colors.success : colors.text, fontSize: 11, fontWeight: '700' }}>{tx('admin.onboardingAB.create.autoWinnerDetection', 'Auto-Winner Detection')}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 9 }}>{tx('admin.onboardingAB.create.autoWinnerHint', 'Automatically retire weaker variants and promote the winner when thresholds are met')}</Text>
              </View>
            </TouchableOpacity>
            {autoWinner && (
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600', marginBottom: 3 }}>{tx('admin.onboardingAB.create.minParticipants', 'Min Participants')}</Text>
                  <TextInput value={minParticipants} onChangeText={setMinParticipants} data-testid="min-participants-input" testID="min-participants-input" accessibilityLabel="Confidence %"
                    style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 6, padding: 8, borderWidth: 1, borderColor: colors.border, fontSize: 11, textAlign: 'center' }} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600', marginBottom: 3 }}>{tx('admin.onboardingAB.create.confidencePercent', 'Confidence %')}</Text>
                  <TextInput value={confidenceThreshold} onChangeText={setConfidenceThreshold} data-testid="confidence-threshold-input" testID="confidence-threshold-input" accessibilityLabel="Text input"
                    style={{ backgroundColor: colors.surface, color: colors.text, borderRadius: 6, padding: 8, borderWidth: 1, borderColor: colors.border, fontSize: 11, textAlign: 'center' }} />
                </View>
              </View>
            )}
          </View>

          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={create} data-testid="save-experiment-btn" testID="save-experiment-btn"
              style={{ backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 10, paddingHorizontal: 20 }}>
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.onboardingAB.actions.createExperiment', 'Create Experiment')}</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="Cancel" onPress={() => setShowCreate(false)} style={{ paddingVertical: 10, paddingHorizontal: 16 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('admin.onboardingAB.actions.cancel', 'Cancel')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {view === 'experiments' && (
        <View>
          {experiments.length === 0 && !showCreate ? (
            <View style={{ padding: 32, alignItems: 'center', backgroundColor: colors.surfaceHover, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name="flask-outline" size={32} color={colors.textMuted} />
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{tx('admin.onboardingAB.states.noExperiments', 'No experiments yet. Create one to start safe feature experimentation.')}</Text>
            </View>
          ) : experiments.map((exp: any) => {
            const sc = STATUS_COLORS[exp.status] || STATUS_COLORS.active;
            const hasWinner = !!exp.winner_variant_id;
            return (
              <View key={exp.experiment_id} data-testid={`experiment-${exp.experiment_id}`} testID={`experiment-${exp.experiment_id}`}
                style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: selectedExp?.experiment_id === exp.experiment_id ? (globalThis as any).__alphaColor(colors.primary, '40') : hasWinner ? colors.successSoft : colors.border }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{exp.name}</Text>
                      <View style={{ backgroundColor: sc.bg, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                        <Text style={{ color: sc.text, fontSize: 8, fontWeight: '800' }}>{(exp.status || '').toUpperCase()}</Text>
                      </View>
                      {exp.auto_winner && (
                        <View style={{ backgroundColor: colors.successSoft, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                          <Ionicons name="flash" size={8} color={colors.success} />
                          <Text style={{ color: colors.successText, fontSize: 7, fontWeight: '800' }}>AUTO</Text>
                        </View>
                      )}
                      {hasWinner && (
                        <View style={{ backgroundColor: colors.warningSoft, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                          <Ionicons name="trophy" size={8} color={colors.warning} />
                          <Text style={{ color: colors.warningText, fontSize: 7, fontWeight: '800' }}>{tx('admin.onboardingAB.badges.winner', 'WINNER')}</Text>
                        </View>
                      )}
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 }}>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{exp.target_key || exp.step_id}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{exp.target_type || tx('admin.onboardingAB.defaults.frontendFeature', 'frontend_feature')}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{exp.scope || tx('admin.onboardingAB.defaults.frontendApi', 'frontend_api')}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.onboardingAB.meta.variantsCount', '{count} variants').replace('{count}', String((exp.variants || []).length))}</Text>
                      {exp.auto_winner && <Text style={{ color: colors.textMuted, fontSize: 10 }}>{tx('admin.onboardingAB.meta.minConf', 'min:{min} conf:{conf}%').replace('{min}', String(exp.min_participants)).replace('{conf}', String(exp.confidence_threshold))}</Text>}
                    </View>
                    {/* Variant pills */}
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 }} data-testid={`experiment-variants-wrap-${exp.experiment_id}`} testID={`experiment-variants-wrap-${exp.experiment_id}`}>
                      {(exp.variants || []).map((v: any, vi: number) => (
                        <View key={v.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: (globalThis as any).__alphaColor((v.is_paused || v.is_retired) ? colors.errorSoft : VARIANT_COLORS[vi % VARIANT_COLORS.length], '15'), paddingHorizontal: 6, paddingVertical: 3, borderRadius: 5 }}>
                          <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: (v.is_paused || v.is_retired) ? colors.error : VARIANT_COLORS[vi % VARIANT_COLORS.length] }} />
                          <Text style={{ color: (v.is_paused || v.is_retired) ? colors.error : colors.text, fontSize: 9, fontWeight: '600' }}>{v.label}</Text>
                          <Text style={{ color: colors.textMuted, fontSize: 7 }}>{v.allocation_pct || exp.traffic_split}%</Text>
                          {v.is_retired ? <Text style={{ color: colors.error, fontSize: 7, fontWeight: '800' }}>{tx('admin.onboardingAB.badges.retired', 'RETIRED')}</Text> : v.is_paused ? <Text style={{ color: colors.errorText, fontSize: 7, fontWeight: '800' }}>{tx('admin.onboardingAB.badges.paused', 'PAUSED')}</Text> : null}
                          {exp.winner_variant_id === v.id && <Ionicons name="trophy" size={8} color={colors.warning} />}
                        </View>
                      ))}
                    </View>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 6 }}>
                    <TouchableOpacity onPress={() => viewResults(exp)} data-testid={`view-results-${exp.experiment_id}`} testID={`view-results-${exp.experiment_id}`}
                      style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }}>
                      <Ionicons name="bar-chart" size={14} color={colors.primary} />
                    </TouchableOpacity>
                    {exp.status !== 'completed' && (
                      <TouchableOpacity onPress={() => toggleStatus(exp)} data-testid={`toggle-status-${exp.experiment_id}`} testID={`toggle-status-${exp.experiment_id}`}
                        style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: colors.surface }}>
                        <Ionicons name={exp.status === 'active' ? 'pause' : 'play'} size={14} color={exp.status === 'active' ? colors.warning : colors.success} />
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity onPress={() => deleteExp(exp.experiment_id)} data-testid={`delete-experiment-${exp.experiment_id}`} testID={`delete-experiment-${exp.experiment_id}`}
                      style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: colors.errorSoft }}>
                      <Ionicons name="trash" size={14} color={colors.error} />
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            );
          })}
        </View>
      )}

      {view === 'winners' && (
        <View>
          {winnerEvents.length === 0 ? (
            <View style={{ padding: 32, alignItems: 'center', backgroundColor: colors.surfaceHover, borderRadius: 12, borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name="trophy-outline" size={32} color={colors.textMuted} />
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8 }}>{tx('admin.onboardingAB.states.noWinners', 'No winners detected yet. The system checks every 15 minutes.')}</Text>
            </View>
          ) : winnerEvents.map((evt: any) => (
            <View key={evt.event_id} data-testid={`winner-event-${evt.event_id}`} testID={`winner-event-${evt.event_id}`}
              style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: colors.warningSoft, borderLeftWidth: 3, borderLeftColor: colors.warning }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Ionicons name="trophy" size={18} color={colors.warning} />
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>{evt.experiment_name}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 10 }}>{evt.detected_at ? new Date(evt.detected_at).toLocaleString() : ''}</Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ color: colors.successText, fontSize: 16, fontWeight: '800' }}>{evt.confidence?.toFixed(0)}%</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 9 }}>{tx('admin.onboardingAB.common.confidence', 'confidence')}</Text>
                </View>
              </View>
              <View style={{ flexDirection: 'row', gap: 6 }}>
                {(evt.variant_results || []).map((vr: any, idx: number) => {
                  const isWinner = vr.variant_id === evt.winner_variant_id;
                  return (
                    <View key={vr.variant_id} style={{ flex: 1, backgroundColor: isWinner ? colors.successSoft : colors.surface, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: isWinner ? colors.successSoft : colors.border }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                        <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: VARIANT_COLORS[idx % VARIANT_COLORS.length] }} />
                        <Text style={{ color: colors.text, fontSize: 10, fontWeight: '700' }}>{vr.label}</Text>
                        {isWinner && <Ionicons name="trophy" size={9} color={colors.warning} />}
                      </View>
                      <Text style={{ color: isWinner ? colors.success : colors.textMuted, fontSize: 16, fontWeight: '800', marginTop: 2 }}>{vr.composite_score ?? vr.conversion_rate}%</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 8 }}>eng {vr.engagement_rate}% • err {vr.error_rate}%</Text>
                    </View>
                  );
                })}
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 9, marginTop: 6 }}>{tx('admin.onboardingAB.winners.summary', 'Total: {participants} participants | Winner: {winner} | Weaker variants auto-retired').replace('{participants}', String(evt.total_participants)).replace('{winner}', String(evt.winner_label || ''))}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Results Panel */}
      {results && selectedExp && (
        <View style={{ backgroundColor: colors.surfaceHover, borderRadius: 12, padding: 16, marginTop: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30') }} data-testid="experiment-results-panel" testID="experiment-results-panel">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <View>
              <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>{tx('admin.onboardingAB.results.titleWithName', 'Results: {name}').replace('{name}', selectedExp.name || '')}</Text>
              {results.significance_reached && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 }}>
                  <Ionicons name="checkmark-circle" size={12} color={colors.success} />
                  <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '700' }}>{tx('admin.onboardingAB.results.significanceReached', 'Statistical significance reached')}</Text>
                </View>
              )}
            </View>
            <TouchableOpacity accessibilityLabel="results.total_participants" onPress={() => { setSelectedExp(null); setResults(null); }}>
              <Ionicons name="close-circle" size={18} color={colors.textMuted} />
            </TouchableOpacity>
          </View>

          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14 }}>
            <View style={{ flex: 1, backgroundColor: colors.primarySoft, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.primarySoft }}>
              <Text style={{ color: colors.primary, fontSize: 18, fontWeight: '800' }}>{results.total_participants}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.onboardingAB.results.participants', 'Participants')}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: results.significance_reached ? colors.successSoft : colors.warningSoft, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: results.significance_reached ? colors.successSoft : colors.warningSoft }}>
              <Text style={{ color: results.significance_reached ? colors.success : colors.warning, fontSize: 18, fontWeight: '800' }}>{Math.round(results.confidence)}%</Text>
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{tx('admin.onboardingAB.results.confidence', 'Confidence')}</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: results.auto_winner_enabled ? colors.successSoft : colors.surfaceHover, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: results.auto_winner_enabled ? colors.successSoft : colors.border }}>
              <Ionicons name={results.auto_winner_enabled ? 'flash' : 'flash-off'} size={16} color={results.auto_winner_enabled ? colors.success : colors.textSec} style={{ marginBottom: 2 }} />
              <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{results.auto_winner_enabled ? tx('admin.onboardingAB.results.autoOn', 'Auto ON') : tx('admin.onboardingAB.results.manual', 'Manual')}</Text>
            </View>
          </View>

          {(results.variant_results || []).map((vr: any, idx: number) => {
            const isWinner = vr.variant_id === results.winner;
            const vc = VARIANT_COLORS[idx % VARIANT_COLORS.length];
            return (
              <View key={vr.variant_id} data-testid={`variant-result-${vr.variant_id}`} testID={`variant-result-${vr.variant_id}`}
                style={{ flexDirection: 'row', alignItems: 'center', padding: 12, marginBottom: 6, borderRadius: 10, backgroundColor: isWinner ? colors.successSoft : vr.is_paused ? colors.errorSoft : colors.surface, borderWidth: 1, borderColor: isWinner ? colors.successSoft : vr.is_paused ? colors.errorSoft : colors.border, borderLeftWidth: 3, borderLeftColor: vr.is_paused ? colors.error : vc }}>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{vr.label}</Text>
                    {isWinner && (
                      <View style={{ backgroundColor: colors.successSoft, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                        <Ionicons name="trophy" size={10} color={colors.success} />
                        <Text style={{ color: colors.successText, fontSize: 8, fontWeight: '800' }}>{tx('admin.onboardingAB.badges.winner', 'WINNER')}</Text>
                      </View>
                    )}
                    {vr.is_paused && (
                      <View style={{ backgroundColor: colors.errorSoft, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                        <Text style={{ color: colors.error, fontSize: 8, fontWeight: '800' }}>{tx('admin.onboardingAB.badges.autoPaused', 'AUTO-PAUSED')}</Text>
                      </View>
                    )}
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 2 }}>{vr.assigned} assigned • eng {vr.engagement_rate}% • err {vr.error_rate}% • perf {vr.avg_performance_ms ?? 0}ms</Text>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ color: isWinner ? colors.success : vr.is_paused ? colors.error : colors.text, fontSize: 20, fontWeight: '800' }}>{vr.composite_score}%</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 9 }}>{tx('admin.onboardingAB.results.composite', 'composite')}</Text>
                </View>
              </View>
            );
          })}
          {(results.variant_results || []).length === 0 && (
            <Text style={{ color: colors.textMuted, fontSize: 11, textAlign: 'center', padding: 12 }}>{tx('admin.onboardingAB.results.noParticipants', 'No participants yet. Results will appear as users are assigned.')}</Text>
          )}
          {results.winner_detected_at && (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8, padding: 8, backgroundColor: colors.warningSoft, borderRadius: 8, borderWidth: 1, borderColor: colors.warningSoft }}>
              <Ionicons name="time" size={14} color={colors.warning} />
              <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '600' }}>{tx('admin.onboardingAB.results.winnerDetectedWithTime', 'Winner detected: {time}').replace('{time}', new Date(results.winner_detected_at).toLocaleString())}</Text>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

function KPI({ label, value, color, icon, colors }: any) {
  return (
    <View style={{ flex: 1, minWidth: 100, backgroundColor: (globalThis as any).__alphaColor(color, '08'), borderRadius: 12, padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '20') }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 6 }}>
        <Ionicons name={icon} size={13} color={color} />
        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{label}</Text>
      </View>
      <Text style={{ color, fontSize: 22, fontWeight: '800' }}>{value}</Text>
    </View>
  );
}
