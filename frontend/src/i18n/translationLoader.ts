// Dynamic translation loader — loads non-English locales on demand
import enLocale from './locales/en';
import { sanitizeTranslationMap, stripI18nLanguageTagPrefix } from '../utils/brandProtection';
import { Platform } from 'react-native';
import { handleAppRecoverableError } from '../utils/appRecoverableError';
import { getFrontendYearlyDiscountPct } from '../config/pricingPolicy';
import { normalizeAdminLocalePlaceholderContent } from './adminCopyGuard';

type TranslationMap = Record<string, string>;

const GLOBAL_YEARLY_DISCOUNT_PCT = String(getFrontendYearlyDiscountPct());

function replaceDiscountPct(value: string, pct: string = GLOBAL_YEARLY_DISCOUNT_PCT): string {
  if (!value) return value;
  if (value.includes('{pct}')) {
    return value.replace(/\{pct\}/g, pct);
  }
  return value.replace(/60/g, pct);
}

function toDiscountTemplate(value: string, fallback: string): string {
  const candidate = String(value || fallback || '').trim();
  if (!candidate) return fallback;
  if (candidate.includes('{pct}')) return candidate;
  if (/20|60/.test(candidate)) {
    return candidate.replace(/20|60/g, '{pct}');
  }
  return fallback;
}

function normalizeGlobalPricingDiscountCopy(localeData: TranslationMap): TranslationMap {
  const next: TranslationMap = { ...localeData };

  const pricingTemplate = toDiscountTemplate(
    String(next['pricing.saveDynamic'] || next['pricing.save'] || ''),
    String(enLocale['pricing.saveDynamic'] || 'SAVE {pct}%'),
  );
  next['pricing.saveDynamic'] = pricingTemplate;
  next['pricing.save'] = replaceDiscountPct(pricingTemplate);

  const welcomePricingTemplate = toDiscountTemplate(
    String(next['welcome.pricing.saveDynamic'] || next['welcome.pricing.save60'] || next['welcome.pricing.save20'] || pricingTemplate || ''),
    String(enLocale['welcome.pricing.saveDynamic'] || enLocale['pricing.saveDynamic'] || 'SAVE {pct}%'),
  );
  next['welcome.pricing.saveDynamic'] = welcomePricingTemplate;
  next['welcome.pricing.save60'] = replaceDiscountPct(welcomePricingTemplate);
  next['welcome.pricing.save20'] = replaceDiscountPct(welcomePricingTemplate);

  if (typeof next['welcome.faq.a2'] === 'string') {
    next['welcome.faq.a2'] = replaceDiscountPct(next['welcome.faq.a2']);
  }

  if (typeof next['admin.subscriptionAnalyticsPanel.auto.text.013'] === 'string') {
    next['admin.subscriptionAnalyticsPanel.auto.text.013'] = replaceDiscountPct(next['admin.subscriptionAnalyticsPanel.auto.text.013'])
      .replace(/2([.,])40/g, (_match, sep) => `4${sep}79`)
      .replace(/6([.,])40/g, (_match, sep) => `12${sep}79`);
  }

  return next;
}

const PLACEHOLDER_VALUE_PATTERNS = [
  /^name$/i,
  /^nom$/i,
  /^nombre$/i,
  /^nome$/i,
  /^naam$/i,
  /^description$/i,
  /^feature\s*\d+$/i,
  /^feature\d+$/i,
  /^caract[eé]ristique\s*\d+$/i,
  /^caratteristica\s*\d+$/i,
  /^caracter[ií]stica\s*\d+$/i,
  /^funci[oó]n\s*\d+$/i,
  /^funktion\s*\d+$/i,
  /^limit\s*\d+$/i,
  /^limite\s*\d+$/i,
  /^l[ií]mite\s*\d+$/i,
  /^limitation\s*\d+$/i,
  /^grenze\s*\d+$/i,  // German: Grenze1, Grenze2, etc.
  /^descri[cç][aã]o$/i,
  /^descripci[oó]n$/i,
  /^descrizione$/i,
  /^beschreibung$/i,
  /^名前$/,
  /^名称$/,
  /^ชื่อ$/,
  /^नाम$/,
];

function isPlaceholderPricingValue(value: unknown): boolean {
  const normalized = String(value || '').trim();
  if (!normalized) return true;
  return PLACEHOLDER_VALUE_PATTERNS.some((pattern) => pattern.test(normalized));
}

function normalizeWelcomePricingPlaceholderContent(localeData: TranslationMap): TranslationMap {
  const next: TranslationMap = { ...localeData };
  const pricingKeys = [
    'welcome.pricing.default.free.name',
    'welcome.pricing.default.free.description',
    'welcome.pricing.default.free.feature1',
    'welcome.pricing.default.free.feature2',
    'welcome.pricing.default.free.feature3',
    'welcome.pricing.default.free.limit1',
    'welcome.pricing.default.basic.name',
    'welcome.pricing.default.basic.description',
    'welcome.pricing.default.basic.feature1',
    'welcome.pricing.default.basic.feature2',
    'welcome.pricing.default.basic.feature3',
    'welcome.pricing.default.basic.limit1',
    'welcome.pricing.default.premium.name',
    'welcome.pricing.default.premium.description',
    'welcome.pricing.default.premium.feature1',
    'welcome.pricing.default.premium.feature2',
    'welcome.pricing.default.premium.feature3',
  ];

  for (const key of pricingKeys) {
    if (isPlaceholderPricingValue(next[key])) {
      next[key] = String(enLocale[key] || next[key] || '');
    }
  }

  return next;
}

// In-memory cache for loaded translations
const loadedLocales: Record<string, TranslationMap> = {
  en: enLocale,
};

