import { useEffect, useRef, useState, useCallback } from 'react';
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api, { setCachedToken } from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const WARNING_SECONDS = 5 * 60;
const CRITICAL_MODAL_SECONDS = 60;
const SYNC_TOKEN_INTERVAL_MS = 15000;

const decodeJwtExpMs = (token: string): number | null => {
  try {
    const payload = token.split('.')[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=');
    const parsed = JSON.parse(atob(padded));
    return parsed?.exp ? Number(parsed.exp) * 1000 : null;
  } catch {
    return null;
  }
};

const getStoredValue = async (key: string): Promise<string | null> => {
  const primary = await AsyncStorage.getItem(key).catch(() => null);
  if (primary) return primary;

  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  return null;
};

const setStoredValue = async (key: string, value: string) => {
  await AsyncStorage.setItem(key, value).catch(() => {});
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useSessionRefresh.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }
};

interface UseSessionRefreshState {
  secondsRemaining: number | null;
  isWarningVisible: boolean;
  isCriticalVisible: boolean;
  refreshing: boolean;
  refreshError: string | null;
  refreshSession: () => Promise<boolean>;
  dismissWarning: () => void;
  clearRefreshError: () => void;
}

export function useSessionRefresh(userId: string | null, onSessionExpired?: () => Promise<void> | void): UseSessionRefreshState {
  const [secondsRemaining, setSecondsRemaining] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [warningDismissed, setWarningDismissed] = useState(false);

  const expiryMsRef = useRef<number | null>(null);
  const tickRef = useRef<any>(null);
  const syncRef = useRef<any>(null);
  const expiredRef = useRef(false);

  const syncFromToken = useCallback(async () => {
    if (!userId) {
      expiryMsRef.current = null;
      setSecondsRemaining(null);
      return;
    }

    const token = await getStoredValue('session_token');
    if (!token) {
      expiryMsRef.current = null;
      setSecondsRemaining(null);
      return;
    }

    const expiryMs = decodeJwtExpMs(token);
    if (!expiryMs) {
      expiryMsRef.current = null;
      setSecondsRemaining(null);
      return;
    }

    expiryMsRef.current = expiryMs;
    const nextSeconds = Math.max(Math.ceil((expiryMs - Date.now()) / 1000), 0);
    setSecondsRemaining(nextSeconds);
    if (nextSeconds > WARNING_SECONDS) {
      setWarningDismissed(false);
      setRefreshError(null);
    }
  }, [userId]);

  const handleExpired = useCallback(async () => {
    if (expiredRef.current) return;
    expiredRef.current = true;
    setSecondsRemaining(0);
    if (onSessionExpired) {
      await onSessionExpired();
    }
  }, [onSessionExpired]);

  useEffect(() => {
    if (!userId) {
      expiryMsRef.current = null;
      expiredRef.current = false;
      setSecondsRemaining(null);
      setRefreshError(null);
      setWarningDismissed(false);
      return;
    }

    expiredRef.current = false;
    syncFromToken();

    tickRef.current = setInterval(() => {
      const expiry = expiryMsRef.current;
      if (!expiry) return;
      const nextSeconds = Math.max(Math.ceil((expiry - Date.now()) / 1000), 0);
      setSecondsRemaining(nextSeconds);
      if (nextSeconds <= 0) {
        handleExpired();
      }
    }, 1000);

    syncRef.current = setInterval(syncFromToken, SYNC_TOKEN_INTERVAL_MS);

    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const handleFocus = () => {
        syncFromToken();
      };
      const handleStorage = (event: StorageEvent) => {
        if (event.key === 'session_token') {
          syncFromToken();
        }
      };
      window.addEventListener('focus', handleFocus);
      window.addEventListener('storage', handleStorage);

      return () => {
        if (tickRef.current) clearInterval(tickRef.current);
        if (syncRef.current) clearInterval(syncRef.current);
        window.removeEventListener('focus', handleFocus);
        window.removeEventListener('storage', handleStorage);
      };
    }

    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
      if (syncRef.current) clearInterval(syncRef.current);
    };
  }, [userId, syncFromToken, handleExpired]);

  const refreshSession = useCallback(async () => {
    if (refreshing) return false;
    setRefreshing(true);
    setRefreshError(null);

    try {
      const refreshToken = await getStoredValue('refresh_token');
      if (!refreshToken) {
        throw new Error('Refresh token unavailable');
      }

      const response = await api.post('/auth/token/refresh', { refresh_token: refreshToken });
      const nextSessionToken = response.data?.session_token;
      const nextRefreshToken = response.data?.refresh_token;
      if (!nextSessionToken) {
        throw new Error('Missing session token in refresh response');
      }

      await setStoredValue('session_token', nextSessionToken);
      if (nextRefreshToken) {
        await setStoredValue('refresh_token', nextRefreshToken);
      }
      setCachedToken(nextSessionToken);

      const nextExpiryMs = decodeJwtExpMs(nextSessionToken);
      if (!nextExpiryMs) {
        throw new Error('Invalid refreshed session token');
      }

      expiryMsRef.current = nextExpiryMs;
      const nextSeconds = Math.max(Math.ceil((nextExpiryMs - Date.now()) / 1000), 0);
      setSecondsRemaining(nextSeconds);
      setWarningDismissed(false);
      setRefreshError(null);
      expiredRef.current = false;

      return true;
    } catch {
      setRefreshError('Unable to extend your session. Please try again.');
      return false;
    } finally {
      setRefreshing(false);
    }
  }, [refreshing]);

  const dismissWarning = useCallback(() => {
    setWarningDismissed(true);
  }, []);

  const clearRefreshError = useCallback(() => {
    setRefreshError(null);
  }, []);

  const isWarningVisible = Boolean(
    userId && secondsRemaining !== null && secondsRemaining > 0 && secondsRemaining <= WARNING_SECONDS && !warningDismissed,
  );

  const isCriticalVisible = Boolean(
    userId && secondsRemaining !== null && secondsRemaining > 0 && secondsRemaining <= CRITICAL_MODAL_SECONDS,
  );

  return {
    secondsRemaining,
    isWarningVisible,
    isCriticalVisible,
    refreshing,
    refreshError,
    refreshSession,
    dismissWarning,
    clearRefreshError,
  };
}
