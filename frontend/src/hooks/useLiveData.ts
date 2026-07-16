/**
 * useLiveData — WebSocket-powered hook that listens for data_change events
 * and auto-refetches data, so dashboards update without page refresh.
 *
 * Usage:
 *   const { data, loading, error, refetch } = useLiveData('/goals', ['goals']);
 *
 * When the WebSocket broadcasts a data_change event for entity 'goals',
 * the hook automatically refetches the API endpoint.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import { useRealtime } from '../context/RealtimeContext';

interface UseLiveDataOptions {
  /** Poll interval in ms as fallback if WebSocket is unavailable (default: 0 = no polling) */
  pollInterval?: number;
  /** Whether to fetch immediately on mount (default: true) */
  fetchOnMount?: boolean;
}

export function useLiveData<T = any>(
  endpoint: string,
  entities: string[] = [],
  options: UseLiveDataOptions = {},
) {
  const { pollInterval = 0, fetchOnMount = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const { subscribe } = useRealtime();

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const resp = await api.get(endpoint);
      if (mountedRef.current) {
        setData(resp.data);
        setLoading(false);
      }
    } catch (e: any) {
      if (mountedRef.current) {
        setError(e?.message || 'Failed to fetch');
        setLoading(false);
      }
    }
  }, [endpoint]);

  // Subscribe to RealtimeContext-managed data_change events for live updates
  useEffect(() => {
    mountedRef.current = true;
    if (fetchOnMount) fetchData();

    let pollTimer: any;
    if (pollInterval > 0) {
      pollTimer = setInterval(fetchData, pollInterval);
    }

    const uniqueEntities = Array.from(new Set(entities.filter(Boolean)));
    const unsubscribers = uniqueEntities.map((entity) => subscribe(entity, () => fetchData()));

    return () => {
      mountedRef.current = false;
      if (pollTimer) clearInterval(pollTimer);
      unsubscribers.forEach((unsub) => unsub());
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, entities.join(','), pollInterval, fetchOnMount, fetchData, subscribe]);

  return { data, loading, error, refetch: fetchData };
}
