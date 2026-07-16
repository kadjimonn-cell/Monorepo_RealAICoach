import { useEffect, useState, useCallback, useRef } from 'react';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

type ABVariant = {
  experiment_id: string;
  variant_id: string;
  variant_name: string;
  config: Record<string, any>;
} | null;

const variantCache: Record<string, { data: ABVariant; ts: number }> = {};
const CACHE_TTL = 5 * 60_000; // 5 minutes

export function useABVariant(target: string) {
  const [variant, setVariant] = useState<ABVariant>(null);
  const [loading, setLoading] = useState(true);
  const trackedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      // Check cache first
      const cached = variantCache[target];
      if (cached && Date.now() - cached.ts < CACHE_TTL) {
        setVariant(cached.data);
        setLoading(false);
        return;
      }

      try {
        const res = await api.get(`/prompt-experiment/variant?target=${target}`);
        const d = res.data;
        const v = d.experiment_id ? d : null;
        variantCache[target] = { data: v, ts: Date.now() };
        if (!cancelled) setVariant(v);
      } catch {
        if (!cancelled) setVariant(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, [target]);

  const trackEvent = useCallback(
    async (event: string, metadata?: Record<string, any>) => {
      if (!variant) return;
      // Dedupe: only track each event type once per mount
      const key = `${variant.experiment_id}:${variant.variant_id}:${event}`;
      if (trackedRef.current.has(key)) return;
      trackedRef.current.add(key);

      try {
        await api.post('/prompt-experiment/track', {
          experiment_id: variant.experiment_id,
          variant_id: variant.variant_id,
          event,
          metadata: metadata || {},
        });
      } catch (error) { handleAppRecoverableError({ scope: 'src/hooks/useABVariant.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    },
    [variant]
  );

  // Helper to read config with fallback
  const getConfig = useCallback(
    (key: string, fallback: any = undefined) => {
      return variant?.config?.[key] ?? fallback;
    },
    [variant]
  );

  return { variant, loading, trackEvent, getConfig, isActive: !!variant };
}
