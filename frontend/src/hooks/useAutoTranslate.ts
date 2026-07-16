/**
 * Universal auto-translation hook.
 * 
 * Provides `tt(text)` function that translates ANY English string
 * to the user's language. Uses:
 * 1. Static translations from translations.ts (fastest)
 * 2. In-memory cache (fast)
 * 3. Backend auto-translate API with MongoDB caching (one-time per string)
 * 
 * Usage:
 *   const { tt } = useAutoTranslate();
 *   <Text>{tt('Support Center')}</Text>
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { translate, getLanguageCode } from '../utils/translations';
import { enforceProtectedBrands } from '../utils/brandProtection';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

// ── In-memory cache shared across all hook instances ──
const memoryCache: Record<string, Record<string, string>> = {};
const pendingBatch: Record<string, Set<string>> = {};
const batchTimers: Record<string, any> = {};
const listenersByLang: Record<string, Set<() => void>> = {};
const hydratedPersistentLanguages = new Set<string>();
const persistTimers: Record<string, any> = {};
const PERSIST_PREFIX = 'rac_auto_translate_v2_';
const EPHEMERAL_PREFIX = '__ephemeral__:';

function isI18nBackgroundOnlyMode(): boolean {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return false;
  return Boolean((window as any).__racI18nBackgroundOnly);
}

// ── Reverse map: English value → translation key ──
let reverseMap: Record<string, string> | null = null;

function buildReverseMap(): Record<string, string> {
  if (reverseMap) return reverseMap;
  try {
    // Import the English translations from the locale file
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const enLocale = require('../i18n/locales/en').default;
    reverseMap = {};
    for (const [key, value] of Object.entries(enLocale)) {
      if (typeof value === 'string' && value.length > 0) {
        // Store normalized lowercase for matching
        reverseMap[value.toLowerCase().trim()] = key;
      }
    }
  } catch {
    reverseMap = {};
  }
  return reverseMap;
}

function lookupStaticTranslation(text: string, lang: string): string | null {
  if (lang === 'en') return text;
  const map = buildReverseMap();
  const key = map[text.toLowerCase().trim()];
  if (key) {
    const translated = translate(lang, key);
    // translate() returns the key if not found, check it's actually translated
    if (translated !== key && translated !== text) {
      return translated;
    }
  }
  return null;
}

function getCached(text: string, lang: string): string | null {
  return memoryCache[lang]?.[text] ?? null;
}

function setCache(text: string, lang: string, translated: string) {
  if (!memoryCache[lang]) memoryCache[lang] = {};
  memoryCache[lang][text] = translated;
  if (!String(translated || '').startsWith(EPHEMERAL_PREFIX)) {
    schedulePersist(lang);
  }
}

function schedulePersist(lang: string) {
  if (persistTimers[lang]) clearTimeout(persistTimers[lang]);
  persistTimers[lang] = setTimeout(async () => {
    try {
      const payload = JSON.stringify(memoryCache[lang] || {});
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.localStorage.setItem(PERSIST_PREFIX + lang, payload);
        return;
      }
      await AsyncStorage.setItem(PERSIST_PREFIX + lang, payload);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'src/hooks/useAutoTranslate.ts#catch1',
        error,
        message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      });
    }
  }, 180);
}

async function hydratePersistentCache(lang: string) {
  if (!lang || lang === 'en' || hydratedPersistentLanguages.has(lang)) return;
  hydratedPersistentLanguages.add(lang);
  try {
    let raw = '';
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      raw = window.localStorage.getItem(PERSIST_PREFIX + lang) || '';
    } else {
      raw = (await AsyncStorage.getItem(PERSIST_PREFIX + lang)) || '';
    }
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return;
    const filtered = Object.entries(parsed).reduce((acc, [k, v]) => {
      if (typeof v === 'string' && !v.startsWith(EPHEMERAL_PREFIX)) {
        acc[k] = v;
      }
      return acc;
    }, {} as Record<string, string>);
    memoryCache[lang] = {
      ...(memoryCache[lang] || {}),
      ...filtered,
    };
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/hooks/useAutoTranslate.ts#catch2',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }
}

async function fetchBatchTranslations(lang: string) {
  const texts = pendingBatch[lang];
  if (!texts || texts.size === 0) return;

  const batch = Array.from(texts);
  pendingBatch[lang] = new Set();

  if (isI18nBackgroundOnlyMode()) {
    if (!pendingBatch[lang]) pendingBatch[lang] = new Set();
    batch.forEach((text) => pendingBatch[lang].add(text));
    if (batchTimers[lang]) clearTimeout(batchTimers[lang]);
    batchTimers[lang] = setTimeout(() => {
      fetchBatchTranslations(lang);
    }, 900);
    return;
  }

  try {
    const res = await api.post('/i18n/auto-translate', { texts: batch, lang });
    const translations: Record<string, string> = res.data?.translations || {};
    for (const [original, translated] of Object.entries(translations)) {
      setCache(original, lang, enforceProtectedBrands(original, translated));
    }
  } catch {
    // On transient failures, keep short-lived in-memory suppression only.
    // Never persist source->source, otherwise strings can stay stuck in English.
    for (const text of batch) {
      setCache(text, lang, `${EPHEMERAL_PREFIX}${Date.now()}`);
    }
    setTimeout(() => {
      const langCache = memoryCache[lang] || {};
      batch.forEach((text) => {
        if (String(langCache[text] || '').startsWith(EPHEMERAL_PREFIX)) {
          delete langCache[text];
        }
      });
    }, 3500);
  }

  const listeners = listenersByLang[lang];
  if (listeners && listeners.size > 0) {
    listeners.forEach((listener) => {
      try {
        listener();
      } catch (error) {
        handleAppRecoverableError({
          scope: 'src/hooks/useAutoTranslate.ts#catch3',
          error,
          message: 'Something went wrong. Please retry.',
          notifyMode: 'silent',
        });
      }
    });
  }
}

function queueForTranslation(text: string, lang: string): void {
  if (!pendingBatch[lang]) pendingBatch[lang] = new Set();
  pendingBatch[lang].add(text);

  // Debounce: collect for 150ms then batch-fetch
  if (batchTimers[lang]) clearTimeout(batchTimers[lang]);
  batchTimers[lang] = setTimeout(() => {
    fetchBatchTranslations(lang);
  }, 150);
}

export function useAutoTranslate() {
  const { language } = useTheme();
  const lang = getLanguageCode(language || 'English');
  const [, forceUpdate] = useState(0);
  const pendingRef = useRef(new Set<string>());
  const deferredTimersRef = useRef<Record<string, any>>({});
  const refreshTimerRef = useRef<any>(null);

  useEffect(() => {
    hydratePersistentCache(lang).then(() => forceUpdate((n) => n + 1));
  }, [lang]);

  useEffect(() => {
    if (!listenersByLang[lang]) listenersByLang[lang] = new Set();

    const notify = () => {
      pendingRef.current.clear();
      if (refreshTimerRef.current) return;
      refreshTimerRef.current = setTimeout(() => {
        refreshTimerRef.current = null;
        forceUpdate((n) => n + 1);
      }, 120);
    };

    listenersByLang[lang].add(notify);

    return () => {
      listenersByLang[lang]?.delete(notify);
      if (listenersByLang[lang] && listenersByLang[lang].size === 0) {
        delete listenersByLang[lang];
      }
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }

      const deferredTimers = deferredTimersRef.current;
      Object.keys(deferredTimers).forEach((timerKey) => {
        clearTimeout(deferredTimers[timerKey]);
      });
      deferredTimersRef.current = {};
    };
  }, [lang]);

  // `tt` - Translate Text. Synchronous with async background fetch.
  const tt = useCallback((text: string): string => {
    if (!text || lang === 'en') return text;

    // 1. Check static translations (instant)
    const staticResult = lookupStaticTranslation(text, lang);
    if (staticResult) return enforceProtectedBrands(text, staticResult);

    // 2. Check memory cache (instant)
    const cached = getCached(text, lang);
    if (cached && !cached.startsWith(EPHEMERAL_PREFIX)) {
      if (cached !== text) return enforceProtectedBrands(text, cached);
      if (!pendingRef.current.has(text)) {
        pendingRef.current.add(text);
        queueForTranslation(text, lang);
      }
      return text;
    }

    if (isI18nBackgroundOnlyMode()) {
      if (!pendingRef.current.has(text)) {
        pendingRef.current.add(text);
        const timerKey = `${lang}:${text}`;
        if (!deferredTimersRef.current[timerKey]) {
          deferredTimersRef.current[timerKey] = setTimeout(() => {
            delete deferredTimersRef.current[timerKey];
            pendingRef.current.delete(text);
            if (!isI18nBackgroundOnlyMode()) {
              queueForTranslation(text, lang);
            }
          }, 1200);
        }
      }
      return text;
    }

    // 3. Queue for backend translation (async)
    if (!pendingRef.current.has(text)) {
      pendingRef.current.add(text);
      queueForTranslation(text, lang);
    }

    // Return original while waiting
    return text;
  }, [lang]);

  return { tt, language: lang };
}

export default useAutoTranslate;
