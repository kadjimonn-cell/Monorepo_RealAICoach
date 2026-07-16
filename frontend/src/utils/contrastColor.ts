type Rgb = { r: number; g: number; b: number };

const CSS_VAR_FALLBACKS: Record<string, string> = {
  '--app-primary': '#0F766E',
  '--app-primary-text': '#FFFFFF',
  '--app-text': '#0F172A',
  '--app-warning': '#D97706',
  '--app-success': '#16A34A',
  '--app-error': '#DC2626',
  '--app-info': '#0284C7',
};

const resolveCssVar = (input: string): string => {
  const match = String(input || '').trim().match(/^var\((--[^,)\s]+)(?:\s*,\s*([^\)]+))?\)$/i);
  if (!match) return String(input || '').trim();
  const varName = match[1];
  const inlineFallback = String(match[2] || '').trim();

  if (typeof document !== 'undefined') {
    const runtimeValue = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    if (runtimeValue) return runtimeValue;
  }

  return inlineFallback || CSS_VAR_FALLBACKS[varName] || input;
};

const parseRgb = (raw: string): Rgb | null => {
  const color = resolveCssVar(raw);
  const hex = color.replace('#', '').trim();

  if (/^[0-9a-f]{3}$/i.test(hex)) {
    return {
      r: Number.parseInt(hex[0] + hex[0], 16),
      g: Number.parseInt(hex[1] + hex[1], 16),
      b: Number.parseInt(hex[2] + hex[2], 16),
    };
  }

  if (/^[0-9a-f]{6}$/i.test(hex)) {
    return {
      r: Number.parseInt(hex.slice(0, 2), 16),
      g: Number.parseInt(hex.slice(2, 4), 16),
      b: Number.parseInt(hex.slice(4, 6), 16),
    };
  }

  const rgbMatch = color.match(/^rgba?\(([^)]+)\)$/i);
  if (!rgbMatch) return null;
  const parts = rgbMatch[1].split(',').map((p) => Number.parseFloat(p.trim()));
  if (parts.length < 3 || parts.slice(0, 3).some((v) => Number.isNaN(v))) return null;
  return { r: parts[0], g: parts[1], b: parts[2] };
};

const channelLuminance = (value: number) => {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};

export const getReadableTextColor = (
  backgroundColor: string,
  options?: { light?: string; dark?: string; threshold?: number },
) => {
  const light = options?.light || 'var(--app-primary-text)';
  const dark = options?.dark || 'var(--app-text)';
  const threshold = typeof options?.threshold === 'number' ? options.threshold : 0.56;

  const rgb = parseRgb(backgroundColor);
  if (!rgb) return light;

  const luminance =
    0.2126 * channelLuminance(rgb.r) +
    0.7152 * channelLuminance(rgb.g) +
    0.0722 * channelLuminance(rgb.b);

  return luminance > threshold ? dark : light;
};
