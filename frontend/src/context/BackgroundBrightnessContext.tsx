import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const BRIGHTNESS_KEY = 'bg_brightness';
const PRESET_KEY = 'bg_preset';
const PAGE_OVERRIDES_KEY = 'bg_page_overrides';
const DEFAULT_BRIGHTNESS = 15;
const DEFAULT_PRESET = 'default'; // 'default' means use per-page variants

export const PRESET_OPTIONS = [
  { id: 'default', label: 'Default', icon: 'apps-outline' as const, desc: 'Page-specific themes' },
  { id: 'nature', label: 'Nature', icon: 'leaf-outline' as const, desc: 'Mountains & landscapes' },
  { id: 'abstract', label: 'Abstract', icon: 'color-palette-outline' as const, desc: 'Colorful gradients' },
  { id: 'minimal', label: 'Minimal', icon: 'cube-outline' as const, desc: 'Clean architecture' },
  { id: 'city', label: 'City', icon: 'business-outline' as const, desc: 'Urban skylines' },
] as const;

export const PAGE_VARIANT_INFO: Record<string, { label: string; icon: string; pages: string[] }> = {
  coaching: { label: 'AI Tools', icon: 'sparkles-outline', pages: ['Learning Hub', 'Problem Solver', 'Briefing'] },
  admin: { label: 'Admin', icon: 'shield-outline', pages: ['Executive Dashboard'] },
  profile: { label: 'Account', icon: 'person-outline', pages: ['Profile', 'Settings', 'Help', 'Tickets'] },
  gallery: { label: 'Gallery', icon: 'grid-outline', pages: ['Feature Gallery'] },
  analytics: { label: 'Analytics', icon: 'bar-chart-outline', pages: ['My Analytics', 'Leaderboard', 'Progress'] },
  finance: { label: 'Finance', icon: 'card-outline', pages: ['Payments', 'Subscription'] },
  productivity: { label: 'Productivity', icon: 'documents-outline', pages: ['Library', 'Notifications', 'Integrations', 'Agenda'] },
  security: { label: 'Security', icon: 'lock-closed-outline', pages: ['Verification', 'Jobs Portal'] },
};

export const PRESET_COLLECTIONS: Record<string, string[]> = {
  nature: [
    'https://images.unsplash.com/photo-1700148676800-a12f8a016deb?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1683041132892-0fe990b3afc3?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1683669446787-3b4881d3d267?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1595885914073-3af381bbee7e?w=1920&q=80&auto=format',
  ],
  abstract: [
    'https://images.unsplash.com/photo-1614812512064-267299572975?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1614812511804-a62c6ce2f5fb?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1614812513172-567d2fe96a75?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1665764884116-11bf71512155?w=1920&q=80&auto=format',
  ],
  minimal: [
    'https://images.unsplash.com/photo-1720087448033-db1904db294b?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1572635148687-307f8ca9b737?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1570630591157-9cea0732d4f5?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1728460377480-5232daa731a0?w=1920&q=80&auto=format',
  ],
  city: [
    'https://images.unsplash.com/photo-1757843298369-6e5503c14bfd?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1768286868224-4f9375c29913?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1598495886228-fedb44a5b5a1?w=1920&q=80&auto=format',
    'https://images.unsplash.com/photo-1762853005930-3263e4c1b7ce?w=1920&q=80&auto=format',
  ],
};

// 'global' means inherit from global preset
type PageOverrides = Record<string, string>;

interface BgCtx {
  brightness: number;
  setBrightness: (v: number) => void;
  preset: string;
  setPreset: (v: string) => void;
  pageOverrides: PageOverrides;
  setPageOverride: (variant: string, presetId: string) => void;
  getEffectivePreset: (variant: string) => string;
}

const Ctx = createContext<BgCtx>({
  brightness: DEFAULT_BRIGHTNESS,
  setBrightness: () => {},
  preset: DEFAULT_PRESET,
  setPreset: () => {},
  pageOverrides: {},
  setPageOverride: () => {},
  getEffectivePreset: () => DEFAULT_PRESET,
});

export function BackgroundBrightnessProvider({ children }: { children: React.ReactNode }) {
  const [brightness, setBrightnessState] = useState(DEFAULT_BRIGHTNESS);
  const [preset, setPresetState] = useState(DEFAULT_PRESET);
  const [pageOverrides, setPageOverridesState] = useState<PageOverrides>({});

  useEffect(() => {
    Promise.all([
      AsyncStorage.getItem(BRIGHTNESS_KEY),
      AsyncStorage.getItem(PRESET_KEY),
      AsyncStorage.getItem(PAGE_OVERRIDES_KEY),
    ]).then(([b, p, po]) => {
      if (b !== null) setBrightnessState(Number(b));
      if (p !== null) setPresetState(p);
      if (po !== null) {
        try { setPageOverridesState(JSON.parse(po)); } catch (error) { handleAppRecoverableError({ scope: 'src/context/BackgroundBrightnessContext.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }
    }).catch(() => {});
  }, []);

  const setBrightness = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(100, Math.round(v)));
    setBrightnessState(clamped);
    AsyncStorage.setItem(BRIGHTNESS_KEY, String(clamped)).catch(() => {});
  }, []);

  const setPreset = useCallback((v: string) => {
    setPresetState(v);
    AsyncStorage.setItem(PRESET_KEY, v).catch(() => {});
  }, []);

  const setPageOverride = useCallback((variant: string, presetId: string) => {
    setPageOverridesState(prev => {
      const next = { ...prev };
      if (presetId === 'global') {
        delete next[variant];
      } else {
        next[variant] = presetId;
      }
      AsyncStorage.setItem(PAGE_OVERRIDES_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  const getEffectivePreset = useCallback((variant: string): string => {
    // Page-level override takes priority
    if (pageOverrides[variant]) return pageOverrides[variant];
    // Otherwise use global preset
    return preset;
  }, [pageOverrides, preset]);

  return (
    <Ctx.Provider value={{ brightness, setBrightness, preset, setPreset, pageOverrides, setPageOverride, getEffectivePreset }}>
      {children}
    </Ctx.Provider>
  );
}

export const useBackgroundBrightness = () => useContext(Ctx);
