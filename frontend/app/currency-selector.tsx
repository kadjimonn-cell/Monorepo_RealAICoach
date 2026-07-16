import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { useTranslation } from '../src/hooks/useTranslation';
import api from '../src/services/api';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

type CurrencyItem = {
  code: string;
  symbol: string;
  name: string;
};

export default function CurrencySelectorScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { user, refreshUser } = useAuth();
  const { width } = useWindowDimensions();
  const [search, setSearch] = useState('');
  const [items, setItems] = useState<CurrencyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingCode, setSavingCode] = useState('');
  const [selectedCurrency, setSelectedCurrency] = useState('USD');

  const C = useMemo(() => ({
    bg: colors.bg,
    card: colors.card,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
    primary: colors.primary,
    bgSoft: colors.bgSoft,
  }), [colors]);

  useEffect(() => {
    const fromUser = (user as any)?.currency_preference;
    if (fromUser) {
      setSelectedCurrency(String(fromUser).toUpperCase());
      return;
    }
    if (typeof window !== 'undefined') {
      const stored = window.localStorage.getItem('currency_preference');
      if (stored) setSelectedCurrency(stored.toUpperCase());
    }
  }, [user]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      try {
        const [currenciesRes, geoRes] = await Promise.all([
          api.get('/payments/currencies', { timeout: 12000 }).catch(() => ({ data: { currencies: [
            { code: 'USD', symbol: '$', name: 'US Dollar' },
            { code: 'EUR', symbol: '€', name: 'Euro' },
            { code: 'GBP', symbol: '£', name: 'British Pound' },
            { code: 'JPY', symbol: '¥', name: 'Japanese Yen' },
          ] } })),
          api.get('/geo/detect').catch(() => ({ data: {} })),
        ]);
        const list = (currenciesRes.data?.currencies || []).map((c: any) => ({
          code: String(c.code || '').toUpperCase(),
          symbol: String(c.symbol || ''),
          name: String(c.name || c.code || ''),
        }));
        if (mounted) setItems(list);

        if (!(user as any)?.currency_preference && geoRes.data?.default_currency && mounted) {
          setSelectedCurrency(String(geoRes.data.default_currency).toUpperCase());
        }
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [user]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((c) =>
      c.code.toLowerCase().includes(q)
      || c.name.toLowerCase().includes(q)
      || c.symbol.toLowerCase().includes(q)
    );
  }, [items, search]);

  const applyCurrency = async (code: string) => {
    const normalized = code.toUpperCase();
    setSavingCode(normalized);
    try {
      await api.put('/auth/profile', { currency_preference: normalized });
      if (typeof window !== 'undefined') {
        window.localStorage.setItem('currency_preference', normalized);
      }
      setSelectedCurrency(normalized);
      await refreshUser();
    } catch (error) { handleAppRecoverableError({ scope: 'currency-selector.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setSavingCode('');
    }
  };

  const styles = useMemo(() => createStyles(C), [C]);
  const pad = width < 360 ? 14 : width >= 414 ? 20 : 16;

  return (
    <SafeAreaView style={styles.container} edges={['top']} data-testid="currency-selector-screen" testID="currency-selector-screen">
      <View style={styles.header} data-testid="currency-selector-header" testID="currency-selector-header">
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton} data-testid="currency-selector-back-button" testID="currency-selector-back-button">
          <Ionicons name="arrow-back" size={22} color={C.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} data-testid="currency-selector-title" testID="currency-selector-title">{tx('currencySelector.page.title', 'Currency')}</Text>
        <View style={styles.backButton} />
      </View>

      <ScrollView contentContainerStyle={[styles.scrollContent, { paddingHorizontal: pad }]} showsVerticalScrollIndicator={false} data-testid="currency-selector-scroll" testID="currency-selector-scroll">
        <View style={styles.searchContainer} data-testid="currency-selector-search-wrap" testID="currency-selector-search-wrap">
          <Ionicons name="search" size={18} color={C.textMuted} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder={tx('currencySelector.search.placeholder', 'Search currency')}
            placeholderTextColor={C.textMuted}
            style={styles.searchInput}
            data-testid="currency-selector-search-input" testID="currency-selector-search-input"
          />
        </View>

        <View style={styles.currentCard} data-testid="currency-selector-current-card" testID="currency-selector-current-card">
          <Text style={styles.currentLabel}>{tx('currencySelector.labels.current', 'Current Currency')}</Text>
          <Text style={styles.currentValue} data-testid="currency-selector-current-value" testID="currency-selector-current-value">{selectedCurrency}</Text>
        </View>

        <View style={styles.listCard} data-testid="currency-selector-list-card" testID="currency-selector-list-card">
          {loading ? (
            <Text style={styles.emptyText} data-testid="currency-selector-loading-text" testID="currency-selector-loading-text">{tx('currencySelector.states.loading', 'Loading currencies...')}</Text>
          ) : filtered.length === 0 ? (
            <Text style={styles.emptyText} data-testid="currency-selector-empty-text" testID="currency-selector-empty-text">{tx('currencySelector.states.empty', 'No matching currencies found.')}</Text>
          ) : (
            filtered.map((item) => {
              const active = selectedCurrency === item.code;
              const saving = savingCode === item.code;
              return (
                <TouchableOpacity
                  key={item.code}
                  onPress={() => { void applyCurrency(item.code); }}
                  disabled={saving}
                  style={[styles.row, active && { borderColor: C.primary, backgroundColor: (globalThis as any).__alphaColor(C.primary, '10') }]}
                  data-testid={`currency-selector-option-${item.code.toLowerCase()}`} testID={`currency-selector-option-${item.code.toLowerCase()}`}
                >
                  <View>
                    <Text style={styles.rowTitle}>{item.code} · {item.symbol}</Text>
                    <Text style={styles.rowSub}>{item.name}</Text>
                  </View>
                  {saving ? (
                    <Text style={styles.savingText}>{tx('currencySelector.states.saving', 'Saving...')}</Text>
                  ) : active ? (
                    <Ionicons name="checkmark-circle" size={20} color={C.primary} />
                  ) : (
                    <Ionicons name="ellipse-outline" size={18} color={C.textMuted} />
                  )}
                </TouchableOpacity>
              );
            })
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (C: any) => StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
    backgroundColor: C.card,
  },
  backButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.bgSoft,
  },
  headerTitle: { fontSize: 18, fontWeight: '700', color: C.text },
  scrollContent: { paddingTop: 16, paddingBottom: 32 },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: C.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: C.border,
    paddingHorizontal: 12,
  },
  searchInput: { flex: 1, color: C.text, fontSize: 14, marginLeft: 8, paddingVertical: 11 },
  currentCard: {
    marginTop: 14,
    backgroundColor: C.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: C.border,
    padding: 14,
  },
  currentLabel: { fontSize: 12, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 },
  currentValue: { marginTop: 4, fontSize: 17, fontWeight: '700', color: C.text },
  listCard: {
    marginTop: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: C.border,
    backgroundColor: C.card,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
  },
  rowTitle: { fontSize: 14, fontWeight: '600', color: C.text },
  rowSub: { marginTop: 2, fontSize: 12, color: C.textMuted },
  savingText: { fontSize: 12, color: C.textMuted, fontWeight: '600' },
  emptyText: { padding: 16, color: C.textMuted, fontSize: 13 },
});
