import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, TextInput, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

type ColorKey = 'primary' | 'accent' | 'success' | 'warning' | 'error';
const TIER_MAP: Record<string, {label: string; colorKey: ColorKey; days: number}> = {
  tier1: { label: '30d Gentle', colorKey: 'primary', days: 30 },
  tier2: { label: '60d Urgent', colorKey: 'warning', days: 60 },
  tier3: { label: '90d Win-Back', colorKey: 'error', days: 90 },
};

interface Metrics { sent: number; opened: number; clicked: number; returned: number; open_rate: number; click_rate: number; return_rate: number; }
// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface ABTest { test_id: string; name: string; tier: string; status: string; variant_a: any; variant_b: any; evaluation_days: number; created_at: string; ends_at: string; winner: string | null; confidence?: string; auto_promoted: boolean; auto_apply_winner?: boolean; start_time?: string; end_time?: string; metrics_a?: Metrics; metrics_b?: Metrics; }
interface PreviewData { html: string; subject: string; tier: string; }

const tx = (_key: string, fallback: string) => fallback;

export default function ABTestingPanel({ colors }: { colors: any }) {
  const AC = useAdminTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { data: analyticsData, loading: aLoading, refetch: fetchData } = useLiveQuery('/ab-testing/analytics', { entity: 'ab-testing', pollInterval: 60000 });
  const { data: defaultsData, loading: dLoading } = useLiveQuery('/ab-testing/defaults', { entity: 'ab-testing', pollInterval: 60000 });
  const tests = analyticsData?.tests || [];
  const summary = analyticsData?.summary || {};
  const defaults = defaultsData?.defaults || [];
  const loading = aLoading || dLoading;
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [stopping, setStopping] = useState<string | null>(null);

  // Preview modal
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewA, setPreviewA] = useState<PreviewData | null>(null);
  const [previewB, setPreviewB] = useState<PreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewTitle, setPreviewTitle] = useState('');

  // Form
  const [fName, setFName] = useState('');
  const [fTier, setFTier] = useState('tier2');
  const [fDays, setFDays] = useState('7');
  const [fASubject, setFASubject] = useState('');
  const [fACta, setFACta] = useState('');
  const [fBSubject, setFBSubject] = useState('');
  const [fBCta, setFBCta] = useState('');
  const [testMode, setTestMode] = useState<'reengagement' | 'template'>('reengagement');
  const [fTemplateType, setFTemplateType] = useState('');
  const [templateTypes, setTemplateTypes] = useState<{key: string; label: string; category: string}[]>([]);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);

  const [reverting, setReverting] = useState<string | null>(null);
  const [aiSuggesting, setAiSuggesting] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<string[]>([]);
  const [fStartTime, setFStartTime] = useState('');
  const [fEndTime, setFEndTime] = useState('');
  const [fAutoApply, setFAutoApply] = useState(true);
  const [applyingWinner, setApplyingWinner] = useState<string | null>(null);
  const panelTitle = t('abTesting.header.title');

  const resetForm = () => { setFName(''); setFTier('tier2'); setFDays('7'); setFASubject(''); setFACta(''); setFBSubject(''); setFBCta(''); setTestMode('reengagement'); setFTemplateType(''); setShowForm(false); setShowTemplatePicker(false); setAiSuggestions([]); setFStartTime(''); setFEndTime(''); setFAutoApply(true); };

  const handleAiSuggest = async () => {
    setAiSuggesting(true);
    setAiSuggestions([]);
    try {
      const res = await api.post('/ab-testing/suggest-subjects', {
        template_type: testMode === 'template' ? fTemplateType : undefined,
        current_subject: fASubject.trim() || undefined,
        count: 3,
      });
      const suggestions = res.data?.suggestions || [];
      setAiSuggestions(suggestions);
      if (suggestions.length > 0 && !fBSubject.trim()) setFBSubject(suggestions[0]);
    } catch (e) { console.error('AI suggest error:', e); }
    finally { setAiSuggesting(false); }
  };

  const handleCreate = async () => {
    if (!fName.trim() || !fASubject.trim() || !fBSubject.trim()) return;
    if (testMode === 'template' && !fTemplateType) return;
    setSaving(true);
    try {
      const payload: any = {
        name: fName.trim(), evaluation_days: parseInt(fDays) || 7,
        variant_a: { name: 'Variant A', subject_line: fASubject.trim(), cta_text: fACta.trim() || 'Get Started' },
        variant_b: { name: 'Variant B', subject_line: fBSubject.trim(), cta_text: fBCta.trim() || 'Get Started' },
        auto_apply_winner: fAutoApply,
      };
      if (fStartTime) payload.start_time = new Date(fStartTime).toISOString();
      if (fEndTime) payload.end_time = new Date(fEndTime).toISOString();
      if (testMode === 'reengagement') payload.tier = fTier;
      else payload.template_type = fTemplateType;
      await api.post('/ab-testing/tests', payload);
      resetForm(); fetchData();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ABTestingPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setSaving(false); }
  };

  const handleStop = async (testId: string) => {
    setStopping(testId);
    try { await api.post(`/ab-testing/tests/${testId}/stop`); fetchData(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ABTestingPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setStopping(null); }
  };

  const handleDelete = async (testId: string) => {
    try { await api.delete(`/ab-testing/tests/${testId}`); fetchData(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ABTestingPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const handleApplyWinner = async (testId: string) => {
    setApplyingWinner(testId);
    try { await api.post(`/ab-testing/tests/${testId}/apply-winner`); fetchData(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ABTestingPanel.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setApplyingWinner(null); }
  };

  const handleRevert = async (tier: string) => {
    setReverting(tier);
    try { await api.delete(`/ab-testing/defaults/${tier}`); fetchData(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/ABTestingPanel.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setReverting(null); }
  };

  const confColor = (c?: string) => c === 'high' ? 'var(--app-success)' : c === 'medium' ? 'var(--app-warning)' : c === 'low' ? 'var(--app-error)' : AC.textMuted;

  const openPreview = async (tier: string, variantA: any, variantB: any, title: string, templateType?: string) => {
    setPreviewLoading(true);
    setPreviewTitle(title);
    setPreviewVisible(true);
    setPreviewA(null);
    setPreviewB(null);
    try {
      const params = (v: any) => templateType
        ? { template_type: templateType, subject_line: v?.subject_line || '', cta_text: v?.cta_text || '' }
        : { tier, subject_line: v?.subject_line || '', cta_text: v?.cta_text || '' };
      const [resA, resB] = await Promise.all([
        api.get('/ab-testing/preview', { params: params(variantA) }),
        api.get('/ab-testing/preview', { params: params(variantB) }),
      ]);
      setPreviewA(resA.data);
      setPreviewB(resB.data);
    } catch (e) { console.error('Preview error:', e); }
    finally { setPreviewLoading(false); }
  };

  const openSinglePreview = async (tier: string, variant: any, label: string, templateType?: string) => {
    setPreviewLoading(true);
    setPreviewTitle(`${label} Preview`);
    setPreviewVisible(true);
    setPreviewA(null);
    setPreviewB(null);
    try {
      const params = templateType
        ? { template_type: templateType, subject_line: variant?.subject_line || '', cta_text: variant?.cta_text || '' }
        : { tier, subject_line: variant?.subject_line || '', cta_text: variant?.cta_text || '' };
      const res = await api.get('/ab-testing/preview', { params });
      setPreviewA(res.data);
    } catch (e) { console.error('Preview error:', e); }
    finally { setPreviewLoading(false); }
  };

  // Fetch template types catalog
  React.useEffect(() => {
    if (testMode === 'template' && templateTypes.length === 0) {
      api.get('/email-notifications/catalog').then(res => {
        setTemplateTypes(res.data || []);
      }).catch(() => {});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testMode]);

  if (loading) return <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 60 }}><ActivityIndicator size="large" color={colors.primary} /><Text style={{ color: AC.textMuted, fontSize: 13, marginTop: 12 }}>{tx('abTesting.states.loading', 'Loading A/B tests...')}</Text></View>;

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, paddingBottom: 40 }} data-testid="ab-testing-panel" testID="ab-testing-panel">
      <AutoFixBanner domain="ab_testing" />
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 10 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: colors.text, letterSpacing: -0.4 }}>{panelTitle === 'abTesting.header.title' ? 'Email A/B Testing' : panelTitle}</Text>
          <Text style={{ fontSize: 12, color: AC.textMuted, marginTop: 2 }}>{tx('abTesting.header.subtitle', 'Test subject lines, CTAs, and optimize engagement')}</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity onPress={fetchData} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }} data-testid="ab-refresh-btn" testID="ab-refresh-btn">
            <Ionicons name="refresh" size={12} color={'var(--app-success)'} /><Text style={{ fontSize: 11, fontWeight: '700', color: colors.successText }}>{tx('abTesting.actions.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { resetForm(); setShowForm(true); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.primary }} data-testid="ab-new-test-btn" testID="ab-new-test-btn">
            <Ionicons name="add" size={14} color={colors.primaryText} /><Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>{tx('abTesting.actions.newTest', 'New Test')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Summary Cards */}
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        {[
          { label: tx('abTesting.stats.totalTests', 'Total Tests'), value: summary.total_tests || 0, color: colors.primary, icon: 'flask' },
          { label: tx('abTesting.stats.active', 'Active'), value: summary.active || 0, color: colors.successText, icon: 'pulse' },
          { label: tx('abTesting.stats.completed', 'Completed'), value: summary.completed || 0, color: colors.accent, icon: 'checkmark-done' },
          { label: tx('abTesting.stats.totalSends', 'Total Sends'), value: summary.total_sends || 0, color: colors.warningText, icon: 'mail' },
        ].map(s => (
          <View key={s.label} style={{ flex: 1, minWidth: 130, padding: 14, borderRadius: 14, backgroundColor: (globalThis as any).__alphaColor(s.color, '08'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.color, '20') }} data-testid={`ab-stat-${s.label.toLowerCase().replace(/ /g, '-')}`} testID={`ab-stat-${s.label.toLowerCase().replace(/ /g, '-')}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <View style={{ width: 26, height: 26, borderRadius: 7, backgroundColor: (globalThis as any).__alphaColor(s.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={s.icon as any} size={13} color={s.color} />
              </View>
              <Text style={{ fontSize: 9, fontWeight: '700', color: AC.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 }}>{s.label}</Text>
            </View>
            <Text style={{ fontSize: 24, fontWeight: '900', color: s.color }}>{s.value}</Text>
          </View>
        ))}
      </View>

      {/* Promoted Defaults */}
      {defaults.length > 0 && (
        <View style={{ marginBottom: 20, padding: 16, borderRadius: 14, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft }} data-testid="ab-promoted-defaults" testID="ab-promoted-defaults">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="trophy" size={14} color={'var(--app-success)'} />
            </View>
            <View>
              <Text style={{ fontSize: 13, fontWeight: '800', color: colors.successText }}>{tx('admin.aBTestingPanel.auto.text.001', 'Active Promoted Defaults')}</Text>
              <Text style={{ fontSize: 10, color: AC.textMuted }}>{tx('admin.aBTestingPanel.auto.text.002', 'Winning variants automatically applied to emails')}</Text>
            </View>
          </View>
          {defaults.map((d: any) => {
            const tierInfo = TIER_MAP[d.tier] || { label: d.tier, colorKey: 'primary' as ColorKey };
            const tierColor = colors[tierInfo.colorKey] || AC.textMuted;
            return (
              <View key={d.tier} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderRadius: 10, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, marginBottom: 6 }}
                data-testid={`ab-default-${d.tier}`} testID={`ab-default-${d.tier}`}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: tierColor }} />
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <Text style={{ fontSize: 11, fontWeight: '800', color: tierColor }}>{tierInfo.label}</Text>
                    <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: colors.successSoft }}>
                      <Text style={{ fontSize: 8, fontWeight: '800', color: colors.successText }}>{tx('admin.aBTestingPanel.auto.text.003', 'PROMOTED')}</Text>
                    </View>
                    {d.test_name && <Text style={{ fontSize: 9, color: AC.textMuted }}>from: {d.test_name}</Text>}
                  </View>
                  <Text style={{ fontSize: 11, color: colors.text }} numberOfLines={1}>Subject: {d.subject_line}</Text>
                  {d.cta_text && <Text style={{ fontSize: 10, color: AC.textMuted }}>CTA: {d.cta_text}</Text>}
                </View>
                <View style={{ flexDirection: 'row', gap: 6 }}>
                  <TouchableOpacity onPress={() => openSinglePreview(d.tier, d, `Promoted: ${tierInfo.label}`)}
                    style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.accentSoft }}
                    data-testid={`ab-default-preview-${d.tier}`} testID={`ab-default-preview-${d.tier}`}>
                    <Ionicons name="eye" size={12} color={'var(--app-primary)'} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleRevert(d.tier)} disabled={reverting === d.tier}
                    style={{ paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, backgroundColor: colors.errorSoft, opacity: reverting === d.tier ? 0.5 : 1 }}
                    data-testid={`ab-default-revert-${d.tier}`} testID={`ab-default-revert-${d.tier}`}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: colors.error }}>{reverting === d.tier ? '...' : 'Revert'}</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
        </View>
      )}

      {/* Create Form */}
      {showForm && (
        <View style={{ marginBottom: 20, padding: 20, borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }} data-testid="ab-create-form" testID="ab-create-form">
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>{tx('admin.aBTestingPanel.auto.text.004', 'Create A/B Test')}</Text>
            <TouchableOpacity onPress={resetForm}  accessibilityLabel={tx('admin.aBTestingPanel.auto.accessibility.001', 'Test Name')}><Ionicons name="close-circle" size={22} color={AC.textMuted} /></TouchableOpacity>
          </View>
          <Text style={{ fontSize: 11, fontWeight: '700', color: AC.textMuted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.aBTestingPanel.auto.text.005', 'Test Name')}</Text>
          <TextInput value={fName} onChangeText={setFName} placeholder={tx('admin.aBTestingPanel.auto.placeholder.001', 'e.g. Subject Line Test - Tier 2')}
            placeholderTextColor={AC.textMuted + '80'}
            style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 10, padding: 12, fontSize: 13, color: AC.text, marginBottom: 14 }}
            data-testid="ab-form-name" testID="ab-form-name" />

          <View style={{ flexDirection: 'row', gap: 14, marginBottom: 14 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: AC.textMuted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.aBTestingPanel.auto.text.006', 'Target')}</Text>
              <View style={{ flexDirection: 'row', gap: 6, marginBottom: 10 }}>
                {[{ id: 'reengagement', label: 'Re-engagement', color: colors.warningText }, { id: 'template', label: 'Email Template', color: colors.accent }].map(m => (
                  <TouchableOpacity key={m.id} onPress={() => { setTestMode(m.id as any); setFTemplateType(''); }}
                    style={{ flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center', backgroundColor: testMode === m.id ? (globalThis as any).__alphaColor(m.color, '18') : 'transparent', borderWidth: 1, borderColor: testMode === m.id ? (globalThis as any).__alphaColor(m.color, '40') : AC.border }}
                    data-testid={`ab-form-mode-${m.id}`} testID={`ab-form-mode-${m.id}`}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: testMode === m.id ? m.color : AC.textMuted }}>{m.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              {testMode === 'reengagement' ? (
                <View style={{ flexDirection: 'row', gap: 6 }}>
                {Object.entries(TIER_MAP).map(([id, t]) => {
                  const tColor = colors[t.colorKey] || colors.primary;
                  return (
                    <TouchableOpacity key={id} onPress={() => setFTier(id)} style={{
                      flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center',
                      backgroundColor: fTier === id ? (globalThis as any).__alphaColor(tColor, '18') : 'transparent', borderWidth: 1, borderColor: fTier === id ? (globalThis as any).__alphaColor(tColor, '40') : AC.border,
                    }} data-testid={`ab-form-tier-${id}`} testID={`ab-form-tier-${id}`}>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: fTier === id ? tColor : AC.textMuted }}>{t.label}</Text>
                    </TouchableOpacity>
                  );
                })}
                </View>
              ) : (
                <View>
                  <TouchableOpacity onPress={() => setShowTemplatePicker(!showTemplatePicker)}
                    style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: colors.background, borderWidth: 1, borderColor: fTemplateType ? 'var(--app-primary-soft)' : AC.border, borderRadius: 10, padding: 12 }}
                    data-testid="ab-form-template-picker" testID="ab-form-template-picker">
                    <Text style={{ fontSize: 12, color: fTemplateType ? AC.text : AC.textMuted + '80' }}>
                      {fTemplateType ? templateTypes.find(t => t.key === fTemplateType)?.label || fTemplateType : 'Select email template...'}
                    </Text>
                    <Ionicons name={showTemplatePicker ? 'chevron-up' : 'chevron-down'} size={14} color={AC.textMuted} />
                  </TouchableOpacity>
                  {showTemplatePicker && (
                    <ScrollView style={{ maxHeight: 200, marginTop: 6, backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 10 }}>
                      {Object.entries(templateTypes.reduce((acc: Record<string, typeof templateTypes>, t) => { (acc[t.category] = acc[t.category] || []).push(t); return acc; }, {})).map(([cat, items]) => (
                        <View key={cat}>
                          <Text style={{ fontSize: 9, fontWeight: '800', color: AC.textMuted, padding: 8, paddingBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>{cat}</Text>
                          {items.map((t: any) => (
                            <TouchableOpacity key={t.key} onPress={() => { setFTemplateType(t.key); setShowTemplatePicker(false); }}
                              style={{ paddingVertical: 8, paddingHorizontal: 12, backgroundColor: fTemplateType === t.key ? 'var(--app-primary-soft)' : 'transparent' }}
                              data-testid={`ab-form-template-${t.key}`} testID={`ab-form-template-${t.key}`}>
                              <Text style={{ fontSize: 12, color: fTemplateType === t.key ? 'var(--app-primary)' : AC.text }}>{t.label}</Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                      ))}
                    </ScrollView>
                  )}
                </View>
              )}
            </View>
            <View style={{ width: 100 }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: AC.textMuted, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.aBTestingPanel.auto.text.007', 'Days')}</Text>
              <TextInput value={fDays} onChangeText={setFDays} keyboardType="numeric" accessibilityLabel={tx('admin.aBTestingPanel.auto.accessibility.002', 'Text input')}
                style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 10, padding: 12, fontSize: 13, color: AC.text, textAlign: 'center' }}
                data-testid="ab-form-days" testID="ab-form-days" />
            </View>
          </View>

          {/* Scheduling */}
          <View style={{ marginBottom: 14, padding: 14, borderRadius: 12, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
              <Ionicons name="calendar" size={14} color={'var(--app-primary)'} />
              <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primary }}>{tx('admin.aBTestingPanel.auto.text.008', 'SCHEDULING (Optional)')}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <View style={{ flex: 1, minWidth: 180 }}>
                <Text style={{ fontSize: 10, fontWeight: '700', color: AC.textMuted, marginBottom: 4 }}>{tx('admin.aBTestingPanel.auto.text.009', 'Start Date')}</Text>
                {Platform.OS === 'web' ? (
                  <input type="datetime-local" value={fStartTime} aria-label="YYYY-MM-DDTHH:MM"
                    onChange={(e: any) => setFStartTime(e.target.value)}
                    style={{ backgroundColor: AC.surface, border: `1px solid ${AC.border}`, borderRadius: 8, padding: 10, fontSize: 12, color: AC.text, width: '100%' }}
                    data-testid="ab-form-start-time"
                  />
                ) : (
                  <TextInput value={fStartTime} onChangeText={setFStartTime} placeholder={tx('admin.aBTestingPanel.auto.placeholder.002', 'YYYY-MM-DDTHH:MM')}
                    placeholderTextColor={AC.textMuted + '80'}
                    style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, fontSize: 12, color: AC.text }}
                    data-testid="ab-form-start-time" testID="ab-form-start-time" />
                )}
              </View>
              <View style={{ flex: 1, minWidth: 180 }}>
                <Text style={{ fontSize: 10, fontWeight: '700', color: AC.textMuted, marginBottom: 4 }}>{tx('admin.aBTestingPanel.auto.text.010', 'End Date')}</Text>
                {Platform.OS === 'web' ? (
                  <input type="datetime-local" value={fEndTime} aria-label="YYYY-MM-DDTHH:MM"
                    onChange={(e: any) => setFEndTime(e.target.value)}
                    style={{ backgroundColor: AC.surface, border: `1px solid ${AC.border}`, borderRadius: 8, padding: 10, fontSize: 12, color: AC.text, width: '100%' }}
                    data-testid="ab-form-end-time"
                  />
                ) : (
                  <TextInput value={fEndTime} onChangeText={setFEndTime} placeholder={tx('admin.aBTestingPanel.auto.placeholder.003', 'YYYY-MM-DDTHH:MM')}
                    placeholderTextColor={AC.textMuted + '80'}
                    style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, fontSize: 12, color: AC.text }}
                    data-testid="ab-form-end-time" testID="ab-form-end-time" />
                )}
              </View>
            </View>
            <Text style={{ fontSize: 9, color: AC.textMuted, marginTop: 6 }}>{tx('admin.aBTestingPanel.auto.text.011', 'Leave empty to start immediately. End date overrides evaluation days if set.')}</Text>
          </View>

          {/* Auto-Apply Winner Toggle */}
          <TouchableOpacity onPress={() => setFAutoApply(!fAutoApply)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14, padding: 12, borderRadius: 10, backgroundColor: fAutoApply ? 'var(--app-success-soft)' : colors.background, borderWidth: 1, borderColor: fAutoApply ? 'var(--app-success-soft)' : AC.border }}
            data-testid="ab-form-auto-apply-toggle" testID="ab-form-auto-apply-toggle">
            <View style={{ width: 20, height: 20, borderRadius: 4, backgroundColor: fAutoApply ? 'var(--app-success)' : 'transparent', borderWidth: 1.5, borderColor: fAutoApply ? 'var(--app-success)' : AC.border, alignItems: 'center', justifyContent: 'center' }}>
              {fAutoApply && <Ionicons name="checkmark" size={12} color={AC.primaryText} />}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: fAutoApply ? 'var(--app-success)' : AC.text }}>{tx('admin.aBTestingPanel.auto.text.012', 'Auto-Apply Winner')}</Text>
              <Text style={{ fontSize: 9, color: AC.textMuted }}>{tx('admin.aBTestingPanel.auto.text.013', 'Automatically promote the winning variant as the default email template when the test completes with high confidence')}</Text>
            </View>
          </TouchableOpacity>

          {/* Variant A */}
          <View style={{ marginBottom: 14, padding: 14, borderRadius: 12, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primarySoft }}>
            <Text style={{ fontSize: 12, fontWeight: '800', color: colors.primary, marginBottom: 10 }}>{tx('admin.aBTestingPanel.auto.text.014', 'VARIANT A')}</Text>
            <TextInput value={fASubject} onChangeText={setFASubject} placeholder={tx('admin.aBTestingPanel.auto.placeholder.004', 'Subject line...')}
              placeholderTextColor={AC.textMuted + '80'}
              style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, fontSize: 12, color: AC.text, marginBottom: 8 }}
              data-testid="ab-form-a-subject" testID="ab-form-a-subject" />
            <TextInput value={fACta} onChangeText={setFACta} placeholder={tx('admin.aBTestingPanel.auto.placeholder.005', 'CTA button text (optional)')}
              placeholderTextColor={AC.textMuted + '80'}
              style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, fontSize: 12, color: AC.text }}
              data-testid="ab-form-a-cta" testID="ab-form-a-cta" />
          </View>

          {/* Variant B */}
          <View style={{ marginBottom: 16, padding: 14, borderRadius: 12, backgroundColor: colors.warningSoft, borderWidth: 1, borderColor: colors.warningSoft }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text style={{ fontSize: 12, fontWeight: '800', color: colors.warningText }}>{tx('admin.aBTestingPanel.auto.text.015', 'VARIANT B')}</Text>
              <TouchableOpacity onPress={handleAiSuggest} disabled={aiSuggesting}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accentSoft, opacity: aiSuggesting ? 0.5 : 1 }}
                data-testid="ab-form-ai-suggest-btn" testID="ab-form-ai-suggest-btn">
                {aiSuggesting ? <ActivityIndicator size="small" color={'var(--app-primary)'} /> : <Ionicons name="sparkles" size={12} color={'var(--app-primary)'} />}
                <Text style={{ fontSize: 10, fontWeight: '700', color: colors.accent }}>{aiSuggesting ? 'Generating...' : 'AI Suggest'}</Text>
              </TouchableOpacity>
            </View>
            {aiSuggestions.length > 0 && (
              <View style={{ marginBottom: 10, gap: 4 }}>
                {aiSuggestions.map((s, i) => (
                  <TouchableOpacity key={i} onPress={() => setFBSubject(s)}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 8, borderRadius: 8, backgroundColor: fBSubject === s ? 'var(--app-primary-soft)' : colors.background, borderWidth: 1, borderColor: fBSubject === s ? 'var(--app-primary-soft)' : AC.border }}
                    data-testid={`ab-form-ai-suggestion-${i}`} testID={`ab-form-ai-suggestion-${i}`}>
                    <View style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: fBSubject === s ? 'var(--app-primary)' : 'transparent', borderWidth: 1.5, borderColor: fBSubject === s ? 'var(--app-primary)' : AC.border, alignItems: 'center', justifyContent: 'center' }}>
                      {fBSubject === s && <Ionicons name="checkmark" size={10} color={AC.primaryText} />}
                    </View>
                    <Text style={{ fontSize: 11, color: fBSubject === s ? 'var(--app-primary)' : AC.text, flex: 1 }}>{s}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
            <TextInput value={fBSubject} onChangeText={setFBSubject} placeholder={tx('admin.aBTestingPanel.auto.placeholder.006', 'Subject line...')}
              placeholderTextColor={AC.textMuted + '80'}
              style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, fontSize: 12, color: AC.text, marginBottom: 8 }}
              data-testid="ab-form-b-subject" testID="ab-form-b-subject" />
            <TextInput value={fBCta} onChangeText={setFBCta} placeholder={tx('admin.aBTestingPanel.auto.placeholder.007', 'CTA button text (optional)')}
              placeholderTextColor={AC.textMuted + '80'}
              style={{ backgroundColor: colors.background, borderWidth: 1, borderColor: AC.border, borderRadius: 8, padding: 10, fontSize: 12, color: AC.text }}
              data-testid="ab-form-b-cta" testID="ab-form-b-cta" />
          </View>

          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={() => openPreview(fTier, { subject_line: fASubject, cta_text: fACta }, { subject_line: fBSubject, cta_text: fBCta }, 'Preview: ' + (fName || 'New Test'), testMode === 'template' ? fTemplateType : undefined)}
              disabled={(!fASubject.trim() && !fBSubject.trim()) || (testMode === 'template' && !fTemplateType)}
              style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accentSoft, opacity: (!fASubject.trim() && !fBSubject.trim()) || (testMode === 'template' && !fTemplateType) ? 0.4 : 1 }}
              data-testid="ab-form-preview-btn" testID="ab-form-preview-btn">
              <Ionicons name="eye" size={16} color={'var(--app-primary)'} />
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.accent }}>{tx('admin.aBTestingPanel.auto.text.016', 'Preview Emails')}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={handleCreate} disabled={saving || !fName.trim() || !fASubject.trim() || !fBSubject.trim() || (testMode === 'template' && !fTemplateType)}
              style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 10, backgroundColor: colors.primary, opacity: saving || !fName.trim() || !fASubject.trim() || !fBSubject.trim() || (testMode === 'template' && !fTemplateType) ? 0.5 : 1 }}
              data-testid="ab-form-save-btn" testID="ab-form-save-btn">
              {saving ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="flask" size={16} color={colors.primaryText} />}
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>{tx('admin.aBTestingPanel.auto.text.017', 'Launch A/B Test')}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Tests List */}
      {tests.length === 0 ? (
        <View style={{ padding: 40, alignItems: 'center', backgroundColor: colors.card, borderRadius: 16, borderWidth: 1, borderColor: colors.border }}>
          <Ionicons name="flask-outline" size={40} color={AC.textMuted} />
          <Text style={{ fontSize: 14, fontWeight: '600', color: AC.textMuted, marginTop: 10 }}>{tx('admin.aBTestingPanel.auto.text.018', 'No A/B tests yet')}</Text>
          <Text style={{ fontSize: 12, color: AC.textMuted, marginTop: 4, textAlign: 'center' }}>{tx('admin.aBTestingPanel.auto.text.019', 'Create your first test to optimize email engagement')}</Text>
        </View>
      ) : (
        <View style={{ gap: 14 }}>
          {tests.map(test => {
            const tier = TIER_MAP[test.tier] || { label: test.template_type || test.tier || 'N/A', colorKey: 'accent' as ColorKey, days: 0 };
            const tierColor = colors[tier.colorKey] || colors.accent;
            const isTemplate = !!test.template_type;
            const targetLabel = isTemplate ? (test.template_type || '').replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()) : tier.label;
            const targetColor = isTemplate ? colors.accent : tierColor;
            const mA = test.metrics_a || {} as Metrics;
            const mB = test.metrics_b || {} as Metrics;
            const isActive = test.status === 'active';
            const isScheduled = test.status === 'scheduled';
            const isCompleted = test.status === 'completed';
            const maxRate = Math.max(mA.return_rate || 0, mB.return_rate || 0, 1);
            const statusColor = isScheduled ? 'var(--app-primary)' : isActive ? 'var(--app-success)' : 'var(--app-primary)';

            return (
              <View key={test.test_id} style={{
                padding: 20, borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
                borderLeftWidth: 4, borderLeftColor: statusColor,
              }} data-testid={`ab-test-${test.test_id}`} testID={`ab-test-${test.test_id}`}>
                {/* Test Header */}
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
                      <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>{test.name}</Text>
                      <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(statusColor, '15') }}>
                        <Text style={{ fontSize: 9, fontWeight: '800', color: statusColor }}>{test.status.toUpperCase()}</Text>
                      </View>
                      <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(targetColor, '15') }}>
                        <Text style={{ fontSize: 9, fontWeight: '800', color: targetColor }}>{isTemplate ? 'TEMPLATE' : ''} {targetLabel}</Text>
                      </View>
                      {test.winner && (
                        <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, backgroundColor: colors.warningSoft }}>
                          <Text style={{ fontSize: 9, fontWeight: '800', color: colors.warningText }}>WINNER: {test.winner.toUpperCase()}</Text>
                        </View>
                      )}
                      {test.confidence && (
                        <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(confColor(test.confidence), '15') }}>
                          <Text style={{ fontSize: 8, fontWeight: '700', color: confColor(test.confidence) }}>{test.confidence}</Text>
                        </View>
                      )}
                      {test.auto_promoted && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 7, paddingVertical: 2, borderRadius: 5, backgroundColor: colors.successSoft }}
                          data-testid={`ab-promoted-badge-${test.test_id}`} testID={`ab-promoted-badge-${test.test_id}`}>
                          <Ionicons name="trophy" size={8} color={'var(--app-success)'} />
                          <Text style={{ fontSize: 8, fontWeight: '800', color: colors.successText }}>{tx('admin.aBTestingPanel.auto.text.020', 'PROMOTED')}</Text>
                        </View>
                      )}
                    </View>
                    <Text style={{ fontSize: 10, color: AC.textMuted }}>
                      Created {new Date(test.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                      {' \u2022 '}{test.evaluation_days}d evaluation
                      {test.ends_at && ` \u2022 Ends ${new Date(test.ends_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`}
                      {test.start_time && ` \u2022 Starts ${new Date(test.start_time).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                    </Text>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 6 }}>
                    <TouchableOpacity onPress={() => openPreview(test.tier, test.variant_a, test.variant_b, test.name)}
                      style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accentSoft }}
                      data-testid={`ab-compare-${test.test_id}`} testID={`ab-compare-${test.test_id}`}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                        <Ionicons name="eye" size={12} color={'var(--app-primary)'} />
                        <Text style={{ fontSize: 10, fontWeight: '700', color: colors.accent }}>{tx('admin.aBTestingPanel.auto.text.021', 'Compare')}</Text>
                      </View>
                    </TouchableOpacity>
                    {isActive && (
                      <TouchableOpacity onPress={() => handleStop(test.test_id)} disabled={stopping === test.test_id}
                        style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.warningSoft, borderWidth: 1, borderColor: colors.warningSoft, opacity: stopping === test.test_id ? 0.5 : 1 }}
                        data-testid={`ab-stop-${test.test_id}`} testID={`ab-stop-${test.test_id}`}>
                        <Text style={{ fontSize: 10, fontWeight: '700', color: colors.warningText }}>{tx('admin.aBTestingPanel.auto.text.022', 'End & Evaluate')}</Text>
                      </TouchableOpacity>
                    )}
                    {isCompleted && test.winner && !test.auto_promoted && (
                      <TouchableOpacity onPress={() => handleApplyWinner(test.test_id)} disabled={applyingWinner === test.test_id}
                        style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: colors.successSoft, opacity: applyingWinner === test.test_id ? 0.5 : 1 }}
                        data-testid={`ab-apply-winner-${test.test_id}`} testID={`ab-apply-winner-${test.test_id}`}>
                        <Ionicons name="trophy" size={10} color={'var(--app-success)'} />
                        <Text style={{ fontSize: 10, fontWeight: '700', color: colors.successText }}>{tx('admin.aBTestingPanel.auto.text.023', 'Apply Winner')}</Text>
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity onPress={() => handleDelete(test.test_id)}
                      style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: colors.errorSoft }}
                      data-testid={`ab-delete-${test.test_id}`} testID={`ab-delete-${test.test_id}`}>
                      <Ionicons name="trash" size={12} color={'var(--app-error)'} />
                    </TouchableOpacity>
                  </View>
                </View>

                {/* Variant Comparison */}
                <View style={{ flexDirection: 'row', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
                  {[
                    { key: 'a', label: 'Variant A', color: colors.primary, variant: test.variant_a, metrics: mA },
                    { key: 'b', label: 'Variant B', color: colors.warningText, variant: test.variant_b, metrics: mB },
                  ].map(v => (
                    <View key={v.key} style={{
                      flex: 1, minWidth: 200, padding: 14, borderRadius: 12,
                      backgroundColor: (globalThis as any).__alphaColor(v.color, '06'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(v.color, '20'),
                      ...(test.winner === v.key ? { borderWidth: 2, borderColor: (globalThis as any).__alphaColor(v.color, '60') } : {}),
                    }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                        <View style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: v.color, alignItems: 'center', justifyContent: 'center' }}>
                          <Text style={{ fontSize: 10, fontWeight: '900', color: colors.primaryText }}>{v.key.toUpperCase()}</Text>
                        </View>
                        <Text style={{ fontSize: 11, fontWeight: '700', color: v.color }}>{v.label}</Text>
                        {test.winner === v.key && <Ionicons name="trophy" size={12} color={'var(--app-warning)'} />}
                        <TouchableOpacity onPress={() => openSinglePreview(test.tier, v.variant, v.label)}
                          style={{ marginLeft: 'auto', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 5, backgroundColor: (globalThis as any).__alphaColor(v.color, '10') }}
                          data-testid={`ab-preview-${test.test_id}-${v.key}`} testID={`ab-preview-${test.test_id}-${v.key}`}>
                          <Text style={{ fontSize: 9, fontWeight: '700', color: v.color }}>{tx('admin.aBTestingPanel.auto.text.024', 'Preview')}</Text>
                        </TouchableOpacity>
                      </View>
                      <Text style={{ fontSize: 11, fontWeight: '600', color: colors.text, marginBottom: 2 }} numberOfLines={2}>{v.variant?.subject_line}</Text>
                      {v.variant?.cta_text && <Text style={{ fontSize: 10, color: AC.textMuted }}>CTA: {v.variant.cta_text}</Text>}

                      {/* Metrics */}
                      <View style={{ marginTop: 10, gap: 6 }}>
                        {[
                          { label: 'Sent', value: v.metrics.sent || 0, rate: null },
                          { label: 'Open Rate', value: v.metrics.opened || 0, rate: v.metrics.open_rate || 0 },
                          { label: 'Click Rate', value: v.metrics.clicked || 0, rate: v.metrics.click_rate || 0 },
                          { label: 'Return Rate', value: v.metrics.returned || 0, rate: v.metrics.return_rate || 0 },
                        ].map(m => (
                          <View key={m.label}>
                            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
                              <Text style={{ fontSize: 10, color: AC.textMuted }}>{m.label}</Text>
                              <Text style={{ fontSize: 10, fontWeight: '700', color: colors.text }}>
                                {m.rate !== null ? `${m.value} (${m.rate}%)` : m.value}
                              </Text>
                            </View>
                            {m.rate !== null && (
                              <View style={{ height: 4, borderRadius: 2, backgroundColor: colors.border, overflow: 'hidden' }}>
                                <View style={{ height: '100%' as any, width: `${Math.min(m.rate, 100)}%` as any, borderRadius: 2, backgroundColor: v.color }} />
                              </View>
                            )}
                          </View>
                        ))}
                      </View>
                    </View>
                  ))}
                </View>

                {/* Visual Comparison Bar */}
                {((mA.sent || 0) + (mB.sent || 0) > 0) && (
                  <View style={{ padding: 12, borderRadius: 10, backgroundColor: colors.background, borderWidth: 1, borderColor: colors.border }}>
                    <Text style={{ fontSize: 10, fontWeight: '700', color: AC.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.aBTestingPanel.auto.text.025', 'Return Rate Comparison')}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: colors.primary, width: 16 }}>A</Text>
                      <View style={{ flex: 1, height: 18, borderRadius: 4, backgroundColor: colors.border, overflow: 'hidden' }}>
                        <View style={{ height: '100%' as any, width: `${Math.min(maxRate > 0 ? (mA.return_rate || 0) / maxRate * 100 : 0, 100)}%` as any, backgroundColor: colors.primary, borderRadius: 4, alignItems: 'center', justifyContent: 'center' }}>
                          {(mA.return_rate || 0) > 10 && <Text style={{ fontSize: 8, fontWeight: '800', color: colors.primaryText }}>{mA.return_rate}%</Text>}
                        </View>
                      </View>
                      <Text style={{ fontSize: 11, fontWeight: '800', color: colors.primary, width: 40, textAlign: 'right' }}>{mA.return_rate || 0}%</Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 }}>
                      <Text style={{ fontSize: 10, fontWeight: '700', color: colors.warningText, width: 16 }}>B</Text>
                      <View style={{ flex: 1, height: 18, borderRadius: 4, backgroundColor: colors.border, overflow: 'hidden' }}>
                        <View style={{ height: '100%' as any, width: `${Math.min(maxRate > 0 ? (mB.return_rate || 0) / maxRate * 100 : 0, 100)}%` as any, backgroundColor: colors.warning, borderRadius: 4, alignItems: 'center', justifyContent: 'center' }}>
                          {(mB.return_rate || 0) > 10 && <Text style={{ fontSize: 8, fontWeight: '800', color: colors.primaryText }}>{mB.return_rate}%</Text>}
                        </View>
                      </View>
                      <Text style={{ fontSize: 11, fontWeight: '800', color: colors.warningText, width: 40, textAlign: 'right' }}>{mB.return_rate || 0}%</Text>
                    </View>
                  </View>
                )}
              </View>
            );
          })}
        </View>
      )}
      {/* Preview Modal */}
      {previewVisible && Platform.OS === 'web' && (
        <View style={{
          position: 'fixed' as any, top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: colors.overlay, zIndex: 9999,
          justifyContent: 'center', alignItems: 'center', padding: 20,
        }} data-testid="ab-preview-modal" testID="ab-preview-modal">
          <View style={{
            width: '100%', maxWidth: previewB ? 1100 : 600, maxHeight: '90vh' as any,
            backgroundColor: colors.card, borderRadius: 20, overflow: 'hidden',
            borderWidth: 1, borderColor: colors.border,
          }}>
            {/* Modal Header */}
            <View style={{
              flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
              padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border,
              backgroundColor: colors.surfaceElevated,
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="eye" size={16} color={'var(--app-primary)'} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 15, fontWeight: '800', color: colors.text }} numberOfLines={1}>{previewTitle}</Text>
                  <Text style={{ fontSize: 11, color: AC.textMuted }}>
                    {previewB ? 'Side-by-side variant comparison' : 'Email template preview'}
                  </Text>
                </View>
              </View>
              <TouchableOpacity onPress={() => setPreviewVisible(false)}
                style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}
                data-testid="ab-preview-close" testID="ab-preview-close">
                <Ionicons name="close" size={18} color={'var(--app-error)'} />
              </TouchableOpacity>
            </View>

            {/* Modal Body */}
            {previewLoading ? (
              <View style={{ padding: 60, alignItems: 'center', justifyContent: 'center' }}>
                <ActivityIndicator size="large" color={'var(--app-primary)'} />
                <Text style={{ fontSize: 13, color: AC.textMuted, marginTop: 12 }}>{tx('admin.aBTestingPanel.auto.text.026', 'Rendering email previews...')}</Text>
              </View>
            ) : (
              <ScrollView style={{ flex: 1, maxHeight: 'calc(90vh - 80px)' as any }} contentContainerStyle={{ padding: 16 }}>
                <View style={{ flexDirection: previewB ? 'row' : 'column', gap: 16, flexWrap: 'wrap' as any }}>
                  {/* Variant A Preview */}
                  {previewA && (
                    <View style={{ flex: 1, minWidth: 280 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                        <View style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' }}>
                          <Text style={{ fontSize: 10, fontWeight: '900', color: colors.primaryText }}>A</Text>
                        </View>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primary }}>{tx('admin.aBTestingPanel.auto.text.027', 'Variant A')}</Text>
                      </View>
                      <View style={{ padding: 10, borderRadius: 10, backgroundColor: colors.surfaceHover, marginBottom: 8, borderWidth: 1, borderColor: colors.primarySoft }}>
                        <Text style={{ fontSize: 10, fontWeight: '600', color: AC.textMuted }}>{tx('admin.aBTestingPanel.auto.text.028', 'Subject:')}</Text>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text, marginTop: 2 }}>{previewA.subject}</Text>
                      </View>
                      <View style={{ borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}>
                        <iframe
                          srcDoc={previewA.html}
                          style={{ width: '100%', height: 480, border: 'none' } as any}
                          title="Variant A Preview"
                          sandbox="allow-same-origin"
                          data-testid="ab-preview-iframe-a"
                        />
                      </View>
                    </View>
                  )}

                  {/* Variant B Preview */}
                  {previewB && (
                    <View style={{ flex: 1, minWidth: 280 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                        <View style={{ width: 22, height: 22, borderRadius: 6, backgroundColor: colors.warning, alignItems: 'center', justifyContent: 'center' }}>
                          <Text style={{ fontSize: 10, fontWeight: '900', color: colors.primaryText }}>B</Text>
                        </View>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: colors.warningText }}>{tx('admin.aBTestingPanel.auto.text.029', 'Variant B')}</Text>
                      </View>
                      <View style={{ padding: 10, borderRadius: 10, backgroundColor: colors.surfaceHover, marginBottom: 8, borderWidth: 1, borderColor: colors.warningSoft }}>
                        <Text style={{ fontSize: 10, fontWeight: '600', color: AC.textMuted }}>{tx('admin.aBTestingPanel.auto.text.030', 'Subject:')}</Text>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text, marginTop: 2 }}>{previewB.subject}</Text>
                      </View>
                      <View style={{ borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}>
                        <iframe
                          srcDoc={previewB.html}
                          style={{ width: '100%', height: 480, border: 'none' } as any}
                          title="Variant B Preview"
                          sandbox="allow-same-origin"
                          data-testid="ab-preview-iframe-b"
                        />
                      </View>
                    </View>
                  )}
                </View>
              </ScrollView>
            )}
          </View>
        </View>
      )}
    </ScrollView>
  );
}
