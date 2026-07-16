import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getBackendOriginConsistency, getRuntimeBackendUrl } from '../utils/runtimeBaseUrl';
import { useRealtime, useRealtimeEvent } from '../context/RealtimeContext';
import { useTheme } from '../context/ThemeContext';
import { handleAppRecoverableError } from '../utils/appRecoverableError';
import api from '../services/api';

const GPS_FETCH_TIMEOUT_MS = 9000;
const GPS_LKG_STORAGE_KEY = 'gps:last-known-good:v1';
const GPS_LKG_MAX_AGE_MS = 15 * 60 * 1000;
const GPS_PREFERRED_BASE_STORAGE_KEY = 'gps:preferred-base:v1';
const GPS_LABEL_BLOCKING_OVERRIDE_KEY = 'gps:enforce-label-blocking';
const GPS_NEXT_FETCH_AT_STORAGE_KEY = 'gps:next-fetch-at:v1';

const GPS_ACTIVE_ROUTE_PREFIXES = [
  '/',
  '/welcome',
  '/features',
  '/help',
  '/settings',
  '/notifications',
  '/admin',
];
const GPS_SHARED_MIN_FETCH_INTERVAL_MS = 120_000;
const GPS_SHARED_REALTIME_THROTTLE_MS = 60_000;
const GPS_MAX_POLL_INTERVAL_MS = 300_000;
const GPS_MIN_POLL_INTERVAL_MS = 45_000;

let gpsSharedInFlight: Promise<{ payload: any; endpoint: string; error: string }> | null = null;
let gpsSharedLastAttemptMs = 0;
let gpsSharedLastSuccessMs = 0;
let gpsSharedLastEndpoint = '';
let gpsSharedLastPayload: GlobalPlatformState | null = null;
let gpsRealtimeThrottleUntilMs = 0;
let gpsPollingLeaderToken: symbol | null = null;

const GPS_SHARED_EVENT = 'gps:shared-state-updated';

function broadcastGpsSharedStateUpdate(): void {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent(GPS_SHARED_EVENT));
  } catch {
    // no-op
  }
}

function getConfiguredEnvBase(): string {
  const raw = String(getBackendOriginConsistency().canonicalBase || '').trim().replace(/\/+$/, '');
  if (!raw) return '';
  if (raw.startsWith('http://localhost') || raw.startsWith('http://127.0.0.1')) return raw;
  return raw.replace(/^http:\/\//i, 'https://');
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`GPS timeout after ${timeoutMs}ms`)), timeoutMs);
    promise
      .then((value) => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch((err) => {
        clearTimeout(timer);
        reject(err);
      });
  });
}

function isValidGpsPayload(data: any): boolean {
  if (!data || typeof data !== 'object') return false;
  if (!data.state_id || String(data.state_id).trim() === '') return false;
  return Array.isArray(data.features) && Array.isArray(data.plans) && Array.isArray(data.faq);
}

export interface GPSFeature {
  feature_id: string;
  title: string;
  description?: string;
  status?: string;
  availability?: string;
  category?: string;
  icon?: string;
  route?: string;
  color?: string;
  enabled?: boolean;
  is_new?: boolean;
  sort_order?: number;
}

export interface GPSPlan {
  plan_id: string;
  name: string;
  description?: string;
  status?: string;
  currency?: string;
  monthly_price?: number;
  yearly_price?: number;
  features?: string[];
  limitations?: string[];
}

export interface GPSFaq {
  faq_id: string;
  lang?: string;
  question: string;
  answer: string;
  category?: string;
  active?: boolean;
}

export interface GlobalPlatformState {
  state_id: string;
  version: number;
  features: GPSFeature[];
  plans: GPSPlan[];
  faq: GPSFaq[];
  assistant_knowledge?: { documents?: Record<string, any>[]; last_refreshed_at?: string };
  ui_labels?: Record<string, string>;
  messaging?: Record<string, any>;
  layout_config?: Record<string, any>;
  meta?: { counts?: Record<string, number>; categories?: { id: string; label: string }[] };
  updated_at?: string;
}

