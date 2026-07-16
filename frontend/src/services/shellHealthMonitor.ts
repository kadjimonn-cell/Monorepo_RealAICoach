import { Platform } from 'react-native';
import { buildObservabilityHeaders } from './traceContext';
import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

type ShellMetricKey = 'dedupe_hits' | 'fallback_activations' | 'route_recoveries' | 'rate_limit_429s';

type ShellHealthCounters = Record<ShellMetricKey, number>;

const BACKEND_BASE = resolveRuntimeBaseUrl().replace(/\/+$/, '');
const INGEST_URL = BACKEND_BASE ? `${BACKEND_BASE}/api/platform-shell-health/ingest` : '/api/platform-shell-health/ingest';
const DEFAULT_COUNTERS: ShellHealthCounters = {
  dedupe_hits: 0,
  fallback_activations: 0,
  route_recoveries: 0,
  rate_limit_429s: 0,
};

let pendingCounters: ShellHealthCounters = { ...DEFAULT_COUNTERS };
let pendingEvents: Record<string, any>[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function getClientId() {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return 'native-preview';
  const existing = window.localStorage.getItem('shell_health_client_id');
  if (existing) return existing;
  const created = `shc_${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem('shell_health_client_id', created);
  return created;
}

async function flushShellHealthMetrics() {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }

  const counters = pendingCounters;
  const events = pendingEvents;
  pendingCounters = { ...DEFAULT_COUNTERS };
  pendingEvents = [];

  const hasCounters = Object.values(counters).some((value) => value > 0);
  if (!hasCounters && events.length === 0) return;

  const payload = {
    client_id: getClientId(),
    counters,
    events,
    pathname: Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.pathname : '',
    user_agent: Platform.OS === 'web' && typeof navigator !== 'undefined' ? navigator.userAgent : 'native-preview',
    captured_at: new Date().toISOString(),
  };

  try {
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      navigator.sendBeacon(INGEST_URL, JSON.stringify(payload));
      return;
    }
  } catch (error) { handleAppRecoverableError({ scope: 'src/services/shellHealthMonitor.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

  try {
    await fetch(INGEST_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...buildObservabilityHeaders() },
      body: JSON.stringify(payload),
      keepalive: true,
    });
  } catch (error) { handleAppRecoverableError({ scope: 'src/services/shellHealthMonitor.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

export function recordShellHealthMetric(metric: ShellMetricKey, metadata: Record<string, any> = {}) {
  pendingCounters[metric] = (pendingCounters[metric] || 0) + 1;
  recordShellHealthEvent(metric, metadata);
}

export function recordShellHealthEvent(metric: string, metadata: Record<string, any> = {}) {
  pendingEvents.push({
    metric,
    metadata,
    pathname: Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.pathname : '',
    timestamp: new Date().toISOString(),
  });
  pendingEvents = pendingEvents.slice(-25);

  if (flushTimer) return;
  flushTimer = setTimeout(() => {
    void flushShellHealthMetrics();
  }, 5000);
}

export function flushShellHealthNow() {
  return flushShellHealthMetrics();
}