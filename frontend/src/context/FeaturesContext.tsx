import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import { useRealtimeEvent } from './RealtimeContext';

export interface Feature {
  feature_id: string;
  id?: string;
  title: string;
  description: string;
  icon: string;
  route: string;
  category: string;
  color: string;
  is_new?: boolean;
  isNew?: boolean;
  premium?: boolean;
  enabled?: boolean;
  sort_order?: number;
}

export interface FeatureCategory {
  id: string;
  label: string;
}

interface FeaturesContextType {
  features: Feature[];
  categories: FeatureCategory[];
  loading: boolean;
  error: string | null;
  refreshFeatures: () => Promise<void>;
  getFeatureById: (id: string) => Feature | undefined;
  getFeaturesByCategory: (category: string) => Feature[];
  totalCount: number;
  lastUpdated: string | null;
  source: 'live';
  recoveryActive: false;
}

const FeaturesContext = createContext<FeaturesContextType>({
  features: [],
  categories: [],
  loading: true,
  error: null,
  refreshFeatures: async () => {},
  getFeatureById: () => undefined,
  getFeaturesByCategory: () => [],
  totalCount: 0,
  lastUpdated: null,
  source: 'live',
  recoveryActive: false,
});

export function FeaturesProvider({ children }: { children: React.ReactNode }) {
  const [features, setFeatures] = useState<Feature[]>([]);
  const [categories, setCategories] = useState<FeatureCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const fetchFeatures = useCallback(async () => {
    try {
      setError(null);
      const resp = await api.get('/features/registry', {
        silentLoading: true,
        timeout: 12000,
      });
      if (mountedRef.current && resp.data) {
        const feats = (resp.data.features || []).map((f: any) => ({
          ...f,
          id: f.feature_id || f.id,
          isNew: f.is_new,
        }));
        setFeatures(feats);
        setCategories(resp.data.categories || []);
        const nextLastUpdated = resp.data.timestamp || new Date().toISOString();
        setLastUpdated(nextLastUpdated);
        setLoading(false);
      }
    } catch (e: any) {
      if (mountedRef.current) {
        console.error('[FeaturesContext] Failed to fetch features:', e?.message);
        setError(e?.message || 'Failed to load features');
        setLoading(false);
      }
    }
  }, []);

  // Subscribe to real-time feature changes via shared RealtimeProvider
  useRealtimeEvent('features', fetchFeatures);
  useRealtimeEvent('config', fetchFeatures);

  useEffect(() => {
    mountedRef.current = true;
    fetchFeatures();
    // Fallback poll every 60s
    const interval = setInterval(fetchFeatures, 60000);
    return () => { mountedRef.current = false; clearInterval(interval); };
  }, [fetchFeatures]);

  const getFeatureById = useCallback(
    (id: string) => features.find(f => f.feature_id === id || f.id === id),
    [features],
  );

  const getFeaturesByCategory = useCallback(
    (category: string) =>
      category === 'all' ? features : features.filter(f => f.category === category),
    [features],
  );

  return (
    <FeaturesContext.Provider
      value={{
        features,
        categories,
        loading,
        error,
        refreshFeatures: fetchFeatures,
        getFeatureById,
        getFeaturesByCategory,
        totalCount: features.length,
        lastUpdated,
        source: 'live',
        recoveryActive: false,
      }}
    >
      {children}
    </FeaturesContext.Provider>
  );
}

export const useFeatures = () => useContext(FeaturesContext);
