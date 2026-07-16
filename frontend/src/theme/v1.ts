/**
 * Theme v1 export names are preserved for compatibility.
 * Runtime theme source of truth is now `theme/v2.ts`.
 */
import { V2_LIGHT, V2_DARK, THEME_V2_VERSION } from './v2';

export const THEME_VERSION = THEME_V2_VERSION;

export const V1_LIGHT = V2_LIGHT;
export const V1_DARK = V2_DARK;

export type ThemeColors = typeof V2_LIGHT;
