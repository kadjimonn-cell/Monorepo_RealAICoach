export const MAX_RETRY_ATTEMPTS = 3;
export const RETRY_BACKOFF_MS = [1500, 3000, 5000] as const;

export type ResilienceAttemptResult = {
  ok: boolean;
  status?: number;
  detail?: string;
};

export type ResilienceDecision = {
  shouldRetry: boolean;
  shouldOpenUpgrade: boolean;
  nextDelayMs: number;
  terminalErrorMessage: string;
};

export type ChaosFailureMode = 'none' | 'transient_5xx_once' | 'always_5xx' | 'network_once';

export class PlaybackChaosController {
  private mode: ChaosFailureMode;
  private hitCount: number;

  constructor(mode: ChaosFailureMode = 'none') {
    this.mode = mode;
    this.hitCount = 0;
  }

  inject(result: ResilienceAttemptResult): ResilienceAttemptResult {
    this.hitCount += 1;
    if (this.mode === 'none') return result;

    if (this.mode === 'transient_5xx_once' && this.hitCount === 1) {
      return { ok: false, status: 502, detail: 'CHAOS_TRANSIENT_5XX_ONCE' };
    }
    if (this.mode === 'always_5xx') {
      return { ok: false, status: 503, detail: 'CHAOS_ALWAYS_5XX' };
    }
    if (this.mode === 'network_once' && this.hitCount === 1) {
      return { ok: false, status: 0, detail: 'CHAOS_NETWORK_ONCE' };
    }

    return result;
  }
}

export const evaluateResilienceDecision = (
  attemptIndex: number,
  result: ResilienceAttemptResult,
): ResilienceDecision => {
  const status = Number(result.status || 0);
  const detail = String(result.detail || 'Playback failed');
  const exhausted = attemptIndex >= MAX_RETRY_ATTEMPTS - 1;

  if (result.ok) {
    return {
      shouldRetry: false,
      shouldOpenUpgrade: false,
      nextDelayMs: 0,
      terminalErrorMessage: '',
    };
  }

  const planOrQuotaBlocked = status === 403 || status === 429;
  if (planOrQuotaBlocked) {
    return {
      shouldRetry: false,
      shouldOpenUpgrade: status === 403 || detail.toLowerCase().includes('requires') || detail.toLowerCase().includes('plan'),
      nextDelayMs: 0,
      terminalErrorMessage: detail,
    };
  }

  if (!exhausted) {
    return {
      shouldRetry: true,
      shouldOpenUpgrade: false,
      nextDelayMs: Number(RETRY_BACKOFF_MS[attemptIndex] || RETRY_BACKOFF_MS[RETRY_BACKOFF_MS.length - 1]),
      terminalErrorMessage: '',
    };
  }

  return {
    shouldRetry: false,
    shouldOpenUpgrade: false,
    nextDelayMs: 0,
    terminalErrorMessage: detail,
  };
};

export const getNextQueueCandidateIndex = (
  currentCursor: number,
  queueLength: number,
): { nextCursor: number; selectedIndex: number } => {
  const safeLength = Math.max(0, Number(queueLength || 0));
  if (safeLength <= 0) {
    return { nextCursor: 0, selectedIndex: -1 };
  }
  const selectedIndex = Math.max(0, Number(currentCursor || 0) % safeLength);
  return { nextCursor: selectedIndex + 1, selectedIndex };
};
