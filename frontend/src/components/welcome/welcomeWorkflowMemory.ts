import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

export const WELCOME_WORKFLOW_MEMORY_KEY = 'welcome_workflow_memory_v1';
export const WELCOME_SUMMARY_INTEREST_KEY = 'welcome_summary_interest_v1';
export const WELCOME_DECISION_PATH_KEY = 'welcome_decision_path_v1';
export const WELCOME_DECISION_PATH_AREAS = ['features', 'pricing', 'social-proof'] as const;

export type WelcomeWorkflowMemory = {
  featureId: string;
  categoryId: string;
  updatedAt: string;
};

export type WelcomeSummaryInterestAreaId = 'features' | 'pricing' | 'social-proof';

export type WelcomeSummaryInterest = {
  areaId: WelcomeSummaryInterestAreaId;
  updatedAt: string;
};

export type WelcomeDecisionPathAreaId = WelcomeSummaryInterestAreaId;

export type WelcomeDecisionPathMemory = {
  topAreaId: WelcomeDecisionPathAreaId;
  lastAreaId: WelcomeDecisionPathAreaId;
  scores: Record<WelcomeDecisionPathAreaId, number>;
  updatedAt: string;
};

const EMPTY_DECISION_SCORES: Record<WelcomeDecisionPathAreaId, number> = {
  features: 0,
  pricing: 0,
  'social-proof': 0,
};

function isValidMemory(value: any): value is WelcomeWorkflowMemory {
  return Boolean(
    value
    && typeof value === 'object'
    && typeof value.featureId === 'string'
    && typeof value.categoryId === 'string'
    && typeof value.updatedAt === 'string',
  );
}

function isValidSummaryInterest(value: any): value is WelcomeSummaryInterest {
  return Boolean(
    value
    && typeof value === 'object'
    && ['features', 'pricing', 'social-proof'].includes(value.areaId)
    && typeof value.updatedAt === 'string',
  );
}

function isValidDecisionPathMemory(value: any): value is WelcomeDecisionPathMemory {
  if (!value || typeof value !== 'object') return false;
  if (!WELCOME_DECISION_PATH_AREAS.includes(value.topAreaId)) return false;
  if (!WELCOME_DECISION_PATH_AREAS.includes(value.lastAreaId)) return false;
  if (!value.scores || typeof value.scores !== 'object') return false;

  return WELCOME_DECISION_PATH_AREAS.every((areaId) => Number.isFinite(Number(value.scores?.[areaId])))
    && typeof value.updatedAt === 'string';
}

async function loadStoredJson<T>(key: string, validator: (value: any) => value is T): Promise<T | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (validator(parsed)) return parsed;
    }
  } catch {
    // ignore
  }

  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      const raw = window.localStorage.getItem(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return validator(parsed) ? parsed : null;
    } catch {
      return null;
    }
  }

  return null;
}

async function persistStoredJson(key: string, value: unknown): Promise<void> {
  const payload = JSON.stringify(value);
  try {
    await AsyncStorage.setItem(key, payload);
  } catch {
    // ignore
  }

  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(key, payload);
    } catch {
      // ignore
    }
  }
}

export async function loadWelcomeWorkflowMemory(): Promise<WelcomeWorkflowMemory | null> {
  return loadStoredJson(WELCOME_WORKFLOW_MEMORY_KEY, isValidMemory);
}

export async function persistWelcomeWorkflowMemory(memory: WelcomeWorkflowMemory): Promise<void> {
  await persistStoredJson(WELCOME_WORKFLOW_MEMORY_KEY, memory);
}

export async function loadWelcomeSummaryInterest(): Promise<WelcomeSummaryInterest | null> {
  return loadStoredJson(WELCOME_SUMMARY_INTEREST_KEY, isValidSummaryInterest);
}

export async function persistWelcomeSummaryInterest(interest: WelcomeSummaryInterest): Promise<void> {
  await persistStoredJson(WELCOME_SUMMARY_INTEREST_KEY, interest);
}

export function mergeWelcomeDecisionPathSignal(
  memory: WelcomeDecisionPathMemory | null,
  areaId: WelcomeDecisionPathAreaId,
  weight = 1,
): WelcomeDecisionPathMemory {
  const nextScores = {
    ...EMPTY_DECISION_SCORES,
    ...(memory?.scores || {}),
  };
  nextScores[areaId] = Math.max(0, Number(nextScores[areaId] || 0) + Math.max(1, Math.round(weight)));

  const topAreaId = WELCOME_DECISION_PATH_AREAS.reduce<WelcomeDecisionPathAreaId>((best, candidate) => {
    const candidateScore = Number(nextScores[candidate] || 0);
    const bestScore = Number(nextScores[best] || 0);
    if (candidateScore > bestScore) return candidate;
    if (candidateScore === bestScore && candidate === areaId) return candidate;
    return best;
  }, (memory?.topAreaId || areaId) as WelcomeDecisionPathAreaId);

  return {
    topAreaId,
    lastAreaId: areaId,
    scores: nextScores,
    updatedAt: new Date().toISOString(),
  };
}

export async function loadWelcomeDecisionPath(): Promise<WelcomeDecisionPathMemory | null> {
  return loadStoredJson(WELCOME_DECISION_PATH_KEY, isValidDecisionPathMemory);
}

export async function persistWelcomeDecisionPath(memory: WelcomeDecisionPathMemory): Promise<void> {
  await persistStoredJson(WELCOME_DECISION_PATH_KEY, memory);
}
