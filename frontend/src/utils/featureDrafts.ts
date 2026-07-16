import AsyncStorage from '@react-native-async-storage/async-storage';
import { handleAppRecoverableError } from './appRecoverableError';

const DRAFTS_KEY = 'feature_drafts';

const canUseWebStorage = () => typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';

export interface FeatureDraftEntry {
  text: string;
  updatedAt: string;
}

type DraftMap = Record<string, FeatureDraftEntry>;

async function getDraftMap(): Promise<DraftMap> {
  try {
    if (canUseWebStorage()) {
      const stored = window.localStorage.getItem(DRAFTS_KEY);
      return stored ? JSON.parse(stored) : {};
    }
    const stored = await AsyncStorage.getItem(DRAFTS_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

async function setDraftMap(map: DraftMap): Promise<void> {
  try {
    const serialized = JSON.stringify(map);
    if (canUseWebStorage()) {
      window.localStorage.setItem(DRAFTS_KEY, serialized);
      return;
    }
    await AsyncStorage.setItem(DRAFTS_KEY, serialized);
  } catch (error) { handleAppRecoverableError({ scope: 'src/utils/featureDrafts.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

export async function getFeatureDraft(featureId: string): Promise<string> {
  const map = await getDraftMap();
  return map[featureId]?.text || '';
}

export async function setFeatureDraft(featureId: string, text: string): Promise<void> {
  const map = await getDraftMap();
  map[featureId] = { text, updatedAt: new Date().toISOString() };
  await setDraftMap(map);
}
