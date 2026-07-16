import { Platform } from 'react-native';

type ShadowSize = 'sm' | 'md' | 'lg' | 'xl';

const WEB_SHADOWS = {
  light: {
    sm: '0 1px 3px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04)',
    md: '0 4px 16px rgba(15,23,42,0.08), 0 2px 4px rgba(15,23,42,0.04)',
    lg: '0 12px 32px rgba(15,23,42,0.10), 0 4px 8px rgba(15,23,42,0.05)',
    xl: '0 20px 48px rgba(15,23,42,0.12), 0 8px 16px rgba(15,23,42,0.06)',
  },
  dark: {
    sm: '0 1px 2px rgba(0,0,0,0.28)',
    md: '0 8px 22px rgba(0,0,0,0.36)',
    lg: '0 18px 40px rgba(0,0,0,0.42)',
    xl: '0 28px 60px rgba(0,0,0,0.5)',
  },
};

const IOS_SHADOWS = {
  light: {
    sm: { shadowColor: '#0F172A', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, shadowRadius: 2, elevation: 1 },
    md: { shadowColor: '#0F172A', shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.08, shadowRadius: 14, elevation: 3 },
    lg: { shadowColor: '#0F172A', shadowOffset: { width: 0, height: 12 }, shadowOpacity: 0.1, shadowRadius: 24, elevation: 6 },
    xl: { shadowColor: '#0F172A', shadowOffset: { width: 0, height: 18 }, shadowOpacity: 0.12, shadowRadius: 34, elevation: 8 },
  },
  dark: {
    sm: { shadowColor: '#000000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.24, shadowRadius: 2, elevation: 1 },
    md: { shadowColor: '#000000', shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.3, shadowRadius: 14, elevation: 3 },
    lg: { shadowColor: '#000000', shadowOffset: { width: 0, height: 12 }, shadowOpacity: 0.36, shadowRadius: 24, elevation: 6 },
    xl: { shadowColor: '#000000', shadowOffset: { width: 0, height: 18 }, shadowOpacity: 0.42, shadowRadius: 34, elevation: 8 },
  },
};

export function getShadow(size: ShadowSize = 'md', isDark = false): any {
  if (Platform.OS === 'web') {
    return { boxShadow: (isDark ? WEB_SHADOWS.dark : WEB_SHADOWS.light)[size] } as any;
  }
  return (isDark ? IOS_SHADOWS.dark : IOS_SHADOWS.light)[size];
}
