import AsyncStorage from '@react-native-async-storage/async-storage';
import { handleAppRecoverableError } from './appRecoverableError';

const RECENT_FEATURES_KEY = 'recent_features';
const PINNED_FEATURES_KEY = 'pinned_recommended_features';
const canUseWebStorage = () => typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';

export interface RecentFeatureEntry {
  id: string;
  openedAt: string;
}

export async function getRecentFeatures(): Promise<RecentFeatureEntry[]> {
  try {
    if (canUseWebStorage()) {
      const stored = window.localStorage.getItem(RECENT_FEATURES_KEY);
      return stored ? JSON.parse(stored) : [];
    }
    const stored = await AsyncStorage.getItem(RECENT_FEATURES_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

export async function setRecentFeatures(entries: RecentFeatureEntry[]): Promise<void> {
  try {
    const serialized = JSON.stringify(entries);
    if (canUseWebStorage()) {
      window.localStorage.setItem(RECENT_FEATURES_KEY, serialized);
      return;
    }
    await AsyncStorage.setItem(RECENT_FEATURES_KEY, serialized);
  } catch (error) { handleAppRecoverableError({ scope: 'src/utils/recentFeatures.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

export async function getPinnedFeatures(): Promise<string[]> {
  try {
    if (canUseWebStorage()) {
      const stored = window.localStorage.getItem(PINNED_FEATURES_KEY);
      return stored ? JSON.parse(stored) : [];
    }
    const stored = await AsyncStorage.getItem(PINNED_FEATURES_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

export async function setPinnedFeatures(ids: string[]): Promise<void> {
  try {
    const serialized = JSON.stringify(ids);
    if (canUseWebStorage()) {
      window.localStorage.setItem(PINNED_FEATURES_KEY, serialized);
      return;
    }
    await AsyncStorage.setItem(PINNED_FEATURES_KEY, serialized);
  } catch (error) { handleAppRecoverableError({ scope: 'src/utils/recentFeatures.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}