// Dynamic import map for lazy-loaded locales
const localeLoaders: Record<string, () => Promise<{ default: TranslationMap }>> = {
  es: () => import('./locales/es'),
  fr: () => import('./locales/fr'),
  de: () => import('./locales/de'),
  it: () => import('./locales/it'),
  pt: () => import('./locales/pt'),
  ja: () => import('./locales/ja'),
  zh: () => import('./locales/zh'),
  hi: () => import('./locales/hi'),
  ar: () => import('./locales/ar'),
  ko: () => import('./locales/ko'),
  ru: () => import('./locales/ru'),
  tr: () => import('./locales/tr'),
  nl: () => import('./locales/nl'),
  sv: () => import('./locales/sv'),
  pl: () => import('./locales/pl'),
  th: () => import('./locales/th'),
  vi: () => import('./locales/vi'),
  id: () => import('./locales/id'),
  ms: () => import('./locales/ms'),
  sw: () => import('./locales/sw'),
  uk: () => import('./locales/uk'),
  ro: () => import('./locales/ro'),
};

// Pending load promises to avoid duplicate fetches
const pendingLoads: Record<string, Promise<TranslationMap>> = {};

/**
 * Seed the DOM auto-translation engine with known static translations.
 * This enables instant rendering of locale-file strings without API calls.
 */
function seedDomEngine(code: string, localeData: TranslationMap): void {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  if (code === 'en' || !localeData) return;
  try {
    const txEngine = (window as any).__txEngine;
    if (!txEngine || typeof txEngine.seedCache !== 'function') return;
    // Build English→Translated map for DOM engine
    const seedMap: Record<string, string> = {};
    const en = loadedLocales['en'] || {};
    const seedPair = (source: string, translated: string) => {
      if (!source || !translated) return;
      const s = source.trim();
      const t = stripI18nLanguageTagPrefix(translated).trim();
      if (s.length < 2 || t.length < 2 || s === t) return;
      seedMap[s] = t;

      // Normalization variants for legacy hardcoded strings with whitespace
      // / punctuation drift across pages.
      const compact = s.replace(/\s+/g, ' ').trim();
      if (compact && compact !== s && !seedMap[compact]) {
        seedMap[compact] = t;
      }
      const dePunct = compact.replace(/[\s\u00A0]*[.!?…:;]+$/, '').trim();
      if (dePunct && dePunct !== compact && !seedMap[dePunct]) {
        seedMap[dePunct] = t;
      }
    };

    for (const [key, enValue] of Object.entries(en)) {
      const translated = localeData[key];
      if (typeof enValue !== 'string' || typeof translated !== 'string') continue;

      const source = enValue.trim();
      const translatedNormalized = stripI18nLanguageTagPrefix(translated).trim();
      if (source.length < 2 || translatedNormalized.length < 2) continue;

      if (__DEV__ && source === translatedNormalized) {
        console.warn(`[i18n][seedDomEngine] untranslated locale echo detected: locale=${code} key=${key}`);
        continue;
      }

      seedPair(source, translatedNormalized);
    }
    if (Object.keys(seedMap).length > 0) {
      txEngine.seedCache(code, seedMap);
    }
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/i18n/translationLoader.ts#catch1',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }
}

/**
 * Load translations for a given language code.
 * English is always available synchronously.
 * Other languages are loaded on demand and cached.
 */
export async function loadLocale(code: string): Promise<TranslationMap> {
  // Already cached
  if (loadedLocales[code]) return loadedLocales[code];

  // Already loading
  if (pendingLoads[code]) return pendingLoads[code];

  const loader = localeLoaders[code];
  if (!loader) {
    // Unsupported language — fall back to English
    return loadedLocales['en'];
  }

  pendingLoads[code] = loader()
    .then((mod) => {
      loadedLocales[code] = normalizeAdminLocalePlaceholderContent(
        normalizeWelcomePricingPlaceholderContent(
          normalizeGlobalPricingDiscountCopy(sanitizeTranslationMap(mod.default, enLocale))
        ),
        enLocale,
      );
      delete pendingLoads[code];
      // Feed the DOM auto-translation engine with static translations
      seedDomEngine(code, loadedLocales[code]);
      return loadedLocales[code];
    })
    .catch(() => {
      delete pendingLoads[code];
      return loadedLocales['en'];
    });

  return pendingLoads[code];
}

/**
 * Get cached translations for a language code.
 * Returns English if the requested language hasn't been loaded yet.
 */
export function getCachedLocale(code: string): TranslationMap {
  return loadedLocales[code] || loadedLocales['en'];
}

/**
 * Check if a locale is already loaded.
 */
export function isLocaleLoaded(code: string): boolean {
  return code in loadedLocales;
}

export async function buildLocaleSeedMap(code: string): Promise<Record<string, string>> {
  if (!code || code === 'en') return {};

  await Promise.all([loadLocale('en'), loadLocale(code)]).catch(() => {});
  const enLocale = getCachedLocale('en');
  const targetLocale = getCachedLocale(code);
  const seedMap: Record<string, string> = {};

  Object.keys(enLocale || {}).forEach((key) => {
    const source = enLocale[key];
    const translatedRaw = targetLocale?.[key];
    const translated = typeof translatedRaw === 'string' ? stripI18nLanguageTagPrefix(translatedRaw) : translatedRaw;
    if (
      typeof source === 'string' &&
      typeof translated === 'string' &&
      source.trim().length >= 2 &&
      translated.trim().length >= 2 &&
      source !== translated
    ) {
      seedMap[source] = translated;
    }
  });

  return seedMap;
}
