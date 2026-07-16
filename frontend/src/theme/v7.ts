/**
 * V7 Theme — Template-Only Design System
 * 
 * STRICT ISOLATION: V7 tokens are ONLY for template-scoped components.
 * Platform UI uses V2. Never mix V2 inside templates or V7 outside templates.
 */

export const THEME_V7_VERSION = 'v7' as const;

// ── V7 Spacing Scale ──
export const V7_SPACING = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  section: 40,
} as const;

// ── V7 Typography ──
export const V7_TYPOGRAPHY = {
  heading1: { fontSize: 28, fontWeight: '800' as const, lineHeight: 34 },
  heading2: { fontSize: 22, fontWeight: '700' as const, lineHeight: 28 },
  heading3: { fontSize: 18, fontWeight: '700' as const, lineHeight: 24 },
  body: { fontSize: 14, fontWeight: '400' as const, lineHeight: 20 },
  bodySm: { fontSize: 12, fontWeight: '400' as const, lineHeight: 18 },
  caption: { fontSize: 10, fontWeight: '500' as const, lineHeight: 14 },
  label: { fontSize: 11, fontWeight: '600' as const, lineHeight: 16 },
  mono: { fontSize: 12, fontWeight: '400' as const, fontFamily: 'monospace', lineHeight: 18 },
} as const;

// ── V7 Border Radii ──
export const V7_RADII = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  pill: 999,
} as const;

// ── V7 Light Palette (Template Domain) ──
export const V7_LIGHT = {
  bg: '#F4F7FA',
  bgAlt: '#EDF1F6',
  bgSoft: '#E8EDF4',
  card: '#FFFFFF',
  cardMuted: '#F9FAFB',
  surface: '#FFFFFF',
  surfaceHover: '#F0F4F8',
  surfaceElevated: '#FFFFFF',

  text: '#1A2332',
  textSecondary: '#4A5568',
  textMuted: '#718096',
  textDim: '#A0AEC0',
  textDisabled: '#CBD5E0',

  border: '#E2E8F0',
  borderMd: '#CBD5E0',
  borderLight: '#EDF2F7',
  borderStrong: '#A0AEC0',
  divider: '#E2E8F0',

  primary: '#2B6CB0',
  primarySoft: '#2B6CB014',
  primaryHover: '#2C5282',
  primaryText: '#FFFFFF',

  accent: '#4C6EF5',
  accentSoft: '#4C6EF514',
  accentHover: '#3B5BDB',

  success: '#38A169',
  successSoft: '#38A16914',
  successText: '#276749',
  warning: '#D69E2E',
  warningSoft: '#D69E2E14',
  warningText: '#975A16',
  error: '#E53E3E',
  errorSoft: '#E53E3E14',
  errorText: '#C53030',
  info: '#3182CE',
  infoSoft: '#3182CE14',
  infoText: '#2B6CB0',

  hover: 'rgba(43,108,176,0.08)',
  active: 'rgba(43,108,176,0.14)',
  focus: 'rgba(76,110,245,0.28)',
  overlay: 'rgba(26,35,50,0.42)',
  shadowColor: 'rgba(26,35,50,0.08)',

  input: '#FFFFFF',
  inputBorder: '#CBD5E0',
  inputText: '#1A2332',
  placeholder: '#A0AEC0',

  badge: '#EBF4FF',
  badgeText: '#2B6CB0',

  skeleton: '#E2E8F0',

  templateBorder: '#D1DAE6',
  templateHeader: '#F0F4F8',
  templateFooter: '#F7FAFC',
  templateHighlight: '#EBF8FF',
} as const;

// ── V7 Dark Palette (Template Domain) ──
export const V7_DARK = {
  bg: '#0D1321',
  bgAlt: '#131B2E',
  bgSoft: '#161F33',
  card: '#131B2E',
  cardMuted: '#161F33',
  surface: '#131B2E',
  surfaceHover: '#1A253B',
  surfaceElevated: '#161F33',

  text: '#E2E8F0',
  textSecondary: '#A0AEC0',
  textMuted: '#718096',
  textDim: '#4A5568',
  textDisabled: '#2D3748',

  border: '#2D3748',
  borderMd: '#4A5568',
  borderLight: '#1A2332',
  borderStrong: '#4A5568',
  divider: '#2D3748',

  primary: '#63B3ED',
  primarySoft: '#63B3ED22',
  primaryHover: '#4299E1',
  primaryText: '#0D1321',

  accent: '#7C8CF5',
  accentSoft: '#7C8CF522',
  accentHover: '#5C6FF5',

  success: '#68D391',
  successSoft: '#68D39122',
  successText: '#9AE6B4',
  warning: '#F6E05E',
  warningSoft: '#F6E05E22',
  warningText: '#FEFCBF',
  error: '#FC8181',
  errorSoft: '#FC818122',
  errorText: '#FED7D7',
  info: '#63B3ED',
  infoSoft: '#63B3ED22',
  infoText: '#BEE3F8',

  hover: 'rgba(99,179,237,0.14)',
  active: 'rgba(99,179,237,0.22)',
  focus: 'rgba(124,140,245,0.36)',
  overlay: 'rgba(2,6,23,0.72)',
  shadowColor: 'rgba(0,0,0,0.45)',

  input: '#161F33',
  inputBorder: '#4A5568',
  inputText: '#E2E8F0',
  placeholder: '#4A5568',

  badge: '#1A365D',
  badgeText: '#BEE3F8',

  skeleton: '#2D3748',

  templateBorder: '#2D3748',
  templateHeader: '#1A253B',
  templateFooter: '#0D1321',
  templateHighlight: '#1A365D',
} as const;

export type V7Colors = typeof V7_LIGHT;

// ── V7 Approved Component Names ──
export const V7_APPROVED_COMPONENTS = [
  'V7Card', 'V7Header', 'V7Footer', 'V7Section', 'V7Badge',
  'V7Button', 'V7Input', 'V7Text', 'V7Divider', 'V7Grid',
  'V7Stack', 'V7Image', 'V7Table', 'V7List', 'V7Alert', 'V7Metric',
] as const;

// ── V7 Layout Grid ──
export const V7_GRID = {
  columns: 12,
  gutter: V7_SPACING.md,
  maxWidth: 960,
  padding: V7_SPACING.lg,
} as const;

// ── V2 Token Fingerprints (for cross-contamination detection) ──
export const V2_FINGERPRINT_COLORS = [
  '#0F766E', '#14B8A6', '#5EEAD4', '#2DD4BF',
  '#0B5F58', '#99F6E4', '#ECFDFB',
] as const;
