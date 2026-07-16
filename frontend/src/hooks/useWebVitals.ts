import { useEffect } from 'react';
import { Platform } from 'react-native';
import { reportClientCrash } from '../services/clientErrorReporter';

export function useWebVitals() {
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    
    let reported = false;
    
    const reportVitals = async () => {
      if (reported) return;
      try {
        const vitals = await import('web-vitals');
        const metrics = {};
        let count = 0;

        const handlers = [
          { fn: vitals.onLCP, assign: (value) => { metrics.lcp = Math.round(value) / 1000; } },
          { fn: vitals.onCLS, assign: (value) => { metrics.cls = Math.round(value * 1000) / 1000; } },
          { fn: vitals.onFCP, assign: (value) => { metrics.fcp = Math.round(value) / 1000; } },
          { fn: vitals.onTTFB, assign: (value) => { metrics.ttfb = Math.round(value) / 1000; } },
          { fn: vitals.onINP, assign: (value) => { metrics.inp = Math.round(value); } },
        ].filter((handler) => typeof handler.fn === 'function');

        // wait for at least 3 available metrics (or all if fewer are available)
        const target = Math.max(1, Math.min(3, handlers.length));
        
        const send = () => {
          if (reported) return;
          count++;
          if (count >= target) {
            reported = true;
            const payload = {
              lcp: metrics.lcp || 0,
              fid: metrics.fid || 0,
              cls: metrics.cls || 0,
              fcp: metrics.fcp || 0,
              ttfb: metrics.ttfb || 0,
              inp: metrics.inp || 0,
              url: window.location.pathname,
              screen_width: window.innerWidth,
            };
            const apiUrl = typeof window !== 'undefined' ? `https://${window.location.host}` : (process.env.EXPO_PUBLIC_BACKEND_URL || '').replace(/^http:\/\//i, 'https://');
            navigator.sendBeacon?.(
              `${apiUrl}/api/seo/web-vitals`,
              JSON.stringify(payload)
            ) || fetch(`${apiUrl}/api/seo/web-vitals`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
              keepalive: true,
            }).catch(() => {});
          }
        };
        
        for (const { fn, assign } of handlers) {
          fn((metric) => {
            assign(metric.value);
            send();
          });
        }

        if (handlers.length === 0) {
          reportClientCrash({
            panelId: 'telemetry:web-vitals:no-handlers',
            panelName: 'useWebVitals',
            message: 'web-vitals import loaded without callable handlers',
          });
        }
      } catch (error) {
        // Telemetry failures must never interrupt UI with retry popups.
        reportClientCrash({
          panelId: 'telemetry:web-vitals:init',
          panelName: 'useWebVitals',
          message: 'web-vitals initialization failed',
          stack: String(error?.stack || error?.message || error || ''),
        });
      }
    };
    
    // Delay to not compete with initial page load
    const timer = setTimeout(reportVitals, 3000);
    return () => clearTimeout(timer);
  }, []);
}
