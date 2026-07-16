/**
 * UIEM — UI Enforcement Middleware
 * 
 * Global render gatekeeper that intercepts ALL UI rendering.
 * Provides 4 validation layers: Design, Data, State, Performance.
 * Logs violations to backend and blocks non-compliant renders.
 */
import React, { createContext, useContext, useCallback, useRef, useMemo } from 'react';
import { Platform } from 'react-native';
import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const API = resolveRuntimeBaseUrl();

// ── Violation Types ──
export type UIEMLayer = 'design' | 'data' | 'state' | 'performance';
export type UIEMSeverity = 'critical' | 'high' | 'warn' | 'info';

export interface UIEMViolation {
  component: string;
  layer: UIEMLayer;
  error_type: string;
  message: string;
  severity: UIEMSeverity;
  pathname?: string;
  timestamp: number;
}

// ── Context ──
interface UIEMContextValue {
  logViolation: (violation: Omit<UIEMViolation, 'timestamp'>) => void;
  getViolationCount: () => number;
}

const UIEMContext = createContext<UIEMContextValue>({
  logViolation: () => {},
  getViolationCount: () => 0,
});

export function useUIEM() {
  return useContext(UIEMContext);
}

// ── Batched log sender ──
const LOG_BATCH_INTERVAL = 5000;
const MAX_BATCH_SIZE = 20;

export function UIEMProvider({ children }: { children: React.ReactNode }) {
  const batchRef = useRef<UIEMViolation[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countRef = useRef(0);
  // Dedup: skip identical violations within 30s
  const recentRef = useRef<Set<string>>(new Set());

  const flushBatch = useCallback(() => {
    if (batchRef.current.length === 0) return;
    const violations = batchRef.current.splice(0, MAX_BATCH_SIZE);
    if (Platform.OS === 'web') {
      try {
        const beacon = navigator?.sendBeacon;
        if (beacon) {
          beacon.call(navigator, `${API}/api/admin/uiem/log`, JSON.stringify({ violations }));
        } else {
          fetch(`${API}/api/admin/uiem/log`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ violations }),
            keepalive: true,
          }).catch(() => {});
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/uiem/UIEMContext.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  }, []);

  const logViolation = useCallback((v: Omit<UIEMViolation, 'timestamp'>) => {
    const key = `${v.component}:${v.layer}:${v.error_type}`;
    if (recentRef.current.has(key)) return;
    recentRef.current.add(key);
    setTimeout(() => recentRef.current.delete(key), 30000);

    const violation: UIEMViolation = { ...v, timestamp: Date.now() };
    batchRef.current.push(violation);
    countRef.current++;

    // Log to console in dev
    if (__DEV__) {
      console.warn(`[UIEM] ${v.layer.toUpperCase()} violation at ${v.component}: ${v.message}`);
    }

    // Schedule flush
    if (!timerRef.current) {
      timerRef.current = setTimeout(() => {
        flushBatch();
        timerRef.current = null;
      }, LOG_BATCH_INTERVAL);
    }

    // Immediate flush if batch is full
    if (batchRef.current.length >= MAX_BATCH_SIZE) {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      flushBatch();
    }
  }, [flushBatch]);

  const getViolationCount = useCallback(() => countRef.current, []);

  const value = useMemo(() => ({ logViolation, getViolationCount }), [logViolation, getViolationCount]);

  return (
    <UIEMContext.Provider value={value}>
      {children}
    </UIEMContext.Provider>
  );
}
