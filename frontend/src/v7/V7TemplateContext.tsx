/**
 * V7 Template Context — Isolated theme provider for template-scoped components.
 * 
 * STRICT ISOLATION: V7 context must ONLY be used inside template domains.
 * Detects and logs if V2 platform context leaks into template scope.
 */
import React, { createContext, useContext, useMemo } from 'react';
import { V7_LIGHT, V7_DARK, V7_SPACING, V7_TYPOGRAPHY, V7_RADII, V7_GRID } from '../theme/v7';
import type { V7Colors } from '../theme/v7';
import { useUIEM } from '../uiem/UIEMContext';

interface V7ContextValue {
  colors: V7Colors;
  darkMode: boolean;
  spacing: typeof V7_SPACING;
  typography: typeof V7_TYPOGRAPHY;
  radii: typeof V7_RADII;
  grid: typeof V7_GRID;
  isV7Domain: true; // Always true — marker for boundary detection
}

const V7Context = createContext<V7ContextValue | null>(null);

/**
 * useV7Theme — Access V7 template tokens.
 * Throws if used outside V7TemplateProvider (boundary violation).
 */
export function useV7Theme(): V7ContextValue {
  const ctx = useContext(V7Context);
  if (!ctx) {
    throw new Error('[V7] useV7Theme called outside V7TemplateProvider — theme boundary violation');
  }
  return ctx;
}

/**
 * Check if we're inside a V7 domain (non-throwing version).
 */
export function useIsV7Domain(): boolean {
  const ctx = useContext(V7Context);
  return ctx?.isV7Domain === true;
}

interface V7TemplateProviderProps {
  children: React.ReactNode;
  darkMode?: boolean;
}

/**
 * V7TemplateProvider — Wraps template-scoped components with V7 tokens.
 * Must ONLY be used around template content — never around platform UI.
 */
export function V7TemplateProvider({ children, darkMode = false }: V7TemplateProviderProps) {
  const { _logViolation } = useUIEM();

  const value = useMemo<V7ContextValue>(() => ({
    colors: darkMode ? V7_DARK : V7_LIGHT,
    darkMode,
    spacing: V7_SPACING,
    typography: V7_TYPOGRAPHY,
    radii: V7_RADII,
    grid: V7_GRID,
    isV7Domain: true,
  }), [darkMode]);

  return (
    <V7Context.Provider value={value}>
      {children}
    </V7Context.Provider>
  );
}

export { V7Context };
