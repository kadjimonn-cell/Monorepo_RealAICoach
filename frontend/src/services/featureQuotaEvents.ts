export type FeatureQuotaLimitEvent = {
  featureKey: string;
  used: number;
  limit: number;
};

type Listener = (event: FeatureQuotaLimitEvent) => void;

const listeners = new Set<Listener>();

export const onFeatureQuotaLimit = (listener: Listener): (() => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const emitFeatureQuotaLimit = (event: FeatureQuotaLimitEvent) => {
  listeners.forEach((listener) => {
    try {
      listener(event);
    } catch {}
  });
};
