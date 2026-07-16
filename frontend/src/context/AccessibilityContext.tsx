/**
 * SVG element IDs, not hex colors. Context injects CSS variables via the
 * existing `ThemeContext`; no structural chrome rendered here.
 */
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

export interface AccessibilityPreferences {
  textSize: 'small' | 'medium' | 'large' | 'extra-large';
  dyslexiaFont: boolean;
  highContrast: boolean;
  colorBlindMode: 'none' | 'protanopia' | 'deuteranopia' | 'tritanopia';
  contrastMode: 'default' | 'dark' | 'light' | 'ultra-contrast';
  screenReaderOptimized: boolean;
  keyboardNavigation: boolean;
  focusIndicators: boolean;
  motionReduction: boolean;
  readingGuide: boolean;
  textToSpeech: boolean;
  buttonSpacing: boolean;
  simplifiedNav: boolean;
  easyNavMode: boolean;
  voiceCommand: boolean;
}

interface AccessibilityContextType {
  prefs: AccessibilityPreferences;
  updatePref: <K extends keyof AccessibilityPreferences>(key: K, value: AccessibilityPreferences[K]) => void;
  resetAll: () => void;
  applyPreset: (preset: Partial<AccessibilityPreferences>) => void;
  panelOpen: boolean;
  setPanelOpen: (v: boolean) => void;
  fontScale: number;
  fontFamily: string;
  activeCount: number;
  speakText: (text: string) => void;
  stopSpeaking: () => void;
  isSpeaking: boolean;
}

const DEFAULTS: AccessibilityPreferences = {
  textSize: 'medium',
  dyslexiaFont: false,
  highContrast: false,
  colorBlindMode: 'none',
  contrastMode: 'default',
  screenReaderOptimized: false,
  keyboardNavigation: false,
  focusIndicators: false,
  motionReduction: false,
  readingGuide: false,
  textToSpeech: false,
  buttonSpacing: false,
  simplifiedNav: false,
  easyNavMode: false,
  voiceCommand: false,
};

const STORAGE_KEY = 'accessibility_preferences';

const TEXT_SCALES: Record<string, number> = {
  'small': 0.85,
  'medium': 1,
  'large': 1.2,
  'extra-large': 1.45,
};

const AccessibilityContext = createContext<AccessibilityContextType | undefined>(undefined);

export function useAccessibility() {
  const ctx = useContext(AccessibilityContext);
  if (!ctx) {
    // Return safe defaults when used outside provider (e.g., welcome page)
    return {
      prefs: DEFAULTS,
      updatePref: () => {},
      resetAll: () => {},
      applyPreset: () => {},
      panelOpen: false,
      setPanelOpen: () => {},
      fontScale: 1,
      fontFamily: 'Manrope_400Regular, sans-serif',
      activeCount: 0,
      speakText: () => {},
      stopSpeaking: () => {},
      isSpeaking: false,
    } as AccessibilityContextType;
  }
  return ctx;
}

