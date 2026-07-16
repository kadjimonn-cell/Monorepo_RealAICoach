import React, { createContext, useContext, ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, Text, View } from 'react-native';
import { usePathname } from 'expo-router';
import { getLanguageCode, LanguageCode, SUPPORTED_LANGUAGES } from '../utils/translations';
import { loadLocale, getCachedLocale, isLocaleLoaded } from './translationLoader';
import { useTheme } from '../context/ThemeContext';
import { trackTranslationFallbackHit } from './fallbackTelemetry';
import { useAutoTranslate } from '../hooks/useAutoTranslate';
import { withAlpha } from '../utils/colorAlpha';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

interface LanguageContextType {
  language: string;
  languageCode: LanguageCode;
  setLanguage: (language: string) => void;
  t: (key: string) => string;
  isRTL: boolean;
  isLanguageReady: boolean;
  currentRouteReady: boolean;
  currentRouteKey: string;
  switchEpoch: number;
  markRouteReady: (routeKey?: string) => void;
  isRouteReady: (routeKey?: string) => boolean;
  supportedLanguages: typeof SUPPORTED_LANGUAGES;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

// Watchdog timeout for language switch - clears stuck "Applying language..." state
const I18N_SWITCH_TIMEOUT_MS = 2800;

/**
 * Sync `<html lang>` and `<html dir>` to the active language.
 *
 * Auto-translation v2: this replaces the hardcoded `<html lang="en"
 * translate="no">` that bypassed both the platform's i18n and the
 * browser's native fallback engine. Now:
 *   - screen-readers announce content in the active language,
 *   - search engines see the correct lang attribute on hreflang variants,
 *   - the browser's native auto-translate is allowed as a safety net for
 *     any string the static dictionary genuinely misses.
 */
function syncHtmlLangAttr(code: string, isRTL: boolean) {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return;
  try {
    document.documentElement.setAttribute('lang', code);
    document.documentElement.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
  } catch (error) { handleAppRecoverableError({ scope: 'src/i18n/LanguageContext.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

function readStoredLanguageCodeSync(): LanguageCode {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return 'en';
  try {
    const raw = window.localStorage.getItem('app_theme');
    if (!raw) return 'en';
    const parsed = JSON.parse(raw);
    const candidate =
      (typeof parsed?.languageCode === 'string' && parsed.languageCode.trim())
      || (typeof parsed?.language === 'string' && parsed.language.trim())
      || 'en';
    return getLanguageCode(candidate) as LanguageCode;
  } catch {
    return 'en';
  }
}

export const LanguageProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { language, languageCode, languageSwitching, setLanguage, colors } = useTheme();
  const pathname = usePathname();
  const [, setLocaleReady] = useState(0);
  const [bootLanguageCode] = useState<LanguageCode>(() => readStoredLanguageCodeSync());
  const [resolvedLanguageCode, setResolvedLanguageCode] = useState<LanguageCode>(() => bootLanguageCode || 'en');
  const [localeLoading, setLocaleLoading] = useState(false);
  const [switchEpoch, setSwitchEpoch] = useState(0);
  const [routeReadyByEpoch, setRouteReadyByEpoch] = useState<Record<string, number>>({});
  const switchWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSwitchTokenAppliedRef = useRef<string>('');
  const { tt } = useAutoTranslate();

  const resolveRouteKey = useCallback((candidate?: string) => {
    const base = String(
      candidate
      || pathname
      || ((Platform.OS === 'web' && typeof window !== 'undefined') ? window.location?.pathname : '')
      || '/'
    ).trim();
    return base || '/';
  }, [pathname]);

  const currentRouteKey = resolveRouteKey();

  const markRouteReady = useCallback((routeKey?: string) => {
    const key = resolveRouteKey(routeKey);
    setRouteReadyByEpoch((prev) => {
      if (prev[key] === switchEpoch) return prev;
      return { ...prev, [key]: switchEpoch };
    });
  }, [resolveRouteKey, switchEpoch]);

  const isRouteReady = useCallback((routeKey?: string) => {
    if (languageCode === 'en') return true;
    const key = resolveRouteKey(routeKey);
    return routeReadyByEpoch[key] === switchEpoch;
  }, [languageCode, resolveRouteKey, routeReadyByEpoch, switchEpoch]);

  const currentRouteReady = isRouteReady(currentRouteKey);
  const isLanguageReady = !localeLoading && !languageSwitching && currentRouteReady;

  const getActiveSwitchToken = useCallback(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return '';
    return String((window as any).__racI18nSwitchToken || '').trim();
  }, []);

  // Load non-English locale on demand when language changes.
  // DOM translation engine lifecycle is centralized in GlobalTranslationProvider
  // to avoid duplicate reinit storms.
  useEffect(() => {
    let cancelled = false;
    setSwitchEpoch((prev) => prev + 1);
    setRouteReadyByEpoch({});

    const isRTL = SUPPORTED_LANGUAGES.find(l => l.code === languageCode)?.rtl || false;
    syncHtmlLangAttr(languageCode, isRTL);
    if (languageCode !== 'en') {
      setLocaleLoading(true);
      loadLocale(languageCode)
        .then(() => {
          if (cancelled) return;
          if (isLocaleLoaded(languageCode)) {
            setResolvedLanguageCode(languageCode);
          }
          // Trigger re-render so `t()` picks up the new locale
          setLocaleReady((v) => v + 1);
        })
        .finally(() => {
          if (!cancelled) {
            setLocaleLoading(false);
          }
        });
      return () => {
        cancelled = true;
      };
    }

    setResolvedLanguageCode('en');
    setLocaleLoading(false);
    return () => {
      cancelled = true;
    };
  }, [languageCode]);

  useEffect(() => {
    // Synchronous localStorage warm-start (web): prefetch locale before ThemeContext completes hydration.
    if (bootLanguageCode === 'en' || bootLanguageCode === languageCode) return;
    let cancelled = false;
    loadLocale(bootLanguageCode)
      .then(() => {
        if (cancelled) return;
        if (isLocaleLoaded(bootLanguageCode)) {
          setResolvedLanguageCode(bootLanguageCode);
        }
        setLocaleReady((v) => v + 1);
      })
      .catch(() => {
        // best-effort warm-start
      });
    return () => {
      cancelled = true;
    };
  }, [bootLanguageCode, languageCode]);

  useEffect(() => {
    if (localeLoading) return;
    markRouteReady(currentRouteKey);
  }, [currentRouteKey, localeLoading, markRouteReady]);

  useEffect(() => {
    if (languageCode === 'en' || Platform.OS !== 'web') {
      return;
    }

    const activeToken = getActiveSwitchToken();
    if (!activeToken) {
      return;
    }

    if (activeToken === lastSwitchTokenAppliedRef.current) {
      return;
    }

    if (switchWatchdogRef.current) {
      clearTimeout(switchWatchdogRef.current);
      switchWatchdogRef.current = null;
    }

    switchWatchdogRef.current = setTimeout(() => {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const tokenAtTimeout = String((window as any).__racI18nSwitchToken || '').trim();
        if (tokenAtTimeout === activeToken) {
          (window as any).__racI18nBackgroundOnly = false;
          (window as any).__racI18nSwitching = false;
          (window as any).__racI18nSwitchToken = '';
          lastSwitchTokenAppliedRef.current = activeToken;
          markRouteReady(currentRouteKey);
        }
      }
    }, I18N_SWITCH_TIMEOUT_MS);

    return () => {
      if (switchWatchdogRef.current) {
        clearTimeout(switchWatchdogRef.current);
        switchWatchdogRef.current = null;
      }
    };
  }, [currentRouteKey, getActiveSwitchToken, languageCode, markRouteReady]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const backgroundOnly = !isLanguageReady;
    (window as any).__racI18nSwitching = backgroundOnly;
    (window as any).__racI18nBackgroundOnly = backgroundOnly;
    (window as any).__racI18nRouteReady = currentRouteReady;
    (window as any).__racI18nRoute = currentRouteKey;
    (window as any).__racI18nSwitchEpoch = switchEpoch;

    try {
      window.dispatchEvent(new CustomEvent('rac:i18n-readiness', {
        detail: {
          languageCode,
          route: currentRouteKey,
          routeReady: currentRouteReady,
          switchEpoch,
          backgroundOnly,
        },
      }));
    } catch (error) { handleAppRecoverableError({ scope: 'src/i18n/LanguageContext.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [currentRouteKey, currentRouteReady, isLanguageReady, languageCode, switchEpoch]);

  useEffect(() => {
    return () => {
      if (switchWatchdogRef.current) {
        clearTimeout(switchWatchdogRef.current);
        switchWatchdogRef.current = null;
      }
    };
  }, []);

  const t = useCallback((key: string): string => {
    const fallbackLanguageCode = (localeLoading || languageSwitching)
      ? resolvedLanguageCode
      : languageCode;
    const locale = getCachedLocale(fallbackLanguageCode);
    const source = getCachedLocale('en')[key] || key;
    const localized = locale[key] || source;
    if (
      fallbackLanguageCode === 'en'
      || localized !== source
      || source === key
      || localeLoading
      || languageSwitching
    ) {
      return localized;
    }
    trackTranslationFallbackHit(languageCode, key);
    return tt(source);
  }, [languageCode, languageSwitching, localeLoading, resolvedLanguageCode, tt]);

  const isRTL = SUPPORTED_LANGUAGES.find(l => l.code === languageCode)?.rtl || false;
  const showLanguageSyncIndicator = !isLanguageReady && languageCode !== 'en';

  return (
    <LanguageContext.Provider
      value={{
        language,
        languageCode,
        setLanguage,
        t,
        isRTL,
        isLanguageReady,
        currentRouteReady,
        currentRouteKey,
        switchEpoch,
        markRouteReady,
        isRouteReady,
        supportedLanguages: SUPPORTED_LANGUAGES,
      }}
    >
      {children}
      {showLanguageSyncIndicator ? (
        <View
          pointerEvents="none"
          style={{
            width: '100%',
            paddingHorizontal: 12,
            paddingBottom: 10,
            alignItems: 'center',
            justifyContent: 'center',
          }}
          data-testid="global-language-switch-loading-overlay"
          testID="global-language-switch-loading-overlay"
        >
          <View
            style={{
              width: '100%',
              maxWidth: 420,
              borderRadius: 14,
              paddingHorizontal: 14,
              paddingVertical: 12,
              backgroundColor: withAlpha(colors.surface || colors.card || colors.bgAlt || colors.bg, 'EE'),
              borderWidth: 1,
              borderColor: withAlpha(colors.primary, '2E'),
              gap: 8,
            }}
            data-testid="global-language-switch-loading-card"
            testID="global-language-switch-loading-card"
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <ActivityIndicator size="small" color={colors.primary} />
              <Text
                style={{ fontSize: 12, fontWeight: '700', color: colors.text }}
                data-testid="global-language-switch-loading-text"
                testID="global-language-switch-loading-text"
              >
                {t('language.syncing')}
              </Text>
            </View>
            <View
              style={{
                height: 7,
                borderRadius: 999,
                backgroundColor: withAlpha(colors.primary, '24'),
              }}
              data-testid="global-language-switch-skeleton-line-1"
              testID="global-language-switch-skeleton-line-1"
            />
            <View
              style={{
                height: 7,
                width: '78%',
                borderRadius: 999,
                backgroundColor: withAlpha(colors.primary, '1A'),
              }}
              data-testid="global-language-switch-skeleton-line-2"
              testID="global-language-switch-skeleton-line-2"
            />
          </View>
        </View>
      ) : null}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};

export default LanguageContext;
