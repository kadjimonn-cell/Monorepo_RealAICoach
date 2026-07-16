import React, { useEffect, useRef, useState } from 'react';
import { View, Platform } from 'react-native';

interface ScrollRevealProps {
  children: React.ReactNode;
  delay?: number;
  direction?: 'up' | 'down' | 'left' | 'right';
  distance?: number;
  duration?: number;
  threshold?: number;
}

export function ScrollReveal({
  children,
  delay = 0,
  direction = 'up',
  distance = 40,
  duration = 800,
  threshold = 0.15,
}: ScrollRevealProps) {
  const [visible, setVisible] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (Platform.OS !== 'web' || !ref.current) {
      setVisible(true);
      return;
    }

    const mediaQuery = typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)')
      : null;
    const reducedMotion = Boolean(mediaQuery?.matches);
    setPrefersReducedMotion(reducedMotion);
    if (reducedMotion) {
      setVisible(true);
      return;
    }

    let scrollRoot: Element | null = null;
    let el = ref.current.parentElement;
    while (el) {
      const overflow = window.getComputedStyle(el).overflowY;
      if (overflow === 'auto' || overflow === 'scroll') {
        scrollRoot = el;
        break;
      }
      el = el.parentElement;
    }

    const revealRootMargin = `0px 0px -${Math.max(32, Math.round(distance * 0.9))}px 0px`;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold, rootMargin: revealRootMargin, root: scrollRoot }
    );

    observer.observe(ref.current);

    const fallback = setTimeout(() => setVisible(true), 3000);

    const syncReducedMotion = (event: MediaQueryListEvent) => {
      setPrefersReducedMotion(Boolean(event.matches));
      if (event.matches) {
        setVisible(true);
        observer.disconnect();
      }
    };

    if (mediaQuery?.addEventListener) {
      mediaQuery.addEventListener('change', syncReducedMotion);
    } else if (mediaQuery?.addListener) {
      mediaQuery.addListener(syncReducedMotion);
    }

    return () => {
      observer.disconnect();
      clearTimeout(fallback);
      if (mediaQuery?.removeEventListener) {
        mediaQuery.removeEventListener('change', syncReducedMotion);
      } else if (mediaQuery?.removeListener) {
        mediaQuery.removeListener(syncReducedMotion);
      }
    };
  }, [distance, threshold]);

  if (Platform.OS !== 'web') {
    return <View>{children}</View>;
  }

  const translateMap = {
    up: `translateY(${distance}px)`,
    down: `translateY(-${distance}px)`,
    left: `translateX(${distance}px)`,
    right: `translateX(-${distance}px)`,
  };

  return (
    <div
      ref={ref as any}
      data-testid="scroll-reveal"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        width: '100%',
        opacity: visible || prefersReducedMotion ? 1 : 0,
        transform: visible || prefersReducedMotion ? 'translate(0, 0)' : translateMap[direction],
        transition: prefersReducedMotion
          ? 'none'
          : `opacity ${duration}ms cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms, transform ${duration}ms cubic-bezier(0.16, 1, 0.3, 1) ${delay}ms`,
        willChange: visible || prefersReducedMotion ? 'auto' : 'opacity, transform',
      }}
    >
      {children}
    </div>
  );
}

/* i18n-probe t('i18n.auto.probe') */
