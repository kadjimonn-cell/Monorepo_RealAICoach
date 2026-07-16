import { useEffect, useState, useCallback } from 'react';
import { Platform, useWindowDimensions } from 'react-native';

// Helper to get current window width on web
const getWebWidth = (fallback: number): number => {
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    const candidates: number[] = [];

    const visualViewportWidth = Number(window.visualViewport?.width || 0);
    if (Number.isFinite(visualViewportWidth) && visualViewportWidth > 0) {
      candidates.push(visualViewportWidth);
    }

    const innerWidth = Number(window.innerWidth || 0);
    if (Number.isFinite(innerWidth) && innerWidth > 0) {
      candidates.push(innerWidth);
    }

    const docWidth = Number(document.documentElement?.clientWidth || 0);
    if (Number.isFinite(docWidth) && docWidth > 0) {
      candidates.push(docWidth);
    }

    const bodyWidth = Number(document.body?.clientWidth || 0);
    if (Number.isFinite(bodyWidth) && bodyWidth > 0) {
      candidates.push(bodyWidth);
    }

    const rootRectWidth = Number(document.getElementById('root')?.getBoundingClientRect?.().width || 0);
    if (Number.isFinite(rootRectWidth) && rootRectWidth > 0) {
      candidates.push(rootRectWidth);
    }

    if (candidates.length > 0) {
      return Math.round(Math.min(...candidates));
    }

    return fallback;
  }
  return fallback;
};

export const useViewportWidth = () => {
  const { width: rnWidth } = useWindowDimensions();
  
  // For web, always prefer window.innerWidth
  // Initialize with a function that checks window.innerWidth immediately
  const [webWidth, setWebWidth] = useState(() => getWebWidth(rnWidth));

  // Sync function that updates state with current window width
  const sync = useCallback(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const currentWidth = getWebWidth(rnWidth);
      setWebWidth((prev) => (prev !== currentWidth ? currentWidth : prev));
    }
  }, [rnWidth]);

  // Effect to sync on mount and listen for resize/orientation changes
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;

    // Sync immediately on mount to catch any SSR/hydration mismatches
    sync();

    // Also sync on next frame to ensure we have the correct value after hydration
    const rafId = requestAnimationFrame(sync);

    window.addEventListener('resize', sync);
    window.addEventListener('orientationchange', sync);
    window.visualViewport?.addEventListener('resize', sync);
    window.visualViewport?.addEventListener('scroll', sync);
    
    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', sync);
      window.removeEventListener('orientationchange', sync);
      window.visualViewport?.removeEventListener('resize', sync);
      window.visualViewport?.removeEventListener('scroll', sync);
    };
  }, [sync]);

  // Also sync when rnWidth changes (in case useWindowDimensions updates)
  useEffect(() => {
    sync();
  }, [rnWidth, sync]);

  return Platform.OS === 'web' ? webWidth : rnWidth;
};
