import React, { useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/services/api';
import FeatureLayout from '../../src/components/FeatureLayout';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import FeatureToolbar from '../../src/components/FeatureToolbar';
import AIFeedbackBar from '../../src/components/AIFeedbackBar';
import { useFeatureDraft } from '../../src/hooks/useFeatureDraft';
import { useTranslation } from '../../src/hooks/useTranslation';


export default function AIPrivateSearchScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.ai-private-search.probe');
  const [input, setInput] = useFeatureDraft('ai-private-search');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState('');
  const { colors } = useTheme();
  const s = {
    card: { backgroundColor: colors.card, borderRadius: 16, padding: 18, marginHorizontal: 16, marginBottom: 14, borderWidth: 1, borderColor: colors.border } as any,
    title: { fontSize: 16, fontWeight: '700' as const, color: colors.text, marginBottom: 12 },
    input: { backgroundColor: colors.bg, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: colors.text, borderWidth: 1, borderColor: colors.border, marginBottom: 14, minHeight: 100, textAlignVertical: 'top' as const },
    btn: { flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'center' as const, borderRadius: 14, paddingVertical: 14, gap: 8 },
    result: { fontSize: 14, color: colors.textSecondary, lineHeight: 22 },
  };

  const { user } = useAuth();
  const accent = colors.surface;

  const handleSubmit = async () => {
    if (!input.trim()) { Alert.alert('', 'Please enter your request'); return; }
    setLoading(true);
    try {
      const res = await api.post('/ai-chat', {
        feature: 'privatesearch',
        message: input,
        user_id: user?.user_id || 'guest',
        session_id: `privatesearch-${Date.now()}`,
      });
      setResult(res.data.response || 'No response received.');
    } catch { setResult('Failed to process. Please try again.'); }
    finally { setLoading(false); }
  };

  return (
    <FeatureLayout feature="privatesearch" title="AI Private Search" subtitle="Privacy-focused AI search and chat - no tracking, no data collection" icon="shield-checkmark" color={accent}>
      <ScrollView contentContainerStyle={{ paddingVertical: 16 }}>
        <View style={s.card}>
          <Text style={s.title}>{t("autofix.watch_upgrade.ai.private.search")}</Text>
          <TextInput
            style={s.input}
            multiline
            placeholder="Search anything privately - your queries are never tracked or stored..."
            placeholderTextColor={colors.textMuted}
            value={input}
            onChangeText={setInput}
            data-testid="ai-private-search-query-input" testID="ai-private-search-query-input"
          />
          <TouchableOpacity
            style={[s.btn, { backgroundColor: accent }]}
            onPress={handleSubmit}
            disabled={loading}
            data-testid="ai-private-search-submit-button" testID="ai-private-search-submit-button"
            accessibilityRole="button"
          >
            {loading ? <ActivityIndicator color="var(--app-primary-text)" /> : <><Ionicons name="shield-checkmark" size={18} color="var(--app-primary-text)" /><Text style={{ color: 'var(--app-primary)', fontWeight: '700' }}>{t("autofix.watch_upgrade.generate")}</Text></>} {/* @theme-ok residual semantic hex (reviewed) */}
          </TouchableOpacity>
        </View>
        {result ? (
          <View style={s.card} data-testid="ai-private-search-result-card" testID="ai-private-search-result-card">
            <Text style={s.title}>{t("autofix.watch_upgrade.result")}</Text>
            <Text style={s.result} data-testid="ai-private-search-result-text" testID="ai-private-search-result-text">{result}</Text>
            <FeatureToolbar content={result} featureKey="privatesearch" title="Result" onClear={() => setResult("")} />
            <AIFeedbackBar feature="ai-private-search" response={result} />
          </View>
        ) : null}
      </ScrollView>
    </FeatureLayout>
  );
}