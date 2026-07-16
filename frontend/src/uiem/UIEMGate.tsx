/**
 * UIEMGate — The mandatory render pipeline gate.
 * 
 * DATA -> VALIDATION -> UIEM -> RENDER
 * 
 * Wraps any component to enforce all 4 validation layers.
 * Blocks render and shows safe fallback on validation failure.
 */
import React, { useRef, useMemo } from 'react';
import { useUIEM } from './UIEMContext';
import { UIEMFallback } from './UIEMFallback';
import { useRenderGuard } from './UIEMWatchdog';

interface UIEMGateProps {
  name: string;
  children: React.ReactNode;
  /** Required data fields — render blocked if any are undefined/null */
  requiredData?: Record<string, unknown>;
  /** Disable specific layers */
  skipLayers?: ('data' | 'state' | 'performance')[];
}

export function UIEMGate({ name, children, requiredData, skipLayers = [] }: UIEMGateProps) {
  const { logViolation } = useUIEM();
  const { checkRenderRate } = useRenderGuard(name);
  const renderTimeRef = useRef(Date.now());

  // ── LAYER 2: Data Validation ──
  const dataValid = useMemo(() => {
    if (skipLayers.includes('data') || !requiredData) return true;
    for (const [key, value] of Object.entries(requiredData)) {
      if (value === undefined || value === null) {
        logViolation({
          component: name,
          layer: 'data',
          error_type: 'missing_required_data',
          message: `Required field "${key}" is ${value === null ? 'null' : 'undefined'}`,
          severity: 'high',
        });
        return false;
      }
    }
    return true;
  }, [name, requiredData, skipLayers, logViolation]);

  // ── LAYER 3: State Validation (render loop detection) ──
  const stateValid = useMemo(() => {
    if (skipLayers.includes('state')) return true;
    return !checkRenderRate();
  }, [skipLayers, checkRenderRate]);

  // ── LAYER 4: Performance Validation ──
  const _perfValid = useMemo(() => {
    if (skipLayers.includes('performance')) return true;
    const now = Date.now();
    const elapsed = now - renderTimeRef.current;
    renderTimeRef.current = now;
    // Flag if re-render happened in < 16ms (60fps threshold) repeatedly
    if (elapsed < 16) {
      // Only log, don't block for perf — defer instead
      logViolation({
        component: name,
        layer: 'performance',
        error_type: 'rapid_rerender',
        message: `Re-render in ${elapsed}ms (< 16ms threshold)`,
        severity: 'info',
      });
    }
    return true; // Perf issues defer, don't block
  }, [name, skipLayers, logViolation]);

  // ── Gate Decision ──
  if (!dataValid) {
    return <UIEMFallback componentName={name} layer="data" message="Waiting for valid data" showSkeleton />;
  }

  if (!stateValid) {
    logViolation({
      component: name,
      layer: 'state',
      error_type: 'render_loop_blocked',
      message: `Render loop detected and blocked`,
      severity: 'critical',
    });
    return <UIEMFallback componentName={name} layer="state" message="Render loop stopped by UIEM" />;
  }

  return <>{children}</>;
}

/**
 * HOC version of UIEMGate for wrapping entire components.
 */
export function withUIEM<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  gateName: string,
  options?: { requiredData?: (props: P) => Record<string, unknown> }
) {
  return function UIEMWrapped(props: P) {
    const data = options?.requiredData ? options.requiredData(props) : undefined;
    return (
      <UIEMGate name={gateName} requiredData={data}>
        <WrappedComponent {...props} />
      </UIEMGate>
    );
  };
}
