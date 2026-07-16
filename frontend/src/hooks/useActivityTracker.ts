import { useEffect, useRef, useCallback } from 'react';
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

/**
 * useActivityTracker — Logs page views, feature completions, and error events
 * to the backend live activity feed for admin monitoring.
 *
 * Auto-logs: page_view on route change
 * Manual: logEvent(), logCompletion(), logError()
 */

let _lastPageView = '';
let _lastDispatchAt = 0;
let _eventWindow: number[] = [];
const _eventSignatureTimestamps = new Map<string, number>();
let _feedbackSessionId = '';

const EVENT_GLOBAL_THROTTLE_MS = 1200;
const EVENT_DUPLICATE_WINDOW_MS = 30000;
const EVENT_WINDOW_MS = 60000;
const EVENT_MAX_PER_WINDOW = 24;

const shouldSkipEvent = (eventType: string, detail: string) => {
  const now = Date.now();
  _eventWindow = _eventWindow.filter((ts) => now - ts < EVENT_WINDOW_MS);

  if (_eventWindow.length >= EVENT_MAX_PER_WINDOW) return true;
  if (now - _lastDispatchAt < EVENT_GLOBAL_THROTTLE_MS) return true;

  const normalizedType = String(eventType || '').trim().toLowerCase();
  const normalizedDetail = String(detail || '').trim().toLowerCase().slice(0, 140);
  const signature = `${normalizedType}|${normalizedDetail}`;
  const previous = _eventSignatureTimestamps.get(signature) || 0;
  if (now - previous < EVENT_DUPLICATE_WINDOW_MS) return true;

  _eventSignatureTimestamps.set(signature, now);
  _eventWindow.push(now);
  _lastDispatchAt = now;
  return false;
};

const shouldIgnoreGlobalError = (message: string) => {
  const value = String(message || '').toLowerCase();
  if (!value) return true;
  return (
    value.includes('too many requests') ||
    value.includes('rate limit') ||
    value.includes('status code 429') ||
    value.includes('status code 403') ||
    value.includes('status code 401') ||
    value.includes('network request failed') ||
    value.includes('failed to fetch') ||
    value.includes('aborted')
  );
};