export function AccessibilityProvider({ children, userId }: { children: React.ReactNode; userId?: string }) {
  const [prefs, setPrefs] = useState<AccessibilityPreferences>(DEFAULTS);
  const [panelOpen, setPanelOpen] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const synthRef = useRef<SpeechSynthesis | null>(null);

  // Init speech synthesis
  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && window.speechSynthesis) {
      synthRef.current = window.speechSynthesis;
    }
    return () => {
      synthRef.current?.cancel();
    };
  }, []);

  // Load prefs from local storage then sync from API
  useEffect(() => {
    (async () => {
      try {
        const local = await AsyncStorage.getItem(STORAGE_KEY);
        if (local) setPrefs({ ...DEFAULTS, ...JSON.parse(local) });
      } catch (error) { handleAppRecoverableError({ scope: 'src/context/AccessibilityContext.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      if (userId) {
        try {
          const { data } = await api.get(`/accessibility/preferences/${userId}`);
          if (data?.preferences) {
            const merged = { ...DEFAULTS, ...data.preferences };
            setPrefs(merged);
            await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
          }
        } catch (error) { handleAppRecoverableError({ scope: 'src/context/AccessibilityContext.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }
    })();
  }, [userId]);

  // Apply CSS classes to document
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    const root = document.documentElement;
    root.setAttribute('data-text-size', prefs.textSize);
    root.setAttribute('data-dyslexia-font', String(prefs.dyslexiaFont));
    root.setAttribute('data-high-contrast', String(prefs.highContrast));
    root.setAttribute('data-color-blind', prefs.colorBlindMode);
    root.setAttribute('data-contrast-mode', prefs.contrastMode);
    root.setAttribute('data-focus-indicators', String(prefs.focusIndicators));
    root.setAttribute('data-motion-reduction', String(prefs.motionReduction));
    root.setAttribute('data-button-spacing', String(prefs.buttonSpacing));
    root.setAttribute('data-easy-nav', String(prefs.easyNavMode));
    root.setAttribute('data-simplified-nav', String(prefs.simplifiedNav));
    root.setAttribute('data-screen-reader', String(prefs.screenReaderOptimized));
    if (prefs.motionReduction) {
      root.style.setProperty('--a11y-transition', 'none');
      root.style.setProperty('--a11y-animation', 'none');
    } else {
      root.style.removeProperty('--a11y-transition');
      root.style.removeProperty('--a11y-animation');
    }
    root.style.setProperty('--a11y-font-scale', String(TEXT_SCALES[prefs.textSize] || 1));
  }, [prefs]);

  // Reading guide management (moved from panel to context for centralized control)
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    let guide = document.getElementById('a11y-reading-guide');
    if (prefs.readingGuide) {
      if (!guide) {
        guide = document.createElement('div');
        guide.id = 'a11y-reading-guide';
        document.body.appendChild(guide);
      }
      guide.style.display = 'block';
      const handler = (e: MouseEvent) => { guide!.style.top = `${e.clientY - 20}px`; };
      document.addEventListener('mousemove', handler);
      (guide as any)._handler = handler;
      return () => {
        document.removeEventListener('mousemove', handler);
        if (guide) guide.style.display = 'none';
      };
    } else {
      if (guide) {
        guide.style.display = 'none';
        if ((guide as any)._handler) {
          document.removeEventListener('mousemove', (guide as any)._handler);
          (guide as any)._handler = null;
        }
      }
    }
  }, [prefs.readingGuide]);

  // Inject global accessibility stylesheet once
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    if (document.getElementById('a11y-global-styles')) return;
    const style = document.createElement('style');
    style.id = 'a11y-global-styles';
    style.textContent = A11Y_CSS;
    document.head.appendChild(style);

    // Optional remote OpenDyslexic font loading (disabled by default to avoid cross-network failures).
    const enableRemoteA11yFonts = String(process.env.REACT_APP_ENABLE_REMOTE_A11Y_FONTS || '').toLowerCase() === 'true';
    if (enableRemoteA11yFonts) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = 'https://fonts.cdnfonts.com/css/opendyslexic';
      document.head.appendChild(link);
    }
  }, []);

  const persist = useCallback((newPrefs: AccessibilityPreferences) => {
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(newPrefs)).catch(() => {});
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      if (userId) {
        api.put(`/accessibility/preferences/${userId}`, { preferences: newPrefs }).catch(() => {});
      }
    }, 800);
  }, [userId]);

  const updatePref = useCallback(<K extends keyof AccessibilityPreferences>(key: K, value: AccessibilityPreferences[K]) => {
    setPrefs(prev => {
      const next = { ...prev, [key]: value };
      persist(next);
      return next;
    });
  }, [persist]);

  const resetAll = useCallback(() => {
    setPrefs(DEFAULTS);
    persist(DEFAULTS);
    if (userId) {
      api.post(`/accessibility/preferences/${userId}/reset`).catch(() => {});
    }
  }, [userId, persist]);

  const applyPreset = useCallback((preset: Partial<AccessibilityPreferences>) => {
    setPrefs(prev => {
      const next = { ...DEFAULTS, ...preset };
      persist(next);
      return next;
    });
  }, [persist]);

  const speakText = useCallback((text: string) => {
    if (!synthRef.current || !prefs.textToSpeech) return;
    synthRef.current.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    synthRef.current.speak(utterance);
  }, [prefs.textToSpeech]);

  const stopSpeaking = useCallback(() => {
    synthRef.current?.cancel();
    setIsSpeaking(false);
  }, []);

  const fontScale = TEXT_SCALES[prefs.textSize] || 1;
  const fontFamily = prefs.dyslexiaFont ? '"OpenDyslexic", sans-serif' : 'Manrope_400Regular, sans-serif';
  const activeCount = Object.entries(prefs).filter(([k, v]) => {
    if (k === 'textSize') return v !== 'medium';
    if (k === 'colorBlindMode') return v !== 'none';
    if (k === 'contrastMode') return v !== 'default';
    return v === true;
  }).length;

  return (
    <AccessibilityContext.Provider value={{
      prefs, updatePref, resetAll, applyPreset, panelOpen, setPanelOpen,
      fontScale, fontFamily, activeCount, speakText, stopSpeaking, isSpeaking,
    }}>
      {children}
    </AccessibilityContext.Provider>
  );
}

