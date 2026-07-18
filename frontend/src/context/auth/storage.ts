import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { setCachedToken } from '../../services/api';
import { secureGetToken, secureSetToken, secureClearToken } from '../../utils/secureTokenStore';
import type { User } from './types';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { canonicalizeAdminIdentity } from '../../utils/adminAccess';

const SESSION_TOKEN_KEY = 'session_token';
const GUEST_MODE_KEY = 'guest_mode';
export const USER_SNAPSHOT_KEY = 'auth_user_snapshot';
const WEB_COOKIE_ONLY_AUTH = true;

export async function getSessionToken(): Promise<string | null> {
  if (WEB_COOKIE_ONLY_AUTH && Platform.OS === 'web') {
    return null;
  }
  if (Platform.OS !== 'web') {
    return secureGetToken();
  }
  try {
    return await AsyncStorage.getItem(SESSION_TOKEN_KEY);
  } catch {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      try {
        return window.localStorage.getItem(SESSION_TOKEN_KEY);
      } catch {
        return null;
      }
    }
    return null;
  }
}

export async function persistSessionToken(token: string): Promise<void> {
  if (WEB_COOKIE_ONLY_AUTH && Platform.OS === 'web') {
    // Strict mode: use HttpOnly cookie only for web session auth.
    setCachedToken(null);
    return;
  }

  // Set fast-path token first so immediate route/API transitions after login
  // do not race against AsyncStorage writes.
  setCachedToken(token);
  if (Platform.OS !== 'web') {
    await secureSetToken(token);
    return;
  }
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(SESSION_TOKEN_KEY, token);
    } catch (error) { handleAppRecoverableError({ scope: 'src/context/auth/storage.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }
  await AsyncStorage.setItem(SESSION_TOKEN_KEY, token);
}

export async function persistUserSnapshot(userData: User | null): Promise<void> {
  if (!userData) return;
  const serialized = JSON.stringify(canonicalizeAdminIdentity(userData as any) || userData);
  await AsyncStorage.setItem(USER_SNAPSHOT_KEY, serialized).catch(() => {});
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(USER_SNAPSHOT_KEY, serialized);
    } catch (error) { handleAppRecoverableError({ scope: 'src/context/auth/storage.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }
}

export async function loadUserSnapshot(): Promise<User | null> {
  let raw: string | null = null;
  try {
    raw = await AsyncStorage.getItem(USER_SNAPSHOT_KEY);
  } catch {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      try {
        raw = window.localStorage.getItem(USER_SNAPSHOT_KEY);
      } catch (error) { handleAppRecoverableError({ scope: 'src/context/auth/storage.ts#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as User;
    if (!parsed || typeof parsed !== 'object') return null;
    const safeSnapshot = canonicalizeAdminIdentity(parsed as any);
    return (safeSnapshot || parsed) as User;
  } catch {
    return null;
  }
}

export async function clearGuestModeFlag(): Promise<void> {
  await AsyncStorage.removeItem(GUEST_MODE_KEY).catch(() => {});
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      window.localStorage.removeItem(GUEST_MODE_KEY);
    } catch (error) { handleAppRecoverableError({ scope: 'src/context/auth/storage.ts#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }
}

export async function clearPersistedSession(): Promise<void> {
  if (Platform.OS !== 'web') {
    await secureClearToken();
  }
  await AsyncStorage.multiRemove([SESSION_TOKEN_KEY, GUEST_MODE_KEY, USER_SNAPSHOT_KEY]).catch(() => {});
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      window.localStorage.removeItem(SESSION_TOKEN_KEY);
      window.localStorage.removeItem(GUEST_MODE_KEY);
      window.localStorage.removeItem(USER_SNAPSHOT_KEY);
    } catch (error) { handleAppRecoverableError({ scope: 'src/context/auth/storage.ts#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }
}