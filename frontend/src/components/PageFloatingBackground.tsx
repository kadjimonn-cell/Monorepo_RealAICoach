import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Platform } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { useBackgroundBrightness, PRESET_COLLECTIONS } from '../context/BackgroundBrightnessContext';

// ── Page-specific image collections (used when preset is 'default') ──
export const PAGE_COLLECTIONS: Record<string, string[]> = {
  // Home dashboard — data-rich command center imagery
  home: [
    'https://static.prod-images.emergentagent.com/jobs/7c3c8b68-3aaa-4a62-b9a0-466afdea9162/images/198c14f19df9ca52f53f99507581204f189d58df60dd484e799174a8db00e703.png',
    'https://static.prod-images.emergentagent.com/jobs/7c3c8b68-3aaa-4a62-b9a0-466afdea9162/images/2c69219cd902599e348991f07f8a1c229806e6dc91a6c178b559a97b4f41cc2f.png',
    'https://static.prod-images.emergentagent.com/jobs/7c3c8b68-3aaa-4a62-b9a0-466afdea9162/images/db6e174c7af3102fcb79a2afb7bc83f154d7eb9d754c97425a51faf188a27f15.png',
    'https://static.prod-images.emergentagent.com/jobs/7c3c8b68-3aaa-4a62-b9a0-466afdea9162/images/3dda28a2a14eb59839570524b5f5bae75a6cb227b5b876a7e41fefaaf8132671.png',
  ],
  // Nature & focus — Coaching, AI tools, Learning Hub
  coaching: [
    'https://images.unsplash.com/photo-1762457189347-9061d9687390?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1768811751834-925777512e25?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1769542711710-9ec6a731851d?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1772377763796-9439456189a7?w=1280&q=60&auto=format',
  ],
  // Abstract tech — Admin dashboard, analytics, control center
  admin: [
    'https://images.unsplash.com/photo-1761078739233-629de9252840?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1603347729548-6844517490c7?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1764258057610-be7ca21a0978?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1771013304380-dfaf9f928de6?w=1280&q=60&auto=format',
  ],
  // Minimalist workspace — Profile, settings, help, tickets
  profile: [
    'https://images.unsplash.com/photo-1761123261084-53c40fe1e607?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1765371512336-99c2b1c6975f?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1765371515218-0a4c992ba8e2?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1765371513492-264506c3ad09?w=1280&q=60&auto=format',
  ],
  // Futuristic AI — Feature Gallery
  gallery: [
    'https://images.unsplash.com/photo-1768796371277-5cff3ec6cfc1?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1640231912426-0d5feab0b9f9?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1695902173528-0b15104c4554?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1664639985362-7eb8309f9e94?w=1280&q=60&auto=format',
  ],
  // Analytics & data — My Analytics, leaderboard, progress
  analytics: [
    'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1504868584819-f8e8b4b6d7e3?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1526628953301-3e589a6a8b74?w=1280&q=60&auto=format',
  ],
  // Finance & payments — Subscription plans, payment history
  finance: [
    'https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1642790106117-e829e14a795f?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1559526324-593bc073d938?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1518186285589-2f7649de83e0?w=1280&q=60&auto=format',
  ],
  // Collaboration & productivity — Content library, integrations, agenda
  productivity: [
    'https://images.unsplash.com/photo-1497215842964-222b430dc094?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1522071820081-009f0129c71c?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1542744173-8e7e53415bb0?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1531538606174-e5b64ba660e0?w=1280&q=60&auto=format',
  ],
  // Security & verification — ID verification, employer portal
  security: [
    'https://images.unsplash.com/photo-1563013544-824ae1b704d3?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1510511459019-5dda7724fd87?w=1280&q=60&auto=format',
    'https://images.unsplash.com/photo-1555949963-ff9fe0c870eb?w=1280&q=60&auto=format',
  ],
  // Default/fallback — existing images
  default: [
    'https://static.prod-images.emergentagent.com/jobs/3b78c97f-d2eb-45fd-ae96-0647fd26bb32/images/419c6aa428fc04534369b6377ce545ea69d7bf4312deff6127a6d6faf736e7d6.png',
    'https://static.prod-images.emergentagent.com/jobs/3b78c97f-d2eb-45fd-ae96-0647fd26bb32/images/21491b4b40674805a010b7146d059f2c19253b98f105ae64508d66a8226abfae.png',
    'https://static.prod-images.emergentagent.com/jobs/3b78c97f-d2eb-45fd-ae96-0647fd26bb32/images/f114b55ab3775ba25ae3b1107600a585af71755f19d27218ef4690ef180f8018.png',
    'https://static.prod-images.emergentagent.com/jobs/3b78c97f-d2eb-45fd-ae96-0647fd26bb32/images/07c183d45bb6506c1b45d635049cd8ec7d12007909e449d68d2173e57c53cef5.png',
  ],
};

