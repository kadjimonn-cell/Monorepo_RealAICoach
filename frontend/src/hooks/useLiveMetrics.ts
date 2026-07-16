import { useCallback, useEffect, useState } from 'react';
import { Platform } from 'react-native';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

export interface LiveVanityMetrics {
  active_users: number;
  ai_sessions_today: number;
  global_coaches: number;
  performance_boost: number;
  users_online: number;
  system_health: number;
}

export interface GrowthIntelligencePoint {
  label: string;
  period_start: string;
  growth_score: number;
  benchmark_score: number;
  active_users: number;
  ai_sessions: number;
  completion_rate: number;
  conversion_velocity: number;
  milestone?: {
    title: string;
    impact_label: string;
  } | null;
}

export interface GrowthIntelligenceRange {
  label: string;
  comparison_label: string;
  points: GrowthIntelligencePoint[];
  strongest_period_label: string;
  weakest_period_label: string;
  momentum_delta: number;
  forecast_teaser: string;
}

export interface GrowthIntelligencePayload {
  headline_metric: {
    label: string;
    value: number;
    unit: string;
    delta_vs_baseline: number;
  };
  benchmark_value: number;
  confidence: {
    score: number;
    label: string;
  };
  narrative_summary: string;
  premium_teaser: string;
  proof_points: {
    label: string;
    value: number;
    tone: string;
  }[];
  ranges: Record<string, GrowthIntelligenceRange>;
  default_range: '30d' | '90d' | '12m';
  current_momentum_label: string;
}

export interface LiveMetricsPayload {
  vanity: LiveVanityMetrics;
  kpis?: Record<string, any>;
  ai_load?: Record<string, number>;
  recent_activity?: { type: string; time: string }[];
  timestamp?: string;
  mode?: string;
  growth_intelligence?: GrowthIntelligencePayload;
}

const SNAPSHOT_KEY = 'live-metrics-stream-snapshot-v1';
const DEFAULT_POLL_INTERVAL_MS = 3000;

// ── SSE transport tuning ──
// The backend emits a `retry: 5000` hint with each SSE event, so the browser
// auto-reconnects roughly every 5s without us holding a long-lived socket.
// If we see this many consecutive connection errors on the EventSource, we
// assume SSE is broken for this session (proxy / firewall / older browser)
// and fall back to polling permanently.
const SSE_MAX_CONSECUTIVE_ERRORS = 3;

type SubscriberState = {
  data: LiveMetricsPayload | null;
  loading: boolean;
  error: string | null;
};

type Subscriber = (state: SubscriberState) => void;

let sharedData: LiveMetricsPayload | null = null;
let sharedLoading = true;
let sharedError: string | null = null;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let visibilityBound = false;
let inFlight = false;
let activePollIntervalMs = DEFAULT_POLL_INTERVAL_MS;
const subscribers = new Set<Subscriber>();
// ── Per-subscriber requested intervals ─────────────────────────────────────
// When multiple components call useLiveMetrics() with different pollInterval
// values (e.g. WelcomeHero(3000) + WelcomeLiveTickertape(4000)), the global
// interval was getting thrashed by whichever subscriber mounted last. We
// now track every subscriber's requested interval and poll at the SHORTEST
// — so the tightest consumer gets its cadence + the slower consumers still
// receive updates (just faster than they asked, which is always fine).
const requestedIntervals = new Map<Subscriber, number>();
function recomputeActivePollInterval() {
  if (requestedIntervals.size === 0) {
    activePollIntervalMs = DEFAULT_POLL_INTERVAL_MS;
    return;
  }
  let minMs = Number.POSITIVE_INFINITY;
  for (const ms of requestedIntervals.values()) {
    if (ms < minMs) minMs = ms;
  }
  activePollIntervalMs = Math.max(2000, Math.min(minMs, 30000));
}

// SSE state
let eventSource: EventSource | null = null;
let sseConsecutiveErrors = 0;
let sseDisabled = false; // becomes true after SSE_MAX_CONSECUTIVE_ERRORS failures
let transportMode: 'sse' | 'poll' | 'idle' = 'idle';

