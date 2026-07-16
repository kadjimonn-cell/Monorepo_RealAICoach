export interface HybridPollingConfig {
  reconnectAttempt: number;
  thresholdAttempt?: number;
  slowIntervalMs: number;
  fastIntervalMs: number;
}

export type WorkflowPollingPresetKey =
  | 'support-ticket-fallback'
  | 'batch-job-status'
  | 'webhook-stream-fallback';

export interface WorkflowPollingPreset {
  slowIntervalMs: number;
  fastIntervalMs: number;
  runOnMount: true;
  wsEnabled: false;
}

export const WORKFLOW_POLLING_PRESETS: Record<WorkflowPollingPresetKey, WorkflowPollingPreset> = {
  'support-ticket-fallback': {
    slowIntervalMs: 8000,
    fastIntervalMs: 3000,
    runOnMount: true,
    wsEnabled: false,
  },
  'batch-job-status': {
    slowIntervalMs: 6000,
    fastIntervalMs: 3000,
    runOnMount: true,
    wsEnabled: false,
  },
  'webhook-stream-fallback': {
    slowIntervalMs: 5000,
    fastIntervalMs: 2500,
    runOnMount: true,
    wsEnabled: false,
  },
};

export function getWorkflowPollingPreset(
  presetKey: WorkflowPollingPresetKey,
  overrides: Partial<WorkflowPollingPreset> = {}
): WorkflowPollingPreset {
  return {
    ...WORKFLOW_POLLING_PRESETS[presetKey],
    ...overrides,
    runOnMount: true,
    wsEnabled: false,
  };
}

export function getHybridPollingInterval(config: HybridPollingConfig): number {
  const thresholdAttempt = Number.isFinite(config.thresholdAttempt) ? Number(config.thresholdAttempt) : 3;
  const reconnectAttempt = Number(config.reconnectAttempt || 0);
  return reconnectAttempt >= thresholdAttempt ? config.fastIntervalMs : config.slowIntervalMs;
}
