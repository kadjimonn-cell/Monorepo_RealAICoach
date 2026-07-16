/**
 * RealtimeProvider — Single shared WebSocket connection for the entire app.
 *
 * All real-time features (config, features, notifications, data changes)
 * go through this one connection. Components subscribe via useRealtimeEvent().
 */
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { Platform, AppState } from 'react-native';
import { notificationEvents } from '../utils/notificationEvents';
import { getRuntimeBackendUrl } from '../utils/runtimeBaseUrl';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

type EventHandler = (data: any) => void;

interface RealtimeContextType {
  connected: boolean;
  subscribe: (entity: string, handler: EventHandler) => () => void;
  subscribeType: (type: string, handler: EventHandler) => () => void;
  reconnectNow: () => void;
  connectionHealth: {
    reconnectAttempt: number;
    currentBackoffMs: number;
    consecutiveFailures: number;
    lastEventAt: string | null;
    autoReconnectPaused: boolean;
    maxAutoReconnectAttempts: number;
  };
}

const RealtimeContext = createContext<RealtimeContextType>({
  connected: false,
  subscribe: () => () => {},
  subscribeType: () => () => {},
  reconnectNow: () => {},
  connectionHealth: {
    reconnectAttempt: 0,
    currentBackoffMs: 0,
    consecutiveFailures: 0,
    lastEventAt: null,
    autoReconnectPaused: false,
    maxAutoReconnectAttempts: 10,
  },
});

const TELEMETRY_FLUSH_INTERVAL_MS = 30000;
const MIN_RECONNECT_BACKOFF_MS = 5000;
const MAX_RECONNECT_BACKOFF_MS = 30000;
const MAX_AUTO_RECONNECT_ATTEMPTS = 10;

const getApiBase = () => {
  const resolved = getRuntimeBackendUrl() || '';
  const normalized = String(resolved).replace(/\/+$/, '');
  if (/^http:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?::\d+)?/i.test(normalized)) {
    return normalized;
  }
  return normalized.replace(/^http:\/\//i, 'https://');
};

const shouldSkipSameOriginLocalWebSocket = (apiBase: string) => {
  if (typeof window === 'undefined') return false;
  try {
    const apiUrl = new URL(apiBase);
    const runtimeUrl = new URL(window.location.origin);
    const localHost = apiUrl.hostname === 'localhost' || apiUrl.hostname === '127.0.0.1';
    return localHost && apiUrl.origin === runtimeUrl.origin && apiUrl.protocol === 'http:';
  } catch {
    return false;
  }
};

const getTelemetryEndpoint = () => {
  const apiBase = getApiBase();
  return apiBase ? `${apiBase}/api/platform-shell-health/realtime-ingest` : '/api/platform-shell-health/realtime-ingest';
};

const resolveClientId = () => {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return 'native-client';
  try {
    const existing = window.localStorage.getItem('realtime_client_id');
    if (existing) return existing;
    const generated = `rt_${Math.random().toString(36).slice(2, 10)}_${Date.now().toString(36)}`;
    window.localStorage.setItem('realtime_client_id', generated);
    return generated;
  } catch {
    return `rt_fallback_${Date.now().toString(36)}`;
  }
};

const computeBackoffMs = (attempt: number) => {
  const boundedAttempt = Math.max(1, Math.min(attempt, 10));
  const base = Math.min(MAX_RECONNECT_BACKOFF_MS, MIN_RECONNECT_BACKOFF_MS * (2 ** (boundedAttempt - 1)));
  const jitter = 0.85 + (Math.random() * 0.3);
  return Math.max(MIN_RECONNECT_BACKOFF_MS, Math.min(MAX_RECONNECT_BACKOFF_MS, Math.round(base * jitter)));
};