const getFeedbackSessionId = () => {
  if (typeof window === 'undefined') return 'anonymous';
  if (_feedbackSessionId) return _feedbackSessionId;
  const existing = window.sessionStorage.getItem('feedback_loop_session_id');
  if (existing) {
    _feedbackSessionId = existing;
    return existing;
  }
  _feedbackSessionId = `feedback_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  window.sessionStorage.setItem('feedback_loop_session_id', _feedbackSessionId);
  return _feedbackSessionId;
};

const sendFeedbackSignal = async (event_type: string, payload: Record<string, any>) => {
  if (Platform.OS !== 'web') return;
  const baseUrl = resolveRuntimeBaseUrl();
  if (!baseUrl) return;
  const body = JSON.stringify({
    event_type,
    session_id: getFeedbackSessionId(),
    ...payload,
  });

  try {
    const token = await AsyncStorage.getItem('session_token');
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    await fetch(`${baseUrl}/api/admin/autonomous-engine/feedback/collect`, {
      method: 'POST',
      headers,
      body,
      keepalive: true,
      credentials: 'include',
    });
  } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useActivityTracker.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
};

export function useActivityTracker(pathname: string, enabled = true) {
  const debounceRef = useRef<any>(null);
  const routeStateRef = useRef({ path: '', startedAt: 0, interactionCount: 0, errorCount: 0 });

  const logEvent = useCallback(async (eventType: string, detail: string, metadata?: Record<string, any>) => {
    if (Platform.OS !== 'web' || !enabled) return;
    if (shouldSkipEvent(eventType, detail)) return;

    try {
      const token = await AsyncStorage.getItem('session_token');
      if (!token) return;
      const baseUrl = resolveRuntimeBaseUrl();
      const payload = JSON.stringify({ event_type: eventType, detail, metadata: metadata || {} });

      await fetch(`${baseUrl}/api/admin/live-activity/log-event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: payload,
        keepalive: true,
      });
    } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useActivityTracker.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [enabled]);

  /** Log a feature completion event (e.g., onboarding step, course finish) */
  const logCompletion = useCallback((featureName: string, metadata?: Record<string, any>) => {
    logEvent('completion', `Completed: ${featureName}`, { feature: featureName, ...metadata });
  }, [logEvent]);

  /** Log a client-side error event */
  const logError = useCallback((errorMessage: string, metadata?: Record<string, any>) => {
    logEvent('error', `Error: ${errorMessage}`, { error: errorMessage, source: 'client', ...metadata });
  }, [logEvent]);

  // Track page views on route change
  useEffect(() => {
    if (!enabled) return;
    if (!pathname || pathname === _lastPageView) return;

    const previous = routeStateRef.current;
    if (previous.path && previous.path !== pathname) {
      sendFeedbackSignal('route_exit', {
        route: previous.path,
        duration_ms: Date.now() - previous.startedAt,
        interaction_count: previous.interactionCount,
        metadata: { error_count: previous.errorCount },
      });
    }

    routeStateRef.current = { path: pathname, startedAt: Date.now(), interactionCount: 0, errorCount: 0 };
    _lastPageView = pathname;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const pageName = pathname.replace(/^\/(tabs\/)?/, '').replace(/\//g, ' > ') || 'Home';
      logEvent('page_view', `Viewed ${pageName}`);
      sendFeedbackSignal('page_view', { route: pathname, metadata: { page_name: pageName } });
    }, 500);
  }, [enabled, pathname, logEvent]);

  // Global error listener — auto-log unhandled errors
  useEffect(() => {
    if (Platform.OS !== 'web' || !enabled) return;
    const handler = (event: ErrorEvent) => {
      if (shouldIgnoreGlobalError(event.message || '')) return;
      routeStateRef.current.errorCount += 1;
      logEvent('error', `Unhandled: ${event.message?.slice(0, 120)}`, {
        source: 'window.onerror',
        filename: event.filename,
        lineno: event.lineno,
      });
      sendFeedbackSignal('error', {
        route: routeStateRef.current.path || pathname,
        error_message: event.message?.slice(0, 200),
        metadata: { source: 'window.onerror', filename: event.filename, lineno: event.lineno },
      });
    };
    const rejectionHandler = (event: PromiseRejectionEvent) => {
      const reason = event.reason?.message || String(event.reason).slice(0, 120);
      if (shouldIgnoreGlobalError(reason)) return;
      routeStateRef.current.errorCount += 1;
      logEvent('error', `Unhandled rejection: ${reason}`, { source: 'unhandledrejection' });
      sendFeedbackSignal('error', {
        route: routeStateRef.current.path || pathname,
        error_message: reason,
        metadata: { source: 'unhandledrejection' },
      });
    };
    const clickHandler = (event: Event) => {
      const target = event.target as HTMLElement | null;
      const actionable = target?.closest('button, a, [role="button"], [data-testid]') as HTMLElement | null;
      if (!actionable) return;
      routeStateRef.current.interactionCount += 1;
      const targetName = actionable.getAttribute('data-testid') || actionable.getAttribute('aria-label') || actionable.textContent?.trim() || actionable.tagName.toLowerCase();
      const started = performance.now();
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const durationMs = Math.round(performance.now() - started);
          sendFeedbackSignal('interaction', {
            route: routeStateRef.current.path || pathname,
            target: String(targetName || '').slice(0, 160),
            duration_ms: durationMs,
            metadata: { tag: actionable.tagName.toLowerCase() },
          });
        });
      });
    };
    const unloadHandler = () => {
      if (!routeStateRef.current.path) return;
      sendFeedbackSignal('route_exit', {
        route: routeStateRef.current.path,
        duration_ms: Date.now() - routeStateRef.current.startedAt,
        interaction_count: routeStateRef.current.interactionCount,
        metadata: { error_count: routeStateRef.current.errorCount, source: 'beforeunload' },
      });
    };
    window.addEventListener('error', handler);
    window.addEventListener('unhandledrejection', rejectionHandler);
    window.addEventListener('click', clickHandler, true);
    window.addEventListener('beforeunload', unloadHandler);
    return () => {
      window.removeEventListener('error', handler);
      window.removeEventListener('unhandledrejection', rejectionHandler);
      window.removeEventListener('click', clickHandler, true);
      window.removeEventListener('beforeunload', unloadHandler);
    };
  }, [enabled, logEvent, pathname]);

  return { logEvent, logCompletion, logError };
}
