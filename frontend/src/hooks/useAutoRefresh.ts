import { useEffect, useRef, useCallback } from 'react';
import { AppState, Platform } from 'react-native';

/**
 * Auto-refreshes data when:
 * 1. Browser tab becomes visible (web)
 * 2. App returns to foreground (native)
 * 3. Periodic interval (optional)
 */
export function useAutoRefresh(
  refreshFn: () => void,
  options?: { intervalMs?: number; enabled?: boolean }
) {
  const { intervalMs, enabled = true } = options || {};
  const lastRefresh = useRef(Date.now());

  const doRefresh = useCallback(() => {
    const now = Date.now();
    if (now - lastRefresh.current < 5000) return; // debounce 5s
    lastRefresh.current = now;
    refreshFn();
  }, [refreshFn]);

  // AppState change (works on both web and native)
  useEffect(() => {
    if (!enabled) return;
    const sub = AppState.addEventListener('change', s => {
      if (s === 'active') doRefresh();
    });
    return () => sub.remove();
  }, [doRefresh, enabled]);

  // Browser visibility API (web only, more reliable than AppState for tab switches)
  useEffect(() => {
    if (!enabled || Platform.OS !== 'web') return;
    const handler = () => {
      if (document.visibilityState === 'visible') doRefresh();
    };
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, [doRefresh, enabled]);

  // Optional periodic refresh
  useEffect(() => {
    if (!enabled || !intervalMs) return;
    const id = setInterval(doRefresh, intervalMs);
    return () => clearInterval(id);
  }, [doRefresh, intervalMs, enabled]);
}
