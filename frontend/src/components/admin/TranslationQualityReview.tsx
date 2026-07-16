import React, { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

interface Sample {
  key: string;
  en: string;
  translated: string;
  status: 'verified' | 'flagged' | 'unreviewed';
  notes: string;
}

interface LangQuality {
  code: string;
  name: string;
  total_keys: number;
  verified: number;
  flagged: number;
  unreviewed: number;
  samples: Sample[];
}

export default function TranslationQualityReview({ colors: _colors }: { colors: any }) {
  const colors = useAdminTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [data, setData] = useState<LangQuality[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedLang, setSelectedLang] = useState<string | null>(null);
  const [reviewingKey, setReviewingKey] = useState<string | null>(null);
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('/i18n/quality-review');
      setData(res.data.languages || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/translation-quality-review/hybrid-refresh',
    onTick: fetchData,
    runOnMount: true,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const submitReview = useCallback(async (lang: string, key: string, status: string) => {
    setSaving(true);
    try {
      await api.post('/i18n/quality-review', { lang, key, status, notes });
      setNotes('');
      setReviewingKey(null);
      await fetchData();
    } catch (e) { console.error(e); } finally { setSaving(false); }
  }, [notes, fetchData]);

  if (loading) return <ActivityIndicator color={'var(--app-primary)'} style={{ marginVertical: 20 }} />;

  const selectedData = data.find(l => l.code === selectedLang);

  return (
    <View data-testid="translation-quality-review" testID="translation-quality-review">
      <AutoFixBanner domain="languages" />
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.translationQualityReview.header.title', 'Translation Quality Review')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.translationQualityReview.header.subtitle', 'Review and verify AI-generated translations for accuracy')}</Text>
        </View>
        <TouchableOpacity onPress={fetchData} data-testid="quality-refresh-btn" testID="quality-refresh-btn"
          style={{ padding: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }}>
          <Ionicons name="refresh" size={16} color={'var(--app-primary)'} />
        </TouchableOpacity>
      </View>

      {/* Language Selector Pills */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {data.map(lang => {
          const isActive = selectedLang === lang.code;
          const hasFlags = lang.flagged > 0;
          return (
            <TouchableOpacity
              key={lang.code}
              onPress={() => setSelectedLang(isActive ? null : lang.code)}
              data-testid={`quality-lang-${lang.code}`} testID={`quality-lang-${lang.code}`}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10,
                backgroundColor: isActive ? colors.primarySoft : colors.surfaceHover,
                borderWidth: 1, borderColor: isActive ? (globalThis as any).__alphaColor('var(--app-primary)', '40') : hasFlags ? (globalThis as any).__alphaColor(colors.error, '40') : colors.border,
              }}
            >
              <Text style={{ color: isActive ? 'var(--app-primary)' : colors.text, fontSize: 12, fontWeight: '700' }}>{lang.code.toUpperCase()}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 10 }}>{lang.name}</Text>
              {hasFlags && (
                <View style={{ backgroundColor: colors.error, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 4 }}>
                  <Text style={{ color: colors.primaryText, fontSize: 8, fontWeight: '700' }}>{lang.flagged}</Text>
                </View>
              )}
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Summary Stats */}
      {selectedData && (
        <View style={{ marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
            {[
              { label: 'Total', value: selectedData.total_keys, color: colors.primary },
              { label: 'Verified', value: selectedData.verified, color: colors.successText },
              { label: 'Flagged', value: selectedData.flagged, color: colors.error },
              { label: 'Unreviewed', value: selectedData.unreviewed, color: colors.warningText },
            ].map(s => (
              <View key={s.label} style={{ flex: 1, padding: 10, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(s.color, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.color, '20'), alignItems: 'center' }}>
                <Text style={{ color: s.color, fontSize: 16, fontWeight: '800' }}>{s.value}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 9, fontWeight: '600' }}>{s.label}</Text>
              </View>
            ))}
          </View>

          {/* Translation Samples */}
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>{tx('admin.translationQualityReview.samples.title', 'Sample Translations')}</Text>
          <View style={{ gap: 6 }}>
            {selectedData.samples.map(sample => {
              const isReviewing = reviewingKey === `${selectedData.code}:${sample.key}`;
              const statusColor = sample.status === 'verified' ? 'var(--app-success)' : sample.status === 'flagged' ? 'var(--app-error)' : 'var(--app-warning)';
              const statusIcon = sample.status === 'verified' ? 'checkmark-circle' : sample.status === 'flagged' ? 'flag' : 'ellipse-outline';

              return (
                <View key={sample.key} style={{
                  padding: 12, borderRadius: 10,
                  backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border,
                }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Text style={{ color: colors.textMuted, fontSize: 10, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>{sample.key}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Ionicons name={statusIcon as any} size={12} color={statusColor} />
                      <Text style={{ color: statusColor, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' }}>{sample.status}</Text>
                    </View>
                  </View>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginBottom: 4 }}>EN: {sample.en}</Text>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{selectedData.code.toUpperCase()}: {sample.translated}</Text>

                  {isReviewing ? (
                    <View style={{ marginTop: 8, gap: 6 }}>
                      <TextInput
                        value={notes}
                        onChangeText={setNotes}
                        placeholder={tx('admin.translationQualityReview.samples.notesPlaceholder', 'Add review notes...')}
                        placeholderTextColor={colors.textMuted}
                        style={{
                          borderWidth: 1, borderColor: colors.border, borderRadius: 8,
                          padding: 8, color: colors.text, fontSize: 12, backgroundColor: colors.surfaceHover,
                        }}
                      />
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        <TouchableOpacity accessibilityLabel="Verify"
                          onPress={() => submitReview(selectedData.code, sample.key, 'verified')}
                          disabled={saving}
                          style={{ flex: 1, padding: 8, borderRadius: 8, backgroundColor: colors.success, alignItems: 'center' }}
                        >
                          <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.translationQualityReview.actions.verify', 'Verify')}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity accessibilityLabel="Flag Issue"
                          onPress={() => submitReview(selectedData.code, sample.key, 'flagged')}
                          disabled={saving}
                          style={{ flex: 1, padding: 8, borderRadius: 8, backgroundColor: colors.error, alignItems: 'center' }}
                        >
                          <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700' }}>{tx('admin.translationQualityReview.actions.flagIssue', 'Flag Issue')}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity accessibilityLabel="close button"
                          onPress={() => { setReviewingKey(null); setNotes(''); }}
                          style={{ padding: 8, borderRadius: 8, backgroundColor: colors.border, alignItems: 'center' }}
                        >
                          <Ionicons name="close" size={14} color={colors.textMuted} />
                        </TouchableOpacity>
                      </View>
                    </View>
                  ) : (
                    <TouchableOpacity accessibilityLabel="Review"
                      onPress={() => setReviewingKey(`${selectedData.code}:${sample.key}`)}
                      style={{ marginTop: 6, alignSelf: 'flex-start' }}
                    >
                      <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '600' }}>{tx('admin.translationQualityReview.actions.review', 'Review')}</Text>
                    </TouchableOpacity>
                  )}
                </View>
              );
            })}
          </View>
        </View>
      )}

      {!selectedData && (
        <View style={{ padding: 20, alignItems: 'center', borderRadius: 12, backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border }}>
          <Ionicons name="language" size={24} color={colors.textMuted} />
          <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 8 }}>{tx('admin.translationQualityReview.states.selectLanguage', 'Select a language above to review translations')}</Text>
        </View>
      )}
    </View>
  );
}