function sseSupported(): boolean {
  return (
    Platform.OS === 'web' &&
    typeof window !== 'undefined' &&
    typeof (window as any).EventSource === 'function' &&
    !sseDisabled
  );
}

function notifySubscribers() {
  const snapshot = { data: sharedData, loading: sharedLoading, error: sharedError };
  subscribers.forEach((cb) => cb(snapshot));
}

function teardownTransports() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  if (eventSource) {
    try { eventSource.close(); } catch { /* ignore */ }
    eventSource = null;
  }
  transportMode = 'idle';
}

function stopTransportsIfIdle() {
  if (subscribers.size > 0) return;
  teardownTransports();
}

function scheduleNextPoll() {
  if (pollTimer) clearTimeout(pollTimer);
  if (subscribers.size === 0) {
    pollTimer = null;
    return;
  }
  pollTimer = setTimeout(async () => {
    await fetchSharedMetrics(false);
    scheduleNextPoll();
  }, activePollIntervalMs);
}

function ensureVisibilityListener() {
  if (visibilityBound || Platform.OS !== 'web' || typeof document === 'undefined') return;
  visibilityBound = true;
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      // Re-sync both transports on tab refocus
      if (transportMode === 'poll') {
        fetchSharedMetrics(true).finally(() => scheduleNextPoll());
      } else if (transportMode === 'sse' && (!eventSource || eventSource.readyState === 2 /* CLOSED */)) {
        // EventSource auto-reconnects, but if it's been closed while hidden,
        // re-open it so we get fresh data immediately.
        openEventSource();
      }
    }
  });
}

function setBackoffFromError(error: any) {
  const status = Number(error?.response?.status || 0);
  if (status === 429) {
    activePollIntervalMs = Math.min(30000, Math.max(activePollIntervalMs * 2, 10000));
    return;
  }
  activePollIntervalMs = DEFAULT_POLL_INTERVAL_MS;
}

async function fetchSharedMetrics(force = false) {
  if (inFlight) return;
  if (!force && Platform.OS === 'web' && typeof document !== 'undefined' && document.visibilityState !== 'visible') return;

  inFlight = true;
  try {
    const res = await api.get('/system/live-metrics', {
      params: { mode: 'stream' },
      silentLoading: true,
    });
    const normalized = normalizePayload(res.data || {});
    sharedData = normalized;
    sharedError = null;
    sharedLoading = false;
    activePollIntervalMs = DEFAULT_POLL_INTERVAL_MS;
    writeSnapshot(normalized);
  } catch (e: any) {
    sharedError = e?.message || 'Failed to fetch live metrics';
    sharedLoading = false;
    setBackoffFromError(e);
  } finally {
    inFlight = false;
    notifySubscribers();
  }
}

