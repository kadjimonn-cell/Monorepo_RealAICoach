/**
 * ThemeEnforcer — Runtime CSS custom property injection.
 *
 * Reads from theme/v1.ts (the single source of truth) and injects
 * CSS variables onto :root. Acts as a safety net for components
 * that use var(--app-*) instead of useTheme().colors.
 *
 * Version: v1 (synced with theme/v1.ts)
 */
import { useEffect } from 'react';
import { Platform } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { V1_LIGHT, V1_DARK } from '../theme/v1';

function toCssVars(tokens: Record<string, string>): Record<string, string> {
  return {
    '--app-bg':            tokens.bg,
    '--app-bg-alt':        tokens.bgAlt,
    '--app-card':          tokens.card,
    '--app-card-soft':     tokens.cardSoft,
    '--app-surface':       tokens.surface,
    '--app-border':        tokens.border,
    '--app-border-light':  tokens.borderLight,
    '--app-border-strong': tokens.borderStrong,
    '--app-text':          tokens.text,
    '--app-text-sec':      tokens.textSec,
    '--app-text-muted':    tokens.textMuted,
    '--app-text-dim':      tokens.textDim,
    '--app-accent':        tokens.accent,
    '--app-accent-soft':   tokens.accentSoft,
    '--app-primary':       tokens.primary,
    '--app-primary-soft':  tokens.primarySoft,
    '--app-success':       tokens.success,
    '--app-warning':       tokens.warning,
    '--app-error':         tokens.error,
    '--app-info':          tokens.info,
    '--app-input-bg':      tokens.input,
    '--app-input-border':  tokens.inputBorder,
    '--app-skeleton':      tokens.skeleton,
  };
}

const LIGHT = toCssVars(V1_LIGHT as unknown as Record<string, string>);
const DARK = toCssVars(V1_DARK as unknown as Record<string, string>);

const STYLE_ID = 'theme-enforcer-vars';

export function ThemeEnforcer() {
  const { darkMode } = useTheme();

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;

    const vars = darkMode ? DARK : LIGHT;
    let style = document.getElementById(STYLE_ID) as HTMLStyleElement | null;

    if (!style) {
      style = document.createElement('style');
      style.id = STYLE_ID;
      document.head.appendChild(style);
    }

    const css = `:root {\n${Object.entries(vars)
      .map(([k, v]) => `  ${k}: ${v};`)
      .join('\n')}\n}`;

    style.textContent = css;
  }, [darkMode]);

  return null;
}

export { LIGHT as THEME_VARS_LIGHT, DARK as THEME_VARS_DARK };

/* i18n-probe t('i18n.auto.probe') */
