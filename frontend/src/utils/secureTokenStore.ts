// Native-only secure JWT storage (expo-secure-store) with one-time migration
// from legacy AsyncStorage persistence. All functions are no-ops on web so the
// web cookie-only auth flow remains byte-identical.
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

const SESSION_TOKEN_KEY = 'session_token';

let SecureStore: any = null;
if (Platform.OS !== 'web') {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  SecureStore = require('expo-secure-store');
}

export async function secureSetToken(token: string): Promise<void> {
  if (Platform.OS === 'web' || !SecureStore) return;
  try {
    await SecureStore.setItemAsync(SESSION_TOKEN_KEY, token);
    // Remove the plaintext legacy copy once the token lives in secure storage
    await AsyncStorage.removeItem(SESSION_TOKEN_KEY).catch(() => {});
  } catch {
    // SecureStore unavailable (rare device/simulator edge) — keep AsyncStorage
    await AsyncStorage.setItem(SESSION_TOKEN_KEY, token).catch(() => {});
  }
}

export async function secureGetToken(): Promise<string | null> {
  if (Platform.OS === 'web' || !SecureStore) return null;
  try {
    const token = await SecureStore.getItemAsync(SESSION_TOKEN_KEY);
    if (token) return token;
  } catch {
    /* fall through to legacy migration */
  }
  try {
    const legacy = await AsyncStorage.getItem(SESSION_TOKEN_KEY);
    if (legacy) {
      await secureSetToken(legacy);
      return legacy;
    }
  } catch {
    /* no legacy token */
  }
  return null;
}

export async function secureClearToken(): Promise<void> {
  if (Platform.OS === 'web' || !SecureStore) return;
  await SecureStore.deleteItemAsync(SESSION_TOKEN_KEY).catch(() => {});
  await AsyncStorage.removeItem(SESSION_TOKEN_KEY).catch(() => {});
}
