/**
 * GlobalTranslationProvider — React bridge for the DOM translation engine.
 *
 * The actual translation engine lives in +html.tsx as a vanilla JS script
 * that runs before React hydrates. This React component bridges ThemeContext
 * language changes to the engine via window.__txEngine.reinit(lang).
 */

import React, { useEffect } from 'react';
import { Platform } from 'react-native';
import { usePathname } from 'expo-router';
import { enforceProtectedBrands } from '../utils/brandProtection';
import { buildLocaleSeedMap } from '../i18n/translationLoader';
import { getLanguageCode } from '../utils/translations';
import { useTheme } from '../context/ThemeContext';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const DOM_TRANSLATION_PUBLIC_EXACT = new Set([
  '/',
  '/welcome',
  '/about',
  '/about-us',
  '/talent-network',
  '/blog',
  '/career',
  '/careers',
  '/certificate-compare',
  '/contact',
  '/faq',
  '/features',
  '/feature-gallery',
  '/help',
  '/home',
  '/hiring-hub',
  '/pricing',
  '/privacy-policy',
  '/security',
  '/terms',
]);

const DOM_TRANSLATION_PUBLIC_PREFIXES = [
  '/blog/',
  '/features/',
  '/mini-apps/',
  '/careers/',
  '/subscription/',
];

const normalizePath = (pathname: string | null | undefined): string => {
  const raw = String(pathname || '/').trim();
  if (!raw) return '/';
  const noQuery = raw.split('?')[0].split('#')[0] || '/';
  if (noQuery === '/') return '/';
  return noQuery.endsWith('/') ? noQuery.slice(0, -1) : noQuery;
};

const shouldEnableDomEngineForPath = (pathname: string | null | undefined): boolean => {
  const path = normalizePath(pathname);
  if (DOM_TRANSLATION_PUBLIC_EXACT.has(path)) return true;
  return DOM_TRANSLATION_PUBLIC_PREFIXES.some((prefix) => path.startsWith(prefix));
};

export function GlobalTranslationProvider({ children }: { children: React.ReactNode }) {
  const { language, languageCode } = useTheme();
  const pathname = usePathname();
  const lang = getLanguageCode(languageCode || language || 'en');

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    let cancelled = false;

    const syncEngine = async () => {
      try {
        const engine = (window as any).__txEngine;
        if (!engine) return;

        const shouldEnable = lang !== 'en' && shouldEnableDomEngineForPath(pathname);
        if (!shouldEnable) {
          if (engine.isOn()) engine.stop();
          return;
        }

        const seedMap = await buildLocaleSeedMap(lang);
        if (cancelled) return;

        const protectedSeedMap: Record<string, string> = {};
        Object.keys(seedMap).forEach((source) => {
          protectedSeedMap[source] = enforceProtectedBrands(source, seedMap[source]);
        });

        engine.seedCache?.(lang, protectedSeedMap);
        if (engine.isOn?.() && engine.getLang?.() === lang) return;
        engine.reinit(lang);
      } catch (error) { handleAppRecoverableError({ scope: 'src/providers/GlobalTranslationProvider.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    };

    syncEngine();

    return () => {
      cancelled = true;
    };
  }, [lang, pathname]);

  return <>{children}</>;
}

export function useGlobalTranslation() {
  const { language, languageCode } = useTheme();
  const lang = getLanguageCode(languageCode || language || 'en');
  const tt = (text: string): string => text;
  return { tt, lang };
}

export default GlobalTranslationProvider;
