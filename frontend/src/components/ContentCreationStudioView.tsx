import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';
import { useAutoRefresh } from '../hooks/useAutoRefresh';
import FeatureToolbar from './FeatureToolbar';

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
  word_count: number;
  created_at: string;
}

export default function ContentCreationStudioView() {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { _user } = useAuth();
  const { colors: theme, accentColor } = useTheme();
  const [categories, setCategories] = useState<Category[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [activeTab, setActiveTab] = useState<'create' | 'history'>('create');
  const [activeCategory, setActiveCategory] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [tone, setTone] = useState('professional');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(true);

  const C = useMemo(() => ({
    bg: theme.bg,
    card: theme.card,
    text: theme.text,
    muted: theme.textMuted,
    border: theme.border,
    primary: accentColor || theme.primary,
  }), [theme, accentColor]);

  const loadData = useCallback(async () => {
    try {
      const [templatesRes, historyRes] = await Promise.all([
        api.get('/content-studio/templates'),
        api.get('/content-studio/history?limit=20'),
      ]);
      setCategories(templatesRes.data.categories || []);
      setTemplates(templatesRes.data.templates || []);
      if (!activeCategory && templatesRes.data.categories?.length) {
        setActiveCategory(templatesRes.data.categories[0].id);
      }
      setHistory(historyRes.data.history || []);
    } catch (err) {
      console.error('Failed to load studio data:', err);
    } finally {
      setLoading(false);
    }
  }, [activeCategory]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadData(); }, []);
  useAutoRefresh(loadData, { intervalMs: 60000 });

  const filteredTemplates = useMemo(() =>
    templates.filter(t => t.category === activeCategory),
    [templates, activeCategory]
  );

  const selectTemplate = useCallback((t: Template) => {
    setSelectedTemplate(t);
    setFieldValues({});
    setResult('');
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!selectedTemplate) return;
    setGenerating(true);
    setResult('');
    try {
      const res = await api.post('/content-studio/generate', {
        template_id: selectedTemplate.id,
        fields: fieldValues,
        tone,
      });
      setResult(res.data.content || '');
      loadData(); // refresh history
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    } catch (err: any) {
      setResult('Generation failed. Please try again.');
    } finally {
      setGenerating(false);
    }
  }, [selectedTemplate, fieldValues, tone, loadData]);

  const tones = ['professional', 'casual', 'formal', 'creative', 'persuasive'];

  if (loading) return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
      <ActivityIndicator size="large" color={C.primary} />
      <Text style={{ color: C.muted, marginTop: 12, fontSize: 13 }}>Loading Content Studio...</Text>
    </View>
  );

  return (
    <View style={{ flex: 1 }} data-testid="content-studio" testID="content-studio">
      {/* Header */}
      <View style={{ padding: 16, paddingBottom: 8 }}>
        <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, letterSpacing: -0.5 }}>Content Studio</Text>
        <Text style={{ fontSize: 13, color: C.muted, marginTop: 2 }}>AI-powered content generation for any platform</Text>
      </View>

      {/* Tab Bar */}
      <View style={{ flexDirection: 'row', paddingHorizontal: 16, gap: 8, marginBottom: 12 }}>
        {[{ id: 'create' as const, label: 'Create', icon: 'create' }, { id: 'history' as const, label: 'History', icon: 'time' }].map(tab => (
          <TouchableOpacity
            key={tab.id}
            onPress={() => setActiveTab(tab.id)}
            style={[s.tab, { backgroundColor: activeTab === tab.id ? C.primary : C.card, borderColor: activeTab === tab.id ? C.primary : C.border }]}
            data-testid={`studio-tab-${tab.id}`} testID={`studio-tab-${tab.id}`}
          >
            <Ionicons name={tab.icon as any} size={14} color={activeTab === tab.id ? 'var(--app-primary-text)' : C.muted} />
            <Text style={{ fontSize: 12, fontWeight: '600', color: activeTab === tab.id ? 'var(--app-primary-text)' : C.text, marginLeft: 6 }}>{tab.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView style={{ flex: 1, paddingHorizontal: 16 }} showsVerticalScrollIndicator={false}>
        {activeTab === 'create' && (
          <>
            {/* Category Selector */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                {categories.map(cat => (
                  <TouchableOpacity
                    key={cat.id}
                    onPress={() => { setActiveCategory(cat.id); setSelectedTemplate(null); setResult(''); }}
                    style={[s.catBtn, { backgroundColor: activeCategory === cat.id ? (globalThis as any).__alphaColor(cat.color, '20') : C.card, borderColor: activeCategory === cat.id ? cat.color : C.border }]}
                    data-testid={`cat-${cat.id}`} testID={`cat-${cat.id}`}
                  >
                    <Ionicons name={cat.icon as any} size={16} color={activeCategory === cat.id ? cat.color : C.muted} />
                    <Text style={{ fontSize: 12, fontWeight: '600', color: activeCategory === cat.id ? cat.color : C.text, marginLeft: 6 }}>{cat.name}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>

            {/* Template Grid */}
            {!selectedTemplate && (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
                {filteredTemplates.map(t => (
                  <TouchableOpacity
                    key={t.id}
                    onPress={() => selectTemplate(t)}
                    style={[s.templateCard, { backgroundColor: C.card, borderColor: C.border }]}
                    data-testid={`template-${t.id}`} testID={`template-${t.id}`}
                  >
                    <View style={[s.templateIcon, { backgroundColor: (globalThis as any).__alphaColor(t.color, '20') }]}>
                      <Ionicons name={t.icon as any} size={20} color={t.color} />
                    </View>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginTop: 8 }}>{t.name}</Text>
                    <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }} numberOfLines={2}>{t.description}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {/* Generation Form */}
            {selectedTemplate && (
              <View style={[s.formCard, { backgroundColor: C.card, borderColor: C.border }]} data-testid="generation-form" testID="generation-form">
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                    <View style={[s.templateIcon, { backgroundColor: (globalThis as any).__alphaColor(selectedTemplate.color, '20'), width: 36, height: 36 }]}>
                      <Ionicons name={selectedTemplate.icon as any} size={18} color={selectedTemplate.color} />
                    </View>
                    <View style={{ marginLeft: 12 }}>
                      <Text style={{ fontSize: 16, fontWeight: '700', color: C.text }}>{selectedTemplate.name}</Text>
                      <Text style={{ fontSize: 11, color: C.muted }}>{selectedTemplate.description}</Text>
                    </View>
                  </View>
                  <TouchableOpacity onPress={() => { setSelectedTemplate(null); setResult(''); }} data-testid="back-to-templates" testID="back-to-templates">
                    <Ionicons name="close-circle" size={24} color={C.muted} />
                  </TouchableOpacity>
                </View>

                {/* Fields */}
                {selectedTemplate.fields.map(field => (
                  <View key={field.key} style={{ marginBottom: 14 }}>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 6 }}>{field.label}</Text>
                    <TextInput
                      style={[s.input, { backgroundColor: C.bg, color: C.text, borderColor: C.border }]}
                      placeholder={field.placeholder}
                      placeholderTextColor={C.muted}
                      value={fieldValues[field.key] || ''}
                      onChangeText={v => setFieldValues(prev => ({ ...prev, [field.key]: v }))}
                      multiline
                      data-testid={`field-${field.key}`} testID={`field-${field.key}`}
                    />
                  </View>
                ))}

                {/* Tone Selector */}
                <Text style={{ fontSize: 12, fontWeight: '600', color: C.text, marginBottom: 8 }}>Tone</Text>
                <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
                  {tones.map(t => (
                    <TouchableOpacity
                      key={t}
                      onPress={() => setTone(t)}
                      style={[s.toneBtn, { backgroundColor: tone === t ? C.primary : C.bg, borderColor: tone === t ? C.primary : C.border }]}
                      data-testid={`tone-${t}`} testID={`tone-${t}`}
                    >
                      <Text style={{ fontSize: 11, fontWeight: '600', color: tone === t ? 'var(--app-primary-text)' : C.muted, textTransform: 'capitalize' }}>{t}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* Generate Button */}
                <TouchableOpacity
                  onPress={handleGenerate}
                  disabled={generating || !Object.values(fieldValues).some(v => v.trim())}
                  style={[s.generateBtn, { backgroundColor: C.primary, opacity: generating ? 0.6 : 1 }]}
                  data-testid="generate-content-btn" testID="generate-content-btn"
                >
                  {generating ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <ActivityIndicator color="var(--app-primary-text)" size="small" />
                      <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>Generating...</Text>
                    </View>
                  ) : (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Ionicons name="sparkles" size={16} color="var(--app-primary-text)" />
                      <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>Generate Content</Text>
                    </View>
                  )}
                </TouchableOpacity>

                {/* Result */}
                {result ? (
                  <View style={[s.resultCard, { backgroundColor: C.bg, borderColor: C.border }]} data-testid="generated-result" testID="generated-result">
                    <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10 }}>
                      <Ionicons name="document-text" size={16} color={C.primary} />
                      <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginLeft: 6 }}>Generated Content</Text>
                      <Text style={{ fontSize: 11, color: C.muted, marginLeft: 'auto' }}>{result.split(/\s+/).length} words</Text>
                    </View>
                    <Text style={{ fontSize: 14, lineHeight: 22, color: C.text }}>{result}</Text>
                    <FeatureToolbar content={result} featureKey="content-studio" title={selectedTemplate.name} onClear={() => setResult('')} />
                  </View>
                ) : null}
              </View>
            )}
          </>
        )}

        {activeTab === 'history' && (
          <View data-testid="studio-history" testID="studio-history">
            {history.length === 0 ? (
              <View style={{ alignItems: 'center', padding: 40 }}>
                <Ionicons name="document-text-outline" size={40} color={C.muted} />
                <Text style={{ fontSize: 14, fontWeight: '600', color: C.text, marginTop: 12 }}>No content generated yet</Text>
                <Text style={{ fontSize: 12, color: C.muted, marginTop: 4 }}>Create your first content to see it here</Text>
              </View>
            ) : (
              history.map((h, i) => (
                <View key={h.doc_id || i} style={[s.historyCard, { backgroundColor: C.card, borderColor: C.border }]} data-testid={`history-${i}`} testID={`history-${i}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{h.template_name}</Text>
                    <Text style={{ fontSize: 10, color: C.muted }}>{h.word_count} words</Text>
                  </View>
                  <Text style={{ fontSize: 12, color: C.muted }} numberOfLines={3}>{h.content}</Text>
                  <Text style={{ fontSize: 10, color: C.muted, marginTop: 6 }}>{new Date(h.created_at).toLocaleDateString()}</Text>
                </View>
              ))
            )}
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  tab: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, borderWidth: 1 },
  catBtn: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1 },
  templateCard: { width: '47%', padding: 16, borderRadius: 12, borderWidth: 1 },
  templateIcon: { width: 40, height: 40, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  formCard: { padding: 20, borderRadius: 16, borderWidth: 1, marginBottom: 20 },
  input: { padding: 12, borderRadius: 10, borderWidth: 1, fontSize: 14, minHeight: 48 },
  toneBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  generateBtn: { padding: 16, borderRadius: 12, alignItems: 'center', marginTop: 4 },
  resultCard: { padding: 16, borderRadius: 12, borderWidth: 1, marginTop: 16 },
  historyCard: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 10 },
});

/* i18n-probe t('i18n.auto.probe') */
