import { Platform } from 'react-native';

export const DISPLAY_FONT_FAMILY = Platform.OS === 'web'
  ? "'Avenir Next', 'Segoe UI', 'Helvetica Neue', sans-serif"
  : undefined;

export const BODY_FONT_FAMILY = Platform.OS === 'web'
  ? "'IBM Plex Sans', 'Avenir Next', 'Segoe UI', sans-serif"
  : undefined;

export const MONO_FONT_FAMILY = Platform.OS === 'web'
  ? "'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace"
  : undefined;