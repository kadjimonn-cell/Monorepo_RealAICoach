/**
 * UIEM — UI Enforcement Middleware
 * Barrel export for all UIEM modules.
 */
export { UIEMProvider, useUIEM } from './UIEMContext';
export type { UIEMViolation, UIEMLayer, UIEMSeverity } from './UIEMContext';
export { UIEMGate, withUIEM } from './UIEMGate';
export { UIEMFallback } from './UIEMFallback';
export { UIEMWatchdog, useRenderGuard } from './UIEMWatchdog';
