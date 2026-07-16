import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

export interface VanityMetrics {
  active_users: number;
  ai_sessions_today: number;
  global_coaches: number;
  performance_boost: number;
  users_online: number;
  system_health: number;
}

const _POLL_INTERVAL = 45_000; // 45 seconds
const SNAPSHOT_KEY = 'welcome-vanity-metrics-snapshot-v1';

function readSnapshot(): VanityMetrics | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(SNAPSHOT_KEY) || window.localStorage.getItem(SNAPSHOT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeSnapshot(metrics: VanityMetrics) {
  if (typeof window === 'undefined') return;
  try {
    const payload = JSON.stringify(metrics);
    window.sessionStorage.setItem(SNAPSHOT_KEY, payload);
    window.localStorage.setItem(SNAPSHOT_KEY, payload);
  } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useVanityMetrics.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

export function useVanityMetrics() {
  const [metrics, setMetrics] = useState<VanityMetrics | null>(() => readSnapshot());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await api.get('/system/vanity-metrics');
      setMetrics(res.data);
      writeSnapshot(res.data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    fetchMetrics();
    const refresh = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
      fetchMetrics();
    };
    intervalRef.current = setInterval(refresh, 90_000);
    const onVisible = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') refresh();
    };
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisible);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisible);
      }
    };
  }, [fetchMetrics]);

  return metrics;
}
