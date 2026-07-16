export const PLATFORM_BRAND = 'RealAICoach';
export const PROTECTED_BRANDS_MULTI = ['Google Play', 'App Store', 'Apple Pay'];
export const PROTECTED_BRANDS_SINGLE = ['Google', 'Microsoft', 'Apple', PLATFORM_BRAND, 'PayPal', 'Stripe', 'FedaPay', 'OpenAI', 'Anthropic', 'Gemini', 'Claude'];
export const PROTECTED_BRANDS = [...PROTECTED_BRANDS_MULTI, ...PROTECTED_BRANDS_SINGLE];

const PLATFORM_BRAND_VARIANT_RE = /(Real\s*AI\s*Coach|Real-?AI-?Coach|Realaicoach|RéelAIEntraîneur|RealAICoach)/gi;

const multi = PROTECTED_BRANDS_MULTI.map((item) => item.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
const single = PROTECTED_BRANDS_SINGLE.map((item) => `\\b${item.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`);
const BRAND_RE = new RegExp(`${[...multi, ...single].join('|')}`, 'g');
const I18N_LANG_TAG_PREFIX_RE = /^\s*\[[a-z]{2}\]\s*/i;

export const stripI18nLanguageTagPrefix = (value: string): string => value.replace(I18N_LANG_TAG_PREFIX_RE, '').trimStart();

export const normalizePlatformBrand = (value: string): string => {
  if (!value) return value;
  return String(value).replace(PLATFORM_BRAND_VARIANT_RE, PLATFORM_BRAND);
};

export const extractProtectedBrands = (text: string): string[] => {
  if (!text) return [];
  const matches = text.match(BRAND_RE);
  return matches || [];
};

export const preservesProtectedBrands = (sourceText: string, candidateText: string): boolean => {
  const brands = extractProtectedBrands(sourceText);
  if (!brands.length) return true;
  const sourceCounts: Record<string, number> = {};
  brands.forEach((brand) => {
    sourceCounts[brand] = (sourceCounts[brand] || 0) + 1;
  });
  const candidateCounts: Record<string, number> = {};
  extractProtectedBrands(String(candidateText || '')).forEach((brand) => {
    candidateCounts[brand] = (candidateCounts[brand] || 0) + 1;
  });
  return Object.entries(sourceCounts).every(([brand, required]) => (candidateCounts[brand] || 0) >= required);
};

export const enforceProtectedBrands = (sourceText: string, candidateText: string): string => {
  const normalizedSource = normalizePlatformBrand(String(sourceText || ''));
  const normalizedCandidate = normalizePlatformBrand(String(candidateText || ''));
  if (!extractProtectedBrands(normalizedSource).length) return normalizedCandidate;
  return preservesProtectedBrands(normalizedSource, normalizedCandidate) ? normalizedCandidate : normalizedSource;
};

export const sanitizeTranslationMap = (locale: Record<string, string>, sourceLocale: Record<string, string>) => {
  const sanitized: Record<string, string> = {};
  Object.keys(locale || {}).forEach((key) => {
    const source = sourceLocale[key] || '';
    const candidateRaw = locale[key];
    const candidate = typeof candidateRaw === 'string' ? stripI18nLanguageTagPrefix(candidateRaw) : candidateRaw;
    sanitized[key] = typeof candidate === 'string' ? enforceProtectedBrands(source, candidate) : candidate;
  });
  return sanitized;
};