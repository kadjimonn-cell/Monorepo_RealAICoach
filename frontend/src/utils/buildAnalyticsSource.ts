type AnalyticsSourcePart = string | number | null | undefined | false;

export function normalizeAnalyticsSourcePart(value: AnalyticsSourcePart): string {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[:/_.\s]+/g, '-')
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/(^-|-$)/g, '');

  return normalized;
}

export function buildAnalyticsSource(...parts: AnalyticsSourcePart[]): string {
  const source = parts
    .map((part) => normalizeAnalyticsSourcePart(part))
    .filter(Boolean)
    .join('-');

  return source || 'unknown-source';
}