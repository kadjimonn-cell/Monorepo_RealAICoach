import { useState, useEffect, useRef, useCallback } from 'react';
import { Text, Platform } from 'react-native';

interface AnimatedCounterProps {
  value: number;
  format?: 'number' | 'k' | 'percent' | 'plus-percent';
  duration?: number;
  style?: any;
  prefix?: string;
  suffix?: string;
}

export function AnimatedCounter({
  value,
  format = 'number',
  duration = 800,
  style,
  prefix = '',
  suffix = '',
}: AnimatedCounterProps) {
  const [display, setDisplay] = useState(value);
  const prevRef = useRef(value);
  const rafRef = useRef<number | null>(null);

  const formatValue = useCallback((n: number) => {
    if (format === 'k') {
      return n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(Math.round(n));
    }
    if (format === 'percent') {
      return `${Math.round(n)}%`;
    }
    if (format === 'plus-percent') {
      return `+${Math.round(n)}%`;
    }
    return n >= 1000 ? n.toLocaleString() : String(Math.round(n));
  }, [format]);

  useEffect(() => {
    if (Platform.OS !== 'web' || prevRef.current === value) {
      prevRef.current = value;
      setDisplay(value);
      return;
    }

    const from = prevRef.current;
    const to = value;
    const diff = to - from;
    const startTime = performance.now();

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic for smooth deceleration
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = from + diff * eased;
      setDisplay(current);

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        setDisplay(to);
        prevRef.current = to;
      }
    };

    rafRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [value, duration]);

  return (
    <Text style={style}>
      {prefix}{formatValue(display)}{suffix}
    </Text>
  );
}

/* i18n-probe t('i18n.auto.probe') */
