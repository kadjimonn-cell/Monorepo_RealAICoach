import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { Appearance, Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getLanguageCode, SUPPORTED_LANGUAGES } from '../utils/translations';
import { loadLocale } from '../i18n/translationLoader';
import api, { clearCache } from '../services/api';
import { useAuth } from './AuthContext';

import { V1_LIGHT, V1_DARK, THEME_VERSION } from '../theme/v1';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

// Theme mode can be 'system', 'light', or 'dark'
type ThemeMode = 'system' | 'light' | 'dark';

interface ThemeContextType {
  darkMode: boolean;           // Computed: actual dark mode state
  _darkMode?: boolean;         // Legacy alias (backward compatibility)
  themeMode: ThemeMode;        // User preference: 'system', 'light', 'dark'
  accentColor: string;
  language: string;
  languageCode: string;
  languageSwitching: boolean;
  fontSize: string;
  previewEnabled: boolean;
  hasPendingPreviewChanges: boolean;
  isThemePreview: boolean;
  toggleThemePreview: () => void;
  exitThemePreview: () => void;
  setThemeMode: (val: ThemeMode) => void;
  setDarkMode: (val: boolean) => void;  // Legacy - sets to 'dark' or 'light'
  setAccentColor: (val: string) => void;
  setLanguage: (val: string) => void;
  setFontSize: (val: string) => void;
  setPreviewEnabled: (val: boolean) => void;
  savePreviewChanges: () => void;
  cancelPreviewChanges: () => void;
  colors: typeof LIGHT_COLORS;
  _colors?: typeof LIGHT_COLORS; // Legacy alias (backward compatibility)
  systemColorScheme: 'light' | 'dark' | null;
}

// Global source of truth for the permanent RealAICoach v2 design system.
export { THEME_VERSION };

const LIGHT_COLORS = V1_LIGHT;
const DARK_COLORS = V1_DARK;

const THEME_NEUTRAL_FALLBACK_COLORS = {
  ...V1_LIGHT,
  surfaceElevated: (V1_LIGHT as any)?.surfaceElevated || (V1_LIGHT as any)?.card || (V1_LIGHT as any)?.surface || (V1_LIGHT as any)?.bg,
  purpleSoft: (V1_LIGHT as any)?.purpleSoft || (V1_LIGHT as any)?.primarySoft || (V1_LIGHT as any)?.surfaceHover,
} as typeof LIGHT_COLORS;

const resolveThemeColors = (preferDark: boolean): typeof LIGHT_COLORS => {
  const preferred = (preferDark ? DARK_COLORS : LIGHT_COLORS) as any;
  if (preferred && typeof preferred === 'object') {
    return { ...THEME_NEUTRAL_FALLBACK_COLORS, ...preferred } as typeof LIGHT_COLORS;
  }

  const branchFallback = (preferDark ? V1_DARK : V1_LIGHT) as any;
  if (branchFallback && typeof branchFallback === 'object') {
    return { ...THEME_NEUTRAL_FALLBACK_COLORS, ...branchFallback } as typeof LIGHT_COLORS;
  }

  return THEME_NEUTRAL_FALLBACK_COLORS;
};

