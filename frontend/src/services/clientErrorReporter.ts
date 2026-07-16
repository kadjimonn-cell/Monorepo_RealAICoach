import { Platform } from 'react-native';
import { buildObservabilityHeaders } from './traceContext';

import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';

/**
 * Fire-and-forget client crash reporter used by the ErrorBoundary.
 * Uses navigator.sendBeacon when available so the report still goes out
 * even if the tab is mid-crash or the user immediately reloads.
 */

type CrashReport = {
  panelId?: string;
  panelName?: string;
  message: string;
  stack?: string;
  componentStack?: string;
};

function getIngestUrl(): string {
  // Resolve at call-time so we always use the live window origin when the
  // baked-in preview URL has drifted (common in forked jobs).
  try {
    const base = resolveRuntimeBaseUrl();
    return base ? `${base}/api/errors/client` : '/api/errors/client';
  } catch {
    return '/api/errors/client';
  }
}

const RECENT_CAP = 8;
const RECENT_WINDOW_MS = 60_000; // dedupe identical crashes within a minute
const recent: { key: string; at: number }[] = [];

function getClientId(): string {
  try {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return 'native-preview';
    const existing = window.localStorage.getItem('client_error_id');
    if (existing) return existing;
    const created = `cei_${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem('client_error_id', created);
    return created;
  } catch {
    return 'anon';
  }
}

function isDuplicate(key: string): boolean {
  const now = Date.now();
  // drop stale
  while (recent.length && now - recent[0].at > RECENT_WINDOW_MS) recent.shift();
  if (recent.some((r) => r.key === key)) return true;
  recent.push({ key, at: now });
  if (recent.length > RECENT_CAP) recent.shift();
  return false;
}

export function reportClientCrash(report: CrashReport): void {
  try {
    const routeScopedPanelId = (
      Platform.OS === 'web' && typeof window !== 'undefined'
        ? `route:${window.location.pathname || '/'}`
        : 'unknown'
    );
    const panelId = (report.panelId || routeScopedPanelId || 'unknown').slice(0, 120);
    const message = (report.message || '').slice(0, 1024);
    if (!message) return;
    const key = `${panelId}::${message}`;
    if (isDuplicate(key)) return;

    const payload = {
      panel_id: panelId,
      panel_name: (report.panelName || '').slice(0, 120),
      message,
      stack: (report.stack || '').slice(0, 8192),
      component_stack: (report.componentStack || '').slice(0, 8192),
      pathname:
        Platform.OS === 'web' && typeof window !== 'undefined'
          ? window.location.pathname
          : '',
      user_agent:
        Platform.OS === 'web' && typeof navigator !== 'undefined'
          ? navigator.userAgent
          : 'native-preview',
      client_id: getClientId(),
    };

    const body = JSON.stringify(payload);

    if (
      Platform.OS === 'web' &&
      typeof navigator !== 'undefined' &&
      typeof navigator.sendBeacon === 'function'
    ) {
      try {
        const blob = new Blob([body], { type: 'application/json' });
        const sent = navigator.sendBeacon(getIngestUrl(), blob);
        if (sent) return;
      } catch {
        // fall through to fetch
      }
    }

    // Fallback: regular fetch with keepalive so it survives navigation
    void fetch(getIngestUrl(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...buildObservabilityHeaders() },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {
    // best-effort telemetry only
  }
}