// ── EventSource (SSE) transport ──
// Opens a persistent connection to /api/system/live-metrics?mode=sse. The
// server emits one `snapshot` event per connection then closes, and we rely
// on the browser's built-in auto-reconnect (driven by the `retry: 5000` hint
// the server emits) to tick updates. Zero polling timer while SSE is active.
function openEventSource() {
  if (!sseSupported()) return;
  if (eventSource) {
    try { eventSource.close(); } catch { /* ignore */ }
    eventSource = null;
  }

  const apiBase = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
  const url = `${apiBase}/api/system/live-metrics?mode=sse`;

  try {
    eventSource = new EventSource(url, { withCredentials: false });
  } catch {
    // Construction can synchronously throw on pathological URLs; disable SSE
    // and fall back to polling so the hook still delivers data.
    sseDisabled = true;
    return false;
  }

  const handleSnapshot = (ev: MessageEvent) => {
    try {
      const raw = JSON.parse(ev.data);
      const normalized = normalizePayload(raw || {});
      sharedData = normalized;
      sharedError = null;
      sharedLoading = false;
      sseConsecutiveErrors = 0;
      writeSnapshot(normalized);
      notifySubscribers();
    } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useLiveMetrics.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  eventSource.addEventListener('snapshot', handleSnapshot as EventListener);
  // Some clients deliver the payload as the default `message` event instead
  // of the named `snapshot` event; handle both.
  eventSource.onmessage = handleSnapshot as any;

  eventSource.onerror = () => {
    sseConsecutiveErrors += 1;
    if (sseConsecutiveErrors >= SSE_MAX_CONSECUTIVE_ERRORS) {
      // SSE is wedged for this session — close it, flip the permanent
      // disable flag, and fall back to polling.
      try { eventSource?.close(); } catch { /* ignore */ }
      eventSource = null;
      sseDisabled = true;
      transportMode = 'poll';
      fetchSharedMetrics(true).finally(() => scheduleNextPoll());
    }
    // Otherwise: the browser will auto-reconnect using the server's
    // `retry:` hint — nothing for us to do.
  };

  transportMode = 'sse';
  return true;
}

function startTransport() {
  if (subscribers.size === 0) return;
  if (transportMode === 'sse' || transportMode === 'poll') return; // already up

  if (sseSupported()) {
    const opened = openEventSource();
    if (opened !== false) {
      // Kick off one immediate fetch so consumers aren't staring at
      // `loading:true` for the first ~5s until the first SSE event.
      void fetchSharedMetrics(true);
      return;
    }
  }

  transportMode = 'poll';
  fetchSharedMetrics(true).finally(() => scheduleNextPoll());
}

function readSnapshot(): LiveMetricsPayload | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(SNAPSHOT_KEY) || window.localStorage.getItem(SNAPSHOT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeSnapshot(payload: LiveMetricsPayload) {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  try {
    const serialized = JSON.stringify(payload);
    window.sessionStorage.setItem(SNAPSHOT_KEY, serialized);
    window.localStorage.setItem(SNAPSHOT_KEY, serialized);
  } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useLiveMetrics.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

function toNumber(value: any, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizePayload(raw: any): LiveMetricsPayload {
  const vanity = raw?.vanity || {};
  const kpis = raw?.kpis || {};
  const realtime = raw?.kpis_realtime || {};

  return {
    ...raw,
    vanity: {
      active_users: toNumber(realtime.active_users ?? kpis.active_users ?? vanity.active_users),
      ai_sessions_today: toNumber(realtime.ai_sessions_today ?? kpis.ai_sessions_today ?? vanity.ai_sessions_today),
      global_coaches: toNumber(realtime.global_coaches ?? kpis.global_coaches ?? vanity.global_coaches),
      performance_boost: toNumber(realtime.performance_boost ?? kpis.performance_boost ?? vanity.performance_boost),
      users_online: toNumber(realtime.users_online ?? kpis.users_online ?? vanity.users_online),
      system_health: toNumber(realtime.system_health ?? kpis.system_health ?? vanity.system_health),
    },
  };
}

export function useLiveMetrics(pollInterval = DEFAULT_POLL_INTERVAL_MS) {
  const initialSnapshot = sharedData || readSnapshot();
  if (!sharedData && initialSnapshot) {
    sharedData = initialSnapshot;
    sharedLoading = false;
  }

  const [state, setState] = useState<SubscriberState>({
    data: sharedData,
    loading: sharedLoading,
    error: sharedError,
  });

  const fetchMetrics = useCallback(async () => {
    // refetch() always goes through the JSON endpoint for an immediate
    // snapshot regardless of transport — gives callers a way to force a
    // read-through even while SSE is ticking.
    await fetchSharedMetrics(true);
    if (transportMode === 'poll') scheduleNextPoll();
  }, []);

  useEffect(() => {
    ensureVisibilityListener();

    const subscriber: Subscriber = (next) => setState(next);
    subscribers.add(subscriber);
    requestedIntervals.set(subscriber, pollInterval);
    recomputeActivePollInterval();
    setState({ data: sharedData, loading: sharedLoading, error: sharedError });

    startTransport();

    return () => {
      subscribers.delete(subscriber);
      requestedIntervals.delete(subscriber);
      recomputeActivePollInterval();
      stopTransportsIfIdle();
    };
  }, [fetchMetrics, pollInterval]);

  return {
    data: state.data,
    vanity: state.data?.vanity || null,
    loading: state.loading,
    error: state.error,
    refetch: fetchMetrics,
    /** Transport currently in use: `'sse' | 'poll' | 'idle'`. Exposed for
     * diagnostics UIs (e.g. the admin "LIVE" pill in the nav bar). */
    transport: transportMode,
  };
}
