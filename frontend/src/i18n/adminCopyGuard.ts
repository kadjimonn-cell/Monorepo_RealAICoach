type TranslationMap = Record<string, string>;

const ADMIN_NAMESPACE_PREFIXES = ['admin.', 'operationsConsole.', 'observability.'];

const ADMIN_PLACEHOLDER_PATTERNS = [
  /^title$/i,
  /^subtitle$/i,
  /^description$/i,
  /^summary$/i,
  /^details?$/i,
  /^message$/i,
  /^label$/i,
  /^name$/i,
  /^status$/i,
  /^type$/i,
  /^action$/i,
  /^source$/i,
  /^category$/i,
  /^surface$/i,
  /^report$/i,
  /^note$/i,
  /^metric$/i,
  /^value$/i,
  /^(title|subtitle|description|summary|details?|message|label|name|status|type|action|source|category|surface|report|note|metric|value)\s*[-_#:]*\s*\d*$/i,
  /^auto\.text\.\d+$/i,
  /^auto\.placeholder\.\d+$/i,
  /^titre$/i,
  /^sous[-\s]?titre$/i,
  /^descripci[oó]n$/i,
  /^descri[cç][aã]o$/i,
  /^descrizione$/i,
  /^beschreibung$/i,
  /^detalles?$/i,
  /^maelezo$/i,
  /^nom$/i,
  /^nombre$/i,
  /^nome$/i,
  /^naam$/i,
];

function collapseWhitespace(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

export function isWeakAdminCopy(value: unknown): boolean {
  const normalized = collapseWhitespace(String(value || ''));
  if (!normalized) return true;
  return ADMIN_PLACEHOLDER_PATTERNS.some((pattern) => pattern.test(normalized));
}

export function normalizeAdminRuntimeCopy(value: unknown, fallback: string): string {
  const normalized = collapseWhitespace(String(value || ''));
  if (!normalized || isWeakAdminCopy(normalized)) {
    return fallback;
  }
  return normalized;
}

export function humanizeAdminToken(value: unknown, fallback: string): string {
  const normalized = normalizeAdminRuntimeCopy(value, '');
  if (!normalized) return fallback;
  const humanized = collapseWhitespace(normalized.replace(/[_-]+/g, ' '));
  if (!humanized || isWeakAdminCopy(humanized)) {
    return fallback;
  }
  if (humanized === humanized.toUpperCase()) {
    return humanized;
  }
  return humanized
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function normalizeAdminStatusTone(value: unknown, fallback: string): string {
  const normalized = normalizeAdminRuntimeCopy(value, fallback);
  return normalized.toUpperCase();
}

export function normalizeAdminLocalePlaceholderContent(localeData: TranslationMap, enLocale: TranslationMap): TranslationMap {
  const next: TranslationMap = { ...localeData };
  for (const [key, value] of Object.entries(next)) {
    if (!ADMIN_NAMESPACE_PREFIXES.some((prefix) => key.startsWith(prefix))) continue;
    if (typeof value !== 'string') continue;
    if (!isWeakAdminCopy(value)) continue;
    next[key] = String(enLocale[key] || value || '');
  }
  return next;
}