const A11Y_CSS = `
/* ═══ TEXT SIZE SCALING ═══ */
html[data-text-size="small"] { font-size: 13px; }
html[data-text-size="medium"] { font-size: 16px; }
html[data-text-size="large"] { font-size: 19px; }
html[data-text-size="extra-large"] { font-size: 23px; }

/* ═══ DYSLEXIA FONT ═══ */
html[data-dyslexia-font="true"] * {
  font-family: "OpenDyslexic", sans-serif !important;
  letter-spacing: 0.05em;
  word-spacing: 0.12em;
  line-height: 1.8 !important;
}

/* ═══ HIGH CONTRAST ═══ */
html[data-high-contrast="true"] {
  filter: contrast(1.35);
}

/* ═══ COLOR BLIND MODES ═══ */
html[data-color-blind="protanopia"]   { filter: url('#protanopia-filter') contrast(1.05); }
html[data-color-blind="deuteranopia"] { filter: url('#deuteranopia-filter') contrast(1.05); }
html[data-color-blind="tritanopia"]   { filter: url('#tritanopia-filter') contrast(1.05); }

/* ═══ ULTRA CONTRAST ═══ */
html[data-contrast-mode="ultra-contrast"] {
  filter: contrast(1.75) saturate(0);
}

/* ═══ FOCUS INDICATORS ═══ */
html[data-focus-indicators="true"] *:focus {
  outline: 3px solid #FF6B00 !important;
  outline-offset: 2px !important;
  box-shadow: 0 0 0 5px rgba(255,107,0,0.25) !important;
}
html[data-focus-indicators="true"] *:focus:not(:focus-visible) {
  outline: none !important;
  box-shadow: none !important;
}
html[data-focus-indicators="true"] *:focus-visible {
  outline: 3px solid #FF6B00 !important;
  outline-offset: 2px !important;
  box-shadow: 0 0 0 5px rgba(255,107,0,0.25) !important;
}

/* ═══ MOTION REDUCTION ═══ */
html[data-motion-reduction="true"] *,
html[data-motion-reduction="true"] *::before,
html[data-motion-reduction="true"] *::after {
  animation-duration: 0.01ms !important;
  animation-iteration-count: 1 !important;
  transition-duration: 0.01ms !important;
  scroll-behavior: auto !important;
}

/* ═══ BUTTON SPACING ═══ */
html[data-button-spacing="true"] button,
html[data-button-spacing="true"] [role="button"],
html[data-button-spacing="true"] a,
html[data-button-spacing="true"] input[type="submit"],
html[data-button-spacing="true"] input[type="button"] {
  min-height: 48px !important;
  min-width: 48px !important;
  margin: 4px !important;
  padding: 10px 16px !important;
}

/* ═══ EASY NAV (LARGE CARDS) ═══ */
html[data-easy-nav="true"] [data-testid*="nav-"] {
  min-height: 56px !important;
  font-size: 18px !important;
  padding: 14px 20px !important;
}

/* ═══ READING GUIDE (via JS overlay) ═══ */
#a11y-reading-guide {
  position: fixed;
  left: 0;
  right: 0;
  height: 40px;
  pointer-events: none;
  z-index: 99999;
  border-top: 2px solid rgba(255,107,0,0.6);
  border-bottom: 2px solid rgba(255,107,0,0.6);
  background: rgba(255,107,0,0.06);
  transition: top 0.05s linear;
  display: none;
}

/* ═══ SKIP TO CONTENT ═══ */
.a11y-skip-link {
  position: fixed;
  top: -100px;
  left: 16px;
  background: #FF6B00;
  color: #FFF;
  padding: 12px 24px;
  border-radius: 0 0 8px 8px;
  font-weight: 700;
  font-size: 16px;
  z-index: 100000;
  text-decoration: none;
  transition: top 0.15s;
}
.a11y-skip-link:focus {
  top: 0;
}
`;
