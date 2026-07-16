import { handleAppRecoverableError } from './appRecoverableError';
const getConfiguredOrigins = (): string[] => {
  if (typeof window === 'undefined') return [];

  const origins = new Set<string>();
  const currentOrigin = window.location.origin?.trim();
  if (currentOrigin) origins.add(currentOrigin);

  const rawConfigured = [
    process.env.EXPO_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL,
    process.env.REACT_APP_BACKEND_URL,
  ]
    .map((value) => String(value || '').trim())
    .filter(Boolean);

  rawConfigured.forEach((value) => {
    try {
      origins.add(new URL(value).origin);
    } catch (error) { handleAppRecoverableError({ scope: 'src/utils/ssoMessagingSecurity.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  });

  return Array.from(origins);
};

export const resolveSsoPopupTargetOrigin = (): string | null => {
  const origins = getConfiguredOrigins();
  return origins[0] || null;
};

export const isTrustedSsoMessageOrigin = (origin: string): boolean => {
  if (!origin) return false;
  const normalized = String(origin).trim();
  return getConfiguredOrigins().includes(normalized);
};
