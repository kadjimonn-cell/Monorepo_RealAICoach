import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator, TextInput, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';
import PremiumGuard from './PremiumGuard';
import FeatureToolbar from './FeatureToolbar';
import MarkdownDisplay from './MarkdownDisplay';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

interface Template {
  id: string;
  name: string;
  category: string;
  icon: string;
  color: string;
  description: string;
  fields: { key: string; label: string; placeholder: string }[];
}

interface Category {
  id: string;
  name: string;
  icon: string;
  color: string;
}

interface HistoryItem {
  doc_id: string;
  template_name: string;
  category: string;
  content: string;
  created_at: string;
  tone: string;
}

export default function AIContentStudioView() {
  const { user } = useAuth();
  const { colors: C, accentColor } = useTheme();

  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    container: { flex: 1 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    tabRow: { flexDirection: 'row', paddingHorizontal: 16, paddingTop: 12, gap: 10 },
    tab: {
      flexDirection: 'row', alignItems: 'center', gap: 6,
      paddingVertical: 8, paddingHorizontal: 16, borderRadius: 20, borderWidth: 1, borderColor: 'transparent',
    },
    tabText: { fontWeight: '600', fontSize: 14 },
    scroll: { flex: 1, paddingHorizontal: 16 },
    section: { marginTop: 16 },
    catRow: { marginBottom: 16 },
    catChip: {
      flexDirection: 'row', alignItems: 'center', gap: 6,
      paddingVertical: 6, paddingHorizontal: 14, borderRadius: 20,
      borderWidth: 1, borderColor: C.border, marginRight: 8,
    },
    catText: { fontSize: 13, fontWeight: '500', color: C.textMuted },
    templateGrid: {
      flexDirection: 'row', flexWrap: 'wrap', gap: 12,
    },
    templateCard: {
      width: Platform.OS === 'web' ? 'calc(50% - 6px)' as any : '48%',
      padding: 14, borderRadius: 14, borderWidth: 1, gap: 8,
    },
    templateIcon: {
      width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
    },
    templateName: { fontSize: 14, fontWeight: '700' },
    templateDesc: { fontSize: 12, lineHeight: 17 },
    backRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 16 },
    backText: { fontSize: 14, fontWeight: '600' },
    templateHeader: {
      padding: 18, borderRadius: 16, borderWidth: 1, alignItems: 'center', gap: 8, marginBottom: 20,
    },
    headerTitle: { fontSize: 18, fontWeight: '700' },
    headerDesc: { fontSize: 13, textAlign: 'center' },
    fieldWrap: { marginBottom: 14 },
    fieldLabel: { fontSize: 13, fontWeight: '600', marginBottom: 6 },
    input: {
      padding: 12, borderRadius: 12, borderWidth: 1, fontSize: 14, minHeight: 48,
      ...Platform.select({ web: { outlineStyle: 'none' } as any }),
    },
    toneChip: {
      paddingVertical: 6, paddingHorizontal: 14, borderRadius: 20,
      borderWidth: 1, borderColor: C.border, marginRight: 8,
    },
    toneText: { fontSize: 13, fontWeight: '500', color: C.textMuted },
    genBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
      padding: 16, borderRadius: 14,
    },
    genBtnText: { color: C.primaryText, fontWeight: '700', fontSize: 16 },
    resultHeader: {
      flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
      marginBottom: 12, paddingBottom: 12, borderBottomWidth: 1,
    },
    resultBadge: {
      flexDirection: 'row', alignItems: 'center', gap: 4,
      paddingVertical: 4, paddingHorizontal: 10, borderRadius: 12,
    },
    resultBadgeText: { fontSize: 12, fontWeight: '600' },
    resultWords: { fontSize: 12 },
    resultCard: { padding: 16, borderRadius: 14, borderWidth: 1, marginBottom: 12 },
    emptyState: { alignItems: 'center', paddingTop: 60, gap: 8 },
    emptyTitle: { fontSize: 16, fontWeight: '600' },
    emptyDesc: { fontSize: 13 },
    historyCard: { borderRadius: 14, borderWidth: 1, marginBottom: 10, overflow: 'hidden' },
    historyRow: { flexDirection: 'row', alignItems: 'center', padding: 14 },
    historyName: { fontSize: 14, fontWeight: '600' },
    historyMeta: { fontSize: 12, marginTop: 2 },
    historyContent: { paddingHorizontal: 14, paddingBottom: 14 },
    historyText: { fontSize: 13, lineHeight: 20 },
    historyActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 10 },
    deleteBtn: { padding: 8 },
  });

  const [activeTab, setActiveTab] = useState<'generate' | 'history'>('generate');
  const [categories, setCategories] = useState<Category[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [tone, setTone] = useState('professional');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<{ content: string; word_count: number; doc_id: string } | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(null);
  const [loadingTemplates, setLoadingTemplates] = useState(true);

  const TONES = ['professional', 'casual', 'persuasive', 'friendly', 'formal', 'humorous'];

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    try {
      const res = await api.get('/content-studio/templates');
      setCategories(res.data.categories || []);
      setTemplates(res.data.templates || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIContentStudioView.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setLoadingTemplates(false);
    }
  };

  const fetchHistory = useCallback(async () => {
    if (!user) return;
    setHistoryLoading(true);
    try {
      const res = await api.get('/content-studio/history');
      setHistory(res.data.items || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIContentStudioView.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setHistoryLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (activeTab === 'history') fetchHistory();
  }, [activeTab, fetchHistory]);

  const filteredTemplates = selectedCategory
    ? templates.filter(t => t.category === selectedCategory)
    : templates;

  const handleSelectTemplate = (t: Template) => {
    setSelectedTemplate(t);
    setFieldValues({});
    setResult(null);
  };

  const handleGenerate = async () => {
    if (!selectedTemplate) return;
    const empty = selectedTemplate.fields.some(f => !fieldValues[f.key]?.trim());
    if (empty) return;

    setGenerating(true);
    setResult(null);
    try {
      const res = await api.post('/content-studio/generate', {
        template_id: selectedTemplate.id,
        fields: fieldValues,
        tone,
      });
      setResult(res.data);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIContentStudioView.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setGenerating(false);
    }
  };

  const handleDeleteHistory = async (docId: string) => {
    try {
      await api.delete(`/content-studio/history/${docId}`);
      setHistory(h => h.filter(i => i.doc_id !== docId));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AIContentStudioView.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const iconMap: Record<string, keyof typeof Ionicons.glyphMap> = {
    'share-social': 'share-social',
    'mail': 'mail',
    'document-text': 'document-text',
    'briefcase': 'briefcase',
    'logo-linkedin': 'logo-linkedin',
    'logo-twitter': 'logo-twitter',
    'logo-instagram': 'logo-instagram',
    'mail-open': 'mail-open',
    'newspaper': 'newspaper',
    'list': 'list',
    'clipboard': 'clipboard',
  };

  if (loadingTemplates) {
    return (
      <View style={[styles.center, { backgroundColor: C.bg }]}>
        <ActivityIndicator size="large" color={accentColor} />
      </View>
    );
  }

  return (
    <PremiumGuard featureName="AI Content Studio">
      <View style={[styles.container, { backgroundColor: C.bg }]} data-testid="content-studio-view" testID="content-studio-view">
        {/* Tab Bar */}
        <View style={styles.tabRow}>
          {(['generate', 'history'] as const).map(tab => (
            <TouchableOpacity
              key={tab}
              data-testid={`tab-${tab}`} testID={`tab-${tab}`}
              style={[styles.tab, activeTab === tab && { backgroundColor: (globalThis as any).__alphaColor(accentColor, '18'), borderColor: accentColor }]}
              onPress={() => setActiveTab(tab)}
            >
              <Ionicons
                name={tab === 'generate' ? 'sparkles' : 'time'}
                size={16}
                color={activeTab === tab ? accentColor : C.textMuted}
              />
              <Text style={[styles.tabText, { color: activeTab === tab ? accentColor : C.textMuted }]}>
                {tab === 'generate' ? 'Generate' : 'History'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: 60 }}>
          {activeTab === 'generate' && !selectedTemplate && (
            <View style={styles.section}>
              {/* Category Filter */}
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.catRow}>
                <TouchableOpacity
                  data-testid="category-all" testID="category-all"
                  style={[styles.catChip, !selectedCategory && { backgroundColor: accentColor, borderColor: accentColor }]}
                  onPress={() => setSelectedCategory(null)}
                >
                  <Text style={[styles.catText, !selectedCategory && { color: C.primaryText }]}>All</Text>
                </TouchableOpacity>
                {categories.map(c => (
                  <TouchableOpacity
                    key={c.id}
                    data-testid={`category-${c.id}`} testID={`category-${c.id}`}
                    style={[styles.catChip, selectedCategory === c.id && { backgroundColor: c.color, borderColor: c.color }]}
                    onPress={() => setSelectedCategory(selectedCategory === c.id ? null : c.id)}
                  >
                    <Ionicons name={(iconMap[c.icon] || 'apps') as any} size={14} color={selectedCategory === c.id ? 'var(--app-primary-text)' : C.textMuted} />
                    <Text style={[styles.catText, selectedCategory === c.id && { color: C.primaryText }]}>{c.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>

              {/* Template Grid */}
              <View style={styles.templateGrid}>
                {filteredTemplates.map(t => (
                  <TouchableOpacity
                    key={t.id}
                    data-testid={`template-${t.id}`} testID={`template-${t.id}`}
                    style={[styles.templateCard, { backgroundColor: C.card, borderColor: C.border }]}
                    onPress={() => handleSelectTemplate(t)}
                  >
                    <View style={[styles.templateIcon, { backgroundColor: (globalThis as any).__alphaColor(t.color, '18') }]}>
                      <Ionicons name={(iconMap[t.icon] || 'document-text') as any} size={22} color={t.color} />
                    </View>
                    <Text style={[styles.templateName, { color: C.text }]} numberOfLines={1}>{t.name}</Text>
                    <Text style={[styles.templateDesc, { color: C.textMuted }]} numberOfLines={2}>{t.description}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {activeTab === 'generate' && selectedTemplate && !result && (
            <View style={styles.section}>
              {/* Back + Template Header */}
              <TouchableOpacity
                data-testid="back-to-templates" testID="back-to-templates"
                style={styles.backRow}
                onPress={() => { setSelectedTemplate(null); setResult(null); }}
              >
                <Ionicons name="arrow-back" size={20} color={accentColor} />
                <Text style={[styles.backText, { color: accentColor }]}>Templates</Text>
              </TouchableOpacity>

              <View style={[styles.templateHeader, { backgroundColor: (globalThis as any).__alphaColor(selectedTemplate.color, '10'), borderColor: (globalThis as any).__alphaColor(selectedTemplate.color, '30') }]}>
                <View style={[styles.templateIcon, { backgroundColor: (globalThis as any).__alphaColor(selectedTemplate.color, '20') }]}>
                  <Ionicons name={(iconMap[selectedTemplate.icon] || 'document-text') as any} size={24} color={selectedTemplate.color} />
                </View>
                <Text style={[styles.headerTitle, { color: C.text }]}>{selectedTemplate.name}</Text>
                <Text style={[styles.headerDesc, { color: C.textMuted }]}>{selectedTemplate.description}</Text>
              </View>

              {/* Fields */}
              {selectedTemplate.fields.map(f => (
                <View key={f.key} style={styles.fieldWrap}>
                  <Text style={[styles.fieldLabel, { color: C.textSec }]}>{f.label}</Text>
                  <TextInput
                    data-testid={`field-${f.key}`} testID={`field-${f.key}`}
                    style={[styles.input, { backgroundColor: C.card, color: C.text, borderColor: C.border }]}
                    placeholder={f.placeholder}
                    placeholderTextColor={C.textMuted}
                    value={fieldValues[f.key] || ''}
                    onChangeText={v => setFieldValues(prev => ({ ...prev, [f.key]: v }))}
                    multiline
                  />
                </View>
              ))}

              {/* Tone Selector */}
              <Text style={[styles.fieldLabel, { color: C.textSec, marginTop: 8 }]}>Tone</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
                {TONES.map(t => (
                  <TouchableOpacity
                    key={t}
                    data-testid={`tone-${t}`} testID={`tone-${t}`}
                    style={[styles.toneChip, tone === t && { backgroundColor: accentColor, borderColor: accentColor }]}
                    onPress={() => setTone(t)}
                  >
                    <Text style={[styles.toneText, tone === t && { color: C.primaryText }]}>
                      {t.charAt(0).toUpperCase() + t.slice(1)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>

              {/* Generate Button */}
              <TouchableOpacity
                data-testid="generate-content-btn" testID="generate-content-btn"
                style={[styles.genBtn, { backgroundColor: accentColor }]}
                onPress={handleGenerate}
                disabled={generating}
              >
                {generating ? (
                  <ActivityIndicator color="var(--app-primary-text)" />
                ) : (
                  <>
                    <Ionicons name="sparkles" size={18} color="var(--app-primary-text)" />
                    <Text style={styles.genBtnText}>Generate Content</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          )}

          {activeTab === 'generate' && result && (
            <View style={styles.section}>
              <TouchableOpacity
                data-testid="new-generation-btn" testID="new-generation-btn"
                style={styles.backRow}
                onPress={() => { setResult(null); setSelectedTemplate(null); }}
              >
                <Ionicons name="arrow-back" size={20} color={accentColor} />
                <Text style={[styles.backText, { color: accentColor }]}>New Generation</Text>
              </TouchableOpacity>

              <View style={[styles.resultHeader, { borderColor: (globalThis as any).__alphaColor(accentColor, '30') }]}>
                <View style={[styles.resultBadge, { backgroundColor: (globalThis as any).__alphaColor(accentColor, '18') }]}>
                  <Ionicons name="checkmark-circle" size={16} color={accentColor} />
                  <Text style={[styles.resultBadgeText, { color: accentColor }]}>Generated</Text>
                </View>
                <Text style={[styles.resultWords, { color: C.textMuted }]}>{result.word_count} words</Text>
              </View>

              <View style={[styles.resultCard, { backgroundColor: C.card, borderColor: C.border }]} data-testid="generated-content-result" testID="generated-content-result">
                <MarkdownDisplay content={result.content} />
              </View>

              <FeatureToolbar
                content={result.content}
                featureKey="content-studio-ai"
                title={selectedTemplate?.name || 'Generated Content'}
                onClear={() => { setResult(null); setSelectedTemplate(null); }}
              />
            </View>
          )}

          {activeTab === 'history' && (
            <View style={styles.section}>
              {historyLoading ? (
                <ActivityIndicator color={accentColor} size="large" style={{ marginTop: 40 }} />
              ) : history.length === 0 ? (
                <View style={styles.emptyState} data-testid="history-empty" testID="history-empty">
                  <Ionicons name="document-text-outline" size={48} color={C.textMuted} />
                  <Text style={[styles.emptyTitle, { color: C.text }]}>No content generated yet</Text>
                  <Text style={[styles.emptyDesc, { color: C.textMuted }]}>Generated content will appear here</Text>
                </View>
              ) : (
                history.map(item => (
                  <View
                    key={item.doc_id}
                    style={[styles.historyCard, { backgroundColor: C.card, borderColor: C.border }]}
                    data-testid={`history-item-${item.doc_id}`} testID={`history-item-${item.doc_id}`}
                  >
                    <TouchableOpacity accessibilityLabel="item.template_name"
                      onPress={() => setExpandedHistoryId(expandedHistoryId === item.doc_id ? null : item.doc_id)}
                      style={styles.historyRow}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.historyName, { color: C.text }]}>{item.template_name}</Text>
                        <Text style={[styles.historyMeta, { color: C.textMuted }]}>
                          {item.tone} &middot; {new Date(item.created_at).toLocaleDateString()}
                        </Text>
                      </View>
                      <Ionicons
                        name={expandedHistoryId === item.doc_id ? 'chevron-up' : 'chevron-down'}
                        size={18}
                        color={C.textMuted}
                      />
                    </TouchableOpacity>
                    {expandedHistoryId === item.doc_id && (
                      <View style={styles.historyContent}>
                        <Text style={[styles.historyText, { color: C.textSec }]} numberOfLines={15}>
                          {item.content}
                        </Text>
                        <View style={styles.historyActions}>
                          <FeatureToolbar
                            content={item.content}
                            featureKey="content-studio-history"
                            title={item.template_name}
                          />
                          <TouchableOpacity
                            data-testid={`delete-history-${item.doc_id}`} testID={`delete-history-${item.doc_id}`}
                            onPress={() => handleDeleteHistory(item.doc_id)}
                            style={styles.deleteBtn}
                          >
                            <Ionicons name="trash-outline" size={16} color={C.error} />
                          </TouchableOpacity>
                        </View>
                      </View>
                    )}
                  </View>
                ))
              )}
            </View>
          )}
        </ScrollView>
      </View>
    </PremiumGuard>
  );
}

/* i18n-probe t('i18n.auto.probe') */
