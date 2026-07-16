import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const LANGS = ['en', 'fr', 'es', 'de', 'it', 'pt'];
const CATEGORIES = ['general', 'account', 'billing', 'features', 'security', 'employer', 'technical'];

interface FAQ {
  faq_id: string;
  question: string;
  answer: string;
  category: string;
  lang: string;
  order: number;
  active: boolean;
  created_at?: string;
}

export default function FAQManagementPanel({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const C = { ...colors, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)' };
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [filterLang, setFilterLang] = useState('en');
  const [faqPage, setFaqPage] = useState(1);
  const faqPageSize = 25;
  const { data: faqData, loading, refetch: fetchFaqs } = useLiveQuery(
    `/support/faq/admin/list?lang=${filterLang}&page=${faqPage}&page_size=${faqPageSize}`,
    { pollInterval: 30000, entity: 'faqs' },
  );
  const { data: completenessData, loading: completenessLoading, refetch: refetchCompleteness } = useLiveQuery('/support/faq/admin/language-completeness', { pollInterval: 60000, entity: 'faqs' });
  const faqs = faqData?.data || faqData?.faqs || [];
  const faqTotalCount = Number(faqData?.total_count ?? faqData?.total ?? faqs.length ?? 0);
  const faqTotalPages = Math.max(1, Math.ceil(faqTotalCount / faqPageSize));

  useEffect(() => {
    if (faqPage > faqTotalPages) {
      setFaqPage(faqTotalPages);
    }
  }, [faqPage, faqTotalPages]);
  const [editingFaq, setEditingFaq] = useState<FAQ | null>(null);
  const [isNew, setIsNew] = useState(false);

  // Form state
  const [formQ, setFormQ] = useState('');
  const [formA, setFormA] = useState('');
  const [formCat, setFormCat] = useState('general');
  const [formLang, setFormLang] = useState('en');
  const [formOrder, setFormOrder] = useState('0');
  const [saving, setSaving] = useState(false);
  const [seeding, setSeeding] = useState(false);

  const startEdit = (faq: FAQ) => {
    setEditingFaq(faq); setIsNew(false);
    setFormQ(faq.question); setFormA(faq.answer);
    setFormCat(faq.category); setFormLang(faq.lang);
    setFormOrder(String(faq.order));
  };

  const startNew = () => {
    setEditingFaq(null); setIsNew(true);
    setFormQ(''); setFormA(''); setFormCat('general');
    setFormLang(filterLang); setFormOrder('0');
  };

  const cancelEdit = () => { setEditingFaq(null); setIsNew(false); };

  const handleSave = async () => {
    if (!formQ.trim() || !formA.trim()) return;
    setSaving(true);
    try {
      const payload = { question: formQ, answer: formA, category: formCat, lang: formLang, order: parseInt(formOrder) || 0 };
      if (isNew) {
        await api.post('/support/faq/admin/create', payload);
      } else if (editingFaq) {
        await api.put(`/support/faq/admin/${editingFaq.faq_id}`, payload);
      }
      cancelEdit(); fetchFaqs();
    } catch (e: any) {
      if (Platform.OS === 'web') window.alert(e?.response?.data?.detail || tx('admin.faqManagement.errors.saveFailed', 'Save failed'));
    } finally { setSaving(false); }
  };

  const handleDelete = async (faq: FAQ) => {
    if (Platform.OS === 'web' && !window.confirm(tx('admin.faqManagement.prompts.deleteConfirmWithQuestion', 'Delete "{question}"?').replace('{question}', `${faq.question.substring(0, 50)}...`))) return;
    try {
      await api.delete(`/support/faq/admin/${faq.faq_id}`);
      fetchFaqs();
    } catch (e) { console.error('Delete failed:', e); }
  };

  const handleSeed = async () => {
    setSeeding(true);
    try {
      const res = await api.post('/support/faq/admin/seed');
      if (Platform.OS === 'web') window.alert(res.data.message || tx('admin.faqManagement.actions.seeded', 'Seeded'));
      fetchFaqs();
    } catch (e: any) {
      if (Platform.OS === 'web') window.alert(e?.response?.data?.detail || tx('admin.faqManagement.errors.seedFailed', 'Seed failed'));
    } finally { setSeeding(false); }
  };

  const activeFaqs = faqs.filter(f => f.active);
  const inactiveFaqs = faqs.filter(f => !f.active);

  const langCompleteness = completenessData?.languages || [];
  const completenessSummary = completenessData?.summary || null;

  const completenessColor = (pct: number) => {
    if (pct >= 95) return C.green;
    if (pct >= 70) return C.yellow;
    return C.red;
  };

  // ── Editor Form ──
  if (isNew || editingFaq) {
    return (
      <ScrollView showsVerticalScrollIndicator={false} data-testid="faq-editor" testID="faq-editor">
      <AutoFixBanner domain="faq" />
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <Text style={{ fontSize: 16, fontWeight: '800', color: C.text }}>{isNew ? tx('admin.faqManagement.editor.newFaq', 'New FAQ') : tx('admin.faqManagement.editor.editFaq', 'Edit FAQ')}</Text>
          <TouchableOpacity onPress={cancelEdit} data-testid="faq-cancel-btn" testID="faq-cancel-btn">
            <Ionicons name="close" size={22} color={C.muted || C.textMuted} />
          </TouchableOpacity>
        </View>

        <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 4 }}>{tx('admin.faqManagement.editor.language', 'Language')}</Text>
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
          {LANGS.map(l => (
            <TouchableOpacity key={l} data-testid={`faq-lang-${l}`} testID={`faq-lang-${l}`}
              style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: formLang === l ? (globalThis as any).__alphaColor(C.blue, '20') : (C.bgSoft || C.card) }}
              onPress={() => setFormLang(l)}>
              <Text style={{ fontSize: 12, fontWeight: '700', color: formLang === l ? C.blue : (C.muted || C.textMuted) }}>{l.toUpperCase()}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 4 }}>{tx('admin.faqManagement.editor.category', 'Category')}</Text>
        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
          {CATEGORIES.map(c => (
            <TouchableOpacity key={c} data-testid={`faq-cat-${c}`} testID={`faq-cat-${c}`}
              style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: formCat === c ? (globalThis as any).__alphaColor(C.purple, '20') : (C.bgSoft || C.card) }}
              onPress={() => setFormCat(c)}>
              <Text style={{ fontSize: 11, fontWeight: '600', color: formCat === c ? C.purple : (C.muted || C.textMuted) }}>{tx(`admin.faqManagement.categories.${c}`, c)}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 4 }}>{tx('admin.faqManagement.editor.order', 'Order')}</Text>
        <TextInput data-testid="faq-order-input" testID="faq-order-input" value={formOrder} onChangeText={setFormOrder} accessibilityLabel={tx('admin.faqManagement.editor.order', 'Order')}
          keyboardType="numeric" style={{ backgroundColor: C.bgSoft || C.card, color: C.text, borderRadius: 8, padding: 10, fontSize: 14, marginBottom: 12, borderWidth: 1, borderColor: C.border }} />

        <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 4 }}>{tx('admin.faqManagement.editor.questionRequired', 'Question *')}</Text>
        <TextInput data-testid="faq-question-input" testID="faq-question-input" value={formQ} onChangeText={setFormQ}
          placeholder={tx('admin.faqManagement.editor.questionPlaceholder', 'Enter FAQ question...')} placeholderTextColor={C.muted || C.textMuted} multiline
          style={{ backgroundColor: C.bgSoft || C.card, color: C.text, borderRadius: 8, padding: 10, fontSize: 14, minHeight: 60, marginBottom: 12, borderWidth: 1, borderColor: C.border, textAlignVertical: 'top' }} />

        <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 4 }}>{tx('admin.faqManagement.editor.answerRequired', 'Answer *')}</Text>
        <TextInput data-testid="faq-answer-input" testID="faq-answer-input" value={formA} onChangeText={setFormA}
          placeholder={tx('admin.faqManagement.editor.answerPlaceholder', 'Enter FAQ answer...')} placeholderTextColor={C.muted || C.textMuted} multiline
          style={{ backgroundColor: C.bgSoft || C.card, color: C.text, borderRadius: 8, padding: 10, fontSize: 14, minHeight: 120, marginBottom: 16, borderWidth: 1, borderColor: C.border, textAlignVertical: 'top' }} />

        <View style={{ flexDirection: 'row', gap: 10 }}>
          <TouchableOpacity data-testid="faq-save-btn" testID="faq-save-btn"
            style={{ flex: 1, backgroundColor: C.blue, borderRadius: 10, paddingVertical: 12, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6, opacity: saving ? 0.6 : 1 }}
            onPress={handleSave} disabled={saving}>
            {saving ? <ActivityIndicator size="small" color="var(--app-primary-text)" /> : <Ionicons name="checkmark" size={18} color="var(--app-primary-text)" />}
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.primaryText }}>{tx('admin.faqManagement.actions.save', 'Save')}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={{ flex: 1, backgroundColor: C.bgSoft || C.card, borderRadius: 10, paddingVertical: 12, alignItems: 'center' }} onPress={cancelEdit} accessibilityLabel={tx('admin.faqManagement.actions.cancel', 'Cancel')} data-testid="faq-cancel-edit-btn" testID="faq-cancel-edit-btn">
            <Text style={{ fontSize: 14, fontWeight: '600', color: C.muted || C.textMuted }}>{tx('admin.faqManagement.actions.cancel', 'Cancel')}</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    );
  }

  // ── FAQ List ──
  return (
    <ScrollView showsVerticalScrollIndicator={false}>
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="help-circle" size={20} color={C.blue} />
          <Text style={{ fontSize: 17, fontWeight: '800', color: C.text }}>{tx('admin.faqManagement.header.title', 'FAQ Management')}</Text>
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.blue, '20'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.blue }}>{activeFaqs.length}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <TouchableOpacity data-testid="faq-seed-btn" testID="faq-seed-btn"
            style={{ backgroundColor: (globalThis as any).__alphaColor(C.yellow, '14'), paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }}
            onPress={handleSeed} disabled={seeding}>
            {seeding ? <ActivityIndicator size="small" color={C.yellow} /> : <Ionicons name="download" size={14} color={C.yellow} />}
            <Text style={{ fontSize: 11, fontWeight: '600', color: C.yellow }}>{tx('admin.faqManagement.actions.seed', 'Seed')}</Text>
          </TouchableOpacity>
          <TouchableOpacity data-testid="faq-new-btn" testID="faq-new-btn"
            style={{ backgroundColor: C.blue, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, flexDirection: 'row', alignItems: 'center', gap: 4 }}
            onPress={startNew}>
            <Ionicons name="add" size={16} color="var(--app-primary-text)" />
            <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>{tx('admin.faqManagement.actions.addFaq', 'Add FAQ')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Language Filter */}
      <View
        style={{ backgroundColor: C.card, borderRadius: 12, padding: 12, marginBottom: 12, borderWidth: 1, borderColor: C.border }}
        data-testid="faq-language-completeness-card"
        testID="faq-language-completeness-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Ionicons name="language" size={15} color={C.blue} />
            <Text style={{ fontSize: 12, fontWeight: '800', color: C.text }}>{tx('admin.faqManagement.completeness.title', 'Language Completeness Checker')}</Text>
          </View>
          <TouchableOpacity
            onPress={() => refetchCompleteness()}
            style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 7, backgroundColor: C.bgSoft || C.card, borderWidth: 1, borderColor: C.border }}
            data-testid="faq-language-completeness-refresh"
            testID="faq-language-completeness-refresh"
          >
            <Text style={{ fontSize: 10, fontWeight: '700', color: C.blue }}>{completenessLoading ? tx('admin.faqManagement.completeness.refreshing', 'Refreshing…') : tx('admin.faqManagement.completeness.refresh', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>

        {completenessSummary ? (
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.blue, '12'), borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5 }} data-testid="faq-language-completeness-languages-complete" testID="faq-language-completeness-languages-complete">
              <Text style={{ fontSize: 10, color: C.text }}>{tx('admin.faqManagement.completeness.complete', 'Complete')}: <Text style={{ fontWeight: '800', color: C.blue }}>{completenessSummary.languages_complete}/{completenessSummary.languages_total}</Text></Text>
            </View>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.yellow, '14'), borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5 }} data-testid="faq-language-completeness-average" testID="faq-language-completeness-average">
              <Text style={{ fontSize: 10, color: C.text }}>{tx('admin.faqManagement.completeness.averageCoverage', 'Avg coverage')}: <Text style={{ fontWeight: '800', color: C.yellow }}>{completenessSummary.average_completeness_pct}%</Text></Text>
            </View>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.red, '12'), borderRadius: 8, paddingHorizontal: 8, paddingVertical: 5 }} data-testid="faq-language-completeness-missing" testID="faq-language-completeness-missing">
              <Text style={{ fontSize: 10, color: C.text }}>{tx('admin.faqManagement.completeness.missingPairs', 'Missing pairs')}: <Text style={{ fontWeight: '800', color: C.red }}>{completenessSummary.missing_pairs_total}</Text></Text>
            </View>
          </View>
        ) : null}

        <View style={{ gap: 6 }}>
          {langCompleteness.map((langRow: any) => {
            const pct = Number(langRow?.completeness_pct || 0);
            const color = completenessColor(pct);
            const missingText = (langRow?.missing_categories || []).slice(0, 3).join(', ');
            return (
              <TouchableOpacity accessibilityLabel="Set filter lang in faqmanagement panel"
                key={langRow.lang}
                onPress={() => { setFilterLang(langRow.lang); setFaqPage(1); }}
                style={{
                  backgroundColor: (C.bgSoft || C.card),
                  borderRadius: 8,
                  borderWidth: 1,
                  borderColor: (globalThis as any).__alphaColor(color, '40'),
                  paddingHorizontal: 9,
                  paddingVertical: 7,
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 8,
                }}
                data-testid={`faq-language-completeness-row-${langRow.lang}`}
                testID={`faq-language-completeness-row-${langRow.lang}`}
              >
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(color, '18'), borderRadius: 6, paddingHorizontal: 7, paddingVertical: 2 }}>
                  <Text style={{ fontSize: 10, fontWeight: '800', color }}>{String(langRow.lang || '').toUpperCase()}</Text>
                </View>
                <Text style={{ fontSize: 10, color: C.text, fontWeight: '700' }} data-testid={`faq-language-completeness-pct-${langRow.lang}`} testID={`faq-language-completeness-pct-${langRow.lang}`}>{pct}%</Text>
                <Text style={{ fontSize: 9, color: C.muted || C.textMuted, flex: 1 }} numberOfLines={1} data-testid={`faq-language-completeness-missing-text-${langRow.lang}`} testID={`faq-language-completeness-missing-text-${langRow.lang}`}>
                  {langRow?.missing_count > 0
                    ? tx('admin.faqManagement.completeness.missingWithValues', 'Missing: {items}{suffix}')
                      .replace('{items}', missingText)
                      .replace('{suffix}', langRow?.missing_count > 3 ? '…' : '')
                    : tx('admin.faqManagement.completeness.allCovered', 'All required categories covered')}
                </Text>
                <Ionicons name="chevron-forward" size={12} color={C.muted || C.textMuted} />
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
        <TouchableOpacity style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: filterLang === 'all' ? (globalThis as any).__alphaColor(C.blue, '20') : (C.bgSoft || C.card) }}
          onPress={() => { setFilterLang('all'); setFaqPage(1); }} data-testid="faq-filter-all" testID="faq-filter-all">
          <Text style={{ fontSize: 12, fontWeight: '600', color: filterLang === 'all' ? C.blue : (C.muted || C.textMuted) }}>{tx('admin.faqManagement.filters.all', 'All')}</Text>
        </TouchableOpacity>
        {LANGS.map(l => (
          <TouchableOpacity key={l} data-testid={`faq-filter-${l}`} testID={`faq-filter-${l}`}
            style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: filterLang === l ? (globalThis as any).__alphaColor(C.blue, '20') : (C.bgSoft || C.card) }}
            onPress={() => { setFilterLang(l); setFaqPage(1); }}>
            <Text style={{ fontSize: 12, fontWeight: '600', color: filterLang === l ? C.blue : (C.muted || C.textMuted) }}>{l.toUpperCase()}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={{ padding: 30, alignItems: 'center' }}><ActivityIndicator size="large" color={C.blue} /></View>
      ) : activeFaqs.length === 0 ? (
        <View style={{ padding: 30, alignItems: 'center' }}>
          <Ionicons name="help-circle-outline" size={40} color={C.muted || C.textMuted} />
          <Text style={{ fontSize: 14, color: C.muted || C.textMuted, marginTop: 8 }}>{tx('admin.faqManagement.states.noFaqForLanguage', 'No FAQs for this language. Use "Seed" to populate.')}</Text>
        </View>
      ) : (
        activeFaqs.map((faq, idx) => (
          <View key={faq.faq_id} data-testid={`faq-item-${faq.faq_id}`} testID={`faq-item-${faq.faq_id}`}
            style={{ backgroundColor: C.card, borderRadius: 10, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: C.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <View style={{ flex: 1, marginRight: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.purpleText, textTransform: 'uppercase' }}>{faq.category}</Text>
                  <Text style={{ fontSize: 10, color: C.muted || C.textMuted }}>#{faq.order}</Text>
                  <Text style={{ fontSize: 10, color: C.blue, fontWeight: '600' }}>{faq.lang.toUpperCase()}</Text>
                </View>
                <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 4 }} numberOfLines={2}>{faq.question}</Text>
                <Text style={{ fontSize: 12, color: C.sec || C.textSec, lineHeight: 18 }} numberOfLines={3}>{faq.answer}</Text>
              </View>
              <View style={{ flexDirection: 'row', gap: 4 }}>
                <TouchableOpacity style={{ padding: 6, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.blue, '14') }} onPress={() => startEdit(faq)} data-testid={`faq-edit-${faq.faq_id}`} testID={`faq-edit-${faq.faq_id}`}>
                  <Ionicons name="create" size={14} color={C.blue} />
                </TouchableOpacity>
                <TouchableOpacity style={{ padding: 6, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.red, '14') }} onPress={() => handleDelete(faq)} data-testid={`faq-delete-${faq.faq_id}`} testID={`faq-delete-${faq.faq_id}`}>
                  <Ionicons name="trash" size={14} color={C.red} />
                </TouchableOpacity>
              </View>
            </View>
          </View>
        ))
      )}

      {inactiveFaqs.length > 0 && (
        <View style={{ marginTop: 16 }}>
          <Text style={{ fontSize: 13, fontWeight: '700', color: C.muted || C.textMuted, marginBottom: 8 }}>{tx('admin.faqManagement.states.archivedWithCount', 'Archived ({count})').replace('{count}', String(inactiveFaqs.length))}</Text>
          {inactiveFaqs.map(faq => (
            <View key={faq.faq_id} style={{ backgroundColor: C.card, borderRadius: 10, padding: 10, marginBottom: 6, opacity: 0.5, borderWidth: 1, borderColor: C.border }}>
              <Text style={{ fontSize: 12, color: C.muted || C.textMuted }} numberOfLines={1}>{faq.question}</Text>
            </View>
          ))}
        </View>
      )}

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 10, marginBottom: 4 }}>
        <Text style={{ fontSize: 11, color: C.muted || C.textMuted }} data-testid="faq-pagination-summary" testID="faq-pagination-summary">
          Page {faqPage} of {faqTotalPages} • {faqTotalCount} total
        </Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TouchableOpacity
            onPress={() => setFaqPage((p) => Math.max(1, p - 1))}
            disabled={faqPage <= 1}
            style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: C.border, opacity: faqPage <= 1 ? 0.5 : 1 }}
            data-testid="faq-prev-page"
            testID="faq-prev-page"
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>Prev</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setFaqPage((p) => Math.min(faqTotalPages, p + 1))}
            disabled={faqPage >= faqTotalPages}
            style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: C.border, opacity: faqPage >= faqTotalPages ? 0.5 : 1 }}
            data-testid="faq-next-page"
            testID="faq-next-page"
          >
            <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>Next</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
}
