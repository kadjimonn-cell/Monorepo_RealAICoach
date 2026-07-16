import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import AppShell from '../src/components/AppShell';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { NOVA_HUB_PREFILL_KEY } from '../src/config/novaHub';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

type FavoriteItem = { message_id: string; conversation_id: string; content: string; updated_at?: string };
type PinItem = { conversation_id: string; preview?: string; updated_at?: string };

export default function NovaCurationHubPage() {
  const router = useRouter();
  const { colors } = useTheme();
  const { user, loading: authLoading } = useAuth();
  const { t } = useTranslation();

  const tx = useCallback((key: string, fallback: string) => {
    const translated = t(key);
    return translated === key ? fallback : translated;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState('');
  const [searchText, setSearchText] = useState('');
  const [pins, setPins] = useState<PinItem[]>([]);
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [error, setError] = useState('');

  const loadHub = useCallback(async () => {
    if (!user?.user_id) return;
    setLoading(true);
    setError('');
    try {
      const [pinsRes, favRes] = await Promise.all([
        api.get('/support/chat/conversations/pins?limit=60', { silentLoading: true }),
        api.get('/support/chat/messages/favorites?limit=150', { silentLoading: true }),
      ]);
      setPins(Array.isArray(pinsRes?.data?.pins) ? pinsRes.data.pins : []);
      setFavorites(Array.isArray(favRes?.data?.favorites) ? favRes.data.favorites : []);
    } catch {
      setError(tx('novaCurationHub.loadError', 'Unable to load your saved Nova items right now.'));
      setPins([]);
      setFavorites([]);
    } finally {
      setLoading(false);
    }
  }, [tx, user?.user_id]);

  useEffect(() => {
    if (!authLoading && user?.user_id) {
      void loadHub();
    }
  }, [authLoading, user?.user_id, loadHub]);

  const removePin = useCallback(async (conversationId: string) => {
    setBusyId(`pin:${conversationId}`);
    try {
      await api.delete('/support/chat/conversations/pin', {
        data: { conversation_id: conversationId },
        timeout: 10000,
      });
      await loadHub();
    } finally {
      setBusyId('');
    }
  }, [loadHub]);

  const removeFavorite = useCallback(async (conversationId: string, messageId: string) => {
    setBusyId(`fav:${messageId}`);
    try {
      await api.delete('/support/chat/messages/favorite', {
        data: { conversation_id: conversationId, message_id: messageId },
        timeout: 10000,
      });
      await loadHub();
    } finally {
      setBusyId('');
    }
  }, [loadHub]);

  const openSnippetInHelp = useCallback((text: string) => {
    const snippet = String(text || '').trim();
    if (!snippet) return;
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(NOVA_HUB_PREFILL_KEY, snippet.slice(0, 400));
      } catch (error) { handleAppRecoverableError({ scope: 'nova-curation-hub.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
    router.push('/help');
  }, [router]);

  const query = searchText.trim().toLowerCase();
  const filteredPins = useMemo(() => {
    if (!query) return pins;
    return pins.filter((pin) => String(pin.preview || pin.conversation_id || '').toLowerCase().includes(query));
  }, [pins, query]);
  const filteredFavorites = useMemo(() => {
    if (!query) return favorites;
    return favorites.filter((fav) => String(fav.content || '').toLowerCase().includes(query) || String(fav.conversation_id || '').toLowerCase().includes(query));
  }, [favorites, query]);

  if (authLoading) {
    return (
      <AppShell>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: 'transparent' }} data-testid="nova-curation-hub-auth-loading" testID="nova-curation-hub-auth-loading">
          <ActivityIndicator color={colors.primary} />
        </View>
      </AppShell>
    );
  }

  if (!user?.user_id) {
    return (
      <AppShell>
        <View style={{ flex: 1, backgroundColor: 'transparent', padding: 18, alignItems: 'center', justifyContent: 'center' }} data-testid="nova-curation-hub-auth-required" testID="nova-curation-hub-auth-required">
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }} data-testid="nova-curation-hub-auth-required-title" testID="nova-curation-hub-auth-required-title">{tx('novaCurationHub.authRequiredTitle', 'Sign in required')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8, textAlign: 'center' }} data-testid="nova-curation-hub-auth-required-subtitle" testID="nova-curation-hub-auth-required-subtitle">
            Your Nova pinned conversations and favorite answers are available after login.
          </Text>
          <TouchableOpacity onPress={() => router.push('/login')} style={{ marginTop: 12, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.primary }} data-testid="nova-curation-hub-login-button" testID="nova-curation-hub-login-button">
            <Text style={{ color: colors.primaryText || colors.text, fontSize: 12, fontWeight: '800' }}>Go to login</Text>
          </TouchableOpacity>
        </View>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: 'transparent' }} data-testid="nova-curation-hub-page" testID="nova-curation-hub-page">
        <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800' }} data-testid="nova-curation-hub-title" testID="nova-curation-hub-title">{tx('novaCurationHub.pageTitle', 'Nova Pinned & Favorites Hub')}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} data-testid="nova-curation-hub-subtitle" testID="nova-curation-hub-subtitle">
                {tx('novaCurationHub.pageSubtitle', 'Manage all saved Nova items in one place.')}
              </Text>
            </View>
            <TouchableOpacity onPress={() => void loadHub()} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, 'AE') : colors.card, paddingHorizontal: 12, paddingVertical: 8, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid="nova-curation-hub-refresh-button" testID="nova-curation-hub-refresh-button">
              <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>Refresh</Text>
            </TouchableOpacity>
          </View>

          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <StatCard label="Pinned" value={String(pins.length)} colors={colors} testId="nova-curation-hub-pinned-count" />
            <StatCard label="Favorites" value={String(favorites.length)} colors={colors} testId="nova-curation-hub-favorites-count" />
          </View>

          <TextInput
            value={searchText}
            onChangeText={setSearchText}
            placeholder="Search saved snippets and conversations"
            placeholderTextColor={colors.textMuted}
            style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, 'AE') : colors.card, color: colors.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13 }}
            data-testid="nova-curation-hub-search-input"
            testID="nova-curation-hub-search-input"
          />

          {error ? (
            <Text style={{ color: colors.error, fontSize: 12 }} data-testid="nova-curation-hub-error" testID="nova-curation-hub-error">{error}</Text>
          ) : null}

          {loading ? (
            <View style={{ paddingVertical: 30, alignItems: 'center', justifyContent: 'center' }} data-testid="nova-curation-hub-loading" testID="nova-curation-hub-loading">
              <ActivityIndicator color={colors.primary} />
            </View>
          ) : (
            <>
              <Section title={`Pinned conversations (${filteredPins.length})`} colors={colors} testId="nova-curation-hub-pinned-section">
                {filteredPins.length === 0 ? (
                  <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="nova-curation-hub-pinned-empty" testID="nova-curation-hub-pinned-empty">No pinned conversations found.</Text>
                ) : filteredPins.map((pin, idx) => {
                  const id = String(pin.conversation_id || `pin-${idx}`);
                  const busy = busyId === `pin:${id}`;
                  return (
                    <View key={id} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.bgSoft, 'B8') : colors.bgSoft, padding: 10, gap: 8, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}) }} data-testid={`nova-curation-hub-pinned-row-${idx}`} testID={`nova-curation-hub-pinned-row-${idx}`}>
                      <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }} numberOfLines={2}>{pin.preview || id}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }} numberOfLines={1}>{id}</Text>
                      <View style={{ flexDirection: 'row', gap: 8 }}>
                        <TouchableOpacity onPress={() => openSnippetInHelp(pin.preview || id)} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primary, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`nova-curation-hub-pinned-use-${idx}`} testID={`nova-curation-hub-pinned-use-${idx}`}>
                          <Text style={{ color: colors.primaryText || colors.text, fontSize: 10, fontWeight: '800' }}>Use in chat</Text>
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => void removePin(id)} disabled={busy} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.error, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.bg, 'A8') : colors.bg, paddingHorizontal: 10, paddingVertical: 7, opacity: busy ? 0.7 : 1 }} data-testid={`nova-curation-hub-pinned-remove-${idx}`} testID={`nova-curation-hub-pinned-remove-${idx}`}>
                          <Text style={{ color: colors.error, fontSize: 10, fontWeight: '800' }}>{busy ? 'Removing…' : 'Unpin'}</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                })}
              </Section>

              <Section title={`Favorite answers (${filteredFavorites.length})`} colors={colors} testId="nova-curation-hub-favorites-section">
                {filteredFavorites.length === 0 ? (
                  <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="nova-curation-hub-favorites-empty" testID="nova-curation-hub-favorites-empty">No favorite answers found.</Text>
                ) : filteredFavorites.map((fav, idx) => {
                  const id = String(fav.message_id || `fav-${idx}`);
                  const busy = busyId === `fav:${id}`;
                  return (
                    <View key={id} style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.bgSoft, 'B8') : colors.bgSoft, padding: 10, gap: 8, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' } as any : {}) }} data-testid={`nova-curation-hub-favorite-row-${idx}`} testID={`nova-curation-hub-favorite-row-${idx}`}>
                      <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }} numberOfLines={3}>{fav.content}</Text>
                      <Text style={{ color: colors.textMuted, fontSize: 10 }} numberOfLines={1}>{fav.conversation_id}</Text>
                      <View style={{ flexDirection: 'row', gap: 8 }}>
                        <TouchableOpacity onPress={() => openSnippetInHelp(fav.content)} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primary, paddingHorizontal: 10, paddingVertical: 7 }} data-testid={`nova-curation-hub-favorite-use-${idx}`} testID={`nova-curation-hub-favorite-use-${idx}`}>
                          <Text style={{ color: colors.primaryText || colors.text, fontSize: 10, fontWeight: '800' }}>Use in chat</Text>
                        </TouchableOpacity>
                        <TouchableOpacity onPress={() => void removeFavorite(fav.conversation_id, id)} disabled={busy} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.error, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.bg, 'A8') : colors.bg, paddingHorizontal: 10, paddingVertical: 7, opacity: busy ? 0.7 : 1 }} data-testid={`nova-curation-hub-favorite-remove-${idx}`} testID={`nova-curation-hub-favorite-remove-${idx}`}>
                          <Text style={{ color: colors.error, fontSize: 10, fontWeight: '800' }}>{busy ? 'Removing…' : 'Remove'}</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                })}
              </Section>
            </>
          )}
        </ScrollView>
      </View>
    </AppShell>
  );
}

function StatCard({ label, value, colors, testId }: { label: string; value: string; colors: any; testId: string }) {
  return (
    <View style={{ minWidth: 130, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, 'B0') : colors.card, padding: 10, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{label}</Text>
      <Text style={{ color: colors.text, fontSize: 18, fontWeight: '900', marginTop: 5 }}>{value}</Text>
    </View>
  );
}

function Section({ title, children, colors, testId }: { title: string; children: React.ReactNode; colors: any; testId: string }) {
  return (
    <View style={{ borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: Platform.OS === 'web' ? (globalThis as any).__alphaColor(colors.card, 'AE') : colors.card, padding: 12, gap: 8, ...(Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {}) }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{title}</Text>
      {children}
    </View>
  );
}
