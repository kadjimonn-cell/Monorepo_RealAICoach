import React, { createContext, useContext, useMemo } from 'react';
import { useGlobalPlatformState } from '../hooks/useGlobalPlatformState';

export interface GLSTokens {
  maxWidth: number;
  maxWidthWide: number;
  maxWidthNarrow: number;
  paddingMobile: number;
  paddingTablet: number;
  paddingDesktop: number;
  paddingLarge: number;
  sectionPaddingMobile: number;
  sectionPaddingTablet: number;
  sectionPaddingDesktop: number;
  breakpoints: {
    mobile: number;
    tablet: number;
    desktop: number;
    large: number;
  };
  layoutMode: 'centered' | 'full-width' | 'compact';
  responsiveEnabled: boolean;
}

export const DEFAULT_GLS_TOKENS: GLSTokens = {
  maxWidth: 1240,
  maxWidthWide: 1440,
  maxWidthNarrow: 960,
  paddingMobile: 18,
  paddingTablet: 28,
  paddingDesktop: 32,
  paddingLarge: 40,
  sectionPaddingMobile: 48,
  sectionPaddingTablet: 64,
  sectionPaddingDesktop: 80,
  breakpoints: {
    mobile: 0,
    tablet: 768,
    desktop: 1024,
    large: 1440,
  },
  layoutMode: 'centered',
  responsiveEnabled: true,
};

function normalizeLayoutTokens(raw: any): GLSTokens {
  if (!raw || typeof raw !== 'object') return DEFAULT_GLS_TOKENS;

  const tokens: GLSTokens = {
    maxWidth: Number(raw.max_width ?? DEFAULT_GLS_TOKENS.maxWidth),
    maxWidthWide: Number(raw.max_width_wide ?? DEFAULT_GLS_TOKENS.maxWidthWide),
    maxWidthNarrow: Number(raw.max_width_narrow ?? DEFAULT_GLS_TOKENS.maxWidthNarrow),
    paddingMobile: Number(raw.padding_mobile ?? DEFAULT_GLS_TOKENS.paddingMobile),
    paddingTablet: Number(raw.padding_tablet ?? DEFAULT_GLS_TOKENS.paddingTablet),
    paddingDesktop: Number(raw.padding_desktop ?? DEFAULT_GLS_TOKENS.paddingDesktop),
    paddingLarge: Number(raw.padding_large ?? DEFAULT_GLS_TOKENS.paddingLarge),
    sectionPaddingMobile: Number(raw.section_padding_mobile ?? DEFAULT_GLS_TOKENS.sectionPaddingMobile),
    sectionPaddingTablet: Number(raw.section_padding_tablet ?? DEFAULT_GLS_TOKENS.sectionPaddingTablet),
    sectionPaddingDesktop: Number(raw.section_padding_desktop ?? DEFAULT_GLS_TOKENS.sectionPaddingDesktop),
    breakpoints: {
      mobile: 0,
      tablet: Number(raw.breakpoint_tablet ?? DEFAULT_GLS_TOKENS.breakpoints.tablet),
      desktop: Number(raw.breakpoint_desktop ?? DEFAULT_GLS_TOKENS.breakpoints.desktop),
      large: Number(raw.breakpoint_large ?? DEFAULT_GLS_TOKENS.breakpoints.large),
    },
    layoutMode: ['centered', 'full-width', 'compact'].includes(String(raw.layout_mode || '').toLowerCase())
      ? (String(raw.layout_mode).toLowerCase() as 'centered' | 'full-width' | 'compact')
      : DEFAULT_GLS_TOKENS.layoutMode,
    responsiveEnabled: Boolean(raw.responsive_enabled ?? DEFAULT_GLS_TOKENS.responsiveEnabled),
  };

  if (tokens.breakpoints.desktop <= tokens.breakpoints.tablet) {
    tokens.breakpoints.desktop = tokens.breakpoints.tablet + 1;
  }
  if (tokens.breakpoints.large <= tokens.breakpoints.desktop) {
    tokens.breakpoints.large = tokens.breakpoints.desktop + 1;
  }
  if (tokens.maxWidthNarrow > tokens.maxWidth) {
    tokens.maxWidthNarrow = tokens.maxWidth;
  }
  if (tokens.maxWidth > tokens.maxWidthWide) {
    tokens.maxWidth = tokens.maxWidthWide;
  }

  return tokens;
}

interface GLSContextValue {
  tokens: GLSTokens;
  loading: boolean;
}

const GLSContext = createContext<GLSContextValue>({
  tokens: DEFAULT_GLS_TOKENS,
  loading: true,
});

export function GLSProvider({ children }: { children: React.ReactNode }) {
  const { state, loading } = useGlobalPlatformState();

  const value = useMemo<GLSContextValue>(() => ({
    tokens: normalizeLayoutTokens((state as any)?.layout_config),
    loading,
  }), [state, loading]);

  return <GLSContext.Provider value={value}>{children}</GLSContext.Provider>;
}

export function useGLSConfig() {
  return useContext(GLSContext);
}