const ROTATE_MS = 35000;

const DEFAULT_BG_VISIBILITY = {
  minOpacityLight: 0.15,
  minOpacityDark: 0.18,
  overlayLight: 'linear-gradient(180deg, rgba(245,248,252,0.68) 0%, rgba(245,248,252,0.55) 35%, rgba(245,248,252,0.58) 65%, rgba(245,248,252,0.72) 100%)',
  overlayDark: 'linear-gradient(180deg, rgba(5,10,24,0.76) 0%, rgba(5,10,24,0.66) 42%, rgba(5,10,24,0.80) 100%)',
} as const;

const HOME_BG_VISIBILITY = {
  imageOpacityLight: 0.82,
  imageOpacityDark: 0.72,
  overlayLight: 'linear-gradient(180deg, rgba(248,250,252,0.20) 0%, rgba(248,250,252,0.12) 34%, rgba(248,250,252,0.18) 68%, rgba(248,250,252,0.26) 100%)',
  overlayDark: 'linear-gradient(180deg, rgba(5,10,24,0.26) 0%, rgba(5,10,24,0.16) 38%, rgba(5,10,24,0.34) 100%)',
  imageFilterLight: 'brightness(1.06) contrast(1.14) saturate(1.10)',
  imageFilterDark: 'brightness(0.92) contrast(1.16) saturate(1.10)',
  accentLight: 'radial-gradient(circle at 18% 16%, rgba(56,189,248,0.12) 0%, rgba(56,189,248,0.00) 30%), radial-gradient(circle at 78% 22%, rgba(59,130,246,0.10) 0%, rgba(59,130,246,0.00) 28%), radial-gradient(circle at 58% 76%, rgba(16,185,129,0.08) 0%, rgba(16,185,129,0.00) 24%)',
  accentDark: 'radial-gradient(circle at 18% 16%, rgba(34,211,238,0.22) 0%, rgba(34,211,238,0.00) 30%), radial-gradient(circle at 78% 22%, rgba(99,102,241,0.18) 0%, rgba(99,102,241,0.00) 28%), radial-gradient(circle at 58% 76%, rgba(16,185,129,0.14) 0%, rgba(16,185,129,0.00) 24%)',
} as const;

interface Props {
  variant?: keyof typeof PAGE_COLLECTIONS;
}