const defaultState: GlobalPlatformState = {
  state_id: 'global-platform-state',
  version: 1,
  features: [],
  plans: [],
  faq: [],
  ui_labels: {},
  messaging: {},
  assistant_knowledge: { documents: [] },
};

function loadLastKnownGoodSnapshot(): GlobalPlatformState | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(GPS_LKG_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!isValidGpsPayload(parsed)) return null;

    const nowMs = Date.now();
    const updatedAtMs = parsed?.updated_at ? Date.parse(String(parsed.updated_at)) : NaN;
    const cachedAtMs = parsed?._client_cached_at ? Number(parsed._client_cached_at) : NaN;
    const ageMs = Number.isFinite(updatedAtMs)
      ? nowMs - updatedAtMs
      : Number.isFinite(cachedAtMs)
        ? nowMs - cachedAtMs
        : Number.POSITIVE_INFINITY;

    if (!Number.isFinite(ageMs) || ageMs > GPS_LKG_MAX_AGE_MS) {
      window.localStorage.removeItem(GPS_LKG_STORAGE_KEY);
      return null;
    }

    return { ...defaultState, ...parsed };
  } catch {
    return null;
  }
}

function saveLastKnownGoodSnapshot(payload: GlobalPlatformState): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      GPS_LKG_STORAGE_KEY,
      JSON.stringify({
        ...payload,
        _client_cached_at: Date.now(),
      })
    );
  } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useGlobalPlatformState.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

function loadPreferredBase(): string {
  if (typeof window === 'undefined') return '';
  try {
    return String(window.localStorage.getItem(GPS_PREFERRED_BASE_STORAGE_KEY) || '').trim().replace(/\/+$/, '');
  } catch {
    return '';
  }
}

function savePreferredBase(base: string): void {
  if (typeof window === 'undefined') return;
  try {
    const normalized = String(base || '').trim().replace(/\/+$/, '');
    if (!normalized) return;
    window.localStorage.setItem(GPS_PREFERRED_BASE_STORAGE_KEY, normalized);
  } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useGlobalPlatformState.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

function isLabelBlockingEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(GPS_LABEL_BLOCKING_OVERRIDE_KEY) === '1';
  } catch {
    return false;
  }
}

function readNextGpsFetchAt(): number {
  if (typeof window === 'undefined') return 0;
  try {
    const raw = Number(window.sessionStorage.getItem(GPS_NEXT_FETCH_AT_STORAGE_KEY) || 0);
    return Number.isFinite(raw) ? raw : 0;
  } catch {
    return 0;
  }
}

function writeNextGpsFetchAt(nextAt: number): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(GPS_NEXT_FETCH_AT_STORAGE_KEY, String(Math.max(0, Math.floor(nextAt))));
  } catch {
    // no-op
  }
}

function isGpsRouteActive(): boolean {
  if (typeof window === 'undefined') return true;
  const path = String(window.location?.pathname || '/');
  return GPS_ACTIVE_ROUTE_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
}

