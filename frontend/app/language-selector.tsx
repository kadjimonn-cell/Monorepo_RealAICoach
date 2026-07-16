import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ScrollView,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { useTranslation } from '../src/hooks/useTranslation';
import api from '../src/services/api';
import { LanguageSelectorSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import {
  LANGUAGE_OPTIONS,
  POPULAR_LANGUAGE_CODES,
  getCurrentLanguageOption,
} from '../src/i18n/languageOptions';

export default function LanguageSelectorScreen() {
  const pageReady = usePageReady();
  const router = useRouter();
  const params = useLocalSearchParams<{ returnTo?: string | string[] }>();
  const { width } = useWindowDimensions();
  const theme = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();
  const [search, setSearch] = useState('');

  const returnTo = useMemo(() => {
    const raw = params?.returnTo;
    const value = Array.isArray(raw) ? raw[0] : raw;
    return value && value !== '/language-selector' ? value : '';
  }, [params]);

  const handleClose = () => {
    if (returnTo) {
      router.replace(returnTo as any);
      return;
    }
    if (typeof window !== 'undefined' && window.history.length > 1) {
      router.back();
      return;
    }
    router.replace((user ? '/dashboard' : '/welcome') as any);
  };

  const C = useMemo(() => ({
    primary: theme.colors.primary,
    bg: theme.colors.bg,
    bgSoft: theme.colors.bgSoft,
    card: theme.colors.card,
    text: theme.colors.text,
    textSec: theme.colors.textSec,
    textMuted: theme.colors.textMuted,
    border: theme.colors.border,
  }), [theme.colors]);

  const styles = useMemo(() => createStyles(C), [C]);
  const pad = width < 360 ? 14 : width >= 414 ? 20 : 16;
  const currentLanguage = useMemo(
    () => getCurrentLanguageOption(theme.language, theme.languageCode),
    [theme.language, theme.languageCode]
  );

  const filtered = useMemo(() => {
    if (!search.trim()) return LANGUAGE_OPTIONS;
    const q = search.toLowerCase();
    return LANGUAGE_OPTIONS.filter(lang =>
      lang.label.toLowerCase().includes(q) || lang.native.toLowerCase().includes(q)
    );
  }, [search]);

  const popularLanguages = useMemo(
    () => LANGUAGE_OPTIONS.filter(lang => POPULAR_LANGUAGE_CODES.has(lang.code)),
    []
  );

  const renderLanguage = (lang: typeof LANGUAGE_OPTIONS[number], scope: 'popular' | 'all' | 'results') => {
    const selected = currentLanguage?.label === lang.label;
    const rowId = `language-option-${scope}-${lang.id}`;
    return (
      <TouchableOpacity
        key={lang.id}
        style={[styles.languageRow, selected && { borderColor: C.primary, backgroundColor: (globalThis as any).__alphaColor(C.primary, '12') }]}
        onPress={() => {
          theme.setLanguage(lang.label);
          api.post('/i18n/language-guidance/event', {
            event_type: 'switch',
            source: 'language_selector',
            metadata: { language_code: lang.code, language_label: lang.label },
          }).catch(() => {});
          api.post('/i18n/language-guidance/event', {
            event_type: 'remediation_success',
            source: 'language_selector',
            metadata: { language_code: lang.code, language_label: lang.label },
          }).catch(() => {});
        }}
        data-testid={rowId} testID={rowId}
        dataSet={{ testid: rowId }}
        accessibilityLabel={rowId}
        accessible={true}
        nativeID={rowId}
      >
        <View style={styles.languageText}>
          <View style={styles.languageHeadingRow}>
            <Text style={styles.languageLabel} data-testid={`language-label-${scope}-${lang.id}`} testID={`language-label-${scope}-${lang.id}`}>{lang.label}</Text>
            <View style={[styles.languageCodeBadge, { backgroundColor: selected ? (globalThis as any).__alphaColor(C.primary, '18') : C.bgSoft }]}>
              <Text style={[styles.languageCodeText, { color: selected ? C.primary : C.textMuted }]}>{lang.short}</Text>
            </View>
          </View>
          <Text style={styles.languageNative} data-testid={`language-native-${scope}-${lang.id}`} testID={`language-native-${scope}-${lang.id}`}>{lang.native}</Text>
        </View>
        {selected && (
          <View style={styles.selectedBadge} data-testid={`language-selected-${scope}-${lang.id}`} testID={`language-selected-${scope}-${lang.id}`}>
            <Ionicons name="checkmark" size={16} color={theme.colors.primaryText} />
          </View>
        )}
      </TouchableOpacity>
    );
  };

  if (!pageReady) return <LanguageSelectorSkeleton />;
  return (
    <SafeAreaView style={styles.container} edges={['top']} data-testid="language-selector-screen" testID="language-selector-screen">
      <View style={styles.header} data-testid="language-selector-header" testID="language-selector-header">
        <TouchableOpacity
          style={styles.backButton}
          onPress={handleClose}
          data-testid="language-selector-back" testID="language-selector-back"
          dataSet={{ testid: 'language-selector-back' }}
          accessibilityLabel="language-selector-back"
          accessible={true}
          nativeID="language-selector-back"
        >
          <Ionicons name="arrow-back" size={22} color={C.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} data-testid="language-selector-title" testID="language-selector-title">{t('settings.item.language')}</Text>
        <View style={styles.headerSpacer} data-testid="language-selector-spacer" testID="language-selector-spacer" />
      </View>

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[styles.scrollContent, { paddingHorizontal: pad }]}
        data-testid="language-selector-scroll" testID="language-selector-scroll"
      >
        <View style={styles.searchContainer} data-testid="language-selector-search" testID="language-selector-search">
          <Ionicons name="search" size={18} color={C.textMuted} />
          <TextInput
            style={styles.searchInput}
            placeholder={t('language.search')}
            placeholderTextColor={C.textMuted}
            value={search}
            onChangeText={setSearch}
            data-testid="language-selector-search-input" testID="language-selector-search-input"
            dataSet={{ testid: 'language-selector-search-input' }}
            accessibilityLabel="language-selector-search-input"
            nativeID="language-selector-search-input"
          />
          {search.length > 0 && (
            <TouchableOpacity
              onPress={() => setSearch('')}
              data-testid="language-selector-clear" testID="language-selector-clear"
              dataSet={{ testid: 'language-selector-clear' }}
              accessibilityLabel="language-selector-clear"
              accessible={true}
              nativeID="language-selector-clear"
            >
              <Ionicons name="close-circle" size={18} color={C.textMuted} />
            </TouchableOpacity>
          )}
        </View>

        <View style={styles.currentCard} data-testid="language-selector-current" testID="language-selector-current">
          <Text style={styles.currentLabel} data-testid="language-selector-current-label" testID="language-selector-current-label">{t('language.current')}</Text>
          <View style={styles.currentValueRow}>
            <View>
              <Text style={styles.currentValue} data-testid="language-selector-current-value" testID="language-selector-current-value">{currentLanguage?.native || theme.language}</Text>
              <Text style={styles.currentMeta} data-testid="language-selector-current-meta" testID="language-selector-current-meta">{currentLanguage?.label || theme.language}</Text>
            </View>
            <View style={[styles.currentCodeBadge, { backgroundColor: (globalThis as any).__alphaColor(C.primary, '14') }]} data-testid="language-selector-current-code" testID="language-selector-current-code">
              <Text style={[styles.currentCodeText, { color: C.primary }]}>{currentLanguage?.short || 'EN'}</Text>
            </View>
          </View>
        </View>

        {!search.trim() ? (
          <>
            <Text style={styles.sectionTitle} data-testid="language-selector-popular-title" testID="language-selector-popular-title">{t('language.popular')}</Text>
            <View style={styles.sectionCard} data-testid="language-selector-popular-list" testID="language-selector-popular-list">
              {popularLanguages.map((lang) => renderLanguage(lang, 'popular'))}
            </View>

            <Text style={styles.sectionTitle} data-testid="language-selector-all-title" testID="language-selector-all-title">{t('language.all')}</Text>
            <View style={styles.sectionCard} data-testid="language-selector-all-list" testID="language-selector-all-list">
              {LANGUAGE_OPTIONS.map((lang) => renderLanguage(lang, 'all'))}
            </View>
          </>
        ) : (
          <>
            <Text style={styles.sectionTitle} data-testid="language-selector-results-title" testID="language-selector-results-title">{t('language.results')}</Text>
            <View style={styles.sectionCard} data-testid="language-selector-results-list" testID="language-selector-results-list">
              {filtered.length === 0 ? (
                <View style={styles.emptyState} data-testid="language-selector-empty" testID="language-selector-empty">
                  <Ionicons name="search-outline" size={32} color={C.textMuted} />
                  <Text style={styles.emptyTitle} data-testid="language-selector-empty-title" testID="language-selector-empty-title">{t('language.noMatches')}</Text>
                  <Text style={styles.emptySubtitle} data-testid="language-selector-empty-subtitle" testID="language-selector-empty-subtitle">{t('language.tryDifferent')}</Text>
                </View>
              ) : (
                filtered.map((lang) => renderLanguage(lang, 'results'))
              )}
            </View>
          </>
        )}

        <TouchableOpacity
          style={[styles.doneButton, { backgroundColor: C.primary }]}
          onPress={handleClose}
          data-testid="language-selector-done" testID="language-selector-done"
          dataSet={{ testid: 'language-selector-done' }}
          accessibilityLabel="language-selector-done"
          accessible={true}
          nativeID="language-selector-done"
        >
          <Text style={styles.doneButtonText} data-testid="language-selector-done-label" testID="language-selector-done-label">{t('language.done')}</Text>
          <Ionicons name="checkmark" size={18} color={theme.colors.primaryText} />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (C: any) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: C.bg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: C.card,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
  },
  backButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: C.bgSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: C.text,
  },
  headerSpacer: {
    width: 38,
  },
  scrollContent: {
    paddingTop: 16,
    paddingBottom: 32,
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: C.card,
    borderRadius: 14,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: C.border,
  },
  searchInput: {
    flex: 1,
    paddingVertical: 12,
    marginLeft: 10,
    fontSize: 15,
    color: C.text,
  },
  currentCard: {
    backgroundColor: C.card,
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: C.border,
    marginTop: 16,
  },
  currentValueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    marginTop: 4,
  },
  currentLabel: {
    fontSize: 12,
    color: C.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  currentValue: {
    fontSize: 16,
    fontWeight: '600',
    color: C.text,
  },
  currentMeta: {
    fontSize: 12,
    color: C.textMuted,
    marginTop: 2,
  },
  currentCodeBadge: {
    minWidth: 42,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 999,
  },
  currentCodeText: {
    fontSize: 12,
    fontWeight: '800',
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: C.textMuted,
    marginTop: 20,
    marginBottom: 10,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  sectionCard: {
    backgroundColor: C.card,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: C.border,
    overflow: 'hidden',
  },
  languageRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
  },
  languageText: {
    flex: 1,
  },
  languageHeadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  languageLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: C.text,
    flex: 1,
  },
  languageNative: {
    fontSize: 12,
    color: C.textMuted,
    marginTop: 2,
  },
  languageCodeBadge: {
    minWidth: 34,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  languageCodeText: {
    fontSize: 10,
    fontWeight: '800',
  },
  selectedBadge: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: C.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  emptyTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: C.text,
    marginTop: 8,
  },
  emptySubtitle: {
    fontSize: 12,
    color: C.textMuted,
    marginTop: 4,
  },
  doneButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 24,
    borderRadius: 14,
    paddingVertical: 14,
    gap: 8,
  },
  doneButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FEFEFE', // @theme-ok deliberate-high-contrast residual semantic hex (reviewed)
  },
});
