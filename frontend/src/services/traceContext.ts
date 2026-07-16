const SESSION_STORAGE_KEY = 'obs_session_id_v1';

function randomHex(bytes: number): string {
  if (typeof window !== 'undefined' && window.crypto?.getRandomValues) {
    const arr = new Uint8Array(bytes);
    window.crypto.getRandomValues(arr);
    return Array.from(arr)
      .map((value) => value.toString(16).padStart(2, '0'))
      .join('');
  }
  let out = '';
  for (let i = 0; i < bytes; i += 1) {
    out += Math.floor(Math.random() * 256).toString(16).padStart(2, '0');
  }
  return out;
}

export function getOrCreateObservabilitySessionId(): string {
  if (typeof window === 'undefined') return '';
  try {
    const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const next = `obs_${randomHex(12)}`;
    window.localStorage.setItem(SESSION_STORAGE_KEY, next);
    return next;
  } catch {
    return `obs_${randomHex(12)}`;
  }
}

export function buildTraceparentHeader(): string {
  // W3C traceparent: version-traceid-spanid-flags
  const traceId = randomHex(16); // 32 hex chars
  const spanId = randomHex(8); // 16 hex chars
  const traceFlags = '01';
  return `00-${traceId}-${spanId}-${traceFlags}`;
}

export function buildObservabilityHeaders(): Record<string, string> {
  const traceparent = buildTraceparentHeader();
  const traceId = traceparent.split('-')[1] || randomHex(16);
  const correlationId = `corr_${traceId}`;
  const sessionId = getOrCreateObservabilitySessionId();
  return {
    traceparent,
    'x-correlation-id': correlationId,
    'x-session-id': sessionId,
  };
}
