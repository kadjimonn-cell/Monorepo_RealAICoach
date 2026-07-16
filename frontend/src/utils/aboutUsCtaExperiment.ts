import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { buildAnalyticsSource } from './buildAnalyticsSource';

export const ABOUT_US_CTA_EXPERIMENT_ID = 'about_us_cta_copy_v1';
export const ABOUT_US_CTA_EXPERIMENT_KEY = 'about_us_cta_copy_v1_assignment';

export type AboutUsCtaVariantId = 'activation' | 'demo-first';

export type AboutUsCtaExperimentAssignment = {
  assignedAt: string;
  bucket: number;
  experimentId: string;
  variantId: AboutUsCtaVariantId;
};

const CTA_VARIANTS: AboutUsCtaVariantId[] = ['activation', 'demo-first'];

function isValidAssignment(value: any): value is AboutUsCtaExperimentAssignment {
  return Boolean(
    value
    && typeof value === 'object'
    && value.experimentId === ABOUT_US_CTA_EXPERIMENT_ID
    && CTA_VARIANTS.includes(value.variantId)
    && Number.isFinite(Number(value.bucket))
    && typeof value.assignedAt === 'string',
  );
}

async function readAssignment(): Promise<AboutUsCtaExperimentAssignment | null> {
  try {
    const raw = await AsyncStorage.getItem(ABOUT_US_CTA_EXPERIMENT_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (isValidAssignment(parsed)) return parsed;
    }
  } catch {
    // ignore
  }

  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      const raw = window.localStorage.getItem(ABOUT_US_CTA_EXPERIMENT_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return isValidAssignment(parsed) ? parsed : null;
    } catch {
      return null;
    }
  }

  return null;
}

async function persistAssignment(assignment: AboutUsCtaExperimentAssignment): Promise<void> {
  const payload = JSON.stringify(assignment);
  try {
    await AsyncStorage.setItem(ABOUT_US_CTA_EXPERIMENT_KEY, payload);
  } catch {
    // ignore
  }

  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(ABOUT_US_CTA_EXPERIMENT_KEY, payload);
    } catch {
      // ignore
    }
  }
}

function createAssignment(): AboutUsCtaExperimentAssignment {
  const bucket = Math.floor(Math.random() * 100);
  return {
    assignedAt: new Date().toISOString(),
    bucket,
    experimentId: ABOUT_US_CTA_EXPERIMENT_ID,
    variantId: bucket < 50 ? 'activation' : 'demo-first',
  };
}

export async function loadOrAssignAboutUsCtaExperiment(): Promise<AboutUsCtaExperimentAssignment> {
  const existing = await readAssignment();
  if (existing) return existing;
  const assignment = createAssignment();
  await persistAssignment(assignment);
  return assignment;
}

export function buildAboutUsCtaSource(baseSource: string, variantId: AboutUsCtaVariantId | null | undefined): string {
  if (!variantId) return buildAnalyticsSource(baseSource);
  return buildAnalyticsSource(baseSource, variantId);
}