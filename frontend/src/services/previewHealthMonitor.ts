import { Platform } from 'react-native';
import { buildObservabilityHeaders } from './traceContext';
import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const BACKEND_BASE = resolveRuntimeBaseUrl().replace(/\/+$/, '');
const PREVIEW_INGEST_URL = BACKEND_BASE ? `${BACKEND_BASE}/api/platform-shell-health/preview-ingest` : '/api/platform-shell-health/preview-ingest';

function getClientId() {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return 'preview-native';
  const key = 'preview_health_client_id';
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const created = `phc_${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem(key, created);
  return created;
}

function readChallengeSignals() {
  if (Platform.OS !== 'web' || typeof document === 'undefined') {
    return {
      has_cf_challenge_script: false,
      has_cf_turnstile_iframe: false,
      contains_checking_browser_text: false,
      contains_enable_js_text: false,
    };
  }

  const bodyText = (document.body?.innerText || '').toLowerCase();
  const hasChallengeScript = Boolean(document.querySelector('script[src*="/cdn-cgi/challenge-platform/"]'));
  const hasTurnstile = Boolean(document.querySelector('iframe[src*="challenges.cloudflare.com"]'));

  return {
    has_cf_challenge_script: hasChallengeScript,
    has_cf_turnstile_iframe: hasTurnstile,
    contains_checking_browser_text: bodyText.includes('checking your browser'),
    contains_enable_js_text: bodyText.includes('enable javascript'),
  };
}

function collectRenderSnapshot() {
  if (Platform.OS !== 'web' || typeof document === 'undefined') {
    return {
      root_present: false,
      app_ready: false,
      element_count: 0,
      text_length: 0,
    };
  }
  const root = document.getElementById('root');
  const textLength = ((root?.innerText || '').replace(/\s+/g, '').length || 0);
  const elementCount = root?.querySelectorAll('*')?.length || 0;
  return {
    root_present: Boolean(root),
    app_ready: root?.getAttribute('data-app-ready') === 'true',
    element_count: elementCount,
    text_length: textLength,
  };
}

function toPayload(eventType: string, metadata: Record<string, any> = {}) {
  const href = Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.href : '';
  const pathname = Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.pathname : '';
  const host = Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.hostname : '';
  const referrer = Platform.OS === 'web' && typeof document !== 'undefined' ? document.referrer || '' : '';
  const referrerHost = referrer.includes('//') ? referrer.split('//')[1].split('/')[0] : '';

  let embedded = false;
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      embedded = window.self !== window.top;
    } catch {
      embedded = true;
    }
  }

  return {
    event_type: eventType,
    client_id: getClientId(),
    captured_at: new Date().toISOString(),
    href,
    pathname,
    host,
    referrer,
    referrer_host: referrerHost,
    embedded,
    visibility_state: Platform.OS === 'web' && typeof document !== 'undefined' ? document.visibilityState : '',
    ready_state: Platform.OS === 'web' && typeof document !== 'undefined' ? document.readyState : '',
    cookie_enabled: Platform.OS === 'web' && typeof navigator !== 'undefined' ? Boolean(navigator.cookieEnabled) : false,
    user_agent: Platform.OS === 'web' && typeof navigator !== 'undefined' ? navigator.userAgent : 'native-preview',
    challenge_signals: readChallengeSignals(),
    render: collectRenderSnapshot(),
    metadata,
  };
}

export async function reportPreviewHealth(eventType: string, metadata: Record<string, any> = {}) {
  const payload = toPayload(eventType, metadata);
  try {
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      const ok = navigator.sendBeacon(PREVIEW_INGEST_URL, JSON.stringify(payload));
      if (ok) return;
    }
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/services/previewHealthMonitor.ts#catch1',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }

  try {
    await fetch(PREVIEW_INGEST_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...buildObservabilityHeaders() },
      body: JSON.stringify(payload),
      keepalive: true,
    });
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/services/previewHealthMonitor.ts#catch2',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }
}
