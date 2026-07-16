/**
 * useLiveQuery — Auto-fetching hook with real-time updates.
 *
 * Fetches data from an API endpoint and auto-refetches when:
 * 1. A WebSocket `data_change` event arrives for the specified entity
 * 2. The user returns to the tab (visibility change)
 * 3. The component mounts
 * 4. Manual refetch() is called
 *
 * Usage:
 *   const { data, loading, error, refetch } = useLiveQuery('/admin/users', 'users');
 *   const { data } = useLiveQuery('/features/registry', 'features', { pollInterval: 60000 });
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Platform, AppState } from 'react-native';
import api from '../services/api';
import { useRealtime } from '../context/RealtimeContext';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const LIVE_QUERY_CACHE_PREFIX = 'live_query_snapshot_v1:';
const LIVE_QUERY_CACHE_TTL_MS = 10 * 60 * 1000;
const LIVE_QUERY_FRESH_SNAPSHOT_MS = 30 * 1000;
const LIVE_QUERY_MIN_FETCH_GAP_MS = 8 * 1000;

type GlobalPollEntry = {
  intervalId: ReturnType<typeof setInterval>;
  listeners: Set<() => void>;
};

const GLOBAL_LIVEQUERY_LAST_FETCH_AT = new Map<string, number>();
const GLOBAL_LIVEQUERY_INFLIGHT = new Map<string, Promise<any>>();
const GLOBAL_LIVEQUERY_POLLERS = new Map<string, GlobalPollEntry>();

function getGlobalPollerKey(endpoint: string, intervalMs: number): string {
  return `${endpoint}::${Math.max(1000, Math.floor(intervalMs))}`;
}

function subscribeGlobalPoller(endpoint: string, intervalMs: number, listener: () => void): () => void {
  const key = getGlobalPollerKey(endpoint, intervalMs);
  let entry = GLOBAL_LIVEQUERY_POLLERS.get(key);
  if (!entry) {
    const listeners = new Set<() => void>();
    const intervalId = setInterval(() => {
      for (const fn of Array.from(listeners)) {
        try {
          fn();
        } catch {
          // no-op
        }
      }
    }, Math.max(1000, intervalMs));
    entry = { intervalId, listeners };
    GLOBAL_LIVEQUERY_POLLERS.set(key, entry);
  }

  entry.listeners.add(listener);

  return () => {
    const current = GLOBAL_LIVEQUERY_POLLERS.get(key);
    if (!current) return;
    current.listeners.delete(listener);
    if (current.listeners.size === 0) {
      clearInterval(current.intervalId);
      GLOBAL_LIVEQUERY_POLLERS.delete(key);
    }
  };
}

function readLiveQuerySnapshot<T = any>(endpoint: string): { data: T; cachedAt: number } | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
  const cacheKey = `${LIVE_QUERY_CACHE_PREFIX}${endpoint}`;
  try {
    const raw = window.sessionStorage.getItem(cacheKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.cachedAt !== 'number') {
      window.sessionStorage.removeItem(cacheKey);
      return null;
    }
    if (Date.now() - parsed.cachedAt > LIVE_QUERY_CACHE_TTL_MS) {
      window.sessionStorage.removeItem(cacheKey);
      return null;
    }
    return parsed;
  } catch {
    try {
      window.sessionStorage.removeItem(cacheKey);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'src/hooks/useLiveQuery.ts#catch1',
        error,
        message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      });
    }
    return null;
  }
}

function writeLiveQuerySnapshot(endpoint: string, data: any) {
  if (Platform.OS !== 'web' || typeof window === 'undefined' || data == null) return;
  const payload = JSON.stringify({ data, cachedAt: Date.now() });
  const cacheKey = `${LIVE_QUERY_CACHE_PREFIX}${endpoint}`;
  try {
    window.sessionStorage.setItem(cacheKey, payload);
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/hooks/useLiveQuery.ts#catch2',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }
}

interface UseLiveQueryOptions {
  /** WebSocket entity to listen for (triggers refetch on data_change) */
  entity?: string;
  /** Additional entities to listen for */
  entities?: string[];
  /** Fallback poll interval in ms (default: none) */
  pollInterval?: number;
  /** Whether to refetch on window/tab focus (default: true) */
  refetchOnFocus?: boolean;
  /** Whether to skip the initial fetch (default: false) */
  skip?: boolean;
  /** Transform the response data */
  transform?: (data: any) => any;
  /** Dependencies that trigger a refetch when changed */
  deps?: any[];
}

interface UseLiveQueryResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  lastUpdated: Date | null;
}

