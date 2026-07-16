// Import English translations inline (always available, no dynamic load)
import enLocale from '../i18n/locales/en';
import { getCachedLocale } from '../i18n/translationLoader';
import { enforceProtectedBrands } from './brandProtection';

export type LanguageCode = 'en' | 'es' | 'fr' | 'de' | 'it' | 'pt' | 'zh' | 'ja' | 'ko' | 'hi' | 'ar' | 'ru' | 'tr' | 'nl' | 'sv' | 'pl' | 'th' | 'vi' | 'id' | 'ms' | 'sw' | 'uk' | 'ro';

export interface Language {
  code: LanguageCode;
  name: string;
  nativeName: string;
  rtl?: boolean;
}

export const SUPPORTED_LANGUAGES: Language[] = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'es', name: 'Spanish', nativeName: 'Español' },
  { code: 'fr', name: 'French', nativeName: 'Français' },
  { code: 'de', name: 'German', nativeName: 'Deutsch' },
  { code: 'it', name: 'Italian', nativeName: 'Italiano' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português' },
  { code: 'zh', name: 'Chinese', nativeName: '中文' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語' },
  { code: 'ko', name: 'Korean', nativeName: '한국어' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी' },
  { code: 'ar', name: 'Arabic', nativeName: 'العربية', rtl: true },
  { code: 'ru', name: 'Russian', nativeName: 'Русский' },
  { code: 'tr', name: 'Turkish', nativeName: 'Türkçe' },
  { code: 'nl', name: 'Dutch', nativeName: 'Nederlands' },
  { code: 'sv', name: 'Swedish', nativeName: 'Svenska' },
  { code: 'pl', name: 'Polish', nativeName: 'Polski' },
  { code: 'th', name: 'Thai', nativeName: 'ไทย' },
  { code: 'vi', name: 'Vietnamese', nativeName: 'Tiếng Việt' },
  { code: 'id', name: 'Indonesian', nativeName: 'Bahasa Indonesia' },
  { code: 'ms', name: 'Malay', nativeName: 'Bahasa Melayu' },
  { code: 'sw', name: 'Swahili', nativeName: 'Kiswahili' },
  { code: 'uk', name: 'Ukrainian', nativeName: 'Українська' },
  { code: 'ro', name: 'Romanian', nativeName: 'Română' },
];

export const LANGUAGE_CODES: Record<string, string> = {
  English: 'en',
  Spanish: 'es',
  Español: 'es',
  French: 'fr',
  Français: 'fr',
  German: 'de',
  Deutsch: 'de',
  Italian: 'it',
  Italiano: 'it',
  Portuguese: 'pt',
  Português: 'pt',
  'Chinese (Simplified)': 'zh',
  简体中文: 'zh',
  Japanese: 'ja',
  日本語: 'ja',
  Korean: 'ko',
  한국어: 'ko',
  Hindi: 'hi',
  Arabic: 'ar',
  Russian: 'ru',
  Русский: 'ru',
  Turkish: 'tr',
  Türkçe: 'tr',
  Dutch: 'nl',
  Nederlands: 'nl',
  Swedish: 'sv',
  Svenska: 'sv',
  Polish: 'pl',
  Polski: 'pl',
  Thai: 'th',
  ไทย: 'th',
  Vietnamese: 'vi',
  'Tiếng Việt': 'vi',
  Indonesian: 'id',
  'Bahasa Indonesia': 'id',
  Malay: 'ms',
  'Bahasa Melayu': 'ms',
  Swahili: 'sw',
  Kiswahili: 'sw',
  Ukrainian: 'uk',
  Українська: 'uk',
  Romanian: 'ro',
  Română: 'ro',
};

// Keep backward-compatible `translations` accessor — English always available,
// other languages available after dynamic load via getCachedLocale
export const translations: Record<string, Record<string, string>> = new Proxy(
  { en: enLocale } as Record<string, Record<string, string>>,
  {
    get(target, prop: string) {
      if (prop === 'en') return enLocale;
      return getCachedLocale(prop);
    },
  }
);

export const getLanguageCode = (language: string) => {
  if (!language) {
    return 'en';
  }
  const normalized = language.trim();
  if (!normalized) return 'en';
  if (LANGUAGE_CODES[normalized]) {
    return LANGUAGE_CODES[normalized];
  }
  const lower = normalized.toLowerCase();
  if (SUPPORTED_LANGUAGES.some((entry) => entry.code === lower)) {
    return lower;
  }
  const base = lower.split(/[-_]/)[0];
  if (SUPPORTED_LANGUAGES.some((entry) => entry.code === base)) {
    return base;
  }
  const match = Object.entries(LANGUAGE_CODES).find(
    ([key]) => key.toLowerCase() === lower
  );
  return match ? match[1] : 'en';
};

export const translate = (language: string, key: string) => {
  const code = getLanguageCode(language);
  const locale = getCachedLocale(code);
  const source = enLocale[key] || key;
  const candidate = locale[key] || source;
  return enforceProtectedBrands(source, candidate);
};
