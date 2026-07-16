const HEX_ALPHA_FALLBACK = 'FF';

const CSS_VAR_FALLBACKS: Record<string, string> = {
  '--app-primary': '#0F766E',
  '--app-success': '#16A34A',
  '--app-error': '#DC2626',
  '--app-warning': '#D97706',
  '--app-info': '#0284C7',
  '--app-accent': '#14B8A6',
  '--app-cyan': '#0891B2',
  '--app-purple': '#0F766E',
  '--app-red': '#DC2626',
  '--app-green': '#16A34A',
  '--app-yellow': '#CA8A04',
  '--app-blue': '#14B8A6',
};

function normalizeHexAlpha(alphaHex: string): number {
  const raw = String(alphaHex || '').trim().replace('#', '').toUpperCase();
  const candidate = raw.length === 1 ? raw + raw : raw;
  const parsed = Number.parseInt(candidate || HEX_ALPHA_FALLBACK, 16);
  if (Number.isNaN(parsed)) return 1;
  return Math.max(0, Math.min(1, parsed / 255));
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const raw = String(hex || '').trim().replace('#', '');
  if (![3, 6].includes(raw.length)) return null;
  const full = raw.length === 3 ? raw.split('').map((c) => c + c).join('') : raw;
  const intVal = Number.parseInt(full, 16);
  if (Number.isNaN(intVal)) return null;
  return {
    r: (intVal >> 16) & 255,
    g: (intVal >> 8) & 255,
    b: intVal & 255,
  };
}

function resolveCssVarColor(color: string): string {
  if (typeof document === 'undefined') return color;
  const match = color.match(/^var\((--[^,)\s]+)(?:\s*,\s*([^\)]+))?\)$/i);
  if (!match) return color;

  const cssVarName = match[1];
  const fallback = String(match[2] || '').trim();
  const resolved = getComputedStyle(document.documentElement).getPropertyValue(cssVarName).trim();
  return resolved || fallback || color;
}

export function withAlpha(color: string, alphaHex: string): string {
  const alpha = normalizeHexAlpha(alphaHex);
  const input = resolveCssVarColor(String(color || '').trim());

  if (!input) return color;

  const hexRgb = hexToRgb(input);
  if (hexRgb) {
    return `rgba(${hexRgb.r}, ${hexRgb.g}, ${hexRgb.b}, ${alpha})`;
  }

  const rgbMatch = input.match(/^rgba?\(([^)]+)\)$/i);
  if (rgbMatch) {
    const parts = rgbMatch[1].split(',').map((p) => Number.parseFloat(p.trim()));
    if (parts.length >= 3 && parts.slice(0, 3).every((v) => Number.isFinite(v))) {
      return `rgba(${parts[0]}, ${parts[1]}, ${parts[2]}, ${alpha})`;
    }
  }

  return input;
}

export function alphaColorSafe(rawColor: any, rawAlpha: any): string {
  const color = String(rawColor || '').trim();
  const alphaRaw = String(rawAlpha || '').replace('#', '').trim();
  const alpha = (alphaRaw.length === 1 ? `${alphaRaw}${alphaRaw}` : alphaRaw || HEX_ALPHA_FALLBACK).slice(0, 2).toUpperCase();

  if (/^#([0-9a-f]{6})$/i.test(color)) {
    return `${color}${alpha}`;
  }

  if (/^#([0-9a-f]{3})$/i.test(color)) {
    const expanded = `#${color.slice(1).split('').map((c) => c + c).join('')}`;
    return `${expanded}${alpha}`;
  }

  if (color.startsWith('var(')) {
    const match = color.match(/var\((--[^),\s]+)/i);
    const fallback = match ? CSS_VAR_FALLBACKS[match[1]] : undefined;
    if (fallback) return `${fallback}${alpha}`;
  }

  return withAlpha(color, alpha);
}

export function ensureGlobalAlphaColor() {
  if (typeof globalThis === 'undefined') return;
  if (typeof (globalThis as any).__alphaColor === 'function') return;
  (globalThis as any).__alphaColor = alphaColorSafe;
}