export default function PageFloatingBackground({ variant = 'default' }: Props) {
  const { darkMode } = useTheme();
  const { brightness, getEffectivePreset } = useBackgroundBrightness();
  
  // Check DOM attribute as fallback for SSR hydration
  const [isDark, setIsDark] = useState(darkMode);
  useEffect(() => {
    if (Platform.OS === 'web') {
      const attr = document.documentElement.getAttribute('data-theme-active');
      if (attr === 'dark') setIsDark(true);
      else if (attr === 'light') setIsDark(false);
    }
  }, []);
  useEffect(() => { setIsDark(darkMode); }, [darkMode]);
  // Resolve: page override > global preset > page-specific variant
  const effectivePreset = getEffectivePreset(variant);
  const images = (effectivePreset !== 'default' && PRESET_COLLECTIONS[effectivePreset])
    ? PRESET_COLLECTIONS[effectivePreset]
    : (PAGE_COLLECTIONS[variant] || PAGE_COLLECTIONS.default);
  const [activeIdx, setActiveIdx] = useState(() => Math.floor(Math.random() * images.length));
  const [prevIdx, setPrevIdx] = useState(activeIdx);
  const [transitioning, setTransitioning] = useState(false);
  const imagesRef = useRef(images);

  // Update ref when variant changes
  useEffect(() => { imagesRef.current = images; }, [images]);

  // Reset indices when variant changes
  useEffect(() => {
    const startIdx = Math.floor(Math.random() * images.length);
    setActiveIdx(startIdx);
    setPrevIdx(startIdx);
    setTransitioning(false);
  }, [variant, images.length]);

  const advance = useCallback(() => {
    setTransitioning(true);
    setActiveIdx(prev => {
      setPrevIdx(prev);
      return (prev + 1) % imagesRef.current.length;
    });
    setTimeout(() => setTransitioning(false), 1200);
  }, []);

  useEffect(() => {
    const timer = setInterval(advance, ROTATE_MS);
    return () => clearInterval(timer);
  }, [advance]);

  if (Platform.OS !== 'web') return null;

  const isHomeVariant = variant === 'home';
  const visibilityConfig = isHomeVariant ? HOME_BG_VISIBILITY : DEFAULT_BG_VISIBILITY;
  const requestedOpacity = (isDark ? Math.min(brightness, 40) : brightness) / 100;
  const effectiveOpacity = Math.max(
    requestedOpacity,
    isDark ? DEFAULT_BG_VISIBILITY.minOpacityDark : DEFAULT_BG_VISIBILITY.minOpacityLight,
  );
  const homeImageOpacity = isDark ? HOME_BG_VISIBILITY.imageOpacityDark : HOME_BG_VISIBILITY.imageOpacityLight;
  const imageFilter = isDark ? HOME_BG_VISIBILITY.imageFilterDark : HOME_BG_VISIBILITY.imageFilterLight;

  return (
    <div
      data-testid="page-floating-background"
      data-variant={variant}
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
        opacity: isHomeVariant ? 1 : effectiveOpacity,
        transition: 'opacity 0.4s ease',
      }}
    >
      {/* Previous image (fades out during transition) */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `url(${images[prevIdx]})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          opacity: transitioning ? 0 : (isHomeVariant ? homeImageOpacity : 1),
          transition: 'opacity 1.2s ease-in-out, filter 0.5s ease',
          filter: isHomeVariant ? imageFilter : 'none',
        }}
      />
      {/* Active image (fades in during transition) */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `url(${images[activeIdx]})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          opacity: isHomeVariant ? homeImageOpacity : 1,
          transition: 'opacity 1.2s ease-in-out, filter 0.5s ease',
          filter: isHomeVariant ? imageFilter : 'none',
        }}
      />
      {/* Theme-aware overlay */}
      <div
        data-testid="page-floating-bg-overlay"
        className="pfb-overlay"
        style={{
          position: 'absolute',
          inset: 0,
          background: isDark ? visibilityConfig.overlayDark : visibilityConfig.overlayLight,
          transition: 'background 0.5s ease',
          zIndex: 1,
        }}
      />
      {isHomeVariant ? (
        <div
          data-testid="page-floating-bg-accent"
          style={{
            position: 'absolute',
            inset: 0,
            background: isDark ? HOME_BG_VISIBILITY.accentDark : HOME_BG_VISIBILITY.accentLight,
            zIndex: 2,
          }}
        />
      ) : null}
    </div>
  );
}

/* i18n-probe t('i18n.auto.probe') */
