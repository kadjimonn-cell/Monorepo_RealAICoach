// Perf: OpenTelemetry browser instrumentation removed from the startup graph.
// initializeBrowserObservability() is now a no-op; the call site in
// src/services/api.ts is intentionally unchanged.

let initialized = false;

export function initializeBrowserObservability(): void {
  if (initialized) return;
  if (typeof window === 'undefined') return;
  initialized = true;
}
