import { useEffect, useMemo } from 'react';
import api from '../services/api';
import { getHybridPollingInterval } from '../utils/hybridPolling';
import { useManagedWebSocket } from './useManagedWebSocket';
import { handleRecoverableError } from '../utils/handleRecoverableError';

interface UseHybridPollingOptions {
  enabled: boolean;
  errorScope: string;
  onTick: () => void | Promise<void>;
  slowIntervalMs: number;
  fastIntervalMs: number;
  thresholdAttempt?: number;
  runOnMount?: boolean;
  wsEnabled?: boolean;
  buildWsUrl?: () => string | Promise<string>;
  maxReconnectAttempts?: number;
  baseReconnectDelayMs?: number;
}

export const useHybridPolling = (options: UseHybridPollingOptions) => {
  const {
    enabled,
    errorScope,
    onTick,
    slowIntervalMs,
    fastIntervalMs,
    thresholdAttempt = 3,
    runOnMount = true,
    wsEnabled = true,
    buildWsUrl,
    maxReconnectAttempts = 4,
    baseReconnectDelayMs = 900,
  } = options;

  const defaultWsUrlBuilder = useMemo(
    () => () => {
      const baseUrl = String(api.defaults.baseURL || '').replace(/^http/, 'ws');
      return `${baseUrl}/ws/live-activity`;
    },
    []
  );

  const { reconnectAttempt, connected, lastError } = useManagedWebSocket({
    enabled: enabled && wsEnabled,
    buildUrl: buildWsUrl || defaultWsUrlBuilder,
    errorScope: `${errorScope}/ws-hybrid`,
    maxReconnectAttempts,
    baseReconnectDelayMs,
  });

  const intervalMs = useMemo(() => {
    if (!wsEnabled || !enabled) return slowIntervalMs;
    return getHybridPollingInterval({
      reconnectAttempt,
      thresholdAttempt,
      slowIntervalMs,
      fastIntervalMs,
    });
  }, [enabled, wsEnabled, reconnectAttempt, thresholdAttempt, slowIntervalMs, fastIntervalMs]);

  useEffect(() => {
    if (!enabled) return;

    const runTick = () => {
      Promise.resolve(onTick()).catch((error) => {
        handleRecoverableError(error, {
          scope: `${errorScope}/poll`,
          fallbackMessage: 'Hybrid polling cycle failed.',
        });
      });
    };

    if (runOnMount) runTick();
    const intervalId = setInterval(runTick, intervalMs);
    return () => clearInterval(intervalId);
  }, [enabled, runOnMount, onTick, intervalMs, errorScope]);

  return {
    reconnectAttempt,
    connected,
    lastError,
    intervalMs,
  };
};
