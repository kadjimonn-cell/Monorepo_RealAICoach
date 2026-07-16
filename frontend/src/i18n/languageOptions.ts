import { LanguageCode } from '../utils/translations';

export type LanguageOption = {
  code: LanguageCode;
  label: string;
  native: string;
  short: string;
  id: string;
};

export const LANGUAGE_OPTIONS: LanguageOption[] = [
  { code: 'en', label: 'English', native: 'English', short: 'EN', id: 'english' },
  { code: 'es', label: 'Spanish', native: 'Español', short: 'ES', id: 'spanish' },
  { code: 'fr', label: 'French', native: 'Français', short: 'FR', id: 'french' },
  { code: 'de', label: 'German', native: 'Deutsch', short: 'DE', id: 'german' },
  { code: 'it', label: 'Italian', native: 'Italiano', short: 'IT', id: 'italian' },
  { code: 'pt', label: 'Portuguese', native: 'Português', short: 'PT', id: 'portuguese' },
  { code: 'zh', label: 'Chinese (Simplified)', native: '简体中文', short: 'ZH', id: 'chinese-simplified' },
  { code: 'ja', label: 'Japanese', native: '日本語', short: 'JA', id: 'japanese' },
  { code: 'ko', label: 'Korean', native: '한국어', short: 'KO', id: 'korean' },
  { code: 'hi', label: 'Hindi', native: 'हिन्दी', short: 'HI', id: 'hindi' },
  { code: 'ar', label: 'Arabic', native: 'العربية', short: 'AR', id: 'arabic' },
  { code: 'ru', label: 'Russian', native: 'Русский', short: 'RU', id: 'russian' },
  { code: 'tr', label: 'Turkish', native: 'Türkçe', short: 'TR', id: 'turkish' },
  { code: 'nl', label: 'Dutch', native: 'Nederlands', short: 'NL', id: 'dutch' },
  { code: 'sv', label: 'Swedish', native: 'Svenska', short: 'SV', id: 'swedish' },
  { code: 'pl', label: 'Polish', native: 'Polski', short: 'PL', id: 'polish' },
  { code: 'th', label: 'Thai', native: 'ไทย', short: 'TH', id: 'thai' },
  { code: 'vi', label: 'Vietnamese', native: 'Tiếng Việt', short: 'VI', id: 'vietnamese' },
  { code: 'id', label: 'Indonesian', native: 'Bahasa Indonesia', short: 'ID', id: 'indonesian' },
  { code: 'ms', label: 'Malay', native: 'Bahasa Melayu', short: 'MS', id: 'malay' },
  { code: 'sw', label: 'Swahili', native: 'Kiswahili', short: 'SW', id: 'swahili' },
  { code: 'uk', label: 'Ukrainian', native: 'Українська', short: 'UK', id: 'ukrainian' },
  { code: 'ro', label: 'Romanian', native: 'Română', short: 'RO', id: 'romanian' },
];

export const POPULAR_LANGUAGE_CODES = new Set<LanguageCode>([
  'en',
  'es',
  'fr',
  'de',
  'it',
  'pt',
  'zh',
  'ja',
  'ko',
  'hi',
]);

const normalize = (value?: string) => (value || '').trim().toLowerCase();

export const getLanguageOptionByCode = (code?: string) => (
  LANGUAGE_OPTIONS.find((option) => option.code === code)
);

export const getLanguageOptionByLabel = (label?: string) => {
  const normalized = normalize(label);
  if (!normalized) {
    return undefined;
  }

  return LANGUAGE_OPTIONS.find((option) => (
    normalize(option.label) === normalized ||
    normalize(option.native) === normalized ||
    normalize(option.code) === normalized
  )) || (normalized === 'chinese' ? getLanguageOptionByCode('zh') : undefined);
};

export const getCurrentLanguageOption = (language?: string, code?: string) => {
  return getLanguageOptionByLabel(language) || getLanguageOptionByCode(code) || getLanguageOptionByCode('en');
};