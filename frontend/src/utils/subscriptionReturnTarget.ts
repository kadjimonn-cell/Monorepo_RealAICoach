export function normalizeReturnTarget(value: string): string {
  const raw = String(value || '').trim();
  if (!raw) return '/dashboard';
  if (!raw.startsWith('/')) return '/dashboard';
  if (
    raw.startsWith('/welcome')
    || raw.startsWith('/auth/')
    || raw.startsWith('/subscription/success')
    || raw.startsWith('/subscription/payment-result')
  ) {
    return '/dashboard';
  }
  return raw;
}