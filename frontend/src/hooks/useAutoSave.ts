import { useEffect, useRef, useCallback } from 'react';
import api from '../services/api';

/**
 * useAutoSave — Automatically saves form data after a debounce period.
 * Uses a debounce pattern: saves only after the user stops editing for `delayMs`.
 * 
 * @param endpoint - API endpoint to POST/PUT the data to
 * @param data - The data object to save
 * @param options - Configuration options
 */
export function useAutoSave(
  endpoint: string,
  data: Record<string, any> | null,
  options: {
    delayMs?: number;
    enabled?: boolean;
    method?: 'post' | 'put' | 'patch';
    onSaved?: () => void;
    onError?: (err: any) => void;
  } = {}
) {
  const { delayMs = 3000, enabled = true, method = 'put', onSaved, onError } = options;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevDataRef = useRef<string>('');
  const isMountedRef = useRef(true);
  const savingRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  const save = useCallback(async (payload: Record<string, any>) => {
    if (savingRef.current || !endpoint) return;
    savingRef.current = true;
    try {
      if (method === 'post') await api.post(endpoint, payload);
      else if (method === 'patch') await api.patch(endpoint, payload);
      else await api.put(endpoint, payload);
      if (isMountedRef.current) onSaved?.();
    } catch (err) {
      if (isMountedRef.current) onError?.(err);
    } finally {
      savingRef.current = false;
    }
  }, [endpoint, method, onSaved, onError]);

  useEffect(() => {
    if (!enabled || !data || !endpoint) return;

    const serialized = JSON.stringify(data);
    if (serialized === prevDataRef.current) return;

    // Skip initial mount (don't save on first render)
    if (!prevDataRef.current) {
      prevDataRef.current = serialized;
      return;
    }

    prevDataRef.current = serialized;

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => save(data), delayMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [data, enabled, delayMs, endpoint, save]);

  return { saving: savingRef.current };
}