export function useLiveQuery<T = any>(
  endpoint: string,
  entityOrOptions?: string | UseLiveQueryOptions,
  options?: UseLiveQueryOptions,
): UseLiveQueryResult<T> {
  // Normalize args: useLiveQuery('/endpoint', 'entity') or useLiveQuery('/endpoint', { entity: '...' })
  const opts: UseLiveQueryOptions = typeof entityOrOptions === 'string'
    ? { entity: entityOrOptions, ...options }
    : entityOrOptions || {};

  const normalizedEndpoint = String(endpoint || '').trim();
  const { entity, entities = [], pollInterval, refetchOnFocus = true, skip = false, transform } = opts;
  const shouldSkip = skip || !normalizedEndpoint;
  const allEntities = entity ? [entity, ...entities] : entities;
  const initialSnapshot = readLiveQuerySnapshot<T>(normalizedEndpoint);
  const initialSnapshotAgeMs = initialSnapshot ? Date.now() - initialSnapshot.cachedAt : Number.POSITIVE_INFINITY;
  const hasFreshSnapshot = initialSnapshotAgeMs <= LIVE_QUERY_FRESH_SNAPSHOT_MS;

  const [data, setData] = useState<T | null>(initialSnapshot?.data || null);
  const [loading, setLoading] = useState(!shouldSkip && !initialSnapshot?.data);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(initialSnapshot?.cachedAt ? new Date(initialSnapshot.cachedAt) : null);
  const mountedRef = useRef(true);
  const fetchingRef = useRef(false);
  const latestDataRef = useRef<T | null>(initialSnapshot?.data || null);
  const lastFetchAtRef = useRef(initialSnapshot?.cachedAt || 0);
  const { subscribe } = useRealtime();

  useEffect(() => {
    latestDataRef.current = data;
  }, [data]);

  const fetchData = useCallback(async (force = false) => {
    if (shouldSkip || fetchingRef.current) return;
    const now = Date.now();
    const globalLastFetch = GLOBAL_LIVEQUERY_LAST_FETCH_AT.get(normalizedEndpoint) || 0;
    if (!force && (lastFetchAtRef.current && (now - lastFetchAtRef.current) < LIVE_QUERY_MIN_FETCH_GAP_MS)) return;
    if (!force && globalLastFetch && (now - globalLastFetch) < LIVE_QUERY_MIN_FETCH_GAP_MS) return;
    fetchingRef.current = true;
    lastFetchAtRef.current = now;

    try {
      let requestTask = GLOBAL_LIVEQUERY_INFLIGHT.get(normalizedEndpoint);
      if (!requestTask) {
        requestTask = api.get(normalizedEndpoint)
          .finally(() => {
            const current = GLOBAL_LIVEQUERY_INFLIGHT.get(normalizedEndpoint);
            if (current === requestTask) {
              GLOBAL_LIVEQUERY_INFLIGHT.delete(normalizedEndpoint);
            }
          });
        GLOBAL_LIVEQUERY_INFLIGHT.set(normalizedEndpoint, requestTask);
      }

      const res = await requestTask;
      GLOBAL_LIVEQUERY_LAST_FETCH_AT.set(normalizedEndpoint, Date.now());
      if (mountedRef.current) {
        const result = transform ? transform(res.data) : res.data;
        setData(result);
        writeLiveQuerySnapshot(normalizedEndpoint, result);
        setError(null);
        setLastUpdated(new Date());
        setLoading(false);
      }
    } catch (e: any) {
      if (mountedRef.current) {
        const fallbackSnapshot = readLiveQuerySnapshot<T>(normalizedEndpoint);
        if (!latestDataRef.current && fallbackSnapshot?.data) {
          setData(fallbackSnapshot.data);
          setLastUpdated(new Date(fallbackSnapshot.cachedAt));
          setError(null);
        } else {
          setError(e?.message || 'Failed to fetch');
        }
        setLoading(false);
      }
    } finally {
      fetchingRef.current = false;
    }
  }, [normalizedEndpoint, shouldSkip, transform]);

  // Initial fetch
  useEffect(() => {
    mountedRef.current = true;
    if (shouldSkip) {
      setLoading(false);
      return () => { mountedRef.current = false; };
    }
    let idleTimeoutId: ReturnType<typeof setTimeout> | null = null;
    let idleCallbackHandle: any = null;
    if (hasFreshSnapshot) {
      const scheduleRefresh = () => {
        fetchData();
      };
      if (Platform.OS === 'web' && typeof window !== 'undefined' && 'requestIdleCallback' in window) {
        idleCallbackHandle = (window as any).requestIdleCallback(scheduleRefresh, { timeout: 1600 });
      } else {
        idleTimeoutId = setTimeout(scheduleRefresh, 900);
      }
    } else {
      fetchData(true);
    }
    return () => {
      mountedRef.current = false;
      if (idleTimeoutId) clearTimeout(idleTimeoutId);
      if (idleCallbackHandle && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
        (window as any).cancelIdleCallback(idleCallbackHandle);
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchData, hasFreshSnapshot, shouldSkip, ...(opts.deps || [])]);

  // WebSocket subscriptions
  useEffect(() => {
    if (shouldSkip || allEntities.length === 0) return;
    const unsubs = allEntities.map(e => subscribe(e, () => fetchData()));
    return () => unsubs.forEach(u => u());
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allEntities.join(','), subscribe, fetchData, shouldSkip]);

  // Refetch on tab/window focus
  useEffect(() => {
    if (!refetchOnFocus || shouldSkip) return;

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') fetchData();
    };

    if (Platform.OS === 'web') {
      document.addEventListener('visibilitychange', handleVisibility);
    }

    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') fetchData();
    });

    return () => {
      if (Platform.OS === 'web') {
        document.removeEventListener('visibilitychange', handleVisibility);
      }
      sub.remove();
    };
  }, [refetchOnFocus, fetchData, shouldSkip]);

  // Fallback polling
  useEffect(() => {
    if (!pollInterval || shouldSkip) return;
    return subscribeGlobalPoller(normalizedEndpoint, pollInterval, () => {
      void fetchData();
    });
  }, [pollInterval, fetchData, shouldSkip, normalizedEndpoint]);

  return { data, loading, error, refetch: () => fetchData(true), lastUpdated };
}