export function useGlobalPlatformState() {
  const { languageCode } = useTheme();
  const initialSnapshot = useMemo(() => loadLastKnownGoodSnapshot(), []);
  if (!gpsSharedLastPayload && initialSnapshot) {
    gpsSharedLastPayload = { ...defaultState, ...initialSnapshot };
  }
  const [state, setState] = useState<GlobalPlatformState>(
    initialSnapshot ? { ...defaultState, ...initialSnapshot } : defaultState,
  );
  // Permanent non-blocking policy: never hard-block route rendering on initial GPS fetch.
  // Pages can show inline diagnostics while content remains accessible.
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAttemptAt, setLastAttemptAt] = useState<string | null>(null);
  const [lastSuccessAt, setLastSuccessAt] = useState<string | null>(null);
  const [lastErrorAt, setLastErrorAt] = useState<string | null>(null);
  const [nextRetryAt, setNextRetryAt] = useState<number | null>(null);
  const [gpsEndpoint, setGpsEndpoint] = useState<string>('');
  const [gpsMode, setGpsMode] = useState<'live' | 'degraded' | 'bootstrap'>(initialSnapshot ? 'degraded' : 'bootstrap');

  const [retryDelayMs, setRetryDelayMs] = useState(3000);
  const { connected: realtimeConnected, connectionHealth } = useRealtime();
  const fetchInFlightRef = useRef(false);
  const instanceTokenRef = useRef<symbol>(Symbol('gps-instance'));
  const isLeaderRef = useRef(false);

  const syncFromSharedPayload = useCallback(() => {
    if (!gpsSharedLastPayload) return;
    setState(gpsSharedLastPayload);
    if (gpsSharedLastEndpoint) {
      setGpsEndpoint(gpsSharedLastEndpoint);
      setGpsMode('live');
    }
    if (gpsSharedLastSuccessMs > 0) {
      setLastSuccessAt(new Date(gpsSharedLastSuccessMs).toISOString());
      setError(null);
    }
  }, []);

  useEffect(() => {
    const instanceToken = instanceTokenRef.current;

    if (!gpsPollingLeaderToken) {
      gpsPollingLeaderToken = instanceToken;
      isLeaderRef.current = true;
    } else {
      isLeaderRef.current = gpsPollingLeaderToken === instanceToken;
    }

    const onSharedUpdate = () => {
      syncFromSharedPayload();
    };

    if (typeof window !== 'undefined') {
      window.addEventListener(GPS_SHARED_EVENT, onSharedUpdate as EventListener);
    }

    syncFromSharedPayload();

    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener(GPS_SHARED_EVENT, onSharedUpdate as EventListener);
      }

      if (gpsPollingLeaderToken === instanceToken) {
        gpsPollingLeaderToken = null;
        isLeaderRef.current = false;
      }
    };
  }, [syncFromSharedPayload]);

  const fetchState = useCallback(async () => {
    if (!isGpsRouteActive()) {
      const sharedSnapshot = gpsSharedLastPayload || loadLastKnownGoodSnapshot();
      if (sharedSnapshot) {
        setState(sharedSnapshot);
        gpsSharedLastPayload = sharedSnapshot;
        setGpsMode(gpsSharedLastSuccessMs > 0 ? 'live' : 'degraded');
        if (gpsSharedLastEndpoint) {
          setGpsEndpoint(gpsSharedLastEndpoint);
        }
        setLoading(false);
        return;
      }
      // Critical bootstrap safety: on first-load cold starts, inactive routes can still
      // render strict GPS-dependent surfaces (welcome/help/features).
      // If no shared snapshot exists yet, continue with one live fetch attempt instead
      // of returning an empty default payload that can trigger false blockers.
    }

    if (!isLeaderRef.current) {
      syncFromSharedPayload();
      setLoading(false);
      return;
    }

    if (fetchInFlightRef.current) return;

    const nowMsGlobal = Date.now();
    const nextAllowedFetchAt = readNextGpsFetchAt();
    if (nextAllowedFetchAt > nowMsGlobal) {
      const sharedSnapshot = gpsSharedLastPayload || loadLastKnownGoodSnapshot();
      if (sharedSnapshot) {
        setState(sharedSnapshot);
        gpsSharedLastPayload = sharedSnapshot;
        setGpsMode(gpsSharedLastSuccessMs > 0 ? 'live' : 'degraded');
      } else {
        setGpsMode('bootstrap');
      }
      setLoading(false);
      return;
    }

    fetchInFlightRef.current = true;
    setLoading(true);

    const nowIso = new Date().toISOString();
    setLastAttemptAt(nowIso);

    const activeLang = String(languageCode || 'en').trim().toLowerCase() || 'en';

    const consistency = getBackendOriginConsistency(
      undefined,
      typeof window !== 'undefined' ? window.location?.origin : '',
    );

    const runtimeBase = getRuntimeBackendUrl();
    const configuredBase = getConfiguredEnvBase();
    const preferredBase = loadPreferredBase();
    const sameOriginBase = typeof window !== 'undefined'
      ? String(window.location?.origin || '').trim().replace(/\/+$/, '')
      : '';
    const consistencyRuntimeBase = String(consistency.runtimeBase || '').trim().replace(/\/+$/, '');

    const baseCandidates = [preferredBase, sameOriginBase, consistencyRuntimeBase, runtimeBase, configuredBase]
      .filter((base) => typeof base === 'string' && String(base || '').trim().length > 0)
      .map((base) => String(base || '').trim().replace(/\/+$/, ''))
      .filter((base, idx, arr) => arr.indexOf(base) === idx);

    const fallbackEndpoint = sameOriginBase
      ? `${sameOriginBase}/api/gps/state?lang=${encodeURIComponent(activeLang)}`
      : `/api/gps/state?lang=${encodeURIComponent(activeLang)}`;

    let data: any = null;
    let endpointUsed = '';
    let lastError = consistency.ok ? '' : `Backend origin mismatch detected: ${consistency.issues.join(' ')}`;

    try {
      const nowMs = Date.now();
      if (gpsSharedLastAttemptMs > 0 && nowMs - gpsSharedLastAttemptMs < GPS_SHARED_MIN_FETCH_INTERVAL_MS) {
        const sharedSnapshot = gpsSharedLastPayload || loadLastKnownGoodSnapshot();
        if (sharedSnapshot) {
          setState(sharedSnapshot);
          gpsSharedLastPayload = sharedSnapshot;
        }
        setGpsEndpoint(gpsSharedLastEndpoint || fallbackEndpoint);
        setGpsMode(gpsSharedLastSuccessMs > 0 ? 'live' : (sharedSnapshot ? 'degraded' : 'bootstrap'));
        if (consistency.ok) setError(null);
        if (gpsSharedLastSuccessMs > 0) setLastSuccessAt(new Date(gpsSharedLastSuccessMs).toISOString());
        setRetryDelayMs(3000);
        setNextRetryAt(null);
        return;
      }

      if (!gpsSharedInFlight) {
        gpsSharedLastAttemptMs = nowMs;
        writeNextGpsFetchAt(Date.now() + GPS_SHARED_MIN_FETCH_INTERVAL_MS);
        gpsSharedInFlight = (async () => {
          let sharedPayload: any = null;
          let sharedEndpoint = '';
          let sharedError = consistency.ok
            ? ''
            : `Backend origin mismatch detected: ${consistency.issues.join(' ')}`;

          const fallbackPath = `/gps/state?lang=${encodeURIComponent(activeLang)}`;
          const fallbackEndpoint = `${sameOriginBase || ''}/api/gps/state?lang=${encodeURIComponent(activeLang)}`;

          try {
            const response = await withTimeout(
              api.get(fallbackPath, {
                silentLoading: true,
                skipDedupe: false,
              }),
              GPS_FETCH_TIMEOUT_MS,
            );
            const payload = response?.data;

            if (Number(response?.status || 0) === 204 || Boolean(payload?.suppressed)) {
              const snapshot = gpsSharedLastPayload || loadLastKnownGoodSnapshot();
              if (snapshot) {
                sharedPayload = snapshot;
                sharedEndpoint = fallbackEndpoint;
                sharedError = '';
                return {
                  payload: sharedPayload,
                  endpoint: sharedEndpoint,
                  error: sharedError,
                };
              }
            }

            if (!isValidGpsPayload(payload)) {
              throw new Error('GPS payload invalid from canonical endpoint');
            }
            sharedPayload = payload;
            sharedEndpoint = fallbackEndpoint;
            sharedError = '';
          } catch (err: any) {
            sharedError = String(err?.message || err || '').trim() || sharedError;

            // fallback only if canonical call fails and we have backup bases
            for (const base of baseCandidates) {
              const endpoint = `${base}/api/gps/state?lang=${encodeURIComponent(activeLang)}`;
              try {
                const res = await withTimeout(
                  fetch(endpoint, {
                    headers: { Accept: 'application/json' },
                  }),
                  GPS_FETCH_TIMEOUT_MS,
                );

                if (!res.ok) {
                  throw new Error(`GPS fetch failed (${res.status}) from ${endpoint}`);
                }

                const contentType = String(res.headers.get('content-type') || '').toLowerCase();
                if (!contentType.includes('application/json')) {
                  throw new Error(`GPS fetch returned non-JSON from ${endpoint}`);
                }

                const payload = await res.json();
                if (!isValidGpsPayload(payload)) {
                  throw new Error(`GPS payload invalid from ${endpoint}`);
                }

                sharedPayload = payload;
                sharedEndpoint = endpoint;
                sharedError = '';
                break;
              } catch (fallbackErr: any) {
                sharedError = String(fallbackErr?.message || fallbackErr || '').trim() || sharedError;
              }
            }
          }

          return {
            payload: sharedPayload,
            endpoint: sharedEndpoint,
            error: sharedError,
          };
        })().finally(() => {
          gpsSharedInFlight = null;
        });
      }

      const sharedResult = await gpsSharedInFlight;
      data = sharedResult.payload;
      endpointUsed = sharedResult.endpoint;
      lastError = sharedResult.error;

      if (!data) {
        throw new Error(lastError || 'Failed to load global platform state from all candidate endpoints');
      }

      const mergedState = { ...defaultState, ...data };
      const runtimeMode = String((mergedState as any)?._gps_runtime?.mode || '').trim().toLowerCase();
      const isRuntimeDegraded = runtimeMode === 'degraded' || runtimeMode === 'bootstrap';
      gpsSharedLastPayload = mergedState;
      gpsSharedLastEndpoint = endpointUsed || fallbackEndpoint;
      gpsSharedLastSuccessMs = Date.now();
      writeNextGpsFetchAt(Date.now() + 5 * 60 * 1000);
      broadcastGpsSharedStateUpdate();
      setState(mergedState);
      setGpsEndpoint(gpsSharedLastEndpoint);
      if (endpointUsed) {
        try {
          const endpointOrigin = new URL(endpointUsed).origin;
          savePreferredBase(endpointOrigin);
        } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useGlobalPlatformState.ts#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }
      if (!isRuntimeDegraded) {
        saveLastKnownGoodSnapshot(mergedState);
      }

      // NOTE: consistency/check is handled by backend-side GPS governance pipeline.
      // Avoid client-side per-fetch POST to prevent request amplification under degraded networks.

      if (isRuntimeDegraded) {
        const degradedReason = String((mergedState as any)?._gps_runtime?.reason || '').trim();
        setError(`GPS runtime degraded${degradedReason ? ` (${degradedReason})` : ''}. Running non-blocking fallback state.`);
      } else if (consistency.ok) {
        setError(null);
      } else {
        setError(`GPS loaded with degraded routing. ${lastError}`);
      }
      setGpsMode(isRuntimeDegraded ? 'degraded' : 'live');
      setRetryDelayMs(3000);
      setNextRetryAt(null);
      setLastErrorAt(null);
      setLastSuccessAt(new Date().toISOString());
    } catch (e: any) {
      const message = e?.message || 'Failed to load global platform state';
      const snapshot = loadLastKnownGoodSnapshot();

      if (snapshot) {
        setState(snapshot);
        gpsSharedLastPayload = snapshot;
        broadcastGpsSharedStateUpdate();
        setGpsMode('degraded');
        setError(`GPS live feed unavailable. Running in degraded mode using last-known-good snapshot. ${message}`);
      } else {
        setGpsMode('bootstrap');
        setError(`GPS unavailable and no snapshot found. Running bootstrap mode. ${message}`);
      }

      setGpsEndpoint(endpointUsed || gpsSharedLastEndpoint || fallbackEndpoint);
      setLastErrorAt(new Date().toISOString());
      writeNextGpsFetchAt(Date.now() + (/429/.test(message) ? 5 * 60 * 1000 : 2 * 60 * 1000));
      const nextDelay = /403|401|forbidden|unauthorized/i.test(message) ? 8000 : 10000;
      setRetryDelayMs(nextDelay);
      setNextRetryAt(Date.now() + nextDelay);
    } finally {
      fetchInFlightRef.current = false;
      setLoading(false);
    }
  }, [languageCode, syncFromSharedPayload]);

  useEffect(() => {
    if (!isLeaderRef.current) return;
    fetchState();

    const reconnectAttempt = Number(connectionHealth?.reconnectAttempt || 0);
    const autoReconnectPaused = Boolean(connectionHealth?.autoReconnectPaused);
    const shouldRunFastFallback = !realtimeConnected && (autoReconnectPaused || reconnectAttempt >= 2);
    const fallbackIntervalMs = shouldRunFastFallback
      ? Math.max(GPS_MIN_POLL_INTERVAL_MS, retryDelayMs)
      : Math.max(GPS_MAX_POLL_INTERVAL_MS, retryDelayMs);

    const id = setInterval(fetchState, fallbackIntervalMs);
    return () => clearInterval(id);
  }, [fetchState, retryDelayMs, realtimeConnected, connectionHealth?.reconnectAttempt, connectionHealth?.autoReconnectPaused]);

  const handleRealtimeRefresh = useCallback(() => {
    if (!isLeaderRef.current) return;
    const now = Date.now();
    if (now < gpsRealtimeThrottleUntilMs) return;
    gpsRealtimeThrottleUntilMs = now + GPS_SHARED_REALTIME_THROTTLE_MS;
    fetchState();
  }, [fetchState]);

  useRealtimeEvent('gps', handleRealtimeRefresh);
  useRealtimeEvent('features', handleRealtimeRefresh);
  useRealtimeEvent('config', handleRealtimeRefresh);

  const label = useCallback(
    (key: string, fallback: string) => {
      const value = state?.ui_labels?.[key];
      if (typeof value === 'string' && value.trim()) return value;
      return fallback;
    },
    [state?.ui_labels],
  );

  const strictLabel = useCallback(
    (key: string) => {
      const value = state?.ui_labels?.[key];
      if (typeof value === 'string' && value.trim()) return value;
      return null;
    },
    [state?.ui_labels],
  );

  const getMissingLabels = useCallback(
    (keys: string[]) => {
      // Permanent non-blocking default for real users/admins.
      // Strict label blocking can still be manually enabled for audits.
      if (!isLabelBlockingEnabled()) return [];
      if (loading || !lastSuccessAt || gpsMode !== 'live') return [];
      return keys.filter((k) => !strictLabel(k));
    },
    [strictLabel, loading, lastSuccessAt, gpsMode],
  );

  const counts = useMemo(() => {
    const activeFeatures = (state.features || []).filter((f) => f.enabled !== false);
    const activeFaq = (state.faq || []).filter((f) => f.active !== false);
    const activePlans = (state.plans || []).filter((p) => p.status !== 'deprecated');
    return {
      features: activeFeatures.length,
      faq: activeFaq.length,
      plans: activePlans.length,
    };
  }, [state.features, state.faq, state.plans]);

  const gpsStatus = loading ? 'loading' : gpsMode === 'live' ? 'healthy' : 'degraded';

  return {
    state,
    loading,
    error,
    refetch: fetchState,
    label,
    strictLabel,
    getMissingLabels,
    counts,
    gpsStatus,
    diagnostics: {
      lastAttemptAt,
      lastSuccessAt,
      lastErrorAt,
      nextRetryAt,
      gpsEndpoint,
      mode: gpsMode,
    },
  };
}
