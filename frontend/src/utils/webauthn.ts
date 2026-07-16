import { Platform } from 'react-native';

const toBase64Url = (value: ArrayBuffer | Uint8Array): string => {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
};

const fromBase64Url = (value: string): Uint8Array => {
  const normalized = String(value || '').replace(/-/g, '+').replace(/_/g, '/');
  const pad = normalized.length % 4;
  const padded = pad ? normalized + '='.repeat(4 - pad) : normalized;
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
};

export const isPasskeySupportedOnWeb = (): boolean => {
  return Boolean(
    Platform.OS === 'web'
    && typeof window !== 'undefined'
    && (window as any).PublicKeyCredential
    && (navigator as any)?.credentials,
  );
};

export const normalizeRegistrationOptions = (serverOptions: any) => {
  const options = { ...(serverOptions || {}) };
  options.challenge = fromBase64Url(options.challenge);
  if (options.user?.id) {
    options.user = { ...options.user, id: fromBase64Url(options.user.id) };
  }
  if (Array.isArray(options.excludeCredentials)) {
    options.excludeCredentials = options.excludeCredentials.map((item: any) => ({
      ...item,
      id: fromBase64Url(item.id),
    }));
  }
  return options;
};

export const normalizeAuthenticationOptions = (serverOptions: any) => {
  const options = { ...(serverOptions || {}) };
  options.challenge = fromBase64Url(options.challenge);
  if (Array.isArray(options.allowCredentials)) {
    options.allowCredentials = options.allowCredentials.map((item: any) => ({
      ...item,
      id: fromBase64Url(item.id),
    }));
  }
  return options;
};

export const serializeWebAuthnCredential = (credential: any) => {
  const response = credential?.response || {};
  const serialized: any = {
    id: credential?.id,
    type: credential?.type || 'public-key',
    rawId: toBase64Url(credential?.rawId),
    response: {
      clientDataJSON: response.clientDataJSON ? toBase64Url(response.clientDataJSON) : undefined,
      attestationObject: response.attestationObject ? toBase64Url(response.attestationObject) : undefined,
      authenticatorData: response.authenticatorData ? toBase64Url(response.authenticatorData) : undefined,
      signature: response.signature ? toBase64Url(response.signature) : undefined,
      userHandle: response.userHandle ? toBase64Url(response.userHandle) : undefined,
    },
  };

  if (typeof response?.getTransports === 'function') {
    try {
      serialized.response.transports = response.getTransports();
    } catch {
      serialized.response.transports = [];
    }
  }

  return serialized;
};
