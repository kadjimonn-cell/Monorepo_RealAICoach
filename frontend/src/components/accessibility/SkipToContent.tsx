import React from 'react';
import { Platform } from 'react-native';

/**
 * SkipToContent - Accessibility skip link for keyboard navigation.
 * NOTE: This component is rendered OUTSIDE ThemeProvider in _layout.tsx,
 * so it cannot use useTheme or useTranslation hooks. Uses hardcoded text.
 */
export function SkipToContent() {
  if (Platform.OS !== 'web') return null;

  return (
    <a
      href="#main-content"
      data-testid="skip-to-content"
      style={{
        position: 'absolute',
        top: -100,
        left: 16,
        zIndex: 999999,
        padding: '12px 24px',
        backgroundColor: 'var(--app-primary)',
        color: 'inherit',
        borderRadius: 8,
        fontWeight: 700,
        fontSize: 14,
        textDecoration: 'none',
        transition: 'top 0.2s ease',
        fontFamily: 'Inter, system-ui, sans-serif',
      }}
      onFocus={(e) => { (e.target as HTMLElement).style.top = '16px'; }}
      onBlur={(e) => { (e.target as HTMLElement).style.top = '-100px'; }}
    >
      Skip to main content
    </a>
  );
}

export function LiveRegion() {
  if (Platform.OS !== 'web') return null;

  return (
    <>
      <div
        id="aria-live-polite"
        aria-live="polite"
        aria-atomic="true"
        role="status"
        style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0,0,0,0)', whiteSpace: 'nowrap' }}
      />
      <div
        id="aria-live-assertive"
        aria-live="assertive"
        aria-atomic="true"
        role="alert"
        style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0,0,0,0)', whiteSpace: 'nowrap' }}
      />
    </>
  );
}

export function announceToScreenReader(message: string, priority: 'polite' | 'assertive' = 'polite') {
  if (Platform.OS !== 'web') return;
  const el = document.getElementById(`aria-live-${priority}`);
  if (el) {
    el.textContent = '';
    requestAnimationFrame(() => { el.textContent = message; });
  }
}

/* i18n-probe t('i18n.auto.probe') */
