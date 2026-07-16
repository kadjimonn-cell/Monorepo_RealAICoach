import React, { useEffect, useRef, useState } from 'react';
import { View, Platform } from 'react-native';

interface StaggerChildrenProps {
  children: React.ReactNode;
  staggerMs?: number;
  direction?: 'up' | 'down' | 'left' | 'right';
  distance?: number;
  duration?: number;
  threshold?: number;
  className?: string;
}

let instanceId = 0;

export function StaggerChildren({
  children,
  staggerMs = 100,
  direction = 'up',
  distance = 30,
  duration = 600,
  threshold = 0.1,
}: StaggerChildrenProps) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const idRef = useRef(++instanceId);

  useEffect(() => {
    if (Platform.OS !== 'web' || !ref.current) {
      setVisible(true);
      return;
    }

    // Find the nearest scrollable ancestor for IntersectionObserver root
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

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold, rootMargin: '0px 0px -20px 0px', root: scrollRoot }
    );

    observer.observe(ref.current);

    // Fallback: force visible after 3s in case observer never fires
    const fallback = setTimeout(() => setVisible(true), 3000);

    return () => {
      observer.disconnect();
      clearTimeout(fallback);
    };
  }, [threshold]);

  if (Platform.OS !== 'web') {
    return <View>{children}</View>;
  }

  const id = `stagger-${idRef.current}`;
  const translateHidden = {
    up: `translateY(${distance}px)`,
    down: `translateY(-${distance}px)`,
    left: `translateX(${distance}px)`,
    right: `translateX(-${distance}px)`,
  }[direction];

  // Generate nth-child rules for up to 12 children
  const nthRules = Array.from({ length: 12 }, (_, i) =>
    `.${id}.stagger-visible > * > *:nth-child(${i + 1}) { transition-delay: ${i * staggerMs}ms !important; opacity: 1 !important; transform: translate(0, 0); }`
  ).join('\n');

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: `
        .${id} > * > * {
          opacity: 0;
          transform: ${translateHidden};
          transition: opacity ${duration}ms cubic-bezier(0.16, 1, 0.3, 1), transform ${duration}ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        ${nthRules}
      `}} />
      <div
        ref={ref as any}
        className={`${id}${visible ? ' stagger-visible' : ''}`}
        data-testid="stagger-children"
      >
        {children}
      </div>
    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