const getLanguageNameByCode = (code: string): string => {
  const normalized = getLanguageCode(code || 'en');
  return SUPPORTED_LANGUAGES.find((entry) => entry.code === normalized)?.name || 'English';
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    // SSR fallback: return neutral/light-safe defaults when ThemeProvider isn't mounted yet
    return {
      colors: THEME_NEUTRAL_FALLBACK_COLORS,
      _colors: THEME_NEUTRAL_FALLBACK_COLORS,
      darkMode: false,
      _darkMode: false,
      themeMode: 'system' as ThemeMode,
      setThemeMode: () => {},
      accentColor: V1_LIGHT.primary,
      setAccentColor: () => {},
      language: 'English',
      setLanguage: () => {},
      languageCode: 'en',
      languageSwitching: false,
      t: (key: string) => key,
    } as ThemeContextType;
  }

  const safeColors = {
    ...THEME_NEUTRAL_FALLBACK_COLORS,
    ...((ctx as any)?.colors || {}),
  } as typeof LIGHT_COLORS;

  return {
    ...ctx,
    colors: safeColors,
    _colors: safeColors,
    _darkMode: Boolean((ctx as any)?._darkMode ?? ctx.darkMode),
  };
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [nativeSystemDark, setNativeSystemDark] = useState(Appearance.getColorScheme() === 'dark');
  const { user } = useAuth();
  
  // Theme mode: 'system' (default), 'light', or 'dark'
  const [themeMode, setThemeModeState] = useState<ThemeMode>('system');
  const [accentColor, setAccentColorState] = useState(V1_LIGHT.primary);
  const [language, setLanguageState] = useState('English');
  const [languageCode, setLanguageCode] = useState('en');
  const [languageSwitching, setLanguageSwitching] = useState(false);
  const [fontSize, setFontSizeState] = useState('Medium');
  const [previewEnabled, setPreviewEnabledState] = useState(false);
  const [previewAccentColor, setPreviewAccentColor] = useState(V1_LIGHT.primary);
  const [previewLanguage, setPreviewLanguage] = useState('English');
  const [previewLanguageCode, setPreviewLanguageCode] = useState('en');
  const [isThemePreview, setIsThemePreview] = useState(false);
  const [previewDarkOverride, setPreviewDarkOverride] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);
  const dbSyncedRef = useRef(false);
  const languagePolicySyncRef = useRef('');
  const languageSwitchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const languageSwitchTokenRef = useRef<string>('');
  const LANGUAGE_SWITCH_FAILSAFE_MS = 3200;

  useEffect(() => {
    dbSyncedRef.current = false;
  }, [user?.user_id, (user as any)?.theme_preference]);

  const persistLanguagePreference = useCallback((code: string) => {
    const normalizedCode = getLanguageCode(code);
    if (!user?.user_id) return;
    const syncKey = `${user.user_id}:${normalizedCode}`;
    if (languagePolicySyncRef.current === syncKey) return;
    languagePolicySyncRef.current = syncKey;
    clearCache('/i18n/user-preference');
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      try {
        window.sessionStorage.removeItem('live_query_snapshot_v1:/i18n/user-preference');
      } catch {
        // no-op: best effort snapshot invalidation
      }
    }
    api.post('/i18n/user-preference', { language: normalizedCode }).catch(() => {});
    api.put('/auth/profile', { language_preference: normalizedCode }).catch(() => {});
  }, [user?.user_id]);

  const saveTheme = useCallback(async (updates: any) => {
    try {
      const data = await AsyncStorage.getItem('app_theme');
      const current = data ? JSON.parse(data) : {};
      const merged = { ...current, ...updates };
      await AsyncStorage.setItem('app_theme', JSON.stringify(merged));
    } catch (e) { console.error('Theme save error:', e); }
  }, []);

  // Track system preference reactively on web via matchMedia
  // Initialize synchronously so system-dark users don't see a light-theme flash before effect sync.
  const [webSystemDark, setWebSystemDark] = useState(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return false;
  });
  const systemColorScheme: 'light' | 'dark' = Platform.OS === 'web'
    ? (webSystemDark ? 'dark' : 'light')
    : (nativeSystemDark ? 'dark' : 'light');

  // Compute actual dark mode based on theme mode and system preference
  const computedDarkMode = themeMode === 'system'
    ? (Platform.OS === 'web' ? webSystemDark : nativeSystemDark)
    : themeMode === 'dark';

  // When theme preview is active, override the computed value
  const darkMode = isThemePreview ? previewDarkOverride : computedDarkMode;

  // Listen for system theme changes (web: matchMedia, native: Appearance)
  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const mql = window.matchMedia('(prefers-color-scheme: dark)');
      // Sync initial value after hydration (SSR may have returned false)
      setWebSystemDark(mql.matches);
      const handler = (e: MediaQueryListEvent) => {
        setWebSystemDark(e.matches);
      };
      mql.addEventListener('change', handler);
      return () => mql.removeEventListener('change', handler);
    } else {
      const subscription = Appearance.addChangeListener(({ colorScheme }) => {
        setNativeSystemDark(colorScheme === 'dark');
      });
      return () => subscription?.remove();
    }
  }, [themeMode]);

  // ── Theme Transition Effect ──
  // Instead of always-on transitions (which interfere with hovers/interactions),
  // we briefly add a global transition class during theme switches, then remove it.
  const transitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    const root = document.documentElement;
    root.setAttribute('data-theme-mode', themeMode);
    root.setAttribute('data-theme-active', darkMode ? 'dark' : 'light');
    
    // Directly set backgrounds to prevent SSR flash
    const activeTokens = resolveThemeColors(darkMode);
    const bgColor = activeTokens.bg;
    root.style.backgroundColor = bgColor;
    document.body.style.backgroundColor = bgColor;
    const rootEl = document.getElementById('root');
    if (rootEl) rootEl.style.backgroundColor = bgColor;

    // Set CSS custom properties for class components and non-React contexts
    root.style.setProperty('--app-bg', bgColor);
    root.style.setProperty('--app-card-bg', activeTokens.surfaceElevated);
    root.style.setProperty('--app-text', activeTokens.text);
    root.style.setProperty('--app-text-sec', activeTokens.textSec);
    root.style.setProperty('--app-text-muted', activeTokens.textMuted);
    root.style.setProperty('--app-border', activeTokens.border);
    root.style.setProperty('--app-primary', activeTokens.primary);
    root.style.setProperty('--app-primary-text', activeTokens.primaryText);
    root.style.setProperty('--app-primary-soft', activeTokens.primarySoft);
    root.style.setProperty('--app-surface', activeTokens.surface);
    // V2 semantic status colours — exposed so that admin panels using
    // `var(--app-*)` directly (without calling useAdminTheme) pick up the
    // themed palette instead of frozen light-mode fallbacks. See fix notes
    // "Executive Console panels missing v2 light/dark theme" (2026-04-24).
    root.style.setProperty('--app-success', activeTokens.success);
    root.style.setProperty('--app-success-soft', activeTokens.successSoft);
    root.style.setProperty('--app-warning', activeTokens.warning);
    root.style.setProperty('--app-warning-soft', activeTokens.warningSoft);
    root.style.setProperty('--app-error', activeTokens.error);
    root.style.setProperty('--app-error-soft', activeTokens.errorSoft);
    root.style.setProperty('--app-info', activeTokens.info);
    root.style.setProperty('--app-info-soft', activeTokens.infoSoft);
    // Structural / layering tokens — these were REFERENCED by 40+ panels
    // via `var(--app-surface-hover, ...)` / `var(--app-card-muted, ...)` /
    // `var(--app-border-strong, ...)` but never injected, so panels silently
    // fell back to their light-mode fallback hex and never flipped in dark
    // mode. Exposing them closes that reactivity gap.
    root.style.setProperty('--app-surface-hover', activeTokens.surfaceHover);
    root.style.setProperty('--app-card-muted', activeTokens.cardMuted);
    root.style.setProperty('--app-border-strong', activeTokens.borderStrong);
    root.style.setProperty('--app-border-bright', activeTokens.borderBright);
    root.style.setProperty('--app-divider', activeTokens.divider);
    // Chart tokens — used by analytics charts in admin panels so bars/axes/
    // gridlines read correctly on both themes.
    root.style.setProperty('--app-chart-grid', activeTokens.chartGrid);
    root.style.setProperty('--app-chart-axis', activeTokens.chartAxis);

    // Inject the transition stylesheet (create or update)
    const styleId = 'realaicoach-theme-transitions';
    let styleEl = document.getElementById(styleId) as HTMLStyleElement | null;
    if (!styleEl) {
      styleEl = document.createElement('style');
      styleEl.id = styleId;
      document.head.appendChild(styleEl);
    }
    styleEl.textContent = `
      html.theme-switching,
      html.theme-switching *,
      html.theme-switching *::before,
      html.theme-switching *::after {
        transition: background-color 320ms ease, color 320ms ease, border-color 320ms ease, box-shadow 320ms ease, fill 320ms ease, stroke 320ms ease !important;
        transition-delay: 0s !important;
      }
    `;

    // Activate the transition class
    root.classList.add('theme-switching');
    if (transitionTimerRef.current) clearTimeout(transitionTimerRef.current);
    transitionTimerRef.current = setTimeout(() => {
      root.classList.remove('theme-switching');
    }, 380);
  }, [themeMode, darkMode]);

  // Global language adaptation policy:
  // account profile > local storage > browser auto-detect
  useEffect(() => {
    if (!isLoaded || !user?.user_id) return;

    const profileRaw = String((user as any)?.language_preference || '').trim();
    const syncKey = `${user.user_id}:${profileRaw}`;
    if (languagePolicySyncRef.current === syncKey) return;
    languagePolicySyncRef.current = syncKey;

    let cancelled = false;
    const applyLanguage = (incomingCode: string) => {
      const nextCode = getLanguageCode(incomingCode || 'en');
      const nextLanguage = getLanguageNameByCode(nextCode);
      if (!cancelled) {
        setLanguageState(nextLanguage);
        setLanguageCode(nextCode);
      }
      saveTheme({ language: nextLanguage, languageCode: nextCode });
      return nextCode;
    };

    const syncLanguage = async () => {
      // 1) Account profile is highest priority when present.
      if (profileRaw) {
        const profileCode = applyLanguage(profileRaw);
        clearCache('/i18n/user-preference');
        api.post('/i18n/user-preference', { language: profileCode }).catch(() => {});
        return;
      }

      // 2) Backward compatibility: migrate historic /i18n preference into account profile.
      try {
        const prefRes = await api.get('/i18n/user-preference', {
          silentLoading: true,
          skipDedupe: true,
          timeout: 8000,
        });
        const hasPreference = Boolean(prefRes?.data?.has_preference);
        const serverCode = getLanguageCode(String(prefRes?.data?.language || 'en'));

        if (hasPreference) {
          const appliedCode = applyLanguage(serverCode);
          api.put('/auth/profile', { language_preference: appliedCode }).catch(() => {});
          return;
        }
      } catch (error) {
        handleAppRecoverableError({
          scope: 'src/context/ThemeContext.tsx#catch1',
          error,
          message: 'Something went wrong. Please retry.',
          notifyMode: 'silent',
        });
      }

      // 3) No account or backend preference yet -> bootstrap from local/browser and persist.
      const bootstrapCode = getLanguageCode(languageCode || language || 'en');
      persistLanguagePreference(bootstrapCode);
    };

    syncLanguage();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, user?.user_id, (user as any)?.language_preference, persistLanguagePreference, saveTheme]);

  // Preload selected locale globally for all routes/tabs after language change.
  useEffect(() => {
    if (!languageCode || languageCode === 'en') return;
    loadLocale(languageCode).catch(() => {});
  }, [languageCode]);

  const loadTheme = useCallback(async () => {
    let loadedThemeMode: ThemeMode = 'system';
    try {
      const data = await AsyncStorage.getItem('app_theme');
      if (data) {
        const t = JSON.parse(data);
        // Support legacy 'darkMode' boolean and new 'themeMode'
        if (t.themeMode !== undefined) {
          loadedThemeMode = t.themeMode as ThemeMode;
          setThemeModeState(loadedThemeMode);
        } else if (t.darkMode !== undefined) {
          // Migrate from legacy format
          loadedThemeMode = t.darkMode ? 'dark' : 'light';
          setThemeModeState(loadedThemeMode);
        }
        if (t.language || t.languageCode) {
          const resolvedCode = getLanguageCode(String(t.languageCode || t.language || 'en'));
          const resolvedLanguage = String(
            t.language
            || SUPPORTED_LANGUAGES.find((entry) => entry.code === resolvedCode)?.name
            || 'English'
          );
          setLanguageState(resolvedLanguage);
          setLanguageCode(resolvedCode);
        }
        if (t.fontSize) setFontSizeState(t.fontSize);
      } else {
        // FIRST LAUNCH - Auto Detect Language from browser
        let detectedLang = 'English';
        if (Platform.OS === 'web' && typeof navigator !== 'undefined') {
           const navLang = (navigator.language || navigator.languages?.[0] || 'en').toLowerCase();
           const langMap: Record<string, string> = {
             fr: 'French', es: 'Spanish', de: 'German', it: 'Italian',
             pt: 'Portuguese', zh: 'Chinese', ja: 'Japanese', ko: 'Korean',
             ru: 'Russian', ar: 'Arabic', hi: 'Hindi', tr: 'Turkish',
             nl: 'Dutch', sv: 'Swedish', pl: 'Polish', th: 'Thai',
             vi: 'Vietnamese', id: 'Indonesian', ms: 'Malay', sw: 'Swahili',
             uk: 'Ukrainian', ro: 'Romanian',
           };
           for (const [prefix, name] of Object.entries(langMap)) {
             if (navLang.startsWith(prefix)) { detectedLang = name; break; }
           }
        }
        setLanguageState(detectedLang);
        setLanguageCode(getLanguageCode(detectedLang));
        // Persist the auto-detected language so it sticks across reloads
        const initial = { language: detectedLang, languageCode: getLanguageCode(detectedLang), fontSize: 'Medium' };
        AsyncStorage.setItem('app_theme', JSON.stringify(initial)).catch(() => {});
      }

      const dbPrefRaw = (user as any)?.theme_preference;
      const dbPref = (typeof dbPrefRaw === 'string' ? dbPrefRaw : '').trim() as ThemeMode;
      if (user?.user_id && !dbSyncedRef.current && ['system', 'light', 'dark'].includes(dbPref)) {
        if (dbPref !== loadedThemeMode) {
          setThemeModeState(dbPref);
          await saveTheme({ themeMode: dbPref, darkMode: dbPref === 'dark' });
        }
        dbSyncedRef.current = true;
      }

      setIsLoaded(true);
    } catch (e) { 
      console.error('Theme load error:', e); 
      setIsLoaded(true);
    }
  }, [saveTheme, user?.user_id, (user as any)?.theme_preference]);

  useEffect(() => {
    loadTheme();
  }, [loadTheme]);

  const setThemeMode = useCallback((val: ThemeMode) => {
    setIsThemePreview(false); // Exit preview when theme mode changes
    setThemeModeState(val);
    saveTheme({ themeMode: val, darkMode: val === 'dark' }); // Keep legacy support
    // Persist to backend (fire-and-forget)
    if (user?.user_id) {
      api.put('/auth/profile', { theme_preference: val }).catch(() => {});
    }
  }, [saveTheme, user?.user_id]);

  useEffect(() => {
    const lockedAccent = resolveThemeColors(darkMode).primary;
    setAccentColorState(lockedAccent);
    setPreviewAccentColor(lockedAccent);
  }, [darkMode]);

  // Legacy setter - converts boolean to theme mode
  const setDarkMode = useCallback((val: boolean) => {
    const mode: ThemeMode = val ? 'dark' : 'light';
    setThemeModeState(mode);
    saveTheme({ themeMode: mode, darkMode: val });
  }, [saveTheme]);

  const setAccentColor = useCallback((_val: string) => {
    const lockedAccent = resolveThemeColors(darkMode).primary;
    setAccentColorState(lockedAccent);
    setPreviewAccentColor(lockedAccent);
    saveTheme({ accentColor: lockedAccent });
  }, [darkMode, saveTheme]);

  const setLanguage = useCallback((val: string) => {
    const code = getLanguageCode(val);
    const normalizedLanguage = getLanguageNameByCode(code);
    // Immediately apply RTL/LTR direction on web
    if (Platform.OS === 'web' && typeof document !== 'undefined') {
      const langEntry = SUPPORTED_LANGUAGES.find(l => l.code === code);
      const isRTL = langEntry?.rtl || false;
      document.documentElement.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
      document.documentElement.setAttribute('lang', code);
    }
    if (previewEnabled) {
      setPreviewLanguage(normalizedLanguage);
      setPreviewLanguageCode(code);
      return;
    }
    if (code === languageCode && normalizedLanguage === language) {
      return;
    }

    const nextSwitchToken = `${code}:${Date.now()}`;
    languageSwitchTokenRef.current = nextSwitchToken;
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      (window as any).__racI18nSwitchToken = nextSwitchToken;
      (window as any).__racI18nSwitchStartAt = Date.now();
    }

    setLanguageSwitching(true);
    if (languageSwitchTimerRef.current) {
      clearTimeout(languageSwitchTimerRef.current);
    }
    languageSwitchTimerRef.current = setTimeout(() => {
      setLanguageSwitching(false);
      languageSwitchTimerRef.current = null;
    }, LANGUAGE_SWITCH_FAILSAFE_MS);

    setLanguageState(normalizedLanguage);
    setLanguageCode(code);
    saveTheme({ language: normalizedLanguage, languageCode: code });
    persistLanguagePreference(code);
  }, [language, languageCode, persistLanguagePreference, previewEnabled, saveTheme]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;

    const onReadiness = (event: Event) => {
      try {
        const detail = (event as CustomEvent)?.detail || {};
        const ready = Boolean(detail?.routeReady);
        const readyLanguageCode = getLanguageCode(String(detail?.languageCode || languageCode || 'en'));
        if (!ready || readyLanguageCode !== getLanguageCode(languageCode || 'en')) return;
      } catch {
        return;
      }

      setLanguageSwitching(false);
      if (languageSwitchTimerRef.current) {
        clearTimeout(languageSwitchTimerRef.current);
        languageSwitchTimerRef.current = null;
      }

      try {
        (window as any).__racI18nSwitching = false;
        (window as any).__racI18nBackgroundOnly = false;
        (window as any).__racI18nSwitchToken = '';
      } catch {
        // no-op
      }
    };

    window.addEventListener('rac:i18n-readiness', onReadiness as EventListener);
    return () => window.removeEventListener('rac:i18n-readiness', onReadiness as EventListener);
  }, [languageCode]);

  useEffect(() => {
    if (languageCode === 'en') {
      setLanguageSwitching(false);
      if (languageSwitchTimerRef.current) {
        clearTimeout(languageSwitchTimerRef.current);
        languageSwitchTimerRef.current = null;
      }
    }
  }, [languageCode]);

  useEffect(() => {
    return () => {
      if (languageSwitchTimerRef.current) {
        clearTimeout(languageSwitchTimerRef.current);
        languageSwitchTimerRef.current = null;
      }
    };
  }, []);

  const setPreviewEnabled = useCallback((val: boolean) => {
    const lockedAccent = resolveThemeColors(computedDarkMode).primary;
    if (val) {
      setPreviewEnabledState(true);
      setPreviewAccentColor(lockedAccent);
      setPreviewLanguage(language);
      setPreviewLanguageCode(languageCode);
      return;
    }
    setPreviewEnabledState(false);
    setPreviewAccentColor(lockedAccent);
    setPreviewLanguage(language);
    setPreviewLanguageCode(languageCode);
  }, [computedDarkMode, language, languageCode]);

  const savePreviewChanges = useCallback(() => {
    if (!previewEnabled) return;
    setLanguageState(previewLanguage);
    setLanguageCode(previewLanguageCode);
    saveTheme({ language: previewLanguage, languageCode: previewLanguageCode });
    persistLanguagePreference(previewLanguageCode);
    setPreviewEnabledState(false);
  }, [persistLanguagePreference, previewEnabled, previewLanguage, previewLanguageCode, saveTheme]);

  const cancelPreviewChanges = useCallback(() => {
    setPreviewAccentColor(resolveThemeColors(computedDarkMode).primary);
    setPreviewLanguage(language);
    setPreviewLanguageCode(languageCode);
    setPreviewEnabledState(false);
  }, [computedDarkMode, language, languageCode]);

  const toggleThemePreview = useCallback(() => {
    if (isThemePreview) {
      setIsThemePreview(false);
    } else {
      setPreviewDarkOverride(!computedDarkMode);
      setIsThemePreview(true);
    }
  }, [isThemePreview, computedDarkMode]);

  const exitThemePreview = useCallback(() => {
    setIsThemePreview(false);
  }, []);

  useEffect(() => {
    if (previewEnabled) return;
    setPreviewAccentColor(resolveThemeColors(computedDarkMode).primary);
    setPreviewLanguage(language);
    setPreviewLanguageCode(languageCode);
  }, [computedDarkMode, language, languageCode, previewEnabled]);

  const setFontSize = useCallback((val: string) => {
    setFontSizeState(val);
    saveTheme({ fontSize: val });
  }, [saveTheme]);

  // Apply font scale globally on web
  useEffect(() => {
    if (Platform.OS === 'web' && typeof document !== 'undefined') {
      const scales: Record<string, number> = { Small: 0.92, Medium: 1, Large: 1.12 };
      const scale = scales[fontSize] || 1;
      document.documentElement.style.setProperty('--app-font-scale', String(scale));
      document.documentElement.style.fontSize = `${Math.round(scale * 100)}%`;
      document.documentElement.setAttribute('data-font-size', fontSize.toLowerCase());
    }
  }, [fontSize]);

  // Apply RTL/LTR direction based on selected language
  const effectiveLanguageCode = previewEnabled ? previewLanguageCode : languageCode;
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    const langEntry = SUPPORTED_LANGUAGES.find(l => l.code === effectiveLanguageCode);
    const isRTL = langEntry?.rtl || false;
    const root = document.documentElement;
    root.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
    root.setAttribute('lang', effectiveLanguageCode);
  }, [effectiveLanguageCode]);

  const effectiveAccentColor = previewEnabled ? previewAccentColor : accentColor;
  const effectiveLanguage = previewEnabled ? previewLanguage : language;
  const baseColors = resolveThemeColors(darkMode);
  const colors = {
    ...baseColors,
    primary: baseColors.primary,
    accent: baseColors.accent,
  };

  const hasPendingPreviewChanges = previewEnabled && (
    previewLanguage !== language
  );

  return (
    <ThemeContext.Provider value={{
      darkMode, 
      _darkMode: darkMode,
      themeMode,
      accentColor: effectiveAccentColor, 
      language: effectiveLanguage,
      languageCode: effectiveLanguageCode,
      languageSwitching,
      fontSize,
      previewEnabled,
      hasPendingPreviewChanges,
      isThemePreview,
      toggleThemePreview,
      exitThemePreview,
      setThemeMode,
      setDarkMode, 
      setAccentColor, 
      setLanguage, 
      setFontSize,
      setPreviewEnabled,
      savePreviewChanges,
      cancelPreviewChanges,
      colors,
      _colors: colors,
      systemColorScheme,
    }}>
      {children}
    </ThemeContext.Provider>
  );
}
