export const normalizeCertificatePrintLayout = (value?: string): 'portrait' | 'landscape' => {
  return String(value || '').toLowerCase() === 'landscape' ? 'landscape' : 'portrait';
};

export const withCertificatePrintLayout = (value: string, layout?: string) => {
  const normalized = normalizeCertificatePrintLayout(layout);
  const raw = String(value || '').trim();
  if (!raw) return '';

  const origin = typeof window !== 'undefined' ? window.location.origin : 'https://realaicoach.app';
  const parsed = new URL(raw, origin);
  parsed.searchParams.set('layout', normalized);

  if (raw.startsWith('/')) {
    return `${parsed.pathname}${parsed.search}`;
  }
  return parsed.toString();
};