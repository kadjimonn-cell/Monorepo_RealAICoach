import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import { hasAdminConsoleVisibility } from '../../utils/adminAccess';
import api from '../../services/api';
import { BASE_NAV_ITEMS, NAV_TKEY } from '../AppShell';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY } from '../../constants/appTypography';

const RECENTS_KEY = 'command-palette-recent';
const MAX_RECENTS = 5;

type Destination = { key: string; label: string; icon: string; href: string; section: string };

function readRecents(): string[] {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(RECENTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((k) => typeof k === 'string') : [];
  } catch {
    return [];
  }
}

function writeRecent(key: string) {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  try {
    const next = [key, ...readRecents().filter((k) => k !== key)].slice(0, MAX_RECENTS);
    window.localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  } catch {
    // no-op
  }
}

type CommandPaletteProps = {
  visible: boolean;
  onClose: () => void;
};

export default function CommandPalette({ visible, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const { colors, darkMode } = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [recents, setRecents] = useState<string[]>([]);
  const inputRef = useRef<any>(null);
  const isAdmin = hasAdminConsoleVisibility(user as any);

  const tNav = useCallback((key: string, fallback: string) => {
    const tkey = NAV_TKEY[key];
    if (!tkey) return fallback;
    const value = t(tkey);
    return value === tkey ? fallback : value;
  }, [t]);

  const destinations = useMemo<Destination[]>(() => {
    const out: Destination[] = [];
    let currentSection = '';
    for (const item of BASE_NAV_ITEMS as any[]) {
      if (item.section) {
        currentSection = tNav(item.key, item.label);
        continue;
      }
      if (item.key === 'logout' || !item.href) continue;
      out.push({ key: item.key, label: tNav(item.key, item.label), icon: item.icon, href: item.href, section: currentSection });
    }
    if (isAdmin) {
      const adminSection = tNav('_section_admin', 'ADMIN');
      out.push(
        { key: 'team-management', label: tNav('team-management', 'Team Management'), icon: 'people-circle-outline', href: '/team-management', section: adminSection },
        { key: 'admin', label: tNav('admin', 'Executive Console'), icon: 'shield-checkmark-outline', href: '/executive-dashboard', section: adminSection },
        { key: 'admin-console', label: tNav('admin-console', 'Operations Console'), icon: 'grid-outline', href: '/admin-console?category=people&tab=career-applications', section: adminSection },
      );
    }
    return out;
  }, [isAdmin, tNav]);

  const results = useMemo<Destination[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      const recentItems = recents
        .map((key) => destinations.find((d) => d.key === key))
        .filter((d): d is Destination => Boolean(d));
      const rest = destinations.filter((d) => !recents.includes(d.key));
      return [...recentItems, ...rest];
    }
    return destinations.filter((d) =>
      d.label.toLowerCase().includes(q) || d.key.toLowerCase().includes(q) || d.section.toLowerCase().includes(q)
    );
  }, [query, destinations, recents]);

  const recentCount = query.trim() ? 0 : recents.filter((key) => destinations.some((d) => d.key === key)).length;

  useEffect(() => {
    if (!visible) return;
    setQuery('');
    setActiveIndex(0);
    setRecents(readRecents());
    const handle = setTimeout(() => inputRef.current?.focus?.(), 30);
    return () => clearTimeout(handle);
  }, [visible]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  const handleSelect = useCallback((dest: Destination) => {
    writeRecent(dest.key);
    router.push(dest.href as any);
    setTimeout(() => {
      void api.post('/home/command-palette-nav', {}, { silentLoading: true } as any).catch(() => {});
    }, 0);
    onClose();
  }, [onClose, router]);

  const handleKeyDown = useCallback((e: any) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const dest = results[activeIndex];
      if (dest) handleSelect(dest);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  }, [results, activeIndex, handleSelect, onClose]);

  if (Platform.OS !== 'web' || !visible) return null;

  const kbd = (label: string) => (
    <View style={{ paddingHorizontal: 5, paddingVertical: 2, borderRadius: 5, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}>
      <Text style={{ fontSize: 9.5, fontWeight: '700', color: colors.textMuted, fontFamily: BODY_FONT_FAMILY }}>{label}</Text>
    </View>
  );

  return (
    <View
      style={{
        position: 'fixed' as any, top: 0, left: 0, right: 0, bottom: 0, zIndex: 1200,
        backgroundColor: `${colors.overlay}${darkMode ? 'B3' : '80'}`,
        alignItems: 'center',
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)' } as any : {}),
      }}
      data-testid="command-palette-overlay" testID="command-palette-overlay"
    >
      <TouchableOpacity
        style={{ position: 'absolute' as any, top: 0, left: 0, right: 0, bottom: 0 }}
        activeOpacity={1}
        onPress={onClose}
        data-testid="command-palette-backdrop" testID="command-palette-backdrop"
        accessibilityLabel="Close command palette"
      />
      <View
        style={{
          width: '92%' as any, maxWidth: 600, marginTop: '12vh' as any,
          borderRadius: 16, overflow: 'hidden' as const,
          backgroundColor: colors.card, borderWidth: 1, borderColor: colors.borderStrong || colors.border,
          ...(Platform.OS === 'web' ? {
            boxShadow: darkMode ? '0 24px 64px rgba(0,0,0,0.55)' : '0 24px 64px rgba(15,23,42,0.22)',
          } as any : {}),
        }}
        data-testid="command-palette-panel" testID="command-palette-panel"
      >
        {/* Search input row */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <Ionicons name="search-outline" size={17} color={colors.textMuted} />
          <input accessibilityLabel="Text input"
            ref={inputRef}
            value={query}
            onChange={(e: any) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('commandPalette.placeholder')}
            data-testid="command-palette-input"
            aria-label={t('commandPalette.placeholder')}
            style={{
              flex: 1, border: 'none', outline: 'none', background: 'transparent',
              fontSize: 15, fontWeight: 600, color: colors.text, fontFamily: DISPLAY_FONT_FAMILY,
            } as any}
          />
          {kbd('esc')}
        </View>

        {/* Results */}
        <ScrollView style={{ maxHeight: 380 }} keyboardShouldPersistTaps="handled">
          {results.length === 0 ? (
            <View style={{ paddingVertical: 32, alignItems: 'center', gap: 8 }} data-testid="command-palette-empty" testID="command-palette-empty">
              <Ionicons name="telescope-outline" size={22} color={colors.textMuted} />
              <Text style={{ fontSize: 13, color: colors.textMuted, fontFamily: BODY_FONT_FAMILY }}>{t('commandPalette.noResults')}</Text>
            </View>
          ) : (
            <View style={{ paddingVertical: 6 }}>
              {results.map((dest, idx) => {
                const active = idx === activeIndex;
                const showRecentHeader = idx === 0 && recentCount > 0;
                const showAllHeader = recentCount > 0 ? idx === recentCount : idx === 0;
                return (
                  <React.Fragment key={dest.key}>
                    {showRecentHeader && (
                      <Text style={{ fontSize: 10, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase' as any, color: colors.textMuted, paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4, fontFamily: BODY_FONT_FAMILY }} data-testid="command-palette-recent-header" testID="command-palette-recent-header">
                        {t('commandPalette.recent')}
                      </Text>
                    )}
                    {!query.trim() && showAllHeader && (
                      <Text style={{ fontSize: 10, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase' as any, color: colors.textMuted, paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4, fontFamily: BODY_FONT_FAMILY }} data-testid="command-palette-all-header" testID="command-palette-all-header">
                        {t('commandPalette.allDestinations')}
                      </Text>
                    )}
                    <TouchableOpacity
                      activeOpacity={0.7}
                      onPress={() => handleSelect(dest)}
                      data-testid={`command-palette-item-${dest.key}`} testID={`command-palette-item-${dest.key}`}
                      accessibilityRole="button"
                      accessibilityLabel={dest.label}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 11,
                        marginHorizontal: 8, paddingHorizontal: 10, paddingVertical: 10,
                        borderRadius: 10,
                        backgroundColor: active ? colors.primarySoft : 'transparent',
                        borderWidth: 1, borderColor: active ? `${colors.primary}33` : 'transparent',
                        ...(Platform.OS === 'web' ? { transition: 'background-color .12s ease' } as any : {}),
                      }}
                    >
                      <View style={{ width: 30, height: 30, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: active ? `${colors.primary}1A` : colors.cardMuted }}>
                        <Ionicons name={dest.icon as any} size={15} color={active ? colors.primary : colors.textMuted} />
                      </View>
                      <Text style={{ flex: 1, fontSize: 13.5, fontWeight: active ? '700' : '500', color: active ? colors.text : colors.textSec, fontFamily: BODY_FONT_FAMILY }} numberOfLines={1}>
                        {dest.label}
                      </Text>
                      <Text style={{ fontSize: 10, fontWeight: '700', letterSpacing: 0.8, textTransform: 'uppercase' as any, color: colors.textMuted, fontFamily: BODY_FONT_FAMILY }} numberOfLines={1}>
                        {dest.section}
                      </Text>
                      {active && <Ionicons name="return-down-back-outline" size={13} color={colors.primary} />}
                    </TouchableOpacity>
                  </React.Fragment>
                );
              })}
            </View>
          )}
        </ScrollView>

        {/* Footer hints */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 16, paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.cardMuted }} data-testid="command-palette-footer" testID="command-palette-footer">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            {kbd('\u2191\u2193')}
            <Text style={{ fontSize: 10.5, color: colors.textMuted, fontFamily: BODY_FONT_FAMILY }}>{t('commandPalette.hintNavigate')}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            {kbd('\u21B5')}
            <Text style={{ fontSize: 10.5, color: colors.textMuted, fontFamily: BODY_FONT_FAMILY }}>{t('commandPalette.hintOpen')}</Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            {kbd('esc')}
            <Text style={{ fontSize: 10.5, color: colors.textMuted, fontFamily: BODY_FONT_FAMILY }}>{t('commandPalette.hintClose')}</Text>
          </View>
        </View>
      </View>
    </View>
  );
}