export function RealtimeProvider({ userId, children }: { userId: string | null; children: React.ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [autoReconnectPaused, setAutoReconnectPaused] = useState(false);
  const [connectionHealth, setConnectionHealth] = useState({
    reconnectAttempt: 0,
    currentBackoffMs: 0,
    consecutiveFailures: 0,
    lastEventAt: null as string | null,
    autoReconnectPaused: false,
    maxAutoReconnectAttempts: MAX_AUTO_RECONNECT_ATTEMPTS,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const entitySubs = useRef<Map<string, Set<EventHandler>>>(new Map());
  const typeSubs = useRef<Map<string, Set<EventHandler>>>(new Map());
  const reconnectTimer = useRef<any>(null);
  const mountedRef = useRef(true);
  const reconnectAttemptRef = useRef(0);
  const autoReconnectPausedRef = useRef(false);
  const consecutiveFailuresRef = useRef(0);
  const currentBackoffMsRef = useRef(0);
  const lastEventAtRef = useRef<string | null>(null);
  const clientIdRef = useRef<string>(resolveClientId());
  const telemetryQueueRef = useRef<any[]>([]);
  const telemetryFlushTimerRef = useRef<any>(null);
  const lastOpenAtRef = useRef<string | null>(null);

  const syncConnectionHealthState = useCallback(() => {
    const payload = {
      reconnectAttempt: reconnectAttemptRef.current,
      currentBackoffMs: currentBackoffMsRef.current,
      consecutiveFailures: consecutiveFailuresRef.current,
      lastEventAt: lastEventAtRef.current,
      autoReconnectPaused: autoReconnectPausedRef.current,
      maxAutoReconnectAttempts: MAX_AUTO_RECONNECT_ATTEMPTS,
    };
    setConnectionHealth(payload);
  }, []);

  const flushTelemetryQueue = useCallback(async () => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    if (!telemetryQueueRef.current.length) return;

    const batched = telemetryQueueRef.current.splice(0, 20);
    const telemetryEndpoint = getTelemetryEndpoint();
    try {
      await fetch(telemetryEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: clientIdRef.current,
          user_id: userId,
          pathname: window.location?.pathname || '',
          captured_at: new Date().toISOString(),
          events: batched,
        }),
        keepalive: true,
      });
    } catch (error) { handleAppRecoverableError({ scope: 'src/context/RealtimeContext.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [userId]);

  const trackRealtimeEvent = useCallback((eventType: string, metadata: Record<string, any> = {}) => {
    const timestamp = new Date().toISOString();
    lastEventAtRef.current = timestamp;
    telemetryQueueRef.current.push({
      event_type: eventType,
      timestamp,
      connected: wsRef.current?.readyState === WebSocket.OPEN,
      reconnect_attempt: reconnectAttemptRef.current,
      backoff_ms: currentBackoffMsRef.current,
      consecutive_failures: consecutiveFailuresRef.current,
      metadata,
    });
    if (telemetryQueueRef.current.length >= 6) {
      void flushTelemetryQueue();
    }
    syncConnectionHealthState();
  }, [flushTelemetryQueue, syncConnectionHealthState]);

  const connect = useCallback(async () => {
    if (!userId || Platform.OS !== 'web') return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    if (autoReconnectPausedRef.current) {
      trackRealtimeEvent('connect_skipped', { reason: 'auto_reconnect_paused' });
      syncConnectionHealthState();
      return;
    }

    try {
      const ticketResp = await api.post('/auth/ws-ticket');
      const wsTicket = String(ticketResp?.data?.ticket || '').trim();
      if (!wsTicket) {
        trackRealtimeEvent('connect_skipped', { reason: 'ws_ticket_missing' });
        return;
      }

      const apiBase = getApiBase();
      if (!apiBase) {
        trackRealtimeEvent('connect_skipped', { reason: 'missing_backend_base_url' });
        return;
      }
      if (shouldSkipSameOriginLocalWebSocket(apiBase)) {
        trackRealtimeEvent('connect_skipped', { reason: 'same_origin_local_proxy_no_websocket_upgrade' });
        syncConnectionHealthState();
        return;
      }
      const wsUrl = apiBase.replace('https://', 'wss://').replace('http://', 'ws://');
      const ws = new WebSocket(`${wsUrl}/api/ws/notifications/${userId}?ticket=${encodeURIComponent(wsTicket)}`);
      wsRef.current = ws;
      trackRealtimeEvent('connect_attempt', {
        endpoint: `${wsUrl}/api/ws/notifications/${userId}`,
      });

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        consecutiveFailuresRef.current = 0;
        currentBackoffMsRef.current = 0;
        autoReconnectPausedRef.current = false;
        setAutoReconnectPaused(false);
        lastOpenAtRef.current = new Date().toISOString();
        if (mountedRef.current) setConnected(true);
        if (reconnectTimer.current) { clearTimeout(reconnectTimer.current); reconnectTimer.current = null; }
        trackRealtimeEvent('connected', {
          opened_at: lastOpenAtRef.current,
        });
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === 'notification') {
            const notif = msg.notification || {};
            notificationEvents.emit('toast', {
              title: notif.title || 'New Notification',
              message: notif.message || '',
              type: notif.type,
            });
            notificationEvents.emit('unread_update', {
              unread_count: msg.unread_count,
              notification: notif,
            });
          }

          // Dispatch to type subscribers
          const typeHandlers = typeSubs.current.get(msg.type);
          if (typeHandlers) typeHandlers.forEach(h => h(msg));

          // Dispatch data_change to entity subscribers
          if (msg.type === 'data_change' && msg.entity) {
            const entityHandlers = entitySubs.current.get(msg.entity);
            if (entityHandlers) entityHandlers.forEach(h => h(msg));

            // Also notify wildcard '*' subscribers (they get all data changes)
            const wildcardHandlers = entitySubs.current.get('*');
            if (wildcardHandlers) wildcardHandlers.forEach(h => h(msg));
          }
        } catch (error) { handleAppRecoverableError({ scope: 'src/context/RealtimeContext.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      };

      ws.onclose = () => {
        const closeCode = ws?.code || 0;
        const closeReason = ws?.reason || 'unknown';
        wsRef.current = null;
        if (mountedRef.current) {
          setConnected(false);
          reconnectAttemptRef.current += 1;
          consecutiveFailuresRef.current += 1;

          if (reconnectAttemptRef.current >= MAX_AUTO_RECONNECT_ATTEMPTS) {
            currentBackoffMsRef.current = 0;
            autoReconnectPausedRef.current = true;
            setAutoReconnectPaused(true);
            trackRealtimeEvent('auto_reconnect_paused', {
              close_code: closeCode,
              close_reason: closeReason,
              reconnect_attempts: reconnectAttemptRef.current,
              max_auto_reconnect_attempts: MAX_AUTO_RECONNECT_ATTEMPTS,
            });
            syncConnectionHealthState();
            return;
          }

          const nextBackoff = computeBackoffMs(reconnectAttemptRef.current);
          currentBackoffMsRef.current = nextBackoff;
          trackRealtimeEvent('disconnected', {
            close_code: closeCode,
            close_reason: closeReason,
            next_backoff_ms: nextBackoff,
          });
          reconnectTimer.current = setTimeout(() => {
            reconnectTimer.current = null;
            connect();
          }, nextBackoff);
        }
      };

      ws.onerror = () => {
        trackRealtimeEvent('error', { message: 'websocket_error_event' });
        ws.close();
      };
    } catch (error) { handleAppRecoverableError({ scope: 'src/context/RealtimeContext.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [userId, trackRealtimeEvent, syncConnectionHealthState]);

  const reconnectNow = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    autoReconnectPausedRef.current = false;
    setAutoReconnectPaused(false);
    reconnectAttemptRef.current = 0;
    currentBackoffMsRef.current = 0;
    consecutiveFailuresRef.current = 0;
    trackRealtimeEvent('manual_reconnect_requested', {
      source: 'manual_reconnect_button',
    });
    syncConnectionHealthState();
    void connect();
  }, [connect, syncConnectionHealthState, trackRealtimeEvent]);

  useEffect(() => {
    mountedRef.current = true;
    if (Platform.OS === 'web') {
      telemetryFlushTimerRef.current = setInterval(() => {
        void flushTelemetryQueue();
      }, TELEMETRY_FLUSH_INTERVAL_MS);
    }
    connect();

    // Reconnect on app focus
    const handleFocus = () => {
      if (!autoReconnectPausedRef.current && wsRef.current?.readyState !== WebSocket.OPEN) connect();
    };

    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') handleFocus();
    });

    const flushOnBackground = () => {
      if (document.visibilityState === 'hidden') {
        void flushTelemetryQueue();
      }
    };

    if (Platform.OS === 'web') {
      window.addEventListener('focus', handleFocus);
      document.addEventListener('visibilitychange', flushOnBackground);
    }

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (telemetryFlushTimerRef.current) clearInterval(telemetryFlushTimerRef.current);
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
      if (Platform.OS === 'web') {
        window.removeEventListener('focus', handleFocus);
        document.removeEventListener('visibilitychange', flushOnBackground);
      }
      sub.remove();
      void flushTelemetryQueue();
    };
  }, [connect, flushTelemetryQueue]);

  // Subscribe to data_change events for a specific entity
  const subscribe = useCallback((entity: string, handler: EventHandler) => {
    if (!entitySubs.current.has(entity)) entitySubs.current.set(entity, new Set());
    entitySubs.current.get(entity)!.add(handler);
    return () => { entitySubs.current.get(entity)?.delete(handler); };
  }, []);

  // Subscribe to any WebSocket message type
  const subscribeType = useCallback((type: string, handler: EventHandler) => {
    if (!typeSubs.current.has(type)) typeSubs.current.set(type, new Set());
    typeSubs.current.get(type)!.add(handler);
    return () => { typeSubs.current.get(type)?.delete(handler); };
  }, []);

  return (
    <RealtimeContext.Provider value={{ connected, subscribe, subscribeType, reconnectNow, connectionHealth: { ...connectionHealth, autoReconnectPaused } }}>
      {children}
    </RealtimeContext.Provider>
  );
}

export const useRealtime = () => useContext(RealtimeContext);

/**
 * useRealtimeEvent — Subscribe to data_change events for a specific entity.
 * Calls the handler whenever the entity changes on the server.
 */
export function useRealtimeEvent(entity: string, handler: EventHandler) {
  const { subscribe } = useRealtime();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    return subscribe(entity, (data) => handlerRef.current(data));
  }, [entity, subscribe]);
}
