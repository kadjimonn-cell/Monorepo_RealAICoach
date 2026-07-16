import React, { useEffect, useMemo, useState } from 'react';
import { View, TouchableOpacity, Text, StyleSheet, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { usePathname, useRouter } from 'expo-router';
import { useIsFocused } from '@react-navigation/native';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useLocation } from '../context/LocationContext';
import { useNavigationStore } from '../store/useNavigationStore';
import { getShadow } from '../utils/themeShadows';
import { useTranslation } from '../hooks/useTranslation';
import api from '../services/api';
import EnterpriseSignOutConfirmModal from './auth/EnterpriseSignOutConfirmModal';
import { handleAppRecoverableError } from '../utils/appRecoverableError';
import { hasAdminConsoleVisibility } from '../utils/adminAccess';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY } from '../constants/appTypography';
import CommandPalette from './nav/CommandPalette';
import { BASE_NAV_ITEMS, NAV_TKEY } from './AppShell';

const AUTH_ROUTES = new Set(['/welcome', '/auth/login', '/auth/register', '/auth/reset-password']);
const NAVBAR_HINT_CACHE_TTL_MS = 15 * 60 * 1000;

function readSessionCache<T = any>(key: string): T | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.expiresAt || parsed.expiresAt < Date.now()) {
      window.sessionStorage.removeItem(key);
      return null;
    }
    return parsed.value as T;
  } catch {
    return null;
  }
}

