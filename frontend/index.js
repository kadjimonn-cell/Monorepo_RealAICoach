import { registerRootComponent } from 'expo';
import { ExpoRoot } from 'expo-router';
import { Platform } from 'react-native';
import { alphaColorSafe } from './src/utils/colorAlpha';

if (typeof globalThis !== 'undefined' && typeof globalThis.__alphaColor !== 'function') {
  globalThis.__alphaColor = alphaColorSafe;
}

// Suppress known upstream @react-navigation pointerEvents deprecation warning
// (comes from BottomTabBar.tsx, Header.tsx, Screen.tsx in @react-navigation)
if (Platform.OS === 'web') {
  const _origWarn = console.warn;
  console.warn = (...args) => {
    if (typeof args[0] === 'string' && args[0].includes('props.pointerEvents is deprecated')) return;
    _origWarn.apply(console, args);
  };
}

// Must be exported or Fast Refresh won't update the context
export function App() {
  const ctx = require.context('./app');
  return <ExpoRoot context={ctx} />;
}

registerRootComponent(App);
