import { useEffect, useRef, useState, useCallback, type MutableRefObject } from 'react';
import { handleRecoverableError } from '../utils/handleRecoverableError';

interface UseManagedWebSocketOptions {
  enabled: boolean;
  buildUrl: () => string | Promise<string>;
  errorScope: string;
  maxReconnectAttempts?: number;
  baseReconnectDelayMs?: number;
  maxReconnectDelayMs?: number;
  pingIntervalMs?: number;
  pingMessage?: string;
  onOpen?: (socket: WebSocket) => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (event: Event) => void;
  onMessage?: (event: MessageEvent) => void;
  onReconnectAttempt?: (attempt: number) => void;
}

interface UseManagedWebSocketResult {
  socketRef: MutableRefObject<WebSocket | null>;
  connected: boolean;
  reconnectAttempt: number;
  lastError: string;
  connectNow: () => void;
  disconnectNow: () => void;
  sendJson: (payload: unknown) => boolean;
}

const DEFAULT_MAX_RECONNECT_ATTEMPTS = 3;
const DEFAULT_BASE_RECONNECT_DELAY_MS = 900;
const DEFAULT_MAX_RECONNECT_DELAY_MS = 6000;

export const useManagedWebSocket = (options: UseManagedWebSocketOptions): UseManagedWebSocketResult => {
  const {
    enabled,
    buildUrl,
    errorScope,
    maxReconnectAttempts = DEFAULT_MAX_RECONNECT_ATTEMPTS,
    baseReconnectDelayMs = DEFAULT_BASE_RECONNECT_DELAY_MS,
    maxReconnectDelayMs = DEFAULT_MAX_RECONNECT_DELAY_MS,
    pingIntervalMs = 25000,
    pingMessage = 'ping',
    onOpen,
    onClose,
    onError,
    onMessage,
    onReconnectAttempt,
  } = options;

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const manualCloseRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  const onErrorRef = useRef(onError);
  const onMessageRef = useRef(onMessage);
  const onReconnectAttemptRef = useRef(onReconnectAttempt);

  const [connected, setConnected] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [lastError, setLastError] = useState('');

  useEffect(() => {
    onOpenRef.current = onOpen;
  }, [onOpen]);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    onReconnectAttemptRef.current = onReconnectAttempt;
  }, [onReconnectAttempt]);

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  const disconnectNow = useCallback(() => {
    manualCloseRef.current = true;
    clearTimers();
    if (socketRef.current) {
      try {
        socketRef.current.close();
      } catch (error) {
        handleRecoverableError(error, {
          scope: `${errorScope}/close`,
          fallbackMessage: 'Socket close failed.',
        });
      }
    }
    socketRef.current = null;
    setConnected(false);
  }, [clearTimers, errorScope]);

  const connectNow = useCallback(() => {
    if (!enabled) return;
    if (socketRef.current?.readyState === WebSocket.OPEN || socketRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    const connectInternal = async () => {
      let wsUrl = '';
      try {
        wsUrl = String((await Promise.resolve(buildUrl())) || '').trim();
        if (!wsUrl) return;

        manualCloseRef.current = false;
        clearTimers();

        const socket = new WebSocket(wsUrl);
        socketRef.current = socket;

        socket.onopen = () => {
          reconnectAttemptRef.current = 0;
          setReconnectAttempt(0);
          setConnected(true);
          setLastError('');
          if (pingIntervalMs > 0) {
            pingTimerRef.current = setInterval(() => {
              if (socket.readyState === WebSocket.OPEN) {
                socket.send(pingMessage);
              }
            }, pingIntervalMs);
          }
          onOpenRef.current?.(socket);
        };

        socket.onmessage = (event) => {
          onMessageRef.current?.(event);
        };

        socket.onerror = (event) => {
          onErrorRef.current?.(event);
        };

        socket.onclose = (event) => {
          setConnected(false);
          clearTimers();
          onCloseRef.current?.(event);
          if (!enabled || manualCloseRef.current) return;

          const nextAttempt = reconnectAttemptRef.current + 1;
          reconnectAttemptRef.current = nextAttempt;
          setReconnectAttempt(nextAttempt);
          onReconnectAttemptRef.current?.(nextAttempt);

          if (nextAttempt > maxReconnectAttempts) {
            setLastError('Realtime connection unavailable. Please retry.');
            return;
          }

          const backoffMs = Math.min(maxReconnectDelayMs, baseReconnectDelayMs * (2 ** (nextAttempt - 1)));
          reconnectTimerRef.current = setTimeout(() => {
            reconnectTimerRef.current = null;
            connectNow();
          }, backoffMs);
        };
      } catch (error) {
        const message = handleRecoverableError(error, {
          scope: `${errorScope}/connect`,
          fallbackMessage: 'Realtime connection failed.',
        });
        setLastError(message);
      }
    };

    void connectInternal();
  }, [
    enabled,
    buildUrl,
    clearTimers,
    pingIntervalMs,
    pingMessage,
    maxReconnectAttempts,
    baseReconnectDelayMs,
    maxReconnectDelayMs,
    errorScope,
  ]);

  useEffect(() => {
    if (!enabled) {
      disconnectNow();
      return;
    }
    connectNow();
    return () => {
      disconnectNow();
    };
  }, [enabled, connectNow, disconnectNow]);

  const sendJson = useCallback((payload: unknown) => {
    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return false;
    socketRef.current.send(JSON.stringify(payload));
    return true;
  }, []);

  return {
    socketRef,
    connected,
    reconnectAttempt,
    lastError,
    connectNow,
    disconnectNow,
    sendJson,
  };
};