function writeSessionCache(key: string, value: any) {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify({ value, expiresAt: Date.now() + NAVBAR_HINT_CACHE_TTL_MS }));
  } catch (error) { handleAppRecoverableError({ scope: 'src/components/GlobalNavBar.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

type GlobalNavBarProps = {
  dimmed?: boolean;
};

export default function GlobalNavBar({ dimmed = false }: GlobalNavBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { colors, darkMode, language } = useTheme();

  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    bar: {
      flexDirection: 'row',
      alignItems: 'center',
      minHeight: 54,
      borderBottomWidth: 1,
      paddingHorizontal: 14,
      paddingVertical: 10,
    },
    btn: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 12,
      paddingVertical: 8,
      borderRadius: 12,
      gap: 6,
    },
    btnDisabled: {
      opacity: 0.35,
    },
    label: {
      fontSize: 12,
      fontWeight: '700',
      fontFamily: BODY_FONT_FAMILY,
    },
    divider: {
      width: 1,
      height: 18,
      marginHorizontal: 8,
    },
    quickControls: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      flexWrap: 'wrap',
    },
    chipBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      borderWidth: 1,
      borderRadius: 999,
      paddingHorizontal: 10,
      paddingVertical: 7,
    },
    chipLabel: {
      fontSize: 11,
      fontWeight: '700',
      fontFamily: BODY_FONT_FAMILY,
    },
    signOutBtn: {
      borderColor: colors.errorSoft,
      backgroundColor: colors.errorSoft,
    },
    signOutLabel: {
      color: colors.error,
    },
    hintBar: {
      borderBottomWidth: 1,
      paddingHorizontal: 10,
      paddingVertical: 5,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
    },
    hintText: {
      fontSize: 11,
      fontWeight: '500',
      color: 'var(--app-primary)', // @theme-ok residual semantic hex (reviewed)
      fontFamily: BODY_FONT_FAMILY,
    },
  });
  const { user, logout, isAuthenticated } = useAuth();
  const { detectedLocale } = useLocation();
  const { canGoBack, canGoForward, goBack, goForward, onPathChange, onPopState } = useNavigationStore();
  const { t } = useTranslation();
  const txv = (key: string, fallback: string) => { const v = t(key); return v === key ? fallback : v; };
  const [geoCurrency, setGeoCurrency] = useState('');
  const [currentCurrency, setCurrentCurrency] = useState('USD');
  const [hintDismissed, setHintDismissed] = useState(false);
  const [hintSuppressedServerSide, setHintSuppressedServerSide] = useState(false);
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const isScreenFocused = useIsFocused();
  const [systemHealth, setSystemHealth] = useState<{ status?: string; active_sessions?: number; recent_errors?: any[] } | null>(null);

  const isAdmin = hasAdminConsoleVisibility(user as any);

  const languageShort = useMemo(() => {
    const map: Record<string, string> = {
      English: 'EN', French: 'FR', Spanish: 'ES', German: 'DE', Portuguese: 'PT', Japanese: 'JA', Hindi: 'HI', Arabic: 'AR', Korean: 'KO', Dutch: 'NL', Swedish: 'SV', Polish: 'PL', Thai: 'TH', Vietnamese: 'VI', Indonesian: 'ID', Malay: 'MS', Swahili: 'SW', Ukrainian: 'UK', Romanian: 'RO',
    };
    return map[language] || (language || 'EN').slice(0, 2).toUpperCase();
  }, [language]);

  useEffect(() => {
    const fromUser = (user as any)?.currency_preference;
    if (fromUser) {
      setCurrentCurrency(String(fromUser).toUpperCase());
      return;
    }
    if (typeof window !== 'undefined') {
      const stored = window.localStorage.getItem('currency_preference');
      if (stored) {
        setCurrentCurrency(stored.toUpperCase());
      }
    }
  }, [user]);

  useEffect(() => {
    let mounted = true;
    const cachedCurrency = readSessionCache<string>('global-nav-geo-currency');
    if (cachedCurrency) {
      setGeoCurrency(cachedCurrency);
      return () => { mounted = false; };
    }
    api.get('/geo/detect', { silentLoading: true })
      .then((res) => {
        if (!mounted) return;
        const detected = String(res.data?.default_currency || '').toUpperCase();
        setGeoCurrency(detected);
        if (detected) writeSessionCache('global-nav-geo-currency', detected);
      })
      .catch(() => {});
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    let mounted = true;
    if (!user) return;
    const cachedGuidance = readSessionCache<{ suppressed?: boolean }>('global-nav-language-guidance');
    if (cachedGuidance) {
      const suppressed = Boolean(cachedGuidance.suppressed);
      setHintSuppressedServerSide(suppressed);
      if (suppressed) setHintDismissed(true);
      return () => { mounted = false; };
    }
    api.get('/i18n/language-guidance', { silentLoading: true })
      .then((res) => {
        if (!mounted) return;
        const suppressed = Boolean(res.data?.suppressed);
        setHintSuppressedServerSide(suppressed);
        if (suppressed) setHintDismissed(true);
        writeSessionCache('global-nav-language-guidance', { suppressed });
      })
      .catch(() => {});
    return () => { mounted = false; };
  }, [user]);

  useEffect(() => {
    if (!isAuthenticated || !isAdmin) {
      setSystemHealth(null);
      return;
    }

    let mounted = true;
    const loadSystemHealth = async () => {
      try {
        const response = await api.get('/system/health', { silentLoading: true });
        if (mounted) {
          setSystemHealth({
            status: response.data?.status,
            active_sessions: response.data?.active_sessions,
            recent_errors: response.data?.recent_errors || [],
          });
        }
      } catch {
        if (mounted) setSystemHealth(null);
      }
    };

    loadSystemHealth();
    const interval = setInterval(loadSystemHealth, 60000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [isAdmin, isAuthenticated]);

  // Track pathname changes
  useEffect(() => {
    onPathChange(pathname);
  }, [pathname, onPathChange]);

  // Listen for browser popstate (back/forward via browser buttons)
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const handler = () => onPopState();
    window.addEventListener('popstate', handler);
    return () => window.removeEventListener('popstate', handler);
  }, [onPopState]);

  // Global command palette shortcut (Ctrl/Cmd + K) — only on the focused screen
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || !isScreenFocused) return;
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isScreenFocused]);

  const isAuthRoute = AUTH_ROUTES.has(pathname);
  const pageLabel = (() => {
    const clean = String(pathname || '/dashboard').split('?')[0];
    const navMatch = (BASE_NAV_ITEMS as any[])
      .filter((item) => !item.section && item.href)
      .map((item) => ({ ...item, path: String(item.href).split('?')[0] }))
      .filter((item) => item.path.length > 1 && (clean === item.path || clean.startsWith(`${item.path}/`)))
      .sort((a, b) => b.path.length - a.path.length)[0];
    if (navMatch) {
      const tkey = NAV_TKEY[navMatch.key];
      if (tkey) {
        const localized = t(tkey);
        if (localized !== tkey) return localized;
      }
      return navMatch.label;
    }
    const parts = clean.split('/').filter(Boolean);
    if (!parts.length) return t('nav.home');
    return parts[parts.length - 1].replace(/[-_]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
  })();
  if (Platform.OS !== 'web' || isAuthRoute) return null;

  const handleSignOutConfirmed = async () => {
    setSigningOut(true);
    try {
      await logout();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/GlobalNavBar.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSigningOut(false);
    setShowSignOutConfirm(false);
    router.replace('/auth/login?logout=1' as any);
  };

  const hasCurrencyMismatch = !!geoCurrency && !!currentCurrency && geoCurrency !== currentCurrency;
  const detectedLanguageShort = (detectedLocale || 'en').split('-')[0].toUpperCase();
  const hasLanguageMismatch = !!detectedLanguageShort && detectedLanguageShort !== languageShort;
  const hasAnyMismatch = (hasCurrencyMismatch || hasLanguageMismatch) && !hintDismissed && !hintSuppressedServerSide;
  const hideExecutiveQuickControls = String(pathname || '').startsWith('/executive-dashboard');
  const warningColor = colors.warning;
  const warningBg = `${colors.warning}16`;
  const warningBorder = `${colors.warning}35`;
  const signOutBg = `${colors.error}14`;
  const systemHealthStatus = String(systemHealth?.status || 'unknown');
  const systemHealthColor = systemHealthStatus === 'healthy' ? colors.success : systemHealthStatus === 'degraded' ? colors.warning : colors.error;
  const systemHealthBg = `${systemHealthColor}14`;
  const systemHealthBorder = `${systemHealthColor}30`;
  const systemHealthLabel = systemHealthStatus === 'healthy' ? t('globalNav.systemHealthy') : systemHealthStatus === 'degraded' ? t('globalNav.systemDegraded') : t('globalNav.systemOffline');
  const isMac = Platform.OS === 'web' && typeof navigator !== 'undefined' && Boolean(navigator.platform?.includes('Mac'));

  return (
    <View data-testid="global-nav-wrap" testID="global-nav-wrap">
      {/* Top-bar hover micro-interactions (web only, token-driven) */}
      {Platform.OS === 'web' && (
        <style dangerouslySetInnerHTML={{ __html: `
          [data-testid="global-nav-bar"] [role="button"] { transition: transform .15s ease, opacity .15s ease; }
          [data-testid="global-nav-bar"] [role="button"]:hover { transform: translateY(-1px); }
        ` }} />
      )}
      <View
        style={[styles.bar, { backgroundColor: colors.surfaceElevated, borderBottomColor: colors.border }, Platform.OS === 'web' ? getShadow('sm', darkMode) : null, dimmed ? { opacity: 0.4, pointerEvents: 'none' as any, transform: [{ scale: 0.995 }] } : null]}
        data-testid="global-nav-bar" testID="global-nav-bar"
      >
        <View style={{ marginRight: 12, minWidth: 0, flexShrink: 1 }} data-testid="global-nav-page-context" testID="global-nav-page-context">
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.6, textTransform: 'uppercase', fontFamily: BODY_FONT_FAMILY }} data-testid="global-nav-page-context-label" testID="global-nav-page-context-label">
            {t('globalNav.commandContext')}
          </Text>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '900', letterSpacing: -0.5, fontFamily: DISPLAY_FONT_FAMILY }} numberOfLines={1} data-testid="global-nav-page-context-title" testID="global-nav-page-context-title">
            {pageLabel}
          </Text>
        </View>

        <TouchableOpacity
          style={[styles.btn, !canGoBack && styles.btnDisabled]}
          onPress={goBack}
          disabled={!canGoBack}
          data-testid="global-nav-back-btn" testID="global-nav-back-btn"
          accessibilityLabel="Go back"
          accessibilityRole="button"
        >
          <Ionicons name="chevron-back" size={16} color={canGoBack ? colors.text : colors.textMuted} />
          <Text style={[styles.label, { color: canGoBack ? colors.text : colors.textMuted }]}>{t('nav.back')}</Text>
        </TouchableOpacity>

        <View style={[styles.divider, { backgroundColor: colors.border }]} />

        <TouchableOpacity
          style={[styles.btn, !canGoForward && styles.btnDisabled]}
          onPress={goForward}
          disabled={!canGoForward}
          data-testid="global-nav-forward-btn" testID="global-nav-forward-btn"
          accessibilityLabel="Go forward"
          accessibilityRole="button"
        >
          <Text style={[styles.label, { color: canGoForward ? colors.text : colors.textMuted }]}>{t('nav.forward')}</Text>
          <Ionicons name="chevron-forward" size={16} color={canGoForward ? colors.text : colors.textMuted} />
        </TouchableOpacity>

        <View style={{ flex: 1 }} />

        {/* Quick actions: command palette search + Ask Nova */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginRight: 8 }} data-testid="global-nav-quick-actions" testID="global-nav-quick-actions">
          <TouchableOpacity
            style={[styles.chipBtn, { borderColor: colors.border, backgroundColor: colors.surfaceHover }]}
            onPress={() => setPaletteOpen(true)}
            data-testid="global-nav-search-btn" testID="global-nav-search-btn"
            accessibilityLabel="Open command palette search"
            accessibilityRole="button"
          >
            <Ionicons name="search-outline" size={13} color={colors.textMuted} />
            <Text style={[styles.chipLabel, { color: colors.textSec }]}>{t('globalNav.searchLabel')}</Text>
            <View style={{ paddingHorizontal: 5, paddingVertical: 2, borderRadius: 5, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border }}>
              <Text style={{ fontSize: 9.5, fontWeight: '700', color: colors.textMuted, fontFamily: BODY_FONT_FAMILY }}>{isMac ? '\u2318K' : 'Ctrl+K'}</Text>
            </View>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.chipBtn, { borderColor: `${colors.primary}33`, backgroundColor: colors.primarySoft }]}
            onPress={() => router.push('/help' as any)}
            data-testid="global-nav-ask-nova-btn" testID="global-nav-ask-nova-btn"
            accessibilityLabel="Ask Nova assistant"
            accessibilityRole="button"
          >
            <Ionicons name="sparkles" size={13} color={colors.primary} />
            <Text style={[styles.chipLabel, { color: colors.primary }]}>{t('globalNav.askNova')}</Text>
          </TouchableOpacity>
        </View>

        {!hideExecutiveQuickControls && (
          <View style={styles.quickControls} data-testid="global-nav-locale-controls" testID="global-nav-locale-controls">
            <TouchableOpacity
              style={[styles.chipBtn, { borderColor: colors.border, backgroundColor: colors.surfaceHover }]}
              onPress={() => router.push({ pathname: '/language-selector', params: { returnTo: pathname || '/dashboard' } } as any)}
              data-testid="global-nav-language-selector-btn" testID="global-nav-language-selector-btn"
              accessibilityLabel="Top navigation language selector"
              accessibilityRole="button"
            >
              <Ionicons name="language-outline" size={13} color={hasLanguageMismatch ? warningColor : colors.textMuted} />
              <Text style={[styles.chipLabel, { color: hasLanguageMismatch ? warningColor : colors.text }]}>{languageShort}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.chipBtn, { borderColor: hasCurrencyMismatch ? warningBorder : colors.border, backgroundColor: hasCurrencyMismatch ? warningBg : colors.surfaceHover }]}
              onPress={() => router.push('/currency-selector')}
              data-testid="global-nav-currency-selector-btn" testID="global-nav-currency-selector-btn"
              accessibilityLabel="Top navigation currency selector"
              accessibilityRole="button"
            >
              <Ionicons name="cash-outline" size={13} color={hasCurrencyMismatch ? warningColor : colors.textMuted} />
              <Text style={[styles.chipLabel, { color: hasCurrencyMismatch ? warningColor : colors.text }]}>{currentCurrency}</Text>
            </TouchableOpacity>

            {isAuthenticated && isAdmin && systemHealth && (
              <TouchableOpacity
                style={[styles.chipBtn, { borderColor: systemHealthBorder, backgroundColor: systemHealthBg }]}
                onPress={() => router.push('/admin-console?category=operations&tab=system-health' as any)}
                data-testid="global-nav-system-health-badge"
                testID="global-nav-system-health-badge"
                accessibilityLabel="Open system health dashboard"
                accessibilityRole="button"
              >
                <View style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: systemHealthColor }} data-testid="global-nav-system-health-dot" testID="global-nav-system-health-dot" />
                <Text style={[styles.chipLabel, { color: systemHealthColor }]} data-testid="global-nav-system-health-label" testID="global-nav-system-health-label">
                  {systemHealthLabel}
                </Text>
              </TouchableOpacity>
            )}

            {isAuthenticated && (
              <TouchableOpacity
                style={[styles.chipBtn, styles.signOutBtn, { borderColor: signOutBg, backgroundColor: signOutBg }]}
                onPress={() => setShowSignOutConfirm(true)}
                data-testid="global-nav-signout-btn" testID="global-nav-signout-btn"
                accessibilityLabel="Top navigation sign out"
                accessibilityRole="button"
              >
                <Ionicons name="log-out-outline" size={13} color={colors.error} />
                <Text style={[styles.chipLabel, styles.signOutLabel]}>{t('nav.logout')}</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      </View>

      <EnterpriseSignOutConfirmModal
        visible={showSignOutConfirm}
        loading={signingOut}
        onCancel={() => setShowSignOutConfirm(false)}
        onConfirm={handleSignOutConfirmed}
        darkMode={darkMode}
        testIdPrefix="global-nav-signout"
      />

      <CommandPalette visible={paletteOpen && isScreenFocused} onClose={() => setPaletteOpen(false)} />

      {hasAnyMismatch && !hideExecutiveQuickControls && (
        <View style={[styles.hintBar, { backgroundColor: warningBg, borderBottomColor: warningBorder }, dimmed ? { opacity: 0.35, pointerEvents: 'none' as any } : null]} data-testid={hasLanguageMismatch ? 'global-nav-language-mismatch-hint' : 'global-nav-currency-mismatch-hint'} testID={hasLanguageMismatch ? 'global-nav-language-mismatch-hint' : 'global-nav-currency-mismatch-hint'}>
          <TouchableOpacity accessibilityLabel="Global nav mismatch hint open button"
            onPress={() => {
              api.post('/i18n/language-guidance/event', {
                event_type: 'open',
                source: hasLanguageMismatch ? 'topnav_language_hint' : 'topnav_currency_hint',
                metadata: { detected_language: detectedLanguageShort, current_language: languageShort, detected_currency: geoCurrency, current_currency: currentCurrency },
              }).catch(() => {});
              router.push(hasLanguageMismatch
                ? ({ pathname: '/language-selector', params: { returnTo: pathname || '/dashboard' } } as any)
                : '/currency-selector');
            }}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 }}
            data-testid="global-nav-mismatch-hint-open" testID="global-nav-mismatch-hint-open"
          >
            <Ionicons name="alert-circle-outline" size={13} color={warningColor} />
            <Text style={[styles.hintText, { color: warningColor }]}>
              {hasLanguageMismatch
                ? txv('globalNav.hint.languageMismatch', 'Detected locale suggests {lang}. Tap to align language preferences.').replace('{lang}', detectedLanguageShort)
                : txv('globalNav.hint.currencyMismatch', 'Detected region currency is {currency}. Tap to align preferences.').replace('{currency}', geoCurrency)}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel="Global nav mismatch hint snooze button"
            onPress={() => {
              setHintDismissed(true);
              api.post('/i18n/language-guidance/preference', { action: 'snooze', snooze_hours: 24 }).catch(() => {});
              api.post('/i18n/language-guidance/event', {
                event_type: 'dismiss',
                source: hasLanguageMismatch ? 'topnav_language_hint_snooze' : 'topnav_currency_hint_snooze',
                metadata: { detected_language: detectedLanguageShort, current_language: languageShort, detected_currency: geoCurrency, current_currency: currentCurrency, snooze_hours: 24 },
              }).catch(() => {});
            }}
            style={{ marginLeft: 4, paddingHorizontal: 6, height: 22, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: warningBorder }}
            data-testid="global-nav-mismatch-hint-snooze" testID="global-nav-mismatch-hint-snooze"
          >
            <Text style={{ color: warningColor, fontSize: 10, fontWeight: '700' }}>24h</Text>
          </TouchableOpacity>
          <TouchableOpacity accessibilityLabel="Global nav mismatch hint dismiss button"
            onPress={() => {
              setHintDismissed(true);
              api.post('/i18n/language-guidance/preference', { action: 'dismiss', snooze_hours: 24 }).catch(() => {});
              api.post('/i18n/language-guidance/event', {
                event_type: 'dismiss',
                source: hasLanguageMismatch ? 'topnav_language_hint' : 'topnav_currency_hint',
                metadata: { detected_language: detectedLanguageShort, current_language: languageShort, detected_currency: geoCurrency, current_currency: currentCurrency },
              }).catch(() => {});
            }}
            style={{ marginLeft: 8, width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center' }}
            data-testid="global-nav-mismatch-hint-dismiss" testID="global-nav-mismatch-hint-dismiss"
          >
            <Ionicons name="close" size={13} color={warningColor} />
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}
