import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, TextInput,
  StyleSheet, ActivityIndicator, Modal, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

const _T = {
  bg: 'var(--app-bg)' as any,
  card: 'var(--app-card-bg)' as any,
  cardAlt: 'var(--app-card-muted)' as any,
  border: 'var(--app-border)' as any,
  text: 'var(--app-text)' as any,
  textSec: 'var(--app-text-sec)' as any,
  textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any,
  success: 'var(--app-success)' as any,
  warning: 'var(--app-warning)' as any,
  danger: 'var(--app-error)' as any,
  purple: 'var(--app-info)' as any,
};

function makeT(AC: any) { return {
  bg: AC.bg, card: AC.card, cardAlt: AC.border, border: AC.border,
  text: AC.textSec, textSec: AC.textMuted, textMuted: AC.textDim || AC.textMuted,
  primary: AC.primary || 'var(--app-primary)', success: AC.success || 'var(--app-success)', warning: AC.warning || 'var(--app-warning)', danger: AC.error || 'var(--app-error)',
  purple: AC.purple || 'var(--app-primary)',
}; }

const TARGETS = [
  { id: 'upgrade_modal', label: 'Upgrade Modal', icon: 'arrow-up-circle' },
  { id: 'usage_indicator', label: 'Usage Indicator', icon: 'bar-chart' },
  { id: 'daily_email', label: 'Daily Email', icon: 'mail' },
  { id: 'pricing_page', label: 'Pricing Page', icon: 'pricetags' },
];

const AUDIENCES = [
  { id: 'all', label: 'All Users' },
  { id: 'free', label: 'Free Only' },
  { id: 'basic', label: 'Basic Only' },
  { id: 'free_basic', label: 'Free & Basic' },
];

const ALLOCATION_MODES = [
  { id: 'fixed_split', label: 'Fixed Split' },
  { id: 'multi_armed_bandit', label: 'Multi-Armed Bandit' },
];

const STATUS_COLORS: Record<string, string> = {
  draft: 'var(--app-text-muted)', running: 'var(--app-success)', paused: 'var(--app-warning)', completed: 'var(--app-primary)', winner_detected: 'var(--app-success)', rolled_out: 'var(--app-primary)', // @theme-ok brand/role/state identifier
};

// ── Metric Card (module-scope helper — uses CSS-var inline styles so it
// doesn't depend on the component's `s` StyleSheet which is created
// inside the default export's scope)
function MetricCard({ label, value, color, sub }: { label: string; value: string | number; color: string; sub?: string }) {
  return (
    <View style={{ flex: 1, minWidth: 130, backgroundColor: 'var(--app-card-bg)' as any, borderRadius: 10, padding: 14, borderLeftWidth: 3, borderLeftColor: color }}>
      <Text style={{ color: 'var(--app-text)' as any, fontSize: 22, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: 'var(--app-text-sec)' as any, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 }}>{label}</Text>
      {sub ? <Text style={{ color: 'var(--app-success)' as any, fontSize: 11, fontWeight: '600', marginTop: 2 }}>{sub}</Text> : null}
    </View>
  );
}

