export const STARTUP_RECOVERY_DELAY_KEY = 'startup_recovery_auto_refresh_delay_ms_v1';
export const DEFAULT_STARTUP_RECOVERY_DELAY_MS = 3000;
export const STARTUP_RECOVERY_DELAY_OPTIONS = [1000, 3000, 5000, 8000] as const;

export const normalizeStartupRecoveryDelay = (value: any): number => {
  const parsed = Number(value || 0);
  if (!Number.isFinite(parsed)) return DEFAULT_STARTUP_RECOVERY_DELAY_MS;
  const rounded = Math.round(parsed);
  return STARTUP_RECOVERY_DELAY_OPTIONS.includes(rounded as any)
    ? rounded
    : DEFAULT_STARTUP_RECOVERY_DELAY_MS;
};
