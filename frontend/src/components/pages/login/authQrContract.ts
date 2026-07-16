export const AUTH_QR_RENDER_CONTRACT = Object.freeze({
  backgroundColor: '#FFFFFF',
  moduleColor: '#111827',
  quietZonePadding: 16,
  size: 176,
  borderRadius: 16,
});

export function normalizeAuthQrPayload(value: unknown): string {
  return String(value || '').trim();
}

export function isValidAuthQrPayload(value: unknown): boolean {
  const payload = normalizeAuthQrPayload(value);
  if (!payload) return false;

  try {
    const parsed = new URL(payload);
    return Boolean(
      parsed.protocol &&
      /^https?:$/i.test(parsed.protocol) &&
      parsed.host &&
      parsed.pathname === '/auth/qr-approve' &&
      parsed.searchParams.get('session')
    );
  } catch {
    return false;
  }
}