// ── Variant Row (module-scope helper — inline styles so it doesn't depend
// on the component's `s` StyleSheet)
function VariantRow({ variant, metrics, winner }: { variant: any; metrics: any; winner?: any }) {
  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { colors } = useTheme();
  const m = metrics || {};
  const impressions = m.impression?.total || m.impressions || 0;
  const clicks = m.click?.total || m.clicks || 0;
  const upgrades = m.upgrade?.total || m.upgrades || 0;
  const dismisses = m.dismiss?.total || m.dismisses || 0;
  const ctr = impressions > 0 ? ((clicks / impressions) * 100).toFixed(1) : '0.0';
  const cvr = impressions > 0 ? ((upgrades / impressions) * 100).toFixed(1) : '0.0';
  const isWinner = winner?.variant_id === variant.id;

  const vRowStyle = { backgroundColor: T.cardAlt, borderRadius: 10, padding: 12, marginBottom: 8 };
  const vHeaderStyle = { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 8, marginBottom: 8 };
  const vDotStyle = { width: 8, height: 8, borderRadius: 4 };
  const vNameStyle = { color: T.text, fontSize: 13, fontWeight: '700' as const, flex: 1 };
  const vWeightStyle = { color: T.textMuted, fontSize: 11 };
  const vMetricsStyle = { flexDirection: 'row' as const, gap: 8, flexWrap: 'wrap' as const };
  const vMetricStyle = { alignItems: 'center' as const, minWidth: 50 };
  const vmValueStyle = { color: T.text, fontSize: 14, fontWeight: '700' as const };
  const vmLabelStyle = { color: T.textMuted, fontSize: 10 };
  const configBoxStyle = { marginTop: 8, backgroundColor: T.bg, borderRadius: 6, padding: 8 };
  const configItemStyle = { color: T.textSec, fontSize: 11, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined };

  return (
    <View style={[vRowStyle, isWinner && { borderWidth: 1, borderColor: colors.success }]} data-testid={`variant-row-${variant.id}`} testID={`variant-row-${variant.id}`}>
      <View style={vHeaderStyle}>
        <View style={[vDotStyle, { backgroundColor: isWinner ? 'var(--app-success)' : variant.id === 'control' ? T.primary : T.warning }]} />
        <Text style={vNameStyle}>{variant.name}</Text>
        {isWinner && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.successSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }} data-testid={`winner-badge-${variant.id}`} testID={`winner-badge-${variant.id}`}>
            <Ionicons name="trophy" size={12} color={'var(--app-success)'} />
            <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800' }}>{tx('admin.promptAbTestingPanel.auto.text.001', 'WINNER')}</Text>
            <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '600' }}>{winner.confidence_pct}%</Text>
          </View>
        )}
        <Text style={vWeightStyle}>{variant.weight}%</Text>
      </View>
      <View style={vMetricsStyle}>
        <View style={vMetricStyle}>
          <Text style={vmValueStyle}>{impressions}</Text>
          <Text style={vmLabelStyle}>{tx('admin.promptAbTestingPanel.auto.text.002', 'Views')}</Text>
        </View>
        <View style={vMetricStyle}>
          <Text style={vmValueStyle}>{clicks}</Text>
          <Text style={vmLabelStyle}>{tx('admin.promptAbTestingPanel.auto.text.003', 'Clicks')}</Text>
        </View>
        <View style={vMetricStyle}>
          <Text style={[vmValueStyle, { color: T.successText }]}>{upgrades}</Text>
          <Text style={vmLabelStyle}>{tx('admin.promptAbTestingPanel.auto.text.004', 'Upgrades')}</Text>
        </View>
        <View style={vMetricStyle}>
          <Text style={vmValueStyle}>{dismisses}</Text>
          <Text style={vmLabelStyle}>{tx('admin.promptAbTestingPanel.auto.text.005', 'Dismiss')}</Text>
        </View>
        <View style={vMetricStyle}>
          <Text style={[vmValueStyle, { color: T.primary }]}>{ctr}%</Text>
          <Text style={vmLabelStyle}>{tx('admin.promptAbTestingPanel.auto.text.006', 'CTR')}</Text>
        </View>
        <View style={vMetricStyle}>
          <Text style={[vmValueStyle, { color: T.successText }]}>{cvr}%</Text>
          <Text style={vmLabelStyle}>{tx('admin.promptAbTestingPanel.auto.text.007', 'CVR')}</Text>
        </View>
      </View>
      {variant.config && Object.keys(variant.config).length > 0 && (
        <View style={configBoxStyle}>
          {Object.entries(variant.config).map(([k, v]) => (
            <Text key={k} style={configItemStyle}>
              <Text style={{ color: T.textMuted }}>{k}:</Text> {String(v)}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}

// ── Create/Edit Modal ──
function ExperimentFormModal({
  visible, onClose, onSave, initial,
}: { visible: boolean; onClose: () => void; onSave: (data: any) => void; initial?: any }) {
  const colors = useAdminTheme();
  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [name, setName] = useState(initial?.name || '');
  const [desc, setDesc] = useState(initial?.description || '');
  const [target, setTarget] = useState(initial?.target || 'upgrade_modal');
  const [audience, setAudience] = useState(initial?.audience || 'free_basic');
  const [traffic, setTraffic] = useState(String(initial?.traffic_pct ?? 100));
  const [allocationMode, setAllocationMode] = useState(initial?.traffic_allocation_mode || 'fixed_split');
  const [explorationRate, setExplorationRate] = useState(String(initial?.exploration_rate ?? 0.15));
  const [minSample, setMinSample] = useState(String(initial?.min_sample_size ?? 100));
  const [confidence, setConfidence] = useState(String(initial?.confidence_threshold ?? 95));
  const [autoRollout, setAutoRollout] = useState(initial?.auto_rollout ?? false);
  const [scheduledRollout, setScheduledRollout] = useState(initial?.scheduled_rollout_at || '');
  const [variants, setVariants] = useState<any[]>(
    initial?.variants || [
      { id: 'control', name: 'Control', weight: 50, config: {} },
      { id: 'variant_b', name: 'Variant B', weight: 50, config: {} },
    ]
  );

  useEffect(() => {
    if (initial) {
      setName(initial.name || '');
      setDesc(initial.description || '');
      setTarget(initial.target || 'upgrade_modal');
      setAudience(initial.audience || 'free_basic');
      setTraffic(String(initial.traffic_pct ?? 100));
      setAllocationMode(initial.traffic_allocation_mode || 'fixed_split');
      setExplorationRate(String(initial.exploration_rate ?? 0.15));
      setMinSample(String(initial.min_sample_size ?? 100));
      setConfidence(String(initial.confidence_threshold ?? 95));
      setAutoRollout(initial.auto_rollout ?? false);
      setScheduledRollout(initial.scheduled_rollout_at || '');
      setVariants(initial.variants || []);
    }
  }, [initial]);

  const updateVariant = (idx: number, field: string, value: any) => {
    setVariants(prev => prev.map((v, i) => i === idx ? { ...v, [field]: value } : v));
  };
  const addVariant = () => {
    const id = `var_${String.fromCharCode(65 + variants.length)}`;
    setVariants(prev => [...prev, { id, name: `Variant ${String.fromCharCode(65 + prev.length)}`, weight: 50, config: {} }]);
  };
  const removeVariant = (idx: number) => setVariants(prev => prev.filter((_, i) => i !== idx));

  return (
    <Modal transparent visible={visible} animationType="fade" onRequestClose={onClose}>
      <View style={s.modalOverlay}>
        <View style={[s.modalContent, { maxHeight: '90%' }]}>
          <ScrollView showsVerticalScrollIndicator={false}>
            <Text style={s.modalTitle}>{initial ? 'Edit Experiment' : 'New Experiment'}</Text>

            <Text style={s.fieldLabel}>{tx('admin.promptAbTestingPanel.auto.text.008', 'Name')}</Text>
            <TextInput style={s.input} value={name} onChangeText={setName} placeholder={tx('admin.promptAbTestingPanel.auto.placeholder.001', 'e.g. Upgrade Modal CTA Test')} placeholderTextColor={T.textMuted} data-testid="exp-name-input" testID="exp-name-input" />

            <Text style={s.fieldLabel}>{tx('admin.promptAbTestingPanel.auto.text.009', 'Description')}</Text>
            <TextInput style={[s.input, { height: 60 }]} value={desc} onChangeText={setDesc} placeholder={tx('admin.promptAbTestingPanel.auto.placeholder.002', 'What are you testing?')} placeholderTextColor={T.textMuted} multiline data-testid="exp-desc-input" testID="exp-desc-input" />

            <Text style={s.fieldLabel}>{tx('admin.promptAbTestingPanel.auto.text.010', 'Target Surface')}</Text>
            <View style={s.chipRow}>
              {TARGETS.map(t => (
                <TouchableOpacity key={t.id} onPress={() => setTarget(t.id)}
                  style={[s.chip, target === t.id && { backgroundColor: T.primary, borderColor: T.primary }]}
                  data-testid={`target-${t.id}`} testID={`target-${t.id}`}>
                  <Ionicons name={t.icon as any} size={14} color={target === t.id ? 'var(--app-primary-text)' : T.textSec} />
                  <Text style={[s.chipText, target === t.id && { color: colors.primaryText }]}>{t.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={s.fieldLabel}>{tx('admin.promptAbTestingPanel.auto.text.011', 'Audience')}</Text>
            <View style={s.chipRow}>
              {AUDIENCES.map(a => (
                <TouchableOpacity key={a.id} onPress={() => setAudience(a.id)}
                  style={[s.chip, audience === a.id && { backgroundColor: T.primary, borderColor: T.primary }]}
                  data-testid={`audience-${a.id}`} testID={`audience-${a.id}`}>
                  <Text style={[s.chipText, audience === a.id && { color: colors.primaryText }]}>{a.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={s.fieldLabel}>{tx('admin.promptAbTestingPanel.auto.text.012', 'Traffic %')}</Text>
            <TextInput style={[s.input, { width: 80 }]} value={traffic} onChangeText={setTraffic} keyboardType="numeric" data-testid="exp-traffic-input" testID="exp-traffic-input" />

            <Text style={[s.fieldLabel, { marginTop: 12 }]}>{tx('admin.promptAbTestingPanel.auto.text.013', 'Traffic Allocation Mode')}</Text>
            <View style={s.chipRow}>
              {ALLOCATION_MODES.map(mode => (
                <TouchableOpacity
                  key={mode.id}
                  onPress={() => setAllocationMode(mode.id)}
                  style={[s.chip, allocationMode === mode.id && { backgroundColor: T.purple, borderColor: T.purple }]}
                  data-testid={`allocation-mode-${mode.id}`}
                  testID={`allocation-mode-${mode.id}`}
                >
                  <Ionicons name={mode.id === 'multi_armed_bandit' ? 'pulse' : 'git-branch'} size={14} color={allocationMode === mode.id ? 'var(--app-primary-text)' : T.textSec} />
                  <Text style={[s.chipText, allocationMode === mode.id && { color: colors.primaryText }]}>{mode.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {allocationMode === 'multi_armed_bandit' && (
              <View style={{ marginTop: 10 }}>
                <Text style={[s.fieldLabel, { marginTop: 0 }]}>{tx('admin.promptAbTestingPanel.auto.text.014', 'Exploration Rate (0 to 0.5)')}</Text>
                <TextInput accessibilityLabel={tx('admin.promptAbTestingPanel.auto.accessibility.001', 'Text input')}
                  style={[s.input, { width: 120 }]}
                  value={explorationRate}
                  onChangeText={setExplorationRate}
                  keyboardType="numeric"
                  data-testid="exp-exploration-rate-input"
                  testID="exp-exploration-rate-input"
                />
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{tx('admin.promptAbTestingPanel.auto.text.015', 'Higher values explore more often; lower values exploit top-performing variants.')}</Text>
              </View>
            )}

            <Text style={[s.fieldLabel, { marginTop: 12 }]}>{tx('admin.promptAbTestingPanel.auto.text.016', 'Auto Winner Detection')}</Text>
            <View style={{ flexDirection: 'row', gap: 12 }}>
              <View style={{ flex: 1 }}>
                <Text style={[s.fieldLabel, { marginTop: 4, fontSize: 11 }]}>{tx('admin.promptAbTestingPanel.auto.text.017', 'Min Impressions/Variant')}</Text>
                <TextInput style={s.input} value={minSample} onChangeText={setMinSample} keyboardType="numeric" placeholder="100" placeholderTextColor={T.textMuted} data-testid="exp-min-sample-input" testID="exp-min-sample-input" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.fieldLabel, { marginTop: 4, fontSize: 11 }]}>{tx('admin.promptAbTestingPanel.auto.text.018', 'Confidence Threshold %')}</Text>
                <TextInput style={s.input} value={confidence} onChangeText={setConfidence} keyboardType="numeric" placeholder="95" placeholderTextColor={T.textMuted} data-testid="exp-confidence-input" testID="exp-confidence-input" />
              </View>
            </View>

            <TouchableOpacity
              style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 12, paddingVertical: 8 }}
              onPress={() => setAutoRollout(!autoRollout)}
              data-testid="exp-auto-rollout-toggle" testID="exp-auto-rollout-toggle"
            >
              <View style={{
                width: 40, height: 22, borderRadius: 11, justifyContent: 'center',
                backgroundColor: autoRollout ? T.primary : T.border, paddingHorizontal: 2,
              }}>
                <View style={{
                  width: 18, height: 18, borderRadius: 9, backgroundColor: colors.primaryText,
                  alignSelf: autoRollout ? 'flex-end' : 'flex-start',
                }} />
              </View>
              <View>
                <Text style={{ color: T.text, fontSize: 13, fontWeight: '600' }}>{tx('admin.promptAbTestingPanel.auto.text.019', 'Auto-Rollout Winner')}</Text>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.promptAbTestingPanel.auto.text.020', 'Apply winning config as default when significance reached')}</Text>
              </View>
            </TouchableOpacity>

            {autoRollout && (
              <View style={{ marginTop: 12 }}>
                <Text style={s.fieldLabel}>{tx('admin.promptAbTestingPanel.auto.text.021', 'Schedule Rollout (optional)')}</Text>
                <TextInput
                  style={s.input}
                  value={scheduledRollout}
                  onChangeText={setScheduledRollout}
                  placeholder={tx('admin.promptAbTestingPanel.auto.placeholder.003', 'YYYY-MM-DDTHH:MM (leave empty for immediate)')}
                  placeholderTextColor={T.textMuted}
                  data-testid="scheduled-rollout-input" testID="scheduled-rollout-input"
                />
                <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>
                  {scheduledRollout ? `Rollout scheduled for ${new Date(scheduledRollout).toLocaleString()}` : 'Winner will be rolled out immediately when detected'}
                </Text>
              </View>
            )}

            <Text style={[s.fieldLabel, { marginTop: 16 }]}>{tx('admin.promptAbTestingPanel.auto.text.022', 'Variants')}</Text>
            {variants.map((v, i) => (
              <View key={i} style={s.variantForm}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={s.variantFormTitle}>Variant {i + 1}</Text>
                  {variants.length > 2 && (
                    <TouchableOpacity accessibilityLabel={tx('admin.promptAbTestingPanel.auto.accessibility.002', 'trash outline button')} onPress={() => removeVariant(i)}>
                      <Ionicons name="trash-outline" size={16} color={T.danger} />
                    </TouchableOpacity>
                  )}
                </View>
                <TextInput style={s.inputSm} value={v.name} onChangeText={val => updateVariant(i, 'name', val)} placeholder={tx('admin.promptAbTestingPanel.auto.placeholder.004', 'Variant name')} placeholderTextColor={T.textMuted} />
                <TextInput style={s.inputSm} value={String(v.weight)} onChangeText={val => updateVariant(i, 'weight', parseFloat(val) || 0)} keyboardType="numeric" placeholder={tx('admin.promptAbTestingPanel.auto.placeholder.005', 'Weight')} placeholderTextColor={T.textMuted} />
                <TextInput style={[s.inputSm, { height: 50 }]} value={JSON.stringify(v.config || {})}
                  onChangeText={val => { try { updateVariant(i, 'config', JSON.parse(val)); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/PromptABTestingPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }}
                  placeholder='{"cta_text": "...", "cta_color": "#..."}'
                  placeholderTextColor={T.textMuted} multiline />
              </View>
            ))}
            <TouchableOpacity style={s.addVariantBtn} onPress={addVariant} data-testid="add-variant-btn" testID="add-variant-btn">
              <Ionicons name="add-circle-outline" size={16} color={T.primary} />
              <Text style={{ color: T.primary, fontSize: 13, fontWeight: '600' }}>{tx('admin.promptAbTestingPanel.auto.text.023', 'Add Variant')}</Text>
            </TouchableOpacity>

            <View style={s.modalActions}>
              <TouchableOpacity style={s.cancelBtn} onPress={onClose} data-testid="exp-cancel-btn" testID="exp-cancel-btn">
                <Text style={{ color: T.textSec, fontWeight: '600' }}>{tx('admin.promptAbTestingPanel.auto.text.024', 'Cancel')}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.saveBtn} accessibilityLabel={tx('admin.promptAbTestingPanel.auto.accessibility.003', 'checkmark button')} onPress={() => onSave({
                name, description: desc, target, audience, traffic_pct: parseFloat(traffic) || 100,
                traffic_allocation_mode: allocationMode,
                exploration_rate: Math.max(0, Math.min(0.5, parseFloat(explorationRate) || 0.15)),
                min_sample_size: parseInt(minSample) || 100, confidence_threshold: parseFloat(confidence) || 95,
                auto_rollout: autoRollout,
                scheduled_rollout_at: autoRollout && scheduledRollout ? new Date(scheduledRollout).toISOString() : null,
                variants,
              })} data-testid="exp-save-btn" testID="exp-save-btn">
                <Ionicons name="checkmark" size={16} color="var(--app-primary-text)" />
                <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{tx('admin.promptAbTestingPanel.auto.text.025', 'Save')}</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

// ── Main Panel ──
export default function PromptABTestingPanel() {
  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const panelTitle = t('promptAB.header.title');
  const s = StyleSheet.create({
    // Uses _T (module-level defaults) for static styles
    container: { flex: 1, padding: 20 },
    header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 },
    title: { color: _T.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.3 },
    subtitle: { color: _T.textMuted, fontSize: 13, marginTop: 2 },
    createBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: _T.primary, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
    createBtnText: { color: colors.primaryText, fontSize: 13, fontWeight: '700' },
    kpiRow: { flexDirection: 'row', gap: 12, marginBottom: 20, flexWrap: 'wrap' },
    metricCard: { flex: 1, minWidth: 130, backgroundColor: _T.card, borderRadius: 10, padding: 14, borderLeftWidth: 3 },
    metricValue: { color: _T.text, fontSize: 22, fontWeight: '800' },
    metricLabel: { color: _T.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 },
    metricSub: { color: _T.successText, fontSize: 11, fontWeight: '600', marginTop: 2 },
    emptyState: { alignItems: 'center', paddingVertical: 60 },
    emptyTitle: { color: _T.textSec, fontSize: 16, fontWeight: '700', marginTop: 12 },
    emptyDesc: { color: _T.textMuted, fontSize: 13, marginTop: 4, textAlign: 'center' },
    expCard: { backgroundColor: _T.card, borderRadius: 12, marginBottom: 12, borderWidth: 1, borderColor: _T.border, overflow: 'hidden' },
    expHeader: { flexDirection: 'row', alignItems: 'center', padding: 16, gap: 12 },
    statusBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, borderWidth: 1 },
    statusText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
    targetBadge: { color: _T.textSec, fontSize: 11, fontWeight: '600', backgroundColor: _T.cardAlt, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
    audienceBadge: { color: _T.textMuted, fontSize: 11, backgroundColor: _T.cardAlt, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
    expName: { color: _T.text, fontSize: 15, fontWeight: '700' },
    expDesc: { color: _T.textMuted, fontSize: 12, marginTop: 2 },
    quickMetrics: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingBottom: 8, flexWrap: 'wrap' },
    quickVariant: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: _T.cardAlt, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6 },
    qvName: { color: _T.textSec, fontSize: 11, fontWeight: '600' },
    qvMetric: { color: _T.textMuted, fontSize: 11 },
    expActions: { flexDirection: 'row', gap: 6, paddingHorizontal: 16, paddingBottom: 12, flexWrap: 'wrap' },
    actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 1, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 5 },
    actionText: { fontSize: 12, fontWeight: '600' },
    detailSection: { borderTopWidth: 1, borderTopColor: _T.border, padding: 16 },
    detailTitle: { color: _T.text, fontSize: 14, fontWeight: '700', marginBottom: 12 },
    variantRow: { backgroundColor: _T.cardAlt, borderRadius: 10, padding: 12, marginBottom: 8 },
    variantHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
    variantDot: { width: 8, height: 8, borderRadius: 4 },
    variantName: { color: _T.text, fontSize: 13, fontWeight: '700', flex: 1 },
    variantWeight: { color: _T.textMuted, fontSize: 11 },
    variantMetrics: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
    variantMetric: { alignItems: 'center', minWidth: 50 },
    vmValue: { color: _T.text, fontSize: 14, fontWeight: '700' },
    vmLabel: { color: _T.textMuted, fontSize: 10 },
    configBox: { marginTop: 8, backgroundColor: _T.bg, borderRadius: 6, padding: 8 },
    configItem: { color: _T.textSec, fontSize: 11, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined },
    modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', alignItems: 'center' },
    modalContent: { backgroundColor: _T.card, borderRadius: 16, padding: 24, width: '90%', maxWidth: 520 },
    modalTitle: { color: _T.text, fontSize: 18, fontWeight: '800', marginBottom: 16 },
    fieldLabel: { color: _T.textSec, fontSize: 12, fontWeight: '600', marginTop: 12, marginBottom: 4 },
    input: { backgroundColor: _T.bg, borderWidth: 1, borderColor: _T.border, borderRadius: 8, padding: 10, color: _T.text, fontSize: 13 },
    inputSm: { backgroundColor: _T.bg, borderWidth: 1, borderColor: _T.border, borderRadius: 6, padding: 8, color: _T.text, fontSize: 12, marginTop: 4 },
    chipRow: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
    chip: { flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 1, borderColor: _T.border, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 5 },
    chipText: { color: _T.textSec, fontSize: 12, fontWeight: '600' },
    variantForm: { backgroundColor: _T.cardAlt, borderRadius: 8, padding: 10, marginBottom: 8 },
    variantFormTitle: { color: _T.textSec, fontSize: 12, fontWeight: '700', marginBottom: 4 },
    addVariantBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 8 },
    modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 10, marginTop: 20 },
    cancelBtn: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: _T.border },
    saveBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: _T.primary, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  });
  const [experiments, setExperiments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingExp, setEditingExp] = useState<any>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detailData, setDetailData] = useState<any>(null);
  const [evaluating, setEvaluating] = useState<string | null>(null);

  const fetchExperiments = useCallback(async () => {
    try {
      const res = await api.get('/admin/prompt-experiments');
      setExperiments(res.data.experiments || []);
    } catch (e) {
      console.error('Failed to load experiments', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchExperiments(); }, [fetchExperiments]);

  const handleSave = async (data: any) => {
    try {
      if (editingExp) {
        await api.patch(`/admin/prompt-experiments/${editingExp.experiment_id}`, data);
      } else {
        await api.post('/admin/prompt-experiments', data);
      }
      setShowForm(false);
      setEditingExp(null);
      fetchExperiments();
    } catch (e: any) {
      console.error('Save failed', e);
    }
  };

  const handleStatusChange = async (expId: string, newStatus: string) => {
    try {
      await api.patch(`/admin/prompt-experiments/${expId}`, { status: newStatus });
      fetchExperiments();
    } catch (e) {
      console.error('Status update failed', e);
    }
  };

  const handleDelete = async (expId: string) => {
    try {
      await api.delete(`/admin/prompt-experiments/${expId}`);
      if (expandedId === expId) setExpandedId(null);
      fetchExperiments();
    } catch (e) {
      console.error('Delete failed', e);
    }
  };

  const handleEvaluate = async (expId: string) => {
    setEvaluating(expId);
    try {
      const res = await api.post('/prompt-experiment/evaluate', { experiment_id: expId });
      if (res.data.winner_detected || res.data.already_detected) {
        fetchExperiments();
        if (expandedId === expId) loadDetail(expId);
      }
    } catch (e) {
      console.error('Evaluation failed', e);
    } finally {
      setEvaluating(null);
    }
  };

  const handleRollout = async (expId: string) => {
    try {
      await api.post('/prompt-experiment/rollout', { experiment_id: expId });
      fetchExperiments();
      if (expandedId === expId) loadDetail(expId);
    } catch (e) {
      console.error('Rollout failed', e);
    }
  };

  const handleRevert = async (expId: string) => {
    try {
      await api.post('/prompt-experiment/revert-rollout', { experiment_id: expId });
      fetchExperiments();
      if (expandedId === expId) loadDetail(expId);
    } catch (e) {
      console.error('Revert failed', e);
    }
  };

  const loadDetail = async (expId: string) => {
    if (expandedId === expId) {
      setExpandedId(null);
      setDetailData(null);
      return;
    }
    try {
      const res = await api.get(`/admin/prompt-experiments/${expId}`);
      setDetailData(res.data);
      setExpandedId(expId);
    } catch (e) {
      console.error('Failed to load detail', e);
    }
  };

  // Summary metrics across all experiments
  const totalExperiments = experiments.length;
  const running = experiments.filter(e => e.status === 'running').length;
  const totalImpressions = experiments.reduce((sum, e) => {
    const m = e.metrics || {};
    return sum + Object.values(m).reduce((s: number, vm: any) => s + (vm.impressions || 0), 0);
  }, 0);
  const totalUpgrades = experiments.reduce((sum, e) => {
    const m = e.metrics || {};
    return sum + Object.values(m).reduce((s: number, vm: any) => s + (vm.upgrades || 0), 0);
  }, 0);

  if (loading) {
    return (
      <View style={{ padding: 40, alignItems: 'center', backgroundColor: colors.bg }}>
        <ActivityIndicator size="large" color={T.primary} />
        <Text style={{ color: colors.textSec, marginTop: 12 }}>{tx('promptAB.states.loading', 'Loading experiments...')}</Text>
      </View>
    );
  }

  return (
    <View style={[s.container, { backgroundColor: colors.bg }]} data-testid="prompt-ab-testing-panel" testID="prompt-ab-testing-panel">
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.title}>{panelTitle === 'promptAB.header.title' ? 'Prompt A/B Testing' : panelTitle}</Text>
          <Text style={s.subtitle}>{tx('promptAB.header.subtitle', 'Test upgrade prompts, CTAs, and UI elements')}</Text>
        </View>
        <TouchableOpacity style={s.createBtn} onPress={() => { setEditingExp(null); setShowForm(true); }} data-testid="create-experiment-btn" testID="create-experiment-btn">
          <Ionicons name="add" size={16} color="var(--app-primary-text)" />
          <Text style={s.createBtnText}>{tx('promptAB.header.newExperiment', 'New Experiment')}</Text>
        </TouchableOpacity>
      </View>

      {/* Summary KPIs */}
      <View style={s.kpiRow}>
        <MetricCard label={tx('promptAB.kpis.totalExperiments', 'Total Experiments')} value={totalExperiments} color={T.primary} />
        <MetricCard label={tx('promptAB.kpis.running', 'Running')} value={running} color={T.successText} />
        <MetricCard label={tx('promptAB.kpis.totalImpressions', 'Total Impressions')} value={totalImpressions.toLocaleString()} color={T.warningText} />
        <MetricCard label={tx('promptAB.kpis.totalUpgrades', 'Total Upgrades')} value={totalUpgrades} color={T.successText} sub={totalImpressions > 0 ? tx('promptAB.kpis.cvr', '{value}% CVR').replace('{value}', (totalUpgrades / totalImpressions * 100).toFixed(1)) : '--'} />
      </View>

      {/* Experiment List */}
      {experiments.length === 0 ? (
        <View style={s.emptyState}>
          <Ionicons name="flask-outline" size={40} color={T.textMuted} />
          <Text style={s.emptyTitle}>{tx('promptAB.states.emptyTitle', 'No experiments yet')}</Text>
          <Text style={s.emptyDesc}>{tx('promptAB.states.emptyDesc', 'Create your first A/B test to optimize upgrade conversions')}</Text>
        </View>
      ) : (
        experiments.map(exp => {
          const isExpanded = expandedId === exp.experiment_id;
          const detail = isExpanded ? detailData : null;

          return (
            <View key={exp.experiment_id} style={s.expCard} data-testid={`exp-card-${exp.experiment_id}`} testID={`exp-card-${exp.experiment_id}`}>
              {/* Experiment header */}
              <TouchableOpacity style={s.expHeader} onPress={() => loadDetail(exp.experiment_id)} data-testid={`exp-toggle-${exp.experiment_id}`} testID={`exp-toggle-${exp.experiment_id}`}>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <View style={[s.statusBadge, { backgroundColor: (globalThis as any).__alphaColor(STATUS_COLORS[exp.status], '20'), borderColor: STATUS_COLORS[exp.status] }]}>
                      <Text style={[s.statusText, { color: STATUS_COLORS[exp.status] }]}>{exp.status.toUpperCase()}</Text>
                    </View>
                    <Text style={s.targetBadge}>{TARGETS.find(t => t.id === exp.target)?.label || exp.target}</Text>
                    <Text style={s.audienceBadge}>{AUDIENCES.find(a => a.id === exp.audience)?.label || exp.audience}</Text>
                      {exp.traffic_allocation_mode === 'multi_armed_bandit' && (
                        <View style={{ backgroundColor: colors.purpleSoft, borderWidth: 1, borderColor: colors.purpleSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid={`exp-bandit-badge-${exp.experiment_id}`} testID={`exp-bandit-badge-${exp.experiment_id}`}>
                          <Ionicons name="pulse" size={10} color={colors.purpleText} />
                          <Text style={{ color: colors.purpleText, fontSize: 10, fontWeight: '700' }}>{tx('admin.promptAbTestingPanel.auto.text.026', 'BANDIT')}</Text>
                        </View>
                      )}
                  </View>
                  <Text style={s.expName}>{exp.name}</Text>
                  {exp.description ? <Text style={s.expDesc}>{exp.description}</Text> : null}
                </View>
                <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={18} color={T.textMuted} />
              </TouchableOpacity>

              {/* Quick metrics */}
              <View style={s.quickMetrics}>
                {(exp.variants || []).map((v: any) => {
                  const vm = (exp.metrics || {})[v.id] || {};
                  return (
                    <View key={v.id} style={s.quickVariant}>
                      <Text style={s.qvName}>{v.name}</Text>
                      <Text style={s.qvMetric}>{vm.impressions || 0} views</Text>
                      <Text style={[s.qvMetric, { color: T.successText }]}>{vm.upgrades || 0} upgrades</Text>
                    </View>
                  );
                })}
              </View>

              {/* Winner banner */}
              {exp.winner && (
                <View style={{ backgroundColor: colors.successSoft, borderTopWidth: 1, borderTopColor: colors.successSoft, paddingHorizontal: 16, paddingVertical: 10 }} data-testid={`winner-banner-${exp.experiment_id}`} testID={`winner-banner-${exp.experiment_id}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="trophy" size={16} color={colors.successText} />
                    <Text style={{ color: colors.successText, fontSize: 13, fontWeight: '800' }}>{tx('admin.promptAbTestingPanel.auto.text.027', 'Winner Detected')}</Text>
                    <Text style={{ color: T.textSec, fontSize: 12 }}>
                      {exp.winner.variant_name} at {exp.winner.confidence_pct}% confidence
                    </Text>
                  </View>
                  <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>
                    CTR: {exp.winner.winner_cr}% vs {exp.winner.loser_cr}% | z={exp.winner.z_score}
                  </Text>
                </View>
              )}

              {/* Actions */}
              <View style={s.expActions}>
                {exp.status === 'draft' && (
                  <TouchableOpacity style={[s.actionBtn, { borderColor: T.success }]}
                    onPress={() => handleStatusChange(exp.experiment_id, 'running')}
                    data-testid={`exp-start-${exp.experiment_id}`} testID={`exp-start-${exp.experiment_id}`}>
                    <Ionicons name="play" size={14} color={T.successText} />
                    <Text style={[s.actionText, { color: T.successText }]}>{tx('admin.promptAbTestingPanel.auto.text.028', 'Start')}</Text>
                  </TouchableOpacity>
                )}
                {exp.status === 'running' && (
                  <TouchableOpacity style={[s.actionBtn, { borderColor: T.warning }]}
                    onPress={() => handleStatusChange(exp.experiment_id, 'paused')}
                    data-testid={`exp-pause-${exp.experiment_id}`} testID={`exp-pause-${exp.experiment_id}`}>
                    <Ionicons name="pause" size={14} color={T.warningText} />
                    <Text style={[s.actionText, { color: T.warningText }]}>{tx('admin.promptAbTestingPanel.auto.text.029', 'Pause')}</Text>
                  </TouchableOpacity>
                )}
                {exp.status === 'paused' && (
                  <TouchableOpacity style={[s.actionBtn, { borderColor: T.success }]}
                    onPress={() => handleStatusChange(exp.experiment_id, 'running')}
                    data-testid={`exp-resume-${exp.experiment_id}`} testID={`exp-resume-${exp.experiment_id}`}>
                    <Ionicons name="play" size={14} color={T.successText} />
                    <Text style={[s.actionText, { color: T.successText }]}>{tx('admin.promptAbTestingPanel.auto.text.030', 'Resume')}</Text>
                  </TouchableOpacity>
                )}
                {exp.status === 'winner_detected' && (
                  <TouchableOpacity style={[s.actionBtn, { borderColor: T.success }]}
                    onPress={() => handleStatusChange(exp.experiment_id, 'running')}
                    data-testid={`exp-rerun-${exp.experiment_id}`} testID={`exp-rerun-${exp.experiment_id}`}>
                    <Ionicons name="refresh" size={14} color={T.successText} />
                    <Text style={[s.actionText, { color: T.successText }]}>{tx('admin.promptAbTestingPanel.auto.text.031', 'Re-run')}</Text>
                  </TouchableOpacity>
                )}
                {exp.status === 'winner_detected' && (
                  <TouchableOpacity style={[s.actionBtn, { borderColor: colors.primary }]}
                    onPress={() => handleRollout(exp.experiment_id)}
                    data-testid={`exp-rollout-${exp.experiment_id}`} testID={`exp-rollout-${exp.experiment_id}`}>
                    <Ionicons name="rocket" size={14} color={colors.primary} />
                    <Text style={[s.actionText, { color: colors.primary }]}>{tx('admin.promptAbTestingPanel.auto.text.032', 'Rollout Winner')}</Text>
                  </TouchableOpacity>
                )}
                {exp.status === 'rolled_out' && (
                  <TouchableOpacity style={[s.actionBtn, { borderColor: T.warning }]}
                    onPress={() => handleRevert(exp.experiment_id)}
                    data-testid={`exp-revert-${exp.experiment_id}`} testID={`exp-revert-${exp.experiment_id}`}>
                    <Ionicons name="arrow-undo" size={14} color={T.warningText} />
                    <Text style={[s.actionText, { color: T.warningText }]}>{tx('admin.promptAbTestingPanel.auto.text.033', 'Revert Rollout')}</Text>
                  </TouchableOpacity>
                )}
                {(exp.status === 'running' || exp.status === 'paused') && (
                  <TouchableOpacity style={[s.actionBtn, { borderColor: T.purple }]}
                    onPress={() => handleStatusChange(exp.experiment_id, 'completed')}
                    data-testid={`exp-complete-${exp.experiment_id}`} testID={`exp-complete-${exp.experiment_id}`}>
                    <Ionicons name="checkmark-done" size={14} color={T.purpleText} />
                    <Text style={[s.actionText, { color: T.purpleText }]}>{tx('admin.promptAbTestingPanel.auto.text.034', 'Complete')}</Text>
                  </TouchableOpacity>
                )}
                {(exp.status === 'running' || exp.status === 'paused') && (
                  <TouchableOpacity style={[s.actionBtn, { borderColor: colors.success, backgroundColor: evaluating === exp.experiment_id ? colors.successSoft : undefined }]}
                    onPress={() => handleEvaluate(exp.experiment_id)}
                    disabled={evaluating === exp.experiment_id}
                    data-testid={`exp-evaluate-${exp.experiment_id}`} testID={`exp-evaluate-${exp.experiment_id}`}>
                    {evaluating === exp.experiment_id ? (
                      <ActivityIndicator size={14} color={colors.successText} />
                    ) : (
                      <Ionicons name="analytics" size={14} color={colors.successText} />
                    )}
                    <Text style={[s.actionText, { color: colors.successText }]}>{tx('admin.promptAbTestingPanel.auto.text.035', 'Evaluate')}</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity style={[s.actionBtn, { borderColor: T.border }]}
                  onPress={() => { setEditingExp(exp); setShowForm(true); }}
                  data-testid={`exp-edit-${exp.experiment_id}`} testID={`exp-edit-${exp.experiment_id}`}>
                  <Ionicons name="create-outline" size={14} color={T.textMuted} />
                  <Text style={[s.actionText, { color: T.textMuted }]}>{tx('admin.promptAbTestingPanel.auto.text.036', 'Edit')}</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.actionBtn, { borderColor: T.danger }]}
                  onPress={() => handleDelete(exp.experiment_id)}
                  data-testid={`exp-delete-${exp.experiment_id}`} testID={`exp-delete-${exp.experiment_id}`}>
                  <Ionicons name="trash-outline" size={14} color={T.danger} />
                </TouchableOpacity>
              </View>

              {/* Expanded detail */}
              {isExpanded && detail && (
                <View style={s.detailSection}>
                  {/* Settings info */}
                  <View style={{ flexDirection: 'row', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>
                      Min Sample: {detail.min_sample_size ?? 100}/variant
                    </Text>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>
                      Confidence: {detail.confidence_threshold ?? 95}%
                    </Text>
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>
                      Traffic: {detail.traffic_pct ?? 100}%
                    </Text>
                    <Text style={{ color: T.textMuted, fontSize: 11 }} data-testid={`exp-allocation-mode-${exp.experiment_id}`} testID={`exp-allocation-mode-${exp.experiment_id}`}>
                      Allocation: {detail.traffic_allocation_mode === 'multi_armed_bandit' ? 'Multi-Armed Bandit' : 'Fixed Split'}
                    </Text>
                    {detail.traffic_allocation_mode === 'multi_armed_bandit' && (
                      <Text style={{ color: T.textMuted, fontSize: 11 }}>
                        Exploration: {Math.round((detail.exploration_rate ?? 0.15) * 100)}%
                      </Text>
                    )}
                    {detail.auto_rollout && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                        <Ionicons name="rocket" size={10} color={colors.primary} />
                        <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '600' }}>{tx('admin.promptAbTestingPanel.auto.text.037', 'Auto-Rollout')}</Text>
                      </View>
                    )}
                    {detail.status === 'rolled_out' && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.primarySoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }} data-testid="active-default-badge" testID="active-default-badge">
                        <Ionicons name="checkmark-circle" size={12} color={colors.primary} />
                        <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }}>{tx('admin.promptAbTestingPanel.auto.text.038', 'ACTIVE DEFAULT')}</Text>
                      </View>
                    )}
                    {detail.status === 'pending_rollout' && (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.warningSoft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }} data-testid="pending-rollout-badge" testID="pending-rollout-badge">
                        <Ionicons name="time" size={12} color={colors.warningText} />
                        <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }}>
                          SCHEDULED {detail.scheduled_rollout_at ? new Date(detail.scheduled_rollout_at).toLocaleDateString() : ''}
                        </Text>
                      </View>
                    )}
                  </View>
                  <Text style={s.detailTitle}>{tx('admin.promptAbTestingPanel.auto.text.039', 'Variant Performance')}</Text>
                  {detail.allocation_insights?.mode === 'multi_armed_bandit' && (detail.allocation_insights?.scoreboard || []).length > 0 && (
                    <View style={{ backgroundColor: colors.purpleSoft, borderWidth: 1, borderColor: colors.purpleSoft, borderRadius: 8, padding: 10, marginBottom: 12, gap: 6 }} data-testid={`exp-bandit-scoreboard-${exp.experiment_id}`} testID={`exp-bandit-scoreboard-${exp.experiment_id}`}>
                      <Text style={{ color: colors.purpleText, fontSize: 11, fontWeight: '700' }}>{tx('admin.promptAbTestingPanel.auto.text.040', 'Bandit Allocation Scores')}</Text>
                      {(detail.allocation_insights.scoreboard || []).slice(0, 4).map((row: any, scoreIdx: number) => (
                        <View key={`${row.variant_id}-${scoreIdx}`} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                          <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '600' }}>{row.variant_name}</Text>
                          <Text style={{ color: colors.purpleText, fontSize: 10, fontWeight: '700' }}>draw {Number(row.thompson_draw || 0).toFixed(3)}</Text>
                        </View>
                      ))}
                    </View>
                  )}
                  {(detail.variants || []).map((v: any) => (
                    <VariantRow key={v.id} variant={v} metrics={(detail.variant_metrics || {})[v.id]} winner={detail.winner} />
                  ))}
                </View>
              )}
            </View>
          );
        })
      )}

      {/* Create/Edit Modal */}
      <ExperimentFormModal visible={showForm} onClose={() => { setShowForm(false); setEditingExp(null); }} onSave={handleSave} initial={editingExp} />
    </View>
  );
}
